"""The inbox, belonging to somebody.

The table shipped without an owner column and the page ran one query:
`SELECT * FROM inbox`. Every signed-in account read every row - one
artist's booking enquiries, the pitch emails sent to their one-sheet,
the addresses of people who asked for demo access. Not a display bug; a
leak, and the page could not have been correct without the column.

With ownership in place the page can also stop being a dump of raw
key/value pairs. Each kind knows what it is, which direction it went,
and what the one useful action on it is:

  Received - a pitch on a one-sheet, a licence request on a sync pack.
  Somebody outside the account asked for something, and the useful
  action is replying, so the address is a mailto link.

  Sent - playlist submissions and booking enquiries this account made.
  Kept because a submission you cannot prove you sent is a submission
  you will send twice.

  Records - invoices raised. A trail, not a message.

Rows belonging to no account are platform-level (demo access requests)
and are shown only to an owner account, which is also the only place
legacy rows written before the column existed can honestly appear.
"""

KINDS = {
    "onesheet_pitch": {
        "label": "One-sheet pitch", "group": "received",
        "title": lambda p: p.get("name") or p.get("email") or "Someone",
        "body": lambda p: p.get("message") or "",
        "reply": lambda p: p.get("email") or "",
    },
    "sync_request": {
        "label": "Licence request", "group": "received",
        "title": lambda p: "%s asked about %s" % (
            p.get("email") or "Someone", p.get("pack") or "a sync pack"),
        "body": lambda p: p.get("message") or "",
        "reply": lambda p: p.get("email") or "",
    },
    "playlist_submission": {
        "label": "Playlist submission", "group": "sent",
        "title": lambda p: "Submitted %s" % (p.get("song") or "a track"),
        "body": lambda p: p.get("message") or "",
        "reply": lambda p: "",
    },
    "booking_enquiry": {
        "label": "Booking enquiry", "group": "sent",
        "title": lambda p: "Enquired about %s%s" % (
            p.get("city") or "a show",
            " on %s" % p["date"] if p.get("date") else ""),
        "body": lambda p: p.get("message") or "",
        "reply": lambda p: "",
    },
    "invoice": {
        "label": "Invoice raised", "group": "records",
        "title": lambda p: "Invoice %s to %s" % (
            p.get("number") or "?", p.get("client") or "a client"),
        "body": lambda p: ("%s hours, $%s" % (p.get("hours"), p.get("total"))
                           if p.get("total") is not None else ""),
        "reply": lambda p: "",
    },
    "demo-access": {
        "label": "Demo access request", "group": "platform",
        "title": lambda p: p.get("email") or "Someone",
        "body": lambda p: "%s workspace · password %s" % (
            (p.get("workspace") or "unspecified").title(),
            "sent" if p.get("password_sent") else "not sent"),
        "reply": lambda p: p.get("email") or "",
    },
}

GROUPS = [
    ("received", "Received", "Somebody outside your account asked for something."),
    ("sent", "Sent", "What this account submitted, kept so you can prove you sent it."),
    ("records", "Records", "A trail of what went out."),
    ("platform", "Platform", "Not tied to any account — owner view only."),
]


def _safe(fn, payload, fallback=""):
    """A malformed payload loses its line, not the whole page."""
    try:
        return fn(payload) or fallback
    except Exception:
        return fallback


def present(row):
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    kind = row.get("kind") or "other"
    spec = KINDS.get(kind)
    if spec is None:
        # An unknown kind is still a real submission: show it plainly
        # rather than dropping it, and say that it is unrecognised.
        return {
            "kind": kind, "label": kind.replace("_", " ").title(),
            "group": "records", "title": "Unrecognised submission",
            "body": ", ".join("%s: %s" % (k, v) for k, v in payload.items()),
            "reply": "", "created": row.get("created") or "", "payload": payload,
        }
    return {
        "kind": kind, "label": spec["label"], "group": spec["group"],
        "title": _safe(spec["title"], payload, "Submission"),
        "body": _safe(spec["body"], payload),
        "reply": _safe(spec["reply"], payload),
        "created": row.get("created") or "", "payload": payload,
    }


def build(rows):
    """Group presented rows for the page, dropping empty groups."""
    items = [present(r) for r in rows]
    groups = []
    for key, title, blurb in GROUPS:
        matching = [i for i in items if i["group"] == key]
        if matching:
            groups.append({"key": key, "title": title, "blurb": blurb,
                           "items": matching})
    return {"groups": groups, "count": len(items)}
