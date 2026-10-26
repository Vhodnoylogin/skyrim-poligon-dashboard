"""Read observation wrappers without confusing ordinary event metadata with data."""
import json


def parse(text, source):
    samples, diagnostics = [], []
    for number, line in enumerate(text.splitlines(), 1):
        def diagnostic(code, value, severity='error'):
            diagnostics.append({'source':str(source), 'line':number, 'code':code,
                                'actualType':type(value).__name__, 'severity':severity})
        try: event = json.loads(line)
        except ValueError:
            diagnostic('invalid_json', line); continue
        if not isinstance(event, dict):
            diagnostic('event_not_object', event); continue
        nested = event.get('observations', [])
        if not isinstance(nested, list):
            if event.get('kind') == 'shutdown-identity-settled' and type(nested) is int and nested >= 0:
                diagnostic('observation_count_metadata', nested, 'info')
            else:
                diagnostic('observations_not_array', nested)
            nested = []
        for item in [event, *nested]:
            if not isinstance(item, dict):
                diagnostic('observation_not_object', item); continue
            query = item.get('query', item)
            if not isinstance(query, dict):
                diagnostic('query_not_object', query); continue
            args = query.get('args', {})
            if not isinstance(args, dict):
                diagnostic('args_not_object', args); continue
            if args.get('kind') == 'world_observer':
                samples.append({'at':item.get('at', event.get('at')),
                                'response':item.get('response', item.get('result'))})
    return samples, diagnostics
