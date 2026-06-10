"""Post-shim regression: the DazzleEntity dict shim is DELETED (the 0.8.0 lib bump).

The Phase-1 ratchet this file once enforced has done its job -- the dict shim is
gone. Entities now expose typed attributes + ``extra_get``/``extra_set`` for the
untyped remainder (``source``, ``_vars``). These tests pin the breaking change:

1. the key ``dz`` operations still run end-to-end with the shim removed, and
2. legacy dict-style access on an entity now raises rather than silently working,
   while ``extra_get``/``extra_set`` provide the sanctioned untyped path.
"""
import contextlib
import io
import json
import sys

import pytest

from dazzlecmd_lib.entity import build_entity
from dazzlecmd.cli import main

# The key operations the migration committed to keeping shim-free -- they must
# still run end-to-end now that the shim backing them is gone.
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


@pytest.mark.parametrize("argv", KEY_OPS, ids=lambda a: " ".join(a[1:]))
def test_key_operations_run_without_the_shim(argv, tmp_path, monkeypatch):
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

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = main()
        except SystemExit as e:           # argparse --help exits 0
            rc = e.code if isinstance(e.code, int) else 0
    assert rc in (0, None), (
        f"`{' '.join(argv)}` failed (rc={rc}) with the shim removed:\n"
        f"{buf.getvalue()[-800:]}"
    )


class TestShimDeleted:
    def _entity(self):
        return build_entity(
            {"name": "t", "namespace": "core", "_fqcn": "core:t",
             "source": {"url": "https://example.com/y.git"}},
            entity_type="tool",
        )

    def test_dict_getitem_is_gone(self):
        with pytest.raises(TypeError):
            _ = self._entity()["name"]

    def test_dict_get_is_gone(self):
        # the shim's .get() / Mapping protocol is removed
        assert not hasattr(self._entity(), "get")

    def test_extra_get_reads_untyped_source(self):
        e = self._entity()
        assert e.extra_get("source") == {"url": "https://example.com/y.git"}
        assert e.extra_get("missing", "default") == "default"

    def test_extra_set_writes_untyped(self):
        e = self._entity()
        e.extra_set("source", {"url": "https://example.com/z.git"})
        assert e.extra_get("source")["url"] == "https://example.com/z.git"

    def test_typed_access_is_attribute(self):
        e = self._entity()
        assert e.name == "t"
        assert e.fqcn == "core:t"
        assert e.runtime == {}   # typed dict field, attribute access
