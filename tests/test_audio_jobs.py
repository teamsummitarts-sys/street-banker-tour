"""Audio Intelligence: the gate, the runner, and the schema underneath them.

Every test here is a regression test for something that was actually wrong
during the build, not a restatement of the design. In order of how much they
would have cost:

  * audio_jobs carried UNIQUE(partner_key, idempotency_key) over a column
    that defaults to ''. The SECOND job a tenant submitted without an
    idempotency key - which is most of them - raised IntegrityError. Every
    Signal brief after the first would have failed.
  * The partner_key column was only ever in CREATE TABLE, which does nothing
    to a database that already exists, so the NULL-key fix would not have
    reached any environment that had already run the old schema.
  * The rebuild that removes the bad constraint keyed off "is this an
    auto-index", which is true forever because `id TEXT PRIMARY KEY` makes
    one. It copied the whole table on every boot.

They use real databases and the real app rather than reading source, because
none of the three was visible in the source at a glance.
"""
import os
import sqlite3
import tempfile
import uuid

import pytest

import audio_jobs as aj
import audio_policy
import audio_providers as ap
import audio_store as astore


LEGACY_AUDIO_JOBS = """
CREATE TABLE audio_jobs (
    id TEXT PRIMARY KEY, partner_id TEXT, user_id TEXT NOT NULL,
    feature_key TEXT NOT NULL, provider TEXT NOT NULL DEFAULT '',
    capability TEXT NOT NULL DEFAULT '', operation TEXT NOT NULL DEFAULT '',
    provider_job_id TEXT, idempotency_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
    input_asset_ids TEXT NOT NULL DEFAULT '[]',
    output_asset_ids TEXT NOT NULL DEFAULT '[]',
    configuration TEXT, estimated_cost REAL, final_cost REAL,
    error_code TEXT, error_message TEXT, created_at TEXT NOT NULL,
    started_at TEXT, completed_at TEXT,
    partner_key TEXT NOT NULL DEFAULT '',
    UNIQUE(partner_key, idempotency_key)
);
"""


@pytest.fixture(scope="module", autouse=True)
def _app():
    """The schema and the adapter registry are both built by create_app, so
    the app is the setup - not a hand-rolled init that could drift from it."""
    import app as appmod
    application = appmod.create_app()
    with application.app_context():
        yield application


@pytest.fixture
def audio_flags(monkeypatch):
    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("SIGNAL_AUDIO_BRIEFS_ENABLED", "1")
    monkeypatch.setenv("MUSIC_GENERATION_ENABLED", "1")


def _uid():
    return "t-" + uuid.uuid4().hex[:10]


def _legacy_db():
    """A database created by the first cut of the schema, with a row in it."""
    path = os.path.join(tempfile.mkdtemp(prefix="sb-audio-mig-"), "legacy.db")
    c = sqlite3.connect(path)
    c.executescript(LEGACY_AUDIO_JOBS)
    c.execute("INSERT INTO audio_jobs (id, partner_id, partner_key, user_id, "
              "feature_key, status, created_at) VALUES "
              "('legacy-1', NULL, '', 'u1', 'signal_briefs', 'completed', "
              "'2026-08-01T00:00:00Z')")
    c.commit()
    c.close()
    return path


# --- the schema ------------------------------------------------------------

def test_second_keyless_job_is_not_a_collision(audio_flags):
    """The bug that would have broken every brief after the first."""
    made = [astore.create_job(None, _uid(), "signal_briefs", "speech", "synthesize")
            for _ in range(4)]
    assert len({j["id"] for j in made}) == 4, \
        "keyless jobs must not collide on the empty idempotency key"


def test_idempotency_key_still_guards_double_submits(audio_flags):
    """Dropping the false collision must not drop the real guard."""
    key = "k-" + uuid.uuid4().hex[:8]
    uid = _uid()
    a = astore.create_job(None, uid, "signal_briefs", "speech", "synthesize",
                          idempotency_key=key)
    b = astore.create_job(None, uid, "signal_briefs", "speech", "synthesize",
                          idempotency_key=key)
    assert a["id"] == b["id"], "a repeated idempotency key must return the same job"


def test_distinct_webhook_events_without_a_delivery_id_are_not_merged():
    """Same defect as the jobs table, found by a test that would not have been
    written without it: external_event_id defaults to '' and not every vendor
    sends a delivery id. Under a whole-column UNIQUE, genuinely different
    events were reported as duplicates and silently never processed."""
    ids = [astore.store_webhook_event("mock", "", "job.completed", True, body)[0]
           for body in ('{"job":"one"}', '{"job":"two"}', '{"job":"three"}')]
    assert len(set(ids)) == 3, "distinct id-less events were merged into one"


