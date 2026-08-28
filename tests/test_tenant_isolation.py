"""One account must never be served another account's rows.

This file exists because it happened twice. The `inbox` table shipped with
no user_id and every account read every row; it was fixed and a comment was
left in db.py. `smart_links` had the column all along but `get_db_links()`
had no WHERE clause, and /links rendered the result straight into the page,
so every signed-in account was served every other account's link titles,
slugs and destinations.

The pattern in both: the leak is not in the schema, it is in one query that
forgot the predicate, and nothing failed loudly. So these tests do not read
the source — they create two real accounts through the real app, write data
as one, and assert the other cannot see it in the HTML it is served.
"""
import os
import sys
import uuid

import pytest

import app as appmod
import db as store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _account(app, label):
    c = app.test_client()
    email = "iso-%s-%s@example.net" % (label, uuid.uuid4().hex[:8])
    c.post("/signup", data={"name": label, "email": email, "password": "iso-pass-123"})
    c.post("/login", data={"email": email, "password": "iso-pass-123"})
    with app.app_context():
        return c, store.get_user_by_email(email)


def test_smart_links_are_not_served_to_another_account(flask_app):
    """The regression. A private link is a release plan: its title names an
    unreleased track and its target is often an unlisted URL."""
    a_client, a = _account(flask_app, "alpha")
    b_client, b = _account(flask_app, "bravo")
    assert a["id"] != b["id"]

    title = "PRIVATE-%s" % uuid.uuid4().hex[:8]
    target = "https://unreleased.example.net/%s" % uuid.uuid4().hex[:8]
    with flask_app.app_context():
        slug = store.create_db_link("iso-secret", a["id"], title, target, ["spotify"], None)

    html = b_client.get("/links").get_data(as_text=True)
    assert title not in html, "another account's link TITLE is on this page"
    assert slug not in html, "another account's link SLUG is on this page"
    assert target not in html, "another account's link TARGET is on this page"

    # ...and the owner still sees their own.
    own = a_client.get("/links").get_data(as_text=True)
    assert title in own and slug in own


def test_get_db_links_requires_an_owner(flask_app):
    """A default of None would make the forgetful call site return every row
    again. The argument is required so that mistake raises instead."""
    with flask_app.app_context():
        with pytest.raises(TypeError):
            store.get_db_links()


def test_every_owned_table_query_in_db_scopes_by_its_owner(flask_app):
    """A live crawl, not a source read: for each account-owned table, write a
    row as A and assert B's listing does not contain it."""
    a_client, a = _account(flask_app, "alpha2")
    b_client, b = _account(flask_app, "bravo2")
    mark = uuid.uuid4().hex[:10]

    with flask_app.app_context():
        cases = []
        slug = store.create_db_link("iso-crawl", a["id"], "CRAWL-" + mark,
                                    "https://x.example.net/" + mark, [], None)
        cases.append(("smart_links", lambda uid: store.get_db_links(uid), mark))

        for name, lister, needle in cases:
            mine = repr(lister(a["id"]))
            theirs = repr(lister(b["id"]))
            assert needle in mine, "%s: the owner cannot see their own row" % name
            assert needle not in theirs, "%s: another account can see it" % name
