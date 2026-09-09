"""Hosted transport metadata and revision-anchored feedback. Audio stays local."""
import json
import time
from flask import g, jsonify
from . import validation as v
from .live import actor, prune


def active_host(db, project_id, now):
    return db.execute('''SELECT h.*,s.name FROM room_listening h JOIN room_live_sessions s
        ON s.session_id=h.session_id AND s.project_id=h.project_id AND s.actor=h.actor
        WHERE h.project_id=? AND s.expires>?''',(project_id,now)).fetchone()


def register(bp, service, body):
    with service.store.connection(write=True) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS room_listening (
          project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
          session_id TEXT NOT NULL, actor TEXT NOT NULL, revision INTEGER NOT NULL, version INTEGER NOT NULL,
          playing INTEGER NOT NULL, position REAL NOT NULL, changed REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS room_feedback (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          actor TEXT NOT NULL,name TEXT NOT NULL,revision INTEGER NOT NULL,position REAL NOT NULL,
          text TEXT NOT NULL,resolved INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS room_feedback_project ON room_feedback(project_id,created);
        ''')
    service.store.listening_enabled=True

    def person():
        member=getattr(g,'room_member',None)
        return member,actor(member,g.song_builder_account),member['name'] if member else 'Project owner'

    def current_session(db,pid,sid,who):
        row=db.execute('SELECT * FROM room_live_sessions WHERE session_id=? AND project_id=? AND actor=?',(sid,pid,who)).fetchone()
        if row is None:raise v.SongError('live_expired','Join the live session before leading playback.',409)
        if row['role']=='viewer':raise v.SongError('room_permission','Viewer access cannot lead playback.',403)
        return row

    @bp.get('/api/projects/<project_id>/listening')
    def listening_status(project_id):
        v.identifier(project_id);_,who,_=person();now=time.time()
        with service.store.connection(write=True) as db:
            project=service.store._owned_project(db,g.song_builder_account,project_id);prune(db,now)
            host=active_host(db,project_id,now)
            transport={k:host[k] for k in ('session_id','revision','version','playing','position','changed','name')} if host else None
            comments=[{**{k:r[k] for k in ('id','name','revision','position','text','resolved','created')},'canResolve':r['actor']==who or not getattr(g,'room_member',None)} for r in db.execute('SELECT * FROM room_feedback WHERE project_id=? ORDER BY created DESC LIMIT 100',(project_id,))]
        return jsonify(transport=transport,comments=comments,serverNow=now,revision=project['revision'])

    @bp.post('/api/projects/<project_id>/listening')
    def listening_command(project_id):
        v.identifier(project_id);data=body('sessionId action expectedVersion position expectedRevision')
        v.identifier(data['sessionId']);v.revision(data['expectedRevision'])
        if type(data['expectedVersion']) is not int or data['expectedVersion']<0:v.invalid('Invalid transport version.')
        if data['action'] not in ('host','play','pause','seek','end'):v.invalid('Choose a listening action.')
        member,who,_=person();now=time.time()
        with service.store.connection(write=True) as db:
            project=service.store._owned_project(db,g.song_builder_account,project_id);prune(db,now)
            own=current_session(db,project_id,data['sessionId'],who);host=active_host(db,project_id,now)
            total=sum(s['duration'] for s in json.loads(project['data'])['sections'])
            if type(data['position']) not in (int,float) or not 0<=data['position']<=total:v.invalid('Choose a position inside this song.')
            if project['revision']!=data['expectedRevision']:raise v.SongError('conflict','Reload the saved song before starting shared playback.',409)
            if data['action']=='host':
                if host:raise v.SongError('host_busy',host['name']+' is already leading playback.',409)
                if db.execute('SELECT 1 FROM room_live_sessions WHERE project_id=? AND session_id<>? AND scope IS NOT NULL',(project_id,data['sessionId'])).fetchone():
                    raise v.SongError('part_busy','Ask collaborators to release editing control before the listening session.',409)
                db.execute('INSERT OR REPLACE INTO room_listening VALUES(?,?,?,?,1,0,?,?)',(project_id,data['sessionId'],who,project['revision'],data['position'],now))
            else:
                if not host or host['session_id']!=data['sessionId']:raise v.SongError('room_permission','Only the active host can control this listening session.',403)
                if host['version']!=data['expectedVersion']:raise v.SongError('transport_conflict','Playback changed elsewhere. Refresh before sending another command.',409)
                if data['action']=='end':db.execute('DELETE FROM room_listening WHERE project_id=?',(project_id,))
                else:
                    playing=1 if data['action']=='play' else 0 if data['action']=='pause' else host['playing']
                    db.execute('UPDATE room_listening SET version=version+1,playing=?,position=?,changed=? WHERE project_id=?',(playing,data['position'],now,project_id))
        return jsonify(updated=True)

    @bp.post('/api/projects/<project_id>/feedback')
    def add_feedback(project_id):
        v.identifier(project_id);data=body('id text position expectedRevision');v.identifier(data['id']);v.string(data['text'],1,1000);v.revision(data['expectedRevision']);member,who,name=person();now=time.time()
        with service.store.connection(write=True) as db:
            project=service.store._owned_project(db,g.song_builder_account,project_id)
            if member and not db.execute('SELECT 1 FROM room_members WHERE id=? AND revoked=0 AND expires>?',(member['id'],now)).fetchone():raise v.SongError('room_permission','Your invitation is no longer active.',403)
            total=sum(s['duration'] for s in json.loads(project['data'])['sections'])
            if type(data['position']) not in (int,float) or not 0<=data['position']<=total:v.invalid('Choose a feedback timestamp inside the song.')
            previous=db.execute('SELECT * FROM room_feedback WHERE id=?',(data['id'],)).fetchone()
            if previous:
                if previous['project_id']!=project_id or previous['actor']!=who or previous['text']!=data['text'] or previous['position']!=data['position'] or previous['revision']!=data['expectedRevision']:raise v.SongError('feedback_conflict','This feedback request has already been used.',409)
                return jsonify(saved=True),200
            if project['revision']!=data['expectedRevision']:raise v.SongError('conflict','The song changed. Reopen the current version before adding feedback.',409)
            if db.execute('SELECT count(*) FROM room_feedback WHERE project_id=?',(project_id,)).fetchone()[0]>=500:raise v.SongError('feedback_limit','This project has reached its 500-note limit.',429)
            if db.execute('SELECT count(*) FROM room_feedback WHERE actor=? AND created>?',(who,now-10)).fetchone()[0]>=5:raise v.SongError('feedback_limit','Wait a moment before adding another note.',429)
            db.execute('INSERT INTO room_feedback VALUES(?,?,?,?,?,?,?,0,?)',(data['id'],project_id,who,name,project['revision'],data['position'],data['text'],now))
        return jsonify(saved=True),201

    @bp.patch('/api/projects/<project_id>/feedback/<feedback_id>')
    def resolve_feedback(project_id,feedback_id):
        v.identifier(project_id);v.identifier(feedback_id);data=body('resolved');member,who,_=person()
        if type(data['resolved']) is not bool:v.invalid('Choose resolved or open.')
        service.store.get_project(g.song_builder_account,project_id)
        with service.store.connection(write=True) as db:
            row=db.execute('SELECT * FROM room_feedback WHERE id=? AND project_id=?',(feedback_id,project_id)).fetchone()
            if row is None:raise v.SongError('not_found','This note is unavailable.',404)
            if member and row['actor']!=who:raise v.SongError('room_permission','Only the author or project owner can resolve this note.',403)
            db.execute('UPDATE room_feedback SET resolved=? WHERE id=?',(int(data['resolved']),feedback_id))
        return jsonify(updated=True)
