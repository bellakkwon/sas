/*---------------------------------------------------------------------------
  ScamLens 08 — 실패조건 게이트 (PROC LOGISTIC)

  Python `scripts/run_fage_20260911.py`가 만든 본문 없는 개발 행을 읽는다.
  원래 train의 fold 0 보정·결과 확인만 들어 있다. 원래 validation/test를
  넣지 않는다. 시드를 한 모형에 섞지 않는다.

  시드마다 게이트를 보정 행에서만 적합하고, 기존 선형 A/B/C와 단어·KcBERT는
  저장 확률에 같은 오탐 상한으로 임계값만 고른다.

    lr_a / lr_b / lr_c : 안정성 실험 저장 확률
    word / kcbert      : 이미 만든 전문가 확률
    stacking           : 전문가 확률 스태킹, 무가중
    fage               : 실패조건 게이트, 무가중
    fage_a             : 같은 실패조건 특징, A형 클래스 균형 WEIGHT
    fage_c             : 같은 실패조건 특징, C형 URL 없는 악성 상대 가중 2 WEIGHT

  임계값은 보정 전체 정상 오탐률 1% 이하에서 전체 악성 탐지를 최대화한다.
  동률이면 오탐이 적고 임계값이 높은 쪽. 후보는 0부터 1까지 0.001 격자와
  전원 음판(1.0001)이다. Python은 고유 점수를 쓰므로 임계값 숫자까지
  일치한다고 보지 않는다.

  무가중 FAGE는 그대로 두고, A형·C형 WEIGHT는 같은 보정 행에서 따로 적합한다.
  Python FAGE는 규제와 C형 표본 가중을 쓰므로 계수와 같아야 한다고 강제하지 않는다.
  Wald CI는 교차적합의 공유 모형 불확실성 전체를 반영하지 않는다.

  독립 실행. 01의 work.scores를 요구하지 않는다.
  선행: data/processed/sas/sas_fage_abc_rows.csv
---------------------------------------------------------------------------*/

%let projroot = /home/student/github;
%let sasdata  = &projroot./data/processed/sas;
%let fpr_ceiling = 0.01;
%let seed_list = 42 101 202 303 404;

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

/* PROC IMPORT는 role을 $21로 자를 수 있다. threshold_calibration은 22글자다.
   길이·인코딩을 고정한 DATA 단계로 읽는다. */
data work.fage;
    infile "&sasdata./sas_fage_abc_rows.csv"
           dsd dlm=',' firstobs=2 truncover encoding='utf-8' lrecl=32767;
    length message_id $40 role $32 similarity_group_id $40 label $12
           seed fold target has_url p_kcbert_missing p_url_missing 8
           p_lr_a p_lr_b p_lr_c p_word p_kcbert_filled p_url_filled
           similarity_to_train model_disagreement uncertainty 8;
    input message_id $ seed fold role $ similarity_group_id $ label $
          target has_url p_lr_a p_lr_b p_lr_c p_word p_kcbert_filled
          p_kcbert_missing p_url_filled p_url_missing similarity_to_train
          model_disagreement uncertainty;
run;

