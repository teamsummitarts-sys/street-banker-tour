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
