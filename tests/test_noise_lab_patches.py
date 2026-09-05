"""Real SQLite patch persistence and private ownership tests; no live database."""
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from flask import Blueprint, Flask, g, jsonify, request

from noise_lab import patches


def recipe(**changes):
    value = {'schemaVersion': 1, 'engineVersion': 'noise-lab-1.0.0',
             'profile': 'metal-bloom', 'macros': {
                 'texture': 76, 'motion': 22, 'space': 30, 'mix': 68, 'level': -12}}
    value.update(changes)
    return value


def payload(name='Metal Bloom', **changes):
    value = {'requestId': str(uuid.uuid4()), 'name': name, 'recipe': recipe()}
    value.update(changes)
    return value


def make_app(enabled=True):
    app = Flask(__name__)
    app.config.update(TESTING=True, NOISE_LAB_PATCH_STORAGE_ENABLED=enabled)
    bp = Blueprint('patch_test', __name__, url_prefix='/noise-lab')

    @bp.before_request
    def identity():
        # Synthetic identity injection exists only in this isolated test host.
        g.noise_lab_account = request.headers.get('X-Test-Account', 'one')

    def csrf():
        if request.headers.get('X-Noise-Lab-CSRF') != 'test-token':
            return jsonify(error='session_check'), 403

    patches.register_patch_routes(bp, csrf)
    app.register_blueprint(bp)
    return app


@pytest.fixture
def host(tmp_path, monkeypatch):
    path = tmp_path / 'host.sqlite'
    monkeypatch.setenv('DATABASE_PATH', str(path))
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE users (id TEXT PRIMARY KEY)')
        db.executemany('INSERT INTO users VALUES (?)', [('one',), ('two',)])
    return make_app(), path


HEADERS = {'X-Noise-Lab-CSRF': 'test-token'}
BASE = '/noise-lab/api/patches'


def create(client, data=None, account='one'):
    return client.post(BASE, json=data or payload(),
                       headers={**HEADERS, 'X-Test-Account': account})


def test_create_reopen_append_and_export_preserve_immutable_versions(host):
    app, _ = host
    data = payload(name='  My private sound  ')
    response = create(app.test_client(), data)
    assert response.status_code == 201
    saved = response.json['patch']
    assert saved['name'] == 'My private sound'
    assert saved['headVersion'] == 1
    assert saved['versions'][0]['recipe'] == data['recipe']
    client = make_app().test_client()
    assert client.get(BASE).json['patches'][0]['id'] == saved['id']
    changed = payload(name='Darker', baseVersion=1, recipe=recipe(profile='dark-room'))
    response = client.post(f"{BASE}/{saved['id']}/versions", json=changed, headers=HEADERS)
    assert response.status_code == 201
    current = response.json['patch']
    assert current['headVersion'] == 2
    assert current['versions'][0] == saved['versions'][0]
    assert current['versions'][1]['recipe']['profile'] == 'dark-room'
    exported = client.get(f"{BASE}/{saved['id']}/export").json
    assert exported == {'archiveVersion': 1, 'patch': current}


def test_every_patch_operation_is_scoped_to_authenticated_owner(host):
    app, _ = host
    client = app.test_client()
    own = create(client).json['patch']
    other = create(client, account='two').json['patch']
    assert [p['id'] for p in client.get(BASE).json['patches']] == [own['id']]
    assert [p['id'] for p in client.get(BASE, headers={'X-Test-Account': 'two'}).json['patches']] == [other['id']]
    for target in (other['id'], str(uuid.uuid4()), 'invalid-identifier'):
        for suffix in ('', '/export'):
            response = client.get(f'{BASE}/{target}{suffix}')
            assert response.status_code == 404
            assert response.json == {'error': 'not_found'}
        response = client.post(f'{BASE}/{target}/versions', headers=HEADERS, json=payload(baseVersion=1))
        assert response.status_code == 404
        assert response.json == {'error': 'not_found'}
        response = client.delete(f'{BASE}/{target}', headers=HEADERS, json={'baseVersion': 1})
        assert response.status_code == 404
        assert response.json == {'error': 'not_found'}
    assert client.get(BASE, headers={'X-Test-Account': ''}).status_code == 404


def test_mutations_enforce_csrf_same_origin_and_json_ownership(host):
    app, _ = host
    client = app.test_client()
    saved = create(client).json['patch']
    operations = [('post', BASE, payload()),
                  ('post', f"{BASE}/{saved['id']}/versions", payload(baseVersion=1)),
                  ('delete', f"{BASE}/{saved['id']}", {'baseVersion': 1})]
    for method, url, data in operations:
        for headers in ({}, {**HEADERS, 'Origin': 'https://attacker.invalid'},
                        {**HEADERS, 'Sec-Fetch-Site': 'cross-site'}):
            assert getattr(client, method)(url, json=data, headers=headers).status_code == 403
        assert getattr(client, method)(url, json={**data, 'owner_id': 'two'}, headers=HEADERS).status_code == 400
    assert client.get(f"{BASE}/{saved['id']}").json['patch']['headVersion'] == 1


