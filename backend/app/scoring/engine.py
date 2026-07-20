"""
Scoring Engine
==============
Deterministic, explainable lead scoring.
NO AI used here — pure math with evidence tracking.

Final Score = Pain*0.40 + Value*0.25 + Digital*0.20 + Timing*0.15
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.scoring.signals import (
    PAIN_SIGNALS, VALUE_SIGNALS, DIGITAL_SIGNALS, TIMING_SIGNALS,
    INDUSTRY_VALUE_MAP, LOCATION_TIER_MAP, CALL_PAIN_KEYWORDS,
    industry_value, location_tier,
    has_extended_hours, is_7_days
)

logger = logging.getLogger(__name__)


# ── Output Types ────────────────────────────────────────────────────────────
def ev(text: str, url: Optional[str] = None, label: Optional[str] = None) -> dict:
    """
    One evidence bullet. `url` is a REAL link backing the claim (their
    website, Google Maps reviews, an actual job posting) — never a guess,
    left None when we have nothing concrete to point at. This is what lets
    a cold caller verify a claim before repeating it to a prospect.
    """
    return {"text": text, "source_url": url, "source_label": label}


@dataclass
class ScoreBreakdown:
    """One dimension of scoring with sub-scores and evidence."""
    score: float                        # 0-100
    sub_scores: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)   # [{"text","source_url","source_label"}]


@dataclass
class ScoredLead:
    pain_score: float
    pain_breakdown: ScoreBreakdown
    business_value_score: float
    value_breakdown: ScoreBreakdown
    digital_score: float
    digital_breakdown: ScoreBreakdown
    timing_score: float
    timing_breakdown: ScoreBreakdown
    final_score: float
    priority: str                       # HOT | HIGH | MEDIUM | LOW
    pitch_angle: str = ""
    qualification_reason: str = ""
    pitch_source: Optional[dict] = None  # {"label": str, "url": str} — real evidence link, when we have one


# ── Classifier ──────────────────────────────────────────────────────────────
def classify_priority(score: float) -> str:
    if score >= 82:
        return "HOT"
    elif score >= 68:
        return "HIGH"
    elif score >= 50:
        return "MEDIUM"
    else:
        return "LOW"


# ── Main Engine ─────────────────────────────────────────────────────────────
class ScoringEngine:
    """
    Computes the Deskie Opportunity Score from structured research data.

    Inputs come from:
      - business: raw business fields (rating, review_count, opening_hours, etc.)
      - website_result: output from WebsiteIntelligenceAgent
      - review_result:  output from ReviewIntelligenceAgent
      - social_result:  output from SocialIntelligenceAgent
      - value_result:   output from BusinessValueAgent
    """

    def score(
        self,
        business: dict,
        website_result: Optional[dict] = None,
        review_result: Optional[dict] = None,
        social_result: Optional[dict] = None,
        value_result: Optional[dict] = None,
        enricher_result: Optional[dict] = None,
    ) -> ScoredLead:

        website = website_result or {}
        review  = review_result or {}
        social  = social_result or {}
        value   = value_result or {}
        enricher = enricher_result or {}

        pain     = self._score_pain(business, website, review, value, enricher)
        bv       = self._score_business_value(business, value)
        digital  = self._score_digital(business, website, social)
        timing   = self._score_timing(social, value, enricher)

        final = (
            pain.score    * 0.40 +
            bv.score      * 0.25 +
            digital.score * 0.20 +
            timing.score  * 0.15
        )
        final = min(100.0, max(0.0, final))

        pitch_angle, qual_reason, pitch_source = self._classify_pitch_angle(business, website, review, enricher, pain)

        return ScoredLead(
            pain_score=round(pain.score, 2),
            pain_breakdown=pain,
            business_value_score=round(bv.score, 2),
            value_breakdown=bv,
            digital_score=round(digital.score, 2),
            digital_breakdown=digital,
            timing_score=round(timing.score, 2),
            timing_breakdown=timing,
            final_score=round(final, 2),
            priority=classify_priority(final),
            pitch_angle=pitch_angle,
            qualification_reason=qual_reason,
            pitch_source=pitch_source,
        )

    def _classify_pitch_angle(
        self, business: dict, website: dict, review: dict, enricher: dict, pain: ScoreBreakdown
    ) -> tuple[str, str, Optional[dict]]:
        if review.get("missed_call_complaints_found"):
            source = {"label": "See the reviews on Google Maps", "url": business["maps_url"]} \
                if business.get("maps_url") else None
            return (
                "🔥 Missed Calls",
                "Explicit complaints in Google reviews about missed calls or long phone waits.",
                source,
            )
        if enricher.get("runs_google_ads") and not website.get("booking_available"):
            ads = enricher.get("ads_sources") or []
            source = {"label": f"View the ad — {ads[0]['title']}", "url": ads[0]["url"]} if ads else None
            return (
                "💰 Wasting Ad Budget",
                "Running Google ads but has no online booking system to capture leads.",
                source,
            )
        if enricher.get("is_hiring_receptionist") or enricher.get("is_hiring_any"):
            jobs = enricher.get("hiring_sources") or []
            source = {"label": f"View the job posting — {jobs[0]['title']}", "url": jobs[0]["url"]} if jobs else None
            return (
                "💼 Hiring Receptionist",
                "Actively hiring front-desk staff or receptionists; an AI can reduce overhead.",
                source,
            )
        if pain.sub_scores.get("after_hours_leak", 0.0) > 0.5:
            return (
                "🌙 After-Hours Leak",
                "Not open 24/7 and lacks online booking, losing leads during closed hours.",
                None,
            )
        if not business.get("website"):
            return "🌐 No Website", "No website found; totally reliant on walk-ins and phone calls.", None
        if not website.get("booking_available"):
            return "📅 No Booking System", "Has a website but no booking automation.", None

        return "✨ General AI Upgrade", "Good fit for automated patient/client handling.", None

    # ── Pain Score (40%) ─────────────────────────────────────────────────────
    def _score_pain(self, business: dict, website: dict, review: dict, value: dict, enricher: dict) -> ScoreBreakdown:
        sub = {}
        evidence = []

        website_url = business.get("website")
        maps_url = business.get("maps_url")
        hiring_sources = enricher.get("hiring_sources") or []
        hiring_url = hiring_sources[0]["url"] if hiring_sources else None
        hiring_label = f"View job posting — {hiring_sources[0]['title']}" if hiring_sources else "View job posting"

        # Phone Dependency (30%) — no website or no online booking = phone dependent
        phone_dep = 0.0
        if not website_url:
            phone_dep = 1.0
            evidence.append(ev(
                "No website detected — customers must call to inquire",
                maps_url, "See their Google listing",
            ))
        elif not website.get("booking_available"):
            phone_dep = 0.8
            evidence.append(ev(
                "Website has no online booking — bookings are phone-based",
                website_url, "View their website",
            ))
        elif website.get("phone_dependency_score", 0) > 0.6:
            phone_dep = website["phone_dependency_score"]
            evidence.append(ev(f"High phone dependency score ({phone_dep:.0%})", website_url, "View their website"))
        else:
            phone_dep = 0.4
        sub["phone_dependency"] = phone_dep

        # No Booking Automation (20%)
        no_booking = 0.0
        if not website.get("booking_available") and not website.get("whatsapp_available"):
            no_booking = 1.0
            evidence.append(ev(
                "No online booking or WhatsApp booking detected",
                website_url, "View their website",
            ))
        elif not website.get("booking_available"):
            no_booking = 0.6
            evidence.append(ev("Online booking not available on website", website_url, "View their website"))
        else:
            no_booking = 0.1
        sub["no_booking_automation"] = no_booking

        # Negative Call Reviews (20%)
        call_pain = min(1.0, review.get("call_pain_score", 0))
        if call_pain > 0.5:
            evidence.append(ev(
                f"Reviews mention call/booking pain ({len(review.get('evidence', []))} signals)",
                maps_url, "See the reviews on Google Maps",
            ))
        sub["negative_call_reviews"] = call_pain

        # Receptionist Hiring (20%) — from enricher, backed by the real job posting
        hiring = 1.0 if enricher.get("is_hiring_receptionist") else (0.5 if enricher.get("is_hiring_any") else 0.0)
        if hiring > 0:
            evidence.append(ev(
                "Business is actively hiring receptionist/front-desk staff",
                hiring_url, hiring_label,
            ))
        sub["receptionist_hiring"] = hiring

        # Extended Hours (10%)
        extended = 1.0 if has_extended_hours(business.get("opening_hours")) else 0.0
        if extended:
            evidence.append(ev(
                "Business operates extended/late hours — after-hours call handling needed",
                maps_url, "See hours on Google Maps",
            ))
        sub["extended_hours"] = extended

        # After-Hours Leak (10%)
        is_7d = is_7_days(business.get("opening_hours"))
        after_hours_leak = 0.0
        if not is_7d and not website.get("booking_available"):
            after_hours_leak = 1.0
            evidence.append(ev(
                "Closed on some days/nights with no online booking to catch leads",
                maps_url, "See hours on Google Maps",
            ))
        sub["after_hours_leak"] = after_hours_leak

        weights = PAIN_SIGNALS
        raw = sum(sub[k] * weights[k] for k in sub)
        score = round(raw * 100, 2)

        return ScoreBreakdown(score=score, sub_scores=sub, evidence=evidence)

    # ── Business Value Score (25%) ────────────────────────────────────────────
    def _score_business_value(self, business: dict, value: dict) -> ScoreBreakdown:
        sub = {}
        evidence = []

        maps_url = business.get("maps_url")

        # Industry Value (30%) — internal scoring definition, nothing external to link
        category = business.get("category", "default")
        industry_val = industry_value(category)
        sub["industry_value"] = industry_val
        evidence.append(ev(f"Industry: {category.replace('_', ' ').title()} (value={industry_val:.0%})"))

        # Location Tier (20%) — internal scoring definition, nothing external to link
        city = business.get("city", "default")
        loc_tier = location_tier(city)
        sub["location_tier"] = loc_tier
        evidence.append(ev(f"City: {city} (tier={loc_tier:.0%})"))

        # Review Volume (20%) — proxy for demand
        review_count = business.get("review_count", 0) or 0
        if review_count >= 1000:
            review_vol = 1.0
        elif review_count >= 500:
            review_vol = 0.8
        elif review_count >= 200:
            review_vol = 0.6
        elif review_count >= 50:
            review_vol = 0.4
        else:
            review_vol = 0.2
        sub["review_volume"] = review_vol
        evidence.append(ev(f"{review_count} Google reviews (demand proxy)", maps_url, "See Google Reviews"))

        # Customer Value (20%) — from value_result or industry default
        cust_val = value.get("customer_value_score", industry_val * 0.8)
        sub["customer_value"] = min(1.0, cust_val)

        # Business Size (10%)
        rating = business.get("rating") or 0
        if review_count > 500 and rating >= 4.0:
            biz_size = 0.9
            evidence.append(ev("Established business: high reviews + good rating", maps_url, "See Google Reviews"))
        elif review_count > 100:
            biz_size = 0.6
        else:
            biz_size = 0.3
        sub["business_size"] = biz_size

        weights = VALUE_SIGNALS
        raw = sum(sub[k] * weights[k] for k in sub)
        score = round(raw * 100, 2)

        return ScoreBreakdown(score=score, sub_scores=sub, evidence=evidence)

    # ── Digital Adoption Score (20%) ──────────────────────────────────────────
    def _score_digital(self, business: dict, website: dict, social: dict) -> ScoreBreakdown:
        sub = {}
        evidence = []

        website_url = business.get("website")

        # Has Website (20%)
        has_web = 1.0 if website_url else 0.0
        sub["has_website"] = has_web
        if has_web:
            evidence.append(ev(f"Website: {website_url}", website_url, "Visit website"))
        else:
            evidence.append(ev("No website — very low digital maturity"))

        # Runs Ads (30%) — heuristic from ad-tracking pixels found in their own site source
        runs_ads = website.get("runs_ads", 0.0)
        sub["runs_ads"] = runs_ads
        if runs_ads > 0.5:
            evidence.append(ev(
                "Ads detected (Google/Meta) — business invests in acquisition",
                website_url, "View their website source",
            ))

        # Social Activity (20%)
        social_score = min(1.0, social.get("activity_score", 0.0))
        sub["social_activity"] = social_score
        if social_score > 0.5:
            # website["socials"] (from the contact-extractor crawl) is far more
            # reliably populated than business["social_links"] (Places API,
            # rarely has these) at the point scoring runs.
            socials = website.get("socials") or business.get("social_links") or {}
            social_url = socials.get("instagram") or socials.get("facebook")
            evidence.append(ev(f"Active social presence (score={social_score:.0%})", social_url, "View their social profile"))

        # Existing Software (20%) — using software = tech adopter
        auto_level = website.get("automation_level", 0.0)
        sub["existing_software"] = min(1.0, auto_level)
        if auto_level > 0.5:
            evidence.append(ev("CRM/booking software detected on website", website_url, "View their website"))

        # Online Presence (10%)
        web_quality = min(1.0, website.get("website_quality_score", 0.3 if has_web else 0.0))
        sub["online_presence"] = web_quality

        weights = DIGITAL_SIGNALS
        raw = sum(sub[k] * weights[k] for k in sub)
        score = round(raw * 100, 2)

        return ScoreBreakdown(score=score, sub_scores=sub, evidence=evidence)

    # ── Buying Timing Score (15%) ─────────────────────────────────────────────
    def _score_timing(self, social: dict, value: dict, enricher: dict) -> ScoreBreakdown:
        sub = {}
        evidence = []

        # Is Hiring (30%) — backed by the real job posting, when we found one
        is_hiring = 1.0 if enricher.get("is_hiring_any") or value.get("is_hiring") else 0.0
        sub["is_hiring"] = is_hiring
        if is_hiring:
            hiring_sources = enricher.get("hiring_sources") or []
            hiring_url = hiring_sources[0]["url"] if hiring_sources else None
            hiring_label = f"View job posting — {hiring_sources[0]['title']}" if hiring_sources else None
            evidence.append(ev("Hiring signal detected — business is growing", hiring_url, hiring_label))

        # Expanding (20%)
        expanding = 1.0 if value.get("is_expanding") else 0.0
        sub["expanding"] = expanding
        if expanding:
            evidence.append(ev("Expansion signals detected"))

        # Marketing Activity (30%)
        mktg = min(1.0, social.get("customer_intent_score", 0.0))
        sub["marketing_activity"] = mktg
        if mktg > 0.5:
            evidence.append(ev("Active marketing signals in social comments"))

        # Recent Growth (20%)
        growth = min(1.0, value.get("recent_growth_score", 0.3))
        sub["recent_growth"] = growth

        weights = TIMING_SIGNALS
        raw = sum(sub[k] * weights[k] for k in sub)
        score = round(raw * 100, 2)

        return ScoreBreakdown(score=score, sub_scores=sub, evidence=evidence)
