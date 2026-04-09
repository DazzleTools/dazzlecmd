"""Tests for safedel _zones module."""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from _zones import (
    Zone,
    DEFAULT_CONFIG,
    determine_zone,
    get_zone_warnings,
    check_clean_permission,
    format_age,
    load_config,
)


def test_zone_properties():
    assert Zone.A.is_blocked is True
    assert Zone.B.requires_force is True
    assert Zone.B.requires_interactive is True
    assert Zone.B.allows_yes_override is False
    assert Zone.C.requires_force is False
    assert Zone.C.requires_interactive is True
    assert Zone.C.allows_yes_override is False
    assert Zone.D.requires_force is False
    assert Zone.D.requires_interactive is True
    assert Zone.D.allows_yes_override is True


def test_determine_zone_defaults():
    now = datetime.datetime(2026, 4, 8, 12, 0, 0)
    config = DEFAULT_CONFIG

    # 1 hour ago -> Zone B (< 48h)
    one_hour = now - datetime.timedelta(hours=1)
    assert determine_zone(one_hour, config, now) == Zone.B

    # 3 days ago -> Zone C (48h - 30d)
    three_days = now - datetime.timedelta(days=3)
    assert determine_zone(three_days, config, now) == Zone.C

    # 45 days ago -> Zone D (> 30d)
    forty_five_days = now - datetime.timedelta(days=45)
    assert determine_zone(forty_five_days, config, now) == Zone.D


def test_determine_zone_a_enabled():
    now = datetime.datetime(2026, 4, 8, 12, 0, 0)
    config = {
        "protection": {
            "zone_a_enabled": True,
            "zone_a_hours": 6,
            "zone_b_hours": 48,
            "zone_c_days": 30,
        }
    }

    # 2 hours ago -> Zone A (< 6h, zone_a enabled)
    two_hours = now - datetime.timedelta(hours=2)
    assert determine_zone(two_hours, config, now) == Zone.A

    # 12 hours ago -> Zone B (past zone_a, < 48h)
    twelve_hours = now - datetime.timedelta(hours=12)
    assert determine_zone(twelve_hours, config, now) == Zone.B


def test_check_clean_permission_zone_a():
    allowed, reason = check_clean_permission(Zone.A)
    assert allowed is False
    assert "blocked" in reason.lower()


def test_check_clean_permission_zone_b():
    # Without --force
    allowed, reason = check_clean_permission(Zone.B, force=False, is_tty=True)
    assert allowed is False
    assert "--force" in reason

    # With --force, TTY
    allowed, reason = check_clean_permission(Zone.B, force=True, is_tty=True)
    assert allowed is True

    # With --force but --yes in non-TTY
    allowed, reason = check_clean_permission(Zone.B, force=True, yes=True, is_tty=False)
    assert allowed is False
    assert "--yes is not accepted" in reason


def test_check_clean_permission_zone_d():
    # Zone D with --yes in non-TTY: allowed
    allowed, reason = check_clean_permission(Zone.D, yes=True, is_tty=False)
    assert allowed is True

    # Zone D interactive TTY: allowed
    allowed, reason = check_clean_permission(Zone.D, is_tty=True)
    assert allowed is True


def test_get_zone_warnings_verbosity():
    meta = {
        "original_path": "/tmp/test.txt",
        "file_type": "symlink",
        "link_target": "/tmp/real.txt",
    }

    # Full warnings (verbosity 0)
    warnings = get_zone_warnings(Zone.B, meta, verbosity=0)
    assert len(warnings) > 0
    assert any("less than 48 hours" in w for w in warnings)
    assert any("original" in w.lower() for w in warnings)

    # Quiet (verbosity 1)
    warnings_q = get_zone_warnings(Zone.B, meta, verbosity=1)
    assert len(warnings_q) <= len(warnings)

    # Silent (verbosity 2)
    warnings_qq = get_zone_warnings(Zone.B, meta, verbosity=2)
    assert len(warnings_qq) == 0


def test_format_age():
    assert format_age(datetime.timedelta(seconds=30)) == "30s"
    assert format_age(datetime.timedelta(minutes=5)) == "5m"
    assert format_age(datetime.timedelta(hours=3)) == "3h"
    assert format_age(datetime.timedelta(days=7)) == "7d"
    assert "y" in format_age(datetime.timedelta(days=400))


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
