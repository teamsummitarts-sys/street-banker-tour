"""The operator's window: who can open it, and what it must never show.

Two things are worth guarding here beyond "does it render". The page reports
on credentials, so it is a plausible place for one to leak into HTML. And the
sweep button destroys audio, so the default has to be the harmless one.
"""
import os
import uuid

import pytest

import audio_store as astore

SECRET_VALUE = "sk_test_value_that_must_never_reach_a_browser"


@pytest.fixture(scope="module")
def owner_email():
    return "audio-owner-%s@example.net" % uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def application(owner_email):
    os.environ["OWNER_EMAILS"] = owner_email
    import app as appmod
    return appmod.create_app()


def _account(application, email):
    client = application.test_client()
    client.post("/signup", data={"name": "T", "email": email, "password": "aa-pass-123"})
    client.post("/login", data={"email": email, "password": "aa-pass-123"})
    return client


@pytest.fixture
def owner(application, owner_email, monkeypatch):
    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("OWNER_EMAILS", owner_email)
    return _account(application, owner_email)


@pytest.fixture
def stranger(application):
    return _account(application, "audio-stranger-%s@example.net" % uuid.uuid4().hex[:8])


# --- access ----------------------------------------------------------------

def test_an_owner_can_open_it(owner):
    assert owner.get("/admin/audio").status_code == 200


def test_a_signed_out_visitor_cannot(application):
    resp = application.test_client().get("/admin/audio")
    assert resp.status_code in (301, 302)
    assert "/login" in (resp.headers.get("Location") or "")


def test_an_ordinary_account_cannot(stranger):
    resp = stranger.get("/admin/audio")
    assert resp.status_code in (301, 302)


def test_the_destructive_endpoints_refuse_a_stranger(stranger):
    """404 rather than 403: a stranger should not learn the route exists."""
    assert stranger.post("/admin/audio/sweep").status_code == 404
    assert stranger.post("/admin/audio/poll").status_code == 404


def test_the_destructive_endpoints_refuse_a_signed_out_visitor(application):
    """A redirect, not the route's own 404: the global login wall gets there
    first, which is the app-wide answer for every protected path and gives a
    stranger nothing this route would not have. What matters is that neither
    verb runs."""
    client = application.test_client()
    for path in ("/admin/audio/sweep", "/admin/audio/poll"):
        resp = client.post(path)
        assert resp.status_code in (301, 302, 404), path
        if resp.status_code != 404:
            assert "/login" in (resp.headers.get("Location") or ""), path


# --- what it must never show -----------------------------------------------

def test_a_credential_value_never_reaches_the_page(owner, monkeypatch):
    """The page reports whether a key is set. It is not a place to read one."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET_VALUE)
    body = owner.get("/admin/audio").get_data(as_text=True)

    assert "ELEVENLABS_API_KEY" in body, "the operator still needs to see it is set"
    assert SECRET_VALUE not in body, "a credential VALUE was rendered into HTML"


def test_no_person_is_named_in_the_module():
    """Access is a predicate over hashed emails plus OWNER_EMAILS. A name in
    source is how special access outlives the person it was granted to."""
    import io
    source = io.open("audio_admin.py", encoding="utf-8").read().lower()
    for token in ("@gmail", "@example.com", "warren", "javon"):
        assert token not in source, "audio_admin.py names %r" % token


# --- the sweep is safe by default ------------------------------------------

def test_the_sweep_defaults_to_a_dry_run(owner):
    """An operator pressing a button labelled with a number should get to see
    what would happen before anything is destroyed."""
    report = (owner.post("/admin/audio/sweep").get_json() or {}).get("report") or {}
    assert report.get("dry_run") is True


def test_the_sweep_destroys_only_when_confirmed(owner):
    report = (owner.post("/admin/audio/sweep", data={"confirm": "1"})
              .get_json() or {}).get("report") or {}
    assert report.get("dry_run") is False


# --- the table answers the operator's actual question ----------------------

def test_providers_are_listed_once_per_capability(owner, application):
    """The adapter-shaped report is nineteen rows carrying the same sentence
    nine times, which buries the only question worth asking."""
    import audio_admin
    import audio_providers as ap

    with application.app_context():
        rows = audio_admin._provider_rows()

    assert len(rows) == len(ap.CAPABILITIES)
    capabilities = [r["capability"] for r in rows]
    assert len(set(capabilities)) == len(capabilities), "a capability appears twice"
    for row in rows:
        assert row["serving"], "%s has no serving adapter" % row["capability"]


def test_the_serving_adapter_is_the_one_a_job_would_get(owner, application):
    """The page must not show one adapter while the runner uses another."""
    import audio_admin
    import audio_providers as ap

    with application.app_context():
        for row in audio_admin._provider_rows():
            assert row["serving"] == ap.get(row["capability"]).key


def test_the_button_ids_are_attributes_not_classes(owner):
    """sb.btn appends `extra` to the CLASS attribute, so passing an id through
    it emits class="sb-btn ... id=..." and every handler silently misses."""
    import re
    body = owner.get("/admin/audio").get_data(as_text=True)
    for element_id in ("aa-poll", "aa-sweep-dry", "aa-sweep-run"):
        assert 'id="%s"' % element_id in body, "%s lost its id" % element_id
        assert not re.search(r'class="[^"]*%s' % element_id, body), \
            "%s leaked into a class attribute" % element_id


def test_the_owner_is_offered_the_link_and_nobody_else_is(owner, stranger):
    """Internal tools were reachable only by typing the URL once. Offering
    everyone a link that answers 404 is worse than offering no link, so it is
    in the sidebar for owners and absent for everybody else."""
    assert "/admin/audio" in owner.get("/overview").get_data(as_text=True)
    assert "/admin/audio" not in stranger.get("/overview").get_data(as_text=True)


def test_every_section_renders(owner):
    body = owner.get("/admin/audio").get_data(as_text=True)
    for heading in ("Providers", "Feature flags", "Credentials", "Recent jobs",
                    "Webhook deliveries", "Usage", "Retention"):
        assert heading in body, "the %s section is missing" % heading
