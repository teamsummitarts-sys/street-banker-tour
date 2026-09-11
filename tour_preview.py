"""Dedicated no-login TOUR preview entrypoint.

Only the isolated Render preview service starts this module. Production starts
app:app and keeps its existing authentication and durable-storage settings.
Each preview browser receives its own disposable account and can create tours
or one-off shows without seeing the Street Banker login wall.
"""
import os
import uuid

from flask import Response, redirect, request, session
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

import tour_store as ts
from app import app


_PREVIEW_DOMAIN = "tour-preview.local"
PREVIEW_REVISION = "launcher-direct-v3"


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
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-TOUR-Preview-Revision"] = PREVIEW_REVISION
    return response


def _kill_preview_service_worker():
    """The isolated preview must never strand a reviewer on cached offline UI."""
    js = r'''self.addEventListener("install",function(e){self.skipWaiting();});
self.addEventListener("activate",function(e){e.waitUntil(caches.keys().then(function(k){return Promise.all(k.map(function(n){return caches.delete(n);}));}).then(function(){return self.registration.unregister();}));});
self.addEventListener("fetch",function(){});'''
    return Response(js, mimetype="application/javascript", headers={
        "Cache-Control": "no-store, max-age=0",
        "Service-Worker-Allowed": "/",
    })

# Replace only the preview process's /sw.js view. Production app:app keeps the
# full offline-capable TOUR service worker.
if "service_worker" in app.view_functions:
    app.view_functions["service_worker"] = _kill_preview_service_worker


@app.route("/tour-share/preview")
def open_tour_preview():
    """Render the TOUR launcher directly: no external redirect, no login."""
    user = _preview_user()
    if user is None:
        return "TOUR preview could not initialize.", 500
    # Call the registered TOUR index inside this request so the browser receives
    # a 200 HTML document at the root URL instead of a redirect that an older
    # mobile service worker can mistake for a failed navigation.
    return app.view_functions["tours.index"]()


@app.route("/tour-share/preview/one-off", methods=["POST"])
def create_preview_one_off():
    """Create one show with a minimal internal TOUR container.

    The user experiences a one-off show; the small container lets the existing
    Show Command tools work unchanged instead of building a second show model.
    """
    user = _preview_user()
    if user is None:
        return "TOUR preview could not initialize.", 500

    venue = (request.form.get("venue") or "").strip()
    city = (request.form.get("city") or "").strip()
    show_date = (request.form.get("date") or "").strip()
    artist = (request.form.get("artist_name") or user.get("name") or "").strip()
    tz = (request.form.get("home_tz") or "America/New_York").strip()
    currency = (request.form.get("currency") or "USD").strip().upper()[:3]
    notes = (request.form.get("notes") or "").strip()
    if not venue or not show_date:
        return redirect("/tours#one-off")

    tour_id = ts.create_tour(user["id"], {
        "name": "One-off · %s" % venue,
        "artist_name": artist,
        "start_date": show_date,
        "end_date": show_date,
        "home_tz": tz,
        "currency": currency,
        "notes": "One-off show workspace",
    })
    show_id = store.add_tour_show(user["id"], show_date, venue, city, notes)
    ts.attach_show(tour_id, show_id, tz)
    try:
        ts.update_show_ext(tour_id, show_id, {"currency": currency})
    except Exception:
        pass
    return redirect("/tours/%s/shows/%s" % (tour_id, show_id))


class TourPreviewEntry:
    """Keep the preview root inside TOUR on both first and repeat visits."""
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        if (environ.get("REQUEST_METHOD", "GET") in ("GET", "HEAD")
                and path in ("/", "/tours", "/tours/")):
            environ["PATH_INFO"] = "/tour-share/preview"
        return self.wrapped(environ, start_response)


app.wsgi_app = TourPreviewEntry(app.wsgi_app)
