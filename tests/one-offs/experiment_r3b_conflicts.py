"""Round 3b experiment: Multiple virtual kits with overlapping aliases.

Meta-A1 from Gemini: test the collision policy when two virtual kits both
declare the same alias FQCN.

Expected behaviors (per current insert_alias at engine.py:123):
    - Same alias -> same target: idempotent (silent no-op)
    - Same alias -> different target: FQCNCollisionError

Also tests "dangling pointer" case (Meta-A2): virtual kit alias points to
a canonical FQCN that is NOT in canonical_index.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "packages", "dazzlecmd-lib", "src"))

from dazzlecmd_lib.engine import FQCNIndex, FQCNCollisionError


def make_canonical(fqcn, short=None, kit=None):
    return {
        "_fqcn": fqcn,
        "_short_name": short or fqcn.rsplit(":", 1)[-1],
        "_kit_import_name": kit or fqcn.split(":", 1)[0],
        "name": short or fqcn.rsplit(":", 1)[-1],
        "namespace": fqcn.split(":", 1)[0],
    }


def test(name, fn):
    try:
        fn()
        print(f"  [PASS] {name}")
    except AssertionError as exc:
        print(f"  [FAIL] {name}: {exc}")
    except Exception as exc:
        print(f"  [ERROR] {name}: {type(exc).__name__}: {exc}")


# ============================================================
# Meta-A1: Multiple virtual kits with conflicting aliases
# ============================================================

print("=== Meta-A1: Conflicting virtual kit aliases ===\n")


def test_idempotent_same_target():
    """Two virtual kits both declare foo:bar -> dazzletools:tool_a (same target)."""
    idx = FQCNIndex()
    idx.insert_canonical(make_canonical("dazzletools:tool_a"))
    idx.insert_alias("foo:bar", "dazzletools:tool_a", source="vk1.kit.json")
    # Second insert with same target should be a silent no-op (idempotent)
    idx.insert_alias("foo:bar", "dazzletools:tool_a", source="vk2.kit.json")
    assert idx.alias_index["foo:bar"] == "dazzletools:tool_a"
    # Only one entry
    assert len(idx.alias_index) == 1


def test_conflict_different_target():
    """Two virtual kits both declare foo:bar -> different targets."""
    idx = FQCNIndex()
    idx.insert_canonical(make_canonical("dazzletools:tool_a"))
    idx.insert_canonical(make_canonical("dazzletools:tool_b"))
    idx.insert_alias("foo:bar", "dazzletools:tool_a", source="vk1.kit.json")
    try:
        idx.insert_alias("foo:bar", "dazzletools:tool_b", source="vk2.kit.json")
        assert False, "Expected FQCNCollisionError"
    except FQCNCollisionError as exc:
        msg = str(exc)
        assert "already maps to" in msg
        assert "dazzletools:tool_a" in msg
        assert "dazzletools:tool_b" in msg
        assert "vk2.kit.json" in msg


def test_3_kits_chain_first_wins():
    """vk1 claims foo:bar -> tool_a. vk2 tries foo:bar -> tool_b (rejected).
    vk3 tries foo:bar -> tool_a (same as vk1, idempotent). Verify state is sane."""
    idx = FQCNIndex()
    idx.insert_canonical(make_canonical("dazzletools:tool_a"))
    idx.insert_canonical(make_canonical("dazzletools:tool_b"))
    idx.insert_alias("foo:bar", "dazzletools:tool_a")
    try:
        idx.insert_alias("foo:bar", "dazzletools:tool_b")
    except FQCNCollisionError:
        pass  # expected
    # Index unchanged
    assert idx.alias_index["foo:bar"] == "dazzletools:tool_a"
    # Third call to original target: idempotent
    idx.insert_alias("foo:bar", "dazzletools:tool_a")
    assert idx.alias_index["foo:bar"] == "dazzletools:tool_a"


test("idempotent same target", test_idempotent_same_target)
test("conflict different target raises", test_conflict_different_target)
test("first-wins chain stability", test_3_kits_chain_first_wins)


# ============================================================
# Meta-A2: Dangling pointers (alias -> missing canonical)
# ============================================================

print("\n=== Meta-A2: Alias to missing canonical (dangling pointer) ===\n")


def test_alias_to_missing_canonical_raises():
    """Virtual kit aliases a canonical that doesn't exist."""
    idx = FQCNIndex()
    # No canonical inserted
    try:
        idx.insert_alias("claude:cleanup", "dazzletools:gone",
                         source="claude.kit.json")
        assert False, "Expected KeyError"
    except KeyError as exc:
        msg = str(exc)
        assert "not found in canonical index" in msg
        assert "claude.kit.json" in msg


def test_resolve_missing_alias_returns_none():
    """If somehow an alias exists pointing to a missing canonical (corruption),
    resolve() returns a helpful notification."""
    idx = FQCNIndex()
    # Force state by poking alias_index directly (simulating corruption)
    idx.alias_index["claude:cleanup"] = "dazzletools:gone"
    project, note = idx.resolve("claude:cleanup")
    assert project is None
    assert "missing canonical entry" in note
    assert "index corruption?" in note


def test_alias_to_disabled_canonical_is_rejected_at_insert():
    """The skeleton filters canonical by _kit_active, so if dazzletools is
    disabled, none of its tools end up in canonical_index. An alias targeting
    those tools fails at insert time with KeyError."""
    idx = FQCNIndex()
    # dazzletools NOT inserted (simulating disabled)
    try:
        idx.insert_alias("claude:cleanup", "dazzletools:claude-cleanup")
        assert False, "Expected KeyError"
    except KeyError as exc:
        assert "not found in canonical index" in str(exc)


test("alias to missing canonical raises KeyError", test_alias_to_missing_canonical_raises)
test("resolve with corrupted alias_index returns helpful msg",
     test_resolve_missing_alias_returns_none)
test("alias to disabled canonical rejected at insert",
     test_alias_to_disabled_canonical_is_rejected_at_insert)


# ============================================================
# Extra: §9b self-collision mirror
# ============================================================

print("\n=== §9b mirror: canonical added AFTER alias claims its FQCN ===\n")


def test_canonical_cant_shadow_existing_alias():
    """If an alias claims foo:bar, a later canonical claiming foo:bar
    should fail (§9b mirror at engine.py:108-116)."""
    idx = FQCNIndex()
    idx.insert_canonical(make_canonical("dazzletools:tool_a"))
    idx.insert_alias("foo:bar", "dazzletools:tool_a")
    try:
        idx.insert_canonical(make_canonical("foo:bar"))
        assert False, "Expected FQCNCollisionError"
    except FQCNCollisionError as exc:
        msg = str(exc)
        assert "collides with existing alias" in msg


test("canonical added after alias with same FQCN is rejected",
     test_canonical_cant_shadow_existing_alias)


print("\nDone.")
