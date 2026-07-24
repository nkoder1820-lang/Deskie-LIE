"""
Outreach API
============
One-click sending of the generated cold email for a lead.

Uses the Resend API (https://resend.com) — set RESEND_API_KEY and
OUTREACH_FROM_EMAIL (a sender on a domain verified in Resend) in .env.
Each send is an explicit user action from the UI; nothing is sent automatically.
"""
import logging
from datetime import datetime
from uuid import UUID as PyUUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models.business import Business, ResearchResult
from app.outreach_templates import compose_outreach_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/outreach", tags=["Outreach"])


@router.get("/compose/{business_id}")
def compose_email(business_id: str, db: Session = Depends(get_db)):
    """Builds the professional HTML outreach email for a lead — template
    chosen by pitch angle, evidence cited with its source link, CTA pointing
    at the lead's /demo/<slug>. Deterministic: preview == what would send."""
    try:
        biz_uuid = PyUUID(business_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Business not found")

    business = (
        db.query(Business)
        .options(joinedload(Business.lead_score))
        .filter(Business.id == biz_uuid)
        .first()
    )
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    enricher = (
        db.query(ResearchResult)
        .filter_by(business_id=biz_uuid, agent_name="lead_enricher_agent")
        .first()
    )
    return compose_outreach_email(
        business,
        business.lead_score,
        enricher.result_json if enricher else None,
    )


class SendEmailRequest(BaseModel):
    # Optional overrides — defaults come from the stored outreach copy
    subject: str | None = None
    body: str | None = None
    to: str | None = None


@router.get("/config")
def outreach_config():
    """Tells the UI whether one-click email sending is available."""
    return {
        "email_sending_enabled": bool(settings.RESEND_API_KEY and settings.OUTREACH_FROM_EMAIL),
        "from_email": settings.OUTREACH_FROM_EMAIL or None,
    }


@router.post("/send-email/{business_id}")
def send_email(business_id: str, req: SendEmailRequest, db: Session = Depends(get_db)):
    """Send the lead's generated cold email via Resend. Explicit action per lead."""
    if not settings.RESEND_API_KEY or not settings.OUTREACH_FROM_EMAIL:
        raise HTTPException(
            status_code=400,
            detail="Email sending not configured. Set RESEND_API_KEY and OUTREACH_FROM_EMAIL in backend/.env",
        )

    try:
        biz_uuid = PyUUID(business_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Business not found")

    business = (
        db.query(Business)
        .options(joinedload(Business.lead_report))
        .filter(Business.id == biz_uuid)
        .first()
    )
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    report = business.lead_report
    to = req.to or business.email
    subject = req.subject or (report.outreach_subject if report else None)
    body = req.body or (report.outreach_email if report else None)

    if not to:
        raise HTTPException(status_code=400, detail="Lead has no email address")
    if not subject or not body:
        raise HTTPException(status_code=400, detail="Lead has no generated outreach — run research first")

    payload = {
        "from": settings.OUTREACH_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if settings.OUTREACH_REPLY_TO:
        payload["reply_to"] = settings.OUTREACH_REPLY_TO

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json=payload,
            timeout=15.0,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Email provider unreachable: {e}")

    if resp.status_code >= 300:
        logger.error(f"[Outreach] Resend error {resp.status_code}: {resp.text[:300]}")
        raise HTTPException(status_code=502, detail=f"Send failed: {resp.text[:200]}")

    if report:
        report.email_sent_at = datetime.utcnow()
        db.commit()

    email_id = resp.json().get("id")
    logger.info(f"[Outreach] Sent email to {to} for {business.name} (id={email_id})")
    return {"status": "sent", "to": to, "email_id": email_id}
