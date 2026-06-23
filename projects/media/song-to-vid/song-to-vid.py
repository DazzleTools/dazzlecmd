#!/usr/bin/env python3
"""song-to-vid: make a video per audio file from its embedded album art.

For each input audio file, extracts the embedded cover image via ffmpeg and
loops it as a still image over the full track (libx264 -tune stillimage, AAC
320k). Useful for turning an album/track into an uploadable video.

Ported from Z:\\omnitools\\vid-preview-maker\\song-to-vid.py into the dazzlecmd
'media' kit. Self-contained: shells out to ffmpeg only (list-form subprocess,
no shell=True). Pure stdlib otherwise, single main(argv) entry point.

Usage:
  dz song-to-vid track.mp3
  dz song-to-vid *.flac -o videos
  dz song-to-vid a.mp3 b.mp3 -o out -v
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

_AUDIO_EXTS = (".mp3", ".flac", ".wav")


def extract_album_art(ffmpeg: str, audio_file: Path, image_file: Path) -> bool:
    """Extract the embedded cover image to image_file. Returns True on success."""
    proc = subprocess.run(
        [ffmpeg, "-y", "-i", str(audio_file), str(image_file)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not image_file.exists():
        logging.error("Failed to extract album art from %s", audio_file)
        return False
    return True


def create_video(ffmpeg: str, image_file: Path, audio_file: Path, video_file: Path) -> bool:
    """Loop the still image over the audio track. Returns True on success."""
    proc = subprocess.run(
        [ffmpeg, "-y", "-loop", "1", "-i", str(image_file), "-i", str(audio_file),
         "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "320k",
         "-pix_fmt", "yuv420p", "-shortest", str(video_file)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        logging.error("Failed to create video for %s", audio_file)
        return False
    logging.info("Successfully created video for %s", audio_file)
    return True


def process_audio_file(ffmpeg: str, audio_file: Path, output_dir: Path) -> bool:
    image_file = output_dir / f"{audio_file.stem}.jpg"
    video_file = output_dir / f"{audio_file.stem}.mp4"
    if not extract_album_art(ffmpeg, audio_file, image_file):
        logging.warning("No album art found for %s. Skipping video creation.", audio_file)
        return False
    return create_video(ffmpeg, image_file, audio_file, video_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="song-to-vid",
        description="Create videos from audio files using their embedded album art.",
    )
    parser.add_argument("audio_files", nargs="+", help="paths to audio files")
    parser.add_argument("-o", "--output", default="output_videos",
                        help="output directory for videos (default: output_videos)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="enable verbose logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("error: ffmpeg not found on PATH.", file=sys.stderr)
        return 2

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    any_ok = False
    for audio_file_path in args.audio_files:
        audio_file = Path(audio_file_path)
        if audio_file.is_file() and audio_file.suffix.lower() in _AUDIO_EXTS:
            any_ok = process_audio_file(ffmpeg, audio_file, output_dir) or any_ok
        else:
            logging.warning("Invalid or unsupported file: %s", audio_file)

    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
