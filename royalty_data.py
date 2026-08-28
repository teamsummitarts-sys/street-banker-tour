from dataclasses import dataclass, replace
from datetime import date, timedelta


@dataclass
class PlatformBalance:
    platform: str
    royalty_type: str
    amount: float


@dataclass
class PlatformConnection:
    id: str
    platform: str
    royalty_type: str
    amount: float
    status: str  # connected | not_connected | syncing | needs_login | error


@dataclass
class Kpi:
    label: str
    value: str
    delta_label: str
    trend: list = None


@dataclass
class Payout:
    song: str
    platform: str
    status: str
    amount: float
    days_ago: int = 0


@dataclass
class Alert:
    id: str
    title: str
    description: str
    severity: str  # High | Medium | Low
    source: str
    estimated_impact: float
    cta_label: str
    resolution_message: str


@dataclass
class Finding:
    id: str
    source: str
    issue_type: str
    estimated_value: float
    confidence: str  # High | Medium | Low
    recommended_action: str


@dataclass
class SplitEntry:
    collaborator: str
    role: str
    percentage: float
    confirmed: bool


@dataclass
class Recommendation:
    id: str
    reason: str
    urgency: str  # High | Medium | Low
    estimated_value: float
    cta_label: str
    target_type: str  # "alert" | "song"
    target_id: str


@dataclass
class Claim:
    id: str
    source: str
    issue_type: str
    estimated_value: float
    status: str  # Detected | Needs Info | Submitted | In Review | Approved | Paid | Rejected
    recommended_action: str


@dataclass
class Song:
    id: str
    title: str
    isrc: str
    iswc: str
    upc: str
    master_owner: str
    writers: list
    producers: list
    publisher: str
    lyrics_on_file: bool
    alternate_titles: list
    registrations: dict  # distribution|pro|mlc|soundexchange|youtube_content_id|tiktok_meta_rights -> bool
    total_earned: float
    streams: int
    platform_earnings: dict
    splits: list  # list[SplitEntry]
    monthly_trend: list


@dataclass
class ScheduledPayout:
    id: str
    source: str
    amount: float
    pay_date: date
    status: str  # Scheduled | Processing | Delayed | Paid


_DEFAULT_PLATFORMS = [
    PlatformConnection("spotify", "Spotify", "Streaming Royalties", 2500.00, "connected"),
    PlatformConnection("apple-music", "Apple Music", "Streaming Royalties", 1234.56, "connected"),
    PlatformConnection("ascap", "ASCAP", "Performance Royalties", 8765.43, "connected"),
    PlatformConnection("bmi", "BMI", "Performance Royalties", 4321.00, "connected"),
    PlatformConnection("sesac", "SESAC", "Performance Royalties", 3120.75, "connected"),
    PlatformConnection("soundexchange", "SoundExchange", "Digital Performance Royalties", 1850.32, "connected"),
    PlatformConnection("the-mlc", "The MLC", "Mechanical Royalties", 940.18, "connected"),
    PlatformConnection("youtube-music", "YouTube Music", "Streaming Royalties", 612.44, "not_connected"),
    PlatformConnection("amazon-music", "Amazon Music", "Streaming Royalties", 430.10, "syncing"),
    PlatformConnection("deezer", "Deezer", "Streaming Royalties", 210.77, "needs_login"),
    PlatformConnection("tidal", "Tidal", "Streaming Royalties", 95.20, "error"),
    PlatformConnection("pandora", "Pandora", "Digital Performance Royalties", 150.00, "not_connected"),
    PlatformConnection("ppl", "PPL", "Performance Royalties", 320.90, "not_connected"),
    PlatformConnection("youtube-content-id", "YouTube Content ID", "Sync Royalties", 480.00, "not_connected"),
    PlatformConnection("distrokid", "DistroKid", "Distribution Royalties", 275.40, "connected"),
    PlatformConnection("tunecore", "TuneCore", "Distribution Royalties", 190.15, "not_connected"),
    PlatformConnection("cd-baby", "CD Baby", "Distribution Royalties", 88.60, "not_connected"),
    PlatformConnection("unitedmasters", "UnitedMasters", "Distribution Royalties", 132.75, "not_connected"),
    PlatformConnection("meta", "Meta", "Sync Royalties", 64.20, "not_connected"),
    PlatformConnection("tiktok", "TikTok", "Sync Royalties", 340.90, "syncing"),
    PlatformConnection("twitch", "Twitch", "Streaming Royalties", 41.30, "not_connected"),
    PlatformConnection("bandcamp", "Bandcamp", "Streaming Royalties", 210.00, "connected"),
    PlatformConnection("beatstars", "BeatStars", "Licensing Royalties", 155.50, "not_connected"),
    PlatformConnection("songtrust", "Songtrust", "Publishing Royalties", 265.90, "needs_login"),
    PlatformConnection("harry-fox-agency", "Harry Fox Agency", "Mechanical Royalties", 175.25, "not_connected"),
]

_status_overrides = {}


def get_platform_catalog():
    return [
        replace(p, status=_status_overrides.get(p.id, p.status))
        for p in _DEFAULT_PLATFORMS
    ]


def set_connection_status(platform_id, status):
    entry = next((p for p in _DEFAULT_PLATFORMS if p.id == platform_id), None)
    if entry is None:
        return None
    _status_overrides[platform_id] = status
    return replace(entry, status=status)


def reset_connection_state():
    _status_overrides.clear()


def get_platform_balances():
    return [
        PlatformBalance(p.platform, p.royalty_type, p.amount)
        for p in get_platform_catalog()
        if p.status == "connected"
    ]


def total_royalties(balances):
    return sum(balance.amount for balance in balances)


def get_kpis():
    return [
        Kpi("Active Streams", "+2,350", "+180.1% from last month", [12, 18, 15, 22, 27, 35]),
        Kpi("New Listeners", "+1,200", "+50 from last month", [8, 10, 9, 13, 14, 16]),
        Kpi("Sync Licenses", "2", "1 pending negotiation", [0, 1, 1, 1, 2, 2]),
        Kpi("Follower Growth", "+842", "+5.2% this month", [20, 19, 24, 26, 25, 29]),
    ]


def get_earnings_trend():
    return [
        ("Jan", 800.0),
        ("Feb", 1450.0),
        ("Mar", 1900.0),
        ("Apr", 2200.0),
        ("May", 2800.0),
        ("Jun", 3200.0),
    ]


def get_recent_payouts():
    return [
        Payout("Midnight Drive", "Spotify", "Paid", 250.00, days_ago=0),
        Payout("Neon Dreams", "Apple Music", "Paid", 150.00, days_ago=2),
        Payout("City Lights", "ASCAP", "Processing", 350.00, days_ago=3),
        Payout("Digital Paradise", "YouTube Content ID", "Paid", 180.15, days_ago=5),
        Payout("Digital Paradise", "SoundExchange", "Paid", 140.25, days_ago=7),
    ]


