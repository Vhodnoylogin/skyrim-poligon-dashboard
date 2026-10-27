# Companion checks inside a tool qualification

A new operator `tool-qualification` request may explicitly include a separately
pinned component plan and sequencer. It uses the existing schema1 tool order,
qualification lease, one actual game start, native startup, runner, guardian,
restoration and archive. It does not use or relax ordinary subject companion
baseline admission, change the global host, or start a queued mod order.

Add this optional object to the existing qualification request:

```json
{
  "companion": {
    "transport": {"path": "C:/Bench/candidate/tools/subject_companion.py", "sha256": "ACTUAL_SHA256"},
    "plan": {"path": "C:/Bench/qualification/execution-plan.json", "sha256": "ACTUAL_SHA256"},
    "sequencer": {"path": "C:/Bench/qualification/sequencer.py", "sha256": "ACTUAL_SHA256"},
    "maximumSeconds": 600
  }
}
```

The pinned plan has1..64 unique ordered `checks` with `name` and
`role:"subject"`, `fixture.cell`, and `bounds.maximumSeconds` equal to the
declared companion window. `bounds.maximumCommands` is1..256. These protocol
roles identify the components under qualification; they do not accept a mod.
The ordinary generic qualification scenario retains at least one real core
check and declares the same cell with `startMode:"new-game"`.

Use an explicitly configured cold-owned SE native startup. The frozen
`interactive_session` must have the same window in1..(maximumWallSeconds-300)seconds,
`sourceId:"operator.actions"`, an absolute channel path, the `inspect`, `papyrus`
and `platform` allowlist, and the reviewed typed `nativeBindings`. Additional
candidate opt-ins such as `npcPersistence`, `morphSession` and
`allow_owned_save_load` are validated by the selected executor's own config
validator. Registration and `qualification-check` pin and validate the exact
new composition. Earlier baseline bytes are never relabeled as qualification
of these capabilities.

The existing `qualification-register`, `qualification-check` and
`qualification-run` commands remain the only route. No manual attachment is
needed. The original qualification child calls the normal runner exactly once.
A bounded companion thread waits only for that qualification's fresh native run,
matching worker PID/birth/image, owned game identity, complete common bootstrap,
frozen configuration and interactive binding. It then starts only the pinned
data client with `--order-id` and `--attempt-id` equal to
`qualification-QUALIFICATION_ID`. The client verifies its exact manifest, fresh
empty channel and exclusive per-run claim before any action.

The outer qualification wall is explicitly frozen in900..14400seconds. Historical
900second requests still admit at most600companion seconds. A longer manual
inspection can declare7200outer/6900companion seconds, for example; the pinned
plan, native interactive configuration and client all retain exactly the same
6900second window. The companion maximum is the declared wall minus300seconds,
with an absolute14100second ceiling. There are no implicit renewals.
60seconds of the original outer window are reserved for native
restoration. Before the native start and again at client admission, the full
declared companion window plus that reserve must still fit. Startup admission
is bounded by240seconds and the earlier original deadline. The native executor's
fixed five-second interactive completion allowance is accepted; client work is
still clamped to the declared maximum and the original native window. No
deadline, lease, claim, process budget or owner permission is refreshed.

`qualifications/ID/subject-companion/` retains the executor manifest, client log,
dispatch intent/argv, exact retained client identity and exit observation,
report, origin events, requests, native delivery records and completions.
Only that retained client handle can be terminated by the hook; the original
runner and guardian own Skyrim. An unknown action is never retried or replaced
by a new client, run or game. An early client failure leaves bounded native
cleanup with the original owner and retains the qualification hold.

Collection uses the existing strict companion evidence parser in a
qualification-only context. It independently verifies the exact plan/sequencer,
case order, worker/game/run/session/binding, matching actual native deliveries,
source assertions, unchanged raw results/artifacts, normal client and inner
sequencer exits, fresh native proof that both processes ended, known single
finish, and completed native restoration. The packet adds `toolCompanion` and
every verified evidence hash. The native `result.json`, generic core checks and
historical packets remain unchanged.

A missing report, startup refusal or unavailable identity/death evidence stays
uncollectable and held, with dispatch diagnostics preserved. A valid stopped,
uncertain, mismatched or incomplete component report cannot satisfy release.
Successful release still requires the existing exact operator completion review,
one actual game start, normal original worker completion, full native restoration,
archived/removed test profile, and now every declared companion case passed.
All paths keep `globalProviderQualified:false`; the companion summary explicitly
keeps `subjectModAccepted:false` and `physicsQualified:false`. Operator review
determines what exact measured component scope is qualified.

Offline tests exercise new registration/pin drift, the real native
`maximumSeconds+5` startup contract, exact retained client arguments, insufficient
outer budget, independent delivery/assertion/artifact collection, wrong identities,
inner exit failures, unknown process death and release predicates. They use
simulated owners/providers and never launch a game or touch a live queue.
