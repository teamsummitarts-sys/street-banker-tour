"""Signal Audio Briefs - the week's findings, read aloud.

WHAT IS SPOKEN IS WHAT IS IN THE TABLE
--------------------------------------
The script is assembled from real alert rows by a template. No sentence in a
brief is generated, inferred or summarised - every number and name is read
straight out of the database, and when there is nothing to report the brief
says exactly that rather than filling the time.

This matters more here than almost anywhere else in the product. A brief is
listened to while driving. Nobody cross-checks a voice, and a spoken number
carries more authority than the same number on a screen, so a brief that
smoothed over a gap in the data would be believed.

WHY THE SCRIPT IS SAVED ALONGSIDE THE AUDIO
-------------------------------------------
Audio cannot be skimmed, searched or quoted, and it cannot be checked against
a source without listening to the whole thing. Every brief keeps its exact
script, so what was said is readable afterwards.

MOCK BRIEFS ARE SILENT ON PURPOSE
---------------------------------
With no provider configured the speech adapter returns a correctly-formed WAV
of silence. Silence rather than a tone or a stock voice: a demo that plays
audible speech gets mistaken for a working one, and somebody eventually ships
it to a client.
"""
import uuid

from db import get_db, _now

# How far back a brief looks. A week, because that is the rhythm the Signal
# alerts themselves are tuned to and a daily brief on weekly data is mostly
# silence.
DEFAULT_WINDOW_DAYS = 7

# Above this the brief stops listing and starts counting. A spoken list of
# forty artists is not information, it is noise with a number in it.
MAX_SPOKEN_ITEMS = 8


def _uid():
    return uuid.uuid4().hex


def _row(r):
    return dict(r) if r is not None else None


def init_briefs():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS signal_briefs (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                organization_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                script TEXT NOT NULL DEFAULT '',
                window_days INTEGER NOT NULL DEFAULT 7,
                item_count INTEGER NOT NULL DEFAULT 0,
                job_id TEXT,
                audio_asset_id TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                is_mock INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_briefs_org
                ON signal_briefs(organization_id, created_at);
        """)


# --- composing --------------------------------------------------------------

def _plural(count, singular, plural=None):
    return singular if count == 1 else (plural or singular + "s")


def compose_script(alerts, window_days=DEFAULT_WINDOW_DAYS, org_name=""):
    """Turn alert rows into something a voice can read.

    Deterministic and total: the same rows always produce the same script,
    and a script is always produced - including for no rows at all, which is
    a real finding and is said out loud rather than skipped.
    """
    lines = []
    opening = "This is your Signal brief"
    if org_name:
        opening += " for %s" % org_name
    opening += ", covering the last %d days." % window_days
    lines.append(opening)

    if not alerts:
        # Said plainly. "Nothing to report" is information; silence is a bug
        # the listener cannot distinguish from a broken player.
        lines.append("Nothing crossed an alert threshold in that window. "
                     "That is not the same as nothing happening, so the "
                     "dashboard is still worth a look.")
        lines.append("End of brief.")
        return "\n".join(lines)

    by_severity = {}
    for alert in alerts:
        by_severity.setdefault(alert.get("severity") or "info", []).append(alert)

    total = len(alerts)
    lines.append("There %s %d %s." % (_plural(total, "is", "are"), total,
                                      _plural(total, "alert")))

    for severity in ("critical", "warning", "info"):
        group = by_severity.get(severity) or []
        if not group:
            continue
        lines.append("%d %s %s." % (len(group), _plural(len(group), "is", "are"),
                                    _severity_word(severity, len(group))))
        for alert in group[:MAX_SPOKEN_ITEMS]:
            lines.append(_speak_alert(alert))
        if len(group) > MAX_SPOKEN_ITEMS:
            remaining = len(group) - MAX_SPOKEN_ITEMS
            lines.append("There %s %d more, which you can read on the "
                         "alerts page." % (_plural(remaining, "is", "are"), remaining))

    lines.append("End of brief.")
    return "\n".join(lines)


def _severity_word(severity, count):
    words = {"critical": ("critical", "critical"),
             "warning": ("a warning", "warnings"),
             "info": ("for information", "for information")}
    single, many = words.get(severity, (severity, severity))
    return single if count == 1 else many


def _speak_alert(alert):
    """One alert, as a sentence. The artist's name leads because that is what
    a listener is holding in their head."""
    name = (alert.get("canonical_name") or "").strip()
    title = (alert.get("title") or "").strip().rstrip(".")
    body = (alert.get("body") or "").strip().rstrip(".")

    if name and title:
        sentence = "%s: %s" % (name, title)
    else:
        sentence = title or name or "An alert with no title"

    # The body is included only when it adds something the title did not. A
    # voice repeating itself is how a listener stops paying attention.
    if body and body.lower() not in sentence.lower():
        sentence += ". %s" % body
    return sentence + "."


# --- storage ----------------------------------------------------------------

def create_brief(organization_id, script, created_by="", title="",
                 window_days=DEFAULT_WINDOW_DAYS, item_count=0, partner_id=None):
    bid = _uid()
    with get_db() as db:
        db.execute(
            "INSERT INTO signal_briefs (id, partner_id, organization_id, title, "
            "script, window_days, item_count, status, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?, 'draft', ?, ?)",
            (bid, partner_id, organization_id,
             (title or "Signal brief")[:160], script, int(window_days),
             int(item_count), created_by, _now()))
    return get_brief(bid, partner_id)


def get_brief(brief_id, partner_id=None):
    with get_db() as db:
        return _row(db.execute(
            "SELECT * FROM signal_briefs WHERE id = ? AND partner_id IS ?",
            (brief_id, partner_id)).fetchone())


def list_briefs(organization_id, partner_id=None, limit=50):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM signal_briefs WHERE organization_id = ? AND partner_id IS ? "
            "ORDER BY created_at DESC LIMIT ?",
            (organization_id, partner_id, limit)).fetchall()]


def set_brief_audio(brief_id, partner_id=None, job_id=None, audio_asset_id=None,
                    status=None, is_mock=None):
    sets, args = [], []
    for column, value in (("job_id", job_id), ("audio_asset_id", audio_asset_id),
                          ("status", status)):
        if value is not None:
            sets.append("%s = ?" % column)
            args.append(value)
    if is_mock is not None:
        sets.append("is_mock = ?")
        args.append(1 if is_mock else 0)
    if not sets:
        return False
    args.extend([brief_id, partner_id])
    with get_db() as db:
        cur = db.execute("UPDATE signal_briefs SET %s WHERE id = ? AND partner_id IS ?"
                         % ", ".join(sets), args)
    return cur.rowcount > 0


def delete_brief(brief_id, partner_id=None):
    with get_db() as db:
        db.execute("DELETE FROM signal_briefs WHERE id = ? AND partner_id IS ?",
                   (brief_id, partner_id))
