# Several mod tests in one game session

Tags: testing, tools

Owner instruction: 2026-10-07. Accepted scheduling policy; shared-session dispatch,
reservation and evidence support are not implemented in the current CLI. This
policy replaces the blanket rule that separate orders require separate launches.
It does not start testing or authorize bypassing current queue/recovery checks.

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

## Implementation boundary

The current jobs mutex, claim/execute_next path, cycle slots, per-order platform
plans and recovery/packet contracts execute one order per native run. Do not fake
a shared session by concurrent claims, changing retained order identities, assigning
one origin to several mods, or invoking next against an already running game.
Implement explicit session/member records, shared reservation ownership, qualified
scenario composition, per-member evidence projection and recovery before automatic
multi-order dispatch. Preserve legacy single-order execution until then.

Offline validation must cover compatible grouping, conflicting composition/save
requirements, exact-origin routing, independently authorized member budgets,
FIFO fairness, state contamination, partial coverage after a crash, idempotent
recovery, immutable member pins and independent delivery after shared restoration.
No live run or service restart follows from this documentation change.
