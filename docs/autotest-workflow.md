# Owner-requested autotest

Tags: testing, tools

An owner request to a mod chat to **conduct an autotest** covers preparing its
ordinary immutable subject order, handing it to Polygon for one authorized
automatic attempt, awaiting the final report and analyzing it. This is distinct
from preparation only and from a full mod repair/build/retest cycle. Discussion
of this policy does not start a particular test.

## Preparation and handoff

Keep the mod order mode independent: schema2 subject/dependency/fixture pins,
semantic subjectPlan, factual testing.start, checks, requested data and exact
sourceThreadId. Tool versions and workflow belong in separate Polygon records.
Normally Polygon copies the active profile; special profiles keep their existing
authority rules. The origin verifies the actual human request and its mod/task
scope, submits the order and records the finite exact set via `batch-release`:

```json
{
  "schemaVersion": 1,
  "id": "mod-autotest-start-1",
  "workflow": "autotest",
  "orderIds": ["EXACT-SUBMITTED-ORDER-ID"],
  "toolThreadId": "VERIFIED-SKYRIM-AUTOTEST-THREAD-ID",
  "ownerAuthorization": {
    "threadId": "ACTUAL-OWNER-REQUEST-THREAD",
    "messageId": "ACTUAL-HUMAN-TURN",
    "quote": "EXACT-HUMAN-AUTOTEST-REQUEST",
    "verifiedBy": "REVIEWING-OPERATOR",
    "path": "owner-request.txt",
    "sha256": "ACTUAL-EVIDENCE-SHA256"
  }
}
```

Optional owner deadlineUtc retains its meaning. Verify the tool chat's real ID,
distinct from every mod origin. Registration cannot alter old releases/orders,
extend cycles or release future orders. Each order runs once; installation/game
ownership, qualification, holds and deadlines remain mandatory. Compatible
independently authorized orders may share an existing bounded session.

The origin may send Polygon one short start command containing order ID,
authorization ID/path and request hash. Detailed test data stay in files. The
concrete owner autotest request authorizes this handoff; no second batch-start
request is needed. The origin awaits the result and analysis rather than launching
the game itself or sending stage-by-stage messages.

## End, restore, collect, finalize, then route

After factual testing start, ended attempt, native restoration, finished
collection/assessment and verified `report-ready`, ordinary `outbox` exposes:

| Verified result | Mod origin | Tool chat |
| --- | --- | --- |
| Subject testing never factually began | No message or command | No message or command |
| Tool fault after start | Unsuccessful report; review what was established | Same final evidence and command to analyze, repair in scope and test tooling |
| Subject check mismatch | Report and command to analyze errors | None unless a separate technical fault also exists |
| Complete passing checks/data, healthy tooling | Report and command to analyze it, then tell the owner testing succeeded if supported | None |
| Missing coverage/data or unknown failure | Incomplete report; analyze evidence limits, never claim success or infer a mod defect | Only for independently evidenced technical faults |

Before factual subject start the test is equivalent to unlaunched: records remain
in files/on the board, with no messages to either chat, delivery receipts, tested
labels or follow-on testing. This is the owner's explicit2026-10-07correction.
Existing recovery/ownership barriers remain facts. Mixed faults preserve both
findings. Mechanical mismatch is not a diagnosis; diagnosis belongs to the mod
chat. Pinned self-check findings/operational interruptions establish tool routing.
Absent evidence cannot establish success. Incomplete collection may end with data
marked unavailable/not_collected, but restoration must independently be proven.

Tool commands request testing the tooling. They do not silently enable a mod
repair cycle or unlimited subject runs. Subsequent subject attempts use existing
reviewed retry/cycle/owner authority and finite accounting; no new retry count is
invented and no hold is cleared. This policy itself activates no host/game.
Deduplicate notification ID/report hash and common native failures before repairs.

## Independent delivery and origin completion

Each item carries notificationId `autotest:<order-id>:origin` or
`autotest:<order-id>:tooling`, exact threadId, action and report hash. Send its
generated text once to that target, then call `delivered` with notificationId
and a JSON receipt string containing notificationId, threadId, reportSha256 and
messageId from the actual successful app response. Do not invent receipts.
One recipient's acknowledgment cannot suppress the other's. Discovery and receipt
commands reverify raw/final evidence; replay preserves the original receipt.
No app messages are sent merely to deploy these instructions.

On success the mod chat checks required assertions, complete requested evidence
and tool health, then explicitly tells the owner testing completed successfully
when supported. On errors it analyzes and reports findings under existing task
scope. Autotest supplies no automatic mod fix/retest loop; that is the separate
full-cycle workflow. Existing reports, packets, releases/orders and historical
delivery decisions are never rewritten.
