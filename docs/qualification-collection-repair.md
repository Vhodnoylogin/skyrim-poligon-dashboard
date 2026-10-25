# Qualification collection repair

This completion-only bridge supports one exact collector defect: a successful
native result with JSON `reason: null` reached `execution_summary`, which used a
string operation on that value. The sole accepted `polygon.py` change inserts
`reason = "" if reason is None else reason` immediately after that function's
docstring. Any other source change in that file refuses this bridge.

An explicit review uses `kind: qualification-collection-repair-review`, schema1,
`qualificationId`, nonempty `verifiedBy`/`summary`, and all five true flags:
`nullableSuccessReasonReviewed`, `nativeCompletionReviewed`,
`restorationReviewed`, `archiveReviewed`, `retainHold`. It supplies ordinary exact
path/SHA256 pins for `originalDashboardExport`, `worker`, `childExit`, `state`,
`result`, `observer`, plus current `implementationPins` and full
`profileArchivePins`/`profileArchiveDirectories`. The observer must be the already
reviewed strict native observer with SHA256 `ce57c40710921be46901daf19aa58f75c5f3990e24bc7899797ac9aa07182da6`.

Run from the Dashboard checkout with the explicit host root, exact qualification
identity and external review path:

```
python qualification_collection_repair.py --root ROOT --id ID --review REVIEW
```

The review must bind a complete original Dashboard export to the unchanged frozen
plan. Existing source-export validation preserves every original module, checks
all other original pins and the entire candidate inventory, and binds the current
implementation closure. The bridge additionally requires child exit0, exact dead
worker identity, one admitted actual game start, passed/done/restored native state
and result with an explicit null result reason (state reason absent or null), no restoration errors, removed temporary profile and
complete archive membership. It observes absence of all owned/worker/game/loader
processes under the strict native mutex and checks the current exclusive hold and
owner in a database transaction.

Only after those checks does it freeze current implementation files and observer
under `QUAL/collection-repair-implementation/`, then exclusively create the
immutable `collection-repair.json` review pointer. It invokes the normal collector.
The attempt plan, original source exports, executor, raw state/result and launch
accounting remain unchanged. No run, recovery, source-pin relaxation for execution,
status reset, game operation or hold release is provided.

The packet retains the review pointer, original exports, frozen repair
implementation and native completion/archive evidence. Cached packet reads verify
full archive membership from the immutable review, so later repository changes do
not invalidate a historical result. Collection success still does not release the
qualification reservation; the existing separately reviewed completion procedure
controls that step.

Offline tests: `python -m unittest test_qualification_collection_repair` exercises
exact patch scope and mocked proof guards for null versus missing/string result reasons,
failed/unrestored/unfinished state, wrong worker, nonzero exit, additional archive
members, changed owner, changed plan and extra game starts. No test launches a game.
