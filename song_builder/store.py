"""Private SQLite metadata and UUID-named audio. No host database dependency."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from .provider import composition_payload
from .persistence import on_persistent_disk

from .validation import (MAX_ASSETS, MAX_PROJECTS, MAX_STORAGE_BYTES, SongError,
                         enforce_locks, invalid, safe_name)

LEASE_SECONDS = 600
MAX_DAILY_JOBS = 10
MAX_SERVICE_DAILY_JOBS = 50
MAX_CONCURRENT_JOBS = 2
MAX_JOB_BYTES = {'generate': 8 * 1024 * 1024, 'separate': 48 * 1024 * 1024}


def not_found():
    raise SongError('not_found', 'This item is unavailable.', 404)


def conflict():
    raise SongError('revision_conflict', 'This song changed elsewhere. Keep your work and reload before saving.', 409)


def iso(value):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.audio_dir = self.directory / 'audio'
        self.audio_dir.mkdir(mode=0o700, exist_ok=True)
        self.path = self.directory / 'songs.sqlite3'
        descriptor = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        os.chmod(self.path, 0o600)
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                    data TEXT NOT NULL, revision INTEGER NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS projects_owner ON projects(owner,updated_at);
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
                    mime TEXT NOT NULL, size INTEGER NOT NULL, duration REAL,
                    filename TEXT NOT NULL UNIQUE, created_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS assets_owner ON assets(owner);
                CREATE TABLE IF NOT EXISTS project_assets (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    asset_id TEXT NOT NULL REFERENCES assets(id),
                    PRIMARY KEY(project_id,asset_id));
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                    project_id TEXT NOT NULL, section_id TEXT, kind TEXT NOT NULL,
                    status TEXT NOT NULL, result_ids TEXT NOT NULL DEFAULT '[]',
                    error TEXT, created_at REAL NOT NULL, started_at REAL,
                    finished_at REAL, lease_until REAL NOT NULL,
                    UNIQUE(owner,request_id));
                CREATE INDEX IF NOT EXISTS jobs_owner_date ON jobs(owner,created_at);
                CREATE INDEX IF NOT EXISTS jobs_project ON jobs(owner,project_id,created_at);
            ''')

    @contextlib.contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _owned_project(self, db, owner, project_id):
        result = db.execute('SELECT * FROM projects WHERE id=? AND owner=?', (project_id, owner)).fetchone()
        if result is None:
            not_found()
        return result

    def _assets(self, db, owner, value):
        ids = sorted({c['assetId'] for c in value['clips']})
        assets = []
        for asset_id in ids:
            row = db.execute('SELECT * FROM assets WHERE id=? AND owner=?', (asset_id, owner)).fetchone()
            if row is None:
                not_found()
            assets.append(dict(row))
        lookup = {a['id']: a for a in assets}
        for clip in value['clips']:
            duration = lookup[clip['assetId']]['duration']
            if duration is not None and ((clip['loop'] and clip['sourceOffset'] >= duration)
                    or (not clip['loop'] and clip['sourceOffset'] + clip['duration'] > duration + .001)):
                invalid('A clip extends beyond its source audio.')
        return assets

    def _project_result(self, db, row):
        value = json.loads(row['data'])
        return {'project': value, 'revision': row['revision'], 'assets': self._assets(db, row['owner'], value)}

    def list_projects(self, owner):
        with self.connection() as db:
            rows = db.execute('SELECT id,title,revision,updated_at FROM projects WHERE owner=? ORDER BY updated_at DESC', (owner,)).fetchall()
            return [{'id': r['id'], 'title': r['title'], 'revision': r['revision'], 'updatedAt': iso(r['updated_at'])} for r in rows]

    def get_project(self, owner, project_id):
        with self.connection() as db:
            return self._project_result(db, self._owned_project(db, owner, project_id))

    def save_project(self, owner, value, expected=None, access=None, live_session=None):
        now = time.time()
        with self.connection(write=True) as db:
            if access:
                member=db.execute("SELECT * FROM room_members WHERE id=? AND project_id=? AND role='editor' AND revoked=0 AND expires>?", (access['id'],value['id'],now)).fetchone()
                if member is None or expected is None:
                    raise SongError('room_permission','Your editing invitation is no longer active.',403)
            if expected is None:
                if db.execute('SELECT id FROM projects WHERE id=?', (value['id'],)).fetchone():
                    raise SongError('project_exists', 'Choose a new song ID or open the existing song.', 409)
                if db.execute('SELECT count(*) FROM projects WHERE owner=?', (owner,)).fetchone()[0] >= MAX_PROJECTS:
                    raise SongError('storage_quota', 'The song limit has been reached.', 429)
                self._assets(db, owner, value)
                db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?)',
                           (value['id'], owner, value['title'], json.dumps(value), 1, now, now))
            else:
                row = self._owned_project(db, owner, value['id'])
                if getattr(self,'live_enabled',False):
                    from .live import prepare_save
                    value,expected=prepare_save(db,owner,value,expected,json.loads(row['data']),row['revision'],access,live_session)
                elif row['revision'] != expected:
                    conflict()
                if getattr(self,'workflow_protections',False):
                    from .advanced import enforce_clip_protections
                    metadata=db.execute('SELECT data FROM room_workflow WHERE owner=? AND project_id=?',(owner,value['id'])).fetchone()
                    if metadata: enforce_clip_protections(json.loads(metadata['data']),json.loads(row['data']),value)
                if access:
                    allowed={c['assetId'] for c in json.loads(row['data'])['clips']}
                    allowed.update(r[0] for r in db.execute('SELECT asset_id FROM room_guest_uploads WHERE member_id=?',(access['id'],)))
                    if not {c['assetId'] for c in value['clips']}.issubset(allowed):
                        raise SongError('room_permission','Only this project’s audio and your uploads may be used.',403)
                    old_sections=json.loads(row['data'])['sections']
                    new_sections={s['id']:s for s in value['sections']}
                    if any(s['locked'] and not new_sections.get(s['id'],{}).get('locked') for s in old_sections):
                        raise SongError('room_permission','Only the owner can unlock approved sections.',403)
                enforce_locks(json.loads(row['data']), value)
                self._assets(db, owner, value)
                db.execute('UPDATE projects SET title=?,data=?,revision=revision+1,updated_at=? WHERE id=? AND owner=?',
                           (value['title'], json.dumps(value), now, value['id'], owner))
                db.execute('DELETE FROM project_assets WHERE project_id=?', (value['id'],))
            for asset_id in sorted({c['assetId'] for c in value['clips']}):
                db.execute('INSERT INTO project_assets VALUES(?,?)', (value['id'], asset_id))
            if getattr(self,'live_enabled',False):
                from .live import snapshot
                snapshot(db,value,1 if expected is None else expected+1)
            if access:
                db.execute('INSERT INTO room_contributions(project_id,member_id,revision,created) VALUES(?,?,?,?)',(value['id'],access['id'],expected+1,now))
            return self._project_result(db, self._owned_project(db, owner, value['id']))

    def delete_project(self, owner, project_id, expected):
        with self.connection(write=True) as db:
            row = self._owned_project(db, owner, project_id)
            if row['revision'] != expected:
                conflict()
            if db.execute("SELECT id FROM jobs WHERE owner=? AND project_id=? AND status IN ('queued','running')", (owner, project_id)).fetchone():
                raise SongError('job_active', 'Wait for this song’s music request to finish before deleting it.', 409)
            db.execute('DELETE FROM projects WHERE id=? AND owner=?', (project_id, owner))
            # Audio is retained deliberately: other projects and saved audition
            # takes can share it. Quota remains accurate; no cross-project loss.

    def storage(self, owner):
        with self.connection() as db:
            count, size = db.execute('SELECT count(*),coalesce(sum(size),0) FROM assets WHERE owner=?', (owner,)).fetchone()
            return {'durable': on_persistent_disk(self.directory), 'usedBytes': size, 'maxBytes': MAX_STORAGE_BYTES, 'assetCount': count}

    def _quota(self, db, owner, size, count=1):
        current_count, current_size = db.execute('SELECT count(*),coalesce(sum(size),0) FROM assets WHERE owner=?', (owner,)).fetchone()
        if current_count + count > MAX_ASSETS or current_size + size > MAX_STORAGE_BYTES:
            raise SongError('storage_quota', 'Private audio storage is full. Export a backup before removing unused audio.', 429)

    def _write_audio(self, data, asset_id):
        path = self.audio_dir / (asset_id + '.audio')
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def _insert_asset(self, db, owner, result, asset_id):
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)',
                   (asset_id, owner, safe_name(result['name']), result['mime'], len(result['data']),
                    result['duration'], asset_id + '.audio', time.time()))
        return dict(db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone())

    def add_asset(self, owner, result):
        asset_id, path = str(uuid.uuid4()), None
        try:
            with self.connection(write=True) as db:
                self._quota(db, owner, len(result['data']))
                path = self._write_audio(result['data'], asset_id)
                return self._insert_asset(db, owner, result, asset_id)
        except BaseException:
            if path:
                path.unlink(missing_ok=True)
            raise

    def get_asset(self, owner, asset_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM assets WHERE id=? AND owner=?', (asset_id, owner)).fetchone()
            if row is None:
                not_found()
            return dict(row)

    def asset_path(self, row):
        # Only stored UUIDs determine the path; names are display-only metadata.
        return self.audio_dir / (str(uuid.UUID(row['id'])) + '.audio')

    def _expire(self, db, now):
        db.execute("UPDATE jobs SET status='interrupted',error='This request was interrupted. It will not be retried automatically.',finished_at=? WHERE status IN ('queued','running') AND lease_until<?", (now, now))

    def reserve_job(self, owner, request, available):
        now = time.time()
        signature = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with self.connection(write=True) as db:
            self._expire(db, now)
            existing = db.execute('SELECT * FROM jobs WHERE owner=? AND request_id=?', (owner, request['requestId'])).fetchone()
            if existing:
                if existing['payload_hash'] != signature:
                    raise SongError('idempotency_conflict', 'This request ID was already used for different settings.', 409)
                return dict(existing), False
            row = self._owned_project(db, owner, request['projectId'])
            if row['revision'] != request['expectedRevision']:
                conflict()
            value = json.loads(row['data'])
            snapshot = {'kind': request['kind']}
            section_id = None
            if request['kind'] == 'generate':
                section_id = request['sectionId']
                section = next((s for s in value['sections'] if s['id'] == section_id), None)
                if section is None:
                    not_found()
                if section['locked']:
                    raise SongError('section_locked', 'Unlock and save this section before generating a new take.', 409)
                snapshot.update(section=section, tempo=value['tempo'], key=value['key'], prompt=request['prompt'])
                composition_payload(snapshot)  # Reject invalid input before reserving quota.
            else:
                asset = db.execute('SELECT * FROM assets WHERE id=? AND owner=?', (request['assetId'], owner)).fetchone()
                if asset is None:
                    not_found()
                if asset['duration'] is not None and asset['duration'] > 120:
                    invalid('Stem separation currently accepts audio up to two minutes.')
                snapshot['assetId'] = asset['id']
            if not available:
                raise SongError('provider_unavailable', 'Music generation is not enabled. Record or import audio to keep building.', 503)
            daily = db.execute('SELECT count(*) FROM jobs WHERE owner=? AND created_at>=?', (owner, now - 86400)).fetchone()[0]
            service = db.execute('SELECT count(*) FROM jobs WHERE created_at>=?', (now - 86400,)).fetchone()[0]
            active_owner = db.execute("SELECT count(*) FROM jobs WHERE owner=? AND status IN ('queued','running')", (owner,)).fetchone()[0]
            active = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if daily >= MAX_DAILY_JOBS or service >= MAX_SERVICE_DAILY_JOBS or active_owner or active >= MAX_CONCURRENT_JOBS:
                raise SongError('generation_quota', 'The music request limit has been reached. Please try later.', 429)
            self._quota(db, owner, MAX_JOB_BYTES[request['kind']], 6 if request['kind'] == 'separate' else 1)
            job_id = str(uuid.uuid4())
            db.execute('INSERT INTO jobs(id,owner,request_id,payload_hash,payload_json,project_id,section_id,kind,status,created_at,lease_until) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (job_id, owner, request['requestId'], signature, json.dumps(snapshot), request['projectId'], section_id,
                 request['kind'], 'queued', now, now + LEASE_SECONDS))
            return dict(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()), True

    def claim_job(self, job_id):
        now = time.time()
        with self.connection(write=True) as db:
            self._expire(db, now)
            row = db.execute("SELECT * FROM jobs WHERE id=? AND status='queued'", (job_id,)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='running',started_at=?,lease_until=? WHERE id=? AND status='queued'", (now, now + LEASE_SECONDS, job_id))
            return dict(row)

    def complete_job(self, row, results):
        paths = []
        try:
            with self.connection(write=True) as db:
                self._expire(db, time.time())
                active = db.execute("SELECT id FROM jobs WHERE id=? AND status='running'", (row['id'],)).fetchone()
                if not active:
                    return
                self._quota(db, row['owner'], sum(len(result['data']) for result in results), len(results))
                ids = []
                for result in results:
                    asset_id = str(uuid.uuid4())
                    paths.append(self._write_audio(result['data'], asset_id))
                    self._insert_asset(db, row['owner'], result, asset_id)
                    ids.append(asset_id)
                db.execute("UPDATE jobs SET status='succeeded',result_ids=?,finished_at=? WHERE id=? AND status='running'", (json.dumps(ids), time.time(), row['id']))
        except BaseException:
            for path in paths:
                path.unlink(missing_ok=True)
            raise

    def fail_job(self, job_id, message):
        with self.connection(write=True) as db:
            db.execute("UPDATE jobs SET status='failed',error=?,finished_at=? WHERE id=? AND status IN ('queued','running')", (message, time.time(), job_id))

    def get_job(self, owner, job_id):
        with self.connection(write=True) as db:
            self._expire(db, time.time())
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (job_id, owner)).fetchone()
            if row is None:
                not_found()
            return dict(row)

    def list_jobs(self, owner, project_id):
        with self.connection(write=True) as db:
            self._expire(db, time.time())
            self._owned_project(db, owner, project_id)
            return [dict(r) for r in db.execute('SELECT * FROM jobs WHERE owner=? AND project_id=? ORDER BY created_at DESC LIMIT 50', (owner, project_id)).fetchall()]
