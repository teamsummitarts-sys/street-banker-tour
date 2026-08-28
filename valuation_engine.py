"""What the catalog is worth, from the statements that prove it.

/valuation was the same page as /recovery in a different suit. Estimated
Catalog Value, Annual Run Rate, the value tracker and its percentage
change, the six-point valuation curve, Suggested Advance, the three
eligibility bars, the conservative/expected/aggressive forecast - every
one of them traced back to `get_earnings_trend()`, six hardcoded months
(Jan 800 through Jun 3200) that describe no account that has ever
existed. Two of the Value Drivers even carried hardcoded payoffs:
"+$28,650/yr" and "+$4,820".

This computes the page from the artist's own uploaded months.

  Run rate is the mean of the statement months on record, annualised.
  Nothing is smoothed, weighted or projected into months that have not
  happened.

  The value band is 3x/4x/5x that run rate, the same conservative
  independent-catalog range `report_builder` already uses, so the CSV a
  label receives and the page it was quoted from cannot disagree.

  The forecast is the artist's own worst, mean and best month on record,
  each carried forward. It is not a model - it is the range their own
  statements have actually produced, which is the only projection this
  product can defend.

  Advance figures come from `capital_engine.advance_eligibility`, which
  was already honest, rather than from a multiple of an invented curve.

One month of statements is one month of evidence, and the page says so
instead of annualising a single row into a five-figure valuation without
comment. No statements means no figure at all.
"""

import capital_engine
import db as store
import recovery_engine
import statements_engine
import trust_score


# The same conservative independent-catalog range report_builder quotes.
MULTIPLES = {"low": 3, "mid": 4, "high": 5}


def _monthly(rows):
    """Tracked revenue per statement period, oldest first."""
    totals = {}
    for r in rows:
        period = (r.get("period") or "").strip()
        if not period:
            continue
        totals[period] = totals.get(period, 0) + (r.get("amount") or 0)
    return [{"period": p, "amount": round(a, 2)}
            for p, a in sorted(totals.items())]


def _drivers(user_id, view):
    """Value drivers, each carrying a number this account can verify."""
    out = []

    recovery = recovery_engine.build(user_id)
    if recovery["has_data"] and recovery["total_at_stake"] > 0:
        out.append({
            "route": "/recovery",
            "title": "Collect what your statements already flag",
            "detail": ("%d finding%s on your uploaded rows — $%s actual, "
                       "$%s estimated. Collected revenue is what a multiple "
                       "is applied to."
                       % (recovery["finding_count"],
                          "" if recovery["finding_count"] == 1 else "s",
                          "{:,.2f}".format(recovery["actual_unattributed"]),
                          "{:,.2f}".format(recovery["estimated_gaps"]))),
            "impact": "${:,.2f} at stake".format(recovery["total_at_stake"]),
        })

    if view["source_count"] < 3:
        out.append({
            "route": "/statements",
            "title": "Upload statements from more sources",
            "detail": ("This valuation reads %d source%s. Income spread "
                       "across three or more is the difference between a "
                       "buyer's low multiple and their mid one."
                       % (view["source_count"],
                          "" if view["source_count"] == 1 else "s")),
            "impact": "%d of 3 sources" % view["source_count"],
        })

    if view["months"] < 6:
        out.append({
            "route": "/statements",
            "title": "Build up statement history",
            "detail": ("%d month%s on record. A run rate annualised from a "
                       "short history is the weakest kind, and every buyer "
                       "discounts it."
                       % (view["months"], "" if view["months"] == 1 else "s")),
            "impact": "%d of 6 months" % view["months"],
        })

    try:
        trust = trust_score.calculate(user_id)
    except Exception:
        trust = None
    if trust and trust["total"] < 100:
        out.append({
            "route": "/catalog",
            "title": "Clean up rights data",
            "detail": ("Trust Score %d/100. Splits, metadata and paperwork "
                       "are what a buyer's diligence actually checks — "
                       "unresolved, they come off the price."
                       % trust["total"]),
            "impact": "Trust %d/100" % trust["total"],
        })
    return out


def build(user_id):
    """The whole /valuation page for one account. Never seed data."""
    rows = store.get_statement_rows(user_id) if user_id else []
    analysis = statements_engine.analyze(rows) if rows else None
    advance = capital_engine.advance_eligibility(user_id) if user_id else None

    if analysis is None:
        return {"has_data": False, "advance": advance, "monthly": [],
                "months": 0, "source_count": 0, "row_count": 0,
                "tracked_total": 0.0, "monthly_avg": 0.0, "annualized": 0.0,
                "value": {"low": 0, "mid": 0, "high": 0}, "multiples": MULTIPLES,
                "forecast": [], "drivers": [], "thin": True}

    monthly = _monthly(rows)
    amounts = [m["amount"] for m in monthly]
    # Rows with no period still count as tracked revenue, but they cannot
    # be placed in a month, so the run rate is built from the months.
    months = len(amounts)
    monthly_avg = round(sum(amounts) / months, 2) if months else 0.0
    annualized = round(monthly_avg * 12, 2)

    view = {
        "has_data": True,
        "row_count": analysis["row_count"],
        "source_count": analysis["source_count"],
        "tracked_total": analysis["total"],
        "monthly": monthly,
        "months": months,
        "monthly_avg": monthly_avg,
        "annualized": annualized,
        "multiples": MULTIPLES,
        "value": {k: round(annualized * m) for k, m in MULTIPLES.items()},
        # One or two months is evidence of a month or two, not of a year.
        "thin": months < 3,
        # A statement with no period column cannot be annualised at all.
        "no_periods": months == 0,
        "undated_rows": sum(1 for r in rows if not (r.get("period") or "").strip()),
        "advance": advance,
    }

    if months:
        worst, best = min(amounts), max(amounts)
        view["month_low"], view["month_high"] = worst, best
        view["forecast"] = [
            {"label": "Worst month on record", "monthly": round(worst, 2),
             "d30": round(worst, 2), "d90": round(worst * 3, 2),
             "y1": round(worst * 12, 2)},
            {"label": "Average month", "monthly": monthly_avg,
             "d30": monthly_avg, "d90": round(monthly_avg * 3, 2),
             "y1": annualized},
            {"label": "Best month on record", "monthly": round(best, 2),
             "d30": round(best, 2), "d90": round(best * 3, 2),
             "y1": round(best * 12, 2)},
        ]
    else:
        view["forecast"] = []

    view["drivers"] = _drivers(user_id, view)
    return view
