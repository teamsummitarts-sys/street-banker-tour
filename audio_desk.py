"""Meeting Intelligence, wired into the Operator Desk.

WHY A SEPARATE MODULE
---------------------
operator_desk.py is already long, and this is the first thing in the Desk
that can cost money and touch a vendor. Keeping it here means the audio
imports, the gate and the job plumbing sit in one file that can be read on
its own - and the Desk's own routes keep working with the audio feature off.

IT REGISTERS ON THE DESK'S BLUEPRINT
------------------------------------
Same URL prefix, same @require decorator, same denied page. Meeting pages are
Desk pages: a second permission system beside the first is how two of them
end up disagreeing.

NOTHING REACHES A LEAD WITHOUT A PERSON
---------------------------------------
The extractor proposes; a human disposes. Approving a candidate is what
writes a task or a note, it records who approved it, and the audit trail says
it came from a meeting. "The system added this" is not an answer anybody
accepts when a task turns out to be wrong.
"""
import mimetypes
import os
import time

from flask import (abort, jsonify, redirect, render_template, request,
                   url_for)

import audio_agent as agent
import audio_jobs
import audio_meetings as meetings
import audio_policy
import audio_providers as ap
import audio_retention
import audio_store as astore
import blob_store
import desk_store

# Audio a meeting can plausibly arrive as. Deliberately narrower than the
# Desk's general file list: this is fed to a transcription provider, and a
# .docx reaching that path is a bug, not a format to support.
MEETING_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".mp4", ".aac", ".ogg",
                      ".oga", ".flac", ".webm"}

MAX_MEETING_BYTES = 200 * 1024 * 1024      # 200 MB


def _audio_on():
    return audio_policy.flag("AUDIO_INTELLIGENCE_ENABLED") and \
        audio_policy.flag("MEETING_INTELLIGENCE_ENABLED")


def _agent_on():
    return audio_policy.flag("AUDIO_INTELLIGENCE_ENABLED") and \
        audio_policy.flag("AUDIO_OPERATOR_ENABLED")


_registered = False


