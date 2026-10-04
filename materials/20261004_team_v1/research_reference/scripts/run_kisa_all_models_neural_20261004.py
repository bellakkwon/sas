#!/usr/bin/env python3
"""Run and verify KISA All-Models Neural Diagnostic (20261004_v1).

Scope & Boundaries:
- Evaluates 9-fold one-example fine-tuning across all 27 saved KcBERT checkpoints.
- Adheres strictly to ScamLens Codex and AGENTS.md:
  * Zero external network access, URL navigation, or external API calls.
  * Library offline settings enforced (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1).
  * Zero raw text, PII, phone numbers, or private paths in public outputs.
  * Comprehensive source binding and drift prevention:
    - Verifies current runner, plan, all 27 models' source files, and threshold reports against prepare_manifest.
    - Verified BEFORE importing torch/transformers and executing models.
    - Re-verified after each model execution to ensure original source weights are untouched.
  * Mandated u5_DUP_s42 baseline replay:
    - Verified against prior seed 42 reference across all 272 decisions with tolerance <= 1e-5.
    - Prior reference path and hash bound in prepare_manifest.
  * Model-specific baseline miss denominators:
    - Common-other-eight detection is NOT recovery; recovery counts baseline 0 -> 1 transitions only.
    - Support example (1): reported separately, strictly excluded from recovery and retention.
    - Model-specific held-out misses: baseline misses excluding support.
    - Model-specific retention: baseline detections excluding support.
    - Normal regression: 250 normal candidates transition tracking.
  * Atomic exclusive writes and interrupted run fail-fast:
    - Baseline, fold checkpoints, and completion receipts written atomically with refuse-existing check.
    - Partial/interrupted runs detected and failed immediately before training starts.
    - Per-model resume reuses fully validated checkpoints.
  * Fold diagnostics:
    - Final state SHA256, parameter delta L2 norm from CPU immutable cache, finite training losses (1..10).
    - Clean optimizer deletion before memory garbage collection.
  * --check mode:
    - Binds every fold record's baseline predictions to baseline_predictions.json and validates IDs.
    - Detects baseline row tampering, non-finite values, and metric drift without loading torch model weights.
    - Full check requires all 27 models completed and verified.
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

# Enforce offline library behavior
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN_PATH = PROJECT_ROOT / "docs/experiments/KISA_ALL_MODELS_NEURAL_PLAN_20261004.json"
DEFAULT_PRIVATE_ROOT = Path.home() / "scamlens_private"
DEFAULT_PUBLIC_JSON = PROJECT_ROOT / "reports/generated/kisa_all_models_neural_20261004.json"
DEFAULT_PUBLIC_MD = PROJECT_ROOT / "docs/KISA_ALL_MODELS_NEURAL_RESULT_20261004.md"


def sha256_file(path: Path) -> str:
    """Compute SHA256 of file in 64KB chunks."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_text(text: str) -> str:
    """Compute SHA256 of string encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_state_dict(state_dict: dict[str, Any]) -> str:
    """Compute deterministic SHA256 of a model state_dict by sorted parameter names."""
    hasher = hashlib.sha256()
    for key in sorted(state_dict.keys()):
        val = state_dict[key]
        hasher.update(key.encode("utf-8"))
        if hasattr(val, "detach"):
            t = val.detach().cpu()
            hasher.update(str(t.dtype).encode("utf-8"))
            hasher.update(str(list(t.shape)).encode("utf-8"))
            hasher.update(t.numpy().tobytes())
        else:
            hasher.update(str(val).encode("utf-8"))
    return hasher.hexdigest()


def ensure_private_dir(path: Path) -> None:
    """Create directory with 0700 permissions."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def ensure_private_file(path: Path) -> None:
    """Set file permissions to 0600 if it exists."""
    if path.exists():
        os.chmod(path, 0o600)


def atomic_exclusive_private_json(path: Path, data: Any) -> None:
    """Atomically write JSON with mode 0600, refusing if target file already exists."""
    if path.exists():
        raise FileExistsError(f"Target file already exists: {path}. Overwriting is strictly forbidden.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".tmp_{path.name}_{os.getpid()}_{datetime.now(timezone.utc).timestamp()}"
    content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(tmp_path), flags, 0o600)
    try:
        os.write(fd, content)
        os.fsync(fd)
    finally:
        os.close(fd)
    if path.exists():
        try:
            tmp_path.unlink()
        except Exception:
            pass
        raise FileExistsError(f"Target file appeared concurrently: {path}")
    os.replace(str(tmp_path), str(path))
    os.chmod(path, 0o600)


def atomic_write_public_file(path: Path, content: str) -> None:
    """Atomically write public text file with 0644 permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".tmp_{path.name}_{os.getpid()}_{datetime.now(timezone.utc).timestamp()}"
    data = content.encode("utf-8")
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    fd = os.open(str(tmp_path), flags, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp_path), str(path))
    os.chmod(path, 0o644)


def load_json(path: Path) -> Any:
    """Load JSON file with UTF-8 encoding."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_path_safety(
    target_path: Path,
    allowed_roots: list[Path],
    label: str = "path",
) -> Path:
    """Ensure resolved target path does not escape allowed boundary roots."""
    resolved = target_path.resolve()
    for root in allowed_roots:
        resolved_root = root.resolve()
        try:
            resolved.relative_to(resolved_root)
            return resolved
        except ValueError:
            continue
    raise ValueError(
        f"Security violation: {label} ({target_path}) escapes allowed roots: "
        f"{[str(r) for r in allowed_roots]}"
    )


