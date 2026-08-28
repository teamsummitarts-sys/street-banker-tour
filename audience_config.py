"""Config-driven data for the Audience Analytics page.

The app doesn't track listeners, followers, or demographics, so those are
illustrative — but the listener trend is shaped from the real per-song
monthly trends, and top tracks are the real catalog ranked by streams,
so the page stays anchored to actual data where it can.
"""

from royalty_data import get_songs, get_earnings_trend

# Illustrative audience splits (untracked by the app).
_AGE_BRACKETS = [
    {"label": "18–24", "pct": 34},
    {"label": "25–34", "pct": 38},
    {"label": "35–44", "pct": 16},
    {"label": "45+", "pct": 12},
]
_GEO = [
    {"country": "United States", "flag": "US", "pct": 42},
    {"country": "United Kingdom", "flag": "GB", "pct": 14},
    {"country": "Germany", "flag": "DE", "pct": 11},
    {"country": "Canada", "flag": "CA", "pct": 8},
    {"country": "Australia", "flag": "AU", "pct": 7},
    {"country": "Other", "flag": "··", "pct": 18},
]


def get_audience_data():
    songs = get_songs()
    total_streams = sum(s.streams for s in songs)

    # Shape a monthly-listener trend from the summed per-song trends so the
    # curve reflects real momentum, scaled to a plausible listener count.
    labels = [label for label, _ in get_earnings_trend()]
    summed = [0] * len(labels)
    for s in songs:
        for i, v in enumerate(s.monthly_trend[: len(labels)]):
            summed[i] += v
    scale = 40  # illustrative listeners-per-trend-unit
    trend = [{"label": labels[i], "value": summed[i] * scale} for i in range(len(labels))]
    monthly_listeners = trend[-1]["value"] if trend else 0
    prev = trend[-2]["value"] if len(trend) > 1 else monthly_listeners
    growth_pct = round(((monthly_listeners - prev) / prev) * 100, 1) if prev else 0.0

    top_tracks = sorted(songs, key=lambda s: s.streams, reverse=True)[:5]
    top_tracks = [{"title": s.title, "streams": s.streams} for s in top_tracks]

    return {
        "summary": {
            "monthly_listeners": monthly_listeners,
            "followers": round(monthly_listeners * 0.22),
            "playlist_adds": 230,
            "growth_pct": growth_pct,
            "total_streams": total_streams,
        },
        "trend": trend,
        "age_brackets": _AGE_BRACKETS,
        "geography": _GEO,
        "top_tracks": top_tracks,
    }
