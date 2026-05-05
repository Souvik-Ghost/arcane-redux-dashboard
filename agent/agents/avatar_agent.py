"""
agents/avatar_agent.py — Virtual AI Avatar Character Generator.

Creates a talking avatar video of your AI character using:
  Primary:  D-ID API (realistic talking head, free tier available)
  Fallback: HeyGen API (alternative talking avatar)
  Local:    Animated avatar overlay via MoviePy (zero-cost offline option)

The avatar speaks the full script narration lip-synced to the TTS audio.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

# Pillow 10+ removed Image.ANTIALIAS (renamed to LANCZOS); patch for moviepy 1.x compatibility
try:
    from PIL import Image as _PILImage
    if not hasattr(_PILImage, "ANTIALIAS"):
        _PILImage.ANTIALIAS = _PILImage.LANCZOS
except Exception:
    pass

import config
from utils.logger import logger


# ── D-ID API Integration ──────────────────────────────────────────────────────

class DIDClient:
    """Client for the D-ID Talks API (talking portrait from a static image)."""

    BASE_URL = "https://api.d-id.com"

    def __init__(self):
        self.api_key = config.DID_API_KEY
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def create_talk(
        self,
        audio_url: str | None = None,
        audio_path: str | None = None,
        script_text: str | None = None,
        presenter_url: str | None = None,
    ) -> str:
        presenter = presenter_url or config.DID_PRESENTER_IMAGE_URL
        if not presenter:
            raise ValueError(
                "No presenter image URL set. Add DID_PRESENTER_IMAGE_URL to .env "
                "or pass presenter_url= to create_talk()."
            )

        payload: dict = {
            "source_url": presenter,
            "config": {
                "fluent": True,
                "pad_audio": 0.0,
                "stitch": True,
            },
        }

        if audio_url:
            payload["script"] = {"type": "audio", "audio_url": audio_url}
        elif script_text:
            payload["script"] = {
                "type": "text",
                "input": script_text,
                "provider": {
                    "type": "elevenlabs",
                    "voice_id": "EXAVITQu4vr4xnSDxMaL",
                },
            }
        elif audio_path:
            audio_url = self._upload_audio(audio_path)
            payload["script"] = {"type": "audio", "audio_url": audio_url}
        else:
            raise ValueError("Provide audio_url, audio_path, or script_text")

        resp = httpx.post(
            f"{self.BASE_URL}/talks",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        talk_id = resp.json()["id"]
        logger.info(f"D-ID talk job submitted: {talk_id}")
        return talk_id

    def _upload_audio(self, audio_path: str) -> str:
        with open(audio_path, "rb") as f:
            resp = httpx.post(
                f"{self.BASE_URL}/audios",
                headers={"Authorization": self.api_key},
                files={"audio": (Path(audio_path).name, f, "audio/mpeg")},
                timeout=60,
            )
        resp.raise_for_status()
        return resp.json()["url"]

    def poll_until_done(self, talk_id: str, timeout_secs: int = 300) -> dict:
        deadline = time.time() + timeout_secs
        delay = 5

        while time.time() < deadline:
            resp = httpx.get(
                f"{self.BASE_URL}/talks/{talk_id}",
                headers=self.headers,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")

            if status == "done":
                logger.success(f"D-ID talk ready: {talk_id}")
                return data
            elif status == "error":
                raise RuntimeError(f"D-ID talk failed: {data.get('error')}")

            logger.debug(f"D-ID status: {status} — waiting {delay}s...")
            time.sleep(delay)
            delay = min(delay * 1.5, 30)

        raise TimeoutError(f"D-ID job {talk_id} timed out after {timeout_secs}s")

    def download_video(self, talk_data: dict, output_path: Path) -> Path:
        result_url = talk_data.get("result_url")
        if not result_url:
            raise ValueError("No result_url in D-ID response")

        resp = httpx.get(result_url, timeout=120, follow_redirects=True)
        resp.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)
        logger.success(f"Avatar video saved: {output_path}")
        return output_path


# ── HeyGen API Integration (fallback) ────────────────────────────────────────

class HeyGenClient:
    """Client for HeyGen's Avatar Video API."""

    BASE_URL = "https://api.heygen.com/v2"

    def __init__(self):
        self.api_key = config.HEYGEN_API_KEY
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def create_video(self, script_text: str, avatar_id: str = "default") -> str:
        payload = {
            "video_inputs": [{
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": script_text,
                    "voice_id": "en-US-JennyNeural",
                },
            }],
            "aspect_ratio": "16:9",
            "test": False,
        }
        resp = httpx.post(f"{self.BASE_URL}/video/generate",
                          headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["data"]["video_id"]

    def poll_until_done(self, video_id: str, timeout_secs: int = 600) -> dict:
        deadline = time.time() + timeout_secs
        delay = 10
        while time.time() < deadline:
            resp = httpx.get(f"{self.BASE_URL}/video_status.get",
                             params={"video_id": video_id},
                             headers=self.headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()["data"]
            if data["status"] == "completed":
                return data
            elif data["status"] == "failed":
                raise RuntimeError(f"HeyGen video failed: {data.get('error')}")
            time.sleep(delay)
            delay = min(delay * 1.5, 30)
        raise TimeoutError(f"HeyGen job {video_id} timed out")


# ── Local Animated Avatar (zero-cost fallback) ────────────────────────────────

def create_local_avatar_overlay(
    audio_path: Path,
    avatar_image_path: Path,
    output_path: Path,
    background_color: str = "#0a0a1a",
) -> Path:
    try:
        from moviepy.editor import (
            AudioFileClip, ImageClip, ColorClip, CompositeVideoClip
        )
        import numpy as np
        from PIL import Image, ImageFilter, ImageEnhance
    except ImportError:
        raise ImportError("moviepy and Pillow required: pip install moviepy Pillow")

    logger.info(f"Creating local avatar overlay for: {audio_path.name}")

    audio = AudioFileClip(str(audio_path))
    duration = audio.duration
    fps = 24

    bg_r = int(background_color[1:3], 16)
    bg_g = int(background_color[3:5], 16)
    bg_b = int(background_color[5:7], 16)
    background = ColorClip(size=(1920, 1080), color=[bg_r, bg_g, bg_b], duration=duration)

    avatar_img = Image.open(str(avatar_image_path)).convert("RGBA")
    avatar_w = int(1920 * 0.42)
    avatar_h = int(avatar_img.height * (avatar_w / avatar_img.width))
    avatar_img = avatar_img.resize((avatar_w, avatar_h), Image.LANCZOS)

    avatar_clip = (
        ImageClip(str(avatar_image_path))
        .set_duration(duration)
        .resize(width=avatar_w)
        .set_position(("right", "center"))
    )

    composite = CompositeVideoClip([background, avatar_clip])
    composite = composite.set_audio(audio)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    composite.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )
    logger.success(f"Local avatar video saved: {output_path}")
    return output_path


# ── Main Entry Point ──────────────────────────────────────────────────────────

def generate_avatar_video(
    audio_path: Path,
    output_path: Path,
    script_text: str | None = None,
    force_local: bool = False,
) -> Path:
    """
    Generate a talking avatar video.

    Strategy:
      1. Try D-ID API (most realistic, free tier available)
      2. Try HeyGen API (fallback if D-ID fails)
      3. Local animated overlay (always works, zero cost)
    """
    if force_local:
        avatar_img = config.AVATAR_DIR / "character.png"
        if not avatar_img.exists():
            raise FileNotFoundError(
                f"Place your avatar character image at: {avatar_img}\n"
                f"Recommended: A professional AI-generated portrait, transparent PNG, 512x512+"
            )
        return create_local_avatar_overlay(audio_path, avatar_img, output_path)

    # Try D-ID first
    if config.DID_API_KEY:
        try:
            client = DIDClient()
            talk_id = client.create_talk(audio_path=str(audio_path))
            talk_data = client.poll_until_done(talk_id)
            return client.download_video(talk_data, output_path)
        except Exception as e:
            logger.warning(f"D-ID failed ({e}), trying HeyGen...")

    # Try HeyGen
    if config.HEYGEN_API_KEY and script_text:
        try:
            client = HeyGenClient()
            video_id = client.create_video(script_text)
            video_data = client.poll_until_done(video_id)
            video_url = video_data.get("video_url", "")
            if video_url:
                resp = httpx.get(video_url, timeout=120, follow_redirects=True)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(resp.content)
                return output_path
        except Exception as e:
            logger.warning(f"HeyGen failed ({e}), falling back to local avatar...")

    # Local image overlay disabled — character.png is a logo, not a human face.
    # video_agent._create_waveform_avatar() is the preferred fast fallback.
    raise FileNotFoundError(
        "No avatar source available (D-ID requires human face, "
        "HeyGen key missing). "
        "video_agent will substitute the waveform visualizer."
    )