@pytest.mark.parametrize('name', ['', ' ' * 10, 'x' * 81, 14, None, 'hello\nworld', '\ud800'])
def test_invalid_names_do_not_create_records(host, name):
    client = host[0].test_client()
    response = create(client, payload(name=name))
    assert response.status_code == 400
    assert response.json == {'error': 'invalid_patch'}
    assert client.get(BASE).json['patches'] == []


@pytest.mark.parametrize('changed', [
    {'schemaVersion': 2}, {'schemaVersion': True}, {'engineVersion': 'future-2'},
    {'profile': 'code:alert(1)'}, {'profile': []}, {'script': 'execute this'},
    {'macros': {'texture': 0}}, {'macros': []},
])
def test_unknown_recipe_versions_and_fields_are_rejected(host, changed):
    response = create(host[0].test_client(), payload(recipe=recipe(**changed)))
    assert response.status_code == 422
    assert response.json == {'error': 'incompatible_recipe'}


@pytest.mark.parametrize('value', [None, True, '2', -1, 101, float('nan'), float('inf'), 10**2000])
def test_macro_values_are_finite_and_not_coerced(host, value):
    data = recipe()
    data['macros']['texture'] = value
    response = create(host[0].test_client(), payload(recipe=data))
    assert response.status_code in (400, 422)


@pytest.mark.parametrize('level', [-61, 1, True, '0'])
def test_output_level_bounds_are_enforced(host, level):
    data = recipe()
    data['macros']['level'] = level
    response = create(host[0].test_client(), payload(recipe=data))
    assert response.status_code == 422


@pytest.mark.parametrize('raw', ['not JSON', '[]', '{}', '{"name":"a","name":"b"}',
    'x' * 8193, '{"requestId":"not-a-uuid","name":"a","recipe":{}}',
    b'\xff'])
def test_malformed_bounded_json_has_no_effect(host, raw):
    client = host[0].test_client()
    response = client.post(BASE, headers=HEADERS, content_type='application/json', data=raw)
    assert response.status_code == 400
    assert response.json == {'error': 'invalid_patch'}
    assert client.get(BASE).json['patches'] == []


def test_idempotent_retries_return_original_snapshot_and_reject_changed_payload(host):
    client = host[0].test_client()
    original = payload()
    first = create(client, original)
    saved = first.json['patch']
    duplicate = create(client, original)
    assert duplicate.status_code == 200
    assert duplicate.json == first.json
    assert len(client.get(BASE).json['patches']) == 1
    assert create(client, {**original, 'name': 'Changed'}).json == {'error': 'request_conflict'}
    assert create(client, original, account='two').status_code == 201
    version_data = payload(name='Next version', baseVersion=1)
    second = client.post(f"{BASE}/{saved['id']}/versions", headers=HEADERS, json=version_data)
    assert second.status_code == 201
    retry = client.post(f"{BASE}/{saved['id']}/versions", headers=HEADERS, json=version_data)
    assert retry.status_code == 200
    assert retry.json == second.json
    assert create(client, original).json == first.json
    changed = client.post(f"{BASE}/{saved['id']}/versions", headers=HEADERS,
                          json={**version_data, 'baseVersion': 2})
    assert changed.status_code == 409
    assert changed.json == {'error': 'request_conflict'}
    reuse_operation = client.post(f"{BASE}/{saved['id']}/versions", headers=HEADERS,
                                  json={**original, 'baseVersion': 2})
    assert reuse_operation.json == {'error': 'request_conflict'}


def test_stale_write_and_delete_preserve_latest_version(host):
    client = host[0].test_client()
    saved = create(client).json['patch']
    url = f"{BASE}/{saved['id']}"
    assert client.post(url + '/versions', headers=HEADERS, json=payload(baseVersion=1)).status_code == 201
    for method, target, data in [('post', url + '/versions', payload(baseVersion=1)),
                                 ('delete', url, {'baseVersion': 1})]:
        response = getattr(client, method)(target, headers=HEADERS, json=data)
        assert response.status_code == 409
        assert response.json == {'error': 'version_conflict'}
    assert client.get(url).json['patch']['headVersion'] == 2


def test_concurrent_updates_commit_one_version_without_silent_overwrite(host):
    app, _ = host
    saved = create(app.test_client()).json['patch']
    def append(index):
        return app.test_client().post(f"{BASE}/{saved['id']}/versions", headers=HEADERS,
                                     json=payload(name=f'Writer {index}', baseVersion=1)).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(append, [1, 2]))
    assert sorted(statuses) == [201, 409]
    current = app.test_client().get(f"{BASE}/{saved['id']}").json['patch']
    assert current['headVersion'] == 2
    assert len(current['versions']) == 2


