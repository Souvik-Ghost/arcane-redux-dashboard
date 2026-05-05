"""
config.py — Central configuration for the YouTube AI Agent.
Loads all settings from environment variables with sensible defaults.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root — override=True so .env wins over any system env vars
load_dotenv(Path(__file__).parent / ".env", override=True)


def _require(key: str) -> str:
    """Return env var or raise a clear error."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"Copy .env.template to agent/.env and fill in your credentials."
        )
    return val


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── Anthropic / Claude ────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = _get("ANTHROPIC_API_KEY")
CLAUDE_MODEL: str = _get("CLAUDE_MODEL", "claude-sonnet-4-6")

# ── Groq (free, OpenAI-compatible) ───────────────────────────────────────────
GROQ_API_KEY: str = _get("GROQ_API_KEY")
GROQ_MODEL: str = _get("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── Google Gemini ─────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = _get("GEMINI_API_KEY")
GEMINI_MODEL: str = _get("GEMINI_MODEL", "gemini-2.0-flash")

# ── YouTube Data API v3 ───────────────────────────────────────────────────────
YOUTUBE_CLIENT_ID: str = _get("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET: str = _get("YOUTUBE_CLIENT_SECRET")
YOUTUBE_CHANNEL_ID: str = _get("YOUTUBE_CHANNEL_ID")
YOUTUBE_CLIENT_SECRETS_FILE: str = _get("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
YOUTUBE_TOKEN_FILE: str = _get("YOUTUBE_TOKEN_FILE", "youtube_token.json")

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL: str = _get("SUPABASE_URL")
SUPABASE_SERVICE_KEY: str = _get("SUPABASE_SERVICE_KEY")

# ── Avatar (D-ID) ─────────────────────────────────────────────────────────────
DID_API_KEY: str = _get("DID_API_KEY")
DID_PRESENTER_IMAGE_URL: str = _get("DID_PRESENTER_IMAGE_URL")
DID_BASE_URL: str = "https://api.d-id.com"
HEYGEN_API_KEY: str = _get("HEYGEN_API_KEY")

# ── Canva ─────────────────────────────────────────────────────────────────────
CANVA_CLIENT_ID: str = _get("CANVA_CLIENT_ID")
CANVA_CLIENT_SECRET: str = _get("CANVA_CLIENT_SECRET")
CANVA_BRAND_TEMPLATE_ID: str = _get("CANVA_BRAND_TEMPLATE_ID")
CANVA_VIDEO_TEMPLATE_ID: str = _get("CANVA_VIDEO_TEMPLATE_ID")

# ── ClickUp (Human-in-the-Loop Approvals) ────────────────────────────────────
CLICKUP_API_KEY: str = _get("CLICKUP_API_KEY")
CLICKUP_LIST_ID: str = _get("CLICKUP_LIST_ID")
CLICKUP_IDEAS_LIST_ID: str = _get("CLICKUP_IDEAS_LIST_ID")
CLICKUP_CHAT_LIST_ID: str = _get("CLICKUP_CHAT_LIST_ID")

# ── LM Studio (local LLM — OpenAI-compatible API) ────────────────────────────
LM_STUDIO_BASE_URL: str = _get("LM_STUDIO_BASE_URL", "http://10.206.96.37:1234/v1")
LM_STUDIO_MODEL: str = _get("LM_STUDIO_MODEL", "nvidia/nemotron-3-nano-4b")
LM_STUDIO_API_KEY: str = _get("LM_STUDIO_API_KEY", "lm-studio")

# ── Pexels ────────────────────────────────────────────────────────────────────
PEXELS_API_KEY: str = _get("PEXELS_API_KEY")

# ── Pipeline / Channel Settings ───────────────────────────────────────────────
CHANNEL_NICHE: str = _get("CHANNEL_NICHE", "AI & Automation")
CHANNEL_TONE: str = _get("CHANNEL_TONE", "educational, engaging")
AVATAR_NAME: str = _get("AVATAR_NAME", "Aria")
AVATAR_VOICE: str = _get("AVATAR_VOICE", "af_heart")

VIDEOS_PER_WEEK: int = int(_get("VIDEOS_PER_WEEK", "3"))
PUBLISH_DAYS: list[str] = _get("PUBLISH_DAYS", "tue,thu,sat").split(",")
PUBLISH_HOUR: int = int(_get("PUBLISH_HOUR", "15"))

# Shorts schedule — comma-separated UTC hours to post each day
SHORTS_HOURS: list[int] = [int(h) for h in _get("SHORTS_HOURS", "8,14,20").split(",")]
SHORTS_PER_DAY: int = int(_get("SHORTS_PER_DAY", "3"))

# Community post schedule — comma-separated UTC hours
COMMUNITY_HOURS: list[int] = [int(h) for h in _get("COMMUNITY_HOURS", "10,18").split(",")]

COMPETITOR_CHANNELS: list[str] = [
    c.strip() for c in _get("COMPETITOR_CHANNELS", "").split(",") if c.strip()
]
OUTLIER_THRESHOLD: float = float(_get("OUTLIER_THRESHOLD", "2.0"))
REQUIRE_APPROVAL: bool = _get("REQUIRE_APPROVAL", "true").lower() == "true"

# ── Output Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / _get("OUTPUT_DIR", "output")
SCRIPTS_DIR = BASE_DIR / _get("SCRIPTS_DIR", "output/scripts")
AUDIO_DIR = BASE_DIR / _get("AUDIO_DIR", "output/audio")
VIDEOS_DIR = BASE_DIR / _get("VIDEOS_DIR", "output/videos")
THUMBNAILS_DIR = BASE_DIR / _get("THUMBNAILS_DIR", "output/thumbnails")
ASSETS_DIR = BASE_DIR / "assets"
AVATAR_DIR = BASE_DIR / "assets" / "avatar"

# Ensure output dirs exist
for _dir in [OUTPUT_DIR, SCRIPTS_DIR, AUDIO_DIR, VIDEOS_DIR, THUMBNAILS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)
