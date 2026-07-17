"""
Website Intelligence Agent
===========================
Fetches and analyzes a business website.
Detects: phone dependency, online booking, WhatsApp, chatbot, ads, automation.

Output JSON:
{
  "phone_dependency_score": 0.0-1.0,
  "booking_available": bool,
  "whatsapp_available": bool,
  "chatbot_available": bool,
  "runs_ads": 0.0-1.0,
  "automation_level": 0.0-1.0,
  "website_quality_score": 0.0-1.0,
  "pain_signals": [str],
  "emails": [str],
  "detected_tech": [str]
}
"""
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.agents.nvidia_client import call_nvidia

logger = logging.getLogger(__name__)


class WebsiteIntelligenceAgent:

    def run(self, website_url: Optional[str], business_name: str) -> dict:
        """
        Analyze a business website.
        Returns structured signals dict.
        """
        if not website_url:
            return self._no_website_result()

        html = self._fetch_html(website_url)
        if not html:
            return self._no_website_result()

        # Attempt to find and fetch a contact page
        contact_html = ""
        try:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all('a', href=True):
                href = a['href'].lower()
                if any(kw in href for kw in ['contact', 'about', 'reach', 'info']):
                    if href.startswith('http'):
                        contact_url = a['href']
                    elif href.startswith('/'):
                        contact_url = website_url.rstrip('/') + a['href']
                    else:
                        contact_url = website_url.rstrip('/') + '/' + a['href']
                    
                    fetched_contact = self._fetch_html(contact_url)
                    if fetched_contact:
                        contact_html = fetched_contact
                    break
        except Exception as e:
            logger.warning(f"Failed to crawl contact page: {e}")

        combined_html = html + "\n" + contact_html

        # Heuristic extraction (fast, no AI credits)
        heuristics = self._extract_heuristics(combined_html, website_url)

        # AI-assisted deeper analysis (uses NVIDIA NIM)
        ai_signals = self._ai_analyze(html, business_name, website_url)

        # Merge: heuristics take precedence for binary signals, AI fills the rest
        result = {**ai_signals, **{k: v for k, v in heuristics.items() if v is not None}}
        result.setdefault("pain_signals", [])

        if not heuristics.get("booking_available") and not heuristics.get("whatsapp_available"):
            result["pain_signals"].append("No online booking or WhatsApp contact found")

        if heuristics.get("phone_numbers"):
            result["pain_signals"].append(f"Phone number prominently displayed: {heuristics['phone_numbers'][0]}")

        return result

    def _fetch_html(self, url: str) -> Optional[str]:
        """Fetch raw HTML with a browser-like UA. Returns None on failure."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-IN,en;q=0.9",
        }
        try:
            resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
            resp.raise_for_status()
            return resp.text[:50_000]   # Cap at 50KB to stay within token limits
        except Exception as e:
            logger.warning(f"[WebsiteAgent] Could not fetch {url}: {e}")
            return None

    def _extract_heuristics(self, html: str, url: str) -> dict:
        """Fast regex + BS4 heuristic extraction."""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True).lower()
        raw_html_lower = html.lower()

        # Email addresses — multi-strategy extraction
        emails = []

        # Strategy 1: mailto: href links (most reliable)
        mailto_emails = re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html, re.IGNORECASE)
        emails.extend(mailto_emails)

        # Strategy 2: Standard regex on raw HTML
        raw_emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,4}', html)
        emails.extend(raw_emails)

        # Strategy 3: Visible text (catches obfuscated [at] / (at) patterns)
        page_text_raw = soup.get_text(separator=" ", strip=True)
        text_emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,4}', page_text_raw)
        emails.extend(text_emails)

        # Strategy 4: Obfuscated "email [at] domain [dot] com" style
        obfuscated = re.findall(r'([a-zA-Z0-9._%+\-]+)\s*[\[({]?\s*(?:at|AT|@)\s*[\])}]?\s*([a-zA-Z0-9.\-]+)\s*[\[({]?\s*(?:dot|DOT|\.)\s*[\])}]?\s*([a-zA-Z]{2,4})', page_text_raw)
        for match in obfuscated:
            emails.append(f"{match[0]}@{match[1]}.{match[2]}")

        # Clean and deduplicate — with strict validity checks
        skip_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.webp', '.woff', '.ttf', '.ico')
        skip_domains = (
            'sentry.io', 'example.com', 'yourdomain', 'domain.com', 'email.com',
            'test.com', 'wix.com', 'schemas.org', 'w3.org', 'acad', 'erials',
        )
        valid_tlds = {
            'com', 'in', 'co', 'org', 'net', 'io', 'info', 'biz', 'edu', 'gov',
            'uk', 'us', 'au', 'ca', 'de', 'fr', 'sg', 'nz', 'ae', 'me',
        }

        # mailto: addresses are most trustworthy — sort them first
        mailto_set = set(e.lower() for e in mailto_emails)

        def email_priority(e):
            return 0 if e.lower() in mailto_set else 1

        emails_sorted = sorted(emails, key=email_priority)

        cleaned_emails = []
        seen = set()
        for e in emails_sorted:
            e_lower = e.lower()
            if e_lower in seen:
                continue
            if '@' not in e:
                continue
            local, _, domain = e.partition('@')
            if len(local) < 3:                                         # too short local
                continue
            if '.' not in domain:                                      # no TLD
                continue
            tld = domain.rsplit('.', 1)[-1].lower()
            domain_name = domain.rsplit('.', 1)[0].lower()
            if len(domain_name) < 3:                                   # too short domain
                continue
            if tld not in valid_tlds:                                  # unknown TLD (catches .THE, .acad etc.)
                continue
            if any(e_lower.endswith(ext) for ext in skip_extensions):
                continue
            if any(skip in e_lower for skip in skip_domains):
                continue
            seen.add(e_lower)
            cleaned_emails.append(e)
        emails = cleaned_emails[:5]

        # Phone numbers — broader pattern for Indian numbers
        phone_numbers = re.findall(r'(?:(?:\+91|91|0)[\s\-]?)?[6-9]\d{9}', html.replace(' ', '').replace('-', '').replace('\xa0', ''))
        # Also try generic 10+ digit numbers
        phone_numbers += re.findall(r'[\+]?[0-9]{10,13}', html)
        phone_numbers = list(dict.fromkeys([re.sub(r'[^\d+]', '', p) for p in phone_numbers if len(re.sub(r'[^\d]', '', p)) >= 10]))[:5]

        # Tech Stack Detection
        tech_keywords = {
            "wordpress": "WordPress",
            "squarespace": "Squarespace",
            "wix.com": "Wix",
            "hubspot": "HubSpot",
            "facebook pixel": "Facebook Pixel",
            "fbevents.js": "Facebook Pixel",
            "googletagmanager": "Google Tag Manager",
            "gtag(": "Google Tag Manager",
            "calendly": "Calendly",
            "practo": "Practo",
            "shopify": "Shopify",
            "react": "React",
            "next.js": "Next.js"
        }
        detected_tech = list(set([name for kw, name in tech_keywords.items() if kw in raw_html_lower]))

        # Booking indicators
        booking_keywords = ["book appointment", "book now", "schedule appointment",
                            "book online", "online booking", "book a slot", "book consultation",
                            "practo", "calendly", "zocdoc", "appointy", "healthplix"]
        booking_available = any(kw in text for kw in booking_keywords)

        # WhatsApp
        whatsapp_available = "whatsapp" in raw_html_lower or "wa.me" in raw_html_lower

        # Chatbot
        chatbot_keywords = ["tawk.to", "intercom", "freshchat", "crisp.chat",
                            "livechat", "tidio", "botpress", "landbot"]
        chatbot_available = any(kw in raw_html_lower for kw in chatbot_keywords)

        # Ads (GTM or ad pixels = running ads)
        ad_indicators = ["googletagmanager", "facebook pixel", "fbevents.js",
                         "google_conversion", "gtag(", "adsbygoogle"]
        runs_ads = 1.0 if any(kw in raw_html_lower for kw in ad_indicators) else 0.0

        # CRM / automation
        crm_keywords = ["hubspot", "salesforce", "zoho", "freshworks", "pipedrive",
                        "healthplix", "practoreach", "drchrono", "clinicsoftware"]
        automation_level = 1.0 if any(kw in raw_html_lower for kw in crm_keywords) else 0.0

        # Website quality (rough proxy: has CSS framework or structured layout)
        quality_indicators = ["bootstrap", "tailwind", "react", "next.js", "wordpress",
                               "wix.com", "squarespace", "webflow"]
        quality_score = 0.8 if any(kw in raw_html_lower for kw in quality_indicators) else 0.4

        # Phone dependency: phone is in hero/header?
        hero_html = html[:5000].lower()
        phone_prominent = bool(re.search(r'[\+]?[0-9]{10,13}', hero_html))
        phone_dep = 0.9 if phone_prominent and not booking_available else (0.5 if phone_prominent else 0.2)

        return {
            "phone_numbers": phone_numbers,
            "phone_dependency_score": phone_dep,
            "booking_available": booking_available,
            "whatsapp_available": whatsapp_available,
            "chatbot_available": chatbot_available,
            "runs_ads": runs_ads,
            "automation_level": automation_level,
            "website_quality_score": quality_score,
            "emails": emails,
            "detected_tech": detected_tech,
        }

    def _ai_analyze(self, html: str, business_name: str, url: str) -> dict:
        """Use NVIDIA NIM to extract deeper signals from page text."""
        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(separator=" ", strip=True)[:3000]

        system = """You are a business intelligence analyst. Analyze the website text and return ONLY valid JSON with these exact keys:
{
  "phone_dependency_score": <float 0.0-1.0>,
  "booking_available": <bool>,
  "whatsapp_available": <bool>,
  "chatbot_available": <bool>,
  "automation_level": <float 0.0-1.0>,
  "website_quality_score": <float 0.0-1.0>,
  "runs_ads": <float 0.0-1.0>,
  "pain_signals": [<list of pain signal strings>]
}

Scoring guidance:
- phone_dependency_score: 1.0 if business has no online booking and prominently shows phone number
- booking_available: true if there is any online booking / appointment scheduling
- automation_level: how much CRM/software automation is visible (0=none, 1=fully automated)
- pain_signals: list of specific observations that indicate Deskie would help this business
Return ONLY the JSON object, no other text."""

        user = f"""Business: {business_name}
URL: {url}
Website text:
{page_text}"""

        result = call_nvidia(system, user, max_tokens=512)
        return result if result else {}

    def _no_website_result(self) -> dict:
        return {
            "phone_dependency_score": 1.0,
            "booking_available": False,
            "whatsapp_available": False,
            "chatbot_available": False,
            "runs_ads": 0.0,
            "automation_level": 0.0,
            "website_quality_score": 0.0,
            "pain_signals": ["No website — business entirely dependent on phone/walk-in inquiries"],
            "emails": [],
            "detected_tech": [],
        }
