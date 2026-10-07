# Several automatic full cycles on one test installation

The owner may explicitly start full-cycle development for several named mods/tasks
at once. Each originating chat diagnoses/fixes/builds its own mod, submits complete
file-backed orders, reads returned evidence and decides its next iteration under
[the full-cycle contract](full-cycle.md). Polygon only schedules, executes/collects
and returns references. No cycle is started by this document or a notice.

Several cycles may be active concurrently; there is still **one shared game and
one install/run reservation**. Parallel game sessions are not supported. Parallel
analysis, editing and building are allowed only in independent checkouts/output
directories, outside live MO2/game/profile files. Installing a DLL while another
test uses it would invalidate that test even if the game-session mutex is intact.

## Shared launches

Compatible ready orders from several origins may share a single game launch;
read [shared-game-sessions.md](shared-game-sessions.md). The single game/reservation
barrier excludes concurrent physical sessions, not several subjects within one.
Each member keeps its own authority, cycle accounting, checks and report. Current
single-order slots/dispatch below are legacy implementation, not permission to
reuse another origin's slot; explicit shared reservation support is pending.

## Owner start and group limits

The explicit owner start names the allowed mods, tasks and their originating
chats/threads. Record a separate external group manifest: groupId, owner evidence,
fixed roster of cycle ids/origins/tasks, per-cycle quotas, common UTC deadline and
group stop policy. Independently register each roster member with that same owner
evidence, its own scope and quota, and the common deadline; retain groupId as
authorization metadata. A generic proposal for this workflow is not a start.

Default limits for an explicit multi-mod start without specified bounds are
three total iterations per named mod and one shared hour per named mod for the group, measured
from its initial registration. For M mods this is at most 3*M member test attempts
(possibly fewer physical launches when compatible tests share sessions), not
three more attempts every time a result is delivered. Three named mods therefore
have a common three-hour deadline; the group stays bounded as work is serialized.
If the owner sets a smaller
total budget, allocate per-cycle quotas whose sum does not exceed it. Do not
silently add a mod, increase quotas, restart the deadline or spawn an unrequested
chat/automation. New members/extensions require a new owner instruction.

Group roster/budget verification and meaningful task/progress assessment are
agent responsibilities; the DB enforces registered per-cycle quotas/deadlines and
one shared reservation/session. There is no separate cryptographic group approval
service. Each origin may send its owner-authorized mode-start notice to Polygon;
Polygon never sends preparation prompts/grants to origins. Test details and
preparation exchanges stay file-backed.

## Build independently, reserve installation

An origin checks its authority/limits and prior packet, records analysis and builds
to external staging. It must not alter installed mods, active profiles, load order,
dependencies or saves while waiting. Reserve a stable next order id and queue a
preparation ticket (outside Git):

```json
{
  "schemaVersion": 1,
  "id": "slot-mod-a-iteration2",
  "cycleId": "mod-a-cycle1",
  "iteration": 2,
  "orderId": "mod-a-build2-case1",
  "sourceChat": "mod-a",
  "sourceThreadId": "ACTUAL-ORIGIN-THREAD",
  "writePaths": ["ABSOLUTE-INSTALL-DLL-PATH", "EVERY-OTHER-LIVE-WRITE-TARGET"]
}
```

Declare all file/directory targets, including any authorized exclusive source
profile and dependency/configuration changes. Origins verify semantic allowed
scope and avoid overlapping code writers. Ticket metadata cannot authorize a
cycle. Identical ticket submission is idempotent; the DB admits at most one ticket
for a cycle iteration/order. A later iteration requires prior orders delivered.

```text
python <repository>/polygon.py --root <ROOT> pipeline-status
python <repository>/polygon.py --root <ROOT> slot-request <ticket.json>
```

Polygon's existing heartbeat calls slot-next when no game/recovery/hold owns the
installation. It grants the oldest waiting eligible ticket (FIFO). A already
released finite standard batch drains before a new installation reservation; new
unreleased standard orders wait. Each completed cycle iteration goes to the tail
when it requests its next slot, so a fast origin cannot bypass waiting B/C.

```text
python <repository>/polygon.py --root <ROOT> slot-next
python <repository>/polygon.py --root <ROOT> slots
python <repository>/polygon.py --root <ROOT> slot-ack <slot-id> <origin-ack.json>
```

Polygon publishes reservations through slots/pipeline-status; origins read them
while handling their already owner-started cycles. The origin writes an external
ack JSON with schemaVersion1, slotId, cycleId, iteration, orderId, exact sourceChat/
sourceThreadId and grantSha256 from slots, then calls slot-ack. This pins the file
and verifies origin/grant identity. No app/ledger preparation message or wake is
sent. slot-notified remains a rejecting compatibility command; old app receipts
are preserved but cannot authorize new preparation. Repeated reads return the
same grant; identical file acknowledgments are idempotent. The origin rechecks
authority/deadline/reservation and records progress before install. A stale/duplicate grant is
not permission to reapply installation. No task/wake message is required after
slot-request or after each new order; the durable queue drives discovery.
While awaiting a grant, the origin remains responsible for bounded file/board
polling within its existing active cycle and deadline. Do not create an unrequested
automation or ask Polygon to wake the origin as a substitute for these reads.

