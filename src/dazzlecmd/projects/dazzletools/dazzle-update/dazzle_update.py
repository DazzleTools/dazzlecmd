"""dz dazzle-update -- ecosystem-wide update/status scanner.

Reports what needs fetching, pushing, or reinstalling across every
namespace we own, by joining four independent views: GitHub namespace
listings, editable installs, the filesystem, and PyPI.

Read-only by default. --fix applies exactly two provably-safe
operations and refuses anything requiring judgment.

CONTRACT: bare positional arguments are repo QUERIES (names or globs),
permanently. This tool is flag-shaped; capability growth happens as
flags, not verbs, so queries and modes can never collide. (Decided
2026-08-02; relitigable only as a deliberate breaking change -- see the
single-repo-query-surface design doc.)

    dz dazzle-update                 The report
    dz dazzle-update dazzlesum       Everything about one repo (globs ok)
    dz dazzle-update --published     Add the PyPI axis (network)
    dz dazzle-update --json          Machine-readable, for cross-box diffs
    dz dazzle-update --fix           ff-only pulls + editable reinstalls
    dz dazzle-update --scope DazzleLib
"""

import argparse
import json
import time
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
from _repo_common.private_state import private_state  # noqa: E402
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
from sets import (  # noqa: E402
    annotate as annotate_sets,
    declared_members,
    load_sets,
)
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
    select_primary,
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
        out.append(_read_one(path, resolver,
                             churn_patterns=config.churn_files))
    progress.done()
    return out, fetch_failures


def _read_one(path, resolver, churn_patterns=()):
    """All axes for a single repo path."""
    remotes = detect_remotes(path)
    origin = next((r for r in remotes if r["name"] == "origin"), None)
    slug = None
    if origin:
        slug = origin.get("slug") or parse_slug(origin.get("fetch_url"))
    info = resolver.resolve(slug) if slug else None
    upstream = get_upstream(path)
    behind, ahead = get_ahead_behind(path, upstream=upstream)
    counts = get_status_counts(path, churn_patterns=churn_patterns)
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
            "churn_count": counts.get("churn_count", 0),
        },
        "error": (info or {}).get("error"),
        "last_activity": get_last_commit_epoch(path),
        "private": private_state(path),
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


def count_churn_repos(records):
    """In-scope repos where any checkout carries reclassified churn.

    The number the NOTE line reports: churn is filtered from dirty, and a
    filter that does not say what it filtered is how a report starts
    describing the question instead of the machine.
    """
    return sum(
        1 for r in records.values()
        if r.get("cloned") and not r.get("excluded")
        and not r.get("third_party")
        and any((c.get("git") or {}).get("churn_count")
                for c in (r.get("checkouts") or [])))


def apply_set_lens(findings, wanted_names):
    """Filter every findings bucket to records in the named set(s).

    Returns (filtered_findings, hidden). `hidden` counts the DISTINCT
    repos that carried at least one real finding and were dropped by the
    lens -- the number the report must state, because a lens that hides
    silently is the report describing the question instead of the
    machine. `clean` and `excluded-by-policy` are not findings and do
    not count toward it.
    """
    wanted = {n.lower() for n in wanted_names}
    out, hidden = {}, set()
    for kind, items in findings.items():
        keep = []
        for r in items:
            if wanted & {s.lower() for s in (r.get("sets") or [])}:
                keep.append(r)
            elif kind not in ("clean", "excluded-by-policy"):
                hidden.add(r["key"])
        out[kind] = keep
    return out, len(hidden)


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


