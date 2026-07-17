"""
Review Intelligence Agent
=========================
Fetches Google reviews and extracts call/booking pain signals using
keyword matching + NVIDIA NIM analysis.

Output JSON:
{
  "review_sentiment": "positive" | "neutral" | "negative",
  "call_pain_score": 0.0-1.0,
  "missed_call_complaints_found": bool,
  "customer_complaints": [str],
  "evidence": [str]
}
"""
import logging
import re
from typing import Optional

import httpx
from app.agents.nvidia_client import call_nvidia
from app.scoring.signals import CALL_PAIN_KEYWORDS
from app.config import settings

logger = logging.getLogger(__name__)


class ReviewIntelligenceAgent:

    def run(self, place_id: Optional[str], business_name: str) -> dict:
        """
        Analyze reviews for call/booking pain signals.
        """
        reviews = []

        if place_id and settings.GOOGLE_PLACES_API_KEY:
            reviews = self._fetch_google_reviews(place_id)

        if not reviews:
            logger.info(f"[ReviewAgent] No reviews fetched for {business_name}, using keyword defaults")
            return self._empty_result()

        return self._analyze_reviews(reviews, business_name)

    def _fetch_google_reviews(self, place_id: str) -> list[str]:
        """Fetch top reviews from Google Places API."""
        params = {
            "place_id": place_id,
            "fields": "reviews",
            "key": settings.GOOGLE_PLACES_API_KEY,
            "language": "en",
        }
        try:
            resp = httpx.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            reviews_raw = data.get("result", {}).get("reviews", [])
            return [r.get("text", "") for r in reviews_raw if r.get("text")]
        except Exception as e:
            logger.warning(f"[ReviewAgent] Could not fetch reviews for {place_id}: {e}")
            return []

    def _analyze_reviews(self, reviews: list[str], business_name: str) -> dict:
        """Keyword scan + AI analysis."""
        combined_text = "\n".join(reviews)

        # Keyword scan for call/booking pain
        pain_hits = []
        combined_lower = combined_text.lower()
        for keyword in CALL_PAIN_KEYWORDS:
            if keyword in combined_lower:
                # Find the sentence containing this keyword
                sentences = re.split(r'[.!?]', combined_lower)
                for s in sentences:
                    if keyword in s and len(s.strip()) > 10:
                        pain_hits.append(s.strip()[:200])
                        break

        # Remove duplicates
        pain_hits = list(dict.fromkeys(pain_hits))[:10]
        call_pain_score = min(1.0, len(pain_hits) / 5.0)   # 5+ hits = max score

        # AI analysis for deeper extraction
        ai_result = self._ai_analyze(combined_text[:3000], business_name)

        complaints = ai_result.get("customer_complaints", [])
        evidence   = ai_result.get("evidence", pain_hits)
        sentiment  = ai_result.get("review_sentiment", "neutral")
        missed_call = ai_result.get("missed_call_complaints_found", False)

        # AI may give a better call_pain_score — take the max
        ai_pain = ai_result.get("call_pain_score", 0.0)
        final_pain = max(call_pain_score, ai_pain)

        return {
            "review_sentiment": sentiment,
            "call_pain_score": round(final_pain, 3),
            "missed_call_complaints_found": missed_call,
            "customer_complaints": complaints,
            "evidence": evidence[:5],
        }

    def _ai_analyze(self, reviews_text: str, business_name: str) -> dict:
        """Use NVIDIA NIM to extract pain signals from review text."""
        system = """You are a customer experience analyst. Analyze these business reviews and return ONLY valid JSON:
{
  "review_sentiment": "<positive|neutral|negative>",
  "call_pain_score": <float 0.0-1.0>,
  "missed_call_complaints_found": <bool>,
  "customer_complaints": [<list of specific complaint strings>],
  "evidence": [<list of exact review snippets that mention phone/call/booking issues>]
}

call_pain_score guidance:
- 0.0: No phone/booking complaints
- 0.3: Minor mention of calling/waiting
- 0.6: Multiple complaints about phone response, booking, or no-answer
- 1.0: Consistent pattern of missed calls, no response, booking failures
Pay very close attention to any mention of unanswered calls, busy lines, or poor phone service. Set missed_call_complaints_found to true if ANY exist.

Return ONLY the JSON object."""

        user = f"""Business: {business_name}
Reviews:
{reviews_text}"""

        result = call_nvidia(system, user, max_tokens=512)
        return result if result else {}

    def _empty_result(self) -> dict:
        return {
            "review_sentiment": "unknown",
            "call_pain_score": 0.0,
            "missed_call_complaints_found": False,
            "customer_complaints": [],
            "evidence": [],
        }
