/* Optional bounded smoke: one seed, one arm, two optimizer updates.
   No predictions, model weights, or research metrics are saved.
   Keep v2 unchanged; use a new version for another private root. */

proc python;
submit;
from pathlib import Path
import runpy
import sys

bundle = Path('/home/student/scamlens_private/matched_kcbert_sas_private_20260917_v1')
runner = Path('/home/student/github/sas/kcbert_matched_20260917/run_matched_kcbert_portable_20260917.py')
if not bundle.is_dir() or not runner.is_file():
    raise RuntimeError('SCAMLENS_KCBERT_PRIVATE_PATH_MISSING')
old_argv = sys.argv[:]
try:
    sys.argv = [str(runner), '--bundle', str(bundle), '--smoke']
    runpy.run_path(str(runner), run_name='__main__')
finally:
    sys.argv = old_argv
print('SCAMLENS_KCBERT_SMOKE_RETURNED_NOT_A_RESEARCH_RESULT')
endsubmit;
run;
