"""
utils/tts.py — Text-to-Speech synthesis using Kokoro ONNX v1.0.

Kokoro is a free, local, high-quality TTS engine.
Install: pip install kokoro-onnx soundfile
Models: download from https://github.com/thewh1teagle/kokoro-onnx/releases

Voice options (English):
  af_heart   — warm female (recommended)
  af_bella   — expressive female
  am_adam    — male voice
  am_michael — deep male
"""
from __future__ import annotations

from pathlib import Path
from utils.logger import logger


def synthesise(
    text: str,
    output_path: Path,
    voice: str = "af_heart",
    speed: float = 1.0,
) -> Path:
    """
    Convert text to speech and save as MP3/WAV.

    Args:
        text: The narration text to synthesise
        output_path: Path where audio file will be saved
        voice: Kokoro voice ID (default: af_heart)
        speed: Playback speed multiplier (0.5-2.0)

    Returns:
        Path to the saved audio file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"TTS: {len(text)} chars → {output_path.name} (voice={voice})")

    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf
        import numpy as np

        # Look for model files in the agent directory and common locations
        agent_dir = Path(__file__).parent.parent
        search_paths = [
            agent_dir,
            agent_dir.parent,
            Path.home() / "models",
            Path.home() / "Downloads",
        ]

        model_path = None
        voices_path = None
        for base in search_paths:
            m = base / "kokoro-v1.0.onnx"
            v = base / "voices-v1.0.bin"
            if m.exists() and v.exists():
                model_path, voices_path = m, v
                break

        if not model_path:
            raise FileNotFoundError(
                "Kokoro model files not found!\n"
                "Download from: https://github.com/thewh1teagle/kokoro-onnx/releases\n"
                f"Place kokoro-v1.0.onnx and voices-v1.0.bin in: {agent_dir}"
            )

        k = Kokoro(str(model_path), str(voices_path))
        samples, sample_rate = k.create(text, voice=voice, speed=speed, lang="en-us")

        # Save as the appropriate format based on extension
        ext = output_path.suffix.lower()
        if ext == ".mp3":
            # Save as WAV first, then convert if possible
            wav_path = output_path.with_suffix(".wav")
            sf.write(str(wav_path), samples, sample_rate)
            try:
                import subprocess
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", str(wav_path), str(output_path)],
                    capture_output=True
                )
                if result.returncode == 0:
                    wav_path.unlink(missing_ok=True)
                else:
                    # Rename WAV to MP3 path if ffmpeg fails (still playable)
                    wav_path.rename(output_path)
            except FileNotFoundError:
                wav_path.rename(output_path)
        else:
            sf.write(str(output_path), samples, sample_rate)

        logger.success(f"TTS saved: {output_path} ({output_path.stat().st_size // 1024}KB)")
        return output_path

    except FileNotFoundError:
        logger.warning("Kokoro model files not found — falling back to edge-tts (Microsoft Neural TTS)")
        return _synthesise_edge_tts(text, output_path, voice)

    except ImportError:
        logger.warning("kokoro-onnx not installed — falling back to edge-tts")
        return _synthesise_edge_tts(text, output_path, voice)


# ── edge-tts fallback (Microsoft Neural TTS, no model files needed) ───────────

_EDGE_VOICE_MAP = {
    "af_heart":   "en-US-JennyNeural",    # warm female (closest to af_heart)
    "af_bella":   "en-US-AnaNeural",      # expressive female
    "am_adam":    "en-US-GuyNeural",      # male
    "am_michael": "en-US-ChristopherNeural",  # deep male
}


def _synthesise_edge_tts(text: str, output_path: Path, voice: str = "af_heart") -> Path:
    """
    Synthesise speech via Microsoft Edge TTS (free, no model files, internet required).
    Falls back to this when Kokoro ONNX models are not available.
    """
    import asyncio
    import subprocess

    edge_voice = _EDGE_VOICE_MAP.get(voice, "en-US-JennyNeural")
    logger.info(f"edge-tts: {len(text)} chars → {output_path.name} (voice={edge_voice})")

    try:
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, edge_voice)
            # edge-tts saves as MP3 directly
            mp3_path = output_path.with_suffix(".mp3")
            await communicate.save(str(mp3_path))
            return mp3_path

        # Run in new event loop (safe from both sync and async contexts)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _run())
                    mp3_path = future.result(timeout=300)
            else:
                mp3_path = loop.run_until_complete(_run())
        except RuntimeError:
            mp3_path = asyncio.run(_run())

        # Rename to expected extension if needed
        if output_path.suffix.lower() != ".mp3":
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(mp3_path), str(output_path)],
                capture_output=True, timeout=120,
            )
            mp3_path.unlink(missing_ok=True)
        elif mp3_path != output_path:
            mp3_path.rename(output_path)

        logger.success(f"edge-tts saved: {output_path} ({output_path.stat().st_size // 1024}KB)")
        return output_path

    except ImportError:
        raise RuntimeError(
            "No TTS available! Install edge-tts:\n"
            "  pip install edge-tts\n"
            "Or download Kokoro models from: https://github.com/thewh1teagle/kokoro-onnx/releases"
        )
