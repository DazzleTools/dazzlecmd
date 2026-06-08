"""Phase 1 ratchet enforcement (Stage 3).

Proof that the DazzleEntity call-site migration is complete for in-scope
production code: each key ``dz`` operation is driven through the real CLI with
``DazzleEntity._warn_on_shim`` flipped ON, and we assert NO production
typed-field shim ``DeprecationWarning`` fires -- i.e. every operation reaches
its entities' typed fields via attribute access, not the dict shim.

Scope (per the Phase 1 DWP, D2): the ratchet is typed-field-only (extra /
nested-block dict access like ``entity["runtime"]`` is legitimate and does NOT
warn), and only dazzlecmd's OWN suite flips it. wtf-windows / amdead run their
own suites with the ratchet OFF, so this enforcement never touches those
consumers. Test-file assertion-side shim reads are out of scope here -- they are
not on these production paths and migrate at shim deletion.

The end-to-end one-off ``tests/one-offs/ratchet_recon.py`` is the manual
diagnostic sibling of this gate.
"""
import contextlib
import io
import json
import sys
import warnings

import pytest

from dazzlecmd_lib.entity import DazzleEntity
from dazzlecmd.cli import main

# The key operations the migration committed to making shim-free: the read
# surfaces (list/info/tree/mode-status/kit), plus tool dispatch by short name
# AND by FQCN (the dispatch path held the last straggler, registry.resolve).
KEY_OPS = [
    ["dz", "list"],
    ["dz", "list", "--show", "all"],
    ["dz", "info", "core:find"],
    ["dz", "tree"],
    ["dz", "mode", "status"],
    ["dz", "kit", "list"],
    ["dz", "kit", "status"],
    ["dz", "find", "--help"],           # dispatch by short name
    ["dz", "core:safedel", "--help"],   # dispatch by FQCN
]


def _is_production(filename):
    """True if a warning originated in shipped source (not tests / one-offs)."""
    p = filename.replace("\\", "/")
    return (("/src/" in p) or ("dazzlecmd_lib" in p)) and "/tests/" not in p and "/one-offs/" not in p


@pytest.mark.parametrize("argv", KEY_OPS, ids=lambda a: " ".join(a[1:]))
def test_no_typed_field_shim_on_key_operations(argv, tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({
            "list_view": "default", "_schema_version": 1,
            "active_kits": ["wtf"], "disabled_kits": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("DAZZLECMD_CONFIG", str(cfg))
    monkeypatch.setattr(sys, "argv", list(argv))

    prev = DazzleEntity._warn_on_shim
    DazzleEntity._warn_on_shim = True
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                try:
                    main()
                except SystemExit:
                    pass  # argparse --help exits 0; that's fine
        shim = [
            w for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "DazzleEntity" in str(w.message)
            and _is_production(w.filename)
        ]
        assert not shim, (
            "production typed-field shim access on `%s` -- migrate to attribute access:\n%s"
            % (
                " ".join(argv),
                "\n".join(f"  {w.filename}:{w.lineno}: {w.message}" for w in shim),
            )
        )
    finally:
        DazzleEntity._warn_on_shim = prev
