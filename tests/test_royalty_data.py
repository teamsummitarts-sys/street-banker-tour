import pytest

from royalty_data import (
    Kpi,
    Payout,
    PlatformBalance,
    PlatformConnection,
    CLAIM_PIPELINE,
    Alert,
    Finding,
    Recommendation,
    ScheduledPayout,
    Song,
    SplitEntry,
    advance_claim,
    add_split,
    assess_advance_eligibility,
    estimate_catalog_value,
    get_claims,
    get_dashboard_story,
    get_song_splits,
    live_song,
    remove_split,
    reset_split_state,
    toggle_split_confirmed,
    get_missing_royalty_findings,
    get_payout_calendar,
    get_platform_balances,
    get_platform_catalog,
    get_recent_payouts,
    get_kpis,
    get_royalty_leak_alerts,
    get_smart_recommendations,
    get_song,
    get_songs,
    reject_claim,
    reset_claim_state,
    metadata_completion_score,
    registration_checklist_score,
    reset_connection_state,
    royalty_progress,
    set_connection_status,
    song_check_status,
    song_missing_issues,
    split_total_percentage,
    splits_fully_confirmed,
    total_royalties,
    upcoming_payout_total,
    complete_registration_step,
    generate_report,
    get_available_reports,
    get_catalog_value_tracker,
    get_documents_vault,
    get_fixes_queue,
    get_registration_wizard,
    get_rights_conflicts,
    get_royalty_forecast,
    get_since_last_login_summary,
    get_top_royalty_leaks,
    get_upcoming_releases,
    money_left_on_table,
    reset_fix_status_state,
    reset_registration_wizard_state,
    set_fix_status,
    get_action_center,
    get_earnings_trend,
    get_overview_health,
    get_recovery_summary,
    get_since_last_login_summary,
)


def test_total_royalties_empty():
    assert total_royalties([]) == 0


def test_total_royalties_single():
    assert total_royalties([PlatformBalance("Spotify", "Streaming", 100.0)]) == 100.0


def test_total_royalties_multiple():
    balances = [
        PlatformBalance("Spotify", "Streaming", 100.0),
        PlatformBalance("ASCAP", "Performance", 50.5),
    ]
    assert total_royalties(balances) == 150.5


def test_royalty_progress_under_goal():
    assert royalty_progress(5000, 20000) == 0.25


def test_royalty_progress_capped_at_one():
    assert royalty_progress(30000, 20000) == 1.0


def test_royalty_progress_zero_goal():
    assert royalty_progress(100, 0) == 0.0


def test_alerts_processing_payout_is_medium_severity():
    payouts = [Payout("City Lights", "ASCAP", "Processing", 350.0)]
    kpis = [Kpi("Active Streams", "+1", "no pending items here", [1])]
    alerts = get_royalty_leak_alerts([], payouts, kpis, [])
    payout_alerts = [a for a in alerts if "City Lights" in a.title]
    assert len(payout_alerts) == 1
    assert payout_alerts[0].severity == "Medium"
    assert "ASCAP" in payout_alerts[0].resolution_message


def test_alerts_needs_login_platform_is_high_severity():
    catalog = [PlatformConnection("deezer", "Deezer", "Streaming", 200.0, "needs_login")]
    alerts = get_royalty_leak_alerts([], [], [], catalog)
    deezer_alerts = [a for a in alerts if a.source == "Deezer"]
    assert len(deezer_alerts) == 1
    assert deezer_alerts[0].severity == "High"
    assert deezer_alerts[0].estimated_impact == 100.0


def test_alerts_sync_error_platform_is_high_severity():
    catalog = [PlatformConnection("tidal", "Tidal", "Streaming", 95.0, "error")]
    alerts = get_royalty_leak_alerts([], [], [], catalog)
    assert alerts[0].severity == "High"
    assert alerts[0].estimated_impact == 95.0


def test_alerts_not_connected_severity_by_amount():
    catalog = [
        PlatformConnection("big", "Big Platform", "Streaming", 500.0, "not_connected"),
        PlatformConnection("small", "Small Platform", "Streaming", 50.0, "not_connected"),
    ]
    alerts = get_royalty_leak_alerts([], [], [], catalog)
    by_source = {a.source: a for a in alerts}
    assert by_source["Big Platform"].severity == "Medium"
    assert by_source["Small Platform"].severity == "Low"


