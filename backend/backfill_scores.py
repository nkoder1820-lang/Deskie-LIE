"""
Backfill Script: Patch pitch_angle and qualification_reason for all existing leads.
Reads research_results already in the DB, re-runs the scoring engine,
and updates lead_scores without re-calling any external APIs.
"""
import sys
import os
import json
import logging

# Make sure the app package is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.scoring.engine import ScoringEngine
from app.models.business import Business, LeadScore

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("backfill")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./deskie_lie.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

scoring_engine = ScoringEngine()


def backfill():
    db = Session()
    businesses = db.query(Business).all()
    logger.info(f"Found {len(businesses)} businesses to backfill.")

    updated = 0
    for biz in businesses:
        # Collect research results keyed by agent name
        research = {r.agent_name: r.result_json for r in biz.research_results}

        biz_dict = {
            "id": str(biz.id),
            "name": biz.name,
            "category": biz.category,
            "city": biz.city,
            "phone": biz.phone,
            "website": biz.website,
            "rating": float(biz.rating) if biz.rating else None,
            "review_count": biz.review_count,
            "opening_hours": biz.opening_hours,
        }

        website_result   = research.get("website_agent", {})
        review_result    = research.get("review_agent", {})
        social_result    = research.get("social_agent", {})
        value_result     = research.get("value_agent", {})
        enricher_result  = research.get("lead_enricher_agent", {})

        scored = scoring_engine.score(
            business=biz_dict,
            website_result=website_result,
            review_result=review_result,
            social_result=social_result,
            value_result=value_result,
            enricher_result=enricher_result,
        )

        lead_score = db.query(LeadScore).filter_by(business_id=biz.id).first()
        if lead_score:
            lead_score.pitch_angle         = scored.pitch_angle
            lead_score.qualification_reason = scored.qualification_reason
            lead_score.final_score          = scored.final_score
            lead_score.priority             = scored.priority
            lead_score.pain_score           = scored.pain_score
            lead_score.pain_breakdown       = {
                "score": scored.pain_breakdown.score,
                "sub_scores": scored.pain_breakdown.sub_scores,
                "evidence": scored.pain_breakdown.evidence,
            }
            lead_score.business_value_score = scored.business_value_score
            lead_score.value_breakdown      = {
                "score": scored.value_breakdown.score,
                "sub_scores": scored.value_breakdown.sub_scores,
                "evidence": scored.value_breakdown.evidence,
            }
            lead_score.digital_score        = scored.digital_score
            lead_score.digital_breakdown    = {
                "score": scored.digital_breakdown.score,
                "sub_scores": scored.digital_breakdown.sub_scores,
                "evidence": scored.digital_breakdown.evidence,
            }
            lead_score.timing_score         = scored.timing_score
            lead_score.timing_breakdown     = {
                "score": scored.timing_breakdown.score,
                "sub_scores": scored.timing_breakdown.sub_scores,
                "evidence": scored.timing_breakdown.evidence,
            }
            updated += 1
            logger.info(f"  ✓ {biz.name[:50]:<50} → {scored.priority:6} | {scored.pitch_angle}")
        else:
            logger.warning(f"  ✗ {biz.name[:50]:<50} has no lead_score row — skipping")

    db.commit()
    db.close()
    logger.info(f"\n✅ Backfill complete. {updated}/{len(businesses)} leads updated.")


if __name__ == "__main__":
    backfill()
