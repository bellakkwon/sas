/* Pre-consensus nominal A/B agreement; final consensus is a separate stratum. */
%macro sc11_check;
  %if &syscc ne 0 or &syserr ne 0 %then %do;
    %put ERROR: SAS 11 stopped after an unsuccessful step.;
    %abort cancel;
  %end;
%mend;
%macro sc11_run;
  %global projroot sasdata runout sc11_complete;
  %local n u bad;
  %let sc11_complete=0;
  %if %length(%superq(projroot))=0 %then %let projroot=/home/student/github;
  %if %length(%superq(sasdata))=0 %then %let sasdata=&projroot./data/processed/sas;
  %if %length(%superq(runout))=0 %then %do;
    %put ERROR: Run sas/00_RUN_AB.sas to define a fresh output directory.;
    %abort cancel;
  %end;
  %if not %sysfunc(fileexist(&sasdata./sas_reviewer_ab_20260914.csv)) %then %do;
    %put ERROR: Missing A/B agreement input.;
    %abort cancel;
  %end;
  data work.sc11_ab;
    infile "&sasdata./sas_reviewer_ab_20260914.csv" dsd dlm=',' firstobs=2
      truncover encoding='utf-8' lrecl=32767;
    length review_id $32 a_category b_category final_category a_action_mask b_action_mask 8
      resolution_source $48;
    input review_id $ a_category b_category final_category a_action_mask b_action_mask resolution_source $;
  run;
  %sc11_check;
  proc sql noprint;
    select count(*),count(distinct review_id) into :n trimmed,:u trimmed from work.sc11_ab;
    select count(*) into :bad trimmed from work.sc11_ab
    where missing(review_id) or missing(a_category) or missing(b_category) or missing(final_category)
      or a_category not in (1,2,3,4) or b_category not in (1,2,3,4)
      or final_category not in (1,2,3,4)
      or missing(a_action_mask) or missing(b_action_mask)
      or a_action_mask<1 or a_action_mask>127 or b_action_mask<1 or b_action_mask>127
      or a_action_mask ne floor(a_action_mask) or b_action_mask ne floor(b_action_mask)
      or (band(a_action_mask,16)>0 and a_action_mask ne 16)
      or (band(b_action_mask,16)>0 and b_action_mask ne 16)
      or (band(a_action_mask,64)>0 and a_action_mask ne 64)
      or (band(b_action_mask,64)>0 and b_action_mask ne 64)
      or resolution_source not in ('auto_agreement_not_human_adjudication','adjudication')
      or ((resolution_source='auto_agreement_not_human_adjudication') ne
          (a_category=b_category and a_action_mask=b_action_mask))
      or (resolution_source='auto_agreement_not_human_adjudication' and final_category ne a_category);
  quit;
  %sc11_check;
  %if &n ne 556 or &u ne 556 or &bad ne 0 %then %do;
    %put ERROR: Invalid A/B input rows=&n. unique=&u. bad=&bad.;
    %abort cancel;
  %end;

  data work.sc11_category_grid;
    do a_category=1 to 4; do b_category=1 to 4; output; end; end;
  run;
  proc sql;
    create table work.sc11_category_cells as
    select g.a_category,g.b_category,count(x.review_id) as n
    from work.sc11_category_grid g left join work.sc11_ab x
      on g.a_category=x.a_category and g.b_category=x.b_category
    group by g.a_category,g.b_category order by g.a_category,g.b_category;
  quit;
  %sc11_check;
  data work.sc11_final_category_grid;
    do final_category=1 to 4; output; end;
  run;
  %sc11_check;
  proc sql;
    create table work.sc11_final_category_cells as
    select g.final_category,count(x.review_id) as n
    from work.sc11_final_category_grid g left join work.sc11_ab x
      on g.final_category=x.final_category
    group by g.final_category order by g.final_category;
  quit;
  %sc11_check;
  data work.sc11_final_category_cells;
    set work.sc11_final_category_cells;
    proportion=n/&n.;
    format proportion best32.;
  run;
  %sc11_check;
  data work.sc11_actions;
    set work.sc11_ab;
    do action_code=1 to 7;
      a_value=(band(a_action_mask,2**(action_code-1))>0);
      b_value=(band(b_action_mask,2**(action_code-1))>0);
      output;
    end;
    keep review_id action_code a_value b_value;
  run;
  data work.sc11_action_grid;
    do action_code=1 to 7; do a_value=0 to 1; do b_value=0 to 1; output; end; end; end;
  run;
  proc sql;
    create table work.sc11_action_cells as
    select g.action_code,g.a_value,g.b_value,count(x.review_id) as n
    from work.sc11_action_grid g left join work.sc11_actions x
      on g.action_code=x.action_code and g.a_value=x.a_value and g.b_value=x.b_value
    group by g.action_code,g.a_value,g.b_value order by g.action_code,g.a_value,g.b_value;
  quit;
  %sc11_check;

  /* Both axes include all codes, including zero frequency rows and columns. */
  data work.sc11_all_cells;
    length measure $32;
    set work.sc11_category_cells(in=category) work.sc11_action_cells(in=action);
    if category then do; measure='category'; av=a_category; bv=b_category; end;
    if action then do; measure=cats('action_',action_code); av=a_value; bv=b_value; end;
    keep measure av bv n;
  run;
  proc sql;
    create table work.sc11_margina as select measure,av,sum(n) as na
      from work.sc11_all_cells group by measure,av;
    create table work.sc11_marginb as select measure,bv,sum(n) as nb
      from work.sc11_all_cells group by measure,bv;
    create table work.sc11_chance as select a.measure,sum(a.na*b.nb) as numerator
      from work.sc11_margina a inner join work.sc11_marginb b
      on a.measure=b.measure and a.av=b.bv group by a.measure;
    create table work.sc11_totals as select measure,sum(n) as n,
      sum(case when av=bv then n else 0 end) as agree_n
      from work.sc11_all_cells group by measure;
    create table work.sc11_agreement as select t.*,c.numerator
      from work.sc11_totals t inner join work.sc11_chance c on t.measure=c.measure;
    create table work.sc11_action_set as select 'action_set' as measure length=32,
      count(*) as n,sum(a_action_mask=b_action_mask) as agree_n from work.sc11_ab;
  quit;
  %sc11_check;
  data work.sc11_agreement;
    set work.sc11_agreement work.sc11_action_set;
    agreement=.; kappa=.;
    if n>0 then do;
      agreement=agree_n/n;
      if measure ne 'action_set' then do;
        pe=numerator/(n*n);
        if pe<1 then kappa=(agreement-pe)/(1-pe);
      end;
    end;
    format agreement kappa best32.;
    keep measure n agree_n agreement kappa;
  run;
  %sc11_check;

  title 'Pre-consensus A/B categories: use unweighted kappa only';
  proc freq data=work.sc11_category_cells;
    tables a_category*b_category / agree;
    weight n / zeros;
  run;
  %sc11_check;
  title 'Pre-consensus action indicators: descriptive agreement';
  proc freq data=work.sc11_action_cells;
    by action_code;
    tables a_value*b_value / agree;
    weight n / zeros;
  run;
  %sc11_check;
  title 'Pre-consensus agreement: category, exact action set, individual actions';
  proc print data=work.sc11_agreement noobs; run;
  title 'Final consensus category counts: separate descriptive table';
  proc freq data=work.sc11_ab; tables final_category; run;
  %sc11_check;
  proc export data=work.sc11_category_cells outfile="&runout./11_category_cells.csv" dbms=csv replace; run;
  %sc11_check;
  proc export data=work.sc11_final_category_cells outfile="&runout./11_final_category_cells.csv" dbms=csv replace; run;
  %sc11_check;
  proc export data=work.sc11_agreement outfile="&runout./11_agreement.csv" dbms=csv replace; run;
  %sc11_check;
  proc export data=work.sc11_action_cells outfile="&runout./11_action_cells.csv" dbms=csv replace; run;
  %sc11_check;
  title;
  %let sc11_complete=1;
  %put NOTE: A was AI-assisted. B used no AI and had no prior answer/label/prediction exposure per user attestation.;
  %put NOTE: Agreement is descriptive review evidence, not detection accuracy.;
  %put NOTE: SCAMLENS_11_COMPLETE;
%mend;
%sc11_run;
