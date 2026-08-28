"""Street Banker Audio Intelligence - storage and policy.

TENANCY
-------
Every table here carries `partner_id`, the tenant Partner OS established.
NULL means Street Banker itself, which is what a direct account is. The
rule from partner_store applies unchanged: if a row would tell one tenant
what another is doing, it is scoped, and every query in this module
filters on it.

WHAT THIS MODULE REFUSES TO DO
------------------------------
It will not let a job start that the organisation's own policy forbids,
and it will not quietly relax the policy to make a job possible. The
sharpest case is zero retention: if an organisation requires it and the
selected provider cannot prove it supports it for this account, the job is
rejected before a single byte is uploaded. Downgrading silently would mean
telling somebody their audio was never stored when it was.

CONSENT AND RIGHTS ARE ROWS, NOT FLAGS
--------------------------------------
A checkbox in a form is not a consent record. Consent and rights
confirmations are stored with who gave them, when, against which policy
version, and what text they were shown - because the question that gets
asked later is "what exactly did they agree to", and a boolean cannot
answer it.
"""
import json
import sqlite3
import uuid

from db import get_db, _now

# --- capability keys (entitlements) -----------------------------------------
# These extend Partner OS permissions rather than starting a second system.
CAPS = [
    "audio.meeting_intelligence", "audio.meeting_recording", "audio.meeting_upload",
    "audio.transcription", "audio.realtime_transcription",
    "audio.signal_briefs", "audio.signal_brief_scheduling",
    "audio.operator_agent", "audio.operator_phone", "audio.operator_web",
    "audio.operator_human_transfer",
    "audio.global_release_pack", "audio.dubbing",
    "audio.campaign_voiceover", "audio.sound_effects", "audio.voice_isolation",
    "audio.remix_lab", "audio.stem_separation",
    "audio.music_generation", "audio.music_inpainting",
    "audio.voice_vault", "audio.voice_vault_verified_cloning",
    "audio.white_label_operator", "audio.api", "audio.webhooks",
    "audio.zero_retention", "audio.custom_provider",
]

JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled", "rejected")


def _uid():
    return uuid.uuid4().hex


def _pk(partner_id):
    """Street Banker itself is '' here, never NULL.

    SQLite treats NULLs as distinct in PRIMARY KEY and UNIQUE constraints,
    so a NULL tenant key silently defeats both. This module found that the
    hard way: every policy write for the default tenant inserted a fresh
    row, ON CONFLICT never fired, and the read picked the oldest one - a
    policy change that appeared to save and did nothing. Anything used as a
    KEY passes through here. Scoping predicates elsewhere still use
    `partner_id IS ?`, which handles NULL correctly.
    """
    return partner_id or ""


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


# --- schema ------------------------------------------------------------------

