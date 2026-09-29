/*-----------------------------------------------------------------------------
  ScamLens 00_RUN_ALL — SAS Viya / SAS 9.4 공통 통합 마스터 실행기

  [개요]
  ScamLens(안심문자 탐지 및 난독화 강건성 연구)의 전체 분석 파이프라인을 단일
  진입점에서 실행하는 공개 실행기입니다. 호출 시마다 outputs/ 디렉터리 하위에
  새로운 고유 식별자(run_<UUID>) 폴더를 생성(sl_output_root)하여 이전 실행 결과를
  보존하고 분석 결과를 완전히 격리합니다.

  [복사하여 바로 실행하는 방법 (SAS Studio / Enterprise Guide)]
  -----------------------------------------------------------------------------
  1. 기본 자동 실행 (AUTO 프로파일: 데이터 완비 여부에 따라 가능한 모든 분석 실행)
     %let projroot = /home/student/github;
     %include "&projroot./sas/00_RUN_ALL.sas";

  2. 공개 집계 전용 실행 (PUBLIC 프로파일: 비공개 데이터 없이 공개 집계 및 시각화만 실행)
     %let projroot = /home/student/github;
     %let sl_profile = PUBLIC;
     %include "&projroot./sas/00_RUN_ALL.sas";

  3. 전체 데이터 완전 검증 실행 (FULL 프로파일: 비공개 원본 데이터 완비 필수 검증)
     %let projroot = /home/student/github;
     %let sl_profile = FULL;
     %include "&projroot./sas/00_RUN_ALL.sas";

  4. 한국어 n-gram 텍스트 모형(04) 포함 실행
     %let projroot = /home/student/github;
     %let sl_run_text = 1;
     %include "&projroot./sas/00_RUN_ALL.sas";

  5. SAS Viya CAS 인메모리 배포(13, 15, 32) 포함 실행
     %let projroot = /home/student/github;
     %let sl_run_cas = 1;
     %include "&projroot./sas/00_RUN_ALL.sas";
  -----------------------------------------------------------------------------

  [전역 제어 매크로 변수 설명]
  - projroot    : 프로젝트 루트 디렉터리 경로 (기본값: /home/student/github, 호출자 설정 유지)
  - sl_profile  : 실행 프로파일 (기본값: AUTO)
                  * AUTO   : 투입 가능한 데이터 및 의존성에 맞추어 모든 가용 단계 실행
                  * PUBLIC : 공개 집계 단계(14, 21, 99, 31 및 CAS)만 실행, 비공개 단계 비활성화
                  * FULL   : 분석 시작 전 필수 비공개 데이터 및 01 감사 후 OOF 검증 필수 강제
  - sl_run_cas  : CAS 인메모리 테이블 적재 및 글로벌 승격 여부 (0: 비활성, 1: 활성)
                  미지정 기본값은 SAS Viya 1, SAS 9.4 0. 호출자의 명시적 설정은 유지한다.
  - sl_run_text : 04_korean_text_model.sas 실행 여부 (0: 건너뜀 [기본값], 1: 실행)
  - sl_run_zip  : 21 후속 진단 결과 ZIP 압축 패키징 여부 (1: 압축 실행 [기본값], 0: 비활성)

  [안전 및 무결성 보장 원칙]
  - 세션 진입 시 이전 세션의 잔여 오류(SYSCC>0)를 거부하고 클린 세션을 요구합니다.
  - 세션 재호출 시 이전 완료 플래그 및 WORK 임시/상태 테이블을 자동 리셋합니다.
  - 각 단계(%include) 시작 직전 run_status.csv에 RUNNING 체크포인트를 즉시 저장하며,
    체크포인트 저장 실패 시 해당 단계 실행을 즉시 차단합니다.
  - %include 직후 ODS 닫기/PRINTTO 복원 전에 SYSCC와 SYSERR을 독립 지역 변수에 즉시 포착합니다.
  - 모듈 오류 발생 시 포착된 실패 코드를 온전히 보존한 상태에서 스코프 리셋을 통해 실패 사실을
    디스크(run_status.csv, master_run.log)에 안전하게 영구 기록하고 즉시 중단합니다.
  - 건너뛴 단계(disabled, missing_input, missing_upstream)는 명확히 구분되며 성공으로 간주되지 않습니다.
  - CAS 게시 시 고유 UUID 접미사(V7 호환, 8~12자)를 사용하여 기존 테이블 덮어쓰기를 방지합니다.
  - 모든 완료 표기는 절차적 완료(completed_check_log)이며, 로그 및 표의 검수가 필수입니다.
-----------------------------------------------------------------------------*/

/* 전역 매크로 변수 사전 선언 및 충돌 방지 초기화 */
%global projroot sl_profile sl_run_cas sl_run_text sl_run_zip
        sl_output_root sl_run_id sasdata runout run_tag
        sas_oof_ready sas_meta_fit_completed text_threshold meta_threshold
        sc11_complete sc12_complete slva_complete slkc_visuals_complete slkc_complete
        sl_followup_run sl_followup_outdir sl_followup_complete
        sv_report_complete sv_cas_complete sv_root sv_loaded sv_outdir sv_runid
        slva_caslib slva_suffix slva_upload slva_promote slva_save
        slkc_caslib slkc_suffix slkc_upload slkc_promote slkc_save
        sv_suffix zip_run sl_followup_zip_path sl_followup_zip_complete;

/* 0. 세션 시작 전 잔여 오류(SYSCC) 감지 및 클린 세션 강제 */
%macro sl_check_initial_syscc;
  %if %length(&syscc.) > 0 %then %do;
    %if &syscc. > 0 %then %do;
      %put ERROR: [ScamLens] 이전 SAS 작업의 잔여 SYSCC(=&syscc.)가 감지되었습니다.;
      %put ERROR- 파이프라인의 안전한 실행과 정확한 상태 추적을 위해 새로운 클린 세션(fresh session)이 필요합니다.;
      %abort cancel;
    %end;
  %end;
%mend sl_check_initial_syscc;
%sl_check_initial_syscc;

/* 0-1. 동일 세션 재실행 대비 전역 플래그 및 WORK 상태 리셋 */
%macro sl_reset_session_context;
  %let sas_oof_ready = 0;
  %let sas_meta_fit_completed = 0;
  %let sc11_complete = 0;
  %let sc12_complete = 0;
  %let slva_complete = 0;
  %let slkc_visuals_complete = 0;
  %let slkc_complete = 0;
  %let sl_followup_complete = 0;
  %let sv_report_complete = 0;
  %let sv_cas_complete = 0;
  %let sv_loaded = 0;
  %let text_threshold = ;
  %let meta_threshold = ;
  %let sl_followup_run = ;
  %let sl_followup_outdir = ;
  %let sv_outdir = ;
  %let sv_runid = ;
  %let zip_run = ;
  %let sl_followup_zip_path = ;
  %let sl_followup_zip_complete = 0;

  proc datasets lib=work nolist nowarn;
    delete scamlens_run_status _sl_new_row scab_status scab_run_context
           slva_key_check slva_duplicate_keys;
  quit;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] WORK 라이브러리 세션 상태 초기화 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;
%mend sl_reset_session_context;

