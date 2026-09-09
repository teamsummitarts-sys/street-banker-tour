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


def test_reach_database_is_separate_from_v2_database(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})
    client.get("/reach")

    from reach import db as reach_db

    assert os.path.basename(reach_db.current_path()) == "reach.db"
    assert reach_db.current_path() != os.environ["DATABASE_PATH"]
