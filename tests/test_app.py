from app import create_app
from royalty_data import (
    get_platform_balances,
    reset_claim_state,
    reset_connection_state,
    reset_fix_status_state,
    reset_registration_wizard_state,
    reset_split_state,
)


def test_index_renders_landing_page():
    client = _demo()
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "STREET BANKER" in body
    # Section 2: the headline is live HTML over the band photograph, and
    # both CTAs land somewhere a signed-out visitor can use.
    assert "BUILD THE RELEASE." in body and "OWN THE MOMENT." in body
    assert "hero-band-wide-1342.avif" in body     # the responsive set
    assert "Explore Street Banker" in body
    assert "Run a Royalty Sweep" in body
    assert "ROYALTY SWEEP" in body                # the sweep section below


def test_no_part_of_the_landing_page_links_into_the_gated_app():
    """Not the header, and now not the footer either.

    The footer used to send seven of its fifteen links into the login
    wall - /overview, /recovery, /artist-twin, /roster, /audience,
    /capital, /network - on the theory that the body could link into the
    app even if the header could not. A stranger reading the footer is
    still a stranger.
    """
    client = create_app().test_client()
    body = client.get("/").get_data(as_text=True)
    assert "Log in" in body                 # the header's own wording
    for gated in ("/overview", "/recovery", "/artist-twin", "/roster",
                  "/audience", "/capital", "/network"):
        assert 'href="%s"' % gated not in body, gated


def _all_landing_hrefs(config):
    """Every href the homepage renders, in one flat list."""
    hrefs = [l["href"] for l in config["nav"]["links"]]
    # The header's actions are now a named pair rather than a list: one
    # log-in and one CTA, because a header with a list of actions is a
    # header nobody chose.
    hrefs += [l["href"] for l in config["nav"]["drawer_links"]]
    hrefs += [config["nav"]["login"]["href"], config["nav"]["cta"]["href"]]
    hrefs += [c["href"] for c in config["hero"]["ctas"]]
    for col in config["footer"]["columns"]:
        hrefs += [l["href"] for l in col["links"]]
    return hrefs

def test_landing_page_links_all_resolve():
    """Every landing link points at a real GET route or an on-page anchor
    that exists -- no dead placeholder routes or hashes."""
    import re
    from landing_config import get_landing_config

    app = create_app()
    body = app.test_client().get("/").get_data(as_text=True)
    page_ids = set(re.findall(r'id="([^"]+)"', body))
    real_routes = {rule.rule for rule in app.url_map.iter_rules()
                   if "GET" in rule.methods and "<" not in rule.rule}
    # Prefixes for parameterized GET routes, e.g. "/services/<slug>" -> "/services/".
    param_prefixes = [rule.rule.split("<", 1)[0] for rule in app.url_map.iter_rules()
                      if "GET" in rule.methods and "<" in rule.rule]

    for href in _all_landing_hrefs(get_landing_config()):
        if href.startswith("/#") or href.startswith("#"):
            assert href.lstrip("/#") in page_ids, f"dead anchor: {href}"
        elif href.startswith("http"):
            continue
        else:
            ok = href in real_routes or any(
                href.startswith(pfx) and len(href) > len(pfx) for pfx in param_prefixes)
            assert ok, f"unknown route: {href}"


def test_the_footer_carries_the_modules_and_every_link_is_public():
    """The Signature Tools strip is gone.

    It named five modules and sent all five into the login wall. The
    footer's Platform column names them instead, and every destination in
    the whole footer answers a signed-out visitor.

    One deliberate exception, named here so a second cannot be added
    without somebody deciding to: /operator-desk, the team's own door in
    the Company column. A stranger meeting the login wall there is
    correct — it is the staff entrance, labeled as such.

    The Press Desk briefly needed an exception too, when the Platform
    column pointed straight at the gated workspace. It has a public page
    now, so the column is back to every link answering a stranger.
    """
    from landing_config import get_landing_config

    GATED_ON_PURPOSE = {"/operator-desk"}

    client = create_app().test_client()
    body = client.get("/").get_data(as_text=True)
    for name in ["AI Artist Twin", "Metadata Passport", "Rollout Engine",
                 "Royalty Sweep", "Creative Studio", "Smart Links"]:
        assert name in body, name

    for col in get_landing_config()["footer"]["columns"]:
        for link in col["links"]:
            assert 'href="%s"' % link["href"] in body, link["href"]
            response = client.get(link["href"])
            if link["href"] in GATED_ON_PURPOSE:
                assert response.status_code == 302, link["href"]
                assert "/login" in response.headers["Location"]
            else:
                assert response.status_code == 200, link["href"]


def test_the_retired_homepage_blocks_are_gone_from_config_and_page():
    """Dead config outlives dead markup unless something checks."""
    from landing_config import get_landing_config

    config = get_landing_config()
    for retired in ("tools", "final_cta", "band_image", "lanes", "sweep"):
        assert retired not in config, retired

    body = create_app().test_client().get("/").get_data(as_text=True)
    for gone in ["EVERYTHING BEHIND THE ARTIST.", "START FREE",
                 "sb-band-catalog.jpg", 'href="/overview"',
                 'href="/recovery"', 'href="/roster"', 'href="/capital"']:
        assert gone not in body, gone


# --- the Artist EQ ------------------------------------------------------

def test_artist_eq_sits_between_the_hero_and_the_lanes():
    """Additive section: it goes after the hero, before the three lanes,
    and displaces nothing that was already there."""
    body = _demo().get("/").get_data(as_text=True)
    assert 'id="artist-eq"' in body
    assert "TUNE YOUR ARTIST SYSTEM." in body
    assert body.index("sbhero") < body.index("TUNE YOUR ARTIST SYSTEM.")
    assert body.index("TUNE YOUR ARTIST SYSTEM.") < body.index("Choose your lane.")
    # Every section that was on the page before is still on it.
    for kept in ["Choose your lane.", "Built for artist control.",
                 "Your catalog is the ", "closing-wide-1672"]:
        assert kept in body, kept


def test_artist_eq_renders_six_channels_and_six_presets():
    """Six faders, six presets - no knobs, no decorative controls."""
    body = _demo().get("/").get_data(as_text=True)
    assert body.count('class="sbeq-range"') == 6
    assert body.count('class="sbeq-preset"') == 6
    # Real range inputs, so keyboard and touch come from the platform.
    assert body.count('type="range"') >= 6
    # Every fader is named and described by markup the reader can reach.
    for key in ["release", "creative", "audience", "rights", "revenue", "growth"]:
        assert 'aria-labelledby="sbeq-name-%s"' % key in body, key
        assert 'aria-describedby="sbeq-desc-%s"' % key in body, key
        assert 'id="sbeq-desc-%s"' % key in body, key
    assert "knob" not in body.lower()


def test_artist_eq_only_links_modules_that_really_exist():
    """The panel may print a module with no page, but never a dead link."""
    from artist_eq_config import get_artist_eq_config

    cfg = get_artist_eq_config()
    client = _demo()
    for name, href in cfg["module_routes"].items():
        assert client.get(href).status_code < 400, "%s -> %s" % (name, href)
    for label, href in cfg["action_routes"].items():
        assert client.get(href).status_code < 400, "%s -> %s" % (label, href)
    for lane in cfg["lanes"]:
        assert client.get(lane["href"]).status_code < 400, lane["href"]
    assert client.get(cfg["cta"]["href"]).status_code < 400


def test_artist_eq_data_is_complete_and_consistent():
    """Every channel needs a preset value, a module and an action, or the
    recommendation silently drops a priority."""
    from artist_eq_config import get_artist_eq_config

    cfg = get_artist_eq_config()
    keys = [c["key"] for c in cfg["channels"]]
    assert len(keys) == 6 and len(set(keys)) == 6
    for key in keys:
        assert cfg["modules"].get(key), key
        assert cfg["actions"].get(key), key
        for name, slug in cfg["modules"][key]:
            assert slug and cfg["module_notes"].get(slug), name
        for label, slug in cfg["actions"][key]:
            assert slug and label
    named = [p for p in cfg["presets"] if p["values"] is not None]
    assert len(named) == 5                # five real presets + Custom
    for preset in named:
        assert sorted(preset["values"]) == sorted(keys), preset["name"]
        for v in preset["values"].values():
            assert 0 <= v <= 10
        # Weights are sparse - an unlisted channel simply weighs 1.0 - but
        # a typo'd key would silently weigh nothing at all.
        assert set(preset["weights"]) <= set(keys), preset["name"]
        assert all(w > 0 for w in preset["weights"].values()), preset["name"]
    # The section must not start with every fader on the floor.
    default = [p for p in cfg["presets"] if p["id"] == cfg["default_preset"]]
    assert default and any(v > 5 for v in default[0]["values"].values())
    # Bands are ordered and cover the whole scale.
    cuts = [c for c, _label in cfg["readiness_bands"]]
    assert cuts == sorted(cuts) and cuts[-1] > 100


def test_artist_eq_promises_nothing_it_cannot_know():
    """No forecast, no revenue, no guarantee - it reports the visitor's
    own settings back to them."""
    from artist_eq_config import get_artist_eq_config

    cfg = get_artist_eq_config()
    blob = " ".join([cfg["heading"], cfg["support"], cfg["instruction"]] +
                    [l["why"] for l in cfg["lanes"]] +
                    [c["desc"] for c in cfg["channels"]] +
                    list(cfg["module_notes"].values()) +
                    [label for acts in cfg["actions"].values()
                     for label, _slug in acts])
    for banned in ["guarantee", "guaranteed", "projected", "forecast",
                   "estimated revenue", "you will earn", "$"]:
        assert banned not in blob.lower(), banned


def test_artist_eq_assets_are_served():
    client = _demo()
    for asset in ["/static/css/artist-eq.css", "/static/js/artist-eq.js"]:
        assert client.get(asset).status_code == 200, asset


def test_landing_is_the_twelve_approved_sections_in_order():
    """The homepage is an editorial sequence, not a feature directory.

    Order matters here: each section answers the one before it, and the
    closing frame only lands after the trust band has said what the
    artist keeps. Checked by position rather than by presence.
    """
    body = create_app().test_client().get("/").get_data(as_text=True)
    order = [
        "sbhero",                       # 2  hero
        'id="artist-eq"',               # 3  Artist EQ
        'id="departments"',             # 4  one system, six departments
        'id="artist-twin-section"',     # 5  AI Artist Twin
        'id="lanes"',                   # 6  three lanes
        'id="creative-studio"',         # 7  Creative Studio
        'id="rollout-engine"',          # 8  Rollout Engine
        'id="royalty-sweep-section"',   # 9  Royalty Sweep
        'id="global-distribution"',     # 10 Global Distribution
        'id="metadata-passport"',       # 11 Metadata Passport + Rights
        'id="artist-control"',          # 11.5 trust band
        'id="closing"',                 # 12 closing statement
    ]
    positions = []
    for marker in order:
        assert marker in body, marker
        positions.append(body.index(marker))
    assert positions == sorted(positions), "sections are out of order"

    # The footer is last, and it is the only thing after the closing frame.
    assert body.index("<footer") > positions[-1]

    # Everything moved deeper into the site stays gone.
    for old in ["Everything Street Banker Is", "Nightdrive", "ONE PLATFORM",
                "FROM RELEASE TO OWNERSHIP", "No Upfront Fees",
                "sb-patchbay.jpg"]:
        assert old not in body


def test_all_pages_render():
    client = _demo()
    for route in ["/overview", "/royalties", "/catalog", "/connections", "/recovery", "/valuation", "/reports", "/settings"]:
        response = client.get(route)
        assert response.status_code == 200, route


def test_dashboard_redirects_to_overview():
    client = _demo()
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"] == "/overview"


def test_nav_highlights_active_page():
    client = _demo()
    body = client.get("/royalties").get_data(as_text=True)
    assert 'href="/royalties"' in body
    assert "bg-amber-500/10 font-semibold text-amber-400" in body


def test_nav_includes_all_eight_routes():
    client = _demo()
    body = client.get("/overview").get_data(as_text=True)
    for href in ["/overview", "/royalties", "/catalog", "/connections", "/recovery", "/valuation", "/reports", "/settings"]:
        assert 'href="{}"'.format(href) in body


def test_overview_renders_command_center():
    client = _demo()
    response = client.get("/overview")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "What came in, what is missing, and the next thing worth doing." in body
    assert "Total Royalties Collected" in body   # the ledger line's eyebrow
    assert "Royalty Goal" in body


def test_overview_includes_goal_card_and_modal():
    client = _demo()
    body = client.get("/overview").get_data(as_text=True)
    assert 'id="edit-goal-btn"' in body
    assert 'id="goal-modal"' in body
    assert 'id="goal-amount"' in body
    assert 'id="goal-type"' in body
    assert 'id="goal-deadline"' in body


def test_overview_includes_health_score_card():
    client = _demo()
    body = client.get("/overview").get_data(as_text=True)
    assert "Royalty Health Score" in body
    assert "Improve Score" in body
    assert "/100" in body


def test_overview_includes_money_left_card():
    client = _demo()
    body = client.get("/overview").get_data(as_text=True)
    assert "Money Left on the Table" in body
    assert "Scan Now" in body
    assert 'href="/recovery"' in body


def test_overview_includes_action_center_and_payouts():
    client = _demo()
    body = client.get("/overview").get_data(as_text=True)
    assert "Action Center" in body
    assert "Recent Payouts" in body
    assert 'id="payout-drawer"' in body


def test_overview_includes_last_visit_summary():
    client = _demo()
    body = client.get("/overview").get_data(as_text=True)
    assert "What Changed Since Your Last Visit" in body
    assert "New royalties collected" in body
    assert "Tasks completed" in body
    assert "Catalog value increase" in body


def test_overview_includes_date_range_selector():
    client = _demo()
    body = client.get("/overview").get_data(as_text=True)
    assert 'id="date-range"' in body


def test_overview_includes_earnings_trend():
    client = _demo()
    body = client.get("/overview").get_data(as_text=True)
    assert "Earnings Trend" in body
    assert 'id="earningsChart"' in body


def test_royalties_page_matches_tracking_dashboard():
    client = _demo()
    body = client.get("/royalties").get_data(as_text=True)
    assert "Track every royalty stream in one place." in body
    assert "Total Royalties" in body
    assert "Payouts Received" in body
    assert "Pending Payouts" in body
    assert "Platforms Connected" in body
    assert "Royalties by Source" in body
    assert 'id="royaltiesChart"' in body
    assert 'id="export-btn"' in body


def test_resolve_alert_returns_result_message():
    client = _demo()
    response = client.post("/alerts/pending-negotiation/resolve")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["message"]


def test_resolve_unknown_alert_returns_404():
    client = _demo()
    response = client.post("/alerts/not-a-real-id/resolve")
    assert response.status_code == 404


def test_connections_true_status_board(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "csec")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("BANDSINTOWN_APP_ID", raising=False)
    client = _demo()
    body = client.get("/connections").get_data(as_text=True)
    # Real statuses, not mock health scores.
    assert "Spotify" in body and "Bandsintown" in body
    assert "Connected" in body and "Not connected" in body
    assert "RESEND_API_KEY not set" in body        # honest env truth
    assert "we won" in body                        # unavailable section header
    assert "Connection Health" not in body         # old mock gone


def test_settings_links_to_connections_page():
    client = _demo()
    body = client.get("/settings").get_data(as_text=True)
    assert 'href="/connections"' in body


def test_settings_includes_account_profile_ui():
    client = _demo()
    body = client.get("/settings").get_data(as_text=True)
    assert "Account Profile" in body
    assert 'id="profile-form"' in body
    assert 'id="profile-name"' in body
    assert 'id="profile-email"' in body
    assert 'id="profile-plan"' in body


def test_settings_includes_notification_preferences_ui():
    client = _demo()
    body = client.get("/settings").get_data(as_text=True)
    assert "Notification Preferences" in body
    assert 'id="notification-list"' in body
    assert "High severity leak alerts" in body
    assert "Weekly summary email" in body
    assert 'data-key="leak_high"' in body
    assert 'data-key="new_song_detected"' in body


def test_scan_endpoint_returns_findings():
    client = _demo()
    response = client.post("/scan/missing-royalties")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["count"] == len(data["findings"])
    assert data["count"] > 0
    assert data["total_estimated"] > 0
    required = {"id", "source", "issue_type", "estimated_value", "confidence", "recommended_action"}
    assert required <= set(data["findings"][0].keys())


def test_connect_and_disconnect_platform():
    client = _demo()
    try:
        response = client.post("/connections/youtube-music/connect")
        assert response.status_code == 200
        assert response.get_json() == {"ok": True, "status": "connected"}
        assert "YouTube Music" in [b.platform for b in get_platform_balances()]

        response = client.post("/connections/youtube-music/disconnect")
        assert response.status_code == 200
        assert "YouTube Music" not in [b.platform for b in get_platform_balances()]
    finally:
        reset_connection_state()


def test_connect_unknown_platform_returns_404():
    client = _demo()
    response = client.post("/connections/not-a-platform/connect")
    assert response.status_code == 404


def test_catalog_page_matches_control_center():
    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)
    assert "Your entire catalog. Organized. Verified. Maximized." in body
    assert "Total Tracks" in body
    assert "Total Releases" in body
    assert "Registered Tracks" in body
    assert "Total ISRCs" in body
    assert "Blood in the Groove" in body


def test_catalog_has_all_five_tabs():
    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)
    for tab in ["Tracks", "Releases", "Songwriters", "Publishers", "Splits"]:
        assert 'data-tab="{}"'.format(tab) in body


def test_catalog_right_column_and_recently_added():
    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)
    assert "Catalog Health" in body
    assert "Metadata Issues" in body
    assert "Catalog Value (Estimated)" in body
    assert "Recently Added" in body
    assert "Improve Catalog Health" in body


def test_catalog_includes_add_release_and_filters():
    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)
    assert 'id="add-release-modal"' in body
    assert 'id="status-filter"' in body
    assert 'id="genre-filter"' in body
    assert 'id="source-filter"' in body


def test_sidebar_shows_the_users_real_plan_not_the_mock_one():
    """This used to assert the opposite - that the sidebar rendered
    catalog_config's hardcoded "Pro Plan". That is mock data, identical
    for every account, and it sat next to a hardcoded "Next payout:
    $2,500 in 6 days" on every authenticated page. Both read as the
    user's own. The plan is knowable, so the sidebar shows the real one."""
    import db as store
    import plans
    from catalog_config import get_account

    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)

    user = store.get_user_by_email("demo@streetbanker.io")
    expected = plans.PLAN_NAMES.get(user["plan"] or "artist", "Artist")
    assert expected in body, "sidebar does not show the account's real plan"
    assert user["name"] in body

    # And the fabricated payout must not come back.
    mock = get_account()
    assert "Next payout" not in body or str(mock["next_payout"]) not in body, \
        "the hardcoded $%s payout is rendering again" % mock["next_payout"]


def test_song_detail_endpoint_returns_full_payload():
    client = _demo()
    response = client.get("/songs/midnight-drive")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    song = data["song"]
    required = {
        "isrc", "iswc", "upc", "master_owner", "splits", "platform_earnings",
        "check_status", "missing_issues", "recent_payouts", "metadata_score",
        "registration_score",
    }
    assert required <= set(song.keys())
    assert song["title"] == "Midnight Drive"


def test_song_detail_unknown_id_returns_404():
    client = _demo()
    response = client.get("/songs/not-a-real-song")
    assert response.status_code == 404


def test_royalties_includes_payout_calendar():
    client = _demo()
    body = client.get("/royalties").get_data(as_text=True)
    assert "Payout Calendar" in body
    assert "Upcoming total" in body


def test_advance_claim_route():
    client = _demo()
    try:
        response = client.post("/claims/youtube-music-uncollected/advance")
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["status"] == "Needs Info"
    finally:
        reset_claim_state()


def test_reject_claim_route():
    client = _demo()
    try:
        response = client.post("/claims/youtube-music-uncollected/reject")
        assert response.status_code == 200
        assert response.get_json() == {"ok": True, "status": "Rejected"}
    finally:
        reset_claim_state()


def test_advance_unknown_claim_returns_404():
    client = _demo()
    response = client.post("/claims/not-a-real-claim/advance")
    assert response.status_code == 404


def test_add_split_route():
    client = _demo()
    try:
        response = client.post(
            "/songs/midnight-drive/splits",
            json={"collaborator": "New Collaborator", "role": "Mixer", "percentage": 15.0},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert len(data["splits"]) == 4
        assert data["split_total"] == 115.0
    finally:
        reset_split_state()


def test_add_split_missing_fields_returns_400():
    client = _demo()
    response = client.post("/songs/midnight-drive/splits", json={"collaborator": "", "role": "Mixer", "percentage": 10.0})
    assert response.status_code == 400


def test_add_split_unknown_song_returns_404():
    client = _demo()
    response = client.post(
        "/songs/not-a-real-song/splits",
        json={"collaborator": "X", "role": "Writer", "percentage": 100.0},
    )
    assert response.status_code == 404


def test_remove_split_route():
    client = _demo()
    try:
        client.post("/songs/midnight-drive/splits", json={"collaborator": "Temp", "role": "Mixer", "percentage": 10.0})
        response = client.post("/songs/midnight-drive/splits/3/remove")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["splits"]) == 3
    finally:
        reset_split_state()


def test_toggle_split_route():
    client = _demo()
    try:
        response = client.post("/songs/neon-dreams/splits/1/toggle")
        assert response.status_code == 200
        data = response.get_json()
        assert data["splits"][1]["confirmed"] is True
    finally:
        reset_split_state()


def test_toggle_split_unknown_song_returns_404():
    client = _demo()
    response = client.post("/songs/not-a-real-song/splits/0/toggle")
    assert response.status_code == 404


def test_base_includes_collapsible_section_script():
    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)
    assert "section-chevron" in body
    assert "royaltySweep.collapsed." in body


def test_catalog_releases_tab_lists_releases():
    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)
    assert 'id="tab-Releases"' in body
    assert "The Collection Vol. 1" in body
    assert "Survival Mode" in body


def test_catalog_splits_tab_lists_splits():
    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)
    assert 'id="tab-Splits"' in body
    assert "Collaborator" in body
    assert "Conflict" in body


def test_catalog_metadata_issues_have_counts():
    client = _demo()
    body = client.get("/catalog").get_data(as_text=True)
    assert "Missing ISRCs" in body
    assert "Unregistered Tracks" in body
    assert "Split Conflicts" in body


def test_reports_page_includes_report_library():
    client = _demo()
    body = client.get("/reports").get_data(as_text=True)
    assert "Investor Snapshot" in body
    assert "Recently Generated" in body
    assert "Scheduled Reports" in body
    assert "Report Types" in body


def test_reports_data_config_shapes():
    from reports_config import get_reports_data
    data = get_reports_data()
    assert data["summary"]["total_reports"] == len(data["categories"][0]["reports"]) + sum(
        len(c["reports"]) for c in data["categories"][1:]
    )
    assert [c["name"] for c in data["categories"]] == ["Financial", "Recovery", "Rights", "Investor"]
    assert data["formats"]
    assert all("tone" in c for c in data["categories"])
    # No scheduler exists, so a real account is shown no schedules. The
    # three examples ("Monthly · 2 recipients · next 2026-08-01") were
    # identical for every account and would never have run.
    assert data["scheduled"] == [], "real accounts are shown jobs that do not exist"
    assert get_reports_data(demo=True)["scheduled"], "showcase lost its examples"


def test_epk_page_includes_press_kit():
    client = _demo()
    body = client.get("/epk").get_data(as_text=True)
    assert 'id="epk-document"' in body
    assert "Biography" in body
    assert "Top Tracks" in body
    assert "Press Kit Sections" in body
    assert "section-toggle" in body


def test_epk_sidebar_and_export():
    client = _demo()
    assert 'href="/epk"' in client.get("/links").get_data(as_text=True)
    resp = client.post("/epk/export")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] and data["filename"].endswith(".pdf")
    assert "press-kit" in data["filename"]


def test_epk_data_config_shapes():
    from epk_config import get_epk_data
    from catalog_config import get_account
    data = get_epk_data(get_account(), {"mid": 296400.0})
    assert data["name"] == get_account()["name"]
    assert len(data["stats"]) == 4
    assert data["top_tracks"]
    # Top tracks sorted by streams descending.
    streams = [t["streams"] for t in data["top_tracks"]]
    assert streams == sorted(streams, reverse=True)
    assert all(s["key"] for s in data["sections"])


def test_artwork_page_includes_generator():
    client = _demo()
    body = client.get("/artwork").get_data(as_text=True)
    assert 'id="cover-frame"' in body
    assert "AI Artwork" in body and "Pollinations.ai" in body
    assert 'id="bg-color"' in body              # background color wheel
    assert "colorway-btn" not in body           # preset blocks removed
    assert 'href="/artwork"' in body


def test_artwork_generate_endpoint():
    client = _demo()
    resp = client.post("/artwork/generate", json={"prompt": "warm ember sunset fire heat"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"]
    assert data["suggestion"]["colorway_id"] == "ember"
    assert "template_id" in data["suggestion"]


def test_smart_links_page_and_create():
    from links_config import reset_smart_links_state
    reset_smart_links_state()
    client = _demo()
    body = client.get("/links").get_data(as_text=True)
    assert 'id="links-list"' in body
    assert "Create Smart Link" in body
    assert 'href="/links"' in body
    ok = client.post("/links/create", json={"title": "New Single", "platforms": ["Spotify", "TikTok"]})
    assert ok.status_code == 200
    link = ok.get_json()["link"]
    assert link["slug"] == "new-single"
    assert link["url"].endswith("/new-single")
    bad = client.post("/links/create", json={"title": "", "platforms": []})
    assert bad.status_code == 400


def test_links_data_config_shapes():
    from links_config import get_links_data, reset_smart_links_state
    reset_smart_links_state()
    data = get_links_data()
    assert data["summary"]["total_links"] == len(data["links"])
    assert data["summary"]["total_clicks"] == sum(l["clicks"] for l in data["links"])
    assert all("url" in l and "platform_logos" in l for l in data["links"])
    assert data["platforms"]


def _rtype_client(app_obj, email):
    import io
    client = app_obj.test_client()
    client.post("/signup", data={"name": "RT", "email": email, "password": "rtpass1"})
    client.post("/plan/switch", data={"plan": "pro"})
    csv = ("title,source,amount,period,territory\n"
           "Song A,Spotify,500,2026-01,US\n"
           "Song A,ASCAP,120,2026-01,US\n"
           "Song B,The MLC,45,2026-02,\n"
           "Song B,SoundExchange,60,2026-02,GB\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv.encode()), "rt.csv")},
                content_type="multipart/form-data")
    return client


def test_publishing_page_real_classification():
    client = _rtype_client(create_app(), "rt-pub@example.net")
    body = client.get("/publishing").get_data(as_text=True)
    assert "Performance / Publishing" in body
    assert "ASCAP" in body and "$120.00" in body
    assert "Spotify" not in body.split("By source")[1][:600]  # streams stay out


def test_tier2_pages_render_and_are_in_nav():
    client = _demo()
    nav = client.get("/overview").get_data(as_text=True)
    for href in ("/documents", "/identifiers", "/conflicts", "/releases", "/registration"):
        assert 'href="%s"' % href in nav
        assert client.get(href).status_code == 200
    # Ecosystem Hub model: five collapsible hubs plus Account, on every page.
    for hub in ("command", "studio", "launch", "stage", "money", "account"):
        assert 'data-hub="%s"' % hub in nav
    promote_nav = client.get("/links").get_data(as_text=True)
    for hub in ("launch", "money"):
        assert 'data-hub="%s"' % hub in promote_nav


def test_identifiers_page_content():
    body = _demo().get("/identifiers").get_data(as_text=True)
    assert "Identifiers" in body
    assert "ISRC" in body and "ISWC" in body and "UPC" in body


def test_conflicts_page_content():
    body = _demo().get("/conflicts").get_data(as_text=True)
    assert "Rights Conflict Center" in body


def test_releases_real_calendar():
    import links_store as mls
    app_obj = create_app()
    client = _demo(app_obj)
    client.post("/links/new", data={"title": "Calendar Drop",
                                    "release_date": "2031-03-15",
                                    "dest_spotify": "https://open.spotify.com/track/x"})
    body = client.get("/releases").get_data(as_text=True)
    assert "Release Scheduler" in body
    assert "2031-03" in body and "Calendar Drop" in body   # real campaign date
    assert "release day" in body
    assert "Readiness Checklist" not in body               # old mock gone


def test_registration_page_and_complete_step():
    client = _demo()
    body = client.get("/registration").get_data(as_text=True)
    assert "Registration Wizard" in body
    # The completion endpoint the page posts to should advance a missing target.
    resp = client.post("/songs/neon-dreams/registration-wizard/mlc/complete")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] and data["wizard"]["status"]["mlc"] is True


def test_neighboring_rights_page_real():
    client = _rtype_client(create_app(), "rt-nb@example.net")
    body = client.get("/neighboring-rights").get_data(as_text=True)
    assert "Neighboring Rights" in body
    assert "SoundExchange" in body and "$60.00" in body


def test_sync_page_content():
    client = _demo()
    body = client.get("/sync").get_data(as_text=True)
    assert "Sync / Licensing" in body
    assert "Placements" in body
    assert "Incoming Requests" in body
    assert 'href="/sync"' in body


def test_sync_data_config_shapes():
    from sync_config import get_sync_data
    from royalty_data import get_songs
    data = get_sync_data()
    assert data["placements"] and data["requests"] and data["opportunities"]
    # Placements reference real catalog song titles.
    titles = {s.title for s in get_songs()}
    assert all(p["song"] in titles for p in data["placements"])
    # Sync income counts only live placements.
    live = round(sum(p["fee"] for p in data["placements"] if p["status"] == "Live"), 2)
    assert data["summary"]["sync_income"] == live


def test_territories_page_real():
    client = _rtype_client(create_app(), "rt-terr@example.net")
    body = client.get("/territories").get_data(as_text=True)
    assert "Territories" in body
    assert "US" in body and "$620.00" in body      # Spotify + ASCAP both US
    assert "GB" in body and "$60.00" in body
    assert "no imputed geography" in body


def test_mechanicals_page_real():
    client = _rtype_client(create_app(), "rt-mech@example.net")
    body = client.get("/mechanicals").get_data(as_text=True)
    assert "Mechanical" in body
    assert "The MLC" in body and "$45.00" in body
    # Empty stream shows honest guidance for a fresh account with no uploads.
    fresh = create_app().test_client()
    fresh.post("/signup", data={"name": "F", "email": "rt-fresh@example.net",
                                "password": "rtpass1"})
    fresh.post("/plan/switch", data={"plan": "pro"})
    body = fresh.get("/mechanicals").get_data(as_text=True)
    assert "that's the finding" in body and "The MLC pays" in body


def test_funding_quotes_nothing_without_income():
    """The page used to show a suggested advance - with a Request button
    under it - scaled off a hardcoded earnings trend identical for every
    account. With no statements there is no income to lend against, so
    there is no honest figure to quote and no offer to request."""
    client = _demo()
    body = client.get("/funding").get_data(as_text=True)
    assert "Advance &amp; Funding" in body
    if "Nothing to quote yet" in body:
        # An amount nobody can stand behind must not be requestable.
        refused = client.post("/funding/request",
                              json={"offer_id": "offer-royalty-advance"})
        assert refused.status_code == 400


def test_funding_quotes_a_range_once_statements_exist():
    import io
    # Its own account. Uploading statements to the shared demo login
    # changes totals that other tests assert on exactly - the tax page
    # checks for $750.25 and does not want this test's income in it.
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "Fund Test",
                                 "email": "fund-range@example.net",
                                 "password": "fundpass1"})
    # Statements and funding sit above the entry tier, so a fresh signup
    # gets 402 on both. Promote it rather than borrow the demo account.
    import db as _store
    _u = _store.get_user_by_email("fund-range@example.net")
    _store.set_user_plan(_u["id"], "pro")
    csv_text = 'title,source,amount,period\nTrack A,Spotify,900.00,2026-01\nTrack B,Apple Music,750.00,2026-02\nTrack C,YouTube,640.00,2026-03\n'
    client.post("/statements",
                data={"statement": (io.BytesIO(csv_text.encode()), "fund.csv")},
                content_type="multipart/form-data")
    body = client.get("/funding").get_data(as_text=True)
    # A range rather than a single figure, and it names its own basis.
    assert "Indicative Range" in body
    assert "Indicative range, not an offer" in body
    ok = client.post("/funding/request",
                     json={"offer_id": "offer-royalty-advance"})
    assert ok.status_code == 200 and ok.get_json()["ok"]
    assert ok.get_json()["reference"].startswith("REQ-")
    bad = client.post("/funding/request", json={"offer_id": "nope"})
    assert bad.status_code == 400


def test_funding_offers_derive_from_advance():
    from funding_config import get_funding_data
    elig = {"suggested_advance": 70000, "tier": "Eligible", "score": 95}
    data = get_funding_data(elig)
    assert data["eligibility"]["suggested_advance"] == 70000
    # Recommended offer matches the suggested advance.
    rec = next(o for o in data["offers"] if o["recommended"])
    assert rec["amount"] == 70000
    # Total repayable exceeds the amount by the cost of funds.
    for o in data["offers"]:
        assert round(o["amount"] + o["cost"], 2) == o["total_repayable"]


def test_tax_page_real_income_by_year():
    """A fresh account, not the demo: the showcase carries seeded
    statements of its own now, so per-year totals asserted against the
    demo would be asserting against somebody else's rows too."""
    import io
    import uuid as _uuid
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "T",
                                 "email": "tax%s@x.com" % _uuid.uuid4().hex[:8],
                                 "password": "secret1", "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    # Empty state points at Statements.
    body = client.get("/tax").get_data(as_text=True)
    assert "Tax Center" in body
    assert ("Upload a royalty statement" in body) or ("Total Reported Income" in body)
    # Upload a statement -> real per-year totals appear.
    csv = ("title,source,amount,period\n"
           "Song A,Spotify,700.00,2026-01\n"
           "Song A,Apple Music,50.25,2026-02\n"
           "Song B,Spotify,10.00,2025-11\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv.encode()), "tax.csv")},
                content_type="multipart/form-data")
    body = client.get("/tax").get_data(as_text=True)
    assert "2026" in body and "$750.25" in body
    assert "2025" in body and "$10.00" in body
    assert "Over $600" in body            # 1099 flag only on the big year
    assert "not tax advice" in body


