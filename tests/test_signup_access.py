"""Registration access controls for the isolated V2 comparison service."""

import db as store
from werkzeug.security import check_password_hash

from app import create_app


def _owner_only_client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "streetbanker.db"))
    monkeypatch.setenv("SIGNUP_MODE", "owner_only")
    monkeypatch.setenv("OWNER_EMAILS", "owner@example.com")
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    return create_app().test_client()


def test_owner_only_signup_rejects_public_accounts(monkeypatch, tmp_path):
    client = _owner_only_client(monkeypatch, tmp_path)

    response = client.post(
        "/signup",
        data={
            "name": "Public Visitor",
            "email": "visitor@example.com",
            "password": "strong-password",
            "account_type": "artist",
        },
    )

    assert response.status_code == 200
    assert "registration is owner-only" in response.get_data(as_text=True)
    assert store.get_user_by_email("visitor@example.com") is None


def test_owner_only_signup_accepts_allowlisted_owner_without_display_name(
        monkeypatch, tmp_path):
    client = _owner_only_client(monkeypatch, tmp_path)

    response = client.post(
        "/signup",
        data={
            "name": "",
            "email": "owner@example.com",
            "password": "strong-password",
            "account_type": "artist",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/team")
    owner = store.get_user_by_email("owner@example.com")
    assert owner is not None
    assert owner["name"] == "Street Banker"
    assert owner["plan"] == "label"


def test_repeated_owner_entry_signs_existing_owner_in(monkeypatch, tmp_path):
    client = _owner_only_client(monkeypatch, tmp_path)
    first = client.post(
        "/signup",
        data={
            "email": "owner@example.com",
            "password": "strong-password",
            "account_type": "artist",
        },
        follow_redirects=False,
    )
    assert first.status_code == 302
    owner = store.get_user_by_email("owner@example.com")
    original_hash = owner["password_hash"]

    with client.session_transaction() as session:
        session.clear()

    repeated = client.post(
        "/signup",
        data={
            "email": "owner@example.com",
            "password": "strong-password",
            "account_type": "artist",
        },
        follow_redirects=False,
    )

    assert repeated.status_code == 302
    assert repeated.headers["Location"].endswith("/team")
    with client.session_transaction() as session:
        assert session["user_id"] == owner["id"]
    assert store.get_user_by_email("owner@example.com")["password_hash"] == original_hash


def test_repeated_owner_entry_rejects_wrong_password_without_changing_it(
        monkeypatch, tmp_path):
    client = _owner_only_client(monkeypatch, tmp_path)
    client.post(
        "/signup",
        data={
            "email": "owner@example.com",
            "password": "strong-password",
            "account_type": "artist",
        },
    )

    response = client.post(
        "/signup",
        data={
            "email": "owner@example.com",
            "password": "wrong-password",
            "account_type": "artist",
        },
    )

    assert response.status_code == 200
    assert "owner account already exists" in response.get_data(as_text=True)
    owner = store.get_user_by_email("owner@example.com")
    assert check_password_hash(owner["password_hash"], "strong-password")
    assert not check_password_hash(owner["password_hash"], "wrong-password")
