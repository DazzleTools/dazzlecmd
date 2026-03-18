# DazzleTools Kit

The DazzleTools kit contains cross-platform utilities from the [DazzleTools](https://github.com/DazzleTools) organization.

## Current Tools

| Tool | Description | Platform |
|------|-------------|----------|
| `claude-cleanup` | Stage and commit Claude Code transient state files | Cross-platform |
| `dos2unix` | Pure-Python line ending converter (dos2unix/unix2dos) | Cross-platform |
| `delete-nul` | Delete Windows NUL device files created by accidental `>nul` redirection | Windows |
| `srch-path` | Search the system PATH for executables | Cross-platform |
| `split` | Split text by separator with optional token filtering | Cross-platform |

## External Ownership

These tools are maintained by the DazzleTools organization and bundled with dazzlecmd for convenience. They will eventually move to their own repository as a standalone kit (`dazzletools.kit.json` pointing to a git submodule).

For documentation, issues, and contributions, see the individual tool repositories at [github.com/DazzleTools](https://github.com/DazzleTools).

## Kit Architecture

DazzleTools demonstrates the kit-as-repo pattern: a collection of related tools grouped under a single namespace, distributable as a git submodule. When the migration is complete, adding this kit to any dazzlecmd installation will be:

```bash
git submodule add https://github.com/DazzleTools/dazzletools-kit projects/dazzletools
```

See the [Kits Guide](../../guides/kits.md) for details on how kit repos work.