def recent_payout_rows():
    """Recent payouts with a resolved calendar date, for list views that
    show when each payment landed."""
    today = date.today()
    return [
        {
            "song": p.song, "platform": p.platform, "status": p.status,
            "amount": p.amount, "date": today - timedelta(days=p.days_ago),
        }
        for p in get_recent_payouts()
    ]


def get_payout_calendar():
    today = date.today()
    entries = [
        ("cal-1", "The MLC", 180.18, -10, "Paid"),
        ("cal-2", "BMI", 340.00, -4, "Delayed"),
        ("cal-3", "Apple Music", 295.75, 2, "Processing"),
        ("cal-4", "Spotify", 410.20, 5, "Scheduled"),
        ("cal-5", "ASCAP", 780.00, 12, "Scheduled"),
        ("cal-6", "SoundExchange", 610.75, 20, "Scheduled"),
        ("cal-7", "SESAC", 520.00, 28, "Scheduled"),
    ]
    payouts = [
        ScheduledPayout(id=eid, source=source, amount=amount, pay_date=today + timedelta(days=offset), status=status)
        for eid, source, amount, offset, status in entries
    ]
    payouts.sort(key=lambda p: p.pay_date)
    return payouts


def upcoming_payout_total(payouts):
    return sum(p.amount for p in payouts if p.status in ("Scheduled", "Processing"))


_SONGS = [
    Song(
        id="midnight-drive",
        title="Midnight Drive",
        isrc="USRC12345678",
        iswc="T-034.524.680-1",
        upc="810012345671",
        master_owner="Synthwave Surfer",
        writers=["Synthwave Surfer", "Jamie Rowe"],
        producers=["Synthwave Surfer"],
        publisher="Street Banker Publishing",
        lyrics_on_file=True,
        alternate_titles=[],
        registrations={
            "distribution": True, "pro": True, "mlc": True,
            "soundexchange": True, "youtube_content_id": True, "tiktok_meta_rights": False,
        },
        total_earned=4120.55,
        streams=5_200_000,
        platform_earnings={"Spotify": 2450.00, "Apple Music": 890.55, "ASCAP": 780.00},
        splits=[
            SplitEntry("Synthwave Surfer", "Writer/Performer", 70.0, True),
            SplitEntry("Jamie Rowe", "Co-Writer", 20.0, True),
            SplitEntry("Street Banker Publishing", "Publisher", 10.0, True),
        ],
        monthly_trend=[520, 610, 700, 780, 820, 890],
    ),
    Song(
        id="neon-dreams",
        title="Neon Dreams",
        isrc="USRC12345679",
        iswc=None,
        upc="810012345672",
        master_owner="Synthwave Surfer",
        writers=["Synthwave Surfer"],
        producers=["Marco Velocity"],
        publisher="Street Banker Publishing",
        lyrics_on_file=True,
        alternate_titles=["Neon Dreams (Extended Mix)"],
        registrations={
            "distribution": True, "pro": True, "mlc": False,
            "soundexchange": True, "youtube_content_id": False, "tiktok_meta_rights": False,
        },
        total_earned=2340.10,
        streams=3_100_000,
        platform_earnings={"Apple Music": 1234.56, "Spotify": 1105.54},
        splits=[
            SplitEntry("Synthwave Surfer", "Writer/Performer", 60.0, True),
            SplitEntry("Marco Velocity", "Producer", 40.0, False),
        ],
        monthly_trend=[310, 340, 360, 400, 410, 430],
    ),
    Song(
        id="city-lights",
        title="City Lights",
        isrc=None,
        iswc=None,
        upc=None,
        master_owner="Synthwave Surfer",
        writers=["Synthwave Surfer", "Lila Rose"],
        producers=[],
        publisher=None,
        lyrics_on_file=False,
        alternate_titles=[],
        registrations={
            "distribution": True, "pro": False, "mlc": False,
            "soundexchange": False, "youtube_content_id": False, "tiktok_meta_rights": False,
        },
        total_earned=350.00,
        streams=980_000,
        platform_earnings={"ASCAP": 350.00},
        splits=[
            SplitEntry("Synthwave Surfer", "Writer/Performer", 50.0, False),
            SplitEntry("Lila Rose", "Featured Vocalist", 50.0, False),
        ],
        monthly_trend=[40, 55, 60, 70, 62, 63],
    ),
    Song(
        id="digital-paradise",
        title="Digital Paradise",
        isrc="USRC12345680",
        iswc="T-034.524.681-2",
        upc="810012345673",
        master_owner="Synthwave Surfer",
        writers=["Synthwave Surfer"],
        producers=["Synthwave Surfer", "DJ Codec"],
        publisher="Street Banker Publishing",
        lyrics_on_file=False,
        alternate_titles=[],
        registrations={
            "distribution": True, "pro": True, "mlc": True,
            "soundexchange": True, "youtube_content_id": True, "tiktok_meta_rights": True,
        },
        total_earned=1980.75,
        streams=2_500_000,
        platform_earnings={"Spotify": 980.00, "SoundExchange": 620.75, "BMI": 380.00},
        splits=[
            SplitEntry("Synthwave Surfer", "Writer/Performer", 100.0, True),
        ],
        monthly_trend=[260, 280, 300, 330, 340, 350],
    ),
    Song(
        id="velvet-static",
        title="Velvet Static",
        isrc=None,
        iswc=None,
        upc=None,
        master_owner="Synthwave Surfer",
        writers=[],
        producers=[],
        publisher=None,
        lyrics_on_file=False,
        alternate_titles=["Velvet Static (Demo)"],
        registrations={
            "distribution": False, "pro": False, "mlc": False,
            "soundexchange": False, "youtube_content_id": False, "tiktok_meta_rights": False,
        },
        total_earned=95.20,
        streams=210_000,
        platform_earnings={"Tidal": 95.20},
        splits=[],
        monthly_trend=[10, 12, 15, 14, 18, 20],
    ),
]


def get_songs():
    return list(_SONGS)


def get_song(song_id):
    return next((s for s in _SONGS if s.id == song_id), None)


_split_overrides = {}


def get_song_splits(song_id):
    if song_id in _split_overrides:
        return _split_overrides[song_id]
    song = get_song(song_id)
    return list(song.splits) if song else []


def live_song(song):
    """A song with any Split Manager edits applied. Every other field is
    untouched — this only ever overrides `splits`, so the rest of the
    catalog's static fields (metadata, registrations, earnings) stay
    exactly as seeded.
    """
    return replace(song, splits=get_song_splits(song.id))


def add_split(song_id, collaborator, role, percentage):
    if get_song(song_id) is None:
        return None
    splits = get_song_splits(song_id) + [SplitEntry(collaborator, role, percentage, False)]
    _split_overrides[song_id] = splits
    return splits


