# Setup scripts -- developer guide

This guide is for **tool authors** writing setup logic for their dazzlecmd-pattern tools. It documents the conventions tools should follow so `dz setup <tool>` behaves predictably for users, regardless of which tool's setup is running.

Audience: developers writing `.dazzlecmd.json` manifests + setup scripts. Users (running `dz setup <tool>`) don't need to read this; see `docs/guides/dz-setup.md` for the user-facing reference.

For the schema shape (`setup.command`, `setup.script`, `setup.platforms`, `_schema_version`), see `docs/guides/manifests.md`. This guide covers the *policy* layer on top: what makes a setup script that's safe, predictable, and pleasant to invoke.

---

## The two manifest shapes

A `setup` block declares ONE of two mutually-exclusive forms (XOR-validated by the engine):

### `setup.command` -- one-liner shell command

Use when setup is a single, idiomatic shell line. Examples:

```json
{
    "setup": {
        "note": "Build the binary via Cargo.",
        "command": "cargo build --release"
    }
}
```

```json
{
    "setup": {
        "note": "Install npm dependencies.",
        "command": "npm install"
    }
}
```

Pros: zero extra files. The command runs through the system shell (`shell=True`) so `&&`, `||`, env-var expansion, and pipes work.

Cons: hard to test, hard to support multi-step or conditional logic, hard to expose `--dry-run` (the convention below). The shell-string form is *correct* for the simple case, but if your install needs branching, prefer `setup.script`.

### `setup.script` -- file pointer

Use when setup needs more than one step, platform branching, error handling, or post-install verification. The engine infers the interpreter from the file extension and dispatches as a real `argv` (not a shell string):

| Extension       | Interpreter             |
|-----------------|-------------------------|
| `.py`           | `python <script>`       |
| `.sh`           | `bash <script>`         |
| `.cmd` / `.bat` | `cmd /c <script>`       |
| `.ps1`          | `powershell -File <script>` |

```json
{
    "setup": {
        "note": "Install fd, the file-search binary that `dz find` wraps.",
        "script": "dz_setup.py"
    }
}
```

The script must live in the tool directory (absolute paths are rejected) and the file must exist on disk at dispatch time.

**Rule of thumb**: if your setup needs to test for `which X`, branch on OS, install multiple packages, or report what it's about to do before doing it, use `setup.script`. If it's a single `pip install foo` or `cargo build`, `setup.command` is fine.

---

## Conventions for setup scripts

These are *policies*, not engine-enforced contracts. Following them makes `dz setup <your-tool>` feel consistent with every other tool in the ecosystem. The engine stays dumb on purpose -- the discipline lives in the tools.

### 1. Honor `--dry-run`

Every setup script SHOULD accept `--dry-run` (and ideally `-n` as a short form). When passed, the script prints the commands it would execute and exits cleanly without running them.

Why: setup scripts often run with elevation (sudo / UAC) or modify the user's environment (install packages, write to `~/.local`, change PATH). Users deserve a way to preview the impact before committing. The user can run:

```bash
dz setup mytool -- --dry-run
```

and see exactly what's about to happen. (The double-dash forwards `--dry-run` to the script rather than letting `dz setup` try to consume it.)

Minimal pattern:

```python
import argparse

DRY_RUN = False

def _run(cmd):
    print(f"$ {' '.join(cmd)}")
    if DRY_RUN:
        return 0
    return subprocess.run(cmd).returncode

def main(argv=None):
    global DRY_RUN
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", "-n", action="store_true")
    args = parser.parse_args(argv)
    DRY_RUN = args.dry_run
    ...
```

The `python/__full__/dz_setup.py.tmpl` scaffold ships with this pattern by default.

### 2. Be idempotent

Re-running `dz setup <tool>` on an already-set-up machine SHOULD be a no-op. Detect existing state and short-circuit before doing destructive work.

For Python tools using `runtime.venv: ".venv"`, this means: check whether `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (POSIX) already exists, and skip venv creation if so. The `python/__full__/dz_setup.py.tmpl` template does this.

For binary installers, check `shutil.which("fd")` (or whatever your tool needs) and skip the install when the binary is already on PATH. Offer `--force` for explicit reinstall:

```python
existing = shutil.which("fd")
if existing and not args.force:
    print(f"fd is already installed at: {existing}")
    return 0
```

### 3. Echo commands before running them

Print each command to stdout before executing it, prefixed with `$ `. This serves three purposes:

- Users can copy/paste the command if they want to run it manually.
- Failed runs are debuggable from the captured log.
- `--dry-run` becomes a one-line code change (print, then skip exec).

### 4. Verify after install

After running the installer, re-check that the thing you tried to install is now on PATH (for binaries) or importable (for Python packages). The installer's exit code is necessary but not sufficient -- on some platforms a successful install lands in a directory not yet on PATH.

```python
# After the install ran...
installed_at = shutil.which("fd") or shutil.which("fdfind")
if installed_at:
    print(f"success. fd available at: {installed_at}")
    return 0
print("installer reported success but fd is not on PATH.", file=sys.stderr)
print("You may need to open a new shell or update PATH.", file=sys.stderr)
return 1
```

### 5. Use `dazzlecmd_lib.platform_detect` for cross-platform logic

The library provides `PlatformInfo` with `.os`, `.subtype`, `.version`, `.arch`, `.is_wsl`, and `.id_like`. Setup scripts SHOULD import it rather than re-implementing platform detection:

```python
from dazzlecmd_lib.platform_detect import get_platform_info

