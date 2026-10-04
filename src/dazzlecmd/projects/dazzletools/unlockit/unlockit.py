"""unlockit -- who is holding this file or folder, and which window is it?

    dz unlockit <path>            probe the path, name its holders, group them by window
    dz unlockit <path> --json     the same, machine-readable
    dz unlockit <path> --handle   also ask Sysinternals handle.exe (slow; hard timeout)
    dz unlockit <path> --focus N  then bring holder N's window to the front

Windows-only. Without --focus it changes nothing. --focus restores and
raises one window; nothing is closed and no process is ended. The window
code lives in winfocus.py, which is kept free of unlockit imports so it
can be reused elsewhere.

Exit codes: 0 the path is free, 1 it is held, 2 it does not exist or the
check could not run. With --focus: 0 the window came to the front, 2 it
did not (or there was no single window to raise).
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import holders as hd  # noqa: E402
import winfocus as wf  # noqa: E402

EXIT_FREE, EXIT_HELD, EXIT_ERROR = 0, 1, 2


class Group:
    """Holders that resolve to the same window (or the same windowless process)."""

    def __init__(self, owner_pid, owner_exe, window, window_count):
        self.owner_pid = owner_pid
        self.owner_exe = owner_exe
        self.window = window            # wf.Window or None
        self.window_count = window_count
        self.holders = []
        self.is_self = False            # a holder is the shell unlockit was run from

    def to_dict(self, index):
        w = self.window
        return {
            "index": index,
            "window": None if w is None else {
                "hwnd": w.hwnd, "title": w.title, "exe": w.exe, "pid": w.pid,
                "class": w.class_name, "minimized": w.minimized, "cloaked": w.cloaked,
            },
            "owner_pid": self.owner_pid,
            "owner_exe": self.owner_exe,
            "window_count": self.window_count,
            "is_self": self.is_self,
            "holders": [h.__dict__ for h in self.holders],
        }


def group_holders(holders, path, procs, windows, self_chain=()):
    """Resolve each holder to a window and bundle holders that share one.

    A holder resolves to its first ancestor that owns windows; when that
    process owns several (Electron apps run every window under one
    process), the one whose title names the path is chosen. When no title
    names it, the group stays on the process with window=None, so the
    report can say "N windows, none names this path" rather than guess.
    """
    by_pid = wf.windows_by_pid(windows)
    groups = {}
    seen = set()
    for h in holders:
        key_h = (h.pid, h.reason, os.path.normcase(h.detail))
        if key_h in seen:
            continue
        seen.add(key_h)
        exe = procs[h.pid].exe if h.pid in procs else h.exe
        h = hd.Holder(h.pid, exe, h.reason, h.detail, h.source)
        owner = wf.windowed_ancestor(h.pid, procs, by_pid)
        if owner is None:
            key = ("process", h.pid)
            if key not in groups:
                groups[key] = Group(h.pid, exe, None, 0)
        else:
            owner_windows = by_pid[owner]
            win = wf.best_window(owner_windows, path)
            key = ("window", owner, win.hwnd if win else None)
            if key not in groups:
                owner_exe = procs[owner].exe if owner in procs else ""
                groups[key] = Group(owner, owner_exe, win, len(owner_windows))
        groups[key].holders.append(h)
        if h.pid in self_chain:
            groups[key].is_self = True
    # windows first, then by how much each group holds
    return sorted(groups.values(), key=lambda g: (g.window is None, -len(g.holders)))


# ------------------------------------------------------------------ report

def _describe(h, path, is_dir):
    if h.reason == "cwd":
        if os.path.normcase(h.detail).rstrip("\\") == os.path.normcase(path).rstrip("\\"):
            return "working directory is here"
        return f"working directory is inside: {os.path.relpath(h.detail, path)}"
    if not h.detail:
        return "has a file inside open" + (" (handle.exe)" if h.source == "handle.exe" else "")
    if not is_dir or os.path.normcase(h.detail) == os.path.normcase(path):
        what = "has it open"
    else:
        what = f"has {os.path.relpath(h.detail, path)} open"
    return what + (" (handle.exe)" if h.source == "handle.exe" else "")


def _status_line(g, n_holders):
    kind = "folder" if g.is_dir else "file"
    state = g.probe.state
    if state == "in-use":
        line = "In use: deleting it now would fail (sharing violation)."
        if not n_holders:
            line += "\nNo holder could be identified."
            if g.uninspected:
                line += f" {g.uninspected} processes could not be inspected from this prompt;"
            line += (" holders running as a service or another user need an elevated prompt, "
                     "and --handle may also help.")
        return line
    if state == "denied":
        return ("Access denied when opening it for deletion: that is a permissions or read-only "
                "problem, not a lock." + (f" {n_holders} process(es) also hold it." if n_holders else ""))
    if state == "error":
        return f"The lock check failed (Windows error {g.probe.winerror})."
    if n_holders:
        if g.is_dir:
            return (f"The {kind} itself is not locked, but processes hold things inside it, so "
                    f"deleting its contents may fail.")
        return "Open, but every holder allows deletion; deleting it should succeed."
    return f"Free: nothing holds this {kind}."


def render_text(g, groups, out=None):
    out = out or sys.stdout
    n_holders = sum(len(gr.holders) for gr in groups)
    print(f"{g.path}  ({'folder' if g.is_dir else 'file'})", file=out)
    print(_status_line(g, n_holders), file=out)
    for i, gr in enumerate(groups, 1):
        print(file=out)
        if gr.window is not None:
            flags = [f for f, on in (("minimized", gr.window.minimized),
                                     ("on another desktop or hidden", gr.window.cloaked)) if on]
            extra = f"  [{', '.join(flags)}]" if flags else ""
            print(f"[{i}] window: \"{gr.window.title}\"{extra}", file=out)
            print(f"    {gr.owner_exe} (pid {gr.owner_pid})", file=out)
        elif gr.window_count:
            print(f"[{i}] {gr.owner_exe} (pid {gr.owner_pid}): {gr.window_count} windows, "
                  f"none names this path", file=out)
        else:
            print(f"[{i}] no window: {gr.owner_exe} (pid {gr.owner_pid})", file=out)
        if gr.is_self:
            print("    note: this includes the shell you ran unlockit from", file=out)
        width = max(len(h.exe) for h in gr.holders)
        for h in sorted(gr.holders, key=lambda h: (h.reason, h.exe.lower(), h.pid)):
            print(f"      pid {h.pid:<7} {h.exe:<{width}}  {_describe(h, g.path, g.is_dir)}", file=out)
    if g.notes:
        print(file=out)
        for note in g.notes:
            print(f"note: {note}", file=out)


def pick_group(groups, n):
    """(group, None) for --focus N, or (None, reason). N=0 means "the only
    one with a window"."""
    if n == 0:
        windowed = [gr for gr in groups if gr.window is not None]
        if len(windowed) == 1:
            return windowed[0], None
        if not windowed:
            return None, "no holder has a window that can be identified"
        return None, f"{len(windowed)} windows hold it; choose one with --focus N"
    if not 1 <= n <= len(groups):
        return None, f"there is no [{n}]" + (f"; choose 1-{len(groups)}" if groups else "")
    gr = groups[n - 1]
    if gr.window is None:
        if gr.window_count:
            return None, (f"[{n}] {gr.owner_exe} has {gr.window_count} windows and none names this path, "
                          f"so there is no telling which one to raise")
        return None, f"[{n}] {gr.owner_exe} (pid {gr.owner_pid}) has no window"
    return gr, None


