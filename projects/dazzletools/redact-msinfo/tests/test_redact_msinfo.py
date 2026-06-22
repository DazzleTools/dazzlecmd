"""
Tests for redact-msinfo.

Covers section-name resolution (--include/--exclude), the PII scrubbing
regexes, the runtime hostname scrub, render keep/strip behavior, the
self-verify pass, and end-to-end dispatch via main().

A synthetic UTF-16 fixture (tests/fixtures/sample_msinfo.txt) stands in for a
real msinfo32 export; regenerate it with tests/fixtures/make_sample.py.
"""

import sys
from pathlib import Path

import pytest

# Locate the tool module without polluting sys.path globally.
_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import redact_msinfo as rm  # noqa: E402
sys.path.pop(0)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_msinfo.txt"
HOST = "TESTHOST01"


# ---------------------------------------------------------------------------
# Section-name matching / resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", [
    "System Drivers", "system drivers", "SystemDrivers",
    "[System Drivers]", "system-drivers", "SYSTEMDRIVERS",
])
def test_normalize_token_collapses_forms(token):
    assert rm.normalize_token(token) == "systemdrivers"


def test_split_section_tokens_flattens_and_trims():
    assert rm.split_section_tokens(["A,B", " C ", "D,,E"]) == ["A", "B", "C", "D", "E"]
    assert rm.split_section_tokens(None) == []


def _order():
    # Section order as it appears in the fixture (for resolution against file).
    _, _, _, order = read()
    return order


def read():
    return rm.read_sections(str(FIXTURE))


def test_resolve_defaults_when_no_flags():
    keep, errors = rm.resolve_keep_sections(_order(), [], [])
    assert errors == []
    assert keep == set(rm.KEEP_SECTIONS)


def test_resolve_include_adds_section():
    keep, errors = rm.resolve_keep_sections(_order(), ["SystemDrivers", "EnvironmentVariables"], [])
    assert errors == []
    assert "[System Drivers]" in keep
    assert "[Environment Variables]" in keep
    assert "[System Summary]" in keep  # defaults still present


def test_resolve_exclude_removes_default():
    keep, errors = rm.resolve_keep_sections(_order(), [], ["Display"])
    assert errors == []
    assert "[Display]" not in keep
    assert "[System Summary]" in keep


def test_resolve_conflict_is_error():
    keep, errors = rm.resolve_keep_sections(_order(), ["Display"], ["Display"])
    assert any("BOTH" in e for e in errors)


def test_resolve_unknown_token_is_error():
    keep, errors = rm.resolve_keep_sections(_order(), ["Bogus"], [])
    assert any("Unrecognized" in e for e in errors)


def test_known_sections_catalog_is_union():
    assert rm.KNOWN_SECTIONS == set(rm.KEEP_SECTIONS) | set(rm.STRIP_REASONS)


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line,needle", [
    ("System Name\t" + HOST + "\t", "[REDACTED-HOSTNAME]"),
    ("User Name\t" + HOST + "\\testuser\t", "[REDACTED-USER]"),
    ("Registered Owner\tTest Owner\t", "[REDACTED]"),
    ("Windows Product ID\t00330-00000-00000-AA000\t", "[REDACTED-PRODUCT-ID]"),
    ("Key\tAAAAA-BBBBB-CCCCC-DDDDD-EEEEE\t", "[REDACTED-PRODUCT-KEY]"),
    ("UUID\t12345678-1234-1234-1234-123456789ABC\t", "[REDACTED-UUID]"),
    ("Serial Number\tSN-TEST-123456\t", "[REDACTED-SERIAL]"),
    ("MAC Address\t00:11:22:33:44:55\t", "[REDACTED-MAC]"),
    ("IP Address\t192.168.1.50\t", "[REDACTED-IP]"),
    ("Dir\tC:\\Users\\testuser\\AppData\t", "C:\\Users\\[REDACTED-USER]"),
])
def test_apply_pii_rules_scrubs(line, needle):
    out = rm.apply_pii_rules(line)
    assert needle in out


def test_pii_rules_leave_benign_content():
    line = "OS Name\tMicrosoft Windows 11 Pro\t"
    assert rm.apply_pii_rules(line) == line


def test_build_dynamic_rules_hostname_scrub():
    rules = rm.build_dynamic_rules(HOST)
    out = rm.apply_pii_rules("driver on " + HOST + " path", extra_rules=rules)
    assert HOST not in out
    assert "[REDACTED-HOSTNAME]" in out


def test_build_dynamic_rules_skips_short_hostname():
    assert rm.build_dynamic_rules("PC") == []
    assert rm.build_dynamic_rules("") == []


# ---------------------------------------------------------------------------
# Render (keep / strip)
# ---------------------------------------------------------------------------

