# One operator-owned candidate qualification

This is a separate tool-only admission path, not a subject/mod workflow. Ordinary
orders never select executable code. The operator independently verifies a direct
human instruction and exact tool scope before using this path. No command here
grants that authority or clears an existing hold.

All commands use the SAME `--root` and SQLite queue as Polygon. Never use a second
root, direct run.py invocation or global executor replacement as a workaround.
Candidate validation is offline; the implementation tests use a fake executor and
do not attest live Skyrim, headset hardware or the new candidate's correctness.

## Operator request

Prepare external JSON (paths relative to this request unless absolute):

```json
{
  "schemaVersion": 1,
  "kind": "tool-qualification",
  "id": "vr-candidate-qualification-1",
  "order": "order.json",
  "executor": "frozen-executor",
  "maximumActualGameStarts": 1,
  "maximumWallSeconds": 900,
  "deadlineUtc": 1900000000,
  "cumulativeActualGameStartsBefore": 123,
  "launchAccounting": {"path": "reviewed-accounting.json", "sha256": "ACTUAL-SHA256"},
  "reason": "Exact tool qualification scope independently reviewed",
  "verifiedBy": "Actual operator identity",
  "ownerAuthorization": {
    "threadId": "ACTUAL-OWNER-THREAD", "messageId": "ACTUAL-HUMAN-MESSAGE",
    "quote": "EXACT-SCOPED-HUMAN-INSTRUCTION", "verifiedBy": "Actual operator identity",
    "path": "owner-evidence.txt", "sha256": "ACTUAL-SHA256"
  }
}
```

The accounting JSON has cumulativeActualGameStarts (same integer), verifiedBy and
reason. Verify the actual cumulative counter independently; examples are not a
baseline. The order is a dedicated schema1 automatic qualification with explicit
testing boundary/checks/collection, active profile, no cycle and no exceptional
profile. Config paths must be absolute for relocation into frozen attempt files.
Only generic sequential scenarios are supported, without console/game tools,
restart selectors, physical probe kinds or postSteps. Owned save/load is allowed;
it is not a process restart. The candidate's validator and restart-budget planner
must accept the scenario with zero reserved restarts.

### A new qualification after an unresolved historical count

Historical uncertainty does not become zero or an observed minimum when the owner
authorizes a new bounded test. For that case only, set the request's explicit
`cumulativeActualGameStartsBefore:null`. Its separately pinned accounting review
must contain explicit `cumulativeActualGameStarts:null`,
`accountingStatus:"historical_unknown"`, nonempty `verifiedBy`/`reason` and
`historyPins:[{"path":"prior-packet.json","sha256":"ACTUAL-SHA256"}]`.
Paths in historyPins resolve relative to the accounting review. Each unique pin
must match a final packet registered in this same queue, with a supported
qualification packet kind and explicit `cumulativeActualGameStartsAfter:null`.
Missing fields, an empty history, invented/unregistered history, a known count or
changed packet bytes refuse registration or dispatch. The history and accounting
review remain pinned through collection and retained in the new result evidence.

The new attempt still requires its own current owner authority, no competing
holds/owners, exact native start accounting, one physical start at most and zero
reserved restarts. Its `actualGameStarts` records only that new attempt, while
both cumulative fields stay null even on success or a proven zero-start refusal.
A successful new qualification does not repair or qualify the historical run.
No counter epoch, history reset, automatic hold clearance or old-order release
is introduced. The existing integer-baseline behavior is unchanged.

Registration pins request, order, configuration, scenario, inputs, staged plugin
sources, fixture ESS/SKSE, owner evidence, accounting, host config and dashboard
Python source. It inventories all candidate files except Python bytecode/cache;
links/reparse points are rejected. Keep sources/configuration frozen through
collection/recovery. This code is explicitly being qualified, not accepted as a
globally qualified platform by the result itself.

## Safe ordering around a stale hold

1. Refresh native process/worker/profile, installation and durable ownership
   evidence. Independently verify current human authority and launch accounting.
2. `qualification-register <request.json>` registers the immutable plan and adds
   `qualification-<id>` to the SAME pipeline holds. It permits an existing
   unrelated hold, but refuses existing active job/session/retry/installation
   owners and unfinished qualifications. It never launches or clears anything.
