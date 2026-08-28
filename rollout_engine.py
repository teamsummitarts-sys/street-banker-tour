"""Rollout Engine generation engine.

Turns a release (title, artist, date, lyrics, assets, goal, tone) into a
dated social rollout: phased posting schedule, platform-specific captions
and hashtags, video edit plans (edit decision lists — the system never
pretends it rendered a video), and one Street Banker Links variant per
post so attribution flows back through ml_events.

Deterministic template generation for now; the AI provider slots in behind
generate_rollout() later without changing callers.
"""

from datetime import date, datetime, timedelta, timezone

CAMPAIGN_GOALS = [
    ("presaves", "Pre-saves"), ("streams", "Streams"), ("email", "Email capture"),
    ("merch", "Merch sales"), ("tickets", "Ticket sales"), ("tiktok", "TikTok sound usage"),
    ("community", "Fan community growth"), ("awareness", "General awareness"),
]

ROLLOUT_LENGTHS = [(3, "3-day quick push"), (7, "7-day rollout"), (14, "14-day rollout"),
                   (21, "21-day rollout"), (30, "30-day rollout")]

TONES = [("premium", "Premium"), ("street", "Street"), ("fan_first", "Fan-first"),
         ("high_energy", "High-energy")]

PLATFORMS = [
    ("instagram_reels", "Instagram Reels", "video"),
    ("instagram_feed", "Instagram Feed", "image"),
    ("instagram_stories", "Instagram Stories", "image"),
    ("tiktok", "TikTok", "video"),
    ("youtube_shorts", "YouTube Shorts", "video"),
    ("x", "X / Twitter", "text"),
    ("facebook", "Facebook", "image"),
    ("threads", "Threads", "text"),
    ("email", "Email", "text"),
    ("street_qr", "Street-team QR / Flyer", "image"),
]
PLATFORM_NAMES = dict((k, n) for k, n, _ in PLATFORMS)
PLATFORM_KIND = dict((k, kind) for k, _, kind in PLATFORMS)

# Ordered campaign phases mapped across the rollout window.
PHASES = ["tease", "announce", "presave_push", "storytelling", "lyric_reveal",
          "snippet", "countdown", "release_day", "post_release", "long_tail"]
PHASE_NAMES = {
    "tease": "Tease", "announce": "Announce", "presave_push": "Pre-save Push",
    "storytelling": "Storytelling", "lyric_reveal": "Lyric Reveal",
    "snippet": "Snippet Push", "countdown": "Countdown",
    "release_day": "Release Day", "post_release": "Post-Release",
    "long_tail": "Long-tail Push",
}

CONTENT_PILLARS = [
    "Announcement", "Artist story", "Lyric meaning", "Behind the scenes",
    "Snippet / hook", "Visual identity", "Fan call-to-action", "Countdown",
    "Release day", "Long-tail push",
]

# Caption templates per phase. Slots: {title} {artist} {date} {cta} {lyric} {days}
_CAPTIONS = {
    "tease": "Something's coming. {artist}. Soon.",
    "announce": "“{title}” — the new {artist} record. {date}. {cta}",
    "presave_push": "“{title}” drops {date}. Pre-save it now so it hits your library the second it's out. {cta}",
    "storytelling": "Every record has a story. “{title}” started in a room with no budget and one idea that wouldn't leave. {date}.",
    "lyric_reveal": "“{lyric}”\n\n— {title}, {date}. {cta}",
    "snippet": "15 seconds of “{title}”. The rest drops {date}. {cta}",
    "countdown": "{days} days. “{title}”. {cta}",
    "release_day": "“{title}” IS OUT NOW. Everywhere. Run it up. {cta}",
    "post_release": "“{title}” is out everywhere. If it soundtracked your week, share it with one person who needs it.",
    "long_tail": "Still spinning “{title}”? Add it to your playlist and keep it alive. {cta}",
}

_TONE_TAGS = {
    "premium": "#newmusic #independentartist",
    "street": "#newmusic #streetheat #nodeal",
    "fan_first": "#newmusic #fanfirst",
    "high_energy": "#newmusic #outnow #runitup",
}

_GOAL_CTA = {
    "presaves": "Pre-save at the link.",
    "streams": "Stream it at the link.",
    "email": "Join the inner circle at the link.",
    "merch": "Merch at the link.",
    "tickets": "Tickets at the link.",
    "tiktok": "Use the sound.",
    "community": "Link in bio — join us.",
    "awareness": "Link in bio.",
}

VIDEO_FORMATS = {
    "instagram_reels": ("9:16", 15), "tiktok": ("9:16", 15), "youtube_shorts": ("9:16", 30),
}


def _fmt_date(d):
    return d.strftime("%b %d")


def creative_direction(campaign):
    tone = dict(TONES).get(campaign["tone"], "Premium")
    goal = dict(CAMPAIGN_GOALS).get(campaign["goal"], "Awareness")
    return {
        "summary": ("A %d-day %s rollout for “%s” built around %s. Open quiet, "
                    "reveal in layers (story, lyrics, sound), compress into a countdown, "
                    "detonate on release day, then keep the record alive with fan-driven "
                    "long-tail pushes. Every post carries its own tracked link." % (
                        campaign["rollout_length"], tone.lower(), campaign["title"],
                        goal.lower())),
        "pillars": CONTENT_PILLARS,
        "tone": tone,
        "goal": goal,
    }


