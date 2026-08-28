"""The vault, counted from the files that are actually in it.

/documents had two halves that disagreed with each other. The top was
real: the artist's own uploads, stored, listed, deletable. Everything
below it came from `_DOCUMENT_PRESENCE`, five invented song ids mapped
to sets of paperwork - "Vault Completeness 34%", "Songs Tracked 5",
"Missing Documents 19", and a per-song grid of green ticks for split
sheets nobody had ever uploaded. Uploading a real document moved none
of it, because nothing downstream read the documents table.

The gap was structural, not cosmetic: documents had no song on them, so
per-song coverage could not be computed even in principle. This adds
that column and computes the page from it.

  Tracks come from the account's own catalog, its Artist OS tracks, and
  the titles on its uploaded statements - a track that is earning money
  is a track whose paperwork matters, whether or not it was entered by
  hand anywhere.

  Coverage is attached documents over the paperwork this app knows to
  ask for. That is a checklist, not a legal standard, and the page says
  so: a complete vault here means every file this product asked for,
  not that the rights are clean.

Documents filed against the account rather than a single recording -
distribution deals, publishing agreements - are counted for the account
and are not held against any track's coverage.
"""

import db as store


# The paperwork that decides who gets paid for a specific recording.
# Deliberately short: a checklist nobody finishes is a checklist nobody
# reads, and every item here is one an artist can actually produce.
PER_TRACK_TYPES = ["Split Agreement", "Producer Agreement", "Feature Agreement"]

# Paperwork that covers the whole catalog rather than one recording.
CATALOG_TYPES = ["Distribution", "Publishing", "Registration"]


def _norm(title):
    return " ".join((title or "").split()).strip().lower()


def known_tracks(user_id):
    """Every recording this account has named, from any real source."""
    seen = {}
    for t in store.get_catalog_tracks(user_id):
        title = (t.get("title") or "").strip()
        if title:
            seen.setdefault(_norm(title), {"title": title, "sources": set()})
            seen[_norm(title)]["sources"].add("catalog")
    try:
        os_tracks = store.list_os_tracks(user_id)
    except Exception:
        os_tracks = []
    for t in os_tracks:
        title = (t.get("title") or "").strip()
        if title:
            seen.setdefault(_norm(title), {"title": title, "sources": set()})
            seen[_norm(title)]["sources"].add("os")
    for r in store.get_statement_rows(user_id):
        title = (r.get("title") or "").strip()
        if title:
            seen.setdefault(_norm(title), {"title": title, "sources": set()})
            seen[_norm(title)]["sources"].add("statements")
    out = [{"title": v["title"], "key": k, "sources": sorted(v["sources"])}
           for k, v in seen.items()]
    out.sort(key=lambda t: t["title"].lower())
    return out


def build(user_id):
    """The whole /documents page for one account. Never seed data."""
    docs = store.list_documents(user_id) if user_id else []
    tracks = known_tracks(user_id) if user_id else []

    by_type = {}
    for d in docs:
        by_type.setdefault(d.get("doc_type") or "Other", []).append(d)

    # Documents naming a recording, keyed by that recording.
    per_track_docs = {}
    unmatched = []
    track_keys = {t["key"] for t in tracks}
    for d in docs:
        key = _norm(d.get("track"))
        if not key:
            continue
        per_track_docs.setdefault(key, []).append(d)
        if key not in track_keys:
            unmatched.append(d)

    entries = []
    covered_slots = 0
    for t in tracks:
        mine = per_track_docs.get(t["key"], [])
        have = {d.get("doc_type") for d in mine}
        types = [{"type": ty, "present": ty in have} for ty in PER_TRACK_TYPES]
        covered_slots += sum(1 for ty in types if ty["present"])
        entries.append({
            "title": t["title"],
            "key": t["key"],
            "sources": t["sources"],
            "documents": mine,
            "types": types,
            "missing": [ty["type"] for ty in types if not ty["present"]],
            "missing_count": sum(1 for ty in types if not ty["present"]),
        })
    entries.sort(key=lambda e: (-e["missing_count"], e["title"].lower()))

    total_slots = len(tracks) * len(PER_TRACK_TYPES)
    catalog_cover = [{"type": ty, "count": len(by_type.get(ty, []))}
                     for ty in CATALOG_TYPES]

    return {
        "docs": docs,
        "doc_count": len(docs),
        "tracks": tracks,
        "entries": entries,
        "has_tracks": bool(tracks),
        "has_docs": bool(docs),
        "covered_slots": covered_slots,
        "total_slots": total_slots,
        # None, not 0: with no tracks named there is no denominator, and
        # 0% would read as a failing grade for work nobody was asked for.
        "coverage_pct": (round(100 * covered_slots / total_slots)
                         if total_slots else None),
        "catalog_cover": catalog_cover,
        "catalog_missing": [c["type"] for c in catalog_cover if not c["count"]],
        "unfiled": [d for d in docs if not _norm(d.get("track"))],
        # Filed against a title the account no longer names anywhere.
        "unmatched": unmatched,
        "by_type": by_type,
    }
