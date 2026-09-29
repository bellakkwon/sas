/*---------------------------------------------------------------------------
  ScamLens 16 — KcBERT U5 오류 진단 및 신뢰성 분석 패키지 (SAS 9.4 / Viya 호환)

  프로젝트: ScamLens (안심문자 탐지 및 난독화 강건성 연구)
  작성일: 2026-09-20
  목적: KcBERT U5 과거 평가 이력이 있는 원래 test(N=2,317) 15개 모델(BASE, DUP, FLIP x 5 Seeds)의
        오탐(FP)/미탐(FN) 상세 집계, 토크나이저 128 토큰 절단 영향, 마커별 오차율,
        영속 오차 합의도 및 쌍별 전이(Paired Transitions)를 SAS Studio 및 Viya 환경에서
        정밀 그래픽스와 함께 분석한다.

  ★ 안전 및 이식성(Portability) 원칙 ★
  1. 특정 운영체제(macOS 등)의 하드코딩된 절대 경로를 일체 사용하지 않는다.
  2. 원문 텍스트 및 개인식별정보(PII)가 배제된 사전 검증 집계 CSV만을 입력으로 사용한다.
  3. DATA step + INFILE LRECL=32767 ENCODING="utf-8" DSD DLM=',' FIRSTOBS=2 와 명시적 LENGTH/INPUT을 채택한다.
  4. 데이터셋 유효성(15개 arm-seed 키 조합, 관측치 수, 정수 제약, 재계산 오차율 검증) 가드 검증을 내장한다.
  5. 모표준편차(Population SD) 산출 시 PROC MEANS VARDEF=N 절차를 준수한다.
     - 참조: https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a000146729.htm
     - PROC SGPLOT 가이드: https://documentation.sas.com/api/docsets/grstatproc/9.4/content/grstatproc.pdf
---------------------------------------------------------------------------*/

/* 1. 작업 경로 매크로 변수 설정 (빈 변수 또는 미정의 시 안전하게 '.' 설정) */
%macro init_env;
  %global root_dir data_dir out_dir;
  %if %length(%superq(root_dir)) = 0 %then %do;
    %let root_dir = .;
  %end;
  %let data_dir = &root_dir./data;
  %let out_dir  = &root_dir./outputs;
%mend init_env;
%init_env;

/* ODS 옵션 초기화 (goptions 배제) */
ods _all_ close;
options nodate nonumber linesize=120 pagesize=60;

/* 출력 디렉터리 확인 및 안전 생성 가드 */
data _null_;
  length created $2048;
  if not fileexist(symget('out_dir')) then
    created=dcreate('outputs',symget('root_dir'));
  if not fileexist(symget('out_dir')) then do;
    put 'ERROR: Output directory cannot be created. Check root_dir and permissions.';
    abort cancel;
  end;
run;

/* 2. 필수 입력 CSV 파일 존재 여부 검사 (경로 따옴표 보호) */
%macro verify_input_files;
  %local missing;
  %let missing =;
  %if not %sysfunc(fileexist(%superq(data_dir)/eval_metadata_summary.csv)) %then
    %let missing = &missing. eval_metadata_summary.csv;
  %if not %sysfunc(fileexist(%superq(data_dir)/model_seed_diagnostics.csv)) %then
    %let missing = &missing. model_seed_diagnostics.csv;
  %if not %sysfunc(fileexist(%superq(data_dir)/error_breakdown_by_feature.csv)) %then
    %let missing = &missing. error_breakdown_by_feature.csv;
  %if not %sysfunc(fileexist(%superq(data_dir)/truncation_audit_summary.csv)) %then
    %let missing = &missing. truncation_audit_summary.csv;
  %if not %sysfunc(fileexist(%superq(data_dir)/persistent_error_summary.csv)) %then
    %let missing = &missing. persistent_error_summary.csv;
  %if not %sysfunc(fileexist(%superq(data_dir)/paired_transition_summary.csv)) %then
    %let missing = &missing. paired_transition_summary.csv;

  %if %length(&missing.) > 0 %then %do;
    %put ERROR: [ScamLens 16] 다음 필수 CSV 데이터 파일이 존재하지 않습니다: &missing.;
    %put ERROR- data/ 디렉터리에 정제 CSV가 배치되어 있는지 확인하십시오.;
    %abort cancel;
  %end;
  %else %do;
    %put NOTE: [ScamLens 16] 6종 필수 입력 CSV 파일의 존재를 확인하였습니다.;
  %end;
