"""Unit tests for _f_common.safe_ops.

These tests exercise the adapter in isolation: preservelib's
copy_operation and move_operation are mocked so we can assert on the
options dict we pass to them and the OpResult we translate back. The
goal is to catch regressions in the translation layer specifically --
integration tests with real preservelib live in projects/core/tests/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# The adapter lives in a sibling directory under projects/core/ and is
# imported by path because it has no manifest (intentionally -- it is
# not a dispatched dz tool, just a shared library).
_HERE = Path(__file__).resolve().parent
_ADAPTER_DIR = _HERE.parent
sys.path.insert(0, str(_ADAPTER_DIR.parent))  # add projects/core/ so '_f_common' resolves

from _f_common.safe_ops import (  # noqa: E402
    ConflictPolicy,
    OpResult,
    PRESERVELIB_AVAILABLE,
    safe_cp,
    safe_mv,
    _options_for,
    _translate_result,
    _is_rename_style,
    _resolve_rename_target,
    EXIT_OK,
    EXIT_USER_ERROR,
    EXIT_SYSTEM_ERROR,
    EXIT_VERIFY_FAILED_SOURCE_PRESERVED,
    EXIT_PARTIAL,
    EXIT_DRY_RUN_WOULD_FAIL,
)


# ---------------------------------------------------------------- enum tests

class TestConflictPolicy:
    """The enum values must match preservelib's on_conflict strings exactly.

    Any drift here means dz callers think they're skipping/overwriting
    but preservelib sees an unknown policy and falls back to its
    default. This is precisely the sort of silent breakage the adapter
    layer exists to catch.
    """

    def test_values_match_preservelib_on_conflict_vocabulary(self):
        # See preservelib/operations.py:891 "on_conflict": "Conflict resolution strategy
        # (skip, overwrite, newer, larger, rename, fail)"
        expected = {"skip", "overwrite", "newer", "larger", "rename", "fail"}
        actual = {p.value for p in ConflictPolicy}
        assert actual == expected


# ----------------------------------------------------------- translation tests

class TestOptionsFor:
    """The options dict handed to preservelib must reflect dz-facing args."""

    def test_on_conflict_string_from_enum(self):
        opts = _options_for(
            policy=ConflictPolicy.SKIP, verify=True, dry_run=False,
            preserve_attrs=True, hash_algorithm="SHA256",
            check_space=True, check_permissions=True,
        )
        assert opts["on_conflict"] == "skip"

    def test_overwrite_boolean_aligns_with_policy(self):
        # Legacy preservelib codepaths may still consult the 'overwrite'
        # bool. We set it only when the policy is OVERWRITE; never
        # otherwise.
        for policy, expected in [
            (ConflictPolicy.OVERWRITE, True),
            (ConflictPolicy.FAIL, False),
            (ConflictPolicy.SKIP, False),
            (ConflictPolicy.NEWER, False),
            (ConflictPolicy.LARGER, False),
            (ConflictPolicy.RENAME, False),
        ]:
            opts = _options_for(
                policy=policy, verify=True, dry_run=False,
                preserve_attrs=True, hash_algorithm="SHA256",
                check_space=True, check_permissions=True,
            )
            assert opts["overwrite"] is expected, f"policy={policy}"

    def test_dry_run_passes_through(self):
        opts = _options_for(
            policy=ConflictPolicy.FAIL, verify=True, dry_run=True,
            preserve_attrs=True, hash_algorithm="SHA256",
            check_space=True, check_permissions=True,
        )
        assert opts["dry_run"] is True

    def test_path_style_is_flat(self):
        # path_style=flat matches POSIX mv/cp semantics: source lands
        # at dest/<basename>, not at dest/<full-source-path>. preserve
        # defaults to "absolute" (for backup/restore round-trips) but
        # dz f-mv / f-cp are coreutils-style tools.
        opts = _options_for(
            policy=ConflictPolicy.FAIL, verify=True, dry_run=False,
            preserve_attrs=True, hash_algorithm="SHA256",
            check_space=True, check_permissions=True,
        )
        assert opts["path_style"] == "flat"


class TestTranslateResult:
    """preservelib's OperationResult -> dz OpResult mapping."""

    def _make_plib(
        self, succeeded=0, failed=0, skipped=0,
        incorporated=0, unverified=0, error_messages=None,
    ):
        r = MagicMock()
        r.succeeded = [("s", "d")] * succeeded
        r.failed = [("s", "d")] * failed
        r.skipped = [("s", "d")] * skipped
        r.incorporated = [("s", "d")] * incorporated
        r.unverified = [("s", "d")] * unverified
        r.error_messages = error_messages or {}
        return r

    def test_clean_copy_exits_zero(self):
        plib = self._make_plib(succeeded=3)
        result = _translate_result(plib, operation="copy")
        assert result.ok is True
        assert result.files_processed == 3
        assert result.exit_code == EXIT_OK
        assert result.verify_failed is False

    def test_clean_move_exits_zero(self):
        plib = self._make_plib(succeeded=2)
        result = _translate_result(plib, operation="move")
        assert result.ok is True
        assert result.exit_code == EXIT_OK

    def test_move_verify_failed_uses_exit_3_source_preserved_code(self):
        # Critical safety invariant: on mv, if any file failed to
        # verify, the exit code is 3 (source preserved). The CLI shim
        # uses this to render the appropriate warning.
        plib = self._make_plib(unverified=1)
        result = _translate_result(plib, operation="move")
        assert result.verify_failed is True
        assert result.exit_code == EXIT_VERIFY_FAILED_SOURCE_PRESERVED

    def test_copy_verify_failed_does_not_use_exit_3(self):
        # Exit 3 is move-specific. Copy with verify failure goes to
        # exit 2 (system error) because there is no source-preserved
        # invariant on copy -- the source was never going to be touched.
        plib = self._make_plib(unverified=1, failed=1)
        result = _translate_result(plib, operation="copy")
        assert result.verify_failed is True
        assert result.exit_code != EXIT_VERIFY_FAILED_SOURCE_PRESERVED

    def test_partial_success_uses_exit_5(self):
        plib = self._make_plib(succeeded=2, failed=1)
        result = _translate_result(plib, operation="copy")
        assert result.exit_code == EXIT_PARTIAL

    def test_error_messages_propagated(self):
        plib = self._make_plib(
            failed=1,
            error_messages={"a.txt": "permission denied"},
        )
        result = _translate_result(plib, operation="copy")
        assert any("permission denied" in e for e in result.errors)
        assert any("a.txt" in e for e in result.errors)

    def test_incorporated_counts_as_processed(self):
        # 'incorporated' = file at destination already had identical
        # hash, so no copy was needed but the file is part of the
        # successful manifest. From the user's perspective, the file
        # "got there."
        plib = self._make_plib(succeeded=1, incorporated=2)
        result = _translate_result(plib, operation="copy")
        assert result.files_processed == 3


