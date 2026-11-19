"""The CLI over the common-base trash layout (dazzlecmd-lib 0.10.39).

Two same-named items in one call are both staged and both recovered, and
``recover`` refuses a stored file whose size no longer matches its record
unless ``--force-identity`` is given.

These need the 0.10.39 engine; with an older library installed the whole
file is skipped (the engine there refuses a same-name batch, which
test_cli_truth.py covers). Everything is under ``tmp_path``.
"""
import os
import sys

import pytest

import safedel
import dazzlecmd_lib.core.safedel as sd
from dazzlecmd_lib.core.safedel import _store

pytestmark = pytest.mark.skipif(
    not hasattr(_store, "CONTENT_LAYOUT"),
    reason="needs dazzlecmd-lib 0.10.39 (the common-base trash layout)")


def _write(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _last_line(out):
    return out.rstrip("\n").splitlines()[-1]


@pytest.fixture
def cli(tmp_path, monkeypatch, capsys):
    """``cli(argv)`` runs ``safedel.main`` on a temp store, nobody at the
    keyboard, copy-first off. Returns ``(exit code, stdout, stderr)``."""
    def run(argv):
        monkeypatch.setattr(
            safedel, "TrashStore",
            lambda: sd.TrashStore(store_path=str(tmp_path / "trash"),
                                  registry_path=str(tmp_path / "reg.json")))
        monkeypatch.setattr(safedel, "stdin_is_interactive", lambda: False)
        monkeypatch.setattr(safedel, "copy_first_settings",
                            lambda: ("off", 10 * 1024 * 1024))
        rc = safedel.main([str(a) for a in argv])
        out = capsys.readouterr()
        return rc, out.out, out.err
    return run


def _batch(tmp_path):
    return os.listdir(tmp_path / "trash")[0]


def test_two_same_named_files_in_one_call_are_both_staged(cli, tmp_path):
    a = _write(tmp_path / "src" / "a" / "x.json", b"AAA")
    b = _write(tmp_path / "src" / "b" / "x.json", b"BB")

    rc, out, err = cli(["--yes", a, b])

    assert rc == 0, (out, err)
    assert _last_line(out).startswith("safedel: STAGED 2")
    assert not a.exists() and not b.exists()
    content = tmp_path / "trash" / _batch(tmp_path) / "content"
    assert (content / "a" / "x.json").read_bytes() == b"AAA"
    assert (content / "b" / "x.json").read_bytes() == b"BB"


def test_and_both_come_back_where_they_were(cli, tmp_path):
    a = _write(tmp_path / "src" / "a" / "x.json", b"AAA")
    b = _write(tmp_path / "src" / "b" / "x.json", b"BB")
    cli(["--yes", a, b])

    rc, out, err = cli(["recover", _batch(tmp_path)])

    assert rc == 0, (out, err)
    assert (a.read_bytes(), b.read_bytes()) == (b"AAA", b"BB")


def test_recover_to_another_folder_keeps_them_apart(cli, tmp_path):
    a = _write(tmp_path / "src" / "a" / "x.json", b"AAA")
    b = _write(tmp_path / "src" / "b" / "x.json", b"BB")
    cli(["--yes", a, b])

    rc, out, err = cli(["recover", _batch(tmp_path), "--to", tmp_path / "back"])

    assert rc == 0, (out, err)
    assert (tmp_path / "back" / "a" / "x.json").read_bytes() == b"AAA"
    assert (tmp_path / "back" / "b" / "x.json").read_bytes() == b"BB"


def _tampered(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"original")
    cli(["--yes", f])
    stored = tmp_path / "trash" / _batch(tmp_path) / "content" / "a.txt"
    stored.write_bytes(b"shorter")              # changed while in the trash
    return f, stored


def test_a_stored_file_of_the_wrong_size_is_refused_and_kept(cli, tmp_path):
    f, stored = _tampered(cli, tmp_path)

    rc, out, err = cli(["recover", _batch(tmp_path)])

    assert rc == 1
    assert not f.exists() and stored.read_bytes() == b"shorter"
    assert "--force-identity" in err


def test_force_identity_recovers_it(cli, tmp_path):
    f, stored = _tampered(cli, tmp_path)

    rc, out, err = cli(["recover", _batch(tmp_path), "--force-identity"])

    assert rc == 0, (out, err)
    assert f.read_bytes() == b"shorter"
    assert "recovering anyway" in err
