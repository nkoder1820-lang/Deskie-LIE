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
    "real_estate":          0.85,
    "coaching_institutes":  0.70,
    "premium_salons":       0.75,
    "default":              0.60,
}

# ── Location Tier Multipliers ────────────────────────────────────────────────
LOCATION_TIER_MAP = {
    "Mumbai":     1.0,
    "Delhi":      1.0,
    "Bangalore":  1.0,
    "Hyderabad":  0.90,
    "Chennai":    0.90,
    "Pune":       0.85,
    "Kolkata":    0.80,
    "Ahmedabad":  0.80,
    "Jaipur":     0.75,
    "Surat":      0.75,
    "default":    0.65,
}

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
