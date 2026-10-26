# Operator selection for one solo subject

An operator can bind an untouched schema2 automatic order to a separately qualified
executor and platform manifest without replacing the global host configuration.
The mod order, its source inputs and existing one-shot release stay immutable.
This route supports the first solo attempt only; shared sessions, cycles and new
retry attempts require their own supported contracts and fail closed here.

The operator first completes one authorized tool-only composition qualification
through the existing qualification commands. Its collected packet stays recorded
and its exact qualification hold stays in place. A successful HTTP response or a
source build does not qualify a mapping: review actual native results, declared
semantics, evidence hashes, restoration, archived profile/removal and cumulative
physical starts. Publish a manifest/qualification with only the covered fields.

## Immutable selection

`python polygon.py --root HOST platform-bind REQUEST.json` never launches. The
request has these exact keys (paths resolve relative to the request):

```json
{
  "schemaVersion": 1,
  "kind": "operator-order-platform",
  "orderId": "exact-existing-order",
  "subjectOrderSha256": "subject_contract.identity of the stored order",
  "executor": "frozen-executor-directory",
  "platformManifest": {"path": "manifest.json", "sha256": "actual hash"},
  "qualificationId": "exact-completed-composition",
  "holdId": "qualification-exact-completed-composition",
  "verifiedBy": "accountable operator",
  "reason": "Actual composition and covered domain semantics",
  "ownerAuthorization": {
    "threadId": "actual owner thread", "messageId": "actual human message",
    "quote": "actual request", "path": "owner.txt", "sha256": "actual hash",
    "verifiedBy": "independent verification"
  }
}
```

Selection requires the exact sole completed qualification hold, matching owner,
actual packet retained in the qualified evidence, executor and resolved config
matching the native qualification, and no previous attempt/platform/group. Normal
`next` skips bound orders. Rebinding is refused; exact repeats are idempotent.

## Reviewed atomic admission

Ordinary `qualification-release` deliberately refuses to expose already released
queued work. Its guard remains unchanged. Do not clear the hold separately or
withdraw/recreate the subject to bypass it. After independent review use:

`python polygon.py --root HOST execute-bound REVIEW.json`

```json
{
  "schemaVersion": 1,
  "kind": "operator-bound-subject-admission",
  "orderId": "exact-existing-order",
  "binding": {"path": "REQUEST.json", "sha256": "actual hash"},
  "packet": {"path": "actual-final-packet.json", "sha256": "registered hash"},
  "ownerAuthorization": {"threadId": "actual owner thread", "messageId": "actual human message", "quote": "actual request", "path": "owner.txt", "sha256": "actual hash", "verifiedBy": "independent verification"},
  "successfulQualificationReviewed": true,
  "restorationReviewed": true,
  "archiveReviewed": true,
  "exactOnlySubjectReviewed": true,
  "verifiedBy": "accountable operator",
  "reason": "Exact one-shot subject after successful composition qualification"
}
```

**This command launches the subject.** It verifies the successful single-start
qualification, dead exact worker/owned identities, no game/VR processes or unfinished
native session, archived/removed profile and current subject authorization/inputs.
Under the native session mutex and one SQLite transaction it claims only the exact
released queued target and removes only that completed tool hold. Other released,
active, cycle, retry or shared work retains the barrier. There is no interval where
the old global dispatcher can claim the subject. Repeating the same review cannot
launch again. A crash after claim leaves a running recovery barrier, not a retry.

Launch authority is rechecked through the SAME SQLite connection after the exact
own hold is removed inside the still-uncommitted transaction. Other readers still
see the hold and queued target until commit. A refusal rolls back both changes.
There is no ignore-holds option: the ordinary hold, slot, release, owner hash,
deadline and profile checks remain intact. This avoids a second connection seeing
the pre-transfer hold and incorrectly rejecting its own reviewed admission.

The normal same-root child pipeline freezes/rechecks the selected executor,
manifest, qualification, source files, owner evidence, review and compiled scenario.
A fresh subprocess validates the selected executor to avoid cached global VR modules.
Native child imports also reject a mixed cache. Frozen plans and packets retain their
original provenance. Global host bytes and unbound behavior remain unchanged.

The qualification row remains recorded historical evidence after transfer; it is
not relabeled as an ordinary release. This route grants no extra launch or retry,
does not certify a subject mod or rendered geometry and changes no notification
gates. Polygon still owns launch/restoration/collection and the origin owns analysis.
