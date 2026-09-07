import io
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from flask import Flask
from noise_lab import init, sound_effects as sfx

AUDIO = b'ID3' + bytes(200)

@pytest.fixture
def host(tmp_path, monkeypatch):
    path = tmp_path / 'host.db'
    monkeypatch.setenv('DATABASE_PATH', str(path))
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE users(id TEXT PRIMARY KEY)')
        conn.executemany('INSERT INTO users VALUES (?)', [('one',), ('two',)])
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='test', NOISE_LAB_ENABLED=True,
        NOISE_LAB_PATCH_STORAGE_ENABLED=True, ELEVENLABS_API_KEY='test-only',
        NOISE_LAB_SFX_PROVIDER=lambda *args: AUDIO, NOISE_LAB_SFX_ENABLED=True)
    init(app, lambda: {'id':'one'})
    client = app.test_client()
    scope = client.get('/noise-lab/capabilities').json['account_scope']
    return app, client, {'X-Noise-Lab-CSRF':scope}, path

def payload(**changes):
    return dict(requestId=str(uuid.uuid4()), prompt='Metal impact', seconds=5, loop=False, **changes)

def send(host, data=None, headers=None):
    return host[1].post('/noise-lab/api/sound-effects', json=data or payload(), headers=host[2] if headers is None else headers)

def test_real_route_returns_private_audio_and_never_stores_prompt(host):
    assert host[1].get('/noise-lab/capabilities').json['sound_effects']
    result = send(host)
    assert result.status_code == 200 and result.data == AUDIO
    assert result.mimetype == 'audio/mpeg' and result.headers['Cache-Control'] == 'no-store'
    with sqlite3.connect(host[3]) as conn:
        row = conn.execute('SELECT * FROM noise_lab_sfx_requests').fetchone()
        assert row[1] == 'one' and row[3:] == (1,5)
        assert 'Metal impact' not in repr(row)

def test_forged_owner_and_invalid_inputs_never_call_provider(host):
    calls = []
    host[0].config['NOISE_LAB_SFX_PROVIDER'] = lambda *args: calls.append(args)
    assert send(host, headers={}).status_code == 403
    for changes in [{'owner':'two'}, {'seconds':30}, {'seconds':True}, {'loop':'yes'}, {'prompt':' '}, {'requestId':'bad'}]:
        data = payload(); data.update(changes)
        assert send(host,data).status_code == 400
    assert calls == []

def test_duplicate_failed_request_cannot_trigger_another_paid_call(host):
    calls = []
    def fail(*args):
        calls.append(args)
        raise sfx.SoundError('provider_quota')
    host[0].config['NOISE_LAB_SFX_PROVIDER'] = fail
    data = payload()
    assert send(host,data).json['error'] == 'provider_quota'
    assert send(host,data).status_code == 409
    assert len(calls) == 1

def test_limits_survive_new_connections_and_are_per_owner(host):
    with host[0].app_context():
        with sqlite3.connect(host[3]) as conn:
            sfx.schema(conn)
            conn.executemany('INSERT INTO noise_lab_sfx_requests VALUES (?,?,0,1,5)', [(str(uuid.uuid4()),'one') for _ in range(20)])
        with pytest.raises(sfx.SoundError, match='limit'):
            sfx.reserve('one',str(uuid.uuid4()),5)
        sfx.reserve('two',str(uuid.uuid4()),5)

def test_concurrent_reservations_only_admit_one_per_account(host):
    def attempt(_):
        with host[0].app_context():
            try: sfx.reserve('one',str(uuid.uuid4()),5); return 'ok'
            except sfx.SoundError as error: return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(attempt,range(2)))
    assert sorted(result) == ['busy','ok']

def test_disabled_or_missing_credentials_do_not_reserve(host):
    host[0].config['ELEVENLABS_API_KEY'] = ''
    assert send(host).status_code == 503
    with sqlite3.connect(host[3]) as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='noise_lab_sfx_requests'").fetchone()

@pytest.mark.parametrize('value',[b'', b'<html>provider error</html>', b'ID3'+bytes(sfx.MAX_BYTES)])
def test_invalid_provider_audio_is_rejected(host,value):
    host[0].config['NOISE_LAB_SFX_PROVIDER'] = lambda *args: value
    assert send(host).json['error'] == 'provider_audio'

def test_provider_request_uses_fixed_endpoint_and_bounded_contract(monkeypatch):
    seen=[]
    class Response(io.BytesIO):
        status=200; headers={}
    class Opener:
        def open(self, request, timeout):
            seen.append((request,timeout)); return Response(AUDIO)
    monkeypatch.setattr(sfx.urllib.request,'build_opener',lambda *_:Opener())
    assert sfx.generate_audio('impact',8,True,'test-only') == AUDIO
    import json
    req,timeout = seen[0]
    assert req.full_url == sfx.URL and timeout == 60
    assert json.loads(req.data) == dict(text='impact',duration_seconds=8,loop=True,model_id='eleven_text_to_sound_v2',prompt_influence=0.3)
    assert req.get_header('Xi-api-key') == 'test-only'
