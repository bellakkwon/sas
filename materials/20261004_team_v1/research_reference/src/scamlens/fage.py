"""Leak-free FAGE feature helpers. Experiment I/O lives in the runner script."""

from __future__ import annotations

import numpy as np

FIXED_TEXT_WEIGHT = 0.70
EXPERT_ORDER = ("lr_a", "lr_c", "word", "kcbert", "url")
TEXT_EXPERTS = EXPERT_ORDER[:-1]
URL_EXPERT = "url"
STACKING_FEATURES = (
    "p_lr_a",
    "p_lr_c",
    "p_word",
    "p_kcbert_filled",
    "p_url_filled",
    "p_kcbert_missing",
    "p_url_missing",
)
FAGE_FEATURES = STACKING_FEATURES + (
    "has_url",
    "similarity_to_train",
    "model_disagreement",
    "uncertainty",
)
SAS_COLUMNS = (
    "message_id",
    "seed",
    "fold",
    "role",
    "similarity_group_id",
    "label",
    "target",
    "has_url",
    "p_lr_a",
    "p_lr_c",
    "p_word",
    "p_kcbert_filled",
    "p_kcbert_missing",
    "p_url_filled",
    "p_url_missing",
    "similarity_to_train",
    "model_disagreement",
    "uncertainty",
)


def _masked(probs: np.ndarray, available: np.ndarray) -> np.ma.MaskedArray:
    probs = np.asarray(probs, dtype=float)
    available = np.asarray(available, dtype=bool)
    if probs.shape != available.shape or probs.ndim != 2 or probs.shape[1] == 0:
        raise ValueError("expert_shape_mismatch")
    if not np.isfinite(probs).all():
        raise ValueError("non_finite_expert_probability")
    return np.ma.array(probs, mask=~available)


def equal_weight_scores(probs: np.ndarray, available: np.ndarray) -> np.ndarray:
    """Mean of experts that are allowed for that row. URL is off when unavailable."""
    return _masked(probs, available).mean(axis=1).filled(0.0)


def disagreement_scores(probs: np.ndarray, available: np.ndarray) -> np.ndarray:
    masked = _masked(probs, available)
    return (masked.max(axis=1) - masked.min(axis=1)).filled(0.0)


def uncertainty_scores(mean_probability: np.ndarray) -> np.ndarray:
    mean_probability = np.asarray(mean_probability, dtype=float)
    if mean_probability.ndim != 1:
        raise ValueError("mean_probability_must_be_1d")
    return 1.0 - np.abs(2.0 * mean_probability - 1.0)


def fixed_weight_scores(
    text_mean: np.ndarray,
    url_probability: np.ndarray,
    url_available: np.ndarray,
    *,
    text_weight: float = FIXED_TEXT_WEIGHT,
) -> np.ndarray:
    if not 0 <= text_weight <= 1:
        raise ValueError("text_weight_out_of_range")
    text_mean = np.asarray(text_mean, dtype=float)
    url_probability = np.asarray(url_probability, dtype=float)
    url_available = np.asarray(url_available, dtype=bool)
    if not (text_mean.shape == url_probability.shape == url_available.shape):
        raise ValueError("fixed_weight_shape_mismatch")
    mixed = text_weight * text_mean + (1.0 - text_weight) * url_probability
    return np.where(url_available, mixed, text_mean)


def expert_availability(
    has_url: np.ndarray,
    kcbert_missing: np.ndarray,
    url_missing: np.ndarray,
    *,
    experts: tuple[str, ...] = EXPERT_ORDER,
) -> np.ndarray:
    has_url = np.asarray(has_url, dtype=int)
    kcbert_missing = np.asarray(kcbert_missing, dtype=int)
    url_missing = np.asarray(url_missing, dtype=int)
    n = len(has_url)
    if not (len(kcbert_missing) == len(url_missing) == n):
        raise ValueError("availability_length_mismatch")
    columns = []
    for name in experts:
        if name == "url":
            columns.append((has_url == 1) & (url_missing == 0))
        elif name == "kcbert":
            columns.append(kcbert_missing == 0)
        elif name in TEXT_EXPERTS:
            columns.append(np.ones(n, dtype=bool))
        else:
            raise ValueError(f"unknown_expert:{name}")
    return np.column_stack(columns)


def context_from_experts(probs: np.ndarray, available: np.ndarray) -> dict[str, np.ndarray]:
    equal = equal_weight_scores(probs, available)
    return {
        "equal_weight": equal,
        "model_disagreement": disagreement_scores(probs, available),
        "uncertainty": uncertainty_scores(equal),
        "available_expert_count": np.asarray(available, dtype=bool).sum(axis=1).astype(int),
    }
