# dz rn

Rename files using regular expressions.

## Quick Start

```bash
# Rename .bak files to .txt
dz rn "(.*)\.bak" "\g<1>.txt" *.bak

# Add a prefix to all Python files
dz rn "(.*\.py)" "test_\g<1>" *.py

# Auto-number files with \q incrementer
dz rn "(.*)\.(jpg)" "\g<1>_\q.\g<2>" *.jpg
# photo.jpg -> photo_0.jpg, sunset.jpg -> sunset_1.jpg, ...
```

## Usage

```
dz rn [-q] [-v] [-d] [--version] regex replacement filenames...
```

### Positional Arguments

| Argument | Description |
|----------|-------------|
| `regex` | Python regular expression to match in filenames |
| `replacement` | Replacement string with capture group references |
| `filenames` | One or more filenames or glob patterns |

### Flags

| Flag | Description |
|------|-------------|
| `-q`, `--quiet` | Suppress output |
| `-v`, `--verbose` | Verbose output |
| `-d`, `--debug` | Debug output showing transformation steps |
| `--version` | Show version |

## Capture Groups

Uses Python's `re` module syntax:

```bash
# Named groups
dz rn "(?P<name>.*)\.(?P<ext>.*)" "\g<name>_backup.\g<ext>" *.txt

# Numbered groups
dz rn "(.*)_(old)\.(.*)" "\g<1>_new.\g<3>" *_old.*
```

## The `\q` Incrementer

A unique feature: `\q` in the replacement string auto-increments for each matched file:

```bash
# Number a sequence of images
dz rn "(.*)\.(png)" "screenshot_\q.\g<2>" *.png
# image.png -> screenshot_0.png
# photo.png -> screenshot_1.png
# frame.png -> screenshot_2.png
```

## Safety

- Won't overwrite existing files -- skips if the target name already exists
- Reports success/failure for each rename
- Use `-d` (debug) mode to preview transformations without renaming

## Platform Notes

Works identically on all platforms. Uses Python's `os.rename()` and `re` module.

## See Also

- Python [re module](https://docs.python.org/3/library/re.html) -- regex syntax reference
