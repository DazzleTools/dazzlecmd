"""Tests for safedel _zones module."""

import datetime

from _zones import (
    Zone,
    DEFAULT_CONFIG,
    determine_zone,
    get_zone_warnings,
    check_clean_permission,
    format_age,
)


class TestZoneProperties:
    def test_zone_a_is_blocked(self):
        assert Zone.A.is_blocked is True
        assert Zone.A.requires_force is False

    def test_zone_b_max_friction(self):
        assert Zone.B.requires_force is True
        assert Zone.B.requires_interactive is True
        assert Zone.B.allows_yes_override is False

    def test_zone_c_standard(self):
        assert Zone.C.requires_force is False
        assert Zone.C.requires_interactive is True
        assert Zone.C.allows_yes_override is False

    def test_zone_d_relaxed(self):
        assert Zone.D.requires_force is False
        assert Zone.D.allows_yes_override is True


class TestDetermineZone:
    NOW = datetime.datetime(2026, 4, 8, 12, 0, 0)

    def test_one_hour_ago_is_zone_b(self):
        dt = self.NOW - datetime.timedelta(hours=1)
        assert determine_zone(dt, DEFAULT_CONFIG, self.NOW) == Zone.B

    def test_three_days_ago_is_zone_c(self):
        dt = self.NOW - datetime.timedelta(days=3)
        assert determine_zone(dt, DEFAULT_CONFIG, self.NOW) == Zone.C

    def test_forty_five_days_ago_is_zone_d(self):
        dt = self.NOW - datetime.timedelta(days=45)
        assert determine_zone(dt, DEFAULT_CONFIG, self.NOW) == Zone.D

    def test_zone_a_when_enabled(self):
        config = {
            "protection": {
                "zone_a_enabled": True,
                "zone_a_hours": 6,
                "zone_b_hours": 48,
                "zone_c_days": 30,
            }
        }
        dt = self.NOW - datetime.timedelta(hours=2)
        assert determine_zone(dt, config, self.NOW) == Zone.A

    def test_past_zone_a_falls_to_zone_b(self):
        config = {
            "protection": {
                "zone_a_enabled": True,
                "zone_a_hours": 6,
                "zone_b_hours": 48,
                "zone_c_days": 30,
            }
        }
        dt = self.NOW - datetime.timedelta(hours=12)
        assert determine_zone(dt, config, self.NOW) == Zone.B


class TestCheckCleanPermission:
    def test_zone_a_always_blocked(self):
        allowed, reason = check_clean_permission(Zone.A)
        assert allowed is False

    def test_zone_b_requires_force(self):
        allowed, _ = check_clean_permission(Zone.B, force=False, is_tty=True)
        assert allowed is False

    def test_zone_b_with_force_and_tty(self):
        allowed, _ = check_clean_permission(Zone.B, force=True, is_tty=True)
        assert allowed is True

    def test_zone_b_rejects_yes_in_non_tty(self):
        allowed, reason = check_clean_permission(
            Zone.B, force=True, yes=True, is_tty=False
        )
        assert allowed is False
        assert "--yes is not accepted" in reason

    def test_zone_d_accepts_yes(self):
        allowed, _ = check_clean_permission(Zone.D, yes=True, is_tty=False)
        assert allowed is True


class TestZoneWarnings:
    def test_full_warnings(self):
        meta = {
            "original_path": "/tmp/test.txt",
            "file_type": "symlink",
            "link_target": "/tmp/real.txt",
        }
        warnings = get_zone_warnings(Zone.B, meta, verbosity=0)
        assert len(warnings) > 0
        assert any("48 hours" in w for w in warnings)

    def test_quiet_reduces_warnings(self):
        meta = {"original_path": "/tmp/test.txt", "file_type": "regular_file"}
        full = get_zone_warnings(Zone.B, meta, verbosity=0)
        quiet = get_zone_warnings(Zone.B, meta, verbosity=1)
        assert len(quiet) <= len(full)

    def test_qq_suppresses_all(self):
        meta = {"original_path": "/tmp/test.txt"}
        warnings = get_zone_warnings(Zone.B, meta, verbosity=2)
        assert len(warnings) == 0


class TestFormatAge:
    def test_seconds(self):
        assert format_age(datetime.timedelta(seconds=30)) == "30s"

    def test_minutes(self):
        assert format_age(datetime.timedelta(minutes=5)) == "5m"

    def test_hours(self):
        assert format_age(datetime.timedelta(hours=3)) == "3h"

    def test_days(self):
        assert format_age(datetime.timedelta(days=7)) == "7d"

    def test_years(self):
        assert "y" in format_age(datetime.timedelta(days=400))
