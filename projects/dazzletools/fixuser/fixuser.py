r"""
fixuser (fixusr) - diagnose & repair a broken Windows user profile.

WHY THIS EXISTS
---------------
When an admin runs `takeown` (or `icacls /reset`, or the Explorer "replace all
child permissions" checkbox) on a live user profile to copy files in/out, it
strips the profile's private ACL: the user loses explicit FullControl on its own
hive files (notably AppData\Local\Microsoft\Windows\UsrClass.dat). At the next
logon the User Profile Service can't load that hive read/write, logs Event 1542
("cannot load classes registry file"), gives up with Event 1511 (temporary
profile) and Event 1515 (it renames the good ProfileList key to "<SID>.bak").
The user then lives at C:\Users\TEMP and never sees their real profile.

fixuser detects that state and repairs BOTH halves, in the order that matters:
  1. ACLs   - re-grant the user FullControl on its profile (loop-safe, via
              safe-icacls, so the profile's self-referential junctions don't
              make icacls /T recurse forever).
  2. Registry - restore the ProfileList entry so the user logs into its real
              profile again (promote the ".bak" key / un-redirect / clear State).

Doing only the registry fix re-triggers the temp profile on the next logon,
because the ACLs would still be broken. fixuser does them together.

THE BROKEN SHAPES (use -v / -vv / -vvv to see which one you have)
----------------------------------------------------------------
  HEALTHY               active <SID> -> real profile, State=0. Nothing to do.
  BAK-ONLY              only <SID>.bak remains (Windows already cleaned up the
                        temp profile on logoff). Promote .bak back to active.
  TEMP-ACTIVE + BAK     active <SID> -> a temp profile (\Users\TEMP-like) AND a
                        <SID>.bak holds the real path. Park temp, promote .bak.
  TEMP-ACTIVE, NO BAK   single <SID> whose ProfileImagePath was rewritten to a
                        temp path, no .bak. Re-point it at the real profile.
  STATE-FLAGGED         active <SID> -> real profile but State != 0. Clear State.
  MISSING               no ProfileList entry for this SID. Cannot synthesize a
                        profile; create / log the account in normally.
(The ACL break is independent of the registry shape and is reported separately.)

USAGE
-----
  dz fixuser <username|SID>                 # diagnose only (read-only); default
  dz fixuser <username|SID> --repair        # apply the repair (needs elevation)
  dz fixuser <username|SID> --repair --harden   # also re-privatize the ACL
  dz fixuser localuser -vv                  # verbose diagnosis (raw values)

OPTIONS
-------
  --repair, --fix       Apply the repair. Without this, fixuser only reports.
  --acls-only           Repair only the ACLs (skip the registry).
  --registry-only       Repair only the ProfileList registry (skip the ACLs).
  --harden              Additionally re-protect inheritance and remove the
                        inherited Everyone/Users read leak (less reversible).
  --backup-dir <dir>    Where to write backups (default:
                        ~/.fixuser/backups/<SID>_<timestamp>/).
  --yes, -y             Skip the confirmation prompt when repairing.
  -v / -vv / -vvv       Increase verbosity (reasoning / raw values / debug).
  -h, --help            Show this help.

SAFETY
------
  * Default is read-only. --repair requires an elevated (admin) shell.
  * --repair refuses to run while the target's hive is loaded (an open session
    or `runas`); log the account off first.
  * Before changing anything, ProfileList is exported (reg export) and the
    critical ACLs recorded; the backup directory is printed.
  * The ACL grant is purely additive (revert with:
    dz sicacls "<profile>" /remove *<SID> /T /C).
"""

import ctypes
import os
import subprocess
import sys

PROFILELIST = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"
PROFILELIST_HKLM = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"

SID_SYSTEM = "S-1-5-18"
SID_ADMINS = "S-1-5-32-544"

