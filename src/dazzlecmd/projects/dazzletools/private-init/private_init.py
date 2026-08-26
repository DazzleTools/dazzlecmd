"""
private-init - Initialize private/ as a standalone versioned git repo.

Creates (or converts) a project's private/ directory into its own git
repository, completely invisible to the parent repo thanks to .gitignore.

This replaces the complex 4-layer private content protection system
(gitignore + .git/info/exclude + pre-commit hooks + content stripping)
with simple architectural separation: private/ is literally a different repo.

Usage:
    dz private-init                      # init in current project
    dz private-init /path/to/project     # init in specified project
    dz private-init --remote <url>       # init with remote for backup
    dz private-init --adopt              # convert existing private/ content
    dz private-init --status             # check if private/ is a git repo
    dz private-init --fix                # add the .gitignore patterns it is missing
    dz private-init --fix --dry-run      # show what --fix would add
"""

import argparse
import os
import subprocess
import sys


# Standard private folder structure
PRIVATE_STRUCTURE = [
    "claude",
    "claude/commits",
    "claude/issues",
    "docs",
    "notes",
]

# What a correct private repo ignores, as (section, patterns) pairs.
#
# This is the definition, not just a template: `cmd_init` renders it into a new
# vault's .gitignore, and `cmd_status` compares an existing vault against it and
# reports what has drifted. Adding a pattern here therefore fixes new vaults and
# makes old ones report as out of date -- which is the point, since a vault
# created a year ago cannot learn about a tool written last week on its own.
PRIVATE_GITIGNORE_SECTIONS = [
    ("Python", ["__pycache__/", "*.py[cod]", "*.so"]),
    ("Editors", ["*.swp", "*~", "*.*~", ".*.swp", ".vscode/"]),
    ("OS", [".DS_Store", "Thumbs.db", "desktop.ini"]),
    ("Temp files", ["*.tmp", "*.bak"]),
    ("Agent working state -- written by tools, never versioned", [".gauntlet/"]),
]

# What the PARENT project must ignore so agent scratch state stays out of its
# history. The vault's own .gitignore cannot cover these: they live beside the
# vault, in the project, one level up.
PARENT_GITIGNORE_SECTIONS = [
    ("Agent working state -- written by tools, never versioned", ["CLAUDE.local.md"]),
]


def render_gitignore(sections):
    """Render (section, patterns) pairs into .gitignore text."""
    blocks = []
    for title, patterns in sections:
        blocks.append("# " + title + "\n" + "\n".join(patterns) + "\n")
    return "\n".join(blocks)


def gitignore_patterns(sections):
    """Every pattern in a definition, flattened, in declaration order."""
    return [pattern for _title, patterns in sections for pattern in patterns]


# Rendered form of the vault definition, for writing a new vault's .gitignore.
PRIVATE_GITIGNORE = render_gitignore(PRIVATE_GITIGNORE_SECTIONS)


