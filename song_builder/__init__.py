"""Portable Song Builder host adapter. Register with an existing user resolver.

No host tables, provider SDK, OpenAI calls or public uploads are used.
"""
import json
import os
from pathlib import Path
import secrets
import threading

from flask import Blueprint, g, jsonify, render_template, request, send_file, session, url_for
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from . import provider, validation as v
from .store import (MAX_CONCURRENT_JOBS, MAX_DAILY_JOBS, MAX_SERVICE_DAILY_JOBS,
                    Store, iso)


def enabled(value):
    return value is True or (isinstance(value, str) and value.lower() in ('1', 'true'))


class SongBuilder:
    def __init__(self, app, directory):
        self.app, self.directory = app, directory
        self._store = None
        self._store_lock = threading.Lock()

    @property
    def store(self):
        # Default-off registration neither opens nor creates storage.
        with self._store_lock:
            if self._store is None:
                self._store = Store(self.directory)
            return self._store

    def configured(self):
        return enabled(self.app.config.get('SONG_BUILDER_MUSIC_ENABLED')) and bool(
            str(self.app.config.get('ELEVENLABS_API_KEY') or '').strip())

    def start_job(self, job_id):
        if self.app.testing and self.app.config.get('SONG_BUILDER_JOB_AUTOSTART') is False:
            return
        try:
            threading.Thread(target=self.run_job, args=(job_id,), daemon=True,
                             name='song-builder-music').start()
        except RuntimeError:
            self.store.fail_job(job_id, 'The music request could not start. It has not been retried.')

    def run_job(self, job_id):
        row = self.store.claim_job(job_id)
        if row is None:
            return
        try:
            if not self.configured():
                raise v.SongError('provider_unavailable', 'Music generation is currently unavailable.', 503)
            snapshot = json.loads(row['payload_json'])
            source, source_bytes = None, None
            if row['kind'] == 'separate':
                source = self.store.get_asset(row['owner'], snapshot['assetId'])
                with self.store.asset_path(source).open('rb') as audio:
                    source_bytes = audio.read(v.MAX_UPLOAD_BYTES + 1)
                if len(source_bytes) > v.MAX_UPLOAD_BYTES:
                    raise v.SongError('invalid_audio', 'The source audio is too large.')
            test_provider = self.app.config.get('SONG_BUILDER_PROVIDER') if self.app.testing else None
            if test_provider:
                results = test_provider(row['kind'], snapshot, source_bytes)
            elif row['kind'] == 'generate':
                results = provider.generate(snapshot, self.app.config['ELEVENLABS_API_KEY'])
            else:
                results = provider.separate(source, source_bytes, self.app.config['ELEVENLABS_API_KEY'])
            expected = 1 if row['kind'] == 'generate' else 6
            if not isinstance(results, list) or not 1 <= len(results) <= expected:
                raise v.SongError('provider_response', 'The music service returned an unsupported result.', 502)
            if row['kind'] == 'separate' and len(results) < 2:
                raise v.SongError('provider_response', 'The music service returned an unsupported result.', 502)
            validated = []
            for result in results:
                if (type(result) is not dict or not isinstance(result.get('data'), bytes)
                        or len(result['data']) > provider.MAX_GENERATION_BYTES):
                    raise v.SongError('provider_response', 'The music service returned an unsupported result.', 502)
                validated.append(provider.audio_result(result['data'], result.get('name', 'Music take.mp3')))
            self.store.complete_job(row, validated)
        except v.SongError as error:
            self.store.fail_job(row['id'], error.message)
        except Exception:
            self.store.fail_job(row['id'], 'The music request failed. It has not been retried.')


