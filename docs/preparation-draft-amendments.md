# Correct a never-granted preparation draft

`slot-amend` is an explicit metadata operation for an independently reviewed
missing/incorrect `writePaths` declaration before any installation or subject
submission. It is not a test retry, cycle restart, grant or hold clearance.
Ordinary `slot-request` remains immutable/idempotent and never amends a ticket.

The physical reservation keeps its original ID, FIFO sequence, cycle, iteration,
order and origin. Only `writePaths` may change. Copy the stored request, keep all
other fields identical and use **the same slot ID**. The cycle's authority,
allowed changes, deadline and iteration budget remain unchanged. New paths need
an independent review that they are within that existing owner-approved scope;
this command does not interpret free-text owner scope or grant new permissions.
An auxiliary UI proposal with a different ID or added `installationPlan`/
`supersedesUnexecutedDraftSlot` fields cannot be passed unchanged: construct the
minimal replacement from the stored original metadata and reviewed writePaths.

```text
python polygon.py --root <ROOT> slots
python polygon.py --root <ROOT> slot-amend <existing-slot-id> <amendment.json>
```

Keep all request/review/owner/evidence files outside Git. The amendment document:

```json
{
  "schemaVersion": 1,
  "id": "amend-mod-a-i1-writes",
  "slotId": "slot-mod-a-i1",
  "cycleId": "mod-a-cycle",
  "iteration": 1,
  "orderId": "mod-a-i1",
  "sourceChat": "mod-a",
  "sourceThreadId": "EXACT-ORIGIN-THREAD",
  "previousRequestSha256": "SHA256-OF-UTF8-STORED-SLOTS-REQUEST-STRING",
  "replacementRequest": {"path": "replacement-request.json", "sha256": "EXACT-FILE-SHA256"},
  "review": {"path": "independent-review.json", "sha256": "EXACT-FILE-SHA256"},
  "ownerAuthorization": {
    "threadId": "ORIGINAL-OWNER-THREAD",
    "messageId": "ORIGINAL-OWNER-MESSAGE",
    "quote": "Exact original owner instruction",
    "path": "owner.txt",
    "sha256": "EXACT-FILE-SHA256",
    "verifiedBy": "Accountable verification of the original human instruction"
  }
}
```

`previousRequestSha256` hashes the actual canonical `request` **string returned
by `slots`**, without reparsing/reformatting it. Replacement/review/evidence pins
instead hash exact file bytes. Relative pin paths resolve beside the containing
document. The original registered owner thread/message/quote/path/hash must
match; a new amendment cannot replace the original cycle authority.

The separately pinned independent review repeats `schemaVersion`, `slotId`,
`cycleId`, `iteration`, `orderId`, `sourceChat`, `sourceThreadId`, and
`previousRequestSha256`. It also contains:

```json
{
  "replacementRequestSha256": "EXACT-REPLACEMENT-FILE-SHA256",
  "reviewerThreadId": "INDEPENDENT-REVIEWER-THREAD",
  "verifiedBy": "Accountable independent reviewer",
  "reason": "Explain the missing write declaration and why it stays within the original scope",
  "neverGranted": true,
  "neverAcknowledged": true,
  "noSubmittedOrder": true,
  "liveWrites": false,
  "physicalGameStarts": 0,
  "withinOriginalAllowedChanges": true,
  "allowedWritePaths": ["ABSOLUTE-PATH-1", "ABSOLUTE-PATH-2"],
  "evidence": [{"path": "zero-effect-witness.json", "sha256": "EXACT-FILE-SHA256"}]
}
```

`allowedWritePaths` must match the full normalized replacement list, not just
the added paths. Reviewers verify the evidence and scope themselves; files and
hashes are local accountability records, not automatic human authentication.
The command independently rejects existing grants/acknowledgments, submitted
subjects or attempt/session traces for this order, stopped/expired/changed cycle
authority, changed identity fields and unreviewed paths. It never probes a live
game or touches the installation. Unrelated active work or pipeline holds stay
as they were; ordinary grant/launch barriers remain mandatory afterward.

## Released but never-granted legacy drafts

Old code did not record grant history, and `receipt=null` alone does not prove
that a released slot was never granted. This narrow case additionally requires
`originalClearance: {"path": "original-clearance.json", "sha256": "..."}` in the
amendment. Its verified canonical contents must exactly match the retained slot
note, identify this slot with `installationSettled=true`, and explicitly retain
`review.oldTicketStatus="waiting"`. The new independent review must still attest
zero effects with pinned evidence. A generic clearance or unverifiable history
is insufficient. This is an explicit reviewed legacy boundary, not a claim that
missing historical grants can be reconstructed from the database.

New requests, grants, acknowledgments and clearances append audit events. SQLite
triggers also retain a durable witness when either the old/new state is reserved,
blocked or acknowledged, including updates by a concurrently running older CLI.
Initialization seeds known retained grant/ack states without changing them.
Grant/ack history observed after witness installation cannot be hidden by a
later clearance or null receipt. Before changing the
draft, one atomic transaction retains its complete original row/request/note,
original clearance if relevant, replacement, independent review and owner pins
in an audit event. The row's new note points to that event, preserving successive
amendment lineage. A changed request receives a different grant hash; a stale
acknowledgment cannot authorize it.

Exact duplicate amendment IDs/content are read-only, including after a grant.
`currentlyApplied=false` means the record is historical and a later reviewed
revision exists. A duplicate never reapplies an old request, refreshes FIFO or
deadlines, grants access, reopens a submitted/tested subject or clears a hold.
