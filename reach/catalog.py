"""Canonical music identity — REACH's own catalog.

This is the source of truth for the tracks REACH works with. It is not a mirror
of another application's catalog and it does not import one: the ``recording``
table holds the tracks the rights holder entered here, and every campaign,
evidence record and placement hangs off a row in it.

Different remixes, edits, remasters, clean versions and instrumentals are
distinct recordings. An ISRC identifies a recording; it never proves ownership,
which is why :func:`attest_rights` exists separately.
"""

import json
import os

from . import audit, clock, db, rbac, tracks
from .errors import ValidationError

SEED_SAMPLE_ENV = "REACH_SEED_SAMPLE_TRACKS"

ORIGINAL = "ORIGINAL"
VERSION_TYPES = [
    ORIGINAL, "RADIO_EDIT", "EXTENDED_MIX", "REMIX", "REMASTER",
    "INSTRUMENTAL", "CLEAN", "ACOUSTIC", "LIVE", "VIDEO",
]

RIGHTS_SCOPE = [
    "master_recording", "artwork", "photographs", "biography",
    "video", "epk_assets", "names_and_likenesses", "submission_materials",
]


def _artist_id(tenant_id, name):
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
        "name": name,
        "created_at": clock.now_iso(),
    })
    return artist_id


def _slugify(title):
    keep = [c.lower() if c.isalnum() else "-" for c in (title or "").strip()]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "untitled"


def _optional_text(values, key):
    value = values.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _optional_bool(values, key):
    value = values.get(key)
    if value in (None, "", "UNKNOWN"):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in ("1", "true", "yes", "on", "explicit") else 0


