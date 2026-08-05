"""Ecosystem join -- four discovery views reconciled into one record set.

The engine behind dz dazzle-update. Its whole job is to key every repo by
CANONICAL identity and then report the asymmetries between what the orgs
say, what pip has installed, what is on disk, and what PyPI publishes.

The deltas are the findings:

    in an org, not on disk            -> not-cloned
    on disk, no remote at all         -> no-upstream (exists nowhere else)
    configured URL != resolved name   -> stale-remote-url
    installed version < source tree   -> stale-install-metadata
    installed version < PyPI          -> install-behind-published
    installed path missing on disk    -> source-missing
    commits/changes not pushed        -> unpushed / dirty

Ordering is deliberate: outbound drift sorts first, because it is the
only class nobody else can see. A repo that is behind can be fixed by
anyone with the remote; a repo that is ahead holds work that exists on
exactly one machine.
"""

import fnmatch
import os
import re

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _repo_common.private_state import (  # noqa: E402
    PRIVATE_BROKEN,
    PRIVATE_NONE,
    PRIVATE_SPLIT,
    PRIVATE_UNVERSIONED,
    has_private_material,
    judge_private,
)


# The order here IS the report order, and it is ordered by WHAT THE READER
# SHOULD DO, not by abstract severity:
#
#   1. behind-upstream    material to merge locally -- the question most
#                         runs are actually asking
#   2. source-missing     a broken install; imports may already be failing
#   3. stale-install      you are running older code than your own tree
#   4. unpushed           work to share back before it is stranded here
#   5. stale-remote-url   structural: the URL no longer names the repo
#   6. no-upstream        nothing to push TO; needs a decision, not an action
#   7. dirty              large, expected, and mostly already known to you
#   8. not-cloned         purely informational -- nothing here is at risk
#
# Overridable per user via the `order` config key; see apply_order().
FINDING_ORDER = [
    "behind-upstream",
    "source-missing",
    "stale-dist-name",
    "pypi-name-collision",
    "stale-install-metadata",
    "install-behind-published",
    "unpushed",
    "stale-remote-url",
    "vendored-drift",
    "no-upstream",
    "private-uninitialized",
    "dirty",
    "not-cloned",
    "excluded-by-policy",
    "clean",
]

# Short names accepted by --only / --skip.
FINDING_ALIASES = {
    "behind": "behind-upstream",
    "pull": "behind-upstream",
    "broken": "source-missing",
    "stale": "stale-install-metadata",
    "install": "stale-install-metadata",
    "published": "install-behind-published",
    "push": "unpushed",
    "ahead": "unpushed",
    "remote": "stale-remote-url",
    "url": "stale-remote-url",
    "vendored": "vendored-drift",
    "unbacked": "no-upstream",
    "private": "private-uninitialized",
    "privinit": "private-uninitialized",
    "missing": "not-cloned",
    "clone": "not-cloned",
    "excluded": "excluded-by-policy",
    "renamed": "stale-dist-name",
    "dist": "stale-dist-name",
    "collision": "pypi-name-collision",
    "ok": "clean",
    "current": "clean",
}


def apply_order(configured):
    """Build the report order from a user-supplied (possibly partial) list.

    Semantics are deliberately PARTIAL: whatever you name goes first, in
    your order, and everything you did not name follows in the built-in
    order. A config listing three kinds must not silently hide the other
    eight -- hiding is what --only and --skip are for, and conflating
    "show me this first" with "show me only this" is how a config quietly
    starts lying about the state of your machine.

    Returns (order, unknown_names).
    """
    if not configured:
        return list(FINDING_ORDER), []
    kinds, unknown = resolve_kinds(configured)
    tail = [k for k in FINDING_ORDER if k not in kinds]
    return kinds + tail, unknown


def resolve_kinds(names):
    """Map user-facing names/aliases to finding keys. Returns (kinds, bad)."""
    kinds, bad = [], []
    for raw in names or []:
        key = raw.strip().lower()
        key = FINDING_ALIASES.get(key, key)
        if key in FINDING_ORDER:
            if key not in kinds:
                kinds.append(key)
        else:
            bad.append(raw)
    return kinds, bad

