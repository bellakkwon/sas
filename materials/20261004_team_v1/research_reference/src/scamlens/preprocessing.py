"""Safe message preprocessing.

These helpers never perform network requests. The raw masked text and normalized
text should be stored separately so evidence is not destroyed.
"""

from __future__ import annotations

from collections import Counter
import re
import unicodedata

# Schemes are strong URL boundaries on their own. A leading ``\b`` misses URLs
# attached directly to Korean text because both Hangul and ASCII letters are
# Unicode "word" characters (for example ``안내https://example.invalid``).
URL_RE = re.compile(
    r"(?i)(?:"
    r"(?:https?|hxxps?)://[^\s<>\"']+"
    r"|(?<![A-Za-z0-9@])www\.[^\s<>\"']+"
    r"|(?<![A-Za-z0-9@])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,24}(?:[/?#][^\s<>\"']*)?"
    r")"
)
# Korean numbers reach a message as mobile, landline, internet, toll-free and
# representative prefixes. Masking only mobile prefixes leaves call-center and
# landline numbers in stored text, so every dialable form is covered here.
# A trailing hyphen is ordinary Korean punctuation (``7000-앱``, ``1111->``), so
# the boundary may only reject a hyphen that continues the number itself. A
# following space never continues a number here: ``02-3297-3791 1번`` is a phone
# number followed by ordinary text, and greedy repetition already absorbs the
# space-separated groups of an account number.
_NUMBER_START = r"(?<!\d)(?<!\d-)"
_NUMBER_END = r"(?!\d)(?!-\d)"
PHONE_RE = re.compile(
    _NUMBER_START
    + r"(?:"
    r"1(?:5|6|8)\d{2}[-\s]?\d{4}"
    r"|0(?:1[016789]|505|507|50|70|80|2|[3-6]\d)[-\s]?\d{3,4}[-\s]?\d{4}"
    r")"
    + _NUMBER_END
)
# ``LONG_NUMBER_RE`` only sees runs of consecutive digits, so grouped card and
# account numbers such as ``1234-5678-9012-3456`` or ``1005 581 2853`` used to
# pass through intact.
CARD_NUMBER_RE = re.compile(_NUMBER_START + r"\d{4}(?:[-\s]\d{4}){3}" + _NUMBER_END)
# Inner groups may hold a single digit (``82-2-6343-9000`` is a Seoul number in
# international form), but the first group needs two so a bare ``5-07-30`` date
# fragment is not treated as the head of an identifier.
GROUPED_NUMBER_RE = re.compile(
    _NUMBER_START + r"\d{2,6}(?:[-\s]\d{1,6}){1,}" + _NUMBER_END
)
# Grouped digits shorter than an account number are dates and times, not
# identifiers, so the digit count decides rather than the separator shape. A
# ``YYYY-MM-DD`` date has eight digits, so nine is the first length that cannot
# be a date.
GROUPED_NUMBER_MIN_DIGITS = 9
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{6,}(?!\d)")
# The journey validator rejects unmasked emails and resident numbers, so the
# shared masking step has to cover them too; leaving them to each caller is how
# they went missing from imported transcripts.
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RRN_RE = re.compile(r"(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)")
# ``URL_RE`` requires content after the scheme, so ``https:// example.invalid``
# loses only its body and leaves a bare scheme behind in stored text.
DANGLING_SCHEME_RE = re.compile(r"(?i)(?:https?|hxxps?)\s*:\s*/\s*/\s*")
# ``www.`` with no host after it is not a link, but leaving the live form in
# stored text means audits cannot tell it apart from one that is.
BARE_WWW_RE = re.compile(r"(?i)www\.(?![A-Za-z0-9])")
WHITESPACE_RE = re.compile(r"\s+")
URL_PLACEHOLDER_RE = re.compile(r"(?i)\[url\]")


