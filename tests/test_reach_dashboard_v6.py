import os
import tempfile


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-v6-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")
    import app as app_module
    return app_module.create_app().test_client()


def test_v6_media_are_real_binary_images(monkeypatch):
    client = _client(monkeypatch)

    hero = client.get("/reach/static/reach-approved-hero-v6.jpg")
    assert hero.status_code == 200
    assert hero.data[:2] == b"\xff\xd8"
    assert hero.data[-2:] == b"\xff\xd9"
    assert len(hero.data) > 3000

    logo = client.get("/reach/static/reach-approved-logo-v6.png")
    assert logo.status_code == 200
    assert logo.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(logo.data) > 1000


def test_v6_home_uses_compact_mockup_shell(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})

    page = client.get("/reach")
    assert page.status_code == 200
    assert b"dashboard-v6.css" in page.data
    assert b"reach-approved-logo-v6.png" in page.data
    assert b"reach-approved-hero-v6.jpg" in page.data
    assert b"Three moves" in page.data
    assert b"Operating Brief" in page.data
    assert b"Release Passport" in page.data
    assert b"Opportunity Radar" in page.data
    assert b"Campaign Lanes" in page.data
    assert b"Relationship Memory" in page.data
    assert b"Recent Activity" in page.data
    assert b'id="r6-account-popover"' in page.data
    assert b'id="r6-more-sheet"' in page.data
    assert b"r6ToggleAccount" in page.data
    assert b"r6OpenMore" in page.data

    css = client.get("/reach/static/dashboard-v6.css")
    assert css.status_code == 200
    assert b".r6-hero{height:180px" in css.data
    assert b".r6-mid{grid-template-columns:1fr 1fr" in css.data
    assert b".r6-more-sheet" in css.data
    assert b".r6-account-popover" in css.data
