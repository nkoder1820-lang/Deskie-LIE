"""
ICP (Ideal Customer Profile) gate + fit assessment
==================================================
Deskie's buyer is a single-location SMB with a real front desk — clinics,
salons, firms, restaurants. NOT national chains, franchises, casinos,
dealership groups, staffing agencies or B2B offices: they show the same
hiring signals but a branch manager can't buy, and most already run a
contact centre.

Every check is a deterministic zero-cost heuristic over data already stored
(name, phone, website, review count, Google's own place types) — no LLM, no
API calls — so it runs at read time and applies retroactively to every lead
ever collected.

Fit levels:
  "good"       — matches the ICP profile
  "borderline" — worth a look, but signals suggest a larger operation
  "excluded"   — clear non-ICP
"""
import re
from urllib.parse import urlparse

# Word-boundary wrapper. Built from a plain list so a name can never be
# silently broken by escaping — an earlier revision lost its boundaries to
# string escaping and matched nothing at all.
def _boundary_re(names: list[str]) -> re.Pattern:
    return re.compile(
        r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE
    )


# Staffing / recruiting agencies post most receptionist ads on aggregators —
# pure noise for us: the role isn't at their own office.
_STAFFING_NAMES = [
    "staffing", "recruiting", "recruitment", "recruiters", "employment agency",
    "personnel", "talent acquisition", "talent solutions", "talent group",
    "talent partners", "robert half", "adecco", "randstad", "manpower",
    "kelly services", "aerotek", "insight global", "express employment",
    "pridestaff", "spherion", "teksystems", "staffmark", "kforce",
    "michael page", "hays recruitment", "workforce solutions",
    "professional resources", "staffing solutions", "temp agency",
    "temporary services",
]
_STAFFING_RE = _boundary_re(_STAFFING_NAMES)

# National/global chains and franchises.
_CHAIN_NAMES = [
    # hospitality
    "marriott", "hilton", "hyatt", "sheraton", "radisson", "westin",
    "holiday inn", "ramada", "novotel", "four seasons", "ritz-carlton",
    "ritz carlton", "intercontinental", "doubletree", "courtyard by marriott",
    "fairfield inn", "residence inn", "best western", "wyndham", "wynn",
    "mgm grand", "caesars palace", "encore boston harbor", "oyo rooms",
    "lemon tree hotel", "ibis hotel",
    # auto brands / dealer groups
    "volkswagen", "toyota", "honda", "hyundai", "nissan", "mercedes-benz",
    "mercedes benz", "chevrolet", "land rover", "porsche", "lexus", "subaru",
    "maruti suzuki", "bmw", "audi", "kia motors", "mazda", "jaguar",
    # F&B / retail chains
    "starbucks", "mcdonald", "mcdonald's", "domino's", "dominos pizza",
    "pizza hut", "burger king", "dunkin", "costa coffee", "cafe coffee day",
    "kfc", "walmart", "costco", "walgreens", "cvs pharmacy",
    # healthcare / services chains
    "apollo hospital", "apollo hospitals", "fortis hospital", "manipal hospital",
    "max healthcare", "narayana health", "cloudnine hospital", "aspen dental",
    "pacific dental", "lenskart", "titan eye",
]
_CHAIN_RE = _boundary_re(_CHAIN_NAMES)

# Indian brand words that are ALSO ordinary local names ("Envi Salon & Spa -
# Oberoi Mall", a "Taj Dental Clinic"). Only the chain when a hospitality or
# hospital qualifier follows.
_AMBIGUOUS_CHAIN_RE = re.compile(
    r"\b(taj|oberoi|leela|itc|aster)\s+(hotel|hotels|palace|resort|resorts|hospital|hospitals)\b",
    re.IGNORECASE,
)

# B2B / corporate offices: real businesses, but nobody phones them to book, so
# an AI receptionist has nothing to answer.
_B2B_NAMES = [
    "venture", "ventures", "venture partners", "capital partners",
    "private equity", "holdings", "technologies", "software", "infotech",
    "analytics", "consultancy", "consulting", "advisory", "media agency",
    "advertising agency", "digital agency", "digital marketing agency",
    "saas", "fintech",
]
_B2B_RE = _boundary_re(_B2B_NAMES)

# Consumer verticals where phone/walk-in customers ARE the business. Guards
# the B2B and ambiguous rules so "Smile Technologies Dental" stays a lead.
_CONSUMER_NAMES = [
    "dental", "dentist", "clinic", "clinics", "hospital", "medical", "health",
    "salon", "spa", "beauty", "hair", "aesthetics", "dermatology", "skin",
    "restaurant", "cafe", "coffee", "kitchen", "bakery", "dining",
    "gym", "fitness", "yoga", "wellness", "physiotherapy", "physio",
    "law", "legal", "advocate", "attorney", "realty", "real estate",
    "property", "fertility", "ivf", "veterinary", "diagnostic", "diagnostics",
    "pathology", "academy", "school", "tutor", "coaching", "garage",
    "auto repair", "optical", "eye care", "pharmacy", "nursing",
]
_CONSUMER_RE = _boundary_re(_CONSUMER_NAMES)

