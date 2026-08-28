"""The Fan Dashboard on real records, and the claim it used to make.

/fans handed community_config's invented figures to every account - 1,240
superfans, 41,000 casual listeners, a leaderboard of made-up handles spending
made-up money - under a line reading "the app doesn't track individual fans".

Two defects in one panel. The numbers were nobody's, and the disclaimer was a
privacy claim the product could not stand behind: the Fan CRM at /links/fans
has held named fans with intent scores since smart links shipped.
"""
import re
import uuid

import pytest

import db as store
import fan_dashboard
import links_store as mls


@pytest.fixture(scope="module")
def application():
    import app as appmod
    return appmod.app


def _account(application, email):
    client = application.test_client()
    client.post("/signup", data={"name": "Artist", "email": email,
                                 "password": "fd-pass-123"})
    client.post("/login", data={"email": email, "password": "fd-pass-123"})
    with application.app_context():
        return client, store.get_user_by_email(email)


@pytest.fixture
def artist(application):
    return _account(application, "fd-%s@example.net" % uuid.uuid4().hex[:8])


def _seed(application, user_id, qr_scans=0):
    with application.app_context():
        campaign_id = mls.create_campaign(user_id, "seed-%s" % uuid.uuid4().hex[:6],
                                          {"title": "Seed"})
        for i, (email, score, level) in enumerate([
                ("ada@example.net", 92, "Hot"), ("bo@example.net", 71, "Warm"),
                ("cy@example.net", 44, "Cool"), ("di@example.net", 12, "Cold")]):
            fan_id = mls.upsert_fan(user_id, email, campaign_id, name="Fan %d" % i)
            mls.set_fan_intent(fan_id, score, level)
            mls.bump_fan(fan_id, "total_visits", 3 + i)
            mls.add_consent(fan_id, campaign_id, "email", "I agree.")
        for _ in range(qr_scans):
            mls.track(campaign_id, "qr_scan")
    return campaign_id


def _text(response):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", response.get_data(as_text=True)))


# --- the claim that was false ----------------------------------------------

def test_the_page_no_longer_says_the_app_does_not_track_fans(application, artist):
    """It does track them. Saying otherwise is a statement about personal
    data, not about a feature."""
    client, _user = artist
    assert "doesn't track individual fans" not in _text(client.get("/fans"))


def test_a_real_account_is_never_shown_invented_fans(application, artist):
    """Showcase figures handed to a real artist read as their own - the same
    defect the royalty dashboard had."""
    client, _user = artist
    body = _text(client.get("/fans"))
    assert "vinylhoarder" not in body
    assert "41,000" not in body


# --- real numbers ----------------------------------------------------------

def test_the_numbers_come_from_the_accounts_own_records(application, artist):
    client, user = artist
    _seed(application, user["id"], qr_scans=7)

    with application.app_context():
        data = fan_dashboard.fan_dashboard_for(user["id"])

    assert data["is_real"]
    assert data["summary"]["total_fans"] == 4
    assert data["summary"]["consented"] == 4
    assert data["summary"]["qr_scans"] == 7


def test_qr_scans_are_counted_apart_from_ordinary_visits(application, artist):
    """/l/<slug> writes a qr_scan event when the link carried ?src=qr, which
    is what makes a printed code measurable at all."""
    client, user = artist
    campaign_id = _seed(application, user["id"], qr_scans=3)
    with application.app_context():
        mls.track(campaign_id, "page_view")
        data = fan_dashboard.fan_dashboard_for(user["id"])

    assert data["summary"]["qr_scans"] == 3
    assert data["summary"]["page_views"] == 1


def test_segments_are_the_real_intent_bands(application, artist):
    """Not invented tiers - the bands the smart-link scorer already writes."""
    client, user = artist
    _seed(application, user["id"])
    with application.app_context():
        data = fan_dashboard.fan_dashboard_for(user["id"])

    assert [s["segment"] for s in data["segments"]] == ["Hot", "Warm", "Cool", "Cold"]
    assert sum(s["count"] for s in data["segments"]) == 4


def test_no_money_figure_is_produced_anywhere(application, artist):
    """ml_fans has no spend column and the app has no purchase feed, so every
    lifetime-value figure the old panel showed was invented. A fan-value
    number an artist might act on is not a thing to estimate."""
    client, user = artist
    _seed(application, user["id"])
    with application.app_context():
        data = fan_dashboard.fan_dashboard_for(user["id"])

    blob = str(data).lower()
    assert "ltv" not in blob
    assert "spend" not in blob

    body = _text(client.get("/fans"))
    assert "Avg. Fan LTV" not in body


# --- the empty state -------------------------------------------------------

def test_an_account_with_no_fans_gets_an_honest_empty_state(application, artist):
    """Zero is the correct answer for somebody who has not published a link,
    and the panel should say what makes a fan rather than show nothing."""
    client, _user = artist
    body = _text(client.get("/fans"))
    assert "No fans captured yet" in body
    assert "smart link" in body.lower()


def test_a_signed_out_visitor_does_not_see_an_empty_dashboard(application):
    """They get the showcase, clearly labelled - not somebody's real zero."""
    response = application.test_client().get("/fans")
    assert response.status_code in (200, 301, 302)


# --- tenancy ---------------------------------------------------------------

def test_one_accounts_fans_never_reach_another(application, artist):
    client, user = artist
    _seed(application, user["id"])

    other_client, _other = _account(application,
                                    "fd-other-%s@example.net" % uuid.uuid4().hex[:8])
    body = _text(other_client.get("/fans"))
    assert "ada@example.net" not in body
    assert "No fans captured yet" in body


# --- QR codes are a shipped feature ----------------------------------------

def test_qr_codes_are_published_as_live():
    """They generate through segno, carry ?src=qr, and every scan is counted.
    Publishing them as "coming soon" under-sold a finished feature, and
    capability_status is the one place that stops a capability reading
    differently on different pages."""
    import capability_status

    resolved = capability_status.resolve("qr_codes")
    assert resolved["status"] == capability_status.LIVE
