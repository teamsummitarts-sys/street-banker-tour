"""Immutable collaborator takes, private saved-mix auditions and owner decisions."""
import copy
import hashlib
import json
import time
import uuid

from flask import g, jsonify, send_file, url_for

from . import validation as v
from .advanced import default_metadata, enforce_clip_protections
from .live import actor, prune, snapshot
from .listening import active_host
from .store import iso


def _signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _missing():
    raise v.SongError('not_found', 'This take is unavailable.', 404)


def _scope(db, service, project_id, *, editor=False, owner=False):
    """Repeat membership checks inside the read/write transaction, after the host gate."""
    member = getattr(g, 'room_member', None)
    project = service.store._owned_project(db, g.song_builder_account, project_id)
    if member:
        if member['project_id'] != project_id:
            _missing()
        active = db.execute('SELECT * FROM room_members WHERE id=? AND project_id=? AND revoked=0 AND expires>?',
                            (member['id'], project_id, time.time())).fetchone()
        if active is None or owner or (editor and active['role'] != 'editor'):
            raise v.SongError('room_permission', 'Your invitation does not allow this action.', 403)
    return project, member, actor(member, g.song_builder_account)


def _row(db, project_id, submission_id, member, who):
    row = db.execute('SELECT * FROM room_submissions WHERE id=? AND project_id=?',
                     (submission_id, project_id)).fetchone()
    if row is None or (member and row['actor'] != who):
        _missing()
    return row


def _workflow(db, owner, project_id):
    row = db.execute('SELECT * FROM room_workflow WHERE owner=? AND project_id=?',
                     (owner, project_id)).fetchone()
    return (json.loads(row['data']), row['revision']) if row else (default_metadata(), 0)


def _not_listening(db, project_id):
    prune(db, time.time())
    if active_host(db, project_id, time.time()):
        raise v.SongError('listening_active', 'End the shared listening session before auditioning or accepting a take.', 409)


def _placement(project, payload, metadata):
    section = next((s for s in project['sections'] if s['id'] == payload['sectionId']), None)
    if section is None or not any(t['id'] == payload['trackId'] for t in project['tracks']):
        v.invalid('Choose an existing section and instrument in this saved song.')
    if section['locked']:
        raise v.SongError('section_locked', 'The owner must unlock and save this section before a new take can replace it.', 409)
    if payload['offset'] + payload['duration'] > section['duration'] + .000001:
        v.invalid('The take must fit inside its section. Adjust its start or duration.')
    start, end = payload['offset'], payload['offset'] + payload['duration']
    affected = {c['id'] for c in project['clips'] if c['sectionId'] == section['id']
                and c['trackId'] == payload['trackId'] and c['offset'] < end
                and c['offset'] + c['duration'] > start}
    if any(p['clipId'] in affected for p in metadata['protections']):
        raise v.SongError('clip_protected', 'The owner must remove this clip’s protection before replacing its audio.', 409)
    return section


def _candidate(project, payload, asset_durations, candidate_id):
    """Replace only the assigned lane range; retain the unaffected clip portions."""
    result = copy.deepcopy(project)
    start, end = payload['offset'], payload['offset'] + payload['duration']
    clips = []
    for clip in result['clips']:
        if (clip['sectionId'] != payload['sectionId'] or clip['trackId'] != payload['trackId']
                or clip['offset'] >= end or clip['offset'] + clip['duration'] <= start):
            clips.append(clip)
            continue
        old_end = clip['offset'] + clip['duration']
        if clip['offset'] < start:
            clips.append({**clip, 'duration': start - clip['offset'], 'fadeOut': 0})
        if old_end > end:
            source_offset = clip['sourceOffset'] + end - clip['offset']
            if clip['loop']:
                source_duration = asset_durations.get(clip['assetId'])
                if not source_duration:
                    v.invalid('This looping source needs a known duration before its take can be replaced.')
                source_offset = clip['sourceOffset'] + (end - clip['offset']) % (source_duration - clip['sourceOffset'])
            right_id = str(uuid.uuid5(uuid.UUID(candidate_id), clip['id'])) if clip['offset'] < start else clip['id']
            clips.append({**clip, 'id': right_id, 'offset': end, 'sourceOffset': source_offset,
                          'duration': old_end - end, 'fadeIn': 0})
    clips.append({'id': candidate_id, 'sectionId': payload['sectionId'], 'trackId': payload['trackId'],
                  'assetId': payload['assetId'], 'offset': start, 'sourceOffset': payload['sourceOffset'],
                  'duration': payload['duration'], 'loop': False, 'gainDb': 0})
    result['clips'] = clips
    return v.project(result)


