"""`dz private-init` carries one definition of what a correct vault ignores.

The definition is not decoration: a vault created before a tool existed cannot
learn about that tool on its own, so the same declaration has to serve both
creating a new vault and judging an old one. These tests ask git itself whether
the patterns do their job, rather than asserting that a string contains a
substring -- a vault whose .gitignore merely *mentions* `.gauntlet/` while some
other rule re-includes it is still broken, and only `git check-ignore` notices.

Regression origin: a `/gauntlet` run's ledger and VS Code's per-folder settings
were both landing inside private vaults untracked, and `CLAUDE.local.md` was
doing the same one level up in the project. All three are written by tools and
belong in no history.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "dazzlecmd" / "projects" / "dazzletools" / "private-init" / "private_init.py"
)


def _load_private_init():
    """Load private_init.py by path -- its directory is hyphenated, so it is not importable."""
    spec = importlib.util.spec_from_file_location("private_init_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def private_init():
    if not MODULE_PATH.is_file():
        pytest.skip(f"private_init.py not found at {MODULE_PATH}")
    return _load_private_init()


def _git(args, cwd):
    return subprocess.run(
        ["git"] + args, cwd=str(cwd), capture_output=True, text=True
    )


def _repo_with_gitignore(tmp_path, text):
    """A real git repo whose .gitignore is `text`, so git's own matcher can be asked."""
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(["init", "-q"], repo).returncode == 0
    (repo / ".gitignore").write_text(text, encoding="utf-8")
    return repo


def _is_ignored(repo, relative_path):
    """git's verdict, not ours: check-ignore honours every layer and every negation."""
    return _git(["check-ignore", "-q", "--", relative_path], repo).returncode == 0


# --- the definition, as git sees it -------------------------------------------------


@pytest.mark.parametrize(
    "path_in_vault",
    [
        ".gauntlet/private-gitignore-assumptions/run-log.md",  # a /gauntlet run's ledger
        ".vscode/settings.json",                               # written when the folder is opened
    ],
)
def test_a_new_vault_ignores_what_our_tools_write(private_init, tmp_path, path_in_vault):
    """Agent and editor working state must never reach a vault's history."""
    repo = _repo_with_gitignore(tmp_path, private_init.PRIVATE_GITIGNORE)
    assert _is_ignored(repo, path_in_vault), (
        f"{path_in_vault} is not ignored by the vault definition; "
        "a tool's working state would be committable"
    )


def test_the_parent_definition_covers_the_recovery_pointer(private_init, tmp_path):
    """`CLAUDE.local.md` lives beside the vault, in the project -- the vault cannot cover it."""
    text = private_init.render_gitignore(private_init.PARENT_GITIGNORE_SECTIONS)
    repo = _repo_with_gitignore(tmp_path, text)
    assert _is_ignored(repo, "CLAUDE.local.md")


# One representative path per declared pattern. Dropping any pattern from the
# definition -- the kind of edit that looks like tidying a duplicate -- must fail
# here rather than quietly shrinking what a vault ignores.
PATTERN_EXAMPLES = [
    ("__pycache__/", "__pycache__/x.pyc"),
    ("*.py[cod]", "build.pyc"),
    ("*.so", "ext.so"),
    ("*.swp", "notes.swp"),
    ("*~", "notes~"),
    ("*.*~", "notes.md~"),
    (".*.swp", ".notes.swp"),
    (".vscode/", ".vscode/settings.json"),
    (".DS_Store", ".DS_Store"),
    ("Thumbs.db", "Thumbs.db"),
    ("desktop.ini", "desktop.ini"),
    ("*.tmp", "scratch.tmp"),
    ("*.bak", "notes.md.bak"),
    (".gauntlet/", ".gauntlet/slug/run-log.md"),
]


@pytest.mark.parametrize("pattern,example", PATTERN_EXAMPLES)
def test_every_declared_pattern_actually_ignores_something(
    private_init, tmp_path, pattern, example
):
    """Each pattern earns its place: git must ignore the thing it exists for."""
    repo = _repo_with_gitignore(tmp_path, private_init.PRIVATE_GITIGNORE)
    assert _is_ignored(repo, example), (
        f"{example} is not ignored -- the {pattern!r} pattern is missing or overridden"
    )


