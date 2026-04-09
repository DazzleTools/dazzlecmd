"""End-to-end roundtrip tests for safedel.

Tests: create files -> delete via safedel -> verify in trash -> recover -> verify restored.
Requires admin on Windows for symlink tests.
"""

import json
import os
import sys
import tempfile

_safedel_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _safedel_dir)
# _lib for preservelib, links dir for detect_link
sys.path.insert(0, os.path.join(_safedel_dir, "_lib"))
sys.path.insert(0, os.path.join(_safedel_dir, "..", "links"))

from _store import TrashStore
from _classifier import classify, FileType
from _platform import detect_platform


def _make_test_store():
    """Create a temporary trash store."""
    tmpdir = tempfile.mkdtemp(prefix="safedel_test_store_")
    return TrashStore(store_path=tmpdir), tmpdir


def test_regular_file_roundtrip():
    """Delete a regular file, verify in trash, recover, verify content."""
    store, store_dir = _make_test_store()

    with tempfile.TemporaryDirectory(prefix="safedel_test_") as workdir:
        # Create test file
        test_file = os.path.join(workdir, "hello.txt")
        with open(test_file, "w") as f:
            f.write("hello world")

        # Classify
        c = classify(test_file)
        assert c.file_type == FileType.REGULAR_FILE
        assert c.exists is True

        # Delete
        result = store.trash([test_file])
        assert result.success is True
        assert len(result.entries) == 1
        assert result.entries[0].file_type == "regular_file"

        # Verify original is gone
        assert not os.path.exists(test_file)

        # Verify in trash
        folders = store.list_entries()
        assert len(folders) == 1
        assert folders[0].entries[0].original_name == "hello.txt"

        # Check manifest exists
        manifest_path = os.path.join(
            store_dir, result.folder_name, "manifest.json"
        )
        assert os.path.isfile(manifest_path)
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["entries"][0]["file_type"] == "regular_file"
        assert manifest["entries"][0]["stat"]["st_size"] == 11

        # Recover
        from _recover import cmd_recover
        # Recover to a new location to avoid path conflicts
        recover_dir = os.path.join(workdir, "recovered")
        os.makedirs(recover_dir)

        class FakeArgs:
            pass

        rc = cmd_recover(
            store,
            positional_args=["last"],
            to_path=recover_dir,
        )
        assert rc == 0

        # Verify recovered content
        recovered_file = os.path.join(recover_dir, "hello.txt")
        assert os.path.isfile(recovered_file)
        with open(recovered_file) as f:
            assert f.read() == "hello world"

    # Cleanup store
    import shutil
    shutil.rmtree(store_dir, ignore_errors=True)


def test_directory_roundtrip():
    """Delete a directory tree, verify staging, recover."""
    store, store_dir = _make_test_store()

    with tempfile.TemporaryDirectory(prefix="safedel_test_") as workdir:
        # Create test dir with files
        test_dir = os.path.join(workdir, "mydir")
        os.makedirs(test_dir)
        with open(os.path.join(test_dir, "a.txt"), "w") as f:
            f.write("file a")
        with open(os.path.join(test_dir, "b.txt"), "w") as f:
            f.write("file b")

        # Classify
        c = classify(test_dir)
        assert c.file_type == FileType.REGULAR_DIR

        # Delete
        result = store.trash([test_dir])
        assert result.success is True

        # Verify original is gone
        assert not os.path.exists(test_dir)

        # Recover
        from _recover import cmd_recover
        recover_dir = os.path.join(workdir, "recovered")
        os.makedirs(recover_dir)
        rc = cmd_recover(store, positional_args=["last"], to_path=recover_dir)
        assert rc == 0

        # Verify recovered structure
        recovered_dir = os.path.join(recover_dir, "mydir")
        assert os.path.isdir(recovered_dir)
        with open(os.path.join(recovered_dir, "a.txt")) as f:
            assert f.read() == "file a"
        with open(os.path.join(recovered_dir, "b.txt")) as f:
            assert f.read() == "file b"

    import shutil
    shutil.rmtree(store_dir, ignore_errors=True)


def test_dry_run():
    """Dry run should not modify any files."""
    store, store_dir = _make_test_store()

    with tempfile.TemporaryDirectory(prefix="safedel_test_") as workdir:
        test_file = os.path.join(workdir, "keep_me.txt")
        with open(test_file, "w") as f:
            f.write("don't delete")

        result = store.trash([test_file], dry_run=True)
        assert result.success is True

        # File should still exist
        assert os.path.exists(test_file)
        with open(test_file) as f:
            assert f.read() == "don't delete"

        # Trash should be empty
        assert len(store.list_entries()) == 0

    import shutil
    shutil.rmtree(store_dir, ignore_errors=True)


def test_symlink_roundtrip():
    """Delete a symlink, verify target survives, recover symlink."""
    platform_info = detect_platform()

    # Symlinks on Windows require admin
    if platform_info.is_windows:
        # Test if we can create symlinks
        with tempfile.TemporaryDirectory(prefix="safedel_test_") as workdir:
            target = os.path.join(workdir, "target.txt")
            link = os.path.join(workdir, "link.txt")
            with open(target, "w") as f:
                f.write("target content")
            try:
                os.symlink(target, link)
            except OSError:
                print("  SKIP: symlink creation requires admin on Windows")
                return

    store, store_dir = _make_test_store()

    with tempfile.TemporaryDirectory(prefix="safedel_test_") as workdir:
        target = os.path.join(workdir, "target.txt")
        link = os.path.join(workdir, "sym_link.txt")

        with open(target, "w") as f:
            f.write("target content")
        os.symlink(target, link)

        # Classify
        c = classify(link)
        assert c.file_type == FileType.SYMLINK_FILE

        # Delete
        result = store.trash([link])
        assert result.success is True

        # Symlink gone, target survives
        assert not os.path.exists(link)
        assert os.path.isfile(target)
        with open(target) as f:
            assert f.read() == "target content"

        # Recover
        from _recover import cmd_recover
        rc = cmd_recover(store, positional_args=["last"])
        assert rc == 0

        # Symlink restored and points to target
        assert os.path.islink(link)
        with open(link) as f:
            assert f.read() == "target content"

    import shutil
    shutil.rmtree(store_dir, ignore_errors=True)


def test_multiple_files():
    """Delete multiple files in one operation."""
    store, store_dir = _make_test_store()

    with tempfile.TemporaryDirectory(prefix="safedel_test_") as workdir:
        files = []
        for name in ["a.txt", "b.txt", "c.txt"]:
            path = os.path.join(workdir, name)
            with open(path, "w") as f:
                f.write(f"content of {name}")
            files.append(path)

        result = store.trash(files)
        assert result.success is True
        assert len(result.entries) == 3

        # All gone
        for f in files:
            assert not os.path.exists(f)

        # All in one trash folder
        folders = store.list_entries()
        assert len(folders) == 1
        assert len(folders[0].entries) == 3

    import shutil
    shutil.rmtree(store_dir, ignore_errors=True)


def test_status():
    """Status command returns stats."""
    store, store_dir = _make_test_store()

    stats = store.get_stats()
    assert stats.total_folders == 0
    assert stats.total_entries == 0

    # Add something
    with tempfile.TemporaryDirectory(prefix="safedel_test_") as workdir:
        test_file = os.path.join(workdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("x" * 100)
        store.trash([test_file])

    stats = store.get_stats()
    assert stats.total_folders == 1
    assert stats.total_entries == 1
    assert stats.total_size_bytes == 100

    import shutil
    shutil.rmtree(store_dir, ignore_errors=True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    skipped = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS: {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
