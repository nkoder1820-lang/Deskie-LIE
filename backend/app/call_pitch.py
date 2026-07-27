"""
Cold-call pitch builder (hiring-first leads)
============================================
Turns a lead's actual job posting into a call script.

The core idea is honesty, and it's also what makes the pitch land: most
front-desk roles mix PHYSICAL duties (greeting walk-ins, handling couriers,
escorting visitors) with DIGITAL/PHONE duties (answering calls, booking
appointments, taking messages, chasing follow-ups). Deskie cannot and should
not claim the physical half. So the script explicitly hands the physical
duties back to their human hire and offers to take the phone load off that
person — which is a far easier "yes" than "replace your receptionist", and
it's true.

Deterministic on purpose: no LLM at call time, so what the operator reads on
screen is exactly what the script says, and duty claims are always traceable
to phrases actually present in the posting.
"""
import re

from app.outreach_templates import _calendly_url

# Duty patterns -> (bucket, plain-English label).
#   "digital"  = Deskie can genuinely do this today
#   "physical" = stays with the human hire; we say so out loud
_DUTY_PATTERNS: list[tuple[str, str, str]] = [
    # ── Digital / phone work Deskie handles ─────────────────────────────────
    (r"answer(ing)? (all )?(incoming|inbound)? ?calls?|call handling|handle .{0,15}calls|attend(ing)? calls",
     "digital", "answering every incoming call"),
    (r"outbound calls?|follow[- ]?up calls?|calling (back|patients|customers)",
     "digital", "outbound follow-up calls"),
    (r"appointment|schedul(e|ing)|book(ing)?s?\b|calendar",
     "digital", "booking and rescheduling appointments"),
    (r"transfer(ring)? calls?|route (calls|enquiries|inquiries)|redirect(ing)?|switchboard|forward(ing)? calls?",
     "digital", "routing callers to the right department"),
    (r"messages?|take down|relay|convey",
     "digital", "taking and delivering messages"),
    (r"enquir|inquir|questions? from (patients|customers|clients)|answer(ing)? questions",
     "digital", "answering common questions (hours, services, directions)"),
    (r"phone (records?|logs?)|call logs?|maintain.{0,20}records?|documentation|report(s|ing)",
     "digital", "logging every call automatically"),
    (r"reminder|confirm(ation|ing)? (of )?appointments?|no[- ]show",
     "digital", "appointment reminders and confirmations"),
    (r"email|correspondence|whatsapp|chat",
     "digital", "handling written enquiries"),
    (r"order status|tracking|shipment status|delivery status|track(ing)? (orders?|shipments?)",
     "digital", "answering order/shipment status calls"),
    (r"after[- ]?hours|24[/x]7|night shift|weekend",
     "digital", "covering after-hours and weekends"),
    (r"lead|prospect|new (patient|customer|client) (intake|registration)",
     "digital", "capturing new enquiries as leads"),
    # ── Physical / in-person work that stays with the hire ───────────────────
    (r"greet(ing)? (guests?|visitors?|patients?|clients?|customers?)|welcom(e|ing)|meet and greet|reception area",
     "physical", "greeting people who walk in"),
    (r"escort(ing)?|guide (guests?|visitors?)|show(ing)? .{0,15}(around|to their)",
     "physical", "escorting visitors"),
    (r"courier|mail|parcels?|packages?|post\b|deliver(y|ies) (received|handling)",
     "physical", "receiving mail and parcels"),
    (r"shipment routing|dispatch|warehouse|loading|inventory|stock",
     "physical", "physical dispatch and stock handling"),
    (r"filing|photocop|scan(ning)? documents?|paperwork|stationery",
     "physical", "filing and paperwork"),
    (r"visitor (log|badge|pass)|sign[- ]?in|id (card|badge)",
     "physical", "visitor badges and sign-in"),
    (r"refreshments?|tea|coffee|water|hospitality tray",
     "physical", "hosting and refreshments"),
    (r"keep(ing)? .{0,20}(clean|tidy)|housekeep|maintain.{0,15}(lobby|reception area)",
     "physical", "keeping the reception area presentable"),
    (r"cash|payment(s)? (collection|handling)|billing counter|invoice",
     "physical", "handling payments at the counter"),
]

# Role persona -> how to frame the opening line.
_PERSONAS: list[tuple[str, str]] = [
    (r"telephone|telecall|switchboard|call handler|phone operator|call cent", "phone_only"),
    (r"patient coordinator|medical receptionist|clinic|hospital|dental", "clinical"),
    (r"guest relations|hotel|hospitality|concierge|spa|salon", "hospitality"),
    (r"dispatch|shipment|logistics|warehouse|supply", "logistics"),
    (r"admin|office assistant|office administrator|secretary|executive assistant", "admin"),
    (r"front desk|front office|reception", "front_desk"),
]

