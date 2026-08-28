"""Street Banker Audio Intelligence - the job runner.

THE ONE WAY IN
--------------
Every piece of audio work goes through submit(). It gates, records, dispatches
and settles, in that order, and there is no second entry point. A caller that
reaches an adapter directly has bypassed consent, entitlement, retention and
the usage ledger, so the adapters are never imported anywhere but here and the
gate.

SYNCHRONOUS AND SLOW WORK, ONE SHAPE
------------------------------------
Speech and sound effects come back in one call. Dubbing and stem separation
take minutes and answer later, by polling or by webhook. Both produce the same
audio_jobs row and the same statuses, so the UI has one thing to render and one
thing to poll. A fast job simply reaches "completed" inside submit().

REFUSAL IS NOT FAILURE
----------------------
ProviderRefusal -> "rejected", terminal, never retried: the provider has made a
decision and trying again will produce the same decision while costing another
call. ProviderUnavailable -> back to "queued" until MAX_ATTEMPTS: the vendor was
unreachable, which is a condition that passes. Collapsing the two is how a repo
ends up hammering an endpoint that has said no.

BILLING IS RECORDED ON THE WAY OUT, ALWAYS
------------------------------------------
record_usage runs for mock jobs too, with a null cost. A ledger that only has
rows when a vendor was involved cannot answer "what did this artist actually
use", which is the question the ledger exists for.
"""
import json
import traceback

import audio_policy
import audio_providers as ap
import audio_store as astore

# After this many attempts a job that keeps failing to reach the vendor stops
# trying. Low on purpose: audio work is expensive, and a queue that retries
# forever turns one bad afternoon into a bill.
MAX_ATTEMPTS = 3

# Operations that answer inside the same call. Anything not listed is assumed
# slow and left for the poller, which is the safe direction to be wrong in:
# a slow job that was actually fast just settles on the next sweep, whereas a
# fast job wrongly awaited would block a request.
SYNCHRONOUS = {"synthesize", "generate_effect", "isolate", "composition_plan"}


class Submission(object):
    """What a caller gets back: the job row, and why, if it did not start."""

    def __init__(self, job=None, decision=None, error=None):
        self.job = job
        self.decision = decision
        self.error = error

    @property
    def allowed(self):
        return bool(self.decision and self.decision.allowed)

    @property
    def status(self):
        return (self.job or {}).get("status")

    def as_dict(self):
        out = {"allowed": self.allowed, "job": self.job, "error": self.error}
        if self.decision is not None:
            out["decision"] = self.decision.as_dict()
        return out


def submit(feature, user_id, request, partner_id=None, member=None,
           subject_id="", rights_confirmed=False, budget_check=None,
           adapter_key=None, idempotency_key=None, input_asset_ids=None):
    """Gate, record, dispatch. Returns a Submission; does not raise for refusal.

    `request` is the capability-shaped request object or dict the adapter
    expects. It is built by the caller because only the caller knows the
    domain; this function's job is to make sure it is allowed to exist.
    """
    decision = audio_policy.gate(
        feature, partner_id=partner_id, member=member, subject_id=subject_id,
        rights_confirmed=rights_confirmed, budget_check=budget_check,
        adapter_key=adapter_key)

    if not decision.allowed:
        # Deliberately no audio_jobs row. A refused request never happened as
        # far as the ledger is concerned - it cost nothing and sent nothing.
        return Submission(None, decision)

    spec = audio_policy.FEATURES[feature]
    adapter = decision.adapter
    operation = _operation_for(spec["capability"], request)

    job = astore.create_job(
        partner_id, user_id, feature, spec["capability"], operation,
        provider=adapter.key, input_asset_ids=input_asset_ids,
        configuration=_safe_config(request), idempotency_key=idempotency_key)

    # An idempotent re-submit of work already done returns it untouched rather
    # than dispatching a second time.
    if job.get("status") in ("completed", "running", "rejected"):
        return Submission(job, decision)

    return Submission(_dispatch(job, adapter, request, partner_id), decision)


