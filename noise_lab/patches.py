"""Private, immutable recipe versions in the host's existing SQLite database.

No recording, prompt, or provider credential is stored. Schema initialization is
lazy and gated by an explicit storage flag and a verified persistent mount.
"""
import hashlib
import json
import math
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps

from flask import current_app, g, jsonify, request

import db as host_db
from .generation import GenerationError, strict_json


STORE_VERSION = 1
PATCH_LIMIT = 50
VERSION_LIMIT = 100
REQUEST_LIMIT = 5000
BODY_LIMIT = 8192
PROFILES = {'clean', 'metal-bloom', 'slow-orbit', 'dark-room'}
TABLES = {'noise_lab_store_meta', 'noise_lab_patches',
          'noise_lab_patch_versions', 'noise_lab_patch_requests'}


class PatchError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def storage_ready():
    """Never label an ephemeral host database as durable account storage."""
    flag = current_app.config.get('NOISE_LAB_PATCH_STORAGE_ENABLED', False)
    if flag is not True and flag != '1':
        return False
    if current_app.testing:
        return True
    root = current_app.config.get('NOISE_LAB_PERSISTENT_ROOT', '')
    if not isinstance(root, str) or not root or not os.path.isabs(root):
        return False
    try:
        root = os.path.realpath(root)
        path = os.path.realpath(host_db.db_path())
        return (root != os.path.sep and os.path.ismount(root)
                and path != root and os.path.commonpath([root, path]) == root)
    except (OSError, TypeError, ValueError):
        return False


def _uuid(value):
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError()
    parsed = str(uuid.UUID(value))
    if parsed != value:
        raise ValueError()
    return parsed


def validate_recipe(value):
    """Accept data for the tested v1 engine only; never repair or clamp inputs."""
    if (type(value) is not dict or set(value) !=
            {'schemaVersion', 'engineVersion', 'profile', 'macros'}
            or type(value['schemaVersion']) is not int or value['schemaVersion'] != 1
            or value['engineVersion'] != 'noise-lab-1.0.0'
            or not isinstance(value['profile'], str) or value['profile'] not in PROFILES):
        raise PatchError('incompatible_recipe', 422)
    macros = value['macros']
    if type(macros) is not dict or set(macros) != {'texture', 'motion', 'space', 'mix', 'level'}:
        raise PatchError('incompatible_recipe', 422)
    for key, number in macros.items():
        lo, hi = (-60, 0) if key == 'level' else (0, 100)
        if (type(number) not in (float, int) or not lo <= number <= hi
                or not math.isfinite(number)):
            raise PatchError('incompatible_recipe', 422)
    return value


def _body(keys):
    if not request.is_json:
        raise PatchError('invalid_patch', 400)
    if request.content_length is not None and request.content_length > BODY_LIMIT:
        raise PatchError('invalid_patch', 400)
    raw = request.stream.read(BODY_LIMIT + 1)
    if len(raw) > BODY_LIMIT:
        raise PatchError('invalid_patch', 400)
    try:
        data = strict_json(raw)
        if type(data) is not dict or set(data) != keys:
            raise ValueError()
        if 'requestId' in keys:
            _uuid(data['requestId'])
        if 'name' in keys:
            if not isinstance(data['name'], str):
                raise ValueError()
            data['name'] = data['name'].strip()
            if (not 1 <= len(data['name']) <= 80
                    or any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
                           for char in data['name'])):
                raise ValueError()
        if 'baseVersion' in keys and (type(data['baseVersion']) is not int
                                       or not 1 <= data['baseVersion'] <= VERSION_LIMIT):
            raise ValueError()
    except (ValueError, GenerationError):
        raise PatchError('invalid_patch', 400) from None
    if 'recipe' in keys:
        validate_recipe(data['recipe'])
    return data


