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

        # 3. Parse with NVIDIA NIM
        parsed_hiring = self._parse_hiring(business_name, hiring_results)
        parsed_ads = self._parse_ads(business_name, ads_results)

        return {
            "is_hiring_receptionist": parsed_hiring.get("is_hiring_receptionist", False),
            "is_hiring_any": parsed_hiring.get("is_hiring_any", False),
            "hiring_evidence": parsed_hiring.get("hiring_evidence", []),
            "runs_google_ads": parsed_ads.get("runs_google_ads", False),
            "ads_evidence": parsed_ads.get("ads_evidence", []),
        }

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

    def _parse_hiring(self, business_name: str, search_results: dict) -> dict:
        if not search_results:
            return {}
            
        snippets = []
        for result in search_results.get("organic_results", [])[:5]:
            snippets.append(f"- {result.get('title')}: {result.get('snippet')}")
        
        for job in search_results.get("jobs_results", [])[:5]:
            snippets.append(f"- JOB POSTING: {job.get('title')} at {job.get('company_name')}")

        if not snippets:
            return {}

        system = """You are an intelligence analyst. Based on the Google search snippets provided, determine if the business is actively hiring.
Return ONLY valid JSON:
{
  "is_hiring_receptionist": <boolean>,
  "is_hiring_any": <boolean>,
  "hiring_evidence": [<list of strings (quotes or job titles) demonstrating they are hiring>]
}"""
        user = f"Business: {business_name}\nSearch Snippets:\n" + "\n".join(snippets)
        result = call_nvidia(system, user, max_tokens=256)
        return result if result else {}

    def _parse_ads(self, business_name: str, search_results: dict) -> dict:
        if not search_results:
            return {}

        ads = search_results.get("ads", [])
        if not ads:
            return {"runs_google_ads": False, "ads_evidence": []}

        snippets = []
        for ad in ads:
            title = ad.get('title') or ad.get('headline') or ''
            desc = ad.get('description') or ''
            snippets.append(f"- AD: {title}: {desc}")

        if not snippets:
            return {"runs_google_ads": False, "ads_evidence": []}

        system = """You are an intelligence analyst. Based on the Google ads provided, determine if the target business is the one running the ad (and not a competitor).
Return ONLY valid JSON:
{
  "runs_google_ads": <boolean>,
  "ads_evidence": [<list of strings showing the ad copy>]
}"""
        user = f"Target Business: {business_name}\nAds Found:\n" + "\n".join(snippets)
        result = call_nvidia(system, user, max_tokens=256)
        return result if result else {}