%macro assert_fage_input;
    %local rows unique_keys bad_rows cal_rows read_rows seeds min_role min_id;
    proc sql noprint;
        select count(*) into :rows trimmed from work.fage;
        select count(*) into :unique_keys trimmed
            from (select distinct seed, role, message_id from work.fage);
        select count(distinct seed) into :seeds trimmed from work.fage;
        select count(*) into :bad_rows trimmed from work.fage
            where missing(message_id) or missing(role) or missing(seed)
               or fold ne 0
               or target not in (0,1) or has_url not in (0,1)
               or role not in ('threshold_calibration', 'development_readout')
               or p_lr_a < 0 or p_lr_a > 1 or p_lr_b < 0 or p_lr_b > 1
               or p_lr_c < 0 or p_lr_c > 1
               or p_word < 0 or p_word > 1
               or p_kcbert_filled < 0 or p_kcbert_filled > 1
               or p_url_filled < 0 or p_url_filled > 1
               or similarity_to_train < 0 or similarity_to_train > 1
               or model_disagreement < 0 or model_disagreement > 1
               or uncertainty < 0 or uncertainty > 1
               or p_kcbert_missing not in (0,1) or p_url_missing not in (0,1)
               or (has_url=0 and p_url_filled ne 0);
        select count(*) into :cal_rows trimmed from work.fage
            where role='threshold_calibration';
        select count(*) into :read_rows trimmed from work.fage
            where role='development_readout';
        select min(lengthn(role)), min(lengthn(message_id))
            into :min_role trimmed, :min_id trimmed from work.fage;
    quit;
    %if &rows=0 or &rows ne &unique_keys or &bad_rows>0
        or &cal_rows=0 or &read_rows=0 or &seeds ne 5
        or &min_role < 19 or &min_id < 8 %then %do;
        %put ERROR: FAGE 입력 무결성 실패. 행=&rows. 키=&unique_keys. 불량=&bad_rows. 시드=&seeds.;
        %put ERROR- 역할 최소길이=&min_role. ID 최소길이=&min_id. 역할 변수 잘림을 의심하십시오.;
        %abort cancel;
    %end;
%mend;
%assert_fage_input;

data work.fage_thresholds;
    length seed 8 method $16 threshold 8 recall fpr 8;
    call missing(seed, method, threshold, recall, fpr);
    stop;
run;
data work.fage_readout_scored;
    length seed fold target has_url model_predicted 8
           method $16 message_id $40 role $32 similarity_group_id $40 label $12
           model_probability 8;
    call missing(seed, fold, target, has_url, model_predicted, method, message_id,
                 role, similarity_group_id, label, model_probability);
    stop;
run;

/* INTO로 만든 매크로 변수는 이 매크로의 지역 심볼 테이블에 들어가서
   호출 측에서 사라진다. 1행 데이터셋으로만 넘긴다. */
%macro pick_fpr_threshold(indata, scorevar, outds);
    %local qualifying;
    %let qualifying=0;
    data work.fage_grid;
        set &indata.;
        do threshold_index = 0 to 1000;
            threshold = threshold_index / 1000;
            predicted = (&scorevar. >= threshold);
            output;
        end;
        threshold = 1.0001;
        predicted = (&scorevar. >= threshold);
        output;
    run;
    proc sql noprint;
        create table work.fage_threshold_stats as
        select threshold,
               sum(case when target=1 and predicted=1 then 1 else 0 end) as tp,
               sum(case when target=0 and predicted=1 then 1 else 0 end) as fp,
               sum(case when target=1 and predicted=0 then 1 else 0 end) as fn,
               sum(case when target=0 and predicted=0 then 1 else 0 end) as tn
        from work.fage_grid
        group by threshold;
        select count(*) into :qualifying trimmed
        from work.fage_threshold_stats
        where (fp + tn) > 0 and fp / (fp + tn) <= &fpr_ceiling.;
    quit;
    %if %sysevalf(&qualifying = 0, boolean) %then %do;
        %put ERROR: 보정에서 정상 오탐률 &fpr_ceiling. 이하 임계값이 없습니다.;
        %abort cancel;
    %end;
    data work.fage_threshold_stats;
        set work.fage_threshold_stats;
        recall = tp / max(tp + fn, 1);
        fpr = fp / max(fp + tn, 1);
    run;
    proc sort data=work.fage_threshold_stats;
        by descending recall fpr descending threshold;
    run;
    data &outds;
        set work.fage_threshold_stats;
        where fpr <= &fpr_ceiling.;
        output;
        stop;
    run;
%mend;