# shape id -> (label, explanation)
SHAPES = {
    "healthy": (
        "HEALTHY",
        "The active ProfileList key points at the real profile and State=0; "
        "nothing to repair in the registry.",
    ),
    "bak_only": (
        "BAK-ONLY (temp profile already cleaned up)",
        "Only a '<SID>.bak' key remains, pointing at the real profile; the "
        "active '<SID>' key is gone because Windows removed the temporary "
        "profile on logoff. Fix: rename '<SID>.bak' back to '<SID>'.",
    ),
    "temp_active_with_bak": (
        "TEMP-ACTIVE + BAK (classic temporary profile)",
        "The active '<SID>' key points at a temporary profile (a \\Users\\TEMP "
        "style path) and a '<SID>.bak' key holds the real profile path. Fix: "
        "park the temp key, promote '<SID>.bak' to '<SID>', clear State.",
    ),
    "temp_active_no_bak": (
        "TEMP-ACTIVE, NO BAK (in-place rewrite)",
        "A single '<SID>' key whose ProfileImagePath was rewritten to a "
        "temporary path, with no '.bak'. Fix: reset ProfileImagePath to the "
        "real profile (which must exist on disk) and clear State.",
    ),
    "state_nonzero": (
        "STATE-FLAGGED",
        "The active key points at the real profile but State != 0, so Windows "
        "flagged it. Fix: clear State to 0.",
    ),
    "missing": (
        "MISSING",
        "There is no ProfileList entry for this SID at all. fixuser cannot "
        "synthesize a profile; create or log the account in normally first.",
    ),
}

CRITICAL_HIVES = (
    "NTUSER.DAT",
    os.path.join("AppData", "Local", "Microsoft", "Windows", "UsrClass.dat"),
)


# ============================================================================
# Options / argument parsing  (manual, like safe-icacls -- no argparse SystemExit)
# ============================================================================

class Options:
    def __init__(self):
        self.target = None
        self.repair = False
        self.acls_only = False
        self.registry_only = False
        self.harden = False
        self.yes = False
        self.backup_dir = None
        self.verbosity = 0
        self.help = False


def parse_args(argv):
    opts = Options()
    i = 0
    while i < len(argv):
        tok = argv[i]
        low = tok.lower()
        if low in ("-h", "--help"):
            opts.help = True
        elif low in ("--repair", "--fix"):
            opts.repair = True
        elif low == "--acls-only":
            opts.acls_only = True
        elif low == "--registry-only":
            opts.registry_only = True
        elif low == "--harden":
            opts.harden = True
        elif low in ("-y", "--yes"):
            opts.yes = True
        elif low == "--backup-dir":
            i += 1
            if i >= len(argv):
                raise SystemExit("error: --backup-dir requires a value")
            opts.backup_dir = argv[i]
        elif low in ("-v", "-vv", "-vvv", "-vvvv"):
            opts.verbosity += low.count("v")
        elif tok == "--verbose":
            opts.verbosity += 1
        elif tok.startswith("-") and tok != "-":
            raise SystemExit(f"error: unknown option '{tok}' (see -h)")
        else:
            if opts.target is None:
                opts.target = tok
            else:
                raise SystemExit(f"error: unexpected extra argument '{tok}'")
        i += 1
    return opts


# ============================================================================
# OS access (these are the only functions that touch the real machine; tests
# monkeypatch them so the analysis/plan logic can be exercised without admin)
# ============================================================================

