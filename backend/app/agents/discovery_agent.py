"""
Business Discovery Agent (Places API New)
=========================================
Discovers businesses using the Google Places API (New) searchText endpoint.
Falls back automatically to mock data if Google returns REQUEST_DENIED or other errors.

Input : industry (str), city (str), max_results (int)
Output: List[BusinessDiscovery] — structured business records
"""
import logging
import httpx
from typing import Optional
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


# ── Output Schema ────────────────────────────────────────────────────
class BusinessDiscovery(BaseModel):
    name: str
    category: str
    city: str
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    google_rating: Optional[float] = None
    review_count: Optional[int] = None
    opening_hours: Optional[dict] = None
    social_links: dict = Field(default_factory=dict)
    place_id: Optional[str] = None
    source: str = "google_places"


# ── Industry → Search Query Mapping ─────────────────────────────────
INDUSTRY_QUERIES = {
    "dental_clinics":      "dental clinic",
    "dermatology_clinics": "dermatology clinic skin clinic",
    "cosmetic_clinics":    "cosmetic clinic aesthetics",
    "fertility_clinics":   "fertility clinic IVF",
    "real_estate":         "real estate agency property",
    "coaching_institutes": "coaching institute tuition center",
    "premium_salons":      "premium salon beauty parlour",
}


