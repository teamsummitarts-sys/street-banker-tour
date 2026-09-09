"""Short-lived editing leases and canonical revision merging for shared Rooms."""
import copy
import json
import time
from flask import g, jsonify
from . import validation as v

TTL = 20


def actor(member, owner):
    return 'guest:' + member['id'] if member else 'owner:' + owner


def prune(db, now):
    db.execute('DELETE FROM room_live_sessions WHERE expires<=?', (now,))
    db.execute("DELETE FROM room_live_sessions WHERE member_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM room_members m WHERE m.id=room_live_sessions.member_id AND m.revoked=0 AND m.expires>?)", (now,))


def scopes(before, after):
    changed = set()
    if any(before.get(k) != after.get(k) for k in set(before) | set(after) if k not in ('tracks', 'clips')):
        changed.add('arrangement')
    old = {t['id']: t for t in before['tracks']}; new = {t['id']: t for t in after['tracks']}
    if [t['id'] for t in before['tracks']] != [t['id'] for t in after['tracks']]:
        changed.add('arrangement')
    for tid in old.keys() | new.keys():
        if old.get(tid) != new.get(tid) or ([c for c in before['clips'] if c['trackId']==tid] != [c for c in after['clips'] if c['trackId']==tid]):
            changed.add('track:' + tid)
    return changed


def overlaps(a, b):
    return bool(a and b and ('arrangement' in a or 'arrangement' in b or a & b))


def snapshot(db, project, revision):
    db.execute('INSERT OR IGNORE INTO room_live_revisions VALUES(?,?,?)', (project['id'],revision,json.dumps(project)))
    db.execute('DELETE FROM room_live_revisions WHERE project_id=? AND revision<?', (project['id'],revision-39))
    rows=db.execute('SELECT revision,length(data) AS size FROM room_live_revisions WHERE project_id=? ORDER BY revision DESC',(project['id'],)).fetchall()
    total=0
    for row in rows:
        total+=row['size']
        if total>2*1024*1024 and row['revision']<revision:
            db.execute('DELETE FROM room_live_revisions WHERE project_id=? AND revision<=?',(project['id'],row['revision']))
            break


def prepare_save(db, owner, incoming, expected, current, revision, member, session_id):
    now=time.time();prune(db,now)
    who=actor(member,owner)
    if session_id:
        active=db.execute('SELECT * FROM room_live_sessions WHERE session_id=? AND project_id=? AND actor=?', (session_id,incoming['id'],who)).fetchone()
        if active is None:
            raise v.SongError('live_expired','Live editing disconnected. Reconnect before saving; your edits are still here.',409)
    snapshot(db,current,revision)
    if expected!=revision:
        if not session_id:
            raise v.SongError('conflict','This song changed elsewhere. Reload or save a separate version.',409)
        row=db.execute('SELECT data FROM room_live_revisions WHERE project_id=? AND revision=?',(incoming['id'],expected)).fetchone()
        if row is None:
            raise v.SongError('conflict','This version is too old to merge safely. Keep a backup and reload.',409)
        base=json.loads(row['data']);local=scopes(base,incoming);remote=scopes(base,current)
        if overlaps(local,remote):
            raise v.SongError('conflict','The same part changed in another session. Your edits are retained for review.',409)
        if local:
            merged=copy.deepcopy(current)
            if 'arrangement' in local:
                merged=copy.deepcopy(incoming)
            else:
                touched={s[6:] for s in local}
                tracks={t['id']:t for t in incoming['tracks']}
                merged['tracks']=[copy.deepcopy(tracks[t['id']]) if t['id'] in touched else t for t in current['tracks']]
                merged['clips']=[c for c in current['clips'] if c['trackId'] not in touched]+[copy.deepcopy(c) for c in incoming['clips'] if c['trackId'] in touched]
            incoming=v.project(merged)
        else:
            incoming=copy.deepcopy(current)
    changed=scopes(current,incoming)
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='room_listening'").fetchone():
        from .listening import active_host
        if changed and active_host(db,incoming['id'],now):
            raise v.SongError('listening_active','End the listening session before changing this saved mix.',409)
    if session_id and changed and (not active['scope'] or (active['scope']!='arrangement' and changed!={active['scope']})):
        raise v.SongError('part_busy','Claim editing control of this instrument or the arrangement before saving.',409)
    for lock in db.execute('SELECT * FROM room_live_sessions WHERE project_id=? AND scope IS NOT NULL',(incoming['id'],)):
        if lock['session_id']==session_id and lock['actor']==who:continue
        if overlaps(changed,{lock['scope']}):
            raise v.SongError('part_busy',lock['name']+' is editing this part. Your unsaved changes are retained.',409)
    return incoming,revision


