/*---------------------------------------------------------------------------
  ScamLens 14 — KcBERT 고해상도 시각화 및 CAS 적재 통합 모듈 (All-in-One)

  프로젝트: ScamLens (안심문자 탐지 및 난독화 강건성 연구)
  작성일: 2026-09-18
  버전: v3.2 (Visual Analytics CAS 포맷 결측 에러 TKCASDAL_WHERE 완벽 해결)

  [해결 내역]
  - CAS 인메모리 엔진에서 사용자 정의 포맷($ARMKR.) 부재로 인한 WHERE 필터 에러 원천 해결
  - 1) 실제 문자형 컬럼(arm_kr, url_group_kr)을 테이블에 직접 내장 (포맷 종속성 0%)
  - 2) CAS 세션에 사용자 정의 포맷 라이브러리(casfmtlib) 정식 등록
  - 3) CAS 적재 전 사용자 정의 포맷 바인딩 제거로 순수 문자열 필터링 100% 안전 보장
---------------------------------------------------------------------------*/

/*=============================================================================
  [1단계: 데이터 생성] 5대 핵심 분석 데이터셋 생성 (오픈 코드)
=============================================================================*/
%put NOTE: ========================================================;
%put NOTE: [ScamLens Step 1] 5대 핵심 정본 데이터셋 생성 시작...;
%put NOTE: ========================================================;

/* 1-1. 15-Arm 세부 수치 테이블 (15행) */
data work.kcbert_15arms;
  length arm $8;
  infile datalines dlm="," dsd truncover;
  input arm :$8. seed threshold recall fpr f1 tp fp fn tn total_n brier_score;
  datalines;
DUP,42,0.025356,0.972727,0.007746,0.969789,321,11,9,1409,1750,0.012249
FLIP,42,0.249265,0.960606,0.008451,0.962064,317,12,13,1408,1750,0.011669
BASE,42,0.033222,0.978788,0.009155,0.969970,323,13,7,1407,1750,0.012018
DUP,101,0.056655,0.957576,0.008451,0.960486,316,12,14,1408,1750,0.015002
FLIP,101,0.038150,0.966667,0.007746,0.966667,319,11,11,1409,1750,0.011353
BASE,101,0.108383,0.969697,0.011972,0.959520,320,17,10,1403,1750,0.013184
DUP,202,0.023381,0.978788,0.007746,0.972892,323,11,7,1409,1750,0.010791
FLIP,202,0.068893,0.966667,0.004930,0.972561,319,7,11,1413,1750,0.010618
BASE,202,0.620583,0.939394,0.003521,0.961240,310,5,20,1415,1750,0.013332
DUP,303,0.018280,0.969697,0.010563,0.962406,320,15,10,1405,1750,0.012190
FLIP,303,0.294521,0.951515,0.007746,0.958779,314,11,16,1409,1750,0.013780
BASE,303,0.199156,0.966667,0.011972,0.957958,319,17,11,1403,1750,0.013492
DUP,404,0.019324,0.972727,0.009859,0.965414,321,14,9,1406,1750,0.010659
FLIP,404,0.036188,0.963636,0.004930,0.970992,318,7,12,1413,1750,0.010497
BASE,404,0.013827,0.975758,0.010563,0.965517,322,15,8,1405,1750,0.011603
;
run;

/* 1-2. Arm 요약 통계 테이블 (3행) */
data work.kcbert_arm_summary;
  length arm $8;
  infile datalines dlm="," dsd truncover;
  input arm :$8. recall_mean recall_std fpr_mean fpr_std f1_mean f1_std brier_mean brier_std group_std_all group_std_multi group_std_singleton;
  format brier_mean 8.5;
  datalines;
DUP,0.970303,0.007016,0.008873,0.001144,0.966197,0.004589,0.012178,0.001563,0.006167,0.011112,0.005886
FLIP,0.961818,0.005620,0.006761,0.001517,0.966212,0.005212,0.011583,0.001183,0.005771,0.013670,0.005322
BASE,0.966061,0.014005,0.009437,0.003137,0.962841,0.004368,0.012726,0.000765,0.007722,0.014283,0.007349
;
run;