FINDING_LABELS = {
    "unpushed": "NEEDS PUSH -- work that exists only on this box",
    "no-upstream": "NO UPSTREAM -- not backed up anywhere",
    "source-missing": "BROKEN INSTALL -- editable path does not exist",
    "stale-dist-name": ("DIST NAME MISMATCH -- installed under a name the "
                        "repo does not declare"),
    # Wording note: say what is true of the PYPI PROJECT, never of the
    # local checkout. "not ours" reads as "this repo is junk", which has
    # led to archiving a fork that held unpushed work. The checkout may
    # be entirely ours -- it is the PyPI NAME that belongs elsewhere.
    "pypi-name-collision": ("PYPI NAME COLLISION -- this PyPI name belongs to "
                            "a different project; installing would OVERWRITE "
                            "this checkout, not update it"),
    "stale-install-metadata": "STALE INSTALL -- metadata behind its own source",
    "install-behind-published": "BEHIND PUBLISHED -- PyPI is ahead of this install",
    "stale-remote-url": "STALE REMOTE URL -- fetching through a transfer redirect",
    "behind-upstream": "BEHIND UPSTREAM -- a pull would advance these",
    "not-cloned": "NOT CLONED -- in a namespace, absent here",
    "private-uninitialized": ("PRIVATE NOT INITIALIZED -- private material "
                              "with no repo behind it (dz private-init)"),
    "dirty": "DIRTY -- uncommitted changes",
    "vendored-drift": "VENDORED DRIFT -- embedded copy differs from upstream",
    "excluded-by-policy": "EXCLUDED BY POLICY",
    "clean": "CLEAN -- scanned, nothing to do",
}

# How to order rows WITHIN a section. Recency beats alphabetical at this
# scale: with 150 repos, what you touched this week is what you mean.
SORT_MODES = ("newest", "oldest", "name")


def sort_records(items, mode="newest"):
    """Sort rows within a section: ours first, foreign last.

    Repos we do not own still belong in the report -- a fork you track
    genuinely can be behind, and hiding that is worse than ranking it.
    But they must not crowd the top of BEHIND UPSTREAM, which answers
    "what should I merge": ostris/ai-toolkit at 491 behind and
    thu-ml/SageAttention at 95 are upstreams nobody here is going to
    pull, and they pushed our own one-commit-behind repos off the eye.

    So the primary key is ownership, and the chosen mode orders WITHIN
    each group rather than across the whole list.
    """
    def within(r):
        if mode == "name":
            return (r["full_name"] or r["key"]).lower()
        # Negate for recency so a single ascending sort handles both
        # tiers; records with no date sort last within their group.
        act = r.get("last_activity")
        if mode == "oldest":
            return (act is None, act or 0)
        return (act is None, -(act or 0))

    return sorted(items, key=lambda r: (bool(r.get("foreign")), within(r)))

# Upstreams we track but do not own. Redirects here are informational:
# they are other projects moving org, not our inventory drifting.
THIRD_PARTY_OWNERS = {
    "comfy-org", "comfyanonymous", "triton-lang", "openai",
    "huggingface", "pytorch", "microsoft", "nvidia",
}

# Branches that are local-only BY DESIGN. repokit projects keep `private`
# unpushed on purpose ("The private branch is LOCAL ONLY"), so reporting it
# as unbacked-up is a false positive that buries the real findings.
LOCAL_ONLY_BRANCHES = {"private"}

# Files whose modifications are machine-made churn, not work. The repokit
# git hook restamps `_version.py` build metadata after every commit, so on
# a repokit-heavy machine a scan lists repos as DIRTY whose only change is
# the tooling talking to itself -- which trains the reader to ignore the
# dirty section. Matched against porcelain paths AND basenames.
#
# Both entries are MEASURED, not guessed (2026-08-02 survey of every
# dirty repo on a real machine): `_version.py` is the current repokit
# stamp; `version.py` is the same stamp under the older convention the
# DazzleNodes-era projects still use -- 19 dirty files, every sampled
# diff a pure `__version__` restamp. Nothing else version-ish observed
# (test_version.py, update-version.sh, version.h) is a stamp, so
# nothing else is default-filtered.
DEFAULT_CHURN_FILES = ["_version.py", "version.py"]

