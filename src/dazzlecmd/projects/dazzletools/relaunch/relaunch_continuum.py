"""The two named-rung axes of ``dz relaunch``, built on dazzle-lib's Continuum.

- ACTION: what ``claim`` does with the member -- print (show what to do),
  open (run it in this tab), tabs (spawn tabs; reserved, not built).
- TRUST: how a runnable member is checked before ``claim -o`` -- none,
  hashed (v1), signed (later).

Levels are *selected* with ``rank`` / ``level_at``, never gated with
``passes`` (oracle note, section 4). Lift-ready: no relaunch imports.
"""

from __future__ import annotations

from dazzle_lib.continuum import Continuum

ACTION = Continuum(name="relaunch-action", ranks={"print": 0, "open": 1, "tabs": 2},
                   invariant="print")
TRUST = Continuum(name="relaunch-trust", ranks={"none": 0, "hashed": 1, "signed": 2},
                  invariant="hashed")

BUILT_ACTION_LEVELS = ("print", "open")


class LevelNotBuilt(Exception):
    pass


def resolve_action(*, open_flag: bool = False, tabs_flag: bool = False,
                   console: bool = True) -> str:
    """The action level for one claim: requested, then capped.

    ``tabs`` is reserved and refused; without a console the level is capped
    to ``print`` so pipes and agents never start programs.
    """
    if tabs_flag:
        raise LevelNotBuilt("claim --tabs is designed but not built yet -- open the tabs yourself "
                            "and run `dz relaunch <set> claim -o` in each")
    wanted = "open" if open_flag else "print"
    if not console and ACTION.rank(wanted) > ACTION.rank("print"):
        return "print"
    return wanted
