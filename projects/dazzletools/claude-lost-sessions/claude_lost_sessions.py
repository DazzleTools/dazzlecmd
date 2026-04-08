#!/usr/bin/env python3
"""
claude-lost-sessions - Catalog lost Claude Code session transcripts.

Scans ~/.claude/sesslogs/ for broken transcript.jsonl symlinks, extracts
metadata from session log files (timestamps, commands, tools used), and
creates a structured ~/claude/lost-sessions/ directory with per-session
summaries and an INDEX.md master table.

For each lost session, cross-references project private/claude/ docs,
~/claude/ general docs, and git commits within the session timeframe to
find surviving artifacts.

Usage via dz:
    dz claude-lost-sessions                         # dry-run preview
    dz claude-lost-sessions --apply                 # create lost-sessions catalog
    dz claude-lost-sessions --apply --verbose       # with per-session detail
    dz claude-lost-sessions --sesslogs-path DIR     # custom sesslogs path
    dz claude-lost-sessions --output-path DIR       # custom output directory
"""

import argparse
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

def _set_symlink_timestamps(symlink_path, mtime, atime=None, ctime=None):
    """Set timestamps on a symlink itself (not following to target).

    Uses Win32 CreateFileW with FILE_FLAG_OPEN_REPARSE_POINT to open the
    symlink entry directly, then SetFileTime to set its timestamps. This
    does NOT modify the target file's timestamps.

    On non-Windows platforms, falls back to os.utime with follow_symlinks=False
    (which works on Linux/macOS but not Windows Python).

    Args:
        symlink_path: Path to the symlink
        mtime: Modification time as a float (epoch seconds) or datetime
        atime: Access time (defaults to mtime if not specified)
        ctime: Creation time (defaults to mtime if not specified)
    """
    if isinstance(mtime, datetime):
        mtime = mtime.timestamp()
    if atime is None:
        atime = mtime
    elif isinstance(atime, datetime):
        atime = atime.timestamp()
    if ctime is None:
        ctime = mtime
    elif isinstance(ctime, datetime):
        ctime = ctime.timestamp()

    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32

            FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
            FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
            FILE_WRITE_ATTRIBUTES = 0x100
            OPEN_EXISTING = 3

            handle = kernel32.CreateFileW(
                str(symlink_path),
                FILE_WRITE_ATTRIBUTES,
                0,
                None,
                OPEN_EXISTING,
                FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
                None,
            )

            INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
            if handle == INVALID_HANDLE_VALUE:
                return

            # Convert epoch seconds to Windows FILETIME (100-ns intervals since 1601)
            EPOCH_DIFF = 116444736000000000

            class FILETIME(ctypes.Structure):
                _fields_ = [
                    ("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD),
                ]

            def _to_filetime(ts):
                ft_val = int(ts * 10000000) + EPOCH_DIFF
                ft = FILETIME()
                ft.dwLowDateTime = ft_val & 0xFFFFFFFF
                ft.dwHighDateTime = (ft_val >> 32) & 0xFFFFFFFF
                return ft

            ft_ctime = _to_filetime(ctime)
            ft_atime = _to_filetime(atime)
            ft_mtime = _to_filetime(mtime)

            kernel32.SetFileTime(
                handle,
                ctypes.byref(ft_ctime),
                ctypes.byref(ft_atime),
                ctypes.byref(ft_mtime),
            )
            kernel32.CloseHandle(handle)
        except Exception:
            pass
    else:
        try:
            os.utime(str(symlink_path), (atime, mtime), follow_symlinks=False)
        except (NotImplementedError, OSError):
            pass

# Filename date prefix pattern: YYYY-MM-DD__HH-MM-SS (full) or YYYY-MM-DD__HH-MM (short)
FILENAME_DATE_FULL = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})__(\d{2})-(\d{2})-(\d{2})"
)
FILENAME_DATE_SHORT = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})__(\d{2})-(\d{2})"
)


def _extract_filename_datetime(filename):
    """Extract a datetime from a date-prefixed filename.

    Supports YYYY-MM-DD__HH-MM-SS and YYYY-MM-DD__HH-MM formats.
    Returns a datetime or None if the filename doesn't match.
    """
    m = FILENAME_DATE_FULL.match(filename)
    if m:
        return datetime(*[int(g) for g in m.groups()])
    m = FILENAME_DATE_SHORT.match(filename)
    if m:
        return datetime(*[int(g) for g in m.groups()])
    return None


# Timestamp pattern from sesslog files: [[2026-02-24 23:28:19]]
TS_PATTERN = re.compile(r"\[\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\]")

# Tool usage pattern: {ToolName: ...}
TOOL_PATTERN = re.compile(r"\{(\w+):")

