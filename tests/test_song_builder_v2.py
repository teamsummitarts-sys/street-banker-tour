"""Real V2 authentication and module integration, isolated from live data."""
import os
from pathlib import Path
import subprocess
import sys


def test_song_builder_actual_v2_host(tmp_path):
    env = {'PATH': os.environ.get('PATH', ''), 'APP_ENV': 'development',
           'DATABASE_PATH': str(tmp_path / 'host.db'), 'SONG_BUILDER_ENABLED': '1',
           'SONG_BUILDER_MUSIC_ENABLED': '0', 'NOISE_LAB_ENABLED': '1',
           'SONG_BUILDER_DATA_DIR': str(tmp_path / 'songs')}
    result = subprocess.run([sys.executable, '-c', '''
import app
client = app.app.test_client()
assert client.get('/song-builder/').status_code == 302
user = app.store.get_user_by_email('demo@streetbanker.io')
with client.session_transaction() as session:
    session['user_id'] = user['id']
page = client.get('/song-builder/')
assert page.status_code == 200
assert b'/song-builder/assets/ui/controller.mjs' in page.data
assert b'Song Builder' in client.get('/noise-lab/').data
caps = client.get('/song-builder/api/capabilities')
assert caps.status_code == 200
assert caps.json['generation']['configured'] is False
assert client.get('/song-builder/api/projects').json == {'projects': []}
assert client.get('/song-builder/assets/core/audio.mjs').status_code == 200
app.app.config['SONG_BUILDER_ENABLED'] = False
assert client.get('/song-builder/').status_code == 404
'''], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True,
        text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