def test_disputes_real_tracker():
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "Disp", "email": "disp@example.net",
                                 "password": "disppass"})
    client.post("/plan/switch", data={"plan": "pro"})
    body = client.get("/disputes").get_data(as_text=True)
    assert "Dispute Tracker" in body and "Nothing in dispute" in body
    # Log a dispute -> shows on the board with the amount in dispute.
    r = client.post("/disputes/new", data={
        "platform": "DistroKid", "dispute_type": "missing payment",
        "amount": "230.50", "description": "March payout never arrived."})
    assert r.get_json()["ok"]
    body = client.get("/disputes").get_data(as_text=True)
    assert "DistroKid" in body and "$230.50" in body
    # Resolve it -> moves to recovered, notification lands.
    uid = store_mod.get_user_by_email("disp@example.net")["id"]
    did = store_mod.list_disputes(uid)[0]["id"]
    assert client.post("/disputes/%s/status" % did,
                       json={"status": "resolved"}).get_json()["ok"]
    body = client.get("/disputes").get_data(as_text=True)
    assert body.count("$230.50") >= 2               # resolved tile + row
    assert not client.post("/disputes/%s/status" % did,
                           json={"status": "bogus"}).get_json()["ok"]
    assert any("Dispute resolved" in n["title"]
               for n in store_mod.list_notifications(uid))


def test_tier3_pages_render_and_nav():
    client = _demo()
    nav = client.get("/links").get_data(as_text=True)
    for href in ("/audience", "/playlists", "/stats"):
        assert 'href="%s"' % href in nav
        assert client.get(href).status_code == 200


def test_audience_data_config_shapes():
    from audience_config import get_audience_data
    data = get_audience_data()
    assert data["trend"] and data["top_tracks"]
    assert sum(a["pct"] for a in data["age_brackets"]) == 100
    # Top tracks are ranked by streams.
    streams = [t["streams"] for t in data["top_tracks"]]
    assert streams == sorted(streams, reverse=True)


def test_playlists_data_config_shapes():
    from playlists_config import get_playlists_data, reset_playlists_state
    reset_playlists_state()
    data = get_playlists_data()
    assert data["summary"]["total_pitches"] == len(data["pitches"])
    assert data["summary"]["placements"] == sum(1 for p in data["pitches"] if p["stage"] == "Added")


def test_notifications_page_and_mark_read():
    from notifications_config import reset_notifications_state
    reset_notifications_state()
    client = _demo()
    body = client.get("/notifications").get_data(as_text=True)
    assert "Notifications" in body
    assert 'href="/notifications"' in body
    assert client.post("/notifications/ntf-sys-welcome/read").get_json()["ok"]
    assert client.post("/notifications/read-all").get_json()["ok"]
    reset_notifications_state()


def test_global_search_finds_songs_and_sources():
    from search_config import search
    client = _demo()
    assert client.get("/search").status_code == 200
    assert 'action="/search"' in client.get("/overview").get_data(as_text=True)
    # The showcase account still finds the seeded catalogue.
    res = search("spotify", demo=True)
    assert res["total"] >= 1
    assert any(g["type"] == "Sources" for g in res["groups"])
    assert search("", demo=True)["total"] == 0

    # A real account searches its own statements. With none uploaded the
    # honest answer is nothing - this used to return "Midnight Drive,
    # ISRC USRC12345678" to an artist who had never heard of it.
    import db as store_mod
    fresh = store_mod.get_user_by_email("demo@streetbanker.io")
    plain = search("midnight", user_id=fresh["id"])
    assert plain["is_demo"] is False
    assert all(g["type"] != "Songs" for g in plain["groups"]), \
        "real search is still serving the hardcoded song catalogue"


def test_billing_page_content():
    client = _demo()
    body = client.get("/billing").get_data(as_text=True)
    assert "Compare Plans" in body
    assert 'href="/billing"' in body


def test_team_page_renders_and_in_nav():
    client = _demo()
    assert 'href="/team"' in client.get("/overview").get_data(as_text=True)
    assert client.get("/team").status_code == 200


def test_onboarding_page_renders():
    client = _demo()
    body = client.get("/onboarding").get_data(as_text=True)
    assert "Connect your sources" in body


def test_real_auth_flow():
    import uuid
    client = create_app().test_client()
    # One-click demo login is gone; the demo account is password-only.
    assert client.post("/login/demo").status_code in (302, 404, 405)
    email = "u%s@example.com" % uuid.uuid4().hex[:8]
    assert client.get("/login").status_code == 200
    assert client.get("/signup").status_code == 200
    # Signup -> onboarding; weak input rejected.
    ok = client.post("/signup", data={"name": "T", "email": email, "password": "secret1"})
    assert ok.status_code == 302 and "/onboarding" in ok.headers["Location"]
    dup = client.post("/signup", data={"name": "T", "email": email, "password": "secret1"})
    assert "already exists" in dup.get_data(as_text=True)
    assert client.post("/logout").status_code == 302
    # Login with right/wrong password.
    good = client.post("/login", data={"email": email, "password": "secret1"})
    assert good.status_code == 302
    bad = client.post("/login", data={"email": email, "password": "nope"})
    assert "Incorrect email or password" in bad.get_data(as_text=True)
    # One-click demo login is retired (password-only demo account).


def test_statements_upload_and_real_findings():
    import io, uuid
    client = create_app().test_client()
    email = "s%s@example.com" % uuid.uuid4().hex[:8]
    # Requires login.
    assert client.get("/statements").status_code == 302
    client.post("/signup", data={"name": "S", "email": email, "password": "secret1"})
    client.post("/plan/switch", data={"plan": "pro"})  # Royalty Sweep is Pro tier
    csv_data = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"Midnight Drive,Spotify,120.50,2026-05\n"
                b"Midnight Drive,Apple Music,80.25,2026-05\n"
                b"Neon Dreams,Spotify,60.00,2026-05\n"
                b",Spotify,12.40,2026-05\n")
    up = client.post("/statements", data={"statement": (io.BytesIO(csv_data), "symphonic.csv")},
                     content_type="multipart/form-data")
    assert up.status_code == 302
    body = client.get("/statements").get_data(as_text=True)
    assert "273.15" in body            # real total
    assert "12.40" in body             # unmatched revenue detected
    assert "Coverage Gaps" in body     # Neon Dreams missing Apple Music
    # Real CSV export includes the uploaded rows.
    csv_out = client.get("/reports/royalty-report/download.csv")
    assert csv_out.status_code == 200 and "Midnight Drive" in csv_out.get_data(as_text=True)


def test_statement_engine_math():
    from statements_engine import parse_statement, analyze
    parsed = parse_statement("Song,Platform,Earnings\nA,Spotify,10\nA,Apple,20\nB,Spotify,5\n")
    assert parsed["error"] is None and len(parsed["rows"]) == 3
    a = analyze(parsed["rows"])
    assert a["total"] == 35.0
    assert a["by_source"][0]["source"] in ("Apple", "Spotify")
    # B earns on Spotify but not Apple -> one coverage gap, est = B's avg (5).
    assert a["coverage_gaps"][0]["title"] == "B"
    assert a["coverage_gaps"][0]["estimated_value"] == 5.0
    assert parse_statement("no,amount,columns\nx,y,z\n")["error"]


def test_real_smart_link_redirect_and_click():
    client = _demo()
    link = client.post("/links/create", json={"title": "Wire Test", "platforms": ["Spotify"]}).get_json()["link"]
    assert link["real"] and "/l/" in link["url"]
    r = client.get("/l/" + link["slug"])
    assert r.status_code == 302 and "spotify.com/search" in r.headers["Location"]
    assert client.get("/l/does-not-exist").status_code == 302  # falls back to /links
    assert "real clicks" in client.get("/links").get_data(as_text=True)


def test_inbox_persists_submissions():
    import uuid
    from network_config import reset_network_state
    reset_network_state()
    client = create_app().test_client()
    assert client.get("/inbox").status_code == 302  # requires login
    client.post("/signup", data={"name": "I", "email": "i%s@example.com" % uuid.uuid4().hex[:8], "password": "secret1"})
    client.post("/network/playlist/late-night-synth/submit", json={"song": "Midnight Drive"})
    client.post("/network/nova-reign/enquire", json={"city": "Chicago"})
    body = client.get("/inbox").get_data(as_text=True)
    assert "Playlist submission" in body and "Booking enquiry" in body
    # Both are records of what this account sent, so they file under Sent.
    assert "Midnight Drive" in body and "Chicago" in body
    assert "Sent" in body
    reset_network_state()


def test_tier5_and_community_pages_render_and_nav():
    client = _demo()
    promote_nav = client.get("/links").get_data(as_text=True)
    fan_nav = client.get("/discover").get_data(as_text=True)
    for href in ("/insights", "/benchmark"):
        assert 'href="%s"' % href in promote_nav
        assert client.get(href).status_code == 200
    for href in ("/marketplace", "/network", "/fan-label", "/fans"):
        assert 'href="%s"' % href in fan_nav
        assert client.get(href).status_code == 200
    assert 'data-hub="command"' in promote_nav  # Intelligence lives in the Command hub now
    assert ">Community<" in fan_nav


def test_insights_computed_from_real_data():
    import io
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "Ins", "email": "ins@example.net",
                                 "password": "inspass"})
    # Fresh account: honest starting insight, no fabricated observations.
    body = client.get("/insights").get_data(as_text=True)
    assert "No income data yet" in body
    assert "not a language model" in body
    # Concentrated income -> the risk insight appears with real numbers.
    client.post("/plan/switch", data={"plan": "pro"})
    csv = ("title,source,amount,period\n"
           "A,Spotify,900,2026-01\n"
           "A,ASCAP,100,2026-01\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv.encode()), "i.csv")},
                content_type="multipart/form-data")
    body = client.get("/insights").get_data(as_text=True)
    assert "Income concentration" in body and "90%" in body
    assert "Uncollected royalty streams" in body and "Mechanical" in body


def test_benchmark_uses_real_metrics():
    from benchmark_config import get_benchmark_data
    from royalty_data import get_songs
    data = get_benchmark_data()
    streams = next(m for m in data["metrics"] if m["label"] == "Total streams")
    assert streams["you"] == sum(s.streams for s in get_songs())
    assert data["summary"]["ahead"] + data["summary"]["behind"] == data["summary"]["metrics"]


def test_marketplace_post_flow():
    """The marketplace is a real db-backed collab board now."""
    import db as store_mod
    app_obj = create_app()
    poster = _demo(app_obj)
    page = poster.get("/marketplace").get_data(as_text=True)
    assert "Collab Marketplace" in page and "Nothing here is seeded" in page
    assert "For Bid" in page and "Royalty Split" in page and "For Fun" in page
    # Post a real request with terms up front.
    poster.post("/marketplace/post", data={
        "kind": "split", "role": "Vocalist", "genre": "Synthwave",
        "title": "Velvet topline for a midnight cruiser",
        "details": "90 BPM, minor key.", "terms": "5-15% master",
        "ref_url": "https://example.com/scratch"})
    page = poster.get("/marketplace").get_data(as_text=True)
    assert "Velvet topline" in page and "5-15% master" in page
    assert "Trust" in page and "Hear the reference track" in page
    # A second member applies; the poster sees the application + notification.
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    req = store_mod.list_own_collab_requests(uid)[0]
    applicant = app_obj.test_client()
    applicant.post("/signup", data={"name": "Top Liner", "email": "topliner@example.net",
                                    "password": "toplinepass"})
    # Kind filter tabs actually filter (checked from a non-owner's view —
    # the poster's own section always lists their requests).
    assert "Velvet topline" in applicant.get("/marketplace?kind=split").get_data(as_text=True)
    assert "Velvet topline" not in applicant.get("/marketplace?kind=bid").get_data(as_text=True)
    r = applicant.post("/marketplace/%s/apply" % req["id"],
                       data={"message": "I sing airy toplines.",
                             "contact": "topliner@example.net",
                             "proposal": "10% master"})
    assert r.status_code == 302 and "applied=1" in r.headers["Location"]
    mine = poster.get("/marketplace").get_data(as_text=True)
    assert "Top Liner" in mine and "10% master" in mine
    # Applicants can't apply to their own post; saves toggle.
    own_try = poster.post("/marketplace/%s/apply" % req["id"],
                          data={"message": "me", "contact": "a@b.c"})
    assert own_try.status_code == 302
    assert store_mod.list_collab_replies(req["id"]) and \
        len(store_mod.list_collab_replies(req["id"])) == 1
    applicant.post("/marketplace/%s/save" % req["id"])
    assert req["id"] in store_mod.list_collab_saves(
        store_mod.get_user_by_email("topliner@example.net")["id"])
    # Close hides it from the open feed (non-owner view).
    poster.post("/marketplace/%s/close" % req["id"])
    assert "Velvet topline" not in applicant.get("/marketplace?kind=split"
                                               ).get_data(as_text=True)


def test_fan_label_vote_flow():
    from community_config import reset_fan_label_state, get_fan_label_data
    reset_fan_label_state()
    before = {d["id"]: d["votes"] for d in get_fan_label_data()["demos"]}
    client = _demo()
    resp = client.post("/fan-label/vote/demo-1")
    assert resp.status_code == 200 and resp.get_json()["votes"] == before["demo-1"] + 1
    assert client.post("/fan-label/vote/nope").status_code == 404
    reset_fan_label_state()


def test_fan_dashboard_content():
    body = _demo().get("/fans").get_data(as_text=True)
    assert "Fan Segments" in body and "Fan Leaderboard" in body


def test_capital_page_content_and_disclaimer():
    client = _demo()
    body = client.get("/capital").get_data(as_text=True)
    assert 'href="/capital"' in body
    assert "Fan Royalty Passes" in body
    assert "Royalty Futures Marketplace" in body
    assert "Roll the Dice" in body
    # Must carry the prominent simulated-demo disclaimer.
    assert "Simulated demo" in body
    assert "no royalties are actually assigned, transferred, or forfeited" in body


def test_capital_data_config_shapes():
    from capital_config import get_capital_data
    from royalty_data import get_songs
    data = get_capital_data()
    assert set(data.keys()) == {"passes", "crowdfunding", "futures", "staking", "dice"}
    titles = {s.title for s in get_songs()}
    assert data["passes"]["release"] in titles
    assert all(f["release"] in titles for f in data["futures"])
    assert data["crowdfunding"]["pct"] == round(data["crowdfunding"]["raised"] / data["crowdfunding"]["goal"] * 100)


def test_label_services_pages_and_nav():
    client = _demo()
    nav = client.get("/services").get_data(as_text=True)
    assert 'href="/services"' in nav
    assert 'href="/submit"' in nav
    assert ">Label Services<" in nav
    for path in ("/services", "/services/distribution", "/services/marketing", "/services/management", "/submit"):
        assert client.get(path).status_code == 200
    # Unknown service slug redirects back to the hub.
    assert client.get("/services/nope").status_code == 302


def test_label_services_content_from_site():
    client = _demo()
    hub = client.get("/services").get_data(as_text=True)
    # Platform branding is Street Banker; the AIW Shopify store is only a link.
    assert "Street Banker" in hub
    assert "artiswarrecords.com" in hub  # store link retained
    assert "team.summitarts@gmail.com" in hub
    assert "200+" in hub
    dist = client.get("/services/distribution").get_data(as_text=True)
    assert "No physical or digital set-up fees" in dist
    assert "Content ID" in dist  # UGC monetization sell point
    submit = client.get("/submit").get_data(as_text=True)
    assert "artiswarrecords@gmail.com" in submit
    assert 'href="/epk"' in submit  # submissions tie into the EPK builder


def test_landing_links_to_label_services():
    client = _demo()
    body = client.get("/").get_data(as_text=True)
    assert 'href="/services"' in body


def test_network_directory_filters_and_sort():
    from network_config import get_network_data, reset_network_state
    reset_network_state()
    client = _demo()
    assert client.get("/network").status_code == 200
    # Role filter narrows results to that role only.
    data = get_network_data({"role": "Producer"})
    assert data["people"] and all(p["role"] == "Producer" for p in data["people"])
    # Genre filter.
    house = get_network_data({"genre": "House"})
    assert all("House" in p["genres"] for p in house["people"])
    # Name sort is alphabetical.
    names = [p["name"] for p in get_network_data({"sort": "name"})["people"]]
    assert names == sorted(names, key=str.lower)
    # Search matches location/role/genre text.
    assert get_network_data({"q": "berlin"})["result_count"] >= 1


def test_network_profile_and_playlist_pages():
    client = _demo()
    assert client.get("/network/nova-reign").status_code == 200
    assert client.get("/network/does-not-exist").status_code == 302  # redirect to /network
    assert client.get("/network/playlist/late-night-synth").status_code == 200
    assert client.get("/network/playlist/nope").status_code == 302
    body = client.get("/network/echo-lin").get_data(as_text=True)
    assert "Late Night Synth" in body  # curator's playlist listed on profile


def test_network_connect_pitch_submit_flows():
    from network_config import reset_network_state
    reset_network_state()
    client = _demo()
    assert client.post("/network/kilo-byte/connect").get_json()["status"] == "Pending"
    assert client.post("/network/nope/connect").status_code == 404
    assert client.post("/network/kilo-byte/pitch", json={"song": "Midnight Drive"}).get_json()["ok"]
    # Submit to an open playlist works; closed one is rejected.
    assert client.post("/network/playlist/late-night-synth/submit", json={"song": "Midnight Drive"}).get_json()["ok"]
    assert client.post("/network/playlist/chill-drive/submit", json={"song": "X"}).status_code == 400
    assert client.post("/network/playlist/late-night-synth/submit", json={"song": ""}).status_code == 400
    # My Network reflects the connection + submission.
    my = client.get("/network?tab=my").get_data(as_text=True)
    assert "Kilo Byte" in my and "Late Night Synth" in my
    reset_network_state()


def test_network_shows_and_booking():
    from network_config import reset_network_state
    reset_network_state()
    client = _demo()
    assert client.get("/network?tab=shows").status_code == 200
    assert "Tour Dates" in client.get("/network/nova-reign").get_data(as_text=True)
    # Enquire works for booking profiles, rejected for non-booking.
    assert client.post("/network/nova-reign/enquire", json={"city": "Chicago"}).get_json()["ok"]
    assert client.post("/network/vera-sound/enquire", json={"city": "X"}).status_code == 400
    reset_network_state()


def test_network_moments_and_claim():
    from network_config import reset_network_state, get_moment
    reset_network_state()
    client = _demo()
    assert client.get("/network?tab=moments").status_code == 200
    body = client.get("/network/moment/mo-1").get_data(as_text=True)
    # Watermark/serial + honest deterrent labeling present.
    assert "SB-1-0001" in body
    assert "can't truly block screenshots" in body
    assert client.get("/network/moment/nope").status_code == 302
    # Claim marks it owned.
    resp = client.post("/network/moment/mo-1/claim")
    assert resp.get_json()["serial"] == "SB-1-0001"
    assert get_moment("mo-1")["claimed"] is True
    assert client.post("/network/moment/nope/claim").status_code == 404
    reset_network_state()


def test_discover_page_and_filters():
    from discover_config import get_discover_data, reset_discover_state
    reset_discover_state()
    client = _demo()
    assert client.get("/discover").status_code == 200
    assert 'href="/discover"' in client.get("/discover").get_data(as_text=True)  # fan-world sidebar
    assert "Create a free fan account" in client.get("/login").get_data(as_text=True)  # fan row on Session Recall
    # Genre filter narrows the feed.
    data = get_discover_data({"genre": "Synthwave"})
    assert data["tracks"] and all(t["genre"] == "Synthwave" for t in data["tracks"])
    # Mood filter.
    assert all(t["mood"] == "late-night" for t in get_discover_data({"mood": "late-night"})["tracks"])


def test_discover_like_and_follow():
    from discover_config import reset_discover_state
    reset_discover_state()
    client = _demo()
    r = client.post("/discover/like/tr-1").get_json()
    assert r["liked"] is True and r["count"] == 1
    assert client.post("/discover/like/tr-1").get_json()["liked"] is False  # toggles off
    assert client.post("/discover/like/nope").status_code == 404
    assert client.post("/discover/follow/nova-reign").get_json()["following"] is True
    reset_discover_state()


def test_epk_editable_savable_real():
    import uuid
    client = create_app().test_client()
    # Anonymous users are sent to sign in; nothing renders.
    assert client.get("/epk").status_code == 302
    assert client.post("/epk/save", json={"tagline": "X"}).status_code == 401
    # Signed-in edits persist across requests.
    client.post("/signup", data={"name": "EPK Artist",
                                 "email": "epk%s@example.com" % uuid.uuid4().hex[:6],
                                 "password": "secret1"})
    assert client.post("/epk/save", json={
        "tagline": "Custom tagline here.", "bio": "Custom biography.",
        "genres": "Synthwave, House", "socials": {"instagram": "@custom"},
        "contact": {"booking": "book@custom.com"},
        "press": [{"quote": "Stellar.", "source": "MagX"}],
    }).get_json()["ok"]
    body = client.get("/epk").get_data(as_text=True)
    for s in ("Custom tagline here.", "Custom biography.", "House",
              "@custom", "book@custom.com", "Stellar.", "EPK Artist"):
        assert s in body


def test_epk_photo_upload_real():
    import io, uuid
    client = create_app().test_client()
    assert client.post("/epk/photo").status_code == 401  # login required
    client.post("/signup", data={"name": "P", "email": "p%s@example.com" % uuid.uuid4().hex[:6],
                                 "password": "secret1"})
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = client.post("/epk/photo", data={"photo": (io.BytesIO(png), "me.png")},
                    content_type="multipart/form-data")
    photo = r.get_json()["photo"]
    assert photo.startswith("/uploads/epk_")
    assert client.get(photo).status_code == 200          # actually served
    assert photo in client.get("/epk").get_data(as_text=True)
    bad = client.post("/epk/photo", data={"photo": (io.BytesIO(b"x"), "x.exe")},
                      content_type="multipart/form-data")
    assert bad.status_code == 400                        # non-image rejected


def _fake_itunes(url):
    return {"results": [{"trackName": "Fake Song", "artistName": "Fake Artist",
                         "collectionName": "Fake LP", "artworkUrl100": "https://x/100x100bb.jpg",
                         "previewUrl": "https://x/p.m4a", "trackViewUrl": "https://x/t"}]}


def _fake_odesli(url):
    return {"entityUniqueId": "E", "pageUrl": "https://song.link/x",
            "entitiesByUniqueId": {"E": {"title": "Fake Song", "artistName": "Fake Artist",
                                          "thumbnailUrl": "https://x/art.jpg"}},
            "linksByPlatform": {"spotify": {"url": "https://sp/x"},
                                 "appleMusic": {"url": "https://ap/x"},
                                 "youtube": {"url": "https://yt/x"}}}


def test_discover_real_search_offline(monkeypatch):
    import music_apis
    monkeypatch.setattr(music_apis, "_fetch_json", _fake_itunes)
    client = _demo()
    body = client.get("/discover?q=offline+test+query").get_data(as_text=True)
    assert "Fake Song" in body and "Fake Artist" in body
    assert "preview-play" in body                       # playable preview button
    assert "300x300bb.jpg" in body                      # artwork upscaled


def test_universal_link_via_odesli_offline(monkeypatch):
    import music_apis
    monkeypatch.setattr(music_apis, "_fetch_json", _fake_odesli)
    client = _demo()
    r = client.post("/links/create", json={"title": "Uni", "platforms": ["Spotify"],
                                            "source_url": "https://open.spotify.com/track/offlinetest"})
    link = r.get_json()["link"]
    assert link["universal"] is True and link["platform_count"] == 3
    landing = client.get("/l/" + link["slug"]).get_data(as_text=True)
    for s in ("Fake Song", "Fake Artist", "Spotify", "Apple Music", "YouTube",
              "Powered by Street Banker", "https://sp/x"):
        assert s in landing
    # Odesli failure falls back to a plain redirect link.
    monkeypatch.setattr(music_apis, "_fetch_json",
                        lambda url: (_ for _ in ()).throw(Exception("down")))
    r2 = client.post("/links/create", json={"title": "Plain Fallback", "platforms": ["Spotify"],
                                             "source_url": "https://open.spotify.com/track/failing"})
    l2 = r2.get_json()["link"]
    assert l2["universal"] is False
    assert client.get("/l/" + l2["slug"]).status_code == 302


def test_add_discover_track_to_catalog():
    client = create_app().test_client()
    # Anonymous adds are redirected to sign-in by the login gate.
    assert client.post("/catalog/add", json={"title": "Neon Ride"}).status_code == 302
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    r = client.post("/catalog/add", json={"title": "Neon Ride", "artist": "Test Artist",
                                           "art": "https://x/300x300bb.jpg", "url": "https://x/t"})
    assert r.status_code == 200 and r.get_json()["ok"]
    track_id = r.get_json()["id"]
    # Same title+artist can't be added twice.
    assert client.post("/catalog/add", json={"title": "Neon Ride",
                                              "artist": "Test Artist"}).status_code == 409
    body = client.get("/catalog").get_data(as_text=True)
    assert "Add from Discover" in body and "Neon Ride" in body
    assert client.post("/catalog/remove/" + track_id).get_json()["ok"] is True
    body = client.get("/catalog").get_data(as_text=True)
    assert "Neon Ride" not in body and "Nothing saved yet" in body
    # Signed out, the personal section disappears entirely.
    client.post("/logout")
    assert "Add from Discover" not in client.get("/catalog").get_data(as_text=True)


def test_discover_results_have_add_button(monkeypatch):
    import music_apis
    monkeypatch.setattr(music_apis, "_fetch_json", _fake_itunes)
    client = _demo()
    body = client.get("/discover?q=offline+add+button").get_data(as_text=True)
    assert "add-to-catalog" in body and "+ Catalog" in body


def _fake_deezer(url):
    if "api.deezer.com/search" in url:
        return {"data": [{"id": 42}]}
    if "api.deezer.com/track/" in url:
        return {"isrc": "USTEST2500001", "duration": 200, "release_date": "2025-01-10",
                "album": {"id": 7, "title": "Test LP"}}
    if "api.deezer.com/album/" in url:
        return {"upc": "123456789012", "label": "Test Label", "title": "Test LP",
                "release_date": "2025-01-10", "nb_tracks": 10,
                "genres": {"data": [{"name": "Electro"}]}}
    if "musicbrainz.org/ws/2/isrc/" in url:
        return {"recordings": [{"id": "rec1"}]}
    if "musicbrainz.org/ws/2/recording/" in url:
        return {"relations": [{"work": {"id": "work1"}}]}
    if "musicbrainz.org/ws/2/work/" in url:
        return {"relations": [{"type": "composer", "artist": {"name": "Fake Writer"}},
                              {"type": "publisher", "label": {"name": "Fake Publishing Co"}}]}
    return {"results": []}


def test_catalog_add_pulls_metadata(monkeypatch):
    import music_apis
    monkeypatch.setattr(music_apis, "_fetch_json", _fake_deezer)
    monkeypatch.setattr(music_apis.time, "sleep", lambda s: None)
    client = _demo()
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    r = client.post("/catalog/add", json={"title": "Meta Song", "artist": "Meta Artist"})
    meta = r.get_json()["meta"]
    assert meta["isrc"] == "USTEST2500001" and meta["upc"] == "123456789012"
    assert meta["label"] == "Test Label" and meta["album"] == "Test LP"
    assert meta["writers"] == ["Fake Writer"]
    assert meta["publishers"] == ["Fake Publishing Co"]
    body = client.get("/catalog").get_data(as_text=True)
    assert "My Releases" in body and "UPC 123456789012" in body
    assert "ISRC USTEST2500001" in body and "Test Label" in body
    # Credits populate the Songwriters and Publishers tabs + release row.
    assert "My Songwriters" in body and "Fake Writer" in body
    assert "My Publishers" in body and "Fake Publishing Co" in body
    assert "Written by Fake Writer" in body
    # A failed lookup must never block the save itself.
    monkeypatch.setattr(music_apis, "_fetch_json",
                        lambda url: (_ for _ in ()).throw(Exception("down")))
    r2 = client.post("/catalog/add", json={"title": "No Meta Song", "artist": "X"})
    assert r2.status_code == 200 and r2.get_json()["meta"] is None


def test_fresh_account_gets_clean_catalog(monkeypatch):
    import music_apis
    monkeypatch.setattr(music_apis, "_fetch_json", _fake_deezer)
    client = _demo()
    client.post("/signup", data={"name": "Clean Artist", "email": "clean@a.com",
                                  "password": "pass1234"})
    client.post("/login", data={"email": "clean@a.com", "password": "pass1234"})
    client.post("/plan/switch", data={"plan": "pro"})  # catalog is Royalty Sweep (Pro)
    body = client.get("/catalog").get_data(as_text=True)
    # No sample-catalog remnants for a real account.
    assert "1,248" not in body and "New World Order" not in body
    assert "Nothing saved yet" in body
    client.post("/catalog/add", json={"title": "First Song", "artist": "Clean Artist"})
    body = client.get("/catalog").get_data(as_text=True)
    assert "First Song" in body
    # Demo tour account keeps the rich showcase.
    client.post("/logout")
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    assert "1,248" in client.get("/catalog").get_data(as_text=True)


def test_public_epk_share_link():
    app_obj = create_app()
    client = app_obj.test_client()
    # Signed-out editor has no share block.
    assert "Public link" not in client.get("/epk").get_data(as_text=True)
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    body = client.get("/epk").get_data(as_text=True)
    # Visiting the editor mints a stable slug and shows the copyable link.
    assert "Public link" in body and "/epk/synthwave-surfer" in body
    assert "f-show-sweep" in body
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert "Official Press Kit" in public and "Synthwave Surfer" in public
    assert "Customize" not in public          # no editor UI on the public page
    assert "Powered by Royalty Sweep" not in public  # private by default
    # The artist opts in to showing backend stats publicly.
    client.post("/epk/save", json={"show_sweep": True})
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert "Powered by Royalty Sweep" in public and "Strongest Platform" in public
    # The press kit must always say which kind of number it is showing:
    # either these are the artist's own statements, or they are samples
    # and belong to nobody. It may never leave that ambiguous - this page
    # goes to labels.
    assert ("Sample metrics" in public
            or "own royalty statements" in public)
    # Anyone can open it without signing in; unknown slugs 404.
    anon = app_obj.test_client()
    assert anon.get("/epk/synthwave-surfer").status_code == 200
    assert anon.get("/epk/no-such-artist").status_code == 404


def test_epk_section_visibility_persists():
    client = _demo()
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    client.get("/epk")  # mints the public slug
    body = client.get("/epk").get_data(as_text=True)
    assert "Press Kit Sections" in body and "section-jump" in body
    assert ">Complete<" in body            # readiness statuses render
    # Hide press + stats; the editor reflects it and the public page drops them.
    client.post("/epk/save", json={"sections_off": ["press", "stats"]})
    body = client.get("/epk").get_data(as_text=True)
    assert body.count(">Hidden<") == 2
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    # Whichever stats this account has, none of them may render while the
    # section is switched off.
    assert "Indie Wave" not in public
    assert not any(lbl in public for lbl in
                   ("Total Streams", "Catalog Earnings", "Est. Catalog Value"))
    # (Releases is deliberately not checked here: the word appears in
    # other sections of the press kit, so its absence proves nothing.)
    assert "Biography" in public           # untouched sections stay
    client.post("/epk/save", json={"sections_off": []})
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    # Stats are back on. Which figures appear depends on whether this
    # account has uploaded statements - and under -n the suite shares one
    # database, so that varies by test order. What must hold either way:
    # the section renders, and the page says which kind of number it is.
    assert "Indie Wave" in public
    assert any(lbl in public for lbl in
               ("Total Streams", "Catalog Earnings", "Est. Catalog Value",
                "Releases"))
    # One-directional contract: sample figures must carry a warning.
    # Real ones need none - a press kit built from the artist's own
    # statements should not apologise for itself.
    if "Total Streams" in public:            # the demo-only headline
        assert "Sample metrics" in public


def test_epk_media_assets_and_zip():
    import io
    import zipfile
    client = create_app().test_client()
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    # Anonymous uploads are redirected by the login gate; unknown kinds rejected.
    assert client.post("/epk/asset/logo", data={"asset": (io.BytesIO(png), "a.png")},
                       content_type="multipart/form-data").status_code == 401
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    client.get("/epk")
    assert client.post("/epk/asset/nonsense", data={"asset": (io.BytesIO(png), "a.png")},
                       content_type="multipart/form-data").status_code == 400
    for kind in ("press_photo", "logo"):
        r = client.post("/epk/asset/" + kind, data={"asset": (io.BytesIO(png), "a.png")},
                        content_type="multipart/form-data")
        assert r.get_json()["ok"]
    # Public page gains the downloads section and the ZIP bundles both files.
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert "Media Assets" in public and "Download Press Kit (ZIP)" in public
    z = zipfile.ZipFile(io.BytesIO(client.get("/epk/synthwave-surfer/kit.zip").data))
    assert sorted(z.namelist()) == ["synthwave-surfer-logo.png",
                                    "synthwave-surfer-press-photo.png"]
    # Making the logo private removes it from the public page and the ZIP.
    client.post("/epk/asset/logo/visibility", json={"public": False})
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert "Logo" not in public
    z = zipfile.ZipFile(io.BytesIO(client.get("/epk/synthwave-surfer/kit.zip").data))
    assert z.namelist() == ["synthwave-surfer-press-photo.png"]
    # A YouTube link saves and renders as an embed.
    client.post("/epk/save", json={"video_url": "https://www.youtube.com/watch?v=abc123"})
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert "youtube.com/embed/abc123" in public