%macro score_column(scorevar, method);
    %local t_col t_col_recall t_col_fpr;
    %pick_fpr_threshold(work.fage_cal, &scorevar, work.th_&method._&seed);
    data _null_;
        set work.th_&method._&seed;
        call symputx('t_col', threshold, 'l');
        call symputx('t_col_recall', recall, 'l');
        call symputx('t_col_fpr', fpr, 'l');
    run;
    data work.fage_th_row;
        length method $16;
        seed=&seed.; method="&method";
        threshold=&t_col.; recall=&t_col_recall.; fpr=&t_col_fpr.;
    run;
    proc append base=work.fage_thresholds data=work.fage_th_row force; run;
    data work.read_one;
        length method $16;
        set work.fage_read;
        method="&method";
        model_probability=&scorevar;
        model_predicted=(&scorevar >= &t_col.);
        keep seed fold role message_id similarity_group_id label target has_url
             method model_probability model_predicted;
    run;
    proc append base=work.fage_readout_scored data=work.read_one force; run;
    %put NOTE: seed=&seed. method=&method. threshold=&t_col.;
%mend;

%macro fit_weighted_fage(outname, weightvar);
    ods output ParameterEstimates=work.&outname._pe_&seed
               FitStatistics=work.&outname._fit_&seed
               ConvergenceStatus=work.&outname._cv_&seed;
    proc logistic data=work.fage_cal outmodel=work.&outname._model_&seed;
        weight &weightvar;
        model target(event='1') = p_lr_a p_lr_c p_word p_kcbert_filled p_url_filled
                                  p_url_missing has_url similarity_to_train
                                  model_disagreement uncertainty
              / clodds=wald;
    run;
    ods output close;
    data _null_;
        set work.&outname._cv_&seed;
        if status ne 0 then do;
            put "ERROR: &outname PROC LOGISTIC did not converge. seed=&seed.";
            abort cancel;
        end;
    run;
    proc logistic inmodel=work.&outname._model_&seed;
        score data=work.fage_cal out=work.&outname._cal_&seed(rename=(P_1=&outname._probability));
        score data=work.fage_read out=work.&outname._read_&seed(rename=(P_1=&outname._probability));
    run;
    %pick_fpr_threshold(work.&outname._cal_&seed, &outname._probability, work.th_&outname._&seed);
    data _null_;
        set work.th_&outname._&seed;
        call symputx('t_w', threshold, 'l');
        call symputx('t_w_recall', recall, 'l');
        call symputx('t_w_fpr', fpr, 'l');
    run;
    data work.fage_th_row;
        length method $16;
        seed=&seed.; method="&outname";
        threshold=&t_w.; recall=&t_w_recall.; fpr=&t_w_fpr.;
    run;
    proc append base=work.fage_thresholds data=work.fage_th_row force; run;
    data work.read_one;
        length method $16;
        set work.&outname._read_&seed;
        method="&outname";
        model_probability=&outname._probability;
        model_predicted=(&outname._probability >= &t_w.);
        keep seed fold role message_id similarity_group_id label target has_url
             method model_probability model_predicted;
    run;
    proc append base=work.fage_readout_scored data=work.read_one force; run;
    %put NOTE: seed=&seed. method=&outname. threshold=&t_w.;
%mend;

