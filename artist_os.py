"""Artist OS engines — the spine every OS-layer page reads.

Pure functions over a track's passport/lockbox JSON plus a `ctx` dict of
real account signals (statement lanes, fans, links, club members). No
invented numbers: estimates exist only where the artist's own statements
provide a basis, and every function says what it doesn't know.
"""

# (key, label, critical, fix_route) — critical means a rights/blocking
# issue: empty or negative stays RED and blocks Clean Release.
PASSPORT_FIELDS = [
    ("artist_name",     "Artist name",              False, None),
    ("legal_name",      "Legal name",               False, None),
    ("label",           "Label",                    False, None),
    ("release_title",   "Release title",            False, None),
    ("upc",             "UPC",                      False, "/identifiers"),
    ("isrc",            "ISRC",                     False, "/identifiers"),
    ("songwriters",     "Songwriters",              True,  None),
    ("producers",       "Producers",                False, None),
    ("publishers",      "Publishers",               False, "/publishing"),
    ("pro",             "PRO affiliation",          False, "/publishing"),
    ("mlc_status",      "MLC registration",         False, "/mechanicals"),
    ("soundexchange_status", "SoundExchange",       False, "/neighboring-rights"),
    ("content_id_status", "YouTube Content ID",     False, "/connections"),
    ("split_sheet_status", "Split sheet",           True,  None),
    ("sample_clearance", "Sample clearance",        True,  None),
    ("beat_license",    "Beat license",             True,  None),
    ("featured_approval", "Featured artist approval", True, None),
    ("master_owner",    "Master owner",             True,  None),
    ("pub_admin",       "Publishing administrator", False, "/publishing"),
    ("explicit",        "Explicit status",          False, None),
    ("artwork_rights",  "Artwork rights",           True,  None),
    ("ai_disclosure",   "AI disclosure",            True,  None),
    ("territories",     "Territory restrictions",   False, None),
    ("release_date",    "Release date",             False, "/releases"),
    ("dsp_routing",     "DSP profile routing",      False, "/connections"),
]

_NEGATIVE = ("blocked", "issue", "unresolved", "declined", "disputed", "no")
_POSITIVE_HINTS = ("registered", "cleared", "signed", "licensed", "approved",
                   "complete", "done", "yes", "clean", "routed", "n/a",
                   "none needed", "not applicable", "original", "owned")


def field_state(key, value, critical):
    """green / yellow / red for one passport field."""
    v = (value or "").strip().lower()
    if not v:
        return "red" if critical else "yellow"
    if any(n in v for n in _NEGATIVE):
        return "red"
    if v in ("pending", "in review", "submitted", "waiting"):
        return "yellow"
    return "green"


def passport_report(track):
    passport = track.get("passport") or {}
    items = []
    for key, label, critical, fix in PASSPORT_FIELDS:
        value = passport.get(key, "")
        if key == "release_title" and not value:
            value = track.get("release_title") or ""
        if key == "release_date" and not value:
            value = track.get("release_date") or ""
        state = field_state(key, value, critical)
        items.append({"key": key, "label": label, "value": value,
                      "state": state, "critical": critical, "fix": fix})
    reds = [i for i in items if i["state"] == "red"]
    yellows = [i for i in items if i["state"] == "yellow"]
    overall = "red" if reds else ("yellow" if yellows else "green")
    done = len([i for i in items if i["state"] == "green"])
    return {"items": items, "overall": overall,
            "greens": done, "yellows": len(yellows), "reds": len(reds),
            "pct": round(100 * done / len(items))}


# --- Rights / Split Lockbox ----------------------------------------------------

LOCKBOX_DOCS = [
    ("split_sheet",       "Split sheet",              True),
    ("producer_agreement", "Producer agreement",      False),
    ("beat_license",      "Beat license",             True),
    ("sample_clearance",  "Sample clearance",         True),
    ("featured_approval", "Featured artist approval", True),
    ("artwork_license",   "Artwork license",          False),
    ("video_license",     "Video license",            False),
    ("ai_voice_consent",  "AI voice consent",         False),
]

APPROVAL_STATES = ("pending", "signed", "declined", "needs resend")