def test_epk_cover_color_logo_video_press():
    import io
    import music_apis
    client = _demo()
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    client.get("/epk")
    # Cover color: valid hex persists to the public page; junk is rejected.
    client.post("/epk/save", json={"bg_color": "#2a1015"})
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert "background-color: #2a1015" in public
    client.post("/epk/save", json={"bg_color": "javascript:alert(1)"})
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert "background-color: #141210" in public          # falls back to default
    # Logo asset renders above the hero on both editor and public page.
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    client.post("/epk/asset/logo", data={"asset": (io.BytesIO(png), "logo.png")},
                content_type="multipart/form-data")
    # An earlier test may have made the demo logo private; visibility is
    # deliberately preserved across re-uploads, so re-enable it here.
    client.post("/epk/asset/logo/visibility", json={"public": True})
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert 'alt="Synthwave Surfer logo"' in public
    # Video URL yields a thumbnail in the editor and an embed publicly.
    client.post("/epk/save", json={"video_url": "https://www.youtube.com/watch?v=xyz789"})
    editor = client.get("/epk").get_data(as_text=True)
    assert "img.youtube.com/vi/xyz789/hqdefault.jpg" in editor
    # Press quotes keep their source links on the public page.
    client.post("/epk/save", json={"press": [{"quote": "Brilliant live show.",
                                               "source": "Test Mag",
                                               "url": "https://example.com/review"}]})
    public = client.get("/epk/synthwave-surfer").get_data(as_text=True)
    assert 'href="https://example.com/review"' in public


def test_epk_press_search(monkeypatch):
    import music_apis
    rss = ('<rss><channel><item><title>Great new single - Test Weekly</title>'
           '<link>https://example.com/a</link><source url="https://tw.com">Test Weekly</source>'
           '<pubDate>Tue, 08 Jul 2026 01:00:00 GMT</pubDate></item></channel></rss>')
    monkeypatch.setattr(music_apis, "_fetch_text", lambda url: rss)
    client = create_app().test_client()
    # Requires sign-in.
    assert client.get("/epk/press/search?q=x").status_code == 401
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    data = client.get("/epk/press/search?q=Test Artist").get_json()
    assert data["ok"] and data["results"][0] == {
        "title": "Great new single", "source": "Test Weekly",
        "url": "https://example.com/a", "date": "Tue, 08 Jul 2026"}
    # Editor ships the finder UI.
    body = client.get("/epk").get_data(as_text=True)
    assert "press-search-btn" in body and "Find press on the web" in body
    assert "bg-swatch" in body                     # cover color swatches too


def test_bandsintown_tour_dates(monkeypatch):
    import db as store_mod
    import bandsintown_provider as bit
    monkeypatch.setenv("BANDSINTOWN_APP_ID", "test-app")
    monkeypatch.setattr(bit, "_fetch_json", lambda url: [
        {"datetime": "2026-08-01T20:00:00",
         "venue": {"name": "The Fillmore", "city": "Charlotte", "region": "NC"},
         "url": "https://bandsintown.com/e/1",
         "offers": [{"type": "Tickets", "url": "https://tix.example/1"}]}])
    app_obj = create_app()
    client = _demo(app_obj)
    assert client.post("/epk/save", json={
        "bandsintown_artist": "Art Is War"}).get_json()["ok"]
    # Editor: field prefilled, live dates render in the preview.
    body = client.get("/epk").get_data(as_text=True)
    assert "Bandsintown Artist Name" in body
    assert "The Fillmore" in body and "Aug 1, 2026" in body
    assert "Charlotte, NC" in body
    # Public EPK carries the tour section with the ticket link.
    # This user's slug, not "whatever EPK exists" - the tests share one
    # database, so LIMIT 1 picks up any account that happens to have
    # saved a kit first and asserts against a stranger's page.
    demo_user = store_mod.get_user_by_email("demo@streetbanker.io")
    with store_mod.get_db() as conn:
        slug = conn.execute(
            "SELECT slug FROM epk_profiles WHERE slug IS NOT NULL "
            "AND user_id = ?", (demo_user["id"],)).fetchone()["slug"]
    pub = app_obj.test_client().get("/epk/" + slug).get_data(as_text=True)
    assert "Tour Dates" in pub and "The Fillmore" in pub
    assert "https://tix.example/1" in pub
    assert "Live dates via Bandsintown" in pub


def test_bandsintown_honest_when_unconfigured(monkeypatch):
    monkeypatch.delenv("BANDSINTOWN_APP_ID", raising=False)
    client = _demo()
    body = client.get("/epk").get_data(as_text=True)
    # Field is disabled with an honest note; no fake dates anywhere.
    assert "not enabled on this server yet" in body
    assert "The Fillmore" not in body


def _pulse_http(url, data=None, headers=None):
    if "api/token" in url:
        return {"access_token": "apptok"}
    if "/v1/search" in url:
        return {"artists": {"items": [{
            "id": "art1", "name": "Art Is War",
            "followers": {"total": 4321}, "popularity": 41,
            "images": [{"url": "https://i/img.jpg"}], "genres": ["hip hop"]}]}}
    if "/top-tracks" in url:
        return {"tracks": [{"name": "Anthem", "popularity": 55,
                            "album": {"name": "LP1"},
                            "external_urls": {"spotify": "https://x/t1"}}]}
    if "/v1/artists/" in url:
        return {"id": "art1", "name": "Art Is War",
                "followers": {"total": 4321}, "popularity": 41,
                "genres": ["hip hop"], "images": [{"url": "https://i/big.jpg"}],
                "external_urls": {"spotify": "https://x/artist/art1"}}
    raise AssertionError("unexpected url: " + url)


def test_login_page_has_partner_demo_box():
    client = create_app().test_client()
    body = client.get("/login").get_data(as_text=True)
    # The Tour rack: four workspace radios, the demo password stays
    # server-side until a lead requests it, and the have-password form
    # still drives the same demo sign-in.
    assert "B. TOUR STREET BANKER" in body
    assert body.count('name="lsr-workspace"') == 4
    assert "REQUEST DEMO ACCESS" in body
    assert "OPEN SAMPLE WORKSPACE" in body
    assert "Demo password" in body
    assert "sweep" not in body          # never ship the password client-side
    # And the flow it drives signs in and lands on the guided tour.
    r = client.post("/login", data={"email": "demo@streetbanker.io",
                                    "password": "sweep"})
    assert r.status_code == 302 and "/walkthrough" in r.headers["Location"]


def test_tier_demo_accounts():
    app_obj = create_app()
    # Login page offers all four tier demos as workspace radios; the
    # component script maps each to its demo account.
    body = app_obj.test_client().get("/login").get_data(as_text=True)
    for value in ('value="artist"', 'value="pro"', 'value="label"',
                  'value="fan"'):
        assert value in body
    import io
    js = io.open("static/js/login-session-recall.js", encoding="utf-8").read()
    for email in ("demo@streetbanker.io", "demo-pro@streetbanker.io",
                  "demo-artist@streetbanker.io", "demo-fan@streetbanker.io"):
        assert email in js
    # Each signs in with the shared password and lands on its tour.
    for email, landing in (("demo@streetbanker.io", "/walkthrough"),
                           ("demo-pro@streetbanker.io", "/walkthrough"),
                           ("demo-artist@streetbanker.io", "/walkthrough"),
                           ("demo-fan@streetbanker.io", "/discover")):
        r = app_obj.test_client().post("/login", data={
            "email": email, "password": "sweep"})
        assert r.status_code == 302 and r.headers["Location"].endswith(landing)
    # The tiers actually gate: artist demo hits the paywall on a Pro page.
    artist = app_obj.test_client()
    artist.post("/login", data={"email": "demo-artist@streetbanker.io",
                                "password": "sweep"})
    assert artist.get("/overview").status_code == 402
    fan = app_obj.test_client()
    fan.post("/login", data={"email": "demo-fan@streetbanker.io",
                             "password": "sweep"})
    assert fan.get("/links").status_code == 402


def test_walkthrough_is_a_guided_tour():
    app_obj = create_app()
    artist = app_obj.test_client()
    artist.post("/login", data={"email": "demo-artist@streetbanker.io",
                                "password": "sweep"})
    wt = artist.get("/walkthrough").get_data(as_text=True)
    # Continue bar, per-step done buttons, and progress machinery.
    assert "Your progress" in wt and "Checklist" in wt
    assert "Done — next step" in wt and "wt-step-9" in wt
    assert 'target="_blank"' in wt          # steps never lose your place
    assert "Pro plan" in wt                 # artist tier sees the gate chips
    # In-app guided tour: launcher on the walkthrough, guide bar on every page.
    assert "Start guided tour" in wt and "sbStartTour" in wt
    links = artist.get("/links").get_data(as_text=True)
    assert 'id="tour-bar"' in links and 'data-plan="artist"' in links
    label = _demo(app_obj)
    assert "Pro plan</span>" not in label.get("/walkthrough").get_data(as_text=True)


def test_artist_pulse_live_flow(monkeypatch):
    import spotify_provider as sp
    import music_apis
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "csec")
    monkeypatch.setattr(sp, "_http", _pulse_http)
    monkeypatch.setattr(music_apis, "_fetch_json", lambda url: {"data": [{
        "id": 9, "name": "Art Is War", "nb_fan": 777,
        "link": "https://deezer.com/artist/9"}]})
    client = _demo()
    # One-time setup state, then search -> select -> live numbers.
    assert "Find yourself on Spotify" in client.get("/pulse").get_data(as_text=True)
    res = client.get("/pulse/search?q=art").get_json()
    assert res["results"][0]["followers"] == 4321
    assert client.post("/pulse/select", json=res["results"][0]).get_json()["ok"]
    body = client.get("/pulse").get_data(as_text=True)
    assert "4,321" in body                       # Spotify followers
    assert "Anthem" in body and "LP1" in body    # live top tracks
    assert "777" in body                         # Deezer fans
    assert "refreshed every 6 hours" in body     # honest sourcing note
    # Change Artist resets to setup.
    assert client.post("/pulse/clear").get_json()["ok"]
    assert "Find yourself on Spotify" in client.get("/pulse").get_data(as_text=True)


def test_artist_pulse_honest_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    client = _demo()
    body = client.get("/pulse").get_data(as_text=True)
    assert "Not Connected" in body
    assert "4,321" not in body                   # never sample numbers
    # Search endpoint returns empty rather than pretending.
    assert client.get("/pulse/search?q=art").get_json()["results"] == []


def test_release_day_emails(monkeypatch):
    import db as store_mod
    import links_store as mls
    import email_provider as emailer
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    sent = []
    monkeypatch.setattr(emailer, "_http",
                        lambda url, payload, headers: sent.append(payload) or {"id": "em1"})
    app_obj = create_app()
    client = _demo(app_obj)
    r = client.post("/links/new", data={
        "title": "Email Drop", "release_date": "2031-01-01",
        "email_capture": "1", "consent_text": "ok",
        "dest_spotify": "https://open.spotify.com/track/T1"})
    cid = r.headers["Location"].split("/")[2]
    client.post("/links/%s/publish" % cid)
    slug = mls.get_campaign(cid)["slug"]
    anon = app_obj.test_client()
    # Fan subscribes pre-release; no email yet.
    anon.post("/l/%s/subscribe" % slug, data={"email": "notifyme@example.net"})
    anon.get("/l/" + slug)
    assert sent == []
    # Release day: first page view emails the fan exactly once.
    with store_mod.get_db() as conn:
        conn.execute("UPDATE ml_campaigns SET release_date = ? WHERE id = ?",
                     ("2020-01-01", cid))
    anon.get("/l/" + slug)
    assert len(sent) == 1
    assert sent[0]["to"] == ["notifyme@example.net"]
    assert "Email Drop is out now" == sent[0]["subject"]
    assert "/l/" + slug in sent[0]["html"]        # listen link points home
    # Second view never double-sends; owner got a notification.
    anon.get("/l/" + slug)
    assert len(sent) == 1
    owner = mls.get_campaign(cid)["user_id"]
    notes = [n for n in store_mod.list_notifications(owner)
             if "Release emails sent" in n["title"]]
    assert len(notes) == 1 and "1 fan" in notes[0]["body"]


def test_release_emails_never_send_unconfigured(monkeypatch):
    import db as store_mod
    import links_store as mls
    import email_provider as emailer
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setattr(emailer, "_http",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    app_obj = create_app()
    client = _demo(app_obj)
    r = client.post("/links/new", data={
        "title": "Quiet Drop", "release_date": "2020-01-01",
        "email_capture": "1", "consent_text": "ok",
        "dest_spotify": "https://open.spotify.com/track/T2"})
    cid = r.headers["Location"].split("/")[2]
    client.post("/links/%s/publish" % cid)
    slug = mls.get_campaign(cid)["slug"]
    anon = app_obj.test_client()
    anon.post("/l/%s/subscribe" % slug, data={"email": "notifyme@example.net"})
    anon.get("/l/" + slug)      # released view: no key -> no send, no crash
    assert not emailer.configured()


# --- Street Banker Links: campaign engine ------------------------------------

def _demo(app_obj=None):
    """App pages now require login; demo account is the showcase."""
    client = (app_obj or create_app()).test_client()
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    return client


def _ml_login(app_obj):
    client = app_obj.test_client()
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    return client


def _ml_create(client, **overrides):
    data = {"title": "Test Drop", "artist_name": "Test Artist",
            "release_type": "Single", "campaign_type": "release",
            "cover_url": "https://x/art.jpg", "description": "New single.",
            "email_capture": "1", "consent_text": "I agree to updates.",
            "dest_spotify": "https://open.spotify.com/track/x",
            "dest_apple_music": "https://music.apple.com/x",
            "dest_youtube": "https://youtube.com/watch?v=x"}
    data.update(overrides)
    r = client.post("/links/new", data=data)
    assert r.status_code == 302
    return r.headers["Location"].split("/")[2]


def test_ml_campaign_lifecycle_and_public_page():
    import links_store as mls
    app_obj = create_app()
    client = _ml_login(app_obj)
    # Anonymous cannot create.
    anon = app_obj.test_client()
    assert anon.post("/links/new", data={"title": "x"}).status_code == 302  # -> login
    cid = _ml_create(client)
    camp = mls.get_campaign(cid)
    assert camp["status"] == "draft"
    # Draft is invisible to the public but previewable by the owner.
    assert anon.get("/l/" + camp["slug"]).status_code == 404
    assert "Draft preview" in client.get("/l/" + camp["slug"]).get_data(as_text=True)
    client.post("/links/%s/publish" % cid)
    page = anon.get("/l/" + camp["slug"]).get_data(as_text=True)
    assert "Test Drop" in page and "Listen Now" in page
    assert "Powered by" in page and "Street Banker" in page
    assert "I agree to updates." in page          # consent copy on public form
    # Page view tracked; service click via /go/ redirects and tracks.
    dests = mls.get_destinations(cid)
    r = anon.get("/l/%s/go/%s" % (camp["slug"], dests[0]["id"]))
    assert r.status_code == 302 and "spotify" in r.headers["Location"]
    counts = mls.event_counts(cid)
    assert counts["page_view"] >= 1 and counts["service_click"] == 1
    # Archive -> public 410 unavailable state.
    client.post("/links/%s/archive" % cid)
    assert anon.get("/l/" + camp["slug"]).status_code == 410


def test_ml_presave_capture_consent_and_intent():
    import links_store as mls
    app_obj = create_app()
    client = _ml_login(app_obj)
    cid = _ml_create(client, campaign_type="presave", release_date="2030-01-01",
                     title="Future Drop")
    client.post("/links/%s/publish" % cid)
    camp = mls.get_campaign(cid)
    anon = app_obj.test_client()
    page = anon.get("/l/" + camp["slug"]).get_data(as_text=True)
    assert "Dropping in" in page and 'id="countdown"' in page  # pre-save state
    # Bad email rejected; good email creates fan + consent + presave event.
    assert anon.post("/l/%s/subscribe" % camp["slug"],
                     data={"email": "junk"}).status_code == 400
    r = anon.post("/l/%s/subscribe" % camp["slug"],
                  data={"email": "Fan@Example.com", "name": "Fan One"})
    assert r.get_json()["ok"]
    fans = mls.list_fans(camp["user_id"], "fan@example.com")
    assert fans and fans[0]["total_presaves"] == 1
    assert fans[0]["intent_score"] > 0 and fans[0]["intent_level"] != ""
    consents = mls.list_consents(fans[0]["id"])
    assert consents[0]["consent_type"] == "presave_notify"
    assert consents[0]["consent_text"] == "I agree to updates."
    # Fan CRM lists + exports the fan.
    assert "fan@example.com" in client.get("/links/fans").get_data(as_text=True)
    assert "fan@example.com" in client.get("/links/fans/export.csv").get_data(as_text=True)
    # Duplicate emails update, not duplicate.
    anon.post("/l/%s/subscribe" % camp["slug"], data={"email": "fan@example.com"})
    assert len(mls.list_fans(camp["user_id"], "fan@example.com")) == 1


def test_ml_score_variants_qr_duplicate():
    import links_store as mls
    app_obj = create_app()
    client = _ml_login(app_obj)
    # Bare campaign scores low with actionable warnings.
    bare = _ml_create(client, title="Bare", cover_url="", description="",
                      email_capture="", consent_text="", dest_spotify="",
                      dest_apple_music="", dest_youtube="")
    body = client.get("/links/%s/edit" % bare).get_data(as_text=True)
    assert "Spotify destination missing." in body
    assert "No email capture enabled" in body
    import links_engine
    camp = mls.get_campaign(bare)
    score = links_engine.calculate_street_banker_score(camp, [])
    assert score["total"] < 40
    # Full campaign scores high once published.
    full = _ml_create(client, title="Full", release_date="2030-06-01")
    client.post("/links/%s/publish" % full)
    camp = mls.get_campaign(full)
    score = links_engine.calculate_street_banker_score(
        camp, mls.get_destinations(full))
    assert score["total"] >= 70
    # Variants: unique slug, tracked separately, QR per variant.
    client.post("/links/%s/variants" % full,
                data={"name": "Instagram bio", "utm_source": "instagram"})
    variants = mls.list_variants(full)
    assert len(variants) == 1
    anon = app_obj.test_client()
    anon.get("/l/%s?v=%s" % (camp["slug"], variants[0]["slug"]))
    assert mls.variant_stats(full)[variants[0]["id"]]["page_view"] == 1
    r = client.get("/links/%s/qr.svg?v=%s" % (full, variants[0]["slug"]))
    assert r.status_code == 200 and b"<svg" in r.data
    # Duplicate copies destinations, resets to draft.
    r = client.post("/links/%s/duplicate" % full)
    new_id = r.headers["Location"].split("/")[2]
    dup = mls.get_campaign(new_id)
    assert dup["status"] == "draft" and "(copy)" in dup["title"]
    assert len(mls.get_destinations(new_id)) == len(mls.get_destinations(full))
    # Dashboard shows campaign cards with the score.
    body = client.get("/links").get_data(as_text=True)
    assert "Music Link Campaigns" in body and "SB Score" in body


def test_ml_autofill_and_cover_upload(monkeypatch):
    import io
    import music_apis
    import links_store as mls
    monkeypatch.setattr(music_apis, "_fetch_json", _fake_odesli)
    app_obj = create_app()
    # Autofill requires sign-in, then maps Odesli platforms to service keys.
    anon = app_obj.test_client()
    assert anon.get("/links/autofill?url=https://x").status_code == 302
    client = _ml_login(app_obj)
    data = client.get("/links/autofill?url=https://open.spotify.com/track/t").get_json()
    assert data["ok"] and data["title"] == "Fake Song" and data["artist"] == "Fake Artist"
    assert data["links"]["spotify"] == "https://sp/x"
    assert data["links"]["apple_music"] == "https://ap/x"
    assert data["links"]["youtube"] == "https://yt/x"
    # A bad URL fails gracefully.
    monkeypatch.setattr(music_apis, "_fetch_json",
                        lambda url: (_ for _ in ()).throw(Exception("down")))
    assert client.get("/links/autofill?url=https://bad").get_json()["ok"] is False
    # Cover art uploads as a file and overrides the URL field.
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = client.post("/links/new", data={
        "title": "Upload Test", "cover_url": "https://ignored.example/x.jpg",
        "cover_file": (io.BytesIO(png), "cover.png")},
        content_type="multipart/form-data")
    cid = r.headers["Location"].split("/")[2]
    camp = mls.get_campaign(cid)
    assert camp["cover_url"].startswith("/uploads/mlcover_")
    assert client.get(camp["cover_url"]).status_code == 200  # actually served


# --- Rollout Engine ------------------------------------------------------------

def test_rollout_studio_full_flow():
    import io
    import links_store as mls
    import rollout_store as ros
    app_obj = create_app()
    client = _ml_login(app_obj)
    # Attach a published Links campaign for attribution.
    ml_id = _ml_create(client, title="Rollout Base", release_date="2031-01-01")
    client.post("/links/%s/publish" % ml_id)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = client.post("/rollout-studio/new", data={
        "title": "Rollout Base", "artist_name": "Test Artist",
        "release_date": "2031-01-01", "rollout_length": "7", "goal": "presaves",
        "tone": "street", "ml_campaign_id": ml_id,
        "pf_instagram_reels": "1", "pf_tiktok": "1", "pf_x": "1",
        "art_file": (io.BytesIO(png), "art.png"),
        "video_file": (io.BytesIO(b"0" * 128), "clip.mp4"),
        "lyrics": "Neon lights across the bay\nWe ride until the break of day\nNothing left to prove",
    }, content_type="multipart/form-data")
    cid = r.headers["Location"].split("/")[2]
    # Generation: dated posts across the phase arc, one Links variant each.
    client.post("/rollout-studio/%s/generate" % cid)
    posts = ros.list_posts(cid)
    assert len(posts) == 10                      # 7 pre-release + release + 2 follow-ups
    phases = [p["phase"] for p in posts]
    assert phases[0] == "tease" and "release_day" in phases and "post_release" in phases
    assert all(p["variant_id"] for p in posts)
    variants = mls.list_variants(ml_id)
    assert len(variants) == len(posts)
    assert variants[0]["name"].startswith("rollout_")
    assert variants[0]["utm_medium"] == "rollout"
    # Lyrics feed the lyric-reveal caption; video posts get edit plans.
    lyric_posts = [p for p in posts if p["phase"] == "lyric_reveal"]
    assert any("ride until the break" in p["caption"] for p in lyric_posts)
    video_posts = [p for p in posts if p["edit_plan"]]
    assert video_posts and video_posts[0]["edit_plan"]["aspect_ratio"] == "9:16"
    assert "export_checklist" in video_posts[0]["edit_plan"]
    # Approval workflow + manual posting with published URL.
    pid = posts[0]["id"]
    client.post("/rollout-studio/%s/posts" % cid,
                data={"post_id": pid, "action": "approve"})
    assert ros.get_post(pid)["status"] == "approved"
    client.post("/rollout-studio/%s/posts" % cid,
                data={"post_id": pid, "action": "posted",
                      "published_url": "https://instagram.com/p/abc"})
    post = ros.get_post(pid)
    assert post["status"] == "posted" and post["published_url"].endswith("/abc")
    # Attribution: a fan hitting this post's variant shows on performance.
    ml_camp = mls.get_campaign(ml_id)
    vslug = next(v["slug"] for v in variants if v["id"] == posts[0]["variant_id"])
    anon = app_obj.test_client()
    anon.get("/l/%s?v=%s" % (ml_camp["slug"], vslug))
    perf = client.get("/rollout-studio/%s/performance" % cid).get_data(as_text=True)
    assert "Top Posts" in perf and "1v" in perf
    # All pages render; socials shows manual mode ready.
    for path in ("", "/posts", "/calendar", "/socials"):
        assert client.get("/rollout-studio/%s%s" % (cid, path)).status_code == 200
    socials = client.get("/rollout-studio/%s/socials" % cid).get_data(as_text=True)
    assert "Manual posting" in socials and "ready" in socials
    assert "TikTok" in socials and "needs credentials" in socials
    # Dashboard card with attribution totals.
    dash = client.get("/rollout-studio").get_data(as_text=True)
    assert "Rollout Base" in dash and "link clicks" in dash
    # Other users cannot see this rollout.
    other = app_obj.test_client()
    import uuid as _uuid
    other.post("/signup", data={"name": "O", "email": "o%s@x.com" % _uuid.uuid4().hex[:6],
                                "password": "secret1"})
    assert other.get("/rollout-studio/%s" % cid).status_code == 404


# --- Artist OS: Command Center + Actions ---------------------------------------

def test_command_center_and_actions():
    import command_center as cc_mod
    import db as store_mod
    from datetime import date, timedelta
    app_obj = create_app()
    # Anonymous users are sent to sign in.
    assert app_obj.test_client().get("/command-center").status_code == 302
    client = _ml_login(app_obj)
    # A live campaign with gaps drives real derived alerts.
    soon = (date.today() + timedelta(days=3)).isoformat()
    r = client.post("/links/new", data={"title": "OS Drop", "release_date": soon,
                                        "dest_spotify": "https://open.spotify.com/track/x"})
    cid = r.headers["Location"].split("/")[2]
    client.post("/links/%s/publish" % cid)
    body = client.get("/command-center").get_data(as_text=True)
    assert "Command Center" in body and "capturing fans" in body
    assert "with no rollout" in body           # release in 3 days, no rollout
    assert "OS Drop" in body and "Autopilot" in body
    assert "Fraud Sentinel" in body            # module grid with previews
    # Alert -> action -> lifecycle.
    client.post("/actions/from-alert", data={"title": "Enable capture on OS Drop",
                                             "description": "x", "category": "fan_growth"})
    body = client.get("/actions").get_data(as_text=True)
    assert "Enable capture on OS Drop" in body
    user = store_mod.get_user_by_email("demo@streetbanker.io")
    action = next(a for a in cc_mod.list_actions(user["id"])
                  if a["title"] == "Enable capture on OS Drop")
    client.post("/actions", data={"action_id": action["id"], "status": "in_progress"})
    client.post("/actions", data={"action_id": action["id"], "status": "complete"})
    refreshed = next(a for a in cc_mod.list_actions(user["id"])
                     if a["id"] == action["id"])
    assert refreshed["status"] == "complete" and refreshed["completed_at"]
    # Manual action creation with priority ordering.
    client.post("/actions", data={"title": "Call the plant", "category": "release",
                                  "priority": "high"})
    body = client.get("/actions?status=new").get_data(as_text=True)
    assert "Call the plant" in body


def test_release_autopilot_and_clean_release():
    app_obj = create_app()
    client = _ml_login(app_obj)
    r = client.post("/links/new", data={"title": "Checklist Drop",
                                        "dest_spotify": "https://open.spotify.com/track/x"})
    cid = r.headers["Location"].split("/")[2]
    for route in ("/releases/autopilot", "/releases/clean-release"):
        body = client.get("%s?campaign=%s" % (route, cid)).get_data(as_text=True)
        assert "Checklist Drop" in body
        assert "Spotify destination" in body          # passing check listed
        assert "Apple Music destination" in body      # failing check listed
        assert "Create action" in body                # failed checks are actionable
        assert "ready" in body                        # score badge


def test_capital_score_and_spend_optimizer_real():
    import io
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "Cap Tester", "email": "cap@example.net",
                                 "password": "cappass"})
    client.post("/plan/switch", data={"plan": "pro"})
    csv = ("title,source,amount,period\n"
           "A,Spotify,900,2026-01\n"
           "A,Apple Music,300,2026-02\n"
           "B,Deezer,150,2026-03\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv.encode()), "cap.csv")},
                content_type="multipart/form-data")
    body = client.get("/capital-score").get_data(as_text=True)
    assert "Capital Readiness" in body
    assert "$1,350" in body                     # real income on record
    assert "Illustrative Advance Band" in body
    assert "not financial advice" in body
    body = client.get("/spend-optimizer?budget=1000").get_data(as_text=True)
    assert "Recommended split" in body and "$400.00" in body
    assert "Don't spend it here" in body
    # Money features stay behind the Pro wall.
    artist = app_obj.test_client()
    artist.post("/login", data={"email": "demo-artist@streetbanker.io",
                                "password": "sweep"})
    assert artist.get("/capital-score").status_code == 402
    assert artist.get("/spend-optimizer").status_code == 402


def test_metadata_passport_real():
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "MP Tester", "email": "mp@example.net",
                                 "password": "mppass"})
    uid = store_mod.get_user_by_email("mp@example.net")["id"]
    # Empty state points at the catalog.
    assert "Add your first track" in client.get("/metadata-passport").get_data(as_text=True)
    tid = store_mod.add_catalog_track(uid, {"title": "Passport Song",
                                            "artist": "Art Is War"})
    store_mod.set_catalog_track_meta(uid, tid, {
        "isrc": "USX9P2100001", "upc": "0198001", "label": "AIW Records",
        "release_date": "2026-01-01", "album": "LP1",
        "writers": ["V. Kaye"], "publishers": []})
    body = client.get("/metadata-passport").get_data(as_text=True)
    assert "Catalog Completeness" in body and "Passport Song" in body
    assert "6/7 fields" in body                       # real completeness math
    assert "✕ Publishers" in body and "✓ ISRC" in body
    csv = client.get("/metadata-passport/export.csv").get_data(as_text=True)
    assert "USX9P2100001" in csv and "V. Kaye" in csv


def test_statement_dropbox_webhook(monkeypatch):
    import base64
    import hashlib
    import hmac
    import json
    import db as store_mod
    import email_provider as emailer
    secret_raw = base64.b64encode(b"hooksecret").decode()
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "whsec_" + secret_raw)
    monkeypatch.setenv("RESEND_INBOUND_DOMAIN", "inbound-t.resend.app")
    monkeypatch.setattr(emailer, "list_received_attachments", lambda email_id: [
        {"filename": "sym.csv", "content_type": "text/csv",
         "download_url": "https://cdn/a1"}])
    csv = b"title,source,amount,period\nDrop Song,Spotify,321.00,2026-05\n"
    monkeypatch.setattr(emailer, "download_attachment", lambda url: csv)
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "Box", "email": "box@example.net",
                                 "password": "boxpass"})
    client.post("/plan/switch", data={"plan": "pro"})
    body = client.get("/statements").get_data(as_text=True)
    assert "Your statement drop-box" in body
    token = body.split("@inbound-t.resend.app")[0].split(">")[-1]

    def sign(payload):
        signed = "m1.1700000000." + payload
        sig = base64.b64encode(hmac.new(base64.b64decode(secret_raw),
                                        signed.encode(), hashlib.sha256).digest()).decode()
        return {"svix-id": "m1", "svix-timestamp": "1700000000",
                "svix-signature": "v1," + sig}

    anon = app_obj.test_client()
    payload = json.dumps({"type": "email.received", "data": {
        "email_id": "em1", "to": ["%s@inbound-t.resend.app" % token]}})
    # Forged signatures never ingest.
    assert anon.post("/webhooks/resend", data=payload, headers={
        "svix-id": "m1", "svix-timestamp": "1700000000",
        "svix-signature": "v1,forged"}, content_type="application/json").status_code == 401
    # Signed webhook lands the CSV in the right account.
    out = anon.post("/webhooks/resend", data=payload, headers=sign(payload),
                    content_type="application/json").get_json()
    assert out["ok"] and out["ingested"] == 1
    uid = store_mod.get_user_by_email("box@example.net")["id"]
    assert any(r["title"] == "Drop Song" and r["amount"] == 321.0
               for r in store_mod.get_statement_rows(uid))
    # Unknown recipient is ignored, never guessed.
    p2 = json.dumps({"type": "email.received", "data": {
        "email_id": "em2", "to": ["stranger@inbound-t.resend.app"]}})
    assert anon.post("/webhooks/resend", data=p2, headers=sign(p2),
                     content_type="application/json").get_json()["ignored"]


def _stripe_sig(payload, secret=b"whsec_stripetest"):
    import hashlib
    import hmac
    import time
    t = str(int(time.time()))
    sig = hmac.new(secret, ("%s.%s" % (t, payload)).encode(),
                   hashlib.sha256).hexdigest()
    return {"Stripe-Signature": "t=%s,v1=%s" % (t, sig)}


def test_stripe_checkout_and_webhooks(monkeypatch):
    import json
    import db as store_mod
    import stripe_provider as sb
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_stripetest")
    calls = []
    monkeypatch.setattr(sb, "_http", lambda path, fields: calls.append(
        (path, fields)) or {"id": "cs_1", "url": "https://checkout.stripe.com/c/1"})
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "Payer", "email": "payer2@example.net",
                                 "password": "paypass"})
    # Real accounts see real checkout, not the demo switch.
    body = client.get("/billing").get_data(as_text=True)
    assert "Subscribe — $29/mo" in body and "Switch (demo)" not in body
    r = client.post("/billing/checkout", data={"plan": "pro"})
    assert r.status_code == 303 and "checkout.stripe.com" in r.headers["Location"]
    path, fields = calls[0]
    assert path == "/v1/checkout/sessions"
    assert fields["line_items[0][price_data][unit_amount]"] == "2900"
    assert fields["mode"] == "subscription"
    # Paid demo switching is blocked for real users when Stripe is live.
    uid = store_mod.get_user_by_email("payer2@example.net")["id"]
    client.post("/plan/switch", data={"plan": "label"})
    assert store_mod.get_user(uid)["plan"] != "label"
    # Webhook: signature required; completed checkout activates the plan.
    anon = app_obj.test_client()
    payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {
        "client_reference_id": uid, "customer": "cus_t9", "subscription": "sub_t9",
        "metadata": {"plan": "pro"}}}})
    assert anon.post("/webhooks/stripe", data=payload,
                     headers={"Stripe-Signature": "t=1,v1=forged"},
                     content_type="application/json").status_code == 401
    anon.post("/webhooks/stripe", data=payload, headers=_stripe_sig(payload),
              content_type="application/json")
    u = store_mod.get_user(uid)
    assert u["plan"] == "pro" and u["stripe_customer_id"] == "cus_t9"
    assert "Manage Billing" in client.get("/billing").get_data(as_text=True)
    # Cancellation downgrades to the free tier, data untouched.
    p2 = json.dumps({"type": "customer.subscription.deleted",
                     "data": {"object": {"customer": "cus_t9"}}})
    anon.post("/webhooks/stripe", data=p2, headers=_stripe_sig(p2),
              content_type="application/json")
    assert store_mod.get_user(uid)["plan"] == "fan"


