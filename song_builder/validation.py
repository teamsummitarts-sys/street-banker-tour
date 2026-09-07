"""Strict, provider-independent project schema and audio input validation."""
import copy
import io
import json
import math
import re
import uuid
import wave

MAX_UPLOAD_BYTES = 32 * 1024 * 1024
MAX_JSON_BYTES = 256 * 1024
MAX_STORAGE_BYTES = 512 * 1024 * 1024
MAX_ASSETS = 256
MAX_PROJECTS = 100


class SongError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def invalid(message='Check the project fields and try again.'):
    raise SongError('invalid_input', message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('nonfinite number')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError):
        invalid('Send a valid JSON object.')


def exact(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        invalid()


def identifier(value):
    if not isinstance(value, str):
        invalid()
    try:
        if str(uuid.UUID(value)) != value:
            invalid()
    except ValueError:
        invalid()
    return value


def string(value, low, high):
    if not isinstance(value, str) or not low <= len(value) <= high or (low and not value.strip()):
        invalid()
    # Lyrics may contain newlines; NUL and other non-text controls may not.
    if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        invalid()
    return value


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        invalid()
    return value


def boolean(value):
    if type(value) is not bool:
        invalid()


def revision(value):
    if type(value) is not int or not 1 <= value <= 2**53 - 1:
        invalid()
    return value


def project(value):
    exact(value, 'schemaVersion id title tempo key sections tracks clips')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
        invalid()
    identifier(value['id'])
    string(value['title'], 1, 120)
    string(value['key'], 0, 24)
    number(value['tempo'], 40, 240)
    for name, low, high in [('sections', 1, 30), ('tracks', 0, 12), ('clips', 0, 256)]:
        if type(value[name]) is not list or not low <= len(value[name]) <= high:
            invalid()
    sections, tracks, clips, asset_ids = {}, {}, set(), set()
    for s in value['sections']:
        exact(s, 'id name duration lyrics direction locked')
        identifier(s['id'])
        if s['id'] in sections:
            invalid()
        string(s['name'], 1, 60)
        string(s['lyrics'], 0, 3000)
        string(s['direction'], 0, 1000)
        number(s['duration'], 3, 120)
        boolean(s['locked'])
        sections[s['id']] = s
    if sum(s['duration'] for s in sections.values()) > 600:
        invalid('Keep the song under ten minutes.')
    for t in value['tracks']:
        exact(t, 'id name gainDb pan muted solo')
        identifier(t['id'])
        if t['id'] in tracks:
            invalid()
        string(t['name'], 1, 60)
        number(t['gainDb'], -60, 6)
        number(t['pan'], -1, 1)
        boolean(t['muted'])
        boolean(t['solo'])
        tracks[t['id']] = t
    for c in value['clips']:
        if type(c) is not dict:
            invalid()
        exact(c, 'id trackId sectionId assetId offset sourceOffset duration loop gainDb' +
              ''.join(' ' + key for key in ('fadeIn', 'fadeOut') if key in c))
        for key in ('fadeIn', 'fadeOut'):
            if key in c:
                number(c[key], 0, 120)
        for field in ('id', 'trackId', 'sectionId', 'assetId'):
            identifier(c[field])
        if c['id'] in clips or c['trackId'] not in tracks or c['sectionId'] not in sections:
            invalid()
        number(c['offset'], 0, 600)
        number(c['sourceOffset'], 0, 600)
        number(c['duration'], 0.000001, 600)
        number(c['gainDb'], -60, 6)
        boolean(c['loop'])
        if c['offset'] + c['duration'] > sections[c['sectionId']]['duration'] + .001:
            invalid('A clip extends beyond its section.')
        clips.add(c['id'])
        asset_ids.add(c['assetId'])
    if len(asset_ids) > 128:
        invalid()
    return copy.deepcopy(value)


def enforce_locks(old, new):
    sections = {s['id']: s for s in new['sections']}
    for old_section in old['sections']:
        if not old_section['locked']:
            continue
        newer = sections.get(old_section['id'])
        old_clips = sorted((c for c in old['clips'] if c['sectionId'] == old_section['id']), key=lambda c: c['id'])
        new_clips = sorted((c for c in new['clips'] if c['sectionId'] == old_section['id']), key=lambda c: c['id'])
        if (newer is None or {k: v for k, v in old_section.items() if k != 'locked'} !=
                {k: v for k, v in newer.items() if k != 'locked'} or old_clips != new_clips):
            raise SongError('section_locked', 'Unlock and save this section before changing its contents.', 409)


def wav_info(data):
    if not isinstance(data, bytes) or not 44 <= len(data) <= MAX_UPLOAD_BYTES:
        invalid('Upload a PCM WAV file no larger than 32 MiB.')
    try:
        with wave.open(io.BytesIO(data), 'rb') as audio:
            frames, rate = audio.getnframes(), audio.getframerate()
            if (audio.getcomptype() != 'NONE' or audio.getnchannels() not in (1, 2)
                    or audio.getsampwidth() not in (1, 2, 3, 4) or not 8000 <= rate <= 96000
                    or not 0 < frames / rate <= 600):
                invalid('Use a mono or stereo PCM WAV, up to ten minutes.')
            expected = frames * audio.getnchannels() * audio.getsampwidth()
            if expected > MAX_UPLOAD_BYTES or len(audio.readframes(frames)) != expected:
                invalid('This WAV file is incomplete.')
            return frames / rate
    except (wave.Error, EOFError, ValueError, OverflowError):
        invalid('This file is not a supported PCM WAV.')


def safe_name(value, fallback='Audio.wav'):
    value = re.split(r'[/\\]', str(value or ''))[-1]
    value = ''.join(c for c in value if ord(c) >= 32 and ord(c) != 127).strip()[:120]
    return value or fallback