def lockbox_report(track):
    box = track.get("lockbox") or {}
    docs = []
    for key, label, needed in LOCKBOX_DOCS:
        entry = box.get(key) or {}
        na = bool(entry.get("not_applicable"))
        uploaded = bool(entry.get("file"))
        approvals = entry.get("approvals") or []
        signed = all(a.get("state") == "signed" for a in approvals) if approvals else True
        declined = any(a.get("state") == "declined" for a in approvals)
        state = ("n/a" if na else
                 "declined" if declined else
                 "ready" if (uploaded and signed) else
                 "awaiting signatures" if uploaded else
                 "missing")
        docs.append({"key": key, "label": label, "required": needed,
                     "state": state, "file": entry.get("file", ""),
                     "approvals": approvals, "not_applicable": na})
    def ok(*keys):
        return all(d["state"] in ("ready", "n/a")
                   for d in docs if d["key"] in keys)
    caps = {
        "release":  ok("split_sheet", "beat_license", "sample_clearance",
                       "featured_approval"),
        "monetize": ok("split_sheet", "beat_license", "sample_clearance"),
        "sync":     ok("split_sheet", "beat_license", "sample_clearance",
                       "featured_approval", "artwork_license"),
        "pitch":    ok("split_sheet"),
    }
    return {"docs": docs, "caps": caps}


# --- Clean Release --------------------------------------------------------------

def clean_release(track, ctx):
    """17 checks -> score 0-100; red rights issues block submission.
    ctx carries real account signals; unknown stays honest yellow."""
    rep = passport_report(track)
    p = {i["key"]: i for i in rep["items"]}
    box = lockbox_report(track)

    def pf(key):  # passport field state
        return p[key]["state"]

    checks = [
        ("Audio quality confirmed",  "green" if (track.get("passport") or {}).get("audio_ok") else "yellow", False),
        ("Artwork specs confirmed",  "green" if (track.get("passport") or {}).get("artwork_ok") else "yellow", False),
        ("Metadata complete",        rep["overall"], True),
        ("Artist profile routing",   pf("dsp_routing"), False),
        ("Splits locked",            "green" if box["docs"][0]["state"] in ("ready", "n/a") else "red", True),
        ("Publishing set",           pf("publishers"), False),
        ("Mechanical collection (MLC)", pf("mlc_status"), False),
        ("SoundExchange",            pf("soundexchange_status"), False),
        ("Content ID",               pf("content_id_status"), False),
        ("AI disclosure",            pf("ai_disclosure"), True),
        ("Sample & beat licenses",   "green" if all(
            d["state"] in ("ready", "n/a") for d in box["docs"]
            if d["key"] in ("beat_license", "sample_clearance")) else "red", True),
        ("Featured artist approval", "green" if box["docs"][4]["state"] in ("ready", "n/a") else "red", True),
        ("Pre-save / smart link live", "green" if ctx.get("live_links") else "yellow", False),
        ("Spotify pitch reminder set", "green" if ctx.get("release_scheduled") else "yellow", False),
        ("Apple/YouTube profile ready", pf("dsp_routing"), False),
        ("Social assets prepared",   "green" if ctx.get("rollout_assets") else "yellow", False),
        ("Fan capture in place",     "green" if ctx.get("fans") else "yellow", False),
    ]
    items = [{"label": lbl, "state": st, "critical": crit}
             for lbl, st, crit in checks]
    score = round(sum({"green": 1, "yellow": 0.4, "red": 0}[i["state"]]
                      for i in items) / len(items) * 100)
    blocked = any(i["state"] == "red" and i["critical"] for i in items)
    return {"items": items, "score": score, "blocked": blocked}


# --- Royalty Lane Tracker -------------------------------------------------------

LANES = [
    ("master",       "Master royalties"),
    ("mechanicals",  "Publishing mechanicals"),
    ("pro",          "PRO performance"),
    ("soundexchange", "SoundExchange / digital performance"),
    ("neighboring",  "Neighboring rights"),
    ("content_id",   "YouTube Content ID"),
    ("ugc",          "TikTok / Meta / UGC"),
    ("sync",         "Sync licensing"),
    ("fan_sales",    "Direct fan sales"),
]

# Rough lane shares of a typical indie catalog's collected total — used
# ONLY to size an estimate from the artist's OWN statement revenue.
_LANE_SHARE = {"mechanicals": 0.06, "pro": 0.12, "soundexchange": 0.05,
               "neighboring": 0.04, "content_id": 0.05, "ugc": 0.04}