def is_windows():
    return sys.platform == "win32"


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(cmd):
    """Run a command, return (rc, combined_text). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True)
    except OSError as exc:
        return 1, f"failed to launch {cmd[0]}: {exc}"
    enc = "mbcs" if sys.platform == "win32" else "utf-8"
    out = (p.stdout or b"").decode(enc, "replace") + (p.stderr or b"").decode(enc, "replace")
    return p.returncode, out


def name_to_sid(name):
    """Resolve an account name to a string SID via Win32, or None."""
    try:
        from ctypes import wintypes
        advapi32 = ctypes.windll.advapi32
        cb_sid = wintypes.DWORD(0)
        cch_dom = wintypes.DWORD(0)
        use = wintypes.DWORD(0)
        advapi32.LookupAccountNameW(None, name, None, ctypes.byref(cb_sid),
                                    None, ctypes.byref(cch_dom), ctypes.byref(use))
        if cb_sid.value == 0:
            return None
        sid_buf = ctypes.create_string_buffer(cb_sid.value)
        dom_buf = ctypes.create_unicode_buffer(cch_dom.value)
        if not advapi32.LookupAccountNameW(None, name, sid_buf, ctypes.byref(cb_sid),
                                           dom_buf, ctypes.byref(cch_dom), ctypes.byref(use)):
            return None
        str_ptr = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_buf, ctypes.byref(str_ptr)):
            return None
        s = str_ptr.value
        ctypes.windll.kernel32.LocalFree(str_ptr)
        return s
    except Exception:
        return None


def sid_to_name(sid):
    """Resolve a string SID to DOMAIN\\name via Win32, or None (best effort)."""
    try:
        from ctypes import wintypes
        advapi32 = ctypes.windll.advapi32
        psid = ctypes.c_void_p()
        if not advapi32.ConvertStringSidToSidW(sid, ctypes.byref(psid)):
            return None
        try:
            cch_name = wintypes.DWORD(0)
            cch_dom = wintypes.DWORD(0)
            use = wintypes.DWORD(0)
            advapi32.LookupAccountSidW(None, psid, None, ctypes.byref(cch_name),
                                       None, ctypes.byref(cch_dom), ctypes.byref(use))
            if cch_name.value == 0:
                return None
            name_buf = ctypes.create_unicode_buffer(cch_name.value)
            dom_buf = ctypes.create_unicode_buffer(cch_dom.value)
            if not advapi32.LookupAccountSidW(None, psid, name_buf, ctypes.byref(cch_name),
                                              dom_buf, ctypes.byref(cch_dom), ctypes.byref(use)):
                return None
            dom = dom_buf.value
            return f"{dom}\\{name_buf.value}" if dom else name_buf.value
        finally:
            ctypes.windll.kernel32.LocalFree(psid)
    except Exception:
        return None


def read_profile_list():
    """Return {subkey_name: {'path': str|None, 'state': int|None}} for ProfileList."""
    import winreg
    out = {}
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, PROFILELIST) as base:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(base, i)
            except OSError:
                break
            i += 1
            entry = {"path": None, "state": None}
            try:
                with winreg.OpenKey(base, sub) as k:
                    try:
                        entry["path"] = winreg.QueryValueEx(k, "ProfileImagePath")[0]
                    except OSError:
                        pass
                    try:
                        entry["state"] = winreg.QueryValueEx(k, "State")[0]
                    except OSError:
                        pass
            except OSError:
                pass
            out[sub] = entry
    return out


def is_hive_loaded(sid):
    """True if HKEY_USERS\\<SID> is loaded (an active session or runas)."""
    import winreg
    try:
        winreg.OpenKey(winreg.HKEY_USERS, sid).Close()
        return True
    except OSError:
        return False


def acl_user_has_full(path, names, sid):
    """Best-effort: does `path` grant FullControl to the user? True/False/None."""
    if not os.path.exists(path):
        return None
    rc, out = _run(["icacls", path])
    if rc != 0:
        return None
    for raw in out.splitlines():
        line = raw.rstrip()
        if not line or "Successfully processed" in line or "Failed processing" in line:
            continue
        s = line[len(path):] if line.startswith(path) else line
        s = s.strip()
        if ":(" not in s:
            continue
        principal = s[:s.index(":(")].strip()
        perms = s[s.index(":("):]
        if _principal_matches(principal, names, sid) and "(F)" in perms:
            return True
    return False


def _principal_matches(principal, names, sid):
    p = principal.lower()
    if sid and (p == sid.lower() or p == "*" + sid.lower()):
        return True
    for n in names:
        if not n:
            continue
        n = n.lower()
        if p == n or p.endswith("\\" + n) or p == "*" + n:
            return True
    return False


# -- mutation helpers (only called in --repair) ------------------------------

def backup_profile_list(dest_reg):
    rc, _ = _run(["reg", "export", PROFILELIST_HKLM, dest_reg, "/y"])
    return rc == 0


def snapshot_acls(nodes, dest_txt):
    """Write human-readable icacls output of the given nodes (no /T -> no loop)."""
    chunks = []
    for n in nodes:
        if os.path.exists(n):
            _, out = _run(["icacls", n])
            chunks.append(f"=== {n} ===\n{out}")
    try:
        with open(dest_txt, "w", encoding="utf-8") as fh:
            fh.write("\n".join(chunks))
        return True
    except OSError:
        return False


def rename_profile_key(old_leaf, new_leaf):
    """Rename a ProfileList subkey (winreg has no rename: copy values+subkeys, delete)."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, PROFILELIST, 0, winreg.KEY_ALL_ACCESS) as base:
        with winreg.OpenKey(base, old_leaf, 0, winreg.KEY_ALL_ACCESS) as src:
            dst = winreg.CreateKey(base, new_leaf)
            try:
                _copy_key(src, dst)
            finally:
                dst.Close()
        _delete_key_tree(base, old_leaf)