def test_alerts_pending_kpi_is_low_severity():
    kpis = [Kpi("Sync Licenses", "1", "1 pending negotiation", [1])]
    alerts = get_royalty_leak_alerts([], [], kpis, [])
    matches = [a for a in alerts if "needs review" in a.title.lower()]
    assert len(matches) == 1
    assert matches[0].severity == "Low"


def test_alerts_fallback_when_nothing_applies():
    alerts = get_royalty_leak_alerts([], [], [], [])
    assert len(alerts) == 1
    assert alerts[0].id == "scan"


def test_alerts_sorted_high_severity_first():
    catalog = [
        PlatformConnection("a", "A", "Streaming", 50.0, "not_connected"),
        PlatformConnection("b", "B", "Streaming", 200.0, "error"),
    ]
    alerts = get_royalty_leak_alerts([], [], [], catalog)
    assert alerts[0].severity == "High"


def test_connecting_platform_removes_its_leak_alert():
    try:
        set_connection_status("tidal", "connected")
        alerts = get_royalty_leak_alerts([], [], [], get_platform_catalog())
        assert not any(a.source == "Tidal" for a in alerts)
    finally:
        reset_connection_state()


def test_catalog_includes_all_statuses():
    statuses = {p.status for p in get_platform_catalog()}
    assert statuses == {"connected", "not_connected", "syncing", "needs_login", "error"}


def test_only_connected_platforms_count_toward_balances():
    names = [b.platform for b in get_platform_balances()]
    assert "Spotify" in names
    assert "Tidal" not in names


def test_connecting_platform_adds_it_to_balances_and_total():
    try:
        before = total_royalties(get_platform_balances())
        set_connection_status("tidal", "connected")
        balances = get_platform_balances()
        assert "Tidal" in [b.platform for b in balances]
        assert total_royalties(balances) == pytest.approx(before + 95.20)
    finally:
        reset_connection_state()


def test_disconnecting_platform_removes_it():
    try:
        set_connection_status("spotify", "not_connected")
        assert "Spotify" not in [b.platform for b in get_platform_balances()]
    finally:
        reset_connection_state()


def test_set_connection_status_unknown_platform_returns_none():
    assert set_connection_status("not-a-platform", "connected") is None


def test_scan_findings_include_unconnected_source():
    findings = get_missing_royalty_findings(get_platform_catalog())
    yt = [f for f in findings if f.source == "YouTube Music"]
    assert len(yt) == 1
    assert yt[0].issue_type == "Uncollected royalties"
    assert yt[0].recommended_action == "Connect YouTube Music"


def test_scan_findings_have_all_fields_and_valid_confidence():
    for f in get_missing_royalty_findings(get_platform_catalog()):
        assert f.source and f.issue_type and f.recommended_action
        assert f.estimated_value > 0
        assert f.confidence in {"High", "Medium", "Low"}


def test_scan_findings_sorted_by_value_desc():
    values = [f.estimated_value for f in get_missing_royalty_findings(get_platform_catalog())]
    assert values == sorted(values, reverse=True)


def test_connecting_source_clears_its_uncollected_finding():
    try:
        set_connection_status("youtube-music", "connected")
        findings = get_missing_royalty_findings(get_platform_catalog())
        uncollected = [
            f for f in findings
            if f.source == "YouTube Music" and f.issue_type == "Uncollected royalties"
        ]
        assert uncollected == []
    finally:
        reset_connection_state()


def test_connected_source_deep_scan_finding_present():
    findings = get_missing_royalty_findings(get_platform_catalog())
    mlc = [f for f in findings if f.source == "The MLC"]
    assert any(f.issue_type == "Unclaimed mechanical royalties" for f in mlc)


def test_get_songs_returns_expected_titles():
    titles = [s.title for s in get_songs()]
    assert "Midnight Drive" in titles
    assert "City Lights" in titles
    assert len(titles) >= 5


def test_get_song_by_id():
    song = get_song("midnight-drive")
    assert song is not None
    assert song.title == "Midnight Drive"


