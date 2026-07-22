# Verification Sweep: #103 self-setup + #104 verb-contracts (uncommitted)

**Run by:** tester-unbounded (autonomous, SAFE-READ + SAFE-WRITE-SCRATCH scope, pre-approved)
**Date:** 2026-07-19
**Scope:** uncommitted working trees of `C:\code\dazzlecmd` and `C:\code\dazzlecmd-lib`
**Constraint discipline:** no registry writes, no PATH/env changes, no installs, no git state changes, no commits. All work in `%TEMP%\dz_verify_103_104` and this results file.

## Environment

| Fact | Value |
|---|---|
| dazzlecmd-lib installed (site-packages) | 0.8.55 -- stale, predates `self_setup`/`verb_contracts`/`instance_plane` |
| dazzlecmd installed (site-packages) | 0.10.14 -- stale, predates #103/#104 |
| Installed `dz.exe` | `C:\Users\Extreme\AppData\Roaming\Python\Python313\Scripts\dz.exe` |
| pytest | 8.3.5, Python 3.13.2 |
| Both repos' `git status` | clean except the #103/#104 changes listed below; no other drift |

**Changed files (uncommitted):**
- `dazzlecmd-lib`: `dazzlecmd_lib/{self_setup.py (new), verb_contracts.py (new), engine.py, conditions.py, default_meta_commands.py, paths.py, registry.py}`, `tests/{test_self_setup.py, test_verb_contracts.py, one-offs/selfsetup-standalone/conftest.py}` (new), `CHANGELOG.md`
- `dazzlecmd`: `src/dazzlecmd/{__main__.py, parsers.py, commands/setup.py}`, `README.md`, `docs/guides/setup-scripts.md`, `CHANGELOG.md`, `tests/{test_setup_self.py, one-offs/smoke_setup_self_wiring.py, checklists/v0.12.2__Feature__setup-self-path-bootstrap.md}` (new)

### Why the full suites cannot run here (confirmed environmental, not a regression)

Neither package is truly editable-installed against this worktree -- `import dazzlecmd_lib` / `import dazzlecmd` from a neutral cwd resolve to the stale site-packages copies above, not local `src/`. Traced the actual root causes (differ slightly from the pre-briefed description, but the underlying story is identical):

- `dazzlecmd-lib` suite: `python -m pytest --co` → 19 collection errors, first-reported `ModuleNotFoundError: No module named 'dazzlecmd_lib._version'` (a setuptools_scm build artifact, only materializes on a real editable install). Deeper in the chain, `tests/test_verb_context_adherence.py` needs `dazzlecmd_lib.transitions.VerbContext` -- confirmed via direct `python -c "from dazzlecmd_lib.transitions import VerbContext"` that this module **does not exist anywhere in this checkout** (not in local source, not in site-packages) -- genuinely unpushed, matching the task's description.
- `dazzlecmd` suite: `python -m pytest --co` → 13 collection errors, first-reported `ImportError: cannot import name '_init_verbosity' from 'dazzlecmd.cli'` (resolves to the stale installed 0.10.14 `cli.py`, not local `src/`). Confirmed via direct import that `dazzlecmd_lib.instance_plane` (which local, uncommitted `src/dazzlecmd/tree_plane.py` now imports) **does not exist in the installed 0.8.55 dazzlecmd_lib** either.

Conclusion: **environmental, not a regression** -- both blockers are confirmed real, just surfaced via different first-error names than pre-briefed (pytest reports collection errors alphabetically; other broken imports happen to sort earlier). The standalone harness below sidesteps this by loading the new modules directly from file, bypassing both broken package `__init__` chains.

