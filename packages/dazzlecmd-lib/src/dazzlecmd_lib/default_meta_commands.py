"""Default meta-commands for dazzlecmd-pattern aggregators.

Exposes the built-in ``list``, ``info``, ``kit``, ``version``, ``tree``,
and ``setup`` commands as parser factories + handlers + render functions.
``AggregatorEngine`` auto-registers them on construction via
``register_all()``; aggregators can opt out (``include_default_meta_commands=False``),
unregister specific ones (``engine.meta_registry.unregister("tree")``),
or override them (``engine.meta_registry.override("info", handler=...)``).

Public surface for aggregator authors:

- ``render_*(args, projects, ...) -> int``: the printing logic for each
  command, decoupled from engine context. Import these to **compose** —
  call ``render_info()`` from your override, then append domain fields.

- ``*_parser_factory(subparsers)``: argparse subparser setup. Import
  these to reuse the argument shape while replacing the handler.

- ``*_handler(args, engine, projects, kits, project_root) -> int``: the
  handlers the registry calls. These are thin wrappers around ``render_*``
  that unpack engine context. Override at the handler level when your
  domain logic needs ``engine`` or ``project_root``.

- ``register_all(registry)``: bulk-register every default. Invoked by the
  engine at construction time.

- ``register_selected(registry, include=[...])``: opt-in helper — register
  only the defaults you want.

These implementations are intentionally **minimal**. They cover the
common-case output for a generic aggregator. Aggregators with rich
domain fields (diagnostic badges, Docker-specific rendering, collision
markers, terminal-width wrapping, etc.) should override the handler and
compose with the stock render function OR replace it outright.
"""

from __future__ import annotations

import json as _json
import os as _os
import shutil as _shutil
import sys as _sys
from typing import Iterable, Optional


def _wrap_description(text, width):
    """Wrap a description string to fit within a given width.

    Returns a list of lines. Wraps at word boundaries when possible,
    falls back to hard break with hyphen when a single word exceeds
    the width.
    """
    if not text or width < 10:
        return [text or ""]
    if len(text) <= width:
        return [text]

    lines = []
    remaining = text
    while remaining:
        if len(remaining) <= width:
            lines.append(remaining)
            break

        # Find the last space within the width
        break_at = remaining.rfind(" ", 0, width)
        if break_at > 0:
            lines.append(remaining[:break_at])
            remaining = remaining[break_at + 1:]
        else:
            # No space found -- hard break with hyphen
            lines.append(remaining[:width - 1] + "-")
            remaining = remaining[width - 1:]

    return lines


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def list_parser_factory(subparsers):
    """Register the ``list`` subparser.

    Flags:
        --namespace / -n: filter by namespace
        --kit / -k: filter by kit (canonical OR virtual)
        --tag / -t: filter by taxonomy.tags
        --platform / -p: filter by platform
        --show: content selector (default/canonical/alias/all)
    """
    p = subparsers.add_parser("list", help="List available tools")
    p.add_argument("--namespace", "-n", help="Filter by namespace")
    p.add_argument("--kit", "-k", help="Filter by kit (canonical OR virtual)")
    p.add_argument("--tag", "-t", help="Filter by tag")
    p.add_argument("--platform", "-p", help="Filter by platform")
    p.add_argument(
        "--show",
        choices=["default", "canonical", "alias", "all"],
        default=None,
        help=(
            "Content selector. 'default' (alias-preferred): virtual-kit "
            "aliases replace their canonical targets. 'canonical': "
            "canonicals only (script-stable legacy view). 'alias': aliases "
            "only. 'all': both canonicals and aliases. Falls back to "
            "config key 'list_view' then to 'default' if unset."
        ),
    )
    p.set_defaults(_meta="list")


