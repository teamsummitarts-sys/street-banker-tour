"""Optional ElevenLabs adapter. Fixed endpoints, bounded bytes, zero retries.

Contract verified 2026-09-05 against official Music compose, inpainting and
stem-separation documentation. Generation creates one new audition section.
It does not upload neighboring clips or promise contextual regeneration.
"""
import io
import json
import secrets
import stat
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import PurePosixPath

from .validation import SongError, safe_name, wav_info

MODEL = 'music_v2'
COMPOSE_URL = 'https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128'
STEMS_URL = 'https://api.elevenlabs.io/v1/music/stem-separation?output_format=mp3_44100_128'
MAX_GENERATION_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_STEM_BYTES = 8 * 1024 * 1024
MAX_STEMS_TOTAL_BYTES = 48 * 1024 * 1024
TIMEOUT_SECONDS = 180


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SongError('provider_redirect', 'The music service could not complete this request.', 502)


def _request(url, key, data, content_type, byte_limit):
    if url not in (COMPOSE_URL, STEMS_URL):
        raise SongError('provider_endpoint', 'The music service is unavailable.', 503)
    request = urllib.request.Request(url, data=data, method='POST', headers={
        'xi-api-key': key, 'Content-Type': content_type, 'Accept': '*/*'})
    opener = urllib.request.build_opener(NoRedirect())
    started = time.monotonic()
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise SongError('provider_failed', 'The music request failed. It has not been retried.', 502)
            declared = response.headers.get('Content-Length')
            if declared is not None and (not declared.isdigit() or int(declared) > byte_limit):
                raise SongError('provider_response', 'The music service returned an unsupported result.', 502)
            chunks, total = [], 0
            while True:
                # read1 limits each operation to one underlying socket read so a
                # trickling response cannot defer the wall-clock bound forever.
                chunk = response.read1(min(65536, byte_limit + 1 - total))
                if time.monotonic() - started > TIMEOUT_SECONDS:
                    raise TimeoutError()
                if not chunk:
                    break
                total += len(chunk)
                if total > byte_limit:
                    raise SongError('provider_response', 'The music service returned an unsupported result.', 502)
                chunks.append(chunk)
            return b''.join(chunks)
    except SongError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Never return exception text: upstream bodies can contain prompts/keys.
        raise SongError('provider_failed', 'The music request failed. It has not been retried.', 502) from None


def audio_result(data, name):
    if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
        duration = wav_info(data)
        return {'name': safe_name(name), 'mime': 'audio/wav', 'duration': duration, 'data': data}
    if len(data) >= 128 and (data[:3] == b'ID3' or (data[0] == 0xff and data[1] & 0xe0 == 0xe0)):
        return {'name': safe_name(name), 'mime': 'audio/mpeg', 'duration': None, 'data': data}
    raise SongError('provider_response', 'The music service did not return supported audio.', 502)


def composition_payload(snapshot):
    section = snapshot['section']
    styles = [snapshot['prompt'], section['direction'], f"Target tempo {snapshot['tempo']} BPM",
              f"Target key {snapshot['key']}" if snapshot['key'] else '']
    return {'model_id': MODEL, 'store_for_inpainting': False,
            'composition_plan': {'chunks': [{
                'text': f"[{section['name']}]\n{section['lyrics']}",
                'duration_ms': round(section['duration'] * 1000),
                'positive_styles': [s for s in styles if s],
                'negative_styles': [], 'context_adherence': 'high'}]}}


def generate(snapshot, key):
    data = _request(COMPOSE_URL, key, json.dumps(composition_payload(snapshot)).encode(),
                    'application/json', MAX_GENERATION_BYTES)
    return [audio_result(data, snapshot['section']['name'] + ' — new take.mp3')]


def unpack_stems(data):
    """Read member bytes only; archive paths never become filesystem paths."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise SongError('provider_response', 'The stem archive is too large.', 502)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if not 2 <= len(members) <= 6:
                raise ValueError()
            total, seen, results = 0, set(), []
            for entry in members:
                path = PurePosixPath(entry.filename)
                mode = entry.external_attr >> 16
                if (entry.is_dir() or path.is_absolute() or '..' in path.parts
                        or '\\' in entry.filename or '\x00' in entry.filename or ':' in entry.filename
                        or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not stat.S_ISREG(mode))
                        or entry.flag_bits & 1 or entry.filename.casefold() in seen
                        or path.suffix.lower() not in ('.mp3', '.wav')
                        or not 1 <= entry.file_size <= MAX_STEM_BYTES
                        or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError()
                total += entry.file_size
                if total > MAX_STEMS_TOTAL_BYTES:
                    raise ValueError()
                seen.add(entry.filename.casefold())
                with archive.open(entry) as source:
                    audio = source.read(MAX_STEM_BYTES + 1)
                if len(audio) != entry.file_size:
                    raise ValueError()
                results.append(audio_result(audio, path.name))
            return results
    except SongError:
        raise
    except (zipfile.BadZipFile, ValueError, OSError, RuntimeError, NotImplementedError):
        raise SongError('provider_response', 'The music service returned an unsupported stem archive.', 502) from None


def separate(asset, data, key):
    boundary = 'songbuilder' + secrets.token_hex(16)
    extension = '.wav' if asset['mime'] == 'audio/wav' else '.mp3'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="stem_variation_id"\r\n\r\n'
            f'six_stems_v1\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="input{extension}"\r\n'
            f'Content-Type: {asset["mime"]}\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
    result = _request(STEMS_URL, key, body, f'multipart/form-data; boundary={boundary}', MAX_ARCHIVE_BYTES)
    return unpack_stems(result)
