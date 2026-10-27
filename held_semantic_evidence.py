"""Independent original-role/boundary oracle over verified held transport bytes."""
import copy
import math
from pathlib import Path

import companion_evidence
import held_semantic as held


def _require(value,message):
    if not value:raise ValueError('Held semantic evidence: '+message)


def _field(value,path):
    for part in path.split('.') if path else []:value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def _equal(first,second):
    if type(first) is bool or type(second) is bool:return type(first) is type(second) and first==second
    if isinstance(first,dict) or isinstance(second,dict):return type(first) is dict and type(second) is dict and first.keys()==second.keys() and all(_equal(first[k],second[k]) for k in first)
    if isinstance(first,list) or isinstance(second,list):return type(first) is list and type(second) is list and len(first)==len(second) and all(_equal(a,b) for a,b in zip(first,second))
    return first==second


def assertions(value,rules):
    result=[]
    for index,rule in enumerate(rules):
        operator=next(key for key in ('equals','contains','min','max','exists') if key in rule)
        available=True
        try:
            actual=_field(value,rule['path']);expected=rule[operator]
            if operator=='equals':passed=_equal(actual,expected)
            elif operator=='contains':passed=expected in actual
            elif operator=='exists':passed=(actual is not None)==expected
            else:passed=type(actual) in (int,float) and math.isfinite(actual) and (actual>=expected if operator=='min' else actual<=expected)
        except (KeyError,IndexError,TypeError):actual=None;available=False;passed=False
        result.append({'check':None,'assertionRole':'semantic','rule':rule,'actual':actual,'expected':rule[operator],
                       'available':available,'outcome':'passed' if passed else 'mismatch','index':index})
    return result


class _Context:
    def __init__(self,p,order,plan):self.p,self.order,self.plan=p,order,plan
    def evidence_dir(self,key):
        _require(key==self.order['id'],'foreign output order');return self.p.evidence_dir(key)
    def attempt_plan(self,order):return self.plan
    def verify_companion_processes_dead(self,order,identities):
        held.verify(self.p,self.order)
        from qualification_companion import verify_processes_dead
        return verify_processes_dead(self.plan,identities)


def collect(p,order,run):
    plan=held.verify(p,order)
    view=held.protocol_order(order,plan)
    transport=companion_evidence.collect(_Context(p,order,plan),view,run)
    root=p.evidence_dir(order['id'])/'subject-companion'
    files=companion_evidence._Files((root,Path(run)/'interactive-results'))
    report,_=files.json(root/'report.json');events,_=files.lines(report['events'])
    state,_=files.json(Path(run)/'state.json',confined=False)
    native_steps,_=files.lines(Path(run)/'steps.jsonl',confined=False,maximum=128*1024*1024)
    _require(state.get('done') is True and state.get('restored') is True and not state.get('restoreErrors'),'ended restored native owner required')
    roles={row['name']:row['role'] for row in order['testing']['checks']}
    boundary=order['testing']['start']['name']
    original=plan['compiledProgram']['steps'];names=[step['name'] for step in original]
    _require([row['name'] for row in order['testing']['checks']]==names,'original checkpoint order changed')
    origins=[wrapper['record'] for wrapper in events if wrapper.get('kind')=='origin']
    actions=report['actions'];checks=[];subject_boundary=None;delivered_total=0
    delivered_ids=[action['commandId'] for action in actions if action.get('deliveredEvidence')]
    _require([row.get('commandId') for row in native_steps if row.get('kind')=='interactive-action-delivered']==delivered_ids,
             'native command delivery order/complete inventory differs from the compiled transport')
    previous=-1
    for action in actions:
        if action['caseId'] is None:continue
        current=names.index(action['caseId'])
        _require(current==previous or current==previous+1,'compiled steps were reordered or skipped')
        previous=current
    for index,step in enumerate(original):
        name=step['name'];case=report['cases'][index]
        case_actions=[action for action in actions if action['caseId']==name]
        _require(len(case_actions)<=1 or step.get('poll') is True,'mutation/unpolled step was replayed')
        for action in case_actions:
            envelope=action['envelope'];args=copy.deepcopy(step.get('args',{}));actual_args=envelope.get('args',{})
            if 'timeoutMs' in args:
                timeout_ms=actual_args.get('timeoutMs')
                _require(type(timeout_ms) is int and 0<timeout_ms<=args['timeoutMs'],'native read timeout widened')
                args['timeoutMs']=timeout_ms
            timeout=envelope.get('timeoutSeconds')
            _require(set(envelope)=={'schemaVersion','operation','tool','args','timeoutSeconds'} and envelope['schemaVersion']==1 and
                envelope['operation']=='tool' and envelope['tool']==step['tool'] and actual_args==args and
                type(timeout) in (int,float) and math.isfinite(timeout) and 0<timeout<=step.get('timeout',20),
                'actual delivered action differs from compiled original step')
            if action.get('deliveredEvidence'):
                delivered_total+=1
                if name==boundary and subject_boundary is None:
                    subject_boundary={key:action[key] for key in ('caseId','commandId','sourceEventId','deliveredEvidence')}
        results=[row for row in origins if row.get('kind')=='check-result' and row.get('caseId')==name]
        _require(len(results)<=1,'duplicate semantic verdict')
        status=case['status']
        finals=[row for row in origins if row.get('kind')=='assertion' and row.get('caseId')==name]
        completed=[action for action in case_actions if action['status']=='completed']
        if status in ('passed','failed'):
            _require(completed and len(completed)==len(case_actions) and len(results)==1,'semantic verdict lacks complete actual readback')
            raw,_=files.json(completed[-1]['rawResult'])
            expected=assertions(raw,step.get('assert',[]))
            if expected:
                _require(len(finals)==len(expected),'missing/extra final original assertions')
                for row,proof in zip(finals,expected):
                    proof=dict(proof);proof['check']=name+'/assert-'+str(proof.pop('index'))
                    _require(all(_equal(row.get(key),value) for key,value in proof.items()),'assertion differs from independently evaluated actual native result')
                semantic='passed' if all(row['outcome']=='passed' for row in expected) else 'failed'
                _require(status==semantic,'transport masked the original assertion verdict')
            else:
                _require(step.get('observe') is True and status=='passed' and len(finals)==1 and finals[0].get('assertionRole')=='transport' and
                    finals[0].get('check')=='transport.receipt-recorded' and finals[0].get('actual') is True,'observation was promoted into a business assertion')
                semantic='observed'
            _require(results[0].get('semanticResult')==semantic and results[0].get('semanticRole')==roles[name] and results[0].get('stepIndex')==index,
                     'original semantic result/role/index metadata changed')
        elif status=='not_run':
            _require(not case_actions and not finals,'not_run step has actual actions/assertions');semantic='not_run'
            if results:_require(results[0].get('semanticResult')=='not_run' and results[0].get('semanticRole')==roles[name] and results[0].get('stepIndex')==index,'not_run original role changed')
        else:
            _require(status=='unavailable','unknown semantic status');semantic='unavailable'
        checks.append({'name':name,'role':roles[name],'result':semantic,'asserted':bool(step.get('assert')),
                       'executed':any(action.get('deliveredEvidence') for action in case_actions),'attempts':len(case_actions)})
    _require(all(action['caseId'] in names or action['envelope']=={'schemaVersion':1,'operation':'finish'} for action in actions),'extra undeclared command')
    pins={item['path']:item for item in transport['pins']}
    for value in plan['pins']:
        path=Path(value['path']);item={'path':str(path),'sha256':value['sha256'],'bytes':path.stat().st_size}
        pins[str(path)]=item
    return {'checks':checks,'subjectStarted':subject_boundary is not None,'actualSubjectBoundary':subject_boundary,
        'transportBoundary':report.get('subjectStart'),'transportStarted':transport['subjectStarted'],
        'originalTesting':copy.deepcopy(order['testing']),'subjectOrderSha256':plan['subjectOrderSha256'],
        'completed':transport['completed'],'uncertain':transport['uncertain'],
        'planCompleted':transport['completed'] and not transport['uncertain'] and all(row['result'] in ('passed','observed') for row in checks),
        'executedStepCount':sum(row['executed'] for row in checks),'observedStepCount':sum(row['result']=='observed' for row in checks),
        'assertedSubjectCheckCount':sum(row['role']=='subject' and row['asserted'] for row in checks),
        'pins':sorted(pins.values(),key=lambda item:item['path'])}


