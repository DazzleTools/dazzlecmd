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


def handover_from_argv(argv):
    """Split ``--cd-file=`` / ``--cd-format=`` (passed by ``dzr.cmd``) out of ``argv``.

    Returns (the remaining args, {env var: value}) -- the caller applies the mapping for one run.
    """
    rest, found = [], {}
    for tok in argv:
        if tok.startswith("--cd-file="):
            found[CD_FILE_ENV] = tok[len("--cd-file="):]
        elif tok.startswith("--cd-format="):
            found[CD_FORMAT_ENV] = tok[len("--cd-format="):]
        else:
            rest.append(tok)
    return rest, found


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
    try:
        with open(path, "wb") as f:
            f.write(data)
    except OSError:          # the wrapper's temp folder is gone (e.g. an inherited variable)
        return False
    return True


CMD_SPECIAL = set('&|<>^%!"\n\r')
DZ_ENV_VARS = ("DZ_APP_NAME", "DZ_COMMAND", "DZ_CANONICAL_FQCN", "DZ_INVOKED_FQCN")


class LaunchRefused(Exception):
    pass


def resolve_program(name: str) -> str:
    from dazzlecmd_lib.paths import which_with_pathext
    if os.path.isabs(name) and os.path.isfile(name):
        return name
    exe = which_with_pathext(name)
    if not exe:
        raise LaunchRefused(f"'{name}' was not found on PATH (PATHEXT searched). A shell builtin "
                            f"needs a shell member: dz relaunch <set> add --shell cmd \"...\"")
    return exe


def build_command(m, *, which=None):
    """(program-or-cmdline, display) for a member, refusing what cannot be passed safely."""
    k = m["kind"]
    if k == "command":
        exe = (which or resolve_program)(m["argv"][0])
        args = m["argv"][1:]
        if exe.lower().endswith((".cmd", ".bat")):
            for a in args:
                bad = CMD_SPECIAL & set(a)
                if bad:
                    raise LaunchRefused(f"argument {a!r} contains {''.join(sorted(bad))!r}, which a .cmd/.bat "
                                        f"program ({os.path.basename(exe)}) would receive changed -- store this "
                                        f"member as a shell member instead")
        return [exe] + args, " ".join([exe] + args)
    if k == "shell":
        d = m["shell"]
        if d == "cmd":
            if sys.platform != "win32":
                raise LaunchRefused("a cmd shell member can only run on Windows")
            line = f'cmd /d /s /c "{m["script"]}"'
            return line, line
        exe = (which or resolve_program)("bash" if d == "bash" else "pwsh")
        argv = [exe, "-c", m["script"]] if d == "bash" else [exe, "-NoProfile", "-Command", m["script"]]
        return argv, f"{d}: {m['script']}"
    if k == "claude":
        exe = (which or resolve_program)("csb")
        ref = m.get("session_id") or m["name_at_add"]     # by name until csb can see the session
        return [exe, "resume", ref], f"csb resume {ref}"
    raise LaunchRefused(f"a {k} member has nothing to run")


def child_env(base=None):
    env = dict(os.environ if base is None else base)
    for k in DZ_ENV_VARS + (CD_FILE_ENV, CD_FORMAT_ENV):
        env.pop(k, None)
    return env


def spawn(command, cwd: Optional[str], env) -> int:
    """Run the member as a child with the console intact; Ctrl-C belongs to it. (Seam.)"""
    import signal
    import subprocess
    old = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        proc = subprocess.Popen(command, cwd=cwd or None, env=env)
        return proc.wait()
    finally:
        signal.signal(signal.SIGINT, old)


