# Explicit completion of the known pre-native loader refusal

This narrowly bounded path concerns an admitted candidate qualification whose
exact reviewed executor stopped with the missing `sksevr_loader.exe` preflight
error before creating native run state or entering setup. It is not a general
failed-qualification waiver. It never calls runner recovery, launch, next, queue
dispatch, notifications or ordinary pipeline clearance. Failed/uncertain cases
outside this exact proof remain held under their existing procedures.

The two explicit commands use the existing SAME session root and SQLite database:

```text
python PATH_TO_DASHBOARD/polygon.py --root SAME_ROOT qualification-reconcile-pre-native ID REVIEW.json
python PATH_TO_DASHBOARD/polygon.py --root SAME_ROOT qualification-finish-pre-native ID FINISH.json
```

Reconciliation appends a reviewed zero-start diagnostic packet and marks this
qualification recorded, while keeping its exclusive reservation. Finish is a
separate technical decision which removes only that unchanged routine reservation
and marks this qualification released. The original admission row, unknown
preparation reports, dispatch allowance and other records remain intact. This ID
cannot run again. The packet states testingStarted=false, actualGameStarts=0,
restored=null, restorationBasis=not_required_no_mutation, unchanged cumulative
accounting and globalProviderQualified=false. It invents no archive, successful
test, historical mod result or delivery.

## Evidence and authority

An independent operator must verify the actual existing human tool-repair scope
and explicitly review this exact qualification. Evidence files and a verifiedBy
string do not authenticate a human instruction. Existing authority may cover
finishing this own routine reservation after all uncertainty has been resolved;
there is no extra human-approval requirement solely for this technical finish.
An unrelated or genuine uncertainty hold still requires its own existing
owner-reviewed clearance. The old CLAW hold clearance never clears this hold.

Before changing Dashboard sources, copy ALL original Dashboard Python files named
in the frozen plan's pins into a separate external export, verify each original
hash, and retain a receipt. Never reset the checkout or rewrite original plan
pins. The export receipt has schemaVersion=1,
kind=original-dashboard-source-export, qualificationId, planSha256, and files
entries with originalPath, exportPath and sha256. Every original pinned Dashboard
Python file must be represented once. Only the changed polygon.py CLI-routing
file may substitute its original exported bytes. EVERY other original Dashboard
Python file, including qualification.py and all imported mixins/helpers, must
also match its CURRENT original pin; exports do not exempt runtime dependencies.
All other original pins, including host configuration, and the entire candidate
inventory still match their original locations. The new recovery module and polygon.py are separately pinned
by implementationPins; `qualification_pre_native.implementation_pins()` returns
that exact list. No blanket source-pin exemption is added to existing commands.

The only supported control flow is the original Dashboard polygon.py SHA256
a0e7f8fb2da8140cebef4bb33f3c5ea68273891f85f3d123562566123cb2c551,
qualification.py SHA256
c9251b27a33f1d2cf8c5e36ea9573dcc41f07729eba55713f7b6efcf1470006f,
and candidate runner.py SHA256
36605b612f5de4f94546b691818e6e8cadf9638bdebd013af320110a48a803ab.
These are source-byte identities, not version-string assumptions. A different
candidate or control flow needs a separate code review and source change.

The review must bind the complete child exit, worker identity, dispatch intent,
full executor log and profile-selection evidence. The child exit must be exactly
returncode=2 without timeout. The full log must contain only the exact JSON
missing-loader refusal for this configured game directory. There must be no
launch-intent file and no candidate native run trace. Empty runs alone never
establish zero. Exact admission and original expiry are retained and checked.

The historical-protected-baseline mode (default for existing reviews) requires a
real independently reviewed PRE-DISPATCH protected baseline. Never create a
current snapshot and backdate it. The alternative executed-source-prefix mode
below proves absence of mutation by this exact attempt from its complete audited
source prefix and makes no historical global-state equality claim.
Public read-only helpers protected_scopes(config,
profile, original_saves) and protected_inventory(path) define its structure.
The baseline document contains:

```text
schemaVersion: 1
kind: qualification-pre-native-baseline
qualificationId: exact ID
capturedAt: actual Unix UTC capture time before dispatch/admission
originalSavesRoot: explicit absolute directory of original saves
snapshots: mapping of each protected scope to protected_inventory(path)
```

