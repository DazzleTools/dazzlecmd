"""Allow running as: python -m dazzlecmd"""

import sys

from dazzlecmd.cli import main


def _maybe_hint_path_bootstrap():
    """One stderr line when dz is installed but off PATH (#103).

    ``python -m dazzlecmd`` is the door that always opens after a
    user-scheme pip install on Windows strands the shims off PATH --
    so this is the one place the user is guaranteed to see a pointer
    at the fix. Silent when healthy; never breaks the CLI; skipped
    when the user is already running ``setup`` (that flow explains
    itself).
    """
    if sys.argv[1:2] == ["setup"]:
        return
    try:
        from dazzlecmd_lib.self_setup import first_run_hint
        import os
        import dazzlecmd as _pkg
        location = os.path.dirname(getattr(_pkg, "__file__", "") or "")
        hint = first_run_hint(["dz", "dazzlecmd"],
                              package_name="dazzlecmd",
                              package_location=location or None)
        if hint:
            print(hint, file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    _maybe_hint_path_bootstrap()
    sys.exit(main())
