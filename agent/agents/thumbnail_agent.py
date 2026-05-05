"""
agents/thumbnail_agent.py — YouTube thumbnail generator.
Uses Pillow to create a simple branded thumbnail.
"""
from pathlib import Path
import config
from utils.logger import logger


def generate_thumbnail(title: str, hook: str, concept: str, job_id: str) -> Path:
    """
    Generate a YouTube thumbnail (1280x720 JPEG).
    Uses Pillow for local generation — no API required.
    """
    path = config.THUMBNAILS_DIR / f"{job_id}_thumb.jpg"
    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        # Dark space background
        img = Image.new("RGB", (1280, 720), color=(5, 5, 16))
        draw = ImageDraw.Draw(img)

        # Gradient overlay (simple)
        for y in range(720):
            alpha = int(30 * (y / 720))
            draw.line([(0, y), (1280, y)], fill=(alpha, alpha // 4, alpha * 2))

        # Title text (wrapped)
        try:
            font_large = ImageFont.truetype("arial.ttf", 72)
            font_small = ImageFont.truetype("arial.ttf", 36)
        except Exception:
            font_large = ImageFont.load_default()
            font_small = font_large

        lines = textwrap.wrap(title[:80], width=28)
        y_offset = 200
        for line in lines[:3]:
            draw.text((80, y_offset), line, fill=(255, 255, 255), font=font_large)
            y_offset += 85

        # Hook text
        draw.text((80, y_offset + 20), hook[:70], fill=(79, 143, 255), font=font_small)

        # Channel watermark
        draw.text((80, 660), "ARCANE REDUX", fill=(100, 100, 140), font=font_small)

        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path), "JPEG", quality=95)
        logger.success(f"Thumbnail saved: {path}")

    except Exception as e:
        logger.warning(f"Thumbnail generation failed ({e}), creating placeholder")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Create minimal valid JPEG placeholder
        try:
            from PIL import Image
            img = Image.new("RGB", (1280, 720), color=(10, 10, 20))
            img.save(str(path), "JPEG", quality=85)
        except Exception:
            path.write_bytes(b"")

    return path
