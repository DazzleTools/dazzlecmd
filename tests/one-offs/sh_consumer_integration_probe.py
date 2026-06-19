"""SH consumer-integration PROBE (validate-first, no production rewiring).

Exercise the new dazzle-lib v0.6.5 bridges (poles/densify_between/from_groupable,
QuadrantView, Transition.kind, to_dict) against dazzlecmd's REAL production
structures -- VISIBILITY_CONTINUUM, KIT_PRESENCE_SPACE, the default registry --
to see whether they WORK on production data or need reshaping. Read-only; each
section is independent so one failure still shows the others' signal.

Run: python tests/one-offs/sh_consumer_integration_probe.py
"""
from fractions import Fraction


def section(t):
    print("\n== " + t + " ==")


def probe(label, fn):
    try:
        fn()
        print(f"  [OK] {label}")
    except Exception as e:  # noqa: BLE001 -- a probe wants ALL signals
        print(f"  [XX] {label}: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
section("VISIBILITY_CONTINUUM -- structure + ladder bridges")
try:
    from dazzlecmd_lib.states import VISIBILITY_CONTINUUM as VC
    print("  levels (cold->warm):", VC.levels())
    print("  cold_pole / warm_pole:", VC.cold_pole(), "/", VC.warm_pole())

    def _poles():
        g = VC.poles()
        print("    poles():", g, "| invert:", g.invert(), "| to_dict:", g.to_dict())
        assert g.minus == VC.cold_pole() and g.plus == VC.warm_pole()
    probe("poles() -> Groupable matches the real cold/warm poles", _poles)

    def _densify():
        ls = VC.levels()
        d = VC.densify_between(ls[0], ls[1], "__probe_rung__")
        r = d.rank("__probe_rung__")
        print(f"    densify_between({ls[0]!r}, {ls[1]!r}) -> rank {r} ({type(r).__name__})")
        print("    new ordering:", d.levels())
        assert VC.rank(ls[0]) < r < VC.rank(ls[1]) or VC.rank(ls[1]) < r < VC.rank(ls[0])
        # original is untouched (immutability) -> byte-transparent
        assert "__probe_rung__" not in VC.ranks
    probe("densify_between inserts an exact rung; original untouched", _densify)
except Exception as e:  # noqa: BLE001
    print(f"  [XX] could not import/probe VISIBILITY_CONTINUUM: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
section("KIT_PRESENCE_SPACE -- structure + the SH pairwise QuadrantView")
try:
    from dazzlecmd_lib.contexts import KIT_PRESENCE_SPACE as KPS
    axes = tuple(KPS.axes)
    print("  name:", KPS.name, "| axes:", axes, "| aligned:", KPS.is_aligned)

    if len(axes) >= 2:
        def _quad():
            qv = KPS.quadrants(axes[0], axes[1])
            print(f"    pair ({axes[0]}, {axes[1]}):")
            print("      quadrants:", qv.quadrants())
            print("      hidden_at Q1..Q4:", [qv.hidden_at(q) for q in ("Q1", "Q2", "Q3", "Q4")])
            print("      tau_steps:", qv.tau_steps())
            print("      diagonals:", qv.agreement_diagonal(), qv.disagreement_diagonal())
            assert len(set(qv.quadrants())) == 4
        probe("quadrants() yields a working QuadrantView over 2 real axes", _quad)
    else:
        print(f"  [..] KIT_PRESENCE_SPACE has {len(axes)} axis -> quadrants needs 2 "
              f"(single-axis presence space; pairwise view N/A here)")
except Exception as e:  # noqa: BLE001
    print(f"  [XX] could not import/probe KIT_PRESENCE_SPACE: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
section("Transition.kind -- lateral/generative on the real declared registry")
try:
    from dazzlecmd_lib.states import build_default_registry
    reg = build_default_registry()
    # TransitionRegistry exposes transitions() as a METHOD (not an iterable attr).
    raw = reg.transitions()
    trans = list(raw.values()) if hasattr(raw, "values") else list(raw)
    if trans:
        print(f"  {len(trans)} declared edge(s); kind classification:")
        for t in trans[:12]:
            verb = getattr(t, "verb", "?")
            kind = getattr(t, "kind", "(no .kind)")
            print(f"    {verb:<12} {getattr(t,'axis','?'):<14} -> kind={kind}")
        probe("every declared edge reports a .kind", lambda: [t.kind for t in trans])
    else:
        print("  [..] could not enumerate registry edges via common accessors;",
              "attrs:", [a for a in dir(reg) if not a.startswith('__')][:12])
except Exception as e:  # noqa: BLE001
    print(f"  [XX] could not import/probe the registry: {type(e).__name__}: {e}")

print("\n-- probe complete --")
