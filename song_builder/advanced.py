"""Persistent non-AI workflow metadata for The Room.

Groups, section scenes, takes/comping snapshots and clip protection live beside
portable song projects without changing the provider-independent audio schema.
"""
import json
import time
import uuid

from flask import g, jsonify, request

from . import validation as v

MAX_METADATA_BYTES = 512 * 1024
MAX_GROUPS = 12
MAX_SCENES = 48
MAX_TAKES = 96
PROTECTION_MODES = {'position', 'never'}


def _uuid(value):
    v.identifier(value)
    return value


def _small_string(value, maximum=80):
    return v.string(value, 1, maximum)


def _number(value, low, high):
    v.number(value, low, high)
    return value


def _boolean(value):
    v.boolean(value)
    return value


def _snapshot_clip(value):
    if type(value) is not dict:
        v.invalid('A saved take contains an invalid clip.')
    allowed = {'id', 'trackId', 'sectionId', 'assetId', 'offset', 'sourceOffset',
               'duration', 'loop', 'gainDb', 'fadeIn', 'fadeOut'}
    required = {'id', 'trackId', 'sectionId', 'assetId', 'offset', 'sourceOffset',
                'duration', 'loop', 'gainDb'}
    if set(value) - allowed or not required.issubset(value):
        v.invalid('A saved take contains an invalid clip.')
    for key in ('id', 'trackId', 'sectionId', 'assetId'):
        _uuid(value[key])
    _number(value['offset'], 0, 600)
    _number(value['sourceOffset'], 0, 600)
    _number(value['duration'], 0.000001, 600)
    _number(value['gainDb'], -60, 6)
    _boolean(value['loop'])
    for key in ('fadeIn', 'fadeOut'):
        if key in value:
            _number(value[key], 0, 120)
    return dict(value)


def validate_metadata(value):
    if type(value) is not dict or set(value) != {'version', 'groups', 'scenes', 'takes', 'protections'}:
        v.invalid('The Room workflow data is invalid.')
    if value['version'] != 1:
        v.invalid('This Room workflow version is not supported.')
    for key, limit in (('groups', MAX_GROUPS), ('scenes', MAX_SCENES), ('takes', MAX_TAKES)):
        if type(value[key]) is not list or len(value[key]) > limit:
            v.invalid('The Room workflow has too many saved items.')
    if type(value['protections']) is not list or len(value['protections']) > 256:
        v.invalid('The Room workflow has too many protected clips.')

    ids = set()
    groups = []
    for item in value['groups']:
        if type(item) is not dict or set(item) != {'id', 'name', 'trackIds', 'gainDb', 'muted', 'solo'}:
            v.invalid('A group bus is invalid.')
        _uuid(item['id'])
        if item['id'] in ids:
            v.invalid('Workflow item IDs must be unique.')
        ids.add(item['id'])
        _small_string(item['name'], 60)
        if type(item['trackIds']) is not list or len(item['trackIds']) > 12 or len(set(item['trackIds'])) != len(item['trackIds']):
            v.invalid('A group bus has invalid members.')
        for track_id in item['trackIds']:
            _uuid(track_id)
        _number(item['gainDb'], -24, 6)
        _boolean(item['muted'])
        _boolean(item['solo'])
        groups.append({**item, 'trackIds': list(item['trackIds'])})

    scenes = []
    for item in value['scenes']:
        if type(item) is not dict or set(item) != {'id', 'sectionId', 'name', 'clips'}:
            v.invalid('A section scene is invalid.')
        _uuid(item['id']); _uuid(item['sectionId'])
        if item['id'] in ids:
            v.invalid('Workflow item IDs must be unique.')
        ids.add(item['id']); _small_string(item['name'], 60)
        if type(item['clips']) is not list or len(item['clips']) > 256:
            v.invalid('A section scene has too many clips.')
        clips = [_snapshot_clip(clip) for clip in item['clips']]
        if any(clip['sectionId'] != item['sectionId'] for clip in clips):
            v.invalid('A section scene contains audio from another section.')
        scenes.append({**item, 'clips': clips})

    takes = []
    for item in value['takes']:
        if type(item) is not dict or set(item) != {'id', 'sectionId', 'trackId', 'name', 'clips'}:
            v.invalid('A saved take is invalid.')
        _uuid(item['id']); _uuid(item['sectionId']); _uuid(item['trackId'])
        if item['id'] in ids:
            v.invalid('Workflow item IDs must be unique.')
        ids.add(item['id']); _small_string(item['name'], 60)
        if type(item['clips']) is not list or len(item['clips']) > 64:
            v.invalid('A saved take has too many clips.')
        clips = [_snapshot_clip(clip) for clip in item['clips']]
        if any(clip['sectionId'] != item['sectionId'] or clip['trackId'] != item['trackId'] for clip in clips):
            v.invalid('A saved take contains audio from another lane.')
        takes.append({**item, 'clips': clips})

    protections = []
    protected = set()
    for item in value['protections']:
        if type(item) is not dict or set(item) != {'clipId', 'mode'}:
            v.invalid('A clip protection rule is invalid.')
        _uuid(item['clipId'])
        if item['clipId'] in protected or item['mode'] not in PROTECTION_MODES:
            v.invalid('A clip protection rule is invalid.')
        protected.add(item['clipId']); protections.append(dict(item))

    result = {'version': 1, 'groups': groups, 'scenes': scenes, 'takes': takes,
              'protections': protections}
    if len(json.dumps(result, separators=(',', ':')).encode()) > MAX_METADATA_BYTES:
        v.invalid('The Room workflow data is too large.')
    return result


