"""
preservelib - Library for file preservation with path normalization and verification.

This is a standalone copy embedded in safedel. The canonical source is at
c:\\code\\preserve\\preservelib\\. Changes here should be kept generic and
pushed upstream for the official dazzlelib release.

This __init__.py is simplified to avoid pulling in the full preserve package
or external dependencies like dazzle_filekit. Individual modules can be
imported directly (e.g., from preservelib.metadata import collect_file_metadata).
"""

import logging

__version__ = "0.4.0"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Lazy imports -- only pull in what's actually used.
# This avoids circular imports and missing dependency errors.
# Users should import directly from submodules:
#   from preservelib.metadata import collect_file_metadata
#   from preservelib.manifest import PreserveManifest

__all__ = [
    "__version__",
]