def render_list(args, projects, engine=None) -> int:
    """List available tools with --show enum + sectioned layout.

    Display modes (controlled by ``--show`` flag, then ``list_view``
    config key, then hardcoded ``"default"``):

    - ``default`` (alias-preferred): virtual-kit aliases replace their
      canonical targets. Canonicals without aliases still shown.
    - ``canonical``: canonicals only (script-stable legacy view).
    - ``alias``: aliases only (virtual-kit entries only).
    - ``all``: both canonicals and aliases shown separately;
      canonicals that have aliases are marked ``[+]``.

    Layout (Phase 4e v0.7.28 — Option O):

    - Tools are grouped into sections by kit. Section header shows the
      kit path; virtual-kit headers include a ``(virtual kit '<name>')``
      annotation.
    - Two columns within a section: name + description. The kit info
      lives in the header — no per-row Kit column inside sections.
    - When only one section would render, fall back to the v0.7.27 flat
      table layout (still has the Kit column).
    - One blank line between sections.

    Short-name collisions are marked ``[*]``; canonicals with aliases
    (in ``--show all``) are marked ``[+]``. Footer note explains both
    when present.

    ``--kit`` filter accepts either a canonical kit name or a virtual
    kit name. Virtual-kit filter surfaces the kit's aliases.

    ``engine`` is optional for backward compat: when ``None``, no
    sectioning, no virtual kits, no collision markers — plain flat
    output (filtered by namespace/kit/tag/platform). Pass ``engine``
    to enable the full sectioned/alias-aware behavior.
    """
    # Backward-compat path: engine=None → plain flat output (no sections,
    # no virtual kits, no collision markers, no --show modes).
    if engine is None:
        filtered = list(projects)
        ns = getattr(args, "namespace", None)
        plat = getattr(args, "platform", None)
        tag = getattr(args, "tag", None)
        kit = getattr(args, "kit", None)
        if ns:
            filtered = [p for p in filtered if p.get("namespace") == ns]
        if plat:
            filtered = [
                p for p in filtered
                if p.get("platform", "cross-platform") == plat
            ]
        if tag:
            filtered = [
                p for p in filtered
                if tag in p.get("taxonomy", {}).get("tags", [])
            ]
        if kit:
            filtered = [p for p in filtered if p.get("_kit_import_name") == kit]
        if not filtered:
            print("No tools found.")
            return 0
        name_width = max(len(p["name"]) for p in filtered)
        name_width = max(name_width, len("Name"))
        kit_col_width = max(
            (len(p.get("_kit_import_name", "")) for p in filtered),
            default=0,
        )
        kit_col_width = max(kit_col_width, len("Kit"))
        header = f"  {'Name':<{name_width}}  {'Kit':<{kit_col_width}}  Description"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for project in filtered:
            name = project["name"]
            kit_name = project.get("_kit_import_name", "")
            desc = project.get("description", "")
            if len(desc) > 60:
                desc = desc[:57] + "..."
            print(f"  {name:<{name_width}}  {kit_name:<{kit_col_width}}  {desc}")
        print(f"\n  {len(filtered)} tool(s) found")
        return 0

    # Determine effective --show mode
    show_mode = getattr(args, "show", None)
    if show_mode is None and engine is not None:
        show_mode = engine._get_user_config().get("list_view")
    if show_mode not in ("default", "canonical", "alias", "all"):
        show_mode = "default"

    # show_empty_virtual_kits config: render virtual-kit sections even
    # when no aliases are active (e.g., target canonical kit is disabled)?
    show_empty_virtuals = True
    if engine is not None:
        cfg_val = engine._get_user_config().get("show_empty_virtual_kits")
        if isinstance(cfg_val, bool):
            show_empty_virtuals = cfg_val

    entries = build_list_entries(
        projects, engine, show_mode, getattr(args, "kit", None)
    )

    if args.namespace:
        entries = [e for e in entries if e["namespace"] == args.namespace]
    if args.platform:
        entries = [e for e in entries if e["platform"] == args.platform]
    if args.tag:
        entries = [e for e in entries if args.tag in e["tags"]]

    # Group entries by section_key
    sections = {}  # section_key -> {kind, vk_name, entries[]}
    for e in entries:
        sk = e["section_key"]
        if sk not in sections:
            sections[sk] = {
                "kind": e["section_kind"],
                "vk_name": e.get("section_vk_name"),
                "entries": [],
            }
        sections[sk]["entries"].append(e)

    # Optionally inject empty virtual-kit sections (no active aliases).
    # Useful for users who want awareness that a virtual kit exists even
    # when its targets are disabled. See `show_empty_virtual_kits` config.
    if show_empty_virtuals and show_mode in ("alias", "all", "default") and engine is not None:
        kit_filter = getattr(args, "kit", None)
        for k in getattr(engine, "kits", []):
            if not k.get("virtual"):
                continue
            if not k.get("_kit_active", True):
                continue
            vk_name = k.get("_kit_name") or k.get("name")
            if not vk_name:
                continue
            if kit_filter is not None and kit_filter != vk_name:
                continue
            # Compute the section key this virtual kit WOULD have.
            tools_list = k.get("tools") or []
            if ":" in vk_name:
                section_key = vk_name
                vk_local = vk_name.rsplit(":", 1)[-1]
            elif tools_list:
                first_tool = tools_list[0]
                canonical_kit_path = (
                    first_tool.rsplit(":", 1)[0] if ":" in first_tool else ""
                )
                section_key = (
                    f"{canonical_kit_path}:{vk_name}"
                    if canonical_kit_path else vk_name
                )
                vk_local = vk_name
            else:
                section_key = vk_name
                vk_local = vk_name
            if section_key not in sections:
                sections[section_key] = {
                    "kind": "virtual",
                    "vk_name": vk_local,
                    "entries": [],
                }

    if not sections:
        print("No tools found.")
        return 0

    # Sort sections so virtual kits sit immediately after their canonical
    # parent. A virtual kit conceptually EXTENDS the canonical kit it
    # aliases from -- visually grouping them together makes the
    # relationship explicit and prevents the user from having to scan
    # the whole list to find a virtual kit's parent.
    #
    # Sort key tuple: (parent_path, kind_rank, full_key)
    # - parent_path is the canonical-kit prefix (everything before the
    #   last segment for virtuals; the section key itself for canonicals)
    # - kind_rank is 0 for canonicals, 1 for virtuals (canonical first
    #   when sharing the same parent)
    # - full_key for stable alphabetical tiebreak among siblings
    def _section_sort_key(sk):
        section = sections[sk]
        if section["kind"] == "virtual":
            parent = sk.rsplit(":", 1)[0] if ":" in sk else sk
            return (parent, 1, sk)
        return (sk, 0, sk)

    section_keys = sorted(sections.keys(), key=_section_sort_key)

    # Sort entries within each section alphabetically by name
    for sk in section_keys:
        sections[sk]["entries"].sort(key=lambda e: e["name"])

    # Decide layout: single-section -> flat (v0.7.27 style); else sectioned.
    use_flat = len(section_keys) == 1

    # Collision + alias markers
    colliding = set()
    if engine is not None and hasattr(engine, "fqcn_index"):
        for short, fqcns in engine.fqcn_index.short_index.items():
            if len(fqcns) > 1:
                colliding.add(short)

    def _label(entry):
        markers = []
        if entry["name"] in colliding:
            markers.append("*")
        if show_mode == "all" and entry.get("has_aliases"):
            markers.append("+")
        if not markers:
            return entry["name"]
        # Use [*][+] form (each marker bracketed) for clarity
        suffix = "".join(f"[{m}]" for m in markers)
        return f"{entry['name']} {suffix}"

    term_width = _shutil.get_terminal_size((80, 24)).columns

    if use_flat:
        # Single-section flat fallback (v0.7.27 layout).
        flat_entries = sections[section_keys[0]]["entries"]
        if not flat_entries:
            print("No tools found.")
            return 0
        name_width = max(len(_label(e)) for e in flat_entries)
        name_width = max(name_width, len("Name"))
        kit_width = max(len(e["kit"]) for e in flat_entries)
        kit_width = max(kit_width, len("Kit"))

        header = f"  {'Name':<{name_width}}  {'Kit':<{kit_width}}  Description"
        print(header)
        print("  " + "-" * (len(header) - 2))

        desc_col = 2 + name_width + 2 + kit_width + 2
        desc_max = term_width - desc_col
        for entry in flat_entries:
            label = _label(entry)
            kit = entry["kit"]
            desc = entry["description"]
            wrapped = _wrap_description(desc, desc_max)
            print(f"  {label:<{name_width}}  {kit:<{kit_width}}  {wrapped[0]}")
            indent = " " * desc_col
            for line in wrapped[1:]:
                print(f"{indent}{line}")
    else:
        # Sectioned layout.
        for i, sk in enumerate(section_keys):
            if i > 0:
                print()  # one blank line between sections
            section = sections[sk]
            if section["kind"] == "virtual":
                annotation = f"  (virtual kit '{section['vk_name']}')"
            else:
                annotation = ""
            print(f"{sk}:{annotation}")

            section_entries = section["entries"]
            if not section_entries:
                print("    (no active aliases)")
                continue

            # Per-section column widths (name only; description fills rest)
            name_width = max(len(_label(e)) for e in section_entries)
            indent = "  "  # 2-space indent under each section header
            desc_col = len(indent) + name_width + 2
            desc_max = term_width - desc_col
            for entry in section_entries:
                label = _label(entry)
                desc = entry["description"]
                wrapped = _wrap_description(desc, desc_max)
                print(f"{indent}{label:<{name_width}}  {wrapped[0]}")
                wrap_indent = " " * desc_col
                for line in wrapped[1:]:
                    print(f"{wrap_indent}{line}")

    # Footer — markers explanation
    has_collision = bool(colliding)
    has_alias_marker = show_mode == "all" and any(
        e.get("has_aliases") for e in entries
    )
    if has_collision or has_alias_marker:
        print()
        if has_collision:
            print(
                "  [*] short-name collision -- use 'dz info <fqcn>' or "
                "'dz kit favorite' to disambiguate."
            )
        if has_alias_marker:
            print(
                "  [+] canonical has aliases under one or more virtual kits "
                "-- see virtual-kit sections below."
            )

    # Footer — counts
    canonical_count = sum(1 for e in entries if e["entry_type"] == "canonical")
    alias_count = sum(1 for e in entries if e["entry_type"] == "alias")
    print()
    if show_mode == "canonical" or alias_count == 0:
        print(f"  {canonical_count} tool(s) found")
    elif show_mode == "alias":
        print(f"  {alias_count} alias(es) found")
    elif show_mode == "all":
        print(
            f"  {canonical_count} tool(s) + {alias_count} alias(es) "
            f"({len(entries)} rows)"
        )
    else:
        # default — alias-preferred: aliases shown INSTEAD OF their
        # canonical targets; total is the unique invocation surface.
        print(
            f"  {len(entries)} tool(s) "
            f"({canonical_count} canonical + {alias_count} virtual-kit alias(es)). "
            f"Use --show all to see both; --show canonical for legacy view."
        )
    return 0


def list_handler(args, engine, projects, kits, project_root) -> int:
    """Default handler for ``list``. Passes engine to render_list so
    aggregators with virtual kits / FQCN indexes get the full sectioned
    output. Aggregators that don't have an engine context can call
    ``render_list(args, projects)`` directly for plain flat output."""
    return render_list(args, projects, engine=engine)


