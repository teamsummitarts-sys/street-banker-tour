import os
import tempfile
from types import SimpleNamespace


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-watch-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")
    import app as app_module
    return app_module.create_app().test_client()


def _unlock(client):
    client.post("/reach/unlock", data={"key": "test-reach-key"})


def _artist_with_comparables(client):
    response = client.post(
        "/reach/artist-profile",
        json={
            "artist_name": "Watch Test Artist",
            "primary_genre": "alternative",
            "microgenres": ["indie electronic"],
            "mood": ["cinematic"],
            "language": "en",
            "comparable_artists": ["Reference One", "Reference Two"],
        },
    )
    assert response.status_code == 200
    return response.get_json()["artist_id"]


def test_radar_exposes_comparable_artist_watch(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)
    artist_id = _artist_with_comparables(client)

    page = client.get(f"/reach/opportunities?artist_id={artist_id}")
    assert page.status_code == 200
    assert b"Comparable Artist Watch" in page.data
    assert b"Reference One" in page.data
    assert b"Reference Two" in page.data
    assert b"Search results are signals until REACH verifies the outlet" in page.data


def test_watch_never_uses_fixture_search(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)
    artist_id = _artist_with_comparables(client)

    from reach import comparable_watch
    monkeypatch.setattr(comparable_watch.search_provider, "connected", lambda: False)

    response = client.post(
        "/reach/radar/comparable-watch/run",
        data={"artist_id": artist_id},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"fixture data is never used here" in response.data


def test_watch_records_new_sources_and_deduplicates_weekly_snapshots(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)
    artist_id = _artist_with_comparables(client)

    from reach import comparable_watch
    monkeypatch.setattr(comparable_watch.search_provider, "connected", lambda: True)

    calls = []
    def fake_search(query, limit=10, campaign_id=None):
        calls.append(query)
        if "Reference One" in query:
            items = [
                {"url": "https://examplemusicblog.com/reference-one-review", "title": "Reference One review", "snippet": "A new review of Reference One."},
                {"url": "https://radioexample.org/shows/reference-one", "title": "Reference One on radio", "snippet": "Reference One joins the weekly new music show."},
            ]
        else:
            items = [
                {"url": "https://anotheroutlet.net/features/reference-two", "title": "Reference Two feature", "snippet": "An interview and feature with Reference Two."},
            ]
        return SimpleNamespace(items=items[:limit], mode="LIVE", note=None)

    monkeypatch.setattr(comparable_watch.search_provider, "search", fake_search)

    with client.application.app_context():
        first = comparable_watch.run_now(artist_id)
        assert first["status"] == "SUCCEEDED"
        assert first["new_signals"] == 3
        state = comparable_watch.summary(artist_id)
        assert len(state["new"]) == 3
        assert any(row["signal_kind"] == "PICKUP_SIGNAL" for row in state["new"])

        second = comparable_watch.run_now(artist_id)
        assert second["status"] == "SUCCEEDED"
        assert second["new_signals"] == 0
        all_rows = comparable_watch.signals(artist_id)
        assert len(all_rows) == 3

    assert len(calls) == 8


def test_watch_signal_promotes_only_as_discovered(monkeypatch):
    client = _client(monkeypatch)
    _unlock(client)
    artist_id = _artist_with_comparables(client)

    from reach import campaigns, catalog, comparable_watch, db, profile
    monkeypatch.setattr(comparable_watch.search_provider, "connected", lambda: True)
    monkeypatch.setattr(
        comparable_watch.search_provider,
        "search",
        lambda query, limit=10, campaign_id=None: SimpleNamespace(
            items=[{"url": "https://credibleoutlet.example/story", "title": "Reference One premiere", "snippet": "Reference One premieres a new track."}],
            mode="LIVE",
            note=None,
        ),
    )

    with client.application.app_context():
        artist = db.query_one("SELECT name FROM artist WHERE id = ?", (artist_id,))
        recording_id = catalog.add_track({"title": "Real Release", "artist_name": artist["name"]})
        catalog.attest_rights(recording_id)
        profile_id = profile.get_or_create(recording_id)
        profile.set_field(profile_id, "primary_genre", "alternative")
        profile.set_field(profile_id, "microgenres", ["indie electronic"])
        profile.set_field(profile_id, "mood", ["cinematic"])
        profile.set_field(profile_id, "language", "en")
        profile.set_field(profile_id, "comparable_artists", ["Reference One", "Reference Two"])
        campaign_id = campaigns.create(recording_id, name="Comparable watch campaign")

        comparable_watch.run_now(artist_id)
        signal = comparable_watch.signals(artist_id)[0]
        target_id = comparable_watch.promote(signal["id"], campaign_id)
        target = db.query_one("SELECT * FROM campaign_target WHERE id = ?", (target_id,))
        promoted = db.query_one("SELECT * FROM comparable_watch_signal WHERE id = ?", (signal["id"],))
        assert target["status"] == campaigns.DISCOVERED
        assert "Comparable artist signal" in (target["status_reason"] or "")
        assert promoted["state"] == comparable_watch.PROMOTED
        assert promoted["target_id"] == target_id
