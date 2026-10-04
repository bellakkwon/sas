#!/usr/bin/env python3
"""Run and verify KISA One-Example Adaptation Diagnostic (20261004_v1).

Scope & Boundaries:
- Evaluates nine-fold one-example fine-tuning on known KISA misses using frozen KC-BERT DUP model.
- Adheres strictly to ScamLens Codex and AGENTS.md:
  * Zero external network access, URL navigation, or external API calls.
  * Library offline settings enforced (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1).
  * Zero raw text, PII, phone numbers, or private paths in public outputs.
  * Frozen threshold, fixed optimizer (AdamW 2e-5, wd 0.01), 10 updates, steps [1, 5, 10].
  * Strictly separated denominators:
    - Support example (1): reported separately, excluded from held-out recovery.
    - Held-out misses (8): recovery count / 8.
    - Retention (13): originally detected KISA cases, new miss count / 13.
    - Normal regression (250): total alerts, new alerts, resolved alerts.
  * Baseline replay gate: 13/22 KISA, 11/250 normal, max probability diff <= 1e-5.
  * Exclusive private directory mode 0700 and private files mode 0600.
  * Safe path handling preventing boundary escape.
  * Public outputs contain only aggregate metrics and pseudonymous K01-K22 decisions (no probabilities, no normal IDs).
  * --check mode performs independent metric recomputation without loading torch model weights,
    verifying 7344 row probabilities, adapted model weights, baseline replay, and input hashes.
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

# Offline library settings
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN_PATH = PROJECT_ROOT / "docs/experiments/KISA_ONE_EXAMPLE_PLAN_20261004.json"
DEFAULT_PRIVATE_ROOT = Path.home() / "scamlens_private"


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


def ensure_private_dir(path: Path) -> None:
    """Create directory with 0700 permissions."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def ensure_private_file(path: Path) -> None:
    """Set file permissions to 0600 if it exists."""
    if path.exists():
        os.chmod(path, 0o600)


def save_exclusive_private_json(path: Path, data: Any) -> None:
    """Save data to JSON file with mode 0600, failing if file already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(path), flags, 0o600)
    try:
        os.write(fd, content)
    finally:
        os.close(fd)


def save_exclusive_public_file(path: Path, content: str) -> None:
    """Save public text file exclusively, failing if file already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(path), flags, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def load_json(path: Path) -> Any:
    """Load JSON file."""
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