Scopes cover the complete source profile, original save directory, MO2 INI,
game installation, overwrite, configured OpenVR settings/Root Builder data,
bridge-token file, every extra_files entry and configured host runnerConfig. Inventories retain
paths, hashes, sizes, directories and absent roots; links/reparse points and
oversized inventories are refused. Operators verify the scope is the actual
installation/settings/saves, including any additional configuration a tool
could write. Missing, changed or incomplete scope is uncertainty, not proof of
restoration. The source profile must remain selected in saved settings and in
the live owned MO2 bridge when MO2 is open.

## Review records

All evidence pin objects contain only absolute path and lowercase sha256.
REVIEW.json contains these common fields and one explicit proof-mode section:

```text
schemaVersion: 1
kind: qualification-pre-native-review
qualificationId, verifiedBy, summary
ownerAuthorization: existing independently verified human tool-repair evidence
sourceFlowReviewed: true
zeroStartsReviewed: true
noMutationReviewed: true
protectedStateReviewed: true
originalAuthorityReviewed: true
uncertaintyResolved: true
reservationIsOwnRoutine: true
plan: pin to the original qualification plan.json
originalDashboardExport: pin to the original-source export receipt
implementationPins: exact implementation_pins() list after code is frozen
admission: exact original {id, started} database row
sourceFlow: {runnerSha256: supported runner hash,
             case: missing-sksevr-loader-before-native-state-and-setup}
evidence: {worker: pin, child-exit: pin, dispatch-intent: pin,
           executor: pin, profile-selection: pin}
```

FINISH.json contains schemaVersion=1, kind=qualification-pre-native-finish,
qualificationId, verifiedBy, summary, packetSha256,
reconciliationReviewSha256, and true values for reconciliationReviewed,
zeroStartsReviewed, noMutationReviewed and finishOwnReservation. It binds the
registered pre-native packet and the exact original reconciliation review.
Reconciliation and finish recheck evidence and protected state under the native
mutex and a SQLite write transaction. They require the exact worker dead, a
usable process inventory, no game/loader/VR process, no candidate run traces,
and no unfinished or uncertain configured-host native session. Live MO2 identity,
/session mo2Pid/profilesPath/instance/boot, and /ping game/modsPath/profile must
match the configured installation. Session and native identity are rechecked
after those reads. /ping must report ok=true, mainThread=ok and explicit idle
busy. If busyKnown is advertised it must be true. Installed Bridge2.3.1 does not
advertise it; evidence records busyKnownAvailability=not_advertised and a null
value without claiming that metadata exists or treating its absence as a writer.
A /procs read within the same /session bracket must have the
same serverBootId, explicit busy=null/false, integer running=0 and
launchedByMO2=[]. Missing/unknown state, xEdit or any other active MO2 writer
retains the reservation. Foreign holds,
owners, qualifications, eligible released/cycle/retry/shared work, changed
evidence or an uncertainty-reclassified own hold prevent either operation.

Packets and the automatic pre-native-finish.json receipt retain source/evidence
hashes and fresh native/runtime observations. Exact repeated finish is idempotent;
altered reviews or receipts are refused. Existing qualification-release and
pipeline-clear semantics remain unchanged. A storage interruption leaving an
unregistered packet/finish artifact is an explicit review stop, never an overwrite
or automatic retry. This feature neither authorizes a replacement qualification
nor refreshes any launch budget.

## Source-prefix proof without a historical baseline

For historical-protected-baseline mode, add proofMode with that value and
protectedBaseline with the real original baseline pin. Missing evidence never
becomes a fabricated baseline or an empty-runs shortcut.

The alternative executed-source-prefix requires the complete known candidate
(176 files), its CLI, and all 18 exported original Dashboard Python files to
match exact separately reviewed relative-path/SHA256 inventory digests. Matching
only runner.py or recognizing a failure string is insufficient:

```text
candidateInventorySha256: da99b03e94b26020057236fb13e15aac1b7417b6e6070a5eb5d991a274a73b62
originalDashboardInventorySha256: e7921ba1fa723353acffde0dc5bd9d3956b2875e3ee097ea84521c914a168e23
candidateCliSha256: f390ada90b67fa1b9e8ace9f966b5c5ab0dac5d70984cbe15ecba4291d3cb78e
```

