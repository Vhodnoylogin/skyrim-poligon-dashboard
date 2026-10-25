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
`recover-active` points to qualification collection rather than ordinary recovery
while a qualification is running. No generic timeout takeover is provided for an
unknown worker or unproven admission with no native state; those require review.

The qualification lease persists after recorded completion. It cannot be cleared
while prepared/running. Once recorded, releasing it is a SEPARATE owner-reviewed
pipeline clearance: clearing it may permit previously released queues to run.
Do not clear it as part of old-hold clearance or automatic qualification cleanup.
Neither failure nor successful collection refreshes the one-start allowance;
`qualification-run` on the same id is refused thereafter.

Artifacts: `local/skyrim-polygon/qualifications/<id>/`; plan is also immutable in
the qualifications SQLite table. `qualification-show` and `pipeline-status` expose
the admission/lease status. This protocol changes no global host configuration.
