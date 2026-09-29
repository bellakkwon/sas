/* Frozen public aggregates only. Included by both entrypoints. No model fitting. */
%global projroot sv_root sv_loaded;
%let sv_loaded=0;
%macro sv_check(label);
  %if &syserr > 4 or &syscc > 4 %then %do;
    %put ERROR: [ScamLens final] &label failed SYSERR=&syserr SYSCC=&syscc;
    %abort cancel;
  %end;
%mend;
%macro sv_init;
  %if %length(%superq(projroot))=0 %then %let projroot=/home/student/github;
  %let sv_root=&projroot./visualization_20260921_v1;
  %if not %sysfunc(fileexist(%superq(sv_root)/data)) %then %do;
    %put ERROR: Missing final package data directory under projroot=&projroot;
    %abort cancel;
  %end;
%mend;
%sv_init;
%macro sv_unique(ds,keys,n);
  %local got dup;
  proc sort data=work.&ds out=work._sv_keys nodupkey dupout=work._sv_dups;
    by &keys;
  run;
  %sv_check(unique_sort)
  proc sql noprint;
    select count(*) into :got trimmed from work._sv_keys;
    select count(*) into :dup trimmed from work._sv_dups;
  quit;
  %sv_check(unique_count)
  %if &got ne &n or &dup ne 0 %then %do;
    %put ERROR: Invalid row count or duplicate keys in &ds expected=&n actual=&got duplicates=&dup;
    %abort cancel;
  %end;
%mend;
%macro sv_nonempty(path);
  data _null_;
    length p $2048;
    p="&path";
    rc=filename('_svfile',p);
    fid=fopen('_svfile','I',1,'B');
    if fid=0 then do; put 'ERROR: Missing output ' p; abort cancel; end;
    rc=fread(fid);
    if rc ne 0 then do; put 'ERROR: Empty or unreadable output ' p; abort cancel; end;
    rc=fclose(fid); rc=filename('_svfile');
  run;
  %sv_check(output_file)
%mend;

data work.sv_models;
  length arm $8 seed 8 threshold 8 tp 8 tn 8 fp 8 fn 8 accuracy 8 precision 8 recall 8 fpr 8 f1 8 brier 8 mean_margin 8 std_margin 8;
  infile "&sv_root./data/u5_models.csv" encoding='utf-8' dsd dlm=',' firstobs=2 lrecl=32767 truncover;
  input arm :$8. seed :best32. threshold :best32. tp :best32. tn :best32. fp :best32. fn :best32. accuracy :best32. precision :best32. recall :best32. fpr :best32. f1 :best32. brier :best32. mean_margin :best32. std_margin :best32.;
  if _error_ then do; put 'ERROR: Invalid u5_models CSV row ' _n_; abort cancel; end;
  format _numeric_ best32.;
run;
%sv_check(load_u5_models)
%sv_unique(sv_models,arm seed,15)

data work.sv_features;
  length feature_category $40 feature_value $40 n_total 8 n_normal 8 n_smishing 8 dup_avg_fp 8 dup_avg_fn 8 dup_fpr 8 dup_fnr 8 base_avg_fp 8 base_avg_fn 8 flip_avg_fp 8 flip_avg_fn 8;
  infile "&sv_root./data/u5_features.csv" encoding='utf-8' dsd dlm=',' firstobs=2 lrecl=32767 truncover;
  input feature_category :$40. feature_value :$40. n_total :best32. n_normal :best32. n_smishing :best32. dup_avg_fp :best32. dup_avg_fn :best32. dup_fpr :best32. dup_fnr :best32. base_avg_fp :best32. base_avg_fn :best32. flip_avg_fp :best32. flip_avg_fn :best32.;
  if _error_ then do; put 'ERROR: Invalid u5_features CSV row ' _n_; abort cancel; end;
  format _numeric_ best32.;
run;
%sv_check(load_u5_features)
%sv_unique(sv_features,feature_category feature_value,17)

data work.sv_truncation;
  length arm $8 is_truncated 8 n_total 8 n_normal 8 n_smishing 8 mean_tp 8 mean_tn 8 mean_fp 8 mean_fn 8 recall 8 fnr 8 fpr 8 f1 8;
  infile "&sv_root./data/u5_truncation.csv" encoding='utf-8' dsd dlm=',' firstobs=2 lrecl=32767 truncover;
  input arm :$8. is_truncated :best32. n_total :best32. n_normal :best32. n_smishing :best32. mean_tp :best32. mean_tn :best32. mean_fp :best32. mean_fn :best32. recall :best32. fnr :best32. fpr :best32. f1 :best32.;
  if _error_ then do; put 'ERROR: Invalid u5_truncation CSV row ' _n_; abort cancel; end;
  format _numeric_ best32.;
