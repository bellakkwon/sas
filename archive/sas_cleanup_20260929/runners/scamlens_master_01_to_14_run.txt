/*---------------------------------------------------------------------------
  ScamLens 00_RUN_MASTER_01_TO_14 — 전체 분석 파이프라인 (01 ~ 14) 마스터 실행기

  프로젝트: ScamLens (안심문자 탐지 및 난독화 강건성 연구)
  작성일: 2026-09-18
  버전: v2.1 (A/B 디렉터리 자동 초기화 및 무결성 파이프라인)
  
  [전체 파이프라인 구성]
  ■ Track 1: 베이스라인 머신러닝 & 감사 파이프라인
    - Step 1: 01_load_and_audit.sas          (데이터 감사 및 적재)
    - Step 2: 07_composition_and_novelty.sas (특징 구성 및 신종 분석)
    - Step 3: 02_meta_classifier.sas         (메타 분류기 학습/평가)
    - Step 4: 03_model_comparison.sas        (ROC/PR 모델 성능 비교)
    - Step 5: 06_transformer_contrast.sas    (트랜스포머 대조 분석)
    - Step 6: 05_visuals.sas                 (베이스라인 종합 시각화)
    - Step 7: 08_fage_gate.sas               (FAGE 공정성/신뢰성 게이트)

  ■ Track 2: 인간-AI 검수자 합의 및 A/B CAS 배포
    - Step 8: 00_RUN_AB_CAS.sas              (11 일치도 + 12 합의모델 + 13 CAS 적재)

  ■ Track 3: 심층 KcBERT 15-Arm 시각화 및 CAS 배포
    - Step 9: 14_kcbert_visuals.sas          (5대 정본 테이블 + 5종 ODS 그래픽스 + VA 승격)
---------------------------------------------------------------------------*/

%global projroot run_tag runout;

/* 1. 환경 변수 및 필수 디렉터리 자동 초기화 */
%macro init_master_env;
  %if %length(%superq(projroot))=0 %then %do;
    %if %sysfunc(fileexist(/home/student/github/sas/14_kcbert_visuals.sas)) %then %do;
      %let projroot=/home/student/github;
    %end;
    %else %if %sysfunc(fileexist(/Users/sangwoolee/sas/sas/sas/14_kcbert_visuals.sas)) %then %do;
      %let projroot=/Users/sangwoolee/sas/sas;
    %end;
    %else %do;
      %let projroot=/home/student/github;
    %end;
  %end;

  /* Track 2용 runout 디렉터리 사전 생성 */
  %if %length(%superq(runout))=0 %then %do;
    %let run_tag=ab_20260914_%sysfunc(datetime(),hex16.);
    %let runout=&projroot./outputs/&run_tag.;
    data _null_;
      length created $1024;
      if not fileexist("&projroot./outputs") then created=dcreate('outputs',"&projroot.");
      if not fileexist("&runout.") then created=dcreate("&run_tag.","&projroot./outputs");
    run;
  %end;
%mend init_master_env;
%init_master_env;

/* 상태 기록 테이블 초기화 */
data work.scamlens_master_run_status;
  length step 8 stage_num $10 stage_name $45 program $35 status $15 syscc 8;
  stop;
run;

%macro run_substage(step_idx, stage_id, stage_desc, sas_file);
  %put NOTE: ;
  %put NOTE: =========================================================================;
  %put NOTE: >>> [Step &step_idx.] &stage_desc. (&sas_file.);
  %put NOTE: =========================================================================;
  
  %local file_path cur_syscc;
  %let file_path=&projroot./sas/&sas_file.;
  
  %if not %sysfunc(fileexist(&file_path.)) %then %do;
    %put WARNING: 실행 파일이 존재하지 않아 건너뜁니다: &file_path.;
    data work._tmp_status;
      length step 8 stage_num $10 stage_name $45 program $35 status $15 syscc 8;
      step = &step_idx.;
      stage_num = "&stage_id.";
      stage_name = "&stage_desc.";
      program = "&sas_file.";
      status = "SKIPPED";
      syscc = .;
    run;
  %end;
  %else %do;
    %let syscc=0;
    %include "&file_path.";
    %let cur_syscc=&syscc.;
    
    data work._tmp_status;
      length step 8 stage_num $10 stage_name $45 program $35 status $15 syscc 8;
      step = &step_idx.;
      stage_num = "&stage_id.";
      stage_name = "&stage_desc.";
      program = "&sas_file.";
      syscc = &cur_syscc.;
      if syscc <= 4 then status = "SUCCESS";
      else status = "ERROR";
    run;
  %end;
  
  proc append base=work.scamlens_master_run_status data=work._tmp_status force; run;
%mend run_substage;

%macro run_scamlens_full_master;
  %local t_start t_end;
  %let t_start=%sysfunc(datetime());

  %put NOTE: =========================================================================;
  %put NOTE: ScamLens 01 ~ 14 전체 마스터 파이프라인 시작 (실행 환경: &projroot.);
  %put NOTE: 시작 시각: %sysfunc(datetime(), datetime20.);
  %put NOTE: =========================================================================;

  /* [Track 1] 베이스라인 머신러닝 및 데이터 감사 */
  %run_substage(1, 01, 데이터 적재 및 무결성 감사, 01_load_and_audit.sas);
  %run_substage(2, 07, 특징 구성 및 신종 스미싱 분석, 07_composition_and_novelty.sas);
  %run_substage(3, 02, 메타 분류기 학습 및 평가, 02_meta_classifier.sas);
  %run_substage(4, 03, 단일/앙상블 모델 비교 (ROC), 03_model_comparison.sas);
  %run_substage(5, 06, 트랜스포머 vs ML 대조 분석, 06_transformer_contrast.sas);
  %run_substage(6, 05, 베이스라인 종합 시각화, 05_visuals.sas);
  %run_substage(7, 08, FAGE 공정성 및 신뢰성 게이트, 08_fage_gate.sas);

  /* [Track 2] 인간-AI 검수자 합의 및 A/B CAS 배포 */
  %run_substage(8, 11-13, 검수자 A/B 합의 및 CAS 배포, 00_RUN_AB_CAS.sas);

  /* [Track 3] 심층 KcBERT 15-Arm 강건성 시각화 및 CAS 글로벌 승격 */
  %run_substage(9, 14, KcBERT 15-Arm 시각화 & CAS 배포, 14_kcbert_visuals.sas);

  %let t_end=%sysfunc(datetime());
  %put NOTE: =========================================================================;
  %put NOTE: ScamLens 01 ~ 14 전체 마스터 파이프라인 완주 완료!;
  %put NOTE: 총 소요 시간: %sysfunc(round(%sysevalf(&t_end. - &t_start.), 0.01)) 초;
  %put NOTE: =========================================================================;

  /* 최종 종합 실행 현황표 출력 */
  title1 "ScamLens 01 ~ 14 전체 파이프라인 단계별 실행 결과 현황표";
  title2 "전체 세부 단계 완주 요약 (SUCCESS / SKIPPED / ERROR)";
  proc print data=work.scamlens_master_run_status noobs;
    var step stage_num stage_name program status syscc;
  run;
  title;
%mend run_scamlens_full_master;

%run_scamlens_full_master;