def test_get_song_unknown_id_returns_none():
    assert get_song("not-a-real-song") is None


def test_split_total_percentage_sums_to_100_when_complete():
    song = next(s for s in get_songs() if s.id == "midnight-drive")
    assert split_total_percentage(song) == 100.0


def test_splits_fully_confirmed_true_when_all_confirmed():
    complete = Song(
        id="x", title="X", isrc="A", iswc="B", upc="C", master_owner="M",
        writers=["W"], producers=["P"], publisher="Pub", lyrics_on_file=True,
        alternate_titles=[], registrations={}, total_earned=0, streams=0,
        platform_earnings={}, splits=[SplitEntry("A", "Writer", 100.0, True)],
        monthly_trend=[],
    )
    assert splits_fully_confirmed(complete) is True


def test_splits_fully_confirmed_false_when_any_unconfirmed():
    partial = Song(
        id="x", title="X", isrc="A", iswc="B", upc="C", master_owner="M",
        writers=["W"], producers=["P"], publisher="Pub", lyrics_on_file=True,
        alternate_titles=[], registrations={}, total_earned=0, streams=0,
        platform_earnings={},
        splits=[SplitEntry("A", "Writer", 50.0, True), SplitEntry("B", "Writer", 50.0, False)],
        monthly_trend=[],
    )
    assert splits_fully_confirmed(partial) is False


def test_splits_fully_confirmed_false_when_no_splits():
    empty = Song(
        id="x", title="X", isrc="A", iswc="B", upc="C", master_owner="M",
        writers=["W"], producers=["P"], publisher="Pub", lyrics_on_file=True,
        alternate_titles=[], registrations={}, total_earned=0, streams=0,
        platform_earnings={}, splits=[], monthly_trend=[],
    )
    assert splits_fully_confirmed(empty) is False


def test_song_check_status_all_true_for_fully_complete_song():
    complete = Song(
        id="x", title="X", isrc="A", iswc="B", upc="C", master_owner="M",
        writers=["W"], producers=["P"], publisher="Pub", lyrics_on_file=True,
        alternate_titles=["Alt"],
        registrations={
            "distribution": True, "pro": True, "mlc": True,
            "soundexchange": True, "youtube_content_id": True, "tiktok_meta_rights": True,
        },
        total_earned=0, streams=0, platform_earnings={},
        splits=[SplitEntry("A", "Writer", 100.0, True)], monthly_trend=[],
    )
    status = song_check_status(complete)
    assert all(status.values())
    assert song_missing_issues(complete) == []
    assert metadata_completion_score(complete) == 1.0
    assert registration_checklist_score(complete) == 1.0


def test_song_check_status_empty_song_all_false():
    empty = Song(
        id="x", title="X", isrc=None, iswc=None, upc=None, master_owner="M",
        writers=[], producers=[], publisher=None, lyrics_on_file=False,
        alternate_titles=[], registrations={}, total_earned=0, streams=0,
        platform_earnings={}, splits=[], monthly_trend=[],
    )
    status = song_check_status(empty)
    assert not any(status.values())
    assert len(song_missing_issues(empty)) == len(status)
    assert metadata_completion_score(empty) == 0.0
    assert registration_checklist_score(empty) == 0.0


def test_metadata_and_registration_scores_within_range():
    for song in get_songs():
        assert 0.0 <= metadata_completion_score(song) <= 1.0
        assert 0.0 <= registration_checklist_score(song) <= 1.0


def test_payout_calendar_sorted_by_date():
    calendar = get_payout_calendar()
    dates = [p.pay_date for p in calendar]
    assert dates == sorted(dates)


def test_payout_calendar_has_all_statuses():
    statuses = {p.status for p in get_payout_calendar()}
    assert statuses == {"Paid", "Processing", "Scheduled", "Delayed"}


def test_upcoming_payout_total_excludes_paid_and_delayed():
    payouts = [
        ScheduledPayout("a", "Spotify", 100.0, None, "Scheduled"),
        ScheduledPayout("b", "ASCAP", 50.0, None, "Processing"),
        ScheduledPayout("c", "BMI", 999.0, None, "Paid"),
        ScheduledPayout("d", "SESAC", 999.0, None, "Delayed"),
    ]
    assert upcoming_payout_total(payouts) == 150.0


