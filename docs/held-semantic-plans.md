# Operator-selected held semantic plans

This optional first-attempt route executes an unchanged ordinary schema2
`polygon-actions/1` order inside the existing owned interactive session. The
original order ID, canonical SHA-256, semantic steps, testing roles and factual
start checkpoint remain authoritative. Origins do not clone the order, change
it to a file plan or pin executor/provider versions.

The common runner still owns startup, New Game, the initial cell, the disposable
MO2 profile and final restoration. Its preparation scenario contains only the
ordinary readiness assertion. Subject actions start after the held owner is
ready, so controlled creations and mutations receive actual durable command IDs.
No second runner or alternate game launch is introduced.

The route requires a released successful new component qualification with its
complete `toolCompanion` evidence. An old startup-only baseline or a failed,
incomplete or unrestored qualification cannot admit it. The executor inventory,
transport and provider/staging/core configuration must match that actual
qualification. A fresh isolated runtime and separately reviewed interactive
window in1..1200seconds are allowed; the native bindings, morph/persistence
configuration and channel remain unchanged. Further binding expansion is not
silently admitted by this version.

The900second outer limit belongs to the dedicated tool-qualification workflow.
This ordinary-order route does not alter that limit or inherit another launch
allowance from the qualification. A current owner release for the exact mod
order and an exact sole preparation hold are independently required at admission.

## Prepare and bind

After actual qualification, freeze the SE mapping outside the global VR
manifest. Its ordinary `operations` table compiles the original semantic plan.
The manifest's `qualification` pin points to a reviewed record containing:

- `qualified:true`, `interface:"polygon-actions/1"` and the identical `operations`;
- `evidence` containing the exact released baseline-packet pin;
- `configurationSha256` equal to the recorded qualification configuration's
  canonical identity, and `pins` containing its exact frozen executor inventory.

Freeze the resulting native scenario as a separate operator artifact. The
generic Autotest `tools/prepare_semantic_companion.py` takes the unchanged order,
mapping manifest, compiled scenario, finite window and command bound, and writes
a fresh external execution-plan/standalone-sequencer pair. Its separately pinned
`skyrim_autotest/semantic_companion.py` source has deterministic `render(spec)`.
The Dashboard recomputes compilation, verifies the original-order and mapping
provenance, and compares the supplied sequencer bytes to that exact rendering.
Generated artifacts remain outside Git and outside the frozen baseline executor.

`held-semantic-bind` accepts this exact operator selection shape. Every pin is
an absolute `path` plus lowercase `sha256` after normalization:

```json
{
  "schemaVersion": 1,
  "kind": "operator-held-semantic",
  "orderId": "the-existing-order",
  "subjectOrderSha256": "EXACT_CANONICAL_SUBMITTED_ORDER_SHA256",
  "executor": "ABSOLUTE_FROZEN_BASELINE_EXECUTOR",
  "configuration": {"path": "ABSOLUTE_CONFIG", "sha256": "SHA256"},
  "transport": {"path": "ABSOLUTE_QUALIFIED_TRANSPORT", "sha256": "SHA256"},
  "qualificationId": "the-successful-released-component-qualification",
  "baselinePacket": {"path": "ABSOLUTE_PACKET", "sha256": "SHA256"},
  "holdId": "the-exact-preparation-hold",
  "mappingManifest": {"path": "ABSOLUTE_SE_MAPPING", "sha256": "SHA256"},
  "compiledProgram": {"path": "ABSOLUTE_NATIVE_SCENARIO", "sha256": "SHA256"},
  "sequencerModule": {"path": "ABSOLUTE_GENERIC_SOURCE", "sha256": "SHA256"},
  "sequencer": {"path": "ABSOLUTE_GENERATED_SEQUENCER", "sha256": "SHA256"},
  "executionPlan": {"path": "ABSOLUTE_GENERATED_PLAN", "sha256": "SHA256"},
  "maximumSeconds": 1200,
  "ownerAuthorization": {},
  "subjectCapabilitiesUnderTest": true,
  "verifiedBy": "operator",
  "reason": "Reviewed unchanged semantic plan over the exact qualified composition"
}
```

`ownerAuthorization` must contain the existing complete independently verified
human evidence; the empty example is not an admissible request. Binding creates
no launch, clears no hold and changes no global host setting. The normal queue
dispatcher skips a held-bound order until its separate reviewed admission.

`held-semantic-execute` accepts the existing companion-admission review fields,
with `kind:"operator-held-semantic-admission"`: exact `orderId`, `binding`,
`baselinePacket`, current `ownerAuthorization`, `verifiedBy`, `reason`, and true
`preparationReviewed`, `restorationReviewed`, `archiveReviewed`,
`exactOnlySubjectReviewed` and `subjectCapabilitiesUnderTest`. Under the native
mutex and one SQLite transaction it verifies current process death, no foreign
game or unfinished runtime, the same released baseline, exact sole hold and sole
currently released queued order. It transfers only that hold into the original
order's claim and calls the ordinary execution path once. Repeated admission
returns its existing receipt and never starts another attempt.

## Independent evidence and boundaries

The qualified transport's private file-plan wrapper treats all checkpoint names
as protocol cases. That lets the same frozen client retain actual commands and
raw results. Its first delivery is recorded as `transportBoundary` only. It is
not factual mod-testing start and cannot authorize an origin notification.

The held collector independently verifies the unchanged semantic order and
selected mapping, exact compiled scenario, every delivered envelope, native
delivery log, raw result, original final assertion, role and stopped remainder.
It reevaluates the original rules against actual returned data. Mutations cannot
have repeated attempts; polling is allowed only where the original compiled step
declares it. Missing files, changed code/mapping or unknown command outcomes
retain the normal collection/ownership hold.

`actualSubjectBoundary` is the first actual native delivery of the original
`testing.start` checkpoint. If the first twelve checkpoints are fixtures and the
thirteenth is the declared start, a fixture failure in that prefix remains
`testingStarted:false`, even when the transport protocol has started. The public
projection preserves every original fixture/tooling/subject role. Final report
and autotest notification gates use that original boundary.

Observation-only steps remain `observed`, with separate observed/executed and
measurement counts. They are never relabeled as passed business assertions.
Complete execution may include those actual collected observations alongside
passed asserted checks. Success requires the original subject boundary, all
asserted subject checks passed, the full plan conducted, every requested
observation collected, no unavailable/not_run/uncertain steps, healthy native
completion and restoration. Subject observations contribute measurement coverage,
not business assertion coverage.

The collector also requires known finish, exact worker/game/session attribution,
independent client/sequencer death and the original profile archive/removal gates.
This route provides no automatic retry, post-start continuation, physics claim,
voice/NLP bridge or mod acceptance. Such extensions require their own supported
reviewed workflow; a stopped action is never replayed here.
