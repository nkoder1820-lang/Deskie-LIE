"""
Lead Enricher Agent
===================
Uses SerpAPI to find active hiring and google ads signals for the business.
Parses search results with NVIDIA NIM Llama 3.1.
"""
import logging
import httpx
from typing import Optional, List
from app.config import settings
from app.agents.nvidia_client import call_nvidia

logger = logging.getLogger(__name__)

class LeadEnricherAgent:
    def run(self, business_name: str, city: str) -> dict:
        default_response = {
            "is_hiring_receptionist": False,
            "is_hiring_any": False,
            "hiring_evidence": [],
            "runs_google_ads": False,
            "ads_evidence": [],
        }

        if not settings.SERPAPI_KEY:
            logger.warning("SERPAPI_KEY not set. Skipping LeadEnricherAgent.")
            return default_response

        # 1. Check Hiring
        hiring_query = f'"{business_name}" {city} (hiring OR jobs OR careers OR receptionist OR "front desk" OR assistant)'
        hiring_results = self._search_serpapi(hiring_query)

        # 2. Check Ads
        ads_query = f'"{business_name}" {city}'
        ads_results = self._search_serpapi(ads_query)

        # 3. Parse both with a single NVIDIA NIM call
        parsed = self._parse_combined(business_name, hiring_results, ads_results)

        return {
            "is_hiring_receptionist": parsed.get("is_hiring_receptionist", False),
            "is_hiring_any": parsed.get("is_hiring_any", False),
            "hiring_evidence": parsed.get("hiring_evidence", []),
            "runs_google_ads": parsed.get("runs_google_ads", False),
            "ads_evidence": parsed.get("ads_evidence", []),
        }

    def _parse_combined(self, business_name: str, hiring_results: dict, ads_results: dict) -> dict:
        """One LLM call for both hiring and ads signals."""
        hiring_snippets = []
        for result in (hiring_results or {}).get("organic_results", [])[:5]:
            hiring_snippets.append(f"- {result.get('title')}: {result.get('snippet')}")
        for job in (hiring_results or {}).get("jobs_results", [])[:5]:
            hiring_snippets.append(f"- JOB POSTING: {job.get('title')} at {job.get('company_name')}")

        ad_snippets = []
        for ad in (ads_results or {}).get("ads", []):
            title = ad.get('title') or ad.get('headline') or ''
            desc = ad.get('description') or ''
            ad_snippets.append(f"- AD: {title}: {desc}")

        if not hiring_snippets and not ad_snippets:
            return {}

        system = """You are an intelligence analyst. Based on Google search snippets and ads, determine:
1. whether the target business is actively hiring (especially receptionist / front-desk roles)
2. whether the target business itself (not a competitor) is running Google ads
Return ONLY valid JSON:
{
  "is_hiring_receptionist": <boolean>,
  "is_hiring_any": <boolean>,
  "hiring_evidence": [<quotes or job titles demonstrating they are hiring>],
  "runs_google_ads": <boolean>,
  "ads_evidence": [<ad copy strings from the target business's own ads>]
}"""
        user = (
            f"Target Business: {business_name}\n\n"
            "Hiring Search Snippets:\n" + ("\n".join(hiring_snippets) or "(none)") + "\n\n"
            "Ads Found:\n" + ("\n".join(ad_snippets) or "(none)")
        )
        result = call_nvidia(system, user, max_tokens=384)
        return result if result else {}

    def _search_serpapi(self, query: str) -> dict:
        try:
            url = "https://serpapi.com/search"
            params = {
                "q": query,
                "api_key": settings.SERPAPI_KEY,
                "engine": "google"
            }
            response = httpx.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"SerpAPI search failed for query '{query}': {e}")
            return {}

