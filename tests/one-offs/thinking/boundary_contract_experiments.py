"""Empirical experiments: are "boundary contracts" instances of the
group/ungroup identity invariant -- and should `source` be a typed object?

Triggered by the user's design challenge (2026-06-10, post-v0.8.32):

    "It seems like 'boundary contracts' get to the heart of the invariant
    aspect of going between group(X) composed-with ungroup(X) = identity,
    right? In which case this feels like it should be formalized with a
    general interface of some sort and how that connects with our 'state'
    class? ... I'm worried that the keys you are talking about ARE
    polymorphic and therefore should be TYPED in a more rigorous way as
    actual defined objects not just entries in a dictionary ... I just want
    to make sure we tested rather than asserted."

Three experiments, run against the REAL repo population (every manifest on
disk), not synthetic fixtures:

E1  The manifest<->entity boundary as a round-trip identity:
    to_manifest(build_entity(m)) vs m, for every real manifest.
    Measures: LOST keys (data loss -- must be zero post-v0.8.32),
    CHANGED values (corruption -- must be zero), ADDED keys (default
    materialization -- the L2-semantic vs L2.5-byte gap, enumerable).

E2  A typed SourceRef prototype validated against every real `source`
    block in the wild: what shapes/fields actually exist, does a typed
    object capture them all, and does normalize->emit round-trip exactly?

E3  The boundary expressed through the EXISTING state harness:
    assert_round_trip(read, apply=build_entity, invert=to_manifest) with
    the L2-semantic restriction (original keys only) -- does the states.py
    machinery already speak this contract, or does it need a new interface?

Usage:  python tests/one-offs/thinking/boundary_contract_experiments.py
"""
import glob
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "packages", "dazzlecmd-lib", "src"))
sys.path.insert(0, os.path.join(REPO, "src"))

from dazzlecmd_lib.entity import build_entity  # noqa: E402
from dazzlecmd_lib.states import assert_round_trip  # noqa: E402


def find_manifests():
    """(path, kind, dict) for every real manifest in the repo."""
    out = []
    for p in glob.glob(os.path.join(REPO, "projects", "**", ".dazzlecmd.json"),
                       recursive=True):
        try:
            with open(p, encoding="utf-8") as f:
                out.append((p, "tool", json.load(f)))
        except (json.JSONDecodeError, OSError):
            pass
    for p in glob.glob(os.path.join(REPO, "kits", "*.kit.json")):
        try:
            with open(p, encoding="utf-8") as f:
                out.append((p, "kit", json.load(f)))
        except (json.JSONDecodeError, OSError):
            pass
    # in-repo kit manifests (.kit.json inside projects/<ns>/)
    for p in glob.glob(os.path.join(REPO, "projects", "*", ".kit.json")):
        try:
            with open(p, encoding="utf-8") as f:
                out.append((p, "kit", json.load(f)))
        except (json.JSONDecodeError, OSError):
            pass
    return out


# ---------------------------------------------------------------------------
# E1 -- the round-trip identity over the real population
# ---------------------------------------------------------------------------
def e1(manifests):
    print("=" * 72)
    print("E1: to_manifest(build_entity(m)) vs m  --  the boundary identity")
    print("=" * 72)
    lost_total, changed_total, added_keys_seen = 0, 0, {}
    for path, kind, m in manifests:
        try:
            e = build_entity(dict(m), entity_type=kind)
            back = e.to_manifest()
        except Exception as exc:
            print(f"  BUILD-FAIL {os.path.relpath(path, REPO)}: {exc!r}")
            continue
        lost = [k for k in m if k not in back]
        changed = [k for k in m if k in back and back[k] != m[k]]
        added = [k for k in back if k not in m]
        for k in added:
            added_keys_seen[k] = added_keys_seen.get(k, 0) + 1
        if lost or changed:
            print(f"  {os.path.relpath(path, REPO)} [{kind}]")
            if lost:
                print(f"    LOST:    {lost}")
            if changed:
                for k in changed:
                    print(f"    CHANGED: {k}: {m[k]!r} -> {back[k]!r}")
        lost_total += len(lost)
        changed_total += len(changed)
    print(f"\n  manifests tested: {len(manifests)}")
    print(f"  LOST keys (data loss):      {lost_total}   <- the invariant; must be 0")
    print(f"  CHANGED values (corruption): {changed_total}   <- must be 0")
    print(f"  ADDED keys (materialized defaults -- the L2/L2.5 gap):")
    for k, n in sorted(added_keys_seen.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<20} added in {n} manifest(s)")
    return lost_total, changed_total