## PASS/FAIL Table

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Standalone harness (`selfsetup-standalone/conftest.py` + `test_self_setup.py` + `test_verb_contracts.py`) | **PASS** | 53 collected: 52 passed, 1 skipped (`test_posix_quote_safety`, `skipif(os.name=="nt")`) -- exactly the expected "53 + 1 platform-skip" |
| 2 | `smoke_setup_self_wiring.py` (app-routing smoke) | **PASS** | exit 0, `app wiring smoke: all checks pass`. Stderr line `Error: engine unavailable` is expected output *from the script's own tool-fallthrough test case*, not a failure |
| 3 | `py_compile` on all 10 changed source files | **PASS** | all 10 compile clean (`self_setup.py`, `verb_contracts.py`, `paths.py`, `engine.py`, `default_meta_commands.py`, `conditions.py`, `registry.py`, `__main__.py`, `parsers.py`, `commands/setup.py`) |
| 4 | New edge-case tests (this run) | **PASS** | 9/9 new pytest cases pass; 1/1 new smoke-extension script passes (see below) |
| 5a | `dz --version` via full path | **PASS** | exit 0, `dazzlecmd PREALPHA 0.10.14 (...)` |
| 5b | `where dz`-equivalent finds it | **REVIEW (expected)** | `Get-Command dz` / `where.exe dz` find nothing in **this** live PowerShell session -- `$env:Path` in this process predates today's PATH fix (registry has it, live session doesn't). This is a live demonstration of the exact `needs_new_terminal` scenario the code under test is designed to detect, not a bug. See Findings. |
| 5c | `reg query HKCU\Environment /v Path` -- Scripts dir appended, `REG_EXPAND_SZ`, `%USERPROFILE%` intact | **PASS** | type `REG_EXPAND_SZ`; value ends `...WinGet\Links;...npm;...Python313\Scripts`; `%USERPROFILE%\.dotnet\tools` entry present unexpanded |
| 5d | Backup file exists under `~/.dazzlecmd/` | **PASS** | `path-backup-2026-07-19_06-57-38.txt`, 492 bytes, same day |
| 5e | Installed 0.10.14 baseline: `dz setup no-such-tool-xyz -- --dry-run` errors gracefully | **PASS** | exit 2, `dz: error: unrecognized arguments: --dry-run` -- confirms the pre-fix baseline the #104 work closes |
| 6 | Static review pass | **DONE** | see Findings below |

## New tests written (this run)

Both files are in `%TEMP%\dz_verify_103_104\` and are self-contained; content included below for possible promotion.

### `test_edge_cases.py` (9 pytest cases, all pass)

Targets: `split_level_args` with no target before `--`, `join_for_shell` embedded-quote handling on both platforms, and `run_self_setup`'s `dry_run`-beats-`assume_yes` priority + the healthy-but-`needs_new_terminal` message-suppression path. Every case passed -- **no bugs found by these**, which is a positive result (confirms the priority ordering and quoting are correct), but they close real gaps in the existing suite and are worth promoting.

```python
"""Extension coverage written during the #103/#104 verification sweep.

Targets gaps not covered by test_self_setup.py / test_verb_contracts.py:
  - split_level_args with a "--" that has NO target before it (pathological
    input flagged by the dispatching tester-unbounded task)
  - join_for_shell with an embedded double-quote (Windows) / single-quote
    (POSIX, forced via monkeypatch since this host is Windows)
  - run_self_setup: dry_run must win over assume_yes (never mutate when
    dry_run=True even if the caller also passed --yes)
  - run_self_setup: healthy + needs_new_terminal suppresses the redundant
    "Everything is in order" line but still returns 0
"""

import os

import pytest

from dazzlecmd_lib import self_setup
from dazzlecmd_lib.self_setup import SelfSetupReport
from dazzlecmd_lib.verb_contracts import join_for_shell, split_level_args


class TestSplitLevelArgsPathological:
    def test_separator_with_no_target(self):
        """`dz setup -- x` -- no level-object named before the split.

        The verb_contracts layer does not know or care whether a target
        was supplied; it just splits at the first `--`. head has no
        positional after "setup", level carries the orphaned tail.
        """
        head, level = split_level_args(["setup", "--", "x"])
        assert head == ["setup"]
        assert level == ["x"]

    def test_separator_immediately_after_verb_only_flags(self):
        head, level = split_level_args(["setup", "--yes", "--", "x", "y"])
        assert head == ["setup", "--yes"]
        assert level == ["x", "y"]

    def test_second_dashdash_is_data_not_delimiter(self):
        head, level = split_level_args(["setup", "--", "--"])
        assert head == ["setup"]
        assert level == ["--"]

    def test_leading_dashdash_verb_position(self):
        # argv[0] IS "--" -- contract_for("--") is CONTRACT_BARE (not a
        # subscribed verb name), so nothing splits.
        head, level = split_level_args(["--", "setup", "x"])
        assert head == ["--", "setup", "x"]
        assert level == []


