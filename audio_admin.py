"""Street Banker Audio Intelligence - the operator's window.

WHAT THIS PAGE IS FOR
---------------------
Everything under it is invisible by design: adapters that refuse quietly,
jobs that settle on a vendor's clock, webhooks that arrive signed or not,
audio that passes its retention date. A control nobody can see is a control
nobody trusts, so this is where all four are shown to a person.

IT REPORTS, IT DOES NOT REASSURE
--------------------------------
Health comes from the adapters themselves, which only claim `ready` after a
call has actually succeeded. Rejected webhooks are listed alongside accepted
ones, because a run of bad signatures is the thing worth noticing. Retention
shows what is OVERDUE, not what is scheduled - the number that matters is the
one that should be zero.

OWNER ONLY
----------
Gated on the same predicate as the rest of the platform's internal surfaces,
which reads hashed emails plus OWNER_EMAILS. No person's name appears here.
"""
from flask import Blueprint, jsonify, redirect, render_template, request, url_for

import audio_jobs
import audio_policy
import audio_providers as ap
import audio_retention
import audio_store as astore

bp = Blueprint("audio_admin", __name__)

# Set by init() so this module does not reach back into app.py for it.
_is_owner_email = None
_current_user = None


def _guard():
    """Returns the signed-in owner, or None. Callers redirect on None."""
    user = _current_user() if _current_user else None
    if user is None:
        return None
    if _is_owner_email and not _is_owner_email(user.get("email")):
        return None
    return user


def _provider_rows():
    """One row per capability, not one per adapter.

    The flat health report is adapter-shaped: nine capabilities times every
    registered adapter, which renders as nineteen rows carrying the same
    sentence nine times over. That buries the only question an operator
    actually has, which is "for transcription, who is answering right now".

    So the serving adapter leads, and the others follow as small badges. The
    detail shown is the SERVING adapter's, because that is the one doing the
    work.
    """
    by_capability = {}
    for row in ap.health_report():
        by_capability.setdefault(row["capability"], []).append(row)

    rows = []
    for capability in ap.CAPABILITIES:
        entries = by_capability.get(capability) or []
        if not entries:
            continue
        serving = ap.get(capability)
        serving_key = getattr(serving, "key", None)
        active = next((e for e in entries if e["adapter"] == serving_key), entries[0])
        others = [e for e in entries if e["adapter"] != active["adapter"]]
        rows.append({
            "capability": capability,
            "label": ap.CAPABILITY_LABELS.get(capability, capability),
            "serving": active["adapter"],
            "state": active["state"],
            "detail": active["detail"],
            "others": sorted(others, key=lambda e: e["adapter"]),
        })
    return rows


def _flag_rows():
    """Every flag, whether it is on, and whether it gates anything at all.

    Values are never shown - only on or off - and no credential appears here.

    `wired` matters: some names in FLAGS gate NOTHING. An operator could switch
    one on, watch this page report it "on", and nothing whatsoever would change.
    A switch that reports its own state and has no effect is worse than an
    absent one, so the page says which is which.
    """
    gated = {spec["flag"] for spec in audio_policy.FEATURES.values()}
    # Read directly by their own modules rather than through FEATURES.
    gated |= {"AUDIO_INTELLIGENCE_ENABLED", "ELEVENLABS_ENABLED"}
    # The Studio's lanes carry their own advertising flag, which is not always
    # the one the gate checks - GLOBAL_RELEASE_PACK_ENABLED shows the dubbing
    # lane while the gate reads DUBBING_ENABLED. Reading FEATURES alone called
    # it unwired, which would have been a new false statement on this page.
    try:
        import audio_studio
        gated |= {lane[2] for lane in audio_studio.LANES}
    except Exception:
        pass
    return [{"name": name, "on": audio_policy.flag(name),
             "wired": name in gated}
            for name in audio_policy.FLAGS]


def _secret_presence():
    """Whether a credential EXISTS, never what it is.

    An operator needs to know a key is set without the page becoming a place
    to read it, so this reports presence only and the value never leaves the
    process.
    """
    import os
    out = []
    for name in ("ELEVENLABS_API_KEY", "ELEVENLABS_WEBHOOK_SECRET",
                 "ELEVENLABS_ZERO_RETENTION_VERIFIED"):
        out.append({"name": name, "set": bool((os.environ.get(name) or "").strip())})
    return out


@bp.route("/admin/audio")
def audio_admin():
    user = _guard()
    if user is None:
        return redirect(url_for("login", next=request.path))

    jobs = astore.list_jobs(None, limit=40)
    counts = {}
    for job in astore.list_jobs(None, limit=500):
        counts[job["status"]] = counts.get(job["status"], 0) + 1

    return render_template(
        "audio_admin.html",
        health=ap.health_report(),
        providers=_provider_rows(),
        flags=_flag_rows(),
        secrets=_secret_presence(),
        jobs=jobs,
        counts=counts,
        usage=astore.usage_summary(None),
        events=astore.list_webhook_events(limit=25),
        policy=astore.get_policy(None),
        overdue=audio_retention.due_count(),
        capability_labels=ap.CAPABILITY_LABELS,
    )


@bp.route("/admin/audio/sweep", methods=["POST"])
def audio_sweep():
    """Run the retention sweep by hand.

    A dry run is the default from the UI: an operator pressing a button
    labelled with a number should get to see what would happen before
    anything is destroyed.
    """
    if _guard() is None:
        return jsonify({"ok": False}), 404
    dry = (request.form.get("confirm") or "").strip().lower() not in ("1", "yes", "true")
    report = audio_retention.sweep(dry_run=dry)
    return jsonify({"ok": True, "report": report})


@bp.route("/admin/audio/poll", methods=["POST"])
def audio_poll():
    """Advance any job still waiting on a vendor. Safe to press twice."""
    if _guard() is None:
        return jsonify({"ok": False}), 404
    return jsonify({"ok": True, "advanced": audio_jobs.run_pending(None)})


def init(app, is_owner_email=None, current_user=None):
    global _is_owner_email, _current_user
    _is_owner_email = is_owner_email
    _current_user = current_user
    app.register_blueprint(bp)
