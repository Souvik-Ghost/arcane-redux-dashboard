"""
agents/shorts_agent.py — YouTube Shorts production pipeline.

Each Short is:
  - 30–59 seconds (YouTube Shorts limit)
  - Vertical 1080×1920 (9:16)
  - One killer hook + one key insight + CTA
  - Auto-extracted from long-form script OR standalone topic
  - TTS narration + avatar overlay + animated text
  - Uploaded immediately (public) with #Shorts tag

Sources (priority order):
  1. Latest published long-form concept in DB (extract best moment)
  2. Latest outlier/trend from research
  3. Channel niche evergreen hook
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import config
from utils.logger import logger
from utils.tts import synthesise
from database import supabase_client as db


# ── Short script generator ────────────────────────────────────────────────────

def generate_short_script(topic: str, context: dict[str, Any]) -> dict:
    """
    Generate a 45-second short script via best available LLM (LM Studio first).
    Returns: {title, hook, key_insight, cta, narration, tags}
    """
    from agents.script_agent import _call_llm
    import json, re

    system = f"""You are a YouTube Shorts scriptwriter for "{config.AVATAR_NAME}" on Arcane Redux.
Channel niche: {config.CHANNEL_NICHE}
Tone: {config.CHANNEL_TONE}

Rules for Shorts scripts:
- Total narration: 120-160 words (fits 45-55 seconds at natural pace)
- Hook: first 3 seconds must be a shocking stat or provocative question
- One main insight only -- no padding
- End with: "Follow for more" or "Subscribe for the full breakdown"
- No fluff, no generic intros
- Return ONLY valid JSON, no markdown"""

    prompt = f"""Write a YouTube Short script for this topic: "{topic}"

Context: {str(context)[:500]}

