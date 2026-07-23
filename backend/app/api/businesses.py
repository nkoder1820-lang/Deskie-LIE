from datetime import datetime

from app.models.business import Business, LeadScore, LeadReport
from app.database import get_db

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from typing import Optional
from urllib.parse import quote
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/businesses", tags=["Businesses"])


@router.get("")
def list_businesses(
    city: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    sort_by: str = Query("final_score", description="final_score | rating | review_count"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """
    List all researched businesses with their lead scores.
    Supports filtering by city, category, priority and sorting.
    """
    query = (
        db.query(Business)
        .outerjoin(LeadScore, Business.id == LeadScore.business_id)
        .options(
            joinedload(Business.lead_score),
            joinedload(Business.lead_report),
        )
    )

    if city:
        query = query.filter(Business.city.ilike(f"%{city}%"))
    if category:
        query = query.filter(Business.category == category)
    if priority:
        query = query.filter(LeadScore.priority == priority.upper())

    if sort_by == "final_score":
        query = query.order_by(desc(LeadScore.final_score))
    elif sort_by == "rating":
        query = query.order_by(desc(Business.rating))
    elif sort_by == "review_count":
        query = query.order_by(desc(Business.review_count))

    total = query.count()
    businesses = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "businesses": [_serialize_business(b) for b in businesses],
    }


@router.get("/{business_id}")
def get_business(business_id: str, db: Session = Depends(get_db)):
    """Get full details for a single business including all research results."""
    from uuid import UUID as PyUUID

    try:
        biz_uuid = PyUUID(business_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Business not found")

    business = (
        db.query(Business)
        .options(
            joinedload(Business.lead_score),
            joinedload(Business.lead_report),
            joinedload(Business.research_results),
        )
        .filter(Business.id == biz_uuid)
        .first()
    )

    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    result = _serialize_business(business)

    # Add research details
    result["research"] = {
        r.agent_name: r.result_json
        for r in business.research_results
    }

    return result


class SetDemoRequest(BaseModel):
    demo_slug: str
    demo_url: str


@router.patch("/{business_id}/demo")
def set_business_demo(business_id: str, req: SetDemoRequest, db: Session = Depends(get_db)):
    """Called by deskie-agent after it creates a demo receptionist for this
    lead, so the demo link shows up here too (and via GET /api/businesses).
    Intentionally unauthenticated, matching every other endpoint in this
    service — see README for the deployment-time caveat."""
    from uuid import UUID as PyUUID

    try:
        biz_uuid = PyUUID(business_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Business not found")

    business = db.query(Business).filter(Business.id == biz_uuid).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    business.demo_slug = req.demo_slug
    business.demo_url = req.demo_url
    business.demo_created_at = datetime.utcnow()
    db.commit()
    db.refresh(business)

    return {
        "id": str(business.id),
        "demo_slug": business.demo_slug,
        "demo_url": business.demo_url,
        "demo_created_at": business.demo_created_at.isoformat(),
    }


def _serialize_business(b: Business) -> dict:
    score = b.lead_score
    report = b.lead_report
    return {
        "id": str(b.id),
        "name": b.name,
        "category": b.category,
        "city": b.city,
        "phone": b.phone,
        "email": b.email,
        "emails": b.emails or [],
        "phones": b.phones or [],
        "whatsapp": b.whatsapp,
        "whatsapp_link": f"https://wa.me/{b.whatsapp.lstrip('+')}" if b.whatsapp else None,
        "decision_makers": b.decision_makers or [],
        "poc_contacts": b.poc_contacts or [],
        "poc_researched_at": b.poc_researched_at.isoformat() if b.poc_researched_at else None,
        "linkedin_search": (
            "https://www.linkedin.com/search/results/people/?keywords="
            + quote(f'"{b.name}" owner OR manager')
        ),
        "website": b.website,
        "maps_url": b.maps_url,
        "contact_form_url": b.contact_form_url,
        "address": b.address,
        "rating": float(b.rating) if b.rating else None,
        "review_count": b.review_count,
        "opening_hours": b.opening_hours,
        "social_links": b.social_links,
        "detected_tech": b.detected_tech,
        "source": b.source,
        "demo_slug": b.demo_slug,
        "demo_url": b.demo_url,
        "demo_created_at": b.demo_created_at.isoformat() if b.demo_created_at else None,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        # Lead score
        "score": {
            "final_score": float(score.final_score) if score and score.final_score else None,
            "priority": score.priority if score else None,
            "pitch_angle": score.pitch_angle if score else None,
            "qualification_reason": score.qualification_reason if score else None,
            "pitch_source": score.pitch_source if score else None,
            "pain_score": float(score.pain_score) if score and score.pain_score else None,
            "business_value_score": float(score.business_value_score) if score and score.business_value_score else None,
            "digital_score": float(score.digital_score) if score and score.digital_score else None,
            "timing_score": float(score.timing_score) if score and score.timing_score else None,
            "pain_breakdown": score.pain_breakdown if score else None,
            "value_breakdown": score.value_breakdown if score else None,
            "digital_breakdown": score.digital_breakdown if score else None,
            "timing_breakdown": score.timing_breakdown if score else None,
        } if score else None,
        # Lead report
        "report": {
            "summary": report.summary,
            "top_reasons": report.top_reasons,
            "pain_points": report.pain_points,
            "recommended_pitch": report.recommended_pitch,
            "outreach_subject": report.outreach_subject,
            "outreach_email": report.outreach_email,
            "whatsapp_message": report.whatsapp_message,
            "email_sent_at": report.email_sent_at.isoformat() if report.email_sent_at else None,
            "poc_outreach": report.poc_outreach or [],
            "sources": (report.evidence or {}).get("sources", []),
        } if report else None,
    }
