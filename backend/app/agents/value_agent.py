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
from app.agents.nvidia_client import call_nvidia
from app.scoring.signals import INDUSTRY_VALUE_MAP, LOCATION_TIER_MAP

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

        # Base scores from deterministic maps
        industry_val = INDUSTRY_VALUE_MAP.get(category, INDUSTRY_VALUE_MAP["default"])
        location_val = LOCATION_TIER_MAP.get(city, LOCATION_TIER_MAP["default"])

        # Review-based growth proxy
        recent_growth = self._estimate_growth(review_count, rating)

        # AI reasoning for deeper signals
        ai_result = self._ai_assess(
            business_name, category, city, rating, review_count, website, opening_hours
        )

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

    def _ai_assess(
        self,
        business_name: str,
        category: str,
        city: str,
        rating: Optional[float],
        review_count: Optional[int],
        website: Optional[str],
        opening_hours: Optional[dict],
    ) -> dict:
        """Use NVIDIA NIM to estimate business value and hiring signals."""
        hours_text = ""
        if opening_hours:
            hours_text = "\n".join(opening_hours.get("weekday_text", []))

        system = """You are a B2B SaaS sales intelligence analyst for an AI phone receptionist product in India.
Analyze the business and return ONLY valid JSON:
{
  "business_value_score": <float 0.0-1.0>,
  "estimated_willingness_to_pay": "<low|medium|high>",
  "receptionist_hiring_signal": <bool>,
  "is_hiring": <bool>,
  "is_expanding": <bool>,
  "reasoning": "<2 sentences max>"
}

Scoring context:
- Dental clinics in Tier-1 cities: high value (₹3k-₹15k per customer)
- business_value_score 1.0 = ideal Deskie prospect (high revenue per call, many missed calls possible)
- receptionist_hiring_signal = likely need a receptionist based on hours/size
- Assume businesses with 500+ reviews and extended hours likely need call handling help
Return ONLY the JSON."""

        user = f"""Business: {business_name}
Category: {category}
City: {city}
Rating: {rating} ({review_count} reviews)
Has Website: {'Yes' if website else 'No'}
Hours:
{hours_text or 'Not available'}"""

        result = call_nvidia(system, user, max_tokens=384)
        return result if result else {}

    def _default_wtp(self, industry_val: float, location_val: float) -> str:
        score = (industry_val + location_val) / 2
        if score >= 0.8:
            return "high"
        elif score >= 0.6:
            return "medium"
        else:
            return "low"
