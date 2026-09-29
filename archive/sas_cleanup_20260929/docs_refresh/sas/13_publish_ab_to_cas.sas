/* Optional adapter: run AFTER the updated 00_RUN_AB in the SAME Compute session.
   Default: prepare aggregate WORK tables only; do not connect to CAS.
   To upload, explicitly set slva_upload=1, slva_caslib and a fresh slva_suffix.
   Promotion and persistent SAVE each require their own explicit 1 flag.
   Never drops/replaces an existing CAS table or file. Not an atomic transaction:
   on failure, keep the log and any new partial tables; do not mark complete. */
%macro slva_check;
  %if &syscc ne 0 or &syserr ne 0 %then %do;
    %put ERROR: CAS adapter stopped after an unsuccessful step. Inspect the log.;
    %abort cancel;
  %end;
%mend;

%macro slva_context;
  length run_tag $64 input_version $32 analysis_contract $32;
  run_tag="&run_tag.";
  input_version='ab_20260914';
  analysis_contract='ab_cas_20260915_v1';
%mend;

%macro slva_compare(source=,target=,keys=);
  %local compare_rc;
  /* Read back into Compute, sort by unique keys, and compare every value.
     Do not assume row order survives a CAS round trip. */
  data work.slva_readback; set slvcas.&target.; run;
  %slva_check;
  proc sort data=work.slva_readback; by &keys.; run;
  %slva_check;
  proc sort data=work.&source. out=work.slva_baseline; by &keys.; run;
  %slva_check;
  proc compare base=work.slva_baseline compare=work.slva_readback
      method=absolute criterion=1e-10 noprint;
    id &keys.;
  run;
  %let compare_rc=&sysinfo.;
  %slva_check;
  /* Bits 1-6 concern label/type-label/format/informat/length metadata.
     Values, missingness, row/variable coverage, types and duplicate IDs
     (bits 7-16) must all agree. Native CAS metadata can differ. */
  %if %sysfunc(band(&compare_rc.,65472)) ne 0 %then %do;
    %put ERROR: CAS readback differs for &target. SYSINFO=&compare_rc.;
    %abort cancel;
  %end;
%mend;

