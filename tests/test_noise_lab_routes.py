"""Noise Lab's host boundary; no recordings, provider calls or real accounts."""
import pytest
from flask import Flask

from noise_lab import init


def host(enabled=True, user=None):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='isolated-test-secret', NOISE_LAB_ENABLED=enabled,
                      OPENAI_API_KEY='')
    init(app, current_user=lambda: user)
    return app


def test_disabled_module_is_unavailable_even_to_authenticated_users():
    client = host(enabled=False, user={"id": "owner"}).test_client()
    for path in ("/noise-lab/", "/noise-lab/capabilities", "/noise-lab/assets/ui/controller.mjs"):
        assert client.get(path).status_code == 404


def test_anonymous_access_is_denied_including_module_assets():
    client = host().test_client()
    for path in ("/noise-lab/", "/noise-lab/capabilities", "/noise-lab/assets/ui/controller.mjs"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["Cache-Control"] == "no-store"


def test_account_must_have_a_stable_id():
    assert host(user={"email": "test@example.invalid"}).test_client().get("/noise-lab/capabilities").status_code == 401


def test_capabilities_do_not_claim_unbuilt_features():
    response = host(user={"id": "owner"}).test_client().get("/noise-lab/capabilities")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["phase"] == 2
    assert payload["ai_generation"] is False
    assert payload["cloud_patch_storage"] is False
    assert payload["audio_uploads"] is False
    assert payload["device_verification"] == "unverified"
    assert "owner" not in response.get_data(as_text=True)


def test_per_application_identity_does_not_bleed_between_hosts():
    first = host(user={"id": "one"}).test_client()
    second = host(user=None).test_client()
    assert first.get("/noise-lab/capabilities").status_code == 200
    assert second.get("/noise-lab/capabilities").status_code == 401
    assert first.get("/noise-lab/capabilities").status_code == 200


def test_no_recording_upload_and_generation_requires_a_session_token():
    client = host(user={"id": "owner"}).test_client()
    assert client.post("/noise-lab/", data=b"audio").status_code == 405
    assert client.post("/noise-lab/capabilities", json={"user_id": "other"}).status_code == 405
    assert client.post("/noise-lab/api/generate", json={"prompt": "test"}).status_code == 403
    assert client.post("/noise-lab/upload", data=b"audio").status_code == 404


def test_module_does_not_change_host_responses_and_can_be_removed():
    app = host(user={"id": "owner"})
    app.add_url_rule("/existing", view_func=lambda: "existing")
    response = app.test_client().get("/existing")
    assert response.data == b"existing"
    assert "Content-Security-Policy" not in response.headers
    removed = Flask("without_noise_lab")
    removed.add_url_rule("/existing", view_func=lambda: "existing")
    assert removed.test_client().get("/existing").data == b"existing"
    assert removed.test_client().get("/noise-lab/").status_code == 404


def test_page_and_assets_are_private_and_strictly_scoped():
    client = host(user={"id": "owner"}).test_client()
    response = client.get("/noise-lab/")
    assert response.status_code == 200
    assert "Noise Lab" in response.get_data(as_text=True)
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-eval" not in csp
    assert "unsafe-inline" not in csp
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    asset = client.get("/noise-lab/assets/ui/controller.mjs")
    assert asset.status_code == 200
    assert "javascript" in asset.content_type


@pytest.mark.parametrize("value", ["0", "false", "yes", "", None, 0])
def test_non_boolean_or_explicit_string_one_flags_fail_closed(value):
    assert host(enabled=value, user={"id": "one"}).test_client().get("/noise-lab/capabilities").status_code == 404
