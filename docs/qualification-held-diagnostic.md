# Ended qualification with unresolved accounting

`qualification-record-diagnostic ID REVIEW.json` records an explicitly reviewed
failed diagnostic when native execution has ended and its declared tracked
restoration/profile archive are complete, but exhaustive launch accounting is
unproven. It never launches, restores, clears a hold, dispatches an order, activates
a provider or grants another start. Source changes alone do not execute this command.

The original plan, admission, result, state and coverage remain immutable. The
qualification moves from `running` to `recorded`, meaning collection ended, while
the same genuine `qualification-ID` hold remains. A diagnostic has
the original native `executionOutcome`, a separate `qualificationOutcome="unqualified"`,
`qualificationPassed=false`, `actualGameStarts=null` and
`cumulativeActualGameStartsAfter=null`. Its independently reviewed distinct native
identities produce only `observedMinimumActualGameStarts`, never an exhaustive
count. An observed lower bound of two is not rewritten to zero or one.

`restored=true` is explicitly limited to `tracked_executor_domains_only`;
`unownedWriteDomains="unresolved"` remains. Factual testing start and performed
checks are projected from the original boundary and retained evidence: a startup
phase may start a tool test with zero requested gameplay checks performed. This
diagnostic cannot satisfy successful qualification release or mod acceptance.

The external review must include:

- `schemaVersion:1`, `kind:"qualification-held-diagnostic-review"`,
  `qualificationId`, `verifiedBy` and a concrete `summary`.
- Explicit true `nativeCompletionReviewed`, `trackedRestorationReviewed`,
  `archiveReviewed`, `uncertainAccountingReviewed`, `observedGamesReviewed`,
  `retainHold`.
- Exact `{path,sha256}` pins for `worker`, `childExit`, `state`, `result`.
  These must name the original qualification/native artifacts, not substitutes.
- `originalDashboardExport`: a pinned `original-dashboard-source-export` receipt
  bound to the exact original plan hash, with every original Dashboard Python
  pin and its exported bytes. Only CLI integration `polygon.py` and the explicit
  diagnostic-release refusal in `qualification.py` may differ currently;
  all other original helper/module and non-source pins must still match.
  Exported code is never executed.
- `implementationPins`: the complete current top-level Python inventory returned
  by `qualification_diagnostic.implementation_pins()`, pinning this new code and
  its imported helper closure separately from the old implementation.
  At recording this code and the observer are copied and hash-verified under
  `diagnostic-implementation/`; historical packet pins name these frozen copies,
  not mutable repository source paths. The copies are never executed.
  Live host settings and installed input pins inside declared game/mod/profile/
  overwrite roots are independently verified at recording and frozen there,
  retaining `originalInputSnapshots` origin mapping. The frozen original attempt
  request, order, config, scenario, authority/accounting evidence stay pinned at
  their original paths; no historical frozen-input substitution is introduced.
  Later legitimate host/installed-input updates do not rewrite old plans or
  invalidate the historical packet through mutable input paths. Original frozen
  run state/results/archive and executor export remain independently pinned.
- `observer`: a separately pinned stdlib-only `native.py` from Skyrim Autotest
  0.3.5/0.3.6, SHA256
  `ce57c40710921be46901daf19aa58f75c5f3990e24bc7899797ac9aa07182da6`.
  Only this reviewed file is imported; no candidate runner, setup, recovery or
  shutdown is imported/called. Its strict full process enumeration and the native
  session mutex independently verify worker, every owned identity and every
  observed game identity are dead, and no current game/loader is present.
  This current observer is explicitly not the executor of the historical run.
- Exact sorted `profileArchivePins` and `profileArchiveDirectories`. Empty,
  changed, linked/reparse or unsupported archive objects are refused; the original
  temporary profile must be absent. No native state means refusal, not zero starts.
- `observedGameIdentities`: exact `{pid,birth,path}` rows, the integer
  `observedMinimumActualGameStarts` matching the union of these and captured owned
  games, plus pinned `accountingEvidence` and `observedIdentityEvidence` rows.
  Each mapping contains `identity`, an `evidence` pin present in that evidence
  list, and a nonempty `locator` describing where the reviewer verified this exact
  identity in raw evidence. Pins alone do not authenticate that interpretation;
  the operator independently reviews the source bytes and provenance.

Unfinished sessions in either candidate or configured host runtime, a live/unknown
worker or owned/observed identity, absent original admission/completion, another
active owner, changed evidence or an absent genuine hold refuse finalization.
The checks repeat under native mutex and SQLite write transaction. Exact repeats
verify retained evidence and the continuing hold; an altered review/packet/evidence
refuses. An artifact written before an interrupted database registration is kept
for explicit review and never silently overwritten or adopted.

No general exception for SE installations is introduced. After recording, any
clearance still needs the existing exact-hold independently verified human
clearance contract and a deliberate review/settlement of current shared state.
The historical unknown count remains unknown after clearance. Old jobs and cycles
never restart automatically. Offline acquisition, extraction and builds are
separate from live installation and game qualification.

## Ended late companion admission failure

The same collection-only command supports a failed restored native session whose
official companion dispatch stopped at the late `ModOrganizer.ini` pin check.
The official report remains missing; a separately retained manual attachment is
raw evidence, never an adopted official client or passed qualification.
Repeated collection verifies the retained packet digest, every evidence/code
snapshot digest and exact profile archive membership, then returns that failed
diagnostic. It does not reconstruct an official companion result, even when the
historical plan declared a companion. Ordinary qualification packets retain their
strict official companion verification.

A frozen plan may include earlier Dashboard roots as historical accounting pins.
For that case the original source-export receipt additionally declares
`executedDashboardRoot` and `executionEvidence:{path,sha256}`. The evidence must
be the original qualification's `subject-companion/dispatch.json`: exact order,
qualification and worker, the original MO2-INI pin error, and its two traceback
frames in `qualification_companion.py:companion` and
`qualification.py:qualification_verify` inside the selected pinned root.
The selected root's full original Python export is mandatory. Every other
historical source/input pin remains checked; a reviewer path alone cannot select
or waive a source root.
The exact original configured `mo2_ini` is checked at recording and frozen with
its origin mapping, like other operational inputs. Later authorized profile
selection cannot invalidate the historical packet through that mutable file.

Optional `exactSingleStartReviewed:true` preserves a proven exact native count
of one, rather than replacing it with an unknown count. It requires failed state
and result, exact child exit1, one captured native start with no restart and the
same single independently reviewed observed game identity. A null cumulative
baseline remains null. `qualificationPassed=false`, original failed outcome,
original coverage and the genuine hold remain unchanged.

`additionalEvidencePins` may retain immutable raw manual-report/events and their
referenced evidence without supplying official companion results or coverage.
`additionalDeadIdentities` may add up to16 exact client/sequencer identities to
the fresh process-death check. No process is terminated by collection.

The operator sequence is `qualification-record-diagnostic ID REVIEW.json`, verify
the resulting packet and restoration, then, only with separately verified current
owner authority and settled installation/native state, use the existing
`pipeline-clear qualification-ID CLEARANCE.json`. The clearance declares the
exact `holdId`, `installationSettled:true` and independently verified
`ownerAuthorization` with thread/message, exact quote and pinned evidence.
Failed diagnostics cannot use `qualification-release`. Clearance starts no game,
reopens no cycle and refreshes no budget. A subsequent manual launch needs its
own fresh bounded registration/owner evidence and a new ID; old channel, claim,
commands and qualification remain historical.
