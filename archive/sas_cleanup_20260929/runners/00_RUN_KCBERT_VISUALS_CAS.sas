/*
  ScamLens 00_RUN_KCBERT_VISUALS_CAS — KcBERT 시각화 및 CAS 적재 통합 실행기
  
  작성일: 2026-09-18
  역할:
    14_kcbert_visuals.sas (14+15 통합 모듈화 파이프라인)를 실행하여
    - 5개 정본 요약 테이블 생성 및 무결성 검증 (Module 1)
    - 5종 핵심 고해상도 SGPLOT/SGPANEL 그래픽스 리포트 렌더링 (Module 2)
    - SAS Viya CASUSER 세션에 테이블 적재 및 Visual Analytics 글로벌 승격 (Module 3)
    을 단일 호출로 한 번에 완결합니다.
*/

/* 1. 기본 환경 설정 */
%macro init_kcbert_runner;
  %global projroot run_data run_visuals run_cas slkc_caslib slkc_promote slkc_save;
  %if not %symexist(projroot) %then %do;
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
  %if not %symexist(run_data) %then %let run_data=1;
  %if not %symexist(run_visuals) %then %let run_visuals=1;
  %if not %symexist(run_cas) %then %let run_cas=1;
  %if not %symexist(slkc_caslib) %then %let slkc_caslib=CASUSER;
  %if not %symexist(slkc_promote) %then %let slkc_promote=1;
  %if not %symexist(slkc_save) %then %let slkc_save=0;
%mend init_kcbert_runner;
%init_kcbert_runner;

%put NOTE: ========================================================;
%put NOTE: ScamLens KcBERT 시각화 & CAS 통합 모듈러 워크플로 시작;
%put NOTE: 프로젝트 루트 : &projroot.;
%put NOTE: 데이터 생성  : &run_data.;
%put NOTE: 시각화 차트  : &run_visuals.;
%put NOTE: CAS 적재 활성: &run_cas.;
%put NOTE: 대상 CASLIB  : &slkc_caslib.;
%put NOTE: ========================================================;

/* 2. 14+15 통합 모듈러 파이프라인 실행 */
%include "&projroot./sas/14_kcbert_visuals.sas";

%if &syscc ne 0 or &syserr ne 0 %then %do;
  %put ERROR: 14_kcbert_visuals.sas 통합 실행 중 오류 발생.;
  %abort cancel;
%end;

%put NOTE: ========================================================;
%put NOTE: [SUCCESS] ScamLens KcBERT 통합 워크플로가 완벽하게 성공했습니다.;
%put NOTE: ========================================================;