3. `qualification-check <id>` validates config/scenario/restart budget in a fresh
   candidate process, without running/recovering/configuring the native runner.
4. Obtain separately scoped human clearance for the old hold, then use the
   existing `pipeline-clear <old-hold> <clearance.json>` protocol after refreshing
   safety evidence. The qualification hold MUST remain: ordinary queue dispatch
   stays blocked throughout. Do not release old batches or invoke `next`.
5. `qualification-run <id>` explicitly selects only this qualification. It
   refuses every other hold and any shared/installation owner, and atomically
   transitions prepared to running. It never selects from ordinary queues.

The parent freezes the plan and records dispatch intent before spawning a fresh
child. The child rechecks all pins, current authority, active profile and shared
ownership; records native admission once; imports only the pinned candidate;
uses the executor's native SessionMutex/preflight/guardian/restoration. It refuses
unfinished candidate-runtime sessions before automatic native recovery could
touch them. A bridge launch wrapper permits one launch request and rejects a
second or expired request; scenario restart slots must be zero. Counting still
uses distinct owned native game identities, never launcher PID/request counts.

The parent waits at most 900 seconds (or the earlier authority deadline), kills
and waits only for its exact child on timeout, and retains the shared hold while
the independent native guardian restores. Safe restoration may finish after the
test authority expires. Timeout never admits another attempt or clears ownership.

## Collection, uncertainty and recovery

For ended and tracked-restored execution with unresolved exhaustive accounting,
the separate explicit [held diagnostic recording](qualification-held-diagnostic.md)
can finish collection without clearing the genuine hold or inventing a count.

`qualification-collect <id>` verifies native done/restored/result and archived
nonempty copied profile/removal, calculates cumulative real game starts, retains
raw manifests and projects declared test coverage into a separate packet. Input,
tool and host pins are rechecked; final packet and evidence hashes are verified on
subsequent reads. Requested data remain unassessed pending tool-chat analysis.
Raw execution success alone is not a qualification claim. No automatic app or
ledger message, outbox entry, tested mod label or provider activation is generated.
After factual start/end/restoration/collection, the operator may return the final
tool report to its exact tool origin under existing human messaging authority.

A child that ended before native admission has a zero-start diagnostic packet and
no factual test notification. After admission, absent/ambiguous native accounting
is unknown, never zero. More than one run, unverified ownership/restoration/archive,
missing child completion or multiple real starts retain the running barrier.

`qualification-recover <id>` invokes recovery in a fresh pinned candidate process
only after the exact worker has ended (recorded child exit, or exact native worker
identity verified dead). It refuses live/unknown workers and foreign unfinished
candidate sessions, uses the native mutex, never launches, and then recollects.
The specific admitted missing-loader refusal with no native state has a separate
explicit [pre-native reconciliation and finish](pre-native-qualification.md).
It requires original source exports, reviewed accounting/control flow, either a
real protected baseline or exact audited write-free source-prefix proof, and
fresh ownership/safety checks. Current inventory is never a historical baseline. Missing proof
retains uncertainty; this is not a general failed-qualification release.
`recover-active` points to qualification collection rather than ordinary recovery
while a qualification is running. No generic timeout takeover is provided for an
unknown worker or unproven admission with no native state; those require review.

The qualification lease persists after recorded completion until the operator
explicitly finishes this planned reservation. It cannot be cleared while
prepared/running. A successful test needs no second human authorization solely
to finish its own ordinary reservation: use
`qualification-release <id> <technical-review.json>`, never automatic cleanup.

```json
{
  "schemaVersion": 1,
  "kind": "tool-qualification-release",
  "qualificationId": "vr-candidate-qualification-1",
  "packetSha256": "ACTUAL-REGISTERED-FINAL-PACKET-SHA256",
  "verifiedBy": "Actual operator identity",
  "summary": "Technical review of the exact successful packet and collection",
  "successfulResultReviewed": true,
  "collectionReviewed": true,
  "nativeCompletionReviewed": true,
  "restorationReviewed": true,
  "archiveReviewed": true
}
```

