"""Operator-selected held execution of an unchanged ordinary semantic order.

The file-plan view is a private transport protocol, never a replacement subject
order or a source of factual mod-start/role metadata.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import time

import subject_companion_route as companion
import subject_contract as contract


def api():
    import polygon
    return polygon


def init(p):
    with p.connect() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS held_semantic_bindings
          (id TEXT PRIMARY KEY, request TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS held_semantic_admissions (id TEXT PRIMARY KEY, review TEXT NOT NULL);''')


def selected(p, order, con=None):
    if order.get('schemaVersion') != 2 or order.get('subjectPlan',{}).get('interface') != contract.INTERFACE:
        return False
    if con is None:
        with p.connect() as connection:return selected(p,order,connection)
    return con.execute('SELECT id FROM held_semantic_bindings WHERE id=?',(order['id'],)).fetchone() is not None


def normalize(path):
    m=api();path=Path(path).resolve();r=m.read(path)
    fields={'schemaVersion','kind','orderId','subjectOrderSha256','executor','configuration','transport','qualificationId',
        'baselinePacket','holdId','ownerAuthorization','subjectCapabilitiesUnderTest','verifiedBy','reason',
        'mappingManifest','compiledProgram','sequencer','sequencerModule','executionPlan','maximumSeconds'}
    if set(r)!=fields or r.get('schemaVersion')!=1 or r.get('kind')!='operator-held-semantic':
        raise ValueError('Exact operator-held-semantic selection required')
    for key in ('orderId','qualificationId','holdId'):
        if not isinstance(r[key],str) or not m.SAFE_ID.fullmatch(r[key]):raise ValueError('Safe exact held identities required')
    if r['subjectCapabilitiesUnderTest'] is not True or type(r['maximumSeconds']) is not int or not 1<=r['maximumSeconds']<=1200:
        raise ValueError('Explicit capabilities-under-test and finite1..1200 held window required')
    for key in ('verifiedBy','reason'):m.required_string(r,key)
    m.owner_evidence(r,path,require_deadline=False)
    r['executor']=str((path.parent/m.required_string(r,'executor')).resolve())
    for key in ('configuration','transport','baselinePacket','mappingManifest','compiledProgram','sequencer','sequencerModule','executionPlan'):
        value=r[key]
        if type(value) is not dict or set(value)!={'path','sha256'}:raise ValueError('Exact held input pin required')
        value['path']=str((path.parent/value['path']).absolute());value['path']=str(companion.pin(value))
    return r


def find(p,order,con=None):
    m=api()
    if con is None:
        with p.connect() as connection:return find(p,order,connection)
    row=con.execute('SELECT * FROM held_semantic_bindings WHERE id=?',(order['id'],)).fetchone()
    if not row:return None
    path=companion.pin({'path':row['path'],'sha256':row['sha256']});r=normalize(path)
    if json.dumps(r,sort_keys=True)!=row['request'] or r['subjectOrderSha256']!=contract.identity(order):
        raise ValueError('Immutable semantic order/held selection changed')
    return {'request':{'path':str(path),'sha256':row['sha256']},**r}


def baseline(p,selection):
    q,packet,state,worker=companion.baseline(p,selection)
    summary=packet.get('toolCompanion',{})
    if (not q.get('companion') or summary.get('scope')!='tool-qualification-only' or summary.get('completed') is not True or
            summary.get('uncertain') is not False or summary.get('subjectStarted') is not True or not summary.get('checks') or
            any(row.get('result')!='passed' for row in summary['checks'])):
        raise ValueError('Successful released new held/native component qualification required')
    if selection['transport']!=q['companion'].get('transport'):
        raise ValueError('Held protocol transport must remain byte-identical to the actual qualified transport')
    return q,packet,state,worker


def compiled(order,selection,q):
    m=api();manifest_path=companion.pin(selection['mappingManifest']);manifest=m.read(manifest_path)
    if manifest.get('schemaVersion')!=1 or manifest.get('interface')!=contract.INTERFACE or type(manifest.get('operations')) is not dict:
        raise ValueError('Explicit held semantic mapping manifest required')
    qualification=dict(manifest.get('qualification',{}));qualification['path']=str((manifest_path.parent/qualification.get('path','')).absolute())
    proof=m.read(companion.pin(qualification))
    if (proof.get('qualified') is not True or proof.get('interface')!=contract.INTERFACE or proof.get('operations')!=manifest['operations'] or
            selection['baselinePacket'] not in proof.get('evidence',[]) or
            proof.get('configurationSha256')!=contract.identity(q['configuration'])):
        raise ValueError('Mapping needs exact reviewed successful composition evidence/configuration')
    declared={(x['path'],x['sha256']) for x in proof.get('pins',[])}
    if not all((x['path'],x['sha256']) in declared for x in q['executorPins']):
        raise ValueError('Mapping qualification lacks the exact frozen executor pins')
    for value in proof.get('pins',[]):companion.pin(value)
    scenario=contract.compile_plan(order['subjectPlan'],manifest['operations'])
    if m.read(companion.pin(selection['compiledProgram']))!=scenario:
        raise ValueError('Compiled native program differs from unchanged semantic order/mapping')
    if order.get('testing',{}).get('start',{}).get('kind')!='check':
        raise ValueError('Held semantic factual boundary must be one original named check')
    names=[step['name'] for step in scenario['steps']]
    if [row['name'] for row in order['testing']['checks']]!=names or 'held-semantic-core-preparation' in names:
        raise ValueError('Original testing roles must cover every compiled checkpoint exactly')
    return scenario,qualification


def configuration(p,order,selection,q):
    from order_platform import isolated_config
    cfg=isolated_config(selection['executor'],companion.pin(selection['configuration']),core_scenario(order))
    prior=isolated_config(selection['executor'],Path(q['configPath']),core_scenario(order))
    if (cfg.get('game_edition')!='se' or cfg.get('se_new_game_ui') is not True or cfg.get('root_builder') or cfg.get('reuse_test_profile')):
        raise ValueError('Held semantic route requires the unchanged cold-owned SE startup')
    if {k:v for k,v in cfg.items() if k not in {'runtime','interactive_session'}}!={k:v for k,v in prior.items() if k not in {'runtime','interactive_session'}}:
        raise ValueError('Qualified native provider/staging/core configuration changed')
    current,old=cfg.get('interactive_session',{}),prior.get('interactive_session',{})
    if {k:v for k,v in current.items() if k!='maximumSeconds'}!={k:v for k,v in old.items() if k!='maximumSeconds'}:
        raise ValueError('Qualified held channel, native policy or morph/persistence configuration changed')
    if current.get('maximumSeconds')!=selection['maximumSeconds'] or not current.get('nativeBindings'):
        raise ValueError('Reviewed held window differs from exact configuration')
    if Path(cfg['runtime']).resolve()==Path(prior['runtime']).resolve():raise ValueError('A fresh isolated runtime is required')
    return cfg


def core_scenario(order):
    fixture=order['subjectPlan']['fixture']
    if fixture.get('startMode')!='new-game' or 'save' in fixture:raise ValueError('Current held composition qualifies New Game fixture only')
    return {'schemaVersion':1,**fixture,'steps':[{'name':'held-semantic-core-preparation','tool':'platform',
        'args':{'operation':'state.read'},'timeout':20,'assert':[{'path':'world.ready','equals':True}]}]}


def same_pin(value,expected):
    if (type(value) is not dict or set(value)-{'path','sha256','bytes'} or
            {key:value.get(key) for key in ('path','sha256')}!=expected):return False
    return 'bytes' not in value or (type(value['bytes']) is int and value['bytes']==Path(expected['path']).stat().st_size)


def materialize(p,order,selection,scenario):
    m=api();execution=m.read(companion.pin(selection['executionPlan']));spec=execution.get('semantic',{})
    expected_checks=[{'name':step['name'],'role':'subject'} for step in scenario['steps']]
    provenance=spec.get('provenance',{})
    order_input=provenance.get('order',{})
    order_pin={key:order_input.get(key) for key in ('path','sha256')} if isinstance(order_input,dict) else {}
    if not same_pin(order_input,order_pin):raise ValueError('Original semantic provenance pin differs')
    required={'checks','fixture','bounds','semantic'}
    if (not required<=set(execution) or set(execution)-required-{'schemaVersion','kind','protocolBoundaryMeaning'} or
            ('schemaVersion' in execution and execution['schemaVersion']!=1) or ('kind' in execution and execution['kind']!='held-semantic-plan') or
            execution['checks']!=expected_checks or execution['fixture'] not in (order['subjectPlan']['fixture'],{'cell':scenario.get('cell')}) or
            spec.get('schemaVersion')!=1 or spec.get('interface')!='held-semantic-plan/1' or
            spec.get('subjectOrderSha256')!=contract.identity(order) or spec.get('originalTesting')!=order['testing'] or spec.get('scenario')!=scenario or
            execution['bounds']!=spec.get('bounds') or execution['bounds'].get('maximumSeconds')!=selection['maximumSeconds'] or
            type(execution['bounds'].get('maximumCommands')) is not int or not len(scenario['steps'])+1<=execution['bounds']['maximumCommands']<=2048 or
            not same_pin(provenance.get('mappingManifest'),selection['mappingManifest']) or not same_pin(provenance.get('compiledScenario'),selection['compiledProgram']) or
            provenance.get('sourcePlanSha256')!=contract.identity(order['subjectPlan']) or
            contract.identity(m.read(companion.pin(order_pin)))!=contract.identity(order)):
        raise ValueError('Held execution wrapper differs from unchanged original order/compiled program/provenance')
    module=selection['sequencerModule']
    code="import hashlib,importlib.util,json,sys;from pathlib import Path;p=Path(sys.argv[1]);assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2];s=importlib.util.spec_from_file_location('held_renderer',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);sys.stdout.buffer.write(m.render(json.load(sys.stdin)).encode('utf-8'))"
    rendered=subprocess.run([sys.executable,'-B','-c',code,module['path'],module['sha256']],
        input=json.dumps(spec).encode('utf-8'),capture_output=True,timeout=30,shell=False)
    if rendered.returncode or rendered.stdout!=companion.pin(selection['sequencer']).read_bytes():
        raise ValueError('Pinned generic sequencer differs from exact deterministic compiled specification: '+rendered.stderr[-1000:].decode('utf-8','replace'))
    return selection['executionPlan'],spec


def protocol_order(order,plan):
    result=copy.deepcopy(order);spec=plan['heldSemanticSelection']
    names=[step['name'] for step in plan['compiledProgram']['steps']]
    result['subjectPlan']={'interface':contract.FILE_INTERFACE,'fixture':copy.deepcopy(order['subjectPlan']['fixture']),
        'plan':plan['transportPlan'],'sequencer':spec['sequencer'],'checks':names,'maximumSeconds':spec['maximumSeconds']}
    result['testing']={'start':{'kind':'check','name':names[0]},'checks':[{'name':name,'role':'subject'} for name in names]}
    result['inputs']+= [{**plan['transportPlan'],'role':'fixture'},{**spec['sequencer'],'role':'fixture'}]
    return result


def register(p,path):
    m=api();path=Path(path).resolve();selection=normalize(path);key=selection['orderId'];row=p.get(key);order=json.loads(row['request'])
    if (order.get('schemaVersion')!=2 or order.get('subjectPlan',{}).get('interface')!=contract.INTERFACE or order.get('cycle') or
            order.get('mode')!='automatic' or row['status']!='queued' or selection['subjectOrderSha256']!=contract.identity(order)):
        raise ValueError('Only an untouched immutable first ordinary semantic order may select held execution')
    q,_,_,_=baseline(p,selection);program,_=compiled(order,selection,q);configuration(p,order,selection,q)
    materialize(p,order,selection,program);p.verify_inputs(order)
    canonical=json.dumps(selection,sort_keys=True)
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        prior=con.execute('SELECT * FROM held_semantic_bindings WHERE id=?',(key,)).fetchone()
        if prior:
            if (prior['request'],prior['path'],prior['sha256'])!=(canonical,str(path),m.digest(path)):raise ValueError('Held selection is immutable')
            return {'id':key,'duplicate':True,'launch':False}
        current=con.execute('SELECT status,request FROM jobs WHERE id=?',(key,)).fetchone()
        if not current or current['status']!='queued' or current['request']!=row['request']:raise ValueError('Queued semantic order changed')
        if (con.execute('SELECT id FROM attempts WHERE id=?',(key,)).fetchone() or con.execute('SELECT id FROM platform_attempts WHERE id=?',(key,)).fetchone() or
                con.execute('SELECT order_id FROM session_members WHERE order_id=?',(key,)).fetchone() or
                con.execute('SELECT id FROM operator_platform_bindings WHERE order_id=?',(key,)).fetchone()):raise ValueError('Prepared/dispatched/grouped order cannot bind held execution')
        if p.qualification_busy(con) or con.execute("SELECT id FROM qualifications WHERE status IN ('prepared','running')").fetchone():raise ValueError('Active owner retains admission barrier')
        if [x['id'] for x in con.execute('SELECT id FROM pipeline_holds')]!=[selection['holdId']]:raise ValueError('Exact sole preparation hold required')
        con.execute('INSERT INTO held_semantic_bindings VALUES(?,?,?,?)',(key,canonical,str(path),m.digest(path)))
        p.event(con,key,'held_semantic_bound',canonical)
    return {'id':key,'launch':False,'subjectOrderSha256':contract.identity(order),'globalHostChanged':False}


def admission(p,key):
    with p.connect() as con:row=con.execute('SELECT review FROM held_semantic_admissions WHERE id=?',(key,)).fetchone()
    if not row:return None
    saved=json.loads(row['review']);pin={'path':saved['path'],'sha256':saved['sha256']}
    if api().read(companion.pin(pin))!=saved['review']:raise ValueError('Held admission review changed')
    api().owner_evidence(saved['review'],Path(saved['path']),require_deadline=False)
    return pin


def freeze(p,order,attempt_id=None):
    if attempt_id is not None:raise ValueError('Held semantic retry requires separate supported admission; no fallback')
    m=api();selection=find(p,order);q,_,_,_=baseline(p,selection)
    program,mapping_proof=compiled(order,selection,q);cfg=configuration(p,order,selection,q);review=admission(p,order['id'])
    if not review:raise ValueError('Atomic held semantic admission required')
    transport_plan,spec=materialize(p,order,selection,program)
    pins=[]
    def add(value):
        item={'path':str(companion.pin({key:value[key] for key in ('path','sha256')})),'sha256':value['sha256']}
        if item not in pins:pins.append(item)
    for value in q['executorPins']+q['pins']:add(value)
    for key in ('request','configuration','transport','baselinePacket','mappingManifest','compiledProgram','sequencer','sequencerModule','executionPlan'):add(selection[key])
    add(mapping_proof);add(review);add(transport_plan);add(spec['provenance']['order'])
    auth=selection['ownerAuthorization'];add({'path':auth['path'],'sha256':auth['sha256']})
    for file in sorted(m.HERE.glob('*.py')):add({'path':str(file),'sha256':m.digest(file)})
    companion.validate_core_overlaps(order,q,cfg,pins)
    plan={'schemaVersion':1,'interface':'held-semantic-plan/1','orderId':order['id'],'subjectOrderSha256':contract.identity(order),
        'subjectSpecificationSha256':contract.subject_identity(order),'originalTesting':copy.deepcopy(order['testing']),
        'executor':selection['executor'],'configuration':cfg,'scenario':core_scenario(order),'compiledProgram':program,
        'transportPlan':transport_plan,'heldSemanticSelection':selection,'companionSelection':selection,'heldSemanticAdmission':review,
        'pins':pins,'executorPins':q['executorPins'],'preparedAt':time.time(),'subjectCapabilitiesQualified':False}
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT status FROM jobs WHERE id=?',(order['id'],)).fetchone()[0]!='running':raise ValueError('Held preparation requires atomic original claim')
        con.execute('INSERT INTO platform_attempts VALUES(?,?,?)',(order['id'],json.dumps(plan,sort_keys=True),contract.identity(plan)))
    m.write(p.evidence_dir(order['id'])/'platform-plan.json',plan)
    return verify(p,order)


def verify(p,order,require_file=True,attempt_id=None):
    if attempt_id is not None:raise ValueError('No implicit held semantic continuation')
    m=api();plan=p.attempt_plan(order)
    if (plan.get('heldSemanticSelection')!=find(p,order) or plan.get('heldSemanticAdmission')!=admission(p,order['id']) or
            plan.get('subjectOrderSha256')!=contract.identity(order) or plan.get('originalTesting')!=order['testing']):raise ValueError('Held attempt/order/admission provenance changed')
    if require_file and m.read(p.evidence_dir(order['id'])/'platform-plan.json')!=plan:raise ValueError('Held attempt file changed')
    for value in plan['pins']:companion.pin(value)
    from qualification import inventory
    if inventory(plan['executor'])!=plan['executorPins']:raise ValueError('Frozen qualified held executor changed')
    q,_,_,_=baseline(p,plan['heldSemanticSelection'])
    program,_=compiled(order,plan['heldSemanticSelection'],q)
    transport,spec=materialize(p,order,plan['heldSemanticSelection'],program)
    if program!=plan['compiledProgram'] or transport!=plan['transportPlan'] or configuration(p,order,plan['heldSemanticSelection'],q)!=plan['configuration']:
        raise ValueError('Held compiled/configuration materialization changed')
    return plan


def run(p,order,plan,runner):
    verify(p,order)
    return companion.run(p,protocol_order(order,plan),plan,runner)


def execute(p,path):
    """Consume only the same current human release and exact preparation hold."""
    m=api();path=Path(path).resolve();r=m.read(path)
    required={'schemaVersion','kind','orderId','binding','baselinePacket','ownerAuthorization','verifiedBy','reason',
        'preparationReviewed','restorationReviewed','archiveReviewed','exactOnlySubjectReviewed','subjectCapabilitiesUnderTest'}
    if (set(r)!=required or r.get('schemaVersion')!=1 or r.get('kind')!='operator-held-semantic-admission' or
            any(r.get(key) is not True for key in required if key.endswith('Reviewed') or key=='subjectCapabilitiesUnderTest')):raise ValueError('Explicit exact held admission review required')
    m.owner_evidence(r,path,require_deadline=False)
    for key in ('verifiedBy','reason'):m.required_string(r,key)
    from order_platform import authority,activate
    order=json.loads(p.get(r['orderId'])['request']);selection=find(p,order)
    if not selection or r['binding']!=selection['request'] or r['baselinePacket']!=selection['baselinePacket'] or authority(r)!=authority(selection):raise ValueError('Exact current held selection/authority required')
    canonical=json.dumps({'path':str(path),'sha256':m.digest(path),'review':r},sort_keys=True)
    with p.connect() as con:prior=con.execute('SELECT review FROM held_semantic_admissions WHERE id=?',(order['id'],)).fetchone()
    if prior:
        if prior['review']!=canonical:raise ValueError('Held admission is immutable')
        return {'id':order['id'],'status':'already_admitted','rerun':False}
    q,_,state,worker=baseline(p,selection);program,_=compiled(order,selection,q);cfg=configuration(p,order,selection,q)
    runner=activate(selection['executor'])
    with runner.native.SessionMutex(),p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if find(p,order,con)!=selection:raise ValueError('Held selection changed before admission')
        current_baseline=con.execute('SELECT * FROM qualifications WHERE id=?',(selection['qualificationId'],)).fetchone()
        if not current_baseline or current_baseline['status']!='released' or json.loads(current_baseline['packet'])!=selection['baselinePacket']:
            raise ValueError('Released held baseline changed before atomic admission')
        p.qualification_verify(dict(current_baseline),authority=False)
        if p.qualification_busy(con) or con.execute("SELECT id FROM qualifications WHERE status IN ('prepared','running')").fetchone():raise ValueError('Another active owner retains barrier')
        if [x['id'] for x in con.execute('SELECT id FROM pipeline_holds')]!=[selection['holdId']]:raise ValueError('Exact sole held preparation hold required')
        waiting=con.execute("SELECT j.id,r.release_id FROM jobs j JOIN released_orders r ON r.id=j.id WHERE j.status IN ('queued','running','waiting_player','session_waiting')").fetchall()
        if len(waiting)!=1 or waiting[0]['id']!=order['id'] or p.get(order['id'])['status']!='queued':raise ValueError('Only exact currently released queued order may enter held execution')
        release=con.execute('SELECT authorization FROM releases WHERE id=?',(waiting[0]['release_id'],)).fetchone()
        if authority(json.loads(release[0]))!=authority(r):raise ValueError('Current exact human one-shot release required')
        if (con.execute("SELECT id FROM retry_attempts WHERE status='queued'").fetchone() or con.execute("SELECT id FROM game_sessions WHERE status='queued'").fetchone() or
                con.execute("SELECT id FROM jobs WHERE status IN ('queued','session_waiting') AND json_extract(request,'$.cycle') IS NOT NULL").fetchone()):raise ValueError('Other queued retry/shared/cycle work retains barrier')
        rows=runner.native.processes()
        if not isinstance(rows,list) or not rows or any(row['name'].lower() in {'skyrimse.exe','skyrimvr.exe','skse64_loader.exe','sksevr_loader.exe','vrserver.exe','vrcompositor.exe'} for row in rows):raise ValueError('Current game/VR blocks held admission')
        for ident in [worker]+[row['identity'] for row in state.get('owned',[])]:
            if runner.native.alive(ident) or any(row['pid']==ident['pid'] and runner.native.identity(ident['pid']) is None for row in rows):raise ValueError('Baseline native owner alive or identity unavailable')
        runtimes={Path(cfg['runtime']),Path(q['configuration']['runtime'])}
        if p.host().get('runnerConfig'):runtimes.add(Path(m.read(p.host()['runnerConfig'])['runtime']))
        for runtime in runtimes:
            if any(m.read(file).get('done') is not True for file in (runtime/'runs').glob('*/state.json')):raise ValueError('Unfinished native session retains hold')
        if m.digest(path)!=json.loads(canonical)['sha256']:raise ValueError('Held admission changed')
        p.verify_inputs(order)
        con.execute('DELETE FROM pipeline_holds WHERE id=?',(selection['holdId'],))
        p.check_launch_authorization(order,connection=con)
        con.execute("UPDATE jobs SET status='running',note='' WHERE id=?",(order['id'],))
        con.execute('INSERT INTO held_semantic_admissions VALUES(?,?)',(order['id'],canonical))
        p.event(con,order['id'],'held_semantic_admitted',canonical)
        row=dict(con.execute('SELECT * FROM jobs WHERE id=?',(order['id'],)).fetchone())
    return p.execute_claimed(row)
