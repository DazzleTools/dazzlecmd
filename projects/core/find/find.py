"""
find - Cross-platform file search powered by fd

Wraps fd (sharkdp/fd) with dazzlecmd-style actions: open files,
browse in file manager, or copy paths to clipboard. Provides a
consistent interface across Windows, Linux, macOS, and BSD.

Requires fd to be installed:
  Windows:  winget install sharkdp.fd
  macOS:    brew install fd
  Linux:    apt install fd-find
  BSD:      pkg install fd
"""

import argparse
import os
import shutil
import subprocess
import sys


# -- fd binary detection --

def find_fd():
    """Find the fd binary on the system.

    Returns the path to fd, or None if not found.
    On Debian/Ubuntu, fd-find installs as 'fdfind' due to a naming conflict.
    """
    for name in ("fd", "fdfind"):
        path = shutil.which(name)
        if path:
            return path
    return None


def print_install_instructions():
    """Print platform-specific fd install instructions."""
    print("Error: fd is not installed.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install fd for your platform:", file=sys.stderr)
    if sys.platform == "win32":
        print("  winget install sharkdp.fd", file=sys.stderr)
        print("  choco install fd", file=sys.stderr)
    elif sys.platform == "darwin":
        print("  brew install fd", file=sys.stderr)
    else:
        print("  apt install fd-find    (Debian/Ubuntu)", file=sys.stderr)
        print("  pacman -S fd           (Arch)", file=sys.stderr)
        print("  pkg install fd         (FreeBSD)", file=sys.stderr)
    print("", file=sys.stderr)
    print("See https://github.com/sharkdp/fd#installation", file=sys.stderr)


# -- Actions (shared pattern with fixpath) --

def action_open(path):
    """Open file in default application."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return 0
    except OSError as exc:
        print(f"Error: Could not open: {exc}", file=sys.stderr)
        return 1


def action_lister(path):
    """Open containing folder, selecting the file if possible."""
    try:
        if sys.platform == "win32":
            if os.path.isdir(path):
                subprocess.run(["explorer", path], check=False)
            else:
                subprocess.run(["explorer", "/select,", path], check=False)
        elif sys.platform == "darwin":
            if os.path.isdir(path):
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["open", "-R", path], check=False)
        else:
            target_dir = path if os.path.isdir(path) else os.path.dirname(path)
            subprocess.run(["xdg-open", target_dir], check=False)
        return 0
    except OSError as exc:
        print(f"Error: Could not open folder: {exc}", file=sys.stderr)
        return 1


def action_copy(path):
    """Copy path string to system clipboard."""
    try:
        from teeclip.clipboard import ClipboardBackend
        backend = ClipboardBackend()
        backend.copy(path.encode("utf-8"))
        return 0
    except ImportError:
        pass
    except Exception:
        pass

    # Platform fallbacks
    try:
        if sys.platform == "win32":
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            p.communicate(path.encode("utf-16-le"))
            return 0 if p.returncode == 0 else 1
        elif sys.platform == "darwin":
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(path.encode("utf-8"))
            return 0 if p.returncode == 0 else 1
        else:
            for cmd in [
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["wl-copy"],
            ]:
                try:
                    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    p.communicate(path.encode("utf-8"))
                    if p.returncode == 0:
                        return 0
                except FileNotFoundError:
                    continue
            print("Warning: No clipboard tool found.", file=sys.stderr)
            return 1
    except OSError as exc:
        print(f"Error: Clipboard failed: {exc}", file=sys.stderr)
        return 1


# -- fd invocation --

def build_fd_command(fd_path, pattern, paths, args):
    """Build the fd command line from our arguments."""
    cmd = [fd_path]

    # Search mode: glob by default (more intuitive), regex with --regex
    if args.regex:
        # fd uses regex by default, so no flag needed
        pass
    else:
        cmd.append("--glob")

    # Case sensitivity
    if args.case_sensitive:
        cmd.append("--case-sensitive")
    else:
        cmd.append("--ignore-case")

    # Hidden files
    if args.hidden:
        cmd.append("--hidden")

    # No ignore (.gitignore)
    if args.no_ignore:
        cmd.append("--no-ignore")

    # Depth
    if args.depth is not None:
        cmd.extend(["--max-depth", str(args.depth)])

    # Type filter
    if args.type:
        cmd.extend(["--type", args.type])

    # Extension filter
    if args.extension:
        cmd.extend(["--extension", args.extension])

    # Size filter
    if args.size:
        cmd.extend(["--size", args.size])

    # Date filters
    if args.newer:
        cmd.extend(["--changed-within", args.newer])
    if args.older:
        cmd.extend(["--changed-before", args.older])

    # Exclude patterns
    for exc in (args.exclude or []):
        cmd.extend(["--exclude", exc])

    # Absolute paths (needed for actions to work correctly)
    cmd.append("--absolute-path")

    # Pattern (if provided and non-empty)
    if pattern:
        cmd.append(pattern)

    # Search paths -- use --search-path to avoid ambiguity with pattern
    if paths:
        for p in paths:
            cmd.extend(["--search-path", p])

    return cmd


def run_fd(cmd):
    """Run fd and return the list of result paths."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode not in (0, 1):
            # fd returns 1 when no results found, that's not an error
            if result.stderr.strip():
                print(f"fd error: {result.stderr.strip()}", file=sys.stderr)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return lines
    except subprocess.TimeoutExpired:
        print("Error: Search timed out after 5 minutes.", file=sys.stderr)
        return []
    except FileNotFoundError:
        print_install_instructions()
        return []


