"""Prototype for the FQCN resolver — Phase 2 of the dazzlecmd aggregator engine.

This is a disposable prototype. It validates the data structure and resolution
algorithm before the real implementation lands in src/dazzlecmd/engine.py.

Goals:
    1. Exact FQCN match returns the project unambiguously, no notification.
    2. Short-name with one candidate dispatches silently.
    3. Short-name with multiple candidates applies precedence and emits a
       notification describing what was picked and how to be explicit.
    4. Custom kit_precedence overrides the default order.
    5. No match returns a "not found" signal with close-match suggestions.
    6. FQCN collisions at insertion time are errors (not resolved at lookup).
    7. Cycle detection via a loading-stack set.

Run:
    python tests/one-offs/test_fqcn_prototype.py
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Optional


# -----------------------------------------------------------------------------
# Prototype data structure
# -----------------------------------------------------------------------------


class FQCNCollisionError(Exception):
    """Raised when two projects declare the same FQCN during index build."""


class CircularDependencyError(Exception):
    """Raised when recursive discovery encounters a cycle."""


@dataclass
class Resolution:
    """Result of resolve_command() — the picked project plus any user-visible note."""
    project: dict
    notification: Optional[str] = None  # stderr text, None if unambiguous


@dataclass
class FQCNIndex:
    """The dual-dict FQCN index.

    - fqcn_index: {fqcn_string: project_dict} — exact-match dispatch
    - short_index: {short_name: [fqcn_string, ...]} — candidates for short-name resolution
    - kit_order: ordered list of top-level kit names (for default precedence)
    """

    fqcn_index: dict = field(default_factory=dict)
    short_index: dict = field(default_factory=lambda: {})  # name -> list of fqcns
    kit_order: list = field(default_factory=list)

    def insert(self, project: dict) -> None:
        """Insert a project. Project must carry _fqcn, _short_name, _kit_import_name."""
        fqcn = project["_fqcn"]
        short = project["_short_name"]
        kit = project["_kit_import_name"]

        if fqcn in self.fqcn_index:
            existing = self.fqcn_index[fqcn]
            raise FQCNCollisionError(
                f"Duplicate FQCN '{fqcn}': "
                f"{existing.get('_dir', '?')} vs {project.get('_dir', '?')}"
            )

        self.fqcn_index[fqcn] = project
        self.short_index.setdefault(short, []).append(fqcn)
        if kit not in self.kit_order:
            self.kit_order.append(kit)

    def resolve(self, name: str, precedence: Optional[list] = None) -> Optional[Resolution]:
        """Resolve a command name to a project.

        Args:
            name: argv[0] — may be an FQCN ('wtf:core:restarted') or short name ('restarted')
            precedence: optional ordered list of kit names overriding default

        Returns:
            Resolution if found, None if no match
        """
        # Case 1: FQCN (contains ":")
        if ":" in name:
            project = self.fqcn_index.get(name)
            if project is not None:
                return Resolution(project=project, notification=None)
            return None  # no match for explicit FQCN

        # Case 2: short name
        candidates = self.short_index.get(name, [])
        if not candidates:
            return None

        if len(candidates) == 1:
            project = self.fqcn_index[candidates[0]]
            return Resolution(project=project, notification=None)

        # Multiple candidates — apply precedence
        order = self._effective_precedence(precedence)
        ranked = self._rank_by_precedence(candidates, order)

        picked_fqcn = ranked[0]
        other_fqcns = ranked[1:]
        project = self.fqcn_index[picked_fqcn]

        # Build notification
        others_display = ", ".join(self._kit_of(f) for f in other_fqcns)
        notification = (
            f"dz: '{name}' resolved to {picked_fqcn} "
            f"(also in: {others_display}). "
            f"Use 'dz {picked_fqcn}' to be explicit."
        )
        return Resolution(project=project, notification=notification)

    def _effective_precedence(self, override: Optional[list]) -> list:
        """Return the effective kit precedence list.

        If override is given, use it (with unknown kits appended at the end).
        Otherwise default: core first, dazzletools second, then discovery order.
        """
        if override:
            # Explicit override — honor user's ordering
            # Append any kits not mentioned in override at the end
            tail = [k for k in self.kit_order if k not in override]
            return list(override) + tail

        # Default precedence
        default_priority = ["core", "dazzletools"]
        ordered = [k for k in default_priority if k in self.kit_order]
        tail = [k for k in self.kit_order if k not in ordered]
        return ordered + tail

    def _rank_by_precedence(self, fqcns: list, order: list) -> list:
        """Rank a list of FQCNs by the precedence order of their kits."""
        def kit_rank(fqcn):
            kit = self._kit_of(fqcn)
            try:
                return order.index(kit)
            except ValueError:
                return len(order)  # unknown kits sort last

        return sorted(fqcns, key=kit_rank)

    @staticmethod
    def _kit_of(fqcn: str) -> str:
        """Return the top-level kit name from an FQCN."""
        return fqcn.split(":", 1)[0]


# -----------------------------------------------------------------------------
# Test fixtures
# -----------------------------------------------------------------------------


def make_project(fqcn: str, short: str, kit: str, description: str = "") -> dict:
    """Build a minimal project dict for testing."""
    return {
        "name": short,
        "_fqcn": fqcn,
        "_short_name": short,
        "_kit_import_name": kit,
        "_dir": f"/fake/{fqcn.replace(':', '/')}",
        "description": description,
    }


def build_fixture_index() -> FQCNIndex:
    """Build a realistic fixture with deliberate collisions."""
    idx = FQCNIndex()

    # Core kit — dazzlecmd's own
    idx.insert(make_project("core:rn", "rn", "core", "regex file renamer"))
    idx.insert(make_project("core:fixpath", "fixpath", "core", "fix mangled paths"))
    idx.insert(make_project("core:find", "find", "core", "cross-platform search"))
    idx.insert(make_project("core:links", "links", "core", "filesystem link detection"))

    # DazzleTools kit
    idx.insert(make_project("dazzletools:dos2unix", "dos2unix", "dazzletools", "line ending conversion"))
    idx.insert(make_project("dazzletools:split", "split", "dazzletools", "split files"))

    # wtf kit (imported, nested aggregator)
    idx.insert(make_project("wtf:core:restarted", "restarted", "wtf", "Windows restart diagnostics"))
    idx.insert(make_project("wtf:core:locked", "locked", "wtf", "Windows lockout diagnostics"))

    # Deliberate collision: both core and wtf have a "find" tool
    # (simulating a hypothetical future scenario)
    idx.insert(make_project("wtf:core:find", "find", "wtf", "wtf-specific find"))

    # Deliberate 3-way collision to stress-test precedence
    idx.insert(make_project("core:status", "status", "core", "core status"))
    idx.insert(make_project("dazzletools:status", "status", "dazzletools", "dazzletools status"))
    idx.insert(make_project("wtf:core:status", "status", "wtf", "wtf status"))

    return idx


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


PASSED = 0
FAILED = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}  {detail}")


def test_exact_fqcn_match_unambiguous():
    print("\n[1] exact FQCN match returns project with no notification")
    idx = build_fixture_index()

    r = idx.resolve("core:fixpath")
    check("core:fixpath found", r is not None)
    check("correct project returned", r.project["_fqcn"] == "core:fixpath")
    check("no notification", r.notification is None)

    r = idx.resolve("wtf:core:restarted")
    check("wtf:core:restarted found", r is not None)
    check("correct project returned", r.project["_fqcn"] == "wtf:core:restarted")
    check("no notification", r.notification is None)


def test_exact_fqcn_no_match():
    print("\n[2] exact FQCN with no match returns None")
    idx = build_fixture_index()

    r = idx.resolve("core:nonexistent")
    check("core:nonexistent returns None", r is None)

    r = idx.resolve("wtf:core:nonexistent")
    check("wtf:core:nonexistent returns None", r is None)


def test_short_name_unambiguous():
    print("\n[3] unambiguous short name dispatches silently")
    idx = build_fixture_index()

    r = idx.resolve("fixpath")
    check("fixpath found", r is not None)
    check("resolves to core:fixpath", r.project["_fqcn"] == "core:fixpath")
    check("no notification", r.notification is None)

    r = idx.resolve("restarted")
    check("restarted found (only in wtf)", r is not None)
    check("resolves to wtf:core:restarted", r.project["_fqcn"] == "wtf:core:restarted")
    check("no notification", r.notification is None)


def test_short_name_default_precedence():
    print("\n[4] colliding short name with default precedence (core wins)")
    idx = build_fixture_index()

    # 'find' is in both core and wtf — core should win
    r = idx.resolve("find")
    check("find found", r is not None)
    check("resolves to core:find (default precedence)",
          r.project["_fqcn"] == "core:find",
          f"got {r.project['_fqcn']}")
    check("notification present", r.notification is not None)
    check("notification mentions core:find",
          "core:find" in (r.notification or ""),
          f"got: {r.notification}")
    check("notification mentions wtf",
          "wtf" in (r.notification or ""),
          f"got: {r.notification}")
    print(f"    notification: {r.notification}")


def test_short_name_three_way_collision():
    print("\n[5] three-way collision ordered correctly by default precedence")
    idx = build_fixture_index()

    # 'status' is in core, dazzletools, and wtf — order: core > dazzletools > wtf
    r = idx.resolve("status")
    check("status found", r is not None)
    check("resolves to core:status", r.project["_fqcn"] == "core:status",
          f"got {r.project['_fqcn']}")
    check("notification mentions dazzletools and wtf",
          "dazzletools" in (r.notification or "") and "wtf" in (r.notification or ""),
          f"got: {r.notification}")
    print(f"    notification: {r.notification}")


def test_short_name_custom_precedence():
    print("\n[6] user kit_precedence override inverts resolution")
    idx = build_fixture_index()

    # User wants wtf to win
    override = ["wtf", "core", "dazzletools"]
    r = idx.resolve("find", precedence=override)
    check("find found", r is not None)
    check("resolves to wtf:core:find (override)",
          r.project["_fqcn"] == "wtf:core:find",
          f"got {r.project['_fqcn']}")
    check("notification mentions core (other option)",
          "core" in (r.notification or ""))
    print(f"    notification: {r.notification}")


def test_short_name_not_found():
    print("\n[7] non-existent short name returns None")
    idx = build_fixture_index()

    r = idx.resolve("nonexistent")
    check("nonexistent returns None", r is None)


def test_fqcn_collision_at_insert():
    print("\n[8] duplicate FQCN insertion raises FQCNCollisionError")
    idx = FQCNIndex()
    idx.insert(make_project("core:rn", "rn", "core"))

    try:
        idx.insert(make_project("core:rn", "rn", "core"))
        check("collision raises", False, "no exception")
    except FQCNCollisionError as exc:
        check("collision raises FQCNCollisionError", True)
        check("error message mentions the FQCN", "core:rn" in str(exc))


def test_cycle_detection():
    """Cycle detection is not part of FQCNIndex itself — it belongs in
    _discover_aggregator. But we prototype the stack-set approach here."""
    print("\n[9] cycle detection via loading stack")

    def discover(path, stack):
        real = os.path.realpath(path)
        if real in stack:
            raise CircularDependencyError(
                f"Circular aggregator import: {' -> '.join(sorted(stack))} -> {real}"
            )
        stack = stack | {real}
        return stack

    # Simulate non-cyclic chain
    s = set()
    s = discover("/a", s)
    s = discover("/b", s)
    s = discover("/c", s)
    check("non-cyclic chain succeeds", len(s) == 3)

    # Simulate cycle
    try:
        s = discover("/a", s)  # /a already in stack
        check("cycle raises", False)
    except CircularDependencyError as exc:
        check("cycle raises CircularDependencyError", True)
        check("error message mentions the repeat", "/a" in str(exc).replace("\\", "/"))


def test_precedence_with_unknown_kit_in_override():
    print("\n[10] unknown kit in override is tolerated (ignored)")
    idx = build_fixture_index()

    # "ghost" doesn't exist but user listed it
    override = ["ghost", "core", "dazzletools"]
    r = idx.resolve("find", precedence=override)
    check("still resolves", r is not None)
    check("falls through to core:find",
          r.project["_fqcn"] == "core:find",
          f"got {r.project['_fqcn']}")


def test_short_name_skip_unknown_kits_in_default():
    print("\n[11] default precedence handles only-non-core kit case")
    idx = FQCNIndex()
    # Only wtf tools, no core
    idx.insert(make_project("wtf:core:a", "a", "wtf"))
    idx.insert(make_project("other:a", "a", "other"))

    r = idx.resolve("a")
    check("resolves", r is not None)
    # Neither is in default priority list — falls to discovery order
    # wtf was inserted first
    check("discovery-order fallback picks wtf",
          r.project["_fqcn"] == "wtf:core:a",
          f"got {r.project['_fqcn']}")


# -----------------------------------------------------------------------------
# Run all
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_exact_fqcn_match_unambiguous,
        test_exact_fqcn_no_match,
        test_short_name_unambiguous,
        test_short_name_default_precedence,
        test_short_name_three_way_collision,
        test_short_name_custom_precedence,
        test_short_name_not_found,
        test_fqcn_collision_at_insert,
        test_cycle_detection,
        test_precedence_with_unknown_kit_in_override,
        test_short_name_skip_unknown_kits_in_default,
    ]

    for t in tests:
        t()

    print(f"\n{'=' * 60}")
    print(f"  {PASSED} passed, {FAILED} failed")
    print(f"{'=' * 60}")
    sys.exit(0 if FAILED == 0 else 1)
