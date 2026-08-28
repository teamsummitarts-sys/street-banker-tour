"""Operator Desk Meeting Intelligence - storage, extraction, approval.

WHAT THIS DOES, AND WHAT IT DOES NOT CLAIM
------------------------------------------
It turns a recording into a transcript with speakers and timestamps, and then
it reads that transcript for PHRASES that usually mean somebody committed to
something. It surfaces those as candidates for a person to approve.

It does not understand the meeting. The audio seam supplies audio
capabilities - transcription, speech, agents - and there is no
language-reasoning provider behind it. An extractor that claimed to know what
was decided would be inventing the most consequential part of the record, and
the record of a meeting is the thing a deal later turns on.

So the extraction is deterministic and rule-based, every candidate carries the
exact sentence it came from, and the UI says it was matched on phrasing. A
person promotes a candidate to a task or a note; nothing reaches the lead on
its own.

CONSENT IS NOT A CHECKBOX HERE
------------------------------
Recording a meeting is the one audio operation in this product that involves
people who are not the user. `meeting_recording` carries a consent
requirement through audio_policy.gate(), and DEFAULT_POLICY has it OFF. An
uploaded file the operator already holds is a different act from recording a
live conversation, and they are separate features for that reason.

TENANCY
-------
Meetings hang off the Operator Desk, which is internal and single-tenant
today. partner_id is carried anyway so that when a reseller gets a Desk, the
rows already know whose they are.
"""
import json
import re
import sqlite3
import uuid

from db import get_db, _now

# What a candidate can become. Deliberately small: a meeting produces work and
# a record, and anything more elaborate is somebody's guess about intent.
CANDIDATE_KINDS = ("action", "decision", "risk", "date")

CANDIDATE_STATUSES = ("pending", "approved", "dismissed")


def _uid():
    return uuid.uuid4().hex


def _row(r):
    return dict(r) if r is not None else None


