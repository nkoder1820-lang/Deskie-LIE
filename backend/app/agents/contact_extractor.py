"""
Deep Contact Extractor
======================
Crawls a business website (homepage + contact/about/booking pages) and pulls
every reachable contact channel:

  - emails      : mailto links, Cloudflare-obfuscated, JSON-LD, raw text,
                  "name [at] domain [dot] com" patterns — validated + ranked
  - phones      : tel: links + international number matching (phonenumbers)
  - whatsapp    : wa.me / api.whatsapp.com links → E.164 number
  - socials     : Instagram, Facebook, LinkedIn, X/Twitter, YouTube, TikTok,
                  Threads, Pinterest, Telegram, Yelp, Practo, Justdial, ...
  - booking     : Calendly / Zocdoc / Fresha / Square / Practo booking links
  - contact form: URL of a page containing a message/contact form

All extraction is offline-heuristic (no AI credits, no paid APIs).
"""
import html as html_lib
import json
import logging
import re
from urllib.parse import urljoin, urlparse, unquote

import httpx
import phonenumbers
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_PAGES = 5          # homepage + up to 4 subpages
MAX_PAGE_BYTES = 400_000

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Subpage link keywords worth crawling for contact info
CRAWL_KEYWORDS = ("contact", "about", "reach", "book", "appointment", "location", "find-us",
                  "support", "team", "staff", "our-people", "meet-", "leadership", "management")

# Decision-maker titles worth surfacing (owners / people who buy software)
DM_TITLES = (
    "owner", "co-owner", "founder", "co-founder", "ceo", "managing director",
    "general manager", "gm", "operations manager", "practice manager",
    "office manager", "proprietor", "principal", "partner", "president",
    "executive chef", "head chef", "chef", "medical director", "clinic director",
    "director", "manager", "franchisee",
)
# Longest first — Python regex alternation is first-match, so "executive chef"
# must be tried before "chef", "managing director" before "director", etc.
_TITLE_ALT = "|".join(re.escape(t) for t in sorted(DM_TITLES, key=len, reverse=True))
# "Jane Doe — Owner" / "Jane Doe, General Manager"
DM_NAME_TITLE_RE = re.compile(
    r"(?:Dr\.|Mr\.|Mrs\.|Ms\.|Chef)?\s*([A-Z][a-zA-Z'\-]+(?: [A-Z][a-zA-Z'\-]+){1,2})\s*[,–—\-|:]\s*"
    rf"((?:{_TITLE_ALT})(?: ?& ?(?:{_TITLE_ALT}))?)\b", re.IGNORECASE)
# "Owner: Jane Doe" / "Founder – Jane Doe"
DM_TITLE_NAME_RE = re.compile(
    rf"\b((?:{_TITLE_ALT}))\s*[,–—\-|:]\s*(?:Dr\.|Mr\.|Mrs\.|Ms\.|Chef)?\s*"
    r"([A-Z][a-zA-Z'\-]+(?: [A-Z][a-zA-Z'\-]+){1,2})", re.IGNORECASE)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
OBFUSCATED_EMAIL_RE = re.compile(
    r"([A-Za-z0-9._%+\-]{2,})\s*[\[({]\s*(?:at|AT)\s*[\])}]\s*([A-Za-z0-9\-]+)"
    r"\s*[\[({]\s*(?:dot|DOT)\s*[\])}]\s*([A-Za-z]{2,24})"
)

JUNK_EMAIL_DOMAINS = (
    "example.", "sentry.", "wixpress.com", "sentry-next", "yourdomain", "domain.com",
    "email.com", "mysite.com", "test.com", "schema.org", "w3.org", "godaddy.com",
    "placeholder", "latofonts.com", "2x.png", "polyfill",
    # web/marketing agencies whose form addresses leak into client sites
    "tambourine.com", "spothopper.com", "popmenu.com", "singleplatform.com",
)
FILE_EXT_RE = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|css|js|json|ico|woff2?|ttf|eot|mp4|pdf|avif)$", re.I
)
HEX_LOCAL_RE = re.compile(r"^[0-9a-f]{12,}$", re.I)
GENERIC_LOCALS = ("info", "contact", "hello", "office", "admin", "care", "support",
                  "booking", "bookings", "appointments", "enquiry", "enquiries",
                  "inquiries", "reception", "frontdesk", "team", "mail")

