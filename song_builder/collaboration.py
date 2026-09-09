"""Room-only, single-use invitations. Guest sessions never create a host login."""
import hashlib
import json
import secrets
import time
import uuid

from flask import g, jsonify, render_template, request, session, url_for
from . import validation as v

PUBLIC_ENDPOINTS = {'song_builder.join_page', 'song_builder.redeem_invite', 'song_builder.static'}


def allow_guest_gate(app):
    """The host delegates only Room routes; blueprint authorization still runs."""
    return (request.blueprint == 'song_builder' and
            (request.endpoint in PUBLIC_ENDPOINTS or bool(session.get('room_guest'))))


def guest_member(app):
    member_id = session.get('room_guest')
    service = app.extensions.get('room_collaboration')
    if not member_id or service is None:
        return None
    with service.store.connection() as db:
        row = db.execute('''SELECT m.*,p.owner FROM room_members m JOIN projects p
            ON p.id=m.project_id WHERE m.id=? AND m.revoked=0 AND m.expires>?''',
                         (member_id, time.time())).fetchone()
    return dict(row) if row else None


def guard_guest(service, member):
    endpoint = request.endpoint.rsplit('.', 1)[-1]
    project_id = (request.view_args or {}).get('project_id')
    if project_id and project_id != member['project_id']:
        raise v.SongError('not_found', 'This project is not part of your invitation.', 404)
    read = {'index', 'static', 'capabilities', 'list_projects', 'get_project',
            'asset_audio', 'list_jobs', 'collaboration_status', 'leave_room',
            'live_status', 'live_heartbeat', 'live_release'}
    write = {'save_project', 'upload_asset'}
    if endpoint not in read | (write if member['role'] == 'editor' else set()):
        raise v.SongError('room_permission', 'Your invitation does not allow this action.', 403)
    if endpoint == 'list_jobs' and request.args.get('projectId') != member['project_id']:
        raise v.SongError('not_found', 'This project is not part of your invitation.', 404)
    if endpoint == 'asset_audio':
        allowed_assets(service, member, [(request.view_args or {}).get('asset_id')])


def allowed_assets(service, member, ids):
    with service.store.connection() as db:
        project = db.execute('SELECT data FROM projects WHERE id=?', (member['project_id'],)).fetchone()
        if project is None:
            raise v.SongError('not_found', 'This project is unavailable.', 404)
        allowed = {c['assetId'] for c in json.loads(project['data'])['clips']}
        allowed.update(row[0] for row in db.execute('SELECT asset_id FROM room_guest_uploads WHERE member_id=?', (member['id'],)))
        if not set(ids).issubset(allowed):
            raise v.SongError('room_permission', 'Only this project’s audio and your uploads may be used.', 403)


