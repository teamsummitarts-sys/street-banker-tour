"""The Hours desk: what your time is worth, and where it went.

Four jobs on one page, all reading the same rows:

  Session log     Hours worked against a project and client, at a rate,
                  rolled up into what is unbilled and what an invoice would
                  come to.
  Rate card       What you charge per service, and which of those the
                  public booking form is allowed to offer.
  Collaborator    Hours submitted by other people, approved or rejected,
  hours           with approved hours rolling into what you owe.
  Day plan        The day blocked out hour by hour, with real clashes
                  flagged rather than silently overlapping.

Every total here is summed from stored rows. There are no projections, no
"estimated value of your time", and no invented averages: if you have
logged nothing, the desk says so instead of showing a plausible number.

Pure functions over plain dicts - the same shapes db.py returns - so the
arithmetic can be checked without a database or a request.
"""

from datetime import date, datetime, timedelta

# Anything longer than this in one entry is almost certainly a typo (a date
# typed into the hours box, a doubled digit). Flagged, never silently fixed.
IMPLAUSIBLE_HOURS = 18.0


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value):
    """Round the way an invoice does - two places, half-up on the cent."""
    return round(_f(value) + 1e-9, 2)


def entry_value(entry):
    return money(_f(entry.get("hours")) * _f(entry.get("rate")))


def session_totals(entries):
    """Roll up the session log. Unbilled is the number that matters: it is
    what you are owed and have not asked for yet."""
    unbilled = [e for e in entries if not e.get("billed")]
    billed = [e for e in entries if e.get("billed")]
    total_hours = round(sum(_f(e.get("hours")) for e in entries), 2)
    unbilled_hours = round(sum(_f(e.get("hours")) for e in unbilled), 2)
    return {
        "entries": len(entries),
        "hours": total_hours,
        "value": money(sum(entry_value(e) for e in entries)),
        "unbilled_count": len(unbilled),
        "unbilled_hours": unbilled_hours,
        "unbilled_value": money(sum(entry_value(e) for e in unbilled)),
        "billed_count": len(billed),
        "billed_value": money(sum(entry_value(e) for e in billed)),
        # A blended rate is only meaningful once there are hours to blend.
        "effective_rate": (money(sum(entry_value(e) for e in entries)
                                 / total_hours) if total_hours else None),
    }


def group_by_client(entries):
    """Unbilled work grouped the way you would invoice it: one client and
    project at a time, because that is what becomes one invoice."""
    groups = {}
    for e in entries:
        if e.get("billed"):
            continue
        key = ((e.get("client") or "").strip(), (e.get("project") or "").strip())
        g = groups.setdefault(key, {"client": key[0], "project": key[1],
                                    "ids": [], "hours": 0.0, "value": 0.0,
                                    "days": set()})
        g["ids"].append(e.get("id"))
        g["hours"] += _f(e.get("hours"))
        g["value"] += entry_value(e)
        if e.get("day"):
            g["days"].add(e["day"])
    out = []
    for g in groups.values():
        days = sorted(g["days"])
        out.append({"client": g["client"], "project": g["project"],
                    "ids": g["ids"], "count": len(g["ids"]),
                    "hours": round(g["hours"], 2), "value": money(g["value"]),
                    "first_day": days[0] if days else "",
                    "last_day": days[-1] if days else ""})
    out.sort(key=lambda g: (-g["value"], g["client"]))
    return out


def next_invoice_number(invoices, today=None):
    """SB-YYYY-NNN, counting only this year's invoices, so the sequence
    restarts cleanly each January instead of climbing forever."""
    year = (today or date.today()).year
    prefix = "SB-%d-" % year
    used = 0
    for inv in invoices:
        num = (inv.get("number") or "")
        if num.startswith(prefix):
            tail = num[len(prefix):]
            if tail.isdigit():
                used = max(used, int(tail))
    return "%s%03d" % (prefix, used + 1)


def invoice_totals(invoices):
    outstanding = [i for i in invoices if i.get("status") != "paid"]
    paid = [i for i in invoices if i.get("status") == "paid"]
    return {
        "count": len(invoices),
        "outstanding_count": len(outstanding),
        "outstanding": money(sum(_f(i.get("total")) for i in outstanding)),
        "paid_count": len(paid),
        "paid": money(sum(_f(i.get("total")) for i in paid)),
    }


def booking_totals(bookings):
    """Confirmed bookings are money you have agreed to earn; requested ones
    are not, and are counted separately so the two never blur."""
    req = [b for b in bookings if b.get("status") == "requested"]
    conf = [b for b in bookings if b.get("status") == "confirmed"]
    return {
        "requested_count": len(req),
        "requested_value": money(sum(_f(b.get("hours")) * _f(b.get("rate"))
                                     for b in req)),
        "confirmed_count": len(conf),
        "confirmed_hours": round(sum(_f(b.get("hours")) for b in conf), 2),
        "confirmed_value": money(sum(_f(b.get("hours")) * _f(b.get("rate"))
                                     for b in conf)),
    }


def submission_totals(subs):
    """What collaborators are owed. Pending is a liability you have not
    agreed to yet; approved is one you have."""
    pend = [s for s in subs if s.get("status") == "pending"]
    appr = [s for s in subs if s.get("status") == "approved"]
    rej = [s for s in subs if s.get("status") == "rejected"]
    return {
        "pending_count": len(pend),
        "pending_hours": round(sum(_f(s.get("hours")) for s in pend), 2),
        "pending_value": money(sum(_f(s.get("hours")) * _f(s.get("rate"))
                                   for s in pend)),
        "approved_count": len(appr),
        "approved_hours": round(sum(_f(s.get("hours")) for s in appr), 2),
        "approved_value": money(sum(_f(s.get("hours")) * _f(s.get("rate"))
                                    for s in appr)),
        "rejected_count": len(rej),
    }


