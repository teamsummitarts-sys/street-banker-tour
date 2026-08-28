"""Street Banker Operator Desk — the internal workspace.

Leads, notes, tasks, follow-ups, shows and meetings, deals, files, team
and an activity log, for the people running Street Banker. Nothing here
is public and nothing here is for artist accounts: the whole blueprint
sits behind the app's login wall AND its own roster check.

Authorization model, in one place:

  Who gets in: a signed-in user whose email is on the desk roster
  (desk_users) with status active. App owners (_is_owner_email) are
  auto-provisioned as desk Owners on first visit, so the Desk can never
  lock everybody out. Anyone else signed in sees one sentence - "You do
  not have access to the Street Banker Operator Desk." - and a 403.
  Anonymous visitors are redirected to login by the app's global wall.

  What they can do once in, by role:

    owner   everything: manage users, delete records, export, audit log
    admin   add/edit leads, notes, tasks, stages, uploads, view all
    member  add notes, update leads assigned to them, create tasks,
            upload files, view
    viewer  read-only

  Every write route names the permission it needs; the decorator checks
  it server-side before the handler runs. Templates hide what a role
  cannot do, but the enforcement is here, not in the markup.

Files: desk uploads never touch the public /uploads tree. On disk they
live in a desk_uploads directory next to the database; with R2
configured they go to the bucket under a desk/ prefix. Either way the
only road to the bytes is /operator-desk/files/<id>/download, which runs
the same roster check as every other route.
"""
import mimetypes
import os

from flask import (Blueprint, Response, abort, redirect, render_template,
                   request, session, url_for)

import blob_store
import db as store
import desk_store

bp = Blueprint("desk", __name__, url_prefix="/operator-desk")

_is_owner_email = lambda email: False   # replaced by init()

DENIED_MESSAGE = "You do not have access to the Street Banker Operator Desk."

# Permission -> roles that hold it. The single source the decorator and
# the templates both read.
PERMS = {
    "view":         {"owner", "admin", "member", "viewer"},
    "lead_add":     {"owner", "admin"},
    "lead_edit":    {"owner", "admin"},          # members: assigned only
    "lead_edit_assigned": {"owner", "admin", "member"},
    "note_add":     {"owner", "admin", "member"},
    "task_add":     {"owner", "admin", "member"},
    "task_assign":  {"owner", "admin"},
    "stage_move":   {"owner", "admin"},
    "file_upload":  {"owner", "admin", "member"},
    "event_add":    {"owner", "admin", "member"},
    "deal_edit":    {"owner", "admin"},
    "delete":       {"owner"},
    "export":       {"owner"},
    "audit":        {"owner"},
    "manage_users": {"owner"},
}


def can(desk_user, permission):
    return bool(desk_user) and desk_user["role"] in PERMS.get(permission, ())


def _desk_user():
    """(app_user, desk_user) for this request; desk_user None means the
    login exists but is not on the roster."""
    user_id = session.get("user_id")
    app_user = store.get_user(user_id) if user_id else None
    if app_user is None:
        return None, None
    desk_user = desk_store.get_user_by_email(app_user.get("email"))
    if desk_user is None and _is_owner_email(app_user.get("email")):
        desk_user = desk_store.ensure_owner(app_user["email"],
                                            app_user.get("name") or "Owner")
    if desk_user is not None and desk_user.get("status") != "active":
        desk_user = None
    return app_user, desk_user


def require(permission="view"):
    """Server-side check before every handler. The decorator, not the
    template, is the boundary."""
    def wrap(fn):
        def guarded(*args, **kwargs):
            app_user, desk_user = _desk_user()
            if app_user is None:
                return redirect(url_for("login", next=request.path))
            if desk_user is None:
                return render_template("desk/denied.html",
                                       message=DENIED_MESSAGE), 403
            if not can(desk_user, permission):
                return render_template("desk/denied.html",
                                       message="Your role does not allow "
                                               "that action."), 403
            desk_store.touch_login(desk_user["id"])
            return fn(desk_user, *args, **kwargs)
        guarded.__name__ = fn.__name__
        return guarded
    return wrap


