"""Operator-only immutable solo attempt selection and atomic reviewed admission."""
import json
from pathlib import Path
import subprocess
import sys
import time


def api():
    import polygon
    return polygon


def init(p):
    with p.connect() as con:
        con.executescript("""CREATE TABLE IF NOT EXISTS operator_platform_bindings
          (id TEXT PRIMARY KEY, order_id TEXT NOT NULL, request TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operator_bound_admissions
          (id TEXT PRIMARY KEY, review TEXT NOT NULL);""")


def pin(value):
    m=api();path=Path(value['path']).resolve()
    if m.digest(path)!=value.get('sha256'):raise ValueError('Operator selection pin changed: '+str(path))
    return path


def authority(value):
    a=value['ownerAuthorization']
    return {k:a[k] for k in ('threadId','messageId','quote','path','sha256')}


def normalize(path):
    m=api();r=m.read(path)
    allowed={'schemaVersion','kind','orderId','subjectOrderSha256','executor','platformManifest','qualificationId','holdId','verifiedBy','reason','ownerAuthorization'}
    if set(r)!=allowed or r['schemaVersion']!=1 or r['kind']!='operator-order-platform':raise ValueError('Exact operator platform request required')
    for k in ('orderId','qualificationId'):
        if not m.SAFE_ID.fullmatch(r[k]):raise ValueError('Safe exact order/qualification identity required')
    if r['holdId']!='qualification-'+r['qualificationId']:raise ValueError('Exact completed qualification hold required')
    for k in ('verifiedBy','reason'):m.required_string(r,k)
    m.owner_evidence(r,path,require_deadline=False)
    r['executor']=str((path.parent/m.required_string(r,'executor')).resolve())
    r['platformManifest']['path']=str((path.parent/r['platformManifest']['path']).resolve())
    pin(r['platformManifest'])
    return r


def find(p, order, attempt_id=None, con=None):
    m=api()
    if con is None:
        with p.connect() as c:return find(p,order,attempt_id,c)
    row=con.execute('SELECT * FROM operator_platform_bindings WHERE order_id=?',(order['id'],)).fetchone()
    if not row:return None
    if attempt_id:raise ValueError('Bound solo order needs a separately supported new-attempt binding; no global fallback')
    path=pin({'path':row['path'],'sha256':row['sha256']});r=normalize(path)
    if json.dumps(r,sort_keys=True,ensure_ascii=False)!=row['request'] or r['subjectOrderSha256']!=m.subject_contract.identity(order):raise ValueError('Operator selection/order changed')
    return {'request':{'path':str(path),'sha256':row['sha256']},'executor':r['executor'],
            'manifestPath':r['platformManifest']['path'],'qualificationId':r['qualificationId'],'holdId':r['holdId']}


def admission(p, key):
    m=api()
    with p.connect() as con:row=con.execute('SELECT review FROM operator_bound_admissions WHERE id=?',(key,)).fetchone()
    if not row:return None
    saved=json.loads(row['review']);value={'path':saved['path'],'sha256':saved['sha256']}
    if m.read(pin(value))!=saved['review']:raise ValueError('Atomic admission review changed')
    return value


def register(p,path):
    m=api();path=Path(path).resolve();r=normalize(path);key=r['orderId']
    canonical=json.dumps(r,sort_keys=True,ensure_ascii=False)
    manifest_path=pin(r['platformManifest']);manifest=m.read(manifest_path);qpin=dict(manifest['qualification']);qpin['path']=str((manifest_path.parent/qpin['path']).resolve());q=m.read(pin(qpin))
    if q.get('qualified') is not True or q.get('operations')!=manifest.get('operations'):raise ValueError('Actual reviewed qualified mapping required')
    if not (Path(r['executor'])/'run.py').is_file():raise ValueError('Exact frozen executor required')
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        prior=con.execute('SELECT * FROM operator_platform_bindings WHERE id=?',(key,)).fetchone()
        if prior:
            if prior['request']!=canonical or prior['path']!=str(path) or prior['sha256']!=m.digest(path):raise ValueError('Operator selection is immutable')
            find(p,json.loads(p.get(key)['request']),con=con)
            return {'id':key,'duplicate':True,'launch':False}
        row=con.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
        if not row or row['status']!='queued':raise ValueError('Only an untouched queued order can select a platform')
        order=json.loads(row['request'])
        if order.get('schemaVersion')!=2 or order.get('mode')!='automatic' or order.get('cycle'):raise ValueError('Only solo schema2 automatic first attempts are supported')
        if r['subjectOrderSha256']!=m.subject_contract.identity(order):raise ValueError('Exact submitted order hash required')
        if con.execute('SELECT id FROM platform_attempts WHERE id=?',(key,)).fetchone() or con.execute('SELECT id FROM attempts WHERE id=?',(key,)).fetchone() or con.execute('SELECT order_id FROM session_members WHERE order_id=?',(key,)).fetchone():raise ValueError('Already prepared/dispatched/grouped order cannot select tools')
        if p.qualification_busy(con) or con.execute("SELECT id FROM qualifications WHERE status IN ('prepared','running')").fetchone():raise ValueError('Active owner blocks operator selection')
        holds=[x['id'] for x in con.execute('SELECT id FROM pipeline_holds')]
        if holds!=[r['holdId']]:raise ValueError('Retain the exact sole completed qualification hold until atomic admission')
        nativeq=con.execute('SELECT * FROM qualifications WHERE id=?',(r['qualificationId'],)).fetchone()
        if not nativeq or nativeq['status']!='recorded' or authority(json.loads(nativeq['request']))!=authority(r):raise ValueError('Same-owner completed composition qualification required')
        qp=json.loads(nativeq['request']);packetpin=json.loads(nativeq['packet'])
        if packetpin not in q.get('evidence',[]):raise ValueError('Mapping must retain this exact factual composition qualification')
        if r['executor']!=qp['executor']:raise ValueError('Mapping executor differs from actual qualification')
        scenario=m.subject_contract.compile_plan(order['subjectPlan'],manifest['operations'])
        cfg=isolated_config(r['executor'],(manifest_path.parent/manifest['config']).resolve(),scenario)
        if cfg!=qp['configuration'] or q.get('configurationSha256')!=m.subject_contract.identity(cfg):raise ValueError('Mapping configuration differs from actual qualified composition')
        con.execute('INSERT INTO operator_platform_bindings VALUES(?,?,?,?,?)',(key,key,canonical,str(path),m.digest(path)))
        p.event(con,key,'operator_platform_bound',canonical)
    return {'id':key,'launch':False,'globalHostChanged':False}


