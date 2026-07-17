"""
NVIDIA NIM Client
=================
Wraps the OpenAI SDK to use NVIDIA's free-tier inference endpoint.
All agents use this client for structured JSON extraction.
"""
import json
import logging
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_nvidia_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=settings.NVIDIA_BASE_URL,
            api_key=settings.NVIDIA_API_KEY,
        )
    return _client


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

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        return json.loads(text)

    except json.JSONDecodeError as e:
        logger.error(f"[NVIDIA] JSON parse error: {e} — raw: {text[:200]}")
        return {}
    except Exception as e:
        logger.error(f"[NVIDIA] API call failed: {e}")
        return {}