def _public(row):
    payload = json.loads(row['payload'])
    source = json.loads(row['source_data'])
    section = next(s for s in source['sections'] if s['id'] == payload['sectionId'])
    track = next(t for t in source['tracks'] if t['id'] == payload['trackId'])
    return {'id': row['id'], 'projectId': row['project_id'], 'name': row['name'],
            'sourceRevision': row['source_revision'], 'sourceWorkflowRevision': row['workflow_revision'],
            'sectionId': payload['sectionId'], 'sectionName': section['name'],
            'trackId': payload['trackId'], 'trackName': track['name'],
            'offset': payload['offset'], 'sourceOffset': payload['sourceOffset'],
            'duration': payload['duration'], 'assetId': row['asset_id'], 'note': payload['note'],
            'status': row['status'], 'reason': row['reason'], 'acceptedProjectId': row['accepted_project_id'],
            'createdAt': iso(row['created']), 'decidedAt': iso(row['decided']) if row['decided'] else None}


def _asset_json(row, project_id=None, submission_id=None):
    route = ('song_builder.submission_asset_audio' if submission_id else 'song_builder.asset_audio')
    args = {'asset_id': row['id']}
    if submission_id:
        args.update(project_id=project_id, submission_id=submission_id)
    return {k: row[k] for k in ('id', 'name', 'mime', 'size', 'duration')} | {'url': url_for(route, **args)}


