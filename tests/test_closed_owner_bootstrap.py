"""Cold-start access contract for the private V2 comparison service."""

import db as store
import pytest
from werkzeug.security import generate_password_hash

from app import create_app


OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "private-owner-password"
V2_URL = "https://street-banker-v2-workflows.onrender.com"


def _closed_deployment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "street-banker-v2.db"))
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("SIGNUP_MODE", "closed")
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    monkeypatch.setenv("OWNER_BOOTSTRAP_EMAIL", OWNER_EMAIL)
    monkeypatch.setenv(
        "OWNER_BOOTSTRAP_PASSWORD_HASH",
        generate_password_hash(OWNER_PASSWORD),
    )
    monkeypatch.setenv("SECRET_KEY", "v2-test-secret-with-at-least-32-characters")
    monkeypatch.setenv("PUBLIC_BASE_URL", V2_URL)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    monkeypatch.delenv("RENDER", raising=False)


def test_closed_deployment_bootstraps_only_owner_and_allows_login(
        monkeypatch, tmp_path):
    _closed_deployment(monkeypatch, tmp_path)

    app = create_app()
    users = store.list_users()

    assert len(users) == 1
    assert users[0]["email"] == OWNER_EMAIL
    client = app.test_client()
    response = client.post(
        "/login",
        data={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/team")
    assert client.get("/signup", follow_redirects=False).status_code == 302


@pytest.mark.parametrize(
    ("bootstrap_email", "bootstrap_hash"),
    [
        (None, None),
        (OWNER_EMAIL, None),
        (OWNER_EMAIL, "plaintext-is-never-accepted"),
        (OWNER_EMAIL, "scrypt:" + "x" * 60),
        (OWNER_EMAIL, "pbkdf2:" + "x" * 60),
        (OWNER_EMAIL, "scrypt:32768:8:1$salt$abcdef"),
        (OWNER_EMAIL, "pbkdf2:sha256:1000000$salt$abcdef"),
        ("different@example.com", "valid_hash"),
    ],
)
def test_closed_deployment_fails_before_serving_without_valid_bootstrap(
        monkeypatch, tmp_path, bootstrap_email, bootstrap_hash):
    _closed_deployment(monkeypatch, tmp_path)
    if bootstrap_email is None:
        monkeypatch.delenv("OWNER_BOOTSTRAP_EMAIL", raising=False)
    else:
        monkeypatch.setenv("OWNER_BOOTSTRAP_EMAIL", bootstrap_email)
    if bootstrap_hash is None:
        monkeypatch.delenv("OWNER_BOOTSTRAP_PASSWORD_HASH", raising=False)
    elif bootstrap_hash == "valid_hash":
        monkeypatch.setenv(
            "OWNER_BOOTSTRAP_PASSWORD_HASH",
            generate_password_hash(OWNER_PASSWORD),
        )
    else:
        monkeypatch.setenv("OWNER_BOOTSTRAP_PASSWORD_HASH", bootstrap_hash)

    with pytest.raises(RuntimeError):
        create_app()