def _asset_items(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    return raw if isinstance(raw, list) else []


def add_track(values, tenant_id=None, artist_name=None, is_sample=False, slug=None):
    """Add a recording and persist the artist/release context supplied with it.

    The create-campaign wizard may send both reusable artist profile defaults
    and release-specific values. Artist defaults are saved once and inherited
    by later releases; release-specific fields stay attached to this recording.
    Unknown values remain unknown.
    """
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    columns = tracks.columns(values)
    if not columns["title"]:
        raise ValidationError("A track needs a title")
    artist_name = (artist_name or values.get("artist_name") or "").strip()
    if not artist_name:
        raise ValidationError("A track needs an artist name")

    slug = slug or _slugify(columns["title"])
    existing = db.query_one(
        "SELECT id FROM recording WHERE tenant_id = ? AND slug = ? AND version_type = ? "
        "AND mix_name IS NULL AND edit_name IS NULL",
        (tenant_id, slug, ORIGINAL),
    )
    if existing:
        raise ValidationError(f"A track with the identifier {slug!r} is already in the catalog")

    artist_id = _artist_id(tenant_id, artist_name)
    recording_id = db.new_id("rec")
    row = {
        "id": recording_id,
        "tenant_id": tenant_id,
        "artist_id": artist_id,
        "release_id": None,
        "slug": slug,
        "musicbrainz_recording_id": None,
        "version_type": ORIGINAL,
        "mix_name": None,
        "edit_name": None,
        "explicit": _optional_bool(values, "explicit"),
        "duration_seconds": None,
        "master_version": 1,
        "release_territory": _optional_text(values, "release_territory"),
        "release_date": _optional_text(values, "release_date"),
        "is_sample": 1 if is_sample else 0,
        "created_at": clock.now_iso(),
    }
    row.update(columns)
    # tracks.columns does not own these release identity columns. Preserve the
    # values supplied by the wizard after its generic mapping is applied.
    row["explicit"] = _optional_bool(values, "explicit")
    row["release_territory"] = _optional_text(values, "release_territory")
    row["release_date"] = _optional_text(values, "release_date")
    db.insert("recording", row)

    if not is_sample:
        from . import artist_profile, profile as track_profile, release_credits

        # Save reusable artist defaults before building the recording profile,
        # so this release immediately sees those values in its editable fields.
        artist_profile.save(artist_id, values)
        profile_id = track_profile.get_or_create(recording_id)
        for field in track_profile.FIELDS_BY_NAME:
            if field not in values or values.get(field) in (None, "", []):
                continue
            track_profile.set_field(profile_id, field, values.get(field))

        # Guest artist billing is release-specific. It must never leak into the
        # reusable primary Artist Profile.
        if "featured_artists" in values:
            release_credits.set_featured_artists(
                recording_id, values.get("featured_artists"), tenant_id
            )

        # Files themselves already live in V2 Vault/blob storage. REACH stores
        # only associations, so one upload can be reused without duplicating bytes.
        for item in _asset_items(values.get("release_assets")):
            if isinstance(item, str):
                path, kind, label = item.strip(), "file", None
            elif isinstance(item, dict):
                path = str(item.get("path") or "").strip()
                kind = str(item.get("kind") or "file").strip()
                label = str(item.get("label") or "").strip() or None
            else:
                continue
            if path:
                add_platform_asset(recording_id, f"reach_upload:{kind}", external_id=label, url=path)

        for provider, key in (
            ("spotify", "release_spotify_url"),
            ("apple_music", "release_apple_url"),
            ("youtube", "release_youtube_url"),
            ("soundcloud", "release_soundcloud_url"),
        ):
            url = _optional_text(values, key)
            if url:
                add_platform_asset(recording_id, provider, url=url)

        audit.record("catalog.track_added", entity_type="recording", entity_id=recording_id,
                     payload={"title": columns["title"], "artist": artist_name})
    return recording_id


def delete_track(recording_id):
    """Remove a recording that no campaign depends on."""
    row = get_recording(recording_id)
    if row is None:
        raise ValidationError("Unknown recording")
    used = db.query_one("SELECT id FROM campaign WHERE recording_id = ? LIMIT 1", (recording_id,))
    if used:
        raise ValidationError("This track has campaign history and cannot be deleted")
    from . import release_credits
    release_credits.delete_for_recording(recording_id)
    db.execute("DELETE FROM platform_asset WHERE recording_id = ?", (recording_id,))
    db.execute("DELETE FROM rights_attestation WHERE recording_id = ?", (recording_id,))
    db.execute("DELETE FROM recording WHERE id = ?", (recording_id,))
    audit.record("catalog.track_deleted", entity_type="recording", entity_id=recording_id,
                 payload={"title": row["title"]})
    return True


def seed_sample_tracks(tenant_id=None):
    """Seed the sample catalog, once, only into an empty catalog."""
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    if os.environ.get(SEED_SAMPLE_ENV, "1") == "0":
        return []
    existing = db.query_one(
        "SELECT id FROM recording WHERE tenant_id = ? LIMIT 1", (tenant_id,)
    )
    if existing:
        return []
    created = []
    for entry in tracks.SAMPLE_TRACKS:
        recording_id = db.new_id("rec")
        row = {
            "id": recording_id,
            "tenant_id": tenant_id,
            "artist_id": _artist_id(tenant_id, tracks.SAMPLE_ARTIST),
            "release_id": None,
            "slug": entry["slug"],
            "musicbrainz_recording_id": None,
            "version_type": ORIGINAL,
            "mix_name": None,
            "edit_name": None,
            "explicit": None,
            "duration_seconds": None,
            "master_version": 1,
            "release_territory": None,
            "release_date": None,
            "is_sample": 1,
            "created_at": clock.now_iso(),
        }
        row.update(tracks.sample_columns(entry))
        db.insert("recording", row)
        created.append(recording_id)
    return created


def ensure_catalog(tenant_id=None):
    """Idempotent catalog start-up. Safe to call on every request."""
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    rbac.ensure_default_tenant()
    return seed_sample_tracks(tenant_id)


def recordings(tenant_id=None):
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    ensure_catalog(tenant_id)
    return db.query(
        "SELECT r.*, a.name AS artist_name FROM recording r "
        "JOIN artist a ON a.id = r.artist_id WHERE r.tenant_id = ? ORDER BY r.title",
        (tenant_id,),
    )


def get_recording(recording_id):
    return db.query_one(
        "SELECT r.*, a.name AS artist_name FROM recording r "
        "JOIN artist a ON a.id = r.artist_id WHERE r.id = ?",
        (recording_id,),
    )


def recording_by_slug(slug, tenant_id=None):
    tenant_id = tenant_id or rbac.current_principal().tenant_id
    ensure_catalog(tenant_id)
    return db.query_one(
        "SELECT r.*, a.name AS artist_name FROM recording r "
        "JOIN artist a ON a.id = r.artist_id "
        "WHERE r.tenant_id = ? AND r.slug = ? AND r.version_type = ?",
        (tenant_id, slug, ORIGINAL),
    )


def track(recording_row):
    """The first-party facts REACH holds about this recording."""
    return tracks.from_row(recording_row)


def add_version(source_recording_id, version_type, mix_name=None, edit_name=None,
                isrc=None, explicit=None):
    """Register a distinct recording entity for a remix/edit/version."""
    if version_type not in VERSION_TYPES:
        raise ValidationError(f"Unknown version type: {version_type}")
    source = get_recording(source_recording_id)
    if source is None:
        raise ValidationError("Unknown source recording")
    recording_id = db.new_id("rec")
    db.insert("recording", {
        "id": recording_id,
        "tenant_id": source["tenant_id"],
        "artist_id": source["artist_id"],
        "release_id": source["release_id"],
        "slug": source["slug"],
        "title": source["title"],
        "isrc": isrc,
        "iswc": source["iswc"],
        "upc": source["upc"],
        "musicbrainz_recording_id": None,
        "version_type": version_type,
        "mix_name": mix_name,
        "edit_name": edit_name,
        "explicit": explicit,
        "duration_seconds": None,
        "master_version": 0,
        "release_territory": source["release_territory"],
        "release_date": source["release_date"],
        "created_at": clock.now_iso(),
    })
    from . import release_credits
    source_featured = release_credits.featured_artists(
        source_recording_id, source["tenant_id"]
    )
    if source_featured:
        release_credits.set_featured_artists(
            recording_id, source_featured, source["tenant_id"]
        )
    audit.record("catalog.version_added", entity_type="recording", entity_id=recording_id,
                 payload={"version_type": version_type, "source": source_recording_id})
    return recording_id


def add_platform_asset(recording_id, provider, external_id=None, url=None):
    asset_id = db.new_id("asset")
    db.insert("platform_asset", {
        "id": asset_id,
        "recording_id": recording_id,
        "provider": provider,
        "external_id": external_id,
        "url": url,
        "created_at": clock.now_iso(),
    })
    return asset_id


def platform_assets(recording_id):
    return db.query(
        "SELECT * FROM platform_asset WHERE recording_id = ? ORDER BY provider",
        (recording_id,),
    )


def identifiers(recording_id):
    """Everything REACH knows that identifies this recording."""
    row = get_recording(recording_id)
    if row is None:
        return {}
    assets = platform_assets(recording_id)
    return {
        "internal_recording_id": row["id"],
        "internal_track_id": row["slug"],
        "isrc": row["isrc"],
        "iswc": row["iswc"],
        "upc": row["upc"],
        "musicbrainz_recording_id": row["musicbrainz_recording_id"],
        "musicbrainz_release_id": None,
        "version_type": row["version_type"],
        "mix_name": row["mix_name"],
        "edit_name": row["edit_name"],
        "explicit": row["explicit"],
        "master_version": bool(row["master_version"]),
        "release_territory": row["release_territory"],
        "release_date": row["release_date"],
        "platform_assets": [dict(a) for a in assets],
    }


# --------------------------------------------------------------------------
# rights attestation
# --------------------------------------------------------------------------

ATTESTATION_STATEMENT = (
    "I confirm that the campaign owner holds or controls the rights necessary to use the "
    "master recording, artwork, photographs, biography, video, EPK assets, names and "
    "likenesses, and submission materials for this recording in promotional outreach."
)


def attest_rights(recording_id, scope=None, attested_by=None):
    """Record a rights attestation. A campaign cannot launch without one."""
    principal = rbac.require("campaign.create")
    scope = scope or list(RIGHTS_SCOPE)
    unknown = [item for item in scope if item not in RIGHTS_SCOPE]
    if unknown:
        raise ValidationError(f"Unknown rights scope: {', '.join(unknown)}")
    attestation_id = db.new_id("rights")
    db.insert("rights_attestation", {
        "id": attestation_id,
        "tenant_id": principal.tenant_id,
        "recording_id": recording_id,
        "attested_by": attested_by or principal.email,
        "scope_json": json.dumps(sorted(scope)),
        "statement": ATTESTATION_STATEMENT,
        "attested_at": clock.now_iso(),
        "revoked_at": None,
    })
    audit.record("rights.attested", entity_type="recording", entity_id=recording_id,
                 payload={"scope": sorted(scope)}, actor_kind=audit.ACTOR_USER,
                 actor_id=principal.id)
    return attestation_id


def active_attestation(recording_id):
    return db.query_one(
        "SELECT * FROM rights_attestation WHERE recording_id = ? AND revoked_at IS NULL "
        "ORDER BY attested_at DESC LIMIT 1",
        (recording_id,),
    )


def has_rights_attestation(recording_id):
    return active_attestation(recording_id) is not None


# --------------------------------------------------------------------------
# release readiness
# --------------------------------------------------------------------------

def release_readiness(recording_id):
    """Checks that gate what a campaign can actually do."""
    row = get_recording(recording_id)
    facts = track(row)
    checks = []

    def add(key, label, ok, consequence):
        checks.append({"key": key, "label": label, "ok": bool(ok), "consequence": consequence})

    add("isrc", "ISRC on file", bool(row["isrc"]),
        "Placement monitoring and several submission forms require an ISRC.")
    add("upc", "UPC on file", bool(row["upc"]),
        "Release-level pitches (Amazon, Pandora) require a UPC.")
    add("distribution", "Delivered through a distributor",
        bool(facts and facts.distributed),
        "DSP editorial pitches require the release to be delivered.")
    add("rights", "Rights attestation recorded", has_rights_attestation(recording_id),
        "No campaign may launch without one.")
    add("writers", "Writers on file", bool(facts and facts.writers),
        "Credits are required by most editorial and radio submission forms.")
    add("publisher", "Publisher on file", bool(facts and facts.publisher),
        "Some publications ask for publishing information.")
    add("splits", "Splits confirmed", bool(facts and facts.splits_confirmed),
        "Unconfirmed splits put placement revenue at risk.")

    passed = sum(1 for c in checks if c["ok"])
    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "score": round(passed / len(checks) * 100) if checks else 0,
        "blocking": [c for c in checks if not c["ok"] and c["key"] == "rights"],
    }