%mend verify_input_files;
%verify_input_files;

/* 3. CSV 데이터 로드 (LRECL=32767 ENCODING="utf-8" DSD DLM=',' FIRSTOBS=2 및 _ERROR_ 검사) */

/* 3.1. 시험셋 메타데이터 요약 */
data work.eval_metadata;
  infile "&data_dir./eval_metadata_summary.csv" lrecl=32767 encoding="utf-8" dsd dlm=',' firstobs=2 truncover;
  length metric $32 value 8 description $1024;
  input metric $ value description $;
  if _error_ then do;
    put "ERROR: [ScamLens 16] eval_metadata_summary.csv 파싱 오류 발생 행: " _n_;
    abort cancel;
  end;
run;

/* 3.2. 15개 모델 시드별 진단 지표 */
data work.model_diagnostics;
  infile "&data_dir./model_seed_diagnostics.csv" lrecl=32767 encoding="utf-8" dsd dlm=',' firstobs=2 truncover;
  length arm $8 seed 8 threshold 8 tp 8 tn 8 fp 8 fn 8
         accuracy 8 precision 8 recall 8 fpr 8 f1 8 brier 8 mean_margin 8 std_margin 8;
  input arm $ seed threshold tp tn fp fn accuracy precision recall fpr f1 brier mean_margin std_margin;
  if _error_ then do;
    put "ERROR: [ScamLens 16] model_seed_diagnostics.csv 파싱 오류 발생 행: " _n_;
    abort cancel;
  end;
  /* 재계산 무결성 지표 */
  recalc_total = tp + tn + fp + fn;
  recalc_normal = tn + fp;
  recalc_smishing = tp + fn;
  if recalc_smishing > 0 then calc_fnr = fn / recalc_smishing * 100;
  else calc_fnr = .;
  if recalc_normal > 0 then calc_fpr = fp / recalc_normal * 100;
  else calc_fpr = .;
run;

/* 3.3. 특성/마커별 오차 분해 */
data work.feature_breakdown;
  infile "&data_dir./error_breakdown_by_feature.csv" lrecl=32767 encoding="utf-8" dsd dlm=',' firstobs=2 truncover;
  length feature_category $32 feature_value $32 n_total 8 n_normal 8 n_smishing 8
         dup_avg_fp 8 dup_avg_fn 8 dup_fpr 8 dup_fnr 8
         base_avg_fp 8 base_avg_fn 8 flip_avg_fp 8 flip_avg_fn 8;
  input feature_category $ feature_value $ n_total n_normal n_smishing
        dup_avg_fp dup_avg_fn dup_fpr dup_fnr base_avg_fp base_avg_fn flip_avg_fp flip_avg_fn;
  if _error_ then do;
    put "ERROR: [ScamLens 16] error_breakdown_by_feature.csv 파싱 오류 발생 행: " _n_;
    abort cancel;
  end;
  if dup_fnr ne . then dup_fnr_pct = dup_fnr * 100; else dup_fnr_pct = .;
  if dup_fpr ne . then dup_fpr_pct = dup_fpr * 100; else dup_fpr_pct = .;
run;

