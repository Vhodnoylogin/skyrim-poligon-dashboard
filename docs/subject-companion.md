# Ordinary bounded file-plan subjects

`polygon-file-plan/1` is an explicit schema2 interface for a finite, reviewed
origin sequencer. It reuses the exact frozen executor's common initialized SE
game and existing interactive protocol. It does not introduce a game launcher,
replace the global host, rewrite an origin plan, or convert a tool qualification
into a subject result. Ordinary `polygon-actions/1`, legacy orders and
`platform-bind`/`execute-bound` retain their existing contracts.

The originating chat supplies the assertions and same-run actor handling in a
pinned Python module exposing `run(exchange, emit)`. The separately pinned
Autotest `tools/subject_companion.py` supplies the generic external transport.
It is maintained in Autotest, not copied into Dashboard or the frozen runtime.
The origin source is executable code: independently review its actual contents
and finite machine oracles before selecting it. File hashes are not a sandbox.
The sequencer must not launch/restart games, initialize startup, open audio,
write installed files, or bypass the supplied exchange function for game calls.

## Origin order

Use the normal automatic schema2 envelope, installed subject/dependency pins,
actual profile/origin, collection requirements and ordinary one-shot release.
The following replaces only `subjectPlan` and `testing`:

```json
{
  "subjectPlan": {
    "interface": "polygon-file-plan/1",
    "fixture": {"cell": "QASmoke", "startMode": "new-game"},
    "plan": {"path": "C:/Bench/origin/plan.json", "sha256": "ACTUAL_SHA256"},
    "sequencer": {"path": "C:/Bench/origin/sequencer.py", "sha256": "ACTUAL_SHA256"},
    "checks": ["catalogs", "male-core", "female-core", "clear-resume"],
    "maximumSeconds": 1200
  },
  "testing": {
    "start": {"kind": "check", "name": "catalogs"},
    "checks": [
      {"name": "catalogs", "role": "subject"},
      {"name": "male-core", "role": "subject"},
      {"name": "female-core", "role": "subject"},
      {"name": "clear-resume", "role": "subject"}
    ]
  }
}
```

The example is a fragment, not a runnable order. Use actual lower-case SHA256s.
Both plan and sequencer must also appear in `inputs` with role `fixture`.
The origin's `checks[].name` (subject roles) or legacy `cases[].id`,
`subjectPlan.checks` and `testing.checks` must have the exact same nonempty,
unique order. If both origin lists exist, both must agree. The first check is the factual subject boundary.
The origin's `bounds.maximumSeconds` must equal the explicit window in 1..1200.
No case count, actor count or mod name is hardcoded. A revised inventory receives
a new immutable plan/sequencer/order; historical plans remain unchanged.

The sequencer sends existing schema1 interactive envelopes and emits the
documented `check-start`, `measurement`, `assertion` and `check-result` records.
Native Bool admissions and command ACKs are receipts, not business assertions.
Only repeated reads may poll, within the original action/case/session deadline.
Unknown mutation outcomes stop without repetition. References come from actual
same-run fixture creation results and registry witnesses; never adopt an old NPC
or guess a dynamic reference. Rendered appearance remains unavailable without
actual captured/inspected evidence.

## Operator selection

Register a separate selection, after independently reviewing the current human
request, origin source and exact sole preparation hold:

`python polygon.py --root HOST companion-bind SELECTION.json`

```json
{
  "schemaVersion": 1,
  "kind": "operator-subject-companion",
  "orderId": "exact-new-subject",
  "subjectOrderSha256": "ACTUAL_CANONICAL_STORED_ORDER_HASH",
  "executor": "C:/Bench/frozen-rc6/portable",
  "configuration": {"path": "C:/Bench/operator/config.json", "sha256": "ACTUAL_SHA256"},
  "transport": {"path": "C:/Bench/operator/subject_companion.py", "sha256": "ACTUAL_SHA256"},
  "qualificationId": "exact-released-se-core-qualification",
  "baselinePacket": {"path": "C:/Bench/baseline/packet.json", "sha256": "ACTUAL_SHA256"},
  "holdId": "exact-current-preparation-hold",
  "subjectCapabilitiesUnderTest": true,
  "verifiedBy": "accountable independent operator",
  "reason": "Exact current subject; baseline proves core startup and ownership only",
  "ownerAuthorization": {
    "threadId": "ACTUAL_CURRENT_OWNER_THREAD",
    "messageId": "ACTUAL_CURRENT_HUMAN_MESSAGE",
    "quote": "ACTUAL_REQUEST",
    "path": "C:/Bench/operator/owner-evidence.txt",
    "sha256": "ACTUAL_SHA256",
    "verifiedBy": "independent verification"
  }
}
```

Selection never launches. The released baseline must retain its successful
single-start native packet, complete collection, restored/ended exact worker and
owned identities, archived/removed copied profile and unchanged executor bytes.
Its historical owner evidence does not supply current subject permission. The
new selection/admission must match the current ordinary release's actual human
evidence. The baseline row/packet remains historical and released.

