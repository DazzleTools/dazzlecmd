#!/usr/bin/env python3
"""crossfade: quick 2-image -> video with a crossfade and an audio track.

Builds a video from exactly two images: holds the first image, crossfades into
the second, and lays an audio track underneath. The simpler 2-image shortcut;
for N images with sequential transitions use img2vid. (Formerly named vid2img,
which read as video->image -- this tool is image->video.)

Ported from Z:\\omnitools\\vid-preview-maker\\vid2img.py into the dazzlecmd
'media' kit. Self-contained: audio duration probed via ffprobe (was mutagen);
shells out to ffmpeg only. Pure stdlib otherwise, single main(argv) entry point.

Image arg syntax: PATH[:TIME[,fFADE]]  e.g.  pic.jpg:10s,f5s
  TIME  -- transition time (Ns seconds, N% of total, or a fraction/seconds)
  fFADE -- per-segment fade duration (e.g. f5s)

Usage:
  dz crossfade -i a.jpg -i b.jpg:50% -a song.mp3 -o out.mp4
"""

from __future__ import annotations

import argparse
import os
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


def create_video_segment(image_path, duration, output_path):
    if not os.path.isfile(output_path):
        subprocess.run([
            "ffmpeg", "-loop", "1", "-i", image_path, "-c:v", "libx264", "-t", str(duration),
            "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", output_path
        ])
    return output_path


def combine_videos_with_crossfade(video1_path, video2_path, fade_duration, output_path):
    if not os.path.isfile(output_path):
        subprocess.run([
            "ffmpeg", "-i", video1_path, "-i", video2_path,
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset=4[v]",
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
        elif time.endswith("s"):
            transition_time = float(time[:-1])
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crossfade",
        description="Create a video from two images and an audio file with a crossfade.")
    parser.add_argument("-i", "--image", action="append", help="Image file with optional transition time and fade duration (e.g., image.jpg:10s,f5s)")
    parser.add_argument("-a", "--audio", required=True, help="Path to the audio file (FLAC or MP3)")
    parser.add_argument("-fd", "--fade-duration", type=float, default=2, help="Duration of the fade transition in seconds (default: 2)")
    parser.add_argument("-td", "--total-duration", type=float, help="Total duration of the video in seconds (default: audio duration)")
    parser.add_argument("-o", "--output", default="output.mp4", help="Path to the output video file (default: output.mp4)")
    parser.add_argument("-d", "--debug", action="store_true", help="Keep intermediate files for debugging")
    args = parser.parse_args(argv)

    if not which("ffmpeg") or not which("ffprobe"):
        print("error: ffmpeg/ffprobe not found on PATH.", file=sys.stderr)
        return 2
    if not args.image or len(args.image) < 2:
        print("error: crossfade needs exactly two -i/--image arguments.", file=sys.stderr)
        return 2
    if not os.path.isfile(args.audio):
        print(f"error: audio file not found: {args.audio}", file=sys.stderr)
        return 2

    audio_duration = get_audio_duration(args.audio)
    total_duration = args.total_duration or audio_duration
    fade_duration = args.fade_duration

    images = []
    transition_times = []
    fade_durations = []

    for i in range(len(args.image)):
        image_arg = args.image[i]
        if i < len(args.image) - 1:
            next_image_arg = args.image[i + 1]
            _, next_transition_time, _ = parse_image_arg(next_image_arg, total_duration, fade_duration)
        else:
            next_transition_time = total_duration

        image_path, _, segment_fade_duration = parse_image_arg(image_arg, total_duration, fade_duration)
        duration = next_transition_time - transition_times[-1] if transition_times else next_transition_time

        images.append(image_path)
        transition_times.append(next_transition_time)
        fade_durations.append(segment_fade_duration)

    # Temporary files
    video_segment1 = "video_segment1.mp4"
    video_segment2 = "video_segment2.mp4"
    video_output = "video_output.mp4"

    # Create video segments for each image
    video_segment1 = create_video_segment(images[0], transition_times[0], video_segment1)
    video_segment2 = create_video_segment(images[1], total_duration - transition_times[0], video_segment2)

    # Combine the video segments with a crossfade transition
    combine_videos_with_crossfade(video_segment1, video_segment2, fade_durations[1], video_output)

    # Combine the video with the audio
    combine_video_with_audio(video_output, args.audio, args.output)

    # Clean up temporary files if not in debug mode
    if not args.debug:
        for f in (video_segment1, video_segment2, video_output):
            if os.path.isfile(f):
                os.remove(f)

    print(f"Final video saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