def isolated_config(executor,config,scenario):
    # No parent module-cache reuse when global VR was imported earlier.
    code="import sys,json;from pathlib import Path;r=Path(sys.argv[1]).resolve();sys.path.insert(0,str(r));from skyrim_autotest import config,scenarios;assert Path(config.__file__).resolve()==r/'skyrim_autotest/config.py' and Path(scenarios.__file__).resolve()==r/'skyrim_autotest/scenarios.py','Wrong selected module';x=json.load(sys.stdin);v=config.load(x['config']);scenarios.validate(x['scenario']);print(json.dumps(v))"
    child=subprocess.run([sys.executable,'-c',code,str(executor)],input=json.dumps({'config':str(config),'scenario':scenario}),capture_output=True,text=True,timeout=30)
    if child.returncode:raise ValueError('Selected executor validation failed: '+child.stderr[-3000:])
    return json.loads(child.stdout)


def activate(executor):
    root=Path(executor).resolve()
    for name,module in list(sys.modules.items()):
        if name=='skyrim_autotest' or name.startswith('skyrim_autotest.'):
            file=getattr(module,'__file__',None)
            if not file or not Path(file).resolve().is_relative_to(root):raise ValueError('Mixed cached executor; use a fresh supported child')
    sys.path.insert(0,str(root))
    from skyrim_autotest import runner
    if Path(runner.__file__).resolve()!=root/'skyrim_autotest/runner.py':raise ValueError('Wrong selected runner imported')
    return runner