/* 3.4. 토크나이저 절단 영향 감사 */
data work.truncation_audit;
  infile "&data_dir./truncation_audit_summary.csv" lrecl=32767 encoding="utf-8" dsd dlm=',' firstobs=2 truncover;
  length arm $8 is_truncated 8 n_total 8 n_normal 8 n_smishing 8
         mean_tp 8 mean_tn 8 mean_fp 8 mean_fn 8 recall 8 fnr 8 fpr 8 f1 8;
  input arm $ is_truncated n_total n_normal n_smishing mean_tp mean_tn mean_fp mean_fn recall fnr fpr f1;
  if _error_ then do;
    put "ERROR: [ScamLens 16] truncation_audit_summary.csv 파싱 오류 발생 행: " _n_;
    abort cancel;
  end;
  length trunc_label $80;
  if is_truncated = 1 then trunc_label = '절단 (>128 토큰)';
  else trunc_label = '가시 (<=128 토큰)';
  if fnr ne . then fnr_pct = fnr * 100; else fnr_pct = .;
  if fpr ne . then fpr_pct = fpr * 100; else fpr_pct = .;
run;

/* 3.5. 영속 오류 합의도 요약 */
data work.persistent_errors;
  infile "&data_dir./persistent_error_summary.csv" lrecl=32767 encoding="utf-8" dsd dlm=',' firstobs=2 truncover;
  length arm $8 error_type $4 vote_count 8 count_messages 8 total_error_events 8
         pct_of_unique_errors 8 pct_of_class 8;
  input arm $ error_type $ vote_count count_messages total_error_events pct_of_unique_errors pct_of_class;
  if _error_ then do;
    put "ERROR: [ScamLens 16] persistent_error_summary.csv 파싱 오류 발생 행: " _n_;
    abort cancel;
  end;
run;

/* 3.6. DUP -> FLIP 쌍별 전이 요약 */
data work.paired_transitions;
  infile "&data_dir./paired_transition_summary.csv" lrecl=32767 encoding="utf-8" dsd dlm=',' firstobs=2 truncover;
  length seed 8 error_type $4 denominator 8 dup_count 8 flip_count 8 net_change 8
         resolved 8 new 8 persistent 8 neither 8;
  input seed error_type $ denominator dup_count flip_count net_change resolved new persistent neither;
  if _error_ then do;
    put "ERROR: [ScamLens 16] paired_transition_summary.csv 파싱 오류 발생 행: " _n_;
    abort cancel;
  end;
run;

/* 4. 데이터 유효성 및 정합성 가드 검증 매크로 */
%macro guard_validation;
  %local n_diag n_trunc n_trans bad_keys bad_integers bad_totals bad_tolerances;

  /* 4.1. 관측치 수 검증 */
  proc sql noprint;
    select count(*) into :n_diag from work.model_diagnostics;
    select count(*) into :n_trunc from work.truncation_audit;
    select count(*) into :n_trans from work.paired_transitions;

    /* 15개 키 조합 및 음수 정수 검사 */
    select count(*) into :bad_keys from work.model_diagnostics
      where arm not in ('BASE', 'DUP', 'FLIP') or seed not in (42, 101, 202, 303, 404);

    select count(*) into :bad_integers from work.model_diagnostics
      where tp < 0 or tn < 0 or fp < 0 or fn < 0 or
            tp ne int(tp) or tn ne int(tn) or fp ne int(fp) or fn ne int(fn);

    /* 총 레코드 수 및 분할 정합성 검사 */
    select count(*) into :bad_totals from work.model_diagnostics
      where recalc_total ne 2317 or recalc_normal ne 1665 or recalc_smishing ne 652;

    /* 재계산 지표 허용오차(1e-4) 검사 */
    select count(*) into :bad_tolerances from work.model_diagnostics
      where abs(recall - (tp/recalc_smishing)) > 0.0001 or
            abs(fpr - (fp/recalc_normal)) > 0.0001;
  quit;

  %if &n_diag. ne 15 %then %do;
    %put ERROR: [ScamLens 16] model_diagnostics 관측치 수 불일치: &n_diag. (기대: 15);
    %abort cancel;
  %end;

  %if &n_trunc. ne 6 %then %do;
    %put ERROR: [ScamLens 16] truncation_audit 관측치 수 불일치: &n_trunc. (기대: 6);
    %abort cancel;
  %end;

  %if &n_trans. ne 10 %then %do;
    %put ERROR: [ScamLens 16] paired_transitions 관측치 수 불일치: &n_trans. (기대: 10);
    %abort cancel;
  %end;

  %if &bad_keys. > 0 or &bad_integers. > 0 or &bad_totals. > 0 or &bad_tolerances. > 0 %then %do;
    %put ERROR: [ScamLens 16] 데이터 정합성 검증 실패 (bad_keys=&bad_keys, bad_int=&bad_integers, bad_totals=&bad_totals, bad_tol=&bad_tolerances);
    %abort cancel;
  %end;

  %put NOTE: [ScamLens 16] 데이터 정합성 가드 검증 통과 (15개 모델 전수 합치 및 오차 허용범위 만족).;