def register(bp, app, service, csrf, body):
    with service.store.connection(write=True) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS room_invites (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          token_hash TEXT NOT NULL UNIQUE, role TEXT NOT NULL, label TEXT NOT NULL,
          expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS room_members (
          id TEXT PRIMARY KEY, invite_id TEXT NOT NULL REFERENCES room_invites(id) ON DELETE CASCADE,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          name TEXT NOT NULL, role TEXT NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS room_guest_uploads (
          member_id TEXT NOT NULL REFERENCES room_members(id) ON DELETE CASCADE,
          asset_id TEXT NOT NULL REFERENCES assets(id), PRIMARY KEY(member_id,asset_id));
        CREATE TABLE IF NOT EXISTS room_contributions (
          id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, member_id TEXT NOT NULL,
          revision INTEGER NOT NULL, created REAL NOT NULL);
        ''')
    app.extensions['room_collaboration'] = service

    @bp.get('/join')
    def join_page():
        token = session.setdefault('room_join_csrf', secrets.token_urlsafe(32))
        return render_template('song_builder/join.html', join_csrf=token,
            builder_assets_url=url_for('song_builder.static', filename=''),
            builder_base_url=url_for('song_builder.index').rstrip('/'))

    @bp.post('/api/invitations/redeem')
    def redeem_invite():
        supplied = request.headers.get('X-Room-Join-CSRF', '')
        expected = session.get('room_join_csrf', '')
        if (not expected or not supplied.isascii() or len(supplied)>100 or
            not secrets.compare_digest(supplied, expected) or request.headers.get('Sec-Fetch-Site')=='cross-site' or
            ('Origin' in request.headers and request.headers['Origin'] != request.host_url.rstrip('/'))):
            raise v.SongError('session_check', 'Reload the invitation before joining.', 403)
        data=body('token name')
        v.string(data['token'], 30, 100); v.string(data['name'], 1, 80)
        fingerprint=hashlib.sha256(data['token'].encode()).hexdigest()
        with service.store.connection(write=True) as db:
            invite=db.execute('SELECT * FROM room_invites WHERE token_hash=? AND used=0 AND revoked=0 AND expires>?', (fingerprint,time.time())).fetchone()
            if invite is None:
                raise v.SongError('invite_unavailable','This invitation expired, was revoked, or was already used. Ask the project owner for a new link.',403)
            member_id=str(uuid.uuid4())
            db.execute('INSERT INTO room_members VALUES(?,?,?,?,?,?,0)',(member_id,invite['id'],invite['project_id'],data['name'].strip(),invite['role'],invite['expires']))
            db.execute('UPDATE room_invites SET used=1 WHERE id=?',(invite['id'],))
        session['room_guest']=member_id
        session.pop('room_join_csrf',None)
        return jsonify(url=url_for('song_builder.index',project=invite['project_id']))

    @bp.get('/api/collaboration')
    def collaboration_status():
        member=getattr(g,'room_member',None)
        if member:
            return jsonify(role=member['role'],name=member['name'],projectId=member['project_id'],expires=member['expires'])
        return jsonify(role='owner')

    @bp.post('/api/collaboration/leave')
    def leave_room():
        session.pop('room_guest',None)
        session.pop('song_builder_csrf',None)
        return jsonify(left=True)

    @bp.get('/api/projects/<project_id>/collaborators')
    def list_collaborators(project_id):
        v.identifier(project_id);service.store.get_project(g.song_builder_account,project_id)
        with service.store.connection() as db:
            invites=[dict(r) for r in db.execute('SELECT id,label,role,expires,used,revoked FROM room_invites WHERE project_id=? ORDER BY expires DESC',(project_id,))]
            members=[dict(r) for r in db.execute('SELECT id,invite_id,name,role,expires,revoked FROM room_members WHERE project_id=?',(project_id,))]
            edits=[dict(r) for r in db.execute('SELECT c.revision,c.created,m.name FROM room_contributions c JOIN room_members m ON m.id=c.member_id WHERE c.project_id=? ORDER BY c.id DESC LIMIT 20',(project_id,))]
        return jsonify(invites=invites,members=members,contributions=edits)

    @bp.post('/api/projects/<project_id>/invitations')
    def create_invitation(project_id):
        v.identifier(project_id);service.store.get_project(g.song_builder_account,project_id)
        data=body('role label');v.string(data['label'],1,80)
        if data['role'] not in ('viewer','editor'):v.invalid('Choose viewer or editor access.')
        token=secrets.token_urlsafe(32);invite_id=str(uuid.uuid4());expires=time.time()+7*86400
        with service.store.connection(write=True) as db:
            count=db.execute('SELECT count(*) FROM room_invites WHERE project_id=? AND revoked=0 AND expires>?',(project_id,time.time())).fetchone()[0]
            if count>=20:raise v.SongError('invite_limit','Revoke an existing invitation before creating more.',429)
            db.execute('INSERT INTO room_invites VALUES(?,?,?,?,?,?,0,0)',(invite_id,project_id,hashlib.sha256(token.encode()).hexdigest(),data['role'],data['label'].strip(),expires))
        return jsonify(id=invite_id,url=url_for('song_builder.join_page')+'#'+token,expires=expires),201

    @bp.delete('/api/projects/<project_id>/invitations/<invite_id>')
    def revoke_invitation(project_id,invite_id):
        v.identifier(project_id);v.identifier(invite_id);service.store.get_project(g.song_builder_account,project_id)
        with service.store.connection(write=True) as db:
            db.execute('UPDATE room_invites SET revoked=1 WHERE project_id=? AND id=?',(project_id,invite_id))
            db.execute('UPDATE room_members SET revoked=1 WHERE project_id=? AND invite_id=?',(project_id,invite_id))
        return jsonify(revoked=True)
