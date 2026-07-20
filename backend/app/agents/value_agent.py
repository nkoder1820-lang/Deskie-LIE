"""
Business Value Agent
====================
Estimates whether the business has both the need and ability to pay for Deskie.
Uses NVIDIA NIM for reasoning, combined with deterministic industry/location data.

Output JSON:
{
  "business_value_score": 0.0-1.0,
  "estimated_willingness_to_pay": "low" | "medium" | "high",
  "customer_value_score": 0.0-1.0,
  "receptionist_hiring_signal": bool,
  "is_hiring": bool,
  "is_expanding": bool,
  "recent_growth_score": 0.0-1.0,
  "reasoning": str
}
"""
import logging
from typing import Optional
from app.scoring.signals import industry_value, location_tier

logger = logging.getLogger(__name__)


class BusinessValueAgent:

    def run(
        self,
        business_name: str,
        category: str,
        city: str,
        rating: Optional[float] = None,
        review_count: Optional[int] = None,
        website: Optional[str] = None,
        opening_hours: Optional[dict] = None,
    ) -> dict:

        # Base scores from deterministic maps (free-text industries supported)
        industry_val = industry_value(category)
        location_val = location_tier(city)

        # Review-based growth proxy
        recent_growth = self._estimate_growth(review_count, rating)

        # Deterministic only — the old AI call here guessed hiring/expansion
        # with no real data (the enricher agent covers those with actual
        # search results), so it was cut to save an LLM call per lead.
        ai_result: dict = {}

        # Merge
        base_value = (industry_val * 0.5) + (location_val * 0.3) + (recent_growth * 0.2)

        return {
            "business_value_score": round(
                ai_result.get("business_value_score", base_value), 3
            ),
            "estimated_willingness_to_pay": ai_result.get(
                "estimated_willingness_to_pay",
                self._default_wtp(industry_val, location_val)
            ),
            "customer_value_score": round(industry_val * location_val, 3),
            "receptionist_hiring_signal": ai_result.get("receptionist_hiring_signal", False),
            "is_hiring": ai_result.get("is_hiring", False),
            "is_expanding": ai_result.get("is_expanding", False),
            "recent_growth_score": round(recent_growth, 3),
            "reasoning": ai_result.get(
                "reasoning",
                f"{category.replace('_', ' ').title()} in {city} — estimated value {base_value:.0%}"
            ),
        }

    def _estimate_growth(self, review_count: Optional[int], rating: Optional[float]) -> float:
        """Infer growth from review volume and rating."""
        score = 0.0
        review_count = review_count or 0
        if review_count >= 1000:
            score += 0.6
        elif review_count >= 500:
            score += 0.4
        elif review_count >= 100:
            score += 0.25
        else:
            score += 0.1

        if rating and rating >= 4.5:
            score += 0.3
        elif rating and rating >= 4.0:
            score += 0.2
        elif rating and rating >= 3.5:
            score += 0.1

        return min(1.0, score)

    def _default_wtp(self, industry_val: float, location_val: float) -> str:
        score = (industry_val + location_val) / 2
        if score >= 0.8:
            return "high"
        elif score >= 0.6:
            return "medium"
        else:
            return "low"