def _pick_lyric(lyrics):
    lines = [l.strip() for l in (lyrics or "").splitlines()
             if l.strip() and len(l.strip()) > 12]
    return lines[len(lines) // 3] if lines else ""


def _phase_for_day(day_index, total_days):
    """Map a day in the rollout window onto the phase arc. The last
    pre-release day is always countdown, release day and after get their
    own phases."""
    if day_index >= total_days:
        return {total_days: "release_day",
                total_days + 1: "post_release"}.get(day_index, "long_tail")
    remaining = total_days - day_index
    if remaining == 1:
        return "countdown"
    frac = day_index / max(total_days - 1, 1)
    arc = ["tease", "announce", "presave_push", "storytelling",
           "lyric_reveal", "snippet", "countdown"]
    return arc[min(int(frac * len(arc)), len(arc) - 1)]


def generate_rollout(campaign, lyrics="", video_asset_id=None, image_asset_id=None):
    """Returns a list of post dicts (without variant ids — the caller
    creates one Street Banker Links variant per post)."""
    platforms = campaign["platforms"] or ["instagram_reels", "tiktok", "x"]
    total = int(campaign["rollout_length"])
    release = None
    if campaign.get("release_date"):
        try:
            release = datetime.strptime(campaign["release_date"], "%Y-%m-%d").date()
        except ValueError:
            release = None
    if release is None:
        release = date.today() + timedelta(days=total)
    start = release - timedelta(days=total)
    cta = _GOAL_CTA.get(campaign["goal"], "Link in bio.")
    tags = _TONE_TAGS.get(campaign["tone"], "#newmusic")
    lyric = _pick_lyric(lyrics)
    posts = []
    # Release day plus two follow-ups: post-release and long-tail.
    for day_index in range(total + 3):
        post_date = start + timedelta(days=day_index)
        phase = _phase_for_day(day_index, total)
        if phase == "lyric_reveal" and not lyric:
            phase = "storytelling"
        platform = platforms[day_index % len(platforms)]
        days_left = (release - post_date).days
        caption = _CAPTIONS[phase].format(
            title=campaign["title"], artist=campaign["artist_name"] or "the artist",
            date=_fmt_date(release), cta=cta, lyric=lyric, days=max(days_left, 0))
        kind = PLATFORM_KIND.get(platform, "text")
        post = {
            "platform": platform,
            "post_type": kind,
            "phase": phase,
            "caption": caption,
            "hashtags": tags,
            "cta": cta,
            "scheduled_date": post_date.strftime("%Y-%m-%d"),
            "asset_id": video_asset_id if kind == "video" else image_asset_id,
        }
        # Video platforms get an edit decision list, not a fake render.
        if kind == "video" and video_asset_id:
            ratio, seconds = VIDEO_FORMATS.get(platform, ("9:16", 15))
            post["edit_plan"] = {
                "aspect_ratio": ratio,
                "start_seconds": 0,
                "end_seconds": seconds,
                "hook_text": "%s — %s" % (campaign["title"], PHASE_NAMES[phase]),
                "lyric_overlay": lyric if phase in ("lyric_reveal", "snippet") else "",
                "cta_overlay": cta,
                "edit_notes": ("Cut the strongest %ss from the source video. Open on the hook "
                               "text within the first second, %s keep the CTA overlay on the "
                               "final 3 seconds. Export %s vertical, captions burned in." % (
                                   seconds,
                                   "burn the lyric overlay mid-clip, " if lyric and phase in ("lyric_reveal", "snippet") else "",
                                   ratio)),
                "export_checklist": ["Trim to %ss" % seconds, "Add hook text overlay",
                                     "Add CTA end card", "Export %s" % ratio,
                                     "Attach tracked link in bio/caption"],
            }
        posts.append(post)
    return posts


def variant_name(platform, phase, post_date):
    return "rollout_%s_%s_%s" % (platform, phase, post_date)


def next_action(campaign, posts, assets):
    """One recommended next step for the dashboard."""
    if not posts:
        return "Generate your rollout — captions, schedule, and tracked links in one click."
    drafts = [p for p in posts if p["status"] == "draft"]
    if drafts:
        return "Review and approve %d draft post%s." % (len(drafts), "s" if len(drafts) != 1 else "")
    if not any(a["asset_type"] == "video" for a in assets):
        return "Upload a video clip to unlock Reels/TikTok/Shorts edit plans."
    approved = [p for p in posts if p["status"] == "approved"]
    if approved:
        return "%d approved post%s ready — post them and mark as posted." % (
            len(approved), "s" if len(approved) != 1 else "")
    return "Rollout is live — watch the performance page for what converts."


def platform_casts(caption, hashtags, title, link_url, avoid=None):
    """Rule-based recasts of one caption for each platform register.
    Same facts, different shape — a generator, not a chatbot. Phrases on
    the do-not-say list are stripped before casting."""
    text = (caption or "").strip()
    for phrase in (avoid or []):
        if phrase and phrase.lower() in text.lower():
            i = text.lower().find(phrase.lower())
            text = (text[:i] + text[i + len(phrase):]).replace("  ", " ")
            text = text.strip().lstrip(".,;:-— ").strip()
            if text:
                text = text[0].upper() + text[1:]
    first = text.split(". ")[0].rstrip(".")
    tags = (hashtags or "").strip()
    link = link_url or ""
    casts = [
        ("tiktok", "TikTok",
         "%s %s" % (first + ".", "Full song at the link in bio.")
         + ("\n" + tags if tags else "")),
        ("instagram_reels", "Instagram",
         text + "\n\nLink in bio." + ("\n\n" + tags if tags else "")),
        ("youtube_shorts", "YouTube",
         "%s\n\n%s%s" % (first + " — " + (title or "new single"),
                         text, ("\n\nListen: " + link) if link else "")),
        ("x", "X / Twitter",
         (first + ". " + link).strip()[:275]),
    ]
    return [{"key": k, "name": n, "text": t} for k, n, t in casts]