class TestJoinForShellQuoting:
    def test_windows_embedded_double_quote(self):
        if os.name != "nt":
            pytest.skip("Windows list2cmdline behavior")
        joined = join_for_shell(['say "hi"'])
        # list2cmdline escapes embedded quotes with backslash-quote so a
        # cmd.exe re-parse recovers the original single token.
        import subprocess
        # round-trip: list2cmdline is not directly invertible without a
        # shell, but we can assert the raw escaping shape it documents.
        assert joined == subprocess.list2cmdline(['say "hi"'])
        assert '\\"' in joined

    def test_posix_embedded_single_quote_forced(self, monkeypatch):
        # Force the POSIX branch on this Windows host to exercise the
        # shlex.join path (join_for_shell reads os.name at call time).
        monkeypatch.setattr(os, "name", "posix")
        joined = join_for_shell(["it's"])
        import shlex
        assert joined == shlex.join(["it's"])
        # shlex.join wraps a value containing a single quote in double
        # quotes with the inner quote escaped -- confirm it round-trips.
        assert shlex.split(joined) == ["it's"]

    def test_posix_semicolon_forced(self, monkeypatch):
        monkeypatch.setattr(os, "name", "posix")
        assert join_for_shell(["a;b"]) == "'a;b'"


class TestRunSelfSetupPriority:
    """dry_run must short-circuit before the assume_yes / TTY prompt path."""

    def _broken_report(self, tmp_path):
        return SelfSetupReport(
            command_names=["dz"],
            package_name="dazzlecmd",
            package_version="0.12.2",
            package_location=str(tmp_path),
            python_exe="python",
            scheme="user",
            scripts_dir=str(tmp_path / "Scripts"),
            shims_present=["dz"],
            on_effective_path=False,
            on_persisted_path=False,
        )

    def test_dry_run_wins_over_assume_yes_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr(os, "name", "nt")
        report = self._broken_report(tmp_path)
        monkeypatch.setattr(self_setup, "diagnose", lambda *a, **k: report)

        write_calls = []
        monkeypatch.setattr(self_setup, "_write_user_path_raw",
                            lambda raw, kind: write_calls.append((raw, kind)))
        monkeypatch.setattr(self_setup, "_read_user_path_raw",
                            lambda: ("", self_setup.REG_EXPAND_SZ))
        monkeypatch.setattr(self_setup, "_broadcast_environment_change",
                            lambda: True)

        printed = []
        rc = self_setup.run_self_setup(
            ["dz"], assume_yes=True, dry_run=True,
            print_fn=printed.append, input_fn=lambda p: "y")

        assert rc == 0
        assert not write_calls, (
            "dry_run=True must never write the registry, even with "
            "assume_yes=True")
        assert any("[dry-run]" in line for line in printed)

    def test_healthy_needs_new_terminal_suppresses_redundant_line(
            self, monkeypatch, tmp_path):
        report = SelfSetupReport(
            command_names=["dz"],
            package_name="dazzlecmd",
            package_version="0.12.2",
            package_location=str(tmp_path),
            python_exe="python",
            scheme="user",
            scripts_dir=str(tmp_path / "Scripts"),
            shims_present=["dz"],
            on_effective_path=False,
            on_persisted_path=True,  # persisted fixed, this shell predates it
        )
        assert report.healthy is True
        assert report.needs_new_terminal is True

        monkeypatch.setattr(self_setup, "diagnose", lambda *a, **k: report)
        printed = []
        rc = self_setup.run_self_setup(["dz"], print_fn=printed.append)

        assert rc == 0
        assert not any("Everything is in order" in line for line in printed)
        assert any("NEW terminal" in line for line in printed)