%mend guard_validation;
%guard_validation;

/* Main review: explicit key, missing-value and cross-table checks. */
%macro assert_unique(ds,keys,expected);
  %local unique_n dup_n;
  proc sort data=&ds out=work._unique nodupkey dupout=work._duplicates;
    by &keys;
  run;
  proc sql noprint;
    select count(*) into :unique_n trimmed from work._unique;
    select count(*) into :dup_n trimmed from work._duplicates;
  quit;
  %if &unique_n ne &expected or &dup_n ne 0 %then %do;
    %put ERROR: Duplicate or missing keys in &ds.;
    %abort cancel;
  %end;
%mend;
%assert_unique(work.model_diagnostics,arm seed,15);
%assert_unique(work.truncation_audit,arm is_truncated,6);
%assert_unique(work.paired_transitions,seed error_type,10);
%assert_unique(work.persistent_errors,arm error_type vote_count,30);
%assert_unique(work.feature_breakdown,feature_category feature_value,17);

data _null_;
  set work.model_diagnostics;
  /* Fixed-denominator metrics are always defined; precision/F1 allow
     null when their denominators are zero (checked explicitly below). */
  array rates[*] threshold accuracy recall fpr brier;
  do i=1 to dim(rates);
    if missing(rates[i]) or rates[i]<0 or rates[i]>1 then do;
      put 'ERROR: Missing/out-of-range model metric'; abort cancel;
    end;
  end;
  /* Accuracy/recall/FPR denominators are fixed positives (2317/652/1665). */
  if abs(accuracy-(tp+tn)/2317)>0.000001 or
     abs(recall-tp/652)>0.000001 or abs(fpr-fp/1665)>0.000001 then do;
    put 'ERROR: Recomputed model rate mismatch'; abort cancel;
  end;
  /* Precision null semantics: undefined when tp+fp=0, else tp/(tp+fp). */
  if (tp+fp)=0 then do;
    if not missing(precision) then do;
      put 'ERROR: Precision must be null when tp+fp=0'; abort cancel;
    end;
  end;
  else if missing(precision) or precision<0 or precision>1
          or abs(precision-tp/(tp+fp))>0.000001 then do;
    put 'ERROR: Recomputed precision mismatch'; abort cancel;
  end;
  /* F1 null semantics: undefined when 2*tp+fp+fn=0, else harmonic mean. */
  if (2*tp+fp+fn)=0 then do;
    if not missing(f1) then do;
      put 'ERROR: F1 must be null when 2*tp+fp+fn=0'; abort cancel;
    end;
  end;
  else if missing(f1) or f1<0 or f1>1
          or abs(f1-2*tp/(2*tp+fp+fn))>0.000001 then do;
    put 'ERROR: Recomputed F1 mismatch'; abort cancel;
  end;
run;

