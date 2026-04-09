"""Tests for safedel _timepattern module."""

import datetime
import os
import sys
import tempfile

# Add safedel to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from _timepattern import (
    parse_folder_datetime,
    generate_folder_name,
    generate_unique_folder_name,
    time_pattern_to_glob,
    parse_age_filter,
    matches_age_filter,
    match_trash_folders,
    get_most_recent_folder,
    resolve_time_args,
)


def test_parse_folder_datetime():
    dt = parse_folder_datetime("2026-04-08__10-46-33")
    assert dt == datetime.datetime(2026, 4, 8, 10, 46, 33)

    # With suffix
    dt = parse_folder_datetime("2026-04-08__10-46-33_001")
    assert dt == datetime.datetime(2026, 4, 8, 10, 46, 33)

    # Invalid
    assert parse_folder_datetime("not-a-date") is None
    assert parse_folder_datetime("2026-04-08") is None


def test_generate_folder_name():
    dt = datetime.datetime(2026, 4, 8, 10, 46, 33)
    assert generate_folder_name(dt) == "2026-04-08__10-46-33"


def test_generate_unique_folder_name():
    with tempfile.TemporaryDirectory() as tmpdir:
        name1 = generate_unique_folder_name(tmpdir)
        os.makedirs(os.path.join(tmpdir, name1))
        name2 = generate_unique_folder_name(tmpdir)
        # Should get a suffix since name1 exists
        assert name2.startswith(name1[:19])  # Same second
        assert name1 != name2 or "_001" in name2


def test_time_pattern_to_glob():
    # "last" returns None (special)
    assert time_pattern_to_glob(["last"]) is None

    # "today" returns today's date
    today = datetime.date.today().strftime("%Y-%m-%d")
    assert time_pattern_to_glob(["today"]) == f"{today}__*"

    # "today 10:46"
    assert time_pattern_to_glob(["today", "10:46"]) == f"{today}__10-46-*"

    # Date only
    assert time_pattern_to_glob(["2026-04-08"]) == "2026-04-08__*"

    # Date + time
    assert time_pattern_to_glob(["2026-04-08", "10:46"]) == "2026-04-08__10-46-*"

    # Date + time with wildcard
    assert time_pattern_to_glob(["2026-04-08", "10:4*"]) == "2026-04-08__10-4*"

    # Date with wildcard
    assert time_pattern_to_glob(["2026-04-0*"]) == "2026-04-0*"

    # Empty args
    assert time_pattern_to_glob([]) == "*"


def test_parse_age_filter():
    op, delta = parse_age_filter(">30d")
    assert op == ">"
    assert delta == datetime.timedelta(days=30)

    op, delta = parse_age_filter(">=2h")
    assert op == ">="
    assert delta == datetime.timedelta(hours=2)

    op, delta = parse_age_filter("<7d")
    assert op == "<"
    assert delta == datetime.timedelta(days=7)


def test_matches_age_filter():
    now = datetime.datetime(2026, 4, 8, 12, 0, 0)
    old = datetime.datetime(2026, 3, 1, 12, 0, 0)  # 38 days ago
    recent = datetime.datetime(2026, 4, 8, 10, 0, 0)  # 2 hours ago

    assert matches_age_filter(old, ">", datetime.timedelta(days=30), now) is True
    assert matches_age_filter(recent, ">", datetime.timedelta(days=30), now) is False
    assert matches_age_filter(recent, "<", datetime.timedelta(days=1), now) is True


def test_match_trash_folders():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test folders
        folders = [
            "2026-04-01__10-00-00",
            "2026-04-08__10-46-33",
            "2026-04-08__14-22-55",
            "not-a-trash-folder",
        ]
        for f in folders:
            os.makedirs(os.path.join(tmpdir, f))

        # Match all
        result = match_trash_folders(tmpdir)
        assert len(result) == 3
        assert result[0] == "2026-04-01__10-00-00"  # Oldest first

        # Match by date pattern
        result = match_trash_folders(tmpdir, "2026-04-08__*")
        assert len(result) == 2

        # Match with wildcard time
        result = match_trash_folders(tmpdir, "2026-04-08__10-*")
        assert len(result) == 1
        assert result[0] == "2026-04-08__10-46-33"


def test_get_most_recent_folder():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "2026-04-01__10-00-00"))
        os.makedirs(os.path.join(tmpdir, "2026-04-08__14-22-55"))
        assert get_most_recent_folder(tmpdir) == "2026-04-08__14-22-55"

    # Empty dir
    with tempfile.TemporaryDirectory() as tmpdir:
        assert get_most_recent_folder(tmpdir) is None


def test_resolve_time_args_last():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "2026-04-08__14-22-55"))
        result = resolve_time_args(tmpdir, ["last"])
        assert result == ["2026-04-08__14-22-55"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS: {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
