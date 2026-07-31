"""dz dazzle-update -- ecosystem-wide update/status scanner.

Reports what needs fetching, pushing, or reinstalling across every
namespace we own, by joining four independent views: GitHub namespace
listings, editable installs, the filesystem, and PyPI.

Read-only by default. --fix applies exactly two provably-safe
operations and refuses anything requiring judgment.

    dz dazzle-update                 The report
    dz dazzle-update --published     Add the PyPI axis (network)
    dz dazzle-update --json          Machine-readable, for cross-box diffs
    dz dazzle-update --fix           ff-only pulls + editable reinstalls
    dz dazzle-update --scope DazzleLib
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

# projects/dazzletools/ on sys.path so _repo_common (sibling dir) imports.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

from _repo_common.discovery import (  # noqa: E402
    editable_installs,
    find_git_repos,
    list_org_repos,
    normalize_dist,
    pypi_owned_by,
    pypi_project,
    read_declared_dist_name,
)
from _repo_common.gh_identity import (  # noqa: E402
    IdentityResolver,
    gh_status,
    load_cache,
    parse_slug,
    save_cache,
)
from _repo_common.repo_state import (  # noqa: E402
    detect_remotes,
    fetch_remote,
    get_ahead_behind,
    get_branch,
    get_last_commit_epoch,
    get_status_counts,
    get_upstream,
    safe_print,
    set_verbosity,
)
from config import (  # noqa: E402
    load as load_config,
    user_config_dir,
    write_template,
)
import scancache  # noqa: E402
from ecosystem import (  # noqa: E402
    DEFAULT_EXCLUDES,
    FINDING_ALIASES,
    FINDING_LABELS,
    FINDING_ORDER,
    EcosystemConfig,
    classify,
    SORT_MODES,
    apply_order,
    clean_count,
    join,
    norm,
    resolve_kinds,
)

DEFAULT_ROOT = r"C:\code" if os.name == "nt" else os.path.expanduser("~/code")

# -- colour --
#
# Severity, not decoration. The mapping encodes how bad a state is and
# what it would cost you:
#
#   bold red    work exists ONLY here -- losing this box loses the work
#   red         the remote has commits you do not
#   yellow      local edits, recoverable and in your control
#   magenta     structural/identity drift (a URL that no longer names it)
#   grey        informational; nothing is at risk
#
# ANSI only (7-bit ASCII), so no codepage hazard on cmd.exe or
# PowerShell. Disabled automatically when piped, and honours NO_COLOR.

_ANSI = {
    "reset": "\033[0m", "bold": "\033[1m",
    "red": "\033[31m", "bright_red": "\033[91m",
    "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m",
    "grey": "\033[90m",
}

FINDING_COLOURS = {
    "unpushed": "bright_red",
    "no-upstream": "bright_red",
    "source-missing": "red",
    "stale-install-metadata": "yellow",
    "install-behind-published": "yellow",
    "stale-remote-url": "magenta",
    "behind-upstream": "red",
    "not-cloned": "grey",
    "dirty": "yellow",
    "vendored-drift": "magenta",
    "excluded-by-policy": "grey",
}


class Palette:
    """Colour codes, or empty strings when colour is off."""

    def __init__(self, enabled):
        self.enabled = enabled

    def __call__(self, name, text):
        if not self.enabled:
            return text
        code = _ANSI.get(name)
        return f"{code}{text}{_ANSI['reset']}" if code else text

    def bold(self, text):
        return f"{_ANSI['bold']}{text}{_ANSI['reset']}" if self.enabled else text


def _enable_windows_ansi():
    """Turn on VT processing so ANSI works in cmd.exe / PowerShell."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # -11 = STD_OUTPUT_HANDLE; 0x4 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x4))
    except Exception:  # noqa: BLE001 - colour is never worth an exception
        return False


def make_palette(choice):
    """choice: 'auto' | 'always' | 'never'."""
    if choice == "never" or os.environ.get("NO_COLOR"):
        return Palette(False)
    if choice == "always":
        _enable_windows_ansi()
        return Palette(True)
    if not sys.stdout.isatty():
        return Palette(False)
    return Palette(_enable_windows_ansi())
_VERSION_RE = re.compile(
    r'^\s*(?:__version__|version)\s*=\s*["\']([^"\']+)', re.MULTILINE)


def _cache_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    return os.path.join(base, "dazzlecmd", "dazzle-update-identity.json")


def derive_namespaces(runner=None):
    """Namespaces from `gh api user/orgs` -- derived, never hardcoded.

    A hardcoded list is a manifest with the same rot: DazzleML was
    actively in use and absent from every list written by hand.
    """
    from _repo_common.gh_identity import _run_gh
    run = runner or _run_gh
    rc, out, err = run(["api", "user/orgs", "--jq", ".[].login"])
    if rc != 0:
        return [], f"could not derive namespaces: {(err or '').strip().splitlines()[:1]}"
    names = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return names, None


def gh_login(runner=None):
    from _repo_common.gh_identity import _run_gh
    run = runner or _run_gh
    rc, out, _ = run(["api", "user", "--jq", ".login"])
    return out.strip() if rc == 0 and out.strip() else None