def register(bp, service, body):
    with service.store.connection(write=True) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS room_live_sessions (
          session_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          actor TEXT NOT NULL, member_id TEXT, name TEXT NOT NULL, role TEXT NOT NULL,
          scope TEXT, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS room_live_revisions (
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          revision INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(project_id,revision));
        ''')
    service.store.live_enabled=True

    def identity():
        member=getattr(g,'room_member',None)
        return member,actor(member,g.song_builder_account)

    @bp.get('/api/projects/<project_id>/live')
    def live_status(project_id):
        v.identifier(project_id)
        with service.store.connection(write=True) as db:
            project=service.store._owned_project(db,g.song_builder_account,project_id);prune(db,time.time())
            rows=[dict(r) for r in db.execute('SELECT session_id AS sessionId,name,role,scope,expires FROM room_live_sessions WHERE project_id=? ORDER BY name,session_id',(project_id,))]
        return jsonify(revision=project['revision'],presence=rows,leaseSeconds=TTL)

    @bp.post('/api/projects/<project_id>/live')
    def live_heartbeat(project_id):
        v.identifier(project_id);data=body('sessionId scope');v.identifier(data['sessionId'])
        member,who=identity();scope=data['scope'];role=member['role'] if member else 'owner';now=time.time()
        if scope is not None and (not isinstance(scope,str) or len(scope)>50):v.invalid('Choose a valid editing part.')
        if role=='viewer' and scope is not None:raise v.SongError('room_permission','Viewers can listen but cannot claim editing control.',403)
        with service.store.connection(write=True) as db:
            project=service.store._owned_project(db,g.song_builder_account,project_id);prune(db,now)
            if member and not db.execute('SELECT 1 FROM room_members WHERE id=? AND revoked=0 AND expires>?',(member['id'],now)).fetchone():
                raise v.SongError('room_permission','This invitation is no longer active.',403)
            value=json.loads(project['data'])
            if scope and getattr(service.store,'listening_enabled',False):
                from .listening import active_host
                if active_host(db,project_id,now):raise v.SongError('listening_active','Playback review is active. Choose Listen only or end the session.',409)
            if scope is not None and scope!='arrangement' and scope not in {'track:'+t['id'] for t in value['tracks']}:v.invalid('Choose a track in this song.')
            own=db.execute('SELECT * FROM room_live_sessions WHERE session_id=?',(data['sessionId'],)).fetchone()
            if own and (own['actor']!=who or own['project_id']!=project_id):raise v.SongError('room_permission','Use a new live session for this project.',403)
            if not own and db.execute('SELECT count(*) FROM room_live_sessions WHERE project_id=?',(project_id,)).fetchone()[0]>=30:
                raise v.SongError('live_limit','This Room has reached its active session limit.',429)
            if scope:
                for lock in db.execute('SELECT * FROM room_live_sessions WHERE project_id=? AND session_id<>? AND scope IS NOT NULL',(project_id,data['sessionId'])):
                    if overlaps({scope},{lock['scope']}):raise v.SongError('part_busy',lock['name']+' is editing this part. Choose another instrument or listen.',409)
            db.execute('INSERT INTO room_live_sessions VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET scope=excluded.scope,expires=excluded.expires',
                (data['sessionId'],project_id,who,member['id'] if member else None,member['name'] if member else 'Project owner',role,scope,now+TTL))
            snapshot(db,value,project['revision'])
        return jsonify(connected=True,expires=now+TTL)

    @bp.delete('/api/projects/<project_id>/live')
    def live_release(project_id):
        v.identifier(project_id);data=body('sessionId');v.identifier(data['sessionId']);_,who=identity()
        service.store.get_project(g.song_builder_account,project_id)
        with service.store.connection(write=True) as db:
            db.execute('DELETE FROM room_live_sessions WHERE session_id=? AND project_id=? AND actor=?',(data['sessionId'],project_id,who))
        return jsonify(released=True)
