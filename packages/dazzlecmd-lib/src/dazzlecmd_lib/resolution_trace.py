"""Resolution trace dataclasses -- shared diagnostic structure.

When the runtime resolver fails to pick a `prefer` entry (or the setup resolver
fails to find a matching install block), the diagnostic output is a structured
trace: which platform was detected, which entries were tried, why each failed,
and what the caller can do about it.

This module owns the DATA STRUCTURE. The RENDERING (turning a ResolutionTrace
into terminal text) stays per-layer so runtime and setup can phrase their
error messages appropriately for their concerns. Shared structure, per-layer
presentation.

Usage:
    trace = ResolutionTrace(platform_info=pi, layer="runtime")
    trace.attempts.append(ResolutionAttempt(
        label="prefer[0]: bun",
        passed=False,
        reason="bun not on PATH",
    ))
    if trace.has_match():
        ...
    else:
        raise NoResolutionError(render_runtime_trace(trace))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from dazzlecmd_lib.platform_detect import PlatformInfo


@dataclass
class ResolutionAttempt:
    """A single evaluation attempt within a resolution chain.

    Fields:
        label: Short human-readable label (e.g., "prefer[0]: bun",
            "platforms.linux.debian", "setup.steps[2]").
        passed: Whether this attempt matched / was selected.
        reason: Why the attempt passed or failed. Kept short and actionable
            where possible. Never includes env var VALUES (security).
        detail: Optional structured supplementary data (e.g., the entry dict
            that was evaluated). For diagnostics; not rendered by default.
    """

    label: str
    passed: bool
    reason: str = ""
    detail: Optional[dict] = None


@dataclass
class ResolutionTrace:
    """A complete resolution pass's diagnostic record.

    Fields:
        platform_info: The PlatformInfo used for this resolution.
        layer: "runtime" or "setup" -- identifies which pipeline produced this.
        attempts: Ordered list of ResolutionAttempts. First `passed=True`
            attempt (if any) is the selected result.
        selected_index: Index into `attempts` of the chosen attempt, or None
            if no attempt passed.
        notes: Free-form strings for context a layer wants to surface (e.g.,
            "schema version 1", "user override present").
    """

    platform_info: PlatformInfo
    layer: str
    attempts: List[ResolutionAttempt] = field(default_factory=list)
    selected_index: Optional[int] = None
    notes: List[str] = field(default_factory=list)

    def record(self, label: str, passed: bool, reason: str = "", detail: Optional[dict] = None) -> None:
        """Append an attempt. If it passes and no selection is set, record the index."""
        self.attempts.append(
            ResolutionAttempt(label=label, passed=passed, reason=reason, detail=detail)
        )
        if passed and self.selected_index is None:
            self.selected_index = len(self.attempts) - 1

    def has_match(self) -> bool:
        return self.selected_index is not None

    def selected(self) -> Optional[ResolutionAttempt]:
        if self.selected_index is None:
            return None
        return self.attempts[self.selected_index]

    def failed_attempts(self) -> List[ResolutionAttempt]:
        return [a for a in self.attempts if not a.passed]
