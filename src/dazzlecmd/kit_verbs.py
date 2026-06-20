"""The kit inverse-verb registry -- the declared ``{P, not-P}`` pairs the kit
presence axes expose, and the grouped ``dz kit -h`` epilog driven from it.

Each entry is an inverse-pair (the Groupable ``{cold, warm}`` atom surfacing in
the CLI verb layer): a WARM verb (more present -- ``enable``/``attach``/``add``)
and its COLD inverse (letting-go -- ``disable``/``detach``/``remove``), tagged
with the presence AXIS it moves on, that axis's coldward RANK on the unified
kit-lifecycle gradient, and the axis's cascade COUPLING.

One declared source: the help rendering reads it, so adding a future verb-pair
updates ``dz kit -h`` with no other edit. This is the kit-local first cut (per the
kit-lifecycle command-grouping DWP, 2026-06-19); the generalized cross-tool
"inverse-pairs in help anywhere" facility (the dazzle-lib ``hint_lib`` analog) is a
later follow-up. When it lands, a pair's ``{cold, warm, axis}`` maps directly onto
``dazzle_lib.Groupable`` ``{minus, plus, meaning}``.
"""
from __future__ import annotations

from dataclasses import dataclass


# Cascade coupling -- declared per axis (the slice-4 Gauss-Jordan property):
#   aligned     = nested axes fused onto one gradient -> a colder move IMPLICITLY
#                 subsumes the warmer (detach already disables); the lifecycle.
#   independent = free columns (Gauss-Jordan) -> cascade is OPT-IN, per channel.
COUPLING_ALIGNED = "aligned"
COUPLING_INDEPENDENT = "independent"


@dataclass(frozen=True)
class KitVerbPair:
    """An inverse verb-pair on a kit presence axis (the ``{P, not-P}`` atom).

    ``warm`` is the +/grouping verb (more present); ``cold`` is the -/ungrouping
    verb (letting-go). ``rank`` is the axis's coldward depth on the unified
    ``{KitOff, KitOn}`` lifecycle continuum (``activation`` is the weakest/innermost
    letting-go, ``membership`` the strongest/outermost); ``0`` = NOT on that
    gradient (an independent axis -- e.g. favorite, or the visibility channels).
    """

    warm: str
    cold: str
    axis: str
    rank: int
    coupling: str
    gloss: str = ""


# The unified kit-lifecycle continuum {KitOff, KitOn}: nested presence axes fused
# onto one common gradient -- to be active a kit must be loaded; to be loaded, a
# member. Declared WARM-first (rank -1 -> -3 = innermost/warmest -> outermost/
# coldest), so the natural display order reads warm -> cold. The coldward cascade
# is IMPLICIT here (detach already disables -- the dependent pivot).
LIFECYCLE_PAIRS = (
    KitVerbPair("enable", "disable", "activation", -1, COUPLING_ALIGNED,
                "active vs loaded-but-inactive"),
    KitVerbPair("attach", "detach", "loading", -2, COUPLING_ALIGNED,
                "loaded vs a pointer (listed, not loaded)"),
    KitVerbPair("add", "remove", "membership", -3, COUPLING_ALIGNED,
                "registered vs deregistered + trashed"),
)

# Independent axes (NOT on the lifecycle gradient; opt-in cascade). favorite is a
# config-pointer pair; the visibility channels live under ``dz kit visibility``.
FAVORITE_PAIR = KitVerbPair("favorite", "unfavorite", "favorite", 0,
                            COUPLING_INDEPENDENT, "a saved shortcut name")

VISIBILITY_PAIRS = (
    KitVerbPair("unsilence", "silence", "visibility", 0, COUPLING_INDEPENDENT,
                "show the rerooting hint vs suppress it"),
    KitVerbPair("unhide", "hide", "visibility", 0, COUPLING_INDEPENDENT,
                "shown in listings vs omitted (still dispatchable)"),
    KitVerbPair("unshadow", "shadow", "visibility", 0, COUPLING_INDEPENDENT,
                "in dispatch vs removed + short name freed"),
)

