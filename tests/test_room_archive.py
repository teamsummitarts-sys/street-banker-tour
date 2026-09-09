import copy
import io
import json
import zipfile

import pytest

from test_room_workflow import app_client, make_project, metadata, uid, wav_bytes
from test_room_collaboration import setup, invite, join


def archive(client, pid):
    result = client.get('/song-builder/api/projects/' + pid + '/archive')
    assert result.status_code == 200, result.data[:200]
    return result.data


def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return json.loads(z.read('session.json')), {n: z.read(n) for n in z.namelist() if n != 'session.json'}


def repack(manifest, files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED) as z:
        z.writestr('session.json', json.dumps(manifest))
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def restore(client, headers, data):
    return client.post('/song-builder/api/session-archives', headers=headers,
                       data={'file': (io.BytesIO(data), 'session.room.zip')})


def populated(app, client, h):
    saved = make_project(client, h)
    project = saved['project']
    alternate = client.post('/song-builder/api/assets', headers=h,
        data={'file': (io.BytesIO(wav_bytes()), 'alternate.wav')}).json['asset']
    clip = {**project['clips'][0], 'id': uid(), 'assetId': alternate['id']}
    workflow = metadata(
        scenes=[{'id': uid(), 'sectionId': clip['sectionId'], 'name': 'Earlier chorus', 'clips': [clip]}],
        takes=[{'id': uid(), 'sectionId': clip['sectionId'], 'trackId': clip['trackId'], 'name': 'Alternate', 'clips': [clip]}],
        protections=[{'clipId': project['clips'][0]['id'], 'mode': 'never'}])
    assert client.put('/song-builder/api/workflow/' + project['id'], headers=h,
        json={'metadata': workflow, 'expectedRevision': 0}).status_code == 200
    assert client.post('/song-builder/api/projects/' + project['id'] + '/feedback', headers=h,
        json={'id': uid(), 'text': 'Keep this vocal', 'position': 1.25, 'expectedRevision': 1}).status_code == 201
    return saved, workflow, alternate


def test_archive_preserves_alternate_audio_feedback_protection_and_never_overwrites(tmp_path):
    app, client, h = app_client(tmp_path)
    saved, workflow, alternate = populated(app, client, h)
    pid = saved['project']['id']
    data = archive(client, pid)
    manifest, files = unpack(data)
    assert len(files) == 2
    assert {a['id'] for a in manifest['assets']} == {alternate['id'], saved['assets'][0]['id']}
    assert manifest['snapshot']['workflow'] == workflow
    assert manifest['snapshot']['feedback'][0]['text'] == 'Keep this vocal'
    result = restore(client, h, data)
    assert result.status_code == 201, result.json
    new_id = result.json['projectId']
    assert new_id != pid
    assert client.get('/song-builder/api/projects/' + pid).json == saved
    restored = client.get('/song-builder/api/projects/' + new_id).json
    assert restored['revision'] == 1
    assert restored['project']['sections'][0]['id'] != saved['project']['sections'][0]['id']
    newer = client.get('/song-builder/api/workflow?projectId=' + new_id).json['metadata']
    assert newer['protections'][0]['clipId'] == restored['project']['clips'][0]['id']
    assert newer['takes'][0]['clips'][0]['assetId'] != alternate['id']
    assert client.get('/song-builder/api/assets/' + newer['takes'][0]['clips'][0]['assetId'] + '/audio').data == wav_bytes()
    comments = client.get('/song-builder/api/projects/' + new_id + '/listening').json['comments']
    assert comments[0]['text'] == 'Keep this vocal' and comments[0]['position'] == 1.25
    protected = copy.deepcopy(restored['project'])
    protected['clips'][0]['gainDb'] = -5
    assert client.put('/song-builder/api/projects/' + new_id, headers=h,
        json={'project': protected, 'expectedRevision': 1}).status_code == 409


