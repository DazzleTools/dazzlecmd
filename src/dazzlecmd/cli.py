"""Main CLI entry point for dazzlecmd.

This module provides the dazzlecmd-specific configuration and the
build_parser/dispatch functions that the AggregatorEngine delegates to.
New aggregator projects should use AggregatorEngine directly rather than
importing from this module.
"""

import os
import sys

from dazzlecmd._version import DISPLAY_VERSION, __version__
from dazzlecmd._constants import RESERVED_COMMANDS  # noqa: F401  (re-exported)
from dazzlecmd.engine import AggregatorEngine
from dazzlecmd_lib.aggregator_config import find_aggregator_root
# The read surface lives in the lib (SD-A): one interrogation function + one
# renderer power every level's card. cli.py keeps the public names below as
# thin delegators (engine wiring + tests import them from dazzlecmd.cli).
from dazzlecmd_lib.interrogation import (  # noqa: F401
    axis_state as _kit_axis_state,
    interrogate as _interrogate,
    render_interrogation as _render_interrogation,
    _print_entity_card,
    _print_axis_rows,
)


# v0.7.44 (4b-T3 + 4d-3): per-language scaffolding ships. The set of
# valid ``--language`` values is now derived from the template directory
# layout under ``packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/`` --
# any directory there (other than ``__*__`` overlay dirs) is a valid
# language. The v0.7.40 ``_SUPPORTED_LANGUAGES_V0740`` guard is gone.


def find_project_root():
    """Find the dazzlecmd project root by navigating from __file__.

    Legacy wrapper -- new code should use AggregatorEngine.find_project_root().
    """
    return AggregatorEngine().find_project_root()


# ---------------------------------------------------------------------------
# The parser builder moved to dazzlecmd/parsers.py (cli.py decomposition R4,
# DWP 2026-06-25__16-14-19). Re-exported so AggregatorEngine.run()'s wiring in
# main() and the test-suite keep importing build_parser from dazzlecmd.cli.
# ---------------------------------------------------------------------------
from dazzlecmd.parsers import (  # noqa: F401,E402
    build_parser,
    _build_categorized_help,
    _register_meta_commands,
)


# Display helpers: canonical implementations live in dazzlecmd_lib.
# (The kit-list renderer itself moved to the lib in the unification DWP,
# 2026-06-11 -- dazzlecmd no longer carries a custom _cmd_kit_list.)
from dazzlecmd_lib.default_meta_commands import (  # noqa: F401
    _wrap_description,
    KIT_NAME_COL,
    MIN_DESC_WIDTH,
    SUMMARY_INDENT,
    TERM_SIZE_FALLBACK,
)



# ---------------------------------------------------------------------------
# Dispatch + read surfaces moved to dispatch.py (R7) and commands/inspect.py
# (R6) -- cli.py decomposition, DWP 2026-06-25__16-14-19 (landed with the FQCN
# arc, SD-FQCN-2 slice 2b). Re-exported for engine wiring + back-compat (the
# suite and one-offs import these from dazzlecmd.cli).
# ---------------------------------------------------------------------------
from dazzlecmd.dispatch import (  # noqa: F401,E402
    _init_verbosity,
    dispatch_meta,
    INSPECT_VERBS,
    verb_plan,
    _dispatch_verb_target,
    _dispatch_bare_verb,
    _VERB_LEVEL_HANDLERS,
    _resolved_kit_name,
    _enable_at_kit,
    _disable_at_kit,
    _attach_at_kit,
    _detach_at_kit,
    dispatch_tool,
    _sugar_flags_hook,
)
from dazzlecmd.commands.inspect import (  # noqa: F401,E402
    _cmd_list,
    render_aggregator_info,
    _info_at_tool,
    _info_at_kit,
    _info_at_aggregator,
    _cmd_info,
    render_kit_info,
    _cmd_version,
    _cmd_tree,
)

# ---------------------------------------------------------------------------
# ADD / MODE / SETUP handlers moved to commands/{add,mode,setup}.py
# (cli.py decomposition R3, DWP 2026-06-25__16-14-19). Re-exported for
# dispatch_meta + back-compat (tests import _cmd_setup et al. from dazzlecmd.cli).
# ---------------------------------------------------------------------------
from dazzlecmd.commands.add import _cmd_add  # noqa: F401,E402
from dazzlecmd.commands.mode import (  # noqa: F401,E402
    _cmd_mode_status,
    _cmd_mode_switch,
    _cmd_mode_restore,
)
from dazzlecmd.commands.meta import (  # noqa: F401,E402
    foreground_level,
    _cmd_meta,
    _cmd_meta_use,
    _cmd_meta_reset,
)
from dazzlecmd.commands.setup import _cmd_setup  # noqa: F401,E402