def remove_split(song_id, index):
    if get_song(song_id) is None:
        return None
    splits = list(get_song_splits(song_id))
    if 0 <= index < len(splits):
        del splits[index]
    _split_overrides[song_id] = splits
    return splits


def toggle_split_confirmed(song_id, index):
    if get_song(song_id) is None:
        return None
    splits = list(get_song_splits(song_id))
    if 0 <= index < len(splits):
        entry = splits[index]
        splits[index] = replace(entry, confirmed=not entry.confirmed)
    _split_overrides[song_id] = splits
    return splits


def reset_split_state():
    _split_overrides.clear()


def split_total_percentage(song):
    return sum(s.percentage for s in song.splits)


def splits_fully_confirmed(song):
    return bool(song.splits) and all(s.confirmed for s in song.splits)


_METADATA_CHECK_KEYS = [
    "isrc", "iswc", "upc", "writers", "producers", "publisher",
    "pro", "mlc", "soundexchange", "lyrics", "alternate_titles",
]

_REGISTRATION_CHECK_KEYS = [
    "distribution", "isrc", "upc", "pro", "publisher",
    "mlc", "soundexchange", "youtube_content_id", "tiktok_meta_rights", "split_confirmation",
]


def song_check_status(song):
    """Single source of truth: every checklist item this song could be scored on."""
    return {
        "isrc": bool(song.isrc),
        "iswc": bool(song.iswc),
        "upc": bool(song.upc),
        "writers": bool(song.writers),
        "producers": bool(song.producers),
        "publisher": bool(song.publisher),
        "lyrics": song.lyrics_on_file,
        "alternate_titles": bool(song.alternate_titles),
        "distribution": song.registrations.get("distribution", False),
        "pro": song.registrations.get("pro", False),
        "mlc": song.registrations.get("mlc", False),
        "soundexchange": song.registrations.get("soundexchange", False),
        "youtube_content_id": song.registrations.get("youtube_content_id", False),
        "tiktok_meta_rights": song.registrations.get("tiktok_meta_rights", False),
        "split_confirmation": splits_fully_confirmed(song),
    }


def song_missing_issues(song):
    status = song_check_status(song)
    labels = {
        "isrc": "Missing ISRC", "iswc": "Missing ISWC", "upc": "Missing UPC",
        "writers": "No writers on file", "producers": "No producers on file",
        "publisher": "No publisher on file", "lyrics": "Lyrics not on file",
        "alternate_titles": "No alternate titles logged",
        "distribution": "Not registered with a distributor", "pro": "Not registered with a PRO",
        "mlc": "Not registered with The MLC", "soundexchange": "Not registered with SoundExchange",
        "youtube_content_id": "Not registered with YouTube Content ID",
        "tiktok_meta_rights": "TikTok/Meta rights not secured",
        "split_confirmation": "Splits not fully confirmed",
    }
    return [labels[key] for key, ok in status.items() if not ok]


def metadata_completion_score(song):
    status = song_check_status(song)
    checks = [status[k] for k in _METADATA_CHECK_KEYS]
    return sum(checks) / len(checks)


def registration_checklist_score(song):
    status = song_check_status(song)
    checks = [status[k] for k in _REGISTRATION_CHECK_KEYS]
    return sum(checks) / len(checks)


def get_royalty_goal():
    return 25000.0


def royalty_progress(total, goal):
    if goal <= 0:
        return 0.0
    return min(total / goal, 1.0)


CATALOG_VALUE_MULTIPLES = {"low": 8, "mid": 12, "high": 16}


def estimate_catalog_value(earnings_trend, multiples=None):
    multiples = multiples or CATALOG_VALUE_MULTIPLES
    values = [v for _, v in earnings_trend]
    monthly_avg = sum(values) / len(values) if values else 0.0
    annual_run_rate = monthly_avg * 12
    return {
        "annual_run_rate": round(annual_run_rate, 2),
        "low": round(annual_run_rate * multiples["low"], 2),
        "mid": round(annual_run_rate * multiples["mid"], 2),
        "high": round(annual_run_rate * multiples["high"], 2),
        "multiples": multiples,
    }


def assess_advance_eligibility(earnings_trend, payout_calendar, catalog_value_mid, total_royalties_collected):
    values = [v for _, v in earnings_trend]
    if values and values[0] > 0:
        trend_growth = (values[-1] - values[0]) / values[0]
    else:
        trend_growth = 0.0
    trend_score = min(max(trend_growth, 0.0), 1.0)

    statuses = [p.status for p in payout_calendar]
    non_delayed = sum(1 for s in statuses if s != "Delayed")
    consistency_score = (non_delayed / len(statuses)) if statuses else 0.0

    history_score = min(total_royalties_collected / 20000, 1.0)

    overall = round((trend_score * 0.4 + consistency_score * 0.35 + history_score * 0.25) * 100)

    if overall >= 70:
        tier = "Eligible"
    elif overall >= 45:
        tier = "Eligible with conditions"
    else:
        tier = "Not yet eligible"

    suggested_advance = round(catalog_value_mid * (overall / 100) * 0.25, 2)

    return {
        "score": overall,
        "tier": tier,
        "trend_score": round(trend_score * 100),
        "consistency_score": round(consistency_score * 100),
        "history_score": round(history_score * 100),
        "suggested_advance": suggested_advance,
    }


def get_overview_health(catalog, songs):
    """The Overview health card's four-bar breakdown plus an overall
    score, each bar deep-linking to the page that fixes it. Derived from
    the live catalog and songs so it stays honest as connections and
    metadata change.
    """
    total_platforms = len(catalog) or 1
    connected = sum(1 for p in catalog if p.status == "connected")
    connections_pct = round(connected / total_platforms * 100)

    if songs:
        metadata_pct = round(sum(metadata_completion_score(s) for s in songs) / len(songs) * 100)
        registration_pct = round(sum(registration_checklist_score(s) for s in songs) / len(songs) * 100)
        confirmed = sum(1 for s in songs if splits_fully_confirmed(s))
        splits_pct = round(confirmed / len(songs) * 100)
    else:
        metadata_pct = registration_pct = splits_pct = 0

    bars = [
        {"key": "connections", "label": "Connections", "pct": connections_pct, "route": "/connections"},
        {"key": "metadata", "label": "Metadata", "pct": metadata_pct, "route": "/catalog"},
        {"key": "registration", "label": "Registration", "pct": registration_pct, "route": "/catalog"},
        {"key": "splits", "label": "Splits", "pct": splits_pct, "route": "/catalog"},
    ]
    overall = round(sum(b["pct"] for b in bars) / len(bars))
    if overall >= 80:
        band = "Excellent"
    elif overall >= 60:
        band = "Good"
    elif overall >= 40:
        band = "Fair"
    else:
        band = "At risk"
    return {"score": overall, "band": band, "bars": bars}