def read_source_version(path):
    """Best-effort version from a checkout's _version.py or pyproject."""
    for rel in ("_version.py", "pyproject.toml"):
        for cand in Path(path).rglob(rel):
            # Only look near the top; deep vendored copies are not ours.
            if len(cand.relative_to(path).parts) > 3:
                continue
            try:
                text = cand.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = _VERSION_RE.search(text)
            if m:
                return m.group(1)
    return None


class Progress:
    """Single-line progress on stderr, so stdout stays pipeable.

    A scan touches ~150 repos and fetches most of them; without feedback
    the tool looks hung for over a minute. Writes to stderr specifically
    so `--json` output remains clean for cross-box diffing.
    """

    def __init__(self, enabled=True, verbose=0):
        self.enabled = enabled and sys.stderr.isatty()
        self.verbose = verbose
        self.width = 0

    def update(self, phase, current, total=None, name=""):
        if not (self.enabled or self.verbose):
            return
        count = f"{current}/{total}" if total else str(current)
        line = f"  {phase} {count}  {name}"
        if self.verbose:
            print(line, file=sys.stderr)
            return
        line = line[:100]
        pad = " " * max(0, self.width - len(line))
        self.width = len(line)
        print("\r" + line + pad, end="", file=sys.stderr, flush=True)

    def done(self):
        if self.enabled and not self.verbose:
            print("\r" + " " * self.width + "\r", end="", file=sys.stderr,
                  flush=True)
        self.width = 0


