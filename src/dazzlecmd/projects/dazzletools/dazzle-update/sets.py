"""Working sets -- named, overlapping lenses over the repo population.

A set answers "which repos does THIS effort mean" -- distinct from
ownership (which governs `--fix` eligibility and the "not ours" label)
and from ecosystem membership (which governs ranking). Sets are lenses:
a repo may sit in several at once, and wtf-windows genuinely belongs to
both the `dazzle` set (a kit manifest names it) and the `wtf` set (the
product line). Overlap is a feature, not a conflict to resolve.

Membership is expressed by four sources, deliberately unequal in weight.
The weights are MEASURED, not argued: the rule language was scored
against a human-adjudicated ground truth of the real 100-repo population
(see the set-rule-language design doc, Outcome Addendum):

    namespaces   glob patterns over owner/repo. Carries the body of the
                 set. Choosing these PER SET is the largest single
                 accuracy effect measured: "all five Dazzle* orgs" scored
                 0.50 precision, the two orgs the set actually means
                 scored 0.96 -- with fewer config lines.
    declared     membership the ecosystem states about itself: kit
                 manifests naming their source repo, tools naming their
                 dependencies. Zero config lines, cannot drift without
                 the software breaking, and makes distinctions no glob
                 can (admits wtf-windows while silent on wtf-privacy).
                 Derived, never user-written; a set opts in per its
                 `declared` flag.
    include      EXACT repo names. Both glob includes measured were
                 over-broad (djdarcy/wtf-* swept 2 false positives into
                 the dazzle set, djdarcy/dazzle-* swept 4), while exact
                 names reached 1.00/1.00 -- so globs get a health
                 warning here and belong in `namespaces` instead.
                 Include entries are also TEMPORARY by nature: they name
                 dependency-shaped membership nobody has declared yet,
                 and retire the moment a manifest says it.
    exclude      small nameable noise (*/.github). Vetoes everything,
                 declared included.

No regex, no boolean composition. The language stays small because every
scoping failure in this tool's history was a mechanism that LOOKED
right; three unioned lists can be read aloud.
"""

import fnmatch
import json
import os
import re

# dazzle-update lives at <pkg>/projects/dazzletools/dazzle-update, so the
# dazzlecmd package root is three levels up. Derived from this file, not
# imported, so the module works when run as a bare tool directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)                    # projects/dazzletools
_PROJECTS = os.path.dirname(_PROJECT)                # projects/
_PKG = os.path.dirname(_PROJECTS)                    # src/dazzlecmd

#: Health thresholds, calibrated by measurement. The original design said
#: "warn past 10", which would never have fired on any configuration ever
#: measured -- including the design's own include list, which was wrong
#: at three entries. Healthy is 0-3 exact names.
INCLUDE_WARN_THRESHOLD = 3
_GLOB_CHARS = re.compile(r"[*?\[]")


def match_repo(full_name, patterns):
    """Case-folded glob match of an owner/repo name against patterns.

    Pure function, no I/O. This is deliberately the whole matching
    engine: fnmatch over the lowercased full name.
    """
    if not full_name:
        return False
    n = str(full_name).lower()
    return any(fnmatch.fnmatch(n, str(p).lower()) for p in patterns or ())


class SetDefinition:
    """One named set: namespaces + include + exclude (+ declared opt-in)."""

    FIELDS = ("namespaces", "include", "exclude", "declared")

    def __init__(self, name, namespaces=(), include=(), exclude=(),
                 declared=False):
        self.name = name
        self.namespaces = [str(p) for p in (namespaces or [])]
        self.include = [str(p) for p in (include or [])]
        self.exclude = [str(p) for p in (exclude or [])]
        self.declared = bool(declared)

    def contains(self, full_name, declared_members=None):
        """Membership test. exclude vetoes every other source, declared
        included -- a set that excludes */.github means it even if a
        manifest were somehow to declare one."""
        if not full_name:
            return False
        if match_repo(full_name, self.exclude):
            return False
        if match_repo(full_name, self.namespaces):
            return True
        n = str(full_name).lower()
        if any(n == str(p).lower() for p in self.include):
            return True
        # include tolerates globs (with a health warning) rather than
        # ignoring them: a config that parses must behave as written.
        globby = [p for p in self.include if _GLOB_CHARS.search(p)]
        if globby and match_repo(full_name, globby):
            return True
        if self.declared and declared_members:
            if declared_members.matches(full_name):
                return True
        return False

    def warnings(self):
        """Health checks on the definition itself. Returns [str].

        These fire at load time, not match time: a bad rule should be
        reported once per run, next to the config that caused it.
        """
        out = []
        globby = [p for p in self.include if _GLOB_CHARS.search(p)]
        if globby:
            out.append(
                f"set '{self.name}': glob(s) in include ({', '.join(globby)}) "
                f"-- measured over-broad in every real case; globs belong in "
                f"'namespaces', include takes exact owner/repo names")
        if len(self.include) > INCLUDE_WARN_THRESHOLD:
            out.append(
                f"set '{self.name}': include has {len(self.include)} entries "
                f"(healthy is 0-{INCLUDE_WARN_THRESHOLD}) -- entries this "
                f"list accumulates are memberships waiting to become "
                f"declarations or namespaces")
        return out


