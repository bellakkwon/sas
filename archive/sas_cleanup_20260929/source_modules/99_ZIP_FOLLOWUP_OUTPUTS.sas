/*---------------------------------------------------------------------------
  S99 — Follow-up run evidence ZIP packaging helper.

  Usage (three lines in SAS Studio / Enterprise Guide):
    %let projroot = /home/student/github;
    %let zip_run  = run_01234567-89ab-cdef-0123-456789abcdef;
    %include "&projroot./sas/99_ZIP_FOLLOWUP_OUTPUTS.sas";

  Purpose:
    Enumerate existing evidence artifacts (step logs, HTML reports, CSV readbacks,
    ODS graphics PNG images, status records) from an existing follow-up run and
    bundle them into a single ZIP archive under &projroot./followup_20260921_v1/outputs/
    without rerunning any analysis, model fitting, or external network calls.
    Designed for SAS Studio / Enterprise Guide users where direct folder downloads
    are not supported by the web UI.

  Design & Safety Guards:
    - Pure SAS native FILENAME ZIP; no shell/X/PIPE commands, network, or APIs.
    - Read-only on source files: does NOT modify or delete original run files.
    - Rejects existing archive name: creates a fresh uniquely named ZIP.
    - Inspects the SIX bounded known directories:
        1. root:              &rundir
        2. stage_u5:          &rundir/stage_u5
        3. stage_u5/data:     &rundir/stage_u5/data
        4. stage_u5/outputs:  &rundir/stage_u5/outputs
        5. stage_cmp:         &rundir/stage_cmp
        6. stage_cmp/outputs: &rundir/stage_cmp/outputs
    - Validates directory bounds: unexpected subdirectories trigger immediate abort
      instead of being silently omitted.
    - Tolerates failed runs: required root must exist, while optional nested
      stages absent in failed runs are safely skipped.
    - Member names validated against directory traversal and unsafe characters.
    - Binary-preserving copy using recfm=n byte stream (preserves PNG/CSV/HTML/UTF-8).
    - Post-packaging verification: reopens ZIP archive and reconciles member
      count and member manifest against expected files before printing the path.
    - Clean failure handling: aborts on copy or verification errors without
      resetting SYSCC or claiming analysis completion status.

  Runtime Limitations:
    - Requires SAS 9.4 or SAS Viya with native FILENAME ZIP access method.
    - Packages existing run outputs on disk; does not assert analysis validity.
---------------------------------------------------------------------------*/
%global projroot zip_run;

/* Portable projroot default if not already set */
data _null_;
  if symget('projroot') = '' then call symputx('projroot', '/home/student/github');
run;

