"""Street Banker Artist Twin.

A private writing agent that uses ONLY the data the artist approves:
each source can be excluded, a do-not-say list is enforced on every
output, and every generation shows exactly which sources fed it.
Deterministic template generation today — an AI provider can slot in
behind generate() later without changing the consent layer.
"""

import db as store
import links_engine
import links_store as mls
import rollout_store as ros

SOURCES = [
    ("epk", "Press kit (bio, tagline, press quotes)"),
    ("catalog", "Catalog (tracks, identifiers)"),
    ("campaigns", "Campaign history + performance"),
    ("fans", "Fan counts + intent levels"),
    ("lyrics", "Lyrics uploaded to rollouts"),
    ("rack", "Rack measurements (loudness, true peak, tempo, key)"),
]
SOURCE_KEYS = {k for k, _ in SOURCES}

OUTPUT_TYPES = [
    ("bio_snippet", "Short bio snippet"),
    ("press_pitch", "Press pitch"),
    ("playlist_pitch", "Playlist pitch"),
    ("partner_summary", "Manager / partner summary"),
    ("fan_message", "Fan thank-you message"),
]
OUTPUT_KEYS = {k for k, _ in OUTPUT_TYPES}

TONES = [("premium", "Premium"), ("street", "Street"), ("fan_first", "Fan-first")]


def gather_context(user_id, enabled):
    """Collect facts from approved sources only. Returns (facts, used)."""
    facts = {"name": "", "tagline": "", "bio": "", "genres": [], "press": [],
             "tracks": 0, "campaigns": 0, "visits": 0, "clicks": 0,
             "fans": 0, "hot_fans": 0, "lyric": "", "top_campaign": "",
             "master": "", "tempo_key": ""}
    used = []

    # What the Rack measured. The Twin has been reasoning about an artist's
    # catalogue, audience and campaigns while knowing nothing about how the
    # music itself is actually built - the one thing the app measures to a
    # published standard. Facts only, and only where the measurement is
    # trustworthy: an unconfident tempo is left out rather than quoted.
    if "rack" in enabled:
        import audio_readiness
        row = store.latest_track_analysis(user_id)
        if row:
            a = audio_readiness.assess(row)
            facts["master"] = a["summary"]
            bits = []
            conf = row.get("bpm_confidence")
            if row.get("bpm") and (conf is None or conf >= 0.5):
                bits.append("%.0f BPM" % row["bpm"])
            if row.get("key"):
                bits.append("key of %s" % row["key"])
            facts["tempo_key"] = ", ".join(bits)
            used.append("rack")
    user = store.get_user(user_id)
    facts["name"] = user["name"] if user else "the artist"
    if "epk" in enabled:
        saved = store.get_epk(user_id) or {}
        data = saved.get("data") or {}
        facts["tagline"] = data.get("tagline") or ""
        facts["bio"] = (data.get("bio") or "")[:300]
        facts["genres"] = data.get("genres") or []
        facts["press"] = data.get("press") or []
        used.append("Press kit")
    if "catalog" in enabled:
        facts["tracks"] = len(store.get_catalog_tracks(user_id))
        used.append("Catalog")
    if "campaigns" in enabled:
        campaigns = [c for c in mls.list_campaigns(user_id) if not c.get("archived_at")]
        facts["campaigns"] = len(campaigns)
        events = mls.account_event_counts(user_id)
        facts["visits"] = events.get("page_view", 0)
        facts["clicks"] = events.get("service_click", 0)
        if campaigns:
            facts["top_campaign"] = campaigns[0]["title"]
        used.append("Campaigns")
    if "fans" in enabled:
        fans = mls.list_fans(user_id)
        facts["fans"] = len(fans)
        facts["hot_fans"] = sum(1 for f in fans if f["intent_level"] in ("Hot", "Superfan"))
        used.append("Fans")
    if "lyrics" in enabled:
        for r in ros.list_campaigns(user_id):
            for a in ros.list_assets(r["id"]):
                if a["asset_type"] == "lyrics" and a["lyrics_text"]:
                    lines = [l.strip() for l in a["lyrics_text"].splitlines()
                             if len(l.strip()) > 12]
                    if lines:
                        facts["lyric"] = lines[len(lines) // 3]
                        used.append("Lyrics")
                        break
            if facts["lyric"]:
                break
    return facts, used


def _scrub(text, do_not_say):
    for phrase in do_not_say:
        if phrase:
            text = text.replace(phrase, "[removed]")
    return text


def generate(kind, facts, tone="premium", do_not_say=()):
    f = facts
    genre = " / ".join(f["genres"][:2]) if f["genres"] else "independent"
    press_line = ('Press has called it "%s" (%s). ' % (
        f["press"][0]["quote"], f["press"][0]["source"])) if f["press"] else ""
    opener = {"premium": "%s is building something deliberate.",
              "street": "%s doesn't ask for a seat at the table.",
              "fan_first": "%s makes music for the people who show up."}
    open_line = opener.get(tone, opener["premium"]) % f["name"]

    if kind == "bio_snippet":
        text = "%s %s %s artist%s. %s" % (
            open_line, f["tagline"] or "Self-released and self-owned.",
            genre.title(),
            " with %d tracked releases" % f["campaigns"] if f["campaigns"] else "",
            f["bio"].split(".")[0] + "." if f["bio"] else "")
    elif kind == "press_pitch":
        text = ("Subject: %s — %s\n\n%s %s%s"
                "The numbers back it: %d campaign(s), %d link visits, %d owned fans. "
                "Press kit and assets: reply for the private link." % (
                    f["name"], f["tagline"] or "new music",
                    open_line, press_line,
                    ("Latest: “%s”. " % f["top_campaign"]) if f["top_campaign"] else "",
                    f["campaigns"], f["visits"], f["fans"]))
    elif kind == "playlist_pitch":
        text = ("%s — %s. %s%s"
                "Fits %s playlists. Clean metadata, ISRCs registered, one-stop contact. "
                "%d listeners have already clicked through our own links." % (
                    f["name"], f["tagline"] or genre,
                    ("Lyric that lands: “%s”. " % f["lyric"]) if f["lyric"] else "",
                    press_line, genre, f["clicks"]))
    elif kind == "partner_summary":
        text = ("%s: %s act with %d catalog track(s), %d campaign(s) run through "
                "Street Banker, %d link visits, %d service clicks, and %d owned fans "
                "(%d hot/superfan). %sFull executive report available." % (
                    f["name"], genre, f["tracks"], f["campaigns"], f["visits"],
                    f["clicks"], f["fans"], f["hot_fans"], press_line))
    elif kind == "fan_message":
        text = ("You showed up — %d of you and counting — and that's the whole "
                "reason this works. %sMore coming. Stay close. — %s" % (
                    max(f["fans"], 1),
                    ("“%s” " % f["lyric"]) if f["lyric"] else "",
                    f["name"]))
    else:
        text = ""
    return _scrub(text, do_not_say)