class BusinessDiscoveryAgent:
    """
    Fetches businesses from Google Places API (New).
    """

    def __init__(self):
        self.api_key = settings.GOOGLE_PLACES_API_KEY
        self.client = httpx.Client(timeout=15.0)

    def run(self, industry: str, city: str, max_results: int = 20) -> list[BusinessDiscovery]:
        """
        Main entry point.
        Returns a list of BusinessDiscovery objects.
        """
        if not self.api_key:
            logger.warning("[DiscoveryAgent] No Google Places API key configured. Using mock data.")
            return self._mock_data(industry, city)

        query = INDUSTRY_QUERIES.get(industry, industry.replace("_", " "))
        search_query = f"{query} in {city}"

        logger.info(f"[DiscoveryAgent] Querying Places API (New): '{search_query}' (max={max_results})")

        try:
            # Places API (New) Text Search
            url = "https://places.googleapis.com/v1/places:searchText"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.formattedAddress,"
                    "places.internationalPhoneNumber,places.websiteUri,"
                    "places.rating,places.userRatingCount,places.regularOpeningHours,"
                    "nextPageToken"
                )
            }
            
            businesses = []
            page_token = None
            
            while len(businesses) < max_results:
                payload = {
                    "textQuery": search_query,
                    "maxResultCount": min(20, max_results - len(businesses))
                }
                if page_token:
                    payload["pageToken"] = page_token

                resp = self.client.post(url, headers=headers, json=payload)
                
                if resp.status_code != 200:
                    logger.error(f"[DiscoveryAgent] Google Places API returned status {resp.status_code}: {resp.text}")
                    if not businesses:
                        logger.warning("[DiscoveryAgent] Falling back to mock data due to API error.")
                        return self._mock_data(industry, city)
                    else:
                        break # return what we have so far

                data = resp.json()
                places = data.get("places", [])

                if not places:
                    if not businesses:
                        logger.info("[DiscoveryAgent] No results found from Places API. Using mock data.")
                        return self._mock_data(industry, city)
                    else:
                        break

                for p in places:
                    hours_desc = p.get("regularOpeningHours", {}).get("weekdayDescriptions")
                    open_now = p.get("regularOpeningHours", {}).get("openNow")
                    opening_hours = None
                    if hours_desc is not None:
                        opening_hours = {
                            "weekday_text": hours_desc,
                            "open_now": open_now
                        }

                    name = p.get("displayName", {}).get("text", "Unknown")
                    
                    businesses.append(
                        BusinessDiscovery(
                            name=name,
                            category=industry,
                            city=city,
                            phone=p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"),
                            website=p.get("websiteUri"),
                            address=p.get("formattedAddress"),
                            google_rating=p.get("rating"),
                            review_count=p.get("userRatingCount"),
                            opening_hours=opening_hours,
                            place_id=p.get("id"),
                            source="google_places"
                        )
                    )
                
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            logger.info(f"[DiscoveryAgent] Successfully fetched {len(businesses)} businesses from Google Places API.")
            return businesses

        except Exception as e:
            logger.error(f"[DiscoveryAgent] Places API error: {e}")
            logger.warning("[DiscoveryAgent] Falling back to mock data.")
            return self._mock_data(industry, city)

    def _mock_data(self, industry: str, city: str) -> list[BusinessDiscovery]:
        """Returns realistic mock data when API key fails or is missing."""
        return [
            BusinessDiscovery(
                name="Apollo Dental Mumbai Andheri",
                category=industry,
                city=city,
                phone="+91-22-4012-3456",
                website="https://apollodental.in",
                address="Link Road, Andheri West, Mumbai 400053",
                google_rating=4.3,
                review_count=1247,
                opening_hours={
                    "weekday_text": [
                        "Monday: 9:00 AM – 9:00 PM",
                        "Tuesday: 9:00 AM – 9:00 PM",
                        "Wednesday: 9:00 AM – 9:00 PM",
                        "Thursday: 9:00 AM – 9:00 PM",
                        "Friday: 9:00 AM – 9:00 PM",
                        "Saturday: 9:00 AM – 8:00 PM",
                        "Sunday: 10:00 AM – 6:00 PM",
                    ],
                    "open_now": True,
                },
                place_id="mock_001",
                source="mock",
            ),
            BusinessDiscovery(
                name="SmileZone Dental Care",
                category=industry,
                city=city,
                phone="+91-22-2614-8899",
                website=None,
                address="FC Road, Dadar West, Mumbai 400028",
                google_rating=4.1,
                review_count=389,
                opening_hours={
                    "weekday_text": [
                        "Monday: 10:00 AM – 8:00 PM",
                        "Tuesday: 10:00 AM – 8:00 PM",
                        "Wednesday: Closed",
                        "Thursday: 10:00 AM – 8:00 PM",
                        "Friday: 10:00 AM – 8:00 PM",
                        "Saturday: 10:00 AM – 7:00 PM",
                        "Sunday: Closed",
                    ],
                    "open_now": False,
                },
                place_id="mock_002",
                source="mock",
            ),
            BusinessDiscovery(
                name="Bright Smiles Dental Clinic",
                category=industry,
                city=city,
                phone="+91-22-2556-7890",
                website="https://brightsmilesdental.com",
                address="S.V. Road, Borivali West, Mumbai 400092",
                google_rating=4.6,
                review_count=782,
                opening_hours={
                    "weekday_text": [
                        "Monday: 9:00 AM – 10:00 PM",
                        "Tuesday: 9:00 AM – 10:00 PM",
                        "Wednesday: 9:00 AM – 10:00 PM",
                        "Thursday: 9:00 AM – 10:00 PM",
                        "Friday: 9:00 AM – 10:00 PM",
                        "Saturday: 9:00 AM – 9:00 PM",
                        "Sunday: 10:00 AM – 7:00 PM",
                    ],
                    "open_now": True,
                },
                place_id="mock_003",
                source="mock",
            ),
            BusinessDiscovery(
                name="Dr. Mehta's Multispeciality Dental",
                category=industry,
                city=city,
                phone="+91-22-4987-6543",
                website="https://drmehtadental.com",
                address="Linking Road, Bandra West, Mumbai 400050",
                google_rating=4.8,
                review_count=2134,
                opening_hours={
                    "weekday_text": [
                        "Monday: 8:00 AM – 11:00 PM",
                        "Tuesday: 8:00 AM – 11:00 PM",
                        "Wednesday: 8:00 AM – 11:00 PM",
                        "Thursday: 8:00 AM – 11:00 PM",
                        "Friday: 8:00 AM – 11:00 PM",
                        "Saturday: 8:00 AM – 10:00 PM",
                        "Sunday: 9:00 AM – 8:00 PM",
                    ],
                    "open_now": True,
                },
                place_id="mock_004",
                source="mock",
            ),
            BusinessDiscovery(
                name="Family Dental House",
                category=industry,
                city=city,
                phone=None,
                website=None,
                address="MG Road, Ghatkopar East, Mumbai 400077",
                google_rating=3.8,
                review_count=64,
                opening_hours=None,
                place_id="mock_005",
                source="mock",
            ),
        ]