def _schema(conn):
    found = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'noise_lab_%'")}
    if 'noise_lab_store_meta' in found:
        rows = conn.execute('SELECT id, schema_version FROM noise_lab_store_meta').fetchall()
        if (len(rows) != 1 or rows[0]['id'] != 1 or rows[0]['schema_version'] != STORE_VERSION
                or not TABLES.issubset(found)):
            raise PatchError('storage_unavailable', 503)
        return
    if found:
        # An unrecognized prior/future schema needs an explicit migration.
        raise PatchError('storage_unavailable', 503)
    statements = [
        '''CREATE TABLE noise_lab_store_meta (
            id INTEGER PRIMARY KEY CHECK (id=1), schema_version INTEGER NOT NULL)''',
        '''CREATE TABLE noise_lab_patches (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
            name TEXT NOT NULL, head_version INTEGER NOT NULL,
            created TEXT NOT NULL, updated TEXT NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE)''',
        '''CREATE INDEX noise_lab_patches_owner ON noise_lab_patches(owner_id, updated)''',
        '''CREATE TABLE noise_lab_patch_versions (
            patch_id TEXT NOT NULL, version INTEGER NOT NULL,
            name TEXT NOT NULL, created TEXT NOT NULL, recipe_json TEXT NOT NULL,
            PRIMARY KEY (patch_id, version),
            FOREIGN KEY (patch_id) REFERENCES noise_lab_patches(id) ON DELETE CASCADE)''',
        '''CREATE TABLE noise_lab_patch_requests (
            owner_id TEXT NOT NULL, request_id TEXT NOT NULL,
            operation TEXT NOT NULL, fingerprint TEXT NOT NULL,
            patch_id TEXT NOT NULL, version INTEGER NOT NULL,
            PRIMARY KEY (owner_id, request_id),
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE)''',
    ]
    for statement in statements:
        conn.execute(statement)
    conn.execute('INSERT INTO noise_lab_store_meta VALUES (1, ?)', (STORE_VERSION,))


@contextmanager
def _store():
    if not storage_ready():
        raise PatchError('storage_unavailable', 503)
    with host_db.get_db() as conn:
        # Serializes quota checks, version comparison, idempotency and inserts.
        # Individual DDL statements preserve rollback; executescript would commit.
        conn.execute('BEGIN IMMEDIATE')
        _schema(conn)
        yield conn


def _owned(conn, patch_id):
    row = conn.execute('SELECT * FROM noise_lab_patches WHERE id=? AND owner_id=?',
                       (patch_id, g.noise_lab_account)).fetchone()
    if row is None:
        raise PatchError('not_found', 404)
    return row


def _summary(row):
    return {'id': row['id'], 'name': row['name'],
            'headVersion': row['head_version'], 'updated': row['updated']}


def _full(conn, row, through=None):
    through = row['head_version'] if through is None else through
    versions = []
    for stored in conn.execute('''SELECT version, name, created, recipe_json
            FROM noise_lab_patch_versions WHERE patch_id=? AND version<=? ORDER BY version''',
            (row['id'], through)):
        entry = {'version': stored['version'], 'name': stored['name'], 'created': stored['created']}
        try:
            entry['recipe'] = strict_json(stored['recipe_json'])
            # JSON exponent overflow can decode to infinity without using a
            # named NaN/Infinity token. Export that source verbatim as text.
            json.dumps(entry['recipe'], allow_nan=False)
        except (GenerationError, ValueError, TypeError, RecursionError):
            # Keep unreadable data exportable without attempting to run or repair it.
            entry.update(recipe=None, recipeRaw=stored['recipe_json'])
        try:
            validate_recipe(entry['recipe'])
            entry['compatible'] = True
        except PatchError:
            entry['compatible'] = False
        versions.append(entry)
    if not versions or versions[-1]['version'] != through:
        raise PatchError('storage_unavailable', 503)
    return {'id': row['id'], 'name': versions[-1]['name'], 'headVersion': through,
            'updated': versions[-1]['created'], 'versions': versions}


