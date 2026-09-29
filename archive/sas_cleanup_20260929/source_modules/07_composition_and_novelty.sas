/*---------------------------------------------------------------------------
  ScamLens 07 — 고정 탐지기의 외부 평가 결과: 연도 · 유형 · 유사도 진단

  이미 관찰한 자료에 대한 탐색이다. 분류기 재학습·임계값 선택에 사용하지 않는다.
  전기간 중복 제거 후 최초 관측 연도에 남긴 사례이므로 실제 연도별 문자 트래픽,
  전향적 시간 홀드아웃, 시간의 인과 효과로 해석하지 않는다.
  주 분석은 범주형 연도다. 연속 연도는 가정·적합성을 확인하는 별도 민감도 분석으로
  검토할 수 있다. 유사도의 비단조성만으로 연속 연도를 금지하지 않는다.
  비유의성은 효과 부재·유형별 추이 동일성·상쇄 부재의 증거가 아니다.

  Python 대조: scripts/evaluate_failure_decomposition.py 와 같은 입력·표본·기준범주·
  무규제 최대우도 모형. reports/generated/failure_decomposition.json/.md 와 실제
  ODS 출력을 비교한다. 수기 기대값이나 모형 채택 결론을 코드에 넣지 않는다.
  독립 실행. 입력은 본문 없는 sas_external_evaluation.csv.

  SAS/STAT 13.2 이상 joint effects ODS 이름은 ModelANOVA다. 구버전에서는 ODS TRACE로
  이름을 확인해 joint_table을 Type3으로 바꾼다. joint Wald와 LR의 p값은 다른 검정이다.
  ODS: support.sas.com/documentation/cdl/en/statug/67523/HTML/default/statug_logistic_details97.htm
  수렴: support.sas.com/kb/51/437.html
---------------------------------------------------------------------------*/

%let projroot = /home/student/github;
%let sasdata = &projroot./data/processed/sas;
%let joint_table = ModelANOVA;
%let rare_min_rows = 30;

proc options option=encoding value; run;
%macro assert_utf8;
    %local enc;
    %let enc=%upcase(%sysfunc(getoption(encoding)));
    %if "&enc" ne "UTF8" and "&enc" ne "UTF-8" %then %do;
        %put ERROR: 세션 인코딩이 UTF-8이 아닙니다 (&enc).;
        %abort cancel;
    %end;
%mend;
%assert_utf8;

/* 1. 모형별 결측 제거로 비교 표본이 달라지는 것을 허용하지 않는다. */
proc import datafile="&sasdata./sas_external_evaluation.csv"
            out=work.external dbms=csv replace;
    guessingrows=max;
run;
%macro assert_input;
    %local invalid rows unique_ids reference_rows;
    proc sql noprint;
        select count(*), count(distinct message_id)
            into :rows trimmed, :unique_ids trimmed from work.external;
        select count(*) into :invalid trimmed from work.external
        where missing(message_id) or missing(collection_year)
          or collection_year ne int(collection_year) or missing(attack_type_code)
          or detected not in (0,1) or year_has_enough_rows not in (0,1)
          or missing(similarity_to_train) or similarity_to_train < 0
          or similarity_to_train > 1;
        select count(*) into :reference_rows trimmed from work.external
        where year_has_enough_rows=1 and collection_year=2022
          and attack_type_code in ('delivery','public_agency');
    quit;
    %if &rows=0 or &invalid>0 or &rows ne &unique_ids or &reference_rows=0 %then %do;
        %put ERROR: 입력 무결성 실패. 결측 또는 중복 또는 기준연도 부재를 확인하십시오.;
        %abort cancel;
    %end;
%mend;
%assert_input;

data work.ext work.excluded_small_year;
    set work.external;
    if year_has_enough_rows=1 then output work.ext;
    else output work.excluded_small_year;
run;
data work.dominant work.excluded_non_dominant;
    set work.ext;
    if attack_type_code in ('delivery','public_agency') then output work.dominant;
    else output work.excluded_non_dominant;
run;

/* 포함 비율뿐 아니라 제외된 행에 집중된 미탐도 공개한다. */
data work.flow_rows;
    length stage $28;
    set work.external;
    stage='input'; output;
    if year_has_enough_rows ne 1 then do;
        stage='excluded_small_year'; output;
    end;
    else do;
        stage='eligible'; output;
        if attack_type_code in ('delivery','public_agency') then stage='dominant';
        else stage='excluded_non_dominant';
        output;
    end;
