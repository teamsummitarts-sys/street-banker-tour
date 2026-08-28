"""What actually changed since the artist was last here.

The Overview strip called "What Changed Since Your Last Visit" reported
"+$482.15 new royalties collected", two new payouts, five tasks
completed and a catalog value increase. All five were constants in
royalty_data, and the page had no idea when the last visit was - there
was no such column. So the strip was not stale or approximate, it was
fiction with a timestamp-shaped title, and it said the same thing on a
first login as on a hundredth.

This measures a real window. `db.roll_seen` stamps the visit and hands
back the previous one; every count below is rows created after it, one
query per kind, all filtered to the account.

Rules the strip follows:

  A first visit says so. There is no window to measure yet, and five
  zeros would read as "a quiet week" rather than "no week yet".

  A quiet window says so too, in one line, rather than laying out a
  grid of zeros to fill the space. Nothing happened is a real answer.

  Only kinds that moved are shown. A zero is not news, and five of them
  drown the one number that is.
"""

import db as store


def _plural(n, noun, plural=None):
    return "%d %s" % (n, noun if n == 1 else (plural or noun + "s"))


def build(user_id, since):
    """The strip, or a state explaining why there isn't one."""
    if not user_id:
        return {"first_visit": True, "items": [], "since": None}
    if not since:
        return {"first_visit": True, "items": [], "since": None}

    a = store.activity_since(user_id, since)
    items = []

    if a["statements"]:
        items.append({
            "route": "/statements", "tone": "gold",
            "value": "$%s" % "{:,.2f}".format(a["statement_total"]),
            "label": "tracked in %s" % _plural(a["statements"], "new statement"),
        })
    if a["cases_won"]:
        items.append({
            "route": "/royalty-recovery/cases", "tone": "green",
            "value": "$%s" % "{:,.2f}".format(a["recovered"]),
            "label": "recovered on %s" % _plural(a["cases_won"], "closed case"),
        })
    if a["cases_opened"]:
        items.append({
            "route": "/royalty-recovery/cases", "tone": "plain",
            "value": str(a["cases_opened"]),
            "label": _plural(a["cases_opened"], "recovery case") + " opened",
        })
    if a["fans"]:
        items.append({
            "route": "/fans", "tone": "green", "value": str(a["fans"]),
            "label": _plural(a["fans"], "fan") + " captured",
        })
    if a["visits"] or a["clicks"]:
        items.append({
            "route": "/links", "tone": "plain",
            "value": "%d / %d" % (a["visits"], a["clicks"]),
            "label": "link visits / platform clicks",
        })
    if a["presaves"]:
        items.append({
            "route": "/links", "tone": "gold", "value": str(a["presaves"]),
            "label": _plural(a["presaves"], "pre-save") + " registered",
        })
    if a["documents"]:
        items.append({
            "route": "/documents", "tone": "plain", "value": str(a["documents"]),
            "label": _plural(a["documents"], "document") + " filed",
        })
    if a["notifications"]:
        items.append({
            "route": "/notifications", "tone": "plain",
            "value": str(a["notifications"]),
            "label": _plural(a["notifications"], "notification"),
        })

    return {"first_visit": False, "since": since, "items": items[:5],
            "quiet": not items}
