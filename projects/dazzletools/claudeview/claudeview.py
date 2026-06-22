"""dz claudeview -- open Claude Code sessions in the history viewer.

Resolves a session query (UUID, path, sesslog folder name, or free-text
title) via csb's session index and launches Claude Code History Viewer
with --session <value> so the viewer opens pre-focused on that session.

    dz claudeview <uuid>                  # full UUID
    dz claudeview <uuid-prefix>           # 8+ hex chars
    dz claudeview <absolute-jsonl-path>   # path to .jsonl
    dz claudeview <sesslog-folder-name>   # NAME__<uuid>_<host>
    dz claudeview <title-or-keyword>      # free-text search
    dz claudeview                         # list recent sessions
"""

import argparse
import os
import platform
import re
import subprocess
import sys


# -- constants --

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){0,3}(?:-[0-9a-fA-F]{1,12})?$")
UUID_PREFIX_RE = re.compile(r"^[0-9a-fA-F-]{8,36}$")
SESSLOG_UUID_RE = re.compile(r"__([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})_")


# -- binary discovery --

def find_viewer():
    """Locate the Claude Code History Viewer — binary or dev-mode project dir.

    Resolution order:
    1. $CLAUDEVIEW_BIN environment variable (explicit binary path)
    2. Platform-specific installed / release binaries
    3. Dev-mode project dir (has package.json; launched via pnpm tauri:dev)
    4. None (caller prints an error)

    Returns a dict: { "mode": "binary"|"dev", "path": <str> }
    or None if nothing found.
    """
    env_bin = os.environ.get("CLAUDEVIEW_BIN")
    if env_bin and os.path.isfile(env_bin):
        return {"mode": "binary", "path": env_bin}

    binary_candidates = []
    dev_candidates = []
    system = platform.system()

    if system == "Windows":
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if localappdata:
            binary_candidates.append(os.path.join(
                localappdata, "Programs",
                "Claude Code History Viewer",
                "Claude Code History Viewer.exe",
            ))
            binary_candidates.append(os.path.join(
                localappdata, "Programs",
                "dazzle-claude-code-history-viewer",
                "dazzle-claude-code-history-viewer.exe",
            ))
        for code_root in [r"C:\code", os.path.expanduser(r"~\code")]:
            for fork_name in ["djdarcy-claude-code-history-viewer", "claude-code-history-viewer"]:
                # Release binaries (preferred -- self-contained)
                binary_candidates.append(os.path.join(
                    code_root, "claude-projects", fork_name,
                    "src-tauri", "target", "release",
                    "claude-code-history-viewer.exe",
                ))
                # Dev project dirs (fallback -- launched via pnpm tauri:dev)
                dev_candidates.append(os.path.join(
                    code_root, "claude-projects", fork_name,
                ))
        binary_candidates.append(r"C:\code-ext\claude-code-history-viewer\src-tauri\target\release\claude-code-history-viewer.exe")
        dev_candidates.append(r"C:\code-ext\claude-code-history-viewer")
    elif system == "Darwin":
        binary_candidates.append("/Applications/Claude Code History Viewer.app/Contents/MacOS/claude-code-history-viewer")
        binary_candidates.append(os.path.expanduser("~/Applications/Claude Code History Viewer.app/Contents/MacOS/claude-code-history-viewer"))
    else:  # Linux
        binary_candidates.append("/usr/bin/claude-code-history-viewer")
        binary_candidates.append(os.path.expanduser("~/.local/bin/claude-code-history-viewer"))

    # Prefer release binaries
    for path in binary_candidates:
        if os.path.isfile(path):
            return {"mode": "binary", "path": path}

    # Fall back to dev-mode project dirs (must have package.json + src-tauri/)
    for path in dev_candidates:
        if (os.path.isfile(os.path.join(path, "package.json"))
                and os.path.isdir(os.path.join(path, "src-tauri"))):
            return {"mode": "dev", "path": path}

    return None


# -- session resolution --

def _get_csb_connection():
    """Open csb's SQLite index. Returns (conn, config) or (None, None)."""
    try:
        from claude_session_backup.config import load_config, resolve_paths
        from claude_session_backup.index import init_schema, open_db
        config = resolve_paths(load_config())
        conn = open_db(config["index_path"])
        init_schema(conn)
        return conn, config
    except (ImportError, Exception) as exc:
        print(f"Warning: csb not available ({exc}). Install with:", file=sys.stderr)
        print("  pip install git+https://github.com/DazzleML/Claude-Session-Backup.git", file=sys.stderr)
        return None, None