%macro fage_one_seed(seed);
    %local cal_n read_n cal_cls read_cls stack_t stack_t_recall stack_t_fpr
           fage_t fage_t_recall fage_t_fpr ncal n0 n1 csum0 csum1 t_w t_w_recall t_w_fpr;
    %let cal_n=0; %let read_n=0; %let cal_cls=0; %let read_cls=0;

    data work.fage_cal work.fage_read;
        set work.fage;
        if seed=&seed. then do;
            if role='threshold_calibration' then output work.fage_cal;
            else if role='development_readout' then output work.fage_read;
        end;
    run;

    proc sql noprint;
        select count(*) into :cal_n trimmed from work.fage_cal;
        select count(*) into :read_n trimmed from work.fage_read;
        select count(distinct target) into :cal_cls trimmed from work.fage_cal;
        select count(distinct target) into :read_cls trimmed from work.fage_read;
    quit;
    %if %sysevalf(&cal_n = 0, boolean) or %sysevalf(&read_n = 0, boolean)
        or %sysevalf(&cal_cls < 2, boolean) or %sysevalf(&read_cls < 2, boolean)
    %then %do;
        %put ERROR: seed &seed. 보정 또는 결과 확인 행이 비었거나 한 클래스만 있습니다.;
        %abort cancel;
    %end;

    /* p_kcbert_missing 은 fold 0에서 상수 0이라 모형에서 뺀다.
       Viya V.04는 OddsRatios ODS를 안 만들 수 있어 계수표만 남긴다. */
    title "FAGE 스태킹 seed=&seed. — 보정 행만";
    ods output ParameterEstimates=work.fage_stack_pe_&seed
               FitStatistics=work.fage_stack_fit_&seed
               ConvergenceStatus=work.fage_stack_cv_&seed;
    proc logistic data=work.fage_cal outmodel=work.fage_stack_model_&seed;
        model target(event='1') = p_lr_a p_lr_c p_word p_kcbert_filled p_url_filled
                                  p_url_missing
              / clodds=wald;
    run;
    ods output close;

    title "FAGE 실패조건 게이트 seed=&seed. — 보정 행만";
    ods output ParameterEstimates=work.fage_pe_&seed
               FitStatistics=work.fage_fit_&seed
               ConvergenceStatus=work.fage_cv_&seed;
    proc logistic data=work.fage_cal outmodel=work.fage_model_&seed;
        model target(event='1') = p_lr_a p_lr_c p_word p_kcbert_filled p_url_filled
                                  p_url_missing has_url similarity_to_train
                                  model_disagreement uncertainty
              / clodds=wald;
    run;
    ods output close;

    data _null_;
        set work.fage_stack_cv_&seed;
        if status ne 0 then do;
            put "ERROR: stacking PROC LOGISTIC did not converge. seed=&seed.";
            abort cancel;
        end;
    run;
    data _null_;
        set work.fage_cv_&seed;
        if status ne 0 then do;
            put "ERROR: FAGE PROC LOGISTIC did not converge. seed=&seed.";
            abort cancel;
        end;
    run;

    proc logistic inmodel=work.fage_stack_model_&seed;
        score data=work.fage_cal out=work.stack_cal_&seed(rename=(P_1=stacking_probability));
        score data=work.fage_read out=work.stack_read_&seed(rename=(P_1=stacking_probability));
    run;
    proc logistic inmodel=work.fage_model_&seed;
        score data=work.fage_cal out=work.fage_cal_&seed(rename=(P_1=fage_probability));
        score data=work.fage_read out=work.fage_read_&seed(rename=(P_1=fage_probability));
    run;

    %pick_fpr_threshold(work.stack_cal_&seed, stacking_probability, work.th_stack_&seed);
    data _null_;
        set work.th_stack_&seed;
        call symputx('stack_t', threshold, 'l');
        call symputx('stack_t_recall', recall, 'l');
        call symputx('stack_t_fpr', fpr, 'l');
    run;
    data work.fage_th_row;
        length method $16;
        seed=&seed.; method='stacking';
        threshold=&stack_t.; recall=&stack_t_recall.; fpr=&stack_t_fpr.;
    run;
    proc append base=work.fage_thresholds data=work.fage_th_row force; run;

    %pick_fpr_threshold(work.fage_cal_&seed, fage_probability, work.th_fage_&seed);
    data _null_;
        set work.th_fage_&seed;
        call symputx('fage_t', threshold, 'l');
        call symputx('fage_t_recall', recall, 'l');
        call symputx('fage_t_fpr', fpr, 'l');
    run;
    data work.fage_th_row;
        length method $16;
        seed=&seed.; method='fage';
        threshold=&fage_t.; recall=&fage_t_recall.; fpr=&fage_t_fpr.;
    run;
    proc append base=work.fage_thresholds data=work.fage_th_row force; run;

    %put NOTE: seed=&seed. stacking_threshold=&stack_t. fage_threshold=&fage_t.;

    proc sql noprint;
        select count(*) into :ncal trimmed from work.fage_cal;
        select sum(target=0), sum(target=1)
            into :n0 trimmed, :n1 trimmed from work.fage_cal;
    quit;
    data work.fage_cal;
        set work.fage_cal;
        w_a = (target=0)*(&ncal/2/&n0) + (target=1)*(&ncal/2/&n1);
        raw_c = 1;
        if target=1 and has_url=0 then raw_c=2;
    run;
    proc sql noprint;
        select sum(raw_c*(target=0)), sum(raw_c*(target=1))
            into :csum0 trimmed, :csum1 trimmed from work.fage_cal;
    quit;
    data work.fage_cal;
        set work.fage_cal;
        w_c = raw_c * ((target=0)*(&ncal/2/&csum0) + (target=1)*(&ncal/2/&csum1));
    run;

    title "FAGE A형 균형 가중 seed=&seed. — 보정 행만";
    %fit_weighted_fage(fage_a, w_a);
    title "FAGE C형 URL 없는 악성 가중 seed=&seed. — 보정 행만";
    %fit_weighted_fage(fage_c, w_c);

    %score_column(p_lr_a, lr_a);
    %score_column(p_lr_b, lr_b);
    %score_column(p_lr_c, lr_c);
    %score_column(p_word, word);
    %score_column(p_kcbert_filled, kcbert);

    data work.read_scored;
        length method $16;
        set work.stack_read_&seed(in=in_stack) work.fage_read_&seed(in=in_fage);
        if in_stack then do;
            method='stacking';
            model_probability=stacking_probability;
            model_predicted=(stacking_probability >= &stack_t.);
        end;
        else do;
            method='fage';
            model_probability=fage_probability;
            model_predicted=(fage_probability >= &fage_t.);
        end;
        keep seed fold role message_id similarity_group_id label target has_url
             method model_probability model_predicted;
    run;
    proc append base=work.fage_readout_scored data=work.read_scored force; run;

    title "seed=&seed. 결과 확인 혼동행렬 — 스태킹";
    proc freq data=work.read_scored;
        where method='stacking';
        tables target*model_predicted / nocol norow nopercent;
    run;
    title "seed=&seed. 결과 확인 혼동행렬 — FAGE";
    proc freq data=work.read_scored;
        where method='fage';
        tables target*model_predicted / nocol norow nopercent;
    run;
    title "seed=&seed. URL 유무별 결과 확인 — FAGE";
    proc freq data=work.read_scored;
        where method='fage';
        tables has_url*target*model_predicted / nocol norow nopercent;
    run;
