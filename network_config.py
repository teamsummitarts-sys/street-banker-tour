"""Config-driven data for the Network hub.

A directory of industry contacts (artists, producers, songwriters, labels,
managers, A&R, engineers, sync supervisors, playlist curators) plus a
Playlists area where curators list playlists that accept track
submissions. Search / role / genre filters and sorting are applied
server-side. Connections, pitches, and submissions are held in
module-level session state (reset on restart) -- illustrative demo data.
"""

from datetime import datetime, timedelta

ROLES = ["Artist", "Producer", "Songwriter", "Label", "Manager",
         "A&R", "Engineer", "Sync Supervisor", "Playlist Curator"]

GENRES = ["Synthwave", "Electronic", "House", "Techno", "Pop",
          "Hip-Hop", "R&B", "Indie", "Ambient"]

SORTS = [
    {"id": "followers", "label": "Most followers"},
    {"id": "name", "label": "Name (A–Z)"},
    {"id": "available", "label": "Available first"},
]


def _initials(name):
    parts = [p for p in name.replace("&", " ").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


# --- Directory ---------------------------------------------------------------
_PROFILES = [
    {"id": "nova-reign", "avatar": "/static/img/people/p5.jpg", "name": "Nova Reign", "role": "Artist", "genres": ["Synthwave", "Pop"],
     "location": "Los Angeles, CA", "followers": 128000, "verified": True, "available": True,
     "tagline": "Synth-pop for night drives.", "credits": ["'Midnight Tape' (2M streams)", "Toured with Lumen"],
     "rate": None, "links": [{"label": "Spotify", "url": "https://spotify.com"}]},
    {"id": "kilo-byte", "avatar": "/static/img/people/p2.jpg", "name": "Kilo Byte", "role": "Producer", "genres": ["Electronic", "House"],
     "location": "Berlin, DE", "followers": 54000, "verified": True, "available": True,
     "tagline": "Punchy mixes, fast turnarounds.", "credits": ["Mixed 40+ indie EPs", "Grammy-considered 2024"],
     "rate": "$500 / track", "links": []},
    {"id": "marco-velocity", "avatar": "/static/img/discover/av-marco-velocity.jpg", "name": "Marco Velocity", "role": "Producer", "genres": ["House", "Techno"],
     "location": "Miami, FL", "followers": 89000, "verified": False, "available": False,
     "tagline": "Club-ready productions.", "credits": ["Resident, Vault Miami"], "rate": "$750 / track", "links": []},
    {"id": "lila-rose", "avatar": "/static/img/people/p6.jpg", "name": "Lila Rose", "role": "Songwriter", "genres": ["Pop", "R&B"],
     "location": "Nashville, TN", "followers": 32000, "verified": True, "available": True,
     "tagline": "Toplines & co-writes.", "credits": ["12 cuts placed", "ASCAP member"], "rate": "Split-based", "links": []},
    {"id": "nightdrive-records", "avatar": "/static/img/people/p1.jpg", "name": "Nightdrive Records", "role": "Label", "genres": ["Synthwave", "Indie"],
     "location": "London, UK", "followers": 410000, "verified": True, "available": True,
     "tagline": "Independent synth & indie label.", "credits": ["30-artist roster", "Distributed worldwide"],
     "rate": None, "links": [{"label": "Site", "url": "https://example.com"}]},
    {"id": "dj-codec", "avatar": "/static/img/discover/av-dj-codec.jpg", "name": "DJ Codec", "role": "Artist", "genres": ["Techno"],
     "location": "Detroit, MI", "followers": 76000, "verified": False, "available": True,
     "tagline": "Warehouse techno.", "credits": ["Boiler Room set"], "rate": None, "links": []},
    {"id": "sasha-quill", "avatar": "/static/img/people/p4.jpg", "name": "Sasha Quill", "role": "Manager", "genres": ["Pop", "Electronic"],
     "location": "Los Angeles, CA", "followers": 21000, "verified": True, "available": True,
     "tagline": "Artist manager & strategist.", "credits": ["Managed 2 gold records"], "rate": "Commission", "links": []},
    {"id": "reed-mensah", "avatar": "/static/img/people/p3.jpg", "name": "Reed Mensah", "role": "A&R", "genres": ["Hip-Hop", "R&B"],
     "location": "Atlanta, GA", "followers": 44000, "verified": True, "available": True,
     "tagline": "Scouting the next wave.", "credits": ["Signed 6 breakout acts"], "rate": None, "links": []},
    {"id": "vera-sound", "name": "Vera Sound", "role": "Engineer", "genres": ["Pop", "Indie"],
     "location": "New York, NY", "followers": 18000, "verified": False, "available": True,
     "tagline": "Mastering & mix engineer.", "credits": ["Mastered 200+ releases"], "rate": "$120 / master", "links": []},
    {"id": "atlas-sync", "name": "Atlas Sync", "role": "Sync Supervisor", "genres": ["Electronic", "Ambient"],
     "location": "Los Angeles, CA", "followers": 15000, "verified": True, "available": True,
     "tagline": "Placing music in film, TV & ads.", "credits": ["Placements on 3 networks"], "rate": None, "links": []},
    {"id": "echo-lin", "avatar": "/static/img/people/p7.jpg", "name": "Echo Lin", "role": "Playlist Curator", "genres": ["Synthwave", "Electronic"],
     "location": "Toronto, CA", "followers": 240000, "verified": True, "available": True,
     "tagline": "Curator — late-night electronic.", "credits": ["3 flagship playlists"], "rate": None,
     "links": [], "playlists": ["late-night-synth", "neon-circuit"]},
    {"id": "harper-vale", "avatar": "/static/img/people/p10.jpg", "name": "Harper Vale", "role": "Playlist Curator", "genres": ["Indie", "Pop"],
     "location": "London, UK", "followers": 180000, "verified": True, "available": True,
     "tagline": "Indie discovery weekly.", "credits": ["Editorial contributor"], "rate": None,
     "links": [], "playlists": ["indie-rising", "chill-drive"]},
    {"id": "milo-tran", "name": "Milo Tran", "role": "Producer", "genres": ["Hip-Hop"],
     "location": "Toronto, CA", "followers": 61000, "verified": False, "available": True,
     "tagline": "Boom-bap & trap beats.", "credits": ["Placed with indie rappers"], "rate": "$400 / beat", "links": []},
    {"id": "jade-okoro", "avatar": "/static/img/people/p11.jpg", "name": "Jade Okoro", "role": "Songwriter", "genres": ["R&B", "Pop"],
     "location": "Atlanta, GA", "followers": 27000, "verified": True, "available": False,
     "tagline": "Soulful toplines.", "credits": ["8 cuts placed"], "rate": "Split-based", "links": []},
    {"id": "prism-collective", "avatar": "/static/img/people/p8.jpg", "name": "Prism Collective", "role": "Label", "genres": ["House", "Techno"],
     "location": "Berlin, DE", "followers": 320000, "verified": True, "available": True,
     "tagline": "Electronic label & agency.", "credits": ["20-artist roster"], "rate": None, "links": []},
    {"id": "theo-park", "name": "Theo Park", "role": "Manager", "genres": ["Hip-Hop", "R&B"],
     "location": "New York, NY", "followers": 19000, "verified": False, "available": True,
     "tagline": "Day-to-day artist management.", "credits": ["Booked 40+ shows"], "rate": "Commission", "links": []},
    {"id": "sable-wynn", "avatar": "/static/img/discover/av-sable-wynn.jpg", "name": "Sable Wynn", "role": "Artist", "genres": ["R&B", "Indie"],
     "location": "Los Angeles, CA", "followers": 95000, "verified": True, "available": True,
     "tagline": "Alt-R&B singer-songwriter.", "credits": ["Sync in 2 ad campaigns"], "rate": None, "links": []},
    {"id": "grid-runner", "avatar": "/static/img/discover/av-grid-runner.jpg", "name": "Grid Runner", "role": "Artist", "genres": ["Synthwave"],
     "location": "Berlin, DE", "followers": 52000, "verified": False, "available": True,
     "tagline": "Retro-futurist producer/artist.", "credits": ["2 self-released albums"], "rate": None, "links": []},
    {"id": "cass-oram", "avatar": "/static/img/people/p12.jpg", "name": "Cass Oram", "role": "Engineer", "genres": ["Ambient", "Electronic"],
     "location": "London, UK", "followers": 12000, "verified": False, "available": True,
     "tagline": "Atmospheric mixing & sound design.", "credits": ["Film score work"], "rate": "$140 / mix", "links": []},
    {"id": "juno-fields", "avatar": "/static/img/people/p9.jpg", "name": "Juno Fields", "role": "Playlist Curator", "genres": ["Ambient", "Indie"],
     "location": "Portland, OR", "followers": 88000, "verified": False, "available": True,
     "tagline": "Focus & ambient sounds.", "credits": ["Fast-growing curator"], "rate": None,
     "links": [], "playlists": ["deep-focus"]},
    {"id": "rico-santana", "name": "Rico Santana", "role": "A&R", "genres": ["Hip-Hop"],
     "location": "Miami, FL", "followers": 33000, "verified": True, "available": False,
     "tagline": "Label A&R, Latin & hip-hop.", "credits": ["Signed 4 acts"], "rate": None, "links": []},
    {"id": "wren-adler", "name": "Wren Adler", "role": "Sync Supervisor", "genres": ["Indie", "Pop"],
     "location": "New York, NY", "followers": 9000, "verified": False, "available": True,
     "tagline": "Ad & trailer music supervisor.", "credits": ["Trailer placements"], "rate": None, "links": []},
]

# --- Playlists (accept submissions) -----------------------------------------
_PLAYLISTS = [
    {"id": "late-night-synth", "name": "Late Night Synth", "curator_id": "echo-lin",
     "followers": 842000, "genres": ["Synthwave", "Electronic"], "mood": "Nocturnal · Driving",
     "accepting": True, "description": "Dark, cinematic synth for after-hours."},
    {"id": "neon-circuit", "name": "Neon Circuit", "curator_id": "echo-lin",
     "followers": 305000, "genres": ["Electronic", "House"], "mood": "Energetic · Bright",
     "accepting": True, "description": "Upbeat electronic and future-pop."},
    {"id": "indie-rising", "name": "Indie Rising", "curator_id": "harper-vale",
     "followers": 512000, "genres": ["Indie", "Pop"], "mood": "Fresh · Melodic",
     "accepting": True, "description": "New indie discovery, updated weekly."},
    {"id": "chill-drive", "name": "Chill Drive", "curator_id": "harper-vale",
     "followers": 96000, "genres": ["Indie", "Synthwave"], "mood": "Mellow · Warm",
     "accepting": False, "description": "Laid-back tracks for the open road."},
    {"id": "deep-focus", "name": "Deep Focus", "curator_id": "juno-fields",
     "followers": 431000, "genres": ["Ambient", "Electronic"], "mood": "Calm · Minimal",
     "accepting": True, "description": "Ambient beds for work and study."},
]

# --- Shows / touring ---------------------------------------------------------
# Profiles open to booking; each has upcoming tour dates.
_BOOKING = {"nova-reign", "dj-codec", "sable-wynn", "grid-runner", "prism-collective", "nightdrive-records"}

_SHOWS = [
    {"id": "sh-1", "profile_id": "nova-reign", "date": "2026-08-14", "city": "Los Angeles, CA", "venue": "The Echo", "status": "On sale"},
    {"id": "sh-2", "profile_id": "nova-reign", "date": "2026-08-20", "city": "San Francisco, CA", "venue": "Rickshaw Stop", "status": "On sale"},
    {"id": "sh-3", "profile_id": "dj-codec", "date": "2026-09-05", "city": "Detroit, MI", "venue": "Spot Lite", "status": "Announced"},
    {"id": "sh-4", "profile_id": "sable-wynn", "date": "2026-08-28", "city": "Los Angeles, CA", "venue": "Moroccan Lounge", "status": "Sold out"},
    {"id": "sh-5", "profile_id": "grid-runner", "date": "2026-09-12", "city": "Berlin, DE", "venue": "About Blank", "status": "On sale"},
    {"id": "sh-6", "profile_id": "prism-collective", "date": "2026-10-03", "city": "Berlin, DE", "venue": "Watergate", "status": "Announced"},
]

# --- Mintable Moments (timed, watermarked, serial-numbered collectibles) -----
# Each is a limited "moment" an artist posts; it shows for a set window, is
# watermarked + numbered, and can be claimed (simulated purchase). Card art is
# a two-color gradient rendered client-side -- no external image needed.
_MOMENTS = [
    {"id": "mo-1", "owner_id": "nova-reign", "title": "Backstage — Echo, LA", "caption": "One take before we hit the stage.",
     "from": "#1e1b4b", "to": "#0f172a", "edition_n": 1, "edition_total": 50, "price": 25, "hours_left": 18},
    {"id": "mo-2", "owner_id": "sable-wynn", "title": "Studio Bloom", "caption": "The night 'Afterglow' came together.",
     "from": "#831843", "to": "#1e3a8a", "edition_n": 7, "edition_total": 100, "price": 15, "hours_left": 6},
    {"id": "mo-3", "owner_id": "grid-runner", "title": "Neon Run", "caption": "Berlin, 3am, lights still on.",
     "from": "#064e3b", "to": "#0c0a09", "edition_n": 12, "edition_total": 25, "price": 40, "hours_left": 47},
    {"id": "mo-4", "owner_id": "dj-codec", "title": "Warehouse Set", "caption": "Peak time. You had to be there.",
     "from": "#7f1d1d", "to": "#18181b", "edition_n": 3, "edition_total": 30, "price": 30, "hours_left": 2},
]

# --- Session state (resets on restart) --------------------------------------
_connections = {}   # profile_id -> status ("Pending" | "Connected")
_pitches = []       # {profile_id, message, song}
_submissions = []   # {playlist_id, song, message, status}
_bookings = []      # {profile_id, city, date, message}
_claimed = {}       # moment_id -> serial owned by "you"


def reset_network_state():
    _connections.clear()
    _pitches.clear()
    _submissions.clear()
    _bookings.clear()
    _claimed.clear()


def _serial(moment):
    return "SB-%s-%04d" % (moment["id"].split("-")[-1], moment["edition_n"])


def _decorate_show(s):
    owner = next((x for x in _PROFILES if x["id"] == s["profile_id"]), None)
    return {**s, "owner_name": owner["name"] if owner else "—",
            "owner_role": owner["role"] if owner else ""}


def _decorate_moment(m):
    owner = next((x for x in _PROFILES if x["id"] == m["owner_id"]), None)
    expires = (datetime.now() + timedelta(hours=m["hours_left"])).isoformat()
    return {**m, "owner_name": owner["name"] if owner else "—",
            "owner_initials": _initials(owner["name"]) if owner else "?",
            "serial": _serial(m), "expires_iso": expires,
            "claimed": m["id"] in _claimed}


def get_shows():
    return sorted((_decorate_show(s) for s in _SHOWS), key=lambda s: s["date"])


def get_moments():
    return [_decorate_moment(m) for m in _MOMENTS]


def get_moment(moment_id):
    m = next((x for x in _MOMENTS if x["id"] == moment_id), None)
    return _decorate_moment(m) if m else None


def enquire_show(profile_id, city, date, message):
    if profile_id not in _BOOKING:
        return None
    entry = {"profile_id": profile_id, "city": (city or "").strip(),
             "date": (date or "").strip(), "message": (message or "").strip()}
    _bookings.append(entry)
    return entry


def claim_moment(moment_id):
    m = next((x for x in _MOMENTS if x["id"] == moment_id), None)
    if m is None:
        return None
    _claimed[moment_id] = _serial(m)
    return _claimed[moment_id]


def _decorate(p):
    return {**p, "initials": _initials(p["name"]),
            "connection": _connections.get(p["id"]),
            "booking": p["id"] in _BOOKING,
            "playlist_count": len(p.get("playlists", []))}


def get_profile(profile_id):
    p = next((x for x in _PROFILES if x["id"] == profile_id), None)
    if p is None:
        return None
    prof = _decorate(p)
    prof["playlists_full"] = [_decorate_playlist(pl) for pl in _PLAYLISTS if pl["curator_id"] == p["id"]]
    prof["shows"] = [_decorate_show(s) for s in _SHOWS if s["profile_id"] == p["id"]]
    return prof


def _decorate_playlist(pl):
    curator = next((x for x in _PROFILES if x["id"] == pl["curator_id"]), None)
    submitted = any(s["playlist_id"] == pl["id"] for s in _submissions)
    return {**pl, "curator_name": curator["name"] if curator else "—", "submitted": submitted}


def get_playlist(playlist_id):
    pl = next((x for x in _PLAYLISTS if x["id"] == playlist_id), None)
    return _decorate_playlist(pl) if pl else None


def connect(profile_id):
    if not any(x["id"] == profile_id for x in _PROFILES):
        return None
    _connections[profile_id] = "Pending"
    return _connections[profile_id]


def pitch(profile_id, message, song):
    if not any(x["id"] == profile_id for x in _PROFILES):
        return None
    entry = {"profile_id": profile_id, "message": (message or "").strip(), "song": (song or "").strip()}
    _pitches.append(entry)
    return entry


def submit_to_playlist(playlist_id, song, message):
    pl = next((x for x in _PLAYLISTS if x["id"] == playlist_id), None)
    if pl is None or not pl["accepting"] or not (song or "").strip():
        return None
    entry = {"playlist_id": playlist_id, "song": song.strip(),
             "message": (message or "").strip(), "status": "Submitted"}
    _submissions.append(entry)
    return entry


def get_network_data(args=None):
    args = args or {}
    q = (args.get("q") or "").strip().lower()
    role = args.get("role") or "All"
    genre = args.get("genre") or "All"
    sort = args.get("sort") or "followers"
    tab = args.get("tab") or "directory"

    people = [_decorate(p) for p in _PROFILES]
    if role != "All":
        people = [p for p in people if p["role"] == role]
    if genre != "All":
        people = [p for p in people if genre in p["genres"]]
    if q:
        people = [p for p in people if q in " ".join(
            [p["name"], p["role"], p["location"], p["tagline"], " ".join(p["genres"])]).lower()]

    if sort == "name":
        people.sort(key=lambda p: p["name"].lower())
    elif sort == "available":
        people.sort(key=lambda p: (not p["available"], -p["followers"]))
    else:
        people.sort(key=lambda p: p["followers"], reverse=True)

    connected_ids = set(_connections)
    my_connections = [_decorate(p) for p in _PROFILES if p["id"] in connected_ids]

    return {
        "summary": {
            "total": len(_PROFILES),
            "roles": len({p["role"] for p in _PROFILES}),
            "playlists": len(_PLAYLISTS),
            "accepting": sum(1 for pl in _PLAYLISTS if pl["accepting"]),
            "connections": len(_connections),
            "shows": len(_SHOWS),
            "moments": len(_MOMENTS),
        },
        "tab": tab,
        "people": people,
        "playlists": [_decorate_playlist(pl) for pl in _PLAYLISTS],
        "shows": get_shows(),
        "moments": get_moments(),
        "my_connections": my_connections,
        "my_bookings": [{**b, "name": next((x["name"] for x in _PROFILES if x["id"] == b["profile_id"]), b["profile_id"])} for b in _bookings],
        "my_moments": [_decorate_moment(m) for m in _MOMENTS if m["id"] in _claimed],
        "pitches": [{**pt, "name": next((x["name"] for x in _PROFILES if x["id"] == pt["profile_id"]), pt["profile_id"])} for pt in _pitches],
        "submissions": [{**s, "playlist_name": next((x["name"] for x in _PLAYLISTS if x["id"] == s["playlist_id"]), s["playlist_id"])} for s in _submissions],
        "roles": ["All"] + ROLES,
        "genres": ["All"] + GENRES,
        "sorts": SORTS,
        "filters": {"q": args.get("q") or "", "role": role, "genre": genre, "sort": sort},
        "result_count": len(people),
    }
