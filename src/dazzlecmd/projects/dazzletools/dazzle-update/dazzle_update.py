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
    pypi_version,
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


def _visible_kinds(only_kinds, skip_kinds, show_clean=False):
    """Which finding kinds to render. None means 'all except clean'.

    'clean' is opt-in: on a 150-repo box it is the longest section and
    says nothing actionable. But it must be REACHABLE, because otherwise
    there is no way to tell "scanned and fine" from "never scanned" --
    which is exactly the doubt a scanned inventory should remove.
    """
    if only_kinds:
        return [k for k in only_kinds if k not in (skip_kinds or [])]
    base = [k for k in FINDING_ORDER if k != "clean" or show_clean]
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


def _fmt_repo(r):
    name = _display_name(r)
    g = r["git"] or {}
    bits = []
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
    for err in meta.get("errors", []):
        safe_print(f"  WARNING     {err}")

    # Headline first. The question most runs are asking is "what do I need
    # to pull?", and burying it under risk-ordered sections makes the tool
    # feel like it answers a different question than the one you asked.
    counts = {k: len(findings.get(k) or []) for k in FINDING_ORDER}
    to_pull = counts.get("behind-upstream", 0)
    headline = (pal("red", f"{to_pull} to pull") if to_pull
                else pal("green", "nothing to pull"))
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
            raw, detail = _fmt_repo(r)
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


def apply_fixes(findings, dry_run=False):
    """The two provably-safe operations. Everything else refuses.

    Refuses on any dirty tree rather than stashing: auto-stashing is a
    well-known way to lose work, and the judgment of what to do with
    in-progress changes belongs to a human.
    """
    actions, refused = [], []

    for r in findings.get("behind-upstream") or []:
        g = r["git"] or {}
        if (g.get("dirty_count") or 0) > 0 or (g.get("untracked_count") or 0) > 0:
            refused.append((r, "dirty tree -- refusing to pull (will not stash)"))
            continue
        if (g.get("ahead") or 0) > 0:
            refused.append((r, "diverged -- needs a merge, not a fast-forward"))
            continue
        actions.append(("pull", r))

    for r in findings.get("stale-install-metadata") or []:
        actions.append(("reinstall", r))

    for kind in ("unpushed", "no-upstream", "stale-remote-url"):
        for r in findings.get(kind) or []:
            refused.append((r, f"{kind}: reported only -- needs your decision"))

    # dazzlecmd is updated LAST: dz runs from an editable install of it,
    # so pulling it mid-run swaps source under the running process.
    def is_self(rec):
        return "dazzlecmd" in (rec["full_name"] or rec["key"]).lower()
    actions.sort(key=lambda a: is_self(a[1]))

    for verb, r in actions:
        target = r["paths"][0] if r["paths"] else None
        if not target:
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
        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        status = "ok" if res.returncode == 0 else "FAILED"
        safe_print(f"    {label}: {verb} {status}")
        if res.returncode != 0:
            safe_print(f"      {(res.stderr or '').strip().splitlines()[:1]}")

    if refused:
        safe_print("")
        safe_print("  REFUSED -- reported, not acted on:")
        for r, why in refused:
            safe_print(f"    {(r['full_name'] or r['key']):<38} {why}")
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

    gh_ok, gh_detail = gh_status()
    namespaces, ns_err = ([], None)
    if cfg.get("namespaces"):
        namespaces = list(cfg["namespaces"])          # explicit override
    elif gh_ok:
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
        include=cfg.get("include") or ())

    cache = {} if args.no_cache else load_cache(_cache_path())
    resolver = IdentityResolver(cache=cache)

    org_repos = []
    for ns in namespaces + ([personal] if personal else []):
        repos, err = list_org_repos(ns)
        if err:
            errors.append(err)
        for entry in repos:
            org_repos.append({"full_name": entry.get("nameWithOwner")})

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
                                               show_clean=args.all)
        meta["order"] = apply_order(cfg.get("order"))[0] if cfg else meta.get("order")
        pal = make_palette(args.color)
        if args.json:
            return render_json(records, findings, meta)
        return render_text(records, findings, meta, pal=pal)

    progress = Progress(enabled=not args.no_progress, verbose=args.verbose)
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
    installs = editable_installs()

    source_versions = {}
    for inst in installs:
        p = inst.get("path")
        if p and os.path.isdir(str(p)):
            v = read_source_version(p)
            if v:
                source_versions[norm(p)] = v

    published, published_detail = {}, "skipped -- pass --published"
    if args.published or cfg.get("published"):
        failures = 0
        for inst in installs:
            v, err = pypi_version(inst["name"])
            if err:
                failures += 1
            elif v:
                published[inst["name"].lower()] = v
        published_detail = f"{len(published)} resolved"
        if failures:
            published_detail += f", {failures} failed"

    if not args.no_cache:
        save_cache(_cache_path(), resolver.cache)

    records = join(org_repos, local, installs, config,
                   source_versions=source_versions, published=published)
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
                                        show_clean=args.all),
        "order": report_order,
        "sort": sort_mode,
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
        safe_print("  APPLYING FIXES" + (" (dry run)" if args.dry_run else ""))
        return apply_fixes(findings, dry_run=args.dry_run)
    if args.json:
        return render_json(records, findings, meta)
    return render_text(records, findings, meta, pal=pal)


if __name__ == "__main__":
    sys.exit(main())
