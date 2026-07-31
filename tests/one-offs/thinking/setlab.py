"""setlab -- score candidate set-rule languages against a real ground truth.

The design question "org rule vs text rule vs enumeration vs layered" has
been argued from what each rule MATCHES. That is only half the evidence:
without a statement of what SHOULD be in the set, matching counts cannot
tell you which rule is right, only which is bigger.

This harness closes that. It:

  1. resolves the real repo population from disk,
  2. evaluates every candidate rule form over it,
  3. isolates only the repos where the rules DISAGREE -- the sole set
     that needs a human verdict (agreement zones need no labelling),
  4. once labelled, scores each rule form on precision, recall, the
     config size needed to express it, and whether it self-maintains.

Usage:
    python setlab.py disputed          # emit the adjudication file
    python setlab.py score             # score rules against labels
    python setlab.py score --verbose   # per-repo detail

Read-only with respect to git and the network beyond `gh repo list`.
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys

_DZ = r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools"
sys.path.insert(0, _DZ)
sys.path.insert(0, os.path.join(_DZ, "dazzle-update"))

from _repo_common.discovery import find_git_repos, editable_installs  # noqa: E402
from _repo_common.gh_identity import IdentityResolver, parse_slug  # noqa: E402
from _repo_common.repo_state import detect_remotes  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, "setlab_labels.json")

DAZZLE_ORGS = ["DazzleTools", "DazzleLib", "DazzleML", "DazzleNodes", "DazzleProj"]


# -- population ----------------------------------------------------------

def population(root=r"C:\code"):
    r = IdentityResolver()
    out = {}
    for p in find_git_repos(root, max_depth=3):
        o = next((x for x in detect_remotes(p) if x["name"] == "origin"), None)
        slug = (o.get("slug") or parse_slug(o.get("fetch_url"))) if o else None
        if not slug:
            continue
        full = r.resolve(slug)["full_name"] or slug
        out.setdefault(full, []).append(p)
    return out


def installed_names():
    return {(i["name"] or "").lower() for i in editable_installs()}


def tool_dependencies():
    """Dist names that a REGISTERED dz tool actually depends on.

    First cut of this used "is any installed package", which is not the
    same question at all -- it swept in stellaris-ironman-cheat and
    AMDead simply because they are pip-installed. The semantic claim
    being tested is "this repo is a member because a shipped tool needs
    it", and the evidence for that is a tool's own requirements.txt or
    the aggregator's declared dependencies -- which is how DPAPIck3
    (backing `dz efs-recover`) earns membership no naming rule can see.
    """
    import glob
    import re
    deps = set()
    # Tool requirements live at projects/<kit>/<tool>/requirements.txt.
    # _DZ already points at projects/dazzletools, so the glob is one level
    # shallower than it looks; search both shapes to cover other kits.
    projects = os.path.dirname(_DZ)
    patterns = [os.path.join(_DZ, "*", "requirements.txt"),
                os.path.join(projects, "*", "*", "requirements.txt")]
    for pat in patterns:
        for req in glob.glob(pat):
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

    # _DZ is <repo>/src/dazzlecmd/projects/dazzletools -- four levels to root.
    pp = os.path.join(_DZ, "..", "..", "..", "..", "pyproject.toml")
    try:
        import tomllib
        with open(os.path.abspath(pp), "rb") as fh:
            data = tomllib.load(fh)
        for d in (data.get("project") or {}).get("dependencies", []):
            m = re.match(r"^([A-Za-z0-9._-]+)", d)
            if m:
                deps.add(m.group(1).lower().replace("_", "-"))
    except Exception:
        pass
    return deps


def kit_sources():
    """Repos a kit manifest NAMES as its own source.

    This is the ecosystem describing itself: `wtf.kit.json` carries
    "source": ".../djdarcy/wtf-windows.git". That is an authoritative
    membership statement -- it needs no naming convention, cannot drift
    from reality without the kit breaking, and costs zero config lines.
    Notably it admits wtf-windows while saying NOTHING about wtf-privacy
    or wtf-restarted, which a `djdarcy/wtf-*` glob cannot distinguish.
    """
    import glob
    import re
    out = set()
    projects = os.path.dirname(_DZ)
    pkg = os.path.dirname(projects)          # <repo>/src/dazzlecmd
    pats = [os.path.join(pkg, "kits", "*.json"),
            os.path.join(projects, "*", ".kit.json"),
            os.path.join(projects, "*", "kits", "*.json")]
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


# -- candidate rule forms ------------------------------------------------
#
# Each returns (matcher, config_lines, self_maintaining).
# config_lines approximates how much a human must write and keep correct.

def _glob_any(name, pats):
    n = name.lower()
    return any(fnmatch.fnmatch(n, p.lower()) for p in pats)


def rule_org_only():
    pats = [f"{o}/*" for o in DAZZLE_ORGS]
    return (lambda n, ctx: _glob_any(n, pats), len(DAZZLE_ORGS), True)


def rule_org_subset():
    """Namespaces chosen PER SET, not "every org whose name says Dazzle".

    Every other rule here silently assumes the five Dazzle* orgs form one
    set. They plainly do not -- DazzleNodes is ComfyUI nodes and DazzleML
    is model tooling; neither ships a `dz` subcommand. If the intended set
    is the CLI tools, the org list IS the set definition and the whole
    include/exclude apparatus may be unnecessary. Without this candidate
    the experiment cannot discover that, because no other rule can say no
    to DazzleNodes.
    """
    pats = ["DazzleTools/*", "DazzleLib/*"]
    return (lambda n, ctx: _glob_any(n, pats), len(pats), True)


def rule_name_prefix():
    return (lambda n, ctx: n.split("/", 1)[1].lower().startswith("dazzle"), 1, True)


def rule_fullname_substring():
    return (lambda n, ctx: "dazzle" in n.lower(), 1, True)


def rule_enumeration(members):
    s = {m.lower() for m in members}
    return (lambda n, ctx: n.lower() in s, len(s), False)


_NS = [f"{o}/*" for o in DAZZLE_ORGS]
_INC = ["djdarcy/dazzle-*", "djdarcy/wtf-*", "djdarcy/DPAPIck3"]
_EXC = ["*/.github"]


def _layered(ns, inc, exc):
    def m(n, ctx):
        if _glob_any(n, exc):
            return False
        return _glob_any(n, ns) or _glob_any(n, inc)
    return m, len(ns) + len(inc) + len(exc)


def rule_layered():
    """The recommended form: org + glob include - exclude."""
    m, lines = _layered(_NS, _INC, _EXC)
    return (m, lines, True)


def rule_layered_plus_backs_tool():
    """Layered, plus the semantic rule: a repo backing an installed tool.

    Drops `djdarcy/DPAPIck3` from the include list on purpose. That entry
    exists in the hand-maintained rule ONLY because no pattern can see the
    membership; the semantic rule derives it from a tool's declared
    requirements. Leaving it in would charge this form for config it does
    not need and make the size comparison meaningless.
    """
    inc = [p for p in _INC if p != "djdarcy/DPAPIck3"]
    base, lines = _layered(_NS, inc, _EXC)

    def m(n, ctx):
        if base(n, ctx):
            return True
        repo = n.split("/", 1)[1].lower().replace("_", "-")
        return repo in ctx["tool_deps"]
    return (m, lines, True)


def _declared(n, ctx):
    """Membership the ecosystem states about itself, in either form."""
    return (n.lower() in ctx["kit_sources"]
            or n.split("/", 1)[1].lower().replace("_", "-") in ctx["tool_deps"])


def rule_declared_only():
    """Zero config: believe only what the manifests declare."""
    return (_declared, 0, True)


def rule_org_subset_plus_declared():
    """The narrow org list, plus whatever the manifests declare.

    If this scores well it is the strongest result available: two config
    lines, no per-repo maintenance, and every exception earned from a file
    that already has to be correct for the software to run.
    """
    base, lines = _layered(["DazzleTools/*", "DazzleLib/*"], [], [])

    def m(n, ctx):
        return base(n, ctx) or _declared(n, ctx)
    return (m, lines, True)


def rule_ns_declared_exc():
    """namespaces + exclude + declared. No `include` field at all.

    Every entry the hand-maintained include list carried was either WRONG
    (djdarcy/wtf-* swept in wtf-privacy and wtf-restarted; djdarcy/dazzle-*
    swept in adopted forks) or DERIVABLE (DPAPIck3, wtf-windows, UNCtools
    are declared by a manifest). If this scores 1.00/1.00 the include field
    is not a needed part of the rule language -- it is a place for mistakes.
    """
    base, lines = _layered(["DazzleTools/*", "DazzleLib/*"], [], ["*/.github"])

    def m(n, ctx):
        if _glob_any(n, ["*/.github"]):
            return False
        return base(n, ctx) or _declared(n, ctx)
    return (m, lines, True)


def rule_ns_declared_exc_inc():
    """Same, plus ONE include line. Only relevant if djdarcy/dazzle-* is IN.

    Exists to measure the cost of the `include` field honestly: if the
    C5 verdict is IN, does the field earn its keep at exactly one entry,
    or does it drag false positives in with it?
    """
    _, lines = _layered(["DazzleTools/*", "DazzleLib/*"],
                        ["djdarcy/dazzle-*"], ["*/.github"])

    def m(n, ctx):
        if _glob_any(n, ["*/.github"]):
            return False
        return (_glob_any(n, ["DazzleTools/*", "DazzleLib/*",
                              "djdarcy/dazzle-*"]) or _declared(n, ctx))
    return (m, lines, True)


def rule_ns_declared_exc_names():
    """include as EXACT repo names, not globs.

    The user's C5 verdict SPLIT the cluster: dazzle-claude-code-config and
    the history-viewer are members ("our claude tools rely on" them);
    vault, frame-interpolation, opentimestamps-client, python-bitcoinlib
    are dazzle-adjacent, each with its own condition for joining later.
    No glob can express a split -- and every glob include measured so far
    has been over-broad (djdarcy/wtf-* swept 2 false positives,
    djdarcy/dazzle-* sweeps 4). Exact names are the healthy form of the
    field; they are also the hand-maintained part, which is what the
    warn-threshold exists to police.
    """
    inc = ["djdarcy/dazzle-claude-code-config",
           "djdarcy/dazzle-claude-code-history-viewer"]
    base, lines = _layered(["DazzleTools/*", "DazzleLib/*"], inc, ["*/.github"])

    def m(n, ctx):
        if _glob_any(n, ["*/.github"]):
            return False
        return base(n, ctx) or _declared(n, ctx)
    return (m, lines, True)


RULES = {
    "org-only":            rule_org_only,
    "org-subset":          rule_org_subset,
    "declared-only":       rule_declared_only,
    "org-subset+declared": rule_org_subset_plus_declared,
    "ns+declared-exc":     rule_ns_declared_exc,
    "ns+declared-exc+inc": rule_ns_declared_exc_inc,
    "ns+declared-exc+names": rule_ns_declared_exc_names,
    "name-prefix":         rule_name_prefix,
    "fullname-substring":  rule_fullname_substring,
    "layered":             rule_layered,
    "layered+backs_tool":  rule_layered_plus_backs_tool,
}


def evaluate(pop, ctx):
    out = {}
    for name, factory in RULES.items():
        matcher, lines, sm = factory()
        out[name] = {
            "members": {n for n in pop if matcher(n, ctx)},
            "config_lines": lines,
            "self_maintaining": sm,
        }
    return out


# -- disputed set --------------------------------------------------------

def disputed(pop, results):
    """Repos where the rule forms disagree. Only these need a verdict."""
    rows = []
    for n in sorted(pop):
        votes = {k: (n in v["members"]) for k, v in results.items()}
        if len(set(votes.values())) > 1:
            rows.append((n, votes))
    return rows


def cmd_disputed():
    pop = population()
    ctx = {"installed": installed_names(),
           "tool_deps": tool_dependencies(),
           "kit_sources": kit_sources()}
    res = evaluate(pop, ctx)
    rows = disputed(pop, res)

    agreed_in = [n for n in pop if all(n in v["members"] for v in res.values())]
    agreed_out = [n for n in pop
                  if all(n not in v["members"] for v in res.values())]

    print(f"  population              : {len(pop)}")
    print(f"  all rules agree IN      : {len(agreed_in)}   (no verdict needed)")
    print(f"  all rules agree OUT     : {len(agreed_out)}  (no verdict needed)")
    print(f"  DISPUTED                : {len(rows)}   <- only these need you")
    print()

    # Group by vote signature. Repos sharing a signature are, to every
    # candidate rule, THE SAME REPO -- no rule here can separate them. So
    # the real adjudication is per cluster, not per repo, and a cluster the
    # human wants to SPLIT is direct evidence that no candidate rule can
    # express the intended set (which is itself a result worth having).
    clusters = {}
    for n, votes in rows:
        sig = tuple(sorted(k for k, v in votes.items() if v))
        clusters.setdefault(sig, []).append(n)
    ordered = sorted(clusters.items(), key=lambda kv: -len(kv[1]))

    # Carry prior verdicts forward keyed by REPO, not by vote signature.
    # Adding or changing a rule re-splits the clusters and renumbers them,
    # so signature-keyed carry-forward silently drops every verdict exactly
    # when the experiment is most active. A cluster inherits a verdict only
    # if its members previously agreed; a cluster that straddles an old
    # boundary goes back to null and is re-asked, which is correct.
    old_repo, old_why, old_over = {}, {}, {}
    if os.path.isfile(LABELS):
        prev = json.load(open(LABELS, encoding="utf-8"))
        old_over = prev.get("overrides") or {}
        for c in (prev.get("clusters") or {}).values():
            v = c.get("in_dazzle_set")
            for n in c.get("repos", []):
                old_repo[n] = v
                if c.get("_proposed_why"):
                    old_why[n] = c["_proposed_why"]

    def inherit(names):
        vs = {old_repo.get(n) for n in names}
        return (vs.pop() if len(vs) == 1 else None)

    def inherit_why(names):
        ws = {old_why.get(n) for n in names}
        return (ws.pop() if len(ws) == 1 else None)

    payload = {
        "_help": ("Set in_dazzle_set on each CLUSTER below (7 booleans, not "
                  "52). Every repo in a cluster is indistinguishable to all "
                  "candidate rules, so they must share a verdict -- unless "
                  "you put a per-repo exception in `overrides`, which is "
                  "itself the finding that no rule can express the set. "
                  "Values are PROPOSALS to review, not ground truth. "
                  "Then run: python setlab.py score --verbose"),
        "agreed_in": sorted(agreed_in),
        "agreed_out_count": len(agreed_out),
        "overrides": old_over,
        "clusters": {},
    }
    for i, (sig, names) in enumerate(ordered, 1):
        entry = {
            "in_dazzle_set": inherit(names),
            "_signature_key": ",".join(sig),
            "_rules_saying_yes": list(sig),
            "repos": sorted(names),
        }
        why = inherit_why(names)
        if why:
            entry["_proposed_why"] = why
        payload["clusters"][f"C{i}"] = entry
    with open(LABELS, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
    print(f"  wrote {LABELS}")
    print()

    print(f"  {len(rows)} disputed repos collapse to "
          f"{len(clusters)} distinct vote patterns:")
    print()
    for i, (sig, names) in enumerate(ordered, 1):
        print(f"  [C{i}] {len(names)} repos -- yes: {', '.join(sig)}")
        for n in sorted(names):
            print(f"         {n}")
        print()


# -- scoring -------------------------------------------------------------

def cmd_score(verbose=False, flip=()):
    if not os.path.isfile(LABELS):
        print("  no labels yet -- run: python setlab.py disputed")
        return 2
    data = json.load(open(LABELS, encoding="utf-8"))
    clusters = data.get("clusters") or {}
    blank = [k for k, c in clusters.items() if c.get("in_dazzle_set") is None]
    if blank:
        print(f"  {len(blank)} cluster(s) still unlabelled: "
              f"{', '.join(sorted(blank))}")
        print("  set in_dazzle_set (true/false) on each cluster, then re-run")
        return 2

    # Sensitivity: flip a cluster's verdict to see whether the ranking is
    # robust to the labels I was least sure of. A conclusion that survives
    # flipping an uncertain label is worth more than one that does not.
    for k in flip:
        if k not in clusters:
            print(f"  no such cluster: {k}")
            return 2
        clusters[k]["in_dazzle_set"] = not bool(clusters[k]["in_dazzle_set"])
        print(f"  FLIPPED {k} -> {clusters[k]['in_dazzle_set']} "
              f"({len(clusters[k]['repos'])} repos)")

    # Expand cluster verdicts to per-repo, then apply any explicit overrides.
    labels = {}
    for c in clusters.values():
        for n in c["repos"]:
            labels[n] = bool(c["in_dazzle_set"])
    overrides = data.get("overrides") or {}
    split = {}
    for n, v in overrides.items():
        if n in labels and bool(v) != labels[n]:
            sig = next(c["_signature_key"] for c in clusters.values()
                       if n in c["repos"])
            split.setdefault(sig, []).append(n)
        labels[n] = bool(v)

    pop = population()
    ctx = {"installed": installed_names(),
           "tool_deps": tool_dependencies(),
           "kit_sources": kit_sources()}
    res = evaluate(pop, ctx)

    # ground truth = agreed_in (all rules concur) + human verdicts
    truth = set(data.get("agreed_in", []))
    truth |= {k for k, v in labels.items() if v}

    print(f"  ground truth size: {len(truth)}")
    if split:
        print()
        print("  !! CEILING: these clusters were split by an override, so no")
        print("     candidate rule can reach precision AND recall 1.00 --")
        print("     every rule votes identically on the whole cluster:")
        for sig, names in split.items():
            print(f"       [{sig}] split by {', '.join(sorted(names))}")
    print()
    print(f"  {'rule':<22}{'prec':>6}{'rec':>7}{'F1':>7}{'cfg':>6}  self-maint")
    for name, v in res.items():
        m = v["members"]
        tp = len(m & truth)
        fp = len(m - truth)
        fn = len(truth - m)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        print(f"  {name:<22}{prec:>6.2f}{rec:>7.2f}{f1:>7.2f}"
              f"{v['config_lines']:>6}  {'yes' if v['self_maintaining'] else 'NO'}")
        if verbose:
            for n in sorted(m - truth):
                print(f"      FP {n}")
            for n in sorted(truth - m):
                print(f"      FN {n}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "disputed"
    if cmd == "disputed":
        cmd_disputed()
    elif cmd == "score":
        flips = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--flip=")]
        sys.exit(cmd_score("--verbose" in sys.argv, flips))
    else:
        print(__doc__)
