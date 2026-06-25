"""SPIKE (DWP ground-truth, 2026-06-25): prove or break the verb x level generic
dispatcher -- the reuse hypothesis (Option A).

Claim under test: a SINGLE generic dispatcher can route `dz <verb> <target>` for
BOTH a pole-less INSPECT verb (info) AND a poled TOGGLE verb (enable/disable on
the activation axis) into ONE flat `<level>_<verb>` handler table, with ZERO
per-verb and ZERO per-level `if` branching in the dispatcher body -- using only
the already-built primitives:
  - engine.resolve_target(name, applies_at, ...) -> (entity, level)   [B4]
  - resolve_special(token) -> (VerbAxis, pole)                        [B1]
  - meta_tag_for(axis, pole, level) -> "<level>_<special>"            [B1]
and a handler table keyed by the SAME `<level>_<verb>` tags the existing
`dz kit info`/`dz kit enable` parsers already set as `_meta`.

Run: python tests/one-offs/thinking/spike_verb_level_dispatch.py
Exit 0 = hypothesis holds; non-zero = it broke (read the assertion).
"""
import sys
import tempfile

from dazzlecmd_lib.engine import AggregatorEngine
from dazzlecmd_lib.verb_axis import (
    KIT, WARM, COLD, meta_tag_for, resolve_special, axis_by_name)
from dazzlecmd_lib.testing import make_tool, make_kit


# ---------------------------------------------------------------------------
# 1. The per-(verb, level) HANDLERS -- the ONLY thing a verb author writes.
#    Keyed by the `<level>_<verb>` tag (the same tags the grouped parsers set).
#    In the real CLI these are render_info / render_kit_info / _cmd_kit_enable /
#    ... living in dazzlecmd; here they are stubs that just record the call.
# ---------------------------------------------------------------------------
CALLS = []


def _h(label):
    def handler(entity, **ctx):
        CALLS.append((label, getattr(entity, "name", entity)))
        return 0
    return handler


HANDLERS = {
    # inspect verb `info` at every level
    "tool_info": _h("INFO@tool"),
    "kit_info": _h("INFO@kit"),
    "aggregator_info": _h("INFO@aggregator"),
    # toggle verb activation {enable, disable} -- kit level only (applies_at={kit})
    "kit_enable": _h("ENABLE@kit"),
    "kit_disable": _h("DISABLE@kit"),
}

# Which bare verbs are INSPECT verbs (pole-less, ordered continua -- info/status/
# list/tree). A toggle verb is anything resolve_special() recognises.
INSPECT_VERBS = {"info", "status", "list", "tree"}


# ---------------------------------------------------------------------------
# 2. The UNIFIED key generator -- the ONE function that resolves both verb
#    kinds to a `<level>_<verb>` tag. This is the inspect-vs-toggle unification
#    (Tension 1). It returns (applies_at, tag_fn) so the dispatcher can prune
#    levels per the verb's reach before resolving.
# ---------------------------------------------------------------------------
def verb_plan(token):
    """(applies_at_or_None, mutating, tag_fn(level)->tag) for a bare verb token.

    INSPECT verb  -> applies at all levels, not mutating, tag = `<level>_<verb>`.
    TOGGLE special -> applies_at from its VerbAxis, mutating, tag via meta_tag_for.
    Returns None if the token is neither (unknown verb).
    """
    if token in INSPECT_VERBS:
        return (None, False, lambda level: f"{level}_{token}")
    hit = resolve_special(token)            # e.g. "enable" -> (activation_axis, "warm")
    if hit is not None:
        va, pole = hit
        return (va.applies_at, True, lambda level: meta_tag_for(va.axis, pole, level))
    return None


