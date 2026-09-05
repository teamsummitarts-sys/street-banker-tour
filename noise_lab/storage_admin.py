"""Operator-run, local SQLite snapshot and restore-copy helpers.

Usage from the repository root (destination directories must already exist):

    python -m noise_lab.storage_admin snapshot \
        --source /absolute/source.sqlite --destination /absolute/new-snapshot.sqlite

    python -m noise_lab.storage_admin restore-copy \
        --source /absolute/snapshot.sqlite --destination /persistent/streetbanker.sqlite \
        --persistent-root /persistent

Both operations refuse an existing destination and preserve the source. Copies
include the entire host database, including account IDs and private patches.
Keep them private. This helper does not activate a database, schedule backups,
upload a backup, implement retention, or create an off-site recovery service.
"""
import argparse
import os
from pathlib import Path
import sqlite3
import stat
import sys
from contextlib import closing


class StorageAdminError(Exception):
    """An allowlisted diagnostic without SQL, row contents or credentials."""


def _paths(source, destination):
    try:
        source = Path(source).resolve(strict=True)
        if not source.is_file():
            raise StorageAdminError('invalid_source')
        supplied_target = Path(destination).absolute()
        target = supplied_target.parent.resolve(strict=True) / supplied_target.name
        if source == target.resolve():
            raise StorageAdminError('source_is_destination')
        if os.path.lexists(target):
            raise StorageAdminError('destination_exists')
        if any(os.path.lexists(str(target) + suffix) for suffix in ('-journal', '-wal', '-shm')):
            raise StorageAdminError('destination_exists')
        if not target.parent.is_dir():
            raise StorageAdminError('destination_directory_unavailable')
        return source, target
    except (OSError, TypeError, ValueError, RuntimeError):
        raise StorageAdminError('invalid_path') from None


def _check_database(conn):
    if conn.execute('PRAGMA integrity_check(1)').fetchone() != ('ok',):
        raise StorageAdminError('database_check_failed')
    if conn.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise StorageAdminError('database_check_failed')


def _owned_file(path, identity):
    """A failed attempt must never remove a replacement supplied by someone else."""
    try:
        current = path.lstat()
        return stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == identity
    except OSError:
        return False


def _snapshot(source, target):
    identity, complete = None, False
    try:
        with source.open('rb') as file:
            if file.read(16) != b'SQLite format 3\x00':
                raise StorageAdminError('invalid_database')
        # mode=ro is deliberate: connecting to a mistyped path must never create
        # a new source database. Do not use immutable=1; it can ignore live WAL.
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
            _check_database(original)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            try:
                created = os.fstat(descriptor)
                identity = (created.st_dev, created.st_ino)
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
            if not _owned_file(target, identity):
                raise StorageAdminError('destination_changed')
            with closing(sqlite3.connect(target.as_uri() + '?mode=rw', uri=True)) as copy:
                original.backup(copy)
                # Produce a standalone file after copying a source that uses WAL.
                if copy.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                    raise StorageAdminError('database_check_failed')
                _check_database(copy)
                copy.commit()
        if not _owned_file(target, identity):
            raise StorageAdminError('destination_changed')
        with target.open('rb') as file:
            os.fsync(file.fileno())
        directory = os.open(target.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        complete = True
        return target
    except StorageAdminError:
        raise
    except FileExistsError:
        raise StorageAdminError('destination_exists') from None
    except (sqlite3.Error, OSError, TypeError, ValueError):
        raise StorageAdminError('snapshot_failed') from None
    finally:
        if not complete and identity is not None and _owned_file(target, identity):
            try:
                target.unlink()
            except OSError:
                raise StorageAdminError('partial_copy_cleanup_failed') from None


def snapshot_database(source, destination):
    """Create a checked native SQLite copy at a new mode-0600 destination."""
    source, target = _paths(source, destination)
    return _snapshot(source, target)


def restore_to_mount(source, destination, persistent_root):
    """Copy to a verified mount; never replace or activate an existing store."""
    source, target = _paths(source, destination)
    try:
        supplied_root = Path(persistent_root)
        if not supplied_root.is_absolute():
            raise StorageAdminError('persistent_mount_required')
        root = supplied_root.resolve(strict=True)
        if root == Path(root.anchor) or not os.path.ismount(str(root)):
            raise StorageAdminError('persistent_mount_required')
        if target == root or not target.is_relative_to(root):
            raise StorageAdminError('destination_outside_mount')
    except (OSError, TypeError, ValueError, RuntimeError):
        raise StorageAdminError('invalid_mount_path') from None
    return _snapshot(source, target)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Create a private, checked SQLite copy without overwriting data.')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('snapshot', 'restore-copy'):
        command = commands.add_parser(name)
        command.add_argument('--source', required=True)
        command.add_argument('--destination', required=True)
        if name == 'restore-copy':
            command.add_argument('--persistent-root', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'snapshot':
            snapshot_database(args.source, args.destination)
        else:
            restore_to_mount(args.source, args.destination, args.persistent_root)
    except StorageAdminError as error:
        print(f'Copy failed: {error}. No database was activated.', file=sys.stderr)
        return 1
    print('Verified private SQLite copy created. No database was activated.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
