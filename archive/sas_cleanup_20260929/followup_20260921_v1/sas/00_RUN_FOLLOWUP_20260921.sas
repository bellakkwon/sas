/*---------------------------------------------------------------------------
  S1 — Follow-up runner: one include runs all four aggregate stages.

  Usage (two lines in SAS Studio / Enterprise Guide):
    %let projroot = /home/student/github;
    %include "&projroot./followup_20260921_v1/sas/00_RUN_FOLLOWUP_20260921.sas";

  The package directory &projroot./followup_20260921_v1 holds sas/, data/,
  README and a manifest. Each run creates a fresh UUID output directory
  under outputs/ with separate step logs, ODS reports, and a run status
  file. No model fitting, no CAS publication, no training, no API, no
  network. Any stage error (SYSCC/SYSERR, captured before PRINTTO restore)
  or missing/empty expected output aborts with a clear message; a file
  alone never counts as success and existing logs are never erased.
  Stage 1 additionally requires its three readback CSVs. status=ok is
  written only after the summary report itself passes its guards.
  Static review only; SAS runtime here is executed by the user, not
  claimed by the authors.

  Isolation notes: stage modules 16/comparison issue `ods _all_ close`
  and set global root_dir/data_dir/out_dir/agg_csv. This runner therefore
  re-establishes its own ODS destination per stage AFTER each include and
  sets root_dir/agg_csv freshly BEFORE each include. Fusion auto-invokes
  %verify_aggregate exactly once on %include, so the runner never calls it
  again. All logic lives inside %run_followup (no conditional open code).
---------------------------------------------------------------------------*/
%global projroot root_dir data_dir out_dir agg_csv;

/* Portable projroot default without conditional open code. */
data _null_;
  if symget('projroot') = '' then call symputx('projroot', '/home/student/github');
run;

/* Aggregate-only file copy helper (top-level macro definition is portable;
   it is only CALLED from inside the runner wrapper). */
%macro fu_copy(src, dst);
  data _null_;
    infile "&src" lrecl=32767 truncover;
    file "&dst" lrecl=32767;
    input;
    put _infile_;
  run;
%mend fu_copy;

/* Expected-file guard: the file must exist and be nonempty. A file alone
   never counts as success; callers also test SYSCC/SYSERR. */
%macro fu_expect_nonempty(path, label);
  data _null_;
    length p $2048;
    p = "%superq(path)";
    /* FOPEN takes a fileref, not a physical path. */
    rc = filename('_fuchk', p);
    if rc ne 0 then do;
      put "ERROR: cannot assign expected output fileref (&label)";
      abort cancel;
    end;
    fid = fopen('_fuchk', 'I', 1, 'B');
    if fid = 0 then do;
      put "ERROR: expected output missing (&label)";
      abort cancel;
    end;
    /* Read one byte: do not depend on localized FINFO item names. */
    read_rc = fread(fid);
    rc = fclose(fid);
    rc = filename('_fuchk');
    if read_rc ne 0 then do;
      put "ERROR: expected output empty (&label)";
      abort cancel;
    end;
  run;
%mend fu_expect_nonempty;

/* Echo bounded error/warning context after PRINTTO is restored so that
   the SAS Studio log contains the first failure, not only the wrapper. */
%macro fu_echo_failure(log_path);
  data _null_;
    infile "%superq(log_path)" lrecl=32767 truncover end=eof;
    retain context 0 printed 0;
    input;
    if prxmatch('/^\s*(ERROR|WARNING)\b/i', _infile_) then context=8;
    if context>0 and printed<200 then do;
      put _infile_;
      printed+1;
      context=context-1;
    end;
    if eof and printed=0 then
      put 'NOTE: No ERROR/WARNING excerpt found. Inspect the full stage log.';
  run;
%mend fu_echo_failure;