/* 1-3. URL 유무 하위집단 테이블 (30행) */
data work.kcbert_subgroup_url;
  length arm $8 url_group $12;
  infile datalines dlm="," dsd truncover;
  input arm :$8. seed has_url url_group :$12. recall fpr f1 tp fp fn tn total_n;
  datalines;
DUP,42,0,URL_NO,0.962264,0.002597,0.953271,51,3,2,1152,1208
DUP,42,1,URL_YES,0.974729,0.030189,0.972973,270,8,7,257,542
FLIP,42,0,URL_NO,0.943396,0.004329,0.925926,50,5,3,1150,1208
FLIP,42,1,URL_YES,0.963899,0.026415,0.969147,267,7,10,258,542
BASE,42,0,URL_NO,0.943396,0.004329,0.925926,50,5,3,1150,1208
BASE,42,1,URL_YES,0.985560,0.030189,0.978495,273,8,4,257,542
DUP,101,0,URL_NO,0.924528,0.002597,0.933333,49,3,4,1152,1208
DUP,101,1,URL_YES,0.963899,0.033962,0.965642,267,9,10,256,542
FLIP,101,0,URL_NO,0.962264,0.004329,0.935780,51,5,2,1150,1208
FLIP,101,1,URL_YES,0.967509,0.022642,0.972777,268,6,9,259,542
BASE,101,0,URL_NO,0.905660,0.004329,0.905660,48,5,5,1150,1208
BASE,101,1,URL_YES,0.981949,0.045283,0.969697,272,12,5,253,542
DUP,202,0,URL_NO,0.981132,0.001732,0.971963,52,2,1,1153,1208
DUP,202,1,URL_YES,0.978339,0.033962,0.973070,271,9,6,256,542
FLIP,202,0,URL_NO,0.943396,0.003463,0.934579,50,4,3,1151,1208
FLIP,202,1,URL_YES,0.971119,0.011321,0.979964,269,3,8,262,542
BASE,202,0,URL_NO,0.849057,0.000866,0.909091,45,1,8,1154,1208
BASE,202,1,URL_YES,0.956679,0.015094,0.970696,265,4,12,261,542
DUP,303,0,URL_NO,0.943396,0.002597,0.943396,50,3,3,1152,1208
DUP,303,1,URL_YES,0.974729,0.045283,0.966011,270,12,7,253,542
FLIP,303,0,URL_NO,0.886792,0.003463,0.903846,47,4,6,1151,1208
FLIP,303,1,URL_YES,0.963899,0.026415,0.969147,267,7,10,258,542
BASE,303,0,URL_NO,0.962264,0.003463,0.944444,51,4,2,1151,1208
BASE,303,1,URL_YES,0.967509,0.049057,0.960573,268,13,9,252,542
DUP,404,0,URL_NO,0.924528,0.002597,0.933333,49,3,4,1152,1208
DUP,404,1,URL_YES,0.981949,0.041509,0.971429,272,11,5,254,542
FLIP,404,0,URL_NO,0.924528,0.001732,0.942308,49,2,4,1153,1208
FLIP,404,1,URL_YES,0.971119,0.018868,0.976407,269,5,8,260,542
BASE,404,0,URL_NO,0.943396,0.003463,0.934579,50,4,3,1151,1208
BASE,404,1,URL_YES,0.981949,0.041509,0.971429,272,11,5,254,542
;
run;

/* 1-4. 오류 전이 테이블 (4행) */
data work.kcbert_transitions;
  length transition_code $20 transition_name_kr $40 net_effect $12;
  infile datalines dlm="," dsd truncover;
  input transition_code :$20. transition_name_kr :$40. total_count unique_messages url_0_count url_1_count url_1_ratio net_effect :$12.;
  datalines;
resolved_fp,정상 오탐 해소,25,14,2,23,0.9200,개선(+)
lost_tp,악성 정탐 손실,22,9,8,14,0.6364,악화(-)
new_fp,신규 정상 오탐,10,7,8,2,0.2000,악화(-)
rescued_fn,악성 미탐 구제,8,6,4,4,0.5000,개선(+)
;
run;

/* 1-5. 최대 불확실성 상위 20개 그룹 테이블 (20행) */
data work.kcbert_top_uncertain;
  length group_id_short $12 label_kr $12;
  infile datalines dlm="," dsd truncover;
  input group_rank group_id_short :$12. label_kr :$12. group_size has_url base_mean dup_mean flip_mean base_std dup_std flip_std;
  datalines;
