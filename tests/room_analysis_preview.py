"""Isolated preview/test host; synthetic identity and temporary storage only."""
from pathlib import Path
import sys
import tempfile
from flask import Flask
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from song_builder import init

app = Flask(__name__)
app.config.update(SECRET_KEY='local-analysis-preview-only', SONG_BUILDER_ENABLED=True)
_storage = tempfile.TemporaryDirectory(prefix='room-analysis-preview-')
init(app, lambda: {'id': 'local-preview'}, data_dir=_storage.name)
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(sys.argv[1]) if len(sys.argv)>1 else 8765, threaded=True)