# ------------------------------------------------------ refuse-without-preservelib

class TestRefuseWithoutPreservelib:
    """When preservelib is missing, ops refuse rather than silently degrade."""

    def test_safe_cp_refuses_with_install_instruction(self):
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", False):
            result = safe_cp(["src.txt"], "dst.txt")
        assert result.ok is False
        assert result.exit_code == EXIT_SYSTEM_ERROR
        assert any("pip install" in e for e in result.errors)

    def test_safe_mv_refuses_with_install_instruction(self):
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", False):
            result = safe_mv(["src.txt"], "dst.txt")
        assert result.ok is False
        assert result.exit_code == EXIT_SYSTEM_ERROR
        assert any("pip install" in e for e in result.errors)


# ------------------------------------------------------------------ safe_mv invariant

class TestSafeMvAlwaysVerifies:
    """safe_mv must NEVER pass verify=False through to preservelib.

    The verify gate is the safety invariant for source deletion. The
    function signature does not even expose a verify parameter --
    callers cannot disable it. These tests use a directory-style dest
    (``dst/``) to ensure the move_operation path is exercised. Rename
    mode uses copy_operation and is tested separately.
    """

    @pytest.mark.skipif(not PRESERVELIB_AVAILABLE, reason="preservelib not installed")
    def test_safe_mv_does_not_accept_verify_kwarg(self):
        # The signature explicitly omits verify. Passing it should
        # raise TypeError. (This guards against a future maintainer
        # adding verify to safe_mv's signature without realizing it
        # breaks the safety invariant.)
        with pytest.raises(TypeError):
            safe_mv(["s.txt"], "d.txt", verify=False)  # type: ignore

    def test_safe_mv_options_always_have_verify_true(self):
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.move_operation") as mock_move:
            mock_result = MagicMock()
            mock_result.succeeded = []
            mock_result.failed = []
            mock_result.skipped = []
            mock_result.incorporated = []
            mock_result.unverified = []
            mock_result.error_messages = {}
            mock_move.return_value = mock_result

            # Trailing slash forces directory mode, which uses
            # move_operation (not copy_operation as rename mode does).
            safe_mv(["s.txt"], "dst/")

            assert mock_move.called
            options = mock_move.call_args.kwargs.get("options") or mock_move.call_args[0][2]
            assert options["verify"] is True

    def test_safe_mv_options_force_is_false(self):
        # force=True would let preservelib delete the source even on
        # verify failure. We explicitly set force=False so the safety
        # invariant holds.
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.move_operation") as mock_move:
            mock_result = MagicMock()
            mock_result.succeeded = []
            mock_result.failed = []
            mock_result.skipped = []
            mock_result.incorporated = []
            mock_result.unverified = []
            mock_result.error_messages = {}
            mock_move.return_value = mock_result

            safe_mv(["s.txt"], "dst/")

            options = mock_move.call_args.kwargs.get("options") or mock_move.call_args[0][2]
            assert options["force"] is False