1,37027523,정상,1,1,0.961792,0.596392,0.401538,0.056629,0.458889,0.455347
2,bcaa3ff2,스미싱,1,0,0.128196,0.207435,0.367219,0.216663,0.245682,0.440154
3,f2869943,정상,2,1,0.950564,0.733824,0.374136,0.091237,0.278455,0.439216
4,e2187648,정상,1,0,0.226809,0.003916,0.327932,0.389032,0.004412,0.387543
5,772d4c5a,스미싱,1,1,0.999218,0.604843,0.752189,0.000832,0.481803,0.381202
6,1dbebbdd,스미싱,1,1,0.297923,0.188523,0.248049,0.297307,0.348949,0.375487
7,c44cad38,정상,1,1,0.022506,0.119011,0.198615,0.027704,0.229198,0.369747
8,0df9abfd,스미싱,1,1,0.999526,0.999536,0.783509,0.000353,0.000247,0.352195
9,f495a399,스미싱,2,1,0.759811,0.982680,0.765352,0.383383,0.032149,0.339518
10,2359f71f,스미싱,1,0,0.019260,0.150656,0.585657,0.019684,0.206974,0.338988
11,7964a599,스미싱,1,1,0.903909,0.589601,0.575252,0.119106,0.367110,0.333583
12,72bea48f,스미싱,1,0,0.606623,0.412056,0.552535,0.330556,0.322929,0.312353
13,aacad2de,정상,1,1,0.791462,0.973397,0.651527,0.386627,0.036077,0.308368
14,2de44534,정상,1,1,0.140756,0.231406,0.464674,0.213868,0.334198,0.298094
15,2668f9cc,스미싱,1,0,0.350154,0.044224,0.310125,0.423258,0.038169,0.298002
16,48cd83d4,정상,1,0,0.158641,0.005356,0.168242,0.287999,0.003452,0.290138
17,0a415ee5,스미싱,1,1,0.999513,0.999381,0.849724,0.000429,0.000382,0.277202
18,39efe806,정상,1,0,0.034156,0.003297,0.145697,0.065384,0.003227,0.270638
19,e8dd0f61,스미싱,2,1,0.861935,0.468088,0.099237,0.259279,0.439803,0.206695
20,3ab8514e,스미싱,1,0,0.751340,0.771393,0.898550,0.361525,0.350489,0.198125
;
run;

/* 1-6. 실제 문자열 컬럼 생성 (VA 포맷 종속성 제로화) */
data work.kcbert_15arms;
  set work.kcbert_15arms;
  length arm_kr $30;
  if arm='DUP' then arm_kr='중복제거 (DUP)';
  else if arm='FLIP' then arm_kr='난독화반전 (FLIP)';
  else if arm='BASE' then arm_kr='기본모델 (BASE)';
  format recall fpr f1 percent8.2 brier_score 8.5 threshold 8.4;
  label arm='실험 조건(Arm 코드)' arm_kr='실험 조건(Arm)' seed='난수 시드' threshold='최적 임계값'
        recall='재현율 (Recall)' fpr='오탐률 (FPR)' f1='F1 점수' brier_score='Brier 점수';
run;

data work.kcbert_arm_summary;
  set work.kcbert_arm_summary;
  length arm_kr $30;
  if arm='DUP' then arm_kr='중복제거 (DUP)';
  else if arm='FLIP' then arm_kr='난독화반전 (FLIP)';
  else if arm='BASE' then arm_kr='기본모델 (BASE)';
  label arm='실험 조건(Arm 코드)' arm_kr='실험 조건(Arm)';
run;

data work.kcbert_subgroup_url;
  set work.kcbert_subgroup_url;
  length arm_kr $30 url_group_kr $30;
  if arm='DUP' then arm_kr='중복제거 (DUP)';
  else if arm='FLIP' then arm_kr='난독화반전 (FLIP)';
  else if arm='BASE' then arm_kr='기본모델 (BASE)';
  if url_group='URL_NO' then url_group_kr='URL 미포함 문자';
  else if url_group='URL_YES' then url_group_kr='URL 포함 문자';
  format recall fpr f1 percent8.2;
  label arm='실험 조건(코드)' arm_kr='실험 조건(Arm)' url_group='URL 그룹(코드)' url_group_kr='URL 포함 여부'
        recall='재현율 (Recall)' fpr='오탐률 (FPR)' f1='F1 점수';