def _copy_key(src, dst):
    import winreg
    i = 0
    while True:
        try:
            name, data, typ = winreg.EnumValue(src, i)
        except OSError:
            break
        i += 1
        winreg.SetValueEx(dst, name, 0, typ, data)
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(src, i)
        except OSError:
            break
        i += 1
        with winreg.OpenKey(src, sub, 0, winreg.KEY_ALL_ACCESS) as s2:
            d2 = winreg.CreateKey(dst, sub)
            try:
                _copy_key(s2, d2)
            finally:
                d2.Close()


def _delete_key_tree(base, leaf):
    import winreg
    with winreg.OpenKey(base, leaf, 0, winreg.KEY_ALL_ACCESS) as k:
        while True:
            try:
                sub = winreg.EnumKey(k, 0)
            except OSError:
                break
            _delete_key_tree(k, sub)
    winreg.DeleteKey(base, leaf)


def set_profile_dword(leaf, name, value):
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, PROFILELIST + "\\" + leaf, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)


def set_profile_path(leaf, path):
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, PROFILELIST + "\\" + leaf, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "ProfileImagePath", 0, winreg.REG_EXPAND_SZ, path)


def loop_safe_grant(profile_path, grants, verbose=False):
    """Apply additive grants to the whole profile tree, loop-safe, via safe-icacls.

    `grants` is a list of icacls grant specs like '*S-1-...:(OI)(CI)F'.
    Returns 0 on success.
    """
    si = _import_safe_icacls()
    if si is None:
        return _grant_via_dz(profile_path, grants, verbose)
    icacls = si.find_icacls()
    if not icacls:
        return 1
    wa = si.WrapperArgs()
    wa.verbose = verbose
    ops = ["/grant"] + grants + ["/C"]
    stats = si.safe_walk(icacls, profile_path, ops, wa)
    return 1 if stats.errors else 0


def loop_safe_reprotect(profile_path, grants, verbose=False):
    """--harden: per-object remove inheritance + reassert explicit grants (loop-safe)."""
    si = _import_safe_icacls()
    if si is None:
        return 1
    icacls = si.find_icacls()
    if not icacls:
        return 1
    wa = si.WrapperArgs()
    wa.verbose = verbose
    # /inheritance:r drops inherited ACEs (the Everyone/Users leak); the explicit
    # grants keep the owner+admins+system able to access. icacls computes the final
    # DACL from both, so order within one call is safe.
    ops = ["/inheritance:r", "/grant"] + grants + ["/C"]
    stats = si.safe_walk(icacls, profile_path, ops, wa)
    return 1 if stats.errors else 0


def _import_safe_icacls():
    try:
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        sib = os.path.normpath(os.path.join(here, "..", "safe-icacls", "safe_icacls.py"))
        spec = importlib.util.spec_from_file_location("safe_icacls", sib)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _grant_via_dz(profile_path, grants, verbose):
    import shutil
    dz = shutil.which("dz")
    if not dz:
        print("error: could not locate safe-icacls (neither the sibling module "
              "nor 'dz' on PATH).", file=sys.stderr)
        return 1
    cmd = [dz, "safe-icacls", profile_path, "/grant"] + grants + ["/T", "/C"]
    if verbose:
        cmd.append("--safe-verbose")
    return subprocess.run(cmd).returncode


# ============================================================================
# Pure analysis & planning (no OS access -- fully unit-testable)
# ============================================================================

def is_temp_path(path):
    if not path:
        return False
    base = os.path.basename(path.rstrip("\\/"))
    return base.upper() == "TEMP" or path.upper().rstrip("\\/").endswith("\\USERS\\TEMP")


def classify_shape(sid, profile_list):
    active = profile_list.get(sid)
    bak = profile_list.get(sid + ".bak")
    if active is None and bak is None:
        return "missing"
    if active is None and bak is not None:
        return "bak_only"
    if active is not None and bak is not None:
        # Active key plus a backup key: promote the backup either way.
        return "temp_active_with_bak"
    # active only
    if is_temp_path(active.get("path")):
        return "temp_active_no_bak"
    state = active.get("state")
    if state not in (0, None):
        return "state_nonzero"
    return "healthy"