Only `runtime` and `interactive_session` may differ from the normalized baseline
configuration. Inside `interactive_session`, only `maximumSeconds` and
`nativeBindings` may differ. Every other setting, including channel, source,
allowed tools, provider/staging/extra-file pins, ownership, guardian and shutdown
flags, must match exactly. The separate expanded binding policy is reviewed data
whose installed metadata/admission/business behavior is under test; it is not
declared qualified by an earlier Alvor/race probe. This route supports SE with
explicit native New Game, no Root Builder or profile reuse, and one first solo
attempt. Cycles, shared sessions and checkpoint reconnect are unsupported. The
strict zero-native continuation below is the only supported subsequent attempt.

## Reviewed atomic execution

**The following command launches the one ordinary subject game:**

`python polygon.py --root HOST companion-execute REVIEW.json`

The exact review has `schemaVersion:1`,
`kind:"operator-subject-companion-admission"`, `orderId`, `binding` (selection
path/hash), `baselinePacket` (the same registered pin), `ownerAuthorization`,
`verifiedBy`, `reason`, and these five explicit true fields:
`preparationReviewed`, `restorationReviewed`, `archiveReviewed`,
`exactOnlySubjectReviewed`, `subjectCapabilitiesUnderTest`.

Under the native session mutex and one SQLite transaction it verifies the exact
sole preparation hold, sole released queued target, current human release,
deadline, profile and input hashes, no other active/released/cycle/retry/shared
work, no live/unknown baseline identities or game/VR processes, and no unfinished
known runtime. It removes only that hold and claims only that target. Authorization
is rechecked on the same connection after the uncommitted removal; a refusal rolls
back both changes. Other readers still see the hold and queued target until commit.
An identical repeated review never launches again. A crash after claim leaves a
running recovery barrier. Normal `next` always skips file plans, even if their hold
was independently removed. There is no old-global-VR dispatch interval.

The fresh child freezes/rechecks the selected configuration, unchanged runtime,
client, origin sources, owner evidence, baseline and Dashboard source. Its original
main thread calls the normal runner, retaining the one mutex/guardian/bootstrap.
A finite companion thread waits for that exact run's interactive readiness, then
launches only the pinned data client with exact worker/game/session identity.
Startup wait is bounded to 600 seconds; the game/client keeps the declared finite
interactive window. No microphone, second game or per-subject startup code runs.
The transport process has its own retained `Popen` handle: PID, birth and image
path are read from that same handle, and a separate read-only retained handle
records the actual exit code/UTC observation after wait. Dispatch records its
argv, source pin, identity, timeout and exit evidence. A deadline may terminate
only that owned client handle once, never a game or a process selected by PID.
Collection independently reads a fresh complete native inventory for the client
and any declared inner sequencer child. A same PID with unavailable identity or
the same birth still blocks; proven absence or different birth proves the old
process ended. Unavailable telemetry cannot be reported as exit0 or a crash.

## Evidence and results

`orders/ID/subject-companion/` retains dispatch status, client log, final report
and hashed raw requests, receipts, native-delivery rows, completions, origin
assertions and results. Large raw results remain exact hashed JSON evidence.
The collector verifies exact order/attempt/run/session/binding/worker/game,
source/checklist pins, owned evidence paths, current native log rows and hashes.
It requires the first case's prior origin `check-start` followed by its matching
actual `interactive-action-delivered`. Readiness and ACK alone cannot start a
subject test. Missing, replayed or changed evidence retains a tooling hold.

The packet adds `subjectCompanion` and all verified evidence pins. Native
`result.json` and raw core checks are left intact. Final projection reports core
readiness as tooling and the exact origin case verdicts as subject coverage.
A known assertion mismatch may produce helper exit0 and normal game finish:
the failed case still yields `tested_with_errors`, with the remainder not run.
A transport/native uncertainty, nonzero helper exit or incomplete helper is a
tooling fault and retains a hold; it never becomes an automatic retry.

Normal owned finish, process/start accounting, restoration, profile archive/removal,
collection, final report and exact-origin notification gates still apply. Source
tests and a prepared order do not constitute a completed CLAW mod test or authorize
another launch. This development integration starts no game and changes no live
database, installation, listener or external application.

## Reviewed zero-native continuation

A confirmed refusal before any platform plan, worker, native session or subject
action may use one separate `companion-pre-session` attempt. It cannot reopen,
requeue, clone or reset the original job. Its blocked packet, admission, order,
input hashes and factual zero-start history remain unchanged. A run that reached
native dispatch or factual subject start is ineligible for this route.

