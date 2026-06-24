"""
Tests for md-rm-img.

Covers the regex contract, file-finding helpers, content transformation,
output-path resolution, idempotency, and CLI dispatch via main().
"""

import os
import sys
from pathlib import Path

import pytest

# Locate the tool module without polluting sys.path globally
_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import md_rm_img  # noqa: E402
sys.path.pop(0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# A short but realistic-looking base64 blob (decodes to gibberish but
# matches the character class).
BASE64_BLOB = "UklGRpqTAABXRUJQVlA4II6TAAAwgQKdASq/AwEEPm02l0kkIqIhIvI5MIANiWdu="


def _data_uri(subtype="webp", blob=None):
    return f"data:image/{subtype};base64,{blob or BASE64_BLOB}"


def _img(alt, subtype="webp", blob=None):
    return f"![{alt}]({_data_uri(subtype, blob)})"


@pytest.fixture
def transcript(tmp_path):
    """A markdown file in tmp_path with three data: URI images and one
    plain reference, no on-disk image files alongside.
    """
    p = tmp_path / "transcript.md"
    body = (
        "# Title\n"
        "\n"
        "Intro paragraph.\n"
        "\n"
        + _img("alpha.webp") + "\n"
        "\n"
        "Middle text.\n"
        "\n"
        + _img("beta.png", subtype="png") + "\n"
        "\n"
        + _img("gamma.gif", subtype="gif") + "\n"
        "\n"
        "Trailing text with a regular link: ![other](https://example.com/x.png)\n"
    )
    p.write_text(body, encoding="utf-8")
    return p


@pytest.fixture
def transcript_with_local_files(tmp_path):
    """Markdown plus a sibling _graphics/ directory containing one
    matching image. Lets us exercise local-search relink.
    """
    md = tmp_path / "doc.md"
    body = (
        "# With Graphics\n\n"
        + _img("foo.webp") + "\n\n"
        + _img("missing.png", subtype="png") + "\n"
    )
    md.write_text(body, encoding="utf-8")
    graphics = tmp_path / "_graphics"
    graphics.mkdir()
    (graphics / "foo.webp").write_bytes(b"fake-webp-bytes")
    return md, graphics


# ---------------------------------------------------------------------------
# Regex contract
# ---------------------------------------------------------------------------

class TestRegex:
    def test_matches_basic_data_uri_image(self):
        text = _img("foo.png", subtype="png")
        m = md_rm_img.DATA_URI_IMG_RE.search(text)
        assert m is not None
        assert m.group(1) == "foo.png"

    def test_matches_empty_alt(self):
        text = "![](data:image/png;base64,ABCD=)"
        m = md_rm_img.DATA_URI_IMG_RE.search(text)
        assert m is not None
        assert m.group(1) == ""

    def test_matches_alt_with_spaces_and_punctuation(self):
        text = "![ChatGPT Image Apr 25, 2026.png](data:image/png;base64,XYZ=)"
        m = md_rm_img.DATA_URI_IMG_RE.search(text)
        assert m is not None
        assert m.group(1) == "ChatGPT Image Apr 25, 2026.png"

    def test_does_not_match_url_link(self):
        text = "![alt](https://example.com/x.png)"
        assert md_rm_img.DATA_URI_IMG_RE.search(text) is None

    def test_does_not_match_local_file_link(self):
        text = "![alt](images/foo.png)"
        assert md_rm_img.DATA_URI_IMG_RE.search(text) is None

    def test_does_not_match_already_stripped(self):
        text = "![alt]()"
        assert md_rm_img.DATA_URI_IMG_RE.search(text) is None

    def test_does_not_match_bare_reference_no_parens(self):
        # The transcript has lines like "![1777001198413_image.png]" --
        # bare reference, no link target. Must not match.
        text = "![1777001198413_image.png]"
        assert md_rm_img.DATA_URI_IMG_RE.search(text) is None

    def test_finds_multiple_in_string(self):
        text = _img("a.png", subtype="png") + "\n\n" + _img("b.gif", subtype="gif")
        matches = list(md_rm_img.DATA_URI_IMG_RE.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(1) == "a.png"
        assert matches[1].group(1) == "b.gif"


# ---------------------------------------------------------------------------
# Content transformation
# ---------------------------------------------------------------------------

class TestProcessContent:
    def test_strip_with_no_relink_yields_empty_parens(self, tmp_path):
        text = _img("anything.png", subtype="png")
        out = md_rm_img.process_content(
            text, str(tmp_path), relink=False, use_fixpath=False
        )
        assert out == "![anything.png]()"

    def test_strip_relink_finds_local_file(self, transcript_with_local_files):
        md, graphics = transcript_with_local_files
        content = md.read_text(encoding="utf-8")
        stats = {"stripped": 0, "relinked": 0}
        out = md_rm_img.process_content(
            content,
            markdown_dir=str(md.parent.resolve()),
            relink=True,
            use_fixpath=False,
            stats=stats,
        )
        assert stats["stripped"] == 2
        assert stats["relinked"] == 1
        # foo.webp should have been resolved to the _graphics path
        expected = str((graphics / "foo.webp").resolve())
        assert f"![foo.webp]({expected})" in out
        # missing.png had no on-disk file -> empty parens
        assert "![missing.png]()" in out

    def test_idempotent_on_already_stripped(self, tmp_path):
        text = "![foo.png]()\n\n![bar.gif]()\n"
        out = md_rm_img.process_content(
            text, str(tmp_path), relink=True, use_fixpath=False
        )
        assert out == text

    def test_idempotent_run_twice(self, transcript):
        first = md_rm_img.process_content(
            transcript.read_text(encoding="utf-8"),
            str(transcript.parent),
            relink=False,
            use_fixpath=False,
        )
        second = md_rm_img.process_content(
            first, str(transcript.parent), relink=False, use_fixpath=False
        )
        assert first == second

    def test_no_images_in_content_returns_unchanged(self, tmp_path):
        text = "# Just prose\n\nNothing to see here.\n"
        out = md_rm_img.process_content(
            text, str(tmp_path), relink=False, use_fixpath=False
        )
        assert out == text

    def test_default_strips_inside_code_fences(self, tmp_path):
        # Default behavior: strip everywhere, including inside fences
        text = (
            "Before fence\n"
            "```\n"
            + _img("inside.png", subtype="png") + "\n"
            "```\n"
            "After fence\n"
            + _img("outside.png", subtype="png") + "\n"
        )
        stats = {"stripped": 0, "relinked": 0}
        out = md_rm_img.process_content(
            text, str(tmp_path), relink=False, use_fixpath=False,
            respect_fences=False, stats=stats,
        )
        assert stats["stripped"] == 2
        assert "![inside.png]()" in out
        assert "![outside.png]()" in out

    def test_fence_flag_protects_inside_fences(self, tmp_path):
        text = (
            "Before fence\n"
            "```\n"
            + _img("inside.png", subtype="png") + "\n"
            "```\n"
            "After fence\n"
            + _img("outside.png", subtype="png") + "\n"
        )
        stats = {"stripped": 0, "relinked": 0}
        out = md_rm_img.process_content(
            text, str(tmp_path), relink=False, use_fixpath=False,
            respect_fences=True, stats=stats,
        )
        # outside is stripped; inside is preserved verbatim
        assert stats["stripped"] == 1
        assert "![outside.png]()" in out
        assert _img("inside.png", subtype="png") in out

    def test_fence_with_tilde_marker(self, tmp_path):
        text = (
            "~~~\n"
            + _img("inside.png", subtype="png") + "\n"
            "~~~\n"
        )
        stats = {"stripped": 0, "relinked": 0}
        out = md_rm_img.process_content(
            text, str(tmp_path), relink=False, use_fixpath=False,
            respect_fences=True, stats=stats,
        )
        assert stats["stripped"] == 0
        assert _img("inside.png", subtype="png") in out


# ---------------------------------------------------------------------------
# Helpers: filename detection, local search
# ---------------------------------------------------------------------------

class TestFilenameDetection:
    @pytest.mark.parametrize("name", [
        "foo.png", "FOO.PNG", "image.webp", "diagram.SVG",
        "x.gif", "y.jpeg", "z.JPG", "a.bmp",
    ])
    def test_recognized_extensions(self, name):
        assert md_rm_img._looks_like_image_filename(name) is True

    @pytest.mark.parametrize("name", [
        "", "no-extension", "foo.txt", "image", "data.json", "doc.md",
    ])
    def test_rejected_non_image(self, name):
        assert md_rm_img._looks_like_image_filename(name) is False


class TestFindLocalImage:
    def test_finds_in_root(self, tmp_path):
        (tmp_path / "x.png").write_bytes(b"")
        found = md_rm_img.find_local_image("x.png", str(tmp_path))
        assert found == str((tmp_path / "x.png").resolve())

    def test_finds_in_subdir(self, tmp_path):
        sub = tmp_path / "_graphics"
        sub.mkdir()
        (sub / "y.webp").write_bytes(b"")
        found = md_rm_img.find_local_image("y.webp", str(tmp_path))
        assert found == str((sub / "y.webp").resolve())

    def test_returns_none_when_missing(self, tmp_path):
        assert md_rm_img.find_local_image("ghost.png", str(tmp_path)) is None

    def test_picks_shortest_path_on_collision(self, tmp_path):
        near = tmp_path / "near.png"
        near.write_bytes(b"")
        far = tmp_path / "deeply" / "nested" / "near.png"
        far.parent.mkdir(parents=True)
        far.write_bytes(b"")
        found = md_rm_img.find_local_image("near.png", str(tmp_path))
        # near is shorter -> should win
        assert found == str(near.resolve())

    def test_respects_max_depth(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "deep.png"
        deep.parent.mkdir(parents=True)
        deep.write_bytes(b"")
        # max_depth=2 should not find a file at depth 4
        assert md_rm_img.find_local_image("deep.png", str(tmp_path), max_depth=2) is None
        # max_depth=5 should find it
        assert md_rm_img.find_local_image("deep.png", str(tmp_path), max_depth=5) is not None


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------

class TestDetermineOutputPath:
    def test_default_sidecar(self):
        assert md_rm_img.determine_output_path("foo.md", delete_mode=False).endswith(
            "foo.no-graphics.md"
        )

    def test_delete_mode_returns_input(self):
        assert md_rm_img.determine_output_path("foo.md", delete_mode=True) == "foo.md"

    def test_sidecar_with_path(self, tmp_path):
        p = tmp_path / "sub" / "doc.md"
        out = md_rm_img.determine_output_path(str(p), delete_mode=False)
        assert out.endswith(os.path.join("sub", "doc.no-graphics.md"))

    def test_sidecar_preserves_extension(self):
        out = md_rm_img.determine_output_path("foo.markdown", delete_mode=False)
        assert out.endswith("foo.no-graphics.markdown")


# ---------------------------------------------------------------------------
# process_file (full file I/O round-trip)
# ---------------------------------------------------------------------------

class TestProcessFile:
    def test_default_writes_sidecar_and_preserves_original(self, transcript):
        original_size = transcript.stat().st_size
        original_text = transcript.read_text(encoding="utf-8")

        result = md_rm_img.process_file(
            str(transcript), relink=False, use_fixpath=False
        )

        assert result["stripped"] == 3
        assert result["wrote"] is True
        sidecar = transcript.parent / "transcript.no-graphics.md"
        assert sidecar.exists()
        # Original is untouched
        assert transcript.stat().st_size == original_size
        assert transcript.read_text(encoding="utf-8") == original_text
        # Sidecar is smaller (image data removed)
        assert sidecar.stat().st_size < original_size

    def test_delete_mode_overwrites_in_place(self, transcript):
        original_size = transcript.stat().st_size
        result = md_rm_img.process_file(
            str(transcript), delete_mode=True, relink=False, use_fixpath=False
        )
        assert result["wrote"] is True
        # No sidecar
        assert not (transcript.parent / "transcript.no-graphics.md").exists()
        # Original is now smaller
        assert transcript.stat().st_size < original_size

    def test_no_images_writes_nothing(self, tmp_path):
        p = tmp_path / "plain.md"
        p.write_text("# Just text\n", encoding="utf-8")
        result = md_rm_img.process_file(str(p), relink=False, use_fixpath=False)
        assert result["stripped"] == 0
        assert result["wrote"] is False
        assert not (tmp_path / "plain.no-graphics.md").exists()

    def test_dry_run_writes_nothing_but_reports(self, transcript):
        result = md_rm_img.process_file(
            str(transcript), relink=False, use_fixpath=False, dry_run=True
        )
        assert result["stripped"] == 3
        assert result["wrote"] is False
        assert not (transcript.parent / "transcript.no-graphics.md").exists()

    def test_relink_resolves_local_file(self, transcript_with_local_files):
        md, graphics = transcript_with_local_files
        result = md_rm_img.process_file(
            str(md), relink=True, use_fixpath=False
        )
        assert result["stripped"] == 2
        assert result["relinked"] == 1
        sidecar = md.parent / "doc.no-graphics.md"
        out = sidecar.read_text(encoding="utf-8")
        assert str((graphics / "foo.webp").resolve()) in out
        assert "![missing.png]()" in out

    def test_preserves_crlf_line_endings(self, tmp_path):
        p = tmp_path / "crlf.md"
        body = "line1\r\n" + _img("x.png", subtype="png") + "\r\nline3\r\n"
        p.write_bytes(body.encode("utf-8"))
        md_rm_img.process_file(str(p), relink=False, use_fixpath=False)
        sidecar = tmp_path / "crlf.no-graphics.md"
        raw = sidecar.read_bytes()
        # CRLF preserved
        assert b"\r\n" in raw
        # No bare LFs that weren't part of a CRLF
        assert raw.replace(b"\r\n", b"").count(b"\n") == 0

    def test_preserves_utf8_bom(self, tmp_path):
        p = tmp_path / "bom.md"
        body = "﻿# Title\n" + _img("x.png", subtype="png") + "\n"
        p.write_text(body, encoding="utf-8")
        md_rm_img.process_file(str(p), relink=False, use_fixpath=False)
        sidecar = tmp_path / "bom.no-graphics.md"
        raw = sidecar.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            md_rm_img.process_file(str(tmp_path / "nope.md"))

    def test_idempotent_second_run_is_noop(self, transcript):
        # First run produces a sidecar
        md_rm_img.process_file(str(transcript), relink=False, use_fixpath=False)
        sidecar = transcript.parent / "transcript.no-graphics.md"
        assert sidecar.exists()

        # Now process the sidecar -- it has no remaining data: URIs
        result = md_rm_img.process_file(str(sidecar), relink=False, use_fixpath=False)
        assert result["stripped"] == 0
        assert result["wrote"] is False
        # No double-sidecar like transcript.no-graphics.no-graphics.md
        assert not (transcript.parent / "transcript.no-graphics.no-graphics.md").exists()


# ---------------------------------------------------------------------------
# CLI dispatch via main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_basic_invocation(self, transcript, capsys):
        rc = md_rm_img.main([str(transcript), "--no-fixpath", "--no-relink"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "stripped 3" in out
        assert (transcript.parent / "transcript.no-graphics.md").exists()

    def test_main_dry_run(self, transcript, capsys):
        rc = md_rm_img.main([
            str(transcript), "-n", "--no-fixpath", "--no-relink"
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "would write" in out
        assert not (transcript.parent / "transcript.no-graphics.md").exists()

    def test_main_delete_flag(self, transcript, capsys):
        original_size = transcript.stat().st_size
        rc = md_rm_img.main([
            str(transcript), "-D", "--no-fixpath", "--no-relink"
        ])
        assert rc == 0
        assert transcript.stat().st_size < original_size
        assert not (transcript.parent / "transcript.no-graphics.md").exists()

    def test_main_quiet(self, transcript, capsys):
        rc = md_rm_img.main([
            str(transcript), "-q", "--no-fixpath", "--no-relink"
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert out == ""

    def test_main_no_relink_via_flag(self, transcript_with_local_files, capsys):
        md, graphics = transcript_with_local_files
        rc = md_rm_img.main([
            str(md), "--no-relink", "--no-fixpath"
        ])
        assert rc == 0
        sidecar = md.parent / "doc.no-graphics.md"
        out = sidecar.read_text(encoding="utf-8")
        # No paths populated even though foo.webp exists in _graphics/
        assert "![foo.webp]()" in out
        assert str((graphics / "foo.webp").resolve()) not in out

    def test_main_missing_file_continues_with_error(self, transcript, tmp_path, capsys):
        rc = md_rm_img.main([
            str(tmp_path / "ghost.md"),
            str(transcript),
            "--no-fixpath", "--no-relink",
        ])
        # Missing file logs ERROR but main continues to next file -> rc 0
        assert rc == 0
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert (transcript.parent / "transcript.no-graphics.md").exists()
