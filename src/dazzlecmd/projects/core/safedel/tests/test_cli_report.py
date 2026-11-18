"""The delete report says what actually happened.

Found by the hand-run checklist for the 0.12.24 hotfix: after a same-name
batch, the report printed every item as "[OK]" directly under the errors
saying two of them were left in place, because the label came from the
classifier ("content can be preserved"), not from whether the item was
staged. The "Trash store:" line also named the central default store even
when the batch went to a per-volume store.

These build TrashResult/TrashEntry objects in memory -- no trash store is
read or written.
"""
import json
import os

import safedel
from dazzlecmd_lib.core.safedel import TrashEntry, TrashResult


def _entry(name, content_path, content_preserved=True, file_type="regular_file"):
    return TrashEntry(
        original_path=os.path.join("C:\\src", name),
        original_name=os.path.basename(name),
        file_type=file_type,
        content_preserved=content_preserved,
        content_path=content_path,
    )


def test_entry_status_reflects_what_happened():
    assert safedel._entry_status(_entry("a\\x.json", "content/x.json")) == "OK"
    assert safedel._entry_status(_entry("b\\x.json", None)) == "NOT staged -- left in place"
    link = _entry("lnk", None, content_preserved=False, file_type="symlink_file")
    assert safedel._entry_status(link) == "metadata only"


def test_report_marks_refused_items_and_names_the_real_store(capsys, tmp_path):
    store = tmp_path / ".safedel-trash"
    folder = store / "2026-11-10__00-00-00"
    result = TrashResult(
        success=False,
        folder_name=folder.name,
        folder_path=str(folder),
        entries=[_entry("a\\x.json", "content/x.json"),
                 _entry("b\\x.json", None),
                 _entry("c\\x.json", None)],
        errors=["Failed to stage C:\\src\\b\\x.json: already staged",
                "Failed to stage C:\\src\\c\\x.json: already staged"],
    )

    safedel._print_delete_report(result)
    out = capsys.readouterr().out

    assert out.count("[OK]") == 1
    assert out.count("[NOT staged -- left in place]") == 2
    assert f"Trash store: {store}" in out


def test_json_output_carries_the_same_status(capsys, tmp_path, monkeypatch):
    """--json gets a per-entry status, so scripts can tell refused items apart."""
    folder = tmp_path / "store" / "2026-11-10__00-00-00"
    result = TrashResult(
        success=False, folder_name=folder.name, folder_path=str(folder),
        entries=[_entry("a\\x.json", "content/x.json"), _entry("b\\x.json", None)],
        errors=["Failed to stage C:\\src\\b\\x.json: already staged"],
        staged_count=1, not_staged_count=1,
    )

    from dazzlecmd_lib.core.safedel import TrashPlan

    class _FakeStore:
        """Stands in for the store: nothing on disk is planned or moved."""
        def plan(self, paths, **kwargs):
            return TrashPlan(store_path=str(tmp_path / "store"))

        def execute(self, plan):
            return result

    monkeypatch.setattr(safedel, "stdin_is_interactive", lambda: False)
    monkeypatch.setattr(safedel, "copy_first_settings",
                        lambda: ("off", 10 * 1024 * 1024))

    args = safedel._build_delete_parser().parse_args(
        ["--json", "a-path", "b-path"])
    rc = safedel._do_delete(_FakeStore(), args, scopes=("noninteractive",),
                            yes_given=True)

    data = json.loads(capsys.readouterr().out)
    assert rc == 4                                    # partial: one of two
    assert data["exit_code"] == 4
    assert data["verdict"] == "safedel: PARTIAL staged 1, not staged 1"
    assert [e["status"] for e in data["entries"]] == ["OK", "NOT staged -- left in place"]
