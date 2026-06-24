"""Safe copy/move operations with metadata preservation.

Wraps dazzle_preservelib.operations behind a stable dz-facing API. The adapter
exists so dz can evolve independently of dazzle_preservelib's option/result
shape: if dazzle_preservelib renames or restructures fields, only the
translation helpers in this module change -- the public surface
(safe_cp, safe_mv, OpResult, ConflictPolicy) stays the same.

Design intent (see private/claude/2026-05-16__18-41-42__dev-workflow-process_dz-f-safe-mv-cp-tool.md):

- Safe by default: refuse-to-clobber, full metadata preservation, hash
  verification all default ON. Caller relaxes via explicit flags.
- safe_mv ALWAYS verifies. Verify is the gate for source deletion; you
  do not get to disable it. Use safe_cp + manual delete if you need
  unverified semantics.
- OpResult surfaces every safety-relevant signal (ctime_restored,
  cross_device, verify_failed, preflight_failed) so callers can render
  honest user-facing output and pick exit codes deterministically.
- PRESERVELIB_AVAILABLE is the hard-fail sentinel. If dazzle_preservelib is
  not installed, both operations refuse to run rather than silently
  fall back to shutil.copy2 -- the caller asked for SAFE ops, and we
  cannot deliver safe semantics without dazzle_preservelib's metadata work.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

# Hard-fail sentinel. If dazzle_preservelib cannot import, safe_cp/safe_mv
# return an OpResult with ok=False and a clear install instruction
# rather than degrading to lossy shutil-based ops.
try:
    from dazzle_preservelib.operations import copy_operation, move_operation  # noqa: F401
    PRESERVELIB_AVAILABLE = True
except ImportError:
    PRESERVELIB_AVAILABLE = False


class ConflictPolicy(Enum):
    """How to handle a destination that already exists.

    Maps 1:1 to dazzle_preservelib's ``on_conflict`` option values, which is
    why the .value strings match exactly. The enum exists so dz
    callers get type-checked policy selection instead of stringly-typed
    arguments.
    """

    SKIP = "skip"
    OVERWRITE = "overwrite"
    NEWER = "newer"
    LARGER = "larger"
    RENAME = "rename"
    FAIL = "fail"


# dz-convention exit codes (also documented in the design doc Section 5).
EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_VERIFY_FAILED_SOURCE_PRESERVED = 3  # mv only
EXIT_CONFLICT_NO_POLICY = 4
EXIT_PARTIAL = 5
EXIT_DRY_RUN_WOULD_FAIL = 64


@dataclass
class OpResult:
    """Outcome of a safe_cp or safe_mv call.

    Fields are deliberately granular: the CLI shim translates these
    flags into status-prefixed stdout and an exit code. Tests assert on
    individual fields so a regression in any safety invariant
    (ctime_restored, verify_failed, source-preserved-on-failure) shows
    up as a specific test failure, not a generic 'op failed'.
    """

    ok: bool
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    # True if ctime restoration was attempted AND succeeded for every
    # processed file. False if pywin32 is missing on Windows, or if
    # any file's ctime could not be restored. Always True on POSIX
    # (ctime is not settable; restoration is a no-op semantically).
    ctime_restored: bool = True
    # True if any operation crossed a device boundary (EXDEV). For mv
    # this triggers copy-then-delete semantics in dazzle_preservelib; we
    # surface it so the CLI can warn callers that the op was not
    # filesystem-level atomic.
    cross_device: bool = False
    # True if the post-copy hash verification failed for any file.
    # For mv, this MUST be False before any source is deleted; if True,
    # all sources are preserved.
    verify_failed: bool = False
    # True if preflight space/permission checks blocked the operation.
    preflight_failed: bool = False
    # True if this was a dry-run (no FS writes occurred).
    dry_run: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    exit_code: int = EXIT_OK


def _options_for(
    policy: ConflictPolicy,
    verify: bool,
    dry_run: bool,
    preserve_attrs: bool,
    hash_algorithm: str,
    check_space: bool,
    check_permissions: bool,
) -> dict:
    """Translate dz-facing args into dazzle_preservelib's options dict.

    See dazzle_preservelib.operations.copy_operation default_options for the
    full surface this maps to.
    """
    return {
        "on_conflict": policy.value,
        # overwrite is the legacy boolean; on_conflict supersedes it
        # for dazzle_preservelib >= 0.7.x. Setting both keeps older codepaths
        # in dazzle_preservelib doing the right thing if any still consult
        # overwrite directly.
        "overwrite": policy == ConflictPolicy.OVERWRITE,
        "verify": verify,
        "dry_run": dry_run,
        "preserve_attrs": preserve_attrs,
        "hash_algorithm": hash_algorithm,
        "check_space": check_space,
        "check_permissions": check_permissions,
        # path_style=flat matches POSIX mv/cp semantics: `mv src/a.txt
        # dst/` lands the file at `dst/a.txt`, not `dst/src/a.txt` and
        # certainly not `dst/<full-absolute-path-of-source>/a.txt`. The
        # preserve CLI defaults to "absolute" because its workflow is
        # backup/restore (which wants reconstructible source paths
        # under the dest root), but dz f-mv / f-cp are coreutils-style
        # tools -- the user expects flat placement.
        "path_style": "flat",
    }


@contextmanager
def _capture_dazzle_preservelib_warnings():
    """Attach a logging.Handler that captures WARN+ records from dazzle_preservelib.

    dazzle_preservelib's metadata layer uses ``logger.error()`` / ``.warning()``
    for non-fatal failures (e.g. SetFileSecurity Access Denied on
    Windows ACL preservation) and continues without populating
    OperationResult.error_messages. The user-visible symptom is bare
    stderr noise and an exit code that says "ok" while metadata was
    actually lost.

    This context manager attaches a handler that collects WARN+ records
    from the 'dazzle_preservelib' logger and its children. The records are
    returned in a list shared with the caller, who can then merge them
    into OpResult.warnings.

    The handler is removed on context exit regardless of exception.
    """
    captured: List[logging.LogRecord] = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                captured.append(record)
            except Exception:
                # If even appending fails, swallow -- we are not in the
                # business of breaking the underlying operation.
                pass

    handler = _CapturingHandler(level=logging.WARNING)
    target_logger = logging.getLogger("dazzle_preservelib")
    target_logger.addHandler(handler)
    # Ensure dazzle_preservelib's logger isn't filtered at a higher level.
    prior_level = target_logger.level
    if prior_level == logging.NOTSET or prior_level > logging.WARNING:
        target_logger.setLevel(logging.WARNING)
    try:
        yield captured
    finally:
        target_logger.removeHandler(handler)
        target_logger.setLevel(prior_level)


def _warnings_from_records(records: List[logging.LogRecord]) -> List[str]:
    """Convert captured log records into user-facing warning strings."""
    out: List[str] = []
    for r in records:
        try:
            msg = r.getMessage()
        except Exception:
            msg = str(r.msg)
        # Tag the originating logger so the user knows the warning came
        # from the underlying library, not from our adapter.
        out.append(f"{r.name}: {msg}")
    return out


# Patterns that indicate ctime / creation-time restoration failed in
# dazzle_preservelib's metadata layer. Heuristic matching against warning
# strings rather than re-importing dazzle_preservelib internals (which would
# couple this adapter to dazzle_preservelib's exception types).
_CTIME_FAILURE_PATTERNS = (
    "setfiletime",        # win32file.SetFileTime error
    "creation time",      # generic "failed to set creation time"
    "creation_time",
    "creationtime",
    "pywin32",            # "pywin32 not available"
    "win32file",          # win32file import / call failure
)


def _detect_ctime_failure(warnings: List[str]) -> bool:
    """Inspect captured warnings for signals that ctime restoration failed.

    Returns True if any warning matches a known ctime-failure pattern.
    Caller sets ``OpResult.ctime_restored`` based on this so the result
    is honest about what was preserved -- otherwise the field would
    always be True even when pywin32 is missing or SetFileTime errored.
    """
    for w in warnings:
        lower = w.lower()
        for pat in _CTIME_FAILURE_PATTERNS:
            if pat in lower:
                return True
    return False


def _finalize_op_result(result: OpResult) -> OpResult:
    """Update derived flags on an OpResult based on its current warnings.

    Called as the last step before any safe_cp/safe_mv return so the
    flags reflect ALL warnings accumulated during the operation
    (including ones added after the initial dazzle_preservelib log capture,
    e.g. source-deletion warnings in mv).

    Today this only updates ``ctime_restored``. Future derived flags
    (acl_preserved, ads_preserved, etc.) plug in here.
    """
    if _detect_ctime_failure(result.warnings):
        result.ctime_restored = False
    return result


def _is_rename_style(sources: List[str], dest: str) -> bool:
    """POSIX cp/mv rename detection.

    POSIX semantics:

    - ``cp src.txt newname.txt`` -- single source, dest doesn't exist,
      no trailing path separator -> POSIX treats dest as the NEW
      FILENAME (rename-style copy).
    - ``cp src.txt dst/`` (trailing /) -> directory-style.
    - ``cp src.txt existing_dir`` (dest exists as dir) -> directory-style.
    - ``cp s1 s2 dst`` (multiple sources) -> MUST be directory-style.

    dazzle_preservelib's ``path_style="flat"`` always treats dest as a
    directory and places files inside by basename. That breaks the
    rename case, which is the common ``cp old new`` pattern. This
    helper identifies the rename case so the adapter can route around
    dazzle_preservelib's directory-only assumption (copy to dest's parent,
    then rename the placed file).

    Returns True if the operation should be interpreted as a rename;
    False for directory-style (current dazzle_preservelib behavior).
    """
    if len(sources) != 1:
        return False
    if dest.endswith(("/", "\\")):
        return False
    if os.path.isdir(dest):
        return False
    if os.path.exists(dest):
        # Dest exists as a non-directory (a file). POSIX cp/mv overwrite
        # the existing file -- the user's conflict policy decides
        # whether to allow it. That's still rename-style semantics
        # (single target file), so we treat it as rename mode.
        return True
    # Dest doesn't exist, no trailing separator, single source -> rename.
    return True


@dataclass
class _RenameTarget:
    """Resolved paths for a rename-style operation.

    Captures the three derived paths the rename path needs:

    - ``parent_dir``: where dazzle_preservelib will place the file (absolute).
    - ``placed_path``: where the file lands BEFORE we rename it
      (parent_dir + source basename).
    - ``final_path``: where the file should be AFTER our rename
      (parent_dir + dest basename), or equivalently the user's
      original ``dest`` resolved absolutely.

    If source basename equals dest basename, ``placed_path ==
    final_path`` and the rename step is a no-op.
    """

    parent_dir: str
    placed_path: str
    final_path: str
    needs_rename: bool


def _resolve_rename_target(source: str, dest: str) -> _RenameTarget:
    """Compute the rename-mode paths for one source + one destination."""
    abs_dest = os.path.abspath(dest)
    parent_dir = os.path.dirname(abs_dest) or "."
    src_basename = os.path.basename(source)
    dest_basename = os.path.basename(abs_dest)
    placed_path = os.path.join(parent_dir, src_basename)
    return _RenameTarget(
        parent_dir=parent_dir,
        placed_path=placed_path,
        final_path=abs_dest,
        needs_rename=(src_basename != dest_basename),
    )


def _ensure_mkdir_p(target_dir: str) -> Optional[str]:
    """Create target_dir (and parents) if missing. Return error message or None."""
    try:
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        return None
    except OSError as exc:
        return f"mkdir failed for '{target_dir}': {exc}"


def _resolve_rename_conflict(
    source: str, final_path: str, policy: ConflictPolicy
) -> str:
    """Apply conflict policy at the rename-mode layer.

    Rename mode stages files in a tempdir, so dazzle_preservelib never sees
    the final destination -- which means dazzle_preservelib's conflict check
    is no help. We re-implement the policy here for the final-path
    conflict.

    Returns one of:
    - ``"proceed"``: caller should continue with overwrite semantics
      (existing final_path will be removed before rename).
    - ``"skip"``: caller should skip this file and return a skipped
      OpResult.
    - ``"fail"``: caller should return a conflict-failure OpResult
      (exit 4).
    """
    if not os.path.exists(final_path):
        return "proceed"
    if policy == ConflictPolicy.OVERWRITE:
        return "proceed"
    if policy == ConflictPolicy.SKIP:
        return "skip"
    if policy == ConflictPolicy.FAIL:
        return "fail"
    if policy == ConflictPolicy.NEWER:
        try:
            src_mtime = os.path.getmtime(source)
            dst_mtime = os.path.getmtime(final_path)
        except OSError:
            return "fail"
        return "proceed" if src_mtime > dst_mtime else "skip"
    if policy == ConflictPolicy.LARGER:
        try:
            src_size = os.path.getsize(source)
            dst_size = os.path.getsize(final_path)
        except OSError:
            return "fail"
        return "proceed" if src_size > dst_size else "skip"
    if policy == ConflictPolicy.RENAME:
        # "rename on conflict" is awkward when the user already
        # specified a target name. For v1: treat it like overwrite.
        # If callers want suffix-rename behavior here, they should
        # use a different policy.
        return "proceed"
    return "fail"


def _stage_and_finalize(
    source: str,
    final_path: str,
    parent_dir: str,
    options: dict,
    operation_label: str,
) -> "tuple[OpResult, List[logging.LogRecord]]":
    """Stage source in a tempdir under parent_dir, then rename to final_path.

    Used by both rename-mode safe_cp and rename-mode safe_mv. The
    tempdir lives inside parent_dir so the final ``os.rename`` is a
    same-volume atomic move (preserves metadata; no copy required).

    Returns ``(OpResult, captured_log_records)``. Caller adds any
    additional warning records and finalizes the dry_run / exit_code
    handling.
    """
    from dazzle_preservelib.operations import copy_operation

    # Create the tempdir AS a child of parent_dir so os.rename to
    # final_path is same-volume. tempfile.mkdtemp returns a unique
    # name, so dazzle_preservelib never sees a conflict in its dest dir.
    try:
        tmpdir = tempfile.mkdtemp(prefix=".dz-f-stage-", dir=parent_dir)
    except OSError as exc:
        return (
            OpResult(
                ok=False,
                files_failed=1,
                errors=[f"failed to create staging tempdir in '{parent_dir}': {exc}"],
                exit_code=EXIT_SYSTEM_ERROR,
            ),
            [],
        )

    try:
        try:
            with _capture_dazzle_preservelib_warnings() as captured:
                plib_result = copy_operation(
                    source_files=[source],
                    dest_base=tmpdir,
                    options=options,
                )
        except Exception as exc:
            return (
                OpResult(
                    ok=False,
                    files_failed=1,
                    errors=[
                        f"copy_operation raised: {type(exc).__name__}: {exc}"
                    ],
                    exit_code=EXIT_SYSTEM_ERROR,
                ),
                [],
            )

        result = _translate_result(plib_result, operation=operation_label)

        if not result.ok or result.verify_failed:
            # Don't move from staging if copy/verify didn't succeed.
            return result, list(captured)

        placed_path = os.path.join(tmpdir, os.path.basename(source))
        if not os.path.exists(placed_path):
            # dazzle_preservelib reported success but the placed file isn't
            # where we expect. Defensive: surface as error.
            result.ok = False
            result.errors.append(
                f"dazzle_preservelib reported success but no file at staging "
                f"path '{placed_path}'"
            )
            result.exit_code = EXIT_SYSTEM_ERROR
            return result, list(captured)

        # Move staged file to final destination. Same-volume rename is
        # atomic; preserves metadata fully (mtime/atime/ctime/ACLs).
        try:
            if os.path.exists(final_path):
                # Final exists because conflict resolution allowed
                # overwrite. Remove it so os.rename can land.
                os.remove(final_path)
            os.rename(placed_path, final_path)
        except OSError as exc:
            result.ok = False
            result.errors.append(
                f"copy succeeded to staging but final rename to "
                f"'{final_path}' failed: {exc}"
            )
            # For move operations this means source is preserved.
            if operation_label == "move":
                result.exit_code = EXIT_VERIFY_FAILED_SOURCE_PRESERVED
            else:
                result.exit_code = EXIT_SYSTEM_ERROR

        return result, list(captured)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _translate_result(
    plib_result,
    operation: str,
) -> OpResult:
    """Convert a dazzle_preservelib OperationResult into a dz OpResult.

    dazzle_preservelib's result object has fields like succeeded[], failed[],
    skipped[], verified[], unverified[], incorporated[], plus an
    error_messages dict. We collapse these into the granular flags
    callers care about and compute the dz exit code from them.
    """
    succeeded = len(getattr(plib_result, "succeeded", []) or [])
    failed = len(getattr(plib_result, "failed", []) or [])
    skipped = len(getattr(plib_result, "skipped", []) or [])
    incorporated = len(getattr(plib_result, "incorporated", []) or [])
    unverified = len(getattr(plib_result, "unverified", []) or [])

    errors = []
    error_messages = getattr(plib_result, "error_messages", {}) or {}
    for path, msg in error_messages.items():
        errors.append(f"{path}: {msg}")

    verify_failed = unverified > 0 or failed > 0
    files_processed = succeeded + incorporated

    if operation == "move" and verify_failed:
        exit_code = EXIT_VERIFY_FAILED_SOURCE_PRESERVED
    elif failed > 0 and succeeded > 0:
        exit_code = EXIT_PARTIAL
    elif failed > 0:
        exit_code = EXIT_SYSTEM_ERROR
    else:
        exit_code = EXIT_OK

    return OpResult(
        ok=(failed == 0 and not verify_failed),
        files_processed=files_processed,
        files_skipped=skipped,
        files_failed=failed,
        # ctime_restored: dazzle_preservelib does not currently surface this
        # per-file. v1 assumes True unless pywin32 import failed at
        # adapter load; the CLI shim can downgrade this if needed.
        ctime_restored=True,
        cross_device=False,  # dazzle_preservelib doesn't surface this either
        verify_failed=verify_failed,
        preflight_failed=False,  # set elsewhere if preflight raised
        errors=errors,
        exit_code=exit_code,
    )


def _refuse_without_dazzle_preservelib() -> OpResult:
    """Return a failure OpResult when dazzle_preservelib cannot be imported.

    No silent fallback: the caller asked for safe ops, and shutil.copy2
    cannot deliver ctime/ACL preservation. The error message includes
    the install command so the user can fix it immediately.
    """
    return OpResult(
        ok=False,
        files_processed=0,
        files_failed=0,  # not really "failed" -- the op did not start
        ctime_restored=False,
        verify_failed=False,
        preflight_failed=True,
        errors=[
            "dazzle-preservelib is not installed. "
            "Install via: pip install dazzle-preservelib"
        ],
        exit_code=EXIT_SYSTEM_ERROR,
    )


def _validate_multi_source_dest(
    sources: List[str], dest: str
) -> Optional[OpResult]:
    """Reject the POSIX-invalid case: multiple sources with a non-directory dest.

    POSIX: ``cp src1 src2 dst`` requires dst to be a directory (or end
    with /). If neither, it's a user error -- there's no sensible way
    to put two files at one non-directory path. Return an OpResult
    with EXIT_USER_ERROR; the caller surfaces it. None if validation
    passed.
    """
    if len(sources) > 1:
        if not os.path.isdir(dest) and not dest.endswith(("/", "\\")):
            return OpResult(
                ok=False,
                files_failed=len(sources),
                errors=[
                    f"target '{dest}' is not a directory "
                    f"(multiple sources require a directory destination)"
                ],
                exit_code=EXIT_USER_ERROR,
            )
    return None


def safe_cp(
    sources: List[str],
    dest: str,
    *,
    policy: ConflictPolicy = ConflictPolicy.FAIL,
    verify: bool = True,
    dry_run: bool = False,
    preserve_attrs: bool = True,
    hash_algorithm: str = "SHA256",
    check_space: bool = True,
    check_permissions: bool = True,
    mkdir_p: bool = False,
) -> OpResult:
    """Copy files to dest with full metadata preservation and clobber protection.

    Detects POSIX rename-style (single source + non-existent file dest
    without trailing /) and routes around dazzle_preservelib's directory-only
    flat-mode by copying to dest's parent and renaming the placed file.

    Args:
        sources: Source file paths.
        dest: Destination path. POSIX rules apply:
            - Trailing /: directory-style; sources land inside.
            - Existing directory: directory-style.
            - Existing file: rename-style (overwrite via conflict policy).
            - Doesn't exist + no trailing /: rename-style if single
              source, else error.
        policy: How to handle existing destinations. Default FAIL.
        verify: Hash-verify after copy. Default True.
        dry_run: Show plan without writing. Default False.
        preserve_attrs: Preserve mtime/atime/ctime/ACLs/attrs. Default True.
        hash_algorithm: SHA256 by default.
        check_space: Pre-flight disk space check. Default True.
        check_permissions: Pre-flight permission check. Default True.
        mkdir_p: Create missing destination directories. In rename
            mode, creates dest's PARENT directory (since dest itself
            is the new filename). In directory mode, creates dest.

    Returns:
        OpResult with granular safety flags and dz-convention exit code.
    """
    if not PRESERVELIB_AVAILABLE:
        return _refuse_without_dazzle_preservelib()

    err_result = _validate_multi_source_dest(sources, dest)
    if err_result is not None:
        return err_result

    rename_mode = _is_rename_style(sources, dest)

    if rename_mode:
        return _finalize_op_result(_safe_cp_rename_mode(
            source=sources[0],
            dest=dest,
            policy=policy,
            verify=verify,
            dry_run=dry_run,
            preserve_attrs=preserve_attrs,
            hash_algorithm=hash_algorithm,
            check_space=check_space,
            check_permissions=check_permissions,
            mkdir_p=mkdir_p,
        ))

    # Directory-mode: dazzle_preservelib places sources by basename under dest.
    if mkdir_p and not dry_run:
        mkdir_err = _ensure_mkdir_p(dest)
        if mkdir_err:
            return OpResult(
                ok=False,
                errors=[mkdir_err],
                exit_code=EXIT_SYSTEM_ERROR,
                dry_run=dry_run,
            )

    from dazzle_preservelib.operations import copy_operation

    options = _options_for(
        policy, verify, dry_run, preserve_attrs,
        hash_algorithm, check_space, check_permissions,
    )

    try:
        with _capture_dazzle_preservelib_warnings() as captured:
            plib_result = copy_operation(
                source_files=sources,
                dest_base=dest,
                options=options,
            )
    except Exception as exc:
        return OpResult(
            ok=False,
            files_failed=len(sources),
            verify_failed=False,
            preflight_failed=False,
            errors=[f"copy_operation raised: {type(exc).__name__}: {exc}"],
            exit_code=EXIT_SYSTEM_ERROR,
            dry_run=dry_run,
        )

    result = _translate_result(plib_result, operation="copy")
    result.warnings.extend(_warnings_from_records(captured))
    result.dry_run = dry_run
    if dry_run and result.exit_code != EXIT_OK:
        # In dry-run, a "would have failed" outcome maps to the
        # dedicated 64 code so CI gating can distinguish "dry-run
        # noticed a problem" from "real op failed."
        result.exit_code = EXIT_DRY_RUN_WOULD_FAIL
    return _finalize_op_result(result)


def _safe_cp_rename_mode(
    source: str,
    dest: str,
    *,
    policy: ConflictPolicy,
    verify: bool,
    dry_run: bool,
    preserve_attrs: bool,
    hash_algorithm: str,
    check_space: bool,
    check_permissions: bool,
    mkdir_p: bool,
) -> OpResult:
    """Rename-style copy: stage in tempdir, then rename to final name.

    Stages the copy in a tempdir under the destination's parent
    directory so:

    - dazzle_preservelib never sees the same-directory self-conflict that
      arises when the source lives in the destination dir (the
      copy-to-parent approach was naive about this).
    - The final ``os.rename`` from tempdir to final_path is a
      same-volume atomic operation -- preserves all metadata.
    - Conflict policy applies at THIS layer (dazzle_preservelib sees only
      an empty tempdir, so its conflict check is no help on
      final_path).
    """
    target = _resolve_rename_target(source, dest)

    if mkdir_p and not dry_run:
        mkdir_err = _ensure_mkdir_p(target.parent_dir)
        if mkdir_err:
            return OpResult(
                ok=False,
                errors=[mkdir_err],
                exit_code=EXIT_SYSTEM_ERROR,
                dry_run=dry_run,
            )

    # Apply conflict policy on final_path. We must do this BEFORE
    # calling dazzle_preservelib because dazzle_preservelib's conflict check looks
    # at its dest_base (the tempdir), not at our final destination.
    decision = _resolve_rename_conflict(source, target.final_path, policy)
    if decision == "fail":
        return OpResult(
            ok=False,
            files_failed=1,
            errors=[
                f"Conflict: destination '{dest}' exists "
                f"(--on-conflict={policy.value})"
            ],
            exit_code=EXIT_CONFLICT_NO_POLICY,
            dry_run=dry_run,
        )
    if decision == "skip":
        return OpResult(
            ok=True,
            files_skipped=1,
            warnings=[f"skipped '{source}' -> '{dest}' (--on-conflict={policy.value})"],
            exit_code=EXIT_OK,
            dry_run=dry_run,
        )

    # dry_run: report what would happen and stop (no FS writes).
    if dry_run:
        return OpResult(
            ok=True,
            files_processed=1,
            exit_code=EXIT_OK,
            dry_run=True,
            warnings=[f"would copy '{source}' -> '{dest}'"],
        )

    # Stage + finalize via tempdir.
    options = _options_for(
        policy, verify, dry_run, preserve_attrs,
        hash_algorithm, check_space, check_permissions,
    )
    result, captured = _stage_and_finalize(
        source=source,
        final_path=target.final_path,
        parent_dir=target.parent_dir,
        options=options,
        operation_label="copy",
    )
    result.warnings.extend(_warnings_from_records(captured))
    return result


def safe_mv(
    sources: List[str],
    dest: str,
    *,
    policy: ConflictPolicy = ConflictPolicy.FAIL,
    dry_run: bool = False,
    preserve_attrs: bool = True,
    hash_algorithm: str = "SHA256",
    check_space: bool = True,
    check_permissions: bool = True,
    mkdir_p: bool = False,
) -> OpResult:
    """Move files to dest with full metadata preservation and clobber protection.

    Move ALWAYS verifies. The hash check is the gate for source
    deletion: if verify fails for any file, all sources are preserved
    and the OpResult has exit_code=EXIT_VERIFY_FAILED_SOURCE_PRESERVED
    (3). There is no --no-verify on safe_mv; this is intentional.

    Detects POSIX rename-style (single source + non-existent file dest
    without trailing /). In rename mode the implementation uses
    copy_operation (not move_operation) so that the source is NOT
    deleted by dazzle_preservelib before our rename step runs. We then rename
    the placed file to its final name and delete the source ourselves.
    This preserves the safety invariant: source is removed only after
    copy + verify + rename ALL succeed.

    Args:
        sources: Source file paths.
        dest: Destination path. POSIX rules apply (see safe_cp).
        policy: How to handle existing destinations. Default FAIL.
        dry_run: Show plan without writing. Default False.
        preserve_attrs: Preserve mtime/atime/ctime/ACLs/attrs. Default True.
        hash_algorithm: SHA256 by default.
        check_space: Pre-flight disk space check. Default True.
        check_permissions: Pre-flight permission check. Default True.
        mkdir_p: Create missing destination directories. In rename
            mode, creates dest's PARENT directory.

    Returns:
        OpResult with granular safety flags and dz-convention exit code.
    """
    if not PRESERVELIB_AVAILABLE:
        return _refuse_without_dazzle_preservelib()

    err_result = _validate_multi_source_dest(sources, dest)
    if err_result is not None:
        return err_result

    rename_mode = _is_rename_style(sources, dest)

    if rename_mode:
        return _finalize_op_result(_safe_mv_rename_mode(
            source=sources[0],
            dest=dest,
            policy=policy,
            dry_run=dry_run,
            preserve_attrs=preserve_attrs,
            hash_algorithm=hash_algorithm,
            check_space=check_space,
            check_permissions=check_permissions,
            mkdir_p=mkdir_p,
        ))

    # Directory-style: dazzle_preservelib's move_operation handles atomically.
    if mkdir_p and not dry_run:
        mkdir_err = _ensure_mkdir_p(dest)
        if mkdir_err:
            return OpResult(
                ok=False,
                errors=[mkdir_err],
                exit_code=EXIT_SYSTEM_ERROR,
                dry_run=dry_run,
            )

    from dazzle_preservelib.operations import move_operation

    options = _options_for(
        policy, verify=True, dry_run=dry_run,
        preserve_attrs=preserve_attrs,
        hash_algorithm=hash_algorithm,
        check_space=check_space,
        check_permissions=check_permissions,
    )
    # Move-specific: force=False ensures dazzle_preservelib refuses to delete
    # source on verify failure. This is the safety invariant.
    options["force"] = False

    try:
        with _capture_dazzle_preservelib_warnings() as captured:
            plib_result = move_operation(
                source_files=sources,
                dest_base=dest,
                options=options,
            )
    except Exception as exc:
        return OpResult(
            ok=False,
            files_failed=len(sources),
            verify_failed=False,
            preflight_failed=False,
            errors=[f"move_operation raised: {type(exc).__name__}: {exc}"],
            exit_code=EXIT_SYSTEM_ERROR,
            dry_run=dry_run,
        )

    result = _translate_result(plib_result, operation="move")
    result.warnings.extend(_warnings_from_records(captured))
    result.dry_run = dry_run
    if dry_run and result.exit_code != EXIT_OK:
        result.exit_code = EXIT_DRY_RUN_WOULD_FAIL
    return _finalize_op_result(result)


def _safe_mv_rename_mode(
    source: str,
    dest: str,
    *,
    policy: ConflictPolicy,
    dry_run: bool,
    preserve_attrs: bool,
    hash_algorithm: str,
    check_space: bool,
    check_permissions: bool,
    mkdir_p: bool,
) -> OpResult:
    """Rename-style move: stage + rename + delete source, in that order.

    Decomposes dazzle_preservelib's atomic copy+verify+delete into three
    explicit steps so we can slip the rename between verify and
    delete. Uses the same tempdir staging helper as
    _safe_cp_rename_mode to avoid the same-directory self-conflict.

    Safety invariant: source is deleted ONLY after copy + verify +
    rename all succeed. Failure at any step preserves the source.
    """
    target = _resolve_rename_target(source, dest)

    if mkdir_p and not dry_run:
        mkdir_err = _ensure_mkdir_p(target.parent_dir)
        if mkdir_err:
            return OpResult(
                ok=False,
                errors=[mkdir_err],
                exit_code=EXIT_SYSTEM_ERROR,
                dry_run=dry_run,
            )

    # Conflict policy on final_path -- before staging.
    decision = _resolve_rename_conflict(source, target.final_path, policy)
    if decision == "fail":
        return OpResult(
            ok=False,
            files_failed=1,
            errors=[
                f"Conflict: destination '{dest}' exists "
                f"(--on-conflict={policy.value})"
            ],
            exit_code=EXIT_CONFLICT_NO_POLICY,
            dry_run=dry_run,
        )
    if decision == "skip":
        return OpResult(
            ok=True,
            files_skipped=1,
            warnings=[f"skipped '{source}' -> '{dest}' (--on-conflict={policy.value})"],
            exit_code=EXIT_OK,
            dry_run=dry_run,
        )

    if dry_run:
        return OpResult(
            ok=True,
            files_processed=1,
            exit_code=EXIT_OK,
            dry_run=True,
            warnings=[f"would move '{source}' -> '{dest}'"],
        )

    options = _options_for(
        policy, verify=True, dry_run=False,
        preserve_attrs=preserve_attrs,
        hash_algorithm=hash_algorithm,
        check_space=check_space,
        check_permissions=check_permissions,
    )

    # Stage + finalize. operation_label="move" so verify failures
    # report exit 3 (source preserved).
    result, captured = _stage_and_finalize(
        source=source,
        final_path=target.final_path,
        parent_dir=target.parent_dir,
        options=options,
        operation_label="move",
    )
    result.warnings.extend(_warnings_from_records(captured))

    # If copy/verify/rename succeeded, source still exists at its
    # original location. Delete it now -- the final step of the move.
    if result.ok and not result.verify_failed:
        try:
            os.remove(source)
        except OSError as exc:
            # Source deletion failure is a warning, not a fatal error:
            # the destination is correct; the source just wasn't removed.
            result.warnings.append(
                f"source deletion after successful move failed: {exc} "
                f"(destination is correct; source still exists at {source})"
            )

    return result