def _show_candidates(sessions, query, method_label):
    """Display multiple session candidates using csb's rich timeline format."""
    try:
        from claude_session_backup.timeline import render_timeline_rich
        from rich.console import Console
        console = Console(stderr=True)
        console.print(f"\n  [bold yellow]{len(sessions)}[/bold yellow] sessions match "
                       f"[cyan]'{query}'[/cyan] (via {method_label}):\n")
        render_timeline_rich(sessions, console=console)
        console.print("\n  [dim]Re-run with a UUID prefix to open a specific session.[/dim]")
    except ImportError:
        # Fallback: plain text if rich isn't available
        print(f"\n  {len(sessions)} sessions match '{query}' (via {method_label}):\n", file=sys.stderr)
        for i, s in enumerate(sessions, 1):
            name = s.get("session_name") or "(unnamed)"
            sid = s.get("session_id", "")[:12]
            msgs = s.get("message_count", 0)
            print(f"    {i}. {name}  id: {sid}...  {msgs} messages", file=sys.stderr)
        print(f"\n  Re-run with a UUID prefix to open a specific session.", file=sys.stderr)


def resolve_query(query, conn, config):
    """Resolve a user query to a session dict with jsonl_path.

    Resolution order:
    1. Directory path (including ".") -> folder-usage lookup via csb
    2. Absolute .jsonl path -> follow symlinks, extract UUID
    3. UUID or UUID prefix -> csb get_session (prefix LIKE match)
    4. Sesslog folder name pattern -> extract UUID -> get_session
    5. Free-text -> csb search_sessions (substring match on name/project/folder)

    Returns (session_dict, resolution_method) or (None, reason).
    For multi-match cases, returns (list_of_sessions, "candidates:<label>").
    """
    from claude_session_backup.index import (
        find_sessions_by_folder_usage,
        get_session,
        search_sessions,
    )

    # Normalize "." and relative dirs to absolute path
    resolved_path = os.path.realpath(query) if not os.path.isabs(query) else query

    # 1. Directory path (including ".") -> folder-usage scan
    if os.path.isdir(resolved_path):
        # Check if it's a sesslog directory with embedded UUID first
        m = SESSLOG_UUID_RE.search(os.path.basename(resolved_path))
        if m:
            session = get_session(conn, m.group(1))
            if session:
                return session, "sesslog-dir"
        # Folder-usage scan (like csb scan <path>)
        results = find_sessions_by_folder_usage(conn, resolved_path, limit=10)
        if len(results) == 1:
            return results[0], "folder"
        if len(results) > 1:
            return results, "candidates:folder"
        return None, f"no sessions found that used directory: {resolved_path}"

    # 2. Absolute .jsonl file path
    if os.path.isabs(query) and os.path.exists(query):
        resolved = os.path.realpath(query)
        if resolved.endswith(".jsonl"):
            stem = os.path.splitext(os.path.basename(resolved))[0]
            session = get_session(conn, stem)
            if session:
                return session, "path"
        return None, f"path exists but no matching session found: {query}"

    # 3. UUID or UUID prefix (8+ hex/dash chars)
    if UUID_PREFIX_RE.match(query):
        session = get_session(conn, query)
        if session:
            return session, "uuid"
        return None, f"no session found for UUID/prefix: {query}"

    # 4. Sesslog folder name with embedded UUID
    m = SESSLOG_UUID_RE.search(query)
    if m:
        session = get_session(conn, m.group(1))
        if session:
            return session, "sesslog-name"
        return None, f"UUID extracted from folder name ({m.group(1)}) but no matching session"

    # 5. Free-text search
    results = search_sessions(conn, query, limit=10)
    if len(results) == 1:
        return results[0], "search"
    if len(results) > 1:
        return results, "candidates:search"
    return None, f"no sessions match '{query}'"


def resolve_jsonl_path(session, config):
    """Turn a csb session dict into an absolute jsonl path."""
    jsonl_path = session.get("jsonl_path", "")
    claude_dir = config.get("claude_dir", os.path.expanduser("~/.claude"))
    full_path = os.path.join(claude_dir, jsonl_path)
    if os.path.isfile(full_path):
        return full_path
    # Fallback: jsonl_path might already be absolute
    if os.path.isabs(jsonl_path) and os.path.isfile(jsonl_path):
        return jsonl_path
    return None


