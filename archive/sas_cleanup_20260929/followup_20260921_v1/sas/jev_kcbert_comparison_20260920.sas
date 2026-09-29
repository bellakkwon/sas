/*---------------------------------------------------------------------------
  ScamLens — Jev x KcBERT 사후 비교 집계 교차검증 (P3 보고용 SAS 예시)

  작성일: 2026-09-20
  입력: scripts/render_jev_kcbert_comparison_20260920.py --csv 로 만든
        공개 집계 CSV 1건 (행 ID·원문·개별 점수·로컬 절대경로 없음).
        실행 전 SAS에서 %let agg_csv = <csv 경로>; 를 지정한다.
        CSV 계약 열:
          seed, cohort, n,
          b_tp, b_tn, b_fp, b_fn,
          j_tp, j_tn, j_fp, j_fn, j_abstain_pos, j_abstain_neg,
          t_corrected_fp, t_corrected_fn, t_new_fp, t_new_fn,
          t_persistent_fp, t_persistent_fn,
          t_abstain_from_error, t_abstain_from_correct, t_retained_correct,
          g_review_count, g_caught_error, g_missed_error,
          g_unnecessary_review
        cohort 값: all, error_union, correct_controls.
        시드별 (seed, cohort) 조합은 중복 없이 3종이 모두 있어야 하며,
        all 층의 모든 수치는 error_union + correct_controls 와 같아야 한다.
  처리: 행별 합계·전이·검토큐·라벨보존 산술을 재검증하고, 불일치 시
        ERROR 후 중단한다. 통과 시         시드·층별 ODS 요약표를 만든다.
        기대 시드 42, 101, 202, 303, 404이 모두 있어야 하며, 미지·누락·소수
        시드를 거부하고 정확히 15개 seed-cohort 행을 요구한다.
  경계: 집계 CSV만 읽는다. CAS·원문·비공개 데이터에 접속하지 않는다.
        가상 대체는 실제 수정이 아니며, 검토 큐는 후보 집계일 뿐이다.
        보류는 판정 분모에 포함하지 않는다. 시드를 합산하지 않는다.
        정적 검토만 완료했으며 SAS 실제 실행은 미검증이다.
---------------------------------------------------------------------------*/

/* 1. 작업 경로 (절대경로 하드코딩 금지) */
%macro init_env;
  %global root_dir data_dir out_dir agg_csv;
  %if %length(%superq(root_dir)) = 0 %then %do;
    %let root_dir = .;
  %end;
  %let data_dir = &root_dir./data;
  %let out_dir  = &root_dir./outputs;
%mend init_env;
%init_env;

ods _all_ close;
options nodate nonumber linesize=120 pagesize=60;

/* 수치형 집계 열 목록 (가드 배열이 파생 변수를 포함하지 않도록 명시) */
%let numcols = n b_tp b_tn b_fp b_fn
               j_tp j_tn j_fp j_fn j_abstain_pos j_abstain_neg
               t_corrected_fp t_corrected_fn t_new_fp t_new_fn
               t_persistent_fp t_persistent_fn
               t_abstain_from_error t_abstain_from_correct t_retained_correct
               g_review_count g_caught_error g_missed_error g_unnecessary_review;

/* 출력 디렉터리 확인 및 안전 생성 가드 */
data _null_;
  length created $2048;
  if not fileexist(symget('out_dir')) then
    created = dcreate('outputs', symget('root_dir'));
  if not fileexist(symget('out_dir')) then do;
    put 'ERROR: Output directory cannot be created. Check root_dir and permissions.';
    abort cancel;
  end;
run;

/* 2. 입력 CSV 지정·존재·비어 있음 검사 */
data _null_;
  if "%superq(agg_csv)" = "" then do;
    put 'ERROR: agg_csv macro variable is not set. Submit %let agg_csv = <csv path>; first.';
    abort cancel;
  end;
  if not fileexist(symget('agg_csv')) then do;
    put 'ERROR: Aggregate CSV not found.';
    abort cancel;
  end;
