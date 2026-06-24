"""
md-rm-img -- strip inline base64 image data from markdown files.

Removes ``data:`` URI image blobs from markdown ``![alt](data:image/...;base64,...)``
references while preserving the image's filename in the alt text. By default
the alt text is treated as a filename hint and the tool tries to relink to
the matching on-disk file (local sibling-directory search first, then
``dz fixpath`` as a fallback). When no match is found the link target is
emptied to ``![alt]()``.

Output:
    Default: writes a sidecar ``<stem>.no-graphics<.ext>`` next to the
             input; the original is never modified.
    -D / --delete: mutate the input in place; no backup is written.

Idempotency: rerunning on a file with no remaining ``data:`` URIs is a
no-op (no sidecar produced). Already-stripped ``![alt]()`` references are
left untouched (they would be re-resolved only with a hypothetical
``--relink-empty`` flag, not implemented in this version).

Usage:
    dz md-rm-img file.md
    dz md-rm-img -D file.md                 # in-place, no backup
    dz md-rm-img --no-relink file.md        # skip path resolution
    dz md-rm-img --no-fixpath file.md       # skip dz fixpath fallback
    dz md-rm-img --fence file.md            # protect content inside ``` blocks
    dz md-rm-img -n file.md                 # dry run (report only)
    dz md-rm-img *.md                       # glob (shell-expanded)
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


# Match a markdown image whose link target is a base64-encoded data: URI.
#
# Structure:
#   ![alt](data:image/<subtype>[;params];base64,<base64-blob>)
#
# Anchors:
#   - The base64 alphabet is [A-Za-z0-9+/=] plus tolerated whitespace.
#     None of those characters include '(' or ')', so a literal '\)' is an
#     unambiguous terminator.
#   - We require the ';base64,' marker. URL-encoded data URIs (which use
#     '%' escapes and a different character set) are intentionally not
#     matched in v1; they are rare in Claude Code transcripts.
DATA_URI_IMG_RE = re.compile(
    r"!\[([^\]]*)\]\(\s*data:image/[^;)]+;base64,[A-Za-z0-9+/=\s]*\s*\)",
    re.DOTALL,
)

# Image extensions probed during local + fixpath relink. Used to validate
# that an alt-text "filename hint" actually resembles an image filename
# before launching a search.
IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".bmp", ".tif", ".tiff", ".ico", ".avif", ".heic",
})


# ---------------------------------------------------------------------------
# File-finding helpers
# ---------------------------------------------------------------------------

def _looks_like_image_filename(name):
    """Return True iff ``name`` ends in a known image extension."""
    if not name:
        return False
    ext = os.path.splitext(name)[1].lower()
    return ext in IMAGE_EXTS


def find_local_image(filename, search_root, max_depth=3):
    """Walk ``search_root`` to ``max_depth`` levels deep looking for an exact
    basename match. Returns the absolute path of the closest match, or
    ``None`` if nothing matched.

    "Closest" = shortest absolute path (fewest directory levels from root),
    which keeps ambiguity resolution biased toward the markdown's own
    directory and immediate siblings (``_graphics/``, ``images/``, etc.).
    """
    target = filename.strip()
    if not target:
        return None

    root = Path(search_root)
    if not root.is_dir():
        return None

    # Direct hit at root before walking
    direct = root / target
    if direct.is_file():
        return str(direct.resolve())

    root_parts = len(root.parts)
    matches = []
    for current_root, dirs, files in os.walk(root):
        # Depth gate
        depth = len(Path(current_root).parts) - root_parts
        if depth >= max_depth:
            dirs.clear()
            continue
        if target in files:
            matches.append(str((Path(current_root) / target).resolve()))

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return min(matches, key=len)


def find_via_fixpath(filename, search_root, timeout=10):
    """Subprocess to ``dz fixpath`` to broaden the search. Returns the first
    on-disk path printed by fixpath, or ``None`` on miss / fixpath unavailable.
    """
    if not filename.strip():
        return None

    # Resolve a 'dz' command. On Windows the entry point may be 'dz.exe' or
    # the .py shim depending on install method. shutil.which handles both.
    import shutil
    dz_cmd = shutil.which("dz") or shutil.which("dazzlecmd")
    if not dz_cmd:
        return None

    try:
        result = subprocess.run(
            [dz_cmd, "fixpath", "--search-on", "local", filename],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=search_root,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    # fixpath prints the resolved path on its own line. Take the first
    # non-empty line that points to an existing file.
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def resolve_image_path(filename, markdown_dir, use_fixpath=True):
    """Two-step resolution: local sibling-dir walk, then fixpath fallback."""
    if not _looks_like_image_filename(filename):
        return None
    found = find_local_image(filename, markdown_dir)
    if found:
        return found
    if use_fixpath:
        return find_via_fixpath(filename, markdown_dir)
    return None


# ---------------------------------------------------------------------------
# Content transformation
# ---------------------------------------------------------------------------

def _make_replacer(markdown_dir, relink, use_fixpath, stats):
    """Closure factory for re.sub. Returns the per-match callback."""
    def _replace(match):
        alt = match.group(1)
        stats["stripped"] += 1
        if relink:
            resolved = resolve_image_path(alt, markdown_dir, use_fixpath=use_fixpath)
            if resolved:
                stats["relinked"] += 1
                return f"![{alt}]({resolved})"
        return f"![{alt}]()"
    return _replace


def _strip_outside_fences(content, replacer):
    """Apply ``replacer`` only to lines outside ``` / ~~~ fenced blocks.

    Tracks an open fence by marker (``` or ~~~) and forwards in-fence
    lines verbatim. Per-line regex application is correct because data
    URIs always live on a single line in practice.
    """
    out = []
    in_fence = False
    fence_marker = None
    for line in content.splitlines(keepends=True):
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = True
                fence_marker = stripped[:3]
                out.append(line)
            else:
                out.append(DATA_URI_IMG_RE.sub(replacer, line))
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = None
            out.append(line)
    return "".join(out)


def process_content(content, markdown_dir, relink=True, use_fixpath=True,
                    respect_fences=False, stats=None):
    """Strip data: URI image blobs from ``content``. Returns modified text.

    Stats is mutated in place: keys ``stripped`` and ``relinked`` count
    matches and successful relinks respectively.
    """
    if stats is None:
        stats = {"stripped": 0, "relinked": 0}
    replacer = _make_replacer(markdown_dir, relink, use_fixpath, stats)
    if respect_fences:
        return _strip_outside_fences(content, replacer)
    return DATA_URI_IMG_RE.sub(replacer, content)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def determine_output_path(input_path, delete_mode):
    """Default = sidecar ``<stem>.no-graphics<.ext>``. With ``-D`` = same path."""
    p = Path(input_path)
    if delete_mode:
        return str(p)
    return str(p.with_name(f"{p.stem}.no-graphics{p.suffix}"))


def process_file(input_path, delete_mode=False, relink=True, use_fixpath=True,
                 respect_fences=False, dry_run=False):
    """Process a single file. Returns a dict summarizing what happened."""
    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError(f"Not a file: {input_path}")

    # Read with newline='' so original line endings (LF / CRLF / mixed) are
    # preserved verbatim in the string. encoding='utf-8' (no -sig) means
    # any BOM is preserved as a U+FEFF character at the front of the string,
    # which round-trips through write_text identically.
    with open(p, "r", encoding="utf-8", newline="") as fh:
        content = fh.read()

    stats = {"stripped": 0, "relinked": 0}
    new_content = process_content(
        content,
        markdown_dir=str(p.parent.resolve()),
        relink=relink,
        use_fixpath=use_fixpath,
        respect_fences=respect_fences,
        stats=stats,
    )

    result = {
        "input": str(p),
        "output": None,
        "stripped": stats["stripped"],
        "relinked": stats["relinked"],
        "wrote": False,
    }

    if stats["stripped"] == 0:
        # No images found -> no output (don't pollute the directory with an
        # unchanged sidecar).
        return result

    output_path = determine_output_path(str(p), delete_mode)
    result["output"] = output_path

    if not dry_run:
        with open(output_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_content)
        result["wrote"] = True

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="dz md-rm-img",
        description=(
            "Strip inline base64 image data from markdown files. "
            "Default writes a sidecar <stem>.no-graphics<.ext>; "
            "alt-text filenames are resolved against the local directory "
            "and dz fixpath when possible."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="+", help="Markdown files to process")
    p.add_argument(
        "-D", "--delete", action="store_true",
        help="Modify in place; do not write a sidecar (the original is lost).",
    )
    p.add_argument(
        "--no-relink", action="store_true",
        help="Skip path-resolution; emit empty () instead of attempting to "
             "relink to on-disk files.",
    )
    p.add_argument(
        "--no-fixpath", action="store_true",
        help="Skip the dz fixpath fallback; use only local sibling-directory "
             "search for path resolution.",
    )
    p.add_argument(
        "--fence", action="store_true",
        help="Protect content inside ```/~~~ fenced code blocks (do not "
             "strip data URIs found inside fences). Default: strip everywhere.",
    )
    p.add_argument(
        "-n", "--dry-run", action="store_true",
        help="Report what would change without writing any files.",
    )
    p.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress per-file progress lines.",
    )
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    relink = not args.no_relink
    use_fixpath = not args.no_fixpath
    respect_fences = args.fence

    total = {"files": 0, "no_images": 0, "changed": 0, "stripped": 0, "relinked": 0}

    for f in args.files:
        try:
            r = process_file(
                f,
                delete_mode=args.delete,
                relink=relink,
                use_fixpath=use_fixpath,
                respect_fences=respect_fences,
                dry_run=args.dry_run,
            )
        except FileNotFoundError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        except UnicodeDecodeError:
            print(f"  ERROR: {f}: not valid UTF-8", file=sys.stderr)
            continue

        total["files"] += 1
        total["stripped"] += r["stripped"]
        total["relinked"] += r["relinked"]
        if r["stripped"] == 0:
            total["no_images"] += 1
        if r["wrote"]:
            total["changed"] += 1

        if not args.quiet:
            if r["stripped"] == 0:
                print(f"  {f}: no images found")
            else:
                verb = "would write" if args.dry_run else "wrote"
                print(
                    f"  {f}: stripped {r['stripped']} "
                    f"(relinked {r['relinked']}) -> {verb} {r['output']}"
                )

    if not args.quiet and len(args.files) > 1:
        print(
            f"Total: {total['files']} files processed, "
            f"{total['stripped']} images stripped "
            f"({total['relinked']} relinked), "
            f"{total['changed']} files written, "
            f"{total['no_images']} unchanged"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
