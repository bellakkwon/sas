#!/usr/bin/env python3
"""KISA OCR Diagnostics & Normal Candidate Regression Pipeline (20260921_v1).

Scope & Boundaries:
- Offline diagnostic post-hoc intervention audit on frozen models and inputs.
- Evaluates 7 fixed conditions across 5 seeds:
    1. original128: Baseline truncation, max_length=128
    2. ocr_delete128: Screen UI/OCR artifact character deletion, max_length=128
    3. cap300: Full text up to 300 tokens (model max_position_embeddings=300)
    4. ocr_delete300: OCR deletion + 300 tokens
    5. ocr_unk128: Positional UNK masking overlapping OCR spans, max_length=128
    6. ocr_unk300: Positional UNK masking overlapping OCR spans, max_length=300
    7. head_tail128: 63 head + 63 tail tokens with CLS/SEP for >126 tokens; short inputs identical
- Evaluates 3 cohorts separately:
    - kisa_unique (22 unique primary_model_inputs)
    - kisa_representatives (18 group representatives, aggregated from unique predictions)
    - normal_candidates (250 reviewed normal messages)
- Candidate criterion: head_tail128 ONLY; requires per EACH of the 5 seeds:
    (a) recovers >= 1 KISA False Negative on kisa_unique,
    (b) 0 new KISA False Negatives on kisa_unique,
    (c) 0 new False Positives on normal_candidates.
    All 5 seeds must individually pass.
- Security & Privacy:
    - All private inputs/spans/scores stored in ~/scamlens_private/kisa_ocr_diagnostics_20260921_v1 (mode 0700/0600).
    - ZERO model inference during Task C1. Run command is strictly gated by main_c1_acceptance.json.
    - Overwrites are strictly forbidden. No --overwrite option.
    - Zero network, zero URL expansion, zero external service calls.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import pandas as pd

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scamlens.preprocessing import mask_sensitive_text, normalize_text  # noqa: E402

VERSION = "20260921_v1"
SEEDS = [42, 101, 202, 303, 404]
PRIMARY_SEED = 42

CONDITIONS = [
    "original128",
    "ocr_delete128",
    "cap300",
    "ocr_delete300",
    "ocr_unk128",
    "ocr_unk300",
    "head_tail128",
]

COHORTS = ["kisa_unique", "kisa_representatives", "normal_candidates"]

PRIVATE_DIR = Path.home() / "scamlens_private" / f"kisa_ocr_diagnostics_{VERSION}"
MANIFEST_PATH = PRIVATE_DIR / "input_manifest.json"
OCR_SPANS_PATH = PRIVATE_DIR / "ocr_spans.json"
KISA_INPUTS_PATH = PRIVATE_DIR / "kisa_inputs.json"
NORMAL_INPUTS_PATH = PRIVATE_DIR / "normal_candidates.json"
PROVENANCE_PATH = PRIVATE_DIR / "provenance_metadata.json"
ACCEPTANCE_PATH = PRIVATE_DIR / "main_c1_acceptance.json"
SNAPSHOT_PLAN_PATH = PRIVATE_DIR / "protocol_frozen.md"
RECEIPT_PATH = PRIVATE_DIR / "run_receipt.json"
PREDICTIONS_CSV_PATH = PRIVATE_DIR / "predictions_diagnostics.csv"

# Source paths
SOURCE_PACKET = Path.home() / "scamlens_private/external_eval_20260921_v1/evaluation_packet.json"
SOURCE_PRED_KISA = Path.home() / "scamlens_private/external_eval_20260921_v1/predictions_kisa_20260921.csv"
SOURCE_NORMAL = Path.home() / "scamlens_private/normal_review_20260921_v1/blind_candidates.json"
SOURCE_PLAN = PROJECT_ROOT / "docs/experiments/KISA_OCR_DIAGNOSTICS_PLAN_20260921.md"
SOURCE_THRESHOLDS = PROJECT_ROOT / "reports/generated/matched_kcbert_u5_unused_test_20260918_v1.json"
SOURCE_PREPROC = PROJECT_ROOT / "src/scamlens/preprocessing.py"
SOURCE_MODEL_DIR = Path.home() / "scamlens_private/local_kcbert_u5_20260918_v1/results"
RUNNER_PATH = Path(__file__).resolve()

# Public output paths
PUBLIC_JSON_REPORT = PROJECT_ROOT / "reports" / "generated" / "kisa_ocr_diagnostics_20260921.json"
PUBLIC_DOC_REPORT = PROJECT_ROOT / "docs" / "KISA_OCR_DIAGNOSTICS_20260921.md"
PUBLIC_CSV_REPORT = PROJECT_ROOT / "reports" / "generated" / "kisa_ocr_diagnostics_20260921.csv"

CSV_HEADER = [
    "cohort",
    "seed",
    "condition",
    "n",
    "tp",
    "tn",
    "fp",
    "fn",
    "baseline_tp",
    "baseline_tn",
    "baseline_fp",
    "baseline_fn",
    "corrected_fp",
    "corrected_fn",
    "new_fp",
    "new_fn",
    "threshold",
    "recall",
    "fpr",
]

EXPECTED_SOURCE_KEYS = {
    "evaluation_packet_json",
    "predictions_kisa_csv",
    "blind_candidates_json",
    "matched_thresholds_json",
    "plan_snapshot",
    "preprocessing_source",
}

EXPECTED_CODE_KEYS = {"runner_py"}

EXPECTED_PREPARED_KEYS = {
    "ocr_spans.json",
    "kisa_inputs.json",
    "normal_candidates.json",
    "provenance_metadata.json",
}

EXPECTED_MODEL_KEYS = set()
for _s in SEEDS:
    EXPECTED_MODEL_KEYS.add(f"model_seed_{_s}_config.json")
    EXPECTED_MODEL_KEYS.add(f"model_seed_{_s}_model.safetensors")
    EXPECTED_MODEL_KEYS.add(f"model_seed_{_s}_tokenizer.json")
    EXPECTED_MODEL_KEYS.add(f"model_seed_{_s}_tokenizer_config.json")
    EXPECTED_MODEL_KEYS.add(f"model_seed_{_s}_unused_test_csv")


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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_private_json(path: Path, data: Any) -> None:
    ensure_private_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def load_thresholds() -> dict[int, float]:
    data = load_json(SOURCE_THRESHOLDS)
    return {r["seed"]: float(r["threshold"]) for r in data["arm_statistics"]["DUP"]["seeds"]}


def build_manifest_dict() -> dict[str, Any]:
    """Generate canonical manifest binding exact fixed keysets for sources, models, code, and prepared files."""
    source_files = {
        "evaluation_packet_json": sha256_file(SOURCE_PACKET),
        "predictions_kisa_csv": sha256_file(SOURCE_PRED_KISA),
        "blind_candidates_json": sha256_file(SOURCE_NORMAL),
        "matched_thresholds_json": sha256_file(SOURCE_THRESHOLDS),
        "plan_snapshot": sha256_file(SNAPSHOT_PLAN_PATH),
        "preprocessing_source": sha256_file(SOURCE_PREPROC),
    }

    model_files = {}
    for seed in SEEDS:
        model_dir = SOURCE_MODEL_DIR / f"seed_{seed}/DUP/model"
        for fname in ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"]:
            fpath = model_dir / fname
            model_files[f"model_seed_{seed}_{fname}"] = sha256_file(fpath)
        unused_test = SOURCE_MODEL_DIR / f"seed_{seed}/DUP/unused_test.csv"
        model_files[f"model_seed_{seed}_unused_test_csv"] = sha256_file(unused_test)

    code_files = {
        "runner_py": sha256_file(RUNNER_PATH),
    }

    prepared_files = {
        "ocr_spans.json": sha256_file(OCR_SPANS_PATH),
        "kisa_inputs.json": sha256_file(KISA_INPUTS_PATH),
        "normal_candidates.json": sha256_file(NORMAL_INPUTS_PATH),
        "provenance_metadata.json": sha256_file(PROVENANCE_PATH),
    }

    return {
        "manifest_version": VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_files": source_files,
        "model_files": model_files,
        "code_files": code_files,
        "prepared_files": prepared_files,
        "counts": {
            "kisa_unique_templates": 22,
            "kisa_group_representatives": 18,
            "kisa_templates_with_spans": 9,
            "kisa_templates_zero_spans": 13,
            "normal_candidates": 250,
            "total_diagnostic_rows": 272,
        },
        "safety_invariants": {
            "zero_inference_in_c1": True,
            "max_position_embeddings_clamped_to_300": True,
            "circular_acceptance_excluded": True,
            "exact_quote_match": True,
            "no_brand_or_url_or_contact_deleted": True,
            "normal_candidates_reproduced_via_pipeline": True,
        },
    }


def verify_manifest(verbose: bool = True) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not MANIFEST_PATH.exists():
        errors.append(f"Manifest missing: {MANIFEST_PATH}")
        return False, errors

    manifest = load_json(MANIFEST_PATH)

    # Validate exact required key sets
    sections_and_expected = [
        ("source_files", EXPECTED_SOURCE_KEYS),
        ("code_files", EXPECTED_CODE_KEYS),
        ("prepared_files", EXPECTED_PREPARED_KEYS),
        ("model_files", EXPECTED_MODEL_KEYS),
    ]

    for sec_name, exp_keys in sections_and_expected:
        if sec_name not in manifest or not isinstance(manifest[sec_name], dict):
            errors.append(f"Manifest missing section: {sec_name}")
            continue
        act_keys = set(manifest[sec_name].keys())
        if act_keys != exp_keys:
            missing = exp_keys - act_keys
            extra = act_keys - exp_keys
            if missing:
                errors.append(f"Section {sec_name} missing expected keys: {sorted(missing)}")
            if extra:
                errors.append(f"Section {sec_name} contains unexpected keys: {sorted(extra)}")

    if errors:
        return False, errors

    # Check source files hashes
    source_map = {
        "evaluation_packet_json": SOURCE_PACKET,
        "predictions_kisa_csv": SOURCE_PRED_KISA,
        "blind_candidates_json": SOURCE_NORMAL,
        "matched_thresholds_json": SOURCE_THRESHOLDS,
        "plan_snapshot": SNAPSHOT_PLAN_PATH,
        "preprocessing_source": SOURCE_PREPROC,
    }
    for name, exp_sha in manifest.get("source_files", {}).items():
        target = source_map.get(name)
        if not target or not target.exists():
            errors.append(f"Source file {name} missing: {target}")
        else:
            act_sha = sha256_file(target)
            if act_sha != exp_sha:
                errors.append(f"Source file {name} modified: expected {exp_sha}, got {act_sha}")

    # Check code files hashes
    for name, exp_sha in manifest.get("code_files", {}).items():
        if name == "runner_py":
            act_sha = sha256_file(RUNNER_PATH)
            if act_sha != exp_sha:
                errors.append(f"Code file runner_py modified: expected {exp_sha}, got {act_sha}")

    # Check model files hashes
    for name, exp_sha in manifest.get("model_files", {}).items():
        parts = name.split("_")
        seed = parts[2]
        rest = "_".join(parts[3:])
        if rest == "unused_test_csv":
            target = SOURCE_MODEL_DIR / f"seed_{seed}/DUP/unused_test.csv"
        else:
            target = SOURCE_MODEL_DIR / f"seed_{seed}/DUP/model/{rest}"
        if not target.exists():
            errors.append(f"Model file {name} missing: {target}")
        else:
            act_sha = sha256_file(target)
            if act_sha != exp_sha:
                errors.append(f"Model file {name} modified: expected {exp_sha}, got {act_sha}")

    # Check prepared files hashes
    for name, exp_sha in manifest.get("prepared_files", {}).items():
        target = PRIVATE_DIR / name
        if not target.exists():
            errors.append(f"Prepared file missing: {target}")
        else:
            act_sha = sha256_file(target)
            if act_sha != exp_sha:
                errors.append(f"Prepared file {name} hash drift: expected {exp_sha}, got {act_sha}")

    ok = len(errors) == 0
    if verbose:
        if ok:
            print(f"[PASS] Freeze manifest key sets and hashes verified ({len(manifest.get('prepared_files', {}))} prepared, {len(manifest.get('model_files', {}))} model files).")
        else:
            print(f"[FAIL] Freeze manifest verification failed with {len(errors)} errors:")
            for e in errors:
                print(f"  - {e}")
    return ok, errors


def verify_ocr_spans(verbose: bool = True) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not OCR_SPANS_PATH.exists():
        errors.append(f"OCR spans file missing: {OCR_SPANS_PATH}")
        return False, errors

    records = load_json(OCR_SPANS_PATH)
    if len(records) != 22:
        errors.append(f"Expected 22 template records in ocr_spans.json, got {len(records)}")

    protected_terms = [
        "+[number]",
        "[tel_no]",
        "네",
        "(오늘)",
        "스팸",
        "없는 발",
        "cj대한통운",
        "우체국",
        "[url]",
        "배송",
        "동·호수",
        "주소",
    ]

    spanned_count = 0
    for r in records:
        idx = r["template_index"]
        text = r["original_text"]
        spans = r["spans"]
        if spans:
            spanned_count += 1

        # Check overlapping spans
        sorted_spans = sorted(spans, key=lambda s: s["start"])
        for i in range(len(sorted_spans) - 1):
            if sorted_spans[i]["end"] > sorted_spans[i + 1]["start"]:
                errors.append(f"Template {idx} has overlapping spans: {sorted_spans[i]} and {sorted_spans[i+1]}")

        # Check quotes and non-deletion invariants
        for s in spans:
            st, en, quote, reason = s["start"], s["end"], s["quote"], s["reason"]
            actual = text[st:en]
            if actual != quote:
                errors.append(f"Template {idx} span quote mismatch at [{st}:{en}]: expected {quote!r}, got {actual!r}")

            for term in protected_terms:
                if term in quote:
                    errors.append(f"Template {idx} span deletes protected term {term!r}: quote={quote!r}")

        # Check cleaned text
        cleaned = text
        for s in sorted(spans, key=lambda s: s["start"], reverse=True):
            cleaned = cleaned[: s["start"]] + cleaned[s["end"] :]
        if cleaned != r["cleaned_text"]:
            errors.append(f"Template {idx} cleaned_text mismatch")

    if spanned_count != 9:
        errors.append(f"Expected exactly 9 templates with OCR spans, got {spanned_count}")

    ok = len(errors) == 0
    if verbose:
        if ok:
            print(f"[PASS] Narrowed OCR spans verified: 22 templates (9 with spans, 13 zero-span SMS), all contact headers/warnings preserved.")
        else:
            print(f"[FAIL] OCR spans verification failed with {len(errors)} errors:")
            for e in errors:
                print(f"  - {e}")
    return ok, errors


def verify_normal_candidates(verbose: bool = True) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not NORMAL_INPUTS_PATH.exists():
        errors.append(f"Normal candidates file missing: {NORMAL_INPUTS_PATH}")
        return False, errors

    rows = load_json(NORMAL_INPUTS_PATH)
    if len(rows) != 250:
        errors.append(f"Expected exactly 250 normal candidates, got {len(rows)}")

    candidate_ids = set()
    message_ids = set()
    source_rows = load_json(SOURCE_NORMAL)
    source_by_id = {r["candidate_id"]: r for r in source_rows}

    for idx, r in enumerate(rows):
        cid = r["candidate_id"]
        mid = r["message_id"]

        if cid in candidate_ids:
            errors.append(f"Duplicate candidate_id found: {cid}")
        candidate_ids.add(cid)

        if mid in message_ids:
            errors.append(f"Duplicate message_id found: {mid}")
        message_ids.add(mid)

        if cid not in source_by_id:
            errors.append(f"Row {idx} candidate_id {cid} not in source blind_candidates")
            continue

        src = source_by_id[cid]
        expected_norm = normalize_text(mask_sensitive_text(src["text_raw_masked"]))
        if r["text_normalized"] != expected_norm:
            errors.append(f"Row {idx} ({cid}) text_normalized does not match normalize_text(mask_sensitive_text(...))")
        if r["text_sha256"] != sha256_text(r["text_normalized"]):
            errors.append(f"Row {idx} ({cid}) text_sha256 mismatch")
        if not r.get("split_origin") or not r.get("source") or not r.get("message_category"):
            errors.append(f"Row {idx} ({cid}) missing required metadata fields")

    ok = len(errors) == 0
    if verbose:
        if ok:
            print(f"[PASS] Normal candidates verified: 250 unique rows, bit-for-bit match with normalization pipeline.")
        else:
            print(f"[FAIL] Normal candidates verification failed with {len(errors)} errors:")
            for e in errors:
                print(f"  - {e}")
    return ok, errors


def verify_models_and_configs(verbose: bool = True) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for seed in SEEDS:
        model_dir = SOURCE_MODEL_DIR / f"seed_{seed}/DUP/model"
        if not model_dir.exists():
            errors.append(f"Seed {seed} model dir missing: {model_dir}")
            continue
        cfg_path = model_dir / "config.json"
        if not cfg_path.exists():
            errors.append(f"Seed {seed} model config missing: {cfg_path}")
            continue
        cfg = load_json(cfg_path)
        mpe = cfg.get("max_position_embeddings")
        if mpe != 300:
            errors.append(f"Seed {seed} model max_position_embeddings is {mpe} (expected 300)")

    ok = len(errors) == 0
    if verbose:
        if ok:
            print(f"[PASS] Models verified: 5 DUP seeds, max_position_embeddings=300 strictly enforced.")
        else:
            print(f"[FAIL] Model verification failed with {len(errors)} errors:")
            for e in errors:
                print(f"  - {e}")
    return ok, errors


def verify_provenance_metadata(verbose: bool = True) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not PROVENANCE_PATH.exists():
        errors.append(f"Provenance metadata file missing: {PROVENANCE_PATH}")
        return False, errors

    doc = load_json(PROVENANCE_PATH)
    if doc.get("total_rows") != 272:
        errors.append(f"Expected 272 total rows in provenance metadata, got {doc.get('total_rows')}")
    if doc.get("kisa_rows") != 22:
        errors.append(f"Expected 22 KISA rows, got {doc.get('kisa_rows')}")
    if doc.get("normal_rows") != 250:
        errors.append(f"Expected 250 normal rows, got {doc.get('normal_rows')}")

    invariants = doc.get("safety_invariants", {})
    if invariants.get("max_position_embeddings_clamped_to_300") is not True:
        errors.append("Provenance: max_position_embeddings_clamped_to_300 is not True")
    if invariants.get("positional_unk_preserves_attention_mask_and_positions") is not True:
        errors.append("Provenance: positional_unk_preserves_attention_mask_and_positions is not True")
    if invariants.get("head_tail_short_unchanged") is not True:
        errors.append("Provenance: head_tail_short_unchanged is not True")
    if invariants.get("head_tail_long_budget_equals_128") is not True:
        errors.append("Provenance: head_tail_long_budget_equals_128 is not True")

    ok = len(errors) == 0
    if verbose:
        if ok:
            print(f"[PASS] Provenance metadata verified: 272 rows × 7 conditions, all token invariants confirmed.")
        else:
            print(f"[FAIL] Provenance metadata verification failed with {len(errors)} errors:")
            for e in errors:
                print(f"  - {e}")
    return ok, errors


def build_encodings(
    texts: list[str],
    spans_per_text: list[list[dict[str, Any]]],
    tokenizer: Any,
) -> dict[str, dict[str, Any]]:
    """Generate tokenized inputs for all 7 fixed conditions."""
    import torch

    variants: dict[str, dict[str, Any]] = {}

    # 1. original128
    enc128 = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=128,
        return_tensors="pt",
        return_offsets_mapping=True,
    )
    offsets128 = enc128.pop("offset_mapping")
    orig128 = dict(enc128)
    variants["original128"] = orig128

    # 2. ocr_delete128
    cleaned_texts = []
    for t, spans in zip(texts, spans_per_text):
        c = t
        for s in sorted(spans, key=lambda x: x["start"], reverse=True):
            c = c[: s["start"]] + c[s["end"] :]
        cleaned_texts.append(c)

    enc_del128 = tokenizer(
        cleaned_texts,
        truncation=True,
        padding="max_length",
        max_length=128,
        return_tensors="pt",
    )
    variants["ocr_delete128"] = dict(enc_del128)

    # 3. cap300 (Max length clamped to 300, matching model's max_position_embeddings)
    enc300 = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=300,
        return_tensors="pt",
        return_offsets_mapping=True,
    )
    offsets300 = enc300.pop("offset_mapping")
    orig300 = dict(enc300)
    variants["cap300"] = orig300

    # 4. ocr_delete300
    enc_del300 = tokenizer(
        cleaned_texts,
        truncation=True,
        padding="max_length",
        max_length=300,
        return_tensors="pt",
    )
    variants["ocr_delete300"] = dict(enc_del300)

    # 5. ocr_unk128: Replace tokens overlapping OCR spans with UNK, retaining positions/masks
    unk128 = {k: v.clone() for k, v in orig128.items()}
    for i, spans in enumerate(spans_per_text):
        if not spans:
            continue
        for j, (start, end) in enumerate(offsets128[i].tolist()):
            if end > start and any(start < s["end"] and end > s["start"] for s in spans):
                unk128["input_ids"][i, j] = tokenizer.unk_token_id
    assert torch.equal(unk128["attention_mask"], orig128["attention_mask"]), "UNK128 mask drift"
    variants["ocr_unk128"] = unk128

    # 6. ocr_unk300: Same positional UNK at 300 tokens
    unk300 = {k: v.clone() for k, v in orig300.items()}
    for i, spans in enumerate(spans_per_text):
        if not spans:
            continue
        for j, (start, end) in enumerate(offsets300[i].tolist()):
            if end > start and any(start < s["end"] and end > s["start"] for s in spans):
                unk300["input_ids"][i, j] = tokenizer.unk_token_id
    assert torch.equal(unk300["attention_mask"], orig300["attention_mask"]), "UNK300 mask drift"
    variants["ocr_unk300"] = unk300

    # 7. head_tail128: 63 head + 63 tail body tokens with CLS/SEP for >126 tokens
    headtail = {k: v.clone() for k, v in orig128.items()}
    full_ids = tokenizer(texts, add_special_tokens=False, truncation=False, verbose=False)["input_ids"]
    assert tokenizer.num_special_tokens_to_add(False) == 2, "Special token budget must be 2 (CLS, SEP)"
    for i, ids in enumerate(full_ids):
        if len(ids) > 126:
            changed = [tokenizer.cls_token_id] + ids[:63] + ids[-63:] + [tokenizer.sep_token_id]
            assert len(changed) == 128, f"Head-tail budget must equal 128, got {len(changed)}"
            headtail["input_ids"][i] = torch.tensor(changed)
            headtail["attention_mask"][i] = 1
            if "token_type_ids" in headtail:
                headtail["token_type_ids"][i] = 0
    variants["head_tail128"] = headtail

    return variants


def validate_predictions(df_pred: pd.DataFrame, seeds: list[int] | None = None) -> None:
    """Enforce exact 9520 rows, complete keys, finite values, baseline replay, and no-op invariants."""
    # 1. Total row count: 272 inputs * 7 conditions * 5 seeds = 9520
    seeds = SEEDS if seeds is None else seeds
    expected_n = 272 * len(CONDITIONS) * len(seeds)
    assert seeds and set(seeds) <= set(SEEDS) and len(seeds) == len(set(seeds))
    assert len(df_pred) == expected_n, f"Expected exactly {expected_n} prediction rows, found {len(df_pred)}"

    # 2. Unique complete keys
    key_tuples = set(zip(df_pred["row_id"], df_pred["seed"], df_pred["condition"]))
    assert len(key_tuples) == expected_n, f"Duplicate prediction keys: {len(key_tuples)}"

    # Check that required row IDs are present
    kisa_inputs = load_json(KISA_INPUTS_PATH)
    normal_inputs = load_json(NORMAL_INPUTS_PATH)

    exp_kisa_ids = {f"kisa_{r['template_index']:02d}" for r in kisa_inputs}
    exp_norm_ids = {f"normal_{r['candidate_id']}" for r in normal_inputs}
    all_exp_ids = exp_kisa_ids | exp_norm_ids
    assert key_tuples == {(rid, seed, cond) for rid in all_exp_ids for seed in seeds for cond in CONDITIONS}, "Incomplete or unknown prediction key grid"
    metadata = {
        f"kisa_{r['template_index']:02d}": ("kisa_unique", r['primary_model_input_sha256'], r['group_id'], r['is_group_representative'], 1)
        for r in kisa_inputs
    }
    metadata.update({f"normal_{r['candidate_id']}": ("normal_candidates", r['candidate_id'], "none", False, 0) for r in normal_inputs})
    thresholds = load_thresholds()
    for r in df_pred.itertuples(index=False):
        assert (r.cohort, r.source_id, r.group_id, r.is_group_representative, r.label) == metadata[r.row_id], "Prediction source metadata drift"
        assert math.isfinite(r.threshold) and abs(r.threshold - thresholds[r.seed]) < 1e-14, "Threshold drift"

    act_ids = set(df_pred["row_id"].unique())
    assert act_ids == all_exp_ids, f"Row ID set mismatch! Missing: {all_exp_ids - act_ids}, Extra: {act_ids - all_exp_ids}"

    # 3. Value domain and finiteness checks
    assert not df_pred["probability"].isna().any(), "NaN found in probabilities!"
    assert not df_pred["threshold"].isna().any(), "NaN found in thresholds!"
    assert not df_pred["baseline_probability"].isna().any(), "NaN found in baseline_probabilities!"

    assert ((df_pred["probability"] >= 0.0) & (df_pred["probability"] <= 1.0)).all(), "Probability outside [0, 1]!"
    assert ((df_pred["baseline_probability"] >= 0.0) & (df_pred["baseline_probability"] <= 1.0)).all(), "Baseline probability outside [0, 1]!"
    assert (df_pred["threshold"] > 0.0).all(), "Threshold non-positive!"

    # 4. Predictions alignment
    calc_preds = (df_pred["probability"] >= df_pred["threshold"]).astype(int)
    assert (df_pred["prediction"] == calc_preds).all(), "Prediction mismatch with probability >= threshold!"

    calc_base_preds = (df_pred["baseline_probability"] >= df_pred["threshold"]).astype(int)
    assert (df_pred["baseline_prediction"] == calc_base_preds).all(), "Baseline prediction mismatch with baseline_probability >= threshold!"

    # 5. Label invariants
    kisa_mask = df_pred["cohort"] == "kisa_unique"
    norm_mask = df_pred["cohort"] == "normal_candidates"
    assert (df_pred.loc[kisa_mask, "label"] == 1).all(), "KISA rows must have label 1!"
    assert (df_pred.loc[norm_mask, "label"] == 0).all(), "Normal rows must have label 0!"

    # 6. Original E2 baseline score tolerance <= 1e-5 on original128
    df_kisa_base_src = pd.read_csv(SOURCE_PRED_KISA)
    frozen_base_map = {}
    for _, r in df_kisa_base_src.groupby("primary_model_input_sha256").first().iterrows():
        sha = r.name
        frozen_base_map[sha] = {s: float(r[f"prob_seed_{s}"]) for s in SEEDS}

    for _, row in df_pred[(df_pred["cohort"] == "kisa_unique") & (df_pred["condition"] == "original128")].iterrows():
        sha = row["source_id"]
        seed = row["seed"]
        exp_p = frozen_base_map[sha][seed]
        act_p = row["probability"]
        assert abs(act_p - exp_p) <= 1e-5, f"KISA original128 baseline drift for {sha[:8]} seed {seed}: {act_p} vs {exp_p}"

    # 7. No-op condition probability equality within 1e-5
    # For normal candidates (all 250 have zero spans):
    # ocr_delete128 == original128, ocr_unk128 == original128, ocr_delete300 == cap300, ocr_unk300 == cap300
    df_indexed = df_pred.set_index(["row_id", "seed", "condition"])["probability"]
    for rid in exp_norm_ids:
        for s in seeds:
            p_orig = df_indexed.loc[(rid, s, "original128")]
            p_del128 = df_indexed.loc[(rid, s, "ocr_delete128")]
            p_unk128 = df_indexed.loc[(rid, s, "ocr_unk128")]
            assert abs(p_del128 - p_orig) <= 1e-5, f"Normal no-op drift ocr_delete128 at {rid} seed {s}"
            assert abs(p_unk128 - p_orig) <= 1e-5, f"Normal no-op drift ocr_unk128 at {rid} seed {s}"

            p_cap300 = df_indexed.loc[(rid, s, "cap300")]
            p_del300 = df_indexed.loc[(rid, s, "ocr_delete300")]
            p_unk300 = df_indexed.loc[(rid, s, "ocr_unk300")]
            assert abs(p_del300 - p_cap300) <= 1e-5, f"Normal no-op drift ocr_delete300 at {rid} seed {s}"
            assert abs(p_unk300 - p_cap300) <= 1e-5, f"Normal no-op drift ocr_unk300 at {rid} seed {s}"

    base = df_pred[df_pred.condition == "original128"].set_index(["row_id", "seed"])
    for r in df_pred.itertuples(index=False):
        b = base.loc[(r.row_id, r.seed)]
        assert abs(r.baseline_probability - b.probability) <= 1e-5
        assert r.baseline_prediction == b.prediction
    for r in kisa_inputs:
        rid = f"kisa_{r['template_index']:02d}"
        for seed in seeds:
            b = base.loc[(rid, seed)]
            assert b.prediction == r['baseline_predictions'][str(seed)]['decision'], "E2 decision drift"
            if not r['has_ocr_spans']:
                for lhs, rhs in [('ocr_delete128','original128'),('ocr_unk128','original128'),('ocr_delete300','cap300'),('ocr_unk300','cap300')]:
                    assert abs(df_indexed.loc[(rid,seed,lhs)] - df_indexed.loc[(rid,seed,rhs)]) <= 1e-5


def verify_run_receipt() -> None:
    receipt = load_json(RECEIPT_PATH)
    bindings = {'manifest_sha256': MANIFEST_PATH, 'runner_sha256': RUNNER_PATH,
                'acceptance_sha256': ACCEPTANCE_PATH, 'predictions_csv_sha256': PREDICTIONS_CSV_PATH}
    for key, path in bindings.items():
        assert receipt[key] == sha256_file(path), f"Run receipt binding drift: {key}"
    acc = load_json(ACCEPTANCE_PATH)
    assert acc.get('accepted') is True and acc.get('status') == 'main_accepted'
    assert acc['manifest_sha256'] == receipt['manifest_sha256'] and acc['runner_sha256'] == receipt['runner_sha256']
    assert receipt['seeds'] == SEEDS and receipt['conditions'] == CONDITIONS and receipt['total_prediction_rows'] == 9520
    assert set(receipt['checkpoint_sha256s']) == {str(s) for s in SEEDS}
    for seed in SEEDS:
        path = PRIVATE_DIR / f'seed_{seed}_diagnostics.json'
        assert sha256_file(path) == receipt['checkpoint_sha256s'][str(seed)]
        c = load_json(path)
        assert c['seed'] == seed and c['manifest_sha256'] == receipt['manifest_sha256'] and c['runner_sha256'] == receipt['runner_sha256']
        validate_predictions(pd.DataFrame(c['records']), seeds=[seed])


def evaluate_candidate_criteria(df_pred: pd.DataFrame) -> dict[str, Any]:
    """Evaluate head_tail128 candidate criteria independently per EACH seed.

    Rules:
    - Condition: head_tail128
    - Per seed requirements:
        (a) kisa_unique corrected_fn >= 1
        (b) kisa_unique new_fn == 0
        (c) normal_candidates new_fp == 0
    - All 5 seeds must individually satisfy (a), (b), (c).
    - Never sum same-message seed repeats into reported people/rows or add unique+representative FN counts.
    """
    thresholds = load_thresholds()
    by_seed: dict[str, Any] = {}

    for seed in SEEDS:
        th = thresholds[seed]
        df_seed = df_pred[df_pred["seed"] == seed]

        # 1. KISA Unique evaluation
        df_kisa = df_seed[df_seed["cohort"] == "kisa_unique"]
        df_kisa_base = df_kisa[df_kisa["condition"] == "original128"]
        base_kisa_map = dict(zip(df_kisa_base["row_id"], df_kisa_base["prediction"]))

        df_kisa_ht = df_kisa[df_kisa["condition"] == "head_tail128"]
        kisa_corr_fn = 0
        kisa_new_fn = 0

        for _, row in df_kisa_ht.iterrows():
            rid = row["row_id"]
            old_pred = base_kisa_map[rid]  # Strict lookup
            cur_pred = row["prediction"]
            if old_pred == 0 and cur_pred == 1:
                kisa_corr_fn += 1
            elif old_pred == 1 and cur_pred == 0:
                kisa_new_fn += 1

        # 2. Normal Candidates evaluation
        df_norm = df_seed[df_seed["cohort"] == "normal_candidates"]
        df_norm_base = df_norm[df_norm["condition"] == "original128"]
        base_norm_map = dict(zip(df_norm_base["row_id"], df_norm_base["prediction"]))

        df_norm_ht = df_norm[df_norm["condition"] == "head_tail128"]
        norm_corr_fp = 0
        norm_new_fp = 0

        for _, row in df_norm_ht.iterrows():
            rid = row["row_id"]
            old_pred = base_norm_map[rid]  # Strict lookup
            cur_pred = row["prediction"]
            if old_pred == 1 and cur_pred == 0:
                norm_corr_fp += 1
            elif old_pred == 0 and cur_pred == 1:
                norm_new_fp += 1

        crit_a = kisa_corr_fn >= 1
        crit_b = kisa_new_fn == 0
        crit_c = norm_new_fp == 0
        seed_passed = crit_a and crit_b and crit_c

        by_seed[str(seed)] = {
            "seed": seed,
            "threshold": th,
            "kisa_unique_n": len(df_kisa_ht),
            "kisa_corrected_fn": kisa_corr_fn,
            "kisa_new_fn": kisa_new_fn,
            "normal_candidates_n": len(df_norm_ht),
            "normal_corrected_fp": norm_corr_fp,
            "normal_new_fp": norm_new_fp,
            "crit_a_recovered_fn": crit_a,
            "crit_b_zero_new_fn": crit_b,
            "crit_c_zero_new_normal_fp": crit_c,
            "seed_passed": seed_passed,
        }

    all_passed = all(s_data["seed_passed"] for s_data in by_seed.values())
    return {
        "candidate_condition": "head_tail128",
        "all_seeds_passed": all_passed,
        "by_seed": by_seed,
    }


def compute_aggregate_metrics_from_predictions(df_pred: pd.DataFrame) -> list[dict[str, Any]]:
    """Compute exact 19-column table across 105 cohort×seed×condition combinations.

    Retains full numeric precision (.17g) for thresholds and rates.
    """
    thresholds = load_thresholds()
    rows_out: list[dict[str, Any]] = []

    for cohort in COHORTS:
        for seed in SEEDS:
            th = thresholds[seed]
            if cohort == "kisa_unique":
                df_cohort = df_pred[(df_pred["cohort"] == "kisa_unique") & (df_pred["seed"] == seed)]
            elif cohort == "kisa_representatives":
                df_cohort = df_pred[(df_pred["cohort"] == "kisa_unique") & (df_pred["is_group_representative"] == True) & (df_pred["seed"] == seed)]
            elif cohort == "normal_candidates":
                df_cohort = df_pred[(df_pred["cohort"] == "normal_candidates") & (df_pred["seed"] == seed)]
            else:
                continue

            df_base = df_cohort[df_cohort["condition"] == "original128"]
            b_n = len(df_base)
            b_labels = df_base["label"].tolist()
            b_preds = (df_base["probability"] >= th).tolist()
            b_row_ids = df_base["row_id"].tolist()
            base_pred_map = dict(zip(b_row_ids, b_preds))

            b_tp = sum(1 for y, p in zip(b_labels, b_preds) if y == 1 and p is True)
            b_tn = sum(1 for y, p in zip(b_labels, b_preds) if y == 0 and p is False)
            b_fp = sum(1 for y, p in zip(b_labels, b_preds) if y == 0 and p is True)
            b_fn = sum(1 for y, p in zip(b_labels, b_preds) if y == 1 and p is False)

            for condition in CONDITIONS:
                df_cond = df_cohort[df_cohort["condition"] == condition]
                n = len(df_cond)
                labels = df_cond["label"].tolist()
                probs = df_cond["probability"].tolist()
                preds = [p >= th for p in probs]
                row_ids = df_cond["row_id"].tolist()

                tp = sum(1 for y, p in zip(labels, preds) if y == 1 and p is True)
                tn = sum(1 for y, p in zip(labels, preds) if y == 0 and p is False)
                fp = sum(1 for y, p in zip(labels, preds) if y == 0 and p is True)
                fn = sum(1 for y, p in zip(labels, preds) if y == 1 and p is False)

                corrected_fp = 0
                corrected_fn = 0
                new_fp = 0
                new_fn = 0
                for rid, y, cur_p in zip(row_ids, labels, preds):
                    old_p = base_pred_map[rid]  # Strict lookup: require ID
                    if y == 0:
                        if old_p is True and cur_p is False:
                            corrected_fp += 1
                        elif old_p is False and cur_p is True:
                            new_fp += 1
                    elif y == 1:
                        if old_p is False and cur_p is True:
                            corrected_fn += 1
                        elif old_p is True and cur_p is False:
                            new_fn += 1

                # Full numeric precision (.17g)
                recall_val = ""
                fpr_val = ""
                if sum(labels) > 0:
                    rec_f = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                    recall_val = f"{rec_f:.17g}"
                if sum(1 for y in labels if y == 0) > 0:
                    fpr_f = fp / (fp + tn) if (fp + tn) > 0 else 0.0
                    fpr_val = f"{fpr_f:.17g}"

                rows_out.append({
                    "cohort": cohort,
                    "seed": seed,
                    "condition": condition,
                    "n": n,
                    "tp": tp,
                    "tn": tn,
                    "fp": fp,
                    "fn": fn,
                    "baseline_tp": b_tp,
                    "baseline_tn": b_tn,
                    "baseline_fp": b_fp,
                    "baseline_fn": b_fn,
                    "corrected_fp": corrected_fp,
                    "corrected_fn": corrected_fn,
                    "new_fp": new_fp,
                    "new_fn": new_fn,
                    "threshold": f"{th:.17g}",
                    "recall": recall_val,
                    "fpr": fpr_val,
                })

    return rows_out


def render_outputs(
    df_pred: pd.DataFrame | None,
    receipt_data: dict[str, Any] | None,
    provenance_doc: dict[str, Any],
    manifest_doc: dict[str, Any],
    acceptance_doc: dict[str, Any],
) -> tuple[str, str, str]:
    """Pure deterministic rendering function returning (csv_text, json_text, md_text).

    No filesystem writes, no datetime.now() calls.
    """
    # Case 1: Real Predictions Exist (C2 Executed)
    if df_pred is not None:
        assert receipt_data is not None, "Receipt data required when rendering predictions"
        completed_ts = receipt_data["completed_at_utc"]
        grid_rows = compute_aggregate_metrics_from_predictions(df_pred)

        # 1. Deterministic CSV
        csv_lines = [",".join(CSV_HEADER)]
        for r in grid_rows:
            row_str = ",".join(str(r[col]) for col in CSV_HEADER)
            csv_lines.append(row_str)
        csv_text = "\n".join(csv_lines) + "\n"

        # 2. Candidate evaluation per seed
        candidate_res = evaluate_candidate_criteria(df_pred)

        # 3. Primary seed 42 table for all 7 conditions
        s42_summary = {}
        for cond in CONDITIONS:
            k_u = [r for r in grid_rows if r["cohort"] == "kisa_unique" and r["seed"] == PRIMARY_SEED and r["condition"] == cond][0]
            k_r = [r for r in grid_rows if r["cohort"] == "kisa_representatives" and r["seed"] == PRIMARY_SEED and r["condition"] == cond][0]
            n_c = [r for r in grid_rows if r["cohort"] == "normal_candidates" and r["seed"] == PRIMARY_SEED and r["condition"] == cond][0]
            s42_summary[cond] = {
                "condition": cond,
                "kisa_unique_tp": k_u["tp"],
                "kisa_unique_fn": k_u["fn"],
                "kisa_unique_recall": k_u["recall"],
                "kisa_rep_tp": k_r["tp"],
                "kisa_rep_fn": k_r["fn"],
                "kisa_rep_recall": k_r["recall"],
                "normal_fp": n_c["fp"],
                "normal_new_fp": n_c["new_fp"],
                "normal_fpr": n_c["fpr"],
            }

        # Truncation counts from provenance
        prov_rows = provenance_doc.get("rows", [])
        kisa_prov = [r for r in prov_rows if r["cohort"] == "kisa_unique"]
        norm_prov = [r for r in prov_rows if r["cohort"] == "normal_candidates"]

        truncation_stats = {
            "total_diagnostic_rows": len(prov_rows),
            "kisa_unique_total": len(kisa_prov),
            "kisa_unique_truncated_at_128": sum(1 for r in kisa_prov if r["conditions"]["original128"]["is_truncated"]),
            "kisa_unique_truncated_at_300": sum(1 for r in kisa_prov if r["conditions"]["cap300"]["is_truncated"]),
            "normal_candidates_total": len(norm_prov),
            "normal_candidates_truncated_at_128": sum(1 for r in norm_prov if r["conditions"]["original128"]["is_truncated"]),
            "normal_candidates_truncated_at_300": sum(1 for r in norm_prov if r["conditions"]["cap300"]["is_truncated"]),
        }

        # 4. JSON report
        json_doc = {
            "pipeline_version": VERSION,
            "phase": "c2_executed",
            "execution_timestamp_utc": completed_ts,
            "acceptance_status": acceptance_doc.get("status", "main_accepted"),
            "candidate_evaluation": candidate_res,
            "primary_seed_42_conditions": s42_summary,
            "truncation_statistics": truncation_stats,
            "grid_row_count": len(grid_rows),
            "safety_and_integrity": {
                "max_position_embeddings": 300,
                "evaluated_seeds": SEEDS,
                "normal_labels_note": "Normal candidate metrics are development evaluations on mined pool, not certified false positive rates.",
            },
        }
        json_text = json.dumps(json_doc, ensure_ascii=False, indent=2) + "\n"

        # 5. Markdown doc
        md_lines = [
            "# KISA OCR 잔재 진단 및 정상 후보 회귀 검증 실측 보고서",
            "",
            "## 1. 실험 개요 및 실행 조건",
            "",
            f"- **평가 시각**: {completed_ts} (Task C2 완료)",
            f"- **평가 모델**: 사전 고정된 DUP 5개 시드 (Seed {PRIMARY_SEED} 주 모델, {', '.join(str(s) for s in SEEDS if s != PRIMARY_SEED)} 민감도 분석)",
            f"- **전체 집계 규모**: 3개 코호트 × 5개 시드 × 7개 변형 조건 = 총 {len(grid_rows)}개 전수 그리드 행",
            f"- **절단 분모 분석 (Provenance)**: KISA 고유 22건 중 128토큰 절단 {truncation_stats['kisa_unique_truncated_at_128']}건, 300토큰 절단 {truncation_stats['kisa_unique_truncated_at_300']}건. 정상 후보 250건 중 128토큰 절단 {truncation_stats['normal_candidates_truncated_at_128']}건, 300토큰 절단 {truncation_stats['normal_candidates_truncated_at_300']}건.",
            "",
            "---",
            "",
            f"## 2. 주 모델(Seed {PRIMARY_SEED}) 7개 전 조건 실측 성적표",
            "",
            "| 조건명 | KISA 고유 TP / FN (Recall) | 그룹 대표 TP / FN (Recall) | 정상 후보 FP / New FP (FPR) |",
            "| :--- | :---: | :---: | :---: |",
        ]
        for cond in CONDITIONS:
            s_data = s42_summary[cond]
            u_rec = f"{float(s_data['kisa_unique_recall'])*100:.2f}%" if s_data["kisa_unique_recall"] else "-"
            r_rec = f"{float(s_data['kisa_rep_recall'])*100:.2f}%" if s_data["kisa_rep_recall"] else "-"
            n_fpr = f"{float(s_data['normal_fpr'])*100:.2f}%" if s_data["normal_fpr"] else "-"
            md_lines.append(f"| **`{cond}`** | {s_data['kisa_unique_tp']} / {s_data['kisa_unique_fn']} ({u_rec}) | {s_data['kisa_rep_tp']} / {s_data['kisa_rep_fn']} ({r_rec}) | {s_data['normal_fp']} / {s_data['normal_new_fp']} ({n_fpr}) |")

        md_lines.extend([
            "",
            "---",
            "",
            "## 3. 사전 선언된 개선 후보(`head_tail128`) 5개 시드별 개별 판정표",
            "",
            "| 시드 | 적용 임계값 | KISA 미탐 복구 (a: >=1) | KISA 신규 미탐 (b: ==0) | 정상 신규 오탐 (c: ==0) | 시드 판정 |",
            "| :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for seed in SEEDS:
            sd = candidate_res["by_seed"][str(seed)]
            s_verdict = "**PASS**" if sd["seed_passed"] else "FAIL"
            md_lines.append(f"| Seed {seed} | `{sd['threshold']:.6f}` | {sd['kisa_corrected_fn']}건 ({'O' if sd['crit_a_recovered_fn'] else 'X'}) | {sd['kisa_new_fn']}건 ({'O' if sd['crit_b_zero_new_fn'] else 'X'}) | {sd['normal_new_fp']}건 ({'O' if sd['crit_c_zero_new_normal_fp'] else 'X'}) | {s_verdict} |")

        md_lines.extend([
            "",
            f"**최종 개선 후보 판정**: **{'통과 (Candidate Passed across all 5 seeds)' if candidate_res['all_seeds_passed'] else '불통과 (Candidate Rejected)'}**",
            "",
            "---",
            "",
            "## 4. 방법론적 한계 및 보안 고지",
            "",
            "- **사후 진단 한계**: 본 연구는 이미 평가된 KISA 자료를 재사용한 사후 진단이며, 독립 전향 평가 없이 기본 탐지기를 교체하지 않습니다.",
            "- **정상 라벨 성격**: 정상 후보군의 오탐은 출처 데이터셋의 개발용 라벨 기준이며, 검증된 무결점 정상이나 실서비스 독립 FPR이 아닙니다.",
            "- **비공개 정보 격리**: 본 공개 보고서에는 어떠한 원천 본문 인용, 식별 번호, 개인정보, 비공개 절대경로도 포함되지 않습니다.",
            "",
        ])
        md_text = "\n".join(md_lines) + "\n"

        return csv_text, json_text, md_text

    # Case 2: Prepared State (C1 Prepared, No Predictions Yet)
    else:
        created_ts = manifest_doc.get("created_at_utc", "2026-09-21T00:00:00Z")
        csv_text = ",".join(CSV_HEADER) + "\n"

        prov_rows = provenance_doc.get("rows", [])
        kisa_prov = [r for r in prov_rows if r["cohort"] == "kisa_unique"]
        norm_prov = [r for r in prov_rows if r["cohort"] == "normal_candidates"]

        truncation_stats = {
            "total_diagnostic_rows": len(prov_rows),
            "kisa_unique_total": len(kisa_prov),
            "kisa_unique_truncated_at_128": sum(1 for r in kisa_prov if r["conditions"]["original128"]["is_truncated"]),
            "kisa_unique_truncated_at_300": sum(1 for r in kisa_prov if r["conditions"]["cap300"]["is_truncated"]),
            "normal_candidates_total": len(norm_prov),
            "normal_candidates_truncated_at_128": sum(1 for r in norm_prov if r["conditions"]["original128"]["is_truncated"]),
            "normal_candidates_truncated_at_300": sum(1 for r in norm_prov if r["conditions"]["cap300"]["is_truncated"]),
        }

        json_doc = {
            "pipeline_version": VERSION,
            "phase": "c1_prepared",
            "preparation_timestamp_utc": created_ts,
            "acceptance_status": acceptance_doc.get("status", "c1_prepared_pending_main_acceptance"),
            "conditions": {
                "original128": "Original KC-BERT tokenizer, max_length=128 right-truncated (baseline)",
                "ocr_delete128": "Screen UI/OCR artifact character deletion, max_length=128",
                "cap300": "Original text, max_length=300 (model max_position_embeddings=300)",
                "ocr_delete300": "OCR deletion + 300 tokens (2x2 length vs deletion contrast)",
                "ocr_unk128": "Positional UNK masking on OCR spans, preserving positions and masks, max_length=128",
                "ocr_unk300": "Positional UNK masking on OCR spans, max_length=300",
                "head_tail128": "Predeclared improvement candidate: 63 head + 63 tail tokens for >126 token texts",
            },
            "cohorts": {
                "kisa_unique": {"count": 22, "description": "Unique KISA model inputs retained from E1"},
                "kisa_representatives": {"count": 18, "description": "Deterministic group representatives (min SHA256)"},
                "normal_candidates": {"count": 250, "description": "Realistic normal candidate review set (development labels)"},
            },
            "candidate_acceptance_criteria": {
                "candidate_condition": "head_tail128",
                "evaluation_scope": "Evaluated per EACH of the 5 seeds independently; all 5 must pass",
                "criterion_a": "Recovers >= 1 KISA False Negative on kisa_unique in each seed",
                "criterion_b": "0 new KISA False Negatives on kisa_unique in each seed",
                "criterion_c": "0 new False Positives on normal_candidates in each seed",
            },
            "truncation_statistics": truncation_stats,
            "safety_and_integrity": {
                "zero_inference_in_c1": True,
                "max_position_embeddings": 300,
                "private_storage_mode": "0700/0600",
            },
        }
        json_text = json.dumps(json_doc, ensure_ascii=False, indent=2) + "\n"

        md_lines = [
            "# KISA OCR 잔재 진단 및 정상 후보 회귀 검증 계획 (Task C1 준비 완료)",
            "",
            "## 1. 개요 및 연구 목적",
            "",
            "- **연구 상태**: Task C1 입력 패키지 및 272행 토큰 변형 준비 완료 (모델 추론 미수행 상태 보존)",
            f"- **평가 대상 모델**: 사전 고정된 DUP 5개 시드 (Seed {PRIMARY_SEED} 주 모델, {', '.join(str(s) for s in SEEDS if s != PRIMARY_SEED)} 민감도 확인)",
            f"- **절단 분모 분석 (Provenance)**: KISA 고유 22건 중 128토큰 절단 {truncation_stats['kisa_unique_truncated_at_128']}건, 300토큰 절단 {truncation_stats['kisa_unique_truncated_at_300']}건. 정상 후보 250건 중 128토큰 절단 {truncation_stats['normal_candidates_truncated_at_128']}건, 300토큰 절단 {truncation_stats['normal_candidates_truncated_at_300']}건.",
            "",
            "---",
            "",
            "## 2. 7개 고정 변형 조건 및 실험 설계",
            "",
            "| 조건명 | 토큰 한도 | 적용 방식 및 설계 의도 |",
            "| :--- | :---: | :--- |",
            "| **`original128`** | 128 | 원래 토크나이저 우측 절단. 기존 동결 평가(E2)와 완전히 동일한 기준선. |",
            "| **`ocr_delete128`** | 128 | 화면 상태·작성창 UI 구간만 삭제 후 128토큰 절단. 잔재 삭제에 따른 본문 앞당김 효과 관찰. |",
            "| **`cap300`** | 300 | 원문 그대로 모델의 최대 위치 임베딩(300)까지 입력. 길이 확장에 따른 미탐 복구 관찰. |",
            "| **`ocr_delete300`** | 300 | OCR 잔재 삭제 후 300토큰 입력. 2×2 요인 설계로 길이 효과와 삭제 효과의 상호작용 검증. |",
            "| **`ocr_unk128`** | 128 | 원문 토큰 위치·어텐션을 유지하며 OCR 구간과 겹치는 토큰만 UNK 대체 (위치 고정 대조군). |",
            "| **`ocr_unk300`** | 300 | 300토큰에서 위치 고정 UNK 대조군 적용. |",
            "| **`head_tail128`** | 128 | **사전 선언된 유일한 개선 후보**. 126토큰 초과 시 앞 63개+뒤 63개 토큰 결합(총 128토큰). |",
            "",
            "---",
            "",
            "## 3. 사전 선언된 개선 후보 판단 기준 (시드별 개별 검증 원칙)",
            "",
            "개선 후보는 `head_tail128` 하나로 사전 고정하며, 사후적으로 유리한 조건을 후보로 선택하지 않습니다.",
            "후보 통과를 위해서는 5개 시드 각각에서 다음 3대 조건을 **모두 충족**해야 합니다 (합산 합격 불가):",
            "1. **조건 (a)**: KISA 미탐(FN)을 최소 1건 이상 복구할 것 (`corrected_fn >= 1`).",
            "2. **조건 (b)**: 기존 KISA 탐지 건에서 신규 미탐이 단 1건도 발생하지 않을 것 (`new_fn == 0`).",
            "3. **조건 (c)**: 250건의 정상 후보군에서 기존 정상 판정을 새 스미싱 판정으로 바꾸는 신규 오탐이 없을 것 (`new_fp == 0`).",
            "",
            "> **경계 고지**: 조건을 통과하더라도 향후 독립 전향 평가를 위한 후보일 뿐, 즉시 프로덕션 모델을 대체하지 않습니다. 실패 시 조건을 반복 조정(tuning)하지 않고 결과를 있는 그대로 보고합니다.",
            "",
            "---",
            "",
            "## 4. 협소화된 OCR 구간 어노테이션 원칙 및 보존",
            "",
            "- **보수적 보존 원칙**: 모든 발신 번호(`+[number]`, `[tel_no]`), 브랜드(`cj대한통운`), URL(`[url]`), 송장번호, 주소/배송 관련 문구, 답장 지시 문구, 답장 `네` 및 시간 말풍선, 시스템 스팸 경고 배너 및 잔재(`없는 발`)는 절대 삭제하지 않음.",
            "- **제거 대상**: 시간·배터리·통신망 상태바 및 뒤로가기 버튼(발신자 번호 직전에서 종료), 작성창 플레이스홀더(`+ imessage`, `+ 문자 메시지 · sms`)만 엄격히 제거.",
            "- **프라이버시 및 무결성**: 모든 개별 텍스트 및 어노테이션은 비공개 디렉토리(`~/scamlens_private/kisa_ocr_diagnostics_20260921_v1/`, 0700/0600)에 보관되며 SHA-256 매니페스트로 동결됨.",
            "- **추론 게이트**: Task C1 단계에서는 **모델 추론을 일체 수행하지 않으며(Zero Inference)**, 코디네이터/메인의 독립 검수 및 `main_c1_acceptance.json` 승인 후에만 C2 추론이 실행됨.",
            "",
        ]
        md_text = "\n".join(md_lines) + "\n"

        return csv_text, json_text, md_text


def render_reports() -> None:
    """Render public summary JSON, Markdown, and CSV schema from pure renderer."""
    PUBLIC_JSON_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_DOC_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_CSV_REPORT.parent.mkdir(parents=True, exist_ok=True)

    df_pred = pd.read_csv(PREDICTIONS_CSV_PATH) if PREDICTIONS_CSV_PATH.exists() else None
    receipt_data = load_json(RECEIPT_PATH) if RECEIPT_PATH.exists() else None
    prov_doc = load_json(PROVENANCE_PATH) if PROVENANCE_PATH.exists() else {}
    manifest_doc = load_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}
    acc_doc = load_json(ACCEPTANCE_PATH) if ACCEPTANCE_PATH.exists() else {}

    csv_text, json_text, md_text = render_outputs(df_pred, receipt_data, prov_doc, manifest_doc, acc_doc)

    # Safe CSV write: never overwrite multi-line CSV with empty header if predictions don't exist
    should_write_csv = True
    if df_pred is None and PUBLIC_CSV_REPORT.exists():
        with open(PUBLIC_CSV_REPORT, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 1:
            should_write_csv = False

    if should_write_csv:
        PUBLIC_CSV_REPORT.write_text(csv_text, encoding="utf-8")
        print(f"Wrote CSV report: {PUBLIC_CSV_REPORT}")

    PUBLIC_JSON_REPORT.write_text(json_text, encoding="utf-8")
    print(f"Wrote JSON report: {PUBLIC_JSON_REPORT}")

    PUBLIC_DOC_REPORT.write_text(md_text, encoding="utf-8")
    print(f"Wrote Doc report: {PUBLIC_DOC_REPORT}")


def check_pipeline() -> bool:
    print("=== [KISA OCR Diagnostics Pipeline Check (Read-Only)] ===")
    ok_m, _ = verify_manifest()
    ok_s, _ = verify_ocr_spans()
    ok_n, _ = verify_normal_candidates()
    ok_mod, _ = verify_models_and_configs()
    ok_p, _ = verify_provenance_metadata()

    # Check acceptance status
    acc = load_json(ACCEPTANCE_PATH) if ACCEPTANCE_PATH.exists() else {}
    status = acc.get("status", "unknown")
    accepted = acc.get("accepted", False)
    print(f"[INFO] Main C1 acceptance gate: status={status!r}, accepted={accepted}")

    # Check whether C2 predictions exist
    if not PREDICTIONS_CSV_PATH.exists():
        if RECEIPT_PATH.exists():
            print('[FAIL] Receipt exists without predictions.')
            return False
        print("[INFO] C2 inference predictions do not exist yet (phase: prepared-not-executed).")
        print("[INFO] Main acceptance gate status: 'c1_prepared_pending_main_acceptance'. Ready for Main inspection.")

        # Verify rendered public files match pure renderer
        prov_doc = load_json(PROVENANCE_PATH)
        manifest_doc = load_json(MANIFEST_PATH)
        exp_csv, exp_json, exp_md = render_outputs(None, None, prov_doc, manifest_doc, acc)

        diffs = [str(p) for p in (PUBLIC_CSV_REPORT, PUBLIC_JSON_REPORT, PUBLIC_DOC_REPORT) if not p.is_file()]
        if PUBLIC_CSV_REPORT.exists() and PUBLIC_CSV_REPORT.read_text(encoding="utf-8") != exp_csv:
            diffs.append("PUBLIC_CSV_REPORT content drift")
        if PUBLIC_JSON_REPORT.exists() and PUBLIC_JSON_REPORT.read_text(encoding="utf-8") != exp_json:
            diffs.append("PUBLIC_JSON_REPORT content drift")
        if PUBLIC_DOC_REPORT.exists() and PUBLIC_DOC_REPORT.read_text(encoding="utf-8") != exp_md:
            diffs.append("PUBLIC_DOC_REPORT content drift")

        if diffs:
            print(f"[FAIL] Prepared public report drift detected: {diffs}")
            c2_ok = False
        else:
            print("[PASS] Prepared public report files match deterministic pure renderer exactly.")
            c2_ok = True
    else:
        print("[INFO] C2 predictions found. Performing independent recomputation check...")
        try:
            df_pred = pd.read_csv(PREDICTIONS_CSV_PATH)
            receipt_data = load_json(RECEIPT_PATH)
            prov_doc = load_json(PROVENANCE_PATH)
            manifest_doc = load_json(MANIFEST_PATH)

            validate_predictions(df_pred)
            verify_run_receipt()
            candidate_res = evaluate_candidate_criteria(df_pred)

            exp_csv, exp_json, exp_md = render_outputs(df_pred, receipt_data, prov_doc, manifest_doc, acc)

            diffs = []
            if PUBLIC_CSV_REPORT.read_text(encoding="utf-8") != exp_csv:
                diffs.append("PUBLIC_CSV_REPORT content drift")
            if PUBLIC_JSON_REPORT.read_text(encoding="utf-8") != exp_json:
                diffs.append("PUBLIC_JSON_REPORT content drift")
            if PUBLIC_DOC_REPORT.read_text(encoding="utf-8") != exp_md:
                diffs.append("PUBLIC_DOC_REPORT content drift")

            if diffs:
                print(f"[FAIL] Executed public report drift detected: {diffs}")
                c2_ok = False
            else:
                print(f"[PASS] All 105 grid rows and candidate verdict recomputed and match disk files byte-for-byte.")
                print(f"[INFO] Candidate head_tail128 passed: {candidate_res['all_seeds_passed']}")
                c2_ok = True
        except Exception as e:
            print(f"[FAIL] Recomputation verification failed: {e}")
            c2_ok = False

    overall = ok_m and ok_s and ok_n and ok_mod and ok_p and c2_ok
    if overall:
        print("\n>>> ALL READ-ONLY CHECKS PASSED.")
    else:
        print("\n>>> PIPELINE CHECKS FAILED.")
    return overall


def run_inference_guarded() -> None:
    """Execute model inference across seeds and conditions. Guarded by Main acceptance.

    Overwrites are strictly forbidden. If final predictions or receipt exist, refuses execution.
    """
    print("=== [KISA OCR Diagnostics Inference (C2 Guarded)] ===")

    # 1. Check overwrite refusal
    if PREDICTIONS_CSV_PATH.exists() or RECEIPT_PATH.exists():
        raise RuntimeError(
            f"Final predictions ({PREDICTIONS_CSV_PATH.exists()}) or receipt ({RECEIPT_PATH.exists()}) "
            "already exists! Overwrites are forbidden. Run --check to verify."
        )

    # 2. Gate check: Main C1 acceptance
    if not ACCEPTANCE_PATH.exists():
        raise RuntimeError(f"Main acceptance file missing: {ACCEPTANCE_PATH}. Inference blocked.")

    acc = load_json(ACCEPTANCE_PATH)
    if acc.get("status") != "main_accepted" or acc.get("accepted") is not True:
        raise RuntimeError(
            f"Coordinator acceptance required before inference! Current status: {acc.get('status')!r}, accepted: {acc.get('accepted')}. "
            "Task C1 is PREPARE ONLY. Inference will run during C2 after acceptance."
        )

    # 3. Bind exact manifest and code hashes in acceptance
    if acc.get("manifest_sha256") != sha256_file(MANIFEST_PATH):
        raise RuntimeError("Acceptance manifest_sha256 does not match disk input_manifest.json! Stopping.")
    if acc.get("runner_sha256") != sha256_file(RUNNER_PATH):
        raise RuntimeError("Acceptance runner_sha256 does not match disk runner script! Stopping.")

    # 4. Check manifest hashes
    ok, errors = verify_manifest()
    if not ok:
        raise RuntimeError(f"Manifest verification failed before inference: {errors}")

    print("[C2] Coordinator acceptance confirmed. Commencing diagnostic inference across 5 seeds × 7 conditions...")

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"[C2] Using device: {device}")

    kisa_inputs = load_json(KISA_INPUTS_PATH)
    ocr_spans_records = load_json(OCR_SPANS_PATH)
    normal_inputs = load_json(NORMAL_INPUTS_PATH)
    thresholds = load_thresholds()

    df_kisa_baseline = pd.read_csv(SOURCE_PRED_KISA)
    baseline_by_sha = {}
    for sha, group_df in df_kisa_baseline.groupby("primary_model_input_sha256"):
        row = group_df.iloc[0]
        baseline_by_sha[sha] = {
            s: {"prob": float(row[f"prob_seed_{s}"]), "pred": int(row[f"pred_seed_{s}"])}
            for s in SEEDS
        }

    kisa_texts = [r["primary_model_input"] for r in kisa_inputs]
    kisa_spans = [r["spans"] for r in ocr_spans_records]

    normal_texts = [r["text_normalized"] for r in normal_inputs]
    normal_spans = [[] for _ in normal_inputs]

    all_seed_predictions = []
    checkpoint_shas = {}
    current_manifest_sha = sha256_file(MANIFEST_PATH)
    current_runner_sha = sha256_file(RUNNER_PATH)

    for seed in SEEDS:
        print(f"\n--- Processing Seed {seed} ---")
        seed_ckpt_path = PRIVATE_DIR / f"seed_{seed}_diagnostics.json"
        th = thresholds[seed]

        # Check if valid complete checkpoint already exists
        reuse_checkpoint = False
        if seed_ckpt_path.exists():
            try:
                ckpt_data = load_json(seed_ckpt_path)
                if (
                    ckpt_data.get("manifest_sha256") == current_manifest_sha
                    and ckpt_data.get("runner_sha256") == current_runner_sha
                    and ckpt_data.get("seed") == seed
                    and len(ckpt_data.get("records", [])) == 1904
                ):
                    print(f"[Seed {seed}] Reusing existing validated checkpoint at {seed_ckpt_path} (1904 records).")
                    seed_records = ckpt_data["records"]
                    validate_predictions(pd.DataFrame(seed_records), seeds=[seed])
                    all_seed_predictions.extend(seed_records)
                    checkpoint_shas[str(seed)] = sha256_file(seed_ckpt_path)
                    reuse_checkpoint = True
                else:
                    raise RuntimeError(f"Seed {seed} checkpoint exists but has mismatched hashes or incomplete records! Cannot overwrite.")
            except Exception as e:
                raise RuntimeError(f"Failed validating existing checkpoint for seed {seed}: {e}")

        if reuse_checkpoint:
            continue

        model_dir = SOURCE_MODEL_DIR / f"seed_{seed}/DUP/model"
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True).to(device).eval()

        # Step A: Baseline KISA Replay Verification on original128
        print(f"[Seed {seed}] Replaying KISA baseline controls on original128 (tolerance 1e-5)...")
        enc_base = tokenizer(kisa_texts, truncation=True, padding="max_length", max_length=128, return_tensors="pt")
        with torch.no_grad():
            logits_base = model(**{k: v.to(device) for k, v in enc_base.items()}).logits
            probs_base = torch.softmax(logits_base, dim=1)[:, 1].cpu().tolist()

        max_diff = 0.0
        mismatches = 0
        for i, r in enumerate(kisa_inputs):
            sha = r["primary_model_input_sha256"]
            saved_p = baseline_by_sha[sha][seed]["prob"]
            saved_dec = baseline_by_sha[sha][seed]["pred"]
            rec_p = probs_base[i]
            rec_dec = 1 if rec_p >= th else 0
            diff = abs(rec_p - saved_p)
            max_diff = max(max_diff, diff)
            if rec_dec != saved_dec:
                mismatches += 1

        if max_diff > 1e-5 or mismatches > 0:
            raise RuntimeError(f"Seed {seed} baseline KISA replay failed! max_diff={max_diff:.2e}, mismatches={mismatches}")
        print(f"[Seed {seed}] Baseline replay passed (max_diff={max_diff:.2e}, mismatches=0).")

        # Step B: Encode all 7 conditions for KISA and Normal
        kisa_variants = build_encodings(kisa_texts, kisa_spans, tokenizer)
        normal_variants = build_encodings(normal_texts, normal_spans, tokenizer)

        seed_records = []
        for cond in CONDITIONS:
            # 1. KISA inference (22 unique rows)
            enc_k = kisa_variants[cond]
            with torch.no_grad():
                logits_k = model(**{k: v.to(device) for k, v in enc_k.items()}).logits
                probs_k = torch.softmax(logits_k, dim=1)[:, 1].cpu().tolist()

            # 2. Normal inference (250 rows) in batches of 32
            enc_n = normal_variants[cond]
            probs_n = []
            with torch.no_grad():
                for b_start in range(0, len(normal_texts), 32):
                    b_enc = {k: v[b_start : b_start + 32].to(device) for k, v in enc_n.items()}
                    b_logits = model(**b_enc).logits
                    probs_n.extend(torch.softmax(b_logits, dim=1)[:, 1].cpu().tolist())

            # Store KISA records
            for i, r in enumerate(kisa_inputs):
                sha = r["primary_model_input_sha256"]
                b_prob = baseline_by_sha[sha][seed]["prob"]
                b_pred = baseline_by_sha[sha][seed]["pred"]
                p = probs_k[i]
                pred = 1 if p >= th else 0
                seed_records.append({
                    "row_id": f"kisa_{r['template_index']:02d}",
                    "cohort": "kisa_unique",
                    "condition": cond,
                    "seed": seed,
                    "source_id": sha,
                    "group_id": r["group_id"],
                    "is_group_representative": r["is_group_representative"],
                    "probability": p,
                    "prediction": pred,
                    "label": 1,
                    "threshold": th,
                    "baseline_probability": b_prob,
                    "baseline_prediction": b_pred,
                })

            # Store Normal records
            for i, r in enumerate(normal_inputs):
                cid = r["candidate_id"]
                p = probs_n[i]
                pred = 1 if p >= th else 0
                seed_records.append({
                    "row_id": f"normal_{cid}",
                    "cohort": "normal_candidates",
                    "condition": cond,
                    "seed": seed,
                    "source_id": cid,
                    "group_id": "none",
                    "is_group_representative": False,
                    "probability": p,
                    "prediction": pred,
                    "label": 0,
                    "threshold": th,
                    "baseline_probability": -1.0,
                    "baseline_prediction": -1,
                })

        # Backfill baseline for normal candidates from original128
        base_norm_map = {}
        for rec in seed_records:
            if rec["cohort"] == "normal_candidates" and rec["condition"] == "original128":
                base_norm_map[rec["row_id"]] = (rec["probability"], rec["prediction"])
        for rec in seed_records:
            if rec["cohort"] == "normal_candidates":
                bp, bd = base_norm_map[rec["row_id"]]
                rec["baseline_probability"] = bp
                rec["baseline_prediction"] = bd

        # Write atomic seed checkpoint binding hashes
        ckpt_payload = {
            "seed": seed,
            "manifest_sha256": current_manifest_sha,
            "runner_sha256": current_runner_sha,
            "total_records": len(seed_records),
            "records": seed_records,
        }
        save_private_json(seed_ckpt_path, ckpt_payload)
        checkpoint_shas[str(seed)] = sha256_file(seed_ckpt_path)
        print(f"[Seed {seed}] Checkpoint saved atomically at {seed_ckpt_path}")
        all_seed_predictions.extend(seed_records)

        # Free model memory after seed
        del model
        del tokenizer
        gc.collect()
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()

    # Compile and validate full predictions table
    df_all = pd.DataFrame(all_seed_predictions)
    print("\n[C2] Validating full predictions table (9520 rows)...")
    validate_predictions(df_all)

    # Save final predictions CSV
    df_all.to_csv(PREDICTIONS_CSV_PATH, index=False)
    os.chmod(PREDICTIONS_CSV_PATH, 0o600)
    print(f"[C2] Complete predictions written to {PREDICTIONS_CSV_PATH} ({len(df_all)} total prediction rows).")

    # Write run receipt
    receipt_data = {
        "version": VERSION,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "device": device,
        "seeds": SEEDS,
        "conditions": CONDITIONS,
        "total_prediction_rows": len(df_all),
        "manifest_sha256": current_manifest_sha,
        "acceptance_sha256": sha256_file(ACCEPTANCE_PATH),
        "runner_sha256": current_runner_sha,
        "checkpoint_sha256s": checkpoint_shas,
        "predictions_csv_sha256": sha256_file(PREDICTIONS_CSV_PATH),
    }
    save_private_json(RECEIPT_PATH, receipt_data)
    print(f"[C2] Run receipt saved at {RECEIPT_PATH}")

    # Render final reports
    render_reports()
    print("[C2] Inference and report rendering finished successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="KISA OCR Diagnostics & Normal Candidate Regression Pipeline")
    parser.add_argument("--check", action="store_true", help="Run read-only verification of frozen packages and models")
    parser.add_argument("--run", action="store_true", help="Execute diagnostic inference (requires Main acceptance)")
    parser.add_argument("--render", action="store_true", help="Render public JSON, Markdown, and CSV schema")
    args = parser.parse_args()

    if args.run:
        run_inference_guarded()
    elif args.render:
        render_reports()
    else:
        # Default or --check
        ok = check_pipeline()
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
