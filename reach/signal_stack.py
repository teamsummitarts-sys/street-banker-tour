"""Non-destructive signal reasoning for REACH opportunities.

Signal Stack adds context to the explanation layer before changing score math.
That lets REACH surface useful comparable-artist evidence without silently
re-weighting every opportunity score before enough production data exists to
validate a numeric weight.
"""

from . import comparable_watch, db, netguard, rbac


def comparable_artist_signal(outlet, profile_values):
    """Return recent comparable-artist evidence for the outlet's domain.

    Search results remain signals, not proof of a playlist add or review. The
    caller may use this in explanation text but must not call it verification.
    """
    comparable_watch._ensure_schema()
    refs = {
        str(item).strip().casefold()
        for item in (profile_values.get("comparable_artists") or [])
        if str(item).strip()
    }
    if not refs or not outlet or not outlet["domain"]:
        return None
    domain = netguard.registrable_domain(outlet["domain"])
    if not domain:
        return None

    rows = db.query(
        "SELECT comparable_artist, signal_kind, source_url, title, last_seen_at "
        "FROM comparable_watch_signal WHERE tenant_id = ? AND source_domain = ? "
        "AND state != ? ORDER BY last_seen_at DESC LIMIT 30",
        (rbac.current_principal().tenant_id, domain, comparable_watch.DISMISSED),
    )
    matched = []
    seen = set()
    pickup_count = 0
    sources = []
    for row in rows:
        key = (row["comparable_artist"] or "").strip().casefold()
        if key not in refs:
            continue
        if key not in seen:
            matched.append(row["comparable_artist"])
            seen.add(key)
        if row["signal_kind"] == "PICKUP_SIGNAL":
            pickup_count += 1
        if len(sources) < 3:
            sources.append({
                "artist": row["comparable_artist"],
                "kind": row["signal_kind"],
                "url": row["source_url"],
                "title": row["title"],
                "seen_at": row["last_seen_at"],
            })
    if not matched:
        return None
    return {
        "kind": "COMPARABLE_ARTIST_SIGNAL",
        "count": len(matched),
        "artists": matched[:4],
        "pickup_signal_count": pickup_count,
        "sources": sources,
    }


def radar_stack(artist_id, limit=6):
    """Aggregate watched sources by outlet/domain for the Radar decision layer.

    Repeated appearance across multiple comparable artists rises to the top.
    This remains explanatory context; it does not mutate the REACH score.
    """
    if not artist_id:
        return []
    comparable_watch._ensure_schema()
    tenant_id = rbac.current_principal().tenant_id
    refs = {name.casefold() for name in comparable_watch.comparables(artist_id)}
    if not refs:
        return []
    rows = db.query(
        "SELECT source_domain, comparable_artist, signal_kind, source_url, title, last_seen_at "
        "FROM comparable_watch_signal WHERE tenant_id = ? AND artist_id = ? "
        "AND state != ? AND source_domain IS NOT NULL "
        "ORDER BY last_seen_at DESC LIMIT 200",
        (tenant_id, artist_id, comparable_watch.DISMISSED),
    )
    grouped = {}
    for row in rows:
        artist = (row["comparable_artist"] or "").strip()
        if artist.casefold() not in refs:
            continue
        domain = row["source_domain"]
        item = grouped.setdefault(domain, {
            "domain": domain,
            "artists": [],
            "artist_keys": set(),
            "pickup_signals": 0,
            "sources": 0,
            "latest_at": row["last_seen_at"],
            "latest_url": row["source_url"],
            "latest_title": row["title"],
        })
        key = artist.casefold()
        if key not in item["artist_keys"]:
            item["artists"].append(artist)
            item["artist_keys"].add(key)
        item["sources"] += 1
        if row["signal_kind"] == "PICKUP_SIGNAL":
            item["pickup_signals"] += 1
        if (row["last_seen_at"] or "") > (item["latest_at"] or ""):
            item["latest_at"] = row["last_seen_at"]
            item["latest_url"] = row["source_url"]
            item["latest_title"] = row["title"]
    output = []
    for item in grouped.values():
        item["artist_count"] = len(item.pop("artist_keys"))
        output.append(item)
    output.sort(key=lambda item: (
        -item["artist_count"], -item["pickup_signals"], item["domain"]
    ))
    return output[:limit]


def reason_for(signal):
    if not signal:
        return None
    artists = signal.get("artists") or []
    if len(artists) == 1:
        text = f"This outlet recently surfaced around comparable artist {artists[0]}"
    else:
        text = (
            f"This outlet recently surfaced around {len(artists)} artists "
            f"in your comparable set: {', '.join(artists[:3])}"
        )
    return {
        "sign": "+",
        "text": text,
        "signal": "COMPARABLE_ARTIST_SIGNAL",
        "evidence_count": len(signal.get("sources") or []),
    }
