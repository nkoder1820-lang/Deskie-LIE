from app.agents.orchestrator import LeadIntelligenceOrchestrator
from app.agents.discovery_agent import INDUSTRY_QUERIES
from app.agents.contact_extractor import ContactExtractor, region_from_address, _valid_email
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
    """
    industry = req.industry.strip()
    if not industry:
        raise HTTPException(status_code=400, detail="Industry must not be empty")
    if not req.city.strip():
        raise HTTPException(status_code=400, detail="City must not be empty")

    try:
        orchestrator = LeadIntelligenceOrchestrator(db)
        results = orchestrator.run_research(
            industry=industry,
            city=req.city.strip(),
            max_results=min(req.max_results, 300),
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
    max_results_per_pair: int = 60   # up to 300 (query-variant fan-out)


_bulk_lock = threading.Lock()
_bulk_state: dict = {"status": "idle"}


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
                max_results=min(req.max_results_per_pair, 300),
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
    with _bulk_lock:
        if _bulk_state.get("status") == "running":
            raise HTTPException(status_code=409, detail="A bulk job is already running")
        _bulk_state["status"] = "running"  # reserve before the task actually starts
    background_tasks.add_task(_run_bulk_job, req)
    pairs = len([1 for i in req.industries for c in req.cities])
    return {
        "status": "started",
        "pairs": pairs,
        "max_leads": pairs * min(req.max_results_per_pair, 300),
        "poll": "/api/research/bulk/status",
    }


@router.get("/bulk/status")
def bulk_status():
    with _bulk_lock:
        return dict(_bulk_state)


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