def build_list_entries(projects, engine, show_mode, kit_filter):
    """Construct display entries for ``list`` based on ``show_mode``.

    PUBLIC API: aggregators that want to render the list with their own
    display layer (custom colors, custom column widths, custom markers,
    JSON output, etc.) can call this to get the data, then iterate
    entries themselves.

    Each entry is a dict with stable shape (additive changes only):

    - ``name`` (str): short name as it appears in dispatch
    - ``kit`` (str): kit-import-name (or virtual-kit name for aliases)
    - ``description`` (str): tool's description from manifest
    - ``entry_type`` (str): "canonical" or "alias"
    - ``namespace`` (str | None): manifest namespace
    - ``platform`` (str): manifest platform (default "cross-platform")
    - ``tags`` (list[str]): manifest taxonomy.tags
    - ``_fqcn`` (str): FQCN of THIS entry (alias FQCN for aliases)
    - ``_canonical_fqcn`` (str): canonical FQCN this entry resolves to
    - ``section_key`` (str): grouping key for sectioned rendering
    - ``section_kind`` (str): "canonical" or "virtual"
    - ``section_vk_name`` (str, alias-only): virtual-kit's local name
    - ``has_aliases`` (bool, canonical-only): True when one or more
      aliases under any virtual kit point to this canonical FQCN. Used
      to render the ``[+]`` marker in ``--show all``.

    Section key conventions (Phase 4e v0.7.28):

    - Canonical entry: ``section_key = <kit_path>``, where kit_path is
      everything in the canonical FQCN before the tool's last segment.
      ``core:rn`` -> ``core``; ``wtf:core:locked`` -> ``wtf:core``.
    - Alias entry: ``section_key = <canonical_kit_path>:<vk_name>`` for
      root-level virtual kits, or ``<vk_name>`` if the virtual kit's
      name itself contains ``:`` (cross-aggregator rewritten — already
      carries its hierarchy).
    """
    entries = []

    # Identify virtual vs canonical kits up front (if engine available).
    # virtual_kit_metadata: vk_name -> kit dict (for header annotations etc.)
    virtual_kit_names = set()
    virtual_kit_metadata = {}
    if engine is not None:
        for k in getattr(engine, "kits", []):
            if k.get("virtual"):
                vk_name = k.get("_kit_name") or k.get("name")
                if vk_name:
                    virtual_kit_names.add(vk_name)
                    virtual_kit_metadata[vk_name] = k

    kit_filter_is_virtual = kit_filter is not None and kit_filter in virtual_kit_names

    # Track which canonical FQCNs have aliases (used for [+] marker).
    canonicals_with_aliases = set()
    if engine is not None and hasattr(engine, "fqcn_index"):
        for canonical_fqcn in engine.fqcn_index.alias_index.values():
            canonicals_with_aliases.add(canonical_fqcn)

    # --- Build canonical entries ---
    # Skip canonical iteration entirely when the kit filter is a virtual
    # kit name — that filter asks "what's in the virtual kit" which is
    # exclusively aliases, not canonicals.
    if show_mode in ("canonical", "all", "default") and not kit_filter_is_virtual:
        for p in projects:
            kit_name = p.get("_kit_import_name", "")
            if kit_filter is not None:
                if kit_name != kit_filter:
                    continue
            fqcn = p.get("_fqcn", "")
            # Section key: kit_path = FQCN minus the last segment
            if ":" in fqcn:
                section_key = fqcn.rsplit(":", 1)[0]
            else:
                section_key = kit_name or "(unknown)"
            entries.append({
                "name": p["name"],
                "kit": kit_name,
                "description": p.get("description", ""),
                "entry_type": "canonical",
                "namespace": p.get("namespace"),
                "platform": p.get("platform", "cross-platform"),
                "tags": p.get("taxonomy", {}).get("tags", []),
                "_fqcn": fqcn,
                "_canonical_fqcn": fqcn,
                "section_key": section_key,
                "section_kind": "canonical",
                "has_aliases": fqcn in canonicals_with_aliases,
            })

    # --- Build alias entries from virtual kits ---
    if show_mode in ("alias", "all", "default"):
        if engine is None or not hasattr(engine, "fqcn_index"):
            pass  # no engine, no aliases
        else:
            # Map canonical FQCN -> project, for description lookup
            canonical_by_fqcn = {
                p.get("_fqcn"): p for p in projects if p.get("_fqcn")
            }
            # Iterate every alias and build its entry
            for alias_fqcn, canonical_fqcn in engine.fqcn_index.alias_index.items():
                vk_name, _, alias_short = alias_fqcn.rpartition(":")
                if kit_filter is not None and kit_filter_is_virtual:
                    if vk_name != kit_filter:
                        continue
                elif kit_filter is not None and not kit_filter_is_virtual:
                    # Filter is a canonical kit -- show aliases whose
                    # TARGET is in that kit (only useful in --show all)
                    target_project = canonical_by_fqcn.get(canonical_fqcn)
                    if target_project is None:
                        continue
                    if target_project.get("_kit_import_name") != kit_filter:
                        continue

                target_project = canonical_by_fqcn.get(canonical_fqcn)
                if target_project is None:
                    continue  # dangling — should have been caught at load

                # Section key for the alias.
                # Cross-aggregator case: if vk_name already contains ':'
                # (e.g., 'wtf:claude' from Option A rewriting), use vk_name
                # as-is — it already encodes the hierarchy.
                # Root case: build canonical_kit_path : vk_name.
                if ":" in vk_name:
                    section_key = vk_name
                    vk_local_name = vk_name.rsplit(":", 1)[-1]
                else:
                    if ":" in canonical_fqcn:
                        canonical_kit_path = canonical_fqcn.rsplit(":", 1)[0]
                    else:
                        canonical_kit_path = target_project.get("_kit_import_name", "")
                    section_key = (
                        f"{canonical_kit_path}:{vk_name}"
                        if canonical_kit_path else vk_name
                    )
                    vk_local_name = vk_name

                entries.append({
                    "name": alias_short,
                    "kit": vk_name,  # legacy column for flat fallback
                    "description": target_project.get("description", ""),
                    "entry_type": "alias",
                    "namespace": target_project.get("namespace"),
                    "platform": target_project.get("platform", "cross-platform"),
                    "tags": target_project.get("taxonomy", {}).get("tags", []),
                    "_fqcn": alias_fqcn,
                    "_canonical_fqcn": canonical_fqcn,
                    "section_key": section_key,
                    "section_kind": "virtual",
                    "section_vk_name": vk_local_name,
                    "has_aliases": False,  # aliases don't have aliases
                })

    # --- Default mode: alias-preferred. Hide canonicals that have aliases. ---
    if show_mode == "default":
        aliased_canonicals = {
            e["_canonical_fqcn"] for e in entries if e["entry_type"] == "alias"
        }
        entries = [
            e for e in entries
            if e["entry_type"] == "alias" or e["_fqcn"] not in aliased_canonicals
        ]

    # Sort: alphabetical by name (within sections, the renderer re-sorts).
    entries.sort(key=lambda e: e["name"])
    return entries


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


