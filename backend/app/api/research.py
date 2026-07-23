from app.agents.orchestrator import LeadIntelligenceOrchestrator
from app.agents.discovery_agent import INDUSTRY_QUERIES
from app.agents.contact_extractor import ContactExtractor, region_from_address, _valid_email
from app.agents.poc_agent import PocResearchAgent
from app.reports.generator import ReportGenerator
from app.models.business import Business, LeadScore, LeadReport, ResearchResult
from app.database import get_db, SessionLocal

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID as PyUUID
import logging
import threading

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research", tags=["Research"])


class ResearchRequest(BaseModel):
    industry: str                    # preset key OR free text, e.g. "med spa"
    city: str                        # e.g. "Mumbai" or "Austin, TX"
    country: Optional[str] = None    # e.g. "USA" — sharpens search + phone parsing
    max_results: int = 20


class ResearchResponse(BaseModel):
    status: str
    message: str
    leads_count: int = 0


@router.get("/industries")
def list_industries():
    """List suggested industries (any free-text industry is also accepted)."""
    return {
        "industries": [
            {"key": k, "label": k.replace("_", " ").title()}
            for k in INDUSTRY_QUERIES.keys()
        ]
    }


@router.post("/run", response_model=ResearchResponse)
def run_research(
    req: ResearchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Kick off a full research pipeline for an industry + city (+ optional country).
    Industry can be any free-text niche — presets are just suggestions.

    Runs up to 100 leads synchronously; anything bigger (up to 2000) moves to
    the background job — a 2000-lead run takes hours (LLM rate limits), far
    beyond any HTTP timeout. Poll /api/research/bulk/status for progress.
    """
    industry = req.industry.strip()
    if not industry:
        raise HTTPException(status_code=400, detail="Industry must not be empty")
    if not req.city.strip():
        raise HTTPException(status_code=400, detail="City must not be empty")

    if req.max_results > 100:
        bulk_req = BulkResearchRequest(
            industries=[industry],
            cities=[req.city.strip()],
            country=req.country,
            max_results_per_pair=min(req.max_results, 2000),
        )
        _reserve_bulk_slot()
        background_tasks.add_task(_run_bulk_job, bulk_req)
        return ResearchResponse(
            status="started",
            message=f"Background job started for up to {min(req.max_results, 2000)} leads — "
                    "leads appear in the table as they land",
            leads_count=0,
        )

    try:
        orchestrator = LeadIntelligenceOrchestrator(db)
        results = orchestrator.run_research(
            industry=industry,
            city=req.city.strip(),
            max_results=min(req.max_results, 100),
            country=(req.country or "").strip() or None,
        )
        return ResearchResponse(
            status="completed",
            message=f"Research complete for {industry} in {req.city}",
            leads_count=len(results),
        )
    except Exception as e:
        logger.error(f"[ResearchAPI] Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Bulk research (1000s of leads) ──────────────────────────────────────────

class BulkResearchRequest(BaseModel):
    industries: list[str]            # e.g. ["restaurants", "med spas"]
    cities: list[str]                # e.g. ["Austin, TX", "Miami"]
    country: Optional[str] = None
    max_results_per_pair: int = 60   # up to 2000 (query-variant + area fan-out)


_bulk_lock = threading.Lock()
_bulk_state: dict = {"status": "idle"}


def _reserve_bulk_slot():
    """Only one background research job at a time — raises 409 if one is live."""
    with _bulk_lock:
        if _bulk_state.get("status") == "running":
            raise HTTPException(status_code=409, detail="A background research job is already running")
        _bulk_state["status"] = "running"  # reserve before the task actually starts


def _run_bulk_job(req: BulkResearchRequest):
    pairs = [(i.strip(), c.strip()) for i in req.industries for c in req.cities if i.strip() and c.strip()]
    with _bulk_lock:
        _bulk_state.update({
            "status": "running",
            "total_pairs": len(pairs),
            "pairs_done": 0,
            "leads_found": 0,
            "current": None,
            "errors": [],
            "started_at": datetime.utcnow().isoformat(),
        })

    for industry, city in pairs:
        with _bulk_lock:
            _bulk_state["current"] = f"{industry} in {city}"
        session = SessionLocal()
        try:
            orchestrator = LeadIntelligenceOrchestrator(session)
            results = orchestrator.run_research(
                industry=industry,
                city=city,
                max_results=min(req.max_results_per_pair, 2000),
                country=(req.country or "").strip() or None,
            )
            with _bulk_lock:
                _bulk_state["leads_found"] += len(results)
        except Exception as e:
            logger.error(f"[Bulk] {industry} in {city} failed: {e}", exc_info=True)
            with _bulk_lock:
                _bulk_state["errors"].append(f"{industry} in {city}: {e}")
        finally:
            session.close()
            with _bulk_lock:
                _bulk_state["pairs_done"] += 1

    with _bulk_lock:
        _bulk_state["status"] = "completed"
        _bulk_state["current"] = None
        _bulk_state["finished_at"] = datetime.utcnow().isoformat()


@router.post("/bulk")
def run_bulk_research(req: BulkResearchRequest, background_tasks: BackgroundTasks):
    """
    Research every industry × city combination in the background.
    e.g. 10 industries × 5 cities × 60 results = up to 3000 leads.
    Poll GET /api/research/bulk/status for progress.
    """
    if not req.industries or not req.cities:
        raise HTTPException(status_code=400, detail="industries and cities must not be empty")
    _reserve_bulk_slot()
    background_tasks.add_task(_run_bulk_job, req)
    pairs = len([1 for i in req.industries for c in req.cities])
    return {
        "status": "started",
        "pairs": pairs,
        "max_leads": pairs * min(req.max_results_per_pair, 2000),
        "poll": "/api/research/bulk/status",
    }


@router.get("/bulk/status")
def bulk_status():
    with _bulk_lock:
        return dict(_bulk_state)


# ── Hiring-first research ────────────────────────────────────────────────────
# Starts from live job postings (Google Jobs via SerpAPI — aggregates
# LinkedIn, Indeed, ZipRecruiter, company career pages) and works back to the
# business behind each posting, then runs the full enrichment pipeline with
# the hiring evidence pre-seeded. Quota: ~1 SerpAPI credit per ~10 postings
# + 1 Places lookup per company; the enricher's own 2 SerpAPI calls per lead
# are SKIPPED for these leads.

class HiringResearchRequest(BaseModel):
    city: str                        # e.g. "Austin, TX"
    role: str = "receptionist"       # the role being hired for
    industry: Optional[str] = None   # optional niche filter, e.g. "dental"
    country: Optional[str] = None
    max_results: int = 20            # businesses (not postings), up to 2000


def _run_hiring_job(req: HiringResearchRequest):
    with _bulk_lock:
        _bulk_state.update({
            "status": "running",
            "total_pairs": 1,
            "pairs_done": 0,
            "leads_found": 0,
            "current": f"hiring-first: {req.role} in {req.city}",
            "errors": [],
            "started_at": datetime.utcnow().isoformat(),
        })
    session = SessionLocal()
    try:
        orchestrator = LeadIntelligenceOrchestrator(session)
        results = orchestrator.run_hiring_research(
            city=req.city.strip(),
            role=req.role.strip() or "receptionist",
            industry=(req.industry or "").strip() or None,
            country=(req.country or "").strip() or None,
            max_results=min(req.max_results, 2000),
        )
        with _bulk_lock:
            _bulk_state["leads_found"] = len(results)
    except Exception as e:
        logger.error(f"[HiringResearch] Failed: {e}", exc_info=True)
        with _bulk_lock:
            _bulk_state["errors"].append(f"hiring-first {req.role} in {req.city}: {e}")
    finally:
        session.close()
        with _bulk_lock:
            _bulk_state["pairs_done"] = 1
            _bulk_state["status"] = "completed"
            _bulk_state["current"] = None
            _bulk_state["finished_at"] = datetime.utcnow().isoformat()


@router.post("/hiring")
def run_hiring_research(req: HiringResearchRequest, background_tasks: BackgroundTasks):
    """
    Find businesses that are ALREADY hiring the given role right now, and turn
    each into a fully-enriched lead (contacts, decision makers, pitch angle,
    outreach drafts). Always runs in the background — poll
    /api/research/bulk/status for progress.
    """
    if not req.city.strip():
        raise HTTPException(status_code=400, detail="City must not be empty")
    _reserve_bulk_slot()
    background_tasks.add_task(_run_hiring_job, req)
    return {
        "status": "started",
        "mode": "hiring",
        "role": req.role,
        "city": req.city,
        "poll": "/api/research/bulk/status",
    }


@router.post("/enrich-contacts")
def enrich_contacts(db: Session = Depends(get_db)):
    """
    Re-run deep contact extraction for every stored business with a website,
    and purge invalid emails everywhere. Fixes leads scraped by older versions.
    """
    businesses = db.query(Business).all()
    purged = 0

    # 1. Purge garbage emails stored by the old scraper
    for b in businesses:
        if b.email and not _valid_email(b.email):
            logger.info(f"[Enrich] Purging invalid email '{b.email}' from {b.name}")
            b.email = None
            purged += 1
    db.commit()

    targets = [
        (str(b.id), b.website, b.address)
        for b in businesses if b.website
    ]

    def _enrich_one(args):
        biz_id, website, address = args
        session = SessionLocal()
        try:
            extractor = ContactExtractor()
            region = region_from_address(address)
            contacts = extractor.run(website, region=region)
            b = session.query(Business).get(PyUUID(biz_id))
            if not b:
                return 0
            updated = 0
            if contacts["emails"]:
                b.email = contacts["emails"][0]
                b.emails = contacts["emails"]
                updated = 1
            if contacts["phones"]:
                b.phones = contacts["phones"]
                if not b.phone:
                    b.phone = contacts["phones"][0]
            if contacts["whatsapp"]:
                b.whatsapp = contacts["whatsapp"]
            if contacts.get("decision_makers"):
                b.decision_makers = contacts["decision_makers"]
            if contacts["socials"]:
                b.social_links = {**(b.social_links or {}), **contacts["socials"]}
            if contacts["contact_form_url"]:
                b.contact_form_url = contacts["contact_form_url"]
            session.commit()
            return updated
        except Exception as e:
            logger.warning(f"[Enrich] Failed for {biz_id}: {e}")
            return 0
        finally:
            session.close()

    emails_found = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_enrich_one, t) for t in targets]
        for f in as_completed(futures):
            emails_found += f.result()

    return {
        "status": "completed",
        "businesses_scanned": len(businesses),
        "websites_crawled": len(targets),
        "invalid_emails_purged": purged,
        "businesses_with_email_found": emails_found,
    }


# ── Decision-maker (PoC) research ────────────────────────────────────────────
# On-demand (not part of the default pipeline): each call costs ~2 SerpAPI
# searches + 2 LLM calls, and SerpAPI's free tier is ~100 searches/month.

def _research_poc_for_business(b: Business, session: Session) -> dict:
    poc = PocResearchAgent().run(
        business_name=b.name,
        city=b.city,
        website=b.website,
        known_decision_makers=b.decision_makers or [],
        known_business_phone=b.phone,
    )
    b.poc_contacts = poc["poc_contacts"]
    b.poc_researched_at = datetime.utcnow()
    session.commit()

    score = session.query(LeadScore).filter_by(business_id=b.id).first()
    report = session.query(LeadReport).filter_by(business_id=b.id).first()
    pain_evidence = (score.pain_breakdown or {}).get("evidence", []) if score else []
    qualification_reason = score.qualification_reason if score else ""

    drafts = ReportGenerator().generate_poc_outreach(
        business={"name": b.name, "category": b.category, "city": b.city},
        qualification_reason=qualification_reason or "",
        poc_contacts=poc["poc_contacts"],
        pain_evidence=pain_evidence,
    )
    if report:
        report.poc_outreach = drafts
    else:
        report = LeadReport(business_id=b.id, poc_outreach=drafts)
        session.add(report)
    session.commit()

    return {"poc_contacts": poc["poc_contacts"], "poc_outreach": drafts, "serpapi_used": poc["serpapi_used"]}


@router.post("/poc/{business_id}")
def research_poc(business_id: str, db: Session = Depends(get_db)):
    """
    Find the decision maker(s) for one business — names, titles, best-effort
    contact details (site + public web/LinkedIn search + pattern-inferred
    email as a last resort) — and generate a personalized outreach draft for
    each. Explicit per-lead action: costs SerpAPI + LLM calls.
    """
    try:
        biz_uuid = PyUUID(business_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Business not found")

    b = db.query(Business).filter(Business.id == biz_uuid).first()
    if not b:
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        return _research_poc_for_business(b, db)
    except Exception as e:
        logger.error(f"[PocAPI] Failed for {b.name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class PocBulkRequest(BaseModel):
    business_ids: Optional[list[str]] = None   # omit to target every lead missing PoC research
    limit: int = 20                            # safety cap on SerpAPI usage per call


@router.post("/poc/bulk")
def research_poc_bulk(req: PocBulkRequest, db: Session = Depends(get_db)):
    """Run PoC research over several leads at once (thread pool, own DB session per lead)."""
    if req.business_ids:
        try:
            uuids = [PyUUID(i) for i in req.business_ids]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid business_id in list")
        targets = db.query(Business).filter(Business.id.in_(uuids)).all()
    else:
        targets = (
            db.query(Business)
            .filter(Business.poc_researched_at.is_(None))
            .limit(min(req.limit, 100))
            .all()
        )

    ids = [str(b.id) for b in targets]

    def _run_one(biz_id: str) -> bool:
        session = SessionLocal()
        try:
            b = session.query(Business).get(PyUUID(biz_id))
            if not b:
                return False
            _research_poc_for_business(b, session)
            return True
        except Exception as e:
            logger.warning(f"[PocBulk] Failed for {biz_id}: {e}")
            return False
        finally:
            session.close()

    succeeded = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_run_one, i) for i in ids]
        for f in as_completed(futures):
            if f.result():
                succeeded += 1

    return {"status": "completed", "targeted": len(ids), "succeeded": succeeded}