class DeclaredMembers:
    """Membership the installed ecosystem states about itself.

    Two shapes of statement:
      * a kit manifest's `source` field names the repo the kit ships from
        (wtf.kit.json -> djdarcy/wtf-windows)
      * a tool's requirements name the dists it depends on
        (efs-recover/requirements.txt -> dpapick3)

    The first matches on full owner/repo; the second on the repo part of
    the name, dist-normalized -- djdarcy/DPAPIck3 earns membership
    because `dpapick3` is a declared dependency, which no naming rule
    can see.
    """

    def __init__(self, slugs=None, dists=None):
        self.slugs = {str(s).lower() for s in (slugs or ())}
        self.dists = {str(d).lower() for d in (dists or ())}

    def matches(self, full_name):
        if not full_name or "/" not in str(full_name):
            return False
        n = str(full_name).lower()
        if n in self.slugs:
            return True
        repo = n.split("/", 1)[1].replace("_", "-")
        return repo in self.dists


def kit_sources(pkg_root=None):
    """Repos a kit manifest NAMES as its own source."""
    pkg = pkg_root or _PKG
    projects = os.path.join(pkg, "projects")
    pats = [os.path.join(pkg, "kits", "*.json"),
            os.path.join(projects, "*", ".kit.json"),
            os.path.join(projects, "*", "kits", "*.json")]
    import glob
    out = set()
    for pat in pats:
        for f in glob.glob(pat):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            src = d.get("source") if isinstance(d, dict) else None
            if not isinstance(src, str):
                continue
            m = re.search(r"github\.com[/:]([^/]+)/([^/.]+)", src)
            if m:
                out.add(f"{m.group(1)}/{m.group(2)}".lower())
    return out


def tool_dependencies(pkg_root=None):
    """Dist names that a registered dz tool actually depends on.

    Reads each tool's own requirements.txt under projects/<kit>/<tool>/.
    Deliberately NOT "any installed package" -- that measured as a
    different question entirely, sweeping in unrelated pip installs.
    """
    import glob
    pkg = pkg_root or _PKG
    projects = os.path.join(pkg, "projects")
    deps = set()
    for req in glob.glob(os.path.join(projects, "*", "*", "requirements.txt")):
        try:
            for line in open(req, encoding="utf-8", errors="replace"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^([A-Za-z0-9._-]+)", line)
                if m:
                    deps.add(m.group(1).lower().replace("_", "-"))
        except OSError:
            pass
    return deps


def declared_members(pkg_root=None):
    """The derived membership source, built once per run."""
    return DeclaredMembers(slugs=kit_sources(pkg_root),
                           dists=tool_dependencies(pkg_root))


def load_sets(cfg_sets):
    """Parse the config's `sets` mapping. Returns (sets, warnings).

    Malformed entries degrade loudly and are skipped -- a bad set must
    not make the tool unusable, but must never be silently ignored.
    """
    sets, warns = [], []
    if not cfg_sets:
        return sets, warns
    if not isinstance(cfg_sets, dict):
        return sets, ["config 'sets': expected a mapping of name -> rule"]
    for name, body in cfg_sets.items():
        if not isinstance(body, dict):
            warns.append(f"config 'sets': '{name}' is not a mapping; skipped")
            continue
        unknown = [k for k in body if k not in SetDefinition.FIELDS
                   and not k.startswith("_")]
        if unknown:
            warns.append(f"set '{name}': ignoring unknown key(s): "
                         + ", ".join(sorted(unknown)))
        bad_type = [k for k in ("namespaces", "include", "exclude")
                    if k in body and not isinstance(body[k], list)]
        if bad_type:
            warns.append(f"set '{name}': {', '.join(bad_type)} must be "
                         f"list(s); skipped")
            continue
        s = SetDefinition(name,
                          namespaces=body.get("namespaces") or [],
                          include=body.get("include") or [],
                          exclude=body.get("exclude") or [],
                          declared=body.get("declared", False))
        warns.extend(s.warnings())
        sets.append(s)
    return sets, warns


def annotate(records, sets, declared=None):
    """Stamp every record with the sets it belongs to (lens, not filter).

    Records with no resolvable owner/repo name (a repo with no remote)
    match nothing; their `sets` list is empty rather than absent, so a
    consumer can distinguish "in no set" from "sets not computed".
    """
    for r in records.values():
        full = r.get("full_name")
        r["sets"] = [s.name for s in sets
                     if s.contains(full, declared_members=declared)]
    return records
