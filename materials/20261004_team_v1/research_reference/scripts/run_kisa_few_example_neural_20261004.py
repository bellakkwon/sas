"""Offline neural few-example (pairs and triples) fine-tuning runner.

Executes fixed 2- and 3-example adaptations across the 27 saved neural checkpoints.
Adheres strictly to the frozen plan docs/experiments/KISA_FEW_EXAMPLE_PLAN_20261004.json
and the common contract in scripts/kisa_few_example_common_20261004.py.
"""
from __future__ import annotations

import os

for _name in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[_name] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import argparse
import gc
import math
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import kisa_few_example_common_20261004 as common


def resolve_model_dir(
    model_dir_str: str,
    private_root: Path = common.PRIVATE,
    project_root: Path = common.ROOT,
) -> Path:
    """Resolve model directory handling 'private:' alias or project relative paths."""
    old_neural = common.old_module("neural")
    return old_neural.resolve_model_dir(model_dir_str, private_root, project_root)


def check_singleton_support_groups(
    kisa_inputs: list[dict[str, Any]],
    support_case_indices: list[int] = list(range(9)),
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


def check_token_collisions_and_normal(
    tokenizer: Any,
    kisa_inputs: list[dict[str, Any]],
    normal_inputs: list[dict[str, Any]],
    support_indices: list[int],
) -> list[int]:
    """Check token collision between support cases, normal candidates, and heldout KISA.

    1. Verify no two support cases in support_indices share identical 128-token sequences.
    2. Verify no support case matches any of the 250 normal candidates' 128-token sequences.
    3. Detect any collision between support cases and other KISA cases (0..21 not in support_indices).
       Returns sorted list of colliding heldout KISA indices.
    """
    s_tokens: dict[int, list[int]] = {}
    for idx in support_indices:
        txt = kisa_inputs[idx]["primary_model_input"]
        enc = tokenizer(txt, truncation=True, padding="max_length", max_length=128)
        s_tokens[idx] = list(enc["input_ids"])

    # Check pairwise among support cases
    s_list = list(support_indices)
    for i in range(len(s_list)):
        for j in range(i + 1, len(s_list)):
            if s_tokens[s_list[i]] == s_tokens[s_list[j]]:
                raise ValueError(
                    f"Token collision between support cases {s_list[i]} and {s_list[j]}"
                )

    # Check against normal candidates
    for norm_idx, n_item in enumerate(normal_inputs):
        n_enc = tokenizer(
            n_item["text_normalized"],
            truncation=True,
            padding="max_length",
            max_length=128,
        )
        n_ids = list(n_enc["input_ids"])
        for s_idx, s_ids in s_tokens.items():
            if s_ids == n_ids:
                raise ValueError(
                    f"Normal collision detected: support index {s_idx} matches normal candidate {n_item['candidate_id']}"
                )

    # Check against other KISA cases (heldout)
    collisions: list[int] = []
    for other_idx in range(len(kisa_inputs)):
        if other_idx in support_indices:
            continue
        other_enc = tokenizer(
            kisa_inputs[other_idx]["primary_model_input"],
            truncation=True,
            padding="max_length",
            max_length=128,
        )
        other_ids = list(other_enc["input_ids"])
        if any(s_ids == other_ids for s_ids in s_tokens.values()):
            collisions.append(other_idx)

    return sorted(collisions)


def prepare_cached_batches(
    tokenizer: Any,
    kisa_inputs: list[dict[str, Any]],
    normal_inputs: list[dict[str, Any]],
    batch_size: int = 16,
    max_length: int = 128,
) -> tuple[list[dict[str, torch.Tensor]], list[dict[str, torch.Tensor]]]:
    """Pre-tokenize KISA 22 and Normal 250 inputs into batch_size (16) chunks."""
    kisa_texts = [it["primary_model_input"] for it in kisa_inputs]
    norm_texts = [it["text_normalized"] for it in normal_inputs]

    kisa_batches: list[dict[str, torch.Tensor]] = []
    for i in range(0, len(kisa_texts), batch_size):
        b_enc = tokenizer(
            kisa_texts[i : i + batch_size],
            truncation=True,
            padding="max_length",
            max_length=max_length,
            return_tensors="pt",
        )
        kisa_batches.append(b_enc)

    normal_batches: list[dict[str, torch.Tensor]] = []
    for i in range(0, len(norm_texts), batch_size):
        b_enc = tokenizer(
            norm_texts[i : i + batch_size],
            truncation=True,
            padding="max_length",
            max_length=max_length,
            return_tensors="pt",
        )
        normal_batches.append(b_enc)

    return kisa_batches, normal_batches


def evaluate_cached_batches(
    model: Any,
    batches: list[dict[str, torch.Tensor]],
    device: torch.device,
) -> list[float]:
    """Forward evaluate pre-tokenized batches and extract positive class probabilities."""
    probs: list[float] = []
    with torch.no_grad():
        for b in batches:
            b_dev = {k: v.to(device) for k, v in b.items()}
            logits = model(**b_dev).logits
            p = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
            probs.extend(p)
    return probs


def run_group_adaptation(
    model: Any,
    resetter: Any,
    tokenizer: Any,
    group: dict[str, Any],
    kisa_inputs: list[dict[str, Any]],
    normal_inputs: list[dict[str, Any]],
    kisa_batches: list[dict[str, torch.Tensor]],
    normal_batches: list[dict[str, torch.Tensor]],
    device: torch.device,
    clip_norm: float = 1.0,
) -> dict[str, Any]:
    """Run AdamW adaptation for a single pair or triple group with strict reset isolation."""
    old_neural = common.old_module("neural")
    gid = group["id"]
    s_indices = group["support_indices"]

    # Verify no source/token collision and check normal collisions
    collisions = check_token_collisions_and_normal(
        tokenizer, kisa_inputs, normal_inputs, s_indices
    )

    # Restore exact immutable CPU weights, reset RNG, and instantiate fresh AdamW
    model, optimizer = resetter.reset()

    # Encode support batch
    s_texts = [kisa_inputs[idx]["primary_model_input"] for idx in s_indices]
    s_enc = tokenizer(
        s_texts,
        truncation=True,
        padding="max_length",
        max_length=128,
        return_tensors="pt",
    )
    s_enc = {k: v.to(device) for k, v in s_enc.items()}
    s_labels = torch.ones(len(s_texts), dtype=torch.long, device=device)

    loss_fct = torch.nn.CrossEntropyLoss(reduction="mean")
    training_losses: list[float] = []
    steps_data: dict[str, dict[str, list[float]]] = {}

    model.train()
    for step in range(1, 11):
        optimizer.zero_grad()
        outputs = model(**s_enc)
        logits = outputs.logits
        loss = loss_fct(logits.view(-1, 2), s_labels.view(-1))
        loss_val = float(loss.item())
        if not math.isfinite(loss_val) or loss_val < 0.0:
            raise ValueError(
                f"Non-finite or invalid training loss at group {gid} step {step}: {loss_val}"
            )
        training_losses.append(loss_val)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip_norm)
        optimizer.step()

        if str(step) in common.STEPS:
            model.eval()
            k_p = evaluate_cached_batches(model, kisa_batches, device)
            n_p = evaluate_cached_batches(model, normal_batches, device)
            combined = common.probabilities(k_p + n_p).tolist()
            steps_data[str(step)] = {"probabilities": combined}
            model.train()

    final_state_sha = old_neural.sha256_state_dict(model.state_dict())
    param_delta_l2 = old_neural.compute_param_delta_l2_norm(
        model, resetter.cpu_state_cache
    )
    if not math.isfinite(param_delta_l2) or param_delta_l2 <= 0.0:
        raise ValueError(
            f"Invalid parameter delta L2 norm for group {gid}: {param_delta_l2}"
        )

    del optimizer

    return {
        "group_id": gid,
        "support_indices": s_indices,
        "collisions": collisions,
        "steps": steps_data,
        "training_losses": training_losses,
        "final_state_sha256": final_state_sha,
        "param_delta_l2_norm": param_delta_l2,
    }


