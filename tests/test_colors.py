"""Tests for `dazzlecmd_lib.colors` -- ANSI helpers and detection."""

from __future__ import annotations

import io
import os

import pytest

from dazzlecmd_lib import colors as _colors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_ansi_init():
    """Reset the colorama-init flag between tests so each test's Windows
    behavior is independent. Non-fatal on POSIX (the flag isn't consulted)."""
    saved = _colors._ansi_initialized
    _colors._ansi_initialized = False
    yield
    _colors._ansi_initialized = saved


@pytest.fixture
def clear_color_env(monkeypatch):
    """Clear all color-control env vars so should_use_color() detection
    runs against a clean slate. Tests that need a specific env set it
    themselves via monkeypatch.setenv()."""
    for var in ("NO_COLOR", "DZ_COLOR", "FORCE_COLOR"):
        monkeypatch.delenv(var, raising=False)


class _TTYStream(io.StringIO):
    """StringIO that reports isatty=True so we can simulate a real terminal."""

    def isatty(self):
        return True


class _NonTTYStream(io.StringIO):
    """StringIO that reports isatty=False -- this is the default for
    StringIO already, but the explicit subclass makes intent clear."""

    def isatty(self):
        return False


# ---------------------------------------------------------------------------
# colorize
# ---------------------------------------------------------------------------


class TestColorize:

    def test_no_codes_returns_text_unchanged(self):
        assert _colors.colorize("hello") == "hello"

    def test_single_code_wraps_with_reset(self):
        result = _colors.colorize("hello", _colors.BOLD)
        assert result == f"\033[1mhello{_colors.RESET}"

    def test_multiple_codes_concatenated_before_text(self):
        # The pattern used for [*] (BOLD + RED): both codes applied, single reset.
        result = _colors.colorize("[*]", _colors.BOLD, _colors.RED)
        # Both codes appear before the text; RESET appears once at the end.
        assert result.startswith("\033[1m\033[31m") or result.startswith("\033[31m\033[1m")
        assert result.endswith(_colors.RESET)
        assert "[*]" in result
        assert result.count(_colors.RESET) == 1

    def test_empty_string_with_codes_still_wraps(self):
        result = _colors.colorize("", _colors.YELLOW)
        # Wrapper around an empty string yields just the codes + reset
        assert result == f"\033[33m{_colors.RESET}"


# ---------------------------------------------------------------------------
# should_use_color -- environment-variable precedence
# ---------------------------------------------------------------------------


class TestShouldUseColorEnvPrecedence:
    """The detection order is:
    1. NO_COLOR set (any value) -> False
    2. DZ_COLOR=always OR FORCE_COLOR set -> True
    3. DZ_COLOR=never -> False
    4. fall through to isatty()
    """

    def test_no_color_wins_over_force_color(self, clear_color_env, monkeypatch):
        # NO_COLOR is absolute. FORCE_COLOR also set -- still suppressed.
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert _colors.should_use_color(_TTYStream()) is False

    def test_no_color_wins_over_dz_color_always(self, clear_color_env, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "")  # empty string IS set per community spec
        monkeypatch.setenv("DZ_COLOR", "always")
        assert _colors.should_use_color(_TTYStream()) is False

    def test_dz_color_always_overrides_non_tty(self, clear_color_env, monkeypatch):
        monkeypatch.setenv("DZ_COLOR", "always")
        # Non-TTY stream -- still True because DZ_COLOR=always forces it
        assert _colors.should_use_color(_NonTTYStream()) is True

    def test_force_color_overrides_non_tty(self, clear_color_env, monkeypatch):
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert _colors.should_use_color(_NonTTYStream()) is True

    def test_dz_color_never_suppresses_tty(self, clear_color_env, monkeypatch):
        monkeypatch.setenv("DZ_COLOR", "never")
        # TTY stream -- but DZ_COLOR=never wins
        assert _colors.should_use_color(_TTYStream()) is False

    def test_dz_color_never_loses_to_force_color(self, clear_color_env, monkeypatch):
        # Per the documented precedence, FORCE_COLOR is checked BEFORE
        # the DZ_COLOR=never branch. Setting both forces color on.
        monkeypatch.setenv("DZ_COLOR", "never")
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert _colors.should_use_color(_TTYStream()) is True

    def test_dz_color_case_insensitive(self, clear_color_env, monkeypatch):
        monkeypatch.setenv("DZ_COLOR", "Never")
        assert _colors.should_use_color(_TTYStream()) is False
        monkeypatch.setenv("DZ_COLOR", "ALWAYS")
        assert _colors.should_use_color(_NonTTYStream()) is True

    def test_dz_color_garbage_value_falls_through_to_tty(
        self, clear_color_env, monkeypatch
    ):
        # Unknown DZ_COLOR values are ignored -- fall through to isatty.
        monkeypatch.setenv("DZ_COLOR", "purple")
        assert _colors.should_use_color(_TTYStream()) is True
        assert _colors.should_use_color(_NonTTYStream()) is False


