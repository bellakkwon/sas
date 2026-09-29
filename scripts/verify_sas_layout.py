#!/usr/bin/env python3
"""Offline layout, provenance and static SAS contract checks; no SAS execution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "manifests/sas_organization_20260929.json"


def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_zip_return_contract(entry: str, module: str) -> None:
    caller = re.search(r"%macro sl_run_99\b(.*?)%mend sl_run_99;", entry, re.S).group(1)
    caller = re.sub(r"/\*.*?\*/", "", caller, flags=re.S)
    module = re.sub(r"/\*.*?\*/", "", module, flags=re.S)
    if not re.search(r"%let\s+sl_followup_zip_path\s*=\s*&zipfile\.;", module, re.I):
        raise ValueError("ZIP producer must return the actual generated filename")
    if not re.search(r"%let\s+_zip_path\s*=\s*&sl_followup_zip_path\.;", caller, re.I):
        raise ValueError("ZIP caller predicts a filename instead of using the producer return")
    if "sl_followup_zip_complete" not in caller or "sl_followup_zip_complete=1" not in module.replace(" ", ""):
        raise ValueError("ZIP completion flag is missing")
    if not (caller.index("%include") < caller.index("%let _zip_path")):
        raise ValueError("ZIP return is read before the producer executes")


def verify(root: Path = ROOT) -> dict:
    root = root.resolve()
    manifest = json.loads((root / MANIFEST).read_text())
    programs = sorted(p.relative_to(root).as_posix() for p in (root / "sas").glob("*.sas"))
    if programs != sorted(manifest["active_sha256"]):
        raise ValueError("Active program list differs from manifest")
    if [p for p in programs if Path(p).name.startswith("00_RUN")] != ["sas/00_RUN_ALL.sas"]:
        raise ValueError("Exactly one active 00_RUN entrypoint is required")
    elsewhere = [p.relative_to(root).as_posix() for p in root.rglob("*.sas")
                 if "archive" not in p.relative_to(root).parts
                 and ".git" not in p.relative_to(root).parts
                 and p.parent != root / "sas"]
    if elsewhere:
        raise ValueError(f"SAS programs outside sas/: {elsewhere}")
    for obsolete in ("followup_20260921_v1", "visualization_20260921_v1", "sas/kcbert_matched_20260917"):
        if (root / obsolete).exists():
            raise ValueError(f"Obsolete active folder: {obsolete}")
    for section in ("active_sha256", "preserved_sha256", "archived_sha256"):
        for relative, expected in manifest[section].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("Unsafe manifest path")
            if digest(root / relative) != expected:
                raise ValueError(f"SHA-256 mismatch: {relative}")
    for relative, source in manifest["aggregate_sources"].items():
        expected = manifest["archived_sha256"][source]
        if digest(root / relative) != expected:
            raise ValueError(f"Aggregate differs from frozen source: {relative}")
    aggregate_files = {p.relative_to(root).as_posix() for p in (root / "data/aggregates").rglob("*.csv")}
    if aggregate_files != set(manifest["aggregate_sources"]):
        raise ValueError("Unexpected or missing aggregate CSV")
    sources = {Path(p).name: (root / p).read_text() for p in programs}
    entry = sources["00_RUN_ALL.sas"]
    combined = "\n".join(sources.values())
    # All active modules are explicitly referenced by the entry or its helpers.
    missing = [name for name in sources if name != "00_RUN_ALL.sas"
               and name not in "\n".join(s for owner, s in sources.items() if owner != name)]
    if missing:
        raise ValueError(f"Unconnected modules: {missing}")
    for relative in re.findall(r'%include\s+"&projroot\./(sas/[^"&]+\.sas)"', combined, re.I):
        if not (root / relative).is_file():
            raise ValueError(f"Broken include: {relative}")
    for name, source in sources.items():
        code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        if re.search(r"followup_20260921_v1|visualization_20260921_v1|/Users/", code):
            raise ValueError(f"Obsolete/nonportable active path: {name}")
        if re.search(r"%let\s+projroot\s*=\s*/home/student/github\s*;", code, re.I):
            for line in code.splitlines():
                if re.search(r"%let\s+projroot\s*=", line, re.I) and "%if" not in line.lower():
                    raise ValueError(f"Caller projroot overwritten: {name}")
        if len(re.findall(r"%macro\b", code, re.I)) != len(re.findall(r"%mend\b", code, re.I)):
            raise ValueError(f"Unbalanced macro declarations: {name}")
        if len(re.findall(r"%do\b", code, re.I)) != len(re.findall(r"%end\b", code, re.I)):
            raise ValueError(f"Unbalanced macro blocks: {name}")
    for token in ("sl_profile", "AUTO", "PUBLIC", "FULL", "sl_run_cas", "sl_run_text", "sl_run_zip",
                  "uuidgen", "run_status.csv", "RUNNING", "SYSERR", "SYSCC", "%abort cancel"):
        if token.lower() not in entry.lower():
            raise ValueError(f"Missing runner contract: {token}")
    for arguments in re.findall(r"%macro\s+\w+\(([^)]*)\)", entry, re.I):
        if re.search(r"(?:^|,)\s*(?:syscc|syserr)\s*(?:,|$|=)", arguments, re.I):
            raise ValueError("Runner shadows automatic SYSCC/SYSERR variables")
    ordinary = re.search(r"%macro sl_run_ordinary\b(.*?)%mend sl_run_ordinary;", entry, re.S).group(1)
    ordinary = re.sub(r"/\*.*?\*/", "", ordinary, flags=re.S)
    if not (ordinary.index("%sl_record_step") < ordinary.index("%include")
            < ordinary.index("%let _cur_err") < ordinary.index("ods html close;")):
        raise ValueError("Runner loses stage/checkpoint status before cleanup")
    verify_zip_return_contract(entry, sources["99_ZIP_FOLLOWUP_OUTPUTS.sas"])
    cas15 = re.sub(r"/\*.*?\*/", "", sources["15_publish_kcbert_to_cas.sas"], flags=re.S)
    cas_statements = "\n".join(re.findall(r"proc casutil\b.*?quit;", cas15, re.I | re.S))
    if re.search(r"\bdroptable\b|\breplace\b", cas_statements, re.I):
        raise ValueError("CAS stage 15 may overwrite an existing publication")
    if "%scamlens_kcbert_pipeline(run_cas=0);" not in sources["14_kcbert_visuals.sas"]:
        raise ValueError("Stage 14 implicitly enables CAS")
    data_blocks = r"(?im)^\s*datalines;\n.*?^;"
    original_kcbert = (root / "archive/sas_cleanup_20260929/source_modules/14_kcbert_visuals.sas").read_text()
    if re.findall(data_blocks, sources["14_kcbert_visuals.sas"], re.S) != re.findall(data_blocks, original_kcbert, re.S):
        raise ValueError("Embedded KcBERT numeric input changed")
    original = (root / "archive/sas_cleanup_20260929/runners/00_RUN_ALL.sas")
    if not original.is_file():
        raise ValueError("Original entrypoint was not preserved")
    for path in manifest["current_guides"]:
        source = (root / path).read_text()
        for link in re.findall(r"\]\(([^)]+)\)", source):
            if link.startswith(("http:", "https:", "#", "mailto:")):
                continue
            target = link.split("#", 1)[0]
            if target and not ((root / path).parent / target).exists():
                raise ValueError(f"Broken current guide link: {path}: {target}")
    return {"scope": "offline_layout_integrity_and_static_contract", "sas_runtime": "not_executed",
            "active_programs": len(programs), "active_entrypoints": 1,
            "archived_files_verified": len(manifest["archived_sha256"]),
            "preserved_files_verified": len(manifest["preserved_sha256"]),
            "aggregate_csvs_verified": len(aggregate_files), "status": "passed"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
