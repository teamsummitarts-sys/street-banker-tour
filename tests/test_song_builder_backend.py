"""Boundary tests use temporary private storage and synthetic audio only."""
import copy
import io
import json
import uuid
import wave

import pytest
from flask import Flask, session

from song_builder import init


def uid():
    return str(uuid.uuid4())


def project():
    return {'schemaVersion': 1, 'id': uid(), 'title': 'Untitled song', 'tempo': 100,
            'key': 'D minor', 'sections': [{'id': uid(), 'name': 'Verse', 'duration': 8,
                'lyrics': '', 'direction': '', 'locked': False}], 'tracks': [], 'clips': []}


def wav_bytes(seconds=8):
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\x00\x00' * round(8000 * seconds))
    return out.getvalue()


def host(tmp_path, **config):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='song-tests-only', SONG_BUILDER_ENABLED=True)
    app.config.update(config)
    identity = {'user': {'id': 'alice'}}
    init(app, lambda: identity['user'], data_dir=tmp_path)
    return app, identity


def auth_headers(client, owner='alice'):
    with client.session_transaction() as state:
        state['song_builder_csrf'] = {'account': owner, 'token': 'test-token'}
    return {'X-Song-Builder-CSRF': 'test-token'}


def create(client, headers, value=None):
    value = value or project()
    response = client.post('/song-builder/api/projects', headers=headers, json={'project': value})
    assert response.status_code == 201, response.get_json()
    return response.json


def upload(client, headers, data=None):
    return client.post('/song-builder/api/assets', headers=headers,
                       data={'file': (io.BytesIO(data or wav_bytes()), '../../mix.wav')})


def test_music_retry_returns_same_job_after_project_edit(tmp_path):
    app, _ = host(tmp_path, SONG_BUILDER_MUSIC_ENABLED=True,
                  ELEVENLABS_API_KEY='test-placeholder', SONG_BUILDER_JOB_AUTOSTART=False)
    client = app.test_client()
    headers = auth_headers(client)
    saved = create(client, headers)
    value = saved['project']
    payload = {'requestId': uid(), 'kind': 'generate', 'projectId': value['id'],
               'sectionId': value['sections'][0]['id'], 'expectedRevision': saved['revision'],
               'prompt': 'Original musical direction'}
    first = client.post('/song-builder/api/jobs', headers=headers, json=payload)
    assert first.status_code == 202
    value['title'] = 'Later edits'
    assert client.put('/song-builder/api/projects/' + value['id'], headers=headers,
                      json={'project': value, 'expectedRevision': saved['revision']}).status_code == 200
    retry = client.post('/song-builder/api/jobs', headers=headers, json=payload)
    assert retry.status_code == 202
    assert retry.json['job']['id'] == first.json['job']['id']
    assert len(client.get('/song-builder/api/jobs?projectId=' + value['id']).json['jobs']) == 1


def test_version_branch_reuses_owned_audio_without_changing_original(tmp_path):
    app, _ = host(tmp_path)
    client = app.test_client()
    headers = auth_headers(client)
    original = project()
    asset = upload(client, headers).json['asset']
    original['tracks'] = [{'id': uid(), 'name': 'Drums', 'gainDb': 0, 'pan': 0,
                           'muted': False, 'solo': False}]
    original['clips'] = [{'id': uid(), 'trackId': original['tracks'][0]['id'],
        'sectionId': original['sections'][0]['id'], 'assetId': asset['id'], 'offset': 0,
        'sourceOffset': 0, 'duration': 8, 'loop': False, 'gainDb': 0}]
    first = create(client, headers, original)
    branch = copy.deepcopy(first['project'])
    branch['id'] = uid()
    branch['title'] = 'Heavy Chorus'
    second = create(client, headers, branch)
    assert second['project']['clips'][0]['assetId'] == asset['id']
    assert client.get('/song-builder/api/projects/' + original['id']).json['project']['title'] == 'Untitled song'


