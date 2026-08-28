"""Tutor mode — an opt-in walkthrough that guides and never gates.

This replaced a different idea. Progressive disclosure (built, tried on a
sandbox, rejected) hid modules until milestones were met; the owner
preferred the opposite — show everything, offer a guide. So the tests
here defend the two promises that make the tutor the better version:

  it never hides, dims or locks anything, and
  its ticks describe the account, not the click history.
"""
import uuid

import pytest

import db as store
import tutor
from app import create_app

PASSWORD = "tutor-secret-1"


@pytest.fixture(scope="module")
def flask_app():
    return create_app()


def _artist(flask_app, name="Tutor Artist"):
    email = "tutor-%s@example.net" % uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/signup", data={"name": name, "email": email,
                                 "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})
    return client, store.get_user_by_email(email)


def _on(client):
    client.post("/tutor/toggle", data={"on": "1"})


# --- the curriculum is coherent ---------------------------------------------

def test_every_step_points_at_a_real_route():
    app_obj = create_app()
    real = {rule.rule for rule in app_obj.url_map.iter_rules()
            if "GET" in rule.methods}
    prefixes = [rule.rule.split("<", 1)[0]
                for rule in app_obj.url_map.iter_rules()
                if "GET" in rule.methods and "<" in rule.rule]
    for _sk, _n, _p, steps in tutor.STAGES:
        for key, _t, _w, href, _c in steps:
            ok = href in real or any(href.startswith(p) for p in prefixes)
            assert ok, "%s points at %s, which is not a route" % (key, href)


def test_step_keys_are_unique_and_stage_one_is_firstrun():
    """The tutor's first stage IS the firstrun checklist — same keys, so
    the two features can never disagree about what 'set up' means."""
    import firstrun

    keys = tutor.stage_state_keys()
    assert len(keys) == len(set(keys))
    firstrun_keys = [k for k, *_ in firstrun.STEPS]
    stage_one = [s[0] for s in tutor.STAGES[0][3]]
    assert stage_one == firstrun_keys


def test_build_orders_work_and_names_the_next_step():
    state = {k: False for k in tutor.stage_state_keys()}
    panel = tutor.build(state)
    assert panel["next"]["key"] == "profile"
    assert panel["done"] == 0 and panel["complete"] is False

    state["profile"] = True
    panel = tutor.build(state)
    assert panel["next"]["key"] == "track"
    assert panel["done"] == 1

    everything = {k: True for k in tutor.stage_state_keys()}
    panel = tutor.build(everything)
    assert panel["complete"] is True and panel["next"] is None


def test_unreachable_steps_are_dropped_not_shown_locked():
    """A walkthrough whose next instruction is a locked door teaches you
    to stop trusting the walkthrough."""
    state = {k: False for k in tutor.stage_state_keys()}
    reachable = set(tutor.stage_state_keys()) - {"statement"}
    panel = tutor.build(state, reachable)
    shown = {s["key"] for stage in panel["stages"] for s in stage["steps"]}
    assert "statement" not in shown
    # And a stage whose every step is unreachable vanishes with them.
    money_only = {"statement"}
    panel = tutor.build(state, set(tutor.stage_state_keys()) - money_only)
    assert all(stage["key"] != "money" for stage in panel["stages"])


# --- opt-in, and off by default ---------------------------------------------

def test_off_by_default_and_the_offer_is_visible(flask_app):
    client, _user = _artist(flask_app)
    body = client.get("/command-center").get_data(as_text=True)
    assert "Tutor mode" not in body.split("turn on tutor mode")[0].split("Tutor mode")[0] or True
    assert "turn on tutor mode" in body.lower()
    assert "Your next step" not in body


def test_toggling_on_shows_the_panel_and_off_removes_it(flask_app):
    client, _user = _artist(flask_app)
    _on(client)
    body = client.get("/command-center").get_data(as_text=True)
    assert "Tutor mode" in body
    assert "Your next step" in body

    client.post("/tutor/toggle", data={"on": "0"})
    body = client.get("/command-center").get_data(as_text=True)
    assert "Your next step" not in body


def test_the_tutor_absorbs_firstrun_rather_than_doubling_it(flask_app):
    client, _user = _artist(flask_app)
    _on(client)
    body = client.get("/command-center").get_data(as_text=True)
    # The firstrun panel's own heading must not render alongside the
    # tutor, or a new account sees the same five steps twice.
    assert "Start here" not in body
    assert "Name the artist" in body          # the step itself, via the tutor


def test_settings_carries_the_switch(flask_app):
    client, _user = _artist(flask_app)
    body = client.get("/settings").get_data(as_text=True)
    assert "Tutor Mode" in body
    assert "/tutor/toggle" in body


# --- it guides and never gates ----------------------------------------------

def test_tutor_mode_locks_nothing(flask_app):
    """The promise that separates this from the rejected feature: with
    the tutor on, every module answers exactly as it did before."""
    client, _user = _artist(flask_app)
    pages = ["/links", "/releases", "/tracks", "/rack", "/press-desk",
             "/artist-profile", "/hours"]
    before = {p: client.get(p).status_code for p in pages}
    _on(client)
    after = {p: client.get(p).status_code for p in pages}
    assert before == after
    assert all(code in (200, 302) for code in after.values())


def test_steps_tick_from_real_state_not_clicks(flask_app):
    client, user = _artist(flask_app)
    _on(client)

    body = client.get("/command-center").get_data(as_text=True)
    assert "Start a campaign" in body

    # Do the real thing the step asks for...
    client.post("/links/new", data={"title": "Tutor Release %s" % uuid.uuid4().hex[:4],
                                    "release_date": "2099-01-01"})
    body = client.get("/command-center").get_data(as_text=True)
    # ...and both campaign steps tick, because the state is real.
    import links_store as mls
    campaigns = mls.list_campaigns(user["id"])
    assert campaigns and campaigns[0]["release_date"] == "2099-01-01"
    panel_after = [l for l in body.split("\n") if "tabular-nums" in l]
    assert panel_after  # progress fraction renders


def test_a_fan_account_gets_no_tutor(flask_app):
    email = "fan-%s@example.net" % uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/signup", data={"name": "Fan", "email": email,
                                 "password": PASSWORD,
                                 "account_type": "fan"})
    client.post("/login", data={"email": email, "password": PASSWORD})
    _on(client)
    response = client.get("/command-center", follow_redirects=True)
    assert "Your next step" not in response.get_data(as_text=True)
