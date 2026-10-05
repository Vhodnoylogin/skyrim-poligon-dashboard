# Test results and notification eligibility

Queue lifecycle (`queued`, `running`, `recorded`, `blocked`, `delivered`), game
execution, testing outcome, coverage and delivery are separate facts. A game
process or loaded fixture is not proof that the order's testing began. `recorded`
means a raw packet exists; `delivered` means a verified notification receipt.
Neither means tested successfully. No final testing label appears before the
attempt has ended and collection/report checks have completed.

## Declare the factual testing boundary in new orders

Optional schemaVersion1 `testing` metadata is backward compatible:

```json
"testing": {
  "start": {"kind": "check", "name": "first actual subject check"},
  "checks": [
    {"name": "first actual subject check", "role": "subject"},
    {"name": "later required check", "role": "subject"},
    {"name": "observer quality check", "role": "tooling"}
  ]
}
```

The author defines the earliest factual subject-test checkpoint. For a mod test,
fixture loading and launcher setup normally precede it. For a control-chain test,
launch itself may be the subject: declare `start={kind:"event",event:"phase",
name:"start-skse"}` only if that exact logged event is the intended test boundary.
Automatic boundaries use raw result.checks or steps.jsonl events (`kind`, `name`).
Assisted boundaries use `start={kind:"observation",query:{tool:"inspect",args:...}}`
and require that exact query with a non-null response in observations.jsonl.
All checkpoint evidence must already be included in the verified raw packet.
Late/unpinned observations cannot retroactively establish start. Required check
names are unique and have explicit subject/fixture/tooling roles. Unknown roles,
duplicates and missing coverage never prove subject acceptance.

Older immutable orders remain readable/executable under their prior launch
authorization. They have no declared test-start contract: their reports are
conservatively not_started with startContractAvailable=false and notifications
suppressed. This means start is not proven, not a historical assertion that no
testing happened. Do not modify an old order or raw packet to add a boundary.
A new order requires its own existing owner launch/cycle authorization.

## Complete, restore, collect, finalize, then send

`finish` retains the raw schemaVersion1 packet and legacy executionOutcome.
New completions also log execution-summary.json, separating assertion_stop,
unexpected_process_exit, operational_interruption, normal_close and unknown.
Unexpected exit cannot distinguish a crash from external termination. These are
evidence projections from executor reasons/state, not new executor capabilities.
Original runner steps/state/result remain the source. Raw packets are immutable;
later notes use separate followups files instead of regenerating packets.

After the same-origin testing work finishes, the operator prepares an external
final-report request and runs `report-ready`. This creates a separate immutable
report, verifies raw manifests and identity, confirms execution done/restored,
and registers eligible or suppressed notification decisions. A still-running or
released queued same-origin successor/repeat defers finalization/delivery.
An interrupted un-restored session requires recovery before report finalization;
do not alter raw evidence to conceal failed recovery. No test start means no app
OR ledger message to the origin, no fake delivered state and no delivery receipt.
Cancelled, withdrawn and pre-test launch failures remain in files/on the board.

```json
{
  "schemaVersion": 1,
  "id": "mod-task-final-report-1",
  "orderIds": ["mod-build1-test1"],
  "summary": "Requested attempt ended; collected evidence verified",
  "collectionFinished": true,
  "dataCoverage": {
    "mod-build1-test1": [
      {"name": "EXACT collect item", "status": "collected",
       "evidence": [{"path": "EXACT VERIFIED PACKET FILE", "sha256": "ACTUAL SHA256"}]}
    ]
  }
}
```

Data coverage must list every requested collection item once when supplied;
statuses are collected/unavailable/not_collected. Collected entries require
references to already hash-verified packet files. The operator verifies semantic
data sufficiency; hashes alone do not establish that a requested measurement is
present. Missing assessment is unassessed and cannot yield successful testing.

```text
python <repository>/polygon.py --root <ROOT> report-ready <final-report-request.json>
python <repository>/polygon.py --root <ROOT> outbox
python <repository>/polygon.py --root <ROOT> delivered <order-id> --note "Verified exact-origin app receipt"
```

Only eligible final reports are in the outbox. The delivery command rechecks the
same gate and all hashes, so bypassing outbox cannot mark a premature notification
delivered. A duplicate delivery preserves the first receipt. Already historical
deliveries remain historical; they are not retroactively revoked or resent.
An origin notification contains ID, testing outcome and final-report path, with
raw-packet refs/hashes in the report. Detailed reports stay in files. The origin prepares checks, studies the completed report, fixes in-scope findings,
builds/installs when needed and prepares a new immutable order. These duties are
the same for manual and full-cycle testing; run count alone never requires renewed
repair approval. Honor explicit owner limits and existing task scope. Polygon and
the owner control launch authorization and the shared installation/game slot.
A scenario-only correction retains the actual mod version/build and installed pins.
Preparing the next order grants no additional launch or unbounded cycle.

## Outcome and coverage

Final report testResult.outcome is tested_successfully, tested_with_errors,
interrupted_external, incomplete or not_started. All required known-role checks
and requested data must be complete/passing for success. A subject check mismatch
is tested_with_errors, not a diagnosed mod defect. A known operational/tooling
interruption after start is interrupted_external. Unknown failed-check roles
remain incomplete rather than blaming the subject. Coverage separately lists
required/performed/passed/failed/not_run/unavailable, per-check roles and requested
data statuses. Earlier subject mismatches and later interruptions are both
retained as subjectMismatchObserved/interruptionObserved flags.

Before report finalization, board testOutcome is null; queue/game activity cannot
display 'tested'. A suppressed final decision retains testingLifecycle=not_started.
Only proven started-and-ended attempts receive testingLifecycle=completed and a
final testing outcome. This does not certify mod acceptance or authorize repeats.