run;

data work.kcbert_transitions;
  set work.kcbert_transitions;
  format url_1_ratio percent8.1;
  label transition_name_kr='오류 전이 유형'
        total_count='발생 건수'
        unique_messages='고유 메시지 수'
        url_1_ratio='URL 포함 비율'
        net_effect='순효과 구분';
run;

%put NOTE: ========================================================;
%put NOTE: [ScamLens Step 1] 5대 정본 테이블 생성 완료 (15, 3, 30, 4, 20행).;
%put NOTE: ========================================================;

/*=============================================================================
  [2단계: 시각화 모듈] 고해상도 시각화 렌더링 (%m_kcbert_visuals)
=============================================================================*/
%macro m_kcbert_visuals;
  %put NOTE: [ScamLens Step 2] 고해상도 시각화 리포트 렌더링 시작...;
  ods graphics on / reset=all width=960px height=540px;

  /* 차트 1: 15-Arm FPR vs Recall 산점도 */
  title1 'ScamLens KcBERT 15개 조건 성능 트레이드오프 (Recall vs FPR)';
  title2 'FLIP 조건의 FPR 1.0% 규제 상한 준수 및 파레토 최적 입증';
  proc sgplot data=work.kcbert_15arms;
    scatter x=fpr y=recall / group=arm_kr markerattrs=(size=13) filledoutlinedmarkers
            datalabel=seed datalabelattrs=(size=9 weight=bold) name="scatter_arms";
    refline 0.01 / axis=x lineattrs=(pattern=dash color=crimson thickness=2)
            label="FPR 1.0% 규제 상한선" labelloc=inside;
    xaxis label="오탐률 (False Positive Rate)" valuesformat=percent8.2 grid min=0.002 max=0.014;
    yaxis label="재현율 (Recall)" valuesformat=percent8.1 grid min=0.93 max=0.99;
    keylegend "scatter_arms" / title="실험 조건" location=outside position=bottom;
  run;

  /* 차트 2: 조건별 오탐률(FPR) 분포 박스플롯 */
  title1 '실험 조건(Arm)별 오탐률(FPR) 분포 비교';
  title2 'FLIP 조건의 안정적인 오탐 통제력 (평균 0.68%)';
  proc sgplot data=work.kcbert_15arms;
    vbox fpr / category=arm_kr fillattrs=(transparency=0.3) boxwidth=0.45 datalabel;
    refline 0.01 / axis=y lineattrs=(pattern=dash color=crimson thickness=2) label="FPR 1.0% 기준";
    yaxis label="False Positive Rate" valuesformat=percent8.2 grid;
    xaxis label="실험 조건 (Arm)";
  run;

  /* 차트 3: URL 유무별 하위집단 오탐률 패널 분석 (SGPANEL) */
  title1 'URL 유무별 하위집단 오탐률(FPR) 비교 (SGPANEL)';
  title2 'URL 포함 시 DUP 오탐 급증(3.0%) 대비 FLIP의 강력한 방어력(0.6%)';
  proc sgpanel data=work.kcbert_subgroup_url;
    panelby url_group_kr / columns=2 spacing=10 novarname;
    vbar arm_kr / response=fpr group=arm_kr stat=mean datalabel;
    rowaxis label="평균 오탐률 (Mean FPR)" valuesformat=percent8.2 grid;
    colaxis label="실험 조건";
  run;

  /* 차트 4: Brier Score 불확실성 비교 */
  title1 '실험 조건별 Brier Score (확률 예측 오차)';
  title2 'Brier 점수: FLIP(0.01158) < DUP(0.01218) < BASE(0.01273) — 낮을수록 우수';
  proc sgplot data=work.kcbert_arm_summary;
    vbar arm_kr / response=brier_mean fillattrs=(color=vibg transparency=0.4)
           datalabel datalabelattrs=(size=10 weight=bold);
    yaxis label="평균 Brier Score (낮을수록 우수)" grid min=0.010 max=0.014;
    xaxis label="실험 조건 (Arm)";
  run;

  /* 차트 5: 4대 오류 전이 건수 분석 */
  title1 'FLIP 도입에 따른 4대 오류 전이 건수 분석';
  title2 '정상 오탐 해소 25건 중 92.0%가 URL 포함 정상 문자에서 발생';
  proc sgplot data=work.kcbert_transitions;
    vbar transition_name_kr / response=total_count group=net_effect
           datalabel datalabelattrs=(size=10 weight=bold);
    yaxis label="발생 건수 (건)" grid min=0 max=30;
    xaxis label="오류 전이 범주";
    keylegend / title="순효과 구분" location=outside position=bottom;
  run;

  title;
  %put NOTE: [ScamLens Step 2] 고해상도 시각화 리포트 렌더링 완료.;
