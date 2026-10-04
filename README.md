# Skyrim-Poligon-Dashboard

Tags: testing, tools, devbench

This standalone chat tool routes mod test orders to one dedicated Codex chat. It is not
a game mod. It wraps the independent Skyrim Autotest executor and has its own
durable multi-chat queue, read-only board and evidence return outbox.

There are two workflows, separate from automatic/assisted execution modes:

- **Standard/manual**: the owner asks mod chats to prepare complete file-backed
  orders. They submit to the durable board without messaging Polygon. When all
  orders are ready, the owner asks Polygon to start testing; it releases that
  finite batch. Heartbeat discovery alone never starts an unreleased standard order.
- **Full cycle**: only an explicit owner start for a particular mod/task authorizes
  fix/build/install -> file-backed order -> Polygon collection -> origin analysis
  -> bounded continuation. The mod chat sends a short mode-start notice referencing
  the independently registered authorization; all testing details stay in order
  files. See [the full-cycle contract](docs/full-cycle.md). This task/documentation
  does not start a cycle, and a result notification cannot start one.

Several mod chats can develop under independent active full cycles at once.
Their analysis and staged builds may run in parallel; installation and game runs
use one shared FIFO reservation. Read [multi-chat-cycles.md](docs/multi-chat-cycles.md)
before installing or operating any full-cycle order. An owner-authorized cycle
permits a short exact-origin preparation grant notification; testing data stay in
files. Standard preparation also waits while a cycle/game owns the live installation.

These replace the earlier blanket wake/automatic-queue authorization. Result
notifications to the exact origin remain authorized. Authorized execution covers reversible test launches
and idle MO2 restart, not public publication, destroying saves or taking over a
manual game. Test requests remain data; they do not redefine Polygon's role.

## Prepare a mod for testing

The originating chat owns test design and mod conclusions. A ready order has:

1. A built mod and exact **installed** test inputs, SHA256 pins, dependencies and
   source profile provenance. A source commit alone is not proof of the installed binary.
   Normally the mod chat does not create a profile: declare the actual active MO2
   profile in `profile`. Polygon's executor copies it, activates its temporary
   copy for the run and manages saves there. Before execution Polygon checks the
   active selection; a changed profile blocks instead of silently substituting it.
   An exclusive clean profile is allowed only on direct owner instruction or an
   origin-chat decision within an explicitly started full cycle (see below).
2. A reproducible initial state: pinned save pair for physical probes, or exact
   fixture/location/setup in the scenario. Declare every file the mod may write
   in the runner config's `extra_files`; optional staged SKSE plugins are pinned.
3. Bounded actions and collection points, expected results, queried fields, units/tolerances and
   author-supplied mechanical assertions. Include baseline/comparison orders if
   needed. Separate orders are separate launches; never silently rerun a failure.
4. `sourceChat` (ledger name), `sourceThreadId` (real app thread id), purpose and
   `collect` list. Files remain outside Git; redact secrets from reports.
5. Local scenario validation and config-check. Do not promise physics coverage
   beyond the observer's advertised domains. An unsupported field is unavailable.

If the module is not built, installed/enabled in the active source profile, or a fixture/API
field is unknown, the mod chat finishes that preparation itself. Polygon reports
an incomplete order; it does not invent the test or patch the mod.

## Location and commands

Clone this repository and run its `polygon.py` from any cwd with explicit
`--root <SESSION-ROOT>` (outside Git), or set `SKYRIM_POLYGON_ROOT`. From within
a configured session directory its ancestors may be discovered by the existing
`local/skyrim-polygon/config.json`; the source checkout never determines the host. `local/skyrim-polygon/config.json` points to our executor and
the actual game's DevBench runtime metadata. No credentials belong in orders.

```text
python <repository>/polygon.py --root <SESSION-ROOT> submit <external-order.json>
python <repository>/polygon.py --root <SESSION-ROOT> board
python <repository>/polygon.py --root <SESSION-ROOT> show <order-id>
python <repository>/polygon.py --root <SESSION-ROOT> next
python <repository>/polygon.py --root <SESSION-ROOT> reconcile
python <repository>/polygon.py --root <SESSION-ROOT> recover-active
python <repository>/polygon.py --root <SESSION-ROOT> outbox
python <repository>/polygon.py --root <SESSION-ROOT> delivered <order-id> --note "verified app delivery receipt"
python <repository>/polygon.py --root <SESSION-ROOT> serve --port 8934
```

