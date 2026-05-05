# Arcane Redux — AI YouTube Channel Dashboard

> **Fully portable, AI-powered YouTube channel operator with a real-time web dashboard.**
> Drop it on any machine, run `start.bat`, and let it write scripts, generate voiceovers, render videos, and upload to YouTube — automatically.

![Dashboard UI](https://img.shields.io/badge/UI-Google%20Stitch%20Inspired-7c3aed?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## What It Does

Arcane Redux is a **one-click YouTube automation stack** built around a dark, Google Stitch–inspired dashboard. Point it at a topic, pick your AI brain, and the agent handles everything end-to-end:

```
Topic (you) → Script (AI) → Thumbnail → TTS Voiceover → Avatar → 10 Scene Clips → Upload → YouTube
```

**Long-form pipeline** (`/api/produce`):
1. Generates a full 10–15 min script with hook, scenes, and CTA via your chosen LLM
2. Creates a thumbnail with Pillow
3. Synthesises voiceover — Kokoro ONNX (local, free) or Microsoft Edge TTS (fallback)
4. Renders an animated waveform avatar via FFmpeg (~90s render)
5. Builds 10 animated scene clips (pre-rendered cosmic gradient loop, ~10 min total on CPU)
6. Concatenates and composites everything into a final 1080p MP4
7. Uploads to YouTube with title, description, tags, and thumbnail

**Shorts pipeline** (`/api/shorts`):
- Vertical 1080×1920 clips with animated gradient, hook text, and watermark
- Up to 5 shorts per batch, auto-uploaded with `#Shorts` tag

---

## AI Model Chain (free-first priority)

The agent tries each provider in order, falls back automatically:

| Priority | Provider | Cost | Notes |
|----------|----------|------|-------|
| 1 | **LM Studio** (local) | Free | Any model you load — zero network cost |
| 2 | **Groq** | Free | 14,400 req/day, llama-3.3-70b |
| 3 | **OpenRouter** | Free tier | meta-llama/llama-3.3-70b-instruct:free |
| 4 | **Gemini** | Free | 1,500 req/day, gemini-2.0-flash |
| 5 | **OpenAI** | Paid | gpt-4o-mini |
| 6 | **Claude** | Paid | claude-sonnet-4-6 |

You can also force a specific provider from the dashboard's **AI Models** page.

---

## Dashboard Pages

| Page | What it does |
|------|-------------|
| **Dashboard** | Status pills (LM Studio / Claude / YouTube / Supabase), active jobs summary |
| **Produce Video** | Topic input, context field, model selector, one-click produce |
| **Shorts** | Batch shorts input (up to 5 topics), model selector, start button |
| **Library** | Video grid pulled from Supabase — thumbnails from YouTube CDN |
| **Jobs** | Live job list with status badges and elapsed time |
| **AI Models** | Provider cards with live Test buttons, current model display |
| **Settings** | Reads/writes `agent/.env` live — channel niche, schedule, API keys |
| **Live Logs** | Real-time terminal via WebSocket — colour-coded by log level |

---

## Quick Start

### Requirements
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) on `PATH`
- At least one free API key (Groq recommended: [console.groq.com](https://console.groq.com))

### Windows (double-click)

```bat
start.bat
```

This creates a `.venv`, installs all dependencies, and opens the dashboard at `http://localhost:7842`.

### Linux / macOS

```bash
chmod +x start.sh && ./start.sh
```

### Manual

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:7842
```

---

## Configuration

Copy `.env.template` → `agent/.env` and fill in your keys:

```dotenv
# ── LLM (at least one required) ───────────────────────────────────────────────
GROQ_API_KEY=gsk_...              # free at console.groq.com
ANTHROPIC_API_KEY=sk-ant-...      # optional paid fallback
GEMINI_API_KEY=AIza...            # free 1500/day at aistudio.google.com

# ── LM Studio (optional — run any local model for free) ───────────────────────
LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=nvidia/nemotron-3-nano-4b

# ── YouTube ───────────────────────────────────────────────────────────────────
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_CHANNEL_ID=UC...

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...

# ── Channel Identity ─────────────────────────────────────────────────────────
CHANNEL_NICHE=applied AI research and automation
CHANNEL_TONE=analytical, no-hype, evidence-based
AVATAR_NAME=Rabbit King
AVATAR_VOICE=af_heart
```

All settings can also be changed live from the **Settings** page in the dashboard.

---

## Project Structure

```
arcane-redux-dashboard/
├── app.py                        # FastAPI backend — REST API + WebSocket log stream
├── requirements.txt              # Python dependencies
├── start.bat                     # Windows one-click launcher
├── start.sh                      # Linux/macOS launcher
├── .env.template                 # Config template (copy → agent/.env)
│
├── static/
│   └── index.html                # Full dashboard UI (vanilla JS, no build step)
│
└── agent/
    ├── config.py                 # Loads agent/.env, typed constants
    ├── run_shorts.py             # One-shot Shorts batch runner
    │
    ├── agents/
    │   ├── script_agent.py       # LLM script generation (multi-provider chain)
    │   ├── video_agent.py        # Full long-form video pipeline (5 steps)
    │   ├── shorts_agent.py       # Shorts pipeline
    │   ├── thumbnail_agent.py    # Pillow-based thumbnail generator
    │   └── avatar_agent.py       # D-ID / HeyGen / waveform FFmpeg fallback
    │
    ├── database/
    │   └── supabase_client.py    # Supabase CRUD (video_concepts, production_queue)
    │
    └── utils/
        ├── tts.py                # Kokoro ONNX → edge-tts fallback TTS
        ├── youtube_api.py        # YouTube Data API v3 OAuth2 wrapper
        └── logger.py             # Loguru config
```

---

## Video Pipeline (Technical)

### Long-form (1080p, ~10–15 min)

```
Step 1/5  TTS          Kokoro ONNX v1.0 (af_heart) or Microsoft Edge Neural TTS
                       ~5–8 min inference on CPU for 3000-char script

Step 2/5  Avatar       D-ID API → HeyGen API → FFmpeg waveform visualizer fallback
                       Waveform render: ~90s regardless of audio length

Step 3/5  Scene clips  Pre-render 12s cosmic gradient tile ONCE via FFmpeg geq filter (~90s)
                       Loop tile for each scene + drawtext overlay (~10s per clip)
                       Total: ~10 min for 10 scenes  ← was 2.5 hrs before optimization

Step 4/5  Concat       FFmpeg concat demuxer → single timeline MP4

Step 5/5  Composite    Avatar PIP (320×180, bottom-right) over scene timeline
                       Map avatar audio track → final.mp4
```

### Shorts (1080×1920)

```
TTS → FFmpeg vertical gradient → drawtext hook/body/watermark → YouTube Shorts upload
```

---

## API Reference

All endpoints served at `http://localhost:7842`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Dashboard UI |
| `GET` | `/api/status` | LM Studio / Claude / YouTube / Supabase health |
| `POST` | `/api/produce` | Start long-form video job |
| `POST` | `/api/shorts` | Start Shorts batch job |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/{id}` | Job detail + full log |
| `GET` | `/api/videos` | Published videos from Supabase |
| `GET` | `/api/settings` | Current config values |
| `POST` | `/api/settings` | Update a single `.env` key live |
| `POST` | `/api/test/lm` | Test LM Studio connection |
| `POST` | `/api/test/claude` | Test Claude API key |
| `GET` | `/api/lm/models` | List models loaded in LM Studio |
| `WS` | `/ws` | Real-time log stream (WebSocket) |

### Example: Produce a video

```bash
curl -X POST http://localhost:7842/api/produce \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "How AI agents are replacing entire job categories",
    "context": "Focus on white-collar automation, cite recent studies",
    "model_provider": "groq"
  }'
# → {"job_id": "a1b2c3d4", "status": "queued"}
```

### WebSocket log stream

```javascript
const ws = new WebSocket("ws://localhost:7842/ws");
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "log")       console.log(msg.line);
  if (msg.type === "published") console.log("Live:", msg.url);
};
```

---

## TTS Options

| Engine | Quality | Cost | Setup |
|--------|---------|------|-------|
| **Kokoro ONNX v1.0** | ★★★★★ | Free, local | Download `kokoro-v1.0.onnx` + `voices-v1.0.bin` from [releases](https://github.com/thewh1teagle/kokoro-onnx/releases), place in `agent/` |
| **Edge TTS** (auto-fallback) | ★★★★☆ | Free, cloud | `pip install edge-tts` — no model files needed |

Place Kokoro model files in `agent/` for best voice quality:
```
agent/
├── kokoro-v1.0.onnx     ← download ~310 MB
├── voices-v1.0.bin      ← download ~115 MB
```

---

## Supabase Schema

```sql
create table video_concepts (
  id            bigserial primary key,
  title         text,
  hook          text,
  script_outline text,
  full_script   text,
  status        text default 'pending',  -- scripted → rendering → published / failed
  canva_design_id text,                  -- stores YouTube video_id after publish
  created_at    timestamptz default now()
);

create table production_queue (
  id                bigserial primary key,
  concept_id        bigint references video_concepts(id),
  youtube_video_id  text,
  status            text default 'queued',
  created_at        timestamptz default now()
);
```

---

## Known Issues & Workarounds

| Issue | Fix |
|-------|-----|
| LM Studio IP changes on network restart | Update `LM_STUDIO_BASE_URL` in Settings page or `agent/.env` |
| FFmpeg fontconfig warning on Windows | Non-fatal — videos still render correctly (exit code 0) |
| Kokoro model files missing | edge-tts fallback activates automatically |
| D-ID rejects logo images | Expected — waveform avatar fallback is always used |
| Scene clips slow on CPU | Optimised: pre-render gradient tile once, loop per scene |

---

## License

MIT — free to use, modify, and distribute.

---

*Built with FastAPI · FFmpeg · Kokoro ONNX · LM Studio · Claude · Groq · Supabase · YouTube Data API v3*
