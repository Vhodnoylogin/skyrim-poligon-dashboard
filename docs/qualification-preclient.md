# Collect an ended pre-client transport refusal

`qualification-record-preclient ID REVIEW.json` is a collection-only operation.
It never launches, recovers, restarts an endpoint, retries a command, clears a
hold or refreshes owner authority/start allowances. Use only for an exact admitted
companion qualification whose client stopped with ConnectionRefusedError before
adopting its run/session/binding or starting an inner sequencer. Other failure
shapes remain on their existing collection/recovery paths.

The explicit operator review contains schemaVersion1,
kind `qualification-preclient-review`, qualificationId, verifiedBy, summary,
true nativeCompletionReviewed, restorationReviewed, archiveReviewed,
preclientFailureReviewed and retainHold. Pin exact path/SHA256 pairs for plan,
state, result, report, dispatch, childExit and worker. Include the exact current
`qualification_preclient.implementation_pins()` and the nonempty profile archive
inventory returned by `qualification_diagnostic.archive_inventory()` as
profileArchivePins/profileArchiveDirectories. The operator reviews these facts;
a template or peer message is not a completed review.

Recording independently verifies the unchanged original plan/executor/input pins,
worker/game/client identities and actual argv, retained exit2, empty client events,
actions/evidence, original cases all not_run, absent report run/binding/inner
identity fields, and exactly one native delivered owner finish. Common startup
and native completion/restoration/collection must have ended successfully. It
checks all tracked restored targets against original backups, the archived and
removed copied profile, one consumed actual game start and fresh complete native
proof that the worker/client/owned identities ended with no current game.

The immutable `preclient-diagnostic/packet.json` records the native attribution
basis separately. It does not fill the missing fields in the raw client report,
invent completed cases or conflate the passed core startup with nine unrun cases.
It records qualificationOutcome:not_conducted, each component:not_run, one actual
start and the unchanged known/unknown cumulative baseline. The original hold
remains. Normal qualification release and baseline acceptance refuse this kind.

Original installed input bytes are copied and pinned under original-inputs so a
separately reviewed installation rollback does not invalidate the historical
proof. Raw plan/dispatch/report/native files are unchanged and retained. Cached
collection rechecks every retained hash, original prefix and archive membership;
it does not re-run current recovery or confuse a later installation with the
recorded restoration proof. Historical accounting may retain this registered
unknown-total diagnostic without converting its cumulative count to zero.

A future test requires its own current, finite, independently reviewed admission
and exact repaired candidate; this command creates none. Old packets and launch
counts are never rewritten or reopened.

## Guardian-ended startup with no client

`qualification-record-startup ID REVIEW.json` is a separate, narrower prefix
case. Use kind `qualification-startup-review` and true startupFailureReviewed
in place of preclientFailureReviewed. Pin plan/state/result/childExit/worker;
there is no report or dispatch to pin or manufacture. All other review, source,
restoration/archive/death and hold-retention requirements above still apply.

This path accepts only an exact exit125 guardian-ended failed startup whose
prior phase is wait-devbench, se-native-startup-events or wait-task-queue. No
completed bootstrap, interactive owner, artifact/actor registry, command delivery
or later phase may exist. The helper folder must contain only the exact executor
manifest, consistent with the unchanged source's pre-readiness admission gate.
Partial client output, unknown processes, a successful client or another exit
shape refuse recording. It records qualification-startup-diagnostic, failed
native execution, zero component actions, every original case not_run and one
consumed start. ownerFinishCommandId remains null; no client/report fields are
invented. Normal release refuses the kind. Its recorded unknown-total history
may be retained by a separate new qualification without resetting that history.

## Native bootstrap failure before client admission

The same `qualification-record-startup` command also supports a separately checked
exit1 prefix. The native run must be failed, ended, restored and collected, with
an exact independently observed nonzero game exit. Common startup may have reached
New Game or fixture-cell preparation, but the initial world must remain incomplete:
no completed bootstrap, anchor attempt, interactive owner, delivered command or
interactive readiness is accepted.

For this prefix the helper directory must contain exactly executor-manifest.json
and dispatch.json. Dispatch must contain only schemaVersion, exact orderId,
qualificationId and worker. Any client intent, identity/PID, nativeRun admission,
returncode/error, report, client log, inner identity or events refuses this path.
A missing report after possible client admission is never evidence of not_run.

The startup operator review additionally pins dispatch and endedTechnicalReview.
That independent ended review binds the qualification/run, worker exit1, observed
game exit, zero component actions, all original cases not_run and the exact initial
dispatch. Its rawPins inventory must include plan/worker/child exit, manifest,
dispatch, native state/result/steps; every listed hash is checked at recording and
cached collection. Current implementation pins, original source/input pins,
restoration/backups, archive/removal and fresh process-death checks still apply.

The existing startup diagnostic records startupFailureMode:native-failed-before-client.
It creates no client report, identity or action and grants no launch authority.
Release remains refused; the original hold, consumed start and unknown cumulative
baseline remain intact. Guardian exit125 retains its original narrower checks.
