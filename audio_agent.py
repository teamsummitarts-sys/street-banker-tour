"""Operator Voice Agent - configuration, guardrails, sessions.

WHAT THIS IS
------------
An agent that can answer a line for a music company: take details, answer
questions it has been given answers to, and put a caller through to a person.

WHAT IT IS NOT ALLOWED TO BE
----------------------------
Not a person. Not an artist. Not anybody with a name.

Those are enforced here, not left to whoever writes the greeting:

  * A profile cannot go live until its greeting DISCLOSES that the caller is
    talking to an AI. `activate()` refuses otherwise, and the check is on the
    text that will actually be spoken, not a checkbox beside it.
  * A profile that names a real person as its persona is refused outright.
    The whole failure mode of a voice product in music is a machine that
    sounds like a specific artist, and the moment to stop that is before it
    exists, not in review.
  * Every profile must name a way to reach a human. An agent with no exit is
    a hold queue that never ends.

WHY THE GUARDRAILS ARE FUNCTIONS AND NOT DOCUMENTATION
------------------------------------------------------
A rule written in a doc is followed by whoever read the doc. This product
will be configured by an operator under time pressure who did not. So the
rules refuse, with a sentence saying what would make them pass.

SESSIONS
--------
A conversation is a record: what was said, whether disclosure was made,
whether a human was asked for, and what happened. Recording a call carries a
consent requirement through audio_policy.gate() like any other recording,
and DEFAULT_POLICY has call recording OFF.
"""
import json
import re
import uuid

from db import get_db, _now

PROFILE_STATUSES = ("draft", "active", "suspended")
SESSION_STATUSES = ("open", "completed", "escalated", "failed")

# Ways a greeting can disclose that the caller is not talking to a person.
# Matched on the text that will actually be spoken.
_DISCLOSURE_PATTERNS = [
    re.compile(r"\b(a|an)\s+(ai|a\.i\.|artificial intelligence|automated|virtual)\b", re.I),
    re.compile(r"\b(ai|automated|virtual)\s+(assistant|agent|receptionist|system)\b", re.I),
    re.compile(r"\bnot\s+a\s+(real\s+)?(person|human)\b", re.I),
    re.compile(r"\b(speaking|talking)\s+(with|to)\s+(an?\s+)?(ai|assistant|bot)\b", re.I),
    re.compile(r"\bthis\s+(call|line)\s+is\s+(handled|answered)\s+by\s+(an?\s+)?(ai|automated)", re.I),
]

# Phrasings that claim to BE a person. A greeting may say "I can put you
# through to a person"; it may not say "I am a person".
_PERSONHOOD_CLAIMS = [
    re.compile(r"\bi\s+am\s+a\s+(real\s+)?(person|human)\b", re.I),
    re.compile(r"\bi'm\s+a\s+(real\s+)?(person|human)\b", re.I),
    re.compile(r"\bnot\s+a\s+(bot|machine|robot|computer|ai)\b", re.I),
    re.compile(r"\byou'?re\s+(speaking|talking)\s+(with|to)\s+a\s+(real\s+)?person\b", re.I),
]


def _uid():
    return uuid.uuid4().hex


def _row(r):
    return dict(r) if r is not None else None


def _dump(v):
    return json.dumps(v) if v is not None else None


def _load(v, default=None):
    if not v:
        return default
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return default