def info_parser_factory(subparsers):
    """Register the ``info`` subparser.

    Flags:
        tool: tool name or FQCN to inspect
        --raw: show the manifest as declared, without conditional-dispatch
            resolution.
        --platform SPEC: preview runtime resolution for a specific
            platform (e.g. ``linux``, ``linux.ubuntu``, ``windows``).
    """
    p = subparsers.add_parser("info", help="Show detailed info about a tool")
    p.add_argument("tool", help="Tool name or FQCN to inspect")
    p.add_argument(
        "--raw",
        action="store_true",
        help="Show the manifest as declared, without conditional-dispatch resolution.",
    )
    p.add_argument(
        "--platform",
        metavar="SPEC",
        help=(
            "Preview runtime resolution for a specific platform "
            "(e.g. 'linux', 'linux.ubuntu', 'windows'). Does not check "
            "PATH; uses declared platform block."
        ),
    )
    p.set_defaults(_meta="info")


# ---------------------------------------------------------------------------
# Runtime display helpers for `info`
#
# Ported verbatim from dazzlecmd cli.py:889-1116 in v0.7.32 (4b-T9 info-parity
# port). Provides the runtime-resolution display that consumers (amdead,
# wtf-windows, sysdiagnose, future personal aggregators) need when their
# users run ``aggregator info <tool>`` against a tool with conditional
# runtime dispatch (per-platform blocks, prefer ladders, ``{{var}}``
# template references, Docker fields, etc.).
# ---------------------------------------------------------------------------


_RUNTIME_DISPATCH_FIELDS = [
    # (manifest_key, display_label, render_fn)
    ("script_path", None, None),  # handled specially (label depends on type)
    ("dev_command", "Dev command", None),
    ("interpreter", "Interpreter", None),
    ("interpreter_args", "Interp args", lambda v: " ".join(v)),
    ("npm_script", "NPM script", None),
    ("npx", "Npx", None),
    ("shell", "Shell", None),
    ("shell_args", "Shell args", lambda v: " ".join(v)),
    ("shell_env", "Shell env", lambda v: (
        v.get("script", "") +
        ((" " + " ".join(v.get("args", []))) if v.get("args") else "")
    )),
]


def _print_runtime_dispatch_fields(runtime):
    """Print the concrete dispatch fields (script_path, interpreter, etc.)."""
    runtime_type = runtime.get("type", "python")
    if runtime.get("script_path"):
        label = "Binary" if runtime_type == "binary" else "Script"
        print(f"{label + ':':13}{runtime['script_path']}")
    for key, label, render in _RUNTIME_DISPATCH_FIELDS:
        if key == "script_path":
            continue
        value = runtime.get(key)
        if not value:
            continue
        if render is not None:
            value = render(value)
        print(f"{label + ':':13}{value}")
    interactive = runtime.get("interactive")
    if interactive:
        label = "exec (hand-off)" if interactive == "exec" else "keep open"
        print(f"Interactive: {label}")

    # Docker-specific fields (Phase 4c.4, v0.7.21). Rendered only when the
    # runtime type is "docker" AND the field is declared, so non-docker tools
    # never see a spurious "Image: None" line.
    if runtime_type == "docker":
        if runtime.get("image"):
            print(f"{'Image:':13}{runtime['image']}")
        volumes = runtime.get("volumes") or []
        if volumes:
            print(f"{'Volumes:':13}{len(volumes)} mount(s)")
            for i, vol in enumerate(volumes):
                if isinstance(vol, dict):
                    host = vol.get("host", "?")
                    container = vol.get("container", "?")
                    mode = vol.get("mode", "")
                    mode_str = f" ({mode})" if mode else ""
                    print(f"             [{i}] {host} -> {container}{mode_str}")
                else:
                    print(f"             [{i}] <malformed: {type(vol).__name__}>")
        env = runtime.get("env") or {}
        if env:
            print(f"{'Env:':13}{len(env)} var(s)")
            for k, v in env.items():
                print(f"             {k}={v}")
        passthrough = runtime.get("env_passthrough") or []
        if passthrough:
            # Values never shown -- only names. Security.
            print(f"Env passthru: {', '.join(passthrough)}")
        docker_args = runtime.get("docker_args") or []
        if docker_args:
            print(f"{'Docker args:':13}{' '.join(docker_args)}")
        inner = runtime.get("inner_runtime")
        if inner and isinstance(inner, dict):
            inner_type = inner.get("type", "?")
            inner_script = inner.get("script_path") or inner.get("module") or ""
            inner_interp = inner.get("interpreter") or ""
            bits = [f"type={inner_type}"]
            if inner_interp:
                bits.append(f"interpreter={inner_interp}")
            if inner_script:
                bits.append(f"script={inner_script}")
            print(f"Inner runtime: (informational) {', '.join(bits)}")


def _print_runtime_resolved(project):
    """Default view: show the runtime resolved for the current host."""
    from dazzlecmd_lib.registry import resolve_runtime, NoRuntimeResolutionError
    from dazzlecmd_lib.platform_detect import get_platform_info
    from dazzlecmd_lib.templates import has_template_refs

    raw_runtime = project.get("runtime", {})
    # BUG-3 fix: also trigger resolution when the manifest contains any
    # `{{var}}` references -- catching unresolved vars at inspection time
    # rather than silently passing through. Includes manifest-top _vars
    # declarations because those make a var-reference-only manifest
    # "conditional" on those vars being defined.
    has_conditional = (
        "platforms" in raw_runtime
        or "prefer" in raw_runtime
        or has_template_refs(raw_runtime)
        or bool(project.get("_vars"))
    )

    if not has_conditional:
        # No conditional dispatch; plain print of the raw runtime.
        runtime_type = raw_runtime.get("type", "python")
        print(f"Runtime:     {runtime_type}")
        _print_runtime_dispatch_fields(raw_runtime)
        return

    pi = get_platform_info()
    try:
        resolved = resolve_runtime(project)
    except NoRuntimeResolutionError as exc:
        print(f"Runtime:     <unresolved for this host>")
        print()
        for line in str(exc).splitlines():
            print(f"  {line}")
        return
    except Exception as exc:  # UnsupportedSchemaVersionError, UnresolvedTemplateVariableError, TemplateRecursionError etc.
        print(f"Runtime:     <resolution error>")
        print()
        for line in str(exc).splitlines():
            print(f"  {line}")
        return

    runtime = resolved.get("runtime", {})
    runtime_type = runtime.get("type", "python")
    platform_tag = pi.os + (f".{pi.subtype}" if pi.subtype else "")
    print(f"Runtime:     {runtime_type}  (resolved for {platform_tag})")
    _print_runtime_dispatch_fields(runtime)
    print(f"             (manifest declares conditional dispatch; use --raw to see the full declaration)")