DEFAULT_EXCLUDES = [
    # Archive trees and dated snapshots. Patterns are deliberately narrow.
    # A bare "*backup*" also matches legitimate names such as
    # DazzleML/Claude-Session-Backup, and "*sysdiagnose*" matches the
    # public sysdiagnose-public repo -- both would silently hide live work.
    "*/git-repokit-old-versions/*",
    "*/baks/*",
    "*/previous-unc-tests/*",
    "*- Copy*",
    "*.bak",
    "*.bak/*",
    "*-bak",
    "*backup-20*",
    "*_BACKUP_*",
    "*_backup_*",
    "*.backup-*",
    "*/old-material-backup/*",
    "*_LAST-WORKING*",
    "*_pre-deleting-*",
    "*_orig",
    "*_borked*",
    # Repos governed by their own deliberate workflow (GT-24).
    "*/amdead",
    "*/amdead-*",
    "*/amdead.*",
    "*/amdtoy-*",
    "*/SYSDIAGNOSE",
    "*/SYSDIAGNOSE_*",
]


def select_primary(record, config=None):
    """Choose which checkout a repo-scoped finding should speak for.

    A canonical identity can span many working copies -- worktrees, the
    <project>/github + <project>/local convention, dated snapshots. On
    one real machine 22 of 142 identities spanned several paths, one of
    them 17. Picking whichever was discovered first meant picking
    alphabetically, which is not a reason, and it was wrong in 7 of the 9
    cases where pip already recorded the answer.

    Precedence, first match wins:

      1. The path pip records as the editable install. Pip answers "what
         does this environment actually run", which is the question. This
         beats rule 2 deliberately: for two real repos the installed
         checkout has NO upstream while a sibling has one, and the tidier
         sibling is not the one being executed.
      2. A non-excluded checkout whose HEAD tracks an upstream.
      3. A non-excluded checkout on a branch that looks default-ish.
      4. The only non-excluded checkout, if exactly one remains.
      5. No primary. The caller must report ambiguity and REFUSE to act
         -- guessing here is how a fast-forward lands on someone's
         feature branch.

    Returns (checkout_dict_or_None, reason_str).
    """
    checkouts = [c for c in (record.get("checkouts") or []) if c]
    if not checkouts:
        return None, "no checkouts"
    if len(checkouts) == 1:
        return checkouts[0], "only checkout"

    excluded = {norm(p) for p in (record.get("excluded_paths") or [])}
    live = [c for c in checkouts if norm(c.get("path")) not in excluded] or checkouts

    inst = record.get("installed") or {}
    inst_path = norm(inst.get("path"))
    if inst_path:
        for c in live:
            if norm(c.get("path")) == inst_path:
                return c, "pip-installed checkout"

    tracking = [c for c in live if (c.get("git") or {}).get("upstream")]
    if len(tracking) == 1:
        return tracking[0], "only checkout with an upstream"
    if tracking:
        # Rule 3 must be UNIQUE to count as a reason. An earlier version
        # returned the first default-branch match it walked, which is
        # directory order -- reintroducing, one rule deeper, exactly the
        # arbitrary pick this function exists to eliminate. The live
        # dazzlecmd layout has THREE tracking checkouts on `main`
        # (github, "github - Copy", github.2026.6.21) and was saved only
        # because pip matched at rule 1.
        default_ish = [
            c for c in tracking
            if ((c.get("git") or {}).get("branch") or "").lower()
            in DEFAULT_BRANCH_NAMES
        ]
        if len(default_ish) == 1:
            branch = (default_ish[0].get("git") or {}).get("branch")
            return default_ish[0], f"only tracking checkout on {branch}"
        if len(default_ish) > 1:
            return None, (f"{len(default_ish)} tracking checkouts on a default "
                          f"branch -- ambiguous, refusing to guess")
        return None, f"{len(tracking)} tracking checkouts, none on a default branch"

    if len(live) == 1:
        return live[0], "only non-excluded checkout"
    return None, f"{len(live)} checkouts, none installed or tracking"


