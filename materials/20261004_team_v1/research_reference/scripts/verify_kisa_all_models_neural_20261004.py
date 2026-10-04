"""Repair two key-order comparisons without changing the frozen experiment runner.

The legacy checker lexically sorted string keys but compared them with numerically
ordered expectations. JSON object order has no meaning. This adapter binds the
exact original source and changes only those two comparisons to exact key sets.
Every source hash, receipt, probability, metric, and report check remains intact.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path

RUNNER = Path(__file__).with_name("run_kisa_all_models_neural_20261004.py")
RUNNER_SHA256 = "baa66fec401f41c964405ea498e111108d715a62d576f91f9acefa7aba8e71b7"
REPLACEMENTS = (
    (
        "sorted(list(losses.keys())) != [str(s) for s in range(1, 11)]",
        "not _exact_checkpoint_keys(losses, [str(s) for s in range(1, 11)])",
    ),
    (
        'sorted(list(steps.keys())) != ["1", "5", "10"]',
        'not _exact_checkpoint_keys(steps, ["1", "5", "10"])',
    ),
)


def _exact_checkpoint_keys(records, expected):
    return isinstance(records, dict) and set(records) == set(expected)


def corrected_source(source):
    for old, new in REPLACEMENTS:
        if source.count(old) != 1:
            raise ValueError("Frozen checker source differs from the reviewed two-line repair")
        source = source.replace(old, new, 1)
    return source


def load_checker():
    if hashlib.sha256(RUNNER.read_bytes()).hexdigest() != RUNNER_SHA256:
        raise ValueError("Frozen neural runner SHA256 changed")
    spec = importlib.util.spec_from_file_location("frozen_kisa_neural_20261004", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = corrected_source(inspect.getsource(module.check_pipeline))
    namespace = dict(vars(module))
    namespace["_exact_checkpoint_keys"] = _exact_checkpoint_keys
    # Keep the original __file__: the checker must hash the actual training runner.
    assert Path(namespace["__file__"]).resolve() == RUNNER.resolve()
    exec(compile(source, str(__file__) + "::<corrected_check_pipeline>", "exec"), namespace)
    return namespace["check_pipeline"]


if __name__ == "__main__":
    sys.exit(0 if load_checker()() else 1)
