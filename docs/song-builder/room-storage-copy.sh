python - <<'ROOM_STORAGE_COPY'
"""Copy a quiescent Room store without deleting or replacing its source.

Run in the live V2 shell BEFORE deploying or changing SONG_BUILDER_DATA_DIR.
Pause Room edits until the destination is configured and the release completes.
This file uses only Python's standard library and can be pasted into the shell.
"""
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid


def migrate(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError('Destination already exists; nothing was replaced.')
    database = source / 'songs.sqlite3'
    if not database.is_file():
        raise ValueError('Source database does not exist; nothing was copied.')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as original:
        original.execute('BEGIN')
        if original.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:
            raise ValueError('Wait for active music requests to finish before copying.')
        assets = original.execute('SELECT id,size FROM assets').fetchall()
        with tempfile.TemporaryDirectory(prefix='.room-copy-', dir=destination.parent) as staging:
            staging = Path(staging)
            (staging / 'audio').mkdir(mode=0o700)
            with sqlite3.connect(staging / 'songs.sqlite3') as copied:
                original.backup(copied)
                if copied.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Database integrity check failed.')
            os.chmod(staging / 'songs.sqlite3', 0o600)
            for asset_id, size in assets:
                filename = str(uuid.UUID(asset_id)) + '.audio'
                src, dst = source / 'audio' / filename, staging / 'audio' / filename
                if src.is_symlink() or not src.is_file() or src.stat().st_size != size:
                    raise ValueError('A referenced audio file is missing or invalid.')
                shutil.copyfile(src, dst)
                os.chmod(dst, 0o600)
                def digest(path):
                    with path.open('rb') as handle:
                        return hashlib.file_digest(handle, 'sha256').digest()
                if digest(src) != digest(dst):
                    raise ValueError('Audio verification failed.')
            # mkdir is exclusive: never replace a destination created during copying.
            destination.mkdir(mode=0o700)
            try:
                for child in staging.iterdir():
                    shutil.move(str(child), destination / child.name)
            except Exception:
                raise RuntimeError('Copy incomplete; leave source configured and inspect destination.') from None
    return {'copied_assets': len(assets), 'destination': str(destination)}


if __name__ == '__main__':
    if not os.path.ismount('/var/data'):
        raise SystemExit('Persistent disk is not mounted; stopping.')
    source = os.environ.get('SONG_BUILDER_DATA_DIR') or 'instance/song_builder'
    print(migrate(source, '/var/data/v2/the_room'))
    print('Source retained. Keep The Room idle until its new path is configured.')

ROOM_STORAGE_COPY