%macro zip_followup_outputs;
  %local pkg outputs_dir rundir zipfile n_files i cur_src cur_rel
         _err _cc;

  %let pkg = &projroot./followup_20260921_v1;
  %let outputs_dir = &pkg./outputs;

  /* Step 1: Validate required zip_run macro variable */
  data _null_;
    length zr $256;
    zr = strip(symget('zip_run'));
    if zr = '' then do;
      put 'ERROR: [ScamLens 99] Macro variable zip_run is REQUIRED.';
      put 'NOTE:  Example: %let zip_run = run_01234567-89ab-cdef-0123-456789abcdef;';
      abort cancel;
    end;
    /* ZR is fixed-width: assignment pads it back to 256 bytes even after
       STRIP. Trim at the PRXMATCH call so the end anchor sees the run ID. */
    if not (prxmatch('/^run_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/', strip(zr))
            or prxmatch('/^run_[0-9a-fA-F]{32}$/', strip(zr))) then do;
      put 'ERROR: [ScamLens 99] zip_run must match exact format run_<UUID>: ' zr;
      abort cancel;
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  %let rundir = &outputs_dir./&zip_run;

  /* Step 2: Validate existence of outputs and run directory */
  data _null_;
    length rdir $2048;
    rdir = symget('rundir');
    if not fileexist(rdir) then do;
      put 'ERROR: [ScamLens 99] Required run directory does not exist: ' rdir;
      abort cancel;
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* Step 3: Determine fresh uniquely named ZIP file under outputs/ */
  %let zipfile = &outputs_dir./&zip_run._evidence_%sysfunc(uuidgen()).zip;

  data _null_;
    length zf $2048;
    zf = symget('zipfile');
    if fileexist(zf) then do;
      put 'ERROR: [ScamLens 99] ZIP file already exists, refusing to overwrite: ' zf;
      abort cancel;
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* Step 4: Define the SIX known run directories and their allowed subdirectories */
  data work._dirs_to_scan;
    length dir_id 8 dir_rel $128 dir_path $2048 is_required 8 allowed_subs $256;
    dir_id = 1; dir_rel = '';                  dir_path = symget('rundir');                                     is_required = 1; allowed_subs = 'stage_u5|stage_cmp'; output;
    dir_id = 2; dir_rel = 'stage_u5';          dir_path = catx('/', symget('rundir'), 'stage_u5');              is_required = 0; allowed_subs = 'data|outputs'; output;
    dir_id = 3; dir_rel = 'stage_u5/data';     dir_path = catx('/', symget('rundir'), 'stage_u5', 'data');     is_required = 0; allowed_subs = ''; output;
    dir_id = 4; dir_rel = 'stage_u5/outputs';  dir_path = catx('/', symget('rundir'), 'stage_u5', 'outputs');  is_required = 0; allowed_subs = ''; output;
    dir_id = 5; dir_rel = 'stage_cmp';         dir_path = catx('/', symget('rundir'), 'stage_cmp');             is_required = 0; allowed_subs = 'outputs'; output;
    dir_id = 6; dir_rel = 'stage_cmp/outputs'; dir_path = catx('/', symget('rundir'), 'stage_cmp', 'outputs'); is_required = 0; allowed_subs = ''; output;
  run;

  /* Step 5: Enumerate immediate files and reject unexpected subdirectories */
  data work._manifest_expected(keep=file_id src_path rel_path);
    set work._dirs_to_scan;
    length mem $256 item_path $2048 full_rel $256 subref $8 dref $8 fref $8;
    length src_path $2048 rel_path $256;
    retain file_id 0;

    /* Check if directory exists */
    if not fileexist(dir_path) then do;
      if is_required then do;
        put 'ERROR: [ScamLens 99] Required directory does not exist: ' dir_path;
        abort cancel;
      end;
      return; /* Optional directory absent in failed run is okay */
    end;

    /* Open directory for member inspection */
    dref = '_sdir';
    rc = filename(dref, dir_path);
    if rc ne 0 then do;
      put 'ERROR: [ScamLens 99] Cannot assign fileref for directory: ' dir_path;
      abort cancel;
    end;

    did = dopen(dref);
    if did <= 0 then do;
      put 'ERROR: [ScamLens 99] Cannot open directory: ' dir_path;
      abort cancel;
    end;

    memcnt = dnum(did);
    do i = 1 to memcnt;
      mem = dread(did, i);
      if mem in ('.', '..') then continue;

      item_path = catx('/', dir_path, mem);

      /* Test if item is a subdirectory */
      subref = '_subchk';
      rc_sub = filename(subref, item_path);
      if rc_sub ne 0 then do;
        put 'ERROR: [ScamLens 99] Cannot assign fileref for member inspection: ' item_path;
        abort cancel;
      end;
      sub_did = dopen(subref);

      if sub_did > 0 then do;
        /* Subdirectory encountered: check if allowed */
        rc_c = dclose(sub_did);
        rc_sub = filename(subref);

        is_allowed = 0;
        if allowed_subs ne '' then do;
          do k = 1 to countw(allowed_subs, '|');
            if mem = scan(allowed_subs, k, '|') then is_allowed = 1;
          end;
        end;

        if is_allowed = 0 then do;
          put 'ERROR: [ScamLens 99] Unexpected subdirectory found in ' dir_path ': ' mem;
          put 'ERROR: [ScamLens 99] Rejecting run package containing unknown subdirectories.';
          abort cancel;
        end;
        /* Allowed subdirectories are enumerated when processing their own scan entries */
      end;
      else do;
        /* Regular immediate file */
        rc_sub = filename(subref);

        /* Construct relative member path */
        if dir_rel = '' then full_rel = mem;
        else full_rel = catx('/', dir_rel, mem);

        /* Security guard 1: Check for directory traversal */
        if index(full_rel, '..') > 0 then do;
          put 'ERROR: [ScamLens 99] Path traversal pattern detected: ' full_rel;
          abort cancel;
        end;

        /* Security guard 2: Member name must only contain safe characters */
        if not prxmatch('/^[a-zA-Z0-9_\-\.\/]+$/', strip(full_rel)) then do;
          put 'ERROR: [ScamLens 99] Member name contains unsafe characters: ' full_rel;
          abort cancel;
        end;

        /* Verify file is readable */
        fref = '_fchk';
        rc_f = filename(fref, item_path);
        if rc_f ne 0 then do;
          put 'ERROR: [ScamLens 99] Cannot assign fileref for file: ' item_path;
          abort cancel;
        end;
        fid = fopen(fref, 'I', 1, 'B');
        if fid <= 0 then do;
          put 'ERROR: [ScamLens 99] Cannot open file for reading: ' item_path;
          abort cancel;
        end;
        rc_f = fclose(fid);
        rc_f = filename(fref);

        file_id + 1;
        src_path = item_path;
        rel_path = full_rel;
        output;
      end;
    end;

    rc_d = dclose(did);
    rc_d = filename(dref);
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* Step 6: Verify at least one file was discovered */
  data _null_;
    if 0 then set work._manifest_expected nobs=n;
    if n = 0 then do;
      put 'ERROR: [ScamLens 99] No evidence files discovered in run directory.';
      abort cancel;
    end;
    call symputx('n_files', n);
    stop;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* Step 7: Binary-preserving copy into ZIP archive */
  %do i = 1 %to &n_files;
    data _null_;
      set work._manifest_expected(where=(file_id = &i));
      call symputx('cur_src', strip(src_path));
      call symputx('cur_rel', strip(rel_path));
      stop;
    run;
    %if &syserr > 0 or &syscc > 4 %then %abort cancel;

    filename _in "&cur_src" recfm=n;
    filename _out zip "&zipfile" member="&cur_rel";

    data _null_;
      infile _in recfm=n;
      file _out recfm=n;
      input byte $char1. @;
      put byte $char1. @;
    run;

    %let _err = &syserr;
    %let _cc = &syscc;

    filename _in clear;
    filename _out clear;

    %if &_err > 0 or &_cc > 4 %then %do;
      %put ERROR: [ScamLens 99] Failed while copying &cur_rel into ZIP archive.;
      %abort cancel;
    %end;
  %end;

  /* Step 8: Reopen ZIP archive and reconcile member names and counts */
  filename _chkzip zip "&zipfile";

  data work._members_actual;
    length mname $256 actual_rel $256;
    fid = dopen('_chkzip');
    if fid <= 0 then do;
      put 'ERROR: [ScamLens 99] Cannot reopen generated ZIP archive for member reconciliation.';
      abort cancel;
    end;
    actual_cnt = dnum(fid);
    if actual_cnt ne &n_files then do;
      put 'ERROR: [ScamLens 99] Reopened ZIP member count (' actual_cnt ') does not match expected count (&n_files).';
      abort cancel;
    end;
    do j = 1 to actual_cnt;
      mname = dread(fid, j);
      actual_rel = strip(mname);
      output;
    end;
    rc = dclose(fid);
  run;

  filename _chkzip clear;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  proc sort data=work._manifest_expected out=work._exp_sorted(keep=rel_path);
    by rel_path;
  run;
  proc sort data=work._members_actual out=work._act_sorted;
    by actual_rel;
  run;

  data _null_;
    set work._act_sorted;
    by actual_rel;
    if not (first.actual_rel and last.actual_rel) then do;
      put 'ERROR: [ScamLens 99] Duplicate member detected in ZIP archive: ' actual_rel;
      abort cancel;
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  data work._reconcile;
    merge work._exp_sorted(in=in_exp rename=(rel_path=mem_name))
          work._act_sorted(in=in_act rename=(actual_rel=mem_name));
    by mem_name;
    in_expected = in_exp;
    in_actual = in_act;
    if not (in_exp and in_act) then mismatch = 1;
    else mismatch = 0;
  run;

  data _null_;
    set work._reconcile end=eof;
    retain mismatches 0 total 0;
    total + 1;
    if mismatch = 1 then do;
      mismatches + 1;
      if in_expected and not in_actual then
        put 'ERROR: [ScamLens 99] Expected file missing from ZIP: ' mem_name;
      if in_actual and not in_expected then
        put 'ERROR: [ScamLens 99] Unexpected file present in ZIP: ' mem_name;
    end;
    if eof then do;
      if mismatches > 0 or total ne &n_files then do;
        put 'ERROR: [ScamLens 99] Member reconciliation failed with ' mismatches ' mismatch(es) (verified ' total ' vs expected &n_files).';
        abort cancel;
      end;
      put 'NOTE: [ScamLens 99] Reconciliation passed: ' total ' member(s) verified.';
    end;
  run;
  %if &syserr > 0 or &syscc > 4 %then %abort cancel;

  /* Step 9: Print full path only after packaging and reconciliation checks pass */
  %put NOTE: [ScamLens 99] SCAMLENS_FOLLOWUP_ZIP_COMPLETE: Evidence archive created at &zipfile.;
  %put NOTE: [ScamLens 99] Packaged &n_files evidence artifact(s) from &rundir.;
%mend zip_followup_outputs;

%zip_followup_outputs;