def _ctx(desk_user, **extra):
    base = {
        "me": desk_user,
        "can": lambda perm: can(desk_user, perm),
        "vocab": {
            "stages": desk_store.PIPELINE_STAGES,
            "priorities": desk_store.PRIORITIES,
            "sources": desk_store.LEAD_SOURCES,
            "contact_roles": desk_store.CONTACT_ROLES,
            "opportunities": desk_store.OPPORTUNITY_TYPES,
            "note_types": desk_store.NOTE_TYPES,
            "task_statuses": desk_store.TASK_STATUSES,
            "task_categories": desk_store.TASK_CATEGORIES,
            "event_types": desk_store.EVENT_TYPES,
            "deal_types": desk_store.DEAL_TYPES,
            "deal_statuses": desk_store.DEAL_STATUSES,
            "file_categories": desk_store.FILE_CATEGORIES,
            "tags": desk_store.SUGGESTED_TAGS,
            "team": desk_store.TEAM_NAMES,
            "roles": desk_store.ROLES,
            "role_labels": desk_store.ROLE_LABELS,
            "lead_fields": desk_store.LEAD_TEXT_FIELDS,
        },
        "legal_note": desk_store.LEGAL_NOTE,
    }
    base.update(extra)
    return base


def _member_can_touch(desk_user, lead):
    """A member may edit only what is assigned to them."""
    if desk_user["role"] in ("owner", "admin"):
        return True
    return (lead or {}).get("assigned_to") == desk_user["name"]


# --- files on disk ----------------------------------------------------------

def _desk_dir():
    path = os.path.join(os.path.dirname(store.db_path()), "desk_uploads")
    os.makedirs(path, exist_ok=True)
    return path


DESK_PREFIX = "desk:"
ALLOWED_FILE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".csv",
                     ".xlsx", ".xls", ".doc", ".docx", ".txt", ".zip",
                     ".wav", ".mp3", ".key", ".ppt", ".pptx"}


def _save_desk_file(fname, data, content_type):
    """Bucket under desk/ when configured, desk_uploads dir otherwise.
    Never the public uploads tree."""
    if blob_store.configured():
        try:
            if blob_store.put("desk/" + fname, data, content_type):
                return blob_store.PREFIX + "desk/" + fname
        except Exception:
            pass    # fall through to disk; the upload must not be lost
    with open(os.path.join(_desk_dir(), fname), "wb") as fh:
        fh.write(data)
    return DESK_PREFIX + fname


# --- dashboard --------------------------------------------------------------

@bp.route("")
@bp.route("/")
@require("view")
def dashboard(me):
    return render_template("desk/dashboard.html", **_ctx(
        me,
        counts=desk_store.dashboard_counts(),
        follow_ups=desk_store.todays_follow_ups(),
        recent=desk_store.recently_updated(),
        warnings=desk_store.warnings(),
        my_tasks=desk_store.list_tasks(view="my", my_name=me["name"])[:8],
    ))


# --- leads ------------------------------------------------------------------

@bp.route("/leads")
@require("view")
def leads(me):
    filters = {key: request.args.get(key, "")
               for key in ("q", "stage", "priority", "assigned", "source",
                           "opportunity", "tag", "quick")}
    rows = desk_store.list_leads(
        search=filters["q"], stage=filters["stage"],
        priority=filters["priority"], assigned=filters["assigned"],
        source=filters["source"], opportunity=filters["opportunity"],
        tag=filters["tag"], quick=filters["quick"], my_name=me["name"])
    return render_template("desk/leads.html",
                           **_ctx(me, leads=rows, filters=filters))


@bp.route("/leads/new", methods=["GET", "POST"])
@require("lead_add")
def lead_new(me):
    if request.method == "POST":
        lead_id = desk_store.create_lead(
            request.form, request.form.getlist("opportunity_types"),
            request.form.getlist("tags"), me)
        return redirect(url_for("desk.lead", lead_id=lead_id))
    return render_template("desk/lead_form.html",
                           **_ctx(me, lead=None))


@bp.route("/leads/<lead_id>")
@require("view")
def lead(me, lead_id):
    row = desk_store.get_lead(lead_id)
    if row is None:
        abort(404)
    lead_warnings = [w for l, w in desk_store.warnings()
                     if l["id"] == lead_id]
    # If Signal produced this lead, link back to the intelligence and show
    # what it believed at the moment of the hand-off. Imported lazily and
    # defensively: the Desk predates Signal and must not depend on it.
    signal_link = None
    try:
        import signal_store as _sig
        signal_link = _sig.desk_link_by_lead(lead_id)
    except Exception:
        signal_link = None
    return render_template("desk/lead.html", **_ctx(
        me, lead=row, signal_link=signal_link,
        notes=desk_store.list_notes(lead_id),
        tasks=desk_store.list_tasks(lead_id=lead_id),
        deals=desk_store.list_deals(lead_id=lead_id),
        files=desk_store.list_files(lead_id=lead_id),
        events=desk_store.list_events(lead_id=lead_id),
        lead_warnings=lead_warnings,
        editable=_member_can_touch(me, row),
    ))


