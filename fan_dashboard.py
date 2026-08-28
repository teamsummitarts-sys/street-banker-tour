"""The Fan Dashboard, built from the account's own fan records.

WHY THIS EXISTS
---------------
/fans rendered community_config.get_fan_dashboard_data() to every account:
1,240 superfans, 41,000 casual listeners, and a leaderboard of invented
handles spending invented money. Underneath it sat the sentence "the app
doesn't track individual fans" - which was false. The Fan CRM at /links/fans
holds named fans with intent scores, and has since smart links shipped.

That was two problems in one panel. The numbers were somebody else's, and the
disclaimer was a privacy claim the product could not stand behind.

WHAT IS REAL, AND WHAT IS NOT SHOWN
-----------------------------------
Everything here comes from ml_fans, ml_consents and ml_events for the signed-in
account. Nothing is modelled, projected or filled in.

The one thing the old panel showed that is NOT here is money: lifetime value,
spend per fan, a leaderboard by amount. `ml_fans` has no spend column and the
app has no purchase feed, so every one of those figures was invented. They are
gone rather than estimated - a fan-value number an artist might act on is not
something to guess at.

What replaces them is what the records actually hold: how many people have
been captured, how engaged they are, whether they consented, and where they
came from.
"""
import links_store as mls

# The intent bands the smart-link scorer writes into ml_fans.intent_level.
# Ordered hottest first, because that is the order somebody reads them in.
INTENT_ORDER = ["Hot", "Warm", "Cool", "Cold"]

# Above this many fans, the top list stops being a list somebody reads.
TOP_FANS = 8


def _empty(reason):
    """A real account with no fans yet. Says so, and says what makes fans.

    A zero here is not a failure state - it is the honest answer for an artist
    who has not published a smart link yet, and the panel should tell them the
    next step rather than showing them nothing.
    """
    return {
        "is_real": True,
        "has_data": False,
        "reason": reason,
        "summary": {"total_fans": 0, "consented": 0, "qr_scans": 0,
                    "page_views": 0, "presaves": 0},
        "segments": [],
        "top_fans": [],
    }


def fan_dashboard_for(user_id):
    """Real fan data for one account, or an honest empty state."""
    if not user_id:
        return _empty("Sign in to see your own fans.")

    try:
        fans = mls.list_fans(user_id)
    except Exception:
        return _empty("Fan records could not be read.")

    events = {}
    try:
        events = mls.account_event_counts(user_id) or {}
    except Exception:
        pass

    if not fans:
        return _empty("No fans captured yet. Fans appear here when somebody "
                      "gives you their email on a smart link.")

    # Segments are the real distribution of the scorer's own bands, not
    # invented tiers. A band nobody is in is dropped rather than shown as 0.
    counts = {}
    for fan in fans:
        level = (fan.get("intent_level") or "Cold").strip() or "Cold"
        counts[level] = counts.get(level, 0) + 1

    ordered = [level for level in INTENT_ORDER if level in counts]
    ordered += sorted(level for level in counts if level not in INTENT_ORDER)

    total = len(fans)
    segments = []
    for level in ordered:
        n = counts[level]
        members = [f for f in fans if (f.get("intent_level") or "Cold") == level]
        segments.append({
            "segment": level,
            "count": n,
            "share": round(100.0 * n / total, 1) if total else 0.0,
            # Averages over REAL counters. No money, because there is none.
            "avg_visits": _avg(members, "total_visits"),
            "avg_clicks": _avg(members, "total_clicks"),
            "presaves": sum(int(f.get("total_presaves") or 0) for f in members),
        })

    consented = 0
    try:
        for fan in fans:
            if mls.list_consents(fan["id"]):
                consented += 1
    except Exception:
        consented = 0

    return {
        "is_real": True,
        "has_data": True,
        "reason": "",
        "summary": {
            "total_fans": total,
            "consented": consented,
            # Every QR scan is a real ml_events row written by /l/<slug> when
            # the link carried ?src=qr.
            "qr_scans": int(events.get("qr_scan") or 0),
            "page_views": int(events.get("page_view") or 0),
            "presaves": int(events.get("presave") or 0),
        },
        "segments": segments,
        # Ranked by the scorer's own number, which is what the CRM ranks by
        # too - so the two pages cannot disagree about who is most engaged.
        "top_fans": [{
            "name": (f.get("name") or "").strip(),
            "email": f.get("email") or "",
            "intent_score": int(f.get("intent_score") or 0),
            "intent_level": f.get("intent_level") or "Cold",
            "visits": int(f.get("total_visits") or 0),
            "clicks": int(f.get("total_clicks") or 0),
            "presaves": int(f.get("total_presaves") or 0),
        } for f in fans[:TOP_FANS]],
    }


def _avg(rows, field):
    if not rows:
        return 0.0
    return round(sum(int(r.get(field) or 0) for r in rows) / float(len(rows)), 1)