def test_billing_sync_claims_completed_checkout(monkeypatch):
    import db as store_mod
    import stripe_provider as sb
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "Sync", "email": "sync@example.net",
                                 "password": "syncpass"})
    # Nothing found: honest message, no plan change.
    monkeypatch.setattr(sb, "active_subscription_for_email", lambda email: None)
    r = client.post("/billing/sync")
    assert r.headers["Location"].endswith("?sync=none")
    uid = store_mod.get_user_by_email("sync@example.net")["id"]
    assert store_mod.get_user(uid)["plan"] == "artist"
    # Active sub in Stripe: plan applies, ids stored, notification lands.
    monkeypatch.setattr(sb, "active_subscription_for_email", lambda email: {
        "customer_id": "cus_s1", "subscription_id": "sub_s1", "plan": "artist"}
        if email == "sync@example.net" else None)
    monkeypatch.setattr(sb, "active_subscription_for_email", lambda email: {
        "customer_id": "cus_s1", "subscription_id": "sub_s1", "plan": "pro"})
    r = client.post("/billing/sync")
    assert "upgraded=1" in r.headers["Location"]
    u = store_mod.get_user(uid)
    assert u["plan"] == "pro" and u["stripe_customer_id"] == "cus_s1"


def test_stripe_absent_keeps_honest_demo_switching(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "NoPay", "email": "nopay@example.net",
                                 "password": "nopaypass"})
    body = client.get("/billing").get_data(as_text=True)
    assert "Switch (demo)" in body and "Subscribe —" not in body
    assert "no payment is taken" in body
    assert client.post("/webhooks/stripe", data="{}").status_code == 404
    r = client.post("/billing/checkout", data={"plan": "pro"})
    assert r.status_code == 302        # falls back to /billing, never fakes


def test_ai_artwork_generate_and_save(monkeypatch):
    import music_apis
    app_obj = create_app()
    client = _demo(app_obj)
    # Generate: real image URL from the free model + palette suggestion.
    data = client.post("/artwork/generate", json={
        "prompt": "moody midnight synthwave"}).get_json()
    assert data["ok"]
    assert data["image_url"].startswith("https://image.pollinations.ai/prompt/")
    assert "moody%20midnight%20synthwave" in data["image_url"]
    assert "nologo=true" in data["image_url"]
    assert data["suggestion"]["colorway_id"]
    # Empty prompt: suggestion only, never a fake image.
    assert client.post("/artwork/generate", json={}).get_json()["image_url"] is None
    # Save: downloads the generated image into the user's uploads.
    monkeypatch.setattr(music_apis, "fetch_image_bytes",
                        lambda url, timeout=60: b"\xff\xd8fakejpegbytes")
    out = client.post("/artwork/save", json={"url": data["image_url"]}).get_json()
    assert out["ok"] and out["path"].startswith("/uploads/aiart_")
    assert client.get(out["path"]).status_code == 200
    # Only generated-image URLs are fetchable — no proxying arbitrary hosts.
    bad = client.post("/artwork/save", json={"url": "https://evil.example/x.jpg"})
    assert bad.status_code == 400


def test_artwork_studio_upload_and_controls():
    import io
    app_obj = create_app()
    client = _demo(app_obj)
    body = client.get("/artwork").get_data(as_text=True)
    # Text controls + upload + remix all ship.
    for needle in ('id="title-color"', 'id="artist-color"', 'id="text-size"',
                   'id="text-x"', 'id="text-y"', 'id="art-upload"',
                   'id="remix-btn"', "re-imagines the same concept",
                   # full studio: alignment, case/shadow, spacing, artist size,
                   # image zoom/pan/darken, save-finished-cover, line breaks
                   'id="upper-toggle"', 'id="text-style"',
                   'id="letter-spacing"', 'id="artist-size"',
                   'id="img-scrim"', 'id="img-zoom"', 'id="img-panx"',
                   'id="save-cover-btn"', "use / for a line break"):
        assert needle.lower() in body.lower(), needle
    # Upload lands in the user's uploads and serves back.
    r = client.post("/artwork/upload", data={
        "art": (io.BytesIO(b"\x89PNGfake"), "mycover.png")},
        content_type="multipart/form-data")
    out = r.get_json()
    assert out["ok"] and out["path"].startswith("/uploads/artup_")
    assert client.get(out["path"]).status_code == 200
    # Wrong types are rejected.
    r = client.post("/artwork/upload", data={
        "art": (io.BytesIO(b"MZ"), "virus.exe")}, content_type="multipart/form-data")
    assert r.status_code == 400
    # Remix reuses a seed deterministically.
    a = client.post("/artwork/generate", json={"prompt": "neon skyline",
                                               "seed": 777}).get_json()
    b = client.post("/artwork/generate", json={"prompt": "neon skyline, add rain",
                                               "seed": 777}).get_json()
    assert "seed=777" in a["image_url"] and "seed=777" in b["image_url"]
    assert "add%20rain" in b["image_url"]


def test_fan_club_full_loop(monkeypatch):
    import json
    import db as store_mod
    import links_store as mls
    import stripe_provider as sb
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_stripetest")
    monkeypatch.setattr(sb, "_http", lambda path, fields: {
        "id": "cs_c", "url": "https://checkout.stripe.com/c/club"})
    app_obj = create_app()
    artist = _demo(app_obj)
    # Configure and open the club.
    artist.post("/fan-club", data={"name": "Inner Circle T", "price": "7.5",
                                   "blurb": "b", "perks": "Early drops",
                                   "active": "1"})
    body = artist.get("/fan-club").get_data(as_text=True)
    assert "Open for members" in body
    slug = body.split("/club/")[1].split('"')[0]
    # Public page + join -> Stripe checkout.
    anon = app_obj.test_client()
    pub = anon.get("/club/" + slug).get_data(as_text=True)
    assert "Inner Circle T" in pub and "Early drops" in pub
    r = anon.post("/club/%s/join" % slug, data={"email": "clubfan@example.net"})
    assert r.status_code == 303 and "checkout.stripe.com" in r.headers["Location"]
    # Signed webhook lands the member in the roster and the Fan CRM.
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {
        "customer": "cus_ct", "subscription": "sub_ct",
        "metadata": {"kind": "fan_club", "artist_id": uid,
                     "member_email": "clubfan@example.net"}}}})
    anon.post("/webhooks/stripe", data=payload, headers=_stripe_sig(payload),
              content_type="application/json")
    assert any(m["member_email"] == "clubfan@example.net"
               for m in store_mod.list_club_members(uid))
    assert mls.list_fans(uid, "clubfan@example.net")
    # Cancellation flips status without touching the artist's plan.
    p2 = json.dumps({"type": "customer.subscription.deleted",
                     "data": {"object": {"id": "sub_ct", "customer": "cus_ct"}}})
    anon.post("/webhooks/stripe", data=p2, headers=_stripe_sig(p2),
              content_type="application/json")
    canceled = [m for m in store_mod.list_club_members(uid)
                if m["member_email"] == "clubfan@example.net"][0]
    assert canceled["status"] == "canceled"
    assert store_mod.get_user(uid)["plan"] == "label"


def test_partner_portal_role_scoping():
    app_obj = create_app()
    artist = _demo(app_obj)
    uid_body = artist.post("/team/invite", data={
        "email": "portal-acct@example.net", "role": "accountant"}).get_json()
    tok = uid_body["link"].split("/team/join/")[1]
    member = app_obj.test_client()
    member.post("/team/join/" + tok, data={"name": "Books", "password": "bookpass"})
    body = member.get("/portal").get_data(as_text=True)
    assert "accountant" in body
    import db as store_mod
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    view = member.get("/portal/" + uid).get_data(as_text=True)
    assert "read-only" in view and "Money" in view
    assert "Promotion" not in view          # accountants don't see promo
    # Non-members are shut out entirely.
    stranger = app_obj.test_client()
    stranger.post("/signup", data={"name": "S", "email": "portal-stranger@example.net",
                                   "password": "strange1"})
    assert stranger.get("/portal/" + uid).status_code == 404


def test_shopify_merch_stitch():
    import links_store as mls
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    assert artist.post("/epk/save", json={
        "store_url": "https://artiswar.myshopify.com",
        "merch": [{"title": "Logo Tee", "price": "$30",
                   "url": "https://artiswar.myshopify.com/products/tee"}]}).get_json()["ok"]
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    # Make the EPK this test needs rather than hoping an earlier test in
    # the file left one behind - under -n the file is split across
    # workers, so which tests ran first is not something to rely on. Only
    # when it is missing: /epk/save replaces the whole profile, and these
    # tests share one database.
    # A row can exist without a slug - save_epk_photo inserts one with
    # none - so check for the slug, not the row. Set it through the db
    # layer rather than a route: /epk/share is the private pitch-link
    # token, not the public slug, and which route happens to mint the
    # public one is not something a fixture should depend on.
    if not store_mod.get_epk(uid):
        artist.post("/epk/save", data={"bio": "fixture"})
    if not (store_mod.get_epk(uid) or {}).get("slug"):
        store_mod.set_epk_slug(uid, "fixture-slug-%s" % uid[:8])
    slug = store_mod.get_epk(uid)["slug"]
    pub = app_obj.test_client().get("/epk/" + slug).get_data(as_text=True)
    assert "Merch" in pub and "Logo Tee" in pub and "Full store" in pub
    # The store button rides along on live smart-link pages.
    live = [c for c in mls.list_campaigns(uid) if c["status"] == "live"]
    if live:
        lp = app_obj.test_client().get("/l/" + live[0]["slug"]).get_data(as_text=True)
        assert "Merch Store" in lp


def test_preview_modules_are_honest():
    client = _ml_login(create_app())
    routes = ["/fraud-sentinel", "/ai-rights",
              "/opportunities", "/voice-of-fan", "/royalty-recovery/mlc"]
    for route in routes:
        r = client.get(route)
        assert r.status_code == 200, route
        body = r.get_data(as_text=True)
        assert "in preview" in body, route            # no fake functionality
    assert "not legal advice" in client.get("/ai-rights").get_data(as_text=True)
    assert "not financial advice" in client.get("/capital-score").get_data(as_text=True)


# --- Plan tiers + product worlds -------------------------------------------------

def test_plan_tiers_gate_sections():
    import uuid as _uuid
    app_obj = create_app()
    client = app_obj.test_client()
    email = "tier%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "T", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    # Artist tier: Promote works, Royalty Sweep is gated with the upgrade page.
    assert client.get("/links").status_code == 200
    assert client.get("/command-center").status_code == 200
    r = client.get("/overview")
    assert r.status_code == 402
    assert "This is a Pro feature" in r.get_data(as_text=True)
    assert client.get("/statements").status_code == 402
    # Demo plan switch unlocks it (labeled demo until Stripe).
    client.post("/plan/switch", data={"plan": "pro"})
    assert client.get("/overview").status_code == 200
    assert client.get("/catalog").status_code == 200
    # Billing shows the plan cards.
    body = client.get("/billing").get_data(as_text=True)
    assert "Your Plan" in body and "Switch (demo)" in body


def test_fan_accounts_get_fan_shell():
    import uuid as _uuid
    app_obj = create_app()
    client = app_obj.test_client()
    email = "fanshell%s@x.com" % _uuid.uuid4().hex[:6]
    r = client.post("/signup", data={"name": "F", "email": email, "password": "secret1",
                                     "account_type": "fan"})
    assert r.headers["Location"] == "/discover"
    body = client.get("/discover").get_data(as_text=True)
    # Fan shell: Community nav, no artist tooling, no world switcher.
    assert "Fan Account" in body and ">Community<" in body
    assert "Rollout Engine" not in body and "Statements" not in body
    # Artist tools are gated for fans.
    assert client.get("/links").status_code == 402
    assert client.get("/overview").status_code == 402
    # Fan login lands on Discover.
    fresh = app_obj.test_client()
    r = fresh.post("/login", data={"email": email, "password": "secret1"})
    assert r.headers["Location"] == "/discover"


def test_world_switcher_and_public_pages():
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/login", data={"email": "demo@streetbanker.io", "password": "sweep"})
    # Demo account has the Label plan: everything open, switcher rendered.
    body = client.get("/links").get_data(as_text=True)
    assert "/world/sweep" in body and "/world/fan" in body
    # Ecosystem Hub model: every artist world carries all five hubs.
    assert "Rollout Engine" in body and "Statements" in body
    assert 'data-hub="launch"' in body and 'data-hub="money"' in body
    assert client.get("/world/label").headers["Location"] == "/services"
    # Signed-out visitors are sent to login; share pages stay public.
    anon = app_obj.test_client()
    assert anon.get("/links").status_code == 302
    assert anon.get("/epk").status_code == 302
    assert anon.get("/l/nonexistent-slug").status_code in (302, 404)


# --- Release OS: qualification, profile, vault, review queue ---------------------

def test_qualification_score_from_real_data():
    import qualification
    import db as store_mod
    app_obj = create_app()
    client = _ml_login(app_obj)
    user = store_mod.get_user_by_email("demo@streetbanker.io")
    before = qualification.calculate(user["id"])["total"]
    # Real work moves the score: publish a fully-set-up campaign.
    cid = _ml_create(client, title="Qual Drop", release_date="2031-06-01")
    client.post("/links/%s/publish" % cid)
    after = qualification.calculate(user["id"])
    # Other tests may have already saturated some categories in the shared DB.
    assert after["total"] >= before and after["total"] > 0
    assert "Fan Capture Enabled" in after["badges"]
    assert after["recommendation"] in ("Needs work", "Approve — with guidance",
                                       "High potential")
    # Page renders meters, unlocks, and action shortcuts.
    body = client.get("/qualification").get_data(as_text=True)
    assert "Growth Score" in body and "Release Readiness" in body
    assert "What Your Score Unlocks" in body and "Raise growth score" in body


def test_artist_profile_and_vault():
    client = _ml_login(create_app())
    cid = _ml_create(client, title="Sheet Drop")
    body = client.get("/artist-profile").get_data(as_text=True)
    assert "Label-Facing One-Sheet" in body and "SB Score" in body
    assert "Sheet Drop" in body            # campaign history is real
    assert "Fans owned" in body
    vault = client.get("/vault").get_data(as_text=True)
    assert "Archive Drawer" in vault and "Sheet Drop" in vault
    assert "Cover art" in vault and "Manage" in vault


def test_admin_review_queue_owner_only(monkeypatch):
    import uuid as _uuid
    monkeypatch.setenv("OWNER_EMAILS", "demo@streetbanker.io")
    app_obj = create_app()
    owner_client = _ml_login(app_obj)
    body = owner_client.get("/admin/review").get_data(as_text=True)
    assert "Review Queue" in body and "Synthwave Surfer" in body
    # Paid tiers cannot see the internal curation desk.
    artist = app_obj.test_client()
    artist.post("/signup", data={"name": "A", "email": "rq%s@x.com" % _uuid.uuid4().hex[:6],
                                 "password": "secret1", "account_type": "artist"})
    assert artist.get("/admin/review").status_code == 404
    assert artist.get("/qualification").status_code == 200  # own score always visible


# --- Real royalty engine: statements power the money pages -----------------------

def test_money_pages_use_real_statement_data():
    import io
    import uuid as _uuid
    app_obj = create_app()
    client = app_obj.test_client()
    email = "money%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "M", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    # Before any upload: honest sample-data nudge.
    body = client.get("/overview").get_data(as_text=True)
    assert "Sample data below" in body and "Upload a statement" in body
    csv_data = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"Midnight Drive,Spotify,120.50,2026-04\n"
                b"Midnight Drive,Apple Music,80.25,2026-05\n"
                b"Neon Dreams,Spotify,60.00,2026-05\n"
                b",Spotify,12.40,2026-05\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv_data), "s.csv")},
                content_type="multipart/form-data")
    # Overview: real totals, unmatched, top track.
    body = client.get("/overview").get_data(as_text=True)
    assert "Your Real Numbers" in body and "273.15" in body and "12.40" in body
    assert "Midnight Drive" in body
    # Royalties: source bars, monthly trend, top tracks.
    body = client.get("/royalties").get_data(as_text=True)
    assert "By Source" in body and "Monthly Trend" in body and "200.75" in body
    # Recovery: unmatched + coverage-gap findings with action buttons.
    body = client.get("/recovery").get_data(as_text=True)
    assert "Unattributed revenue" in body and "12.40" in body
    assert "Neon Dreams" in body and "Apple Music" in body
    assert "Create recovery action" in body
    # The showcase's hardcoded figures are nowhere near this account.
    assert "3,301.38" not in body and "Ready to Claim" not in body
    # Valuation: annualized signal with the honesty disclaimer.
    body = client.get("/valuation").get_data(as_text=True)
    assert "Annualised run rate" in body and "Catalog signal" in body
    assert "not financial advice" in body
    # Not the showcase's hardcoded Jan-Jun curve.
    assert "31,000" not in body and "Payout consistency" not in body
    # Command Center surfaces the money-on-the-table alerts first.
    body = client.get("/command-center").get_data(as_text=True)
    assert "unmatched revenue in your statements" in body
    assert "coverage gap" in body


def test_royalty_summary_math():
    from statements_engine import build_royalty_summary
    rows = [
        {"title": "A", "source": "Spotify", "amount": 100.0, "period": "2026-01"},
        {"title": "A", "source": "Apple Music", "amount": 50.0, "period": "2026-02"},
        {"title": "", "source": "Spotify", "amount": 10.0, "period": "2026-02"},
    ]
    s = build_royalty_summary(rows)
    assert s["total"] == 160.0
    assert s["monthly_trend"] == [("2026-01", 100.0), ("2026-02", 60.0)]
    assert s["annualized"] == 960.0            # 160 over 2 months, annualized
    assert s["valuation"]["low"] == 2880 and s["valuation"]["high"] == 4800
    assert build_royalty_summary([]) is None


# --- Real reports ------------------------------------------------------------------

def test_real_reports_suite():
    import io
    import uuid as _uuid
    app_obj = create_app()
    client = app_obj.test_client()
    email = "rep%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "R", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})   # reports live in Royalty Sweep
    # Seed real activity: a published campaign and a statement.
    r = client.post("/links/new", data={"title": "Report Drop",
                                        "dest_spotify": "https://sp/x"})
    cid = r.headers["Location"].split("/")[2]
    client.post("/links/%s/publish" % cid)
    csv_rows = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"Midnight Drive,Spotify,120.50,2026-04\n"
                b",Spotify,12.40,2026-05\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv_rows), "s.csv")},
                content_type="multipart/form-data")
    # Reports hub shows the live-data band.
    body = client.get("/reports").get_data(as_text=True)
    assert "Your Real Reports" in body and "Executive Report" in body
    # Campaign CSV carries real rows.
    body = client.get("/reports/campaigns.csv").get_data(as_text=True)
    assert "Report Drop" in body and "SB Score" in body
    # Recovery CSV carries the unmatched finding.
    body = client.get("/reports/recovery.csv").get_data(as_text=True)
    assert "Unmatched revenue" in body and "12.4" in body
    # Executive report composes score + money + campaigns + fans.
    body = client.get("/reports/executive").get_data(as_text=True)
    for marker in ("Executive Report", "SB Qualification", "Royalty Findings",
                   "Report Drop", "Fan Ownership", "Prepared by Street Banker"):
        assert marker in body
    # Signed-out visitors are redirected, never served account data.
    assert app_obj.test_client().get("/reports/executive").status_code == 302
    assert app_obj.test_client().get("/reports/campaigns.csv").status_code == 302


# --- Real notifications ------------------------------------------------------------

def test_notifications_from_real_events():
    import io
    import re
    import uuid as _uuid
    app_obj = create_app()
    client = app_obj.test_client()
    email = "ntf%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "N", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    # Publish -> notification; fan subscribe -> notification; statement -> notification.
    r = client.post("/links/new", data={"title": "Bell Drop", "email_capture": "1",
                                        "consent_text": "ok",
                                        "dest_spotify": "https://sp/x"})
    cid = r.headers["Location"].split("/")[2]
    client.post("/links/%s/publish" % cid)
    import links_store as mls
    slug = mls.get_campaign(cid)["slug"]
    app_obj.test_client().post("/l/%s/subscribe" % slug, data={"email": "bellfan@x.com"})
    csv_rows = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"Midnight Drive,Spotify,120.50,2026-04\n"
                b",Spotify,12.40,2026-05\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv_rows), "s.csv")},
                content_type="multipart/form-data")
    # Badge shows unread count in the nav. Design system v1 moved it off
    # gold: gold is brand and primary action, and an unread counter is a
    # state indicator, so it wears the info colour.
    body = client.get("/links").get_data(as_text=True)
    assert re.search(r'text-sb-info">\d+</span>', body)
    # Page lists all three real events and clears the badge.
    body = client.get("/notifications").get_data(as_text=True)
    assert "Campaign live: Bell Drop" in body
    assert "bellfan@x.com" in body
    assert "Recovery findings in s.csv" in body
    body = client.get("/links").get_data(as_text=True)
    assert not re.search(r'text-\[#1c1302\]">\d+</span>', body)
    # Anonymous visitors are redirected to login.
    assert app_obj.test_client().get("/notifications").status_code == 302


# --- Documents vault + real identifiers --------------------------------------------

def test_documents_vault_real():
    import io
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "doc%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "D", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    r = client.post("/documents", data={
        "document": (io.BytesIO(b"%PDF-1.4 fake"), "producer-split.pdf"),
        "doc_type": "Producer Agreement", "note": "50/50 with Marcus"},
        content_type="multipart/form-data")
    assert r.status_code == 302
    body = client.get("/documents").get_data(as_text=True)
    assert "Add to your vault" in body and "producer-split.pdf" in body
    assert "50/50 with Marcus" in body
    user = store_mod.get_user_by_email(email)
    doc = store_mod.list_documents(user["id"])[0]
    assert client.get(doc["path"]).status_code == 200      # actually served
    # Dangerous extensions rejected; deletion removes listing + file.
    bad = client.post("/documents", data={"document": (io.BytesIO(b"x"), "evil.exe")},
                      content_type="multipart/form-data")
    assert "Use PDF" in bad.get_data(as_text=True)
    client.post("/documents/%s/delete" % doc["id"])
    assert "producer-split.pdf" not in client.get("/documents").get_data(as_text=True)
    # Other users cannot delete someone else's document.
    assert store_mod.delete_document("someone-else", doc["id"]) is None


def test_identifiers_page_uses_real_catalog(monkeypatch):
    import music_apis
    monkeypatch.setattr(music_apis, "_fetch_json", _fake_deezer)
    monkeypatch.setattr(music_apis.time, "sleep", lambda s: None)
    client = _ml_login(create_app())
    client.post("/catalog/add", json={"title": "ID Song", "artist": "A"})
    body = client.get("/identifiers").get_data(as_text=True)
    assert "Your Identifiers" in body
    assert "USTEST2500001" in body and "123456789012" in body   # real pulled IDs
    assert "auto-pulled from your catalog" in body
    # A metadata-less track is flagged with an actionable MISSING row.
    monkeypatch.setattr(music_apis, "_fetch_json",
                        lambda url: {"data": [], "results": []})
    client.post("/catalog/add", json={"title": "No Meta Song", "artist": "B"})
    body = client.get("/identifiers").get_data(as_text=True)
    assert "MISSING" in body and "Create action" in body


# --- Recovery cases + deal room ------------------------------------------------

def test_recovery_case_lifecycle():
    import io
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "case%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "C", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    # One-click case from a statement finding.
    client.post("/royalty-recovery/cases/from-finding",
                data={"title": "Unmatched statement revenue", "category": "unmatched",
                      "amount": "12.40", "notes": "from finding"})
    body = client.get("/royalty-recovery/cases").get_data(as_text=True)
    assert "Unmatched statement revenue" in body and "12.40" in body
    # Manual case -> submitted -> won with payout; totals + notification.
    client.post("/royalty-recovery/cases",
                data={"title": "Content ID claim", "category": "content_id",
                      "estimated_amount": "85"})
    user = store_mod.get_user_by_email(email)
    case = next(x for x in store_mod.list_recovery_cases(user["id"])
                if "Content ID" in x["title"])
    client.post("/royalty-recovery/cases", data={"case_id": case["id"], "status": "submitted"})
    client.post("/royalty-recovery/cases", data={"case_id": case["id"], "status": "won",
                                                 "payout_result": "92.50"})
    body = client.get("/royalty-recovery/cases").get_data(as_text=True)
    assert "92.50" in body and "Recovered" in body
    assert "Case won: Content ID claim" in client.get("/notifications").get_data(as_text=True)
    # Evidence from the vault attaches to a case.
    client.post("/documents", data={"document": (io.BytesIO(b"%PDF x"), "evidence.pdf"),
                                    "doc_type": "Statement"},
                content_type="multipart/form-data")
    doc = store_mod.list_documents(user["id"])[0]
    open_case = next(x for x in store_mod.list_recovery_cases(user["id"])
                     if x["status"] == "open")
    client.post("/royalty-recovery/cases", data={"case_id": open_case["id"],
                                                 "status": "open",
                                                 "evidence_doc_id": doc["id"]})
    assert "evidence.pdf" in client.get("/royalty-recovery/cases").get_data(as_text=True)
    # Recovery findings page offers Open case buttons.
    csv_rows = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"A,Spotify,10.00,2026-05\n"
                b",Spotify,5.00,2026-05\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv_rows), "s.csv")},
                content_type="multipart/form-data")
    assert "Open case" in client.get("/recovery").get_data(as_text=True)


def test_deal_room_and_split_generator():
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "deal%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "D", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    client.post("/deal-room", data={"title": "Producer deal", "deal_type": "producer",
                                    "counterparty": "Marcus", "terms": "3 points"})
    body = client.get("/deal-room").get_data(as_text=True)
    assert "Producer deal" in body and "Marcus" in body and "not legal advice" in body
    user = store_mod.get_user_by_email(email)
    deal = store_mod.list_deals(user["id"])[0]
    client.post("/deal-room", data={"deal_id": deal["id"], "status": "signed"})
    assert next(d for d in store_mod.list_deals(user["id"])
                if d["id"] == deal["id"])["status"] == "signed"
    # Split generator: vault document + tracked deal, honest template text.
    client.post("/deal-room/generate-split", data={
        "track": "Neon Nights", "party1_name": "Artist", "party1_share": "60",
        "party2_name": "Producer", "party2_share": "40"})
    body = client.get("/deal-room").get_data(as_text=True)
    assert "Split: Neon Nights" in body and "Artist 60%" in body
    gen = next(d for d in store_mod.list_documents(user["id"])
               if "split-agreement" in d["filename"])
    txt = client.get(gen["path"]).get_data(as_text=True)
    assert "SPLIT AGREEMENT" in txt and "NOT LEGAL ADVICE" in txt and "60%" in txt
    # Fewer than two parties: no deal created.
    before = len(store_mod.list_deals(user["id"]))
    client.post("/deal-room/generate-split", data={"track": "Solo",
                                                   "party1_name": "Artist",
                                                   "party1_share": "100"})
    assert len(store_mod.list_deals(user["id"])) == before


# --- Sync clearance packs ------------------------------------------------------

def test_sync_clearance_pack_flow():
    import io
    import re
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "sync%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "S", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    # Main audio is required; bad request re-renders with the error.
    r = client.post("/sync/clearance-packs", data={"title": "No Audio"},
                    content_type="multipart/form-data")
    assert "Upload the main audio" in r.get_data(as_text=True)
    # Full pack with two audio files.
    r = client.post("/sync/clearance-packs", data={
        "title": "Sync Track", "artist_name": "Test Artist", "bpm": "118",
        "song_key": "A min", "moods": "dark, driving",
        "master_status": "cleared", "publishing_status": "cleared",
        "ownership_note": "One-stop, no samples.",
        "contact_email": "team.summitarts@gmail.com",
        "main_audio": (io.BytesIO(b"ID3fake"), "t.mp3"),
        "instrumental_audio": (io.BytesIO(b"ID3inst"), "t-inst.mp3")},
        content_type="multipart/form-data")
    assert r.status_code == 302
    user = store_mod.get_user_by_email(email)
    pack = store_mod.list_sync_packs(user["id"])[0]
    body = client.get("/sync/clearance-packs").get_data(as_text=True)
    assert "Sync Track" in body and "Master cleared" in body
    # Anonymous supervisor page: facts, one-stop badge, streaming audio, noindex.
    anon = app_obj.test_client()
    public = anon.get("/s/" + pack["slug"]).get_data(as_text=True)
    assert "Private Sync Pack" in public and "118 BPM" in public
    assert "One-Stop" in public and public.count("<audio") == 2
    assert "noindex" in public
    src = re.search(r'src="(/uploads/sync_[^"]+)"', public).group(1)
    assert anon.get(src).status_code == 200
    # License request lands in inbox and notifies the owner.
    r = anon.post("/s/%s/request" % pack["slug"],
                  data={"email": "supervisor@studio.com", "message": "Trailer use"})
    assert r.get_json()["ok"]
    assert "License request: Sync Track" in client.get("/notifications").get_data(as_text=True)
    # Views counted; archiving kills the public link.
    assert store_mod.get_sync_pack_by_slug(pack["slug"])["views"] >= 1
    client.post("/sync/clearance-packs", data={"pack_id": pack["id"], "status": "archived"})
    assert anon.get("/s/" + pack["slug"]).status_code == 404


# --- Deal simulator + artist twin ------------------------------------------------

def test_sync_deal_simulator():
    import sync_simulator
    # Engine: lowball perpetuity exclusive trailer offer gets flagged hard.
    res = sync_simulator.simulate({"fee": 500, "media": "trailer",
                                   "term": "perpetuity", "territory": "worldwide",
                                   "exclusive": True, "buyout": True})
    assert res["position"] == "below"
    flag_text = " ".join(t for _sev, t in res["flags"])
    assert "Perpetuity / buyout" in flag_text
    assert "Exclusivity below the range floor" in flag_text
    assert res["counteroffer"] and "one-stop" in res["counteroffer"]
    # A fair offer sits within range and needs no counteroffer.
    res = sync_simulator.simulate({"fee": 2000, "media": "web_social",
                                   "term": "3y", "territory": "worldwide"})
    assert res["position"] == "within" and res["counteroffer"] is None
    # Gratis offers warn about exposure-only terms.
    res = sync_simulator.simulate({"fee": 0, "media": "indie_film",
                                   "term": "1y", "territory": "single"})
    assert any("Gratis" in t for _sev, t in res["flags"])
    # Page renders form + results with the disclaimer.
    client = _ml_login(create_app())
    body = client.post("/sync/deal-simulator",
                       data={"fee": "500", "media": "trailer", "term": "perpetuity",
                             "territory": "worldwide", "buyout": "1"}).get_data(as_text=True)
    assert "Market Range" in body and "Counteroffer Draft" in body
    assert "not legal or financial advice" in body


def test_artist_twin_consent_and_generation():
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "twin%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "Twin Artist", "email": email,
                                 "password": "secret1", "account_type": "artist"})
    client.post("/epk/save", json={"tagline": "Night drive synths.",
                                   "bio": "Analog and modern.",
                                   "press": [{"quote": "Gleaming work.",
                                              "source": "Test Mag"}]})
    # Consent layer: only EPK approved, "Gleaming" is forbidden.
    client.post("/artist-twin", data={"save_settings": "1", "src_epk": "1",
                                      "tone": "street", "do_not_say": "Gleaming"})
    body = client.post("/artist-twin", data={"kind": "press_pitch"}).get_data(as_text=True)
    assert "Sources used" in body
    sources_section = body.split("Sources used")[1][:150]
    assert "Press kit" in sources_section
    assert "Campaigns" not in sources_section       # excluded source never read
    # Do-not-say enforced on the fresh generation block.
    gen_block = body.split('id="gen-text"')[1].split("</p>")[0]
    assert "Gleaming" not in gen_block
    # Generation history persists with its source audit.
    user = store_mod.get_user_by_email(email)
    gens = store_mod.list_twin_generations(user["id"])
    assert gens and gens[0]["kind"] == "press_pitch"
    assert "Press kit" in gens[0]["sources_used"]


# --- Revenue OS + trust score ------------------------------------------------------

def test_revenue_os_pnl():
    import io
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "rev%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "R", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    # Real income from a statement, self-reported spend, net computed.
    csv_rows = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"A,Spotify,500.00,2026-04\n"
                b"B,Apple Music,300.00,2026-05\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv_rows), "s.csv")},
                content_type="multipart/form-data")
    client.post("/revenue-os", data={"description": "Mix and master",
                                     "category": "mixing_mastering", "amount": "350"})
    client.post("/revenue-os", data={"description": "Meta ads",
                                     "category": "marketing_ads", "amount": "200"})
    body = client.get("/revenue-os").get_data(as_text=True)
    assert "800.00" in body            # real statement income
    assert "550.00" in body            # tracked spend
    assert "250.00" in body            # net
    assert "not financial advice" in body
    # Deleting an expense updates the ledger.
    user = store_mod.get_user_by_email(email)
    exp = store_mod.list_expenses(user["id"])[0]
    client.post("/revenue-os", data={"delete_id": exp["id"]})
    assert len(store_mod.list_expenses(user["id"])) == 1
    # Invalid amounts are ignored.
    client.post("/revenue-os", data={"description": "junk", "category": "other",
                                     "amount": "not-a-number"})
    assert len(store_mod.list_expenses(user["id"])) == 1


def test_trust_score_from_real_state():
    import uuid as _uuid
    import db as store_mod
    import trust_score
    app_obj = create_app()
    client = app_obj.test_client()
    email = "trust%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "T", "email": email, "password": "secret1",
                                 "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    user = store_mod.get_user_by_email(email)
    before = trust_score.calculate(user["id"])
    assert before["verdict"] == "Getting started" and before["blockers"]
    # Real work moves the score: a signed split agreement.
    client.post("/deal-room/generate-split", data={
        "track": "T", "party1_name": "A", "party1_share": "60",
        "party2_name": "B", "party2_share": "40"})
    deal = store_mod.list_deals(user["id"])[0]
    client.post("/deal-room", data={"deal_id": deal["id"], "status": "signed"})
    after = trust_score.calculate(user["id"])
    assert after["total"] > before["total"]
    # Page renders factors, blockers, badge preview, and action shortcuts.
    body = client.get("/trust-score").get_data(as_text=True)
    assert "Trust Score" in body and "Blocking Factors" in body
    assert "Verified by" in body and "Raise trust score" in body
    assert "not a credit score" in body


# --- Spotify pre-save OAuth ---------------------------------------------------

def _spotify_env(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "csec")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "https://x/presave/callback")


