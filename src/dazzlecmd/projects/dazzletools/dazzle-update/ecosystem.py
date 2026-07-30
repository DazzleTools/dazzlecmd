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
    "stale-install-metadata",
    "install-behind-published",
    "unpushed",
    "stale-remote-url",
    "vendored-drift",
    "no-upstream",
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
    "missing": "not-cloned",
    "clone": "not-cloned",
    "excluded": "excluded-by-policy",
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
    "stale-install-metadata": "STALE INSTALL -- metadata behind its own source",
    "install-behind-published": "BEHIND PUBLISHED -- PyPI is ahead of this install",
    "stale-remote-url": "STALE REMOTE URL -- fetching through a transfer redirect",
    "behind-upstream": "BEHIND UPSTREAM -- a pull would advance these",
    "not-cloned": "NOT CLONED -- in a namespace, absent here",
    "dirty": "DIRTY -- uncommitted changes",
    "vendored-drift": "VENDORED DRIFT -- embedded copy differs from upstream",
    "excluded-by-policy": "EXCLUDED BY POLICY",
    "clean": "CLEAN -- scanned, nothing to do",
}

# How to order rows WITHIN a section. Recency beats alphabetical at this
# scale: with 150 repos, what you touched this week is what you mean.
SORT_MODES = ("newest", "oldest", "name")


def sort_records(items, mode="newest"):
    """Sort rows within a section. Records with no date sort last."""
    if mode == "name":
        return sorted(items, key=lambda r: (r["full_name"] or r["key"]).lower())
    reverse = (mode != "oldest")
    return sorted(
        items,
        key=lambda r: (r.get("last_activity") is not None,
                       r.get("last_activity") or 0) if reverse
        else (r.get("last_activity") is None,
              r.get("last_activity") or 0),
        reverse=reverse,
    )

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
                 personal_allow=(), include=()):
        self.namespaces = list(namespaces or [])
        self.personal_namespace = personal_namespace
        self.excludes = list(excludes if excludes is not None else DEFAULT_EXCLUDES)
        self.roots = list(roots or [])
        self.member_prefixes = tuple(member_prefixes)
        self.personal_allow = {s.lower() for s in personal_allow}
        self.include = list(include or [])

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
        "last_activity": None,
        "third_party": False,
        "errors": [],
    }


def join(org_repos, local_repos, installs, config,
         source_versions=None, published=None):
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
        if slug and slug not in r["configured_slugs"]:
            r["configured_slugs"].append(slug)
        r["redirected"] = r["redirected"] or bool(entry.get("redirected"))
        r["third_party"] = config.is_third_party(full)
        r["paths"].append(path)
        r["cloned"] = True
        if entry.get("git") and not r["git"]:
            r["git"] = entry["git"]
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
        pub = published.get((inst.get("name") or "").lower())
        if pub:
            r["published"] = pub

    for r in records.values():
        # A record is excluded only when EVERY path it owns is excluded.
        # Otherwise one stale sibling ("github - Copy", a baks/ snapshot)
        # suppresses the live checkout it shares a canonical key with --
        # which silently hid dazzlecmd, dazzlesum, and git-repokit.
        if r["paths"] and len(r["excluded_paths"]) == len(r["paths"]):
            r["excluded"] = "path excluded by policy"
        if r["excluded"] is None and r["full_name"] \
                and not config.is_member(
                    r["full_name"],
                    installed=bool(r["installed"]),
                    backs_a_tool=False):
            if config.is_third_party(r["full_name"]):
                r["third_party"] = True
                r["excluded"] = "third-party upstream"
    return records


_VER_CORE = re.compile(r'^(\d+(?:\.\d+)*)(.*)$')


def _version_tuple(v):
    """Loose version parse: enough to order 0.9.0 above 0.8.7a0.

    Two normalizations matter here, both learned from real data:

      * The git hooks stamp versions as ``0.8.2_main_30-20260719-46503732``.
        Everything from the first ``_`` or ``+`` is build metadata and must
        be dropped, or every stamped tree looks newer than its own install.
      * ``0.10.33a0`` (PEP 440) and ``0.10.33-alpha`` (the tree's spelling)
        are the SAME release. Comparing them naively reports a package as
        stale against itself.
    """
    if not v:
        return ()
    s = re.split(r'[_+]', str(v).strip())[0]
    m = _VER_CORE.match(s)
    if not m:
        return ()
    nums = tuple(int(x) for x in m.group(1).split(".") if x != "")
    rest = m.group(2).strip("-.").lower()
    # A prerelease suffix sorts BELOW the same numeric release; a post
    # release sorts above it.
    is_pre = bool(rest) and not rest.startswith("post")
    return (nums, 0 if is_pre else 1)


def classify(records, config, sort_mode="newest"):
    """Emit findings per record. Returns {finding_type: [record, ...]}."""
    findings = {k: [] for k in FINDING_ORDER}
    flagged = set()

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
            if _version_tuple(inst.get("version")) < _version_tuple(r["source_version"]):
                findings["stale-install-metadata"].append(r)
        if inst and r["published"]:
            if _version_tuple(inst.get("version")) < _version_tuple(r["published"]):
                findings["install-behind-published"].append(r)

        if r["redirected"]:
            findings["stale-remote-url"].append(r)

        g = r["git"] or {}
        if r["cloned"]:
            branch = (g.get("branch") or "").lower()
            if not g.get("upstream") and branch not in LOCAL_ONLY_BRANCHES:
                findings["no-upstream"].append(r)
            else:
                if (g.get("ahead") or 0) > 0:
                    findings["unpushed"].append(r)
                if (g.get("behind") or 0) > 0:
                    findings["behind-upstream"].append(r)
            if (g.get("dirty_count") or 0) > 0:
                findings["dirty"].append(r)

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


def clean_count(records, findings):
    """How many in-scope records produced no finding at all."""
    flagged = set()
    for key, items in findings.items():
        if key == "excluded-by-policy":
            continue
        for r in items:
            flagged.add(r["key"])
    total = sum(1 for r in records.values()
                if not r["excluded"] and not r["third_party"])
    return max(0, total - len(flagged))