def _fmt_repo(r, kind=None, hide_sets=frozenset()):
    """Render a row. `kind` selects WHICH checkout the row describes.

    Checkout-scoped findings (unpushed / no-upstream / dirty) must show
    the checkout that triggered them, not the repo's primary -- otherwise
    a repo appears under NO UPSTREAM displaying a branch that plainly has
    one, which reads as a bug in the tool rather than a fact about the
    machine.

    `hide_sets` suppresses set tags the reader already knows: under
    --only-set dazzle, tagging every row `in:dazzle` is noise.
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
    if g.get("churn_count"):
        bits.append(f"{g['churn_count']} churn")
    # Notable-only: `ok` and `none` say nothing, because a tag that
    # appears on every row stops being read. `split` and `broken` are
    # encouragement, not fault -- separated private repos can be
    # deliberate, so this never becomes a finding.
    pstate = r.get("private_state")
    if pstate in ("split", "broken"):
        bits.append(f"private:{pstate}")
    tags = [s for s in (r.get("sets") or []) if s.lower() not in hide_sets]
    if tags:
        bits.append("in:" + ",".join(tags))
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
    # Finding NOTHING on disk is not a clean bill of health, it is a
    # scan that could not see the machine -- almost always a `roots`
    # that does not match where the code lives, which is the one
    # machine-specific setting and therefore the first thing wrong on a
    # new box. Saying "nothing needs attention" here would be the report
    # describing its own scope instead of reality.
    if not meta.get("cloned_count"):
        where = ", ".join(meta.get("roots") or []) or "(no roots configured)"
        safe_print(f"  SETUP       no git repos found under {where}")
        if meta.get("org_repo_count"):
            safe_print(f"              but {meta['org_repo_count']} repo(s) "
                       f"exist in your namespaces -- 'roots' is probably "
                       f"pointing at the wrong place")
        safe_print("              set 'roots' in your config "
                   "(dz dazzle-update --init-config writes one)")
    if meta.get("churn_repos"):
        pats = ", ".join(meta.get("churn_files") or [])
        safe_print(f"  NOTE        auto-stamp churn in {meta['churn_repos']} "
                   f"repo(s) ({pats}) is not counted dirty; rows show it as "
                   "'N churn'")
    if meta.get("set_lens"):
        hidden = meta.get("set_hidden", 0)
        tail = (f"; {hidden} repo(s) with findings outside the set hidden"
                if hidden else "; nothing with findings falls outside it")
        safe_print("  SET LENS    showing only "
                   f"'{', '.join(meta['set_lens'])}'{tail}")
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
        lens_names = frozenset(n.lower() for n in meta.get("set_lens") or ())
        for r in items[:40]:
            raw, detail = _fmt_repo(r, kind, hide_sets=lens_names)
            if len(raw) > 38:
                raw = raw[:37] + "~"
            # Pad BEFORE colouring: ANSI codes are characters, so padding
            # a coloured string mis-aligns every column.
            name = pal(colour, f"{raw:<38}")
            if kind == "stale-remote-url":
                # Show the slug that actually DIFFERS from canonical, not
                # whichever checkout was walked first. On a repo with
                # several checkouts where some have been repointed, [0]
                # produced rows reading "X -> X" -- a redirect from a
                # name to itself, which is nonsense on its face.
                canon = (r["full_name"] or "").lower()
                stale = [x for x in (r["configured_slugs"] or [])
                         if x.lower() != canon]
                cfg = (stale[0] if stale
                       else (r["configured_slugs"] or ["?"])[0])
                if len(stale) > 1:
                    cfg += f" (+{len(stale) - 1} more)"
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
            elif kind == "private-uninitialized":
                stores = r.get("private_stores") or []
                where = stores[0] if stores else "?"
                extra = " (claude docs)" if any(
                    (c.get("private") or {}).get("claude")
                    for c in (r.get("checkouts") or [])) else ""
                safe_print(f"    {name} {where}{extra}")
            elif kind == "not-cloned":
                safe_print(f"    {name}")
            elif kind == "excluded-by-policy":
                safe_print(f"    {name} {r['excluded']}")
            else:
                safe_print(f"    {name} {detail}")
        if len(items) > 40:
            safe_print(f"    ... and {len(items) - 40} more")

    safe_print("")
    # Churn-only repos land in `clean`, whose section is hidden by
    # default -- so without this parenthetical they appear NOWHERE: not
    # dirty (reclassified), not listed (clean is a noop section). The
    # footer is the one line that still accounts for them.
    churn_clean = sum(
        1 for r in findings.get("clean") or []
        if any((c.get("git") or {}).get("churn_count")
               for c in (r.get("checkouts") or [])))
    churn_tail = (f" ({churn_clean} with only auto-stamp churn)"
                  if churn_clean else "")
    if meta.get("set_lens"):
        # Under a lens the bare count invites a misreading: "4 repos
        # clean" directly under 4 dirty rows read as a contradiction (a
        # live user hit exactly this, helped by the numeric coincidence).
        # Scope and denominator make it unambiguous: clean repos are
        # OTHER members of the set, counted against the set's scanned
        # size. not-cloned and excluded repos were never scanned, so
        # they cannot sit in the denominator of "clean".
        scanned = {r["key"] for k, items in findings.items()
                   for r in items
                   if k not in ("excluded-by-policy", "not-cloned")}
        names = ", ".join(meta["set_lens"])
        safe_print("  " + pal("green",
                   f"{meta['clean']} of {len(scanned)} repo(s) in "
                   f"'{names}' clean and current{churn_tail}."))
    else:
        safe_print("  " + pal("green",
                   f"{meta['clean']} repos clean and current{churn_tail}."))
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
        elif not meta.get("cloned_count"):
            # Ranked above the no-fetch caveat: "we scanned nothing" is
            # the more fundamental fact, and mentioning stale behind-
            # counts first implies a scan happened.
            safe_print("  Nothing was scanned -- see SETUP above.")
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
                "sets": r.get("sets") or [],
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
        if (g.get("churn_count") or 0) > 0:
            # Churn is not counted dirty for REPORTING, but the write
            # path stays conservative: a pull often touches the very
            # file the hook restamps, and git would refuse mid-fix.
            refused.append((r, "auto-stamp churn present -- refusing to "
                               "pull (will not stash)"))
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


#: QF-1: at most this many matched records get live verification per
#: query. Measured: `dazzle*` matches 68 records; uncapped that is a
#: scan wearing a query's clothes. Matches beyond the cap render from
#: cache, and the header says so.
QUERY_REFRESH_CAP = 8


def refresh_matched(records, matched, config, do_fetch=True,
                    cap=QUERY_REFRESH_CAP, fetch_timeout=60,
                    resolver=None):
    """Live truth for the matched slice only (QF-1, querylab-validated).

    Re-reads git state, install metadata, source version, and declared
    dist for matched records' NON-EXCLUDED checkouts -- refreshing a
    baks snapshot cost 0.9s of the measured 1.29s and told us nothing
    (querylab amendment 1). Fetches run through the same parallel
    machinery as a scan (amendment 3). Returns
    {refreshed, from_cache, fetch_failures} for the provenance header.

    IDENTITY is re-resolved too, not just git state: a remote repointed
    since the cache was written would otherwise keep reporting
    stale-remote-url from cached identity -- the card contradicting the
    fix the user had just made, which is the worst moment to be wrong.
    """
    picked, from_cache = [], []
    for key, r in matched.items():
        live_cos = [c for c in (r.get("checkouts") or [])
                    if not c.get("excluded") and c.get("path")
                    and os.path.isdir(str(c["path"]))]
        if not live_cos:
            continue        # not-cloned or gone: nothing to verify live
        if len(picked) >= cap:
            from_cache.append(key)
            continue
        picked.append((key, r, live_cos))

    failures = []
    if do_fetch and picked:
        # Only checkouts that HAVE a remote can be fetched. Without this
        # filter a remoteless repo (no origin at all -- a real category
        # the tool reports as no-upstream) was counted as a fetch
        # FAILURE, turning "nothing to fetch from" into "fetching went
        # wrong". The population scan has always filtered this way.
        allp = [c["path"] for _, _, cos in picked for c in cos
                if detect_remotes(c["path"])]
        if allp:
            failures = fetch_all(allp, Progress(enabled=False),
                                 timeout=fetch_timeout)

    live_installs = {}
    if picked:
        live_installs = {norm(i.get("path")): i for i in editable_installs()
                         if i.get("path")}

    for key, r, cos in picked:
        for c in cos:
            path = c["path"]
            upstream = get_upstream(path)
            behind, ahead = get_ahead_behind(path, upstream=upstream)
            counts = get_status_counts(path,
                                       churn_patterns=config.churn_files)
            c["git"] = {
                "branch": get_branch(path),
                "upstream": upstream,
                "ahead": ahead,
                "behind": behind,
                "dirty_count": counts["dirty_count"],
                "untracked_count": counts["untracked_count"],
                "churn_count": counts.get("churn_count", 0),
            }
            c["last_activity"] = get_last_commit_epoch(path)
            c["private"] = private_state(path)
        slugs, redirected, canonical = [], False, None
        for c in cos:
            o = next((x for x in detect_remotes(c["path"])
                      if x["name"] == "origin"), None)
            if not o:
                continue
            slug = o.get("slug") or parse_slug(o.get("fetch_url"))
            if not slug:
                continue
            if slug not in slugs:
                slugs.append(slug)
            info = resolver.resolve(slug) if resolver else None
            if info:
                canonical = canonical or info.get("full_name")
                redirected = redirected or bool(info.get("redirected"))
        if slugs:
            r["configured_slugs"] = slugs
            r["redirected"] = redirected
            if canonical:
                r["full_name"] = canonical
        for path in r.get("paths") or []:
            li = live_installs.get(norm(path))
            if li:
                r["installed"] = li
                r["source_version"] = read_source_version(path)
                name, source = read_declared_dist_name(path)
                if name:
                    r["declared_dist"] = name
                    r["declared_dist_source"] = source
        primary, reason = select_primary(r, config)
        r["primary"] = primary.get("path") if primary else None
        r["primary_reason"] = reason
        r["git"] = (primary or {}).get("git") or None
    return {"refreshed": [k for k, _, _ in picked],
            "from_cache": from_cache, "fetch_failures": failures}


def match_records(records, queries):
    """Records matching any query term, case-insensitive.

    A term with glob characters fnmatches; a plain term substring-matches.
    Candidates per record: canonical name, key, bare repo name, installed
    and declared dist names, and every checkout's directory basename --
    so `dazzlesum`, `DazzleTools/dazzlesum`, `dazzle-sum*`, and the name
    of the folder you are standing in all find the same record.
    """
    import fnmatch as _fn
    out = {}
    for key, r in records.items():
        cands = {key.lower()}
        if r.get("full_name"):
            full = r["full_name"].lower()
            cands.add(full)
            cands.add(full.split("/", 1)[-1])
        inst = r.get("installed") or {}
        if inst.get("name"):
            cands.add(str(inst["name"]).lower())
        if r.get("declared_dist"):
            cands.add(str(r["declared_dist"]).lower())
        for path in r.get("paths") or []:
            cands.add(os.path.basename(str(path).rstrip("\\/")).lower())
        for q in queries:
            ql = q.lower()
            if any(ch in ql for ch in "*?["):
                hit = any(_fn.fnmatch(c, ql) for c in cands)
            else:
                hit = any(ql in c for c in cands)
            if hit:
                out[key] = r
                break
    return out


def render_query(records, findings, queries, meta, pal=None, as_json=False,
                 stats=None):
    """The detail card: one repo, every axis. `pip show` for the ecosystem."""
    pal = pal or Palette(False)
    # In JSON mode stdout belongs to the document, exclusively: warnings
    # and provenance travel INSIDE the payload (meta) rather than being
    # printed above it. Printing them first made `--json > out.json`
    # produce a file that would not parse -- the machine-readable mode
    # emitting something no machine could read.
    if not as_json:
        for err in (meta or {}).get("errors") or []:
            safe_print(f"  WARNING     {err}")
    matched = match_records(records, queries)
    if not matched:
        if as_json:
            print(json.dumps({"schema": 1, "query": list(queries),
                              "meta": meta or {}, "matches": []},
                             indent=2, sort_keys=True, default=str))
            return 2
        safe_print(f"  no repo matches {', '.join(repr(q) for q in queries)}")
        safe_print("  (matching covers owner/repo names, dist names, and "
                   "checkout folder names; globs allowed)")
        return 2

    if as_json:
        print(json.dumps({"schema": 1, "query": list(queries),
                          "meta": meta or {},
                          "matches": list(matched.values())},
                         indent=2, sort_keys=True, default=str))
        return 0

    kinds_of = {}
    for kind in FINDING_ORDER:
        for r in findings.get(kind) or []:
            kinds_of.setdefault(r["key"], []).append(kind)

    shown = list(matched.values())[:10]
    for r in shown:
        name = r.get("full_name") or r["key"]
        safe_print("")
        safe_print("  " + pal.bold(name))
        slugs = [s for s in (r.get("configured_slugs") or [])
                 if s.lower() != (r.get("full_name") or "").lower()]
        if slugs:
            tag = " (redirected)" if r.get("redirected") else ""
            safe_print(f"    identity    configured as "
                       f"{', '.join(slugs)}{tag}")
        bits = []
        bits.append("in namespace" if r.get("in_namespace")
                    else "not in any listed namespace")
        if r.get("third_party"):
            bits.append("third-party upstream")
        if r.get("foreign"):
            bits.append("not ours")
        safe_print(f"    status      {'; '.join(bits)}")
        if r.get("sets"):
            safe_print(f"    sets        {', '.join(r['sets'])}")
        inst = r.get("installed") or {}
        if inst:
            safe_print(f"    install     {inst.get('name')} "
                       f"{inst.get('version')} (editable) at "
                       f"{inst.get('path')}")
        if r.get("source_version"):
            safe_print(f"    source      {r['source_version']}")
        if r.get("declared_dist"):
            safe_print(f"    declares    {r['declared_dist']} "
                       f"({r.get('declared_dist_source')})")
        if r.get("published"):
            owned = r.get("pypi_owned")
            note = ("" if owned else "  [NOT OURS -- name collision]"
                    if owned is False else "  [ownership unverified]")
            safe_print(f"    published   PyPI {r['published']}{note}")
        pstate = r.get("private_state")
        if pstate and pstate != "none":
            # Say what is true rather than grading it. "shared" alone
            # invited the question "shared with whom?" -- the answer is
            # always "this repo's own checkouts", so name them and the
            # count instead of using a word that implies more.
            stores = r.get("private_stores") or []
            live = len([c for c in (r.get("checkouts") or [])
                        if not c.get("excluded")])
            if pstate == "ok":
                line = (f"versioned -- all {live} checkouts use {stores[0]}"
                        if live > 1 and stores
                        else f"versioned -- {stores[0]}" if stores
                        else "versioned")
            elif pstate == "split":
                line = (f"versioned, but {len(stores)} separate stores; "
                        f"these checkouts do not use one")
            elif pstate == "unversioned":
                where = f" -- {stores[0]}" if len(stores) == 1 else ""
                line = f"no repo behind it (dz private-init){where}"
            elif pstate == "broken":
                line = "link target is missing"
            else:
                line = pstate
            safe_print(f"    private     {line}")
        checkouts = r.get("checkouts") or []
        if checkouts:
            prim = norm(r.get("primary") or "")
            safe_print(f"    checkouts   {len(checkouts)}"
                       + (f"  (primary: {r.get('primary_reason')})"
                          if r.get("primary") else
                          f"  ({r.get('primary_reason')})"))
            for c in checkouts:
                g = c.get("git") or {}
                state = []
                if g.get("branch"):
                    state.append(g["branch"])
                if g.get("upstream"):
                    state.append(f"-> {g['upstream']}")
                else:
                    state.append("no upstream")
                for k, label in (("ahead", "ahead"), ("behind", "behind"),
                                 ("dirty_count", "dirty"),
                                 ("untracked_count", "untracked"),
                                 ("churn_count", "churn")):
                    if g.get(k):
                        state.append(f"{g[k]} {label}")
                mark = "*" if norm(c.get("path")) == prim and prim else " "
                excl = "  [excluded]" if c.get("excluded") else ""
                safe_print(f"      {mark} {c.get('path')}{excl}")
                safe_print(f"          {', '.join(state)}")
        elif r.get("paths"):
            safe_print(f"    paths       {'; '.join(r['paths'])}")
        if r.get("excluded"):
            safe_print(f"    excluded    {r['excluded']}")
        kinds = kinds_of.get(r["key"]) or []
        if kinds:
            coloured = [pal(FINDING_COLOURS.get(k, "reset"), k)
                        for k in kinds]
            safe_print(f"    findings    {', '.join(coloured)}")
        else:
            safe_print("    findings    "
                       + pal("green", "none -- not classified this run"))
    if len(matched) > 10:
        rest = [r.get("full_name") or r["key"]
                for r in list(matched.values())[10:]]
        safe_print("")
        safe_print(f"  ... and {len(matched) - 10} more match(es): "
                   + ", ".join(rest[:15]))
    if stats:
        n = len(matched)
        bits = [f"{n} match{'es' if n != 1 else ''} of "
                f"{len(records)} repos"]
        mode = stats.get("mode")
        if mode == "live":
            r = stats.get("refreshed", 0)
            bits.append(f"{r} verified live just now" if r
                        else "nothing to verify live")
        elif mode == "local":
            bits.append("re-read locally (no fetch; behind-counts from "
                        "last fetch)")
        elif mode == "replay":
            bits.append("replayed from cache")
        elif mode == "fresh":
            bits.append("from a fresh full scan")
        if stats.get("fetch_failures"):
            bits.append(f"{stats['fetch_failures']} fetch failure(s)")
        if stats.get("beyond_cap"):
            bits.append(f"{stats['beyond_cap']} beyond the live-refresh "
                        f"cap shown from cache")
        if stats.get("t_start") is not None:
            bits.append(f"{time.perf_counter() - stats['t_start']:.2f}s")
        safe_print("")
        safe_print("  " + pal("grey", "; ".join(bits)))
    safe_print("")
    return 0


def _print_timing(verbose, t_start, phases=None):
    """Operation timing at -v; per-phase breakdown at -vv (stderr, so
    --json stdout stays clean). Deeper -vvv levels are reserved."""
    if not verbose:
        return
    total = time.perf_counter() - t_start
    line = f"[timing] total {total:.2f}s"
    if verbose >= 2 and phases:
        parts = ", ".join(f"{name} {dt:.2f}s" for name, dt in phases)
        line += f"  ({parts})"
    print(line, file=sys.stderr)


def build_parser():
    p = argparse.ArgumentParser(
        prog="dz dazzle-update",
        description="Ecosystem-wide update/status scanner across every "
                    "namespace we own.",
        epilog=(
            "examples:\n"
            "  dz dazzle-update                 Report what needs attention\n"
            "  dz dazzle-update dazzlesum       Everything about one repo\n"
            "  dz dazzle-update \"wtf-*\"         Same, by glob\n"
            "  dz dazzle-update --published     Also compare against PyPI\n"
            "  dz dazzle-update --json          Machine-readable output\n"
            "  dz dazzle-update --fix --dry-run Show what --fix would do\n"
            "  dz dazzle-update --scope DazzleLib\n"
            "\n"
            "first run on a new machine:\n"
            "  dz dazzle-update --init-config   Write a config to edit\n"
            "  dz dazzle-update --root D:/src   Scan elsewhere for one run\n"
            "  Identity is derived from `gh` (authenticate first); of the\n"
            "  config, only 'roots' is machine-specific -- the rest travels.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("query", nargs="*", metavar="REPO",
                   help="Show a detail card for repos matching these "
                        "names or globs, across every axis the scanner "
                        "knows (identity, checkouts, install, PyPI, sets, "
                        "findings). Read-only; instant with --cached.")
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
    p.add_argument("--only-set", action="append", default=None,
                   metavar="NAME",
                   help="Show only repos in this working set (repeatable). "
                        "Sets are defined in the config; --list-sets shows "
                        "them. What the lens hides is counted, never silent.")
    p.add_argument("--list-sets", action="store_true",
                   help="List configured working sets, then exit")
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
    t_start = time.perf_counter()
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

    # Working sets: parsed early so definition problems surface as
    # warnings in every path, cached replay included.
    set_defs, set_warns = load_sets(cfg.get("sets"))
    errors.extend(set_warns)

    if args.list_sets:
        safe_print("")
        if cfg_err:
            safe_print(f"  WARNING     {cfg_err}")
        if not set_defs:
            safe_print("  no sets configured.")
            safe_print("  add a 'sets' mapping to your config; --init-config "
                       "writes worked examples.")
            return 0
        safe_print("  configured working sets (membership needs a scan; "
                   "these are the rules):")
        for s in set_defs:
            safe_print(f"    {s.name}")
            if s.namespaces:
                safe_print(f"      namespaces: {', '.join(s.namespaces)}")
            for entry in s.include:
                safe_print(f"      include:    {entry}")
            if s.exclude:
                safe_print(f"      exclude:    {', '.join(s.exclude)}")
            dec = ("yes -- kit sources and tool requirements count"
                   if s.declared else "no")
            safe_print(f"      declared:   {dec}")
        safe_print("")
        return 0

    if args.query and args.fix:
        safe_print("  the detail view is read-only; drop the repo name to "
                   "use --fix, or run --fix with --only/--only-set to scope it")
        return 2

    if args.only_set:
        defined = {s.name.lower() for s in set_defs}
        bad = [n for n in args.only_set if n.lower() not in defined]
        if bad:
            safe_print(f"  unknown set(s): {', '.join(bad)}")
            if set_defs:
                safe_print("  configured sets: "
                           + ", ".join(s.name for s in set_defs))
            else:
                safe_print("  no sets configured -- add a 'sets' mapping to "
                           "your config (--init-config writes examples)")
            return 2

    sort_mode = args.sort or cfg.get("sort") or "newest"
    if sort_mode not in SORT_MODES:
        errors.append(f"config 'sort': unknown mode {sort_mode!r}; using newest")
        sort_mode = "newest"

    report_order, bad_order = apply_order(cfg.get("order"))
    if bad_order:
        errors.append("config 'order': unknown kind(s) ignored: "
                      + ", ".join(bad_order))

    # QF-2 fast path: a query with a cache present answers from the
    # index, verifying only the matches live -- no namespace listing, no
    # filesystem walk, no fleet fetch. Explicit scope flags (--root,
    # --scope, --cached, --no-cache) name a different pipeline and fall
    # through to it.
    if (args.query and not args.cached and not args.no_cache
            and not args.root and not args.scope):
        t_load0 = time.perf_counter()
        rec, cmeta, cage, cerr = scancache.load(
            path=cfg.get("cache_path"), max_age=None)
        t_load = time.perf_counter() - t_load0
        if not cerr and rec:
            excludes = (list(cfg["exclude"]) if cfg.get("exclude_replace")
                        else DEFAULT_EXCLUDES + list(cfg.get("exclude") or []))
            lite = EcosystemConfig(
                namespaces=[],
                personal_namespace=cfg.get("personal_namespace"),
                excludes=excludes,
                member_prefixes=tuple(cfg.get("member_prefixes")
                                      or ("dazzle",)),
                personal_allow=cfg.get("personal_allow") or (),
                include=cfg.get("include") or (),
                local_only_branches=cfg.get("local_only_branches") or (),
                churn_files=cfg.get("churn_files") or (),
                churn_files_replace=bool(cfg.get("churn_files_replace")),
                private_check=cfg.get("private_check", "auto"),
                private_ignore=cfg.get("private_ignore") or ())
            t_m0 = time.perf_counter()
            matched = match_records(rec, args.query)
            t_match = time.perf_counter() - t_m0
            t_r0 = time.perf_counter()
            info = refresh_matched(
                rec, matched, lite, do_fetch=not args.no_fetch,
                fetch_timeout=args.fetch_timeout
                or cfg.get("fetch_timeout", 60),
                resolver=IdentityResolver(
                    cache={} if args.no_cache
                    else load_cache(_cache_path())))
            t_refresh = time.perf_counter() - t_r0
            t_c0 = time.perf_counter()
            set_declared = (declared_members()
                            if any(s.declared for s in set_defs) else None)
            annotate_sets(rec, set_defs, set_declared)
            findings = classify(rec, lite, sort_mode=sort_mode)
            t_classify = time.perf_counter() - t_c0

            meta = dict(cmeta)
            merged, seen = [], set()
            for e in (list(meta.get("errors") or []) + errors):
                if e not in seen:
                    seen.add(e)
                    merged.append(e)
            # QF-4: the cache's SCOPE travels with it (a narrowed-config
            # scan made an org repo read "not ours"); a query must say
            # when its population was written under a different config.
            if cmeta.get("narrowed"):
                merged.append(
                    "population cache was written by a --root-narrowed "
                    f"scan ({', '.join(cmeta.get('roots') or [])}); repos "
                    "outside that root are absent from this answer -- "
                    "run a full scan to rebuild the index")
            cached_cfg = cmeta.get("config")
            if (cached_cfg or cfg_path) and cached_cfg != cfg_path:
                merged.append(
                    f"population cache was written under config "
                    f"{cached_cfg or '(defaults)'}; this run uses "
                    f"{cfg_path or '(defaults)'} -- population scope "
                    f"may differ")
            meta["errors"] = merged

            pal = make_palette(args.color)
            if not args.json:
                cfg_note = f"; config {cached_cfg}" if cached_cfg else ""
                safe_print("")
                safe_print(
                    f"  (population from cache, "
                    f"{scancache.format_age(cage)} old; scan covered "
                    f"{meta.get('namespace_count', '?')} namespace(s), "
                    f"{meta.get('org_repo_count', '?')} namespace repos"
                    f"{cfg_note})")
            rc = render_query(
                rec, findings, args.query, meta, pal=pal,
                as_json=args.json,
                stats={"mode": "local" if args.no_fetch else "live",
                       "refreshed": len(info["refreshed"]),
                       "beyond_cap": len(info["from_cache"]),
                       "fetch_failures": len(info["fetch_failures"]),
                       "t_start": t_start})
            _print_timing(args.verbose, t_start,
                          [("cache", t_load), ("match", t_match),
                           ("refresh", t_refresh), ("classify", t_classify)])
            return rc
        errors.append("no scan cache yet -- this first query performs a "
                      "full scan; later queries answer from the index "
                      "in about a second")

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
        local_only_branches=cfg.get("local_only_branches") or (),
        churn_files=cfg.get("churn_files") or (),
        churn_files_replace=bool(cfg.get("churn_files_replace")),
        private_check=cfg.get("private_check", "auto"),
        private_ignore=cfg.get("private_ignore") or ())

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
        # Cached errors describe the replayed DATA; current-run errors
        # (config problems, set-definition warnings) describe THIS run
        # and were silently dropped here -- a malformed set warned on a
        # fresh scan and said nothing on replay, which is exactly the
        # silent-degradation this tool exists to refuse. Dedupe keeps
        # the same-config case from saying everything twice.
        merged, seen = [], set()
        for e in (list(meta.get("errors") or []) + errors):
            if e not in seen:
                seen.add(e)
                merged.append(e)
        meta["errors"] = merged + [
            f"REPLAYED from cache, {scancache.format_age(cached_age)} old -- "
            "remote state may have changed since"]
        # The Sources line must name the config governing THIS replay
        # (lens, order, visibility) -- showing whichever file produced
        # the cached scan sent a reader to the wrong config entirely.
        meta["config"] = cfg_path
        findings = classify(records, EcosystemConfig(),
                            sort_mode=args.sort or cfg.get("sort") or "newest")
        # Sets are re-derived on replay, never trusted from the cache:
        # the config may have changed since the scan was written.
        declared = (declared_members()
                    if any(s.declared for s in set_defs) else None)
        annotate_sets(records, set_defs, declared)
        if args.only_set:
            findings, hidden = apply_set_lens(findings, args.only_set)
            meta["set_lens"] = list(args.only_set)
            meta["set_hidden"] = hidden
        meta["churn_repos"] = count_churn_repos(records)
        meta["churn_files"] = config.churn_files
        meta["clean"] = clean_count(records, findings)
        if args.query:
            pal = make_palette(args.color)
            safe_print("")
            # Provenance matters MORE for a single-repo card than for the
            # full report: "not in any listed namespace" is a statement
            # about the SCAN's scope, and a card that omits the scope
            # presents a narrowed answer as a global one. Live case: a
            # 1-namespace scan cached under a scoped config made
            # DazzleTools/dazzlesum read "not ours".
            safe_print(f"  (from cache, "
                       f"{scancache.format_age(cached_age)} old; scan "
                       f"covered {meta.get('namespace_count', '?')} "
                       f"namespace(s), {meta.get('org_repo_count', '?')} "
                       f"namespace repos"
                       + (f"; config {meta.get('config')}"
                          if meta.get("config") else "") + ")")
            rc = render_query(records, findings, args.query, meta,
                              pal=pal, as_json=args.json,
                              stats={"mode": "replay", "t_start": t_start})
            _print_timing(args.verbose, t_start)
            return rc
        meta["visible_kinds"] = _visible_kinds(only_kinds, skip_kinds,
                                               show_clean=args.all,
                                               drop_not_cloned=bool(args.root))
        meta["order"] = apply_order(cfg.get("order"))[0] if cfg else meta.get("order")
        pal = make_palette(args.color)
        if args.json:
            rc = render_json(records, findings, meta)
        else:
            rc = render_text(records, findings, meta, pal=pal)
        _print_timing(args.verbose, t_start)
        return rc

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

    set_declared = (declared_members()
                    if any(s.declared for s in set_defs) else None)
    annotate_sets(records, set_defs, set_declared)
    set_lens, set_hidden = None, 0
    if args.only_set:
        findings, set_hidden = apply_set_lens(findings, args.only_set)
        set_lens = list(args.only_set)
        # A set whose body is a namespace cannot see its uncloned members
        # when the org listing failed. Under a lens that incompleteness
        # deceives, so it must be said out loud, per set.
        if not gh_ok:
            wanted = {n.lower() for n in args.only_set}
            for s in set_defs:
                if s.name.lower() in wanted and s.namespaces:
                    errors.append(
                        f"set '{s.name}': namespace listing unavailable -- "
                        f"members not cloned locally cannot be detected")

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
        "set_lens": set_lens,
        "set_hidden": set_hidden,
        "churn_repos": count_churn_repos(records),
        "churn_files": config.churn_files,
        "stale_behind": bool(args.no_fetch) or not cfg.get("fetch", True),
    }

    ok, cache_err = (True, None)
    if cfg.get("cache_write", True) and not narrowed:
        ok, cache_err = scancache.save(records, meta,
                                       path=cfg.get("cache_path"))
    elif narrowed and args.verbose:
        # A --root run answers a narrower question than the cache exists
        # to answer. Overwriting the shared index with it silently
        # replaced a 184-repo population with 124 and made later queries
        # report against a partial world -- caught only because a repo
        # count moved. Narrowed scans are complete for their root and
        # wrong as an index, so they are not written.
        safe_print("  (--root narrows the scan; not overwriting the "
                   "shared scan cache)")
    if not ok and args.verbose:
        errors.append(f"could not cache scan: {cache_err}")

    pal = make_palette(args.color)
    if args.query:
        rc = render_query(records, findings, args.query, meta,
                          pal=pal, as_json=args.json,
                          stats={"mode": "fresh", "t_start": t_start})
        _print_timing(args.verbose, t_start)
        return rc
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
        rc = render_json(records, findings, meta)
    else:
        rc = render_text(records, findings, meta, pal=pal)
    _print_timing(args.verbose, t_start)
    return rc


if __name__ == "__main__":
    sys.exit(main())
