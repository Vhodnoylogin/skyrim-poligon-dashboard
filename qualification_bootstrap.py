"""Recognize only the exact SE new-game prefix around two declared tool checks.

This completion classification does not rewrite raw coverage, roles or results.
The caller retains all source, packet, native completion and restoration guards.
"""
from pathlib import Path


def declared_tool_checks_after_new_game_prefix(plan, packet, checks, actual):
    configuration = plan.get('configuration', {})
    scenario = plan.get('scenario', {})
    steps = scenario.get('steps', [])
    testing = plan.get('orderData', {}).get('testing', {})
    declared = testing.get('checks', [])
    if (configuration.get('game_edition') != 'se' or configuration.get('se_new_game_ui') is not True
            or scenario.get('startMode') != 'new-game' or scenario.get('cell') != 'QASmoke'
            or scenario.get('kind') or scenario.get('fixture') or scenario.get('postSteps')
            or len(steps) != 5 or len(declared) != 2
            or any(c.get('role') != 'tooling' for c in declared)):
        return False
    names = [s.get('name') for s in steps]
    required = [c.get('name') for c in declared]
    if (any(not isinstance(n, str) or not n for n in names) or len(set(names)) != 5
            or required != names[3:] or testing.get('start') != {'kind': 'check', 'name': names[3]}):
        return False
    for step, menu in zip(steps[:2], ('Journal Menu', 'Tutorial Menu')):
        if (step.get('tool') != 'menu' or step.get('args') != {'action': 'close', 'name': menu}
                or step.get('observe') is not True or step.get('assert') or step.get('poll')):
            return False
    if (steps[2].get('tool') != 'platform' or steps[2].get('args') != {'operation': 'state.read'}
            or steps[2].get('assert') != [{'equals': True, 'path': 'world.ready'}]
            or steps[2]['assert'][0].get('equals') is not True
            or steps[2].get('observe') or steps[2].get('poll')):
        return False
    for step, domain in zip(steps[3:], ('human-preset-catalog', 'human-provider-config')):
        if (step.get('tool') != 'platform' or step.get('args', {}).get('operation') != 'world.read'
                or step.get('args', {}).get('request', {}).get('domain') != domain or not step.get('assert')):
            return False
    if (len(checks) != 5 or len({c.get('name') for c in checks}) != 5
            or {c.get('name') for c in checks} != set(names)):
        return False
    projected = {c['name']: c for c in checks}
    for name, status in zip(names, ('observed', 'observed', 'passed', 'passed', 'passed')):
        role = 'tooling' if name in required else 'unknown'
        if projected[name].get('status') != status or projected[name].get('role') != role:
            return False
    aux_name = 'new game world transition observed'
    if (aux_name in names or len(actual) != 6
            or [c.get('name') for c in actual] != [aux_name, *names]
            or [c.get('result') for c in actual] != ['passed', 'observed', 'observed', 'passed', 'passed', 'passed']
            or any(c.get('provenance') for c in actual[1:])):
        return False
    provenance = {'schemaVersion': 1, 'component': 'skyrim-autotest', 'stage': 'bootstrap',
                  'role': 'tooling', 'runId': Path(packet['runDirectory']).name, 'checkId': 'new-game-world-transition'}
    if (actual[0].get('provenance') != provenance
            or type(actual[0].get('provenance', {}).get('schemaVersion')) is not int):
        return False
    auxiliary = packet.get('testResult', {}).get('auxiliaryCoverage', {}).get('checks', [])
    if (auxiliary != [{'name': aux_name, 'role': 'tooling', 'status': 'passed', 'provenance': provenance}]
            or type(auxiliary[0].get('provenance', {}).get('schemaVersion')) is not int):
        return False
    for raw, menu in zip(actual[1:3], ('Journal Menu', 'Tutorial Menu')):
        if (raw.get('observation') != {'action': 'close', 'name': menu, 'queued': True}
                or raw['observation'].get('queued') is not True):
            return False
    return actual[3].get('observation', {}).get('world', {}).get('ready') is True