def init_audio():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS audio_assets (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                owner_user_id TEXT NOT NULL,
                project_type TEXT NOT NULL DEFAULT '',
                project_id TEXT,
                asset_type TEXT NOT NULL DEFAULT 'source',
                storage_key TEXT NOT NULL,
                file_name TEXT NOT NULL DEFAULT '',
                mime_type TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER,
                checksum TEXT NOT NULL DEFAULT '',
                rights_status TEXT NOT NULL DEFAULT 'unconfirmed',
                consent_status TEXT NOT NULL DEFAULT 'not_required',
                retention_expires_at TEXT,
                deleted_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audio_jobs (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                user_id TEXT NOT NULL,
                feature_key TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                capability TEXT NOT NULL DEFAULT '',
                operation TEXT NOT NULL DEFAULT '',
                provider_job_id TEXT,
                idempotency_key TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                input_asset_ids TEXT NOT NULL DEFAULT '[]',
                output_asset_ids TEXT NOT NULL DEFAULT '[]',
                configuration TEXT,
                estimated_cost REAL,
                final_cost REAL,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                partner_key TEXT NOT NULL DEFAULT ''
                /* The idempotency guard is a PARTIAL unique index created in
                   _migrate, not a UNIQUE() here. See the note there: a
                   whole-column constraint makes every keyless job after the
                   first collide on the default ''. */
            );
            CREATE TABLE IF NOT EXISTS audio_transcripts (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                audio_asset_id TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                full_text TEXT NOT NULL DEFAULT '',
                confidence REAL,
                is_mock INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audio_transcript_segments (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                transcript_id TEXT NOT NULL,
                speaker_key TEXT NOT NULL DEFAULT '',
                start_ms INTEGER NOT NULL DEFAULT 0,
                end_ms INTEGER NOT NULL DEFAULT 0,
                text TEXT NOT NULL DEFAULT '',
                confidence REAL,
                entities TEXT
            );
            CREATE TABLE IF NOT EXISTS audio_transcript_speakers (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                transcript_id TEXT NOT NULL,
                provider_speaker_key TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                person_id TEXT,
                manually_confirmed INTEGER NOT NULL DEFAULT 0
            );
            /* Consent and rights are records, not booleans: who, when,
               which policy version, and the exact words they were shown. */
            CREATE TABLE IF NOT EXISTS audio_consent (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL DEFAULT '',
                consent_type TEXT NOT NULL,
                policy_version TEXT NOT NULL DEFAULT '',
                disclosure_text TEXT NOT NULL DEFAULT '',
                accepted INTEGER NOT NULL DEFAULT 0,
                accepted_by_user_id TEXT,
                accepted_at TEXT,
                revoked_at TEXT,
                evidence TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audio_policies (
                partner_id TEXT PRIMARY KEY NOT NULL DEFAULT '',
                policy TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audio_usage (
                id TEXT PRIMARY KEY,
                partner_id TEXT,
                user_id TEXT,
                job_id TEXT,
                provider TEXT NOT NULL DEFAULT '',
                operation TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                input_units REAL NOT NULL DEFAULT 0,
                output_units REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT '',
                estimated_cost REAL,
                final_cost REAL,
                currency TEXT NOT NULL DEFAULT 'USD',
                provider_request_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audio_webhook_events (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                external_event_id TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL DEFAULT '',
                signature_valid INTEGER NOT NULL DEFAULT 0,
                partner_id TEXT,
                payload TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'received',
                attempts INTEGER NOT NULL DEFAULT 0,
                received_at TEXT NOT NULL,
                processed_at TEXT,
                failure_reason TEXT
                /* Dedup is a PARTIAL unique index built in _migrate, for the
                   same reason as audio_jobs: external_event_id defaults to ''
                   and not every vendor sends a delivery id. Under a
                   whole-column UNIQUE, every id-less event after the first
                   was reported as a duplicate and silently never processed. */
            );
            CREATE INDEX IF NOT EXISTS idx_aud_assets_partner
                ON audio_assets(partner_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_aud_assets_owner
                ON audio_assets(owner_user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_aud_assets_retention
                ON audio_assets(retention_expires_at);
            CREATE INDEX IF NOT EXISTS idx_aud_jobs_partner
                ON audio_jobs(partner_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_aud_jobs_status
                ON audio_jobs(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_aud_seg_transcript
                ON audio_transcript_segments(transcript_id, start_ms);
            CREATE INDEX IF NOT EXISTS idx_aud_usage_partner
                ON audio_usage(partner_id, created_at);
        """)
        return _migrate(db)


def _partial_unique(db, index_name, table, cols, nonempty_col, applied, step):
    """A unique index that ignores the empty string.

    Both tables that need one have a key column with DEFAULT '': the
    idempotency key on a job, the vendor's delivery id on a webhook. A plain
    UNIQUE over the whole column makes every row that omits the key collide
    with the first one that did - which for jobs meant an IntegrityError on
    the second brief, and for webhooks meant genuinely different events being
    reported as duplicates and silently never processed.
    """
    existed = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)).fetchone() is not None
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s(%s) WHERE %s != ''"
               % (index_name, table, ", ".join(cols), nonempty_col))
    if not existed:
        applied.append(step)


def _rebuild_without_unique(db, table, cols, create_sql, indexes, applied, step):
    """Drop a table-level UNIQUE that ALTER TABLE cannot touch.

    SQLite implements UNIQUE(...) as an auto-index and offers no way to drop
    it, so the table has to be rebuilt around it.

    The trigger matches on the COLUMNS the auto-index covers, never on the
    name merely looking auto-generated: `id TEXT PRIMARY KEY` produces one of
    those on every table, so a name-only test stays true forever and copies
    the whole table on every boot - including on brand new databases.
    """
    def covers(index_name):
        return tuple(r[2] for r in
                     db.execute("PRAGMA index_info(%s)" % index_name).fetchall())

    offending = [r for r in db.execute("PRAGMA index_list(%s)" % table).fetchall()
                 if str(r[1]).startswith("sqlite_autoindex") and r[2]
                 and covers(r[1]) == tuple(cols)]
    if not offending:
        return

    names = ", ".join(r[1] for r in
                      db.execute("PRAGMA table_info(%s)" % table).fetchall())
    tmp = "%s_rebuilt" % table
    db.execute("PRAGMA foreign_keys=off")
    db.execute("DROP TABLE IF EXISTS %s" % tmp)
    db.execute(create_sql % {"tmp": tmp})
    db.execute("INSERT INTO %s (%s) SELECT %s FROM %s" % (tmp, names, names, table))
    db.execute("DROP TABLE %s" % table)
    db.execute("ALTER TABLE %s RENAME TO %s" % (tmp, table))
    for stmt in indexes:
        db.execute(stmt)
    db.execute("PRAGMA foreign_keys=on")
    applied.append(step)


_JOBS_DDL = """
    CREATE TABLE %(tmp)s (
        id TEXT PRIMARY KEY,
        partner_id TEXT,
        user_id TEXT NOT NULL,
        feature_key TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT '',
        capability TEXT NOT NULL DEFAULT '',
        operation TEXT NOT NULL DEFAULT '',
        provider_job_id TEXT,
        idempotency_key TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0,
        input_asset_ids TEXT NOT NULL DEFAULT '[]',
        output_asset_ids TEXT NOT NULL DEFAULT '[]',
        configuration TEXT,
        estimated_cost REAL,
        final_cost REAL,
        error_code TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        partner_key TEXT NOT NULL DEFAULT ''
    )"""

_HOOKS_DDL = """
    CREATE TABLE %(tmp)s (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        external_event_id TEXT NOT NULL DEFAULT '',
        event_type TEXT NOT NULL DEFAULT '',
        signature_valid INTEGER NOT NULL DEFAULT 0,
        partner_id TEXT,
        payload TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'received',
        attempts INTEGER NOT NULL DEFAULT 0,
        received_at TEXT NOT NULL,
        processed_at TEXT,
        failure_reason TEXT
    )"""


def _migrate(db):
    """Bring an already-created audio schema up to date.

    CREATE TABLE IF NOT EXISTS is not a migration: it does nothing at all to a
    table that exists, so a column added to the statement above never reaches
    a database that was initialised before it. Every structural change after
    the first release belongs here.

    Returns the list of steps it actually applied, which is empty on a database
    that is already current. That return value is the only honest way to tell
    whether a migration ran: SQLite reuses freed page numbers after a drop and
    rename, so a table's rootpage can be identical either side of a full
    rebuild, and a test that watches rootpage will happily pass while the
    schema is being copied on every single boot.
    """
    applied = []

    cols = {r[1] for r in db.execute("PRAGMA table_info(audio_jobs)").fetchall()}
    if "partner_key" not in cols:
        db.execute("ALTER TABLE audio_jobs ADD COLUMN partner_key TEXT NOT NULL DEFAULT ''")
        db.execute("UPDATE audio_jobs SET partner_key = COALESCE(partner_id, '')")
        applied.append("add_partner_key")

    _rebuild_without_unique(
        db, "audio_jobs", ("partner_key", "idempotency_key"), _JOBS_DDL,
        ["CREATE INDEX IF NOT EXISTS idx_aud_jobs_partner ON audio_jobs(partner_id, created_at)",
         "CREATE INDEX IF NOT EXISTS idx_aud_jobs_status ON audio_jobs(status, created_at)"],
        applied, "rebuild_audio_jobs_without_whole_column_unique")

    _rebuild_without_unique(
        db, "audio_webhook_events", ("provider", "external_event_id"), _HOOKS_DDL,
        [], applied, "rebuild_audio_webhook_events_without_whole_column_unique")

    _partial_unique(db, "idx_aud_jobs_idem", "audio_jobs",
                    ("partner_key", "idempotency_key"), "idempotency_key",
                    applied, "partial_idempotency_index")

    _partial_unique(db, "idx_aud_hooks_ext", "audio_webhook_events",
                    ("provider", "external_event_id"), "external_event_id",
                    applied, "partial_webhook_dedup_index")

    return applied


# --- the data policy ---------------------------------------------------------
# Defaults are the cautious reading: recording and cloning off, consent and
# rights required, retention finite. An organisation opts IN to the rest.
DEFAULT_POLICY = {
    "allow_audio_upload": True,
    "allow_meeting_recording": False,
    "allow_call_recording": False,
    "allow_transcription": True,
    "allow_voice_generation": True,
    "allow_dubbing": False,
    "allow_music_generation": False,
    "allow_voice_cloning": False,

    "require_zero_retention": False,
    "allow_provider_storage": True,
    "allow_internal_storage": True,

    "source_audio_retention_days": 90,
    "transcript_retention_days": 365,
    "generated_audio_retention_days": 365,
    "agent_conversation_retention_days": 365,
    "voice_sample_retention_days": 30,

    "allow_human_review": True,
    "allow_ai_extraction": True,
    "allow_download": True,
    "allow_export": True,

    "require_recording_consent": True,
    "require_agent_disclosure": True,
    "require_rights_confirmation": True,
}


def get_policy(partner_id):
    with get_db() as db:
        row = db.execute("SELECT policy FROM audio_policies WHERE partner_id = ?",
                         (_pk(partner_id),)).fetchone()
    p = dict(DEFAULT_POLICY)
    if row:
        p.update(_load(row["policy"], {}) or {})
    return p


def set_policy(partner_id, changes, actor_user_id=None):
    p = get_policy(partner_id)
    for k, v in (changes or {}).items():
        if k in DEFAULT_POLICY:
            p[k] = v
    with get_db() as db:
        db.execute(
            "INSERT INTO audio_policies (partner_id, policy, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(partner_id) DO UPDATE SET policy=excluded.policy, "
            "updated_at=excluded.updated_at",
            (_pk(partner_id), _dump(p), _now()))
    return p


# --- consent -----------------------------------------------------------------

def record_consent(partner_id, subject_type, consent_type, policy_version,
                   disclosure_text, accepted, subject_id="", user_id=None,
                   evidence=None):
    cid = _uid()
    with get_db() as db:
        db.execute(
            "INSERT INTO audio_consent (id, partner_id, subject_type, subject_id, "
            "consent_type, policy_version, disclosure_text, accepted, "
            "accepted_by_user_id, accepted_at, evidence, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, partner_id, subject_type, subject_id or "", consent_type,
             policy_version or "", disclosure_text or "", 1 if accepted else 0,
             user_id, _now() if accepted else None, _dump(evidence), _now()))
    return cid


def latest_consent(partner_id, consent_type, subject_id=""):
    with get_db() as db:
        return _row(db.execute(
            "SELECT * FROM audio_consent WHERE partner_id IS ? AND consent_type = ? "
            "AND subject_id = ? AND revoked_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (partner_id, consent_type, subject_id or "")).fetchone())


def has_consent(partner_id, consent_type, subject_id=""):
    c = latest_consent(partner_id, consent_type, subject_id)
    return bool(c and c["accepted"])


# --- jobs --------------------------------------------------------------------

def create_job(partner_id, user_id, feature_key, capability, operation,
               provider="", input_asset_ids=None, configuration=None,
               estimated_cost=None, idempotency_key=None):
    """Idempotent per (partner, key). A repeated submit returns the job that
    already exists rather than charging twice."""
    if idempotency_key:
        with get_db() as db:
            row = db.execute(
                "SELECT * FROM audio_jobs WHERE partner_key = ? AND idempotency_key = ?",
                (_pk(partner_id), idempotency_key)).fetchone()
            if row:
                return dict(row)
    jid = _uid()
    with get_db() as db:
        try:
            db.execute(
                "INSERT INTO audio_jobs (id, partner_id, partner_key, user_id, feature_key, "
                "provider, capability, operation, idempotency_key, status, input_asset_ids, "
                "configuration, estimated_cost, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'queued',?,?,?,?)",
                (jid, partner_id, _pk(partner_id), user_id, feature_key, provider,
                 capability, operation, idempotency_key or "",
                 _dump(list(input_asset_ids or [])),
                 _dump(configuration), estimated_cost, _now()))
        except sqlite3.IntegrityError:
            row = db.execute(
                "SELECT * FROM audio_jobs WHERE partner_key = ? AND idempotency_key = ?",
                (_pk(partner_id), idempotency_key)).fetchone()
            if row:
                return dict(row)
            raise
    return get_job(partner_id, jid)


def get_job(partner_id, job_id):
    with get_db() as db:
        return _row(db.execute(
            "SELECT * FROM audio_jobs WHERE id = ? AND partner_id IS ?",
            (job_id, partner_id)).fetchone())


def list_jobs(partner_id, limit=100, status=None):
    q = "SELECT * FROM audio_jobs WHERE partner_id IS ?"
    args = [partner_id]
    if status:
        q += " AND status = ?"
        args.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with get_db() as db:
        return [dict(r) for r in db.execute(q, args).fetchall()]


def set_job_status(partner_id, job_id, status, provider_job_id=None,
                   error_code=None, error_message=None, output_asset_ids=None,
                   final_cost=None):
    if status not in JOB_STATUSES:
        raise ValueError("unknown job status: %s" % status)
    sets = ["status = ?"]
    args = [status]
    if status == "running":
        sets.append("started_at = COALESCE(started_at, ?)"); args.append(_now())
        sets.append("attempts = attempts + 1")
    if status in ("completed", "failed", "cancelled", "rejected"):
        sets.append("completed_at = ?"); args.append(_now())
    if provider_job_id is not None:
        sets.append("provider_job_id = ?"); args.append(provider_job_id)
    if error_code is not None:
        sets.append("error_code = ?"); args.append(error_code)
    if error_message is not None:
        sets.append("error_message = ?"); args.append((error_message or "")[:800])
    if output_asset_ids is not None:
        sets.append("output_asset_ids = ?"); args.append(_dump(list(output_asset_ids)))
    if final_cost is not None:
        sets.append("final_cost = ?"); args.append(final_cost)
    args.extend([job_id, partner_id])
    with get_db() as db:
        cur = db.execute("UPDATE audio_jobs SET %s WHERE id = ? AND partner_id IS ?"
                         % ", ".join(sets), args)
    return cur.rowcount > 0


# --- usage -------------------------------------------------------------------

def record_usage(partner_id, provider, operation, input_units=0, output_units=0,
                 unit="", user_id=None, job_id=None, model="",
                 estimated_cost=None, final_cost=None, provider_request_id=None):
    """What was actually consumed. Cost is nullable on purpose: this repo
    does not hardcode vendor prices into product logic, and a number the
    provider has not confirmed is a guess, not a charge."""
    with get_db() as db:
        db.execute(
            "INSERT INTO audio_usage (id, partner_id, user_id, job_id, provider, "
            "operation, model, input_units, output_units, unit, estimated_cost, "
            "final_cost, provider_request_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_uid(), partner_id, user_id, job_id, provider, operation, model or "",
             input_units or 0, output_units or 0, unit or "", estimated_cost,
             final_cost, provider_request_id, _now()))


def usage_summary(partner_id, since=None):
    q = ("SELECT provider, operation, COUNT(*) AS jobs, "
         "SUM(input_units) AS input_units, SUM(output_units) AS output_units, "
         "SUM(COALESCE(final_cost, estimated_cost, 0)) AS cost "
         "FROM audio_usage WHERE partner_id IS ?")
    args = [partner_id]
    if since:
        q += " AND created_at >= ?"
        args.append(since)
    q += " GROUP BY provider, operation ORDER BY jobs DESC"
    with get_db() as db:
        return [dict(r) for r in db.execute(q, args).fetchall()]


# --- webhook events ----------------------------------------------------------

def store_webhook_event(provider, external_event_id, event_type, signature_valid,
                        payload, partner_id=None):
    """Store raw, before processing, and exactly once.

    Returns (event_id, is_duplicate). A duplicate is not an error: vendors
    retry, and the right answer to a repeat is the same answer as the first
    time, with nothing happening twice.
    """
    eid = _uid()
    with get_db() as db:
        external_event_id = external_event_id or ""
        if external_event_id:
            row = db.execute(
                "SELECT id FROM audio_webhook_events WHERE provider = ? AND external_event_id = ?",
                (provider, external_event_id)).fetchone()
            if row:
                return row["id"], True
        try:
            db.execute(
                "INSERT INTO audio_webhook_events (id, provider, external_event_id, "
                "event_type, signature_valid, partner_id, payload, status, received_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (eid, provider, external_event_id, event_type or "",
                 1 if signature_valid else 0, partner_id,
                 payload if isinstance(payload, str) else _dump(payload),
                 "received" if signature_valid else "rejected", _now()))
        except sqlite3.IntegrityError:
            row = db.execute(
                "SELECT id FROM audio_webhook_events WHERE provider = ? AND external_event_id = ?",
                (provider, external_event_id)).fetchone()
            return (row["id"] if row else eid), True
    return eid, False


def mark_webhook(event_id, status, failure_reason=None):
    with get_db() as db:
        db.execute(
            "UPDATE audio_webhook_events SET status = ?, processed_at = ?, "
            "failure_reason = ?, attempts = attempts + 1 WHERE id = ?",
            (status, _now(), (failure_reason or "")[:500] or None, event_id))


def list_webhook_events(limit=100):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT id, provider, external_event_id, event_type, signature_valid, "
            "partner_id, status, attempts, received_at, processed_at, failure_reason "
            "FROM audio_webhook_events ORDER BY received_at DESC LIMIT ?",
            (limit,)).fetchall()]


# --- assets ------------------------------------------------------------------

def create_asset(partner_id, owner_user_id, storage_key, file_name="", mime_type="",
                 file_size=0, duration_ms=None, checksum="", asset_type="source",
                 project_type="", project_id=None, rights_status="unconfirmed",
                 consent_status="not_required", retention_days=None):
    aid = _uid()
    expires = None
    if retention_days:
        from datetime import datetime, timedelta, timezone
        expires = (datetime.now(timezone.utc)
                   + timedelta(days=int(retention_days))).isoformat(timespec="seconds")
    with get_db() as db:
        db.execute(
            "INSERT INTO audio_assets (id, partner_id, owner_user_id, project_type, "
            "project_id, asset_type, storage_key, file_name, mime_type, file_size, "
            "duration_ms, checksum, rights_status, consent_status, "
            "retention_expires_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, partner_id, owner_user_id, project_type, project_id, asset_type,
             storage_key, file_name[:200], mime_type[:80], file_size, duration_ms,
             checksum, rights_status, consent_status, expires, _now()))
    return aid


def get_asset(partner_id, asset_id):
    with get_db() as db:
        return _row(db.execute(
            "SELECT * FROM audio_assets WHERE id = ? AND partner_id IS ? "
            "AND deleted_at IS NULL", (asset_id, partner_id)).fetchone())


def list_assets(partner_id, owner_user_id=None, limit=100):
    q = "SELECT * FROM audio_assets WHERE partner_id IS ? AND deleted_at IS NULL"
    args = [partner_id]
    if owner_user_id:
        q += " AND owner_user_id = ?"
        args.append(owner_user_id)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with get_db() as db:
        return [dict(r) for r in db.execute(q, args).fetchall()]


def expired_assets(now=None):
    """Due for retention cleanup. The row survives deletion of the bytes -
    an audit trail that vanishes with the audio is not an audit trail."""
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM audio_assets WHERE deleted_at IS NULL "
            "AND retention_expires_at IS NOT NULL AND retention_expires_at <= ?",
            (now or _now(),)).fetchall()]


def mark_asset_deleted(asset_id):
    with get_db() as db:
        db.execute("UPDATE audio_assets SET deleted_at = ?, storage_key = '' "
                   "WHERE id = ?", (_now(), asset_id))


# --- transcripts -------------------------------------------------------------

def save_transcript(partner_id, audio_asset_id, provider, result):
    tid = _uid()
    segs = result.get("segments") or []
    with get_db() as db:
        db.execute(
            "INSERT INTO audio_transcripts (id, partner_id, audio_asset_id, provider, "
            "language, full_text, confidence, is_mock, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,'draft',?)",
            (tid, partner_id, audio_asset_id, provider, result.get("language") or "",
             result.get("full_text") or "", result.get("confidence"),
             1 if result.get("is_mock") else 0, _now()))
        for s in segs:
            db.execute(
                "INSERT INTO audio_transcript_segments (id, partner_id, transcript_id, "
                "speaker_key, start_ms, end_ms, text, confidence, entities) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (_uid(), partner_id, tid, s.get("speaker") or "", s.get("start_ms") or 0,
                 s.get("end_ms") or 0, s.get("text") or "", s.get("confidence"),
                 _dump(s.get("entities"))))
        for name in sorted({s.get("speaker") or "" for s in segs} - {""}):
            db.execute(
                "INSERT INTO audio_transcript_speakers (id, partner_id, transcript_id, "
                "provider_speaker_key, display_name, manually_confirmed) "
                "VALUES (?,?,?,?,?,0)", (_uid(), partner_id, tid, name, name))
    return tid


def get_transcript(partner_id, transcript_id):
    with get_db() as db:
        t = _row(db.execute(
            "SELECT * FROM audio_transcripts WHERE id = ? AND partner_id IS ?",
            (transcript_id, partner_id)).fetchone())
        if t is None:
            return None
        t["segments"] = [dict(r) for r in db.execute(
            "SELECT * FROM audio_transcript_segments WHERE transcript_id = ? "
            "AND partner_id IS ? ORDER BY start_ms", (transcript_id, partner_id)).fetchall()]
        t["speakers"] = [dict(r) for r in db.execute(
            "SELECT * FROM audio_transcript_speakers WHERE transcript_id = ? "
            "AND partner_id IS ?", (transcript_id, partner_id)).fetchall()]
    return t


def rename_speaker(partner_id, transcript_id, provider_speaker_key, display_name,
                   person_id=None):
    with get_db() as db:
        cur = db.execute(
            "UPDATE audio_transcript_speakers SET display_name = ?, person_id = ?, "
            "manually_confirmed = 1 WHERE transcript_id = ? AND partner_id IS ? "
            "AND provider_speaker_key = ?",
            ((display_name or "")[:120], person_id, transcript_id, partner_id,
             provider_speaker_key))
    return cur.rowcount > 0