def determine_real_path(sid, name, profile_list, exists=os.path.isdir):
    """Return (path, source_explanation) for the user's REAL profile, or (None, why)."""
    bak = profile_list.get(sid + ".bak")
    active = profile_list.get(sid)
    if bak and bak.get("path") and not is_temp_path(bak["path"]):
        return bak["path"], "from the <SID>.bak key (Windows' backup of the good path)"
    if active and active.get("path") and not is_temp_path(active["path"]):
        return active["path"], "from the active <SID> key"
    if name:
        short = name.split("\\")[-1]
        drive = os.environ.get("SystemDrive", "C:")
        cand = f"{drive}\\Users\\{short}"
        if exists(cand):
            return cand, f"derived as {cand} (it exists on disk)"
        return None, f"could not derive: {cand} does not exist"
    return None, "no .bak path and account name unknown"


class Diagnosis:
    def __init__(self):
        self.target = None
        self.sid = None
        self.name = None
        self.shape = None
        self.profile_list = {}
        self.real_path = None
        self.real_path_source = None
        self.acl_results = {}        # node -> True/False/None
        self.acl_broken = None       # True/False
        self.hive_loaded = None
        self.is_admin = None

    @property
    def registry_broken(self):
        return self.shape not in ("healthy", "missing")

    @property
    def healthy(self):
        # If ACLs weren't checked (registry-only / unresolved), don't claim an
        # ACL problem -- only a confirmed False counts as broken.
        return self.shape == "healthy" and self.acl_broken is not True


def analyze(target, sid, name, profile_list, acl_results, hive_loaded, admin):
    d = Diagnosis()
    d.target = target
    d.sid = sid
    d.name = name
    d.profile_list = profile_list
    d.hive_loaded = hive_loaded
    d.is_admin = admin
    if sid:
        d.shape = classify_shape(sid, profile_list)
        d.real_path, d.real_path_source = determine_real_path(sid, name, profile_list)
    else:
        d.shape = "missing"
    d.acl_results = acl_results
    if acl_results:
        d.acl_broken = not all(v is True for v in acl_results.values())
    else:
        d.acl_broken = None
    return d


def build_plan(diag, opts):
    """Return a list of action dicts describing exactly what --repair would do."""
    plan = []
    grants = [f"*{diag.sid}:(OI)(CI)F"]
    harden_grants = [
        f"*{diag.sid}:(OI)(CI)F",
        f"*{SID_SYSTEM}:(OI)(CI)F",
        f"*{SID_ADMINS}:(OI)(CI)F",
    ]

    do_acls = not opts.registry_only
    do_reg = not opts.acls_only

    if do_acls and diag.real_path and diag.acl_broken is not False:
        plan.append({"op": "grant_acl", "path": diag.real_path, "grants": grants,
                     "desc": f"grant the user FullControl on {diag.real_path} (loop-safe, additive)"})
    if do_acls and opts.harden and diag.real_path:
        plan.append({"op": "harden_acl", "path": diag.real_path, "grants": harden_grants,
                     "desc": f"re-protect inheritance on {diag.real_path} and drop the Everyone/Users leak"})

    if do_reg:
        sid = diag.sid
        if diag.shape == "temp_active_with_bak":
            plan.append({"op": "rename_key", "old": sid, "new": sid + ".temp",
                         "desc": "park the temp profile key (<SID> -> <SID>.temp)"})
            plan.append({"op": "rename_key", "old": sid + ".bak", "new": sid,
                         "desc": "promote the backup key (<SID>.bak -> <SID>)"})
            plan.append({"op": "set_dword", "key": sid, "name": "State", "value": 0,
                         "desc": "set State=0"})
            plan.append({"op": "set_dword", "key": sid, "name": "RefCount", "value": 0,
                         "desc": "set RefCount=0"})
        elif diag.shape == "bak_only":
            plan.append({"op": "rename_key", "old": sid + ".bak", "new": sid,
                         "desc": "promote the backup key (<SID>.bak -> <SID>)"})
            plan.append({"op": "set_dword", "key": sid, "name": "State", "value": 0,
                         "desc": "set State=0"})
            plan.append({"op": "set_dword", "key": sid, "name": "RefCount", "value": 0,
                         "desc": "set RefCount=0"})
        elif diag.shape == "temp_active_no_bak":
            if diag.real_path:
                plan.append({"op": "set_path", "key": sid, "path": diag.real_path,
                             "desc": f"re-point ProfileImagePath to {diag.real_path}"})
                plan.append({"op": "set_dword", "key": sid, "name": "State", "value": 0,
                             "desc": "set State=0"})
            else:
                plan.append({"op": "manual", "desc":
                             "cannot auto-fix: the real profile path is unknown/missing "
                             f"({diag.real_path_source}); restore it manually."})
        elif diag.shape == "state_nonzero":
            plan.append({"op": "set_dword", "key": sid, "name": "State", "value": 0,
                         "desc": "set State=0"})
        elif diag.shape == "missing":
            plan.append({"op": "manual", "desc":
                         "no ProfileList entry exists; create/log the account in normally."})
    return plan


