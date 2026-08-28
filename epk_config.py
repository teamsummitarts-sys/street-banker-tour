"""Config-driven data for the EPK / Press Kit builder.

Composes an artist press kit from live catalog data (streams, earnings,
catalog value, top tracks) plus an editable artist profile block. The
derived stats stay in sync with the rest of the app; the profile fields
(bio, genres, socials, contact, press) are artist-supplied and live here
so they can be edited without touching the template.
"""

import re

from royalty_data import get_songs

# Artist-supplied profile. Not derivable from royalty data, so it lives
# here as editable config rather than being hard-coded in the template.
# The display name is intentionally omitted -- it comes from the shared
# account config so the EPK, sidebar chip, and settings stay consistent.
_EPK_PROFILE = {
    "tagline": "Synthwave-driven pop for late-night drives.",
    "bio": (
        "An independent artist blending analog synths with modern pop "
        "production. Self-released and self-owned, with a catalog that has "
        "quietly crossed the multi-million-stream mark across every major "
        "platform."
    ),
    "genres": ["Synthwave", "Electronic Pop", "Alternative"],
    "location": "Los Angeles, CA",
    "socials": [
        {"label": "Instagram", "handle": "@artiswar", "logo": "other"},
        {"label": "TikTok", "handle": "@artiswar", "logo": "tiktok"},
        {"label": "YouTube", "handle": "Art Is War", "logo": "youtube"},
        {"label": "Spotify", "handle": "Art Is War", "logo": "spotify"},
    ],
    "contact": {
        "booking": "booking@streetbanker.co",
        "management": "Street Banker Management",
        "press": "press@streetbanker.co",
    },
    # Editable pull quotes for the press strip.
    "press": [
        {"quote": "A gleaming, confident record that sounds bigger than its budget.", "source": "Indie Wave"},
        {"quote": "One of the most consistent independent catalogs we've heard this year.", "source": "Nightdrive Mag"},
    ],
}

# What a real artist starts with: nothing.
#
# _EPK_PROFILE above is the demo showcase. Handing it to a real account
# was the worst honesty bug in the app, because the EPK editor prefills
# its form from whatever get_epk_data returns - so an artist who opened
# /epk, glanced at a finished-looking kit and pressed Save Draft
# persisted two press quotes credited to publications that do not exist
# ("Indie Wave", "Nightdrive Mag"), a management company they had never
# hired, and contact addresses that were not theirs. Then published them
# on a public URL they would send to labels.
#
# The shape is still shown, as placeholder text in the form. Placeholders
# do not submit; values do. That distinction is the whole fix.
_EMPTY_PROFILE = {
    "tagline": "",
    "bio": "",
    "genres": [],
    "location": "",
    "socials": [],
    "contact": {"booking": "", "management": "", "press": ""},
    "press": [],
}


# Which sections the artist can toggle into the shareable kit.
_SECTIONS = [
    {"key": "bio", "label": "Artist Bio", "on": True},
    {"key": "stats", "label": "Career Stats", "on": True},
    {"key": "tracks", "label": "Top Tracks", "on": True},
    {"key": "press", "label": "Press Quotes", "on": True},
    {"key": "tour", "label": "Tour Dates", "on": True},
    {"key": "contact", "label": "Contact", "on": True},
    {"key": "media", "label": "Media Assets", "on": True},
]
_SECTION_KEYS = {s["key"] for s in _SECTIONS}