```

### `smoke_extension.py` (standalone script, extends `smoke_setup_self_wiring.py`'s stub pattern)

Targets: level_args forwarding into a **normal** (non-self) tool's `command` invocation, and the "no target, but a `--` tail present" pathological shape (`dz setup -- x`). This is what surfaced Finding 1 below.

```python
"""Extension of dazzlecmd/tests/one-offs/smoke_setup_self_wiring.py.

Covers two gaps the original smoke script didn't touch:
  1. level_args forwarding into a NORMAL (non-self) tool's `command`
     invocation via join_for_shell -- the #104 "documented but unwired"
     forwarding path, now wired through _cmd_setup.
  2. The "no target, but a `--` tail present" pathological shape
     (`dz setup -- x`): split_level_args hands back head=["setup"],
     level_args=["x"]; does _cmd_setup silently drop the orphaned tail,
     or does it warn?

Uses the exact same stub-loading pattern as smoke_setup_self_wiring.py so
it can load the real commands/setup.py without dragging in the broken
package __init__ chain.
"""

import importlib.util
import sys
import types

pkg = types.ModuleType("dazzlecmd_lib")
pkg.__path__ = []
sys.modules["dazzlecmd_lib"] = pkg

colors = types.ModuleType("dazzlecmd_lib.colors")
colors.warn = lambda s: s
colors.error = lambda s: s
sys.modules["dazzlecmd_lib.colors"] = colors
pkg.colors = colors

verb_contracts_spec = importlib.util.spec_from_file_location(
    "dazzlecmd_lib.verb_contracts",
    r"C:\code\dazzlecmd-lib\dazzlecmd_lib\verb_contracts.py")
verb_contracts = importlib.util.module_from_spec(verb_contracts_spec)
sys.modules["dazzlecmd_lib.verb_contracts"] = verb_contracts
verb_contracts_spec.loader.exec_module(verb_contracts)
pkg.verb_contracts = verb_contracts

self_setup_spec = importlib.util.spec_from_file_location(
    "dazzlecmd_lib.self_setup",
    r"C:\code\dazzlecmd-lib\dazzlecmd_lib\self_setup.py")
self_setup = importlib.util.module_from_spec(self_setup_spec)
sys.modules["dazzlecmd_lib.self_setup"] = self_setup
self_setup_spec.loader.exec_module(self_setup)
pkg.self_setup = self_setup

# Stub setup_resolve / platform_detect / schema_version -- the tool-path
# branch of _cmd_setup imports these; give it just enough to run a
# `command`-form setup block with no platform/override complexity.
setup_resolve = types.ModuleType("dazzlecmd_lib.setup_resolve")


class InvalidSetupBlockError(Exception):
    pass


def resolve_setup_block(project):
    return dict(project.setup)


setup_resolve.InvalidSetupBlockError = InvalidSetupBlockError
setup_resolve.resolve_setup_block = resolve_setup_block
setup_resolve.infer_setup_script_interpreter = lambda p: None
sys.modules["dazzlecmd_lib.setup_resolve"] = setup_resolve
pkg.setup_resolve = setup_resolve

schema_version = types.ModuleType("dazzlecmd_lib.schema_version")


class UnsupportedSchemaVersionError(Exception):
    pass


schema_version.UnsupportedSchemaVersionError = UnsupportedSchemaVersionError
sys.modules["dazzlecmd_lib.schema_version"] = schema_version
pkg.schema_version = schema_version

sys.modules.setdefault("dazzlecmd", types.ModuleType("dazzlecmd"))
sys.modules["dazzlecmd"].__file__ = (
    r"C:\code\dazzlecmd\src\dazzlecmd\__init__.py")
app_spec = importlib.util.spec_from_file_location(
    "dazzlecmd.commands.setup",
    r"C:\code\dazzlecmd\src\dazzlecmd\commands\setup.py")
app_setup = importlib.util.module_from_spec(app_spec)
app_spec.loader.exec_module(app_setup)


class Args:
    def __init__(self, tool, yes=False, dry_run=False, level_args=None):
        self.tool = tool
        self.yes = yes
        self.dry_run = dry_run
        self.level_args = level_args or []


class Project:
    def __init__(self, name, setup):
        self.name = name
        self.fqcn = f"core:{name}"
        self.directory = "."
        self.setup = setup


