"""Unit tests for dazzle-update's scancache.py.

Covers save/load roundtrip, max_age refusal (a stale answer presented as
current is exactly the failure this cache layer exists to prevent),
schema-version mismatch, corrupt-file tolerance, and format_age(). No
coverage existed before this session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_TOOL_DIR = _HERE.parent
sys.path.insert(0, str(_TOOL_DIR))

import scancache  # noqa: E402


# -- save / load roundtrip ---------------------------------------------------

class TestSaveLoadRoundtrip:
    def test_roundtrip_preserves_records_and_meta(self, tmp_path):
        path = str(tmp_path / "scan.json")
        records = {"org/proj": {"key": "org/proj", "full_name": "Org/proj"}}
        meta = {"roots": ["C:/code"], "clean": 3}
        ok, err = scancache.save(records, meta, path=path, now=1000.0)
        assert ok is True
        assert err is None

        loaded_records, loaded_meta, age, load_err = scancache.load(
            path=path, now=1005.0)
        assert load_err is None
        assert loaded_records == records
        assert loaded_meta == meta
        assert age == pytest.approx(5.0)

    def test_save_creates_parent_directories(self, tmp_path):
        path = str(tmp_path / "a" / "b" / "scan.json")
        ok, err = scancache.save({}, {}, path=path)
        assert ok is True
        assert Path(path).is_file()

    def test_save_writes_atomically_no_leftover_tmp_file(self, tmp_path):
        path = str(tmp_path / "scan.json")
        ok, err = scancache.save({"x": 1}, {}, path=path)
        assert ok is True
        assert not (tmp_path / "scan.json.tmp").exists()
        assert Path(path).is_file()

    def test_save_uses_default_path_when_none_given(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ok, err = scancache.save({}, {}, path=None)
        assert ok is True
        assert Path(scancache.default_path()).is_file()

    def test_save_non_json_serializable_value_uses_str_fallback(self, tmp_path):
        """json.dump(..., default=str) means an odd value type doesn't
        blow up the save -- it's stringified instead."""
        path = str(tmp_path / "scan.json")

        class Weird:
            def __str__(self):
                return "weird-value"

        ok, err = scancache.save({"k": Weird()}, {}, path=path)
        assert ok is True
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["records"]["k"] == "weird-value"

    def test_save_oserror_is_not_fatal_returns_false(self, tmp_path, monkeypatch):
        path = str(tmp_path / "scan.json")

        def _boom(*a, **kw):
            raise OSError("simulated disk full")

        monkeypatch.setattr(scancache.os, "makedirs", _boom)
        ok, err = scancache.save({}, {}, path=path)
        assert ok is False
        assert "simulated disk full" in err


# -- load() edge cases --------------------------------------------------------

