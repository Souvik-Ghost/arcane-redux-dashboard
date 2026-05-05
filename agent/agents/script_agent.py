"""
agents/script_agent.py — AI-powered video script generator.

LLM priority: LM Studio (local) -> Groq (free) -> OpenRouter (free) -> Gemini (free) -> OpenAI -> Claude
Produces:
  - Optimised YouTube title (A/B variants)
  - Hook (first 30 seconds)
  - Scene-by-scene narrative script with visual directions
  - Call-to-action
  - SEO metadata (description, tags)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from utils.logger import logger


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class Scene:
    index: int
    narration: str
    visual_direction: str
    duration_secs: int = 30


@dataclass
class VideoScript:
    title: str
    title_variants: list[str]
    hook: str
    scenes: list[Scene]
    cta: str
    description: str
    tags: list[str]
    thumbnail_concept: str
    total_duration_estimate: int = 0

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "title_variants": self.title_variants,
            "hook": self.hook,
            "scenes": [
                {
                    "index": s.index,
                    "narration": s.narration,
                    "visual_direction": s.visual_direction,
                    "duration_secs": s.duration_secs,
                }
                for s in self.scenes
            ],
            "cta": self.cta,
            "description": self.description,
            "tags": self.tags,
            "thumbnail_concept": self.thumbnail_concept,
            "total_duration_estimate": self.total_duration_estimate,
        }

    def full_narration(self) -> str:
        parts = [self.hook]
        for scene in self.scenes:
            parts.append(scene.narration)
        parts.append(self.cta)
        return "\n\n".join(parts)


# ── LLM caller — multi-provider free-first chain ──────────────────────────────

def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 8192) -> str:
    """
    Call the best available LLM.
    Priority order (free/local first):
      1. LM Studio   -- FREE, fully local, zero cost (preferred)
      2. Groq        -- FREE, 14,400 req/day (console.groq.com)
      3. OpenRouter  -- FREE models available (openrouter.ai)
      4. Gemini      -- FREE tier, 1,500 req/day (aistudio.google.com)
      5. OpenAI      -- PAID (platform.openai.com)
      6. Claude      -- PAID (console.anthropic.com)
    """

    # 1. LM Studio -- local, free, no rate limits
    lm_url = config.LM_STUDIO_BASE_URL
    lm_key = config.LM_STUDIO_API_KEY
    lm_model = config.LM_STUDIO_MODEL
    if lm_url and lm_key:
        try:
            import re as _re
            from openai import OpenAI
            client = OpenAI(api_key=lm_key, base_url=lm_url)
            resp = client.chat.completions.create(
                model=lm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=min(max_tokens, 8000),
                temperature=0.7,
                # Disable Qwen3 thinking mode so tokens go to the actual response
                extra_body={"enable_thinking": False},
            )
            raw = resp.choices[0].message.content or ""
            # Strip any residual <think>…</think> blocks (safety net)
            clean = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL).strip()
            if not clean:
                raise ValueError("LM Studio returned empty response after stripping think blocks")
            logger.info(f"Script generated via LM Studio ({lm_model})")
            return clean
        except Exception as e:
            logger.warning(f"LM Studio failed ({e}), trying Groq...")

    # 2. Groq -- completely free, no credit card needed
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key and "PASTE" not in groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=min(max_tokens, 8000),
                temperature=0.7,
            )
            logger.info("Script generated via Groq (free)")
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning(f"Groq failed ({e}), trying OpenRouter...")

    # 3. OpenRouter -- free models: meta-llama/llama-3.3-70b-instruct:free
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_key and "PASTE" not in openrouter_key:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
            )
            resp = client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=min(max_tokens, 8000),
            )
            logger.info("Script generated via OpenRouter (free)")
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning(f"OpenRouter failed ({e}), trying Gemini...")

    # 4. Gemini -- free tier (1,500 req/day, resets daily)
    if config.GEMINI_API_KEY and "PASTE" not in config.GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=full_prompt,
            )
            logger.info("Script generated via Gemini (free)")
            return resp.text
        except Exception as e:
            logger.warning(f"Gemini failed ({e}), trying OpenAI...")

    # 5. OpenAI -- paid (gpt-4o-mini is cheapest ~$0.001/script)
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key and "PASTE" not in openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=min(max_tokens, 8000),
            )
            logger.info("Script generated via OpenAI (gpt-4o-mini)")
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning(f"OpenAI failed ({e}), trying Claude...")

    # 6. Claude -- paid fallback
    if config.ANTHROPIC_API_KEY and "PASTE" not in config.ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            logger.info("Script generated via Claude")
            return message.content[0].text
        except Exception as e:
            logger.warning(f"Claude failed: {e}")

    raise RuntimeError(
        "No LLM available! Add at least one free key to agent/.env:\n"
        "  GROQ_API_KEY     -> console.groq.com (free, recommended)\n"
        "  OPENROUTER_API_KEY -> openrouter.ai (free models available)\n"
        "  GEMINI_API_KEY   -> aistudio.google.com (free tier)"
    )


# ── LM Studio pre-processing (zero-cost local) ────────────────────────────────

def _lm_studio_preprocess(topic: str, context: dict) -> str:
    try:
        prompt = f"""Analyze this YouTube content context and extract compelling angles.

Topic: {topic}
Niche: {config.CHANNEL_NICHE}
Context: {json.dumps(context, indent=2)[:1000]}

