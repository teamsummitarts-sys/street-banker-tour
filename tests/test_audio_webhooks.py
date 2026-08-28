"""The inbound edge: signature, dedup, and who a webhook is allowed to touch.

This endpoint sits under /webhooks/, which is a PUBLIC prefix - the login wall
does not stand in front of it, by design, because the vendor calling it has no
session. Everything that keeps it safe is in the route itself, so it is tested
against the real app over real HTTP rather than by calling the handler.
"""
import hashlib
import hmac
import json
import uuid

import pytest

import audio_store as astore

SECRET = "test-signing-secret"


@pytest.fixture(scope="module")
def application():
    import app as appmod
    return appmod.create_app()


@pytest.fixture
def hook(application, monkeypatch):
    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("MOCK_WEBHOOK_SECRET", SECRET)
    return application.test_client()


def _sign(body):
    return hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _body(**kw):
    payload = {"type": "job.completed"}
    payload.update(kw)
    return json.dumps(payload).encode("utf-8")


def _post(client, body, signature=None, event_id=None, provider="mock"):
    headers = {"X-Signature": signature if signature is not None else _sign(body)}
    if event_id:
        headers["X-Event-Id"] = event_id
    return client.post("/webhooks/audio/%s" % provider, data=body,
                       content_type="application/json", headers=headers)


# --- the endpoint should not admit it exists -------------------------------

def test_disabled_feature_is_a_404(application, monkeypatch):
    monkeypatch.delenv("AUDIO_INTELLIGENCE_ENABLED", raising=False)
    monkeypatch.setenv("MOCK_WEBHOOK_SECRET", SECRET)
    body = _body(job_id="x")
    assert _post(application.test_client(), body).status_code == 404


def test_missing_signing_secret_is_a_404_not_a_401(application, monkeypatch):
    """Whether a secret is configured is not a stranger's business."""
    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.delenv("MOCK_WEBHOOK_SECRET", raising=False)
    body = _body(job_id="x")
    assert _post(application.test_client(), body).status_code == 404


def test_unknown_provider_is_a_404(hook):
    assert _post(hook, _body(job_id="x"), provider="notavendor").status_code == 404


# --- the signature ---------------------------------------------------------

def test_a_bad_signature_is_rejected(hook):
    assert _post(hook, _body(job_id="x"), signature="deadbeef").status_code == 401


def test_a_missing_signature_is_rejected(hook):
    assert _post(hook, _body(job_id="x"), signature="").status_code == 401


def test_a_valid_signature_for_different_bytes_is_rejected(hook):
    """The check must run over the RAW body. A payload that was decoded and
    re-encoded is no longer the bytes that were signed."""
    signed = _body(job_id="legitimate")
    tampered = _body(job_id="attacker-supplied")
    assert _post(hook, tampered, signature=_sign(signed)).status_code == 401


def test_a_good_signature_is_accepted(hook):
    assert _post(hook, _body(job_id="unknown-but-signed")).status_code == 200


def test_a_rejected_delivery_is_recorded_for_admin(hook, application):
    """A run of bad signatures should be visible to a person, not only in a
    log nobody reads."""
    marker = "ext-%s" % uuid.uuid4().hex[:8]
    _post(hook, _body(job_id=marker), signature="deadbeef")
    with application.app_context():
        events = astore.list_webhook_events(limit=50)
    assert any(not e["signature_valid"] for e in events)


# --- duplicates ------------------------------------------------------------

def test_a_repeated_delivery_does_no_work_twice(hook):
    """Vendors retry. A repeat means they did not hear our 200."""
    eid = "evt-%s" % uuid.uuid4().hex[:8]
    body = _body(job_id="dup-test", id=eid)

    first = _post(hook, body, event_id=eid)
    second = _post(hook, body, event_id=eid)

    assert first.status_code == 200
    assert not (first.get_json() or {}).get("duplicate")
    assert (second.get_json() or {}).get("duplicate") is True


# --- tenancy ---------------------------------------------------------------

def test_the_payload_cannot_nominate_its_own_tenant(hook, application, monkeypatch):
    """A webhook that could name its own partner_id could write into any
    tenant on the instance. The tenant comes from OUR row, matched on an id we
    issued, and the body gets no say."""
    monkeypatch.setenv("SIGNAL_AUDIO_BRIEFS_ENABLED", "1")
    import audio_jobs as aj
    import audio_providers as ap

    with application.app_context():
        sub = aj.submit("signal_briefs", "tenant-test-user", ap.SpeechRequest("Brief."))
        assert sub.allowed
        job_id = sub.job["id"]
        provider_job_id = sub.job["provider_job_id"]

        # A delivery that names a different tenant, correctly signed.
        body = _body(job_id=provider_job_id, partner_id="some-other-partner",
                     id="evt-%s" % uuid.uuid4().hex[:8])
        resp = _post(hook, body)
        assert resp.status_code == 200

        # The job is still where it was, under the tenant that created it.
        row = astore.get_job(None, job_id)
        assert row is not None, "the job left the tenant that owns it"
        assert row["partner_id"] is None


def test_an_unknown_provider_job_id_is_not_an_error(hook):
    """Not ours, or already cleaned up. Vendors should not be made to retry
    something that will never match."""
    resp = _post(hook, _body(job_id="nothing-we-ever-issued"))
    assert resp.status_code == 200
    assert (resp.get_json() or {}).get("advanced") == []


# --- the wall this endpoint sits beside ------------------------------------

def test_registering_the_webhook_did_not_open_the_login_wall(application):
    """A blueprint registered into create_app once landed between
    @app.before_request and plan_gate, and the entire login wall came off.
    It is cheap to keep asking."""
    client = application.test_client()
    for path in ("/overview", "/admin", "/settings"):
        resp = client.get(path)
        assert resp.status_code in (301, 302), "%s served without a session" % path
        assert "/login" in (resp.headers.get("Location") or "")

    names = [f.__name__ for f in application.before_request_funcs.get(None, [])]
    assert "plan_gate" in names, "plan_gate is no longer a before_request handler"