def test_concurrent_duplicate_requests_commit_once(host):
    app, _ = host
    data = payload()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: create(app.test_client(), data), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json == responses[1].json
    assert len(app.test_client().get(BASE).json['patches']) == 1


def test_concurrent_creates_cannot_exceed_account_quota(host, monkeypatch):
    app, _ = host
    monkeypatch.setattr(patches, 'PATCH_LIMIT', 1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: create(app.test_client()), range(2)))
    assert sorted(response.status_code for response in responses) == [201, 429]
    assert [r.json for r in responses if r.status_code == 429] == [{'error': 'patch_limit'}]
    assert len(app.test_client().get(BASE).json['patches']) == 1


def test_delete_removes_content_and_leaves_non_resurrecting_tombstones(host):
    app, path = host
    client = app.test_client()
    data = payload()
    saved = create(client, data).json['patch']
    url = f"{BASE}/{saved['id']}"
    appended = payload(name='Second private name', baseVersion=1)
    assert client.post(url + '/versions', headers=HEADERS, json=appended).status_code == 201
    assert client.delete(url, headers=HEADERS, json={'baseVersion': 2}).json == {'deleted': True}
    assert client.get(BASE).json['patches'] == []
    assert client.get(url + '/export').status_code == 404
    assert create(client, data).json == {'error': 'request_retired'}
    retry = client.post(url + '/versions', headers=HEADERS, json=appended)
    assert retry.status_code == 410
    assert retry.json == {'error': 'request_retired'}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patches').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patch_versions').fetchone()[0] == 0
        columns = {row[1] for row in db.execute('PRAGMA table_info(noise_lab_patch_requests)')}
        assert columns == {'owner_id', 'request_id', 'operation', 'fingerprint', 'patch_id', 'version'}
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patch_requests').fetchone()[0] == 2


def test_deleting_account_cascades_patch_versions_and_tombstones(host):
    app, path = host
    client = app.test_client()
    create(client)
    other = create(client, account='two').json['patch']
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute("DELETE FROM users WHERE id='one'")
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patches').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patch_versions').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patch_requests').fetchone()[0] == 1
    assert client.get(BASE, headers={'X-Test-Account': 'two'}).json['patches'][0]['id'] == other['id']


def test_patch_and_version_limits_are_atomic_and_do_not_consume_request_id(host, monkeypatch):
    app, _ = host
    monkeypatch.setattr(patches, 'PATCH_LIMIT', 2)
    monkeypatch.setattr(patches, 'VERSION_LIMIT', 2)
    client = app.test_client()
    saved = create(client).json['patch']
    create(client)
    data = payload()
    assert create(client, data).json == {'error': 'patch_limit'}
    assert create(client, account='two').status_code == 201
    url = f"{BASE}/{saved['id']}"
    assert client.post(url + '/versions', headers=HEADERS, json=payload(baseVersion=1)).status_code == 201
    response = client.post(url + '/versions', headers=HEADERS, json=payload(baseVersion=2))
    assert response.status_code == 429
    assert response.json == {'error': 'version_limit'}
    assert client.delete(url, headers=HEADERS, json={'baseVersion': 2}).status_code == 200
    assert create(client, data).status_code == 201


def test_deleted_request_ledger_has_bounded_retention_per_account(host, monkeypatch):
    app, _ = host
    monkeypatch.setattr(patches, 'REQUEST_LIMIT', 2)
    client = app.test_client()
    for _ in range(2):
        saved = create(client).json['patch']
        client.delete(f"{BASE}/{saved['id']}", headers=HEADERS, json={'baseVersion': 1})
    assert create(client).status_code == 429
    assert create(client).json == {'error': 'request_limit'}
    assert create(client, account='two').status_code == 201


@pytest.mark.parametrize('raw', [json.dumps(recipe(engineVersion='future-2', schemaVersion=2)),
    json.dumps(recipe(extra='preserve future data')), 'unreadable legacy recipe', '1e309'])
def test_unknown_or_corrupt_stored_recipe_is_readable_and_exported_without_migration(host, raw):
    app, path = host
    client = app.test_client()
    saved = create(client).json['patch']
    with sqlite3.connect(path) as db:
        db.execute('UPDATE noise_lab_patch_versions SET recipe_json=? WHERE patch_id=?', (raw, saved['id']))
    version = client.get(f"{BASE}/{saved['id']}").json['patch']['versions'][0]
    assert version['compatible'] is False
    exported = client.get(f"{BASE}/{saved['id']}/export").json['patch']['versions'][0]
    assert exported == version
    if raw.startswith('{'):
        assert version['recipe'] == json.loads(raw)
    else:
        assert version['recipe'] is None
        assert version['recipeRaw'] == raw
    assert client.post(f"{BASE}/{saved['id']}/versions", headers=HEADERS,
                       json=payload(baseVersion=1)).status_code == 201
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT recipe_json FROM noise_lab_patch_versions WHERE version=1').fetchone()[0] == raw