def test_the_examples_cover_every_declared_pattern(private_init):
    """The table above is only a safety net if nothing declared escapes it."""
    declared = set(private_init.gitignore_patterns(private_init.PRIVATE_GITIGNORE_SECTIONS))
    covered = {pattern for pattern, _example in PATTERN_EXAMPLES}
    assert declared == covered, (
        f"declared but untested: {sorted(declared - covered)}; "
        f"tested but no longer declared: {sorted(covered - declared)}"
    )


# --- the definition is addressable, not only renderable -----------------------------


def test_every_declared_pattern_survives_rendering(private_init):
    """cmd_status has to compare against the same patterns cmd_init writes."""
    rendered = private_init.PRIVATE_GITIGNORE
    for pattern in private_init.gitignore_patterns(private_init.PRIVATE_GITIGNORE_SECTIONS):
        assert pattern in rendered.splitlines(), f"{pattern} declared but not rendered"


def test_rendered_definition_is_what_a_new_vault_receives(private_init):
    """The blob cmd_init writes is the rendered definition, not a second copy of it."""
    assert private_init.PRIVATE_GITIGNORE == private_init.render_gitignore(
        private_init.PRIVATE_GITIGNORE_SECTIONS
    )


# --- flattening, on input whose order and shape are known ---------------------------


def test_flattening_preserves_declaration_order_and_drops_nothing(private_init):
    """`cmd_status` compares against this list, so a lost or reordered pattern is drift it cannot see.

    Deliberately unsorted input: a flatten that quietly sorts would look correct
    against alphabetical fixtures and wrong against a real definition.
    """
    sections = [("B section", ["zulu", "alpha"]), ("A section", ["mike"])]
    assert private_init.gitignore_patterns(sections) == ["zulu", "alpha", "mike"]


def test_flattening_keeps_the_last_pattern_of_every_section(private_init):
    """An off-by-one here silently shrinks what drift detection can notice."""
    sections = [("one", ["a", "LAST-OF-ONE"]), ("two", ["b", "LAST-OF-TWO"])]
    flattened = private_init.gitignore_patterns(sections)
    assert "LAST-OF-ONE" in flattened and "LAST-OF-TWO" in flattened


# --- drift: does an existing file carry the current definition? ----------------------


VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES = """\
# Python
__pycache__/
*.py[cod]
*.so

# Editors
*.swp
*~
*.*~
.*.swp

# OS
.DS_Store
Thumbs.db
desktop.ini

# Temp files
*.tmp
*.bak
"""


def test_a_vault_predating_an_entry_is_reported_as_drifted(private_init, tmp_path):
    """The 18-line template several vaults still carry, named exactly."""
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES, encoding="utf-8")
    assert private_init.gitignore_drift(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS
    ) == [".vscode/", ".gauntlet/"]


def test_a_current_vault_reports_no_drift(private_init, tmp_path):
    path = tmp_path / ".gitignore"
    path.write_text(private_init.PRIVATE_GITIGNORE, encoding="utf-8")
    assert private_init.gitignore_drift(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS
    ) == []


def test_a_missing_file_has_drifted_from_everything(private_init, tmp_path):
    """A project with no .gitignore at all is not 'up to date'."""
    missing = private_init.gitignore_drift(
        str(tmp_path / "absent"), private_init.PARENT_GITIGNORE_SECTIONS
    )
    assert missing == ["CLAUDE.local.md"]


def test_drift_ignores_comments_and_blank_lines(private_init, tmp_path):
    """A pattern that only appears inside a comment has not been declared."""
    path = tmp_path / ".gitignore"
    path.write_text("\n\n# CLAUDE.local.md\n\n", encoding="utf-8")
    assert private_init.gitignore_drift(
        str(path), private_init.PARENT_GITIGNORE_SECTIONS
    ) == ["CLAUDE.local.md"]