data _null_;
  set work.truncation_audit;
  array nums[*] n_total n_normal n_smishing mean_tp mean_tn mean_fp mean_fn;
  do i=1 to dim(nums);
    if missing(nums[i]) or nums[i]<0 then do; put 'ERROR: Invalid truncation count'; abort cancel; end;
  end;
  if arm not in ('BASE','DUP','FLIP') or is_truncated not in (0,1) or
     n_total ne n_normal+n_smishing or abs(mean_tp+mean_fn-n_smishing)>0.000001 or
     abs(mean_tn+mean_fp-n_normal)>0.000001 or n_normal ne int(n_normal) or n_smishing ne int(n_smishing) then do;
    put 'ERROR: Truncation denominator/count mismatch'; abort cancel;
  end;
  if missing(recall) or missing(fnr) or missing(fpr) or missing(f1) or
     abs(recall-mean_tp/n_smishing)>0.000001 or
     abs(fnr-mean_fn/n_smishing)>0.000001 or abs(fpr-mean_fp/n_normal)>0.000001 or
     abs(f1-2*mean_tp/(2*mean_tp+mean_fp+mean_fn))>0.000001 then do;
    put 'ERROR: Truncation rate mismatch'; abort cancel;
  end;
run;

data _null_;
  set work.feature_breakdown;
  array nums[*] n_total n_normal n_smishing dup_avg_fp dup_avg_fn base_avg_fp base_avg_fn flip_avg_fp flip_avg_fn;
  do i=1 to dim(nums);
    if missing(nums[i]) or nums[i]<0 then do; put 'ERROR: Invalid feature count'; abort cancel; end;
  end;
  if n_total ne n_normal+n_smishing or n_normal ne int(n_normal) or n_smishing ne int(n_smishing) or
     max(dup_avg_fp,base_avg_fp,flip_avg_fp)>n_normal or max(dup_avg_fn,base_avg_fn,flip_avg_fn)>n_smishing then do;
    put 'ERROR: Feature denominator mismatch'; abort cancel;
  end;
  if n_normal=0 then do;
    if not missing(dup_fpr) then do; put 'ERROR: Empty denominator must be missing'; abort cancel; end;
  end;
  else if missing(dup_fpr) or abs(dup_fpr-dup_avg_fp/n_normal)>0.000001 then do;
    put 'ERROR: Feature FPR mismatch'; abort cancel;
  end;
  if n_smishing=0 then do;
    if not missing(dup_fnr) then do; put 'ERROR: Empty denominator must be missing'; abort cancel; end;
  end;
  else if missing(dup_fnr) or abs(dup_fnr-dup_avg_fn/n_smishing)>0.000001 then do;
    put 'ERROR: Feature FNR mismatch'; abort cancel;
  end;
run;

data _null_;
  set work.paired_transitions;
  array counts[*] denominator dup_count flip_count resolved new persistent neither;
  do i=1 to dim(counts);
    if missing(counts[i]) or counts[i]<0 or counts[i] ne int(counts[i]) then do;
      put 'ERROR: Invalid transition count'; abort cancel;
    end;
  end;
  if seed not in (42,101,202,303,404) or error_type not in ('FP','FN') or
     (error_type='FP' and denominator ne 1665) or (error_type='FN' and denominator ne 652) or
     sum(resolved,new,persistent,neither) ne denominator or
     resolved+persistent ne dup_count or new+persistent ne flip_count or
     missing(net_change) or net_change ne new-resolved then do;
    put 'ERROR: Transition reconciliation failed'; abort cancel;
  end;
run;

data _null_;
  set work.persistent_errors;
  if arm not in ('BASE','DUP','FLIP') or error_type not in ('FP','FN') or vote_count not in (1,2,3,4,5) or
     missing(count_messages) or count_messages<0 or count_messages ne int(count_messages) or
     total_error_events ne count_messages*vote_count then do;
    put 'ERROR: Invalid persistence summary'; abort cancel;
  end;
run;

