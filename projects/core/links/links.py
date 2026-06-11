"""
links - Detect and display filesystem links

Cross-platform tool that scans directories for all types of filesystem links
and shortcuts, and displays them with their targets and status.

Detected types:
  symlink     - Symbolic links (file or directory)
  junction    - Windows junctions (directory reparse points)
  hardlink    - Hard links (multiple directory entries for same inode)
  shortcut    - Windows .lnk Shell Link files
  urlshortcut - .url Internet Shortcut files (web resources, URIs)
  dazzlelink  - .dazzlelink JSON descriptor files

This is the thin CLI over the constitutional engine
``dazzlecmd_lib.core.links`` (the same engine/CLI split as the safedel tool):
the ENGINE (detection, classification, scanning -- returns data) lives in the
library, because lib code itself needs it (mode switching, safedel's
link-aware classifier); this file owns only dz-territory concerns -- argument
parsing, table/JSON display, exit codes. Until 2026-06-11 this file carried
its own verbatim copy of the engine (the links-fork DWP); defining engine
logic here again is a contract violation caught by the lib's
``test_constitutional_contract.py``.
"""

import argparse
import json
import os
import sys

from dazzlecmd_lib.core.links import (
    ALL_LINK_TYPES,
    LINK_HARDLINK,
    canonicalize_path,
    detect_link,
    matches_filter,
    scan_directory,
)


# -- Display --

def shorten_path(path):
    """Shorten a path by replacing the home directory with ~."""
    home = os.path.expanduser("~")
    if path and os.path.normcase(path).startswith(os.path.normcase(home)):
        return "~" + path[len(home):]
    return path


def display_table(links, verbose=False):
    """Display links in table format."""
    link_list = list(links)
    if not link_list:
        print("  No links found.")
        return

    for info in link_list:
        status = "[BROKEN]" if info.broken else ""
        target_str = ""
        if info.target:
            target_str = f" -> {shorten_path(info.target)}"
        count_str = ""
        if info.link_type == LINK_HARDLINK and info.link_count > 1:
            count_str = f"  ({info.link_count} links)"

        suffix = "/"  if info.is_dir else ""
        print(f"  {info.name}{suffix:<1}  {info.link_type:<12}{target_str}{count_str}  {status}")

        if verbose:
            print(f"    path:    {info.path}")
            if info.target:
                print(f"    target:  {info.target}")
            print(f"    type:    {info.link_type}")
            if info.link_type == LINK_HARDLINK:
                print(f"    links:   {info.link_count}")
            if info.inode:
                print(f"    inode:   {info.inode}")
            print(f"    size:    {info.size} bytes")
            print()

    # Summary
    type_counts = {}
    broken_count = 0
    for info in link_list:
        type_counts[info.link_type] = type_counts.get(info.link_type, 0) + 1
        if info.broken:
            broken_count += 1

    parts = [f"{count} {ltype}" for ltype, count in sorted(type_counts.items())]
    summary = f"\n  {len(link_list)} link(s) found: {', '.join(parts)}"
    if broken_count:
        summary += f"  ({broken_count} broken)"
    print(summary)


def display_json(links):
    """Display links as JSON."""
    link_list = [info.to_dict() for info in links]
    print(json.dumps(link_list, indent=2))


# -- CLI --

def build_parser():
    """Build argument parser for links."""
    parser = argparse.ArgumentParser(
        prog="dz links",
        description="Detect and display filesystem links",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."],
        help="Files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true",
        help="Scan directories recursively",
    )
    parser.add_argument(
        "-d", "--depth", type=int, default=None,
        help="Maximum depth for recursive scan (implies -r)",
    )
    parser.add_argument(
        "--type", "-t", dest="link_type",
        help=f"Filter by link type: {', '.join(ALL_LINK_TYPES)} (comma-separated)",
    )
    parser.add_argument(
        "--broken", "-b", action="store_true",
        help="Show only broken links",
    )
    parser.add_argument(
        "--json", "-j", dest="json_output", action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show detailed info (inode, size, full paths)",
    )
    return parser


def main(argv=None):
    """Entry point for links."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    # Parse type filter
    type_filter = None
    if args.link_type:
        requested = [t.strip().lower() for t in args.link_type.split(",")]
        invalid = [t for t in requested if t not in ALL_LINK_TYPES]
        if invalid:
            print(f"Error: Unknown link type(s): {', '.join(invalid)}", file=sys.stderr)
            print(f"Valid types: {', '.join(ALL_LINK_TYPES)}", file=sys.stderr)
            return 1
        type_filter = set(requested)

    # --depth implies --recursive
    recursive = args.recursive or args.depth is not None

    # Collect links from all paths
    all_links = []
    for path in args.paths:
        path = canonicalize_path(path)
        if os.path.isdir(path):
            all_links.extend(
                scan_directory(path, recursive=recursive,
                               type_filter=type_filter, broken_only=args.broken,
                               max_depth=args.depth)
            )
        elif os.path.exists(path) or os.path.islink(path):
            info = detect_link(path)
            if info and matches_filter(info, type_filter, args.broken):
                all_links.append(info)
        else:
            print(f"Warning: Path not found: {path}", file=sys.stderr)

    # Display
    if args.json_output:
        display_json(all_links)
    else:
        display_table(all_links, verbose=args.verbose)

    return 0


if __name__ == "__main__":
    sys.exit(main())