def test_drift_reports_in_declaration_order(private_init, tmp_path):
    """The report reads in the order the definition declares, not alphabetically."""
    path = tmp_path / ".gitignore"
    path.write_text("", encoding="utf-8")
    sections = [("first", ["zulu", "alpha"]), ("second", ["mike"])]
    assert private_init.gitignore_drift(str(path), sections) == ["zulu", "alpha", "mike"]


def test_report_names_every_missing_pattern_and_the_fix(private_init, tmp_path, capsys):
    """A drift report nobody can act on is not a report."""
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES, encoding="utf-8")
    missing = private_init.report_gitignore_drift(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS, "Vault ignores", "To fix, run X"
    )
    out = capsys.readouterr().out
    assert missing == [".vscode/", ".gauntlet/"]
    for pattern in missing:
        assert pattern in out
    assert "To fix, run X" in out


def test_report_says_so_when_nothing_has_drifted(private_init, tmp_path, capsys):
    path = tmp_path / ".gitignore"
    path.write_text(private_init.PRIVATE_GITIGNORE, encoding="utf-8")
    private_init.report_gitignore_drift(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS, "Vault ignores", "To fix, run X"
    )
    out = capsys.readouterr().out
    assert "up to date" in out
    assert "To fix" not in out


# --- what counts as a declared line --------------------------------------------------


def test_a_directory_at_the_gitignore_path_is_treated_as_absent(private_init, tmp_path):
    """`dz private-init --status` must report, not crash, on a pathological tree."""
    weird = tmp_path / ".gitignore"
    weird.mkdir()
    missing = private_init.gitignore_drift(
        str(weird), private_init.PARENT_GITIGNORE_SECTIONS
    )
    assert missing == ["CLAUDE.local.md"]


def test_a_comment_is_not_a_declaration(private_init, tmp_path):
    """A pattern that only appears commented out has not been declared.

    Written against a definition whose pattern is itself comment-shaped, because
    a definition of ordinary patterns cannot tell the two apart: every real
    pattern differs from every comment line anyway, so the distinction only
    becomes observable when they could collide.
    """
    path = tmp_path / ".gitignore"
    path.write_text("# hello\n", encoding="utf-8")
    sections = [("odd", ["# hello"])]
    assert private_init.gitignore_drift(str(path), sections) == ["# hello"]


def test_a_line_that_merely_contains_a_hash_is_a_declaration(private_init, tmp_path):
    """Only a leading `#` starts a comment; `#` elsewhere is part of the pattern."""
    path = tmp_path / ".gitignore"
    path.write_text("build#tmp/\n", encoding="utf-8")
    sections = [("odd", ["build#tmp/"])]
    assert private_init.gitignore_drift(str(path), sections) == []


def test_blank_lines_are_not_declarations(private_init, tmp_path):
    path = tmp_path / ".gitignore"
    path.write_text("\n   \n\n", encoding="utf-8")
    sections = [("odd", [""])]
    assert private_init.gitignore_drift(str(path), sections) == [""]


# --- --fix: append what drifted, touch nothing else -----------------------------------


VAULT_WITH_ITS_OWN_RULES = VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES + """
# rules this definition knows nothing about
secrets/
!secrets/README.md
"""


def test_fix_leaves_no_drift(private_init, tmp_path):
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES, encoding="utf-8")
    added = private_init.apply_gitignore_drift(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS
    )
    assert added == [".vscode/", ".gauntlet/"]
    assert private_init.gitignore_drift(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS
    ) == []


def test_fix_is_idempotent(private_init, tmp_path):
    """A fleet-wide repair has to converge, not accumulate."""
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES, encoding="utf-8")
    private_init.apply_gitignore_drift(str(path), private_init.PRIVATE_GITIGNORE_SECTIONS)
    after_first = path.read_text(encoding="utf-8")
    assert private_init.apply_gitignore_drift(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS
    ) == []
    assert path.read_text(encoding="utf-8") == after_first