def test_get_claims_start_as_detected():
    try:
        claims = get_claims(get_platform_catalog())
        assert len(claims) > 0
        assert all(c.status == "Detected" for c in claims)
    finally:
        reset_claim_state()


def test_get_claims_sorted_by_value_desc():
    values = [c.estimated_value for c in get_claims(get_platform_catalog())]
    assert values == sorted(values, reverse=True)


def test_advance_claim_moves_through_pipeline():
    try:
        catalog = get_platform_catalog()
        claim_id = get_claims(catalog)[0].id
        for expected in CLAIM_PIPELINE[1:]:
            new_status = advance_claim(claim_id, catalog)
            assert new_status == expected
    finally:
        reset_claim_state()


def test_advance_claim_stays_at_paid():
    try:
        catalog = get_platform_catalog()
        claim_id = get_claims(catalog)[0].id
        for _ in range(len(CLAIM_PIPELINE) + 3):
            advance_claim(claim_id, catalog)
        assert advance_claim(claim_id, catalog) == "Paid"
    finally:
        reset_claim_state()


def test_advance_unknown_claim_returns_none():
    assert advance_claim("not-a-real-claim", get_platform_catalog()) is None


def test_reject_claim_sets_rejected():
    try:
        catalog = get_platform_catalog()
        claim_id = get_claims(catalog)[0].id
        assert reject_claim(claim_id, catalog) == "Rejected"
        assert get_claims(catalog)[0].status == "Rejected" or any(
            c.id == claim_id and c.status == "Rejected" for c in get_claims(catalog)
        )
    finally:
        reset_claim_state()


def test_reject_claim_does_not_override_paid():
    try:
        catalog = get_platform_catalog()
        claim_id = get_claims(catalog)[0].id
        for _ in range(len(CLAIM_PIPELINE)):
            advance_claim(claim_id, catalog)
        assert reject_claim(claim_id, catalog) == "Paid"
    finally:
        reset_claim_state()


def test_reject_unknown_claim_returns_none():
    assert reject_claim("not-a-real-claim", get_platform_catalog()) is None


def test_smart_recommendations_sorted_by_value_desc():
    alerts = [
        Alert("a1", "Small alert", "d", "Low", "SrcA", 50.0, "Fix", "done"),
        Alert("a2", "Big alert", "d", "High", "SrcB", 900.0, "Fix", "done"),
    ]
    recs = get_smart_recommendations(alerts, [])
    values = [r.estimated_value for r in recs]
    assert values == sorted(values, reverse=True)
    assert recs[0].reason == "Big alert"


def test_smart_recommendations_includes_unconfirmed_split_risk():
    song = Song(
        id="x", title="X", isrc="A", iswc="B", upc="C", master_owner="M",
        writers=["W"], producers=["P"], publisher="Pub", lyrics_on_file=True,
        alternate_titles=[], registrations={}, total_earned=5000.0, streams=0,
        platform_earnings={},
        splits=[SplitEntry("A", "Writer", 50.0, True), SplitEntry("B", "Writer", 50.0, False)],
        monthly_trend=[],
    )
    recs = get_smart_recommendations([], [song])
    assert len(recs) == 1
    assert recs[0].estimated_value == 5000.0
    assert recs[0].target_type == "song"
    assert recs[0].target_id == "x"


def test_smart_recommendations_excludes_fully_confirmed_and_empty_splits():
    confirmed = Song(
        id="c", title="C", isrc="A", iswc="B", upc="C", master_owner="M",
        writers=[], producers=[], publisher=None, lyrics_on_file=False,
        alternate_titles=[], registrations={}, total_earned=999.0, streams=0,
        platform_earnings={}, splits=[SplitEntry("A", "Writer", 100.0, True)],
        monthly_trend=[],
    )
    no_splits = Song(
        id="n", title="N", isrc="A", iswc="B", upc="C", master_owner="M",
        writers=[], producers=[], publisher=None, lyrics_on_file=False,
        alternate_titles=[], registrations={}, total_earned=999.0, streams=0,
        platform_earnings={}, splits=[], monthly_trend=[],
    )
    assert get_smart_recommendations([], [confirmed, no_splits]) == []