@bp.route("/leads/<lead_id>/edit", methods=["GET", "POST"])
@require("lead_edit_assigned")
def lead_edit(me, lead_id):
    row = desk_store.get_lead(lead_id)
    if row is None:
        abort(404)
    if not _member_can_touch(me, row):
        return render_template("desk/denied.html",
                               message="Members can edit only leads "
                                       "assigned to them."), 403
    if request.method == "POST":
        desk_store.update_lead(
            lead_id, request.form, request.form.getlist("opportunity_types"),
            request.form.getlist("tags"), me)
        return redirect(url_for("desk.lead", lead_id=lead_id))
    return render_template("desk/lead_form.html", **_ctx(me, lead=row))


@bp.route("/leads/<lead_id>/stage", methods=["POST"])
@require("stage_move")
def lead_stage(me, lead_id):
    desk_store.set_stage(lead_id, request.form.get("stage") or "", me)
    return redirect(url_for("desk.lead", lead_id=lead_id))


@bp.route("/leads/<lead_id>/follow-up", methods=["POST"])
@require("lead_edit_assigned")
def lead_follow_up(me, lead_id):
    row = desk_store.get_lead(lead_id)
    if row is None:
        abort(404)
    if not _member_can_touch(me, row):
        return render_template("desk/denied.html",
                               message="Members can edit only leads "
                                       "assigned to them."), 403
    desk_store.set_follow_up(
        lead_id, request.form.get("follow_up_date"),
        request.form.get("follow_up_owner"),
        request.form.get("follow_up_reason"),
        request.form.get("follow_up_status"), me)
    return redirect(url_for("desk.lead", lead_id=lead_id))


@bp.route("/leads/<lead_id>/delete", methods=["POST"])
@require("delete")
def lead_delete(me, lead_id):
    desk_store.delete_lead(lead_id, me)
    return redirect(url_for("desk.leads"))


# --- notes ------------------------------------------------------------------

@bp.route("/leads/<lead_id>/notes", methods=["POST"])
@require("note_add")
def note_add(me, lead_id):
    body = (request.form.get("body") or "").strip()
    if body:
        desk_store.add_note(
            lead_id, me, request.form.get("note_type") or "General Note",
            body, next_step=request.form.get("next_step"),
            follow_up_date=request.form.get("follow_up_date"),
            is_pinned=bool(request.form.get("is_pinned")))
    return redirect(url_for("desk.lead", lead_id=lead_id) + "#notes")


@bp.route("/notes/<note_id>/pin", methods=["POST"])
@require("note_add")
def note_pin(me, note_id):
    desk_store.toggle_pin(note_id, me)
    return redirect(request.form.get("back")
                    or url_for("desk.dashboard"))


# --- tasks ------------------------------------------------------------------

@bp.route("/tasks", methods=["GET", "POST"])
@require("view")
def tasks(me):
    if request.method == "POST":
        if not can(me, "task_add"):
            return render_template("desk/denied.html",
                                   message="Your role does not allow "
                                           "that action."), 403
        title = (request.form.get("title") or "").strip()
        if title:
            assigned = request.form.get("assigned_to") or me["name"]
            if not can(me, "task_assign"):
                assigned = me["name"]     # members assign to themselves
            desk_store.add_task(
                me, title, description=request.form.get("description"),
                lead_id=request.form.get("lead_id") or None,
                assigned_to=assigned,
                due_date=request.form.get("due_date"),
                priority=request.form.get("priority") or "Medium",
                category=request.form.get("category") or "Other")
        return redirect(url_for("desk.tasks", view=request.args.get("view")))
    view = request.args.get("view") or "team"
    return render_template("desk/tasks.html", **_ctx(
        me, view=view,
        tasks=desk_store.list_tasks(view=view, my_name=me["name"]),
        leads=desk_store.list_leads()))


@bp.route("/tasks/<task_id>/status", methods=["POST"])
@require("task_add")
def task_status(me, task_id):
    desk_store.set_task_status(task_id, request.form.get("status") or "", me)
    return redirect(request.form.get("back") or url_for("desk.tasks"))