# -------------------------------------------------------------- dry-run mapping

class TestDryRunExitCode:
    """Dry-run that would have failed maps to exit 64 for CI gating."""

    def test_dry_run_clean_exits_zero(self):
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation") as mock_copy:
            mock_result = MagicMock()
            mock_result.succeeded = [("s", "d")]
            mock_result.failed = []
            mock_result.skipped = []
            mock_result.incorporated = []
            mock_result.unverified = []
            mock_result.error_messages = {}
            mock_copy.return_value = mock_result

            result = safe_cp(["s.txt"], "d.txt", dry_run=True)
            assert result.dry_run is True
            assert result.exit_code == EXIT_OK

    def test_dry_run_with_problems_uses_exit_64(self):
        # Directory-style dest so this hits the non-rename code path
        # where preservelib's failure result is what determines the
        # exit code. (Rename-mode dry-run short-circuits with a plan
        # report; the exit-64-on-problems case for rename mode would
        # be triggered by a conflict policy failing pre-stage, not by
        # preservelib returning a failed result.)
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation") as mock_copy:
            mock_result = MagicMock()
            mock_result.succeeded = []
            mock_result.failed = [("s", "d")]
            mock_result.skipped = []
            mock_result.incorporated = []
            mock_result.unverified = []
            mock_result.error_messages = {"s": "would fail"}
            mock_copy.return_value = mock_result

            # Trailing slash forces directory mode.
            result = safe_cp(["s.txt"], "dst/", dry_run=True)
            assert result.dry_run is True
            assert result.exit_code == EXIT_DRY_RUN_WOULD_FAIL


# ------------------------------------------------------- exception-path coverage

class TestExceptionFromPreservelib:
    """Unhandled exceptions from preservelib get translated, not propagated."""

    def test_safe_cp_translates_exception_to_OpResult(self):
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=RuntimeError("disk full")):
            result = safe_cp(["s.txt"], "d.txt")
            assert result.ok is False
            assert result.exit_code == EXIT_SYSTEM_ERROR
            assert any("RuntimeError" in e for e in result.errors)
            assert any("disk full" in e for e in result.errors)

    def test_safe_mv_translates_exception_to_OpResult(self):
        # Directory-style dest -> move_operation path. The trailing
        # slash is what routes through move_operation (rename mode
        # routes through copy_operation instead).
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.move_operation",
                   side_effect=OSError("permission denied")):
            result = safe_mv(["s.txt"], "dst/")
            assert result.ok is False
            assert result.exit_code == EXIT_SYSTEM_ERROR
            assert any("OSError" in e for e in result.errors)
            assert any("permission denied" in e for e in result.errors)


# ------------------------------------------------------ warning capture from preservelib