def test_smart_recommendations_respects_limit():
    alerts = [
        Alert(f"a{i}", f"Alert {i}", "d", "Low", "Src", float(100 - i), "Fix", "done")
        for i in range(10)
    ]
    assert len(get_smart_recommendations(alerts, [], limit=3)) == 3


def test_estimate_catalog_value_orders_low_mid_high():
    result = estimate_catalog_value([("Jan", 1000.0), ("Feb", 1000.0)])
    assert result["low"] < result["mid"] < result["high"]
    assert result["annual_run_rate"] == 12000.0


def test_estimate_catalog_value_uses_custom_multiples():
    result = estimate_catalog_value([("Jan", 1000.0)], multiples={"low": 2, "mid": 4, "high": 6})
    assert result["low"] == 24000.0
    assert result["mid"] == 48000.0
    assert result["high"] == 72000.0


def test_estimate_catalog_value_empty_trend_is_zero():
    result = estimate_catalog_value([])
    assert result["annual_run_rate"] == 0
    assert result["mid"] == 0


def test_advance_eligibility_strong_signals_yield_eligible():
    trend = [("Jan", 1000.0), ("Feb", 1500.0), ("Mar", 2000.0), ("Apr", 2500.0), ("May", 3000.0), ("Jun", 3500.0)]
    payouts = [ScheduledPayout("1", "Spotify", 100.0, None, "Paid") for _ in range(5)]
    result = assess_advance_eligibility(trend, payouts, catalog_value_mid=200000.0, total_royalties_collected=25000.0)
    assert result["tier"] == "Eligible"
    assert result["score"] >= 70
    assert result["suggested_advance"] > 0


def test_advance_eligibility_weak_signals_yield_not_eligible():
    trend = [("Jan", 1000.0), ("Feb", 1000.0)]
    payouts = [ScheduledPayout("1", "Spotify", 100.0, None, "Delayed") for _ in range(5)]
    result = assess_advance_eligibility(trend, payouts, catalog_value_mid=1000.0, total_royalties_collected=0.0)
    assert result["tier"] == "Not yet eligible"
    assert result["score"] < 45


def test_advance_eligibility_no_data_does_not_crash():
    result = assess_advance_eligibility([], [], catalog_value_mid=0.0, total_royalties_collected=0.0)
    assert result["score"] == 0
    assert result["tier"] == "Not yet eligible"


def test_add_split_appends_unconfirmed_entry():
    try:
        splits = add_split("midnight-drive", "New Collaborator", "Mixer", 15.0)
        assert splits[-1].collaborator == "New Collaborator"
        assert splits[-1].confirmed is False
        assert len(get_song_splits("midnight-drive")) == 4
    finally:
        reset_split_state()


def test_add_split_unknown_song_returns_none():
    assert add_split("not-a-real-song", "X", "Writer", 100.0) is None


def test_remove_split_by_index():
    try:
        add_split("midnight-drive", "Temp", "Mixer", 10.0)
        splits = remove_split("midnight-drive", 3)
        assert len(splits) == 3
        assert all(s.collaborator != "Temp" for s in splits)
    finally:
        reset_split_state()


def test_toggle_split_confirmed_flips_state():
    try:
        splits = toggle_split_confirmed("neon-dreams", 1)
        assert splits[1].confirmed is True
        splits = toggle_split_confirmed("neon-dreams", 1)
        assert splits[1].confirmed is False
    finally:
        reset_split_state()


def test_live_song_reflects_split_overrides():
    try:
        add_split("midnight-drive", "Extra", "Mixer", 5.0)
        song = live_song(get_song("midnight-drive"))
        assert len(song.splits) == 4
        assert song.title == "Midnight Drive"  # untouched fields stay intact
    finally:
        reset_split_state()


def test_split_total_over_100_after_add():
    try:
        add_split("midnight-drive", "Extra", "Mixer", 15.0)
        song = live_song(get_song("midnight-drive"))
        assert split_total_percentage(song) == 115.0
    finally:
        reset_split_state()


