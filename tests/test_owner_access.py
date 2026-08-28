"""The owner gets the product without paying — and nothing else.

The risk in a rule like "this email gets everything" is that it quietly
becomes an authentication bypass. These tests pin down that it grants a
plan and only a plan: the password still has to be right, and no other
account is affected.
"""
import app as app_module
from app import create_app
import db as store
import plans

# Both of the owner's addresses. The account was actually created with
# the artiswarrecords one, so a list that only held the other granted
# nothing to the person it was written for.
OWNER = "artiswarrecords@gmail.com"
OWNER_ALT = "team.summitarts@gmail.com"
NOT_OWNER = "someone.else@example.com"


PASSWORD = "ownerpw12345"


def _account(app_obj, email, password=PASSWORD):
    """Sign up, or log in if a previous test already created it.

    The suite shares one database and the owner address is fixed, so a
    second signup returns 'already exists' and leaves the client with no
    session - which silently turns a gating assertion into a redirect."""
    client = app_obj.test_client()
    if store.get_user_by_email(email) is None:
        r = client.post("/signup", data={"name": "Owner Test",
                                         "email": email, "password": password})
        assert r.status_code == 302, "signup failed for %s" % email
    else:
        r = client.post("/login", data={"email": email, "password": password})
        assert r.status_code == 302, "login failed for %s" % email
    return client


def test_the_entitlement_list_holds_no_plaintext_address():
    """The list is SHA-256, so reading the source does not tell you which
    address gets in. (The address appears elsewhere in app.py as a public
    contact line - that is a different thing and not what this guards.)"""
    assert all(len(h) == 64 and all(c in "0123456789abcdef" for c in h)
               for h in app_module._OWNER_EMAIL_HASHES), \
        "entitlement list should contain hashes, not addresses"
    assert app_module._is_owner_email(OWNER)
    assert app_module._is_owner_email(OWNER_ALT)
    assert app_module._is_owner_email("  ArtIsWarRecords@Gmail.com  "), \
        "case and whitespace should not decide entitlement"
    assert not app_module._is_owner_email(NOT_OWNER)
    assert not app_module._is_owner_email("")
    assert not app_module._is_owner_email(None)


def test_the_owner_lands_on_the_top_plan_without_paying():
    app_obj = create_app()
    _account(app_obj, OWNER)
    user = store.get_user_by_email(OWNER)
    assert user["plan"] == app_module.OWNER_PLAN
    assert app_module.OWNER_PLAN == max(plans.TIER_RANK,
                                        key=plans.TIER_RANK.get), \
        "owner plan is not the top tier"


def test_the_owner_can_reach_the_pages_a_free_account_cannot():
    app_obj = create_app()
    owner = _account(app_obj, OWNER)
    other = _account(app_obj, NOT_OWNER)

    for path in ("/overview", "/royalties", "/catalog", "/reports"):
        assert owner.get(path).status_code == 200, "owner blocked from %s" % path
        assert other.get(path).status_code == 402, \
            "%s stopped being gated for everyone else" % path


def test_it_is_a_plan_grant_not_a_login_bypass():
    """The important one. A wrong password must still fail, and the
    address alone must not get anybody in."""
    app_obj = create_app()
    _account(app_obj, OWNER)

    attacker = app_obj.test_client()
    r = attacker.post("/login", data={"email": OWNER, "password": "wrong"})
    assert r.status_code == 200, "a failed login should re-render, not redirect"
    assert b"Incorrect email or password" in r.data
    # And no session was handed out.
    assert attacker.get("/overview").status_code in (302, 402), \
        "a failed owner login still reached a gated page"


def test_no_other_account_is_upgraded():
    app_obj = create_app()
    _account(app_obj, NOT_OWNER)
    user = store.get_user_by_email(NOT_OWNER)
    assert user["plan"] != app_module.OWNER_PLAN
    assert not app_module._grant_owner_plan(user)


def test_the_reset_link_ignores_the_host_header():
    """A password-reset link is the one URL where trusting Host hands a
    valid token to whoever set it: POST /forgot with the victim's address
    and Host: attacker.com, and the victim gets a genuine email pointing
    at the attacker's server.

    Render's edge refuses unconfigured hosts today, so this is not live.
    The link is pinned to PUBLIC_BASE_URL so it does not depend on that."""
    import app as m

    sent = []
    real_send, real_conf = m.emailer.send, m.emailer.configured
    # The route refuses to send at all without a mail provider, so both
    # have to be stood up to reach the link-building code.
    m.emailer.send = lambda to, subj, html, **kw: sent.append(html) or True
    m.emailer.configured = lambda: True
    try:
        app_obj = create_app()
        _account(app_obj, NOT_OWNER)
        app_obj.test_client().post(
            "/forgot", data={"email": NOT_OWNER},
            headers={"Host": "attacker.example"})
    finally:
        m.emailer.send, m.emailer.configured = real_send, real_conf

    assert sent, "no reset email was sent"
    body = sent[-1]
    assert "attacker.example" not in body, \
        "the reset link followed the Host header"
    assert m.PUBLIC_BASE_URL in body, \
        "the reset link should be pinned to PUBLIC_BASE_URL"


def test_the_demo_account_is_untouched():
    """Demo stays on its own plan - the tour depends on it."""
    create_app()
    demo = store.get_user_by_email("demo@streetbanker.io")
    assert demo is not None
    assert not app_module._is_owner_email(demo["email"])