def run_single_neural_model(
    model_id: str,
    device: torch.device | None = None,
) -> dict[str, Any]:
    """Execute complete 2- and 3-example adaptation pipeline for a single neural model."""
    common.verify_sources(neural_model_id=model_id)

    # Check existing result or partial execution
    existing = common.existing_result("neural", model_id)
    if existing is not None:
        print(f"[NEURAL] Model {model_id} already executed and verified with valid receipt.")
        return existing

    # Device requirement: MPS enforced for production runs unless explicitly injected
    if device is None:
        if not (torch.backends.mps.is_available() and torch.backends.mps.is_built()):
            raise RuntimeError(
                "MPS device is strictly required for neural execution on Apple Silicon."
            )
        device = torch.device("mps")

    old_neural = common.old_module("neural")
    lock = old_neural.FileLock(common.OUT / "neural.lock")

    with lock:
        # Re-check existing under lock
        existing = common.existing_result("neural", model_id)
        if existing is not None:
            print(f"[NEURAL] Model {model_id} already executed and verified.")
            return existing

        spec = next(
            (m for m in common.model_specs("neural") if m["id"] == model_id),
            None,
        )
        if spec is None:
            raise ValueError(f"Unknown neural model_id: {model_id}")

        model_dir = resolve_model_dir(spec["model_dir"], common.PRIVATE, common.ROOT)
        if not model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        threshold = spec["threshold"]
        family = spec["family"]

        kisa_inputs, normal_inputs, row_ids = common.input_data()
        plan = common.get_plan()
        groups = plan["groups"]

        # 1. Enforce singleton support group guards on indices 0..8
        check_singleton_support_groups(kisa_inputs, list(range(9)))

        # 2. Tokenizer and cached batches
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        kisa_batches, normal_batches = prepare_cached_batches(
            tokenizer, kisa_inputs, normal_inputs, batch_size=16, max_length=128
        )

        # 3. Model load
        model = AutoModelForSequenceClassification.from_pretrained(
            str(model_dir), local_files_only=True
        ).to(device)

        # 4. Live baseline evaluation
        model.eval()
        kisa_base_probs = evaluate_cached_batches(model, kisa_batches, device)
        norm_base_probs = evaluate_cached_batches(model, normal_batches, device)
        live_base_probs = common.probabilities(kisa_base_probs + norm_base_probs).tolist()

        # 5. Prior baseline replay comparison
        prior_base_probs, _ = common.prior_predictions("neural", model_id)
        diffs = np.abs(np.asarray(live_base_probs, dtype=float) - prior_base_probs)
        baseline_replay_max_diff = float(np.max(diffs))

        if baseline_replay_max_diff > 1e-5:
            raise RuntimeError(
                f"Live baseline probability gap exceeded 1e-5: max gap {baseline_replay_max_diff:.2e} for {model_id}"
            )

        live_decisions = (np.asarray(live_base_probs) >= threshold).astype(int)
        prior_decisions = (prior_base_probs >= threshold).astype(int)
        if not np.array_equal(live_decisions, prior_decisions):
            raise RuntimeError(
                f"Live baseline threshold decisions do not identically match prior decisions for {model_id}"
            )

        print(
            f"[{model_id}] Baseline verified: max replay diff = {baseline_replay_max_diff:.2e}, "
            f"decisions match prior exactly."
        )

        # 6. Initialize ModelResetter with original CPU cache
        resetter = old_neural.ModelResetter(
            model,
            device,
            learning_rate=plan["design"]["neural"]["learning_rate"],
            weight_decay=plan["design"]["neural"]["weight_decay"],
            seed=plan["design"]["neural"]["seed"],
        )

        # 7. Execute 12 groups (9 pairs + 3 triples)
        groups_payload: list[dict[str, Any]] = []
        for g_idx, group in enumerate(groups, 1):
            g_res = run_group_adaptation(
                model=model,
                resetter=resetter,
                tokenizer=tokenizer,
                group=group,
                kisa_inputs=kisa_inputs,
                normal_inputs=normal_inputs,
                kisa_batches=kisa_batches,
                normal_batches=normal_batches,
                device=device,
                clip_norm=plan["design"]["neural"]["clip_norm"],
            )
            groups_payload.append(g_res)
            print(
                f"[{model_id}] ({g_idx}/12) Group {group['id']} done (losses: "
                f"s1={g_res['training_losses'][0]:.4f}, "
                f"s5={g_res['training_losses'][4]:.4f}, "
                f"s10={g_res['training_losses'][9]:.4f} | "
                f"L2 delta: {g_res['param_delta_l2_norm']:.4f})"
            )

        # Cleanup in-memory weights
        del model
        del tokenizer
        del resetter
        gc.collect()
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()

        payload = {
            "model_id": model_id,
            "family": family,
            "kind": "neural",
            "threshold": threshold,
            "row_ids": row_ids,
            "baseline_probabilities": live_base_probs,
            "baseline_replay_max_diff": baseline_replay_max_diff,
            "groups": groups_payload,
        }

        # 8. Save result and receipt
        common.save_result("neural", model_id, payload)

        # 9. Verify source integrity after execution
        common.verify_sources(neural_model_id=model_id)

        print(f"[SUCCESS] Model {model_id} completed and verified.")
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KISA Few Example Neural Runner (2/3-example diagnostic)"
    )
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["run", "list"],
        help="Subcommand: 'run' to execute a model or 'list' to list available models",
    )
    parser.add_argument("--model-id", type=str, help="Specific model ID to run")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available neural models",
    )
    args = parser.parse_args()

    if args.list or args.cmd == "list":
        specs = common.model_specs("neural")
        print(f"Available neural models ({len(specs)}):")
        for s in specs:
            print(f"  {s['id']} (family={s['family']}, threshold={s['threshold']})")
        return

    if not args.model_id:
        parser.error("--model-id is required when not listing models.")

    run_single_neural_model(args.model_id)


if __name__ == "__main__":
    main()
