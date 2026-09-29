/*---------------------------------------------------------------------------
  ScamLens 01 — SAS Viya 적재와 데이터 감사

  전제
    - Python 파이프라인이 비식별화·URL 비활성화·분할까지 끝낸 CSV를 읽는다.
      생성 명령: PYTHONPATH=src python3 scripts/export_for_sas.py
    - Viya 세션 인코딩은 UTF-8이어야 한다. 한글이 깨지면 먼저 이것부터 확인한다.
    - 한글은 UTF-8에서 글자당 3바이트다. 문자 단위 처리에는 반드시 K 함수
      (KSUBSTR, KLENGTH, KINDEX, KSCAN)를 쓴다. SUBSTR은 글자를 쪼개 깨뜨린다.

  이 프로그램은 모델을 만들지 않는다. Python이 찾은 URL·라벨 상관을 SAS에서
  독립적으로 재현하고 통계적 유의성과 신뢰구간을 붙이는 것이 목적이다.
---------------------------------------------------------------------------*/

%let projroot = /home/student/github;       /* SAS 서버 기본 프로젝트 경로 */
%let sasdata  = &projroot./data/processed/sas;
%let sas_oof_ready = 0;
%let sas_meta_fit_completed = 0;

/* 세션 인코딩을 먼저 확인한다. UTF-8이 아니면 이후 모든 한글이 깨지므로
   여기서 멈추는 편이 낫다. 로그에서 ENCODING 값을 눈으로 확인한다. */
proc options option=encoding value; run;

%macro assert_utf8;
    %local enc;
    %let enc=%upcase(%sysfunc(getoption(encoding)));
    %if "&enc" ne "UTF8" and "&enc" ne "UTF-8" %then %do;
        %put ERROR: 세션 인코딩이 UTF-8이 아닙니다 (&enc).;
        %put ERROR- SAS Viya 세션을 UTF-8로 다시 시작한 뒤 실행하십시오.;
        %abort cancel;
    %end;
%mend;
%assert_utf8;


/*--- 1. 점수 테이블 적재 -------------------------------------------------*/
proc import datafile="&sasdata./sas_message_scores.csv"
            out=work.scores
            dbms=csv
            replace;
    guessingrows=max;
run;

/*--- 2. 텍스트 테이블 적재 -----------------------------------------------
  길이는 실측으로 정한다. 내보낸 CSV의 최대 본문은 5,547바이트이고 158행
  (0.94%)이 2,000바이트를 넘는다. $2000으로 읽으면 그 158행이 조용히 잘려
  나가는데, 잘린 쪽이 대체로 긴 대출 광고 템플릿이라 n-gram 분포가 함께
  왜곡된다. 여유를 둬 $8000으로 잡는다.

  DSD는 구분자를 쉼표로 바꾸므로 한글 사이 공백이 필드를 끊지 않는다.
  그래도 의도를 드러내기 위해 dlm을 명시한다.
-------------------------------------------------------------------------*/
data work.msgtext;
    infile "&sasdata./sas_message_text.csv"
           dsd dlm=',' firstobs=2 truncover encoding='utf-8' lrecl=32767;
    length message_id $40 split $12 label $12 text_normalized $8000;
    input message_id $ split $ label $ target has_url text_utf8_bytes text_normalized $;
run;

/* LENGTHM은 할당된 $8000의 크기를 반환하므로 본문 실측에 쓸 수 없다.
   LENGTHN은 뒤쪽 패딩을 제외한 실제 바이트 수다. Python의 원본 UTF-8 바이트
   수와 대조해 필드 잘림·인코딩 손상을 검출한다. */
proc sql;
    create table work.text_length_audit as
    select count(*)                       as rows,
           max(lengthn(text_normalized))  as max_bytes,
           max(klength(text_normalized))  as max_chars,
           sum(lengthn(text_normalized) >= 8000) as possibly_truncated,
           sum(missing(text_utf8_bytes) or
               lengthn(text_normalized) ne text_utf8_bytes) as byte_length_mismatches
    from work.msgtext;
quit;

title "본문 길이 감사 — possibly_truncated 가 0이어야 한다";
proc print data=work.text_length_audit noobs; run;

data _null_;
    set work.text_length_audit;
    if rows=0 or possibly_truncated > 0 or byte_length_mismatches > 0 then do;
        put "ERROR: SAS text import differs from the verified UTF-8 export. Stop and re-export.";
        abort cancel;
    end;
run;

title "OOF 적격성 — sas_meta_fit_eligible=0이면 02는 실행 불가";
proc freq data=work.scores;
    tables split*sas_meta_fit_eligible / missing nopercent;
run;

