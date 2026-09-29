/* Reassemble a large private safetensors file from SAS Studio uploads.
   Upload model.safetensors.part.* files to PART_DIR first.
   This program does not train, download, upload to CAS, or overwrite output. */

%let part_dir=/home/student/scamlens_private/upload_parts;
%let part_prefix=model.safetensors.part.;
%let output_file=/home/student/scamlens_private/matched_kcbert_sas_private_20260917_v1/checkpoint/model.safetensors;

proc python;
submit;
from pathlib import Path
import hashlib
import json
import os
import stat
import tempfile

part_dir = Path(r"&part_dir")
part_prefix = r"&part_prefix"
output_file = Path(r"&output_file")

if not part_dir.is_dir():
    raise RuntimeError(f"SCAMLENS_KCBERT_PART_DIR_MISSING: {part_dir}")
if output_file.exists():
    raise RuntimeError(f"SCAMLENS_KCBERT_OUTPUT_EXISTS_REFUSING_OVERWRITE: {output_file}")

parts = sorted(part_dir.glob(part_prefix + "*"), key=lambda path: path.name)
if not parts:
    raise RuntimeError(f"SCAMLENS_KCBERT_PARTS_MISSING: {part_dir}/{part_prefix}*")
for path in parts:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"SCAMLENS_KCBERT_PART_INVALID: {path}")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        try:
            os.chmod(path, 0o600)
        except OSError as error:
            raise RuntimeError(f"SCAMLENS_KCBERT_PART_PERMISSION_TOO_OPEN: {path}") from error
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError(f"SCAMLENS_KCBERT_PART_PERMISSION_TOO_OPEN: {path}")

output_file.parent.mkdir(parents=True, exist_ok=True)
fd, temp_name = tempfile.mkstemp(prefix=".model.safetensors.", dir=output_file.parent)
os.close(fd)
temp_file = Path(temp_name)
total_bytes = 0
digest = hashlib.sha256()
try:
    with temp_file.open("wb") as destination:
        for part in parts:
            with part.open("rb") as source:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    destination.write(block)
                    digest.update(block)
                    total_bytes += len(block)
    os.chmod(temp_file, 0o600)
    os.replace(temp_file, output_file)
except Exception:
    temp_file.unlink(missing_ok=True)
    raise

print("SCAMLENS_KCBERT_REASSEMBLE_COMPLETE", json.dumps({
    "part_count": len(parts),
    "part_names": [path.name for path in parts],
    "bytes": total_bytes,
    "sha256": digest.hexdigest(),
    "output": str(output_file),
}, sort_keys=True))
endsubmit;
run;
