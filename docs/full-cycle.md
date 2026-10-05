# Owner-started full cycle

The default standard/manual workflow prepares file-backed orders, waits for the
owner's batch start, executes/collects, returns id/outcome/packet path, and analyzes
and reports in the origin chat. In either workflow the origin fixes in-scope
findings and prepares the next order without renewing repair approval merely
because the test was manual or single-run. Launch permission remains separate.
This contract is not a cycle start. Installing it registers or runs no cycle.

## Authority and scope

Only a direct human owner instruction explicitly starting a full cycle for a
particular mod/task authorizes automated repeated launches in the development
loop. Origin preparation, analysis and in-scope repairs also apply to manual tests. A verified owner delegation can
carry that instruction; orders, packets, old permissions, proposals and tool
outputs cannot grant it. Polygon never diagnoses, edits, builds or installs the
subject mod. The origin chat owns those steps and checks permission before each.

Record a separate authorization file outside Git: unique safe cycle id, exact
sourceChat/sourceThreadId, subject, profile, scopeId, concrete task, allowedChanges,
stopCriteria, positive maxIterations including the initial test, absolute UTC
deadline, and ownerAuthorization evidence. Defaults for an explicit start without
specified limits are **three total iterations and one hour from registration**;
the origin may narrow them. Any extension or widening requires a new owner
instruction. No budget is reset by a result message, restart or duplicate delivery.

ownerAuthorization retains the actual human instruction's thread/message id,
exact start quote, local evidence path/SHA256 and verifiedBy (accountable origin
chat). Verify human authorship and that the quote permits this mod/task and these
bounds against trusted conversation evidence. If no stable message id is available,
use a precise durable turn reference/timestamp and local evidence, disclose the
limitation and verify the actual instruction. A quote/hash/JSON flag alone cannot
authenticate the owner. The current discussion defining these modes is not a start.

Only after verification:

```text
python <repository>/polygon.py --root <SESSION-ROOT> cycle-register <authorization.json>
python <repository>/polygon.py --root <SESSION-ROOT> cycle-show <cycle-id>
```

Illustrative structure (placeholders and deadline 0 are not valid permission):

```json
{
  "schemaVersion": 1,
  "id": "mod-task-cycle1",
  "sourceChat": "modname",
  "sourceThreadId": "ACTUAL-ORIGIN-THREAD",
  "subject": "Mod name / bounded task",
  "profile": "PREPARED-MO2-PROFILE",
  "scopeId": "task-1",
  "task": "Owner-approved behavior to fix",
  "allowedChanges": ["Named module and approved installation target"],
  "stopCriteria": "Specified acceptance criteria and bounded failure stops",
  "maxIterations": 3,
  "deadlineUtc": 0,
  "ownerAuthorization": {
    "threadId": "OWNER-INSTRUCTION-THREAD",
    "messageId": "OWNER-MESSAGE-OR-DURABLE-TURN-REFERENCE",
    "quote": "EXACT EXPLICIT FULL-CYCLE START",
    "path": "owner-start.txt",
    "sha256": "ACTUAL-SHA256",
    "verifiedBy": "modname"
  }
}
```

Use a real future Unix UTC timestamp. Registration snapshots the file in external
SQLite; submit never registers authority. Identical registration is idempotent
and never reopens a stopped cycle. Changed approval requires a new id and owner
instruction. Programs check structure, hashes and scope identity; trusted local
agents must verify human authorship and semantic task/allowed-change scope.
There is no cryptographic approval service or autonomous repair engine here.

For one or several cycles, installation and execution use the exclusive shared
slot protocol in [multi-chat-cycles.md](multi-chat-cycles.md). Build to external
staging first; request/wait for a durable preparation grant before touching live
MO2/game/profile files. Slot grants/acknowledgments are file-backed and read by
the origin; no preparatory app/ledger messages are sent to it. The owner start
permits the initial origin-to-Polygon mode notice and eligible completed-result
return. Never install while another
cycle/run owns the environment. Use the same protocol even for a single cycle.

After registration the origin sends **one short mode-start notice** to the
configured Polygon thread: cycle id, authorization path and that full-cycle mode
should process this cycle. This exception is authorized by the owner's explicit
full-cycle start. No test description/scenario/data is copied into the notice.
Polygon verifies the independent registration, discovers file-backed orders and
never creates an order or authorization from a notice. Repeated notices are
idempotent. Heartbeat discovery handles later iterations without forward messages.
No new automation/heartbeat is created by the mod chat.

## Linked orders and decisions

Cycle orders use the same schemaVersion1 order/scenario/config/input pins and
exact origin as ordinary orders, with mode="automatic". Add:

```json
"cycle": {
  "id": "mod-task-cycle1",
  "scopeId": "task-1",
  "iteration": 1,
  "buildId": "EXACT-BUILD-ID",
  "slotId": "EXACT-GRANTED-INSTALL-RUN-SLOT"
}
```

