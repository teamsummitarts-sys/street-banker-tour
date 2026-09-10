"""Release-level artist credits for REACH.

The reusable Artist Profile owns the primary artist identity. Featured artist
credits belong to a recording instead: a guest on one song must never become a
persistent default for every future campaign.
"""

from . import audit, clock, db, rbac
from .errors import ValidationError

FEATURED = "FEATURED"
MAX_FEATURED_ARTISTS = 20
_schema_ready_path = None


def _ensure_schema():
    global _schema_ready_path
    current_path = db.current_path()
    if _schema_ready_path == current_path:
        return
    db.execute(
        "CREATE TABLE IF NOT EXISTS recording_artist_credit ("
        "id TEXT PRIMARY KEY, "
        "tenant_id TEXT NOT NULL REFERENCES tenant(id), "
        "recording_id TEXT NOT NULL REFERENCES recording(id), "
        "artist_name TEXT NOT NULL, "
        "role TEXT NOT NULL, "
        "position INTEGER NOT NULL DEFAULT 0, "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_recording_artist_credit_recording "
        "ON recording_artist_credit(recording_id, role, position)"
    )
    _schema_ready_path = current_path


def _recording(recording_id, tenant_id=None):
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    return db.query_one(
        "SELECT id, tenant_id, artist_id, title FROM recording "
        "WHERE id = ? AND tenant_id = ?",
        (recording_id, tenant_id),
    )


def normalize_featured_artists(raw):
    """Return ordered, unique, human-entered guest artist names."""
    if raw is None:
        return []
    if isinstance(raw, str):
        values = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        values = raw
    else:
        raise ValidationError("Featured artists must be names separated by commas")

    result = []
    seen = set()
    for value in values:
        name = str(value or "").strip()
        if not name:
            continue
        if len(name) > 180:
            raise ValidationError("Featured artist names must be 180 characters or fewer")
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
        if len(result) > MAX_FEATURED_ARTISTS:
            raise ValidationError(f"A release can list up to {MAX_FEATURED_ARTISTS} featured artists")
    return result


def featured_artists(recording_id, tenant_id=None):
    _ensure_schema()
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    if _recording(recording_id, tenant_id) is None:
        return []
    rows = db.query(
        "SELECT artist_name FROM recording_artist_credit "
        "WHERE recording_id = ? AND tenant_id = ? AND role = ? "
        "ORDER BY position, created_at",
        (recording_id, tenant_id, FEATURED),
    )
    return [row["artist_name"] for row in rows]


def set_featured_artists(recording_id, names, tenant_id=None):
    """Replace a recording's featured artist credit line atomically enough for SQLite.

    These are display/submission credits only. They do not create or mutate an
    Artist Profile for the guest artist.
    """
    _ensure_schema()
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    recording = _recording(recording_id, tenant_id)
    if recording is None:
        raise ValidationError("Unknown release")

    cleaned = normalize_featured_artists(names)
    existing = featured_artists(recording_id, tenant_id)
    if existing == cleaned:
        return cleaned

    db.execute(
        "DELETE FROM recording_artist_credit "
        "WHERE recording_id = ? AND tenant_id = ? AND role = ?",
        (recording_id, tenant_id, FEATURED),
    )
    now = clock.now_iso()
    for position, name in enumerate(cleaned):
        db.insert("recording_artist_credit", {
            "id": db.new_id("credit"),
            "tenant_id": tenant_id,
            "recording_id": recording_id,
            "artist_name": name,
            "role": FEATURED,
            "position": position,
            "created_at": now,
            "updated_at": now,
        })

    audit.record(
        "recording.featured_artists_updated",
        entity_type="recording",
        entity_id=recording_id,
        payload={"before": existing, "after": cleaned},
        actor_kind=audit.ACTOR_USER,
        actor_id=rbac.current_principal().id,
    )
    return cleaned


def credit_line(primary_artist, featured=None):
    primary = str(primary_artist or "").strip()
    featured = normalize_featured_artists(featured or [])
    if not featured:
        return primary
    return f"{primary} feat. {', '.join(featured)}"


def delete_for_recording(recording_id):
    _ensure_schema()
    db.execute("DELETE FROM recording_artist_credit WHERE recording_id = ?", (recording_id,))