def test_reset_split_state_restores_original():
    try:
        add_split("midnight-drive", "Extra", "Mixer", 15.0)
        reset_split_state()
        song = live_song(get_song("midnight-drive"))
        assert len(song.splits) == 3
    finally:
        reset_split_state()


def test_dashboard_story_sums_missing_total():
    findings = [
        Finding("a", "SrcA", "Issue A", 100.0, "High", "Fix A"),
        Finding("b", "SrcB", "Issue B", 50.0, "Medium", "Fix B"),
    ]
    catalog_value = {"low": 1000.0, "mid": 2000.0, "high": 3000.0}
    story = get_dashboard_story(500.0, findings, catalog_value, [])
    assert story["made"] == 500.0
    assert story["missing_total"] == 150.0
    assert story["missing_count"] == 2


def test_dashboard_story_picks_top_finding_and_recommendation():
    findings = [
        Finding("a", "SrcA", "Biggest Issue", 900.0, "High", "Fix A"),
        Finding("b", "SrcB", "Smaller Issue", 50.0, "Medium", "Fix B"),
    ]
    recs = [Recommendation("r1", "Top reason", "High", 900.0, "Do it", "alert", "a")]
    catalog_value = {"low": 1000.0, "mid": 2000.0, "high": 3000.0}
    story = get_dashboard_story(500.0, findings, catalog_value, recs)
    assert story["top_finding"].issue_type == "Biggest Issue"
    assert story["top_recommendation"].reason == "Top reason"


def test_dashboard_story_handles_no_findings_or_recommendations():
    catalog_value = {"low": 0.0, "mid": 0.0, "high": 0.0}
    story = get_dashboard_story(0.0, [], catalog_value, [])
    assert story["missing_total"] == 0.0
    assert story["missing_count"] == 0
    assert story["top_finding"] is None
    assert story["top_recommendation"] is None


def test_dashboard_story_catalog_value_passthrough():
    catalog_value = {"low": 111.0, "mid": 222.0, "high": 333.0}
    story = get_dashboard_story(0.0, [], catalog_value, [])
    assert story["catalog_value_low"] == 111.0
    assert story["catalog_value_mid"] == 222.0
    assert story["catalog_value_high"] == 333.0


def test_money_left_on_table_buckets_by_confidence():
    findings = [
        Finding("a", "SrcA", "Issue A", 100.0, "High", "Fix A"),
        Finding("b", "SrcB", "Issue B", 40.0, "Medium", "Fix B"),
        Finding("c", "SrcC", "Issue C", 10.0, "Low", "Fix C"),
    ]
    result = money_left_on_table(findings)
    assert result == {"high": 100.0, "medium": 40.0, "low": 10.0, "total": 150.0}


def test_get_top_royalty_leaks_respects_limit():
    catalog = get_platform_catalog()
    findings = get_missing_royalty_findings(catalog)
    top = get_top_royalty_leaks(findings, limit=2)
    assert top == findings[:2]


def test_get_fixes_queue_includes_all_categories():
    catalog = get_platform_catalog()
    songs = get_songs()
    findings = get_missing_royalty_findings(catalog)
    items = get_fixes_queue(catalog, songs, findings, limit=50)
    categories = {item.category for item in items}
    assert {"Royalty", "Metadata", "Registration", "Connection"} <= categories
    assert all(item.status == "Open" for item in items)


def test_get_fixes_queue_respects_limit():
    catalog = get_platform_catalog()
    songs = get_songs()
    findings = get_missing_royalty_findings(catalog)
    items = get_fixes_queue(catalog, songs, findings, limit=3)
    assert len(items) == 3


def test_set_fix_status_updates_and_reflects_in_queue():
    catalog = get_platform_catalog()
    songs = get_songs()
    findings = get_missing_royalty_findings(catalog)
    items = get_fixes_queue(catalog, songs, findings, limit=50)
    try:
        set_fix_status(items[0].id, "Complete")
        updated = get_fixes_queue(catalog, songs, findings, limit=50)
        match = next(i for i in updated if i.id == items[0].id)
        assert match.status == "Complete"
    finally:
        reset_fix_status_state()