# Generic inspect verbs (not toggles -- no inverse).
GENERIC_VERBS = (
    ("list", "list kits, or the tools in a kit"),
    ("status", "show active kits"),
    ("focus", "enable only the named kit(s)"),
    ("reset", "clear kit config to defaults"),
)

# Every pair (for iteration / the generalized facility later).
ALL_PAIRS = LIFECYCLE_PAIRS + (FAVORITE_PAIR,) + VISIBILITY_PAIRS


# ---------------------------------------------------------------------------
# Grammar: the flat verbs AND the nested per-axis groups, from ONE spec.
#
# `dz kit visibility` is the template -- a nested sub-group whose verbs route to
# handlers. We mirror it per lifecycle axis: `dz kit {activation,loading,
# membership}`. The verb arg-setup lives in ONE place (VERB_SPEC), shared by the
# flat `dz kit <verb>` form and the nested `dz kit <axis> <verb>` form -- both set
# the SAME `_meta`, so they route to the SAME handler (`dz kit activation enable`
# == `dz kit enable`). The flat forms are kept as aliases (non-breaking).
# ---------------------------------------------------------------------------

def _add_enable(p):
    p.add_argument("name", help="Kit name to enable")
    p.set_defaults(_meta="kit_enable")


def _add_disable(p):
    p.add_argument("name", help="Kit name to disable")
    p.set_defaults(_meta="kit_disable")


def _add_attach(p):
    p.add_argument("name", help="Kit name to attach")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan; change nothing")
    p.set_defaults(_meta="kit_attach")


def _add_detach(p):
    p.add_argument("name", help="Kit name to detach")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan; change nothing")
    p.set_defaults(_meta="kit_detach")


def _add_add(p):
    p.add_argument("url", help="Git URL of the kit repo")
    p.add_argument("--name", help="Override kit name (default: derive from URL)")
    p.add_argument("--branch", help="Branch to check out (default: repo default)")
    p.add_argument("--shallow", action="store_true", help="Shallow clone")
    p.set_defaults(_meta="kit_add")


def _add_remove(p):
    p.add_argument("name", help="Kit name to remove")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan; change nothing")
    p.add_argument("--yes", action="store_true",
                   help="Skip the confirmation prompt")
    p.add_argument("--force", action="store_true",
                   help="Proceed despite a dirty submodule worktree")
    p.set_defaults(_meta="kit_remove")


# verb -> (help, arg-adder). The adder sets the verb's args AND its `_meta`.
VERB_SPEC = {
    "enable":  ("Enable a kit (include its tools in dispatch)", _add_enable),
    "disable": ("Disable a kit (exclude its tools from dispatch)", _add_disable),
    "attach":  ("Attach a kit -- the inverse of detach: load its tools again "
                "+ enable", _add_attach),
    "detach":  ("Detach a kit -- make it a pointer (listed, not loaded) + "
                "disable; files kept", _add_detach),
    "add":     ("Add a kit from a git URL via submodule", _add_add),
    "remove":  ("Remove a kit -- deregister + safedel its files (recoverable)",
                _add_remove),
}

# Per-axis group help (the nested `dz kit <axis>` parser's one-liner).
_AXIS_HELP = {
    "activation": "Activation axis: enable/disable a kit (loaded, on vs off)",
    "loading":    "Loading axis: attach/detach a kit (loaded vs a pointer)",
    "membership": "Membership axis: add/remove a kit (registered vs gone)",
}


def add_flat_verb(kit_sub, verb):
    """Register the flat `dz kit <verb>` parser from the shared spec."""
    help_text, adder = VERB_SPEC[verb]
    p = kit_sub.add_parser(verb, help=help_text)
    adder(p)
    return p


def build_lifecycle_axis_groups(kit_sub):
    """Register the nested per-axis groups `dz kit {activation,loading,membership}`
    -- the same shape as `dz kit visibility`, driven by LIFECYCLE_PAIRS. Each
    group's warm/cold verbs share VERB_SPEC (and thus the handler) with the flat
    forms. A group with no verb routes to ``_meta='kit_axis_<axis>'`` (a summary)."""
    for pair in LIFECYCLE_PAIRS:
        group = kit_sub.add_parser(pair.axis, help=_AXIS_HELP[pair.axis])
        axis_sub = group.add_subparsers(dest=f"{pair.axis}_command")
        for verb in (pair.warm, pair.cold):     # warm-first (enable before disable)
            help_text, adder = VERB_SPEC[verb]
            adder(axis_sub.add_parser(verb, help=help_text))
        group.set_defaults(_meta=f"kit_axis_{pair.axis}")