run;
proc sql;
    create table work.sample_flow as
    select stage, count(*) as rows, sum(1-detected) as misses
    from work.flow_rows group by stage;
    create table work.sample_flow_year as
    select stage, collection_year, count(*) as rows, sum(1-detected) as misses
    from work.flow_rows group by stage, collection_year;
    create table work.cell_counts as
    select collection_year, attack_type_code, count(*) as rows,
           sum(detected) as detections, sum(1-detected) as misses
    from work.dominant group by collection_year, attack_type_code;
quit;
title '표본 흐름 — 포함 및 제외된 행과 미탐';
proc print data=work.sample_flow noobs; run;
proc print data=work.sample_flow_year noobs; run;
title '모형 진단 — 연도 × 유형 칸별 표본과 미탐';
proc print data=work.cell_counts noobs; run;
title '관측 — 연도별·유형별 탐지율';
proc freq data=work.dominant;
    tables collection_year*detected attack_type_code*collection_year*detected / nocol nocum;
run;
title '관측 — 연도별 유사도';
proc means data=work.dominant n mean median min max maxdec=4;
    class collection_year; var similarity_to_train;
run;

/* 2. 적합 및 수렴 상태. 부적절한 적합의 LR은 생성하지 않는다.
   ParameterEstimates에서 Wald OR를 생성한다. 교호작용 계수의 exp(beta)는
   조건부 OR 또는 OR의 비이며 유형 전체의 무조건 OR가 아니다.
   LOG의 complete/quasi-complete separation·Hessian 경고도 확인한다. */
%macro fit(tag=, data=dominant, class=, terms=, predict=0);
    %global ok_&tag;
    %let ok_&tag=0;
    /* 같은 세션 재실행 실패 시 이전 ODS 결과를 새 결과로 읽지 않는다. */
    proc datasets library=work nolist nowarn;
        delete est_&tag fit_&tag conv_&tag joint_&tag or_&tag nobs_&tag;
    quit;
    proc logistic data=work.&data;
        %if %length(%superq(class)) %then %do;
            class &class / param=ref;
        %end;
        model detected(event='1') = &terms / clodds=wald maxiter=200;
        ods output ParameterEstimates=work.est_&tag
                   FitStatistics=work.fit_&tag
                   ConvergenceStatus=work.conv_&tag
                   NObs=work.nobs_&tag;
        %if %length(%superq(class)) %then %do;
            ods output &joint_table=work.joint_&tag;
        %end;
        %if &predict %then %do;
            effectplot slicefit(x=similarity_to_train sliceby=attack_type_code) / clm;
            output out=work.pred_inter predicted=phat;
        %end;
    run;
    ods output close;
    %if %sysfunc(exist(work.conv_&tag)) and %sysfunc(exist(work.est_&tag)) %then %do;
        %local invalid_conv invalid_est n_conv n_est;
        proc sql noprint;
            select count(*) into :n_conv trimmed from work.conv_&tag;
            select count(*) into :n_est trimmed from work.est_&tag;
            select count(*) into :invalid_conv trimmed from work.conv_&tag
            where missing(Status) or Status ne 0;
            select count(*) into :invalid_est trimmed from work.est_&tag
            where missing(Estimate) or missing(StdErr) or DF ne 1;
        quit;
        %if &n_conv>0 and &n_est>0 and &invalid_conv=0 and &invalid_est=0 %then %let ok_&tag=1;
        data work.or_&tag;
            set work.est_&tag;
            odds_ratio=exp(Estimate);
            or_ci_low=exp(Estimate-probit(0.975)*StdErr);
            or_ci_high=exp(Estimate+probit(0.975)*StdErr);
            inference_valid=&&ok_&tag;
        run;
        title "적합 상태 — &tag";
        proc print data=work.conv_&tag noobs; run;
        title "계수·Wald OR 및 95% CI — &tag";
        proc print data=work.or_&tag noobs; run;
    %end;
    %if &&ok_&tag ne 1 %then %put WARNING: &tag 적합 검토 필요. 관련 LR 검정을 보류합니다.;
%mend;

