# SAS follow-up package (aggregate-only)

Status: complete

Contents: sas/ (runner + 4 stage modules), data/ (public aggregates),
manifest.json (SHA256 of every file).
No raw messages, row IDs, scores, models, or credentials.
Static/schema checks only; SAS runtime is executed by the user,
not claimed here.

## Run (SAS server)

Pull the approved checkout on the SAS server first:

    git -C /home/student/github pull --ff-only

(If the checkout lives elsewhere, use that path. Push is done
by main only.) Then submit exactly two lines in SAS:

    %let projroot = /home/student/github;
    %include "&projroot./followup_20260921_v1/sas/00_RUN_FOLLOWUP_20260921.sas";

Each run creates outputs/run_<UUID>/. Return the whole run folder
unmodified: run_status.txt, followup_summary.html, the four stage
logs, the stage HTML reports, and kisa_verified_readback.csv.
