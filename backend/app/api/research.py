from app.agents.orchestrator import LeadIntelligenceOrchestrator
from app.agents.discovery_agent import INDUSTRY_QUERIES
from app.models.business import Business, LeadScore, LeadReport, ResearchResult
from app.database import get_db

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research", tags=["Research"])


class ResearchRequest(BaseModel):
    industry: str           # e.g. "dental_clinics"
    city: str               # e.g. "Mumbai"
    max_results: int = 20


class ResearchResponse(BaseModel):
    status: str
    message: str
    leads_count: int = 0


# Track running jobs (simple in-memory for MVP)
_running_jobs: dict[str, str] = {}


@router.get("/industries")
def list_industries():
    """List all supported industries."""
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
    Kick off a full research pipeline for an industry + city.
    Runs synchronously for MVP (background task in future).
    """
    if req.industry not in INDUSTRY_QUERIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown industry: {req.industry}. Supported: {list(INDUSTRY_QUERIES.keys())}"
        )

    try:
        orchestrator = LeadIntelligenceOrchestrator(db)
        results = orchestrator.run_research(
            industry=req.industry,
            city=req.city,
            max_results=min(req.max_results, 60),
        )
        return ResearchResponse(
            status="completed",
            message=f"Research complete for {req.industry} in {req.city}",
            leads_count=len(results),
        )
    except Exception as e:
        logger.error(f"[ResearchAPI] Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
