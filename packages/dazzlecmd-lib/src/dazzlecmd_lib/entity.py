"""DazzleEntity -- the typed object model for every co-level occupant.

The foundation of the {grouping, ungrouping} = {P, ¬P} object model (the
"same bones" thesis made code). Today tools/kits/aggregators are anonymous
dicts; this module gives them one typed base.

Locked model (synthesis DWP 2026-06-07__04-24-42; validated via a 5-round
/collaborate3 with Gemini 2.5 Pro + the probes in
``tests/one-offs/dazzleentity_probes.py``):

- ``Groupable`` -- the UNIVERSAL grouping/ungrouping capability (mixin). The
  five verbs (GROUP / UNGROUP / HIDE / EXPOSE / REBIND) + the canonical-identity
  contract (C1/C2/C3). Mixed into the entity base so grouping/ungrouping is
  universal WITHOUT forcing one inheritance root.
- ``DazzleEntity(Groupable, BaseModel)`` -- base for every ON-TREE co-level
  occupant (anything reached via the ``:`` hierarchy axis): tool / kit /
  aggregator now, property / environment later (the discriminated union is
  OPEN to additive members).
- ``Tool`` / ``Kit`` / ``Aggregator`` -- discriminated-union subtypes on
  ``type``. Type is *emergent at discovery* (the loader detects structural
  markers and sets ``type``) and *fixed for the process lifetime*.

NOT in this module (deliberately): ``KindBase`` -- the OFF-tree schema-contract
for kind-*types* (recipe/note/...) is #77-era and lives in the kind registry,
not here. A blueprint is not a building.

Migration boundary: only the TOP-LEVEL entity is a ``DazzleEntity``. Nested
blocks (``runtime``, ``_vars``, ``volumes``, ``platforms``, ``setup``) stay
plain dicts -- they are an entity's field data (the future ``.`` field axis),
not co-level occupants. Hence ``extra="allow"`` + a backward-compat shim:
existing ``project["x"]`` / ``project.get("x")`` call sites keep working
unchanged while the codebase migrates to attribute access incrementally.

Phase 0 scope: the base, the union, the shim, set-once canonical-FQCN (C1).
The grouping/ungrouping *verbs* are declared as the capability surface but
their tree mechanics (move/graduate/hide) land post-0.8.x with the
grouping/ungrouping implementation work.
"""

from __future__ import annotations

import warnings
from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class AmbiguousEntityTypeError(Exception):
    """Raised when an entity's type cannot be determined from its markers.

    Fail fast, fail loudly: a directory that is somehow both a tool and a kit
    (or neither) is a corrupt/invalid state the user must fix, not something to
    paper over with a silent default.
    """


