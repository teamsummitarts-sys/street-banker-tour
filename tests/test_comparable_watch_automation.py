import os
import tempfile
from types import SimpleNamespace


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-watch-auto-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")
    monkeypatch.delenv("RENDER", raising=False)
    import app as app_module
    return app_module.create_app().test_client()


def _artist(client):
    client.post("/reach/unlock", data={"key": "test-reach-key"})
    response = client.post(
        "/reach/artist-profile",
        json={
            "artist_name": "Automatic Watch Artist",
            "comparable_artists": ["Reference One", "Reference Two"],
        },
    )
    assert response.status_code == 200
    return response.get_json()["artist_id"]


def test_scheduler_is_off_outside_deployed_render(monkeypatch):
    client = _client(monkeypatch)
    from reach import comparable_watch_scheduler
    assert comparable_watch_scheduler.start(client.application, interval_seconds=1) is None


def test_scheduler_runs_only_due_artist_profiles(monkeypatch):
    client = _client(monkeypatch)
    artist_id = _artist(client)

    from reach import comparable_watch, comparable_watch_scheduler
    monkeypatch.setattr(comparable_watch_scheduler.search_provider, "connected", lambda: True)
    monkeypatch.setattr(comparable_watch.search_provider, "connected", lambda: True)
    monkeypatch.setattr(
        comparable_watch.search_provider,
        "search",
        lambda query, limit=10, campaign_id=None: SimpleNamespace(
            items=[{
                "url": "https://weeklyoutlet.example/" + ("one" if "Reference One" in query else "two"),
                "title": "Comparable artist feature",
                "snippet": "A new music feature.",
            }],
            mode="LIVE",
            note=None,
        ),
    )

    with client.application.app_context():
        first = comparable_watch_scheduler.run_due_once()
        assert first["ran"] == 1
        assert comparable_watch.latest_run(artist_id)["status"] == "SUCCEEDED"
        second = comparable_watch_scheduler.run_due_once()
        assert second["ran"] == 0


def test_signal_stack_ranks_domains_seen_across_multiple_comparables(monkeypatch):
    client = _client(monkeypatch)
    artist_id = _artist(client)

    from reach import comparable_watch, signal_stack
    monkeypatch.setattr(comparable_watch.search_provider, "connected", lambda: True)

    def fake_search(query, limit=10, campaign_id=None):
        if "Reference One" in query:
            url = "https://repeatoutlet.example/reference-one"
            artist = "Reference One"
        else:
            url = "https://repeatoutlet.example/reference-two"
            artist = "Reference Two"
        return SimpleNamespace(
            items=[{
                "url": url,
                "title": f"{artist} review",
                "snippet": f"A review of {artist}.",
            }],
            mode="LIVE",
            note=None,
        )

    monkeypatch.setattr(comparable_watch.search_provider, "search", fake_search)

    with client.application.app_context():
        comparable_watch.run_now(artist_id)
        stack = signal_stack.radar_stack(artist_id)
        assert stack
        assert stack[0]["domain"] == "repeatoutlet.example"
        assert stack[0]["artist_count"] == 2
        assert set(stack[0]["artists"]) == {"Reference One", "Reference Two"}

        reason = signal_stack.reason_for({
            "artists": stack[0]["artists"],
            "sources": [{"url": stack[0]["latest_url"]}],
        })
        assert reason["signal"] == "COMPARABLE_ARTIST_SIGNAL"
        assert "2 artists" in reason["text"]


def test_radar_renders_signal_stack_without_changing_score_copy(monkeypatch):
    client = _client(monkeypatch)
    artist_id = _artist(client)

    from reach import comparable_watch
    monkeypatch.setattr(comparable_watch.search_provider, "connected", lambda: True)
    monkeypatch.setattr(
        comparable_watch.search_provider,
        "search",
        lambda query, limit=10, campaign_id=None: SimpleNamespace(
            items=[{
                "url": "https://stackedoutlet.example/" + ("one" if "Reference One" in query else "two"),
                "title": "New music feature",
                "snippet": "Comparable artist coverage.",
            }],
            mode="LIVE",
            note=None,
        ),
    )
    with client.application.app_context():
        comparable_watch.run_now(artist_id)

    page = client.get(f"/reach/opportunities?artist_id={artist_id}")
    assert page.status_code == 200
    assert b"Signal Stack" in page.data
    assert b"stackedoutlet.example" in page.data
    assert b"Context only" in page.data
    assert b"score unchanged" in page.data
