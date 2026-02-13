"""Basic smoke tests for dazzlecmd."""

import subprocess
import sys


def test_import():
    """Verify the package imports without error."""
    import dazzlecmd
    assert hasattr(dazzlecmd, "__version__")
    assert hasattr(dazzlecmd, "__app_name__")
    assert dazzlecmd.__app_name__ == "dazzlecmd"


def test_version_format():
    """Verify version string is well-formed."""
    from dazzlecmd._version import MAJOR, MINOR, PATCH, get_base_version, get_pip_version
    assert isinstance(MAJOR, int)
    assert isinstance(MINOR, int)
    assert isinstance(PATCH, int)
    base = get_base_version()
    assert f"{MAJOR}.{MINOR}.{PATCH}" in base
    pip_ver = get_pip_version()
    assert f"{MAJOR}.{MINOR}.{PATCH}" in pip_ver


def test_cli_version():
    """Verify dz --version runs and outputs version info."""
    result = subprocess.run(
        [sys.executable, "-m", "dazzlecmd", "--version"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "dazzlecmd" in result.stdout.lower()


def test_cli_list():
    """Verify dz list runs and finds tools."""
    result = subprocess.run(
        [sys.executable, "-m", "dazzlecmd", "list"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "tool(s) found" in result.stdout


def test_cli_kit_list():
    """Verify dz kit list runs."""
    result = subprocess.run(
        [sys.executable, "-m", "dazzlecmd", "kit", "list"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "core" in result.stdout
    assert "dazzletools" in result.stdout


def test_loader_discover_kits():
    """Verify kit discovery finds both kits."""
    from dazzlecmd.cli import find_project_root
    from dazzlecmd.loader import discover_kits
    import os

    root = find_project_root()
    if root is None:
        return  # Skip if not in dev environment
    kits = discover_kits(os.path.join(root, "kits"))
    kit_names = [k["name"] for k in kits]
    assert "core" in kit_names
    assert "dazzletools" in kit_names


def test_loader_discover_projects():
    """Verify project discovery finds the initial tools."""
    from dazzlecmd.cli import find_project_root
    from dazzlecmd.loader import discover_kits, discover_projects, get_active_kits
    import os

    root = find_project_root()
    if root is None:
        return  # Skip if not in dev environment
    kits = discover_kits(os.path.join(root, "kits"))
    active = get_active_kits(kits)
    projects = discover_projects(os.path.join(root, "projects"), active)
    names = [p["name"] for p in projects]
    assert "rn" in names
    assert "dos2unix" in names
