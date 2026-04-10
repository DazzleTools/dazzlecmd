"""Tests for NTFS Alternate Data Stream detection.

Windows-only. Creates files with ADS using Python's native ::stream
syntax and verifies detection filters out :Zone.Identifier.
"""

import os
import sys

import pytest

from _platform import detect_alternate_streams, has_significant_ads

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="ADS tests are Windows-only"
)


@pytest.fixture
def workdir(tmp_path):
    d = tmp_path / "work"
    d.mkdir()
    return d


def _create_ads(path: str, stream_name: str, content: str):
    """Create an alternate data stream on a file."""
    with open(f"{path}:{stream_name}", "w") as f:
        f.write(content)


class TestDetectAlternateStreams:
    def test_plain_file_no_streams(self, workdir):
        """A file with no ADS should return empty list."""
        f = workdir / "plain.txt"
        f.write_text("content")
        assert detect_alternate_streams(str(f)) == []

    def test_file_with_custom_stream(self, workdir):
        """A file with a custom ADS should return that stream."""
        f = workdir / "has_ads.txt"
        f.write_text("main")
        _create_ads(str(f), "custom_stream", "secret")

        streams = detect_alternate_streams(str(f))
        assert len(streams) == 1
        assert "custom_stream" in streams[0]

    def test_zone_identifier_filtered(self, workdir):
        """Zone.Identifier should be filtered out (alert fatigue reduction)."""
        f = workdir / "downloaded.txt"
        f.write_text("fake download")
        _create_ads(str(f), "Zone.Identifier",
                    "[ZoneTransfer]\r\nZoneId=3\r\n")

        streams = detect_alternate_streams(str(f))
        # Zone.Identifier should NOT appear in the result
        assert not any("Zone.Identifier" in s for s in streams)

    def test_mixed_streams(self, workdir):
        """File with both Zone.Identifier and custom ADS returns only custom."""
        f = workdir / "mixed.txt"
        f.write_text("content")
        _create_ads(str(f), "Zone.Identifier", "[ZoneTransfer]\r\nZoneId=3\r\n")
        _create_ads(str(f), "my_custom", "important")

        streams = detect_alternate_streams(str(f))
        assert len(streams) == 1
        assert "my_custom" in streams[0]

    def test_nonexistent_file(self):
        """Detecting on non-existent file should return empty list."""
        assert detect_alternate_streams("C:/nonexistent/path.txt") == []


class TestHasSignificantAds:
    def test_plain_file_no_ads(self, workdir):
        f = workdir / "plain.txt"
        f.write_text("content")
        assert has_significant_ads(str(f)) is False

    def test_file_with_custom_ads(self, workdir):
        f = workdir / "ads.txt"
        f.write_text("content")
        _create_ads(str(f), "custom", "data")
        assert has_significant_ads(str(f)) is True

    def test_file_with_only_zone_identifier(self, workdir):
        """File with only Zone.Identifier should not be 'significant'."""
        f = workdir / "dl.txt"
        f.write_text("content")
        _create_ads(str(f), "Zone.Identifier", "[ZoneTransfer]\r\nZoneId=3\r\n")
        assert has_significant_ads(str(f)) is False
