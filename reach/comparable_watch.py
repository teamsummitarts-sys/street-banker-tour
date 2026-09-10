"""Comparable Artist Watch for REACH.

Tracks a small set of comparable artists from the reusable Artist Profile and
records newly surfaced outlet/source signals over time. Search-result evidence
is deliberately labelled SIGNAL, not VERIFIED PICKUP. A signal can be promoted
into a campaign only as DISCOVERED so the normal REACH verification pipeline
still decides whether the outlet is real, relevant and contactable.
"""

from urllib.parse import urlsplit

from . import artist_profile, audit, campaigns, clock, db, entities, netguard, rbac
from .errors import ValidationError
from .providers import search as search_provider

_schema_ready_path = None

SIGNAL = "SIGNAL"
DISMISSED = "DISMISSED"
PROMOTED = "PROMOTED"

_PICKUP_TERMS = (
    "review", "premiere", "interview", "playlist", "radio", "feature",
    "featured", "spotlight", "new music", "track of the", "song of the",
    "rotation", "airplay", "added", "adds",
)


def _ensure_schema():
    global _schema_ready_path
    current = db.current_path()
    if _schema_ready_path == current:
        return
    db.execute(
        "CREATE TABLE IF NOT EXISTS comparable_watch_run ("
        "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, artist_id TEXT NOT NULL, "
        "status TEXT NOT NULL, provider_mode TEXT, searched_artists INTEGER NOT NULL DEFAULT 0, "
        "new_signals INTEGER NOT NULL DEFAULT 0, total_signals INTEGER NOT NULL DEFAULT 0, "
        "created_at TEXT NOT NULL, finished_at TEXT)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS comparable_watch_signal ("
        "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, artist_id TEXT NOT NULL, "
        "comparable_artist TEXT NOT NULL, source_url TEXT NOT NULL, source_domain TEXT, "
        "title TEXT, snippet TEXT, signal_kind TEXT NOT NULL, state TEXT NOT NULL, "
        "first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, last_run_id TEXT, "
        "outlet_id TEXT, target_id TEXT, dismissed_at TEXT)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_comparable_watch_signal "
        "ON comparable_watch_signal(tenant_id, artist_id, comparable_artist, source_url)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS ix_comparable_watch_artist_seen "
        "ON comparable_watch_signal(tenant_id, artist_id, first_seen_at DESC)"
    )
    _schema_ready_path = current


def _owned_artist(artist_id):
    principal = rbac.current_principal()
    row = db.query_one(
        "SELECT id, name FROM artist WHERE id = ? AND tenant_id = ?",
        (artist_id, principal.tenant_id),
    )
    if row is None:
        raise ValidationError("Unknown artist profile")
    return row


def comparables(artist_id):
    profile_data = artist_profile.display(artist_id)
    if not profile_data:
        return []
    values = profile_data.get("defaults") or {}
    result = []
    seen = set()
    for item in values.get("comparable_artists") or []:
        name = str(item).strip()
        key = name.casefold()
        if name and key not in seen:
            result.append(name)
            seen.add(key)
    return result[:5]


def latest_run(artist_id):
    _ensure_schema()
    tenant_id = rbac.current_principal().tenant_id
    return db.query_one(
        "SELECT * FROM comparable_watch_run WHERE tenant_id = ? AND artist_id = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (tenant_id, artist_id),
    )


def due(artist_id, days=7):
    row = latest_run(artist_id)
    if row is None or row["status"] != "SUCCEEDED":
        return True
    elapsed = clock.days_since(row["finished_at"] or row["created_at"])
    return elapsed is None or elapsed >= days


def signals(artist_id, only_new_since=None, include_dismissed=False, limit=60):
    _ensure_schema()
    tenant_id = rbac.current_principal().tenant_id
    sql = (
        "SELECT * FROM comparable_watch_signal WHERE tenant_id = ? AND artist_id = ?"
    )
    params = [tenant_id, artist_id]
    if not include_dismissed:
        sql += " AND state != ?"
        params.append(DISMISSED)
    if only_new_since:
        sql += " AND first_seen_at >= ?"
        params.append(only_new_since)
    sql += " ORDER BY first_seen_at DESC, source_domain, comparable_artist LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def summary(artist_id):
    latest = latest_run(artist_id)
    previous = None
    if latest:
        previous = db.query_one(
            "SELECT * FROM comparable_watch_run WHERE tenant_id = ? AND artist_id = ? "
            "AND created_at < ? ORDER BY created_at DESC LIMIT 1",
            (rbac.current_principal().tenant_id, artist_id, latest["created_at"]),
        )
    new_rows = signals(artist_id, only_new_since=latest["created_at"] if latest else None)
    return {
        "latest": latest,
        "previous": previous,
        "new": new_rows,
        "all": signals(artist_id),
        "due": due(artist_id),
        "comparables": comparables(artist_id),
        "provider_live": search_provider.connected(),
    }


def _signal_kind(title, snippet):
    text = f"{title or ''} {snippet or ''}".casefold()
    return "PICKUP_SIGNAL" if any(term in text for term in _PICKUP_TERMS) else "COVERAGE_SIGNAL"