def bookable_services(rates):
    """Only lines explicitly marked bookable are offered publicly - a rate
    you keep for reference should not become a thing strangers can book."""
    return [r for r in rates if r.get("bookable")]


def fmt_hour(hour):
    """0.0 -> 00:00, 13.5 -> 13:30. Quarter hours are as fine as the desk
    goes, which is finer than anybody bills."""
    h = max(0.0, min(24.0, _f(hour)))
    whole = int(h)
    mins = int(round((h - whole) * 60))
    if mins >= 60:
        whole, mins = whole + 1, 0
    return "%02d:%02d" % (whole, mins)


def block_span(block):
    start = _f(block.get("start_hour"))
    return start, start + _f(block.get("hours"))


def find_clashes(blocks):
    """Which blocks actually overlap, as a set of ids. Two things booked
    into the same hour is a real problem worth showing, and it is cheap to
    detect properly rather than leaving the user to spot it."""
    clashing = set()
    ordered = sorted(blocks, key=lambda b: _f(b.get("start_hour")))
    for i, a in enumerate(ordered):
        a0, a1 = block_span(a)
        for b in ordered[i + 1:]:
            b0, b1 = block_span(b)
            if b0 >= a1:
                break              # sorted, so nothing later can overlap
            if b0 < a1 and a0 < b1:
                clashing.add(a.get("id"))
                clashing.add(b.get("id"))
    return clashing


def day_plan(blocks, bookings=None, day=None, from_hour=8, to_hour=22):
    """The day as a list of hour rows, each carrying whatever sits in it.

    Confirmed bookings are folded in as blocks so a session someone booked
    cannot be double-booked by the plan - they are the same day, and
    pretending otherwise is how two things end up at 3pm.
    """
    items = [dict(b, source="plan") for b in blocks]
    for bk in (bookings or []):
        if bk.get("status") != "confirmed":
            continue
        if day and bk.get("day") != day:
            continue
        items.append({"id": "bk-" + str(bk.get("id")),
                      "start_hour": bk.get("start_hour"),
                      "hours": bk.get("hours"),
                      "label": (bk.get("service") or "Session")
                               + (" · " + bk["who"] if bk.get("who") else ""),
                      "kind": "booking", "done": 0, "source": "booking"})
    clashes = find_clashes(items)
    rows = []
    for hour in range(int(from_hour), int(to_hour) + 1):
        here = []
        for it in items:
            s, e = block_span(it)
            if s < hour + 1 and e > hour:
                here.append(dict(it, clash=it.get("id") in clashes,
                                 starts_here=int(s) == hour,
                                 span=fmt_hour(s) + "–" + fmt_hour(e)))
        # Named "blocks", not "items": in a template, row.items resolves to
        # dict.items - the method - and silently iterates the wrong thing.
        rows.append({"hour": hour, "label": fmt_hour(hour), "blocks": here})
    planned = round(sum(_f(i.get("hours")) for i in items), 2)
    return {
        "rows": rows,
        "planned_hours": planned,
        "free_hours": round(max(0.0, (to_hour - from_hour + 1) - planned), 2),
        # Count the blocks caught in a clash, not "pairs": three things in
        # the same hour is three pairs but only three blocks, and halving
        # the id count would misreport it either way.
        "clash_items": len(clashes),
        "block_count": len(items),
    }


def flag_entry(entry):
    """Anything worth a second look before it becomes an invoice line."""
    notes = []
    hours = _f(entry.get("hours"))
    if hours <= 0:
        notes.append("no hours logged")
    elif hours > IMPLAUSIBLE_HOURS:
        notes.append("%.2g hours in one entry — typo?" % hours)
    if _f(entry.get("rate")) <= 0:
        notes.append("no rate — this bills at zero")
    if not (entry.get("client") or "").strip():
        notes.append("no client — cannot be invoiced")
    return notes


def desk_summary(entries, invoices, bookings, subs):
    """One honest headline. What you are owed is unbilled work plus invoices
    that have gone out and not come back; what you owe is approved
    collaborator hours. Pending anything is excluded on purpose - it is not
    agreed money in either direction."""
    st = session_totals(entries)
    iv = invoice_totals(invoices)
    sub = submission_totals(subs)
    bk = booking_totals(bookings)
    owed = money(st["unbilled_value"] + iv["outstanding"])
    return {
        "owed_to_you": owed,
        "unbilled_value": st["unbilled_value"],
        "outstanding_invoiced": iv["outstanding"],
        "you_owe": sub["approved_value"],
        "net": money(owed - sub["approved_value"]),
        "logged_hours": st["hours"],
        "awaiting_you": sub["pending_count"],
        "booking_requests": bk["requested_count"],
        "has_data": bool(entries or invoices or bookings or subs),
    }


def week_days(today=None, back=6):
    """The last seven dates, oldest first, for the log's day picker."""
    base = today or date.today()
    return [(base - timedelta(days=n)).strftime("%Y-%m-%d")
            for n in range(back, -1, -1)]


def parse_day(value, fallback=None):
    try:
        return datetime.strptime((value or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return fallback or date.today()
