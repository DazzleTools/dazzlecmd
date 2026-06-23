#!/usr/bin/env python3
"""vidresize: AR-preserving video resize with optional audio injection.

Encodes through ffmpeg with a proven Instagram-friendly recipe (libx264 CRF 17,
high@4.1, AAC 192k, +faststart), strips all container metadata by default
(removes any ComfyUI workflow JSON), can inject/mux a music track with
fade-in/out, and optionally injects phone-spoof tags via exiftool.

Ported from C:\\code\\comfyui_experiment\\output\\resize-vid.py into the dazzlecmd
'media' kit. Pure stdlib + subprocess, single main(argv) entry point, no
module-level side effects -- matches the dazzlecmd python-tool contract.

Usage:
  dz vidresize -i in.mp4 -W 1400
  dz vidresize -i in.mp4 -H 1600 --as-phone
  dz vidresize -i in.mp4 -W 1080 -o reel.mp4 --as-phone iphone-8 -y
  dz vidresize -i in.mp4 -H 1600 \
      --audio song.mp3 --audio-start 30 \
      --audio-fade-in 1 --audio-fade-out 2
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path

# Phone presets for --as-phone. Modelled on Z:\OmniTools\exiftool\*.cmd patterns.
# Values are exiftool args (input file appended at call time).
PHONE_PRESETS: dict[str, list[str]] = {
    "galaxy-s3": [
        "-Make=Samsung",
        "-Model=GT-I9300",
        "-Software=4.3",
    ],
    "iphone-5": [
        "-Make=Apple",
        "-Model=iPhone 5",
        "-Software=9.3.5",
    ],
    "iphone-8": [
        "-Make=Apple",
        "-Model=iPhone 8",
        "-Software=13.7",
    ],
}
DEFAULT_PHONE = "galaxy-s3"
FALLBACK_FPS = "24"
EXIFTOOL_WINDOWS_FALLBACK = r"Z:\OmniTools\exiftool\exiftool.exe"
DEFAULT_AUDIO_SEARCH_DIR = ""  # optional personal default; empty = broad scope


def detect_source_fps(ffprobe: str, src: Path) -> str | None:
    """Return the source video stream's r_frame_rate (e.g. '30000/1001'), or None."""
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(src)],
            check=True, capture_output=True, text=True,
        )
        fps = out.stdout.strip()
        return fps if fps and fps != "0/0" else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_video_duration(ffprobe: str, src: Path) -> float | None:
    """Return source duration in seconds (float), or None if probing fails."""
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error",
             "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
            check=True, capture_output=True, text=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None


_AUDIO_EXTS = {".mp3", ".aac", ".m4a", ".wav", ".mp4", ".ogg", ".flac", ".opus", ".wma"}


def search_audio_file(pattern: str, search_dir: Path | None) -> list[Path]:
    """Find audio files matching a glob pattern.

    Preferred backend: `dz fixpath -p --all` -- broadens beyond a hint dir, uses
    Everything index on Windows, finds mangled paths. Falls back to `fd` then
    to pathlib.rglob if dz is unavailable.

    `search_dir` is a hint passed as `-d` to dz fixpath; the tool may broaden
    beyond it (this is desirable). If None, dz fixpath searches its default
    scope (typically anywhere via Everything). For fd / rglob fallbacks,
    search_dir is mandatory (a search root is required).

    The `-p` flag is critical -- without it, dz fixpath performs its configured
    default action (often: open the file in the system player). We always pass
    `-p` to enforce print-only behavior.

    Returns matches sorted by full path. Results are filtered to actual files
    with audio-ish extensions to avoid cache/sidecar false-positives (Adobe
    .cfa/.pek files whose names contain '.mp3', etc.).
    """
    def _filter(paths) -> list[Path]:
        return sorted(
            p for p in paths
            if p.is_file() and p.suffix.lower() in _AUDIO_EXTS
        )

    dz = shutil.which("dz")
    if dz:
        cmd = [dz, "fixpath", "-p", "--all"]
        if search_dir is not None:
            cmd += ["-d", str(search_dir)]
        cmd.append(pattern)
        try:
            out = subprocess.run(cmd, check=True, capture_output=True, text=True)
            paths = [Path(line.strip()) for line in out.stdout.splitlines()
                     if line.strip()]
            return _filter(paths)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    if search_dir is None:
        # fd / rglob need a search root and we have none.
        return []

    fd = shutil.which("fd")
    if fd:
        try:
            out = subprocess.run(
                [fd, "-t", "f", "-g", pattern, str(search_dir)],
                check=True, capture_output=True, text=True,
            )
            paths = [Path(line.strip()) for line in out.stdout.splitlines()
                     if line.strip()]
            return _filter(paths)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    return _filter(search_dir.rglob(pattern))