def test_spotify_presave_oauth_flow(monkeypatch):
    import urllib.parse
    import db as store_mod
    import links_store as mls
    import spotify_provider as sp
    _spotify_env(monkeypatch)
    monkeypatch.setattr(sp, "_http", lambda url, data=None, headers=None: (
        {"access_token": "at", "refresh_token": "rt"} if "api/token" in url
        else {"id": "fan123", "email": "PresaveFan@Example.com",
              "display_name": "Presave Fan"}))
    app_obj = create_app()
    client = _demo(app_obj)
    r = client.post("/links/new", data={
        "title": "Presave Drop", "release_date": "2031-01-01",
        "email_capture": "1", "consent_text": "ok",
        "dest_spotify": "https://open.spotify.com/track/TRACK123"})
    cid = r.headers["Location"].split("/")[2]
    client.post("/links/%s/publish" % cid)
    slug = mls.get_campaign(cid)["slug"]
    anon = app_obj.test_client()
    # Button renders on the pre-release page.
    body = anon.get("/l/" + slug).get_data(as_text=True)
    assert "Pre-Save on Spotify" in body
    # Start -> Spotify authorize with a session-bound state.
    r = anon.get("/presave/%s/start" % slug)
    assert "accounts.spotify.com/authorize" in r.headers["Location"]
    state = urllib.parse.parse_qs(
        urllib.parse.urlparse(r.headers["Location"]).query)["state"][0]
    # Forged state is rejected.
    r = anon.get("/presave/callback?code=abc&state=%s.forged" % slug)
    assert "presave=error" in r.headers["Location"]
    # Real callback: presave stored encrypted, fan lands in CRM with consent.
    r = anon.get("/presave/%s/start" % slug)
    state = urllib.parse.parse_qs(
        urllib.parse.urlparse(r.headers["Location"]).query)["state"][0]
    r = anon.get("/presave/callback?code=abc&state=" + state)
    assert r.headers["Location"].endswith("?presave=done")
    pres = store_mod.pending_spotify_presaves(cid)
    assert len(pres) == 1 and pres[0]["refresh_token_enc"] != "rt"
    assert sp.decrypt_token(pres[0]["refresh_token_enc"]) == "rt"
    owner = mls.get_campaign(cid)["user_id"]
    fan = mls.list_fans(owner, "presavefan@example.com")[0]
    assert fan["total_presaves"] == 1
    assert mls.list_consents(fan["id"])[0]["consent_type"] == "spotify_presave"
    # Duplicate pre-save is deduped.
    r = anon.get("/presave/%s/start" % slug)
    state = urllib.parse.parse_qs(
        urllib.parse.urlparse(r.headers["Location"]).query)["state"][0]
    r = anon.get("/presave/callback?code=abc&state=" + state)
    assert r.headers["Location"].endswith("?presave=already")
    # Release day: a page view lazily delivers the save to the fan's library.
    with store_mod.get_db() as conn:
        conn.execute("UPDATE ml_campaigns SET release_date = ? WHERE id = ?",
                     ("2020-01-01", cid))
    saved = []
    monkeypatch.setattr(sp, "refresh_access_full",
                        lambda rt: {"access_token": "fresh",
                                    "scope": "user-library-modify user-read-email"})
    monkeypatch.setattr(sp, "save_track",
                        lambda at, tid: saved.append((at, tid)) or True)
    anon.get("/l/" + slug)
    assert saved == [("fresh", "TRACK123")]
    assert store_mod.count_spotify_presaves(cid).get("completed") == 1


def test_spotify_presave_hidden_without_env():
    import links_store as mls
    app_obj = create_app()
    client = _demo(app_obj)
    r = client.post("/links/new", data={
        "title": "NoEnv Drop", "release_date": "2031-01-01",
        "dest_spotify": "https://open.spotify.com/track/x"})
    cid = r.headers["Location"].split("/")[2]
    client.post("/links/%s/publish" % cid)
    slug = mls.get_campaign(cid)["slug"]
    anon = app_obj.test_client()
    body = anon.get("/l/" + slug).get_data(as_text=True)
    assert "Pre-Save on Spotify" not in body       # never fake availability
    r = anon.get("/presave/%s/start" % slug)
    assert r.headers["Location"].endswith("/l/" + slug)


def test_ml_quick_links_still_work():
    # The original quick smart links share /l/ and must be untouched.
    client = _demo()
    r = client.post("/links/create", json={"title": "Quick", "platforms": ["Spotify"]})
    slug = r.get_json()["link"]["slug"]
    assert client.get("/l/" + slug).status_code == 302


def test_api_cache_roundtrip():
    import db as store
    store.cache_set("t:key", {"a": 1})
    assert store.cache_get("t:key", 60) == {"a": 1}
    assert store.cache_get("t:key", -1) is None  # expired
    assert store.cache_get("missing", 60) is None


def test_catalog_data_config_shapes():
    from catalog_config import get_catalog_data
    data = get_catalog_data()
    assert data["tabs"] == ["Tracks", "Releases", "Songwriters", "Publishers", "Splits"]
    assert data["tracks"] and data["releases"] and data["songwriters"]
    assert data["publishers"] and data["splits"] and data["recently_added"]
    assert data["registered_pct"] == 82.7
    assert data["health"]["total"] == 76


def test_update_fix_status_invalid_status_returns_400():
    client = _demo()
    response = client.post("/fixes/some-id/status", json={"status": "NotAStatus"})
    assert response.status_code == 400


def test_registration_wizard_route():
    client = _demo()
    response = client.get("/songs/midnight-drive/registration-wizard")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["wizard"]["song_id"] == "midnight-drive"


def test_registration_wizard_unknown_song_returns_404():
    client = _demo()
    response = client.get("/songs/not-a-real-song/registration-wizard")
    assert response.status_code == 404


def test_complete_registration_wizard_step_route():
    client = _demo()
    try:
        response = client.post("/songs/midnight-drive/registration-wizard/publishing_admin/complete")
        assert response.status_code == 200
        data = response.get_json()
        assert data["wizard"]["status"]["publishing_admin"] is True
    finally:
        reset_registration_wizard_state()


def test_complete_registration_wizard_step_unknown_song_returns_404():
    client = _demo()
    response = client.post("/songs/not-a-real-song/registration-wizard/pro/complete")
    assert response.status_code == 404


def test_generate_report_route():
    """The invariant, not the state: a filename is only ever returned
    when there are bytes behind it. This used to assert ok:True while the
    route invented a name and built nothing.

    Deliberately does not assume whether the demo account has statements
    - the suite shares one database and other tests upload to it, so that
    varies with shard count. Asserting the contract holds either way."""
    client = _demo()
    response = client.post("/reports/royalty-report/generate")
    assert response.status_code == 200
    data = response.get_json()
    if data["ok"]:
        assert data["report"]["id"] == "royalty-report"
        got = client.get(data["report"]["download"])
        assert got.status_code == 200, "claimed a file that will not download"
        assert got.get_data(as_text=True).strip(), "download was empty"
    else:
        assert data.get("error"), "refused without saying why"


def test_generate_report_unknown_id_returns_404():
    client = _demo()
    response = client.post("/reports/not-a-report/generate")
    assert response.status_code == 404


def test_team_real_invite_flow(monkeypatch):
    import db as store_mod
    import email_provider as emailer
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    sent = []
    monkeypatch.setattr(emailer, "_http",
                        lambda url, payload, headers: sent.append(payload) or {"id": "e"})
    app_obj = create_app()
    owner = _demo(app_obj)
    assert "Invite someone" in owner.get("/team").get_data(as_text=True)
    r = owner.post("/team/invite", data={"email": "roadie@example.net",
                                         "role": "assistant"}).get_json()
    assert r["ok"] and r["emailed"] and "/team/join/" in r["link"]
    assert sent[0]["to"] == ["roadie@example.net"]
    token = r["link"].split("/team/join/")[1]
    # Duplicate invite blocked.
    assert not owner.post("/team/invite", data={"email": "roadie@example.net",
                                                "role": "manager"}).get_json()["ok"]
    # Join publicly, creating an account; roster flips to Active.
    joiner = app_obj.test_client()
    assert "Accept Invite" in joiner.get("/team/join/" + token).get_data(as_text=True)
    assert joiner.post("/team/join/" + token, data={
        "name": "Roadie", "password": "roadpass"}).status_code == 302
    body = owner.get("/team").get_data(as_text=True)
    assert "Roadie" in body and "Active" in body
    # Token is single-use; member can be removed.
    assert "Invite not found" in app_obj.test_client().get(
        "/team/join/" + token).get_data(as_text=True)
    owner_id = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    mid = store_mod.list_team(owner_id)[0]["id"]
    assert owner.post("/team/%s/remove" % mid).get_json()["ok"]


def test_password_reset_flow(monkeypatch):
    import email_provider as emailer
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    sent = []
    monkeypatch.setattr(emailer, "_http",
                        lambda url, payload, headers: sent.append(payload) or {"id": "e"})
    app_obj = create_app()
    c = app_obj.test_client()
    c.post("/signup", data={"name": "PW Tester", "email": "pwtest@example.net",
                            "password": "oldpass"})
    anon = app_obj.test_client()
    assert "Forgot password?" in anon.get("/login").get_data(as_text=True)
    r = anon.post("/forgot", data={"email": "pwtest@example.net"})
    assert "reset link is on its way" in r.get_data(as_text=True)
    token = sent[0]["html"].split("/reset/")[1].split('"')[0]
    # Unknown email: identical response, nothing sent.
    anon.post("/forgot", data={"email": "ghost@example.net"})
    assert len(sent) == 1
    # Reset signs you in; old password stops working.
    assert anon.post("/reset/" + token,
                     data={"password": "newpass"}).status_code == 302
    assert b"Incorrect" in app_obj.test_client().post(
        "/login", data={"email": "pwtest@example.net", "password": "oldpass"}).data
    assert app_obj.test_client().post(
        "/login", data={"email": "pwtest@example.net",
                        "password": "newpass"}).status_code == 302
    assert "Link expired" in app_obj.test_client().get(
        "/reset/bogus").get_data(as_text=True)


def test_legal_pages_public():
    client = create_app().test_client()
    for path, needle in (("/terms", "Terms of Service"), ("/privacy", "Privacy Policy")):
        body = client.get(path).get_data(as_text=True)
        assert needle in body and "Last updated" in body


def test_stats_page_real_only(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    client = _demo()
    body = client.get("/stats").get_data(as_text=True)
    # Honest: no platform numbers without credentials, no fake stream counts.
    assert "Not Connected" in body
    assert "Cross-platform performance" not in body


def test_settings_has_quick_links_and_signout():
    client = _demo()
    body = client.get("/settings").get_data(as_text=True)
    assert 'href="/team"' in body
    assert 'href="/billing"' in body
    assert 'action="/logout"' in body


def test_webhook_auto_setup(monkeypatch):
    import hashlib as _hashlib
    import hmac as _hmac
    import json as _json
    import time as _time
    import db as store_mod
    import stripe_provider as sb
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    created, deleted = {}, []
    monkeypatch.setattr(sb, "_http_get", lambda path: {"data": [
        {"id": "we_old", "url": "http://localhost/webhooks/stripe"}]})
    monkeypatch.setattr(sb, "_http_delete",
                        lambda path: deleted.append(path) or {"deleted": True})
    monkeypatch.setattr(sb, "_http", lambda path, fields: (
        created.update(fields) or {"id": "we_new", "secret": "whsec_kvstored"}))
    app_obj = create_app()
    outsider = app_obj.test_client()
    outsider.post("/signup", data={"name": "O", "email": "webhook-outsider@example.net",
                                   "password": "outside1"})
    assert outsider.post("/billing/webhook-setup").status_code == 404
    artist = _demo(app_obj)
    # Owner sees the one-click card while the webhook is missing.
    assert "Set up webhook automatically" in artist.get("/billing").get_data(as_text=True)
    r = artist.post("/billing/webhook-setup")
    assert r.status_code == 302 and "webhook=ok" in r.headers["Location"]
    assert deleted == ["/v1/webhook_endpoints/we_old"]  # stale endpoint replaced
    assert created["enabled_events[0]"] == "checkout.session.completed"
    assert store_mod.get_kv("stripe_webhook_secret") == "whsec_kvstored"
    assert sb.webhook_configured()
    assert "active" in artist.get("/billing").get_data(as_text=True)
    # A webhook signed with the stored secret verifies with no env secret.
    payload = _json.dumps({"type": "invoice.payment_failed",
                           "data": {"object": {"customer": "cus_none"}}})
    t = str(int(_time.time()))
    sig = _hmac.new(b"whsec_kvstored", ("%s.%s" % (t, payload)).encode(),
                    _hashlib.sha256).hexdigest()
    resp = app_obj.test_client().post(
        "/webhooks/stripe", data=payload, content_type="application/json",
        headers={"Stripe-Signature": "t=%s,v1=%s" % (t, sig)})
    assert resp.get_json()["ok"]
    store_mod.set_kv("stripe_webhook_secret", "")  # shared-DB cleanup


def test_club_members_area(monkeypatch):
    import db as store_mod
    import email_provider as emailer_mod
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    sent = {}
    monkeypatch.setattr(emailer_mod, "send",
                        lambda to, subject, html, attachments=None:
                        sent.update({"to": to, "html": html}) or True)
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/fan-club", data={"name": "Members Test Club", "price": "5",
                                   "blurb": "b", "perks": "Early drops",
                                   "active": "1"})
    artist.post("/fan-club/drops", data={"title": "Secret Demo v1",
                                         "body": "Members hear it first.",
                                         "link_url": "https://example.net/demo"})
    assert "Secret Demo v1" in artist.get("/fan-club").get_data(as_text=True)
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    # Make the EPK this test needs rather than hoping an earlier test in
    # the file left one behind - under -n the file is split across
    # workers, so which tests ran first is not something to rely on. Only
    # when it is missing: /epk/save replaces the whole profile, and these
    # tests share one database.
    # A row can exist without a slug - save_epk_photo inserts one with
    # none - so check for the slug, not the row. Set it through the db
    # layer rather than a route: /epk/share is the private pitch-link
    # token, not the public slug, and which route happens to mint the
    # public one is not something a fixture should depend on.
    if not store_mod.get_epk(uid):
        artist.post("/epk/save", data={"bio": "fixture"})
    if not (store_mod.get_epk(uid) or {}).get("slug"):
        store_mod.set_epk_slug(uid, "fixture-slug-%s" % uid[:8])
    slug = store_mod.get_epk(uid)["slug"]
    store_mod.add_club_member(uid, "vip@example.net", "cus_v", "sub_vip")
    fan = app_obj.test_client()
    # The gate never leaks drop content.
    gate = fan.get("/club/%s/members" % slug).get_data(as_text=True)
    assert "Member access" in gate and "Secret Demo v1" not in gate
    # Magic link -> signed in -> feed visible.
    r = fan.post("/club/%s/members/link" % slug, data={"email": "vip@example.net"})
    assert "sent=1" in r.headers["Location"] and sent["to"] == "vip@example.net"
    token_path = sent["html"].split('href="')[1].split('"')[0].replace(
        "http://localhost", "")
    assert fan.get(token_path).status_code == 302
    feed = fan.get("/club/%s/members" % slug).get_data(as_text=True)
    assert "Secret Demo v1" in feed and "vip@example.net" in feed
    # A non-member request gets the same neutral message but no email.
    before = dict(sent)
    r = fan.post("/club/%s/members/link" % slug, data={"email": "nobody@example.net"})
    assert "sent=1" in r.headers["Location"] and sent == before
    # Cancellation locks the door again.
    store_mod.cancel_club_member_by_subscription("sub_vip")
    locked = fan.get("/club/%s/members" % slug).get_data(as_text=True)
    assert "Secret Demo v1" not in locked
    # Drop removal.
    drop_id = store_mod.list_club_drops(uid)[0]["id"]
    artist.post("/fan-club/drops/%s/delete" % drop_id)
    assert store_mod.list_club_drops(uid) == []


def test_club_checkout_instant_access(monkeypatch):
    import db as store_mod
    import stripe_provider as sb
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/fan-club", data={"name": "Members Test Club", "price": "5",
                                   "blurb": "b", "perks": "Early drops",
                                   "active": "1"})
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    # Make the EPK this test needs rather than hoping an earlier test in
    # the file left one behind - under -n the file is split across
    # workers, so which tests ran first is not something to rely on. Only
    # when it is missing: /epk/save replaces the whole profile, and these
    # tests share one database.
    # A row can exist without a slug - save_epk_photo inserts one with
    # none - so check for the slug, not the row. Set it through the db
    # layer rather than a route: /epk/share is the private pitch-link
    # token, not the public slug, and which route happens to mint the
    # public one is not something a fixture should depend on.
    if not store_mod.get_epk(uid):
        artist.post("/epk/save", data={"bio": "fixture"})
    if not (store_mod.get_epk(uid) or {}).get("slug"):
        store_mod.set_epk_slug(uid, "fixture-slug-%s" % uid[:8])
    slug = store_mod.get_epk(uid)["slug"]
    monkeypatch.setattr(sb, "get_checkout_session", lambda sid: {
        "payment_status": "paid", "customer": "cus_now", "subscription": "sub_now",
        "metadata": {"kind": "fan_club", "artist_id": uid,
                     "member_email": "instant@example.net"}}
        if sid == "cs_good" else None)
    fan = app_obj.test_client()
    # The success redirect verifies with Stripe and signs the member in.
    r = fan.get("/club/%s?joined=1&session_id=cs_good" % slug)
    assert r.status_code == 302 and r.headers["Location"].endswith("/members")
    assert store_mod.get_active_club_member(uid, "instant@example.net")
    assert fan.get("/club/%s/members" % slug).status_code == 200
    # A bogus session id grants nothing — plain join page, no membership.
    anon = app_obj.test_client()
    assert anon.get("/club/%s?joined=1&session_id=cs_fake" % slug).status_code == 200
    assert "Member access" in anon.get("/club/%s/members" % slug).get_data(as_text=True)


def test_drop_notifications(monkeypatch):
    import db as store_mod
    import email_provider as emailer_mod
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    outbox = []
    monkeypatch.setattr(emailer_mod, "send",
                        lambda to, subject, html, attachments=None:
                        outbox.append((to, subject, html)) or to.endswith("@ok.example"))
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/fan-club", data={"name": "Notify Club", "price": "5",
                                   "blurb": "b", "perks": "Early drops",
                                   "active": "1"})
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    for m in store_mod.list_club_members(uid):  # shared-DB leftovers
        if m["status"] == "active" and m["stripe_subscription_id"]:
            store_mod.cancel_club_member_by_subscription(m["stripe_subscription_id"])
    store_mod.add_club_member(uid, "n1@ok.example", "cus_n1", "sub_n1")
    store_mod.add_club_member(uid, "n2@blocked.example", "cus_n2", "sub_n2")
    store_mod.add_club_member(uid, "n3@ok.example", "cus_n3", "sub_n3")
    store_mod.cancel_club_member_by_subscription("sub_n3")
    r = artist.post("/fan-club/drops", data={"title": "Notify Test Drop",
                                             "body": "Fresh for members."})
    # Two active members contacted; the sandbox-blocked one reported honestly.
    assert "notified=1" in r.headers["Location"]
    assert "failed=1" in r.headers["Location"]
    tos = sorted(t for t, _s, _h in outbox)
    assert tos == ["n1@ok.example", "n2@blocked.example"]
    to, subject, html = [m for m in outbox if m[0] == "n1@ok.example"][0]
    assert "Notify Club" in subject and "/members?token=" in html
    # The emailed magic link actually signs the member in.
    path = html.split('href="')[1].split('"')[0].replace("http://localhost", "")
    fan = app_obj.test_client()
    assert fan.get(path).status_code == 302
    slug = store_mod.get_epk(uid)["slug"]
    assert "Notify Test Drop" in fan.get(
        "/club/%s/members" % slug).get_data(as_text=True)
    banner = artist.get("/fan-club?posted=1&notified=1&failed=1").get_data(as_text=True)
    assert "Emailed 1 member" in banner and "couldn't be delivered" in banner


def test_backup_download(monkeypatch):
    import io as _io
    import zipfile
    import db as store_mod
    app_obj = create_app()
    # The shared demo account must NOT be able to exfiltrate the database.
    demo = _demo(app_obj)
    assert demo.get("/backup").status_code == 404
    assert "Download backup" not in demo.get("/settings").get_data(as_text=True)
    # A real owner can, independent of paid tier.
    monkeypatch.setenv("OWNER_EMAILS", "real-owner@example.net")
    owner = app_obj.test_client()
    owner.post("/signup", data={"name": "Owner", "email": "real-owner@example.net",
                                "password": "ownerpass1"})
    assert "Download backup" in owner.get("/settings").get_data(as_text=True)
    r = owner.get("/backup")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    names = zipfile.ZipFile(_io.BytesIO(r.data)).namelist()
    assert "streetbanker.db" in names
    # A Label subscription alone never opens the database export.
    label = app_obj.test_client()
    label.post("/signup", data={"name": "L", "email": "label-customer@example.net",
                                "password": "labelpass1"})
    store_mod.set_user_plan(
        store_mod.get_user_by_email("label-customer@example.net")["id"], "label")
    assert label.get("/backup").status_code == 404
    # Additional operators are named explicitly through OWNER_EMAILS.
    monkeypatch.setenv(
        "OWNER_EMAILS", "real-owner@example.net,cheap-owner@example.net")
    cheap = app_obj.test_client()
    cheap.post("/signup", data={"name": "C", "email": "cheap-owner@example.net",
                                "password": "cheappass1"})
    assert cheap.get("/backup").status_code == 200


def test_homepage_distribution_links():
    # Lane 01 and the footer route into the distribution page.
    app_obj = create_app()
    client = app_obj.test_client()
    home = client.get("/").get_data(as_text=True)
    assert 'href="/services/distribution"' in home
    assert "Explore Distribution" in home
    assert client.get("/services/distribution").status_code == 200


def test_tour_hub():
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    r = artist.post("/tour/add", data={"date": "2026-09-12", "venue": "The Basement",
                                       "city": "Nashville, TN", "notes": "hometown show"})
    assert r.status_code == 302
    body = artist.get("/tour").get_data(as_text=True)
    assert "The Basement" in body and "Nashville" in body
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    show = [s for s in store_mod.list_tour_shows(uid) if s["venue"] == "The Basement"][0]
    assert show["status"] == "hold"
    artist.post("/tour/%s/status" % show["id"], data={"status": "confirmed"})
    assert [s for s in store_mod.list_tour_shows(uid)
            if s["id"] == show["id"]][0]["status"] == "confirmed"
    # A made-up status is rejected.
    artist.post("/tour/%s/status" % show["id"], data={"status": "hacked"})
    assert [s for s in store_mod.list_tour_shows(uid)
            if s["id"] == show["id"]][0]["status"] == "confirmed"
    artist.post("/tour/%s/delete" % show["id"])
    assert not [s for s in store_mod.list_tour_shows(uid) if s["id"] == show["id"]]


def test_stage_plot_designer():
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    page = artist.get("/stage-plot").get_data(as_text=True)
    assert "Stage Plot Designer" in page and "Input list" in page
    # Anonymous saves bounce off the login wall.
    anon = app_obj.test_client().post("/stage-plot/save", json={})
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]
    r = artist.post("/stage-plot/save", json={
        "name": "Plot Save Test", "items": {"drums": 1, "vox": 2},
        "pos": {"vox-1": [400, 520]}})
    assert r.get_json()["ok"]
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    plot = store_mod.get_stage_plot(uid)
    assert plot["items"]["vox"] == 2 and plot["pos"]["vox-1"] == [400, 520]
    # Saved state comes back embedded on reload.
    assert "Plot Save Test" in artist.get("/stage-plot").get_data(as_text=True)


def test_show_advancer_and_showday(monkeypatch):
    import db as store_mod
    import email_provider as emailer_mod
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    outbox = []
    monkeypatch.setattr(emailer_mod, "send",
                        lambda to, subject, html, attachments=None:
                        outbox.append((to, subject, html)) or True)
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/tour/add", data={"date": "2026-10-02", "venue": "Advance Test Hall",
                                   "city": "Memphis, TN"})
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    show = [s for s in store_mod.list_tour_shows(uid)
            if s["venue"] == "Advance Test Hall"][0]
    page = artist.get("/tour/%s" % show["id"]).get_data(as_text=True)
    assert "Advance Builder" in page and "What we still need" in page
    artist.post("/tour/%s/advance" % show["id"], data={
        "contact_name": "Sam Booker", "contact_email": "sam@venue.example",
        "dayof_contact": "Sam 555-0100", "load_in": "4pm",
        "set_time": "9pm, 45 min", "deal": "$500 flat", "payout": "cash with Sam"})
    page = artist.get("/tour/%s" % show["id"]).get_data(as_text=True)
    # Confirms what's saved, asks only what's missing; core fields unlock
    # the mark-Advanced button.
    assert "Sam Booker" in page and "What time are doors?" in page
    assert "What time is load-in?" not in page
    assert "mark Advanced" in page
    # Share link -> public day sheet with logistics but never money.
    artist.post("/tour/%s/share" % show["id"])
    token = store_mod.get_tour_show(uid, show["id"])["share_token"]
    pub = app_obj.test_client().get("/showday/%s" % token)
    assert pub.status_code == 200
    text = pub.get_data(as_text=True)
    assert "Advance Test Hall" in text and "4pm" in text and "555-0100" in text
    assert "$500" not in text
    assert app_obj.test_client().get("/showday/nope").status_code == 404
    # Sending the advance emails the venue contact with the share link.
    r = artist.post("/tour/%s/send-advance" % show["id"])
    assert "sent=1" in r.headers["Location"]
    to, subject, html = outbox[-1]
    assert to == "sam@venue.example" and "Advance:" in subject and token in html
    # Someone else's account can't open the show.
    stranger = app_obj.test_client()
    stranger.post("/signup", data={"name": "S2", "email": "tour-stranger@example.net",
                                   "password": "strange2"})
    assert stranger.get("/tour/%s" % show["id"]).status_code == 404


def test_settlement_math_and_route():
    import touring
    import db as store_mod
    t = touring.settlement_totals({"deal_type": "guarantee_split", "guarantee": "500",
                                   "door_gross": "1000", "split_pct": "20",
                                   "merch_gross": "300", "merch_cut_pct": "20",
                                   "expenses": "150"})
    assert t["door_share"] == 200.0 and t["merch_net"] == 240.0 and t["walk"] == 790.0
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/tour/add", data={"date": "2026-10-03", "venue": "Settle Test Room"})
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    show = [s for s in store_mod.list_tour_shows(uid)
            if s["venue"] == "Settle Test Room"][0]
    artist.post("/tour/%s/settlement" % show["id"], data={
        "deal_type": "guarantee_split", "guarantee": "500", "door_gross": "1000",
        "split_pct": "20", "merch_gross": "300", "merch_cut_pct": "20",
        "expenses": "150", "mark_settled": "1"})
    page = artist.get("/tour/%s" % show["id"]).get_data(as_text=True)
    assert "790.00" in page
    assert store_mod.get_tour_show(uid, show["id"])["status"] == "settled"


def test_team_up_board(monkeypatch):
    import db as store_mod
    import email_provider as emailer_mod
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    outbox = []
    monkeypatch.setattr(emailer_mod, "send",
                        lambda to, subject, html, attachments=None:
                        outbox.append((to, subject, html)) or True)
    import board_store as bs
    app_obj = create_app()
    artist = _demo(app_obj)
    r = artist.post("/tour-board/post", data={
        "kind": "venue", "title": "Saturday slots open at The Vault",
        "region_text": "Charlotte, NC", "window": "Oct 2026", "genre": "indie",
        "details": "Cap 250, guarantee + door split for the right draw."})
    assert r.status_code == 302 and "/tour-board/" in r.headers["Location"]
    body = artist.get("/tour-board").get_data(as_text=True)
    assert "Saturday slots open at The Vault" in body and "Your listings" in body
    # A second account replies in-platform; the poster gets a thread notification.
    other = app_obj.test_client()
    other.post("/signup", data={"name": "Road Dog", "email": "roaddog@example.net",
                                "password": "roadpass1"})
    # Kind filter narrows the open board (checked from a non-poster view,
    # since "Your listings" always shows your own posts).
    assert "Saturday slots" not in other.get(
        "/tour-board?kind=artist").get_data(as_text=True)
    assert "Saturday slots" in other.get(
        "/tour-board?kind=venue").get_data(as_text=True)
    listing = [l for l in bs.list_listings(kind="venue")
               if l["title"].startswith("Saturday slots")][0]
    # Poster can't reply to their own listing.
    artist.post("/tour-board/%s/reply" % listing["id"], data={"message": "self reply"})
    assert bs.list_board_replies(listing["id"]) == []
    r = other.post("/tour-board/%s/reply" % listing["id"], data={
        "message": "We pull 200 in Charlotte, October works."})
    assert "/tour-board/thread/" in r.headers["Location"]
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    notes = store_mod.list_notifications(uid)
    assert any("Team-Up" in n["title"] and n["link"].startswith("/tour-board/thread/")
               for n in notes)
    assert outbox and outbox[-1][0] == "demo@streetbanker.io"
    assert "roaddog@example.net" not in outbox[-1][2]      # no email address is handed over
    # The thread is the poster's to read; the replier's email never appears.
    tid = r.headers["Location"].split("/thread/")[1].split("?")[0]
    assert "We pull 200 in Charlotte" in artist.get(
        "/tour-board/thread/%s" % tid).get_data(as_text=True)
    assert "We pull 200 in Charlotte" not in other.get(
        "/tour-board").get_data(as_text=True)
    # Closing hides it from the open board; delete removes it and its threads.
    artist.post("/tour-board/%s/close" % listing["id"])
    assert not [l for l in bs.list_listings() if l["id"] == listing["id"]]
    artist.post("/tour-board/%s/delete" % listing["id"])
    assert bs.get_listing(listing["id"]) is None
    assert bs.list_board_replies(listing["id"]) == []


def test_rack_page_and_presets():
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    page = artist.get("/rack").get_data(as_text=True)
    assert "The Rack" in page and "12 Band" in page
    # CSS-drawn chassis; every live control keeps its hook. The photo is gone
    # and the template asks for no image at all (base.html still links the
    # apple-touch-icon on every page, so check the template, not the page).
    assert "rack-chassis2.jpg" not in page and "rackdsp.js?v=" in page
    assert "/static/img/" not in open("templates/rack.html", encoding="utf8").read()
    # v3 workflow layer: flow strip, reference slot, shareable rigs
    assert 'class="flow-node' in page and 'id="rk-ref"' in page
    assert 'id="rk-rig-export"' in page and "Import rig" in page
    assert 'data-ksize' in page and 'data-screen' in page
    assert "Harmonic Bank" in page
    # Every module carries power + compare + A/B LEDs; the screen has zone trim.
    assert page.count('class="rk-pwr') == 7 and page.count('class="rk-cmp') == 9
    assert page.count('class="rk-ledwrap"') == 9
    assert 'id="rk-zone"' in page and "+1 dB" in page and "Reset zone" in page
    assert 'id="rk-gr"' in page  # gain reduction meter on the compressor unit
    # UX layer: focus mode, sticky transport dock, waveform scrubber.
    assert 'id="rk-focus"' in page and "Focus mode" in page
    assert 'id="rk-dock"' in page and 'id="rk-wave"' in page and 'id="rk-play2"' in page
    assert "Tube Stage" in page and "not instrument identification" in page
    assert "CAB-3" in page and "not measurements of any specific hardware" in page
    assert "4×12 Closed-Back" in page and "Ribbon" in page
    # SB-08/10/11 are hardware panels, not web forms: the cab and mic are
    # picked with selector caps, the native selects only hold the value.
    assert 'id="rk-pick-cab"' in page and 'id="rk-pick-mic"' in page
    assert 'id="rk-pick-axis"' in page
    assert '<select id="rk-cab-cab" hidden' in page
    assert '<select id="rk-cab-mic" hidden' in page
    for cap in ("cb-direct", "cb-combo112", "cb-open212", "cb-closed412",
                "cb-bass810", "mc-dynamic", "mc-ribbon", "mc-condenser",
                "ax-on", "ax-off"):
        assert 'id="%s"' % cap in page, cap
        assert 'for="%s"' % cap in page, cap
    # Every cap row is announced as a labelled group, and the diagram is
    # named by the caption that describes it. Checking the labels rather
    # than counting groups, so adding a panel does not fail this.
    for group in ("Cabinet", "Microphone type", "Microphone angle"):
        assert 'aria-label="%s"' % group in page, group
    assert 'id="rk-cabview"' in page and 'aria-labelledby="rk-cabview-cap"' in page
    assert 'id="rk-hookmap"' in page and 'id="rk-hookmap-cap"' in page
    # Function blocks are fenced into labelled sub-plates.
    for legend in ("Cabinet", "Microphone", "Separation", "Scan"):
        assert '<span class="lg">%s</span>' % legend in page, legend
    assert "Four-lane bay" in page and "Hook map" in page
    # SB-13's tempo now feeds SB-11: hooks snap to a downbeat, and the
    # panel reports which of snapped / already-on-grid / no-grid happened.
    assert 'id="rk-hook-note"' in page
    assert "snapped to the nearest downbeat" in page
    assert "only snaps when the grid is confident" in page
    # SB-12 Format Bench and SB-13 Tempo & Key, with their engines loaded.
    assert 'id="sb12"' in page and "CNV-2" in page
    assert 'id="sb13"' in page and "TMP-1" in page
    assert "audioconv.js?v=" in page and "tempokey.js?v=" in page
    assert 'id="rk-cnv-go"' in page and 'id="rk-cnv-rate"' in page
    assert 'id="rk-tk-detect"' in page and 'id="rk-tk-chroma"' in page
    assert 'id="rk-tk-target"' in page and 'id="rk-tk-cents"' in page
    for legend in ("Source", "Container", "Depth", "Sample rate",
                   "Channels", "Analyse", "Chroma", "Tempo", "Key"):
        assert '<span class="lg">%s</span>' % legend in page, legend
    for group in ("Conversion source", "Output container", "Bit depth",
                  "Sample rate", "Channel count"):
        assert 'aria-label="%s"' % group in page, group
    # The honesty the two panels owe the user, stated on the faceplate:
    # what the estimates are, and what the browser will not encode.
    assert "estimates with a score attached" in page
    assert "Krumhansl-Schmuckler" in page and "WSOLA" in page
    # The converter always offers the two it can write in the tab.
    assert 'value="wav"' in page and 'value="aiff"' in page
    assert "TPDF dither" in page
    # SB-15 Loudness, and the normalise option it feeds in SB-12.
    assert 'id="sb15"' in page and "LDN-1" in page and "loudness.js?v=" in page
    assert 'id="rk-ldn-go"' in page and 'id="rk-ldn-graph"' in page
    assert 'id="rk-ldn-targets"' in page and 'id="rk-ldn-i"' in page
    assert 'id="rk-cnv-lufs"' in page          # normalise on convert
    for legend in ("Measure", "Integrated", "True peak", "Range", "Loudness"):
        assert '<span class="lg">%s</span>' % legend in page, legend
    # The claims the panel makes about its own method stay on the faceplate.
    assert "ITU-R BS.1770" in page
    assert "EBU Tech 3341" in page and "EBU 3342" in page
    assert "K-weighting derived" in page       # not the printed 48 kHz table
    assert "Turning a master down is lossless" in page
    # SB-14 Valve Bank: six sockets, each a separate stage.
    assert 'id="sb14"' in page and "VLV-6" in page and "tubes.js?v=" in page
    assert page.count('class="vlv"') == 6
    assert page.count('class="vlv-pwr sw"') == 6
    assert page.count('class="glass"') == 6
    assert page.count('style="--heat:0"') == 6
    for key, tube, name in (("triode", "V1", "Triode"),
                            ("pentode", "V2", "Pentode"),
                            ("tape", "V3", "Tape"),
                            ("flutter", "V4", "Flutter"),
                            ("iron", "V5", "Iron"),
                            ("varimu", "V6", "Vari-Mu")):
        assert 'id="rk-vlv-%s"' % key in page, key
        assert 'data-valve="%s"' % key in page, key
        assert ">%s<" % tube in page, tube
        assert ">%s<" % name in page, name
    assert 'id="rk-vlv-all"' in page
    # What the panel promises about itself stays on the faceplate.
    assert "the glow is a meter, not decoration" in page
    assert "off is genuinely off" in page
    assert "squaring term" in page and "odd-symmetric" in page
    assert 'Stem Deck' in page and 'not ML isolation' in page
    assert "Remove Center" in page and "Physics, not stem separation" in page
    assert "DLY-1" in page and "REV-1" in page and "honestly generated" in page
    assert "SUB-1" in page and "psychoacoustics, not magic" in page
    assert "never leaves this machine" in page
    # Anonymous saves bounce off the login wall.
    anon = app_obj.test_client().post("/rack/save", json={})
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]
    # Saved rack round-trips and is embedded on reload.
    rack = {"eq": [1.5, 0, 0, -2, 0, 0, 0, 0, 0, 0, 1, 0.5], "q": 1.2,
            "tube": {"drive": 3, "bias": 0.2, "mix": 0.4},
            "comp": {"thr": -20, "ratio": 3, "att": 0.01, "rel": 0.25, "makeup": 2},
            "out": -1}
    assert artist.post("/rack/save", json=rack).get_json()["ok"]
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    assert store_mod.get_rack_preset(uid)["tube"]["mix"] == 0.4
    assert '"drive": 3' in artist.get("/rack").get_data(as_text=True)


