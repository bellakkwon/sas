/*---------------------------------------------------------------------------
  ScamLens 15 — KcBERT 시각화 테이블 CAS 적재 및 SAS Visual Analytics(VA) 연동

  프로젝트: ScamLens (안심문자 탐지 및 난독화 강건성 연구)
  작성일: 2026-09-18
  목적: 14_kcbert_visuals.sas에서 검증/임포트된 5개 요약 테이블을
        SAS Viya CAS(Cloud Analytic Services) 메모리에 적재 및 승격(promote)하여,
        SAS Visual Analytics (VA)에서 대시보드 리포트를 즉시 구성할 수 있게 한다.

  ★ 실행 순서 및 선행 조건 ★
  1. 동일 Compute 세션에서 14_kcbert_visuals.sas 를 먼저 실행하여 WORK 테이블을 생성한다.
  2. CAS 세션을 활성화할 수 있는 SAS Viya 환경에서 본 프로그램을 실행한다.
  3. slkc_upload=1, slkc_promote=1 설정 시 VA에서 해당 테이블이 즉시 검색/선택 가능해진다.
---------------------------------------------------------------------------*/

%macro slkc_check;
  %if &syscc ne 0 or &syserr ne 0 %then %do;
    %put ERROR: CAS 적재 중 오류가 발생하여 프로그램을 중단합니다. 로그를 확인하십시오.;
    %abort cancel;
  %end;
%mend slkc_check;

%macro slkc_compare(source=,target=,keys=);
  %local compare_rc;
  /* CAS에 적재된 테이블을 Compute 세션으로 다시 읽어와 정렬 후 완벽 일치 비교 */
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

%macro slkc_publish_main;
  %global slkc_caslib slkc_suffix slkc_upload slkc_promote slkc_save slkc_complete;
  %local i source target count_expected actual_n bad
         source_list target_list expected_list key_list;

  /* 기본 매개변수 설정 */
  %if %length(%superq(slkc_caslib))=0 %then %let slkc_caslib=CASUSER;
  %if %length(%superq(slkc_suffix))=0 %then %let slkc_suffix=20260918;
  %if %length(%superq(slkc_upload))=0 %then %let slkc_upload=1;
  %if %length(%superq(slkc_promote))=0 %then %let slkc_promote=1;
  %if %length(%superq(slkc_save))=0 %then %let slkc_save=0;
  %let slkc_complete=0;

  %put NOTE: ========================================================;
  %put NOTE: ScamLens KcBERT CAS 적재 시작;
  %put NOTE: Target CASLIB  : &slkc_caslib.;
  %put NOTE: Table Suffix   : &slkc_suffix.;
  %put NOTE: Upload / Promote: &slkc_upload. / &slkc_promote.;
  %put NOTE: ========================================================;

  /* 1. WORK 라이브러리의 5개 필수 테이블 존재 및 건수 검증 */
  %let source_list=kcbert_15arms kcbert_arm_summary kcbert_subgroup_url kcbert_transitions kcbert_top_uncertain;
  %let target_list=va_kcbert_15arms va_kcbert_arm_summary va_kcbert_subgroup_url va_kcbert_transitions va_kcbert_top_uncertain;
  %let expected_list=15 3 30 4 20;
  %let key_list=arm seed|arm|arm seed has_url|transition_code|group_rank;

  %do i=1 %to 5;
    %let source=%scan(&source_list.,&i.);
    %if not %sysfunc(exist(work.&source.)) %then %do;
      %put ERROR: 필수 WORK 테이블이 없습니다: work.&source.;
      %put ERROR- 14_kcbert_visuals.sas를 먼저 실행하십시오.;
      %abort cancel;
    %end;
    proc sql noprint; select count(*) into :actual_n trimmed from work.&source.; quit;
    %slkc_check;
    %let count_expected=%scan(&expected_list.,&i.);
    %if &actual_n. ne &count_expected. %then %do;
      %put ERROR: &source. 테이블의 행 수가 예상(&count_expected.)과 다릅니다(실제: &actual_n.).;
      %abort cancel;
    %end;
  %end;

  %if &slkc_upload.=0 %then %do;
    %put NOTE: slkc_upload=0 이므로 CAS 업로드를 건너뜁니다.;
    %return;
  %end;

  /* 2. CAS 세션 시작 및 라이브러리 연결 */
  cas slkccas;
  %slkc_check;
  libname slvcas cas sessref=slkccas caslib="&slkc_caslib.";
  %slkc_check;

  /* 3. 대상 CAS 테이블 중복 검사 (이미 존재하면 사전에 알림) */
  %do i=1 %to 5;
    %let target=%scan(&target_list.,&i.)_&slkc_suffix.;
    %if %sysfunc(exist(slvcas.&target.)) %then %do;
      %put WARNING: 대상 CAS 테이블 &target. 이(가) 이미 존재합니다. 교체 적재를 진행합니다.;
      proc casutil sessref=slkccas;
        droptable casdata="&target." incaslib="&slkc_caslib." quiet;
      quit;
      %slkc_check;
    %end;
  %end;

  /* 4. 테이블 CAS 적재 및 데이터 무결성 검증 */
  %do i=1 %to 5;
    %let source=%scan(&source_list.,&i.);
    %let target=%scan(&target_list.,&i.)_&slkc_suffix.;
    proc casutil sessref=slkccas;
      load data=work.&source. outcaslib="&slkc_caslib." casout="&target.";
    quit;
    %slkc_check;

    /* 적재 후 Readback 정합성 검사 */
    %slkc_compare(source=&source.,target=&target.,keys=%scan(&key_list.,&i.,|));
    %put NOTE: [SUCCESS] CAS 적재 및 정합성 검증 완료: &target.;
  %end;

  /* 5. 선택적 영구 저장(SAVE) 및 VA 승격(PROMOTE) */
  %do i=1 %to 5;
    %let target=%scan(&target_list.,&i.)_&slkc_suffix.;
    %if &slkc_save.=1 %then %do;
      proc casutil sessref=slkccas;
        save casdata="&target." incaslib="&slkc_caslib."
          outcaslib="&slkc_caslib." casout="&target..sashdat" replace;
      quit;
      %slkc_check;
      %put NOTE: [SAVED] .sashdat 파일 영구 저장 완료: &target.;
    %end;

    %if &slkc_promote.=1 %then %do;
      proc casutil sessref=slkccas;
        promote casdata="&target." incaslib="&slkc_caslib."
          outcaslib="&slkc_caslib." casout="&target.";
      quit;
      %slkc_check;
      %put NOTE: [PROMOTED] Visual Analytics용 글로벌 승격 완료: &target.;
    %end;
  %end;

  %let slkc_complete=1;
  %put NOTE: ========================================================;
  %put NOTE: ScamLens KcBERT CAS 테이블 배포가 성공적으로 완료되었습니다.;
  %put NOTE: 이제 SAS Visual Analytics에서 아래 테이블을 선택해 대시보드를 구성할 수 있습니다:;
  %do i=1 %to 5;
    %let target=%scan(&target_list.,&i.)_&slkc_suffix.;
    %put NOTE:   - &slkc_caslib..&target.;
  %end;
  %put NOTE: ========================================================;
%mend slkc_publish_main;

%slkc_publish_main;