def _domain(url):
    try:
        validated = netguard.validate_url(url, resolve=False)
        return netguard.registrable_domain(validated["domain"])
    except Exception:
        host = (urlsplit(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host


def run_now(artist_id):
    """Run one bounded live-web snapshot for up to five comparable artists."""
    _ensure_schema()
    artist = _owned_artist(artist_id)
    refs = comparables(artist_id)
    if not refs:
        raise ValidationError("Add comparable artists to the Artist Profile first")
    if not search_provider.connected():
        raise ValidationError(
            "Comparable Artist Watch needs the live REACH search connection; fixture data is never used here"
        )

    principal = rbac.current_principal()
    run_id = db.new_id("cwr")
    started = clock.now_iso()
    db.insert("comparable_watch_run", {
        "id": run_id,
        "tenant_id": principal.tenant_id,
        "artist_id": artist_id,
        "status": "RUNNING",
        "provider_mode": "LIVE",
        "searched_artists": 0,
        "new_signals": 0,
        "total_signals": 0,
        "created_at": started,
        "finished_at": None,
    })

    new_count = 0
    total = 0
    try:
        for reference in refs:
            queries = [
                f'"{reference}" music review interview premiere',
                f'"{reference}" playlist radio feature',
            ]
            seen_urls = set()
            for query in queries:
                response = search_provider.search(query, limit=6)
                for item in response.items:
                    url = (item.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    domain = _domain(url)
                    if not domain or entities.is_platform_domain(domain):
                        continue
                    total += 1
                    existing = db.query_one(
                        "SELECT id, state FROM comparable_watch_signal WHERE tenant_id = ? "
                        "AND artist_id = ? AND comparable_artist = ? AND source_url = ?",
                        (principal.tenant_id, artist_id, reference, url),
                    )
                    now = clock.now_iso()
                    payload = {
                        "source_domain": domain,
                        "title": (item.get("title") or "")[:500],
                        "snippet": (item.get("snippet") or "")[:1400],
                        "signal_kind": _signal_kind(item.get("title"), item.get("snippet")),
                        "last_seen_at": now,
                        "last_run_id": run_id,
                    }
                    if existing:
                        db.update("comparable_watch_signal", existing["id"], payload)
                    else:
                        signal_id = db.new_id("cws")
                        payload.update({
                            "id": signal_id,
                            "tenant_id": principal.tenant_id,
                            "artist_id": artist_id,
                            "comparable_artist": reference,
                            "source_url": url,
                            "state": SIGNAL,
                            "first_seen_at": now,
                            "outlet_id": None,
                            "target_id": None,
                            "dismissed_at": None,
                        })
                        db.insert("comparable_watch_signal", payload)
                        new_count += 1
        finished = clock.now_iso()
        db.update("comparable_watch_run", run_id, {
            "status": "SUCCEEDED",
            "searched_artists": len(refs),
            "new_signals": new_count,
            "total_signals": total,
            "finished_at": finished,
        })
        audit.record(
            "comparable_watch.completed", entity_type="artist", entity_id=artist_id,
            payload={"artist": artist["name"], "comparables": refs,
                     "new_signals": new_count, "total_signals": total},
        )
    except Exception:
        db.update("comparable_watch_run", run_id, {
            "status": "FAILED", "finished_at": clock.now_iso(),
            "searched_artists": len(refs), "new_signals": new_count,
            "total_signals": total,
        })
        raise
    return latest_run(artist_id)


def dismiss(signal_id):
    _ensure_schema()
    principal = rbac.current_principal()
    row = db.query_one(
        "SELECT * FROM comparable_watch_signal WHERE id = ? AND tenant_id = ?",
        (signal_id, principal.tenant_id),
    )
    if row is None:
        raise ValidationError("Unknown comparable-artist signal")
    db.update("comparable_watch_signal", signal_id, {
        "state": DISMISSED, "dismissed_at": clock.now_iso(),
    })
    audit.record("comparable_watch.dismissed", entity_type="comparable_watch_signal",
                 entity_id=signal_id, actor_kind=audit.ACTOR_USER)
    return True


def promote(signal_id, campaign_id):
    """Turn a signal into a DISCOVERED target; normal verification still applies."""
    _ensure_schema()
    principal = rbac.current_principal()
    signal = db.query_one(
        "SELECT * FROM comparable_watch_signal WHERE id = ? AND tenant_id = ?",
        (signal_id, principal.tenant_id),
    )
    if signal is None:
        raise ValidationError("Unknown comparable-artist signal")
    campaign = campaigns.get(campaign_id)
    if campaign is None or campaign["tenant_id"] != principal.tenant_id:
        raise ValidationError("Unknown campaign")

    outlet_id = entities.ensure_outlet(
        name=signal["source_domain"] or signal["title"] or "Comparable artist source",
        url=signal["source_url"],
        domain=signal["source_domain"],
        kind="PUBLICATION",
        provider="comparable_watch",
        description=(
            f"Comparable artist signal for {signal['comparable_artist']}: "
            f"{signal['title'] or signal['snippet'] or signal['source_url']}"
        )[:1200],
    )
    target_id = campaigns.add_target(
        campaign_id,
        outlet_id,
        status=campaigns.DISCOVERED,
        dedup_key=entities.dedup_key(outlet_id),
        reason=f"Comparable artist signal: {signal['comparable_artist']}",
    )
    db.update("comparable_watch_signal", signal_id, {
        "state": PROMOTED, "outlet_id": outlet_id, "target_id": target_id,
        "last_seen_at": clock.now_iso(),
    })
    audit.record(
        "comparable_watch.promoted", entity_type="campaign_target", entity_id=target_id,
        payload={"signal_id": signal_id, "comparable_artist": signal["comparable_artist"],
                 "campaign_id": campaign_id}, actor_kind=audit.ACTOR_USER,
    )
    return target_id