def _dispatch(job, adapter, request, partner_id):
    """Call the adapter once and settle the job as far as it can go."""
    jid = job["id"]
    astore.set_job_status(partner_id, jid, "running")

    try:
        result = _invoke(adapter, job["operation"], request)
    except ap.ProviderRefusal as r:
        # Terminal. The provider decided; retrying spends money to hear it again.
        astore.set_job_status(partner_id, jid, "rejected",
                              error_code=r.code, error_message=r.reason)
        return astore.get_job(partner_id, jid)
    except ap.ProviderUnavailable as e:
        return _retry_or_fail(partner_id, jid, "provider_unavailable", str(e))
    except Exception as e:
        # An adapter bug must not look like a vendor outage - that would get it
        # retried three times and then blamed on the vendor.
        astore.set_job_status(
            partner_id, jid, "failed", error_code="adapter_error",
            error_message="%s: %s" % (type(e).__name__, e))
        _log_unexpected(jid, e)
        return astore.get_job(partner_id, jid)

    provider_job_id = (result or {}).get("provider_job_id")
    _record_usage(job, adapter, result, partner_id)

    status = (result or {}).get("status") or "completed"
    if job["operation"] in SYNCHRONOUS or status == "completed":
        astore.set_job_status(partner_id, jid, "completed",
                              provider_job_id=provider_job_id)
    else:
        # Slow work: the row stays running and the poller or the webhook
        # finishes it. provider_job_id is written now so both can find it.
        astore.set_job_status(partner_id, jid, "running",
                              provider_job_id=provider_job_id)

    out = astore.get_job(partner_id, jid)
    out["result"] = result
    return out


def _retry_or_fail(partner_id, job_id, code, message):
    """Unreachable vendor: queue it again unless it has had its chances."""
    job = astore.get_job(partner_id, job_id) or {}
    if (job.get("attempts") or 0) >= MAX_ATTEMPTS:
        astore.set_job_status(partner_id, job_id, "failed", error_code=code,
                              error_message="%s (gave up after %d attempts)"
                                            % (message, MAX_ATTEMPTS))
    else:
        astore.set_job_status(partner_id, job_id, "queued", error_code=code,
                              error_message=message)
    return astore.get_job(partner_id, job_id)


def _invoke(adapter, operation, request):
    """The capability verb for this operation. Explicit rather than getattr on
    a caller-supplied string, so a bad operation cannot reach arbitrary
    attributes of the adapter."""
    verbs = {
        "transcribe": "transcribe", "synthesize": "synthesize",
        "create_project": "create_project", "download": "download",
        "generate": "generate", "inpaint": "inpaint",
        "composition_plan": "composition_plan", "upload_owned": "upload_owned",
        "separate": "separate", "isolate": "isolate",
        "generate_effect": "generate_effect",
        "register_verified_voice": "register_verified_voice",
        "create_agent": "create_agent", "create_session": "create_session",
    }
    verb = verbs.get(operation)
    if verb is None:
        raise ap.ProviderRefusal("Unknown operation: %s" % operation, "unknown_operation")
    fn = getattr(adapter, verb, None)
    if fn is None:
        raise ap.ProviderRefusal(
            "This provider does not offer %s." % operation, "unsupported")
    return fn(request)


def _operation_for(capability, request):
    """Default verb per capability, overridable by the request itself."""
    if isinstance(request, dict) and request.get("operation"):
        return request["operation"]
    op = getattr(request, "operation", None)
    if op:
        return op
    return {
        ap.TRANSCRIPTION: "transcribe", ap.SPEECH: "synthesize",
        ap.DUBBING: "create_project", ap.MUSIC: "generate",
        ap.STEMS: "separate", ap.VOICE_ISOLATION: "isolate",
        ap.SOUND_EFFECTS: "generate_effect",
        ap.VOICE_IDENTITY: "register_verified_voice",
        ap.AGENT: "create_session",
    }.get(capability, "unknown")


# Fields that must never be written to the jobs table. The text of a brief is
# the artist's business, not configuration, and audio bytes are not JSON.
_NEVER_STORE = {"audio", "text", "api_key", "secret", "token"}


