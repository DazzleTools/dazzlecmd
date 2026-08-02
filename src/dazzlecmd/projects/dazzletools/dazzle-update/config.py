"""User configuration for dz dazzle-update.

Everything the scanner scopes on is overridable: which roots to walk,
which namespaces to enumerate, what counts as ecosystem membership, and
what to ignore. Without this the tool only fits one machine's layout.

Search order (first hit wins):

    1. --config PATH
    2. ./.dazzle-update.json         (project-local, checked in if useful)
    3. <user config dir>/dazzlecmd/dazzle-update.json

YAML is accepted when PyYAML happens to be installed, because a config
humans hand-edit benefits from comments -- but it is never required, and
JSON is always understood. A parse error is reported and the run
continues on defaults: a malformed config must not make the tool
unusable, but it must also never be silently ignored.

Defaults are deliberately empty-ish rather than opinionated: namespaces
DERIVE from `gh api user/orgs` when not listed here, which is what kept
DazzleML from being missed by a hand-written list.
"""

import json
import os

CONFIG_BASENAME = "dazzle-update"
PROJECT_CONFIG = ".dazzle-update.json"

DEFAULTS = {
    "roots": [],                 # [] -> platform default
    "namespaces": [],            # [] -> derived from gh api user/orgs
    "personal_namespace": None,  # None -> derived from gh api user
    "exclude": [],               # merged with built-in defaults
    "exclude_replace": False,    # True -> use ONLY the configured excludes
    "include": [],               # force-include, wins over exclude
    "member_prefixes": ["dazzle"],
    "personal_allow": [],        # personal-namespace repos to treat as members
    # Files whose modifications are machine-made churn (hook-restamped
    # version files); matched by fnmatch against porcelain paths and
    # basenames, merged with the built-in defaults (_version.py and the
    # older stamp convention version.py). Set
    # churn_files_replace true to use ONLY your list -- true plus an
    # empty list disables churn filtering entirely.
    "churn_files": [],
    "churn_files_replace": False,
    # Working sets: named, OVERLAPPING lenses over the population.
    #   {"<name>": {"namespaces": [globs], "include": [exact owner/repo],
    #               "exclude": [globs], "declared": bool}}
    # namespaces carry the body; include takes exact names (globs warn --
    # measured over-broad in every real case); declared opts in to
    # membership derived from kit manifests and tool requirements.
    "sets": {},
    "third_party_owners": [],    # merged with built-in defaults
    "local_only_branches": [],   # merged with built-in defaults
    "sort": "newest",            # newest | oldest | name
    "order": [],                 # [] -> built-in order; partial lists allowed
    # Caching. Three different lifetimes, deliberately separate:
    #   cache_write     save each fresh scan for later replay
    #   cache_max_age   default age limit for --cached (None = any age)
    #   cache_path      where the scan cache lives
    #   namespace_ttl   how long a gh org listing may be reused (seconds);
    #                   0 disables reuse. Org membership changes on the
    #                   order of days, so re-listing every run is waste --
    #                   but this NEVER affects fetch, which must be live.
    "cache_write": True,
    "cache_max_age": None,
    "cache_path": None,
    "namespace_ttl": 86400,
    "fetch": True,
    "published": False,
    "fetch_timeout": 60,
    "fetch_workers": 8,
}


def user_config_dir():
    base = (os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_CONFIG_HOME")
            or os.path.expanduser("~/.config"))
    return os.path.join(base, "dazzlecmd")


def candidate_paths(explicit=None, cwd=None):
    """Config locations in precedence order."""
    out = []
    if explicit:
        out.append(explicit)
    out.append(os.path.join(cwd or os.getcwd(), PROJECT_CONFIG))
    for ext in ("json", "yaml", "yml"):
        out.append(os.path.join(user_config_dir(), f"{CONFIG_BASENAME}.{ext}"))
    return out


def _parse(path, text):
    if path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml  # optional
        except ImportError:
            return None, (f"{path}: YAML config found but PyYAML is not "
                          "installed; convert it to JSON or pip install pyyaml")
        try:
            return yaml.safe_load(text) or {}, None
        except Exception as exc:  # noqa: BLE001 - report, do not crash
            return None, f"{path}: {exc}"
    try:
        return json.loads(text or "{}"), None
    except json.JSONDecodeError as exc:
        return None, f"{path}: {exc}"


def load(explicit=None, cwd=None):
    """Return (config_dict, source_path_or_None, error_or_None).

    A missing config is normal and silent. A malformed one is reported
    and defaults are used -- loud degradation, never a silent fallback.
    """
    for path in candidate_paths(explicit, cwd):
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, "r", encoding="utf-8").read()
        except OSError as exc:
            return dict(DEFAULTS), None, f"{path}: {exc}"
        data, err = _parse(path, text)
        if err:
            return dict(DEFAULTS), None, err
        if not isinstance(data, dict):
            return dict(DEFAULTS), None, f"{path}: expected a mapping at top level"

        merged = dict(DEFAULTS)
        # Underscore keys are comments (JSON has no comment syntax; the
        # shipped template itself uses "_comment"). Warning about them
        # made the template nag about its own documentation.
        unknown = [k for k in data
                   if k not in DEFAULTS and not k.startswith("_")]
        merged.update({k: v for k, v in data.items() if k in DEFAULTS})
        warn = None
        if unknown:
            warn = f"{path}: ignoring unknown key(s): {', '.join(sorted(unknown))}"
        return merged, path, warn

    if explicit:
        return dict(DEFAULTS), None, f"{explicit}: config file not found"
    return dict(DEFAULTS), None, None


def write_template(path):
    """Write a commented starter config. Returns (ok, error)."""
    template = {
        "_comment": [
            "dz dazzle-update configuration.",
            "Omit a key to accept the default. Namespaces are derived from",
            "`gh api user/orgs` when 'namespaces' is empty -- prefer that,",
            "since a hand-written list goes stale silently.",
        ],
        "roots": [r"C:\code" if os.name == "nt"
                  else os.path.expanduser("~/code")],
        "namespaces": [],
        "personal_namespace": None,
        "exclude": ["*/baks/*", "*- Copy*"],
        "exclude_replace": False,
        "include": [],
        "member_prefixes": ["dazzle"],
        "personal_allow": [],
        # Two worked examples, from the measured rule-language design:
        # `dazzle` names its orgs and carries two exact includes whose
        # membership rests on reliance nobody has declared yet (they
        # retire to `declared` the moment a manifest names them);
        # `wtf` shows a set whose body is a repo-glob product line
        # rather than an org. Overlap is deliberate -- wtf-windows is
        # in both, via declaration on one side and the glob on the other.
        "sets": {
            "dazzle": {
                "namespaces": ["DazzleTools/*", "DazzleLib/*"],
                "include": ["djdarcy/dazzle-claude-code-config",
                            "djdarcy/dazzle-claude-code-history-viewer"],
                "exclude": ["*/.github"],
                "declared": True,
            },
            "wtf": {
                "namespaces": ["djdarcy/wtf-*"],
                "include": [],
                "exclude": [],
                "declared": False,
            },
        },
        "sort": "newest",
        "order": ["behind-upstream", "unpushed", "dirty"],
        "cache_write": True,
        "cache_max_age": 3600,
        "namespace_ttl": 86400,
        "fetch": True,
        "published": False,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(template, fh, indent=4)
            fh.write("\n")
        return True, None
    except OSError as exc:
        return False, str(exc)
