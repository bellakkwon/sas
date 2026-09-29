/*
  ScamLens 개인 SAS 실행기. 번들 내부 폴더를 /home/student/에 배치한다.
  outputs/를 준비하고 매 실행 전에 이전 결과를 날짜별로 보관한다.
  단계별 로그/HTML/상태를 남기지만, 실행 성공은 경고와 결과표 검수 후 판단한다.
*/
%let projroot = /home/student/github;
%let run_heavy_text_model = 0;
%let run_meta_model = 1;
/* %include는 run_step 내부에서 실행되므로 단계 간 공유 매크로를 전역으로 만든다. */
%global sas_oof_ready sas_meta_fit_completed text_threshold meta_threshold;
%let sas_oof_ready=0;
%let sas_meta_fit_completed=0;
%let text_threshold=;
%let meta_threshold=;

data work.scamlens_run_status;
    length stage $32 state $24;
    length syserr syscc 8;
    stop;
run;

%macro run_step(stage, program);
    %local step_syserr step_syscc;
    %let syscc=0;
    proc printto log="&projroot./outputs/&stage..log" new; run;
    %put NOTE: SCAMLENS_STAGE=&stage. SAS_VERSION=&sysvlong. DATE=&sysdate9. TIME=&systime.;
    proc options option=encoding; run;
    ods html path="&projroot./outputs" (url=none)
        file="&stage..html" style=HTMLBlue;
    %include "&projroot./sas/&program.";
    %let step_syserr=&syserr.;
    %let step_syscc=&syscc.;
    ods html close;
    proc printto; run;
    data work.scamlens_step_status;
        length stage $32 state $24;
        stage="&stage.";
        syserr=&step_syserr.;
        syscc=&step_syscc.;
        if syserr=0 and syscc=0 then state='completed_check_log';
        else state='requires_review';
    run;
    proc append base=work.scamlens_run_status data=work.scamlens_step_status; run;
%mend;

%macro skip_step(stage);
    data work.scamlens_step_status;
        length stage $32 state $24;
        stage="&stage.";
        state='skipped_not_completed';
        syserr=.; syscc=.;
    run;
    proc append base=work.scamlens_run_status data=work.scamlens_step_status; run;
%mend;

/* 07은 별도 외부 feature CSV를 읽는 독립 분석이다. */
%macro team_external;
    %if %sysfunc(fileexist(&projroot./data/processed/sas/sas_external_evaluation.csv)) %then %do;
        %run_step(07_composition, 07_composition_and_novelty.sas);
    %end;
    %else %do;
        %put WARNING: Restricted external input absent. Stage 07 is NOT completed.;
        %skip_step(07_composition);
    %end;
%mend;
%team_external;
%run_step(01_audit, 01_load_and_audit.sas);

%macro run_meta_if_ready;
    %if &run_meta_model.=1 and %symexist(sas_oof_ready) %then %do;
        %if &sas_oof_ready.=1 %then %do;
            %run_step(02_meta, 02_meta_classifier.sas);
        %end;
        %else %do;
            %put WARNING: 검증된 OOF가 없어 02 메타 회귀를 건너뜁니다.;
            %skip_step(02_meta);
        %end;
    %end;
    %else %do;
        %skip_step(02_meta);
    %end;
%mend;
%run_meta_if_ready;

%run_step(03_roc, 03_model_comparison.sas);
%run_step(06_transformer, 06_transformer_contrast.sas);
%run_step(05_visuals, 05_visuals.sas);

%macro run_optional_text;
    %if &run_heavy_text_model.=1 %then %do;
        %run_step(04_text, 04_korean_text_model.sas);
    %end;
    %else %do;
        %skip_step(04_text);
    %end;
%mend;
%run_optional_text;

proc export data=work.scamlens_run_status
    outfile="&projroot./outputs/analysis_run_status.csv" dbms=csv replace;
run;
proc print data=work.scamlens_run_status noobs; run;
%put NOTE: 출력 파일이 존재해도 로그 ERROR/WARNING 및 ODS 결과를 검수해야 합니다.;
