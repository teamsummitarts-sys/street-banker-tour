"""Dedicated no-login TOUR preview entrypoint.

Only the isolated Render preview service starts this module. Production starts
app:app and keeps its existing authentication and durable-storage settings.
Each preview browser receives its own disposable account and example tour.
"""
import os
import uuid

from flask import redirect, request, session
from werkzeug.security import generate_password_hash

import db as store

# The parent app registers REACH's application-wide template context. Rendering
# a TOUR page therefore opens REACH's store too. Render's free preview has no
# /var/data mount, unlike the durable V2 service. Resolve a preview-only default
# BEFORE importing the parent app; never change the main application's default
# or overwrite an explicitly configured REACH database.
if not (os.environ.get("REACH_DB_PATH") or "").strip():
    os.environ["REACH_DB_PATH"] = os.path.join(
        os.path.dirname(os.path.abspath(store.db_path())), "reach-preview.db"
    )

import tour_seed
import tour_store as ts
from app import app


_PREVIEW_DOMAIN = "tour-preview.local"
PREVIEW_REVISION = "storage-and-entry-v2"


def _preview_user():
    # Flask has already verified the session signature. A raw cookie's presence
    # must never decide whether a browser has a valid preview account.
    user_id = session.get("user_id")
    user = store.get_user(user_id) if user_id else None
    if user and (user.get("email") or "").endswith("@" + _PREVIEW_DOMAIN):
        session["tour_preview"] = True
        return user

    email = "tour-preview-%s@%s" % (uuid.uuid4().hex, _PREVIEW_DOMAIN)
    user_id = store.create_user(
        email, "TOUR Preview", generate_password_hash(uuid.uuid4().hex)
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


@app.after_request
def _preview_cache_policy(response):
    if not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-TOUR-Preview-Revision"] = PREVIEW_REVISION
    return response


@app.route("/tour-share/preview")
def open_tour_preview():
    """Open the browser's own tour, recovering expired/disposable sessions."""
    user = _preview_user()
    if user is None:
        return "TOUR preview could not initialize.", 500
    tours = ts.list_tours(user["id"])
    tour_id = tours[0]["id"] if tours else tour_seed.seed(user["id"])
    return redirect("/tours/%s" % tour_id)


class TourPreviewEntry:
    """Keep the preview root inside TOUR on both first and repeat visits.

    The public bootstrap verifies the signed session and persisted account.
    Looking for 'session=' in a Cookie header is insufficient: a session can
    expire, be malformed, or reference a disposable account lost on a restart.
    Other routes keep the parent's authentication and TOUR ownership checks.
    """
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        if (environ.get("REQUEST_METHOD", "GET") in ("GET", "HEAD")
                and path in ("/", "/tours", "/tours/")):
            environ["PATH_INFO"] = "/tour-share/preview"
        return self.wrapped(environ, start_response)


app.wsgi_app = TourPreviewEntry(app.wsgi_app)
