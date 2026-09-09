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



def test_reach_today_and_campaign_hub_present_clear_workflow(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})

    today = client.get("/reach")
    assert today.status_code == 200
    assert b"Today / Operations" in today.data
    assert b"Your next move" in today.data
    assert b"Evidence stays attached" in today.data
    assert b"Human approval required" in today.data
    assert b"reach-wordmark.svg" in today.data
    assert b"Open the platform" in today.data
    assert b"Every REACH workspace stays available" in today.data
    assert b"Campaign Hub" in today.data
    assert b"My Music" in today.data
    assert b"Contacts" in today.data
    assert b"Needs You" in today.data
    assert b'id="reach-mobile-modules-trigger"' in today.data
    assert b'id="reach-mobile-modules"' in today.data
    assert b"Sender Setup" in today.data
    assert b"Connections" in today.data
    assert b"Settings &amp; Safety" in today.data

    hub = client.get("/reach/campaigns")
    assert hub.status_code == 200
    assert b"Campaign Hub" in hub.data
    assert b"No campaigns yet. Start with one release." in hub.data
    assert b"Start a campaign" in hub.data


def test_reach_database_is_separate_from_v2_database(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})
    client.get("/reach")

    from reach import db as reach_db

    assert os.path.basename(reach_db.current_path()) == "reach.db"
    assert reach_db.current_path() != os.environ["DATABASE_PATH"]