def test_a_genuine_webhook_retry_is_still_deduped():
    """Dropping the false collision must not drop the real guard: a vendor
    retrying the same delivery must not be processed twice."""
    ext = "evt-" + uuid.uuid4().hex[:8]
    first, dup_first = astore.store_webhook_event("mock", ext, "job.completed", True, "{}")
    again, dup_again = astore.store_webhook_event("mock", ext, "job.completed", True, "{}")
    assert dup_first is False
    assert dup_again is True
    assert first == again


def test_migration_rebuilds_a_legacy_database_once(monkeypatch):
    """CREATE TABLE IF NOT EXISTS is not a migration, and the rebuild that
    fixes it must not run on every boot.

    This asserts on what init_audio REPORTS having applied, not on the table's
    rootpage. The first version of this test watched rootpage and passed
    against code that rebuilt the table on every single boot, because SQLite
    reuses freed pages after a drop and rename and handed the replacement the
    same number.
    """
    path = _legacy_db()
    monkeypatch.setenv("DATABASE_PATH", path)

    first = astore.init_audio()
    second = astore.init_audio()
    third = astore.init_audio()

    assert "rebuild_audio_jobs_without_whole_column_unique" in first, \
        "the legacy UNIQUE constraint was not rebuilt out"
    assert second == [], "migrations re-ran on an already-current database: %r" % second
    assert third == [], "migrations re-ran on an already-current database: %r" % third


def test_a_fresh_database_needs_no_rebuild(monkeypatch):
    """Nothing legacy about it, so the rebuild step must never fire."""
    path = os.path.join(tempfile.mkdtemp(prefix="sb-audio-fresh-"), "fresh.db")
    monkeypatch.setenv("DATABASE_PATH", path)

    first = astore.init_audio()
    second = astore.init_audio()

    assert "rebuild_audio_jobs_without_whole_column_unique" not in first
    assert second == [], "migrations re-ran on a fresh database: %r" % second


def test_migration_preserves_existing_rows(monkeypatch):
    path = _legacy_db()
    monkeypatch.setenv("DATABASE_PATH", path)
    astore.init_audio()

    c = sqlite3.connect(path)
    try:
        rows = c.execute("SELECT id, status FROM audio_jobs").fetchall()
    finally:
        c.close()
    assert ("legacy-1", "completed") in rows, "the rebuild dropped existing jobs"


def test_migrated_database_accepts_keyless_jobs(monkeypatch):
    path = _legacy_db()
    monkeypatch.setenv("DATABASE_PATH", path)
    astore.init_audio()
    made = [astore.create_job(None, "u1", "signal_briefs", "speech", "synthesize")
            for _ in range(3)]
    assert len({j["id"] for j in made}) == 3


# --- the gate --------------------------------------------------------------

def test_a_refused_request_leaves_no_job_row(audio_flags):
    """A refusal cost nothing and sent nothing, so it is not in the ledger."""
    before = len(astore.list_jobs(None, limit=500))
    sub = aj.submit("dubbing", _uid(), {"source_asset_id": "x"})   # flag unset
    after = len(astore.list_jobs(None, limit=500))

    assert not sub.allowed
    assert sub.job is None
    assert before == after, "a refused request must not create a job row"


def test_refusal_carries_a_reason_a_person_can_act_on(audio_flags):
    sub = aj.submit("dubbing", _uid(), {"source_asset_id": "x"})
    assert sub.decision.code
    assert len(sub.decision.reason) > 20, \
        "a refusal must say what would make it pass, not just carry a code"


def test_zero_retention_is_refused_not_downgraded(audio_flags, monkeypatch):
    """The one mistake with no remedy: never label as zero-retention a job
    the provider has not verified it can run that way."""
    class NoZeroRetention(ap.SpeechProvider):
        key = "nozr"

        def health(self):
            return ap.ProviderHealth(True, "ready", "test double")

        def supports_zero_retention(self):
            return False

        def synthesize(self, request):
            raise AssertionError("must never be reached")

    ap.register(NoZeroRetention())
    pid = None
    astore.set_policy(pid, {"require_zero_retention": True,
                            "allow_voice_generation": True})
    try:
        sub = aj.submit("signal_briefs", _uid(), ap.SpeechRequest("x"),
                        adapter_key="nozr")
        assert not sub.allowed
        assert sub.decision.code == "zero_retention_unavailable"
        assert sub.job is None
    finally:
        astore.set_policy(pid, {"require_zero_retention": False})