def spawn_detached(command, cwd: Optional[str], env) -> None:
    """Start a detached member and do not wait: no tab, no console window. (Seam.)

    Windows: CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP -- measured (poc10/12): the
    DETACHED_PROCESS form opens a visible console when a .cmd runs a console program.
    """
    import subprocess
    if sys.platform == "win32":
        flags = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(command, cwd=cwd or None, env=env, creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(command, cwd=cwd or None, env=env, start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _launched_path(home=None):
    import relaunch_store as rs
    return os.path.join(rs.local_dir(home), "launched.json")


def launched_this_boot(set_name: str, member_id: int, boot: Optional[float], home=None) -> bool:
    """Was this detached member started since the current boot? (local/launched.json)"""
    import json
    import relaunch_claims as rc
    p = _launched_path(home)
    if boot is None or not os.path.isfile(p):
        return False
    try:
        at = json.load(open(p, encoding="utf-8")).get(set_name, {}).get(str(member_id))
    except ValueError:
        return False
    return at is not None and abs(at - boot) <= rc.BOOT_TOLERANCE_S


def record_launched(set_name: str, member_id: int, boot: Optional[float], home=None) -> None:
    import json
    from dazzle_filekit import atomic_write_json
    p = _launched_path(home)
    data = {}
    if os.path.isfile(p):
        try:
            data = json.load(open(p, encoding="utf-8"))
        except ValueError:
            data = {}
    data.setdefault(set_name, {})[str(member_id)] = boot
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write_json(p, data, indent=2, default=None)


def swap_launched(set_name: str, a: int, b: int, home=None) -> None:
    """``swap`` renumbered two members: their once-per-boot launch record moves with them."""
    import json
    from dazzle_filekit import atomic_write_json
    p = _launched_path(home)
    if not os.path.isfile(p):
        return
    try:
        data = json.load(open(p, encoding="utf-8"))
    except ValueError:
        return
    rec = data.get(set_name)
    if not rec:
        return
    va, vb = rec.pop(str(a), None), rec.pop(str(b), None)
    if va is not None:
        rec[str(b)] = va
    if vb is not None:
        rec[str(a)] = vb
    atomic_write_json(p, data, indent=2, default=None)


def open_asks(home=None, env=None) -> bool:
    """Whether -o asks first: env var > ~/.dz/relaunch/.env > local/config.json (default: ask)."""
    import json
    import relaunch_store as rs
    env = os.environ if env is None else env
    v = env.get("DZ_RELAUNCH_OPEN_ASKS")
    if v is not None:
        return v.strip().lower() not in ("0", "false", "no", "off")
    dotenv = os.path.join(home or rs.relaunch_home(), ".env")
    if os.path.isfile(dotenv):
        for line in open(dotenv, encoding="utf-8"):
            if line.strip().startswith("DZ_RELAUNCH_OPEN_ASKS="):
                return line.split("=", 1)[1].strip().lower() not in ("0", "false", "no", "off")
    cfg = os.path.join(rs.local_dir(home), "config.json")
    if os.path.isfile(cfg):
        try:
            return bool(json.load(open(cfg, encoding="utf-8")).get("open_asks", True))
        except ValueError:
            return True
    return True


def open_member(r, doc, folder, *, json_mode: bool = False) -> int:
    """claim -o: show what will run, check trust, ask (unless overridden), run, hand the folder over."""
    import relaunch_cli_io as io
    import relaunch_trust as trust
    m = r.member
    if m["kind"] == "folder":
        for line in ([f"this tab moves to {folder}"] if write_cd_file(folder) else [cd_line(folder)]):
            print(f"  {line}")
        return io.finish("CLAIMED", f"{r.set_name} {m['id']} folder", json_mode=json_mode)
    try:
        command, display = build_command(m)
    except LaunchRefused as e:
        print(f"relaunch: {e}", file=sys.stderr)
        return io.finish("REFUSED", str(e), io.EXIT_REFUSED, json_mode=json_mode)
    yes = bool(getattr(r, "yes", False))
    trusted = trust.is_trusted(doc, m)
    if m["kind"] == "claude":           # resume by UUID (rename-proof); show the name so a person can decide
        import relaunch_csb as csb
        name = csb.name_for_member(r.set_name, m)
        if name:
            display = f"{display}  ({name})"
    print(f"  will run: {display}" + (f"\n  in: {folder}" if folder else ""))
    if not trusted:
        print("  this command is not the one relaunch recorded (edited outside relaunch, or from another box)")
    if (not trusted) or (open_asks() and not yes):
        ok = io.confirm("run it?" + ("" if not trusted else "  (-y skips; DZ_RELAUNCH_OPEN_ASKS=0 stops asking)"))
        if not ok:
            # a "no" (n, Enter, Ctrl+C, closed input) gives the member back -- unless the tab already had it
            import relaunch_claims as rc
            label = m.get("label") or m["kind"]
            if getattr(r, "already", False):
                print(f"not run -- this tab still holds {r.set_name}:{m['id']} {label} (it had it before)")
            elif rc.unclaim(r, rc.current_tab()):
                print(f"not run -- released {r.set_name}:{m['id']} {label}")
            return io.finish("REFUSED", "not run", io.EXIT_REFUSED, json_mode=json_mode)
        if not trusted:
            trust.record(doc["name"], m)
    io.finish("STARTING", f"{r.set_name} {m['id']} {m.get('label') or m['kind']}")
    code = spawn(command, folder, child_env())
    print(f"relaunch: {m.get('label') or m['kind']} exited {code}", file=sys.stderr)
    if folder:
        write_cd_file(folder)
    return code


def cd_line(folder: str, shell: Optional[str] = None) -> str:
    """The line a person can paste to change to ``folder`` in their shell."""
    shell = shell or ("cmd" if sys.platform == "win32" else "bash")
    if shell == "cmd":
        return f'cd /d "{folder}"'
    if shell in ("powershell", "pwsh"):
        return "Set-Location -LiteralPath '" + folder.replace("'", "''") + "'"
    return "cd -- '" + folder.replace("'", "'\\''") + "'"
