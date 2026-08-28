"""Partner OS phase 1: the tenant seam.

These tests do not read source. They create real partners and real accounts
through the real app and ask what each one is actually served, because the
two isolation bugs this repo has shipped were both invisible to every
source-level test in the suite.
"""
import os
import uuid

import pytest

import app as appmod
import db as store
import partner_store as pstore


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _account(app, label):
    c = app.test_client()
    email = "po-%s-%s@example.net" % (label, uuid.uuid4().hex[:8])
    c.post("/signup", data={"name": label.title(), "email": email, "password": "po-pass-123"})
    c.post("/login", data={"email": email, "password": "po-pass-123"})
    with app.app_context():
        return c, store.get_user_by_email(email)


def _partner(app, name, **kw):
    with app.app_context():
        pid = pstore.create_partner(name, **kw)
        assert pid, "slug or domain collision in a test fixture"
        return pstore.get_partner(pid)


# --- the seam ---------------------------------------------------------------

def test_an_account_belongs_to_at_most_one_partner(flask_app):
    a = _partner(flask_app, "Alpha Records %s" % uuid.uuid4().hex[:6])
    b = _partner(flask_app, "Bravo Music %s" % uuid.uuid4().hex[:6])
    _, artist = _account(flask_app, "artist")
    with flask_app.app_context():
        assert pstore.attach_user(a["id"], artist["id"]) is True
        # A transfer is a deliberate two-step, never a side effect.
        assert pstore.attach_user(b["id"], artist["id"]) is False
        assert [r["id"] for r in pstore.roster(a["id"])] == [artist["id"]]
        assert pstore.roster(b["id"]) == []
        assert pstore.detach_user(a["id"], artist["id"]) is True
        assert pstore.attach_user(b["id"], artist["id"]) is True


def test_a_partner_never_sees_another_partners_roster(flask_app):
    a = _partner(flask_app, "Alpha Two %s" % uuid.uuid4().hex[:6])
    b = _partner(flask_app, "Bravo Two %s" % uuid.uuid4().hex[:6])
    _, mine = _account(flask_app, "mine")
    _, theirs = _account(flask_app, "theirs")
    with flask_app.app_context():
        pstore.attach_user(a["id"], mine["id"])
        pstore.attach_user(b["id"], theirs["id"])
        ids_a = [r["id"] for r in pstore.roster(a["id"])]
        ids_b = [r["id"] for r in pstore.roster(b["id"])]
    assert mine["id"] in ids_a and theirs["id"] not in ids_a
    assert theirs["id"] in ids_b and mine["id"] not in ids_b


def test_owns_user_is_the_gate_and_it_asks_the_database(flask_app):
    """Every act-on-behalf passes this. An id arriving in a URL the partner
    was allowed to load proves nothing about who owns it."""
    a = _partner(flask_app, "Alpha Three %s" % uuid.uuid4().hex[:6])
    b = _partner(flask_app, "Bravo Three %s" % uuid.uuid4().hex[:6])
    _, artist = _account(flask_app, "owned")
    with flask_app.app_context():
        pstore.attach_user(a["id"], artist["id"])
        assert pstore.owns_user(a["id"], artist["id"]) is True
        assert pstore.owns_user(b["id"], artist["id"]) is False
        assert pstore.owns_user(a["id"], None) is False
        assert pstore.owns_user(None, artist["id"]) is False


def test_the_roster_never_hands_back_a_password_hash(flask_app):
    a = _partner(flask_app, "Alpha Four %s" % uuid.uuid4().hex[:6])
    _, artist = _account(flask_app, "hashcheck")
    with flask_app.app_context():
        pstore.attach_user(a["id"], artist["id"])
        rows = pstore.roster(a["id"])
    assert rows and "password_hash" not in rows[0]


# --- permissions ------------------------------------------------------------

def test_permissions_fail_closed(flask_app):
    assert pstore.can(None, "view") is False
    assert pstore.can({"role": "owner"}, "no_such_permission") is False
    assert pstore.can({"role": "no_such_role"}, "view") is False
    assert pstore.can({"role": "viewer"}, "view") is True
    assert pstore.can({"role": "viewer"}, "manage_members") is False
    assert pstore.can({"role": "owner"}, "manage_members") is True
    # acting inside somebody else's workspace is deliberately narrow
    assert pstore.can({"role": "manager"}, "act_as_artist") is False
    assert pstore.can({"role": "support"}, "act_as_artist") is True


def test_every_permission_names_a_real_role(flask_app):
    for perm, roles in pstore.PERMS.items():
        unknown = roles - set(pstore.ROLES)
        assert not unknown, "%s grants unknown roles %s" % (perm, unknown)


def test_a_seat_at_a_suspended_partner_is_no_seat(flask_app):
    p = _partner(flask_app, "Suspended %s" % uuid.uuid4().hex[:6])
    _, staff = _account(flask_app, "staff")
    with flask_app.app_context():
        pstore.add_member(p["id"], staff["email"], "Staff", "owner", user_id=staff["id"])
        assert pstore.member_for_user(staff["id"]) is not None
        assert pstore.set_partner_status(p["id"], "suspended") is True
        assert pstore.member_for_user(staff["id"]) is None, (
            "a suspended partner must grant nothing")