# -- Result handling --

def select_result(results, interactive=True):
    """When multiple results found, let user pick or return first/all."""
    if not results:
        return []
    if len(results) == 1:
        return results

    if not interactive or not sys.stdin.isatty():
        return results

    print(f"\n  Found {len(results)} matches:", file=sys.stderr)
    for i, path in enumerate(results[:20], 1):
        print(f"  {i:3d}. {path}", file=sys.stderr)
    if len(results) > 20:
        print(f"  ... and {len(results) - 20} more", file=sys.stderr)

    print(f"\n  Select [1-{min(len(results), 20)}, all, cancel]: ",
          end="", file=sys.stderr, flush=True)
    try:
        choice = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return []

    if choice == "cancel" or choice == "":
        return []
    if choice == "all":
        return results
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(results):
            return [results[idx]]
    except ValueError:
        pass

    print("Invalid selection.", file=sys.stderr)
    return []


# -- CLI --

def build_parser():
    """Build argument parser for find."""
    parser = argparse.ArgumentParser(
        prog="dz find",
        description="Cross-platform file search powered by fd",
        epilog="""\
examples:
  dz find README.md                     Find a specific file
  dz find "*.md" --dir docs             Find markdown files in docs/
  dz find "*.py" --count                Count all Python files
  dz find -e json --dir kits            Find by extension in a directory
  dz find "*postmortem*" -o             Find and open in default app
  dz find "*.log" -d 2                  Search only 2 levels deep
  dz find "*.tmp" --older 7d            Files older than 7 days
  dz find "*.py" -S +1M                 Python files larger than 1MB
  dz find --regex "test_.*\\.py$"       Use regex instead of glob
  dz find "*.md" -c                     Find and copy path to clipboard
  dz find "*.md" --dir ~/code -l        Find and browse in file manager
  dz find -e py -E node_modules         Exclude a directory
  dz find --check                       Verify fd is installed

requires fd: https://github.com/sharkdp/fd""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "pattern", nargs="?", default="",
        help="Search pattern (glob by default, regex with --regex)",
    )
    parser.add_argument(
        "--dir", dest="paths", action="append", default=None,
        help="Directory to search (repeatable, default: current directory)",
    )

    # Actions
    actions = parser.add_argument_group("actions")
    actions.add_argument(
        "-o", "--open", dest="action_open", action="store_true",
        help="Open first result in default application",
    )
    actions.add_argument(
        "-l", "--lister", dest="action_lister", action="store_true",
        help="Open containing folder of first result",
    )
    actions.add_argument(
        "-c", "--copy", dest="action_copy", action="store_true",
        help="Copy result path(s) to clipboard",
    )

    # Search options
    search = parser.add_argument_group("search options")
    search.add_argument(
        "--regex", action="store_true",
        help="Use regex instead of glob for pattern matching",
    )
    search.add_argument(
        "--case-sensitive", action="store_true",
        help="Case-sensitive search (default: case-insensitive)",
    )
    search.add_argument(
        "-H", "--hidden", action="store_true",
        help="Include hidden files and directories",
    )
    search.add_argument(
        "--no-ignore", action="store_true",
        help="Don't respect .gitignore rules",
    )
    search.add_argument(
        "-d", "--depth", type=int, default=None,
        help="Maximum search depth",
    )
    search.add_argument(
        "-t", "--type", choices=["f", "file", "d", "dir", "l", "symlink"],
        help="Filter by type: file, dir, symlink",
    )
    search.add_argument(
        "-e", "--extension",
        help="Filter by file extension (e.g., md, py, txt)",
    )
    search.add_argument(
        "-S", "--size",
        help="Filter by size (e.g., +1M, -100k)",
    )
    search.add_argument(
        "--newer",
        help="Files changed within duration/date (e.g., 1week, 2026-03-01)",
    )
    search.add_argument(
        "--older",
        help="Files changed before duration/date",
    )
    search.add_argument(
        "-E", "--exclude", action="append",
        help="Exclude pattern (repeatable)",
    )

    # Output
    output = parser.add_argument_group("output options")
    output.add_argument(
        "--first", action="store_true",
        help="Act on first result only (skip selection)",
    )
    output.add_argument(
        "--all", dest="act_all", action="store_true",
        help="Act on all results (skip selection)",
    )
    output.add_argument(
        "--count", action="store_true",
        help="Print count of matches only",
    )
    output.add_argument(
        "--check", action="store_true",
        help="Check if fd is installed and show version",
    )

    return parser


def main(argv=None):
    """Entry point for find."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    # --check: verify fd installation
    if args.check:
        return _check_fd()

    # Find fd binary
    fd_path = find_fd()
    if not fd_path:
        print_install_instructions()
        return 1

    # Build and run fd command
    cmd = build_fd_command(fd_path, args.pattern, args.paths, args)
    results = run_fd(cmd)

    if not results:
        if args.pattern:
            print(f"  No matches for: {args.pattern}", file=sys.stderr)
        return 1

    # --count mode
    if args.count:
        print(len(results))
        return 0

    # Determine which results to act on
    has_action = args.action_open or args.action_lister or args.action_copy
    if args.first or (has_action and not args.act_all):
        selected = [results[0]]
    elif args.act_all or not has_action:
        selected = results
    else:
        selected = select_result(results, interactive=has_action)

    if not selected:
        return 0

    # Print results (always, even with actions)
    for path in selected:
        print(path)

    # Execute actions
    exit_code = 0
    if args.action_copy:
        # Copy all selected paths (newline-separated)
        copy_text = "\n".join(selected) if len(selected) > 1 else selected[0]
        rc = action_copy(copy_text)
        if rc != 0:
            exit_code = rc

    if args.action_open:
        rc = action_open(selected[0])
        if rc != 0:
            exit_code = rc

    if args.action_lister:
        rc = action_lister(selected[0])
        if rc != 0:
            exit_code = rc

    return exit_code


def _check_fd():
    """Check fd installation and print version."""
    fd_path = find_fd()
    if not fd_path:
        print_install_instructions()
        return 1

    try:
        result = subprocess.run([fd_path, "--version"], capture_output=True, text=True)
        version = result.stdout.strip()
        print(f"  fd found: {fd_path}")
        print(f"  version:  {version}")
        return 0
    except OSError as exc:
        print(f"Error: fd found at {fd_path} but failed to run: {exc}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
