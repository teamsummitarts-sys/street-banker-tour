"""Offline snapshot/restore-copy verification against temporary SQLite files."""
import os
import sqlite3
import stat

import pytest

from noise_lab import storage_admin


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'source.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL)')
        db.execute('CREATE TABLE noise_lab_patches (id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id), recipe TEXT)')
        db.execute("INSERT INTO users VALUES ('stable-account-id', 'Private account')")
        db.execute("INSERT INTO noise_lab_patches VALUES ('stable-patch-id', 'stable-account-id', '{\"schemaVersion\":1}')")
    return path


def rows(path):
    with sqlite3.connect(path) as db:
        return (db.execute('SELECT * FROM users').fetchall(),
                db.execute('SELECT * FROM noise_lab_patches').fetchall())


def test_snapshot_keeps_ids_recipes_source_and_private_permissions(source, tmp_path):
    original = source.read_bytes()
    target = tmp_path / 'new snapshot.sqlite'
    result = storage_admin.snapshot_database(source, target)
    assert result == target
    assert rows(target) == rows(source)
    assert source.read_bytes() == original
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_wal_snapshot_contains_committed_state_without_uncommitted_writer_changes(source, tmp_path):
    with sqlite3.connect(source) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        writer.execute("INSERT INTO users VALUES ('committed', 'Committed account')")
        writer.commit()
        writer.execute("INSERT INTO users VALUES ('not-committed', 'Pending account')")
        target = storage_admin.snapshot_database(source, tmp_path / 'wal-copy.sqlite')
        with sqlite3.connect(target) as copy:
            assert copy.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert copy.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
            assert copy.execute('SELECT id FROM users ORDER BY id').fetchall() == [
                ('committed',), ('stable-account-id',)]
        writer.rollback()
    assert not os.path.exists(str(target) + '-wal')
    assert not os.path.exists(str(target) + '-shm')
    assert rows(target) == rows(source)


@pytest.mark.parametrize('content', [b'', b'private malformed input', b'SQLite format 3\x00broken'])
def test_malformed_source_creates_no_partial_copy(tmp_path, content):
    source = tmp_path / 'bad.sqlite'
    target = tmp_path / 'output.sqlite'
    source.write_bytes(content)
    with pytest.raises(storage_admin.StorageAdminError) as caught:
        storage_admin.snapshot_database(source, target)
    assert 'private' not in str(caught.value)
    assert not target.exists()
    assert source.read_bytes() == content


def test_source_foreign_key_violation_is_rejected_without_copy(source, tmp_path):
    with sqlite3.connect(source) as connection:
        connection.execute("INSERT INTO noise_lab_patches VALUES ('orphan', 'no-user', '{}')")
    target = tmp_path / 'output.sqlite'
    with pytest.raises(storage_admin.StorageAdminError, match='database_check_failed'):
        storage_admin.snapshot_database(source, target)
    assert not target.exists()


def test_missing_source_and_destination_directory_are_not_created(source, tmp_path):
    target = tmp_path / 'copy.sqlite'
    with pytest.raises(storage_admin.StorageAdminError):
        storage_admin.snapshot_database(tmp_path / 'missing.sqlite', target)
    assert not target.exists()
    assert not (tmp_path / 'missing.sqlite').exists()
    with pytest.raises(storage_admin.StorageAdminError):
        storage_admin.snapshot_database(source, tmp_path / 'missing' / 'copy.sqlite')
    assert not (tmp_path / 'missing').exists()


def test_existing_destination_same_path_and_symlink_are_never_overwritten(source, tmp_path):
    original = source.read_bytes()
    target = tmp_path / 'already-there.sqlite'
    target.write_bytes(b'preserve this existing data')
    with pytest.raises(storage_admin.StorageAdminError, match='destination_exists'):
        storage_admin.snapshot_database(source, target)
    assert target.read_bytes() == b'preserve this existing data'
    with pytest.raises(storage_admin.StorageAdminError, match='source_is_destination'):
        storage_admin.snapshot_database(source, source)
    link = tmp_path / 'link.sqlite'
    link.symlink_to(target)
    with pytest.raises(storage_admin.StorageAdminError, match='destination_exists'):
        storage_admin.snapshot_database(source, link)
    assert link.is_symlink()
    dangling = tmp_path / 'dangling.sqlite'
    dangling.symlink_to(tmp_path / 'missing.sqlite')
    with pytest.raises(storage_admin.StorageAdminError, match='destination_exists'):
        storage_admin.snapshot_database(source, dangling)
    assert dangling.is_symlink()
    assert source.read_bytes() == original


@pytest.mark.parametrize('suffix', ['-journal', '-wal', '-shm'])
def test_preexisting_sqlite_sidecar_is_not_reused_or_removed(source, tmp_path, suffix):
    target = tmp_path / 'copy.sqlite'
    sidecar = tmp_path / ('copy.sqlite' + suffix)
    sidecar.write_bytes(b'preexisting private data')
    with pytest.raises(storage_admin.StorageAdminError, match='destination_exists'):
        storage_admin.snapshot_database(source, target)
    assert sidecar.read_bytes() == b'preexisting private data'
    assert not target.exists()


