"""Tests for Linux/macOS extended attribute (xattr) preservation.

Unix-only. Tests the capture/restore of xattrs via os.listxattr/getxattr/setxattr.
Skips on Windows and on filesystems that don't support xattrs.
"""

import base64
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="xattr tests are Unix-only"
)


def _xattr_supported(path: str) -> bool:
    """Check if the filesystem supports xattrs by attempting to set one."""
    try:
        os.setxattr(path, "user.safedel_test", b"x", follow_symlinks=False)
        os.removexattr(path, "user.safedel_test", follow_symlinks=False)
        return True
    except (OSError, AttributeError):
        return False


@pytest.fixture
def xattr_workdir(tmp_path):
    """Create a workdir and skip if xattrs aren't supported."""
    d = tmp_path / "work"
    d.mkdir()
    f = d / "probe.txt"
    f.write_text("probe")
    if not _xattr_supported(str(f)):
        pytest.skip("Filesystem does not support xattrs")
    f.unlink()
    return d


class TestCollectXattrs:
    def test_plain_file_no_xattrs(self, xattr_workdir):
        """A file with no xattrs should return empty dict."""
        from preservelib.metadata import _collect_unix_xattrs
        from pathlib import Path
        f = xattr_workdir / "plain.txt"
        f.write_text("content")
        assert _collect_unix_xattrs(Path(f)) == {}

    def test_file_with_user_xattr(self, xattr_workdir):
        """A file with a user.* xattr should be captured."""
        from preservelib.metadata import _collect_unix_xattrs
        from pathlib import Path
        f = xattr_workdir / "with_xattr.txt"
        f.write_text("content")
        os.setxattr(str(f), "user.mylabel", b"important")

        xattrs = _collect_unix_xattrs(Path(f))
        assert "user.mylabel" in xattrs
        # Value should be base64-encoded
        decoded = base64.b64decode(xattrs["user.mylabel"])
        assert decoded == b"important"


class TestApplyXattrs:
    def test_apply_restores_xattrs(self, xattr_workdir):
        """Applying xattrs from a dict should restore them."""
        from preservelib.metadata import _apply_unix_xattrs
        from pathlib import Path
        f = xattr_workdir / "restore.txt"
        f.write_text("content")

        xattrs_dict = {
            "user.label1": base64.b64encode(b"value1").decode("ascii"),
            "user.label2": base64.b64encode(b"value2").decode("ascii"),
        }
        result = _apply_unix_xattrs(Path(f), xattrs_dict)
        assert result is True

        # Verify both were set
        assert os.getxattr(str(f), "user.label1") == b"value1"
        assert os.getxattr(str(f), "user.label2") == b"value2"

    def test_apply_skips_quarantine(self, xattr_workdir):
        """com.apple.quarantine should NOT be restored."""
        from preservelib.metadata import _apply_unix_xattrs
        from pathlib import Path
        f = xattr_workdir / "quarantine.txt"
        f.write_text("content")

        xattrs_dict = {
            "user.normal": base64.b64encode(b"ok").decode("ascii"),
            "com.apple.quarantine": base64.b64encode(b"0081;abcd;Browser;").decode("ascii"),
        }
        _apply_unix_xattrs(Path(f), xattrs_dict)

        # user.normal was applied
        assert os.getxattr(str(f), "user.normal") == b"ok"
        # quarantine was NOT applied
        names = os.listxattr(str(f))
        assert "com.apple.quarantine" not in names


class TestRoundtrip:
    def test_xattr_preserved_through_roundtrip(self, tmp_path, xattr_workdir):
        """End-to-end: create file with xattr, delete via safedel, recover."""
        from _store import TrashStore
        from _recover import cmd_recover

        store = TrashStore(
            store_path=str(tmp_path / "trash"),
            registry_path=str(tmp_path / "volumes.json"),
        )

        f = xattr_workdir / "roundtrip.txt"
        f.write_text("content")
        os.setxattr(str(f), "user.color", b"blue")
        os.setxattr(str(f), "user.tag", b"important")

        # Delete
        store.trash([str(f)])
        assert not f.exists()

        # Recover
        rc = cmd_recover(store, positional_args=["last"])
        assert rc == 0
        assert f.exists()

        # Verify xattrs restored
        names = set(os.listxattr(str(f)))
        assert "user.color" in names
        assert "user.tag" in names
        assert os.getxattr(str(f), "user.color") == b"blue"
        assert os.getxattr(str(f), "user.tag") == b"important"