def test_render_default_keeps_and_strips():
    _, preamble, sections, order = read()
    text = "\n".join(rm.render(preamble, sections, order, set(rm.KEEP_SECTIONS)))
    # Kept content present
    assert "Test GPU 9000" in text                      # [Display]
    assert "--- OS Identity ---" in text                 # reordered summary
    # Stripped sections collapsed to placeholders
    assert "[System Drivers]  -- REMOVED" in text
    assert "[Environment Variables]  -- REMOVED" in text
    # No hostname survives (System Name field redacted; drivers section stripped)
    assert HOST not in text
    # The fake secret lives only in the stripped env-var section -> gone
    assert "sk-test-EXAMPLE" not in text


def test_render_include_systemdrivers_with_hostname_scrub():
    _, preamble, sections, order = read()
    keep = set(rm.KEEP_SECTIONS) | {"[System Drivers]"}
    rules = rm.build_dynamic_rules(HOST)
    text = "\n".join(rm.render(preamble, sections, order, keep, extra_rules=rules))
    assert "testdrv.sys" in text          # section is now kept
    assert HOST not in text               # but bare hostname scrubbed


def test_render_exclude_display():
    _, preamble, sections, order = read()
    keep = set(rm.KEEP_SECTIONS) - {"[Display]"}
    text = "\n".join(rm.render(preamble, sections, order, keep))
    assert "[Display]  -- REMOVED" in text
    assert "Test GPU 9000" not in text


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def test_verify_passes_on_clean_output(tmp_path):
    out = tmp_path / "clean.txt"
    out.write_text("OS Name\tWindows\nUser Name\tNot Available\n", encoding="utf-8")
    assert rm.verify(str(out), hostname=HOST) is True


def test_verify_fails_on_unredacted_mac(tmp_path):
    out = tmp_path / "leaky.txt"
    out.write_text("MAC Address\t00:11:22:33:44:55\n", encoding="utf-8")
    assert rm.verify(str(out), hostname=HOST) is False


def test_verify_fails_on_unredacted_hostname(tmp_path):
    out = tmp_path / "leaky.txt"
    out.write_text("some path on " + HOST + " here\n", encoding="utf-8")
    assert rm.verify(str(out), hostname=HOST) is False


# ---------------------------------------------------------------------------
# End-to-end via main()
# ---------------------------------------------------------------------------

def test_main_default_passes(tmp_path, capsys):
    out = tmp_path / "out.txt"
    rc = rm.main(["--input", str(FIXTURE), "--output", str(out), "--hostname", HOST])
    assert rc == 0
    assert out.is_file()
    captured = capsys.readouterr().out
    assert "All verification checks passed." in captured
    body = out.read_text(encoding="utf-8")
    assert HOST not in body
    assert "[System Drivers]  -- REMOVED" in body


def test_main_include_envvars_warns_and_secret_survives(tmp_path, capsys):
    """Including a default-stripped section warns; the scrubber cannot catch an
    arbitrary secret, so it survives even though verify may pass -- which is
    exactly why the WARN exists."""
    out = tmp_path / "out.txt"
    rc = rm.main(["--input", str(FIXTURE), "--output", str(out),
                  "--hostname", HOST, "--include", "EnvironmentVariables"])
    captured = capsys.readouterr().out
    assert "[WARN ]" in captured
    assert "Force-including" in captured
    body = out.read_text(encoding="utf-8")
    assert "sk-test-EXAMPLE" in body   # the secret is NOT auto-scrubbed
    assert rc in (0, 1)                 # verify outcome is secondary to the WARN


def test_main_conflict_exits_1(tmp_path):
    out = tmp_path / "out.txt"
    rc = rm.main(["--input", str(FIXTURE), "--output", str(out),
                  "--hostname", HOST, "--include", "Display", "--exclude", "Display"])
    assert rc == 1
    assert not out.exists()


def test_main_unknown_token_exits_1(tmp_path):
    out = tmp_path / "out.txt"
    rc = rm.main(["--input", str(FIXTURE), "--output", str(out),
                  "--hostname", HOST, "--include", "Nonexistent"])
    assert rc == 1


def test_main_missing_input_exits_2():
    rc = rm.main(["--hostname", HOST])
    assert rc == 2


def test_main_input_equals_output_refused(tmp_path):
    # Copy fixture so input and output resolve to the same path
    src = tmp_path / "msinfo.txt"
    src.write_bytes(FIXTURE.read_bytes())
    rc = rm.main(["--input", str(src), "--output", str(src), "--hostname", HOST])
    assert rc == 1


def test_main_list_sections(capsys):
    rc = rm.main(["--list-sections"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Default-KEPT sections" in out
    assert "[System Drivers]" in out


def test_default_output_path_is_sidecar():
    assert rm.default_output_path("/a/b/msinfo.txt").endswith("msinfo.redacted.txt")
