"""
Deskie Lead Intelligence Engine — FastAPI Application
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.api import research, businesses

# Import models to register them with SQLAlchemy
import app.models.business  # noqa: F401

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


from sqlalchemy import text

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup (dev mode)."""
    logger.info("🚀 Deskie LIE starting up...")
    Base.metadata.create_all(bind=engine)
    
    # Run dynamic schema migrations
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE businesses ADD COLUMN email VARCHAR(256)"))
            logger.info("Added 'email' column to businesses")
        except Exception:
            pass

        try:
            conn.execute(text("ALTER TABLE businesses ADD COLUMN detected_tech JSON"))
            logger.info("Added 'detected_tech' column to businesses")
        except Exception:
            pass

        try:
            conn.execute(text("ALTER TABLE lead_scores ADD COLUMN pitch_angle VARCHAR(128)"))
            logger.info("Added 'pitch_angle' column to lead_scores")
        except Exception:
            pass

        try:
            conn.execute(text("ALTER TABLE lead_scores ADD COLUMN qualification_reason TEXT"))
            logger.info("Added 'qualification_reason' column to lead_scores")
        except Exception:
            pass
            
    logger.info("✅ Database tables ready")
    yield
    logger.info("👋 Deskie LIE shutting down")


app = FastAPI(
    title="Deskie Lead Intelligence Engine",
    description="AI-powered lead scoring and intelligence for Deskie AI Receptionist",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(research.router)
app.include_router(businesses.router)


@app.get("/")
def root():
    return {
        "service": "Deskie Lead Intelligence Engine",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
