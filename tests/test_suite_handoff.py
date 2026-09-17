"""This suite receives Street Banker's sign-in hand-off (sb_suite_sso).

One account for every suite (owner, 2026-09-17): /auth/street-banker verifies
the short-lived token Street Banker minted, finds or creates the matching
account here by email, and starts the session. No second password, ever.
"""
import uuid

import pytest

import db as store
import sb_suite_sso as sso
from app import app

SECRET = "test-shared-secret-street-banker-suites"
SUITE = "tour"
HOME = sso.suite_home(SUITE)


def _sb_user(plan="pro"):
    tag = uuid.uuid4().hex[:8]
    return {"id": "sb-" + tag, "email": "artist-" + tag + "@example.com", "name": "Handed Artist", "plan": plan}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUITE_SSO_SECRET", SECRET)
    monkeypatch.delenv("SUITE_KEYS", raising=False)
    return app.test_client()


def test_without_the_shared_secret_the_door_says_so(monkeypatch):
    monkeypatch.delenv("SUITE_SSO_SECRET", raising=False)
    r = app.test_client().get("/auth/street-banker?token=x")
    assert r.status_code == 503 and b"not connected" in r.data


def test_a_bare_visit_is_refused_plainly_even_when_unconnected(monkeypatch):
    """The fresh-account walker visits every GET route with no parameters;
    a 5xx there reads as a broken page. No token is a plain refusal on
    every build, whether or not the shared secret is set."""
    monkeypatch.delenv("SUITE_SSO_SECRET", raising=False)
    r = app.test_client().get("/auth/street-banker")
    assert r.status_code == 401 and b"needs a link from Street Banker" in r.data


def test_a_missing_or_tampered_token_is_refused_with_a_way_back(client):
    r = client.get("/auth/street-banker")
    assert r.status_code == 401 and b"Street Banker" in r.data and b"/login" in r.data
    token = sso.issue(_sb_user(), SUITE)
    assert client.get("/auth/street-banker?token=" + token[:-4] + "zzzz").status_code == 401


def test_a_token_for_another_suite_is_refused(client):
    other = "tour" if SUITE != "tour" else "reach"
    r = client.get("/auth/street-banker?token=" + sso.issue(_sb_user(), other))
    assert r.status_code == 401 and b"different suite" in r.data


def test_a_good_token_creates_the_account_and_signs_them_in(client):
    who = _sb_user(plan="pro")
    assert store.get_user_by_email(who["email"]) is None
    r = client.get("/auth/street-banker?token=" + sso.issue(who, SUITE))
    assert r.status_code == 302 and r.headers["Location"].endswith(HOME)
    user = store.get_user_by_email(who["email"])
    assert user and user["name"] == "Handed Artist" and user["plan"] == "pro"
    with client.session_transaction() as s:
        assert s["user_id"] == user["id"] and s["sb_suite_sso"] is True and s["sb_suite"] == SUITE


def test_the_second_visit_reuses_the_same_account(client):
    who = _sb_user()
    client.get("/auth/street-banker?token=" + sso.issue(who, SUITE))
    first = store.get_user_by_email(who["email"])["id"]
    client.get("/auth/street-banker?token=" + sso.issue(who, SUITE))
    assert store.get_user_by_email(who["email"])["id"] == first


def test_next_stays_on_this_service(client):
    who = _sb_user()
    r = client.get("/auth/street-banker?next=//evil.example&token=" + sso.issue(who, SUITE))
    assert r.headers["Location"].endswith(HOME)
    r = client.get("/auth/street-banker?next=%2Fsomewhere%2Flocal&token=" + sso.issue(who, SUITE))
    assert r.headers["Location"].endswith("/somewhere/local")


def test_a_handed_session_survives_closed_mode(client, monkeypatch):
    """Closed mode keeps strangers out of a private build. Somebody Street
    Banker vouched for is not a stranger."""
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("SIGNUP_MODE", "closed")
    monkeypatch.setenv("OWNER_EMAILS", "owner@example.com")
    who = _sb_user()
    client.get("/auth/street-banker?token=" + sso.issue(who, SUITE))
    r = client.get("/overview")
    assert r.status_code == 200 or (r.status_code == 302 and "/login" not in r.headers.get("Location", ""))


def test_the_login_wall_is_street_bankers_once_connected(client, monkeypatch):
    r = client.get("/tours")
    assert r.status_code == 302 and r.headers["Location"] == "https://app.streetbankermusic.com/suites/go/tour"
    monkeypatch.delenv("SUITE_SSO_SECRET", raising=False)
    r = app.test_client().get("/tours")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_a_new_arrival_opens_onto_the_mock_up_tour(client):
    import tour_store as ts
    who = _sb_user()
    client.get("/auth/street-banker?token=" + sso.issue(who, SUITE))
    user = store.get_user_by_email(who["email"])
    tours = ts.list_tours(user["id"])
    assert [t["name"] for t in tours] == ["Mock Up Tour"]
    shows = ts.list_shows(tours[0]["id"])
    assert len(shows) == 36 and len(ts.list_days(tours[0]["id"])) == 45
    assert any(s.get("status") == "confirmed" for s in shows)
    page = client.get("/tours/%s/calendar" % tours[0]["id"]).get_data(as_text=True).lower()
    assert "mock up tour" in page and "prayers" not in page and "devora" not in page
    assert any(s["venue"] == "Bottom Lounge" for s in shows)
    # a second arrival never builds a second copy
    client.get("/auth/street-banker?token=" + sso.issue(who, SUITE))
    assert len(ts.list_tours(user["id"])) == 1


def test_nobody_registers_here_once_street_banker_is_connected(client):
    """Accounts are Street Banker's to give. This suite's own sign-up sends
    people to Street Banker and creates nothing."""
    email = "stranger-%s@example.com" % uuid.uuid4().hex[:8]
    r = client.post("/signup", data={"name": "Stranger", "email": email, "password": "stranger-pass-1"})
    assert r.status_code == 302 and r.headers["Location"] == "https://app.streetbankermusic.com/signup"
    assert store.get_user_by_email(email) is None