#: Branch names that suggest "the main line of development".
DEFAULT_BRANCH_NAMES = {"main", "master", "trunk", "develop", "dev"}


def _norm_dist(name):
    """PEP 503 dist-name normalization (local copy to avoid an import cycle)."""
    if not name:
        return ""
    return re.sub(r'[-_.]+', '-', str(name)).strip().lower()


def norm(path):
    """Case- and separator-normalized absolute path, for comparison."""
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(str(path)))


class EcosystemConfig:
    """Scope rules. Namespaces are DERIVED, never hardcoded.

    `personal_namespace` is enumerated like any other namespace but,
    unlike the orgs, needs a membership predicate: it also holds repos
    that are plainly outside the ecosystem.
    """

    def __init__(self, namespaces=None, personal_namespace=None,
                 excludes=None, roots=None, member_prefixes=("dazzle",),
                 personal_allow=(), include=(), local_only_branches=(),
                 churn_files=None, churn_files_replace=False,
                 private_check="auto", private_ignore=()):
        self.namespaces = list(namespaces or [])
        self.personal_namespace = personal_namespace
        self.excludes = list(excludes if excludes is not None else DEFAULT_EXCLUDES)
        self.roots = list(roots or [])
        self.member_prefixes = tuple(member_prefixes)
        self.personal_allow = {s.lower() for s in personal_allow}
        self.include = list(include or [])
        # Branches that are unpushed BY DESIGN. `private` is the repokit
        # convention; a project may add its own -- e.g. a vendor-disclosure
        # branch that must never reach a public remote. Reporting those as
        # "needs push" is not merely noise, it nudges toward publishing
        # something that must not be published.
        self.local_only_branches = (
            LOCAL_ONLY_BRANCHES | {b.strip().lower()
                                   for b in (local_only_branches or [])
                                   if b and b.strip()})
        # Files whose dirt is machine churn, not work. Merged with the
        # built-in default; `churn_files_replace` uses ONLY the configured
        # list (set it true with an empty list to disable filtering for a
        # project whose _version.py is hand-maintained).
        base = [] if churn_files_replace else list(DEFAULT_CHURN_FILES)
        self.churn_files = base + [str(c) for c in (churn_files or []) if c]
        self.private_check = private_check
        self.private_ignore = [str(g) for g in (private_ignore or []) if g]

    def private_axis_enabled(self, records):
        """Is the private/ convention in use on this machine?

        "auto" derives the answer instead of asking: if no repo anywhere
        has a VERSIONED private store, the convention is not in use here
        and the axis stays entirely silent -- no tags, no findings, no
        setting to discover. Same reasoning as deriving namespaces
        rather than hardcoding them.
        """
        if self.private_check is True:
            return True
        if self.private_check is False:
            return False
        return any(
            (c.get("private") or {}).get("versioned")
            for r in records.values()
            for c in (r.get("checkouts") or []))

    def private_ignored(self, full_name):
        if not full_name or not self.private_ignore:
            return False
        n = str(full_name).lower()
        return any(fnmatch.fnmatch(n, g.lower()) for g in self.private_ignore)

    def is_local_only_branch(self, branch):
        return bool(branch) and branch.strip().lower() in self.local_only_branches

    def is_excluded(self, path):
        """True when a path matches an exclusion pattern.

        `include` wins over `exclude`, so a user can keep one repo out of
        a broad archive pattern without rewriting the pattern.
        """
        if not path:
            return False
        p = str(path).replace("\\", "/")
        for pat in self.include:
            if fnmatch.fnmatch(p, pat.replace("\\", "/")):
                return False
        for pat in self.excludes:
            if fnmatch.fnmatch(p, pat.replace("\\", "/")):
                return True
        return False

    def is_member(self, full_name, installed=False, backs_a_tool=False):
        """Ecosystem membership for a canonical OWNER/REPO.

        Org repos are members wholesale. The personal namespace needs a
        predicate: the `dazzle-` rename marks an adopted fork, and being
        installed or backing a dz tool are equally strong signals.
        """
        if not full_name or "/" not in full_name:
            return False
        owner, name = full_name.split("/", 1)
        owner_l, name_l = owner.lower(), name.lower()

        if owner_l in THIRD_PARTY_OWNERS:
            return False
        if owner_l in {n.lower() for n in self.namespaces}:
            return True
        if self.personal_namespace and owner_l == self.personal_namespace.lower():
            if installed or backs_a_tool:
                return True
            if name_l in self.personal_allow:
                return True
            return any(name_l.startswith(p) for p in self.member_prefixes)
        return False

    def owns(self, full_name):
        """Do WE own this repo? Distinct from ecosystem membership.

        Two questions were previously answered by one predicate, and
        conflating them was a real bug: djdarcy/reddit-slack is owned by
        the user but is not part of the dazzle tooling stack, so
        is_member() said False and the tool labelled it "not ours",
        sorted it below third-party upstreams, and refused to pull it.

        Ownership is the coarse question -- any repo in one of our
        namespaces, personal included, without qualification. Membership
        (is_member) is the finer one and governs ranking only.
        """
        if not full_name or "/" not in full_name:
            return False
        owner = full_name.split("/", 1)[0].lower()
        if owner in THIRD_PARTY_OWNERS:
            return False
        if owner in {n.lower() for n in self.namespaces}:
            return True
        return bool(self.personal_namespace
                    and owner == self.personal_namespace.lower())

    def is_third_party(self, full_name):
        if not full_name or "/" not in full_name:
            return False
        return full_name.split("/", 1)[0].lower() in THIRD_PARTY_OWNERS