PLATFORM_LOGO_KEYS = {
    "Spotify": "spotify",
    "Apple Music": "apple",
    "YouTube Music": "youtube",
    "YouTube Content ID": "youtube",
    "YouTube": "youtube",
    "TikTok": "tiktok",
    "ASCAP": "ascap",
    "BMI": "bmi",
    "The MLC": "mlc",
    "SoundExchange": "soundexchange",
}


def platform_logo_key(name):
    return PLATFORM_LOGO_KEYS.get(name, "other")


def _pseudo_change(name):
    """Stable, varied month-over-month %% for a source. We don't track
    per-source history, so this is illustrative -- deterministic from the
    name so it never jumps around between renders."""
    h = sum(ord(ch) for ch in name)
    return round((h % 340) / 10 - 4, 1)


def get_valuation_overview(earnings_trend, catalog_value, advance_eligibility, value_tracker):
    """The Valuation page's summary layer: headline estimated value,
    month-over-month change, annual run rate, suggested advance, and a
    value-over-time series -- all derived from the existing catalog
    value, advance, and tracker figures so nothing is independently
    invented. The trend applies the mid multiple to the running
    annualized run rate at each month.
    """
    mid_multiple = catalog_value["multiples"]["mid"]
    labels = [label for label, _ in earnings_trend]
    values = [v for _, v in earnings_trend]

    trend = []
    for i, label in enumerate(labels):
        window = values[: i + 1]
        annual = (sum(window) / len(window)) * 12 if window else 0
        trend.append({"label": label, "value": round(annual * mid_multiple, 2)})

    return {
        "estimated_value": catalog_value["mid"],
        "value_low": catalog_value["low"],
        "value_high": catalog_value["high"],
        "monthly_change": value_tracker["pct_change"],
        "annual_run_rate": catalog_value["annual_run_rate"],
        "suggested_advance": advance_eligibility["suggested_advance"],
        "eligibility_tier": advance_eligibility["tier"],
        "eligibility_score": advance_eligibility["score"],
        "trend": trend,
    }


def get_royalties_overview(balances, catalog, payout_calendar, earnings_trend, recent_rows):
    """Everything the Royalties page's top half needs -- four summary
    stats, the ranked by-source breakdown, and the earnings-trend footer
    -- assembled from real connected balances, the payout calendar, and
    the earnings trend. Only the per-source change %% is illustrative."""
    values = [v for _, v in earnings_trend]
    this_month = values[-1] if values else 0
    last_month = values[-2] if len(values) > 1 else this_month
    growth = round(((this_month - last_month) / last_month * 100), 1) if last_month else 0.0

    total = round(sum(b.amount for b in balances), 2)
    ranked = sorted(balances, key=lambda b: b.amount, reverse=True)
    top, rest = ranked[:7], ranked[7:]

    by_source = []
    for b in top:
        by_source.append({
            "name": b.platform,
            "logo": platform_logo_key(b.platform),
            "earned": round(b.amount, 2),
            "change_pct": _pseudo_change(b.platform),
            "pct_of_total": round(b.amount / total * 100) if total else 0,
            "connected": True,
        })
    if rest:
        other = round(sum(b.amount for b in rest), 2)
        by_source.append({
            "name": "Other Sources", "logo": "other", "earned": other,
            "change_pct": _pseudo_change("Other Sources"),
            "pct_of_total": round(other / total * 100) if total else 0,
            "connected": True,
        })

    pending = [p for p in payout_calendar if p.status in ("Scheduled", "Processing")]
    payouts_received = round(sum(r["amount"] for r in recent_rows if r["status"] == "Paid"), 2)
    connected = sum(1 for p in catalog if p.status == "connected")

    return {
        "summary": {
            "total_royalties": total,
            "total_change": growth,
            "payouts_received": payouts_received,
            "payouts_change": growth,
            "pending_payouts": round(sum(p.amount for p in pending), 2),
            "pending_count": len(pending),
            "sources_connected": connected,
            "total_sources": len(catalog),
        },
        "by_source": by_source,
        "this_month": this_month,
        "last_month": last_month,
        "growth": growth,
    }


# Deep-scan findings that apply to *connected* sources (shown only when the
# platform is connected, since you can't audit a source you aren't pulling from).
_CONNECTED_FINDINGS = [
    ("spotify", "Unmatched ISRC", 142.50, "Medium", "Submit ISRC correction"),
    ("the-mlc", "Unclaimed mechanical royalties", 318.00, "High", "File a claim"),
    ("ascap", "Missing live performance royalties", 96.25, "Low", "Register setlists"),
]


def _slug(text):
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def get_missing_royalty_findings(catalog):
    findings = []
    by_id = {p.id: p for p in catalog}

    for p in catalog:
        if p.status == "not_connected":
            findings.append(Finding(
                id=f"{p.id}-uncollected",
                source=p.platform,
                issue_type="Uncollected royalties",
                estimated_value=round(p.amount, 2),
                confidence="High" if p.amount >= 300 else "Medium",
                recommended_action=f"Connect {p.platform}",
            ))
        elif p.status == "needs_login":
            findings.append(Finding(
                id=f"{p.id}-login",
                source=p.platform,
                issue_type="Login expired — collections paused",
                estimated_value=round(p.amount * 0.5, 2),
                confidence="Medium",
                recommended_action=f"Re-authenticate {p.platform}",
            ))
        elif p.status == "error":
            findings.append(Finding(
                id=f"{p.id}-sync",
                source=p.platform,
                issue_type="Sync failure",
                estimated_value=round(p.amount, 2),
                confidence="Medium",
                recommended_action=f"Retry {p.platform} sync",
            ))

    for pid, issue, value, confidence, action in _CONNECTED_FINDINGS:
        p = by_id.get(pid)
        if p is not None and p.status == "connected":
            findings.append(Finding(
                id=f"{pid}-{_slug(issue)}",
                source=p.platform,
                issue_type=issue,
                estimated_value=value,
                confidence=confidence,
                recommended_action=action,
            ))

    findings.sort(key=lambda f: f.estimated_value, reverse=True)
    return findings


CLAIM_PIPELINE = ["Detected", "Needs Info", "Submitted", "In Review", "Approved", "Paid"]

_claim_status_overrides = {}


def get_claims(catalog):
    findings = get_missing_royalty_findings(catalog)
    claims = [
        Claim(
            id=f.id,
            source=f.source,
            issue_type=f.issue_type,
            estimated_value=f.estimated_value,
            status=_claim_status_overrides.get(f.id, "Detected"),
            recommended_action=f.recommended_action,
        )
        for f in findings
    ]
    claims.sort(key=lambda c: c.estimated_value, reverse=True)
    return claims


