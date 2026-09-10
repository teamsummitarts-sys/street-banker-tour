"""Persistent reusable artist profiles for REACH.

An artist profile is the reusable source of truth for identity, positioning,
links, contacts and campaign defaults. Release-specific facts stay on the
recording. REACH can use this profile by itself; Street Banker EPK, Artwork,
Vault and Passport tools are optional helpers, never dependencies.
"""

import json

from . import audit, clock, db, profile, rbac
from .errors import ValidationError

SOURCE_ARTIST_PROFILE = "artist_profile"

ARTIST_DEFAULT_FIELDS = [
    "primary_genre",
    "secondary_genres",
    "microgenres",
    "vocal_style",
    "vocal_range",
    "vocal_presentation",
    "instrumentation",
    "production_style",
    "era_influences",
    "cultural_scene",
    "language",
    "comparable_artists",
    "target_audiences",
    "playlist_contexts",
    "radio_formats",
    "geographic_affinity",
    "live_relevance",
    "visual_identity",
]

PROFILE_TEXT_FIELDS = [
    "bio",
    "hometown",
    "website",
    "instagram_url",
    "tiktok_url",
    "youtube_url",
    "spotify_url",
    "management_name",
    "management_email",
]

_schema_ready_path = None


def _ensure_schema():
    """Create the profile table once per configured REACH database."""
    global _schema_ready_path
    current_path = db.current_path()
    if _schema_ready_path == current_path:
        return
    db.execute(
        "CREATE TABLE IF NOT EXISTS artist_profile_data ("
        "artist_id TEXT PRIMARY KEY REFERENCES artist(id), "
        "tenant_id TEXT NOT NULL REFERENCES tenant(id), "
        "profile_json TEXT NOT NULL DEFAULT '{}', "
        "defaults_json TEXT NOT NULL DEFAULT '{}', "
        "assets_json TEXT NOT NULL DEFAULT '[]', "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    _schema_ready_path = current_path


def _loads(raw, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def _clean_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _clean_asset(item):
    if isinstance(item, str):
        path = item.strip()
        return {"path": path, "kind": "file", "label": None} if path else None
    if not isinstance(item, dict):
        return None
    path = _clean_text(item.get("path"))
    if not path:
        return None
    return {
        "path": path,
        "kind": _clean_text(item.get("kind")) or "file",
        "label": _clean_text(item.get("label")),
    }


def _artist_row(artist_id, tenant_id=None):
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    return db.query_one(
        "SELECT * FROM artist WHERE id = ? AND tenant_id = ?", (artist_id, tenant_id)
    )


def ensure_artist(name, tenant_id=None):
    """Create an artist identity without forcing the user to create a release."""
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    name = _clean_text(name)
    if not name:
        raise ValidationError("Artist name is required")
    row = db.query_one(
        "SELECT id FROM artist WHERE tenant_id = ? AND lower(name) = lower(?)",
        (tenant_id, name),
    )
    if row:
        return row["id"]
    artist_id = db.new_id("art")
    db.insert("artist", {
        "id": artist_id,
        "tenant_id": tenant_id,
        "name": name[:180],
        "musicbrainz_artist_id": None,
        "created_at": clock.now_iso(),
    })
    audit.record(
        "artist_profile.artist_created", entity_type="artist", entity_id=artist_id,
        payload={"name": name[:180]},
    )
    return artist_id


def list_artists(tenant_id=None):
    """Real/user-created artists only; sample-only fixture artists are excluded."""
    _ensure_schema()
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    return db.query(
        "SELECT a.id, a.name, a.created_at, "
        "(SELECT COUNT(*) FROM recording r WHERE r.artist_id = a.id AND r.is_sample = 0) AS release_count, "
        "(SELECT MAX(r.created_at) FROM recording r WHERE r.artist_id = a.id AND r.is_sample = 0) AS last_release_at "
        "FROM artist a WHERE a.tenant_id = ? AND ("
        "EXISTS (SELECT 1 FROM recording r WHERE r.artist_id = a.id AND r.is_sample = 0) "
        "OR EXISTS (SELECT 1 FROM artist_profile_data p WHERE p.artist_id = a.id)) "
        "ORDER BY lower(a.name)",
        (tenant_id,),
    )


def get(artist_id, tenant_id=None):
    _ensure_schema()
    artist = _artist_row(artist_id, tenant_id)
    if artist is None:
        return None
    row = db.query_one("SELECT * FROM artist_profile_data WHERE artist_id = ?", (artist_id,))
    base = {
        "artist_id": artist_id,
        "artist_name": artist["name"],
        "profile": {},
        "defaults": {},
        "assets": [],
        "updated_at": None,
    }
    if row is None:
        return base
    base.update({
        "profile": _loads(row["profile_json"], {}),
        "defaults": _loads(row["defaults_json"], {}),
        "assets": _loads(row["assets_json"], []),
        "updated_at": row["updated_at"],
    })
    return base


def _history_defaults(artist_id, tenant_id):
    """Newest user-confirmed reusable track fields, used only to fill profile gaps."""
    rows = db.query(
        "SELECT f.field, f.value_json, f.generated_at "
        "FROM track_profile_field f "
        "JOIN track_profile p ON p.id = f.profile_id "
        "JOIN recording r ON r.id = p.recording_id "
        "WHERE r.artist_id = ? AND r.tenant_id = ? AND r.is_sample = 0 "
        "AND f.human_override = 1 ORDER BY f.generated_at DESC",
        (artist_id, tenant_id),
    )
    allowed = set(ARTIST_DEFAULT_FIELDS)
    result = {}
    for row in rows:
        field = row["field"]
        if field not in allowed or field in result or not row["value_json"]:
            continue
        try:
            value = json.loads(row["value_json"])
        except (TypeError, ValueError):
            continue
        if value not in (None, "", []):
            result[field] = value
    return result


def display(artist_id, tenant_id=None):
    """Profile for editing, with older user-entered release defaults filling gaps."""
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    current = get(artist_id, tenant_id)
    if current is None:
        return None
    merged = dict(_history_defaults(artist_id, tenant_id))
    merged.update({k: v for k, v in current["defaults"].items() if v not in (None, "", [])})
    current["defaults"] = merged
    current["releases"] = db.query(
        "SELECT id, title, isrc, release_date, created_at FROM recording "
        "WHERE artist_id = ? AND tenant_id = ? AND is_sample = 0 ORDER BY created_at DESC",
        (artist_id, tenant_id),
    )
    known_profile = sum(1 for key in PROFILE_TEXT_FIELDS if current["profile"].get(key))
    known_defaults = sum(1 for key in ARTIST_DEFAULT_FIELDS if merged.get(key) not in (None, "", []))
    current["known_fields"] = known_profile + known_defaults
    current["total_fields"] = len(PROFILE_TEXT_FIELDS) + len(ARTIST_DEFAULT_FIELDS)
    return current


def save(artist_id, values, tenant_id=None):
    """Replace supplied profile fields while preserving fields not present in the payload."""
    _ensure_schema()
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    artist = _artist_row(artist_id, tenant_id)
    if artist is None:
        raise ValidationError("Unknown artist profile")

    current = get(artist_id, tenant_id)
    profile_values = dict(current["profile"])
    defaults = dict(current["defaults"])
    assets = list(current["assets"])

    for key in PROFILE_TEXT_FIELDS:
        if key not in values:
            continue
        cleaned = _clean_text(values.get(key))
        if cleaned is None:
            profile_values.pop(key, None)
        else:
            profile_values[key] = cleaned

    for field in ARTIST_DEFAULT_FIELDS:
        if field not in values:
            continue
        raw = values.get(field)
        if raw in (None, "", []):
            defaults.pop(field, None)
            continue
        _, kind, _, _ = profile.FIELDS_BY_NAME[field]
        try:
            defaults[field] = profile._coerce(kind, raw)
        except Exception as exc:
            raise ValidationError(f"Invalid {field.replace('_', ' ')}") from exc

    incoming_assets = values.get("artist_assets") or []
    if isinstance(incoming_assets, str):
        try:
            incoming_assets = json.loads(incoming_assets)
        except (TypeError, ValueError):
            incoming_assets = []
    known_paths = {item.get("path") for item in assets if isinstance(item, dict)}
    for item in incoming_assets:
        cleaned = _clean_asset(item)
        if cleaned and cleaned["path"] not in known_paths:
            assets.append(cleaned)
            known_paths.add(cleaned["path"])

    now = clock.now_iso()
    profile_json = json.dumps(profile_values)
    defaults_json = json.dumps(defaults)
    assets_json = json.dumps(assets)
    existing = db.query_one("SELECT artist_id FROM artist_profile_data WHERE artist_id = ?", (artist_id,))
    if existing:
        db.execute(
            "UPDATE artist_profile_data SET profile_json = ?, defaults_json = ?, "
            "assets_json = ?, updated_at = ? WHERE artist_id = ?",
            (profile_json, defaults_json, assets_json, now, artist_id),
        )
    else:
        db.insert("artist_profile_data", {
            "artist_id": artist_id,
            "tenant_id": tenant_id,
            "profile_json": profile_json,
            "defaults_json": defaults_json,
            "assets_json": assets_json,
            "created_at": now,
            "updated_at": now,
        })
    audit.record(
        "artist_profile.saved", entity_type="artist", entity_id=artist_id,
        payload={"profile_fields": sorted(profile_values), "default_fields": sorted(defaults),
                 "asset_count": len(assets)},
    )
    return display(artist_id, tenant_id)


def defaults_for_recording(recording_id):
    """Return persistent artist defaults, then fill gaps from prior real releases."""
    recording = db.query_one(
        "SELECT artist_id, tenant_id FROM recording WHERE id = ?", (recording_id,)
    )
    if recording is None:
        return {}
    stored = get(recording["artist_id"], recording["tenant_id"])
    result = {
        key: value for key, value in (stored["defaults"] if stored else {}).items()
        if key in ARTIST_DEFAULT_FIELDS and value not in (None, "", [])
    }
    history = _history_defaults(recording["artist_id"], recording["tenant_id"])
    for field, value in history.items():
        result.setdefault(field, value)
    return result


def apply_to_profile(profile_id, recording_id):
    """Populate only currently-UNKNOWN artist fields on a new release profile."""
    inherited = defaults_for_recording(recording_id)
    if not inherited:
        return []
    existing = {
        row["field"]
        for row in db.query("SELECT field FROM track_profile_field WHERE profile_id = ?", (profile_id,))
    }
    applied = []
    for field, value in inherited.items():
        if field in existing or field not in profile.FIELDS_BY_NAME:
            continue
        profile.set_field(profile_id, field, value, source=SOURCE_ARTIST_PROFILE, confidence=1.0)
        applied.append(field)
    return applied