# ---------------------------------------------------------------------------
# should_use_color -- isatty fallback
# ---------------------------------------------------------------------------


class TestShouldUseColorIsattyFallback:

    def test_tty_stream_returns_true(self, clear_color_env):
        assert _colors.should_use_color(_TTYStream()) is True

    def test_non_tty_stream_returns_false(self, clear_color_env):
        assert _colors.should_use_color(_NonTTYStream()) is False

    def test_stream_without_isatty_returns_false(self, clear_color_env):
        class NoIsatty:
            pass
        assert _colors.should_use_color(NoIsatty()) is False

    def test_default_stream_is_stdout(self, clear_color_env, monkeypatch):
        # Patch sys.stdout temporarily to a fake TTY; verify the function
        # picks it up when stream=None.
        import sys
        monkeypatch.setattr(sys, "stdout", _TTYStream())
        assert _colors.should_use_color() is True


# ---------------------------------------------------------------------------
# colorize_for -- stream-aware convenience wrapper
# ---------------------------------------------------------------------------


class TestColorizeFor:
    """``colorize_for(stream, text, *codes)`` colorizes only when
    ``should_use_color(stream)`` is True. Designed for the stderr-warning
    pattern where the caller wants a one-liner."""

    def test_tty_stream_colorizes(self, clear_color_env):
        result = _colors.colorize_for(_TTYStream(), "Warning: x", _colors.YELLOW)
        assert result == f"\033[33mWarning: x{_colors.RESET}"

    def test_non_tty_stream_returns_plain(self, clear_color_env):
        result = _colors.colorize_for(_NonTTYStream(), "Warning: x", _colors.YELLOW)
        assert result == "Warning: x"

    def test_no_color_env_suppresses(self, clear_color_env, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        # Even with a TTY stream, NO_COLOR wins.
        result = _colors.colorize_for(_TTYStream(), "Error: y", _colors.BRIGHT_RED)
        assert result == "Error: y"

    def test_force_color_overrides_non_tty(self, clear_color_env, monkeypatch):
        monkeypatch.setenv("DZ_COLOR", "always")
        # Non-TTY stream but DZ_COLOR=always forces color on.
        result = _colors.colorize_for(_NonTTYStream(), "Warning: z", _colors.YELLOW)
        assert result == f"\033[33mWarning: z{_colors.RESET}"

    def test_empty_codes_returns_plain_even_with_tty(self, clear_color_env):
        # No codes passed -> colorize() returns text unchanged regardless.
        result = _colors.colorize_for(_TTYStream(), "plain")
        assert result == "plain"


# ---------------------------------------------------------------------------
# warn / error -- semantic stderr-class wrappers
# ---------------------------------------------------------------------------


class TestWarnError:
    """``warn(text)`` and ``error(text)`` are the recommended wrappers for
    the two most common stderr-message classes. They default the stream to
    ``sys.stderr`` and pick a fixed color (YELLOW / BRIGHT_RED) so call
    sites don't repeat the (stream, codes) tuple every time."""

    def test_warn_with_tty_stderr_returns_yellow(self, clear_color_env, monkeypatch):
        monkeypatch.setattr("sys.stderr", _TTYStream())
        result = _colors.warn("Tool 'x' not found.")
        assert result == f"\033[33mTool 'x' not found.{_colors.RESET}"

    def test_warn_with_non_tty_stderr_returns_plain(self, clear_color_env, monkeypatch):
        monkeypatch.setattr("sys.stderr", _NonTTYStream())
        result = _colors.warn("Tool 'x' not found.")
        assert result == "Tool 'x' not found."

    def test_warn_respects_no_color(self, clear_color_env, monkeypatch):
        monkeypatch.setattr("sys.stderr", _TTYStream())
        monkeypatch.setenv("NO_COLOR", "1")
        result = _colors.warn("anything")
        assert result == "anything"

    def test_warn_explicit_stream_argument(self, clear_color_env):
        # Caller can pass a specific stream, overriding the default sys.stderr.
        tty = _TTYStream()
        result = _colors.warn("x", stream=tty)
        assert result == f"\033[33mx{_colors.RESET}"

    def test_error_with_tty_stderr_returns_bright_red(self, clear_color_env, monkeypatch):
        monkeypatch.setattr("sys.stderr", _TTYStream())
        result = _colors.error("Error: cannot read config")
        assert result == f"\033[91mError: cannot read config{_colors.RESET}"

    def test_error_with_non_tty_stderr_returns_plain(self, clear_color_env, monkeypatch):
        monkeypatch.setattr("sys.stderr", _NonTTYStream())
        result = _colors.error("Error: x")
        assert result == "Error: x"

    def test_error_respects_no_color(self, clear_color_env, monkeypatch):
        monkeypatch.setattr("sys.stderr", _TTYStream())
        monkeypatch.setenv("NO_COLOR", "1")
        result = _colors.error("Error: x")
        assert result == "Error: x"

    def test_error_explicit_stream_argument(self, clear_color_env):
        tty = _TTYStream()
        result = _colors.error("Error", stream=tty)
        assert result == f"\033[91mError{_colors.RESET}"

    def test_warn_and_error_use_distinct_colors(self, clear_color_env, monkeypatch):
        # Regression guard: the two wrappers should NEVER share a color,
        # otherwise distinguishing warnings from errors visually breaks.
        monkeypatch.setattr("sys.stderr", _TTYStream())
        w = _colors.warn("x")
        e = _colors.error("x")
        assert w != e
        # YELLOW for warn, BRIGHT_RED for error.
        assert "\033[33m" in w
        assert "\033[91m" in e


# ---------------------------------------------------------------------------
# Public constants -- regression guard so the exported palette doesn't drift
# ---------------------------------------------------------------------------


class TestPublicConstants:

    def test_reset_terminator(self):
        assert _colors.RESET == "\033[0m"

    def test_basic_8_color_codes(self):
        # 8-color palette only -- broadly supported (PuTTY, legacy terminals).
        assert _colors.BOLD == "\033[1m"
        assert _colors.DIM == "\033[2m"
        assert _colors.RED == "\033[31m"
        assert _colors.GREEN == "\033[32m"
        assert _colors.YELLOW == "\033[33m"
        assert _colors.CYAN == "\033[36m"
        assert _colors.BRIGHT_RED == "\033[91m"

    def test_no_truecolor_or_256color_constants_exported(self):
        # Slim-by-design: no 256-color or RGB codes leak into the API,
        # because those break on PuTTY and older terminals. If a future
        # commit adds them, this test should be revised intentionally.
        public_attrs = {
            name for name in dir(_colors)
            if not name.startswith("_")
            and isinstance(getattr(_colors, name), str)
            and getattr(_colors, name).startswith("\033[")
        }
        # All exported color constants should match the documented 8-color
        # palette + emphasis -- no extended codes.
        expected = {"RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "CYAN", "BRIGHT_RED"}
        assert public_attrs == expected, (
            f"Unexpected color constants exported: "
            f"{public_attrs - expected}"
        )