# ============================================================================
# Rendering
# ============================================================================

def _vlines(diag, plan, opts):
    """Build the report as a list of (min_verbosity, text) lines."""
    v = []
    if diag.sid is None:
        v.append((0, f"fixuser: could not resolve '{diag.target}' to a Windows "
                     "account. Pass an exact local username or a SID (S-1-5-...)."))
        return v
    label, expl = SHAPES[diag.shape]
    target = diag.name or diag.target
    v.append((0, f"fixuser: {target}"))
    v.append((0, f"  SID            : {diag.sid or '(unresolved)'}"))
    v.append((0, f"  real profile   : {diag.real_path or '(unknown)'}"))
    v.append((1, f"                   ({diag.real_path_source})"))
    v.append((0, f"  registry shape : {label}"))
    v.append((1, f"                   {expl}"))
    # raw ProfileList values
    for leaf in (diag.sid, (diag.sid or "") + ".bak", (diag.sid or "") + ".temp"):
        if leaf in diag.profile_list:
            e = diag.profile_list[leaf]
            v.append((2, f"    [{leaf}] path={e.get('path')!r} state={e.get('state')!r}"))
    # ACL status
    if diag.acl_broken is None:
        v.append((0, "  acl status     : (not checked)"))
    elif diag.acl_broken:
        v.append((0, "  acl status     : BROKEN (user is missing FullControl on a hive)"))
    else:
        v.append((0, "  acl status     : ok (user has FullControl)"))
    for node, res in diag.acl_results.items():
        tag = {True: "ok", False: "MISSING FullControl", None: "unknown"}[res]
        v.append((2, f"    {tag:>20} : {node}"))
    v.append((1, f"  hive loaded    : {diag.hive_loaded}"))
    v.append((1, f"  elevated       : {diag.is_admin}"))

    v.append((0, ""))
    if diag.healthy:
        v.append((0, "  VERDICT: healthy -- nothing to do."))
    else:
        problems = []
        if diag.registry_broken:
            problems.append("registry (temp/backup profile state)")
        if diag.acl_broken:
            problems.append("ACLs (missing FullControl)")
        v.append((0, "  VERDICT: needs repair -- " + ", ".join(problems) + "."))
        v.append((0, "  PLAN" + (" (run with --repair to apply)" if not opts.repair else "") + ":"))
        if not plan:
            v.append((0, "    (no automatic actions available)"))
        for a in plan:
            mark = "  ! " if a["op"] == "manual" else "  - "
            v.append((0, "  " + mark + a["desc"]))
    return v


def render(diag, plan, opts):
    for min_v, text in _vlines(diag, plan, opts):
        if opts.verbosity >= min_v:
            print(text)


# ============================================================================
# Repair execution
# ============================================================================

def _timestamp():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d__%H-%M-%S")


def default_backup_root():
    # Matches the DazzleTools precedent set by `safedel` (~/.safedel/): a
    # per-tool, home-based dir owned by the admin who ran the repair, with
    # timestamped subfolders. Override with --backup-dir.
    return os.path.join(os.path.expanduser("~"), ".fixuser", "backups")


