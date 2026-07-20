"""
Signal Definitions
==================
All scoring signals, their weights, and helper functions for detecting them
from research data. This is the single source of truth for scoring logic.
"""

# ── Pain Score Signals (40% of final) ───────────────────────────────────────
PAIN_SIGNALS = {
    "phone_dependency":      0.25,   # Business relies on phone for bookings
    "no_booking_automation": 0.15,   # No online booking / booking link detected
    "negative_call_reviews": 0.20,   # Reviews mention missed calls / no answer
    "receptionist_hiring":   0.20,   # Job postings for receptionist/front desk
    "extended_hours":        0.10,   # Open beyond 8 PM or 7 days a week
    "after_hours_leak":      0.10,   # Closed on weekends or early + no booking
}

# ── Business Value Score Signals (25% of final) ─────────────────────────────
VALUE_SIGNALS = {
    "industry_value":  0.30,   # High-value industry (dental = high)
    "location_tier":   0.20,   # Metro / tier-1 city premium
    "review_volume":   0.20,   # High review count = popular business
    "customer_value":  0.20,   # High per-customer revenue potential
    "business_size":   0.10,   # Estimated size from reviews + hours
}

# ── Digital Adoption Score Signals (20% of final) ───────────────────────────
DIGITAL_SIGNALS = {
    "has_website":       0.20,
    "runs_ads":          0.30,   # Google Ads / Meta Ads detected
    "social_activity":   0.20,   # Active Instagram / Facebook presence
    "existing_software": 0.20,   # CRM / booking software already in use (adoption indicator)
    "online_presence":   0.10,   # Listed on Practo / Justdial / similar
}

# ── Buying Timing Score Signals (15% of final) ──────────────────────────────
TIMING_SIGNALS = {
    "is_hiring":         0.30,   # Recently posted jobs
    "expanding":         0.20,   # Opening new branches / locations
    "marketing_activity":0.30,   # Active ads / promotions
    "recent_growth":     0.20,   # Growing reviews / new ratings
}

# ── Industry Value Multipliers ───────────────────────────────────────────────
# Scale 0.0 – 1.0 representing revenue potential / Deskie value
INDUSTRY_VALUE_MAP = {
    "dental_clinics":       1.0,
    "dermatology_clinics":  0.95,
    "cosmetic_clinics":     0.95,
    "fertility_clinics":    1.0,
    "med_spas":             0.95,
    "veterinary_clinics":   0.90,
    "chiropractors":        0.90,
    "physiotherapy":        0.85,
    "law_firms":            0.95,
    "hvac_services":        0.90,
    "plumbers":             0.90,
    "roofing":              0.90,
    "auto_repair":          0.80,
    "real_estate":          0.85,
    "property_management":  0.85,
    "coaching_institutes":  0.70,
    "premium_salons":       0.75,
    "restaurants":          0.60,
    "default":              0.70,
}

# Keyword fallback so free-text industries ("cosmetic dentist", "immigration
# lawyer", "hvac repair") still get a sensible value multiplier.
_INDUSTRY_KEYWORD_VALUES = [
    (("dental", "dentist", "orthodont"), 1.0),
    (("fertility", "ivf"), 1.0),
    (("law", "attorney", "legal"), 0.95),
    (("derma", "skin", "cosmetic", "aesthetic", "med spa", "medspa", "plastic"), 0.95),
    (("hvac", "plumb", "roof", "electrician", "pest"), 0.90),
    (("vet", "animal"), 0.90),
    (("chiro", "physio", "physical therapy", "ortho"), 0.88),
    (("clinic", "medical", "doctor", "health"), 0.85),
    (("real estate", "property", "realtor", "broker"), 0.85),
    (("auto", "mechanic", "car "), 0.80),
    (("salon", "spa", "beauty", "barber"), 0.75),
    (("coaching", "tuition", "academy", "school"), 0.70),
    (("restaurant", "cafe", "food"), 0.60),
]


def industry_value(category: str | None) -> float:
    """Value multiplier for a preset key OR free-text industry."""
    if not category:
        return INDUSTRY_VALUE_MAP["default"]
    if category in INDUSTRY_VALUE_MAP:
        return INDUSTRY_VALUE_MAP[category]
    low = category.replace("_", " ").lower()
    for keywords, value in _INDUSTRY_KEYWORD_VALUES:
        if any(kw in low for kw in keywords):
            return value
    return INDUSTRY_VALUE_MAP["default"]


# ── Location Tier Multipliers ────────────────────────────────────────────────
LOCATION_TIER_MAP = {
    # India metros
    "Mumbai": 1.0, "Delhi": 1.0, "Bangalore": 1.0, "Bengaluru": 1.0,
    "Hyderabad": 0.90, "Chennai": 0.90, "Pune": 0.85, "Kolkata": 0.80,
    "Ahmedabad": 0.80, "Jaipur": 0.75, "Surat": 0.75,
    # US metros (high willingness-to-pay markets)
    "New York": 1.0, "Los Angeles": 1.0, "San Francisco": 1.0, "Chicago": 0.95,
    "Houston": 0.95, "Dallas": 0.95, "Miami": 0.95, "Austin": 0.95,
    "Seattle": 0.95, "Boston": 0.95, "Atlanta": 0.90, "Phoenix": 0.90,
    "San Diego": 0.90, "Denver": 0.90, "Charlotte": 0.85, "Tampa": 0.85,
    # Other global hubs
    "London": 1.0, "Toronto": 0.95, "Sydney": 0.95, "Dubai": 0.95, "Singapore": 0.95,
    "default": 0.80,
}


def location_tier(city: str | None) -> float:
    """Tier for exact match or partial match ('Austin, TX' → Austin)."""
    if not city:
        return LOCATION_TIER_MAP["default"]
    if city in LOCATION_TIER_MAP:
        return LOCATION_TIER_MAP[city]
    low = city.lower()
    for known, tier in LOCATION_TIER_MAP.items():
        if known != "default" and known.lower() in low:
            return tier
    return LOCATION_TIER_MAP["default"]

# ── Call Pain Keywords (Review Intelligence) ─────────────────────────────────
CALL_PAIN_KEYWORDS = [
    # English
    "nobody answered", "no one answered", "didn't pick up", "did not pick up",
    "call not answered", "phone not answered", "couldn't reach",
    "no response", "no reply", "not reachable", "unreachable",
    "waiting", "waited long", "waited a lot", "on hold",
    "busy line", "line busy", "engaged", "couldn't connect",
    "appointment", "booking", "book", "schedule", "reschedule",
    "missed call", "callback", "called back",
    # Hinglish / Indian English
    "call nahi", "utha nahi", "busy tha", "nahi mila",
    "appointment nahi", "response nahi",
]

# ── Extended Hours Detection ─────────────────────────────────────────────────
def has_extended_hours(opening_hours: dict | None) -> bool:
    """Returns True if business is open past 8 PM or on Sundays."""
    if not opening_hours:
        return False
    texts = opening_hours.get("weekday_text", [])
    for line in texts:
        line_lower = line.lower()
        # Check for late closing
        for hour in ["9:00 pm", "10:00 pm", "11:00 pm", "9 pm", "10 pm", "11 pm"]:
            if hour in line_lower:
                return True
        # Check Sunday open
        if "sunday" in line_lower and "closed" not in line_lower:
            return True
    return False

def is_7_days(opening_hours: dict | None) -> bool:
    """Returns True if business is open all 7 days."""
    if not opening_hours:
        return False
    texts = opening_hours.get("weekday_text", [])
    closed_count = sum(1 for t in texts if "closed" in t.lower())
    return len(texts) >= 7 and closed_count == 0