/* 1. 옵션 기본값 및 유효성 검증 */
%macro sl_validate_options;
  %if %length(%superq(projroot))=0 %then %let projroot=/home/student/github;
  %if %length(%superq(sl_profile))=0 %then %let sl_profile=AUTO;
  %let sl_profile = %upcase(&sl_profile.);
  %if "&sl_profile." ne "AUTO" and "&sl_profile." ne "PUBLIC" and "&sl_profile." ne "FULL" %then %do;
    %put ERROR: [ScamLens] 유효하지 않은 sl_profile 값입니다 (&sl_profile.). AUTO, PUBLIC, FULL 중 하나여야 합니다.;
    %abort cancel;
  %end;
  /* Viya 기본 실행에는 CAS 게시를 포함하고, 명시적 0/1은 유지한다. */
  %if %length(%superq(sl_run_cas))=0 %then %do;
    %if "%substr(%upcase(&sysvlong.),1,2)"="V." %then %let sl_run_cas=1;
    %else %let sl_run_cas=0;
  %end;
  %if "&sl_run_cas." ne "0" and "&sl_run_cas." ne "1" %then %do;
    %put ERROR: [ScamLens] sl_run_cas 값은 0 또는 1이어야 합니다 (&sl_run_cas.).;
    %abort cancel;
  %end;
  %put NOTE: [ScamLens] CAS 게시 옵션: sl_run_cas=&sl_run_cas. SAS=&sysvlong.;
  %if %length(%superq(sl_run_text))=0 %then %let sl_run_text=0;
  %if "&sl_run_text." ne "0" and "&sl_run_text." ne "1" %then %do;
    %put ERROR: [ScamLens] sl_run_text 값은 0 또는 1이어야 합니다 (&sl_run_text.).;
    %abort cancel;
  %end;
  %if %length(%superq(sl_run_zip))=0 %then %let sl_run_zip=1;
  %if "&sl_run_zip." ne "0" and "&sl_run_zip." ne "1" %then %do;
    %put ERROR: [ScamLens] sl_run_zip 값은 0 또는 1이어야 합니다 (&sl_run_zip.).;
    %abort cancel;
  %end;
%mend sl_validate_options;

/* 2. UTF-8 세션 인코딩 무결성 검증 */
%macro sl_assert_utf8;
  %local enc;
  %let enc = %upcase(%sysfunc(getoption(encoding)));
  %if "&enc." ne "UTF8" and "&enc." ne "UTF-8" %then %do;
    %put ERROR: [ScamLens] 세션 인코딩이 UTF-8이 아닙니다 (&enc.). SAS 세션을 UTF-8로 시작하십시오.;
    %abort cancel;
  %end;
%mend sl_assert_utf8;

/* 3. 파일 존재 및 비결측(non-empty) 무결성 가드 */
%macro sl_expect_nonempty(path, label);
  data _null_;
    length p $2048;
    p = "%superq(path)";
    rc = filename('_slchk', p);
    if rc ne 0 then do;
      put "ERROR: [ScamLens] 파일 참조자 할당 실패 (&label): " p;
      abort cancel;
    end;
    fid = fopen('_slchk', 'I', 1, 'B');
    if fid = 0 then do;
      put "ERROR: [ScamLens] 필수 파일 또는 산출물이 누락되었습니다 (&label): " p;
      abort cancel;
    end;
    read_rc = fread(fid);
    rc = fclose(fid);
    rc = filename('_slchk');
    if read_rc ne 0 then do;
      put "ERROR: [ScamLens] 필수 파일 또는 산출물이 비어 있습니다 (&label): " p;
      abort cancel;
    end;
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %abort cancel;
%mend sl_expect_nonempty;

/* 4. 고유 실행 출력 디렉터리 및 상태 테이블 초기화 */
%macro sl_init_output_dir;
  %let sl_run_id = run_%sysfunc(compress(%sysfunc(uuidgen()),'-'));
  %let sl_output_root = &projroot./outputs/&sl_run_id.;
  %let runout = &sl_output_root.;
  %let run_tag = ab_20260914_%sysfunc(datetime(),hex16.);
  %let sasdata = &projroot./data/processed/sas;
  %let sv_root = &sl_output_root.;

  data _null_;
    length parent root $2048 created $1024;
    parent = symget('projroot');
    if not fileexist(cats(parent, '/outputs')) then created = dcreate('outputs', parent);
    if not fileexist(cats(parent, '/outputs')) then do;
      put "ERROR: [ScamLens] outputs 디렉터리를 생성할 수 없습니다: " parent;
      abort cancel;
    end;
    root = symget('sl_output_root');
    if fileexist(root) then do;
      put "ERROR: [ScamLens] 실행 출력 디렉터리가 이미 존재합니다 (덮어쓰기 거부): " root;
      abort cancel;
    end;
    created = dcreate(symget('sl_run_id'), cats(parent, '/outputs'));
    if not fileexist(root) then do;
      put "ERROR: [ScamLens] 고유 실행 출력 디렉터리를 생성하지 못했습니다: " root;
      abort cancel;
    end;
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %abort cancel;

  data work.scamlens_run_status;
    length step 8 stage $32 program $40 state $32 syscc 8 syserr 8 timestamp $24 details $120;
    stop;
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] scamlens_run_status 데이터셋 초기화 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;
%mend sl_init_output_dir;

