from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/deskie_lie"

    # Google Places
    GOOGLE_PLACES_API_KEY: str = ""

    # NVIDIA NIM
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_MODEL: str = "meta/llama-3.1-70b-instruct"

    # SerpAPI (optional)
    SERPAPI_KEY: Optional[str] = None

    # Adzuna (free official jobs API — primary provider for hiring-first
    # discovery; register at developer.adzuna.com)
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""

    # Jooble (free jobs API, key granted at jooble.org/api/about) — runs
    # ALONGSIDE Adzuna in hiring-first discovery; results are merged and
    # deduped by company. Comma-separated keys rotate on errors.
    JOOBLE_API_KEYS: str = ""

    # Apollo.io — verified decision-maker contacts (primary PoC provider;
    # SerpAPI PoC research becomes the fallback). Comma-separated keys are
    # pooled: on a quota/auth error the next key is tried.
    APOLLO_API_KEYS: str = ""

    # Per-lead hiring/ads verification during CLASSIC research costs 2 SerpAPI
    # searches per lead — the #1 quota drain (149 leads ≈ 300 searches). Off by
    # default; scoring still works from website/review/social signals, and
    # hiring-first leads carry their own posting evidence anyway.
    ENABLE_SERPAPI_ENRICHER: bool = False

    # Outreach sending (optional — Resend API)
    RESEND_API_KEY: str = ""
    OUTREACH_FROM_EMAIL: str = ""      # e.g. "Deskie <hello@yourdomain.com>" (verified in Resend)
    OUTREACH_REPLY_TO: str = ""        # optional reply-to address

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
