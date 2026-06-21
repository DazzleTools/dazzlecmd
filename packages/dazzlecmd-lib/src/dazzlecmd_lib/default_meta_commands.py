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

from . import colors as _colors
from .core import is_constitutional as _is_constitutional


def _constitutional_entry(entry) -> bool:
    """True if a list entry is a constitutional ``dazzlecmd_lib.core`` tool.

    Such a tool's canonical home is ``dazzlecmd_lib:core:<name>`` (the engine
    lives in the lib's constitutional namespace); ``core:<name>`` is the
    consumer projection shown in ``dz list``. The ``[lib]`` marker surfaces
    that distinction.
    """
    return (entry.get("namespace") == "core"
            and _is_constitutional(entry.get("name", "")))


# ---------------------------------------------------------------------------
# Display-layout constants (shared by the lib renderers and consumer CLIs).
# The preferred pattern for COLUMN widths is data-computed (the #48 drill-in
# discipline: width = max over the actual rows); these constants exist for the
# genuinely fixed parts of the layout that data can't derive.
# ---------------------------------------------------------------------------

# get_terminal_size fallback when no TTY is attached (pipes, CI, byte-gate).
TERM_SIZE_FALLBACK = (80, 24)

# Never wrap or truncate a description below this many columns -- on absurdly
# narrow terminals, overflow beats unreadable two-character shards.
MIN_DESC_WIDTH = 20

# Kit-name column in the kit list/status summary views.
KIT_NAME_COL = 16

# Hanging indent for summary-view description lines (kit list/status).
SUMMARY_INDENT = 4


def _term_width():
    """The terminal's column count, with the standard non-TTY fallback."""
    return _shutil.get_terminal_size(TERM_SIZE_FALLBACK).columns


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