def _fmt_compact(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(int(n))


_SOCIAL_KEYS = [("instagram", "Instagram", "other"), ("tiktok", "TikTok", "tiktok"),
                ("youtube", "YouTube", "youtube"), ("spotify", "Spotify", "spotify")]


def normalize_epk_overrides(payload):
    """Validate + shape a saved editor payload into profile overrides."""
    p = payload or {}
    out = {}
    for key, cap in (("tagline", 120), ("bio", 1200), ("location", 80)):
        val = (p.get(key) or "").strip()
        if val:
            out[key] = val[:cap]
    genres = [g.strip() for g in (p.get("genres") or "").split(",") if g.strip()][:6]
    if genres:
        out["genres"] = genres
    socials = []
    for key, label, logo in _SOCIAL_KEYS:
        handle = ((p.get("socials") or {}).get(key) or "").strip()
        if handle:
            socials.append({"label": label, "handle": handle[:60], "logo": logo})
    if socials:
        out["socials"] = socials
    contact = {k: ((p.get("contact") or {}).get(k) or "").strip()[:120]
               for k in ("booking", "press", "management")}
    if any(contact.values()):
        out["contact"] = contact
    press = [{"quote": (q.get("quote") or "").strip()[:220],
              "source": (q.get("source") or "").strip()[:60],
              "url": (q.get("url") or "").strip()[:300]}
             for q in (p.get("press") or []) if (q.get("quote") or "").strip()][:3]
    if press:
        out["press"] = press
    if "show_sweep" in p:
        out["show_sweep"] = bool(p.get("show_sweep"))
    bg = (p.get("bg_color") or "").strip()
    if "bg_color" in p:
        out["bg_color"] = bg if re.fullmatch(r"#[0-9a-fA-F]{6}", bg) else ""
    if "sections_off" in p:
        out["sections_off"] = [k for k in (p.get("sections_off") or [])
                               if k in _SECTION_KEYS]
    video = (p.get("video_url") or "").strip()[:300]
    if "video_url" in p:
        out["video_url"] = video if video.startswith("http") else ""
    if "bandsintown_artist" in p:
        out["bandsintown_artist"] = (p.get("bandsintown_artist") or "").strip()[:100]
    store_url = (p.get("store_url") or "").strip()[:300]
    if "store_url" in p:
        out["store_url"] = store_url if store_url.startswith("http") else ""
    merch = []
    for item in (p.get("merch") or [])[:4]:
        title = (item.get("title") or "").strip()[:80]
        url = (item.get("url") or "").strip()[:300]
        if title and url.startswith("http"):
            merch.append({"title": title, "url": url,
                          "price": (item.get("price") or "").strip()[:20]})
    if "merch" in p:
        out["merch"] = merch
    return out


def _youtube_id(url):
    if "youtube.com/watch" in url and "v=" in url:
        return url.split("v=")[1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return None


def _video_embed(url):
    """YouTube watch/short URLs become embeddable; anything else stays a link."""
    vid = _youtube_id(url)
    return "https://www.youtube.com/embed/" + vid if vid else None


def _video_thumb(url):
    vid = _youtube_id(url)
    return "https://img.youtube.com/vi/%s/hqdefault.jpg" % vid if vid else None


def real_stats(statement_rows, track_count):
    """Headline figures built only from what the artist actually has.

    The press kit is the one page that leaves the building. It goes to
    labels, managers and partners, and until now every number on it came
    from the demo catalog - the same Total Streams, the same Catalog
    Earnings, the same Est. Catalog Value, identical for every account,
    rendered in gold and captioned "Mid valuation" with nothing to say it
    was illustrative.

    Fewer true numbers beat four invented ones. Anything that cannot be
    computed from the artist's own data is left out rather than filled
    in, so an empty press kit looks empty instead of looking successful.
    """
    stats = []
    rows = statement_rows or []
    if rows:
        import statements_engine
        clean = [{"title": r["title"], "source": r["source"],
                  "amount": r["amount"], "period": r["period"]} for r in rows]
        analysis = statements_engine.analyze(clean)
        # The annualised 3-5x band lives in build_royalty_summary, not in
        # analyze - analyze reports totals and coverage gaps.
        summary = statements_engine.build_royalty_summary(clean) or {}
        if analysis:
            stats.append({
                "label": "Catalog Earnings",
                "value": "${:,.0f}".format(analysis["total"]),
                "sub": "From %d statement row%s" % (
                    len(rows), "" if len(rows) == 1 else "s")})
            val = summary.get("valuation") or {}
            if val.get("mid"):
                stats.append({
                    "label": "Est. Catalog Value",
                    "value": "${:,.0f}".format(val["mid"]),
                    "sub": "${:,.0f}-${:,.0f} at 3-5x annualised".format(
                        val["low"], val["high"])})
    if track_count:
        stats.append({"label": "Releases", "value": str(track_count),
                      "sub": "In active catalog"})
    return stats


def get_epk_data(account, catalog_value, overrides=None, photo=None, assets=None,
                 tour_dates=None, stats_override=None, demo=False):
    """`demo` decides whose profile the kit starts from. Defaults to
    False so a caller that forgets it gets the safe, empty one rather
    than silently handing a real artist the invented identity."""
    songs = get_songs()
    total_streams = sum(s.streams for s in songs)
    total_earned = sum(s.total_earned for s in songs)

    # Aggregate platform earnings to name the artist's biggest platform.
    platform_totals = {}
    for s in songs:
        for platform, amount in (s.platform_earnings or {}).items():
            platform_totals[platform] = platform_totals.get(platform, 0) + amount
    top_platform = max(platform_totals, key=platform_totals.get) if platform_totals else "Spotify"

    top_tracks = sorted(songs, key=lambda s: s.streams, reverse=True)[:5]
    top_tracks = [
        {
            "title": s.title,
            "streams": s.streams,
            "streams_compact": _fmt_compact(s.streams),
            "earned": round(s.total_earned, 2),
            "owner": s.master_owner,
        }
        for s in top_tracks
    ]

    stats = [
        {"label": "Total Streams", "value": _fmt_compact(total_streams), "sub": "All platforms, all time"},
        {"label": "Catalog Earnings", "value": "${:,.0f}".format(total_earned), "sub": "Collected to date"},
        {"label": "Est. Catalog Value", "value": "${:,.0f}".format(catalog_value["mid"]), "sub": "Mid valuation"},
        {"label": "Releases", "value": str(len(songs)), "sub": "In active catalog"},
    ]

    # Real figures win outright. When the artist has statements or tracks
    # of their own, the demo stats above are discarded rather than padded
    # out - a press kit that shows two true numbers is worth more to a
    # label than one showing four that belong to nobody.
    stats_are_real = False
    if stats_override is not None:
        stats = stats_override
        stats_are_real = bool(stats_override)

    # Merge the artist's saved edits over the base profile. Real accounts
    # start empty; only the demo showcase starts from _EPK_PROFILE.
    base = _EPK_PROFILE if demo else _EMPTY_PROFILE
    profile = {k: (v.copy() if isinstance(v, (dict, list)) else v)
               for k, v in base.items()}
    o = overrides or {}
    for key in ("tagline", "bio", "location", "genres", "socials", "press"):
        if o.get(key):
            profile[key] = o[key]
    if o.get("contact"):
        profile["contact"] = {**profile["contact"],
                              **{k: v for k, v in o["contact"].items() if v}}

    # Editor prefill: flat handle map for the fixed social rows.
    social_handles = {key: "" for key, _, _ in _SOCIAL_KEYS}
    for s in profile["socials"]:
        for key, label, _ in _SOCIAL_KEYS:
            if s["label"] == label:
                social_handles[key] = s["handle"]

    # Section rail: persisted visibility + a readiness status per section.
    assets = assets or []
    tour_dates = tour_dates or []
    video_url = (o.get("video_url") or "").strip()
    off = set(o.get("sections_off") or [])
    complete = {
        "bio": bool(profile["bio"]),
        "stats": True,
        "tracks": True,
        "press": bool(profile["press"]),
        "tour": bool(tour_dates),
        "contact": any(profile["contact"].values()),
        "media": bool(assets or video_url),
    }
    sections = []
    for s in _SECTIONS:
        on = s["key"] not in off
        status = "Hidden" if not on else ("Complete" if complete[s["key"]] else "Needs Info")
        sections.append({"key": s["key"], "label": s["label"], "on": on,
                         "status": status})
    sections_on = {s["key"]: s["on"] for s in sections}

    return {
        "stats_are_real": stats_are_real,
        # True only when the showcase profile is standing in for an
        # artist who has written nothing. Lets the page say so.
        "profile_is_sample": bool(demo and not o),
        "name": account["name"],
        "initials": account["initials"],
        "profile": profile,
        "social_handles": social_handles,
        "photo": photo,
        "customized": bool(o),
        "show_sweep": bool(o.get("show_sweep")),
        "top_platform": top_platform,
        "stats": stats,
        "top_tracks": top_tracks,
        "sections": sections,
        "sections_on": sections_on,
        "video_url": video_url,
        "video_embed": _video_embed(video_url) if video_url else None,
        "video_thumb": _video_thumb(video_url) if video_url else None,
        "assets": assets,
        "logo_path": next((a["path"] for a in assets if a.get("kind") == "logo"), None),
        # Not a token: this is the artist's cover colour, stored and
        # validated as a hex. Exempt in tools/sweep_colours.py.
        "bg_color": o.get("bg_color") or "#141210",
        "bandsintown_artist": (o.get("bandsintown_artist") or "").strip(),
        "tour_dates": tour_dates,
        "store_url": (o.get("store_url") or "").strip(),
        "merch": o.get("merch") or [],
    }
