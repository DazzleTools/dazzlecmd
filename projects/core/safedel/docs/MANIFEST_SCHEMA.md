# safedel Manifest Schema Reference

Every safedel deletion creates a timestamped folder in the trash store
containing a `manifest.json` file that records everything needed to
recover the deleted item and its metadata. This document describes the
schema so you can inspect manifests by hand or build tools that work
with them.

## File Layout

Each trash folder is structured as:

```
<trash_store>/
    2026-04-10__06-12-27/           # Timestamped folder
        manifest.json               # This file
        content/                    # Actual file data (if preserved)
            <original_name>
            <original_name_2>
            ...
```

The folder name is `YYYY-MM-DD__hh-mm-ss` and serves as the primary
index -- time-pattern queries match against these names directly with
glob patterns. Collisions get a `_001`, `_002` suffix.

## Top-Level Schema

```json
{
    "version": 1,
    "safedel_version": "0.7.8",
    "deleted_at": "2026-04-10T06:12:27.123456",
    "folder_name": "2026-04-10__06-12-27",
    "platform": { ... },
    "entries": [ ... ]
}
```

### Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `version` | integer | Manifest schema version. Currently 1. Increment on breaking changes. |
| `safedel_version` | string | Version of safedel that wrote the manifest. Useful for debugging cross-version compat. |
| `deleted_at` | string | ISO 8601 timestamp of when the deletion occurred. |
| `folder_name` | string | The timestamped folder name. Redundant with the parent directory name but useful for orphan detection. |
| `platform` | object | Platform info (see below). |
| `entries` | array | List of deleted items (see below). |

### `platform` object

