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

    if _is_toll_free(phone):
        locals_exist = any(not _is_toll_free(p) for p in (phones or []) if p)
        if locals_exist:
            borderline.append("Main line is toll-free (national), but local numbers exist")
        else:
            excluded.append("Only toll-free numbers — a national call center, not a local front desk")

    rc = review_count or 0
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