def do_repair(diag, plan, opts):
    if not diag.is_admin:
        print("error: --repair requires an elevated (admin) shell.", file=sys.stderr)
        return 1
    if diag.hive_loaded:
        print(f"error: {diag.name or diag.sid}'s hive is currently loaded (an open "
              "session or `runas`). Log the account off / close all its shells, then "
              "retry. fixuser will not repair a profile that is in use.", file=sys.stderr)
        return 1
    if not plan or all(a["op"] == "manual" for a in plan):
        print("Nothing to repair automatically.")
        for a in plan:
            if a["op"] == "manual":
                print("  ! " + a["desc"])
        return 0 if diag.healthy else 2

    # --- backups -----------------------------------------------------------
    root = opts.backup_dir or default_backup_root()
    dest = os.path.join(root, f"{diag.sid}_{_timestamp()}")
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as exc:
        print(f"error: cannot create backup dir {dest}: {exc}", file=sys.stderr)
        return 1
    reg_ok = backup_profile_list(os.path.join(dest, "ProfileList.reg"))
    nodes = [diag.real_path] if diag.real_path else []
    if diag.real_path:
        nodes += [os.path.join(diag.real_path, h) for h in CRITICAL_HIVES]
    snapshot_acls(nodes, os.path.join(dest, "acls-before.txt"))
    print(f"backup: {dest}  (ProfileList.reg={'ok' if reg_ok else 'FAILED'}, acls-before.txt)")
    print(f"        revert ACL grant if needed:  dz sicacls \"{diag.real_path}\" /remove *{diag.sid} /T /C")

    # --- confirm -----------------------------------------------------------
    if not opts.yes:
        try:
            ans = input(f"Apply {len(plan)} action(s) to repair '{diag.name or diag.sid}'? [y/N] ")
        except EOFError:
            ans = ""
        if ans.strip().lower() not in ("y", "yes"):
            print("aborted.")
            return 0

    # --- execute -----------------------------------------------------------
    verbose = opts.verbosity >= 3
    errors = 0
    for a in plan:
        op = a["op"]
        print("  -> " + a["desc"])
        try:
            if op == "grant_acl":
                if loop_safe_grant(a["path"], a["grants"], verbose):
                    errors += 1
            elif op == "harden_acl":
                if loop_safe_reprotect(a["path"], a["grants"], verbose):
                    errors += 1
            elif op == "rename_key":
                rename_profile_key(a["old"], a["new"])
            elif op == "set_dword":
                set_profile_dword(a["key"], a["name"], a["value"])
            elif op == "set_path":
                set_profile_path(a["key"], a["path"])
            elif op == "manual":
                print("     (manual step -- not automated)")
        except Exception as exc:
            errors += 1
            print(f"     ! failed: {exc}", file=sys.stderr)

    if errors:
        print(f"repair finished with {errors} error(s); see above. Backup at {dest}.",
              file=sys.stderr)
        return 1
    print("repair complete. Log the account off and back on (or reboot); then verify "
          "%USERPROFILE% points at the real profile and the original symptom is gone.")
    return 0


# ============================================================================
# Entry point
# ============================================================================

def gather_diagnosis(opts):
    """Touch the real OS to build a Diagnosis for opts.target."""
    target = opts.target
    if target and target.upper().startswith("S-1-"):
        sid = target
        name = sid_to_name(sid)
    else:
        sid = name_to_sid(target)
        name = target
    profile_list = read_profile_list()
    real_path, _ = determine_real_path(sid, name, profile_list) if sid else (None, "")
    acl_results = {}
    if real_path and not opts.registry_only:
        names = {name, name.split("\\")[-1] if name else None}
        for rel in ("",) + CRITICAL_HIVES:
            node = os.path.join(real_path, rel) if rel else real_path
            acl_results[node] = acl_user_has_full(node, names, sid)
    hive_loaded = is_hive_loaded(sid) if sid else False
    return analyze(target, sid, name, profile_list, acl_results, hive_loaded, is_admin())


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        opts = parse_args(argv)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if opts.help or not opts.target:
        print(__doc__.strip())
        return 0

    if not is_windows():
        print("error: fixuser is Windows-only (it repairs the Windows user-profile "
              "registry and NTFS ACLs).", file=sys.stderr)
        return 1

    diag = gather_diagnosis(opts)
    plan = build_plan(diag, opts) if diag.sid else []
    render(diag, plan, opts)

    if not opts.repair:
        if diag.target and diag.sid is None:
            return 2
        return 0 if diag.healthy else 2

    return do_repair(diag, plan, opts)


if __name__ == "__main__":
    sys.exit(main())