def test_set_fix_status_rejects_invalid_status():
    assert set_fix_status("some-id", "NotAStatus") is None


def test_get_documents_vault_counts_missing():
    songs = get_songs()
    vault = get_documents_vault(songs)
    velvet_entry = next(e for e in vault["entries"] if e["song"].id == "velvet-static")
    assert velvet_entry["missing_count"] == len(velvet_entry["documents"])
    assert 0.0 <= vault["completeness"] <= 1.0


def test_get_upcoming_releases_have_future_dates():
    from datetime import date
    releases = get_upcoming_releases()
    assert len(releases) >= 1
    assert all(r.release_date > date.today() for r in releases)


def test_get_royalty_forecast_expected_scales_with_horizon():
    trend = [("Jan", 1000.0), ("Feb", 1000.0)]
    forecast = get_royalty_forecast(trend)
    assert forecast["expected"]["90_day"] == pytest.approx(forecast["expected"]["30_day"] * 3)
    assert forecast["expected"]["12_month"] == pytest.approx(forecast["expected"]["30_day"] * 12)


def test_get_catalog_value_tracker_scales_with_multiple():
    trend = [("Jan", 1000.0), ("Feb", 2000.0)]
    low = get_catalog_value_tracker(trend, multiple=12)
    high = get_catalog_value_tracker(trend, multiple=24)
    assert high["current_value"] == pytest.approx(low["current_value"] * 2)
    assert high["available_multiples"] == [12, 15, 18, 24]


def test_get_registration_wizard_reflects_song_registrations():
    song = get_song("midnight-drive")
    wizard = get_registration_wizard(song)
    assert wizard["status"]["pro"] is True
    assert wizard["status"]["tiktok_meta_rights"] is False
    assert "publishing_admin" in wizard["missing"]


def test_complete_registration_step_updates_status():
    try:
        result = complete_registration_step("midnight-drive", "publishing_admin")
        assert result["status"]["publishing_admin"] is True
        assert "publishing_admin" not in result["missing"]
    finally:
        reset_registration_wizard_state()


def test_complete_registration_step_unknown_song_returns_none():
    assert complete_registration_step("not-a-song", "pro") is None


def test_complete_registration_step_unknown_target_returns_none():
    assert complete_registration_step("midnight-drive", "not-a-target") is None


def test_get_available_reports_have_ids_and_labels():
    reports = get_available_reports()
    assert len(reports) == 6
    assert all("id" in r and "label" in r for r in reports)


def test_generate_report_returns_metadata():
    report = generate_report("royalty-report")
    assert report["id"] == "royalty-report"
    assert report["filename"].startswith("royalty-report-")


def test_generate_report_unknown_id_returns_none():
    assert generate_report("not-a-report") is None


def test_get_since_last_login_summary_counts_connection_issues():
    catalog = get_platform_catalog()
    songs = get_songs()
    summary = get_since_last_login_summary(catalog, songs, 5.0)
    expected_issues = sum(1 for p in catalog if p.status in ("needs_login", "error"))
    assert summary["connection_issues"] == expected_issues
    assert summary["catalog_value_change_pct"] == 5.0


def test_get_rights_conflicts_detects_missing_ownership():
    songs = get_songs()
    conflicts = get_rights_conflicts(songs)
    assert any(c.conflict_type == "Missing Ownership Data" and "Velvet Static" in c.title for c in conflicts)


def test_get_rights_conflicts_detects_disputed_publisher():
    songs = get_songs()
    conflicts = get_rights_conflicts(songs)
    assert any(c.conflict_type == "Disputed Publisher Information" for c in conflicts)


def test_get_rights_conflicts_empty_catalog():
    assert get_rights_conflicts([]) == []


def test_get_recovery_summary_matches_money_left_total():
    catalog = get_platform_catalog()
    songs = get_songs()
    trend = get_earnings_trend()
    findings = get_missing_royalty_findings(catalog)
    expected_total = money_left_on_table(findings)["total"]
    summary = get_recovery_summary(catalog, songs, trend)
    assert summary["estimated_uncollected"] == expected_total
    assert summary["flagged_issues"] == len(findings)


