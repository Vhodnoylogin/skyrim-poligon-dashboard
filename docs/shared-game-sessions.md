# Several mod tests in one game session

Tags: testing, tools

Owner instruction: 2026-10-07. Shared automatic standard-session dispatch is
implemented for compatible generic schema1/schema2 scenarios. This replaces the
blanket rule that separate orders require separate launches. Current legacy
profile identity checks remain; mode-independent/composition-based requests are
a separate pending migration. This document does not authorize a launch.

## Select compatible ready orders

Polygon may combine several independently authorized, ready mod orders into one
bounded game session. Prefer this when their requirements are compatible; do not
wait for future orders to fill a group. Origins submit ordinary independent
subject requests and need not choose companions or create a multi-mod order.
Keep the oldest eligible order first; group only ready compatible companions
without bypassing an older conflicting reservation or starving other work.

The selected profile must enable all tested builds and dependency closure with
verified effective file/plugin pins and compatible load order. Ordinary requests
constrain required mods, not the profile name or unrelated enabled inventory.
Honor explicit exclusions, minimal compositions and specially required profiles:
conflicting requirements need separate sessions. Current legacy identity-bound
orders retain their checks; do not rewrite their pins to make them compatible.

Use one physical game process, one accountable session owner, one frozen platform
plan and one exclusive installation/run reservation. Stage and serialize every
required installation before launch through verified grants/acknowledgments;
no origin installs while another test/session owns live files. A full-cycle roster
is not permission to share an existing origin's single-order slot. Shared-session
support must explicitly bind all members and their origins to the reservation.

Freeze a session manifest before launch: session id, exact member order ids/hashes,
origins, authority/cycle tickets, installed composition, platform pins, ordered
check segments, fixtures/state transitions and evidence mapping. Validate each
member's authorization, cancellation, limits and deadline independently. Sharing
a launch never releases an unauthorized order or resets any cycle budget. Charge
each started member attempt under its existing policy, once; retain a separate
physical-launch count. Record unstarted members without claiming testing began.

## Execute distinct checks in one process

Run bounded segments sequentially. Preserve each order's factual start/end,
assertions, requested observations and write surfaces with namespaced check ids
and exact mapping to original ids. Mod presence or another mod's passing check
is not evidence that this mod was tested. Shared observations may be referenced
by several reports only when their provenance, timing and semantics apply.

Fixture/save transitions must be supported and verified. Reset state between
segments when the later scenario requires it. Tests requiring a new process,
exclusive clean composition, incompatible startup/save state, or isolation from
persistent effects belong in separate sessions. Do not silently alter a scenario
to make grouping possible. Failure in one subject may leave independent segments
runnable only if platform health and their required initial state remain verified;
otherwise stop affected work and mark missing coverage honestly.

On a crash, cancellation or tooling/recovery failure, retain each member's actual
performed coverage. Never mark unstarted members tested, blame every mod for one
failure, automatically repeat the whole group, or reopen ended attempts. Perform
one verified physical recovery/restoration and preserve the shared profile/saves
archive, referenced by each affected report. Installation ownership remains held
until recovery/restoration is complete.

## Return independent reports

Keep separate per-order packets/final reports and exact sourceThreadId routing;
do not merge several origins into an ordinary single-origin order/report. Each
report contains its own result, coverage and links to hash-verified shared session,
platform and restoration evidence. There is no common pass/fail for all mods.

A segment ending is not full report readiness while its shared game environment
is still in use. The existing restoration gate still applies. After the bounded
shared session ends and restoration/collection are verified, finalize and return
each eligible member report promptly. Do not wait for other sessions, unrelated
queued/blocked mods, or completion of the full batch/cycle group. One member's
missing collection/report assessment must not delay another whose own evidence
and common restoration are already verified. delivered still requires a successful
app receipt for that exact target/order. No origin notification before factual
test start/end and verified report readiness.

## Commands and supported scope

The operator verifies compatibility and creates this external session request;
origins keep their existing immutable orders:

```json
{
  "schemaVersion": 1,
  "id": "compatible-mods-session-1",
  "orderIds": ["mod-a-order-1", "mod-b-order-1"],
  "compatibility": {
    "verifiedBy": "ACCOUNTABLE-OPERATOR",
    "reason": "Same fixture and composition; these segments have independent state",
    "stateIndependent": true
  }
}
```

```text
python <repository>/polygon.py --root <ROOT> session-register <session-request.json>
python <repository>/polygon.py --root <ROOT> session-show compatible-mods-session-1
python <repository>/polygon.py --root <ROOT> next
python <repository>/polygon.py --root <ROOT> reconcile
python <repository>/polygon.py --root <ROOT> recover-active
```

Registration is idempotent and does not release orders. Each member still needs
its independently verified owner batch release. List 2..32 orders in FIFO order;
all must form the contiguous oldest released ready work at dispatch. Otherwise
the group waits without skipping unrelated older work. An unstarted group may be
dissolved using session-cancel <session-id>; this preserves its request/history,
leaves member orders unchanged and permits normal scheduling/regrouping.

Preparation verifies input pins, each member's authority, exact source-profile
selection requirements, identical resolved runner configuration/platform pins,
and identical initial cell/save/new-game state. Only generic steps scenarios
with explicit check-based factual starts are supported. Total checks are bounded
at256. There is no mid-session fixture reset: requests needing different fixtures,
process startup semantics or contamination-sensitive isolation use separate runs.
The accountable stateIndependent review describes semantic compatibility; hashes
cannot establish absence of cross-mod state effects. Specialized mobility/hand
probes and mixed platform configurations are rejected before native execution.

Cycle orders currently retain single-origin exclusive preparation slots and are
rejected from grouping. Sharing a launch does not justify reusing another origin's
slot. A shared multi-origin installation protocol is a separate required extension
before full-cycle members can share sessions. Assisted execution remains separate.

One running anchor job and durable session/member records own the shared native
launch; companions use session_waiting. All launch/install/clearance paths retain
the session barrier through restoration and packet collection, including partial
finalization after a crash. Each dispatched member receives an attempts entry;
replaying the child refuses instead of launching again. The session id and member
bindings are exposed on the board. No subject order or old packet is rewritten.

The frozen session plan binds original request hashes, exact origins, per-member
qualified platform plans, namespaced check mapping, combined scenario/configuration
and tool pins. Dispatch rechecks it and each owner release/input/source profile.
The native runner is called once. Its immutable shared state/result/log evidence
is pinned in separate member packets; final reports project only that member's
checks back to original names. Later unstarted checks have no factual start and
cannot notify an origin. Earlier fully passing members retain their results when
a later segment fails; unsupported or missing coverage stays explicit.

Finish/reconcile requires native completion, exact combined scenario hash and
successful restoration. Ordinary finish cannot bypass a shared member's barrier.
An interrupted preparation before a frozen dispatch plan can be closed by
recover-active without launching; a possibly started run uses native recovery.
After common restoration, use ordinary report-ready/outbox/delivered independently
for each member. No automatic replay, game launch or service restart is authorized
by installing this source change.