/* 같은 행과 반응값의 사전 명시 중첩 모형끼리만 호출한다.
   추정 모수 수에서 df를 계산해 연도 개수를 상수로 가정하지 않는다. */
%macro lr(reduced=, full=, out=);
    proc datasets library=work nolist nowarn; delete &out; quit;
    %if &&ok_&reduced=1 and &&ok_&full=1 %then %do;
        %local p_small p_large;
        proc sql noprint;
            select sum(DF) into :p_small trimmed from work.est_&reduced;
            select sum(DF) into :p_large trimmed from work.est_&full;
        quit;
        data work.&out;
            merge work.fit_&reduced(where=(Criterion='-2 Log L')
                       rename=(InterceptAndCovariates=reduced_m2ll))
                  work.fit_&full(where=(Criterion='-2 Log L')
                       rename=(InterceptAndCovariates=full_m2ll));
            length comparison $80 analysis_status $32;
            comparison="&reduced -> &full";
            analysis_status='exploratory';
            lr_statistic=reduced_m2ll-full_m2ll;
            df=&p_large-&p_small;
            if df>0 and not missing(lr_statistic) and lr_statistic>=-1e-7 then do;
                lr_statistic=max(0,lr_statistic);
                p_value=sdf('CHISQUARE',lr_statistic,df);
            end;
            else do;
                analysis_status='invalid_likelihood_or_df';
                p_value=.;
            end;
        run;
        title "탐색적 우도비 검정 — &reduced -> &full";
        proc print data=work.&out noobs;
            var comparison reduced_m2ll full_m2ll lr_statistic df p_value analysis_status;
        run;
    %end;
    %else %put WARNING: &out 보류. 관련 모형 수렴 및 분리를 먼저 확인하십시오.;
%mend;

/* 3. Sep 5의 가법모형·연도 × 유형 점검을 보존한다. AIC/p값은 적합 진단이며
   이 표본으로 분류기나 정책을 선택하지 않는다. 비유의성으로 상쇄 부재를 증명하지 않는다. */
title '연도만';
%fit(tag=year, class=collection_year(ref='2022'), terms=collection_year);
title '유사도만';
%fit(tag=sim, terms=similarity_to_train);
title '유형만';
%fit(tag=type, class=attack_type_code(ref='delivery'), terms=attack_type_code);
title '유사도 + 유형';
%fit(tag=main, class=attack_type_code(ref='delivery'), terms=similarity_to_train attack_type_code);
title '유사도 + 유형 + 범주형 연도';
%fit(tag=full, class=collection_year(ref='2022') attack_type_code(ref='delivery'),
     terms=similarity_to_train attack_type_code collection_year);
title '추가 탐색 — 유사도 + 유형 × 연도';
%fit(tag=year_type, class=collection_year(ref='2022') attack_type_code(ref='delivery'),
     terms=similarity_to_train attack_type_code|collection_year);
%lr(reduced=full, full=year_type, out=lr_year_type);
%lr(reduced=main, full=full, out=lr_year_additive);

/* 4. 같은 작은 모형에서 연도 전체를 검정한다. 연도 보정 전후 교호작용도 병기한다. */
ods graphics on / width=9in height=5in;
title '유사도 × 유형 — 연도 미보정 예측 곡선';
%fit(tag=inter, class=attack_type_code(ref='delivery'),
     terms=similarity_to_train|attack_type_code, predict=1);
title '유사도 × 유형 + 범주형 연도';
%fit(tag=inter_year, class=collection_year(ref='2022') attack_type_code(ref='delivery'),
     terms=similarity_to_train|attack_type_code collection_year);
%lr(reduced=main, full=inter, out=lr_interaction);
%lr(reduced=inter, full=inter_year, out=lr_joint_year);
%lr(reduced=full, full=inter_year, out=lr_interaction_adjusted_year);
title '범주형 연도 joint Wald 검정 — 교호작용 포함 모형';
%macro show_joint;
    %if %sysfunc(exist(work.joint_inter_year)) %then %do;
        proc print data=work.joint_inter_year noobs; run;
    %end;
    %else %put WARNING: joint ODS 미생성. ODS TRACE로 joint_table 설정을 확인하십시오.;
%mend;
%show_joint;

/* 5. 고정 구간의 관측과 모형 적합값. 첫 구간은 0을 포함한다.
   같은 자료의 예측·관측 비교는 적합 진단이며 독립 검증이 아니다. */
