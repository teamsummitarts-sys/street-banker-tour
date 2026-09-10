"""Reusable artist-level profile defaults for REACH.

Artist profile values are derived only from prior user-confirmed track-profile
fields for the same artist. They are copied into a new release profile as
explicit inherited defaults, never guessed. Release-specific values such as
BPM, key, explicitness and release narrative are intentionally excluded.
"""

import json

from . import clock, db, profile

SOURCE_ARTIST_PROFILE = "artist_profile"

# Fields that normally describe the artist/brand rather than one recording.
# These are safe to reuse as editable defaults on a new release.
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


def defaults_for_recording(recording_id):
    """Return inherited artist defaults from the newest other real recording."""
    recording = db.query_one(
        "SELECT artist_id, tenant_id FROM recording WHERE id = ?", (recording_id,)
    )
    if recording is None:
        return {}

    rows = db.query(
        "SELECT f.field, f.value_json, f.confidence, f.generated_at "
        "FROM track_profile_field f "
        "JOIN track_profile p ON p.id = f.profile_id "
        "JOIN recording r ON r.id = p.recording_id "
        "WHERE r.artist_id = ? AND r.tenant_id = ? AND r.id != ? "
        "AND r.is_sample = 0 AND f.human_override = 1 "
        "ORDER BY f.generated_at DESC",
        (recording["artist_id"], recording["tenant_id"], recording_id),
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
        if value is not None and value != "" and value != []:
            result[field] = value
    return result


def apply_to_profile(profile_id, recording_id):
    """Populate only currently-UNKNOWN artist fields on a new release profile."""
    inherited = defaults_for_recording(recording_id)
    if not inherited:
        return []

    existing = {
        row["field"]
        for row in db.query(
            "SELECT field FROM track_profile_field WHERE profile_id = ?", (profile_id,)
        )
    }

    applied = []
    for field, value in inherited.items():
        if field in existing or field not in profile.FIELDS_BY_NAME:
            continue
        profile.set_field(
            profile_id,
            field,
            value,
            source=SOURCE_ARTIST_PROFILE,
            confidence=1.0,
        )
        applied.append(field)
    return applied
