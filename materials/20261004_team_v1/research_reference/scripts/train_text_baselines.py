#!/usr/bin/env python3
"""Train reproducible word and character TF-IDF smishing baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))
from scripts._paths import display_path, resolved_path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scamlens.preprocessing import neutralize_url_placeholder  # noqa: E402


def metric_bundle(y_true: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict:
    predicted = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
    return {
        "threshold": round(float(threshold), 6),
        "precision": round(float(precision_score(y_true, predicted, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, predicted, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, predicted, zero_division=0)), 6),
        "macro_f1": round(
            float(f1_score(y_true, predicted, average="macro", zero_division=0)), 6
        ),
        "pr_auc": round(float(average_precision_score(y_true, probabilities)), 6),
        "false_positive_rate": round(float(fp / (fp + tn)) if fp + tn else 0.0, 6),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
    }


def select_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    *,
    minimum_recall: float,
) -> tuple[float, dict]:
    candidates: list[tuple[float, dict]] = []
    for threshold in np.linspace(0.05, 0.95, 181):
        metrics = metric_bundle(y_true, probabilities, float(threshold))
        if metrics["recall"] >= minimum_recall:
            candidates.append((float(threshold), metrics))
    if not candidates:
        threshold = 0.5
        return threshold, metric_bundle(y_true, probabilities, threshold)
    threshold, metrics = min(
        candidates,
        key=lambda item: (
            item[1]["false_positive_rate"],
            -item[1]["precision"],
            -item[0],
        ),
    )
    return threshold, metrics


def pipelines(random_state: int) -> dict[str, Pipeline]:
    classifier = lambda: LogisticRegression(  # noqa: E731
        max_iter=1_000,
        class_weight="balanced",
        random_state=random_state,
        solver="liblinear",
    )
    return {
        "word_tfidf_lr": Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        analyzer="word",
                        ngram_range=(1, 2),
                        min_df=2,
                        max_features=80_000,
                        sublinear_tf=True,
                    ),
                ),
                ("model", classifier()),
            ]
        ),
        "char_tfidf_lr": Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        analyzer="char",
                        ngram_range=(3, 5),
                        min_df=2,
                        max_features=120_000,
                        sublinear_tf=True,
                        dtype=np.float32,
                    ),
                ),
                ("model", classifier()),
            ]
        ),
        "char_tfidf_url_neutral_lr": Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        analyzer="char",
                        ngram_range=(3, 5),
                        min_df=2,
                        max_features=120_000,
                        sublinear_tf=True,
                        dtype=np.float32,
                        preprocessor=neutralize_url_placeholder,
                    ),
                ),
                ("model", classifier()),
            ]
        ),
    }


def train(
    input_path: Path,
    model_dir: Path,
    *,
    minimum_recall: float,
    random_state: int,
) -> dict:
    frame = pd.read_csv(input_path)
    train_frame = frame[frame["split"] == "train"]
    validation_frame = frame[frame["split"] == "validation"]
    test_frame = frame[frame["split"] == "test"]
    if min(len(train_frame), len(validation_frame), len(test_frame)) == 0:
        raise ValueError("train, validation, and test rows are all required")

    encode = lambda series: (series == "smishing").astype(int).to_numpy()  # noqa: E731
    y_train = encode(train_frame["label"])
    y_validation = encode(validation_frame["label"])
    y_test = encode(test_frame["label"])
    model_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    for name, pipeline in pipelines(random_state).items():
        pipeline.fit(train_frame["text_normalized"], y_train)
        validation_probability = pipeline.predict_proba(
            validation_frame["text_normalized"]
        )[:, 1]
        selected_threshold, validation_selected = select_threshold(
            y_validation,
            validation_probability,
            minimum_recall=minimum_recall,
        )
        # 학습셋 지표는 배포 성능이 아니라 **과적합 점검용**이다. 이것이 없으면
        # train-test 격차를 아무도 못 본다. 임계값은 검증셋에서 고른 그 값을 그대로
        # 쓴다 — 학습셋에서 다시 고르면 격차 자체가 낙관적으로 줄어든다.
        train_probability = pipeline.predict_proba(train_frame["text_normalized"])[:, 1]
        test_probability = pipeline.predict_proba(test_frame["text_normalized"])[:, 1]
        model_path = model_dir / f"{name}.joblib"
        joblib.dump(pipeline, model_path)
        results[name] = {
            "model_path": display_path(model_path),
            "vocabulary_size": int(len(pipeline.named_steps["tfidf"].vocabulary_)),
            "validation_default": metric_bundle(
                y_validation, validation_probability, 0.5
            ),
            "train_selected": metric_bundle(y_train, train_probability, selected_threshold),
            "validation_selected": validation_selected,
            "test_default": metric_bundle(y_test, test_probability, 0.5),
            "test_selected": metric_bundle(
                y_test, test_probability, selected_threshold
            ),
        }

    for name, values in results.items():
        # 격차를 계산해 두면 읽는 사람이 두 수치를 빼지 않아도 된다. 빼는 일을
        # 사람에게 맡기면 아무도 안 뺀다.
        values["overfitting_gap"] = {
            metric: round(
                float(values["train_selected"][metric] - values["test_selected"][metric]), 6
            )
            for metric in ("f1", "precision", "recall")
        }

    return {
        "input": display_path(input_path),
        "random_state": random_state,
        "threshold_policy": {
            "selection_split": "validation",
            "minimum_malicious_recall": minimum_recall,
            "objective": "minimize false positive rate subject to recall constraint",
        },
        "split_rows": {
            "train": int(len(train_frame)),
            "validation": int(len(validation_frame)),
            "test": int(len(test_frame)),
        },
        "models": results,
        "limitations": [
            "Hard Negative labels are not yet available, so category-specific FPR is pending.",
            "The public dataset provenance and real/synthetic mix remain unknown.",
            "Test results use similarity-grouped splits but not a time-based external set.",
        ],
    }


def render_markdown(result: dict) -> str:
    lines = [
        "# 텍스트 기준 모델 결과",
        "",
        f"- 임계값 정책: 검증셋 악성 Recall `{result['threshold_policy']['minimum_malicious_recall']:.2f}` "
        "이상을 만족하면서 FPR 최소화",
        f"- 분할: train `{result['split_rows']['train']:,}` / validation "
        f"`{result['split_rows']['validation']:,}` / test `{result['split_rows']['test']:,}`",
        "",
        "## 테스트 결과",
        "",
        "| 모델 | 임계값 | Precision | Recall | F1 | Macro F1 | PR-AUC | FPR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, values in result["models"].items():
        metrics = values["test_selected"]
        lines.append(
            f"| `{name}` | {metrics['threshold']:.3f} | {metrics['precision']:.3f} | "
            f"{metrics['recall']:.3f} | {metrics['f1']:.3f} | "
            f"{metrics['macro_f1']:.3f} | {metrics['pr_auc']:.3f} | "
            f"{metrics['false_positive_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 해석 제한",
            "",
            "- Hard Negative 카테고리별 오탐률은 아직 측정하지 않았다.",
            "- 공개 데이터의 실제/합성 비율이 확인되지 않았다.",
            "- 유사도 그룹 분할을 사용했지만 시간 기반 외부 테스트는 아니다.",
            "- 이 결과를 실서비스 성능으로 해석하면 안 된다.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=resolved_path,
        default=PROJECT_ROOT / "data/processed/messages_split.csv",
    )
    parser.add_argument(
        "--model-dir",
        type=resolved_path,
        default=PROJECT_ROOT / "models/text",
    )
    parser.add_argument("--minimum-recall", type=float, default=0.95)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--json-output",
        type=resolved_path,
        default=PROJECT_ROOT / "reports/generated/text_baselines.json",
    )
    parser.add_argument(
        "--md-output",
        type=resolved_path,
        default=PROJECT_ROOT / "reports/generated/text_baselines.md",
    )
    args = parser.parse_args()

    result = train(
        args.input,
        args.model_dir,
        minimum_recall=args.minimum_recall,
        random_state=args.random_state,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.md_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
