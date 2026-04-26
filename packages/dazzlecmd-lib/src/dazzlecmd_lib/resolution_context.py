"""Resolution context for FQCN lookups.

When the engine resolves a user-typed name (``dz <name>``) to a concrete
tool, it returns both the target project AND a ``ResolutionContext`` that
records HOW the resolution happened. This lets callers render provenance
("resolved via alias X -> Y"), emit ambiguity notifications, and detect
cases like stale favorites.

Design notes:

- ``resolution_kind`` is a single Literal instead of parallel booleans
  (via_alias / via_favorite / via_precedence), so impossible states like
  "both favorite AND alias" are unrepresentable by construction.
- ``canonical_fqcn`` is always set for a successful resolution. The user's
  input might have been a short name, a favorite, an alias, or a kit-
  qualified shortcut, but the engine resolves it to exactly one canonical
  FQCN (or fails).
- ``alias_fqcn`` is set when resolution traversed an alias. Important: a
  favorite can POINT TO an alias — in that case ``resolution_kind`` is
  ``"favorite"`` AND ``alias_fqcn`` is set.
- ``notification`` stays a ``str | None`` for now. Future refinement may
  promote it to typed sub-fields (ambiguity details, stale-favorite info)
  if consumers need to react programmatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


ResolutionKind = Literal[
    "canonical",        # Direct hit on a canonical FQCN (e.g., "core:rn")
    "alias",            # Direct hit on an alias FQCN (e.g., "claude:cleanup")
    "qualified_alias",  # Qualified-alias dispatch (e.g., "dazzletools:claude:cleanup"
                        # resolves to alias "claude:cleanup" -> canonical
                        # "dazzletools:claude-cleanup"). Display sections use the
                        # qualified form; this resolution path lets users invoke
                        # the same form they read.
    "kit_shortcut",     # 2-segment shortcut resolved within a kit (e.g., "wtf:locked" -> "wtf:core:locked")
    "favorite",         # Short name resolved via user favorites config
    "precedence",       # Short name resolved via kit precedence ordering
]


@dataclass
class ResolutionContext:
    """Metadata about how a user-typed name resolved to a canonical project.

    Returned alongside the resolved project from ``FQCNIndex.resolve()``
    and ``AggregatorEngine.find_project()``.
    """

    original_input: str
    """What the user typed (short name, FQCN, alias, etc.)."""

    canonical_fqcn: str
    """The canonical FQCN of the resolved project."""

    resolution_kind: ResolutionKind
    """How the resolution happened. Makes impossible states unrepresentable."""

    alias_fqcn: Optional[str] = None
    """The alias FQCN traversed, if any. Set when resolution_kind is
    ``"alias"`` OR when a favorite pointed to an alias. ``None`` otherwise."""

    notification: Optional[str] = None
    """Optional stderr-ready message about the resolution — ambiguity
    disambiguation, stale favorite warning, etc. ``None`` for clean
    unambiguous resolutions."""


__all__ = ["ResolutionKind", "ResolutionContext"]
