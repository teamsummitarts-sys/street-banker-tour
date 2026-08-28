"""Mock data + config for the Catalog page (the Flask equivalent of the
spec's mockCatalogData.js). Everything the page renders -- summary
counts, health, issues, value trend, and the five tab datasets -- comes
from here so the template holds no hard-coded content. get_account()
drives the editable sidebar account chip shared across the app.
"""


def get_account():
    # The open demo-workspace persona — matches the sample catalog's artist
    # (all seeded songs are by Synthwave Surfer). A signed-in user's real
    # name/role overlays this via _account_with_user in app.py.
    return {
        "name": "Synthwave Surfer",
        "role": "Demo Workspace",
        "initials": "SS",
        "plan": "Pro Plan",
        "next_payout": 2500,
        "next_payout_in": "6 days",
    }


CATALOG_TABS = ["Tracks", "Releases", "Songwriters", "Publishers", "Splits"]

STATUS_OPTIONS = [
    "All Statuses", "Registered", "Unregistered", "Missing ISRC",
    "Missing Metadata", "Split Conflict", "Pending Registration",
]
GENRE_OPTIONS = [
    "All Genres", "Hip-Hop", "Rock", "Pop", "Electronic",
    "Alternative", "R&B", "Country", "Other",
]
SOURCE_OPTIONS = [
    "All Sources", "Spotify", "Apple Music", "ASCAP", "BMI",
    "The MLC", "SoundExchange", "YouTube Content ID", "Distributor",
]

# status -> tailwind text/border tone
STATUS_TONE = {
    "Registered": "green",
    "Unregistered": "red",
    "Missing ISRC": "amber",
    "Missing Metadata": "amber",
    "Split Conflict": "red",
    "Pending Registration": "gold",
}


def _tracks():
    return [
        {"id": "track_001", "title": "Blood in the Groove", "duration": "3:42",
         "artist": "Synthwave Surfer", "release": "The Collection Vol. 1", "genre": "Alternative",
         "source": ["Spotify", "Apple Music", "ASCAP"], "isrc": "US-A1B-25-00001",
         "iswc": "T-100.100.001-1", "upc": "810000000011", "publisher": "War Machine Publishing",
         "status": "Registered", "earnings_ytd": 1842.32,
         "registrations": {"pro": True, "mlc": True, "soundexchange": True, "youtube_content_id": True, "tiktok_meta_rights": True}},
        {"id": "track_002", "title": "Make It Out Alive", "duration": "3:18",
         "artist": "Synthwave Surfer", "release": "Survival Mode", "genre": "Hip-Hop",
         "source": ["Spotify", "Apple Music"], "isrc": "US-A1B-25-00002",
         "iswc": "T-100.100.002-2", "upc": "810000000028", "publisher": "War Machine Publishing",
         "status": "Registered", "earnings_ytd": 1235.10,
         "registrations": {"pro": True, "mlc": True, "soundexchange": True, "youtube_content_id": False, "tiktok_meta_rights": True}},
        {"id": "track_003", "title": "Midnight Prayers", "duration": "4:05",
         "artist": "Synthwave Surfer", "release": "The Collection Vol. 1", "genre": "R&B",
         "source": ["Spotify", "The MLC"], "isrc": "US-A1B-25-00003",
         "iswc": "T-100.100.003-3", "upc": "810000000011", "publisher": "War Machine Publishing",
         "status": "Registered", "earnings_ytd": 1092.45,
         "registrations": {"pro": True, "mlc": True, "soundexchange": False, "youtube_content_id": True, "tiktok_meta_rights": False}},
        {"id": "track_004", "title": "Broken Crown", "duration": "3:56",
         "artist": "Synthwave Surfer", "release": "Kings Don't Sleep", "genre": "Rock",
         "source": ["YouTube Content ID"], "isrc": "US-A1B-25-00004",
         "iswc": None, "upc": "810000000042", "publisher": "War Machine Publishing",
         "status": "Missing ISRC", "earnings_ytd": 642.18,
         "registrations": {"pro": True, "mlc": False, "soundexchange": False, "youtube_content_id": True, "tiktok_meta_rights": False}},
        {"id": "track_005", "title": "No Looking Back", "duration": "3:27",
         "artist": "Synthwave Surfer", "release": "Survival Mode", "genre": "Hip-Hop",
         "source": ["Distributor"], "isrc": None,
         "iswc": None, "upc": None, "publisher": None,
         "status": "Unregistered", "earnings_ytd": 0.0,
         "registrations": {"pro": False, "mlc": False, "soundexchange": False, "youtube_content_id": False, "tiktok_meta_rights": False}},
        {"id": "track_006", "title": "Still Here", "duration": "3:09",
         "artist": "Synthwave Surfer", "release": "Survival Mode", "genre": "Alternative",
         "source": ["Spotify"], "isrc": None,
         "iswc": None, "upc": None, "publisher": None,
         "status": "Missing Metadata", "earnings_ytd": 0.0,
         "registrations": {"pro": False, "mlc": False, "soundexchange": False, "youtube_content_id": False, "tiktok_meta_rights": False}},
        {"id": "track_007", "title": "Paradise Lost", "duration": "4:11",
         "artist": "Synthwave Surfer", "release": "The Collection Vol. 1", "genre": "Rock",
         "source": ["Spotify", "Apple Music", "BMI"], "isrc": "US-A1B-25-00006",
         "iswc": "T-100.100.006-6", "upc": "810000000011", "publisher": "War Machine Publishing",
         "status": "Registered", "earnings_ytd": 980.77,
         "registrations": {"pro": True, "mlc": True, "soundexchange": True, "youtube_content_id": True, "tiktok_meta_rights": True}},
        {"id": "track_008", "title": "Ghost in the Machine", "duration": "3:51",
         "artist": "Synthwave Surfer", "release": "Digital Souls", "genre": "Electronic",
         "source": ["Spotify", "Apple Music"], "isrc": "US-A1B-25-00007",
         "iswc": "T-100.100.007-7", "upc": "810000000073", "publisher": "War Machine Publishing",
         "status": "Registered", "earnings_ytd": 752.66,
         "registrations": {"pro": True, "mlc": True, "soundexchange": True, "youtube_content_id": True, "tiktok_meta_rights": True}},
    ]


