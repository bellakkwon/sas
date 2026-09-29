#!/usr/bin/env python3
"""Regression checks for missing modules, drift and unsafe extra inputs."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sas_layout", ROOT / "scripts/verify_sas_layout.py")
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class LayoutRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        manifest = json.loads((ROOT / layout.MANIFEST).read_text())
        paths = {layout.MANIFEST, *manifest["current_guides"], *manifest["active_sha256"],
                 *manifest["preserved_sha256"], *manifest["archived_sha256"],
                 *manifest["aggregate_sources"], "docs/SAS_FOLLOWUP_RUN_GUIDE_20260921.md"}
        for relative in paths:
            target = cls.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        # Guide links can point to directories and non-hashed current guide files.
        for relative in ("sas/RUNBOOK.md", "sas/README.md", "docs/SAS_ORGANIZATION_20260929.md"):
            shutil.copyfile(ROOT / relative, cls.root / relative)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_valid_tree(self):
        self.assertEqual(layout.verify(self.root)["sas_runtime"], "not_executed")

    def test_aggregate_tampering_rejected(self):
        self.assert_tampering_rejected("data/aggregates/final/u5_models.csv")

    def test_archive_tampering_rejected(self):
        self.assert_tampering_rejected("archive/sas_cleanup_20260929/runners/00_RUN_ALL.sas")

    def test_active_code_drift_rejected(self):
        self.assert_tampering_rejected("sas/00_RUN_ALL.sas")

    def assert_tampering_rejected(self, relative):
        path = self.root / relative
        before = path.read_bytes()
        try:
            path.write_bytes(before + b"\n/* changed */\n")
            with self.assertRaisesRegex(ValueError, "SHA-256|Aggregate"):
                layout.verify(self.root)
        finally:
            path.write_bytes(before)

    def test_missing_module_rejected(self):
        path = self.root / "sas/31_final_visualization.sas"
        before = path.read_bytes()
        try:
            path.unlink()
            with self.assertRaisesRegex(ValueError, "program list"):
                layout.verify(self.root)
        finally:
            path.write_bytes(before)

    def test_extra_runner_rejected(self):
        path = self.root / "sas/00_RUN_OTHER.sas"
        try:
            path.write_text("%put NOTE: old entrypoint;\n")
            with self.assertRaisesRegex(ValueError, "program list"):
                layout.verify(self.root)
        finally:
            path.unlink()

    def test_extra_aggregate_rejected(self):
        path = self.root / "data/aggregates/final/unapproved.csv"
        try:
            path.write_text("column\nsynthetic\n")
            with self.assertRaisesRegex(ValueError, "aggregate CSV"):
                layout.verify(self.root)
        finally:
            path.unlink()

    def test_zip_caller_cannot_predict_producer_filename(self):
        entry = (self.root / "sas/00_RUN_ALL.sas").read_text()
        producer = (self.root / "sas/99_ZIP_FOLLOWUP_OUTPUTS.sas").read_text()
        layout.verify_zip_return_contract(entry, producer)
        wrong = entry.replace("%let _zip_path = &sl_followup_zip_path.;",
                              "%let _zip_path = &sl_output_root./followup/&sl_followup_run..zip;")
        with self.assertRaisesRegex(ValueError, "ZIP caller predicts"):
            layout.verify_zip_return_contract(wrong, producer)


if __name__ == "__main__":
    unittest.main()
