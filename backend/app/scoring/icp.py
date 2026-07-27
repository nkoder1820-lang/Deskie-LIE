"""
ICP (Ideal Customer Profile) gate + fit assessment
==================================================
Deskie's buyer is a single-location SMB with a real local front desk —
clinics, salons, firms, restaurants. Not chains, national brands, staffing
agencies, or organizations big enough to run their own call center: those
show real hiring signals but never buy a $99/mo AI receptionist.

Everything here is a deterministic, zero-cost heuristic over data we already
store (name, phone, website, review count) — no LLM, no API calls — so it is
computed at read time and applies retroactively to every stored lead.

Fit levels:
  "good"       — matches the ICP profile
  "borderline" — worth a look, but signals suggest a larger operation
  "excluded"   — clear non-ICP (still listed, just ranked/flagged — the ONE
                 hard gate is staffing agencies at hiring-discovery time,
                 because the posting isn't even their own front desk)
"""
import re
from urllib.parse import urlparse

# Staffing / recruiting agencies post the majority of receptionist ads on
# aggregators — they are pure noise for us (the role isn't at their office).
_STAFFING_RE = re.compile(
    "|".join([
        r"\bstaffing\b", r"\brecruit(?:ing|ment|ers?)\b", r"\bemployment agency\b",
        r"\bpersonnel\b", r"\btalent (?:acquisition|solutions|group|partners)\b",
        r"robert half", r"\badecco\b", r"\brandstad\b", r"\bmanpower\b",
        r"kelly services", r"\baerotek\b", r"insight global", r"express employment",
        r"\bpridestaff\b", r"\bspherion\b", r"\bteksystems\b", r"\bstaffmark\b",
        r"\bkforce\b", r"michael page", r"\bhays recruitment\b", r"\bworkforce solutions\b",
        r"professional resources", r"staffing solutions", r"\btemp(?:orary)? (?:agency|services)\b",
    ]),
    re.IGNORECASE,
)

_US_TOLL_FREE = ("800", "833", "844", "855", "866", "877", "888")

# B2B / corporate offices: real businesses, but nobody phones them to book an
# appointment, so an AI receptionist has nothing to answer. They slip through
# hiring searches in tech hubs (a VC firm hiring an "office executive").
_B2B_RE = re.compile(
    "|".join([
        r"\bventures?\b", r"venture partners", r"capital partners", r"private equity",
        r"\bvc\b", r"\bholdings?\b", r"\btechnologies\b", r"\btechnology (private|pvt|inc|llc)",
        r"\bsoftware\b", r"\binfotech\b", r"\banalytics\b", r"\bconsultanc(y|ies)\b",
        r"\bconsulting\b", r"\badvisory\b", r"media agency", r"advertising agency",
        r"digital (marketing )?agency", r"\bsaas\b", r"\bfintech\b",
    ]),
    re.IGNORECASE,
)

# Consumer verticals where walk-in/phone customers are the whole business.
# A clinic called "Smile Technologies" must NOT be caught by _B2B_RE.
_CONSUMER_RE = re.compile(
    "|".join([
        r"dental", r"dentist", r"clinic", r"hospital", r"medical", r"health",
        r"salon", r"spa\b", r"beauty", r"hair", r"aesthet", r"derma", r"skin",
        r"restaurant", r"cafe", r"coffee", r"kitchen", r"bakery", r"dining",
        r"gym", r"fitness", r"yoga", r"wellness", r"physio",
        r"law|legal|advocate|attorney", r"real ?est|realty|property",
        r"fertility", r"ivf", r"veterinar", r"\bvet\b", r"diagnostic", r"patholog",
        r"hotel", r"resort", r"academy", r"school", r"tutor", r"coaching",
        r"auto|garage|repair|service ?cent", r"optic|eye ?care", r"pharmac",
    ]),
    re.IGNORECASE,
)


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
) -> dict:
    """Returns {"fit": "good"|"borderline"|"excluded", "reasons": [...]}."""
    excluded: list[str] = []
    borderline: list[str] = []

    if is_staffing_agency(name):
        excluded.append("Staffing/recruiting agency — the posting isn't their own front desk")

    # Corporate/B2B office — unless the category or name says it's a consumer
    # business, in which case the keyword is incidental ("Smile Technologies").
    haystack = f"{name or ''} {category or ''}"
    if _B2B_RE.search(haystack) and not _CONSUMER_RE.search(haystack):
        excluded.append("B2B/corporate office — customers don't phone to book, so there's no front desk to answer")

    if _is_toll_free(phone):
        locals_exist = any(not _is_toll_free(p) for p in (phones or []) if p)
        if locals_exist:
            borderline.append("Main line is toll-free (national), but local numbers exist")
        else:
            excluded.append("Only toll-free numbers — a national call center, not a local front desk")

    rc = review_count or 0
    if review_count is None and not website:
        # No reviews and no site: nothing suggests a public-facing operation
        # customers actually call.
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