def extract_urls(text: str) -> list[str]:
    """Extract URL-like strings without resolving or opening them.

    NFKC is checked as a second in-memory representation because full-width
    characters can become an active ``http`` URL after normalization.
    """
    raw_results = [
        match.rstrip(".,;:!?)]}")
        for match in URL_RE.findall(text)
    ]
    normalized_text = unicodedata.normalize("NFKC", text)
    if normalized_text == text:
        return raw_results
    normalized_results = [
        match.rstrip(".,;:!?)]}")
        for match in URL_RE.findall(normalized_text)
    ]
    remaining = Counter(normalized_results)
    remaining.subtract(Counter(raw_results))
    supplements: list[str] = []
    for value in normalized_results:
        if remaining[value] > 0:
            supplements.append(value)
            remaining[value] -= 1
    return raw_results + supplements


def defang_url(url: str) -> str:
    """Convert a URL into a non-clickable representation."""
    # Refang only the dot marker in memory first so repeated calls remain
    # idempotent instead of producing ``[[.]]``.
    value = url.strip().replace("[.]", ".")
    value = re.sub(r"(?i)^https://", "hxxps://", value)
    value = re.sub(r"(?i)^http://", "hxxp://", value)
    value = re.sub(r"(?i)^www\.", "www[.]", value)
    if "://" in value:
        scheme, remainder = value.split("://", 1)
        host, separator, tail = remainder.partition("/")
        host = host.replace(".", "[.]")
        value = f"{scheme}://{host}{separator}{tail}"
    elif "[.]" not in value:
        host, separator, tail = value.partition("/")
        value = f"{host.replace('.', '[.]')}{separator}{tail}"
    return value


def strip_dangling_scheme(text: str) -> str:
    """Neutralize URL markers left behind after the body was replaced.

    A scheme that still has its own placeholder neighbour is dropped outright so
    one URL does not become two tokens; a scheme standing alone becomes a
    placeholder itself. A bare ``www.`` with no host is defanged in place.
    """

    def replace(match: re.Match[str]) -> str:
        tail = text[match.end() :].lstrip()
        if URL_PLACEHOLDER_RE.match(tail):
            return ""
        return "[URL] " if tail else "[URL]"

    stripped = DANGLING_SCHEME_RE.sub(replace, text)
    return BARE_WWW_RE.sub("www[.]", stripped)


def _mask_grouped_number(match: re.Match[str]) -> str:
    value = match.group(0)
    digits = sum(character.isdigit() for character in value)
    return "[NUMBER]" if digits >= GROUPED_NUMBER_MIN_DIGITS else value


def mask_sensitive_text(text: str) -> str:
    """Apply conservative masks before a message enters the repository."""
    # Card and phone patterns run before the generic digit-run mask so their
    # grouped forms are recognised while still intact.
    masked = RRN_RE.sub("[RRN]", text)
    masked = EMAIL_RE.sub("[EMAIL]", masked)
    masked = CARD_NUMBER_RE.sub("[CARD]", masked)
    masked = PHONE_RE.sub("[PHONE]", masked)
    masked = GROUPED_NUMBER_RE.sub(_mask_grouped_number, masked)
    masked = LONG_NUMBER_RE.sub("[NUMBER]", masked)
    masked = URL_RE.sub("[URL]", masked)
    normalized_candidate = unicodedata.normalize("NFKC", masked)
    if URL_RE.search(normalized_candidate):
        masked = URL_RE.sub("[URL]", normalized_candidate)
    return strip_dangling_scheme(masked)


# Names an attacker uses to address the victim. Structured identifiers are
# masked elsewhere; a personal name is not a number and survives every one of
# those patterns, so it needs its own pass. Deliberately narrow: it only fires
# where a Korean name sits in one of the grammatical frames that make it a name
# rather than a common noun, and a generic-address list keeps 고객님/회원님 intact.
_GENERIC_ADDRESS_ALTERNATION = (
    "고객|회원|사장|원장|팀장|부장|과장|차장|대리|기사|부모|학부모|선생|대표|본인"
    "|어머니|아버지|환자|이용자|가입자|수신자|담당자|관리자|주주|조합원|입주민"
    "|세대주|구독자|학생|교수|소장|지점장|센터장"
)