def _blank_record(key):
    return {
        "key": key,
        "full_name": None,
        "configured_slugs": [],
        "redirected": False,
        "paths": [],
        "in_namespace": False,
        "cloned": False,
        "installed": None,
        "source_version": None,
        "published": None,
        "git": None,
        "excluded": None,
        "excluded_paths": [],
        "checkouts": [],
        "primary": None,
        "primary_reason": None,
        "declared_dist": None,
        "declared_dist_source": None,
        "pypi_owned": None,
        "pypi_urls": [],
        "last_activity": None,
        "third_party": False,
        "foreign": False,
        "errors": [],
    }


def join(org_repos, local_repos, installs, config,
         source_versions=None, published=None, declared_dists=None,
         pypi_meta=None):
    """Reconcile the discovery views into one record per canonical repo.

    Args:
        org_repos:  [{full_name, ...}] from namespace enumeration
        local_repos: [{path, slug, full_name, redirected, git}] on-disk
        installs:   [{name, version, path}] editable installs
        config:     EcosystemConfig
        source_versions: {normalized path -> version string in the tree}
        published:  {package name -> latest PyPI version}

    Returns records keyed by canonical identity, so a clone whose URL
    still names a pre-transfer namespace lands on the SAME record as its
    org listing -- the bug that made three cloned repos look missing.
    """
    source_versions = source_versions or {}
    published = published or {}
    declared_dists = declared_dists or {}
    pypi_meta = pypi_meta or {}
    records = {}

    def rec(key):
        if key not in records:
            records[key] = _blank_record(key)
        return records[key]

    for entry in org_repos:
        full = entry.get("full_name") or entry.get("nameWithOwner")
        if not full:
            continue
        r = rec(full.lower())
        r["full_name"] = full
        r["in_namespace"] = True

    seen_paths = set()
    for entry in local_repos:
        path = entry.get("path")
        np = norm(path)
        if np in seen_paths:
            continue
        seen_paths.add(np)

        full = entry.get("full_name")
        slug = entry.get("slug")
        key = (full or slug or np).lower()
        r = rec(key)
        r["full_name"] = r["full_name"] or full
        # Identity claims come from LIVE checkouts only. An archived
        # snapshot keeps whatever URL it had when it was frozen, and that
        # URL is not actionable: excluded paths are never fetched, so
        # "fetching through a redirect" is false of them. Letting a bak
        # drive the finding made dazzlesum keep reporting stale-remote-url
        # after its live remote had been repointed -- the report
        # describing an archive rather than the machine. Same family as
        # the every-path-excluded rule below.
        if not config.is_excluded(path):
            if slug and slug not in r["configured_slugs"]:
                r["configured_slugs"].append(slug)
            r["redirected"] = r["redirected"] or bool(entry.get("redirected"))
        r["third_party"] = config.is_third_party(full)
        r["paths"].append(path)
        r["cloned"] = True
        # Retain every checkout. The old code kept only the first git
        # state it saw and discarded the rest, so a record could report
        # "clean" while a sibling worktree held dirty, unpushed work.
        r["checkouts"].append({
            "path": path,
            "git": entry.get("git") or {},
            "last_activity": entry.get("last_activity"),
            "excluded": config.is_excluded(path),
            "private": entry.get("private"),
        })
        act = entry.get("last_activity")
        if act and (r["last_activity"] or 0) < act:
            r["last_activity"] = act
        if config.is_excluded(path):
            r["excluded_paths"].append(path)
        if entry.get("error"):
            r["errors"].append(entry["error"])

    # pip is authoritative for WHICH checkout the environment runs, so it
    # attaches to the record owning that exact path where one exists.
    by_path = {}
    for key, r in records.items():
        for p in r["paths"]:
            by_path[norm(p)] = key

    for inst in installs:
        np = norm(inst.get("path"))
        key = by_path.get(np)
        if key is None:
            # Installed from a path no record claims: either outside the
            # scanned roots, or the directory is gone.
            key = (inst.get("name") or np).lower()
            r = rec(key)
            r["paths"].append(inst.get("path"))
        else:
            r = records[key]
        # Exclusions apply to install-derived records too, or a repo the
        # user has scoped out reappears through the pip axis.
        ipath = inst.get("path")
        if ipath:
            if ipath not in r["paths"]:
                r["paths"].append(ipath)
            if config.is_excluded(ipath) and ipath not in r["excluded_paths"]:
                r["excluded_paths"].append(ipath)
        r["installed"] = inst
        r["source_version"] = source_versions.get(np)

        # PyPI identity comes from the repo's declared name, never from
        # the installed dist name (#106).
        dec = declared_dists.get(np)
        if dec:
            r["declared_dist"], r["declared_dist_source"] = dec
        lookup = _norm_dist(r["declared_dist"] or inst.get("name"))
        pub = published.get(lookup)
        if pub:
            r["published"] = pub
        meta = pypi_meta.get(lookup)
        if meta:
            r["pypi_owned"] = meta.get("owned")
            r["pypi_urls"] = meta.get("urls") or []

    for r in records.values():
        # Resolve which checkout speaks for this identity. Must run AFTER
        # installs are attached, since pip's recorded path is rule 1.
        primary, reason = select_primary(r, config)
        r["primary"] = primary.get("path") if primary else None
        r["primary_reason"] = reason
        # `git` now means "the primary checkout's state", chosen for a
        # stated reason -- not "whichever path was discovered first".
        r["git"] = (primary or {}).get("git") or None

    for r in records.values():
        # A record is excluded only when EVERY path it owns is excluded.
        # Otherwise one stale sibling ("github - Copy", a baks/ snapshot)
        # suppresses the live checkout it shares a canonical key with --
        # which silently hid dazzlecmd, dazzlesum, and git-repokit.
        if r["paths"] and len(r["excluded_paths"]) == len(r["paths"]):
            r["excluded"] = "path excluded by policy"
        if r["full_name"] and not config.owns(r["full_name"]):
            # FOREIGN means "someone else's repo", not "outside the dazzle
            # stack". A KNOWN third-party upstream is excluded outright;
            # anything else we do not own is still reported -- a fork you
            # track really can be behind, and hiding that is worse than
            # ranking it -- but sorted below your own repos so it cannot
            # crowd the top of BEHIND UPSTREAM.
            if config.is_third_party(r["full_name"]):
                r["third_party"] = True
                if r["excluded"] is None:
                    r["excluded"] = "third-party upstream"
            else:
                r["foreign"] = True
    return records