def register(bp, app, service, body):
    """Register after collaboration, workflow, live sessions and listening."""
    with service.store.connection(write=True) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS room_submissions (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          owner TEXT NOT NULL, actor TEXT NOT NULL, member_id TEXT, name TEXT NOT NULL,
          payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
          asset_id TEXT NOT NULL REFERENCES assets(id), source_revision INTEGER NOT NULL,
          source_data TEXT NOT NULL, workflow_revision INTEGER NOT NULL, workflow_data TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', reason TEXT NOT NULL DEFAULT '',
          accepted_project_id TEXT, created REAL NOT NULL, decided REAL);
        CREATE INDEX IF NOT EXISTS room_submissions_project ON room_submissions(project_id,created);
        CREATE TABLE IF NOT EXISTS room_submission_decisions (
          owner TEXT NOT NULL, request_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
          submission_id TEXT NOT NULL REFERENCES room_submissions(id) ON DELETE CASCADE,
          PRIMARY KEY(owner,request_id));
        CREATE TABLE IF NOT EXISTS room_submission_versions (
          project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
          source_project_id TEXT NOT NULL, source_revision INTEGER NOT NULL,
          submission_id TEXT NOT NULL, contributor_name TEXT NOT NULL, created REAL NOT NULL);
        ''')
    app.extensions['room_submissions'] = service

    @bp.get('/api/projects/<project_id>/submissions')
    def list_submissions(project_id):
        v.identifier(project_id)
        with service.store.connection() as db:
            project, member, who = _scope(db, service, project_id)
            query = 'SELECT * FROM room_submissions WHERE project_id=?'
            args = [project_id]
            if member:
                query += ' AND actor=?'; args.append(who)
            rows = db.execute(query + ' ORDER BY created DESC', args).fetchall()
            origin = db.execute('SELECT * FROM room_submission_versions WHERE project_id=?', (project_id,)).fetchone()
            workflow_revision = _workflow(db, g.song_builder_account, project_id)[1]
            return jsonify(submissions=[{**_public(r), 'stale': r['source_revision'] != project['revision']
                            or r['workflow_revision'] != workflow_revision} for r in rows],
                           revision=project['revision'], origin=dict(origin) if origin else None)

    @bp.post('/api/projects/<project_id>/submissions')
    def submit_take(project_id):
        v.identifier(project_id)
        payload = body('requestId assetId sectionId trackId offset sourceOffset duration expectedRevision note')
        for field in ('requestId', 'assetId', 'sectionId', 'trackId'):
            v.identifier(payload[field])
        v.number(payload['offset'], 0, 600); v.number(payload['sourceOffset'], 0, 600)
        v.number(payload['duration'], .000001, 120); v.revision(payload['expectedRevision'])
        v.string(payload['note'], 0, 1000)
        signature = _signature(payload)
        with service.store.connection(write=True) as db:
            current, member, who = _scope(db, service, project_id, editor=True)
            previous = db.execute('SELECT * FROM room_submissions WHERE id=?', (payload['requestId'],)).fetchone()
            if previous:
                if previous['project_id'] != project_id or previous['actor'] != who or previous['payload_hash'] != signature:
                    raise v.SongError('submission_conflict', 'This take request was already used for different settings.', 409)
                return jsonify(submission=_public(previous)), 200
            if current['revision'] != payload['expectedRevision']:
                raise v.SongError('submission_stale', 'The saved backing changed. Reload the song and check your placement before submitting.', 409)
            source = json.loads(current['data'])
            metadata, workflow_revision = _workflow(db, g.song_builder_account, project_id)
            _placement(source, payload, metadata)
            if member:
                allowed = {c['assetId'] for c in source['clips']}
                allowed.update(r[0] for r in db.execute('SELECT asset_id FROM room_guest_uploads WHERE member_id=?', (member['id'],)))
                if payload['assetId'] not in allowed:
                    raise v.SongError('room_permission', 'Choose your uploaded audio or audio already in this song.', 403)
            asset = db.execute('SELECT * FROM assets WHERE id=? AND owner=?',
                               (payload['assetId'], g.song_builder_account)).fetchone()
            if asset is None:
                _missing()
            if asset['duration'] is None or payload['sourceOffset'] + payload['duration'] > asset['duration'] + .000001:
                v.invalid('The selected range extends beyond the uploaded audio.')
            if db.execute('SELECT count(*) FROM room_submissions WHERE project_id=?', (project_id,)).fetchone()[0] >= 100:
                raise v.SongError('submission_limit', 'This song has reached its 100-take submission limit.', 429)
            # Assets are append-only UUID files. A submission holds their exact IDs and never rewrites audio.
            db.execute('''INSERT INTO room_submissions
                (id,project_id,owner,actor,member_id,name,payload_hash,payload,asset_id,source_revision,
                 source_data,workflow_revision,workflow_data,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (payload['requestId'], project_id, g.song_builder_account, who, member['id'] if member else None,
                 member['name'] if member else 'Project owner', signature, json.dumps(payload), asset['id'],
                 current['revision'], current['data'], workflow_revision, json.dumps(metadata), time.time()))
            row = db.execute('SELECT * FROM room_submissions WHERE id=?', (payload['requestId'],)).fetchone()
            return jsonify(submission=_public(row)), 201

    @bp.get('/api/projects/<project_id>/submissions/<submission_id>/preview')
    def submission_preview(project_id, submission_id):
        v.identifier(project_id); v.identifier(submission_id)
        with service.store.connection(write=True) as db:
            current, member, who = _scope(db, service, project_id)
            row = _row(db, project_id, submission_id, member, who)
            _not_listening(db, project_id)
            source, payload = json.loads(row['source_data']), json.loads(row['payload'])
            assets = service.store._assets(db, g.song_builder_account, source)
            candidate = _candidate(source, payload, {a['id']: a['duration'] for a in assets}, row['id'])
            candidate_assets = service.store._assets(db, g.song_builder_account, candidate)
            start = 0
            for section in source['sections']:
                if section['id'] == payload['sectionId']:
                    break
                start += section['duration']
            workflow_revision = _workflow(db, g.song_builder_account, project_id)[1]
            return jsonify(project=candidate, assets=[_asset_json(a, project_id, submission_id) for a in candidate_assets],
                           start=start, end=start + section['duration'], sourceRevision=row['source_revision'],
                           stale=current['revision'] != row['source_revision'] or workflow_revision != row['workflow_revision'],
                           submission=_public(row))

    @bp.get('/api/projects/<project_id>/submissions/<submission_id>/assets/<asset_id>/audio')
    def submission_asset_audio(project_id, submission_id, asset_id):
        for value in (project_id, submission_id, asset_id):
            v.identifier(value)
        with service.store.connection() as db:
            _, member, who = _scope(db, service, project_id)
            row = _row(db, project_id, submission_id, member, who)
            ids = {c['assetId'] for c in json.loads(row['source_data'])['clips']} | {row['asset_id']}
            if asset_id not in ids:
                _missing()
            asset = db.execute('SELECT * FROM assets WHERE id=? AND owner=?', (asset_id, g.song_builder_account)).fetchone()
            if asset is None:
                _missing()
            path = service.store.asset_path(asset)
            if not path.is_file():
                raise v.SongError('audio_missing', 'This saved audio is temporarily unavailable.', 404)
            return send_file(path, mimetype=asset['mime'], conditional=True, etag=False,
                             download_name=asset['name'], as_attachment=False, max_age=0)

    def decision(db, project_id, submission_id, payload, action):
        current, member, who = _scope(db, service, project_id, owner=True)
        row = _row(db, project_id, submission_id, member, who)
        signature = _signature({'projectId': project_id, 'submissionId': submission_id, 'action': action, **payload})
        previous = db.execute('SELECT * FROM room_submission_decisions WHERE owner=? AND request_id=?',
                              (g.song_builder_account, payload['requestId'])).fetchone()
        if previous and previous['payload_hash'] != signature:
            raise v.SongError('submission_conflict', 'This decision request was already used for different settings.', 409)
        if not previous and row['status'] != 'pending':
            raise v.SongError('submission_decided', 'This take already has a decision. Ask for a new submission to review another performance.', 409)
        return current, row, signature, bool(previous)

    def decision_saved(db, row, payload, signature):
        db.execute('INSERT INTO room_submission_decisions VALUES(?,?,?,?)',
                   (g.song_builder_account, payload['requestId'], signature, row['id']))

    def accepted_result(db, row):
        result = service.store._project_result(db, service.store._owned_project(db, g.song_builder_account, row['accepted_project_id']))
        result['assets'] = [_asset_json(a) for a in result['assets']]
        return jsonify(submission=_public(row), version=result)

    @bp.post('/api/projects/<project_id>/submissions/<submission_id>/accept')
    def accept_submission(project_id, submission_id):
        v.identifier(project_id); v.identifier(submission_id)
        payload = body('requestId expectedRevision')
        v.identifier(payload['requestId']); v.revision(payload['expectedRevision'])
        with service.store.connection(write=True) as db:
            current, row, signature, retry = decision(db, project_id, submission_id, payload, 'accept')
            if retry:
                return accepted_result(db, row)
            _not_listening(db, project_id)
            metadata, workflow_revision = _workflow(db, g.song_builder_account, project_id)
            if (current['revision'] != payload['expectedRevision'] or current['revision'] != row['source_revision']
                    or workflow_revision != row['workflow_revision']):
                raise v.SongError('submission_stale', 'The source song or its workflow changed. Request a new take against the current saved backing.', 409)
            source, submitted = json.loads(current['data']), json.loads(row['payload'])
            _placement(source, submitted, metadata)
            assets = service.store._assets(db, g.song_builder_account, source)
            candidate = _candidate(source, submitted, {a['id']: a['duration'] for a in assets}, row['id'])
            v.enforce_locks(source, candidate); enforce_clip_protections(metadata, source, candidate)
            service.store._assets(db, g.song_builder_account, candidate)
            if db.execute('SELECT count(*) FROM projects WHERE owner=?', (g.song_builder_account,)).fetchone()[0] >= v.MAX_PROJECTS:
                raise v.SongError('storage_quota', 'The song limit has been reached. No version was created.', 429)
            version_id, now = str(uuid.uuid4()), time.time()
            candidate['id'] = version_id
            candidate['title'] = (source['title'][:96] + ' · accepted take')[:120]
            db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?)',
                       (version_id, g.song_builder_account, candidate['title'], json.dumps(candidate), 1, now, now))
            for asset_id in sorted({c['assetId'] for c in candidate['clips']}):
                db.execute('INSERT INTO project_assets VALUES(?,?)', (version_id, asset_id))
            db.execute('INSERT INTO room_workflow VALUES(?,?,?,?,?)',
                       (g.song_builder_account, version_id, workflow_revision, json.dumps(metadata), now))
            db.execute('''INSERT INTO room_contributions(project_id,member_id,revision,created)
                          SELECT ?,member_id,revision,created FROM room_contributions WHERE project_id=?''',
                       (version_id, project_id))
            if row['member_id']:
                db.execute('INSERT INTO room_contributions(project_id,member_id,revision,created) VALUES(?,?,?,?)',
                           (version_id, row['member_id'], 1, now))
            db.execute('INSERT INTO room_submission_versions VALUES(?,?,?,?,?,?)',
                       (version_id, project_id, current['revision'], row['id'], row['name'], now))
            snapshot(db, candidate, 1)
            db.execute("UPDATE room_submissions SET status='accepted',accepted_project_id=?,decided=? WHERE id=?", (version_id, now, row['id']))
            decision_saved(db, row, payload, signature)
            updated = db.execute('SELECT * FROM room_submissions WHERE id=?', (row['id'],)).fetchone()
            return accepted_result(db, updated), 201

    @bp.post('/api/projects/<project_id>/submissions/<submission_id>/changes')
    def request_submission_changes(project_id, submission_id):
        v.identifier(project_id); v.identifier(submission_id)
        payload = body('requestId reason'); v.identifier(payload['requestId']); v.string(payload['reason'], 1, 1000)
        with service.store.connection(write=True) as db:
            _, row, signature, retry = decision(db, project_id, submission_id, payload, 'changes')
            if not retry:
                db.execute("UPDATE room_submissions SET status='changes_requested',reason=?,decided=? WHERE id=?",
                           (payload['reason'].strip(), time.time(), row['id']))
                decision_saved(db, row, payload, signature)
            updated = db.execute('SELECT * FROM room_submissions WHERE id=?', (row['id'],)).fetchone()
            return jsonify(submission=_public(updated))