/* Cross-table totals, not just row counts. */
proc sql;
  create table work._partition_bad as
  select arm from work.truncation_audit group by arm
  having sum(n_total) ne 2317 or sum(n_normal) ne 1665 or sum(n_smishing) ne 652;
  create table work._feature_bad as
  select feature_category from work.feature_breakdown group by feature_category
  having sum(n_total) ne 2317 or sum(n_normal) ne 1665 or sum(n_smishing) ne 652;
  create table work._transition_bad as
  select t.seed from work.paired_transitions t
  left join work.model_diagnostics d on t.seed=d.seed and d.arm='DUP'
  left join work.model_diagnostics f on t.seed=f.seed and f.arm='FLIP'
  where (t.error_type='FP' and (t.dup_count ne d.fp or t.flip_count ne f.fp)) or
        (t.error_type='FN' and (t.dup_count ne d.fn or t.flip_count ne f.fn));
  create table work._recurrence_sum as
  select arm,error_type,sum(total_error_events) as observed
  from work.persistent_errors group by arm,error_type;
  create table work._model_error_sum as
  select arm,sum(fp) as fp,sum(fn) as fn
  from work.model_diagnostics group by arm;
  create table work._recurrence_bad as
  select p.arm,p.error_type from work._recurrence_sum p
  left join work._model_error_sum d on p.arm=d.arm
  where (p.error_type='FP' and p.observed ne d.fp) or
        (p.error_type='FN' and p.observed ne d.fn);
quit;
data _null_;
  set work._partition_bad work._feature_bad work._transition_bad work._recurrence_bad;
  put 'ERROR: Cross-table aggregate mismatch'; abort cancel;
run;
%macro stop_on_error;
  %if &syserr > 4 or &syscc > 4 %then %do;
    %put ERROR: SAS error detected before plotting.; %abort cancel;
  %end;
%mend;
%stop_on_error;

/* 5. 모표준편차 산출 (PROC MEANS VARDEF=N) */
proc means data=work.model_diagnostics noprint nway vardef=n;
  class arm;
  var fp fn recall fpr f1;
  output out=work.arm_population_stats
    mean=mean_fp mean_fn mean_rec mean_fpr mean_f1
    std=std_fp std_fn std_rec std_fpr std_f1;
run;

/* 6. ODS 리포트 생성 및 PROC SGPLOT 시각화 5종 */
ods graphics on / reset=all width=10in height=6in imagefmt=png;
ods html path="&out_dir." (url=none) gpath="&out_dir." (url=none) file="u5_error_diagnostics_report.html" style=HTMLBlue;
footnote "Descriptive results; five seeds reuse the same messages. Not causal evidence.";

title1 bold "ScamLens KcBERT U5 오류 진단 및 모델 신뢰성 평가 (SAS 9.4 / Viya)";
title2 "과거 평가 이력이 있는 원래 test(N=2,317) 15개 모델 정밀 감사 결과 (정적 검증 완료본)";

/* 6.1. 표 출력 */
proc print data=work.eval_metadata noobs;
  title3 "표 1. U5 시험 데이터셋 기본 특성 및 토큰 절단 현황";
run;

proc print data=work.model_diagnostics noobs;
  var arm seed threshold tp tn fp fn recall fpr f1 brier;
  title3 "표 2. 15개 모델별 혼동행렬 및 재계산 성능 지표";
run;

proc print data=work.paired_transitions noobs;
  title3 "표 3. DUP -> FLIP 시드별 쌍별 전이 집계표 (Net FP +1, Net FN +11 일치)";
run;

/* 6.2. Plot 1: 조건별 FP 발생 분포 (5개 시드 산점도 + 평균선, 0 베이스라인) */
proc sgplot data=work.model_diagnostics;
  title3 "그림 1. 조건별(BASE, DUP, FLIP) FP 발생 건수 (5개 시드 개별점 및 0 베이스라인)";
  scatter x=arm y=fp / markerattrs=(symbol=CircleFilled size=10 color=CXC0392B) jitter;
  yaxis label="오탐(FP) 건수 (Messages)" min=0 grid;
  xaxis label="실험 조건 (Arm)";