# --- the runner ------------------------------------------------------------

def test_a_fast_job_completes_inside_submit(audio_flags):
    sub = aj.submit("signal_briefs", _uid(), ap.SpeechRequest("Tour brief."))
    assert sub.allowed
    assert sub.job["status"] == "completed"


def test_the_payload_is_never_written_to_the_jobs_table(audio_flags):
    """configuration records HOW a job was set up, never what was in it. This
    row is read by support."""
    secret = "the unannounced festival headline slot"
    sub = aj.submit("signal_briefs", _uid(), ap.SpeechRequest(secret))
    assert secret not in (sub.job["configuration"] or "")


def test_provider_refusal_is_terminal_and_not_retried(audio_flags):
    """A provider that said no will say no again; retrying only spends money."""
    astore.set_policy(None, {"allow_music_generation": True})
    sub = aj.submit("music_generation", _uid(), {"prompt": "x"},
                    rights_confirmed=True)
    assert sub.allowed, "the gate should pass so the ADAPTER is the one refusing"
    assert sub.job["status"] == "rejected"
    assert sub.job["attempts"] == 1, "a refusal must not be retried"


def test_an_unreachable_vendor_is_retryable(audio_flags):
    """The opposite case: a transport failure is a condition that passes."""
    class Flaky(ap.MusicProvider):
        key = "flaky"

        def health(self):
            return ap.ProviderHealth(True, "ready", "test double")

        def supports_zero_retention(self):
            return True

        def generate(self, request):
            raise ap.ProviderUnavailable("connection reset")

    ap.register(Flaky())
    astore.set_policy(None, {"allow_music_generation": True})
    sub = aj.submit("music_generation", _uid(), {"prompt": "x"},
                    rights_confirmed=True, adapter_key="flaky")
    job = astore.get_job(None, sub.job["id"])
    assert job["status"] == "queued", "an outage must leave the job retryable"
    assert job["error_code"] == "provider_unavailable"


def test_an_adapter_bug_is_not_reported_as_a_vendor_outage(audio_flags):
    """Otherwise it gets retried three times and blamed on the vendor."""
    class Broken(ap.MusicProvider):
        key = "broken"

        def health(self):
            return ap.ProviderHealth(True, "ready", "test double")

        def supports_zero_retention(self):
            return True

        def generate(self, request):
            raise KeyError("model_id")

    ap.register(Broken())
    astore.set_policy(None, {"allow_music_generation": True})
    sub = aj.submit("music_generation", _uid(), {"prompt": "x"},
                    rights_confirmed=True, adapter_key="broken")
    assert sub.job["status"] == "failed"
    assert sub.job["error_code"] == "adapter_error"


def test_usage_is_recorded_even_for_mock_jobs(audio_flags):
    """A ledger with rows only when a vendor was involved cannot answer the
    question it exists for."""
    uid = _uid()
    aj.submit("signal_briefs", uid, ap.SpeechRequest("Brief."))
    rows = astore.usage_summary(None)
    assert any(r["operation"] == "synthesize" for r in rows)


def test_an_unknown_operation_cannot_reach_adapter_attributes(audio_flags):
    """_invoke maps operations explicitly rather than getattr-ing a string."""
    with pytest.raises(ap.ProviderRefusal):
        aj._invoke(ap.get(ap.SPEECH), "health", None)


# --- degradation -----------------------------------------------------------

def test_every_capability_resolves_to_something(audio_flags):
    """A missing vendor degrades to an honest offline mock, never to nothing."""
    for cap in ap.CAPABILITIES:
        adapter = ap.get(cap)
        assert adapter is not None, "no adapter at all for %s" % cap


def test_the_vendor_adapter_never_claims_health_it_has_not_verified(monkeypatch):
    """A key in the environment is not evidence that anything works."""
    monkeypatch.setenv("ELEVENLABS_ENABLED", "1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_not_a_real_key")
    for cap in (ap.SPEECH, ap.TRANSCRIPTION, ap.AGENT):
        adapter = ap.adapters_for(cap).get("elevenlabs")
        if adapter is None:
            continue
        health = adapter.health()
        assert not health.verified_live or health.ok, \
            "verified_live must only be set by a call that actually succeeded"
