"""Output seams for ``dz relaunch``: verbosity and diagnostics (dazzle-loglib),
``--json``, colour, the TTY-gated prompt, and the verdict line.

Lift-ready (oracle S4-S6): no relaunch imports. The verdict and exit codes are
imported from dazzlecmd-lib (public exports of ``core.safedel``), so the
numbers stay one contract across tools.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List, Optional, TextIO

from dazzlecmd_lib.core.safedel import (  # noqa: F401  (re-exported for the CLI)
    EXIT_ERROR, EXIT_OK, EXIT_PARTIAL, EXIT_REFUSED, EXIT_USAGE, verdict_line,
)

TOOL = "relaunch"
CHANNELS = ("cli", "store", "claims", "anchor", "csb", "launch")
_log_file: Optional[TextIO] = None


def add_verbosity_flags(parser: argparse.ArgumentParser) -> None:
    """The one place relaunch's verbosity flags are declared (loglib's recipe)."""
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="more diagnostics (repeatable)")
    parser.add_argument("-q", "--quiet", action="count", default=0,
                        help="fewer messages (repeatable)")
    parser.add_argument("--log-file", metavar="PATH",
                        help="write diagnostics to this file instead of stderr")


def setup_output(verbose: int = 0, quiet: int = 0, log_file: Optional[str] = None):
    """Initialize loglib's output manager; route every channel to ``log_file`` if given."""
    global _log_file
    from dazzle_loglib import ChannelDef, init_output, resolve_verbosity
    defs = [ChannelDef(c, f"relaunch {c}") for c in CHANNELS]
    fds = None
    if log_file:
        _log_file = open(log_file, "a", encoding="utf-8")
        fds = {c: _log_file for c in CHANNELS}
    return init_output(verbosity=resolve_verbosity(verbose, quiet, env_var="DZ_RELAUNCH_VERBOSITY"),
                       channel_fds=fds, channel_defs=defs)


def close_output() -> None:
    global _log_file
    if _log_file is not None:
        _log_file.close()
        _log_file = None


def diag(channel: str, message: str, level: int = 2) -> None:
    """A diagnostic on one channel (shown at -v.. or written to --log-file)."""
    try:
        from dazzle_loglib import get_output
        get_output().emit(level, f"[{channel}] {message}", channel=channel)
    except Exception:
        pass


def emit_json(obj: Any, stream: TextIO = None) -> None:
    (stream or sys.stdout).write(json.dumps(obj, indent=2, default=str) + "\n")


def color(text: str, *codes: str, stream: TextIO = None) -> str:
    try:
        from dazzlecmd_lib.colors import colorize_for
        return colorize_for(stream or sys.stdout, text, *codes)
    except Exception:
        return text


def is_console() -> bool:
    try:
        from dazzlecmd_lib.core.safedel import stdin_is_interactive
        return bool(stdin_is_interactive()) and sys.stdout.isatty()
    except Exception:
        return sys.stdin.isatty() and sys.stdout.isatty()


def confirm(question: str, *, default: bool = False, ask=None) -> Optional[bool]:
    """Ask on stderr when a person is at the console; None when nobody can answer."""
    ask = ask or (lambda prompt: input(prompt))
    if not is_console():
        return None
    hint = "[Y/n]" if default else "[y/N]"
    sys.stderr.write(f"{question} {hint} ")
    sys.stderr.flush()
    try:
        answer = ask("").strip().lower()
    except EOFError:
        return None
    if not answer:
        return default
    return answer in ("y", "yes")


def finish(outcome: str, detail: str = "", code: int = EXIT_OK, *, json_mode: bool = False,
           payload: Optional[dict] = None) -> int:
    """Print the verdict as the last stdout line (or inside the JSON object)."""
    sys.stderr.flush()
    if json_mode:
        doc = dict(payload or {})
        doc.update({"verdict": outcome, "detail": detail, "exit_code": code})
        emit_json(doc)
    else:
        print(verdict_line(TOOL, outcome, detail))
    sys.stdout.flush()
    return code