SOCIAL_PATTERNS = {
    "instagram": re.compile(r"instagram\.com/(?!p/|reel/|explore|accounts|share)([A-Za-z0-9._]{2,40})", re.I),
    "facebook":  re.compile(r"(?:facebook|fb)\.com/(?!sharer|share|plugins|dialog|login|hashtag|events/\d|\d{4}/)([A-Za-z0-9.\-_/]{2,80})", re.I),
    "linkedin":  re.compile(r"linkedin\.com/(company|in|school)/([A-Za-z0-9\-_%.]{2,80})", re.I),
    "twitter":   re.compile(r"(?:twitter|x)\.com/(?!intent|share|search|hashtag|home)([A-Za-z0-9_]{2,20})", re.I),
    "youtube":   re.compile(r"youtube\.com/(@[\w\-.]{2,60}|channel/[\w\-]{10,}|user/[\w\-]{2,60}|c/[\w\-]{2,60})", re.I),
    "tiktok":    re.compile(r"tiktok\.com/(@[\w\-.]{2,60})", re.I),
    "threads":   re.compile(r"threads\.net/(@?[\w\-.]{2,60})", re.I),
    "pinterest": re.compile(r"pinterest\.com/([\w\-]{2,60})", re.I),
    "telegram":  re.compile(r"t\.me/([\w\-]{3,60})", re.I),
    "yelp":      re.compile(r"yelp\.com/biz/([\w\-%.]{2,120})", re.I),
    "practo":    re.compile(r"practo\.com/([\w\-/%.]{2,120})", re.I),
    "justdial":  re.compile(r"justdial\.com/([\w\-/%.]{2,160})", re.I),
    "tripadvisor": re.compile(r"tripadvisor\.[a-z.]+/([\w\-.]{2,160})", re.I),
    "google_maps": re.compile(r"(?:goo\.gl/maps|maps\.app\.goo\.gl|google\.[a-z.]+/maps)/?([^\s\"'<>]{0,200})", re.I),
}
SOCIAL_HOME = {
    "instagram": "https://instagram.com/",
    "facebook": "https://facebook.com/",
    "linkedin": "https://linkedin.com/",
    "twitter": "https://x.com/",
    "youtube": "https://youtube.com/",
    "tiktok": "https://tiktok.com/",
    "threads": "https://threads.net/",
    "pinterest": "https://pinterest.com/",
    "telegram": "https://t.me/",
    "yelp": "https://yelp.com/biz/",
    "practo": "https://practo.com/",
    "justdial": "https://justdial.com/",
}

BOOKING_HOSTS = ("calendly.com", "zocdoc.com", "fresha.com", "booksy.com", "squareup.com",
                 "square.site", "setmore.com", "appointy.com", "acuityscheduling.com",
                 "vagaro.com", "mindbodyonline.com", "practo.com/book", "healthplix")

WHATSAPP_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?[^\"'<> ]*phone=)\+?(\d{8,15})", re.I)

COUNTRY_REGION_HINTS = [
    ("united states", "US"), ("usa", "US"),
    ("india", "IN"),
    ("united kingdom", "GB"), (" uk", "GB"),
    ("canada", "CA"), ("australia", "AU"),
    ("united arab emirates", "AE"), ("singapore", "SG"),
    ("new zealand", "NZ"), ("germany", "DE"), ("france", "FR"),
]


def region_from_address(address: str | None, default: str = "IN") -> str:
    """Guess a phonenumbers region code from a formatted address."""
    if not address:
        return default
    low = " " + address.lower()
    for needle, region in COUNTRY_REGION_HINTS:
        if needle in low:
            return region
    return default


def normalize_whatsapp(digits: str, region: str = "IN") -> str | None:
    """Turn wa.me digits into a valid E.164 number (wa.me links sometimes
    omit the country code — repair using the region hint)."""
    digits = digits.lstrip("0")
    for candidate in (f"+{digits}", digits):
        try:
            num = phonenumbers.parse(candidate, None if candidate.startswith("+") else region)
            if phonenumbers.is_valid_number(num):
                return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            continue
    return None


def _decode_cfemail(hex_str: str) -> str | None:
    """Decode Cloudflare email-protection data-cfemail attribute."""
    try:
        data = bytes.fromhex(hex_str)
        key = data[0]
        return "".join(chr(b ^ key) for b in data[1:])
    except Exception:
        return None


def _valid_email(email: str) -> bool:
    email = email.strip().strip(".")
    if not EMAIL_RE.fullmatch(email):
        return False
    local, domain = email.rsplit("@", 1)
    if len(local) < 2 or HEX_LOCAL_RE.match(local):
        return False
    if FILE_EXT_RE.search(email):
        return False
    low = email.lower()
    if any(junk in low for junk in JUNK_EMAIL_DOMAINS):
        return False
    if domain.count(".") > 3 or len(domain.split(".")[0]) < 2:
        return False
    return True


def _email_rank(email: str, trusted: set[str], site_domain: str | None) -> tuple:
    """Sort key: trusted source first, then site-domain match, then generic local part."""
    low = email.lower()
    local, domain = low.rsplit("@", 1)
    return (
        0 if low in trusted else 1,
        0 if site_domain and (site_domain.endswith(domain) or domain in site_domain) else 1,
        0 if local in GENERIC_LOCALS else 1,
        len(low),
    )