def _print_legend_entry(marker, text, term_width, *, color=()):
    """Print a footer marker-legend entry with word-boundary wrapping and a
    hanging indent.

    The marker (``[*]``/``[+]``/``[lib]``) sits alone at the left of the first
    line; wrapped continuation lines align under the START of the text, so the
    marker stands out -- the same layout discipline as tool-description wrapping
    (render_list / render_info). Without this the legend was emitted as one long
    line and the terminal hard-wrapped it mid-word (e.g. "ali" / "as").

    ``color`` is a tuple of ``colors`` codes used to colorize the MARKER token
    (matching the row markers in ``_label_styled`` -- ``[*]`` bold+red, ``[+]``
    cyan, ``[lib]`` green). Width/indent math always uses the PLAIN marker
    length so the ANSI escapes never disturb alignment; color is applied only
    when ``should_use_color()`` (off for the byte-gate / pipes, so baselines
    stay plain).
    """
    prefix = f"  {marker} "                 # plain -> drives all width/indent math
    indent = " " * len(prefix)
    avail = max(MIN_DESC_WIDTH, term_width - len(prefix))
    lines = _wrap_description(text, avail)
    shown_marker = marker
    if color and _colors.should_use_color():
        shown_marker = _colors.colorize(marker, *color)
    print(f"  {shown_marker} {lines[0]}")
    for line in lines[1:]:
        print(f"{indent}{line}")


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
    p.add_argument(
        "--show-hidden", action="store_true",
        help="Include tools hidden via the 'hidden_tools' config (still dispatchable).",
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
            filtered = [p for p in filtered if p.namespace == ns]
        if plat:
            filtered = [
                p for p in filtered
                if (p.platform or "cross-platform") == plat
            ]
        if tag:
            filtered = [
                p for p in filtered
                if tag in p.taxonomy.get("tags", [])
            ]
        if kit:
            filtered = [p for p in filtered if p.kit_import_name == kit]
        if not filtered:
            print("No tools found.")
            return 0
        name_width = max(len(p.name) for p in filtered)
        name_width = max(name_width, len("Name"))
        kit_col_width = max(
            (len(p.kit_import_name or "") for p in filtered),
            default=0,
        )
        kit_col_width = max(kit_col_width, len("Kit"))
        header = f"  {'Name':<{name_width}}  {'Kit':<{kit_col_width}}  Description"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for project in filtered:
            name = project.name
            kit_name = project.kit_import_name or ""
            desc = project.description or ""
            # Width-aware truncation (was a hard 57-char cut).
            _fl_avail = max(
                MIN_DESC_WIDTH,
                _term_width()
                - (2 + name_width + 2 + kit_col_width + 2),
            )
            if len(desc) > _fl_avail:
                desc = desc[:_fl_avail - 3] + "..."
            print(f"  {name:<{name_width}}  {kit_name:<{kit_col_width}}  {desc}")
        print(f"\n  {len(filtered)} tool(s) found")
        return 0

    # Hidden tools: a render-only filter (the tool stays dispatchable; this just
    # omits it from `dz list`). Revealed by --show-hidden. No-op -- byte-identical
    # -- when the hidden_tools config is empty (the default).
    projects = engine.filter_hidden(
        projects, reveal=getattr(args, "show_hidden", False)
    )

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
            if not k.virtual:
                continue
            if not k.kit_active:
                continue
            vk_name = k.kit_name or k.name
            if not vk_name:
                continue
            if kit_filter is not None and kit_filter != vk_name:
                continue
            # Compute the section key this virtual kit WOULD have.
            tools_list = k.tools or []
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

    # v0.7.37: gate ANSI on once per call. The plain/styled label split
    # below keeps column-width math correct -- ANSI escape sequences
    # have zero visible width but contribute to ``len()``.
    _use_color = _colors.should_use_color()

    def _label_plain(entry):
        """Label without ANSI codes -- used for column-width math."""
        markers = []
        if entry["name"] in colliding:
            markers.append("*")
        if show_mode == "all" and entry.get("has_aliases"):
            markers.append("+")
        if _constitutional_entry(entry):
            markers.append("lib")
        if not markers:
            return entry["name"]
        suffix = "".join(f"[{m}]" for m in markers)
        return f"{entry['name']} {suffix}"

    def _label_styled(entry):
        """Label with ANSI codes when ``_use_color`` is True.

        ``[*]`` -- bold+red (collision: maximum attention).
        ``[+]`` -- cyan (alias: informational, not a warning).
        """
        if not _use_color:
            return _label_plain(entry)
        marker_strs = []
        if entry["name"] in colliding:
            marker_strs.append(
                _colors.colorize("[*]", _colors.BOLD, _colors.RED)
            )
        if show_mode == "all" and entry.get("has_aliases"):
            marker_strs.append(_colors.colorize("[+]", _colors.CYAN))
        if _constitutional_entry(entry):
            marker_strs.append(_colors.colorize("[lib]", _colors.GREEN))
        if not marker_strs:
            return entry["name"]
        return f"{entry['name']} {''.join(marker_strs)}"

    term_width = _term_width()

    def _print_styled_row(styled, plain, target_width, suffix):
        """Print row with width padding computed on plain (unstyled) label,
        so ANSI escape sequences don't break column alignment."""
        padding = " " * (target_width - len(plain))
        print(f"{styled}{padding}{suffix}")

    if use_flat:
        # Single-section flat fallback (v0.7.27 layout).
        flat_entries = sections[section_keys[0]]["entries"]
        if not flat_entries:
            print("No tools found.")
            return 0
        name_width = max(len(_label_plain(e)) for e in flat_entries)
        name_width = max(name_width, len("Name"))
        kit_width = max(len(e["kit"]) for e in flat_entries)
        kit_width = max(kit_width, len("Kit"))

        # BOLD header row -- structural emphasis, not data.
        header_codes = (_colors.BOLD,) if _use_color else ()
        header_text = (
            f"  {'Name':<{name_width}}  {'Kit':<{kit_width}}  Description"
        )
        print(_colors.colorize(header_text, *header_codes))
        print("  " + "-" * (len(header_text) - 2))

        desc_col = 2 + name_width + 2 + kit_width + 2
        desc_max = term_width - desc_col
        for entry in flat_entries:
            plain = _label_plain(entry)
            styled = _label_styled(entry)
            kit = entry["kit"]
            desc = entry["description"]
            wrapped = _wrap_description(desc, desc_max)
            _print_styled_row(
                "  " + styled, plain, name_width,
                f"  {kit:<{kit_width}}  {wrapped[0]}",
            )
            indent = " " * desc_col
            for line in wrapped[1:]:
                print(f"{indent}{line}")
    else:
        # Sectioned layout.
        for i, sk in enumerate(section_keys):
            if i > 0:
                print()  # one blank line between sections
            section = sections[sk]
            # Section header: BOLD canonical/virtual kit name + DIM
            # virtual-kit annotation. Both fall back to plain when
            # ``_use_color`` is False (e.g., piped output).
            if section["kind"] == "virtual":
                annotation_plain = f"  (virtual kit '{section['vk_name']}')"
                annotation_styled = (
                    _colors.colorize(annotation_plain, _colors.DIM)
                    if _use_color else annotation_plain
                )
            else:
                annotation_styled = ""
            sk_styled = (
                _colors.colorize(sk, _colors.BOLD) if _use_color else sk
            )
            print(f"{sk_styled}:{annotation_styled}")

            section_entries = section["entries"]
            if not section_entries:
                print("    (no active aliases)")
                continue

            # Per-section column widths (name only; description fills rest)
            name_width = max(len(_label_plain(e)) for e in section_entries)
            indent = "  "  # 2-space indent under each section header
            desc_col = len(indent) + name_width + 2
            desc_max = term_width - desc_col
            for entry in section_entries:
                plain = _label_plain(entry)
                styled = _label_styled(entry)
                desc = entry["description"]
                wrapped = _wrap_description(desc, desc_max)
                _print_styled_row(
                    f"{indent}{styled}", plain, name_width,
                    f"  {wrapped[0]}",
                )
                wrap_indent = " " * desc_col
                for line in wrapped[1:]:
                    print(f"{wrap_indent}{line}")

    # Footer — markers explanation
    has_collision = bool(colliding)
    has_alias_marker = show_mode == "all" and any(
        e.get("has_aliases") for e in entries
    )
    has_lib_marker = any(_constitutional_entry(e) for e in entries)
    if has_collision or has_alias_marker or has_lib_marker:
        print()
        if has_collision:
            cmd = getattr(engine, "command", None) or "dz"
            _print_legend_entry(
                "[*]",
                f"short-name collision -- use '{cmd} info <fqcn>' or "
                f"'{cmd} kit favorite' to disambiguate.",
                term_width,
                color=(_colors.BOLD, _colors.RED),
            )
        if has_alias_marker:
            cmd = getattr(engine, "command", None) or "dz"
            _print_legend_entry(
                "[+]",
                f"canonical has aliases (virtual-kit overlays and/or "
                f"auto-realpath dedup of cross-aggregator embeddings) -- "
                f"use '{cmd} info <name>' for alias details.",
                term_width,
                color=(_colors.CYAN,),
            )
        if has_lib_marker:
            cmd = getattr(engine, "command", None) or "dz"
            agg = getattr(engine, "name", None) or "dazzlecmd"
            _print_legend_entry(
                "[lib]",
                f"constitutional primitive (engine in dazzlecmd_lib); "
                f"absolute FQCN 'dazzlecmd_lib:core:<name>'. Names show "
                f"prefixless -- the absolute prepends this aggregator (e.g. "
                f"'{agg}:core:<name>'); both resolve. '{cmd} info <name>' shows it.",
                term_width,
                color=(_colors.GREEN,),
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
            if k.virtual:
                vk_name = k.kit_name or k.name
                if vk_name:
                    virtual_kit_names.add(vk_name)
                    virtual_kit_metadata[vk_name] = k

    kit_filter_is_virtual = kit_filter is not None and kit_filter in virtual_kit_names

    # Track which canonical FQCNs have aliases (used for [+] marker). Overlay
    # aliases (#180) are dispatch-only artifacts of the constitutional overlay
    # -- the home FQCN surfaced onto this aggregator. They are shown via the
    # [lib] marker + epilogue, NOT as a [+] "has aliases" (which is reserved for
    # virtual-kit overlays), so they are excluded here.
    canonicals_with_aliases = set()
    if engine is not None and hasattr(engine, "fqcn_index"):
        _alias_sources = getattr(engine.fqcn_index, "_alias_sources", {})
        for alias_fqcn, canonical_fqcn in engine.fqcn_index.alias_index.items():
            if _alias_sources.get(alias_fqcn) == "overlay":
                continue
            canonicals_with_aliases.add(canonical_fqcn)

    # --- Build canonical entries ---
    # Skip canonical iteration entirely when the kit filter is a virtual
    # kit name — that filter asks "what's in the virtual kit" which is
    # exclusively aliases, not canonicals.
    if show_mode in ("canonical", "all", "default") and not kit_filter_is_virtual:
        for p in projects:
            # Skip projects whose FQCN was demoted to an auto-realpath
            # alias (issue #65): they appear under their canonical's row
            # in the alias section, never as duplicate canonical rows.
            if p.auto_realpath_alias:
                continue
            kit_name = p.kit_import_name or ""
            if kit_filter is not None:
                if kit_name != kit_filter:
                    continue
            fqcn = p.fqcn or ""  # matches old .get("_fqcn", ""); fqcn is Optional
            # Section key: kit_path = FQCN minus the last segment
            if ":" in fqcn:
                section_key = fqcn.rsplit(":", 1)[0]
            else:
                section_key = kit_name or "(unknown)"
            entries.append({
                "name": p.name,
                "kit": kit_name,
                "description": p.description or "",
                "entry_type": "canonical",
                "namespace": p.namespace,
                "platform": p.platform or "cross-platform",
                "tags": p.taxonomy.get("tags", []),
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
                p.fqcn: p for p in projects if p.fqcn
            }
            alias_sources = getattr(engine.fqcn_index, "_alias_sources", {})
            # Iterate every alias and build its entry
            for alias_fqcn, canonical_fqcn in engine.fqcn_index.alias_index.items():
                # Auto-realpath aliases (#65) are physical-identity
                # bookkeeping for dispatch; their canonical already
                # appears in the canonical section with the [+] marker.
                # Overlay aliases (#180) are the constitutional home FQCN
                # surfaced onto this aggregator -- dispatch-only, shown via
                # the [lib] marker instead. Skip both from the alias rows to
                # avoid duplicate rows under bogus "(virtual kit '<path>')"
                # section headers.
                if alias_sources.get(alias_fqcn) in ("auto-realpath", "overlay"):
                    continue
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
                    if target_project.kit_import_name != kit_filter:
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
                        canonical_kit_path = target_project.kit_import_name or ""
                    section_key = (
                        f"{canonical_kit_path}:{vk_name}"
                        if canonical_kit_path else vk_name
                    )
                    vk_local_name = vk_name

                entries.append({
                    "name": alias_short,
                    "kit": vk_name,  # legacy column for flat fallback
                    "description": target_project.description or "",
                    "entry_type": "alias",
                    "namespace": target_project.namespace,
                    "platform": target_project.platform or "cross-platform",
                    "tags": target_project.taxonomy.get("tags", []),
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

    raw_runtime = project.runtime or {}
    # BUG-3 fix: also trigger resolution when the manifest contains any
    # `{{var}}` references -- catching unresolved vars at inspection time
    # rather than silently passing through. Includes manifest-top _vars
    # declarations because those make a var-reference-only manifest
    # "conditional" on those vars being defined.
    has_conditional = (
        "platforms" in raw_runtime
        or "prefer" in raw_runtime
        or has_template_refs(raw_runtime)
        or bool(project.extra_get("_vars"))
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

    runtime = resolved.runtime or {}
    runtime_type = runtime.get("type", "python")
    platform_tag = pi.os + (f".{pi.subtype}" if pi.subtype else "")
    print(f"Runtime:     {runtime_type}  (resolved for {platform_tag})")
    _print_runtime_dispatch_fields(runtime)
    print(f"             (manifest declares conditional dispatch; use --raw to see the full declaration)")


def _print_runtime_raw(project):
    """--raw view: show the manifest as declared, no resolution."""
    runtime = project.runtime or {}
    runtime_type = runtime.get("type", "python")
    print(f"Runtime:     {runtime_type}  (raw, unresolved)")
    _print_runtime_dispatch_fields(runtime)

    # BUG-2 fix: surface manifest-top _vars AND runtime-block _vars so authors
    # debugging {{...}} references can see what's declared at each scope level.
    manifest_vars = project.extra_get("_vars")
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

    raw_runtime = project.runtime or {}
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

    # v0.7.37: gate ANSI on once per call. Provenance and shadow banners
    # get color emphasis; standard field rows stay plain for now.
    _use_color = _colors.should_use_color()

    def _dim(s):
        return _colors.colorize(s, _colors.DIM) if _use_color else s

    def _warn(s):
        # BOLD+YELLOW for attention-grabbing status banners (shadow surface).
        return _colors.colorize(s, _colors.BOLD, _colors.YELLOW) if _use_color else s

    # Surface alias provenance so users see how their input resolved.
    # DIM emphasis -- contextual information rather than primary data.
    if ctx is not None and ctx.alias_fqcn:
        alias_sources = getattr(
            getattr(engine, "fqcn_index", None), "_alias_sources", {}
        )
        if alias_sources.get(ctx.alias_fqcn) == "auto-realpath":
            # Issue #65: auto-realpath dedup. The user typed a longer
            # FQCN that resolves to the same physical script as the
            # canonical (shorter) FQCN.
            print(_dim(
                f"(auto-realpath alias '{ctx.alias_fqcn}' -> canonical "
                f"'{ctx.canonical_fqcn}'; same physical script reached "
                f"via two discovery paths)"
            ))
        elif alias_sources.get(ctx.alias_fqcn) == "overlay":
            # Issue #180: constitutional overlay. The user typed the home
            # canonical (`dazzlecmd_lib:core:<name>`, Scheme O) which is
            # surfaced on this aggregator as the prefixless projection
            # (`core:<name>`, Scheme P) via the overlay grouping transition.
            print(_dim(
                f"(overlay: '{ctx.alias_fqcn}' is the constitutional home in "
                f"dazzlecmd_lib; surfaced here as '{ctx.canonical_fqcn}')"
            ))
        elif getattr(ctx, "resolution_kind", None) == "qualified_alias":
            # User typed the qualified form (e.g., "dazzletools:claude:cleanup").
            # Show both the qualified path AND the canonical-FQCN target.
            print(_dim(
                f"(qualified alias '{getattr(ctx, 'original_input', ctx.alias_fqcn)}' = "
                f"'{ctx.alias_fqcn}' -> canonical '{ctx.canonical_fqcn}')"
            ))
        else:
            print(_dim(
                f"(resolved via virtual-kit alias '{ctx.alias_fqcn}' "
                f"-> '{ctx.canonical_fqcn}')"
            ))

    # Shadow status: when this tool's short name conflicts with a
    # registered meta-command, surface the dispatch state. The library
    # default takes precedence at parse time; if the aggregator has
    # called engine.meta_registry.override(<short>, handler=...) the
    # override is the chain-the-default acknowledgment (per issue #56).
    short = project.name or ""
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
        print(f"{_warn('Shadow status:')} name '{short}' is registered as both")
        print(f"  - library default meta-command: {short}")
        print(f"  - aggregator tool: {project.fqcn or short}")
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
                f"dispatch via FQCN: {project.fqcn or short}"
            )
        print()

    print(f"Name:        {project.name}")
    if project.fqcn:
        print(f"FQCN:        {project.fqcn}")
    # The ABSOLUTE FQCN: the prefixless FQCN above is a projection; this is the
    # true globally-unique name (home aggregator prepended), always derivable
    # via engine.absolute_fqcn. Constitutional tools carry the lib's home prefix
    # (they are overlaid here), which is why their absolute differs from
    # <this-aggregator>:<fqcn>.
    _abs = engine.absolute_fqcn(project)
    if _abs and _abs != project.fqcn:
        if project.namespace == "core" and _is_constitutional(project.name):
            print(f"Absolute:    {_abs}   (constitutional; overlaid from dazzlecmd_lib)")
        else:
            print(f"Absolute:    {_abs}")
    if project.kit_import_name:
        print(f"Kit:         {project.kit_import_name}")
    if project.namespace:
        print(f"Namespace:   {project.namespace}")
    print(f"Version:     {project.version or 'unknown'}")
    # v0.7.37: wrap Description to terminal width with continuation-line
    # indent aligned to the start of the value column. Matches the layout
    # discipline established by render_list / render_kit_list (#48 / #NN).
    _label = "Description: "
    _indent = " " * len(_label)
    _desc = project.description or ""
    _tw = _term_width()
    _wrap_width = max(MIN_DESC_WIDTH, _tw - len(_label))
    _wrapped = _wrap_description(_desc, _wrap_width)
    print(f"{_label}{_wrapped[0]}")
    for _line in _wrapped[1:]:
        print(f"{_indent}{_line}")
    print(f"Platform:    {project.platform or 'cross-platform'}")
    if project.language:
        print(f"Language:    {project.language}")

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

    if project.pass_through:
        print(f"Pass-through: yes")

    taxonomy = project.taxonomy
    if taxonomy.get("category"):
        print(f"Category:    {taxonomy['category']}")
    if taxonomy.get("tags"):
        print(f"Tags:        {', '.join(taxonomy['tags'])}")

    deps = project.dependencies or {}
    if isinstance(deps, dict) and deps.get("python"):
        print(f"Python deps: {', '.join(deps['python'])}")

    setup = project.setup
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
        fqcn_for_setup = project.fqcn or project.name or ""
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
    tool_dir = project.directory
    if tool_dir and is_linked_project(tool_dir):
        target = get_link_target(tool_dir)
        print(f"Linked to:   {target or 'unknown'}")

    # Long-form description / mini-manpage (closes #61). Optional manifest
    # field ``long_description``; rendered below the standard field rows
    # with a BOLD ``Details:`` header. Wrapped to terminal width using
    # the same ``_wrap_description`` helper that the ``Description:`` row
    # uses. Multi-line content is preserved -- each input line wraps
    # independently and blank input lines render as blank output lines
    # (paragraph breaks).
    long_desc = project.long_description or ""
    if isinstance(long_desc, str) and long_desc.strip():
        print()
        details_header = (
            _colors.colorize("Details:", _colors.BOLD)
            if _use_color else "Details:"
        )
        print(details_header)
        term_width = _term_width()
        indent = "  "
        wrap_width = max(20, term_width - len(indent))
        for line in long_desc.splitlines():
            if not line.strip():
                print()
                continue
            for sub in _wrap_description(line, wrap_width):
                print(f"{indent}{sub}")

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
    p = subparsers.add_parser("kit", help="Manage {kits, aggregators, virtual kits, ...}")
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


def render_kit_list(args, kits, projects, engine=None) -> int:
    """List all kits or tools in a specific kit.

    Generic over any kit format — reads ``_kit_name`` / ``name``,
    ``description``, ``tools``, and ``always_active`` fields.

    ``engine`` (the renderer-contract convention: renderers take the engine as
    the capability handle, like ``render_info``) unlocks the full view --
    config-aware enabled/disabled status, data-computed drill-in columns with
    wrapped descriptions (#48), and the virtual-kit alias drill-in (reads
    ``engine.fqcn_index.alias_index``). The registry's ``kit_list_handler``
    passes it, so every consumer gets the full view by default.
    ``engine=None`` (legacy direct callers) renders the historical output,
    unchanged. Unified from dazzlecmd's ``_cmd_kit_list`` (the kit-list
    renderer-unification DWP, 2026-06-11) -- dazzlecmd no longer carries its
    own handler.
    """
    if not kits:
        print("No kits found.")
        return 0

    if engine is not None:
        return _render_kit_list_full(args, kits, projects, engine)
    return _render_kit_list_legacy(args, kits, projects)


def _render_kit_list_full(args, kits, projects, engine) -> int:
    """The engine-aware kit list (ported verbatim from dazzlecmd's
    ``_cmd_kit_list``): config-aware status, #48 data-computed drill-in
    columns, virtual-kit alias drill-in."""
    kit_name = getattr(args, "name", None)
    _use_color = _colors.should_use_color()

    # Compute enabled/disabled status from config
    enabled_set = set()
    disabled_set = set()
    config = engine._get_user_config()
    active_list = config.get("active_kits")
    disabled_list = config.get("disabled_kits") or []
    if isinstance(active_list, list):
        enabled_set = set(active_list)
    if isinstance(disabled_list, list):
        disabled_set = set(disabled_list)

    def _kit_status(kit):
        name = kit.kit_name or kit.name
        if name in disabled_set:
            return "disabled"
        if kit.always_active:
            return "always active"
        if enabled_set and name not in enabled_set:
            return "disabled (not in active_kits)"
        return "enabled"

    if kit_name:
        # Show tools in a specific kit
        matching = [k for k in kits if (k.kit_name or k.name) == kit_name]
        if not matching:
            print(f"Kit '{kit_name}' not found. Available kits:")
            for k in kits:
                print(f"  {k.kit_name or k.name}")
            return 1

        kit = matching[0]
        name = kit.kit_name or kit.name
        status = _kit_status(kit)
        is_virtual = kit.virtual is True
        label = "virtual, " + status if is_virtual else status
        # A detached kit carries a `pointer` block (the LOADING axis): declared
        # but not materialized, so it loads no tools. Flag it in the header.
        is_pointer = bool(getattr(kit, "pointer", None))
        if is_pointer:
            label += ", pointer"
        print(f"Kit: {name} [{label}]")
        if kit.description:
            print(f"  {kit.description}")
        if is_pointer:
            print(f"  (detached -- a pointer; tools not loaded; "
                  f"`dz kit attach {name}` to reconnect)")
        print()

        # Virtual-kit drill-in: show alias FQCN + canonical target +
        # description for each declared alias. Without this, users
        # see canonical short names and miss the whole point of the
        # virtual kit (its aliases).
        if is_virtual:
            return _render_virtual_kit_aliases(kit, projects, engine)

        tool_refs = kit.tools or []
        if not tool_refs:
            print("  No tools in this kit.")
            return 0

        # Build rows first so per-column widths can be computed from
        # actual data instead of fixed 16-char columns (#48). Matches
        # the `dz list` flat-fallback layout.
        rows = []  # (name, platform, description_or_notfound_marker)
        for ref in sorted(tool_refs):
            # Modern path: ref is a full FQCN as written by
            # ``engine._discover_aggregator``'s post-recursion populate
            # (e.g., ``wtf:core:locked``). Match by ``_fqcn`` directly so
            # multi-segment FQCNs resolve.
            match = [p for p in projects if p.fqcn == ref]
            if match:
                p = match[0]
                ref_name = p.name
            else:
                # Legacy fallback: parse ref as ``ns:name`` for existing
                # kit manifests that use 2-segment refs.
                if ":" in ref:
                    ns, ref_name = ref.split(":", 1)
                else:
                    ns, ref_name = "", ref
                match = [
                    p for p in projects
                    if p.name == ref_name
                    and (not ns or p.namespace == ns)
                ]
            if match:
                p = match[0]
                rows.append(
                    (ref_name, p.platform or "", p.description or "")
                )
            else:
                rows.append((ref_name, "", "(not found)"))

        term_width = _term_width()
        name_width = max(len(r[0]) for r in rows)
        platform_width = max(len(r[1]) for r in rows)
        indent = "  "
        # 2 indent + name + 2 gap + platform + 2 gap = description column
        desc_col = len(indent) + name_width + 2 + platform_width + 2
        desc_max = term_width - desc_col

        for n, plat, desc in rows:
            wrapped = _wrap_description(desc, desc_max)
            print(
                f"{indent}{n:<{name_width}}  "
                f"{plat:<{platform_width}}  {wrapped[0]}"
            )
            wrap_indent = " " * desc_col
            for line in wrapped[1:]:
                print(f"{wrap_indent}{line}")

        print(f"\n  {len(tool_refs)} tool(s)")
        return 0

    # No name given — list all kits with status
    any_pointer = False
    for i, kit in enumerate(kits):
        if i > 0:
            print()  # blank line separator for readability
        name = kit.kit_name or kit.name
        status = _kit_status(kit)
        tool_count = len(kit.tools or [])
        # BOLD the kit name so it stands out as the row anchor. Pad INSIDE
        # the colorize so the field math runs on plain text and ANSI never
        # skews alignment.
        name_styled = (
            _colors.colorize(f"{name:<{KIT_NAME_COL}}", _colors.BOLD)
            if _use_color else f"{name:<{KIT_NAME_COL}}"
        )
        # [pointer] marks a DETACHED kit (a `pointer` block on the registry,
        # written by `dz kit detach`): declared but not materialized, so it
        # loads no tools (the LOADING axis, orthogonal to the activation
        # [status]). YELLOW = caution, not error. Conditional, so kits without
        # a pointer block render byte-identically to before.
        if getattr(kit, "pointer", None):
            any_pointer = True
            ptr = (_colors.colorize(" [pointer]", _colors.YELLOW)
                   if _use_color else " [pointer]")
        else:
            ptr = ""
        print(f"  {name_styled} {tool_count} tool(s)  [{status}]{ptr}")
        if kit.description:
            # Word-wrap to terminal width with a hanging indent (the
            # render_list formatting discipline).
            avail = max(MIN_DESC_WIDTH, _term_width() - SUMMARY_INDENT)
            for line in _wrap_description(kit.description, avail):
                print(f"    {line}")
    if any_pointer:
        print()
        print("  [pointer] = detached (a pointer; tools not loaded); "
              "`dz kit attach <name>` to reconnect")
    return 0


def _render_virtual_kit_aliases(kit, projects, engine) -> int:
    """Drill-in rendering for a virtual kit: show each alias FQCN with
    its canonical target and canonical description.

    Works by iterating ``engine.fqcn_index.alias_index`` and filtering
    to aliases whose virtual-kit prefix matches this kit's name. Falls
    back to iterating ``kit.tools`` + ``kit.name_rewrite`` when no engine
    index is available (robustness for direct callers).
    """
    vk_name = kit.kit_name or kit.name
    name_rewrite = kit.name_rewrite or {}
    tools = kit.tools or []

    # Build (alias_fqcn, canonical_fqcn, alias_short) rows
    rows = []
    if engine is not None and hasattr(engine, "fqcn_index"):
        for alias_fqcn, canonical_fqcn in engine.fqcn_index.alias_index.items():
            prefix = f"{vk_name}:"
            if not alias_fqcn.startswith(prefix):
                continue
            alias_short = alias_fqcn[len(prefix):]
            rows.append((alias_fqcn, canonical_fqcn, alias_short))
    else:
        # Fallback: derive from manifest directly
        for canonical_fqcn in tools:
            alias_short = (name_rewrite.get(canonical_fqcn)
                           or canonical_fqcn.rsplit(":", 1)[-1])
            rows.append((f"{vk_name}:{alias_short}", canonical_fqcn, alias_short))

    if not rows:
        print("  No aliases declared in this virtual kit.")
        return 0

    rows.sort(key=lambda r: r[2])  # sort by alias short

    # Build project lookup for descriptions
    by_fqcn = {p.fqcn: p for p in projects if p.fqcn}

    # Column widths
    alias_width = max(len(r[0]) for r in rows)
    alias_width = max(alias_width, len("Alias FQCN"))
    target_width = max(len(r[1]) for r in rows)
    target_width = max(target_width, len("-> Canonical"))

    header = (f"  {'Alias FQCN':<{alias_width}}  "
              f"{'-> Canonical':<{target_width}}  Description")
    print(header)
    print("  " + "-" * (len(header) - 2))

    term_width = _term_width()
    desc_col = 2 + alias_width + 2 + target_width + 2
    desc_max = term_width - desc_col

    for alias_fqcn, canonical_fqcn, _alias_short in rows:
        target_project = by_fqcn.get(canonical_fqcn)
        desc = ((target_project.description or "") if target_project
                else "(canonical not discovered)")
        wrapped = _wrap_description(desc, desc_max)
        arrow_target = f"-> {canonical_fqcn}"
        print(f"  {alias_fqcn:<{alias_width}}  "
              f"{arrow_target:<{target_width}}  {wrapped[0]}")
        indent = " " * desc_col
        for line in wrapped[1:]:
            print(f"{indent}{line}")

    print(f"\n  {len(rows)} alias(es) -> canonical tools")
    return 0


def _render_kit_list_legacy(args, kits, projects) -> int:
    """The historical engine-less rendering, preserved byte-for-byte for
    direct callers that don't pass ``engine`` (acceptance A2 of the
    unification DWP)."""
    # v0.7.37: kit names BOLD, "(always active)" annotation DIM,
    # cross-platform/specific platform values differentiated via DIM/plain.
    _use_color = _colors.should_use_color()

    def _bold(s):
        return _colors.colorize(s, _colors.BOLD) if _use_color else s

    def _dim(s):
        return _colors.colorize(s, _colors.DIM) if _use_color else s

    kit_name = getattr(args, "name", None)

    if kit_name:
        matching = [
            k for k in kits
            if (k.kit_name or k.name) == kit_name
        ]
        if not matching:
            print(f"Kit {kit_name!r} not found. Available kits:")
            for k in kits:
                print(f"  {k.kit_name or k.name}")
            return 1

        kit = matching[0]
        name = kit.kit_name or kit.name
        active = _dim(" (always active)") if kit.always_active else ""
        print(f"Kit: {_bold(name)}{active}")
        if kit.description:
            print(f"  {kit.description}")
        print()

        tool_refs = kit.tools or []
        if not tool_refs:
            print("  No tools in this kit.")
            return 0

        for ref in sorted(tool_refs):
            # Modern path: ref is a full FQCN as written by
            # ``engine._discover_aggregator``'s post-recursion populate
            # (e.g., ``dz:core:find``, ``wtf:core:locked``). Match by
            # ``_fqcn`` directly so multi-segment FQCNs resolve.
            match = [p for p in projects if p.fqcn == ref]
            if match:
                # Display the leaf name; the namespace is implicit from kit.
                p = match[0]
                display_name = p.name
            else:
                # Legacy fallback: parse ref as ``ns:name`` for existing
                # kit manifests that use 2-segment refs (e.g.,
                # ``core:find``, ``dazzletools:git``).
                if ":" in ref:
                    ns, name_part = ref.split(":", 1)
                else:
                    ns, name_part = "", ref
                match = [
                    p for p in projects
                    if p.name == name_part
                    and (not ns or p.namespace == ns)
                ]
                display_name = name_part
            if match:
                p = match[0]
                desc = p.description or ""
                # Width-aware truncation budgeted from this row's ACTUAL
                # printed prefix (a long name overflows its column), replacing
                # the hardcoded 55-char cut. One line per tool preserved.
                _rk_used = (2 + max(KIT_NAME_COL, len(display_name)) + 1
                            + KIT_NAME_COL + 1)
                _rk_avail = max(MIN_DESC_WIDTH, _term_width() - _rk_used)
                if len(desc) > _rk_avail:
                    desc = desc[:_rk_avail - 3] + "..."
                platform = p.platform or ""
                # DIM "cross-platform"; leave OS-specific values plain so
                # they stand out (windows / linux / macos).
                platform_styled = (
                    _dim(f"{platform:<{KIT_NAME_COL}}")
                    if _use_color and platform == "cross-platform"
                    else f"{platform:<{KIT_NAME_COL}}"
                )
                print(f"  {display_name:<{KIT_NAME_COL}} {platform_styled} {desc}")
            else:
                print(f"  {display_name:<{KIT_NAME_COL}} {'':{KIT_NAME_COL}} "
                      f"{_dim('(not found)')}")
        print(f"\n  {len(tool_refs)} tool(s)")
        return 0

    # No kit name — list all kits
    for i, kit in enumerate(kits):
        if i > 0:
            print()
        name = kit.kit_name or kit.name
        active = _dim(" (always active)") if kit.always_active else ""
        tool_count = len(kit.tools or [])
        print(f"  {_bold(f'{name:<{KIT_NAME_COL}}')} {tool_count} tool(s){active}")
        if kit.description:
            # Word-wrap the kit description to terminal width with the
            # 4-space hanging indent (the render_list discipline; was an
            # unwrapped line the terminal broke mid-word).
            _ks_avail = max(
                MIN_DESC_WIDTH, _term_width() - SUMMARY_INDENT)
            for _ks_line in _wrap_description(kit.description, _ks_avail):
                print(f"    {_ks_line}")
    return 0


def render_kit_status(active_kits) -> int:
    """Show a summary of the active kits.

    ``active_kits`` is the already-resolved active set (e.g.
    ``engine.active_kits``, which honors ``active_kits`` / ``disabled_kits``
    config); every kit passed is shown. The resolution lives in the handler
    so this stays a pure renderer.
    """
    _use_color = _colors.should_use_color()

    def _bold(s):
        return _colors.colorize(s, _colors.BOLD) if _use_color else s

    active = list(active_kits)
    print(f"Active kits: {len(active)}")
    for kit in active:
        name = kit.kit_name or kit.name
        tool_count = len(kit.tools or [])
        print(f"  {_bold(name)}: {tool_count} tool(s)")
    return 0


def kit_list_handler(args, engine, projects, kits, project_root) -> int:
    # Pass the engine through (the renderer-contract convention): unlocks
    # config-aware status, #48 drill-in columns, and the virtual-kit alias
    # drill-in for every consumer.
    return render_kit_list(args, kits, projects, engine=engine)


def kit_status_handler(args, engine, projects, kits, project_root) -> int:
    # Use the engine's config-resolved active set (active_kits/disabled_kits),
    # matching `kit list`; fall back to all discovered kits if unavailable.
    active = getattr(engine, "active_kits", None)
    if active is None:
        active = kits
    return render_kit_status(active)


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
    p.add_argument(
        "--show-hidden", action="store_true",
        help="Include tools hidden via the 'hidden_tools' config (still dispatchable).",
    )
    p.add_argument(
        "--show-empty", action="store_true",
        help="Include enabled kits that have no tools (shown as childless branches).",
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
        print(
            _colors.error("Error: tree requires engine context"),
            file=_sys.stderr,
        )
        return 1

    as_json = getattr(args, "json", False)
    depth_limit = getattr(args, "depth", None)
    kit_filter = getattr(args, "kit", None)
    show_disabled = getattr(args, "show_disabled", False)
    show_empty = getattr(args, "show_empty", False)

    # Build the hierarchical view from the appropriate project list.
    # --show-disabled uses all_projects (includes disabled kits' tools);
    # default uses the supplied projects (typically engine.projects, active only).
    if show_disabled:
        projects = getattr(engine, "all_projects", projects)

    # Hidden tools: render-only filter (stays dispatchable; omitted from the
    # tree). Revealed by --show-hidden. No-op when hidden_tools is empty.
    if engine is not None:
        projects = engine.filter_hidden(
            projects, reveal=getattr(args, "show_hidden", False)
        )

    by_kit: dict[str, list] = {}
    for project in projects:
        kit_name = project.kit_import_name or "?"
        by_kit.setdefault(kit_name, []).append(project)

    # Build a kit info dict for metadata (always_active, is_aggregator).
    # Aggregator detection: a kit whose directory contains its own ``kits/``
    # subdir is itself an aggregator (e.g., wtf-windows imported under dz).
    import os as _os
    kit_info: dict[str, dict] = {}
    tools_dir = getattr(engine, "tools_dir", "tools")
    proj_root = getattr(engine, "project_root", project_root) or ""
    for kit in getattr(engine, "kits", []):
        name = kit.kit_name or kit.name
        if not name:
            continue
        tools_path = _os.path.join(proj_root, tools_dir)
        candidate_root = _os.path.join(tools_path, name)
        is_aggregator = _os.path.isdir(_os.path.join(candidate_root, "kits"))
        kit_info[name] = {
            "always_active": bool(kit.always_active),
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

    # --show-empty: include enabled kits with NO discovered tools as childless
    # branches (consistent with `dz kit list`, which always lists them). Default
    # off -- the tree stays tool-centric. Virtual + pointer kits have their own
    # branches below, so skip them here. A detached kit round-trips symmetrically:
    # detach -> [pointer] branch (--show-disabled); attach -> childless branch
    # (--show-empty) when it has no tools.
    if show_empty:
        for _k in getattr(engine, "kits", []):
            _kn = _k.kit_name or _k.name
            if _kn and not _k.virtual and not getattr(_k, "pointer", None):
                by_kit.setdefault(_kn, [])

    kit_names = sorted(by_kit.keys())
    if kit_filter:
        kit_names = [k for k in kit_names if k == kit_filter]
        if not kit_names:
            print(
                _colors.error(f"Error: kit {kit_filter!r} not found."),
                file=_sys.stderr,
            )
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
            for project in sorted(by_kit[kit_name], key=lambda p: p.fqcn or ""):
                tools_data.append({
                    "fqcn": project.fqcn or "",
                    "short": project.short_name or project.name or "",
                    "description": project.description or "",
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
    # v0.7.37: gate ANSI on once per call. Kit names get BOLD emphasis;
    # markers (virtual/aggregator/disabled/always_active) get DIM;
    # shadow markers get BOLD+RED (consistency with render_list).
    _use_color = _colors.should_use_color()

    def _bold(s):
        return _colors.colorize(s, _colors.BOLD) if _use_color else s

    def _dim(s):
        return _colors.colorize(s, _colors.DIM) if _use_color else s

    def _shadow(s):
        return _colors.colorize(s, _colors.BOLD, _colors.RED) if _use_color else s

    header = getattr(engine, "command", "root")
    if getattr(engine, "version_info", None):
        display, _ = engine.version_info
        name = getattr(engine, "name", "")
        header = f"{engine.command} ({name} {display})"
    print(_bold(header))

    # Virtual kits appear as separate top-level branches with -> arrows
    # to their canonical targets. Collect them from engine.kits (which
    # includes both canonical and virtual after Phase 4e).
    virtual_kits = [
        k for k in getattr(engine, "kits", [])
        if k.virtual and (
            show_disabled or
            _kit_state(k.kit_name or k.name) not in ("disabled", "disabled (not in active_kits)")
        )
    ]
    # Respect --kit filter for virtual kits too
    if kit_filter:
        virtual_kits = [
            k for k in virtual_kits
            if (k.kit_name or k.name) == kit_filter
        ]

    # Pointer (detached) kits: declared-but-not-materialized -- they carry a
    # `pointer` block (written by `dz kit detach`) and load NO tools (the engine
    # LOADING-skip partition), so they never appear in `by_kit`. Surface them as
    # their own leaf branches (like virtual kits) so `dz tree` shows what's
    # detached. Detach implies disable, so by default they're hidden unless
    # --show-disabled (consistent with how disabled kits are filtered).
    pointer_kits = [
        k for k in getattr(engine, "kits", [])
        if getattr(k, "pointer", None) and not k.virtual and (
            show_disabled or
            _kit_state(k.kit_name or k.name)
            not in ("disabled", "disabled (not in active_kits)")
        )
    ]
    if kit_filter:
        pointer_kits = [
            k for k in pointer_kits
            if (k.kit_name or k.name) == kit_filter
        ]

    total_tools = 0
    total_aliases = 0
    all_branches = len(kit_names) + len(virtual_kits) + len(pointer_kits)
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
        marker_plain = f" [{', '.join(markers)}]" if markers else ""
        marker_str = _dim(marker_plain) if marker_plain else ""

        print(f"{kit_prefix}{_bold(kit_name)}{marker_str}")

        tools = sorted(by_kit[kit_name], key=lambda p: p.fqcn or "")
        total_tools += len(tools)

        if depth_limit is not None and depth_limit < 2:
            continue

        branch_indent = "    " if is_last_branch else "|   "
        for j, project in enumerate(tools):
            is_last_tool = (j == len(tools) - 1)
            tool_prefix = "\\-- " if is_last_tool else "+-- "
            fqcn = project.fqcn or project.name or ""
            desc = project.description or ""
            # Shadow marker: tools whose short name is reserved by a
            # meta-command are flagged in tree output (per issue #56).
            # BOLD+RED to draw attention, consistent with render_list [*].
            short = project.name or ""
            shadowed = bool(short and short in reserved)
            shadow_marker = _shadow(" [shadowed]") if shadowed else ""
            # Truncate the description to the REAL terminal width (was a
            # hard 57-char cut that wasted wide terminals).
            _tr_term_width = _term_width()
            _tr_used = (len(branch_indent) + len(tool_prefix) + len(fqcn)
                        + (len(" [shadowed]") if shadowed else 0) + 2)
            _tr_avail = max(MIN_DESC_WIDTH, _tr_term_width - _tr_used)
            if len(desc) > _tr_avail:
                desc = desc[:_tr_avail - 3] + "..."
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
        vk_name = vkit.kit_name or vkit.name
        state = _kit_state(vk_name)

        markers = ["virtual"]
        if vkit.always_active:
            markers.append("always_active")
        if "disabled" in state:
            markers.append("disabled")
        marker_plain = f" [{', '.join(markers)}]"
        marker_str = _dim(marker_plain)
        print(f"{kit_prefix}{_bold(vk_name)}{marker_str}")

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
            # Virtual-kit aliases point at canonical FQCNs; DIM the arrow
            # so the alias-target pair reads as one logical element.
            arrow = _dim("->") if _use_color else "->"
            print(f"{branch_indent}{tool_prefix}{alias_fqcn} {arrow} {canonical_fqcn}")

    # Pointer (detached) kit branches -- leaf nodes (no tools to render). The
    # [pointer] marker is YELLOW (caution); a trailing dim [disabled] notes the
    # cascade (detach implies disable).
    for pkit in pointer_kits:
        branch_idx += 1
        is_last_branch = (branch_idx == all_branches)
        kit_prefix = "\\-- " if is_last_branch else "+-- "
        pk_name = pkit.kit_name or pkit.name
        state = _kit_state(pk_name)
        ptr_marker = (
            _colors.colorize("[pointer]", _colors.YELLOW)
            if _use_color else "[pointer]"
        )
        dis = _dim(" [disabled]") if "disabled" in state else ""
        print(f"{kit_prefix}{_bold(pk_name)} {ptr_marker}{dis}")

    print()
    summary = f"{total_tools} tools across {len(kit_names)} kit(s)"
    if total_aliases:
        summary += (
            f", {total_aliases} alias(es) in {len(virtual_kits)} virtual kit(s)"
        )
    if pointer_kits:
        summary += f", {len(pointer_kits)} detached pointer kit(s)"
    print(summary)
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
        setup = project.setup
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

    with_setup.sort(key=lambda p: p.fqcn or p.name or "")
    longest = max(
        len(p.fqcn or p.name or "") for p in with_setup
    )
    col_width = max(20, min(50, longest))

    print("Tools with setup declared:\n")
    for project in with_setup:
        fqcn = project.fqcn or project.name or ""
        setup = project.setup or {}
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
    # Advisories (tool-not-found, no-setup) use warn() -> YELLOW.
    # Genuine error paths (override-file parse/read failures) use error() -> BRIGHT_RED.
    project, ctx = engine.find_project(tool_name)
    if project is None:
        print(_colors.warn(f"Tool {tool_name!r} not found."), file=_sys.stderr)
        return 1
    matches = [project]

    if len(matches) > 1:
        print(_colors.warn(f"Multiple tools named {tool_name!r}:"), file=_sys.stderr)
        for p in matches:
            print(f"  {p.fqcn or p.name}", file=_sys.stderr)
        return 1

    project = matches[0]
    setup = project.setup
    if not setup:
        print(
            _colors.warn(
                f"Tool {project.fqcn or project.name!r} has no setup declared."
            ),
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
            _colors.error(f"Error: user override file is not valid JSON: {exc}"),
            file=_sys.stderr,
        )
        return 1
    except OSError as exc:
        print(
            _colors.error(f"Error: cannot read user override file: {exc}"),
            file=_sys.stderr,
        )
        return 1
    except Exception as exc:
        print(_colors.error(f"Error resolving setup: {exc}"), file=_sys.stderr)
        return 1

    if resolved is None:
        print(
            _colors.warn(
                f"Tool {project.fqcn or project.name!r} has no executable setup."
            ),
            file=_sys.stderr,
        )
        return 1

    command = resolved.get("command")
    if not command:
        print(
            _colors.warn(
                f"Tool {project.fqcn or project.name!r} has no setup command "
                f"for this platform."
            ),
            file=_sys.stderr,
        )
        return 1

    # Execute the resolved command. The engine is a dumb dispatcher —
    # we run the author-declared command via the platform shell.
    import subprocess as _subprocess

    print(f"Running setup for {project.fqcn or project.name}...")
    print(f"  {command}")
    _sys.stdout.flush()  # flush before subprocess to avoid output interleaving

    result = _subprocess.run(command, shell=True, cwd=project.directory)
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
