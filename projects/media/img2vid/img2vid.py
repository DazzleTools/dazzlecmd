#!/usr/bin/env python3
"""img2vid: build a video from N images + audio with sequential transitions.

Holds each image for its segment and fades into the next, in order, with an
audio track underneath. The general image->video tool (for the simple 2-image
case, crossfade is a lighter shortcut).

Ported from Z:\\omnitools\\img2vid.py into the dazzlecmd 'media' kit.
Self-contained: audio duration probed via ffprobe (was mutagen); shells out to
ffmpeg only. Non-interactive: out-of-order transition times warn and proceed by
default (use --strict to abort instead of the original interactive prompt).
Pure stdlib otherwise, single main(argv) entry point.

Image arg syntax: PATH[:TIME[,fFADE]]  e.g.  pic.jpg:1m30s,f1s
  TIME  -- transition time (Nm Ns, N%, or seconds)
  fFADE -- per-segment fade duration (e.g. f1s)

Usage:
  dz img2vid -i a.jpg -i b.jpg:30s -i c.jpg:1m -a song.mp3 -o out.mp4
  dz img2vid -i a.jpg -i b.jpg:30s -a song.mp3 --strict
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from shutil import which


def get_audio_duration(audio_path: str) -> float:
    """Audio duration in seconds via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def prepare_image(image_path, output_path):
    if not os.path.isfile(output_path):
        subprocess.run([
            "ffmpeg", "-i", image_path, "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", output_path
        ])
    return output_path


def create_video_segment(image_path, duration, output_path):
    if not os.path.isfile(output_path):
        subprocess.run([
            "ffmpeg", "-loop", "1", "-i", image_path, "-c:v", "libx264", "-t", str(duration),
            "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", output_path
        ])
    return output_path


def combine_video_and_image(video_path, image_path, video_duration, image_duration, fade_duration, output_path):
    if not os.path.isfile(output_path):
        subprocess.run([
            "ffmpeg", "-i", video_path, "-loop", "1", "-i", image_path,
            "-filter_complex",
            f"[0:v]trim=duration={video_duration},setpts=PTS-STARTPTS[v0];"
            f"[1:v]trim=duration={image_duration},format=yuva420p,fade=t=in:st=0:d={fade_duration}:alpha=1,setpts=PTS-STARTPTS+{video_duration}/TB[v1];"
            f"[v0][v1]overlay,format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path
        ])


def combine_video_with_audio(video_path, audio_path, output_path):
    subprocess.run([
        "ffmpeg", "-i", video_path, "-i", audio_path, "-c:v", "copy", "-c:a", "aac",
        "-b:a", "320k", "-shortest", output_path
    ])


def parse_image_arg(image_arg, total_duration, fade_duration):
    parts = image_arg.split(":")
    image_path = parts[0]
    transition_time = total_duration
    segment_fade_duration = fade_duration

    if len(parts) > 1:
        time_fade = parts[1].split(",")
        time = time_fade[0]
        if time.endswith("%"):
            transition_time = float(time[:-1]) / 100 * total_duration
        else:
            # Extract minutes and seconds from the time code
            match = re.match(r"(\d+m)?(\d+s)?", time)
            if match:
                minutes = int(match.group(1)[:-1]) if match.group(1) else 0
                seconds = int(match.group(2)[:-1]) if match.group(2) else 0
                transition_time = minutes * 60 + seconds
            else:
                time = float(time)
                if time > 1:
                    transition_time = time
                else:
                    transition_time = time * total_duration

        if len(time_fade) > 1 and time_fade[1].startswith("f"):
            fade_part = time_fade[1][1:]
            if fade_part:
                segment_fade_duration = float(fade_part[:-1]) if fade_part[-1] == "s" else float(fade_part)
            else:
                segment_fade_duration = fade_duration

    return image_path, transition_time, segment_fade_duration


def validate_image_files(image_args):
    for image_arg in image_args:
        image_path = image_arg.split(":")[0]
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")


