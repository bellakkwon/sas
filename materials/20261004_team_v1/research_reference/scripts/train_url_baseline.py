#!/usr/bin/env python3
"""Train a phishing URL model from offline lexical features only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedGroupKFold


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))
from scripts._paths import display_path, resolved_path
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from scamlens.url_features import lexical_features  # noqa: E402
from scripts.train_text_baselines import metric_bundle  # noqa: E402


def to_phishing_target(uci_label: pd.Series) -> np.ndarray:
    """UCI uses 1=legitimate and 0=phishing; project positive class is phishing."""
    unexpected = set(uci_label.dropna().unique()) - {0, 1}
    if unexpected:
        raise ValueError(f"Unexpected UCI labels: {sorted(unexpected)}")
    return (uci_label.astype(int) == 0).astype(int).to_numpy()


def stable_url_id(url: str) -> str:
    return "uci-url-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def hostname_group(url: str) -> str:
    """Hash the full hostname so it can group splits without being persisted."""
    parseable = re.sub(r"(?i)^hxxps://", "https://", str(url).strip())
    parseable = re.sub(r"(?i)^hxxp://", "http://", parseable)
    if "://" not in parseable:
        parseable = "http://" + parseable
    try:
        host = (urlsplit(parseable).hostname or "").lower()
    except ValueError:
        host = ""
    value = host if host else f"malformed:{url}"
    return "host-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def grouped_split(
    target: np.ndarray,
    groups: np.ndarray,
    *,
    random_state: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    indexes = np.arange(len(target))
    outer = StratifiedGroupKFold(
        n_splits=7,
        shuffle=True,
        random_state=random_state,
    )
    remaining_indexes, test_indexes = next(
        outer.split(indexes, target, groups)
    )
    inner = StratifiedGroupKFold(
        n_splits=6,
        shuffle=True,
        random_state=random_state + 1,
    )
    train_relative, validation_relative = next(
        inner.split(
            remaining_indexes,
            target[remaining_indexes],
            groups[remaining_indexes],
        )
    )
    train_indexes = remaining_indexes[train_relative]
    validation_indexes = remaining_indexes[validation_relative]
    return train_indexes, validation_indexes, test_indexes


def select_url_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    *,
    maximum_fpr: float,
) -> tuple[float, dict]:
    candidates: list[tuple[float, dict]] = []
    for threshold in np.linspace(0.05, 0.95, 181):
        metrics = metric_bundle(y_true, probabilities, float(threshold))
        if metrics["false_positive_rate"] <= maximum_fpr:
            candidates.append((float(threshold), metrics))
    if not candidates:
        threshold = 0.5
        return threshold, metric_bundle(y_true, probabilities, threshold)
    threshold, metrics = max(
        candidates,
        key=lambda item: (
            item[1]["recall"],
            item[1]["precision"],
            -item[1]["false_positive_rate"],
        ),
    )
    return threshold, metrics


def train(
    input_path: Path,
    features_output: Path,
    model_output: Path,
    *,
    maximum_fpr: float,
    random_state: int,
) -> dict:
    source = pd.read_csv(input_path, usecols=["URL", "label"])
    duplicate_rows = int(source.duplicated("URL").sum())
    conflicting_urls = int(source.groupby("URL")["label"].nunique().gt(1).sum())
    if conflicting_urls:
        conflicting_values = set(
            source.groupby("URL")["label"].nunique().loc[lambda item: item > 1].index
        )
        source = source[~source["URL"].isin(conflicting_values)]
    source = source.drop_duplicates("URL", keep="first").reset_index(drop=True)

    feature_rows = [lexical_features(str(url)) for url in source["URL"]]
    features = pd.DataFrame(feature_rows)
    target = to_phishing_target(source["label"])
    host_groups = np.array([hostname_group(str(url)) for url in source["URL"]])

    safe_features = features.copy()
    safe_features.insert(
        0,
        "url_id",
        [stable_url_id(str(url)) for url in source["URL"]],
    )
    safe_features["label"] = target
    features_output.parent.mkdir(parents=True, exist_ok=True)
    safe_features.to_csv(features_output, index=False)

    train_indexes, validation_indexes, test_indexes = grouped_split(
        target,
        host_groups,
        random_state=random_state,
    )
    split_host_sets = [
        set(host_groups[indexes])
        for indexes in (train_indexes, validation_indexes, test_indexes)
    ]
    host_group_leakage = sum(
        len(split_host_sets[left] & split_host_sets[right])
        for left, right in ((0, 1), (0, 2), (1, 2))
    )
    if host_group_leakage:
        raise RuntimeError(f"Hostname group leakage detected: {host_group_leakage}")

    model = HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=180,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        random_state=random_state,
    )
    model.fit(features.iloc[train_indexes], target[train_indexes])
    validation_probability = model.predict_proba(
        features.iloc[validation_indexes]
    )[:, 1]
    threshold, validation_selected = select_url_threshold(
        target[validation_indexes],
        validation_probability,
        maximum_fpr=maximum_fpr,
    )
    test_probability = model.predict_proba(features.iloc[test_indexes])[:, 1]

    model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_columns": features.columns.tolist(),
            "threshold": threshold,
            "positive_class": "phishing",
            "network_features": False,
        },
        model_output,
    )

    return {
        "input": display_path(input_path),
        "input_rows": int(len(source) + duplicate_rows),
        "deduplicated_rows": int(len(source)),
        "duplicate_url_rows_removed": duplicate_rows,
        "conflicting_url_groups_excluded": conflicting_urls,
        "label_mapping": {"UCI_1": "legitimate", "UCI_0": "phishing_positive"},
        "feature_policy": "recomputed lexical features only",
        "split_policy": "full-hostname grouped stratified split",
        "hostname_groups": int(len(set(host_groups))),
        "hostname_group_leakage": int(host_group_leakage),
        "feature_columns": features.columns.tolist(),
        "network_access": False,
        "threshold_policy": {
            "selection_split": "validation",
            "maximum_false_positive_rate": maximum_fpr,
            "objective": "maximize recall subject to FPR constraint",
        },
        "split_rows": {
            "train": int(len(train_indexes)),
            "validation": int(len(validation_indexes)),
            "test": int(len(test_indexes)),
        },
        "validation_default": metric_bundle(
            target[validation_indexes], validation_probability, 0.5
        ),
        "validation_selected": validation_selected,
        "test_default": metric_bundle(target[test_indexes], test_probability, 0.5),
        "test_selected": metric_bundle(
            target[test_indexes], test_probability, threshold
        ),
        "features_output": display_path(features_output),
        "model_output": display_path(model_output),
        "limitations": [
            "The split is grouped by full hostname but is not time-based.",
            "URLs are evaluated as strings only; domain age and live reputation are absent.",
            "Results should not be compared directly with models using webpage-source features.",
        ],
    }


def render_markdown(result: dict) -> str:
    metrics = result["test_selected"]
    return "\n".join(
        [
            "# URL lexical 기준 모델 결과",
            "",
            "- UCI 라벨 방향을 `0=피싱 양성`, `1=정상`으로 명시적으로 변환했다.",
            "- UCI가 제공하는 웹페이지 기반 특징은 사용하지 않았다.",
            "- DNS, HTTP, WHOIS, 리디렉션 요청은 수행하지 않았다.",
            f"- 중복 URL 제거: `{result['duplicate_url_rows_removed']:,}`행",
            "",
            "## 테스트 결과",
            "",
            "| 임계값 | Precision | Recall | F1 | Macro F1 | PR-AUC | FPR |",
            "|---:|---:|---:|---:|---:|---:|---:|",
            f"| {metrics['threshold']:.3f} | {metrics['precision']:.3f} | "
            f"{metrics['recall']:.3f} | {metrics['f1']:.3f} | "
            f"{metrics['macro_f1']:.3f} | {metrics['pr_auc']:.3f} | "
            f"{metrics['false_positive_rate']:.3f} |",
            "",
            "## 해석 제한",
            "",
            "- 동일 호스트는 한 분할에만 배정했지만 시간 기반 분할은 아니다.",
            "- 도메인 등록일과 최신 위협 평판은 포함하지 않았다.",
            "- 웹페이지 소스 특징을 사용하는 모델과 성능을 직접 비교하면 안 된다.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=resolved_path,
        default=PROJECT_ROOT / "data/raw/PhiUSIIL_Phishing_URL_Dataset.csv",
    )
    parser.add_argument(
        "--features-output",
        type=resolved_path,
        default=PROJECT_ROOT / "data/processed/phiusiil_lexical_features.csv",
    )
    parser.add_argument(
        "--model-output",
        type=resolved_path,
        default=PROJECT_ROOT / "models/url/lexical_hist_gradient_boosting.joblib",
    )
    parser.add_argument("--maximum-fpr", type=float, default=0.05)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--json-output",
        type=resolved_path,
        default=PROJECT_ROOT / "reports/generated/url_baseline.json",
    )
    parser.add_argument(
        "--md-output",
        type=resolved_path,
        default=PROJECT_ROOT / "reports/generated/url_baseline.md",
    )
    args = parser.parse_args()

    result = train(
        args.input,
        args.features_output,
        args.model_output,
        maximum_fpr=args.maximum_fpr,
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
