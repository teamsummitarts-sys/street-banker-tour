import sqlite3

import pytest

from song_builder.migrate_storage import migrate
from song_builder.persistence import on_persistent_disk
from song_builder.store import Store
from tests.test_song_builder_backend import project, wav_bytes


def test_copy_retains_unaccepted_audio_and_reopens_after_restart(tmp_path):
    source, target = tmp_path / 'old', tmp_path / 'persistent'
    store = Store(source)
    p = project()
    store.save_project('alice', p)
    data = wav_bytes()
    asset = store.add_asset('alice', {'name': 'Candidate.wav', 'mime': 'audio/wav',
                                     'duration': 8, 'data': data})
    result = migrate(source, target)
    assert result['copied_assets'] == 1
    # Opening a fresh Store models a new worker. Unaccepted takes are copied too.
    reopened = Store(target)
    assert reopened.get_project('alice', p['id'])['project'] == p
    assert reopened.asset_path(reopened.get_asset('alice', asset['id'])).read_bytes() == data
    assert store.asset_path(asset).read_bytes() == data
    with pytest.raises(ValueError, match='already exists'):
        migrate(source, target)


def test_missing_audio_does_not_publish_a_partial_copy(tmp_path):
    source, target = tmp_path / 'old', tmp_path / 'persistent'
    store = Store(source)
    asset = store.add_asset('alice', {'name': 'Missing.wav', 'mime': 'audio/wav',
                                    'duration': 8, 'data': wav_bytes()})
    store.asset_path(asset).unlink()
    with pytest.raises(ValueError, match='missing or invalid'):
        migrate(source, target)
    assert not target.exists()
    assert store.path.exists()


def test_active_jobs_block_copy(tmp_path):
    store = Store(tmp_path / 'old')
    with sqlite3.connect(store.path) as db:
        db.execute("INSERT INTO jobs(id,owner,request_id,payload_hash,payload_json,project_id,kind,status,created_at,lease_until) VALUES ('job','alice','request','hash','{}','project','generate','running',0,99999999999)")
    with pytest.raises(ValueError, match='active music'):
        migrate(store.directory, tmp_path / 'persistent')
    assert not (tmp_path / 'persistent').exists()


def test_durable_status_requires_mounted_disk_and_path(monkeypatch, tmp_path):
    monkeypatch.setattr('song_builder.persistence.os.path.ismount', lambda _: False)
    assert not on_persistent_disk('/var/data/v2/the_room')
    monkeypatch.setattr('song_builder.persistence.os.path.ismount', lambda _: True)
    assert on_persistent_disk('/var/data/v2/the_room')
    assert not on_persistent_disk(tmp_path)