The reviewer audits the complete executed prefix and imports. The candidate
runtime is distinct from the configured host and previously unused; the child
refuses unfinished sessions before runner.run, and pinned recover never deletes
run-state traces. Absent candidate traces, original child/worker/log receipts and
the complete pinned flow consequently prove recover did no native work. If any
part cannot be established, retain the hold. Evidence-folder writes and the
retained admission are documented facts, not protected game/profile mutations.

Use all common REVIEW fields above and this mode-specific section. Omit
protectedBaseline:

```json
{
  "proofMode": "executed-source-prefix",
  "freshSafetyScopeReviewed": true,
  "freshSafety": {"originalSavesRoot": "ABSOLUTE_ACTUAL_ORIGINAL_SAVES_DIRECTORY"},
  "executedControlFlowAudit": {"path": "ABSOLUTE_REVIEWED_AUDIT.json", "sha256": "ACTUAL_SHA256"},
  "operatorExecutionReceipt": {"path": "ABSOLUTE_ORIGINAL_OPERATOR_PREPARATION.json", "sha256": "ACTUAL_SHA256"}
}
```

The original operatorExecutionReceipt retains actualGameStarts:null,
testingStarted:false, exact worker/exit, absent native traces/intent and
hash-bound original log/worker/child/profile artifacts. Its unknown accounting is
preserved; authoritative zero is appended separately after this proof.

The separately pinned executedControlFlowAudit must contain:

```text
schemaVersion: 1
kind: qualification-write-free-prefix-audit
qualificationId, verifiedBy, analysis (substantive reviewed reasoning)
sourcePrefixReviewedWriteFree: true
noAlternateActionPath: true
preExistingRecoveryWorkAbsent: true
noProtectedEnvironmentMutation: true
candidateRuntimePreviouslyUnused: true
candidateRuntime: exact plan.configuration.runtime
recoveryReasoning: distinct_unused_candidate_runtime_and_recover_preserves_run_state_traces
planSha256: REVIEW.plan.sha256
worker: exact original worker.identity
admission: exact original {id, started}
executedCommand: [worker.path, ORIGINAL_PINNED_DASHBOARD/polygon.py,
                  --root, SAME_ABSOLUTE_ROOT, _execute-qualification, ID]
commandEvidenceBasis: pinned_dispatch_subprocess_argv_and_exact_child_exit
runnerSha256: supported runner hash above
candidateCliSha256, candidateInventorySha256, originalDashboardInventorySha256: exact digests above
controlFlow: exact qualification_pre_native.SOURCE_PREFIX list
evidenceSha256: every REVIEW.evidence key mapped to its sha256
```

The command is honestly reconstructed from the frozen parent's subprocess argv
and original child-exit receipt, rather than mislabeled as a captured historical
OS command line. The operator independently verifies that the supported dispatch
produced these receipts and no alternate action path was possible. All original
candidate/input/host pins are rechecked and retained with exported old sources
and separately pinned new recovery code.

Fresh safety scopes cover profile, original saves, MO2 INI, overwrite, Root
Builder cache, OpenVR/settings, staged sources/targets, host configuration,
GameExe and loader. They never walk bulk game Data. Any .bsa/.ba2 encountered in
relevant cache scopes is explicitly metadata-only (sha256:null), with identity,
size and timestamps, and has no content-attestation claim. Other observed files,
including read-only hardlinked GameExe, retain hashes and device/inode/link-count
facts. No target is written, restored, deleted or unlinked.
When the old configuration has no root_builder_data, the fresh cache scope is
derived as mo2/plugins/data/RootBuilder (mo2_exe's parent only if mo2 is absent).
The openvr_paths pointer remains inventoried and its config[0] directory resolves
the actual steamvr.vrsettings scope. Pointer and existing resolved settings JSON
use strict bounded 1 MiB reads, rejecting duplicate keys, nonfinite constants,
invalid/relative directory entries and malformed data. No settings file is
created or rewritten.

The packet and finish receipt explicitly record:

```text
noMutationProof: no_mutation_by_this_attempt_proven_by_executed_source
originalGlobalStateComparison: not_attested
restoration: not_required_no_mutation
restored: null
```

Fresh inventories are current safety observations only. Finish rejects changes
since reconciliation-time safety observation. That later comparison is not a
pre-dispatch baseline or historical global-state equality proof. Zero starts and
absence of this attempt's mutation come from the audited executed prefix.
