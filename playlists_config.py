"""Config-driven data for the Playlist Pitching tracker.

Tracks playlist pitches through a status pipeline (Pitched → In Review →
Added / Passed) with placement stats. Pitches reference real catalog song
titles; playlist names, curators, and follower counts are illustrative.
"""

from royalty_data import get_songs

STAGE_TONE = {
    "Pitched": "border-gray-500/20 bg-gray-500/10 text-gray-300",
    "In Review": "border-amber-500/20 bg-amber-500/10 text-amber-400",
    "Added": "border-green-500/20 bg-green-500/10 text-green-400",
    "Passed": "border-red-500/20 bg-red-500/10 text-red-400",
}

_pitches_seeded = False
_pitches = []


def _seed():
    titles = [s.title for s in get_songs()] or ["Untitled"]

    def t(i):
        return titles[i % len(titles)]

    return [
        {"id": "pl-1", "song": t(0), "playlist": "Late Night Synth", "curator": "Spotify Editorial", "followers": 842000, "stage": "Added"},
        {"id": "pl-2", "song": t(3), "playlist": "Electronic Rising", "curator": "Apple Music", "followers": 410000, "stage": "In Review"},
        {"id": "pl-3", "song": t(1), "playlist": "Chill Drive", "curator": "IndieMood", "followers": 96000, "stage": "Pitched"},
        {"id": "pl-4", "song": t(2), "playlist": "Neon Nights", "curator": "WaveCurator", "followers": 51000, "stage": "Passed"},
        {"id": "pl-5", "song": t(0), "playlist": "Fresh Finds Dance", "curator": "Spotify Editorial", "followers": 1250000, "stage": "In Review"},
    ]


def _ensure():
    global _pitches, _pitches_seeded
    if not _pitches_seeded:
        _pitches = _seed()
        _pitches_seeded = True


def reset_playlists_state():
    global _pitches_seeded
    _pitches_seeded = False
    _ensure()


def get_playlists_data():
    _ensure()
    added = [p for p in _pitches if p["stage"] == "Added"]
    pending = [p for p in _pitches if p["stage"] in ("Pitched", "In Review")]
    reach = sum(p["followers"] for p in added)
    return {
        "summary": {
            "total_pitches": len(_pitches),
            "placements": len(added),
            "pending": len(pending),
            "reach": reach,
        },
        "pitches": _pitches,
        "stage_tone": STAGE_TONE,
    }
