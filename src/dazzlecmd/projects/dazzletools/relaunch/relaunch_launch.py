"""Hand-over for ``dz relaunch``: tell the tab where to go, and (S8) run members.

This slice holds the folder hand-over: ``write_cd_file`` (read by the ``dzr``
wrapper) and ``cd_line`` (printed when no wrapper is in use).
"""

from __future__ import annotations

import os
import sys
from typing import Optional

CD_FILE_ENV = "DZ_RELAUNCH_CD_FILE"
CD_FORMAT_ENV = "DZ_RELAUNCH_CD_FORMAT"


def _console_encoding() -> str:
    if sys.platform == "win32":
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
            if cp:
                return f"cp{cp}"
        except Exception:
            pass
        import locale
        return locale.getpreferredencoding(False) or "mbcs"
    return "utf-8"


def write_cd_file(folder: str, *, env=None) -> Optional[bool]:
    """Write ``folder`` for the wrapper. None: no wrapper in use; False: refused.

    Refuses (returns False, writes nothing) when the folder cannot be encoded
    exactly in the reader's encoding -- a lossy write can turn characters into
    ``?``, which ``cd`` treats as a wildcard and may match a different folder.
    """
    env = os.environ if env is None else env
    path = env.get(CD_FILE_ENV)
    if not path:
        return None
    fmt = env.get(CD_FORMAT_ENV, "cmd" if sys.platform == "win32" else "posix")
    encoding = _console_encoding() if fmt == "cmd" else "utf-8"
    try:
        data = (folder + ("\r\n" if fmt == "cmd" else "\n")).encode(encoding, errors="strict")
    except (UnicodeEncodeError, LookupError):
        return False
    with open(path, "wb") as f:
        f.write(data)
    return True


def cd_line(folder: str, shell: Optional[str] = None) -> str:
    """The line a person can paste to change to ``folder`` in their shell."""
    shell = shell or ("cmd" if sys.platform == "win32" else "bash")
    if shell == "cmd":
        return f'cd /d "{folder}"'
    if shell in ("powershell", "pwsh"):
        return "Set-Location -LiteralPath '" + folder.replace("'", "''") + "'"
    return "cd -- '" + folder.replace("'", "'\\''") + "'"
