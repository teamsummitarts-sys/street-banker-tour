"""Street Banker Audio Intelligence - retention.

A retention policy nobody runs is a promise, not a control. This is the sweep
that makes the numbers in the policy true.

WHAT IS DELETED, AND WHAT SURVIVES
----------------------------------
The BYTES go. The ROW stays, with deleted_at set and storage_key cleared. An
audit trail that vanishes along with the audio is not an audit trail: the
question asked afterwards is "what did you hold, and when did you destroy it",
and only a surviving row can answer it.

DELETION IS ATTEMPTED BEFORE IT IS RECORDED
-------------------------------------------
The row is marked deleted only after the blob is actually gone. Marking first
and deleting second means a failed delete leaves audio on disk that the app
believes it destroyed - which is the one outcome worse than not running the
sweep at all. A blob that will not delete is reported and retried next sweep.

MISSING IS SUCCESS
------------------
A blob that is already absent counts as deleted. It is the state we wanted;
insisting on having been the one to remove it would wedge the sweep forever on
files a person cleaned up by hand.

THIS RUNS FROM A SCHEDULER, NOT A REQUEST
-----------------------------------------
sweep() takes no user and grants no access. It is called by the backup/cron
path and by the admin page, and it never reads a session.
"""
import datetime
import traceback

import audio_store as astore

# A sweep touches storage, so it is bounded. Whatever is left is picked up on
# the next run rather than turning one overdue backlog into a long request.
DEFAULT_LIMIT = 500


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def retention_days(partner_id, asset_type):
    """How long this tenant keeps this kind of audio."""
    policy = astore.get_policy(partner_id)
    key = {
        "source": "source_audio_retention_days",
        "generated": "generated_audio_retention_days",
        "voice_sample": "voice_sample_retention_days",
        "agent_conversation": "agent_conversation_retention_days",
    }.get(asset_type, "source_audio_retention_days")
    try:
        return int(policy.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def expiry_for(partner_id, asset_type, created_at=None):
    """The timestamp to stamp on a new asset, or None to keep it indefinitely.

    Zero or negative days means "no automatic expiry", not "delete at once".
    Reading a missing or malformed policy number as an instruction to delete
    immediately is the wrong direction to fail in.
    """
    days = retention_days(partner_id, asset_type)
    if days <= 0:
        return None
    base = _parse(created_at) or datetime.datetime.now(datetime.timezone.utc)
    return (base + datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts):
    if not ts:
        return None
    try:
        cleaned = str(ts).replace("Z", "+00:00")
        parsed = datetime.datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return None


def uploads_dir():
    """Where local uploads live, derived the same way app.py derives it.

    blob_store.remove() needs this for anything under /uploads/: without it
    the function silently does nothing and returns False, so a sweep that
    forgot to pass it would report every local file as undeletable.
    """
    import os

    import db as store
    try:
        return os.path.join(os.path.dirname(store.db_path()), "uploads")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")


def _delete_blob(storage_key):
    """Remove the bytes. Returns (deleted, detail).

    blob_store.remove() returns a BOOLEAN and swallows its own exceptions - it
    does not raise on failure. Treating "no exception" as success would record
    audio as destroyed while it sat on disk, which is the one outcome worse
    than not sweeping at all. So the return value is what decides here.

    Absent counts as deleted: it is the state we wanted, and insisting on
    having been the one to remove it would wedge the sweep forever on files a
    person tidied up by hand.
    """
    if not storage_key:
        return True, "no stored object"
    try:
        import blob_store
    except Exception as exc:
        return False, "blob_store unavailable: %s" % exc

    try:
        removed = blob_store.remove(storage_key, uploads_dir=uploads_dir())
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)

    if removed:
        return True, "deleted"

    # False means either "already gone" or "could not delete", and remove()
    # does not distinguish. Ask the filesystem rather than guess: a local path
    # that is no longer there is genuinely deleted; anything else is a failure
    # and gets retried on the next sweep.
    if _definitely_absent(storage_key):
        return True, "already absent"
    return False, "blob_store.remove returned False"


def _definitely_absent(storage_key):
    import os
    try:
        import blob_store
        if blob_store.is_remote(storage_key):
            # A remote delete that reported False may or may not have landed.
            # Not provable from here, so it is treated as a failure and retried.
            return False
        if not str(storage_key).startswith("/uploads/"):
            return False
        return not os.path.exists(
            blob_store.safe_local_path(storage_key, uploads_dir()))
    except Exception:
        return False


def sweep(now=None, limit=DEFAULT_LIMIT, dry_run=False):
    """Destroy what is past its retention date.

    Returns a report rather than logging and forgetting: the admin page shows
    it, and a failure that is only in a log is a failure nobody sees.
    """
    report = {"examined": 0, "deleted": 0, "failed": 0, "dry_run": bool(dry_run),
              "ran_at": _now(), "failures": []}

    try:
        due = astore.expired_assets(now=now or _now())
    except Exception as exc:
        report["failures"].append({"asset_id": None,
                                   "reason": "could not list expired assets: %s" % exc})
        report["failed"] = 1
        return report

    for asset in due[:limit]:
        report["examined"] += 1
        if dry_run:
            continue
        try:
            ok, detail = _delete_blob(asset.get("storage_key") or "")
            if not ok:
                report["failed"] += 1
                report["failures"].append({"asset_id": asset.get("id"),
                                           "reason": detail})
                continue
            # Only now. The bytes are gone, so the record can say so.
            astore.mark_asset_deleted(asset["id"])
            report["deleted"] += 1
        except Exception as exc:
            report["failed"] += 1
            report["failures"].append({
                "asset_id": asset.get("id"),
                "reason": "%s: %s" % (type(exc).__name__, exc)})
            _log(exc)

    report["remaining"] = max(0, len(due) - report["examined"])
    return report


def due_count(now=None):
    """How much is overdue, for the admin page. Cheap and read-only."""
    try:
        return len(astore.expired_assets(now=now or _now()))
    except Exception:
        return 0


def _log(exc):
    try:
        import logging
        logging.getLogger("audio").warning("retention sweep: %s: %s\n%s",
                                           type(exc).__name__, exc,
                                           traceback.format_exc())
    except Exception:
        pass
