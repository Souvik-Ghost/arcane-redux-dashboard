"""
agents/video_agent.py — Long-form video producer (stub).

The full video_agent.py was not available when this portable dashboard was created.
To reconstruct it, refer to soul.md in the original agent directory:
  C:\\Users\\souvi\\AppData\\Local\\Temp\\arcane-redux-agent\\soul.md

The full pipeline requires:
  - Kokoro ONNX TTS (v1.0) for narration
  - Waveform avatar fallback via FFmpeg + MoviePy
  - 10 animated scene clips with cosmic gradient (FFmpeg geq filter)
  - Scene concatenation + composite
  - YouTube Data API v3 upload
"""


def produce_video(script, job_id: str) -> dict:
    """
    Produce a full long-form video from a VideoScript object.

    This stub raises NotImplementedError — the full implementation requires
    the complete agent codebase. See soul.md for the reconstruction blueprint.
    """
    raise NotImplementedError(
        "video_agent.py stub only. Full implementation requires Kokoro ONNX, "
        "FFmpeg scene rendering (~18 min on CPU), and MoviePy composite. "
        "See soul.md for reconstruction steps."
    )