def _fingerprint(operation, data):
    content = {key: value for key, value in data.items() if key != 'requestId'}
    canonical = json.dumps([operation, content], sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _replay(conn, operation, data):
    prior = conn.execute('''SELECT operation, fingerprint, patch_id, version
        FROM noise_lab_patch_requests WHERE owner_id=? AND request_id=?''',
        (g.noise_lab_account, data['requestId'])).fetchone()
    if prior is None:
        return None
    if prior['operation'] != operation or prior['fingerprint'] != _fingerprint(operation, data):
        raise PatchError('request_conflict', 409)
    row = conn.execute('SELECT * FROM noise_lab_patches WHERE id=? AND owner_id=?',
                       (prior['patch_id'], g.noise_lab_account)).fetchone()
    if row is None:
        raise PatchError('request_retired', 410)
    return _full(conn, row, through=prior['version'])


def _request_room(conn):
    count = conn.execute('SELECT COUNT(*) FROM noise_lab_patch_requests WHERE owner_id=?',
                         (g.noise_lab_account,)).fetchone()[0]
    if count >= REQUEST_LIMIT:
        raise PatchError('request_limit', 429)


def _record_request(conn, operation, data, patch_id, version):
    conn.execute('INSERT INTO noise_lab_patch_requests VALUES (?, ?, ?, ?, ?, ?)',
                 (g.noise_lab_account, data['requestId'], operation,
                  _fingerprint(operation, data), patch_id, version))


def register_patch_routes(bp, check_csrf):
    """Host must set g.noise_lab_account before these authenticated routes run."""
    def endpoint(mutating=False):
        def decorate(function):
            @wraps(function)
            def wrapped(*args, **kwargs):
                try:
                    if not getattr(g, 'noise_lab_account', None):
                        raise PatchError('not_found', 404)
                    if 'patch_id' in kwargs:
                        try:
                            _uuid(kwargs['patch_id'])
                        except ValueError:
                            raise PatchError('not_found', 404) from None
                    if mutating:
                        rejected = check_csrf()
                        if rejected is not None:
                            return rejected
                        if (request.headers.get('Sec-Fetch-Site') == 'cross-site'
                                or ('Origin' in request.headers and
                                    request.headers['Origin'] != request.host_url.rstrip('/'))):
                            return jsonify(error='session_check'), 403
                    return function(*args, **kwargs)
                except PatchError as error:
                    return jsonify(error=error.code), error.status
                except (sqlite3.Error, OSError, RuntimeError):
                    # Never expose account names, recipe text, paths or SQL errors.
                    return jsonify(error='storage_unavailable'), 503
            return wrapped
        return decorate

    @bp.get('/api/patches')
    @endpoint()
    def list_patches():
        with _store() as conn:
            rows = conn.execute('''SELECT * FROM noise_lab_patches WHERE owner_id=?
                ORDER BY updated DESC, id''', (g.noise_lab_account,)).fetchall()
            return jsonify(patches=[_summary(row) for row in rows])

    @bp.get('/api/patches/<patch_id>')
    @endpoint()
    def read_patch(patch_id):
        with _store() as conn:
            return jsonify(patch=_full(conn, _owned(conn, patch_id)))

    @bp.get('/api/patches/<patch_id>/export')
    @endpoint()
    def export_patch(patch_id):
        with _store() as conn:
            return jsonify(archiveVersion=1, patch=_full(conn, _owned(conn, patch_id)))

    @bp.post('/api/patches')
    @endpoint(mutating=True)
    def create_patch():
        data = _body({'requestId', 'name', 'recipe'})
        with _store() as conn:
            repeated = _replay(conn, 'create', data)
            if repeated is not None:
                return jsonify(patch=repeated), 200
            _request_room(conn)
            if conn.execute('SELECT COUNT(*) FROM noise_lab_patches WHERE owner_id=?',
                            (g.noise_lab_account,)).fetchone()[0] >= PATCH_LIMIT:
                raise PatchError('patch_limit', 429)
            patch_id, now = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT INTO noise_lab_patches VALUES (?, ?, ?, 1, ?, ?)',
                         (patch_id, g.noise_lab_account, data['name'], now, now))
            conn.execute('INSERT INTO noise_lab_patch_versions VALUES (?, 1, ?, ?, ?)',
                         (patch_id, data['name'], now, json.dumps(data['recipe'], allow_nan=False)))
            _record_request(conn, 'create', data, patch_id, 1)
            return jsonify(patch=_full(conn, _owned(conn, patch_id))), 201

    @bp.post('/api/patches/<patch_id>/versions')
    @endpoint(mutating=True)
    def append_version(patch_id):
        data = _body({'requestId', 'baseVersion', 'name', 'recipe'})
        with _store() as conn:
            operation = 'append:' + patch_id
            repeated = _replay(conn, operation, data)
            if repeated is not None:
                return jsonify(patch=repeated), 200
            row = _owned(conn, patch_id)
            if row['head_version'] != data['baseVersion']:
                raise PatchError('version_conflict', 409)
            if row['head_version'] >= VERSION_LIMIT:
                raise PatchError('version_limit', 429)
            _request_room(conn)
            version, now = row['head_version'] + 1, datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT INTO noise_lab_patch_versions VALUES (?, ?, ?, ?, ?)',
                         (patch_id, version, data['name'], now, json.dumps(data['recipe'], allow_nan=False)))
            conn.execute('UPDATE noise_lab_patches SET name=?, head_version=?, updated=? WHERE id=? AND owner_id=?',
                         (data['name'], version, now, patch_id, g.noise_lab_account))
            _record_request(conn, operation, data, patch_id, version)
            return jsonify(patch=_full(conn, _owned(conn, patch_id))), 201

    @bp.delete('/api/patches/<patch_id>')
    @endpoint(mutating=True)
    def delete_patch(patch_id):
        data = _body({'baseVersion'})
        with _store() as conn:
            row = _owned(conn, patch_id)
            if row['head_version'] != data['baseVersion']:
                raise PatchError('version_conflict', 409)
            conn.execute('DELETE FROM noise_lab_patches WHERE id=? AND owner_id=?',
                         (patch_id, g.noise_lab_account))
            # Content-free request tombstones survive until account deletion;
            # deleting them here would allow a lost-response retry to resurrect data.
            return jsonify(deleted=True)