# --- follow-ups -------------------------------------------------------------

@bp.route("/follow-ups")
@require("view")
def follow_ups(me):
    return render_template("desk/followups.html", **_ctx(
        me, due=desk_store.todays_follow_ups(),
        warnings=desk_store.warnings()))


# --- shows & meetings -------------------------------------------------------

@bp.route("/events", methods=["GET", "POST"])
@require("view")
def events(me):
    if request.method == "POST":
        if not can(me, "event_add"):
            return render_template("desk/denied.html",
                                   message="Your role does not allow "
                                           "that action."), 403
        name = (request.form.get("event_name") or "").strip()
        if name:
            attendees = [a.strip() for a in
                         (request.form.get("attendees") or "").split(",")
                         if a.strip()]
            desk_store.add_event(
                me, name, request.form.get("event_type") or "Other",
                date=request.form.get("date"), time=request.form.get("time"),
                venue=request.form.get("venue"),
                city=request.form.get("city"), attendees=attendees,
                notes=request.form.get("notes"),
                follow_up_needed=bool(request.form.get("follow_up_needed")),
                assigned_to=request.form.get("assigned_to"),
                lead_id=request.form.get("lead_id") or None)
        return redirect(url_for("desk.events"))
    return render_template("desk/events.html", **_ctx(
        me, events=desk_store.list_events(),
        leads=desk_store.list_leads()))


# --- deal desk --------------------------------------------------------------

@bp.route("/deals")
@require("view")
def deals(me):
    return render_template("desk/deals.html", **_ctx(
        me, deals=desk_store.list_deals(), leads=desk_store.list_leads()))


@bp.route("/leads/<lead_id>/deals", methods=["POST"])
@require("deal_edit")
def deal_add(me, lead_id):
    if desk_store.get_lead(lead_id) is None:
        abort(404)
    desk_store.add_deal(
        me, lead_id, request.form.get("deal_type") or "Other",
        estimated_value=request.form.get("estimated_value"),
        advance_discussed=request.form.get("advance_discussed"),
        distribution_fee=request.form.get("distribution_fee"),
        term=request.form.get("term"),
        recoupment_notes=request.form.get("recoupment_notes"),
        publishing_involved=request.form.get("publishing_involved"),
        content_id_involved=request.form.get("content_id_involved"),
        counsel_involved=request.form.get("counsel_involved"),
        status=request.form.get("status"),
        notes=request.form.get("notes"))
    return redirect(url_for("desk.lead", lead_id=lead_id) + "#deals")


@bp.route("/deals/<deal_id>/status", methods=["POST"])
@require("deal_edit")
def deal_status(me, deal_id):
    desk_store.set_deal_status(deal_id, request.form.get("status") or "", me)
    return redirect(request.form.get("back") or url_for("desk.deals"))


# --- files ------------------------------------------------------------------

@bp.route("/files")
@require("view")
def files(me):
    return render_template("desk/files.html", **_ctx(
        me, files=desk_store.list_files(), leads=desk_store.list_leads()))


@bp.route("/leads/<lead_id>/files", methods=["POST"])
@bp.route("/files/upload", methods=["POST"], defaults={"lead_id": None})
@require("file_upload")
def file_upload(me, lead_id):
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return redirect(request.form.get("back") or url_for("desk.files"))
    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in ALLOWED_FILE_EXTS:
        return render_template("desk/denied.html",
                               message="That file type is not accepted "
                                       "here."), 400
    import time as _time
    fname = "desk_%d%s" % (int(_time.time() * 1000), ext)
    path = _save_desk_file(fname, upload.read(),
                           upload.mimetype
                           or mimetypes.guess_type(upload.filename)[0])
    desk_store.add_file(me, upload.filename, path, ext.lstrip("."),
                        request.form.get("category") or "Other",
                        lead_id=lead_id or request.form.get("lead_id")
                        or None)
    return redirect(request.form.get("back")
                    or (url_for("desk.lead", lead_id=lead_id) + "#files"
                        if lead_id else url_for("desk.files")))


@bp.route("/files/<file_id>/download")
@require("view")
def file_download(me, file_id):
    record = desk_store.get_file(file_id)
    if record is None:
        abort(404)
    path = record["file_path"]
    if blob_store.is_remote(path):
        url = blob_store.url_for(path, ttl=300)
        if url == path:
            abort(503)      # bucket object, credentials rotated away
        return redirect(url)
    if path.startswith(DESK_PREFIX):
        from flask import send_from_directory
        return send_from_directory(
            _desk_dir(), path[len(DESK_PREFIX):], as_attachment=True,
            download_name=record["file_name"])
    abort(404)


