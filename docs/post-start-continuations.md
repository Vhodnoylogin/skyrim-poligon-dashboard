# Reviewed tooling continuation after subject start

Tags: testing, tools

`continuation-register` is the narrow counterpart to pretest `retry-register`.
It registers one separate full replay of the same immutable standard automatic
schema2 subject after a confirmed tooling failure **after factual subject start**.
It never reopens/requeues the original, clones a mod order, changes installed
subject pins, advances mod iteration/build progress or merges passing coverage.
The old packet, final report (including delivered reports), platform plan and
checks remain historical. A mere failed subject assertion is ineligible.

## Review before registration

The operator independently verifies current real human authority and its scope,
deadline, cancellation, limits and restoration/installation state. An existing
instruction may authorize this tooling repair/continuation; no new owner request
is needed when that actual instruction already covers it. Hashes and review flags
are evidence bindings, not authentication of human permission.

Require the predecessor's verified packet and already registered final report:
factual start, ended collection, native done/restored/no restoreErrors, exact native
order/attempt identity and unchanged subject. A completed shared member may be
replayed alone only after the whole shared session is complete; other members are
not replayed. Orders with a cycle field retain their single-origin slot contract
and are refused. An externally orchestrated bounded full cycle with a standard
schema2 order is supported; registration never reopens a stopped cycle/slot.

Require a separately pinned reviewed tooling-failure proof with native state and
result pins from the predecessor packet. Eligibility needs a mechanically
projected operational/tooling interruption or an exact failed raw check with
`reason` beginning `Tool request failed:` and null/absent observation. The latter
is a request failure, not proof that a subject assertion was false. The operator
must still diagnose and confirm the tooling fault and its repair. No old report's
subjectMismatchObserved/coverage is retrospectively reclassified or erased.

Select the currently qualified repaired platform, with exact provider/executor,
mapping/configuration/evidence pins. Registration/dispatch binds the selected
manifest; full qualification is rechecked in preparation and native dispatch.
An unqualified or changed platform cannot launch. Do not activate a candidate
platform merely to prepare this ticket. Operator qualification/activation remains
separate from source development.

## Ticket

All top-level pin paths resolve from the ticket; proof-native paths below are
absolute exact packet paths. IDs use the existing safe-id format. The following
is an intentionally incomplete example, not launch authority:

```json
{
  "schemaVersion": 1,
  "kind": "post-start-tooling",
  "restartMode": "initial-fixture",
  "id": "subject-tool-continuation-1",
  "orderId": "ORIGINAL-IMMUTABLE-SUBJECT-ID",
  "previousPacketSha256": "EXACT-PREDECESSOR-PACKET-SHA256",
  "previousReport": {"path": "REGISTERED-FINAL-REPORT", "sha256": "ACTUAL-SHA256"},
  "technicalFailure": {"path": "reviewed-failure.json", "sha256": "ACTUAL-SHA256"},
  "launchAccounting": {"path": "reviewed-launch-accounting.json", "sha256": "ACTUAL-SHA256"},
  "ownerAuthority": {"path": "actual-owner-authority.json", "sha256": "ACTUAL-SHA256"},
  "platform": {"path": "CURRENT-QUALIFIED-MANIFEST", "sha256": "ACTUAL-SHA256"},
  "authorityReview": {
    "verifiedBy": "ACCOUNTABLE-OPERATOR",
    "reason": "Actual owner instruction permits this one post-start tooling replay",
    "retryPermitted": true,
    "postStartContinuationPermitted": true,
    "fullReplayReviewed": true,
    "preservePriorCoverage": true,
    "maxAdditionalAttempts": 1,
    "cumulativeActualLaunchesBefore": "REPLACE-WITH-CURRENT-REVIEWED-INTEGER"
  }
}
```

`ownerAuthority` uses the existing retry schema: explicit state=active, exact
orderIds (or roster IDs), ownerAuthorization with threadId/messageId/quote/
verifiedBy/path/sha256 of actual human evidence, and any current deadlineUtc.
The evidence quote must actually be present; scope and current intent are reviewed
by the operator. No authority document is fabricated by source development.

