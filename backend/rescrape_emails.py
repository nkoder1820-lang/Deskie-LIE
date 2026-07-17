"""
rescrape_emails.py
==================
Re-runs WebsiteIntelligenceAgent on every business that has a website URL,
updates the research_results row and writes email + phone fallback back
to the businesses table.

No paid APIs are called — only direct HTTP to the business websites.
Run time: ~20-40 s per business (network dependent).
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.agents.website_agent import WebsiteIntelligenceAgent
from app.scoring.engine import ScoringEngine
from app.models.business import Business, ResearchResult, LeadScore

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("rescrape")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./deskie_lie.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

website_agent = WebsiteIntelligenceAgent()
scoring_engine = ScoringEngine()


def rescrape():
    db: Session = SessionLocal()
    businesses = db.query(Business).all()
    has_website = [b for b in businesses if b.website]
    logger.info(f"Found {len(has_website)}/{len(businesses)} businesses with a website URL to re-scrape.")

    updated_email = 0
    updated_phone = 0

    for biz in has_website:
        logger.info(f"  Scraping: {biz.name[:55]}")
        try:
            result = website_agent.run(biz.website, biz.name)
        except Exception as e:
            logger.warning(f"    ✗ Failed: {e}")
            continue

        emails = result.get("emails", [])
        phones = result.get("phone_numbers", [])

        # Update research_results row
        rr = db.query(ResearchResult).filter_by(
            business_id=biz.id, agent_name="website_agent"
        ).first()
        if rr:
            rr.result_json = result
        else:
            db.add(ResearchResult(
                business_id=biz.id,
                agent_name="website_agent",
                result_json=result,
                status="success",
            ))

        # Write email to business if missing
        if emails and not biz.email:
            biz.email = emails[0]
            updated_email += 1
            logger.info(f"    ✉  Email found: {emails[0]}")
        elif emails:
            # Always refresh with latest find even if we had one before
            biz.email = emails[0]
            updated_email += 1
            logger.info(f"    ✉  Email updated: {emails[0]}")
        else:
            logger.info(f"    —  No email found")

        # Write phone fallback if Places gave nothing
        if phones and not biz.phone:
            biz.phone = phones[0]
            updated_phone += 1
            logger.info(f"    📞 Phone fallback: {phones[0]}")

        # Also update detected_tech
        if result.get("detected_tech"):
            biz.detected_tech = result["detected_tech"]

        db.commit()

    # Re-run scores so breakdowns reflect fresh website data
    logger.info("\nRe-running score backfill with fresh website data…")
    all_businesses = db.query(Business).all()
    rescored = 0
    for biz in all_businesses:
        research = {r.agent_name: r.result_json for r in biz.research_results}
        biz_dict = {
            "id": str(biz.id), "name": biz.name, "category": biz.category,
            "city": biz.city, "phone": biz.phone, "website": biz.website,
            "rating": float(biz.rating) if biz.rating else None,
            "review_count": biz.review_count, "opening_hours": biz.opening_hours,
        }
        try:
            scored = scoring_engine.score(
                business=biz_dict,
                website_result=research.get("website_agent", {}),
                review_result=research.get("review_agent", {}),
                social_result=research.get("social_agent", {}),
                value_result=research.get("value_agent", {}),
                enricher_result=research.get("lead_enricher_agent", {}),
            )
            lead_score = db.query(LeadScore).filter_by(business_id=biz.id).first()
            if lead_score:
                lead_score.pitch_angle = scored.pitch_angle
                lead_score.qualification_reason = scored.qualification_reason
                lead_score.final_score = scored.final_score
                lead_score.priority = scored.priority
                lead_score.pain_score = scored.pain_score
                lead_score.pain_breakdown = {
                    "score": scored.pain_breakdown.score,
                    "sub_scores": scored.pain_breakdown.sub_scores,
                    "evidence": scored.pain_breakdown.evidence,
                }
                lead_score.business_value_score = scored.business_value_score
                lead_score.value_breakdown = {
                    "score": scored.value_breakdown.score,
                    "sub_scores": scored.value_breakdown.sub_scores,
                    "evidence": scored.value_breakdown.evidence,
                }
                lead_score.digital_score = scored.digital_score
                lead_score.digital_breakdown = {
                    "score": scored.digital_breakdown.score,
                    "sub_scores": scored.digital_breakdown.sub_scores,
                    "evidence": scored.digital_breakdown.evidence,
                }
                lead_score.timing_score = scored.timing_score
                lead_score.timing_breakdown = {
                    "score": scored.timing_breakdown.score,
                    "sub_scores": scored.timing_breakdown.sub_scores,
                    "evidence": scored.timing_breakdown.evidence,
                }
                rescored += 1
        except Exception as e:
            logger.warning(f"  Score failed for {biz.name}: {e}")

    db.commit()
    db.close()

    logger.info(f"""
╔══════════════════════════════════════╗
║  Rescrape complete!                  ║
║  Emails updated : {updated_email:<18} ║
║  Phones added   : {updated_phone:<18} ║
║  Scores updated : {rescored:<18} ║
╚══════════════════════════════════════╝""")


if __name__ == "__main__":
    rescrape()