def _print_runtime_raw(project):
    """--raw view: show the manifest as declared, no resolution."""
    runtime = project.get("runtime", {})
    runtime_type = runtime.get("type", "python")
    print(f"Runtime:     {runtime_type}  (raw, unresolved)")
    _print_runtime_dispatch_fields(runtime)

    # BUG-2 fix: surface manifest-top _vars AND runtime-block _vars so authors
    # debugging {{...}} references can see what's declared at each scope level.
    manifest_vars = project.get("_vars")
    if manifest_vars and isinstance(manifest_vars, dict):
        print(f"_vars (manifest-top):")
        for k, v in manifest_vars.items():
            print(f"  {k} = {v!r}")

    runtime_vars = runtime.get("_vars")
    if runtime_vars and isinstance(runtime_vars, dict):
        print(f"_vars (runtime block):")
        for k, v in runtime_vars.items():
            print(f"  {k} = {v!r}")

    platforms = runtime.get("platforms")
    if platforms and isinstance(platforms, dict):
        print(f"Platforms:   {', '.join(sorted(platforms.keys()))}")
        # BUG-2 fix: show per-platform overrides so authors see their
        # unresolved {{...}} references and platform-specific _vars.
        for os_key in sorted(platforms.keys()):
            os_block = platforms[os_key]
            if not isinstance(os_block, (dict, str)):
                continue
            if isinstance(os_block, str):
                print(f"  {os_key}: {os_block}  (flat-string shorthand)")
                continue
            # Nested dict: show top-level fields + subtype names
            top_fields = {k: v for k, v in os_block.items() if not isinstance(v, dict)}
            subtypes = [k for k, v in os_block.items() if isinstance(v, dict) and not k.startswith("_")]
            pv = os_block.get("_vars")
            if pv:
                print(f"  {os_key}._vars: {pv}")
            for k, v in top_fields.items():
                if k.startswith("_"):
                    continue
                print(f"  {os_key}.{k}: {v!r}")
            if subtypes:
                print(f"  {os_key} subtypes: {', '.join(sorted(subtypes))}")

    prefer = runtime.get("prefer")
    if prefer and isinstance(prefer, list):
        print(f"Prefer:      {len(prefer)} entries (in order)")
        for i, entry in enumerate(prefer):
            if not isinstance(entry, dict):
                print(f"  [{i}] <malformed: {type(entry).__name__}>")
                continue
            bits = []
            for k in ("interpreter", "script_path", "npx", "npm_script", "binary"):
                if k in entry:
                    bits.append(f"{k}={entry[k]}")
            if entry.get("detect_when"):
                bits.append("detect_when=<set>")
            print(f"  [{i}] {', '.join(bits) if bits else '<empty>'}")


def _print_runtime_platform_preview(project, spec):
    """--platform SPEC view: preview platform resolution without PATH checks."""
    from dazzlecmd_lib.platform_detect import PlatformInfo
    from dazzlecmd_lib.platform_resolve import resolve_platform_block

    parts = spec.split(".", 1)
    os_name = parts[0]
    subtype = parts[1] if len(parts) > 1 else None
    pi = PlatformInfo(
        os=os_name, subtype=subtype, arch="preview", is_wsl=False, version=None
    )

    raw_runtime = project.get("runtime", {})
    base_runtime = {k: v for k, v in raw_runtime.items() if k != "platforms"}
    platforms = raw_runtime.get("platforms")
    effective = resolve_platform_block(base_runtime, platforms, pi)

    runtime_type = effective.get("type", "python")
    platform_tag = os_name + (f".{subtype}" if subtype else "")
    print(f"Runtime:     {runtime_type}  (preview for {platform_tag})")
    _print_runtime_dispatch_fields(effective)

    prefer = effective.get("prefer")
    if prefer and isinstance(prefer, list):
        print(f"Prefer:      {len(prefer)} entries (preconditions not evaluated in preview)")
        for i, entry in enumerate(prefer):
            if not isinstance(entry, dict):
                print(f"  [{i}] <malformed: {type(entry).__name__}>")
                continue
            bits = []
            for k in ("interpreter", "script_path", "npx", "npm_script", "binary"):
                if k in entry:
                    bits.append(f"{k}={entry[k]}")
            if entry.get("detect_when"):
                bits.append("detect_when=<set>")
            print(f"  [{i}] {', '.join(bits) if bits else '<empty>'}")


def render_info(args, projects, engine) -> int:
    """Print basic info for a tool identified by name or FQCN.

    Lookups route through ``engine.find_project`` so virtual-kit aliases
    resolve transparently and rule 7c (alias shorts in short_index) is
    honored. Alias provenance (if any) is printed as a banner line
    before the tool's metadata.

    Aggregators with domain-specific fields (diagnostics, taxonomy,
    custom runtime rendering) should override this via
    ``registry.override("info", handler=...)`` and optionally call
    ``render_info()`` themselves to emit the standard fields first.

    The ``projects`` parameter is preserved for API stability and for
    potential future use (e.g., rendering the tools list when no
    specific tool is targeted), but lookup itself uses ``engine``.
    ``engine`` is required — callers that don't have an engine context
    should not be calling render_info.
    """
    tool_name = args.tool
    project, ctx = engine.find_project(tool_name)
    if project is None:
        cmd = getattr(engine, "command", None) or "dz"
        print(
            f"Tool '{tool_name}' not found. Use '{cmd} list' to see available tools."
        )
        return 1

    # Surface alias provenance so users see how their input resolved.
    if ctx is not None and ctx.alias_fqcn:
        if getattr(ctx, "resolution_kind", None) == "qualified_alias":
            # User typed the qualified form (e.g., "dazzletools:claude:cleanup").
            # Show both the qualified path AND the canonical-FQCN target.
            print(
                f"(qualified alias '{getattr(ctx, 'original_input', ctx.alias_fqcn)}' = "
                f"'{ctx.alias_fqcn}' -> canonical '{ctx.canonical_fqcn}')"
            )
        else:
            print(
                f"(resolved via virtual-kit alias '{ctx.alias_fqcn}' "
                f"-> '{ctx.canonical_fqcn}')"
            )

    # Shadow status: when this tool's short name conflicts with a
    # registered meta-command, surface the dispatch state. The library
    # default takes precedence at parse time; if the aggregator has
    # called engine.meta_registry.override(<short>, handler=...) the
    # override is the chain-the-default acknowledgment (per issue #56).
    short = project.get("name", "")
    reserved = getattr(engine, "reserved_commands", frozenset())
    if short and short in reserved:
        meta_registry = getattr(engine, "meta_registry", None)
        overrides = (
            meta_registry.user_overrides()
            if meta_registry is not None
            else frozenset()
        )
        is_overridden = short in overrides
        print()
        print(f"Shadow status: name '{short}' is registered as both")
        print(f"  - library default meta-command: {short}")
        print(f"  - aggregator tool: {project.get('_fqcn', short)}")
        print(f"The library default takes precedence at parse time.")
        if is_overridden:
            print(
                f"The aggregator has overridden the handler "
                f"(engine.meta_registry.override({short!r}, ...)) "
                f"to chain both."
            )
        else:
            print(
                f"The aggregator has NOT overridden the handler. "
                f"The tool is unreachable via short name '{short}' -- "
                f"dispatch via FQCN: {project.get('_fqcn', short)}"
            )
        print()

    print(f"Name:        {project['name']}")
    if project.get("_fqcn"):
        print(f"FQCN:        {project['_fqcn']}")
    if project.get("_kit_import_name"):
        print(f"Kit:         {project['_kit_import_name']}")
    if project.get("namespace"):
        print(f"Namespace:   {project['namespace']}")
    print(f"Version:     {project.get('version', 'unknown')}")
    print(f"Description: {project.get('description', '')}")
    print(f"Platform:    {project.get('platform', 'cross-platform')}")
    if project.get("language"):
        print(f"Language:    {project['language']}")

    # Runtime dispatch: --raw shows the manifest unresolved; --platform
    # SPEC previews per-platform resolution; default resolves for the
    # current host (with conditional dispatch + ``{{var}}`` template
    # references handled).
    raw_mode = bool(getattr(args, "raw", False))
    platform_spec = getattr(args, "platform", None)

    if raw_mode:
        _print_runtime_raw(project)
    elif platform_spec:
        _print_runtime_platform_preview(project, platform_spec)
    else:
        _print_runtime_resolved(project)

    if project.get("pass_through"):
        print(f"Pass-through: yes")

    taxonomy = project.get("taxonomy", {})
    if taxonomy.get("category"):
        print(f"Category:    {taxonomy['category']}")
    if taxonomy.get("tags"):
        print(f"Tags:        {', '.join(taxonomy['tags'])}")

    deps = project.get("dependencies", {})
    if isinstance(deps, dict) and deps.get("python"):
        print(f"Python deps: {', '.join(deps['python'])}")

    setup = project.get("setup")
    if setup:
        note = setup.get("note") if isinstance(setup, dict) else None
        cmd_preview = None
        if isinstance(setup, dict):
            cmd_preview = setup.get("command")
        print(f"Setup:       {note or cmd_preview or 'available'}")
        # Setup hint with consumer's command + FQCN so the user can
        # copy-paste. ``engine.command`` resolves to the aggregator's
        # CLI prog name (``dz`` for dazzlecmd, ``amdead`` for amdead,
        # etc.) so the hint matches whichever aggregator the user is
        # running.
        fqcn_for_setup = project.get("_fqcn", project.get("name", ""))
        cmd_name = getattr(engine, "command", None) or "dz"
        if fqcn_for_setup:
            print(f"             Run: {cmd_name} setup {fqcn_for_setup}")

    # Linked-project status: when the tool's source dir is a symlink or
    # Windows junction, surface the link target so users see how the
    # tool's source resolves on disk. Uses dazzlecmd_lib.paths helpers
    # ported from dazzlecmd.importer in v0.7.33 so this surface works
    # for any library consumer (amdead, wtf-windows, sysdiagnose, ...)
    # without dazzlecmd-package coupling.
    from dazzlecmd_lib.paths import is_linked_project, get_link_target
    tool_dir = project.get("_dir")
    if tool_dir and is_linked_project(tool_dir):
        target = get_link_target(tool_dir)
        print(f"Linked to:   {target or 'unknown'}")

    return 0


