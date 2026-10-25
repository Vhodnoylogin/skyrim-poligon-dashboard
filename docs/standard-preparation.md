# One-shot standard preparation

An actual owner request to test a named mod includes its required reversible
installation. It does not start a full cycle. The cycle slot CLI requires an
independently active cycle and must not be populated with a fabricated one.

For a standard one-shot installation, Polygon can use the existing durable
pipeline hold as a planned preparation barrier. This is a deliberate new task
reservation, not a claimed tool fault or authority to clear an older hold:

1. Independently verify the actual human request and scope. Record external
   evidence with exact origin/order, owner path/hash, all writePaths, staged
   input hashes, original files/profile and rollback plan. Prepare offline first.
2. Polygon checks no active/reserved/prepared owner, then calls
   `pipeline-hold EXACT-NEW-PREPARATION-ID --note REVIEWED-EVIDENCE-PATH-AND-HASH`.
   Recheck afterwards: the sole hold is this exact new hold, no active/prepared
   qualifications, reserved/blocked slots, running jobs/shared sessions/retries,
   and no ongoing writer. A pre-check alone is never a reservation. No duplicate
   hold ID with a different request can be adopted.
3. Use the executor's strict native process enumeration under its shared session
   mutex to verify both editions, loaders and VR processes absent, and actual MO2
   Bridge idle. A filtered process list, pipeline-status or HTTP response alone
   is insufficient. The preparation operator retains the mutex through live
   writes and rechecks ownership before each declared installation group. All
   other live writers/launches respect the durable hold; they do not add another
   hold as a way to acquire it. If another owner/hold/state appears, stop writes.
4. The exact origin installs only declared staged files and dependencies, keeping
   originals/backups and an external per-file receipt; verify installed hashes,
   actual active source profile/load order and any intended settled changes.
   No game can start while this hold remains. A crash/timeout keeps the barrier.
5. An independent operator verifies the installation is complete or rolled back,
   no writer remains and the native environment is idle. Use existing
   `pipeline-clear EXACT-NEW-PREPARATION-ID CLEARANCE.json`. Clearance includes
   exact holdId, installationSettled:true and independently verified actual
   ownerAuthorization under the ordinary owner-evidence contract. The concrete
   test request covers completing its planned reversible preparation; a token,
   stale wake or another chat's assertion does not substitute for that request.
   This does not authorize clearing unrelated, recovery or historical holds.
6. Submit the schema2 subject with actual installed pins. Polygon freezes its
   separate exact SE platform/qualification and registers the owner's one-shot
   batch authorization. Preparation does not qualify a new API, activate a
   provider, consume/reset a game attempt or release old orders/cycles.

There is no new preparation queue, database edit, automatic timeout clearance,
cycle or game command here. Existing hold/clear commands remain accountable
manual operations. Durable request/rollback evidence must survive chat/app exit.