def lanes_from_sources(sources):
    """Map raw statement source names -> lanes with REAL income observed.
    Pure so it's testable; the classifier does the heavy lifting."""
    import royalty_types
    srcs = {(s or "").lower() for s in sources}
    buckets = {royalty_types.classify(s) for s in srcs}
    lanes = set()
    if "recording" in buckets:
        lanes.add("master")
    if "mechanical" in buckets:
        lanes.add("mechanicals")
    if "publishing" in buckets:
        lanes.add("pro")
    if "neighboring" in buckets:
        lanes.add("neighboring")
    if any("soundexchange" in s for s in srcs):
        lanes.add("soundexchange")
    if any(k in s for s in srcs for k in ("tiktok", "meta", "facebook", "instagram")):
        lanes.add("ugc")
    if any("youtube" in s for s in srcs):
        lanes.add("content_id")
    return lanes


def _lane_state(lane, track, ctx):
    passport = track.get("passport") or {}
    data_lanes = ctx.get("lanes_with_data") or set()
    if lane in data_lanes:
        return "claimed"     # real income for this lane appears in statements
    if lane == "master":
        return "connected" if ctx.get("statement_rows") else "missing"
    if lane == "mechanicals":
        s = field_state("mlc_status", passport.get("mlc_status"), False)
        return {"green": "connected", "yellow": "needs action", "red": "needs action"}[s] \
            if passport.get("mlc_status") or s != "yellow" else "missing"
    if lane == "pro":
        return "connected" if field_state("pro", passport.get("pro"), False) == "green" else "missing"
    if lane == "soundexchange":
        s = passport.get("soundexchange_status", "")
        return "connected" if field_state("soundexchange_status", s, False) == "green" \
            else ("in review" if s.strip().lower() in ("pending", "in review", "submitted") else "missing")
    if lane == "neighboring":
        return "connected" if "neighboring" in data_lanes else "missing"
    if lane == "content_id":
        s = passport.get("content_id_status", "")
        return "connected" if field_state("content_id_status", s, False) == "green" \
            else ("in review" if s.strip().lower() in ("pending", "in review", "submitted") else "missing")
    if lane == "ugc":
        return "connected" if "ugc" in data_lanes else (
            "needs action" if field_state("content_id_status",
                                          passport.get("content_id_status"), False) == "green"
            else "missing")
    if lane == "sync":
        return "connected" if ctx.get("sync_active") else "not eligible" \
            if (track.get("passport") or {}).get("sample_clearance", "").strip().lower() \
            and field_state("sample_clearance", passport.get("sample_clearance"), True) == "red" \
            else "missing"
    if lane == "fan_sales":
        return "connected" if ctx.get("club_members") else "missing"
    return "missing"


def lane_grid(track, ctx):
    total = float(ctx.get("statement_total") or 0)
    lanes = []
    for key, label in LANES:
        state = _lane_state(key, track, ctx)
        est = None
        if state in ("missing", "needs action") and key in _LANE_SHARE and total > 0:
            est = round(total * _LANE_SHARE[key], 2)
        lanes.append({"key": key, "label": label, "state": state,
                      "estimate": est,
                      "estimate_basis": ("share of your own statement earnings"
                                         if est is not None else None)})
    return lanes


# --- Missing Money Action Queue -------------------------------------------------

_DIFFICULTY = {"mlc_status": "medium", "pro": "medium", "soundexchange_status": "easy",
               "content_id_status": "easy", "split_sheet_status": "easy",
               "sample_clearance": "hard", "beat_license": "easy",
               "featured_approval": "medium", "isrc": "easy", "upc": "easy",
               "ai_disclosure": "easy", "artwork_rights": "easy",
               "songwriters": "easy", "master_owner": "easy"}

_DOCS_FOR = {"mlc_status": "Songwriter splits", "split_sheet_status": "Signed split sheet",
             "sample_clearance": "Clearance letter", "beat_license": "License PDF",
             "featured_approval": "Written approval", "artwork_rights": "Artwork license or ownership note"}


