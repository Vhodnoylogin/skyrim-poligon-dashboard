# Failed qualification: managed-MO2 INI boundary

`qualification-collect-mo2-boundary ID REVIEW.json` is a completion-only bridge
for the reviewed SE executor which closes an existing idle MO2 before snapshotting
ModOrganizer.ini. Its registration pin and native restoration baseline can differ
through GUI persistence. This is not execution-time input permission, a new launch,
a successful qualification, a restoration operation or a general pin waiver.

The command preserves the original frozen plan, registration pin, native
state/result, failed abnormal shutdown, physical-start accounting and genuine
qualification hold. It feeds the ordinary failed collector: `executionOutcome`
remains `failed`, `actualGameStarts` remains exactly one, cumulative unknown
accounting remains null, `qualificationPassed=false`, and no provider becomes
qualified. Existing successful-release and operator-admission guards reject it.
Separate reviewed installation clearance remains a separate owner decision.

## Required independent review

Use schemaVersion1, kind `qualification-managed-mo2-collection-review`, exact
qualificationId, nonempty verifiedBy/summary, and all true flags:

- managedIniBoundaryReviewed
- nativeCompletionReviewed
- restorationReviewed
- archiveReviewed
- retainHold

Supply exact path/SHA256 pins for originalDashboardExport, worker, childExit,
state, result, managerCloseSteps and observer. managerCloseSteps must identify the
original native run's steps.jsonl. Supply the complete current implementationPins
from qualification_diagnostic.implementation_pins(), exact profileArchivePins and
profileArchiveDirectories. The separately acquired read-only native observer is
the existing strict observer with SHA256
`ce57c40710921be46901daf19aa58f75c5f3990e24bc7899797ac9aa07182da6`.

managedMo2IniBoundary pins an independent
`read-only-pre-dispatch-versus-native-INI-baseline-review` document. It binds the
exact qualification/run, original plan/state/result/worker/child artifacts,
original registration INI bytes and their retained snapshot provenance, native
INI snapshot/backup/current bytes, observed GUI-key delta and complete finite
native snapshot count. The collector independently checks those facts; review
flags and a hash alone do not authenticate an interpretation or owner authority.

Only the executed runner with SHA256
`9433d4e8cfe6a578236c5a7aab5a50c0c30f46ef4a337e0965f04b6ed35f8e00`
is supported. Its reviewed source closes the exact preflight idle-manager identity
before the INI snapshot. The original close receipt must match that identity and
record an accepted graceful request. The full original candidate inventory and
every other original input pin must match. Generic qualification verification,
execution, recovery and release receive no exception.

## Exact permitted difference

Only one original pin may differ: configuration.mo2_ini. Its retained original
byte copy must match the original registration SHA. The native backup must match
the original native state snapshot, and current restored bytes must match that
native baseline. All native snapshots are rehashed, and the exact nonempty profile
archive and removal of the temporary profile are checked.

Strict literal INI parsing rejects duplicates and unparsed records. Every value
outside these exact ten GUI keys must remain equal:

- Geometry: MainWindow_downloadView_state, MainWindow_espList_state,
  MainWindow_geometry, MainWindow_modList_state, MainWindow_state.
- Widgets: MainWindow_modList_index, MainWindow_tabWidget_index.
- recentDirectories: `1\directory`, `1\name`, size.

In particular, selected_profile, paths, plugin settings and credentials receive
no exception. The reviewed delta must equal the independently parsed delta.
No individual key's writer/time or globally write-free execution is claimed.

## Retention and retry boundaries

Under the strict native mutex and SQLite ownership transaction, the command
verifies the exact original admission, ended failed single-game run, dead worker
and owned identities, no foreign game/unfinished session, current exclusive hold,
source exports, restoration and archive. It freezes both original/native INI byte
copies, their provenance, executed runner and current collection implementation
and observer. It then creates an exclusive review pointer and invokes ordinary
collection. Review bytes remain bound to the same initial SHA throughout. The
verifier returns its captured review reference and expected evidence hashes;
packet assembly consumes those exact values and rechecks them before writing.
An intervening pointer/review/evidence change refuses instead of adopting new
bytes or newly calculated hashes.

Cached packets depend on frozen historical evidence, not the live MO2 INI,
candidate source or mutable current implementation. Later legitimate GUI or tool
updates do not invalidate the old packet. Archive membership and retained hashes
are still checked. Modified reviews refuse; an interrupted unregistered artifact
is preserved for explicit review, never overwritten or automatically adopted.

No direct SQLite edits, original-INI rollback to appease a pin, repinning,
qualification status reset, hold clearance or game command is provided here.