def init_agents():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS agent_profiles (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                name TEXT NOT NULL DEFAULT '',
                purpose TEXT NOT NULL DEFAULT '',
                greeting TEXT NOT NULL DEFAULT '',
                human_contact TEXT NOT NULL DEFAULT '',
                persona_note TEXT NOT NULL DEFAULT '',
                knowledge TEXT NOT NULL DEFAULT '[]',
                may_not TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'draft',
                provider TEXT NOT NULL DEFAULT '',
                provider_agent_id TEXT,
                record_calls INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                activated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_sessions (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                profile_id TEXT NOT NULL,
                provider_conversation_id TEXT,
                job_id TEXT,
                caller_ref TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                disclosed INTEGER NOT NULL DEFAULT 0,
                human_requested INTEGER NOT NULL DEFAULT 0,
                escalated_to TEXT NOT NULL DEFAULT '',
                transcript TEXT NOT NULL DEFAULT '[]',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                is_mock INTEGER NOT NULL DEFAULT 0,
                outcome TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                ended_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_agent_sess_profile
                ON agent_sessions(profile_id, created_at);
        """)


# --- the guardrails ---------------------------------------------------------

class GuardrailRefusal(Exception):
    """A configuration this product will not accept, and why.

    Carries a sentence saying what would make it pass, because an operator
    under time pressure meets this message and nothing else.
    """

    def __init__(self, reason, code="refused"):
        Exception.__init__(self, reason)
        self.reason = reason
        self.code = code


def discloses_ai(greeting):
    """Does this greeting actually tell the caller they are not talking to a
    person? Checked against the spoken text, never a checkbox beside it."""
    text = (greeting or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _DISCLOSURE_PATTERNS)


def claims_personhood(greeting):
    """The opposite failure: a greeting that asserts it IS a person."""
    text = (greeting or "").strip()
    return any(pattern.search(text) for pattern in _PERSONHOOD_CLAIMS)


def check_profile(fields, known_person_names=()):
    """Everything that must be true before an agent may speak to anybody.

    Returns a list of refusals, empty when the profile is acceptable. A list
    rather than the first failure, so an operator fixes the configuration
    once instead of discovering the next problem after each save.
    """
    problems = []
    greeting = (fields.get("greeting") or "").strip()
    persona = (fields.get("persona_note") or "").strip()
    human = (fields.get("human_contact") or "").strip()

    if not (fields.get("name") or "").strip():
        problems.append("Give the agent a name, so a session can be traced to it.")

    if not greeting:
        problems.append(
            "Write the greeting the caller will hear. It has to disclose that "
            "they are speaking to an AI.")
    else:
        if not discloses_ai(greeting):
            problems.append(
                "The greeting does not tell the caller they are speaking to an "
                "AI. Say so in the first sentence - for example, \"You are "
                "speaking with an AI assistant.\" A caller who does not know "
                "cannot consent to it.")
        if claims_personhood(greeting):
            problems.append(
                "The greeting claims to be a person. An agent may offer to put "
                "somebody through to a person; it may not say it is one.")

    if not human:
        problems.append(
            "Name how a caller reaches a human - a person, a team or a number. "
            "An agent with no exit is a hold queue that never ends.")

    # The failure mode this product exists inside: a machine that sounds like
    # a specific artist. Refused before it exists, not caught in review.
    named = _names_a_real_person(persona, known_person_names)
    if named:
        problems.append(
            "This agent is configured to present as %s. An agent may not take "
            "the identity of a real person, whether or not they are on this "
            "roster. Describe the ROLE it performs instead." % named)

    return problems


def _names_a_real_person(persona_note, known_person_names=()):
    """A persona that names somebody. Checks the roster it was given first,
    then the shape of a claim to be a named individual.

    TWO LAYERS, AND THE SECOND ONE HAS A KNOWN HOLE
    -----------------------------------------------
    The roster check is exact and case-insensitive: anybody the system knows
    about is caught however they are typed. That is the layer that matters,
    because the people this product could plausibly imitate are on it.

    The shape check is a heuristic for names the system has never heard of,
    and it requires Capitalised Words. That is deliberate and it is also its
    limit: "you are jordan vale" in lower case is not caught. Making the name
    part case-insensitive would refuse "you are the front desk", which is a
    legitimate role description, and a guardrail that blocks ordinary
    configuration gets switched off by whoever it blocks.

    So this is defence in depth, not a proof. The operator is told in the form
    that an agent may not take a real person's identity, and the roster check
    is what actually enforces it for real people.
    """
    text = (persona_note or "").strip()
    if not text:
        return None

    for name in known_person_names or ():
        clean = (name or "").strip()
        if len(clean) >= 3 and re.search(r"\b%s\b" % re.escape(clean), text, re.I):
            return clean

    # "speaks as Jordan Vale", "You are Maria Solis", "sounds like Ben Ortiz".
    # Two capitalised words in a row after an identity verb is the shape of a
    # person's name, and this errs toward refusing.
    #
    # The VERB is matched case-insensitively and the NAME is not. That split
    # is the whole point and is why the flag is scoped with (?i:...) rather
    # than passed for the pattern: a persona note beginning "You are Jordan
    # Vale" starts the sentence with a capital Y, and a case-sensitive verb
    # let exactly that phrasing through - the most natural way an operator
    # would write the thing this refuses.
    match = re.search(
        r"\b(?i:speak(?:s|ing)?\s+as|sound(?:s|ing)?\s+like|voice\s+of|"
        r"you\s+are|impersonat\w*|as\s+if\s+you\s+(?:are|were))\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text)
    if match:
        return match.group(1)
    return None


# --- profiles ---------------------------------------------------------------

def create_profile(fields, created_by="", partner_id=None,
                   known_person_names=()):
    """Always created as a draft. A profile that could speak the moment it was
    saved would be one an operator had not read back."""
    problems = check_profile(fields, known_person_names)
    if problems:
        raise GuardrailRefusal(" ".join(problems), "guardrail")

    pid = _uid()
    with get_db() as db:
        db.execute(
            "INSERT INTO agent_profiles (id, partner_id, name, purpose, greeting, "
            "human_contact, persona_note, knowledge, may_not, status, "
            "record_calls, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?, 'draft', ?, ?, ?)",
            (pid, partner_id, (fields.get("name") or "")[:120],
             (fields.get("purpose") or "")[:600],
             (fields.get("greeting") or "")[:1200],
             (fields.get("human_contact") or "")[:200],
             (fields.get("persona_note") or "")[:400],
             _dump(list(fields.get("knowledge") or [])),
             _dump(list(fields.get("may_not") or [])),
             1 if fields.get("record_calls") else 0,
             created_by, _now()))
    return get_profile(pid, partner_id)


def get_profile(profile_id, partner_id=None):
    with get_db() as db:
        row = _row(db.execute(
            "SELECT * FROM agent_profiles WHERE id = ? AND partner_id IS ?",
            (profile_id, partner_id)).fetchone())
    if row:
        row["knowledge"] = _load(row.get("knowledge"), [])
        row["may_not"] = _load(row.get("may_not"), [])
    return row


def list_profiles(partner_id=None, limit=100):
    with get_db() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM agent_profiles WHERE partner_id IS ? "
            "ORDER BY created_at DESC LIMIT ?", (partner_id, limit)).fetchall()]
    for row in rows:
        row["knowledge"] = _load(row.get("knowledge"), [])
        row["may_not"] = _load(row.get("may_not"), [])
    return rows


def update_profile(profile_id, fields, partner_id=None, known_person_names=()):
    """Editing re-runs every guardrail, and a live agent drops back to draft.

    Otherwise the disclosure check is a one-time gate somebody walks through
    and then edits the greeting behind.
    """
    current = get_profile(profile_id, partner_id)
    if current is None:
        return None

    merged = dict(current)
    merged.update(fields or {})
    problems = check_profile(merged, known_person_names)
    if problems:
        raise GuardrailRefusal(" ".join(problems), "guardrail")

    with get_db() as db:
        db.execute(
            "UPDATE agent_profiles SET name = ?, purpose = ?, greeting = ?, "
            "human_contact = ?, persona_note = ?, knowledge = ?, may_not = ?, "
            "record_calls = ?, status = 'draft', activated_at = NULL "
            "WHERE id = ? AND partner_id IS ?",
            ((merged.get("name") or "")[:120], (merged.get("purpose") or "")[:600],
             (merged.get("greeting") or "")[:1200],
             (merged.get("human_contact") or "")[:200],
             (merged.get("persona_note") or "")[:400],
             _dump(list(merged.get("knowledge") or [])),
             _dump(list(merged.get("may_not") or [])),
             1 if merged.get("record_calls") else 0,
             profile_id, partner_id))
    return get_profile(profile_id, partner_id)


def activate(profile_id, partner_id=None, known_person_names=()):
    """The last gate before an agent can speak to anybody.

    Re-checks rather than trusting that creation checked: the row may have
    been edited by another path, and this is the only place that matters.
    """
    profile = get_profile(profile_id, partner_id)
    if profile is None:
        raise GuardrailRefusal("That agent does not exist.", "missing")

    problems = check_profile(profile, known_person_names)
    if problems:
        raise GuardrailRefusal(" ".join(problems), "guardrail")

    with get_db() as db:
        db.execute("UPDATE agent_profiles SET status = 'active', activated_at = ? "
                   "WHERE id = ? AND partner_id IS ?",
                   (_now(), profile_id, partner_id))
    return get_profile(profile_id, partner_id)


def suspend(profile_id, partner_id=None):
    """One column write, and the agent stops answering. Any guardrail that
    cannot be applied instantly is not a guardrail."""
    with get_db() as db:
        db.execute("UPDATE agent_profiles SET status = 'suspended' "
                   "WHERE id = ? AND partner_id IS ?", (profile_id, partner_id))
    return get_profile(profile_id, partner_id)


def delete_profile(profile_id, partner_id=None):
    with get_db() as db:
        db.execute("DELETE FROM agent_sessions WHERE profile_id = ?", (profile_id,))
        db.execute("DELETE FROM agent_profiles WHERE id = ? AND partner_id IS ?",
                   (profile_id, partner_id))


# --- sessions ---------------------------------------------------------------

def create_session(profile_id, partner_id=None, caller_ref="",
                   provider_conversation_id=None, job_id=None):
    sid = _uid()
    with get_db() as db:
        db.execute(
            "INSERT INTO agent_sessions (id, partner_id, profile_id, "
            "provider_conversation_id, job_id, caller_ref, status, created_at) "
            "VALUES (?,?,?,?,?,?, 'open', ?)",
            (sid, partner_id, profile_id, provider_conversation_id, job_id,
             (caller_ref or "")[:120], _now()))
    return get_session(sid, partner_id)


def get_session(session_id, partner_id=None):
    with get_db() as db:
        row = _row(db.execute(
            "SELECT * FROM agent_sessions WHERE id = ? AND partner_id IS ?",
            (session_id, partner_id)).fetchone())
    if row:
        row["transcript"] = _load(row.get("transcript"), [])
    return row


def list_sessions(partner_id=None, profile_id=None, limit=100):
    query = "SELECT * FROM agent_sessions WHERE partner_id IS ?"
    args = [partner_id]
    if profile_id:
        query += " AND profile_id = ?"
        args.append(profile_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with get_db() as db:
        rows = [dict(r) for r in db.execute(query, args).fetchall()]
    for row in rows:
        row["transcript"] = _load(row.get("transcript"), [])
    return rows


def record_outcome(session_id, partner_id=None, transcript=None, status=None,
                   duration_seconds=None, is_mock=None, outcome=None,
                   escalated_to=None):
    """Close a session with what actually happened.

    `disclosed` and `human_requested` are DERIVED from the transcript rather
    than reported by the caller of this function. Whether the agent actually
    disclosed is a question about what was said, and the only honest source
    for it is the words.
    """
    sets, args = [], []

    if transcript is not None:
        sets.append("transcript = ?")
        args.append(_dump(list(transcript)))
        sets.append("disclosed = ?")
        args.append(1 if transcript_discloses(transcript) else 0)
        sets.append("human_requested = ?")
        args.append(1 if transcript_requests_human(transcript) else 0)

    for column, value in (("status", status), ("outcome", outcome),
                          ("escalated_to", escalated_to)):
        if value is not None:
            sets.append("%s = ?" % column)
            args.append(value)
    if duration_seconds is not None:
        sets.append("duration_seconds = ?")
        args.append(int(duration_seconds))
    if is_mock is not None:
        sets.append("is_mock = ?")
        args.append(1 if is_mock else 0)
    if status in ("completed", "escalated", "failed"):
        sets.append("ended_at = ?")
        args.append(_now())

    if not sets:
        return False
    args.extend([session_id, partner_id])
    with get_db() as db:
        cur = db.execute("UPDATE agent_sessions SET %s WHERE id = ? AND partner_id IS ?"
                         % ", ".join(sets), args)
    return cur.rowcount > 0


def transcript_discloses(transcript):
    """Did the agent actually say it was an AI, in what it actually said?

    Only the agent's own turns count. A caller saying "are you a robot" is
    not a disclosure, and reading the whole transcript would score it as one.
    """
    for turn in transcript or []:
        if (turn.get("role") or "") != "agent":
            continue
        if discloses_ai(turn.get("text") or ""):
            return True
    return False


_HUMAN_ASKS = re.compile(
    r"\b(speak|talk)\s+(to|with)\s+(a\s+)?(human|person|someone|somebody|real person)\b"
    r"|\b(put|get)\s+me\s+(through|on)\b"
    r"|\b(real|actual)\s+person\b"
    r"|\b(operator|manager|supervisor)\b", re.I)


def transcript_requests_human(transcript):
    """Did the caller ask for a person? Their turns only.

    This drives escalation review. An agent that was asked for a human and did
    not produce one is the failure this product must be able to find.
    """
    for turn in transcript or []:
        if (turn.get("role") or "") not in ("caller", "user"):
            continue
        if _HUMAN_ASKS.search(turn.get("text") or ""):
            return True
    return False


def unmet_human_requests(partner_id=None, limit=100):
    """Sessions where somebody asked for a person and did not get one.

    The single most important report in this module. An agent that quietly
    refuses to escalate is worse than no agent, and nobody would notice from
    the session list.
    """
    return [s for s in list_sessions(partner_id, limit=limit)
            if s.get("human_requested") and s.get("status") != "escalated"]
