/* Set %let projroot=/home/student/github; then include this file.
   Creates a new self-contained HTML report. CAS is not started here. */
%global projroot sv_runid sv_outdir;
%macro sv_entry;
  %if %length(%superq(projroot))=0 %then %let projroot=/home/student/github;
  %include "&projroot./visualization_20260921_v1/sas/10_LOAD_FINAL_AGGREGATES.sas";
  %if &sv_loaded ne 1 %then %abort cancel;
  %let sv_runid=run_%sysfunc(uuidgen());
  %let sv_outdir=&sv_root./outputs/&sv_runid;
  data _null_;
    length parent created $2048;
    parent=symget('sv_root');
    if not fileexist(cats(parent,'/outputs')) then created=dcreate('outputs',parent);
    if not fileexist(cats(parent,'/outputs')) then do;
      put 'ERROR: Cannot create outputs directory'; abort cancel;
    end;
    if fileexist(symget('sv_outdir')) then do;
      put 'ERROR: Refusing existing run directory'; abort cancel;
    end;
    created=dcreate(symget('sv_runid'),cats(parent,'/outputs'));
    if not fileexist(symget('sv_outdir')) then do;
      put 'ERROR: Cannot create unique run directory'; abort cancel;
    end;
  run;
  %sv_check(create_run_directory)
  ods _all_ close;
  ods graphics on / reset=all width=9in height=5in imagefmt=png;
  ods html5(id=svfinal) path="&sv_outdir" (url=none) gpath="&sv_outdir"
    file='final_visualization.html' style=HTMLBlue options(bitmap_mode='inline');
  title 'ScamLens: 고정 모델 평가와 오류 진단';
  footnote '기존 시험 재사용 / 외부 양성 표본 / 개발 정상 후보를 별도로 해석합니다.';
  ods text='U5: 과거 평가 이력이 있는 동일 문자들을 다섯 시드에서 평가했습니다. 시드 간 차이는 새 독립 표본의 불확실성이 아닙니다.';
  proc means data=work.sv_models noprint nway vardef=n;
    class arm; var fp fn recall fpr;
    output out=work.sv_arm_summary mean=mean_fp mean_fn mean_recall mean_fpr
      std=sd_fp sd_fn sd_recall sd_fpr;
  run;
  %sv_check(arm_summary)
  proc print data=work.sv_arm_summary noobs label;
    var arm mean_fp mean_fn mean_recall mean_fpr sd_fp sd_fn;
    format mean_recall mean_fpr percent8.2 mean_fp mean_fn sd_fp sd_fn 8.2;
    label mean_fp='평균 오탐' mean_fn='평균 미탐' mean_recall='평균 재현율'
      mean_fpr='평균 오탐률' sd_fp='오탐 시드 표준편차' sd_fn='미탐 시드 표준편차';
    title2 'U5 모델 비교: 평균과 시드 변동 (모표준편차)';
  run;
  %sv_check(arm_summary_report)
  proc sgplot data=work.sv_models;
    title2 'U5 오탐 건수: 점 하나가 한 시드';
    scatter x=arm y=fp / jitter markerattrs=(symbol=CircleFilled size=10 color=CX254F6D);
    yaxis min=0 grid label='오탐 건수'; xaxis label='실험 조건';
  run;
  %sv_check(u5_fp_chart)
  proc sgplot data=work.sv_models;
    title2 'U5 미탐 건수: 점 하나가 한 시드';
    scatter x=arm y=fn / jitter markerattrs=(symbol=CircleFilled size=10 color=CX254F6D);
    yaxis min=0 grid label='미탐 건수'; xaxis label='실험 조건';
  run;
  %sv_check(u5_fn_chart)
  proc sgplot data=work.sv_features(where=(feature_category='has_url'));
    title2 'DUP: URL 유무별 정상 문자 오탐률';
    vbarparm category=feature_value response=dup_fpr / datalabel fillattrs=(color=CX254F6D);
    format dup_fpr percent8.2;
    yaxis min=0 grid label='오탐률'; xaxis label='URL 표시 (0=없음, 1=있음)';
  run;
  %sv_check(url_chart)
  proc print data=work.sv_features(where=(feature_category='has_url')) noobs;
    var feature_value n_normal dup_avg_fp dup_fpr; format dup_fpr percent8.2;
  run;
  %sv_check(url_denominators)
  proc sgplot data=work.sv_truncation(where=(arm='DUP'));
    title2 'DUP: 입력 절단 여부별 스미싱 미탐률 (연관성 진단)';
    vbarparm category=is_truncated response=fnr / datalabel fillattrs=(color=CXAE693A);
    format fnr percent8.2;
    yaxis min=0 grid label='미탐률'; xaxis label='128 토큰 절단 (0=없음, 1=있음)';
  run;
  %sv_check(truncation_chart)
  proc print data=work.sv_truncation(where=(arm='DUP')) noobs;
    var is_truncated n_smishing mean_fn fnr; format fnr percent8.2;
  run;
  %sv_check(truncation_denominators)
  ods text='외부 진단: 대표 표본은 고유 표본의 부분집합입니다. 두 집단을 합산하지 않습니다. 아래 조건 비교는 시드 42의 사후 진단이며 임계값을 다시 선택하지 않았습니다.';
  proc sgplot data=work.sv_kisa(where=(seed=42 and cohort='kisa_unique'));
    title2 'KISA 고유 스미싱: 조건별 재현율 (양성만 포함)';
    hbarparm category=condition response=recall / datalabel fillattrs=(color=CX254F6D);
    format recall percent8.2; xaxis min=0 max=1 grid label='재현율'; yaxis label='입력 조건';
  run;
  %sv_check(kisa_unique_chart)
  proc sgplot data=work.sv_kisa(where=(seed=42 and cohort='kisa_representatives'));
    title2 'KISA 대표 표본: 조건별 재현율 (고유 표본의 부분집합)';
    hbarparm category=condition response=recall / datalabel fillattrs=(color=CX427B76);
    format recall percent8.2; xaxis min=0 max=1 grid label='재현율'; yaxis label='입력 조건';
  run;
  %sv_check(kisa_representatives_chart)
  proc sgplot data=work.sv_kisa(where=(seed=42 and cohort='normal_candidates'));
    title2 '기존 정상 후보: 조건별 오탐 건수 (개발용 회귀 검사)';
    hbarparm category=condition response=fp / datalabel fillattrs=(color=CXAE693A);
    xaxis min=0 grid label='오탐 건수'; yaxis label='입력 조건';
  run;
  %sv_check(normal_candidates_chart)
  proc print data=work.sv_kisa(where=(seed=42)) noobs;
    var cohort condition n tp fn fp recall fpr; format recall fpr percent8.2;
    title2 '조건별 건수와 분모: 서로 다른 평가 역할을 합산하지 않습니다';
  run;
  %sv_check(kisa_table)
  ods text='JEV 대체 비교는 오류를 과대표집한 선택 표본입니다. 결합 탐색은 기존 validation 재사용입니다. 아래 두 표를 서로 다른 평가로 해석합니다.';
  proc print data=work.sv_jev(where=(seed=42 and cohort='all')) noobs label;
    var seed n b_fp b_fn j_fp j_fn j_abstain_pos j_abstain_neg t_corrected_fp t_new_fn t_abstain_from_correct;
    title2 'JEV 판정 대체: 오탐 수정과 새 미탐·보류의 교환';
  run;
  %sv_check(jev_comparison_table)
  proc print data=work.sv_fusion(where=(role='readout')) noobs;
    var arm role n normal_denominator smishing_denominator fp fn recall fpr;
    format recall fpr percent8.2;
    title2 'JEV 결합 탐색: 추가 탐지 이득이 입증되지 않았습니다';
  run;
  %sv_check(fusion_table)
  ods html5(id=svfinal) close;
  %sv_check(close_report)
  %sv_nonempty(&sv_outdir./final_visualization.html)
  %local i ds;
  %do i=1 %to 6;
    %let ds=%scan(sv_models sv_features sv_truncation sv_kisa sv_jev sv_fusion,&i);
    proc export data=work.&ds outfile="&sv_outdir./readback_&ds..csv" dbms=csv replace;
    run;
    %sv_check(export_readback)
    %sv_nonempty(&sv_outdir./readback_&ds..csv)
  %end;
  data _null_;
    file "&sv_outdir./run_status.txt";
    put 'status=ok stage=studio_aggregate_report';
    put "run_id=&sv_runid";
    put 'cas_executed=no';
  run;
  %sv_check(write_status)
  %sv_nonempty(&sv_outdir./run_status.txt)
  title; footnote;
  %put NOTE: SCAMLENS_FINAL_STUDIO_COMPLETE;
  %put NOTE: REPORT=&sv_outdir./final_visualization.html;
%mend;
%sv_entry;