The exact ticket has `schemaVersion:1`, `kind:"companion-pre-session"`, distinct
`id`, original `orderId`, `previousPacketSha256`, and pinned `technicalAbort`,
`ownerAuthority`, `companionSelection`, `previousAdmission` and `repair` files.
Its `authorityReview` contains `verifiedBy`, `reason`, `retryPermitted:true`,
`maxAdditionalAttempts:1`, `subjectActualLaunchesBefore:0`,
`maximumSubjectActualLaunches:1` and the unchanged `originalDeadlineUtc`.
This consumes the original unused launch; it does not extend owner authority or
reset historical global/edition start accounting. The actual original release
owner and finite deadline must still match at admission and native dispatch.

The technical review must pin the original refusal and manager-restoration/idle
evidence, explicitly establish `preSessionUntouched:true`, no platform plan or
worker material, no attempt rows and no matching runtime. Repair evidence binds
the complete current operator source inventory and retained tests. Runtime,
client, subject, initial fixture and all inputs stay pinned; a code repair is
not fresh native qualification or evidence that the mod passed.

1. `retry-register TICKET.json` registers the separate attempt under the genuine
   predecessor hold. It never launches or clears that hold.
2. `companion-pretest-admit REVIEW.json` independently verifies the ticket,
   current owner scope, repair, zero-native proof and idle environment. Under the
   native mutex and one database transaction it removes only that genuine hold
   and sets only the new retry attempt to `running`. It does not launch. There
   is no hold-free queued interval for an older global dispatcher to claim.
3. `companion-pretest-run ATTEMPT-ID` dispatches that exact admitted attempt
   once. A durable dispatch marker and native attempt marker reject repetition.

The admission review uses `kind:"operator-companion-pre-session-admission"`,
`schemaVersion:1`, `attemptId`, exact ticket path/hash, current
`ownerAuthorization`, `verifiedBy`, `reason`, and true `zeroNativeReviewed`,
`preSessionUntouchedReviewed`, `restorationReviewed`, `repairReviewed` and
`unusedStartReviewed` fields. Other active, released or queued owners, changed
history, expired authority and unfinished native sessions retain the barrier.

The new frozen plan, helper output, packet and final report live under the
distinct `retry-attempts/ATTEMPT-ID` directory. The native order keeps the
unchanged subject ID and adds exact `attemptId` and `subjectOrderId`; the command
client receives the separate attempt ID. The collector requires this attribution
and registered proof, and refuses an old report, old run or foreign attempt.
The normal bootstrap, one game owner, factual subject boundary, per-case
assertions, process-exit evidence, restoration and final-report gates remain.
Any unknown outcome remains terminal for automatic execution; this contract
does not provide an additional restart, checkpoint resume or automatic retry.

## Collection repair for an already ended failed attempt

An ended, restored attempt still collects and hashes its nonempty profile archive
when its valid companion report is incomplete or uncertain. Such a report remains
a confirmed transport/tool interruption with its original partial case results;
uncertainty does not make already verified receipts or assertions disappear.

An older packet that omitted the archive manifest can use
`companion-collection-repair ATTEMPT-ID REVIEW.json`. This command never starts,
recovers or replays a game/action, changes a launch budget, replaces a packet or
clears a hold. It adds immutable files only below that same retry attempt's
`collection-repair/` directory. Original packet bytes and every old evidence file
must still match their retained hashes.
If the original packet never pinned archive files, the supplement explicitly
records a newly reviewed current inventory. It establishes no historical archive
hash or membership continuity. Later changes are checked against these new pins.

The review uses `schemaVersion:1`, `kind:"companion-ended-collection-repair"`,
`attemptId`, exact pins for `packet`, `platformPlan`, `state`, `result`,
`childExit`, `companionReport`, a complete `profileArchive` record, current
`implementationPins`, `verifiedBy`, `reason`, and true `endedReviewed`,
`restorationReviewed`, `archiveReviewed`, `uncertaintyRetained`, `retainHold`.
The repair checks the exact run/attempt, consumed physical start, ended worker
and owned processes, actual restored target hashes, removed temporary profile,
archive membership and verified partial companion data. It retains reviewed
collection source snapshots and, when recording, independently checks native
process death, the live restoration targets, idle ownership and the fault hold.

Verification exposes an in-memory packet view with the supplemental archive and
source pins. The old raw packet stays unchanged. The final report pins both
`originalPacket` and `collectionRepair`; later verification rechecks both and the
actual archive. Existing factual-start, ended/restored/collected and exact-origin
notification gates remain mandatory. The genuine tooling-fault hold remains.
Historical verification uses the pinned recording proof, original source bytes
and stored copies, closed native/companion evidence and archive inventory. It
does not require today's collector source tree, global idle state or the old
hold to remain unchanged after a separately authorized successor takes ownership.
Adding current modules never replaces or weakens the original frozen proof.

A nonzero process exit is retained as an observation with unknown cause. A game
observed running before cleanup and exited later must not be relabeled as normal
close, a mod assertion failure or proof that the earlier metadata fault was caused
by that exit. Correcting a future binding declaration supplies no extra launch
authorization and does not change this failed attempt's evidence.
