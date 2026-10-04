#!/usr/bin/env python3
"""Build a leakage-safe auxiliary training table from local KR-MOB JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))
from scripts._paths import display_path, resolved_path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scamlens.training_augmentation import prepare_training_augmentation  # noqa: E402


def _display_path(path: Path) -> str:
    try:
        return display_path(path)
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--incident-dir",
        type=resolved_path,
        default=PROJECT_ROOT / "data/raw/kr_mob_smishing_v2/incidents",
    )
    parser.add_argument(
        "--base-split",
        type=resolved_path,
        default=PROJECT_ROOT / "data/processed/messages_split.csv",
    )
    parser.add_argument(
        "--output",
        type=resolved_path,
        default=PROJECT_ROOT / "data/processed/kr_mob_smishing_v2_messages.csv",
    )
    parser.add_argument(
        "--augmented-output",
        type=resolved_path,
        default=PROJECT_ROOT / "data/processed/messages_split_augmented.csv",
    )
    parser.add_argument("--heldout-similarity-threshold", type=float, default=0.90)
    parser.add_argument(
        "--summary-output",
        type=resolved_path,
        default=PROJECT_ROOT / "reports/generated/training_augmentation_summary.json",
    )
    args = parser.parse_args()

    result = prepare_training_augmentation(
        args.incident_dir,
        args.base_split,
        args.output,
        args.augmented_output,
        heldout_similarity_threshold=args.heldout_similarity_threshold,
    )
    result["auxiliary_output"] = _display_path(args.output)
    result["augmented_output"] = _display_path(args.augmented_output)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
