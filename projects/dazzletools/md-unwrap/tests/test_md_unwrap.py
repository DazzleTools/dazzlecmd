"""
Tests for md-unwrap.

Covers the unwrap transform's structure-preservation contract (code fences,
tables, lists, blockquotes, headings, YAML frontmatter, hard breaks),
content-preservation + idempotency invariants, and CLI dispatch via main()
(stdout/file/--check/--inplace/--backup and the stdin guards).
"""

import sys
from pathlib import Path

import pytest

# Locate the tool module without polluting sys.path globally.
_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import md_unwrap as mu  # noqa: E402
sys.path.pop(0)


def _u(text):
    """Convenience: unwrap a multi-line string, return joined output."""
    return "\n".join(mu.unwrap(text.split("\n")))


# ---------------------------------------------------------------------------
# Core transform
# ---------------------------------------------------------------------------

def test_collapses_hard_wrapped_paragraph():
    src = "This is a paragraph\nwrapped across\nthree lines."
    assert _u(src) == "This is a paragraph wrapped across three lines."


def test_blank_line_keeps_paragraphs_separate():
    src = "Para one line\none.\n\nPara two line\ntwo."
    assert _u(src) == "Para one line one.\n\nPara two line two."


def test_code_fence_preserved_verbatim():
    src = "text before\n\n```\nline  one\n  line two\n```\n\ntext after"
    out = _u(src)
    assert "```\nline  one\n  line two\n```" in out


def test_link_reference_definitions_stay_separate():
    # Consecutive [label]: url defs must NOT be joined (the CHANGELOG bug).
    src = ("[Unreleased]: https://example.com/compare/v1...HEAD\n"
           "[1.0.0]: https://example.com/releases/tag/v1.0.0")
    assert _u(src) == src  # unchanged: each definition keeps its own line


def test_paragraph_not_merged_into_following_link_defs():
    src = ("A wrapped paragraph\nover two lines.\n\n"
           "[a]: https://example.com/a\n[b]: https://example.com/b")
    assert _u(src) == ("A wrapped paragraph over two lines.\n\n"
                       "[a]: https://example.com/a\n[b]: https://example.com/b")


def test_table_rows_preserved():
    src = "| a | b |\n| - | - |\n| 1 | 2 |"
    assert _u(src) == src  # each row passes through unchanged


def test_heading_passes_through():
    src = "# Title\n\nbody text\nhere"
    assert _u(src) == "# Title\n\nbody text here"


def test_list_item_continuation_collapsed():
    src = "- item one that\n  wraps a line\n- item two"
    out = _u(src)
    assert "- item one that wraps a line" in out
    assert "- item two" in out


def test_blockquote_collapsed_and_reprefixed():
    src = "> quoted line one\n> quoted line two"
    assert _u(src) == "> quoted line one quoted line two"


def test_yaml_frontmatter_passed_through():
    src = "---\ntitle: Doc\ntags: [a, b]\n---\n\nbody that\nwraps"
    out = _u(src)
    assert out.startswith("---\ntitle: Doc\ntags: [a, b]\n---")
    assert "body that wraps" in out


def test_hard_break_preserved():
    # two trailing spaces on line 1 signal a markdown hard break
    src = "line one  \nline two"
    assert _u(src) == "line one  \nline two"


def test_html_block_preserved():
    src = "<div>\nraw html\nstays\n</div>"
    assert _u(src) == src


def test_html_comment_preserved():
    src = "<!-- a\nmulti-line\ncomment -->"
    assert _u(src) == src


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

SAMPLE = (
    "---\nk: v\n---\n\n"
    "# Heading\n\n"
    "A paragraph that is\nhard wrapped here.\n\n"
    "- list item that\n  continues\n- second item\n\n"
    "> a quote that\n> wraps too\n\n"
    "| h | i |\n| - | - |\n\n"
    "```\ncode  stays\n```\n"
)


def test_content_preserving_word_set():
    # Compare prose tokens in order. Blockquote markers ('>') are structural,
    # not content: collapsing "> a\n> b" to "> a b" legitimately drops the
    # redundant per-line '>' prefix, so exclude '>' from the comparison.
    before = [t for t in SAMPLE.split() if t != ">"]
    after = [t for t in _u(SAMPLE).split() if t != ">"]
    assert before == after  # same tokens in same order; only line breaks change


def test_idempotent():
    once = mu.unwrap(SAMPLE.split("\n"))
    twice = mu.unwrap(once)
    assert once == twice


# ---------------------------------------------------------------------------
# CLI / main()
# ---------------------------------------------------------------------------

def test_main_to_stdout(tmp_path, capsys):
    f = tmp_path / "in.md"
    f.write_text("a line\nwrapped.\n", encoding="utf-8")
    rc = mu.main([str(f)])
    assert rc == 0
    assert capsys.readouterr().out == "a line wrapped.\n"


def test_main_to_output_file(tmp_path):
    f = tmp_path / "in.md"
    f.write_text("a line\nwrapped.\n", encoding="utf-8")
    out = tmp_path / "out.md"
    rc = mu.main([str(f), str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8") == "a line wrapped.\n"


def test_main_check_returns_1_when_changes(tmp_path):
    f = tmp_path / "in.md"
    f.write_text("a line\nwrapped.\n", encoding="utf-8")
    assert mu.main(["--check", str(f)]) == 1


def test_main_check_returns_0_when_clean(tmp_path):
    f = tmp_path / "in.md"
    f.write_text("already one line.\n", encoding="utf-8")
    assert mu.main(["--check", str(f)]) == 0


def test_main_inplace_rewrites(tmp_path):
    f = tmp_path / "in.md"
    f.write_text("a line\nwrapped.\n", encoding="utf-8")
    rc = mu.main(["-i", str(f)])
    assert rc == 0
    assert f.read_text(encoding="utf-8") == "a line wrapped.\n"


def test_main_inplace_backup(tmp_path):
    f = tmp_path / "in.md"
    original = "a line\nwrapped.\n"
    f.write_text(original, encoding="utf-8")
    rc = mu.main(["-i", "-b", str(f)])
    assert rc == 0
    bak = tmp_path / "in.md.bak-pre-unwrap"
    assert bak.read_text(encoding="utf-8") == original
    assert f.read_text(encoding="utf-8") == "a line wrapped.\n"


def test_main_inplace_stdin_guard():
    assert mu.main(["-i", "-"]) == 2


def test_main_check_stdin_guard():
    assert mu.main(["--check", "-"]) == 2


def test_main_inplace_with_output_rejected(tmp_path):
    f = tmp_path / "in.md"
    f.write_text("x\n", encoding="utf-8")
    assert mu.main(["-i", str(f), str(tmp_path / "o.md")]) == 2