/* 5. 사전 점검 (Preflight Check): 프로그램 및 공개/비공개 데이터 검증 */
%macro sl_preflight;
  %put NOTE: [ScamLens Preflight] 활성 SAS 프로그램 및 공개 집계 데이터 사전 점검 시작...;

  /* 5-1. 필수 활성 프로그램 18개 점검 */
  %sl_expect_nonempty(&projroot./sas/07_composition_and_novelty.sas, 07_composition_and_novelty.sas);
  %sl_expect_nonempty(&projroot./sas/01_load_and_audit.sas, 01_load_and_audit.sas);
  %sl_expect_nonempty(&projroot./sas/02_meta_classifier.sas, 02_meta_classifier.sas);
  %sl_expect_nonempty(&projroot./sas/03_model_comparison.sas, 03_model_comparison.sas);
  %sl_expect_nonempty(&projroot./sas/04_korean_text_model.sas, 04_korean_text_model.sas);
  %sl_expect_nonempty(&projroot./sas/05_visuals.sas, 05_visuals.sas);
  %sl_expect_nonempty(&projroot./sas/06_transformer_contrast.sas, 06_transformer_contrast.sas);
  %sl_expect_nonempty(&projroot./sas/08_fage_gate.sas, 08_fage_gate.sas);
  %sl_expect_nonempty(&projroot./sas/11_reviewer_ab_agreement.sas, 11_reviewer_ab_agreement.sas);
  %sl_expect_nonempty(&projroot./sas/12_consensus_model_comparison.sas, 12_consensus_model_comparison.sas);
  %sl_expect_nonempty(&projroot./sas/13_publish_ab_to_cas.sas, 13_publish_ab_to_cas.sas);
  %sl_expect_nonempty(&projroot./sas/14_kcbert_visuals.sas, 14_kcbert_visuals.sas);
  %sl_expect_nonempty(&projroot./sas/15_publish_kcbert_to_cas.sas, 15_publish_kcbert_to_cas.sas);
  %sl_expect_nonempty(&projroot./sas/21_followup_diagnostics.sas, 21_followup_diagnostics.sas);
  %sl_expect_nonempty(&projroot./sas/30_load_final_aggregates.sas, 30_load_final_aggregates.sas);
  %sl_expect_nonempty(&projroot./sas/31_final_visualization.sas, 31_final_visualization.sas);
  %sl_expect_nonempty(&projroot./sas/32_publish_final_to_cas.sas, 32_publish_final_to_cas.sas);
  %sl_expect_nonempty(&projroot./sas/99_ZIP_FOLLOWUP_OUTPUTS.sas, 99_ZIP_FOLLOWUP_OUTPUTS.sas);

  /* 5-2. 필수 공개 집계 CSV 15개 점검 */
  %sl_expect_nonempty(&projroot./data/aggregates/followup/u5/eval_metadata_summary.csv, fu_eval_metadata);
  %sl_expect_nonempty(&projroot./data/aggregates/followup/u5/model_seed_diagnostics.csv, fu_model_seed);
  %sl_expect_nonempty(&projroot./data/aggregates/followup/u5/error_breakdown_by_feature.csv, fu_error_feature);
  %sl_expect_nonempty(&projroot./data/aggregates/followup/u5/truncation_audit_summary.csv, fu_truncation);
  %sl_expect_nonempty(&projroot./data/aggregates/followup/u5/persistent_error_summary.csv, fu_persistent);
  %sl_expect_nonempty(&projroot./data/aggregates/followup/u5/paired_transition_summary.csv, fu_transition);
  %sl_expect_nonempty(&projroot./data/aggregates/followup/comparison/aggregate.csv, fu_comparison);
  %sl_expect_nonempty(&projroot./data/aggregates/followup/fusion/aggregate.csv, fu_fusion);
  %sl_expect_nonempty(&projroot./data/aggregates/followup/kisa_ocr_diagnostics_20260921.csv, fu_kisa_ocr);

  %sl_expect_nonempty(&projroot./data/aggregates/final/u5_models.csv, final_u5_models);
  %sl_expect_nonempty(&projroot./data/aggregates/final/u5_features.csv, final_u5_features);
  %sl_expect_nonempty(&projroot./data/aggregates/final/u5_truncation.csv, final_u5_truncation);
  %sl_expect_nonempty(&projroot./data/aggregates/final/kisa_conditions.csv, final_kisa_conditions);
  %sl_expect_nonempty(&projroot./data/aggregates/final/jev_comparison.csv, final_jev_comparison);
  %sl_expect_nonempty(&projroot./data/aggregates/final/jev_fusion.csv, final_jev_fusion);

  /* 5-3. FULL 프로파일인 경우 필수 비공개 파일 사전 점검 */
  %if "&sl_profile." = "FULL" %then %do;
    %put NOTE: [ScamLens Preflight] FULL 프로파일 필수 비공개 원본 파일 점검 시작...;
    %sl_expect_nonempty(&sasdata./sas_external_evaluation.csv, sas_external_evaluation);
    %sl_expect_nonempty(&sasdata./sas_message_scores.csv, sas_message_scores);
    %sl_expect_nonempty(&sasdata./sas_message_text.csv, sas_message_text);
    %sl_expect_nonempty(&sasdata./sas_robustness.csv, sas_robustness);
    %sl_expect_nonempty(&sasdata./sas_fage_abc_rows.csv, sas_fage_abc_rows);
    %sl_expect_nonempty(&sasdata./sas_reviewer_ab_20260914.csv, sas_reviewer_ab);
    %sl_expect_nonempty(&sasdata./sas_consensus_predictions_20260914.csv, sas_consensus_predictions);
  %end;

  %put NOTE: [ScamLens Preflight] 사전 점검 완료: 모든 필수 프로그램 및 집계 데이터 정상 확인.;
%mend sl_preflight;

/* 6. 마스터 실행 로그 초기화 및 단계별 기록 매크로 */
%macro sl_init_master_log;
  data _null_;
    file "&sl_output_root./master_run.log";
    put '===============================================================================';
    put 'ScamLens SAS 파이프라인 마스터 실행 로그 (Master Run Log)';
    put '===============================================================================';
    put "RUN_ID       : &sl_run_id";
    put "PROFILE      : &sl_profile";
    put "PROJROOT     : &projroot";
    put "OUTPUT_ROOT  : &sl_output_root";
    put "SAS_VERSION  : &sysvlong";
    put "START_TIME   : &sysdate9. &systime.";
    put "OPTIONS      : sl_run_cas=&sl_run_cas sl_run_text=&sl_run_text sl_run_zip=&sl_run_zip";
    put '-------------------------------------------------------------------------------';
    put 'NOTE: 모든 단계별 상세 실행 로그와 HTML 리포트는 outputs 디렉터리 내에 개별 저장됩니다.';
    put 'NOTE: SAS 런타임 결과는 로그 ERROR/WARNING 및 수치 일치도를 연구자가 직접 검수해야 합니다.';
    put '===============================================================================';
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] master_run.log 초기화 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;
%mend sl_init_master_log;

%macro sl_append_master_log(stage, program, state, result_cc, result_err, details);
  data _null_;
    file "&sl_output_root./master_run.log" mod;
    length msg $256;
    msg = cats('[', put(datetime(), datetime20.), '] ', "&stage.", ' (', "&program.", '): ',
               "&state.", ' (SYSCC=', put(&result_cc., best.), ' SYSERR=', put(&result_err., best.), ') - ', "%superq(details)");
    put msg;
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] master_run.log 추가 기록 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;
%mend sl_append_master_log;

/* 7. 단계별 상태 기록 및 디스크 즉시 플러시 */
%macro sl_record_step(step, stage, program, state, result_cc, result_err, details);
  %local cur_ts;
  %let cur_ts = %sysfunc(datetime(), datetime20.);

  data work._sl_new_row;
    length step 8 stage $32 program $40 state $32 syscc 8 syserr 8 timestamp $24 details $120;
    step = &step.;
    stage = "&stage.";
    program = "&program.";
    state = "&state.";
    syscc = &result_cc.;
    syserr = &result_err.;
    timestamp = "&cur_ts.";
    details = "%superq(details)";
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 상태 임시 데이터셋(_sl_new_row) 생성 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;

  data work.scamlens_run_status;
    set work.scamlens_run_status(where=(stage ne "&stage."))
        work._sl_new_row;
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 상태 누적 데이터셋(scamlens_run_status) 갱신 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;

  proc sort data=work.scamlens_run_status;
    by step;
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 상태 누적 데이터셋 정렬 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;

  proc export data=work.scamlens_run_status
    outfile="&sl_output_root./run_status.csv"
    dbms=csv replace;
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] run_status.csv 디스크 내보내기 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;

  %sl_append_master_log(&stage., &program., &state., &result_cc., &result_err., %superq(details));
%mend sl_record_step;

/* 8. 단계 건너뜀 기록 헬퍼
   설명문은 %superq로 전달한다. 등호가 있는 문구는 호출부에서 %nrstr로,
   실행 결과 매크로 변수를 포함한 문구는 %bquote로 감싸 키워드 인자 오해석을 막는다. */
%macro sl_skip_step(step, stage, program, state, details);
  %sl_record_step(&step., &stage., &program., &state., ., ., %superq(details));
  %put NOTE: [ScamLens 건너뜀] 단계=&stage. (&program.) 상태=&state. 사유=%superq(details);
%mend sl_skip_step;

