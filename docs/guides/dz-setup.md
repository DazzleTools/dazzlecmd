# `dz setup` -- Run a tool's declared setup command

`dz setup <tool>` dispatches the setup command declared in a tool's
manifest. The engine never installs dependencies itself -- it runs the
author-declared setup command, in the tool's own directory, and
propagates the exit code back.

This reference covers the `dz setup` subcommand. For the `setup` manifest
schema (fields, platform resolution, `_schema_version`, template variables),
see `docs/guides/manifests.md`.

## Read-only mode

### `dz setup` (no arguments)

Lists tools that have a `setup.command` declared. (v0.7.21+ -- see issue #33.)

```
$ dz setup
Tools with setup commands:
  dazzletools:my-python-tool        Installs Python dependencies
  wtf:restarted                     -
  core:some-compiled-tool           Builds the tool from source

Run: dz setup <tool> to execute a tool's setup.
```

Tools without a setup declaration do not appear.

## Executing a tool's setup

### `dz setup <tool>`

Resolves the tool, reads its `setup` block from the manifest, applies
platform resolution (and `_vars` substitution if declared), and runs
the effective command via `subprocess.run(cmd, shell=True)` in the tool's
directory.

```
$ dz setup dazzletools:my-python-tool
Running setup for dazzletools:my-python-tool...
  Note: Installs Python dependencies into a venv
  Command: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  Working dir: /home/user/.dazzletools/my-python-tool

<subprocess output>

Setup for dazzletools:my-python-tool completed successfully.
```

Exit code matches the subprocess's exit code. If the tool has no `setup`
block, `dz setup` prints an informational message and returns 0.

### Platform resolution

The command that runs depends on the current host. Resolution order:

1. `setup.platforms.<os>.<subtype>.command` if current host matches
   (e.g. `linux.debian`, `windows.win11`, `macos.macos14`)
2. `setup.platforms.<os>.general.command` if subtype not matched
3. `setup.platforms.<os>.command` top-level field if defined
4. `setup.command` (default fallback)

See `docs/guides/manifests.md#setup` for full schema + examples.

### Template variables

If the manifest declares `_vars` (at manifest top, block level, or
platform level), the setup command is substituted before dispatch.

```json
{
    "_vars": {"venv_dir": ".venv"},
    "setup": {
        "platforms": {
            "linux": {"command": "python3 -m venv {{venv_dir}} && {{venv_dir}}/bin/pip install -r requirements.txt"}
        }
    }
}
```

See `docs/guides/manifests.md#template-variables-_vars-v0720` for scoping
rules.

### Error cases

| Scenario | Exit code | Message |
|---|---|---|
| Tool not found | 1 | `Tool '<name>' not found.` |
| No `setup` block declared | 0 | `Tool '<fqcn>' has no setup command declared.` |
| No command for current platform | 1 | `No setup command available for platform '<os>.<subtype>'. Add setup.command, setup.platforms.<os>, or setup.platforms.<os>.general to the manifest.` |
| Unresolved `{{var}}` in setup command | 1 | `Error: '{{name}}' referenced in setup.platforms.<os>.command but not declared in _vars at any visible scope. Available vars: [...]` |
| Malformed `_schema_version` | 1 | `Error: setup for '<name>' declares _schema_version='<v>', but this library only supports: 1.` |
| Subprocess exits nonzero | matches subprocess | `Setup for <fqcn> failed with exit code <n>.` |

### What the engine will NOT do

Per the "dumb dispatcher" principle (#30, Phase 4):

- The engine never creates venvs, installs packages, or runs setup automatically.
- `dz <tool>` does NOT run `dz setup <tool>` implicitly even if the tool's interpreter is missing. Authors who want that UX should write a wrapper.
- The engine does not parse setup output for dependency info.

These are intentional boundaries -- they keep the engine safe to use on
third-party tools without surprising side effects.

## Related

- [Manifests reference](manifests.md#setup) -- full `setup` schema
- [`dz kit`](dz-kit.md) -- kit management
- GitHub issues: #33 (`dz setup` feature), #40 (multi-platform setup), #41 (`_vars` template variables)
