"""Provider-independent subject orders and Polygon-owned attempt compilation.

No executor imports or host configuration are needed to prepare a subject order.
Platform mappings are trusted operator data, qualified against exact tool pins.
"""
import copy
import hashlib
import json
import math
import re

INTERFACE = "polygon-actions/1"
MAX_SUBJECT_STEPS = 512
OPERATIONS = {
    "state.read": set(), "player.read": set(), "world.read": {"request"},
    "input.perform": {"request"}, "controller.perform": {"request"},
    "object.perform": {"request"}, "menu.read": {"request"},
}
RULES = {"equals", "contains", "min", "max", "exists"}


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def subject_identity(order):
    """Stable subject specification; launch/cycle ticket ids are not mod progress."""
    return identity({k: order.get(k) for k in ("subject", "purpose", "profile", "profileSelection",
                    "inputs", "subjectPlan", "testing", "collect", "sourceChat", "sourceThreadId")})


def build_hashes(order):
    pins = order["inputs"]
    if order.get("schemaVersion") == 2:
        pins = [p for p in pins if p["role"] == "subject"]
    return sorted(p["sha256"] for p in pins)


def validate(plan):
    if not isinstance(plan, dict) or set(plan) != {"interface", "fixture", "steps"} or plan["interface"] != INTERFACE:
        raise ValueError("Subject plan needs polygon-actions/1, fixture and steps only")
    fixture = plan["fixture"]
    if not isinstance(fixture, dict) or not fixture or set(fixture) - {"cell", "save", "startMode"}:
        raise ValueError("Declare subject fixture cell or pinned save")
    if "cell" in fixture and not re.fullmatch(r"[A-Za-z0-9_]+", fixture["cell"]):
        raise ValueError("Fixture cell needs a safe editor id")
    if "save" in fixture:
        save = fixture["save"]
        if not isinstance(save, dict) or set(save) != {"saveStem", "essSha256", "skseSha256"} or not re.fullmatch(r"[A-Za-z0-9_-]+", save.get("saveStem", "")) or any(not re.fullmatch(r"[0-9a-f]{64}", save.get(k, "")) for k in ("essSha256", "skseSha256")):
            raise ValueError("Save fixture needs its identity and ESS/SKSE pins")
    if not (fixture.get("cell") or fixture.get("save")):
        raise ValueError("Fixture requires cell or save")
    if "startMode" in fixture and (fixture["startMode"] != "new-game" or "save" in fixture or not fixture.get("cell")):
        raise ValueError("New-game fixture requires cell and no save")
    steps = plan["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_SUBJECT_STEPS:
        raise ValueError(f"Subject plan needs 1..{MAX_SUBJECT_STEPS} bounded steps")
    names, assertions = set(), 0
    for step in steps:
        if not isinstance(step, dict) or set(step) - {"name", "operation", "parameters", "timeout", "poll", "assert", "observe"}:
            raise ValueError("Subject steps cannot contain provider tools or configuration")
        name = step.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Subject checkpoint names must be nonempty and unique")
        names.add(name)
        operation = step.get("operation")
        if operation not in OPERATIONS:
            raise ValueError("Unsupported semantic operation: " + str(operation))
        params = step.get("parameters", {})
        if not isinstance(params, dict) or set(params) != OPERATIONS[operation]:
            raise ValueError("Operation parameters differ from interface")
        # Requests are domain values; executable transport/provider selectors belong to the adapter.
        def domain(value):
            if isinstance(value, dict):
                if set(value) & {"tool", "endpoint", "url", "port", "dll", "transport", "method", "script", "command", "$parameter"}:
                    raise ValueError("Provider command in subject parameters")
                for child in value.values(): domain(child)
            elif isinstance(value, list):
                for child in value: domain(child)
        domain(params)
        timeout = step.get("timeout", 20)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 180:
            raise ValueError("Subject step timeout must be finite within (0,180]")
        for flag in ("observe", "poll"):
            if flag in step and type(step[flag]) is not bool:
                raise ValueError("Subject step flags must be boolean")
        if step.get("poll") and operation not in {"state.read", "player.read", "world.read", "menu.read"}:
            raise ValueError("Subject polling requires a read operation")
        rules = step.get("assert", [])
        if not isinstance(rules, list) or (not rules and (step.get("observe") is not True or step.get("poll"))):
            raise ValueError("Step needs assertions or explicit non-polling observation")
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) - RULES - {"field"} or len(set(rule) & RULES) != 1 or not isinstance(rule.get("field"), str) or not rule["field"]:
                raise ValueError("Assertion needs semantic field and one operator")
            if "exists" in rule and type(rule["exists"]) is not bool:
                raise ValueError("exists must be boolean")
            for key in ("min", "max"):
                if key in rule and (type(rule[key]) not in (int, float) or not math.isfinite(rule[key])):
                    raise ValueError("Numeric assertion must be finite")
        assertions += len(rules)
    if not assertions:
        raise ValueError("Subject plan needs at least one actual assertion")
    identity(plan)  # Reject non-JSON and non-finite domain values.


def compile_plan(plan, operations):
    """Translate semantics through a separately qualified mapping, never a mod-name branch."""
    validate(plan)
    fixture = plan["fixture"]
    result = {"schemaVersion": 1, "steps": []}
    for key in ("cell", "startMode"):
        if key in fixture: result[key] = fixture[key]
    if "save" in fixture: result["fixture"] = copy.deepcopy(fixture["save"])
    for step in plan["steps"]:
        adapter = operations.get(step["operation"])
        if not isinstance(adapter, dict) or set(adapter) != {"tool", "args", "fields"} or not isinstance(adapter["tool"], str) or not isinstance(adapter["fields"], dict):
            raise ValueError("Unavailable platform operation: " + step["operation"])
        def bind(value):
            if isinstance(value, dict):
                if "$parameter" in value:
                    if set(value) != {"$parameter"} or value["$parameter"] not in step.get("parameters", {}):
                        raise ValueError("Invalid platform parameter binding")
                    return copy.deepcopy(step["parameters"][value["$parameter"]])
                return {k: bind(v) for k, v in value.items()}
            if isinstance(value, list): return [bind(v) for v in value]
            return value
        compiled = {"name": step["name"], "tool": adapter["tool"], "args": bind(adapter["args"])}
        for key in ("timeout", "poll", "observe"):
            if key in step: compiled[key] = step[key]
        compiled["assert"] = []
        for rule in step.get("assert", []):
            path = adapter["fields"].get(rule["field"])
            if not isinstance(path, str):
                raise ValueError("Unavailable platform observation: " + rule["field"])
            compiled["assert"].append({"path": path, **{k: v for k, v in rule.items() if k != "field"}})
        result["steps"].append(compiled)
    return result