%macro run_followup;
  %local pkg runid rundir s1root s2root s4csv
         _s1err _s1cc _s2err _s2cc _s3err _s3cc _s4err _s4cc;

  %let pkg = &projroot./followup_20260921_v1;
  /* Unique run folder; dashes are valid in directory names. */
  %let runid = run_%sysfunc(uuidgen());
  %let rundir = &pkg./outputs/&runid;
  %let s1root = &rundir./stage_u5;
  %let s2root = &rundir./stage_cmp;
  %let s4csv = &pkg./data/kisa_ocr_diagnostics_20260921.csv;

  /* Fresh output root; reject an existing folder instead of overwriting. */
  data _null_;
    length base run $2048;
    base = symget('pkg') || '/outputs';
    if not fileexist(base) then do;
      rc = dcreate('outputs', symget('pkg'));
    end;
    run = symget('rundir');
    if fileexist(run) then do;
      put 'ERROR: run directory already exists; refusing to overwrite: ' run;
      abort cancel;
    end;
    rc = dcreate(scan(run, -1, '/'), substr(run, 1, length(run) - length(scan(run, -1, '/')) - 1));
    if not fileexist(run) then do;
      put 'ERROR: cannot create run output directory: ' run;
      abort cancel;
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* ---- Stage 1: U5 error diagnostics (existing module, own ODS) ---- */
  data _null_;
    rc = dcreate('stage_u5', symget('rundir'));
    rc = dcreate('data', symget('s1root'));
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  %fu_copy(&pkg./data/u5/eval_metadata_summary.csv, &s1root./data/eval_metadata_summary.csv)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  %fu_copy(&pkg./data/u5/model_seed_diagnostics.csv, &s1root./data/model_seed_diagnostics.csv)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  %fu_copy(&pkg./data/u5/error_breakdown_by_feature.csv, &s1root./data/error_breakdown_by_feature.csv)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  %fu_copy(&pkg./data/u5/truncation_audit_summary.csv, &s1root./data/truncation_audit_summary.csv)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  %fu_copy(&pkg./data/u5/persistent_error_summary.csv, &s1root./data/persistent_error_summary.csv)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  %fu_copy(&pkg./data/u5/paired_transition_summary.csv, &s1root./data/paired_transition_summary.csv)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  proc printto log="&rundir./stage_u5.log" new; run;
  %let root_dir = &s1root;
  %include "&pkg./sas/16_u5_error_diagnostics.sas";
  /* Capture module status BEFORE restoring PRINTTO, which resets SYSERR. */
  %let _s1err = &syserr;
  %let _s1cc = &syscc;
  proc printto; run;
  %if &_s1err > 0 or &_s1cc > 4 %then %do;
    %put ERROR: stage_u5 failed (SYSCC=&_s1cc SYSERR=&_s1err). See &rundir./stage_u5.log.;
    %fu_echo_failure(&rundir./stage_u5.log)
    %abort cancel;
  %end;
  %fu_expect_nonempty(&s1root./outputs/u5_error_diagnostics_report.html, stage_u5_report)
  %fu_expect_nonempty(&s1root./outputs/sas_model_readback.csv, stage_u5_model_readback)
  %fu_expect_nonempty(&s1root./outputs/sas_arm_readback.csv, stage_u5_arm_readback)
  %fu_expect_nonempty(&s1root./outputs/sas_transition_readback.csv, stage_u5_transition_readback)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* ---- Stage 2: Jev comparison (existing module, own ODS) ---- */
  data _null_;
    rc = dcreate('stage_cmp', symget('rundir'));
    if not fileexist(symget('s2root')) then do;
      put 'ERROR: cannot create stage_cmp directory.';
      abort cancel;
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  proc printto log="&rundir./stage_cmp.log" new; run;
  %let root_dir = &s2root;
  %let agg_csv = &pkg./data/comparison/aggregate.csv;
  %include "&pkg./sas/jev_kcbert_comparison_20260920.sas";
  /* Capture module status BEFORE restoring PRINTTO, which resets SYSERR. */
  %let _s2err = &syserr;
  %let _s2cc = &syscc;
  proc printto; run;
  %if &_s2err > 0 or &_s2cc > 4 %then %do;
    %put ERROR: stage_cmp failed (SYSCC=&_s2cc SYSERR=&_s2err). See &rundir./stage_cmp.log.;
    %fu_echo_failure(&rundir./stage_cmp.log)
    %abort cancel;
  %end;
  %fu_expect_nonempty(&s2root./outputs/jev_kcbert_comparison_summary.html, stage_cmp_report)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* ---- Stage 3: Jev fusion aggregate (runner-managed ODS; the source
         auto-invokes %verify_aggregate exactly once on include, so the
         runner never calls it again) ---- */
  proc printto log="&rundir./stage_fus.log" new; run;
  ods html path="&rundir." (url=none) file="stage_fus.html" style=HTMLBlue;
  ods graphics off;
  %let agg_csv = &pkg./data/fusion/aggregate.csv;
  %include "&pkg./sas/jev_kcbert_fusion_20260920.sas";
  proc sql noprint;
    create table fus_arms as
    select arm, role, n, tp, tn, fp, fn, threshold
    from aggregate order by arm, role;
  quit;
  proc print data=fus_arms noobs label;
    var arm role n tp tn fp fn threshold;
    label arm='암' role='역할' n='건수' threshold='임계값';
    title 'Jev 결합 집계 — 암·역할별 확인표 (사후 진단, 합산 없음)';
  run;
  ods html close;
  /* Capture stage status BEFORE restoring PRINTTO, which resets SYSERR. */
  %let _s3err = &syserr;
  %let _s3cc = &syscc;
  proc printto; run;
  %if &_s3err > 0 or &_s3cc > 4 %then %do;
    %put ERROR: stage_fus failed (SYSCC=&_s3cc SYSERR=&_s3err). See &rundir./stage_fus.log.;
    %fu_echo_failure(&rundir./stage_fus.log)
    %abort cancel;
  %end;
  %fu_expect_nonempty(&rundir./stage_fus.html, stage_fus_report)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* ---- Stage 4: KISA OCR diagnostics (new module, runner-managed ODS) ---- */
  data _null_;
    if not fileexist(symget('s4csv')) then do;
      put 'ERROR: C2 aggregate CSV missing; final data package not complete.';
      abort cancel;
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  proc printto log="&rundir./stage_kisa.log" new; run;
  ods html path="&rundir." (url=none) file="kisa_stage.html" style=HTMLBlue;
  ods graphics on / reset=all width=9in height=5.5in imagefmt=png;
  %include "&pkg./sas/17_external_kisa_diagnostics.sas";
  %kisa17(csv=&s4csv, outdir=&rundir);
  ods html close;
  ods graphics off;
  /* Capture stage status BEFORE restoring PRINTTO, which resets SYSERR. */
  %let _s4err = &syserr;
  %let _s4cc = &syscc;
  proc printto; run;
  %if &_s4err > 0 or &_s4cc > 4 %then %do;
    %put ERROR: stage_kisa failed (SYSCC=&_s4cc SYSERR=&_s4err). See &rundir./stage_kisa.log.;
    %fu_echo_failure(&rundir./stage_kisa.log)
    %abort cancel;
  %end;
  %fu_expect_nonempty(&rundir./kisa_stage.html, stage_kisa_report)
  %fu_expect_nonempty(&rundir./kisa_verified_readback.csv, stage_kisa_readback)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* ---- Run summary (runner ODS, opened last to avoid module side effects) ---- */
  data fu_status;
    length stage $16 log $64 report $256 status $16;
    stage = 'stage_u5'; log = 'stage_u5.log';
    report = symget('s1root') || '/outputs/u5_error_diagnostics_report.html';
    status = 'ok'; output;
    stage = 'stage_cmp'; log = 'stage_cmp.log';
    report = symget('s2root') || '/outputs/jev_kcbert_comparison_summary.html';
    status = 'ok'; output;
    stage = 'stage_fus'; log = 'stage_fus.log'; report = 'stage_fus.html';
    status = 'ok'; output;
    stage = 'stage_kisa'; log = 'stage_kisa.log'; report = 'kisa_stage.html';
    status = 'ok'; output;
  run;
  ods html path="&rundir." (url=none) file="followup_summary.html" style=HTMLBlue;
  proc print data=fu_status noobs label;
    var stage log report status;
    label stage='단계' log='로그' report='산출물' status='상태';
    title 'SAS 후속 실행 요약 (집계 전용, 서버 실행 기록용)';
  run;
  ods html close;
  %if &syserr > 0 or &syscc > 4 %then %do;
    %put ERROR: followup summary report failed (SYSCC/SYSERR).;
    %abort cancel;
  %end;
  %fu_expect_nonempty(&rundir./followup_summary.html, followup_summary)
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
  /* status=ok is written only after every stage and the summary report
     itself have passed their SYSCC/SYSERR and output guards. */
  data _null_;
    file "&rundir./run_status.txt";
    put 'status=ok stages=4 runid=' "&runid";
    if _error_ then do;
      put 'ERROR: cannot write run_status.txt';
      abort cancel;
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;
%mend run_followup;
%run_followup;
