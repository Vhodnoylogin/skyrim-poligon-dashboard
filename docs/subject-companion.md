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
attempt. Cycles, shared sessions, retries and checkpoint reconnect are unsupported.

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