_OPENERS = {
    "phone_only": (
        "I saw you're hiring a {role}. That role is almost entirely phone work — "
        "which is exactly the part we can take off your plate on day one."
    ),
    "clinical": (
        "I saw you're hiring a {role}. In a clinic that role is mostly the phone: "
        "appointments, timings, and patients who need a human on the line."
    ),
    "hospitality": (
        "I saw you're hiring a {role}. Guests in the lobby need a person — but the "
        "phone ringing while your team is with a guest is a different problem."
    ),
    "logistics": (
        "I saw you're hiring a {role}. A lot of that role is people calling to ask "
        "where their order or shipment is, which we can answer automatically."
    ),
    "admin": (
        "I saw you're hiring a {role}. Most of those roles lose hours a day to the "
        "phone instead of the actual admin work."
    ),
    "front_desk": (
        "I saw you're hiring a {role}. Your front desk needs a real person for the "
        "people standing in front of them — the phone is what stops them doing that well."
    ),
    "default": (
        "I saw you're hiring a {role}, so the front-desk load is clearly on your mind."
    ),
}


def _persona(role: str, title: str, jd: str) -> str:
    hay = f"{role} {title}".lower()
    for pattern, name in _PERSONAS:
        if re.search(pattern, hay):
            return name
    for pattern, name in _PERSONAS:      # fall back to the JD body
        if re.search(pattern, jd.lower()):
            return name
    return "default"


def extract_duties(jd_text: str) -> tuple[list[str], list[str]]:
    """Split the posting's duties into (digital, physical), deduped, in the
    order our patterns list them. Only duties actually present in the text."""
    text = (jd_text or "").lower()
    digital, physical = [], []
    for pattern, bucket, label in _DUTY_PATTERNS:
        if re.search(pattern, text):
            (digital if bucket == "digital" else physical).append(label)
    return list(dict.fromkeys(digital)), list(dict.fromkeys(physical))


def build_call_pitch(
    business_name: str,
    role: str,
    enricher_result: dict | None,
    city: str | None = None,
    country_is_india: bool = True,
    agent_name: str = "Priya",
    demo_url: str | None = None,
) -> dict:
    """Returns {script, digital_duties, physical_duties, persona, has_jd}."""
    enricher = enricher_result or {}
    descriptions = enricher.get("hiring_descriptions") or []
    jd_text = " ".join(d.get("text", "") for d in descriptions)
    title = (descriptions[0].get("title") if descriptions else "") or role

    digital, physical = extract_duties(jd_text)
    persona = _persona(role, title, jd_text)
    opener = _OPENERS.get(persona, _OPENERS["default"]).format(role=title or role)

    # Never pitch an empty list — if the posting was thin, fall back to the
    # duties every front-desk role has.
    if not digital:
        digital = [
            "answering every incoming call",
            "booking and rescheduling appointments",
            "taking and delivering messages",
        ]

    salary = ("₹18,000–25,000 a month plus training and cover for leave"
              if country_is_india else
              "$2,500+ a month plus training and cover for time off")
    price = "₹8,299/month" if country_is_india else "$99/month"

    lines: list[str] = []
    lines.append(f"OPENER — “Hi, is this {business_name}? My name's Niket, from Deskie. "
                 f"Do you have 30 seconds?”")
    lines.append("")
    lines.append(f"HOOK — “{opener}”")
    lines.append("")

    if physical:
        lines.append("THE HONEST SPLIT — “To be clear about what we are and aren't:")
        lines.append(f"   • Your new hire still does the in-person part — "
                     f"{_join(physical)}. We don't touch any of that.")
        lines.append(f"   • What we take over is the phone side — {_join(digital[:4])}.")
        lines.append("   So they're free to look after whoever is standing in front of them, "
                     "instead of picking up mid-conversation.”")
    else:
        lines.append("WHAT WE DO — “We handle the phone side end to end — "
                     f"{_join(digital[:4])} — 24/7, answered in under a second.”")
    lines.append("")

    lines.append("WHY IT MATTERS — “Right now, every call that rings out while your desk is "
                 "busy is usually someone booking with whoever picks up next. "
                 f"A hire costs {salary}; {agent_name} costs {price}, never takes leave, "
                 "and answers on the first ring at 2am.”")
    lines.append("")
    lines.append(f"PROOF — “I've already built one for {business_name}"
                 f"{f' — she knows your {city} location' if city else ''}"
                 ", using your own public details. You can hear her yourself in about "
                 "60 seconds, no signup.”")
    if demo_url:
        lines.append(f"   Send: {demo_url}")
    lines.append("")
    lines.append("ASK — “Can I send you that link on WhatsApp right now while we're talking? "
                 "If she's not better than your voicemail, tell me and I'll leave you alone.”")
    booking = _calendly_url()
    if booking:
        lines.append("   THEN — “If she sounds right, grab 15 minutes on my calendar and I'll "
                     "set her up on your real number — that's the Deskie setup discovery call.”")
        lines.append(f"   Send: {booking}")
    lines.append("")
    lines.append("IF THEY SAY “we still need the person”  —  “Completely agree, and you should "
                 "hire them. This just means they answer the door, not the phone. Most desks "
                 "lose the walk-in because the phone won't stop.”")
    lines.append("IF THEY SAY “send an email”  —  “Will do — what's the best address? "
                 "The link works straight from the phone, takes a minute.”")
    lines.append("IF THEY SAY “does it sound robotic?”  —  “Best answer is to hear it. "
                 "30 seconds on the link and you'll know.”")

    return {
        "script": "\n".join(lines),
        "digital_duties": digital,
        "physical_duties": physical,
        "persona": persona,
        "has_jd": bool(jd_text),
        "role_title": title or role,
    }


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