def test_oversized_combined_prompt_does_not_reserve_music_job(tmp_path):
    app, _ = host(tmp_path, SONG_BUILDER_MUSIC_ENABLED=True,
                  ELEVENLABS_API_KEY='test-placeholder', SONG_BUILDER_JOB_AUTOSTART=False)
    client = app.test_client()
    headers = auth_headers(client)
    value = project()
    value['sections'][0].update(lyrics='L' * 3000, direction='D' * 1000)
    saved = create(client, headers, value)
    response = client.post('/song-builder/api/jobs', headers=headers, json={
        'requestId': uid(), 'kind': 'generate', 'projectId': value['id'],
        'sectionId': value['sections'][0]['id'], 'expectedRevision': saved['revision'],
        'prompt': 'P' * 1000})
    assert response.status_code == 400
    assert client.get('/song-builder/api/jobs?projectId=' + value['id']).json['jobs'] == []


def test_default_off_and_unauthenticated_fail_closed(tmp_path):
    app, identity = host(tmp_path, SONG_BUILDER_ENABLED=False)
    client = app.test_client()
    assert client.get('/song-builder/api/projects').status_code == 404
    app.config['SONG_BUILDER_ENABLED'] = True
    identity['user'] = None
    assert client.get('/song-builder/api/projects').status_code == 401
    identity['user'] = {'id': True}
    assert client.get('/song-builder/api/projects').status_code == 401


def test_owner_isolation_revision_and_private_audio(tmp_path):
    app, identity = host(tmp_path)
    client = app.test_client()
    headers = auth_headers(client)
    saved = create(client, headers)
    asset_response = upload(client, headers)
    assert asset_response.status_code == 201
    asset = asset_response.json['asset']
    assert set(asset) == {'id', 'name', 'mime', 'size', 'duration', 'url'}
    assert asset['duration'] == 8
    audio = client.get(asset['url'])
    assert audio.status_code == 200 and audio.data == wav_bytes()
    assert audio.headers['Cache-Control'] == 'private, no-store'
    changed = copy.deepcopy(saved['project'])
    changed['title'] = 'Revised'
    route = '/song-builder/api/projects/' + changed['id']
    assert client.put(route, headers=headers, json={'project': changed, 'expectedRevision': 1}).json['revision'] == 2
    assert client.put(route, headers=headers, json={'project': changed, 'expectedRevision': 1}).status_code == 409
    identity['user'] = {'id': 'bob'}
    assert client.get(route).status_code == 404
    assert client.get(asset['url']).status_code == 404
    assert client.get('/song-builder/api/projects').json == {'projects': []}
    assert client.delete(route, headers=auth_headers(client, 'bob'), json={'expectedRevision': 2}).status_code == 404


def test_csrf_is_account_bound_and_checks_origin(tmp_path):
    app, identity = host(tmp_path)
    client = app.test_client()
    headers = auth_headers(client)
    payload = {'project': project()}
    for bad in ({}, {**headers, 'Origin': 'https://attacker.invalid'},
                {**headers, 'Sec-Fetch-Site': 'cross-site'}, {'X-Song-Builder-CSRF': 'é'}):
        assert client.post('/song-builder/api/projects', json=payload, headers=bad).status_code == 403
    identity['user'] = {'id': 'bob'}
    assert client.post('/song-builder/api/projects', json=payload, headers=headers).status_code == 403


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(owner='bob'),
    lambda p: p.update(tempo=True),
    lambda p: p.update(tempo=float('nan')),
    lambda p: p.update(sections=[]),
    lambda p: p['sections'][0].update(duration=float('inf')),
    lambda p: p['sections'][0].update(locked='false'),
    lambda p: p.update(id='../private'),
    lambda p: p['sections'].append(copy.deepcopy(p['sections'][0])),
])
def test_strict_schema(tmp_path, mutation):
    app, _ = host(tmp_path)
    client = app.test_client()
    value = project()
    mutation(value)
    assert client.post('/song-builder/api/projects', headers=auth_headers(client), json={'project': value}).status_code == 400


