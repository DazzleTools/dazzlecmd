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

    Behavioral phase (#84): the verbs are state-transition operators, and all
    five are now LIVE (see ``dazzlecmd_lib.contexts``) -- ``rebind``
    (alias + mode-switch), ``hide``/``expose`` (the visibility ladder), and
    ``group``/``ungroup`` (in-tree containment). Each delegates to a context.
    The one deferred MECHANIC is graduation -- ``ungroup``'s GENERATIVE regime
    (tool -> own git repo): declared in the registry as a ``CompositeTransition``,
    refused at the criticality boundary until its fs+git body lands (#73).

    Frame (reserved): a presentation/consumer context (ties to
    ``AggregatorConfig.presentation``). ``rebind`` is NOT frame-relative;
    ``hide``/``expose`` will consume Frame -- see ``visibility_in(frame)``.

    The capability is a *mixin*, not a base class, on purpose: it is mixed
    into ``DazzleEntity`` (tree occupants) and -- in the #77 era -- may be
    mixed into ``KindBase`` (registry-space grouping via zone-3 loadability),
    making grouping/ungrouping universal without a forced common ancestor.
    """

    def group(self, target: Any, *, context: Any) -> Any:
        """P: incorporate this entity into the boundary ``target`` (a kit), within
        ``context`` (a ``dazzlecmd_lib.contexts.ContainmentContext``). A
        reversible in-tree move -- C2 = ``local_incorporability`` (files + canonical
        FQCN untouched). Returns a ``ContainmentReceipt``."""
        if context is None:
            raise TypeError(
                "group(target, *, context=...) requires a ContainmentContext"
            )
        return context.apply(self, target, verb="group")

    def ungroup(self, target: Any = None, *, context: Any) -> Any:
        """¬P: disincorporate this entity from its boundary (reversible in-tree).
        With ``target=ContainmentContext.GRADUATE`` the GENERATIVE graduation
        regime is requested -- declared in the registry as a ``CompositeTransition``
        but refused until its fs+git body lands (#73). Constitutional
        (``always_active``) items refuse (C3). Returns a ``ContainmentReceipt``."""
        if context is None:
            raise TypeError(
                "ungroup(target=None, *, context=...) requires a ContainmentContext"
            )
        return context.apply(self, target, verb="ungroup")

    def hide(self, to: str = "hidden", *, context: Any) -> Any:
        """Walk DOWN the visibility ladder (toward MORE suppression) to ``to``
        (``"silenced"`` / ``"hidden"`` / ``"shadowed"``), within ``context`` (a
        ``dazzlecmd_lib.contexts.VisibilityContext``).

        Dispatch always survives (C2 = ``canonical_dispatch``); shadowing a
        constitutional (``always_active``) item raises ``CriticalityBoundaryError``
        (C3: constitutional items may be hidden, never removed). Returns a
        ``VisibilityReceipt``. The third live Groupable verb."""
        if context is None:
            raise TypeError(
                "hide(to=..., *, context=...) requires a VisibilityContext"
            )
        return context.apply(self, to, verb="hide")

    def expose(self, to: str = "visible", *, context: Any) -> Any:
        """Walk UP the visibility ladder (toward LESS suppression) to ``to``
        (``"visible"`` / ``"silenced"`` / ``"hidden"``), within ``context`` -- the
        inverse of ``hide``. Returns a ``VisibilityReceipt``."""
        if context is None:
            raise TypeError(
                "expose(to=..., *, context=...) requires a VisibilityContext"
            )
        return context.apply(self, to, verb="expose")

    def rebind(self, target: Any, *, context: Any) -> Any:
        """REBIND: change this entity's coupling/resolution to ``target`` within
        ``context``, WITHOUT changing its canonical identity (C1 ``fqcn`` is
        unchanged). The first live Groupable verb.

        The verb is entity-local in spirit (the same-bones thesis: entities ARE
        Groupable), but the mechanism is not -- alias routing lives on the
        ``FQCNIndex``, mode state on the filesystem -- so ``context`` (a
        ``dazzlecmd_lib.contexts.RebindContext``: ``AliasRebindContext`` /
        ``ModeRebindContext``) carries the handle plus the identity the verb
        itself can't (e.g. WHICH alias). Returns a ``RebindReceipt``; raises
        ``CriticalityBoundaryError`` when the transition's invariant cannot be
        preserved (would be irreversible).
        """
        if context is None:
            raise TypeError(
                "rebind(target, *, context=...) requires a RebindContext "
                "(e.g. AliasRebindContext or ModeRebindContext)"
            )
        return context.apply(self, target)


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

    # --- declared manifest fields (Phase 1 Stage 5) ---
    # The known manifest schema, typed so attribute access (entity.runtime,
    # entity.always_active) is always safe -- no AttributeError on absent keys.
    # Structured blocks stay dict/list valued (their internals are still dicts;
    # nested Pydantic models are a future refinement). Defaults match each
    # field's dominant `.get(key, default)` call site so adding them is
    # byte-identical. Novel/unmodeled manifest keys still land in extra
    # (extra="allow") and are read via model_extra. `_`-prefixed manifest keys
    # (_vars, _schema_version) CANNOT be fields (Pydantic private-attr trap) --
    # they stay extra, accessed via model_extra.
    # Tool-oriented:
    language: Optional[str] = None
    platform: str = "cross-platform"
    runtime: dict = Field(default_factory=dict)
    pass_through: bool = False
    taxonomy: dict = Field(default_factory=dict)
    lifecycle: dict = Field(default_factory=dict)
    platforms: list = Field(default_factory=list)   # top-level: list of supported platform names (runtime.platforms is a separate per-platform dict)
    dependencies: dict = Field(default_factory=dict)
    setup: Optional[dict] = None
    # NOTE: `source` is intentionally NOT typed -- it is polymorphic across
    # entity types (a kit's `source` is a URL string; a tool's is a
    # `{"url": ...}` dict). It stays in extra (extra="allow"); read it via
    # `.get("source")` / `model_extra`. Typing it per-subtype is a later option.
    long_description: str = ""
    # Kit-oriented (Optional/empty on tools):
    always_active: bool = False
    virtual: bool = False
    tools: list = Field(default_factory=list)
    name_rewrite: dict = Field(default_factory=dict)
    # Nested-aggregator child layout (kit-manifest schema keys; None = defaults).
    # Promoted post-shim (the v0.8.32 review): Stage 5 missed them because they
    # only occur on nested-aggregator kits, off the main sweep's path.
    tools_dir: Optional[str] = None
    manifest: Optional[str] = None

    # --- computed runtime fields (Phase 1 Stage 3) ---
    # Promoted from the `_`-prefixed extra keys so they are typed and
    # attribute-accessible. These are NOT manifest data -- to_manifest()
    # strips them (see _COMPUTED_FIELDS). Accessed via attribute
    # (``entity.directory`` / ``entity.fqcn``); the legacy dict shim that once
    # routed ``entity["_dir"]`` here was removed in the 0.8.0 lib bump.
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
    override_tools_dir: Optional[str] = None     # was "_override_tools_dir" (registry parent-level override)
    override_manifest: Optional[str] = None      # was "_override_manifest"

    # Computed (non-manifest) field names -- stripped by to_manifest().
    _COMPUTED_FIELDS: ClassVar[frozenset] = frozenset({
        "short_name", "kit_import_name", "directory", "manifest_path",
        "cached", "kit_source", "kit_name", "kit_active",
        "auto_realpath_alias", "canonical_fqcn", "original_name",
        "override_tools_dir", "override_manifest",
    })

    # `_`-prefixed keys that ARE manifest data (not computed annotations):
    # to_manifest() must preserve them or round-trips silently lose user data
    # (the `_vars` strip bug: mode.cache_manifest dropped template variables).
    # The `_`-prefix here is schema convention, not a computed marker.
    _MANIFEST_UNDERSCORE_KEYS: ClassVar[frozenset] = frozenset({
        "_vars", "_schema_version",
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
    # Untyped / extra access (the dict shim's replacement).
    # Typed manifest fields have attribute access (entity.runtime,
    # entity.always_active). The genuinely-untyped remainder -- the polymorphic
    # `source` block and `_`-prefixed extras (`_vars`, `_schema_version`) -- has
    # no attribute form and is read/written here via model_extra.
    # ------------------------------------------------------------------
    def extra_get(self, key: str, default: Any = None) -> Any:
        """Read an untyped/extra manifest key from ``model_extra``.

        THE CONTRACT (v0.8.32 review): exactly three categories of key live in
        extra, each for a stated reason -- everything else is a typed field with
        attribute access:

        1. **Genuinely polymorphic blocks** -- ``source`` (a kit's is a str URL,
           a tool's is a ``{"url": ...}`` dict; consumed schema-driven via
           ``aggregator_config.remote_url_paths`` over the manifest projection).
        2. **``_``-prefixed manifest data** -- ``_vars``, ``_schema_version``
           (a Pydantic constraint: a field literally named ``_vars`` becomes a
           private attr; see ``_MANIFEST_UNDERSCORE_KEYS``).
        3. **Novel/unmodeled keys** -- the open-world remainder
           (``extra="allow"``); third-party manifests may carry anything.
        """
        return (self.__pydantic_extra__ or {}).get(key, default)

    def extra_set(self, key: str, value: Any) -> None:
        """Write an untyped/extra manifest key into ``model_extra``."""
        self._set_extra_field(key, value)

    def has_extra(self, key: str) -> bool:
        """Whether an untyped/extra key is present in ``model_extra``."""
        return key in (self.__pydantic_extra__ or {})

    # ------------------------------------------------------------------
    # Serialization: manifest fields only (strip computed `_`-keys).
    # The manifest is the source of truth; the object is its reflection.
    # ------------------------------------------------------------------
    def to_manifest(self) -> Dict[str, Any]:
        data = self.model_dump()
        computed = type(self)._COMPUTED_FIELDS
        keep_underscore = type(self)._MANIFEST_UNDERSCORE_KEYS
        for key in list(data):
            # Strip computed runtime fields (promoted, non-underscore) and
            # `_`-prefixed runtime keys (e.g. `_fqcn`) -- EXCEPT the whitelisted
            # `_`-prefixed MANIFEST keys (`_vars`, `_schema_version`), which are
            # user data that must survive the round-trip (pre-v0.8.32, `_vars`
            # was silently dropped here, losing template variables through
            # mode.cache_manifest).
            if key in computed or (key.startswith("_") and key not in keep_underscore):
                data.pop(key, None)
        # None-valued OPTIONAL schema fields that were never in the source
        # manifest stay out of the projection (tools_dir/manifest are absent on
        # ordinary kits; emitting `"tools_dir": null` would dirty every manifest).
        for key in ("tools_dir", "manifest"):
            if data.get(key, "") is None:
                data.pop(key, None)
        return data

    # ------------------------------------------------------------------
    # Visibility: the entity's current ladder level
    # (visible/silenced/hidden/shadowed).
    # ------------------------------------------------------------------
    def visibility_in(self, frame: Any = None, *, context: Any = None) -> str:
        """Return the entity's current ladder level.

        Real for the GLOBAL path: pass a ``VisibilityContext`` to read the level
        from the running aggregator's config. Without a context the entity alone
        cannot know (visibility lives in config, not on the entity), so it reports
        ``"visible"``. ``frame`` is accepted and -- until #79 environments make
        frame-relative reads real -- falls back to the global level.
        """
        if context is not None:
            return context.current_level(self)
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


# Public API surface -- frozen until 1.0 (Gate I). See the lib README.
__all__ = [
    "AmbiguousEntityTypeError",
    "Groupable",
    "DazzleEntity",
    "Tool",
    "Kit",
    "Aggregator",
    "AnyDazzleEntity",
    "ENTITY_ADAPTER",
    "build_entity",
    "detect_type",
    "reserve_field_axis",
]