# -- list / no-arg --

def list_sessions():
    """Print recent sessions via csb list."""
    try:
        result = subprocess.run(
            ["csb", "list"],
            capture_output=False,
            text=True,
        )
        return result.returncode
    except FileNotFoundError:
        print("Error: 'csb' command not found. Install with:", file=sys.stderr)
        print("  pip install git+https://github.com/DazzleML/Claude-Session-Backup.git", file=sys.stderr)
        return 1


# -- launch --

def launch_viewer(viewer_info, session_value):
    """Launch CCHV with --session <value>.

    viewer_info is a dict from find_viewer():
    - mode "binary": launch the exe directly as a detached process
    - mode "dev": launch via pnpm tauri:dev in the project directory
    """
    mode = viewer_info["mode"]
    path = viewer_info["path"]

    if mode == "dev":
        # Dev mode: pnpm tauri:dev -- -- --session <value>
        # This starts Vite + cargo run together. NOT detached — user sees
        # build output and can Ctrl-C to stop.
        cmd = ["pnpm", "tauri:dev", "--", "--", "--session", session_value]
        print(f"Launching in dev mode from: {path}")
        print(f"  (Vite + cargo run -- Ctrl-C to stop)")
        try:
            result = subprocess.run(cmd, cwd=path)
            return result.returncode
        except (OSError, FileNotFoundError) as exc:
            print(f"Error launching dev mode: {exc}", file=sys.stderr)
            print("  Is pnpm installed?", file=sys.stderr)
            return 1

    # Binary mode: detached so the viewer outlives this shell
    cmd = [path, "--session", session_value]
    try:
        if platform.system() == "Windows":
            subprocess.Popen(
                cmd,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
        else:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                close_fds=True,
            )
        return 0
    except OSError as exc:
        print(f"Error launching viewer: {exc}", file=sys.stderr)
        return 1


# -- main --

def main(argv):
    parser = argparse.ArgumentParser(
        prog="dz claudeview",
        description="Open a Claude Code session in the history viewer.",
        epilog=(
            "With no arguments, lists recent sessions via csb.\n"
            "Set $CLAUDEVIEW_BIN to override the viewer binary path."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Session UUID, UUID prefix, .jsonl path, sesslog folder name, or title keyword",
    )

    args = parser.parse_args(argv)

    # No query -> list sessions
    if args.query is None:
        return list_sessions()

    # Find the viewer (binary or dev-mode project)
    viewer = find_viewer()
    if not viewer:
        print("Error: Claude Code History Viewer not found.", file=sys.stderr)
        print("Options:", file=sys.stderr)
        print("  - Set $CLAUDEVIEW_BIN to the viewer binary path", file=sys.stderr)
        print("  - Install from: https://github.com/jhlee0409/claude-code-history-viewer", file=sys.stderr)
        print("  - Clone the fork and build: pnpm tauri:build", file=sys.stderr)
        return 1

    # Connect to csb
    conn, config = _get_csb_connection()
    if conn is None:
        return 1

    # Resolve the query
    result, method = resolve_query(args.query, conn, config)
    if result is None:
        print(f"Error: {method}", file=sys.stderr)
        return 1
    if isinstance(result, list):
        # Multiple candidates -- show them and exit
        label = method.split(":", 1)[1] if ":" in method else method
        _show_candidates(result, args.query, label)
        return 1
    session = result

    # Get the jsonl path
    jsonl_path = resolve_jsonl_path(session, config)
    session_id = session.get("session_id", args.query)
    session_name = session.get("session_name", "")

    # Decide what to pass to --session: prefer UUID for Stage A compatibility,
    # fall back to path for Stage B when the viewer supports it
    actual_session_id = session.get("actual_session_id") or session_id
    launch_value = actual_session_id

    # Show what we resolved
    display = session_name or session_id
    if session_name:
        display = f"{session_name} ({actual_session_id[:8]}...)"
    else:
        display = actual_session_id
    print(f"Opening: {display}")
    if method != "uuid":
        print(f"  Resolved via: {method}")
    if jsonl_path:
        print(f"  Path: {jsonl_path}")

    return launch_viewer(viewer, launch_value)
