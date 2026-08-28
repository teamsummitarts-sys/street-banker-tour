"""Street Banker Qualification Score.

The system for identifying artists who deserve more reach. Ten categories,
ten points each, every point computed from real account data — campaigns,
rollouts, fans, catalog metadata, EPK completeness, and actual link
traffic. No simulated momentum: if an artist hasn't done the work, the
score says so, and every weak category names the fix.
"""

import audio_readiness
import db as store
import links_engine
import links_store as mls
import rollout_store as ros


def _pts(value, full):
    """Scale a value against a 'full marks' threshold to 0-10."""
    if full <= 0:
        return 0
    return min(round(10 * value / full), 10)


def _pulse_momentum(user_id):
    """Verified Spotify popularity from the latest Artist Pulse snapshot.
    Popularity 60 = full marks — realistic ceiling for an independent act."""
    if store.get_pulse_profile(user_id) is None:
        return 0
    snaps = store.list_pulse_snapshots(user_id, limit=1)
    return _pts((snaps[-1].get("popularity", 0) if snaps else 0), 60)


def calculate(user_id):
    campaigns = [c for c in mls.list_campaigns(user_id) if not c.get("archived_at")]
    scores = [links_engine.calculate_street_banker_score(
        c, mls.get_destinations(c["id"]))["total"] for c in campaigns]
    best_score = max(scores) if scores else 0
    live = [c for c in campaigns if c["status"] == "live"]
    capture_on = any((c.get("settings") or {}).get("email_capture") for c in campaigns)
    fans = mls.list_fans(user_id)
    events = mls.account_event_counts(user_id)
    traffic = events.get("page_view", 0) + events.get("service_click", 0)
    rollouts = ros.list_campaigns(user_id)
    rollout_posts = []
    for r in rollouts:
        rollout_posts.extend(ros.list_posts(r["id"]))
    moved_posts = [p for p in rollout_posts if p["status"] in ("approved", "posted")]
    tracks = store.get_catalog_tracks(user_id)
    with_isrc = sum(1 for t in tracks if (t.get("meta") or {}).get("isrc"))
    epk = store.get_epk(user_id) or {}
    epk_data = epk.get("data") or {}
    epk_assets = store.get_epk_assets(user_id)
    covers = sum(1 for c in campaigns if c.get("cover_url"))

    # What the Rack measured about the actual record. Every other input to
    # this score is paperwork - link setup, artwork counts, ISRC presence -
    # so without this the score could call a release ready while its master
    # clipped on every platform it was headed for.
    analysis = store.latest_track_analysis(user_id)
    audio_pts, audio_max, audio_note = audio_readiness.readiness_points(analysis)

    # Real money, from uploaded statements. Same three facts capital_engine
    # uses - read directly rather than imported, to keep this module free
    # of the trust-score dependency chain.
    st_rows = store.get_statement_rows(user_id)
    income_total = sum(r["amount"] for r in st_rows)
    income_periods = {r.get("period") or "" for r in st_rows if r.get("period")}
    income_sources = {r.get("source") or "" for r in st_rows if r.get("source")}
    if st_rows:
        income_pts = min(10, (_pts(income_total, 2000) + _pts(len(income_periods), 6)
                              + _pts(len(income_sources), 3)) // 2)
        income_note = ("${:,.0f} on record across {} period{} and {} source{}."
                       .format(income_total, len(income_periods),
                               "" if len(income_periods) == 1 else "s",
                               len(income_sources),
                               "" if len(income_sources) == 1 else "s"))
    else:
        income_pts = 0
        income_note = ("Upload a royalty statement — this score gates a "
                       "catalog valuation review and cannot speak to money "
                       "without any.")

    categories = [
        ("Release Readiness", _pts(best_score, 100),
         "Best campaign scores %d/100 — run the Clean Release checklist." % best_score),
        # The only category that listens to the audio.
        ("Master Quality", audio_pts * 10 // max(audio_max, 1), audio_note),
        ("Smart Link Setup", _pts(sum(1 for c in live
                                      if len(mls.get_destinations(c["id"])) >= 3), 1),
         "Publish a campaign with at least three streaming destinations."),
        ("Fan Capture", (5 if capture_on else 0) + _pts(len(fans), 10) // 2,
         "Enable email capture and start converting traffic into owned fans."),
        ("Campaign Strength", _pts(len(moved_posts), 8),
         "Generate a rollout and approve or post its content."),
        ("Asset Completeness", _pts((1 if epk.get("photo") else 0)
                                    + len(epk_assets) + covers, 5),
         "Upload press photo, logo, cover art, and campaign covers."),
        ("Metadata Quality", _pts(with_isrc, max(len(tracks), 1)) if tracks else 0,
         "Add tracks to your catalog — identifiers auto-pull ISRCs."),
        ("Social Consistency", _pts(len(epk_data.get("socials") or []), 3),
         "Add your social handles to the press kit."),
        ("Professional Presentation", _pts((2 if epk_data.get("bio") else 0)
                                           + (2 if epk_data.get("press") else 0)
                                           + (1 if (epk_data.get("contact") or {}) else 0), 5),
         "Complete your EPK: bio, press quotes, and contact info."),
        ("Streaming Momentum", max(_pts(traffic, 50), _pulse_momentum(user_id)),
         "Real link traffic and verified Spotify presence are the signal — "
         "share your campaign links and connect Artist Pulse."),
        ("Catalog Depth", _pts(len(tracks) + len(campaigns), 6),
         "Build the catalog: more releases, more tracked campaigns."),
        ("Income on Record", income_pts, income_note),
    ]

    # Normalised to 0-100 rather than summed. Every category is worth ten
    # points, so a bare sum silently rescales the whole thing each time
    # one is added - which happened: a category added earlier today took
    # the maximum to 110 and made every unlock threshold about nine
    # percent easier to reach without anyone changing a threshold.
    total = round(sum(pts for _, pts, _ in categories)
                  / float(len(categories) * 10) * 100)
    strengths = [(name, pts) for name, pts, _ in categories if pts >= 7]
    needs_work = [(name, pts, note) for name, pts, note in categories if pts < 7]

    badges = []
    if best_score >= 80:
        badges.append("Release Ready")
    if moved_posts:
        badges.append("Campaign Active")
    if tracks and with_isrc == len(tracks):
        badges.append("Data Verified")
    if capture_on:
        badges.append("Fan Capture Enabled")
    if len(tracks) + len(campaigns) >= 4:
        badges.append("Catalog Growth")
    if total >= 75:
        badges.append("Upstream Review Candidate")

    unlocks = [
        ("Primary Artist Profile placement", 60),
        ("Catalog valuation review", 65),
        ("Playlist pitching support", 70),
        ("Higher-touch campaign review", 75),
        ("Distribution rate improvement", 80),
        ("Upstream review", 85),
    ]
    unlocks = [(label, threshold, total >= threshold) for label, threshold in unlocks]

    if total >= 75:
        recommendation = "High potential"
    elif total >= 50:
        recommendation = "Approve — with guidance"
    else:
        recommendation = "Needs work"

    # Remember today's reading. Guarded: a history write must never be
    # the reason a page fails to render.
    try:
        store.record_score(user_id, "qualification", total, {"categories": [[n, p] for n, p, _ in categories]})
    except Exception:
        pass
    return {"total": total, "categories": categories, "strengths": strengths,
            "needs_work": needs_work, "badges": badges, "unlocks": unlocks,
            "recommendation": recommendation}
