#!/usr/bin/env python3
"""Add URL-flipped copies of the training messages under their original label.

The shortcut probe showed both detector families flip their verdict when the
URL marker alone is toggled: 45% of normal messages for the linear model, 76%
for the transformer. That happens because the corpus ties the marker to the
label — ``P(malicious | URL) = 68%`` against ``P(malicious | no URL) = 4%``.

The intervention is to state the opposite in the training data. Every training
message gets a twin with the URL marker flipped and the **same label**, which
says directly: this message's label does not depend on whether it carries a
link. The correlation is not removed from the real rows, it is diluted by
counter-examples.

Only ``train`` is augmented. Touching validation or test would destroy the
comparison the augmentation is meant to be judged by. Twins inherit their
original's similarity group so the split guard still holds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))
from scripts._paths import display_path, resolved_path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scamlens.preprocessing import URL_PLACEHOLDER_RE, WHITESPACE_RE  # noqa: E402

URL_TOKEN = "[url]"


def strip_url_token(text: str) -> str:
    return WHITESPACE_RE.sub(" ", URL_PLACEHOLDER_RE.sub(" ", str(text))).strip()


def add_url_token(text: str) -> str:
    return f"{str(text).strip()} {URL_TOKEN}".strip()


def flip_url_marker(text: str, has_url: bool) -> str:
    return strip_url_token(text) if has_url else add_url_token(text)


def build(input_path: Path) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(input_path)
    train = frame[frame["split"] == "train"].copy()
    held_out = frame[frame["split"] != "train"].copy()
    if train.empty:
        raise ValueError("train rows are required")

    twins = train.copy()
    has_url = train["has_url"].to_numpy().astype(bool)
    twins["text_normalized"] = [
        flip_url_marker(text, flag)
        for text, flag in zip(train["text_normalized"].astype(str), has_url, strict=True)
    ]
    # 원문 컬럼도 같은 방향으로 뒤집어 둔다. 두 컬럼이 어긋나면 나중에
    # 어느 쪽을 썼는지에 따라 결과가 달라진다.
    twins["text_raw_masked"] = [
        flip_url_marker(text, flag)
        for text, flag in zip(train["text_raw_masked"].astype(str), has_url, strict=True)
    ]
    twins["has_url"] = (~has_url).astype(int)
    twins["url_count"] = twins["has_url"]
    twins["message_id"] = [
        "cf-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:18]
        for value in twins["message_id"].astype(str)
    ]
    twins["is_counterfactual"] = 1
    train["is_counterfactual"] = 0
    held_out["is_counterfactual"] = 0

    # 뒤집었는데 본문이 그대로면 URL 표시가 없던 자리에 붙지 않은 것이다.
    unchanged = (
        twins["text_normalized"].to_numpy() == train["text_normalized"].to_numpy()
    )
    # 본문이 URL 표시뿐이던 문자는 뒤집으면 빈 문자열이 된다. 빈 입력에
    # 라벨을 붙이면 "아무 내용도 없으면 악성"을 가르치게 되므로 버린다.
    emptied = twins["text_normalized"].str.strip().eq("")
    dropped = unchanged | emptied.to_numpy()
    twins = twins[~dropped]

    combined = pd.concat([train, twins, held_out], ignore_index=True)

    def prior(part: pd.DataFrame) -> dict:
        target = (part["label"] == "smishing").astype(int)
        url = part["has_url"].astype(bool)
        return {
            "malicious_given_url": round(float(target[url].mean()), 6) if url.any() else None,
            "malicious_given_no_url": round(float(target[~url].mean()), 6)
            if (~url).any()
            else None,
        }

    augmented_train = combined[combined["split"] == "train"]
    summary = {
        "status": "augmented",
        "input": display_path(input_path),
        "original_train_rows": int(len(train)),
        "counterfactual_rows_added": int(len(twins)),
        "rows_unchanged_and_dropped": int(unchanged.sum()),
        "rows_emptied_and_dropped": int(emptied.sum()),
        "augmented_train_rows": int(len(augmented_train)),
        "held_out_rows_untouched": int(len(held_out)),
        "prior_before": prior(train),
        "prior_after": prior(augmented_train),
        "note": (
            "The counterfactual rows make link presence uninformative about the "
            "label by construction; the priors after augmentation should sit near "
            "the base rate."
        ),
        "limitations": [
            "A normal message with a link marker bolted on is text no sender would "
            "produce. The model is being taught invariance using inputs outside the "
            "real distribution, which can cost accuracy on real ones.",
            "Only the URL marker is intervened on. Other spurious cues in the "
            "corpus are untouched.",
            "Messages whose body was nothing but the URL marker cannot be flipped "
            "without becoming empty, so they contribute no counterfactual twin.",
            "Train doubles in size, so a like-for-like comparison needs the same "
            "epoch count rather than the same number of gradient steps.",
        ],
    }
    return combined, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=resolved_path,
        default=PROJECT_ROOT / "data/processed/messages_split.csv",
    )
    parser.add_argument(
        "--output",
        type=resolved_path,
        default=PROJECT_ROOT / "data/processed/messages_split_counterfactual.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=resolved_path,
        default=PROJECT_ROOT / "reports/generated/counterfactual_augmentation.json",
    )
    args = parser.parse_args()

    combined, summary = build(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(args.output, index=False, encoding="utf-8")
    summary["output"] = display_path(args.output)

    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items()
                      if not isinstance(v, (dict, list))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
