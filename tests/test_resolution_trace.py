"""Tests for dazzlecmd_lib.resolution_trace."""

from __future__ import annotations

import pytest

from dazzlecmd_lib.resolution_trace import (
    ResolutionAttempt,
    ResolutionTrace,
)
from dazzlecmd_lib.platform_detect import PlatformInfo


@pytest.fixture
def linux_pi():
    return PlatformInfo(
        os="linux", subtype="debian", arch="x86_64", is_wsl=False, version="12",
    )


class TestResolutionAttempt:
    def test_minimal_construction(self):
        a = ResolutionAttempt(label="prefer[0]", passed=True)
        assert a.label == "prefer[0]"
        assert a.passed is True
        assert a.reason == ""
        assert a.detail is None

    def test_full_construction(self):
        a = ResolutionAttempt(
            label="prefer[1]: node",
            passed=False,
            reason="node not on PATH",
            detail={"interpreter": "node"},
        )
        assert a.reason == "node not on PATH"
        assert a.detail == {"interpreter": "node"}


class TestResolutionTraceConstruction:
    def test_empty_trace(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        assert trace.platform_info is linux_pi
        assert trace.layer == "runtime"
        assert trace.attempts == []
        assert trace.selected_index is None
        assert trace.notes == []

    def test_has_match_false_initially(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        assert trace.has_match() is False

    def test_selected_returns_none_initially(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        assert trace.selected() is None


class TestRecord:
    def test_record_passing_attempt(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        trace.record("prefer[0]: bun", passed=True, reason="bun on PATH")
        assert len(trace.attempts) == 1
        assert trace.selected_index == 0
        assert trace.has_match() is True
        assert trace.selected().label == "prefer[0]: bun"

    def test_record_failing_attempt(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        trace.record("prefer[0]: bun", passed=False, reason="bun not on PATH")
        assert len(trace.attempts) == 1
        assert trace.selected_index is None
        assert trace.has_match() is False

    def test_only_first_passing_attempt_wins(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        trace.record("prefer[0]: bun", passed=False, reason="bun not on PATH")
        trace.record("prefer[1]: node", passed=True, reason="node on PATH")
        trace.record("prefer[2]: npx", passed=True, reason="npx on PATH")
        # Index points to the first passing attempt
        assert trace.selected_index == 1
        assert trace.selected().label == "prefer[1]: node"

    def test_detail_forwarded(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="setup")
        trace.record(
            "setup.steps[0]",
            passed=True,
            reason="matched",
            detail={"command": "apt install -y python3"},
        )
        assert trace.attempts[0].detail == {"command": "apt install -y python3"}


class TestFailedAttempts:
    def test_returns_only_failures(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        trace.record("prefer[0]: bun", passed=False, reason="not on PATH")
        trace.record("prefer[1]: node", passed=True)
        trace.record("prefer[2]: npx", passed=False, reason="not on PATH")
        failed = trace.failed_attempts()
        assert len(failed) == 2
        assert failed[0].label == "prefer[0]: bun"
        assert failed[1].label == "prefer[2]: npx"

    def test_all_failed(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        trace.record("prefer[0]", passed=False, reason="a")
        trace.record("prefer[1]", passed=False, reason="b")
        assert len(trace.failed_attempts()) == 2
        assert trace.has_match() is False


class TestNotes:
    def test_notes_appendable(self, linux_pi):
        trace = ResolutionTrace(platform_info=linux_pi, layer="runtime")
        trace.notes.append("schema version 1")
        trace.notes.append("user override present")
        assert trace.notes == ["schema version 1", "user override present"]
