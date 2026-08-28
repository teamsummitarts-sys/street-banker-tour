"""The producer's side: beats, licences, a cleared list, and usage cases.

What this is not, stated first because the temptation to claim it is
the whole problem with this category:

  **This does not scan anything.** Content ID is YouTube's, granted to
  CMS partners, and cross-platform matching means a paid fingerprinting
  vendor. Nothing here listens to audio, crawls a platform, or detects a
  use on its own. A module that implied otherwise would be selling a
  producer the one thing they most want and least able to check.

What it does instead is make the paperwork checkable, which is the part
that actually decides a dispute:

  A **licence** with real terms, signed by the licensee through a
  single-use link - the same token pattern the Lockbox already uses.

  A **cleared list** per beat: the channels, handles, releases and ISRCs
  that are licensed. Its value is not enforcement, because nobody can
  make a platform honour a list. Its value is that a label, distributor
  or supervisor can check one link and see whether a use is covered,
  with the signed licence behind it.

  A **usage case** for a use found by a human: open, contacted,
  invoiced, resolved. A tracker, labelled a tracker.

`clearance_for` is the question the public page answers, and it answers
three ways rather than two: cleared, not cleared, and *no list yet* -
because a beat whose producer has not written a cleared list yet is not
evidence that a given use is unlicensed.
"""

import db as store

LICENCE_TYPES = [
    ("lease", "Non-exclusive lease"),
    ("exclusive", "Exclusive"),
    ("work_for_hire", "Work for hire"),
    ("free", "Free / promotional"),
]
LICENCE_STATUSES = ["draft", "sent", "signed", "expired", "revoked"]

CLEARANCE_KINDS = [
    ("channel", "Channel or page"),
    ("handle", "Social handle"),
    ("release", "Release title"),
    ("isrc", "ISRC"),
]

USE_STATUSES = ["open", "contacted", "invoiced", "resolved", "cleared"]


def _norm(value):
    return " ".join((value or "").split()).strip().lower()


def clearance_for(beat_id, value):
    """Is this channel / handle / release / ISRC cleared on this beat?

    Three answers, not two. "No list yet" is not "not cleared": a
    producer who has licensed a beat and not written the list down has
    not thereby made every use of it an infringement.
    """
    rows = store.list_beat_clearances(beat_id)
    if not rows:
        return {"state": "unknown", "match": None,
                "detail": "This beat has no cleared list yet, so this page "
                          "cannot say either way. Ask the producer."}
    needle = _norm(value)
    for row in rows:
        if needle and needle == _norm(row["value"]):
            return {"state": "cleared", "match": row,
                    "detail": "Listed as cleared by the producer."}
    return {"state": "not_listed", "match": None,
            "detail": "Not on this beat's cleared list. That means it is "
                      "not listed - the producer may still have licensed "
                      "it elsewhere, so treat this as a reason to ask."}


def licence_label(key):
    return dict(LICENCE_TYPES).get(key, key.replace("_", " ").title())


def beat_summary(beat_id):
    """Counts the beat page leads with, all from rows."""
    licences = store.list_beat_licences(beat_id)
    cleared = store.list_beat_clearances(beat_id)
    signed = [l for l in licences if l["status"] == "signed"]
    return {
        "licences": len(licences),
        "signed": len(signed),
        "unsigned": len([l for l in licences if l["status"] in ("draft", "sent")]),
        "exclusive": any(l["licence_type"] == "exclusive"
                         and l["status"] == "signed" for l in licences),
        "cleared": len(cleared),
        "fees_agreed": round(sum(l["fee"] or 0 for l in signed), 2),
    }


def desk(user_id):
    """Everything the /beats index shows, for both ends of a licence."""
    beats = store.list_beats(user_id)
    rows = []
    for beat in beats:
        rows.append({"beat": beat, "summary": beat_summary(beat["id"])})
    uses = store.list_beat_uses(user_id)
    open_uses = [u for u in uses if u["status"] in ("open", "contacted", "invoiced")]
    user = store.get_user(user_id) or {}
    held = store.licences_for_licensee(user.get("email") or "")
    return {
        "rows": rows,
        "beats": beats,
        "uses": uses,
        "open_uses": open_uses,
        "recovered": round(sum(u["resolved_amount"] or 0 for u in uses
                               if u["status"] == "resolved"), 2),
        # The other end: licences this account has been granted by
        # somebody else. A producer is usually also somebody's licensee.
        "held": held,
        "signed_beats": sum(1 for r in rows if r["summary"]["signed"]),
    }
