"""Billing must not tell a paying artist that nothing is charged.

/billing stacked two sections. The upper one is a showcase: an invented
renewal date, three hardcoded "Paid" invoices, usage tiles read from
royalty_data's seed catalogue rather than the account, and a line reading
"Demo only - no payment method is stored or charged".

The lower one is a live Stripe Checkout.

With STRIPE_SECRET_KEY set, both rendered. An artist paying every month was
shown somebody else's invoices and told they were not being charged, thirty
lines above the button that charges them. That is not a disclaimer that needed
rewording - the whole upper block belongs to a deployment with no payment
provider.
"""
import re
import uuid

import pytest

import stripe_provider


@pytest.fixture(scope="module")
def application():
    import app as appmod
    return appmod.app


@pytest.fixture
def payer(application):
    email = "billing-%s@example.net" % uuid.uuid4().hex[:8]
    client = application.test_client()
    client.post("/signup", data={"name": "Payer", "email": email,
                                 "password": "bl-pass-123"})
    client.post("/login", data={"email": email, "password": "bl-pass-123"})
    return client


@pytest.fixture
def stripe_live(monkeypatch):
    """A deployment with a real payment provider configured."""
    monkeypatch.setattr(stripe_provider, "configured", lambda: True)


def _text(client):
    body = client.get("/billing").get_data(as_text=True)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


# --- the sentence that was false -------------------------------------------

def test_a_live_deployment_never_says_nothing_is_charged(payer, stripe_live):
    """The whole point. It sat directly above a working Subscribe button."""
    assert "Demo only" not in _text(payer)
    assert "no payment method is stored or charged" not in _text(payer)


def test_a_live_deployment_shows_no_fabricated_invoices(payer, stripe_live):
    """Three hardcoded rows marked Paid, shown to accounts that really are
    paying - their actual invoices are in Stripe's portal."""
    body = _text(payer)
    for invented in ("INV-2026-06", "INV-2026-05", "INV-2026-04"):
        assert invented not in body


def test_a_live_deployment_shows_no_invented_renewal_date(payer, stripe_live):
    assert "Renews 2026-08-01" not in _text(payer)


def test_a_live_deployment_hides_the_whole_showcase_block(payer, stripe_live):
    """Not just the sentence. The plan table, the usage tiles and the
    non-functional "Choose" buttons are all part of the same fiction."""
    assert "Compare Plans" not in _text(payer)


# --- and still works ------------------------------------------------------

def test_a_live_deployment_still_offers_checkout(payer, stripe_live):
    """Removing the showcase must not remove the product."""
    body = _text(payer)
    assert "Subscribe" in body
    assert "Billing" in body, "the page lost its heading with the legacy block"


def test_the_live_page_says_where_the_real_invoices_are(payer, stripe_live):
    """The showcase's invoice list is gone, so the page has to point at the
    thing that replaced it rather than leaving a hole."""
    body = _text(payer).lower()
    assert "portal" in body or "invoices" in body


def test_the_live_page_states_it_holds_no_card(payer, stripe_live):
    assert "never stores a card number" in _text(payer)


# --- the deployment the showcase was written for ---------------------------

def test_without_a_provider_the_showcase_still_renders_and_says_so(payer):
    """On a deployment with no Stripe there is nothing to contradict, and the
    block is a legitimate preview of what billing looks like - as long as it
    keeps saying so."""
    body = _text(payer)
    assert "Demo only" in body
    assert "INV-2026-06" in body


def test_the_guard_is_the_same_one_the_checkout_uses(application):
    """real_checkout drives BOTH the showcase and the Subscribe button. Two
    separate conditions would eventually disagree, and the disagreement would
    look exactly like the bug this file is about."""
    import io

    template = io.open("templates/billing.html", encoding="utf-8").read()
    assert template.count("{% set real_checkout") == 1, \
        "real_checkout must be computed once, at the top"

    guard = template.index("{% set real_checkout")
    showcase = template.index("{% if not real_checkout %}")
    assert guard < showcase, "the showcase must be gated by the same flag"
