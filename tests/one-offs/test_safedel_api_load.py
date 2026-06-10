"""One-off: prove the safedel api.py load mechanism works.

Mimics the planned dazzlecmd_lib.mode._load_safedel_api loader:
- compute safedel_dir from a project_root + tools_dir
- put safedel_dir on sys.path (safedel uses bare imports)
- load api.py under a private cache name via spec_from_file_location
- verify the public surface + a real dry-run trash call

Run: python tests/one-offs/test_safedel_api_load.py
"""
import importlib.util
import os
import sys
import tempfile


def load_safedel_api(project_root, tools_dir):
    cache_key = "_dazzlecmd_safedel_api"
    if cache_key in sys.modules:
        return sys.modules[cache_key]
    safedel_dir = os.path.join(project_root, tools_dir, "core", "safedel")
    api_path = os.path.join(safedel_dir, "api.py")
    if not os.path.isfile(api_path):
        return None
    if safedel_dir not in sys.path:
        sys.path.insert(0, safedel_dir)
    try:
        spec = importlib.util.spec_from_file_location(cache_key, api_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[cache_key] = module
        spec.loader.exec_module(module)
        return module
    except Exception as exc:  # noqa: BLE001
        sys.modules.pop(cache_key, None)
        print(f"  LOAD FAILED: {type(exc).__name__}: {exc}")
        return None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(here))  # repo root
    print(f"project_root = {project_root}")

    api = load_safedel_api(project_root, "projects")
    if api is None:
        print("RESULT: FAIL -- api did not load")
        return 1
    print(f"  loaded: {api}")
    print(f"  __api_version__ = {getattr(api, '__api_version__', None)}")
    print(f"  __all__ = {getattr(api, '__all__', None)}")

    for name in ("TrashStore", "TrashEntry", "TrashResult", "StoreStats",
                 "stage_to_trash", "safe_delete", "classify"):
        ok = hasattr(api, name)
        print(f"  has {name}: {ok}")
        if not ok:
            print("RESULT: FAIL -- missing public symbol")
            return 1

    # Real dry-run trash on a temp file (no actual deletion).
    with tempfile.TemporaryDirectory() as td:
        victim = os.path.join(td, "victim.txt")
        with open(victim, "w") as f:
            f.write("hello")
        store = api.TrashStore()
        result = store.trash([victim], dry_run=True)
        print(f"  dry-run trash success = {result.success}")
        print(f"  dry-run folder_path   = {result.folder_path}")
        print(f"  victim still exists    = {os.path.exists(victim)} (must be True for dry-run)")
        if not os.path.exists(victim):
            print("RESULT: FAIL -- dry-run deleted the file!")
            return 1

    # Idempotent re-load returns the cached module.
    api2 = load_safedel_api(project_root, "projects")
    print(f"  cached re-load is same object: {api2 is api}")

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