def info_handler(args, engine, projects, kits, project_root) -> int:
    """Default handler for ``info``. Delegates to ``render_info`` with
    engine context so alias FQCN lookups resolve transparently."""
    return render_info(args, projects, engine=engine)


# ---------------------------------------------------------------------------
# kit (list + status)
# ---------------------------------------------------------------------------


def kit_parser_factory(subparsers):
    """Register the ``kit`` subparser and its nested ``list``/``status``."""
    p = subparsers.add_parser("kit", help="Manage kits")
    sub = p.add_subparsers(dest="kit_command")

    kit_list_p = sub.add_parser(
        "list", help="List available kits, or tools in a kit"
    )
    kit_list_p.add_argument(
        "name", nargs="?", default=None, help="Kit name to show tools for"
    )
    kit_list_p.set_defaults(_meta="kit_list")

    kit_status_p = sub.add_parser("status", help="Show active kits")
    kit_status_p.set_defaults(_meta="kit_status")

    # Bare `kit` with no sub is treated as `kit list`
    p.set_defaults(_meta="kit_list")


def render_kit_list(args, kits, projects) -> int:
    """List all kits or tools in a specific kit.

    Generic over any kit format — reads ``_kit_name`` / ``name``,
    ``description``, ``tools``, and ``always_active`` fields.
    """
    if not kits:
        print("No kits found.")
        return 0

    kit_name = getattr(args, "name", None)

    if kit_name:
        matching = [
            k for k in kits
            if (k.get("_kit_name") or k.get("name")) == kit_name
        ]
        if not matching:
            print(f"Kit {kit_name!r} not found. Available kits:")
            for k in kits:
                print(f"  {k.get('_kit_name') or k.get('name')}")
            return 1

        kit = matching[0]
        name = kit.get("_kit_name") or kit.get("name")
        active = " (always active)" if kit.get("always_active") else ""
        print(f"Kit: {name}{active}")
        if kit.get("description"):
            print(f"  {kit['description']}")
        print()

        tool_refs = kit.get("tools", [])
        if not tool_refs:
            print("  No tools in this kit.")
            return 0

        for ref in sorted(tool_refs):
            if ":" in ref:
                ns, name_part = ref.split(":", 1)
            else:
                ns, name_part = "", ref
            match = [
                p for p in projects
                if p["name"] == name_part
                and (not ns or p.get("namespace") == ns)
            ]
            if match:
                p = match[0]
                desc = p.get("description", "")
                if len(desc) > 55:
                    desc = desc[:52] + "..."
                platform = p.get("platform", "")
                print(f"  {name_part:<16} {platform:<16} {desc}")
            else:
                print(f"  {name_part:<16} {'':16} (not found)")
        print(f"\n  {len(tool_refs)} tool(s)")
        return 0

    # No kit name — list all kits
    for i, kit in enumerate(kits):
        if i > 0:
            print()
        name = kit.get("_kit_name") or kit.get("name")
        active = " (always active)" if kit.get("always_active") else ""
        tool_count = len(kit.get("tools", []))
        print(f"  {name:<16} {tool_count} tool(s){active}")
        if kit.get("description"):
            print(f"    {kit['description']}")
    return 0


def render_kit_status(kits) -> int:
    """Show a summary of active kits."""
    active = [k for k in kits if k.get("always_active")] or list(kits)
    print(f"Active kits: {len(active)}")
    for kit in active:
        name = kit.get("_kit_name") or kit.get("name")
        tool_count = len(kit.get("tools", []))
        print(f"  {name}: {tool_count} tool(s)")
    return 0


def kit_list_handler(args, engine, projects, kits, project_root) -> int:
    return render_kit_list(args, kits, projects)


def kit_status_handler(args, engine, projects, kits, project_root) -> int:
    return render_kit_status(kits)


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def version_parser_factory(subparsers):
    p = subparsers.add_parser("version", help="Show version info")
    p.set_defaults(_meta="version")


def render_version(engine) -> int:
    """Print the aggregator's version string.

    Uses ``engine.version_info`` if set (tuple of
    ``(display_version, full_version)``). Falls back to
    ``engine.name`` alone if version_info is absent.
    """
    if engine is not None and getattr(engine, "version_info", None):
        display, full = engine.version_info
        name = getattr(engine, "name", "aggregator")
        print(f"{name} {display} ({full})")
    elif engine is not None:
        print(getattr(engine, "name", "aggregator"))
    else:
        print("(no version info)")
    return 0


def version_handler(args, engine, projects, kits, project_root) -> int:
    return render_version(engine)


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------


def tree_parser_factory(subparsers):
    p = subparsers.add_parser(
        "tree",
        help="Visualize the aggregator tree (kits and tools)",
    )
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument(
        "--depth", type=int, default=None,
        help="Limit display depth (1=kits only, 2+=include tools)",
    )
    p.add_argument(
        "--kit", "-k", default=None,
        help="Show only this kit's subtree",
    )
    p.add_argument(
        "--show-disabled", action="store_true",
        help="Include disabled kits in the output",
    )
    p.set_defaults(_meta="tree")


