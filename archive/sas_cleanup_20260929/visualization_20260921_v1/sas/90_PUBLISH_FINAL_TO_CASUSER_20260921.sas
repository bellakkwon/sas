/* Explicit CAS publication entrypoint. Aggregates only. No replace/drop/save.
   %let projroot=/home/student/github;
   %let sv_suffix=20260921;  * choose a new suffix for a separate publication;
   %include "&projroot./visualization_20260921_v1/sas/90_PUBLISH_FINAL_TO_CASUSER_20260921.sas";
*/
%global projroot sv_suffix sv_cas_outdir;
%macro sv_publish;
  %local valid i source target keys n cmp_rc runid sources targets keylist counts;
  %if %length(%superq(projroot))=0 %then %let projroot=/home/student/github;
  %if %length(%superq(sv_suffix))=0 %then %let sv_suffix=20260921;
  data _null_;
    call symputx('valid',prxmatch('/^[A-Za-z0-9_]{1,12}$/',strip(symget('sv_suffix'))),'L');
  run;
  %if &valid ne 1 %then %do;
    %put ERROR: sv_suffix must contain 1 to 12 letters digits or underscores;
    %abort cancel;
  %end;
  %include "&projroot./visualization_20260921_v1/sas/10_LOAD_FINAL_AGGREGATES.sas";
  %if &sv_loaded ne 1 %then %abort cancel;
  %let sources=sv_models sv_features sv_truncation sv_kisa sv_jev sv_fusion;
  %let targets=slf_u5 slf_feat slf_trunc slf_kisa slf_jev slf_fusion;
  %let keylist=arm seed|feature_category feature_value|arm is_truncated|cohort seed condition|seed cohort|arm role;
  %let counts=15 17 6 105 15 15;
  cas svfinal;
  %sv_check(start_cas_session)
  libname sfcas cas sessref=svfinal caslib='CASUSER';
  %sv_check(assign_cas_library)
  /* Check every target BEFORE loading any table. Never replace prior tables. */
  %do i=1 %to 6;
    %let target=%scan(&targets,&i)_&sv_suffix;
    %if %sysfunc(exist(sfcas.&target)) %then %do;
      %put ERROR: CASUSER.&target already exists - choose a new sv_suffix;
      %abort cancel;
    %end;
  %end;
  %let runid=cas_%sysfunc(uuidgen());
  %let sv_cas_outdir=&sv_root./outputs/&runid;
  data _null_;
    length parent created $2048;
    parent=symget('sv_root');
    if not fileexist(cats(parent,'/outputs')) then created=dcreate('outputs',parent);
    if not fileexist(cats(parent,'/outputs')) then do;
      put 'ERROR: Cannot create CAS evidence parent'; abort cancel;
    end;
    if fileexist(symget('sv_cas_outdir')) then do;
      put 'ERROR: Refusing existing CAS evidence directory'; abort cancel;
    end;
    created=dcreate(symget('runid'),cats(parent,'/outputs'));
    if not fileexist(symget('sv_cas_outdir')) then do;
      put 'ERROR: Cannot create CAS evidence directory'; abort cancel;
    end;
  run;
  %sv_check(create_cas_evidence_directory)
  data _null_;
    file "&sv_cas_outdir./cas_status.txt";
    put 'status=started - not complete';
    put "suffix=&sv_suffix";
  run;
  %sv_check(write_cas_started)
  /* Upload session-scope only, then independently read back and compare. */
  %do i=1 %to 6;
    %let source=%scan(&sources,&i);
    %let target=%scan(&targets,&i)_&sv_suffix;
    %let keys=%scan(&keylist,&i,|);
    %let n=%scan(&counts,&i);
    proc casutil sessref=svfinal;
      load data=work.&source outcaslib='CASUSER' casout="&target";
    quit;
    %sv_check(cas_load)
    data work._sv_readback; set sfcas.&target; run;
    %sv_check(cas_readback)
    %sv_unique(_sv_readback,&keys,&n)
    proc sort data=work._sv_readback; by &keys; run;
    %sv_check(sort_cas_readback)
    proc sort data=work.&source out=work._sv_expected; by &keys; run;
    %sv_check(sort_cas_expected)
    proc compare base=work._sv_expected compare=work._sv_readback
      method=absolute criterion=1e-10 noprint;
      id &keys;
    run;
    %let cmp_rc=&sysinfo;
    %sv_check(compare_cas_values)
    /* Ignore format/label/length metadata changes. Reject row/key/variable/type/value errors. */
    %if %sysfunc(band(&cmp_rc,65472)) ne 0 %then %do;
      %put ERROR: CAS readback mismatch table=&target SYSINFO=&cmp_rc;
      %abort cancel;
    %end;
    proc export data=work._sv_readback outfile="&sv_cas_outdir./readback_&target..csv" dbms=csv replace;
    run;
    %sv_check(export_cas_readback)
    %sv_nonempty(&sv_cas_outdir./readback_&target..csv)
    %put NOTE: CAS_READBACK_VERIFIED table=&target rows=&n;
  %end;
  /* Only after ALL six tables pass comparison, expose them to VA sessions. */
  %do i=1 %to 6;
    %let target=%scan(&targets,&i)_&sv_suffix;
    proc casutil sessref=svfinal;
      promote casdata="&target" incaslib='CASUSER' outcaslib='CASUSER' casout="&target";
    quit;
    %sv_check(cas_promote)
    %if not %sysfunc(exist(sfcas.&target)) %then %do;
      %put ERROR: Promoted table is not accessible - &target;
      %abort cancel;
    %end;
    %put NOTE: CAS_PROMOTED table=CASUSER.&target;
  %end;
  data _null_;
    length target $32;
    file "&sv_cas_outdir./cas_status.txt";
    put 'status=ok stage=cas_readback_and_promote';
    put "suffix=&sv_suffix";
    do i=1 to 6;
      target=cats(scan("&targets",i),'_',symget('sv_suffix'));
      put 'table=CASUSER.' target;
    end;
    put 'va_report_saved=not_verified';
  run;
  %sv_check(write_cas_status)
  %sv_nonempty(&sv_cas_outdir./cas_status.txt)
  %put NOTE: SCAMLENS_FINAL_CAS_COMPLETE;
  %put NOTE: CAS_EVIDENCE=&sv_cas_outdir;
%mend;
%sv_publish;
