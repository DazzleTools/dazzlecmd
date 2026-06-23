# DazzleTools Kit

The DazzleTools kit contains cross-platform utilities from the [DazzleTools](https://github.com/DazzleTools) organization.

## Current Tools

### Text / files

| Tool | Description | Platform |
|------|-------------|----------|
| `dos2unix` | Pure-Python line-ending converter (dos2unix / unix2dos) | Cross-platform |
| `split` | Split text by separator with optional token filtering | Cross-platform |
| `srch-path` | Search the system PATH for executables and commands | Cross-platform |
| `delete-nul` | Delete Windows NUL device files created by an accidental `>nul` redirection | Windows |
| `md-rm-img` | Strip inline base64 image data from markdown (preserving alt text); relink references to on-disk sources | Cross-platform |
| `md-unwrap` | Unwrap hard-wrapped markdown paragraphs back to one line per paragraph (render-identical) | Cross-platform |

### git / repo

| Tool | Description | Platform |
|------|-------------|----------|
| `git` | Git repo-state inspector -- composition, workspace, and form, via quick subcommands | Cross-platform |
| `git-snapshot` | Lightweight named checkpoints for git working state (save, diff, apply, drop) | Cross-platform |
| `github` | Open GitHub project pages, issues, PRs, and releases from any git repo (needs `gh`) | Cross-platform |
| `private-init` | Initialize `private/` as a standalone versioned git repo inside any project | Cross-platform |

### Claude Code

| Tool | Description | Platform |
|------|-------------|----------|
| `claude-cleanup` | Stage and commit Claude Code state files -- noise (transient) or user (configs, skills, logs) | Cross-platform |
| `claude-session-metadata` | Catalog Claude Code sessions (lost or live) with artifact cross-referencing + navigable symlinks | Cross-platform |
| `claude-recover-sesslogs` | Salvage the surviving logger channels of sessions whose working dir is now missing | Cross-platform |
| `claude-sesslog-datefix` | Fix timestamps on Claude Code session-log directories after git operations corrupt them (`pywin32` optional) | Windows |
| `claudeview` | Open a Claude Code session in the history viewer from the command line | Cross-platform |

### Windows sysadmin

| Tool | Description | Platform |
|------|-------------|----------|
| `safe-icacls` | Loop-safe passthrough wrapper around Windows `icacls` (prunes reparse points on `/T`) | Windows |
| `fixuser` | Diagnose and repair a broken Windows user profile (the temp-profile / `C:\Users\TEMP` state) | Windows |
| `redact-msinfo` | Redact a Windows `msinfo32` export for safe sharing (PII scrub + section selection) | Cross-platform |

### Archives

| Tool | Description | Platform |
|------|-------------|----------|
| `extract-all` | Recursively extract nested archives (exe/zip/msi/7z/...) and locate files inside by glob/regex (needs 7-Zip) | Cross-platform |

## External Ownership

These tools are maintained by the DazzleTools organization and bundled with dazzlecmd for convenience. They will eventually move to their own repository as a standalone kit (`dazzletools.kit.json` pointing to a git submodule).

For documentation, issues, and contributions, see the individual tool repositories at [github.com/DazzleTools](https://github.com/DazzleTools).

## Kit Architecture

DazzleTools demonstrates the kit-as-repo pattern: a collection of related tools grouped under a single namespace, distributable as a git submodule. When the migration is complete, adding this kit to any dazzlecmd installation will be:

```bash
git submodule add https://github.com/DazzleTools/dazzletools-kit projects/dazzletools
```

See the [Kits Guide](../../guides/kits.md) for details on how kit repos work.
