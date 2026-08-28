"""Capital Readiness Score + Spend Optimizer.

Both composed entirely from data already in the account — statement
income, logged spend, campaigns, fans, catalog, and the Trust Score.
Everything here is an informational estimate, never financial advice,
and the pages say so.
"""

import db as store
import links_store as mls
import trust_score


def _pts(value, full, cap):
    if full <= 0:
        return 0
    return min(round(cap * value / full), cap)


def capital_score(user_id):
    """Funding readiness, 0-100, from five verifiable factors of 20."""
    rows = store.get_statement_rows(user_id)
    total_income = sum(r["amount"] for r in rows)
    periods = {r.get("period") or "" for r in rows if r.get("period")}
    sources = {r.get("source") or "" for r in rows if r.get("source")}
    tracks = store.get_catalog_tracks(user_id)
    campaigns = [c for c in mls.list_campaigns(user_id) if not c.get("archived_at")]
    trust = trust_score.calculate(user_id)

    factors = [
        ("Income on record", _pts(total_income, 2000, 20),
         "Upload royalty statements — verifiable income is the core of any advance."),
        ("Income consistency", _pts(len(periods), 6, 20),
         "Six or more distinct statement periods shows income that repeats."),
        ("Source diversity", _pts(len(sources), 3, 20),
         "Income from 3+ platforms is safer to lend against than one."),
        ("Business hygiene", _pts(trust["total"], 100, 20),
         "Raise your Trust Score — splits, metadata, and paperwork move it."),
        ("Catalog & activity", _pts(len(tracks) + len(campaigns), 6, 20),
         "A deeper catalog with tracked campaigns supports larger advances."),
    ]
    total = sum(pts for _, pts, _ in factors)
    if total >= 75:
        verdict = "Advance-ready profile"
    elif total >= 45:
        verdict = "Building the case"
    else:
        verdict = "Too early — keep stacking data"

    # Illustrative advance band: 0.8-1.5x the annualized income on record.
    annualized = total_income * (12 / max(len(periods), 1)) if periods else 0.0
    band = ((round(annualized * 0.8), round(annualized * 1.5))
            if annualized > 0 else None)

    # Remember today's reading. Guarded: a history write must never be
    # the reason a page fails to render.
    try:
        store.record_score(user_id, "capital", total, {"income_total": round(total_income, 2), "periods": len(periods),
         "sources": len(sources)})
    except Exception:
        pass
    return {"total": total, "factors": factors, "verdict": verdict,
            "income_total": round(total_income, 2),
            "periods": len(periods), "sources": len(sources),
            "advance_band": band,
            "weak": [(n, p, note) for n, p, note in factors if p < 12]}


# Rule-of-thumb allocation for a limited release budget. Percentages shift
# with what the account shows is actually working.
def spend_plan(user_id, budget=500.0):
    campaigns = [c for c in mls.list_campaigns(user_id) if not c.get("archived_at")]
    fans = mls.list_fans(user_id)
    expenses = store.list_expenses(user_id)
    spent = sum(e["amount"] for e in expenses)
    clicks = pageviews = 0
    for c in campaigns:
        n = mls.event_counts(c["id"])
        clicks += n.get("click", 0) + n.get("service_click", 0)
        pageviews += n.get("pageview", 0) + n.get("page_view", 0)

    # Base split, then shift weight toward what the data supports.
    alloc = {"Content (short-form video)": 40, "Targeted ads": 25,
             "Fan re-engagement": 15, "Release-day reserve": 20}
    reasons = {
        "Content (short-form video)": "Highest organic ceiling per dollar; every rollout post is already scripted for you in Rollout Engine.",
        "Targeted ads": "Only worth funding once a link converts — send traffic to your best-scoring campaign.",
        "Fan re-engagement": "You own this list; email costs almost nothing per fan reached.",
        "Release-day reserve": "Hold this until you see which channel converts, then double down.",
    }
    if len(fans) >= 25:
        alloc["Fan re-engagement"] += 10
        alloc["Targeted ads"] -= 10
        reasons["Fan re-engagement"] += " With %d consented fans, this is your cheapest conversion channel." % len(fans)
    if pageviews and clicks and clicks / max(pageviews, 1) >= 0.4:
        alloc["Targeted ads"] += 10
        alloc["Content (short-form video)"] -= 10
        reasons["Targeted ads"] += " Your links convert %d%% of visits to platform clicks — paid traffic has somewhere good to land." % round(100 * clicks / pageviews)

    allocations = [{"channel": k, "pct": v, "amount": round(budget * v / 100, 2),
              "reason": reasons[k]} for k, v in alloc.items()]
    avoid = [
        "Playlist placement you have to pay for — bot risk taints your data and DSPs penalize it.",
        "Boosting posts without a tracked link — spend you can't attribute is spend you can't repeat.",
        "Pressing physical stock before demand shows up in your fan and click numbers.",
    ]
    return {"budget": budget, "allocations": allocations, "avoid": avoid,
            "spent_logged": round(spent, 2),
            "fan_count": len(fans), "clicks": clicks, "pageviews": pageviews}


def advance_eligibility(user_id):
    """Advance eligibility from the artist's own statements.

    /funding used to quote a suggested advance, and three offers scaled
    off it, derived from get_earnings_trend() - a hardcoded Jan-Jun list
    identical for every account. Every artist on the platform was shown
    the same amount of money, with a Request button under it, regardless
    of what they actually earn.

    This computes it from the statements they uploaded, and when there
    are none it says so and quotes nothing. An advance figure with no
    income behind it is not a conservative estimate, it is a number
    somebody might act on.

    Shape matches what funding_config and the valuation page already
    expect, plus `real` so the page can say which it is showing.
    """
    cs = capital_score(user_id)
    band = cs.get("advance_band")
    if not band:
        return {
            "real": False, "tier": "Not established", "score": cs["total"],
            "suggested_advance": 0, "band": None,
            "income_total": cs["income_total"], "periods": cs["periods"],
            "sources": cs["sources"],
            "note": "No royalty statements uploaded yet, so there is no "
                    "income to lend against and no honest figure to quote. "
                    "Upload a statement and this fills in from it.",
        }
    low, high = band
    if cs["total"] >= 75:
        tier = "Advance-ready"
    elif cs["total"] >= 45:
        tier = "Eligible with conditions"
    else:
        tier = "Building the case"
    return {
        "real": True, "tier": tier, "score": cs["total"],
        # The conservative end of the band, not the top of it - the number
        # under a Request button should be the one most likely to survive
        # someone actually checking the statements.
        "suggested_advance": low, "band": {"low": low, "high": high},
        "income_total": cs["income_total"], "periods": cs["periods"],
        "sources": cs["sources"],
        "note": "Based on ${:,.0f} across {} period{} from {} source{}, "
                "annualised. Indicative range, not an offer.".format(
                    cs["income_total"], cs["periods"],
                    "" if cs["periods"] == 1 else "s", cs["sources"],
                    "" if cs["sources"] == 1 else "s"),
    }
