"""
Lead Enricher Agent
===================
Uses SerpAPI to find active hiring and google ads signals for the business.
Parses search results with NVIDIA NIM Llama 3.1.

Alongside the boolean signals, captures the REAL source link (job posting
URL, ad landing page) — but only the SPECIFIC item the LLM cites as its
evidence, by index, not just "whichever result came first". Grabbing the
first organic hit for a hiring query is unreliable: if Google's Jobs box
didn't fire, item #1 is very often just the business's own homepage (a
branded name search always ranks the business's own site first), which
would get mislabeled as "the job posting". Same risk on the ads side — the
SERP's ad carousel can include a competitor's ad alongside the target's.
Tying the surfaced link to the exact item the model says it used closes
both failure modes at once.
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
            "hiring_sources": [],
            "runs_google_ads": False,
            "ads_evidence": [],
            "ads_sources": [],
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

        # 3. Build numbered candidate lists so the LLM can cite exactly which
        # item backs its answer, instead of us guessing afterward.
        hiring_items = self._collect_hiring_items(hiring_results)
        ad_items = self._collect_ad_items(ads_results)

        parsed = self._parse_combined(business_name, hiring_items, ad_items)

        hiring_sources = self._resolve_indices(hiring_items, parsed.get("hiring_source_indices"))
        ads_sources = self._resolve_indices(ad_items, parsed.get("ads_source_indices"))

        # Fallback: if the LLM said "yes, hiring" but didn't cite an index
        # (parsing hiccup), trust a job from the structured Jobs box only —
        # that field is always a genuine listing, never a generic web hit.
        if parsed.get("is_hiring_any") and not hiring_sources:
            structured = [i for i in hiring_items if i["kind"] == "job"]
            hiring_sources = structured[:1]

        return {
            "is_hiring_receptionist": parsed.get("is_hiring_receptionist", False),
            "is_hiring_any": parsed.get("is_hiring_any", False),
            "hiring_evidence": parsed.get("hiring_evidence", []),
            "hiring_sources": [{"title": i["title"], "url": i["url"]} for i in hiring_sources[:3]],
            "runs_google_ads": parsed.get("runs_google_ads", False),
            "ads_evidence": parsed.get("ads_evidence", []),
            "ads_sources": [{"title": i["title"], "url": i["url"]} for i in ads_sources[:3]],
        }

    # ── Build numbered candidates ────────────────────────────────────────────
    def _collect_hiring_items(self, hiring_results: dict) -> list[dict]:
        items = []
        for job in (hiring_results or {}).get("jobs_results", [])[:5]:
            url = job.get("link") or job.get("job_google_link")
            if not url:
                for opt in job.get("apply_options") or []:
                    if opt.get("link"):
                        url = opt["link"]
                        break
            if not url:
                continue
            title = f"{job.get('title', 'Job posting')} at {job.get('company_name', '')}".strip()
            items.append({
                "kind": "job", "title": title[:120], "url": url,
                "snippet": title,
            })
        for result in (hiring_results or {}).get("organic_results", [])[:5]:
            if not result.get("link"):
                continue
            items.append({
                "kind": "organic",
                "title": (result.get("title") or "Search result")[:120],
                "url": result["link"],
                "snippet": result.get("snippet") or "",
            })
        return items

    def _collect_ad_items(self, ads_results: dict) -> list[dict]:
        items = []
        for ad in (ads_results or {}).get("ads", []):
            url = ad.get("link") or ad.get("tracking_link")
            if not url:
                continue
            title = ad.get("title") or ad.get("headline") or "Ad"
            items.append({
                "kind": "ad", "title": title[:120], "url": url,
                "snippet": ad.get("description") or "",
            })
        return items

    def _resolve_indices(self, items: list[dict], indices) -> list[dict]:
        if not indices:
            return []
        resolved = []
        for i in indices:
            try:
                idx = int(i)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(items):
                resolved.append(items[idx])
        return resolved

    # ── LLM parse — must cite evidence by index, never invent a link ────────
    def _parse_combined(self, business_name: str, hiring_items: list[dict], ad_items: list[dict]) -> dict:
        if not hiring_items and not ad_items:
            return {}

        hiring_lines = [f"[{i}] ({it['kind']}) {it['title']}: {it['snippet']}"[:300] for i, it in enumerate(hiring_items)]
        ad_lines = [f"[{i}] {it['title']}: {it['snippet']}"[:300] for i, it in enumerate(ad_items)]

        system = """You are an intelligence analyst. Based on numbered Google search results and ads, determine:
1. whether the target business is actively hiring (especially receptionist / front-desk roles)
2. whether the target business itself (not a competitor, not an unrelated business with a similar name) is running Google ads

Return ONLY valid JSON:
{
  "is_hiring_receptionist": <boolean>,
  "is_hiring_any": <boolean>,
  "hiring_evidence": [<quotes or job titles demonstrating they are hiring>],
  "hiring_source_indices": [<indices from the numbered Hiring Results list that DIRECTLY show a job posting or hiring page for THIS business — NOT the business's own homepage/about/menu page just because it ranked highly. Empty list if none of the numbered items are an actual job listing, even if is_hiring_any is true.>],
  "runs_google_ads": <boolean>,
  "ads_evidence": [<ad copy strings from the target business's own ads>],
  "ads_source_indices": [<indices from the numbered Ads list that are confirmed to be the TARGET business's own ad, not a competitor's>]
}"""
        user = (
            f"Target Business: {business_name}\n\n"
            "Hiring Results (numbered):\n" + ("\n".join(hiring_lines) or "(none)") + "\n\n"
            "Ads Found (numbered):\n" + ("\n".join(ad_lines) or "(none)")
        )
        result = call_nvidia(system, user, max_tokens=512)
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
