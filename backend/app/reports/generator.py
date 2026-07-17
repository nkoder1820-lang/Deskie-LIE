"""
Lead Report Generator
======================
Uses NVIDIA NIM to generate a human-readable lead intelligence report
from all research + scoring data.

Output:
{
  "summary": str,
  "top_reasons": [str],
  "pain_points": [str],
  "recommended_pitch": str,
  "evidence": dict
}
"""
import logging
from app.agents.nvidia_client import call_nvidia
from app.scoring.engine import ScoredLead

logger = logging.getLogger(__name__)


class ReportGenerator:

    def generate(
        self,
        business: dict,
        scored_lead: ScoredLead,
        website_result: dict,
        review_result: dict,
        social_result: dict,
        value_result: dict,
    ) -> dict:

        # Collect all evidence for the report
        all_evidence = {
            "pain": scored_lead.pain_breakdown.evidence,
            "value": scored_lead.value_breakdown.evidence,
            "digital": scored_lead.digital_breakdown.evidence,
            "timing": scored_lead.timing_breakdown.evidence,
            "reviews": review_result.get("evidence", []),
            "website_pain": website_result.get("pain_signals", []),
        }

        ai_report = self._generate_ai_report(business, scored_lead, all_evidence, value_result)

        return {
            "summary": ai_report.get("summary", self._default_summary(business, scored_lead)),
            "top_reasons": ai_report.get("top_reasons", scored_lead.pain_breakdown.evidence[:3]),
            "pain_points": ai_report.get("pain_points", []),
            "recommended_pitch": ai_report.get(
                "recommended_pitch",
                self._default_pitch(business, value_result)
            ),
            "evidence": all_evidence,
        }

    def _generate_ai_report(
        self,
        business: dict,
        scored: ScoredLead,
        evidence: dict,
        value_result: dict,
    ) -> dict:

        system = """You are a sales intelligence analyst for Deskie, an AI phone receptionist platform for Indian businesses.
Write a lead intelligence report and return ONLY valid JSON:
{
  "summary": "<2-3 sentence business overview and why Deskie fits>",
  "top_reasons": ["<reason 1>", "<reason 2>", "<reason 3>"],
  "pain_points": ["<specific pain 1>", "<specific pain 2>", "<specific pain 3>"],
  "recommended_pitch": "<One powerful sales pitch sentence tailored to this specific business>"
}

Guidelines:
- Be specific, not generic
- Reference actual data points (ratings, hours, category)
- The pitch should feel personalized, not like a template
- pain_points should be specific to THIS business
- Deskie solves: missed calls, after-hours inquiries, appointment booking via AI voice
Return ONLY the JSON."""

        user = f"""Business: {business.get('name')}
Category: {business.get('category', '').replace('_', ' ')}
City: {business.get('city')}
Rating: {business.get('rating')} ({business.get('review_count')} reviews)
Website: {business.get('website') or 'None'}
Deskie Score: {scored.final_score}/100 ({scored.priority})

Score Breakdown:
- Pain Score: {scored.pain_score}/100
- Business Value: {scored.business_value_score}/100
- Digital Adoption: {scored.digital_score}/100
- Buying Timing: {scored.timing_score}/100

Evidence:
Pain signals: {', '.join(evidence.get('pain', [])[:3])}
Review signals: {', '.join(evidence.get('reviews', [])[:3])}
Website signals: {', '.join(evidence.get('website_pain', [])[:3])}
Willingness to pay: {value_result.get('estimated_willingness_to_pay', 'unknown')}
Value reasoning: {value_result.get('reasoning', 'N/A')}"""

        result = call_nvidia(system, user, max_tokens=768, temperature=0.3)
        return result if result else {}

    def _default_summary(self, business: dict, scored: ScoredLead) -> str:
        return (
            f"{business.get('name')} is a {business.get('category', '').replace('_', ' ')} "
            f"in {business.get('city')} with a Deskie Opportunity Score of {scored.final_score}/100. "
            f"Priority: {scored.priority}."
        )

    def _default_pitch(self, business: dict, value_result: dict) -> str:
        wtp = value_result.get("estimated_willingness_to_pay", "medium")
        return (
            f"You're already investing in patient acquisition — "
            f"Deskie ensures every incoming call is answered, "
            f"every appointment is captured, 24/7."
        )