# ---------------------------------------------------------------------------
# E2 -- the SourceRef prototype vs the wild population
# ---------------------------------------------------------------------------
def e2(manifests):
    print()
    print("=" * 72)
    print("E2: typed SourceRef prototype vs every real `source` block")
    print("=" * 72)
    from typing import Optional
    from pydantic import BaseModel, ConfigDict

    class SourceRef(BaseModel):
        """Prototype: ONE typed object normalizing both wild forms."""
        model_config = ConfigDict(extra="allow")  # capture unknown fields
        url: Optional[str] = None
        _form: str = "dict"  # remembered input shape for faithful re-emission

        @classmethod
        def from_manifest(cls, raw):
            if isinstance(raw, str):
                obj = cls(url=raw)
                object.__setattr__(obj, "_form", "str")
                return obj
            obj = cls(**raw)
            object.__setattr__(obj, "_form", "dict")
            return obj

        def to_manifest(self):
            if self._form == "str":
                return self.url
            d = {"url": self.url} if self.url is not None else {}
            d.update(self.model_extra or {})
            return d

    population = []
    for path, kind, m in manifests:
        if "source" in m:
            population.append((path, kind, m["source"]))
    print(f"  real `source` blocks found: {len(population)}")
    shapes, fields_seen, failures = {}, {}, 0
    for path, kind, raw in population:
        shape = type(raw).__name__
        shapes[shape] = shapes.get(shape, 0) + 1
        if isinstance(raw, dict):
            for k in raw:
                fields_seen[k] = fields_seen.get(k, 0) + 1
        try:
            ref = SourceRef.from_manifest(raw)
            back = ref.to_manifest()
            if back != raw:
                failures += 1
                print(f"  ROUND-TRIP FAIL {os.path.relpath(path, REPO)}: {raw!r} -> {back!r}")
        except Exception as exc:
            failures += 1
            print(f"  VALIDATE FAIL {os.path.relpath(path, REPO)}: {raw!r}: {exc!r}")
    print(f"  shapes in the wild: {shapes}")
    print(f"  dict-form fields in the wild: {fields_seen}")
    print(f"  SourceRef failures: {failures}  <- 0 means a typed object CAN hold the population")
    return len(population), shapes, fields_seen, failures


# ---------------------------------------------------------------------------
# E3 -- the boundary through the EXISTING states.py harness
# ---------------------------------------------------------------------------
def e3(manifests):
    print()
    print("=" * 72)
    print("E3: the boundary as a state transition through assert_round_trip")
    print("=" * 72)
    ok, fail = 0, 0
    for path, kind, m in manifests:
        original_keys = list(m.keys())
        holder = {"form": "manifest", "data": dict(m)}

        def read():
            # L2-SEMANTIC restriction: compare only the original keys
            # (mirrors EntityState.on(*axes) -- ignore materialized defaults).
            return {k: holder["data"].get(k) for k in original_keys}

        def apply():
            holder["entity"] = build_entity(dict(holder["data"]), entity_type=kind)
            holder["form"] = "entity"
            return holder["entity"]          # the "receipt" is the entity

        def invert(entity):
            holder["data"] = entity.to_manifest()
            holder["form"] = "manifest"

        try:
            assert_round_trip(read, apply, invert)
            ok += 1
        except AssertionError as exc:
            fail += 1
            print(f"  IDENTITY BROKEN {os.path.relpath(path, REPO)}: {exc}")
        except Exception as exc:
            fail += 1
            print(f"  ERROR {os.path.relpath(path, REPO)}: {exc!r}")
    print(f"  harness round-trips: {ok} OK / {fail} FAIL")
    print("  (apply=build_entity is the 'group' into typed form; invert=to_manifest")
    print("   is the 'ungroup' back; conserved invariant = the manifest's own keys.)")
    return ok, fail


if __name__ == "__main__":
    manifests = find_manifests()
    l, c = e1(manifests)
    n, shapes, fields, f2 = e2(manifests)
    ok, f3 = e3(manifests)
    print()
    print("=" * 72)
    print("VERDICT INPUTS")
    print("=" * 72)
    print(f"  E1 lost={l} changed={c}  |  E2 population={n} failures={f2}  |  E3 {ok} OK / {f3} FAIL")