def sanitize_transition_times(image_args, total_duration, fade_duration, strict=False):
    """Return transition times. Out-of-order times warn (or abort if strict).

    Replaces the original interactive input() prompt: under dispatch we default
    to proceeding with a warning; --strict restores fail-on-out-of-order.
    Returns None to signal the caller should abort.
    """
    transition_times = [0]
    for i in range(1, len(image_args)):
        _, transition_time, _ = parse_image_arg(image_args[i], total_duration, fade_duration)
        transition_times.append(transition_time)

    if transition_times != sorted(transition_times):
        print("Warning: the transition times are not in chronological order.",
              file=sys.stderr)
        if strict:
            print("error: --strict set; aborting. Reorder the -i images by time.",
                  file=sys.stderr)
            return None
        print("Proceeding with the specified order (pass --strict to abort instead).",
              file=sys.stderr)

    return transition_times


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="img2vid",
        description="Create a video from multiple images and an audio file with transitions.")
    parser.add_argument("-i", "--image", action="append", help="Image file with optional transition time and fade duration (e.g., image.jpg:10s,f5s)")
    parser.add_argument("-a", "--audio", required=True, help="Path to the audio file (FLAC or MP3)")
    parser.add_argument("-fd", "--fade-duration", type=float, default=1, help="Duration of the fade transition in seconds (default: 1)")
    parser.add_argument("-td", "--total-duration", type=float, help="Total duration of the video in seconds (default: audio duration)")
    parser.add_argument("-o", "--output", default="output.mp4", help="Path to the output video file (default: output.mp4)")
    parser.add_argument("-d", "--debug", action="store_true", help="Keep intermediate files for debugging")
    parser.add_argument("--strict", action="store_true", help="Abort if transition times are out of chronological order (default: warn and proceed)")
    args = parser.parse_args(argv)

    if not which("ffmpeg") or not which("ffprobe"):
        print("error: ffmpeg/ffprobe not found on PATH.", file=sys.stderr)
        return 2
    if not args.image or len(args.image) < 2:
        print("error: img2vid needs at least two -i/--image arguments.", file=sys.stderr)
        return 2
    if not os.path.isfile(args.audio):
        print(f"error: audio file not found: {args.audio}", file=sys.stderr)
        return 2
    try:
        validate_image_files(args.image)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    audio_duration = get_audio_duration(args.audio)
    total_duration = args.total_duration or audio_duration
    fade_duration = args.fade_duration

    transition_times = sanitize_transition_times(args.image, total_duration, fade_duration, args.strict)
    if transition_times is None:
        return 1

    images = [image_arg.split(":")[0] for image_arg in args.image]
    fade_durations = [parse_image_arg(image_arg, total_duration, fade_duration)[2] for image_arg in args.image]

    # Temporary files
    prepared_images = [f"prepared_image_{i}.png" for i in range(len(images))]
    video_segments = [f"video_segment_{i}.mp4" for i in range(len(images))]

    # Prepare the images
    for i in range(len(images)):
        prepared_images[i] = prepare_image(images[i], prepared_images[i])

    # Create video segments and combine them sequentially
    video_output = video_segments[0]
    for i in range(len(images) - 1):
        segment_duration = transition_times[i + 1]  # - transition_times[i]
        if i == 0:
            video_output = create_video_segment(prepared_images[i], segment_duration, video_segments[i])
        next_segment_duration = min(transition_times[i + 2] - transition_times[i + 1], audio_duration - transition_times[i + 1]) if i < len(images) - 2 else audio_duration - transition_times[i + 1]
        video_output_temp = f"video_output_{i}.mp4"
        combine_video_and_image(video_output, prepared_images[i + 1], segment_duration, next_segment_duration, fade_durations[i + 1], video_output_temp)
        video_output = video_output_temp

    # Combine the video with the audio
    combine_video_with_audio(video_output, args.audio, args.output)

    # Clean up temporary files if not in debug mode
    if not args.debug:
        for file in prepared_images + video_segments + [f"video_output_{i}.mp4" for i in range(len(images) - 2)]:
            if os.path.isfile(file):
                os.remove(file)

    print(f"Final video saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