def advance_claim(claim_id, catalog):
    findings = get_missing_royalty_findings(catalog)
    if not any(f.id == claim_id for f in findings):
        return None
    current = _claim_status_overrides.get(claim_id, "Detected")
    if current in ("Paid", "Rejected"):
        return current
    idx = CLAIM_PIPELINE.index(current)
    new_status = CLAIM_PIPELINE[min(idx + 1, len(CLAIM_PIPELINE) - 1)]
    _claim_status_overrides[claim_id] = new_status
    return new_status


def reject_claim(claim_id, catalog):
    findings = get_missing_royalty_findings(catalog)
    if not any(f.id == claim_id for f in findings):
        return None
    current = _claim_status_overrides.get(claim_id, "Detected")
    if current == "Paid":
        return current
    _claim_status_overrides[claim_id] = "Rejected"
    return "Rejected"


def reset_claim_state():
    _claim_status_overrides.clear()


_SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def get_royalty_leak_alerts(balances, payouts, kpis, catalog):
    alerts = []

    for p in catalog:
        if p.status == "needs_login":
            alerts.append(Alert(
                id=f"{p.id}-needs-login",
                title=f"{p.platform} login expired",
                description="Collections are paused until you re-authenticate this connection.",
                severity="High",
                source=p.platform,
                estimated_impact=round(p.amount * 0.5, 2),
                cta_label="Re-authenticate",
                resolution_message=f"Re-authenticated {p.platform}. Collections resumed.",
            ))
        elif p.status == "error":
            alerts.append(Alert(
                id=f"{p.id}-sync-error",
                title=f"{p.platform} sync failure",
                description="This platform hasn't synced successfully — royalties may be going uncounted.",
                severity="High",
                source=p.platform,
                estimated_impact=round(p.amount, 2),
                cta_label="Retry Sync",
                resolution_message=f"Resynced {p.platform} successfully.",
            ))
        elif p.status == "not_connected":
            alerts.append(Alert(
                id=f"{p.id}-not-connected",
                title=f"{p.platform} isn't connected",
                description="Estimated royalties are going uncollected on this platform.",
                severity="Medium" if p.amount >= 250 else "Low",
                source=p.platform,
                estimated_impact=round(p.amount, 2),
                cta_label="Connect Platform",
                resolution_message=f"Connected {p.platform}.",
            ))

    processing_payout = next((x for x in payouts if x.status == "Processing"), None)
    if processing_payout is not None:
        alerts.append(Alert(
            id=f"payout-{_slug(processing_payout.song)}",
            title=f'"{processing_payout.song}" payout delayed',
            description=(
                f"${processing_payout.amount:.2f} from {processing_payout.platform} "
                "is still processing."
            ),
            severity="Medium",
            source=processing_payout.platform,
            estimated_impact=round(processing_payout.amount, 2),
            cta_label="Send Follow-Up",
            resolution_message=(
                f'Sent a follow-up to {processing_payout.platform} about '
                f'"{processing_payout.song}".'
            ),
        ))

    pending_kpi = next((k for k in kpis if "pending" in k.delta_label.lower()), None)
    if pending_kpi is not None:
        alerts.append(Alert(
            id="pending-negotiation",
            title=f"{pending_kpi.label} needs review",
            description=f"{pending_kpi.delta_label}.",
            severity="Low",
            source="Internal",
            estimated_impact=0.0,
            cta_label="Review Negotiation",
            resolution_message="Marked the pending negotiation for review.",
        ))

    if not alerts:
        alerts.append(Alert(
            id="scan",
            title="No active leaks detected",
            description="Run a scan periodically to catch new issues early.",
            severity="Low",
            source="System",
            estimated_impact=0.0,
            cta_label="Scan Now",
            resolution_message="Scan complete — no new missing royalties found this time.",
        ))

    alerts.sort(key=lambda a: (_SEVERITY_ORDER.get(a.severity, 3), -a.estimated_impact))
    return alerts


def _alert_route(alert):
    """Send each Action Center alert to the page that resolves it."""
    aid = alert.id
    if any(token in aid for token in ("needs-login", "sync-error", "not-connected")):
        return "/connections"
    if aid.startswith("payout-") or aid == "pending-negotiation":
        return "/royalties"
    if aid == "scan":
        return "/recovery"
    return "/recovery"


def get_action_center(alerts, payouts, limit=5):
    """The Overview Action Center: open problems (from leak alerts, each
    routed to its fix page) blended with recent wins (paid payouts), so
    the feed reads like a real activity log, not just a problem list.
    """
    items = []
    for a in alerts:
        severity = "critical" if a.severity == "High" else ("warning" if a.severity == "Medium" else "info")
        items.append({
            "kind": "alert",
            "severity": severity,
            "title": a.title,
            "description": a.description,
            "impact": round(a.estimated_impact, 2),
            "impact_positive": False,
            "route": _alert_route(a),
        })
    for p in payouts:
        if p.status == "Paid":
            items.append({
                "kind": "success",
                "severity": "success",
                "title": f"{p.platform} payout received",
                "description": f'"{p.song}" collected successfully',
                "impact": round(p.amount, 2),
                "impact_positive": True,
                "route": "/royalties",
            })
    order = {"critical": 0, "warning": 1, "info": 2}
    problems = sorted(
        (i for i in items if i["kind"] != "success"),
        key=lambda i: order.get(i["severity"], 3),
    )
    wins = [i for i in items if i["kind"] == "success"]
    problem_slots = min(len(problems), max(limit - 2, limit - len(wins)))
    blended = problems[:problem_slots] + wins[: limit - problem_slots]
    return blended[:limit]


def get_smart_recommendations(alerts, songs, limit=5):
    """Ranked, deduplicated action list: catalog-level alerts plus song-level
    split risk (a signal no other section surfaces), sorted purely by
    estimated financial impact so the highest-value action is always first.
    """
    recs = [
        Recommendation(
            id=f"alert-{a.id}",
            reason=a.title,
            urgency=a.severity,
            estimated_value=a.estimated_impact,
            cta_label=a.cta_label,
            target_type="alert",
            target_id=a.id,
        )
        for a in alerts
    ]
    for s in songs:
        if s.splits and not splits_fully_confirmed(s):
            recs.append(Recommendation(
                id=f"splits-{s.id}",
                reason=f'Unconfirmed splits on "{s.title}" put its earnings at risk',
                urgency="Medium",
                estimated_value=round(s.total_earned, 2),
                cta_label="Confirm Splits",
                target_type="song",
                target_id=s.id,
            ))
    recs.sort(key=lambda r: r.estimated_value, reverse=True)
    return recs[:limit]


