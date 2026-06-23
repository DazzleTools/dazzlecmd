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

# Default .gitignore for the private repo itself
PRIVATE_GITIGNORE = """\
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


def cmd_status(private_path, project_root, target=None, private_dir_name="private"):
    """Check and report the status of private/."""
    if not os.path.isdir(private_path):
        print(f"  private/ does not exist at {private_path}")
        return 1

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
