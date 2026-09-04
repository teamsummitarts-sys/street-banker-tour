"""Registration access controls for the isolated V2 comparison service."""

import db as store

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


def test_owner_only_signup_accepts_allowlisted_owner(monkeypatch, tmp_path):
    client = _owner_only_client(monkeypatch, tmp_path)

    response = client.post(
        "/signup",
        data={
            "name": "Owner",
            "email": "owner@example.com",
            "password": "strong-password",
            "account_type": "artist",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/onboarding")
    owner = store.get_user_by_email("owner@example.com")
    assert owner is not None
    assert owner["plan"] == "label"