The local board is http://127.0.0.1:8934/. The server is read-only, local-machine
only, has no execution endpoints, and does not expose evidence/backups over HTTP.
Restart it with `serve` after reboot. The queue survives in local SQLite.

On another machine recreate `local/skyrim-polygon/config.json` with schemaVersion1,
executor (our checkout or extracted distribution), threadId (the dedicated app
chat), journalChat="skyrim-polygon", boardUrl, gameExecutable and the
devbenchRuntimeFiles list resolved from that machine's game/MO2 configuration.
For voice, configure `voiceListener` to the independent ASR listener's absolute
path. Start from host-config.example.json; keep the real config outside Git.
Prepare a separate runner config using Skyrim Autotest's `init` and acquisition
manifest. No external dependency binaries/source belong in this repository.
The optional skill validator uses PyYAML6.0.2 from PyPI in an external temporary
validation directory; Polygon's runtime is Python standard library only.

## Automatic order

```json
{
  "schemaVersion": 1,
  "id": "modname-20261005-build1-case1",
  "mode": "automatic",
  "sourceChat": "modname",
  "sourceThreadId": "ACTUAL-CODEX-THREAD-ID",
  "subject": "Mod name / tested build",
  "purpose": "Collect specified interaction data",
  "profile": "VERIFIED-ACTIVE-MO2-PROFILE",
  "config": "config.json",
  "scenario": "scenario.json",
  "inputs": [{"path": "INSTALLED-MOD.dll", "sha256": "ACTUAL-64-CHAR-LOWERCASE-SHA256"}],
  "collect": ["Exact-reference motion and contacts", "Tool responses and restoration evidence"]
}
```

Scenario/config paths and input paths resolve relative to the order file. The
tool copies canonical scenario/config into its immutable DB submission, then
materializes them in the local order directory at execution. Same id+same contents
is idempotent; changed content requires a new id. Installed inputs are checked
again before launch. Source pins and actual game-run executor hashes are retained.
See the independent executor's docs/scenarios.md and docs/configuration.md.

States: queued -> running -> recorded/blocked -> delivered. Only one order may
own a game session. An interrupted running order is a barrier until native
recovery and evidence reconciliation complete. Timeouts do not release ownership.
The underlying runner separately excludes foreign/live manual sessions.

After `submit`, preparation is complete. All purpose, steps, expected results,
collection requirements, pins and exact return addresses are in order/scenario
files and the queue. Standard mod chats do not send an app message, wake, ledger
task or task description to Polygon. Previously received wake messages are not
orders and must never create duplicate submissions. Full cycle permits only the
owner-authorized short mode-start notice; its testing data use the same file format.
Do not launch the game in the originating chat while its order is queued/running.

## Standard batch start

After the owner asks Polygon to start testing, the operator snapshots the exact
ready automatic standard order ids into an external authorization JSON with
schemaVersion=1, safe id, orderIds, and
ownerAuthorization (threadId, messageId or precise durable turn reference, quote,
evidence path/sha256, verifiedBy). Verify the actual human instruction and batch
scope before registering. Files/hashes alone cannot authenticate human authority.
An owner command to start all ready orders means the current snapshot, not future
submissions. An optional owner-specified deadlineUtc (Unix UTC) bounds the launch
window; safe recovery may finish afterward. The ordinary batch is bounded by its
finite exact order set, without imposing a new time limit. Nothing is released at submission.

```text
python <repository>/polygon.py --root <SESSION-ROOT> batch-release <batch-start.json>
python <repository>/polygon.py --root <SESSION-ROOT> next
```

The heartbeat may then process released orders one at a time. New standard orders
wait for another owner start; each released order runs at most once. A repeated
identical release is idempotent; altered id/content is refused. An expired release
blocks its unstarted orders when processed; use new order ids and a new direct
start for any subsequent attempt. Assisted orders still await actual owner readiness.
Existing queued schemaVersion1 orders become standard orders awaiting start;
their ids/content/evidence are preserved. Board fields expose workflow and
awaitingOwnerStart without changing the stored queue states.

