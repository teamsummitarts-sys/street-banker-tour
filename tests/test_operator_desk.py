"""Operator Desk: the internal CRM stays internal, and every role can do
exactly what its label says.

The boundary under test is operator_desk.require(): anonymous visitors
never see desk markup (the app's global wall bounces them to login),
signed-in users who are not on the desk roster get one sentence and a
403, and roster members are held to their role server-side no matter
what the sidebar hides.

Files get their own attention because the app's /uploads tree is public
by design: a desk contract must never land there, and the only road to
its bytes must be the roster-checked download route.
"""
import io
import os
import uuid

import pytest

import app as appmod
import db as store
import desk_store
import operator_desk
from db import get_db

DESK = "/operator-desk"
PASSWORD = "secret-desk-1"

LEAKS = ["<built-in method", "&lt;built-in method", "[object Object]",
         "object at 0x", "&lt;function", "<function ", "dict_keys(",
         "dict_values(", "dict_items(", "<bound method", "&lt;bound method"]

DESK_PAGES = ["", "/leads", "/leads/new", "/tasks", "/follow-ups",
              "/events", "/deals", "/files", "/team", "/activity"]


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _signed_client(flask_app, email, name):
    client = flask_app.test_client()
    client.post("/signup", data={"name": name, "email": email,
                                 "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})
    return client


@pytest.fixture(scope="module")
def owner_email():
    return "desk-owner-%s@example.net" % uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def owner(flask_app, owner_email):
    """An owner client, via the real auto-provisioning path: the module's
    _is_owner_email hook says yes, so the first visit creates the desk
    Owner row."""
    original = operator_desk._is_owner_email
    operator_desk._is_owner_email = lambda email: email == owner_email
    client = _signed_client(flask_app, owner_email, "Test Owner")
    yield client
    operator_desk._is_owner_email = original


def _roster_client(flask_app, role, name):
    """Sign up an app user and put them on the desk roster with a role."""
    email = "desk-%s-%s@example.net" % (role, uuid.uuid4().hex[:8])
    desk_store.add_user(email, name, role)
    return _signed_client(flask_app, email, name)


@pytest.fixture(scope="module")
def admin(flask_app):
    return _roster_client(flask_app, "admin", "Test Admin")


@pytest.fixture(scope="module")
def member(flask_app):
    return _roster_client(flask_app, "member", "Mika")


@pytest.fixture(scope="module")
def viewer(flask_app):
    return _roster_client(flask_app, "viewer", "Test Viewer")


def _sample_lead_id():
    return desk_store.list_leads(tag="Sample")[0]["id"]


# --- the walls --------------------------------------------------------------

def test_anonymous_is_redirected_to_login(flask_app):
    client = flask_app.test_client()
    for path in (DESK, DESK + "/leads", "/admin"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"], path


def test_signed_in_non_roster_user_gets_the_exact_sentence(flask_app):
    email = "artist-%s@example.net" % uuid.uuid4().hex[:8]
    client = _signed_client(flask_app, email, "Just An Artist")
    response = client.get(DESK)
    assert response.status_code == 403
    assert operator_desk.DENIED_MESSAGE in response.get_data(as_text=True)
    # And no desk furniture around the sentence.
    assert "dk-side" not in response.get_data(as_text=True)


def test_owner_is_auto_provisioned_on_first_visit(owner, owner_email):
    assert owner.get(DESK).status_code == 200
    row = desk_store.get_user_by_email(owner_email)
    assert row is not None
    assert row["role"] == "owner"
    assert row["status"] == "active"


def test_admin_alias_redirects_into_the_desk(owner):
    response = owner.get("/admin")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(DESK + "/")


def test_desk_pages_are_not_indexed_and_leak_no_objects(owner):
    for page in DESK_PAGES:
        body = owner.get(DESK + page).get_data(as_text=True)
        assert 'name="robots" content="noindex' in body, page
        for leak in LEAKS:
            assert leak not in body, "%s leaked %r" % (page, leak)


# --- seed -------------------------------------------------------------------

def test_seed_is_five_obviously_fake_leads():
    samples = desk_store.list_leads(tag="Sample")
    assert len(samples) >= 5
    for lead in samples:
        assert "(sample)" in lead["artist_name"]
        assert "Sample" in lead["tags"]


def test_seed_created_the_three_team_names():
    names = {u["name"] for u in desk_store.list_users()}
    assert {"LJ", "Warren", "Jovan"} <= names


# --- role matrix ------------------------------------------------------------

def test_viewer_reads_everything_and_changes_nothing(viewer):
    for page in ("", "/leads", "/tasks", "/follow-ups", "/events",
                 "/deals", "/files"):
        assert viewer.get(DESK + page).status_code == 200, page
    assert viewer.get(DESK + "/team").status_code == 403
    assert viewer.get(DESK + "/activity").status_code == 403
    assert viewer.get(DESK + "/export/leads.csv").status_code == 403
    assert viewer.post(DESK + "/leads/new",
                       data={"artist_name": "Viewer Try"}).status_code == 403
    assert viewer.post(DESK + "/tasks",
                       data={"title": "Viewer Task"}).status_code == 403
    lead_id = _sample_lead_id()
    assert viewer.post(DESK + "/leads/%s/notes" % lead_id,
                       data={"body": "viewer note"}).status_code == 403


def test_member_edits_only_what_is_assigned_to_them(member):
    mine, other = desk_store.list_leads(tag="Sample")[:2]
    with get_db() as db:
        db.execute("UPDATE desk_leads SET assigned_to = 'Mika' WHERE id = ?",
                   (mine["id"],))
        db.execute("UPDATE desk_leads SET assigned_to = 'LJ' WHERE id = ?",
                   (other["id"],))
    assert member.get(DESK + "/leads/%s/edit" % mine["id"]).status_code == 200
    assert member.get(DESK + "/leads/%s/edit" % other["id"]).status_code == 403
    # Notes are open to members on any lead — collaboration, not ownership.
    response = member.post(DESK + "/leads/%s/notes" % other["id"],
                           data={"body": "Talked to @LJ about the catalog."})
    assert response.status_code == 302
    # Stage moves and new leads are not.
    assert member.post(DESK + "/leads/%s/stage" % mine["id"],
                       data={"stage": "Contacted"}).status_code == 403
    assert member.post(DESK + "/leads/new",
                       data={"artist_name": "Member Try"}).status_code == 403


def test_member_tasks_are_forced_onto_themselves(member):
    title = "Member task %s" % uuid.uuid4().hex[:6]
    member.post(DESK + "/tasks", data={"title": title,
                                       "assigned_to": "Warren"})
    task = [t for t in desk_store.list_tasks() if t["title"] == title][0]
    assert task["assigned_to"] == "Mika"
    assert task["created_by"] == "Mika"


def test_admin_runs_the_pipeline_but_not_the_org(admin):
    # Create.
    name = "Admin Lead %s" % uuid.uuid4().hex[:6]
    response = admin.post(DESK + "/leads/new", data={
        "artist_name": name, "role": "Artist", "priority": "High",
        "lead_source": "Referral"})
    assert response.status_code == 302
    lead_id = response.headers["Location"].rstrip("/").split("/")[-1]
    # Stage.
    admin.post(DESK + "/leads/%s/stage" % lead_id,
               data={"stage": "Contacted"})
    assert desk_store.get_lead(lead_id)["pipeline_stage"] == "Contacted"
    assert desk_store.get_lead(lead_id)["stage_changed_at"]
    # Deal.
    assert admin.post(DESK + "/leads/%s/deals" % lead_id,
                      data={"deal_type": "Distribution",
                            "estimated_value": "$2,000"}).status_code == 302
    assert desk_store.list_deals(lead_id=lead_id)
    # But no owner powers.
    assert admin.post(DESK + "/leads/%s/delete" % lead_id).status_code == 403
    assert admin.get(DESK + "/export/leads.csv").status_code == 403
    assert admin.get(DESK + "/team").status_code == 403
    assert admin.get(DESK + "/activity").status_code == 403


def test_owner_deletes_and_the_records_go_with_it(owner):
    response = owner.post(DESK + "/leads/new",
                          data={"artist_name": "Doomed Lead"})
    lead_id = response.headers["Location"].rstrip("/").split("/")[-1]
    owner.post(DESK + "/leads/%s/notes" % lead_id, data={"body": "gone soon"})
    assert owner.post(DESK + "/leads/%s/delete" % lead_id).status_code == 302
    assert desk_store.get_lead(lead_id) is None
    assert desk_store.list_notes(lead_id) == []


def test_owner_export_is_csv_with_the_leads_in_it(owner):
    response = owner.get(DESK + "/export/leads.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["Content-Type"]
    assert "artist_name" in response.get_data(as_text=True)
    assert "(sample)" in response.get_data(as_text=True)


def test_adding_the_same_email_twice_updates_instead_of_crashing(owner):
    """The bug as reported: 'the admin emails i add to desk dont allow
    them access'. One real failure behind it - re-adding an email hit
    the UNIQUE constraint and answered 500."""
    email = "twice-%s@example.net" % uuid.uuid4().hex[:8]
    assert owner.post(DESK + "/team", data={
        "action": "add", "name": "Twice Added", "email": email,
        "role": "admin"}).status_code == 302
    assert desk_store.get_user_by_email(email)["role"] == "admin"
    # The second add is an update, not a crash.
    assert owner.post(DESK + "/team", data={
        "action": "add", "name": "Twice Added", "email": email,
        "role": "viewer"}).status_code == 302
    assert desk_store.get_user_by_email(email)["role"] == "viewer"


def test_team_page_says_whether_the_sign_in_account_exists(flask_app, owner):
    """Authorizing an email is half the door; the app login is the other
    half. The roster now says which half is missing."""
    email = "unlinked-%s@example.net" % uuid.uuid4().hex[:8]
    owner.post(DESK + "/team", data={"action": "add", "name": "Un Linked",
                                     "email": email, "role": "admin"})
    body = owner.get(DESK + "/team").get_data(as_text=True)
    assert "no account yet" in body
    # The moment they sign up with that address, the page says so.
    _signed_client(flask_app, email, "Un Linked")
    body = owner.get(DESK + "/team").get_data(as_text=True)
    row = body[body.find(email):body.find(email) + 1200]
    assert "account linked" in row


def test_owner_attaches_a_sign_in_email_to_a_seeded_name(owner):
    lj = [u for u in desk_store.list_users() if u["name"] == "LJ"][0]
    email = "lj-%s@example.net" % uuid.uuid4().hex[:8]
    owner.post(DESK + "/team", data={"action": "email", "user_id": lj["id"],
                                     "email": email})
    assert desk_store.get_user_by_email(email)["id"] == lj["id"]
    # An email held by another row cannot be moved onto this one.
    warren = [u for u in desk_store.list_users() if u["name"] == "Warren"][0]
    owner.post(DESK + "/team", data={"action": "email",
                                     "user_id": warren["id"], "email": email})
    assert desk_store.get_user_by_email(email)["id"] == lj["id"]


def test_added_admin_can_actually_get_in_after_signing_up(flask_app, owner):
    """The whole reported flow, end to end: owner adds the email, the
    person creates their Street Banker account with it afterwards, and
    the Desk opens."""
    email = "late-signup-%s@example.net" % uuid.uuid4().hex[:8]
    owner.post(DESK + "/team", data={"action": "add", "name": "Late Signup",
                                     "email": email, "role": "admin"})
    late = _signed_client(flask_app, email, "Late Signup")
    assert late.get(DESK).status_code == 200


def test_team_page_adds_people_and_protects_the_owner_from_themselves(
        owner, owner_email):
    name = "Added %s" % uuid.uuid4().hex[:6]
    owner.post(DESK + "/team", data={"action": "add", "name": name,
                                     "role": "viewer"})
    added = [u for u in desk_store.list_users() if u["name"] == name]
    assert added and added[0]["role"] == "viewer"
    # Self-demotion is refused server-side.
    me = desk_store.get_user_by_email(owner_email)
    owner.post(DESK + "/team", data={"action": "role", "user_id": me["id"],
                                     "role": "viewer"})
    assert desk_store.get_user_by_email(owner_email)["role"] == "owner"
    owner.post(DESK + "/team", data={"action": "remove", "user_id": me["id"]})
    assert desk_store.get_user_by_email(owner_email) is not None


# --- notes, tasks, warnings -------------------------------------------------

def test_note_mentions_are_parsed_and_pinning_toggles(owner):
    lead_id = _sample_lead_id()
    body = "Spoke with @LJ and @warren — send terms next week %s" % (
        uuid.uuid4().hex[:6])
    owner.post(DESK + "/leads/%s/notes" % lead_id,
               data={"body": body, "note_type": "Call Note",
                     "next_step": "Send terms"})
    note = [n for n in desk_store.list_notes(lead_id)
            if n["body"] == body][0]
    assert note["tagged_users"] == ["LJ", "Warren"]
    assert note["is_internal"] == 1
    assert note["is_pinned"] == 0
    owner.post(DESK + "/notes/%s/pin" % note["id"])
    refreshed = [n for n in desk_store.list_notes(lead_id)
                 if n["id"] == note["id"]][0]
    assert refreshed["is_pinned"] == 1


def test_completing_a_task_lands_in_the_activity_log(owner):
    title = "Audit me %s" % uuid.uuid4().hex[:6]
    owner.post(DESK + "/tasks", data={"title": title})
    task = [t for t in desk_store.list_tasks() if t["title"] == title][0]
    owner.post(DESK + "/tasks/%s/status" % task["id"],
               data={"status": "Complete"})
    actions = [(a["action"], a["metadata"].get("title"))
               for a in desk_store.list_activity()]
    assert ("task_completed", title) in actions


def test_high_priority_lead_with_no_follow_up_is_flagged():
    flagged = {lead["id"] for lead, reason in desk_store.warnings()
               if "no next follow-up" in reason}
    expected = {l["id"] for l in desk_store.list_leads(quick="high")
                if not l["follow_up_date"]}
    assert expected and expected <= flagged


def test_follow_up_form_sets_date_and_shows_on_the_board(owner):
    lead_id = _sample_lead_id()
    owner.post(DESK + "/leads/%s/follow-up" % lead_id,
               data={"follow_up_date": "2020-01-01",
                     "follow_up_owner": "LJ",
                     "follow_up_reason": "Past-due test date"})
    due_ids = {l["id"] for l in desk_store.todays_follow_ups()}
    assert lead_id in due_ids
    body = owner.get(DESK + "/follow-ups").get_data(as_text=True)
    assert "Past-due test date" in body


# --- files stay private -----------------------------------------------------

def test_desk_files_never_touch_the_public_uploads_tree(owner):
    payload = b"confidential terms"
    response = owner.post(
        DESK + "/files/upload",
        data={"file": (io.BytesIO(payload), "terms.txt"),
              "category": "Contract", "back": DESK + "/files"},
        content_type="multipart/form-data")
    assert response.status_code == 302
    record = [f for f in desk_store.list_files()
              if f["file_name"] == "terms.txt"][0]
    assert record["file_path"].startswith(operator_desk.DESK_PREFIX)
    stored_name = record["file_path"][len(operator_desk.DESK_PREFIX):]
    # On disk in desk_uploads, absent from the public uploads directory.
    desk_dir = os.path.join(os.path.dirname(store.db_path()), "desk_uploads")
    public_dir = os.path.join(os.path.dirname(store.db_path()), "uploads")
    assert os.path.exists(os.path.join(desk_dir, stored_name))
    assert not os.path.exists(os.path.join(public_dir, stored_name))
    # The public route will not serve it either.
    assert owner.get("/uploads/" + stored_name).status_code == 404
    # The gated route serves it to the roster...
    download = owner.get(DESK + "/files/%s/download" % record["id"])
    assert download.status_code == 200
    assert download.data == payload
    # ...and nobody else.
    anonymous = appmod.create_app().test_client()
    assert anonymous.get(
        DESK + "/files/%s/download" % record["id"]).status_code == 302


def test_unaccepted_file_types_are_refused(owner):
    response = owner.post(
        DESK + "/files/upload",
        data={"file": (io.BytesIO(b"MZ"), "evil.exe"),
              "category": "Other"},
        content_type="multipart/form-data")
    assert response.status_code == 400


def test_viewer_cannot_upload_but_can_download(viewer):
    response = viewer.post(
        DESK + "/files/upload",
        data={"file": (io.BytesIO(b"x"), "viewer.txt"), "category": "Other"},
        content_type="multipart/form-data")
    assert response.status_code == 403
    record = [f for f in desk_store.list_files()
              if f["file_name"] == "terms.txt"][0]
    assert viewer.get(
        DESK + "/files/%s/download" % record["id"]).status_code == 200
