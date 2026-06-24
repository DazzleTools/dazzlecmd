"""Shared PowerShell execution utilities for wtf-windows tools.

Each tool's PowerShell scripts live in a tool-specific directory.
The caller supplies the path to its own ps1/ directory:

    from wtf_windows.lib.ps1.runner import run_ps1

    _PS1_DIR = Path(__file__).parent / "ps1"
    data = run_ps1("investigate_locks.ps1", _PS1_DIR, Hours=24)

Two calling conventions:

    run_ps1("script.ps1", ps1_dir, Param=value)  -> parsed JSON dict
    run_ps_command("one-liner", timeout)          -> raw stdout string

Short one-liners (elevation check, single WMI queries) use run_ps_command().
Anything longer belongs in a .ps1 file called via run_ps1().
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def run_ps1(
    script_name: str,
    ps1_dir: Path,
    timeout: int = 300,
    verbose: bool = False,
    **params: Any,
) -> Dict:
    """Run a .ps1 script and return parsed JSON output.

    Args:
        script_name: Name of the PowerShell script (e.g., "investigate_locks.ps1")
        ps1_dir: Directory containing the script (each tool supplies its own)
        timeout: Seconds before timing out (default: 300)
        verbose: Print command to stderr before running
        **params: Passed as -Name Value pairs to the script

    Returns a dict on success, or a dict with an "error" key on failure.
    """
    script = ps1_dir / script_name
    if not script.exists():
        raise FileNotFoundError(f"PowerShell script not found: {script}")

    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
    ]
    for name, value in params.items():
        cmd.append(f"-{name}")
        if isinstance(value, bool):
            # PowerShell switch parameters: just the flag, no value
            if not value:
                cmd.pop()  # remove the flag if False
        else:
            cmd.append(str(value))

    if verbose and verbose > 0:
        print(f"Running: {' '.join(cmd)}", file=sys.stderr)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"Script {script_name} timed out after {timeout}s"}
    except FileNotFoundError:
        return {"error": "PowerShell not found. This tool requires Windows with PowerShell."}

    if result.returncode != 0 and not result.stdout.strip():
        return {
            "error": f"PowerShell script failed (exit {result.returncode})",
            "stderr": result.stderr[:500] if result.stderr else None,
        }

    return _parse_json_output(result.stdout, script_name)


def run_ps_command(command: str, timeout: int = 10) -> Optional[str]:
    """Run a short inline PowerShell command and return raw stdout.

    Use this for one-liners only (elevation check, single queries).
    Anything longer than ~2 lines should be a .ps1 file.

    Returns stdout string on success, None on failure.
    """
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return None


def is_admin() -> bool:
    """Check if the current process has administrative privileges.

    Uses PowerShell to query the current Windows identity. Returns False
    on non-Windows platforms or if the check fails.
    """
    if sys.platform != "win32":
        return False
    result = run_ps_command(
        "([Security.Principal.WindowsPrincipal]"
        "[Security.Principal.WindowsIdentity]::GetCurrent())"
        ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"
    )
    return result is not None and result.strip().lower() == "true"


def _parse_json_output(stdout: str, source: str = "script") -> Dict:
    """Parse JSON from PowerShell output, handling noisy prefixed lines."""
    output = stdout.strip()
    if not output:
        return {"error": f"No output from {source}"}

    # Try the whole output as JSON first
    try:
        data = json.loads(output)
        if isinstance(data, list):
            return {"_list": data}
        return data
    except json.JSONDecodeError:
        pass

    # Scan backwards for a JSON object (handles warning lines before JSON)
    for line in reversed(output.split("\n")):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return data
                if isinstance(data, list):
                    return {"_list": data}
            except json.JSONDecodeError:
                continue

    return {
        "error": f"Could not parse JSON from {source}",
        "raw_output": output[:2000],
    }