/* 9. 일반 모듈 실행 매크로 (사전 RUNNING 체크포인트 저장 및 독립 상태 포착) */
%macro sl_run_ordinary(step_idx, stage_id, prog_name, completion_var=);
  %local _cur_err _cur_cc _step_state _comp_val;
  %let _comp_val=1;
  %if %length(&completion_var.) > 0 %then %do;
    %global &completion_var.;
    %let &completion_var.=0;
  %end;

  /* 1. %include 실행 직전 RUNNING 상태를 디스크(run_status.csv)에 영구 기록 */
  %sl_record_step(&step_idx., &stage_id., &prog_name., running, ., ., 실행 중 체크포인트);
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 단계 &stage_id. 체크포인트 저장 실패. 실행을 중단합니다.;
    %abort cancel;
  %end;

  /* 2. 단계별 독립 LOG 및 HTML 목적지 설정 */
  proc printto log="&sl_output_root./&stage_id..log" new; run;
  %put NOTE: SCAMLENS_STAGE=&stage_id. PROGRAM=&prog_name. SAS_VERSION=&sysvlong. DATE=&sysdate9. TIME=&systime.;
  ods html path="&sl_output_root." (url=none) file="&stage_id..html" style=HTMLBlue;

  /* 3. 모듈 실행 */
  %include "&projroot./sas/&prog_name.";

  /* 4. ODS 닫기 및 PRINTTO 복원 전에 SYSCC와 SYSERR을 즉시 독립 로컬에 포착 */
  %let _cur_err = &syserr.;
  %let _cur_cc = &syscc.;

  /* 5. ODS 및 PRINTTO 정리 */
  ods html close;
  proc printto; run;

  /* 6. 완료 플래그 확인 */
  %if %length(&completion_var.) > 0 %then %do;
    %let _comp_val = &&&completion_var.;
  %end;

  /* 7. 상태 판정 및 하위 단계 중단 제어 */
  %if &_cur_err. = 0 and &_cur_cc. = 0 and &_comp_val. = 1 %then %do;
    %let _step_state = completed_check_log;
    %sl_record_step(&step_idx., &stage_id., &prog_name., &_step_state., &_cur_cc., &_cur_err., 정상 실행 완료 로그 검수 필요);
  %end;
  %else %if &_cur_err. = 0 and &_cur_cc. = 4 %then %do;
    %let _step_state = requires_review;
    /* 경고 발생 상태 포착 완료. 기록기 자체 I/O 상태 검증을 위해 SYSCC 일시 리셋 */
    %let syscc = 0;
    %sl_record_step(&step_idx., &stage_id., &prog_name., &_step_state., &_cur_cc., &_cur_err., %nrstr(경고 발생(SYSCC=4) 수동 검수 필요));
    %put ERROR: [ScamLens] 단계 &stage_id. (&prog_name.) 에서 경고(SYSCC=4)가 발생했습니다.;
    %put ERROR- 로그를 검토하십시오: &sl_output_root./&stage_id..log;
    %put ERROR- 검토 필요/실패 단계 발생으로 하위 파이프라인 실행을 중단합니다.;
    %abort cancel;
  %end;
  %else %do;
    %let _step_state = failed;
    /* [Scoped SYSCC Reset]
       모듈 실행 실패 상태(SYSERR=&_cur_err., SYSCC=&_cur_cc., COMP=&_comp_val.)를 이미 포착하였습니다.
       이 실패 상태를 run_status.csv 및 master_run.log에 정상 기록하고,
       상태 기록기 자체의 오류(I/O 실패 등)를 정확히 판별하기 위해 SYSCC를 일시 0으로 재설정합니다.
       기록 완료 직후 어떠한 추가 분석 단계도 실행하지 않고 즉시 %abort cancel 처리합니다. */
    %if &syscc. > 4 %then %let syscc = 0;
    %sl_record_step(&step_idx., &stage_id., &prog_name., &_step_state., &_cur_cc., &_cur_err., %bquote(실행 오류 발생(SYSERR=&_cur_err. SYSCC=&_cur_cc. COMP=&_comp_val.)));
    %put ERROR: [ScamLens] 단계 &stage_id. (&prog_name.) 실행이 실패했습니다 (SYSERR=&_cur_err. SYSCC=&_cur_cc. COMP=&_comp_val.).;
    %put ERROR- 로그를 확인하십시오: &sl_output_root./&stage_id..log;
    %put ERROR- 오류 발생으로 하위 파이프라인 실행을 중단합니다.;
    %abort cancel;
  %end;
%mend sl_run_ordinary;

/* 10. 자체 ODS/LOG 소유 모듈 21 (21_followup_diagnostics.sas) 실행 매크로 */
%macro sl_run_21(step_idx);
  %local _cur_err _cur_cc _step_state;
  %let sl_followup_complete = 0;

  /* 1. RUNNING 체크포인트 저장 */
  %sl_record_step(&step_idx., 21_followup, 21_followup_diagnostics.sas, running, ., ., 후속 진단 4단계 종합 실행 중);
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 21_followup 체크포인트 저장 실패. 실행을 중단합니다.;
    %abort cancel;
  %end;

  /* 2. 모듈 직접 실행 (21은 내부에서 독립 로그와 HTML을 자체 생성함) */
  %include "&projroot./sas/21_followup_diagnostics.sas";

  /* 3. 상태 즉시 포착 */
  %let _cur_err = &syserr.;
  %let _cur_cc = &syscc.;

  /* 4. 상태 판정 */
  %if &_cur_err. = 0 and &_cur_cc. = 0 and &sl_followup_complete. = 1 %then %do;
    %sl_expect_nonempty(&sl_followup_outdir./followup_summary.html, followup_summary_html);
    %sl_expect_nonempty(&sl_followup_outdir./run_status.txt, followup_run_status_txt);
    %let _step_state = completed_check_log;
    %sl_record_step(&step_idx., 21_followup, 21_followup_diagnostics.sas, &_step_state., &_cur_cc., &_cur_err., 후속 진단 4단계 완료 산출물 검수 필요);
  %end;
  %else %if &_cur_err. = 0 and &_cur_cc. = 4 %then %do;
    %let _step_state = requires_review;
    %let syscc = 0;
    %sl_record_step(&step_idx., 21_followup, 21_followup_diagnostics.sas, &_step_state., &_cur_cc., &_cur_err., %nrstr(후속 진단 경고 발생(SYSCC=4)));
    %put ERROR: [ScamLens] 21_followup 경고 발생. 중단합니다.;
    %abort cancel;
  %end;
  %else %do;
    %let _step_state = failed;
    %if &syscc. > 4 %then %let syscc = 0;
    %sl_record_step(&step_idx., 21_followup, 21_followup_diagnostics.sas, &_step_state., &_cur_cc., &_cur_err., %bquote(후속 진단 실행 실패(COMP=&sl_followup_complete.)));
    %put ERROR: [ScamLens] 21_followup 실행 실패 (COMP=&sl_followup_complete.).;
    %abort cancel;
  %end;
%mend sl_run_21;