class TestPreservelibWarningCapture:
    """preservelib emits non-fatal failures (e.g. ACL preservation) via
    logger.error/.warning rather than populating OperationResult. The
    adapter must capture those records into OpResult.warnings so the
    CLI shim and JSON output can report them honestly.
    """

    def test_warnings_from_preservelib_logger_are_captured(self):
        import logging

        def fake_copy(*args, **kwargs):
            # Simulate preservelib logging a non-fatal ACL failure
            # mid-operation, then returning a "successful" result.
            preservelib_log = logging.getLogger("preservelib.metadata")
            preservelib_log.error(
                "Error applying security information to foo.txt: "
                "Access is denied."
            )
            r = MagicMock()
            r.succeeded = [("foo.txt", "dst/foo.txt")]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            return r

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=fake_copy):
            result = safe_cp(["foo.txt"], "dst/")

        # The op succeeded (exit 0, ok=True) but the warning IS
        # surfaced -- the CLI shim can render it as a [WARN] line.
        assert result.ok is True
        assert result.exit_code == EXIT_OK
        assert len(result.warnings) >= 1
        captured_msg = " ".join(result.warnings)
        assert "Access is denied" in captured_msg
        assert "preservelib" in captured_msg.lower()

    def test_no_warnings_means_clean_warnings_list(self):
        # When preservelib emits nothing at WARN+, warnings stays empty.
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation") as mock_copy:
            r = MagicMock()
            r.succeeded = [("a", "b")]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            mock_copy.return_value = r
            result = safe_cp(["a.txt"], "dst/")
        assert result.warnings == []


# ------------------------------------------------------ ctime_restored honesty

class TestCtimeRestoredHonesty:
    """ctime_restored must reflect reality, not always be True.

    preservelib's metadata layer logs SetFileTime / pywin32 failures
    via logger.error/.warning rather than populating
    OperationResult. The adapter captures those records into
    result.warnings AND inspects them to flip ctime_restored to False
    when a known failure pattern is present. Otherwise the field
    would always report True, lying about what was actually preserved.
    """

    def test_setfiletime_failure_in_warnings_flips_ctime_restored_false(self):
        import logging

        def fake_copy(*args, **kwargs):
            preservelib_log = logging.getLogger("preservelib.metadata")
            preservelib_log.error(
                "Error in SetFileTime for foo.txt: Access is denied"
            )
            r = MagicMock()
            r.succeeded = [("foo.txt", "dst/foo.txt")]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            return r

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=fake_copy):
            result = safe_cp(["foo.txt"], "dst/")

        assert result.ctime_restored is False
        # The op itself didn't fail -- ctime preservation failing is
        # a partial-preservation warning, not a fatal error. The user
        # sees both the success exit and the honest flag.
        assert result.ok is True

    def test_pywin32_missing_warning_flips_ctime_restored_false(self):
        import logging

        def fake_copy(*args, **kwargs):
            preservelib_log = logging.getLogger("preservelib.metadata")
            preservelib_log.warning(
                "pywin32 not available; skipping ctime restoration"
            )
            r = MagicMock()
            r.succeeded = [("foo.txt", "dst/foo.txt")]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            return r

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=fake_copy):
            result = safe_cp(["foo.txt"], "dst/")

        assert result.ctime_restored is False

    def test_no_ctime_warning_means_ctime_restored_true(self):
        # Clean op (no warnings about ctime / SetFileTime / pywin32):
        # ctime_restored stays at its default True.
        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation") as mock_copy:
            r = MagicMock()
            r.succeeded = [("a", "b")]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            mock_copy.return_value = r
            result = safe_cp(["a.txt"], "dst/")
        assert result.ctime_restored is True

    def test_unrelated_acl_warning_does_not_flip_ctime(self):
        # A warning about ACL preservation failure should NOT affect
        # ctime_restored -- they're separate metadata fields.
        import logging

        def fake_copy(*args, **kwargs):
            preservelib_log = logging.getLogger("preservelib.metadata")
            preservelib_log.error(
                "Error applying security information to foo.txt: "
                "Access is denied"
            )
            r = MagicMock()
            r.succeeded = [("foo.txt", "dst/foo.txt")]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            return r

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=fake_copy):
            result = safe_cp(["foo.txt"], "dst/")

        # ACL failure is captured as a warning, but ctime_restored is
        # still True (ACLs and ctime are independent).
        assert result.ctime_restored is True
        assert len(result.warnings) >= 1
        assert any("security information" in w.lower() for w in result.warnings)


# ----------------------------------------------------- POSIX rename-mode detection