def init(app, current_user, data_dir=None, url_prefix='/song-builder', return_url='/noise-lab/'):
    """Mount one independent module without changing the host's data model."""
    if not callable(current_user):
        raise ValueError('A host authenticated-user resolver is required.')
    if not isinstance(url_prefix, str) or not url_prefix.startswith('/') or url_prefix.startswith('//') or '\\' in url_prefix:
        raise ValueError('Use a local module prefix.')
    if not isinstance(return_url, str) or not return_url.startswith('/') or return_url.startswith('//') or '\\' in return_url:
        raise ValueError('Use a local return URL.')
    for name in ('SONG_BUILDER_ENABLED', 'SONG_BUILDER_MUSIC_ENABLED', 'ELEVENLABS_API_KEY'):
        app.config.setdefault(name, os.environ.get(name, ''))
    directory = data_dir or app.config.get('SONG_BUILDER_DATA_DIR') or os.environ.get('SONG_BUILDER_DATA_DIR') or (Path(app.instance_path) / 'song_builder')
    service = SongBuilder(app, directory)
    bp = Blueprint('song_builder', __name__, url_prefix=url_prefix.rstrip('/'),
                   template_folder='templates', static_folder='static', static_url_path='assets')
    app.extensions['song_builder'] = service

    def csrf():
        saved = session.get('song_builder_csrf')
        if (not isinstance(saved, dict) or saved.get('account') != g.song_builder_account
                or not isinstance(saved.get('token'), str)):
            saved = {'account': g.song_builder_account, 'token': secrets.token_urlsafe(32)}
            session['song_builder_csrf'] = saved
        return saved['token']

    @bp.before_request
    def require_account():
        if not enabled(app.config.get('SONG_BUILDER_ENABLED')):
            raise v.SongError('disabled', 'Song Builder is unavailable.', 404)
        user = current_user()
        identity = user.get('id') if isinstance(user, dict) else None
        if (type(identity) not in (str, int) or not str(identity).strip()
                or len(str(identity)) > 128 or (type(identity) is int and identity <= 0)):
            raise v.SongError('sign_in', 'Sign in to open Song Builder.', 401)
        g.song_builder_account = str(identity)
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            saved = session.get('song_builder_csrf', {})
            token = request.headers.get('X-Song-Builder-CSRF', '')
            if (not isinstance(saved, dict) or saved.get('account') != g.song_builder_account
                    or not isinstance(saved.get('token'), str) or not token.isascii() or len(token) > 128
                    or not secrets.compare_digest(saved['token'], token)
                    or request.headers.get('Sec-Fetch-Site') == 'cross-site'
                    or ('Origin' in request.headers and request.headers['Origin'] != request.host_url.rstrip('/'))):
                raise v.SongError('session_check', 'Reload Song Builder after signing in again.', 403)

    @bp.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Vary'] = 'Cookie'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; script-src 'self'; worker-src 'self'; "
            "style-src 'self'; font-src 'self'; img-src 'self' data:; "
            "media-src 'self' blob:; connect-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'self'")
        response.headers['Permissions-Policy'] = 'microphone=(self), camera=(), geolocation=()'
        return response

    @bp.errorhandler(v.SongError)
    def song_error(error):
        return jsonify(error=error.code, message=error.message), error.status

    @bp.errorhandler(RequestEntityTooLarge)
    def oversized(_):
        return jsonify(error='request_too_large', message='The upload or request is too large.'), 400

    @bp.errorhandler(BadRequest)
    def bad_request(_):
        return jsonify(error='invalid_input', message='This request could not be read.'), 400

    def body(fields):
        if not request.is_json:
            v.invalid('Send a JSON object.')
        if request.content_length is not None and request.content_length > v.MAX_JSON_BYTES:
            v.invalid('The project request is too large.')
        data = request.stream.read(v.MAX_JSON_BYTES + 1)
        if len(data) > v.MAX_JSON_BYTES:
            v.invalid('The project request is too large.')
        value = v.strict_json(data)
        if fields is not None:
            v.exact(value, fields)
        return value

    def asset_json(row):
        return {'id': row['id'], 'name': row['name'], 'mime': row['mime'], 'size': row['size'],
                'duration': row['duration'], 'url': url_for('song_builder.asset_audio', asset_id=row['id'])}

    def project_json(value):
        return {**value, 'assets': [asset_json(row) for row in value['assets']]}

    def job_json(row):
        result = {'id': row['id'], 'requestId': row['request_id'], 'projectId': row['project_id'],
                  'kind': row['kind'], 'status': row['status'], 'createdAt': iso(row['created_at'])}
        if row['section_id']:
            result['sectionId'] = row['section_id']
        if row['kind'] == 'separate':
            result['assetId'] = json.loads(row['payload_json'])['assetId']
        if row['error']:
            result['error'] = row['error']
        assets = [asset_json(service.store.get_asset(row['owner'], asset_id)) for asset_id in json.loads(row['result_ids'])]
        if assets:
            if row['kind'] == 'generate':
                result['asset'] = assets[0]
            else:
                result['assets'] = assets
        return result

    @bp.get('/')
    def index():
        return render_template('song_builder/index.html', builder_base_url=url_for('song_builder.index').rstrip('/'),
                               builder_assets_url=url_for('song_builder.static', filename=''),
                               builder_csrf=csrf(), return_url=return_url)

    @bp.get('/api/capabilities')
    def capabilities():
        return jsonify(schemaVersion=1, generation={'configured': service.configured(),
            'separationConfigured': service.configured(), 'provider': 'elevenlabs', 'model': provider.MODEL,
            'maxSeconds': 120, 'unitPriceUsd': None}, storage=service.store.storage(g.song_builder_account),
            limits={'maxUploadBytes': v.MAX_UPLOAD_BYTES, 'maxProjects': v.MAX_PROJECTS,
                    'maxAssets': v.MAX_ASSETS, 'maxDailyJobs': MAX_DAILY_JOBS,
                    'maxServiceDailyJobs': MAX_SERVICE_DAILY_JOBS, 'maxConcurrentJobs': MAX_CONCURRENT_JOBS})

    @bp.get('/api/projects')
    def list_projects():
        return jsonify(projects=service.store.list_projects(g.song_builder_account))

    @bp.post('/api/projects')
    def create_project():
        value = v.project(body('project')['project'])
        return jsonify(project_json(service.store.save_project(g.song_builder_account, value))), 201

    @bp.get('/api/projects/<project_id>')
    def get_project(project_id):
        v.identifier(project_id)
        return jsonify(project_json(service.store.get_project(g.song_builder_account, project_id)))

    @bp.put('/api/projects/<project_id>')
    def save_project(project_id):
        v.identifier(project_id)
        payload = body('project expectedRevision')
        value, expected = v.project(payload['project']), v.revision(payload['expectedRevision'])
        if value['id'] != project_id:
            v.invalid('The project ID must match this song.')
        return jsonify(project_json(service.store.save_project(g.song_builder_account, value, expected)))

    @bp.delete('/api/projects/<project_id>')
    def delete_project(project_id):
        v.identifier(project_id)
        expected = v.revision(body('expectedRevision')['expectedRevision'])
        service.store.delete_project(g.song_builder_account, project_id, expected)
        return jsonify(deleted=True)

    @bp.post('/api/assets')
    def upload_asset():
        request.max_content_length = v.MAX_UPLOAD_BYTES + 65536
        request.max_form_memory_size = 65536
        request.max_form_parts = 2
        if request.mimetype != 'multipart/form-data':
            v.invalid('Choose a WAV file to upload.')
        if set(request.files) != {'file'} or len(request.files.getlist('file')) != 1 or request.form:
            v.invalid('Send one audio file.')
        upload = request.files['file']
        data = upload.stream.read(v.MAX_UPLOAD_BYTES + 1)
        duration = v.wav_info(data)
        row = service.store.add_asset(g.song_builder_account,
            {'name': v.safe_name(upload.filename), 'mime': 'audio/wav', 'data': data, 'duration': duration})
        return jsonify(asset=asset_json(row)), 201

    @bp.get('/api/assets/<asset_id>/audio')
    def asset_audio(asset_id):
        v.identifier(asset_id)
        row = service.store.get_asset(g.song_builder_account, asset_id)
        path = service.store.asset_path(row)
        if not path.is_file():
            raise v.SongError('audio_missing', 'This audio is temporarily unavailable.', 404)
        return send_file(path, mimetype=row['mime'], conditional=True, etag=False,
                         download_name=row['name'], as_attachment=False, max_age=0)

    @bp.post('/api/jobs')
    def create_job():
        payload = body(None)
        if type(payload) is not dict or payload.get('kind') not in ('generate', 'separate'):
            v.invalid()
        if payload['kind'] == 'generate':
            v.exact(payload, 'requestId kind projectId sectionId expectedRevision prompt')
            v.identifier(payload['sectionId'])
            v.string(payload['prompt'], 1, 1000)
        else:
            v.exact(payload, 'requestId kind projectId assetId expectedRevision')
            v.identifier(payload['assetId'])
        v.identifier(payload['requestId'])
        v.identifier(payload['projectId'])
        v.revision(payload['expectedRevision'])
        row, created = service.store.reserve_job(g.song_builder_account, payload, service.configured())
        if created:
            service.start_job(row['id'])
        return jsonify(job=job_json(row)), 202

    @bp.get('/api/jobs')
    def list_jobs():
        project_id = request.args.get('projectId')
        v.identifier(project_id)
        return jsonify(jobs=[job_json(row) for row in service.store.list_jobs(g.song_builder_account, project_id)])

    @bp.get('/api/jobs/<job_id>')
    def get_job(job_id):
        v.identifier(job_id)
        return jsonify(job=job_json(service.store.get_job(g.song_builder_account, job_id)))

    app.register_blueprint(bp)
    return bp
