# Kits

Kits are collections of related tools grouped under a namespace. They're the distribution unit of dazzlecmd -- how tools get organized, shared, and discovered.

## How Kits Work

```
kits/
  core.kit.json          # Ships with dazzlecmd
  dazzletools.kit.json   # DazzleTools collection
  my-org.kit.json        # Your organization's tools
```

Each kit is a JSON file that lists its member tools:

```json
{
    "name": "my-org",
    "version": "1.0.0",
    "description": "My organization's internal tools",
    "author": "My Org",
    "always_active": false,
    "tools": [
        "my-org:deploy",
        "my-org:lint",
        "my-org:report"
    ]
}
```

Tools are referenced as `namespace:tool-name`. The namespace corresponds to a directory under `projects/`:

```
projects/
  my-org/
    deploy/
      .dazzlecmd.json
      deploy.py
    lint/
      .dazzlecmd.json
      lint.py
    report/
      .dazzlecmd.json
      report.py
```

## Kit Types

### Always-Active Kits

Kits with `"always_active": true` are loaded regardless of user selection. The `core` kit uses this -- its tools are available everywhere.

### Selectable Kits

Future: users will be able to enable/disable kits through `dz kit enable/disable`. Currently, all discovered kits are active.

## The Recursive Architecture

This is dazzlecmd's key architectural idea: **kits can be standalone projects that use the same dazzlecmd structure internally**.

### How It Works

Imagine a project called `wtf-tools` that has its own set of diagnostic tools. It can use dazzlecmd's structure internally:

```
wtf-tools/
  projects/
    wtf/
      restart-check/
      crash-dump/
      event-scan/
  kits/
    wtf.kit.json
  src/
    wtf_tools/
      cli.py          # Can work standalone: wtf restart-check
```

This project works on its own as `wtf restart-check`. But it can ALSO be folded into a dazzlecmd installation as a kit:

```bash
# Add wtf-tools as a submodule
git submodule add https://github.com/someone/wtf-tools projects/wtf

# Register the kit
# kits/wtf.kit.json -> points to projects/wtf/
```

Now the same tools are available as `dz restart-check`.

### dz Calling Itself

This creates a recursive pattern:

1. **You** create a dazzlecmd installation with your preferred kits
2. **You** create your own tools using `dz new`
3. **You** organize those tools into kits
4. **Someone else** adds your kit repo as a submodule in their dazzlecmd
5. **They** get all your tools, merged seamlessly with theirs

It's dz all the way down. Every kit repo can be a mini-dz that works standalone AND folds up into the parent.

### Build Your Own dz

You can create your own top-level command that works just like `dz`:

```bash
# Fork dazzlecmd, rename the entry point
# Now "mytools" is YOUR aggregator with YOUR kits
pip install my-tools-cli
mytools deploy staging
mytools lint --fix
```

Or keep `dz` as your aggregator and just add kits:

```bash
# Add your org's tools
dz add --repo https://github.com/my-org/my-tools --kit my-org

# Add a community kit
dz add --repo https://github.com/someone/useful-tools --kit useful

# Now everything is under one roof
dz list
#   deploy      my-org      Deploy to staging/production
#   lint        my-org      Lint and fix code
#   useful-cmd  useful      Something useful from the community
#   rn          core        Rename files using regular expressions
```

### Three-Tier Nesting

The full architecture supports three levels:

```
dazzlecmd (your installation)
  -> kit repos (git submodules)
    -> tool repos (nested submodules within kits)
```

Each level can work independently or nested. The `dz mode` command toggles tools between local development (symlinks) and distributed mode (submodules).

## Kit Management

```bash
# List all kits
dz kit list

# Show tools in a specific kit
dz kit list core

# Show active kits
dz kit status
```

## Creating a Kit

1. Create a `kits/<name>.kit.json` file
2. Create tools under `projects/<name>/`
3. Register tools in the kit JSON

Or import from a GitHub organization:

```bash
# (Future) Auto-generate a kit from all repos in an org
dz kit import --org my-github-org
```

## See Also

- [Creating Tools](creating-tools.md) -- how to build individual tools
- [Manifest Reference](manifests.md) -- `.dazzlecmd.json` specification
