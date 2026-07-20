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
