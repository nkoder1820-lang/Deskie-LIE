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

        # One LLM call produces both the report and the sendable outreach
        combined = self._generate_ai_report(business, scored_lead, all_evidence, value_result)
        ai_report = combined
        fallback = self._fallback_outreach(business, scored_lead)
        outreach = {
            "subject": str(combined.get("outreach_subject") or fallback["subject"])[:200],
            "email": str(combined.get("outreach_email") or fallback["email"]),
            "whatsapp": str(combined.get("whatsapp_message") or fallback["whatsapp"]),
        }

        return {
            "summary": ai_report.get("summary", self._default_summary(business, scored_lead)),
            "top_reasons": ai_report.get("top_reasons", scored_lead.pain_breakdown.evidence[:3]),
            "pain_points": ai_report.get("pain_points", []),
            "recommended_pitch": ai_report.get(
                "recommended_pitch",
                self._default_pitch(business, value_result)
            ),
            "outreach_subject": outreach["subject"],
            "outreach_email": outreach["email"],
            "whatsapp_message": outreach["whatsapp"],
            "evidence": all_evidence,
        }

    # ── Per-decision-maker outreach drafts ──────────────────────────────────
    def generate_poc_outreach(
        self, business: dict, qualification_reason: str, poc_contacts: list[dict],
        pain_evidence: list[str],
    ) -> list[dict]:
        """
        Personalized-by-name outreach for each decision maker found.
        One batched LLM call covers up to 3 people; anyone left over (or if
        the call fails) gets a deterministic template with their name/title
        filled in, so every PoC always has sendable copy.
        """
        if not poc_contacts:
            return []

        top = poc_contacts[:3]
        drafts_by_name = self._ai_poc_outreach(business, qualification_reason, top, pain_evidence)

        results = []
        for poc in poc_contacts:
            name = poc["name"]
            ai_draft = drafts_by_name.get(name.lower())
            if ai_draft and ai_draft.get("email_body"):
                results.append({
                    "name": name,
                    "title": poc.get("title", ""),
                    "email_subject": str(ai_draft.get("email_subject") or "")[:200],
                    "email_body": ai_draft.get("email_body", ""),
                    "whatsapp_message": ai_draft.get("whatsapp_message", ""),
                })
            else:
                results.append(self._fallback_poc_outreach(business, poc))
        return results

    def _ai_poc_outreach(
        self, business: dict, qualification_reason: str, pocs: list[dict], pain_evidence: list[str],
    ) -> dict:
        system = """You write short, high-converting cold outreach for Deskie, an AI phone receptionist that answers every call 24/7, books appointments, and captures leads a business would otherwise miss.
You will be given a business and a list of named decision makers at that business. Write ONE personalized draft PER PERSON, addressed to them by first name.
Return ONLY valid JSON:
{
  "drafts": [
    {
      "name": "<exact name as given>",
      "email_subject": "<under 60 chars>",
      "email_body": "<80-120 words. Open with their first name. Reference their role and one specific observation about the business. 1 sentence on cost of missed calls. 1 sentence on what Deskie does. Single CTA for a 10-min call. Sign off 'The Deskie Team'. No placeholders — sendable as-is.>",
      "whatsapp_message": "<under 60 words, casual, opens with first name, ends with a soft question>"
    }
  ]
}
Never invent facts not present in the evidence. Return ONLY the JSON."""

        people_text = "\n".join(f"- {p['name']} — {p.get('title', 'Decision maker')}" for p in pocs)
        user = f"""Business: {business.get('name')}
Industry: {(business.get('category') or '').replace('_', ' ')}
City: {business.get('city')}
Deskie fit reason: {qualification_reason}
Evidence: {'; '.join(str(p) for p in pain_evidence[:4]) or 'n/a'}

Decision makers to write for:
{people_text}"""

        result = call_nvidia(system, user, max_tokens=900, temperature=0.4)
        drafts = (result or {}).get("drafts", [])
        return {
            str(d.get("name", "")).lower(): d
            for d in drafts if isinstance(d, dict) and d.get("name")
        }

    def _fallback_poc_outreach(self, business: dict, poc: dict) -> dict:
        first_name = poc["name"].split()[0]
        name = business.get("name", "your business")
        city = business.get("city", "")
        category = (business.get("category") or "business").replace("_", " ")
        title = poc.get("title", "the team")
        return {
            "name": poc["name"],
            "title": poc.get("title", ""),
            "email_subject": f"Missed calls at {name}?"[:78],
            "email_body": (
                f"Hi {first_name},\n\n"
                f"As {title} at {name}, you're probably the one who feels it when the phone rings and no one "
                f"can pick up. Every unanswered call in {category} in {city} is usually a customer who books "
                f"with the next place they find.\n\n"
                f"Deskie is an AI receptionist that answers every call 24/7, books appointments straight into "
                f"your calendar, and sends you a summary of each conversation.\n\n"
                f"Worth a 10-minute call this week to see how many calls {name} might be missing?\n\n"
                f"Best,\nThe Deskie Team"
            ),
            "whatsapp_message": (
                f"Hi {first_name}! 👋 Saw you're {title.lower() if title else 'involved'} at {name}. "
                f"We help {category} in {city} stop losing customers to missed calls — our AI receptionist "
                f"answers 24/7 and books appointments automatically. Worth a quick chat?"
            ),
        }

    def _fallback_outreach(self, business: dict, scored: ScoredLead) -> dict:
        name = business.get("name", "your business")
        city = business.get("city", "")
        category = (business.get("category") or "business").replace("_", " ")
        reason = scored.qualification_reason or "many inquiries still start with a phone call"
        subject = f"Missed calls at {name}?"[:78]
        email = (
            f"Hi {name} team,\n\n"
            f"I came across {name} while researching {category} in {city} — "
            f"{reason[0].lower() + reason[1:] if reason else ''}\n\n"
            f"Every unanswered call is usually a customer who books with the next one they find. "
            f"Deskie is an AI receptionist that answers every call 24/7, books appointments directly into "
            f"your calendar, and sends you a summary of each conversation.\n\n"
            f"Would you be open to a 10-minute call this week to see how many calls you might be missing?\n\n"
            f"Best,\nThe Deskie Team"
        )
        whatsapp = (
            f"Hi {name} team! 👋 We help {category} in {city} stop losing customers to "
            f"missed calls — our AI receptionist answers 24/7 and books appointments automatically. "
            f"Curious how many calls you might be missing after hours?"
        )
        return {"subject": subject, "email": email, "whatsapp": whatsapp}

    def _generate_ai_report(
        self,
        business: dict,
        scored: ScoredLead,
        evidence: dict,
        value_result: dict,
    ) -> dict:

        system = """You are a sales intelligence analyst for Deskie, an AI phone receptionist that answers every call 24/7, books appointments, and captures leads a business would otherwise miss.
Write a lead intelligence report AND ready-to-send outreach. Return ONLY valid JSON:
{
  "summary": "<2-3 sentence business overview and why Deskie fits>",
  "top_reasons": ["<reason 1>", "<reason 2>", "<reason 3>"],
  "pain_points": ["<specific pain 1>", "<specific pain 2>", "<specific pain 3>"],
  "recommended_pitch": "<One powerful sales pitch sentence tailored to this specific business>",
  "outreach_subject": "<email subject, under 60 chars, specific to this business, no clickbait>",
  "outreach_email": "<cold email body, 90-130 words, plain text. Structure: 1 personalized observation about THIS business (use the evidence), 1-2 sentences on the cost of missed calls in their industry, 1 sentence on what Deskie does, single clear CTA asking for a 10-minute call. Sign off as 'The Deskie Team'. No placeholders like [Name] — must be sendable as-is.>",
  "whatsapp_message": "<WhatsApp message, under 65 words, casual but professional, same observation, ends with a soft question. No placeholders.>"
}

Guidelines:
- Be specific, not generic — reference actual data points (ratings, hours, category)
- pain_points and outreach must be specific to THIS business
- Never invent facts not present in the evidence
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

        result = call_nvidia(system, user, max_tokens=1200, temperature=0.3)
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