def test_unknown_database_schema_fails_closed_without_rewriting_data(host):
    app, path = host
    saved = create(app.test_client()).json['patch']
    with sqlite3.connect(path) as db:
        db.execute('UPDATE noise_lab_store_meta SET schema_version=2')
    response = create(app.test_client())
    assert response.status_code == 503
    assert response.json == {'error': 'storage_unavailable'}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT schema_version FROM noise_lab_store_meta').fetchone()[0] == 2
        assert db.execute('SELECT id FROM noise_lab_patches').fetchall() == [(saved['id'],)]


def test_unrecognized_schema_without_metadata_is_not_silently_replaced(host):
    app, path = host
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE noise_lab_legacy (private_data TEXT)')
        db.execute("INSERT INTO noise_lab_legacy VALUES ('preserved')")
    response = create(app.test_client())
    assert response.status_code == 503
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'noise_lab_%'").fetchall() == [('noise_lab_legacy',)]
        assert db.execute('SELECT private_data FROM noise_lab_legacy').fetchone()[0] == 'preserved'


def test_disabled_storage_has_no_schema_side_effects(host):
    _, path = host
    client = make_app(enabled=False).test_client()
    assert client.get(BASE).status_code == 503
    assert create(client).json == {'error': 'storage_unavailable'}
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'noise_lab_%'").fetchall() == []


def test_storage_mount_guard_rejects_ephemeral_paths_and_symlink_escape(host, monkeypatch, tmp_path):
    app, path = host
    app.config['TESTING'] = False
    with app.app_context():
        assert not patches.storage_ready()
        app.config['NOISE_LAB_PERSISTENT_ROOT'] = str(tmp_path)
        assert not patches.storage_ready()  # Ordinary directory is not a persistent mount.
        monkeypatch.setattr(patches.os.path, 'ismount', lambda root: root == str(tmp_path))
        assert patches.storage_ready()
        monkeypatch.setenv('DATABASE_PATH', str(tmp_path.parent / 'outside.sqlite'))
        assert not patches.storage_ready()
        link = tmp_path / 'escaped.sqlite'
        link.symlink_to(tmp_path.parent / 'outside.sqlite')
        monkeypatch.setenv('DATABASE_PATH', str(link))
        assert not patches.storage_ready()
        monkeypatch.setenv('DATABASE_PATH', str(path))
        app.config['NOISE_LAB_PERSISTENT_ROOT'] = '/'
        monkeypatch.setattr(patches.os.path, 'ismount', lambda _: True)
        assert not patches.storage_ready()


def test_write_failure_rolls_back_all_parts_and_does_not_expose_raw_error(host, monkeypatch):
    app, path = host
    client = app.test_client()
    saved = create(client).json['patch']
    original = patches._record_request
    def fail(*args):
        raise sqlite3.OperationalError('private details and database path')
    monkeypatch.setattr(patches, '_record_request', fail)
    assert create(client).json == {'error': 'storage_unavailable'}
    response = client.post(f"{BASE}/{saved['id']}/versions", headers=HEADERS, json=payload(baseVersion=1))
    assert response.status_code == 503
    assert response.json == {'error': 'storage_unavailable'}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patches').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patch_versions').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM noise_lab_patch_requests').fetchone()[0] == 1
        assert db.execute('SELECT head_version FROM noise_lab_patches').fetchone()[0] == 1
    monkeypatch.setattr(patches, '_record_request', original)
    assert client.post(f"{BASE}/{saved['id']}/versions", headers=HEADERS,
                       json=payload(baseVersion=1)).status_code == 201


def test_first_write_failure_rolls_back_lazy_schema_and_foreign_account_cannot_save(host, monkeypatch):
    app, path = host
    def fail(*args):
        raise sqlite3.OperationalError('private details')
    monkeypatch.setattr(patches, '_record_request', fail)
    response = create(app.test_client())
    assert response.status_code == 503
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'noise_lab_%'").fetchall() == []
    # Even an erroneous injected host identity cannot create an orphan account row.
    response = create(app.test_client(), account='no-such-account')
    assert response.status_code == 503
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'noise_lab_%'").fetchall() == []


def test_defaults_match_documented_bounds():
    assert patches.PATCH_LIMIT == 50
    assert patches.VERSION_LIMIT == 100
    assert patches.REQUEST_LIMIT == 5000
    assert patches.BODY_LIMIT == 8192
