#!/usr/bin/env python3
"""vid-preview-maker: build a preview clip with a banner overlay + audio fade.

Takes the first N seconds of a video, crossfades into a static banner image for
the tail, and lays the original audio underneath with an optional fade-out.
Produces final_output.mp4.

Ported from Z:\\omnitools\\vid-preview-maker\\vid-preview-maker.py into the
dazzlecmd 'media' kit. Self-contained: shells out to ffmpeg / ffprobe only.
Pure stdlib otherwise, single main(argv) entry point.

Note: intermediate files (preview_audio.wav, first_segment.mp4, padded_image.jpg,
updated_second_segment.mp4, video_output.mp4) are written to the current working
directory and reused if present (acts as a resume cache); they are not deleted.

Usage:
  dz vid-preview-maker input.mp4 banner.png
  dz vid-preview-maker input.mp4 banner.png --preview-duration 71 --banner-duration 10
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys


def get_media_info(video_path):
    """Extract frame rate and (optional) audio sample rate via ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=r_frame_rate", "-of", "json", video_path
    ], stdout=subprocess.PIPE)
    video_info = json.loads(result.stdout)
    frame_rate = eval(video_info['streams'][0]['r_frame_rate'])

    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
        "stream=sample_rate", "-of", "json", video_path
    ], stdout=subprocess.PIPE)
    audio_info = json.loads(result.stdout)
    sample_rate = None
    if 'streams' in audio_info and len(audio_info['streams']) > 0:
        sample_rate = int(audio_info['streams'][0]['sample_rate'])

    return frame_rate, sample_rate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vid-preview-maker",
        description="Create a video preview with an optional banner and audio fade-out.")
    parser.add_argument("input_file", help="Path to the input video file")
    parser.add_argument("replacement_img", help="Path to the replacement image for the banner")
    parser.add_argument("--preview-duration", type=int, default=71, help="Duration of the preview (default: 71 seconds)")
    parser.add_argument("--first-segment-duration", type=int, default=61, help="Duration of the first segment (default: 61 seconds)")
    parser.add_argument("--banner-duration", type=int, default=10, help="Duration of the banner (default: 10 seconds)")
    parser.add_argument("--fade-out-second-segment", default=False, action="store_true", help="Enable fade-out effect for the second segment")
    parser.add_argument("--fade-out-audio", default=True, action="store_true", help="Enable fade-out effect for the audio at the end")
    args = parser.parse_args(argv)

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("error: ffmpeg/ffprobe not found on PATH.", file=sys.stderr)
        return 2
    if not os.path.isfile(args.input_file):
        print(f"error: input not found: {args.input_file}", file=sys.stderr)
        return 2
    if not os.path.isfile(args.replacement_img):
        print(f"error: banner image not found: {args.replacement_img}", file=sys.stderr)
        return 2

    # Temporary files
    preview_audio = "preview_audio.wav"
    first_segment = "first_segment.mp4"
    padded_image = "padded_image.jpg"
    updated_second_segment = "updated_second_segment.mp4"
    video_output = "video_output.mp4"
    final_output = "final_output.mp4"

    # Extract the audio for the entire preview duration
    if not os.path.isfile(preview_audio):
        subprocess.run([
            "ffmpeg", "-i", args.input_file, "-ss", "00:00:00", "-t", str(args.preview_duration),
            "-vn", "-acodec", "pcm_s16le", preview_audio
        ])

    # Create the first segment video
    if not os.path.isfile(first_segment):
        subprocess.run([
            "ffmpeg", "-i", args.input_file, "-ss", "0", "-t", str(args.first_segment_duration),
            "-c:v", "libx264", "-an", first_segment
        ])

    # Prepare the static image (banner) with padding
    if not os.path.isfile(padded_image):
        subprocess.run([
            "ffmpeg", "-i", args.replacement_img,
            "-vf", "scale='if(gt(a,16/9),1920,-1)':'if(gt(a,16/9),-1,1080)',"
                   "pad=1920:1080:(1920-iw)/2:(1080-ih)/2:color=0x000000,format=yuv420p",
            padded_image
        ])

    # Create the updated second segment video with the banner
    if not os.path.isfile(updated_second_segment):
        frame_rate, _ = get_media_info(first_segment)
        fade_out_filter = f",fade=t=out:st={args.banner_duration-4}:d=4" if args.fade_out_second_segment else ""

        subprocess.run([
            "ffmpeg", "-loop", "1", "-i", padded_image,
            "-r", str(frame_rate), "-t", str(args.banner_duration),
            "-vf", f"format=yuva420p{fade_out_filter}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", updated_second_segment
        ])

    # Combine the first segment and updated second segment videos with crossfade
    if not os.path.isfile(video_output):
        subprocess.run([
            "ffmpeg", "-i", first_segment, "-i", updated_second_segment,
            "-filter_complex",
            f"[0:v]setpts=PTS-STARTPTS[v0];"
            f"[1:v]format=yuva420p,fade=t=in:st=0:d=1:alpha=1,setpts=PTS-STARTPTS+{args.first_segment_duration}/TB[v1];"
            f"[v0][v1]overlay,format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", video_output
        ])

    # Combine the video output with the original preview audio
    if not os.path.isfile(final_output):
        audio_fade_filter = f"afade=t=out:st={args.preview_duration-3}:d=3" if args.fade_out_audio else ""

        subprocess.run([
            "ffmpeg", "-i", video_output, "-i", preview_audio,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-af", audio_fade_filter, final_output
        ])

    print(f"Final video saved to {final_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