# ---------------------------------------------------------------------------
# Groupable -- the universal {grouping, ungrouping} capability
# ---------------------------------------------------------------------------
class Groupable:
    """Mixin declaring the grouping/ungrouping capability ("the bones").

    The five verbs of the boundary-formation primitive
    ({grouping, ungrouping} = {P, ¬P}) plus the canonical-identity contract:

    - **C1 canonical immutability** -- the canonical FQCN is a read-only
      invariant once set (the axis-invariant identity that survives every
      display projection). ``DazzleEntity`` implements this via a set-once
      ``fqcn`` property.
    - **C2 round-trip integrity** -- a consumer's display projection is
      invertible back to the canonical.
    - **C3 constitutional inclusion** -- constitutional items appear in every
      consumer (may be hidden, never ungrouped).

    Phase 0 declares the verbs as the capability surface; their concrete
    tree mechanics (move between parents, graduate to a new repo, hide/expose
    in a frame) are implemented post-0.8.x alongside the grouping/ungrouping
    work. They raise ``NotImplementedError`` until then so callers fail
    explicitly rather than silently no-op.

    The capability is a *mixin*, not a base class, on purpose: it is mixed
    into ``DazzleEntity`` (tree occupants) and -- in the #77 era -- may be
    mixed into ``KindBase`` (registry-space grouping via zone-3 loadability),
    making grouping/ungrouping universal without a forced common ancestor.
    """

    _CAP_DEFERRED: ClassVar[str] = (
        "grouping/ungrouping tree mechanics land post-0.8.x "
        "(see the grouping/ungrouping DWPs); Phase 0 ships the capability "
        "surface + the C1 canonical-identity contract only"
    )

    def group(self, *args: Any, **kwargs: Any) -> Any:
        """P: incorporate item(s) into this boundary."""
        raise NotImplementedError(f"group(): {self._CAP_DEFERRED}")

    def ungroup(self, *args: Any, **kwargs: Any) -> Any:
        """¬P: disincorporate item(s) from this boundary (generative/irreversible)."""
        raise NotImplementedError(f"ungroup(): {self._CAP_DEFERRED}")

    def hide(self, *args: Any, **kwargs: Any) -> Any:
        """Display-off, dispatch-on (frame-relative)."""
        raise NotImplementedError(f"hide(): {self._CAP_DEFERRED}")

    def expose(self, *args: Any, **kwargs: Any) -> Any:
        """Undo hide (frame-relative)."""
        raise NotImplementedError(f"expose(): {self._CAP_DEFERRED}")

    def rebind(self, *args: Any, **kwargs: Any) -> Any:
        """Change coupling / resolution / identity without containment change."""
        raise NotImplementedError(f"rebind(): {self._CAP_DEFERRED}")