run;

/* 3. 집계 CSV 읽기 (집계 전용, 원문 없음) */
data agg;
  infile "%superq(agg_csv)" lrecl=32767 encoding="utf-8" dsd dlm=',' firstobs=2 truncover;
  length cohort $16;
  input seed cohort $ n
        b_tp b_tn b_fp b_fn
        j_tp j_tn j_fp j_fn j_abstain_pos j_abstain_neg
        t_corrected_fp t_corrected_fn t_new_fp t_new_fn
        t_persistent_fp t_persistent_fn
        t_abstain_from_error t_abstain_from_correct t_retained_correct
        g_review_count g_caught_error g_missed_error g_unnecessary_review;
run;

data _null_;
  if 0 then set agg nobs=nobs;
  if nobs = 0 then do;
    put 'ERROR: Empty aggregate CSV (no data rows).';
    abort cancel;
  end;
  stop;
run;

/* 4. BY 출력용 정렬과 seed-cohort 중복 제거 (중복은 별도 저장 후 거부) */
proc sort data=agg out=agg_sorted nodupkey dupout=dups;
  by seed cohort;
run;

data _null_;
  if 0 then set dups nobs=ndup;
  if ndup > 0 then do;
    put 'ERROR: Duplicate seed-cohort combinations.';
    abort cancel;
  end;
  stop;
run;

/* 5. 행별 집계 산술 가드 (명시 열만 검사, 파생 변수 제외) */
data _null_;
  set agg_sorted;
  array nums &numcols;
  do over nums;
    if missing(nums) or nums < 0 or round(nums) ne nums then do;
      put 'ERROR: Non-integer or negative count at seed=' seed ' cohort=' cohort;
      abort cancel;
    end;
  end;
  if cohort not in ('all', 'error_union', 'correct_controls') then do;
    put 'ERROR: Unknown cohort=' cohort;
    abort cancel;
  end;
  base_err = b_fp + b_fn;
  base_ok  = b_tp + b_tn;
  jev_ok   = j_tp + j_tn;
  jev_bad  = j_fp + j_fn;
  jev_abs  = j_abstain_pos + j_abstain_neg;
  if base_err + base_ok ne n then do;
    put 'ERROR: Baseline confusion != n at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if jev_ok + jev_bad + jev_abs ne n then do;
    put 'ERROR: Jev confusion+abstain != n at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if t_corrected_fp + t_corrected_fn + t_persistent_fp + t_persistent_fn
     + t_abstain_from_error ne base_err then do;
    put 'ERROR: Transitions do not explain baseline errors at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if t_retained_correct + t_new_fp + t_new_fn + t_abstain_from_correct ne base_ok then do;
    put 'ERROR: Transitions do not explain baseline correct at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if t_retained_correct + t_corrected_fp + t_corrected_fn ne jev_ok then do;
    put 'ERROR: Transitions do not rebuild Jev correct at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if t_persistent_fp + t_persistent_fn + t_new_fp + t_new_fn ne jev_bad then do;
    put 'ERROR: Transitions do not rebuild Jev errors at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if t_abstain_from_error + t_abstain_from_correct ne jev_abs then do;
    put 'ERROR: Transitions do not rebuild abstentions at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if b_tp + b_fn ne j_tp + j_fn + j_abstain_pos then do;
    put 'ERROR: Actual positives not conserved at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if b_tn + b_fp ne j_tn + j_fp + j_abstain_neg then do;
    put 'ERROR: Actual negatives not conserved at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if j_fp ne t_persistent_fp + t_new_fp then do;
    put 'ERROR: Jev fp not explained per-class at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if j_fn ne t_persistent_fn + t_new_fn then do;
    put 'ERROR: Jev fn not explained per-class at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if g_caught_error ne t_corrected_fp + t_corrected_fn + t_abstain_from_error then do;
    put 'ERROR: Triage caught_error rule violated at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if g_missed_error ne t_persistent_fp + t_persistent_fn then do;
    put 'ERROR: Triage missed_error rule violated at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if g_unnecessary_review ne t_new_fp + t_new_fn + t_abstain_from_correct then do;
    put 'ERROR: Triage unnecessary_review rule violated at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if g_caught_error + g_missed_error ne base_err then do;
    put 'ERROR: Triage does not cover baseline errors at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
  if g_caught_error + g_unnecessary_review ne g_review_count then do;
    put 'ERROR: Triage review queue does not add up at seed=' seed ' cohort=' cohort;
    abort cancel;
  end;
