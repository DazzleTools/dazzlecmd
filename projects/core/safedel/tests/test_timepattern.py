"""Tests for safedel _timepattern module."""

import datetime
import os
import tempfile

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
        assert name2.startswith(name1[:19])
        assert name1 != name2 or "_001" in name2


def test_time_pattern_last():
    assert time_pattern_to_glob(["last"]) is None


def test_time_pattern_today():
    today = datetime.date.today().strftime("%Y-%m-%d")
    assert time_pattern_to_glob(["today"]) == f"{today}__*"


def test_time_pattern_today_with_time():
    today = datetime.date.today().strftime("%Y-%m-%d")
    assert time_pattern_to_glob(["today", "10:46"]) == f"{today}__10-46-*"


def test_time_pattern_date_only():
    assert time_pattern_to_glob(["2026-04-08"]) == "2026-04-08__*"


def test_time_pattern_date_and_time():
    assert time_pattern_to_glob(["2026-04-08", "10:46"]) == "2026-04-08__10-46-*"


def test_time_pattern_wildcard_time():
    assert time_pattern_to_glob(["2026-04-08", "10:4*"]) == "2026-04-08__10-4*"


def test_time_pattern_wildcard_date():
    assert time_pattern_to_glob(["2026-04-0*"]) == "2026-04-0*"


def test_time_pattern_empty():
    assert time_pattern_to_glob([]) == "*"


def test_parse_age_filter_days():
    op, delta = parse_age_filter(">30d")
    assert op == ">"
    assert delta == datetime.timedelta(days=30)


def test_parse_age_filter_hours():
    op, delta = parse_age_filter(">=2h")
    assert op == ">="
    assert delta == datetime.timedelta(hours=2)


def test_parse_age_filter_less_than():
    op, delta = parse_age_filter("<7d")
    assert op == "<"
    assert delta == datetime.timedelta(days=7)


def test_matches_age_filter_old():
    now = datetime.datetime(2026, 4, 8, 12, 0, 0)
    old = datetime.datetime(2026, 3, 1, 12, 0, 0)
    assert matches_age_filter(old, ">", datetime.timedelta(days=30), now) is True


def test_matches_age_filter_recent():
    now = datetime.datetime(2026, 4, 8, 12, 0, 0)
    recent = datetime.datetime(2026, 4, 8, 10, 0, 0)
    assert matches_age_filter(recent, ">", datetime.timedelta(days=30), now) is False
    assert matches_age_filter(recent, "<", datetime.timedelta(days=1), now) is True


def test_match_trash_folders():
    with tempfile.TemporaryDirectory() as tmpdir:
        folders = [
            "2026-04-01__10-00-00",
            "2026-04-08__10-46-33",
            "2026-04-08__14-22-55",
            "not-a-trash-folder",
        ]
        for f in folders:
            os.makedirs(os.path.join(tmpdir, f))

        result = match_trash_folders(tmpdir)
        assert len(result) == 3
        assert result[0] == "2026-04-01__10-00-00"

        result = match_trash_folders(tmpdir, "2026-04-08__*")
        assert len(result) == 2

        result = match_trash_folders(tmpdir, "2026-04-08__10-*")
        assert len(result) == 1
        assert result[0] == "2026-04-08__10-46-33"


def test_get_most_recent_folder():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "2026-04-01__10-00-00"))
        os.makedirs(os.path.join(tmpdir, "2026-04-08__14-22-55"))
        assert get_most_recent_folder(tmpdir) == "2026-04-08__14-22-55"


def test_get_most_recent_folder_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        assert get_most_recent_folder(tmpdir) is None


def test_resolve_time_args_last():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "2026-04-08__14-22-55"))
        result = resolve_time_args(tmpdir, ["last"])
        assert result == ["2026-04-08__14-22-55"]
