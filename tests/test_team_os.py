"""Team OS seat limits and the shared ten-seat roster."""

import db as store

from app import create_app


def _signed_in_owner(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "streetbanker.db"))
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("OWNER_EMAILS", "owner@example.com")
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    app = create_app()
    owner_id = store.create_user("owner@example.com", "Owner", "unused-hash")
    store.set_user_plan(owner_id, "label")
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = owner_id
    return client, owner_id


def test_team_os_renders_exactly_ten_shared_seats(monkeypatch, tmp_path):
    client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)

    response = client.get("/team")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.count("data-team-seat=") == 10
    assert "Ten operating seats" in body
    for label in (
        "Manager", "A&amp;R", "Marketing", "Publicist", "Tour Manager",
        "Accountant", "Attorney", "Creative Director",
        "Producer / Engineer", "Assistant",
    ):
        assert label in body


def test_eleventh_team_invite_is_rejected_and_a_removed_seat_reopens(
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
