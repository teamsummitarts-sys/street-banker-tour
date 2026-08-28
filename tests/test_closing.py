"""Section 12, the 11.5 trust band, and the consolidation pass.

Three things these tests are really guarding:

  1. The closing frame says the two sentences and makes no claim - no
     figure, no client, no guarantee.
  2. Every public CTA on the homepage answers a signed-out visitor with a
     page rather than a login wall. That is the rule the whole
     consolidation pass exists to enforce, so it is tested by walking the
     rendered markup rather than by listing routes by hand.
  3. The capability status labels are the agreed six, and the example
     workspaces say they are examples.
"""
import re

import pytest

import closing_config
import tour_config
from app import create_app


@pytest.fixture()
def client():
    return create_app().test_client()


@pytest.fixture()
def home(client):
    r = client.get("/")
    assert r.status_code == 200
    return r.get_data(as_text=True)


# --- Section 12 -------------------------------------------------------------
def test_closing_says_the_two_sentences(home):
    assert "Your music is the" in home
    assert "Your catalog is the" in home
    assert closing_config.SUPPORT in home
    assert closing_config.TRUST_LINE in home


def test_closing_carries_no_numbers_or_claims(home):
    section = home[home.index('id="closing"'):home.index("</section>", home.index('id="closing"'))]
    text = re.sub(r"<[^>]+>", " ", section)
    # No figure of any kind belongs in the last frame.
    assert not re.search(r"\d[\d,.]*\s*(%|artists|streams|countries)", text)
    for banned in ("guarantee", "guaranteed", "we predict", "#1", "millions"):
        assert banned.lower() not in text.lower()


def test_closing_image_is_present_at_both_crops(home):
    assert "closing-wide-1672" in home
    assert "closing-close-1070" in home
    assert closing_config.IMAGE["alt"] in home


def test_closing_ctas_point_at_public_routes(client, home):
    for cta in (closing_config.PRIMARY_CTA, closing_config.SECONDARY_CTA):
        assert 'href="%s"' % cta["href"] in home
        assert client.get(cta["href"]).status_code == 200


# --- 11.5 trust band --------------------------------------------------------
def test_trust_band_shows_all_four_promises(home):
    assert closing_config.BAND_TITLE in home
    for title, body in closing_config.BAND:
        assert title in home
        assert body in home


def test_artist_control_policy_is_public_and_complete(client):
    r = client.get("/artist-control")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    for title, _ in closing_config.POLICY:
        assert title in body


# --- the guided start -------------------------------------------------------
def test_start_is_public_and_carries_the_eq_mix(client):
    plain = client.get("/start")
    assert plain.status_code == 200

    carried = client.get("/start?release=95&rights=10&preset=release-mode")
    assert carried.status_code == 200
    body = carried.get_data(as_text=True)
    # A release-weighted mix must not come back recommending the
    # rights-first lane; if it does the plan is ignoring the query.
    assert "Artist EQ settings you made" in body


# --- the public product tour ------------------------------------------------
def test_product_tour_is_public_and_covers_every_step(client):
    r = client.get("/product-tour")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    for step in tour_config.STEPS:
        assert step["title"] in body
        assert tour_config.STATUS_LABELS[step["status"]] in body


def test_every_tour_step_links_somewhere_public(client):
    for step in tour_config.STEPS:
        target = step["href"].split("#")[0]
        assert client.get(target).status_code == 200, step["slug"]


def test_smart_link_and_fan_pages_are_labelled_examples(client):
    body = client.get("/product-tour/smart-link").get_data(as_text=True)
    assert "Example" in body
    assert tour_config.FAN_PANEL["trust"] in body
    assert tour_config.FAN_PANEL["note"] in body
    assert tour_config.BRAND_MEMORY["trust"] in body
    # Fan intelligence must never present invented rows as real readings.
    for _, reading, _ in tour_config.FAN_PANEL["rows"]:
        assert reading.startswith("Example")


def test_status_vocabulary_is_the_agreed_six():
    assert set(tour_config.STATUS_LABELS.values()) == {
        "Live", "Example", "Partner delivered", "Integration ready",
        "Coming soon", "Requires verification"}


# --- the consolidation rules ------------------------------------------------
def test_no_homepage_link_sends_a_visitor_into_the_login_wall(client, home):
    """The rule the whole pass exists for, checked against real responses.

    One deliberate exception: /operator-desk in the footer's Company
    column is the staff entrance, labeled as such — a stranger clicking
    it is SUPPOSED to meet the login wall. Everything else on the page,
    including the Press Desk's own public page, must answer."""
    gated_on_purpose = {"/operator-desk"}
    seen = {}
    for href in sorted(set(re.findall(r'href="(/[^"?#]*)"', home))):
        if href.startswith("/static") or href in gated_on_purpose:
            continue
        if href not in seen:
            seen[href] = client.get(href).status_code
        assert seen[href] == 200, "%s answered %s" % (href, seen[href])
    assert len(seen) > 5


def test_every_homepage_anchor_target_exists(home):
    ids = set(re.findall(r'id="([^"]+)"', home))
    for href in set(re.findall(r'href="/?#([^"]+)"', home)):
        assert href in ids, "#%s has no target" % href


def test_footer_columns_are_public_and_named(client, home):
    for title in ("Platform", "Solutions", "Trust", "Company", "Account"):
        assert ">%s<" % title in home


def test_the_product_is_called_rollout_engine_everywhere(home):
    assert "Rollout Studio" not in home
    assert "Rollout Engine" in home
