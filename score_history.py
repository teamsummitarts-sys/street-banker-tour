"""Scores over time, so the app can say whether an artist is improving.

Qualification, Trust, Capital Readiness and the catalog valuation are all
computed on every request and stored nowhere. That is fine for answering
"where do I stand" and useless for "am I getting anywhere", which is the
question an artist actually has. A score with no history is a number; a
score with history is feedback.

Two rules shape everything here.

  One row per score per day. These recompute on every page load, so
  appending on each call would write hundreds of identical rows a day and
  turn a trend into noise. The day's row is updated in place instead, and
  the last value of the day is the one that stands.

  A trend needs two points. With one reading there is no delta and this
  module says so rather than showing +0, which reads as "no progress"
  when the truth is "no comparison yet".

Pure functions over rows, so the arithmetic can be tested without a
database.
"""

# What can be recorded. A closed set, because a typo in a kind string
# would silently create a second, empty history for the same score.
KINDS = {
    "qualification": "Qualification Score",
    "trust": "Trust Score",
    "capital": "Capital Readiness",
    "valuation": "Catalog Valuation",
    "master": "Master Quality",
}

# Comparison window, in days. Roughly a working week: long enough that
# ordinary noise averages out, short enough to still feel like feedback.
COMPARE_DAYS = 7


def _as_number(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None       # reject NaN


def delta(rows, days=COMPARE_DAYS):
    """Movement between the newest reading and the best comparison point.

    `rows` are dicts with `total` and `day`, newest first - the shape
    db.score_trend returns.

    Returns None when there is nothing honest to compare against, which
    is a different answer from zero movement and has to stay different.
    """
    clean = [r for r in rows if _as_number(r.get("total")) is not None]
    if len(clean) < 2:
        return None
    latest = clean[0]
    now = _as_number(latest["total"])

    # The oldest reading inside the window; failing that, the oldest we
    # have. An artist who last opened the app a month ago should still
    # get a comparison rather than nothing.
    window = clean[:days] if len(clean) > days else clean
    prior = window[-1]
    before = _as_number(prior["total"])
    if before is None:
        return None

    change = round(now - before, 2)
    if change > 0:
        direction = "up"
    elif change < 0:
        direction = "down"
    else:
        direction = "flat"
    return {
        "now": now, "before": before, "change": change,
        "direction": direction,
        "abs_change": abs(change),
        "from_day": prior.get("day"), "to_day": latest.get("day"),
        "readings": len(clean),
        # Percent only where it means something. A 4-point move from zero
        # is not an infinite improvement.
        "pct": (round(change / before * 100) if before else None),
    }


def sparkline(rows, points=12):
    """Oldest-to-newest totals for a small inline chart."""
    clean = [_as_number(r.get("total")) for r in rows
             if _as_number(r.get("total")) is not None]
    return list(reversed(clean[:points]))


def phrase(kind, d):
    """One line an artist can read, or None when there is nothing to say."""
    label = KINDS.get(kind, kind)
    if not d:
        return None
    if d["direction"] == "flat":
        return "%s unchanged at %g since %s." % (label, d["now"], d["from_day"])
    return "%s %s %g point%s since %s, now %g." % (
        label, "up" if d["direction"] == "up" else "down",
        d["abs_change"], "" if d["abs_change"] == 1 else "s",
        d["from_day"], d["now"])


def summarise(kind, rows):
    """Everything a page needs about one score's history."""
    d = delta(rows)
    return {
        "kind": kind, "label": KINDS.get(kind, kind),
        "delta": d, "spark": sparkline(rows),
        "phrase": phrase(kind, d),
        "readings": len(rows),
        # With one reading the honest statement is that tracking started,
        # not that nothing has changed.
        "note": (None if d else
                 ("Tracking from today — check back to see movement."
                  if rows else None)),
    }