def _safe_config(request):
    """A small, readable record of how the job was configured - never its
    payload. This row is read by support and shown in admin."""
    if isinstance(request, dict):
        src = request
    elif hasattr(request, "__dict__"):
        src = vars(request)
    else:
        src = {}
    out = {}
    for k, v in (src or {}).items():
        if k in _NEVER_STORE or isinstance(v, (bytes, bytearray)):
            continue
        if isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v[:200] if isinstance(v, str) else v
        elif isinstance(v, (list, tuple)):
            out[k] = [x for x in v if isinstance(x, (str, int, float, bool))][:20]
    return out


def _record_usage(job, adapter, result, partner_id):
    """Always, including for mocks. Cost stays null unless the vendor said."""
    r = result or {}
    try:
        astore.record_usage(
            partner_id, adapter.key, job["operation"],
            input_units=r.get("input_units") or r.get("characters") or 0,
            output_units=r.get("output_units") or r.get("duration_ms") or 0,
            unit=r.get("unit") or ("ms" if r.get("duration_ms") else "chars"),
            user_id=job.get("user_id"), job_id=job.get("id"),
            model=r.get("model") or "",
            final_cost=r.get("cost"),
            provider_request_id=r.get("provider_job_id"))
    except Exception as e:
        # A ledger write must never lose completed work. It is recorded as a
        # problem, not raised into the caller's face.
        _log_unexpected(job.get("id"), e)


def poll(partner_id, job_id):
    """Advance one slow job. Safe to call on a job that is already settled."""
    job = astore.get_job(partner_id, job_id)
    if not job or job.get("status") != "running":
        return job
    if not job.get("provider_job_id"):
        return job

    adapter = ap.get(job.get("capability"), job.get("provider"))
    status_fn = getattr(adapter, "status", None) if adapter else None
    if status_fn is None:
        return job

    try:
        res = status_fn(job["provider_job_id"]) or {}
    except ap.ProviderRefusal as r:
        astore.set_job_status(partner_id, job_id, "rejected",
                              error_code=r.code, error_message=r.reason)
        return astore.get_job(partner_id, job_id)
    except ap.ProviderUnavailable as e:
        # Still running as far as we know - a poll that could not reach the
        # vendor is not evidence the job failed.
        _log_unexpected(job_id, e)
        return job
    except Exception as e:
        _log_unexpected(job_id, e)
        return job

    state = res.get("status")
    if state == "completed":
        astore.set_job_status(partner_id, job_id, "completed")
        _store_result(partner_id, job, res)
    elif state in ("failed", "error"):
        astore.set_job_status(partner_id, job_id, "failed",
                              error_code=res.get("error_code") or "provider_failed",
                              error_message=res.get("error") or "The provider reported a failure.")
    out = astore.get_job(partner_id, job_id)
    if out:
        out["result"] = res
    return out


def _store_result(partner_id, job, res):
    """Persist whatever the finished job produced that has a home."""
    try:
        if job.get("capability") == ap.TRANSCRIPTION and res.get("segments"):
            ids = json.loads(job.get("input_asset_ids") or "[]")
            astore.save_transcript(partner_id, ids[0] if ids else None,
                                   job.get("provider") or "", res)
    except Exception as e:
        _log_unexpected(job.get("id"), e)


def run_pending(partner_id=None, limit=25):
    """One sweep: poll everything running. Called by the route and by cron."""
    advanced = []
    for job in astore.list_jobs(partner_id, limit=limit, status="running"):
        before = job.get("status")
        after = poll(partner_id, job["id"]) or {}
        if after.get("status") != before:
            advanced.append({"id": job["id"], "from": before,
                             "to": after.get("status")})
    return advanced


def _log_unexpected(job_id, exc):
    try:
        import logging
        logging.getLogger("audio").warning(
            "audio job %s: %s: %s\n%s", job_id, type(exc).__name__, exc,
            traceback.format_exc())
    except Exception:
        pass
