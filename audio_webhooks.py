"""Street Banker Audio Intelligence - the inbound edge.

Long audio work finishes on the vendor's clock, not ours. Dubbing, stem
separation and agent conversations all answer later, and this is where they
land.

THE ORDER IS THE SECURITY
-------------------------
 1. 404 unless the feature is switched on. An endpoint that answers
    differently when a feature is off tells a stranger what is deployed here.
 2. Verify the signature over the RAW body, before anything is parsed. A
    payload that has been JSON-decoded and re-encoded is no longer the bytes
    that were signed, and a verification done after that check is worthless.
 3. Only then record the event, and only then act on it.

Nothing in the body is trusted to say which tenant it belongs to. The job id
is looked up in our own tables and the tenant comes from the row we already
had. A webhook that could nominate its own partner_id is a webhook that can
write into any tenant on the instance.

DUPLICATES ARE NORMAL
---------------------
Vendors retry, and a retry means they did not hear our 200 - not that
anything is wrong. A repeat gets the same answer as the first time and does
no work twice. Storage dedupes on (provider, external_event_id), so the
second delivery is recognised even across processes.

WHY IT ALWAYS RETURNS 200 ONCE THE SIGNATURE IS GOOD
----------------------------------------------------
A signed event we could not process is our problem, not the vendor's. Return
a 500 and they retry on a schedule we do not control, forever, for a job that
will never succeed. The event is stored with its failure reason and shows up
in admin instead, where a person can see it.
"""
import os

from flask import Blueprint, jsonify, request

import audio_jobs
import audio_providers as ap
import audio_store as astore

bp = Blueprint("audio_webhooks", __name__)

_TRUE = ("1", "true", "yes", "on")


def _enabled():
    return (os.environ.get("AUDIO_INTELLIGENCE_ENABLED") or "").strip().lower() in _TRUE


def _secret(provider):
    """Per-provider signing secret. Absent means the endpoint stays shut: an
    unverifiable webhook is not accepted on trust."""
    return os.environ.get("%s_WEBHOOK_SECRET" % provider.upper()) or ""


@bp.route("/webhooks/audio/<provider>", methods=["POST"])
def audio_webhook(provider):
    if not _enabled():
        return jsonify({"ok": False}), 404

    provider = (provider or "").strip().lower()[:40]
    if not provider or provider not in {a for cap in ap.CAPABILITIES
                                        for a in ap.adapters_for(cap)}:
        return jsonify({"ok": False}), 404

    secret = _secret(provider)
    if not secret:
        # Configured to receive nothing. Say 404 rather than 401: whether a
        # secret is set is not a stranger's business.
        return jsonify({"ok": False}), 404

    raw = request.get_data()            # bytes, exactly as signed
    headers = dict(request.headers)

    adapter = _signing_adapter(provider)
    if adapter is None or not adapter.verify_webhook(raw, headers, secret):
        # Recorded so a run of bad signatures is visible in admin rather than
        # only in a log nobody reads.
        astore.store_webhook_event(provider, _external_id(headers), "",
                                   False, raw.decode("utf-8", "replace")[:8000])
        return jsonify({"ok": False, "error": "bad signature"}), 401

    payload = request.get_json(silent=True) or {}
    event_type = str(payload.get("type") or payload.get("event") or "")[:80]

    event_id, duplicate = astore.store_webhook_event(
        provider, _external_id(headers, payload), event_type, True,
        raw.decode("utf-8", "replace")[:8000])
    if duplicate:
        return jsonify({"ok": True, "duplicate": True})

    try:
        advanced = _apply(provider, event_type, payload)
    except Exception as exc:
        astore.mark_webhook(event_id, "failed",
                            "%s: %s" % (type(exc).__name__, exc))
        # 200 on purpose - see the module docstring.
        return jsonify({"ok": True, "processed": False})

    astore.mark_webhook(event_id, "processed")
    return jsonify({"ok": True, "advanced": advanced})


def _signing_adapter(provider):
    """Any adapter of this vendor can verify - signing is per-vendor, not per
    capability - but the agent one is where verify_webhook actually lives."""
    for cap in (ap.AGENT,) + ap.CAPABILITIES:
        adapter = ap.adapters_for(cap).get(provider)
        if adapter is not None and hasattr(adapter, "verify_webhook"):
            return adapter
    return None


def _external_id(headers, payload=None):
    """The vendor's own id for this delivery, used for dedup."""
    for key in ("X-Event-Id", "X-Request-Id", "Webhook-Id", "X-Delivery-Id"):
        val = headers.get(key)
        if val:
            return str(val)[:120]
    if payload:
        for key in ("event_id", "id", "request_id"):
            if payload.get(key):
                return str(payload[key])[:120]
    return ""


def _apply(provider, event_type, payload):
    """Advance whatever job this event is about.

    The tenant is taken from OUR row, never from the payload. The only thing
    the vendor gets to tell us is which of their job ids finished.
    """
    provider_job_id = (payload.get("provider_job_id") or payload.get("job_id")
                       or payload.get("dubbing_id") or payload.get("conversation_id")
                       or (payload.get("data") or {}).get("id") or "")
    if not provider_job_id:
        return []

    job = _job_by_provider_id(provider, str(provider_job_id))
    if job is None:
        # Not ours, or already cleaned up. Not an error.
        return []

    after = audio_jobs.poll(job["partner_id"], job["id"])
    return [{"job_id": job["id"], "status": (after or {}).get("status")}]


def _job_by_provider_id(provider, provider_job_id):
    """Deliberately not scoped to a tenant: the caller does not know one yet,
    and the whole point is to find out which tenant owns this job. Matching is
    on the vendor's id plus the vendor's name, both of which we issued or
    recorded ourselves."""
    from db import get_db
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM audio_jobs WHERE provider = ? AND provider_job_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (provider, provider_job_id)).fetchone()
    return dict(row) if row else None


def init(app):
    app.register_blueprint(bp)