def default_metadata():
    return {'version': 1, 'groups': [], 'scenes': [], 'takes': [], 'protections': []}


class WorkflowStore:
    def __init__(self, service):
        self.service = service
        with service.store.connection(write=True) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS room_workflow (
                owner TEXT NOT NULL,
                project_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(owner, project_id),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )''')

    def get(self, owner, project_id):
        self.service.store.get_project(owner, project_id)
        with self.service.store.connection() as db:
            row = db.execute('SELECT revision,data FROM room_workflow WHERE owner=? AND project_id=?',
                             (owner, project_id)).fetchone()
        if row is None:
            return {'metadata': default_metadata(), 'revision': 0}
        return {'metadata': validate_metadata(json.loads(row['data'])), 'revision': row['revision']}

    def save(self, owner, project_id, metadata, expected):
        self.service.store.get_project(owner, project_id)
        metadata = validate_metadata(metadata)
        if type(expected) is not int or expected < 0 or expected > 2**53 - 1:
            v.invalid('The workflow revision is invalid.')
        now = time.time()
        with self.service.store.connection(write=True) as db:
            row = db.execute('SELECT revision FROM room_workflow WHERE owner=? AND project_id=?',
                             (owner, project_id)).fetchone()
            current = row['revision'] if row else 0
            if current != expected:
                raise v.SongError('workflow_conflict', 'These workflow tools changed elsewhere. Reload and try again.', 409)
            revision = current + 1
            db.execute('''INSERT INTO room_workflow(owner,project_id,revision,data,updated_at)
                          VALUES(?,?,?,?,?)
                          ON CONFLICT(owner,project_id) DO UPDATE SET
                          revision=excluded.revision,data=excluded.data,updated_at=excluded.updated_at''',
                       (owner, project_id, revision, json.dumps(metadata), now))
        return {'metadata': metadata, 'revision': revision}


def enforce_clip_protections(metadata, old_project, new_project):
    rules = {item['clipId']: item['mode'] for item in metadata.get('protections', [])}
    if not rules:
        return
    old = {clip['id']: clip for clip in old_project['clips']}
    new = {clip['id']: clip for clip in new_project['clips']}
    for clip_id, mode in rules.items():
        before = old.get(clip_id)
        if before is None:
            continue
        after = new.get(clip_id)
        if after is None:
            raise v.SongError('clip_protected', 'Unlock this clip before removing or replacing it.', 409)
        if mode == 'position':
            keys = ('trackId', 'sectionId', 'offset')
            if any(before[key] != after[key] for key in keys):
                raise v.SongError('clip_protected', 'This clip position is locked. Change its protection before moving it.', 409)
        elif before != after:
            raise v.SongError('clip_protected', 'This clip is marked Never alter. Change its protection before editing it.', 409)


def register(bp, service, body):
    """Register workflow endpoints and enforce protections on normal project saves."""
    workflow = WorkflowStore(service)
    # Enforce inside the project save transaction, including merged live edits.
    service.store.workflow_protections = True

    @bp.get('/api/workflow')
    def get_workflow():
        project_id = request.args.get('projectId')
        v.identifier(project_id)
        return jsonify(workflow.get(g.song_builder_account, project_id))

    @bp.put('/api/workflow/<project_id>')
    def save_workflow(project_id):
        v.identifier(project_id)
        payload = body('metadata expectedRevision')
        return jsonify(workflow.save(g.song_builder_account, project_id,
                                     payload['metadata'], payload['expectedRevision']))

    return workflow
