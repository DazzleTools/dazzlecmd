# Triaged mutation survivors -- guarded authority, keyed by file hash

## src/dazzlecmd/projects/dazzletools/github/github.py @ 1d2f3f45e36f

- `return name.strip()` -> `return name` (in resolve_repo_name's OWNER/REPO branch) -- **don't-care** -- the CLI path pre-strips both halves in _split_issue_ref before resolution, and cmd_repo's "/" branch never stripped; only a direct API call with padded input observes the difference, which is outside the tested contract. 2026-08-10, generation mode 1 (fresh subagent).