def money_left_on_table(findings):
    """Uncollected royalties bucketed by confidence, so the headline number
    can be shown with an honest range instead of one falsely-precise figure.
    """
    high = sum(f.estimated_value for f in findings if f.confidence == "High")
    medium = sum(f.estimated_value for f in findings if f.confidence == "Medium")
    low = sum(f.estimated_value for f in findings if f.confidence == "Low")
    return {
        "high": round(high, 2),
        "medium": round(medium, 2),
        "low": round(low, 2),
        "total": round(high + medium + low, 2),
    }


def get_top_royalty_leaks(findings, limit=5):
    return findings[:limit]


@dataclass
class FixItem:
    id: str
    title: str
    category: str  # Royalty | Metadata | Registration | Connection | Split
    severity: str  # High | Medium | Low
    estimated_impact: float
    source: str
    related_song: str  # nullable
    recommended_action: str
    status: str  # Open | Assigned | Dismissed | Complete


_fix_status_overrides = {}


def set_fix_status(item_id, status):
    if status not in ("Open", "Assigned", "Dismissed", "Complete"):
        return None
    _fix_status_overrides[item_id] = status
    return status


def reset_fix_status_state():
    _fix_status_overrides.clear()


def _severity_for_value(value):
    if value >= 300:
        return "High"
    if value >= 100:
        return "Medium"
    return "Low"


_FIX_METADATA_LABELS = {
    "isrc": "Missing ISRC", "iswc": "Missing ISWC", "upc": "Missing UPC",
    "writers": "No writers on file", "producers": "No producers on file",
    "publisher": "No publisher on file", "lyrics": "Lyrics not on file",
    "alternate_titles": "No alternate titles logged",
}
_FIX_REGISTRATION_LABELS = {
    "distribution": "Not registered with a distributor", "pro": "Not registered with a PRO",
    "mlc": "Not registered with The MLC", "soundexchange": "Not registered with SoundExchange",
    "youtube_content_id": "Not registered with YouTube Content ID",
    "tiktok_meta_rights": "TikTok/Meta rights not secured",
}


def get_fixes_queue(catalog, songs, findings, limit=12):
    """A single prioritized queue across every kind of open issue —
    royalty, metadata, registration, connection, and split — so nothing
    requires jumping between five different sections to triage.
    """
    items = []

    for p in catalog:
        if p.status in ("not_connected", "needs_login", "error"):
            sev = "High" if p.status in ("needs_login", "error") else _severity_for_value(p.amount)
            action = "Connect Platform" if p.status == "not_connected" else (
                "Re-authenticate" if p.status == "needs_login" else "Retry Sync"
            )
            items.append(FixItem(
                id=f"fix-conn-{p.id}", title=f"{p.platform} needs attention ({p.status.replace('_', ' ')})",
                category="Connection", severity=sev, estimated_impact=round(p.amount, 2),
                source=p.platform, related_song=None, recommended_action=action, status="Open",
            ))

    for f in findings:
        items.append(FixItem(
            id=f"fix-{f.id}", title=f.issue_type, category="Royalty",
            severity=_severity_for_value(f.estimated_value), estimated_impact=f.estimated_value,
            source=f.source, related_song=None, recommended_action=f.recommended_action, status="Open",
        ))

    for s in songs:
        status = song_check_status(s)
        at_risk = round(s.total_earned * 0.05, 2)
        for key, label in _FIX_METADATA_LABELS.items():
            if not status[key]:
                items.append(FixItem(
                    id=f"fix-meta-{s.id}-{key}", title=f'{label} — "{s.title}"', category="Metadata",
                    severity="Medium", estimated_impact=at_risk, source="Catalog",
                    related_song=s.title, recommended_action="Update Metadata", status="Open",
                ))
        for key, label in _FIX_REGISTRATION_LABELS.items():
            if not status[key]:
                items.append(FixItem(
                    id=f"fix-reg-{s.id}-{key}", title=f'{label} — "{s.title}"', category="Registration",
                    severity="High" if key in ("pro", "distribution") else "Medium",
                    estimated_impact=at_risk, source="Catalog",
                    related_song=s.title, recommended_action="Register Now", status="Open",
                ))
        if s.splits and not splits_fully_confirmed(s):
            items.append(FixItem(
                id=f"fix-split-{s.id}", title=f'Unconfirmed splits — "{s.title}"', category="Split",
                severity="Medium", estimated_impact=round(s.total_earned, 2), source="Catalog",
                related_song=s.title, recommended_action="Confirm Splits", status="Open",
            ))

    for item in items:
        if item.id in _fix_status_overrides:
            item.status = _fix_status_overrides[item.id]

    items.sort(key=lambda i: (_SEVERITY_ORDER.get(i.severity, 3), -i.estimated_impact))
    return items[:limit]


DOCUMENT_TYPES = [
    "split_sheet", "contract", "registration_receipt", "publishing_agreement",
    "royalty_report", "catalog_valuation_report", "advance_offer",
]
DOCUMENT_LABELS = {
    "split_sheet": "Split Sheet", "contract": "Contract", "registration_receipt": "Registration Receipt",
    "publishing_agreement": "Publishing Agreement", "royalty_report": "Royalty Report",
    "catalog_valuation_report": "Catalog Valuation Report", "advance_offer": "Advance Offer",
}

_DOCUMENT_PRESENCE = {
    "midnight-drive": {"split_sheet", "contract", "registration_receipt", "royalty_report"},
    "neon-dreams": {"split_sheet", "royalty_report"},
    "city-lights": set(),
    "digital-paradise": {
        "split_sheet", "contract", "registration_receipt",
        "publishing_agreement", "royalty_report", "catalog_valuation_report",
    },
    "velvet-static": set(),
}


def get_documents_vault(songs):
    entries = []
    total_present = 0
    for s in songs:
        present = _DOCUMENT_PRESENCE.get(s.id, set())
        total_present += len(present)
        docs = [{"type": t, "label": DOCUMENT_LABELS[t], "present": t in present} for t in DOCUMENT_TYPES]
        missing = [d["label"] for d in docs if not d["present"]]
        entries.append({"song": s, "documents": docs, "missing_count": len(missing), "missing": missing})
    total_slots = len(songs) * len(DOCUMENT_TYPES)
    completeness = (total_present / total_slots) if total_slots else 0.0
    return {"entries": entries, "completeness": completeness}


@dataclass
class Release:
    id: str
    title: str
    release_date: date
    readiness_score: int
    missing_tasks: list
    registration_status: dict
    distribution_status: str  # Not submitted | Submitted | Live
    rights_setup: bool
    checklist: list  # list of {"label": str, "done": bool}