/* 11. 후속 진단 ZIP 압축 모듈 (99_ZIP_FOLLOWUP_OUTPUTS.sas) 실행 매크로 */
%macro sl_run_99(step_idx);
  %local _cur_err _cur_cc _step_state _zip_path;
  %let zip_run = &sl_followup_run.;
  %let sl_followup_zip_path = ;
  %let sl_followup_zip_complete = 0;

  /* 1. RUNNING 체크포인트 저장 */
  %sl_record_step(&step_idx., 99_zip_followup, 99_ZIP_FOLLOWUP_OUTPUTS.sas, running, ., ., 후속 진단 ZIP 아카이브 패키징 중);
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 99_zip_followup 체크포인트 저장 실패. 실행을 중단합니다.;
    %abort cancel;
  %end;

  /* 2. 압축 모듈 실행 */
  %include "&projroot./sas/99_ZIP_FOLLOWUP_OUTPUTS.sas";

  /* 3. 상태 즉시 포착 */
  %let _cur_err = &syserr.;
  %let _cur_cc = &syscc.;
  %let _zip_path = &sl_followup_zip_path.;

  /* 4. 상태 판정 */
  %if &_cur_err. = 0 and &_cur_cc. = 0 and &sl_followup_zip_complete. = 1 %then %do;
    %sl_expect_nonempty(&_zip_path., followup_zip_archive);
    %let _step_state = completed_check_log;
    %sl_record_step(&step_idx., 99_zip_followup, 99_ZIP_FOLLOWUP_OUTPUTS.sas, &_step_state., &_cur_cc., &_cur_err., ZIP 패키징 정상 완료 검증 통과);
  %end;
  %else %if &_cur_err. = 0 and &_cur_cc. = 4 %then %do;
    %let _step_state = requires_review;
    %let syscc = 0;
    %sl_record_step(&step_idx., 99_zip_followup, 99_ZIP_FOLLOWUP_OUTPUTS.sas, &_step_state., &_cur_cc., &_cur_err., %nrstr(ZIP 압축 중 경고 발생(SYSCC=4)));
    %put ERROR: [ScamLens] 99_ZIP 경고 발생. 중단합니다.;
    %abort cancel;
  %end;
  %else %do;
    %let _step_state = failed;
    %if &syscc. > 4 %then %let syscc = 0;
    %sl_record_step(&step_idx., 99_zip_followup, 99_ZIP_FOLLOWUP_OUTPUTS.sas, &_step_state., &_cur_cc., &_cur_err., ZIP 패키징 실패);
    %put ERROR: [ScamLens] 99_ZIP 패키징 실패.;
    %abort cancel;
  %end;
%mend sl_run_99;

/* 12. 자체 ODS 소유 모듈 31 (31_final_visualization.sas) 실행 매크로 */
%macro sl_run_31(step_idx);
  %local _cur_err _cur_cc _step_state;
  %let sv_report_complete = 0;
  %let sv_root = &sl_output_root.;

  /* 1. RUNNING 체크포인트 저장 */
  %sl_record_step(&step_idx., 31_final_visuals, 31_final_visualization.sas, running, ., ., 최종 종합 시각화 리포트 생성 중);
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 31_final_visuals 체크포인트 저장 실패. 실행을 중단합니다.;
    %abort cancel;
  %end;

  /* 2. 모듈 직접 실행 (31은 내부에서 30_load_final_aggregates를 포함하고 자체 ODS HTML5를 생성함) */
  %include "&projroot./sas/31_final_visualization.sas";

  /* 3. 상태 즉시 포착 */
  %let _cur_err = &syserr.;
  %let _cur_cc = &syscc.;

  /* 4. 상태 판정 */
  %if &_cur_err. = 0 and &_cur_cc. = 0 and &sv_report_complete. = 1 %then %do;
    %sl_expect_nonempty(&sv_outdir./final_visualization.html, final_visualization_html);
    %sl_expect_nonempty(&sv_outdir./run_status.txt, final_run_status_txt);
    %let _step_state = completed_check_log;
    %sl_record_step(&step_idx., 31_final_visuals, 31_final_visualization.sas, &_step_state., &_cur_cc., &_cur_err., 최종 시각화 리포트 정상 완료 검수 필요);
  %end;
  %else %if &_cur_err. = 0 and &_cur_cc. = 4 %then %do;
    %let _step_state = requires_review;
    %let syscc = 0;
    %sl_record_step(&step_idx., 31_final_visuals, 31_final_visualization.sas, &_step_state., &_cur_cc., &_cur_err., %nrstr(최종 시각화 경고 발생(SYSCC=4)));
    %put ERROR: [ScamLens] 31_final_visuals 경고 발생. 중단합니다.;
    %abort cancel;
  %end;
  %else %do;
    %let _step_state = failed;
    %if &syscc. > 4 %then %let syscc = 0;
    %sl_record_step(&step_idx., 31_final_visuals, 31_final_visualization.sas, &_step_state., &_cur_cc., &_cur_err., %bquote(최종 시각화 실패(COMP=&sv_report_complete.)));
    %put ERROR: [ScamLens] 31_final_visuals 실행 실패 (COMP=&sv_report_complete.).;
    %abort cancel;
  %end;
%mend sl_run_31;

/* 13. 선택적 CAS 배포 모듈 실행 매크로 (13, 15, 32) */
%macro sl_run_cas_13(step_idx);
  %local _cur_err _cur_cc _step_state;
  %let slva_complete = 0;
  %let slva_caslib = CASUSER;
  %let slva_suffix = v%substr(%sysfunc(compress(%sysfunc(uuidgen()),'-')),1,11);
  %let slva_upload = 1;
  %let slva_promote = 1;
  %let slva_save = 0;

  %sl_record_step(&step_idx., 13_cas_ab, 13_publish_ab_to_cas.sas, running, ., ., A/B 합의 테이블 CAS 업로드 중);
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 13_cas_ab 체크포인트 저장 실패. 실행을 중단합니다.;
    %abort cancel;
  %end;

  proc printto log="&sl_output_root./13_publish_ab_to_cas.log" new; run;
  %put NOTE: SCAMLENS_STAGE=13_cas_ab PROGRAM=13_publish_ab_to_cas.sas CASLIB=&slva_caslib. SUFFIX=&slva_suffix.;
  %include "&projroot./sas/13_publish_ab_to_cas.sas";
  %let _cur_err = &syserr.;
  %let _cur_cc = &syscc.;
  proc printto; run;

  %if &_cur_err. = 0 and &_cur_cc. = 0 and &slva_complete. = 1 %then %do;
    %let _step_state = completed_check_log;
    %sl_record_step(&step_idx., 13_cas_ab, 13_publish_ab_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., A/B CAS 적재 및 글로벌 승격 성공);
  %end;
  %else %if &_cur_err. = 0 and &_cur_cc. = 4 %then %do;
    %let _step_state = requires_review;
    %let syscc = 0;
    %sl_record_step(&step_idx., 13_cas_ab, 13_publish_ab_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., %nrstr(A/B CAS 적재 중 경고 발생(SYSCC=4)));
    %put ERROR: [ScamLens] 13_cas_ab 경고 발생. 중단합니다.;
    %abort cancel;
  %end;
  %else %do;
    %let _step_state = failed;
    %if &syscc. > 4 %then %let syscc = 0;
    %sl_record_step(&step_idx., 13_cas_ab, 13_publish_ab_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., %bquote(A/B CAS 적재 실패(COMP=&slva_complete.)));
    %put ERROR: [ScamLens] 13_cas_ab 실패 (COMP=&slva_complete.).;
    %abort cancel;
  %end;
%mend sl_run_cas_13;