def build_audio_filter(fade_in: float, fade_out: float, video_dur: float) -> str:
    """Compose the -af audio-filter chain. Includes apad so audio shorter than
    video is silence-padded; -shortest then clips to video duration."""
    filters: list[str] = []
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        fade_start = max(0.0, video_dur - fade_out)
        filters.append(f"afade=t=out:st={fade_start}:d={fade_out}")
    filters.append("apad")  # pad with silence past natural end of audio
    return ",".join(filters)


def find_exiftool(override: str | None) -> str | None:
    if override:
        return override if Path(override).is_file() else None
    found = shutil.which("exiftool")
    if found:
        return found
    if sys.platform == "win32" and Path(EXIFTOOL_WINDOWS_FALLBACK).is_file():
        return EXIFTOOL_WINDOWS_FALLBACK
    return None


def build_ffmpeg_cmd(
    src: Path, dst: Path, vf: str, fps: str, strip: bool, force: bool,
    audio_path: Path | None = None,
    audio_start: str | None = None,
    audio_filter: str | None = None,
) -> list[str]:
    cmd: list[str] = ["ffmpeg", "-i", str(src)]
    if audio_path is not None:
        # -ss BEFORE -i is input-side seek (fast). Applies to the next input.
        if audio_start:
            cmd += ["-ss", audio_start]
        cmd += ["-i", str(audio_path)]
        # Map video from input 0, audio from input 1; drop any audio in source.
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    cmd += [
        "-vf", vf,
        "-r", fps,
        "-c:v", "libx264", "-crf", "17", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
    ]
    if audio_filter:
        cmd += ["-af", audio_filter]
    if audio_path is not None:
        # -shortest clips output to the shorter input. With apad in the audio
        # filter making the audio effectively infinite, this means: output ends
        # exactly at the video's natural duration.
        cmd += ["-shortest"]
    if strip:
        # -map_metadata -1 drops container tags. The +bitexact triplet is what
        # actually removes the residual `encoder=Lavf...` tag that ffmpeg writes
        # otherwise. Both are needed for a clean output.
        cmd += [
            "-map_metadata", "-1",
            "-map_chapters", "-1",
            "-fflags", "+bitexact",
            "-flags:v", "+bitexact",
            "-flags:a", "+bitexact",
        ]
    if force:
        cmd.append("-y")
    cmd.append(str(dst))
    return cmd


def apply_phone_preset(exiftool: str, dst: Path, preset_name: str) -> int:
    args = PHONE_PRESETS[preset_name]
    cmd = [exiftool, "-overwrite_original", *args, str(dst)]
    return subprocess.call(cmd)


# MP4 atoms that act as pure containers (their payload is just child atoms).
_MP4_CONTAINER_ATOMS = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}
# Visual SampleEntry codings whose VisualSampleEntry layout we know.
# CompressorName Pascal string is at offset 50 from the atom start, 32 bytes wide.
_MP4_VISUAL_SAMPLE_ENTRIES = {b"avc1", b"avc3", b"hev1", b"hvc1"}


def _walk_for_visual_sample_entries(f, start: int, end: int) -> list[int]:
    """Recursively walk MP4 atoms in [start, end); return atom offsets for
    avc1 / avc3 / hev1 / hvc1 sample entries.
    """
    found: list[int] = []
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        hdr = f.read(8)
        if len(hdr) < 8:
            break
        size = struct.unpack(">I", hdr[0:4])[0]
        atype = hdr[4:8]
        if size == 1:
            ext = f.read(8)
            if len(ext) < 8:
                break
            size = struct.unpack(">Q", ext)[0]
            child_start = pos + 16
        elif size == 0:
            size = end - pos  # extends to end
            child_start = pos + 8
        else:
            child_start = pos + 8
        if size < 8:
            break
        atom_end = pos + size

        if atype in _MP4_VISUAL_SAMPLE_ENTRIES:
            found.append(pos)
        elif atype in _MP4_CONTAINER_ATOMS:
            found.extend(_walk_for_visual_sample_entries(f, child_start, atom_end))
        elif atype == b"stsd":
            # stsd: 1 byte version + 3 bytes flags + 4 bytes entry_count, then children.
            found.extend(_walk_for_visual_sample_entries(f, child_start + 8, atom_end))

        pos = atom_end
    return found