def test_fix_preserves_rules_the_definition_does_not_know(private_init, tmp_path):
    """Append-only: a project's own exclusions are not ours to rewrite."""
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_WITH_ITS_OWN_RULES, encoding="utf-8")
    private_init.apply_gitignore_drift(str(path), private_init.PRIVATE_GITIGNORE_SECTIONS)
    after = path.read_text(encoding="utf-8")
    assert VAULT_WITH_ITS_OWN_RULES in after, "existing content was rewritten, not appended to"


def test_fix_preserves_a_negation_and_its_position(private_init, tmp_path):
    """`!` re-inclusions depend on what precedes them; appending must not reorder."""
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_WITH_ITS_OWN_RULES, encoding="utf-8")
    private_init.apply_gitignore_drift(str(path), private_init.PRIVATE_GITIGNORE_SECTIONS)
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    assert lines.index("secrets/") < lines.index("!secrets/README.md")


def test_dry_run_reports_without_writing(private_init, tmp_path):
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES, encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    would = private_init.apply_gitignore_drift(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS, dry_run=True
    )
    assert would == [".vscode/", ".gauntlet/"]
    assert path.read_text(encoding="utf-8") == before


def test_fix_creates_a_file_that_does_not_exist(private_init, tmp_path):
    """A project with no .gitignore is drifted from everything, and fixable."""
    path = tmp_path / "sub" / ".gitignore"
    added = private_init.apply_gitignore_drift(
        str(path), private_init.PARENT_GITIGNORE_SECTIONS
    )
    assert added == ["CLAUDE.local.md"]
    assert path.is_file()
    assert private_init.gitignore_drift(
        str(path), private_init.PARENT_GITIGNORE_SECTIONS
    ) == []


def test_fix_separates_its_addition_from_existing_content(private_init, tmp_path):
    """A file with no trailing newline must not have a pattern glued to its last line."""
    path = tmp_path / ".gitignore"
    path.write_text("secrets/", encoding="utf-8")  # deliberately no trailing newline
    private_init.apply_gitignore_drift(str(path), private_init.PARENT_GITIGNORE_SECTIONS)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "secrets/" in lines, "the last existing line was corrupted"
    assert "CLAUDE.local.md" in lines


def test_fix_reports_what_it_did(private_init, tmp_path, capsys):
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES, encoding="utf-8")
    private_init.fix_gitignore(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS, "Vault ignores"
    )
    out = capsys.readouterr().out
    assert "added 2 pattern(s)" in out
    assert ".gauntlet/" in out and ".vscode/" in out


def test_fix_says_so_when_there_is_nothing_to_do(private_init, tmp_path, capsys):
    path = tmp_path / ".gitignore"
    path.write_text(private_init.PRIVATE_GITIGNORE, encoding="utf-8")
    private_init.fix_gitignore(
        str(path), private_init.PRIVATE_GITIGNORE_SECTIONS, "Vault ignores"
    )
    assert "nothing to fix" in capsys.readouterr().out


def test_fix_appends_only_the_sections_that_were_missing_something(private_init, tmp_path):
    """A repair that adds bare headings for sections already satisfied is noise in every file it touches."""
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES, encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    private_init.apply_gitignore_drift(str(path), private_init.PRIVATE_GITIGNORE_SECTIONS)
    appended = path.read_text(encoding="utf-8")[len(before):]
    for satisfied in ("# Python", "# OS", "# Temp files"):
        assert satisfied not in appended, f"{satisfied!r} was appended with nothing under it"
    assert "# Editors" in appended and "# Agent working state" in appended


def test_fix_leaves_the_file_newline_terminated(private_init, tmp_path):
    """Whatever appends after us -- another tool, another run -- depends on it."""
    path = tmp_path / ".gitignore"
    path.write_text(VAULT_TEMPLATE_BEFORE_AGENT_ENTRIES, encoding="utf-8")
    private_init.apply_gitignore_drift(str(path), private_init.PRIVATE_GITIGNORE_SECTIONS)
    assert path.read_text(encoding="utf-8").endswith("\n")