class ContactExtractor:

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            timeout=8.0, follow_redirects=True, headers=UA_HEADERS
        )

    # ── public ──────────────────────────────────────────────────────────────
    def run(self, website_url: str | None, region: str = "IN") -> dict:
        """Crawl + extract in one shot."""
        if not website_url:
            return self._empty()
        pages = self.crawl(website_url)
        return self.extract_from_pages(pages, website_url, region)

    @staticmethod
    def _empty() -> dict:
        return {
            "emails": [], "phones": [], "socials": {}, "whatsapp": None,
            "whatsapp_link": None, "booking_links": [], "contact_form_url": None,
            "decision_makers": [], "personal_emails": [],
            "pages_crawled": [],
        }

    def extract_from_pages(self, pages: dict[str, str], website_url: str, region: str = "IN") -> dict:
        if not pages:
            return self._empty()

        emails: list[str] = []
        trusted: set[str] = set()      # from mailto / cfemail / JSON-LD
        phones: list[str] = []
        socials: dict[str, str] = {}
        booking_links: list[str] = []
        whatsapp = None
        contact_form_url = None
        decision_makers: list[dict] = []
        dm_seen: set[str] = set()

        def add_dm(name: str, title: str):
            name, title = name.strip(), title.strip().title()
            key = name.lower()
            # Guard against sentence fragments matching as names
            if key in dm_seen or len(name) > 40 or any(w.islower() for w in name.split()):
                return
            dm_seen.add(key)
            decision_makers.append({"name": name, "title": title})

        site_domain = (urlparse(website_url).netloc or "").lower().removeprefix("www.")

        for url, html in pages.items():
            soup = BeautifulSoup(html, "html.parser")

            # -- emails ------------------------------------------------------
            for m in re.finditer(r'mailto:([^"\'?<> ]+)', html, re.I):
                addr = unquote(m.group(1)).strip()
                if _valid_email(addr):
                    emails.append(addr)
                    trusted.add(addr.lower())

            for tag in soup.select("[data-cfemail]"):
                decoded = _decode_cfemail(tag.get("data-cfemail", ""))
                if decoded and _valid_email(decoded):
                    emails.append(decoded)
                    trusted.add(decoded.lower())

            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    ld = json.loads(script.string or "")
                except Exception:
                    continue
                for item in (ld if isinstance(ld, list) else [ld]):
                    if not isinstance(item, dict):
                        continue
                    stack = [item]
                    while stack:
                        node = stack.pop()
                        if isinstance(node, dict):
                            if node.get("@type") == "Person" and isinstance(node.get("name"), str):
                                add_dm(node["name"], str(node.get("jobTitle") or "Team member"))
                            em = node.get("email")
                            if isinstance(em, str) and _valid_email(em.replace("mailto:", "")):
                                em = em.replace("mailto:", "")
                                emails.append(em)
                                trusted.add(em.lower())
                            tel = node.get("telephone")
                            if isinstance(tel, str):
                                phones.extend(self._parse_phones(tel, region))
                            same_as = node.get("sameAs")
                            if isinstance(same_as, str):
                                same_as = [same_as]
                            if isinstance(same_as, list):
                                self._collect_socials(" ".join(str(s) for s in same_as), socials)
                            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
                        elif isinstance(node, list):
                            stack.extend(node)

            text = html_lib.unescape(soup.get_text(separator=" ", strip=True))
            emails.extend(e for e in EMAIL_RE.findall(html) if _valid_email(e))
            emails.extend(e for e in EMAIL_RE.findall(text) if _valid_email(e))
            for m in OBFUSCATED_EMAIL_RE.finditer(text):
                candidate = f"{m.group(1)}@{m.group(2)}.{m.group(3)}"
                if _valid_email(candidate):
                    emails.append(candidate)

            # -- decision makers (names + titles) ---------------------------
            for m in DM_NAME_TITLE_RE.finditer(text):
                add_dm(m.group(1), m.group(2))
            for m in DM_TITLE_NAME_RE.finditer(text):
                add_dm(m.group(2), m.group(1))

            # -- phones ------------------------------------------------------
            for m in re.finditer(r'(?:tel|callto):([+\d\-().\s]{7,20})', html, re.I):
                phones.extend(self._parse_phones(m.group(1), region))
            phones.extend(self._parse_phones(text, region))

            # -- whatsapp ----------------------------------------------------
            wa = WHATSAPP_RE.search(html)
            if wa and not whatsapp:
                whatsapp = normalize_whatsapp(wa.group(1), region)

            # -- socials + booking ------------------------------------------
            self._collect_socials(html, socials)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(bh in href.lower() for bh in BOOKING_HOSTS) and href not in booking_links:
                    booking_links.append(href.split("#")[0][:300])

            # -- contact form ------------------------------------------------
            if not contact_form_url:
                for form in soup.find_all("form"):
                    has_msg = form.find("textarea") is not None
                    has_email = form.find("input", attrs={"type": "email"}) is not None or \
                        form.find("input", attrs={"name": re.compile("email", re.I)}) is not None
                    if has_msg or has_email:
                        contact_form_url = url
                        break

        # rank + dedupe emails (normalize accidental "@www." domains)
        seen, unique = set(), []
        for e in emails:
            e = re.sub(r"@www\.", "@", e, flags=re.I)
            if e.lower() not in seen:
                seen.add(e.lower())
                unique.append(e)
        unique.sort(key=lambda e: _email_rank(e, trusted, site_domain))

        # dedupe phones, prefer E.164
        phone_seen, phone_list = set(), []
        for p in phones:
            if p not in phone_seen:
                phone_seen.add(p)
                phone_list.append(p)

        if not whatsapp and "whatsapp" in socials:
            wam = WHATSAPP_RE.search(socials["whatsapp"])
            if wam:
                whatsapp = normalize_whatsapp(wam.group(1), region)

        # Personal emails (named inbox = likely a specific person, often the owner)
        personal_emails = [
            e for e in unique
            if e.rsplit("@", 1)[0].lower() not in GENERIC_LOCALS
            and not e.rsplit("@", 1)[0].isdigit()
        ]

        return {
            "emails": unique[:5],
            "phones": phone_list[:5],
            "socials": socials,
            "whatsapp": whatsapp,
            "whatsapp_link": f"https://wa.me/{whatsapp.lstrip('+')}" if whatsapp else None,
            "booking_links": booking_links[:5],
            "contact_form_url": contact_form_url,
            "decision_makers": decision_makers[:6],
            "personal_emails": personal_emails[:3],
            "pages_crawled": list(pages.keys()),
        }

    # ── internals ───────────────────────────────────────────────────────────
    def crawl(self, start_url: str) -> dict[str, str]:
        """Fetch homepage + promising same-domain subpages. Returns {url: html}."""
        pages: dict[str, str] = {}
        home = self._fetch(start_url)
        if home is None:
            return pages
        pages[start_url] = home

        base_host = urlparse(start_url).netloc.lower().removeprefix("www.")
        candidates: list[str] = []
        try:
            soup = BeautifulSoup(home, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                full = urljoin(start_url, href).split("#")[0]
                host = urlparse(full).netloc.lower().removeprefix("www.")
                if host != base_host:
                    continue
                path = urlparse(full).path.lower()
                if any(kw in path for kw in CRAWL_KEYWORDS) and full not in candidates:
                    candidates.append(full)
        except Exception as e:
            logger.debug(f"[ContactExtractor] link parse failed: {e}")

        # Prioritise contact pages over the rest
        candidates.sort(key=lambda u: 0 if "contact" in u.lower() else 1)
        for url in candidates[: MAX_PAGES - 1]:
            if url in pages:
                continue
            html = self._fetch(url)
            if html:
                pages[url] = html
        return pages

    def _fetch(self, url: str) -> str | None:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "text/html" not in ctype and "xml" not in ctype and ctype:
                return None
            return resp.text[:MAX_PAGE_BYTES]
        except Exception as e:
            logger.debug(f"[ContactExtractor] fetch failed {url}: {e}")
            return None

    def _parse_phones(self, text: str, region: str) -> list[str]:
        found = []
        try:
            for match in phonenumbers.PhoneNumberMatcher(text[:20_000], region):
                num = match.number
                if phonenumbers.is_valid_number(num):
                    found.append(phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164))
        except Exception:
            pass
        return found

    def _collect_socials(self, blob: str, socials: dict[str, str]):
        for platform, pattern in SOCIAL_PATTERNS.items():
            if platform in socials:
                continue
            m = pattern.search(blob)
            if not m:
                continue
            if platform == "google_maps":
                # keep full matched URL
                url_m = re.search(r"https?://[^\s\"'<>]+", blob[max(0, m.start() - 30): m.end() + 10])
                if url_m:
                    socials[platform] = url_m.group(0)[:300]
                continue
            handle = m.group(m.lastindex or 1).rstrip("/").split("?")[0]
            if platform == "facebook" and handle.lower() in ("profile.php", "pages"):
                continue
            if platform == "linkedin":
                socials[platform] = f"https://linkedin.com/{m.group(1)}/{handle}"
            else:
                socials[platform] = SOCIAL_HOME[platform] + handle
        # whatsapp link as a social too
        if "whatsapp" not in socials:
            wa = WHATSAPP_RE.search(blob)
            if wa:
                socials["whatsapp"] = f"https://wa.me/{wa.group(1)}"