## Temporary profile lifecycle

The mod chat normally creates no profile. Polygon's external executor creates an
isolated temporary copy of the active MO2 profile and makes that copy active for
the run, so saves can be managed locally. The `profile` field records the expected
active source identity, not permission to pick another existing profile. The
default `profileSelection` is `{"mode":"active"}`. Actual active selection is read
from the live MO2 bridge or, when MO2 is absent, its saved settings; ambiguity or
changed selection blocks before game launch. The runner restores the original
selection after the run. After native restoration, archive the completed profile **including its
saves** under external run results (`test-profile/`) and remove that temporary
entry from MO2's standard profiles directory. Verify ownership/restoration and
archive contents; recover interrupted sessions first. Retain original profiles
and saves. Unverified lifecycle evidence stops a full cycle. The board never
performs cleanup merely because it is being developed.

An exclusive clean profile with a defined mod set has two allowed bases: a direct
owner instruction, or an origin decision during an explicitly authorized full
cycle. Only in these cases may the mod chat prepare that exceptional source
profile. Record `profileSelection` with mode="exclusive", concrete reason and
authority="owner" or "cycle-origin". Owner authority also requires pinned
ownerAuthorization evidence using the same fields as batch-start evidence.
cycle-origin requires a separately active cycle; its task scope still applies.
Record exact mod/load-order composition and configuration pins in external order
files. Polygon still copies/activates this exceptional source instead of modifying
it directly. Ordinary automatic executor mode alone grants no profile exception.

## Assisted order / real headset

Use `mode: assisted`, the same origin/profile/input pins and `collect`, plus:

```json
{
  "playerSteps": ["Load the prepared save", "Perform the requested interaction", "Tell Polygon when to record"],
  "observations": [
    {"tool": "inspect", "args": {"kind": "state"}},
    {"tool": "inspect", "args": {"kind": "world_observer", "action": "capabilities"}}
  ]
}
```

Assisted orders wait for the player and are never started by the automatic queue.
After the owner says they are ready/in game:

```text
python <repository>/polygon.py --root <SESSION-ROOT> assisted-start <order-id>
python <CONFIGURED-INDEPENDENT-LISTENER>/asr-listen.py --devices
python <repository>/polygon.py --root <SESSION-ROOT> voice-start --device "EXACT HEADSET MIC NAME"
python <repository>/polygon.py --root <SESSION-ROOT> assisted-poll <order-id>
python <repository>/polygon.py --root <SESSION-ROOT> assisted-finish <order-id> --note "Owner completed the requested steps"
```

Use the existing microphone listener if already owned/live; do not `--force` it.
For a new listener, choose the actual headset device, say **полигон**, then a
short phrase and verify its transcription before declaring hearing operational.
No available headset device is an explicit unavailable channel, not a reason to
silently switch to a desktop microphone. Qualification of this user's headset
requires the owner wearing it; preparation does not claim that live test.

The collector verifies DevBench's game PID/path/creation identity before reads,
uses a private voice cursor and does not change the shared voice-next cursor.
Each poll writes raw observations/transcripts locally and returns new speech to
the agent. Poll repeatedly with short waits (<=30s); keep the chat responsive.
No virtual driver, automatic launch/restart/quit, synthetic input, save/load or
console/Papyrus mutation is invoked by assisted commands. Observer reads may arm
their bounded passive subscription. A game crash does not stop hearing.

In assisted mode the agent may explain observed live behavior and guide the
player, as subsequently authorized by the owner. Final mod diagnosis and code
changes still belong to its originating chat. Text is the normal reply channel;
exceptional voice is a short instruction/acknowledgment through the independent
Windows `say.sh`, never a long spoken analysis. Mark unavailable visuals and
physics explicitly; structured state is the preferred observation source.
The listener remains up until the owner explicitly requests stopping it, even
after an order finishes. `assisted-finish` closes collection only, not the game
or microphone. See knowledge/voice-channel.md for the existing channel.

## Self-checks and evidence return

