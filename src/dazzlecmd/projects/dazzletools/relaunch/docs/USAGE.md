# dz relaunch

Remember working sets of terminal tabs -- folders, commands, shell scripts and Claude sessions -- and bring them back after a restart, one short command per tab. It restores folders and programs; it does not restore scrollback, window layout, splits or window positions, and it does not open tabs for you (yet).

## First run

```text
dz relaunch new ck3                          # a set
dz relaunch ck3 add --here                   # in each tab you want back: its folder (and this tab claims it)
dz relaunch ck3 add C:\code\ck3 -- codex resume --last      # a command, run in that folder
dz relaunch ck3 add --shell cmd "cd mod && build.cmd"       # a compound action, in cmd syntax
dz relaunch ck3 add --claude CK3__2026-10-24__worker        # a Claude session, through csb
dz relaunch new today --from-csb current     # one Claude member per session csb sees open
dz relaunch shell-init cmd --install         # the wrapper that lets claim change the tab's folder
```

`--install` writes `dzr.cmd` beside `dz.exe`, a folder already on PATH, so nothing needs setting; it never overwrites a `dzr.cmd` that is not relaunch's, and `--uninstall` moves it to the safedel trash. To place it yourself: `dz relaunch shell-init cmd > <a local folder on PATH>\dzr.cmd`.

**Linux, macOS and Git Bash.** A program cannot change the folder of the shell that started it, and a script on PATH runs as a separate process, so in bash `dzr` is a file you *source* -- the leading dot runs it inside your shell:

```bash
dz relaunch shell-init bash --install   # writes dzr beside dz (Git Bash on Windows: into ~/bin)
. dzr ck3 claim                         # the dot is what lets it change this shell's folder
```

It never edits your shell's startup files. For plain `dzr ck3 claim`, add one line to `~/.bashrc` (or `~/.zshrc`) yourself: `alias dzr='. dzr'`. Install needs no root: `dzr` goes wherever `dz` lives (`/usr/local/bin`, `~/.local/bin`, a venv), so it is on PATH for whoever runs `dz`. Under Git Bash it goes to `~/bin` instead, because a script with no extension must not sit in a folder Windows searches. Running `dzr` without the dot says how to call it; `--uninstall` moves it to the safedel trash. Prefer a function in `~/.bashrc`? `dz relaunch shell-init bash >> ~/.bashrc` (only the function goes to stdout).

## After a restart

```text
dz relaunch                     # what you had, per set, and what was open last session
dzr ck3 claim                   # in each new tab: the next member, last session's first; the tab moves to its folder
dzr ck3 claim -o                # ...and run it here (shows what it will run, asks [y/N]; -y skips)
dz relaunch ck3                 # who has what, and what claim takes next
```

Every `claim` prints what it took, with a tag -- `open last session -- before restart`, `last open 2 sessions ago`, `never opened` -- and the member that comes next.

## The words

- **set** -- a named working set: one portable JSON file, `~/.dz/relaunch/sets/<name>.json` (`DZ_RELAUNCH_HOME` moves the whole store).
- **member** -- one entry: a folder, a command with its arguments, a shell script in a named dialect (`cmd`, `bash`, `pwsh`), or a Claude session. Addressed as `<set>:<id>`; ids never change.
- **claim** -- this tab's hold on one member. A tab holds one member at a time. A claim ends when the tab closes or the machine restarts -- no reset needed.
- **session** -- a run of claims. A restart, or closing every tab, starts the next one; `dz relaunch last` (or `last~1`, `last:3`) reads what each held.

## Actions

| Command | Does |
|---|---|
| `dz relaunch` / `list` | dashboard; `list --removed` (`only` / `all`) shows removed sets and members |
| `dz relaunch <set>` / `show` | roster; `<set>:<id>` a member's card; `last`, `last~N`, `last:<n>` the session views |
| `new <set>` | create (`--here`, `--notes`, `--from-csb current\|last\|boot\|<csb set>`) |
| `<set> add` | add a member (folder, `--here`, `-- <command>`, `--shell DIALECT SCRIPT`, `--claude SESSION`; `--label`, `--notes`, `--at N`) |
| `<set> edit [<id>]` | change fields (`--label`, `--notes`, `--folder`, `-- <argv>`); with no flags, the whole set in your editor, applied only if nobody changed it meanwhile |
| `<set> note [<id>] "text"` | a note on the set or a member |
| `<set> claim [<id>]` | take the next member (or that one); `-o` run it here; `--next` take another; `--yes` a second copy of one open elsewhere |
| `<set> launch [<id>...]` | start the set's **detached** members -- programs that need no tab, such as an editor (`add --detach -- code C:\code\ck3`). Each starts once per boot, with no window and no claim; naming one starts it again. Asks first, like `claim -o` |
| `release` | let go of this tab's member; `<set> release --all` |
| `<set> drop rm\|disable [<id>...]` | remove (a whole set goes to the safedel trash; `dz safedel recover` brings it back) or hide |
| `<set> enable [<id>...]` | undo disable |
| `shell-init cmd\|bash` | print the `dzr` wrapper |

The set name comes first (`dz relaunch ck3 claim`); the action-first form also works with one set (`dz relaunch claim ck3`).

## Running members (`claim -o`)

- It shows the exact program, arguments and folder and asks `[y/N]`. Turn the question off with `-y`, `DZ_RELAUNCH_OPEN_ASKS=0`, a line `DZ_RELAUNCH_OPEN_ASKS=0` in `~/.dz/relaunch/.env`, or `"open_asks": false` in `~/.dz/relaunch/local/config.json`. A `.env` in the current folder is never read.
- A command or shell member that relaunch did not write as it now reads (edited by hand, or from another machine) is always shown and asked about, even with `-y`.
- Without a console (a pipe, a script) `-o` only prints.
- Programs are found the way Windows runs them (PATH and PATHEXT). For a `.cmd`/`.bat` program, arguments containing `& | < > ^ % ! "` are refused -- make it a shell member instead.
- Claude members run `csb resume <id>`; csb chooses the folder and asks if the session looks open already. relaunch only ever reads from csb.

## Exit codes and output

0 ok, 1 error, 2 usage, 3 refused (nothing changed), 4 partial; after `claim -o` starts a program, its exit code. The last line is the verdict (`relaunch: CLAIMED ck3 2 mod`); `--json` puts it inside one JSON object. `-v`/`-q` change the detail; `--log-file PATH` writes diagnostics to a file.

## Limits

Tested on Windows (Command Prompt in Windows Terminal; Git Bash). Not yet run on Linux or macOS. The tab is identified by its own shell process below the terminal (Windows Terminal, VS Code, mintty, ...); terminals not in that list fall back to the outermost shell.
