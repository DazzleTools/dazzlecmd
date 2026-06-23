# Media Kit

`ffmpeg`-based media tooling -- video, audio, image, and gif tasks -- collected into one kit.

The `media` kit is **opt-in** (it is not active by default). Enable it with:

```bash
dz kit enable media
```

## Tools

| Tool | Description | Platform |
|------|-------------|----------|
| `vid2gif` | High-quality video-to-GIF via an `ffmpeg` two-pass palette + `gifsicle` optimization | Cross-platform |
| `vidresize` | Aspect-ratio-preserving video resize, with metadata strip and optional audio injection | Cross-platform |
| `img2vid` | Build a video from N images plus audio with sequential fade transitions (the general image-to-video tool) | Cross-platform |
| `crossfade` | Build a video from exactly two images with a crossfade and an audio track (the 2-image shortcut) | Cross-platform |
| `song-to-vid` | Make a video per audio file from its embedded album art | Cross-platform |
| `vid-preview-maker` | Build a preview clip with a banner overlay and an audio fade-out | Cross-platform |
| `mp3me` | Batch FLAC -> MP3 / V0 / V2 / Ogg / AAC / ALAC transcoder with tag copy | Cross-platform |

## Dependencies

All tools shell out to **`ffmpeg`** / **`ffprobe`** (must be on PATH). `vid2gif` also uses **`gifsicle`**; `mp3me` uses **`flac`** / **`lame`** / **`metaflac`**. The Python side is stdlib-only.

## Provenance

Each tool records its origin via a `provenance:<source>` tag in its manifest: `vid2gif` is native (new in-repo), `vidresize` was ported from a ComfyUI experiment, and the rest were migrated from a personal media-script collection. The kit is flat by design and can graduate to a nested aggregator (and an eventual `DazzleTools/media-kit` extraction) later without renaming tools.
