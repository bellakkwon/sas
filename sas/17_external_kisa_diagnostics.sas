/*---------------------------------------------------------------------------
  S1 — KISA OCR diagnostics aggregate verification (follow-up stage 4).

  Reads only the public 19-column aggregate CSV (plan contract):
    cohort,seed,condition,n,tp,tn,fp,fn,
    baseline_tp,baseline_tn,baseline_fp,baseline_fn,
    corrected_fp,corrected_fn,new_fp,new_fn,threshold,recall,fpr
  Cohorts: kisa_unique, kisa_representatives, normal_candidates.
  Conditions: original128, ocr_delete128, cap300, ocr_delete300,
              ocr_unk128, ocr_unk300, head_tail128.
  Seeds: 42, 101, 202, 303, 404. Expect 3*5*7 = 105 rows, one per key.

  Entry: %kisa17(csv=, outdir=). No global macro variables, no ODS open or
  close side effects; the caller manages ODS destinations. A verified
  readback CSV is exported to &outdir for return. No model fitting,
  no CAS, no network. Static review only; SAS runtime is unverified.
---------------------------------------------------------------------------*/
%macro kisa17(csv=, outdir=);
  %local header_exp;

  /* 0. Exact header order (first row); fail closed on mismatch. */
  data _null_;
    infile "%superq(csv)" lrecl=32767 obs=1 truncover;
    input header :$32767.;
    if _error_ then do;
      put 'ERROR: kisa CSV header row unreadable.';
      abort cancel;
    end;
    length expected $32767;
    expected = 'cohort,seed,condition,n,tp,tn,fp,fn,baseline_tp,baseline_tn,'
      || 'baseline_fp,baseline_fn,corrected_fp,corrected_fn,new_fp,new_fn,'
      || 'threshold,recall,fpr';
    if strip(header) ne expected then do;
      put 'ERROR: kisa CSV header/order mismatch.';
      abort cancel;
    end;
  run;

  /* Drop stale WORK tables so a previous run cannot mask a failed read. */
  proc datasets lib=work nolist;
    delete kisa_agg kisa_grid kisa_dups kisa_base128;
  quit;

  /* 1. Read with explicit columns; reject parse errors and extra columns. */
  data kisa_agg;
    infile "%superq(csv)" lrecl=32767 encoding="utf-8" dsd dlm="," firstobs=2 truncover;
    length cohort $24 condition $16 _extra $32767;
    input cohort $ seed condition $ n tp tn fp fn
          baseline_tp baseline_tn baseline_fp baseline_fn
          corrected_fp corrected_fn new_fp new_fn
          threshold recall fpr _extra $;
    if _error_ then do;
      put 'ERROR: kisa CSV parse error.';
      abort cancel;
    end;
    if not missing(strip(_extra)) then do;
      put 'ERROR: kisa CSV has more than 19 columns.';
      abort cancel;
    end;
    drop _extra;
  run;
  data _null_;
    if 0 then set kisa_agg nobs=nobs;
    if nobs = 0 then do;
      put 'ERROR: kisa CSV has no data rows.';
      abort cancel;
    end;
    stop;
  run;

  /* 2. Exact key grid, known levels, no duplicate or missing cells. */
  proc sort data=kisa_agg out=kisa_grid nodupkey dupout=kisa_dups;
    by cohort seed condition;
  run;
  data _null_;
    if 0 then set kisa_dups nobs=ndup;
    if ndup > 0 then do;
      put 'ERROR: duplicate cohort-seed-condition cells.';
      abort cancel;
    end;
    stop;
  run;
  data _null_;
    set kisa_grid end=eof;
    by cohort seed condition;
    retain ncell;
    if _n_ = 1 then ncell = 0;
    ncell + 1;
    if last.condition then do;
      if cohort not in ('kisa_unique' 'kisa_representatives' 'normal_candidates') then do;
        put 'ERROR: unknown cohort=' cohort; abort cancel;
      end;
      if seed not in (42 101 202 303 404) then do;
        put 'ERROR: unknown seed=' seed; abort cancel;
      end;
      if condition not in ('original128' 'ocr_delete128' 'cap300' 'ocr_delete300'
                           'ocr_unk128' 'ocr_unk300' 'head_tail128') then do;
        put 'ERROR: unknown condition=' condition; abort cancel;
      end;
    end;
    if eof and ncell ne 105 then do;
      put 'ERROR: expected 105 cells, found ' ncell; abort cancel;
    end;
  run;

  /* 3. Nonnegative integer counts, positive n, finite threshold in [0,1],
        one threshold per seed across all cohorts and conditions. */
  data _null_;
    set kisa_grid end=eof;
    by cohort seed condition;
    array counts n tp tn fp fn baseline_tp baseline_tn baseline_fp baseline_fn
                 corrected_fp corrected_fn new_fp new_fn;
    do over counts;
      if missing(counts) or counts < 0 or round(counts) ne counts then do;
        put 'ERROR: missing or non-integer count'; abort cancel;
      end;
    end;
    if n <= 0 then do;
      put 'ERROR: stratum n must be positive'; abort cancel;
    end;
    if missing(threshold) or threshold < 0 or threshold > 1 then do;
      put 'ERROR: threshold must be finite in [0,1]'; abort cancel;
    end;
    retain t42 t101 t202 t303 t404;
    if seed = 42 then do; if missing(t42) then t42 = threshold;
      else if threshold ne t42 then do; put 'ERROR: threshold not stable per seed'; abort cancel; end; end;
    if seed = 101 then do; if missing(t101) then t101 = threshold;
      else if threshold ne t101 then do; put 'ERROR: threshold not stable per seed'; abort cancel; end; end;
    if seed = 202 then do; if missing(t202) then t202 = threshold;
      else if threshold ne t202 then do; put 'ERROR: threshold not stable per seed'; abort cancel; end; end;
    if seed = 303 then do; if missing(t303) then t303 = threshold;
      else if threshold ne t303 then do; put 'ERROR: threshold not stable per seed'; abort cancel; end; end;
    if seed = 404 then do; if missing(t404) then t404 = threshold;
      else if threshold ne t404 then do; put 'ERROR: threshold not stable per seed'; abort cancel; end; end;
    if eof then put 'NOTE: kisa grid and threshold checks passed.';
  run;

  /* 3b. Exact cohort sizes and baseline class pools (fixed by design:
         kisa_unique n=22, kisa_representatives n=18, normal_candidates
         n=250). KISA baselines carry positives only; normal baselines
         carry normals only. */
  data _null_;
    set kisa_grid end=eof;
    if cohort = 'kisa_unique' and n ne 22 then do;
      put 'ERROR: kisa_unique n must be 22'; abort cancel;
    end;
    if cohort = 'kisa_representatives' and n ne 18 then do;
      put 'ERROR: kisa_representatives n must be 18'; abort cancel;
    end;
    if cohort = 'normal_candidates' and n ne 250 then do;
      put 'ERROR: normal_candidates n must be 250'; abort cancel;
    end;
    if cohort in ('kisa_unique' 'kisa_representatives') then do;
      if baseline_tn ne 0 or baseline_fp ne 0 then do;
        put 'ERROR: KISA baseline has normal cells'; abort cancel;
      end;
      if baseline_tp + baseline_fn ne n then do;
        put 'ERROR: KISA baseline positives do not equal n'; abort cancel;
      end;
    end;
    if cohort = 'normal_candidates' then do;
      if baseline_tp ne 0 or baseline_fn ne 0 then do;
        put 'ERROR: normal baseline has positive cells'; abort cancel;
      end;
      if baseline_tn + baseline_fp ne n then do;
        put 'ERROR: normal baseline normals do not equal n'; abort cancel;
      end;
    end;
    if eof then put 'NOTE: kisa cohort sizes and baseline pools passed.';
  run;

  /* 4. Confusion, denominators, paired transitions, rate null semantics. */
  data _null_;
    set kisa_grid end=eof;
    if tp + tn + fp + fn ne n then do;
      put 'ERROR: confusion totals do not equal n'; abort cancel;
    end;
    if baseline_tp + baseline_tn + baseline_fp + baseline_fn ne n then do;
      put 'ERROR: baseline confusion totals do not equal n'; abort cancel;
    end;
    /* Transition closure (no abstention layer in this contract). */
    if baseline_fp ne corrected_fp + (fp - new_fp) then do;
      put 'ERROR: baseline_fp transition mismatch'; abort cancel;
    end;
    if baseline_fn ne corrected_fn + (fn - new_fn) then do;
      put 'ERROR: baseline_fn transition mismatch'; abort cancel;
    end;
    /* Transition bounds: corrections cannot exceed their baseline pool,
       new errors cannot exceed the current pool. New errors are also
       bounded by the opposite baseline pool (a new FP consumes a
       baseline TN; a new FN consumes a baseline TP). */
    if corrected_fp > baseline_fp or new_fp > fp then do;
      put 'ERROR: FP transition out of bounds'; abort cancel;
    end;
    if corrected_fn > baseline_fn or new_fn > fn then do;
      put 'ERROR: FN transition out of bounds'; abort cancel;
    end;
    if new_fp > baseline_tn or new_fn > baseline_tp then do;
      put 'ERROR: new errors exceed opposite baseline pool'; abort cancel;
    end;
    if tp + fn = 0 then do;
      if not missing(recall) then do; put 'ERROR: recall must be null'; abort cancel; end;
    end;
    else if missing(recall) or recall < 0 or recall > 1
            or abs(recall - tp/(tp+fn)) > 1e-9 then do;
      put 'ERROR: recall arithmetic mismatch'; abort cancel;
    end;
    if tn + fp = 0 then do;
      if not missing(fpr) then do; put 'ERROR: FPR must be null'; abort cancel; end;
    end;
    else if missing(fpr) or fpr < 0 or fpr > 1
            or abs(fpr - fp/(tn+fp)) > 1e-9 then do;
      put 'ERROR: FPR arithmetic mismatch'; abort cancel;
    end;
    /* Cohort class roles: KISA cohorts carry no normals, normal cohort no positives. */
    if cohort in ('kisa_unique' 'kisa_representatives') then do;
      if tn + fp ne 0 then do; put 'ERROR: KISA cohort has normal rows'; abort cancel; end;
    end;
    if cohort = 'normal_candidates' then do;
      if tp + fn ne 0 then do; put 'ERROR: normal cohort has positive rows'; abort cancel; end;
    end;
    if eof then put 'NOTE: kisa arithmetic and cohort-role checks passed.';
  run;

  /* 5. Baseline consistency: baseline_* equals original128 current confusion. */
  proc sql noprint;
    create table kisa_base128 as
    select cohort, seed,
           tp as b128_tp, tn as b128_tn, fp as b128_fp, fn as b128_fn
    from kisa_grid where condition = 'original128';
  quit;
  proc sort data=kisa_base128;
    by cohort seed;
  run;
  data _null_;
    if 0 then set kisa_base128 nobs=nbase;
    if nbase ne 15 then do;
      put 'ERROR: original128 reference must have 15 cohort-seed rows';
      abort cancel;
    end;
    stop;
  run;
  data _null_;
    merge kisa_grid(in=a) kisa_base128;
    by cohort seed;
    if a and missing(b128_tp) then do;
      put 'ERROR: original128 baseline reference missing'; abort cancel;
    end;
    if baseline_tp ne b128_tp or baseline_tn ne b128_tn
       or baseline_fp ne b128_fp or baseline_fn ne b128_fn then do;
      put 'ERROR: baseline columns differ from original128'; abort cancel;
    end;
    /* original128 is the reference itself: no transitions by definition. */
    if condition = 'original128' then do;
      if corrected_fp ne 0 or corrected_fn ne 0
         or new_fp ne 0 or new_fn ne 0 then do;
        put 'ERROR: original128 must have zero transitions'; abort cancel;
      end;
    end;
  run;

  /* 6. Verified readback for return (uses the caller's outdir). */
  proc export data=kisa_grid outfile="%superq(outdir)/kisa_verified_readback.csv"
    dbms=csv replace;
  run;

  /* 7. Readable tables and graphs, never pooling seeds or cohorts. */
  proc print data=kisa_grid noobs label;
    by cohort seed;
    var condition n tp tn fp fn baseline_fp baseline_fn
        corrected_fp corrected_fn new_fp new_fn threshold recall fpr;
    label condition='조건' n='건수' tp='TP' tn='TN' fp='FP' fn='FN'
          baseline_fp='기준 FP' baseline_fn='기준 FN'
          corrected_fp='해소 FP' corrected_fn='해소 FN'
          new_fp='신규 FP' new_fn='신규 FN'
          threshold='임계값' recall='재현율' fpr='FPR';
    title 'KISA OCR 진단 — 코호트·시드별 집계 (사후 진단, 합산 없음)';
  run;
  /* Recall is null for the all-normal cohort; graph positives only to
     avoid all-missing warnings. */
  proc sgplot data=kisa_grid(where=(cohort in ('kisa_unique' 'kisa_representatives')));
    by cohort;
    vbar condition / response=recall group=seed groupdisplay=cluster;
    yaxis min=0 max=1 label='재현율(시드별 분리)';
    title '조건별 재현율 (양성 코호트, 시드 분리)';
  run;
  proc sgplot data=kisa_grid;
    by cohort;
    vbar condition / response=n group=seed groupdisplay=cluster;
    yaxis label='건수(시드별 분리)';
    title '조건별 건수 (코호트 내, 시드 분리)';
  run;
  proc sgplot data=kisa_grid(where=(cohort in ('kisa_unique' 'kisa_representatives')));
    by cohort seed;
    vbar condition / response=corrected_fn;
    yaxis min=0 label='해소된 미탐 FN (후보 기준 a)';
    title 'KISA 조건별 해소 미탐 (코호트·시드 분리)';
  run;
  proc sgplot data=kisa_grid(where=(cohort in ('kisa_unique' 'kisa_representatives')));
    by cohort seed;
    vbar condition / response=new_fn;
    yaxis min=0 label='신규 미탐 FN (후보 기준 b)';
    title 'KISA 조건별 신규 미탐 (코호트·시드 분리)';
  run;
  proc sgplot data=kisa_grid(where=(cohort='normal_candidates'));
    by seed;
    vbar condition / response=fp;
    yaxis min=0 label='정상 후보 FP(개발용, 독립 FPR 아님)';
    title '정상 후보 조건별 FP (시드 분리)';
  run;
%mend kisa17;
