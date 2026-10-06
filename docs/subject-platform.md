# Subject orders and platform attempts

Tags: testing, tools

New automatic **mod** orders use schemaVersion2. A mod chat describes the actual
subject build, gameplay dependencies, fixture and bounded checks. It does not pin
DevBench, the executor, observer providers or driver merely because they implement
the test. Polygon owns their selection, qualification and per-attempt provenance.
Updating a tool while an order is queued does not change or invalidate that order.
Missing compatibility/qualification blocks platform preparation before gameplay.

## Origin contract

```json
{
  "schemaVersion": 2,
  "id": "modname-case1-attempt1",
  "mode": "automatic",
  "subject": "Mod name / tested build",
  "purpose": "Verify requested behavior",
  "sourceChat": "modname",
  "sourceThreadId": "ACTUAL-ORIGIN-THREAD",
  "profile": "VERIFIED-ACTIVE-MO2-PROFILE",
  "inputs": [{"path": "INSTALLED-SUBJECT.dll", "sha256": "ACTUAL-SHA256", "role": "subject"}],
  "collect": ["Actual state and mechanical check evidence"],
  "subjectPlan": {
    "interface": "polygon-actions/1",
    "fixture": {"cell": "QASmoke"},
    "steps": [{"name": "subject-response", "operation": "state.read", "timeout": 20,
               "assert": [{"field": "world.ready", "equals": true}]}]
  },
  "testing": {"start": {"kind": "check", "name": "subject-response"},
              "checks": [{"name": "subject-response", "role": "subject"}]}
}
```

This illustrative readiness assertion is not evidence that any particular mod
works. Origins must author checks of their own subject behavior and declare the
first factual subject checkpoint. Loading the cell alone remains preparation.
No mod name selects adapter code. Exact origin, batch/cycle launch authorization,
profile copying/restoration/archive and final-report notification gates still apply.

Inputs have explicit `subject`, `dependency` or `fixture` roles, and at least one
actual subject pin is required. Dependencies mean game/mod behavior dependencies,
not test providers. Pin installed files, not just source commits. Transport/config
fields and provider pins are refused in schema2. Provider overlap is checked by
exact paths when preparing the attempt; no filename guessing removes legacy pins.

`subjectPlan` is embedded, immutable JSON. Interface operations:

| Operation | Parameters | Semantics |
|---|---|---|
| state.read | none | Inspect current game/world state |
| player.read | none | Inspect current player state |
| world.read | request | Read declared domain objects/observations |
| menu.read | request | Read menu state; no menu mutation |
| input.perform | request | Perform a declared game input |
| controller.perform | request | Perform a bounded controller interaction |
| object.perform | request | Perform a declared object interaction |

Requests contain domain identities, actions and values. HTTP URLs/ports, provider
tool/method/script/command selectors are disallowed. The interface is deliberately
small: unavailable operations or semantic fields are refused, not silently mapped
to guessed backend commands. A platform mapping can expose only semantics covered
by its factual qualification. `world.ready` means loaded gameplay world/player,
not merely a responsive endpoint. Additional field names must describe a stable
domain quantity (including units/identity) in the qualification reason/evidence.
Changing meaning or units requires an explicit interface/scenario migration.

Steps need unique names, finite timeouts up to180seconds and assertions, or explicit
non-polling `observe:true`. At least one assertion is required. Only read operations
may poll. Assertions use `field` and exactly one of equals/contains/min/max/exists.
The origin's semantic field becomes a backend response path through the adapter.
Check names remain identical in executor evidence. Fixture is a safe `cell` and/or
`save:{saveStem,essSha256,skseSha256}`; `startMode:"new-game"` requires cell/no save.
The executor's common startup/gameplay-readiness gate precedes subject actions.

## Polygon-owned platform qualification

The external host config selects absolute `platformManifest`. Only Polygon prepares
this manifest; origins neither copy it into orders nor update it with tool versions.
Its schemaVersion1 structure:

```json
{
  "schemaVersion": 1,
  "interface": "polygon-actions/1",
  "config": "runner-config.json",
  "inputs": [{"path": "INSTALLED-PROVIDER.dll", "sha256": "ACTUAL-SHA256"}],
  "operations": {
    "state.read": {"tool": "inspect", "args": {"kind": "state"},
                   "fields": {"world.ready": "playerLoaded"}}
  },
  "qualification": {"path": "qualification.json", "sha256": "ACTUAL-SHA256"}
}
```

Mapping and response shape above are examples, not a qualified live platform.
For requests, an adapter argument may use exact `{"$parameter":"request"}` to
bind the domain request. Other argument structure and tool selection belong solely
to Polygon. Compiled scenarios are revalidated by the existing executor.

Qualification JSON requires `qualified:true`, `interface`, `verifiedBy`, `reason`,
the exact same `operations`, `configurationSha256` (subject_contract.identity of
the resolved runner configuration), `pins` (absolute path/sha256 for every provider,
executor run.py and recursive package .py/.h/.json file), and nonempty `evidence`
(path/sha256 of actual qualification reports/results). Paths in the manifest are
relative to it; qualification evidence paths are relative to the qualification.
Qualification pins are absolute. Document semantics, units, capabilities, tested
composition and limitations in evidence. A flag/hash is not proof: the accountable
operator must review factual evidence. An unsupported capability cannot be certified
by inventing evidence. Tool replacement needs qualification of its new exact pins,
mapping and resolved configuration, without rebuilding the subject mod.

Before any game side effects, the claimed order freezes its separate platform plan
in SQLite and `platform-plan.json`: immutable order hash, stable subject-specification
hash, exact configuration, compiled scenario, executor selection, provider/executor/
manifest/config/qualification/evidence pins and preparation time. Existing plans are
never rewritten. Parent preparation and child dispatch recheck all pins, executor
inventory/selection and materialized configuration/scenario. Drift blocks dispatch;
it cannot silently switch tools. Runtime recovery uses the saved attempt location.
Raw packets/board expose separate subject and platform identities; raw file manifests
cover the platform plan. Tool findings remain distinct from subject acceptance.

## Compatibility and retries

SchemaVersion1 orders retain their original inputs/config/scenario interpretation,
DB contents, packets and receipts. Assisted and dedicated control-chain qualification
orders can continue using schema1. Never strip, rehash or rewrite a retained order.
Preparing schema2 is explicit new authoring, not an automatic legacy conversion.

The stable subject-specification hash excludes order/cycle ticket identifiers and
all platform details. A queued schema2 order survives tool replacement unchanged.
An ended/blocked attempt is never reopened. Another attempt needs a unique launch
ticket/order id, applicable batch/cycle authority and existing attempt budgets; its
subject specification can stay identical. A tool replacement alone is neither a
new mod build nor a meaningful scenario correction and cannot pass cycle progress
checks or reset limits. Existing tooling/recovery holds still require reviewed
clearance. Explicit executor-repair authority is a separate protocol.

No live qualification, tool installation, host-manifest creation or service restart
is implied by installing this source contract. A host without a qualified manifest
can accept subject orders but honestly refuses their platform preparation.