def render_json(g, groups, out=None, extra=None):
    out = out or sys.stdout
    json.dump({
        "path": g.path,
        "is_dir": g.is_dir,
        "state": g.probe.state,
        "winerror": g.probe.winerror,
        "held": bool(groups) or g.probe.state == "in-use",
        "uninspected": g.uninspected,
        "groups": [gr.to_dict(i) for i, gr in enumerate(groups, 1)],
        "notes": g.notes,
        **(extra or {}),
    }, out, indent=2)
    print(file=out)


# ------------------------------------------------------------------ CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog="dz unlockit",
        description="Show which processes hold a file or folder, grouped by the window they "
                    "belong to. Changes nothing.")
    p.add_argument("path", help="file or folder that cannot be deleted, renamed or moved")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--focus", nargs="?", const=0, type=int, metavar="N",
                   help="bring holder N's window to the front (N may be omitted when only one "
                        "holder has a window)")
    p.add_argument("--handle", action="store_true",
                   help="also ask Sysinternals handle.exe (slow, needs elevation to see most "
                        "handles; stopped after %ds)" % hd.HANDLE_TIMEOUT)
    p.add_argument("--handle-exe", metavar="PATH",
                   help="handle.exe to use with --handle (default: handle64.exe or handle.exe on PATH)")
    p.add_argument("--max-files", type=int, default=hd.DEFAULT_MAX_FILES, metavar="N",
                   help="for a folder, how many files inside to check for open handles "
                        "(default %(default)s)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if sys.platform != "win32":
        print("unlockit: Windows-only", file=sys.stderr)
        return EXIT_ERROR

    path = os.path.abspath(args.path)
    if not os.path.lexists(path):
        print(f"unlockit: no such file or folder: {path}", file=sys.stderr)
        return EXIT_ERROR

    procs = wf.snapshot_processes()
    me = os.getpid()
    self_chain = set(wf.ancestor_chain(me, procs))
    g = hd.gather(path, use_handle=args.handle or bool(args.handle_exe), handle_exe=args.handle_exe,
                  max_files=args.max_files, exclude_pids={me})
    if g.probe.state == "missing":
        print(f"unlockit: no such file or folder: {path}", file=sys.stderr)
        return EXIT_ERROR

    groups = group_holders(g.holders, path, procs, wf.list_windows(procs), self_chain)

    if args.focus is None:
        (render_json if args.json else render_text)(g, groups)
        if g.probe.state == "error":
            return EXIT_ERROR
        return EXIT_HELD if (groups or g.probe.state == "in-use") else EXIT_FREE

    # --focus: report, then act; the exit code reports the action
    gr, why = pick_group(groups, args.focus)
    result = wf.focus(gr.window.hwnd) if gr else wf.FocusResult(False, "not-chosen", why)
    if args.json:
        render_json(g, groups, extra={"focus": {"index": args.focus or None, **result.__dict__}})
    else:
        render_text(g, groups)
        print()
        if result.ok:
            print(f"focused: \"{gr.window.title}\"" + ("" if result.method == "already" else
                                                       f"  (via {result.method})"))
        else:
            print(f"could not focus: {result.detail}", file=sys.stderr)
    return EXIT_FREE if result.ok else EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