# ---------------------------------------------------------------------------
# 3. The GENERIC DISPATCHER -- note: NO `if verb == ...`, NO `if level == ...`.
#    Just: plan the verb -> resolve the target's level -> compute the tag ->
#    look the handler up. Adding a verb adds a HANDLER, never a branch here.
# ---------------------------------------------------------------------------
def dispatch(engine, token, target):
    plan = verb_plan(token)
    if plan is None:
        print(f"  ! unknown verb {token!r}", file=sys.stderr)
        return 2
    applies_at, mutating, tag_fn = plan
    kwargs = {} if applies_at is None else {"applies_at": frozenset(applies_at)}
    res = engine.resolve_target(target, mutating=mutating, **kwargs)
    if res is None:
        print(f"  ! '{target}' not found for verb {token!r} (at its levels)")
        return 1
    tag = tag_fn(res.level)                  # may raise ValueError if off-level
    handler = HANDLERS.get(tag)
    if handler is None:
        print(f"  ! no handler registered for tag {tag!r}")
        return 1
    return handler(res.entity)


# ---------------------------------------------------------------------------
# 4. A REAL engine (isolated) with one tool, one kit, and the aggregator-self.
# ---------------------------------------------------------------------------
def _engine(tmp):
    eng = AggregatorEngine(name="dazzlecmd", command="dz", config_dir=tmp)
    eng.fqcn_index.insert_canonical(make_tool(
        name="thetool", namespace="core", _fqcn="core:thetool",
        short_name="thetool", kit_import_name="core"))
    eng.kits = [make_kit(name="thekit")]
    return eng


def main():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    failures = 0

    def expect(token, target, want_label):
        global CALLS
        CALLS = []
        rc = dispatch(eng, token, target)
        got = CALLS[0][0] if CALLS else None
        ok = (got == want_label)
        print(f"  dz {token:<8} {target:<9} -> tag-handler={got!r} rc={rc}  "
              f"{'OK' if ok else 'FAIL expected ' + repr(want_label)}")
        return ok

    print("INSPECT verb `info` routes by level (one verb, three levels):")
    ok1 = expect("info", "thetool", "INFO@tool")
    ok2 = expect("info", "thekit", "INFO@kit")
    ok3 = expect("info", "dz", "INFO@aggregator")       # aggregator by command

    print("\nTOGGLE verbs `enable`/`disable` (poled) route via meta_tag_for:")
    ok4 = expect("enable", "thekit", "ENABLE@kit")
    ok5 = expect("disable", "thekit", "DISABLE@kit")

    print("\nApplies_at PRUNES: `enable` (kit-only) on a TOOL must NOT act:")
    CALLS = []
    rc = dispatch(eng, "enable", "thetool")    # activation applies_at={kit} -> tool pruned
    ok6 = (rc == 1 and not CALLS)
    print(f"  dz enable   thetool   -> rc={rc} calls={CALLS}  "
          f"{'OK (no wrong-level mutation)' if ok6 else 'FAIL'}")

    print("\nUnknown verb is rejected cleanly (no handler invented):")
    CALLS = []
    rc = dispatch(eng, "teleport", "thekit")
    ok7 = (rc == 2 and not CALLS)
    print(f"  dz teleport thekit    -> rc={rc}  {'OK' if ok7 else 'FAIL'}")

    print("\nThe dispatcher body has ZERO per-verb / per-level branches:")
    import inspect as _inspect
    body = _inspect.getsource(dispatch)
    no_verb_branch = ('== "info"' not in body and '== "kit"' not in body
                      and '== "tool"' not in body and '== "aggregator"' not in body
                      and 'res.level ==' not in body)
    print(f"  dispatch() free of `verb ==`/`level ==` ladders: "
          f"{'OK' if no_verb_branch else 'FAIL'}")

    oks = [ok1, ok2, ok3, ok4, ok5, ok6, ok7, no_verb_branch]
    failures = oks.count(False)
    print(f"\n{'='*60}\nRESULT: {len(oks) - failures}/{len(oks)} checks passed "
          f"-- hypothesis {'HOLDS' if failures == 0 else 'BROKE'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