class Engine:
    command = "dz"
    name = "dazzlecmd"
    projects = []
    all_projects = []

    def resolve_command(self, name):
        for p in self.projects:
            if p.name == name or p.fqcn == name:
                return p, None
        return None, None


failures = []

# -- 1. level_args forward into a normal tool's `command` string ------------
tool = Project("mytool", {"command": "echo base"})
engine = Engine()
engine.projects = [tool]
engine.all_projects = [tool]

rc = app_setup._cmd_setup(
    Args("mytool", dry_run=True, level_args=["--extra", "a b"]), engine)
if rc != 0:
    failures.append(f"normal tool dry-run with level_args: rc={rc}")

# -- 2. orphaned level_args (no target) are silently dropped, not warned ----
calls_capture = []
import builtins
_orig_print = print


def _capturing_print(*a, **k):
    calls_capture.append(" ".join(str(x) for x in a))
    _orig_print(*a, **k)


builtins.print = _capturing_print
try:
    # Simulates `dz setup -- x`: split_level_args hands back
    # head=["setup"] (no positional tool), level_args=["x"].
    rc2 = app_setup._cmd_setup(Args(None, level_args=["x"]), engine)
finally:
    builtins.print = _orig_print

if rc2 != 0:
    failures.append(f"no-target with orphaned level_args: rc={rc2}")
mentioned_x = any("x" in line and "ignoring" in line.lower()
                  for line in calls_capture)
if mentioned_x:
    failures.append(
        "unexpected: orphaned level_args WERE surfaced (re-check finding)")

if failures:
    print("FAIL")
    for f in failures:
        print(" -", f)
    sys.exit(1)

print("smoke_extension: all checks pass")
print(f"FINDING: dz setup -- x (no target) rc={rc2}, "
      f"orphaned level_args=['x'] silently dropped, no warning to user "
      f"(captured output: {calls_capture!r})")
```

**Actual output from the run** (confirms both points):
```
[dry-run] Would run setup for core:mytool...
  Command: echo base --extra "a b"
  Working dir: .

Tools with setup declared:
  core:mytool           -

