"""
Website Intelligence Agent
===========================
Crawls a business website (via ContactExtractor) and analyzes it.
Detects: phone dependency, online booking, WhatsApp, chatbot, ads, automation,
plus every contact channel (emails, phones, socials, WhatsApp, contact form).

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
  "phone_numbers": [str],
  "socials": {platform: url},
  "whatsapp": str | None,
  "whatsapp_link": str | None,
  "booking_links": [str],
  "contact_form_url": str | None,
  "detected_tech": [str]
}
"""
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from app.agents.contact_extractor import ContactExtractor
from app.agents.nvidia_client import call_nvidia

logger = logging.getLogger(__name__)


class WebsiteIntelligenceAgent:

    def __init__(self):
        self.extractor = ContactExtractor()

    def run(self, website_url: Optional[str], business_name: str,
            region: str = "IN", use_ai: bool = True) -> dict:
        """Analyze a business website. Returns structured signals dict."""
        if not website_url:
            return self._no_website_result()

        pages = self.extractor.crawl(website_url)
        if not pages:
            return self._no_website_result()

        contacts = self.extractor.extract_from_pages(pages, website_url, region)
        combined_html = "\n".join(pages.values())

        # Heuristic extraction (fast, no AI credits)
        heuristics = self._extract_heuristics(combined_html, contacts)

        # AI-assisted deeper analysis (uses NVIDIA NIM) on the homepage
        home_html = next(iter(pages.values()))
        ai_signals = self._ai_analyze(home_html, business_name, website_url) if use_ai else {}

        # Merge: heuristics take precedence for binary signals, AI fills the rest
        result = {**ai_signals, **{k: v for k, v in heuristics.items() if v is not None}}
        result.update(contacts)
        result["phone_numbers"] = contacts["phones"]
        result.setdefault("pain_signals", [])
        if not isinstance(result.get("pain_signals"), list):
            result["pain_signals"] = []

        if not heuristics.get("booking_available") and not heuristics.get("whatsapp_available"):
            result["pain_signals"].append("No online booking or WhatsApp contact found")
        if contacts["phones"]:
            result["pain_signals"].append(f"Phone number prominently displayed: {contacts['phones'][0]}")

        return result

    def _extract_heuristics(self, html: str, contacts: dict) -> dict:
        """Fast keyword heuristics across all crawled pages."""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True).lower()
        raw_html_lower = html.lower()

        # Tech Stack Detection
        tech_keywords = {
            "wp-content": "WordPress",
            "wordpress": "WordPress",
            "squarespace": "Squarespace",
            "wix.com": "Wix",
            "webflow": "Webflow",
            "shopify": "Shopify",
            "godaddy": "GoDaddy Builder",
            "hubspot": "HubSpot",
            "fbevents.js": "Facebook Pixel",
            "facebook pixel": "Facebook Pixel",
            "googletagmanager": "Google Tag Manager",
            "gtag(": "Google Analytics",
            "calendly": "Calendly",
            "practo": "Practo",
            "zocdoc": "Zocdoc",
            "mindbody": "Mindbody",
            "fresha": "Fresha",
            "next.js": "Next.js",
            "_next/static": "Next.js",
        }
        detected_tech = sorted({name for kw, name in tech_keywords.items() if kw in raw_html_lower})

        # Booking indicators
        booking_keywords = ["book appointment", "book now", "schedule appointment",
                            "book online", "online booking", "book a slot", "book consultation",
                            "schedule now", "request appointment", "schedule a visit",
                            "practo", "calendly", "zocdoc", "appointy", "healthplix",
                            "fresha", "booksy", "vagaro", "mindbody", "setmore", "acuityscheduling"]
        booking_available = any(kw in text or kw in raw_html_lower for kw in booking_keywords) \
            or bool(contacts.get("booking_links"))

        # WhatsApp
        whatsapp_available = ("whatsapp" in raw_html_lower or "wa.me" in raw_html_lower
                              or contacts.get("whatsapp") is not None)

        # Chatbot
        chatbot_keywords = ["tawk.to", "intercom", "freshchat", "crisp.chat",
                            "livechat", "tidio", "botpress", "landbot", "drift.com", "zendesk"]
        chatbot_available = any(kw in raw_html_lower for kw in chatbot_keywords)

        # Ads (GTM or ad pixels = running ads)
        ad_indicators = ["googletagmanager", "fbevents.js", "facebook pixel",
                         "google_conversion", "gtag(", "adsbygoogle", "tiktok pixel"]
        runs_ads = 1.0 if any(kw in raw_html_lower for kw in ad_indicators) else 0.0

        # CRM / automation
        crm_keywords = ["hubspot", "salesforce", "zoho", "freshworks", "pipedrive",
                        "healthplix", "practoreach", "drchrono", "clinicsoftware", "mindbody"]
        automation_level = 1.0 if any(kw in raw_html_lower for kw in crm_keywords) else 0.0

        # Website quality (rough proxy: has CSS framework or structured layout)
        quality_indicators = ["bootstrap", "tailwind", "react", "next.js", "wordpress",
                              "wix.com", "squarespace", "webflow"]
        quality_score = 0.8 if any(kw in raw_html_lower for kw in quality_indicators) else 0.4

        # Phone dependency: phone in hero/header and no booking?
        hero_html = html[:6000]
        phone_prominent = bool(re.search(r'(?:tel:|\+?\d[\d\-().\s]{8,}\d)', hero_html))
        phone_dep = 0.9 if phone_prominent and not booking_available else (0.5 if phone_prominent else 0.2)

        return {
            "phone_dependency_score": phone_dep,
            "booking_available": booking_available,
            "whatsapp_available": whatsapp_available,
            "chatbot_available": chatbot_available,
            "runs_ads": runs_ads,
            "automation_level": automation_level,
            "website_quality_score": quality_score,
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
- pain_signals: list of specific observations that indicate an AI receptionist would help this business
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
            "phone_numbers": [],
            "phones": [],
            "socials": {},
            "whatsapp": None,
            "whatsapp_link": None,
            "booking_links": [],
            "contact_form_url": None,
            "detected_tech": [],
        }