# --- standing inside a vault ---------------------------------------------------------


def _vault_fixture(tmp_path):
    """A project containing a vault that is its own git repo."""
    proj = tmp_path / "proj"
    vault = proj / "private"
    vault.mkdir(parents=True)
    assert _git(["init", "-q"], vault).returncode == 0
    return proj, vault


def test_a_vault_is_recognised_as_one(private_init, tmp_path):
    proj, vault = _vault_fixture(tmp_path)
    assert private_init.looks_like_a_vault(str(vault)) == str(proj)


def test_a_project_is_not_mistaken_for_a_vault(private_init, tmp_path):
    """The parent of a vault must not itself look like one, or the hint fires everywhere."""
    proj, _vault = _vault_fixture(tmp_path)
    assert _git(["init", "-q"], proj).returncode == 0
    assert private_init.looks_like_a_vault(str(proj)) is None


def test_a_directory_merely_named_private_is_not_a_vault(private_init, tmp_path):
    """Being named `private` is not enough -- a vault is its own git repository."""
    d = tmp_path / "private"
    d.mkdir()
    assert private_init.looks_like_a_vault(str(d)) is None


def test_a_custom_private_dir_name_is_honoured(private_init, tmp_path):
    proj = tmp_path / "proj"
    vault = proj / "notes"
    vault.mkdir(parents=True)
    assert _git(["init", "-q"], vault).returncode == 0
    assert private_init.looks_like_a_vault(str(vault), "notes") == str(proj)
    assert private_init.looks_like_a_vault(str(vault), "private") is None


def test_standing_in_a_vault_says_so_and_names_the_command(private_init, tmp_path, capsys):
    """The report a person actually reads when they run it from the wrong place."""
    proj, vault = _vault_fixture(tmp_path)
    rc = private_init.report_missing_private(
        str(vault / "private"), str(vault), "private", "--fix"
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "inside a vault already" in out
    assert str(proj) in out
    assert "--fix" in out


def test_an_ordinary_missing_private_reports_as_it_always_did(private_init, tmp_path, capsys):
    """Guard: the hint must not appear for the common case it was never about."""
    plain = tmp_path / "plain"
    plain.mkdir()
    rc = private_init.report_missing_private(
        str(plain / "private"), str(plain), "private", "--status"
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "does not exist" in out
    assert "inside a vault" not in out


def test_a_trailing_separator_does_not_hide_a_vault(private_init, tmp_path):
    """`cd private/` and tab-completion both produce trailing separators."""
    proj, vault = _vault_fixture(tmp_path)
    assert private_init.looks_like_a_vault(str(vault) + os.sep) == str(proj)


def test_a_relative_vault_path_resolves_to_a_usable_parent(private_init, tmp_path, monkeypatch):
    """A bare relative name must not yield an empty parent -- the suggestion would name nothing."""
    proj, _vault = _vault_fixture(tmp_path)
    monkeypatch.chdir(proj)
    parent = private_init.looks_like_a_vault("private")
    assert parent != "", "an empty parent would render as: dz private-init --fix \"\""
    assert parent is None or os.path.isdir(parent)


def test_the_suggested_command_names_the_parent_not_the_vault(private_init, tmp_path, capsys):
    """The whole point of the hint is the path the caller should have used instead.

    Asserted on the suggestion line itself: the vault path *contains* the project
    path as a prefix, so a plain `project in output` check passes even when the
    command names the vault -- which is exactly the bug this pins.
    """
    proj, vault = _vault_fixture(tmp_path)
    private_init.report_missing_private(
        str(vault / "private"), str(vault), "private", "--fix"
    )
    suggestion = [
        ln for ln in capsys.readouterr().out.splitlines() if "Did you mean" in ln
    ]
    assert len(suggestion) == 1, "expected exactly one suggestion line"
    assert f'"{proj}"' in suggestion[0], f"suggestion names the wrong path: {suggestion[0]}"
    assert f'"{vault}"' not in suggestion[0], "suggestion repeats the path the caller already used"
