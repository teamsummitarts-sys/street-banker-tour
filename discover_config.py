"""
Config-driven data for the fan-facing Discover section.

A music-fan experience (the "Continue as a Fan" side): browse new music by
genre and mood, see trending tracks, new releases, artist spotlights, and
featured playlists. Likes and follows are held in module-level session
state (reset on restart). Tracks reference real network artists and
catalog titles; play counts and cover gradients are illustrative.
"""

import os

from royalty_data import get_songs

GENRES = ["Synthwave", "Electronic", "House", "Techno", "Pop",
          "Hip-Hop", "R&B", "Indie", "Ambient"]

# Mood tiles (name + gradient art).
MOODS = [
    {"id": "late-night", "name": "Late Night", "from": "#1e1b4b", "to": "#0f172a"},
    {"id": "energetic", "name": "Energetic", "from": "#7f1d1d", "to": "#b45309"},
    {"id": "chill", "name": "Chill", "from": "#0e7490", "to": "#0f172a"},
    {"id": "focus", "name": "Focus", "from": "#064e3b", "to": "#0c0a09"},
    {"id": "feel-good", "name": "Feel Good", "from": "#a16207", "to": "#b91c1c"},
    {"id": "heartbreak", "name": "Heartbreak", "from": "#831843", "to": "#1e3a8a"},
]

# Curated track feed. artist_id links to a /network profile where one exists.
_TRACKS = [
    {"id": "tr-1", "art": "/static/img/discover/tr-1.jpg", "title": "Midnight Drive", "artist": "Nova Reign", "artist_id": "nova-reign", "genre": "Synthwave", "mood": "late-night", "plays": 5200000, "from": "#1e1b4b", "to": "#0f172a", "new": False},
    {"id": "tr-2", "art": "/static/img/discover/tr-2.jpg", "title": "Neon Dreams", "artist": "Nova Reign", "artist_id": "nova-reign", "genre": "Synthwave", "mood": "late-night", "plays": 3100000, "from": "#312e81", "to": "#0f172a", "new": True},
    {"id": "tr-3", "art": "/static/img/discover/tr-3.jpg", "title": "Afterglow", "artist": "Sable Wynn", "artist_id": "sable-wynn", "genre": "R&B", "mood": "heartbreak", "plays": 980000, "from": "#831843", "to": "#1e3a8a", "new": True},
    {"id": "tr-4", "art": "/static/img/discover/tr-4.jpg", "title": "Warehouse Set", "artist": "DJ Codec", "artist_id": "dj-codec", "genre": "Techno", "mood": "energetic", "plays": 640000, "from": "#7f1d1d", "to": "#18181b", "new": False},
    {"id": "tr-5", "art": "/static/img/discover/tr-5.jpg", "title": "Chrome Hearts", "artist": "Kilo Byte", "artist_id": "kilo-byte", "genre": "Electronic", "mood": "energetic", "plays": 410000, "from": "#0e7490", "to": "#0f172a", "new": True},
    {"id": "tr-6", "art": "/static/img/discover/tr-6.jpg", "title": "Glass Horizon", "artist": "Grid Runner", "artist_id": "grid-runner", "genre": "Synthwave", "mood": "focus", "plays": 220000, "from": "#064e3b", "to": "#0c0a09", "new": True},
    {"id": "tr-7", "art": "/static/img/discover/tr-7.jpg", "title": "Velvet Static", "artist": "Sable Wynn", "artist_id": "sable-wynn", "genre": "R&B", "mood": "chill", "plays": 175000, "from": "#3b0764", "to": "#111827", "new": False},
    {"id": "tr-8", "art": "/static/img/discover/tr-8.jpg", "title": "City Lights", "artist": "Nova Reign", "artist_id": "nova-reign", "genre": "Pop", "mood": "feel-good", "plays": 1250000, "from": "#a16207", "to": "#7c2d12", "new": False},
    {"id": "tr-9", "art": "/static/img/discover/tr-9.jpg", "title": "Deep Current", "artist": "Marco Velocity", "artist_id": "marco-velocity", "genre": "House", "mood": "chill", "plays": 320000, "from": "#155e75", "to": "#0f172a", "new": True},
    {"id": "tr-10", "title": "Paper Planes", "artist": "Lila Rose", "artist_id": "lila-rose", "genre": "Pop", "mood": "feel-good", "plays": 88000, "from": "#b45309", "to": "#7c2d12", "new": True},
    {"id": "tr-11", "title": "Low Tide", "artist": "Cass Oram", "artist_id": "cass-oram", "genre": "Ambient", "mood": "focus", "plays": 54000, "from": "#0f766e", "to": "#0c0a09", "new": False},
    {"id": "tr-12", "title": "Backstreet Gold", "artist": "Milo Tran", "artist_id": "milo-tran", "genre": "Hip-Hop", "mood": "energetic", "plays": 210000, "from": "#7c2d12", "to": "#18181b", "new": True},
]