def get_upcoming_releases():
    today = date.today()
    return [
        Release(
            id="release-neon-echoes",
            title="Neon Echoes",
            release_date=today + timedelta(days=18),
            readiness_score=62,
            missing_tasks=["Submit ISRC", "Confirm splits", "Upload artwork metadata"],
            registration_status={
                "pro": True, "mlc": False, "soundexchange": True,
                "youtube_content_id": False, "tiktok_meta_rights": False,
            },
            distribution_status="Submitted",
            rights_setup=False,
            checklist=[
                {"label": "Masters finalized", "done": True},
                {"label": "ISRC/UPC assigned", "done": False},
                {"label": "Splits confirmed", "done": False},
                {"label": "Distributor submission", "done": True},
                {"label": "PRO registration", "done": True},
                {"label": "Artwork + metadata uploaded", "done": False},
            ],
        ),
        Release(
            id="release-glass-horizon",
            title="Glass Horizon",
            release_date=today + timedelta(days=45),
            readiness_score=25,
            missing_tasks=["Assign publisher", "Register with PRO", "Submit to distributor", "Secure TikTok/Meta rights"],
            registration_status={
                "pro": False, "mlc": False, "soundexchange": False,
                "youtube_content_id": False, "tiktok_meta_rights": False,
            },
            distribution_status="Not submitted",
            rights_setup=False,
            checklist=[
                {"label": "Masters finalized", "done": True},
                {"label": "ISRC/UPC assigned", "done": False},
                {"label": "Splits confirmed", "done": False},
                {"label": "Distributor submission", "done": False},
                {"label": "PRO registration", "done": False},
                {"label": "Artwork + metadata uploaded", "done": False},
            ],
        ),
    ]


def get_royalty_forecast(earnings_trend):
    """Conservative / expected / aggressive projections for 30 days, 90
    days, and 12 months, derived from the existing monthly earnings trend
    rather than any new mock series.
    """
    values = [v for _, v in earnings_trend]
    monthly_avg = sum(values) / len(values) if values else 0.0
    growth = (values[-1] - values[0]) / values[0] if values and values[0] > 0 else 0.05
    modes = {
        "conservative": 0.85,
        "expected": 1.0,
        "aggressive": 1.0 + max(growth, 0.15),
    }
    horizons = {"30_day": 1, "90_day": 3, "12_month": 12}
    return {
        mode: {horizon: round(monthly_avg * months * mult, 2) for horizon, months in horizons.items()}
        for mode, mult in modes.items()
    }


CATALOG_VALUE_TRACKER_MULTIPLES = [12, 15, 18, 24]


def get_catalog_value_tracker(earnings_trend, multiple=15):
    values = [v for _, v in earnings_trend]
    monthly_avg = sum(values) / len(values) if values else 0.0
    current_value = round(monthly_avg * 12 * multiple, 2)
    prior_values = values[:-1] if len(values) > 1 else values
    prior_avg = sum(prior_values) / len(prior_values) if prior_values else monthly_avg
    last_month_value = round(prior_avg * 12 * multiple, 2)
    pct_change = round(((current_value - last_month_value) / last_month_value) * 100, 1) if last_month_value else 0.0
    return {
        "current_value": current_value,
        "last_month_value": last_month_value,
        "pct_change": pct_change,
        "multiple": multiple,
        "available_multiples": CATALOG_VALUE_TRACKER_MULTIPLES,
    }


WIZARD_TARGETS = ["pro", "mlc", "soundexchange", "youtube_content_id", "tiktok_meta_rights", "distributor", "publishing_admin"]
WIZARD_TARGET_LABELS = {
    "pro": "Performance Rights Organization (PRO)", "mlc": "The MLC", "soundexchange": "SoundExchange",
    "youtube_content_id": "YouTube Content ID", "tiktok_meta_rights": "TikTok / Meta rights",
    "distributor": "Distributor", "publishing_admin": "Publishing Administrator",
}

_registration_wizard_overrides = {}


def get_registration_wizard(song):
    base = {
        "pro": song.registrations.get("pro", False),
        "mlc": song.registrations.get("mlc", False),
        "soundexchange": song.registrations.get("soundexchange", False),
        "youtube_content_id": song.registrations.get("youtube_content_id", False),
        "tiktok_meta_rights": song.registrations.get("tiktok_meta_rights", False),
        "distributor": song.registrations.get("distribution", False),
        "publishing_admin": False,
    }
    status = {**base, **_registration_wizard_overrides.get(song.id, {})}
    missing = [t for t in WIZARD_TARGETS if not status[t]]
    completed = len(WIZARD_TARGETS) - len(missing)
    return {
        "song_id": song.id,
        "song_title": song.title,
        "status": status,
        "missing": missing,
        "completion_pct": round(completed / len(WIZARD_TARGETS) * 100),
    }


def complete_registration_step(song_id, target):
    song = get_song(song_id)
    if song is None or target not in WIZARD_TARGETS:
        return None
    overrides = _registration_wizard_overrides.setdefault(song_id, {})
    overrides[target] = True
    return get_registration_wizard(song)


def reset_registration_wizard_state():
    _registration_wizard_overrides.clear()


# Formats say CSV because CSV is what report_builder produces. They said
# PDF and XLSX while nothing was produced at all; making the label true
# was cheaper and more useful than adding a PDF dependency.
REPORT_TYPES = [
    {"id": "royalty-report", "label": "Royalty Report", "description": "Full breakdown of collected royalties by platform and song.", "category": "Financial", "format": "CSV", "icon": "dollar"},
    {"id": "missing-money-report", "label": "Missing Money Report", "description": "Every uncollected or at-risk royalty currently detected.", "category": "Recovery", "format": "CSV", "icon": "search"},
    {"id": "catalog-valuation-report", "label": "Catalog Valuation Report", "description": "Estimated catalog value across low, mid, and high multiples.", "category": "Financial", "format": "CSV", "icon": "trend"},
    {"id": "advance-readiness-report", "label": "Advance Readiness Report", "description": "Advance eligibility score and suggested advance amount.", "category": "Financial", "format": "CSV", "icon": "bolt"},
    {"id": "registration-audit", "label": "Registration Audit", "description": "Registration status for every song across every rights body.", "category": "Rights", "format": "CSV", "icon": "shield"},
    {"id": "investor-snapshot", "label": "Investor Snapshot", "description": "One-page summary of catalog health, value, and growth.", "category": "Investor", "format": "CSV", "icon": "chart"},
]

REPORT_CATEGORY_ORDER = ["Financial", "Recovery", "Rights", "Investor"]

# Illustrative saved schedules — the app has no scheduler backend yet, so these
# stand in as example recurring exports until one is wired up.
_scheduled_reports = [
    {"id": "sched-1", "report_id": "royalty-report", "cadence": "Monthly", "next_run": "2026-08-01", "recipients": 2, "enabled": True},
    {"id": "sched-2", "report_id": "investor-snapshot", "cadence": "Quarterly", "next_run": "2026-10-01", "recipients": 1, "enabled": True},
    {"id": "sched-3", "report_id": "missing-money-report", "cadence": "Weekly", "next_run": "2026-07-11", "recipients": 1, "enabled": False},
]

# Live log of reports generated this session, newest first.
_report_history = []


