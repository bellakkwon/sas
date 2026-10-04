# 10-04 추가학습 CSV의 선택 SAS 확인

기본 실행은 루트 sas/00_RUN_ALL.sas다. 아래는 최신 CSV를 WORK로 읽는 문서용 예시다. 별도 활성 SAS 프로그램을 추가하지 않았다. SAS Studio에서 projroot를 본인 서버 경로로 지정한 뒤 코드를 제출한다.

```sas
%let projroot=/home/student/github;
/* Optional static example. Not part of sas/00_RUN_ALL.sas; no training. */
%macro sl_read_adaptation;
  %if not %symexist(projroot) %then %do;
    %put ERROR: Set projroot to the SAS server checkout first.;
    %return;
  %end;
  %let adaptation_csv=&projroot./materials/20261004_team_v1/data/derived/few_example.csv;
  %if not %sysfunc(fileexist(&adaptation_csv.)) %then %do;
    %put ERROR: Missing shared aggregate CSV.;
    %return;
  %end;
  proc import datafile="&adaptation_csv." out=work.sl_adaptation dbms=csv replace;
    getnames=yes; guessingrows=max;
  run;
  %if &syserr. > 4 %then %do;
    %put ERROR: Import failed. Do not interpret incomplete output.;
    %return;
  %end;
  proc contents data=work.sl_adaptation; run;
  proc freq data=work.sl_adaptation;
    tables learned_examples*updates / missing;
  run;
  proc print data=work.sl_adaptation(obs=20); run;
%mend;
%sl_read_adaptation;
```

반입 뒤 character/numeric 타입과 모델 ID 잘림, 행 수, Python CSV와 집계 일치를 확인한다. 반복 조건의 행 수를 고유 문자 수로 읽지 않는다. 이번 공유에서는 실제 SAS Studio/CAS 실행을 하지 않았으며 PROC IMPORT의 타입 추정 결과는 서버에서 확인해야 한다. 기존 RUN_ALL/CAS 설정과 이전 결과는 바꾸지 않는다.
