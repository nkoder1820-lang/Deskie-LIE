"""
Apollo.io Decision-Maker Agent
==============================
Primary provider for PoC (decision-maker) research: real people with real
titles, LinkedIn profiles, and — where credits allow — VERIFIED work emails.
Replaces pattern-guessed emails ("alfie@domain.com, unverified") with
deliverable ones, which is the single biggest outreach-conversion lever.

Key pooling: APOLLO_API_KEYS is comma-separated; on a quota/auth error
(401/402/403/429) the next key is tried, same pattern as the Gemini pool.
The SerpAPI PoC agent remains the fallback when Apollo is unconfigured or
returns nothing for a business.

Credit economics: people *search* is cheap/free-tier friendly; unlocking an
email via people/match consumes one email credit. We only unlock for the top
few title-matched people per business.
"""
import logging
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Who actually decides to buy an AI receptionist at an SMB.
_DECISION_TITLES = [
    "owner", "founder", "co-founder", "ceo", "president",
    "office manager", "practice manager", "clinic manager",
    "general manager", "managing partner", "managing director", "director",
]

_ROTATE_STATUSES = (401, 402, 403, 429)  # bad key / out of credits / throttled


class ApolloAgent:
    def __init__(self):
        raw = [k.strip() for k in (settings.APOLLO_API_KEYS or "").split(",") if k.strip()]
        seen: set[str] = set()
        self.keys = [k for k in raw if not (k in seen or seen.add(k))]
        self._idx = 0
        self.client = httpx.Client(timeout=20.0)

    @property
    def configured(self) -> bool:
        return bool(self.keys)

    # ── HTTP with key rotation ──────────────────────────────────────────────
    def _post(self, path: str, payload: dict) -> dict | None:
        last_err = None
        for attempt in range(len(self.keys)):
            i = (self._idx + attempt) % len(self.keys)
            try:
                r = self.client.post(
                    f"https://api.apollo.io/v1{path}",
                    json=payload,
                    headers={
                        "X-Api-Key": self.keys[i],
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                    },
                )
                if r.status_code in _ROTATE_STATUSES:
                    last_err = f"key #{i}: HTTP {r.status_code}"
                    logger.info(f"[Apollo] {last_err} — rotating to next key")
                    continue
                r.raise_for_status()
                self._idx = i  # stick with the key that worked
                return r.json()
            except Exception as e:  # noqa: BLE001
                last_err = str(e)[:150]
        logger.warning(f"[Apollo] all {len(self.keys)} key(s) failed: {last_err}")
        return None

    # ── Main entry ──────────────────────────────────────────────────────────
    def run(self, business_name: str, website: str | None = None,
            city: str | None = None, max_contacts: int = 3) -> dict:
        """Returns {"poc_contacts": [...], "provider": "apollo"} in the exact
        shape PocResearchAgent produces, so downstream (storage, outreach
        drafts, CSV, UI) needs no changes."""
        result = {"poc_contacts": [], "provider": "apollo"}
        if not self.configured:
            return result

        domain = self._domain(website)
        payload: dict = {"page": 1, "per_page": 10, "person_titles": _DECISION_TITLES}
        if domain:
            payload["q_organization_domains"] = domain
        else:
            # Without a domain, name+location keeps false matches down.
            payload["q_organization_name"] = business_name
            if city:
                payload["person_locations"] = [city]

        data = self._post("/mixed_people/search", payload)
        people = (data or {}).get("people") or []
        logger.info(f"[Apollo] {len(people)} people found for {business_name} ({domain or 'no domain'})")

        contacts = []
        for p in people:
            if len(contacts) >= max_contacts:
                break
            name = (p.get("name") or f"{p.get('first_name', '')} {p.get('last_name', '')}").strip()
            if not name:
                continue
            email = p.get("email")
            if not email or "email_not_unlocked" in email:
                email = self._unlock_email(p, domain, business_name)
            verified = bool(email)
            contacts.append({
                "name": name,
                "title": p.get("title") or "",
                "emails": [email] if email else [],
                "guessed_emails": [],
                "phones": [],
                "linkedin_url": p.get("linkedin_url"),
                "confidence": "verified_apollo" if verified else "public_search",
                "source": "Apollo.io — verified work email" if verified else "Apollo.io — profile match (no email credit spent/found)",
            })
        result["poc_contacts"] = contacts
        return result

    # ── Helpers ─────────────────────────────────────────────────────────────
    def _unlock_email(self, p: dict, domain: str | None, org_name: str) -> str | None:
        """People search hides emails; people/match spends one email credit to
        reveal a verified address. Only called for title-matched people."""
        payload: dict = {
            "first_name": p.get("first_name"),
            "last_name": p.get("last_name"),
            "organization_name": org_name,
            "reveal_personal_emails": False,
        }
        if domain:
            payload["domain"] = domain
        data = self._post("/people/match", payload)
        email = ((data or {}).get("person") or {}).get("email")
        if email and "@" in email and "email_not_unlocked" not in email:
            return email
        return None

    @staticmethod
    def _domain(website: str | None) -> str | None:
        if not website:
            return None
        try:
            host = (urlparse(website).netloc or "").lower()
        except Exception:  # noqa: BLE001
            return None
        host = host.removeprefix("www.")
        return host or None
