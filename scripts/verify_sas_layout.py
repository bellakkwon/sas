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


def verify_status_detail_arguments(entry: str) -> None:
    """Check balanced status calls and explicit masking, without emulating SAS."""
    code = re.sub(r"/\*.*?\*/", "", entry, flags=re.S)
    arities = {"sl_skip_step": 5, "sl_record_step": 7, "sl_append_master_log": 6}
    calls = re.finditer(r"%(sl_skip_step|sl_record_step|sl_append_master_log)\s*\(", code, re.I)
    for call in calls:
        name = call.group(1).lower()
        start = call.end()
        depth = 1
        arguments = []
        for pos in range(start, len(code)):
            char = code[pos]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    arguments.append(code[start:pos].strip())
                    break
            elif char == "," and depth == 1:
                arguments.append(code[start:pos].strip())
                start = pos + 1
        else:
            raise ValueError(f"Unbalanced status call: {name}")
        if len(arguments) != arities[name]:
            raise ValueError(f"Wrong status argument count: {name}")
        details = arguments[-1]
        if re.search(r"&details\b", details, re.I):
            raise ValueError(f"Status details forwarding must use %superq(details): {name}")
        if "=" not in details:
            continue
        quote = re.match(r"%(nrstr|bquote)\(", details, re.I)
        if not quote:
            raise ValueError(f"Unquoted status details can become a keyword argument: {name}")
        # The quote must enclose the entire description, not just a prefix.
        depth = 1
        for pos in range(quote.end(), len(details)):
            if details[pos] == "(":
                depth += 1
            elif details[pos] == ")":
                depth -= 1
                if depth == 0:
                    break
        if depth != 0 or pos != len(details) - 1:
            raise ValueError(f"Status details quoting does not enclose the description: {name}")
        if quote.group(1).lower() == "nrstr" and re.search(r"&\w+", details):
            raise ValueError("Dynamic status details need %bquote to resolve result values")


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


def verify_cas_and_summary_contract(entry: str) -> None:
    code = re.sub(r"/\*.*?\*/", "", entry, flags=re.S)
    options = re.search(r"%macro sl_validate_options;(.*?)%mend sl_validate_options;", code, re.S).group(1)
    compact = re.sub(r"\s+", "", options).lower()
    default = ('%if%length(%superq(sl_run_cas))=0%then%do;'
               '%if"%substr(%upcase(&sysvlong.),1,2)"="v."%then%letsl_run_cas=1;'
               '%else%letsl_run_cas=0;%end;')
    if default not in compact:
        raise ValueError("CAS default must preserve caller options and enable Viya only")
    if re.findall(r"%letsl_run_cas=[^;]*;", compact) != ["%letsl_run_cas=1;", "%letsl_run_cas=0;"]:
        raise ValueError("CAS option is overwritten outside the guarded default")
    summary = re.search(r"%macro sl_print_summary;(.*?)%mend sl_print_summary;", code, re.S).group(1)
    required = ['ods html(id=sl_summary) path=', 'file="run_summary.html"',
                'proc print data=work.scamlens_run_status', '%let _summary_err=&syserr.;',
                '%let _summary_cc=&syscc.;', 'ods html(id=sl_summary) close;',
                '%sl_expect_nonempty(&sl_output_root./run_summary.html, master_summary_html);']
    if any(token not in summary for token in required):
        raise ValueError("Summary needs its own ODS destination, captured result and output check")
    if [summary.index(token) for token in required] != sorted(summary.index(token) for token in required):
        raise ValueError("Summary ODS lifecycle must enclose printing and preserve its result")
    if '%if &_summary_err. ne 0 or &_summary_cc. ne 0 or &syscc. > 4 %then %do;' not in summary:
        raise ValueError("Summary output errors must stop execution")


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
    verify_status_detail_arguments(entry)
    verify_cas_and_summary_contract(entry)
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
