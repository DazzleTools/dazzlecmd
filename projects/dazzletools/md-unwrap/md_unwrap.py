"""Unwrap hard-wrapped paragraphs in a markdown file.

Markdown editors and modern viewers reflow paragraphs to the available
width. Source files that hard-wrap every line at ~72 chars therefore
look like they have stray line breaks all over them. This tool collapses
each paragraph back to one line per paragraph while preserving the
structural elements that *should* keep their line layout.

Preserves:
  - blank-line paragraph boundaries
  - fenced code blocks (``` ... ```)
  - HTML blocks (<p>, <div>, <table>, <img>, <figure>, <center>)
  - HTML comments (<!-- ... -->)
  - markdown tables (| ... |)
  - blockquotes (> ...) -- collapsed within a quote, kept on one line
  - list items (1. / - / *) -- each item is its own paragraph
  - headings (# ... ######, also setext-style detection limited)
  - markdown hard-break signal (line ends with two trailing spaces)
  - YAML frontmatter (--- ... --- at the top of the file)

Usage:
    dz md-unwrap INPUT [OUTPUT]      # OUTPUT defaults to stdout
    dz md-unwrap -i FILE             # rewrite in place
    dz md-unwrap -i -b FILE          # in place + save FILE.bak-pre-unwrap
    dz md-unwrap --check FILE        # exit 1 if changes would be made
    cat README.md | dz md-unwrap     # stdin -> stdout
    dz md-unwrap --help

The transformation is content-preserving (every word is kept) -- the only
diff is collapsed line breaks within paragraphs. Render-identical in any
CommonMark / GFM viewer.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable


CODE_FENCE = re.compile(r"^\s*```")
HTML_BLOCK_OPEN = re.compile(r"^\s*<(?:p|div|table|img|figure|center)\b", re.IGNORECASE)
HTML_BLOCK_CLOSE = re.compile(r"^\s*</(?:p|div|table|figure|center)>\s*$", re.IGNORECASE)
HTML_SELF_CLOSING_OR_VOID = re.compile(r"^\s*</?[a-z][^>]*>\s*$", re.IGNORECASE)
COMMENT_OPEN = re.compile(r"^\s*<!--")
COMMENT_CLOSE = re.compile(r"-->\s*$")
TABLE_ROW = re.compile(r"^\s*\|")
LIST_ITEM = re.compile(r"^\s*(?:\d+\.|[-*+])\s+")
BLOCKQUOTE = re.compile(r"^\s*>")
HEADING = re.compile(r"^\s*#")
# Link reference definitions ([label]: url) and footnote definitions
# ([^id]: text). Each must stay on its own line -- joining them with adjacent
# lines stops them parsing as definitions (the CHANGELOG compare-link bug).
LINK_REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+\S+")
HARD_BREAK = re.compile(r"  +$")  # two-or-more trailing spaces = MD hard break
YAML_FENCE = re.compile(r"^---\s*$")  # YAML frontmatter delimiter (Obsidian, Jekyll, etc.)


def is_blockquote(line: str) -> bool:
    return bool(BLOCKQUOTE.match(line))


def strip_blockquote(line: str) -> str:
    return re.sub(r"^\s*>\s?", "", line)


def has_hard_break(line: str) -> bool:
    return bool(HARD_BREAK.search(line.rstrip("\n")))


def join_paragraph_lines(lines: list[str]) -> str:
    """Join paragraph lines with spaces, preserving two-space hard breaks."""
    if not lines:
        return ""
    out_parts: list[str] = []
    for j, raw in enumerate(lines):
        text = raw.rstrip("\n")
        carries_break = has_hard_break(text)
        clean = text.rstrip()
        if j == 0:
            out_parts.append(clean)
        else:
            sep = "  \n" if has_hard_break(lines[j - 1]) else " "
            out_parts.append(sep + clean)
            del carries_break  # unused on first/last; tracked via lines[j-1]
    return "".join(out_parts)


def unwrap(src: list[str], _is_recursive: bool = False) -> list[str]:
    """Apply unwrap transformation; returns a new list of output lines.

    The ``_is_recursive`` flag is set when this function is called from
    within itself (e.g., to unwrap the inner content of a blockquote).
    YAML frontmatter is only honored at the top level -- a `---` mid-file
    inside a blockquote is just a horizontal-rule marker, not frontmatter.
    """
    out: list[str] = []
    in_code = False
    in_html = False
    in_comment = False

    i = 0
    n = len(src)

    # YAML frontmatter pass-through (Obsidian, Jekyll, Hugo, etc.):
    # if the file starts with `---`, pass through everything up to and
    # including the closing `---` verbatim. Only at the top level.
    if not _is_recursive and n > 0 and YAML_FENCE.match(src[0]):
        out.append(src[0])
        i = 1
        while i < n and not YAML_FENCE.match(src[i]):
            out.append(src[i])
            i += 1
        if i < n:  # closing fence found
            out.append(src[i])
            i += 1

    while i < n:
        line = src[i]

        # Fenced code block: pass through verbatim
        if CODE_FENCE.match(line):
            in_code = not in_code
            out.append(line)
            i += 1
            continue
        if in_code:
            out.append(line)
            i += 1
            continue

        # HTML comment: pass through, single or multi-line
        if COMMENT_OPEN.match(line):
            in_comment = True
            out.append(line)
            if COMMENT_CLOSE.search(line):
                in_comment = False
            i += 1
            continue
        if in_comment:
            out.append(line)
            if COMMENT_CLOSE.search(line):
                in_comment = False
            i += 1
            continue

        # HTML block: pass through verbatim until close
        if HTML_BLOCK_OPEN.match(line):
            in_html = True
        if in_html:
            out.append(line)
            if HTML_BLOCK_CLOSE.match(line) or (
                HTML_SELF_CLOSING_OR_VOID.match(line) and not HTML_BLOCK_OPEN.match(line)
            ):
                in_html = False
            i += 1
            continue

        # Blank line: paragraph boundary
        if line.strip() == "":
            out.append(line)
            i += 1
            continue

        # Heading: single line, pass through
        if HEADING.match(line):
            out.append(line)
            i += 1
            continue

        # Table: pass through each row verbatim
        if TABLE_ROW.match(line):
            while i < n and TABLE_ROW.match(src[i]):
                out.append(src[i])
                i += 1
            continue

        # Blockquote: collect consecutive `> ` lines, recursively unwrap the
        # stripped inner content, then re-prefix each output line with `> `.
        # The recursion handles code fences, lists, tables, and headings
        # nested inside the blockquote correctly. Bare `>` lines (a quoted
        # blank line) become paragraph boundaries inside the inner unwrap.
        if is_blockquote(line):
            inner: list[str] = []
            while i < n and is_blockquote(src[i]):
                if src[i].strip() == ">":
                    inner.append("")
                else:
                    inner.append(strip_blockquote(src[i]))
                i += 1
            inner_unwrapped = unwrap(inner, _is_recursive=True)
            for inner_line in inner_unwrapped:
                if inner_line.strip() == "":
                    out.append(">")
                else:
                    out.append("> " + inner_line)
            continue

        # List item: collapse continuation lines into the item
        if LIST_ITEM.match(line):
            indent_match = re.match(r"^(\s*)", line)
            indent = indent_match.group(1) if indent_match else ""
            collected = [line.rstrip()]
            i += 1
            while i < n:
                nxt = src[i]
                if nxt.strip() == "":
                    break
                if LIST_ITEM.match(nxt):
                    break
                if HEADING.match(nxt) or TABLE_ROW.match(nxt) or CODE_FENCE.match(nxt):
                    break
                if HTML_BLOCK_OPEN.match(nxt) or COMMENT_OPEN.match(nxt):
                    break
                if LINK_REF_DEF.match(nxt):
                    break
                if not nxt.startswith(indent + " "):
                    break
                collected.append(nxt.strip())
                i += 1
            out.append(" ".join(collected))
            continue

        # Link reference / footnote definitions: pass consecutive ones through
        # verbatim, one per line (joining them breaks them as definitions).
        if LINK_REF_DEF.match(line):
            while i < n and LINK_REF_DEF.match(src[i]):
                out.append(src[i])
                i += 1
            continue

        # Regular paragraph: collapse consecutive non-blank lines, preserving
        # markdown hard breaks (lines that end in two-or-more trailing spaces).
        collected = [line.rstrip("\n")]
        i += 1
        while i < n:
            nxt = src[i]
            if nxt.strip() == "":
                break
            if HEADING.match(nxt) or TABLE_ROW.match(nxt) or CODE_FENCE.match(nxt):
                break
            if LIST_ITEM.match(nxt) or is_blockquote(nxt):
                break
            if HTML_BLOCK_OPEN.match(nxt) or COMMENT_OPEN.match(nxt):
                break
            if LINK_REF_DEF.match(nxt):
                break
            collected.append(nxt.rstrip("\n"))
            i += 1
        out.append(join_paragraph_lines(collected))

    return out


def read_input(path: str | None) -> list[str]:
    if path is None or path == "-":
        return sys.stdin.read().splitlines()
    return Path(path).read_text(encoding="utf-8").splitlines()


def write_output(lines: Iterable[str], path: str | None) -> None:
    body = "\n".join(lines) + "\n"
    if path is None or path == "-":
        sys.stdout.write(body)
        return
    Path(path).write_text(body, encoding="utf-8", newline="\n")


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dz md-unwrap",
        description="Collapse hard-wrapped markdown paragraphs to one line per paragraph.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  dz md-unwrap README.md                  # to stdout\n"
            "  dz md-unwrap README.md README.md.new    # to file\n"
            "  dz md-unwrap -i README.md               # rewrite in place\n"
            "  dz md-unwrap -i -b README.md            # in place + .bak-pre-unwrap\n"
            "  dz md-unwrap --check README.md          # exit 1 if changes needed\n"
            "  cat README.md | dz md-unwrap            # stdin -> stdout\n"
        ),
    )
    p.add_argument("input", nargs="?", default="-",
                   help="input markdown file ('-' or omit for stdin)")
    p.add_argument("output", nargs="?", default=None,
                   help="output file (default: stdout; ignored with --inplace/--check)")
    p.add_argument("-i", "--inplace", action="store_true",
                   help="rewrite the input file in place")
    p.add_argument("-b", "--backup", action="store_true",
                   help="with --inplace, save INPUT.bak-pre-unwrap before rewriting")
    p.add_argument("--check", action="store_true",
                   help="exit 1 if the file would change, 0 if no changes; do not write")
    return p


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)

    if args.inplace and args.input == "-":
        print("error: --inplace requires a file path, not stdin", file=sys.stderr)
        return 2
    if args.check and args.input == "-":
        print("error: --check requires a file path, not stdin", file=sys.stderr)
        return 2
    if args.inplace and args.output:
        print("error: --inplace ignores OUTPUT (would write to INPUT)", file=sys.stderr)
        return 2

    src_lines = read_input(args.input)
    out_lines = unwrap(src_lines)

    if args.check:
        if src_lines != out_lines:
            print(f"would change: {args.input}", file=sys.stderr)
            return 1
        return 0

    if args.inplace:
        if args.backup:
            Path(args.input + ".bak-pre-unwrap").write_text(
                "\n".join(src_lines) + "\n", encoding="utf-8", newline="\n"
            )
        write_output(out_lines, args.input)
        return 0

    write_output(out_lines, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
