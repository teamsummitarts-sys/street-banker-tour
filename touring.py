"""Show advancing — the tour-manager checklist as code.

The Advance Builder is rule-based on purpose: it assembles the email a
tour manager would send from the show's actual data, listing what's
confirmed and asking for exactly what's missing. No model, no guessing,
and it says so in the UI.
"""

# (key, label, group, ask) — ask is the question the email raises when
# the field is still blank.
ADVANCE_FIELDS = [
    ("contact_name",  "Venue contact",       "contacts", "Who is our advance contact?"),
    ("contact_email", "Contact email",       "contacts", None),
    ("dayof_contact", "Day-of contact & phone", "contacts", "Who do we call on show day?"),
    ("load_in",       "Load-in time",        "schedule", "What time is load-in?"),
    ("soundcheck",    "Soundcheck time",     "schedule", "When do we soundcheck?"),
    ("doors",         "Doors",               "schedule", "What time are doors?"),
    ("set_time",      "Set time & length",   "schedule", "What's our set time and length?"),
    ("curfew",        "Curfew",              "schedule", "Is there a curfew?"),
    ("backline",      "Backline provided",   "logistics", "What backline does the house provide?"),
    ("parking",       "Parking / load-in access", "logistics", "Where do we park and load in?"),
    ("hospitality",   "Green room / hospitality", "logistics", "What's the hospitality situation?"),
    ("guest_list",    "Guest list count",    "logistics", "How many guest-list spots do we get?"),
    ("merch_setup",   "Merch table",         "logistics", "Is there a merch table, and does the house take a cut?"),
    ("deal",          "Deal / guarantee",    "money", "Can you confirm the deal in writing?"),
    ("payout",        "Payout method & who settles", "money", "How and with whom do we settle at night's end?"),
]

FIELD_KEYS = [f[0] for f in ADVANCE_FIELDS]
# Enough to call a show "advanced" — money + schedule + a human to call.
CORE_KEYS = ("dayof_contact", "load_in", "set_time", "deal", "payout")


def checklist(advance):
    """[{key, label, done}] for every advance field."""
    advance = advance or {}
    return [{"key": k, "label": label, "done": bool((advance.get(k) or "").strip())}
            for k, label, _g, _a in ADVANCE_FIELDS]


def progress(advance):
    items = checklist(advance)
    done = len([i for i in items if i["done"]])
    return {"done": done, "total": len(items),
            "pct": round(100 * done / len(items)),
            "core_ready": all((advance or {}).get(k, "").strip() for k in CORE_KEYS)}


def advance_email(show, advance, artist_name, share_url):
    """The advance email, built from real data: confirms what we know,
    asks only what's missing. Returns {subject, body} (plain text)."""
    advance = advance or {}
    date_str = show.get("date") or "TBD"
    subject = "Advance: %s @ %s — %s" % (artist_name, show.get("venue") or "your venue", date_str)
    lines = ["Hi%s," % ((" " + advance["contact_name"].split()[0])
                        if (advance.get("contact_name") or "").strip() else ""),
             "",
             "%s here, advancing our %s show at %s%s." % (
                 artist_name, date_str, show.get("venue") or "your room",
                 (" in " + show["city"]) if show.get("city") else ""),
             ""]
    confirmed = [(label, advance[k].strip()) for k, label, _g, _a in ADVANCE_FIELDS
                 if (advance.get(k) or "").strip()]
    if confirmed:
        lines.append("What we have so far — flag anything that's wrong:")
        for label, val in confirmed:
            lines.append("  • %s: %s" % (label, val))
        lines.append("")
    questions = [ask for k, _l, _g, ask in ADVANCE_FIELDS
                 if ask and not (advance.get(k) or "").strip()]
    if questions:
        lines.append("What we still need:")
        for q in questions:
            lines.append("  • %s" % q)
        lines.append("")
    if share_url:
        lines.append("Our stage plot, input list, and day sheet live here "
                     "(no login needed): %s" % share_url)
        lines.append("")
    lines += ["Thanks — looking forward to it.", "", artist_name]
    return {"subject": subject, "body": "\n".join(lines)}


def settlement_totals(settlement):
    """Plain math, shown with its work: what the night actually paid."""
    s = settlement or {}

    def num(key):
        try:
            return max(0.0, float(s.get(key) or 0))
        except (TypeError, ValueError):
            return 0.0

    deal_type = s.get("deal_type") or "flat"
    guarantee = num("guarantee")
    door_share = round(num("door_gross") * num("split_pct") / 100, 2)
    if deal_type == "flat":
        earnings = guarantee
    elif deal_type == "split":
        earnings = door_share
    else:  # guarantee_split: guarantee plus the agreed door percentage
        earnings = round(guarantee + door_share, 2)
    merch_net = round(num("merch_gross") * (1 - num("merch_cut_pct") / 100), 2)
    expenses = num("expenses")
    return {"deal_type": deal_type, "guarantee": guarantee,
            "door_share": door_share, "merch_net": merch_net,
            "expenses": expenses,
            "walk": round(earnings + merch_net - expenses, 2)}
