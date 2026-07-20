"""Smoke: the app's _cmd_setup routes self-targets to run_self_setup.

Seeds stub dazzlecmd_lib modules (colors + real self_setup loaded from
file) so dazzlecmd.commands.setup imports cleanly despite this machine's
outdated installed libs. Verifies routing for dz / dazzlecmd / engine
names, engine=None resilience, and that tool names fall through.
"""

import importlib.util
import sys
import types

# -- stub dazzlecmd_lib with real self_setup + minimal colors ------------
pkg = types.ModuleType("dazzlecmd_lib")
pkg.__path__ = []
sys.modules["dazzlecmd_lib"] = pkg

colors = types.ModuleType("dazzlecmd_lib.colors")
colors.warn = lambda s: s
colors.error = lambda s: s
sys.modules["dazzlecmd_lib.colors"] = colors
pkg.colors = colors

spec = importlib.util.spec_from_file_location(
    "dazzlecmd_lib.self_setup",
    r"C:\code\dazzlecmd-lib\dazzlecmd_lib\self_setup.py")
self_setup = importlib.util.module_from_spec(spec)
sys.modules["dazzlecmd_lib.self_setup"] = self_setup
spec.loader.exec_module(self_setup)
pkg.self_setup = self_setup

# -- load the app's commands/setup.py as a standalone module -------------
# (dazzlecmd package import would drag in cli.py -> the missing 0.10.28
# lib surface; commands/setup.py itself only needs os/sys/colors.)
sys.modules.setdefault("dazzlecmd", types.ModuleType("dazzlecmd"))
sys.modules["dazzlecmd"].__file__ = (
    r"C:\code\dazzlecmd\src\dazzlecmd\__init__.py")
spec2 = importlib.util.spec_from_file_location(
    "dazzlecmd.commands.setup",
    r"C:\code\dazzlecmd\src\dazzlecmd\commands\setup.py")
app_setup = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(app_setup)

# -- capture run_self_setup calls ----------------------------------------
calls = []


def fake_run(names, **kw):
    calls.append((names, kw))
    return 0


self_setup.run_self_setup = fake_run


class Args:
    def __init__(self, tool, yes=False, dry_run=False):
        self.tool = tool
        self.yes = yes
        self.dry_run = dry_run


class Engine:
    command = "dz"
    name = "dazzlecmd"
    projects = []
    all_projects = []


failures = []

# self-targets route to run_self_setup
for target in ("dz", "dazzlecmd"):
    calls.clear()
    rc = app_setup._cmd_setup(Args(target, yes=True), Engine())
    if rc != 0 or len(calls) != 1:
        failures.append(f"target {target!r}: rc={rc} calls={calls}")
    elif "dz" not in calls[0][0] or not calls[0][1].get("assume_yes"):
        failures.append(f"target {target!r}: bad call {calls[0]}")

# flags flow through
calls.clear()
app_setup._cmd_setup(Args("dz", dry_run=True), Engine())
if not calls or not calls[0][1].get("dry_run"):
    failures.append(f"dry_run did not flow: {calls}")

# engine=None still reaches self-setup (the broken-engine scenario)
calls.clear()
rc = app_setup._cmd_setup(Args("dz"), None)
if rc != 0 or len(calls) != 1:
    failures.append(f"engine=None: rc={rc} calls={calls}")

# a tool name falls through to normal resolution (engine=None -> error 1)
calls.clear()
rc = app_setup._cmd_setup(Args("some-tool"), None)
if rc != 1 or calls:
    failures.append(f"tool fallthrough: rc={rc} calls={calls}")

# no-arg with empty engine lists nothing but exits 0 (hint path safe)
rc = app_setup._cmd_setup(Args(None), Engine())
if rc != 0:
    failures.append(f"no-arg listing rc={rc}")

if failures:
    print("FAIL")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("app wiring smoke: all checks pass")