run;
%sv_check(load_u5_truncation)
%sv_unique(sv_truncation,arm is_truncated,6)

data work.sv_kisa;
  length cohort $32 seed 8 condition $32 n 8 tp 8 tn 8 fp 8 fn 8 baseline_tp 8 baseline_tn 8 baseline_fp 8 baseline_fn 8 corrected_fp 8 corrected_fn 8 new_fp 8 new_fn 8 threshold 8 recall 8 fpr 8;
  infile "&sv_root./data/kisa_conditions.csv" encoding='utf-8' dsd dlm=',' firstobs=2 lrecl=32767 truncover;
  input cohort :$32. seed :best32. condition :$32. n :best32. tp :best32. tn :best32. fp :best32. fn :best32. baseline_tp :best32. baseline_tn :best32. baseline_fp :best32. baseline_fn :best32. corrected_fp :best32. corrected_fn :best32. new_fp :best32. new_fn :best32. threshold :best32. recall :best32. fpr :best32.;
  if _error_ then do; put 'ERROR: Invalid kisa_conditions CSV row ' _n_; abort cancel; end;
  format _numeric_ best32.;
run;
%sv_check(load_kisa_conditions)
%sv_unique(sv_kisa,cohort seed condition,105)

data work.sv_jev;
  length seed 8 cohort $32 n 8 b_tp 8 b_tn 8 b_fp 8 b_fn 8 j_tp 8 j_tn 8 j_fp 8 j_fn 8 j_abstain_pos 8 j_abstain_neg 8 t_corrected_fp 8 t_corrected_fn 8 t_new_fp 8 t_new_fn 8 t_persistent_fp 8 t_persistent_fn 8 t_abstain_from_error 8 t_abstain_from_correct 8 t_retained_correct 8 g_review_count 8 g_caught_error 8 g_missed_error 8 g_unnecessary_review 8;
  infile "&sv_root./data/jev_comparison.csv" encoding='utf-8' dsd dlm=',' firstobs=2 lrecl=32767 truncover;
  input seed :best32. cohort :$32. n :best32. b_tp :best32. b_tn :best32. b_fp :best32. b_fn :best32. j_tp :best32. j_tn :best32. j_fp :best32. j_fn :best32. j_abstain_pos :best32. j_abstain_neg :best32. t_corrected_fp :best32. t_corrected_fn :best32. t_new_fp :best32. t_new_fn :best32. t_persistent_fp :best32. t_persistent_fn :best32. t_abstain_from_error :best32. t_abstain_from_correct :best32. t_retained_correct :best32. g_review_count :best32. g_caught_error :best32. g_missed_error :best32. g_unnecessary_review :best32.;
  if _error_ then do; put 'ERROR: Invalid jev_comparison CSV row ' _n_; abort cancel; end;
  format _numeric_ best32.;
run;
%sv_check(load_jev_comparison)
%sv_unique(sv_jev,seed cohort,15)

data work.sv_fusion;
  length arm $16 role $24 threshold 8 n 8 normal_denominator 8 smishing_denominator 8 tp 8 tn 8 fp 8 fn 8 recall 8 fpr 8 precision 8 f1 8 brier 8 fpr_quantization 8;
  infile "&sv_root./data/jev_fusion.csv" encoding='utf-8' dsd dlm=',' firstobs=2 lrecl=32767 truncover;
  input arm :$16. role :$24. threshold :best32. n :best32. normal_denominator :best32. smishing_denominator :best32. tp :best32. tn :best32. fp :best32. fn :best32. recall :best32. fpr :best32. precision :best32. f1 :best32. brier :best32. fpr_quantization :best32.;
  if _error_ then do; put 'ERROR: Invalid jev_fusion CSV row ' _n_; abort cancel; end;
  format _numeric_ best32.;
run;
%sv_check(load_jev_fusion)
%sv_unique(sv_fusion,arm role,15)

/* Validate class denominators and rate semantics before any plots or CAS load. */
data _null_;
 set work.sv_models;
 array counts[*] tp tn fp fn;
 do i=1 to dim(counts);
   if missing(counts[i]) or counts[i]<0 or counts[i] ne int(counts[i]) then do;
     put 'ERROR: Invalid U5 count'; abort cancel;
   end;
 end;
 if arm not in ('BASE','DUP','FLIP') or seed not in (42,101,202,303,404)
   or tp+fn ne 652 or tn+fp ne 1665 or missing(recall) or missing(fpr)
   or abs(recall-tp/652)>1e-6 or abs(fpr-fp/1665)>1e-6 then do;
   put 'ERROR: U5 keys or rates mismatch'; abort cancel;
 end;