def test_failed_destination_validation_removes_only_new_partial_copy(source, tmp_path, monkeypatch):
    original_check = storage_admin._check_database
    calls = 0
    def fail_after_copy(connection):
        nonlocal calls
        calls += 1
        original_check(connection)
        if calls == 2:
            raise storage_admin.StorageAdminError('database_check_failed')
    monkeypatch.setattr(storage_admin, '_check_database', fail_after_copy)
    target = tmp_path / 'partial.sqlite'
    original = source.read_bytes()
    with pytest.raises(storage_admin.StorageAdminError, match='database_check_failed'):
        storage_admin.snapshot_database(source, target)
    assert calls == 2
    assert not target.exists()
    assert list(tmp_path.glob('partial.sqlite*')) == []
    assert source.read_bytes() == original


def test_exclusive_creation_rejects_destination_that_appears_during_copy(source, tmp_path, monkeypatch):
    target = tmp_path / 'race.sqlite'
    original_check = storage_admin._check_database
    def insert_other_output(connection):
        original_check(connection)
        target.write_bytes(b'another operation owns this')
    monkeypatch.setattr(storage_admin, '_check_database', insert_other_output)
    with pytest.raises(storage_admin.StorageAdminError, match='destination_exists'):
        storage_admin.snapshot_database(source, target)
    assert target.read_bytes() == b'another operation owns this'


def test_failed_copy_does_not_delete_a_replacement_at_destination(source, tmp_path, monkeypatch):
    target = tmp_path / 'changed.sqlite'
    original_check = storage_admin._check_database
    calls = 0
    def replace_after_check(connection):
        nonlocal calls
        calls += 1
        original_check(connection)
        if calls == 2:
            target.unlink()
            target.write_bytes(b'new owner content')
            raise storage_admin.StorageAdminError('destination_changed')
    monkeypatch.setattr(storage_admin, '_check_database', replace_after_check)
    with pytest.raises(storage_admin.StorageAdminError, match='destination_changed'):
        storage_admin.snapshot_database(source, target)
    assert target.read_bytes() == b'new owner content'


def test_restore_copy_requires_actual_mount_and_preserves_original(source, tmp_path, monkeypatch):
    mount = tmp_path / 'persistent'
    mount.mkdir()
    target = mount / 'streetbanker.sqlite'
    with pytest.raises(storage_admin.StorageAdminError, match='persistent_mount_required'):
        storage_admin.restore_to_mount(source, target, mount)
    assert not target.exists()
    monkeypatch.setattr(storage_admin.os.path, 'ismount', lambda value: value == str(mount))
    original = source.read_bytes()
    result = storage_admin.restore_to_mount(source, target, mount)
    assert result == target
    assert rows(target) == rows(source)
    assert source.read_bytes() == original
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with pytest.raises(storage_admin.StorageAdminError, match='destination_exists'):
        storage_admin.restore_to_mount(source, target, mount)


def test_restore_copy_rejects_root_mount_and_destination_escape(source, tmp_path, monkeypatch):
    mount = tmp_path / 'persistent'
    mount.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    monkeypatch.setattr(storage_admin.os.path, 'ismount', lambda _: True)
    with pytest.raises(storage_admin.StorageAdminError, match='persistent_mount_required'):
        storage_admin.restore_to_mount(source, outside / 'no.sqlite', '/')
    with pytest.raises(storage_admin.StorageAdminError, match='persistent_mount_required'):
        storage_admin.restore_to_mount(source, outside / 'no.sqlite', 'relative-root')
    for destination in (outside / 'no.sqlite', mount / '..' / 'outside' / 'no.sqlite'):
        with pytest.raises(storage_admin.StorageAdminError, match='destination_outside_mount'):
            storage_admin.restore_to_mount(source, destination, mount)
    escaped = mount / 'escape'
    escaped.symlink_to(outside, target_is_directory=True)
    with pytest.raises(storage_admin.StorageAdminError, match='destination_outside_mount'):
        storage_admin.restore_to_mount(source, escaped / 'no.sqlite', mount)
    assert not (outside / 'no.sqlite').exists()


def test_cli_has_explicit_commands_and_sanitized_output(source, tmp_path, capsys):
    target = tmp_path / 'command.sqlite'
    assert storage_admin.main(['snapshot', '--source', str(source), '--destination', str(target)]) == 0
    result = capsys.readouterr()
    assert result.err == ''
    assert 'No database was activated' in result.out
    assert 'Private account' not in result.out
    assert storage_admin.main(['snapshot', '--source', str(source), '--destination', str(target)]) == 1
    result = capsys.readouterr()
    assert result.out == ''
    assert 'destination_exists' in result.err
    assert str(source) not in result.err
    assert str(target) not in result.err


def test_cli_restore_requires_mount_and_offers_no_bypass(source, tmp_path, capsys):
    mount = tmp_path / 'persistent'
    mount.mkdir()
    arguments = ['restore-copy', '--source', str(source), '--destination', str(mount / 'store.sqlite'),
                 '--persistent-root', str(mount)]
    assert storage_admin.main(arguments) == 1
    assert 'persistent_mount_required' in capsys.readouterr().err
    with pytest.raises(SystemExit) as caught:
        storage_admin.main(arguments + ['--skip-mount-check'])
    assert caught.value.code == 2
    assert not (mount / 'store.sqlite').exists()
