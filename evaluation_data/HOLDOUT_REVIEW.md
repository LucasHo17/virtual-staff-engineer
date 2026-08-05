# Holdout Review

`retrieval_holdout_v1.json` is a draft, separately labeled dataset for
validating retrieval changes selected with `retrieval_cases.json`.

Before changing its status to `frozen`:

1. Read every query without looking at retrieval output.
2. Compare it directly with `playbooks/evaluation_playbook.md`.
3. Confirm that every directly applicable rule is listed.
4. Confirm that negative cases truly have no policy answer in the playbook.
5. Set `reviewed_on`, set `reviewed_case_count` to `20`, explain resolutions,
   and only then change `status` to `frozen`.

Do not alter thresholds or fusion parameters after seeing holdout results. If a
new optimization is needed, create another versioned holdout rather than tuning
against this one.
