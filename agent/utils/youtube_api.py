"""
utils/youtube_api.py — YouTube Data API v3 helpers.

Handles OAuth2 token management, video upload, and thumbnail upload.
Token is cached in youtube_token.json for subsequent runs.
Supports both JSON and pickle token formats.
"""
from __future__ import annotations

from pathlib import Path
from utils.logger import logger

import config


def _load_credentials(token_path: Path):
    """Load OAuth2 credentials from token file (JSON or pickle format)."""
    from google.oauth2.credentials import Credentials

    # Try JSON format first (standard google-auth format)
    try:
        creds = Credentials.from_authorized_user_file(
            str(token_path), config.YOUTUBE_SCOPES
        )
        return creds
    except Exception:
        pass

    # Try pickle format (used by some older google-auth versions)
    try:
        import pickle
        with open(token_path, "rb") as f:
            creds = pickle.load(f)
        # Convert to JSON and re-save for future runs
        token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Converted token from pickle to JSON format")
        return creds
    except Exception as e:
        logger.warning(f"Could not load token as pickle: {e}")

    return None


def get_youtube_client():
    """
    Return an authenticated YouTube API client.
    Uses cached OAuth2 token from youtube_token.json.
    Refreshes automatically if expired.
    """
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = Path(config.BASE_DIR) / config.YOUTUBE_TOKEN_FILE

    creds = None
    if token_path.exists():
        creds = _load_credentials(token_path)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing YouTube OAuth token...")
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            secrets_file = Path(config.BASE_DIR) / config.YOUTUBE_CLIENT_SECRETS_FILE
            if not secrets_file.exists():
                raise FileNotFoundError(
                    f"YouTube client secrets not found at {secrets_file}\n"
                    "Download from Google Cloud Console → OAuth 2.0 credentials"
                )
            logger.info("Starting YouTube OAuth flow (browser will open)...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secrets_file), config.YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
            logger.success(f"YouTube token saved: {token_path}")

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "public",
) -> str:
    """
    Upload a video to YouTube.
    Returns YouTube video ID (e.g. "dQw4w9WgXcQ")
    """
    from googleapiclient.http import MediaFileUpload

    logger.info(f"Uploading video: {video_path.name} ({video_path.stat().st_size // 1_048_576:.1f} MB)")

    yt = get_youtube_client()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:15],
            "categoryId": "28",  # Science & Technology
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }

    media = MediaFileUpload(
        str(video_path), mimetype="video/mp4", resumable=True,
        chunksize=10 * 1024 * 1024
    )
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            logger.info(f"Upload progress: {pct}%")

    video_id = response["id"]
    logger.success(f"Video uploaded: https://youtube.com/watch?v={video_id}")
    return video_id


def upload_thumbnail(video_id: str, thumb_path: Path) -> None:
    """Upload a custom thumbnail to an existing YouTube video."""
    from googleapiclient.http import MediaFileUpload

    if not thumb_path.exists() or thumb_path.stat().st_size == 0:
        logger.warning(f"Thumbnail file missing or empty: {thumb_path}")
        return

    logger.info(f"Uploading thumbnail for {video_id}...")
    yt = get_youtube_client()
    media = MediaFileUpload(str(thumb_path), mimetype="image/jpeg")
    yt.thumbnails().set(videoId=video_id, media_body=media).execute()
    logger.success(f"Thumbnail uploaded for {video_id}")