# --- team & audit (owner) ---------------------------------------------------

@bp.route("/team", methods=["GET", "POST"])
@require("manage_users")
def team(me):
    if request.method == "POST":
        action = request.form.get("action")
        target = request.form.get("user_id")
        if action == "add":
            name = (request.form.get("name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            role = request.form.get("role") or "member"
            if name:
                # Adding an email that is already on the roster updates
                # that row instead of crashing into the UNIQUE constraint:
                # the owner's intent - "this address, this role" - is the
                # same either way.
                existing = (desk_store.get_user_by_email(email)
                            if email else None)
                if existing:
                    desk_store.set_user_role(existing["id"], role)
                    desk_store.set_user_status(existing["id"], "active")
                    desk_store.log_activity(me, "user_role_changed", "user",
                                            existing["id"], {"role": role})
                else:
                    desk_store.add_user(email, name, role)
                    desk_store.log_activity(me, "user_added", "user", None,
                                            {"name": name})
        elif action == "role" and target and target != me["id"]:
            desk_store.set_user_role(target, request.form.get("role") or "")
            desk_store.log_activity(me, "user_role_changed", "user", target,
                                    {"role": request.form.get("role")})
        elif action == "email" and target and target != me["id"]:
            email = (request.form.get("email") or "").strip().lower()
            # Refuse to move an email that belongs to a different row.
            holder = desk_store.get_user_by_email(email) if email else None
            if holder is None or holder["id"] == target:
                desk_store.set_user_email(target, email)
                desk_store.log_activity(me, "user_email_set", "user", target,
                                        {"email": email})
        elif action == "status" and target and target != me["id"]:
            desk_store.set_user_status(target,
                                       request.form.get("status") or "")
        elif action == "remove" and target and target != me["id"]:
            desk_store.remove_user(target)
            desk_store.log_activity(me, "user_removed", "user", target, {})
        return redirect(url_for("desk.team"))
    users = desk_store.list_users()
    # Authorization is only half the door: the person also needs a
    # Street Banker login with that exact address. Saying which half is
    # missing is the difference between a fix and a mystery.
    linked = {}
    for row in users:
        linked[row["id"]] = (bool(store.get_user_by_email(row["email"]))
                             if row["email"] else False)
    return render_template("desk/team.html",
                           **_ctx(me, users=users, linked=linked))


@bp.route("/activity")
@require("audit")
def activity(me):
    return render_template("desk/activity.html",
                           **_ctx(me, entries=desk_store.list_activity()))


@bp.route("/export/leads.csv")
@require("export")
def export_leads(me):
    import csv
    import io
    buffer = io.StringIO()
    columns = ["id", "artist_name", "contact_name", "role", "email", "phone",
               "city", "state", "country", "genre", "current_distributor",
               "pipeline_stage", "priority", "lead_source", "assigned_to",
               "follow_up_date", "created_at", "updated_at"]
    writer = csv.writer(buffer)
    writer.writerow(columns + ["opportunity_types", "tags"])
    for row in desk_store.list_leads():
        writer.writerow([row.get(c) or "" for c in columns]
                        + ["; ".join(row["opportunity_types"]),
                           "; ".join(row["tags"])])
    desk_store.log_activity(me, "leads_exported", "lead", None,
                            {"count": len(desk_store.list_leads())})
    return Response(buffer.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=operator-desk-leads.csv"})


# --- wiring -----------------------------------------------------------------

def init(app, is_owner_email):
    """Register the Desk on the app. Called once from create_app."""
    global _is_owner_email
    _is_owner_email = is_owner_email
    desk_store.init_desk()
    desk_store.seed_if_empty()

    # Meeting Intelligence lives in its own module but on THIS blueprint, so
    # it inherits the roster guard, the denied page and the URL prefix rather
    # than growing a second permission system beside the first. Its routes
    # must exist before the blueprint is registered.
    import audio_agent
    import audio_desk
    import audio_meetings
    audio_meetings.init_meetings()
    audio_agent.init_agents()
    audio_desk.register(bp, require, _ctx, _save_desk_file, DESK_PREFIX)

    app.register_blueprint(bp)

    @app.route("/admin")
    def admin_alias():
        return redirect(url_for("desk.dashboard"))
