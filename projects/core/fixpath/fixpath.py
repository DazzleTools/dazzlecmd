"""
fixpath - Fix mangled paths and optionally open, copy, or browse files

Takes paths from terminals, copy-paste, or mixed-OS environments and
canonicalizes them. Handles mixed slashes, cmd.exe prompt artifacts,
MSYS paths, URL encoding, and more. Every mode prints the fixed path
to stdout; action flags add behavior on top.

Modes:
  (default)   Fix path, print to stdout
  --open      Also open file in default application
  --lister    Also open containing folder (select file)
  --copy      Also copy fixed path to clipboard
"""

import argparse
import json
import os
import re
import subprocess
import sys

try:
    from urllib.parse import unquote as url_unquote
except ImportError:
    from urllib import unquote as url_unquote


# -- Configuration --

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".dazzlecmd")
CONFIG_FILE = os.path.join(CONFIG_DIR, "fixpath.json")

DEFAULT_CONFIG = {
    "default_action": "print",
    "lister": None,  # None = OS default (explorer/Finder/xdg-open)
    "search_dirs": None,  # None = CWD only; list of dirs to search
    "search_dirs_mode": "inclusive",  # "inclusive" = add to CWD, "exclusive" = replace
}

VALID_ACTIONS = ["print", "open", "lister", "copy"]

# Known file manager presets -- maps short names to (executable, args_for_file, args_for_dir)
# {path} is replaced with the target path
LISTER_PRESETS = {
    "dopus": {
        "name": "Directory Opus",
        "file": ["{dopusrt}", "/open", "{dir}"],
        "dir": ["{dopusrt}", "/open", "{path}"],
        "detect": [
            r"C:\Program Files\GPSoftware\Directory Opus\dopusrt.exe",
            r"C:\Program Files (x86)\GPSoftware\Directory Opus\dopusrt.exe",
        ],
    },
    "totalcmd": {
        "name": "Total Commander",
        "file": ["{exe}", "/O", "/T", "/L={dir}"],
        "dir": ["{exe}", "/O", "/T", "/L={path}"],
        "detect": [
            r"C:\totalcmd\TOTALCMD64.EXE",
            r"C:\Program Files\totalcmd\TOTALCMD64.EXE",
            r"C:\Program Files (x86)\totalcmd\TOTALCMD.EXE",
        ],
    },
    "explorer": {
        "name": "Windows Explorer",
        "file": ["explorer", "/select,", "{path}"],
        "dir": ["explorer", "{path}"],
        "detect": [],  # Always available on Windows
    },
}