def _releases():
    return [
        {"id": "release_001", "title": "The Collection Vol. 1", "artist": "Synthwave Surfer",
         "type": "Album", "release_date": "2025-03-14", "upc": "810000000011",
         "track_count": 14, "registration_rate": 92, "metadata_rate": 88, "earnings_ytd": 14820.55},
        {"id": "release_002", "title": "Survival Mode", "artist": "Synthwave Surfer",
         "type": "Album", "release_date": "2025-05-22", "upc": "810000000028",
         "track_count": 12, "registration_rate": 83, "metadata_rate": 71, "earnings_ytd": 12450.00},
        {"id": "release_003", "title": "Kings Don't Sleep", "artist": "Synthwave Surfer",
         "type": "Album", "release_date": "2025-05-10", "upc": "810000000042",
         "track_count": 10, "registration_rate": 70, "metadata_rate": 64, "earnings_ytd": 8500.00},
        {"id": "release_004", "title": "Digital Souls", "artist": "Synthwave Surfer",
         "type": "EP", "release_date": "2025-05-22", "upc": "810000000073",
         "track_count": 6, "registration_rate": 95, "metadata_rate": 90, "earnings_ytd": 5210.30},
    ]


def _songwriters():
    return [
        {"id": "sw_001", "name": "Marcus Vance", "songs": 42, "total_share": 55.0,
         "confirmed_splits": 38, "unconfirmed_splits": 4, "earnings_ytd": 9420.15},
        {"id": "sw_002", "name": "Jamie Rowe", "songs": 18, "total_share": 20.0,
         "confirmed_splits": 15, "unconfirmed_splits": 3, "earnings_ytd": 3120.44},
        {"id": "sw_003", "name": "Lila Rose", "songs": 9, "total_share": 15.0,
         "confirmed_splits": 6, "unconfirmed_splits": 3, "earnings_ytd": 1840.90},
        {"id": "sw_004", "name": "DJ Codec", "songs": 5, "total_share": 10.0,
         "confirmed_splits": 5, "unconfirmed_splits": 0, "earnings_ytd": 980.20},
    ]


def _publishers():
    return [
        {"id": "pub_001", "name": "War Machine Publishing", "songs": 61, "territories": 42,
         "pro": "ASCAP", "registration_status": "Registered", "earnings_ytd": 14200.55},
        {"id": "pub_002", "name": "Velocity Sound Group", "songs": 12, "territories": 18,
         "pro": "BMI", "registration_status": "Registered", "earnings_ytd": 3210.10},
        {"id": "pub_003", "name": "Independent (self-published)", "songs": 8, "territories": 5,
         "pro": "None", "registration_status": "Unregistered", "earnings_ytd": 640.00},
    ]