def test_checkpoint_is_named_revision_snapshot_and_restores_separate_version(tmp_path):
    app, client, h = app_client(tmp_path)
    saved, workflow, alternate = populated(app, client, h)
    pid = saved['project']['id']; path = '/song-builder/api/projects/' + pid + '/checkpoints'
    result = client.post(path, headers=h, json={'name': 'Before drums', 'expectedRevision': 1, 'expectedWorkflowRevision': 1})
    assert result.status_code == 201, result.json
    checkpoint = result.json['checkpoint']
    assert checkpoint['name'] == 'Before drums' and checkpoint['revision'] == 1
    assert checkpoint['author'] == 'Project owner'
    assert client.post(path, headers=h, json={'name': 'Stale', 'expectedRevision': 2, 'expectedWorkflowRevision': 1}).status_code == 409
    changed = copy.deepcopy(saved['project']); changed['title'] = 'Later mix'
    assert client.put('/song-builder/api/projects/' + pid, headers=h,
        json={'project': changed, 'expectedRevision': 1}).status_code == 200
    result = client.post(path + '/' + checkpoint['id'] + '/restore', headers=h, json={})
    assert result.status_code == 201, result.json
    new_id = result.json['projectId']
    assert new_id != pid
    assert client.get('/song-builder/api/projects/' + pid).json['project']['title'] == 'Later mix'
    restored = client.get('/song-builder/api/projects/' + new_id).json['project']
    assert 'Before drums' in restored['title']
    assert client.get('/song-builder/api/workflow?projectId=' + new_id).json['metadata']['takes'][0]['name'] == 'Alternate'
    data = archive(client, pid)
    imported = restore(client, h, data)
    assert imported.status_code == 201
    imported_checkpoints = client.get('/song-builder/api/projects/' + imported.json['projectId'] + '/checkpoints').json['checkpoints']
    assert imported_checkpoints[0]['name'] == 'Before drums'


@pytest.mark.parametrize('change', ['missing', 'traversal', 'hash', 'unknown', 'duplicate', 'invalid_workflow'])
def test_malformed_archives_leave_no_partial_project_or_audio(tmp_path, change):
    app, client, h = app_client(tmp_path)
    saved = make_project(client, h)
    manifest, files = unpack(archive(client, saved['project']['id']))
    if change == 'missing': files = {}
    elif change == 'traversal': files['../outside.wav'] = b'untrusted'
    elif change == 'hash': files[next(iter(files))] = b'x' * len(next(iter(files.values())))
    elif change == 'unknown': manifest['credentials'] = {'secret': 'do not import'}
    elif change == 'invalid_workflow': manifest['snapshot']['workflow']['scenes'] = [{}]
    data = repack(manifest, files)
    if change == 'duplicate':
        stream = io.BytesIO(data)
        with zipfile.ZipFile(stream, 'a') as z:
            with pytest.warns(UserWarning): z.writestr('session.json', json.dumps(manifest))
        data = stream.getvalue()
    before = client.get('/song-builder/api/projects').json
    old_files = set(app.extensions['song_builder'].store.audio_dir.iterdir())
    result = restore(client, h, data)
    assert result.status_code == 400, result.json
    assert client.get('/song-builder/api/projects').json == before
    assert set(app.extensions['song_builder'].store.audio_dir.iterdir()) == old_files


def test_restore_compensates_audio_files_when_later_write_fails(tmp_path, monkeypatch):
    app, client, h = app_client(tmp_path)
    saved, _, _ = populated(app, client, h)
    data = archive(client, saved['project']['id'])
    store = app.extensions['song_builder'].store
    original = store._write_audio; writes = []
    def fail_second(data, asset_id):
        if writes: raise OSError('simulated disk full')
        path = original(data, asset_id); writes.append(path); return path
    monkeypatch.setattr(store, '_write_audio', fail_second)
    before = set(store.audio_dir.iterdir())
    result = restore(client, h, data)
    assert result.status_code == 503
    assert len(client.get('/song-builder/api/projects').json['projects']) == 1
    assert set(store.audio_dir.iterdir()) == before


def test_owner_permissions_and_csrf(tmp_path):
    app, owner, h, saved = setup(tmp_path)
    pid = saved['project']['id']; data = archive(owner, pid)
    for role in ('editor', 'viewer'):
        guest, gh = join(app, invite(owner, h, saved, role))
        assert guest.get('/song-builder/api/projects/' + pid + '/archive').status_code == 403
        assert guest.get('/song-builder/api/projects/' + pid + '/checkpoints').status_code == 403
        assert restore(guest, gh, data).status_code == 403
    assert restore(owner, {}, data).status_code == 403
    stranger = app.test_client()
    with stranger.session_transaction() as s: s['host'] = 'bob'
    assert stranger.get('/song-builder/api/projects/' + pid + '/archive').status_code == 404
    assert stranger.get('/song-builder/api/projects/' + pid + '/checkpoints').status_code == 404


def test_archive_limit_is_scoped_without_changing_host_upload_limit(tmp_path):
    app,c,h=app_client(tmp_path);saved=make_project(c,h);data=archive(c,saved['project']['id'])
    app.config['MAX_CONTENT_LENGTH']=200
    r=restore(c,h,data);assert r.status_code==201,r.json
    assert app.config['MAX_CONTENT_LENGTH']==200
    oversized=copy.deepcopy(saved['project']);oversized['id']=uid()
    assert c.post('/song-builder/api/projects',headers=h,json={'project':oversized}).status_code==400