PERSON_ADDRESS_RES = (
    # 김지영고객님 — a name followed by a generic address term. Handled first
    # because the plain 님 rule below cannot see past the generic word, which is
    # how 245 names survived the previous pass.
    re.compile(
        r"(?<![가-힣])([가-힣]{2,4})(?=\s?(?:%s)님)" % _GENERIC_ADDRESS_ALTERNATION
    ),
    re.compile(r"(?<![가-힣])([가-힣]{2,4})(?=\s?님)"),
    # 씨 followed by a particle is still an address form: 홍길동 씨의, 씨가, 씨는.
    re.compile(r"(?<![가-힣])([가-힣]{2,4})(?=\s?씨(?:[의가는를도와과에]|\b|$))"),
    re.compile(r"귀하\s*\(\s*([가-힣]{2,4})\s*\)"),
    # A label like "수취인: 안지은운송장번호" has no delimiter after the name, and
    # a greedy {2,4} silently ate the 운 from 운송장번호 — masking must never
    # corrupt the surrounding text. So this form only fires when the name is
    # followed by a real boundary, or by a field word that reliably starts the
    # next field. A name with neither is left alone and counted instead.
    re.compile(
        r"(?:성명|이름|수취인|수신인|받으시는\s?분|보내는\s?분|수령인)"
        r"\s*[:：]\s*([가-힣]{2,4})"
        r"(?=\s|$|[^가-힣]|운송장|주소|연락처|전화|상품|우편)"
    ),
)

GENERIC_ADDRESS_TERMS = frozenset(
    {
        "고객", "회원", "사장", "원장", "팀장", "부장", "과장", "차장", "대리",
        "기사", "부모", "학부모", "선생", "대표", "본인", "어머니", "아버지",
        "환자", "이용자", "가입자", "수신자", "담당자", "관리자", "주주", "조합원",
        "입주민", "세대주", "구독자", "학생", "교수", "소장", "지점장", "센터장",
    }
)


def mask_person_names(text: str) -> str:
    """Replace personal names used as an address form with ``[PERSON]``.

    Found on 2026-08-30: 245 rows of the stored KISA export still carried the
    recipient's real name in plain text — the attacker had addressed the victim
    by name, and every existing mask targets digits.

    A greedy version of this once captured four characters before 님 and turned
    "김지영고객님" into the token "지영고객", which then failed the generic-term
    check and got masked as if it were a name. The lookbehind keeps the match
    from starting mid-name, and the generic list is checked against the captured
    token, so 고객님 stays 고객님.

    This is conservative by design. It does not attempt general named-entity
    recognition, and a name appearing without one of these frames survives.
    """

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token in GENERIC_ADDRESS_TERMS:
            return match.group(0)
        return match.group(0).replace(token, "[PERSON]", 1)

    masked = text
    for pattern in PERSON_ADDRESS_RES:
        masked = pattern.sub(replace, masked)
    return masked


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving Korean content."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = URL_RE.sub("[URL]", normalized)
    normalized = strip_dangling_scheme(normalized)
    normalized = normalized.lower()
    return WHITESPACE_RE.sub(" ", normalized).strip()


def neutralize_url_placeholder(text: str) -> str:
    """Remove generic URL-presence tokens from text-only model input.

    URL presence and URL structure are evaluated separately. Keeping ``[url]``
    inside a text model can make normal messages with links look malicious and
    can double-count URL evidence during later fusion.
    """
    return WHITESPACE_RE.sub(
        " ",
        URL_PLACEHOLDER_RE.sub(" ", str(text)),
    ).strip()