data work.binned;
    set work.dominant;
    length novelty_bin $16;
    if similarity_to_train<=0.3 then do; novelty_bin='[0.0, 0.3]'; bin_order=1; end;
    else if similarity_to_train<=0.5 then do; novelty_bin='(0.3, 0.5]'; bin_order=2; end;
    else if similarity_to_train<=0.7 then do; novelty_bin='(0.5, 0.7]'; bin_order=3; end;
    else do; novelty_bin='(0.7, 1.0]'; bin_order=4; end;
run;
proc sql;
    create table work.stratified as
    select bin_order, novelty_bin, attack_type_code, count(*) as rows,
           sum(detected) as detections, mean(detected) as detection_rate
    from work.binned group by bin_order, novelty_bin, attack_type_code;
quit;
/* Python과 같은 z=1.96 Wilson. 비율 0 또는 1에서도 유효한 경계를 낸다. */
data work.stratified_ci;
    set work.stratified;
    z=1.96;
    denom=1+z*z/rows;
    centre=(detection_rate+z*z/(2*rows))/denom;
    spread=z*sqrt(detection_rate*(1-detection_rate)/rows+z*z/(4*rows*rows))/denom;
    ci_low=max(0,centre-spread);
    ci_high=min(1,centre+spread);
    misses=rows-detections;
run;
title '유사도 구간 × 유형 — 표본·미탐·Wilson 95% CI';
proc print data=work.stratified_ci noobs;
    var novelty_bin attack_type_code rows misses detection_rate ci_low ci_high;
run;
title '관측 탐지율과 불확실성';
proc sgplot data=work.stratified_ci;
    scatter x=bin_order y=detection_rate / group=attack_type_code
        yerrorlower=ci_low yerrorupper=ci_high markerattrs=(symbol=circlefilled);
    series x=bin_order y=detection_rate / group=attack_type_code;
    yaxis label='탐지율' min=0 max=1 valuesformat=percent8.0;
    xaxis label='학습셋 유사도 구간' values=(1 2 3 4)
        valuesdisplay=('[0,0.3]' '(0.3,0.5]' '(0.5,0.7]' '(0.7,1]');
run;
%macro observed_fitted;
    %if &ok_inter=1 and %sysfunc(exist(work.pred_inter)) %then %do;
        data work.pred_binned;
            set work.pred_inter;
            if similarity_to_train<=0.3 then bin_order=1;
            else if similarity_to_train<=0.5 then bin_order=2;
            else if similarity_to_train<=0.7 then bin_order=3;
            else bin_order=4;
        run;
        title '탐색 적합 진단 — 같은 자료의 관측률과 예측 평균';
        proc means data=work.pred_binned n mean maxdec=4;
            class bin_order attack_type_code; var detected phat;
        run;
    %end;
%mend;
%observed_fitted;

/* 6. Python과 동일: eligible 표본에서 원래 유형이 30건 이상이면 유지.
   빈도 미만만 rare로 묶는다. other도 빈도 기준으로 보존된다. */
proc sql;
    create table work.type_counts as
    select attack_type_code, count(*) as type_rows
    from work.ext group by attack_type_code;
    create table work.with_rare as
    select a.*, b.type_rows,
           case when b.type_rows>=&rare_min_rows then a.attack_type_code
                else 'rare' end as atype length=64
    from work.ext as a left join work.type_counts as b
    on a.attack_type_code=b.attack_type_code;
quit;
title '민감도 표본 — 원래 유형 빈도와 묶음';
proc freq data=work.with_rare;
    tables attack_type_code*atype / list missing;
run;
title '민감도 — 전체 적격 표본; 빈도 기준 소수 유형 묶음';
%fit(tag=rare, data=with_rare, class=collection_year(ref='2022') atype(ref='delivery'),
     terms=similarity_to_train atype collection_year);

title;
%put NOTE: 07 끝. 출력 생성은 통계 해석 또는 SAS 실행 검수 완료를 뜻하지 않습니다.;
%put NOTE: 표본흐름·입력 해시·수렴·분리 경고·계수·OR CI·LR을 Python 산출물과 대조하십시오.;
%put NOTE: p값 비유의성은 효과 부재나 인과 결론이 아닙니다. 미탐 수와 제외 표본을 함께 제시하십시오.;
