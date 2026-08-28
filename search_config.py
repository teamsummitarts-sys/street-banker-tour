"""Global search over the signed-in artist's own catalog.

It used to search royalty_data._SONGS and disputes_config._seed(), both
hardcoded. Typing "midnight" returned "Midnight Drive · ISRC
USRC12345678"; typing "mlc" returned a $640 dispute against The MLC - to
an artist who had neither. Results that look like your records but
belong to nobody are worse than no results, because search is where
people go to confirm a thing exists.

Now it reads statement rows and disputes for one user_id. The demo
account keeps the seeded catalog, because the tour needs something to
find.
"""

import db as store


def _demo_search(q):
    """The previous behaviour, kept for the showcase account only."""
    from royalty_data import get_songs, get_platform_catalog, get_claims
    from disputes_config import get_disputes_data

    groups = []
    q = q.lower()

    # Songs (title / ISRC / writers).
    song_hits = []
    for s in get_songs():
        hay = " ".join([s.title, s.isrc or "", s.iswc or "", " ".join(s.writers)]).lower()
        if q in hay:
            song_hits.append({"label": s.title, "sub": "Song · " + (s.isrc or "no ISRC"), "route": "/catalog"})
    if song_hits:
        groups.append({"type": "Songs", "entries": song_hits})

    # Connected sources / platforms.
    catalog = get_platform_catalog()
    source_hits = [
        {"label": p.platform, "sub": "Source · " + p.status.replace("_", " "), "route": "/connections"}
        for p in catalog if q in p.platform.lower()
    ]
    if source_hits:
        groups.append({"type": "Sources", "entries": source_hits})

    # Claims.
    claim_hits = [
        {"label": c.issue_type, "sub": "Claim · " + c.source, "route": "/recovery"}
        for c in get_claims(catalog)
        if q in c.issue_type.lower() or q in c.source.lower()
    ]
    if claim_hits:
        groups.append({"type": "Claims", "entries": claim_hits})

    # Disputes.
    dispute_hits = [
        {"label": d["title"], "sub": "Dispute · " + d["counterparty"], "route": "/disputes"}
        for d in get_disputes_data()["disputes"]
        if q in d["title"].lower() or q in d["counterparty"].lower() or (d.get("song") and q in d["song"].lower())
    ]
    if dispute_hits:
        groups.append({"type": "Disputes", "entries": dispute_hits})

    return groups


def search(query, user_id=None, demo=False):
    """Real accounts search their own statements and disputes.

    `demo` defaults to False, so a caller that forgets the flag gets an
    honest empty result rather than a stranger's catalog.
    """
    q = (query or "").strip().lower()
    if not q:
        return {"query": "", "groups": [], "total": 0, "is_demo": bool(demo)}

    if demo:
        groups = _demo_search(q)
        return {"query": query, "groups": groups, "is_demo": True,
                "total": sum(len(g["entries"]) for g in groups)}

    groups = []
    rows = store.get_statement_rows(user_id) if user_id else []

    tracks, sources = {}, {}
    for r in rows:
        title = (r.get("title") or "").strip()
        src = (r.get("source") or "").strip()
        if title:
            tracks.setdefault(title, set()).add(src)
        if src:
            sources[src] = sources.get(src, 0.0) + (r.get("amount") or 0)

    hits = [{"label": t,
             "sub": "Track · paid by %d source%s"
                    % (len(s), "" if len(s) == 1 else "s"),
             "route": "/catalog"}
            for t, s in sorted(tracks.items()) if q in t.lower()]
    if hits:
        groups.append({"type": "Tracks", "entries": hits})

    hits = [{"label": s, "sub": "Source · $%s tracked" % format(amt, ",.2f"),
             "route": "/royalties"}
            for s, amt in sorted(sources.items()) if q in s.lower()]
    if hits:
        groups.append({"type": "Sources", "entries": hits})

    if user_id:
        try:
            mine = store.list_disputes(user_id)
        except Exception:
            mine = []
        hits = [{"label": d.get("title") or "(untitled)",
                 "sub": "Dispute · " + (d.get("counterparty") or "—"),
                 "route": "/disputes"}
                for d in mine
                if q in (d.get("title") or "").lower()
                or q in (d.get("counterparty") or "").lower()]
        if hits:
            groups.append({"type": "Disputes", "entries": hits})

    return {"query": query, "groups": groups, "is_demo": False,
            "searched_rows": len(rows),
            "total": sum(len(g["entries"]) for g in groups)}