`technicalFailure` JSON requires schemaVersion=1,
classification=`confirmed-tooling-post-start-failure`, exact orderId,
packetSha256, reportSha256, run, subjectStarted=true, done=true, restored=true,
restoreErrors=[], collectionFinished=true, nonempty verifiedBy/reason, and
evidence=[{path,sha256},...] containing both exact pinned state.json and result.json.
For a failed tooling request supply failedCheck={name,reason} matching exactly one
failed native check with null/absent observation. This cannot substitute a guessed
name or an ordinary assertion failure. A separately proven technical interruption
can qualify without failedCheck. For a successor include exact attemptId.

`launchAccounting` JSON requires schemaVersion=1, orderId, previousPacketSha256,
previousAttemptActualLaunches, cumulativeActualLaunches, verifiedBy and reason.
Counts are integers; cumulativeActualLaunches must exactly equal the ticket review.
The native predecessor count must match distinct captured owned game identities
(pid/birth/path) and its restart count. It must include initial launch and owned
restarts; loader/VR starts and queue rows are not game starts. For a successor add
previousAttemptId. Its cumulative baseline cannot be less than the previous
ticket baseline plus that predecessor's actual starts. Switching to pretest retry
cannot discard charges from a post-start continuation either.

For Body's 2026-10-08 retained attempt the native count was 6 and the historical global
baseline was 161. These are **not** the next ticket's current count: subsequent
qualifications/runs must be included. The operator rechecks current accounting
after qualification and before approving the ticket. Review records stay immutable;
a stale ticket is replaced by a new reviewed ID, not silently refreshed.

## Register and dispatch

```text
python <repository>/polygon.py --root <ROOT> continuation-register <reviewed-ticket.json>
python <repository>/polygon.py --root <ROOT> retry-show subject-tool-continuation-1
python <repository>/polygon.py --root <ROOT> next
python <repository>/polygon.py --root <ROOT> reconcile
python <repository>/polygon.py --root <ROOT> recover-active
```

`retry-register` still accepts only its original pretest ticket; this new ticket
cannot bypass that boundary. Both modes share the existing one-owner FIFO,
installation/shared-session barriers and single ended nonbranching attempt chain.
Identical registration is idempotent; changed content or reused IDs is refused.
Later tickets need previousAttemptId naming the latest ended retry/continuation,
its exact packet/report and explicit new accountable review. No automatic reticket.

Registration can retain a queued ticket while a hold is active, but cannot clear
the hold or launch. Only the operator's existing supported owner-reviewed clearance
can remove a resolved hold; independent blockers remain. Dispatch rechecks human
authority/cancellation/deadline, scope, inputs, predecessor, current qualification,
source profile, materialized full scenario and ownership. Authority/holds are
checked again at final admission. Each child is admitted once.

The new native attempt replays every original semantic step from the original
fixture. No skipping a stateful prefix, using a previous attempt's save as a new
checkpoint or adding a resume index. Qualification must establish the original
fixture restoration on the repaired platform. A checkpoint-based resume requires
separate origin-authored reproducibility and semantic review and is unsupported.

## Results and accounting

Dispatch-time raw bytes of technical proof, predecessor report, launch accounting,
owner authority and platform manifest are frozen under retry-attempts/<id>/review-*.json
and hash-pinned in the new packet. Later cancellation does not rewrite historical
review evidence. Missing/corrupted frozen evidence refuses packaging/delivery.

The new packet/final report carries attemptKind=post_start_tooling,
restartMode=initial-fixture, previousReportSha256 and launchAccounting:
cumulativeActualLaunchesBefore, attemptActualLaunches, cumulativeActualLaunchesAfter.
After equals the reviewed baseline plus concrete native game identities, including
restarts. The board exposes this accounting separately. It does not reset or
overwrite an external global counter; operator accounting reconciles these charges
with qualification/other authorized runs. Unknown actual starts, incomplete native
ownership/restoration or admitted workers without native evidence retain the barrier;
they cannot be recorded as zero. Preparation closed before admission records zero.

Use existing report-ready with attemptId, summary, collectionFinished=true and
dataCoverage for every requested item. End/restoration/pinned evidence checks
remain mandatory. Only this attempt's checks/data determine its outcome; earlier
passes cannot fill missing checks. Return eligible final reports to the unchanged
exact sourceThreadId via outbox/delivered. A continuation that never factually
starts notifies no origin and is never labelled tested. Retain prior reports and
their receipts; each distinct attempt has its own delivery/deduplication identity.

Installing this code prepares no actual ticket, registers no live queue work,
activates no platform, clears no hold, launches no game and messages no other mod.