def render_tree(args, engine, projects, kits, project_root) -> int:
    """Render an ASCII tree (or JSON) of kits and their tools.

    Groups projects by ``_kit_import_name``. Each tool prints its FQCN
    and (truncated) description.

    When ``--show-disabled`` is set, ``engine.all_projects`` is used in
    place of the filtered ``projects`` argument so disabled-kit tools
    appear too. Kit headers carry ``[always_active]`` /
    ``[aggregator]`` / ``[disabled]`` markers based on the engine's
    user-config view (``active_kits`` / ``disabled_kits``) and on
    whether the kit's directory has a nested ``kits/`` subdir.
    """
    if engine is None:
        print("Error: tree requires engine context", file=_sys.stderr)
        return 1

    as_json = getattr(args, "json", False)
    depth_limit = getattr(args, "depth", None)
    kit_filter = getattr(args, "kit", None)
    show_disabled = getattr(args, "show_disabled", False)

    # Build the hierarchical view from the appropriate project list.
    # --show-disabled uses all_projects (includes disabled kits' tools);
    # default uses the supplied projects (typically engine.projects, active only).
    if show_disabled:
        projects = getattr(engine, "all_projects", projects)

    by_kit: dict[str, list] = {}
    for project in projects:
        kit_name = project.get("_kit_import_name", "?")
        by_kit.setdefault(kit_name, []).append(project)

    # Build a kit info dict for metadata (always_active, is_aggregator).
    # Aggregator detection: a kit whose directory contains its own ``kits/``
    # subdir is itself an aggregator (e.g., wtf-windows imported under dz).
    import os as _os
    kit_info: dict[str, dict] = {}
    tools_dir = getattr(engine, "tools_dir", "tools")
    proj_root = getattr(engine, "project_root", project_root) or ""
    for kit in getattr(engine, "kits", []):
        name = kit.get("_kit_name") or kit.get("name")
        if not name:
            continue
        tools_path = _os.path.join(proj_root, tools_dir)
        candidate_root = _os.path.join(tools_path, name)
        is_aggregator = _os.path.isdir(_os.path.join(candidate_root, "kits"))
        kit_info[name] = {
            "always_active": bool(kit.get("always_active")),
            "is_aggregator": is_aggregator,
        }

    # Compute enabled/disabled status from the engine's user config.
    config = engine._get_user_config() if hasattr(engine, "_get_user_config") else {}
    enabled_list = config.get("active_kits") if isinstance(config, dict) else None
    disabled_list = (config.get("disabled_kits") if isinstance(config, dict) else None) or []
    disabled_set = set(disabled_list) if isinstance(disabled_list, list) else set()
    enabled_set = set(enabled_list) if isinstance(enabled_list, list) else set()

    def _kit_state(kit_name):
        if kit_name in disabled_set:
            return "disabled"
        if enabled_set and kit_name not in enabled_set:
            info = kit_info.get(kit_name, {})
            if info.get("always_active"):
                return "enabled (always_active)"
            return "disabled (not in active_kits)"
        info = kit_info.get(kit_name, {})
        if info.get("always_active"):
            return "enabled (always_active)"
        return "enabled"

    kit_names = sorted(by_kit.keys())
    if kit_filter:
        kit_names = [k for k in kit_names if k == kit_filter]
        if not kit_names:
            print(f"Error: kit {kit_filter!r} not found.", file=_sys.stderr)
            return 1

    # Filter out disabled kits unless --show-disabled
    if not show_disabled:
        kit_names = [
            k for k in kit_names
            if _kit_state(k) not in ("disabled", "disabled (not in active_kits)")
        ]

    if as_json:
        result = {
            "root": getattr(engine, "name", "aggregator"),
            "command": getattr(engine, "command", ""),
            "tools_dir": getattr(engine, "tools_dir", ""),
            "kits": {},
        }
        for kit_name in kit_names:
            info = kit_info.get(kit_name, {})
            tools_data = []
            for project in sorted(by_kit[kit_name], key=lambda p: p.get("_fqcn", "")):
                tools_data.append({
                    "fqcn": project.get("_fqcn", ""),
                    "short": project.get("_short_name", project.get("name", "")),
                    "description": project.get("description", ""),
                })
            result["kits"][kit_name] = {
                "name": kit_name,
                "always_active": info.get("always_active", False),
                "is_aggregator": info.get("is_aggregator", False),
                "state": _kit_state(kit_name),
                "tools": tools_data,
            }
        print(_json.dumps(result, indent=2))
        return 0

    # ASCII tree output
    header = getattr(engine, "command", "root")
    if getattr(engine, "version_info", None):
        display, _ = engine.version_info
        name = getattr(engine, "name", "")
        header = f"{engine.command} ({name} {display})"
    print(header)

    # Virtual kits appear as separate top-level branches with -> arrows
    # to their canonical targets. Collect them from engine.kits (which
    # includes both canonical and virtual after Phase 4e).
    virtual_kits = [
        k for k in getattr(engine, "kits", [])
        if k.get("virtual") and (
            show_disabled or
            _kit_state(k.get("_kit_name") or k.get("name")) not in ("disabled", "disabled (not in active_kits)")
        )
    ]
    # Respect --kit filter for virtual kits too
    if kit_filter:
        virtual_kits = [
            k for k in virtual_kits
            if (k.get("_kit_name") or k.get("name")) == kit_filter
        ]

    total_tools = 0
    total_aliases = 0
    all_branches = len(kit_names) + len(virtual_kits)
    branch_idx = 0

    reserved = getattr(engine, "reserved_commands", frozenset())

    for kit_name in kit_names:
        branch_idx += 1
        is_last_branch = (branch_idx == all_branches)
        kit_prefix = "\\-- " if is_last_branch else "+-- "
        info = kit_info.get(kit_name, {})
        state = _kit_state(kit_name)

        markers = []
        if info.get("always_active"):
            markers.append("always_active")
        if info.get("is_aggregator"):
            markers.append("aggregator")
        if "disabled" in state:
            markers.append("disabled")
        marker_str = f" [{', '.join(markers)}]" if markers else ""

        print(f"{kit_prefix}{kit_name}{marker_str}")

        tools = sorted(by_kit[kit_name], key=lambda p: p.get("_fqcn", ""))
        total_tools += len(tools)

        if depth_limit is not None and depth_limit < 2:
            continue

        branch_indent = "    " if is_last_branch else "|   "
        for j, project in enumerate(tools):
            is_last_tool = (j == len(tools) - 1)
            tool_prefix = "\\-- " if is_last_tool else "+-- "
            fqcn = project.get("_fqcn", project.get("name", ""))
            desc = project.get("description", "")
            if len(desc) > 60:
                desc = desc[:57] + "..."
            # Shadow marker: tools whose short name is reserved by a
            # meta-command are flagged in tree output (per issue #56).
            short = project.get("name", "")
            shadow_marker = " [shadowed]" if short and short in reserved else ""
            print(f"{branch_indent}{tool_prefix}{fqcn}{shadow_marker}  {desc}")

    # Virtual-kit branches — rendered as [virtual] with -> arrows to canonicals.
    # Aliases come from engine.fqcn_index.alias_index. When the engine has no
    # fqcn_index (simple consumer with no virtual kits), the virtual_kits list
    # will already be empty, so this loop is a no-op.
    fqcn_index = getattr(engine, "fqcn_index", None)
    alias_index = (
        getattr(fqcn_index, "alias_index", {}) if fqcn_index is not None else {}
    )

    for vkit in virtual_kits:
        branch_idx += 1
        is_last_branch = (branch_idx == all_branches)
        kit_prefix = "\\-- " if is_last_branch else "+-- "
        vk_name = vkit.get("_kit_name") or vkit.get("name")
        state = _kit_state(vk_name)

        markers = ["virtual"]
        if vkit.get("always_active"):
            markers.append("always_active")
        if "disabled" in state:
            markers.append("disabled")
        marker_str = f" [{', '.join(markers)}]"
        print(f"{kit_prefix}{vk_name}{marker_str}")

        if depth_limit is not None and depth_limit < 2:
            continue

        # Collect this virtual kit's aliases from the FQCN index
        alias_pairs = []
        for alias_fqcn, canonical_fqcn in alias_index.items():
            if alias_fqcn.startswith(f"{vk_name}:"):
                alias_pairs.append((alias_fqcn, canonical_fqcn))
        alias_pairs.sort()
        total_aliases += len(alias_pairs)

        branch_indent = "    " if is_last_branch else "|   "
        for j, (alias_fqcn, canonical_fqcn) in enumerate(alias_pairs):
            is_last = (j == len(alias_pairs) - 1)
            tool_prefix = "\\-- " if is_last else "+-- "
            print(f"{branch_indent}{tool_prefix}{alias_fqcn} -> {canonical_fqcn}")

    print()
    if total_aliases:
        print(
            f"{total_tools} tools across {len(kit_names)} kit(s), "
            f"{total_aliases} alias(es) in {len(virtual_kits)} virtual kit(s)"
        )
    else:
        print(f"{total_tools} tools across {len(kit_names)} kit(s)")
    return 0


