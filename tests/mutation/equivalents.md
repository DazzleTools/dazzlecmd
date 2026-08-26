# Triaged mutation survivors -- guarded authority, keyed by file hash

## src/dazzlecmd/projects/dazzletools/github/github.py @ 1d2f3f45e36f

- `return name.strip()` -> `return name` (in resolve_repo_name's OWNER/REPO branch) -- **don't-care** -- the CLI path pre-strips both halves in _split_issue_ref before resolution, and cmd_repo's "/" branch never stripped; only a direct API call with padded input observes the difference, which is outside the tested contract. 2026-08-10, generation mode 1 (fresh subagent).

## src/dazzlecmd/projects/dazzletools/private-init/private_init.py @ 1ed11c3a754a

Three diff-scoped sweeps, generation mode 1 (fresh subagent, zero tools, no sight of the
tests), 2026-08-26: the definition, drift detection, and --fix. Earlier headings for this
file (1c8013bc69d9, cb1170e167e3) expired as each unit changed it; every survivor below was
re-triaged against the current file rather than carried forward.

| id | mutation | label | reasoning |
|----|----------|-------|-----------|
| definition m2 | `"
".join(blocks)` -> `"".join(blocks)` | don't-care | Removes the blank line between rendered sections. Verified against git: identical verdicts. |
| definition m3 | `"# " + title` -> `"#" + title` | don't-care | Headers render `#Python`. Verified against git: a leading `#` is a comment with or without the space. |
| definition m7 | two patterns reordered inside one section | don't-care | Order matters only where a later `!` re-includes; this definition has no negations. Verified against git. |
| drift m02 | `return None` -> `return set()` for a missing file | **equivalent** | Changes which branch of `gitignore_drift` runs and nothing else; both return the same list in the same order. Demonstrated across absent, empty and comment-only files. |
| drift m07 | `if present is None` -> `if not present` | **equivalent** | A set is falsy only when empty, and the empty case returns every pattern down both paths. `is None` is kept regardless: it distinguishes "no file" from "empty file" for any future caller. |
| fix m05 | `"
".join(blocks)` -> `"".join(blocks)` | don't-care | One fewer blank line between appended sections. Blocks already end in a newline, so nothing runs together. |
| fix m06 | `not existing.endswith("
")` -> `existing.endswith("
")` | don't-care | The generator's note claims the last existing line gets concatenated with the new heading. **It does not.** Reproduced the prefix arithmetic for both a file with and without a trailing newline: the last line survives intact in every combination, and only the blank-line count changes. |
| fix m07 | `prefix += "
"` -> `prefix = "
"` | don't-care | Same as m06 -- one newline instead of two, the last existing line still terminated. Verified by the same reproduction. |

**Two of three generator notes that predicted corruption were factually wrong** (definition
m8's claimed coverage loss, fix m06's claimed concatenation), each refuted by a two-minute
check. Generator notes are prompts for triage, not findings; triage them against the
behaviour, not the prose.
