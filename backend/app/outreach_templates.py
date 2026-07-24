"""
Outreach email composer
=======================
Builds the professional HTML (+ plaintext twin) cold email for a lead,
deterministically — a fixed, email-client-safe skeleton with merge fields,
NOT raw LLM output, so what you preview is exactly what sends. The template
and subject are picked from the lead's pitch angle / qualification reason;
the evidence chip cites the real source (job posting, review, ad) with its
link; the CTA points at the lead's personalized /demo/<slug> page.

Style: personal founder note inside a lightly-branded card (small wordmark,
accent bar, one button) — polished like a product email, but short and
human like a person wrote it. Sender identity: "Niket from Deskie".
"""
import html as _html
import re

ACCENT = "#4F46E5"
ACCENT_DARK = "#3730A3"

_SUBJECTS = {
    "hiring":     "Before you hire a receptionist at {biz} — hear this",
    "missed":     "{biz}'s missed calls, answered — hear it live",
    "booking":    "{biz} + 24/7 booking — hear how it sounds",
    "afterhours": "Who answers {biz} after closing?",
    "ads":        "You pay for the calls — hear what answers them",
    "general":    "Built an AI receptionist for {biz} — hear her",
}

_HOOKS = {
    "hiring": (
        "I saw {biz} is hiring for the front desk. Before you commit to a "
        "monthly salary, I'd love you to hear something we already built for "
        "you: an AI receptionist configured with {biz}'s actual hours, "
        "services and details."
    ),
    "missed": (
        "When callers can't reach {biz}, most book with whoever answers "
        "next. So we went ahead and built {biz}'s AI receptionist — she "
        "answers every call in under a second, 24/7, and books straight "
        "into your calendar."
    ),
    "booking": (
        "{biz} runs on phone bookings — which means every unanswered ring "
        "is a lost customer. We already built your AI receptionist: she "
        "answers instantly, books appointments, and never takes a day off."
    ),
    "afterhours": (
        "Who answers {biz}'s phone after closing? We built an AI "
        "receptionist configured for {biz} that takes bookings while you "
        "sleep — evenings, weekends, holidays."
    ),
    "ads": (
        "You're paying to make {biz}'s phone ring — what answers it decides "
        "the return. We built an AI receptionist for {biz} that catches "
        "every one of those calls and turns them into bookings."
    ),
    "general": (
        "Before reaching out, we built something for {biz}: an AI "
        "receptionist that answers your calls 24/7, books appointments, and "
        "logs every lead — already configured with your details."
    ),
}


def _angle_key(pitch_angle: str | None, qualification_reason: str | None) -> str:
    text = f"{pitch_angle or ''} {qualification_reason or ''}".lower()
    if "hiring" in text or "receptionist" in text and "hir" in text:
        return "hiring"
    if "missed call" in text:
        return "missed"
    if "booking" in text:
        return "booking"
    if "after-hours" in text or "after hours" in text:
        return "afterhours"
    if "ad budget" in text or "google ads" in text or "wasting ad" in text:
        return "ads"
    return "general"


def _first_name(business) -> str:
    """Greeting name — only if it actually looks like a person's first name.
    Site-scraped 'decision makers' include acronyms and org fragments (e.g.
    'EEF', 'HR Dept'); a wrong name is worse than none, so fall back to
    'there' unless the token is a clean, capitalized-able word."""
    for pool in (business.poc_contacts or [], business.decision_makers or []):
        for person in pool:
            token = ((person.get("name") or "").strip().split() or [""])[0]
            if (
                token.isalpha()
                and 2 < len(token) <= 12
                and not token.isupper()  # acronyms like EEF/HR
            ):
                return token.capitalize()
    return "there"


def _agent_name(business) -> str:
    phone = (business.phone or "") + " " + " ".join(business.phones or [])
    return "Priya" if "+91" in phone else "Emily"


def _rating_line(business) -> str:
    if business.rating and float(business.rating) >= 4.0:
        count = f" across {business.review_count:,}+ reviews" if business.review_count else ""
        return (
            f"Your {float(business.rating):.1f}★ reputation{count} deserves "
            "better than voicemail."
        )
    return ""


