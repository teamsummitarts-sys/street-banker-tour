"""Bounded session archives and named checkpoints. Imports always create a new song."""
import copy
import hashlib
import io
import json
import time
import tempfile
import uuid
import zipfile
from flask import g, jsonify, request, send_file
from . import validation as v, provider
from .advanced import default_metadata, validate_metadata, enforce_clip_protections

MAX_AUDIO = 512 * 1024 * 1024
MAX_MANIFEST = 32 * 1024 * 1024
MAX_ARCHIVE = MAX_AUDIO + MAX_MANIFEST + 1024 * 1024


def uid(): return str(uuid.uuid4())


def register(bp, app, service, body):
    store = service.store
    with store.connection(write=True) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS room_checkpoints(id TEXT PRIMARY KEY,
          project_id TEXT REFERENCES projects(id) ON DELETE CASCADE, name TEXT, author TEXT,
          revision INTEGER, created REAL, data TEXT)''')
        db.execute('''CREATE TABLE IF NOT EXISTS room_archive_sources(project_id TEXT PRIMARY KEY
          REFERENCES projects(id) ON DELETE CASCADE, data TEXT)''')

    def owner(db, pid):
        if getattr(g, 'room_member', None):
            raise v.SongError('room_permission', 'Only the owner can archive or restore a session.', 403)
        return store._owned_project(db, g.song_builder_account, pid)

    def snapshot(db, pid):
        row = owner(db, pid)
        workflow = db.execute('SELECT * FROM room_workflow WHERE project_id=? AND owner=?', (pid, g.song_builder_account)).fetchone()
        feedback = [dict(r) for r in db.execute('SELECT * FROM room_feedback WHERE project_id=? ORDER BY created', (pid,))]
        for item in feedback:
            item.pop('actor'); item.pop('project_id')
        return {'project': json.loads(row['data']), 'revision': row['revision'],
                'workflow': json.loads(workflow['data']) if workflow else default_metadata(),
                'workflowRevision': workflow['revision'] if workflow else 0, 'feedback': feedback}

    def check_snapshot(value):
        if type(value) is not dict or set(value) != {'project','revision','workflow','workflowRevision','feedback'}:
            v.invalid('Invalid session snapshot.')
        value = copy.deepcopy(value)
        value['project'] = v.project(value['project'])
        value['workflow'] = validate_metadata(value['workflow'])
        v.revision(value['revision'])
        if type(value['workflowRevision']) is not int or value['workflowRevision'] < 0: v.invalid('Invalid workflow revision.')
        if not isinstance(value['feedback'], list) or len(value['feedback']) > 500: v.invalid('Too many feedback notes.')
        for note in value['feedback']:
            if type(note) is not dict or set(note) != {'id','name','revision','position','text','resolved','created'}: v.invalid('Invalid feedback.')
            v.identifier(note['id']); v.string(note['name'], 1, 80); v.string(note['text'], 1, 1000)
            v.number(note['position'],0,3600); v.number(note['created'],0,10**12); v.revision(note['revision'])
            if note['resolved'] not in (0,1): v.invalid('Invalid feedback decision.')
        return value

    def audio_ids(snap):
        clips=list(snap['project']['clips'])
        for kind in ('takes','scenes'):
            for item in snap['workflow'][kind]: clips.extend(item['clips'])
        return {c['assetId'] for c in clips}

    def checkpoint_rows(db, pid):
        return [dict(r) for r in db.execute('SELECT * FROM room_checkpoints WHERE project_id=? ORDER BY created DESC', (pid,))]

    def remap(snap, mapping):
        value=copy.deepcopy(snap)
        def mid(old):
            if old not in mapping: mapping[old]=uid()
            return mapping[old]
        p=value['project']; p['id']=mid(p['id'])
        for row in p['tracks']+p['sections']: row['id']=mid(row['id'])
        def clip(c):
            for key in ('id','trackId','sectionId','assetId'): c[key]=mid(c[key])
        for c in p['clips']: clip(c)
        for group in value['workflow']['groups']:
            group['id']=mid(group['id']);group['trackIds']=[mid(i) for i in group['trackIds']]
        for kind in ('scenes','takes'):
            for item in value['workflow'][kind]:
                item['id']=mid(item['id']);item['sectionId']=mid(item['sectionId'])
                if 'trackId' in item:item['trackId']=mid(item['trackId'])
                for c in item['clips']:clip(c)
        for rule in value['workflow']['protections']: rule['clipId']=mid(rule['clipId'])
        for note in value['feedback']: note['id']=mid(note['id'])
        return value

    def insert_snapshot(db, snap, mapping, checkpoints=(), title=None):
        if db.execute('SELECT count(*) FROM projects WHERE owner=?',(g.song_builder_account,)).fetchone()[0]>=v.MAX_PROJECTS:
            raise v.SongError('storage_quota','The song limit has been reached. No session was restored.',429)
        restored=remap(snap,mapping);p=restored['project']
        if title:p['title']=title[:120]
        p=v.project(p);store._assets(db,g.song_builder_account,p)
        # Validate alternate audio too, including clips retained only by a checkpoint.
        for saved in [restored]+[remap(cp['snapshot'],mapping) for cp in checkpoints]:
            for kind in ('takes','scenes'):
                for item in saved['workflow'][kind]:
                    for c in item['clips']:
                        asset=db.execute('SELECT * FROM assets WHERE id=? AND owner=?',(c['assetId'],g.song_builder_account)).fetchone()
                        if not asset or (asset['duration'] is not None and (c['sourceOffset']>=asset['duration'] or (not c['loop'] and c['sourceOffset']+c['duration']>asset['duration']+.01))):v.invalid('A saved take references missing or insufficient audio.')
        now=time.time()
        db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?)',(p['id'],g.song_builder_account,p['title'],json.dumps(p),1,now,now))
        for asset_id in {c['assetId'] for c in p['clips']}:db.execute('INSERT INTO project_assets VALUES(?,?)',(p['id'],asset_id))
        db.execute('INSERT INTO room_workflow VALUES(?,?,?,?,?)',(g.song_builder_account,p['id'],restored['workflowRevision'],json.dumps(restored['workflow']),now))
        for note in restored['feedback']:
            db.execute('INSERT INTO room_feedback VALUES(?,?,?,?,?,?,?,?,?)',(note['id'],p['id'],'archive:'+note['id'],note['name'],note['revision'],note['position'],note['text'],note['resolved'],note['created']))
        for cp in checkpoints:
            db.execute('INSERT INTO room_checkpoints VALUES(?,?,?,?,?,?,?)',(uid(),p['id'],cp['name'],cp['author'],cp['revision'],cp['created'],json.dumps(remap(cp['snapshot'],mapping))))
        source={'projectId':snap['project']['id'],'revision':snap['revision'],'workflowRevision':snap['workflowRevision']}
        db.execute('INSERT INTO room_archive_sources VALUES(?,?)',(p['id'],json.dumps(source)))
        return {'projectId':p['id'],'revision':1,'source':source,'warnings':[]}

    @bp.get('/api/projects/<project_id>/archive')
    def session_archive(project_id):
        v.identifier(project_id)
        with store.connection() as db:
            snap=snapshot(db,project_id)
            cps=[{k:r[k] for k in ('id','name','author','revision','created')}|{'snapshot':json.loads(r['data'])} for r in checkpoint_rows(db,project_id)]
            ids=audio_ids(snap)
            for cp in cps:ids.update(audio_ids(cp['snapshot']))
            if len(ids)>256:v.invalid('This session exceeds the 256-source archive limit.')
            rows=[]
            for asset_id in sorted(ids):
                row=db.execute('SELECT * FROM assets WHERE id=? AND owner=?',(asset_id,g.song_builder_account)).fetchone()
                if row is None:v.invalid('A saved take references missing audio. Resolve it before archiving.')
                rows.append(dict(row))
            if sum(r['size'] for r in rows)>MAX_AUDIO:v.invalid('This session exceeds the 512 MiB archive limit.')
        out=tempfile.SpooledTemporaryFile(max_size=8*1024*1024); assets=[]
        with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED) as z:
            for row in rows:
                raw=store.asset_path(row).read_bytes();path='audio/'+row['id']+'.bin'
                if len(raw)!=row['size']:raise v.SongError('audio_missing','A saved audio file is incomplete. No archive was created.',503)
                z.writestr(path,raw);assets.append({k:row[k] for k in ('id','name','mime','duration','size')}|{'path':path,'sha256':hashlib.sha256(raw).hexdigest()})
            manifest={'format':'the-room-session','version':1,'snapshot':snap,'checkpoints':cps,'assets':assets}
            encoded=json.dumps(manifest).encode()
            if len(encoded)>MAX_MANIFEST:v.invalid('Session notes exceed the archive size limit.')
            z.writestr('session.json',encoded)
        out.seek(0)
        return send_file(out,mimetype='application/zip',as_attachment=True,download_name='The-Room-session.room.zip')

    @bp.post('/api/session-archives')
    def import_session_archive():
        if getattr(g,'room_member',None):raise v.SongError('room_permission','Only the owner can restore a session.',403)
        # Flask 3.1 supports a per-request cap; the host's other uploads retain 25 MiB.
        request.max_content_length=MAX_ARCHIVE+1024*1024
        request.max_form_parts=2
        if set(request.files)!={'file'} or len(request.files.getlist('file'))!=1 or request.form:v.invalid('Choose one Room session archive.')
        stream=request.files['file'].stream
        stream.seek(0,2);size=stream.tell();stream.seek(0)
        if size>MAX_ARCHIVE:v.invalid('The session archive is too large.')
        try:
            with zipfile.ZipFile(stream) as z:
                entries=z.infolist();names=[i.filename for i in entries]
                if len(names)>257 or len(set(names))!=len(names) or 'session.json' not in names:v.invalid('Invalid or duplicate archive entries.')
                if any(i.compress_type!=zipfile.ZIP_STORED or i.flag_bits&1 for i in entries):v.invalid('Use an uncompressed Room session archive.')
                if sum(i.file_size for i in entries)>MAX_ARCHIVE or z.getinfo('session.json').file_size>MAX_MANIFEST:v.invalid('The session archive is too large.')
                m=v.strict_json(z.read('session.json'))
                if type(m) is not dict or set(m)!={'format','version','snapshot','checkpoints','assets'} or m['format']!='the-room-session' or m['version']!=1:v.invalid('Unsupported Room session archive.')
                snap=check_snapshot(m['snapshot']);cps=m['checkpoints']
                if type(cps) is not list or len(cps)>50:v.invalid('Too many checkpoints.')
                for cp in cps:
                    if type(cp) is not dict or set(cp)!={'id','name','author','revision','created','snapshot'}:v.invalid('Invalid checkpoint.')
                    v.identifier(cp['id']);v.string(cp['name'],1,80);v.string(cp['author'],1,80);v.revision(cp['revision']);v.number(cp['created'],0,10**12);cp['snapshot']=check_snapshot(cp['snapshot'])
                if type(m['assets']) is not list or len(m['assets'])>256:v.invalid('Too many audio sources.')
                ids=audio_ids(snap)
                for cp in cps:ids.update(audio_ids(cp['snapshot']))
                parsed=[];seen=set();paths={'session.json'}
                for a in m['assets']:
                    if type(a) is not dict or set(a)!={'id','name','mime','duration','size','path','sha256'}:v.invalid('Invalid archive audio record.')
                    v.identifier(a['id']);v.string(a['name'],1,180)
                    if a['id'] in seen or a['path']!='audio/'+a['id']+'.bin':v.invalid('Invalid audio path or duplicate source.')
                    seen.add(a['id']);paths.add(a['path'])
                    if a['path'] not in names or z.getinfo(a['path']).file_size>provider.MAX_GENERATION_BYTES:v.invalid('Archive audio is missing or too large.')
                    data=z.read(a['path'])
                    if len(data)!=a['size'] or hashlib.sha256(data).hexdigest()!=a['sha256']:v.invalid('Archive audio failed its integrity check.')
                    result=provider.audio_result(data,a['name'])
                    if result['mime']!=a['mime']:v.invalid('Audio type does not match its record.')
                    parsed.append((a['id'],{k:result[k] for k in ('name','mime','duration')}|{'path':a['path'],'size':len(data)}))
                if seen!=ids or set(names)!=paths:v.invalid('Archive sources do not match the saved session.')
        except v.SongError:raise
        except (ValueError,KeyError,TypeError,zipfile.BadZipFile,UnicodeError,OverflowError):v.invalid('This Room session archive is damaged or unsupported.')
        written=[]
        try:
            with store.connection(write=True) as db:
                store._quota(db,g.song_builder_account,sum(a['size'] for _,a in parsed),len(parsed))
                mapping={}
                for old,result in parsed:
                    new=uid();mapping[old]=new
                    with zipfile.ZipFile(stream) as z:result={**result,'data':z.read(result['path'])}
                    written.append(store._write_audio(result['data'],new));store._insert_asset(db,g.song_builder_account,result,new)
                result=insert_snapshot(db,snap,mapping,cps)
            return jsonify(result),201
        except BaseException as error:
            for path in written:path.unlink(missing_ok=True)
            if isinstance(error,OSError):raise v.SongError('archive_storage','The archive could not be stored. No partial project was retained.',503) from error
            raise

    @bp.get('/api/projects/<project_id>/checkpoints')
    def list_checkpoints(project_id):
        v.identifier(project_id)
        with store.connection() as db:
            owner(db,project_id)
            return jsonify(checkpoints=[{k:r[k] for k in ('id','name','author','revision','created')} for r in checkpoint_rows(db,project_id)])

    @bp.post('/api/projects/<project_id>/checkpoints')
    def create_checkpoint(project_id):
        v.identifier(project_id);p=body('name expectedRevision expectedWorkflowRevision');v.string(p['name'],1,80)
        with store.connection(write=True) as db:
            snap=snapshot(db,project_id)
            if snap['revision']!=p['expectedRevision'] or snap['workflowRevision']!=p['expectedWorkflowRevision']:raise v.SongError('checkpoint_stale','The song changed. Refresh before creating a checkpoint.',409)
            if len(checkpoint_rows(db,project_id))>=50:raise v.SongError('checkpoint_limit','This project already has 50 checkpoints.',429)
            cp={'id':uid(),'name':p['name'],'author':'Project owner','revision':snap['revision'],'created':time.time()}
            db.execute('INSERT INTO room_checkpoints VALUES(?,?,?,?,?,?,?)',(cp['id'],project_id,cp['name'],cp['author'],cp['revision'],cp['created'],json.dumps(snap)))
            return jsonify(checkpoint=cp),201

    @bp.post('/api/projects/<project_id>/checkpoints/<checkpoint_id>/restore')
    def restore_checkpoint(project_id,checkpoint_id):
        v.identifier(project_id);v.identifier(checkpoint_id);body('')
        with store.connection(write=True) as db:
            owner(db,project_id);cp=db.execute('SELECT * FROM room_checkpoints WHERE id=? AND project_id=?',(checkpoint_id,project_id)).fetchone()
            if cp is None:raise v.SongError('not_found','This checkpoint is unavailable.',404)
            snap=check_snapshot(json.loads(cp['data']));mapping={i:i for i in audio_ids(snap)}
            return jsonify(insert_snapshot(db,snap,mapping,title=snap['project']['title']+' · '+cp['name'])),201

    @bp.post('/api/projects/<project_id>/fork')
    def fork_session(project_id):
        v.identifier(project_id);p=body(None)
        if type(p) is not dict or set(p) not in ({'expectedRevision','title'},{'expectedRevision','title','project'}):v.invalid('Invalid version request.')
        v.string(p['title'],1,120);v.revision(p['expectedRevision'])
        with store.connection(write=True) as db:
            snap=snapshot(db,project_id)
            if snap['revision']!=p['expectedRevision']:raise v.SongError('version_stale','Save or reload before creating a version.',409)
            if 'project' in p:
                candidate=v.project(p['project'])
                if candidate['id']!=project_id:v.invalid('The version must originate from this project.')
                v.enforce_locks(snap['project'],candidate);enforce_clip_protections(snap['workflow'],snap['project'],candidate)
                store._assets(db,g.song_builder_account,candidate);snap['project']=candidate
            return jsonify(insert_snapshot(db,snap,{i:i for i in audio_ids(snap)},title=p['title'])),201
