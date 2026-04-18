"""Synthetic venv-exercise tool.

Imports the full requirements.txt dependency set and does a small amount
of real work with each. If any import fails, exit 1 with the missing
package name. Used by the v0.7.20 integration test to prove that:

    1. The venv was created successfully.
    2. Pip installed all declared dependencies into the venv.
    3. dz dispatched via the venv interpreter (NOT sys.executable).
    4. Imports succeed from the venv's site-packages.

The tool's output is machine-parsable so the test can assert it.
"""

from __future__ import annotations

import sys


def main():
    results: dict = {"interpreter": sys.executable, "imports": {}}

    # Attempt each import; record PASS/FAIL in results.
    imports_to_check = [
        ("numpy", "import numpy; assert numpy.array([1, 2, 3]).sum() == 6"),
        ("pandas", "import pandas; assert pandas.DataFrame({'a': [1, 2]}).shape == (2, 1)"),
        ("requests", "import requests; assert requests.__version__"),
        ("rich", "from rich.console import Console; Console()"),
        ("yaml", "import yaml; assert yaml.safe_load('k: v') == {'k': 'v'}"),
        ("click", "import click; assert click.__version__"),
        ("pydantic", "from pydantic import BaseModel; BaseModel.model_validate"),
    ]

    for name, exercise in imports_to_check:
        try:
            exec(exercise, {})
            results["imports"][name] = "PASS"
        except Exception as exc:
            results["imports"][name] = f"FAIL: {type(exc).__name__}: {exc}"

    # Emit a machine-parsable report on stdout.
    print(f"DAZZLECMD_VENV_EXERCISE_REPORT:INTERPRETER={results['interpreter']}")
    for name, status in results["imports"].items():
        print(f"DAZZLECMD_VENV_EXERCISE_REPORT:{name}={status}")

    # Exit nonzero if any import failed.
    if any(s != "PASS" for s in results["imports"].values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