run;
%sv_check(validate_models)
data _null_;
 set work.sv_features;
 if missing(n_total) or n_total ne n_normal+n_smishing or min(n_normal,n_smishing)<0 then do;
   put 'ERROR: Feature denominator mismatch'; abort cancel;
 end;
 if (n_normal=0 and not missing(dup_fpr)) or
    (n_normal>0 and (missing(dup_fpr) or abs(dup_fpr-dup_avg_fp/n_normal)>1e-6)) or
    (n_smishing=0 and not missing(dup_fnr)) or
    (n_smishing>0 and (missing(dup_fnr) or abs(dup_fnr-dup_avg_fn/n_smishing)>1e-6)) then do;
   put 'ERROR: Feature rate mismatch'; abort cancel;
 end;
run;
%sv_check(validate_features)
data _null_;
 set work.sv_truncation;
 if arm not in ('BASE','DUP','FLIP') or is_truncated not in (0,1)
   or missing(n_total) or n_total ne n_normal+n_smishing
   or min(n_normal,n_smishing)<=0 or missing(fnr) or missing(fpr)
   or abs(mean_tp+mean_fn-n_smishing)>1e-6 or abs(mean_tn+mean_fp-n_normal)>1e-6
   or abs(fnr-mean_fn/n_smishing)>1e-6 or abs(fpr-mean_fp/n_normal)>1e-6 then do;
   put 'ERROR: Truncation denominator or rate mismatch'; abort cancel;
 end;
run;
%sv_check(validate_truncation)
data _null_;
 set work.sv_kisa;
 array counts[*] n tp tn fp fn;
 do i=1 to dim(counts);
   if missing(counts[i]) or counts[i]<0 or counts[i] ne int(counts[i]) then do;
     put 'ERROR: Invalid diagnostic count'; abort cancel;
   end;
 end;
 if seed not in (42,101,202,303,404) or condition not in
 ('original128','ocr_delete128','cap300','ocr_delete300','ocr_unk128','ocr_unk300','head_tail128')
 or cohort not in ('kisa_unique','kisa_representatives','normal_candidates')
 or n ne tp+tn+fp+fn then do; put 'ERROR: Diagnostic key or total mismatch'; abort cancel; end;
 if cohort='normal_candidates' then do;
   if n ne 250 or tp+fn ne 0 or not missing(recall) or missing(fpr) or abs(fpr-fp/250)>1e-10 then do;
     put 'ERROR: Normal candidate denominator or rate mismatch'; abort cancel;
   end;
 end;
 else do;
   expected=22; if cohort='kisa_representatives' then expected=18;
   if n ne expected or tn+fp ne 0 or not missing(fpr) or missing(recall) or abs(recall-tp/n)>1e-10 then do;
     put 'ERROR: Positive-only denominator or rate mismatch'; abort cancel;
   end;
 end;
run;
%sv_check(validate_kisa)
data _null_;
 set work.sv_jev;
 if seed not in (42,101,202,303,404) or cohort not in ('all','correct_controls','error_union')
   or missing(n) or n ne b_tp+b_tn+b_fp+b_fn
   or n ne j_tp+j_tn+j_fp+j_fn+j_abstain_pos+j_abstain_neg
   or (cohort='all' and n ne 88) then do;
   put 'ERROR: JEV comparison key or total mismatch'; abort cancel;
 end;
run;
%sv_check(validate_jev)
data _null_;
 set work.sv_fusion;
 if arm not in ('rawK','K','KU','KJ','KJU') or role not in ('meta_fit','calibration','readout')
   or missing(n) or n ne tp+tn+fp+fn or n ne normal_denominator+smishing_denominator
   or normal_denominator ne tn+fp or smishing_denominator ne tp+fn
   or missing(recall) or missing(fpr)
   or abs(recall-tp/smishing_denominator)>1e-10 or abs(fpr-fp/normal_denominator)>1e-10
   or (role='readout' and (n ne 142 or normal_denominator ne 108 or smishing_denominator ne 34)) then do;
   put 'ERROR: Fusion key or denominator mismatch'; abort cancel;
 end;
run;
%sv_check(validate_fusion)
%let sv_loaded=1;
%put NOTE: SCAMLENS_FINAL_AGGREGATES_LOADED;
