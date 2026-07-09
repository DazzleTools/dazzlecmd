"""The app's tree-plane surface -- THE CONSUMER LIFT (C2 DWP Part 2,
2026-07-08) moved the generic instance-plane machinery into
dazzlecmd-lib (dazzlecmd_lib.instance_plane); every aggregator now
gets it as an engine default. This module keeps the APP-ONLY parts
(the generated-command routes, the D8 classifier, configure_tree's
app-verb graft) and re-exports the lifted names for back-compat.
"""

from dazzlecmd_lib.instance_plane import (  # noqa: F401 -- re-exports
    _derive_level,
    alias_registry,
    counterpart_keys,
    counterpart_read,
    derived_config_read,
    derived_instance_read,
    graft_config_ring,
    graft_instance_plane,
    graft_kit_frame_projections,
    graft_virtual_kit_rung,
    graft_vk_projections,
    instance_card_sections,
    instance_level_line,
    node_hint,
    register_aliases_on_tree,
    register_engine_defaults,
)


GENERATED_ROUTES = {
    # exposed node -> (command name, help, the _meta route it reuses)
    "management": ("management",
                   "Kit lifecycle state -- the composed axis quick-read",
                   "kit_management"),
}


def exposed_generated_commands(engine):
    """D2: `expose` is a PROPERTY -- the CLI surface is the exposed
    projection of the graph. A node opts in via the store
    (`dz :.meta:verb:management.expose=true`); flipping it adds/removes
    the generated command from `dz -h` LIVE (the B-8 AC)."""
    out = []
    try:
        store = engine.property_store
        for node_name, (cmd_name, help_text, meta) in GENERATED_ROUTES.items():
            key = f"{engine.command}:.meta:verb:{node_name}.expose"
            if store.get(key) is True:
                out.append((cmd_name, help_text, meta))
    except Exception:
        pass
    return out


def classify_verb(engine, name):
    """D8 -- the sufficiency classifier: HANDLER-backed verbs earn a
    generated command; PROPERTY-backed verbs dissolve into assignment
    (+ optional alias). The pinned demotion exhibits: use, reset."""
    PROPERTY_BACKED = {"use": "dz level=<rung> (the assignment surface)",
                       "reset": "dz prop delete .level (+ the default)",
                       "version": "dz.version (a derived property read)"}
    if name in PROPERTY_BACKED:
        return ("property-backed", PROPERTY_BACKED[name])
    return ("handler-backed", None)


def configure_tree(engine):
    """ONE tree-config source for the APP (cli.main AND the audit):
    the lib defaults are already registered at engine.__init__ (the
    consumer lift); this adds the app-only pieces -- the argparse verb
    inventory graft, ordered FIRST so verb helps attach before the
    instance plane runs."""
    register_engine_defaults(engine)  # idempotent (exotic test engines)
    from dazzlecmd.commands.inspect import _graft_app_verbs
    if _graft_app_verbs not in engine.tree_extensions:
        engine.tree_extensions.insert(0, _graft_app_verbs)