```json
{
    "system": "Windows",
    "platform": "win32",
    "is_wsl": false,
    "wsl_distro": null,
    "python_version": "3.12.0",
    "hostname": "MYPC"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `system` | string | `platform.system()`: "Windows", "Linux", "Darwin" |
| `platform` | string | `sys.platform`: "win32", "linux", "darwin" |
| `is_wsl` | boolean | True if running in WSL (detected via `WSL_DISTRO_NAME` or `/proc/version`) |
| `wsl_distro` | string or null | WSL distro name if applicable |
| `python_version` | string | Python version that wrote the manifest |
| `hostname` | string | Machine hostname |

## Entry Schema

Each element in the `entries` array describes one deleted item:

```json
{
    "original_path": "C:\\temp\\test.txt",
    "original_path_alt": "/mnt/c/temp/test.txt",
    "original_name": "test.txt",
    "file_type": "regular_file",
    "link_target": null,
    "link_broken": false,
    "link_count": 1,
    "is_dir": false,
    "content_preserved": true,
    "content_path": "content/test.txt",
    "delete_method": "os.unlink",
    "stat": { ... },
    "metadata": { ... },
    "warnings": []
}
```

### Entry fields

| Field | Type | Description |
|-------|------|-------------|
| `original_path` | string | Path where the file lived before deletion, in the native form for the runtime that created the manifest |
| `original_path_alt` | string or null | Alternate-platform form of the path (e.g., `/mnt/c/...` when `original_path` is `C:\...`). Used for cross-runtime recovery (WSL <-> Windows). Null when no sensible conversion exists. |
| `original_name` | string | Basename of the original file |
| `file_type` | string | Classification (see File Types below) |
| `link_target` | string or null | For links, the path the link points to |
| `link_broken` | boolean | True if the link target didn't exist at deletion time |
| `link_count` | integer | Hardlink count at deletion. Relevant for `file_type: "hardlink"` |
| `is_dir` | boolean | True if the entry is a directory (including dir symlinks and junctions) |
| `content_preserved` | boolean | True if file content was staged; false for links where only metadata was captured |
| `content_path` | string or null | Relative path to staged content within the trash folder (e.g., `"content/test.txt"`). Null when no content was preserved. |
| `delete_method` | string | Which OS call was used to delete the original: `"os.unlink"`, `"os.rmdir"`, `"shutil.rmtree"`, `"rename (moved to trash)"` |
| `stat` | object | Raw stat results (see Stat Schema below) |
| `metadata` | object or null | Preservelib metadata dict (see Metadata Schema below) |
| `warnings` | array of strings | Warnings emitted during classification or staging |

### File types

Values in the `file_type` field:

| Value | Meaning |
|-------|---------|
| `regular_file` | Ordinary file, deleted via `os.unlink` |
| `regular_dir` | Directory with contents, deleted via `shutil.rmtree` |
| `empty_dir` | Empty directory, deleted via `os.rmdir` |
| `symlink_file` | Symlink to a file; deleted via `os.unlink` (all platforms) |
| `symlink_dir` | Symlink to a directory; deleted via `os.rmdir` on Windows, `os.unlink` elsewhere |
| `junction` | Windows junction; deleted via `os.rmdir` ONLY (never `shutil.rmtree`) |
| `hardlink` | File with `st_nlink > 1`; deleted via `os.unlink` (removes one entry, data survives) |
| `shortcut` | `.lnk` Windows Shell Link file |
| `url_shortcut` | `.url` Internet Shortcut file |
| `dazzlelink` | `.dazzlelink` JSON descriptor file |
| `broken_link` | Link whose target doesn't exist |
| `unknown` | Unclassified (e.g., device files, sockets) |

## Stat Schema

The `stat` object contains raw values from `os.lstat()`:

```json
{
    "st_size": 12345,
    "st_mtime": 1775793943.0,
    "st_atime": 1775793943.0,
    "st_ctime": 1775793943.0,
    "st_mode": 33206,
    "st_nlink": 1,
    "st_ino": 281474976710659,
    "st_file_attributes": 32,
    "st_birthtime": 1775793943.0,
    "st_uid": 1000,
    "st_gid": 1000
}
```

| Field | Always present? | Description |
|-------|----------------|-------------|
| `st_size` | Yes | File size in bytes |
| `st_mtime` | Yes | Last modification time (epoch float) |
| `st_atime` | Yes | Last access time (epoch float) |
| `st_ctime` | Yes | Inode change time (Unix) or creation time (Windows) |
| `st_mode` | Yes | File type + permission bits |
| `st_nlink` | Yes | Number of hardlinks to this inode |
| `st_ino` | Yes | Inode number (0 on some Windows filesystems) |
| `st_file_attributes` | Windows only | Windows file attribute flags (readonly, hidden, system, archive, reparse point, etc.) |
| `st_birthtime` | macOS/BSD only | File creation time (Linux usually doesn't expose this) |
| `st_uid` | Unix only | Owner user ID |
| `st_gid` | Unix only | Owner group ID |

## Metadata Schema (preservelib format)

The `metadata` field contains a preservelib metadata dict, which has a
richer structure than `stat`:

```json
{
    "mode": 33206,
    "timestamps": {
        "modified": 1775793943.0,
        "accessed": 1775793943.0,
        "created": 1775793943.0,
        "modified_iso": "2026-04-09T20:26:26.123456",
        "accessed_iso": "2026-04-09T20:26:26.123456",
        "created_iso": "2026-04-09T20:26:26.123456"
    },
    "size": 12345,
    "windows": { ... },
    "unix": { ... },
    "xattrs": { ... }
}
```

### Windows metadata subsection

Present when running on Windows:

```json
{
    "windows": {
        "attributes": 32,
        "is_hidden": false,
        "is_system": false,
        "is_readonly": false,
        "is_archive": true,
        "owner": "MYPC\\Extreme",
        "group": "MYPC\\None",
        "security_descriptor_sddl": "O:S-1-5-21-...G:S-1-5-21-...D:AI(A;;FA;;;S-1-5-...)"
    }
}
```

| Field | Description |
|-------|-------------|
| `attributes` | Raw Windows file attribute bitmask |
| `is_hidden`, `is_system`, `is_readonly`, `is_archive` | Decoded attribute booleans |
| `owner`, `group` | Human-readable owner/group (from pywin32) |
| `owner_sid`, `group_sid` | Raw SID strings (fallback if lookup fails) |
| `security_descriptor_sddl` | Full security descriptor as an SDDL string (JSON-serializable form of the ACL). On recovery, converted back via `ConvertStringSecurityDescriptorToSecurityDescriptor`. |
| `attrib_output` | Output of `attrib` command (fallback when pywin32 not available) |

### Unix metadata subsection

Present when running on Linux/macOS:

```json
{
    "unix": {
        "uid": 1000,
        "gid": 1000
    }
}
```

### Extended attributes (xattrs)

Present when running on Linux/macOS and the file has xattrs:

```json
{
    "xattrs": {
        "user.color": "Ymx1ZQ==",
        "user.tag": "aW1wb3J0YW50"
    }
}
```

Each value is base64-encoded bytes. On recovery, decoded and restored via
`os.setxattr`. `com.apple.quarantine` is intentionally skipped on restore
to avoid Gatekeeper side-effects.

## Complete Example

A manifest for a Windows regular file deletion:

```json
{
    "version": 1,
    "safedel_version": "0.7.8",
    "deleted_at": "2026-04-09T20:26:26.123456",
    "folder_name": "2026-04-09__20-26-26",
    "platform": {
        "system": "Windows",
        "platform": "win32",
        "is_wsl": false,
        "wsl_distro": null,
        "python_version": "3.12.0",
        "hostname": "MYPC"
    },
    "entries": [
        {
            "original_path": "C:\\temp\\test.txt",
            "original_path_alt": "/mnt/c/temp/test.txt",
            "original_name": "test.txt",
            "file_type": "regular_file",
            "link_target": null,
            "link_broken": false,
            "link_count": 1,
            "is_dir": false,
            "content_preserved": true,
            "content_path": "content/test.txt",
            "delete_method": "os.unlink",
            "stat": {
                "st_size": 12,
                "st_mtime": 1775793943.0,
                "st_atime": 1775793943.0,
                "st_ctime": 1718445600.0,
                "st_mode": 33206,
                "st_nlink": 1,
                "st_ino": 281474976710659,
                "st_file_attributes": 32
            },
            "metadata": {
                "mode": 33206,
                "timestamps": {
                    "modified": 1775793943.0,
                    "accessed": 1775793943.0,
                    "created": 1718445600.0,
                    "modified_iso": "2026-04-09T20:26:26",
                    "accessed_iso": "2026-04-09T20:26:26",
                    "created_iso": "2024-06-15T10:00:00"
                },
                "size": 12,
                "windows": {
                    "attributes": 32,
                    "is_hidden": false,
                    "is_system": false,
                    "is_readonly": false,
                    "is_archive": true,
                    "owner": "MYPC\\Extreme",
                    "group": "MYPC\\None",
                    "security_descriptor_sddl": "O:S-1-5-21-...G:S-1-5-...D:AI(...)"
                }
            },
            "warnings": []
        }
    ]
}
```

## Inspecting Manifests by Hand

### Find the manifest for a specific deletion

```bash
# List all stores
dz safedel status

