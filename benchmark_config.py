"""Config-driven data for the Benchmarking page.

Compares the artist's real catalog metrics against illustrative peer
averages for artists at a similar stage, so each metric shows whether
you're ahead of or behind the pack. Your own numbers are real; the peer
averages are illustrative reference points.
"""

from royalty_data import get_songs, estimate_catalog_value, get_earnings_trend


def _pct_diff(you, peer):
    if not peer:
        return 0.0
    return round((you - peer) / peer * 100, 1)


def get_benchmark_data():
    songs = get_songs()
    total_streams = sum(s.streams for s in songs)
    total_earned = sum(s.total_earned for s in songs)
    avg_per_track = round(total_earned / len(songs), 2) if songs else 0.0
    catalog_value = estimate_catalog_value(get_earnings_trend())["mid"]

    # Illustrative peer averages for a similar-stage independent artist.
    metrics = [
        {"label": "Total streams", "you": total_streams, "peer": 9_500_000, "fmt": "int"},
        {"label": "Catalog earnings", "you": round(total_earned, 2), "peer": 14_500, "fmt": "money"},
        {"label": "Avg. earnings / track", "you": avg_per_track, "peer": 2_400, "fmt": "money"},
        {"label": "Est. catalog value", "you": round(catalog_value, 2), "peer": 240_000, "fmt": "money"},
        {"label": "Catalog size", "you": len(songs), "peer": 8, "fmt": "int"},
    ]
    for m in metrics:
        m["diff_pct"] = _pct_diff(m["you"], m["peer"])
        m["ahead"] = m["you"] >= m["peer"]

    ahead = sum(1 for m in metrics if m["ahead"])
    return {
        "summary": {
            "metrics": len(metrics),
            "ahead": ahead,
            "behind": len(metrics) - ahead,
            "peer_group": "Independent · Electronic/Synth-pop",
        },
        "metrics": metrics,
    }
