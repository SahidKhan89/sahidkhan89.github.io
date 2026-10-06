#!/usr/bin/env python3
"""
reel_audio.py — shared background-track picker + encoder for every reel
generator (VIX gauge, sector heatmap, $1,000 invested, head-to-head).

Any .mp3 dropped into assets/audio/ joins the pool automatically — no list to
maintain. Only tracks at least as long as the reel are eligible (so the video
is never cut short), and the pick is spread out rather than random: each UTC
day maps to a track via a golden-ratio sequence, which keeps consecutive days
on different tracks and spaces repeats as far apart as the pool allows, even
for weekly reels (VIX every Monday) where a plain day % n rotation could get
stuck cycling a handful of tracks. No history file needed. Each reel type gets
its own offset, so two reels on the same day don't share a track.
"""

import hashlib
import math
import subprocess
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

AUDIO_DIR = Path(__file__).parent.parent / "assets" / "audio"

SLOTS = {"vix": 0, "heatmap": 1, "investment": 2, "h2h": 3, "guess": 4, "race": 5}
_PHI = (math.sqrt(5) - 1) / 2


@lru_cache(maxsize=None)
def track_seconds(path: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            check=True, capture_output=True, text=True).stdout
        return float(out.strip())
    except Exception:
        return 0.0


def pick_track(min_seconds: float, slot: str, day: date | None = None) -> Path:
    tracks = sorted(AUDIO_DIR.glob("*.mp3"))
    if not tracks:
        raise FileNotFoundError(f"no .mp3 files in {AUDIO_DIR}")
    eligible = [t for t in tracks if track_seconds(t) >= min_seconds] or tracks
    # Stable shuffle (by filename hash), so similar files — same artist, same
    # naming prefix — aren't adjacent in the rotation.
    eligible.sort(key=lambda p: hashlib.sha1(p.name.encode()).hexdigest())

    day = day or datetime.now(timezone.utc).date()
    x = (day.toordinal() * _PHI + SLOTS.get(slot, 0) / len(SLOTS)) % 1.0
    return eligible[int(x * len(eligible))]


def encode_video(frame_dir: Path, out_path: Path, fps: int, n_frames: int, slot: str) -> str:
    """Encode frame_%05d.png into an mp4 with a background track trimmed to
    the video's length (1s fade-out). Returns the track's name."""
    duration = n_frames / fps
    track = pick_track(duration, slot)
    fade_start = max(0.0, duration - 1.0)
    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%05d.png"),
        # Looping is only a safety net (if every track is shorter than the
        # reel) — never use -shortest, which cuts the video to the audio.
        "-stream_loop", "-1", "-i", str(track),
        "-t", f"{duration:.3f}",
        "-af", f"afade=t=out:st={fade_start:.3f}:d=1.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return track.stem


if __name__ == "__main__":
    # Preview the next fortnight's picks for each reel type.
    from datetime import timedelta
    lengths = {"vix": 7.6, "heatmap": 15, "investment": 23, "h2h": 23, "guess": 22, "race": 25}
    today = datetime.now(timezone.utc).date()
    for i in range(14):
        d = today + timedelta(days=i)
        print(d.strftime("%a %d %b"), " | ".join(
            f"{s}: {pick_track(lengths[s], s, d).stem[:28]}" for s in SLOTS))
