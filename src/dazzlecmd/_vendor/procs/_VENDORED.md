# procs -- vendored process identity

**Status:** vendored in dazzlecmd, 2026-11-19, for `dz relaunch`. Lift-ready: stdlib/ctypes only, no dazzlecmd imports, OS reads behind small functions with injectable inputs.

**Why here, for now:** the maintainer, 2026-11-19 -- "We'll vendor in dazzlecmd for now but the goal should be to design with the idea in mind that that it should work with "csb" and any other libs we think need it so we can improve all of those tools at once rather than duplicating work ... and it should get its own /dev-workflow-process when the time comes probably with its own /collabN-local 2". Process identity has no layer in the frozen STACK-MAP (it is neither a filesystem object nor path identity); its future home is that later design.

## Sources (copies this replaces, or will)

| Source | What it has | What it lacks |
|---|---|---|
| dazzlecmd `projects/dazzletools/unlockit/winfocus.py:115-174` | Toolhelp32 process table, FILETIME start time, ancestor walk with PID-reuse guard | liveness, exe by pid, POSIX, boot time |
| csb `claude_session_backup/lockfile.py:65-188` | liveness, exe name, start time (Windows + `/proc`) | process table, ancestor walk |
| csb `claude_session_backup/live_registry.py:181-219` | boot time (GetTickCount64, `/proc/uptime`, `sysctl kern.boottime`) | -- |
| dazzlecmd-lib `dazzlecmd_lib/shell_fix.py:64-137` | ANSI process table, invoking-shell detection | start time, liveness |

## Who would call what

| Function | dz relaunch | csb lockfile / live_registry | unlockit | shell_fix |
|---|---|---|---|---|
| `process_table()` | anchor | -- (would gain an ancestor walk) | yes | yes (replaces its ANSI table) |
| `process_start_time(pid)` | claim identity | yes | yes | -- |
| `is_alive(pid)` | claim staleness | yes (`_pid_alive`) | -- | -- |
| `process_exe(pid)` | claim identity | yes (`_proc_name`) | -- | -- |
| `same_process(pid, exe, start)` | claim staleness (None = held) | yes (its reclaim rule) | -- | -- |
| `ancestor_chain(pid, table)` | anchor | -- | yes (`self_chain`) | yes (bounded walk) |
| `find_anchor(pid, table)` | the claim's anchor | -- | -- | could seed detection |
| `boot_time()` | session boundary | yes (`current_boot_utc`) | -- | -- |

## Rules for changes while vendored

- No import from `dazzlecmd`; checked by a test in dz relaunch.
- Every OS read stays behind a function that a caller can replace.
- Changes here are noted in this file, so the later lift carries them.
