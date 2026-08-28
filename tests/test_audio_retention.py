"""Retention: destroying audio when the policy says to, and never lying about it.

The sharp edge here is blob_store.remove(), which returns a BOOLEAN and
swallows its own exceptions rather than raising. Code that treats "no
exception" as success will mark audio destroyed while it is still on disk -
worse than never having run the sweep, because now nobody will look for it.
"""
import os

import pytest

import audio_retention as retention
import audio_store as astore
import blob_store
from db import get_db


@pytest.fixture(scope="module")
def application():
    import app as appmod
    return appmod.create_app()


@pytest.fixture
def expired_asset(application):
    """A real file on disk, with a real asset row, already past its date."""
    with application.app_context():
        updir = retention.uploads_dir()
        os.makedirs(updir, exist_ok=True)
        name = "retention-test-%s.wav" % os.urandom(4).hex()
        path = os.path.join(updir, name)
        with open(path, "wb") as handle:
            handle.write(b"RIFF----fake audio")

        created = astore.create_asset(None, "u1", "/uploads/" + name,
                                      file_name=name, mime_type="audio/wav")
        asset_id = created if isinstance(created, str) else created["id"]
        with get_db() as db:
            db.execute("UPDATE audio_assets SET retention_expires_at = ? "
                       "WHERE id = ?", ("2020-01-01T00:00:00Z", asset_id))
        yield {"id": asset_id, "name": name, "path": path}


def _row(application, name):
    """Straight at the table, deliberately.

    list_assets() filters out deleted_at rows - which is right for the app,
    and useless here: the whole point of these tests is that the row OUTLIVES
    the audio, so the assertion has to look where the app no longer does.
    """
    with application.app_context():
        with get_db() as db:
            found = db.execute(
                "SELECT * FROM audio_assets WHERE file_name = ?", (name,)).fetchone()
    return dict(found) if found else None


# --- the happy path --------------------------------------------------------

def test_a_dry_run_reports_without_deleting(application, expired_asset):
    with application.app_context():
        report = retention.sweep(dry_run=True)
    assert report["dry_run"] is True
    assert report["examined"] >= 1
    assert report["deleted"] == 0
    assert os.path.exists(expired_asset["path"]), "a dry run destroyed audio"


def test_expired_audio_is_destroyed(application, expired_asset):
    with application.app_context():
        report = retention.sweep()
    assert report["failed"] == 0, report["failures"]
    assert not os.path.exists(expired_asset["path"])


def test_the_row_survives_the_bytes(application, expired_asset):
    """An audit trail that vanishes with the audio is not an audit trail. The
    question asked afterwards is what was held and when it was destroyed."""
    with application.app_context():
        retention.sweep()
    row = _row(application, expired_asset["name"])
    assert row is not None, "the asset row was deleted along with the audio"
    assert row["deleted_at"], "deleted_at was not recorded"
    assert row["storage_key"] == "", "the storage key still points somewhere"


# --- the property that matters ---------------------------------------------

def test_a_failed_delete_is_not_recorded_as_deleted(application, expired_asset,
                                                    monkeypatch):
    """blob_store.remove returns False rather than raising. If that is read as
    success, the app reports audio destroyed while it is still on disk."""
    monkeypatch.setattr(blob_store, "remove", lambda *a, **k: False)
    monkeypatch.setattr(retention, "_definitely_absent", lambda key: False)

    with application.app_context():
        report = retention.sweep()

    assert report["deleted"] == 0
    assert report["failed"] >= 1
    assert report["failures"], "a failure must say which asset and why"

    row = _row(application, expired_asset["name"])
    assert row["deleted_at"] is None, \
        "audio was reported destroyed when the delete failed"


def test_a_raising_storage_layer_is_also_a_failure(application, expired_asset,
                                                   monkeypatch):
    def explode(*args, **kwargs):
        raise OSError("disk is not mounted")

    monkeypatch.setattr(blob_store, "remove", explode)
    with application.app_context():
        report = retention.sweep()

    assert report["failed"] >= 1
    row = _row(application, expired_asset["name"])
    assert row["deleted_at"] is None


def test_audio_that_is_already_gone_counts_as_deleted(application, expired_asset):
    """Otherwise the sweep wedges forever on a file somebody tidied by hand."""
    os.remove(expired_asset["path"])
    with application.app_context():
        report = retention.sweep()
    assert report["failed"] == 0, report["failures"]
    row = _row(application, expired_asset["name"])
    assert row["deleted_at"], "an already-absent file should settle the row"


# --- the policy arithmetic -------------------------------------------------

def test_a_missing_or_zero_retention_means_keep_not_purge(application):
    """Reading a missing policy number as 'delete immediately' is the wrong
    direction to fail in."""
    with application.app_context():
        astore.set_policy(None, {"source_audio_retention_days": 0})
        try:
            assert retention.expiry_for(None, "source") is None
        finally:
            astore.set_policy(None, {"source_audio_retention_days": 90})


def test_retention_days_come_from_the_tenant_policy(application):
    with application.app_context():
        astore.set_policy(None, {"source_audio_retention_days": 7})
        try:
            assert retention.retention_days(None, "source") == 7
            stamp = retention.expiry_for(None, "source",
                                         created_at="2026-01-01T00:00:00Z")
            assert stamp.startswith("2026-01-08"), stamp
        finally:
            astore.set_policy(None, {"source_audio_retention_days": 90})


def test_unexpired_audio_is_left_alone(application):
    with application.app_context():
        updir = retention.uploads_dir()
        os.makedirs(updir, exist_ok=True)
        name = "retention-keep-%s.wav" % os.urandom(4).hex()
        path = os.path.join(updir, name)
        with open(path, "wb") as handle:
            handle.write(b"RIFF----keep me")
        created = astore.create_asset(None, "u1", "/uploads/" + name,
                                      file_name=name, mime_type="audio/wav")
        asset_id = created if isinstance(created, str) else created["id"]
        with get_db() as db:
            db.execute("UPDATE audio_assets SET retention_expires_at = ? "
                       "WHERE id = ?", ("2099-01-01T00:00:00Z", asset_id))

        retention.sweep()
        assert os.path.exists(path), "audio inside its retention window was destroyed"