Only that origin may now install its staged build and bounded dependencies,
prepare an exclusive clean source profile if justified, verify the active source
and verified installed pins (unchanged for scenario-only fixes), and write/validate/submit the full ordinary order with
cycle.slotId=<reserved-slot-id>. Capture actual active profile, enabled mod/load
order and all relevant installed dependency/configuration hashes after installation;
other mods' latest accepted builds may be present. Do not assume a queue ticket
freezes the environment before its slot is granted. All shared live writers,
including standard preparation chats, must wait while another slot/game owns it.

The roster also records source repository/modules and code writers. Repository-map
aliases (for example Speech Broker components) can share one checkout. Do not let
two chats edit the same source files: assign one writer or serialize those edits;
parallel builds require stable independent source/output snapshots.

The queue binds the order to the reserved cycle/iteration/order id and exact-origin
file acknowledgment. Until restoration, no other installation, standard game run or
assisted start can pass that shared reservation. Polygon copies the active profile,
activates its copy and runs one scenario. It restores the original selection and
archives the test copy including saves before healthy slot release. An authorized
exclusive source is also copied; neither source is directly used as a writable
game-test profile. Polygon does not build/install the tested mod itself.

## Three-chat example

| Step | Chat A | Chat B | Chat C | Polygon/shared installation |
|---|---|---|---|---|
| Start | Edit/build A1 in staging | Edit/build B1 in staging | Edit/build C1 in staging | Verify separate owner-authorized scopes |
| First slot | Install A1; submit pinned order | Ticket waiting; no live writes | Ticket waiting; no live writes | Execute A1 alone, restore/archive, return A packet |
| Second slot | Analyze A packet; build A2 externally | Install B1; submit order | Waiting/building externally | Execute B1, restore/archive, return B packet |
| Third slot | A2 ticket at tail | Analyze B packet; build B2 externally | Install C1; submit order | Execute C1, restore/archive, return C packet |
| Next round | Install A2 only after next grant | B2 ticket at tail | Analyze C; accept or prepare C2 | Continue FIFO among eligible tickets |

These are concurrent development loops with sequential installation/game phases.
An origin that finishes its acceptance criteria leaves the roster; others may
continue within their original quotas/deadline. A slow/offline origin before it
requests a slot does not block other ready cycles. Once its slot is reserved, an
offline/half-installed origin is a shared-environment uncertainty, not a reason
to hand the machine to the next chat automatically.

## Failure and stopping rules

- A normal prescribed subject assertion mismatch returns data and releases a
  restored healthy slot. Only that origin decides whether an in-scope fix exists.
  No progress, acceptance, exhausted quota or task-specific uncertainty stops that
  cycle; healthy unrelated cycles may continue.
- Owner cancellation of one mod stops that cycle only. Cancellation of the group
  applies cycle-stop to every roster member and suppresses further grants. The
  owner may stop all automatic work without naming each cycle; preserve that
  instruction in the group progress record. Required recovery still proceeds.
- Any shared executor/observer fault, ambiguous ownership, unverified restoration,
  profile/save archive or common provenance issue places a pipeline hold. No new
  grants or launches pass it. Active work only collects and restores safely; result
  returns remain allowed. Do not fix tooling mid-run or silently retry as success.
- Deadlines, expired grants, crashes or origin disappearance never automatically
  release a possibly half-installed slot. A blocked reservation is a durable
  barrier. Different processed-packet hashes, partial installs or undocumented
  live writes need explicit review before continuing.

```text
python <repository>/polygon.py --root <ROOT> pipeline-hold <issue-id> --note "Evidence and shared fault"
python <repository>/polygon.py --root <ROOT> cycle-stop <cycle-id> --status blocked --note "Bounded stopping reason"
```

For installation/slot clearance use slot-clear <slot-id> <clearance.json>. The
external clearance has exact slotId, installationSettled=true and independently
verified ownerAuthorization evidence. Verify no origin writer is still working,
installed files are restored or deliberately settled, any submitted order is
withdrawn/reconciled, and there is no active game. Never clear on a timeout alone.
pipeline-clear <issue-id> <clearance.json> likewise requires exact holdId,
installationSettled=true, owner evidence and no active game. Neither operation
reopens a stopped cycle; a new cycle needs a new explicit start. Clearances are
agent-verified local evidence, not automatic authentication of the owner.

Maintain each origin's durable processed packet/action/next-id/install/submission
progress and file grant acknowledgments/eligible final-result receipts. A restart first reconciles those
records, slots, queue and native recovery. Re-delivery of a result or grant resumes
the existing step or reports it; it never branches, reapplies a fix/install or
allocates a fresh budget. Source confusion or unknown partial state stops for
review. Only the exact origin receives an eligible completed final-report
notification and performs mod diagnosis. Factual test start/end, restoration,
collection and report-ready are mandatory (test-results.md). Before-test failures/
withdrawals remain file/board records, never tested/delivered labels or messages.
