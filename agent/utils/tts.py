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

    except ImportError:
        raise RuntimeError(
            "kokoro-onnx not installed.\n"
            "Run: pip install kokoro-onnx soundfile\n"
            "Then download models from: https://github.com/thewh1teagle/kokoro-onnx/releases"
        )