class TestIsRenameStyle:
    """POSIX cp/mv rename detection (single source + non-dir dest)."""

    def test_single_source_nonexistent_dest_is_rename(self, tmp_path):
        src = tmp_path / "a.txt"
        src.write_text("x")
        dst = tmp_path / "newname.txt"
        # dst doesn't exist, no trailing /, single source -> rename
        assert _is_rename_style([str(src)], str(dst)) is True

    def test_single_source_existing_dir_dest_is_directory_style(self, tmp_path):
        src = tmp_path / "a.txt"
        src.write_text("x")
        dst = tmp_path / "subdir"
        dst.mkdir()
        # Dest exists as dir -> directory-style (file goes inside)
        assert _is_rename_style([str(src)], str(dst)) is False

    def test_trailing_slash_is_directory_style(self, tmp_path):
        # Trailing / always means directory-style, even if dest
        # doesn't exist yet.
        assert _is_rename_style(["src.txt"], "dst/") is False
        assert _is_rename_style(["src.txt"], "dst\\") is False

    def test_multiple_sources_is_directory_style(self, tmp_path):
        # Multiple sources MUST be directory-style; the safe_cp/mv
        # entry points will error if dest isn't a directory.
        assert _is_rename_style(["a", "b"], "dst") is False

    def test_existing_file_dest_is_still_rename(self, tmp_path):
        # If dest exists as a file, that's still rename-style -- the
        # user is overwriting one file with another. Conflict policy
        # decides what happens.
        src = tmp_path / "a.txt"
        src.write_text("x")
        dst = tmp_path / "b.txt"
        dst.write_text("y")
        assert _is_rename_style([str(src)], str(dst)) is True


class TestResolveRenameTarget:
    """_resolve_rename_target derives the three paths the rename path uses."""

    def test_different_basenames_needs_rename(self, tmp_path):
        src = str(tmp_path / "old.txt")
        dst = str(tmp_path / "new.txt")
        target = _resolve_rename_target(src, dst)
        assert target.needs_rename is True
        assert target.parent_dir == os.path.abspath(str(tmp_path))
        assert target.placed_path == os.path.join(target.parent_dir, "old.txt")
        assert target.final_path == os.path.abspath(dst)

    def test_same_basenames_no_rename_needed(self, tmp_path):
        # Source and dest have the same basename -> no rename step
        # required; preservelib will place at the right name itself.
        src = str(tmp_path / "subdir" / "file.txt")
        dst = str(tmp_path / "other" / "file.txt")
        target = _resolve_rename_target(src, dst)
        assert target.needs_rename is False


# ----------------------------------------------------- rename-mode safe_cp behavior

class TestSafeCpRenameMode:
    """safe_cp in POSIX rename mode: cp src.txt newname.txt -> file newname.txt."""

    def test_rename_mode_stages_in_tempdir_under_parent(self, tmp_path):
        # Set up a real source so the rename-mode detection sees it
        # and the post-stage os.rename has a real placed file.
        src = tmp_path / "a.txt"
        src.write_text("hello")
        dst = tmp_path / "renamed.txt"  # doesn't exist; no trailing /

        captured_calls = {}

        def fake_copy(source_files, dest_base, options=None, **_):
            captured_calls["source_files"] = source_files
            captured_calls["dest_base"] = dest_base
            captured_calls["options"] = options
            # Simulate preservelib placing the file under its source
            # basename inside whatever dest_base it was given.
            placed = Path(dest_base) / "a.txt"
            placed.write_text("hello")
            r = MagicMock()
            r.succeeded = [(str(src), str(placed))]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            return r

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=fake_copy):
            result = safe_cp([str(src)], str(dst))

        # preservelib received a tempdir INSIDE parent_dir, not the
        # parent_dir itself (avoids the self-conflict when source and
        # dest share a directory).
        parent_abs = os.path.abspath(str(tmp_path))
        assert captured_calls["dest_base"].startswith(parent_abs)
        assert captured_calls["dest_base"] != parent_abs
        # Tempdir prefix from _stage_and_finalize.
        assert ".dz-f-stage-" in captured_calls["dest_base"]
        # Final file landed at the user's requested name.
        assert dst.exists()
        assert dst.read_text() == "hello"
        # And the source is preserved (cp, not mv).
        assert src.exists()
        assert result.ok is True

    def test_directory_mode_passes_dest_as_is(self, tmp_path):
        # Trailing / on dest -> directory mode; preservelib gets the
        # exact dest the caller provided.
        src = tmp_path / "a.txt"
        src.write_text("hello")
        dst = tmp_path / "subdir/"
        (tmp_path / "subdir").mkdir()

        captured_calls = {}

        def fake_copy(source_files, dest_base, options=None, **_):
            captured_calls["dest_base"] = dest_base
            r = MagicMock()
            r.succeeded = [("a", "b")]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            return r

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=fake_copy):
            safe_cp([str(src)], str(dst))

        # Directory mode -> dest passed through unchanged.
        assert captured_calls["dest_base"] == str(dst)

    def test_multiple_sources_to_nondirectory_is_user_error(self, tmp_path):
        # POSIX: cp s1 s2 dst (where dst is not a directory) -> error.
        s1 = tmp_path / "a.txt"
        s2 = tmp_path / "b.txt"
        s1.write_text("x")
        s2.write_text("y")
        # Doesn't exist, doesn't end with /, multiple sources
        result = safe_cp([str(s1), str(s2)], str(tmp_path / "notadir"))
        assert result.ok is False
        assert result.exit_code == EXIT_USER_ERROR
        assert any("not a directory" in e for e in result.errors)