%macro summarize_oof_readiness;
    %local dsid rc index name schema_ready bad_rows train_rows;
    %let schema_ready=1;
    %let dsid=%sysfunc(open(work.scores));
    %do index=1 %to 5;
        %let name=%scan(text_probability_meta_input text_probability_oof
                        oof_fold_id sas_meta_fit_eligible similarity_group_id,&index.);
        %if %sysfunc(varnum(&dsid.,&name.))=0 %then %let schema_ready=0;
    %end;
    %let rc=%sysfunc(close(&dsid.));
    %if &schema_ready.=1 %then %do;
        proc sql noprint;
            select count(*) into :train_rows trimmed from work.scores where split='train';
            select count(*) into :bad_rows trimmed from work.scores
            where sas_meta_fit_eligible ne 1 or missing(text_probability_meta_input)
               or text_probability_meta_input<0 or text_probability_meta_input>1
               or (split='train' and (missing(text_probability_oof) or missing(oof_fold_id)
                   or text_probability_meta_input ne text_probability_oof));
        quit;
        %if &train_rows.>0 and &bad_rows.=0 %then %let sas_oof_ready=1;
    %end;
    %put NOTE: Verified OOF input readiness = &sas_oof_ready.;
%mend;
%summarize_oof_readiness;


/*--- 3. 분할·라벨 분포 ---------------------------------------------------*/
title "분할별 라벨 분포";
proc freq data=work.scores;
    tables split*label / nocol nopercent;
run;


/*--- 4. URL 유무와 라벨의 관계 (Python 분석의 SAS 재현) ------------------
  Python에서 train 기준 P(악성|URL 있음) 68.21% 대 P(악성|URL 없음) 3.86%를
  확인했다. 여기서는 카이제곱과 오즈비까지 붙여 상관이 우연이 아님을 보인다.
-------------------------------------------------------------------------*/
title "URL 유무 × 라벨 (train 분할)";
proc freq data=work.scores;
    where split = 'train';
    tables has_url*label / chisq relrisk nocol;
run;


/*--- 5. URL 유무별 정상 오탐률의 정확 신뢰구간 ---------------------------
  test 분할 정상 문자 1,665건이 대상이다. URL 없는 정상 1,367건에서 오탐은 0건,
  URL 포함 정상 298건에서 4건이다. 0건 구간은 점추정이 0%라 아무 정보를 주지
  않으므로 exact 이항 신뢰구간이 반드시 필요하다.

  임계값은 Python이 validation에서 고른 값과 같아야 한다. 바꾸지 않는다.
-------------------------------------------------------------------------*/
%let text_threshold = 0.515;

data work.normal_test;
    set work.scores;
    where split = 'test' and target = 0;
    length url_group $12;
    false_positive = (text_probability >= &text_threshold.);
    if has_url = 1 then url_group = 'URL 있음';
    else                url_group = 'URL 없음';
run;

/* BY 처리는 정렬을 요구한다. scores는 메시지 순서라 url_group이 뒤섞여 있어
   notsorted로는 같은 그룹이 여러 번 쪼개져 나온다. 반드시 먼저 정렬한다. */
proc sort data=work.normal_test; by url_group; run;

/* 오류가 0건인 그룹에도 오류=1 범주를 빈도 0으로 남긴다. 범주 자체가 없으면
   BINOMIAL(LEVEL='1')이 실패한다. WEIGHT / ZEROS는 분모를 늘리지 않는다. */
data work.normal_test_ci;
    set work.normal_test;
    by url_group;
    audit_weight=1;
    output;
    if last.url_group then do;
        audit_weight=0;
        false_positive=0; output;
        false_positive=1; output;
    end;
run;

title "정상 문자 오탐률과 exact 신뢰구간 (URL 유무별)";
proc freq data=work.normal_test_ci;
    by url_group;
    weight audit_weight / zeros;
    tables false_positive / binomial(level='1' cl=exact);
run;

/*--- 6. URL 유무별 악성 미탐률 -------------------------------------------
  URL 없는 악성은 54건뿐이라 점추정만 보면 안 된다.
-------------------------------------------------------------------------*/
data work.malicious_test;
    set work.scores;
    where split = 'test' and target = 1;
    length url_group $12;
    false_negative = (text_probability < &text_threshold.);
    if has_url = 1 then url_group = 'URL 있음';
    else                url_group = 'URL 없음';
run;

proc sort data=work.malicious_test; by url_group; run;

data work.malicious_test_ci;
    set work.malicious_test;
    by url_group;
    audit_weight=1;
    output;
    if last.url_group then do;
        audit_weight=0;
        false_negative=0; output;
        false_negative=1; output;
    end;
run;

title "악성 문자 미탐률과 exact 신뢰구간 (URL 유무별)";
proc freq data=work.malicious_test_ci;
    by url_group;
    weight audit_weight / zeros;
    tables false_negative / binomial(level='1' cl=exact);
run;

title;
