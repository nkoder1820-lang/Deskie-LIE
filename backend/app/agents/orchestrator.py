"""
Lead Intelligence Orchestrator
================================
Coordinates all agents in sequence for a single business.
Saves results to PostgreSQL after each agent completes.

Flow:
  1. Discovery Agent     → find businesses
  2. For each business:
     a. Website Agent    → website intelligence
     b. Review Agent     → review intelligence
     c. Social Agent     → social intelligence
     d. Value Agent      → business value assessment
     e. Scoring Engine   → calculate score
     f. Report Generator → generate lead report
  3. Save all results to DB
"""
import logging
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.discovery_agent import BusinessDiscoveryAgent
from app.agents.website_agent import WebsiteIntelligenceAgent
from app.agents.review_agent import ReviewIntelligenceAgent
from app.agents.social_agent import SocialIntelligenceAgent
from app.agents.value_agent import BusinessValueAgent
from app.agents.lead_enricher_agent import LeadEnricherAgent
from app.scoring.engine import ScoringEngine
from app.reports.generator import ReportGenerator
from app.models.business import Business, ResearchResult, LeadScore, LeadReport

logger = logging.getLogger(__name__)


class LeadIntelligenceOrchestrator:

    def __init__(self, db: Session):
        self.db = db
        self.discovery  = BusinessDiscoveryAgent()
        self.website    = WebsiteIntelligenceAgent()
        self.review     = ReviewIntelligenceAgent()
        self.social     = SocialIntelligenceAgent()
        self.value      = BusinessValueAgent()
        self.enricher   = LeadEnricherAgent()
        self.scoring    = ScoringEngine()
        self.reporter   = ReportGenerator()

    def run_research(self, industry: str, city: str, max_results: int = 20) -> list[dict]:
        """
        Full pipeline: discover → research → score → report → save.
        Returns list of scored lead summaries.
        """
        logger.info(f"[Orchestrator] Starting research: {industry} in {city}")

        # Phase 1: Discovery
        discovered = self.discovery.run(industry, city, max_results)
        logger.info(f"[Orchestrator] Discovered {len(discovered)} businesses")

        results = []
        for biz in discovered:
            try:
                result = self._process_business(biz)
                results.append(result)
            except Exception as e:
                logger.error(f"[Orchestrator] Failed to process {biz.name}: {e}", exc_info=True)

        # Sort by final score descending
        results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        logger.info(f"[Orchestrator] Research complete. {len(results)} leads scored.")
        return results

    def _process_business(self, biz) -> dict:
        """Process a single discovered business through all agents."""
        logger.info(f"[Orchestrator] Processing: {biz.name}")

        # Save or update business record
        business_record = self._upsert_business(biz)
        biz_id = business_record.id

        biz_dict = {
            "id": str(biz_id),
            "name": biz.name,
            "category": biz.category,
            "city": biz.city,
            "phone": biz.phone,
            "website": biz.website,
            "rating": float(biz.google_rating) if biz.google_rating else None,
            "review_count": biz.review_count,
            "opening_hours": biz.opening_hours,
            "social_links": biz.social_links,
        }

        # Phase 2a: Website Intelligence
        logger.info(f"  → WebsiteAgent")
        website_result = self.website.run(biz.website, biz.name)
        self._save_research(biz_id, "website_agent", website_result)
        
        # Update business with website scraped data
        if website_result.get("emails") or website_result.get("detected_tech") or website_result.get("phone_numbers"):
            business_record = self.db.query(Business).get(biz_id)
            if website_result.get("emails"):
                business_record.email = website_result["emails"][0]
            if website_result.get("detected_tech"):
                business_record.detected_tech = website_result["detected_tech"]
            # Phone fallback: if Google Places had no phone, use the website-found number
            if website_result.get("phone_numbers") and not business_record.phone:
                business_record.phone = website_result["phone_numbers"][0]
                logger.info(f"  📞 Phone fallback from website: {business_record.phone}")
            self.db.commit()


        # Phase 2b: Review Intelligence
        logger.info(f"  → ReviewAgent")
        review_result = self.review.run(biz.place_id, biz.name)
        self._save_research(biz_id, "review_agent", review_result)

        # Phase 2c: Social Intelligence
        logger.info(f"  → SocialAgent")
        social_result = self.social.run(
            business_name=biz.name,
            city=biz.city,
            category=biz.category,
            social_links=biz.social_links,
            review_count=biz.review_count,
            rating=float(biz.google_rating) if biz.google_rating else None,
        )
        self._save_research(biz_id, "social_agent", social_result)

        # Phase 2d: Business Value
        logger.info(f"  → ValueAgent")
        value_result = self.value.run(
            business_name=biz.name,
            category=biz.category,
            city=biz.city,
            rating=float(biz.google_rating) if biz.google_rating else None,
            review_count=biz.review_count,
            website=biz.website,
            opening_hours=biz.opening_hours,
        )
        self._save_research(biz_id, "value_agent", value_result)

        # Phase 2e: Lead Enrichment (Hiring/Ads)
        logger.info(f"  → LeadEnricherAgent")
        enricher_result = self.enricher.run(business_name=biz.name, city=biz.city)
        self._save_research(biz_id, "lead_enricher_agent", enricher_result)

        # Phase 3: Scoring
        logger.info(f"  → ScoringEngine")
        scored = self.scoring.score(
            business=biz_dict,
            website_result=website_result,
            review_result=review_result,
            social_result=social_result,
            value_result=value_result,
            enricher_result=enricher_result,
        )
        self._save_score(biz_id, scored)

        # Phase 4: Report
        logger.info(f"  → ReportGenerator")
        report = self.reporter.generate(
            business=biz_dict,
            scored_lead=scored,
            website_result=website_result,
            review_result=review_result,
            social_result=social_result,
            value_result=value_result,
        )
        self._save_report(biz_id, report)

        logger.info(f"  ✓ {biz.name} → Score: {scored.final_score} ({scored.priority})")

        return {
            "business_id": str(biz_id),
            "name": biz.name,
            "city": biz.city,
            "category": biz.category,
            "rating": biz_dict["rating"],
            "review_count": biz.review_count,
            "final_score": scored.final_score,
            "priority": scored.priority,
            "pain_score": scored.pain_score,
            "business_value_score": scored.business_value_score,
            "digital_score": scored.digital_score,
            "timing_score": scored.timing_score,
            "pitch_angle": scored.pitch_angle,
            "qualification_reason": scored.qualification_reason,
            "summary": report.get("summary"),
            "recommended_pitch": report.get("recommended_pitch"),
        }

    # ── DB Helpers ──────────────────────────────────────────────────────────

    def _upsert_business(self, biz) -> Business:
        """Insert or update a business record (deduplicated by place_id)."""
        existing = None
        if biz.place_id:
            existing = self.db.query(Business).filter_by(place_id=biz.place_id).first()

        if existing:
            existing.name = biz.name
            existing.phone = biz.phone
            existing.website = biz.website
            existing.rating = biz.google_rating
            existing.review_count = biz.review_count
            existing.opening_hours = biz.opening_hours
            self.db.commit()
            return existing
        else:
            record = Business(
                name=biz.name,
                category=biz.category,
                city=biz.city,
                phone=biz.phone,
                website=biz.website,
                address=biz.address,
                rating=biz.google_rating,
                review_count=biz.review_count,
                opening_hours=biz.opening_hours,
                social_links=biz.social_links,
                place_id=biz.place_id,
                source=biz.source,
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return record

    def _save_research(self, business_id: UUID, agent_name: str, result: dict):
        """Save raw agent output to research_results table."""
        existing = self.db.query(ResearchResult).filter_by(
            business_id=business_id, agent_name=agent_name
        ).first()
        if existing:
            existing.result_json = result
            self.db.commit()
        else:
            record = ResearchResult(
                business_id=business_id,
                agent_name=agent_name,
                result_json=result,
                status="success",
            )
            self.db.add(record)
            self.db.commit()

    def _save_score(self, business_id: UUID, scored):
        """Upsert lead score."""
        existing = self.db.query(LeadScore).filter_by(business_id=business_id).first()

        def breakdown_dict(bd):
            return {
                "score": bd.score,
                "sub_scores": bd.sub_scores,
                "evidence": bd.evidence,
            }

        data = dict(
            pain_score=scored.pain_score,
            pain_breakdown=breakdown_dict(scored.pain_breakdown),
            business_value_score=scored.business_value_score,
            value_breakdown=breakdown_dict(scored.value_breakdown),
            digital_score=scored.digital_score,
            digital_breakdown=breakdown_dict(scored.digital_breakdown),
            timing_score=scored.timing_score,
            timing_breakdown=breakdown_dict(scored.timing_breakdown),
            final_score=scored.final_score,
            priority=scored.priority,
            pitch_angle=scored.pitch_angle,
            qualification_reason=scored.qualification_reason,
        )
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            self.db.commit()
        else:
            self.db.add(LeadScore(business_id=business_id, **data))
            self.db.commit()

    def _save_report(self, business_id: UUID, report: dict):
        """Upsert lead report."""
        existing = self.db.query(LeadReport).filter_by(business_id=business_id).first()
        data = dict(
            summary=report.get("summary"),
            top_reasons=report.get("top_reasons", []),
            pain_points=report.get("pain_points", []),
            recommended_pitch=report.get("recommended_pitch"),
            evidence=report.get("evidence", {}),
        )
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            self.db.commit()
        else:
            self.db.add(LeadReport(business_id=business_id, **data))
            self.db.commit()