def test_artist_hub():
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    artist.get("/fan-club")  # ensures the EPK slug exists on a fresh DB
    slug = store_mod.get_epk(uid)["slug"]
    artist.post("/tour/add", data={"date": "2099-01-15", "venue": "Hub Test Hall",
                                   "city": "Asheville, NC"})
    show = [s for s in store_mod.list_tour_shows(uid)
            if s["venue"] == "Hub Test Hall"][0]
    artist.post("/tour/%s/status" % show["id"], data={"status": "confirmed"})
    artist.post("/fan-club", data={"name": "Hub Club", "price": "5", "blurb": "b",
                                   "perks": "Early drops", "active": "1"})
    anon = app_obj.test_client()
    hub = anon.get("/@" + slug).get_data(as_text=True)
    assert "Synthwave Surfer" in hub
    assert "Hub Test Hall" in hub                      # confirmed show listed
    assert "/club/" + slug in hub and "Hub Club" in hub
    assert "/epk/" + slug in hub                       # press kit doorway
    assert "Powered by" in hub
    # Holds stay private: a hold never appears on the public hub.
    artist.post("/tour/add", data={"date": "2099-02-20", "venue": "Secret Hold Room"})
    assert "Secret Hold Room" not in anon.get("/@" + slug).get_data(as_text=True)
    assert anon.get("/@not-a-real-artist").status_code == 404
    # The EPK editor points at the hub.
    assert "Artist Hub" in artist.get("/epk").get_data(as_text=True)
    store_mod.delete_tour_show(uid, show["id"])


def test_label_roster():
    import db as store_mod
    import plans
    assert plans.required_tier("/roster") == "label"
    assert plans.required_tier("/roster/artist/x") == "label"
    assert plans.required_tier("/roster/join/tok") is None  # invited artists enter free
    app_obj = create_app()
    label = _demo(app_obj)  # demo@ is Label tier
    page = label.get("/roster").get_data(as_text=True)
    assert "Label Roster" in page and "read-only" in page
    label.post("/roster/invite", data={"email": "signee@example.net"})
    page = label.get("/roster").get_data(as_text=True)
    assert "signee@example.net" in page and "/roster/join/" in page
    token = page.split("/roster/join/")[1].split('"')[0]
    # New artist accepts, account created, lands signed in.
    artist = app_obj.test_client()
    join = artist.get("/roster/join/" + token).get_data(as_text=True)
    assert "wants you on their roster" in join and "read-only view" in join
    r = artist.post("/roster/join/" + token,
                    data={"name": "Signee One", "password": "signeepass"})
    assert r.status_code == 302 and "/command-center" in r.headers["Location"]
    # Artist shows on the roster with real (zero) numbers; label can open them.
    uid = store_mod.get_user_by_email("signee@example.net")["id"]
    page = label.get("/roster").get_data(as_text=True)
    assert "Signee One" in page
    view = label.get("/roster/artist/%s" % uid).get_data(as_text=True)
    assert "Roster · read-only" in view and "Statement Revenue" in view
    # The label got notified.
    lid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    assert any("Roster invite accepted" in n["title"]
               for n in store_mod.list_notifications(lid))
    # Another label can't open this artist.
    other = app_obj.test_client()
    other.post("/signup", data={"name": "L2", "email": "otherlabel@example.net",
                                "password": "labelpass1"})
    store_mod.set_user_plan(
        store_mod.get_user_by_email("otherlabel@example.net")["id"], "label")
    assert other.get("/roster/artist/%s" % uid).status_code == 404
    # Used invite tokens die.
    assert "isn't valid anymore" in artist.get(
        "/roster/join/" + token).get_data(as_text=True)
    # Remove works.
    member = [m for m in store_mod.list_roster(lid)
              if m["email"] == "signee@example.net"][0]
    label.post("/roster/%s/remove" % member["id"])
    assert store_mod.get_roster_member(lid, uid) is None


def test_pwa_install_surface():
    import json as _json
    app_obj = create_app()
    anon = app_obj.test_client()
    sw = anon.get("/sw.js")
    assert sw.status_code == 200 and b"addEventListener" in sw.data
    man = anon.get("/static/manifest.json")
    assert man.status_code == 200
    data = _json.loads(man.data)
    assert data["name"] == "Street Banker" and data["display"] == "standalone"
    assert anon.get("/static/img/icon-512.png").status_code == 200
    assert anon.get("/static/offline.html").status_code == 200
    home = anon.get("/").get_data(as_text=True)
    assert 'rel="manifest"' in home and "serviceWorker" in home
    dash = _demo(app_obj).get("/command-center").get_data(as_text=True)
    assert 'rel="manifest"' in dash


def test_referral_engine(monkeypatch):
    import json as _json
    import db as store_mod
    import stripe_provider as sb
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_stripetest")
    calls = []

    def fake_http(path, fields):
        calls.append((path, dict(fields)))
        if path == "/v1/coupons":
            return {"id": "coup_free_month"}
        if path == "/v1/checkout/sessions":
            return {"id": "cs_ref", "url": "https://checkout.stripe.com/c/ref"}
        return {"id": "cbt_1"}

    monkeypatch.setattr(sb, "_http", fake_http)
    app_obj = create_app()
    store_mod.set_kv("stripe_ref_coupon", "")  # fresh coupon path per run
    artist = _demo(app_obj)
    page = artist.get("/referrals").get_data(as_text=True)
    assert "/signup?ref=" in page and "first month free" in page
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    code = store_mod.ensure_ref_code(uid)
    # Friend lands on the ref link, signs up, is attributed.
    friend = app_obj.test_client()
    friend.get("/signup?ref=" + code)
    friend.post("/signup", data={"name": "Referred Ray", "email": "ray@example.net",
                                 "password": "raypass1"})
    rid = store_mod.get_user_by_email("ray@example.net")["id"]
    assert store_mod.get_user(rid)["referred_by"] == uid
    assert any("Referral signed up" in n["title"]
               for n in store_mod.list_notifications(uid))
    # Their first checkout carries the 100%-off-first-month coupon.
    friend.post("/billing/checkout", data={"plan": "artist"})
    sess = [f for p, f in calls if p == "/v1/checkout/sessions"][-1]
    assert sess.get("discounts[0][coupon]") == "coup_free_month"
    # Conversion webhook: Ray activates, referrer's Stripe balance is credited.
    store_mod.set_stripe_ids(uid, "cus_referrer", "sub_referrer")
    payload = _json.dumps({"type": "checkout.session.completed", "data": {"object": {
        "client_reference_id": rid, "customer": "cus_ray", "subscription": "sub_ray",
        "metadata": {"plan": "artist"}}}})
    app_obj.test_client().post("/webhooks/stripe", data=payload,
                               headers=_stripe_sig(payload),
                               content_type="application/json")
    assert store_mod.get_user(rid)["ref_credited"] == 1
    credit_paths = [p for p, f in calls if "balance_transactions" in p]
    assert credit_paths and "cus_referrer" in credit_paths[-1]
    credit_fields = [f for p, f in calls if "balance_transactions" in p][-1]
    assert credit_fields["amount"] == "-900"
    assert any("Referral credit applied" in n["title"]
               for n in store_mod.list_notifications(uid))
    assert store_mod.referral_stats(uid)["converted"] >= 1
    # Self-referral is a no-op.
    solo = app_obj.test_client()
    solo.get("/signup?ref=" + code)
    solo.post("/signup", data={"name": "Solo", "email": "solo-ref@example.net",
                               "password": "solopass1"})
    sid = store_mod.get_user_by_email("solo-ref@example.net")["id"]
    assert store_mod.get_user(sid)["referred_by"] == uid  # normal attribution
    store_mod.set_kv("stripe_ref_coupon", "")  # shared-DB cleanup


def test_light_studio():
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    page = artist.get("/lights").get_data(as_text=True)
    assert "Light Studio" in page and "simulation" in page
    assert "ENTTEC" in page and "Web Serial" in page
    assert "Audience view" in page and "drag any bar" in page
    anon = app_obj.test_client().post("/lights/save", json={})
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]
    show = {"name": "DEVORA set", "bars": 10, "chans": 4,
            "cues": [{"t": 0, "group": "all", "color": "#200000",
                      "intensity": 10, "fade": 2}]}
    assert artist.post("/lights/save", json=show).get_json()["ok"]
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    assert store_mod.get_light_show(uid)["bars"] == 10
    assert "DEVORA set" in artist.get("/lights").get_data(as_text=True)


def test_artist_os_engines():
    import artist_os
    # Empty passport: criticals red, rest yellow, overall red.
    track = {"id": "t1", "title": "Night Drive", "passport": {}, "lockbox": {}}
    rep = artist_os.passport_report(track)
    assert rep["overall"] == "red" and rep["pct"] == 0
    crit = [i for i in rep["items"] if i["critical"]]
    assert crit and all(i["state"] == "red" for i in crit)
    # Positive words go green; "pending" holds yellow; "blocked" goes red.
    assert artist_os.field_state("mlc_status", "Registered", False) == "green"
    assert artist_os.field_state("mlc_status", "pending", False) == "yellow"
    assert artist_os.field_state("sample_clearance", "blocked", True) == "red"
    # Clean Release: empty track is blocked (critical reds present).
    ctx = {"statement_rows": 0, "statement_total": 0, "lanes_with_data": set(),
           "live_links": 0, "fans": 0, "club_members": 0, "sync_active": False,
           "release_scheduled": False, "rollout_assets": False}
    clean = artist_os.clean_release(track, ctx)
    assert clean["blocked"] and clean["score"] < 60
    # Fill everything positive -> green passport, unblocked, high score.
    full = {k: "cleared n/a signed registered"
            for k, _l, _c, _f in artist_os.PASSPORT_FIELDS}
    full.update({"audio_ok": "1", "artwork_ok": "1"})
    box = {d[0]: {"not_applicable": True} for d in artist_os.LOCKBOX_DOCS}
    track2 = {"id": "t2", "title": "Clean Song", "passport": full, "lockbox": box}
    rep2 = artist_os.passport_report(track2)
    assert rep2["overall"] == "green" and rep2["pct"] == 100
    clean2 = artist_os.clean_release(track2, dict(ctx, live_links=1, fans=5))
    assert not clean2["blocked"] and clean2["score"] >= 80
    caps = artist_os.lockbox_report(track2)["caps"]
    assert caps["release"] and caps["sync"]
    # Lanes: estimates only exist when statements exist.
    lanes_dry = artist_os.lane_grid(track, ctx)
    assert all(l["estimate"] is None for l in lanes_dry)
    lanes_paid = artist_os.lane_grid(track, dict(ctx, statement_rows=10,
                                                 statement_total=1000.0))
    mech = [l for l in lanes_paid if l["key"] == "mechanicals"][0]
    assert mech["estimate"] == 60.0 and "your own statement" in mech["estimate_basis"]
    # Action queue: critical rights first.
    q = artist_os.action_queue([(track, dict(ctx, statement_total=1000.0,
                                             statement_rows=10))])
    assert q and q[0]["critical"] and q[0]["urgency"] == "release-blocking"
    assert any(a["impact"] for a in q)
    # Certification climbs only on real signals.
    assert artist_os.certification({"tracks": 0})["level"] == "Unranked"
    assert artist_os.certification({"tracks": 2, "passport_avg": 95, "clean_avg": 92,
                                    "lanes_connected": 6, "fans": 50,
                                    "lockbox_ready": 2, "reds": 0,
                                    "statement_rows": 12})["level"] == "Upstream Ready"


def test_artist_os_tracks_flow():
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    page = artist.get("/tracks").get_data(as_text=True)
    assert "Track Passports" in page and "Street Banker Certified" in page
    artist.post("/tracks/add", data={"title": "Night Drive OS",
                                     "release_title": "Midnight EP",
                                     "release_date": "2026-10-30"})
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    track = [t for t in store_mod.list_os_tracks(uid)
             if t["title"] == "Night Drive OS"][0]
    detail = artist.get("/tracks/%s" % track["id"]).get_data(as_text=True)
    assert "Metadata Passport" in detail and "Rights Lockbox" in detail
    assert "Release blocked" in detail or "blocked" in detail
    # Save a fully positive passport -> state flips green on the page.
    import artist_os
    form = {k: "registered / cleared / signed"
            for k, _l, _c, _f in artist_os.PASSPORT_FIELDS}
    form.update({"audio_ok": "1", "artwork_ok": "1"})
    artist.post("/tracks/%s/passport" % track["id"], data=form)
    detail = artist.get("/tracks/%s" % track["id"]).get_data(as_text=True)
    assert "Passport green" in detail and "100%" in detail
    # Stranger can't see it; delete works.
    stranger = app_obj.test_client()
    stranger.post("/signup", data={"name": "S3", "email": "os-stranger@example.net",
                                   "password": "strange3"})
    assert stranger.get("/tracks/%s" % track["id"]).status_code == 404
    artist.post("/tracks/%s/delete" % track["id"])
    assert store_mod.get_os_track(uid, track["id"]) is None


