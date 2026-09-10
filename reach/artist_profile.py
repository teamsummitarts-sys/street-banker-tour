"""Persistent reusable artist profiles for REACH.

Artist profiles are durable defaults shared across an artist's releases. They
hold artist-level identity, links, reusable campaign intelligence and references
to files already stored by V2's hardened Vault/blob layer. A release gets an
editable snapshot of these defaults; release-specific facts are never copied
blindly.
"""

import json

from . import clock, db, profile

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

_schema_ready = False


def _ensure_schema():
    global _schema_ready
    if _schema_ready:
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
    _schema_ready = True


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


def get(artist_id):
    _ensure_schema()
    row = db.query_one("SELECT * FROM artist_profile_data WHERE artist_id = ?", (artist_id,))
    if row is None:
        return {"artist_id": artist_id, "profile": {}, "defaults": {}, "assets": []}
    return {
        "artist_id": artist_id,
        "profile": _loads(row["profile_json"], {}),
        "defaults": _loads(row["defaults_json"], {}),
        "assets": _loads(row["assets_json"], []),
        "updated_at": row["updated_at"],
    }


def save(artist_id, values):
    """Merge artist-supplied values and reusable assets into the durable profile."""
    _ensure_schema()
    artist = db.query_one("SELECT tenant_id FROM artist WHERE id = ?", (artist_id,))
    if artist is None:
        return None

    current = get(artist_id)
    profile_values = dict(current["profile"])
    defaults = dict(current["defaults"])
    assets = list(current["assets"])

    for key in PROFILE_TEXT_FIELDS:
        if key in values:
            cleaned = _clean_text(values.get(key))
            if cleaned is not None:
                profile_values[key] = cleaned

    for field in ARTIST_DEFAULT_FIELDS:
        if field not in values:
            continue
        raw = values.get(field)
        if raw in (None, "", []):
            continue
        _, kind, _, _ = profile.FIELDS_BY_NAME[field]
        try:
            defaults[field] = profile._coerce(kind, raw)
        except Exception:
            continue

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
            "tenant_id": artist["tenant_id"],
            "profile_json": profile_json,
            "defaults_json": defaults_json,
            "assets_json": assets_json,
            "created_at": now,
            "updated_at": now,
        })
    return get(artist_id)


def defaults_for_recording(recording_id):
    """Return persistent artist defaults, then fill gaps from prior real releases."""
    recording = db.query_one(
        "SELECT artist_id, tenant_id FROM recording WHERE id = ?", (recording_id,)
    )
    if recording is None:
        return {}

    stored = get(recording["artist_id"])
    result = {
        key: value for key, value in stored["defaults"].items()
        if key in ARTIST_DEFAULT_FIELDS and value not in (None, "", [])
    }

    rows = db.query(
        "SELECT f.field, f.value_json, f.generated_at "
        "FROM track_profile_field f "
        "JOIN track_profile p ON p.id = f.profile_id "
        "JOIN recording r ON r.id = p.recording_id "
        "WHERE r.artist_id = ? AND r.tenant_id = ? AND r.id != ? "
        "AND r.is_sample = 0 AND f.human_override = 1 "
        "ORDER BY f.generated_at DESC",
        (recording["artist_id"], recording["tenant_id"], recording_id),
    )

    allowed = set(ARTIST_DEFAULT_FIELDS)
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
