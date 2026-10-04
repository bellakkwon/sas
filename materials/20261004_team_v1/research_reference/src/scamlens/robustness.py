"""Deterministic defensive transformations for robustness evaluation."""

from __future__ import annotations

import unicodedata


def insert_spaces(text: str, every: int = 2) -> str:
    """Insert spaces inside Korean alphabetic runs at a fixed interval."""
    if every < 1:
        raise ValueError("every must be at least 1")
    output: list[str] = []
    run = 0
    for char in text:
        if "가" <= char <= "힣":
            if run and run % every == 0:
                output.append(" ")
            run += 1
        else:
            run = 0
        output.append(char)
    return "".join(output)


def insert_symbol(text: str, symbol: str = "·", every: int = 3) -> str:
    """Insert a visible separator inside Korean alphabetic runs."""
    if not symbol or every < 1:
        raise ValueError("symbol must be non-empty and every must be at least 1")
    output: list[str] = []
    run = 0
    for char in text:
        if "가" <= char <= "힣":
            if run and run % every == 0:
                output.append(symbol)
            run += 1
        else:
            run = 0
        output.append(char)
    return "".join(output)


def decompose_hangul(text: str) -> str:
    """Use Unicode NFD to create a reproducible Hangul jamo stress case."""
    return unicodedata.normalize("NFD", text)


def generate_variants(text: str) -> dict[str, str]:
    """Return named variants so original/variant pairs remain traceable."""
    return {
        "original": text,
        "space_insertion": insert_spaces(text),
        "symbol_insertion": insert_symbol(text, every=2),
        "jamo_decomposition": decompose_hangul(text),
    }
