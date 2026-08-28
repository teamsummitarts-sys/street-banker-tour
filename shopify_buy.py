"""Shopify Buy Buttons — the store's checkout, inside the app.

The store at artiswarrecords.com is the ecosystem's real commerce
engine, and the app has only ever linked out to it. A link is a
handoff: the fan leaves, the cart is somewhere else, and whatever
brought them here does not follow them. Buy Buttons put the same
checkout on the page they are already on. No payment code is added on
this side and no card data touches this server - the embed is Shopify's
own SDK talking to Shopify.

Env-gated like every other provider here:

    SHOPIFY_DOMAIN           your-store.myshopify.com
    SHOPIFY_STOREFRONT_TOKEN Storefront API access token (public scope)
    SHOPIFY_COLLECTION_ID    numeric id of the collection to show

Without all three, `configured()` is False and the page keeps the
outbound link. It does not render an empty widget, a spinner, or a
"coming soon" - an unconfigured integration should look like the honest
link it still is, not like a broken store.

The token is a *Storefront* token, which is designed to ship to
browsers: it can read published products and create checkouts, and
nothing else. The admin API key must never appear here.
"""

import os


def domain():
    return (os.environ.get("SHOPIFY_DOMAIN") or "").strip()


def token():
    return (os.environ.get("SHOPIFY_STOREFRONT_TOKEN") or "").strip()


def collection_id():
    return (os.environ.get("SHOPIFY_COLLECTION_ID") or "").strip()


def configured():
    return bool(domain() and token() and collection_id())


def context():
    """What the template needs, and a reason when it needs nothing."""
    if configured():
        return {"configured": True, "domain": domain(), "token": token(),
                "collection_id": collection_id(), "reason": ""}
    missing = [name for name, value in (
        ("SHOPIFY_DOMAIN", domain()),
        ("SHOPIFY_STOREFRONT_TOKEN", token()),
        ("SHOPIFY_COLLECTION_ID", collection_id())) if not value]
    return {"configured": False, "domain": "", "token": "",
            "collection_id": "",
            "reason": "Set %s to embed the store." % ", ".join(missing)}