def init_meetings():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS desk_meetings (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                lead_id TEXT,
                title TEXT NOT NULL DEFAULT '',
                held_on TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'upload',
                audio_asset_id TEXT,
                job_id TEXT,
                transcript_id TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                is_mock INTEGER NOT NULL DEFAULT 0,
                consent_recorded INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            /* Every candidate keeps the sentence it came from and the
               millisecond it was said. A suggestion a person cannot check
               against the recording is a suggestion they have to take on
               faith, which is exactly what this must not ask of them. */
            CREATE TABLE IF NOT EXISTS desk_meeting_candidates (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                meeting_id TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'action',
                text TEXT NOT NULL DEFAULT '',
                quote TEXT NOT NULL DEFAULT '',
                speaker TEXT NOT NULL DEFAULT '',
                start_ms INTEGER NOT NULL DEFAULT 0,
                matched_on TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                decided_by TEXT NOT NULL DEFAULT '',
                decided_at TEXT,
                promoted_kind TEXT NOT NULL DEFAULT '',
                promoted_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_meetings_lead
                ON desk_meetings(lead_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_meeting_cand
                ON desk_meeting_candidates(meeting_id, status);
        """)


# --- meetings ---------------------------------------------------------------

def create_meeting(title, created_by, lead_id=None, partner_id=None,
                   held_on="", source="upload", consent_recorded=False,
                   audio_asset_id=None):
    mid = _uid()
    with get_db() as db:
        db.execute(
            "INSERT INTO desk_meetings (id, partner_id, lead_id, title, held_on, "
            "created_by, source, audio_asset_id, status, consent_recorded, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,'new',?,?)",
            (mid, partner_id, lead_id, (title or "Untitled meeting")[:200],
             held_on or _now()[:10], created_by, source, audio_asset_id,
             1 if consent_recorded else 0, _now()))
    return get_meeting(mid, partner_id)


def get_meeting(meeting_id, partner_id=None):
    with get_db() as db:
        return _row(db.execute(
            "SELECT * FROM desk_meetings WHERE id = ? AND partner_id IS ?",
            (meeting_id, partner_id)).fetchone())


def list_meetings(partner_id=None, lead_id=None, limit=100):
    query = "SELECT * FROM desk_meetings WHERE partner_id IS ?"
    args = [partner_id]
    if lead_id:
        query += " AND lead_id = ?"
        args.append(lead_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with get_db() as db:
        return [dict(r) for r in db.execute(query, args).fetchall()]


def set_meeting_job(meeting_id, partner_id, job_id=None, transcript_id=None,
                    status=None, is_mock=None):
    sets, args = [], []
    for column, value in (("job_id", job_id), ("transcript_id", transcript_id),
                          ("status", status)):
        if value is not None:
            sets.append("%s = ?" % column)
            args.append(value)
    if is_mock is not None:
        sets.append("is_mock = ?")
        args.append(1 if is_mock else 0)
    if not sets:
        return False
    args.extend([meeting_id, partner_id])
    with get_db() as db:
        cur = db.execute("UPDATE desk_meetings SET %s WHERE id = ? AND partner_id IS ?"
                         % ", ".join(sets), args)
    return cur.rowcount > 0


def delete_meeting(meeting_id, partner_id=None):
    with get_db() as db:
        db.execute("DELETE FROM desk_meeting_candidates WHERE meeting_id = ?",
                   (meeting_id,))
        db.execute("DELETE FROM desk_meetings WHERE id = ? AND partner_id IS ?",
                   (meeting_id, partner_id))


# --- the extractor ----------------------------------------------------------
#
# Each rule is (kind, label, compiled pattern). The label is shown to the
# person as the reason this sentence was picked, so it has to be readable:
# "somebody said they would" is checkable, "NLP confidence 0.82" is not.
#
# These are matched on PHRASING. They will pick up sentences that are not
# commitments and miss commitments phrased unusually, which is why nothing
# here reaches a lead without somebody saying yes.
#
# ORDER MATTERS: the first rule to match wins, and action rules come first
# deliberately. "We agreed that I will send the contract by Friday" is both a
# decision and an action; classifying it as an action is what puts a task in
# front of somebody, and the sentence is shown either way. Reordering these
# changes what the meeting produces, so it is a decision, not a list.

_RULES = [
    ("action", "somebody said they would",
     re.compile(r"\b(i|we)\s+(will|'ll|am going to|are going to|can)\s+\w+", re.I)),
    ("action", "somebody was asked to",
     re.compile(r"\b(can|could|would)\s+you\s+\w+", re.I)),
    # "let us" as well as "let's": transcription engines expand contractions
    # inconsistently, and the unexpanded form is the one a regex written by
    # hand tends to forget. A missed next step is a task nobody was offered.
    ("action", "a next step was named",
     re.compile(r"\b(let's|lets|let us|we should|we need to|next step|"
                r"action item)\b", re.I)),
    ("action", "something was promised to be sent",
     re.compile(r"\b(i'll|i will|we'll|we will)\s+(send|share|forward|email|pull)\b", re.I)),

    ("decision", "an agreement was stated",
     re.compile(r"\b(we (agreed|decided)|agreed to|decision is|we're going with|"
                r"we are going with)\b", re.I)),
    ("decision", "a commitment was refused or deferred",
     re.compile(r"\b(i do not want to|i don't want to|not going to commit|"
                r"we won't|we will not)\b", re.I)),

    ("risk", "uncertainty was expressed",
     re.compile(r"\b(i am not sure|i'm not sure|least sure|worried|concern|"
                r"risk|problem|unclear)\b", re.I)),
    ("risk", "a dependency on somebody else was named",
     re.compile(r"\b(waiting on|blocked by|depends on|until we (hear|see))\b", re.I)),

    ("date", "a time was named",
     re.compile(r"\b(by (monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                r"next week|next month|the end of \w+)|before the release|"
                r"same week|this week|next week)\b", re.I)),
]

# Sentences shorter than this are almost always fragments of the previous one
# and read as nonsense on their own.
_MIN_SENTENCE = 18


def _sentences(text):
    for raw in re.split(r"(?<=[.!?])\s+", text or ""):
        cleaned = raw.strip()
        if len(cleaned) >= _MIN_SENTENCE:
            yield cleaned


def extract_candidates(segments):
    """Read a transcript for phrases that usually mean a commitment.

    `segments` is the transcript's segment list: speaker, start_ms, text.
    Returns candidate dicts, deduplicated on the sentence, in the order they
    were said. Every one carries its quote so a person can check it.
    """
    seen = set()
    out = []
    for segment in segments or []:
        speaker = segment.get("speaker") or ""
        start = int(segment.get("start_ms") or 0)
        for sentence in _sentences(segment.get("text") or ""):
            key = sentence.lower()
            if key in seen:
                continue
            for kind, label, pattern in _RULES:
                if pattern.search(sentence):
                    seen.add(key)
                    out.append({"kind": kind, "text": sentence, "quote": sentence,
                                "speaker": speaker, "start_ms": start,
                                "matched_on": label})
                    break            # first rule wins; one sentence, one candidate
    return out


def save_candidates(meeting_id, candidates, partner_id=None):
    rows = []
    with get_db() as db:
        for candidate in candidates:
            cid = _uid()
            db.execute(
                "INSERT INTO desk_meeting_candidates (id, partner_id, meeting_id, "
                "kind, text, quote, speaker, start_ms, matched_on, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?, 'pending', ?)",
                (cid, partner_id, meeting_id, candidate.get("kind") or "action",
                 (candidate.get("text") or "")[:600],
                 (candidate.get("quote") or "")[:600],
                 candidate.get("speaker") or "", int(candidate.get("start_ms") or 0),
                 candidate.get("matched_on") or "", _now()))
            rows.append(cid)
    return rows


def list_candidates(meeting_id, partner_id=None, status=None):
    query = ("SELECT * FROM desk_meeting_candidates "
             "WHERE meeting_id = ? AND partner_id IS ?")
    args = [meeting_id, partner_id]
    if status:
        query += " AND status = ?"
        args.append(status)
    query += " ORDER BY start_ms ASC"
    with get_db() as db:
        return [dict(r) for r in db.execute(query, args).fetchall()]


def get_candidate(candidate_id, partner_id=None):
    with get_db() as db:
        return _row(db.execute(
            "SELECT * FROM desk_meeting_candidates WHERE id = ? AND partner_id IS ?",
            (candidate_id, partner_id)).fetchone())


def decide_candidate(candidate_id, partner_id, status, decided_by,
                     promoted_kind="", promoted_id=None):
    """Approve or dismiss. Recorded with who decided, because 'the system
    added this task' is not an answer anybody accepts later."""
    if status not in CANDIDATE_STATUSES:
        raise ValueError("unknown status: %s" % status)
    with get_db() as db:
        cur = db.execute(
            "UPDATE desk_meeting_candidates SET status = ?, decided_by = ?, "
            "decided_at = ?, promoted_kind = ?, promoted_id = ? "
            "WHERE id = ? AND partner_id IS ?",
            (status, decided_by or "", _now(), promoted_kind or "",
             promoted_id, candidate_id, partner_id))
    return cur.rowcount > 0


def counts(meeting_id, partner_id=None):
    out = {"pending": 0, "approved": 0, "dismissed": 0}
    for row in list_candidates(meeting_id, partner_id):
        out[row["status"]] = out.get(row["status"], 0) + 1
    return out