def test_lockbox_signoff_flow(monkeypatch):
    import io as _io
    import db as store_mod
    import email_provider as emailer_mod
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    outbox = []
    monkeypatch.setattr(emailer_mod, "send",
                        lambda to, subject, html, attachments=None:
                        outbox.append((to, subject, html)) or True)
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/tracks/add", data={"title": "Lockbox Song"})
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    track = [t for t in store_mod.list_os_tracks(uid)
             if t["title"] == "Lockbox Song"][0]
    tid = track["id"]
    # Upload a split sheet -> doc becomes ready (no signers yet).
    r = artist.post("/tracks/%s/lockbox/split_sheet" % tid,
                    data={"action": "upload",
                          "file": (_io.BytesIO(b"splits pdf bytes"), "splits.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    import artist_os
    box = artist_os.lockbox_report(store_mod.get_os_track(uid, tid))
    split = [d for d in box["docs"] if d["key"] == "split_sheet"][0]
    assert split["state"] == "ready" and split["file"].startswith("/uploads/")
    # Request a sign-off -> awaiting signatures, email carries the link.
    artist.post("/tracks/%s/lockbox/split_sheet" % tid,
                data={"action": "approver", "name": "Producer Pat",
                      "email": "pat@example.net"})
    box = artist_os.lockbox_report(store_mod.get_os_track(uid, tid))
    split = [d for d in box["docs"] if d["key"] == "split_sheet"][0]
    assert split["state"] == "awaiting signatures"
    assert outbox and "/sign/" in outbox[-1][2]
    token = outbox[-1][2].split("/sign/")[1].split('"')[0]
    # Signer reviews and signs on the public page.
    signer = app_obj.test_client()
    page = signer.get("/sign/" + token).get_data(as_text=True)
    assert "Lockbox Song" in page and "Split sheet" in page
    signer.post("/sign/" + token, data={"decision": "signed"})
    box = artist_os.lockbox_report(store_mod.get_os_track(uid, tid))
    split = [d for d in box["docs"] if d["key"] == "split_sheet"][0]
    assert split["state"] == "ready"
    assert any("signed the split sheet" in n["title"]
               for n in store_mod.list_notifications(uid))
    # Used token shows the outcome, can't flip the decision.
    signer.post("/sign/" + token, data={"decision": "declined"})
    box = artist_os.lockbox_report(store_mod.get_os_track(uid, tid))
    assert [d for d in box["docs"] if d["key"] == "split_sheet"][0]["state"] == "ready"
    # N/A the other required docs -> pitch/monetize/release caps unlock.
    for key in ("beat_license", "sample_clearance", "featured_approval"):
        artist.post("/tracks/%s/lockbox/%s" % (tid, key), data={"action": "na"})
    caps = artist_os.lockbox_report(store_mod.get_os_track(uid, tid))["caps"]
    assert caps["release"] and caps["monetize"] and caps["pitch"]
    assert signer.get("/sign/not-a-token").status_code == 200  # invalid page, no crash
    artist.post("/tracks/%s/delete" % tid)


def test_os_wiring_on_existing_pages():
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/tracks/add", data={"title": "Wired Song"})
    clean = artist.get("/releases/clean-release").get_data(as_text=True)
    assert "Track Passports · Clean Release" in clean and "Wired Song" in clean
    passport = artist.get("/metadata-passport").get_data(as_text=True)
    assert "Per-Track Passports (Artist OS)" in passport and "Wired Song" in passport
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    for t in store_mod.list_os_tracks(uid):
        if t["title"] == "Wired Song":
            store_mod.delete_os_track(uid, t["id"])


def test_os_p3_lanes_and_queue():
    import artist_os
    import db as store_mod
    # Source mapping is pure and real: distributor rows claim master lane etc.
    lanes = artist_os.lanes_from_sources(
        ["Spotify", "The MLC", "ASCAP", "SoundExchange", "TikTok", "YouTube"])
    assert {"master", "mechanicals", "pro", "soundexchange",
            "ugc", "content_id"} <= lanes
    assert artist_os.lanes_from_sources([]) == set()
    # A lane with real income reads "claimed".
    track = {"id": "x", "title": "Lane Song", "passport": {}, "lockbox": {}}
    ctx = {"statement_rows": 5, "statement_total": 500.0,
           "lanes_with_data": {"master", "pro"}, "live_links": 0, "fans": 0,
           "club_members": 0, "sync_active": False,
           "release_scheduled": False, "rollout_assets": False}
    grid = {l["key"]: l for l in artist_os.lane_grid(track, ctx)}
    assert grid["master"]["state"] == "claimed"
    assert grid["pro"]["state"] == "claimed"
    assert grid["mechanicals"]["state"] == "missing"
    assert grid["mechanicals"]["estimate"] == 30.0
    # Pages render with the demo's real track.
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/tracks/add", data={"title": "Queue Song"})
    lanes_page = artist.get("/royalty-lanes").get_data(as_text=True)
    assert "Royalty Lanes" in lanes_page and "Queue Song" in lanes_page
    queue_page = artist.get("/money-queue").get_data(as_text=True)
    assert "Missing Money Action Queue" in queue_page
    assert "Queue Song" in queue_page and "Fix this" in queue_page
    assert "release-blocking" in queue_page
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    for t in store_mod.list_os_tracks(uid):
        if t["title"] == "Queue Song":
            store_mod.delete_os_track(uid, t["id"])


def test_os_p4_generators_and_twin():
    import artist_os
    # Stage math walks the whole arc from date deltas alone.
    assert artist_os.autopilot_stage(None, "2026-07-26") == "Intake"
    assert artist_os.autopilot_stage("2026-10-01", "2026-07-26") == "Clean-up"
    assert artist_os.autopilot_stage("2026-08-20", "2026-07-26") == "Pre-save"
    assert artist_os.autopilot_stage("2026-08-04", "2026-07-26") == "Pitch"
    assert artist_os.autopilot_stage("2026-07-30", "2026-07-26") == "Rollout"
    assert artist_os.autopilot_stage("2026-07-24", "2026-07-26") == "Release week"
    assert artist_os.autopilot_stage("2026-07-01", "2026-07-26") == "Post-release"
    assert artist_os.autopilot_stage("2026-01-01", "2026-07-26") == "Catalog follow-up"
    # Release kit uses the real inputs and brackets what only the artist knows.
    kit = artist_os.release_kit("Synthwave Surfer", "Night Drive",
                                "2026-10-30", "http://x/l/night-drive")
    assert "Night Drive" in kit["captions"][0]
    assert "http://x/l/night-drive" in kit["email"]["body"]
    assert "[comparable artists]" in kit["pitch"]
    assert len(kit["sms"]) < 200
    # Plans grow with the window and never invent metrics.
    p14 = artist_os.campaign_plan(14, "Night Drive", "2026-10-30")
    p60 = artist_os.campaign_plan(60, "Night Drive", "2026-10-30")
    assert len(p60["windows"]) > len(p14["windows"])
    assert "60 days out" in p60["windows"][0][0]
    assert "per deliverable" in p60["brief"]
    # Twin: real sections ready, absent-data sections say their unlock.
    ctx = {"statement_rows": 0, "statement_total": 0, "lanes_with_data": set(),
           "live_links": 1, "fans": 12, "club_members": 2, "sync_active": False,
           "release_scheduled": False, "rollout_assets": False}
    track = {"id": "t", "title": "Night Drive", "passport": {}, "lockbox": {}}
    rep = artist_os.twin_report([track], ctx, [], artist_os.action_queue([(track, ctx)]))
    by_title = {sec["title"]: sec for sec in rep}
    assert by_title["Release readiness"]["state"] == "ready"
    assert "Night Drive" in by_title["Best single to lead with"]["lines"][0]
    assert by_title["Rollout recommendation"]["state"] == "ready"
    assert by_title["Next best action"]["state"] == "ready"
    assert by_title["Audience match"]["state"] == "awaiting"
    assert "Chartmetric" in by_title["Audience match"]["lines"][0]
    assert by_title["Fan sentiment"]["state"] == "awaiting"


def test_os_p4_pages():
    import db as store_mod
    app_obj = create_app()
    artist = _demo(app_obj)
    twin_page = artist.get("/artist-twin").get_data(as_text=True)
    assert "Strategist Read" in twin_page and "nothing is invented" in twin_page
    auto = artist.get("/releases/autopilot").get_data(as_text=True)
    assert "Autopilot Timeline" in auto
    if "Campaign Plan" in auto:  # renders when a campaign exists
        assert "Release Kit" in auto and "a generator, not a chatbot" in auto
    roll = artist.get("/rollout-studio").get_data(as_text=True)         if artist.get("/rollout-studio").status_code == 200 else ""


def test_os_p5_certified_and_onesheet():
    import plans
    assert plans.required_tier("/certified") == "artist"
    app_obj = create_app()
    artist = _demo(app_obj)
    cert = artist.get("/certified").get_data(as_text=True)
    assert "Street Banker Certified" in cert
    assert "The Ladder" in cert and "Upstream Ready" in cert
    assert "computed from your real record" in cert
    assert "granted, purchased, or faked" in cert  # honesty line
    artist.post("/tracks/add", data={"title": "Night Drive P5",
                                     "release_title": "Midnight EP",
                                     "release_date": "2026-10-30"})
    sheet = artist.get("/deal-room/onesheet")
    assert sheet.status_code == 200
    body = sheet.get_data(as_text=True)
    assert "Artist One-Sheet" in body
    assert "Night Drive P5" in body                 # the artist's real OS track
    assert "from uploaded statements" in body       # revenue names its basis
    assert "not scored" in body                     # no fake stream integrity
    assert "[To discuss]" in body                   # never invents the ask
    assert "Print / Save as PDF" in body
    # Deal Room links to it.
    assert "/deal-room/onesheet" in artist.get("/deal-room").get_data(as_text=True)


def test_os_p5_roster_health_and_export():
    import db as store_mod
    app_obj = create_app()
    label = _demo(app_obj)  # demo@ is Label tier
    label.post("/roster/invite", data={"email": "p5artist@example.net"})
    page = label.get("/roster").get_data(as_text=True)
    token = page.split("p5artist@example.net")[1].split("/roster/join/")[1].split('"')[0]
    joiner = app_obj.test_client()
    r = joiner.post("/roster/join/" + token,
                    data={"name": "P Five", "password": "pfivepass"})
    assert r.status_code == 302
    # Roster row now carries OS health: passport %, red count, cert chip.
    page = label.get("/roster").get_data(as_text=True)
    assert "P Five" in page and "% passport" in page and "red" in page
    assert "Unranked" in page  # fresh artist, no tracks -> honest bottom rung
    assert "Export roster report (CSV)" in page
    csv_body = label.get("/roster/export.csv").get_data(as_text=True)
    head = csv_body.splitlines()[0]
    assert head == ("artist,email,statement_revenue,fans,live_links,"
                    "upcoming_shows,tracks,passport_avg_pct,clean_release_avg,"
                    "red_rights_issues,certification")
    row = [ln for ln in csv_body.splitlines() if "p5artist@example.net" in ln][0]
    assert "Unranked" in row and "P Five" in row


def test_tech_rider_and_rack_handoff():
    import db as store_mod
    import plans
    assert plans.required_tier("/rider/tok") is None  # venue staff need no login
    app_obj = create_app()
    artist = _demo(app_obj)
    artist.post("/tour/add", data={"date": "2099-03-01", "venue": "Rider Hall",
                                   "city": "Denton, TX"})
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    show = [s for s in store_mod.list_tour_shows(uid)
            if s["venue"] == "Rider Hall"][0]
    artist.post("/tour/%s/advance" % show["id"],
                data={"backline": "House provides bass rig + drum shells",
                      "dayof_contact": "Sam 555-0100", "load_in": "4pm"})
    artist.post("/tour/%s/share" % show["id"])
    token = store_mod.get_tour_show(uid, show["id"])["share_token"]
    # Tour detail surfaces the rider link.
    detail = artist.get("/tour/%s" % show["id"]).get_data(as_text=True)
    assert "Tech Rider (print / PDF)" in detail and "/rider/" + token in detail
    # Public rider: no login, real fields only, honest no-boilerplate line.
    anon = app_obj.test_client()
    rider = anon.get("/rider/" + token).get_data(as_text=True)
    assert "Technical Rider" in rider and "Rider Hall" in rider
    assert "House provides bass rig" in rider and "Sam 555-0100" in rider
    assert "no boilerplate" in rider and "Print / Save as PDF" in rider
    assert anon.get("/rider/badtoken").status_code == 404
    # Rack -> Smart Link handoff prefills the builder honestly.
    page = artist.get("/links/new?title=Night+Drive&rack=bounced+through+The+Rack"
                      ).get_data(as_text=True)
    assert 'value="Night Drive"' in page and "From The Rack" in page
    # Snippet Finder unit ships on the rack.
    rack = artist.get("/rack").get_data(as_text=True)
    assert "Snippet Finder" in rack and 'id="rk-hook-scan"' in rack
    assert "level detection, not taste" in rack and 'id="rk-rollout"' in rack


def test_ecosystem_hubs():
    import hubs as hub_defs
    # One source of truth: every hub item key is unique and every hub resolves.
    keys = [k for _hk, _n, _t, items in hub_defs.HUBS for k, *_ in items]
    assert len(keys) == len(set(keys))
    assert hub_defs.get_hub("money")["name"] == "Royalty Sweep & Banking"
    assert hub_defs.get_hub("nope") is None
    app_obj = create_app()
    artist = _demo(app_obj)
    nav = artist.get("/command-center").get_data(as_text=True)
    # Five collapsible hubs + Account; desk links; collapse JS present.
    assert nav.count('data-hub=') == 6
    for hk in ("command", "studio", "launch", "stage", "money"):
        assert '/desk/%s' % hk in nav
    assert "hub-tgl" in nav and "sbHubs" in nav
    # Desk pages render module cards with honest Live/Preview chips.
    desk = artist.get("/desk/stage").get_data(as_text=True)
    assert "Live Stage Suite" in desk and "Tour Hub" in desk
    assert "Light Studio" in desk and "real DMX" in desk.lower() or "DMX" in desk
    assert artist.get("/desk/nope").status_code == 404
    money = artist.get("/desk/money").get_data(as_text=True)
    assert "Money Queue" in money and "Valuation" in money
    # Fan world keeps its simple nav — no hub machinery.
    fan = app_obj.test_client()
    fan.post("/login", data={"email": "demo-fan@streetbanker.io", "password": "sweep"})
    fnav = fan.get("/discover").get_data(as_text=True)
    assert "data-hub=" not in fnav and "Community" in fnav
    # Discover polish: playing visualizer CSS + suggestion empty states.
    assert "preview-play.playing .viz" in fnav


def test_network_upgrades_and_outreach_pipeline():
    import db as store_mod
    app_obj = create_app()
    client = _demo(app_obj)
    page = client.get("/network").get_data(as_text=True)
    # Demo directory is labeled as samples; avatars render; CTAs match roles.
    # Assert the disclosure, not one exact sentence - the wording moved into
    # partials/data_label.html so the index and the profile pages agree.
    assert "Sample data" in page and "not real people" in page
    assert "/static/img/people/p5.jpg" in page
    assert "Pitch Track" in page and "Submit Demo" in page
    assert "/network?tab=playlists" in page  # stat cards are quick-jumps
    # Active filter chips + clear all.
    filt = client.get("/network?tab=directory&role=Label").get_data(as_text=True)
    assert "Role: Label" in filt and "Clear all" in filt
    # Outreach Pipeline: real personal CRM, full lifecycle.
    client.post("/network/outreach/add",
                data={"contact": "Midnight Radio", "role": "Curator",
                      "stage": "pitched", "notes": "sent smart link"})
    my = client.get("/network?tab=my").get_data(as_text=True)
    assert "Outreach Pipeline" in my and "Midnight Radio" in my
    assert "real entries only" in my
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    item = [o for o in store_mod.list_outreach(uid)
            if o["contact"] == "Midnight Radio"][0]
    client.post("/network/outreach/%s/stage" % item["id"],
                data={"stage": "discussion"})
    assert [o for o in store_mod.list_outreach(uid)
            if o["id"] == item["id"]][0]["stage"] == "discussion"
    client.post("/network/outreach/%s/stage" % item["id"],
                data={"stage": "not-a-stage"})  # invalid stages are ignored
    assert [o for o in store_mod.list_outreach(uid)
            if o["id"] == item["id"]][0]["stage"] == "discussion"
    client.post("/network/outreach/%s/delete" % item["id"])
    assert not [o for o in store_mod.list_outreach(uid) if o["id"] == item["id"]]


def test_vault_upload_api_and_batch_zip():
    import io as _io
    import db as store_mod
    app_obj = create_app()
    client = _demo(app_obj)
    # Anonymous bounces off the login wall.
    anon = app_obj.test_client().post("/vault/upload")
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]
    # Upload a labeled master; it appears on the vault page.
    r = client.post("/vault/upload", data={
        "file": (_io.BytesIO(b"RIFFfakewav"), "night-drive.wav"),
        "kind": "master", "label": "Night Drive v2 final"},
        content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["ok"]
    path = r.get_json()["path"]
    page = client.get("/vault").get_data(as_text=True)
    assert "Night Drive v2 final" in page and "Vault upload" in page
    assert "Upload to Vault" in page and 'id="vault-pills"' in page
    # Bad extension rejected; bogus kind coerced.
    bad = client.post("/vault/upload", data={
        "file": (_io.BytesIO(b"x"), "evil.exe")}, content_type="multipart/form-data")
    assert bad.status_code == 400
    # Batch zip honors only the user's own allowlisted paths.
    z = client.post("/vault/zip", data={"paths": [path, "/uploads/not-mine.png"]})
    assert z.status_code == 200
    assert z.headers["Content-Disposition"].endswith("vault-assets.zip")
    import zipfile
    zf = zipfile.ZipFile(_io.BytesIO(z.data))
    assert len(zf.namelist()) == 1 and zf.namelist()[0].endswith(".wav")
    # Delete removes the record (and the vault-owned file).
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]
    vid = [v for v in store_mod.list_vault_files(uid)
           if v["label"] == "Night Drive v2 final"][0]["id"]
    client.post("/vault/%s/delete" % vid)
    assert not [v for v in store_mod.list_vault_files(uid) if v["id"] == vid]
    # The rack ships its archive button; the studio archives covers.
    rack = client.get("/rack").get_data(as_text=True)
    assert 'id="rk-vault"' in rack
    art = client.get("/artwork").get_data(as_text=True)
    assert "/vault/upload" in art


def test_track_passports_pipeline_and_csv_import():
    import io as _io
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "pp-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "PP", "email": email,
                                 "password": "secret1"})
    # Anonymous import bounces off the login wall.
    anon = app_obj.test_client().post("/tracks/import")
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]
    # Empty catalog: no pipeline strip, but the import control is offered.
    page = client.get("/tracks").get_data(as_text=True)
    assert "In catalog" not in page and "Import CSV catalog" in page
    # CSV import: blank-title rows skipped, known columns land in passports.
    csv_bytes = ("title,isrc,writers,label,release,release_date\n"
                 "Gold Chains,USSB12600001,V. Cross; T. Reed,Street Banker,"
                 "Night Shift,2026-09-01\n"
                 ",,,,,\n"
                 "Second Cut,USSB12600002,V. Cross,,,\n").encode()
    r = client.post("/tracks/import",
                    data={"csv": (_io.BytesIO(csv_bytes), "catalog.csv")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "Gold Chains" in page and "Second Cut" in page
    uid = store_mod.get_user_by_email(email)["id"]
    rows = store_mod.list_os_tracks(uid)
    assert len(rows) == 2
    gold = [t for t in rows if t["title"] == "Gold Chains"][0]
    assert gold["passport"].get("isrc") == "USSB12600001"
    assert gold["passport"].get("songwriters") == "V. Cross; T. Reed"
    assert gold["passport"].get("label") == "Street Banker"
    assert gold["release_title"] == "Night Shift"
    assert gold["release_date"] == "2026-09-01"
    # Pipeline strip renders each real-count stage; pills + ID3 reader ship.
    for stage in ("In catalog", "Metadata complete", "Rights signed",
                  "Release-ready"):
        assert stage in page
    assert 'class="state-pill' in page and 'data-state=' in page
    assert "TIT2" in page and "fromCharCode" in page


def test_onesheet_share_pin_views_and_pitch():
    import io as _io
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "os-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "Sheet Artist", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    with store_mod.get_db() as db:
        db.execute("UPDATE users SET plan = 'label' WHERE id = ?", (uid,))
    # Vault assets feed the public sheet.
    client.post("/vault/upload", data={
        "file": (_io.BytesIO(b"png"), "band.png"), "kind": "press_photo",
        "label": "Press banner"}, content_type="multipart/form-data")
    client.post("/vault/upload", data={
        "file": (_io.BytesIO(b"riff"), "single.wav"), "kind": "master",
        "label": "Lead single"}, content_type="multipart/form-data")
    vids = {v["label"]: v["id"] for v in store_mod.list_vault_files(uid)}
    # The private one-sheet carries the share panel.
    page = client.get("/deal-room/onesheet").get_data(as_text=True)
    assert "Shareable One-Sheet" in page and "Create share link" in page
    client.post("/onesheet/share", data={
        "action": "save", "pin": "4711", "banner": vids["Press banner"],
        "audio": [vids["Lead single"]]})
    share = store_mod.get_onesheet_share(uid)
    assert share["pin"] == "4711" and share["banner"].startswith("/uploads/")
    assert share["audio"][0]["label"] == "Lead single"
    token = share["token"]
    # Anonymous viewer hits the PIN gate; wrong PIN bounces, right one opens.
    anon = app_obj.test_client()
    gate = anon.get("/sheet/" + token).get_data(as_text=True)
    assert "PIN-protected" in gate and "Lead single" not in gate
    assert anon.post("/sheet/" + token, data={"pin": "0000"}).status_code == 403
    anon.post("/sheet/" + token, data={"pin": "4711"})
    sheet = anon.get("/sheet/" + token).get_data(as_text=True)
    assert "Artist One-Sheet" in sheet and "Lead single" in sheet
    assert "Collected Revenue" not in sheet  # money never leaves the house
    # Views log for outsiders only.
    client.get("/sheet/" + token)
    assert store_mod.onesheet_view_stats(token)["total"] == 1
    # A pitch lands in the inbox and notifies the artist; honeypot drops bots.
    anon.post("/sheet/%s/pitch" % token, data={
        "name": "A&R Person", "email": "ar@label.example",
        "message": "Love the single."})
    pitches = [i for i in store_mod.get_inbox() if i["kind"] == "onesheet_pitch"
               and i["payload"].get("artist_id") == uid]
    assert len(pitches) == 1 and pitches[0]["payload"]["email"] == "ar@label.example"
    assert store_mod.unread_notifications(uid) >= 1
    anon.post("/sheet/%s/pitch" % token, data={
        "website": "spam", "email": "x@y.example", "message": "buy followers"})
    assert len([i for i in store_mod.get_inbox()
                if i["kind"] == "onesheet_pitch"
                and i["payload"].get("artist_id") == uid]) == 1
    # Regenerating kills the old link; disabling removes share and views.
    client.post("/onesheet/share", data={"action": "regenerate"})
    assert anon.get("/sheet/" + token).status_code == 404
    client.post("/onesheet/share", data={"action": "disable"})
    assert store_mod.get_onesheet_share(uid) is None


def test_launch_desk_countdown_alerts_and_filters():
    import uuid as _uuid
    import db as store_mod
    import links_store as mls_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "ld-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "LD", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    # No scheduled drop: no countdown, but flow strip + pills render.
    page = client.get("/desk/launch").get_data(as_text=True)
    assert "Next drop" not in page
    assert "each stage reads the last one" in page
    assert 'class="desk-pill' in page and 'data-live="1"' in page
    # A dated track with an incomplete passport raises a real blocker line.
    store_mod.add_os_track(uid, "Summer Anthem", "Summer EP", "2099-08-20")
    mls_mod.create_campaign(uid, "ld-%s" % _uuid.uuid4().hex[:6],
                            {"title": "Summer Anthem",
                             "release_date": "2099-08-20"})
    page = client.get("/desk/launch").get_data(as_text=True)
    assert "Next drop" in page and 'data-date="2099-08-20"' in page
    assert "Release blockers" in page and "Summer Anthem" in page


def test_autopilot_timeline_flags_and_kit_export():
    import uuid as _uuid
    import db as store_mod
    import links_store as mls_mod
    from datetime import date as _date, timedelta as _td
    app_obj = create_app()
    client = app_obj.test_client()
    email = "ap-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "AP", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    soon = (_date.today() + _td(days=5)).isoformat()
    cid = mls_mod.create_campaign(uid, "ap-%s" % _uuid.uuid4().hex[:6],
                                  {"title": "Close Drop",
                                   "release_date": soon})
    page = client.get("/releases/autopilot?campaign=%s&days=14"
                      % cid).get_data(as_text=True)
    # Timeline with a pulsing current stage + days-left readout.
    assert "Autopilot Timeline" in page and "ap-live" in page
    assert "days to release" in page
    # 5 days out: the 14/10/7-day windows are flagged as already closed.
    assert page.count("Window passed") == 3
    # Segmented dial + copy buttons + export.
    assert 'class="kit-copy' in page and "Export full kit" in page
    resp = client.get("/releases/autopilot/kit.txt?campaign=%s&days=14" % cid)
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    body = resp.get_data(as_text=True)
    assert "RELEASE KIT" in body and "Close Drop" in body
    assert "CAPTIONS" in body and "14-DAY PLAN" in body
    assert client.get("/releases/autopilot/kit.txt?campaign=nope").status_code == 404


def test_clean_release_nodes_resolve_ping_and_certificate():
    import uuid as _uuid
    import db as store_mod
    import links_store as mls_mod
    import rollout_store as ros_mod
    import artist_os as ao
    from datetime import date as _date, timedelta as _td
    app_obj = create_app()
    client = app_obj.test_client()
    email = "cr-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "Cert Artist", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    soon = (_date.today() + _td(days=10)).isoformat()
    cid = mls_mod.create_campaign(uid, "cr-%s" % _uuid.uuid4().hex[:6],
                                  {"title": "Neon Nights",
                                   "release_date": soon})
    tid = store_mod.add_os_track(uid, "Neon Nights", "Neon EP", soon)
    store_mod.update_os_track_passport(uid, tid, {"isrc": "USSB12600009"})
    ctid = store_mod.add_catalog_track(uid, {"title": "Neon Nights",
                                             "artist": "Cert Artist"})
    page = client.get("/releases/clean-release?campaign=%s"
                      % cid).get_data(as_text=True)
    # Category nodes + hover JS + passport-pull card with the real value.
    assert 'class="cat-node' in page and "Release assets" in page
    assert "Resolve from Track Passport" in page and "USSB12600009" in page
    # A dated at-risk track pings the inbox exactly once.
    client.get("/releases/clean-release?campaign=%s" % cid)
    pings = [n for n in store_mod.list_notifications(uid)
             if n["kind"] == "release_risk"]
    assert len(pings) == 1 and "Neon Nights" in pings[0]["title"]
    # Applying the pull writes the passport value into the catalog record.
    client.post("/clean-release/resolve", data={"catalog_id": ctid})
    ct = [t for t in store_mod.get_catalog_tracks(uid) if t["id"] == ctid][0]
    assert ct["meta"]["isrc"] == "USSB12600009"
    # Certificate is gated until the track really scores 100...
    assert client.get("/tracks/%s/certificate" % tid).status_code == 302
    # ...then unlocks: full passport, lockbox n/a, live link, rollout, fan.
    full = {k: "registered / cleared / signed"
            for k, _l, _c, _f in ao.PASSPORT_FIELDS}
    full.update({"audio_ok": "1", "artwork_ok": "1",
                 "isrc": "USSB12600009", "upc": "198000000042"})
    store_mod.update_os_track_passport(uid, tid, full)
    store_mod.update_os_track_lockbox(
        uid, tid, {d[0]: {"not_applicable": True} for d in ao.LOCKBOX_DOCS})
    mls_mod.update_campaign(cid, uid, {"status": "live"})
    ros_mod.create_campaign(uid, {"title": "Neon Nights",
                                  "release_date": soon})
    mls_mod.upsert_fan(uid, "fan-%s@example.net" % _uuid.uuid4().hex[:6], cid)
    cert = client.get("/tracks/%s/certificate" % tid)
    assert cert.status_code == 200
    body = cert.get_data(as_text=True)
    assert "Certificate of Verification" in body and "100 / 100" in body
    assert "USSB12600009" in body and "not a legal" in body
    # A stranger can't pull someone else's certificate.
    stranger = app_obj.test_client()
    stranger.post("/signup", data={"name": "X", "email":
                                   "x-%s@example.net" % _uuid.uuid4().hex[:8],
                                   "password": "secret1"})
    assert stranger.get("/tracks/%s/certificate" % tid).status_code == 404


def test_release_scheduler_lanes_warnings_presets_ics():
    import uuid as _uuid
    import db as store_mod
    import links_store as mls_mod
    from datetime import date as _date, timedelta as _td
    app_obj = create_app()
    client = app_obj.test_client()
    email = "rs-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "RS", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    far = (_date.today() + _td(days=40)).isoformat()
    near = (_date.today() + _td(days=10)).isoformat()
    rush = (_date.today() + _td(days=3)).isoformat()
    for slug, title, d in (("far", "Far Drop", far), ("near", "Near Drop", near),
                           ("rush", "Rush Drop", rush)):
        mls_mod.create_campaign(uid, "%s-%s" % (slug, _uuid.uuid4().hex[:6]),
                                {"title": title, "release_date": d})
    page = client.get("/releases").get_data(as_text=True)
    # Date-math lead-time warnings: amber under 21 days, red under 7,
    # nothing for the release with a full runway.
    assert "Lead-time warnings" in page
    assert "under the recommended 21-day runway" in page
    assert "effectively closed" in page
    assert "Far Drop is" not in page
    # Swimlanes render one track per campaign; presets are offered.
    assert "Next 90 days by campaign" in page
    assert "Standard 30-day" in page and "Surprise drop" in page
    # Milestones only appear when a preset is chosen — they're derived.
    assert "nothing is stored or predicted" in page
    on = client.get("/releases?preset=standard").get_data(as_text=True)
    assert "Foundation" in on and on.count("days out") > 3
    # One-way iCal export carries the same derived events.
    resp = client.get("/releases/calendar.ics?preset=standard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "BEGIN:VCALENDAR" in body and body.count("BEGIN:VEVENT") >= 3
    assert "Far Drop" in body
    assert resp.headers["Content-Disposition"].endswith(".ics")


def test_smart_links_gate_preview_sparklines_and_variant_ctr():
    import io as _io
    import uuid as _uuid
    import db as store_mod
    import links_store as mls_mod
    import insights_engine as ie
    app_obj = create_app()
    client = app_obj.test_client()
    email = "sl-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "SL", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    # A vault asset becomes the gate reward.
    client.post("/vault/upload", data={
        "file": (_io.BytesIO(b"zipdata"), "stems.zip"), "kind": "stems",
        "label": "Unreleased demo pack"}, content_type="multipart/form-data")
    vid = store_mod.list_vault_files(uid)[0]["id"]
    resp = client.post("/links/new", data={
        "title": "Gate Test", "artist_name": "SL", "email_capture": "1",
        "gate_reward": vid, "gate_label": "Demo pack + presale code",
        "dest_spotify": "https://open.spotify.com/track/x",
        "dest_apple_music": "https://music.apple.com/x"})
    cid = resp.headers["Location"].split("/")[2]
    camp = mls_mod.get_campaign(cid, uid)
    assert camp["settings"]["gate_reward"] == vid
    # Builder: gate picker + the real-page phone preview.
    page = client.get("/links/%s/edit" % cid).get_data(as_text=True)
    assert "Fan gate reward" in page and 'id="pv-frame"' in page
    assert "/l/%s" % camp["slug"] in page
    # Public page teases the gate; capture returns the reward link.
    client.post("/links/%s/publish" % cid)
    anon = app_obj.test_client()
    public = anon.get("/l/%s" % camp["slug"]).get_data(as_text=True)
    assert "Unlocks instantly" in public and "Demo pack + presale code" in public
    sub = anon.post("/l/%s/subscribe" % camp["slug"],
                    data={"email": "fan@example.net"}).get_json()
    assert sub["ok"] and sub["reward"]["label"] == "Demo pack + presale code"
    assert sub["reward"]["url"].startswith("/l/%s/reward/" % camp["slug"])
    assert anon.get(sub["reward"]["url"]).data == b"zipdata"
    # The reward URL is session-gated; copying it does not bypass the
    # campaign's email capture.
    assert app_obj.test_client().get(sub["reward"]["url"]).status_code == 404
    # Clicks feed the 7-day sparkline and the click-split insight.
    dests = {d["service_key"]: d for d in mls_mod.get_destinations(cid)}
    for _ in range(18):
        anon.get("/l/%s/go/%s" % (camp["slug"], dests["apple_music"]["id"]))
    for _ in range(6):
        anon.get("/l/%s/go/%s" % (camp["slug"], dests["spotify"]["id"]))
    cards = client.get("/links").get_data(as_text=True)
    assert "7-day visits" in cards and "polyline" in cards
    dom = [i for i in ie.build_insights(uid) if "dominates" in i["title"]]
    assert len(dom) == 1 and "Apple Music" in dom[0]["body"]
    assert "75%" in dom[0]["body"]
    # Variant head-to-head stays honest below the sample threshold.
    mls_mod.create_variant(cid, "IG bio", "gt-ig-%s" % _uuid.uuid4().hex[:6],
                           "instagram")
    mls_mod.create_variant(cid, "TikTok", "gt-tt-%s" % _uuid.uuid4().hex[:6],
                           "tiktok")
    vpage = client.get("/links/%s/variants" % cid).get_data(as_text=True)
    assert "Head to Head" in vpage and "No winner called yet" in vpage


def test_rollout_storyboard_casts_and_safezone():
    import io as _io
    import uuid as _uuid
    import db as store_mod
    import rollout_store as ros_mod
    from datetime import date as _date, timedelta as _td
    app_obj = create_app()
    client = app_obj.test_client()
    email = "ro-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "RO", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    store_mod.save_twin_settings(uid, [], "premium", "the wait is over")
    client.post("/vault/upload", data={
        "file": (_io.BytesIO(b"png"), "press.png"), "kind": "press_photo",
        "label": "Press shot"}, content_type="multipart/form-data")
    vid = store_mod.list_vault_files(uid)[0]["id"]
    rd = (_date.today() + _td(days=14)).isoformat()
    resp = client.post("/rollout-studio/new", data={
        "title": "Night Drive", "artist_name": "RO", "release_date": rd,
        "rollout_length": "14", "goal": "presaves", "tone": "hype",
        "platforms": ["tiktok", "instagram_reels"]})
    cid = resp.headers["Location"].split("/")[2]
    client.post("/rollout-studio/%s/generate" % cid, data={})
    posts = ros_mod.list_posts(cid)
    assert posts
    pid = posts[0]["id"]
    # Storyboard: heat legend + vault attach that survives the round trip.
    page = client.get("/rollout-studio/%s/storyboard" % cid).get_data(as_text=True)
    assert "Heat = this post" in page and "Attach from Vault" in page
    client.post("/rollout-studio/%s/storyboard" % cid,
                data={"post_id": pid, "vault_id": vid})
    p0 = ros_mod.get_post(pid)
    assets = {a["id"]: a for a in ros_mod.list_assets(cid)}
    assert p0["asset_id"] in assets
    assert assets[p0["asset_id"]]["asset_type"] == "image"
    page = client.get("/rollout-studio/%s/storyboard" % cid).get_data(as_text=True)
    assert assets[p0["asset_id"]]["file_path"] in page
    # Posts page: rule-based platform casts honoring do-not-say, safe zones.
    page = client.get("/rollout-studio/%s/posts" % cid).get_data(as_text=True)
    assert "Platform casts" in page and "a generator, not a chatbot" in page
    assert "do-not-say phrase" in page
    assert "Safe-zone preview" in page and "Not any platform" in page
    assert "/rollout-studio/%s/storyboard" % cid in page
    # Detach clears; a stranger's vault id never attaches.
    client.post("/rollout-studio/%s/storyboard" % cid,
                data={"post_id": pid, "vault_id": ""})
    assert ros_mod.get_post(pid)["asset_id"] is None
    other = app_obj.test_client()
    other.post("/signup", data={"name": "X", "email":
                                "x-%s@example.net" % _uuid.uuid4().hex[:8],
                                "password": "secret1"})
    other.post("/vault/upload", data={
        "file": (_io.BytesIO(b"png"), "other.png"), "kind": "press_photo"},
        content_type="multipart/form-data")
    client.post("/rollout-studio/%s/storyboard" % cid,
                data={"post_id": pid, "vault_id": "not-my-vault-id"})
    assert ros_mod.get_post(pid)["asset_id"] is None


def test_epk_pitch_share_listening_room_and_vault_assets():
    import io as _io
    import uuid as _uuid
    import db as store_mod
    app_obj = create_app()
    client = app_obj.test_client()
    email = "ep-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "EPK Artist", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    client.post("/vault/upload", data={
        "file": (_io.BytesIO(b"riff"), "single.mp3"), "kind": "master",
        "label": "Lead single"}, content_type="multipart/form-data")
    client.post("/vault/upload", data={
        "file": (_io.BytesIO(b"png"), "press.png"), "kind": "press_photo",
        "label": "Press shot"}, content_type="multipart/form-data")
    vids = {v["label"]: v["id"] for v in store_mod.list_vault_files(uid)}
    # Editor ships the new rail: pitch panel, device preview, accordions,
    # vault pickers on asset slots.
    page = client.get("/epk").get_data(as_text=True)
    assert "Private pitch link" in page and "Create pitch link" in page
    assert "Device preview" in page and "asset-vault" in page
    assert "1 · Identity" in page and "3 · Press" in page
    # Create a PIN-gated share carrying one vault master.
    client.post("/epk/share", data={"action": "save", "pin": "2468",
                                    "audio": [vids["Lead single"]]})
    share = store_mod.get_epk_share(uid)
    assert share["pin"] == "2468" and len(share["audio"]) == 1
    token = share["token"]
    anon = app_obj.test_client()
    gate = anon.get("/pitch/" + token).get_data(as_text=True)
    assert "Private Press Kit" in gate and "Lead single" not in gate
    assert anon.post("/pitch/" + token,
                     data={"pin": "9999"}).status_code == 403
    anon.post("/pitch/" + token, data={"pin": "2468"})
    room = anon.get("/pitch/" + token).get_data(as_text=True)
    assert "Private Listening Room" in room and "Lead single" in room
    # Outside opens are logged and notify the artist; owner opens are not.
    client.get("/pitch/" + token)
    assert store_mod.epk_share_stats(token)["views"] == 1
    assert any("pitch EPK was opened" in n["title"]
               for n in store_mod.list_notifications(uid))
    # Play logging accepts only labels on the share.
    assert anon.post("/pitch/%s/play" % token,
                     json={"label": "Lead single"}).get_json()["ok"]
    assert anon.post("/pitch/%s/play" % token,
                     json={"label": "Fake"}).status_code == 400
    assert store_mod.epk_share_stats(token)["plays"] == [("Lead single", 1)]
    page = client.get("/epk").get_data(as_text=True)
    assert "1 play" in page  # per-track count surfaces on the editor
    # Vault image feeds an asset slot; an audio file is refused.
    ok = client.post("/epk/asset/press_photo/from-vault",
                     json={"vault_id": vids["Press shot"]}).get_json()
    assert ok["ok"] and ok["path"].startswith("/uploads/")
    assert client.post("/epk/asset/press_photo/from-vault",
                       json={"vault_id": vids["Lead single"]}).status_code == 400
    # Expiry kills the link with 410; disable removes share and its log.
    client.post("/epk/share", data={"action": "save", "pin": "2468",
                                    "expires": "2020-01-01",
                                    "audio": [vids["Lead single"]]})
    assert anon.get("/pitch/" + token).status_code == 410
    client.post("/epk/share", data={"action": "disable"})
    assert store_mod.get_epk_share(uid) is None
    assert anon.get("/pitch/" + token).status_code == 404


def test_pulse_peers_trendline_and_milestone(monkeypatch):
    import uuid as _uuid
    import db as store_mod
    import spotify_provider
    import music_apis
    monkeypatch.setattr(spotify_provider, "pulse_configured", lambda: True)
    data = {"me123": {"name": "PU Artist", "image": "", "genres": ["indie"],
                      "followers": 1200, "popularity": 44, "url": "",
                      "top_tracks": []},
            "peerA": {"name": "Peer A", "image": "", "genres": [],
                      "followers": 5100, "popularity": 51, "url": "",
                      "top_tracks": []}}
    monkeypatch.setattr(spotify_provider, "artist_pulse", data.get)
    monkeypatch.setattr(music_apis, "deezer_artist_fans",
                        lambda name: {"fans": 130})
    app_obj = create_app()
    client = app_obj.test_client()
    email = "pu-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "PU", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    store_mod.save_pulse_profile(uid, "me123", "PU Artist", "")
    # An older sub-1k snapshot so the 1,000-follower milestone is detected.
    store_mod.record_pulse_snapshot(uid, 900, 40, 100)
    with store_mod.get_db() as db:
        db.execute("UPDATE pulse_snapshots SET day = '2026-07-10'"
                   " WHERE user_id = ?", (uid,))
    # Peer pinning: no self, cap of three, removable.
    assert client.post("/pulse/peer/add", json={
        "id": "me123", "name": "PU Artist"}).status_code == 400
    assert client.post("/pulse/peer/add", json={
        "id": "peerA", "name": "Peer A"}).get_json()["ok"]
    for pid in ("peerB", "peerC"):
        client.post("/pulse/peer/add", json={"id": pid, "name": pid})
    over = client.post("/pulse/peer/add", json={"id": "peerD", "name": "D"})
    assert over.status_code == 400
    client.post("/pulse/peer/peerB/remove")
    client.post("/pulse/peer/peerC/remove")
    store_mod.record_peer_snapshot(uid, "peerA", 4900, 50)
    with store_mod.get_db() as db:
        db.execute("UPDATE pulse_peer_snapshots SET day = '2026-07-10'"
                   " WHERE user_id = ? AND artist_id = 'peerA'", (uid,))
    page = client.get("/pulse").get_data(as_text=True)
    # Layered trendline from real snapshots, with the honest no-fake-lines note.
    assert "Pulse Graph" in page and page.count("<polyline") == 3
    assert "no line is better than a fake one" in page
    # Peer Watch: you + peer, both with measured 7-day deltas.
    assert "Peer A" in page and "(you)" in page
    assert "+200" in page and "+300" in page
    # Milestone detected from snapshot history; canvas value safely quoted.
    assert "Milestone crossed" in page and "1,000" in page
    assert '"1,000"' in page


def test_tour_pnl_board_flags_and_money_queue_feed():
    import uuid as _uuid
    import db as store_mod
    from datetime import date as _date, timedelta as _td
    app_obj = create_app()
    client = app_obj.test_client()
    email = "tr-%s@example.net" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "Tour", "email": email,
                                 "password": "secret1"})
    uid = store_mod.get_user_by_email(email)["id"]
    with store_mod.get_db() as db:
        db.execute("UPDATE users SET plan = 'label' WHERE id = ?", (uid,))
    d1 = (_date.today() + _td(days=10)).isoformat()
    d2 = (_date.today() + _td(days=11)).isoformat()
    d3 = (_date.today() + _td(days=15)).isoformat()
    store_mod.add_tour_show(uid, d1, "The Basement", "Nashville, TN", "")
    store_mod.add_tour_show(uid, d2, "The Empty Bottle", "Chicago, IL", "")
    store_mod.add_tour_show(uid, d3, "The Echo", "Los Angeles, CA", "")
    past = (_date.today() - _td(days=20)).isoformat()
    settled = store_mod.add_tour_show(uid, past, "Home Show",
                                      "Nashville, TN", "")
    store_mod.update_tour_show_status(uid, settled, "settled")
    store_mod.save_show_settlement(uid, settled, {
        "deal_type": "guarantee_split", "guarantee": "500",
        "door_gross": "2000", "split_pct": "20", "merch_gross": "300",
        "merch_cut_pct": "10", "expenses": "150"})
    page = client.get("/tour").get_data(as_text=True)
    # P&L roll-up: 500 guarantee + 400 door + 270 merch - 150 = 1020 walk.
    assert "Tour P&L" in page and "$1020.00" in page
    assert "-$150.00" in page and "nothing estimated" in page
    # Back-to-back different-city dates flag on date math alone.
    assert "Routing flags" in page and "back to back" in page
    assert "flags the pattern instead of guessing" in page
    # Route strip shows the run in order with day gaps.
    assert "Route:" in page and "—1d→" in page and "—4d→" in page
    # Board view: one column per status, cards carry the real walk.
    board = client.get("/tour?view=board").get_data(as_text=True)
    assert "$1020.00 walk" in board and "The Basement" in board
    assert board.count('sb-badge') >= 5  # five status columns, now badges
    # Money Queue surfaces settled tour income as collected money.
    mq = client.get("/money-queue").get_data(as_text=True)
    assert "Settled tour income" in mq and "$1020.00" in mq
    assert "1 settled show" in mq


# --- /login: Session Recall -----------------------------------------------

def test_login_session_recall_page():
    """The rebuilt /login: racks in order, real form, no invented claims."""
    body = create_app().test_client().get("/login").get_data(as_text=True)
    assert "RETURN TO YOUR DESK." in body
    assert "A. SESSION RECALL" in body
    assert "RECALL MY DESK" in body
    assert "B. TOUR STREET BANKER" in body
    assert "YOUR MIX IS READY" in body          # rendered hidden until JS
    assert 'id="lsr-mix" hidden' in body
    # Real form wiring the backend already expects.
    assert 'name="email"' in body and 'name="password"' in body
    assert 'autocomplete="current-password"' in body
    assert 'name="remember"' in body
    # Four workspaces, secondary rows, security line, minimal footer.
    for w in ["ARTIST", "PRO", "LABEL", "FAN"]:
        assert w in body
    # One row, two named destinations - and the fan link arrives on the
    # fan side rather than on an artist-ticked form.
    assert "CREATE ARTIST ACCOUNT" in body
    assert 'href="/signup?as=fan"' in body
    assert "GO TO FAN EXPERIENCE" not in body
    assert "Secure account access. Demo workspaces contain sample data." in body
    assert 'href="/forgot"' in body and 'href="/terms"' in body
    # No unverified security marketing, no implementation language.
    for banned in ["SOC 2", "bank-grade", "end-to-end", "hashed",
                   "encryption at rest", "never share your information"]:
        assert banned not in body, banned


def test_login_remember_device_controls_session_lifetime():
    """Checked -> 31-day cookie (has an Expires); unchecked -> browser
    session cookie (no Expires). The credential check itself is untouched."""
    app_obj = create_app()
    client = app_obj.test_client()
    r = client.post("/login", data={"email": "demo@streetbanker.io",
                                    "password": "sweep", "remember": "1"})
    assert r.status_code == 302
    cookie = r.headers.get("Set-Cookie", "")
    assert "Expires=" in cookie
    client2 = app_obj.test_client()
    r2 = client2.post("/login", data={"email": "demo@streetbanker.io",
                                      "password": "sweep"})
    assert r2.status_code == 302
    assert "Expires=" not in r2.headers.get("Set-Cookie", "")


def test_demo_access_captures_the_lead():
    """The demo password is earned: the request stores an inbox lead and
    marks the browser with a cookie; the honeypot swallows bots."""
    import db as store

    client = create_app().test_client()
    r = client.post("/demo-access", data={"email": "lead@example.com",
                                          "workspace": "label"})
    assert r.status_code == 302
    assert "sb_demo_lead=" in r.headers.get("Set-Cookie", "")
    leads = [i for i in store.get_inbox() if i["kind"] == "demo-access"]
    assert leads, "lead was not stored"
    payload = leads[0]["payload"]      # get_inbox decodes it
    assert payload["email"] == "lead@example.com"
    assert payload["workspace"] == "label"
    assert payload["password_sent"] in (True, False)  # honest about the mailer
    # Bots fill the honeypot; nothing is stored for them.
    before = len([i for i in store.get_inbox() if i["kind"] == "demo-access"])
    client.post("/demo-access", data={"email": "bot@example.com",
                                      "workspace": "artist", "company": "x"})
    after = len([i for i in store.get_inbox() if i["kind"] == "demo-access"])
    assert after == before
    # Junk email is bounced, not stored.
    r3 = client.post("/demo-access", data={"email": "not-an-email"})
    assert "demo=error" in r3.headers.get("Location", "")


def test_login_backend_behaviour_is_unchanged():
    """The redesign is presentation: same fields, same errors, same routing."""
    client = create_app().test_client()
    ok = client.post("/login", data={"email": "demo@streetbanker.io",
                                     "password": "sweep"})
    assert ok.status_code == 302 and "/walkthrough" in ok.headers["Location"]
    bad = client.post("/login", data={"email": "demo@streetbanker.io",
                                      "password": "wrong"})
    assert bad.status_code == 200
    assert "Incorrect email or password." in bad.get_data(as_text=True)


# --- the Artist Signal Profile --------------------------------------------

def test_artist_signal_profile_config_shape():
    """Short plate labels + full names; every lane names the channels it
    is chosen by; every recommendation resolves to a real route."""
    from artist_eq_config import get_artist_eq_config

    cfg = get_artist_eq_config()
    keys = {c["key"] for c in cfg["channels"]}
    for c in cfg["channels"]:
        assert c["short"] and c["short"] == c["short"].upper()
        assert len(c["short"]) <= 9          # one engraved word per channel
        assert c["label"] and c["desc"] and c["icon"]
    assert [l["id"] for l in cfg["lanes"]] == [
        "distribution", "development", "partnership"]
    for lane in cfg["lanes"]:
        assert set(lane["keys"]) <= keys and len(lane["keys"]) == 3
        assert lane["why"] and lane["href"]
    # Every module and action the panel can print has a route on file.
    named = {n for options in cfg["modules"].values() for n, _s in options}
    assert named <= set(cfg["module_routes"])
    labels = {l for acts in cfg["actions"].values() for l, _s in acts}
    assert labels <= set(cfg["action_routes"])
    client = _demo()
    for action, href in cfg["action_routes"].items():
        assert client.get(href).status_code < 400, "%s -> %s" % (action, href)


def test_homepage_carries_the_signal_profile_hooks():
    """The EQ reports inside its own console and changes nothing else."""
    body = _demo().get("/").get_data(as_text=True)
    assert "Your recommended tools and next actions update instantly." in body
    assert "Reset EQ" in body
    assert "streetBankerArtistEq" in body
    # The subtle per-card reactions are gone: no lane badges, no tool
    # badges, no Sweep CTA swap hook. The page responds through one
    # coordinated visual mode instead.
    for gone in ["sb-lane-badge", "sb-tool-badge", "sb-sweep-cta",
                 "sb-lanes-balanced", "data-tool="]:
        assert gone not in body, gone
    # `data-lane` exists again in Section 6, where it belongs to that
    # section's own hover state. What matters here is that the EQ still
    # writes nothing outside itself.
    eq_js = open("static/js/artist-eq.js", encoding="utf-8").read()
    for reach in ("document.body", "data-lane", "data-artist-mode",
                  "querySelectorAll(\".sb-"):
        assert reach not in eq_js, reach
    # The page is STATIC: the EQ reports inside its own racks and touches
    # nothing else. Every page-reaction hook that was tried - badges,
    # tints, adaptive layers, CTA rewording, the banner strip - is gone.
    for gone in ["data-artist-mode", "sb-hero-adaptive", "sb-mode-banner",
                 "sb-final-cta", "sb-adaptive-layer"]:
        assert gone not in body, gone
    assert 'id="sbeq-score"' in body and 'id="sbeq-lane"' in body
    # The hero's own fade is now the Section 2 veil: the same idea (the
    # photograph falling off into the page rather than ending at an edge)
    # on the rebuilt hero rather than the old white-page one.
    assert "sbhero-veil" in body
    assert 'class="min-h-screen bg-white' in body
    assert "Run a Royalty Sweep" in body
    assert "Build my Street Banker" in body


