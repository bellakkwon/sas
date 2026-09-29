/* Read-only verification of saved private predictions and aggregate report.
   Use the same bundle, runner and output paths as 02. */

proc python;
submit;
from pathlib import Path
import runpy
import sys

bundle = Path('/home/student/scamlens_private/matched_kcbert_sas_private_20260917_v1')
runner = Path('/home/student/github/sas/kcbert_matched_20260917/run_matched_kcbert_portable_20260917.py')
output = Path('/home/student/scamlens_private/results_20260917_v1')
if not bundle.is_dir() or not runner.is_file() or not output.is_dir():
    raise RuntimeError('SCAMLENS_KCBERT_PRIVATE_PATH_MISSING')
old_argv = sys.argv[:]
try:
    sys.argv = [str(runner), '--bundle', str(bundle), '--check', '--output', str(output)]
    runpy.run_path(str(runner), run_name='__main__')
finally:
    sys.argv = old_argv
print('SCAMLENS_KCBERT_CHECK_RETURNED')
endsubmit;
run;
