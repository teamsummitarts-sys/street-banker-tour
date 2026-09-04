"""Manager-first Team OS behavior and private collaborator limits."""

import db as store
import hubs
from werkzeug.security import generate_password_hash

from app import create_app


OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "manager-first-pass"


def _signed_in_owner(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "streetbanker.db"))
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    app = create_app()
    owner_id = store.create_user(
        OWNER_EMAIL, "Owner", generate_password_hash(OWNER_PASSWORD))
    store.set_user_plan(owner_id, "label")
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = owner_id
    return client, owner_id


def test_team_os_renders_manager_first_and_ten_operating_members(
        monkeypatch, tmp_path):
    client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)

    response = client.get("/team")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.count("data-agent-seat=") == 10
    assert 'data-manager-primary="true"' in body
    assert body.index("Your Manager") < body.index(
        "Nine specialists behind your manager")
    assert "Your team is already in the room." in body
    for label in (
        "Your Manager", "Your A&amp;R", "Your Marketer", "Your Publicist",
        "Your Tour Manager", "Your Royalty Accountant",
        "Your Rights Attorney", "Your Creative Director", "Your Producer",
        "Your Executive Assistant",
    ):
        assert label in body


def test_team_is_first_navigation_item_and_not_duplicated():
    all_items = [
        item
        for _key, _name, _tagline, items in hubs.HUBS
        for item in items
    ] + list(hubs.ACCOUNT_GROUP[1])

    assert hubs.HUBS[0][0] == "command"
    assert hubs.HUBS[0][3][0][0] == "team"
    assert [item[0] for item in all_items].count("team") == 1


def test_owner_login_lands_on_manager_first_team(monkeypatch, tmp_path):
    client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)
    with client.session_transaction() as session:
        session.clear()

    response = client.post(
        "/login",
        data={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/team")


def test_new_owner_account_enters_through_team(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "new-owner.db"))
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("SIGNUP_MODE", "owner_only")
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/signup",
        data={
            "name": "Owner",
            "email": OWNER_EMAIL,
            "password": OWNER_PASSWORD,
            "account_type": "artist",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/team")


def test_eleventh_human_collaborator_is_rejected_and_removed_seat_reopens(
        monkeypatch, tmp_path):
    client, owner_id = _signed_in_owner(monkeypatch, tmp_path)

    for index in range(10):
        response = client.post(
            "/team/invite",
            data={"email": f"member-{index}@example.com", "role": "manager"},
        )
        assert response.status_code == 200
        assert response.get_json()["ok"] is True

    blocked = client.post(
        "/team/invite",
        data={"email": "member-10@example.com", "role": "manager"},
    )
    assert blocked.status_code == 409
    assert blocked.get_json() == {
        "ok": False,
        "error": "All 10 team seats are filled. Remove a member before inviting someone else.",
    }

    first_member = store.list_team(owner_id)[0]
    removed = client.post(f"/team/{first_member['id']}/remove")
    assert removed.status_code == 200
    assert removed.get_json()["ok"] is True

    reopened = client.post(
        "/team/invite",
        data={"email": "member-10@example.com", "role": "tour_manager"},
    )
    assert reopened.status_code == 200
    assert reopened.get_json()["ok"] is True
