import os
import tempfile


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-v2-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")

    import app as app_module

    return app_module.create_app().test_client()


def test_healthz_is_public(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "service": "street-banker-v2"}


def test_reach_public_landing_and_assets_mount_inside_v2(monkeypatch):
    client = _client(monkeypatch)

    page = client.get("/reach/about")
    assert page.status_code == 200
    assert b"Your release should go" in page.data
    assert b"Illustrative interface" in page.data

    for asset in ("reach-lockup.svg", "reach-wordmark.svg", "reach-mark.svg"):
        response = client.get(f"/reach/static/{asset}")
        assert response.status_code == 200


def test_reach_workspace_keeps_its_access_gate(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/reach", follow_redirects=False)
    assert response.status_code == 302
    assert "/reach/unlock" in response.headers["Location"]

    unlocked = client.post(
        "/reach/unlock",
        data={"key": "test-reach-key", "next": "/reach"},
        follow_redirects=True,
    )
    assert unlocked.status_code == 200
    assert b"Campaign" in unlocked.data


def test_reach_today_and_campaign_hub_present_clear_public_workflow(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})

    today = client.get("/reach")
    assert today.status_code == 200
    assert b"Today / Operations" in today.data
    assert b"Your next move" in today.data
    assert b"reach-wordmark.svg" in today.data
    assert b'id="reach-mobile-modules-trigger"' in today.data
    assert b'id="reach-mobile-modules"' in today.data
    assert b"Artist Profile" in today.data
    assert b"Music" in today.data
    assert b"Relationships" in today.data
    assert b"Tasks" in today.data
    assert b"Plan &amp; Billing" in today.data
    assert b'aria-label="Create campaign"' in today.data

    # Technical/operator surfaces still exist by direct route, but do not read
    # like primary modules in the public artist menu.
    assert b"Advanced &amp; system" not in today.data
    assert b"REACH 1.0.0-phase-one" not in today.data
    assert b"fixture corpus" not in today.data.lower()
    assert b"owner@streetbanker.local" not in today.data

    hub = client.get("/reach/campaigns")
    assert hub.status_code == 200
    assert b"Campaign Hub" in hub.data
    assert b"No campaigns yet. Start with one release." in hub.data
    assert b"Start a campaign" in hub.data


def test_reach_artist_profile_is_a_real_standalone_workspace(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})

    empty = client.get("/reach/artist-profile")
    assert empty.status_code == 200
    assert b"Build your artist once." in empty.data
    assert b"You do not need an EPK" in empty.data
    assert b"Create artist profile" in empty.data

    created = client.post(
        "/reach/artist-profile",
        data={"artist_name": "Real Test Artist", "bio": "A real artist biography."},
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert b"Real Test Artist" in created.data
    assert b"Artist profile saved" in created.data
    assert b"A real artist biography." in created.data
    assert b"Optional Street Banker tools" in created.data

    # Creating another artist must show an intentionally blank profile rather
    # than silently selecting the first one.
    blank_second = client.get("/reach/artist-profile?new=1")
    assert blank_second.status_code == 200
    assert b"Build your artist once." in blank_second.data
    assert b"Create artist profile" in blank_second.data


def test_reach_music_library_hides_fixture_tracks_and_shows_real_releases(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})

    fixture_only = client.get("/reach/catalog")
    assert fixture_only.status_code == 200
    assert b"Add your first release." in fixture_only.data
    assert b"Synthwave Surfer" not in fixture_only.data
    assert b"Digital Paradise" not in fixture_only.data

    from reach import catalog
    with client.application.app_context():
        catalog.add_track({"title": "Real Song", "artist_name": "Real Artist"})

    real_library = client.get("/reach/catalog")
    assert real_library.status_code == 200
    assert b"Real Song" in real_library.data
    assert b"Real Artist" in real_library.data
    assert b"Synthwave Surfer" not in real_library.data
    assert b"Digital Paradise" not in real_library.data


def test_reach_database_is_separate_from_v2_database(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})
    client.get("/reach")

    from reach import db as reach_db

    assert os.path.basename(reach_db.current_path()) == "reach.db"
    assert reach_db.current_path() != os.environ["DATABASE_PATH"]


def test_reach_public_plans_and_private_usage_workspace(monkeypatch):
    client = _client(monkeypatch)

    public = client.get("/reach/plans")
    assert public.status_code == 200
    assert b"Standalone REACH membership" in public.data
    assert b"$29" in public.data
    assert b"two months free" in public.data

    client.post("/reach/unlock", data={"key": "test-reach-key"})
    billing = client.get("/reach/billing")
    assert billing.status_code == 200
    assert b"Current membership" in billing.data
    assert b"Preview" in billing.data
    assert b"Active campaigns" in billing.data
    assert b"Your work stays yours" in billing.data


def test_reach_validation_plan_switch_is_explicitly_env_gated(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})

    denied = client.post("/reach/billing/switch", data={"plan": "solo"})
    assert denied.status_code == 404

    monkeypatch.setenv("REACH_ALLOW_UNBILLED_PLAN_SWITCH", "1")
    changed = client.post(
        "/reach/billing/switch",
        data={"plan": "solo", "interval": "annual"},
        follow_redirects=True,
    )
    assert changed.status_code == 200
    assert b"Solo" in changed.data
    status = client.get("/reach/billing/status").get_json()
    assert status["plan"] == "solo"
    assert status["period"]


def test_reach_preview_limit_blocks_new_mutation_without_deleting_work(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})
    client.get("/reach")

    from reach import catalog, profile

    with client.application.app_context():
        recording = catalog.recordings()[0]
        catalog.attest_rights(recording["id"])
        profile_id = profile.get_or_create(recording["id"])
        profile.set_field(profile_id, "primary_genre", "electronic")
        profile.set_field(profile_id, "microgenres", ["darkwave"])
        profile.set_field(profile_id, "mood", ["cinematic"])
        profile.set_field(profile_id, "language", "en")
        profile.set_field(profile_id, "comparable_artists", ["Reference artist"])

    first = client.post("/reach/campaigns", json={
        "recording_id": recording["id"],
        "name": "First validation campaign",
        "mode": "SCOUT",
    })
    assert first.status_code == 200

    blocked = client.post("/reach/campaigns", json={
        "recording_id": recording["id"],
        "name": "Second validation campaign",
        "mode": "SCOUT",
    })
    assert blocked.status_code == 402
    payload = blocked.get_json()
    assert payload["kind"] == "SUBSCRIPTION_REQUIRED"
    assert payload["upgrade_url"] == "/reach/billing"

    campaigns_page = client.get("/reach/campaigns")
    assert campaigns_page.status_code == 200
    assert b"First validation campaign" in campaigns_page.data


def test_reach_usage_is_persisted_in_its_own_database(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})
    client.get("/reach")

    from reach import subscriptions

    with client.application.app_context():
        assert subscriptions.usage("research_runs") == 0
        subscriptions.increment("research_runs")
        assert subscriptions.usage("research_runs") == 1
        state = subscriptions.dashboard()
        assert state["plan_key"] == "preview"
        assert state["passport"]["verified"] is False