run;

/* 6.3. Plot 2: 128 토큰 절단 여부에 따른 스미싱 미탐률(FNR %) 비교 (0 베이스라인) */
proc sgplot data=work.truncation_audit;
  title3 "그림 2. 128 토큰 절단 여부에 따른 스미싱 미탐률(FNR %) 대조 (0 베이스라인)";
  vbar arm / response=fnr_pct group=trunc_label groupdisplay=cluster
             datalabel barwidth=0.5;
  yaxis label="스미싱 미탐률 (FNR %)" min=0 grid;
  xaxis label="실험 조건 (Arm)";
run;

/* 6.4. Plot 3: DUP 조건 주요 마커별 미탐률(FNR %) 분석 */
proc sgplot data=work.feature_breakdown(where=(feature_category in ('has_url', 'bare_ip', 'phone_marker', 'institution_notice_marker', 'urgency_marker')));
  title3 "그림 3. DUP 조건: 구조 및 어휘 마커별 스미싱 미탐률(FNR %)";
  hbar feature_category / response=dup_fnr_pct group=feature_value groupdisplay=cluster
                          datalabel categoryorder=respdesc;
  xaxis label="스미싱 미탐률 (FNR %)" min=0 grid;
  yaxis label="특성 마커 (0=미보유, 1=보유)";
run;

/* 6.5. Plot 4: DUP 시드별 검증셋 선택 임계값 (시드별 점수 척도 차이) */
proc sgplot data=work.model_diagnostics(where=(arm='DUP'));
  title3 "그림 4. DUP 조건: 시드별 검증셋 선택 임계값(Threshold) 비교 (시드별 점수 척도 차이 θ=0.9858)";
  scatter x=seed y=threshold / markerattrs=(symbol=CircleFilled size=12 color=CXC0392B)
          datalabel=threshold;
  series x=seed y=threshold / lineattrs=(color=CX2980B9 pattern=dash);
  xaxis label="난수 시드 (Seed)" values=(42 101 202 303 404);
  yaxis label="검증셋 선택 임계값 (θ)" min=0 max=1.0 grid;
run;

/* Paired event totals across seeds; same messages recur across seeds. */
data work.transition_long;
  set work.paired_transitions;
  length transition $12;
  transition='Resolved'; events=resolved; output;
  transition='New'; events=new; output;
  transition='Persistent'; events=persistent; output;
run;
proc summary data=work.transition_long nway;
  class error_type transition;
  var events;
  output out=work.transition_totals sum=events;
run;
proc sgplot data=work.transition_totals;
  title3 "DUP to FLIP: resolved / new / persistent error events (five seeds)";
  vbarparm category=transition response=events / group=error_type groupdisplay=cluster datalabel;
  yaxis label="Prediction events, not unique messages" min=0 grid;
run;
proc export data=work.model_diagnostics outfile="&out_dir./sas_model_readback.csv" dbms=csv replace; run;
proc export data=work.arm_population_stats outfile="&out_dir./sas_arm_readback.csv" dbms=csv replace; run;
proc export data=work.transition_totals outfile="&out_dir./sas_transition_readback.csv" dbms=csv replace; run;

ods html close;
ods _all_ close;

title;

/* 7. 종료 상태 안전 확인 */
%macro finalize_status;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens 16] SAS 처리 중 오류가 발생하였습니다 (syserr=&syserr, syscc=&syscc).;
    %abort cancel;
  %end;
  %else %do;
    %put NOTE: [ScamLens 16] SCAMLENS_U5_DIAGNOSTICS_COMPLETE: SAS execution finished. Inspect exported readback tables.;
  %end;
%mend finalize_status;
%finalize_status;