_ARROW = "<->"
_HELP_COL = 17   # the column a verb's description starts at

# Visibility verbs in presence order, pulled UP into `dz kit -h` from the nested
# `dz kit visibility` sub-group (status first -- the generic inspect verb).
_VISIBILITY_ORDER = (
    "status", "silence", "unsilence", "hide", "unhide", "shadow", "unshadow",
)


def _hrow(indent: int, name: str, text: str) -> str:
    """One ``<indent><name>  <text>`` row, the description aligned at ``_HELP_COL``
    (with a >=2-space gap if the name overruns the column)."""
    prefix = " " * indent + name
    if not text:
        return prefix
    gap = max(2, _HELP_COL - len(prefix))
    return prefix + " " * gap + text


def _kit_help_sources(parser):
    """``(top, vis)`` name->help maps -- ``top`` from the kit subcommands, ``vis``
    from the nested ``dz kit visibility`` sub-group. Read from the ACTUAL parsers
    (single source of truth -- no help strings are duplicated in this module)."""
    import argparse

    top, vis = {}, {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            top = {ca.dest: (ca.help or "") for ca in action._choices_actions}
            visp = action.choices.get("visibility")
            if visp is not None:
                for va in visp._actions:
                    if isinstance(va, argparse._SubParsersAction):
                        vis = {ca.dest: (ca.help or "")
                               for ca in va._choices_actions}
            break
    return top, vis


def render_kit_help(parser) -> str:
    """The de-duplicated, by-axis ``dz kit -h`` body -- replaces argparse's default
    positional restatement so each verb appears ONCE. The structure (sections,
    axes, pairings) is registry-driven; the per-verb descriptions are read from the
    real sub-parsers via :func:`_kit_help_sources`, so they never drift. The full
    hierarchical help *toolset* (the cross-aggregator homogenization) is the 0.11
    line; this is the generalized-enough render that ships now."""
    top, vis = _kit_help_sources(parser)
    out = [parser.format_usage().rstrip("\n"), ""]
    out.append("Each presence axis is also a group (`dz kit <axis> -h`); warm<->cold,")
    out.append("a colder move subsumes the warmer (e.g. detach also disables).")
    out.append("")
    out.append("kit verbs by presence axis:")
    out.append("")

    out.append("  inspect:")
    for name, gloss in GENERIC_VERBS:
        out.append(_hrow(4, name, gloss))
    out.append("")

    out.append(_hrow(2, "management:",
                     "`dz kit management [<kit>]` -- lifecycle state; verbs take a <kit>"))
    for pair in reversed(LIFECYCLE_PAIRS):   # coldest-first: membership, loading, activation
        out.append(_hrow(4, pair.axis, f"{pair.warm}{_ARROW}{pair.cold}  ({pair.gloss})"))
        for verb in (pair.warm, pair.cold):
            out.append(_hrow(6, verb, top.get(verb, "")))
        out.append("")

    out.append(_hrow(2, "visibility:",
                     "silence/hide/shadow + inverses -- see `dz kit visibility -h`"))
    for name in _VISIBILITY_ORDER:
        if name in vis:
            out.append(_hrow(4, name, vis[name]))
    out.append("")

    fp = FAVORITE_PAIR
    out.append(_hrow(2, "favorite:", f"{fp.warm} {_ARROW} {fp.cold}  {fp.gloss}"))
    for verb in (fp.warm, fp.cold):
        out.append(_hrow(4, verb, top.get(verb, "")))
    out.append("")

    out.append("options:")
    out.append(_hrow(2, "-h, --help", "show this help message and exit"))
    out.append("")
    out.append("Run 'dz kit <verb> --help' for a specific verb.")
    return "\n".join(out) + "\n"