def action_queue(tracks_with_ctx):
    """tracks_with_ctx: [(track, ctx)] -> prioritized actions across catalog."""
    actions = []
    for track, ctx in tracks_with_ctx:
        rep = passport_report(track)
        for item in rep["items"]:
            if item["state"] == "green":
                continue
            urgency = "release-blocking" if item["critical"] else "collect sooner"
            actions.append({
                "track": track["title"], "track_id": track["id"],
                "lane": item["label"],
                "problem": "%s is %s on “%s”." % (
                    item["label"],
                    "missing" if not item["value"] else "unresolved",
                    track["title"]),
                "impact": None, "difficulty": _DIFFICULTY.get(item["key"], "easy"),
                "urgency": urgency, "fix": item["fix"] or ("/tracks/" + track["id"]),
                "docs": _DOCS_FOR.get(item["key"], ""),
                "status": "open", "critical": item["critical"],
            })
        for lane in lane_grid(track, ctx):
            if lane["state"] in ("missing", "needs action") and lane["estimate"]:
                actions.append({
                    "track": track["title"], "track_id": track["id"],
                    "lane": lane["label"],
                    "problem": "“%s” has no %s collection set up." % (
                        track["title"], lane["label"].lower()),
                    "impact": lane["estimate"], "difficulty": "medium",
                    "urgency": "money on the table",
                    "fix": "/tracks/" + track["id"], "docs": "",
                    "status": "open", "critical": False,
                })
    actions.sort(key=lambda a: (not a["critical"], -(a["impact"] or 0)))
    return actions


# --- Street Banker Certified ----------------------------------------------------

CERT_LEVELS = ["Unranked", "Verified", "Certified", "Priority",
               "Select", "Elite", "Upstream Ready"]


def certification(summary):
    """summary: real account aggregates -> (level, reasons_for_next).
    Rule-based only; every requirement names the real signal it reads."""
    checks = [
        ("Verified",       summary.get("tracks", 0) >= 1 and summary.get("passport_avg", 0) >= 40,
         "Add a track and complete 40% of its Metadata Passport"),
        ("Certified",      summary.get("passport_avg", 0) >= 70 and summary.get("clean_avg", 0) >= 60,
         "Reach 70% passport completion and a 60 Clean Release score"),
        ("Priority",       summary.get("lanes_connected", 0) >= 3 and summary.get("fans", 0) > 0,
         "Connect 3 royalty lanes and capture your first fans"),
        ("Select",         summary.get("clean_avg", 0) >= 80 and summary.get("lockbox_ready", 0) >= 1,
         "Hit an 80 Clean Release score with one fully signed lockbox"),
        ("Elite",          summary.get("passport_avg", 0) >= 90 and summary.get("lanes_connected", 0) >= 5,
         "Reach 90% passports and 5 connected lanes"),
        ("Upstream Ready", summary.get("clean_avg", 0) >= 90 and summary.get("reds", 1) == 0
                           and summary.get("statement_rows", 0) > 0,
         "Zero red rights issues, 90+ Clean Release, and real statements on file"),
    ]
    level = "Unranked"
    next_need = checks[0][2]
    for name, passed, need in checks:
        if passed:
            level = name
        else:
            next_need = need
            break
    else:
        next_need = None
    return {"level": level, "next": next_need,
            "ladder": [{"name": n, "passed": p, "need": d} for n, p, d in checks]}


# --- Release Autopilot stages ---------------------------------------------------

STAGES = ["Intake", "Clean-up", "Pre-save", "Pitch", "Rollout",
          "Release week", "Post-release", "Catalog follow-up"]


def autopilot_stage(release_date, today):
    """Which of the eight stages a release is in, from date math alone."""
    if not release_date:
        return "Intake"
    try:
        from datetime import date as _date
        rd = _date.fromisoformat(release_date[:10])
        td = _date.fromisoformat(today[:10])
    except ValueError:
        return "Intake"
    delta = (rd - td).days
    if delta > 45:
        return "Clean-up"
    if delta > 14:
        return "Pre-save"
    if delta > 7:
        return "Pitch"
    if delta > 0:
        return "Rollout"
    if delta >= -6:
        return "Release week"
    if delta >= -30:
        return "Post-release"
    return "Catalog follow-up"


