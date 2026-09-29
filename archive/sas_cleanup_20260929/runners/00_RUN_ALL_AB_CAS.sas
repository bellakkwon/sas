/*
  Full combined workflow for a fresh UTF-8 Compute session:
    historical common stages 01-08 -> current A/B stages 11-12 -> CASUSER.

  The common runner keeps its documented optional skips. Any stage recorded as
  requires_review blocks the A/B and CAS phases. The included AB/CAS runner
  explicitly uploads and promotes seven aggregate-only tables to CASUSER.
*/
%let projroot=/home/student/github;

%macro scall_abort(message);
  %put ERROR: &message.;
  %abort cancel;
%mend;

%macro scall_main;
  %local stage_n failed_n;
  %if not %sysfunc(fileexist(&projroot./sas/00_RUN_ALL.sas))
      or not %sysfunc(fileexist(&projroot./sas/00_RUN_AB_CAS.sas)) %then %do;
    %scall_abort(Full runner files are missing under &projroot./sas);
  %end;

  %include "&projroot./sas/00_RUN_ALL.sas";

  %if not %sysfunc(exist(work.scamlens_run_status)) %then %do;
    %scall_abort(00_RUN_ALL did not create its status table);
  %end;
  proc sql noprint;
    select count(distinct stage),
           sum(case when state='requires_review' then 1 else 0 end)
      into :stage_n trimmed, :failed_n trimmed
      from work.scamlens_run_status;
  quit;
  %if &syserr. ne 0 or &syscc. ne 0 %then %do;
    %scall_abort(Could not validate the 00_RUN_ALL status table);
  %end;
  %if &stage_n. ne 8 %then %do;
    %scall_abort(00_RUN_ALL status must contain exactly eight stages);
  %end;
  %if &failed_n. ne 0 %then %do;
    %scall_abort(At least one 00_RUN_ALL stage requires review; CAS was not changed);
  %end;

  %include "&projroot./sas/00_RUN_AB_CAS.sas";

  %if not %symexist(slva_complete) or &slva_complete. ne 1 %then %do;
    %scall_abort(A/B CAS phase did not complete);
  %end;
  %put NOTE: SCAMLENS_ALL_AB_CAS_RUN_COMPLETE. RUN_TAG=&run_tag. CASLIB=&slva_caslib.
    SUFFIX=&slva_suffix.;
%mend;

%scall_main;