def get_available_reports():
    return REPORT_TYPES


def get_scheduled_reports():
    by_id = {r["id"]: r for r in REPORT_TYPES}
    out = []
    for s in _scheduled_reports:
        rt = by_id.get(s["report_id"], {})
        out.append({**s, "label": rt.get("label", s["report_id"]), "format": rt.get("format", "PDF")})
    return out


def get_report_history():
    return list(_report_history)


def generate_report(report_id):
    match = next((r for r in REPORT_TYPES if r["id"] == report_id), None)
    if match is None:
        return None
    generated_at = date.today()
    report = {
        "id": report_id,
        "label": match["label"],
        "format": match["format"],
        "generated_at": generated_at.isoformat(),
        "filename": f"{report_id}-{generated_at.strftime('%Y%m%d')}.{match['format'].lower()}",
    }
    _report_history.insert(0, report)
    del _report_history[25:]
    return report


def get_since_last_login_summary(catalog, songs, catalog_value_pct_change, catalog_value_mid=0):
    connection_issues = sum(1 for p in catalog if p.status in ("needs_login", "error"))
    metadata_issues = sum(len(song_missing_issues(s)) for s in songs)
    issues_needing_attention = connection_issues + sum(
        1 for s in songs if not splits_fully_confirmed(s)
    )
    catalog_value_increase = round(catalog_value_mid * (catalog_value_pct_change / 100), 2)
    return {
        "new_royalties_collected": 482.15,
        "new_payouts_detected": 2,
        "connection_issues": connection_issues,
        "metadata_issues": metadata_issues,
        "issues_needing_attention": issues_needing_attention,
        "tasks_completed": 5,
        "catalog_value_change_pct": catalog_value_pct_change,
        "catalog_value_increase": catalog_value_increase,
        "newly_detected_songs": 1,
    }


@dataclass
class Conflict:
    id: str
    conflict_type: str
    title: str
    description: str
    severity: str  # High | Medium | Low
    songs_involved: list


def get_rights_conflicts(songs):
    """Detects split conflicts, missing ownership data, disputed publisher
    information, and ISRC/ISWC inconsistencies across the live catalog
    (including any in-session Split Manager edits).
    """
    conflicts = []

    for s in songs:
        if s.splits:
            total = split_total_percentage(s)
            if abs(total - 100.0) > 0.01:
                conflicts.append(Conflict(
                    id=f"split-conflict-{s.id}", conflict_type="Split Conflict",
                    title=f'"{s.title}" splits total {total:.1f}%',
                    description="Collaborator splits do not sum to 100% — royalties may be miscalculated.",
                    severity="High", songs_involved=[s.title],
                ))

    for s in songs:
        if not s.writers:
            conflicts.append(Conflict(
                id=f"missing-ownership-{s.id}", conflict_type="Missing Ownership Data",
                title=f'"{s.title}" has no writers on file',
                description="Ownership cannot be verified without at least one writer credit.",
                severity="High", songs_involved=[s.title],
            ))

    for s in songs:
        if not s.publisher and s.total_earned > 0:
            conflicts.append(Conflict(
                id=f"publisher-dispute-{s.id}", conflict_type="Disputed Publisher Information",
                title=f'"{s.title}" has no publisher of record',
                description="Publishing royalties may be withheld until publisher information is confirmed.",
                severity="Medium", songs_involved=[s.title],
            ))

    for s in songs:
        if s.isrc and not s.iswc:
            conflicts.append(Conflict(
                id=f"isrc-iswc-{s.id}", conflict_type="Conflicting ISRC/ISWC Metadata",
                title=f'"{s.title}" is missing a matching ISWC',
                description="ISRC is on file but no ISWC is linked — recording and composition metadata are out of sync.",
                severity="Low", songs_involved=[s.title],
            ))

    normalized = {}
    for s in songs:
        for candidate in [s.title] + s.alternate_titles:
            key = candidate.split(" (")[0].strip().lower()
            normalized.setdefault(key, set()).add(s.id)
    for key, ids in normalized.items():
        if len(ids) > 1:
            titles = [s.title for s in songs if s.id in ids]
            conflicts.append(Conflict(
                id=f"duplicate-title-{_slug(key)}", conflict_type="Duplicate Title",
                title=f'Multiple songs share the title "{key.title()}"',
                description="Duplicate titles can cause royalties to be misattributed between recordings.",
                severity="Medium", songs_involved=titles,
            ))

    conflicts.sort(key=lambda c: _SEVERITY_ORDER.get(c.severity, 3))
    return conflicts


def get_recovery_summary(catalog, songs, earnings_trend):
    """Aggregates the missing-royalty scan into the shape the landing
    page's audit hero needs: one headline recovery number, a few
    supporting stats, per-source breakdown, and a recovery-over-time
    series -- all derived from the same findings used everywhere else,
    so a rescan here stays consistent with the rest of the app.
    """
    findings = get_missing_royalty_findings(catalog)
    money_left = money_left_on_table(findings)
    affected_recordings = sum(1 for s in songs if song_missing_issues(s))
    confidence_pct = round((money_left["high"] / money_left["total"]) * 100) if money_left["total"] else 0

    by_source = {}
    for f in findings:
        by_source[f.source] = by_source.get(f.source, 0) + f.estimated_value
    sources = sorted(
        ({"source": source, "amount": round(amount, 2)} for source, amount in by_source.items()),
        key=lambda entry: entry["amount"], reverse=True,
    )

    total = money_left["total"]
    months = [label for label, _ in earnings_trend]
    fractions = [0.15, 0.28, 0.42, 0.58, 0.78, 1.0]
    chart = [
        {"label": label, "value": round(total * fraction, 2)}
        for label, fraction in zip(months, fractions)
    ]

    return {
        "estimated_uncollected": total,
        "flagged_issues": len(findings),
        "affected_recordings": affected_recordings,
        "ready_to_claim": money_left["high"],
        "confidence_pct": confidence_pct,
        "sources": sources[:6],
        "chart": chart,
    }


def get_dashboard_story(total, findings, catalog_value, smart_recommendations):
    """The six-beat narrative: what you made, what you're missing, why,
    how to collect it, what your catalog may be worth, and the next move.
    Every value here is already computed elsewhere on the dashboard --
    this just picks the single most important item from each to answer
    the question in one line, so nothing has to be independently derived
    or kept in sync.
    """
    top_finding = findings[0] if findings else None
    return {
        "made": total,
        "missing_total": round(sum(f.estimated_value for f in findings), 2),
        "missing_count": len(findings),
        "top_finding": top_finding,
        "catalog_value_low": catalog_value["low"],
        "catalog_value_mid": catalog_value["mid"],
        "catalog_value_high": catalog_value["high"],
        "top_recommendation": smart_recommendations[0] if smart_recommendations else None,
    }