def execute(p,path):
    """Transfer only this completed tool hold into this exact released subject claim."""
    m=api();path=Path(path).resolve();r=m.read(path)
    if r.get('schemaVersion')!=1 or r.get('kind')!='operator-bound-subject-admission':raise ValueError('Exact reviewed subject admission required')
    m.owner_evidence(r,path,require_deadline=False)
    if any(r.get(k) is not True for k in ('successfulQualificationReviewed','restorationReviewed','archiveReviewed','exactOnlySubjectReviewed')):raise ValueError('Independent completion and exact-target review required')
    for k in ('verifiedBy','reason'):m.required_string(r,k)
    key=r['orderId'];order=json.loads(p.get(key)['request']);sel=find(p,order)
    if not sel:raise ValueError('No explicit operator platform binding')
    pin(r['binding']);
    if r['binding']!=sel['request']:raise ValueError('Exact binding review required')
    packet=p.qualification_collect(sel['qualificationId']);pin(r['packet'])
    if m.read(r['packet']['path'])!=packet:raise ValueError('Exact collected qualification packet required')
    qrow=p.qualification_show(sel['qualificationId']);plan=p.qualification_verify(qrow,authority=False)
    if r['packet']!=json.loads(qrow['packet']):raise ValueError('Exact registered qualification packet pin required')
    if qrow['status']!='recorded' or not p.qualification_successful_result(plan,packet) or packet.get('actualGameStarts')!=1 or packet.get('restored') is not True or not packet.get('collectionFinished') or packet.get('collectionFindings'):raise ValueError('Successful fully collected/restored single-game qualification required')
    if authority(r)!=authority(plan):raise ValueError('Same actual owner scope required')
    run=Path(packet['runDirectory']);state=m.read(run/'state.json');worker=m.read(p.local/'qualifications'/sel['qualificationId']/'worker.json')['identity']
    child=m.read(p.local/'qualifications'/sel['qualificationId']/'child-exit.json')
    if type(child.get('returncode')) is not int or child['returncode']!=0 or child.get('timeout') or state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors') or p.native_game_starts(state)!=1:raise ValueError('Exact successful ended native run required')
    if state.get('runner')!=worker or state.get('order',{}).get('id')!='qualification-'+sel['qualificationId']:raise ValueError('Exact qualification worker/order required')
    archive=run/'test-profile';actual=[{'path':str(f),'sha256':m.digest(f)} for f in sorted(archive.rglob('*')) if f.is_file()]
    if not actual or actual!=packet.get('profileArchivePins') or Path(state.get('profileArchive','')).resolve()!=archive.resolve() or Path(state['testProfile']).exists():raise ValueError('Exact archived/removed profile required')
    p.check_launch_authorization(order);p.verify_inputs(order)
    canonical=json.dumps({'path':str(path),'sha256':m.digest(path),'review':r},sort_keys=True,ensure_ascii=False)
    runner=activate(sel['executor'])
    with runner.native.SessionMutex(),p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        prior=con.execute('SELECT review FROM operator_bound_admissions WHERE id=?',(key,)).fetchone()
        if prior:
            if prior['review']!=canonical:raise ValueError('Admission review is immutable')
            return {'id':key,'status':'already_admitted','rerun':False}
        if find(p,order,con=con)!=sel:raise ValueError('Binding changed before admission')
        current=con.execute('SELECT * FROM qualifications WHERE id=?',(sel['qualificationId'],)).fetchone()
        if not current or current['status']!='recorded' or current['request']!=qrow['request'] or current['packet']!=qrow['packet']:raise ValueError('Qualification completion changed before admission')
        p.qualification_verify(dict(current),authority=False)
        if p.qualification_busy(con) or con.execute("SELECT id FROM qualifications WHERE status IN ('prepared','running')").fetchone():raise ValueError('Another active owner blocks admission')
        holds=[x['id'] for x in con.execute('SELECT id FROM pipeline_holds')]
        if holds!=[sel['holdId']]:raise ValueError('Exact sole completed tool hold required')
        waiting=con.execute("SELECT j.id,j.request,r.release_id FROM jobs j JOIN released_orders r ON r.id=j.id WHERE j.status IN ('queued','running','waiting_player','session_waiting')").fetchall()
        if len(waiting)!=1 or waiting[0]['id']!=key or con.execute('SELECT status FROM jobs WHERE id=?',(key,)).fetchone()[0]!='queued':raise ValueError('Only the exact reviewed queued subject may become runnable')
        release=con.execute('SELECT authorization FROM releases WHERE id=?',(waiting[0]['release_id'],)).fetchone()
        if not release or authority(json.loads(release[0]))!=authority(r):raise ValueError('Same one-shot subject owner release required')
        if con.execute("SELECT id FROM jobs WHERE status IN ('queued','session_waiting') AND json_extract(request,'$.cycle') IS NOT NULL").fetchone() or con.execute("SELECT id FROM retry_attempts WHERE status='queued'").fetchone() or con.execute("SELECT id FROM game_sessions WHERE status='queued'").fetchone():raise ValueError('Other released/cycle/retry/shared work retains barrier')
        identities=[worker]+[x['identity'] for x in state.get('owned',[])]
        for ident in identities:
            if not isinstance(ident,dict) or type(ident.get('pid')) is not int or ident['pid']<=0 or type(ident.get('birth')) is not int or ident['birth']<=0 or not ident.get('path'):raise ValueError('Exact owned native identities required')
        rows=runner.native.processes()
        if not isinstance(rows,list) or not rows:raise ValueError('Complete native inventory required')
        if any(x['name'].lower() in {'skyrimse.exe','skyrimvr.exe','skse64_loader.exe','sksevr_loader.exe','vrserver.exe','vrcompositor.exe'} for x in rows):raise ValueError('Current game/VR blocks admission')
        for ident in identities:
            if runner.native.alive(ident) or any(x['pid']==ident['pid'] and runner.native.identity(ident['pid']) is None for x in rows):raise ValueError('Worker/owned identity alive or unknown')
        runtimes=set()
        if plan.get('configuration',{}).get('runtime'):runtimes.add(Path(plan['configuration']['runtime']))
        if p.host().get('runnerConfig'):runtimes.add(Path(m.read(p.host()['runnerConfig'])['runtime']))
        for runtime in runtimes:
            for state_file in (runtime/'runs').glob('*/state.json'):
                if m.read(state_file).get('done') is not True:raise ValueError('Unfinished native session retains reservation')
        if m.digest(path)!=json.loads(canonical)['sha256']:raise ValueError('Admission review changed')
        p.check_launch_authorization(order);p.verify_inputs(order)
        con.execute("UPDATE jobs SET status='running',note='' WHERE id=?",(key,))
        con.execute('DELETE FROM pipeline_holds WHERE id=?',(sel['holdId'],))
        con.execute('INSERT INTO operator_bound_admissions VALUES(?,?)',(key,canonical))
        p.event(con,key,'bound_subject_admitted',canonical)
        p.event(con,sel['holdId'],'reviewed_hold_transferred_to_exact_subject',canonical)
        row=dict(con.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone())
    # No interval exposes a queued released subject to an old global-VR dispatcher.
    # The qualification row/packet remains recorded history; normal release guards unchanged.
    return p.execute_claimed(row)
