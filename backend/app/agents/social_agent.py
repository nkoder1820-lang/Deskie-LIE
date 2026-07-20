"""
Social Intelligence Agent
=========================
Analyzes social media presence and detects buying intent signals.
MVP: Infers from business data since Instagram/Facebook APIs require approval.
Uses NVIDIA NIM to analyze any available social text signals.

Output JSON:
{
  "activity_score": 0.0-1.0,
  "customer_intent_score": 0.0-1.0,
  "signals": [str]
}
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Intent signals in social comments
INTENT_KEYWORDS = [
    "price?", "how much", "kitna hai", "cost", "charges",
    "how to book", "appointment", "kaise book", "available",
    "timing", "kab open", "open today", "open on sunday",
    "contact number", "address", "location",
    "do you take", "walk in", "walk-in",
]


class SocialIntelligenceAgent:
    """
    MVP approach: Infer social presence from available data.
    - If website has social links → check activity
    - Use NVIDIA NIM to assess intent from business context
    - Future: Direct Instagram Graph API integration
    """

    def run(
        self,
        business_name: str,
        city: str,
        category: str,
        social_links: Optional[dict] = None,
        review_count: Optional[int] = None,
        rating: Optional[float] = None,
    ) -> dict:
        social_links = social_links or {}

        # Infer activity from available data
        activity_score = self._infer_activity(social_links, review_count, rating)
        intent_score   = self._infer_intent(business_name, category, city, review_count, rating)
        signals        = self._collect_signals(social_links, activity_score, intent_score)

        return {
            "activity_score": round(activity_score, 3),
            "customer_intent_score": round(intent_score, 3),
            "signals": signals,
        }

    def _infer_activity(
        self,
        social_links: dict,
        review_count: Optional[int],
        rating: Optional[float],
    ) -> float:
        """
        Infer social activity without direct API access.
        High reviews + decent rating = likely active social.
        """
        score = 0.0

        # Has social links on website
        if social_links.get("instagram"):
            score += 0.4
        if social_links.get("facebook"):
            score += 0.2

        # Review count proxy (busy business = active online)
        review_count = review_count or 0
        if review_count >= 500:
            score += 0.3
        elif review_count >= 200:
            score += 0.2
        elif review_count >= 50:
            score += 0.1

        # Rating proxy (active responding business)
        if rating and rating >= 4.2:
            score += 0.1

        return min(1.0, score)

    def _infer_intent(
        self,
        business_name: str,
        category: str,
        city: str,
        review_count: Optional[int],
        rating: Optional[float],
    ) -> float:
        """
        Deterministic intent estimate: appointment-driven industries have high
        price/booking question intent; busy businesses more so. (Previously an
        LLM guess — same information, now instant and free.)
        """
        from app.scoring.signals import industry_value

        score = 0.2 + industry_value(category) * 0.6
        if (review_count or 0) >= 200:
            score += 0.1
        if rating and rating >= 4.3:
            score += 0.05
        return min(1.0, score)

    def _collect_signals(self, social_links: dict, activity: float, intent: float) -> list[str]:
        signals = []
        if social_links.get("instagram"):
            signals.append(f"Instagram presence: {social_links['instagram']}")
        if social_links.get("facebook"):
            signals.append(f"Facebook presence: {social_links['facebook']}")
        if activity > 0.6:
            signals.append("High social activity inferred from review volume")
        if intent > 0.6:
            signals.append("High customer buying intent signals expected for this category")
        return signals