# ---------------------------------------------------------------------------
# DazzleEntity -- base for all on-tree co-level occupants
# ---------------------------------------------------------------------------
class DazzleEntity(Groupable, BaseModel):
    """Typed base for any FQCN-addressable co-level occupant.

    Carries the stable manifest fields as typed attributes; everything else
    (type-specific fields + nested blocks + computed ``_``-prefixed runtime
    fields) flows through ``extra="allow"`` so the manifest round-trips and
    the dict-era call sites keep working via the shim.
    """

    model_config = ConfigDict(extra="allow", frozen=False, populate_by_name=True)

    # --- stable manifest fields (common to every entity type) ---
    name: str
    namespace: str = ""
    description: str = ""
    version: str = "0.0.0"

    # --- computed runtime fields (Phase 1 Stage 3) ---
    # Promoted from the `_`-prefixed extra keys so they are typed and
    # attribute-accessible. These are NOT manifest data -- to_manifest()
    # strips them (see _COMPUTED_FIELDS). Legacy dict access
    # (``project["_dir"]`` / ``project["_fqcn"]``) keeps working via
    # _LEGACY_KEY_MAP until every reader migrates to attribute access.
    short_name: Optional[str] = None            # was "_short_name"
    kit_import_name: Optional[str] = None        # was "_kit_import_name"
    directory: Optional[str] = None              # was "_dir"
    manifest_path: Optional[str] = None          # was "_manifest_path"
    cached: bool = False                          # was "_cached"
    kit_source: Optional[str] = None             # was "_source" (kit .kit.json path; renamed -- "source" is a manifest block)
    kit_name: Optional[str] = None               # was "_kit_name"
    kit_active: bool = True                       # was "_kit_active"
    auto_realpath_alias: bool = False            # was "_auto_realpath_alias"
    canonical_fqcn: Optional[str] = None         # was "_canonical_fqcn"
    original_name: Optional[str] = None          # was "_original_name"

    # Legacy dict-era key -> promoted field/property name. Keeps existing
    # ``entity["_dir"]`` / ``entity["_fqcn"]`` call sites (read AND write)
    # working while they migrate to attribute access. (`_fqcn` -> the set-once
    # `fqcn` property.) Removed once all in-scope readers are migrated.
    _LEGACY_KEY_MAP: ClassVar[Dict[str, str]] = {
        "_fqcn": "fqcn",
        "_short_name": "short_name",
        "_kit_import_name": "kit_import_name",
        "_dir": "directory",
        "_manifest_path": "manifest_path",
        "_cached": "cached",
        "_source": "kit_source",
        "_kit_name": "kit_name",
        "_kit_active": "kit_active",
        "_auto_realpath_alias": "auto_realpath_alias",
        "_canonical_fqcn": "canonical_fqcn",
        "_original_name": "original_name",
    }
    # Computed (non-manifest) field names -- stripped by to_manifest().
    _COMPUTED_FIELDS: ClassVar[frozenset] = frozenset({
        "short_name", "kit_import_name", "directory", "manifest_path",
        "cached", "kit_source", "kit_name", "kit_active",
        "auto_realpath_alias", "canonical_fqcn", "original_name",
    })

    # ------------------------------------------------------------------
    # C1: set-once canonical FQCN (the axis-invariant identity)
    # ------------------------------------------------------------------
    @property
    def fqcn(self) -> Optional[str]:
        """The canonical FQCN. Read-only once set (C1)."""
        return (self.__pydantic_extra__ or {}).get("_fqcn")

    @fqcn.setter
    def fqcn(self, value: str) -> None:
        # Set-once (C1): the canonical FQCN must never CHANGE. Re-setting the
        # SAME value is an idempotent no-op (tolerates a harmless re-annotation
        # pass); re-setting a DIFFERENT value is the violation that raises.
        current = (self.__pydantic_extra__ or {}).get("_fqcn")
        if current is not None and current != value:
            raise RuntimeError(
                f"canonical FQCN already set to {current!r}; cannot reset to "
                f"{value!r} (C1: canonical identity is set-once)"
            )
        self._set_extra_field("_fqcn", value)

    # ------------------------------------------------------------------
    # Computed-field writer -- the SOLE place that touches __pydantic_extra__.
    # (The `_`-prefix is a trap: `entity._x = v` becomes a Pydantic PRIVATE
    # attribute, invisible to model_dump. Computed `_`-fields must be written
    # here, into __pydantic_extra__, to round-trip. Verified in the probe.)
    # ------------------------------------------------------------------
    def _set_extra_field(self, key: str, value: Any) -> None:
        if self.__pydantic_extra__ is None:
            object.__setattr__(self, "__pydantic_extra__", {})
        self.__pydantic_extra__[key] = value

    # ------------------------------------------------------------------
    # Backward-compat shim: existing dict call sites keep working unchanged.
    # Phase 0 keeps this transparent (no warning noise) because the engine
    # still relies on it everywhere. The DeprecationWarning ratchet
    # (``_warn_on_shim``) is OFF by default and gets flipped on in the
    # Phase-1 call-site migration, where pytest filterwarnings=error then
    # fails CI on any still-unmigrated dict access.
    # ------------------------------------------------------------------
    _warn_on_shim: ClassVar[bool] = False

    def _is_typed_key(self, key: str) -> bool:
        """True if ``key`` (or its legacy alias) names a typed field or property.

        Only typed fields/properties have a safe attribute form. Extra keys
        (manifest data + nested blocks like ``runtime``/``always_active``/
        ``tools``) have no attribute form -- ``entity.always_active`` raises
        when the key is absent -- so dict access to them is legitimate and
        permanent. The ratchet warns only for typed-key access.
        """
        mapped = type(self)._LEGACY_KEY_MAP.get(key, key)
        if mapped in type(self).model_fields:
            return True
        return isinstance(getattr(type(self), mapped, None), property)

    def _maybe_warn_shim(self, how: str, key: Optional[str] = None) -> None:
        if not type(self)._warn_on_shim:
            return
        # Keyed access (getitem/setitem/get) warns only for TYPED keys; bulk
        # Mapping methods (items/keys/values, key=None) always warn.
        if key is not None and not self._is_typed_key(key):
            return
        warnings.warn(
            f"legacy dict-style access ({how}) on a DazzleEntity; "
            f"use attribute access instead",
            DeprecationWarning,
            stacklevel=3,
        )

    def _raw_get(self, key: str) -> Any:
        """Dict-style lookup WITHOUT the deprecation warning.

        Used by the shim Mapping methods (``items``/``values``) so they warn
        once per call, not once per item. Legacy ``_``-prefixed keys route to
        their promoted field/property via _LEGACY_KEY_MAP.
        """
        mapped = type(self)._LEGACY_KEY_MAP.get(key, key)
        try:
            return getattr(self, mapped)
        except AttributeError:
            extra = self.__pydantic_extra__ or {}
            if key in extra:
                return extra[key]
            raise KeyError(key)

    def __getitem__(self, key: str) -> Any:
        self._maybe_warn_shim("[]", key)
        return self._raw_get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self._maybe_warn_shim("[]=", key)
        # Legacy `_`-keys route to their promoted field/property; so an
        # existing ``project["_dir"] = x`` lands in the typed `directory`
        # field, and ``project["_fqcn"] = x`` goes through the set-once C1
        # property (item-assignment can't bypass C1).
        mapped = type(self)._LEGACY_KEY_MAP.get(key, key)
        prop = getattr(type(self), mapped, None)
        if isinstance(prop, property) and prop.fset is not None:
            prop.fset(self, value)
            return
        if mapped in type(self).model_fields:
            object.__setattr__(self, mapped, value)
        else:
            self._set_extra_field(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        self._maybe_warn_shim(".get()", key)
        try:
            return self._raw_get(key)
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        mapped = type(self)._LEGACY_KEY_MAP.get(key, key)
        if mapped in type(self).model_fields:
            return True
        return key in (self.__pydantic_extra__ or {})

    # --- read-Mapping methods (faithful dict view; warned under the ratchet) ---
    # The shim must be a CORRECT Mapping while it exists: code that does
    # ``manifest.items()`` on an entity (e.g. ``mode.cache_manifest``) used to
    # crash with AttributeError because only __getitem__/get/__contains__ were
    # provided. These complete the read view (keys + extra, incl computed
    # ``_``-prefixed keys -- consistent with ``__contains__``).
    #
    # Deliberately NOT overriding ``__iter__``/``__len__``: pydantic v2's
    # BaseModel.__iter__ yields (field, value) tuples and ``dict(entity)``
    # relies on that contract; redefining it to yield keys would break
    # ``dict(entity)``. No top-level call site iterates a single entity, so
    # the dict-view via keys()/values()/items() is sufficient.
    def _shim_keys(self) -> List[str]:
        keys = list(type(self).model_fields.keys())
        extra = self.__pydantic_extra__ or {}
        for k in extra:
            if k not in type(self).model_fields:
                keys.append(k)
        return keys

    def keys(self) -> List[str]:
        self._maybe_warn_shim(".keys()")
        return self._shim_keys()

    def values(self) -> List[Any]:
        self._maybe_warn_shim(".values()")
        return [self._raw_get(k) for k in self._shim_keys()]

    def items(self) -> List[Any]:
        self._maybe_warn_shim(".items()")
        return [(k, self._raw_get(k)) for k in self._shim_keys()]

    # ------------------------------------------------------------------
    # Serialization: manifest fields only (strip computed `_`-keys).
    # The manifest is the source of truth; the object is its reflection.
    # ------------------------------------------------------------------
    def to_manifest(self) -> Dict[str, Any]:
        data = self.model_dump()
        computed = type(self)._COMPUTED_FIELDS
        for key in list(data):
            # Strip computed runtime fields (promoted, non-underscore) and any
            # `_`-prefixed runtime key (e.g. `_fqcn`). Note: `_vars` is manifest
            # data that merely starts with `_` and is stripped here too -- that
            # pre-existing behavior is unchanged; rescuing it is a separate fix.
            if key in computed or key.startswith("_"):
                data.pop(key, None)
        return data

    # ------------------------------------------------------------------
    # Visibility (frame-relative). Phase 0 stub: everything is visible.
    # The four-level ladder (Visible/Silenced/Hidden/Shadowed) resolves
    # against a consumer frame's presentation policy post-0.8.x.
    # ------------------------------------------------------------------
    def visibility_in(self, frame: Any = None) -> str:
        return "visible"


# ---------------------------------------------------------------------------
# Discriminated-union subtypes (OPEN -- Property/Environment join later)
# ---------------------------------------------------------------------------
class Tool(DazzleEntity):
    type: Literal["tool"] = "tool"


class Kit(DazzleEntity):
    type: Literal["kit"] = "kit"


class Aggregator(DazzleEntity):
    type: Literal["aggregator"] = "aggregator"
    # Phase 2 retypes `config` to the (then-Pydantic) AggregatorConfig and
    # composes it here (has-a). Left untyped in Phase 0 to keep this stage's
    # rollback boundary clean.


# The open union + its adapter. New co-level subtypes (Property, Environment,
# Workspace) join additively: add the subclass + a `type` Literal + extend
# the Union -- no rewrite of the loader/engine.
AnyDazzleEntity = Annotated[
    Union[Tool, Kit, Aggregator],
    Field(discriminator="type"),
]
ENTITY_ADAPTER: TypeAdapter = TypeAdapter(AnyDazzleEntity)


# ---------------------------------------------------------------------------
# Type detection (additive-marker model) + construction
# ---------------------------------------------------------------------------
_VALID_TYPES = {"tool", "kit", "aggregator"}


def detect_type(markers: Dict[str, bool]) -> str:
    """Resolve an entity's type from its structural markers (additive model).

    ``markers`` is a presence map, e.g.
    ``{"has_tool_manifest": True, "has_kit_manifest": False, "has_kits_dir": False}``.
    Precedence: aggregator (has ``kits/``) > kit (has ``*.kit.json``) >
    tool (has ``*.dazzlecmd.json``). A directory matching none is ambiguous.
    """
    if markers.get("has_kits_dir"):
        return "aggregator"
    if markers.get("has_kit_manifest"):
        return "kit"
    if markers.get("has_tool_manifest"):
        return "tool"
    raise AmbiguousEntityTypeError(
        f"cannot determine entity type from markers {markers!r}: "
        f"no tool/kit/aggregator marker present"
    )


def build_entity(data: Dict[str, Any], *, entity_type: Optional[str] = None) -> DazzleEntity:
    """Construct the right DazzleEntity subtype from manifest ``data``.

    The loader passes ``entity_type`` explicitly (it knows whether it is
    discovering a tool vs a kit). Callers that only have a marker map should
    call :func:`detect_type` first. The discriminated union then validates
    ``data`` into the correct subclass; an unknown/missing type hard-fails.
    """
    payload = dict(data)
    if entity_type is not None:
        payload["type"] = entity_type
    t = payload.get("type")
    if t not in _VALID_TYPES:
        raise AmbiguousEntityTypeError(
            f"entity 'type' missing or invalid ({t!r}); "
            f"expected one of {sorted(_VALID_TYPES)}"
        )
    return ENTITY_ADAPTER.validate_python(payload)


def reserve_field_axis(name: str = "", namespace: str = "") -> None:
    """Reject ``.`` in FQCN name segments -- it's reserved for the field axis.

    Two-axis FQCN (#77 Decision #7): ``:`` navigates the hierarchy; ``.`` will
    descend into an entity's record fields (e.g. ``find:srch.template``) once
    that lands post-0.8.x. No current tool/kit/namespace name uses ``.``;
    rejecting it now -- at a single enforcement point -- keeps the two axes
    unambiguous so consumers never start writing dotted names against ``:``.
    """
    for label, seg in (("name", name), ("namespace", namespace)):
        if seg and "." in seg:
            raise ValueError(
                f"invalid {label} {seg!r}: '.' is reserved for the field-access "
                f"axis; use '-' or '_' in entity names "
                f"(two-axis FQCN: ':' is hierarchy, '.' is field access)"
            )
