/* Current workflow: pre-consensus A/B agreement, then consensus model strata.
   Extract the new AB bundle under /home/student/github.
   Each run creates a new folder. Return its contents and bundle MANIFEST.json.
   Run the whole program in a fresh SAS session if earlier code left open quotes. */
%let projroot=/home/student/github;
%let sasdata=&projroot./data/processed/sas;
%let run_tag=ab_20260914_%sysfunc(datetime(),hex16.);
%let runout=&projroot./outputs/&run_tag.;

%macro scab_check;
  %if &syscc ne 0 or &syserr ne 0 %then %do;
    %put ERROR: Runner stopped after an unsuccessful step.;
    %abort cancel;
  %end;
%mend;

proc printto; run;
%scab_check;
options source source2 notes;

%macro scab_prepare;
  %local made;
  %if not %sysfunc(fileexist(&sasdata./sas_reviewer_ab_20260914.csv))
      or not %sysfunc(fileexist(&sasdata./sas_consensus_predictions_20260914.csv))
      or not %sysfunc(fileexist(&projroot./sas/11_reviewer_ab_agreement.sas))
      or not %sysfunc(fileexist(&projroot./sas/12_consensus_model_comparison.sas)) %then %do;
    %put ERROR: Missing AB bundle input or program. Check projroot and extract all folders.;
    %abort cancel;
  %end;
  %if %sysfunc(fileexist(&runout.)) %then %do;
    %put ERROR: Output folder exists. Change run_tag and keep previous results.;
    %abort cancel;
  %end;
  %let made=0;
  data _null_;
    length created $1024;
    if not fileexist("&projroot./outputs") then created=dcreate('outputs',"&projroot.");
    created=dcreate("&run_tag.","&projroot./outputs");
    if not missing(created) then call symputx('made',1,'L');
  run;
  %scab_check;
  %if &made ne 1 %then %do;
    %put ERROR: Cannot create output folder. Check write permission.;
    %abort cancel;
  %end;
%mend;
%scab_prepare;

data work.scab_status;
  length stage $32 state $32;
  stop;
run;
%scab_check;

%macro scab_step(stage,program,completion);
  %local step_cc step_err;
  %global &completion.;
  %let &completion.=0;
  %let syscc=0;
  proc printto log="&runout./&stage..log" new; run;
  %put NOTE: SCAMLENS_AB_STAGE=&stage. SAS_VERSION=&sysvlong.;
  %put NOTE: INPUT_ROOT=&sasdata. OUTPUT_ROOT=&runout.;
  proc options option=encoding; run;
  ods html path="&runout." (url=none) file="&stage..html" style=HTMLBlue;
  %include "&projroot./sas/&program.";
  ods html close;
  %let step_cc=&syscc.;
  %let step_err=&syserr.;
  proc printto; run;
  data work.scab_one;
    length stage $32 state $32;
    stage="&stage.";
    if &step_cc.=0 and &step_err.=0 and &&&completion.=1 then state='completed_check_return';
    else state='failed';
  run;
  %scab_check;
  proc append base=work.scab_status data=work.scab_one; run;
  %scab_check;
  proc export data=work.scab_status outfile="&runout./run_status.csv" dbms=csv replace; run;
  %scab_check;
  %if &step_cc. ne 0 or &step_err. ne 0 or &&&completion. ne 1 %then %do;
    %put ERROR: Stage &stage. did not complete. Inspect its log in &runout.;
    %abort cancel;
  %end;
%mend;

%scab_step(11_reviewer_ab,11_reviewer_ab_agreement.sas,sc11_complete);
%scab_step(12_consensus_models,12_consensus_model_comparison.sas,sc12_complete);
data work.scab_run_context;
  length stage $32 run_tag $64 input_version $32 analysis_contract $32;
  stage='all_stages';
  run_tag="&run_tag.";
  input_version='ab_20260914';
  analysis_contract='ab_cas_20260915_v1';
run;
%scab_check;
proc print data=work.scab_status noobs; run;
%scab_check;
%put NOTE: Return &runout. and the AB bundle MANIFEST.json for numerical checks.;
%put NOTE: Program completion is provisional until returned tables and logs are checked.;
