#!/usr/bin/env python3
"""Run and verify frozen local evaluation of KISA external smishing candidates (E2).

Scope:
- Offline local evaluation using frozen DUP models and thresholds.
- Verifies freeze manifest hashes before and after inference; fails closed.
- Replays fixed old controls (16 rows) per seed to ensure bit-for-bit inference consistency.
- Evaluates 22 unique primary_model_input (retained from E1).
- Primary analysis: 18 group representatives with Wilson 95% score intervals.
- Secondary analysis: 22 unique inputs with Wilson 95% score intervals.
- Saves run receipt, replay verification, private predictions CSV, and all-misses markdown.
- Generates public aggregate reports/generated/external_kisa_evaluation_20260921.json
  and docs/EXTERNAL_KISA_EVALUATION_20260921.md.
- Re-runnable with --check to verify saved artifacts, metrics, and freeze bindings without side-effects.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scamlens.preprocessing import (  # noqa: E402
    defang_url,
    extract_urls,
    mask_person_names,
    mask_sensitive_text,
)

EVAL_VERSION = "20260921_v1"
SEEDS = [42, 101, 202, 303, 404]
PRIMARY_SEED = 42

PRIVATE_BASE = Path.home() / "scamlens_private" / f"external_eval_{EVAL_VERSION}"
FREEZE_MANIFEST_PATH = PRIVATE_BASE / "freeze_manifest.json"
PACKET_JSON_PATH = PRIVATE_BASE / "evaluation_packet.json"
PACKET_CSV_PATH = PRIVATE_BASE / "evaluation_packet.csv"
SOURCE_U5_BASE = Path.home() / "scamlens_private" / "local_kcbert_u5_20260918_v1"
THRESHOLD_JSON_PATH = PROJECT_ROOT / "reports" / "generated" / "matched_kcbert_u5_unused_test_20260918_v1.json"

PUBLIC_REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / f"external_kisa_evaluation_20260921.json"
PUBLIC_DOC_PATH = PROJECT_ROOT / "docs" / "EXTERNAL_KISA_EVALUATION_20260921.md"


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def ensure_private_file(path: Path) -> None:
    if path.exists():
        os.chmod(path, 0o600)


def wilson_score_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    z = 1.959963984540054  # 95% confidence z-score
    p_hat = k / n
    denom = 1 + (z ** 2) / n
    center = (p_hat + (z ** 2) / (2 * n)) / denom
    margin = (z / denom) * math.sqrt((p_hat * (1 - p_hat) / n) + ((z ** 2) / (4 * (n ** 2))))
    lower = max(0.0, float(center - margin))
    upper = min(1.0, float(center + margin))
    return round(lower, 4), round(upper, 4)


def verify_freeze_manifest() -> bool:
    if not FREEZE_MANIFEST_PATH.exists():
        print(f"[FAIL] Missing freeze manifest: {FREEZE_MANIFEST_PATH}")
        return False
    with open(FREEZE_MANIFEST_PATH, encoding="utf-8") as f:
        freeze_data = json.load(f)

    for path_str, exp_sha in freeze_data["files"].items():
        f_path = Path(path_str)
        if not f_path.exists():
            print(f"[FAIL] Frozen file missing on disk: {f_path}")
            return False
        act_sha = sha256_file(f_path)
        if act_sha != exp_sha:
            print(f"[FAIL] Frozen file modified: {f_path} ({act_sha} != {exp_sha})")
            return False
    return True


def load_thresholds() -> dict[int, float]:
    with open(THRESHOLD_JSON_PATH, encoding="utf-8") as f:
        canon = json.load(f)
    return {r["seed"]: float(r["threshold"]) for r in canon["arm_statistics"]["DUP"]["seeds"]}


def load_control_rows() -> pd.DataFrame:
    df_ue = pd.read_csv(SOURCE_U5_BASE / "unused_eval.csv")
    df_test = df_ue[df_ue["split"] == "test"]
    normals = df_test[df_test["label"] == "normal"].sort_values("message_id").head(8)
    smishings = df_test[df_test["label"] == "smishing"].sort_values("message_id").head(8)
    controls = pd.concat([normals, smishings], ignore_index=True)
    if len(controls) != 16:
        raise ValueError(f"Expected 16 control rows, found {len(controls)}")
    return controls


def run_control_replay(
    seed: int,
    model: Any,
    tokenizer: Any,
    device: str,
    threshold: float,
    controls: pd.DataFrame,
) -> dict[str, Any]:
    import torch

    enc = tokenizer(
        controls["text_model_base"].tolist(),
        truncation=True,
        padding="max_length",
        max_length=128,
        return_tensors="pt",
    )
    with torch.no_grad():
        logits = model(**{k: v.to(device) for k, v in enc.items()}).logits
        probs = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()

    df_saved = pd.read_csv(SOURCE_U5_BASE / f"results/seed_{seed}/DUP/unused_test.csv")
    saved_map = dict(zip(df_saved["message_id"], df_saved["probability"]))

    diffs = []
    mismatches = 0
    records = []
    for idx, row in controls.iterrows():
        m_id = row["message_id"]
        saved_p = float(saved_map[m_id])
        rec_p = float(probs[idx])
        diff = abs(rec_p - saved_p)
        diffs.append(diff)
        rec_dec = bool(rec_p >= threshold)
        saved_dec = bool(saved_p >= threshold)
        if rec_dec != saved_dec:
            mismatches += 1
        records.append({
            "message_id": m_id,
            "label": row["label"],
            "saved_probability": saved_p,
            "recomputed_probability": rec_p,
            "abs_diff": diff,
            "decision_match": (rec_dec == saved_dec),
        })

    max_diff = max(diffs)
    passed = (max_diff <= 1e-5) and (mismatches == 0)
    return {
        "seed": seed,
        "threshold": threshold,
        "max_abs_diff": max_diff,
        "decision_mismatches": mismatches,
        "status": "passed" if passed else "failed",
        "controls": records,
    }


def cohort_fss_map(candidates: list[dict[str, Any]]) -> dict[str, bool]:
    """Map template sha to candidate has_fss_prefix (all candidates retained)."""
    mapping: dict[str, bool] = {}
    for c in candidates:
        if c.get("screening_status") != "retained_new_candidate":
            raise ValueError("unretained candidate in frozen packet")
        mapping[c["primary_model_input_sha256"]] = bool(c.get("has_fss_prefix"))
    return mapping


def summarize_seeds(
    templates: list[dict[str, Any]],
    rep_indices: list[int],
    probs_by_seed: dict[int, list[float]],
    thresholds: dict[int, float],
) -> dict[str, Any]:
    """Single summarizer for run and --check: seed metrics from unique probs."""
    total_reps = len(rep_indices)
    total_uniques = len(templates)
    out: dict[str, Any] = {}
    for seed in SEEDS:
        probs = probs_by_seed[seed]
        th = thresholds[seed]
        rep_probs = [probs[i] for i in rep_indices]
        rep_tp = sum(1 for p in rep_probs if p >= th)
        all_tp = sum(1 for p in probs if p >= th)
        out[str(seed)] = {
            "seed": seed,
            "threshold": th,
            "group_representatives": {
                "n": total_reps,
                "tp": rep_tp,
                "fn": total_reps - rep_tp,
                "recall": rep_tp / total_reps if total_reps else 0.0,
                "wilson_95_ci": wilson_score_interval(rep_tp, total_reps),
            },
            "unique_inputs": {
                "n": total_uniques,
                "tp": all_tp,
                "fn": total_uniques - all_tp,
                "recall": all_tp / total_uniques if total_uniques else 0.0,
                "wilson_95_ci": wilson_score_interval(all_tp, total_uniques),
            },
        }
    return out


def generate_all_misses_markdown(
    misses_by_seed: dict[int, list[dict[str, Any]]],
    thresholds: dict[int, float],
    total_reps: int,
    total_uniques: int,
) -> str:
    lines = [
        "# KISA 신규 평가 미탐(Miss, False Negative) 상세 검수서",
        "",
        "- **평가 조건**: 고정 DUP 모델 5개 시드 (Seed 42 주 분석, 101/202/303/404 민감도 분석)",
        "- **원 라벨**: KISA 제공 스미싱 양성 (따라서 모델 미탐은 False Negative에 해당)",
        "- **보안 준수**: 모든 본문은 인명 마스킹 및 URL Defanged 처리되었으며 라이브 링크는 포함되지 않습니다.",
        "- **프라이버시**: 민감 정보 마스킹이 적용되었으나 잔여 식별 정보 가능성이 있으므로 비공개(0600)로 보관합니다.",
        "",
        "---",
        "",
        "## 1. 시드별 미탐 요약",
        "",
        "| 시드 | 임계값 | 그룹 대표 미탐 수 | 고유 본문 미탐 수 | 주요 미탐 원인/유형 |",
        "| :---: | :---: | :---: | :---: | :--- |",
    ]

    for seed in SEEDS:
        th = thresholds[seed]
        m_list = misses_by_seed[seed]
        rep_misses = sum(1 for m in m_list if m["is_group_representative"])
        unique_misses = len(m_list)
        lines.append(f"| Seed {seed} | {th:.4f} | {rep_misses} / {total_reps} | {unique_misses} / {total_uniques} | 개별 카드 참조(원인 단정 없음) |")

    lines.extend([
        "",
        "---",
        "",
        "## 2. Seed 42 (Primary) 미탐 본문 상세 카드",
        "",
    ])

    seed_42_misses = misses_by_seed[PRIMARY_SEED]
    for idx, m in enumerate(seed_42_misses):
        gid = m["group_id"]
        in_sha = m["primary_model_input_sha256"]
        lines.append(f"### [Miss {idx + 1:02d}] {gid} (`{in_sha[:16]}...`)")
        lines.append(f"- **그룹 대표 여부**: {'대표 (Representative)' if m['is_group_representative'] else '변형 템플릿'}")
        lines.append(f"- **모델 부여 확률**: `{m['probability']}` (임계값: `{thresholds[PRIMARY_SEED]}`)")
        lines.append(f"- **토큰 수**: {m['token_length']} (절단 여부: {m['is_truncated']})")
        lines.append("")
        lines.append("```text")
        lines.append("[검수 렌더링 본문 (Defanged & Name-Masked)]")
        lines.append(m["review_text"])
        lines.append("```")
        lines.append("")
        lines.append("```text")
        lines.append("[실제 모델 입력 (primary_model_input)]")
        lines.append(m["primary_model_input"])
        lines.append("```")
        lines.append("")
        lines.append("> **분석 메모**: 화면 캡처 OCR 잔재(시간·통신사 표기 등)가 함께 관찰되나, "
                     "원인으로 단정하지 않는다. 절단 여부와의 동시 발생도 인과 증거가 아니다.")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _cohort_breakdown(
    templates: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    seed_predictions: dict[int, list[float]],
    thresholds: dict[int, float],
) -> dict[str, Any]:
    """FSS-prefix cohort counts derived from frozen flags and seed-42 scores."""
    fss_map = cohort_fss_map(candidates)
    th = thresholds[PRIMARY_SEED]
    probs = seed_predictions[PRIMARY_SEED]
    out: dict[str, Any] = {}
    for flag, name in ((True, "fss_prefixed"), (False, "general")):
        idx = [i for i, t in enumerate(templates)
               if fss_map[t["primary_model_input_sha256"]] == flag]
        ridx = [i for i in idx if templates[i]["is_group_representative"]]
        tp_u = sum(1 for i in idx if probs[i] >= th)
        tp_r = sum(1 for i in ridx if probs[i] >= th)
        out[name] = {
            "unique_inputs": len(idx),
            "unique_tp": tp_u,
            "unique_fn": len(idx) - tp_u,
            "unique_recall": tp_u / len(idx) if idx else 0.0,
            "group_representatives": len(ridx),
            "rep_tp": tp_r,
            "rep_fn": len(ridx) - tp_r,
            "rep_recall": tp_r / len(ridx) if ridx else 0.0,
        }
    return out


def generate_public_evaluation_doc(
    eval_summary: dict[str, Any],
    thresholds: dict[int, float],
) -> str:
    s42_rep = eval_summary["by_seed"]["42"]["group_representatives"]
    s42_all = eval_summary["by_seed"]["42"]["unique_inputs"]
    cohorts = eval_summary["cohorts"]
    packet = json.loads(PACKET_JSON_PATH.read_text())
    dates = sorted({c["datetime"].split()[0] for c in packet["candidates"]})

    lines = [
        "# KISA 외부 스미싱 자료 고정 모델 평가 결과",
        "",
        "## 1. 평가 개요 및 사전 고정 조건",
        "",
        "- **평가 일시**: 2026-09-21 (Orca run `run_038c277363b4`)",
        f"- **평가 후보의 제공 날짜**: {dates[0]} ~ {dates[-1]}. 중복 검사 전 원본 전체의 최신 날짜와 구분하며 실제 수신·발생 시각은 미확인입니다.",
        "- **평가 대상 모델**: 사전 고정된 DUP 5개 시드 (`seed_42` 주 모델, `seed_101`, `seed_202`, `seed_303`, `seed_404` 민감도 확인)",
        "- **임계값 정본**: `matched_kcbert_u5_unused_test_20260918_v1.json`의 불변 임계값을 변경 없이 적용",
        "- **사전 고정 게이트**: 모델 가중치 및 입력 파일 SHA-256 해시를 추론 전 `freeze_manifest.json`으로 고정하고, 기존 고정 대조군 16건 재현 일치율(오차 1e-5 이하, 판정 불일치 0건)을 확인한 후 신규 추론을 수행함",
        "- **전처리 원칙**: 수집 메타데이터 `[FSS]` 접두어는 첫 번째 `추출문자:` 구분자 뒤의 본문(`sms_body`)을 추출하여 분리하였으며, OCR 잔재는 원천 특성으로서 변형 없이 보존함",
        "",
        "---",
        "",
        "## 2. 주 분석 결과: 18개 그룹 대표별 탐지율 (Primary Analysis)",
        "",
        "> **분석 기준**: 0.90 유사도 연결요소로 묶인 18개 그룹의 결정론적 대표 본문(`min SHA256`) 대상 탐지 성능.",
        "",
        "| 모델 (시드) | 적용 임계값 | 탐지 수 (TP) | 미탐 수 (FN) | 탐지율 (Recall) | Wilson 95% 신뢰구간 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    for seed in SEEDS:
        res = eval_summary["by_seed"][str(seed)]["group_representatives"]
        th = thresholds[seed]
        ci_str = f"[{res['wilson_95_ci'][0]:.4f}, {res['wilson_95_ci'][1]:.4f}]"
        seed_label = f"DUP seed {seed} (Primary)" if seed == PRIMARY_SEED else f"DUP seed {seed}"
        lines.append(f"| **{seed_label}** | `{th:.4f}` | {res['tp']} | {res['fn']} | **{res['recall']:.4f}** ({res['tp']}/{res['n']}) | {ci_str} |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. 보조 분석 결과: 22개 고유 본문별 탐지율 (Secondary Analysis)",
        "",
        "> **분석 기준**: FSS 접두어 제거 후 도출된 22개 고유 본문 모델 입력 전체 대상 탐지 성능.",
        "",
        "| 모델 (시드) | 적용 임계값 | 탐지 수 (TP) | 미탐 수 (FN) | 탐지율 (Recall) | Wilson 95% 신뢰구간 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ])

    for seed in SEEDS:
        res = eval_summary["by_seed"][str(seed)]["unique_inputs"]
        th = thresholds[seed]
        ci_str = f"[{res['wilson_95_ci'][0]:.4f}, {res['wilson_95_ci'][1]:.4f}]"
        seed_label = f"DUP seed {seed} (Primary)" if seed == PRIMARY_SEED else f"DUP seed {seed}"
        lines.append(f"| **{seed_label}** | `{th:.4f}` | {res['tp']} | {res['fn']} | **{res['recall']:.4f}** ({res['tp']}/{res['n']}) | {ci_str} |")

    fss = cohorts["fss_prefixed"]
    gen = cohorts["general"]
    lines.extend([
        "",
        "---",
        "",
        "## 4. FSS 접두어 코호트별 집계 ( Seed 42 실측 )",
        "",
        f"- **FSS 접두어 있음**: 고유 본문 {fss['unique_tp']}/{fss['unique_inputs']} 탐지, "
        f"그룹 대표 {fss['rep_tp']}/{fss['group_representatives']} 탐지.",
        f"- **FSS 접두어 없음(일반)**: 고유 본문 {gen['unique_tp']}/{gen['unique_inputs']} 탐지, "
        f"그룹 대표 {gen['rep_tp']}/{gen['group_representatives']} 탐지.",
        "- 코호트 구분은 동결된 `has_fss_prefix` 플래그에서만 도출하며, OCR 잔재·절단과의 "
        "동시 발생은 원인 증거가 아니다.",
        "",
        "---",
        "",
        "## 5. 방법론적 경계 및 한계 고지",
        "",
        "1. **양성 편의 표본 한계**: 본 자료는 KISA C-TAS 위협정보 포털에서 수령된 양성 신고 자료만으로 구성되어 있어, **오탐률(FPR), 정밀도(Precision), 실서비스 종합 정확도를 산출할 수 없습니다**.",
        "2. **사건 확정 여부**: 본문의 사칭 유형 분류는 AI 본문 검수 결과일 뿐 실제 금융 사기 사건의 발생이나 URL 목적지 조사를 거쳐 확정된 라벨이 아닙니다.",
        "3. **표본 비독립성**: 유사한 본문이 포함되어 있으며 실제 캠페인 동일성은 확인하지 않았습니다. 유사도 그룹도 완전한 통계적 독립성을 보장하지 않습니다. Wilson 구간은 편의 표본 편향이나 잔여 그룹 의존성을 보정하지 않습니다.",
        "4. **비전향적 시점 한계**: 제공된 날짜 필드는 수령 CSV 상의 기록일 뿐 실제 문자 발신 시각이나 향후 발생할 공격에 대한 전향적 탐지율로 해석될 수 없습니다.",
        "",
    ])

    return "\n".join(lines)


def run_evaluation() -> dict[str, Any]:
    print(f"=== [E2] Commencing frozen local evaluation ({EVAL_VERSION}) ===")
    # Refuse before imports, inference, or any receipt mutation.
    if (PRIVATE_BASE / "predictions_kisa_20260921.csv").exists() or (PRIVATE_BASE / "run_receipt.json").exists():
        raise RuntimeError("Saved inference exists; use --check. Existing scores and receipts are immutable.")

    # 1. Pre-inference freeze verification
    print("[1/5] Verifying pre-inference freeze manifest hashes...")
    if not verify_freeze_manifest():
        raise RuntimeError("Pre-inference freeze manifest verification failed! Stopping immediately.")

    # 2. Environment and device setup
    import torch
    import transformers
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    transformers.logging.set_verbosity_error()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch.set_num_threads(4)

    run_start_utc = datetime.now(timezone.utc).isoformat()
    script_path = PROJECT_ROOT / "scripts" / "evaluate_external_kisa_20260921.py"
    run_receipt = {
        "evaluation_version": EVAL_VERSION,
        "run_start_utc": run_start_utc,
        "script_path": str(script_path),
        "script_sha256": sha256_file(script_path),
        "device": device,
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "mps_available": torch.backends.mps.is_available(),
        "freeze_manifest_verified_at_start": True,
        "prior_scratch_accepted": False,
    }
    ensure_private_dir(PRIVATE_BASE)
    start_receipt_path = PRIVATE_BASE / "run_receipt_start.json"
    with open(start_receipt_path, "w", encoding="utf-8") as f:
        json.dump(run_receipt, f, indent=2)
    ensure_private_file(start_receipt_path)

    # 3. Load inputs and thresholds
    print("[2/5] Loading evaluation packet and canonical thresholds...")
    with open(PACKET_JSON_PATH, encoding="utf-8") as f:
        packet = json.load(f)
    candidates = packet["candidates"]
    templates = packet["templates"]
    groups = packet["groups"]

    thresholds = load_thresholds()
    controls = load_control_rows()

    unique_inputs = [t["primary_model_input"] for t in templates]
    template_sha_map = {t["primary_model_input_sha256"]: t for t in templates}

    # 4. Infer per seed
    print("[3/5] Running control replay and candidate inference across 5 seeds...")
    control_replays = {}
    seed_predictions: dict[int, list[float]] = {}
    misses_by_seed: dict[int, list[dict[str, Any]]] = {}

    tokenizer = AutoTokenizer.from_pretrained(
        str(SOURCE_U5_BASE / f"results/seed_{PRIMARY_SEED}/DUP/model"), local_files_only=True
    )
    enc = tokenizer(unique_inputs, truncation=True, padding="max_length", max_length=128, return_tensors="pt")

    # Compute token lengths and truncation metadata
    token_lengths = [
        len(tokenizer(inp, add_special_tokens=True, truncation=False)["input_ids"]) for inp in unique_inputs
    ]
    is_truncated = [length > 128 for length in token_lengths]

    for seed in SEEDS:
        model_dir = SOURCE_U5_BASE / f"results/seed_{seed}/DUP/model"
        th = thresholds[seed]
        model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True).to(device).eval()

        # Replay controls check
        replay_res = run_control_replay(seed, model, tokenizer, device, th, controls)
        if replay_res["status"] != "passed":
            raise RuntimeError(
                f"Seed {seed} control replay failed! drift={replay_res['max_abs_diff']}, mismatches={replay_res['decision_mismatches']}"
            )
        control_replays[seed] = replay_res

        # Infer unique candidates
        with torch.no_grad():
            logits = model(**{k: v.to(device) for k, v in enc.items()}).logits
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()

        seed_predictions[seed] = probs

        # Collect misses
        misses = []
        for i, t in enumerate(templates):
            prob = probs[i]
            pred = int(prob >= th)
            if pred == 0:  # False negative (Miss)
                misses.append({
                    "primary_model_input_sha256": t["primary_model_input_sha256"],
                    "primary_model_input": t["primary_model_input"],
                    "review_text": next(c["review_text"] for c in candidates if c["primary_model_input_sha256"] == t["primary_model_input_sha256"]),
                    "group_id": t["group_id"],
                    "is_group_representative": t["is_group_representative"],
                    "probability": prob,
                    "threshold": th,
                    "token_length": token_lengths[i],
                    "is_truncated": is_truncated[i],
                })
        misses_by_seed[seed] = misses

        del model
        gc.collect()
        if device == "mps":
            torch.mps.empty_cache()

    # 5. Compute metric summaries
    print("[4/5] Aggregating primary (18 groups) and secondary (22 unique inputs) metrics...")
    rep_indices = [i for i, t in enumerate(templates) if t["is_group_representative"]]
    total_reps = len(rep_indices)
    total_uniques = len(unique_inputs)

    by_seed_metrics = summarize_seeds(templates, rep_indices, seed_predictions, thresholds)

    eval_summary = {
        "evaluation_version": EVAL_VERSION,
        "status": "frozen_local_evaluation_completed",
        "primary_seed": PRIMARY_SEED,
        "sensitivity_seeds": [s for s in SEEDS if s != PRIMARY_SEED],
        "denominators": {
            "group_representatives_primary": total_reps,
            "unique_inputs_secondary": total_uniques,
            "candidate_rows_source": len(candidates),
        },
        "by_seed": by_seed_metrics,
        "cohorts": _cohort_breakdown(templates, candidates, seed_predictions, thresholds),
    }

    # 6. Save private artifacts
    print("[5/5] Saving private and public evaluation artifacts...")
    receipt_path = PRIVATE_BASE / "run_receipt.json"
    if receipt_path.exists():
        try:
            prior = json.load(open(receipt_path, encoding="utf-8"))
        except (OSError, ValueError):
            prior = {}
        if prior.get("status") == "completed_inference" and PUBLIC_REPORT_PATH.exists() \
                and PUBLIC_DOC_PATH.exists():
            raise RuntimeError("Completed inference exists; refusing accidental overwrite.")
    ensure_private_dir(PRIVATE_BASE)

    # Predictions CSV
    pred_csv_path = PRIVATE_BASE / "predictions_kisa_20260921.csv"
    csv_rows = []
    for c_idx, c in enumerate(candidates):
        in_sha = c["primary_model_input_sha256"]
        u_idx = unique_inputs.index(c["primary_model_input"])
        row = {
            "eval_row_id": f"eval_kisa_20260921_{c_idx:03d}",
            "audit_index": c["audit_index"],
            "source_csv": c["source_csv"],
            "batch_row_index": c["batch_row_index"],
            "primary_model_input_sha256": in_sha,
            "group_id": c["group_id"],
            "is_group_representative": int(c["is_group_representative"]),
            "token_length": token_lengths[u_idx],
            "is_truncated": int(is_truncated[u_idx]),
        }
        for s in SEEDS:
            p_val = seed_predictions[s][u_idx]
            row[f"prob_seed_{s}"] = float(p_val)
            row[f"pred_seed_{s}"] = int(p_val >= thresholds[s])
        csv_rows.append(row)
    df_preds = pd.DataFrame(csv_rows)
    df_preds.to_csv(pred_csv_path, index=False, encoding="utf-8", float_format="%.17g")
    ensure_private_file(pred_csv_path)

    # Replay results JSON
    replay_path = PRIVATE_BASE / "replay_controls_results.json"
    with open(replay_path, "w", encoding="utf-8") as f:
        json.dump(control_replays, f, indent=2)
    ensure_private_file(replay_path)

    # Private summary JSON
    summary_path = PRIVATE_BASE / "evaluation_summary_private.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(eval_summary, f, indent=2, ensure_ascii=False)
    ensure_private_file(summary_path)

    # All misses markdown
    misses_md_path = PRIVATE_BASE / "all_misses_masked.md"
    misses_content = generate_all_misses_markdown(misses_by_seed, thresholds, total_reps, total_uniques)
    with open(misses_md_path, "w", encoding="utf-8") as f:
        f.write(misses_content)
    ensure_private_file(misses_md_path)

    # Run receipt JSON
    run_receipt["run_end_utc"] = datetime.now(timezone.utc).isoformat()
    if not verify_freeze_manifest():
        raise RuntimeError("Post-inference freeze manifest verification failed! Stopping immediately.")
    run_receipt["freeze_manifest_verified_at_finish"] = True
    run_receipt["status"] = "completed_inference"
    run_receipt["artifacts"] = {
        "predictions_csv_sha256": sha256_file(pred_csv_path),
        "replay_controls_sha256": sha256_file(replay_path),
        "summary_private_sha256": sha256_file(summary_path),
        "all_misses_md_sha256": sha256_file(misses_md_path),
    }
    receipt_path = PRIVATE_BASE / "run_receipt.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(run_receipt, f, indent=2)
    ensure_private_file(receipt_path)

    # Public aggregate report JSON
    public_report_data = {
        "status": "frozen_local_evaluation_completed",
        "evaluation_version": EVAL_VERSION,
        "scope": "kisa_smishing_screened_new_candidates",
        "primary_seed": PRIMARY_SEED,
        "sensitivity_seeds": [s for s in SEEDS if s != PRIMARY_SEED],
        "denominators": eval_summary["denominators"],
        "results_by_seed": by_seed_metrics,
        "cohort_breakdown": eval_summary["cohorts"],
        "control_replay": {
            "controls_count": 16,
            "all_seeds_passed": all(r["status"] == "passed" for r in control_replays.values()),
            "max_replay_drift": max(r["max_abs_diff"] for r in control_replays.values()),
            "decision_mismatches": sum(r["decision_mismatches"] for r in control_replays.values()),
        },
        "artifact_bindings": {
            "predictions_csv_sha256": sha256_file(pred_csv_path),
            "summary_private_sha256": sha256_file(summary_path),
            "all_misses_md_sha256": sha256_file(misses_md_path),
            "run_receipt_sha256": sha256_file(receipt_path),
            "freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST_PATH),
        },
    }
    PUBLIC_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PUBLIC_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(public_report_data, f, indent=2, ensure_ascii=False)

    # Public documentation markdown
    public_doc_content = generate_public_evaluation_doc(eval_summary, thresholds)
    PUBLIC_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PUBLIC_DOC_PATH, "w", encoding="utf-8") as f:
        f.write(public_doc_content)

    print("[OK] Evaluation completed successfully.")
    return {
        "status": "success",
        "primary_recall_group_reps": by_seed_metrics[str(PRIMARY_SEED)]["group_representatives"]["recall"],
        "secondary_recall_unique_inputs": by_seed_metrics[str(PRIMARY_SEED)]["unique_inputs"]["recall"],
        "public_report": str(PUBLIC_REPORT_PATH),
        "public_doc": str(PUBLIC_DOC_PATH),
    }


def verify_evaluation() -> bool:
    print(f"=== [VERIFY] Commencing E2 evaluation verification check ({EVAL_VERSION}) ===")

    # 1. Freeze manifest verification
    if not verify_freeze_manifest():
        print("[FAIL] Freeze manifest verification failed!")
        return False

    # 2. Check private artifacts and permissions
    required_private_files = [
        "predictions_kisa_20260921.csv",
        "replay_controls_results.json",
        "evaluation_summary_private.json",
        "all_misses_masked.md",
        "run_receipt.json",
    ]
    for fname in required_private_files:
        fpath = PRIVATE_BASE / fname
        if not fpath.exists():
            print(f"[FAIL] Missing private artifact: {fpath}")
            return False
        mode = fpath.stat().st_mode & 0o777
        if mode != 0o600:
            print(f"[FAIL] Artifact {fname} permission is {oct(mode)}, expected 0600")
            return False

    # 3. Check public files
    if not PUBLIC_REPORT_PATH.exists():
        print(f"[FAIL] Missing public report: {PUBLIC_REPORT_PATH}")
        return False
    if not PUBLIC_DOC_PATH.exists():
        print(f"[FAIL] Missing public doc: {PUBLIC_DOC_PATH}")
        return False

    with open(PUBLIC_REPORT_PATH, encoding="utf-8") as f:
        pub = json.load(f)

    # Check for leaks in public report
    pub_str = json.dumps(pub)
    for forbidden in ["/Users/", "sangwoolee", "http://", "https://", "smsMsg", "smsHash"]:
        if forbidden in pub_str:
            print(f"[FAIL] Sensitive string or path '{forbidden}' exposed in public report!")
            return False

    # Recompute ALL metrics/CIs from saved unique predictions joined to packet
    with open(PACKET_JSON_PATH, encoding="utf-8") as f:
        packet = json.load(f)
    templates = packet["templates"]
    if len(templates) != 22:
        print(f"[FAIL] Frozen template count drift: {len(templates)} != 22")
        return False
    rep_idx = [i for i, t in enumerate(templates) if t["is_group_representative"]]
    if len(rep_idx) != 18:
        print(f"[FAIL] Frozen representative count drift: {len(rep_idx)} != 18")
        return False
    df_preds = pd.read_csv(PRIVATE_BASE / "predictions_kisa_20260921.csv",
                           dtype={f"prob_seed_{s}": str for s in SEEDS})
    if len(df_preds) != 69:
        print(f"[FAIL] Predictions CSV row count mismatch: {len(df_preds)} != 69")
        return False
    sha_to_template = {t["primary_model_input_sha256"]: t for t in templates}
    if set(df_preds["primary_model_input_sha256"].astype(str)) != set(sha_to_template):
        print("[FAIL] Predictions CSV coverage mismatch vs frozen packet")
        return False
    thresholds = load_thresholds()
    for seed in SEEDS:
        col_p, col_d = f"prob_seed_{seed}", f"pred_seed_{seed}"
        texts = df_preds[col_p].astype(str).tolist()
        try:
            probs = [float(x) for x in texts]
        except ValueError:
            print(f"[FAIL] Saved probabilities not numeric for seed {seed}")
            return False
        if any(not math.isfinite(p) or p < 0.0 or p > 1.0 for p in probs):
            print(f"[FAIL] Saved probabilities not finite in [0,1] for seed {seed}")
            return False
        if [int(p >= thresholds[seed]) for p in probs] != df_preds[col_d].astype(int).tolist():
            print(f"[FAIL] Saved decisions do not match threshold for seed {seed}")
            return False
        # Duplicate consistency on raw strings: candidate rows sharing one
        # unique input carry identical probability text.
        per_sha: dict[str, set] = {}
        for _, row in df_preds.iterrows():
            per_sha.setdefault(str(row["primary_model_input_sha256"]), set()).add(
                (str(row[col_p]), int(row[col_d])))
        if any(len(v) != 1 for v in per_sha.values()):
            print(f"[FAIL] Duplicate candidate rows disagree for seed {seed}")
            return False
    probs_by_seed: dict[int, list[float]] = {}
    deduped = df_preds.drop_duplicates(subset=["primary_model_input_sha256"])
    if set(deduped["primary_model_input_sha256"].astype(str)) != {
            t["primary_model_input_sha256"] for t in templates}:
        print("[FAIL] Unique input set drift vs frozen packet")
        return False
    by_row = {str(r["primary_model_input_sha256"]): r for _, r in deduped.iterrows()}
    for s in SEEDS:
        try:
            probs_by_seed[s] = [float(str(by_row[t["primary_model_input_sha256"]][f"prob_seed_{s}"]))
                                for t in templates]
        except ValueError:
            print(f"[FAIL] Saved probabilities not numeric for seed {s}")
            return False
    rep_idx = [i for i, t in enumerate(templates) if t["is_group_representative"]]
    if len(rep_idx) != 18:
        print(f"[FAIL] Frozen representative count drift: {len(rep_idx)} != 18")
        return False
    recomputed = json.loads(json.dumps(
        summarize_seeds(templates, rep_idx, probs_by_seed, thresholds)))
    with open(PRIVATE_BASE / "evaluation_summary_private.json", encoding="utf-8") as f:
        saved_summary = json.load(f)
    if saved_summary.get("by_seed") != recomputed:
        print("[FAIL] Seed metrics differ from single-summarizer recomputation")
        return False
    with open(PUBLIC_REPORT_PATH, encoding="utf-8") as f:
        pub_check = json.load(f)
    for seed in SEEDS:
        if pub_check["results_by_seed"][str(seed)] != recomputed[str(seed)]:
            print(f"[FAIL] Public metrics differ from recomputation for seed {seed}")
            return False
        if pub_check["results_by_seed"][str(seed)]["threshold"] != thresholds[seed]:
            print(f"[FAIL] Threshold drift for seed {seed}")
            return False

    expected_cohorts = _cohort_breakdown(templates, packet["candidates"], probs_by_seed, thresholds)
    if saved_summary.get("cohorts") != expected_cohorts or pub_check.get("cohort_breakdown") != expected_cohorts:
        print("[FAIL] Cohort metrics differ from frozen-input recomputation")
        return False

    # Saved replay records validated without new inference: every control
    # row must show a tight recomputation drift and a matching decision.
    with open(PRIVATE_BASE / "replay_controls_results.json", encoding="utf-8") as f:
        saved_replay = json.load(f)
    for seed in SEEDS:
        entry = saved_replay[str(seed)]
        if entry.get("status") != "passed":
            print(f"[FAIL] Saved replay not passed for seed {seed}")
            return False
        if abs(float(entry.get("threshold", -1)) - thresholds[seed]) > 0:
            print(f"[FAIL] Saved replay threshold drift for seed {seed}")
            return False
        records = entry.get("controls", [])
        if len(records) != 16:
            print(f"[FAIL] Saved replay control count drift for seed {seed}")
            return False
        for rec in records:
            if abs(float(rec["recomputed_probability"]) - float(rec["saved_probability"])) > 1e-5:
                print(f"[FAIL] Saved replay drift exceeds 1e-5 for seed {seed}")
                return False
            if not rec.get("decision_match"):
                print(f"[FAIL] Saved replay decision mismatch for seed {seed}")
                return False

    # Regenerated markdowns must match saved files (tokenizer only, no inference)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        str(SOURCE_U5_BASE / f"results/seed_{PRIMARY_SEED}/DUP/model"), local_files_only=True)
    with open(PRIVATE_BASE / "evaluation_summary_private.json", encoding="utf-8") as f:
        saved_summary = json.load(f)
    by_seed = saved_summary.get("by_seed", {})
    review_by_sha = {}
    for c in packet["candidates"]:
        review_by_sha[c["primary_model_input_sha256"]] = c["review_text"]
    template_by_sha = {t["primary_model_input_sha256"]: t for t in templates}
    misses_full: dict[int, list] = {s: [] for s in SEEDS}
    deduped = df_preds.drop_duplicates(subset=["primary_model_input_sha256"])
    by_sha = {str(r["primary_model_input_sha256"]): r for _, r in deduped.iterrows()}
    for t in templates:
        sha = t["primary_model_input_sha256"]
        row = by_sha[sha]
        inp = t["primary_model_input"]
        tlen = len(tokenizer(inp, add_special_tokens=True, truncation=False)["input_ids"])
        for s in SEEDS:
            if int(row[f"pred_seed_{s}"]) == 0:
                misses_full[s].append({
                    "primary_model_input_sha256": sha,
                    "primary_model_input": inp,
                    "review_text": review_by_sha[sha],
                    "group_id": t["group_id"],
                    "is_group_representative": bool(t["is_group_representative"]),
                    "probability": float(row[f"prob_seed_{s}"]),
                    "threshold": thresholds[s],
                    "token_length": tlen,
                    "is_truncated": tlen > 128,
                })
    regen_misses = generate_all_misses_markdown(misses_full, thresholds, 18, 22)
    if (PRIVATE_BASE / "all_misses_masked.md").read_text(encoding="utf-8") != regen_misses:
        print("[FAIL] Misses markdown differs from regeneration")
        return False
    regen_doc = generate_public_evaluation_doc(
        {"by_seed": by_seed, "cohorts": saved_summary.get("cohorts", {})}, thresholds)
    if PUBLIC_DOC_PATH.read_text(encoding="utf-8") != regen_doc:
        print("[FAIL] Public doc differs from regeneration")
        return False

    # 5. Check bindings in public report
    receipt_p = PRIVATE_BASE / "run_receipt.json"
    pred_csv_p = PRIVATE_BASE / "predictions_kisa_20260921.csv"
    if pub["artifact_bindings"]["run_receipt_sha256"] != sha256_file(receipt_p):
        print("[FAIL] Public report run_receipt_sha256 mismatch")
        return False
    if pub["artifact_bindings"]["predictions_csv_sha256"] != sha256_file(pred_csv_p):
        print("[FAIL] Public report predictions_csv_sha256 mismatch")
        return False

    expected_files = {
        "summary_private_sha256": "evaluation_summary_private.json",
        "all_misses_md_sha256": "all_misses_masked.md",
        "freeze_manifest_sha256": "freeze_manifest.json",
    }
    if any(pub["artifact_bindings"].get(key) != sha256_file(PRIVATE_BASE / name)
           for key, name in expected_files.items()):
        print("[FAIL] Public binding mismatch for summary/misses/frozen inputs")
        return False
    receipt = json.loads(receipt_p.read_text())
    replay_hash = sha256_file(PRIVATE_BASE / "replay_controls_results.json")
    if receipt["artifacts"].get("replay_controls_sha256") != replay_hash:
        print("[FAIL] Replay output differs from execution receipt")
        return False
    print("[OK] All E2 evaluation verification checks and cryptographic bindings passed successfully.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate KISA external smishing candidates.")
    parser.add_argument("--check", action="store_true", help="Perform read-only verification without re-running inference.")
    args = parser.parse_args()

    if args.check:
        success = verify_evaluation()
        sys.exit(0 if success else 1)

    result = run_evaluation()
    print(f"[E2 RESULT] {result}")

    success = verify_evaluation()
    if not success:
        print("[ERROR] Verification failed after run!")
        sys.exit(1)


if __name__ == "__main__":
    main()