# Session start header pattern
SESSION_START_PATTERN = re.compile(
    r"SESSION START\s+.*?\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)

# How much to read from end of file for last timestamp
TAIL_READ_SIZE = 8192

# Log file priority (globs, checked in order)
SOURCE_FILE_PRIORITY = [
    ".sesslog_bash*",
    ".shell_bash*",
    ".tasks_bash*",
    ".Python_sesslog_bash*",
    ".Python_shell_bash*",
]

# Default paths
DEFAULT_SESSLOGS = Path.home() / ".claude" / "sesslogs"
DEFAULT_OUTPUT = Path.home() / "claude" / "lost-sessions"
DEFAULT_CLAUDE_DOCS = Path.home() / "claude"


# ---------------------------------------------------------------------------
# Timestamp extraction (borrowed from claude-sesslog-datefix)
# ---------------------------------------------------------------------------

def extract_first_timestamp(filepath):
    """Read the first [[timestamp]] from a file. Reads first 4KB."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            chunk = f.read(4096)
        match = TS_PATTERN.search(chunk)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except OSError:
        pass
    return None


def extract_last_timestamp(filepath):
    """Read the last [[timestamp]] from a file. Seeks to end for efficiency."""
    try:
        file_size = os.path.getsize(filepath)
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            if file_size > TAIL_READ_SIZE:
                f.seek(file_size - TAIL_READ_SIZE)
                f.readline()  # discard partial first line
            chunk = f.read()
        matches = TS_PATTERN.findall(chunk)
        if matches:
            return datetime.strptime(matches[-1], "%Y-%m-%d %H:%M:%S")
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Sesslog metadata extraction
# ---------------------------------------------------------------------------

def parse_folder_name(folder_name):
    """Parse SESSION_NAME__UUID_USERNAME from folder name.

    Returns (session_name, uuid, username) or (folder_name, None, None) if
    the name doesn't match the expected pattern.
    """
    # Pattern: NAME__UUID_USERNAME (NAME can be empty for unnamed sessions)
    # UUID is 8-4-4-4-12 hex
    match = re.match(
        r"^(.*?)__([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_(\w+)$",
        folder_name,
    )
    if match:
        name = match.group(1) or "(unnamed)"
        return name, match.group(2), match.group(3)
    return folder_name, None, None


def decode_project_path(encoded):
    """Decode Claude Code project path encoding by filesystem validation.

    Claude Code encodes paths like:
        C:\\code\\Prime-Square-Sum -> C--code-Prime-Square-Sum
        C:\\Users\\Extreme\\.claude -> C--Users-Extreme--claude

    The encoding is ambiguous (hyphens in folder names vs path separators
    both become -). We resolve ambiguity by trying candidate decodings
    against the filesystem and returning the first that exists.
    """
    if not encoded:
        return None

    # Remove \\?\\ prefix if present
    encoded = encoded.replace("\\\\?\\", "").replace("\\?\\", "")

    # Extract the project dir from the full path
    parts = encoded.replace("\\", "/").split("/")
    project_dir = None
    for i, part in enumerate(parts):
        if part == "projects" and i + 1 < len(parts):
            project_dir = parts[i + 1]
            break

    if not project_dir:
        return None

    if len(project_dir) < 3 or project_dir[1:3] != "--":
        return project_dir

    drive = project_dir[0] + ":"
    rest = project_dir[3:]

    if not rest:
        return drive + os.sep

    # Handle -- (double dash) as special separator (encodes . or special chars)
    # e.g., C--Users-Extreme--claude = C:\Users\Extreme\.claude
    # Split on -- first, then resolve each segment's internal hyphens
    double_segments = rest.split("--")

    def _resolve_segment(seg, parent_path):
        """Resolve a hyphenated segment against the filesystem.

        Given 'code-Prime-Square-Sum' and parent 'C:', try all ways to
        split on hyphens and find which produces existing directories.
        Returns the resolved path portion or the naive replacement.
        """
        if not seg:
            return ""

        parts = seg.split("-")
        if len(parts) == 1:
            return parts[0]

        # Greedy from left: try longest component that exists as first dir
        # then recurse on remainder
        for i in range(len(parts), 0, -1):
            component = "-".join(parts[:i])
            candidate = os.path.join(parent_path, component)
            if os.path.exists(candidate):
                if i == len(parts):
                    return component
                # Recurse on remaining segments
                rest_resolved = _resolve_segment(
                    "-".join(parts[i:]), candidate
                )
                return component + os.sep + rest_resolved

        # No filesystem match found -- try single-hyphen-as-separator
        # but validate the first component exists
        first = parts[0]
        if os.path.exists(os.path.join(parent_path, first)):
            rest_resolved = _resolve_segment(
                "-".join(parts[1:]), os.path.join(parent_path, first)
            )
            return first + os.sep + rest_resolved

        # Complete fallback: join everything with hyphens (keep as-is)
        return seg

    result_parts = []
    current_path = drive + os.sep

    for seg in double_segments:
        if not seg:
            # -- with nothing after = just a separator
            continue
        resolved = _resolve_segment(seg, current_path)
        result_parts.append(resolved)
        current_path = os.path.join(current_path, resolved)

    if not result_parts:
        return drive + os.sep

    # Join with . for double-dash separated segments (like .claude)
    if len(result_parts) == 1:
        return drive + os.sep + result_parts[0]
    else:
        # First segment is normal path, subsequent -- segments get . prefix
        path = drive + os.sep + result_parts[0]
        for part in result_parts[1:]:
            path = os.path.join(path, "." + part)
        return path


def find_log_files(directory):
    """Find all log files in a sesslog directory."""
    dirpath = Path(directory)
    files = []
    for pattern in SOURCE_FILE_PRIORITY:
        files.extend(dirpath.glob(pattern))
    # Also find task log files (numbered)
    files.extend(dirpath.glob(".tasks_bash*"))
    return sorted(set(files))


def find_primary_log(directory):
    """Find the primary (most informative) log file."""
    dirpath = Path(directory)
    for pattern in SOURCE_FILE_PRIORITY:
        matches = sorted(dirpath.glob(pattern))
        if matches:
            return matches[0]
    return None


def extract_working_dirs(sesslog_dir):
    """Extract working directories from sesslog commands.

    Parses Read/Edit/Write paths and Bash cd commands to find project
    directories touched during the session. Returns a Counter of
    directory -> count.
    """
    from collections import Counter
    dir_counts = Counter()

    # Patterns for extracting paths from different tool types
    read_edit_pattern = re.compile(r'\{(?:Read|Edit|Write):\s+"([^"]+)"')
    bash_cd_pattern = re.compile(r'\{Bash:\s+cd\s+(/[^\s&|;]+|"[^"]+")')
    bash_path_pattern = re.compile(r'\{Bash:\s+(?:ls|cat|head|tail|find|git -C)\s+["\']?([A-Z]:[/\\][^"\'&|;\s]+|/[a-z]/[^"\'&|;\s]+)')

    log_files = find_log_files(sesslog_dir)
    for lf in log_files:
        try:
            with open(lf, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    # Read/Edit/Write paths
                    m = read_edit_pattern.search(line)
                    if m:
                        path = m.group(1).split(":")[0] if ":" in m.group(1) and len(m.group(1).split(":")[0]) > 2 else m.group(1)
                        # Extract directory
                        p = Path(path.replace("\\", "/"))
                        parent = str(p.parent)
                        if len(parent) > 3:  # Skip bare drive roots
                            dir_counts[parent] += 1
                        continue

                    # Bash cd commands
                    m = bash_cd_pattern.search(line)
                    if m:
                        d = m.group(1).strip('"').strip("'")
                        if len(d) > 3:
                            dir_counts[d] += 1
                        continue

                    # Bash commands with paths
                    m = bash_path_pattern.search(line)
                    if m:
                        p = Path(m.group(1).replace("\\", "/"))
                        parent = str(p.parent) if p.suffix else str(p)
                        if len(parent) > 3:
                            dir_counts[parent] += 1
        except OSError:
            pass

    return dir_counts


def extract_markdown_refs(sesslog_dir):
    """Extract references to markdown files from sesslog commands.

    Finds .md file paths mentioned in Read/Write/Edit commands.
    Returns dict with:
        'written': list of .md files we CREATED (Write operations)
        'edited': list of .md files we MODIFIED (Edit operations)
        'read': list of .md files we READ
        'all': combined unique list
        'write_dirs': unique parent directories from Write operations
    """
    written = set()
    edited = set()
    read_files = set()
    write_dirs = set()

    md_pattern = re.compile(r'"([^"]+\.md(?::[0-9-]+)?)"')

    def _strip_line_number(path_str):
        """Remove trailing :LINE or :START-END from a path, preserving drive letter colon."""
        # Match trailing :NNN or :NNN-NNN (line number references)
        m = re.match(r'^(.+\.md):(\d+(?:-\d+)?)$', path_str)
        if m:
            return m.group(1)
        return path_str

    log_files = find_log_files(sesslog_dir)
    for lf in log_files:
        try:
            with open(lf, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "{Write:" in line:
                        for m in md_pattern.finditer(line):
                            path = _strip_line_number(m.group(1))
                            written.add(path)
                            parent = str(Path(path).parent)
                            if len(parent) > 3:
                                write_dirs.add(parent)
                    elif "{Edit:" in line:
                        for m in md_pattern.finditer(line):
                            path = _strip_line_number(m.group(1))
                            edited.add(path)
                    elif "{Read:" in line:
                        for m in md_pattern.finditer(line):
                            path = _strip_line_number(m.group(1))
                            read_files.add(path)
        except OSError:
            pass

    all_files = sorted(written | edited | read_files)

    return {
        "written": sorted(written),
        "edited": sorted(edited),
        "read": sorted(read_files),
        "all": all_files,
        "write_dirs": sorted(write_dirs),
    }


def _deduce_top_dirs(working_dirs):
    """Deduce top-level project directories from working dir counts.

    Finds project roots by looking for directories that contain .git/,
    private/, pyproject.toml, or similar markers. Falls back to grouping
    by the first 3 path components.
    """
    from collections import Counter
    roots = Counter()

    project_markers = [".git", "private", "pyproject.toml", "setup.py", "Cargo.toml", "package.json"]

    for d, count in working_dirs.items():
        p = Path(d.replace("\\", "/"))

        # Walk up from the path to find a project root
        found_root = None
        check = p
        for _ in range(6):  # Don't walk up more than 6 levels
            if any((check / marker).exists() for marker in project_markers):
                found_root = str(check)
                break
            parent = check.parent
            if parent == check:
                break
            check = parent

        if found_root:
            roots[found_root] += count
        else:
            # Fallback: use first 3 components
            parts = p.parts
            if len(parts) >= 3:
                roots[str(Path(*parts[:3]))] += count
            elif len(parts) >= 2:
                roots[str(Path(*parts[:2]))] += count

    # Filter and return
    skip_prefixes = ("/tmp", "/dev", "/usr", "/bin", "/c/Windows", "/c/Program Files")
    return [
        d for d, _ in roots.most_common(10)
        if not any(d.startswith(s) for s in skip_prefixes)
        and Path(d).is_dir()
    ]


def extract_session_metadata(sesslog_dir):
    """Extract all available metadata from a sesslog directory.

    Returns dict with: start_time, end_time, duration, command_count,
    tools_used, first_commands, last_commands, log_files, line_counts.
    """
    meta = {
        "start_time": None,
        "end_time": None,
        "duration": None,
        "command_count": 0,
        "tools_used": set(),
        "first_commands": [],
        "last_commands": [],
        "log_files": [],
        "total_lines": 0,
    }

    log_files = find_log_files(sesslog_dir)
    if not log_files:
        return meta

    # Gather timestamps from all log files for accurate start/end
    all_first_ts = []
    all_last_ts = []

    for lf in log_files:
        first_ts = extract_first_timestamp(lf)
        last_ts = extract_last_timestamp(lf)
        if first_ts:
            all_first_ts.append(first_ts)
        if last_ts:
            all_last_ts.append(last_ts)

        try:
            line_count = sum(1 for _ in open(lf, "r", encoding="utf-8", errors="replace"))
        except OSError:
            line_count = 0

        meta["log_files"].append({
            "name": lf.name,
            "lines": line_count,
        })
        meta["total_lines"] += line_count

    if all_first_ts:
        meta["start_time"] = min(all_first_ts)
    if all_last_ts:
        meta["end_time"] = max(all_last_ts)

    if meta["start_time"] and meta["end_time"]:
        delta = meta["end_time"] - meta["start_time"]
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        meta["duration"] = f"{hours}h {minutes}m"

    # Extract commands and tools from primary log
    primary = find_primary_log(sesslog_dir)
    if primary:
        try:
            with open(primary, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            ts_lines = [l.strip() for l in lines if TS_PATTERN.search(l)]
            meta["command_count"] = len(ts_lines)

            # Collect tools used
            for line in ts_lines:
                tool_match = TOOL_PATTERN.search(line)
                if tool_match:
                    meta["tools_used"].add(tool_match.group(1))

            # First and last N commands
            meta["first_commands"] = ts_lines[:5]
            meta["last_commands"] = ts_lines[-5:] if len(ts_lines) > 5 else []

        except OSError:
            pass

    meta["tools_used"] = sorted(meta["tools_used"])
    return meta


def get_symlink_target(sesslog_dir):
    """Read the transcript.jsonl symlink target (even if broken)."""
    transcript = Path(sesslog_dir) / "transcript.jsonl"
    if transcript.is_symlink():
        try:
            target = os.readlink(str(transcript))
            # Clean up \\?\ prefix
            target = target.replace("\\\\?\\", "").replace("\\?\\", "")
            return target
        except OSError:
            pass
    return None


def is_broken_symlink(sesslog_dir):
    """Check if the transcript.jsonl symlink is broken."""
    transcript = Path(sesslog_dir) / "transcript.jsonl"
    if transcript.is_symlink():
        return not transcript.exists()
    # Also check for other broken transcript variants
    for f in Path(sesslog_dir).glob("trans*"):
        if f.is_symlink() and not f.exists():
            return True
    return not transcript.exists()


# ---------------------------------------------------------------------------
# Artifact cross-referencing
# ---------------------------------------------------------------------------

def find_timeframe_docs(docs_dir, start_time, end_time):
    """Find markdown docs in a directory created within the session timeframe.

    Uses filename date prefixes (YYYY-MM-DD__HH-MM) rather than filesystem
    timestamps (which may have been clobbered).
    """
    if not docs_dir or not Path(docs_dir).is_dir():
        return []

    found = []
    date_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})__(\d{2})-(\d{2})")

    for f in sorted(Path(docs_dir).glob("*.md")):
        match = date_pattern.match(f.name)
        if match:
            try:
                file_date = datetime.strptime(
                    f"{match.group(1)} {match.group(2)}:{match.group(3)}",
                    "%Y-%m-%d %H:%M",
                )
                # Allow 1-day buffer on each side for related docs
                if start_time and end_time:
                    buffer_start = start_time - timedelta(days=1)
                    buffer_end = end_time + timedelta(days=1)
                    if buffer_start <= file_date <= buffer_end:
                        found.append(f)
            except ValueError:
                pass

    return found


def find_git_commits(project_path, start_time, end_time):
    """Find git commits in a project directory within the session timeframe."""
    if not project_path or not Path(project_path).is_dir():
        return []

    try:
        result = subprocess.run(
            [
                "git", "log", "--oneline",
                "--after", start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "--before", (end_time + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return []


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------

def generate_summary_md(session_name, uuid, username, target_path, project_path,
                        meta, project_docs, general_docs, git_commits,
                        top_dirs=None, markdown_refs=None):
    """Generate summary.md content for a lost session."""
    lines = [
        f"# Lost Session: {session_name}",
        "",
        f"**UUID:** `{uuid}`",
        f"**Start:** {meta['start_time'].strftime('%Y-%m-%d %H:%M:%S') if meta['start_time'] else 'unknown'}",
        f"**End:** {meta['end_time'].strftime('%Y-%m-%d %H:%M:%S') if meta['end_time'] else 'unknown'}",
        f"**Duration:** {meta['duration'] or 'unknown'}",
        f"**Project (encoded):** `{target_path or 'unknown'}`",
        f"**Project (decoded):** `{project_path or 'unknown'}`",
        f"**Command Count:** {meta['command_count']}",
        f"**Tools Used:** {', '.join(meta['tools_used']) if meta['tools_used'] else 'unknown'}",
        f"**Total Log Lines:** {meta['total_lines']}",
        "",
    ]

    if meta["first_commands"]:
        lines.append("## First Commands")
        lines.append("```")
        for cmd in meta["first_commands"]:
            lines.append(cmd)
        lines.append("```")
        lines.append("")

    if meta["last_commands"]:
        lines.append("## Last Commands")
        lines.append("```")
        for cmd in meta["last_commands"]:
            lines.append(cmd)
        lines.append("```")
        lines.append("")

    lines.append("## Related Artifacts")
    lines.append("")

    has_artifacts = False
    if project_docs:
        lines.append("### Project Documents")
        for doc in project_docs:
            lines.append(f"- `{doc.name}`")
            has_artifacts = True
        lines.append("")

    if general_docs:
        lines.append("### General Documents")
        for doc in general_docs:
            lines.append(f"- `{doc.name}`")
            has_artifacts = True
        lines.append("")

    if git_commits:
        lines.append("### Git Commits")
        for commit in git_commits:
            lines.append(f"- `{commit}`")
            has_artifacts = True
        lines.append("")

    if not has_artifacts:
        lines.append("*No related artifacts found within the session timeframe.*")
        lines.append("")

    if top_dirs:
        lines.append("## Folders Worked On")
        lines.append("")
        for d in top_dirs:
            lines.append(f"- `{d}`")
        lines.append("")

    if markdown_refs:
        if isinstance(markdown_refs, dict):
            if markdown_refs.get("written"):
                lines.append("## Documents We Created (Write)")
                lines.append("")
                for md in markdown_refs["written"]:
                    exists = " (exists)" if Path(md).exists() else " (missing)"
                    lines.append(f"- `{md}`{exists}")
                lines.append("")
            if markdown_refs.get("edited"):
                lines.append("## Documents We Edited")
                lines.append("")
                for md in markdown_refs["edited"]:
                    exists = " (exists)" if Path(md).exists() else " (missing)"
                    lines.append(f"- `{md}`{exists}")
                lines.append("")
            if markdown_refs.get("read"):
                lines.append("## Documents We Read")
                lines.append("")
                for md in markdown_refs["read"]:
                    exists = " (exists)" if Path(md).exists() else " (missing)"
                    lines.append(f"- `{md}`{exists}")
                lines.append("")
        else:
            # Legacy: list of paths
            lines.append("## Markdown Files Referenced in Session")
            lines.append("")
            for md in markdown_refs:
                exists = " (exists)" if Path(md).exists() else " (missing)"
                lines.append(f"- `{md}`{exists}")
            lines.append("")

    lines.append("## Sesslog Files")
    lines.append("")
    for lf in meta["log_files"]:
        lines.append(f"- `{lf['name']}` ({lf['lines']} lines)")
    lines.append("")

    return "\n".join(lines)


def generate_index_md(sessions):
    """Generate INDEX.md master table."""
    lines = [
        "# Lost Session Index",
        "",
        f"{len(sessions)} sessions with missing transcripts. Sorted by date.",
        "",
        "| Date | Session Name | Project | Duration | Cmds | Artifacts |",
        "|------|-------------|---------|----------|------|-----------|",
    ]

    for s in sessions:
        date_str = s["start_time"].strftime("%Y-%m-%d %H:%M") if s["start_time"] else "unknown"
        artifacts = []
        if s["project_docs"]:
            artifacts.append(f"{len(s['project_docs'])} docs")
        if s["general_docs"]:
            artifacts.append(f"{len(s['general_docs'])} gen-docs")
        if s["git_commits"]:
            artifacts.append(f"{len(s['git_commits'])} commits")
        artifact_str = ", ".join(artifacts) if artifacts else "--"

        # Truncate long session names
        name = s["session_name"]
        if len(name) > 40:
            name = name[:37] + "..."

        project = s.get("project_short", "--")
        if len(project) > 25:
            project = project[:22] + "..."

        lines.append(
            f"| {date_str} | {name} | {project} | {s['duration'] or '--'} | {s['command_count']} | {artifact_str} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary stats
    total_cmds = sum(s["command_count"] for s in sessions)
    with_artifacts = sum(1 for s in sessions if s["project_docs"] or s["general_docs"] or s["git_commits"])
    named = sum(1 for s in sessions if not s["session_name"].startswith("c__"))
    high_value = sum(1 for s in sessions if s["command_count"] > 50 or s.get("has_artifacts"))

    lines.extend([
        "## Summary",
        "",
        f"- **Total lost sessions:** {len(sessions)}",
        f"- **Total commands across all sessions:** {total_cmds}",
        f"- **Sessions with surviving artifacts:** {with_artifacts}",
        f"- **Named sessions (not generic c__):** {named}",
        f"- **High-value sessions (>50 cmds or has artifacts):** {high_value}",
        "",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    """Entry point for dz claude-lost-sessions."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="dz claude-lost-sessions",
        description="Catalog lost Claude Code session transcripts by scanning "
                    "broken sesslog symlinks and cross-referencing artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  dz claude-lost-sessions                         Preview (dry-run)
  dz claude-lost-sessions --apply                 Create lost-sessions catalog
  dz claude-lost-sessions --apply --verbose       With per-session detail
  dz claude-lost-sessions --sesslogs-path DIR     Custom sesslogs directory
  dz claude-lost-sessions --output-path DIR       Custom output directory
""",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Create the lost-sessions catalog (default is dry-run preview)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show per-session detail during processing",
    )
    parser.add_argument(
        "--sesslogs-path", type=str, default=None,
        help=f"Path to sesslogs directory (default: {DEFAULT_SESSLOGS})",
    )
    parser.add_argument(
        "--output-path", type=str, default=None,
        help=f"Path to output directory (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--skip-git", action="store_true",
        help="Skip git commit cross-referencing (faster)",
    )

    args = parser.parse_args(argv)

    sesslogs_path = Path(args.sesslogs_path) if args.sesslogs_path else DEFAULT_SESSLOGS
    output_path = Path(args.output_path) if args.output_path else DEFAULT_OUTPUT

    if not sesslogs_path.is_dir():
        print(f"Error: sesslogs directory not found: {sesslogs_path}")
        return 1

    # Scan for broken symlinks
    print(f"Scanning {sesslogs_path} for broken transcript links...")
    broken_sessions = []
    valid_count = 0
    skip_count = 0

    for entry in sorted(sesslogs_path.iterdir()):
        if not entry.is_dir():
            continue

        if is_broken_symlink(entry):
            broken_sessions.append(entry)
        else:
            transcript = entry / "transcript.jsonl"
            if transcript.exists():
                valid_count += 1
            else:
                skip_count += 1

    print(f"  Found: {len(broken_sessions)} broken, {valid_count} valid, {skip_count} no transcript")
    print()

    if not broken_sessions:
        print("No broken transcript links found. Nothing to catalog.")
        return 0

    # Process each broken session
    sessions_data = []

    for i, sesslog_dir in enumerate(broken_sessions, 1):
        folder_name = sesslog_dir.name
        session_name, uuid, username = parse_folder_name(folder_name)

        if args.verbose or not args.apply:
            progress = f"[{i}/{len(broken_sessions)}]"
            print(f"  {progress} {session_name} ({uuid or 'no-uuid'})")

        # Get symlink target and decode project path
        target_path = get_symlink_target(sesslog_dir)
        project_path = decode_project_path(target_path) if target_path else None

        # Extract project short name from encoded path
        project_short = "--"
        if target_path:
            parts = target_path.replace("\\", "/").split("/")
            for j, part in enumerate(parts):
                if part == "projects" and j + 1 < len(parts):
                    project_short = parts[j + 1]
                    break

        # Extract metadata from log files
        meta = extract_session_metadata(sesslog_dir)

        # Extract working directories and markdown references from sesslogs
        working_dirs = extract_working_dirs(sesslog_dir)
        markdown_refs = extract_markdown_refs(sesslog_dir)

        # Deduce top-level project directories from working dirs
        top_dirs = _deduce_top_dirs(working_dirs)

        # Cross-reference artifacts
        project_docs = []
        general_docs = []
        git_commits = []
        all_known_docs = []  # All .md files found across all sources

        # First priority: files we WROTE during the session (from sesslog)
        written_docs = []
        for md_path in markdown_refs.get("written", []):
            p = Path(md_path)
            if p.exists():
                written_docs.append(p)

        # Second: files we EDITED
        edited_docs = []
        for md_path in markdown_refs.get("edited", []):
            p = Path(md_path)
            if p.exists():
                edited_docs.append(p)

        if meta["start_time"] and meta["end_time"]:
            # Search private/claude/ in decoded project path
            if project_path:
                priv_claude = Path(project_path) / "private" / "claude"
                project_docs = find_timeframe_docs(priv_claude, meta["start_time"], meta["end_time"])

            # Search private/claude/ in all working directories
            searched_privs = set()
            if project_path:
                searched_privs.add(str(Path(project_path) / "private" / "claude"))

            for d in top_dirs:
                priv = Path(d) / "private" / "claude"
                if priv.is_dir() and str(priv) not in searched_privs:
                    extra = find_timeframe_docs(priv, meta["start_time"], meta["end_time"])
                    project_docs.extend(extra)
                    searched_privs.add(str(priv))

            # Search directories where we WROTE .md files (from sesslog Write commands)
            for write_dir in markdown_refs.get("write_dirs", []):
                wd = Path(write_dir)
                if wd.is_dir() and str(wd) not in searched_privs:
                    extra = find_timeframe_docs(wd, meta["start_time"], meta["end_time"])
                    project_docs.extend(extra)
                    searched_privs.add(str(wd))

            # Search ~/claude/ general docs
            general_docs = find_timeframe_docs(DEFAULT_CLAUDE_DOCS, meta["start_time"], meta["end_time"])

            # Search git commits in all top directories
            if not args.skip_git:
                for d in top_dirs:
                    commits = find_git_commits(d, meta["start_time"], meta["end_time"])
                    git_commits.extend(commits)

        # Collect known docs: only files WE AUTHORED during the session
        # NOT files we merely read for reference
        all_known_docs = []

        # 1. Files we explicitly wrote (strongest signal)
        all_known_docs.extend(written_docs)

        # 2. Files we edited that are in private/claude/ or ~/claude/ (our session docs)
        session_doc_patterns = ["private/claude", "private\\claude", "/claude/", "\\claude\\"]
        for doc in edited_docs:
            doc_str = str(doc)
            if any(pat in doc_str for pat in session_doc_patterns):
                all_known_docs.append(doc)

        # 3. Timeframe-matched docs from private/claude/ and ~/claude/
        # These are postmortems, dev-workflow docs, etc. we created
        all_known_docs.extend(project_docs)
        all_known_docs.extend(general_docs)

        # Deduplicate by resolving to canonical absolute paths
        seen_paths = set()
        unique_docs = []
        for d in all_known_docs:
            p = Path(d)
            # Use resolve() for existing files (canonical), normalize for missing
            if p.exists():
                norm = str(p.resolve()).lower()
            else:
                norm = str(p).replace("/", "\\").lower()
            if norm not in seen_paths:
                seen_paths.add(norm)
                unique_docs.append(d)
        all_known_docs = unique_docs

        has_artifacts = bool(all_known_docs or git_commits)

        session_data = {
            "folder_name": folder_name,
            "session_name": session_name,
            "uuid": uuid,
            "username": username,
            "target_path": target_path,
            "project_path": project_path,
            "project_short": project_short,
            "start_time": meta["start_time"],
            "end_time": meta["end_time"],
            "duration": meta["duration"],
            "command_count": meta["command_count"],
            "tools_used": meta["tools_used"],
            "meta": meta,
            "working_dirs": working_dirs,
            "top_dirs": top_dirs,
            "markdown_refs": markdown_refs,
            "project_docs": project_docs,
            "general_docs": general_docs,
            "all_known_docs": all_known_docs,
            "git_commits": git_commits,
            "has_artifacts": has_artifacts,
        }
        sessions_data.append(session_data)

        if args.verbose:
            ts_range = ""
            if meta["start_time"]:
                ts_range = f" ({meta['start_time'].strftime('%Y-%m-%d')} - {meta['end_time'].strftime('%Y-%m-%d') if meta['end_time'] else '?'})"
            art_str = f" [artifacts: {len(project_docs)} docs, {len(git_commits)} commits]" if has_artifacts else ""
            print(f"           {meta['command_count']} cmds, {meta['duration'] or 'unknown'}{ts_range}{art_str}")

    # Sort by start time (unknown times at end)
    sessions_data.sort(key=lambda s: s["start_time"] or datetime.max)

    # Print summary
    print()
    print(f"--- Summary ---")
    total_cmds = sum(s["command_count"] for s in sessions_data)
    with_artifacts = sum(1 for s in sessions_data if s["has_artifacts"])
    with_logs = sum(1 for s in sessions_data if s["command_count"] > 0)
    named = sum(1 for s in sessions_data if not s["session_name"].startswith("c__") and not s["session_name"].startswith("c--"))
    print(f"  Lost sessions:       {len(sessions_data)}")
    print(f"  With log data:       {with_logs}")
    print(f"  Named sessions:      {named}")
    print(f"  Total commands:      {total_cmds}")
    print(f"  With artifacts:      {with_artifacts}")

    if not args.apply:
        print()
        print("Dry run complete. Use --apply to create the lost-sessions catalog.")
        return 0

    # Create output directory structure
    print()
    print(f"Creating catalog at {output_path}/...")
    output_path.mkdir(parents=True, exist_ok=True)

    for s in sessions_data:
        # Folder name: YYYY-MM-DD__HH-MM__SESSION_NAME
        if s["start_time"]:
            date_prefix = s["start_time"].strftime("%Y-%m-%d__%H-%M")
        else:
            date_prefix = "unknown-date"

        # Sanitize session name for filesystem
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', s["session_name"])
        if len(safe_name) > 60:
            safe_name = safe_name[:57] + "..."

        # Include short UUID to disambiguate duplicate names
        short_uuid = s["uuid"][:8] if s["uuid"] else "no-uuid"
        folder_name = f"{date_prefix}__{safe_name}__{short_uuid}"
        session_dir = output_path / folder_name
        session_dir.mkdir(parents=True, exist_ok=True)

        # Write summary.md
        summary_content = generate_summary_md(
            s["session_name"], s["uuid"], s["username"],
            s["target_path"], s["project_path"],
            s["meta"], s["project_docs"], s["general_docs"], s["git_commits"],
            top_dirs=s.get("top_dirs"), markdown_refs=s.get("markdown_refs"),
        )
        (session_dir / "summary.md").write_text(summary_content, encoding="utf-8")

        # Create symlink to original sesslog directory
        sesslog_link = session_dir / "sesslog"
        sesslog_source = Path(sesslogs_path) / s["folder_name"]
        if not sesslog_link.exists():
            try:
                sesslog_link.symlink_to(sesslog_source, target_is_directory=True)
            except OSError:
                (session_dir / "sesslog_path.txt").write_text(
                    str(sesslog_source), encoding="utf-8"
                )

        # Create reverse link: sesslog folder -> lost-session folder
        # Use a junction on Windows so it appears as a real folder in Explorer
        reverse_link = sesslog_source / "lost-session"
        if sesslog_source.is_dir() and not reverse_link.exists():
            target_resolved = str(session_dir.resolve())
            created = False
            if platform.system() == "Windows":
                try:
                    subprocess.run(
                        ["powershell", "-Command",
                         f"New-Item -ItemType Junction "
                         f"-Path '{reverse_link}' "
                         f"-Target '{target_resolved}'"],
                        capture_output=True, check=True,
                    )
                    created = True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass
            if not created:
                try:
                    reverse_link.symlink_to(target_resolved,
                                            target_is_directory=True)
                except OSError:
                    try:
                        (sesslog_source / "lost-session_path.txt").write_text(
                            target_resolved, encoding="utf-8"
                        )
                    except OSError:
                        pass  # sesslog dir might be read-only

        # Create known-docs/ with junction links to discovered documents
        known_docs = s.get("all_known_docs", [])
        if known_docs:
            docs_dir = session_dir / "known-docs"
            docs_dir.mkdir(exist_ok=True)
            for doc in known_docs:
                doc_path = Path(doc)
                if doc_path.exists():
                    link_name = doc_path.name
                    # Avoid name collisions by prepending parent dir
                    link_target = docs_dir / link_name
                    counter = 1
                    while link_target.exists():
                        stem = doc_path.stem
                        link_target = docs_dir / f"{stem}_{counter}{doc_path.suffix}"
                        counter += 1
                    try:
                        link_target.symlink_to(doc_path.resolve())
                        # Set symlink's own timestamps to match the target
                        # file, so ls -lt sorts chronologically.
                        target_stat = doc_path.stat()
                        sym_ctime = target_stat.st_ctime
                        # If filename has a date prefix earlier than the
                        # file's ctime, use it -- the filename date is the
                        # authoritative creation time (ctime gets reset on
                        # copy/move on Windows).
                        fn_dt = _extract_filename_datetime(doc_path.name)
                        if fn_dt is not None:
                            fn_ts = fn_dt.timestamp()
                            if fn_ts < sym_ctime:
                                sym_ctime = fn_ts
                        _set_symlink_timestamps(
                            link_target,
                            mtime=target_stat.st_mtime,
                            atime=target_stat.st_atime,
                            ctime=sym_ctime,
                        )
                    except OSError:
                        # Fallback: write pointer
                        link_target.with_suffix(".txt").write_text(
                            f"-> {doc_path.resolve()}", encoding="utf-8"
                        )

        # Create folders-worked-on/ with junction links to top directories
        top_dirs = s.get("top_dirs", [])
        if top_dirs:
            dirs_dir = session_dir / "folders-worked-on"
            dirs_dir.mkdir(exist_ok=True)
            for d in top_dirs:
                d_path = Path(d)
                if d_path.is_dir():
                    # Use a safe name for the link
                    safe = str(d_path).replace("\\", "/").replace("/", "_").replace(":", "")
                    if len(safe) > 60:
                        safe = safe[:57] + "..."
                    link_path = dirs_dir / safe
                    if not link_path.exists():
                        try:
                            link_path.symlink_to(d_path.resolve(), target_is_directory=True)
                        except OSError:
                            link_path.with_suffix(".txt").write_text(
                                f"-> {d_path.resolve()}", encoding="utf-8"
                            )

        if args.verbose:
            extras = []
            if known_docs:
                extras.append(f"{len(known_docs)} docs")
            if top_dirs:
                extras.append(f"{len(top_dirs)} dirs")
            extra_str = f" [{', '.join(extras)}]" if extras else ""
            print(f"  Created: {folder_name}/{extra_str}")

    # Generate INDEX.md
    index_content = generate_index_md(sessions_data)
    (output_path / "INDEX.md").write_text(index_content, encoding="utf-8")
    print(f"  Created: INDEX.md")

    print()
    print(f"Catalog complete: {len(sessions_data)} sessions in {output_path}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