def register(bp, require, ctx, save_file, desk_prefix):
    """Attach the meeting routes to the Desk blueprint.

    The Desk's own guard, context builder and file saver are passed in rather
    than imported, so this module cannot drift into a second copy of any of
    them.

    Runs at most once per process. The Desk blueprint is a module-level
    singleton and app.py builds an app at import, so a second create_app -
    which every test that wants a clean app does - would otherwise try to add
    routes to a blueprint Flask has already registered, and Flask refuses.
    The Desk's own routes sidestep this by being declared at import time;
    these cannot be, because they need the guard passed in.
    """
    global _registered
    if _registered:
        return
    _registered = True

    # --- list -------------------------------------------------------------

    @bp.route("/meetings")
    @require("view")
    def meetings_index(me):
        rows = meetings.list_meetings()
        for row in rows:
            row["counts"] = meetings.counts(row["id"])
        return render_template("desk/meetings.html", **ctx(
            me, meetings=rows, audio_on=_audio_on(),
            leads=desk_store.list_leads()))

    # --- upload -----------------------------------------------------------

    @bp.route("/meetings/upload", methods=["POST"])
    @require("file_upload")
    def meeting_upload(me):
        if not _audio_on():
            return render_template("desk/denied.html",
                                   message="Meeting Intelligence is switched "
                                           "off on this deployment."), 404

        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return redirect(url_for("desk.meetings_index"))

        ext = os.path.splitext(upload.filename)[1].lower()
        if ext not in MEETING_AUDIO_EXTS:
            return render_template("desk/denied.html",
                                   message="That is not an audio file this "
                                           "can transcribe."), 400

        data = upload.read()
        if not data:
            return render_template("desk/denied.html",
                                   message="That file is empty."), 400
        if len(data) > MAX_MEETING_BYTES:
            return render_template("desk/denied.html",
                                   message="That recording is larger than the "
                                           "200 MB limit."), 400

        # An uploaded file the operator already holds is a different act from
        # recording a live conversation. This route is the former; the consent
        # box is still offered because the people on the recording did not
        # necessarily know it would be processed.
        consent = (request.form.get("consent") or "").strip() == "1"

        fname = "meeting_%d%s" % (int(time.time() * 1000), ext)
        path = save_file(fname, data,
                         upload.mimetype or mimetypes.guess_type(upload.filename)[0])

        # Retention starts at upload, not at transcription: the bytes exist
        # from now, so the clock does too. create_asset stamps the date from
        # the tenant's own policy.
        asset_id = astore.create_asset(
            None, me.get("email") or me.get("name") or "desk", path,
            file_name=upload.filename[:200],
            mime_type=upload.mimetype or "audio/mpeg",
            file_size=len(data),
            retention_days=audio_retention.retention_days(None, "source"))

        meeting = meetings.create_meeting(
            title=request.form.get("title") or upload.filename,
            created_by=me.get("name") or "",
            lead_id=request.form.get("lead_id") or None,
            held_on=request.form.get("held_on") or "",
            source="upload", consent_recorded=consent,
            audio_asset_id=asset_id)

        return redirect(url_for("desk.meeting_detail", meeting_id=meeting["id"]))

    # --- transcribe -------------------------------------------------------

    @bp.route("/meetings/<meeting_id>/transcribe", methods=["POST"])
    @require("file_upload")
    def meeting_transcribe(me, meeting_id):
        meeting = meetings.get_meeting(meeting_id)
        if meeting is None:
            abort(404)

        feature = "meeting_recording" if meeting["source"] == "record" \
            else "meeting_intelligence"

        asset = astore.get_asset(None, meeting["audio_asset_id"]) \
            if meeting["audio_asset_id"] else None
        if asset is None:
            return _fail(meeting_id, "The audio for this meeting is no longer "
                                     "stored. It may have passed its retention "
                                     "date.")

        submission = audio_jobs.submit(
            feature, me.get("email") or "desk",
            ap.TranscriptionRequest(audio_path=asset["storage_key"],
                                    diarize=True, timestamps=True),
            subject_id=meeting_id,
            input_asset_ids=[meeting["audio_asset_id"]],
            # One transcription per meeting, however many times the button is
            # pressed. Transcription is charged per minute.
            idempotency_key="meeting:%s" % meeting_id)

        if not submission.allowed:
            meetings.set_meeting_job(meeting_id, None, status="refused")
            return render_template("desk/denied.html",
                                   message=submission.decision.reason), 403

        job = submission.job
        meetings.set_meeting_job(meeting_id, None, job_id=job["id"],
                                 status=job["status"])

        if job.get("status") == "completed":
            _harvest(meeting_id, job, meeting.get("audio_asset_id"))

        return redirect(url_for("desk.meeting_detail", meeting_id=meeting_id))

    # --- detail -----------------------------------------------------------

    @bp.route("/meetings/<meeting_id>")
    @require("view")
    def meeting_detail(me, meeting_id):
        meeting = meetings.get_meeting(meeting_id)
        if meeting is None:
            abort(404)

        # A job that finished on the vendor's clock settles when somebody
        # looks at the page, so the transcript is not waiting on a cron.
        if meeting.get("job_id") and meeting.get("status") not in ("ready", "refused"):
            job = audio_jobs.poll(None, meeting["job_id"])
            if job and job.get("status") == "completed" and not meeting.get("transcript_id"):
                _harvest(meeting_id, job, meeting.get("audio_asset_id"))
                meeting = meetings.get_meeting(meeting_id)

        transcript = None
        if meeting.get("transcript_id"):
            transcript = astore.get_transcript(None, meeting["transcript_id"])

        return render_template("desk/meeting.html", **ctx(
            me, meeting=meeting, transcript=transcript,
            candidates=meetings.list_candidates(meeting_id),
            counts=meetings.counts(meeting_id),
            audio_on=_audio_on(),
            job=audio_store_job(meeting.get("job_id"))))

    # --- approve / dismiss ------------------------------------------------

    @bp.route("/meetings/candidates/<candidate_id>/decide", methods=["POST"])
    @require("note_add")
    def meeting_decide(me, candidate_id):
        candidate = meetings.get_candidate(candidate_id)
        if candidate is None:
            abort(404)
        meeting = meetings.get_meeting(candidate["meeting_id"])
        if meeting is None:
            abort(404)

        action = (request.form.get("action") or "").strip()
        back = url_for("desk.meeting_detail", meeting_id=candidate["meeting_id"])

        if action == "dismiss":
            meetings.decide_candidate(candidate_id, None, "dismissed",
                                      me.get("name") or "")
            return redirect(back)

        if action not in ("task", "note"):
            return redirect(back)

        # The provenance travels with the record. Somebody reading this task
        # in six months needs to know where the sentence came from.
        origin = "From the meeting \"%s\" (%s). Matched on: %s." % (
            meeting["title"], meeting["held_on"], candidate["matched_on"])
        # Straight quotes, not typographic ones. This string is stored and
        # then rendered in several places, and this repo has had to repair
        # mojibake before; correct curly quotes are not worth that risk.
        quote = 'Said by %s: "%s"' % (
            candidate["speaker"] or "an unidentified speaker", candidate["quote"])

        if action == "task":
            task_id = desk_store.add_task(
                me, title=candidate["text"][:160],
                description="%s\n\n%s" % (quote, origin),
                lead_id=meeting.get("lead_id") or None,
                category="Meeting")
            meetings.decide_candidate(candidate_id, None, "approved",
                                      me.get("name") or "", "task", task_id)
        else:
            note_id = None
            if meeting.get("lead_id"):
                note_id = desk_store.add_note(
                    meeting["lead_id"], me, "Meeting Note",
                    "%s\n\n%s" % (quote, origin))
            meetings.decide_candidate(candidate_id, None, "approved",
                                      me.get("name") or "", "note", note_id)

        return redirect(back)

    # --- the voice agent --------------------------------------------------

    @bp.route("/agents")
    @require("view")
    def agents_index(me):
        return render_template("desk/agents.html", **ctx(
            me, profiles=agent.list_profiles(),
            unmet=agent.unmet_human_requests(),
            sessions=agent.list_sessions(limit=25),
            agent_on=_agent_on()))

    @bp.route("/agents/new", methods=["POST"])
    @require("manage_users")
    def agent_new(me):
        """Creating an agent is an owner action. It is the one thing in the
        Desk that can speak to the public in the company's name."""
        if not _agent_on():
            return render_template("desk/denied.html",
                                   message="The voice agent is switched off "
                                           "on this deployment."), 404
        try:
            agent.create_profile(_agent_fields(), created_by=me.get("name") or "",
                                 known_person_names=_known_people())
        except agent.GuardrailRefusal as refusal:
            return render_template("desk/denied.html", message=refusal.reason), 400
        return redirect(url_for("desk.agents_index"))

    @bp.route("/agents/<profile_id>/activate", methods=["POST"])
    @require("manage_users")
    def agent_activate(me, profile_id):
        try:
            agent.activate(profile_id, known_person_names=_known_people())
        except agent.GuardrailRefusal as refusal:
            return render_template("desk/denied.html", message=refusal.reason), 400
        return redirect(url_for("desk.agents_index"))

    @bp.route("/agents/<profile_id>/suspend", methods=["POST"])
    @require("manage_users")
    def agent_suspend(me, profile_id):
        agent.suspend(profile_id)
        return redirect(url_for("desk.agents_index"))

    @bp.route("/agents/<profile_id>/delete", methods=["POST"])
    @require("delete")
    def agent_delete(me, profile_id):
        agent.delete_profile(profile_id)
        return redirect(url_for("desk.agents_index"))

    @bp.route("/agents/sessions/<session_id>")
    @require("view")
    def agent_session(me, session_id):
        session = agent.get_session(session_id)
        if session is None:
            abort(404)
        return render_template("desk/agent_session.html", **ctx(
            me, session=session,
            profile=agent.get_profile(session["profile_id"])))

    @bp.route("/agents/sessions/<session_id>/escalate", methods=["POST"])
    @require("note_add")
    def agent_escalate(me, session_id):
        """Somebody asked for a person and did not get one. This is a person
        picking it up, and it becomes a task so it cannot be forgotten."""
        session = agent.get_session(session_id)
        if session is None:
            abort(404)
        profile = agent.get_profile(session["profile_id"]) or {}
        task_id = desk_store.add_task(
            me, title="Call back: agent could not resolve a request for a person",
            description="Agent: %s\nCaller reference: %s\n\n%s"
                        % (profile.get("name") or "unknown",
                           session.get("caller_ref") or "not recorded",
                           _transcript_text(session.get("transcript"))),
            category="Follow-Up", priority="High")
        agent.record_outcome(session_id, status="escalated",
                             escalated_to=me.get("name") or "",
                             outcome="Picked up by a person")
        return redirect(url_for("desk.agent_session", session_id=session_id))

    # --- delete -----------------------------------------------------------

    @bp.route("/meetings/<meeting_id>/delete", methods=["POST"])
    @require("delete")
    def meeting_delete(me, meeting_id):
        meeting = meetings.get_meeting(meeting_id)
        if meeting is not None and meeting.get("audio_asset_id"):
            # Destroy the audio with the meeting. Leaving it on disk because
            # the row is gone is how a retention promise quietly stops being
            # true.
            asset = astore.get_asset(None, meeting["audio_asset_id"])
            if asset and asset.get("storage_key"):
                try:
                    blob_store.remove(asset["storage_key"],
                                      uploads_dir=audio_retention.uploads_dir())
                except Exception:
                    pass
                astore.mark_asset_deleted(meeting["audio_asset_id"])
        meetings.delete_meeting(meeting_id)
        return redirect(url_for("desk.meetings_index"))