%macro sl_run_cas_15(step_idx);
  %local _cur_err _cur_cc _step_state;
  %let slkc_complete = 0;
  %let slkc_caslib = CASUSER;
  %let slkc_suffix = k%substr(%sysfunc(compress(%sysfunc(uuidgen()),'-')),1,7);
  %let slkc_upload = 1;
  %let slkc_promote = 1;
  %let slkc_save = 0;

  %sl_record_step(&step_idx., 15_cas_kcbert, 15_publish_kcbert_to_cas.sas, running, ., ., KcBERT 5개 테이블 CAS 업로드 중);
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 15_cas_kcbert 체크포인트 저장 실패. 실행을 중단합니다.;
    %abort cancel;
  %end;

  proc printto log="&sl_output_root./15_publish_kcbert_to_cas.log" new; run;
  %put NOTE: SCAMLENS_STAGE=15_cas_kcbert PROGRAM=15_publish_kcbert_to_cas.sas CASLIB=&slkc_caslib. SUFFIX=&slkc_suffix.;
  %include "&projroot./sas/15_publish_kcbert_to_cas.sas";
  %let _cur_err = &syserr.;
  %let _cur_cc = &syscc.;
  proc printto; run;

  %if &_cur_err. = 0 and &_cur_cc. = 0 and &slkc_complete. = 1 %then %do;
    %let _step_state = completed_check_log;
    %sl_record_step(&step_idx., 15_cas_kcbert, 15_publish_kcbert_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., KcBERT CAS 적재 및 글로벌 승격 성공);
  %end;
  %else %if &_cur_err. = 0 and &_cur_cc. = 4 %then %do;
    %let _step_state = requires_review;
    %let syscc = 0;
    %sl_record_step(&step_idx., 15_cas_kcbert, 15_publish_kcbert_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., %nrstr(KcBERT CAS 적재 중 경고 발생(SYSCC=4)));
    %put ERROR: [ScamLens] 15_cas_kcbert 경고 발생. 중단합니다.;
    %abort cancel;
  %end;
  %else %do;
    %let _step_state = failed;
    %if &syscc. > 4 %then %let syscc = 0;
    %sl_record_step(&step_idx., 15_cas_kcbert, 15_publish_kcbert_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., %bquote(KcBERT CAS 적재 실패(COMP=&slkc_complete.)));
    %put ERROR: [ScamLens] 15_cas_kcbert 실패 (COMP=&slkc_complete.).;
    %abort cancel;
  %end;
%mend sl_run_cas_15;

%macro sl_run_cas_32(step_idx);
  %local _cur_err _cur_cc _step_state;
  %let sv_cas_complete = 0;
  %let sv_suffix = s%substr(%sysfunc(compress(%sysfunc(uuidgen()),'-')),1,7);
  %let sv_root = &sl_output_root.;

  %sl_record_step(&step_idx., 32_cas_final, 32_publish_final_to_cas.sas, running, ., ., 최종 6개 집계 테이블 CAS 업로드 중);
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 32_cas_final 체크포인트 저장 실패. 실행을 중단합니다.;
    %abort cancel;
  %end;

  proc printto log="&sl_output_root./32_publish_final_to_cas.log" new; run;
  %put NOTE: SCAMLENS_STAGE=32_cas_final PROGRAM=32_publish_final_to_cas.sas SUFFIX=&sv_suffix.;
  %include "&projroot./sas/32_publish_final_to_cas.sas";
  %let _cur_err = &syserr.;
  %let _cur_cc = &syscc.;
  proc printto; run;

  %if &_cur_err. = 0 and &_cur_cc. = 0 and &sv_cas_complete. = 1 %then %do;
    %sl_expect_nonempty(&sv_cas_outdir./cas_status.txt, final_cas_status_txt);
    %let _step_state = completed_check_log;
    %sl_record_step(&step_idx., 32_cas_final, 32_publish_final_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., 최종 집계 CAS 적재 및 승격 성공);
  %end;
  %else %if &_cur_err. = 0 and &_cur_cc. = 4 %then %do;
    %let _step_state = requires_review;
    %let syscc = 0;
    %sl_record_step(&step_idx., 32_cas_final, 32_publish_final_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., %nrstr(최종 CAS 적재 중 경고 발생(SYSCC=4)));
    %put ERROR: [ScamLens] 32_cas_final 경고 발생. 중단합니다.;
    %abort cancel;
  %end;
  %else %do;
    %let _step_state = failed;
    %if &syscc. > 4 %then %let syscc = 0;
    %sl_record_step(&step_idx., 32_cas_final, 32_publish_final_to_cas.sas, &_step_state., &_cur_cc., &_cur_err., %bquote(최종 CAS 적재 실패(COMP=&sv_cas_complete.)));
    %put ERROR: [ScamLens] 32_cas_final 실패 (COMP=&sv_cas_complete.).;
    %abort cancel;
  %end;
%mend sl_run_cas_32;

/* 14. 최종 요약 집계 및 검수 안내 보고 매크로 */
%macro sl_print_summary;
  %local n_total n_completed n_review n_failed n_running n_skipped overall_state
         _summary_err _summary_cc;

  proc sql noprint;
    select count(*) into :n_total trimmed from work.scamlens_run_status;
    select count(*) into :n_completed trimmed from work.scamlens_run_status where state = 'completed_check_log';
    select count(*) into :n_review trimmed from work.scamlens_run_status where state = 'requires_review';
    select count(*) into :n_failed trimmed from work.scamlens_run_status where state = 'failed';
    select count(*) into :n_running trimmed from work.scamlens_run_status where state = 'running';
    select count(*) into :n_skipped trimmed from work.scamlens_run_status where state like 'skipped%';
  quit;

  %if &n_failed. > 0 or &n_running. > 0 %then %let overall_state = failed;
  %else %if &n_review. > 0 %then %let overall_state = requires_review;
  %else %if &n_skipped. > 0 %then %let overall_state = completed_with_skips;
  %else %let overall_state = completed_check_logs;

  %put NOTE: ;
  %put NOTE: ===============================================================================;
  %put NOTE: [ScamLens] 전체 분석 파이프라인 실행 현황 요약;
  %put NOTE: -------------------------------------------------------------------------------;
  %put NOTE: 실행 식별자 (RUN_ID)   : &sl_run_id.;
  %put NOTE: 산출물 디렉터리        : &sl_output_root.;
  %put NOTE: 실행 프로파일 (PROFILE): &sl_profile.;
  %put NOTE: CAS 게시 옵션          : sl_run_cas=&sl_run_cas.;
  %put NOTE: 전체 등록 단계 수     : &n_total.;
  %put NOTE: 정상 완료 단계         : &n_completed.;
  %put NOTE: 검토 필요 단계 (경고)  : &n_review.;
  %put NOTE: 실행 실패 단계 (오류)  : &n_failed.;
  %put NOTE: 미완료/중단 단계       : &n_running.;
  %put NOTE: 건너뛴 단계            : &n_skipped.;
  %put NOTE: 최종 종합 판정         : &overall_state.;
  %put NOTE: ===============================================================================;
  %put NOTE: [실행 완료 및 검수 안내];
  %put NOTE: 프로그램 성공 표기(&overall_state.)는 절차적 실행 완료를 의미하며,;
  %put NOTE: 각 단계별 상세 로그(ERROR/WARNING 여부) 및 수치 반환값에 대한 연구자의 검수가 필요합니다.;
  %put NOTE: ===============================================================================;

  /* 31 등 자체 보고서가 모든 ODS 목적지를 닫아도 요약은 독립적으로 저장한다. */
  ods html(id=sl_summary) path="&sl_output_root." (url=none)
    file="run_summary.html" style=HTMLBlue;
  %if &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 요약 HTML 출력 목적지를 열지 못했습니다.;
    %abort cancel;
  %end;
  title1 "ScamLens SAS 전체 파이프라인 실행 요약표";
  title2 "RUN_ID: &sl_run_id. | PROFILE: &sl_profile. | VERDICT: &overall_state.";
  proc print data=work.scamlens_run_status noobs;
    var step stage program state syscc syserr details;
  run;
  %let _summary_err=&syserr.;
  %let _summary_cc=&syscc.;
  title;
  ods html(id=sl_summary) close;
  %if &_summary_err. ne 0 or &_summary_cc. ne 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] 요약표 출력 실패 (SYSERR=&_summary_err. SYSCC=&_summary_cc.).;
    %abort cancel;
  %end;
  %sl_expect_nonempty(&sl_output_root./run_summary.html, master_summary_html);
  %put NOTE: SUMMARY_HTML=&sl_output_root./run_summary.html;
  %if &slkc_complete. = 1 %then
    %put NOTE: CAS_KCBERT_TABLES=&slkc_caslib..va_kcbert_*_&slkc_suffix.;
  %if &sv_cas_complete. = 1 %then
    %put NOTE: CAS_FINAL_TABLES=CASUSER.slf_*_&sv_suffix.;

  data _null_;
    file "&sl_output_root./master_run.log" mod;
    put '===============================================================================';
    put 'EXECUTION SUMMARY:';
    put "RUN_ID        : &sl_run_id";
    put "PROFILE       : &sl_profile";
    put "CAS_ENABLED   : &sl_run_cas";
    put "SUMMARY_HTML  : &sl_output_root./run_summary.html";
    put "TOTAL_STEPS   : &n_total";
    put "COMPLETED     : &n_completed";
    put "REVIEW        : &n_review";
    put "FAILED        : &n_failed";
    put "RUNNING       : &n_running";
    put "SKIPPED       : &n_skipped";
    put "FINAL_VERDICT : &overall_state";
    put "END_TIME      : &sysdate9. &systime.";
    put '-------------------------------------------------------------------------------';
    put 'REVIEW NOTE: Pipeline execution finished. Stage logs, warning states, and';
    put '             numeric returns must be reviewed by the researcher.';
    put '===============================================================================';
  run;
  %if &syserr. > 0 or &syscc. > 4 %then %do;
    %put ERROR: [ScamLens] master_run.log 요약 기록 실패 (SYSERR=&syserr. SYSCC=&syscc.);
    %abort cancel;
  %end;