def projection(p,order,packet):
    current=collect(p,order,packet['runDirectory'])
    _require(packet.get('heldSemantic')==current,'retained held semantic summary changed')
    pins={str(Path(value['path']).resolve()):value for value in packet['files']}
    for value in current['pins']:_require(pins.get(str(Path(value['path']).resolve()))==value,'held evidence absent from packet')
    return current


def complete_projection(result,order,packet,summary):
    """Narrow observation completion rule; no legacy result semantics change."""
    by_name={row['name']:row for row in summary['checks']}
    for row in result['coverage']['checks']:
        if row['name'] in by_name:
            source=by_name[row['name']]
            row.update(status=source['result'],asserted=source['asserted'],executed=source['executed'])
    coverage=result['coverage'];rows=coverage['checks']
    coverage.update({status:sum(row['status']==status for row in rows) for status in ('passed','failed','not_run','unavailable','observed')})
    coverage.update(executed=summary['executedStepCount'],observed=summary['observedStepCount'])
    subject=[row for row in rows if row['role']=='subject' and row.get('asserted')]
    result['assertionCoverage']={'required':len(subject),'passed':sum(row['status']=='passed' for row in subject),
        'failed':sum(row['status']=='failed' for row in subject),'checks':subject}
    measurements=[row for row in rows if not row.get('asserted')]
    result['measurementCoverage']={'required':len(measurements),'observed':summary['observedStepCount'],
        'byRole':{role:sum(row['role']==role and row['status']=='observed' for row in measurements) for role in ('subject','fixture','tooling')},
        'checks':measurements}
    result['transportBoundary']=summary['transportBoundary'];result['actualSubjectBoundary']=summary['actualSubjectBoundary']
    result['testingStarted']=summary['subjectStarted']
    if not summary['subjectStarted']:result['outcome']='not_started'
    elif any(row['status']=='failed' for row in subject):result['outcome']='tested_with_errors'
    elif (summary['planCompleted'] and subject and all(row['status']=='passed' for row in subject) and packet['executionOutcome']=='passed' and
          not result.get('interruptionObserved') and not result.get('subjectMismatchObserved') and
          all(row['status']=='passed' for row in result['auxiliaryCoverage']['checks'])):
        result['outcome']='tested_successfully'
    elif summary['uncertain'] or not summary['completed']:result['outcome']='interrupted_external'
    return result
