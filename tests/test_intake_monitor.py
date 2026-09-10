import os
import tempfile
from types import SimpleNamespace


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-intake-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")
    import app as app_module
    return app_module.create_app().test_client()


def _unlock(client):
    client.post("/reach/unlock", data={"key": "test-reach-key"})


def _campaign_target():
    from reach import campaigns, catalog, contacts, entities, extractor, profile

    recording_id = catalog.add_track({"title": "Monitor Test", "artist_name": "Monitor Artist"})
    catalog.attest_rights(recording_id)
    profile_id = profile.get_or_create(recording_id)
    profile.set_field(profile_id, "primary_genre", "alternative")
    profile.set_field(profile_id, "microgenres", ["indie electronic"])
    profile.set_field(profile_id, "mood", ["cinematic"])
    profile.set_field(profile_id, "language", "en")
    profile.set_field(profile_id, "comparable_artists", ["Reference One"])
    campaign_id = campaigns.create(recording_id, name="Intake monitor campaign")
    outlet_id = entities.ensure_outlet(
        "Monitor Outlet",
        "https://monitor.example/submit",
        "monitor.example",
        "BLOG",
        submissions_open=extractor.OPEN,
        description="Independent music outlet",
    )
    route_id = entities.ensure_route(
        outlet_id,
        contacts.WEB_FORM,
        destination="https://monitor.example/submit",
        verified=True,
    )
    target_id = campaigns.add_target(
        campaign_id,
        outlet_id,
        route_id=route_id,
        status=campaigns.QUALIFIED,
    )
    return campaign_id, target_id


def _result(html):
    return SimpleNamespace(
        final_url="https://monitor.example/submit",
        status=200,
        mime="text/html",
        bytes=len(html.encode()),
        domain="monitor.example",
        robots_decision="ALLOWED",
        text=lambda: html,
    )


def test_explicit_deadline_parser_requires_deadline_language(monkeypatch):
    _client(monkeypatch)
    from reach import intake_monitor

    deadline, excerpt = intake_monitor._deadline(
        "Submissions are open. Closing date October 14, 2030. Send your track."
    )
    assert deadline == "2030-10-14"
    assert "Closing date" in excerpt

    deadline, excerpt = intake_monitor._deadline(
        "Our archive contains an article published October 14, 2030."
    )
    assert deadline is None
    assert excerpt is None


def test_monitor_records_deadline_then_detects_window_and_deadline_change(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)

    from reach import db, intake_monitor
    campaign_id, target_id = _campaign_target()

    first_html = """
    <html><head><title>Monitor Outlet submissions</title></head><body>
      <p>Submissions are open. Deadline October 14, 2030.</p>
      <p>Submit your music using this form.</p>
      <form action='/submit' method='post'><input name='artist'><input name='track'></form>
    </body></html>
    """
    monkeypatch.setattr(intake_monitor.fetcher, "fetch", lambda url: _result(first_html))
    first = intake_monitor.refresh_target(target_id, force=True)
    first_events = [db.query_one("SELECT * FROM intake_monitor_event WHERE id = ?", (eid,)) for eid in first["events"]]
    assert any(row["kind"] == intake_monitor.DEADLINE_FOUND for row in first_events)

    second_html = """
    <html><head><title>Monitor Outlet submissions</title></head><body>
      <p>Submissions are currently closed. Deadline September 30, 2030.</p>
      <p>Please do not send new music while submissions are closed.</p>
      <form action='/new-intake' method='post'><input name='artist'><input name='private_link'></form>
    </body></html>
    """
    monkeypatch.setattr(intake_monitor.fetcher, "fetch", lambda url: _result(second_html))
    second = intake_monitor.refresh_target(target_id, force=True)
    kinds = {
        db.query_one("SELECT kind FROM intake_monitor_event WHERE id = ?", (eid,))["kind"]
        for eid in second["events"]
    }
    assert intake_monitor.WINDOW_CLOSED in kinds
    assert intake_monitor.DEADLINE_CHANGED in kinds
    assert intake_monitor.ROUTE_CHANGED in kinds

    state = intake_monitor.summary()
    assert state["monitored_count"] == 1
    assert state["open_count"] >= 3
    assert state["urgent_count"] >= 1


def test_monitor_acknowledges_without_mutating_target_status(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)

    from reach import campaigns, db, intake_monitor
    _campaign_id, target_id = _campaign_target()
    html = """
    <html><head><title>Monitor Outlet</title></head><body>
      <p>Submissions are open. Submit your music by 2030-10-14.</p>
    </body></html>
    """
    monkeypatch.setattr(intake_monitor.fetcher, "fetch", lambda url: _result(html))
    result = intake_monitor.refresh_target(target_id, force=True)
    assert result["events"]
    event_id = result["events"][0]

    response = client.post(f"/reach/radar/intake-monitor/{event_id}/ack", follow_redirects=False)
    assert response.status_code in (302, 303)
    event = db.query_one("SELECT * FROM intake_monitor_event WHERE id = ?", (event_id,))
    assert event["acknowledged_at"] is not None
    target = campaigns.get_target(target_id)
    assert target["status"] == campaigns.QUALIFIED


def test_radar_renders_intake_monitor(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)

    page = client.get("/reach/opportunities")
    assert page.status_code == 200
    assert b"Deadline + Intake Monitor" in page.data
    assert b"Check now" in page.data
    assert b"submission state, deadlines, routes, costs and requirements" in page.data