%mend sl_print_summary;

/* 15. 메인 오케스트레이션 매크로 (%sl_run_all) */
%macro sl_run_all;
  %sl_check_initial_syscc;
  %sl_reset_session_context;
  %sl_validate_options;
  %sl_assert_utf8;
  %sl_init_output_dir;
  %sl_init_master_log;
  %sl_preflight;

  %local sc07_complete sc01_complete sc02_complete sc03_complete sc06_complete
         sc05_complete sc04_complete sc08_complete;
  %let sc07_complete=0;
  %let sc01_complete=0;
  %let sc02_complete=0;
  %let sc03_complete=0;
  %let sc06_complete=0;
  %let sc05_complete=0;
  %let sc04_complete=0;
  %let sc08_complete=0;
  %let sc11_complete=0;
  %let sc12_complete=0;

  /* -------------------------------------------------------------------------
     Step 1: 07_composition_and_novelty.sas (독립 외부 평가 분석)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(1, 07_composition, 07_composition_and_novelty.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if not %sysfunc(fileexist(&sasdata./sas_external_evaluation.csv)) %then %do;
    %sl_skip_step(1, 07_composition, 07_composition_and_novelty.sas, skipped_missing_input, sas_external_evaluation.csv 결측);
  %end;
  %else %do;
    %sl_run_ordinary(1, 07_composition, 07_composition_and_novelty.sas);
    %let sc07_complete=1;
  %end;

  /* -------------------------------------------------------------------------
     Step 2: 01_load_and_audit.sas (데이터 적재 및 무결성 감사)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(2, 01_audit, 01_load_and_audit.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if not %sysfunc(fileexist(&sasdata./sas_message_scores.csv))
         or not %sysfunc(fileexist(&sasdata./sas_message_text.csv)) %then %do;
    %sl_skip_step(2, 01_audit, 01_load_and_audit.sas, skipped_missing_input, sas_message_scores 또는 text CSV 결측);
  %end;
  %else %do;
    %sl_run_ordinary(2, 01_audit, 01_load_and_audit.sas);
    %let sc01_complete=1;

    /* FULL 프로파일인 경우 01 직후 sas_oof_ready 검증 필수 */
    %if "&sl_profile." = "FULL" %then %do;
      %if &sas_oof_ready. ne 1 %then %do;
        %put ERROR: [ScamLens FULL 프로파일] 01 감사 후 sas_oof_ready가 1이 아닙니다 (값=&sas_oof_ready.).;
        %put ERROR- 검증된 OOF 입력이 없으므로 FULL 프로파일 계약에 따라 실행을 중단합니다.;
        %if &syscc. > 4 %then %let syscc = 0;
        %sl_record_step(2, 01_audit, 01_load_and_audit.sas, failed, 8, 0, FULL 프로파일 OOF 검증 실패);
        %abort cancel;
      %end;
    %end;
  %end;

  /* -------------------------------------------------------------------------
     Step 3: 02_meta_classifier.sas (문자·URL 결합 메타 분류기)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(3, 02_meta, 02_meta_classifier.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if &sc01_complete. ne 1 %then %do;
    %sl_skip_step(3, 02_meta, 02_meta_classifier.sas, skipped_missing_upstream, 01 감사 모듈 미완료);
  %end;
  %else %if &sas_oof_ready. ne 1 %then %do;
    %sl_skip_step(3, 02_meta, 02_meta_classifier.sas, skipped_missing_input, %nrstr(검증된 OOF 입력 부적격(sas_oof_ready=0)));
  %end;
  %else %do;
    %sl_run_ordinary(3, 02_meta, 02_meta_classifier.sas, completion_var=sas_meta_fit_completed);
    %let sc02_complete=1;
  %end;

  /* -------------------------------------------------------------------------
     Step 4: 03_model_comparison.sas (고정 test 점수 ROC-AUC 비교)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(4, 03_roc, 03_model_comparison.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if &sc01_complete. ne 1 %then %do;
    %sl_skip_step(4, 03_roc, 03_model_comparison.sas, skipped_missing_upstream, 01 감사 모듈 미완료);
  %end;
  %else %do;
    %sl_run_ordinary(4, 03_roc, 03_model_comparison.sas);
    %let sc03_complete=1;
  %end;

  /* -------------------------------------------------------------------------
     Step 5: 06_transformer_contrast.sas (트랜스포머 vs ML 대조 분석)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(5, 06_transformer, 06_transformer_contrast.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if &sc01_complete. ne 1 %then %do;
    %sl_skip_step(5, 06_transformer, 06_transformer_contrast.sas, skipped_missing_upstream, 01 감사 모듈 미완료);
  %end;
  %else %do;
    %sl_run_ordinary(5, 06_transformer, 06_transformer_contrast.sas);
    %let sc06_complete=1;
  %end;

  /* -------------------------------------------------------------------------
     Step 6: 05_visuals.sas (베이스라인 종합 시각화)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(6, 05_visuals, 05_visuals.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if &sc01_complete. ne 1 %then %do;
    %sl_skip_step(6, 05_visuals, 05_visuals.sas, skipped_missing_upstream, 01 감사 모듈 미완료);
  %end;
  %else %if not %sysfunc(fileexist(&sasdata./sas_robustness.csv)) %then %do;
    %sl_skip_step(6, 05_visuals, 05_visuals.sas, skipped_missing_input, sas_robustness.csv 결측);
  %end;
  %else %do;
    %sl_run_ordinary(6, 05_visuals, 05_visuals.sas);
    %let sc05_complete=1;
  %end;

  /* -------------------------------------------------------------------------
     Step 7: 04_korean_text_model.sas (선택적 한국어 n-gram 텍스트 모형)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(7, 04_text, 04_korean_text_model.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if &sl_run_text. ne 1 %then %do;
    %sl_skip_step(7, 04_text, 04_korean_text_model.sas, skipped_disabled_by_option, %nrstr(sl_run_text=0 (선택적 텍스트 모형 비활성화)));
  %end;
  %else %if &sc01_complete. ne 1 %then %do;
    %sl_skip_step(7, 04_text, 04_korean_text_model.sas, skipped_missing_upstream, 01 감사 모듈 미완료);
  %end;
  %else %do;
    %sl_run_ordinary(7, 04_text, 04_korean_text_model.sas);
    %let sc04_complete=1;
  %end;

  /* -------------------------------------------------------------------------
     Step 8: 08_fage_gate.sas (실패조건 FAGE 게이트)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(8, 08_fage, 08_fage_gate.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if not %sysfunc(fileexist(&sasdata./sas_fage_abc_rows.csv)) %then %do;
    %sl_skip_step(8, 08_fage, 08_fage_gate.sas, skipped_missing_input, sas_fage_abc_rows.csv 결측);
  %end;
  %else %do;
    %sl_run_ordinary(8, 08_fage, 08_fage_gate.sas);
    %let sc08_complete=1;
  %end;

  /* -------------------------------------------------------------------------
     Step 9 & 10: 11_reviewer_ab_agreement.sas 및 12_consensus_model_comparison.sas
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(9, 11_reviewer_ab, 11_reviewer_ab_agreement.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
    %sl_skip_step(10, 12_consensus_models, 12_consensus_model_comparison.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if not %sysfunc(fileexist(&sasdata./sas_reviewer_ab_20260914.csv))
         or not %sysfunc(fileexist(&sasdata./sas_consensus_predictions_20260914.csv)) %then %do;
    %sl_skip_step(9, 11_reviewer_ab, 11_reviewer_ab_agreement.sas, skipped_missing_input, AB 검수자 입력 CSV 결측);
    %sl_skip_step(10, 12_consensus_models, 12_consensus_model_comparison.sas, skipped_missing_upstream, 11 단계 미실행);
  %end;
  %else %do;
    %sl_run_ordinary(9, 11_reviewer_ab, 11_reviewer_ab_agreement.sas, completion_var=sc11_complete);
    %if &sc11_complete. = 1 %then %do;
      %sl_run_ordinary(10, 12_consensus_models, 12_consensus_model_comparison.sas, completion_var=sc12_complete);
    %end;
    %else %do;
      %sl_skip_step(10, 12_consensus_models, 12_consensus_model_comparison.sas, skipped_missing_upstream, 11 단계 미완료);
    %end;

    /* 11과 12가 모두 성공한 경우 13번 CAS 가드 충족을 위한 context 데이터셋 구성 */
    %if &sc11_complete. = 1 and &sc12_complete. = 1 %then %do;
      data work.scab_status;
        length stage $32 state $32;
        stage = '11_reviewer_ab';
        state = 'completed_check_return';
        output;
        stage = '12_consensus_models';
        state = 'completed_check_return';
        output;
      run;
      data work.scab_run_context;
        length stage $32 run_tag $64 input_version $32 analysis_contract $32;
        stage = 'all_stages';
        run_tag = "&run_tag.";
        input_version = 'ab_20260914';
        analysis_contract = 'ab_cas_20260915_v1';
      run;
    %end;
  %end;

  /* -------------------------------------------------------------------------
     Step 11: 13_publish_ab_to_cas.sas (A/B CAS 적재 및 글로벌 승격)
     ------------------------------------------------------------------------- */
  %if "&sl_profile." = "PUBLIC" %then %do;
    %sl_skip_step(11, 13_cas_ab, 13_publish_ab_to_cas.sas, skipped_disabled_by_profile, PUBLIC 프로파일: 비공개 데이터 모듈 비활성화);
  %end;
  %else %if &sc11_complete. ne 1 or &sc12_complete. ne 1 %then %do;
    %sl_skip_step(11, 13_cas_ab, 13_publish_ab_to_cas.sas, skipped_missing_upstream, 11 또는 12 단계 미완료);
  %end;
  %else %if &sl_run_cas. ne 1 %then %do;
    %sl_skip_step(11, 13_cas_ab, 13_publish_ab_to_cas.sas, skipped_disabled_by_option, %nrstr(sl_run_cas=0 (CAS 배포 비활성화)));
  %end;
  %else %do;
    %sl_run_cas_13(11);
  %end;

  /* -------------------------------------------------------------------------
     Step 12: 14_kcbert_visuals.sas (KcBERT 15-Arm 시각화)
     ------------------------------------------------------------------------- */
  %sl_run_ordinary(12, 14_kcbert_visuals, 14_kcbert_visuals.sas, completion_var=slkc_visuals_complete);

  /* -------------------------------------------------------------------------
     Step 13: 15_publish_kcbert_to_cas.sas (KcBERT CAS 적재 및 승격)
     ------------------------------------------------------------------------- */
  %if &slkc_visuals_complete. ne 1 %then %do;
    %sl_skip_step(13, 15_cas_kcbert, 15_publish_kcbert_to_cas.sas, skipped_missing_upstream, 14 KcBERT 시각화 미완료);
  %end;
  %else %if &sl_run_cas. ne 1 %then %do;
    %sl_skip_step(13, 15_cas_kcbert, 15_publish_kcbert_to_cas.sas, skipped_disabled_by_option, %nrstr(sl_run_cas=0 (CAS 배포 비활성화)));
  %end;
  %else %do;
    %sl_run_cas_15(13);
  %end;

  /* -------------------------------------------------------------------------
     Step 14: 21_followup_diagnostics.sas (후속 진단 4단계 종합 파이프라인)
     ------------------------------------------------------------------------- */
  %sl_run_21(14);

  /* -------------------------------------------------------------------------
     Step 15: 99_ZIP_FOLLOWUP_OUTPUTS.sas (후속 진단 산출물 ZIP 패키징)
     ------------------------------------------------------------------------- */
  %if &sl_run_zip. ne 1 %then %do;
    %sl_skip_step(15, 99_zip_followup, 99_ZIP_FOLLOWUP_OUTPUTS.sas, skipped_disabled_by_option, %nrstr(sl_run_zip=0 (ZIP 압축 비활성화)));
  %end;
  %else %if &sl_followup_complete. ne 1 %then %do;
    %sl_skip_step(15, 99_zip_followup, 99_ZIP_FOLLOWUP_OUTPUTS.sas, skipped_missing_upstream, 21 후속 진단 모듈 미완료);
  %end;
  %else %do;
    %sl_run_99(15);
  %end;

  /* -------------------------------------------------------------------------
     Step 16: 31_final_visualization.sas (최종 집계 ODS 리포트 및 시각화)
     ------------------------------------------------------------------------- */
  %sl_run_31(16);

  /* -------------------------------------------------------------------------
     Step 17: 32_publish_final_to_cas.sas (최종 집계 CAS 적재 및 승격)
     ------------------------------------------------------------------------- */
  %if &sv_report_complete. ne 1 %then %do;
    %sl_skip_step(17, 32_cas_final, 32_publish_final_to_cas.sas, skipped_missing_upstream, 31 최종 시각화 미완료);
  %end;
  %else %if &sl_run_cas. ne 1 %then %do;
    %sl_skip_step(17, 32_cas_final, 32_publish_final_to_cas.sas, skipped_disabled_by_option, %nrstr(sl_run_cas=0 (CAS 배포 비활성화)));
  %end;
  %else %do;
    %sl_run_cas_32(17);
  %end;

  /* -------------------------------------------------------------------------
     최종 요약 집계 및 마스터 로그 완결
     ------------------------------------------------------------------------- */
  %sl_print_summary;
%mend sl_run_all;

/* 마스터 파이프라인 자동 실행 시작 */
%sl_run_all;