Check runner and World Observer throughout the run: start readiness, pinned
builds, actual capabilities, sampling identities/generation/phase, schema/units,
unavailable fields, busy/drop/gap counters and final restoration. Save observations
and operational findings separately as `self-checks.json` / `service-findings.json`.
For our tooling, Polygon may inspect logs/source and propose fixes, clearly
distinguishing confirmed bugs, suspected causes and unsupported coverage. It
does not edit tools during a claimed session or silently compensate for a failure.
Pass proposed changes to the responsible tool chat after the run. This self-review
exception does not authorize diagnosis of the subject mod in automatic mode.

Record a finding or player remark without changing the scenario:
`polygon.py note <id> --category tool_suspected_bug --text "evidence and hypothesis"`.
Categories also include tool_bug, tool_improvement, observation and
player_instruction. Notes on a pending packet refresh its manifest before
delivery; an already delivered packet requires a separate follow-up.

`packet.json` names the exact order/origin, mechanical execution outcome,
restoration status, evidence locations and SHA256/size manifest. It contains
`analysis:null`. A failed assertion is an observed mismatch to the originating
chat's rule, not an automatically established mod defect. `recorded` means data
exists, not that the mod is accepted. Missing capabilities/data stay unavailable.

Process every `outbox` entry: the owner authorizes a short automatic notification
to the exact **sourceThreadId** with the order id, mechanical outcome and packet
path. Detailed samples, logs and analysis stay in files. This initiates packet
reading/analysis/report, without automatic fixes or another test in standard mode.
Continuation requires the separately owner-started active full-cycle contract.
Mark `delivered` only after a successful app tool receipt identifying the exact
target/order; retain that receipt in the note. Also post a short ledger
`result`/`error` + packet reference to sourceChat for durable project delivery.
An offline app leaves the outbox pending; never invent a delivery receipt. Delivery
is at least once: if a crash occurs after send but before receipt marking, the
same order id lets the receiver deduplicate. The outbox includes packetSha256;
consumers record order id/hash before analysis or changes. A duplicate must not
trigger another iteration. A changed hash for a processed id requires provenance
review. Routing verifies the packet origin against the immutable order, and a
mismatch refuses delivery. Repeated delivered commands preserve the first receipt.
Chat consumers analyze only their own returned packet, not other chats' journals.

## Verification

```text
python -m unittest discover -s <repository> -p test_polygon.py -v
```

Queue/recovery boundaries are tested with isolated temporary files; these checks
do not claim a new live-game run or headset microphone qualification.

## Development and operator ownership

Repository: https://github.com/Vhodnoylogin/skyrim-poligon-dashboard (main).
Skyrim-Poligon-Dashboard is the development chat for this service/dashboard.
Skyrim-Polygon is the separate operator chat; its queue and heartbeat remain
independent of development conversations. The owner chose the spelling Poligon
for this repository/development chat; existing Polygon CLI/runtime/order IDs
remain compatible. The agent instructions in AGENTS.md are part of this tool.

This repository was extracted with its original tool history from ai-project-meta,
prefix projects/claude-skyrim-vr/tools/skyrim-polygon at source commit 963e412.
Only that prefix was exported: no project reports, database or raw run data.
The old project polygon.py command delegates to this checkout through external
host config's dashboardRepository, preserving the existing runtime directory.

## Acquire dependencies again

- Python 3.11+: https://www.python.org/downloads/windows/ . Runtime/tests use stdlib.
- Skyrim Autotest: obtain the owner's independent executor distribution or checkout;
  read its README, docs/configuration.md and third-party acquisition manifest.
  It has no public Git remote at extraction time; do not imply a public download.
  Configure host executor to the directory containing skyrim_autotest/.
- DevBench: https://github.com/alandtse/devbench . Install a compatible VR build;
  configure the actual runtime metadata paths, never a guessed HTTP port.
- Optional World Observer: https://github.com/Vhodnoylogin/skyrim-world-observer .
  Acquire/build/install separately and pin the installed DLL for relevant orders.
- Optional headset speech: use the Skyrim VR project's independent asr-listen.py
  and knowledge/voice-channel.md, or obtain that integration from the owner.
  It is not bundled/publicly downloadable as part of this repository.
- Game, MO2 and driver acquisition is handled by the executor's manifest and
  the user's installation. They are never downloaded or installed by this board.

The queue/dashboard can be developed and tested without game dependencies.
Live automatic/assisted execution requires the configured external integrations;
headset microphone qualification requires a real player session.
