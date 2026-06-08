"""Stage 3 ratchet recon (read-only measurement; no commits).

Flips ``DazzleEntity._warn_on_shim`` ON and runs each key ``dz`` operation
through the real CLI, then reports PRODUCTION typed-field shim stragglers
(filtered out of test files / one-offs). The count decides whether Stage 3
ratchet enforcement is a quick clean-up or needs batching.
"""
import os
import sys
import io
import warnings
import tempfile
import contextlib

cfg = os.path.join(tempfile.gettempdir(), "ratchet_recon_cfg.json")
with open(cfg, "w", encoding="utf-8") as f:
    f.write('{"list_view":"default","_schema_version":1,"active_kits":["wtf"],"disabled_kits":[]}')
os.environ["DAZZLECMD_CONFIG"] = cfg

from dazzlecmd_lib.entity import DazzleEntity
from dazzlecmd.cli import main

OPS = [
    ["dz", "list"],
    ["dz", "list", "--show", "all"],
    ["dz", "info", "core:find"],
    ["dz", "tree"],
    ["dz", "mode", "status"],
    ["dz", "kit", "list"],
    ["dz", "kit", "status"],
    ["dz", "find", "--help"],          # dispatch/resolution path
    ["dz", "core:safedel", "--help"],  # FQCN dispatch path
]

DazzleEntity._warn_on_shim = True
all_shim = []
for argv in OPS:
    sys.argv = argv
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                main()
        except SystemExit:
            pass
        except Exception as e:  # noqa: BLE001
            print(f"[op {' '.join(argv)} raised: {type(e).__name__}: {e}]")
    for w in caught:
        if issubclass(w.category, DeprecationWarning) and "DazzleEntity" in str(w.message):
            all_shim.append((" ".join(argv), w.filename, w.lineno, str(w.message)))


def is_prod(fn):
    p = fn.replace("\\", "/")
    return (("/src/" in p) or ("dazzlecmd_lib" in p)) and "/tests/" not in p and "/one-offs/" not in p


prod = {}
test_sites = {}
for op, fn, lineno, msg in all_shim:
    key = f"{fn}:{lineno}"
    bucket = prod if is_prod(fn) else test_sites
    bucket.setdefault(key, set()).add(op)

print(f"\n=== PRODUCTION typed-field shim stragglers: {len(prod)} unique site(s) ===")
for key in sorted(prod):
    print(f"  {key}\n      via: {', '.join(sorted(prod[key]))}")

print(f"\n=== test-file shim reads (deferred to pre-shim-deletion cleanup): {len(test_sites)} site(s) ===")
for key in sorted(test_sites):
    print(f"  {key}")