def load_config():
    """Load fixpath config from disk."""
    if not os.path.isfile(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(config)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


def save_config(config):
    """Save fixpath config to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


# -- Path fixing --

_MSYS_DRIVE_RE = re.compile(r"^/([a-zA-Z])/")
_PROMPT_GT_RE = re.compile(r"(?<=[a-zA-Z0-9_.\\\-])>(?=[a-zA-Z0-9_.\\\/ \-])")


def fix_path(raw_path):
    """Fix a mangled path string and return the canonical form.

    Handles:
      Mixed slashes:     C:\\code\\project/file.md
      cmd.exe prompt >:  C:\\code\\project>private/file.md
      MSYS paths:        /c/code/project/file.md
      Extended-length:   \\\\?\\C:\\code\\file.md
      Surrounding chars: "path", 'path', `path`
      URL encoding:      C:/code/my%20project/file.md
      PowerShell prefix: PS C:\\code\\file.md
      Tilde:             ~/code/file.md
      Env vars:          %USERPROFILE%\\file.md, $HOME/file.md
      Trailing prompts:  /path$ , /path#
    """
    if not raw_path:
        return raw_path

    path = raw_path.strip()

    # Strip surrounding quotes and backticks
    if len(path) >= 2:
        if (path[0] == '"' and path[-1] == '"') or \
           (path[0] == "'" and path[-1] == "'") or \
           (path[0] == '`' and path[-1] == '`'):
            path = path[1:-1].strip()

    # Strip PowerShell prompt prefix
    if path.upper().startswith("PS "):
        rest = path[3:].lstrip()
        if rest and (rest[0] in "/\\~" or (len(rest) > 1 and rest[1] == ":")):
            path = rest

    # Strip trailing bash/zsh prompt artifacts
    path = re.sub(r'[\$#]\s*$', '', path)

    # -- UNC detection (before any slash normalization) --
    # Forward-slash UNC: //server/share/...
    if path.startswith("//") and not path.startswith("///"):
        return _fix_unc_path("\\\\" + path[2:].replace("/", "\\"))

    # Standard UNC: \\server\share\...
    if path.startswith("\\\\"):
        # Extended UNC: \\?\UNC\server\share -> \\server\share
        if path.upper().startswith("\\\\?\\UNC\\"):
            path = "\\\\" + path[8:]
        return _fix_unc_path(path)

    # Possible shell-mangled UNC: \server\share (shell ate one backslash)
    # Check as local path first; if it doesn't exist, try UNC reconstruction
    if path.startswith("\\") and not path.startswith("\\\\"):
        # Only consider UNC if it doesn't look like a root-relative path
        # (i.e., no drive letter context, and has at least \something\something)
        parts = path.lstrip("\\").split("\\")
        if len(parts) >= 2 and ":" not in parts[0]:
            local_test = os.path.normpath(path)
            if not os.path.exists(local_test):
                # Doesn't exist as local -- try as UNC
                unc_candidate = "\\" + path
                return _fix_unc_path(unc_candidate)

    # Replace cmd.exe prompt artifact (>) with path separator
    path = _PROMPT_GT_RE.sub(os.sep.replace("\\", "\\\\"), path)

    # URL-decode %XX sequences
    path = url_unquote(path)

    # Expand tilde
    path = os.path.expanduser(path)

    # Expand environment variables
    path = os.path.expandvars(path)

    # Convert WSL /mnt/c/path -> C:\path (before MSYS check)
    wsl_m = re.match(r"^/mnt/([a-zA-Z])(/.*)?$", path)
    if wsl_m:
        drive = wsl_m.group(1).upper()
        rest = wsl_m.group(2) or ""
        path = drive + ":" + rest

    # Convert MSYS /c/path -> C:\path
    m = _MSYS_DRIVE_RE.match(path)
    if m:
        drive = m.group(1).upper()
        path = drive + ":" + path[2:]

    # Normalize slashes to OS native
    path = path.replace("/", os.sep)

    # Strip \\?\ extended-length prefix
    if path.startswith("\\\\?\\"):
        path = path[4:]

    # Try dazzle_filekit for cross-platform resolution (includes probing)
    try:
        from dazzle_filekit import resolve_cross_platform_path
        resolved = resolve_cross_platform_path(path)
        # Ensure absolute path
        if not resolved.is_absolute():
            resolved = resolved.resolve()
        path = str(resolved)
    except ImportError:
        # Fallback: standard normalization
        path = os.path.normpath(path)
        if not os.path.isabs(path):
            path = os.path.abspath(path)

    # If the path doesn't exist, try alternative platform formats
    if not os.path.exists(path):
        alt = _probe_alt_platform(path)
        if alt:
            path = alt

    # Check for MSYS-mangled WSL paths (e.g. C:\Program Files\Git\mnt\c\Users\...)
    if not os.path.exists(path):
        mangled = re.search(r"[/\\]mnt[/\\]([a-zA-Z])[/\\](.*)", path)
        if mangled:
            drive = mangled.group(1).upper()
            rest = mangled.group(2)
            candidate = os.path.normpath(f"{drive}:\\{rest}")
            if os.path.exists(candidate):
                path = candidate

    return path


def _fix_unc_path(path):
    r"""Fix a UNC path (\\server\share\...), preserving the prefix.

    Normalizes slashes, fixes > artifacts, and optionally converts
    to a local drive letter via unctools if a mapping exists.
    """
    # Ensure starts with \\
    if not path.startswith("\\\\"):
        path = "\\\\" + path.lstrip("\\")

    # Fix mixed slashes after the UNC prefix
    prefix = path[:2]
    rest = path[2:].replace("/", "\\")

    # Fix > artifacts in the rest
    rest = re.sub(r"(?<=[a-zA-Z0-9_.\\\-])>(?=[a-zA-Z0-9_.\\\/ \-])", "\\\\", rest)

    path = prefix + rest
    path = os.path.normpath(path)

    # Try unctools to convert to local drive letter (preferred over UNC)
    try:
        from unctools import convert_to_local
        local = convert_to_local(path)
        local_str = str(local)
        # Only use local if it's actually a drive-letter path (not still UNC)
        if local_str != path and not local_str.startswith("\\\\"):
            return local_str
    except ImportError:
        pass

    return path


# Patterns for cross-platform path probing
_WSL_MNT_RE = re.compile(r"^/mnt/([a-zA-Z])(/.*)?$")
_WIN_DRIVE_RE = re.compile(r"^([a-zA-Z]):[/\\](.*)$")


def _probe_alt_platform(path):
    """If a path doesn't exist, try converting between platform formats.

    On Windows: /mnt/c/Users/... -> C:\\Users\\...
    On Linux:   C:\\Users\\...   -> /mnt/c/Users/...  (WSL)
                C:\\Users\\...   -> /c/Users/...       (Git Bash / MSYS)
    """
    # Already exists -- no probing needed
    if os.path.exists(path):
        return None

    if sys.platform == "win32":
        # Try WSL-style /mnt/c/ -> C:\
        m = _WSL_MNT_RE.match(path)
        if m:
            drive = m.group(1).upper()
            rest = (m.group(2) or "").replace("/", "\\")
            candidate = f"{drive}:{rest}"
            if os.path.exists(candidate):
                return candidate

    else:
        # On Linux/macOS: try Windows path -> /mnt/c/ (WSL) or /c/ (MSYS)
        m = _WIN_DRIVE_RE.match(path)
        if m:
            drive = m.group(1).lower()
            rest = m.group(2).replace("\\", "/")

            # Try WSL mount
            candidate = f"/mnt/{drive}/{rest}"
            if os.path.exists(candidate):
                return candidate

            # Try MSYS/Git Bash style
            candidate = f"/{drive}/{rest}"
            if os.path.exists(candidate):
                return candidate

    return None


def _is_bare_filename(path):
    """Check if a string looks like a bare filename (no path separators).

    Also returns True for glob patterns (contain * ? [) even with separators,
    since those are clearly search patterns, not literal paths.
    """
    # Glob patterns are always search candidates
    if any(c in path for c in "*?["):
        return True
    if os.sep in path or "/" in path or "\\" in path:
        return False
    if len(path) > 1 and path[1] == ":":
        return False
    return True


def _search_for_file(pattern, search_dirs, config, max_results=None):
    """Search for a file using fd, with progressive path resolution.

    If the pattern contains path separators (e.g., "some/bad/path/file*.md"),
    walks the path from left to right to find the deepest existing directory,
    then searches from there for the filename portion. Falls back to searching
    configured dirs or CWD.

    Returns list of found paths, or empty list.
    """
    search_pattern, search_roots = _resolve_search_context(
        pattern, search_dirs, config
    )

    if not search_pattern:
        return []

    return _run_fd_search(search_pattern, search_roots, max_results=max_results)


def _resolve_search_context(pattern, search_dirs, config):
    """Determine what to search for and where.

    If the pattern has path separators, progressively walk the path to find
    the deepest existing directory, then use the remainder as the search
    pattern. Otherwise, use configured search dirs or CWD.

    Returns (search_pattern, search_dirs_list).
    """
    # If explicit --dir flags were given, use those with the full pattern
    if search_dirs:
        dirs = [os.path.expanduser(d) for d in search_dirs]
        mode = config.get("search_dirs_mode", "inclusive")
        if mode == "inclusive" and "." not in search_dirs:
            dirs.insert(0, ".")
        # Extract just the filename if pattern has separators
        basename = os.path.basename(pattern)
        return (basename or pattern, dirs)

    # Check if pattern contains path separators
    has_sep = "/" in pattern or "\\" in pattern
    if has_sep:
        # Progressive path resolution: find the deepest existing directory
        resolved_dir, remainder = _progressive_resolve(pattern)
        if resolved_dir:
            # Use just the filename/glob portion for the search pattern,
            # and search from the deepest valid directory
            basename = os.path.basename(remainder)
            return (basename or remainder, [resolved_dir])

        # Nothing resolved -- extract just the filename and search CWD
        basename = os.path.basename(pattern)
        if basename:
            return (basename, _get_default_search_dirs(config))
        return (pattern, _get_default_search_dirs(config))

    # Bare filename or glob -- search configured dirs
    return (pattern, _get_default_search_dirs(config))


def _progressive_resolve(path):
    """Walk a path from left to right, find the deepest existing directory.

    Returns (existing_dir, remaining_pattern) or (None, None) if nothing exists.

    Example:
      "private/claude/badsubdir/postmortem*.md"
      -> tries ./private/claude/badsubdir/ (no)
      -> tries ./private/claude/ (yes!)
      -> returns ("./private/claude", "postmortem*.md")
    """
    # Normalize separators
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")

    # Try progressively shorter prefixes (deepest first)
    for i in range(len(parts) - 1, 0, -1):
        dir_prefix = os.path.join(*parts[:i])
        # Try as-is
        if os.path.isdir(dir_prefix):
            remainder = "/".join(parts[i:])
            return (os.path.abspath(dir_prefix), remainder)
        # Try with CWD
        abs_prefix = os.path.abspath(dir_prefix)
        if os.path.isdir(abs_prefix):
            remainder = "/".join(parts[i:])
            return (abs_prefix, remainder)

    return (None, None)


def _get_default_search_dirs(config):
    """Get the default search directories from config or CWD."""
    configured_dirs = config.get("search_dirs") or []
    mode = config.get("search_dirs_mode", "inclusive")

    dirs = []
    if configured_dirs:
        dirs.extend(configured_dirs)
        if mode == "inclusive" and "." not in configured_dirs:
            dirs.insert(0, ".")
    else:
        dirs.append(".")

    return [os.path.expanduser(d) for d in dirs]


def _run_fd_search(pattern, dirs, max_results=None):
    """Run fd to search for a pattern in the given directories."""
    import shutil as _shutil
    fd_path = _shutil.which("fd") or _shutil.which("fdfind")
    if fd_path:
        cmd = [fd_path, "--glob", "--ignore-case", "--absolute-path",
               "--follow", "--no-ignore", pattern]
        if max_results:
            cmd.extend(["--max-results", str(max_results)])
        for d in dirs:
            cmd.extend(["--search-path", d])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return [l.strip() for l in result.stdout.splitlines() if l.strip()]
        except (subprocess.TimeoutExpired, OSError):
            pass

    print("Warning: fd is not installed. Cannot search for files.", file=sys.stderr)
    print("  Install: https://github.com/sharkdp/fd#installation", file=sys.stderr)
    return []


def _rank_results(results, original_input):
    """Rank search results by similarity to the original input.

    Scores each result by how many path components from the original
    input appear (in order) in the result path. The result with the
    most matching components is the best match.

    Returns results sorted best-first.
    """
    if not results or not original_input:
        return results

    # Normalize the original input into path components (strip globs)
    orig_parts = original_input.replace("\\", "/").split("/")
    # Remove empty parts and glob-only segments
    orig_parts = [p.lower() for p in orig_parts
                  if p and p not in (".", "..") and "*" not in p and "?" not in p]

    if not orig_parts:
        return results

    def score(result_path):
        result_lower = result_path.replace("\\", "/").lower()
        result_parts = result_lower.split("/")

        # Count how many original parts appear in the result (in order)
        matches = 0
        result_idx = 0
        for orig_part in orig_parts:
            for i in range(result_idx, len(result_parts)):
                if result_parts[i] == orig_part:
                    matches += 1
                    result_idx = i + 1
                    break

        # Secondary: prefer shorter paths (less nesting = more direct match)
        length_penalty = len(result_parts) / 1000.0

        return (-matches, length_penalty)

    return sorted(results, key=score)


def _search_and_select(raw_path, args, config):
    """Search for a file and select the best result.

    Returns:
      - The best matching path (string) on success
      - "_all_handled" if --all was used (results already printed/acted on)
      - None if no matches found
    """
    fast = getattr(args, "fast", False)
    max_results = 1 if fast else None

    results = _search_for_file(raw_path, args.search_dirs, config,
                               max_results=max_results)
    if not results:
        if not args.quiet:
            print(f"  No matches for: {raw_path}", file=sys.stderr)
        return None

    # --fast: skip ranking, take what fd gave us
    if not fast:
        results = _rank_results(results, raw_path)

    if args.show_all:
        _handle_all_results(results, args, config)
        return "_all_handled"

    if len(results) > 1 and not args.quiet:
        print(f"  ({len(results)} matches, using best (use --all to see all))",
              file=sys.stderr)

    return results[0]


def _handle_all_results(results, args, config):
    """Handle --all: print all results, but only open/lister the first.

    Copy gets all paths (useful for clipboard). Open/lister would be
    disruptive with many results, so only the first is acted on.
    """
    # Print all results to stdout
    for r in results:
        print(r)
    print(f"\n  {len(results)} match(es)", file=sys.stderr)

    # Copy: all paths (newline-separated)
    if args.action_copy:
        action_copy("\n".join(results))

    # Open/lister: first result only
    if args.action_open:
        action_open(results[0])

    if args.action_lister:
        action_lister(results[0], config=config)


def verify_path(path):
    """Check if a path exists. Returns (exists, path_type)."""
    if os.path.isfile(path):
        return True, "file"
    elif os.path.isdir(path):
        return True, "dir"
    elif os.path.islink(path):
        return True, "link (broken)"
    return False, None


# -- Actions --

def action_open(path):
    """Open file in default application."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except OSError as exc:
        print(f"Error: Could not open: {exc}", file=sys.stderr)
        return 1
    return 0


def action_lister(path, config=None):
    """Open containing folder, selecting the file if possible.

    Uses the configured lister (dopus, totalcmd, explorer, etc.)
    or falls back to OS default.
    """
    lister_name = (config or {}).get("lister")

    # If a preset is configured, use it
    if lister_name and lister_name in LISTER_PRESETS:
        return _run_lister_preset(lister_name, path)

    # If a custom command is configured (not a preset name)
    if lister_name:
        try:
            cmd = [lister_name, path]
            subprocess.run(cmd, check=False)
            return 0
        except OSError as exc:
            print(f"Error: Could not run lister '{lister_name}': {exc}",
                  file=sys.stderr)
            return 1

    # OS default
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
    except OSError as exc:
        print(f"Error: Could not open folder: {exc}", file=sys.stderr)
        return 1
    return 0


def _run_lister_preset(preset_name, path):
    """Run a file manager preset."""
    preset = LISTER_PRESETS[preset_name]

    # Find the executable
    exe_path = None
    for candidate in preset.get("detect", []):
        if os.path.isfile(candidate):
            exe_path = candidate
            break

    if not exe_path and preset_name == "explorer":
        exe_path = "explorer"
    elif not exe_path:
        print(f"Error: {preset['name']} not found at expected locations.",
              file=sys.stderr)
        for loc in preset.get("detect", []):
            print(f"  Checked: {loc}", file=sys.stderr)
        print(f"  Falling back to OS default.", file=sys.stderr)
        return action_lister(path, config={})  # Recurse without lister config

    # Build command
    is_dir = os.path.isdir(path)
    template = preset["dir"] if is_dir else preset["file"]

    target_dir = path if is_dir else os.path.dirname(path)
    target_file = "" if is_dir else os.path.basename(path)

    cmd = []
    for arg in template:
        arg = arg.replace("{path}", path)
        arg = arg.replace("{dir}", target_dir)
        arg = arg.replace("{file}", target_file)
        arg = arg.replace("{exe}", exe_path)
        arg = arg.replace("{dopusrt}", exe_path)
        cmd.append(arg)

    try:
        subprocess.run(cmd, check=False)
        return 0
    except OSError as exc:
        print(f"Error: Could not run {preset['name']}: {exc}", file=sys.stderr)
        return 1


def action_copy(path):
    """Copy path string to system clipboard."""
    # Try teeclip first (handles all platforms)
    try:
        from teeclip.clipboard import ClipboardBackend
        backend = ClipboardBackend()
        backend.copy(path.encode("utf-8"))
        return 0
    except ImportError:
        pass
    except Exception as exc:
        print(f"Warning: teeclip failed: {exc}", file=sys.stderr)

    # Platform-specific fallbacks
    try:
        if sys.platform == "win32":
            process = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            process.communicate(path.encode("utf-16-le"))
            return 0 if process.returncode == 0 else 1
        elif sys.platform == "darwin":
            process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            process.communicate(path.encode("utf-8"))
            return 0 if process.returncode == 0 else 1
        else:
            for cmd in [
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["wl-copy"],
            ]:
                try:
                    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    process.communicate(path.encode("utf-8"))
                    if process.returncode == 0:
                        return 0
                except FileNotFoundError:
                    continue
            print("Warning: No clipboard tool found. "
                  "Install teeclip, xclip, xsel, or wl-clipboard.",
                  file=sys.stderr)
            return 1
    except OSError as exc:
        print(f"Error: Clipboard failed: {exc}", file=sys.stderr)
        return 1


# -- CLI --

def build_parser():
    """Build argument parser for fixpath."""
    parser = argparse.ArgumentParser(
        prog="dz fixpath",
        description="Fix mangled paths and optionally open, copy, or browse files",
        epilog="Use 'dz fixpath config show' to view settings, "
               "'dz fixpath config default <action>' to change the default.",
    )

    parser.add_argument(
        "paths", nargs="*", default=[],
        help="Paths to fix (reads from stdin if none given)",
    )
    parser.add_argument(
        "-p", "--print", dest="action_print", action="store_true",
        help="Print only -- skip default action (overrides config)",
    )
    parser.add_argument(
        "-o", "--open", dest="action_open", action="store_true",
        help="Open file in default application",
    )
    parser.add_argument(
        "-l", "--lister", dest="action_lister", action="store_true",
        help="Open containing folder (select file)",
    )
    parser.add_argument(
        "-c", "--copy", dest="action_copy", action="store_true",
        help="Copy fixed path to clipboard",
    )
    parser.add_argument(
        "-f", "--find", dest="find_mode", action="store_true",
        help="Search for file if path doesn't resolve (uses dz find / fd)",
    )
    parser.add_argument(
        "-s", "--skip", action="store_true",
        help="Skip path fixing, go straight to search (implies --find)",
    )
    parser.add_argument(
        "-d", "--dir", dest="search_dirs", action="append", default=None,
        help="Directory to search when using --find (repeatable)",
    )
    parser.add_argument(
        "--all", dest="show_all", action="store_true",
        help="Show all search results (best match first)",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Take first match immediately (skip ranking, fd stops after 1 result)",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify path exists and show details",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress warnings (still print fixed paths)",
    )

    return parser


def main(argv=None):
    """Entry point for fixpath."""
    if argv is None:
        argv = sys.argv[1:]

    # Handle "config" subcommand before argparse (avoids subparser conflicts)
    if argv and argv[0] == "config":
        return _handle_config(argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config()

    # Determine action(s) -- explicit flags override config default
    # -p means "just print, ignore my config default"
    explicit_action = (args.action_print or args.action_open
                       or args.action_lister or args.action_copy)
    if not explicit_action:
        default = config.get("default_action", "print")
        if default == "open":
            args.action_open = True
        elif default == "lister":
            args.action_lister = True
        elif default == "copy":
            args.action_copy = True

    # --skip and --dir imply --find
    if args.skip or args.search_dirs:
        args.find_mode = True

    # Collect paths from args or stdin
    paths = args.paths
    if not paths:
        if not sys.stdin.isatty():
            paths = [line.strip() for line in sys.stdin if line.strip()]
        else:
            parser.print_help()
            return 0

    # Process each path
    exit_code = 0
    for raw_path in paths:
        # Skip mode: go straight to search
        if args.skip:
            result = _search_and_select(raw_path, args, config)
            if result is None:
                exit_code = 1
                continue
            if result == "_all_handled":
                continue
            fixed = result
        else:
            fixed = fix_path(raw_path)

        exists, _ = verify_path(fixed)

        # Find fallback: if path doesn't exist, search for it.
        # Progressive resolver extracts the filename from paths with
        # separators and finds the deepest valid directory to search from.
        if not exists:
            result = _search_and_select(raw_path, args, config)
            if result == "_all_handled":
                continue
            if result is not None:
                fixed = result
                exists = True

        # Always print to stdout
        print(fixed)

        # Verify if requested
        if args.verify:
            exists, path_type = verify_path(fixed)
            if exists:
                print(f"  [{path_type}] exists", file=sys.stderr)
            else:
                if not args.quiet:
                    print(f"  [not found]", file=sys.stderr)
                exit_code = 1

        # Execute actions
        if args.action_copy:
            rc = action_copy(fixed)
            if rc != 0:
                exit_code = rc

        if args.action_open:
            if exists:
                rc = action_open(fixed)
                if rc != 0:
                    exit_code = rc
            elif not args.quiet:
                print(f"Warning: Cannot open, path not found: {fixed}",
                      file=sys.stderr)
                exit_code = 1

        if args.action_lister:
            if exists or os.path.isdir(os.path.dirname(fixed)):
                rc = action_lister(fixed, config=config)
                if rc != 0:
                    exit_code = rc
            elif not args.quiet:
                print(f"Warning: Cannot browse, path not found: {fixed}",
                      file=sys.stderr)
                exit_code = 1

    return exit_code


def _handle_config(argv):
    """Handle 'dz fixpath config' subcommands."""
    config = load_config()

    if not argv or argv[0] == "help":
        print("dz fixpath config -- manage fixpath settings")
        print()
        print("Usage:")
        print("  dz fixpath config show                Show current settings")
        print("  dz fixpath config default <action>    Set default action")
        print("  dz fixpath config lister <name>       Set preferred file manager")
        print("  dz fixpath config lister --reset      Reset to OS default")
        print()
        print(f"  Valid actions:  {', '.join(VALID_ACTIONS)}")
        print(f"  Valid listers:  {', '.join(LISTER_PRESETS.keys())}")
        print()
        print("  You can also set 'lister' to any executable path for custom file managers.")
        return 0

    if argv[0] == "show":
        lister = config.get("lister") or "(OS default)"
        if config.get("lister") in LISTER_PRESETS:
            lister = f"{config['lister']} ({LISTER_PRESETS[config['lister']]['name']})"
        print(f"  default_action: {config.get('default_action', 'print')}")
        print(f"  lister:         {lister}")
        print(f"  config_file:    {CONFIG_FILE}")
        exists = "exists" if os.path.isfile(CONFIG_FILE) else "not created yet"
        print(f"  status:         {exists}")
        return 0

    if argv[0] == "default":
        if len(argv) < 2:
            print("Usage: dz fixpath config default <action>", file=sys.stderr)
            print(f"Valid actions: {', '.join(VALID_ACTIONS)}", file=sys.stderr)
            return 1
        action = argv[1].lower()
        if action not in VALID_ACTIONS:
            print(f"Error: Unknown action '{action}'", file=sys.stderr)
            print(f"Valid actions: {', '.join(VALID_ACTIONS)}", file=sys.stderr)
            return 1
        config["default_action"] = action
        save_config(config)
        print(f"  default_action set to: {action}")
        return 0

    if argv[0] == "lister":
        if len(argv) < 2:
            print("Usage: dz fixpath config lister <name>", file=sys.stderr)
            print(f"Presets: {', '.join(LISTER_PRESETS.keys())}", file=sys.stderr)
            print("Or provide a path to any file manager executable.", file=sys.stderr)
            return 1
        name = argv[1]
        if name == "--reset":
            config["lister"] = None
            save_config(config)
            print("  lister reset to OS default")
            return 0
        config["lister"] = name
        save_config(config)
        if name in LISTER_PRESETS:
            print(f"  lister set to: {name} ({LISTER_PRESETS[name]['name']})")
        else:
            print(f"  lister set to: {name}")
        return 0

    print(f"Unknown config command: {argv[0]}", file=sys.stderr)
    print("Run 'dz fixpath config help' for usage.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