def run_git(args, cwd=None, capture=True):
    """Run a git command and return (returncode, stdout, stderr)."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 1, "", "git not found on PATH"


def is_git_repo(path):
    """Check if a directory is its own git repository root.

    Distinguishes between 'this directory IS a git repo' and
    'this directory is inside a parent git repo'. We check for
    .git (directory or file) directly in the path.
    """
    git_path = os.path.join(path, ".git")
    return os.path.exists(git_path)


def find_project_root(start_path):
    """Walk up from start_path to find the nearest git repo root.

    Checks for .git as either a directory (normal repo) or a file
    (worktree pointer like 'gitdir: /path/to/.git/worktrees/name').
    """
    current = os.path.abspath(start_path)
    for _ in range(20):
        git_path = os.path.join(current, ".git")
        if os.path.isdir(git_path) or os.path.isfile(git_path):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def get_project_name(project_root):
    """Derive a project name from the directory."""
    # If this is a repokit-style layout (parent/local/), use the parent name
    basename = os.path.basename(project_root)
    if basename == "local":
        return os.path.basename(os.path.dirname(project_root))
    return basename


def check_gitignore_covers_private(private_path, git_root):
    """Check if git actually ignores the private/ path.

    Uses 'git check-ignore' which respects all gitignore layers
    (.gitignore at any level, .git/info/exclude, global gitignore).
    """
    if not git_root:
        return False
    rc, _, _ = run_git(
        ["check-ignore", "-q", private_path],
        cwd=git_root,
    )
    return rc == 0


def ensure_private_ignored(target, private_dir_name, private_path, git_root):
    """Check if private/ is ignored and warn if not. Never auto-creates files."""
    if check_gitignore_covers_private(private_path, git_root):
        print(f"  Gitignore: {private_dir_name}/ is excluded [OK]")
        return

    if not git_root:
        # No parent git repo -- nothing to worry about
        return

    # Not ignored -- warn and suggest
    print(f"  WARNING: {private_dir_name}/ is NOT ignored by the parent git repo!")
    print(f"  To fix, add one of these to a .gitignore:")

    # Figure out the relative path from git root to target
    rel = os.path.relpath(target, git_root)
    if rel == ".":
        print(f"    In {git_root}/.gitignore:  /{private_dir_name}/")
    else:
        rel_posix = rel.replace("\\", "/")
        print(f"    In {git_root}/.gitignore:  {rel_posix}/{private_dir_name}/")
        print(f"    Or in {target}/.gitignore: /{private_dir_name}/")


def _declared_lines(gitignore_path):
    """The non-comment, non-blank lines of a .gitignore, as a set."""
    if not os.path.isfile(gitignore_path):
        return None
    lines = set()
    with open(gitignore_path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if line and not line.startswith("#"):
                lines.add(line)
    return lines


def gitignore_drift(gitignore_path, sections):
    """Declared patterns a .gitignore does not carry, in declaration order.

    The comparison is textual on purpose. The question a drift report answers is
    "does this file carry the current definition?", and the definition is also
    how future entries reach vaults that already exist -- so a file that ignores
    the same thing by a differently-spelled pattern is reported as drifted, and
    that is the intended answer rather than a false positive. A file that does
    not exist at all has drifted from every pattern.
    """
    present = _declared_lines(gitignore_path)
    if present is None:
        return list(gitignore_patterns(sections))
    return [p for p in gitignore_patterns(sections) if p not in present]


def report_gitignore_drift(gitignore_path, sections, label, fix_hint):
    """Print drift for one file. Returns the missing patterns."""
    missing = gitignore_drift(gitignore_path, sections)
    if not missing:
        print(f"  {label}: up to date with the current definition [OK]")
        return missing
    print(f"  {label}: {len(missing)} pattern(s) missing -- this file predates them")
    for pattern in missing:
        print(f"    {pattern}")
    print(f"  {fix_hint}")
    return missing


def apply_gitignore_drift(gitignore_path, sections, dry_run=False):
    """Append the declared patterns a file lacks, under their own section headings.

    Append-only by construction. The file may carry rules this definition knows
    nothing about -- a project's own exclusions, another tool's block, a `!`
    re-inclusion whose position matters -- and none of that is ours to rewrite.
    Idempotent: a second call finds no drift and writes nothing, so running it
    on a whole fleet of checkouts converges instead of accumulating.

    Returns the patterns added (or, under dry_run, the ones that would be).
    """
    missing = gitignore_drift(gitignore_path, sections)
    if not missing or dry_run:
        return missing

    blocks = []
    for title, patterns in sections:
        absent = [p for p in patterns if p in missing]
        if absent:
            blocks.append("# " + title + "\n" + "\n".join(absent) + "\n")
    addition = "\n".join(blocks)

    existing = ""
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, encoding="utf-8", errors="replace") as handle:
            existing = handle.read()
    prefix = ""
    if existing and not existing.endswith("\n"):
        prefix = "\n"
    if existing:
        prefix += "\n"

    parent = os.path.dirname(gitignore_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(gitignore_path, "a", encoding="utf-8") as handle:
        handle.write(prefix + addition)
    return missing


def fix_gitignore(gitignore_path, sections, label, dry_run=False):
    """Apply drift to one file and say what happened."""
    added = apply_gitignore_drift(gitignore_path, sections, dry_run=dry_run)
    if not added:
        print(f"  {label}: nothing to fix [OK]")
        return added
    verb = "would add" if dry_run else "added"
    print(f"  {label}: {verb} {len(added)} pattern(s) to {gitignore_path}")
    for pattern in added:
        print(f"    {pattern}")
    return added


def looks_like_a_vault(target, private_dir_name="private"):
    """Is `target` itself a private vault rather than a project containing one?

    True when the directory is its own git repository, is named as the private
    directory, and its parent holds it under that name. Every tool in this family
    resolves `private/` relative to where it was told to look, so a person standing
    inside a vault asks about a vault nested inside a vault -- which never exists.
    Git works from any subdirectory; this reports the mismatch instead of guessing,
    because silently operating on a directory other than the one named is its own
    surprise.

    Returns the parent project path, or None.
    """
    if not target or not is_git_repo(target):
        return None
    if os.path.basename(os.path.normpath(target)) != private_dir_name:
        return None
    # No "does the parent really hold it?" check here on purpose: given the two
    # conditions above, os.path.join(parent, private_dir_name) IS normpath(target),
    # and target is already known to be a directory -- so such a check can never
    # fail. A mutation sweep found it: two mutants that broke it survived, because
    # there was nothing to break. Dead code that reads as a guard is worse than no
    # guard, because the next reader believes something is being verified.
    parent = os.path.dirname(os.path.normpath(target))
    return parent or None


def report_missing_private(private_path, target, private_dir_name, verb):
    """Say `private/` is absent -- and, when the caller is standing in a vault, say that instead."""
    print(f"  {private_dir_name}/ does not exist at {private_path}")
    parent = looks_like_a_vault(target, private_dir_name)
    if parent:
        print(f"  You appear to be inside a vault already: {target} is its own git repo")
        print(f"  and its parent lists it as {private_dir_name}/.")
        print(f'  Did you mean:  dz private-init {verb} "{parent}"')
    return 1


def cmd_fix(private_path, project_root, target=None, private_dir_name="private", dry_run=False):
    """Bring a vault's and its project's .gitignore up to the current definition."""
    if not os.path.isdir(private_path):
        verb = "--fix --dry-run" if dry_run else "--fix"
        return report_missing_private(private_path, target, private_dir_name, verb)

    fix_gitignore(
        os.path.join(private_path, ".gitignore"),
        PRIVATE_GITIGNORE_SECTIONS,
        "Vault ignores",
        dry_run=dry_run,
    )
    if project_root:
        fix_gitignore(
            os.path.join(project_root, ".gitignore"),
            PARENT_GITIGNORE_SECTIONS,
            "Project ignores",
            dry_run=dry_run,
        )
    else:
        print("  Project ignores: no parent git repo found -- skipped")
    return 0


def cmd_status(private_path, project_root, target=None, private_dir_name="private"):
    """Check and report the status of private/."""
    if not os.path.isdir(private_path):
        return report_missing_private(private_path, target, private_dir_name, "--status")

    if not is_git_repo(private_path):
        # Count files to show what's there
        file_count = sum(len(files) for _, _, files in os.walk(private_path))
        print(f"  private/ exists but is NOT a git repo ({file_count} files)")
        print(f"  Run 'dz private-init --adopt' to convert it")
        return 1

    # It's a git repo -- show status
    rc, stdout, _ = run_git(["log", "--oneline", "-5"], cwd=private_path)
    rc2, branch, _ = run_git(["branch", "--show-current"], cwd=private_path)
    rc3, remote, _ = run_git(["remote", "-v"], cwd=private_path)

    print(f"  private/ is a git repo")
    print(f"  Path:   {private_path}")
    if branch:
        print(f"  Branch: {branch}")
    if remote:
        print(f"  Remote: {remote.splitlines()[0] if remote else '(none)'}")
    else:
        print(f"  Remote: (none -- local only)")
    if stdout:
        print(f"  Recent commits:")
        for line in stdout.splitlines():
            print(f"    {line}")
    else:
        print(f"  No commits yet")

    # Check gitignore coverage
    if check_gitignore_covers_private(private_path, project_root):
        print(f"  Gitignore: {private_dir_name}/ is excluded [OK]")
    elif project_root:
        print(f"  Gitignore: WARNING - {private_dir_name}/ may not be ignored by parent repo!")

    # Compare both .gitignore files against the current definition. A vault created
    # before a tool existed cannot learn about it on its own, so drift is reported
    # rather than assumed absent.
    report_gitignore_drift(
        os.path.join(private_path, ".gitignore"),
        PRIVATE_GITIGNORE_SECTIONS,
        "Vault ignores",
        "To fix, run 'dz private-init --fix' or add the lines above to "
        + os.path.join(private_path, ".gitignore"),
    )
    if project_root:
        report_gitignore_drift(
            os.path.join(project_root, ".gitignore"),
            PARENT_GITIGNORE_SECTIONS,
            "Project ignores",
            "To fix, run 'dz private-init --fix' or add the lines above to "
            + os.path.join(project_root, ".gitignore"),
        )

    return 0


def cmd_init(private_path, project_root, project_name, target, private_dir_name="private", remote_url=None, adopt=False):
    """Initialize private/ as a git repo."""
    existing_content = os.path.isdir(private_path) and os.listdir(private_path)

    # Safety: don't reinitialize
    if is_git_repo(private_path):
        print(f"  private/ is already a git repo at {private_path}")
        print(f"  Use 'dz private-init --status' to check its state")
        return 0

    # Create directory if needed
    if not os.path.isdir(private_path):
        os.makedirs(private_path, exist_ok=True)
        print(f"  Created {private_path}")

    # Initialize git repo
    rc, _, err = run_git(["init"], cwd=private_path)
    if rc != 0:
        print(f"  ERROR: git init failed: {err}")
        return 1
    print(f"  Initialized git repo in private/")

    # Disable GPG signing -- private repos are local-only, no signatures needed
    run_git(["config", "commit.gpgsign", "false"], cwd=private_path)
    run_git(["config", "tag.gpgsign", "false"], cwd=private_path)

    # Create .gitignore
    gitignore_path = os.path.join(private_path, ".gitignore")
    if not os.path.isfile(gitignore_path):
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(PRIVATE_GITIGNORE)
        print(f"  Created .gitignore")

    # Create standard directory structure (only for fresh init, not adopt)
    if not existing_content:
        for subdir in PRIVATE_STRUCTURE:
            dirpath = os.path.join(private_path, subdir)
            os.makedirs(dirpath, exist_ok=True)
            # Add .gitkeep to empty dirs
            gitkeep = os.path.join(dirpath, ".gitkeep")
            if not os.listdir(dirpath):
                with open(gitkeep, "w") as f:
                    pass
        print(f"  Created standard structure: {', '.join(PRIVATE_STRUCTURE)}")

    # Add remote if specified
    if remote_url:
        rc, _, err = run_git(["remote", "add", "origin", remote_url], cwd=private_path)
        if rc != 0:
            print(f"  WARNING: Could not add remote: {err}")
        else:
            print(f"  Added remote: {remote_url}")

    # Stage and commit
    run_git(["add", "-A"], cwd=private_path)
    rc, status, _ = run_git(["status", "--porcelain"], cwd=private_path)

    if status:
        if adopt and existing_content:
            msg = f"init: adopt existing private content for {project_name}"
        else:
            msg = f"init: private workspace for {project_name}"

        rc, _, err = run_git(["commit", "-m", msg], cwd=private_path)
        if rc != 0:
            print(f"  WARNING: Initial commit failed: {err}")
        else:
            print(f"  Initial commit: {msg}")
    else:
        print(f"  Nothing to commit (empty repo)")

    # Ensure private/ is ignored by the parent repo
    ensure_private_ignored(target, private_dir_name, private_path, project_root)

    print()
    print(f"  Done. private/ is now a standalone git repo.")
    print(f"  Commit your work anytime: cd private && git add -A && git commit -m 'your message'")

    return 0


def main(argv=None):
    """Entry point for private-init."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="dz private-init",
        description="Initialize private/ as a standalone versioned git repo",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--remote", "-r",
        help="Remote URL for backup (e.g., git@github.com:user/project-private.git)",
    )
    parser.add_argument(
        "--adopt", "-a",
        action="store_true",
        help="Convert existing private/ content into a git repo",
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Check if private/ is already a git repo",
    )
    parser.add_argument(
        "--dir", "-d",
        default="private",
        help="Name of the private directory (default: private)",
    )
    parser.add_argument(
        "--fix", "-f",
        action="store_true",
        help="Add the .gitignore patterns this vault and its project are missing",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="With --fix, show what would be added and change nothing",
    )

    args = parser.parse_args(argv)

    # Resolve target directory
    target = os.path.abspath(args.path)

    # If target is a file, use its directory
    if os.path.isfile(target):
        target = os.path.dirname(target)

    # The private/ path is always relative to the target directory given
    private_path = os.path.join(target, args.dir)
    project_name = get_project_name(target)

    # Find the nearest parent git repo (for gitignore checking)
    project_root = find_project_root(target)

    print(f"  Project:  {project_name}")
    print(f"  Target:   {target}")
    if project_root:
        print(f"  Git root: {project_root}")
    print(f"  Private:  {private_path}")
    print()

    if args.status:
        return cmd_status(private_path, project_root, target, args.dir)

    if args.fix:
        return cmd_fix(private_path, project_root, target, args.dir, dry_run=args.dry_run)

    # Default behavior: --adopt if content already exists, plain init otherwise
    adopt = args.adopt
    if not adopt and os.path.isdir(private_path) and os.listdir(private_path):
        # Content exists but not a git repo -- suggest adopt
        if not is_git_repo(private_path):
            file_count = sum(len(files) for _, _, files in os.walk(private_path))
            print(f"  Found existing content ({file_count} files) -- using --adopt mode")
            adopt = True

    return cmd_init(
        private_path, project_root, project_name, target, args.dir,
        args.remote, adopt,
    )


if __name__ == "__main__":
    sys.exit(main())