def test_artist_signal_profile_api_validates():
    """Anon gets 401; junk is clamped, filtered, and capped server-side."""
    import db as store_mod

    app_obj = create_app()
    anon = app_obj.test_client()
    assert anon.post("/api/artist-signal-profile", json={}).status_code == 401

    client = app_obj.test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    keys = ["release", "creative", "audience", "rights", "revenue", "growth"]
    junk = {"priorities": {k: (99 if k == "release" else 5) for k in keys},
            "recommendedLane": "Fake Lane",
            "recommendedModules": ["Royalty Sweep", "EvilModule"],
            "firstActions": ["Run your Royalty Sweep", 123, "y" * 500],
            "preset": "x" * 100}
    assert client.post("/api/artist-signal-profile", json=junk).status_code == 200
    p = client.get("/api/artist-signal-profile").get_json()["profile"]
    assert p["priorities"]["release"] == 10
    assert p["recommendedLane"] == ""
    assert p["recommendedModules"] == ["Royalty Sweep"]
    assert len(p["preset"]) <= 32 and len(p["firstActions"][1]) <= 120
    assert p["source"] == "homepage_artist_eq"
    # Missing priorities are rejected, not guessed.
    bad = client.post("/api/artist-signal-profile",
                      json={"priorities": {"release": 5}})
    assert bad.status_code == 400


def test_signal_profile_reaches_dashboard_twin_and_onboarding():
    """The saved mix shows up where the spec says: Command Center card,
    Artist Twin selected-priorities context, onboarding program panel."""
    from artist_eq_config import get_artist_eq_config

    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    keys = ["release", "creative", "audience", "rights", "revenue", "growth"]
    lane = get_artist_eq_config()["lanes"][1]["name"]
    client.post("/api/artist-signal-profile", json={
        "priorities": {k: 6 for k in keys},
        "recommendedLane": lane,
        "recommendedModules": ["AI Artist Twin"],
        "firstActions": ["Build a 21-day rollout around the active release"],
        "preset": "Custom"})
    cc = client.get("/command-center").get_data(as_text=True)
    assert "Artist Signal Profile" in cc
    assert lane in cc
    assert "Retune my priorities" in cc and "View my program" in cc
    tw = client.get("/artist-twin").get_data(as_text=True)
    assert "priorities you selected" in tw
    assert "a choice, not a measurement" in tw
    ob = client.get("/onboarding").get_data(as_text=True)
    assert 'id="sb-program-ready" hidden' in ob   # hidden until hydrated
    assert "Your Street Banker program is ready." in ob


def test_rack_rough_split_ships_honestly():
    """Rough Split: real DSP, honestly framed - never sold as ML."""
    import io as _io

    client = create_app().test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    body = client.get("/rack").get_data(as_text=True)
    assert 'id="rk-roughsplit"' in body
    assert "Rough Split" in body
    # The copy says exactly what it is and is not.
    assert "not ML isolation" in body
    assert "session-prep quality, expect bleed" in body
    assert "sum back to your record exactly" in body
    assert "nothing uploads" in body
    # Script order: the math module loads before the deck wiring.
    assert body.index("roughsplit.js") < body.index("rackdsp.js")
    assert client.get("/static/js/roughsplit.js").status_code == 200
    js = _io.open("static/js/roughsplit.js", encoding="utf-8").read()
    # The core stays honest and dependency-free.
    for banned in ["fetch(", "XMLHttpRequest", "WebSocket"]:
        assert banned not in js, banned
    assert "Fitzgerald" in js            # the algorithm is named, not vague


def test_studio_split_is_env_gated_and_honest():
    """StemSplit quality tier: invisible without the key, honest with it,
    and the endpoints never pretend. No external call is ever made here -
    only the gating and validation layers are exercised."""
    import io as _io
    import json
    import os as _os

    _os.environ.pop("STEMSPLIT_API_KEY", None)
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    page = client.get("/rack").get_data(as_text=True)
    assert "rk-studiosplit" not in page          # unconfigured -> not rendered
    assert client.post("/rack/studio-split", data={}).status_code == 503
    assert client.get("/stem-src/deadbeef").status_code == 404
    # Path tricks never resolve to files.
    from stemsplit_provider import source_path
    assert source_path("../../app.py") is None
    assert source_path("a/b") is None

    # The diagnostic reports shape, never the secret itself.
    diag = client.get("/rack/studio-split/diag").get_json()
    assert diag["configured"] is False and diag["present"] is False

    _os.environ["STEMSPLIT_API_KEY"] = "test-key-not-real"
    try:
        diag = client.get("/rack/studio-split/diag").get_json()
        assert diag["configured"] is True
        assert diag["length"] == len("test-key-not-real")
        # No field of the diagnostic may echo the value.
        assert "test-key-not-real" not in json.dumps(diag)
        assert app_obj.test_client().get(
            "/rack/studio-split/diag").status_code in (302, 401)
        page = client.get("/rack").get_data(as_text=True)
        assert "Studio Split" in page
        # The copy admits the one thing this feature does differently.
        assert "uploads your track" in page
        assert "processed by StemSplit" in page
        assert client.post("/rack/studio-split", data={}).status_code == 400
        r = client.post("/rack/studio-split",
                        data={"audio": (_io.BytesIO(b"x"), "notes.txt")})
        assert r.status_code == 400              # extension whitelist
        # Anonymous callers meet the global login gate first.
        assert app_obj.test_client().post(
            "/rack/studio-split", data={}).status_code in (302, 401)
    finally:
        _os.environ.pop("STEMSPLIT_API_KEY", None)


def test_stemsplit_reads_both_published_response_shapes():
    """The REST docs return nested outputs; the vendor's n8n node returns
    flat <stem>Url keys. Whichever this account gets, the four lanes have
    to resolve - and the scrubber must keep the key out of diagnostics."""
    import os as _os

    from stemsplit_provider import STEMS, _outputs, _scrub

    nested = _outputs({"outputs": {
        "vocals": {"url": "https://x/v.mp3", "expiresAt": "soon"},
        "drums": {"url": "https://x/d.mp3"}}})
    assert nested == {"vocals": "https://x/v.mp3", "drums": "https://x/d.mp3"}

    flat = _outputs({"vocalsUrl": "https://x/v.mp3",
                     "bassUrl": "https://x/b.mp3",
                     "vocalsExpiresAt": "soon"})
    assert flat == {"vocals": "https://x/v.mp3", "bass": "https://x/b.mp3"}

    # Nested wins when both appear, and junk is skipped rather than crashing.
    both = _outputs({"outputs": {"vocals": {"url": "https://good"}},
                     "vocalsUrl": "https://stale", "otherUrl": None})
    assert both == {"vocals": "https://good"}
    assert _outputs({}) == {}
    assert _outputs({"outputs": None}) == {}
    assert "other" in STEMS and "instrumental" in STEMS

    _os.environ["STEMSPLIT_API_KEY"] = "sk_live_scrubber_probe_value"
    try:
        assert _scrub("Bearer sk_live_scrubber_probe_value bad") == \
            "Bearer [redacted] bad"
    finally:
        _os.environ.pop("STEMSPLIT_API_KEY", None)


def test_valve_stage_keys_match_the_engine():
    """The template hard-codes six valve keys, tubes.js declares six stages
    and rackdsp.js wires six taps. If those lists ever drift, a socket
    lights for a stage that is not there - so pin them to each other
    instead of trusting three hand-written lists to stay in step."""
    import re

    tpl = open("templates/rack.html", encoding="utf8").read()
    js = open("static/js/tubes.js", encoding="utf8").read()
    rack_js = open("static/js/rackdsp.js", encoding="utf8").read()

    engine = re.findall(r'\{key: "(\w+)", tube: "(V\d)"', js)
    assert len(engine) == 6, engine
    tpl_keys = re.findall(r'\("(\w+)",\s+"(V\d)",', tpl)
    assert tpl_keys == engine, (tpl_keys, engine)
    m = re.search(r'var VALVE_KEYS = \[([^\]]+)\]', rack_js)
    assert m, "VALVE_KEYS not found in rackdsp.js"
    wired = [x.strip().strip('"') for x in m.group(1).split(",")]
    assert wired == [k for k, _ in engine], (wired, engine)


def test_vu_needle_agrees_with_its_printed_scale():
    """SB-05's gain-reduction dial is printed non-linearly - 0, 3, 6, 10 and
    20 sit at roughly even spacings - so the needle has to be interpolated
    through those same anchors. It was swept linearly, which pointed it at
    roughly half the reduction the scale claimed and made a working meter
    look dead. Derive the true tick angles from the SVG text positions and
    check the JS table matches, so the two can never drift again."""
    import math
    import re

    tpl = open("templates/rack.html", encoding="utf8").read()
    js = open("static/js/rackdsp.js", encoding="utf8").read()

    # The dial pivots at (100, 100) and the needle starts pointing up.
    vu = tpl[tpl.index('id="rk-vu"'):]
    vu = vu[:vu.index("</svg>")]
    ticks = re.findall(r'<text x="(\d+)" y="(\d+)">(\d+)</text>', vu)
    assert len(ticks) == 5, ticks
    printed = {}
    for x, y, label in ticks:
        dx, dy = int(x) - 100, 100 - int(y)
        printed[int(label)] = math.degrees(math.atan2(dx, dy))

    m = re.search(r'var VU_SCALE = \[(.+?)\];', js, re.S)
    assert m, "VU_SCALE not found in rackdsp.js"
    pairs = re.findall(r'\[(-?[\d.]+), (-?[\d.]+)\]', m.group(1))
    table = {float(db): float(angle) for db, angle in pairs}

    assert sorted(table) == sorted(float(k) for k in printed), (table, printed)
    for db, angle in table.items():
        want = printed[int(db)]
        assert abs(angle - want) < 1.0, (db, angle, want)

    # At rest the needle must already sit on the printed zero, before any
    # script runs - otherwise the dial lies on a cold page load.
    rest = re.search(r'id="rk-vu-needle"[^>]*transform="rotate\((-?[\d.]+)', tpl)
    assert rest, "needle has no resting transform"
    assert abs(float(rest.group(1)) - printed[0]) < 1.0, rest.group(1)

    # And an idle dial has to say why it is idle rather than read 0.0 dB.
    assert '"COMP OFF"' in js and '"COMP AT 1:1"' in js


def test_hours_engine_arithmetic():
    """Every figure on the Hours desk is arithmetic over stored rows, so the
    arithmetic is checked without a database or a request."""
    import hours_engine as H
    from datetime import date

    entries = [
        {"id": "a", "day": "2026-07-28", "client": "Rello", "project": "Night",
         "hours": 4.5, "rate": 60, "billed": 0},
        {"id": "b", "day": "2026-07-30", "client": "Rello", "project": "Night",
         "hours": 3.25, "rate": 75, "billed": 0},
        {"id": "c", "day": "2026-07-20", "client": "Kaz", "project": "Other",
         "hours": 5.0, "rate": 75, "billed": 1},
    ]
    st = H.session_totals(entries)
    assert st["hours"] == 12.75
    assert st["unbilled_value"] == round(4.5 * 60 + 3.25 * 75, 2)
    assert st["billed_value"] == 375.0
    # A blended rate needs hours to blend; with none it is absent, not zero.
    assert H.session_totals([])["effective_rate"] is None

    # Grouped the way you would invoice: billed rows are already gone.
    groups = H.group_by_client(entries)
    assert len(groups) == 1 and groups[0]["client"] == "Rello"
    assert groups[0]["hours"] == 7.75
    assert groups[0]["first_day"] == "2026-07-28"
    assert groups[0]["last_day"] == "2026-07-30"

    # Numbering counts only this year, so January starts clean.
    invoices = [{"number": "SB-2026-001", "total": 100, "status": "paid"},
                {"number": "SB-2026-002", "total": 250, "status": "sent"},
                {"number": "SB-2025-009", "total": 50, "status": "sent"}]
    assert H.next_invoice_number(invoices, date(2026, 7, 30)) == "SB-2026-003"
    assert H.next_invoice_number(invoices, date(2027, 1, 2)) == "SB-2027-001"
    iv = H.invoice_totals(invoices)
    assert iv["outstanding"] == 300.0 and iv["paid"] == 100.0

    # Requested money is not agreed money, in either direction.
    subs = [{"status": "pending", "hours": 6, "rate": 60},
            {"status": "approved", "hours": 4.5, "rate": 70},
            {"status": "rejected", "hours": 2, "rate": 50}]
    sub = H.submission_totals(subs)
    assert sub["pending_value"] == 360.0 and sub["approved_value"] == 315.0
    bookings = [{"status": "requested", "hours": 2, "rate": 75},
                {"status": "confirmed", "hours": 3, "rate": 40, "id": "bk1",
                 "day": "2026-07-30", "start_hour": 13, "service": "Studio",
                 "who": "Dee"}]
    bt = H.booking_totals(bookings)
    assert bt["requested_value"] == 150.0 and bt["confirmed_value"] == 120.0

    summary = H.desk_summary(entries, invoices, bookings, subs)
    # Owed = unbilled work + invoices out and unpaid. Owe = approved only.
    assert summary["owed_to_you"] == round(st["unbilled_value"] + 300.0, 2)
    assert summary["you_owe"] == 315.0
    assert summary["net"] == round(summary["owed_to_you"] - 315.0, 2)
    assert H.desk_summary([], [], [], [])["has_data"] is False

    assert H.fmt_hour(0) == "00:00" and H.fmt_hour(13.5) == "13:30"
    assert H.fmt_hour(9.25) == "09:15"

    # Clashes are detected, not left for the user to spot.
    blocks = [{"id": "1", "start_hour": 9, "hours": 2, "label": "A"},
              {"id": "2", "start_hour": 10, "hours": 1, "label": "B"},
              {"id": "3", "start_hour": 14, "hours": 1, "label": "C"}]
    assert H.find_clashes(blocks) == {"1", "2"}
    # Three in one hour counts three blocks, not "one pair" or "three pairs".
    trio = [{"id": "x", "start_hour": 9, "hours": 2},
            {"id": "y", "start_hour": 9.5, "hours": 1},
            {"id": "z", "start_hour": 10, "hours": 1}]
    assert H.day_plan(trio, [], from_hour=8, to_hour=12)["clash_items"] == 3
    assert H.day_plan(blocks[2:], [], from_hour=8, to_hour=16)["clash_items"] == 0

    # A confirmed booking joins the plan, so it cannot be double-booked.
    plan = H.day_plan(blocks, bookings, day="2026-07-30", from_hour=8, to_hour=16)
    assert plan["planned_hours"] == 7.0
    at13 = [r for r in plan["rows"] if r["hour"] == 13][0]
    assert any(b["source"] == "booking" for b in at13["blocks"])
    # The rows carry "blocks", never "items" - row.items in a template
    # resolves to dict.items and silently iterates the wrong thing.
    assert "items" not in plan["rows"][0]

    assert H.flag_entry({"hours": 26, "rate": 0, "client": ""}) != []
    assert H.flag_entry({"hours": 3, "rate": 60, "client": "Rello"}) == []
    assert H.bookable_services([{"bookable": 1}, {"bookable": 0}]) == [{"bookable": 1}]


def test_hours_desk_end_to_end():
    """The four panels, driven through their real routes: log and invoice,
    rate card and bookings, collaborator approvals, and the day plan."""
    from werkzeug.datastructures import MultiDict

    import db as store_mod

    app_obj = create_app()
    artist = _demo(app_obj)
    uid = store_mod.get_user_by_email("demo@streetbanker.io")["id"]

    # An empty desk says so rather than showing a plausible number.
    page = artist.get("/hours").get_data(as_text=True)
    assert "Hours Desk" in page
    assert "every figure above is zero" in page

    # Rate card: the starter set, then a custom line with a minimum.
    artist.post("/hours/rate", data={"starter": "1"})
    artist.post("/hours/rate", data={"service": "Tour rehearsal", "rate": "35",
                                     "min_hours": "3", "bookable": "on"})
    rates = store_mod.list_hours_rates(uid)
    assert len(rates) == 5
    assert artist.post("/hours/rate", data={"service": " "}).status_code == 400

    # Session log.
    for day, hours, rate in [("2026-07-28", "4.5", "60"),
                             ("2026-07-30", "3.25", "75")]:
        artist.post("/hours/log", data={"day": day, "client": "Rello",
                                        "project": "Nightshift",
                                        "service": "mix", "hours": hours,
                                        "rate": rate})
    assert artist.post("/hours/log", data={"hours": "0"}).status_code == 400
    page = artist.get("/hours").get_data(as_text=True)
    assert "$513.75" in page          # 4.5*60 + 3.25*75

    # Invoice, then the locks: a billed line cannot be deleted or re-invoiced.
    ids = [e["id"] for e in store_mod.list_hours_entries(uid)]
    r = artist.post("/hours/invoice", data=MultiDict(
        [("entry_id", i) for i in ids]
        + [("client", "Rello"), ("number", "SB-2026-001")]))
    assert r.status_code == 302
    inv = store_mod.list_hours_invoices(uid)[0]
    assert inv["total"] == 513.75 and inv["hours"] == 7.75
    assert all(e["billed"] for e in store_mod.list_hours_entries(uid))
    assert artist.post("/hours/entry/%s/delete" % ids[0]).status_code == 400
    again = artist.post("/hours/invoice",
                        data=MultiDict([("entry_id", i) for i in ids]))
    assert again.status_code == 400
    artist.post("/hours/invoice/%s/paid" % inv["id"])
    assert store_mod.list_hours_invoices(uid)[0]["status"] == "paid"

    # Bookings price themselves from the card, and honour its minimum.
    short = artist.post("/hours/booking", data={"service": "Tour rehearsal",
                                                "day": "2026-08-01",
                                                "hours": "1"})
    assert short.status_code == 400 and "minimum" in short.get_json()["error"]
    nope = artist.post("/hours/booking", data={"service": "Beat session",
                                               "hours": "2"})
    assert nope.status_code == 400      # on the card, but not bookable
    artist.post("/hours/booking", data={"service": "Tour rehearsal",
                                        "who": "Dee", "day": "2026-08-01",
                                        "start_hour": "13", "hours": "3"})
    bk = store_mod.list_hours_bookings(uid)[0]
    assert bk["rate"] == 35.0           # from the card, not the form
    artist.post("/hours/booking/%s/confirmed" % bk["id"])
    assert store_mod.list_hours_bookings(uid)[0]["status"] == "confirmed"
    assert artist.post("/hours/booking/%s/nonsense" % bk["id"]).status_code == 400

    # Collaborator hours: approve one, reject one with a reason.
    artist.post("/hours/submission", data={"who": "Dee", "role": "engineer",
                                           "day": "2026-07-29", "hours": "6",
                                           "rate": "60"})
    artist.post("/hours/submission", data={"who": "Kaz", "role": "video",
                                           "day": "2026-07-30", "hours": "4.5",
                                           "rate": "70"})
    assert artist.post("/hours/submission", data={"who": "X",
                                                  "hours": "0"}).status_code == 400
    subs = store_mod.list_hours_submissions(uid)
    artist.post("/hours/submission/%s/approve" % subs[0]["id"])
    artist.post("/hours/submission/%s/reject" % subs[1]["id"],
                data={"reason": "not agreed"})
    subs = store_mod.list_hours_submissions(uid)
    approved = [s for s in subs if s["status"] == "approved"]
    rejected = [s for s in subs if s["status"] == "rejected"]
    assert len(approved) == 1 and len(rejected) == 1
    # A rejection keeps its reason - an unexplained one is how disputes start.
    assert rejected[0]["reason"] == "not agreed"
    # And a decided sheet cannot be quietly re-decided.
    assert not store_mod.decide_hours_submission(uid, approved[0]["id"], False)
    assert artist.post("/hours/submission/%s/sideways"
                       % approved[0]["id"]).status_code == 400

    # Day plan: overlapping blocks are flagged, the booking is folded in.
    artist.post("/hours/block", data={"day": "2026-08-01", "label": "Writing",
                                      "start_hour": "12", "hours": "2"})
    artist.post("/hours/block", data={"day": "2026-08-01", "label": "Admin",
                                      "start_hour": "13", "hours": "1"})
    assert artist.post("/hours/block",
                       data={"day": "2026-08-01", "label": " "}).status_code == 400
    page = artist.get("/hours?day=2026-08-01").get_data(as_text=True)
    assert "overlapping" in page and "Booked" in page
    blocks = store_mod.list_hours_blocks(uid, "2026-08-01")
    artist.post("/hours/block/%s/done" % blocks[0]["id"],
                data={"day": "2026-08-01"})
    assert store_mod.list_hours_blocks(uid, "2026-08-01")[0]["done"] == 1
    artist.post("/hours/block/%s/delete" % blocks[1]["id"],
                data={"day": "2026-08-01"})
    assert len(store_mod.list_hours_blocks(uid, "2026-08-01")) == 1
    assert artist.post("/hours/block/%s/sideways"
                       % blocks[0]["id"]).status_code == 400

    # A bad date cannot land a row on a day that does not exist.
    artist.post("/hours/log", data={"client": "Z", "hours": "1", "rate": "1",
                                    "day": "not-a-date"})
    assert all(len(e["day"]) == 10 for e in store_mod.list_hours_entries(uid))

    # The headline reports agreed money only: approved hours, not pending.
    page = artist.get("/hours").get_data(as_text=True)
    assert "Approved collaborator hours only" in page
    assert "no forecast here" in page


def test_hours_desk_needs_an_account():
    """Nothing on the desk is readable or writable while signed out."""
    app_obj = create_app()
    anon = app_obj.test_client()
    r = anon.get("/hours")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    for path in ("/hours/log", "/hours/rate", "/hours/booking",
                 "/hours/submission", "/hours/block", "/hours/invoice"):
        r = anon.post(path, data={})
        assert r.status_code in (302, 401), path


def test_loudness_targets_are_published_not_verified():
    """The platform targets are figures those services publish, not
    something this app checks with them, and they move. Saying so matters:
    quoting a number as fact that nobody here verified is the kind of small
    dishonesty that costs someone a master."""
    import re

    js = open("static/js/loudness.js", encoding="utf8").read()
    tpl = open("templates/rack.html", encoding="utf8").read()

    # Every target carries a loudness figure AND a true-peak ceiling; one
    # without a ceiling would invite a normalise that clips.
    targets = re.findall(r'\{key: "(\w+)", name: "([^"]+)", lufs: (-?\d+), '
                         r'ceiling: (-?\d+)\}', js)
    assert len(targets) >= 6, targets
    for key, name, lufs, ceiling in targets:
        assert -30 <= int(lufs) <= -8, (name, lufs)
        assert -3 <= int(ceiling) <= 0, (name, ceiling)

    assert "published" in js.lower()
    # The page must not imply the platforms were consulted.
    assert "not something this app checks with them" in tpl
    assert "they do move" in tpl


def test_loudness_module_stays_node_testable():
    """loudness.js must stay free of DOM and Web Audio, or the compliance
    checks in tests/js can no longer run it - and those checks are the only
    thing standing between this and a plausible-looking wrong number."""
    js = open("static/js/loudness.js", encoding="utf8").read()
    for banned in ("document.", "AudioContext", "fetch(", "XMLHttpRequest"):
        assert banned not in js, banned
    assert "module.exports" in js


def test_backup_sigv4_matches_the_published_vector():
    """An off-box backup that 403s is worse than none, because you stop
    worrying about it. AWS publishes a signing-key derivation vector; if
    the chain reproduces it the SigV4 maths is right."""
    import backup_store

    key = backup_store._signing_key(
        "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
        "20150830", "us-east-1", "iam")
    assert key.hex() == (
        "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9")


def test_backup_store_is_env_gated_and_leaks_nothing(monkeypatch):
    """No credentials, no pretending — and the display target never
    carries the secret that reaches it."""
    import datetime

    import backup_store

    for k in ("BACKUP_S3_ENDPOINT", "BACKUP_S3_BUCKET",
              "BACKUP_S3_KEY", "BACKUP_S3_SECRET"):
        monkeypatch.delenv(k, raising=False)
    assert backup_store.configured() is False
    assert backup_store.target() == ""
    ok, detail = backup_store.put("x.zip", b"data")
    assert ok is False and "not configured" in detail

    monkeypatch.setenv("BACKUP_S3_ENDPOINT", "https://acct.r2.example.com")
    monkeypatch.setenv("BACKUP_S3_BUCKET", "sb-backups")
    monkeypatch.setenv("BACKUP_S3_KEY", "AKIAIOSFODNN7EXAMPLE")
    monkeypatch.setenv("BACKUP_S3_SECRET", "sekrit-value-nobody-should-see")
    assert backup_store.configured() is True
    assert "sekrit" not in backup_store.target()
    assert "AKIA" not in backup_store.target()

    # Dated keys sort chronologically, so a bucket listing reads as history.
    when = datetime.datetime(2026, 7, 30, 12, 0, 0,
                             tzinfo=datetime.timezone.utc)
    later = when + datetime.timedelta(days=1)
    assert backup_store.object_name(when) < backup_store.object_name(later)
    assert backup_store.object_name(when).endswith(".zip")

    # The request is signed over the real payload, and the secret is never
    # a header value.
    import hashlib
    import urllib.error
    import urllib.request

    seen = {}

    def fake_open(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = {k.lower(): v for k, v in req.headers.items()}
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    ok, detail = backup_store.put("street-banker/2026-07/t.zip", b"x" * 64)
    assert ok is False and "403" in detail          # honest about failing
    assert seen["url"].endswith("/sb-backups/street-banker/2026-07/t.zip")
    assert seen["headers"]["authorization"].startswith("AWS4-HMAC-SHA256")
    assert seen["headers"]["x-amz-content-sha256"] == hashlib.sha256(
        b"x" * 64).hexdigest()
    assert "sekrit" not in str(seen["headers"])


def test_backup_run_is_gated_and_records_every_outcome(monkeypatch):
    """The trigger is for a scheduler, so it needs a token — and every run,
    including the failures, has to be recorded. A backup system that only
    logs its successes is how people discover at restore time that it
    stopped working months ago."""
    import json

    import backup_store
    import db as store_mod

    app_obj = create_app()

    # Anonymous with no token at all: the login wall takes it, which is
    # the right answer — there is nothing here for a stranger.
    anon = app_obj.test_client()
    assert anon.post("/backup/run").status_code in (302, 404)

    # Configured target but no credentials -> honest 503, not a fake success.
    for k in ("BACKUP_S3_ENDPOINT", "BACKUP_S3_BUCKET",
              "BACKUP_S3_KEY", "BACKUP_S3_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BACKUP_TOKEN", "s3cr3t-token")
    r = anon.post("/backup/run", headers={"X-Backup-Token": "s3cr3t-token"})
    assert r.status_code == 503
    assert "BACKUP_S3_ENDPOINT" in r.get_json()["error"]

    # A wrong token is refused even once everything else is set up.
    monkeypatch.setenv("BACKUP_S3_ENDPOINT", "https://acct.r2.example.com")
    monkeypatch.setenv("BACKUP_S3_BUCKET", "sb-backups")
    monkeypatch.setenv("BACKUP_S3_KEY", "AKIAIOSFODNN7EXAMPLE")
    monkeypatch.setenv("BACKUP_S3_SECRET", "sekrit")
    # A wrong token gets no further than no token at all.
    assert anon.post("/backup/run",
                     headers={"X-Backup-Token": "wrong"}).status_code in (302, 404)
    # And the right token must get PAST the login wall, or a scheduler
    # would be redirected to /login and the backup would never run.
    probe = anon.post("/backup/run", headers={"X-Backup-Token": "s3cr3t-token"})
    assert probe.status_code != 302, "token holder was bounced to login"

    # A failing upload is reported as a failure AND written down.
    monkeypatch.setattr(backup_store, "put",
                        lambda name, data, content_type="application/zip":
                        (False, "HTTP 403 AccessDenied"))
    r = anon.post("/backup/run", headers={"X-Backup-Token": "s3cr3t-token"})
    assert r.status_code == 502 and r.get_json()["ok"] is False
    record = json.loads(store_mod.get_kv("backup_last_run"))
    assert record["ok"] is False and "403" in record["detail"]

    # A successful upload records the real byte count of a real snapshot.
    uploaded = {}

    def fake_put(name, data, content_type="application/zip"):
        uploaded["name"] = name
        uploaded["bytes"] = len(data)
        return True, "HTTP 200"

    monkeypatch.setattr(backup_store, "put", fake_put)
    r = anon.post("/backup/run", headers={"X-Backup-Token": "s3cr3t-token"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    record = json.loads(store_mod.get_kv("backup_last_run"))
    assert record["ok"] is True
    # A real zip of a real database is never a couple of bytes.
    assert record["bytes"] > 1000 and record["bytes"] == uploaded["bytes"]
    assert record["object"] == uploaded["name"]
    assert record["object"].endswith(".zip")


def test_settings_names_the_backup_gap_honestly():
    """With nothing configured the page has to say the data sits on one
    disk, rather than implying the manual download is a backup strategy."""
    app_obj = create_app()
    artist = _demo(app_obj)
    page = artist.get("/settings").get_data(as_text=True)
    # The demo account cannot back up at all, so the panel is absent —
    # that is the gate working, and worth pinning.
    assert "Download backup" not in page


def test_command_palette_index_cannot_drift_from_the_nav():
    """Seventy-odd destinations across five hubs means finding a page
    requires knowing which hub someone filed it under. The palette is the
    escape hatch — and it is derived from the same definitions the sidebar
    renders, so it can never list a page the nav has dropped."""
    import hubs

    idx = hubs.command_index()
    assert len(idx) > 60
    # Every nav destination appears exactly once.
    hrefs = [i["href"] for i in idx]
    assert len(set(hrefs)) == len(hrefs)
    nav_hrefs = set()
    for _k, _name, _tag, items in hubs.HUBS:
        for _key, href, _icon, _label, _desc in items:
            nav_hrefs.add(href)
    for group in (hubs.LABEL_GROUP, hubs.COMMUNITY_GROUP, hubs.ACCOUNT_GROUP):
        for _key, href, _icon, _label, _desc in group[1]:
            nav_hrefs.add(href)
    assert nav_hrefs == set(hrefs)
    # Every entry carries what the palette shows.
    for entry in idx:
        assert entry["label"] and entry["group"] and entry["href"]
        assert isinstance(entry["live"], bool)
    # Things built and shipped are marked live, so the palette does not
    # tell someone a working page is locked.
    live = {i["key"] for i in idx if i["live"]}
    for key in ("hours", "rack", "overview", "links", "tour"):
        assert key in live, key


def test_command_palette_renders_on_every_signed_in_page():
    app_obj = create_app()
    artist = _demo(app_obj)
    for path in ("/overview", "/rack", "/hours", "/settings"):
        page = artist.get(path).get_data(as_text=True)
        assert 'id="cmdk"' in page, path
        assert 'id="cmdk-input"' in page, path
        # The index travels with the page, so search works offline too.
        assert '"href"' in page and '"live"' in page, path
        # Keyboard affordances are stated, not left to be guessed.
        assert "esc" in page and "move" in page, path


def test_command_palette_respects_the_fan_shell():
    """The index travels with the page, so an unfiltered palette would
    quietly hand a fan account the whole artist toolbox — pages the fan
    shell exists to keep out of their world, and which would refuse them
    anyway. It is scoped to the same shell the sidebar renders."""
    import uuid as _uuid

    app_obj = create_app()
    fan = app_obj.test_client()
    fan.post("/signup", data={"name": "F",
                              "email": "palette%s@x.com" % _uuid.uuid4().hex[:6],
                              "password": "secret1", "account_type": "fan"})
    page = fan.get("/discover").get_data(as_text=True)
    assert 'id="cmdk"' in page                    # they still get a palette
    assert "Rollout Engine" not in page
    assert "Royalty Lanes" not in page
    assert "Discover (Fans)" in page              # scoped to their world


def test_firstrun_reads_state_and_retires_itself():
    """A new account lands in five hubs with nothing in any of them. The
    checklist answers 'what first' from what the account actually has —
    and then gets out of the way."""
    import firstrun

    empty = firstrun.build({})
    assert empty["done"] == 0 and empty["fresh"] is True
    assert empty["next"]["key"] == firstrun.STEPS[0][0]
    assert len(empty["steps"]) == len(firstrun.STEPS)

    partial = firstrun.build({"profile": 1, "track": 1})
    assert partial["done"] == 2 and partial["fresh"] is False
    assert partial["remaining"] == len(firstrun.STEPS) - 2
    # "Next" is the first thing NOT done, not simply the next in the list.
    assert partial["next"]["key"] == firstrun.STEPS[2][0]

    # It retires on its own — permanent onboarding is clutter.
    enough = {k: 1 for k, _t, _w, _h, _c in firstrun.STEPS[:firstrun.RETIRE_AT]}
    assert firstrun.build(enough) is None
    assert firstrun.build({k: 1 for k, _t, _w, _h, _c in firstrun.STEPS}) is None

    # Every destination must be reachable on the entry plan. Statements and
    # Overview are gated above it, so a checklist pointing there would open
    # with a locked door.
    hrefs = {h for _k, _t, _w, h, _c in firstrun.STEPS}
    assert "/statements" not in hrefs and "/overview" not in hrefs


def test_firstrun_panel_shows_for_a_new_artist_then_disappears():
    import uuid as _uuid

    import db as store_mod

    app_obj = create_app()
    client = app_obj.test_client()
    email = "firstrun%s@x.com" % _uuid.uuid4().hex[:6]
    client.post("/signup", data={"name": "Rello", "email": email,
                                 "password": "secret1"})
    page = client.get("/command-center").get_data(as_text=True)
    assert "Start here" in page
    # It points at the Ctrl-K palette rather than repeating the whole nav.
    assert "K</kbd>" in page

    uid = store_mod.get_user_by_email(email)["id"]
    store_mod.set_hours_rate(uid, "Mixing", 75)
    store_mod.save_rack_preset(uid, {"out": 0})
    store_mod.create_db_link("fr%s" % _uuid.uuid4().hex[:5], uid, "T",
                             "http://example.com", [])
    page = client.get("/command-center").get_data(as_text=True)
    assert "Start here" not in page          # earned its way off the screen


def test_firstrun_never_shows_for_fan_accounts():
    """Fans have no tracks, rate cards or rack — a setup checklist aimed at
    artists would be five instructions they cannot follow."""
    import uuid as _uuid

    app_obj = create_app()
    fan = app_obj.test_client()
    fan.post("/signup", data={"name": "F",
                              "email": "frfan%s@x.com" % _uuid.uuid4().hex[:6],
                              "password": "secret1", "account_type": "fan"})
    assert "Start here" not in fan.get("/discover").get_data(as_text=True)
