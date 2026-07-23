"""
Lead Intelligence Orchestrator
================================
Coordinates all agents for each discovered business.
Businesses are processed IN PARALLEL (thread pool) — each worker gets its own
DB session. Results are saved as soon as each business finishes.

Flow:
  1. Discovery Agent     → find businesses (any industry, any country)
  2. For each business (parallel):
     a. Website Agent    → website + deep contact intelligence
     b. Review Agent     → review intelligence
     c. Social Agent     → social intelligence
     d. Value Agent      → business value assessment
     e. Enricher Agent   → hiring / ads signals
     f. Scoring Engine   → calculate score
     g. Report Generator → lead report + sendable outreach (email + WhatsApp)
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.discovery_agent import BusinessDiscoveryAgent
from app.agents.website_agent import WebsiteIntelligenceAgent
from app.agents.review_agent import ReviewIntelligenceAgent
from app.agents.social_agent import SocialIntelligenceAgent
from app.agents.value_agent import BusinessValueAgent
from app.agents.lead_enricher_agent import LeadEnricherAgent
from app.agents.contact_extractor import region_from_address
from app.scoring.engine import ScoringEngine
from app.reports.generator import ReportGenerator
from app.models.business import Business, ResearchResult, LeadScore, LeadReport
from app.database import SessionLocal

logger = logging.getLogger(__name__)

MAX_WORKERS = 6     # concurrent businesses


class LeadIntelligenceOrchestrator:

    def __init__(self, db: Session):
        self.db = db                    # session for discovery/upserts on the request thread
        self.discovery  = BusinessDiscoveryAgent()
        self.website    = WebsiteIntelligenceAgent()
        self.review     = ReviewIntelligenceAgent()
        self.social     = SocialIntelligenceAgent()
        self.value      = BusinessValueAgent()
        self.enricher   = LeadEnricherAgent()
        self.scoring    = ScoringEngine()
        self.reporter   = ReportGenerator()

    def run_research(self, industry: str, city: str, max_results: int = 20,
                     country: str | None = None) -> list[dict]:
        """
        Full pipeline: discover → research (parallel) → score → report → save.
        Returns list of scored lead summaries.
        """
        logger.info(f"[Orchestrator] Starting research: {industry} in {city}"
                    + (f", {country}" if country else ""))

        # Phase 1: Discovery
        discovered = self.discovery.run(industry, city, max_results, country=country)
        logger.info(f"[Orchestrator] Discovered {len(discovered)} businesses")

        default_region = region_from_address(country) if country else "IN"

        # Phase 2: Parallel processing — one thread + one DB session per business
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(self._process_business_threadsafe, biz, default_region): biz
                for biz in discovered
            }
            for future in as_completed(futures):
                biz = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"[Orchestrator] Failed to process {biz.name}: {e}", exc_info=True)

        # Sort by final score descending
        results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        logger.info(f"[Orchestrator] Research complete. {len(results)} leads scored.")
        return results

    def run_hiring_research(self, city: str, role: str = "receptionist",
                            industry: str | None = None, country: str | None = None,
                            max_results: int = 20) -> list[dict]:
        """Hiring-first pipeline: start from live job postings (Google Jobs via
        SerpAPI — aggregates LinkedIn/Indeed/etc.), resolve each posting's
        company to a real business, then run the standard enrichment with the
        hiring evidence pre-seeded (skips the enricher's own SerpAPI calls)."""
        from app.agents.hiring_discovery_agent import HiringDiscoveryAgent

        logger.info(f"[Orchestrator] Hiring-first research: '{role}' in {city}"
                    + (f" ({industry})" if industry else ""))
        pairs = HiringDiscoveryAgent().run(
            city=city, role=role, industry=industry, country=country, max_results=max_results,
        )
        default_region = region_from_address(country) if country else "IN"

        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(self._process_business_threadsafe, biz, default_region, seed): biz
                for biz, seed in pairs
            }
            for future in as_completed(futures):
                biz = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"[Orchestrator] Failed to process {biz.name}: {e}", exc_info=True)

        results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        logger.info(f"[Orchestrator] Hiring-first research complete. {len(results)} leads scored.")
        return results

    def _process_business_threadsafe(self, biz, default_region: str,
                                     enricher_seed: dict | None = None) -> dict:
        """Worker entry point: fresh DB session per thread."""
        db = SessionLocal()
        try:
            return self._process_business(biz, db, default_region, enricher_seed)
        finally:
            db.close()

    def _process_business(self, biz, db: Session, default_region: str = "IN",
                          enricher_seed: dict | None = None) -> dict:
        """Process a single discovered business through all agents."""
        logger.info(f"[Orchestrator] Processing: {biz.name}")

        region = region_from_address(biz.address, default=default_region)

        # Save or update business record
        business_record = self._upsert_business(biz, db)
        biz_id = business_record.id

        biz_dict = {
            "id": str(biz_id),
            "name": biz.name,
            "category": biz.category,
            "city": biz.city,
            "phone": biz.phone,
            "website": biz.website,
            "maps_url": biz.maps_url,
            "rating": float(biz.google_rating) if biz.google_rating else None,
            "review_count": biz.review_count,
            "opening_hours": biz.opening_hours,
            "social_links": biz.social_links,
        }

        # Phase 2a: Website + Contact Intelligence
        # (use_ai=False: heuristics cover these signals; saves an LLM call per lead)
        website_result = self.website.run(biz.website, biz.name, region=region, use_ai=False)
        self._save_research(biz_id, "website_agent", website_result, db)
        self._save_contacts(biz_id, website_result, db)

        # Phase 2b: Review Intelligence
        review_result = self.review.run(biz.place_id, biz.name)
        self._save_research(biz_id, "review_agent", review_result, db)

        # Phase 2c: Social Intelligence
        social_result = self.social.run(
            business_name=biz.name,
            city=biz.city,
            category=biz.category,
            social_links=website_result.get("socials") or biz.social_links,
            review_count=biz.review_count,
            rating=float(biz.google_rating) if biz.google_rating else None,
        )
        self._save_research(biz_id, "social_agent", social_result, db)

        # Phase 2d: Business Value
        value_result = self.value.run(
            business_name=biz.name,
            category=biz.category,
            city=biz.city,
            rating=float(biz.google_rating) if biz.google_rating else None,
            review_count=biz.review_count,
            website=biz.website,
            opening_hours=biz.opening_hours,
        )
        self._save_research(biz_id, "value_agent", value_result, db)

        # Phase 2e: Lead Enrichment (Hiring/Ads). Hiring-first discovery hands
        # us the evidence it already holds — no need to burn 2 more SerpAPI
        # searches re-verifying what we started from.
        enricher_result = enricher_seed or self.enricher.run(business_name=biz.name, city=biz.city)
        self._save_research(biz_id, "lead_enricher_agent", enricher_result, db)

        # Phase 3: Scoring
        scored = self.scoring.score(
            business=biz_dict,
            website_result=website_result,
            review_result=review_result,
            social_result=social_result,
            value_result=value_result,
            enricher_result=enricher_result,
        )
        self._save_score(biz_id, scored, db)

        # Phase 4: Report + sendable outreach
        report = self.reporter.generate(
            business=biz_dict,
            scored_lead=scored,
            website_result=website_result,
            review_result=review_result,
            social_result=social_result,
            value_result=value_result,
            enricher_result=enricher_result,
        )
        self._save_report(biz_id, report, db)

        logger.info(f"  ✓ {biz.name} → Score: {scored.final_score} ({scored.priority})")

        return {
            "business_id": str(biz_id),
            "name": biz.name,
            "city": biz.city,
            "category": biz.category,
            "rating": biz_dict["rating"],
            "review_count": biz.review_count,
            "email": website_result.get("emails", [None])[0] if website_result.get("emails") else None,
            "whatsapp": website_result.get("whatsapp"),
            "socials": website_result.get("socials", {}),
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

    def _upsert_business(self, biz, db: Session) -> Business:
        """Insert or update a business record (deduplicated by place_id)."""
        existing = None
        if biz.place_id:
            existing = db.query(Business).filter_by(place_id=biz.place_id).first()

        if existing:
            existing.name = biz.name
            existing.phone = biz.phone or existing.phone
            existing.website = biz.website or existing.website
            existing.rating = biz.google_rating
            existing.review_count = biz.review_count
            existing.opening_hours = biz.opening_hours
            existing.maps_url = biz.maps_url or existing.maps_url
            # Hiring evidence upgrades provenance: a lead first found by
            # industry search that later shows up in job postings becomes a
            # hiring-first lead (never the reverse — classic re-discovery
            # shouldn't erase a hiring signal).
            if (biz.source or "").endswith("_jobs"):
                existing.source = biz.source
            db.commit()
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
                maps_url=biz.maps_url,
                source=biz.source,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record

    def _save_contacts(self, business_id: UUID, website_result: dict, db: Session):
        """Persist every contact channel found by the website/contact agents."""
        b = db.query(Business).get(business_id)
        if not b:
            return
        emails = website_result.get("emails") or []
        phones = website_result.get("phone_numbers") or []
        socials = website_result.get("socials") or {}
        if emails:
            b.email = emails[0]
            b.emails = emails
        if phones:
            b.phones = phones
            if not b.phone:
                b.phone = phones[0]
                logger.info(f"  📞 Phone fallback from website: {b.phone}")
        if website_result.get("whatsapp"):
            b.whatsapp = website_result["whatsapp"]
        if website_result.get("decision_makers"):
            b.decision_makers = website_result["decision_makers"]
        if socials:
            b.social_links = {**(b.social_links or {}), **socials}
        if website_result.get("contact_form_url"):
            b.contact_form_url = website_result["contact_form_url"]
        if website_result.get("detected_tech"):
            b.detected_tech = website_result["detected_tech"]
        db.commit()

    def _save_research(self, business_id: UUID, agent_name: str, result: dict, db: Session):
        """Save raw agent output to research_results table."""
        existing = db.query(ResearchResult).filter_by(
            business_id=business_id, agent_name=agent_name
        ).first()
        if existing:
            existing.result_json = result
            db.commit()
        else:
            record = ResearchResult(
                business_id=business_id,
                agent_name=agent_name,
                result_json=result,
                status="success",
            )
            db.add(record)
            db.commit()

    def _save_score(self, business_id: UUID, scored, db: Session):
        """Upsert lead score."""
        existing = db.query(LeadScore).filter_by(business_id=business_id).first()

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
            pitch_source=scored.pitch_source,
        )
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            db.commit()
        else:
            db.add(LeadScore(business_id=business_id, **data))
            db.commit()

    def _save_report(self, business_id: UUID, report: dict, db: Session):
        """Upsert lead report incl. sendable outreach."""
        existing = db.query(LeadReport).filter_by(business_id=business_id).first()
        data = dict(
            summary=report.get("summary"),
            top_reasons=report.get("top_reasons", []),
            pain_points=report.get("pain_points", []),
            recommended_pitch=report.get("recommended_pitch"),
            outreach_subject=report.get("outreach_subject"),
            outreach_email=report.get("outreach_email"),
            whatsapp_message=report.get("whatsapp_message"),
            evidence=report.get("evidence", {}),
        )
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            db.commit()
        else:
            db.add(LeadReport(business_id=business_id, **data))
            db.commit()
