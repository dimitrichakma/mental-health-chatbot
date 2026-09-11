"""Crisis helpline resources, keyed by 2-letter country code.

Shown verbatim when the safety classifier flags a message as high-risk. The
country is read from the browser's Accept-Language header (resolve_country) -
automatic, no sidebar picker, no IP geolocation, no extra service call: it's a
standard header every browser already sends. It's a best-effort signal (can be
wrong if someone's OS language doesn't match where they are), so a matched
country's response still ends with the international directory as a backup;
unknown/unmatched falls back to the international directory alone, which is
always a safe answer.

Numbers here are the widely-published national lines. Add an entry to
CRISIS_RESOURCES to cover a new country - keep it short, and prefer a 24/7
line plus the national emergency number. Add its ISO code to _EU_CODES if it
should fall back to the "EU" bucket instead of the plain international one.
"""

INTERNATIONAL = [
    "Find a helpline in your country: https://findahelpline.com",
    "International Association for Suicide Prevention directory: "
    "https://www.iasp.info/resources/Crisis_Centres/",
]

# country code -> (display name, [lines])
CRISIS_RESOURCES = {
    "BD": ("Bangladesh", [
        "Emergency services: 999",
        "Kaan Pete Roi (emotional support, 24/7): 09612-119911",
        "Moner Bondhu (24/7 crisis helpline): https://monerbondhu.com",
        "BRAC mental-health helpline: 09643-262626",
    ]),
    "US": ("the United States", [
        "988 Suicide & Crisis Lifeline: call or text 988",
        "Crisis Text Line: text HOME to 741741",
        "Emergency services: 911",
    ]),
    "GB": ("the United Kingdom", [
        "Samaritans: call 116 123 (free, 24/7)",
        "Shout: text SHOUT to 85258",
        "Emergency services: 999",
    ]),
    "IN": ("India", [
        "Tele-MANAS (govt, 24/7): 14416 or 1-800-891-4416",
        "Vandrevala Foundation: 1860-2662-345 (24/7)",
        "Emergency services: 112",
    ]),
    "CA": ("Canada", [
        "9-8-8 Suicide Crisis Helpline: call or text 988 (24/7)",
        "Emergency services: 911",
    ]),
    "AU": ("Australia", [
        "Lifeline: 13 11 14 (24/7)",
        "Beyond Blue: 1300 22 4636",
        "Emergency services: 000",
    ]),
    "EU": ("Europe", [
        "Emergency services: 112",
        "In many EU countries you can reach emotional support on 116 123",
        "Find a local line: https://findahelpline.com",
    ]),
}

# ISO country codes that fall back to the shared "EU" bucket rather than the
# plain international directory. Not exhaustive - the major EU markets.
_EU_CODES = {
    "DE", "FR", "ES", "IT", "NL", "BE", "IE", "PT", "AT", "SE", "DK", "FI",
    "PL", "GR", "CZ", "RO", "HU", "BG", "HR", "SK", "SI", "LT", "LV", "EE",
    "LU", "MT", "CY",
}

_INTRO = (
    "It sounds like you might be going through something very difficult right now. "
    "You deserve support, and you don't have to handle this alone."
)
_CLOSE = "If you are in immediate danger, please contact your local emergency number now."


def resolve_country(accept_language):
    """Best-effort country code from a browser's Accept-Language header, e.g.
    'bn-BD,bn;q=0.9,en-US;q=0.8' -> 'BD'. None if there's no region subtag or
    the header is missing (some browsers send just 'en', no region)."""
    if not accept_language:
        return None
    try:
        first = accept_language.split(",")[0].split(";")[0].strip()
        parts = first.split("-")
        if len(parts) < 2:
            return None
        region = parts[1].upper()
    except Exception:
        return None
    if region in CRISIS_RESOURCES:
        return region
    if region in _EU_CODES:
        return "EU"
    return None


def build_crisis_response(country=None):
    entry = CRISIS_RESOURCES.get((country or "").upper())
    if entry:
        name, lines = entry
        body = (
            f"If you are in {name}, you can reach out to:\n"
            + "\n".join(f"- {ln}" for ln in lines)
            + f"\n\nNot in {name}? {INTERNATIONAL[0]}"
        )
    else:
        body = "Please reach out to a crisis line, or a trusted person near you:\n" + "\n".join(
            f"- {ln}" for ln in INTERNATIONAL
        )
    return f"{_INTRO}\n\n{body}\n\n{_CLOSE}"


# default (no country) response - kept as a constant for the keyword-fallback path
CRISIS_RESPONSE = build_crisis_response(None)