def fetch_all(paths, progress, workers=8, timeout=60):
    """Refresh remote-tracking refs concurrently.

    Sequential fetching of ~150 repos is minutes of wall-clock; these are
    network-bound and independent, so they parallelize cleanly. Failures
    are collected, never raised: one unreachable remote must not abort
    the sweep.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    failures = []
    total = len(paths)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_remote, p, timeout=timeout): p
                   for p in paths}
        for fut in as_completed(futures):
            path = futures[fut]
            done += 1
            progress.update("fetching", done, total, os.path.basename(path))
            try:
                ok, detail = fut.result()
            except Exception as exc:  # noqa: BLE001 - never abort the sweep
                ok, detail = False, str(exc)
            if not ok:
                failures.append((path, detail))
    return failures


def collect_local(roots, resolver, config, verbose=0, progress=None,
                  do_fetch=True, fetch_timeout=60):
    """Filesystem + git + identity for every repo root under `roots`."""
    out = []
    progress = progress or Progress(enabled=False)

    discovered = []
    for root in roots:
        progress.update("scanning", 0, None, str(root))
        discovered.extend(find_git_repos(root, max_depth=3))

    fetch_failures = []
    if do_fetch:
        fetchable = [p for p in discovered
                     if detect_remotes(p) and not config.is_excluded(p)]
        fetch_failures = fetch_all(fetchable, progress, timeout=fetch_timeout)

    total = len(discovered)
    for idx, path in enumerate(discovered, 1):
        progress.update("reading", idx, total, os.path.basename(path))
        out.append(_read_one(path, resolver))
    progress.done()
    return out, fetch_failures


def _read_one(path, resolver):
    """All axes for a single repo path."""
    remotes = detect_remotes(path)
    origin = next((r for r in remotes if r["name"] == "origin"), None)
    slug = None
    if origin:
        slug = origin.get("slug") or parse_slug(origin.get("fetch_url"))
    info = resolver.resolve(slug) if slug else None
    upstream = get_upstream(path)
    behind, ahead = get_ahead_behind(path, upstream=upstream)
    counts = get_status_counts(path)
    return {
        "path": path,
        "slug": slug,
        "full_name": (info or {}).get("full_name") or slug,
        "redirected": bool((info or {}).get("redirected")),
        "git": {
            "branch": get_branch(path),
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
            "dirty_count": counts["dirty_count"],
            "untracked_count": counts["untracked_count"],
        },
        "error": (info or {}).get("error"),
        "last_activity": get_last_commit_epoch(path),
    }


# Directory names that describe a repo's LAYOUT rather than its identity.
# This project checks the same repo out as <project>/github, <project>/local,
# <project>/dev; the basename alone would render a dozen rows all called
# "local", which is unreadable and unactionable.
LAYOUT_DIRS = {"github", "local", "dev", "private", "main", "src", "repo",
               "current", "master", "trunk"}


def installs_in_scope(installs, roots):
    """Keep only editable installs whose source lives under a scanned root.

    The pip axis is environment-wide: it sees every editable install in
    the interpreter, wherever it lives. Narrowing the filesystem with
    --root but leaving this unfiltered made the report mix "what is under
    this directory" with "everything installed anywhere", so scanning
    C:\\code\\dazzlecmd listed wtf-privacy and dazzlelink as stale.

    Scope is decided on the RECORDED path, whether or not that directory
    still exists. An earlier version short-circuited on "the path is
    missing, keep it regardless" before applying the root filter, which
    let a broken install anywhere on disk leak into every narrowed run --
    amdead-lib surfaced while scanning dazzlecmd, rendered only as
    "excluded by policy", which explains nothing. A broken install is
    still worth reporting; it is worth reporting in a run that was
    actually asking about it.
    """
    normed = [norm(r) for r in (roots or []) if r]
    kept, dropped = [], 0
    for inst in installs:
        np = norm(inst.get("path"))
        if not normed or any(np == r or np.startswith(r + os.sep)
                             for r in normed):
            kept.append(inst)
        else:
            dropped += 1
    return kept, dropped


def _visible_kinds(only_kinds, skip_kinds, show_clean=False,
                   drop_not_cloned=False):
    """Which finding kinds to render. None means 'all except clean'.

    'clean' is opt-in: on a 150-repo box it is the longest section and
    says nothing actionable. But it must be REACHABLE, because otherwise
    there is no way to tell "scanned and fine" from "never scanned" --
    which is exactly the doubt a scanned inventory should remove.

    'not-cloned' is suppressed when the caller narrowed the filesystem
    for this run, because the finding would then be measuring the scope
    of the question rather than the state of the machine.
    """
    if only_kinds:
        return [k for k in only_kinds if k not in (skip_kinds or [])]
    base = [k for k in FINDING_ORDER if k != "clean" or show_clean]
    if drop_not_cloned:
        base = [k for k in base if k != "not-cloned"]
    if skip_kinds:
        base = [k for k in base if k not in skip_kinds]
    return base


def _display_name(r):
    """A name a human can act on.

    Repos with no remote have no OWNER/REPO to show. Fall back to the
    directory name -- qualified by its parent when the directory only
    names a checkout layout.
    """
    if r["full_name"]:
        return r["full_name"]
    for path in r["paths"]:
        if not path:
            continue
        clean = str(path).rstrip(r"\/")
        base = os.path.basename(clean)
        if base.lower() in LAYOUT_DIRS:
            parent = os.path.basename(os.path.dirname(clean))
            if parent:
                return f"{parent}/{base}"
        return base or clean
    return r["key"]


def _fmt_repo(r, kind=None):
    """Render a row. `kind` selects WHICH checkout the row describes.

    Checkout-scoped findings (unpushed / no-upstream / dirty) must show
    the checkout that triggered them, not the repo's primary -- otherwise
    a repo appears under NO UPSTREAM displaying a branch that plainly has
    one, which reads as a bug in the tool rather than a fact about the
    machine.
    """
    name = _display_name(r)
    live = [c for c in (r.get("checkouts") or []) if not c.get("excluded")]
    triggered = (r.get("triggers") or {}).get(kind) or []

    if triggered:
        shown = triggered[0]
        g = shown.get("git") or {}
    else:
        shown = None
        g = r["git"] or {}

    bits = []
    if r.get("foreign"):
        bits.append("not ours")
    if shown is not None and len(live) > 1:
        label = os.path.basename(str(shown.get("path", "")).rstrip("\\/"))
        extra = f" +{len(triggered) - 1}" if len(triggered) > 1 else ""
        bits.append(f"{label}{extra} of {len(live)}")
    elif len(live) > 1 and r.get("primary"):
        bits.append(os.path.basename(str(r["primary"]).rstrip("\\/"))
                    + f" of {len(live)}")
    elif len(live) > 1:
        bits.append(f"{len(live)} checkouts, none primary")
    if g.get("branch"):
        bits.append(g["branch"])
    if g.get("ahead"):
        bits.append(f"{g['ahead']} ahead")
    if g.get("behind"):
        bits.append(f"{g['behind']} behind")
    if g.get("dirty_count"):
        bits.append(f"{g['dirty_count']} dirty")
    if g.get("untracked_count"):
        bits.append(f"{g['untracked_count']} untracked")
    return name, ", ".join(bits)


def render_text(records, findings, meta, pal=None):
    """Human-readable report. Outbound drift first, by design."""
    pal = pal or Palette(False)
    safe_print("")
    safe_print(f"  Ecosystem   {meta['namespace_count']} namespaces * "
               f"{meta['org_repo_count']} namespace repos * "
               f"{meta['cloned_count']} cloned here * "
               f"{meta['install_count']} installed")
    safe_print(f"  Sources     namespaces [{meta['gh_detail']}] * "
               f"installed [{meta['install_count']} editable] * "
               f"filesystem [{', '.join(meta['roots'])}]")
    safe_print(f"              published [{meta['published_detail']}]"
               + (f" * config [{meta['config']}]" if meta.get("config") else ""))
    if meta.get("narrowed"):
        safe_print("  NOTE        --root narrows the scan; 'not cloned' is "
                   "suppressed and installs outside it are skipped")
    for err in meta.get("errors", []):
        safe_print(f"  WARNING     {err}")

    # Headline first. The question most runs are asking is "what do I need
    # to pull?", and burying it under risk-ordered sections makes the tool
    # feel like it answers a different question than the one you asked.
    counts = {k: len(findings.get(k) or []) for k in FINDING_ORDER}
    to_pull = counts.get("behind-upstream", 0)
    # Without a fetch, behind-counts came from whatever the last fetch
    # left behind. Saying "nothing to pull" then is a confident negative
    # we have not earned -- the same class of claim as the original bug
    # where a stale ref made every repo read as current.
    if meta.get("stale_behind") and not to_pull:
        headline = pal("yellow", "pull status unknown (no fetch)")
    elif to_pull:
        headline = pal("red", f"{to_pull} to pull")
    else:
        headline = pal("green", "nothing to pull")
    parts = [headline]
    for kind, label in (("unpushed", "to push"),
                        ("stale-install-metadata", "to reinstall"),
                        ("dirty", "dirty"),
                        ("no-upstream", "unbacked")):
        if counts.get(kind):
            parts.append(pal(FINDING_COLOURS[kind],
                             f"{counts[kind]} {label}"))
    safe_print("")
    safe_print("  " + pal.bold("Summary") + "     " + "  *  ".join(parts))

    shown = 0
    visible = meta.get("visible_kinds")
    for kind in meta.get("order") or FINDING_ORDER:
        if visible is not None and kind not in visible:
            continue
        items = findings.get(kind) or []
        if not items:
            continue
        shown += 1
        colour = FINDING_COLOURS.get(kind, "reset")
        safe_print("")
        safe_print("  " + pal(colour, pal.bold(FINDING_LABELS[kind])))
        for r in items[:40]:
            raw, detail = _fmt_repo(r, kind)
            if len(raw) > 38:
                raw = raw[:37] + "~"
            # Pad BEFORE colouring: ANSI codes are characters, so padding
            # a coloured string mis-aligns every column.
            name = pal(colour, f"{raw:<38}")
            if kind == "stale-remote-url":
                cfg = r["configured_slugs"][0] if r["configured_slugs"] else "?"
                safe_print(f"    {name} {cfg} -> {r['full_name']}")
            elif kind == "stale-install-metadata":
                inst = r["installed"] or {}
                safe_print(f"    {name} installed {inst.get('version')} "
                           f"< source {r['source_version']}")
            elif kind == "install-behind-published":
                inst = r["installed"] or {}
                safe_print(f"    {name} installed {inst.get('version')} "
                           f"< PyPI {r['published']}")
            elif kind == "stale-dist-name":
                inst = r["installed"] or {}
                safe_print(f"    {name} installed as {inst.get('name')!r}, "
                           f"repo declares {r['declared_dist']!r} "
                           f"({r['declared_dist_source']})")
            elif kind == "pypi-name-collision":
                urls = ", ".join((r.get("pypi_urls") or [])[:1])
                safe_print(f"    {name} PyPI {r['published']} at {urls or '?'}"
                           f" -- that is a different project; installing "
                           f"would overwrite this checkout")
            elif kind == "source-missing":
                inst = r["installed"] or {}
                safe_print(f"    {name} {inst.get('name')} "
                           f"{inst.get('version')} -> {inst.get('path')}")
            elif kind == "not-cloned":
                safe_print(f"    {name}")
            elif kind == "excluded-by-policy":
                safe_print(f"    {name} {r['excluded']}")
            else:
                safe_print(f"    {name} {detail}")
        if len(items) > 40:
            safe_print(f"    ... and {len(items) - 40} more")

    safe_print("")
    safe_print("  " + pal("green", f"{meta['clean']} repos clean and current."))
    if not shown:
        # "Nothing needs attention" must describe the MACHINE, not the
        # filter. Printing it because --only hid every section produced a
        # flat contradiction with the Summary line directly above it.
        #
        # Count only what the USER's filter hid. `not-cloned` under a
        # narrowed scan was suppressed for a different reason, already
        # stated in the NOTE above -- blaming --only for it inflated the
        # tally from 5 to 128 and simply moved the inaccuracy.
        suppressed_elsewhere = {"clean", "excluded-by-policy"}
        if meta.get("narrowed"):
            suppressed_elsewhere.add("not-cloned")
        hidden = sum(n for k, n in counts.items()
                     if n and k not in suppressed_elsewhere
                     and (visible is not None and k not in visible))
        if hidden:
            safe_print(f"  {hidden} finding(s) hidden by --only/--skip.")
        elif meta.get("stale_behind"):
            safe_print("  Nothing else needs attention, but behind-counts "
                       "were not refreshed (--no-fetch).")
        else:
            safe_print("  Nothing needs attention.")
    safe_print("")
    return 0


def render_json(records, findings, meta):
    payload = {
        "host": platform.node(),
        "schema": 1,
        "meta": meta,
        "findings": {
            k: [{
                "key": r["key"],
                "full_name": r["full_name"],
                "paths": r["paths"],
                "configured_slugs": r["configured_slugs"],
                "redirected": r["redirected"],
                "git": r["git"],
                "primary": r.get("primary"),
                "primary_reason": r.get("primary_reason"),
                "checkouts": r.get("checkouts") or [],
                "installed": r["installed"],
                "source_version": r["source_version"],
                "published": r["published"],
                "excluded": r["excluded"],
            } for r in (findings.get(k) or [])]
            for k in FINDING_ORDER if findings.get(k)
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _norm(name):
    """PEP 503 dist-name normalization."""
    return normalize_dist(name)


def _describe_action(verb, record, cmd):
    """What this action will do, in plain language, for the ? prompt."""
    g = record.get("git") or {}
    if verb == "pull":
        return (f"    fast-forward only -- no merge, no rebase.\n"
                f"    checkout : {record.get('primary')}\n"
                f"    branch   : {g.get('branch')} tracking {g.get('upstream')}\n"
                f"    behind   : {g.get('behind')} commit(s)\n"
                f"    chosen because: {record.get('primary_reason')}\n"
                f"    aborts if the tree is not clean; nothing is stashed.")
    inst = record.get("installed") or {}
    return (f"    refresh this package's recorded version metadata.\n"
            f"    installed: {inst.get('name')} {inst.get('version')}\n"
            f"    source   : {record.get('source_version')}\n"
            f"    --no-deps, so no other package is touched.\n"
            f"    source files are NOT modified.")


def _confirm(prompt, describe, assume_yes=False):
    """Ask before acting. Returns 'yes' | 'no' | 'all' | 'quit'.

    Default is NO on a bare Enter. This writes to real repositories
    across a whole machine; the safe answer must be the one you get by
    reflex. Without a TTY there is no safe way to ask, so the caller
    must have passed --yes explicitly.
    """
    if assume_yes:
        return "yes"
    while True:
        try:
            answer = input(f"  {prompt} [y/N/a/q/?] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "quit"
        if answer in ("", "n", "no"):
            return "no"
        if answer in ("y", "yes"):
            return "yes"
        if answer in ("a", "all"):
            return "all"
        if answer in ("q", "quit"):
            return "quit"
        if answer in ("?", "h", "help"):
            safe_print(describe)
            safe_print("    y = do this one   n = skip (default)")
            safe_print("    a = do this and all remaining without asking")
            safe_print("    q = stop; nothing further is done")
            continue
        safe_print("    unrecognized -- y, n, a, q, or ? for detail")


def apply_fixes(findings, dry_run=False, assume_yes=False, interactive=True):
    """The two provably-safe operations. Everything else refuses.

    Refuses on any dirty tree rather than stashing: auto-stashing is a
    well-known way to lose work, and the judgment of what to do with
    in-progress changes belongs to a human.
    """
    actions, refused = [], []

    for r in findings.get("behind-upstream") or []:
        g = r["git"] or {}
        if not g.get("upstream"):
            # A fast-forward needs a tracking branch. Without one there is
            # nothing to fast-forward FROM, and pulling would guess a
            # remote/branch pair on the user's behalf.
            refused.append((r, "primary checkout has no upstream -- "
                               "nothing to fast-forward from"))
            continue
        if (g.get("dirty_count") or 0) > 0 or (g.get("untracked_count") or 0) > 0:
            refused.append((r, "dirty tree -- refusing to pull (will not stash)"))
            continue
        if (g.get("ahead") or 0) > 0:
            refused.append((r, "diverged -- needs a merge, not a fast-forward"))
            continue
        if r.get("foreign"):
            refused.append((r, "not ours -- refusing to pull an upstream you "
                               "only track"))
            continue
        actions.append(("pull", r))

    for r in findings.get("stale-install-metadata") or []:
        # Never reinstall across a name mismatch: the dist installed under
        # the old name and the repo's declared name are different PyPI
        # identities, and the old one may now belong to someone else (#106).
        inst = r.get("installed") or {}
        declared = r.get("declared_dist")
        if declared and _norm(inst.get("name")) != _norm(declared):
            refused.append((r, f"installed dist {inst.get('name')!r} != repo "
                               f"declares {declared!r} -- these are different "
                               f"PyPI identities; uninstall the old, install "
                               f"the new; refusing to guess"))
            continue
        if r.get("pypi_owned") is False:
            refused.append((r, "that PyPI name belongs to a different project "
                               "-- installing would overwrite this checkout, "
                               "not update it"))
            continue
        actions.append(("reinstall", r))

    # Categories --fix structurally never acts on. Listing each one as a
    # "refusal" implied the tool had considered acting and declined; ~40
    # such lines buried the ~10 dirty-tree refusals, which are the ones
    # you can actually do something about. Summarize instead.
    never_acted = {}
    for kind in ("unpushed", "no-upstream", "stale-remote-url",
                 "stale-dist-name", "pypi-name-collision"):
        n = len(findings.get(kind) or [])
        if n:
            never_acted[kind] = n

    # dazzlecmd is updated LAST: dz runs from an editable install of it,
    # so pulling it mid-run swaps source under the running process.
    def is_self(rec):
        return "dazzlecmd" in (rec["full_name"] or rec["key"]).lower()
    actions.sort(key=lambda a: is_self(a[1]))

    done = skipped = 0
    for verb, r in actions:
        # Act ONLY on the primary checkout, never on paths[0]. paths[0]
        # is discovery order (alphabetical), which for dazzlecmd is
        # `fiber-work` -- a feature branch. Reinstalling or fast-
        # forwarding there would put main's material into someone's
        # in-progress work. Where no primary could be chosen, refuse:
        # guessing is exactly what this must not do.
        target = r.get("primary")
        if not target and not (r.get("checkouts") or []):
            # An install-only record (a subpackage, or a package whose
            # source is outside any scanned repo) has no checkouts to
            # choose between -- its single install path is unambiguous.
            target = (r.get("installed") or {}).get("path")
        if not target:
            refused.append((r, f"no primary checkout ({r.get('primary_reason')})"
                               " -- refusing to guess which one to touch"))
            continue
        if verb == "pull":
            cmd = ["git", "-C", str(target), "pull", "--ff-only"]
        else:
            cmd = [sys.executable, "-m", "pip", "install", "-e",
                   str(target), "--no-deps", "-q"]
        label = r["full_name"] or r["key"]
        if dry_run:
            safe_print(f"    [dry-run] {label}: {' '.join(cmd)}")
            continue

        if interactive and not assume_yes:
            safe_print("")
            safe_print(f"  {verb.upper()}  {label}")
            safe_print(f"    {' '.join(cmd)}")
            choice = _confirm("apply?", _describe_action(verb, r, cmd))
            if choice == "quit":
                safe_print("")
                safe_print(f"  stopped -- {done} applied, "
                           f"{len(actions) - done - 1} not attempted")
                break
            if choice == "no":
                skipped += 1
                continue
            if choice == "all":
                assume_yes = True

        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        status = "ok" if res.returncode == 0 else "FAILED"
        safe_print(f"    {label}: {verb} {status}")
        done += 1
        if res.returncode != 0:
            safe_print(f"      {(res.stderr or '').strip().splitlines()[:1]}")

    if not dry_run:
        safe_print("")
        safe_print(f"  {done} applied, {skipped} skipped, "
                   f"{len(refused)} refused.")
    if refused:
        safe_print("")
        safe_print("  BLOCKED -- would act, but something is in the way:")
        for r, why in refused:
            name = _display_name(r)
            if len(name) > 38:
                name = name[:37] + "~"
            safe_print(f"    {name:<38} {why}")
    if never_acted:
        safe_print("")
        total = sum(never_acted.values())
        detail = ", ".join(f"{n} {k}" for k, n in sorted(never_acted.items()))
        safe_print(f"  NOT ACTED ON -- {total} finding(s) in categories --fix "
                   f"never touches:")
        safe_print(f"    {detail}")
        safe_print("    these need a decision from you; see the report above.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="dz dazzle-update",
        description="Ecosystem-wide update/status scanner across every "
                    "namespace we own.",
        epilog=(
            "examples:\n"
            "  dz dazzle-update                 Report what needs attention\n"
            "  dz dazzle-update --published     Also compare against PyPI\n"
            "  dz dazzle-update --json          Machine-readable output\n"
            "  dz dazzle-update --fix --dry-run Show what --fix would do\n"
            "  dz dazzle-update --scope DazzleLib\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--published", action="store_true",
                   help="Query PyPI (network; off by default)")
    p.add_argument("--fix", action="store_true",
                   help="Apply ff-only pulls and editable reinstalls")
    p.add_argument("--dry-run", action="store_true",
                   help="With --fix, show actions without running them")
    p.add_argument("--yes", "-y", action="store_true",
                   help="With --fix, apply every action without asking. "
                        "Required for non-interactive use.")
    p.add_argument("--scope", action="append", default=None,
                   help="Limit to a namespace (repeatable)")
    p.add_argument("--root", action="append", default=None,
                   help=f"Filesystem root to scan (default: {DEFAULT_ROOT})")
    p.add_argument("--no-cache", action="store_true",
                   help="Ignore the identity-resolution cache")
    p.add_argument("--no-fetch", action="store_true",
                   help="Skip refreshing remote refs (behind-counts will be "
                        "stale; only for offline use)")
    p.add_argument("--fetch-timeout", type=int, default=60,
                   help="Seconds before giving up on one fetch (default 60)")
    p.add_argument("--color", choices=("auto", "always", "never"),
                   default="auto", help="Colourize output (default auto)")
    p.add_argument("--no-progress", action="store_true",
                   help="Suppress the progress line on stderr")
    p.add_argument("--all", action="store_true",
                   help="Also list repos with nothing to do, so you can "
                        "confirm a repo was scanned rather than skipped")
    p.add_argument("--sort", choices=SORT_MODES, default=None,
                   help="Row order within each section (default: newest)")
    p.add_argument("--only", action="append", default=None,
                   metavar="KIND",
                   help="Show only these finding kinds (repeatable). "
                        "Names or aliases, e.g. --only dirty --only behind. "
                        "Use --list-kinds to see them all.")
    p.add_argument("--skip", action="append", default=None, metavar="KIND",
                   help="Hide these finding kinds (repeatable)")
    p.add_argument("--list-kinds", action="store_true",
                   help="List finding kinds and their aliases, then exit")
    p.add_argument("--cached", action="store_true",
                   help="Replay the last scan instead of re-scanning "
                        "(no network); age is always reported")
    p.add_argument("--max-age", type=int, default=None, metavar="SECONDS",
                   help="With --cached, refuse a cache older than this")
    p.add_argument("--config", default=None,
                   help="Path to a config file (JSON, or YAML if PyYAML is "
                        "installed)")
    p.add_argument("--init-config", action="store_true",
                   help="Write a starter config and exit")
    p.add_argument("-v", "--verbose", action="count", default=0)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    set_verbosity(args.verbose)

    errors = []
    if args.init_config:
        target = args.config or os.path.join(
            user_config_dir(), "dazzle-update.json")
        ok, err = write_template(target)
        safe_print(f"  wrote config template: {target}" if ok
                   else f"  could not write {target}: {err}")
        return 0 if ok else 1

    if args.list_kinds:
        safe_print("")
        safe_print("  finding kinds (use with --only / --skip):")
        for kind in FINDING_ORDER:
            aliases = sorted(a for a, k in FINDING_ALIASES.items() if k == kind)
            alias_txt = f"   aliases: {', '.join(aliases)}" if aliases else ""
            safe_print(f"    {kind:<26}{alias_txt}")
        safe_print("")
        return 0

    only_kinds, bad_only = resolve_kinds(args.only)
    skip_kinds, bad_skip = resolve_kinds(args.skip)
    if bad_only or bad_skip:
        safe_print(f"  unknown finding kind(s): {', '.join(bad_only + bad_skip)}")
        safe_print("  run 'dz dazzle-update --list-kinds' to see valid names")
        return 2

    cfg, cfg_path, cfg_err = load_config(args.config)
    if cfg_err:
        errors.append(cfg_err)

    sort_mode = args.sort or cfg.get("sort") or "newest"
    if sort_mode not in SORT_MODES:
        errors.append(f"config 'sort': unknown mode {sort_mode!r}; using newest")
        sort_mode = "newest"

    report_order, bad_order = apply_order(cfg.get("order"))
    if bad_order:
        errors.append("config 'order': unknown kind(s) ignored: "
                      + ", ".join(bad_order))

    # CLI beats config; config beats built-in default.
    roots = args.root or cfg.get("roots") or [DEFAULT_ROOT]

    # "Not cloned" means "we own it and it is nowhere on this machine".
    # That claim is only honest when the scan covered the machine. If the
    # caller deliberately narrowed the filesystem for this run, every repo
    # outside that directory would be reported missing -- 123 of them, on
    # a real run -- which is noise dressed up as a finding.
    narrowed = bool(args.root)

    progress = Progress(enabled=not args.no_progress,
                        verbose=args.verbose)
    progress.update("checking gh auth", 0)
    gh_ok, gh_detail = gh_status()
    namespaces, ns_err = ([], None)
    if cfg.get("namespaces"):
        namespaces = list(cfg["namespaces"])          # explicit override
    elif gh_ok:
        progress.update("deriving namespaces", 0)
        namespaces, ns_err = derive_namespaces()      # preferred: derived
        if ns_err:
            errors.append(ns_err)
    else:
        errors.append(f"namespace listing skipped: {gh_detail}")
    if args.scope:
        wanted = {s.lower() for s in args.scope}
        namespaces = [n for n in namespaces if n.lower() in wanted]

    personal = cfg.get("personal_namespace") or (gh_login() if gh_ok else None)
    excludes = (list(cfg["exclude"]) if cfg.get("exclude_replace")
                else DEFAULT_EXCLUDES + list(cfg.get("exclude") or []))
    config = EcosystemConfig(
        namespaces=namespaces, personal_namespace=personal,
        excludes=excludes, roots=roots,
        member_prefixes=tuple(cfg.get("member_prefixes") or ("dazzle",)),
        personal_allow=cfg.get("personal_allow") or (),
        include=cfg.get("include") or (),
        local_only_branches=cfg.get("local_only_branches") or ())

    cache = {} if args.no_cache else load_cache(_cache_path())
    resolver = IdentityResolver(cache=cache)

    # Listing every namespace costs ~4.7s of sequential gh calls -- the
    # bulk of the wait before scanning starts, with nothing on screen.
    # Reuse it within namespace_ttl (org membership moves in days, not
    # seconds) and narrate it either way so the tool never looks hung.
    want = namespaces + ([personal] if personal else [])
    ns_ttl = cfg.get("namespace_ttl", 86400)
    cached_ns, ns_age, ns_cache_err = ({}, None, "caching disabled")
    if ns_ttl and not args.no_cache:
        cached_ns, ns_age, ns_cache_err = scancache.load_namespaces(
            path=cfg.get("cache_path"), ttl=ns_ttl)
        cached_ns = cached_ns or {}

    org_repos, fetched_ns = [], {}
    for idx, ns in enumerate(want, 1):
        hit = cached_ns.get(ns)
        if hit is not None:
            progress.update("namespaces (cached)", idx, len(want), ns)
            names = hit
        else:
            progress.update("listing namespaces", idx, len(want), ns)
            repos, err = list_org_repos(ns)
            if err:
                errors.append(err)
            names = [e.get("nameWithOwner") for e in repos
                     if e.get("nameWithOwner")]
        fetched_ns[ns] = names
        org_repos.extend({"full_name": n} for n in names)
    progress.done()

    if ns_ttl and not args.no_cache and fetched_ns != cached_ns:
        scancache.save_namespaces(fetched_ns, path=cfg.get("cache_path"))
    if cached_ns and ns_age is not None:
        errors.append(f"namespace listing reused from cache "
                      f"({scancache.format_age(ns_age)} old; "
                      f"--no-cache to refresh)")

    cached_age = None
    if args.cached:
        rec, cmeta, cached_age, cerr = scancache.load(
            path=cfg.get("cache_path"),
            max_age=args.max_age if args.max_age is not None
            else cfg.get("cache_max_age"))
        if cerr:
            safe_print(f"  {cerr}")
            safe_print("  run without --cached to perform a fresh scan")
            return 2
        records = rec
        meta = dict(cmeta)
        meta["errors"] = list(meta.get("errors") or []) + [
            f"REPLAYED from cache, {scancache.format_age(cached_age)} old -- "
            "remote state may have changed since"]
        findings = classify(records, EcosystemConfig(),
                            sort_mode=args.sort or cfg.get("sort") or "newest")
        meta["clean"] = clean_count(records, findings)
        meta["visible_kinds"] = _visible_kinds(only_kinds, skip_kinds,
                                               show_clean=args.all,
                                               drop_not_cloned=bool(args.root))
        meta["order"] = apply_order(cfg.get("order"))[0] if cfg else meta.get("order")
        pal = make_palette(args.color)
        if args.json:
            return render_json(records, findings, meta)
        return render_text(records, findings, meta, pal=pal)

    local, fetch_failures = collect_local(
        roots, resolver, config, verbose=args.verbose, progress=progress,
        do_fetch=(not args.no_fetch) and cfg.get("fetch", True),
        fetch_timeout=args.fetch_timeout or cfg.get("fetch_timeout", 60))
    if args.no_fetch:
        errors.append("--no-fetch: behind-counts reflect the last fetch, "
                      "not the current remote")
    if fetch_failures:
        errors.append(f"{len(fetch_failures)} repo(s) could not be fetched; "
                      "their behind-counts may be stale")
    installs, out_of_scope = installs_in_scope(editable_installs(), roots)
    if out_of_scope:
        errors.append(f"{out_of_scope} editable install(s) outside the scanned "
                      f"root(s) were skipped")

    source_versions = {}
    for inst in installs:
        p = inst.get("path")
        if p and os.path.isdir(str(p)):
            v = read_source_version(p)
            if v:
                source_versions[norm(p)] = v

    # Declared dist names come from each repo's OWN metadata. Never from
    # the installed dist name -- see issue #106.
    declared = {}
    for inst in installs:
        p = inst.get("path")
        if p and os.path.isdir(str(p)):
            name, source = read_declared_dist_name(p)
            if name:
                declared[norm(p)] = (name, source)

    owners = list(namespaces) + ([personal] if personal else [])
    published, pypi_meta = {}, {}
    published_detail = "skipped -- pass --published"
    if args.published or cfg.get("published"):
        failures = 0
        seen = set()
        for inst in installs:
            dec = declared.get(norm(inst.get("path")))
            query = dec[0] if dec else inst["name"]
            key = normalize_dist(query)
            if key in seen:
                continue
            seen.add(key)
            info, err = pypi_project(query)
            if err:
                failures += 1
            elif info:
                published[key] = info["version"]
                pypi_meta[key] = {
                    "owned": pypi_owned_by(info, owners),
                    "urls": info["urls"],
                }
        published_detail = f"{len(published)} resolved"
        if failures:
            published_detail += f", {failures} failed"

    if not args.no_cache:
        save_cache(_cache_path(), resolver.cache)

    records = join(org_repos, local, installs, config,
                   source_versions=source_versions, published=published,
                   declared_dists=declared, pypi_meta=pypi_meta)
    findings = classify(records, config, sort_mode=sort_mode)

    meta = {
        "namespace_count": len(namespaces) + (1 if personal else 0),
        "org_repo_count": len(org_repos),
        "cloned_count": sum(1 for r in records.values() if r["cloned"]),
        "install_count": len(installs),
        "gh_detail": gh_detail,
        "published_detail": published_detail,
        "roots": roots,
        "errors": errors,
        "clean": clean_count(records, findings),
        "config": cfg_path,
        "visible_kinds": _visible_kinds(only_kinds, skip_kinds,
                                        show_clean=args.all,
                                        drop_not_cloned=narrowed),
        "order": report_order,
        "sort": sort_mode,
        "narrowed": narrowed,
        "stale_behind": bool(args.no_fetch) or not cfg.get("fetch", True),
    }

    ok, cache_err = (True, None)
    if cfg.get("cache_write", True):
        ok, cache_err = scancache.save(records, meta,
                                       path=cfg.get("cache_path"))
    if not ok and args.verbose:
        errors.append(f"could not cache scan: {cache_err}")

    pal = make_palette(args.color)
    if args.fix:
        render_text(records, findings, meta, pal=pal)
        interactive = sys.stdin.isatty()
        if not args.dry_run and not args.yes and not interactive:
            safe_print("  --fix needs a terminal to confirm each action.")
            safe_print("  Re-run with --dry-run to preview, or --yes to apply "
                       "without asking.")
            return 2
        safe_print("")
        safe_print("  APPLYING FIXES" + (" (dry run)" if args.dry_run
                                         else " -- you will be asked per repo"
                                         if not args.yes else " (--yes)"))
        return apply_fixes(findings, dry_run=args.dry_run,
                           assume_yes=args.yes, interactive=interactive)
    if args.json:
        return render_json(records, findings, meta)
    return render_text(records, findings, meta, pal=pal)


if __name__ == "__main__":
    sys.exit(main())