def release_kit(artist, title, date, link_url):
    """Rule-based release copy — a generator, not a chatbot. Every draft
    is meant to be edited; [brackets] mark what only the artist knows."""
    artist = artist or "the artist"
    title = title or "the single"
    when = date or "[release date]"
    link = link_url or "[your smart link]"
    return {
        "captions": [
            "%s. %s. Everything I've got went into this one. Pre-save it now — %s" % (title, when, link),
            "The next chapter starts %s. \u201c%s\u201d is coming. Link in bio." % (when, title),
            "You've been asking. \u201c%s\u201d drops %s. Set your alarm." % (title, when),
        ],
        "email": {
            "subject": "\u201c%s\u201d drops %s \u2014 hear it first" % (title, when),
            "body": ("You're on this list because you actually listen.\n\n"
                     "\u201c%s\u201d is out %s. Pre-save it here and it lands in "
                     "your library the second it drops:\n%s\n\n"
                     "\u2014 %s") % (title, when, link, artist),
        },
        "sms": "%s: \u201c%s\u201d drops %s. Save it now \u2192 %s" % (artist, title, when, link),
        "pitch": ("\u201c%s\u201d \u2014 %s (%s). [One sentence on the sound.] "
                  "For fans of [comparable artists]. Written by [writers], produced "
                  "by [producers]. Full metadata and press kit available.") % (title, artist, when),
        "shorts": [
            "15s: the hook, captioned lyrics, one location, no cuts.",
            "20s: studio moment \u2014 the take where it clicked, raw audio up front.",
            "12s: text-on-screen \u2014 the one line of this song people will quote.",
        ],
    }


def campaign_plan(days, title, date):
    """14/30/60-day rollout plan. Windows reference real Street Banker
    tools; nothing here pretends to be a metric."""
    title = title or "the single"
    when = date or "release day"
    core = [
        ("Release day", "Everything fires at once",
         ["Smart link live and pinned everywhere",
          "Fan club drop with something extra (voice note, demo, story)",
          "Post the strongest short \u2014 hook up front"]),
        ("Days 1\u20137 after", "Keep it moving",
         ["Repost every fan reaction \u2014 reply to all of them",
          "Second short: a different 15 seconds of the song",
          "Check Royalty Lanes \u2014 confirm the release is collecting"]),
    ]
    pre14 = [
        ("14 days out", "Announce",
         ["Announce post with artwork \u2014 pin it",
          "Pre-save via your smart link on every profile",
          "Email + SMS the announcement to your fan list"]),
        ("10 days out", "Tease",
         ["First short: the hook only",
          "Behind-the-scenes post \u2014 studio, lyrics page, anything real",
          "Personally message your top fans from the CRM"]),
        ("7 days out", "Pitch",
         ["Submit the Spotify editorial pitch (needs 7 days)",
          "Send the playlist pitch draft to curators you actually know",
          "Update the EPK so press finds the new single"]),
        ("3 days out", "Final push",
         ["Countdown content daily from here",
          "Fan club early listen \u2014 members hear it first",
          "Confirm Clean Release is green \u2014 no red rights issues"]),
    ]
    plan = list(pre14)
    if days >= 30:
        plan = [
            ("30 days out", "Foundation",
             ["Lock the Metadata Passport \u2014 every field green",
              "Split sheets signed in the Rights Lockbox",
              "Artwork finalized in Cover Studio"]),
            ("21 days out", "Warm-up",
             ["Start posting again if you've been quiet \u2014 3x/week",
              "Seed the story of the song without naming the date",
              "Grow the fan list: link-in-bio to your Artist Hub"]),
        ] + plan
    if days >= 60:
        plan = [
            ("60 days out", "Build the base",
             ["Book the release-cycle content day \u2014 shoot everything once",
              "Line up 2\u20133 collaborators or creators for release week",
              "Set the budget: what goes to ads, what goes to content"]),
            ("45 days out", "Assets",
             ["Master delivered and checked in The Rack",
              "Shorts library: cut 6\u20138 clips before the cycle starts",
              "Photos + press shots into the EPK"]),
        ] + plan
    return {"days": days, "title": title, "date": when,
            "windows": plan + core,
            "brief": ("Creator brief \u2014 \u201c%s\u201d: we pay per deliverable, "
                      "not per follower. 1 short in your own voice using the hook "
                      "audio, posted between [dates]. No scripts \u2014 your take on "
                      "the song. [Rate], paid on posting. Tag @[artist]." % title),
            "ads": [
                "A/B the hook: same 15s clip, two different opening lines of text.",
                "Retarget smart-link visitors who didn't pre-save.",
                "Lookalike off your fan CRM emails \u2014 smallest budget first."]}


# --- Artist Twin strategist ------------------------------------------------------