def tree_handler(args, engine, projects, kits, project_root) -> int:
    return render_tree(args, engine, projects, kits, project_root)


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


def setup_parser_factory(subparsers):
    p = subparsers.add_parser(
        "setup",
        help="Run a tool's declared setup script (install deps, build, etc.)",
    )
    p.add_argument(
        "tool", nargs="?", default=None,
        help="Tool name or FQCN. Omit to list tools with setup declared.",
    )
    p.set_defaults(_meta="setup")


def render_setup_listing(projects) -> int:
    """List tools that declare a setup block.

    Used when ``setup`` is invoked without a tool argument.
    """
    def _has_setup(project):
        setup = project.get("setup")
        if not isinstance(setup, dict):
            return False
        if setup.get("command"):
            return True
        if setup.get("steps"):
            return True
        if setup.get("script"):
            return True
        platforms = setup.get("platforms")
        if isinstance(platforms, dict) and platforms:
            return True
        return False

    with_setup = [p for p in projects if _has_setup(p)]
    if not with_setup:
        print("No tools have setup declared.")
        return 0

    with_setup.sort(key=lambda p: p.get("_fqcn", p.get("name", "")))
    longest = max(
        len(p.get("_fqcn", p.get("name", ""))) for p in with_setup
    )
    col_width = max(20, min(50, longest))

    print("Tools with setup declared:\n")
    for project in with_setup:
        fqcn = project.get("_fqcn", project.get("name", ""))
        setup = project.get("setup", {})
        note = setup.get("note") if isinstance(setup, dict) else None
        note = note or "-"
        print(f"  {fqcn:<{col_width}}  {note}")
    print("\nRun: setup <tool> to execute a tool's setup.")
    return 0


def setup_handler(args, engine, projects, kits, project_root) -> int:
    """Default handler for ``setup``.

    With no tool argument: lists tools that declare a setup block.
    With a tool argument: resolves the tool's setup block (platform +
    user overrides + _vars) and executes the resolved command.
    """
    tool_name = getattr(args, "tool", None)

    if not tool_name:
        return render_setup_listing(projects)

    # Resolve the tool via engine.find_project — supports short name,
    # canonical FQCN, alias FQCN, and kit-qualified shortcuts uniformly.
    # engine is mandatory in the registry dispatch path; library
    # consumers that build their own dispatcher must pass an engine.
    project, ctx = engine.find_project(tool_name)
    if project is None:
        print(f"Tool {tool_name!r} not found.", file=_sys.stderr)
        return 1
    matches = [project]

    if len(matches) > 1:
        print(f"Multiple tools named {tool_name!r}:", file=_sys.stderr)
        for p in matches:
            print(f"  {p.get('_fqcn', p['name'])}", file=_sys.stderr)
        return 1

    project = matches[0]
    setup = project.get("setup")
    if not setup:
        print(
            f"Tool {project.get('_fqcn', project['name'])!r} has no setup declared.",
            file=_sys.stderr,
        )
        return 1

    # Resolve the setup block via the library's resolver (handles
    # platform selection, user overrides, _vars substitution).
    try:
        from dazzlecmd_lib.setup_resolve import resolve_setup_block

        resolved = resolve_setup_block(project)
    except _json.JSONDecodeError as exc:
        print(
            f"Error: user override file is not valid JSON: {exc}",
            file=_sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"Error: cannot read user override file: {exc}", file=_sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error resolving setup: {exc}", file=_sys.stderr)
        return 1

    if resolved is None:
        print(
            f"Tool {project.get('_fqcn', project['name'])!r} has no executable setup.",
            file=_sys.stderr,
        )
        return 1

    command = resolved.get("command")
    if not command:
        print(
            f"Tool {project.get('_fqcn', project['name'])!r} has no setup command "
            f"for this platform.",
            file=_sys.stderr,
        )
        return 1

    # Execute the resolved command. The engine is a dumb dispatcher —
    # we run the author-declared command via the platform shell.
    import subprocess as _subprocess

    print(f"Running setup for {project.get('_fqcn', project['name'])}...")
    print(f"  {command}")
    _sys.stdout.flush()  # flush before subprocess to avoid output interleaving

    result = _subprocess.run(command, shell=True, cwd=project.get("_dir"))
    return result.returncode


# ---------------------------------------------------------------------------
# Bulk registration
# ---------------------------------------------------------------------------


# Canonical mapping: meta-command name -> (parser_factory, handler)
_DEFAULTS = {
    "list": (list_parser_factory, list_handler),
    "info": (info_parser_factory, info_handler),
    "kit": (kit_parser_factory, kit_list_handler),  # parser sets _meta=kit_list by default
    "version": (version_parser_factory, version_handler),
    "tree": (tree_parser_factory, tree_handler),
    "setup": (setup_parser_factory, setup_handler),
}

# Sub-meta handlers (kit has kit_list and kit_status sub-commands).
# These are separately registered so the engine's dispatch can route
# kit_status -> kit_status_handler.
_SUB_HANDLERS = {
    "kit_list": kit_list_handler,
    "kit_status": kit_status_handler,
}


def register_all(registry) -> None:
    """Register every default meta-command against the given registry.

    Called by ``AggregatorEngine.__init__`` when
    ``include_default_meta_commands=True`` (the default).

    This registers the top-level commands (list, info, kit, version,
    tree, setup). Nested meta tags (kit_list, kit_status) are registered
    via ``_register_sub_handlers`` so the registry's dispatch can route
    them.
    """
    for name, (parser_factory, handler) in _DEFAULTS.items():
        registry.register(name, parser_factory, handler)
    _register_sub_handlers(registry)


def register_selected(
    registry, include: Optional[Iterable[str]] = None
) -> None:
    """Register only the named defaults.

    Useful when an aggregator wants an explicit subset. Unknown names
    raise ``KeyError``.

    Example::

        register_selected(registry, include=["list", "info", "version"])
        # tree, setup, kit excluded
    """
    if include is None:
        register_all(registry)
        return

    for name in include:
        if name not in _DEFAULTS:
            raise KeyError(
                f"Unknown default meta-command: {name!r}. "
                f"Available: {sorted(_DEFAULTS.keys())}"
            )
        parser_factory, handler = _DEFAULTS[name]
        registry.register(name, parser_factory, handler)

    # If kit is included, also register the sub handlers
    if "kit" in include:
        _register_sub_handlers(registry)


def _register_sub_handlers(registry) -> None:
    """Register the sub-meta handlers (kit_list, kit_status).

    These don't have parser factories (the kit parser factory builds
    the nested subparsers); they only need dispatch-side routing entries
    so ``args._meta = "kit_status"`` resolves to the right handler.
    """
    # A minimal "parser factory" that does nothing — the kit parser
    # already built the subparser when kit was registered.
    def _noop_parser(subparsers):
        pass

    for name, handler in _SUB_HANDLERS.items():
        if name not in registry:
            registry.register(name, _noop_parser, handler)
