/*
  Combined current workflow: run A/B analysis 11 -> 12, then publish the
  seven aggregate-only tables to the user's private CASUSER caslib.

  Run this whole file in a fresh UTF-8 Compute session. Executing this file
  explicitly authorizes a CAS upload. It never drops or replaces a target.
  PROMOTE defaults to 1 for VA visibility; SAVE defaults to 0.
*/
%let projroot=/home/student/github;
%let scabcas_caslib=CASUSER;
%let scabcas_promote=1;
%let scabcas_save=0;
/* Leave blank for a run-specific 12-character suffix derived from run_tag. */
%let scabcas_suffix=;

%macro scabcas_abort(message);
  %put ERROR: &message.;
  %abort cancel;
%mend;

%macro scabcas_main;
  %global slva_caslib slva_suffix slva_upload slva_promote slva_save;

  %if not %sysfunc(fileexist(&projroot./sas/00_RUN_AB.sas))
      or not %sysfunc(fileexist(&projroot./sas/13_publish_ab_to_cas.sas)) %then %do;
    %scabcas_abort(Combined runner files are missing under &projroot./sas);
  %end;
  %if %length(%superq(scabcas_caslib))=0 %then %do;
    %scabcas_abort(Set scabcas_caslib before running the combined workflow);
  %end;
  %if (&scabcas_promote. ne 0 and &scabcas_promote. ne 1)
      or (&scabcas_save. ne 0 and &scabcas_save. ne 1) %then %do;
    %scabcas_abort(scabcas_promote and scabcas_save must each be 0 or 1);
  %end;

  %include "&projroot./sas/00_RUN_AB.sas";

  %if not %symexist(sc11_complete) or not %symexist(sc12_complete)
      or not %symexist(run_tag) %then %do;
    %scabcas_abort(00_RUN_AB did not create its completion context);
  %end;
  %if &sc11_complete. ne 1 or &sc12_complete. ne 1
      or not %sysfunc(exist(work.scab_run_context)) %then %do;
    %scabcas_abort(00_RUN_AB did not complete both analysis stages);
  %end;

  %let slva_caslib=&scabcas_caslib.;
  %if %length(%superq(scabcas_suffix))=0 %then
    %let slva_suffix=v%substr(%scan(%superq(run_tag),-1,_),1,11);
  %else %let slva_suffix=&scabcas_suffix.;
  %let slva_upload=1;
  %let slva_promote=&scabcas_promote.;
  %let slva_save=&scabcas_save.;

  %put NOTE: SCAMLENS_AB_CAS_TARGET=&slva_caslib. SUFFIX=&slva_suffix.;
  %put NOTE: SCAMLENS_AB_CAS_UPLOAD=1 PROMOTE=&slva_promote. SAVE=&slva_save.;
  %include "&projroot./sas/13_publish_ab_to_cas.sas";

  %if not %symexist(slva_complete) or &slva_complete. ne 1 %then %do;
    %scabcas_abort(CAS publish did not complete; inspect the log and partial targets);
  %end;
  %put NOTE: SCAMLENS_AB_CAS_RUN_COMPLETE. RUN_TAG=&run_tag. CASLIB=&slva_caslib.
    SUFFIX=&slva_suffix. PROMOTE=&slva_promote. SAVE=&slva_save.;
%mend;

%scabcas_main;
