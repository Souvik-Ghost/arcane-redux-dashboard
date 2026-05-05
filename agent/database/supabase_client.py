"""
database/supabase_client.py — Supabase CRUD helpers for the YouTube AI agent.

Tables used:
  video_concepts   — script ideas, status tracking, published video IDs
  production_queue — job queue with step-level status
  agent_logs       — event log for all pipeline actions
  outlier_videos   — viral/trending videos detected by research agent
"""
from __future__ import annotations

import config
from utils.logger import logger

_client = None


def get_client():
    """Return a cached Supabase client."""
    global _client
    if _client is None:
        from supabase import create_client
        if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in agent/.env"
            )
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    return _client


def save_concept(title: str, hook: str, outline: str, narration: str) -> int:
    """Insert a new video concept and return its ID."""
    r = get_client().table("video_concepts").insert({
        "title": title,
        "hook": hook,
        "script_outline": outline,
        "full_script": narration,   # DB column is full_script (soul.md schema)
        "status": "scripted",
    }).execute()
    concept_id = r.data[0]["id"]
    logger.info(f"Concept saved (id={concept_id}): {title[:60]}")
    return concept_id


def update_concept_status(concept_id: int, status: str, **kwargs) -> None:
    """Update concept status (scripted → rendering → published / failed)."""
    data = {"status": status, **kwargs}
    get_client().table("video_concepts").update(data).eq("id", concept_id).execute()
    logger.info(f"Concept {concept_id} → {status}")


def get_pending_outliers() -> list[dict]:
    """Return up to 5 unprocessed outlier/viral videos from research."""
    try:
        return (
            get_client()
            .table("outlier_videos")
            .select("*")
            .eq("status", "pending")
            .limit(5)
            .execute()
            .data
        )
    except Exception as e:
        logger.warning(f"Could not fetch outliers: {e}")
        return []


def log_event(category: str, event: str, payload: dict) -> None:
    """Write an agent event log entry."""
    try:
        get_client().table("agent_logs").insert({
            "category": category,
            "event": event,
            "payload": payload,
        }).execute()
    except Exception as e:
        logger.debug(f"log_event failed (non-fatal): {e}")
