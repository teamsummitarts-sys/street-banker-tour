import os
import tempfile
from datetime import timedelta


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-flight-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")
    import app as app_module
    return app_module.create_app().test_client()


def _unlock(client):
    client.post("/reach/unlock", data={"key": "test-reach-key"})


def _campaign(release_date=None):
    from reach import campaigns, catalog, profile

    recording_id = catalog.add_track({
        "title": "Flight Test",
        "artist_name": "Flight Artist",
        "release_date": release_date,
    })
    catalog.attest_rights(recording_id)
    profile_id = profile.get_or_create(recording_id)
    profile.set_field(profile_id, "primary_genre", "alternative")
    profile.set_field(profile_id, "microgenres", ["indie electronic"])
    profile.set_field(profile_id, "mood", ["cinematic"])
    profile.set_field(profile_id, "language", "en")
    profile.set_field(profile_id, "comparable_artists", ["Reference One"])
    return campaigns.create(recording_id, name="Flight Test Campaign")


def test_flight_plan_uses_known_release_date_and_real_state(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)

    from reach import clock, flight_plan
    release_date = (clock.now().date() + timedelta(days=5)).isoformat()
    campaign_id = _campaign(release_date=release_date)

    plan = flight_plan.build(campaign_id)
    assert plan["stage"] == "Discover"
    assert plan["now"][0]["kind"] == "discover"
    release = next(item for item in plan["upcoming"] if item["kind"] == "release")
    assert release["date"] == release_date
    assert release["days"] == 5
    assert plan["release_date_known"] is True


def test_flight_plan_does_not_invent_missing_dates(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)

    from reach import flight_plan
    campaign_id = _campaign(release_date=None)
    plan = flight_plan.build(campaign_id)

    assert plan["release_date_known"] is False
    assert plan["timing"] == []
    assert plan["upcoming"] == []


def test_urgent_intake_change_becomes_top_campaign_move(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)

    from reach import campaigns, db, entities, intake_monitor, flight_plan
    campaign_id = _campaign()
    outlet_id = entities.ensure_outlet(
        "Deadline Outlet",
        "https://deadline.example/submit",
        "deadline.example",
        "BLOG",
    )
    target_id = campaigns.add_target(
        campaign_id,
        outlet_id,
        status=campaigns.QUALIFIED,
    )
    intake_monitor._ensure_schema()
    snapshot_id = db.new_id("ims")
    db.insert("intake_monitor_snapshot", {
        "id": snapshot_id,
        "tenant_id": campaigns.get(campaign_id)["tenant_id"],
        "target_id": target_id,
        "campaign_id": campaign_id,
        "outlet_id": outlet_id,
        "source_url": "https://deadline.example/submit",
        "fetch_status": "OK",
        "http_status": 200,
        "content_hash": "x",
        "submissions_open": "OPEN",
        "submission_excerpt": "Submissions close September 17, 2030",
        "deadline_date": "2030-09-17",
        "deadline_excerpt": "Submissions close September 17, 2030",
        "route_fingerprint": "route",
        "requirements_fingerprint": "requirements",
        "requires_login": 0,
        "requires_captcha": 0,
        "cost_model": None,
        "cost_amount": None,
        "cost_currency": None,
        "fetched_at": "2030-09-10T12:00:00+00:00",
    })
    event_id = db.new_id("ime")
    db.insert("intake_monitor_event", {
        "id": event_id,
        "tenant_id": campaigns.get(campaign_id)["tenant_id"],
        "target_id": target_id,
        "campaign_id": campaign_id,
        "outlet_id": outlet_id,
        "snapshot_id": snapshot_id,
        "kind": intake_monitor.WINDOW_CLOSED,
        "severity": intake_monitor.URGENT,
        "summary": "Deadline Outlet appears to have closed submissions",
        "before_json": '{"submissions_open":"OPEN"}',
        "after_json": '{"submissions_open":"CLOSED"}',
        "source_url": "https://deadline.example/submit",
        "excerpt": "Submissions are closed.",
        "created_at": "2030-09-10T12:00:00+00:00",
        "acknowledged_at": None,
    })

    plan = flight_plan.build(campaign_id)
    assert plan["now"][0]["kind"] == "intake_event"
    assert plan["now"][0]["target_id"] == target_id
    assert any(item["kind"] == "intake" for item in plan["blockers"])


def test_campaign_overview_renders_flight_plan(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)
    campaign_id = _campaign()

    page = client.get(f"/reach/campaigns/{campaign_id}")
    assert page.status_code == 200
    assert b"Campaign Flight Plan" in page.data
    assert b"Forward plan" in page.data
    assert b"Next 7 days" in page.data
    assert b"No release or campaign dates are on file" in page.data