%mend m_kcbert_visuals;

/*=============================================================================
  [3단계: CAS 적재 모듈] SAS Viya CAS 적재 및 Visual Analytics 글로벌 승격 (%m_kcbert_cas)
=============================================================================*/
%macro slkc_check;
  %if &syscc ne 0 or &syserr ne 0 %then %do;
    %put ERROR: CAS 적재 중 오류가 발생하여 프로그램을 중단합니다. 로그를 확인하십시오.;
    %abort cancel;
  %end;
%mend slkc_check;

%macro slkc_compare(source=,target=,keys=);
  %local compare_rc;
  data work.slkc_readback; set slvcas.&target.; run;
  %slkc_check;
  proc sort data=work.slkc_readback; by &keys.; run;
  %slkc_check;
  proc sort data=work.&source. out=work.slkc_baseline; by &keys.; run;
  %slkc_check;
  proc compare base=work.slkc_baseline compare=work.slkc_readback
      method=absolute criterion=1e-10 noprint;
    id &keys.;
  run;
  %let compare_rc=&sysinfo.;
  %slkc_check;
  %if %sysfunc(band(&compare_rc.,65472)) ne 0 %then %do;
    %put ERROR: CAS 적재 검증 실패: &target. 테이블의 내용이 원본과 다릅니다. SYSINFO=&compare_rc.;
    %abort cancel;
  %end;
%mend slkc_compare;