# --- Session state (reset on restart) ---------------------------------------
_likes = set()      # track ids
_follows = set()    # artist ids


def reset_discover_state():
    _likes.clear()
    _follows.clear()


def like_track(track_id):
    if not any(t["id"] == track_id for t in _TRACKS):
        return None
    if track_id in _likes:
        _likes.discard(track_id)
        return {"liked": False, "count": len(_likes)}
    _likes.add(track_id)
    return {"liked": True, "count": len(_likes)}


def follow_artist(artist_id):
    if artist_id in _follows:
        _follows.discard(artist_id)
        return {"following": False, "count": len(_follows)}
    _follows.add(artist_id)
    return {"following": True, "count": len(_follows)}


def _fmt_plays(n):
    if n >= 1_000_000:
        return ("%.1fM" % (n / 1_000_000)).replace(".0M", "M")
    if n >= 1_000:
        return "%dK" % (n / 1_000)
    return str(n)


def _decorate_track(t):
    return {**t, "liked": t["id"] in _likes, "plays_fmt": _fmt_plays(t["plays"])}


def get_discover_data(args=None):
    args = args or {}
    genre = args.get("genre") or "All"
    mood = args.get("mood") or "All"

    tracks = [_decorate_track(t) for t in _TRACKS]
    filtered = tracks
    if genre != "All":
        filtered = [t for t in filtered if t["genre"] == genre]
    if mood != "All":
        filtered = [t for t in filtered if t["mood"] == mood]
    filtered.sort(key=lambda t: t["plays"], reverse=True)

    genre_counts = [{"name": g, "count": sum(1 for t in _TRACKS if t["genre"] == g)} for g in GENRES]
    genre_counts = [g for g in genre_counts if g["count"]]

    new_releases = sorted([t for t in tracks if t["new"]], key=lambda t: t["plays"], reverse=True)

    # Artist spotlights: unique artists in the feed, with follow state.
    seen, spotlights = set(), []
    for t in sorted(tracks, key=lambda t: t["plays"], reverse=True):
        if t["artist_id"] in seen:
            continue
        seen.add(t["artist_id"])
        spotlights.append({"id": t["artist_id"], "name": t["artist"], "genre": t["genre"],
                           "avatar": "/static/img/discover/av-%s.jpg" % t["artist_id"]
                           if os.path.exists(os.path.join("static", "img", "discover",
                                                          "av-%s.jpg" % t["artist_id"])) else None,
                           "following": t["artist_id"] in _follows,
                           "initials": "".join(p[0] for p in t["artist"].split()[:2]).upper()})
    spotlights = spotlights[:6]

    return {
        "genres": genre_counts,
        "moods": MOODS,
        "tracks": filtered,
        "new_releases": new_releases[:6],
        "spotlights": spotlights,
        "filters": {"genre": genre, "mood": mood},
        "summary": {
            "tracks": len(_TRACKS),
            "genres": len(genre_counts),
            "new": len(new_releases),
            "likes": len(_likes),
            "follows": len(_follows),
        },
        "result_count": len(filtered),
    }