def compose_outreach_email(business, score, enricher_result: dict | None = None) -> dict:
    """Returns {subject, html, text, to, template, demo_ready, demo_is_local}."""
    biz = business.name
    angle = _angle_key(
        score.pitch_angle if score else None,
        score.qualification_reason if score else None,
    )
    subject = _SUBJECTS[angle].format(biz=biz)
    hook = _HOOKS[angle].format(biz=biz)
    first_name = _first_name(business)
    agent = _agent_name(business)
    rating_line = _rating_line(business)

    # Evidence: the concrete thing we saw, with its real link. Hiring leads
    # cite the job posting; others use the scored pitch source.
    evidence_text, evidence_url = None, None
    if angle == "hiring" and enricher_result:
        ev = enricher_result.get("hiring_evidence") or []
        src = enricher_result.get("hiring_sources") or []
        if ev:
            evidence_text = ev[0]
        if src and src[0].get("url"):
            evidence_url = src[0]["url"]
    if not evidence_text and score and score.qualification_reason:
        evidence_text = score.qualification_reason
        if isinstance(score.pitch_source, dict):
            evidence_url = score.pitch_source.get("url")

    demo_url = business.demo_url or ""
    demo_ready = bool(demo_url)
    demo_is_local = "localhost" in demo_url or "127.0.0.1" in demo_url

    e = _html.escape
    ev_html = ""
    if evidence_text:
        link_html = (
            f'&nbsp;<a href="{e(evidence_url)}" style="color:{ACCENT};text-decoration:none;">(what we saw &rarr;)</a>'
            if evidence_url else ""
        )
        ev_html = f"""
        <tr><td style="padding:0 32px 20px 32px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="background:#F5F6FA;border-left:3px solid {ACCENT};border-radius:6px;">
            <tr><td style="padding:12px 16px;font-size:13px;color:#555C6E;line-height:1.5;">
              {e(evidence_text)}{link_html}
            </td></tr>
          </table>
        </td></tr>"""

    rating_html = (
        f'<tr><td style="padding:0 32px 20px 32px;font-size:15px;color:#333A48;line-height:1.6;">{e(rating_line)}</td></tr>'
        if rating_line else ""
    )

    cta_href = e(demo_url) if demo_ready else "#"
    html_body = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#EEF0F5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF0F5;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;width:100%;background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(20,24,40,.08);">
  <tr><td style="height:5px;background:linear-gradient(90deg,{ACCENT},{ACCENT_DARK});font-size:0;">&nbsp;</td></tr>
  <tr><td style="padding:26px 32px 8px 32px;">
    <span style="font-size:19px;font-weight:800;letter-spacing:-0.3px;color:{ACCENT_DARK};">Deskie</span>
    <span style="font-size:12px;color:#9AA1B2;">&nbsp;&nbsp;AI receptionists for local businesses</span>
  </td></tr>
  <tr><td style="padding:18px 32px 14px 32px;font-size:15px;color:#333A48;line-height:1.6;">
    Hi {e(first_name)},
  </td></tr>
  <tr><td style="padding:0 32px 20px 32px;font-size:15px;color:#333A48;line-height:1.6;">
    {e(hook)}
  </td></tr>
  {ev_html}
  {rating_html}
  <tr><td style="padding:2px 32px 8px 32px;" align="center">
    <a href="{cta_href}"
       style="display:inline-block;background:{ACCENT};color:#FFFFFF;text-decoration:none;font-size:15px;font-weight:700;padding:14px 28px;border-radius:10px;">
      &#127911;&nbsp; Talk to {e(agent)} &mdash; {e(biz)}'s AI receptionist
    </a>
  </td></tr>
  <tr><td align="center" style="padding:0 32px 24px 32px;font-size:12px;color:#9AA1B2;">
    Live voice demo &middot; no signup &middot; already configured for {e(biz)}
  </td></tr>
  <tr><td style="padding:0 32px 26px 32px;font-size:15px;color:#333A48;line-height:1.6;">
    If she isn't better than voicemail on your busiest day, just ignore me.
  </td></tr>
  <tr><td style="padding:0 32px 26px 32px;">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="font-size:14px;color:#333A48;line-height:1.5;">
        <strong>Niket</strong> &middot; Deskie<br>
        <a href="mailto:deskie70@gmail.com" style="color:{ACCENT};text-decoration:none;">deskie70@gmail.com</a>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:14px 32px;background:#FAFAFC;border-top:1px solid #EEF0F5;font-size:11px;color:#B0B6C4;line-height:1.5;">
    You're receiving this one-time note because {e(biz)}'s public listing suggested our product could help.
    Reply &ldquo;unsubscribe&rdquo; and we won't email again.
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

    text_lines = [
        f"Hi {first_name},",
        "",
        hook,
        "",
    ]
    if evidence_text:
        text_lines += [f"({evidence_text}" + (f" — {evidence_url})" if evidence_url else ")"), ""]
    if rating_line:
        text_lines += [rating_line, ""]
    text_lines += [
        f"Talk to {agent} — {biz}'s AI receptionist (live, no signup):",
        demo_url if demo_ready else "[demo link pending]",
        "",
        "If she isn't better than voicemail on your busiest day, just ignore me.",
        "",
        "Niket · Deskie",
        "deskie70@gmail.com",
        "",
        'You\'re receiving this one-time note because your public listing suggested our product could help. Reply "unsubscribe" and we won\'t email again.',
    ]
    text_body = "\n".join(text_lines)

    to = business.email or None
    if not to:
        for c in business.poc_contacts or []:
            if c.get("emails"):
                to = c["emails"][0]
                break

    return {
        "subject": subject,
        "html": html_body,
        "text": text_body,
        "to": to,
        "template": angle,
        "demo_ready": demo_ready,
        "demo_is_local": demo_is_local,
    }


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "")