# ---------------------------------------------------------------------------
# NEW/SCAFFOLD handlers moved to commands/new.py (cli.py decomposition R2,
# DWP 2026-06-25__16-14-19). Re-exported for dispatch_meta + back-compat
# (_cmd_add, tests, and one-offs import several of these from dazzlecmd.cli).
# ---------------------------------------------------------------------------
from dazzlecmd.commands.new import (  # noqa: F401,E402
    _resolve_new_defaults,
    _find_templates_root,
    _available_languages,
    _substitute_placeholders,
    _copy_template_tree,
    _cmd_new_tool,
    _cmd_new_kit,
    _scaffold_starter_tool,
    _with_copy_component,
    _ComponentUnavailable,
    _REPOKIT_COMMON_URL_DEFAULT,
    _REPOKIT_TEMPLATE_URL_DEFAULT,
    _GIT_SUBTREE_TIMEOUT,
    _run_git,
    _with_common,
    _with_template,
    _WITH_COMPONENTS,
    _WITH_ALL,
    _parse_with_spec,
    _apply_with_components,
    _cmd_new_aggregator,
    _layer_extras,
    _register_in_kit,
)



# ---------------------------------------------------------------------------
# Kit-lifecycle handlers moved to commands/kit*.py (cli.py decomposition R1,
# DWP 2026-06-25__16-14-19). Re-exported here so dispatch_meta resolves them by
# bare name and so the test-suite / one-offs can import them from dazzlecmd.cli.
# ---------------------------------------------------------------------------
from dazzlecmd.commands.kit import (  # noqa: F401,E402
    _kit_exists,
    _cmd_kit_enable,
    _cmd_kit_disable,
    _cmd_kit_focus,
    _cmd_kit_reset,
    _cmd_kit_favorite,
    _suggest_favorite_replacement,
    _cmd_kit_favorite_migrate_stale,
    _cmd_kit_unfavorite,
)
from dazzlecmd.commands.kit_visibility import (  # noqa: F401,E402
    _resolve_visibility_target,
    _is_constitutional_entity,
    _cmd_kit_visibility_set,
    _resolve_cascade_slice,
    _apply_visibility_cascade,
    _cmd_kit_visibility_list,
    _cmd_kit_visibility_status,
)
from dazzlecmd.commands.kit_membership import (  # noqa: F401,E402
    _cmd_kit_add,
    _kit_is_submodule,
    _cmd_kit_remove,
    _cmd_kit_detach,
    _materialize_pointer,
    _cmd_kit_attach,
    _print_axis_hint,
    _cmd_kit_management,
)


def main():
    """Main entry point for dazzlecmd CLI.

    As of v0.7.51 (Phase 3.5 T1-M1), aggregator identity + layout +
    policy are declared in ``aggregator.json`` at the project root
    instead of hardcoded constructor kwargs. The shape below is the
    canonical pattern for any dazzlecmd-lib-based aggregator; every
    per-aggregator knob lives in ``aggregator.json``. Runtime callbacks
    (``build_parser`` / ``dispatch_meta`` / ``dispatch_tool``) stay in
    code because they ARE code -- argparse builders and meta-command
    dispatchers can't be expressed declaratively.

    ``find_aggregator_root`` is anchored to THIS package's ``__file__``,
    not cwd (v0.7.52 fix). Anchoring to cwd would make ``dz`` impersonate
    whatever aggregator the user is standing in -- e.g., running ``dz``
    from inside a wtf-windows checkout would load wtf's ``aggregator.json``
    and ``dz`` would become ``wtf``. The entry point's identity is fixed
    by which package it is (``dazzlecmd``), pinned at install time.
    """
    project_root = find_aggregator_root(os.path.dirname(os.path.abspath(__file__)))
    if project_root is None:
        print(
            "Error: could not find aggregator.json. The dazzlecmd package "
            "must be installed alongside its project tree.",
            file=sys.stderr,
        )
        return 1

    engine = AggregatorEngine.from_project(
        project_root,
        version_info=(DISPLAY_VERSION, __version__),
        is_root=True,
        parser_builder=build_parser,
        meta_dispatcher=dispatch_meta,
        tool_dispatcher=dispatch_tool,
    )

    # The sugar intercept bypasses argparse, so pre-path global flags
    # (`dz -v .note`) are handed back through this hook to initialize
    # log_lib output exactly as dispatch_meta's _init_verbosity does
    # (v2 contract AC-6).
    engine.sugar_flags_hook = _sugar_flags_hook

    # The level property's validator joins the shared write path, so the
    # sugar (`dz .level kit`) and the verbs (`dz level kit`) validate
    # identically (v2 contract C-7 / R1.7).
    from dazzlecmd.commands.meta import register_level_property
    register_level_property(engine)
    from dazzlecmd.commands.inspect import _graft_app_verbs
    engine.tree_extensions.append(_graft_app_verbs)
    from dazzlecmd.tree_plane import graft_instance_plane
    engine.tree_extensions.append(graft_instance_plane)
    from dazzlecmd.tree_plane import derived_instance_read
    engine.derived_reads.append(derived_instance_read)

    return engine.run()


