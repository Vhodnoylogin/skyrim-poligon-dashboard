# Tooling-only pre-subject continuation

An ended attempt is never reopened. retry-register creates a separate one-shot
attempt ticket referencing the same immutable schema2 subject order. It creates
no new mod order, changes no installed pins/scenario, resets no budgets and sends
no preparatory origin message. This is an explicit operator repair protocol,
not an automatic retry policy or permission supplied by a tool finding.
For a confirmed tooling failure after factual subject start, use the distinct
reviewed full-replay [post-start-continuations.md](post-start-continuations.md)
protocol and continuation-register. The pretest command and proof stay unchanged.

## Verify authority and predecessor

The operator verifies the actual human permission and its current scope/bounds.
Pin a separate authority document with ownerAuthorization (threadId, messageId,
quote, path/sha256 of the human evidence, verifiedBy), exact orderIds or roster,
and active state. Optional deadlineUtc remains enforced. The ticket's accountable
authorityReview explains why that existing instruction permits this single extra
tooling attempt; flags and hashes alone do not authenticate human authority.
Set maxAdditionalAttempts=1 and retain the externally reviewed cumulative actual
launch count. Registration and replay cannot refresh this authority or counter.
No stopped cycle, shared hold or partially installed slot is automatically cleared.

The prior packet must hash-verify, bind the unchanged subject specification and
prove a declared factual boundary that was not reached. Its actual native state
must prove done/restored/no restoration errors and exact execution identity. A
pinned reviewed technicalAbort must identify the subject, packet hash, run,
classification=confirmed-tooling-pretest-abort, reason, subjectStarted=false,
done=true, restored=true, and no restoreErrors. A pre-session refusal with no run
instead requires actualGameLaunches=0 and evidence that no native run began.
An already-started mod test, changed subject, uncertain recovery, unqualified
platform or missing human authority is not eligible.

The platform pin names the currently selected platformManifest. Full exact-build
qualification, input identity and current source-profile selection are rechecked
before native dispatch. Updating tools never changes the original subject order
or its old platform plan. Each retry has a new frozen platform_attempts entry.
Registration alone does not claim live qualification or launch the game.

## External ticket and commands

```json
{
  "schemaVersion": 1,
  "id": "mod-tool-retry-1",
  "orderId": "ORIGINAL-SUBJECT-ORDER-ID",
  "previousPacketSha256": "EXACT-PREDECESSOR-PACKET-SHA256",
  "technicalAbort": {"path": "reviewed-abort.json", "sha256": "ACTUAL-SHA256"},
  "ownerAuthority": {"path": "owner-authority.json", "sha256": "ACTUAL-SHA256"},
  "platform": {"path": "qualified-platform-manifest.json", "sha256": "ACTUAL-SHA256"},
  "authorityReview": {
    "verifiedBy": "ACCOUNTABLE-OPERATOR",
    "reason": "Verified existing owner instruction permits this one tooling continuation",
    "retryPermitted": true,
    "maxAdditionalAttempts": 1,
    "cumulativeActualLaunchesBefore": 34
  }
}
```

```text
python <repository>/polygon.py --root <ROOT> retry-register <ticket.json>
python <repository>/polygon.py --root <ROOT> retry-show mod-tool-retry-1
python <repository>/polygon.py --root <ROOT> next
python <repository>/polygon.py --root <ROOT> reconcile
python <repository>/polygon.py --root <ROOT> recover-active
```

Paths resolve from the ticket. Identical registration is idempotent; changed
content for that id is refused. A later tooling-only failure needs a new reviewed
ticket and previousAttemptId naming the latest ended retry, plus its exact packet
and technicalAbort.attemptId. Branches, active predecessors and reuse of ended
attempt ids are refused. All dispatched attempts remain in attempts alongside
the original; the subject's build/iteration/progress record is unchanged. The
reviewed cumulative physical-launch counter is retained, not replaced by queue
rows or dispatch counts; actual launch evidence remains in native state/logs.

Retries enter FIFO behind already released older work. One retry owner excludes
ordinary/shared launches, installations and unsafe clearance. Its child rechecks
proof, authority, source inputs, profile and frozen platform and is admitted once.
A repeated child cannot start another run. If worker completion is unproven before
a native run appears, recovery retains the barrier rather than assuming no game
can still start. Pre-dispatch preparation can be closed without launching. Owned
native runs use existing executor recovery and require verified restoration.

## Independent result and delivery

A retry packet has orderId=original and its distinct attemptId; the old raw packet,
request and platform plan remain unchanged. Original profile-selection evidence
is also preserved; retry preparation writes only into retry-attempts/<id>.
The board lists the continuation separately and identifies its original subject.

Finalize through report-ready using schemaVersion1,id,attemptId,summary,
collectionFinished=true and optional dataCoverage list of each original collection
item with status and pinned evidence (same semantics as ordinary final reports):

```json
{
  "schemaVersion": 1,
  "id": "mod-tool-retry-1-final",
  "attemptId": "mod-tool-retry-1",
  "summary": "Attempt ended and evidence verified",
  "collectionFinished": true,
  "dataCoverage": []
}
```

No data assessment means unassessed/incomplete, never successful testing. outbox
returns eligible retry reports with both orderId and attemptId and the original
exact sourceThreadId. Send that completed report once, then delivered <attemptId>
--note <verified-exact-target-app-receipt>. Repeated receipts preserve the first.
The usual factual-start/end, restored environment, evidence hashes, unavailable
coverage and same-origin successor gates apply. A second pre-subject tooling abort
is suppressed, not sent as a mod-test result. Detailed subject results go only to
the original mod chat; tool status/faults may use the owner's separately authorized
technical coordination channel.

## Supported boundary

This protocol supports standard automatic schema2 orders, including an unstarted
member of a fully ended/restored shared session. It does not replay other members,
merge their reports, restore arbitrary slots or reauthor retained schema1 orders.
Cycle-bound orders retain their existing single-origin slot/iteration contract and
are refused; a multi-origin installation/cycle-attempt migration is separate.
Actual human scope may be an externally orchestrated finite multi-mod workflow;
that is independent of whether the original order has a cycle field.

No live retry registration, service restart or game run follows from installing
this code or preparing an example ticket. Operator review/authority is required
for each actual dispatch. Shared tooling/recovery holds remain owner-reviewed.
