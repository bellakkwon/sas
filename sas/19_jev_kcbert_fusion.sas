/* F2 aggregate verification and optional PROC LOGISTIC boundary reference.
   Reads only the public aggregate.csv. No SAS execution is claimed.
   PROC LOGISTIC below is unpenalized and is not equivalent to the
   sklearn L2 fit; Python-side check() verifies learned scores instead.
   This is aggregate arithmetic, not independent SAS model fitting.
   Brier is enforced finite in [0,1] only; score-level Brier/model
   verification is Python-only. */
/* Caller presets agg_csv with %let before %include; this file never clears
   it. Declare global scope portably (no conditional open code). An empty
   value is fail-closed inside %verify_aggregate below. */
%global agg_csv;

%macro verify_aggregate;
  %local coltypes;
  %global agg_csv;
  %if %superq(agg_csv)= %then %do;
    %put ERROR: Set agg_csv to the public aggregate.csv.;
    %abort cancel;
  %end;
  %else %do;
    /* Drop stale WORK tables so a previous run cannot mask a failed import. */
    proc datasets lib=work nolist;
      delete aggregate grid dups;
    quit;
    %if &syserr > 0 or &syscc > 4 %then %abort cancel;
    proc import datafile="&agg_csv" out=aggregate dbms=csv replace;
      guessingrows=max; getnames=yes;
    run;
    %if &syserr > 0 or &syscc > 4 %then %do;
      %put ERROR: Aggregate CSV import failed.;
      %abort cancel;
    %end;
    /* Explicit typed re-read of the known 16-column contract: names,
       order, types, and row count. IF 0 THEN SET with KEEP checks names
       only, so parse every data row with declared types instead. */
    data _null_;
      infile "&agg_csv" lrecl=32767 encoding="utf-8" dsd dlm="," firstobs=2 truncover end=eof;
      length arm $8 role $16 _extra $32767;
      input arm $ role $ threshold n normal_denominator smishing_denominator
            tp tn fp fn recall fpr precision f1 brier fpr_quantization _extra $;
      if _error_ then do;
        put 'ERROR: Aggregate CSV typed read failed.';
        abort cancel;
      end;
      if not missing(strip(_extra)) then do;
        put 'ERROR: Aggregate CSV has more than 16 columns.';
        abort cancel;
      end;
      if missing(arm) or missing(role) then do;
        put 'ERROR: Aggregate CSV has a blank arm or role.';
        abort cancel;
      end;
      nrows + 1;
      if eof and nrows ne 15 then do;
        put 'ERROR: expected 15 aggregate rows, found ' nrows;
        abort cancel;
      end;
    run;
    %if &syserr > 0 or &syscc > 4 %then %do;
      %put ERROR: Aggregate CSV schema mismatch.;
      %abort cancel;
    %end;
    /* Imported-column type contract (order-sensitive): arm/role char,
       the other 14 numeric. */
    proc sql noprint;
      select cats(upcase(name), ':', upcase(substr(type, 1, 1)))
        into :coltypes separated by ' '
      from dictionary.columns
      where libname = 'WORK' and memname = 'AGGREGATE'
      order by varnum;
    quit;
    %if &syserr > 0 or &syscc > 4 %then %abort cancel;
    %if "&coltypes" ne "ARM:C ROLE:C THRESHOLD:N N:N NORMAL_DENOMINATOR:N SMISHING_DENOMINATOR:N TP:N TN:N FP:N FN:N RECALL:N FPR:N PRECISION:N F1:N BRIER:N FPR_QUANTIZATION:N" %then %do;
      %put ERROR: Aggregate column name/type/order mismatch.;
      %abort cancel;
    %end;
    /* Full 15-cell arm-role grid with no duplicate or missing cells. */
    proc sort data=aggregate out=grid nodupkey dupout=dups;
      by arm role;
    run;
    data _null_;
      if 0 then set dups nobs=ndup;
      if ndup > 0 then do;
        put 'ERROR: duplicate arm-role cells'; abort cancel;
      end;
      stop;
    run;
    data _null_;
      set grid end=eof;
      by arm role;
      retain ncell;
      if _n_ = 1 then ncell = 0;
      ncell + 1;
      if last.role then do;
        armrole = strip(arm) || '/' || strip(role);
        if armrole not in ('rawK/meta_fit' 'rawK/calibration' 'rawK/readout'
                           'K/meta_fit' 'K/calibration' 'K/readout'
                           'KJ/meta_fit' 'KJ/calibration' 'KJ/readout'
                           'KU/meta_fit' 'KU/calibration' 'KU/readout'
                           'KJU/meta_fit' 'KJU/calibration' 'KJU/readout') then do;
          put 'ERROR: unknown arm-role cell=' armrole; abort cancel;
        end;
      end;
      if eof and ncell ne 15 then do;
        put 'ERROR: expected 15 arm-role cells, found ' ncell; abort cancel;
      end;
    run;
    data _null_;
      set grid end=eof;
      array counts n tp tn fp fn normal_denominator smishing_denominator;
      do over counts;
        if missing(counts) or counts < 0 or round(counts) ne counts then do;
          put 'ERROR: missing or non-integer count'; abort cancel;
        end;
      end;
      /* Thresholds may exceed 1 (all-negative nextafter candidate); never cap at 1. */
      if missing(threshold) or threshold < 0 then do;
        put 'ERROR: missing threshold'; abort cancel;
      end;
      if tp+tn+fp+fn ne n then do; put 'ERROR: confusion totals do not equal n'; abort cancel; end;
      if normal_denominator ne tn+fp then do; put 'ERROR: normal denominator mismatch'; abort cancel; end;
      if smishing_denominator ne tp+fn then do; put 'ERROR: smishing denominator mismatch'; abort cancel; end;
      /* Exact null semantics matching Python metrics(): a rate is required
         present iff its denominator is positive, else required missing. */
      if (tp + fn) = 0 then do;
        if not missing(recall) then do; put 'ERROR: recall must be null'; abort cancel; end;
      end;
      else do;
        if missing(recall) or recall < 0 or recall > 1
           or abs(recall - tp/(tp+fn)) > 1e-9 then do;
          put 'ERROR: recall arithmetic mismatch'; abort cancel;
        end;
      end;
      if (tp + fp) = 0 then do;
        if not missing(precision) then do; put 'ERROR: precision must be null'; abort cancel; end;
      end;
      else do;
        if missing(precision) or precision < 0 or precision > 1
           or abs(precision - tp/(tp+fp)) > 1e-9 then do;
          put 'ERROR: precision arithmetic mismatch'; abort cancel;
        end;
      end;
      if missing(recall) or missing(precision) then do;
        if not missing(f1) then do; put 'ERROR: F1 must be null'; abort cancel; end;
      end;
      else do;
        if missing(f1) or f1 < 0 or f1 > 1 then do;
          put 'ERROR: F1 arithmetic mismatch'; abort cancel;
        end;
        if (precision + recall) = 0 then do;
          if f1 ne 0 then do; put 'ERROR: F1 arithmetic mismatch'; abort cancel; end;
        end;
        else if abs(f1 - 2*precision*recall/(precision+recall)) > 1e-9 then do;
          put 'ERROR: F1 arithmetic mismatch'; abort cancel;
        end;
      end;
      if normal_denominator = 0 then do;
        if not missing(fpr) then do; put 'ERROR: FPR must be null'; abort cancel; end;
        if not missing(fpr_quantization) then do;
          put 'ERROR: FPR quantization must be null'; abort cancel;
        end;
      end;
      else do;
        if missing(fpr) or fpr < 0 or fpr > 1
           or abs(fpr - fp/normal_denominator) > 1e-9 then do;
          put 'ERROR: FPR arithmetic mismatch'; abort cancel;
        end;
        if missing(fpr_quantization)
           or abs(fpr_quantization - 1/normal_denominator) > 1e-9 then do;
          put 'ERROR: FPR quantization mismatch'; abort cancel;
        end;
      end;
      /* Brier cannot be reconstructed from confusion counts: require finite
         [0,1] here; score-level Brier/model verification is Python-only. */
      if missing(brier) or brier < 0 or brier > 1 then do;
        put 'ERROR: Brier must be finite in [0,1]'; abort cancel;
      end;
      if role = 'calibration' and fpr > 0.01 + 1e-9 then do;
        put 'ERROR: calibration FPR exceeds 1%'; abort cancel;
      end;
      if eof then put 'NOTE: aggregate arithmetic checks passed; no model fit was executed.';
    run;
    /* Cross-arm stability: identical role denominators/n and one threshold
       per arm across roles. */
    data _null_;
      set grid end=eof;
      by arm role;
      array refn(3) _temporary_;
      array refnd(3) _temporary_;
      array refsd(3) _temporary_;
      array reft(5) _temporary_;
      ridx = whichc(role, 'meta_fit', 'calibration', 'readout');
      aidx = whichc(arm, 'rawK', 'K', 'KJ', 'KU', 'KJU');
      if refn(ridx) = . then do;
        refn(ridx) = n; refnd(ridx) = normal_denominator; refsd(ridx) = smishing_denominator;
      end;
      else if n ne refn(ridx) or normal_denominator ne refnd(ridx)
              or smishing_denominator ne refsd(ridx) then do;
        put 'ERROR: role denominators/n differ across arms'; abort cancel;
      end;
      if reft(aidx) = . then reft(aidx) = threshold;
      else if threshold ne reft(aidx) then do;
        put 'ERROR: threshold not stable per arm'; abort cancel;
      end;
      if eof then put 'NOTE: cross-arm stability checks passed.';
    run;
  %end;
%mend;
/* Optional private-score fit boundary: use only meta_fit rows and the same
   feature columns; do not use this unpenalized estimator as sklearn L2 parity. */
/* proc logistic data=private_scored(where=(role='meta_fit')) outmodel=model;
     model label(event='smishing')=logit_k jev_1-jev_6 url_1-url_5;
   run;
   proc logistic inmodel=model; score data=private_scored(where=(role ne 'meta_fit')) out=scored; run; */
%verify_aggregate;