def test_duplicate_json_keys_rejected(tmp_path):
    app, _ = host(tmp_path)
    client = app.test_client()
    raw = '{"project":' + json.dumps(project()) + ',"project":' + json.dumps(project()) + '}'
    assert client.post('/song-builder/api/projects', headers=auth_headers(client), data=raw,
                       content_type='application/json').status_code == 400


def with_clip(value, asset):
    value['tracks'] = [{'id': uid(), 'name': 'Layer', 'gainDb': 0, 'pan': 0, 'muted': False, 'solo': False}]
    value['clips'] = [{'id': uid(), 'trackId': value['tracks'][0]['id'],
       'sectionId': value['sections'][0]['id'], 'assetId': asset['id'], 'offset': 0,
       'sourceOffset': 0, 'duration': 8, 'loop': False, 'gainDb': 0}]
    return value


def test_locked_sections_require_unlock_save_before_content_edit(tmp_path):
    app, _ = host(tmp_path)
    client = app.test_client()
    headers = auth_headers(client)
    asset = upload(client, headers).json['asset']
    value = with_clip(project(), asset)
    value['sections'][0]['locked'] = True
    create(client, headers, value)
    route = '/song-builder/api/projects/' + value['id']
    changed = copy.deepcopy(value)
    changed['sections'][0].update(locked=False, lyrics='A new lyric')
    assert client.put(route, headers=headers, json={'project': changed, 'expectedRevision': 1}).status_code == 409
    changed = copy.deepcopy(value)
    changed['clips'] = []
    assert client.put(route, headers=headers, json={'project': changed, 'expectedRevision': 1}).status_code == 409
    value['tracks'][0]['gainDb'] = -8
    assert client.put(route, headers=headers, json={'project': value, 'expectedRevision': 1}).status_code == 200
    value['sections'][0]['locked'] = False
    assert client.put(route, headers=headers, json={'project': value, 'expectedRevision': 2}).status_code == 200
    value['sections'][0]['lyrics'] = 'A new lyric'
    assert client.put(route, headers=headers, json={'project': value, 'expectedRevision': 3}).status_code == 200


def test_foreign_asset_and_out_of_bounds_audio_rejected(tmp_path):
    app, identity = host(tmp_path)
    client = app.test_client()
    asset = upload(client, auth_headers(client)).json['asset']
    identity['user'] = {'id': 'bob'}
    headers = auth_headers(client, 'bob')
    value = with_clip(project(), asset)
    assert client.post('/song-builder/api/projects', headers=headers, json={'project': value}).status_code == 404
    identity['user'] = {'id': 'alice'}
    headers = auth_headers(client)
    value['clips'][0]['sourceOffset'] = 1
    assert client.post('/song-builder/api/projects', headers=headers, json={'project': value}).status_code == 400


def test_upload_rejects_malformed_truncated_and_oversized_wav(tmp_path):
    app, _ = host(tmp_path)
    client = app.test_client()
    headers = auth_headers(client)
    for bad in (b'not audio', wav_bytes()[:-20]):
        assert upload(client, headers, bad).status_code == 400
    assert client.post('/song-builder/api/assets', headers=headers, data={'file': (io.BytesIO(b'x' * (32*1024*1024+1)), 'big.wav')}).status_code == 400
    assert client.get('/song-builder/api/capabilities').json['storage']['usedBytes'] == 0


def test_persistence_and_delete_preserves_shared_assets(tmp_path):
    app, _ = host(tmp_path)
    client = app.test_client()
    headers = auth_headers(client)
    asset = upload(client, headers).json['asset']
    first = create(client, headers, with_clip(project(), asset))
    second = create(client, headers, with_clip(project(), asset))
    restarted, _ = host(tmp_path)
    client = restarted.test_client()
    headers = auth_headers(client)
    assert len(client.get('/song-builder/api/projects').json['projects']) == 2
    assert client.delete('/song-builder/api/projects/' + first['project']['id'], headers=headers, json={'expectedRevision': 1}).status_code == 200
    assert client.get(asset['url']).status_code == 200
    assert client.get('/song-builder/api/projects/' + second['project']['id']).json['assets'] == [asset]
