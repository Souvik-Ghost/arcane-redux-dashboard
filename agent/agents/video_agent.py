"""
agents/video_agent.py — Long-form video producer.

Pipeline (reconstructed from soul.md blueprint):
  1/5  TTS       → Kokoro ONNX v1.0 (af_heart voice) via utils.tts.synthesise()
  2/5  Avatar    → D-ID / HeyGen → waveform FFmpeg fallback (~90s render)
  3/5  Scenes    → Pre-rendered gradient tile + per-scene text overlay (fast loop)
  4/5  Concat    → FFmpeg concat demuxer → single scene timeline
  5/5  Composite → Avatar PIP (bottom-right) over scene timeline → final 1080p MP4

Speed note: gradient tile is rendered ONCE (12s, ~90s), then looped for each scene.
  This cuts Step 3 from ~2.5 hours (original geq-per-clip) to ~10 minutes total.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import config
from utils.logger import logger

if TYPE_CHECKING:
    from agents.script_agent import VideoScript


# ── FFmpeg helper ─────────────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list[str], label: str = "") -> None:
    """Run FFmpeg subprocess, log progress, raise RuntimeError on failure."""
    logger.debug(f"FFmpeg [{label}]: {' '.join(cmd[:5])}...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,          # 1hr hard ceiling per step
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg [{label}] timed out after 3600s")

    if result.returncode != 0:
        # Fontconfig errors on Windows are non-fatal (exit 0) — only raise for real errors
        stderr = result.stderr or ""
        raise RuntimeError(
            f"FFmpeg [{label}] failed (exit {result.returncode}):\n{stderr[-3000:]}"
        )


# ── Text sanitizer ────────────────────────────────────────────────────────────

def _safe_text(text: str, max_len: int = 80) -> str:
    """
    Strip characters that break FFmpeg drawtext filter and truncate.
    At fontsize=38 on a 1920px frame, 80 chars fits without wrapping.
    """
    # Remove FFmpeg filter special chars
    text = re.sub(r"[:\\'\[\]{}@#<>|=;,]", " ", text)
    # Collapse whitespace / newlines
    text = " ".join(text.split())
    # Truncate
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + " ..."
    return text


# ── Gradient tile pre-renderer ────────────────────────────────────────────────

def _render_gradient_base(output_path: Path, tile_secs: int = 12) -> Path:
    """
    Pre-render a 12-second animated cosmic gradient tile at 1920x1080/24fps.
    This tile is looped for every scene clip — the key speedup over re-rendering
    the geq filter per clip (~15 min/clip → <30s/clip).
    """
    logger.info(f"Pre-rendering {tile_secs}s cosmic gradient tile...")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=black:size=1920x1080:rate=24:duration={tile_secs}",
        "-filter_complex",
        (
            "geq="
            "r='128+127*sin(2*PI*t/4+X/1920)':"
            "g='64+63*sin(2*PI*t/6+Y/1080)':"
            "b='200+55*sin(2*PI*t/3+X/960+Y/540)'"
        ),
        "-vcodec", "libx264", "-preset", "fast", "-crf", "22",
        str(output_path),
    ]
    _run_ffmpeg(cmd, "gradient_tile")
    logger.success(f"Gradient tile ready: {output_path.name}")
    return output_path


# ── Scene clip builder ────────────────────────────────────────────────────────

def _build_clip(
    gradient_base: Path,
    text: str,
    duration_secs: int,
    output_path: Path,
    label: str = "clip",
    font_size: int = 38,
    y_expr: str = "(h-text_h)/2",
) -> Path:
    """
    Loop gradient_base to duration_secs and overlay text.
    No audio output (-an) — audio comes from the avatar track.
    """
    safe = _safe_text(text)
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(gradient_base),
        "-vf",
        (
            f"drawtext=text='{safe}'"
            f":fontsize={font_size}"
            f":fontcolor=white@0.95"
            f":x=100:y={y_expr}"
            f":box=1:boxcolor=black@0.45:boxborderw=18"
        ),
        "-t", str(max(duration_secs, 3)),   # minimum 3s per clip
        "-vcodec", "libx264", "-preset", "fast", "-crf", "22",
        "-an",
        str(output_path),
    ]
    _run_ffmpeg(cmd, label)
    return output_path


def _build_title_card(
    gradient_base: Path,
    title: str,
    output_path: Path,
    duration: int = 5,
) -> Path:
    """Intro title card — large centered text."""
    safe_title = _safe_text(title, max_len=70)
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(gradient_base),
        "-vf",
        (
            f"drawtext=text='{safe_title}'"
            f":fontsize=52:fontcolor=white"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":box=1:boxcolor=black@0.6:boxborderw=30"
        ),
        "-t", str(duration),
        "-vcodec", "libx264", "-preset", "fast", "-crf", "22",
        "-an",
        str(output_path),
    ]
    _run_ffmpeg(cmd, "title_card")
    return output_path


# ── Waveform avatar fallback ──────────────────────────────────────────────────

def _create_waveform_avatar(audio_path: Path, output_path: Path) -> Path:
    """
    Generate a waveform visualizer avatar video from TTS audio.

    Dark background + animated purple/violet waveform + channel name watermark.
    Renders in ~90 seconds regardless of audio length (no per-frame math).
    This is the permanent fallback when D-ID and HeyGen are unavailable.
    """
    logger.info("Step 2/5: Waveform avatar fallback (FFmpeg)...")
    channel_label = _safe_text(config.AVATAR_NAME, max_len=40)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-filter_complex",
        (
            "[0:a]aformat=channel_layouts=mono,"
            "showwaves=s=1920x400:mode=cline:colors=7c3aed|a855f7:scale=sqrt[wave];"
            "color=c=0a0a1a:size=1920x1080[bg];"
            "[bg][wave]overlay=x=0:y=340,"
            f"drawtext=text='{channel_label}':fontsize=52"
            f":fontcolor=white@0.5:x=(w-text_w)/2:y=h-90[v]"
        ),
        "-map", "[v]",
        "-map", "0:a",
        "-vcodec", "libx264", "-preset", "fast", "-crf", "22",
        "-acodec", "aac",
        "-r", "24",
        str(output_path),
    ]
    _run_ffmpeg(cmd, "waveform_avatar")
    logger.success(f"Waveform avatar saved: {output_path.name}")
    return output_path


# ── Main pipeline ─────────────────────────────────────────────────────────────

def produce_video(script: "VideoScript", job_id: str) -> dict:
    """
    Produce a full 1080p long-form video from a VideoScript object.

    Called by the dashboard's _write_produce_script() runner.
    Prints progress lines that the dashboard WebSocket picks up.

    Args:
        script: VideoScript dataclass from agents.script_agent.generate_script()
        job_id: Short UUID hex (8 chars) used as filename prefix.

    Returns:
        {"final_video": Path} — Path to the finished MP4.
    """
    vdir = config.VIDEOS_DIR
    adir = config.AUDIO_DIR
    vdir.mkdir(parents=True, exist_ok=True)
    adir.mkdir(parents=True, exist_ok=True)

    narration = script.full_narration()
    n_scenes  = len(script.scenes)

    # ── Step 1/5: TTS ─────────────────────────────────────────────────────────
    print(f"\nStep 1/5: TTS ({len(narration)} chars → Kokoro {config.AVATAR_VOICE})...")
    from utils.tts import synthesise
    audio_path = adir / f"{job_id}.mp3"
    synthesise(text=narration, output_path=audio_path, voice=config.AVATAR_VOICE)
    print(f"  Kokoro TTS saved: {audio_path.name} ({audio_path.stat().st_size // 1024}KB)")

    # ── Step 2/5: Avatar ──────────────────────────────────────────────────────
    print("\nStep 2/5: Generating avatar video...")
    avatar_path = vdir / f"{job_id}_avatar.mp4"
    try:
        from agents.avatar_agent import generate_avatar_video
        generate_avatar_video(audio_path=audio_path, output_path=avatar_path,
                              script_text=narration[:500])
        print(f"  Avatar API success: {avatar_path.name}")
    except Exception as e:
        logger.warning(f"Avatar API failed ({type(e).__name__}), using waveform fallback")
        _create_waveform_avatar(audio_path, avatar_path)
        print(f"  Waveform avatar saved: {avatar_path.name}")

    # ── Step 3/5: Scene clips ─────────────────────────────────────────────────
    total_clips = n_scenes + 3   # title + hook + N scenes + cta
    print(f"\nStep 3/5: Building {total_clips} scene clips...")

    # Pre-render gradient tile ONCE (big speedup vs per-clip geq rendering)
    grad = vdir / f"{job_id}_gradient.mp4"
    _render_gradient_base(grad, tile_secs=12)

    clips: list[Path] = []

    # 0: Intro title card (5s)
    p = vdir / f"{job_id}_s000_title.mp4"
    _build_title_card(grad, script.title, p, duration=5)
    clips.append(p)
    print(f"  [0/{total_clips}] Intro title card ✓")

    # 1: Hook clip (45s)
    p = vdir / f"{job_id}_s001_hook.mp4"
    _build_clip(grad, script.hook, duration_secs=45, output_path=p, label="hook",
                font_size=38, y_expr="h/3")
    clips.append(p)
    print(f"  [1/{total_clips}] Hook clip ✓")

    # 2..N+1: Scene clips
    for i, scene in enumerate(script.scenes, start=1):
        p = vdir / f"{job_id}_s{i+1:03d}_scene.mp4"
        _build_clip(
            grad, scene.narration,
            duration_secs=scene.duration_secs,
            output_path=p,
            label=f"scene_{i}",
        )
        clips.append(p)
        print(f"  [{i+1}/{total_clips}] Scene {i}/{n_scenes} ✓")

    # N+2: CTA clip (30s)
    p = vdir / f"{job_id}_s999_cta.mp4"
    _build_clip(grad, script.cta, duration_secs=30, output_path=p, label="cta",
                font_size=42, y_expr="(h-text_h)/2")
    clips.append(p)
    print(f"  [{total_clips}/{total_clips}] CTA clip ✓")

    # ── Step 4/5: Concat ─────────────────────────────────────────────────────
    print("\nStep 4/5: Concatenating clips into timeline...")
    concat_file = vdir / f"{job_id}_concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{c.as_posix()}'" for c in clips),
        encoding="utf-8",
    )
    merged = vdir / f"{job_id}_merged.mp4"
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(merged),
    ], "concat")
    concat_file.unlink(missing_ok=True)
    merged_mb = merged.stat().st_size / 1_048_576
    print(f"  Merged timeline: {merged.name} ({merged_mb:.1f}MB)")

    # ── Step 5/5: Composite (avatar PIP, bottom-right) ────────────────────────
    print("\nStep 5/5: Compositing avatar overlay...")
    final = vdir / f"{job_id}_final.mp4"
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(merged),           # 0: scene timeline (video only)
        "-i", str(avatar_path),      # 1: avatar (video + TTS audio)
        "-filter_complex",
        (
            "[1:v]scale=320:180[av];"
            "[0:v][av]overlay=W-w-20:H-h-20[v]"
        ),
        "-map", "[v]",
        "-map", "1:a",               # use avatar's TTS audio track
        "-vcodec", "libx264", "-preset", "fast", "-crf", "20",
        "-acodec", "aac",
        "-shortest",                  # trim to shorter of the two durations
        str(final),
    ], "composite")

    size_mb = final.stat().st_size / 1_048_576
    print(f"  Final video: {final.name} ({size_mb:.1f}MB)")

    # Cleanup intermediates (keep audio + final)
    for f in [grad, merged] + clips:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    logger.success(f"produce_video complete: {final.name} ({size_mb:.1f}MB)")
    return {"final_video": final}
