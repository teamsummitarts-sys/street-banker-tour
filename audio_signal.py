"""Signal Audio Briefs, wired into Signal.

Registers on Signal's own blueprint so it inherits the org guard, the roster
check and the denied page. Same reasoning as the Desk: a second permission
system beside the first is how two of them end up disagreeing.

THE AUDIO IS PRIVATE
--------------------
A brief names artists an organisation is watching and says why. That is the
organisation's strategy read aloud. It is stored outside the public uploads
tree and served through a route that re-checks the seat on every request -
never as a URL that works for anyone holding it.
"""
import os
import time

from flask import abort, redirect, render_template, request, send_file, url_for

import audio_briefs as briefs
import audio_jobs
import audio_policy
import audio_providers as ap
import audio_retention
import audio_store as astore
import blob_store

_registered = False

BRIEF_PREFIX = "brief:"


def _audio_on():
    return audio_policy.flag("AUDIO_INTELLIGENCE_ENABLED") and \
        audio_policy.flag("SIGNAL_AUDIO_BRIEFS_ENABLED")


def _brief_dir():
    import db as store
    path = os.path.join(os.path.dirname(store.db_path()), "signal_briefs")
    os.makedirs(path, exist_ok=True)
    return path


def _save_brief_audio(fname, data, content_type="audio/wav"):
    """Bucket when configured, private directory otherwise. Never the public
    uploads tree - a brief is an organisation's strategy spoken aloud."""
    if blob_store.configured():
        try:
            if blob_store.put("briefs/" + fname, data, content_type):
                return blob_store.PREFIX + "briefs/" + fname
        except Exception:
            pass                      # fall through to disk; do not lose it
    with open(os.path.join(_brief_dir(), fname), "wb") as handle:
        handle.write(data)
    return BRIEF_PREFIX + fname


def register(bp, require, ctx, sstore):
    global _registered
    if _registered:
        return
    _registered = True

    @bp.route("/briefs")
    @require("view")
    def briefs_index(org, member):
        return render_template("signal/briefs.html", **ctx(
            org, member, briefs=briefs.list_briefs(org["id"]),
            audio_on=_audio_on()))

    @bp.route("/briefs/new", methods=["POST"])
    @require("view")
    def brief_new(org, member):
        if not _audio_on():
            return render_template("signal/denied.html", **ctx(
                org, member, denied=True,
                reason="Signal Audio Briefs are switched off on this "
                       "deployment.")), 404

        window = 7
        try:
            window = max(1, min(90, int(request.form.get("window") or 7)))
        except (TypeError, ValueError):
            window = 7

        alerts = sstore.list_alerts(org["id"], limit=200)
        cutoff = _cutoff(window)
        recent = [a for a in alerts if (a.get("created_at") or "") >= cutoff]

        script = briefs.compose_script(recent, window_days=window,
                                       org_name=org.get("name") or "")
        brief = briefs.create_brief(
            org["id"], script, created_by=member.get("name") or "",
            title="Signal brief, %s" % _now_date(),
            window_days=window, item_count=len(recent))
        return redirect(url_for("signal.brief_detail", brief_id=brief["id"]))

    @bp.route("/briefs/<brief_id>")
    @require("view")
    def brief_detail(org, member, brief_id):
        brief = briefs.get_brief(brief_id)
        if brief is None or brief["organization_id"] != org["id"]:
            abort(404)
        return render_template("signal/brief.html", **ctx(
            org, member, brief=brief, audio_on=_audio_on()))

    @bp.route("/briefs/<brief_id>/speak", methods=["POST"])
    @require("view")
    def brief_speak(org, member, brief_id):
        brief = briefs.get_brief(brief_id)
        if brief is None or brief["organization_id"] != org["id"]:
            abort(404)

        submission = audio_jobs.submit(
            "signal_briefs", member.get("email") or "signal",
            ap.SpeechRequest(brief["script"]),
            subject_id=brief_id,
            # One rendering per brief. Speech is charged per character, and
            # the script cannot change once it is written.
            idempotency_key="brief:%s" % brief_id)

        if not submission.allowed:
            return render_template("signal/denied.html", **ctx(
                org, member, denied=True,
                reason=submission.decision.reason)), 403

        job = submission.job
        briefs.set_brief_audio(brief_id, job_id=job["id"], status=job["status"])

        result = (job or {}).get("result") or {}
        audio = result.get("audio")
        if audio:
            fname = "brief_%s_%d.wav" % (brief_id[:8], int(time.time()))
            path = _save_brief_audio(fname, audio,
                                     result.get("mime_type") or "audio/wav")
            asset_id = astore.create_asset(
                None, member.get("email") or "signal", path,
                file_name=fname, mime_type=result.get("mime_type") or "audio/wav",
                file_size=len(audio), asset_type="generated",
                duration_ms=result.get("duration_ms"),
                retention_days=audio_retention.retention_days(None, "generated"))
            briefs.set_brief_audio(brief_id, audio_asset_id=asset_id,
                                   status="ready",
                                   is_mock=bool(result.get("is_mock")))

        return redirect(url_for("signal.brief_detail", brief_id=brief_id))

    @bp.route("/briefs/<brief_id>/audio")
    @require("view")
    def brief_audio(org, member, brief_id):
        """The seat is re-checked here by the decorator. This is deliberately
        not a shareable URL: a brief names who an organisation is watching."""
        brief = briefs.get_brief(brief_id)
        if brief is None or brief["organization_id"] != org["id"]:
            abort(404)
        if not brief.get("audio_asset_id"):
            abort(404)

        asset = astore.get_asset(None, brief["audio_asset_id"])
        if asset is None or asset.get("deleted_at") or not asset.get("storage_key"):
            # Past its retention date, and destroyed. Saying so beats a 500.
            abort(410)

        path = asset["storage_key"]
        if blob_store.is_remote(path):
            url = blob_store.url_for(path, ttl=300)
            if url == path:
                abort(503)
            return redirect(url)
        if path.startswith(BRIEF_PREFIX):
            return send_file(os.path.join(_brief_dir(), path[len(BRIEF_PREFIX):]),
                             mimetype=asset.get("mime_type") or "audio/wav")
        abort(404)

    @bp.route("/briefs/<brief_id>/delete", methods=["POST"])
    @require("view")
    def brief_delete(org, member, brief_id):
        brief = briefs.get_brief(brief_id)
        if brief is None or brief["organization_id"] != org["id"]:
            abort(404)
        if brief.get("audio_asset_id"):
            asset = astore.get_asset(None, brief["audio_asset_id"])
            if asset and asset.get("storage_key"):
                try:
                    if asset["storage_key"].startswith(BRIEF_PREFIX):
                        os.remove(os.path.join(
                            _brief_dir(), asset["storage_key"][len(BRIEF_PREFIX):]))
                    else:
                        blob_store.remove(asset["storage_key"],
                                          uploads_dir=audio_retention.uploads_dir())
                except OSError:
                    pass
                astore.mark_asset_deleted(brief["audio_asset_id"])
        briefs.delete_brief(brief_id)
        return redirect(url_for("signal.briefs_index"))


def _cutoff(window_days):
    import datetime
    stamp = datetime.datetime.now(datetime.timezone.utc) - \
        datetime.timedelta(days=window_days)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_date():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y")
