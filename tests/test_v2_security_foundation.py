"""Security invariants for the isolated Street Banker V2 foundation.

These tests describe public behavior rather than implementation details.  The
V2 branch must keep them green before feature migration continues.
"""

import uuid

import pytest

from app import create_app


def _email(prefix):
    return "%s-%s@example.net" % (prefix, uuid.uuid4().hex)


def _signup(client, email, password="secure-pass-123", name="V2 Tester"):
    response = client.post(
        "/signup",
        data={"name": name, "email": email, "password": password},
    )
    assert response.status_code == 302


def test_existing_account_team_invite_requires_the_invited_session():
    import db as store

    app = create_app()
    victim_email = _email("team-victim")
    owner_email = _email("team-owner")

    victim = app.test_client()
    _signup(victim, victim_email, name="Invited Member")

    owner = app.test_client()
    _signup(owner, owner_email, name="Team Owner")
    invite = owner.post(
        "/team/invite", data={"email": victim_email, "role": "manager"}
    ).get_json()
    token = invite["link"].split("/team/join/", 1)[1]

    stranger = app.test_client()
    denied = stranger.post("/team/join/" + token)
    assert denied.status_code == 403
    with stranger.session_transaction() as stranger_session:
        assert "user_id" not in stranger_session

    accepted = victim.post("/team/join/" + token)
    assert accepted.status_code == 302
    owner_id = store.get_user_by_email(owner_email)["id"]
    assert any(member["email"] == victim_email for member in store.list_team(owner_id))


def test_existing_account_roster_invite_requires_the_invited_session():
    import db as store

    app = create_app()
    artist_email = _email("roster-artist")
    label_email = _email("roster-label")

    artist = app.test_client()
    _signup(artist, artist_email, name="Roster Artist")

    label = app.test_client()
    _signup(label, label_email, name="Roster Label")
    label_id = store.get_user_by_email(label_email)["id"]
    store.set_user_plan(label_id, "label")
    label.post("/roster/invite", data={"email": artist_email})
    page = label.get("/roster").get_data(as_text=True)
    token = page.split(artist_email, 1)[1].split("/roster/join/", 1)[1].split('"', 1)[0]

    stranger = app.test_client()
    denied = stranger.post("/roster/join/" + token)
    assert denied.status_code == 403
    with stranger.session_transaction() as stranger_session:
        assert "user_id" not in stranger_session

    accepted = artist.post("/roster/join/" + token)
    assert accepted.status_code == 302
    artist_id = store.get_user_by_email(artist_email)["id"]
    assert store.get_roster_member(label_id, artist_id) is not None


def test_real_account_cannot_self_promote_without_checkout(monkeypatch):
    import db as store

    monkeypatch.delenv("ALLOW_UNBILLED_PLAN_SWITCH", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    app = create_app()
    email = _email("plan")
    client = app.test_client()
    _signup(client, email)

    response = client.post("/plan/switch", data={"plan": "label"})
    assert response.status_code == 302
    assert store.get_user_by_email(email)["plan"] == "artist"


def test_database_backup_and_internal_review_are_owner_only(monkeypatch):
    import db as store

    owner_email = _email("owner")
    label_email = _email("label")
    monkeypatch.setenv("OWNER_EMAILS", owner_email)
    app = create_app()

    owner = app.test_client()
    _signup(owner, owner_email)

    label = app.test_client()
    _signup(label, label_email)
    store.set_user_plan(store.get_user_by_email(label_email)["id"], "label")

    assert label.get("/backup").status_code == 404
    assert label.get("/admin/review").status_code == 404
    assert label.get("/presave/diag").status_code == 404
    assert owner.get("/backup").status_code == 200
    assert owner.get("/admin/review").status_code == 200


def test_login_rejects_external_next_destination():
    app = create_app()
    email = _email("redirect")
    password = "secure-pass-123"
    account = app.test_client()
    _signup(account, email, password=password)

    response = app.test_client().post(
        "/login?next=https://example.org/phish",
        data={"email": email, "password": password},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/command-center"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environment_requires_a_session_secret(monkeypatch, environment):
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