class FileLock:
    """Process execution lock for preventing concurrent runs."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.fd: int | None = None

    def acquire(self) -> None:
        if self.lock_path.exists():
            try:
                content = self.lock_path.read_text(encoding="utf-8")
            except Exception:
                content = "unknown"
            raise RuntimeError(
                f"Execution locked by existing lockfile: {self.lock_path} ({content.strip()}). "
                "Concurrent runs or incomplete cleanup detected."
            )
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(
            str(self.lock_path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        lock_info = (
            f"pid={os.getpid()} host={os.uname().nodename} "
            f"time={datetime.now(timezone.utc).isoformat()}\n"
        )
        os.write(self.fd, lock_info.encode("utf-8"))

    def release(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None
        if self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except Exception:
                pass

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


def resolve_model_dir(model_dir_str: str, private_root: Path, project_root: Path) -> Path:
    """Resolve model directory handling 'private:' alias or project relative paths."""
    if model_dir_str.startswith("private:"):
        rel = model_dir_str[len("private:"):]
        return (private_root / rel).resolve()
    return (project_root / model_dir_str).resolve()


def extract_threshold_from_report(report_path: Path, threshold_key: str) -> float:
    """Extract threshold from threshold source report according to key path."""
    data = load_json(report_path)
    if threshold_key == "validation_selected.threshold":
        return float(data["validation_selected"]["threshold"])
    elif threshold_key.startswith("arms."):
        parts = threshold_key.split(".")
        return float(data["arms"][parts[1]]["threshold"])
    elif "seeds[seed=" in threshold_key:
        parts = threshold_key.split(".")
        arm = parts[1]
        seed_str = threshold_key.split("[seed=")[1].split("]")[0]
        target_seed = int(seed_str)
        for s in data["arm_statistics"][arm]["seeds"]:
            if int(s["seed"]) == target_seed:
                return float(s["threshold"])
        raise KeyError(f"Seed {target_seed} not found in {threshold_key} ({report_path})")
    else:
        curr = data
        for part in threshold_key.split("."):
            curr = curr[part]
        return float(curr)


def load_plan(plan_path: Path) -> dict[str, Any]:
    """Load and validate the experiment plan JSON."""
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file missing: {plan_path}")
    plan = load_json(plan_path)

    required_keys = [
        "schema_version",
        "experiment_id",
        "private_root",
        "input_dir",
        "output_dir",
        "support_template_indices",
        "design",
        "models",
    ]
    for k in required_keys:
        if k not in plan:
            raise ValueError(f"Plan missing required field: {k}")

    if plan["schema_version"] != 1:
        raise ValueError(f"Unsupported plan schema_version: {plan['schema_version']}")

    if len(plan["models"]) != 27:
        raise ValueError(f"Expected 27 models in plan, found {len(plan['models'])}")

    expected_support = list(range(9))
    if plan["support_template_indices"] != expected_support:
        raise ValueError(
            f"support_template_indices mismatch: expected {expected_support}, got {plan['support_template_indices']}"
        )

    return plan


def check_singleton_support_groups(
    kisa_inputs: list[dict[str, Any]],
    support_case_indices: list[int],
) -> None:
    """Enforce group guard: each support group must contain only that support case among all 22."""
    group_counts: dict[str, list[int]] = {}
    for item in kisa_inputs:
        g = str(item.get("group_id", ""))
        group_counts.setdefault(g, []).append(item["template_index"])

    for s_idx in support_case_indices:
        item = next((it for it in kisa_inputs if it["template_index"] == s_idx), None)
        if item is None:
            raise ValueError(f"Support template index {s_idx} not found in kisa_inputs")
        g = str(item.get("group_id", ""))
        members = group_counts.get(g, [])
        if len(members) != 1:
            raise ValueError(
                f"Singleton group guard violated! Support case template_index={s_idx} "
                f"group_id={g!r} contains {len(members)} cases: {members} (expected strictly 1)"
            )


def check_encoded_input_guards(
    tokenizer: Any,
    kisa_inputs: list[dict[str, Any]],
    support_case_indices: list[int],
) -> None:
    """Verify before training that no support case encoded 128-token input equals any other KISA case."""
    encodings: dict[int, list[int]] = {}
    for it in kisa_inputs:
        ti = it["template_index"]
        txt = it["primary_model_input"]
        enc = tokenizer(txt, truncation=True, padding="max_length", max_length=128)
        encodings[ti] = list(enc["input_ids"])

    for s_idx in support_case_indices:
        s_tokens = encodings[s_idx]
        for other_idx, other_tokens in encodings.items():
            if s_idx != other_idx and s_tokens == other_tokens:
                raise ValueError(
                    f"Encoded input collision guard violated! Support case template_index={s_idx} "
                    f"shares identical 128-token encoded input with template_index={other_idx}."
                )


def locate_prior_baseline_reference(private_root: Path) -> tuple[Path, str]:
    """Locate the prior seed 42 baseline replay reference file and compute its SHA256."""
    p1 = private_root / "kisa_one_example_20261004_v1/seed_42_baseline_replay.json"
    if p1.exists():
        return p1, sha256_file(p1)
    p2 = private_root / "kisa_ocr_diagnostics_20260921_v1/predictions_diagnostics.csv"
    if p2.exists():
        return p2, sha256_file(p2)
    raise FileNotFoundError(
        f"Prior baseline reference not found in {private_root} (checked {p1} and {p2})"
    )


def load_prior_baseline_targets(
    prior_ref_path: Path,
    kisa_inputs: list[dict[str, Any]],
) -> tuple[dict[str, tuple[float, int]], dict[str, tuple[float, int]]]:
    """Load prior seed 42 target probabilities and predictions for KISA (22) and Normal (250)."""
    kisa_targets: dict[str, tuple[float, int]] = {}
    normal_targets: dict[str, tuple[float, int]] = {}

    if prior_ref_path.name.endswith(".json"):
        doc = load_json(prior_ref_path)
        for r in doc.get("kisa_replay", []):
            ti = int(r["template_index"])
            cid = f"K{ti + 1:02d}"
            bp = float(r.get("baseline_prob", r["prob"]))
            bpred = int(r.get("baseline_pred", r["pred"]))
            kisa_targets[cid] = (bp, bpred)

        for r in doc.get("normal_replay", []):
            cid = r["candidate_id"]
            bp = float(r.get("baseline_prob", r["prob"]))
            bpred = int(r.get("baseline_pred", r["pred"]))
            normal_targets[cid] = (bp, bpred)
    else:
        import csv
        with open(prior_ref_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            kisa_sha_to_cid = {
                it["primary_model_input_sha256"]: f"K{it['template_index'] + 1:02d}"
                for it in kisa_inputs
            }
            for row in reader:
                if row.get("seed") == "42" and row.get("condition") == "original128":
                    p = float(row["probability"])
                    d = int(row["prediction"])
                    if row.get("cohort") == "kisa_unique":
                        cid = kisa_sha_to_cid.get(row["source_id"])
                        if cid:
                            kisa_targets[cid] = (p, d)
                    elif row.get("cohort") == "normal_candidates":
                        cid = row["source_id"]
                        normal_targets[cid] = (p, d)

    if len(kisa_targets) != 22 or len(normal_targets) != 250:
        raise ValueError(
            f"Failed to load complete 272 prior baseline targets from {prior_ref_path} "
            f"(KISA: {len(kisa_targets)}, Normal: {len(normal_targets)})"
        )
    return kisa_targets, normal_targets


class ModelResetter:
    """Manages immutable CPU state dict cache, RNG reset, and fresh optimizer creation."""

    def __init__(
        self,
        model: Any,
        device: Any,
        learning_rate: float = 2e-5,
        weight_decay: float = 0.01,
        seed: int = 42,
    ):
        self.device = device
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.seed = seed
        self.model = model
        # Immutable CPU state dict cache: clone every tensor to CPU memory
        self.cpu_state_cache = {
            k: v.clone().detach().cpu()
            for k, v in model.state_dict().items()
        }

    def reset_rng(self) -> None:
        """Reset all RNG seeds to 42."""
        import random
        import numpy as np
        import torch

        random.seed(self.seed)
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(self.seed)
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.manual_seed(self.seed)

    def reset(self) -> tuple[Any, Any]:
        """Restore model weights to exact original CPU cache, reset RNG, and create fresh AdamW."""
        import torch

        restored_state = {k: v.clone().to(self.device) for k, v in self.cpu_state_cache.items()}
        self.model.load_state_dict(restored_state)
        self.model.to(self.device)
        self.reset_rng()
        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.learning_rate,
            weight_decay=self.weight_decay,
        )
        return self.model, optimizer


def compute_param_delta_l2_norm(model: Any, orig_cpu_cache: dict[str, Any]) -> float:
    """Compute exact parameter displacement L2 norm from original CPU weights."""
    import torch
    sq_sum = 0.0
    with torch.no_grad():
        for name, param in model.state_dict().items():
            orig_p = orig_cpu_cache[name]
            delta = param.detach().cpu().float() - orig_p.float()
            sq_sum += float(torch.sum(delta * delta).item())
    norm = math.sqrt(sq_sum)
    if not math.isfinite(norm):
        raise ValueError(f"Non-finite parameter delta L2 norm: {norm}")
    return norm


def recompute_model_fold_metrics(
    support_case_id: str,
    kisa_records: list[dict[str, Any]],
    normal_records: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    """Pure, independent recomputation of metrics for one evaluation step with strict validation.

    Critical Rules:
    - Support case is reported separately and strictly EXCLUDED from recovery and retention.
    - Models differ in baseline misses: recovery counts baseline 0 -> 1 transitions only.
    - Common-other-eight detection is NOT recovery; both are tracked distinctly.
    - Zero denominators return rate: None (represented as null in JSON).
    """
    if support_case_id not in [f"K{i:02d}" for i in range(1, 10)]:
        raise ValueError(f"Invalid support_case_id: {support_case_id} (expected K01..K09)")

    # 1. Validate KISA records
    if len(kisa_records) != 22:
        raise ValueError(f"Expected exactly 22 KISA records, got {len(kisa_records)}")

    kisa_ids = [r.get("case_id") for r in kisa_records]
    if len(set(kisa_ids)) != 22 or set(kisa_ids) != {f"K{i:02d}" for i in range(1, 23)}:
        raise ValueError(f"KISA records must contain distinct K01..K22, got: {kisa_ids}")

    template_indices = [r.get("template_index") for r in kisa_records]
    if set(template_indices) != set(range(22)):
        raise ValueError(f"KISA template indices not 0..21: {template_indices}")

    for r in kisa_records:
        cid = r["case_id"]
        p = float(r["prob"])
        bp = float(r["baseline_prob"])
        pred = int(r["pred"])
        bpred = int(r["baseline_pred"])

        if not math.isfinite(p) or not (0.0 <= p <= 1.0):
            raise ValueError(f"KISA record {cid} probability not finite in [0, 1]: {p}")
        if not math.isfinite(bp) or not (0.0 <= bp <= 1.0):
            raise ValueError(f"KISA record {cid} baseline probability not finite in [0, 1]: {bp}")

        exp_pred = 1 if p >= threshold else 0
        if pred != exp_pred:
            raise ValueError(f"KISA record {cid} prediction incoherence: pred={pred} vs exp={exp_pred}")

        exp_bpred = 1 if bp >= threshold else 0
        if bpred != exp_bpred:
            raise ValueError(f"KISA record {cid} baseline prediction incoherence: bpred={bpred} vs exp={exp_bpred}")

    # 2. Validate Normal records
    if len(normal_records) != 250:
        raise ValueError(f"Expected exactly 250 normal records, got {len(normal_records)}")

    norm_cids = [r.get("candidate_id") for r in normal_records]
    if len(set(norm_cids)) != 250:
        raise ValueError("Duplicate candidate_ids found in normal records")

    for r in normal_records:
        cid = r["candidate_id"]
        p = float(r["prob"])
        bp = float(r["baseline_prob"])
        pred = int(r["pred"])
        bpred = int(r["baseline_pred"])

        if not math.isfinite(p) or not (0.0 <= p <= 1.0):
            raise ValueError(f"Normal record {cid} probability not finite in [0, 1]: {p}")
        if not math.isfinite(bp) or not (0.0 <= bp <= 1.0):
            raise ValueError(f"Normal record {cid} baseline probability not finite in [0, 1]: {bp}")

        exp_pred = 1 if p >= threshold else 0
        if pred != exp_pred:
            raise ValueError(f"Normal record {cid} prediction incoherence: pred={pred} vs exp={exp_pred}")

        exp_bpred = 1 if bp >= threshold else 0
        if bpred != exp_bpred:
            raise ValueError(f"Normal record {cid} baseline prediction incoherence: bpred={bpred} vs exp={exp_bpred}")

    kisa_by_id = {r["case_id"]: r for r in kisa_records}

    # 1. Support case (reported separately, excluded from recovery)
    support_rec = kisa_by_id[support_case_id]
    s_prob = float(support_rec["prob"])
    s_pred = 1 if s_prob >= threshold else 0
    s_learned = s_pred == 1

    # 2. Held-out cases (the other 21 cases)
    held_out_recs = [r for r in kisa_records if r["case_id"] != support_case_id]
    assert len(held_out_recs) == 21, f"Expected 21 held-out cases, got {len(held_out_recs)}"

    # Model-specific baseline misses (where baseline_pred == 0)
    baseline_miss_recs = [r for r in held_out_recs if r["baseline_pred"] == 0]
    denom_misses = len(baseline_miss_recs)
    recovered_recs = [r for r in baseline_miss_recs if r["pred"] == 1]
    recovered_count = len(recovered_recs)
    recovery_rate = (recovered_count / denom_misses) if denom_misses > 0 else None
    recovered_cases = sorted([r["case_id"] for r in recovered_recs])
    remaining_miss_cases = sorted([r["case_id"] for r in baseline_miss_recs if r["pred"] == 0])

    # Model-specific baseline detections / retention (where baseline_pred == 1)
    baseline_det_recs = [r for r in held_out_recs if r["baseline_pred"] == 1]
    denom_retention = len(baseline_det_recs)
    retained_recs = [r for r in baseline_det_recs if r["pred"] == 1]
    retained_count = len(retained_recs)
    retention_rate = (retained_count / denom_retention) if denom_retention > 0 else None
    newly_missed_recs = [r for r in baseline_det_recs if r["pred"] == 0]
    newly_missed_count = len(newly_missed_recs)
    newly_missed_cases = sorted([r["case_id"] for r in newly_missed_recs])

    # Common other eight (cases in K01..K09 excluding support)
    common_eight_recs = [
        r for r in kisa_records
        if r["case_id"] in [f"K{i+1:02d}" for i in range(9)] and r["case_id"] != support_case_id
    ]
    assert len(common_eight_recs) == 8, f"Expected 8 common cases, got {len(common_eight_recs)}"
    common_eight_detected = sorted([r["case_id"] for r in common_eight_recs if r["pred"] == 1])
    common_eight_baseline_detected = sorted([r["case_id"] for r in common_eight_recs if r["baseline_pred"] == 1])
    common_eight_recovered = sorted([
        r["case_id"] for r in common_eight_recs
        if r["baseline_pred"] == 0 and r["pred"] == 1
    ])

    # Descriptive totals
    total_detected_21 = sum(1 for r in held_out_recs if r["pred"] == 1)
    total_detected_22 = sum(1 for r in kisa_records if r["pred"] == 1)
    total_misses_22 = sum(1 for r in kisa_records if r["pred"] == 0)
    remaining_misses_22 = sorted([r["case_id"] for r in kisa_records if r["pred"] == 0])

    # Normal regression (denominator 250)
    baseline_normal_alerts = sum(1 for r in normal_records if r["baseline_pred"] == 1)
    total_normal_alerts = sum(1 for r in normal_records if r["pred"] == 1)
    new_normal_alerts = sum(1 for r in normal_records if r["baseline_pred"] == 0 and r["pred"] == 1)
    resolved_normal_alerts = sum(1 for r in normal_records if r["baseline_pred"] == 1 and r["pred"] == 0)
    net_alert_change = total_normal_alerts - baseline_normal_alerts

    # Verdicts
    any_held_out_recovery = recovered_count > 0
    all_held_out_recovery = (recovered_count == denom_misses) if denom_misses > 0 else False
    clean_recovery = any_held_out_recovery and (newly_missed_count == 0) and (new_normal_alerts == 0)

    return {
        "support": {
            "case_id": support_case_id,
            "baseline_prob": float(support_rec["baseline_prob"]),
            "baseline_pred": int(support_rec["baseline_pred"]),
            "adapted_prob": s_prob,
            "adapted_pred": s_pred,
            "learned": s_learned,
        },
        "held_out_baseline_misses": {
            "denominator": denom_misses,
            "recovered_count": recovered_count,
            "recovery_rate": recovery_rate,
            "recovered_cases": recovered_cases,
            "remaining_miss_cases": remaining_miss_cases,
        },
        "retention": {
            "denominator": denom_retention,
            "retained_count": retained_count,
            "retention_rate": retention_rate,
            "newly_missed_count": newly_missed_count,
            "newly_missed_cases": newly_missed_cases,
        },
        "common_other_eight": {
            "denominator": 8,
            "detected_count": len(common_eight_detected),
            "detected_cases": common_eight_detected,
            "baseline_detected_count": len(common_eight_baseline_detected),
            "recovered_count": len(common_eight_recovered),
            "recovered_cases": common_eight_recovered,
        },
        "summary_21_cases": {
            "denominator": 21,
            "detected_count": total_detected_21,
            "detected_rate": total_detected_21 / 21.0,
        },
        "summary_22_cases": {
            "denominator": 22,
            "detected_count": total_detected_22,
            "detected_rate": total_detected_22 / 22.0,
            "misses_count": total_misses_22,
            "remaining_misses": remaining_misses_22,
        },
        "normal_regression": {
            "denominator": 250,
            "baseline_alerts": baseline_normal_alerts,
            "total_alerts": total_normal_alerts,
            "new_alerts": new_normal_alerts,
            "resolved_alerts": resolved_normal_alerts,
            "net_alert_change": net_alert_change,
        },
        "verdicts": {
            "any_held_out_recovery": any_held_out_recovery,
            "all_held_out_recovery": all_held_out_recovery,
            "clean_recovery": clean_recovery,
        },
    }


def validate_all_inputs(
    plan: dict[str, Any],
    allowed_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate all source inputs, models existence, threshold reports, text hashes, and return metadata."""
    private_root = Path(plan["private_root"]).expanduser()
    if allowed_roots is None:
        allowed_roots = [private_root, PROJECT_ROOT]

    input_dir = private_root / plan["input_dir"]
    kisa_path = input_dir / "kisa_inputs.json"
    normal_path = input_dir / "normal_candidates.json"

    for p, desc in [(kisa_path, "kisa_inputs"), (normal_path, "normal_candidates")]:
        validate_path_safety(p, allowed_roots, desc)
        if not p.exists():
            raise FileNotFoundError(f"Missing required input {desc}: {p}")

    # Validate KISA inputs
    kisa_inputs = load_json(kisa_path)
    if len(kisa_inputs) != 22:
        raise ValueError(f"Expected 22 KISA inputs, found {len(kisa_inputs)}")

    template_indices = [it["template_index"] for it in kisa_inputs]
    if sorted(template_indices) != list(range(22)):
        raise ValueError(f"KISA template indices not 0..21: {template_indices}")

    for it in kisa_inputs:
        ti = it["template_index"]
        txt = it.get("primary_model_input", "")
        exp_sha = it.get("primary_model_input_sha256", "")
        act_sha = sha256_text(txt)
        if act_sha != exp_sha:
            raise ValueError(f"KISA template {ti} text hash mismatch: {act_sha} vs {exp_sha}")

    # Singleton group guard on support templates 0..8
    check_singleton_support_groups(kisa_inputs, list(range(9)))

    # Validate Normal inputs
    normal_inputs = load_json(normal_path)
    if len(normal_inputs) != 250:
        raise ValueError(f"Expected 250 normal candidates, found {len(normal_inputs)}")

    cids = set()
    for row in normal_inputs:
        cid = row["candidate_id"]
        if cid in cids:
            raise ValueError(f"Duplicate normal candidate_id: {cid}")
        cids.add(cid)
        if row.get("text_sha256") != sha256_text(row.get("text_normalized", "")):
            raise ValueError(f"Normal candidate {cid} text hash mismatch")

    # Validate all 27 models
    models_meta: dict[str, Any] = {}
    for m in plan["models"]:
        mid = m["id"]
        mdir = resolve_model_dir(m["model_dir"], private_root, PROJECT_ROOT)
        validate_path_safety(mdir, allowed_roots, f"model_dir {mid}")
        if not mdir.exists():
            raise FileNotFoundError(f"Model dir missing for {mid}: {mdir}")

        # Check model files
        mfiles = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"]
        mf_hashes = {}
        for mf in mfiles:
            mf_path = mdir / mf
            if not mf_path.exists():
                raise FileNotFoundError(f"Model file missing: {mf_path}")
            mf_hashes[mf] = sha256_file(mf_path)

        # Check threshold report
        tsrc = (PROJECT_ROOT / m["threshold_source"]).resolve()
        validate_path_safety(tsrc, allowed_roots, f"threshold_source {mid}")
        if not tsrc.exists():
            raise FileNotFoundError(f"Threshold source missing for {mid}: {tsrc}")
        extracted_th = extract_threshold_from_report(tsrc, m["threshold_key"])
        if abs(extracted_th - m["threshold"]) > 1e-12:
            raise ValueError(
                f"Threshold mismatch for {mid}: extracted {extracted_th} != plan {m['threshold']}"
            )

        models_meta[mid] = {
            "model_dir": str(mdir),
            "model_files": mf_hashes,
            "threshold_source": str(tsrc),
            "threshold_source_sha256": sha256_file(tsrc),
            "threshold": m["threshold"],
            "seed": m["seed"],
            "family": m["family"],
        }

    # Locate prior baseline reference for u5_DUP_s42
    prior_ref_path, prior_ref_sha = locate_prior_baseline_reference(private_root)

    return {
        "kisa_path": str(kisa_path),
        "kisa_sha256": sha256_file(kisa_path),
        "normal_path": str(normal_path),
        "normal_sha256": sha256_file(normal_path),
        "kisa_inputs": kisa_inputs,
        "normal_inputs": normal_inputs,
        "models": models_meta,
        "prior_baseline_reference_path": str(prior_ref_path),
        "prior_baseline_reference_sha256": prior_ref_sha,
    }


