"""Local-only preview: python3 -m tests.song_builder_preview (or run via runpy).

Synthetic identity and temporary storage. Never use as a production entry point.
"""
import secrets
import tempfile

from flask import Flask
from song_builder import init


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='song-builder-preview-') as directory:
        app = Flask(__name__)
        app.config.update(SECRET_KEY=secrets.token_hex(32), SONG_BUILDER_ENABLED=True,
                          SONG_BUILDER_MUSIC_ENABLED=False, ELEVENLABS_API_KEY='')
        init(app, lambda: {'id': 'synthetic-preview'}, data_dir=directory)
        app.run(host='127.0.0.1', port=5057, debug=False, use_reloader=False)