%macro slva_main;
  %global slva_upload slva_promote slva_save slva_caslib slva_suffix
    slva_prepared slva_complete;
  %local i source target count_expected actual_n bad context_n context_bad
    status_n status_bad source_list target_list expected_list key_list;
  %let slva_prepared=0;
  %let slva_complete=0;
  %if %length(%superq(slva_upload))=0 %then %let slva_upload=0;
  %if %length(%superq(slva_promote))=0 %then %let slva_promote=0;
  %if %length(%superq(slva_save))=0 %then %let slva_save=0;
  %if (%superq(slva_upload) ne 0 and %superq(slva_upload) ne 1)
      or (%superq(slva_promote) ne 0 and %superq(slva_promote) ne 1)
      or (%superq(slva_save) ne 0 and %superq(slva_save) ne 1) %then %do;
    %put ERROR: slva_upload slva_promote slva_save must each be 0 or 1.;
    %abort cancel;
  %end;
  %if &slva_upload.=0 and (&slva_promote.=1 or &slva_save.=1) %then %do;
    %put ERROR: Promotion or save requires explicit upload permission.;
    %abort cancel;
  %end;
  %if not %symexist(sc11_complete) or not %symexist(sc12_complete)
      or not %symexist(run_tag) %then %do;
    %put ERROR: Run updated 00_RUN_AB first in this Compute session.;
    %abort cancel;
  %end;
  %if &sc11_complete. ne 1 or &sc12_complete. ne 1 %then %do;
    %put ERROR: Both analysis stages must complete before preparing CAS tables.;
    %abort cancel;
  %end;
  %if not %sysfunc(exist(work.scab_run_context)) or not %sysfunc(exist(work.scab_status)) %then %do;
    %put ERROR: Missing successful-run context. Old WORK results are not accepted.;
    %abort cancel;
  %end;
  %slva_check;
  proc sql noprint;
    select count(*) into :context_n trimmed from work.scab_run_context;
    select count(*) into :context_bad trimmed from work.scab_run_context
      where stage ne 'all_stages' or run_tag ne "&run_tag." or input_version ne 'ab_20260914'
        or analysis_contract ne 'ab_cas_20260915_v1';
    select count(distinct stage) into :status_n trimmed from work.scab_status;
    select count(*) into :status_bad trimmed from work.scab_status
      where stage not in ('11_reviewer_ab','12_consensus_models') or state ne 'completed_check_return';
    select count(*) into :actual_n trimmed from work.scab_status;
  quit;
  %slva_check;
  %if &context_n. ne 1 or &context_bad. ne 0 or &status_n. ne 2
      or &actual_n. ne 2 or &status_bad. ne 0 %then %do;
    %put ERROR: Stale or invalid AB run context.;
    %abort cancel;
  %end;
  %let source_list=sc11_category_cells sc11_agreement sc11_action_cells sc11_final_category_cells sc12_metrics sc12_strata sc12_seed_means;
  %let target_list=ab_category ab_agreement ab_action ab_final model_seed model_strata model_mean;
  %let expected_list=16 9 28 4 35 280 7;
  %let key_list=a_category b_category|measure|action_code a_value b_value|final_category|model seed|model seed original_label final_category|model;
  %do i=1 %to 7;
    %let source=%scan(&source_list.,&i.);
    %if not %sysfunc(exist(work.&source.)) %then %do;
      %put ERROR: Missing aggregate table &source.;
      %abort cancel;
    %end;
    proc sql noprint; select count(*) into :actual_n trimmed from work.&source.; quit;
    %slva_check;
    %let count_expected=%scan(&expected_list.,&i.);
    %if &actual_n. ne &count_expected. %then %do;
      %put ERROR: Unexpected aggregate row count for &source.;
      %abort cancel;
    %end;
    proc sort data=work.&source. out=work.slva_key_check
        nodupkey dupout=work.slva_duplicate_keys;
      by %scan(&key_list.,&i.,|);
    run;
    %slva_check;
    proc sql noprint;
      select count(*) into :bad trimmed from work.slva_duplicate_keys;
    quit;
    %slva_check;
    %if &bad. ne 0 %then %do;
      %put ERROR: Duplicate aggregate keys for &source.;
      %abort cancel;
    %end;
  %end;
  /* Explicit column allowlists exclude review IDs, text and reviewer notes. */
  proc format;
    value slvacat 1='위험 요구 관찰' 2='일상 안내·대화 가능'
      3='명확한 사기 요구 없는 홍보' 4='문맥 부족';
    value slvaact 1='앱/원격접근' 2='회신 전화' 3='연락 채널 변경'
      4='자격정보/인증' 5='보이는 행동 없음' 6='결제/이체' 7='불명확';
  run;
  %slva_check;
  data work.slva_ab_category;
    set work.sc11_category_cells(keep=a_category b_category n);
    length a_label b_label $96 unit $48;
    a_label=put(a_category,slvacat.); b_label=put(b_category,slvacat.);
    unit='unique_review'; %slva_context;
  run;
  %slva_check;
  data work.slva_ab_agreement;
    set work.sc11_agreement(keep=measure n agree_n agreement kappa);
    length measure_label $96 unit $48;
    if measure='category' then measure_label='범주 일치';
    else if measure='action_set' then measure_label='행동 집합 전체 일치';
    else measure_label=put(input(scan(measure,2,'_'),best32.),slvaact.);
    unit='unique_review_per_measure'; %slva_context;
    label agreement='합의 전 일치율' kappa='비가중 Cohen kappa';
    format agreement percent8.2 kappa 8.4;
  run;
  %slva_check;
  data work.slva_ab_action;
    set work.sc11_action_cells(keep=action_code a_value b_value n);
    length action_label $96 unit $48;
    action_label=put(action_code,slvaact.);
    unit='unique_review_per_action'; %slva_context;
  run;
  %slva_check;
  data work.slva_ab_final;
    set work.sc11_final_category_cells(keep=final_category n proportion);
    length category_label $96 unit $48;
    category_label=put(final_category,slvacat.); unit='unique_review';
    %slva_context;
    format proportion percent8.2;
  run;
  %slva_check;
  data work.slva_model_seed;
    set work.sc12_metrics(keep=model seed rows tp fn fp tn recall fpr f1);
    length unit aggregation_method $48;
    positive_n=tp+fn; negative_n=fp+tn;
    unit='review_seed_per_model'; aggregation_method='per_seed';
    %slva_context;
    format recall fpr f1 percent8.2;
  run;
  %slva_check;
  data work.slva_model_strata;
    set work.sc12_strata(keep=model seed original_label final_category n tp fn fp tn recall fpr);
    length category_label $96 unit aggregation_method $48;
    category_label=put(final_category,slvacat.);
    positive_n=tp+fn; negative_n=fp+tn; sample_present=(n>0);
    unit='review_seed_per_model_stratum'; aggregation_method='per_seed_per_stratum';
    %slva_context;
    format recall fpr percent8.2;
  run;
  %slva_check;
  data work.slva_model_mean;
    set work.sc12_seed_means(keep=model recall fpr f1);
    length unit aggregation_method $48;
    seed_count=5; unit='model'; aggregation_method='unweighted_mean_of_five_seed_rates';
    %slva_context;
    format recall fpr f1 percent8.2;
  run;
  %slva_check;
  %let slva_prepared=1;
  %if &slva_upload.=0 %then %do;
    %put NOTE: SCAMLENS_CAS_PREPARED_NOT_UPLOADED. Seven aggregate WORK tables ready.;
    %return;
  %end;
  /* Explicit destination and short version suffix, never an implicit Public. */
  %if %length(%superq(slva_caslib))=0 or %length(%superq(slva_suffix))=0 %then %do;
    %put ERROR: Set slva_caslib and a fresh slva_suffix before enabling upload.;
    %abort cancel;
  %end;
  %if not %sysfunc(nvalid(%superq(slva_caslib),v7))
      or not %sysfunc(nvalid(%superq(slva_suffix),v7))
      or %length(%superq(slva_suffix))>12 %then %do;
    %put ERROR: CASLIB and suffix must be V7 names. Suffix maximum is 12 characters.;
    %abort cancel;
  %end;
  %if %sysfunc(libref(slvcas))=0 %then %do;
    %put ERROR: SLVCAS libref already assigned. Use a clean adapter session context.;
    %abort cancel;
  %end;
  cas slvacas;
  %slva_check;
  libname slvcas cas sessref=slvacas caslib="&slva_caslib.";
  %slva_check;
  /* Check every target before the first load; no DROP or REPLACE fallback. */
  %do i=1 %to 7;
    %let target=%scan(&target_list.,&i.)_&slva_suffix.;
    %if %sysfunc(exist(slvcas.&target.)) %then %do;
      %put ERROR: Target &target. exists. Choose a new suffix, do not overwrite.;
      %abort cancel;
    %end;
  %end;
  %do i=1 %to 7;
    %let source=slva_%scan(&target_list.,&i.);
    %let target=%scan(&target_list.,&i.)_&slva_suffix.;
    proc casutil sessref=slvacas;
      load data=work.&source. outcaslib="&slva_caslib." casout="&target.";
    quit;
    %slva_check;
    %slva_compare(source=&source.,target=&target.,keys=%scan(&key_list.,&i.,|));
  %end;
  /* Only verified session tables reach optional persistence / promotion. */
  %do i=1 %to 7;
    %let target=%scan(&target_list.,&i.)_&slva_suffix.;
    %if &slva_save.=1 %then %do;
      proc casutil sessref=slvacas;
        save casdata="&target." incaslib="&slva_caslib."
          outcaslib="&slva_caslib." casout="&target..sashdat";
      quit;
      %slva_check;
    %end;
    %if &slva_promote.=1 %then %do;
      proc casutil sessref=slvacas;
        promote casdata="&target." incaslib="&slva_caslib."
          outcaslib="&slva_caslib." casout="&target.";
      quit;
      %slva_check;
    %end;
  %end;
  %let slva_complete=1;
  %put NOTE: SCAMLENS_CAS_UPLOAD_VERIFIED. PROMOTE=&slva_promote. SAVE=&slva_save.;
  %put NOTE: Confirm table visibility and aggregation settings inside Visual Analytics.;
%mend;
%slva_main;