# Central store (Windows)
ls "%LOCALAPPDATA%\safedel\trash\"

# Per-volume store (Windows, typical location)
ls "C:\Users\<user>\.safedel-trash\"

# Linux/macOS
ls ~/.safedel/trash/
ls /<mountpoint>/.safedel-trash-$(id -u)/
```

### Dump a manifest

```bash
cat "C:\Users\<user>\.safedel-trash\2026-04-09__20-26-26\manifest.json" | python -m json.tool
```

### Extract specific fields with jq

```bash
# Get original paths of all entries
jq '.entries[].original_path' manifest.json

# Get files with specific file_type
jq '.entries[] | select(.file_type == "junction")' manifest.json

# Find entries with warnings
jq '.entries[] | select(.warnings | length > 0)' manifest.json

# Get total size
jq '[.entries[].stat.st_size] | add' manifest.json
```

### Rebuild a missing index from manifests

If the volume registry (`~/.safedel/volumes.json`) is corrupted, safedel
can rediscover entries by scanning trash folder names directly. The
manifests are self-contained -- each one has everything needed to describe
its deletion.

## Schema Evolution

### Versioning policy

- **`version: 1`** -- Initial schema (Phase 1 through 3c)
- Future versions will increment when fields are **removed or renamed**.
  Adding new optional fields does NOT require a version bump.

### Backward compatibility

safedel's loader is forgiving:

- Unknown fields are preserved in round-trip read-modify-write
- Missing optional fields fall back to defaults
- `original_path_alt` was added in Phase 3b; older manifests without it
  still load and recover correctly (alt fallback just doesn't trigger)

### Adding a new field

1. Add the field to the `TrashEntry` dataclass in `_store.py`
2. Add it to `_entry_to_dict()` for serialization
3. Add `e_dict.get("new_field")` to `_load_trash_folder()` for loading
4. Don't bump `version` unless removing or renaming existing fields
5. Update this document

## Privacy Note

Manifests record the following potentially sensitive information:

- **Full file paths** including user home directories and project names
- **File sizes** which may leak content information
- **Owner SIDs/UIDs** which identify specific users
- **Hostname** where the deletion happened
- **Security descriptors** (Windows ACLs)

If sharing manifests for debugging, consider redacting these fields or
synthesizing example data. The manifest itself does NOT contain file
content (content lives separately in `content/`).
