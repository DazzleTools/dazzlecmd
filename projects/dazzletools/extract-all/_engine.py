"""
extract-all/_engine.py

7-Zip discovery and subprocess primitives.

Public API:
    find_seven_zip(override=None) -> str | None
    list_archive(z7, archive_path) -> list[ArchiveEntry]
    is_archive(z7, file_path) -> bool
    extract_archive(z7, archive_path, dest_dir) -> tuple[bool, str]
    estimate_size(z7, archive_path) -> int

Discovery order:
    1. Explicit override argument (or DZ_SEVEN_ZIP env var)
    2. shutil.which("7z")  -- system PATH
    3. shutil.which("7zz") -- macOS Homebrew
    4. C:\\Program Files\\7-Zip\\7z.exe
    5. C:\\Program Files (x86)\\7-Zip\\7z.exe

Returns None if 7z is not found anywhere.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass


SEVEN_ZIP_INSTALL_HINT = (
    "7-Zip not found. Install from https://www.7-zip.org/ "
    "or pass --seven-zip-path PATH (or set DZ_SEVEN_ZIP)."
)


@dataclass
class ArchiveEntry:
    """One entry from a 7z listing."""
    path: str           # path within the archive
    size: int           # uncompressed size in bytes (0 for directories)
    is_dir: bool


def find_seven_zip(override: str | None = None) -> str | None:
    """Locate a usable 7z binary. Returns absolute path or None."""
    if override:
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return os.path.abspath(override)
        return None

    env_override = os.environ.get("DZ_SEVEN_ZIP")
    if env_override and os.path.isfile(env_override):
        return os.path.abspath(env_override)

    for name in ("7z", "7zz"):
        found = shutil.which(name)
        if found:
            return found

    if sys.platform == "win32":
        for candidate in (
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
        ):
            if os.path.isfile(candidate):
                return candidate

    return None


def _run_seven_zip(z7: str, args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run 7z with the given args; returns CompletedProcess (does not raise on non-zero exit)."""
    return subprocess.run(
        [z7] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def is_archive(z7: str, file_path: str) -> bool:
    """Probe whether 7z can open the file as an archive (uses list mode -- cheap)."""
    if not os.path.isfile(file_path):
        return False
    # 7z l exits 0 if it can read the archive structure.
    # We use -bso0 -bd to silence stdout/progress; we only care about exit code.
    result = _run_seven_zip(z7, ["l", "-bso0", "-bd", file_path], timeout=30)
    return result.returncode == 0


def list_archive(z7: str, archive_path: str) -> list[ArchiveEntry]:
    """List archive contents. Returns empty list if 7z cannot read the file."""
    if not os.path.isfile(archive_path):
        return []
    # -slt = show technical info (one block per file with key=value lines)
    result = _run_seven_zip(z7, ["l", "-slt", archive_path], timeout=120)
    if result.returncode != 0:
        return []
    return _parse_slt_listing(result.stdout)


def _parse_slt_listing(output: str) -> list[ArchiveEntry]:
    """Parse 7z's -slt output into ArchiveEntry list.

    The -slt output has a header section, then "----------" separator,
    then a block per file with lines like:
        Path = relative/path/inside.archive
        Size = 12345
        Attributes = D (for directories)
    Blocks separated by blank lines.
    """
    entries: list[ArchiveEntry] = []
    in_files_section = False
    current: dict[str, str] = {}

    def flush(buf: dict[str, str]) -> None:
        if not buf.get("Path"):
            return
        size_raw = buf.get("Size", "0").strip()
        try:
            size = int(size_raw)
        except ValueError:
            size = 0
        attrs = buf.get("Attributes", "")
        is_dir = "D" in attrs.split() or attrs.startswith("D")
        entries.append(ArchiveEntry(path=buf["Path"], size=size, is_dir=is_dir))

    for line in output.splitlines():
        if not in_files_section:
            if line.startswith("----------"):
                in_files_section = True
            continue
        line_stripped = line.rstrip()
        if not line_stripped:
            if current:
                flush(current)
                current = {}
            continue
        if " = " in line_stripped:
            key, _, value = line_stripped.partition(" = ")
            current[key.strip()] = value
    if current:
        flush(current)
    return entries


def extract_archive(z7: str, archive_path: str, dest_dir: str) -> tuple[bool, str]:
    """Extract archive into dest_dir. Returns (success, error_message_if_any).

    -y answers yes to all prompts (e.g., overwrite); -bso0 silences stdout chatter;
    -bd disables progress bar. Stderr is preserved for diagnostics.
    """
    if not os.path.isfile(archive_path):
        return False, f"archive not found: {archive_path}"
    os.makedirs(dest_dir, exist_ok=True)
    result = _run_seven_zip(
        z7,
        ["x", archive_path, f"-o{dest_dir}", "-y", "-bso0", "-bd"],
        timeout=None,  # extraction can take a while for huge archives
    )
    if result.returncode == 0:
        return True, ""
    if result.returncode == 1:
        # Warning: extraction completed but with non-fatal warnings (e.g., some files skipped).
        # Treat as partial success.
        return True, f"7z warning: {result.stderr.strip()[:200]}"
    err = result.stderr.strip() or result.stdout.strip()
    return False, f"7z error (exit {result.returncode}): {err[:300]}"


def estimate_size(z7: str, archive_path: str) -> int:
    """Estimate uncompressed size of an archive in bytes. Returns 0 if unknown."""
    entries = list_archive(z7, archive_path)
    return sum(e.size for e in entries if not e.is_dir)