run;

/* 6. 층 정합 가드: 시드별 3종 완비와 all = error_union + correct_controls (전 수치) */
data _null_;
  set agg_sorted;
  by seed;
  array v &numcols;
  array sa(24) _temporary_;
  array se(24) _temporary_;
  array sc(24) _temporary_;
  retain ha he hc;
  if first.seed then do;
    ha = 0; he = 0; hc = 0;
  end;
  if cohort = 'all' then do;
    ha + 1;
    do i = 1 to dim(v);
      sa(i) = v(i);
    end;
  end;
  else if cohort = 'error_union' then do;
    he + 1;
    do i = 1 to dim(v);
      se(i) = v(i);
    end;
  end;
  else if cohort = 'correct_controls' then do;
    hc + 1;
    do i = 1 to dim(v);
      sc(i) = v(i);
    end;
  end;
  if last.seed then do;
    if ha ne 1 or he ne 1 or hc ne 1 then do;
      put 'ERROR: Missing seed-cohort combination for seed=' seed;
      abort cancel;
    end;
    do i = 1 to dim(v);
      if sa(i) ne se(i) + sc(i) then do;
        put 'ERROR: all != error_union+correct_controls for seed=' seed;
        abort cancel;
      end;
    end;
  end;
run;

data _null_;
  put 'NOTE: Aggregate guard checks passed.';
run;

/* 6b. 시드 허용목록과 행 센서스: 5시드 x 3층 = 정확히 15행 */
data _null_;
  set agg_sorted nobs=ntotal;
  by seed;
  if _n_ = 1 and ntotal ne 15 then do;
    put 'ERROR: Expected 15 seed-cohort rows, found ' ntotal;
    abort cancel;
  end;
  if seed ne round(seed, 1) or seed not in (42, 101, 202, 303, 404) then do;
    put 'ERROR: Unknown, missing, or fractional seed=' seed;
    abort cancel;
  end;
run;

/* 7. 시드·층별 요약표 (판정 분모 = n - 보류, 시드 합산 없음) */
data summary;
  set agg_sorted;
  decided = n - (j_abstain_pos + j_abstain_neg);
  if decided > 0 then jev_decided_acc = (j_tp + j_tn) / decided;
  else jev_decided_acc = .;
  /* Explicit n=0 handling: no division by zero; an empty stratum yields
     a null baseline error rate (all counts are already guarded to 0). */
  if n > 0 then base_err_rate = (b_fp + b_fn) / n;
  else base_err_rate = .;
  hypo_corrected = t_corrected_fp + t_corrected_fn;
  hypo_new = t_new_fp + t_new_fn;
  persistent = t_persistent_fp + t_persistent_fn;
  abstain = j_abstain_pos + j_abstain_neg;
  label decided = '판정 분모(보류 제외)'
        jev_decided_acc = 'Jev 판정 정답률(판정 분모)'
        base_err_rate = '기준 오류율'
        hypo_corrected = '가상 해소(가정)'
        hypo_new = '가상 신규 오류(가정)';
run;

ods html file="&out_dir./jev_kcbert_comparison_summary.html" style=HTMLBlue;
proc print data=summary noobs label;
  by seed;
  var cohort n base_err_rate decided jev_decided_acc
      hypo_corrected hypo_new persistent abstain
      g_review_count g_caught_error g_missed_error g_unnecessary_review;
  title 'Jev x KcBERT 사후 비교 — 시드·층별 집계 (사후 진단, 전체 정확도 아님)';
run;
ods html close;
