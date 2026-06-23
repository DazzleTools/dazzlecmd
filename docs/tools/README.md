# Tool Reference

Every tool dazzlecmd ships with, grouped by kit. Run `dz list` to see what's active on your machine, `dz info <tool>` for a tool's metadata, and `dz <tool> --help` for its full flags.

## Canonical kits

These hold the actual tools. **core** and **dazzletools** are always active; **media** is opt-in (`dz kit enable media`).

| Kit | Tools | Always active? | Reference |
|-----|-------|----------------|-----------|
| **core** | `f-cp`, `f-mv`, `find`, `fixpath`, `links`, `listall`, `rn`, `safedel` | yes | [core/](core/README.md) |
| **dazzletools** | 19 utilities (text/files, git/repo, Claude Code, Windows sysadmin, archives) | yes | [dazzletools/](dazzletools/README.md) |
| **media** | `vid2gif`, `vidresize`, `img2vid`, `crossfade`, `song-to-vid`, `vid-preview-maker`, `mp3me` | no (opt-in) | [media/](media/README.md) |

## Virtual kits (verb-grouped overlays)

Virtual kits don't add new tools -- they expose **alias names** for existing canonical tools under a shared prefix, so related operations group together (`dz f:cp`, `dz md:unwrap`). The canonical tool is untouched; the alias just resolves to it. Enable one with `dz kit enable <name>`.

| Kit | Alias | Resolves to |
|-----|-------|-------------|
| **f** (file ops) | `f:cp` / `f:mv` | `core:f-cp` / `core:f-mv` |
| | `f:ls` / `f:rm` | `core:listall` / `core:safedel` |
| **md** (markdown) | `md:unwrap` / `md:rm-img` | `dazzletools:md-unwrap` / `dazzletools:md-rm-img` |
| **windows** | `windows:sicacls` / `windows:fixusr` | `dazzletools:safe-icacls` / `dazzletools:fixuser` |
| | `windows:redact-msinfo` | `dazzletools:redact-msinfo` |
| **claude** | `claude:cleanup` / `claude:session-metadata` | `dazzletools:claude-cleanup` / `...-session-metadata` |
| | `claude:recover-sesslogs` / `claude:sesslog-datefix` / `claude:view` | `...-recover-sesslogs` / `...-sesslog-datefix` / `claudeview` |

See the [Kits Guide](../guides/kits.md) for how kits, virtual kits, and aggregators work.
