"""
extract-all/_staging.py

Staging directory management. Each source archive gets its own staging
directory keyed by SHA-256(first 12 hex chars), under a configurable root
(default: %USERPROFILE%/extract-all/).

A `_source.txt` sibling file records the original filename, full path,
extraction date, and source SHA-256 for human-browsability of the cache.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
from datetime import datetime, timezone


DEFAULT_STAGING_ROOT = pathlib.Path.home() / "extract-all"

SOURCE_RECORD_FILENAME = "_source.txt"


def sha12(file_path: str | os.PathLike) -> str:
    """Return first 12 hex chars of SHA-256 of file contents."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def sha256_full(file_path: str | os.PathLike) -> str:
    """Return full hex SHA-256 of file contents."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def staging_dir(source_path: str | os.PathLike, root: pathlib.Path | None = None) -> pathlib.Path:
    """Return the staging directory path for a given source archive.

    Directory is NOT created here -- caller decides when to mkdir.
    """
    root = pathlib.Path(root) if root else DEFAULT_STAGING_ROOT
    return root / sha12(source_path)


def write_source_record(
    staging: pathlib.Path,
    source_path: str | os.PathLike,
    full_sha256: str | None = None,
) -> None:
    """Write a `_source.txt` describing the source archive.

    Idempotent: if the file already exists with matching content, leaves it alone.
    """
    staging.mkdir(parents=True, exist_ok=True)
    record_path = staging / SOURCE_RECORD_FILENAME

    source_path = pathlib.Path(source_path).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sha = full_sha256 or sha256_full(source_path)
    size = source_path.stat().st_size if source_path.exists() else 0

    content = (
        f"source_path: {source_path}\n"
        f"source_name: {source_path.name}\n"
        f"sha256: {sha}\n"
        f"size_bytes: {size}\n"
        f"first_extracted: {timestamp}\n"
    )
    if record_path.exists():
        existing = record_path.read_text(encoding="utf-8", errors="replace")
        # Preserve original first_extracted timestamp; refresh other fields if changed.
        if "source_path:" in existing:
            return
    record_path.write_text(content, encoding="utf-8")


def list_cache(root: pathlib.Path | None = None) -> list[dict]:
    """Return a list of cached extraction summaries.

    Each entry: {"sha12": str, "source_name": str, "source_path": str,
                 "first_extracted": str, "size_bytes": int, "stage_dir": Path}
    """
    root = pathlib.Path(root) if root else DEFAULT_STAGING_ROOT
    if not root.exists():
        return []
    entries = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        record = child / SOURCE_RECORD_FILENAME
        info = {"sha12": child.name, "stage_dir": child}
        if record.exists():
            try:
                for line in record.read_text(encoding="utf-8", errors="replace").splitlines():
                    if ": " in line:
                        k, v = line.split(": ", 1)
                        info[k.strip()] = v.strip()
            except OSError:
                pass
        entries.append(info)
    return entries


def clear_cache_entry(stage_dir: pathlib.Path) -> bool:
    """Delete a single cache entry (the staging dir for one source)."""
    import shutil
    if not stage_dir.exists():
        return False
    if not stage_dir.is_dir():
        return False
    shutil.rmtree(stage_dir, ignore_errors=False)
    return True
