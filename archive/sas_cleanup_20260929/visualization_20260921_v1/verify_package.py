#!/usr/bin/env python3
"""Standalone package verifier; it does not import the dataproj workspace."""
import argparse, hashlib, json, os, sys
from pathlib import Path
EXPECTED = {"data/u5_models.csv":15,"data/u5_features.csv":17,"data/u5_truncation.csv":6,"data/kisa_conditions.csv":105,"data/jev_comparison.csv":15,"data/jev_fusion.csv":15}
def digest(p):
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("package", nargs="?", default=Path(__file__).resolve().parent); a=ap.parse_args(); root=Path(a.package)
    for item in (root,*root.parents):
        if item.is_symlink(): raise SystemExit('FAIL: package ancestor symlink')
    root=root.resolve()
    m=json.loads((root/"manifest.json").read_text(encoding="utf-8")); files=m["files"]
    actual={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.relative_to(root).parts[0]!="outputs"}
    if any(p.is_symlink() for p in root.rglob("*") if p.relative_to(root).parts[0]!="outputs"): raise SystemExit("FAIL: symlink present")
    required=set(EXPECTED)|{"README.md","SAS_FINAL_VISUALIZATION_20260921.md","verify_package.py","sas/00_RUN_FINAL_VISUALIZATION_20260921.sas","sas/10_LOAD_FINAL_AGGREGATES.sas","sas/90_PUBLISH_FINAL_TO_CASUSER_20260921.sas"}
    if set(files)!=required: raise SystemExit("FAIL: manifest allowlist mismatch")
    listed=set(files)
    if actual-{ "manifest.json" } != listed: raise SystemExit("FAIL: file list mismatch")
    for rel,meta in files.items():
        if Path(rel).is_absolute() or ".." in Path(rel).parts: raise SystemExit("FAIL: invalid path")
        if not isinstance(meta,dict) or not isinstance(meta.get('sha256'),str) or not isinstance(meta.get('size_bytes'),int): raise SystemExit('FAIL: missing hash/size')
        p=root/rel
        if digest(p)!=meta["sha256"] or p.stat().st_size!=meta["size_bytes"]: raise SystemExit("FAIL: content/hash mismatch: "+rel)
    import csv
    for rel,n in EXPECTED.items():
        with (root/rel).open(encoding="utf-8",newline="") as f:
            rows=list(csv.reader(f))
        if len(rows)-1!=n: raise SystemExit("FAIL: row count: "+rel)
    print("OK: standalone aggregate package", root)
if __name__=="__main__": main()