# --- helpers ----------------------------------------------------------------

def audio_store_job(job_id):
    return astore.get_job(None, job_id) if job_id else None


def _fail(meeting_id, message):
    meetings.set_meeting_job(meeting_id, None, status="failed")
    return render_template("desk/denied.html", message=message), 410


def _harvest(meeting_id, job, audio_asset_id=None):
    """Store the transcript and run the extractor over it, once."""
    result = job.get("result") or {}
    if not result.get("segments"):
        adapter = ap.get(ap.TRANSCRIPTION, job.get("provider"))
        if adapter and job.get("provider_job_id"):
            try:
                result = adapter.status(job["provider_job_id"]) or {}
            except Exception:
                return

    if not result.get("segments"):
        return

    transcript_id = astore.save_transcript(
        None, audio_asset_id, job.get("provider") or "", result)

    meetings.set_meeting_job(meeting_id, None, transcript_id=transcript_id,
                             status="ready", is_mock=bool(result.get("is_mock")))

    # Only once: pressing transcribe twice must not double the review queue.
    if not meetings.list_candidates(meeting_id):
        meetings.save_candidates(
            meeting_id, meetings.extract_candidates(result.get("segments")))


def _agent_fields():
    """The form, as the guardrails expect it.

    Lists arrive one per line rather than comma-separated: a comma box turns
    "Discuss deal terms, including advances" into two rules that each say
    half of something.
    """
    def lines(field):
        raw = request.form.get(field) or ""
        return [ln.strip() for ln in raw.splitlines() if ln.strip()][:40]

    return {
        "name": request.form.get("name") or "",
        "purpose": request.form.get("purpose") or "",
        "greeting": request.form.get("greeting") or "",
        "human_contact": request.form.get("human_contact") or "",
        "persona_note": request.form.get("persona_note") or "",
        "knowledge": lines("knowledge"),
        "may_not": lines("may_not"),
        "record_calls": (request.form.get("record_calls") or "") == "1",
    }


def _known_people():
    """Names the guardrail should refuse a persona from taking.

    Everybody this instance actually knows about - the roster and the leads -
    because those are the people a voice agent here could plausibly be made
    to imitate, and they are the ones with something to lose by it.
    """
    names = set()
    try:
        for row in desk_store.list_leads():
            for key in ("artist_name", "contact_name", "manager_name"):
                value = (row.get(key) or "").strip()
                if len(value) >= 3:
                    names.add(value)
    except Exception:
        pass
    try:
        names.update(n for n in (desk_store.TEAM_NAMES or []) if len(n or "") >= 3)
    except Exception:
        pass
    return sorted(names)


def _transcript_text(transcript):
    lines = []
    for turn in transcript or []:
        lines.append("%s: %s" % ((turn.get("role") or "?").title(),
                                 turn.get("text") or ""))
    return "\n".join(lines) or "No transcript was recorded."