# ----------------------------------------------------- rename-mode safe_mv behavior

class TestSafeMvRenameMode:
    """safe_mv in POSIX rename mode: copy + rename + delete-source ordering.

    Safety invariant: source is deleted ONLY after copy + verify +
    rename all succeed. Failure at any step preserves the source.
    """

    def test_rename_mode_uses_copy_operation_not_move(self, tmp_path):
        # Critical: rename mode for mv uses copy_operation so the
        # source isn't deleted by preservelib before our rename runs.
        # We then delete the source manually as the final step.
        src = tmp_path / "a.txt"
        src.write_text("hello")
        dst = tmp_path / "renamed.txt"

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.move_operation") as mock_move, \
             patch("preservelib.operations.copy_operation") as mock_copy:
            r = MagicMock()
            r.succeeded = [(str(src), "placed")]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            mock_copy.return_value = r

            # Pre-create the "placed" file so the rename step can rename it.
            placed_dummy = tmp_path / "a.txt.placed_for_test"
            # Actually we need the rename to work, so let's not actually
            # trigger it: use a dst with same basename as src.
            same_name_dst = tmp_path / "subdir" / "a.txt"
            same_name_dst.parent.mkdir()
            safe_mv([str(src)], str(same_name_dst))

            # copy_operation was used; move_operation was NOT.
            assert mock_copy.called
            assert not mock_move.called

    def test_rename_mode_source_deleted_after_success(self, tmp_path):
        # End-to-end-ish: after copy succeeds and rename succeeds,
        # source is removed. We mock preservelib's copy to actually
        # produce a placed file so the rename + delete steps run.
        src = tmp_path / "a.txt"
        src.write_text("hello")
        dst = tmp_path / "renamed.txt"

        def fake_copy(source_files, dest_base, options=None, **_):
            placed = Path(dest_base) / "a.txt"
            placed.write_text("hello")
            r = MagicMock()
            r.succeeded = [(str(src), str(placed))]
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = []
            r.error_messages = {}
            return r

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=fake_copy):
            result = safe_mv([str(src)], str(dst))

        # All three steps completed: copy placed file, rename to final
        # name, delete source.
        assert result.ok is True
        assert dst.exists()
        assert not src.exists()

    def test_rename_mode_source_preserved_on_verify_failure(self, tmp_path):
        # Safety invariant: verify failure -> source NOT deleted.
        src = tmp_path / "a.txt"
        src.write_text("hello")
        dst = tmp_path / "renamed.txt"

        def fake_copy(source_files, dest_base, options=None, **_):
            # Place the file then mark it unverified.
            placed = Path(dest_base) / "a.txt"
            placed.write_text("hello")
            r = MagicMock()
            r.succeeded = []
            r.failed = []
            r.skipped = []
            r.incorporated = []
            r.unverified = [(str(src), str(placed))]
            r.error_messages = {"a.txt": "hash mismatch"}
            return r

        with patch("_f_common.safe_ops.PRESERVELIB_AVAILABLE", True), \
             patch("preservelib.operations.copy_operation",
                   side_effect=fake_copy):
            result = safe_mv([str(src)], str(dst))

        # Source MUST still exist (verify failed before rename + delete).
        assert src.exists()
        assert result.verify_failed is True
        assert result.exit_code == EXIT_VERIFY_FAILED_SOURCE_PRESERVED


# --------------------------------------------------------------- OpResult shape

class TestOpResultShape:
    """OpResult fields are part of the public API for CLI shims."""

    def test_required_fields_present(self):
        r = OpResult(ok=True)
        # If any of these attrs are missing, the f-mv/f-cp shims break.
        for attr in [
            "ok", "files_processed", "files_skipped", "files_failed",
            "ctime_restored", "cross_device", "verify_failed",
            "preflight_failed", "dry_run", "errors", "warnings",
            "exit_code",
        ]:
            assert hasattr(r, attr), f"OpResult missing {attr}"
