"""Private upload inbox and explicitly assigned analysis runs, isolated from song assets."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from flask import g, jsonify, render_template, request, Response, url_for
from . import validation as v
from .analysis_provider import destinations, select, analyze
from .analysis_signal import measure
from .analysis_report import build_report, export_report

MAX_BYTES = 14 * 1024 * 1024  # base64 + prompt stays below inline provider limit
TTL = 24 * 3600


class Analysis:
    def __init__(self, app, directory):
        self.app, self.path = app, Path(directory) / 'analysis.sqlite3'
        self.lock = threading.Lock()

    @contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA secure_delete=ON')
            conn.executescript('''CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT, duration REAL,
                created REAL, expires REAL, status TEXT, audio BLOB);
                CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT, fingerprint TEXT,
                status TEXT, created REAL, destination TEXT, consent TEXT, payload TEXT,
                report TEXT, error TEXT, revision INTEGER NOT NULL DEFAULT 1,
                UNIQUE(owner, request_id));''')
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def purge(self):
        now = time.time()
        with self.db() as db:
            # Never retry an abandoned worker; release its private copies.
            stale = db.execute("SELECT * FROM analysis_runs WHERE status IN ('queued','running') AND created<?", (now-1800,)).fetchall()
            for row in stale:
                for t in json.loads(row['payload'])['tracks']:
                    if not t['muted'] and t['weight']>0:
                        db.execute('DELETE FROM uploads WHERE owner=? AND id=?', (row['owner'],t['id']))
                db.execute("UPDATE analysis_runs SET status='interrupted', error='Analysis was interrupted. No automatic retry occurred.' WHERE id=?", (row['id'],))
            db.execute("DELETE FROM uploads WHERE expires<? AND status='ready'", (now,))
            db.execute('DELETE FROM analysis_runs WHERE created<?', (now-30*TTL,))

    def upload(self, owner, name, data):
        self.purge()
        if len(data)>MAX_BYTES: v.invalid('Analysis copies must be 14 MiB or smaller.')
        duration = v.wav_info(data)
        # Validate format before retaining bytes; full measurement waits for assignment.
        import wave, io
        with wave.open(io.BytesIO(data), 'rb') as wav:
            if wav.getsampwidth()!=2: v.invalid('Use a 16-bit PCM WAV analysis copy.')
        row = dict(id=str(uuid.uuid4()), name=v.safe_name(name), duration=duration, status='ready', expiresAt=time.time()+TTL)
        with self.db() as db:
            count = db.execute('SELECT count(*) FROM uploads WHERE owner=?',(owner,)).fetchone()[0]
            size = db.execute('SELECT coalesce(sum(length(audio)),0) FROM uploads').fetchone()[0]
            if count>=12 or size+len(data)>512*1024*1024:
                raise v.SongError('analysis_quota', 'The private analysis inbox is full. Remove unused uploads first.', 429)
            db.execute('INSERT INTO uploads VALUES (?,?,?,?,?,?,?,?)',(row['id'],owner,row['name'],duration,time.time(),row['expiresAt'],'ready',data))
        return row

    def uploads(self, owner):
        self.purge()
        with self.db() as db:
            return [dict(id=r['id'],name=r['name'],duration=r['duration'],status=r['status'],expiresAt=r['expires']) for r in db.execute('SELECT id,name,duration,status,expires FROM uploads WHERE owner=? ORDER BY created',(owner,))]

    def get(self, owner, run_id):
        v.identifier(run_id)
        with self.db() as db:
            r = db.execute('SELECT * FROM analysis_runs WHERE owner=? AND id=?',(owner,run_id)).fetchone()
        if r is None: raise v.SongError('not_found','Analysis not found.',404)
        return dict(id=r['id'],status=r['status'],createdAt=r['created'],destination=r['destination'],
                    revision=r['revision'],report=json.loads(r['report']) if r['report'] else None,error=r['error'])

    def submit(self, owner, p):
        validate_payload(p)
        self.purge()
        fingerprint = hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()
        with self.db() as db:
            old = db.execute('SELECT * FROM analysis_runs WHERE owner=? AND request_id=?',(owner,p['requestId'])).fetchone()
            if old:
                if old['fingerprint'] != fingerprint: raise v.SongError('conflict','This request ID was already used with different settings.',409)
                run_id = old['id']
            else:
                dest = select(self.app,p['destination'])
                if dest['external'] and p['consent'] != dest['consentToken']:
                    raise v.SongError('consent_required','Read and approve the selected destination before sending audio.',400)
                active = [t for t in p['tracks'] if not t['muted'] and t['weight']>0]
                for t in p['tracks']:
                    row = db.execute('SELECT id,status,duration FROM uploads WHERE owner=? AND id=?',(owner,t['id'])).fetchone()
                    if row is None: raise v.SongError('not_found','An analysis upload is unavailable. Upload a fresh copy.',404)
                    if row['status']!='ready': raise v.SongError('conflict','This upload already belongs to a running analysis.',409)
                    if not t['muted'] and t['weight']>0 and any(s['end']>row['duration'] for s in p['sections']): v.invalid('Section times exceed the uploaded audio.')
                running = db.execute("SELECT count(*) FROM analysis_runs WHERE status IN ('queued','running')").fetchone()[0]
                recent = db.execute('SELECT owner,payload FROM analysis_runs WHERE created>?',(time.time()-TTL,)).fetchall()
                calls = lambda rows: sum(sum(not t['muted'] and t['weight']>0 for t in json.loads(r['payload'])['tracks']) for r in rows)
                if running>=2 or calls([r for r in recent if r['owner']==owner])+len(active)>48 or calls(recent)+len(active)>200:
                    raise v.SongError('analysis_quota','The analysis limit is reached. Try later; no audio has been sent.',429)
                run_id = str(uuid.uuid4())
                db.execute('INSERT INTO analysis_runs (id,owner,request_id,fingerprint,status,created,destination,consent,payload) VALUES (?,?,?,?,?,?,?,?,?)',
                    (run_id,owner,p['requestId'],fingerprint,'queued',time.time(),dest['id'],dest['consentToken'],json.dumps(p)))
                for t in active: db.execute("UPDATE uploads SET status='assigned' WHERE id=?",(t['id'],))
        return self.get(owner,run_id)

    def start(self, run_id):
        if self.app.testing and self.app.config.get('ROOM_ANALYSIS_AUTOSTART') is False: return
        try:
            threading.Thread(target=self.run,args=(run_id,),daemon=True,name='room-analysis').start()
        except RuntimeError:
            self.finish(run_id, None, 'Analysis could not start. Please upload again; it was not retried.')

    def finish(self, run_id, report, error):
        with self.db() as db:
            row = db.execute('SELECT * FROM analysis_runs WHERE id=?',(run_id,)).fetchone()
            if not row or row['status'] not in ('queued','running'): return
            p = json.loads(row['payload'])
            for t in p['tracks']:
                if not t['muted'] and t['weight']>0: db.execute('DELETE FROM uploads WHERE owner=? AND id=?',(row['owner'],t['id']))
            db.execute('UPDATE analysis_runs SET status=?,report=?,error=? WHERE id=?',
                ('failed' if error else 'succeeded',json.dumps(report,allow_nan=False) if report else None,error,run_id))

    def run(self, run_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM analysis_runs WHERE id=?',(run_id,)).fetchone()
            if not row or row['status']!='queued': return
            db.execute("UPDATE analysis_runs SET status='running' WHERE id=?",(run_id,))
        try:
            p = json.loads(row['payload'])
            dest = select(self.app,row['destination'])
            if dest['consentToken']!=row['consent']: raise ValueError('Destination configuration changed')
            results = []
            for t in p['tracks']:
                if t['muted'] or t['weight']==0: continue
                with self.db() as db:
                    upload = db.execute('SELECT * FROM uploads WHERE id=? AND owner=?',(t['id'],row['owner'])).fetchone()
                if upload is None: raise ValueError('Upload expired')
                data = upload['audio']
                measured = measure(data)
                context = {'mode':p['mode'], 'goal':p['goal'], 'sections':p['sections'], 'keep':t['keep'], 'avoid':t['avoid']}
                interpretation = None if dest['id']=='local' else analyze(self.app,dest,data,measured,context)
                results.append(dict(id=t['id'],name=upload['name'],measured=measured,interpretation=interpretation,
                                    weight=t['weight'],keep=t['keep'],avoid=t['avoid']))
                del data, upload
            report = build_report(results,p)
            report['provenance'] = {'destination':dest['id'],'model':dest['model'],'disclosure':dest['detail'],
                                     'consentToken':row['consent'],'analyzedAt':time.time()}
            self.finish(run_id,report,None)
        except Exception:
            self.finish(run_id,None,'Analysis did not finish. Temporary analysis copies were removed. No fallback or automatic retry occurred; a provider charge may apply if audio was sent.')


def validate_payload(p):
    v.exact(p,'requestId mode destination consent goal sections tracks')
    v.identifier(p['requestId'])
    if p['mode'] not in ('dna','improve'): v.invalid()
    v.string(p['destination'],1,40)
    if p['consent'] is not None: v.string(p['consent'],1,100)
    v.string(p['goal'],0,1000)
    if type(p['tracks']) is not list or not 1<=len(p['tracks'])<=12: v.invalid('Select 1–12 uploads.')
    ids=set()
    for t in p['tracks']:
        v.exact(t,'id weight muted keep avoid')
        v.identifier(t['id']); v.number(t['weight'],0,100); v.boolean(t['muted'])
        if t['id'] in ids: v.invalid('Select each upload only once.')
        ids.add(t['id'])
        for key in ('keep','avoid'):
            if type(t[key]) is not list or len(t[key])>12: v.invalid()
            for label in t[key]: v.string(label,1,100)
        if {x.casefold() for x in t['keep']} & {x.casefold() for x in t['avoid']}: v.invalid('A trait cannot be both Keep and Avoid.')
    active=[t for t in p['tracks'] if not t['muted'] and t['weight']>0]
    if not active or (p['mode']=='improve' and len(active)!=1): v.invalid('Improve My Track needs one active upload; Sound DNA needs at least one.')
    if type(p['sections']) is not list or len(p['sections'])>30: v.invalid()
    previous=0
    for s in p['sections']:
        v.exact(s,'name start end');v.string(s['name'],1,60)
        v.number(s['start'],previous,600);v.number(s['end'],s['start']+.01,600)
        previous=s['end']
    if p['mode']=='dna' and p['sections']: v.invalid('Section maps belong to Improve My Track.')


def register(bp, app, directory, csrf, body):
    service=Analysis(app,directory)
    app.extensions['room_analysis']=service

    @bp.get('/analyze')
    def analysis_page():
        return render_template('song_builder/analyze.html', builder_base_url=url_for('song_builder.index').rstrip('/'),
            builder_assets_url=url_for('song_builder.static',filename=''), builder_csrf=csrf())

    @bp.get('/api/analysis/destinations')
    def analysis_destinations():
        return jsonify(destinations=destinations(app), maxUploadBytes=MAX_BYTES)

    @bp.get('/api/analysis/uploads')
    def analysis_uploads(): return jsonify(tracks=service.uploads(g.song_builder_account))

    @bp.post('/api/analysis/uploads')
    def analysis_upload():
        request.max_content_length=MAX_BYTES+64*1024
        if request.form.get('authorized')!='true' or set(request.files)!={'file'}: v.invalid('Confirm that you are authorized to analyze this audio.')
        file=request.files['file']
        return jsonify(track=service.upload(g.song_builder_account,file.filename,file.stream.read(MAX_BYTES+1))),201

    @bp.delete('/api/analysis/uploads/<upload_id>')
    def analysis_remove(upload_id):
        v.identifier(upload_id)
        with service.db() as db:
            row=db.execute('SELECT * FROM uploads WHERE id=? AND owner=?',(upload_id,g.song_builder_account)).fetchone()
            if row is None: raise v.SongError('not_found','Upload not found.',404)
            if row['status']!='ready': raise v.SongError('conflict','This copy is assigned to a running analysis.',409)
            db.execute('DELETE FROM uploads WHERE id=?',(upload_id,))
        return jsonify(deleted=True)

    @bp.post('/api/analysis/runs')
    def analysis_submit():
        result=service.submit(g.song_builder_account,body(None))
        service.start(result['id'])
        return jsonify(run=result),202

    @bp.get('/api/analysis/runs')
    def analysis_list():
        service.purge()
        with service.db() as db:
            rows=db.execute('SELECT id,status,created,destination FROM analysis_runs WHERE owner=? ORDER BY created DESC LIMIT 30',(g.song_builder_account,)).fetchall()
        return jsonify(runs=[dict(r) for r in rows])

    @bp.get('/api/analysis/runs/<run_id>')
    def analysis_result(run_id):
        service.purge()
        return jsonify(run=service.get(g.song_builder_account,run_id))

    @bp.patch('/api/analysis/runs/<run_id>')
    def analysis_review(run_id):
        p=body('expectedRevision decisions prompt')
        result=service.get(g.song_builder_account,run_id)
        if result['status']!='succeeded': raise v.SongError('conflict','Wait for analysis to finish.',409)
        v.revision(p['expectedRevision']);v.string(p['prompt'],0,999)
        if type(p['decisions']) is not dict: v.invalid()
        report=result['report']; known={n['id'] for n in report['recommendations']}
        if set(p['decisions'])-known or any(x not in ('accepted','rejected','pending') for x in p['decisions'].values()): v.invalid()
        for n in report['recommendations']: n['decision']=p['decisions'].get(n['id'],n['decision'])
        report['blueprint']['prompt']=p['prompt']
        with service.db() as db:
            changed=db.execute('UPDATE analysis_runs SET report=?,revision=revision+1 WHERE id=? AND owner=? AND revision=?',
                (json.dumps(report),run_id,g.song_builder_account,p['expectedRevision'])).rowcount
            if changed!=1: raise v.SongError('conflict','This report changed elsewhere. Reload before reviewing.',409)
        return jsonify(run=service.get(g.song_builder_account,run_id))

    @bp.delete('/api/analysis/runs/<run_id>')
    def analysis_delete(run_id):
        result=service.get(g.song_builder_account,run_id)
        if result['status'] in ('queued','running'): raise v.SongError('conflict','Wait for this analysis to finish.',409)
        with service.db() as db: db.execute('DELETE FROM analysis_runs WHERE id=? AND owner=?',(run_id,g.song_builder_account))
        return jsonify(deleted=True)

    @bp.get('/api/analysis/runs/<run_id>/export/<kind>')
    def analysis_export(run_id,kind):
        if kind not in ('full','producer','timecoded','prompt','markdown','text','json'): v.invalid()
        result=service.get(g.song_builder_account,run_id)
        if result['status']!='succeeded': raise v.SongError('conflict','No completed report to export.',409)
        content,mime,extension=export_report(result,kind)
        return Response(content,mimetype=mime,headers={'Content-Disposition':f'attachment; filename="the-room-{kind}.{extension}"'})

    @app.cli.command('room-analysis-purge')
    def purge_analysis():
        """Remove expired analysis copies/reports without touching song assets."""
        service.purge()
