"""Hard-wrap a commit-message file body at a width boundary.

Commit messages are plain text in `git log` -- git does not reflow them,
so long unwrapped paragraphs look bad. This wraps the BODY at `width`
chars while preserving:
  - the subject line (line 1) verbatim, however long
  - blank lines
  - section headers (lines starting with '#')
  - list items (lines starting with '- ' or 'N. '), with hanging indent
  - fenced/indented code-ish lines (already-indented continuations)

Usage: python wrap_commit_msg.py <path> [width]
"""
import re
import sys
import textwrap


def wrap_file(path, width=72):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    out = []
    for i, line in enumerate(lines):
        # Subject line: never wrap.
        if i == 0:
            out.append(line)
            continue
        # Blank line, header line: passthrough.
        if not line.strip() or line.lstrip().startswith("#"):
            out.append(line)
            continue
        # List item: "- ..." or "N. ..." -> wrap with hanging indent.
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            lead, marker, rest = m.group(1), m.group(2), m.group(3)
            prefix = f"{lead}{marker} "
            hang = " " * len(prefix)
            wrapped = textwrap.fill(
                rest, width=width,
                initial_indent=prefix, subsequent_indent=hang,
                break_long_words=False, break_on_hyphens=False,
            )
            out.append(wrapped)
            continue
        # Already-indented continuation (code/example): leave verbatim.
        if line.startswith("    "):
            out.append(line)
            continue
        # Regular prose paragraph line: wrap at width.
        wrapped = textwrap.fill(
            line, width=width,
            break_long_words=False, break_on_hyphens=False,
        )
        out.append(wrapped)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


if __name__ == "__main__":
    path = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 72
    wrap_file(path, width)
    print(f"Wrapped {path} at {width} chars.")