_US_TOLL_FREE = ("800", "833", "844", "855", "866", "877", "888")

# Google Places types that structurally can't be a bookable front desk.
_BAD_PLACE_TYPES = {
    "casino", "shopping_mall", "department_store", "supermarket", "grocery_store",
    "convenience_store", "gas_station", "bank", "atm", "airport", "train_station",
    "bus_station", "subway_station", "transit_station", "parking", "stadium",
    "amusement_park", "tourist_attraction", "museum", "park", "church", "mosque",
    "hindu_temple", "synagogue", "city_hall", "local_government_office",
    "courthouse", "police", "fire_station", "post_office", "university",
    "primary_school", "secondary_school", "library", "cemetery", "storage",
    "moving_company", "corporate_office",
}


def is_chain(name: str | None) -> bool:
    n = name or ""
    return bool(_CHAIN_RE.search(n) or _AMBIGUOUS_CHAIN_RE.search(n))


def is_staffing_agency(name: str | None) -> bool:
    return bool(_STAFFING_RE.search(name or ""))


def _is_toll_free(phone: str | None) -> bool:
    digits = re.sub(r"[^\d+]", "", phone or "")
    if digits.startswith("+1") and len(digits) >= 5 and digits[2:5] in _US_TOLL_FREE:
        return True
    # India's national toll-free prefix (e.g. "+91 1800 268 4000").
    if digits.startswith("+911800"):
        return True
    return False


def _is_brand_subpage(website: str | None) -> bool:
    """A Places website like fsresidential.com/new-york (a city path on a
    larger brand site) is the classic multi-location signature. Root-domain
    sites — the norm for true SMBs — pass clean."""
    if not website:
        return False
    try:
        path = (urlparse(website).path or "/").strip("/").lower()
    except Exception:  # noqa: BLE001
        return False
    if not path:
        return False
    first = path.split("/")[0]
    return first not in ("index.html", "index.php", "index", "home", "en", "en-us", "en-in", "site")


def assess_icp(
    name: str | None,
    category: str | None = None,
    phone: str | None = None,
    phones: list | None = None,
    website: str | None = None,
    review_count: int | None = None,
    place_types: list | None = None,
) -> dict:
    """Returns {"fit", "reasons", "grade"} — grade is the single 0-100 lead
    quality number the UI shows in place of raw sub-scores."""
    excluded: list[str] = []
    borderline: list[str] = []
    haystack = f"{name or ''} {category or ''}"

    if is_staffing_agency(name):
        excluded.append("Staffing/recruiting agency — the posting isn't their own front desk")

    if is_chain(name):
        excluded.append("National chain/franchise — buys centrally, already has a contact centre")

    bad = sorted({t for t in (place_types or []) if t in _BAD_PLACE_TYPES})
    if bad:
        excluded.append(
            "Venue type has no bookable front desk ("
            + ", ".join(t.replace("_", " ") for t in bad[:3]) + ")"
        )

    if _B2B_RE.search(haystack) and not _CONSUMER_RE.search(haystack):
        excluded.append("B2B/corporate office — customers don't phone to book")

    if _is_toll_free(phone):
        if any(not _is_toll_free(p) for p in (phones or []) if p):
            borderline.append("Main line is toll-free (national), but local numbers exist")
        else:
            excluded.append("Only toll-free numbers — a national call centre, not a local desk")

    rc = review_count or 0
    if review_count is None and not website:
        borderline.append("No public reviews or website — may not be a customer-facing location")
    if rc > 20000:
        excluded.append(f"{rc:,} reviews — mega operation, far beyond an SMB")
    elif rc > 5000:
        borderline.append(f"{rc:,} reviews — likely a large multi-branch operation")
    elif 0 < rc < 10:
        borderline.append(f"Only {rc} reviews — may be too small or too new to buy")

    if _is_brand_subpage(website):
        borderline.append("Website is a sub-page of a larger brand site — likely multi-location")

    if excluded:
        return {"fit": "excluded", "reasons": excluded + borderline}
    if borderline:
        return {"fit": "borderline", "reasons": borderline}
    return {"fit": "good", "reasons": ["Local single-location profile — matches Deskie's ICP"]}


# ── Single lead-quality grade ───────────────────────────────────────────────
# The dashboard shows ONE number instead of pain/value/digital/timing columns.
# Those sub-scores still drive it, they're just internal now.
def lead_grade(fit: str, final_score: float | None, discovery: str) -> dict:
    """Returns {"score": 0-100, "label": "A"|"B"|"C"|"D", "tone"}."""
    base = float(final_score or 0)
    if discovery == "hiring":
        base += 12          # actively hiring for this exact job = strongest timing signal
    if fit == "borderline":
        base -= 15
    elif fit == "excluded":
        base = min(base, 25)
    score = max(0, min(100, round(base)))

    if score >= 75:
        label, tone = "A", "hot"
    elif score >= 60:
        label, tone = "B", "warm"
    elif score >= 40:
        label, tone = "C", "cool"
    else:
        label, tone = "D", "cold"
    return {"score": score, "label": label, "tone": tone}
