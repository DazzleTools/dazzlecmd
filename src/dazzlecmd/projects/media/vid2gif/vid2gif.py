#!/usr/bin/env python3
"""vid2gif: high-quality video -> GIF via ffmpeg two-pass palette + gifsicle.

Bottles the proven recipe: a per-clip optimal palette (palettegen, stats_mode=full)
followed by paletteuse with selectable dithering, then an optional gifsicle pass
for further (optionally lossy) compression. Reusable at any size via --scale,
--width, or --height, with optional trim (--start/--duration) and fps control.

Pure stdlib + subprocess, single main(argv) entry point, no module-level side
effects -- matches the dazzlecmd python-tool contract.

Usage:
  dz vid2gif demo.mp4                         # full size, keep fps, optimize
  dz vid2gif demo.mp4 --scale 0.5             # half resolution (AR preserved)
  dz vid2gif demo.mp4 --width 800 --fps 15    # 800px wide, 15 fps
  dz vid2gif demo.mp4 --start 5 --duration 3  # trim a 3s clip starting at 5s
  dz vid2gif demo.mp4 --lossy 80              # extra gifsicle lossy compression
  dz vid2gif demo.mp4 --dither bayer --colors 128 -o out.gif
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def build_scale_expr(scale: float | None, width: int | None, height: int | None) -> str | None:
    """Return an ffmpeg scale filter expression (AR preserved), or None for no resize."""
    if scale is not None:
        return f"scale=iw*{scale}:ih*{scale}:flags=lanczos"
    if width is not None:
        return f"scale={width}:-1:flags=lanczos"
    if height is not None:
        return f"scale=-1:{height}:flags=lanczos"
    return None


def build_filter_chain(scale_expr: str | None, fps: float | None) -> str:
    """Compose the shared pre-palette filter chain (fps first, then scale)."""
    parts: list[str] = []
    if fps is not None:
        parts.append(f"fps={fps}")
    if scale_expr is not None:
        parts.append(scale_expr)
    return ",".join(parts)


def build_paletteuse(dither: str, bayer_scale: int) -> str:
    """Return the paletteuse filter with the requested dithering."""
    if dither == "none":
        return "paletteuse=dither=none"
    if dither == "bayer":
        return f"paletteuse=dither=bayer:bayer_scale={bayer_scale}"
    return f"paletteuse=dither={dither}"


def seek_args(start: str | None, duration: str | None) -> list[str]:
    """Input-side -ss/-t args (applied identically in both ffmpeg passes)."""
    args: list[str] = []
    if start:
        args += ["-ss", start]
    if duration:
        args += ["-t", duration]
    return args


def human_mb(path: Path) -> str:
    return f"{path.stat().st_size / (1024 * 1024):.1f} MB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="vid2gif",
        description="Convert a video to a high-quality GIF (ffmpeg two-pass "
                    "palette + optional gifsicle compression).",
    )
    ap.add_argument("input", help="input video file")
    ap.add_argument("-o", "--output",
                    help="output gif path (default: <input>.gif, same folder)")
    ap.add_argument("-y", "--force", action="store_true",
                    help="overwrite output if it exists")

    size = ap.add_mutually_exclusive_group()
    size.add_argument("--scale", type=float, metavar="FACTOR",
                      help="scale factor, AR preserved (e.g. 0.5 = half size)")
    size.add_argument("-W", "--width", type=int, metavar="PX",
                      help="target width in px; height auto-derived (AR preserved)")
    size.add_argument("-H", "--height", type=int, metavar="PX",
                      help="target height in px; width auto-derived (AR preserved)")

    ap.add_argument("--fps", type=float, default=None, metavar="N",
                    help="output frame rate (default: keep source fps)")
    ap.add_argument("--start", default=None, metavar="TS",
                    help="trim start (seconds or HH:MM:SS)")
    ap.add_argument("--duration", default=None, metavar="SEC",
                    help="trim duration from --start (seconds or HH:MM:SS)")

    ap.add_argument("--colors", type=int, default=256, metavar="N",
                    help="max palette colors, 2-256 (default: 256)")
    ap.add_argument("--dither", default="sierra2_4a",
                    choices=["sierra2_4a", "floyd_steinberg", "bayer", "none"],
                    help="dithering method (default: sierra2_4a)")
    ap.add_argument("--bayer-scale", type=int, default=5, metavar="N",
                    help="bayer dither scale 0-5, only with --dither bayer (default: 5)")

    ap.add_argument("--lossy", type=int, default=None, metavar="N",
                    help="gifsicle lossy level (e.g. 80); higher = smaller/noisier")
    ap.add_argument("--no-optimize", action="store_true",
                    help="skip the gifsicle pass entirely (ffmpeg output is final)")
    ap.add_argument("--keep-raw", action="store_true",
                    help="keep the intermediate palette.png and pre-gifsicle gif")

    args = ap.parse_args(argv)

    if not (2 <= args.colors <= 256):
        print(f"error: --colors must be 2-256 (got {args.colors})", file=sys.stderr)
        return 2

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("error: ffmpeg not found on PATH.", file=sys.stderr)
        return 2

    src = Path(args.input)
    if not src.is_file():
        print(f"error: input not found: {src}", file=sys.stderr)
        return 2

    out = Path(args.output) if args.output else src.with_suffix(".gif")
    if out.exists() and not args.force:
        print(f"error: output exists (use -y to overwrite): {out}", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)

    gifsicle = shutil.which("gifsicle")
    do_gifsicle = not args.no_optimize and gifsicle is not None
    if args.lossy is not None and not do_gifsicle:
        if gifsicle is None:
            print("warning: --lossy requested but gifsicle not found on PATH; "
                  "writing the un-optimized ffmpeg gif instead.", file=sys.stderr)
        # If --no-optimize was also set, honor that silently.

    scale_expr = build_scale_expr(args.scale, args.width, args.height)
    chain = build_filter_chain(scale_expr, args.fps)

    palette = out.with_name(out.stem + "_palette.png")
    raw = out.with_name(out.stem + "_raw.gif")
    seek = seek_args(args.start, args.duration)

    # Pass 1: generate an optimal palette for the (filtered) clip.
    pg = f"palettegen=max_colors={args.colors}:stats_mode=full"
    vf1 = f"{chain},{pg}" if chain else pg
    cmd1 = [ffmpeg, "-y", *seek, "-i", str(src), "-vf", vf1, str(palette)]
    print(f"[1/2 palette] {' '.join(cmd1)}")
    rc = subprocess.call(cmd1)
    if rc != 0:
        print(f"error: palettegen failed (exit {rc})", file=sys.stderr)
        return rc

    # Pass 2: render the gif using that palette.
    pu = build_paletteuse(args.dither, args.bayer_scale)
    lavfi = f"{chain}[x];[x][1:v]{pu}" if chain else f"[0:v][1:v]{pu}"
    target = raw if do_gifsicle else out
    cmd2 = [ffmpeg, "-y", *seek, "-i", str(src), "-i", str(palette),
            "-lavfi", lavfi, str(target)]
    print(f"[2/2 gif]     {' '.join(cmd2)}")
    rc = subprocess.call(cmd2)
    if rc != 0:
        print(f"error: paletteuse failed (exit {rc})", file=sys.stderr)
        return rc
    print(f"[ffmpeg gif]  {human_mb(target)}")

    # Optional gifsicle optimization / lossy compression.
    if do_gifsicle:
        gcmd = [gifsicle, "-O3"]
        if args.lossy is not None:
            gcmd.append(f"--lossy={args.lossy}")
        gcmd += [str(raw), "-o", str(out)]
        print(f"[gifsicle]    {' '.join(gcmd)}")
        rc = subprocess.call(gcmd)
        if rc != 0:
            print(f"error: gifsicle failed (exit {rc})", file=sys.stderr)
            return rc
        print(f"[optimized]   {human_mb(out)}")

    # Cleanup intermediates unless asked to keep them.
    if not args.keep_raw:
        for tmp in (palette, raw):
            try:
                if tmp.exists() and tmp != out:
                    tmp.unlink()
            except OSError as e:
                print(f"warning: could not remove {tmp}: {e}", file=sys.stderr)

    print(f"done: {out} ({human_mb(out)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
