"""Predeclared, offline lexical action cues for exploratory SMS research.

These features are word-pattern indicators, not validated intent annotations,
maliciousness labels, or a classifier. In particular, an advisory SMS can contain
the same words as a harmful request. The advisory cue is kept alongside all
other cues rather than used as a rule that declares a message safe.

The vocabulary is fixed before any follow-up validation or test evaluation.
Do not change it in response to validation/test errors or measured performance;
a revised vocabulary requires a separately versioned research protocol. No
network access, text retention, URL resolution, logging, or learned state occurs.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


ACTION_CUE_VERSION = "2026-09-09.v1"


def _near(left: str, right: str) -> str:
    """Co-occurrence in either order, within 40 characters in one sentence.

    Co-occurrence does not establish who is requesting what. The bounded window
    is a declared lexical heuristic, not a threshold selected using data.
    """
    gap = r"[^.!?。！？\n]{0,40}"
    return rf"(?:(?:{left}){gap}(?:{right})|(?:{right}){gap}(?:{left}))"


# Patterns and their order are the complete v1 feature specification. They are
# deliberately generic and were not derived from dataset messages or errors.
_FEATURE_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "transfer_payment_request_cue",
        _near(
            r"송금|입금|이체|결제|대금|금액|돈",
            r"해\s*줘|해\s*주|해\s*라|하\s*세요|하시|바랍|부탁|요청|보내|납부",
        ),
    ),
    (
        "credential_request_cue",
        _near(
            r"비밀번호|인증\s*번호|인증\s*코드|보안\s*코드|보안\s*카드|일회용\s*암호|otp",
            r"알려|전달|보내|입력|공유|제출|말해|말씀",
        ),
    ),
    (
        "app_remote_access_request_cue",
        _near(
            r"앱|어플|애플리케이션|프로그램|원격",
            r"설치|실행|접속|연결|제어|허용",
        ),
    ),
    (
        "contact_channel_migration_cue",
        r"전화\s*(?:해|주|하)|연락\s*(?:해|주|하)|"
        r"문자\s*(?:해|줘|주)|"
        + _near(
            r"카톡|카카오톡|메신저|채팅|다른\s*번호|다른\s*계정",
            r"연락|추가|대화|옮기|이동|보내",
        ),
    ),
    (
        "urgency_cue",
        r"긴급|급해|급한|즉시|지금\s*바로|서둘러|오늘\s*안에|마감",
    ),
    (
        "secrecy_cue",
        r"비밀|혼자|말하지\s*마|알리지\s*마|누구에게도",
    ),
    (
        "institution_claim_cue",
        _near(
            r"검찰|경찰|공공\s*기관|금융\s*기관|은행|국세청|우체국|고객\s*센터",
            r"입니다|인데|담당|직원|안내|통보|연락|전화",
        ),
    ),
    (
        "family_claim_cue",
        _near(
            r"엄마|아빠|어머니|아버지|아들|딸|가족",
            r"나야|인데|입니다|휴대\s*폰|전화\s*기|폰이|내가",
        ),
    ),
    (
        "negation_advisory_cue",
        r"하지\s*마|하지\s*않|하지\s*말|않습니다|마세요|금지|"
        r"주의|예방|피해\s*사례|사기\s*사례|요구하지|요청하지|"
        r"의심\s*(?:문자|전화|메시지)|신고\s*(?:하|해|해주)",
    ),
)

FEATURE_NAMES = tuple(name for name, _ in _FEATURE_PATTERNS)
VOCABULARY_SHA256 = hashlib.sha256(
    json.dumps(
        {"version": ACTION_CUE_VERSION, "patterns": _FEATURE_PATTERNS},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
_COMPILED_PATTERNS = tuple(re.compile(pattern) for _, pattern in _FEATURE_PATTERNS)


def _validate_text_list(texts: object) -> list[str]:
    """Fail closed without including potentially sensitive values in errors."""
    if not isinstance(texts, list):
        raise TypeError("SMS action cues require a list of text strings, not records.")
    if any(not isinstance(text, str) for text in texts):
        raise TypeError("Every SMS action-cue input must be a text string.")
    return texts


def _normalize_for_matching(text: str) -> str:
    # Preserve sentence/newline boundaries. This local view never replaces the
    # caller's original or stored normalized text.
    value = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[^\S\n]+", " ", value)


class SmsActionCueTransformer(TransformerMixin, BaseEstimator):
    """Stateless sklearn-compatible transformer of ``list[str]`` to binary cues.

    The output is a dense ``float64`` array of shape ``(n_messages, 9)`` in
    ``FEATURE_NAMES`` order. ``fit`` only checks input type; it does not inspect
    labels, select words, estimate parameters, or retain messages. ``transform``
    is valid before ``fit`` because there is no learned state.

    Only an explicit list of strings is accepted. Dictionaries, lists of row
    mappings, DataFrames, bytes, and implicit string conversions are rejected
    to reduce accidental use of ``explanation`` or label-bearing records. This
    cannot identify a string already extracted from a forbidden column: the
    caller must select only the approved SMS text field.

    ``y`` is accepted for Pipeline/FeatureUnion compatibility and ignored.
    """

    def fit(self, X: list[str], y: object = None) -> SmsActionCueTransformer:
        _validate_text_list(X)
        return self

    def transform(self, X: list[str]) -> np.ndarray:
        texts = _validate_text_list(X)
        result = np.zeros((len(texts), len(FEATURE_NAMES)), dtype=np.float64)
        for row_index, text in enumerate(texts):
            normalized = _normalize_for_matching(text)
            for column_index, pattern in enumerate(_COMPILED_PATTERNS):
                result[row_index, column_index] = float(pattern.search(normalized) is not None)
        return result

    def get_feature_names_out(self, input_features: object = None) -> np.ndarray:
        """Return a fresh copy of the fixed names; input names are not features."""
        return np.asarray(FEATURE_NAMES, dtype=object).copy()

    def __sklearn_is_fitted__(self) -> bool:
        return True
