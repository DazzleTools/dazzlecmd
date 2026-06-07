"""Pytest fixtures for the dazzlecmd-lib test suite."""

import warnings

import pytest


@pytest.fixture
def assert_no_shim_access():
    """Return a helper asserting a callable triggers no typed-field shim access.

    The Phase 1 migration ratchet (test-time, D2-safe -- see the Phase 1 DWP):
    flips ``DazzleEntity._warn_on_shim`` ON for the duration, runs the callable,
    and asserts no shim ``DeprecationWarning`` fired -- i.e. the operation
    reached every entity's TYPED fields via attribute access. Extra /
    nested-block dict access (``entity["runtime"]``, ``entity.get("tools")``)
    does NOT warn (no safe attribute form) and is allowed.
    """
    from dazzlecmd_lib.entity import DazzleEntity

    def _run(fn, *args, **kwargs):
        prev = DazzleEntity._warn_on_shim
        DazzleEntity._warn_on_shim = True
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = fn(*args, **kwargs)
            shim = [
                w for w in caught
                if issubclass(w.category, DeprecationWarning)
                and "DazzleEntity" in str(w.message)
            ]
            assert not shim, (
                "legacy typed-field shim access detected -- migrate to attribute "
                "access:\n"
                + "\n".join(f"  {w.filename}:{w.lineno}: {w.message}" for w in shim)
            )
            return result
        finally:
            DazzleEntity._warn_on_shim = prev

    return _run
