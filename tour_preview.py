"""Dedicated no-login TOUR preview entrypoint.

This module is intentionally used only by the isolated Render preview service.
It does not change production authentication. A browser gets its own disposable
artist account, one seeded example TOUR, and is dropped directly into TOUR.
"""
import uuid

from flask import redirect, request, session
from werkzeug.security import generate_password_hash

import db as store
import tour_seed
import tour_store as ts
from app import app


_PREVIEW_DOMAIN = "tour-preview.local"


def _preview_user():
    user_id = session.get("user_id")
    user = store.get_user(user_id) if user_id else None
    if user and (user.get("email") or "").endswith("@" + _PREVIEW_DOMAIN):
        return user

    email = "tour-preview-%s@%s" % (uuid.uuid4().hex, _PREVIEW_DOMAIN)
    user_id = store.create_user(
        email,
        "TOUR Preview",
        generate_password_hash(uuid.uuid4().hex),
    )
    if user_id is None:
        return None
    store.set_user_plan(user_id, "artist")
    session["user_id"] = user_id
    session["tour_preview"] = True
    return store.get_user(user_id)


@app.context_processor
def _tour_preview_context():
    return {"tour_public_preview": True}


@app.route("/tour-share/preview")
def open_tour_preview():
    """Public entry that creates an isolated browser preview and opens TOUR."""
    user = _preview_user()
    if user is None:
        return "TOUR preview could not initialize.", 500

    tours = ts.list_tours(user["id"])
    if tours:
        tour_id = tours[0]["id"]
    else:
        tour_id = tour_seed.seed(user["id"])
    return redirect("/tours/%s" % tour_id)


class TourPreviewEntry:
    """Make the dedicated preview service root act like the TOUR product root.

    The first anonymous request is internally sent through the public preview
    bootstrap route. Once the signed preview session exists, normal TOUR routes
    run unchanged and keep all of TOUR's existing permission checks.
    """
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        cookie = environ.get("HTTP_COOKIE") or ""
        # The Flask session cookie is present after bootstrap. We do not parse
        # or trust it here; Flask still verifies it before any protected route.
        if path in ("/", "/tours") and "session=" not in cookie:
            environ["PATH_INFO"] = "/tour-share/preview"
        return self.wrapped(environ, start_response)


app.wsgi_app = TourPreviewEntry(app.wsgi_app)