class TestLoad:
    def test_missing_file_reports_specific_error(self, tmp_path):
        path = str(tmp_path / "does-not-exist.json")
        records, meta, age, err = scancache.load(path=path)
        assert records is None
        assert meta is None
        assert age is None
        assert err == "no cached scan found"

    def test_corrupt_json_is_tolerated_not_raised(self, tmp_path):
        path = tmp_path / "scan.json"
        path.write_text("{not valid json,,,", encoding="utf-8")
        records, meta, age, err = scancache.load(path=str(path))
        assert records is None
        assert meta is None
        assert age is None
        assert "unreadable cache" in err

    def test_schema_mismatch_is_refused(self, tmp_path):
        path = tmp_path / "scan.json"
        path.write_text(json.dumps({"schema": scancache.SCHEMA + 1,
                                    "saved_at": 100, "meta": {}, "records": {}}),
                        encoding="utf-8")
        records, meta, age, err = scancache.load(path=str(path))
        assert records is None
        assert meta is None
        assert age is None
        assert "different version" in err

    def test_missing_schema_key_is_refused(self, tmp_path):
        """A hand-edited or pre-schema cache file with no 'schema' key at
        all must be refused, not treated as schema 0 by accident."""
        path = tmp_path / "scan.json"
        path.write_text(json.dumps({"saved_at": 100, "meta": {}, "records": {}}),
                        encoding="utf-8")
        records, meta, age, err = scancache.load(path=str(path))
        assert records is None
        assert "different version" in err

    def test_max_age_refuses_stale_cache(self, tmp_path):
        path = str(tmp_path / "scan.json")
        scancache.save({}, {}, path=path, now=0.0)
        records, meta, age, err = scancache.load(
            path=path, max_age=60, now=120.0)  # 120s old, limit 60s
        assert records is None
        assert meta is None
        assert age == pytest.approx(120.0)
        assert err is not None
        assert "old" in err
        assert "limit" in err

    def test_max_age_accepts_cache_within_limit(self, tmp_path):
        path = str(tmp_path / "scan.json")
        scancache.save({"k": "v"}, {"m": 1}, path=path, now=0.0)
        records, meta, age, err = scancache.load(
            path=path, max_age=60, now=30.0)
        assert err is None
        assert records == {"k": "v"}
        assert meta == {"m": 1}

    def test_max_age_boundary_is_inclusive(self, tmp_path):
        """age == max_age exactly must NOT be refused (only age > max_age is)."""
        path = str(tmp_path / "scan.json")
        scancache.save({}, {}, path=path, now=0.0)
        records, meta, age, err = scancache.load(path=path, max_age=60, now=60.0)
        assert err is None

    def test_max_age_none_accepts_any_age(self, tmp_path):
        path = str(tmp_path / "scan.json")
        scancache.save({}, {}, path=path, now=0.0)
        records, meta, age, err = scancache.load(
            path=path, max_age=None, now=10_000_000.0)
        assert err is None
        assert records == {}

    def test_missing_records_or_meta_default_to_empty_dict(self, tmp_path):
        path = tmp_path / "scan.json"
        path.write_text(json.dumps({"schema": scancache.SCHEMA, "saved_at": 0}),
                        encoding="utf-8")
        records, meta, age, err = scancache.load(path=str(path), now=1.0)
        assert err is None
        assert records == {}
        assert meta == {}

    def test_missing_saved_at_treated_as_epoch_zero(self, tmp_path):
        path = tmp_path / "scan.json"
        path.write_text(json.dumps({"schema": scancache.SCHEMA, "records": {},
                                    "meta": {}}), encoding="utf-8")
        records, meta, age, err = scancache.load(path=str(path), now=500.0)
        assert err is None
        assert age == pytest.approx(500.0)

    def test_load_uses_default_path_when_none_given(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        scancache.save({"a": 1}, {}, path=None, now=0.0)
        records, meta, age, err = scancache.load(path=None, now=1.0)
        assert err is None
        assert records == {"a": 1}


# -- format_age() -------------------------------------------------------------

class TestFormatAge:
    def test_none_is_unknown(self):
        assert scancache.format_age(None) == "unknown"

    def test_seconds_only(self):
        assert scancache.format_age(0) == "0s"
        assert scancache.format_age(45) == "45s"
        assert scancache.format_age(59) == "59s"

    def test_minutes(self):
        assert scancache.format_age(60) == "1m"
        assert scancache.format_age(150) == "2m"
        assert scancache.format_age(3599) == "59m"

    def test_hours_with_and_without_remainder_minutes(self):
        assert scancache.format_age(3600) == "1h"
        assert scancache.format_age(3600 + 600) == "1h 10m"
        assert scancache.format_age(86399) == "23h 59m"

    def test_days_with_and_without_remainder_hours(self):
        assert scancache.format_age(86400) == "1d"
        assert scancache.format_age(86400 + 3600 * 4) == "1d 4h"
        assert scancache.format_age(86400 * 10) == "10d"

    def test_negative_seconds_clamped_to_zero(self):
        assert scancache.format_age(-5) == "0s"

    def test_float_seconds_truncated(self):
        assert scancache.format_age(59.9) == "59s"


class TestNamespaceCachePathCollision:
    def test_custom_cache_path_never_collides(self):
        """REGRESSION: a cache_path without the default '-scan.json'
        suffix made scan and namespace caches share ONE file, and the
        namespace save silently destroyed the scan payload."""
        import scancache as sc
        for base in (r"C:\x\scan.json", "/tmp/mycache.json", "plain"):
            assert sc.namespace_cache_path(base) != base

    def test_default_suffix_still_maps_cleanly(self):
        import scancache as sc
        got = sc.namespace_cache_path(r"C:\x\dazzle-update-scan.json")
        assert got == r"C:\x\dazzle-update-namespaces.json"