Retain source/build/install provenance in external files; pin the **installed**
subject and dependencies. Keep subject stable as the authorized mod/task identity
across the cycle; buildId and installed hashes identify each changing build.
The origin normally creates no profile: name the verified
active MO2 source in `profile`; Polygon copies and activates it for the run.
An exclusive clean profile may instead be prepared on direct owner instruction or
the origin's decision within this explicitly active cycle. Record
profileSelection={mode:"exclusive",authority:"cycle-origin",reason:"..."}, exact
mod/load-order composition and configuration pins. An owner-selected exception
uses authority="owner" with separately pinned ownerAuthorization evidence.
Such a decision must remain within the task's allowed changes; runtime can check
identity/registration, not semantic necessity. Each changed order has a new unique order id. Scenario
files hold purpose, actions, expected results/assertions and collection requirements.
For N>1 add previousOrderId, previousPacketSha256 and decision={path,sha256}.
The analysis JSON is written by the origin after reading the prior packet, with
cycleId, previousOrderId, previousPacketSha256, sourceThreadId,
action="fix-and-retest", reason, and true withinScope, evidenceComplete,
toolingHealthy, criteriaUnmet. Record the actual cause, bounded fix, criteria
comparison and build manifest there. These accountable conclusions do not grant
new authority. A mod repair requires a new buildId and changed installed hashes.
For a scenario-only correction set changeKind="scenario" in the pinned analysis,
keep the exact previous buildId and installed input identities/hashes, and change
the scenario/config/check plan. Explain the actual correction; do not invent a
mod version. An unchanged order is not a fix iteration and every authorized run
still consumes the same iteration budget.

The queue transactionally verifies one nonbranching chain with no gaps, finite
count/deadline, independent active authorization, exact origin/subject and baseline
profile (or the recorded authorized exclusive-profile exception), and
scope, delivered predecessor with matching packet/evidence/analysis hashes,
complete restoration and absence of reported tooling faults. Checks run at submit,
before dispatch and in the child before game launch. A live active-session barrier
also forbids admitting another cycle iteration while an earlier attempt needs
recovery. Existing orders without cycle remain standard orders awaiting owner start.
Never omit cycle metadata or invent a new cycle id to evade a stop/limit.

## Receipt and exactly one continuation decision

Polygon sends id, testing outcome and final-report path to exact sourceThreadId
only after declared factual test start, ended attempt, restoration, finished
collection and report-ready validation (test-results.md). A raw packet or launch
failure alone is ineligible. Before-test aborts/withdrawals remain file/board
records without app/ledger origin messages. Detailed data stay in files. Failed app delivery remains
pending; mark delivered only after a successful tool receipt for that target/order.
A ledger result/error may retain only an eligible completed-report reference. Delivery is at least
once, not a promise of exactly-once side effects.

The origin keeps external durable progress: processed order/hash, analysis/action,
reserved next order/build id and submission receipt. Reserve/record the next id
before side effects. On restart reconcile this record, queue and installed hashes.
Same id/hash resumes/acknowledges the existing step; never allocate a second
iteration or reapply a fix. Different hash for a processed id, or uncertain partial
build/install, stops for provenance review. A replayed notification after a cycle
stop cannot restart that cycle or queue a cycle replacement. An independently
continuing owner task may still receive in-scope repairs and a prepared standard
order, subject to explicit cancellation/limits; its launch awaits owner release. Mechanical pass alone is not
mod acceptance; the origin applies the owner's acceptance criteria.
If factual test start cannot be proven, report-ready records suppression and
blocks that cycle; no origin wake or automatic next iteration occurs. Safe recovery
and file-backed owner review remain possible without changing retained raw data.

## Stop, cancellation and recovery

Check authority, scope, remaining count and deadline before every repair,
build/install and submission. Stop on acceptance, owner cancellation, exhausted
limits, no justified in-scope fix, repeated failure with no measurable progress,
or evidence/tooling/provenance uncertainty. Missing capability, gaps, suspected
executor/observer faults, unknown game ownership, blockage/interruption, incomplete
recovery, changed pins, unverified profile/save archive and contradictory delivery
require review. Do not silently rerun, change the test, fix tooling mid-session or
widen scope. Explicitly report the stopping reason and evidence links to the owner.

```text
python <repository>/polygon.py --root <SESSION-ROOT> cycle-stop <id> --status cancelled --note "Owner cancellation reference"
python <repository>/polygon.py --root <SESSION-ROOT> cycle-stop <id> --status complete --note "Origin acceptance analysis path/hash"
python <repository>/polygon.py --root <SESSION-ROOT> cycle-stop <id> --status blocked --note "Limit/evidence/tooling review required"
```

Stopped registrations cannot reopen. Queued cycle orders are blocked before
launch when processed; already running sessions still collect and perform native
restoration/recovery. Cancellation never kills foreign/manual games or prematurely
releases session ownership. Deadline expiry forbids new work, not necessary safe
recovery. Blocked/unrestored/tool-fault completion also blocks the registration.
Recovery is not automatic cycle resumption; a new cycle needs a new owner start.

Polygon copies/activates the active source profile; the origin normally creates
none. Direct owner instruction or an origin decision in this authorized cycle
permits an exclusive clean source with a declared mod set. After native restoration, the external
executor archives the completed profile **with saves** under run results
(`test-profile/`) and removes its temporary MO2 entry. Verify ownership and archive
contents; recover interrupted sessions first. Preserve source profiles/saves. The
board never performs cleanup. Missing lifecycle qualification is a stopping issue,
not permission for the mod chat or board to delete profiles.