def test_get_recovery_summary_sources_sorted_descending():
    catalog = get_platform_catalog()
    songs = get_songs()
    trend = get_earnings_trend()
    summary = get_recovery_summary(catalog, songs, trend)
    amounts = [s["amount"] for s in summary["sources"]]
    assert amounts == sorted(amounts, reverse=True)


def test_get_recovery_summary_chart_ends_at_total():
    catalog = get_platform_catalog()
    songs = get_songs()
    trend = get_earnings_trend()
    summary = get_recovery_summary(catalog, songs, trend)
    assert summary["chart"][-1]["value"] == pytest.approx(summary["estimated_uncollected"])
    assert len(summary["chart"]) == len(trend)


def test_get_recovery_summary_confidence_pct_in_range():
    catalog = get_platform_catalog()
    songs = get_songs()
    trend = get_earnings_trend()
    summary = get_recovery_summary(catalog, songs, trend)
    assert 0 <= summary["confidence_pct"] <= 100


def test_get_overview_health_bars_and_score():
    catalog = get_platform_catalog()
    songs = [live_song(s) for s in get_songs()]
    health = get_overview_health(catalog, songs)
    keys = [b["key"] for b in health["bars"]]
    assert keys == ["connections", "metadata", "registration", "splits"]
    assert 0 <= health["score"] <= 100
    assert all(0 <= b["pct"] <= 100 for b in health["bars"])
    assert all(b["route"].startswith("/") for b in health["bars"])
    assert health["band"] in ("Excellent", "Good", "Fair", "At risk")


def test_get_overview_health_empty_songs():
    catalog = get_platform_catalog()
    health = get_overview_health(catalog, [])
    assert health["bars"][1]["pct"] == 0


def test_get_action_center_routes_and_blend():
    catalog = get_platform_catalog()
    songs = [live_song(s) for s in get_songs()]
    payouts = get_recent_payouts()
    kpis = get_kpis()
    balances = get_platform_balances()
    alerts = get_royalty_leak_alerts(balances, payouts, kpis, catalog)
    items = get_action_center(alerts, payouts, limit=5)
    assert len(items) <= 5
    assert all(i["route"].startswith("/") for i in items)
    assert any(i["kind"] == "success" for i in items)
    connection_alert = next(i for i in items if "login expired" in i["title"] or "sync failure" in i["title"])
    assert connection_alert["route"] == "/connections"


def test_since_last_login_includes_overview_metrics():
    catalog = get_platform_catalog()
    songs = [live_song(s) for s in get_songs()]
    summary = get_since_last_login_summary(catalog, songs, 12.5, 100000)
    assert summary["tasks_completed"] == 5
    assert summary["issues_needing_attention"] >= 0
    assert summary["catalog_value_increase"] == 12500.0


def test_get_royalties_overview_shapes_and_totals():
    from royalty_data import get_royalties_overview, recent_payout_rows, get_payout_calendar
    balances = get_platform_balances()
    catalog = get_platform_catalog()
    trend = get_earnings_trend()
    ov = get_royalties_overview(balances, catalog, get_payout_calendar(), trend, recent_payout_rows())
    s = ov["summary"]
    assert s["total_royalties"] == pytest.approx(total_royalties(balances), abs=0.01)
    assert s["sources_connected"] == sum(1 for p in catalog if p.status == "connected")
    assert s["total_sources"] == len(catalog)
    assert 0 <= sum(r["pct_of_total"] for r in ov["by_source"]) <= 102
    assert all(r["logo"] for r in ov["by_source"])


def test_get_royalties_overview_groups_extra_sources_as_other():
    from royalty_data import get_royalties_overview, recent_payout_rows, get_payout_calendar
    balances = get_platform_balances()
    catalog = get_platform_catalog()
    ov = get_royalties_overview(balances, catalog, get_payout_calendar(), get_earnings_trend(), recent_payout_rows())
    if len(balances) > 7:
        assert ov["by_source"][-1]["name"] == "Other Sources"


def test_platform_logo_key_maps_known_and_unknown():
    from royalty_data import platform_logo_key
    assert platform_logo_key("Spotify") == "spotify"
    assert platform_logo_key("The MLC") == "mlc"
    assert platform_logo_key("Nonexistent Platform") == "other"
