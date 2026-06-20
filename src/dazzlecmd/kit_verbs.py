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


def render_axis_summary(axis: str) -> str:
    """`dz kit <axis>` (no verb): the axis's pair + how to drive it."""
    pair = next(p for p in LIFECYCLE_PAIRS if p.axis == axis)
    return (
        f"{_AXIS_HELP[axis]}\n"
        f"  {pair.warm} {_ARROW} {pair.cold}   ({pair.gloss})\n"
        f"  run `dz kit {axis} {pair.warm} <name>` (or the flat alias "
        f"`dz kit {pair.warm} <name>`).\n"
        f"  `dz kit {axis} -h` for all options."
    )

_ARROW = "<->"
_AXIS_COL = 13   # the axis-name column
_PAIR_COL = 20   # the verb-pair column (glosses align here when the pair fits)


def _axis_row(axis: str, pair: str, gloss: str) -> str:
    """One ``    <axis>  <pair>  <gloss>`` row with a GUARANTEED >=2-space gap
    after the pair (so a pair wider than the column doesn't abut its gloss)."""
    gap = max(2, _PAIR_COL - len(pair))
    return f"    {axis:<{_AXIS_COL}}{pair}{' ' * gap}{gloss}"


def render_kit_help_epilog() -> str:
    """The grouped ``dz kit -h`` epilog, derived entirely from the registry above:
    the generic inspect verbs, the kit-lifecycle gradient (warm <-> cold, ordered
    coldward), the favorite pair, and a pointer to the visibility sub-group. The
    flat argparse subcommand list still renders above this -- nothing is hidden;
    this adds the axis/pairing structure that list lacks."""
    lines = ["kit verbs by presence axis:", ""]

    lines.append("  inspect:")
    for name, gloss in GENERIC_VERBS:
        lines.append(f"    {name:<13}{gloss}")
    lines.append("")

    lines.append("  lifecycle  (each axis is also a group -- `dz kit activation -h`;")
    lines.append("              warm<->cold, a colder move subsumes the warmer -- "
                 "detach also disables):")
    for p in LIFECYCLE_PAIRS:
        lines.append(_axis_row(p.axis, f"{p.warm} {_ARROW} {p.cold}", p.gloss))
    lines.append("")

    lines.append("  other:")
    fp = FAVORITE_PAIR
    lines.append(_axis_row(fp.axis, f"{fp.warm} {_ARROW} {fp.cold}", fp.gloss))
    lines.append(_axis_row("visibility", "silence/hide/shadow",
                           "+ inverses -- see `dz kit visibility -h`"))
    lines.append("")

    lines.append("Run 'dz kit <verb> --help' for a specific verb.")
    return "\n".join(lines)
