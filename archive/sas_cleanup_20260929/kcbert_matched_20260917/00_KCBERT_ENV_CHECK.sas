/* ScamLens KcBERT: SAS Viya Compute / PROC PYTHON environment check.
   No training, CAS upload, URL access, or model download is performed.
   Keep this reviewed v2 file unchanged; use a new version for another root.
   Never place model_rows.csv, edits.csv or checkpoint in a public Git repo. */

proc python;
submit;
from pathlib import Path
import importlib.metadata
import json
import stat
import sys

bundle = Path('/home/student/scamlens_private/matched_kcbert_sas_private_20260917_v1')
runner = Path('/home/student/github/sas/kcbert_matched_20260917/run_matched_kcbert_portable_20260917.py')
store = Path('/home/student/github/sas/kcbert_matched_20260917/kcbert_private_store_20260917.py')

def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None

print('SCAMLENS_KCBERT_SAS_PYTHON_ENV', json.dumps({
    'python': sys.version.split()[0],
    'executable': sys.executable,
    'torch': package_version('torch'),
    'transformers': package_version('transformers'),
    'numpy': package_version('numpy'),
    'scikit_learn': package_version('scikit-learn'),
    'bundle_exists': bundle.is_dir(),
    'runner_exists': runner.is_file(),
    'store_exists': store.is_file(),
    'input_exists': (bundle / 'model_rows.csv').is_file(),
    'edit_exists': (bundle / 'edits.csv').is_file(),
    'manifest_exists': (bundle / 'manifest.json').is_file(),
    'checkpoint_exists': (bundle / 'checkpoint' / 'model.safetensors').is_file(),
}, sort_keys=True))

if not bundle.is_dir() or not runner.is_file() or not store.is_file():
    raise RuntimeError('SCAMLENS_KCBERT_PRIVATE_PATH_MISSING')
for path in (bundle, bundle / 'model_rows.csv', bundle / 'edits.csv',
             bundle / 'manifest.json', bundle / 'checkpoint',
             bundle / 'checkpoint' / 'model.safetensors'):
    if path.is_symlink() or not path.exists() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError('SCAMLENS_KCBERT_PRIVATE_FILE_PERMISSION_OR_LINK')
missing = [name for name in ('torch', 'transformers', 'numpy')
           if package_version(name) is None]
if missing:
    raise RuntimeError('SCAMLENS_KCBERT_PYTHON_DEPENDENCY_MISSING:' + ','.join(missing))

import torch
print('SCAMLENS_KCBERT_DEVICE', json.dumps({
    'cuda_available': torch.cuda.is_available(),
    'mps_available': torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False,
}, sort_keys=True))
print('SCAMLENS_KCBERT_ENV_CHECK_COMPLETE')
endsubmit;
run;
