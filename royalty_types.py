"""Royalty-type classification over real statement rows.

Statement sources are classified into royalty streams (performance/
publishing, mechanical, neighboring rights, recording/streaming) so the
per-type Sweep pages show the artist's actual money by stream — and,
just as honestly, which streams show nothing, since a missing stream
usually means an uncollected one.
"""

import db as store

# Source-name fragments -> royalty stream. Compared lowercased.
_BUCKETS = [
    ("publishing", ("ascap", "bmi", "sesac", "gmr", "prs", "socan", "gema",
                    "apra", "sacem", "songtrust", "sentric", "publishing",
                    "performance royalt")),
    ("mechanical", ("mlc", "harry fox", "hfa", "mechanical", "cmrra")),
    ("neighboring", ("soundexchange", "ppl", "neighbouring", "neighboring",
                     "re:sound", "resound")),
    ("recording", ("spotify", "apple", "itunes", "amazon", "deezer", "tidal",
                   "youtube", "pandora", "soundcloud", "napster", "boomplay",
                   "distrokid", "tunecore", "cd baby", "distribution",
                   "bandcamp", "beatport", "meta", "tiktok", "facebook",
                   "instagram", "snap")),
]

LABELS = {
    "publishing": "Performance / Publishing",
    "mechanical": "Mechanical",
    "neighboring": "Neighboring Rights",
    "recording": "Recording / Streaming",
    "other": "Unclassified",
}

# What the absence of a stream usually means, and where to start.
GUIDANCE = {
    "publishing": ("No performance or publishing income appears in your uploaded "
                   "statements. If your songs are streamed or played publicly, this "
                   "money exists — it's collected by a PRO (ASCAP, BMI, SESAC) or a "
                   "publishing admin (Songtrust, Sentric). Registering your works is "
                   "how you claim it."),
    "mechanical": ("No mechanical royalties appear in your statements. In the US, "
                   "The MLC pays streaming mechanicals to registered songwriters — "
                   "if you write your own songs and aren't registered, that money "
                   "accrues unclaimed."),
    "neighboring": ("No neighboring-rights income appears in your statements. "
                    "SoundExchange collects US digital-radio royalties (Pandora, "
                    "SiriusXM, webcast) for performers and master owners — a free "
                    "registration many independent artists never file."),
    "recording": ("No streaming or recording income appears in your statements yet. "
                  "This stream arrives through your distributor — upload their "
                  "statements and every page in the money engine fills in."),
}


def classify(source):
    s = (source or "").lower()
    for bucket, needles in _BUCKETS:
        if any(n in s for n in needles):
            return bucket
    return "other"


def type_report(user_id, bucket):
    """Real totals for one royalty stream: sources, periods, top tracks."""
    rows = [r for r in store.get_statement_rows(user_id)
            if classify(r.get("source")) == bucket]
    total = round(sum(r["amount"] for r in rows), 2)
    sources, periods, tracks = {}, {}, {}
    for r in rows:
        sources[r["source"]] = sources.get(r["source"], 0.0) + r["amount"]
        if r.get("period"):
            periods[r["period"]] = periods.get(r["period"], 0.0) + r["amount"]
        title = r.get("title") or "(untitled)"
        tracks[title] = tracks.get(title, 0.0) + r["amount"]
    return {
        "bucket": bucket,
        "label": LABELS[bucket],
        "rows": len(rows),
        "total": total,
        "sources": sorted(sources.items(), key=lambda x: -x[1]),
        "periods": sorted(periods.items()),
        "top_tracks": sorted(tracks.items(), key=lambda x: -x[1])[:8],
        "guidance": GUIDANCE.get(bucket, ""),
    }


def territory_report(user_id):
    """Territory breakdown for statements that carry a territory column."""
    rows = store.get_statement_rows(user_id)
    with_territory = [r for r in rows if (r.get("territory") or "").strip()]
    territories = {}
    for r in with_territory:
        t = r["territory"].strip().upper()
        territories[t] = territories.get(t, 0.0) + r["amount"]
    return {
        "total_rows": len(rows),
        "covered_rows": len(with_territory),
        "total": round(sum(r["amount"] for r in with_territory), 2),
        "territories": sorted(territories.items(), key=lambda x: -x[1]),
    }
