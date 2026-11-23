"""Brand a video clip for an Instagram Reel: 9:16 frame + the page's overlay (logo, tag, headline, footer).

Uses the ffmpeg binary bundled with the imageio-ffmpeg package, so nothing extra needs installing.
"""
import re
import subprocess

from . import card

MAX_SECONDS = 15 * 60  # Instagram's Reel limit


def _ffmpeg():
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def has_audio(path):
    """ffmpeg prints the streams it finds; look for an audio one."""
    out = subprocess.run([_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stderr
    return bool(re.search(r"Stream #\S+.*Audio:", out))


def brand(src, overlay_png, out_path, preview=False):
    """Fit src into 1080x1920 (blurred fill behind landscape/square clips) and lay the overlay on top.

    preview=True makes a smaller 720p file for Telegram; the full-quality one is made when posting.
    """
    w, h = (720, 1280) if preview else (1080, 1920)
    filters = (
        # Background: the clip itself, zoomed to fill and blurred - no black bars.
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        "boxblur=luma_radius=30:luma_power=2,eq=brightness=-0.12[bg];"
        # Foreground: the whole clip, fitted inside the frame.
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[1:v]scale={w}:{h}[ov];"
        "[base][ov]overlay=0:0:shortest=1,fps=30,format=yuv420p[v]"  # stop when the clip ends
    )
    cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-loop", "1", "-i", overlay_png,
           "-filter_complex", filters, "-map", "[v]"]
    if has_audio(src):
        cmd += ["-map", "0:a:0"]
    else:  # Reels expect an audio track - add silence
        at = cmd.index("-filter_complex")
        cmd[at:at] = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        cmd += ["-map", "2:a:0"]
    cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
    cmd += ["-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast",
            "-crf", "28" if preview else "21", "-maxrate", "3M" if preview else "10M",
            "-bufsize", "6M" if preview else "20M", "-movflags", "+faststart",
            "-t", str(MAX_SECONDS), "-shortest", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError("video editing failed: " + (result.stderr.strip().splitlines() or ["?"])[-1])
    return out_path


def render(story, src, out_path, overlay_path, preview=False):
    card.render_overlay(story["headline"], story["tag"], story["source_name"], story["location"], overlay_path,
                        video_credit=story.get("video_credit"), highlight=story.get("highlight"),
                        sensitive=story.get("sensitive", False))
    return brand(src, overlay_path, out_path, preview=preview)