Run: dz setup <tool> to execute a tool's setup.
smoke_extension: all checks pass
FINDING: dz setup -- x (no target) rc=0, orphaned level_args=['x'] silently dropped, no warning to user
```

## Findings (severity-ranked)

### 1. LOW -- `dz setup -- x` (no target) silently discards the forwarded tail

**Where:** `dazzlecmd/src/dazzlecmd/commands/setup.py::_cmd_setup` (confirmed) and `dazzlecmd-lib/dazzlecmd_lib/default_meta_commands.py::setup_handler` (same code shape, traced by reading -- both `if not tool_name:` branches return before `level_args` is ever read).

When a user runs `dz setup -- --dry-run` and forgets the target, `split_level_args` correctly produces `head=["setup"]`, `level_args=["--dry-run"]`. Because `tool_name` is `None`, `_cmd_setup` takes the "no tool specified: list tools" branch and returns 0 -- the `--dry-run` the user clearly intended for *something* is silently dropped with no warning. Contrast with the self-target case (`dz setup dz --`), which explicitly warns `"note: self-setup takes its options before '--'... ignoring reserved trailing args"`. The no-target case has no equivalent notice.

**Impact:** cosmetic/UX only -- no crash, no data loss, exit code is still 0 (successful listing). A user who mistypes the target name gets a silent no-op instead of a hint that their trailing args went nowhere.

**Suggested fix (diagnose only, not applied):** in the `if not tool_name:` branch of both `_cmd_setup` and `setup_handler`, check `level_args` (or the raw split before the tool_name check) and print the same "ignoring... trailing args" warning used in the self-target path.

### 2. INFORMATIONAL -- self-setup routing logic is duplicated across two files

**Where:** `dazzlecmd/src/dazzlecmd/commands/setup.py::_cmd_setup`/`_run_self_setup`/`_self_names` vs. `dazzlecmd-lib/dazzlecmd_lib/default_meta_commands.py::setup_handler`/`_self_setup_identity`.

Both independently implement: self-name detection, the "reserved trailing args" warning, and dry-run-before-listing ordering. This is explicitly acknowledged as intentional in `self_setup.py`'s module docstring ("the `setup` handlers (the app's and `dazzlecmd_lib.default_meta_commands`) special-case... and call into here"), so it is a known design choice, not an oversight -- but it is a DRY/maintenance risk: Finding 1 above, if fixed, needs to be fixed in **both** places, and the two copies could silently drift on future changes. Not a blocker; worth a tracking note if #104 gets a follow-up pass.

### 3. INFORMATIONAL -- live session PATH doesn't yet reflect the registry fix

The current PowerShell session's `$env:Path` predates the PATH fix already present in the HKCU registry (see PASS/FAIL row 5b/5d) -- a fresh terminal would resolve `dz` on PATH; this one won't. This is not a bug: it's the exact scenario `SelfSetupReport.needs_new_terminal` / `first_run_hint`'s "PATH is already fixed -- open a NEW terminal" branch exist to detect, and `TestFirstRunHint::test_new_terminal_hint_when_persisted_fixed` (in the standalone suite, PASS) models it correctly. Flagging only so a human reviewer isn't surprised that checklist item HV.1-adjacent PATH checks don't resolve live in *this* shell.

### 4. No bugs found in the code paths exercised by the 9 new edge-case tests

`split_level_args`'s handling of a `--` with no preceding target, a second literal `--` as data, and `argv[0] == "--"`; `join_for_shell`'s embedded-quote escaping on both the Windows (`list2cmdline`) and forced-POSIX (`shlex.join`) branches; and `run_self_setup`'s `dry_run`-before-`assume_yes` priority plus the healthy+`needs_new_terminal` message suppression -- all behaved exactly as the code intends. This is a positive verification result, not just an absence of failure: these are exactly the shapes a hostile/careless CLI invocation would hit first.

## SHIP/HOLD Recommendation

**SHIP**, with Finding 1 as an optional follow-up (not a blocker).

Rationale: every explicitly-scoped check passed (53+1 standalone suite, app-wiring smoke, 10/10 py_compile, installed-baseline documentation, registry/backup verification). The two environmental full-suite failures are confirmed pre-existing and orthogonal to this diff (traced to their actual root causes, which match the task's "unpushed dependency" framing even though the first-reported error names differ). The one functional finding (orphaned `--` tail silently dropped) is a minor UX polish item with no correctness or safety impact -- it does not affect the documented, tested invocation shapes (`dz setup <target> -- <args>`), only a malformed one (`dz setup -- <args>` with no target). Recommend either fixing Finding 1 in a fast-follow or explicitly noting it as a known limitation in the CHANGELOG/checklist.

## Files referenced

- `C:\code\dazzlecmd-lib\dazzlecmd_lib\self_setup.py`
- `C:\code\dazzlecmd-lib\dazzlecmd_lib\verb_contracts.py`
- `C:\code\dazzlecmd-lib\dazzlecmd_lib\engine.py` (lines ~2238-2255, the pre-argparse split wiring)
- `C:\code\dazzlecmd-lib\dazzlecmd_lib\default_meta_commands.py` (`setup_handler`, `_self_setup_identity`)
- `C:\code\dazzlecmd-lib\dazzlecmd_lib\paths.py` (`which_in_dir`, `which_all_on_path`)
- `C:\code\dazzlecmd-lib\dazzlecmd_lib\conditions.py`, `registry.py` (shutil.which -> which_with_pathext)
- `C:\code\dazzlecmd\src\dazzlecmd\commands\setup.py` (`_cmd_setup`, `_run_self_setup`, `_self_names`)
- `C:\code\dazzlecmd\src\dazzlecmd\parsers.py` (`setup_parser` -y/--yes/--dry-run)
- `C:\code\dazzlecmd\src\dazzlecmd\__main__.py` (`_maybe_hint_path_bootstrap`)
- `C:\code\dazzlecmd\tests\checklists\v0.12.2__Feature__setup-self-path-bootstrap.md` (existing human checklist, cross-referenced, not modified)
- Scratch harness (not committed): `%TEMP%\dz_verify_103_104\{conftest.py, test_self_setup.py, test_verb_contracts.py, test_edge_cases.py, smoke_extension.py}`
