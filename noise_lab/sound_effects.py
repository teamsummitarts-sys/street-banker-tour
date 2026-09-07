"""ElevenLabs text-to-audio. Durable pilot reservations; no audio/prompt storage."""
import json
import sqlite3
import time
import urllib.error
import urllib.request
import uuid

from flask import current_app, g, jsonify, request, Response
import db
from .patches import storage_ready
from .generation import strict_json, GenerationError

URL = 'https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128'
MODEL = 'eleven_text_to_sound_v2'
MAX_BYTES = 2 * 1024 * 1024
MESSAGES = {
    'unconfigured': 'ElevenLabs audio generation is not configured for this account.',
    'provider_access': 'Check the ElevenLabs key and its Sound Effects permission.',
    'provider_quota': 'ElevenLabs rejected this request because of credits or a rate limit. Check your account before retrying.',
    'provider_failed': 'ElevenLabs could not generate this audio. No automatic retry was made.',
    'provider_audio': 'ElevenLabs returned unsupported audio. Your current sound is retained.',
    'duplicate': 'This request was already submitted. It will not be charged again by an automatic retry.',
    'limit': 'The sound-effects test allowance is used up. Contact the V2 owner.',
    'busy': 'A sound generation is still running. Wait before trying again.',
    'cooldown': 'Wait 10 seconds before generating again.',
    'storage': 'The generation allowance could not be checked. No request was sent.',
}

class SoundError(Exception):
    def __init__(self, code, status=502):
        self.code, self.status = code, status
        super().__init__(code)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SoundError('provider_failed')

def availability():
    if current_app.config.get('NOISE_LAB_SFX_ENABLED') not in (True, '1'): return 'disabled'
    if not str(current_app.config.get('ELEVENLABS_API_KEY') or '').strip(): return 'key_missing'
    if not storage_ready(): return 'storage_unavailable'
    return 'ready'

def configured():
    return availability() == 'ready'

def schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS noise_lab_sfx_requests (
        request_id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        started REAL NOT NULL, finished INTEGER NOT NULL DEFAULT 0,
        seconds INTEGER NOT NULL CHECK(seconds IN (5,8,10)))''')

def reserve(owner, request_id, seconds):
    with db.get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        schema(conn)
        if conn.execute('SELECT 1 FROM noise_lab_sfx_requests WHERE request_id=?', (request_id,)).fetchone():
            raise SoundError('duplicate', 409)
        total = conn.execute('SELECT count(*) FROM noise_lab_sfx_requests').fetchone()[0]
        own = conn.execute('SELECT count(*) FROM noise_lab_sfx_requests WHERE owner=?', (owner,)).fetchone()[0]
        if total >= 100 or own >= 20: raise SoundError('limit', 429)
        now = time.time()
        active = conn.execute('SELECT owner FROM noise_lab_sfx_requests WHERE finished=0 AND started>?', (now-180,)).fetchall()
        if len(active) >= 2 or any(row['owner'] == owner for row in active): raise SoundError('busy', 429)
        latest = conn.execute('SELECT max(started) FROM noise_lab_sfx_requests WHERE owner=?', (owner,)).fetchone()[0]
        if latest is not None and now-latest < 10: raise SoundError('cooldown', 429)
        conn.execute('INSERT INTO noise_lab_sfx_requests(request_id,owner,started,seconds) VALUES (?,?,?,?)',
                     (request_id, owner, now, seconds))

def generate_audio(prompt, seconds, loop, key):
    body = json.dumps(dict(text=prompt, duration_seconds=seconds, loop=loop,
                           model_id=MODEL, prompt_influence=0.3)).encode()
    req = urllib.request.Request(URL, data=body, headers={'xi-api-key': key, 'Content-Type': 'application/json'}, method='POST')
    started = time.monotonic()
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=60) as response:
            if response.status != 200: raise SoundError('provider_failed')
            declared = response.headers.get('Content-Length')
            if declared is not None and (not declared.isdigit() or int(declared) > MAX_BYTES):
                raise SoundError('provider_audio')
            chunks, size = [], 0
            while True:
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if time.monotonic() - started > 60: raise TimeoutError()
                if not chunk: break
                size += len(chunk)
                if size > MAX_BYTES: raise SoundError('provider_audio')
                chunks.append(chunk)
            audio = b''.join(chunks)
    except urllib.error.HTTPError as error:
        raise SoundError('provider_access' if error.code in (401,403) else
                         'provider_quota' if error.code == 429 else 'provider_failed') from None
    except (OSError, ValueError):
        raise SoundError('provider_failed') from None
    return validate_audio(audio)

def validate_audio(audio):
    if (not isinstance(audio, bytes) or not 128 <= len(audio) <= MAX_BYTES or
            not (audio[:3] == b'ID3' or (audio[0] == 255 and audio[1] & 224 == 224))):
        raise SoundError('provider_audio')
    return audio

def register(bp, check_csrf):
    @bp.post('/api/sound-effects')
    def sound_effects():
        rejected = check_csrf()
        if rejected is not None: return rejected
        if not request.is_json: return jsonify(error='json_required'), 415
        if request.content_length is not None and request.content_length > 4096:
            return jsonify(error='request_too_large'), 413
        raw = request.stream.read(4097)
        if len(raw) > 4096: return jsonify(error='request_too_large'), 413
        try:
            data = strict_json(raw)
            if type(data) is not dict or set(data) != {'requestId','prompt','seconds','loop'}: raise ValueError()
            if not isinstance(data['requestId'], str) or str(uuid.UUID(data['requestId'])) != data['requestId']: raise ValueError()
            if not isinstance(data['prompt'], str) or not 1 <= len(data['prompt'].strip()) <= 500: raise ValueError()
            if type(data['seconds']) is not int or data['seconds'] not in (5,8,10) or type(data['loop']) is not bool: raise ValueError()
        except (ValueError, TypeError, AttributeError, GenerationError):
            return jsonify(error='invalid_request', message='Enter 1–500 characters and choose a 5, 8 or 10 second sound.'), 400
        reserved = False
        try:
            if not configured(): raise SoundError('unconfigured', 503)
            reserve(g.noise_lab_account, data['requestId'], data['seconds'])
            reserved = True
            provider = current_app.config.get('NOISE_LAB_SFX_PROVIDER') if current_app.testing else None
            audio = (provider(data['prompt'].strip(), data['seconds'], data['loop']) if provider else
                     generate_audio(data['prompt'].strip(), data['seconds'], data['loop'], current_app.config['ELEVENLABS_API_KEY']))
            audio = validate_audio(audio)
            return Response(audio, mimetype='audio/mpeg', headers={'Content-Disposition': 'attachment; filename="noise-lab-generated.mp3"'})
        except SoundError as error:
            return jsonify(error=error.code, message=MESSAGES[error.code]), error.status
        except (sqlite3.Error, RuntimeError, OSError):
            return jsonify(error='storage' if not reserved else 'provider_failed',
                           message=MESSAGES['storage' if not reserved else 'provider_failed']), 503
        except Exception:
            return jsonify(error='provider_failed', message=MESSAGES['provider_failed']), 502
        finally:
            if reserved:
                try:
                    with db.get_db() as conn:
                        conn.execute('UPDATE noise_lab_sfx_requests SET finished=1 WHERE request_id=? AND owner=?',
                                     (data['requestId'], g.noise_lab_account))
                except (sqlite3.Error, RuntimeError, OSError):
                    pass  # Reservation still counts; stale concurrency lease expires after 180s.
