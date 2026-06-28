"""Vendored, in-development copies of code destined to become standalone DazzleLib
libraries. NOT third-party frozen deps -- we actively develop these here until they
are clean + feature-complete, then extract them to their own repos/PyPI dists.

Each subpackage carries a ``_VENDORED.md`` with its origin + extraction plan.

Current tenants:
- ``help_lib`` -> future ``dazzle_helplib`` (the CLI display/help CONTENT framework).
- ``log_lib`` -> future ``dazzle_loglib`` (output channels, verbosity, the hint registry).
"""
