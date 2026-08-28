"""Config-driven data for the Billing / subscription page.

Shows the current plan (from the shared account config), usage this period,
past invoices, and the available plans to compare.

EVERYTHING HERE IS ILLUSTRATIVE, AND IT IS NOT ALWAYS SHOWN
-----------------------------------------------------------
The invoices are three hardcoded rows. `renews_on` is a literal date. The
usage tiles read royalty_data's seed catalogue, which belongs to the showcase
rather than to the signed-in account.

None of that is a problem on a deployment with no payment provider, which is
what this module was written for. It became one when Stripe was configured:
templates/billing.html rendered this block, invented invoices and the line
"Demo only - no payment method is stored or charged", directly ABOVE a live
Stripe Checkout. An artist paying every month read that they were not being
charged.

So the template now hides this entire block whenever `real_checkout` is true,
and the real section carries its own plan state while Stripe's billing portal
carries the real invoices. Do not call this from a path that a paying account
can reach.
"""

from royalty_data import get_songs, get_platform_catalog


PLANS = [
    {"id": "free", "name": "Free", "price": 0, "blurb": "Track your catalog and see what you're owed.",
     "features": ["Up to 10 songs", "1 connected source", "Basic recovery scan"]},
    {"id": "pro", "name": "Pro Plan", "price": 19, "blurb": "Full tools + real career guidance from our team.",
     "features": ["Unlimited songs", "All source connections", "Recovery + claims", "Valuation & advances",
                  "Publishing admin", "Monthly consulting hours + email support — from Street Banker & industry ambassadors"]},
    {"id": "label", "name": "Label", "price": 49, "blurb": "For teams managing multiple artists.",
     "features": ["Everything in Pro", "Expanded consulting hours + priority ambassador access",
                  "Multi-artist roster", "Team permissions", "API access"]},
]


def get_billing_data(account):
    current_plan_name = account.get("plan", "Pro Plan")
    songs = get_songs()
    catalog = get_platform_catalog()
    connected = sum(1 for p in catalog if p.status == "connected")

    plans = [dict(p, current=(p["name"] == current_plan_name)) for p in PLANS]
    current = next((p for p in plans if p["current"]), plans[1])

    invoices = [
        {"id": "INV-2026-06", "date": "2026-06-01", "amount": current["price"], "status": "Paid"},
        {"id": "INV-2026-05", "date": "2026-05-01", "amount": current["price"], "status": "Paid"},
        {"id": "INV-2026-04", "date": "2026-04-01", "amount": current["price"], "status": "Paid"},
    ]

    return {
        "current_plan": current,
        "renews_on": "2026-08-01",
        "usage": [
            {"label": "Songs tracked", "value": len(songs)},
            {"label": "Sources connected", "value": connected},
            {"label": "Plan seats used", "value": 1},
        ],
        "plans": plans,
        "invoices": invoices,
    }