_VER_CORE = re.compile(r'^(\d+(?:\.\d+)*)(.*)$')

# Prerelease ordering. Anything unrecognized sorts with alpha (lowest),
# which is the conservative direction: it under-claims newness rather
# than inventing an upgrade.
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2}


def _version_tuple(v):
    """Loose version parse. Returns None when the string is unparseable.

    Returning None rather than an empty tuple is load-bearing. `()` sorts
    below every real version, so an unparseable installed version (say
    "v1.2.3", with the leading "v") compared as "definitely oldest" and
    fired a spurious stale-install finding purely from formatting. A
    false "you are out of date" is worse than a missed one: it sends
    someone reinstalling for no reason, and erodes trust in every other
    row. Callers must skip the comparison when either side is None.

    Three normalizations, all learned from real data:

      * The git hooks stamp versions as ``0.8.2_main_30-20260719-46532``.
        Everything from the first ``_`` or ``+`` is build metadata.
      * ``0.10.33a0`` (PEP 440) and ``0.10.33-alpha`` (the tree's
        spelling) are the SAME release.
      * ``1.2`` and ``1.2.0`` are the same release, so numeric segments
        are zero-padded before comparison rather than compared by length.
    """
    if v is None:
        return None
    s = re.split(r'[_+]', str(v).strip())[0]
    if not s:
        return None
    m = _VER_CORE.match(s)
    if not m:
        return None
    nums = [int(x) for x in m.group(1).split(".") if x != ""]
    if not nums:
        return None
    # Pad so 1.2 and 1.2.0 compare equal.
    while len(nums) < 4:
        nums.append(0)

    rest = m.group(2).strip("-._").lower()
    if not rest:
        return (tuple(nums[:4]), 1, 0)          # final release
    if rest.startswith("post"):
        tail = re.sub(r'^post[.\-]?', '', rest)
        return (tuple(nums[:4]), 2, int(tail) if tail.isdigit() else 0)

    pm = re.match(r'^([a-z]+)[.\-]?(\d*)$', rest)
    if pm:
        rank = _PRE_RANK.get(pm.group(1), 0)
        ordinal = int(pm.group(2)) if pm.group(2) else 0
        return (tuple(nums[:4]), 0, rank * 1000 + ordinal)
    # Recognizably versioned but with an odd tail (e.g. ".dev3"): treat
    # as a prerelease of that release rather than as unparseable.
    return (tuple(nums[:4]), 0, 0)