def load_plan(plan_path: Path) -> dict[str, Any]:
    """Load and validate the experiment plan JSON."""
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file missing: {plan_path}")
    plan = load_json(plan_path)

    # Validate essential schema elements
    required_keys = [
        "version",
        "model_seed",
        "model_arm",
        "model_directory",
        "kisa_input_path",
        "normal_input_path",
        "saved_predictions_path",
        "threshold_report",
        "private_output_directory",
        "public_output",
        "report_output",
        "baseline",
        "design",
        "evaluation",
    ]
    for key in required_keys:
        if key not in plan:
            raise ValueError(f"Plan missing required field: {key}")

    if plan["model_seed"] != 42 or plan["model_arm"] != "DUP":
        raise ValueError(
            f"Unexpected model seed/arm: {plan['model_seed']}, {plan['model_arm']} (expected 42, DUP)"
        )

    b = plan["baseline"]
    if (
        b["kisa_n"] != 22
        or b["kisa_detected"] != 13
        or b["misses"] != 9
        or b["normal_n"] != 250
        or b["normal_alerts"] != 11
    ):
        raise ValueError(f"Baseline counts drift in plan: {b}")

    expected_support_ids = [f"K{i:02d}" for i in range(1, 10)]
    if plan["design"].get("support_case_ids") != expected_support_ids:
        raise ValueError(
            f"Plan support_case_ids mismatch: expected {expected_support_ids}, "
            f"got {plan['design'].get('support_case_ids')}"
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


def validate_input_datasets(
    plan: dict[str, Any],
    allowed_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate all source inputs, guards, text hashes, and return structured preflight metadata."""
    if allowed_roots is None:
        allowed_roots = [DEFAULT_PRIVATE_ROOT, PROJECT_ROOT]

    # Resolve paths
    model_dir = Path(plan["model_directory"])
    kisa_path = Path(plan["kisa_input_path"])
    normal_path = Path(plan["normal_input_path"])
    saved_pred_path = Path(plan["saved_predictions_path"])
    threshold_path = Path(plan["threshold_report"])
    if not threshold_path.is_absolute():
        threshold_path = PROJECT_ROOT / threshold_path

    # Check existence
    for p, desc in [
        (model_dir, "model_directory"),
        (kisa_path, "kisa_input_path"),
        (normal_path, "normal_input_path"),
        (saved_pred_path, "saved_predictions_path"),
        (threshold_path, "threshold_report"),
    ]:
        if not p.exists():
            raise FileNotFoundError(f"Missing required input {desc}: {p}")

    # Check model files
    expected_model_files = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"]
    model_hashes: dict[str, str] = {}
    for mf in expected_model_files:
        mf_path = model_dir / mf
        if not mf_path.exists():
            raise FileNotFoundError(f"Model file missing: {mf_path}")
        model_hashes[mf] = sha256_file(mf_path)

    # 1. KISA inputs validation
    kisa_inputs = load_json(kisa_path)
    if len(kisa_inputs) != 22:
        raise ValueError(f"Expected 22 KISA inputs, found {len(kisa_inputs)}")

    template_indices = [it["template_index"] for it in kisa_inputs]
    if sorted(template_indices) != list(range(22)):
        raise ValueError(f"KISA template indices not 0..21: {template_indices}")

    # Validate exact KISA text hashes
    for it in kisa_inputs:
        ti = it["template_index"]
        txt = it.get("primary_model_input", "")
        exp_sha = it.get("primary_model_input_sha256", "")
        act_sha = sha256_text(txt)
        if act_sha != exp_sha:
            raise ValueError(f"KISA template {ti} primary_model_input_sha256 mismatch: {act_sha} vs {exp_sha}")

    # Check baseline predictions for seed 42 in kisa_inputs
    kisa_miss_indices: list[int] = []
    kisa_detected_indices: list[int] = []
    for it in sorted(kisa_inputs, key=lambda x: x["template_index"]):
        ti = it["template_index"]
        b42 = it.get("baseline_predictions", {}).get("42")
        if not b42:
            raise ValueError(f"Missing baseline_predictions['42'] in KISA template {ti}")
        dec = int(b42["decision"])
        if dec == 0:
            kisa_miss_indices.append(ti)
        elif dec == 1:
            kisa_detected_indices.append(ti)
        else:
            raise ValueError(f"Invalid decision value {dec} in KISA template {ti}")

    if len(kisa_miss_indices) != 9:
        raise ValueError(f"Expected 9 KISA misses at seed 42, found {len(kisa_miss_indices)}")
    if len(kisa_detected_indices) != 13:
        raise ValueError(f"Expected 13 KISA detections at seed 42, found {len(kisa_detected_indices)}")

    # Verify EXACT support IDs match sorted misses (K01..K09)
    derived_support_ids = [f"K{ti + 1:02d}" for ti in sorted(kisa_miss_indices)]
    expected_support_ids = plan["design"]["support_case_ids"]
    if derived_support_ids != expected_support_ids:
        raise ValueError(
            f"Derived support IDs mismatch protocol: {derived_support_ids} vs {expected_support_ids}"
        )

    # Check singleton group guard
    check_singleton_support_groups(kisa_inputs, kisa_miss_indices)

    # 2. Normal inputs validation
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
            raise ValueError(f"Normal candidate {cid} text_sha256 mismatch")

    # 3. Saved predictions CSV validation
    saved_normal_alerts = 0
    saved_normal_count = 0
    saved_kisa_detections = 0
    saved_kisa_count = 0
    with open(saved_pred_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["seed"] == "42" and row["condition"] == "original128":
                if row["cohort"] == "normal_candidates":
                    saved_normal_count += 1
                    if int(row["prediction"]) == 1:
                        saved_normal_alerts += 1
                elif row["cohort"] == "kisa_unique":
                    saved_kisa_count += 1
                    if int(row["prediction"]) == 1:
                        saved_kisa_detections += 1

    if saved_normal_count != 250:
        raise ValueError(
            f"Saved predictions CSV normal count at seed 42 original128: {saved_normal_count} (expected 250)"
        )
    if saved_normal_alerts != 11:
        raise ValueError(
            f"Saved predictions CSV normal alerts at seed 42 original128: {saved_normal_alerts} (expected 11)"
        )
    if saved_kisa_count != 22:
        raise ValueError(
            f"Saved predictions CSV KISA count at seed 42 original128: {saved_kisa_count} (expected 22)"
        )
    if saved_kisa_detections != 13:
        raise ValueError(
            f"Saved predictions CSV KISA detections at seed 42 original128: {saved_kisa_detections} (expected 13)"
        )

    # 4. Threshold validation
    th_doc = load_json(threshold_path)
    th_val = None
    for s_info in th_doc.get("arm_statistics", {}).get("DUP", {}).get("seeds", []):
        if s_info.get("seed") == 42:
            th_val = float(s_info["threshold"])
            break
    if th_val is None or abs(th_val - plan["baseline"]["threshold"]) > 1e-12:
        raise ValueError(
            f"Threshold report mismatch: expected {plan['baseline']['threshold']}, found {th_val}"
        )

    return {
        "kisa_inputs": kisa_inputs,
        "kisa_miss_indices": kisa_miss_indices,
        "kisa_detected_indices": kisa_detected_indices,
        "normal_inputs": normal_inputs,
        "model_hashes": model_hashes,
        "threshold": th_val,
        "kisa_input_sha256": sha256_file(kisa_path),
        "normal_input_sha256": sha256_file(normal_path),
        "saved_predictions_sha256": sha256_file(saved_pred_path),
        "threshold_report_sha256": sha256_file(threshold_path),
    }


def prepare_diagnostic(
    plan_path: Path = DEFAULT_PLAN_PATH,
    allowed_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Execute preflight preparation, guards, and write immutable prepare_receipt.json exclusively."""
    if allowed_roots is None:
        allowed_roots = [DEFAULT_PRIVATE_ROOT, PROJECT_ROOT]

    plan = load_plan(plan_path)
    private_dir = Path(plan["private_output_directory"])
    validate_path_safety(private_dir, allowed_roots, "private_output_directory")
    ensure_private_dir(private_dir)

    receipt_path = private_dir / "prepare_receipt.json"
    if receipt_path.exists():
        raise RuntimeError(
            f"prepare_receipt.json already exists at {receipt_path}. "
            "Overwrites are strictly forbidden."
        )

    meta = validate_input_datasets(plan, allowed_roots=allowed_roots)
    runner_path = Path(__file__).resolve()

    receipt_data = {
        "schema_version": 1,
        "experiment_id": "kisa_one_example_20261004",
        "version": plan["version"],
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": sha256_file(plan_path),
        "runner_sha256": sha256_file(runner_path),
        "threshold_report_sha256": meta["threshold_report_sha256"],
        "threshold_seed42": meta["threshold"],
        "kisa_input_sha256": meta["kisa_input_sha256"],
        "normal_input_sha256": meta["normal_input_sha256"],
        "saved_predictions_sha256": meta["saved_predictions_sha256"],
        "model_files_sha256": meta["model_hashes"],
        "guards": {
            "kisa_count": 22,
            "kisa_misses_count": len(meta["kisa_miss_indices"]),
            "kisa_detected_count": len(meta["kisa_detected_indices"]),
            "normal_count": 250,
            "normal_baseline_alerts": 11,
            "support_case_ids": plan["design"]["support_case_ids"],
            "support_indices": meta["kisa_miss_indices"],
            "support_groups_are_singletons": True,
        },
    }

    save_exclusive_private_json(receipt_path, receipt_data)
    print(
        f"[PREPARE] Preparation complete. Receipt written to {receipt_path} "
        f"({len(meta['kisa_miss_indices'])} folds prepared, 250 normal guards verified)."
    )
    return receipt_data


def replay_baseline_gate(
    model: Any,
    tokenizer: Any,
    kisa_inputs: list[dict[str, Any]],
    normal_inputs: list[dict[str, Any]],
    saved_predictions_path: Path,
    threshold: float,
    device: Any,
) -> dict[str, Any]:
    """Execute baseline replay gate; requires exact decision equality and max diff <= 1e-5."""
    import torch

    model.eval()

    # 1. KISA Replay
    kisa_texts = [it["primary_model_input"] for it in kisa_inputs]
    kisa_probs: list[float] = []
    with torch.no_grad():
        for i in range(0, len(kisa_texts), 16):
            batch_texts = kisa_texts[i : i + 16]
            enc = tokenizer(
                batch_texts,
                truncation=True,
                padding="max_length",
                max_length=128,
                return_tensors="pt",
            )
            enc = {k: v.to(device) for k, v in enc.items()}
            logits = model(**enc).logits
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
            kisa_probs.extend(probs)

    # 2. Normal Replay
    normal_texts = [it["text_normalized"] for it in normal_inputs]
    normal_probs: list[float] = []
    with torch.no_grad():
        for i in range(0, len(normal_texts), 16):
            batch_texts = normal_texts[i : i + 16]
            enc = tokenizer(
                batch_texts,
                truncation=True,
                padding="max_length",
                max_length=128,
                return_tensors="pt",
            )
            enc = {k: v.to(device) for k, v in enc.items()}
            logits = model(**enc).logits
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
            normal_probs.extend(probs)

    # Load saved baseline targets from saved_predictions_path
    saved_normal: dict[str, tuple[float, int]] = {}
    saved_kisa: dict[str, tuple[float, int]] = {}
    with open(saved_predictions_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["seed"] == "42" and r["condition"] == "original128":
                if r["cohort"] == "normal_candidates":
                    saved_normal[r["source_id"]] = (float(r["probability"]), int(r["prediction"]))
                elif r["cohort"] == "kisa_unique":
                    saved_kisa[r["source_id"]] = (float(r["probability"]), int(r["prediction"]))

    # Check KISA diffs
    max_kisa_diff = 0.0
    kisa_mismatches = 0
    kisa_detected = 0
    kisa_replay_details = []
    for i, it in enumerate(kisa_inputs):
        sha = it["primary_model_input_sha256"]
        p = kisa_probs[i]
        d = 1 if p >= threshold else 0
        if d == 1:
            kisa_detected += 1

        b_entry = it.get("baseline_predictions", {}).get("42")
        exp_p = float(b_entry["probability"]) if b_entry else saved_kisa[sha][0]
        exp_d = int(b_entry["decision"]) if b_entry else saved_kisa[sha][1]

        diff = abs(p - exp_p)
        max_kisa_diff = max(max_kisa_diff, diff)
        if d != exp_d:
            kisa_mismatches += 1
        kisa_replay_details.append({
            "template_index": it["template_index"],
            "prob": p,
            "pred": d,
            "baseline_prob": exp_p,
            "baseline_pred": exp_d,
            "diff": diff,
        })

    # Check Normal diffs
    max_normal_diff = 0.0
    normal_mismatches = 0
    normal_alerts = 0
    normal_replay_details = []
    for i, it in enumerate(normal_inputs):
        cid = it["candidate_id"]
        p = normal_probs[i]
        d = 1 if p >= threshold else 0
        if d == 1:
            normal_alerts += 1
        exp_p, exp_d = saved_normal[cid]
        diff = abs(p - exp_p)
        max_normal_diff = max(max_normal_diff, diff)
        if d != exp_d:
            normal_mismatches += 1
        normal_replay_details.append({
            "candidate_id": cid,
            "prob": p,
            "pred": d,
            "baseline_prob": exp_p,
            "baseline_pred": exp_d,
            "diff": diff,
        })

    passed = (
        kisa_mismatches == 0
        and normal_mismatches == 0
        and max_kisa_diff <= 1e-5
        and max_normal_diff <= 1e-5
        and kisa_detected == 13
        and normal_alerts == 11
    )

    if not passed:
        raise RuntimeError(
            f"Baseline replay verification failed! KISA mismatches: {kisa_mismatches}, "
            f"Normal mismatches: {normal_mismatches}, KISA max diff: {max_kisa_diff:.2e}, "
            f"Normal max diff: {max_normal_diff:.2e}. Refusing execution."
        )

    return {
        "passed": True,
        "kisa_detected": kisa_detected,
        "kisa_misses": len(kisa_inputs) - kisa_detected,
        "kisa_max_diff": max_kisa_diff,
        "normal_alerts": normal_alerts,
        "normal_max_diff": max_normal_diff,
        "kisa_replay": kisa_replay_details,
        "normal_replay": normal_replay_details,
    }


def recompute_fold_metrics(
    support_case_id: str,
    kisa_records: list[dict[str, Any]],
    normal_records: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    """Pure, independent recomputation of metrics for one evaluation step with strict validation."""
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

        # Invariant: K01..K09 are baseline misses (bpred == 0), K10..K22 are detections (bpred == 1)
        case_num = int(cid[1:])
        expected_base_d = 0 if case_num <= 9 else 1
        if bpred != expected_base_d:
            raise ValueError(
                f"KISA record {cid} expected baseline decision {expected_base_d}, got {bpred}"
            )

    # 2. Validate Normal records
    if len(normal_records) != 250:
        raise ValueError(f"Expected exactly 250 normal records, got {len(normal_records)}")

    norm_cids = [r.get("candidate_id") for r in normal_records]
    if len(set(norm_cids)) != 250:
        raise ValueError("Duplicate candidate_ids found in normal records")

    norm_baseline_alerts = 0
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

        if bpred == 1:
            norm_baseline_alerts += 1

    if norm_baseline_alerts != 11:
        raise ValueError(
            f"Expected exactly 11 normal baseline alerts, found {norm_baseline_alerts}"
        )

    # Build maps
    kisa_by_id = {r["case_id"]: r for r in kisa_records}

    # 1. Support case
    support_rec = kisa_by_id[support_case_id]
    s_prob = float(support_rec["prob"])
    s_pred = 1 if s_prob >= threshold else 0
    s_learned = s_pred == 1

    # 2. Held-out misses (denominator = 8)
    held_out_ids = [f"K{i:02d}" for i in range(1, 10) if f"K{i:02d}" != support_case_id]
    assert len(held_out_ids) == 8, f"Held-out cases count error: {len(held_out_ids)}"

    held_out_recovered = 0
    recovered_cases: list[str] = []
    for cid in sorted(held_out_ids):
        r = kisa_by_id[cid]
        p = float(r["prob"])
        d = 1 if p >= threshold else 0
        if d == 1:
            held_out_recovered += 1
            recovered_cases.append(cid)

    # 3. Retention (denominator = 13)
    retention_ids = [f"K{i:02d}" for i in range(10, 23)]
    assert len(retention_ids) == 13, f"Retention cases count error: {len(retention_ids)}"

    retained_count = 0
    newly_missed_cases: list[str] = []
    for cid in sorted(retention_ids):
        r = kisa_by_id[cid]
        p = float(r["prob"])
        d = 1 if p >= threshold else 0
        if d == 1:
            retained_count += 1
        else:
            newly_missed_cases.append(cid)

    newly_missed_count = len(newly_missed_cases)

    # 4. Normal regression (denominator = 250)
    total_normal_alerts = 0
    new_normal_alerts = 0
    resolved_normal_alerts = 0

    for r in normal_records:
        d = int(r["pred"])
        bd = int(r["baseline_pred"])
        if d == 1:
            total_normal_alerts += 1
            if bd == 0:
                new_normal_alerts += 1
        else:
            if bd == 1:
                resolved_normal_alerts += 1

    net_alert_change = total_normal_alerts - 11

    # Descriptive totals
    total_detected_21 = held_out_recovered + retained_count
    total_detected_22 = (1 if s_learned else 0) + total_detected_21

    any_recovery = held_out_recovered > 0
    all_eight_recovery = held_out_recovered == 8
    clean_recovery = any_recovery and newly_missed_count == 0 and new_normal_alerts == 0

    return {
        "support": {
            "case_id": support_case_id,
            "baseline_prob": float(support_rec["baseline_prob"]),
            "baseline_pred": 0,
            "adapted_prob": s_prob,
            "adapted_pred": s_pred,
            "learned": s_learned,
        },
        "held_out_misses": {
            "denominator": 8,
            "recovered_count": held_out_recovered,
            "recovery_rate": held_out_recovered / 8.0,
            "recovered_cases": recovered_cases,
        },
        "retention": {
            "denominator": 13,
            "retained_count": retained_count,
            "retention_rate": retained_count / 13.0,
            "newly_missed_count": newly_missed_count,
            "newly_missed_cases": newly_missed_cases,
        },
        "normal_regression": {
            "denominator": 250,
            "baseline_alerts": 11,
            "total_alerts": total_normal_alerts,
            "new_alerts": new_normal_alerts,
            "resolved_alerts": resolved_normal_alerts,
            "net_alert_change": net_alert_change,
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
        },
        "verdicts": {
            "any_held_out_recovery": any_recovery,
            "all_eight_recovery": all_eight_recovery,
            "clean_recovery": clean_recovery,
        },
    }


def render_public_json(
    plan: dict[str, Any],
    folds_data: list[dict[str, Any]],
    baseline_info: dict[str, Any],
) -> str:
    """Render deterministic public aggregate JSON string with NO probabilities and NO normal IDs."""
    columns = [f"K{i:02d}" for i in range(1, 23)]
    baseline_decisions = {f"K{i:02d}": (0 if i <= 9 else 1) for i in range(1, 23)}

    primary_matrix: dict[str, dict[str, int]] = {}
    for fd in folds_data:
        fid = fd["fold_id"]
        step10_kisa = fd["steps"]["10"]["kisa_records"]
        dec_map = {r["case_id"]: (1 if r["prob"] >= plan["baseline"]["threshold"] else 0) for r in step10_kisa}
        primary_matrix[fid] = dec_map

    clean_folds_summary = []
    for fd in folds_data:
        steps_clean: dict[str, Any] = {}
        for st in ["1", "5", "10"]:
            m = fd["steps"][st]["metrics"]
            # Strictly strip probabilities and normal IDs
            steps_clean[st] = {
                "support": {
                    "case_id": m["support"]["case_id"],
                    "baseline_decision": m["support"]["baseline_pred"],
                    "adapted_decision": m["support"]["adapted_pred"],
                    "learned": m["support"]["learned"],
                },
                "held_out_misses": {
                    "denominator": m["held_out_misses"]["denominator"],
                    "recovered_count": m["held_out_misses"]["recovered_count"],
                    "recovery_rate": m["held_out_misses"]["recovery_rate"],
                    "recovered_cases": m["held_out_misses"]["recovered_cases"],
                },
                "retention": {
                    "denominator": m["retention"]["denominator"],
                    "retained_count": m["retention"]["retained_count"],
                    "retention_rate": m["retention"]["retention_rate"],
                    "newly_missed_count": m["retention"]["newly_missed_count"],
                    "newly_missed_cases": m["retention"]["newly_missed_cases"],
                },
                "normal_regression": {
                    "denominator": m["normal_regression"]["denominator"],
                    "baseline_alerts": m["normal_regression"]["baseline_alerts"],
                    "total_alerts": m["normal_regression"]["total_alerts"],
                    "new_alerts": m["normal_regression"]["new_alerts"],
                    "resolved_alerts": m["normal_regression"]["resolved_alerts"],
                    "net_alert_change": m["normal_regression"]["net_alert_change"],
                },
                "summary_21_cases": m["summary_21_cases"],
                "summary_22_cases": m["summary_22_cases"],
                "verdicts": m["verdicts"],
            }

        clean_folds_summary.append({
            "fold_id": fd["fold_id"],
            "support_case_id": fd["support_case_id"],
            "primary_step": 10,
            "steps": steps_clean,
        })

    any_rec_count = sum(1 for f in clean_folds_summary if f["steps"]["10"]["verdicts"]["any_held_out_recovery"])
    all_rec_count = sum(1 for f in clean_folds_summary if f["steps"]["10"]["verdicts"]["all_eight_recovery"])
    clean_rec_count = sum(1 for f in clean_folds_summary if f["steps"]["10"]["verdicts"]["clean_recovery"])

    doc = {
        "schema_version": 1,
        "experiment_id": "kisa_one_example_20261004",
        "version": plan["version"],
        "plan_path": "docs/experiments/KISA_ONE_EXAMPLE_PLAN_20261004.json",
        "role": plan["role"],
        "model_seed": plan["model_seed"],
        "model_arm": plan["model_arm"],
        "threshold": plan["baseline"]["threshold"],
        "baseline_summary": plan["baseline"],
        "baseline_replay": {
            "kisa_max_diff": baseline_info.get("kisa_max_diff", 0.0),
            "normal_max_diff": baseline_info.get("normal_max_diff", 0.0),
            "passed": True,
        },
        "folds": clean_folds_summary,
        "pseudonymous_matrix": {
            "columns": columns,
            "baseline_decisions": baseline_decisions,
            "primary_step10_decisions_by_fold": primary_matrix,
        },
        "overall_summary": {
            "total_folds": len(clean_folds_summary),
            "folds_with_any_recovery": any_rec_count,
            "folds_with_all_eight_recovery": all_rec_count,
            "folds_with_clean_recovery": clean_rec_count,
            "primary_step": 10,
            "trajectory_steps": [1, 5, 10],
        },
        "limitations": plan.get("limitations", []),
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def render_markdown_report(
    plan: dict[str, Any],
    folds_data: list[dict[str, Any]],
    baseline_info: dict[str, Any],
) -> str:
    """Render comprehensive Korean Markdown report string."""
    th = plan["baseline"]["threshold"]
    lines = [
        "# KISA 1건 추가학습(One-Example Adaptation) 사후 진단 실측 보고서",
        "",
        "## 1. 연구 목적 및 실험 프로토콜 개요",
        "",
        "- **연구 성격**: 9건의 알려진 KISA 미탐(FN) 사례 중 1건만을 선택하여 추가학습(Fine-tuning)했을 때, 다른 8건의 미탐 사례가 복구(Transfer)되는지 및 기존 탐지 결과(KISA 탐지 유지 및 정상 후보 오탐 증가)에 부작용이 발생하는지 측정하는 사후 진단(Post-hoc diagnostic) 연구입니다.",
        f"- **평가 모델**: KC-BERT {plan['model_arm']} Arm (Seed {plan['model_seed']})",
        f"- **적용 임계값**: `{th:.17g}` (Matched KC-BERT u5 Unused Test 동결 기준)",
        "- **학습 파라미터 및 하네스 조건**:",
        "  - 학습 예제: Fold당 단 1건의 미탐 사례 (Label=1, Replay 예제 0건, 증강 없음)",
        f"  - 옵티마이저: AdamW (lr={plan['design']['learning_rate']:.1e}, weight_decay={plan['design']['weight_decay']}, grad_clip={plan['design']['gradient_clip_norm']})",
        f"  - 스텝 스케줄: 총 {plan['design']['updates']}회 업데이트 (중간 측정: {plan['design']['checkpoint_steps']}, 주 판정 스텝: {plan['design']['primary_step']})",
        "  - 하드웨어 및 격리: Apple Silicon MPS 가속기 필수, 각 Fold 시작 시 원본 모델 재로드 및 Seed 42/옵티마이저 초기화",
        "",
        "---",
        "",
        "## 2. 기준선(Baseline Replay) 무결성 검증 결과",
        "",
        "학습 개시 전, 사전 동결된 22건의 KISA 평가문과 250건의 정상 후보군에 대해 원본 모델의 추론 결과를 전수 재현 검증하였습니다.",
        f"- **KISA 고유 22건**: 13건 탐지, 9건 미탐 (불일치 0건, 최대 확률 오차 `{baseline_info.get('kisa_max_diff', 0.0):.2e}` <= 1e-5)",
        f"- **정상 후보 250건**: 11건 오탐, 239건 정상 (불일치 0건, 최대 확률 오차 `{baseline_info.get('normal_max_diff', 0.0):.2e}` <= 1e-5)",
        "- **기준선 런타임 무결성 판정**: **통과 (Pass)**",
        "",
        "---",
        "",
        "## 3. 9개 Fold별 최종 주 성적표 (Step 10 기준)",
        "",
        "> **분모 원칙 및 지표 정의**:",
        "> 1. **Support (학습 예제, 1건)**: 자체 학습 적합 여부만 확인하며, 미탐 복구 분모에서 엄격히 제외됩니다.",
        "> 2. **Held-out 복구 (8건)**: 학습에 사용되지 않은 나머지 8건의 기존 미탐건 중 탐지로 전환된 건수 (`/ 8`).",
        "> 3. **기존 탐지 유지 (Retention, 13건)**: 기존에 탐지되던 13건 중 여전히 탐지되는 건수 (`/ 13`).",
        "> 4. **신규 미탐**: 기존 13건 중 탐지에 실패한 신규 오류 건수.",
        "> 5. **정상 신규 오탐**: 250건 정상 후보군 중 기존 정상에서 신규 오탐으로 돌아선 건수.",
        "",
        "| Fold ID | Support 예제 | 자체 학습 여부 | Held-out 복구 (/ 8) | 기존 탐지 유지 (/ 13) | 신규 미탐 발생 | 정상 신규 오탐 | 총 정상 알림 (기존: 11) | 단독 전이 판정 |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for fd in folds_data:
        fid = fd["fold_id"]
        sid = fd["support_case_id"]
        s10 = fd["steps"]["10"]["metrics"]
        s_res = "O (성공)" if s10["support"]["learned"] else "X (실패)"
        h_rec = f"{s10['held_out_misses']['recovered_count']}건 ({s10['held_out_misses']['recovery_rate']*100:.1f}%)"
        ret = f"{s10['retention']['retained_count']}건 ({s10['retention']['retention_rate']*100:.1f}%)"
        new_m = f"{s10['retention']['newly_missed_count']}건"
        new_fp = f"{s10['normal_regression']['new_alerts']}건"
        tot_fp = f"{s10['normal_regression']['total_alerts']}건"
        if s10["verdicts"]["clean_recovery"]:
            v = "**평가한 자료에서 새 오류 없이 회복**"
        elif s10["verdicts"]["any_held_out_recovery"]:
            v = "회복 관찰·새 오류 동반"
        else:
            v = "전이 실패 (0건 복구)"
        lines.append(
            f"| `{fid}` | `{sid}` | {s_res} | {h_rec} | {ret} | {new_m} | {new_fp} | {tot_fp} | {v} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. 학습 스텝별(1, 5, 10 Step) 궤적 분석",
        "",
        "체리피킹을 방지하기 위해 사전 선언된 전체 체크포인트 스텝(1, 5, 10)의 지표 추이를 전수 기록합니다.",
        "",
        "| Fold ID | 스텝 | Held-out 복구수 (/ 8) | KISA 유지수 (/ 13) | 신규 미탐수 | 정상 신규 오탐수 | 정상 총 알림수 |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for fd in folds_data:
        fid = fd["fold_id"]
        for st in ["1", "5", "10"]:
            sm = fd["steps"][st]["metrics"]
            lines.append(
                f"| `{fid}` | Step {st} | {sm['held_out_misses']['recovered_count']}건 | "
                f"{sm['retention']['retained_count']}건 | {sm['retention']['newly_missed_count']}건 | "
                f"{sm['normal_regression']['new_alerts']}건 | {sm['normal_regression']['total_alerts']}건 |"
            )

    lines.extend([
        "",
        "---",
        "",
        "## 5. K01~K22 익명화 전이 매트릭스 (Step 10 기준)",
        "",
        "본 매트릭스는 원문 SMS 본문 없이 익명화된 식별자(K01~K22)로 판정 상태를 나타냅니다.",
        "기호 설명: `[S]` = 해당 Fold 학습 예제, `O` = 탐지 성공 (TP), `X` = 미탐 (FN).",
        "",
        "| 케이스 ID | 기준선 (Seed 42) | "
        + " | ".join(f"`{fd['fold_id']}`" for fd in folds_data)
        + " |",
        "| :---: | :---: | " + " | ".join(":---:" for _ in folds_data) + " |",
    ])

    for i in range(1, 23):
        cid = f"K{i:02d}"
        base_dec = 0 if i <= 9 else 1
        base_str = "O" if base_dec == 1 else "X"
        row_cols = [f"`{cid}`", base_str]
        for fd in folds_data:
            sid = fd["support_case_id"]
            k_records = fd["steps"]["10"]["kisa_records"]
            rec = next(r for r in k_records if r["case_id"] == cid)
            d = 1 if rec["prob"] >= th else 0
            if cid == sid:
                c_str = f"**[S:{'O' if d == 1 else 'X'}]**"
            else:
                c_str = "O" if d == 1 else "X"
            row_cols.append(c_str)
        lines.append("| " + " | ".join(row_cols) + " |")

    lines.extend([
        "",
        "---",
        "",
        "## 6. 연구 방법론적 한계 및 보안 고지",
        "",
        "- **사후 진단 한계**: 본 연구의 9개 미탐 사례는 이미 기존 평가에서 오답으로 확인된 사례들을 사후적으로 다룬 것이며, 독립적인 전향 평가가 아닙니다.",
        "- **사전 관찰 편향**: 평가 대상 8건은 해당 Fold의 1건 업데이트에서는 배제되었으나, 프로젝트 전체 기준으로는 이미 관찰된 데이터입니다.",
        "- **토큰 절단(128토큰) 한계**: 9건의 미탐 메시지는 모두 원래 128토큰을 초과했던 장문 메시지이며, 본 진단에서는 기본 절단 조건을 유지했습니다.",
        "- **단일 레시피 및 시드 한계**: 단일 모델 시드(42) 및 고정된 학습 하이퍼파라미터(10 updates, lr=2e-5)에 한정된 결과이며, 다른 학습 조건에서의 가능성을 배제하지 않습니다.",
        "- **정상 후보군 라벨의 성격**: 250건의 정상 후보군은 개발용 원천 데이터를 포함하며, 실서비스 환경에서 완전히 무결하게 확정된 정상 SMS나 독립 FPR이 아닙니다.",
        "- **KISA 원천 라벨 한계**: KISA 자료의 레이블은 원천 신고 및 제공 기준의 스미싱 라벨이며, 독립적인 수사·사고 조사를 거친 것이 아닙니다.",
        "- **비공개 및 개인정보 보호**: 본 공개 문서에는 어떠한 원천 SMS 본문, 개인정보, 계좌/전화번호, 비공개 절대경로도 포함되지 않으며 오프라인 집계 결과만을 담고 있습니다.",
        "",
    ])

    return "\n".join(lines) + "\n"


def run_diagnostic_experiment(
    plan_path: Path = DEFAULT_PLAN_PATH,
    allowed_roots: list[Path] | None = None,
) -> None:
    """Execute complete 9-fold fine-tuning diagnostic guarded by prepare receipt and exclusive artifacts."""
    if allowed_roots is None:
        allowed_roots = [DEFAULT_PRIVATE_ROOT, PROJECT_ROOT]

    plan = load_plan(plan_path)
    private_dir = Path(plan["private_output_directory"])
    validate_path_safety(private_dir, allowed_roots, "private_output_directory")
    ensure_private_dir(private_dir)

    prepare_receipt_path = private_dir / "prepare_receipt.json"
    if not prepare_receipt_path.exists():
        raise FileNotFoundError(
            f"prepare_receipt.json missing at {prepare_receipt_path}. "
            "run mode REQUIRES a successful prepare execution first."
        )
    prep_data = load_json(prepare_receipt_path)

    runner_path = Path(__file__).resolve()
    threshold_path = Path(plan["threshold_report"])
    if not threshold_path.is_absolute():
        threshold_path = PROJECT_ROOT / threshold_path
    kisa_path = Path(plan["kisa_input_path"])
    normal_path = Path(plan["normal_input_path"])
    saved_pred_path = Path(plan["saved_predictions_path"])
    model_dir = Path(plan["model_directory"])

    # Strict check: verify frozen runner, plan, source, threshold, and model hashes BEFORE loading model
    if prep_data.get("runner_sha256") != sha256_file(runner_path):
        raise RuntimeError("Prepare receipt runner_sha256 drift before model load! Aborting.")
    if prep_data.get("plan_sha256") != sha256_file(plan_path):
        raise RuntimeError("Prepare receipt plan_sha256 drift before model load! Aborting.")
    if prep_data.get("threshold_report_sha256") != sha256_file(threshold_path):
        raise RuntimeError("Prepare receipt threshold_report_sha256 drift before model load! Aborting.")
    if prep_data.get("kisa_input_sha256") != sha256_file(kisa_path):
        raise RuntimeError("Prepare receipt kisa_input_sha256 drift before model load! Aborting.")
    if prep_data.get("normal_input_sha256") != sha256_file(normal_path):
        raise RuntimeError("Prepare receipt normal_input_sha256 drift before model load! Aborting.")
    if prep_data.get("saved_predictions_sha256") != sha256_file(saved_pred_path):
        raise RuntimeError("Prepare receipt saved_predictions_sha256 drift before model load! Aborting.")
    for mf, exp_sha in prep_data.get("model_files_sha256", {}).items():
        if sha256_file(model_dir / mf) != exp_sha:
            raise RuntimeError(f"Prepare receipt model file {mf} hash drift before model load! Aborting.")

    # Refuse any existing run-start marker or result artifacts before beginning
    run_start_path = private_dir / "run_start.json"
    run_receipt_path = private_dir / "run_receipt.json"
    pred_csv_path = private_dir / "private_predictions.csv"
    replay_path = private_dir / "seed_42_baseline_replay.json"

    existing_artifacts = [
        p for p in [run_start_path, run_receipt_path, pred_csv_path, replay_path] if p.exists()
    ]
    existing_folds = list(private_dir.glob("fold_K*.json"))
    existing_models = list(private_dir.glob("model_fold_K*"))
    if existing_artifacts or existing_folds or existing_models:
        raise RuntimeError(
            f"Existing run artifacts found in {private_dir}! "
            f"Artifacts: {[p.name for p in existing_artifacts + existing_folds + existing_models]}. "
            "Refusing overwrite to preserve failed attempt data. Clean up or use a new directory."
        )

    pub_json_path = Path(plan["public_output"])
    if not pub_json_path.is_absolute():
        pub_json_path = PROJECT_ROOT / pub_json_path
    validate_path_safety(pub_json_path, [PROJECT_ROOT], "public_output")

    pub_md_path = Path(plan["report_output"])
    if not pub_md_path.is_absolute():
        pub_md_path = PROJECT_ROOT / pub_md_path
    validate_path_safety(pub_md_path, [PROJECT_ROOT], "report_output")

    if pub_json_path.exists() or pub_md_path.exists():
        raise RuntimeError(
            "Public report outputs already exist on disk! Overwriting is forbidden."
        )

    # Write exclusive run-start record before baseline; preserves failed attempt record
    run_start_data = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "plan_sha256": sha256_file(plan_path),
        "runner_sha256": sha256_file(runner_path),
        "prepare_receipt_sha256": sha256_file(prepare_receipt_path),
    }
    save_exclusive_private_json(run_start_path, run_start_data)

    lock_path = private_dir / "execution.lock"

    with FileLock(lock_path):
        import random
        import numpy as np
        import torch
        import transformers
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        # Require MPS
        if not torch.backends.mps.is_available():
            raise RuntimeError("MPS device is required for this experiment but is not available.")
        device = torch.device("mps")
        print(f"[RUN] Using device: {device} (PyTorch {torch.__version__}, Transformers {transformers.__version__})")

        # Validate inputs & preflight
        meta = validate_input_datasets(plan, allowed_roots=allowed_roots)
        threshold = meta["threshold"]

        kisa_inputs = meta["kisa_inputs"]
        normal_inputs = meta["normal_inputs"]
        kisa_miss_indices = meta["kisa_miss_indices"]

        # Ensure initial baseline replay gate passes
        print("[RUN] Loading original model for baseline replay verification...")
        orig_tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        check_encoded_input_guards(orig_tokenizer, kisa_inputs, kisa_miss_indices)
        orig_model = AutoModelForSequenceClassification.from_pretrained(
            str(model_dir), local_files_only=True
        ).to(device)

        replay_info = replay_baseline_gate(
            orig_model,
            orig_tokenizer,
            kisa_inputs,
            normal_inputs,
            saved_pred_path,
            threshold,
            device,
        )
        print(
            f"[RUN] Baseline replay gate PASSED (KISA max diff: {replay_info['kisa_max_diff']:.2e}, "
            f"Normal max diff: {replay_info['normal_max_diff']:.2e})."
        )
        save_exclusive_private_json(replay_path, replay_info)

        # Free initial model memory
        del orig_model
        del orig_tokenizer
        gc.collect()
        torch.mps.empty_cache()

        # Execute 9 folds
        folds_data = []
        csv_records = []
        checkpoint_shas: dict[str, str] = {}
        adapted_models: dict[str, dict[str, str]] = {}

        case_id_map = {it["template_index"]: f"K{it['template_index'] + 1:02d}" for it in kisa_inputs}

        for fold_idx, s_idx in enumerate(sorted(kisa_miss_indices)):
            case_id = case_id_map[s_idx]
            fold_id = f"fold_{case_id}"
            fold_ckpt_path = private_dir / f"{fold_id}.json"
            print(f"\n[RUN] Commencing {fold_id} (Support case: {case_id}, template_index={s_idx})...")

            # Reset random seeds and reload fresh untouched original model
            random.seed(42)
            np.random.seed(42)
            torch.manual_seed(42)
            torch.mps.manual_seed(42)

            tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(
                str(model_dir), local_files_only=True
            ).to(device)

            # Support item
            s_item = next(it for it in kisa_inputs if it["template_index"] == s_idx)
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

            optimizer = torch.optim.AdamW(
                model.parameters(),
                lr=plan["design"]["learning_rate"],
                weight_decay=plan["design"]["weight_decay"],
            )

            step_data: dict[str, Any] = {}
            training_losses: dict[str, float] = {}

            # Training updates loop (1 to 10)
            model.train()
            for update_step in range(1, 11):
                optimizer.zero_grad()
                outputs = model(**s_enc, labels=s_label)
                loss = outputs.loss
                training_losses[str(update_step)] = float(loss.item())
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(),
                    plan["design"]["gradient_clip_norm"],
                )
                optimizer.step()

                if update_step in [1, 5, 10]:
                    model.eval()
                    with torch.no_grad():
                        # KISA evaluation
                        k_probs: list[float] = []
                        kisa_texts = [it["primary_model_input"] for it in kisa_inputs]
                        for i in range(0, len(kisa_texts), 16):
                            b_enc = tokenizer(
                                kisa_texts[i : i + 16],
                                truncation=True,
                                padding="max_length",
                                max_length=128,
                                return_tensors="pt",
                            )
                            b_enc = {k: v.to(device) for k, v in b_enc.items()}
                            b_logits = model(**b_enc).logits
                            k_probs.extend(torch.softmax(b_logits, dim=1)[:, 1].cpu().tolist())

                        # Normal evaluation
                        n_probs: list[float] = []
                        norm_texts = [it["text_normalized"] for it in normal_inputs]
                        for i in range(0, len(norm_texts), 16):
                            b_enc = tokenizer(
                                norm_texts[i : i + 16],
                                truncation=True,
                                padding="max_length",
                                max_length=128,
                                return_tensors="pt",
                            )
                            b_enc = {k: v.to(device) for k, v in b_enc.items()}
                            b_logits = model(**b_enc).logits
                            n_probs.extend(torch.softmax(b_logits, dim=1)[:, 1].cpu().tolist())

                    kisa_step_records = []
                    for i, it in enumerate(kisa_inputs):
                        cid = case_id_map[it["template_index"]]
                        p = k_probs[i]
                        b42 = it["baseline_predictions"]["42"]
                        kisa_step_records.append({
                            "case_id": cid,
                            "template_index": it["template_index"],
                            "group_id": it["group_id"],
                            "is_group_representative": it["is_group_representative"],
                            "prob": p,
                            "pred": 1 if p >= threshold else 0,
                            "baseline_prob": float(b42["probability"]),
                            "baseline_pred": int(b42["decision"]),
                        })

                    norm_step_records = []
                    for i, it in enumerate(normal_inputs):
                        cid = it["candidate_id"]
                        p = n_probs[i]
                        rep_n = replay_info["normal_replay"][i]
                        norm_step_records.append({
                            "candidate_id": cid,
                            "prob": p,
                            "pred": 1 if p >= threshold else 0,
                            "baseline_prob": float(rep_n["baseline_prob"]),
                            "baseline_pred": int(rep_n["baseline_pred"]),
                        })

                    # Recompute metrics for this step
                    metrics = recompute_fold_metrics(
                        case_id,
                        kisa_step_records,
                        norm_step_records,
                        threshold,
                    )

                    step_data[str(update_step)] = {
                        "metrics": metrics,
                        "kisa_records": kisa_step_records,
                        "normal_records": norm_step_records,
                    }

                    # Add to CSV records (272 records per step)
                    for kr in kisa_step_records:
                        csv_records.append({
                            "fold_id": fold_id,
                            "step": update_step,
                            "cohort": "kisa_unique",
                            "row_id": f"kisa_{kr['template_index']:02d}",
                            "case_id": kr["case_id"],
                            "source_id": kisa_inputs[kr["template_index"]]["primary_model_input_sha256"],
                            "group_id": kr["group_id"],
                            "is_group_representative": kr["is_group_representative"],
                            "label": 1,
                            "probability": kr["prob"],
                            "prediction": kr["pred"],
                            "threshold": threshold,
                            "baseline_probability": kr["baseline_prob"],
                            "baseline_prediction": kr["baseline_pred"],
                        })

                    for nr in norm_step_records:
                        csv_records.append({
                            "fold_id": fold_id,
                            "step": update_step,
                            "cohort": "normal_candidates",
                            "row_id": f"normal_{nr['candidate_id']}",
                            "case_id": "none",
                            "source_id": nr["candidate_id"],
                            "group_id": "none",
                            "is_group_representative": False,
                            "label": 0,
                            "probability": nr["prob"],
                            "prediction": nr["pred"],
                            "threshold": threshold,
                            "baseline_probability": nr["baseline_prob"],
                            "baseline_prediction": nr["baseline_pred"],
                        })

                    model.train()

                if update_step == 10:
                    fold_model_dir = private_dir / f"model_{fold_id}_step10"
                    ensure_private_dir(fold_model_dir)
                    model.save_pretrained(str(fold_model_dir))
                    tokenizer.save_pretrained(str(fold_model_dir))
                    mf_hashes = {}
                    for mf in sorted(fold_model_dir.iterdir()):
                        ensure_private_file(mf)
                        mf_hashes[mf.name] = sha256_file(mf)
                    adapted_models[fold_id] = mf_hashes

            # Save fold checkpoint
            fold_payload = {
                "fold_id": fold_id,
                "support_case_id": case_id,
                "support_template_index": s_idx,
                "support_group_id": s_item["group_id"],
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "training_losses": training_losses,
                "steps": step_data,
            }
            save_exclusive_private_json(fold_ckpt_path, fold_payload)
            checkpoint_shas[fold_id] = sha256_file(fold_ckpt_path)
            folds_data.append(fold_payload)

            del model
            del tokenizer
            del optimizer
            gc.collect()
            torch.mps.empty_cache()

        folds_data = sorted(folds_data, key=lambda x: x["fold_id"])

        # Validate CSV row count: exactly 7344 rows (9 folds * 3 steps * 272 rows)
        if len(csv_records) != 7344:
            raise ValueError(f"Expected 7344 prediction CSV rows, generated {len(csv_records)}")

        # Write private_predictions.csv exclusively
        csv_header = [
            "fold_id",
            "step",
            "cohort",
            "row_id",
            "case_id",
            "source_id",
            "group_id",
            "is_group_representative",
            "label",
            "probability",
            "prediction",
            "threshold",
            "baseline_probability",
            "baseline_prediction",
        ]
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        fd = os.open(str(pred_csv_path), flags, 0o600)
        try:
            with open(fd, "w", encoding="utf-8", newline="", closefd=False) as f:
                writer = csv.DictWriter(f, fieldnames=csv_header)
                writer.writeheader()
                writer.writerows(csv_records)
        finally:
            os.close(fd)

        # Render public outputs
        public_json_text = render_public_json(plan, folds_data, replay_info)
        public_md_text = render_markdown_report(plan, folds_data, replay_info)

        save_exclusive_public_file(pub_json_path, public_json_text)
        save_exclusive_public_file(pub_md_path, public_md_text)

        # Re-verify all source and original model hashes against prepare_receipt
        meta_post = validate_input_datasets(plan, allowed_roots=allowed_roots)
        if meta_post["model_hashes"] != prep_data["model_files_sha256"]:
            raise RuntimeError("Original model files modified during run! Aborting.")
        if meta_post["kisa_input_sha256"] != prep_data["kisa_input_sha256"]:
            raise RuntimeError("KISA inputs modified during run! Aborting.")
        if meta_post["normal_input_sha256"] != prep_data["normal_input_sha256"]:
            raise RuntimeError("Normal inputs modified during run! Aborting.")

        # Write immutable run_receipt.json exclusively
        receipt_data = {
            "schema_version": 1,
            "experiment_id": "kisa_one_example_20261004",
            "version": plan["version"],
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "plan_sha256": sha256_file(plan_path),
            "runner_sha256": sha256_file(runner_path),
            "prepare_receipt_sha256": sha256_file(prepare_receipt_path),
            "run_start_sha256": sha256_file(run_start_path),
            "environment": {
                "torch_version": torch.__version__,
                "transformers_version": transformers.__version__,
                "device": "mps",
            },
            "baseline_replay": {
                "kisa_max_diff": replay_info["kisa_max_diff"],
                "normal_max_diff": replay_info["normal_max_diff"],
                "passed": True,
            },
            "baseline_replay_sha256": sha256_file(replay_path),
            "checkpoint_sha256s": checkpoint_shas,
            "adapted_models": adapted_models,
            "predictions_csv_sha256": sha256_file(pred_csv_path),
            "public_json_sha256": sha256_file(pub_json_path),
            "report_md_sha256": sha256_file(pub_md_path),
            "all_folds_completed": len(folds_data),
            "total_csv_rows": len(csv_records),
        }
        save_exclusive_private_json(run_receipt_path, receipt_data)
        print(f"\n[RUN] Diagnostic experiment completed successfully! Run receipt saved to {run_receipt_path}.")


def check_pipeline(
    plan_path: Path = DEFAULT_PLAN_PATH,
    allowed_roots: list[Path] | None = None,
) -> bool:
    """Verify stored diagnostic results via independent metric recomputation without torch model load."""
    if allowed_roots is None:
        allowed_roots = [DEFAULT_PRIVATE_ROOT, PROJECT_ROOT]

    errors: list[str] = []
    print("=== [KISA One-Example Adaptation Pipeline Check] ===")

    if not plan_path.exists():
        print(f"[FAIL] Plan file missing: {plan_path}")
        return False

    try:
        plan = load_plan(plan_path)
    except Exception as e:
        print(f"[FAIL] Plan loading/validation failed: {e}")
        return False

    private_dir = Path(plan["private_output_directory"])
    try:
        validate_path_safety(private_dir, allowed_roots, "private_output_directory")
    except Exception as e:
        print(f"[FAIL] Path safety check failed: {e}")
        return False

    prepare_receipt_path = private_dir / "prepare_receipt.json"
    run_receipt_path = private_dir / "run_receipt.json"

    # Strict check: absent results or prepared-only must return False (experiment not complete)
    if not run_receipt_path.exists():
        if not prepare_receipt_path.exists():
            print(f"[FAIL] Neither prepare_receipt nor run_receipt exists at {private_dir}. Pipeline not executed.")
            return False
        print(f"[FAIL] Pipeline is in prepared-only state at {private_dir}. Experiment execution is incomplete.")
        return False

    # Run receipt exists: execute full independent verification
    print("[INFO] Run receipt found. Verifying executed artifacts and recomputing metrics...")
    try:
        receipt = load_json(run_receipt_path)

        if not prepare_receipt_path.exists():
            errors.append("prepare_receipt.json missing alongside run_receipt.json")
        else:
            prep_data = load_json(prepare_receipt_path)
            # Verify original inputs/models against prepare_receipt bindings
            kisa_path = Path(plan["kisa_input_path"])
            normal_path = Path(plan["normal_input_path"])
            saved_pred_path = Path(plan["saved_predictions_path"])
            model_dir = Path(plan["model_directory"])
            threshold_path = Path(plan["threshold_report"])
            if not threshold_path.is_absolute():
                threshold_path = PROJECT_ROOT / threshold_path

            if sha256_file(kisa_path) != prep_data.get("kisa_input_sha256"):
                errors.append("Current kisa_input hash drifts from prepare_receipt")
            if sha256_file(normal_path) != prep_data.get("normal_input_sha256"):
                errors.append("Current normal_input hash drifts from prepare_receipt")
            if sha256_file(saved_pred_path) != prep_data.get("saved_predictions_sha256"):
                errors.append("Current saved_predictions hash drifts from prepare_receipt")
            if sha256_file(threshold_path) != prep_data.get("threshold_report_sha256"):
                errors.append("Current threshold_report hash drifts from prepare_receipt")
            for mf, exp_sha in prep_data.get("model_files_sha256", {}).items():
                if sha256_file(model_dir / mf) != exp_sha:
                    errors.append(f"Current original model file {mf} hash drifts from prepare_receipt")

        # Verify receipt bindings
        runner_path = Path(__file__).resolve()
        if receipt.get("plan_sha256") != sha256_file(plan_path):
            errors.append("Run receipt plan_sha256 drift")
        if receipt.get("runner_sha256") != sha256_file(runner_path):
            errors.append("Run receipt runner_sha256 drift")

        # Verify baseline replay record
        replay_path = private_dir / "seed_42_baseline_replay.json"
        if not replay_path.exists():
            errors.append("Baseline replay artifact missing: seed_42_baseline_replay.json")
        else:
            if sha256_file(replay_path) != receipt.get("baseline_replay_sha256"):
                errors.append("Baseline replay file hash mismatch vs receipt")
            replay_doc = load_json(replay_path)
            if not replay_doc.get("passed"):
                errors.append("Baseline replay file does not indicate passed=True")
            if replay_doc.get("kisa_max_diff", 1.0) > 1e-5 or replay_doc.get("normal_max_diff", 1.0) > 1e-5:
                errors.append("Baseline replay max difference exceeds tolerance 1e-5")

        # Verify public outputs
        pub_json_path = Path(plan["public_output"])
        if not pub_json_path.is_absolute():
            pub_json_path = PROJECT_ROOT / pub_json_path
        if not pub_json_path.exists() or sha256_file(pub_json_path) != receipt.get("public_json_sha256"):
            errors.append("Public JSON missing or hash mismatch")

        pub_md_path = Path(plan["report_output"])
        if not pub_md_path.is_absolute():
            pub_md_path = PROJECT_ROOT / pub_md_path
        if not pub_md_path.exists() or sha256_file(pub_md_path) != receipt.get("report_md_sha256"):
            errors.append("Report Markdown missing or hash mismatch")

        # Check all 9 fold checkpoints
        ckpt_shas = receipt.get("checkpoint_sha256s", {})
        expected_fold_ids = [f"fold_K{i:02d}" for i in range(1, 10)]
        if sorted(list(ckpt_shas.keys())) != expected_fold_ids:
            errors.append(f"Checkpoint fold IDs mismatch: {sorted(list(ckpt_shas.keys()))} vs {expected_fold_ids}")

        # Check adapted models in receipt and on disk
        adapted_models = receipt.get("adapted_models", {})
        if sorted(list(adapted_models.keys())) != expected_fold_ids:
            errors.append(f"Adapted models receipt IDs mismatch: {sorted(list(adapted_models.keys()))} vs {expected_fold_ids}")

        for fid, model_files in adapted_models.items():
            model_dir = private_dir / f"model_{fid}_step10"
            if not model_dir.exists():
                errors.append(f"Adapted model dir missing: {model_dir}")
                continue
            for mf_name, exp_mf_sha in model_files.items():
                mf_file = model_dir / mf_name
                if not mf_file.exists():
                    errors.append(f"Adapted model file missing: {mf_file}")
                elif sha256_file(mf_file) != exp_mf_sha:
                    errors.append(f"Adapted model file tampered: {mf_file} (hash drift)")

        folds_data = []
        fold_probs_map: dict[tuple[str, int, str, str], float] = {}

        for fid in expected_fold_ids:
            f_path = private_dir / f"{fid}.json"
            if not f_path.exists():
                errors.append(f"Fold checkpoint missing: {f_path}")
                continue
            act_sha = sha256_file(f_path)
            if act_sha != ckpt_shas.get(fid):
                errors.append(f"Fold checkpoint {fid} hash mismatch: {act_sha} vs {ckpt_shas.get(fid)}")
                continue
            f_doc = load_json(f_path)
            folds_data.append(f_doc)

            # Check steps 1, 5, 10 presence
            steps = f_doc.get("steps", {})
            for st in ["1", "5", "10"]:
                if st not in steps:
                    errors.append(f"Fold {fid} missing step {st}")
                else:
                    st_int = int(st)
                    for kr in steps[st].get("kisa_records", []):
                        key = (fid, st_int, "kisa_unique", f"kisa_{kr['template_index']:02d}")
                        fold_probs_map[key] = float(kr["prob"])
                    for nr in steps[st].get("normal_records", []):
                        key = (fid, st_int, "normal_candidates", f"normal_{nr['candidate_id']}")
                        fold_probs_map[key] = float(nr["prob"])

        # Verify predictions CSV (exactly 7344 rows and exact equality to fold probabilities)
        pred_csv_path = private_dir / "private_predictions.csv"
        if not pred_csv_path.exists() or sha256_file(pred_csv_path) != receipt.get("predictions_csv_sha256"):
            errors.append("Predictions CSV missing or hash mismatch")
        else:
            csv_row_count = 0
            with open(pred_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    csv_row_count += 1
                    fid = row["fold_id"]
                    step = int(row["step"])
                    cohort = row["cohort"]
                    row_id = row["row_id"]
                    prob = float(row["probability"])

                    map_key = (fid, step, cohort, row_id)
                    if map_key not in fold_probs_map:
                        errors.append(f"CSV row {map_key} not found in fold checkpoints")
                    else:
                        exp_prob = fold_probs_map[map_key]
                        if abs(prob - exp_prob) > 1e-12:
                            errors.append(
                                f"CSV probability mismatch for {map_key}: {prob} vs checkpoint {exp_prob}"
                            )

            if csv_row_count != 7344:
                errors.append(f"Expected 7344 CSV rows (9*3*272), found {csv_row_count}")

        # Recompute all metrics independently and verify against stored metrics
        threshold = plan["baseline"]["threshold"]
        for fd in folds_data:
            fid = fd["fold_id"]
            sid = fd["support_case_id"]
            for st in ["1", "5", "10"]:
                st_data = fd["steps"][st]
                k_recs = st_data["kisa_records"]
                n_recs = st_data["normal_records"]

                recomputed = recompute_fold_metrics(sid, k_recs, n_recs, threshold)
                stored = st_data["metrics"]

                for key in ["support", "held_out_misses", "retention", "normal_regression", "verdicts"]:
                    if recomputed[key] != stored[key]:
                        errors.append(f"Metric recomputation drift in {fid} step {st} [{key}]")

        # Check public outputs deterministic render match
        rep_replay = receipt.get("baseline_replay", {})
        exp_pub_json = render_public_json(plan, folds_data, rep_replay)
        exp_pub_md = render_markdown_report(plan, folds_data, rep_replay)

        act_pub_json = pub_json_path.read_text(encoding="utf-8")
        act_pub_md = pub_md_path.read_text(encoding="utf-8")

        if act_pub_json != exp_pub_json:
            errors.append("Public JSON report differs from deterministic pure renderer")
        if act_pub_md != exp_pub_md:
            errors.append("Public Markdown report differs from deterministic pure renderer")

        # Privacy checks on public files: no private paths, no raw probabilities in public JSON
        pub_json_parsed = json.loads(act_pub_json)
        # Verify no probability fields exist in fold step metrics in public JSON
        for fold_entry in pub_json_parsed.get("folds", []):
            for st_key, st_metrics in fold_entry.get("steps", {}).items():
                if "adapted_prob" in st_metrics.get("support", {}):
                    errors.append(f"Probability leaked in public JSON support metrics: {fold_entry['fold_id']}")
                if "cases" in st_metrics.get("held_out_misses", {}):
                    errors.append(f"Per-case probabilities leaked in public JSON held_out_misses: {fold_entry['fold_id']}")

        for pub_path in [pub_json_path, pub_md_path]:
            content = pub_path.read_text(encoding="utf-8")
            if "scamlens_private" in content:
                errors.append(f"Private path found in public output: {pub_path}")

    except Exception as e:
        errors.append(f"Verification exception: {e}")

    ok = len(errors) == 0
    if ok:
        print("[PASS] All read-only checks passed. 9 folds, 3 checkpoints, denominators, and reports verified.")
    else:
        print(f"[FAIL] Pipeline check failed with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run or check KISA One-Example Adaptation Diagnostic (20261004_v1)"
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
        help="Execute preflight checks, compute input hashes, and write prepare_receipt",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute baseline replay, 9-fold fine-tuning, and generate reports",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify stored artifacts and recompute metrics without model loading",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=DEFAULT_PLAN_PATH,
        help="Path to experiment plan JSON (default: docs/experiments/KISA_ONE_EXAMPLE_PLAN_20261004.json)",
    )

    args = parser.parse_args()

    # Determine mode
    if args.prepare or args.mode == "prepare":
        prepare_diagnostic(plan_path=args.plan)
    elif args.run or args.mode == "run":
        run_diagnostic_experiment(plan_path=args.plan)
    else:
        # Default or --check / check
        ok = check_pipeline(plan_path=args.plan)
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