pi = get_platform_info()
if pi.os == "windows":
    ...
elif pi.os == "linux":
    if "debian" in pi.id_like:
        cmd = ["apt-get", "install", "-y", "fd-find"]
    elif "rhel" in pi.id_like or "fedora" in pi.id_like:
        cmd = ["dnf", "install", "-y", "fd-find"]
    elif "arch" in pi.id_like:
        cmd = ["pacman", "-S", "--noconfirm", "fd"]
    ...
```

The `id_like` field includes the subtype itself, so `"debian" in pi.id_like` matches Debian directly AND every debian-derived distro (Ubuntu, Mint, Kali, Pop, Raspbian, ...). You don't need to enumerate every member of the family.

dazzlecmd-lib provides the identification *facts*; your script writes the policy. The lib intentionally does not pick installers for you -- that's a tool-author decision, and the right answer depends on what your tool needs.

### 6. Prepend `sudo` (or `doas`) on POSIX when needed -- don't assume root

Linux and BSD package managers need root. Detect whether the current process is root and prepend the elevation tool:

```python
def _needs_sudo():
    if not hasattr(os, "geteuid"):
        return False
    return os.geteuid() != 0

cmd = ["apt-get", "install", "-y", "fd-find"]
if _needs_sudo():
    cmd = ["sudo"] + cmd
```

OpenBSD convention is `doas` rather than `sudo`. Adjust per-platform.

### 7. Fail loudly with actionable messages

If something can't be done -- installer not on PATH, unsupported distro, missing prerequisites -- print a clear `Error:` line to stderr, give the user a path forward, and exit non-zero. Don't fall back to a partial install. Users prefer a clean failure with a manual install link over a half-broken state.

```python
return (
    None,
    f"Linux distro {pi.subtype!r} is not in the installer matrix. "
    f"Install fd manually from https://github.com/sharkdp/fd#installation",
)
```

### 8. Don't touch system state outside your tool dir unless installing system packages

Setup scripts SHOULD write only to the tool's own directory (the venv, build artifacts, generated files). The one legitimate exception is system package installers (apt-get, brew, winget) which by definition install globally.

If your tool needs config in `~/.config/<tool>`, write it lazily on first dispatch rather than during setup. Setup is for "the tool can now run"; first-dispatch is for "the tool has the user's preferences."

---

## Worked example: one-liner

```json
{
    "name": "node-helper",
    "runtime": {
        "type": "node",
        "script_path": "index.js"
    },
    "setup": {
        "note": "Install npm dependencies into node_modules.",
        "command": "npm install"
    }
}
```

The shell handles the rest. Re-running `dz setup` on an already-set-up tree re-resolves the package tree -- npm is idempotent enough that this is acceptable for simple cases.

## Worked example: Python with venv + requirements

The `dz new tool --language python --full <name>` scaffold ships with this pattern:

- `runtime.venv: ".venv"` so the dispatcher uses the venv interpreter.
- `setup.script: "dz_setup.py"` so install logic is testable code.
- A `dz_setup.py` that detects the project's installer (uv, poetry, pdm, pipenv, conda, pip+pyproject, pip+requirements, or empty-venv fallback) and dispatches the right one.
- A starter `requirements.txt`.

Run `dz new tool --language python --full myproj` to get a working scaffold; the rendered `dz_setup.py` is a complete, runnable example of every pattern in this guide.

## Worked example: cross-platform installer

See `projects/core/find/dz_setup.py` in this repo -- it installs `fd` on every major platform using `dazzlecmd_lib.platform_detect`, handles sudo elevation on POSIX, supports `--dry-run` and `--force`, and shows the post-install verification pattern.

---

## What dazzlecmd does NOT do

The engine is a dispatcher, not a package manager. These are explicit non-goals:

- **No automatic setup.** The engine never runs setup without explicit `dz setup <tool>` invocation. (v0.7.47 may add an opt-in `auto_setup_on_dispatch` config flag, but it stays opt-in.)
- **No multi-tool batching.** There is no `dz setup --all`. Tools are setup one at a time so failures are observable.
- **No installer picking.** The engine doesn't know whether your Python project should use uv or poetry. Your `setup.script` does.
- **No state tracking.** The engine doesn't remember whether setup ran successfully. Your script's idempotency check is the source of truth.

This dispatcher-not-package-manager promise is the reason setup scripts have so much responsibility. Tools that delegate too much to "the engine should handle this" become brittle when users have non-standard environments. Tools that own their setup explicitly are robust.

---

## Related references

- `docs/guides/dz-setup.md` -- user-facing reference for the `dz setup` command
- `docs/guides/manifests.md` -- the `setup` block schema (fields, validation, platform resolution)
- `docs/guides/creating-tools.md` -- general tool-authoring guide
- `packages/dazzlecmd-lib/src/dazzlecmd_lib/platform_detect.py` -- `PlatformInfo` API for cross-platform logic
- `projects/core/find/dz_setup.py` -- real-world cross-platform installer example
- `packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/python/__full__/dz_setup.py.tmpl` -- gold-standard Python `--full` template

## Conventions versioning

These conventions ship as part of dazzlecmd v0.7.46. They are NOT engine-enforced and there is no `_schema_version`-style gating on them. They evolve as the ecosystem learns; check this guide before tagging a 1.0 release of your tool.
