"""
NVIDIA NIM Client
=================
Wraps the OpenAI SDK to use NVIDIA's free-tier inference endpoint.
All agents use this client for structured JSON extraction.

Free-tier friendly: a global concurrency gate keeps parallel agent threads
from stampeding the API, and 429s are retried with exponential backoff.
"""
import json
import logging
import random
import re
import threading
import time

from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None
_client_lock = threading.Lock()

# At most 2 NIM calls in flight across all worker threads (free-tier limit),
# and pace call starts so we stay under the requests-per-minute cap.
_gate = threading.Semaphore(2)
_pace_lock = threading.Lock()
_last_start = 0.0
MIN_INTERVAL = 1.2      # seconds between call starts (~50 RPM ceiling)
MAX_ATTEMPTS = 4


def _pace():
    global _last_start
    with _pace_lock:
        now = time.monotonic()
        wait = _last_start + MIN_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
        _last_start = time.monotonic()


def get_nvidia_client() -> OpenAI:
    global _client
    with _client_lock:
        if _client is None:
            _client = OpenAI(
                base_url=settings.NVIDIA_BASE_URL,
                api_key=settings.NVIDIA_API_KEY,
            )
    return _client


def _parse_json(text: str) -> dict:
    """Parse model output into JSON, tolerating fences, prose and control chars."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    # Take the outermost {...} block in case the model added prose
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text, strict=False)   # strict=False allows raw newlines in strings


def call_nvidia(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1024,
) -> dict:
    """
    Call NVIDIA NIM with a structured JSON response request.
    Returns parsed dict or empty dict on failure.
    """
    if not settings.NVIDIA_API_KEY:
        logger.warning("[NVIDIA] No API key — returning empty result")
        return {}

    client = get_nvidia_client()
    model_name = model or settings.NVIDIA_MODEL

    text = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with _gate:
                _pace()
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            text = (response.choices[0].message.content or "").strip()
            return _parse_json(text)

        except json.JSONDecodeError as e:
            logger.error(f"[NVIDIA] JSON parse error: {e} — raw: {text[:200]}")
            return {}
        except Exception as e:
            msg = str(e)
            retryable = "429" in msg or "Too Many Requests" in msg or "timeout" in msg.lower() \
                or "503" in msg or "502" in msg
            if retryable and attempt < MAX_ATTEMPTS:
                delay = (2 ** attempt) + random.uniform(0, 1.5)
                logger.warning(f"[NVIDIA] {msg[:120]} — retry {attempt}/{MAX_ATTEMPTS - 1} in {delay:.1f}s")
                time.sleep(delay)
                continue
            logger.error(f"[NVIDIA] API call failed: {e}")
            return {}
    return {}