def twin_report(tracks, ctx, pulse_snaps, queue, analysis=None):
    """A private A&R read on the real account. Sections without a data
    source say exactly what unlocks them — no invented analysis.

    `analysis` is the most recent Rack measurement, when one exists. It
    used to be listed as "audio analysis — planned, not faked", which
    stopped being true the moment the meter's numbers started persisting:
    loudness, dynamic range and true peak are measured to a published
    standard, so the Twin can read the record rather than only the
    paperwork around it.
    """
    sections = []

    def sec(title, state, lines):
        sections.append({"title": title, "state": state, "lines": lines})

    reports = [(t, passport_report(t), clean_release(t, ctx)) for t in tracks]
    if reports:
        lines = []
        for t, rep, cln in sorted(reports, key=lambda r: -r[2]["score"])[:3]:
            lines.append("%s \u2014 Clean Release %d, passport %d%%%s" % (
                t["title"], cln["score"], rep["pct"],
                ", BLOCKED on rights" if cln["blocked"] else ""))
        sec("Release readiness", "ready", lines)
        best = max(reports, key=lambda r: (not r[2]["blocked"], r[2]["score"], r[1]["pct"]))
        sec("Best single to lead with", "ready",
            ["%s \u2014 the cleanest rights and readiness in your catalog right now. "
             "Lead with what can actually ship." % best[0]["title"]])
    else:
        sec("Release readiness", "awaiting",
            ["Add your songs in Track Passports \u2014 readiness is read from real "
             "passports and lockboxes, so it starts empty, not invented."])
        sec("Best single to lead with", "awaiting",
            ["Unlocks once tracks exist in the spine."])

    if pulse_snaps and len(pulse_snaps) >= 2:
        new, old = pulse_snaps[0], pulse_snaps[-1]
        sec("Audience signal (Spotify/Deezer via Pulse)", "ready",
            ["Followers %s \u2192 %s, popularity %s \u2192 %s over your last %d snapshots."
             % (old["followers"], new["followers"], old["popularity"],
                new["popularity"], len(pulse_snaps)),
             "Real numbers from your connected profiles \u2014 not projections."])
    else:
        sec("Audience signal", "awaiting",
            ["Connect Artist Pulse and this reads your real Spotify followers, "
             "popularity, and Deezer fans over time."])

    rollout_lines = []
    if ctx.get("club_members"):
        rollout_lines.append("You have paying club members \u2014 every release should "
                             "hit the fan club first, then the public link.")
    if ctx.get("fans"):
        rollout_lines.append("%d fans in the CRM: announce by email before socials \u2014 "
                             "owned channels first." % ctx["fans"])
    if ctx.get("live_links"):
        rollout_lines.append("%d live smart link(s): route every bio and post through "
                             "them so clicks are yours to keep." % ctx["live_links"])
    sec("Rollout recommendation", "ready" if rollout_lines else "awaiting",
        rollout_lines or ["Create a smart link and capture fans \u2014 the rollout "
                          "engine reads what you own."])

    if queue:
        a = queue[0]
        sec("Next best action", "ready",
            ["%s (%s \u2014 %s difficulty)." % (a["problem"], a["urgency"], a["difficulty"]),
             "The full list lives in the Money Queue."])
    else:
        sec("Next best action", "ready",
            ["Nothing urgent in the queue \u2014 catalog is clean or empty. "
             "Add tracks to be sure."])

    # The one technical read that is real. Everything below it still waits
    # on a data source that has not landed.
    if analysis and analysis.get("measured_at"):
        import audio_readiness
        a = audio_readiness.assess(analysis)
        lines = [a["summary"]]
        for r in a["rulings"]:
            if r["level"] in ("problem", "watch"):
                lines.append("%s %s" % (r["headline"] + ".", r["detail"]))
        if len(lines) == 1:
            lines.append("Measured against the -1 dBTP ceiling and the "
                         "published platform loudness targets.")
        sec("Master read", "ready" if a["verdict"] in ("ok", "watch") else "action",
            lines)
    else:
        sec("Master read", "awaiting",
            ["Run a master through the Rack's loudness meter and this fills "
             "in: integrated loudness, dynamic range and true peak, measured "
             "to BS.1770-4 rather than estimated."])

    for title, unlock in [
        ("Audience match", "external listener analytics (Chartmetric-class data)"),
        ("City / geo opportunities", "geo data from streaming or ticketing feeds"),
        ("Comparable artists", "catalog-similarity data from an external provider"),
        ("Fan sentiment", "comment and message analysis you'd connect explicitly"),
        ("Cover art feedback", "a finished cover uploaded in Cover Studio"),
    ]:
        sec(title, "awaiting", ["Connects when %s lands. Until then this stays "
                                "empty rather than made up." % unlock])
    return sections