%mend;

%macro fage_all_seeds;
    %local i seed;
    %do i=1 %to 5;
        %let seed=%scan(&seed_list., &i);
        %fage_one_seed(&seed);
    %end;
%mend;
%fage_all_seeds;

title "시드별 보정에서 고른 임계값 — A/B/C와 게이트, 시드를 합치지 않음";
proc print data=work.fage_thresholds noobs; run;

title "결과 확인 URL 없는 악성 — 시드·방법별";
proc sql;
    create table work.fage_readout_nourl as
    select seed, method,
           sum(target=1) as malicious_rows,
           sum(target=1 and model_predicted=1) as tp,
           sum(target=1 and model_predicted=0) as fn
    from work.fage_readout_scored
    where has_url=0
    group by seed, method;
quit;
proc print data=work.fage_readout_nourl noobs; run;

title "결과 확인 전체 정상 오탐 — 시드·방법별";
proc sql;
    create table work.fage_readout_fpr as
    select seed, method,
           sum(target=0) as normal_rows,
           sum(target=0 and model_predicted=1) as fp,
           sum(target=0 and model_predicted=0) as tn
    from work.fage_readout_scored
    group by seed, method;
quit;
proc print data=work.fage_readout_fpr noobs; run;

data _null_;
    rc = dcreate('outputs', "&projroot.");
run;

proc export data=work.fage_thresholds
    outfile="&projroot./outputs/fage_thresholds.csv" dbms=csv replace;
run;
proc export data=work.fage_readout_nourl
    outfile="&projroot./outputs/fage_readout_nourl.csv" dbms=csv replace;
run;
proc export data=work.fage_readout_fpr
    outfile="&projroot./outputs/fage_readout_fpr.csv" dbms=csv replace;
run;
proc export data=work.fage_readout_scored
    outfile="&projroot./outputs/fage_readout_scored.csv" dbms=csv replace;
run;

%put NOTE: Python FAGE 수치가 SAS 08 결과를 대신하지 않습니다. 로그와 ODS를 검수하십시오.;
title;