def _splits():
    return [
        {"id": "split_001", "track": "Blood in the Groove", "collaborator": "Marcus Vance",
         "role": "Writer/Performer", "share": 70.0, "status": "Confirmed", "conflict": None},
        {"id": "split_002", "track": "Blood in the Groove", "collaborator": "Jamie Rowe",
         "role": "Co-Writer", "share": 30.0, "status": "Confirmed", "conflict": None},
        {"id": "split_003", "track": "Make It Out Alive", "collaborator": "Marcus Vance",
         "role": "Writer/Performer", "share": 60.0, "status": "Confirmed", "conflict": None},
        {"id": "split_004", "track": "Make It Out Alive", "collaborator": "DJ Codec",
         "role": "Producer", "share": 30.0, "status": "Unconfirmed", "conflict": "Total below 100%"},
        {"id": "split_005", "track": "Midnight Prayers", "collaborator": "Lila Rose",
         "role": "Featured Vocalist", "share": 55.0, "status": "Unconfirmed", "conflict": "Total above 100%"},
        {"id": "split_006", "track": "Midnight Prayers", "collaborator": "Marcus Vance",
         "role": "Writer", "share": 55.0, "status": "Confirmed", "conflict": "Total above 100%"},
        {"id": "split_007", "track": "Broken Crown", "collaborator": "Jamie Rowe",
         "role": "Co-Writer", "share": 50.0, "status": "Unconfirmed", "conflict": "Missing collaborator email"},
    ]


def _recently_added():
    return [
        {"id": "recent_001", "title": "New World Order", "type": "Single",
         "date_added": "May 28, 2025", "status": "Registered"},
        {"id": "recent_002", "title": "Digital Souls", "type": "Album",
         "date_added": "May 22, 2025", "status": "Registered"},
        {"id": "recent_003", "title": "Still Here", "type": "Single",
         "date_added": "May 15, 2025", "status": "Missing Metadata"},
        {"id": "recent_004", "title": "Kings Don't Sleep", "type": "Album",
         "date_added": "May 10, 2025", "status": "Registered"},
        {"id": "recent_005", "title": "Make It Out Alive", "type": "Single",
         "date_added": "May 5, 2025", "status": "Registered"},
    ]


def get_catalog_data():
    summary = {
        "total_tracks": 1248,
        "tracks_added_this_month": 24,
        "total_releases": 87,
        "releases_added_this_month": 3,
        "registered_tracks": 1032,
        "unregistered_tracks": 216,
        "total_isrcs": 1218,
        "isrc_assignment_rate": 97.6,
    }
    registered_pct = round(summary["registered_tracks"] / summary["total_tracks"] * 100, 1)
    unregistered_pct = round(summary["unregistered_tracks"] / summary["total_tracks"] * 100, 1)

    health = {
        "total": 76, "status": "Good",
        "bars": [
            {"label": "Metadata", "pct": 82},
            {"label": "Registration", "pct": 68},
            {"label": "ISRCs", "pct": 98},
            {"label": "Splits", "pct": 74},
            {"label": "Territories", "pct": 65},
        ],
    }

    issues = [
        {"id": "issue_001", "title": "Missing ISRCs", "count": 18, "severity": "critical",
         "filter_tab": "Tracks", "filter_status": "Missing ISRC"},
        {"id": "issue_002", "title": "Unregistered Tracks", "count": 216, "severity": "warning",
         "filter_tab": "Tracks", "filter_status": "Unregistered"},
        {"id": "issue_003", "title": "Missing Metadata", "count": 24, "severity": "warning",
         "filter_tab": "Tracks", "filter_status": "Missing Metadata"},
        {"id": "issue_004", "title": "Split Conflicts", "count": 7, "severity": "critical",
         "filter_tab": "Splits", "filter_status": "Conflict"},
    ]

    catalog_value = {
        "estimated_value": 2815430,
        "monthly_change": 14.2,
        "trend": [
            {"month": "Jan", "value": 1850000},
            {"month": "Feb", "value": 1975000},
            {"month": "Mar", "value": 2140000},
            {"month": "Apr", "value": 2460000},
            {"month": "May", "value": 2815430},
        ],
    }

    return {
        "summary": summary,
        "registered_pct": registered_pct,
        "unregistered_pct": unregistered_pct,
        "health": health,
        "issues": issues,
        "catalog_value": catalog_value,
        "tracks": _tracks(),
        "releases": _releases(),
        "songwriters": _songwriters(),
        "publishers": _publishers(),
        "splits": _splits(),
        "recently_added": _recently_added(),
        "tabs": CATALOG_TABS,
        "release_filter_options": ["All Releases"] + [r["title"] for r in _releases()],
        "status_options": STATUS_OPTIONS,
        "genre_options": GENRE_OPTIONS,
        "source_options": SOURCE_OPTIONS,
        "status_tone": STATUS_TONE,
    }