def prepare_diagnostic(
    plan_path: Path = DEFAULT_PLAN_PATH,
    allowed_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Execute preflight preparation, freeze hashes across all 27 models, and write prepare_manifest.json."""
    plan = load_plan(plan_path)
    private_root = Path(plan["private_root"]).expanduser()
    if allowed_roots is None:
        allowed_roots = [private_root, PROJECT_ROOT]

    output_dir = private_root / plan["output_dir"]
    validate_path_safety(output_dir, allowed_roots, "output_dir")
    ensure_private_dir(output_dir)

    manifest_path = output_dir / "prepare_manifest.json"
    if manifest_path.exists():
        raise RuntimeError(
            f"prepare_manifest.json already exists at {manifest_path}. "
            "Overwrites are strictly forbidden."
        )

    meta = validate_all_inputs(plan, allowed_roots=allowed_roots)
    runner_path = Path(__file__).resolve()

    manifest_data = {
        "schema_version": 1,
        "experiment_id": plan["experiment_id"],
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": sha256_file(plan_path),
        "runner_sha256": sha256_file(runner_path),
        "kisa_input_sha256": meta["kisa_sha256"],
        "normal_input_sha256": meta["normal_sha256"],
        "prior_baseline_reference_path": meta["prior_baseline_reference_path"],
        "prior_baseline_reference_sha256": meta["prior_baseline_reference_sha256"],
        "guards": {
            "kisa_count": 22,
            "normal_count": 250,
            "support_template_indices": plan["support_template_indices"],
            "models_count": len(plan["models"]),
            "singleton_support_groups": True,
        },
        "models": meta["models"],
    }

    atomic_exclusive_private_json(manifest_path, manifest_data)
    print(
        f"[PREPARE] Preparation complete. Manifest written to {manifest_path} "
        f"({len(plan['models'])} models verified)."
    )
    return manifest_data


def verify_source_integrity_against_prepare(
    prep_manifest: dict[str, Any],
    plan_path: Path,
    runner_path: Path,
    kisa_path: Path,
    normal_path: Path,
    models_to_check: list[dict[str, Any]],
    private_root: Path,
) -> None:
    """Strictly verify that all runner, plan, inputs, model files, and threshold reports match prepare manifest."""
    if sha256_file(runner_path) != prep_manifest.get("runner_sha256"):
        raise RuntimeError("Runner hash drift against prepare_manifest! Aborting.")
    if sha256_file(plan_path) != prep_manifest.get("plan_sha256"):
        raise RuntimeError("Plan hash drift against prepare_manifest! Aborting.")
    if sha256_file(kisa_path) != prep_manifest.get("kisa_input_sha256"):
        raise RuntimeError("KISA input hash drift against prepare_manifest! Aborting.")
    if sha256_file(normal_path) != prep_manifest.get("normal_input_sha256"):
        raise RuntimeError("Normal input hash drift against prepare_manifest! Aborting.")

    for m in models_to_check:
        mid = m["id"]
        m_prep = prep_manifest.get("models", {}).get(mid)
        if not m_prep:
            raise RuntimeError(f"Model {mid} missing in prepare_manifest! Aborting.")

        mdir = resolve_model_dir(m["model_dir"], private_root, PROJECT_ROOT)
        for mf, exp_sha in m_prep.get("model_files", {}).items():
            mf_path = mdir / mf
            if not mf_path.exists() or sha256_file(mf_path) != exp_sha:
                raise RuntimeError(f"Model file {mf} drift in {mid} against prepare_manifest! Aborting.")

        tsrc = (PROJECT_ROOT / m["threshold_source"]).resolve()
        if not tsrc.exists() or sha256_file(tsrc) != m_prep.get("threshold_source_sha256"):
            raise RuntimeError(f"Threshold report drift for {mid} against prepare_manifest! Aborting.")


def verify_model_completion(
    model_id: str,
    output_dir: Path,
    prep_manifest: dict[str, Any],
) -> tuple[bool, str, dict[str, Any] | None]:
    """Verify if a model has an atomic valid completion receipt and intact checkpoint files."""
    model_dir = output_dir / model_id
    receipt_path = model_dir / "completion_receipt.json"
    if not receipt_path.exists():
        return False, "completion_receipt.json missing", None

    try:
        receipt = load_json(receipt_path)
    except Exception as e:
        return False, f"corrupted receipt: {e}", None

    if receipt.get("schema_version") != 1 or receipt.get("status") != "completed":
        return False, "receipt schema or status invalid", None

    bound = receipt.get("bound_hashes", {})
    if bound.get("plan_sha256") != prep_manifest.get("plan_sha256"):
        return False, "plan_sha256 drift", None
    if bound.get("runner_sha256") != prep_manifest.get("runner_sha256"):
        return False, "runner_sha256 drift", None
    if bound.get("kisa_input_sha256") != prep_manifest.get("kisa_input_sha256"):
        return False, "kisa_input_sha256 drift", None
    if bound.get("normal_input_sha256") != prep_manifest.get("normal_input_sha256"):
        return False, "normal_input_sha256 drift", None

    m_prep = prep_manifest.get("models", {}).get(model_id, {})
    if bound.get("threshold_source_sha256") != m_prep.get("threshold_source_sha256"):
        return False, "threshold_source_sha256 drift", None
    if bound.get("model_files_sha256") != m_prep.get("model_files"):
        return False, "model_files_sha256 drift", None

    baseline_path = model_dir / "baseline_predictions.json"
    if not baseline_path.exists() or sha256_file(baseline_path) != receipt.get("baseline_sha256"):
        return False, "baseline_predictions.json missing or hash drift", None

    fold_shas = receipt.get("fold_hashes", {})
    expected_folds = [f"fold_K{i:02d}" for i in range(1, 10)]
    if sorted(list(fold_shas.keys())) != expected_folds:
        return False, f"fold_hashes keys mismatch: {list(fold_shas.keys())}", None

    for fid in expected_folds:
        f_path = model_dir / f"{fid}.json"
        if not f_path.exists():
            return False, f"fold checkpoint missing: {f_path}", None
        if sha256_file(f_path) != fold_shas[fid]:
            return False, f"fold checkpoint {fid} hash drift", None

    return True, "valid", receipt


def render_public_json(
    plan: dict[str, Any],
    models_summary: dict[str, Any],
    is_partial: bool = False,
) -> str:
    """Render deterministic public aggregate JSON string with strictly NO raw text, NO raw probabilities, NO private paths."""
    clean_models: dict[str, Any] = {}
    for mid, mdata in sorted(models_summary.items()):
        b = mdata["baseline"]
        folds_clean = []
        for fd in mdata["folds"]:
            steps_clean = {}
            for st in ["1", "5", "10"]:
                m = fd["steps"][st]["metrics"]
                steps_clean[st] = {
                    "support": {
                        "case_id": m["support"]["case_id"],
                        "baseline_decision": m["support"]["baseline_pred"],
                        "adapted_decision": m["support"]["adapted_pred"],
                        "learned": m["support"]["learned"],
                    },
                    "held_out_baseline_misses": {
                        "denominator": m["held_out_baseline_misses"]["denominator"],
                        "recovered_count": m["held_out_baseline_misses"]["recovered_count"],
                        "recovery_rate": m["held_out_baseline_misses"]["recovery_rate"],
                        "recovered_cases": m["held_out_baseline_misses"]["recovered_cases"],
                        "remaining_miss_cases": m["held_out_baseline_misses"]["remaining_miss_cases"],
                    },
                    "retention": {
                        "denominator": m["retention"]["denominator"],
                        "retained_count": m["retention"]["retained_count"],
                        "retention_rate": m["retention"]["retention_rate"],
                        "newly_missed_count": m["retention"]["newly_missed_count"],
                        "newly_missed_cases": m["retention"]["newly_missed_cases"],
                    },
                    "common_other_eight": {
                        "denominator": m["common_other_eight"]["denominator"],
                        "detected_count": m["common_other_eight"]["detected_count"],
                        "detected_cases": m["common_other_eight"]["detected_cases"],
                        "baseline_detected_count": m["common_other_eight"]["baseline_detected_count"],
                        "recovered_count": m["common_other_eight"]["recovered_count"],
                        "recovered_cases": m["common_other_eight"]["recovered_cases"],
                    },
                    "summary_21_cases": m["summary_21_cases"],
                    "summary_22_cases": m["summary_22_cases"],
                    "normal_regression": {
                        "denominator": m["normal_regression"]["denominator"],
                        "baseline_alerts": m["normal_regression"]["baseline_alerts"],
                        "total_alerts": m["normal_regression"]["total_alerts"],
                        "new_alerts": m["normal_regression"]["new_alerts"],
                        "resolved_alerts": m["normal_regression"]["resolved_alerts"],
                        "net_alert_change": m["normal_regression"]["net_alert_change"],
                    },
                    "verdicts": m["verdicts"],
                }
            folds_clean.append({
                "fold_id": fd["fold_id"],
                "support_case_id": fd["support_case_id"],
                "primary_step": 10,
                "param_delta_l2_norm": fd.get("param_delta_l2_norm", 0.0),
                "steps": steps_clean,
            })

        clean_models[mid] = {
            "model_id": mid,
            "family": mdata["family"],
            "seed": mdata["seed"],
            "threshold": mdata["threshold"],
            "baseline": {
                "kisa_detected": b["kisa_detected"],
                "kisa_misses": b["kisa_misses"],
                "normal_alerts": b["normal_alerts"],
                "decisions": b["decisions"],  # K01..K22 -> 0 or 1
            },
            "folds": folds_clean,
        }

    doc = {
        "schema_version": 1,
        "experiment_id": plan["experiment_id"],
        "plan_path": "docs/experiments/KISA_ALL_MODELS_NEURAL_PLAN_20261004.json",
        "role": plan["role"],
        "status": "partial" if is_partial else "completed",
        "partial": is_partial,
        "total_models_evaluated": len(clean_models),
        "total_models_planned": 27,
        "models": clean_models,
        "limitations": plan.get("limitations", []),
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def render_markdown_report(
    plan: dict[str, Any],
    models_summary: dict[str, Any],
    is_partial: bool = False,
) -> str:
    """Render comprehensive Korean Markdown report string."""
    lines = [
        "# KISA 전 모델(27개 체크포인트) 신경망 추가학습 사후 진단 종합 실측 보고서",
        "",
        f"> **실행 상태**: {'[주의] 부분 실행 (Partial)' if is_partial else '전체 완료 (Completed)'} | "
        f"평가 완료 모델: {len(models_summary)} / 27개",
        "",
        "## 1. 연구 목적 및 프로토콜",
        "",
        "- **연구 성격**: 사전에 보존된 27개 KcBERT 체크포인트 전수를 대상으로, 동일한 9개 KISA 지원 예제(K01~K09) 1건 추가학습(One-positive fine-tuning) 시의 전이 복구 및 부작용(정상 오탐 증가, 기존 탐지 망각)을 체계적으로 비교 진단합니다.",
        "- **사후 진단 원칙 (Post-hoc Diagnostic)**: 본 진단은 고정된 과거 체크포인트에 대한 사후 분석이며 독립 전향 평가셋이 아닙니다.",
        "- **분모 엄격 분리 원칙**:",
        "  1. **Support 예제 (1건)**: 자체 적합 여부만 기록하며, 전이 복구 분모에서 엄격히 제외됩니다.",
        "  2. **모델별 기준선 미탐 복구**: 모델마다 기준선 탐지 결과가 다르므로, 해당 모델의 기준선 미탐(baseline 0)이었던 사례가 1로 전환된 것만을 복구로 산정합니다.",
        "  3. **공통 8건 단순 탐지와 복구의 구분**: K01~K09 중 다른 8건이 이미 기준선에서 탐지되던 모델의 경우, 해당 건을 '복구'로 왜곡 산정하지 않고 단순 탐지와 실제 복구(0->1)를 엄격히 분리 표기합니다.",
        "  4. **기존 탐지 유지(Retention)**: 해당 모델의 기준선 탐지(baseline 1) 건 중 적응 후에도 유지되는 건수.",
        "  5. **정상 후보군 전이(Normal Regression)**: 250건 정상 후보군에 대한 신규 오탐 및 해소 추적.",
        "",
        "---",
        "",
        "## 2. 27개 모델별 기준선(Baseline) 성능 요약",
        "",
        "| 모델 ID | Family | Seed | 적용 임계값 | KISA 탐지 (/ 22) | KISA 미탐 (/ 22) | 정상 오탐 (/ 250) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    for mid, mdata in sorted(models_summary.items()):
        b = mdata["baseline"]
        lines.append(
            f"| `{mid}` | `{mdata['family']}` | {mdata['seed']} | `{mdata['threshold']:.4g}` | "
            f"{b['kisa_detected']}건 | {b['kisa_misses']}건 | {b['normal_alerts']}건 |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. 모델별 주 적응 결과 (Step 10 기준, 9개 Fold 평균 및 종합)",
        "",
        "| 모델 ID | 평균 복구율 (모델 미탐 기준) | 평균 유지율 (기존 탐지 기준) | 평균 정상 신규 오탐 | 무오류 완전 복구 Fold수 (/ 9) |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ])

    for mid, mdata in sorted(models_summary.items()):
        folds = mdata["folds"]
        rec_rates = []
        ret_rates = []
        new_fps = []
        clean_count = 0
        for fd in folds:
            s10 = fd["steps"]["10"]["metrics"]
            rr = s10["held_out_baseline_misses"]["recovery_rate"]
            if rr is not None:
                rec_rates.append(rr)
            rtr = s10["retention"]["retention_rate"]
            if rtr is not None:
                ret_rates.append(rtr)
            new_fps.append(s10["normal_regression"]["new_alerts"])
            if s10["verdicts"]["clean_recovery"]:
                clean_count += 1

        avg_rec = f"{sum(rec_rates)/len(rec_rates)*100:.1f}%" if rec_rates else "N/A"
        avg_ret = f"{sum(ret_rates)/len(ret_rates)*100:.1f}%" if ret_rates else "N/A"
        avg_fp = f"{sum(new_fps)/len(new_fps):.1f}건" if new_fps else "N/A"

        lines.append(
            f"| `{mid}` | {avg_rec} | {avg_ret} | {avg_fp} | {clean_count}개 |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. 방법론적 한계 및 보안 고지",
        "",
        "- **과거 모델 조건의 비균일성**: 각 모델은 연구 이력상 서로 다른 시기 및 데이터 세부 구성에서 도출되었으며 본 진단은 모델 간 공정 순위 매기기가 아닌 단일 예제 미세적응 취약성 진단입니다.",
        "- **반복 시드의 비독립성**: 동일한 KISA 22건과 250건 정상 후보군에 대한 반복 측정이며 독립 표본이 아닙니다.",
        "- **128 토큰 절단 한계**: 원문 SMS가 128 토큰을 초과하는 장문 케이스의 경우 고정 절단 조건이 유지되었습니다.",
        "- **비공개 및 개인정보 보호**: 본 보고서에는 어떠한 원천 SMS 텍스트, 개인정보, 계좌번호, 전화번호, 비공개 절대경로도 포함되지 않습니다.",
        "",
    ])

    return "\n".join(lines) + "\n"


def execute_single_model_run(
    model_spec: dict[str, Any],
    plan: dict[str, Any],
    meta: dict[str, Any],
    output_dir: Path,
    device: Any,
    plan_path: Path,
) -> dict[str, Any]:
    """Execute baseline evaluation and 9-fold fine-tuning for a single model."""
    import random
    import numpy as np
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    mid = model_spec["id"]
    model_dir = Path(meta["models"][mid]["model_dir"])
    threshold = model_spec["threshold"]
    private_model_dir = output_dir / mid

    # Guard: check for partial/interrupted run before starting
    receipt_path = private_model_dir / "completion_receipt.json"
    baseline_path = private_model_dir / "baseline_predictions.json"

    if private_model_dir.exists():
        existing_artifacts = [
            p for p in private_model_dir.iterdir()
            if not p.name.startswith(".") and p != receipt_path
        ]
        if existing_artifacts and not receipt_path.exists():
            raise RuntimeError(
                f"Partial or interrupted prior run detected in {private_model_dir}: "
                f"found existing files {[p.name for p in existing_artifacts]} without valid completion receipt. "
                f"Refusing to execute model {mid} to prevent inconsistent state. Clean up directory to re-run."
            )

    ensure_private_dir(private_model_dir)

    print(f"\n=======================================================")
    print(f"[MODEL RUN] Commencing model: {mid} (Threshold: {threshold})")
    print(f"=======================================================")

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    check_encoded_input_guards(tokenizer, meta["kisa_inputs"], list(range(9)))

    # Initial load of original model
    model = AutoModelForSequenceClassification.from_pretrained(
        str(model_dir), local_files_only=True
    ).to(device)

    # 1. Baseline Evaluation
    model.eval()
    kisa_texts = [it["primary_model_input"] for it in meta["kisa_inputs"]]
    norm_texts = [it["text_normalized"] for it in meta["normal_inputs"]]

    kisa_base_probs: list[float] = []
    with torch.no_grad():
        for i in range(0, len(kisa_texts), 16):
            b_enc = tokenizer(
                kisa_texts[i : i + 16],
                truncation=True,
                padding="max_length",
                max_length=128,
                return_tensors="pt",
            )
            b_enc = {k: v.to(device) for k, v in b_enc.items()}
            logits = model(**b_enc).logits
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
            kisa_base_probs.extend(probs)

    norm_base_probs: list[float] = []
    with torch.no_grad():
        for i in range(0, len(norm_texts), 16):
            b_enc = tokenizer(
                norm_texts[i : i + 16],
                truncation=True,
                padding="max_length",
                max_length=128,
                return_tensors="pt",
            )
            b_enc = {k: v.to(device) for k, v in b_enc.items()}
            logits = model(**b_enc).logits
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
            norm_base_probs.extend(probs)

    kisa_base_records = []
    kisa_detected_count = 0
    kisa_decisions = {}
    for i, it in enumerate(meta["kisa_inputs"]):
        cid = f"K{it['template_index'] + 1:02d}"
        p = kisa_base_probs[i]
        d = 1 if p >= threshold else 0
        if d == 1:
            kisa_detected_count += 1
        kisa_decisions[cid] = d
        kisa_base_records.append({
            "case_id": cid,
            "template_index": it["template_index"],
            "prob": p,
            "pred": d,
        })

    norm_base_records = []
    norm_alert_count = 0
    for i, it in enumerate(meta["normal_inputs"]):
        cid = it["candidate_id"]
        p = norm_base_probs[i]
        d = 1 if p >= threshold else 0
        if d == 1:
            norm_alert_count += 1
        norm_base_records.append({
            "candidate_id": cid,
            "prob": p,
            "pred": d,
        })

    baseline_data: dict[str, Any] = {
        "model_id": mid,
        "threshold": threshold,
        "kisa_detected": kisa_detected_count,
        "kisa_misses": len(meta["kisa_inputs"]) - kisa_detected_count,
        "normal_alerts": norm_alert_count,
        "decisions": kisa_decisions,
        "kisa_records": kisa_base_records,
        "normal_records": norm_base_records,
    }

    # Mandated baseline replay for u5_DUP_s42
    if mid == "u5_DUP_s42":
        prior_ref_path = Path(meta["prior_baseline_reference_path"])
        prior_kisa_targets, prior_norm_targets = load_prior_baseline_targets(
            prior_ref_path, meta["kisa_inputs"]
        )

        max_kisa_diff = 0.0
        kisa_mismatches = 0
        for r in kisa_base_records:
            cid = r["case_id"]
            exp_p, exp_d = prior_kisa_targets[cid]
            diff = abs(r["prob"] - exp_p)
            max_kisa_diff = max(max_kisa_diff, diff)
            if r["pred"] != exp_d:
                kisa_mismatches += 1

        max_norm_diff = 0.0
        norm_mismatches = 0
        for r in norm_base_records:
            cid = r["candidate_id"]
            exp_p, exp_d = prior_norm_targets[cid]
            diff = abs(r["prob"] - exp_p)
            max_norm_diff = max(max_norm_diff, diff)
            if r["pred"] != exp_d:
                norm_mismatches += 1

        passed_replay = (
            kisa_mismatches == 0
            and norm_mismatches == 0
            and max_kisa_diff <= 1e-5
            and max_norm_diff <= 1e-5
        )
        if not passed_replay:
            raise RuntimeError(
                f"Mandated u5_DUP_s42 baseline replay verification failed! "
                f"KISA mismatches={kisa_mismatches}, max_diff={max_kisa_diff:.2e}; "
                f"Normal mismatches={norm_mismatches}, max_diff={max_norm_diff:.2e}"
            )

        baseline_data["replay_verification"] = {
            "target_model": "u5_DUP_s42",
            "kisa_mismatches": kisa_mismatches,
            "kisa_max_diff": max_kisa_diff,
            "normal_mismatches": norm_mismatches,
            "normal_max_diff": max_norm_diff,
            "passed": True,
        }
        print(f"[REPLAY] u5_DUP_s42 baseline replay PASSED (KISA diff: {max_kisa_diff:.2e}, Normal diff: {max_norm_diff:.2e})")

    atomic_exclusive_private_json(baseline_path, baseline_data)

    # 2. Nine-Fold Fine-Tuning
    resetter = ModelResetter(
        model,
        device,
        learning_rate=plan["design"]["learning_rate"],
        weight_decay=plan["design"]["weight_decay"],
        seed=plan["design"]["seed_for_updates"],
    )

    folds_data = []
    fold_hashes = {}

    for s_idx in range(9):
        case_id = f"K{s_idx + 1:02d}"
        fold_id = f"fold_{case_id}"
        fold_ckpt_path = private_model_dir / f"{fold_id}.json"

        # Restore fresh model weights and new AdamW
        model, optimizer = resetter.reset()

        s_item = next(it for it in meta["kisa_inputs"] if it["template_index"] == s_idx)
        s_text = s_item["primary_model_input"]
        s_enc = tokenizer(
            s_text,
            truncation=True,
            padding="max_length",
            max_length=128,
            return_tensors="pt",
        )
        s_enc = {k: v.to(device) for k, v in s_enc.items()}
        s_label = torch.tensor([1], dtype=torch.long, device=device)

        step_data = {}
        training_losses = {}

        # 10 training update steps
        model.train()
        for update_step in range(1, 11):
            optimizer.zero_grad()
            outputs = model(**s_enc, labels=s_label)
            loss = outputs.loss
            loss_val = float(loss.item())
            if not math.isfinite(loss_val) or loss_val < 0.0:
                raise ValueError(f"Non-finite or invalid training loss at step {update_step}: {loss_val}")
            training_losses[str(update_step)] = loss_val
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                plan["design"]["gradient_clip_norm"],
            )
            optimizer.step()

            if update_step in [1, 5, 10]:
                model.eval()
                with torch.no_grad():
                    # Evaluate KISA
                    k_probs: list[float] = []
                    for i in range(0, len(kisa_texts), 16):
                        b_enc = tokenizer(
                            kisa_texts[i : i + 16],
                            truncation=True,
                            padding="max_length",
                            max_length=128,
                            return_tensors="pt",
                        )
                        b_enc = {k: v.to(device) for k, v in b_enc.items()}
                        k_probs.extend(
                            torch.softmax(model(**b_enc).logits, dim=1)[:, 1].cpu().tolist()
                        )

                    # Evaluate Normal
                    n_probs: list[float] = []
                    for i in range(0, len(norm_texts), 16):
                        b_enc = tokenizer(
                            norm_texts[i : i + 16],
                            truncation=True,
                            padding="max_length",
                            max_length=128,
                            return_tensors="pt",
                        )
                        b_enc = {k: v.to(device) for k, v in b_enc.items()}
                        n_probs.extend(
                            torch.softmax(model(**b_enc).logits, dim=1)[:, 1].cpu().tolist()
                        )

                k_step_records = []
                for i, it in enumerate(meta["kisa_inputs"]):
                    cid = f"K{it['template_index'] + 1:02d}"
                    p = k_probs[i]
                    bp = kisa_base_probs[i]
                    k_step_records.append({
                        "case_id": cid,
                        "template_index": it["template_index"],
                        "prob": p,
                        "pred": 1 if p >= threshold else 0,
                        "baseline_prob": bp,
                        "baseline_pred": 1 if bp >= threshold else 0,
                    })

                n_step_records = []
                for i, it in enumerate(meta["normal_inputs"]):
                    cid = it["candidate_id"]
                    p = n_probs[i]
                    bp = norm_base_probs[i]
                    n_step_records.append({
                        "candidate_id": cid,
                        "prob": p,
                        "pred": 1 if p >= threshold else 0,
                        "baseline_prob": bp,
                        "baseline_pred": 1 if bp >= threshold else 0,
                    })

                step_metrics = recompute_model_fold_metrics(
                    case_id,
                    k_step_records,
                    n_step_records,
                    threshold,
                )

                step_data[str(update_step)] = {
                    "metrics": step_metrics,
                    "kisa_records": k_step_records,
                    "normal_records": n_step_records,
                }

                model.train()

        # Compute SHA256 of final in-memory adapted state dict and L2 delta norm from immutable cache
        final_state_sha = sha256_state_dict(model.state_dict())
        param_delta_l2 = compute_param_delta_l2_norm(model, resetter.cpu_state_cache)

        fold_payload = {
            "fold_id": fold_id,
            "support_case_id": case_id,
            "support_template_index": s_idx,
            "support_group_id": s_item["group_id"],
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "training_losses": training_losses,
            "final_state_sha256": final_state_sha,
            "param_delta_l2_norm": param_delta_l2,
            "steps": step_data,
        }
        atomic_exclusive_private_json(fold_ckpt_path, fold_payload)
        fold_hashes[fold_id] = sha256_file(fold_ckpt_path)
        folds_data.append(fold_payload)

        # Progress per finished fold
        print(
            f"[{mid}/{case_id}] Finished {fold_id} (Losses: step1={training_losses['1']:.4f}, "
            f"step5={training_losses['5']:.4f}, step10={training_losses['10']:.4f} | "
            f"Param Delta L2: {param_delta_l2:.4f})"
        )

        # Clean del optimizer before memory cleanup
        del optimizer

    # Free model GPU/MPS memory
    del model
    del tokenizer
    del resetter
    gc.collect()
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        torch.mps.empty_cache()

    # Write completion receipt atomically using bound plan hash
    receipt_data = {
        "schema_version": 1,
        "experiment_id": plan["experiment_id"],
        "model_id": mid,
        "family": model_spec["family"],
        "seed": model_spec["seed"],
        "threshold": threshold,
        "status": "completed",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "bound_hashes": {
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "plan_sha256": sha256_file(plan_path),
            "kisa_input_sha256": meta["kisa_sha256"],
            "normal_input_sha256": meta["normal_sha256"],
            "threshold_source_sha256": meta["models"][mid]["threshold_source_sha256"],
            "model_files_sha256": meta["models"][mid]["model_files"],
        },
        "baseline_sha256": sha256_file(baseline_path),
        "fold_hashes": fold_hashes,
    }
    atomic_exclusive_private_json(receipt_path, receipt_data)
    print(f"[MODEL RUN] Model {mid} completed successfully! Receipt: {receipt_path}")

    return {
        "model_id": mid,
        "family": model_spec["family"],
        "seed": model_spec["seed"],
        "threshold": threshold,
        "baseline": baseline_data,
        "folds": folds_data,
        "receipt": receipt_data,
    }


def run_experiment(
    plan_path: Path = DEFAULT_PLAN_PATH,
    model_id_filter: str | None = None,
    allowed_roots: list[Path] | None = None,
) -> None:
    """Execute sequential diagnostic runs across all 27 models (or filtered single model) with resume capability."""
    plan = load_plan(plan_path)
    private_root = Path(plan["private_root"]).expanduser()
    if allowed_roots is None:
        allowed_roots = [private_root, PROJECT_ROOT]

    output_dir = private_root / plan["output_dir"]
    validate_path_safety(output_dir, allowed_roots, "output_dir")
    ensure_private_dir(output_dir)

    manifest_path = output_dir / "prepare_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"prepare_manifest.json missing at {manifest_path}. "
            "run mode REQUIRES a successful prepare execution first."
        )
    prep_manifest = load_json(manifest_path)

    # 1. Comprehensive verification BEFORE importing torch/model
    runner_path = Path(__file__).resolve()
    input_dir = private_root / plan["input_dir"]
    kisa_path = input_dir / "kisa_inputs.json"
    normal_path = input_dir / "normal_candidates.json"

    models_to_run = plan["models"]
    if model_id_filter:
        models_to_run = [m for m in plan["models"] if m["id"] == model_id_filter]
        if not models_to_run:
            raise ValueError(f"Filter model_id {model_id_filter} not found in plan models.")

    verify_source_integrity_against_prepare(
        prep_manifest,
        plan_path,
        runner_path,
        kisa_path,
        normal_path,
        models_to_run,
        private_root,
    )

    meta = validate_all_inputs(plan, allowed_roots=allowed_roots)

    lock_path = output_dir / "execution.lock"

    with FileLock(lock_path):
        import torch

        # Device selection: MPS if available, else CPU
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = torch.device("mps")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")
        print(f"[RUN] Using device: {device} (PyTorch {torch.__version__})")

        all_models_summary: dict[str, Any] = {}

        # Collect already completed models
        for m in plan["models"]:
            mid = m["id"]
            is_valid, reason, receipt = verify_model_completion(mid, output_dir, prep_manifest)
            if is_valid:
                m_dir = output_dir / mid
                b_data = load_json(m_dir / "baseline_predictions.json")
                f_data = [load_json(m_dir / f"fold_K{i:02d}.json") for i in range(1, 10)]
                all_models_summary[mid] = {
                    "model_id": mid,
                    "family": m["family"],
                    "seed": m["seed"],
                    "threshold": m["threshold"],
                    "baseline": b_data,
                    "folds": f_data,
                    "receipt": receipt,
                }

        # Run models that need execution
        for m in models_to_run:
            mid = m["id"]
            if mid in all_models_summary:
                print(f"[RUN] Model {mid} is already completed and valid. Skipping execution.")
                continue

            # Per-model pre-execution verification
            verify_source_integrity_against_prepare(
                prep_manifest, plan_path, runner_path, kisa_path, normal_path, [m], private_root
            )

            summary = execute_single_model_run(m, plan, meta, output_dir, device, plan_path)
            all_models_summary[mid] = summary

            # Per-model post-execution verification: ensure original source files are untouched
            verify_source_integrity_against_prepare(
                prep_manifest, plan_path, runner_path, kisa_path, normal_path, [m], private_root
            )

            # Render updated reports after each completed model
            is_partial = len(all_models_summary) < len(plan["models"])
            pub_json_text = render_public_json(plan, all_models_summary, is_partial=is_partial)
            pub_md_text = render_markdown_report(plan, all_models_summary, is_partial=is_partial)
            atomic_write_public_file(DEFAULT_PUBLIC_JSON, pub_json_text)
            atomic_write_public_file(DEFAULT_PUBLIC_MD, pub_md_text)

        print("\n[RUN] Execution sequence finished.")


def check_pipeline(
    plan_path: Path = DEFAULT_PLAN_PATH,
    model_id_filter: str | None = None,
    allowed_roots: list[Path] | None = None,
) -> bool:
    """Verify stored diagnostic results via independent metric recomputation without torch model load."""
    if allowed_roots is None:
        allowed_roots = [DEFAULT_PRIVATE_ROOT, PROJECT_ROOT]

    errors: list[str] = []
    print("=== [KISA All-Models Neural Pipeline Check] ===")

    if not plan_path.exists():
        print(f"[FAIL] Plan file missing: {plan_path}")
        return False

    try:
        plan = load_plan(plan_path)
    except Exception as e:
        print(f"[FAIL] Plan loading/validation failed: {e}")
        return False

    private_root = Path(plan["private_root"]).expanduser()
    output_dir = private_root / plan["output_dir"]
    try:
        validate_path_safety(output_dir, allowed_roots, "output_dir")
    except Exception as e:
        print(f"[FAIL] Path safety check failed: {e}")
        return False

    manifest_path = output_dir / "prepare_manifest.json"
    if not manifest_path.exists():
        print(f"[FAIL] prepare_manifest.json missing at {output_dir}. Pipeline not prepared.")
        return False

    prep_manifest = load_json(manifest_path)
    runner_path = Path(__file__).resolve()

    input_dir = private_root / plan["input_dir"]
    kisa_path = input_dir / "kisa_inputs.json"
    normal_path = input_dir / "normal_candidates.json"

    models_to_check = plan["models"]
    if model_id_filter:
        models_to_check = [m for m in plan["models"] if m["id"] == model_id_filter]
        if not models_to_check:
            errors.append(f"Model {model_id_filter} not found in plan")

    # Comprehensive verification of all source files against prepare manifest
    try:
        verify_source_integrity_against_prepare(
            prep_manifest,
            plan_path,
            runner_path,
            kisa_path,
            normal_path,
            models_to_check,
            private_root,
        )
    except Exception as e:
        errors.append(str(e))

    # Load canonical input datasets to check ID sets
    try:
        kisa_inputs = load_json(kisa_path)
        normal_inputs = load_json(normal_path)
        canonical_kisa_cids = {f"K{it['template_index'] + 1:02d}" for it in kisa_inputs}
        canonical_norm_cids = {it["candidate_id"] for it in normal_inputs}
    except Exception as e:
        errors.append(f"Failed loading canonical inputs: {e}")
        canonical_kisa_cids = set()
        canonical_norm_cids = set()

    checked_models_summary: dict[str, Any] = {}

    for m in models_to_check:
        mid = m["id"]
        is_valid, reason, receipt = verify_model_completion(mid, output_dir, prep_manifest)
        if not is_valid:
            errors.append(f"Model {mid} completion verification failed: {reason}")
            continue

        m_dir = output_dir / mid
        b_data = load_json(m_dir / "baseline_predictions.json")
        f_data = [load_json(m_dir / f"fold_K{i:02d}.json") for i in range(1, 10)]

        # Recompute baseline summary and bind every baseline prediction by ID
        b_kisa = b_data.get("kisa_records", [])
        b_norm = b_data.get("normal_records", [])

        if len(b_kisa) != 22:
            errors.append(f"Model {mid} baseline kisa_records count: {len(b_kisa)} != 22")
        if len(b_norm) != 250:
            errors.append(f"Model {mid} baseline normal_records count: {len(b_norm)} != 250")

        # Check ID sets match canonical inputs
        b_kisa_cids = {r["case_id"] for r in b_kisa}
        b_norm_cids = {r["candidate_id"] for r in b_norm}
        if canonical_kisa_cids and b_kisa_cids != canonical_kisa_cids:
            errors.append(f"Model {mid} baseline KISA case IDs drift from canonical inputs")
        if canonical_norm_cids and b_norm_cids != canonical_norm_cids:
            errors.append(f"Model {mid} baseline normal candidate IDs drift from canonical inputs")

        # Recompute baseline summary
        th = m["threshold"]
        recomputed_kisa_det = sum(1 for r in b_kisa if r["pred"] == 1)
        recomputed_kisa_miss = len(b_kisa) - recomputed_kisa_det
        recomputed_norm_alert = sum(1 for r in b_norm if r["pred"] == 1)

        if recomputed_kisa_det != b_data.get("kisa_detected"):
            errors.append(f"Model {mid} baseline kisa_detected incoherence: {b_data.get('kisa_detected')} vs {recomputed_kisa_det}")
        if recomputed_kisa_miss != b_data.get("kisa_misses"):
            errors.append(f"Model {mid} baseline kisa_misses incoherence: {b_data.get('kisa_misses')} vs {recomputed_kisa_miss}")
        if recomputed_norm_alert != b_data.get("normal_alerts"):
            errors.append(f"Model {mid} baseline normal_alerts incoherence: {b_data.get('normal_alerts')} vs {recomputed_norm_alert}")

        # Build baseline lookup maps
        b_kisa_map = {r["case_id"]: (float(r["prob"]), int(r["pred"])) for r in b_kisa}
        b_norm_map = {r["candidate_id"]: (float(r["prob"]), int(r["pred"])) for r in b_norm}

        # Check mandated u5_DUP_s42 replay
        if mid == "u5_DUP_s42":
            replay_info = b_data.get("replay_verification", {})
            if not replay_info.get("passed"):
                errors.append("u5_DUP_s42 baseline replay verification missing or failed")
            if replay_info.get("kisa_max_diff", 1.0) > 1e-5 or replay_info.get("normal_max_diff", 1.0) > 1e-5:
                errors.append("u5_DUP_s42 baseline replay max diff exceeds tolerance 1e-5")

        # Verify exact nine support folds
        if len(f_data) != 9:
            errors.append(f"Model {mid} fold count: {len(f_data)} != 9")

        for idx, fd in enumerate(f_data):
            exp_case_id = f"K{idx + 1:02d}"
            exp_fold_id = f"fold_{exp_case_id}"
            if fd.get("fold_id") != exp_fold_id or fd.get("support_case_id") != exp_case_id:
                errors.append(f"Model {mid} fold identity mismatch at index {idx}: {fd.get('fold_id')}")
            if fd.get("support_template_index") != idx:
                errors.append(f"Model {mid} fold {exp_fold_id} template index mismatch: {fd.get('support_template_index')}")

            # Check training losses 1..10 finite
            losses = fd.get("training_losses", {})
            if sorted(list(losses.keys())) != [str(s) for s in range(1, 11)]:
                errors.append(f"Model {mid} {exp_fold_id} training_losses keys mismatch: {list(losses.keys())}")
            for l_step, l_val in losses.items():
                if not math.isfinite(float(l_val)) or float(l_val) < 0.0:
                    errors.append(f"Model {mid} {exp_fold_id} non-finite training loss at step {l_step}: {l_val}")

            # Check state hash shape (64 hex characters)
            sha = str(fd.get("final_state_sha256", ""))
            if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha.lower()):
                errors.append(f"Model {mid} {exp_fold_id} invalid final_state_sha256 shape: {sha}")

            # Check param delta l2 norm
            p_delta = fd.get("param_delta_l2_norm")
            if p_delta is None or not math.isfinite(float(p_delta)) or float(p_delta) < 0.0:
                errors.append(f"Model {mid} {exp_fold_id} invalid param_delta_l2_norm: {p_delta}")

            # Check steps: exactly 1, 5, 10
            steps = fd.get("steps", {})
            if sorted(list(steps.keys())) != ["1", "5", "10"]:
                errors.append(f"Model {mid} {exp_fold_id} steps mismatch: {list(steps.keys())}")

            for st in ["1", "5", "10"]:
                st_data = steps.get(st, {})
                k_recs = st_data.get("kisa_records", [])
                n_recs = st_data.get("normal_records", [])

                # Verify baseline prediction binding and detect tampering
                for kr in k_recs:
                    cid = kr.get("case_id")
                    if cid not in b_kisa_map:
                        errors.append(f"Model {mid} {exp_fold_id} step {st} unknown case_id {cid}")
                        continue
                    exp_bp, exp_bpred = b_kisa_map[cid]
                    if abs(float(kr.get("baseline_prob", 0.0)) - exp_bp) > 1e-12:
                        errors.append(f"Baseline probability tampering detected in model {mid} {exp_fold_id} step {st} case {cid}")
                    if int(kr.get("baseline_pred", -1)) != exp_bpred:
                        errors.append(f"Baseline decision tampering detected in model {mid} {exp_fold_id} step {st} case {cid}")

                for nr in n_recs:
                    cid = nr.get("candidate_id")
                    if cid not in b_norm_map:
                        errors.append(f"Model {mid} {exp_fold_id} step {st} unknown candidate_id {cid}")
                        continue
                    exp_bp, exp_bpred = b_norm_map[cid]
                    if abs(float(nr.get("baseline_prob", 0.0)) - exp_bp) > 1e-12:
                        errors.append(f"Baseline probability tampering detected in model {mid} {exp_fold_id} step {st} candidate {cid}")
                    if int(nr.get("baseline_pred", -1)) != exp_bpred:
                        errors.append(f"Baseline decision tampering detected in model {mid} {exp_fold_id} step {st} candidate {cid}")

                # Recompute metrics and compare
                recomputed = recompute_model_fold_metrics(exp_case_id, k_recs, n_recs, th)
                stored = st_data.get("metrics", {})

                for key in [
                    "support",
                    "held_out_baseline_misses",
                    "retention",
                    "common_other_eight",
                    "summary_21_cases",
                    "summary_22_cases",
                    "normal_regression",
                    "verdicts",
                ]:
                    if recomputed[key] != stored.get(key):
                        errors.append(f"Metric recomputation drift in model {mid} fold {exp_case_id} step {st} [{key}]")

        checked_models_summary[mid] = {
            "model_id": mid,
            "family": m["family"],
            "seed": m["seed"],
            "threshold": m["threshold"],
            "baseline": b_data,
            "folds": f_data,
            "receipt": receipt,
        }

    # Full check validation
    if not model_id_filter:
        if len(checked_models_summary) != 27:
            errors.append(
                f"Full check requires all 27 models, found {len(checked_models_summary)} completed"
            )

        if not DEFAULT_PUBLIC_JSON.exists():
            errors.append(f"Public JSON missing: {DEFAULT_PUBLIC_JSON}")
        else:
            exp_json = render_public_json(plan, checked_models_summary, is_partial=False)
            act_json = DEFAULT_PUBLIC_JSON.read_text(encoding="utf-8")
            if act_json != exp_json:
                errors.append("Public JSON differs from deterministic renderer")

            # Privacy checks
            parsed = json.loads(act_json)
            for m_key, m_val in parsed.get("models", {}).items():
                for f_entry in m_val.get("folds", []):
                    for st_k, st_v in f_entry.get("steps", {}).items():
                        if "adapted_prob" in st_v.get("support", {}):
                            errors.append(f"Raw probability leaked in public JSON support metrics: {m_key}")

        if not DEFAULT_PUBLIC_MD.exists():
            errors.append(f"Public Markdown missing: {DEFAULT_PUBLIC_MD}")
        else:
            exp_md = render_markdown_report(plan, checked_models_summary, is_partial=False)
            act_md = DEFAULT_PUBLIC_MD.read_text(encoding="utf-8")
            if act_md != exp_md:
                errors.append("Public Markdown differs from deterministic renderer")

        for pub_path in [DEFAULT_PUBLIC_JSON, DEFAULT_PUBLIC_MD]:
            if pub_path.exists():
                txt = pub_path.read_text(encoding="utf-8")
                if "scamlens_private" in txt or "/Users/" in txt:
                    errors.append(f"Private path found in public output: {pub_path}")

    ok = len(errors) == 0
    if ok:
        print(f"[PASS] All read-only checks passed ({len(checked_models_summary)} models verified).")
    else:
        print(f"[FAIL] Pipeline check failed with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run or check KISA All-Models Neural Diagnostic (20261004_v1)"
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["prepare", "run", "check"],
        default=None,
        help="Pipeline execution mode (prepare, run, or check)",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Execute preflight checks, freeze hashes for all 27 models, and write prepare_manifest",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute baseline and 9-fold fine-tuning for models and generate reports",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify stored artifacts and recompute metrics without model loading",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default=None,
        help="Optional model ID to run or check a specific model subset",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=DEFAULT_PLAN_PATH,
        help="Path to experiment plan JSON",
    )

    args = parser.parse_args()

    # Determine mode
    if args.prepare or args.mode == "prepare":
        prepare_diagnostic(plan_path=args.plan)
    elif args.run or args.mode == "run":
        run_experiment(plan_path=args.plan, model_id_filter=args.model_id)
    else:
        # Default or --check / check
        ok = check_pipeline(plan_path=args.plan, model_id_filter=args.model_id)
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
