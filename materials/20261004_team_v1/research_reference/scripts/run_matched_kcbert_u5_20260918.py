#!/usr/bin/env python3
"""Confirmatory U5 run: same 281 E, unused original test scored once, no two-track.

Thresholds come only from threshold_calibration. Unused-test metrics are written
after all 15 arms finish. Development readout is stored for sanity, not for
selection. Fine-tuned weights stay in the private output directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "reports/generated/matched_kcbert_u5_e_lock_20260918_v1.json"
UNUSED_PUBLIC = ROOT / "reports/generated/matched_kcbert_u5_unused_eval_20260918_v1.json"
BUNDLE = ROOT / "data/interim/matched_kcbert_sas_private_20260917_v1"
PRIVATE_ROOT = Path.home() / "scamlens_private/local_kcbert_u5_20260918_v1"
UNUSED_CSV = PRIVATE_ROOT / "unused_eval.csv"
RESULTS = PRIVATE_ROOT / "results"
PUBLIC = ROOT / "reports/generated/matched_kcbert_u5_unused_test_20260918_v1.json"
PORTABLE = ROOT / "scripts/run_matched_kcbert_portable_20260917.py"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def load_portable():
    spec = importlib.util.spec_from_file_location("kcbert_portable_u5", PORTABLE)
    require(spec is not None and spec.loader is not None, "portable_import")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_unused() -> dict[str, list[dict[str, str]]]:
    require(UNUSED_CSV.is_file(), "unused_eval_missing")
    public = json.loads(UNUSED_PUBLIC.read_text(encoding="utf-8"))
    require(sha(UNUSED_CSV) == public["private_csv_sha256"], "unused_csv_hash")
    with UNUSED_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == public["private_csv_rows"], "unused_row_count")
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["split"]].append(row)
    return grouped


def metrics(rows: list[dict], probs: list[float], threshold: float) -> dict:
    y = np.array([1 if r["label"] == "smishing" else 0 for r in rows], dtype=int)
    p = np.asarray(probs, dtype=float)
    pred = (p >= threshold).astype(int)
    tp = int(((y == 1) & (pred == 1)).sum())
    fn = int(((y == 1) & (pred == 0)).sum())
    fp = int(((y == 0) & (pred == 1)).sum())
    tn = int(((y == 0) & (pred == 0)).sum())
    recall = tp / (tp + fn) if tp + fn else None
    fpr = fp / (fp + tn) if fp + tn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    by_url = {}
    for flag in ("0", "1"):
        mask = np.array([r["has_url"] == flag for r in rows])
        if not mask.any():
            continue
        yy, pp = y[mask], pred[mask]
        ttp = int(((yy == 1) & (pp == 1)).sum())
        tfn = int(((yy == 1) & (pp == 0)).sum())
        tfp = int(((yy == 0) & (pp == 1)).sum())
        ttn = int(((yy == 0) & (pp == 0)).sum())
        by_url[flag] = {
            "n": int(mask.sum()),
            "tp": ttp, "fn": tfn, "fp": tfp, "tn": ttn,
            "recall": ttp / (ttp + tfn) if ttp + tfn else None,
            "fpr": tfp / (tfp + ttn) if tfp + ttn else None,
        }
    return {
        "n": len(rows), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "recall": recall, "fpr": fpr, "f1": f1,
        "brier": float(np.mean((p - y) ** 2)),
        "threshold": float(threshold),
        "by_has_url": by_url,
    }


def mean_std(values: list[float]) -> dict:
    arr = np.asarray(values, dtype=float)
    return {"mean": float(arr.mean()), "std": float(arr.std(ddof=0))}


def write_pred_csv(path: Path, rows: list[dict], probs: list[float], role: str) -> str:
    out = []
    for row, prob in zip(rows, probs):
        out.append({
            "message_id": row["message_id"],
            "development_group_id": row["development_group_id"],
            "role": role,
            "label": row["label"],
            "has_url": row["has_url"],
            "probability": repr(float(prob)),
        })
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["message_id", "development_group_id", "role", "label", "has_url", "probability"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(out)
    os.chmod(path, 0o600)
    return sha(path)


def private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_mode & 0o077:
        raise AssertionError("private_dir_permissions")


def fingerprint(portable, unused_public: dict, lock: dict) -> str:
    payload = {
        "lock": lock["hashes"],
        "unused_eval": unused_public["private_csv_sha256"],
        "bundle": sha(BUNDLE / "manifest.json"),
        "portable": sha(PORTABLE),
        "runner": sha(Path(__file__)),
        "protocol": {
            "seeds": list(portable.SEEDS),
            "arms": list(portable.ARMS),
            "two_track": False,
            "primary": "unused_original_test_one_shot",
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def aggregate(results: Path, fp: str) -> dict:
    unused_public = json.loads(UNUSED_PUBLIC.read_text(encoding="utf-8"))
    portable = load_portable()
    store = portable.load_store()
    by_arm: dict[str, list[dict]] = {arm: [] for arm in portable.ARMS}
    for seed in portable.SEEDS:
        for arm in portable.ARMS:
            arm_dir = results / f"seed_{seed}" / arm
            require(arm_dir.is_dir(), f"missing {seed}/{arm}")
            meta = json.loads((arm_dir / "arm_manifest.json").read_text(encoding="utf-8"))
            require(meta["fingerprint"] == fp, "fingerprint_mismatch")
            test_path = arm_dir / "unused_test.csv"
            require(test_path.is_file(), "missing_unused_test")
            with test_path.open(encoding="utf-8", newline="") as handle:
                test_rows = list(csv.DictReader(handle))
            require(len(test_rows) == unused_public["test"]["n"], "test_n")
            calib_rows = [r for r in store.read_arm(arm_dir) if r["role"] == "calibration"]
            y = [0 if r["label"] == "normal" else 1 for r in calib_rows]
            p = [float(r["probability"]) for r in calib_rows]
            threshold, _sel = store.threshold(y, p, cap=0.01)
            test_p = [float(r["probability"]) for r in test_rows]
            test_meta = [
                {"label": r["label"], "has_url": r["has_url"], "message_id": r["message_id"],
                 "development_group_id": r["development_group_id"]}
                for r in test_rows
            ]
            by_arm[arm].append(metrics(test_meta, test_p, threshold) | {"seed": seed})
    summary = {}
    for arm, rows in by_arm.items():
        summary[arm] = {
            "recall": mean_std([r["recall"] for r in rows]),
            "fpr": mean_std([r["fpr"] for r in rows]),
            "f1": mean_std([r["f1"] for r in rows]),
            "brier": mean_std([r["brier"] for r in rows]),
            "url_present_fpr": mean_std([r["by_has_url"]["1"]["fpr"] for r in rows]),
            "url_absent_fpr": mean_std([r["by_has_url"]["0"]["fpr"] for r in rows]),
            "seeds": rows,
        }
    exceed = {
        arm: sum(r["fpr"] > 0.01 for r in rows)
        for arm, rows in by_arm.items()
    }
    return {
        "status": "u5_unused_test_complete",
        "E_status": "confirmatory_e_locked_before_unused_test",
        "evaluation_role": "unused_original_test_one_shot",
        "prospective_naturalness_pre_registration": False,
        "two_track_applied": False,
        "fingerprint": fp,
        "n_test": unused_public["test"]["n"],
        "arm_statistics": summary,
        "readout_fpr_above_calibration_cap": exceed,
        "lock_sha256": sha(LOCK),
        "unused_eval_sha256": sha(UNUSED_PUBLIC),
    }


def run(max_arms: int, device_name: str) -> None:
    os.umask(0o077)
    private_dir(PRIVATE_ROOT)
    private_dir(RESULTS)
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    unused_public = json.loads(UNUSED_PUBLIC.read_text(encoding="utf-8"))
    require(lock["status"] == "e_locked_confirmatory_u5", "e_lock")
    require(lock["approved_pairs_E"] == 281, "e_count")
    require(unused_public["status"] == "unused_eval_prepared_text_private", "unused")
    portable = load_portable()
    unused = load_unused()
    fp = fingerprint(portable, unused_public, lock)
    device = portable.choose_device(device_name)
    require(device.type != "cpu", "u5_refuses_cpu_full_run")
    rows, edits, _, checkpoint = portable.load_bundle(BUNDLE)
    require(len(edits) == 281, "edits")
    fit = [r for r in rows if r["role"] == "fit"]
    calibration = [r for r in rows if r["role"] == "threshold_calibration"]
    readout = [r for r in rows if r["role"] == "development_readout"]
    fit_labels = [int(r["label"] == "smishing") for r in fit]
    weights_by_class = portable.class_weights(fit_labels)
    originals = [r["text_model_base"] for r in fit]
    selected_labels = [int(r["label"] == "smishing") for r, _ in edits]
    duplicated_labels = fit_labels + selected_labels
    arm_texts = {
        "DUP": originals + [row["text_model_base"] for row, _ in edits],
        "FLIP": originals + [edit["edited_text"] for _, edit in edits],
        "BASE": originals,
    }
    arm_labels = {"DUP": duplicated_labels, "FLIP": duplicated_labels, "BASE": fit_labels}
    budget = portable.schedule(len(fit), len(edits))["common_update_budget"]
    tokenizer = portable.AutoTokenizer.from_pretrained(str(checkpoint), local_files_only=True)
    trained = 0
    for seed in portable.SEEDS:
        for arm in portable.ARMS:
            arm_dir = RESULTS / f"seed_{seed}" / arm
            if arm_dir.exists():
                print(f"reuse {seed}/{arm}", flush=True)
                continue
            if trained >= max_arms:
                continue
            labels = arm_labels[arm]
            weights = [weights_by_class[value] for value in labels]
            model, updates = portable.train_arm(
                arm_texts[arm], labels, weights, tokenizer, device, checkpoint,
                budget, seed, replacement=arm == "BASE",
            )
            require(updates == budget, "budget")
            cal_p = portable.infer(model, calibration, tokenizer, device)
            read_p = portable.infer(model, readout, tokenizer, device)
            test_p = portable.infer(model, unused["test"], tokenizer, device)
            val_p = portable.infer(model, unused["validation"], tokenizer, device)
            tmp = RESULTS / f".tmp_{seed}_{arm}"
            if tmp.exists():
                import shutil
                shutil.rmtree(tmp)
            tmp.mkdir(mode=0o700)
            write_pred_csv(tmp / "calibration.csv", calibration, cal_p, "calibration")
            write_pred_csv(tmp / "readout.csv", readout, read_p, "development_readout")
            write_pred_csv(tmp / "unused_test.csv", unused["test"], test_p, "unused_original_test")
            write_pred_csv(tmp / "unused_validation.csv", unused["validation"], val_p, "unused_original_validation")
            model_dir = tmp / "model"
            model.save_pretrained(model_dir)
            tokenizer.save_pretrained(model_dir)
            for path in model_dir.rglob("*"):
                if path.is_file():
                    os.chmod(path, 0o600)
            store = portable.load_store()
            store.write_arm(
                RESULTS, seed, arm,
                portable.prediction_rows(calibration, cal_p, "calibration"),
                portable.prediction_rows(readout, read_p, "readout"),
                fp,
            )
            final = RESULTS / f"seed_{seed}" / arm
            for name in ("unused_test.csv", "unused_validation.csv", "calibration.csv", "readout.csv"):
                dest = final / name
                if dest.exists():
                    dest.unlink()
                os.rename(tmp / name, dest)
                os.chmod(dest, 0o600)
            dest_model = final / "model"
            if dest_model.exists():
                import shutil
                shutil.rmtree(dest_model)
            os.rename(model_dir, dest_model)
            manifest = json.loads((final / "arm_manifest.json").read_text(encoding="utf-8"))
            manifest["u5"] = {
                "unused_test": sha(final / "unused_test.csv"),
                "unused_validation": sha(final / "unused_validation.csv"),
                "weights_saved": True,
            }
            (final / "arm_manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
            os.chmod(final / "arm_manifest.json", 0o600)
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            del model
            trained += 1
            print(f"completed {seed}/{arm} updates={updates} unused_test_rows={len(unused['test'])}", flush=True)
    complete = sum(
        (RESULTS / f"seed_{seed}" / arm / "unused_test.csv").is_file()
        for seed in portable.SEEDS for arm in portable.ARMS
    )
    print(json.dumps({"trained_this_invocation": trained, "completed_arms_with_unused_test": complete}), flush=True)
    if complete == 15:
        payload = aggregate(RESULTS, fp)
        PUBLIC.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        print("WROTE", PUBLIC.relative_to(ROOT), flush=True)


def check() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    unused_public = json.loads(UNUSED_PUBLIC.read_text(encoding="utf-8"))
    portable = load_portable()
    fp = fingerprint(portable, unused_public, lock)
    payload = aggregate(RESULTS, fp)
    require(PUBLIC.is_file(), "public_missing")
    current = json.loads(PUBLIC.read_text(encoding="utf-8"))
    require(current["fingerprint"] == payload["fingerprint"], "public_fingerprint")
    require(current["evaluation_role"] == "unused_original_test_one_shot", "role")
    require(current["two_track_applied"] is False, "two_track")
    require(current["n_test"] == unused_public["test"]["n"], "n_test")
    print("PASS: U5 unused-test aggregate current")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "check"))
    parser.add_argument("--max-arms", type=int, default=1)
    parser.add_argument("--device", default="mps")
    args = parser.parse_args()
    if args.action == "check":
        check()
        return
    run(args.max_arms, args.device)


if __name__ == "__main__":
    main()