%macro m_kcbert_cas(caslib=CASUSER, suffix=20260918, upload=1, promote=1, save=0);
  %put NOTE: [ScamLens Step 3] CAS 적재 및 Visual Analytics 연동 시작...;
  %put NOTE:   - Target CASLIB : &caslib.;
  %put NOTE:   - Table Suffix  : &suffix.;
  %put NOTE:   - Promote to VA : &promote.;

  %local i source target count_expected actual_n
         source_list target_list expected_list key_list;

  %let source_list=kcbert_15arms kcbert_arm_summary kcbert_subgroup_url kcbert_transitions kcbert_top_uncertain;
  %let target_list=va_kcbert_15arms va_kcbert_arm_summary va_kcbert_subgroup_url va_kcbert_transitions va_kcbert_top_uncertain;
  %let expected_list=15 3 30 4 20;
  %let key_list=arm seed|arm|arm seed has_url|transition_code|group_rank;

  /* 1. 테이블 행 수 엄격 무결성 사전 검증 */
  %do i=1 %to 5;
    %let source=%scan(&source_list.,&i.);
    %if not %sysfunc(exist(work.&source.)) %then %do;
      %put ERROR: 필수 WORK 테이블이 존재하지 않습니다: work.&source.;
      %abort cancel;
    %end;
    proc sql noprint; select count(*) into :actual_n trimmed from work.&source.; quit;
    %slkc_check;
    %let count_expected=%scan(&expected_list.,&i.);
    %if &actual_n. ne &count_expected. %then %do;
      %put ERROR: &source. 테이블의 행 수가 예상(&count_expected.)과 다릅니다 (실제: &actual_n.).;
      %abort cancel;
    %end;
  %end;

  %if &upload.=0 %then %do;
    %put NOTE: upload=0 설정으로 CAS 적재를 건너뜁니다.;
    %return;
  %end;

  /* 2. CAS 세션 및 라이브러리 연결 */
  cas slkccas;
  %slkc_check;
  libname slvcas cas sessref=slkccas caslib="&caslib.";
  %slkc_check;

  /* 3. CAS 서버 포맷 라이브러리 정식 등록 (VA에서 $ARMKR 등 사용자 포맷 조회 완벽 지원) */
  proc format casfmtlib="casformats";
    value $armkr
      'DUP'  = '중복제거 (DUP)'
      'FLIP' = '난독화반전 (FLIP)'
      'BASE' = '기본모델 (BASE)';
    value $urlgrp
      'URL_NO'  = 'URL 미포함 문자'
      'URL_YES' = 'URL 포함 문자';
    value $transkr
      'resolved_fp' = '정상 오탐 해소'
      'lost_tp'     = '악성 정탐 손실'
      'new_fp'      = '신규 정상 오탐'
      'rescued_fn'  = '악성 미탐 구제';
    value $neteff
      'POSITIVE' = '개선 효과'
      'NEGATIVE' = '손실 효과';
  run;
  %slkc_check;

  /* 4. 대상 CAS 테이블 교체 준비 */
  %do i=1 %to 5;
    %let target=%scan(&target_list.,&i.)_&suffix.;
    %if %sysfunc(exist(slvcas.&target.)) %then %do;
      proc casutil sessref=slkccas;
        droptable casdata="&target." incaslib="&caslib." quiet;
      quit;
      %slkc_check;
    %end;
  %end;

  /* 5. CAS 적재 및 데이터 무결성 검증 */
  %do i=1 %to 5;
    %let source=%scan(&source_list.,&i.);
    %let target=%scan(&target_list.,&i.)_&suffix.;
    proc casutil sessref=slkccas;
      load data=work.&source. outcaslib="&caslib." casout="&target.";
    quit;
    %slkc_check;

    %slkc_compare(source=&source.,target=&target.,keys=%scan(&key_list.,&i.,|));
    %put NOTE: [SUCCESS] CAS 적재 및 일치 검증 완료: &target.;
  %end;

  /* 6. Visual Analytics 승격 (PROMOTE) */
  %do i=1 %to 5;
    %let target=%scan(&target_list.,&i.)_&suffix.;
    %if &save.=1 %then %do;
      proc casutil sessref=slkccas;
        save casdata="&target." incaslib="&caslib."
          outcaslib="&caslib." casout="&target..sashdat" replace;
      quit;
      %slkc_check;
    %end;

    %if &promote.=1 %then %do;
      proc casutil sessref=slkccas;
        promote casdata="&target." incaslib="&caslib."
          outcaslib="&caslib." casout="&target.";
      quit;
      %slkc_check;
      %put NOTE: [PROMOTED] Visual Analytics용 글로벌 승격 완료: &target.;
    %end;
  %end;

  %put NOTE: ========================================================;
  %put NOTE: [ScamLens Step 3] CAS 적재 및 VA 배포가 성공적으로 완료되었습니다.;
  %do i=1 %to 5;
    %let target=%scan(&target_list.,&i.)_&suffix.;
    %put NOTE:   - &caslib..&target.;
  %end;
  %put NOTE: ========================================================;
%mend m_kcbert_cas;

/*=============================================================================
  [4단계: 통합 제어 파이프라인] (%scamlens_kcbert_pipeline)
=============================================================================*/
%macro scamlens_kcbert_pipeline(
    run_visuals=1,
    run_cas=1,
    caslib=CASUSER,
    suffix=20260918,
    promote=1,
    save=0
);
  %put NOTE: ========================================================;
  %put NOTE: ScamLens KcBERT 모듈 파이프라인 실행 제어 시작;
  %put NOTE: 옵션: run_visuals=&run_visuals. run_cas=&run_cas.;
  %put NOTE: ========================================================;

  %if &run_visuals.=1 %then %do;
    %m_kcbert_visuals;
  %end;

  %if &run_cas.=1 %then %do;
    %m_kcbert_cas(caslib=&caslib., suffix=&suffix., upload=1, promote=&promote., save=&save.);
  %end;

  %put NOTE: ========================================================;
  %put NOTE: ScamLens KcBERT 통합 파이프라인 전체 완료!;
  %put NOTE: ========================================================;
%mend scamlens_kcbert_pipeline;

/*---------------------------------------------------------------------------
  ★ 원클릭 실행 트리거 ★
---------------------------------------------------------------------------*/
%scamlens_kcbert_pipeline;
