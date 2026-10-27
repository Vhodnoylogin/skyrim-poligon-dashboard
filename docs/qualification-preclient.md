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