def erase_compressor_name(dst: Path) -> int:
    """Zero out the CompressorName Pascal string in every visual SampleEntry.

    The CompressorName is a 32-byte field at offset 50 inside avc1/hev1/etc.
    Pascal-style (1 length byte + up to 31 ASCII bytes, zero-padded). Spec-legal
    to be empty; many real-world MP4s leave it blank. Removes the lingering
    `Lavc libx264` tell that `+bitexact` and exiftool can't reach.

    Returns count of entries patched.
    """
    file_size = dst.stat().st_size
    with open(dst, "r+b") as f:
        offsets = _walk_for_visual_sample_entries(f, 0, file_size)
        for off in offsets:
            f.seek(off + 50)
            f.write(b"\x00" * 32)
    return len(offsets)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="vidresize",
        description="Resize a video by width or height (AR preserved), "
                    "strip metadata, optionally inject an audio track, "
                    "and optionally inject phone-spoof tags.",
    )
    ap.add_argument("-i", "--input", required=True,
                    help="input video file")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("-W", "--width", type=int,
                   help="target width in pixels; height auto-derived (AR preserved)")
    g.add_argument("-H", "--height", type=int,
                   help="target height in pixels; width auto-derived (AR preserved)")
    ap.add_argument("-o", "--output",
                    help="output path (default: <input>_resized_<w|h><N>.mp4)")
    ap.add_argument("-y", "--force", action="store_true",
                    help="overwrite output if it exists")
    ap.add_argument("--keep-metadata", action="store_true",
                    help="skip the metadata strip (default: strip everything)")
    ap.add_argument("--as-phone", nargs="?", const=DEFAULT_PHONE, default=None,
                    metavar="PRESET",
                    help=f"after strip, inject phone-spoof metadata via exiftool. "
                         f"Bare flag = {DEFAULT_PHONE}. "
                         f"Options: {', '.join(PHONE_PRESETS.keys())}")
    ap.add_argument("--exiftool-path", default=None,
                    help="override exiftool executable location")
    ap.add_argument("--fps", default=None,
                    help=f"output frame rate (default: detect from source via "
                         f"ffprobe, fall back to {FALLBACK_FPS})")
    audio_src = ap.add_mutually_exclusive_group()
    audio_src.add_argument("--audio", default=None, metavar="FILE",
                    help="audio file to inject (mp3/aac/m4a/wav/mp4 - anything "
                         "ffmpeg decodes). Replaces source audio if present.")
    audio_src.add_argument("--audio-srch", default=None, metavar="PATTERN",
                    help="search for audio by glob (e.g. 'Time to Shine*.mp3'). "
                         "Preferred backend: 'dz fixpath -p' (broadens search, "
                         "uses Everything index on Windows). Falls back to 'fd' "
                         "then to stdlib rglob.")
    ap.add_argument("--audio-search-dir", default=None, metavar="DIR",
                    help="hint directory for --audio-srch (default: none -- "
                         "dz fixpath uses its broad scope. Required for fd / "
                         "rglob fallbacks.)")
    ap.add_argument("-as", "--audio-start", default=None, metavar="TIME",
                    help="start position in the audio file (seconds or HH:MM:SS). "
                         "Default: 0.")
    ap.add_argument("-afi", "--audio-fade-in", type=float, default=0.0,
                    metavar="SECS",
                    help="fade-in duration at the start of the video (default: 0)")
    ap.add_argument("-afo", "--audio-fade-out", type=float, default=0.0,
                    metavar="SECS",
                    help="fade-out duration at the end of the video (default: 0)")

    args = ap.parse_args(argv)

    if args.as_phone and args.as_phone not in PHONE_PRESETS:
        print(f"error: unknown --as-phone preset: {args.as_phone}", file=sys.stderr)
        print(f"  valid: {', '.join(PHONE_PRESETS.keys())}", file=sys.stderr)
        return 2

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("error: ffmpeg not found on PATH.", file=sys.stderr)
        return 2
    ffprobe = shutil.which("ffprobe") or ""

    src = Path(args.input)
    if not src.is_file():
        print(f"error: input not found: {src}", file=sys.stderr)
        return 2

    target = args.width if args.width is not None else args.height
    if target < 16:
        print(f"error: target dimension too small (min 16): {target}", file=sys.stderr)
        return 2

    if args.width is not None:
        vf = f"scale={args.width}:-2:flags=lanczos"
        tag = f"_resized_w{args.width}"
    else:
        vf = f"scale=-2:{args.height}:flags=lanczos"
        tag = f"_resized_h{args.height}"

    dst = Path(args.output) if args.output else src.with_name(src.stem + tag + ".mp4")
    if dst.exists() and not args.force:
        print(f"error: output exists (use -y to overwrite): {dst}", file=sys.stderr)
        return 2

    if args.fps:
        fps = args.fps
    else:
        detected = detect_source_fps(ffprobe, src) if ffprobe else None
        fps = detected if detected else FALLBACK_FPS
        if detected:
            print(f"[info] detected source fps: {detected}")
        else:
            print(f"[info] could not detect source fps, using fallback: {FALLBACK_FPS}")

    exiftool = None
    if args.as_phone:
        exiftool = find_exiftool(args.exiftool_path)
        if not exiftool:
            print("error: --as-phone requested but exiftool was not found.",
                  file=sys.stderr)
            print("  Hints:", file=sys.stderr)
            print(f"    Windows: {EXIFTOOL_WINDOWS_FALLBACK} (autodetected if present)",
                  file=sys.stderr)
            print("    Or:      https://exiftool.org/", file=sys.stderr)
            print("    macOS:   brew install exiftool", file=sys.stderr)
            print("    Linux:   apt install libimage-exiftool-perl", file=sys.stderr)
            print("  Or pass --exiftool-path /abs/path/to/exiftool.", file=sys.stderr)
            return 2

    audio_path: Path | None = None
    audio_filter: str | None = None
    if args.audio_srch:
        if args.audio_search_dir:
            search_dir = Path(args.audio_search_dir)
            if not search_dir.is_dir():
                print(f"error: audio search dir not found: {search_dir}",
                      file=sys.stderr)
                return 2
        else:
            # No explicit hint -- prefer the configured default if it exists,
            # otherwise pass None so dz fixpath uses its broad default scope.
            default = Path(DEFAULT_AUDIO_SEARCH_DIR) if DEFAULT_AUDIO_SEARCH_DIR else None
            search_dir = default if default and default.is_dir() else None
        matches = search_audio_file(args.audio_srch, search_dir)
        if not matches:
            print(f"error: no audio files match '{args.audio_srch}' under "
                  f"{search_dir}", file=sys.stderr)
            return 2
        audio_path = matches[0]
        if len(matches) == 1:
            print(f"[audio-srch] matched: {audio_path}")
        else:
            print(f"[audio-srch] {len(matches)} matches, using first:")
            for m in matches[:5]:
                arrow = "->" if m == audio_path else "  "
                print(f"    {arrow} {m}")
            if len(matches) > 5:
                print(f"    ... and {len(matches) - 5} more (pass --audio with "
                      f"a full path to pick a different one)")
    elif args.audio:
        audio_path = Path(args.audio)

    if audio_path is not None:
        if not audio_path.is_file():
            print(f"error: audio file not found: {audio_path}", file=sys.stderr)
            return 2
        if args.audio_fade_in < 0 or args.audio_fade_out < 0:
            print("error: --audio-fade-in / --audio-fade-out must be >= 0",
                  file=sys.stderr)
            return 2
        # We only need the video duration if fade-out is requested (afade-out
        # needs an absolute start timestamp). Fade-in starts at t=0.
        if args.audio_fade_out > 0:
            video_dur = get_video_duration(ffprobe, src) if ffprobe else None
            if video_dur is None:
                print("error: could not determine source video duration; "
                      "--audio-fade-out requires ffprobe.", file=sys.stderr)
                return 2
            if args.audio_fade_out > video_dur:
                print(f"warning: --audio-fade-out ({args.audio_fade_out}s) "
                      f"is longer than the video ({video_dur:.2f}s); "
                      f"the fade will start at t=0.", file=sys.stderr)
        else:
            video_dur = 0.0  # unused
        audio_filter = build_audio_filter(
            args.audio_fade_in, args.audio_fade_out, video_dur,
        )
        print(f"[audio] {audio_path.name}"
              + (f" @ {args.audio_start}" if args.audio_start else "")
              + (f", fade-in {args.audio_fade_in}s" if args.audio_fade_in > 0 else "")
              + (f", fade-out {args.audio_fade_out}s" if args.audio_fade_out > 0 else ""))

    cmd = build_ffmpeg_cmd(
        src=src, dst=dst, vf=vf, fps=fps,
        strip=not args.keep_metadata, force=args.force,
        audio_path=audio_path,
        audio_start=args.audio_start,
        audio_filter=audio_filter,
    )
    print(f"[ffmpeg] {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"error: ffmpeg failed (exit {rc})", file=sys.stderr)
        return rc

    if args.as_phone:
        print(f"[exiftool] applying preset: {args.as_phone}")
        rc = apply_phone_preset(exiftool, dst, args.as_phone)
        if rc != 0:
            print(f"warning: exiftool returned {rc} (output may still be usable)",
                  file=sys.stderr)
            return rc
        # Erase the codec-level CompressorName ('Lavc libx264'). exiftool can't
        # touch this; we patch the avc1/hev1 SampleEntry directly.
        try:
            patched = erase_compressor_name(dst)
            print(f"[patch] zeroed CompressorName in {patched} visual sample "
                  f"{'entry' if patched == 1 else 'entries'}")
        except OSError as e:
            print(f"warning: CompressorName erase failed: {e}", file=sys.stderr)

    print(f"done: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
