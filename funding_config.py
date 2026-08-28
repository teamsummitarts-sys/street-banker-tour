"""Config-driven data for the Advance / Funding marketplace.

Turns the advance eligibility already computed on the Valuation page into
concrete, comparable funding offers plus a request flow. Offer amounts
are derived from the real suggested-advance figure so they stay
consistent with Valuation; terms/providers are illustrative.

This is a simulated demo only: requesting an offer records interest and
returns a reference number. No real money moves, no application is
submitted, and no financial credentials are ever collected.
"""


def get_funding_data(advance_eligibility):
    suggested = advance_eligibility.get("suggested_advance", 0) or 0
    tier = advance_eligibility.get("tier", "—")
    score = advance_eligibility.get("score", 0)

    # No income on record means no figure to scale an offer off. Three
    # offers built from a zero - or worse, from the demo earnings trend
    # this page used to read - are three amounts an artist might act on
    # that nobody can stand behind. Return the reason instead.
    if not suggested:
        return {
            "eligibility": advance_eligibility, "offers": [],
            "unavailable": advance_eligibility.get(
                "note", "Upload a royalty statement to see indicative "
                        "advance ranges based on your own income."),
        }

    # Three offer shapes scaled off the same suggested advance so the
    # marketplace stays consistent with the Valuation page.
    offers = [
        {
            "id": "offer-royalty-advance",
            "provider": "Street Banker Capital",
            "name": "Royalty Advance",
            "amount": round(suggested),
            "term_months": 18,
            "recoupment_pct": 70,
            "factor": 1.15,
            "speed": "3–5 days",
            "recommended": True,
            "note": "Repaid from a share of future royalties. No equity, no personal liability.",
        },
        {
            "id": "offer-catalog-advance",
            "provider": "Catalog Partners",
            "name": "Catalog Advance",
            "amount": round(suggested * 1.6),
            "term_months": 36,
            "recoupment_pct": 85,
            "factor": 1.25,
            "speed": "2–3 weeks",
            "recommended": False,
            "note": "Larger upfront sum against your whole catalog over a longer term.",
        },
        {
            "id": "offer-flex-draw",
            "provider": "FlexDraw",
            "name": "Flexible Draw",
            "amount": round(suggested * 0.5),
            "term_months": 9,
            "recoupment_pct": 50,
            "factor": 1.08,
            "speed": "24 hours",
            "recommended": False,
            "note": "Smaller, fast draw with the lowest cost — top up as you grow.",
        },
    ]

    for o in offers:
        o["total_repayable"] = round(o["amount"] * o["factor"], 2)
        o["cost"] = round(o["total_repayable"] - o["amount"], 2)

    return {
        # Pass the whole eligibility through rather than rebuilding a
        # three-key subset of it - the caller now carries the band, the
        # basis note and whether any of it is real, and a page that drops
        # those silently goes back to quoting a number with no provenance.
        "eligibility": dict(advance_eligibility,
                            tier=tier, score=score,
                            suggested_advance=round(suggested)),
        "offers": offers,
        "max_offer": max((o["amount"] for o in offers), default=0),
    }
