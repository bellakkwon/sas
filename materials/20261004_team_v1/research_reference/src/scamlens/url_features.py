"""Offline URL lexical features.

No DNS lookup, HTTP request, redirect following, WHOIS query, or file download is
performed here.
"""

from __future__ import annotations

from collections import Counter
from ipaddress import ip_address
import math
import re
from urllib.parse import urlsplit

SUSPICIOUS_TOKENS = {
    "account",
    "auth",
    "login",
    "secure",
    "update",
    "verify",
    "인증",
    "확인",
}


def _refang_for_parsing(url: str) -> str:
    value = url.strip().replace("[.]", ".")
    value = re.sub(r"(?i)^hxxps://", "https://", value)
    value = re.sub(r"(?i)^hxxp://", "http://", value)
    if "://" not in value:
        value = "http://" + value
    return value


def _is_ip_literal(hostname: str) -> bool:
    try:
        ip_address(hostname)
        return True
    except ValueError:
        return False


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def lexical_features(url: str) -> dict[str, int | float]:
    """Return deterministic, representation-invariant string-only URL features.

    Scheme spelling and a root-only trailing slash are excluded so equivalent
    forms such as ``example.com`` and ``https://example.com/`` do not create a
    label shortcut.
    """
    raw = url.strip()
    malformed = 0
    try:
        parsed = urlsplit(_refang_for_parsing(url))
        hostname = (parsed.hostname or "").lower()
        raw_path = parsed.path or ""
        path = "" if raw_path in {"", "/"} else raw_path
        query = parsed.query or ""
        fragment = parsed.fragment or ""
        try:
            has_port = int(parsed.port is not None)
        except ValueError:
            malformed = 1
            has_port = 0
    except ValueError:
        malformed = 1
        hostname = ""
        path = raw
        query = ""
        fragment = ""
        has_port = 0
    analysis_value = (
        hostname
        + path
        + (f"?{query}" if query else "")
        + (f"#{fragment}" if fragment else "")
    )
    alnum_count = sum(char.isalnum() for char in analysis_value)
    digit_count = sum(char.isdigit() for char in analysis_value)
    special_count = len(analysis_value) - alnum_count
    labels = [part for part in hostname.split(".") if part]
    lowered = analysis_value.lower()

    return {
        "url_length": len(analysis_value),
        "hostname_length": len(hostname),
        "path_length": len(path),
        "path_depth": len([part for part in path.split("/") if part]),
        "digit_ratio": digit_count / len(analysis_value) if analysis_value else 0.0,
        "special_ratio": special_count / len(analysis_value) if analysis_value else 0.0,
        "subdomain_count": max(0, len(labels) - 2),
        "has_ip_literal": int(_is_ip_literal(hostname)),
        "has_port": has_port,
        "has_punycode": int("xn--" in hostname),
        "has_at_symbol": int("@" in raw),
        "is_malformed": malformed,
        "suspicious_token_count": sum(token in lowered for token in SUSPICIOUS_TOKENS),
        "hostname_entropy": _entropy(hostname),
    }