def test_a_seat_invited_by_email_binds_to_the_account_at_first_sight(flask_app):
    """Signal's members orphan when somebody changes their email, because
    the account id column is never read. Here it is the key."""
    p = _partner(flask_app, "Claim %s" % uuid.uuid4().hex[:6])
    email = "claim-%s@example.net" % uuid.uuid4().hex[:8]
    with flask_app.app_context():
        mid = pstore.add_member(p["id"], email, "Invited", "manager")
        assert mid
        seat = pstore.get_member(p["id"], email=email)
        assert seat and seat["user_id"] is None
    c = flask_app.test_client()
    c.post("/signup", data={"name": "Invited", "email": email, "password": "po-pass-123"})
    with flask_app.app_context():
        user = store.get_user_by_email(email)
        assert pstore.claim_seats(user["id"], email) == 1
        bound = pstore.get_member(p["id"], user_id=user["id"])
        assert bound and bound["user_id"] == user["id"]


def test_removing_a_member_stops_the_seat_working(flask_app):
    p = _partner(flask_app, "Remove %s" % uuid.uuid4().hex[:6])
    _, staff = _account(flask_app, "removable")
    with flask_app.app_context():
        mid = pstore.add_member(p["id"], staff["email"], "Staff", "admin", user_id=staff["id"])
        assert pstore.get_member(p["id"], user_id=staff["id"]) is not None
        assert pstore.remove_member(p["id"], mid) is True
        assert pstore.get_member(p["id"], user_id=staff["id"]) is None


# --- the guard --------------------------------------------------------------

def test_partner_routes_are_a_404_to_someone_with_no_seat(flask_app):
    """Not a 403. A stranger must not be able to learn a tenant exists from
    the shape of the refusal."""
    _partner(flask_app, "Guarded %s" % uuid.uuid4().hex[:6])
    outsider, _ = _account(flask_app, "outsider")
    assert outsider.get("/partner/").status_code == 404
    assert outsider.get("/partner/roster").status_code == 404


def test_a_seated_member_reaches_the_partner_home(flask_app):
    p = _partner(flask_app, "Reachable %s" % uuid.uuid4().hex[:6])
    client, staff = _account(flask_app, "seated")
    _, artist = _account(flask_app, "rostered")
    with flask_app.app_context():
        pstore.add_member(p["id"], staff["email"], "Seated", "owner", user_id=staff["id"])
        pstore.attach_user(p["id"], artist["id"])
    r = client.get("/partner/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert p["name"] in html
    assert artist["email"] in client.get("/partner/roster").get_data(as_text=True)


def test_a_seat_only_reaches_the_permissions_its_role_holds(flask_app):
    p = _partner(flask_app, "Perms %s" % uuid.uuid4().hex[:6])
    client, staff = _account(flask_app, "lowseat")
    with flask_app.app_context():
        pstore.add_member(p["id"], staff["email"], "Low", "viewer", user_id=staff["id"])
        m = pstore.get_member(p["id"], user_id=staff["id"])
        assert pstore.can(m, "roster_view") is True
        assert pstore.can(m, "manage_members") is False
        assert pstore.can(m, "act_as_artist") is False
    assert client.get("/partner/").status_code == 200
    assert client.get("/partner/roster").status_code == 200


def test_the_host_resolves_the_tenant_before_the_seat_does(flask_app):
    """A partner's own domain must resolve to that partner and no other,
    whoever is signed in. Tested through the resolver directly: the test
    client will not carry a session cookie across a host change."""
    custom = "own-%s.example.net" % uuid.uuid4().hex[:6]
    a = _partner(flask_app, "Hosted %s" % uuid.uuid4().hex[:6], domain=custom)
    slug = "sub-%s" % uuid.uuid4().hex[:6]
    b = _partner(flask_app, "Subbed %s" % uuid.uuid4().hex[:6], slug=slug)
    root = appmod._PARTNER_ROOT

    with flask_app.app_context():
        assert pstore.partner_by_domain(custom)["id"] == a["id"]
        assert pstore.partner_by_domain("not-a-tenant.example.net") is None
        # subdomain of the root -> the partner with that slug
        assert pstore.partner_by_slug(slug)["id"] == b["id"]
        host = "%s.%s" % (slug, root)
        assert host.endswith(root) and host != root
        assert pstore.partner_by_slug(host[:-len(root) - 1])["id"] == b["id"]


def test_a_suspended_partner_stops_answering(flask_app):
    p = _partner(flask_app, "Halt %s" % uuid.uuid4().hex[:6])
    client, staff = _account(flask_app, "halted")
    with flask_app.app_context():
        pstore.add_member(p["id"], staff["email"], "Staff", "owner", user_id=staff["id"])
    assert client.get("/partner/").status_code == 200
    with flask_app.app_context():
        pstore.set_partner_status(p["id"], "suspended")
    assert client.get("/partner/").status_code == 404, (
        "a suspended tenant must stop answering, not degrade")


def test_the_plain_address_resolves_no_tenant_for_a_direct_account(flask_app):
    """Every account that exists today is a direct Street Banker account and
    must stay one. Partner resolution has to be invisible to them."""
    client, _ = _account(flask_app, "direct")
    r = client.get("/dashboard")
    assert r.status_code in (200, 302)
    assert client.get("/partner/").status_code == 404


def test_the_audit_trail_is_scoped_and_records_the_actor(flask_app):
    a = _partner(flask_app, "AuditA %s" % uuid.uuid4().hex[:6])
    b = _partner(flask_app, "AuditB %s" % uuid.uuid4().hex[:6])
    _, actor = _account(flask_app, "actor")
    _, subject = _account(flask_app, "subject")
    with flask_app.app_context():
        pstore.audit(a["id"], "act_as_artist", actor=actor,
                     subject_user_id=subject["id"], detail="opened the desk")
        mine = pstore.audit_trail(a["id"])
        theirs = pstore.audit_trail(b["id"])
    assert len(mine) == 1 and mine[0]["actor_email"] == actor["email"].lower()
    assert mine[0]["subject_user_id"] == subject["id"]
    assert theirs == [], "one partner's activity must not appear in another's trail"
