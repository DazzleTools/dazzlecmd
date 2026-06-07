"""DazzleEntity falsification probes for the /collaborate3 design review (2026-06-07).

Runs the empirical tests Gemini 2.5 Pro proposed in Round 1, to collect REAL
data before committing to the DazzleEntity Pydantic redesign:

  P2  perf at scale       -- dict vs model_validate vs model_construct (in-mem + from-disk)
  P3  discriminated union -- single bloated class (A) vs discriminated union (B)
  Sx  shim transparency   -- __getitem__/__setitem__/.get parity with dict
  Rt  round-trip fidelity -- manifest -> entity -> to_manifest() equality
  Id  identity semantics  -- model_copy vs dict.copy; json.dumps failure mode
  C1  set-once + finalize  -- canonical FQCN immutability mechanics

Run: python tests/one-offs/dazzleentity_probes.py
Pure stdlib + pydantic; writes/reads temp manifests under %TEMP%.
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import tempfile
import time
from typing import Annotated, Literal, Optional, Union

import pydantic
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


def line(c="="):
    print(c * 72)


def realistic_manifest(i: int) -> dict:
    """A manifest shaped like a real .dazzlecmd.json tool."""
    return {
        "name": f"tool{i}",
        "namespace": "core" if i % 2 else "dazzletools",
        "description": f"Tool number {i} that does a useful cross-platform thing.",
        "version": "0.1.0",
        "runtime": {"type": "python", "interpreter": "python"},
        "script": f"tool{i}.py",
        "category": "file-tools",
        "tags": ["alpha", "beta", "gamma"],
        "platform": "cross-platform",
        "language": "python",
    }


# --------------------------------------------------------------------------
# The candidate DazzleEntity (single-class, extra="allow", with shim)
# --------------------------------------------------------------------------
class DazzleEntity(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=False, populate_by_name=True)

    name: str
    namespace: str = ""
    description: str = ""
    version: str = "0.0.0"

    # --- backward-compat shim so existing dict call sites keep working ---
    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            extra = self.__pydantic_extra__ or {}
            if key in extra:
                return extra[key]
            raise KeyError(key)

    def __setitem__(self, key, value):
        # route through a set-once property if one exists for this key
        prop = getattr(type(self), key.lstrip("_"), None)
        if isinstance(prop, property) and prop.fset is not None:
            prop.fset(self, value)
            return
        if key in type(self).model_fields:
            object.__setattr__(self, key, value)
        else:
            if self.__pydantic_extra__ is None:
                object.__setattr__(self, "__pydantic_extra__", {})
            self.__pydantic_extra__[key] = value

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        if key in type(self).model_fields:
            return True
        return key in (self.__pydantic_extra__ or {})

    # --- C1: set-once canonical FQCN as a property over __pydantic_extra__ ---
    @property
    def fqcn(self) -> Optional[str]:
        return (self.__pydantic_extra__ or {}).get("_fqcn")

    @fqcn.setter
    def fqcn(self, value):
        extra = self.__pydantic_extra__
        if extra and extra.get("_fqcn") is not None:
            raise RuntimeError(
                f"FQCN already set to {extra['_fqcn']!r}; cannot reset to {value!r}"
            )
        if extra is None:
            object.__setattr__(self, "__pydantic_extra__", {})
        self.__pydantic_extra__["_fqcn"] = value

    def to_manifest(self) -> dict:
        """Manifest fields only -- strip _-prefixed computed keys."""
        d = self.model_dump()
        extra = self.__pydantic_extra__ or {}
        for k in list(extra):
            if k.startswith("_"):
                d.pop(k, None)
        return d


# --------------------------------------------------------------------------
# P2 -- performance
# --------------------------------------------------------------------------
def probe_perf(n=500, repeats=30):
    line()
    print(f"P2  PERFORMANCE  (n={n} manifests, {repeats} repeats)")
    line()
    manifests = [realistic_manifest(i) for i in range(n)]

    def as_dict():
        return [dict(m) for m in manifests]

    def as_validate():
        return [DazzleEntity.model_validate(m) for m in manifests]

    def as_construct():
        return [DazzleEntity.model_construct(**m) for m in manifests]

    def bench(fn):
        samples = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - t0) * 1000.0)
        return statistics.mean(samples), statistics.median(samples), min(samples)

    for label, fn in [("dict copy", as_dict),
                      ("model_validate", as_validate),
                      ("model_construct", as_construct)]:
        mean, med, mn = bench(fn)
        print(f"  {label:18s} mean={mean:7.3f}ms  median={med:7.3f}ms  min={mn:7.3f}ms  "
              f"({mean*1000/n:.1f}us/entity)")

    # from-disk variant (realistic total incl. file I/O + json parse)
    tmp = tempfile.mkdtemp(prefix="dz_perf_")
    try:
        for i, m in enumerate(manifests):
            with open(os.path.join(tmp, f"t{i}.json"), "w", encoding="utf-8") as f:
                json.dump(m, f)
        files = [os.path.join(tmp, f) for f in os.listdir(tmp)]

        def disk_dict():
            out = []
            for fp in files:
                with open(fp, encoding="utf-8") as f:
                    out.append(json.load(f))
            return out

        def disk_validate():
            out = []
            for fp in files:
                with open(fp, encoding="utf-8") as f:
                    out.append(DazzleEntity.model_validate(json.load(f)))
            return out

        for label, fn in [("disk+dict", disk_dict), ("disk+validate", disk_validate)]:
            mean, med, mn = bench(fn)
            print(f"  {label:18s} mean={mean:7.3f}ms  median={med:7.3f}ms  min={mn:7.3f}ms")
        # access perf: attribute vs shim
        ents = as_validate()
        def attr_access():
            return [e.name for e in ents]
        def shim_access():
            return [e["name"] for e in ents]
        for label, fn in [("attr .name", attr_access), ("shim ['name']", shim_access)]:
            mean, med, mn = bench(fn)
            print(f"  {label:18s} mean={mean:7.3f}ms  median={med:7.3f}ms  min={mn:7.3f}ms")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# P3 -- discriminated union vs single bloated class
# --------------------------------------------------------------------------
def probe_union():
    line()
    print("P3  DISCRIMINATED UNION (B) vs SINGLE CLASS (A)")
    line()

    # Approach A: single class, optional fields
    class EntityA(BaseModel):
        model_config = ConfigDict(extra="allow")
        name: str
        type: str = "tool"
        runner: Optional[str] = None
        default_tool: Optional[str] = None

    # Approach B: discriminated union
    class BaseB(BaseModel):
        model_config = ConfigDict(extra="allow")
        name: str

    class ToolB(BaseB):
        type: Literal["tool"] = "tool"
        runner: str  # REQUIRED for a tool

    class KitB(BaseB):
        type: Literal["kit"] = "kit"
        default_tool: Optional[str] = None

    AnyB = Annotated[Union[ToolB, KitB], Field(discriminator="type")]
    adapter = TypeAdapter(AnyB)

    good_tool = {"name": "rn", "type": "tool", "runner": "python"}
    bad_tool = {"name": "rn", "type": "tool"}  # missing runner
    kit = {"name": "core", "type": "kit", "default_tool": "rn"}

    # A: silently accepts the bad tool (runner=None)
    a = EntityA.model_validate(bad_tool)
    print(f"  A(bad_tool) -> OK, runner={a.runner!r}  [validation MISS: no error on missing runner]")

    # B: discriminator picks ToolB; rejects bad tool
    b_ok = adapter.validate_python(good_tool)
    print(f"  B(good_tool) -> {type(b_ok).__name__}  (discriminator selected correct model)")
    b_kit = adapter.validate_python(kit)
    print(f"  B(kit) -> {type(b_kit).__name__}  (discriminator selected correct model)")
    try:
        adapter.validate_python(bad_tool)
        print("  B(bad_tool) -> OK  [UNEXPECTED -- expected ValidationError]")
    except ValidationError as e:
        errs = e.errors()
        print(f"  B(bad_tool) -> ValidationError: {errs[0]['loc']} {errs[0]['msg']!r}  "
              f"[validation CATCH: missing runner rejected]")
    # additive-marker flow: loader sets `type` then validates against union
    discovered = {"name": "find", "runner": "python"}
    discovered["type"] = "tool"   # emergent-type detection sets the discriminator
    picked = adapter.validate_python(discovered)
    print(f"  additive-marker flow: detect type='tool' -> union picks {type(picked).__name__}")


# --------------------------------------------------------------------------
# Sx -- shim transparency
# --------------------------------------------------------------------------
def probe_shim():
    line()
    print("Sx  SHIM TRANSPARENCY (object behaves like the old dict)")
    line()
    m = realistic_manifest(1)
    e = DazzleEntity.model_validate(m)
    checks = []
    checks.append(("e['name'] == dict['name']", e["name"] == m["name"]))
    checks.append(("e.get('name')", e.get("name") == m["name"]))
    checks.append(("e.get('missing', 'd')=='d'", e.get("missing", "d") == "d"))
    checks.append(("'name' in e", ("name" in e) is True))
    checks.append(("e['script'] (extra field)", e["script"] == m["script"]))
    # in-place computed mutation like the engine does today
    e["_kit_active"] = True
    checks.append(("e['_kit_active']=True then read", e["_kit_active"] is True))
    e["_dir"] = "/tmp/x"
    checks.append(("e['_dir'] set/read", e["_dir"] == "/tmp/x"))
    # KeyError on truly-missing
    try:
        _ = e["definitely_missing"]
        checks.append(("KeyError on missing", False))
    except KeyError:
        checks.append(("KeyError on missing", True))
    for label, ok in checks:
        print(f"  [{'OK ' if ok else 'XX '}] {label}")
    return all(ok for _, ok in checks)


# --------------------------------------------------------------------------
# Rt -- round-trip fidelity
# --------------------------------------------------------------------------
def probe_roundtrip():
    line()
    print("Rt  ROUND-TRIP FIDELITY (manifest -> entity -> to_manifest)")
    line()
    m = realistic_manifest(7)
    e = DazzleEntity.model_validate(m)
    # engine sets computed fields after construction
    e["_fqcn"] = "core:tool7"
    e["_kit_active"] = True
    back = e.to_manifest()
    same_keys = set(back) == set(m)
    same_vals = all(back.get(k) == v for k, v in m.items())
    no_computed = not any(k.startswith("_") for k in back)
    print(f"  manifest keys preserved: {same_keys}")
    print(f"  manifest values preserved: {same_vals}")
    print(f"  computed _-keys stripped from manifest: {no_computed}")
    print(f"  fqcn accessible via property: {e.fqcn!r}")
    print(f"  to_manifest() == original dict: {back == m}")
    return same_keys and same_vals and no_computed and back == m


# --------------------------------------------------------------------------
# Id -- identity / json.dumps failure mode
# --------------------------------------------------------------------------
def probe_identity():
    line()
    print("Id  IDENTITY & json.dumps FAILURE MODE")
    line()
    e = DazzleEntity.model_validate(realistic_manifest(3))
    idx = {}
    idx["core:tool3"] = e
    print(f"  index stores entity by fqcn-string key; idx[k] is e: {idx['core:tool3'] is e}")
    cp = e.model_copy()
    print(f"  model_copy() is a DIFFERENT object: {cp is not e}")
    cp.name = "changed"
    print(f"  mutating the copy does NOT change indexed original: {idx['core:tool3'].name != 'changed'}")
    try:
        json.dumps(e)
        print("  json.dumps(entity) -> OK  [UNEXPECTED]")
    except TypeError as ex:
        print(f"  json.dumps(entity) -> TypeError (expected): {str(ex)[:60]}...")
    print(f"  json.dumps(e.to_manifest()) works: {bool(json.dumps(e.to_manifest()))}")
    print(f"  isinstance(e, dict): {isinstance(e, dict)}  [False -> isinstance(x,dict) checks will break]")


# --------------------------------------------------------------------------
# C1 -- set-once / finalize
# --------------------------------------------------------------------------
def probe_c1():
    line()
    print("C1  SET-ONCE CANONICAL FQCN")
    line()
    e = DazzleEntity.model_validate(realistic_manifest(9))
    e.fqcn = "core:tool9"
    print(f"  first set: fqcn={e.fqcn!r}")
    try:
        e.fqcn = "core:hacked"
        print("  second set: OK  [UNEXPECTED -- set-once not enforced]")
    except RuntimeError as ex:
        print(f"  second set rejected (expected): {str(ex)[:60]}...")
    # via shim item-assignment routes through the property too
    e2 = DazzleEntity.model_validate(realistic_manifest(10))
    e2["_fqcn"] = "core:tool10"
    print(f"  shim e2['_fqcn']=x routed through property: fqcn={e2.fqcn!r}")
    try:
        e2["_fqcn"] = "core:hacked2"
        print("  shim second set: OK  [LEAK -- item-assignment bypassed set-once]")
    except RuntimeError:
        print("  shim second set rejected (expected): item-assignment honors set-once")


if __name__ == "__main__":
    print(f"pydantic {pydantic.VERSION}  python {os.sys.version.split()[0]}")
    probe_perf()
    probe_union()
    ok_shim = probe_shim()
    ok_rt = probe_roundtrip()
    probe_identity()
    probe_c1()
    line()
    print(f"SUMMARY: shim_transparent={ok_shim}  roundtrip_fidelity={ok_rt}")
    line()
