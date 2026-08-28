"""The store's checkout, embedded — or an honest link when it is not.

The app has always linked out to artiswarrecords.com. A link is a
handoff: the fan leaves and the cart is somewhere else. Buy Buttons put
Shopify's own checkout on the page they are already on, with no payment
code on this side.

The three env vars are the store's to give. Until they exist the page
must be the link it always was - not an empty widget, not a spinner,
and not a "coming soon".
"""

import os

import shopify_buy
from app import create_app


def _env(monkeypatch, **values):
    for key in ("SHOPIFY_DOMAIN", "SHOPIFY_STOREFRONT_TOKEN",
                "SHOPIFY_COLLECTION_ID"):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _demo(app_obj=None):
    client = (app_obj or create_app()).test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    return client


def test_unconfigured_is_a_link_not_a_broken_shop(monkeypatch):
    _env(monkeypatch)
    assert shopify_buy.configured() is False
    body = _demo().get("/apparel").get_data(as_text=True)
    assert "The store is not embedded here yet" in body
    assert "artiswarrecords.com" in body          # the store still opens
    assert "shopify-collection" not in body       # no empty mount point
    assert "buy-button-storefront" not in body    # and no SDK to hang on


def test_partial_credentials_do_not_half_open_the_store(monkeypatch):
    _env(monkeypatch, SHOPIFY_DOMAIN="artiswar.myshopify.com")
    assert shopify_buy.configured() is False
    ctx = shopify_buy.context()
    assert "SHOPIFY_STOREFRONT_TOKEN" in ctx["reason"]
    assert "SHOPIFY_COLLECTION_ID" in ctx["reason"]


def test_configured_embeds_the_real_sdk(monkeypatch):
    _env(monkeypatch, SHOPIFY_DOMAIN="artiswar.myshopify.com",
         SHOPIFY_STOREFRONT_TOKEN="storefront_public_token",
         SHOPIFY_COLLECTION_ID="123456789")
    assert shopify_buy.configured() is True
    body = _demo().get("/apparel").get_data(as_text=True)
    assert 'id="shopify-collection"' in body
    assert "sdks.shopifycdn.com/buy-button" in body
    assert '"artiswar.myshopify.com"' in body
    assert '"123456789"' in body
    assert "The store is not embedded here yet" not in body


def test_the_page_never_asks_for_a_card(monkeypatch):
    """Checkout belongs to Shopify. If this page ever grows a card field
    it has stopped being an embed and started being a liability."""
    _env(monkeypatch, SHOPIFY_DOMAIN="artiswar.myshopify.com",
         SHOPIFY_STOREFRONT_TOKEN="storefront_public_token",
         SHOPIFY_COLLECTION_ID="123456789")
    body = _demo().get("/apparel").get_data(as_text=True)
    for banned in ["card number", "cardnumber", "cvc", "cvv", "expiry",
                   'name="card', 'autocomplete="cc-']:
        assert banned not in body.lower(), banned


def test_the_admin_key_is_never_read(monkeypatch):
    """A Storefront token is meant to ship to browsers. An admin key is
    not, so nothing here may reach for one."""
    source = open("shopify_buy.py", encoding="utf-8").read()
    template = open("templates/apparel.html", encoding="utf-8").read()
    for banned in ["SHOPIFY_ADMIN", "ADMIN_API", "X-Shopify-Access-Token"]:
        assert banned not in source, banned
        assert banned not in template, banned


def test_services_points_at_the_page(monkeypatch):
    _env(monkeypatch)
    body = _demo().get("/services").get_data(as_text=True)
    assert 'href="/apparel"' in body
