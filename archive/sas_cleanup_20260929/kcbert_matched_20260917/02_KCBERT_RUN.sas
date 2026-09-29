/* Full exploratory KcBERT run in SAS Viya Compute Python.
   First run 00 and 01 in the SAME configured Compute context. The private
   runner verifies hashes and resumes only completed arms of the same run.
   No CAS upload or public output. Use a new, empty private output directory.
   On an operational copy, change slkc_confirm to YES only after reviewing
   preflight and resources. Keep reviewed v2 unchanged for another root. */

%let slkc_confirm=NO;
%macro slkc_run;
  %if %upcase(&slkc_confirm) ne YES %then %do;
    %put ERROR: SCAMLENS_KCBERT_RUN_NOT_CONFIRMED. Set slkc_confirm=YES after preflight.;
    %abort cancel;
  %end;

  proc python;
  submit;
from pathlib import Path
import runpy
import sys

bundle = Path('/home/student/scamlens_private/matched_kcbert_sas_private_20260917_v1')
runner = Path('/home/student/github/sas/kcbert_matched_20260917/run_matched_kcbert_portable_20260917.py')
output = Path('/home/student/scamlens_private/results_20260917_v1')
allow_cpu_full_run = False  # On an operational copy, after measuring CPU time/quota.
if not bundle.is_dir() or not runner.is_file():
    raise RuntimeError('SCAMLENS_KCBERT_PRIVATE_PATH_MISSING')
if output == bundle or output == bundle.parent:
    raise RuntimeError('SCAMLENS_KCBERT_OUTPUT_SCOPE_INVALID')
old_argv = sys.argv[:]
try:
    sys.argv = [str(runner), '--bundle', str(bundle), '--run',
                '--output', str(output), '--max-arms', '1']
    if allow_cpu_full_run:
        sys.argv.append('--allow-cpu-full-run')
    runpy.run_path(str(runner), run_name='__main__')
finally:
    sys.argv = old_argv
print('SCAMLENS_KCBERT_RUN_RETURNED_CHECK_RESULT_STATUS')
  endsubmit;
  run;
%mend;
%slkc_run;
