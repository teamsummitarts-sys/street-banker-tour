"""Preview-safe TOUR integrations for advancing and venue imagery.

These routes are registered only by the dedicated TOUR preview process today.
They use the same V2 Resend provider as production code and a server-side
Google Places lookup when GOOGLE_PLACES_API_KEY (or GOOGLE_MAPS_API_KEY) is set.
No API credential is ever sent to the browser.
"""
import html
import json
import os
import re
import urllib.parse
import urllib.request
from functools import lru_cache

from flask import Response, abort, redirect, request, session

import db as store
import email_provider as emailer
import tour_store as ts

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PLACES_SEARCH = "https://places.googleapis.com/v1/places:searchText"


def _places_key():
    return (os.environ.get("GOOGLE_PLACES_API_KEY")
            or os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()


def _preview_owner(tour_id, show_id=None):
    user_id = session.get("user_id")
    user = store.get_user(user_id) if user_id else None
    tour = ts.get_tour(tour_id) if tour_id else None
    if not user or not tour or tour.get("user_id") != user.get("id"):
        abort(404)
    show = ts.get_show(tour_id, show_id) if show_id else None
    if show_id and not show:
        abort(404)
    return user, tour, show


def _advance_value(tour_id, show_id, key):
    try:
        for row in ts.list_advance(tour_id, show_id):
            if row.get("item_key") == key:
                return (row.get("value") or row.get("comments") or "").strip()
    except Exception:
        pass
    return ""


def _default_advance_body(tour, show):
    artist = (tour.get("artist_name") or "the artist").strip()
    venue = (show.get("venue") or "the venue").strip()
    city = (show.get("city") or "").strip()
    show_date = (show.get("date") or "").strip()
    lines = [
        "Hi,",
        "",
        "We're advancing %s at %s%s on %s." % (
            artist, venue, (" in " + city) if city else "", show_date),
        "",
        "Could you please confirm the show-day details below and send back anything still outstanding?",
        "",
        "• Load-in / parking / bus parking",
        "• Production contact and stage / sound / lighting information",
        "• Soundcheck, doors, set time and curfew",
        "• Dressing rooms / hospitality / catering",
        "• Guest-list allotment / merch terms",
        "• Settlement contact / payment method",
        "",
        "Thank you,",
        "TOUR by Street Banker",
    ]
    return "\n".join(lines)


def _advance_html(body, tour, show):
    safe = html.escape(body).replace("\n", "<br>")
    artist = html.escape(tour.get("artist_name") or "")
    venue = html.escape(show.get("venue") or "")
    date = html.escape(show.get("date") or "")
    return (
        '<div style="background:#0A0A0C;padding:28px 16px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="max-width:620px;margin:0 auto;background:#111114;border:1px solid #51431f;'
        'padding:28px;color:#F5F5E9;">'
        '<div style="font-size:11px;letter-spacing:3px;color:#D4AF37;font-weight:700;">TOUR · ADVANCE</div>'
        '<div style="font-size:20px;line-height:1.25;font-weight:800;margin-top:8px;">%s · %s</div>'
        '<div style="font-size:13px;color:#AAA9A2;margin-top:5px;">%s</div>'
        '<div style="font-size:15px;line-height:1.6;margin-top:24px;">%s</div>'
        '<div style="font-size:11px;color:#77766f;margin-top:28px;border-top:1px solid #29292c;padding-top:14px;">'
        'Sent from TOUR by Street Banker</div></div></div>'
    ) % (artist, venue, date, safe)


def _send_advance():
    tour_id = (request.form.get("tour_id") or "").strip()
    show_id = (request.form.get("show_id") or "").strip()
    user, tour, show = _preview_owner(tour_id, show_id)

    recipient = (request.form.get("to") or "").strip().lower()
    subject = (request.form.get("subject") or "").strip()[:240]
    body = (request.form.get("body") or "").strip()
    if not _EMAIL.match(recipient):
        return redirect("/tours/%s/shows/%s?tab=advance&advance_error=recipient" % (tour_id, show_id))
    if not subject:
        subject = "%s · %s · %s advance" % (
            tour.get("artist_name") or "Artist", show.get("venue") or "Show", show.get("date") or "")
    if not body:
        body = _default_advance_body(tour, show)

    if not emailer.configured() or emailer.using_shared_test_sender():
        return redirect("/tours/%s/shows/%s?tab=advance&advance_error=resend" % (tour_id, show_id))

    accepted = emailer.send(recipient, subject, _advance_html(body, tour, show))
    if not accepted:
        return redirect("/tours/%s/shows/%s?tab=advance&advance_error=send" % (tour_id, show_id))

    try:
        actor = {"id": user["id"], "name": user.get("name") or user.get("email") or "TOUR"}
        ts.log_change(
            tour_id, user["id"], actor, "show", show_id,
            show.get("venue") or "Show", "advance_email", "",
            "Sent to %s · %s" % (recipient, subject), "info", "manual")
    except Exception:
        pass
    return redirect("/tours/%s/shows/%s?tab=advance&advance_sent=1" % (tour_id, show_id))


@lru_cache(maxsize=256)
def _place_photo_name(venue, city):
    key = _places_key()
    if not key or not venue:
        return ""
    query = "%s, %s" % (venue, city) if city else venue
    payload = json.dumps({"textQuery": query, "maxResultCount": 1}).encode("utf-8")
    req = urllib.request.Request(
        _PLACES_SEARCH,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.photos",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        places = data.get("places") or []
        photos = (places[0].get("photos") or []) if places else []
        return (photos[0].get("name") or "") if photos else ""
    except Exception:
        return ""


def _venue_photo():
    venue = (request.args.get("venue") or "").strip()[:180]
    city = (request.args.get("city") or "").strip()[:180]
    if not venue or not _places_key():
        abort(404)
    photo_name = _place_photo_name(venue, city)
    if not photo_name:
        abort(404)
    media_url = "https://places.googleapis.com/v1/%s/media?maxWidthPx=900" % urllib.parse.quote(photo_name, safe="/")
    req = urllib.request.Request(media_url, headers={"X-Goog-Api-Key": _places_key()})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read()
            ctype = resp.headers.get("Content-Type") or "image/jpeg"
    except Exception:
        abort(404)
    return Response(content, mimetype=ctype, headers={"Cache-Control": "public, max-age=86400"})


def register(app):
    app.add_url_rule("/tour-tools/advance/send", "tour_tools_advance_send", _send_advance, methods=["POST"])
    app.add_url_rule("/tour-tools/venue-photo", "tour_tools_venue_photo", _venue_photo, methods=["GET"])

    @app.context_processor
    def _tour_integration_context():
        return {
            "tour_resend_ready": bool(emailer.configured() and not emailer.using_shared_test_sender()),
            "tour_places_ready": bool(_places_key()),
            "tour_advance_default_body": _default_advance_body,
            "tour_advance_value": _advance_value,
        }