Return ONLY this JSON (no markdown fences):
{{
  "title": "Short punchy title under 60 chars with #Shorts",
  "hook": "First 3-second spoken hook (one sentence, shocking)",
  "key_insight": "The single most powerful insight (2-3 sentences)",
  "cta": "Call to action (one sentence)",
  "narration": "Full narration combining hook + insight + cta (120-160 words)",
  "text_overlay": "4-6 word visual text shown on screen",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "#Shorts"]
}}"""

    raw = _call_llm(system, prompt, max_tokens=800)
    # Strip markdown fences if present
    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    json_str = json_match.group(1) if json_match else raw.strip()
    data = json.loads(json_str)
    if "#Shorts" not in data.get("tags", []):
        data["tags"].append("#Shorts")
    return data


# ── Vertical video builder ────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"] + cmd,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr}")


def build_short_video(
    audio_path: Path,
    text_overlay: str,
    hook_text: str,
    output_path: Path,
    duration: float,
    avatar_path: Path | None = None,
) -> Path:
    """
    Build a 1080x1920 vertical Short video:
      - Dark animated gradient background
      - Large hook text at top
      - Key insight text in center
      - TTS narration audio
    """
    W, H = 1080, 1920

    # Write text files (relative paths — no Windows drive letter issues with FFmpeg)
    hook_file = f"_short_hook_{uuid.uuid4().hex[:8]}.txt"
    body_file = f"_short_body_{uuid.uuid4().hex[:8]}.txt"

    with open(hook_file, "w", encoding="utf-8") as f:
        f.write(hook_text[:60])
    with open(body_file, "w", encoding="utf-8") as f:
        f.write(text_overlay[:80])

    try:
        # Build base background + text
        bg_path = output_path.parent / f"_bg_{output_path.stem}.mp4"
        _run_ffmpeg([
            "-f", "lavfi",
            "-i", f"color=c=0x050510:size={W}x{H}:rate=30",
            "-t", str(duration),
            "-vf", (
                # Animated subtle gradient sweep
                f"geq=r='clip(80+40*sin(2*PI*T/8+X/200),0,255)':g='clip(20+15*sin(2*PI*T/6+Y/300),0,255)':b='clip(120+60*sin(2*PI*T/10+X/400),0,255)',"
                # Hook text — large, top area
                f"drawtext=textfile='{hook_file}':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=180:"
                f"box=1:boxcolor=black@0.55:boxborderw=18:line_spacing=12,"
                # Body text — center
                f"drawtext=textfile='{body_file}':fontsize=54:fontcolor=0xFFDD00:x=(w-text_w)/2:y=(h-text_h)/2:"
                f"box=1:boxcolor=black@0.5:boxborderw=14:line_spacing=10,"
                # Channel watermark
                f"drawtext=text='ARCANE REDUX':fontsize=32:fontcolor=white@0.5:x=(w-text_w)/2:y=h-100"
            ),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            str(bg_path),
        ])

        # Add audio
        _run_ffmpeg([
            "-i", str(bg_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_path),
        ])

        if bg_path.exists():
            bg_path.unlink()

    finally:
        for f in [hook_file, body_file]:
            try:
                Path(f).unlink(missing_ok=True)
            except Exception:
                pass

    return output_path


# ── Topic selector ────────────────────────────────────────────────────────────

def _pick_short_topic() -> tuple[str, dict]:
    """Pick the best topic for the next Short."""
    # Priority 1: extract from latest published long-form concept
    try:
        client = db.get_client()
        row = (client.table("video_concepts")
               .select("title,hook,script_outline")
               .eq("status", "published")
               .order("id", desc=True)
               .limit(1)
               .execute().data)
        if row:
            r = row[0]
            lines = [l.strip() for l in r["script_outline"].split("\n") if len(l.strip()) > 20]
            if lines:
                import random
                topic = random.choice(lines[:5])
                return topic, {"source_video": r["title"], "hook": r["hook"]}
    except Exception:
        pass

    # Priority 2: latest outlier from research
    try:
        outliers = db.get_pending_outliers()
        if outliers:
            o = outliers[0]
            return f"Why {o['title'].split('|')[0].strip()} went viral", {"outlier_data": o}
    except Exception:
        pass

    # Priority 3: evergreen niche topic
    import random
    evergreen = [
        f"The fastest way to build {config.CHANNEL_NICHE} systems",
        f"One mistake everyone makes in {config.CHANNEL_NICHE}",
        f"Why 90% of {config.CHANNEL_NICHE} projects fail",
        f"The tool changing {config.CHANNEL_NICHE} right now",
        f"What nobody tells you about {config.CHANNEL_NICHE}",
    ]
    return random.choice(evergreen), {"niche": config.CHANNEL_NICHE}


# ── Main pipeline ─────────────────────────────────────────────────────────────

def produce_and_upload_short(topic: str | None = None) -> str:
    """
    Full Short pipeline: topic → script → TTS → video → YouTube upload.
    Returns YouTube video ID.
    """
    import os
    # Portable: use the agent directory (this file's grandparent)
    os.chdir(Path(__file__).parent.parent)

    job_id = str(uuid.uuid4())[:8]
    logger.info(f"[SHORT {job_id}] Starting Short production")

    # Pick topic
    if not topic:
        topic, context = _pick_short_topic()
    else:
        context = {"niche": config.CHANNEL_NICHE}

    logger.info(f"[SHORT {job_id}] Topic: {topic}")

    # Generate script
    script = generate_short_script(topic, context)
    logger.info(f"[SHORT {job_id}] Script: {script['title']}")

    # TTS
    audio_path = config.AUDIO_DIR / f"short_{job_id}.mp3"
    synthesise(script["narration"], audio_path, voice=config.AVATAR_VOICE)

    # Get audio duration
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True,
    )
    duration = min(float(result.stdout.strip() or "45"), 59.0)

    # Build vertical video (wrapped to catch FFmpeg errors gracefully)
    video_path = config.VIDEOS_DIR / f"short_{job_id}.mp4"
    try:
        build_short_video(
            audio_path=audio_path,
            text_overlay=script["text_overlay"],
            hook_text=script["hook"][:55],
            output_path=video_path,
            duration=duration,
        )
    except Exception as e:
        logger.error(f"[SHORT {job_id}] Video build failed: {e}")
        raise

    logger.info(f"[SHORT {job_id}] Video built: {video_path} ({video_path.stat().st_size//1024}KB)")

    # Upload to YouTube
    from utils.youtube_api import get_youtube_client
    from googleapiclient.http import MediaFileUpload

    yt = get_youtube_client()
    body = {
        "snippet": {
            "title": script["title"][:100],
            "description": (
                f"{script['hook']}\n\n"
                f"{script['key_insight']}\n\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"Arcane Redux — Applied AI Research & Automation\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"#{' #'.join(t.lstrip('#') for t in script['tags'])}"
            ),
            "tags": script["tags"] + ["Shorts", "YouTubeShorts"],
            "categoryId": "28",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = req.next_chunk()

    video_id = response["id"]
    yt_url = f"https://youtube.com/shorts/{video_id}"
    logger.success(f"[SHORT {job_id}] Published: {yt_url}")

    try:
        db.log_event("shorts", "short_published", {
            "job_id": job_id, "video_id": video_id,
            "title": script["title"], "topic": topic,
        })
    except Exception:
        pass

    return video_id