Return JSON with:
- top_3_angles: list of 3 unique content angles
- strongest_hook: most compelling opening statement
- audience_pain_points: top 3 pain points to address
- key_insights: 5 bullet points the video must cover

Return ONLY valid JSON."""

        resp = httpx.post(
            f"{config.LM_STUDIO_BASE_URL}/chat/completions",
            json={
                "model": config.LM_STUDIO_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.7,
            },
            timeout=60,
        )
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.debug(f"LM Studio pre-processing skipped: {e}")
        return "{}"


# ── Script generation ─────────────────────────────────────────────────────────

SCRIPT_SYSTEM_PROMPT = """You are a senior YouTube strategist and scriptwriter specialising in
faceless AI-narrated educational content. Your scripts are delivered by a virtual AI avatar
character named {avatar_name} who is the host of the channel.

Channel: {niche}
Tone: {tone}
Avatar host: {avatar_name}

Your scripts must:
1. Open with an irresistible hook in the FIRST 15 SECONDS
2. Use the Problem -> Agitation -> Solution framework
3. Include specific scene-by-scene visual directions
4. Have natural, conversational narration
5. End with a strong CTA

IMPORTANT: Return ONLY a valid JSON object -- no markdown, no explanation:
{{
  "title": "Primary optimised title",
  "title_variants": ["variant 1", "variant 2", "variant 3"],
  "hook": "Full opening hook narration (60-90 words)",
  "scenes": [
    {{
      "index": 1,
      "narration": "What the avatar says",
      "visual_direction": "Stock footage/animation instructions",
      "duration_secs": 45
    }}
  ],
  "cta": "Full closing CTA narration (40-60 words)",
  "description": "Full YouTube description (200-300 words)",
  "tags": ["tag1", "tag2"],
  "thumbnail_concept": "Visual instructions for thumbnail"
}}"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def generate_script(
    topic: str,
    context: dict | None = None,
    target_duration_mins: int = 10,
) -> VideoScript:
    """Generate a complete video script using best available LLM."""
    context = context or {}
    logger.info(f"Generating script for: '{topic}'")

    # Optional LM Studio pre-processing (zero cost local)
    preprocess_json = _lm_studio_preprocess(topic, context)
    try:
        preprocess_data = json.loads(preprocess_json)
    except json.JSONDecodeError:
        preprocess_data = {}

    scene_count = max(5, target_duration_mins - 2)

    system_prompt = SCRIPT_SYSTEM_PROMPT.format(
        avatar_name=config.AVATAR_NAME,
        niche=config.CHANNEL_NICHE,
        tone=config.CHANNEL_TONE,
    )

    user_prompt = f"""Create a complete YouTube script for this topic:

TOPIC: {topic}
TARGET DURATION: {target_duration_mins} minutes ({scene_count} main scenes)
NICHE: {config.CHANNEL_NICHE}

STRATEGIC CONTEXT:
{json.dumps(preprocess_data, indent=2) if preprocess_data else "Use your expertise."}

ADDITIONAL CONTEXT:
{json.dumps(context, indent=2) if context else "None"}

The avatar {config.AVATAR_NAME} is delivering this content.
Generate exactly {scene_count} scenes. Each scene narration: 80-150 words.
Return ONLY valid JSON -- no markdown fences."""

    raw = _call_llm(system_prompt, user_prompt)

    # Strip markdown fences if present
    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    json_str = json_match.group(1) if json_match else raw.strip()

    data = json.loads(json_str)

    scenes = [
        Scene(
            index=s["index"],
            narration=s["narration"],
            visual_direction=s["visual_direction"],
            duration_secs=s.get("duration_secs", 45),
        )
        for s in data.get("scenes", [])
    ]

    total_duration = sum(s.duration_secs for s in scenes) + 90

    script = VideoScript(
        title=data["title"],
        title_variants=data.get("title_variants", []),
        hook=data["hook"],
        scenes=scenes,
        cta=data["cta"],
        description=data["description"],
        tags=data.get("tags", [])[:15],
        thumbnail_concept=data.get("thumbnail_concept", ""),
        total_duration_estimate=total_duration,
    )

    logger.success(f"Script ready: '{script.title}' (~{total_duration // 60}min)")
    return script


def generate_community_post_copy(post_type: str, topic: str, channel_context: str = "") -> dict:
    """Generate copy for a YouTube Community post."""
    logger.info(f"Generating community post ({post_type}): '{topic}'")

    prompts = {
        "text": f"Write an engaging YouTube Community text post about: {topic}\nNiche: {config.CHANNEL_NICHE}.\nReturn JSON: {{\"text\": \"...\", \"emoji_opener\": \"...\"}}",
        "poll": f"Create a YouTube Community poll about: {topic}\nNiche: {config.CHANNEL_NICHE}.\nReturn JSON: {{\"question\": \"...\", \"options\": [\"opt1\", \"opt2\", \"opt3\", \"opt4\"]}}",
        "quiz": f"Create a YouTube quiz about: {topic}\nNiche: {config.CHANNEL_NICHE}.\nReturn JSON: {{\"question\": \"...\", \"options\": [\"opt1\",\"opt2\",\"opt3\",\"opt4\"], \"correct_index\": 0, \"explanation\": \"...\"}}",
    }

    raw = _call_llm(
        "You are a YouTube community manager.",
        prompts.get(post_type, prompts["text"]),
        max_tokens=512,
    )
    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    json_str = json_match.group(1) if json_match else raw.strip()
    return json.loads(json_str)
