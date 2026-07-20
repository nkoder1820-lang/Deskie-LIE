import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Numeric, Integer, DateTime,
    ForeignKey, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(512), nullable=False)
    category = Column(String(256), nullable=False)
    city = Column(String(256), nullable=False)
    phone = Column(String(64))
    email = Column(String(256))
    emails = Column(JSON, default=list)            # all valid emails found
    phones = Column(JSON, default=list)            # all valid phones found (E.164)
    whatsapp = Column(String(32))                  # E.164 WhatsApp number
    decision_makers = Column(JSON, default=list)   # [{name, title}] from team/about pages
    poc_contacts = Column(JSON, default=list)       # enriched PoCs: [{name, title, emails, guessed_emails, phones, linkedin_url, confidence, source}]
    poc_researched_at = Column(DateTime)            # when PoC research last ran
    website = Column(Text)
    maps_url = Column(Text)                        # Google Maps listing URL
    contact_form_url = Column(Text)                # page with a contact form
    address = Column(Text)
    rating = Column(Numeric(3, 1))
    review_count = Column(Integer)
    opening_hours = Column(JSON)
    social_links = Column(JSON, default=dict)
    detected_tech = Column(JSON, default=list)
    place_id = Column(String(256), unique=True)      # Google Place ID — dedup key
    source = Column(String(64), default="google_places")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    research_results = relationship("ResearchResult", back_populates="business", cascade="all, delete-orphan")
    lead_score = relationship("LeadScore", back_populates="business", uselist=False, cascade="all, delete-orphan")
    lead_report = relationship("LeadReport", back_populates="business", uselist=False, cascade="all, delete-orphan")


class ResearchResult(Base):
    __tablename__ = "research_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(128), nullable=False)    # 'website_agent', 'review_agent', etc.
    result_json = Column(JSON, nullable=False)
    status = Column(String(32), default="success")      # success | failed | skipped
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="research_results")


class LeadScore(Base):
    __tablename__ = "lead_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), unique=True, nullable=False)
    pain_score = Column(Numeric(5, 2))
    pain_breakdown = Column(JSON)           # sub-scores with evidence
    business_value_score = Column(Numeric(5, 2))
    value_breakdown = Column(JSON)
    digital_score = Column(Numeric(5, 2))
    digital_breakdown = Column(JSON)
    timing_score = Column(Numeric(5, 2))
    timing_breakdown = Column(JSON)
    final_score = Column(Numeric(5, 2))
    priority = Column(String(16))           # HOT | HIGH | MEDIUM | LOW
    pitch_angle = Column(String(128))
    qualification_reason = Column(Text)
    pitch_source = Column(JSON)             # {"label": str, "url": str} — real link backing the pitch angle
    scored_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="lead_score")


class LeadReport(Base):
    __tablename__ = "lead_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), unique=True, nullable=False)
    summary = Column(Text)
    top_reasons = Column(JSON)              # list of strings
    pain_points = Column(JSON)              # list of strings
    recommended_pitch = Column(Text)
    outreach_subject = Column(Text)         # ready-to-send email subject
    outreach_email = Column(Text)           # ready-to-send email body
    whatsapp_message = Column(Text)         # ready-to-send WhatsApp text
    email_sent_at = Column(DateTime)        # when outreach email was sent (if ever)
    poc_outreach = Column(JSON, default=list)  # [{name, title, email_subject, email_body, whatsapp_message}] per decision maker
    evidence = Column(JSON)                 # raw evidence snippets
    generated_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="lead_report")
