# dz dazzle-update

Ecosystem-wide update/status scanner. Answers "what do I need to pull, push, or reinstall?" across every namespace you own, in one command, without checking each repo by hand.

Read-only by default. `--fix` applies exactly two provably-safe operations and refuses everything else.

## Why it exists

Keeping a multi-repo ecosystem current is not one question, it is four, and they go stale independently:

- **git** says whether a checkout is behind, ahead, or dirty.
- **pip** says which version of your own code the environment actually executes.
- **the filesystem** says what is physically present, including repos with no remote at all.
- **PyPI** says what the world can install.

Each is authoritative for something and blind to something else, and the blind spots are close to inverted. A repo can be perfectly clean in git while the environment runs months-old metadata for it. A repo can exist on exactly one machine, backed up nowhere, and be invisible to every listing. Checking one axis and concluding "up to date" is how a box drifts without anyone noticing.

This tool joins all four against **canonical repo identity** and reports the asymmetries.

## Usage

```
dz dazzle-update                    Report what needs attention
dz dazzle-update --published        Also compare against PyPI (network)
dz dazzle-update --json             Machine-readable, for cross-box diffing
dz dazzle-update --fix --dry-run    Show what --fix would do
dz dazzle-update --fix              Apply ff-only pulls + editable reinstalls
```

Narrowing the output:

```
dz dazzle-update --only behind      Just what a pull would advance
dz dazzle-update --only dirty       Just uncommitted work
dz dazzle-update --skip missing     Everything except not-cloned
dz dazzle-update --all              Include repos with nothing to do
dz dazzle-update --list-kinds       All finding kinds and their aliases
dz dazzle-update --scope DazzleLib  One namespace only
```

Speed and freshness:

```
dz dazzle-update --cached           Replay the last scan (~5s vs ~70s)
dz dazzle-update --cached --max-age 600
dz dazzle-update --no-fetch         Skip refreshing remotes (offline)
```

## What it reports

| Finding | Meaning |
|---|---|
| `behind-upstream` | The remote has commits you do not. A pull would advance these. |
| `source-missing` | An editable install points at a directory that no longer exists. |
| `stale-install-metadata` | The environment records an older version than the source tree holds. |
| `install-behind-published` | PyPI is ahead of what is installed here. |
| `unpushed` | Commits that exist only on this machine. |
| `stale-remote-url` | The configured URL no longer names the repo; fetches follow a redirect. |
| `no-upstream` | No remote at all. This work exists nowhere else. |
| `dirty` | Uncommitted changes. |
| `not-cloned` | Present in a namespace you own, absent here. |
| `excluded-by-policy` | Deliberately out of scope. |
| `clean` | Scanned, nothing to do. Hidden unless `--all`. |

Sections are ordered by what you should *do*, not by abstract severity, and that order is configurable. Rows within a section sort newest-first by default (`--sort oldest|name`).

## Fetching

`behind` is measured against remote-tracking refs, so it is only as fresh as the last fetch. The tool therefore **fetches by default** — otherwise a repo with commits waiting reports zero behind and reads as current, which defeats the point.

Fetching touches remote-tracking refs only: no local branch, no working tree, no index. It is safe to run against a repo you are mid-edit on. Fetches run in parallel with a per-repo timeout, and failures are reported rather than silently producing stale counts.

`--no-fetch` skips it for offline use, and says so in the output.

## What `--fix` will and will not do

It does exactly two things:

- `git pull --ff-only` on a repo that is clean and strictly behind.
- `pip install -e <path> --no-deps` where install metadata trails the source tree.

It refuses, with a reason, on everything else. It will not stash (auto-stashing loses work), will not merge, will not push, will not rewrite a remote URL, and will not clone. It updates `dazzlecmd` last, because `dz` runs from an editable install of its own source.

## Configuration

Searched in order: `--config PATH`, then `./.dazzle-update.json`, then `<user config dir>/dazzlecmd/dazzle-update.json`. YAML is accepted if PyYAML is installed but never required.

```
dz dazzle-update --init-config      Write a starter config
```

Keys include `roots`, `namespaces`, `personal_namespace`, `exclude` / `include` / `exclude_replace`, `member_prefixes`, `personal_allow`, `order`, `sort`, `fetch`, `published`, and the cache settings.

Two behaviours worth knowing:

- **`namespaces` is best left empty.** It then derives from `gh api user/orgs`, which is self-maintaining. A hand-written list goes stale silently — that is how a whole active namespace went unnoticed during development.
- **`order` is partial.** Whatever you name goes first, in your order; everything else follows in the built-in order. A short list does not hide the rest. Hiding is what `--only` and `--skip` are for, per invocation.

`include` beats `exclude`, so a single repo can be rescued from a broad archive pattern without rewriting the pattern.

## Caching

Three things are cached with deliberately different lifetimes: identity resolution persistently (transfers are rare), scan results for replay (`--cached`), and fetch results never — being current is the point.

The cache stores **observations, not verdicts**: findings are recomputed on replay, so changing `--only` or `order` reflects your new settings rather than a frozen rendering. Replayed output always states its age, because presenting stale state as current is the exact failure this tool exists to catch.

## Requirements

`git` and `gh` (authenticated). Without `gh`, namespace listing is skipped and the tool says so — an unauthenticated run would silently omit private repos, which is a dangerous false negative for an inventory.

## Exit codes

`0` report produced, `2` bad arguments or a refused cache.