The review is operator technical evidence, not fabricated human approval. The
release command requires recorded status, successful factual testing and all
required assertions, exactly one actual game start, no collection findings, normal
successful child exit, exact dead worker/owned identities, no current game/loader,
verified restoration, unchanged collected profile archive/removal, and final
packet/evidence hashes. Older packets without pinned archive inventory remain
held for review; no retrospective evidence is fabricated. Native mutex and SQLite
write transaction serialize the final checks and removal of ONLY this reservation.

A declared non-asserting `observe:true` step with a required `tooling` role may
be reviewed as its actual native `observed` result for reservation completion.
For example, capture-provider discovery does not assert visual capture quality.
Such observations never satisfy subject/fixture assertions or missing/unknown
checks. Their original incomplete/unavailable coverage projection stays unchanged
in the packet; normal completion does not turn them into passed tests.

It refuses any other hold or active owner/installation, another pending
qualification, previously released ordinary waiting jobs, cycle-bound waiting
jobs, queued retries/shared sessions, and unfinished native sessions in either
candidate or configured host runtime. It calls no next/run/recovery, releases no
batch, modifies no foreign hold and activates no provider. Unreleased ordinary
orders stay unreleased. Exact repeat reviews are idempotent; altered reviews are
refused. Successful release marks this reservation released and retains the
packet, accounting and immutable review. It never refreshes the start allowance.

This normal finish path does NOT apply to the old stale hold or any genuine or
uncertain recovery hold: those retain their existing independent owner-reviewed
clearance protocol. Failed, incomplete, timed-out or ambiguous qualifications
also stay held. Do not clear the qualification reservation together with the old
hold. `qualification-run` on the same id remains refused after completion/release.

Artifacts: `local/skyrim-polygon/qualifications/<id>/`; plan is also immutable in
the qualifications SQLite table. `qualification-show` and `pipeline-status` expose
the admission/lease status. This protocol changes no global host configuration.

## Abandon a reservation refused before dispatch

`qualification-abandon-prepared ID REVIEW.json` retires only an unstarted
`prepared` reservation with null expiry/packet, no attempt row, no native or
qualification dispatch artifacts, and an empty candidate runtime. This covers
an input-pin refusal before `qualification-run` changes the row to running,
including MO2 normalizing profile files while it closes. An outer operator
intent alone does not prove native dispatch. Its original files remain intact.

The review is schemaVersion1, kind `qualification-prepared-abandon-review`,
with exact qualificationId, verifiedBy, reason, actual ownerAuthorization and
true noDispatchReviewed, zeroStartsReviewed and installationSettled. Bind
preparedRequestSha256 to SHA256 of the unchanged stored request's UTF-8 bytes.
The pinned executor must remain unchanged. Under its native mutex and a SQLite
write transaction the command verifies a complete no-game inventory, no active
owner or unfinished host session, and no previously released/eligible work that
could become runnable. A child/attempt, run artifact, ambiguity or changed
reservation refuses abandonment; use the ordinary recovery path instead.

The terminal `abandoned` row preserves its original request and null packet.
An event retains the review/hash and zero actual starts; the cumulative baseline
is unchanged, including null. Only its own routine reservation is removed;
other holds and queues remain untouched. No pass, qualification, retry, fresh
allowance or new launch follows. Reusing that id cannot dispatch it again. Any
future reservation needs a fresh id, current frozen inputs and its own ordinary
reviewed authority.

Registration recognizes a historical `abandoned` reservation only through the
supported exact `qualification_prepared` -> `qualification_prepared_abandoned`
audit, unchanged stored-request hash, hash-checked original review/owner evidence,
zero-start and unchanged cumulative accounting, null expiry/packet, and no own
hold, admission or dispatch traces. A bare label, missing/changed/contradictory
proof or an unknown lifecycle remains a blocker. Recognition changes no old row,
event, file, allowance or result and cannot dispatch that identity again.

Historical proof is not a current launch approval: old input pins, candidate
source and unrelated later runtime contents need not remain unchanged forever.
The exact old qualification ID appearing in later native state still contradicts
its zero-start audit. Every new reservation keeps its own current owner authority
and ordinary active-owner guards. Empty folders alone never settle an abandoned
reservation; do not edit SQLite or manufacture an audit/review to unblock it.
