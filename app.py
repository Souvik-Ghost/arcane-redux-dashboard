"""
app.py — Arcane Redux Dashboard Backend
FastAPI server: REST API + WebSocket log streaming + agent process management
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv, set_key
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
AGENT_DIR = BASE_DIR / "agent"
STATIC    = BASE_DIR / "static"

# Load agent/.env first (live credentials), fall back to dashboard root .env
ENV_FILE = AGENT_DIR / ".env"
if not ENV_FILE.exists():
    ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE, override=True)

app = FastAPI(title="Arcane Redux Dashboard", version="1.0.0")

# ── In-memory job store ───────────────────────────────────────────────────────
jobs: dict[str, dict] = {}          # job_id → {status, topic, type, log, pid, url}
log_buffer: deque = deque(maxlen=500)  # global log ring buffer
ws_clients: list[WebSocket] = []    # connected WebSocket clients


# ── Broadcast to all WebSocket clients ───────────────────────────────────────
async def broadcast(msg: dict):
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.remove(ws)


def emit(msg: dict):
    """Thread-safe broadcast from sync context."""
    log_buffer.append(msg)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(msg), loop)
    except Exception:
        pass


# ── Job runner (background thread) ───────────────────────────────────────────
def run_job(job_id: str, script_path: str, env_extra: dict | None = None):
    """Run a Python script as a subprocess, stream its output."""
    job = jobs[job_id]
    job["status"] = "running"
    job["started_at"] = time.time()
    emit({"type": "job_update", "job": job_id, "status": "running"})

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(AGENT_DIR),
        )
        job["pid"] = proc.pid

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            job["log"].append(line)
            emit({"type": "log", "job": job_id, "line": line})

            # Parse key events from log lines
            if "PUBLISHED:" in line or "youtube.com" in line:
                url_match = re.search(r"https?://[^\s]+", line)
                if url_match:
                    job["url"] = url_match.group()
                    emit({"type": "published", "job": job_id, "url": job["url"]})
            if "Script ready:" in line or "Script generated" in line:
                emit({"type": "step", "job": job_id, "step": "script_done"})
            if "Kokoro TTS saved" in line:
                emit({"type": "step", "job": job_id, "step": "tts_done"})
            if "avatar saved" in line.lower() or "waveform avatar" in line.lower():
                emit({"type": "step", "job": job_id, "step": "avatar_done"})
            if "Step 3/5" in line:
                emit({"type": "step", "job": job_id, "step": "scenes_start"})
            if "Step 4/5" in line:
                emit({"type": "step", "job": job_id, "step": "concat_start"})
            if "Step 5/5" in line or "Uploading video" in line:
                emit({"type": "step", "job": job_id, "step": "upload_start"})

        proc.wait()
        job["status"] = "done" if proc.returncode == 0 else "error"
        job["ended_at"] = time.time()
        emit({"type": "job_update", "job": job_id, "status": job["status"],
              "url": job.get("url", "")})

    except Exception as e:
        job["status"] = "error"
        job["log"].append(f"ERROR: {e}")
        emit({"type": "job_update", "job": job_id, "status": "error", "error": str(e)})


# ── API models ────────────────────────────────────────────────────────────────
class ProduceRequest(BaseModel):
    topic: str
    context: str = ""
    model_provider: str = "lm_studio"   # "lm_studio" | "claude" | "groq" | "gemini"
    model_name: str = ""

class ShortsRequest(BaseModel):
    topics: list[str]
    model_provider: str = "lm_studio"

class SettingsUpdate(BaseModel):
    key: str
    value: str


# ── Generate one-shot runner scripts ─────────────────────────────────────────
def _write_produce_script(job_id: str, topic: str, context: str) -> Path:
    script = AGENT_DIR / f"_run_{job_id}.py"
    script.write_text(f'''
import sys, os
sys.path.insert(0, str(__file__).rsplit("/",1)[0] if "/" in str(__file__) else str(__file__).rsplit("\\\\",1)[0])
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONIOENCODING"] = "utf-8"
import config
from agents.script_agent import generate_script
from agents.video_agent import produce_video
from agents.thumbnail_agent import generate_thumbnail
from database import supabase_client as db
from utils.youtube_api import upload_video, upload_thumbnail
import uuid

JOB_ID = "{job_id}"
TOPIC  = {repr(topic)}
CONTEXT = {{"niche": config.CHANNEL_NICHE, "user_research": {repr(context)}}}

print("\\n" + "="*60)
print(f"  Job: {{JOB_ID}}")
print(f"  Topic: {{TOPIC}}")
print("="*60 + "\\n")

print("[1/4] Generating script...")
script = generate_script(topic=TOPIC, context=CONTEXT)
print(f"  Title: {{script.title}}")
print(f"  Scenes: {{len(script.scenes)}}, ~{{script.total_duration_estimate//60}}min")

concept_id = db.save_concept(script.title, script.hook,
    "\\n".join(s.visual_direction for s in script.scenes), script.full_narration())

print("\\n[2/4] Generating thumbnail...")
thumb_path = generate_thumbnail(script.title, script.hook[:80],
    script.thumbnail_concept, JOB_ID)
print(f"  Thumbnail: {{thumb_path}}")

print("\\n[3/4] Producing video...")
db.update_concept_status(concept_id, "rendering")
assets = produce_video(script=script, job_id=JOB_ID)
size_mb = assets["final_video"].stat().st_size / 1_048_576
print(f"  Final video: {{assets[\'final_video\'].name}} ({{size_mb:.1f}} MB)")

print("\\n[4/4] Uploading to YouTube...")
video_id = upload_video(assets["final_video"], script.title,
    script.description, script.tags, "public")
if thumb_path.exists():
    upload_thumbnail(video_id, thumb_path)
db.update_concept_status(concept_id, "published", canva_design_id=video_id)

url = f"https://youtube.com/watch?v={{video_id}}"
print(f"\\n{'='*60}")
print(f"  PUBLISHED: {{url}}")
print(f"{'='*60}\\n")
''', encoding="utf-8")
    return script


def _write_shorts_script(job_id: str, topics: list[str]) -> Path:
    script = AGENT_DIR / f"_run_shorts_{job_id}.py"
    script.write_text(f'''
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONIOENCODING"] = "utf-8"
from agents.shorts_agent import produce_and_upload_short

TOPICS = {repr(topics)}

print("\\n{'='*60}")
print("  Arcane Redux — Shorts Batch ({len(topics)} videos)")
print("{'='*60}\\n")

for i, topic in enumerate(TOPICS, 1):
    print(f"\\n[Short {{i}}/{len(topics)}] {{topic}}")
    try:
        video_id = produce_and_upload_short(topic=topic)
        print(f"  PUBLISHED: https://youtube.com/shorts/{{video_id}}")
    except Exception as e:
        print(f"  ERROR: {{e}}")

print("\\n{'='*60}")
print("  Done.")
print("{'='*60}\\n")
''', encoding="utf-8")
    return script


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/status")
async def get_status():
    """System health check — LM Studio, Claude, Supabase, YouTube."""
    result: dict[str, Any] = {}

    # LM Studio
    lm_url = os.getenv("LM_STUDIO_BASE_URL", "http://10.206.96.37:1234/v1")
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{lm_url}/models")
        models = [m["id"] for m in r.json().get("data", [])]
        result["lm_studio"] = {"ok": True, "url": lm_url,
                               "model": os.getenv("LM_STUDIO_MODEL", ""), "models": models}
    except Exception as e:
        result["lm_studio"] = {"ok": False, "error": str(e), "models": []}

    # Claude
    claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    result["claude"] = {"ok": bool(claude_key and "PASTE" not in claude_key),
                        "model": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")}

    # Groq
    groq_key = os.getenv("GROQ_API_KEY", "")
    result["groq"] = {"ok": bool(groq_key and "PASTE" not in groq_key)}

    # Supabase
    sb_url = os.getenv("SUPABASE_URL", "")
    result["supabase"] = {"ok": bool(sb_url), "url": sb_url}

    # YouTube
    yt_token = AGENT_DIR / os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")
    result["youtube"] = {"ok": yt_token.exists(), "channel": os.getenv("YOUTUBE_CHANNEL_ID", "")}

    # Active jobs
    result["active_jobs"] = sum(1 for j in jobs.values() if j["status"] == "running")
    result["total_jobs"] = len(jobs)

    return result


@app.get("/api/lm/models")
async def get_lm_models():
    lm_url = os.getenv("LM_STUDIO_BASE_URL", "")
    if not lm_url:
        return {"models": []}
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{lm_url}/models")
        return {"models": [m["id"] for m in r.json().get("data", [])]}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.post("/api/produce")
async def start_production(req: ProduceRequest):
    """Start a long-form video production job."""
    if not AGENT_DIR.exists():
        raise HTTPException(400, "Agent directory not found. Check setup.")

    job_id = str(uuid.uuid4())[:8]

    # Override LLM env if user picked a specific provider
    env_override = {}
    if req.model_provider == "claude":
        env_override["FORCE_LLM"] = "claude"
    elif req.model_provider == "groq":
        env_override["FORCE_LLM"] = "groq"
    elif req.model_provider == "lm_studio" and req.model_name:
        env_override["LM_STUDIO_MODEL"] = req.model_name

    script = _write_produce_script(job_id, req.topic, req.context)

    jobs[job_id] = {
        "id": job_id, "type": "video", "topic": req.topic,
        "status": "queued", "log": [], "url": "",
        "started_at": None, "ended_at": None,
    }

    t = threading.Thread(target=run_job, args=(job_id, str(script), env_override), daemon=True)
    t.start()

    return {"job_id": job_id, "status": "queued"}


@app.post("/api/shorts")
async def start_shorts(req: ShortsRequest):
    """Start a Shorts batch job."""
    if not AGENT_DIR.exists():
        raise HTTPException(400, "Agent directory not found.")

    job_id = str(uuid.uuid4())[:8]
    script = _write_shorts_script(job_id, req.topics)

    jobs[job_id] = {
        "id": job_id, "type": "shorts", "topic": f"{len(req.topics)} shorts",
        "status": "queued", "log": [], "url": "",
        "started_at": None, "ended_at": None,
    }

    t = threading.Thread(target=run_job, args=(job_id, str(script)), daemon=True)
    t.start()

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs")
async def list_jobs():
    return {"jobs": list(jobs.values())}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/api/videos")
async def list_videos():
    """Fetch published videos from Supabase."""
    try:
        sys.path.insert(0, str(AGENT_DIR))
        import importlib, config
        importlib.reload(config)
        from database import supabase_client as db
        client = db.get_client()
        result = client.table("video_concepts") \
            .select("id,title,status,canva_design_id,created_at") \
            .eq("status", "published") \
            .order("created_at", desc=True) \
            .limit(20).execute()
        return {"videos": result.data}
    except Exception as e:
        return {"videos": [], "error": str(e)}


@app.get("/api/settings")
async def get_settings():
    """Return non-secret config values."""
    return {
        "LM_STUDIO_BASE_URL": os.getenv("LM_STUDIO_BASE_URL", ""),
        "LM_STUDIO_MODEL": os.getenv("LM_STUDIO_MODEL", ""),
        "CLAUDE_MODEL": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        "CHANNEL_NICHE": os.getenv("CHANNEL_NICHE", ""),
        "CHANNEL_TONE": os.getenv("CHANNEL_TONE", ""),
        "AVATAR_NAME": os.getenv("AVATAR_NAME", ""),
        "AVATAR_VOICE": os.getenv("AVATAR_VOICE", "af_heart"),
        "VIDEOS_PER_WEEK": os.getenv("VIDEOS_PER_WEEK", "3"),
        "PUBLISH_DAYS": os.getenv("PUBLISH_DAYS", "tue,thu,sat"),
        "PUBLISH_HOUR": os.getenv("PUBLISH_HOUR", "15"),
        "SHORTS_PER_DAY": os.getenv("SHORTS_PER_DAY", "3"),
        "REQUIRE_APPROVAL": os.getenv("REQUIRE_APPROVAL", "true"),
        "YOUTUBE_CHANNEL_ID": os.getenv("YOUTUBE_CHANNEL_ID", ""),
        "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
        "PEXELS_API_KEY": os.getenv("PEXELS_API_KEY", ""),
    }


@app.post("/api/settings")
async def update_setting(req: SettingsUpdate):
    """Update a single .env key (writes to agent/.env)."""
    target = AGENT_DIR / ".env"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text("")
    set_key(str(target), req.key, req.value)
    os.environ[req.key] = req.value
    return {"ok": True, "key": req.key}


@app.post("/api/test/lm")
async def test_lm():
    lm_url = os.getenv("LM_STUDIO_BASE_URL", "")
    lm_key = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
    lm_model = os.getenv("LM_STUDIO_MODEL", "")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{lm_url}/chat/completions",
                headers={"Authorization": f"Bearer {lm_key}"},
                json={"model": lm_model,
                      "messages": [{"role": "user", "content": "Reply: READY"}],
                      "max_tokens": 10})
        content = r.json()["choices"][0]["message"]["content"]
        return {"ok": True, "response": content, "model": lm_model}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/test/claude")
async def test_claude():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or "PASTE" in key:
        return {"ok": False, "error": "No API key configured"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model="claude-haiku-4-5",
            max_tokens=20,
            messages=[{"role": "user", "content": "Reply: READY"}])
        return {"ok": True, "response": msg.content[0].text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── WebSocket: real-time log stream ──────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    # Send backlog
    for msg in list(log_buffer):
        try:
            await ws.send_json(msg)
        except Exception:
            break
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        if ws in ws_clients:
            ws_clients.remove(ws)


# ── Serve static files ────────────────────────────────────────────────────────
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn
    import webbrowser

    print("\n" + "="*60)
    print("  Arcane Redux Dashboard")
    print("  http://localhost:7842")
    print("="*60 + "\n")

    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:7842")).start()
    uvicorn.run("app:app", host="0.0.0.0", port=7842, reload=False)