def _is_older(a, b):
    """True when version `a` is strictly older than `b`.

    Returns False whenever either side is unparseable -- "I cannot tell"
    must never render as "out of date".
    """
    ta, tb = _version_tuple(a), _version_tuple(b)
    if ta is None or tb is None:
        return False
    return ta < tb


def classify(records, config, sort_mode="newest"):
    """Emit findings per record. Returns {finding_type: [record, ...]}."""
    findings = {k: [] for k in FINDING_ORDER}
    flagged = set()

    # The private/ axis is gated on EVIDENCE that the convention is in
    # use here (see private_axis_enabled). When it is off, no record
    # gains a verdict and the finding kind stays empty -- a machine
    # that does not use private/ never learns the axis exists.
    private_on = config.private_axis_enabled(records)
    if private_on:
        for r in records.values():
            live = [c for c in (r.get("checkouts") or [])
                    if not c.get("excluded")]
            states = [c.get("private") for c in live]
            r["private_state"] = judge_private(states)
            r["private_content"] = has_private_material(states)
            r["private_stores"] = sorted(
                {s["storage"] for s in states
                 if s and s.get("storage")})

    for r in records.values():
        if r["excluded"]:
            findings["excluded-by-policy"].append(r)
            continue
        if r["third_party"]:
            continue

        if r["in_namespace"] and not r["cloned"]:
            findings["not-cloned"].append(r)
            continue

        inst = r["installed"]
        if inst and inst.get("path") and not os.path.isdir(str(inst["path"])):
            findings["source-missing"].append(r)

        if inst and r["source_version"]:
            if _is_older(inst.get("version"), r["source_version"]):
                findings["stale-install-metadata"].append(r)
        # A dist installed under a name the repo no longer declares must
        # NEVER be version-compared: the old name may now belong to an
        # unrelated PyPI project, and the remedy would install it (#106).
        renamed = False
        if inst and r["declared_dist"]:
            if _norm_dist(inst.get("name")) != _norm_dist(r["declared_dist"]):
                findings["stale-dist-name"].append(r)
                renamed = True

        if inst and r["published"] and not renamed:
            if r["pypi_owned"] is False:
                # Right name, wrong owner -- report, never recommend.
                findings["pypi-name-collision"].append(r)
            elif _is_older(inst.get("version"), r["published"]):
                findings["install-behind-published"].append(r)

        if r["redirected"]:
            findings["stale-remote-url"].append(r)

        # Private material with no repo behind it. Scope is decided by
        # the material's EXISTENCE, never by who owns the repo: notes
        # taken while reading someone else's code are real work, and
        # often the only record of understanding it. A checkout with no
        # private/ is never reported -- the tool does not propose that
        # the convention be adopted, only that existing material be
        # recoverable. `split` and `broken` are tags, not findings:
        # separate private repos are a legitimate way to keep sensitive
        # work apart.
        if (private_on
                and r.get("private_state") in (PRIVATE_UNVERSIONED,)
                and r.get("private_content")
                and not config.private_ignored(r.get("full_name"))):
            findings["private-uninitialized"].append(r)

        # REPO-scoped: asked once, of the primary checkout.
        g = r["git"] or {}
        if r["cloned"] and (g.get("behind") or 0) > 0:
            findings["behind-upstream"].append(r)

        # CHECKOUT-scoped: asked of EVERY working copy. "the repo is
        # backed up" and "the work in THIS tree is backed up" are
        # different questions; rolling them together hides a sibling
        # worktree holding unpushed commits.
        if r["cloned"]:
            # Record WHICH checkout triggered each finding. Showing the
            # primary's state under a checkout-scoped heading reads as
            # nonsense: dazzlecmd appeared under NO UPSTREAM displaying
            # "main, origin/main" -- true of the primary, and precisely
            # not the reason the finding fired (fiber-work and local have
            # no upstream). The row must name the checkout it means.
            triggers = r.setdefault("triggers", {})
            for c in (r["checkouts"] or []):
                if c.get("excluded"):
                    continue
                cg = c.get("git") or {}
                branch = cg.get("branch") or ""
                if not cg.get("upstream"):
                    if not config.is_local_only_branch(branch):
                        triggers.setdefault("no-upstream", []).append(c)
                elif (cg.get("ahead") or 0) > 0:
                    triggers.setdefault("unpushed", []).append(c)
                if (cg.get("dirty_count") or 0) > 0:
                    triggers.setdefault("dirty", []).append(c)
            for kind in ("unpushed", "no-upstream", "dirty"):
                if triggers.get(kind):
                    findings[kind].append(r)

    for key, items in findings.items():
        if key not in ("clean",):
            for r in items:
                flagged.add(r["key"])

    for r in records.values():
        if r["excluded"] or r["third_party"]:
            continue
        if r["key"] not in flagged and r["cloned"]:
            findings["clean"].append(r)

    for key in findings:
        findings[key] = sort_records(findings[key], sort_mode)
    return findings


#: Buckets that are NOT findings -- membership in these says nothing is
#: wrong. Counting them as flagged makes a record subtract itself from
#: its own total, which is how the footer came to report 0 clean repos
#: on a box where 24 were clean.
NON_FINDING_BUCKETS = frozenset({"excluded-by-policy", "clean"})


def clean_count(records, findings):
    """How many in-scope records produced no finding at all.

    Counts the `clean` bucket directly rather than deriving it by
    subtraction. The subtraction form was wrong twice over: it counted
    `clean` itself as a flag, and it assumed every in-scope record was
    either flagged or clean -- which is false for records that are
    install-only (no local checkout) and so hit no check at all.
    """
    return len(findings.get("clean") or [])
