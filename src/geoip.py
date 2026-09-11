"""Best-effort IP -> country lookup for localizing crisis helplines.

Called lazily, only when a message is actually flagged as crisis (see
safety.py) - never on ordinary messages - to keep both latency and how often
a visitor's IP leaves this process to a minimum.

Free, keyless geolocation APIs are unreliable from shared cloud egress IPs
(Railway's outbound IPs are shared across many customers, and ipapi.co - the
first provider tried here - rate-limited almost immediately in testing from
one such IP). Two independent providers are tried in order; if both fail this
returns None and the crisis response falls back to the international
directory (findahelpline.com etc.) - always shown regardless, so a geoip
failure only means less localization, never no help.
"""
import logging
import re

import httpx  # transitive dep of anthropic - avoids adding a new backend dependency

logger = logging.getLogger("geoip")

_TIMEOUT = 2.5
_IP_RE = re.compile(r"^[0-9a-fA-F.:]+$")  # loose IPv4/IPv6 sanity check

_PROVIDERS = [
    ("https://ipwho.is/{ip}", lambda d: d.get("country_code") if d.get("success") else None),
    ("http://ip-api.com/json/{ip}?fields=status,countryCode",
     lambda d: d.get("countryCode") if d.get("status") == "success" else None),
]

# tiny bounded cache so a chatty visitor doesn't re-trigger a lookup per crisis
# message in the same conversation. Not thread-safety-critical - worst case is
# a duplicate lookup, not a wrong answer.
_CACHE_MAX = 500
_cache = {}


def lookup_country(ip):
    if not ip or not _IP_RE.match(ip) or ip in ("127.0.0.1", "::1"):
        return None
    if ip in _cache:
        return _cache[ip]

    country = None
    for url_tpl, extract in _PROVIDERS:
        try:
            r = httpx.get(url_tpl.format(ip=ip), timeout=_TIMEOUT)
            if r.status_code == 200:
                country = extract(r.json())
                if country:
                    break
        except Exception:
            logger.warning("geoip provider failed: %s", url_tpl, exc_info=True)

    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[ip] = country
    return country
