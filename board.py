"""Team-Up Board — routes.

Server-rendered first: every form posts normally and redirects somewhere
sensible, every filter is a query parameter, and the region/genre pickers
are <datalist>s that work with JavaScript off. board.js only layers on
typeahead, chips and auto-opening the post form.

URLs the old page had (/tour-board, /tour-board/post,
/tour-board/<id>/reply, /close, /delete) keep working.
"""
import html as _html
import json

from flask import (Blueprint, abort, jsonify, redirect, render_template, request,
                   session, url_for)

import board_store as bs
import board_taxonomy as tx
import db as store
import email_provider as emailer

bp = Blueprint("board", __name__)
_base_url = lambda: ""


def _me():
    uid = session.get("user_id")
    return store.get_user(uid) if uid else None


def _login():
    return redirect(url_for("login", next=request.path))


def _ctx(user, **extra):
    base = {
        "active_page": "tour-board", "user": user,
        "regions": tx.region_options(), "genre_opts": tx.genre_options(),
        "kinds": bs.KIND_LABELS, "unread": bs.unread_total(user["id"]) if user else 0,
        "region_label": tx.region_label, "genre_label": tx.genre_label,
    }
    base.update(extra)
    return base


def _form_fields(f):
    return {"region_code": f.get("region_code"), "region_text": f.get("region_text") or f.get("region"),
            "window_start": f.get("window_start"), "window_end": f.get("window_end"), "window": f.get("window"),
            "genres": [g for g in f.getlist("genres") if g], "genre": f.get("genre"),
            "details": f.get("details"), "draw_min": f.get("draw_min"), "draw_max": f.get("draw_max")}


def _prefill():
    a = request.args
    if not any(a.get(k) for k in ("new", "kind", "title", "region", "from", "to", "genre", "details")):
        return None
    return {"kind": a.get("kind") or "artist", "title": a.get("title") or "", "region": a.get("region") or "",
            "region_code": tx.parse_region(a.get("region") or "")[0] or "", "window_start": a.get("from") or "",
            "window_end": a.get("to") or "", "genre": a.get("genre") or "", "details": a.get("details") or ""}


def _sweep_renewals():
    """Listings at or past expiry get one renew email with a one-click link;
    the in-app notification is the fallback when email is not configured."""
    for l in bs.expiring_soon():
        link = "%s/board-renew/%s?t=%s" % (_base_url(), l["id"], l["renew_token"])
        store.notify(l["user_id"], "network", "Your Team-Up listing is expiring",
                     "“%s” drops off the board soon. Renew it for another %d days." % (l["title"], bs.EXPIRE_DAYS),
                     "/tour-board/%s" % l["id"])
        if emailer.configured() and l.get("poster_email"):
            try:
                emailer.send(l["poster_email"], "Renew your Team-Up listing?",
                             "<p>“%s” is about to expire on the Team-Up Board.</p>"
                             "<p><a href=\"%s\">Renew it for another %d days</a> — one click, nothing else to do.</p>"
                             % (_html.escape(l["title"]), link, bs.EXPIRE_DAYS))
            except Exception:
                pass
        bs.mark_renew_notice(l["id"])


# --- board ----------------------------------------------------------------------

@bp.route("/tour-board")
def index():
    user = _me()
    if user is None:
        return _login()
    _sweep_renewals()
    a = request.args
    kind = a.get("kind") if a.get("kind") in bs.KINDS else ""
    region = a.get("region") or ""
    if region and not tx.region_label(region):
        region = tx.parse_region(region)[0] or ""
    genre = a.get("genre") if a.get("genre") in dict(tx.genre_options()) else ""
    start, end = (a.get("from") or "")[:10], (a.get("to") or "")[:10]
    sort = "soonest" if a.get("sort") == "soonest" else "newest"
    listings = bs.list_listings(kind=kind or None, region=region or None, genre=genre or None,
                                start=start or None, end=end or None, sort=sort)
    own = bs.list_own(user["id"])
    counts = bs.reply_counts([l["id"] for l in own])
    chips = {}
    for l in listings:
        if l["user_id"] not in chips:
            chips[l["user_id"]] = bs.verified_chips(l["user_id"])
    coach = session.pop("board_coach", None)
    return render_template("board/index.html", **_ctx(
        user, listings=listings, own=own, counts=counts, chips=chips, stats=bs.stats(),
        watches=bs.list_watches(user["id"]), prefill=_prefill(), coach=coach,
        f={"kind": kind, "region": region, "genre": genre, "from": start, "to": end, "sort": sort},
        filtered=bool(kind or region or genre or start or end)))


@bp.route("/tour-board/post", methods=["GET", "POST"])
def post():
    user = _me()
    if user is None:
        return _login()
    if request.method == "GET":
        # Old bookmark / typed URL: open the board with the post form unfolded.
        qs = request.query_string.decode("utf-8", "replace")
        return redirect("/tour-board?new=1" + ("&" + qs if qs else ""))
    kind = request.form.get("kind") or ""
    title = (request.form.get("title") or "").strip()
    lid, coaching = bs.add_listing(user["id"], kind, title, _form_fields(request.form))
    if lid is None:
        session["board_coach"] = {"head": "Not posted.", "err": True, "items": coaching or ["A headline is required."]}
        return redirect("/tour-board?new=1")
    listing = bs.get_listing(lid)
    _alert_watchers(listing, user)
    if coaching:
        session["board_coach"] = {"head": "Posted.", "err": False, "items": coaching}
    return redirect("/tour-board/%s" % lid)


def _alert_watchers(listing, poster):
    for w in bs.matching_watches(listing):
        store.notify(w["user_id"], "network", "New Team-Up listing matches your watch",
                     "“%s” — %s." % (listing["title"], w["label"]), "/tour-board/%s" % listing["id"])
        bs.touch_watch(w["id"])
        if emailer.configured():
            u = store.get_user(w["user_id"])
            if u and u.get("email"):
                try:
                    emailer.send(u["email"], "Team-Up Board: a listing matches your watch",
                                 "<p><b>%s</b> just posted “%s” (%s).</p><p><a href=\"%s/tour-board/%s\">Open it</a></p>"
                                 % (_html.escape(poster.get("name") or "A member"), _html.escape(listing["title"]),
                                    _html.escape(w["label"]), _base_url(), listing["id"]))
                except Exception:
                    pass


@bp.route("/tour-board/inbox")
def inbox():
    user = _me()
    if user is None:
        return _login()
    return render_template("board/inbox.html", **_ctx(user, threads=bs.inbox(user["id"])))


@bp.route("/tour-board/api/regions")
def api_regions():
    user = _me()
    if user is None:
        return jsonify({"ok": False}), 401
    q = (request.args.get("q") or "").strip().lower()
    out = []
    for code, label, kind in tx.region_options():
        if not q or q in label.lower() or q in code:
            out.append({"code": code, "label": label, "kind": kind})
    if q:
        code, conf = tx.parse_region(q)
        if code and code not in [o["code"] for o in out]:
            out.insert(0, {"code": code, "label": tx.region_label(code), "kind": "match"})
    return jsonify({"ok": True, "regions": out[:25]})


# --- one listing -----------------------------------------------------------------

@bp.route("/tour-board/<listing_id>")
def listing(listing_id):
    user = _me()
    if user is None:
        return _login()
    l = bs.get_listing(listing_id)
    if l is None:
        abort(404)
    mine = l["user_id"] == user["id"]
    if l["effective_status"] != "open" and not mine and not bs.get_thread_for(listing_id, user["id"]) if hasattr(bs, "get_thread_for") else False:
        pass
    threads = bs.threads_for_listing(listing_id) if mine else []
    my_thread = None
    if not mine:
        for t in bs.threads_for_listing(listing_id):
            if t["replier_id"] == user["id"]:
                my_thread = t
    coach = session.pop("board_coach", None)
    return render_template("board/listing.html", **_ctx(
        user, l=l, mine=mine, threads=threads, my_thread=my_thread, chips=bs.verified_chips(l["user_id"]),
        coach=coach, posted=request.args.get("posted")))


@bp.route("/tour-board/<listing_id>/reply", methods=["POST"])
def reply(listing_id):
    user = _me()
    if user is None:
        return _login()
    l = bs.get_listing(listing_id)
    message = (request.form.get("message") or "").strip()
    if l is None or l["effective_status"] != "open" or l["user_id"] == user["id"] or not message:
        return redirect("/tour-board/%s" % listing_id if l else "/tour-board")
    tid = bs.start_or_get_thread(l, user["id"])
    bs.add_message(tid, user["id"], message)
    store.notify(l["user_id"], "network", "New reply on your Team-Up listing",
                 "%s replied to “%s”." % (user.get("name") or "A member", l["title"]),
                 "/tour-board/thread/%s" % tid)
    if emailer.configured():
        owner = store.get_user(l["user_id"])
        if owner and owner.get("email"):
            try:
                emailer.send(owner["email"], "New reply on your Team-Up listing",
                             "<p><b>%s</b> replied to “%s”:</p><p>%s</p><p><a href=\"%s/tour-board/thread/%s\">Open the thread</a> in Street Banker to answer.</p>"
                             % (_html.escape(user.get("name") or "A member"), _html.escape(l["title"]),
                                _html.escape(message[:500]), _base_url(), tid))
            except Exception:
                pass
    return redirect("/tour-board/thread/%s?sent=1" % tid)


@bp.route("/tour-board/thread/<thread_id>", methods=["GET", "POST"])
def thread(thread_id):
    user = _me()
    if user is None:
        return _login()
    t = bs.get_thread(thread_id)
    if t is None or user["id"] not in (t["poster_id"], t["replier_id"]):
        abort(404)
    if request.method == "POST":
        body = (request.form.get("message") or "").strip()
        if body:
            bs.add_message(thread_id, user["id"], body)
            other = t["replier_id"] if user["id"] == t["poster_id"] else t["poster_id"]
            store.notify(other, "network", "New message on “%s”" % t["listing_title"],
                         "%s: %s" % (user.get("name") or "A member", body[:120]), "/tour-board/thread/%s" % thread_id)
        return redirect("/tour-board/thread/%s" % thread_id)
    bs.mark_read(thread_id, user["id"])
    l = bs.get_listing(t["listing_id"])
    return render_template("board/thread.html", **_ctx(
        user, t=t, l=l, messages=bs.thread_messages(thread_id), i_am_poster=user["id"] == t["poster_id"],
        sent=request.args.get("sent")))


@bp.route("/tour-board/<listing_id>/edit", methods=["GET", "POST"])
def edit(listing_id):
    user = _me()
    if user is None:
        return _login()
    l = bs.get_listing(listing_id)
    if l is None or l["user_id"] != user["id"]:
        abort(404)
    if request.method == "POST":
        ok, coaching = bs.update_listing(user["id"], listing_id, request.form.get("title"), _form_fields(request.form))
        if coaching:
            session["board_coach"] = {"head": "Saved.", "err": False, "items": coaching}
        return redirect("/tour-board/%s" % listing_id)
    return render_template("board/edit.html", **_ctx(user, l=l))


@bp.route("/tour-board/<listing_id>/close", methods=["POST"])
def close(listing_id):
    user = _me()
    if user is None:
        return _login()
    bs.set_status(user["id"], listing_id, "closed")
    return redirect(request.form.get("next") or "/tour-board")


@bp.route("/tour-board/<listing_id>/reopen", methods=["POST"])
def reopen(listing_id):
    user = _me()
    if user is None:
        return _login()
    bs.renew(listing_id, user_id=user["id"])
    return redirect(request.form.get("next") or "/tour-board/%s" % listing_id)


@bp.route("/tour-board/<listing_id>/fill", methods=["POST"])
def fill(listing_id):
    user = _me()
    if user is None:
        return _login()
    tid = request.form.get("thread_id") or ""
    if tid:
        t = bs.get_thread(tid)
        if not t or t["listing_id"] != listing_id:
            tid = ""
    if bs.set_status(user["id"], listing_id, "filled", filled_via=tid) and tid:
        t = bs.get_thread(tid)
        store.notify(t["replier_id"], "network", "Matched on the Team-Up Board",
                     "“%s” was marked filled with you. Nice one." % t["listing_title"], "/tour-board/thread/%s" % tid)
    return redirect(request.form.get("next") or "/tour-board/%s" % listing_id)


@bp.route("/board-renew/<listing_id>")
def renew_by_token(listing_id):
    """One click from the renew email. /board-renew/ is a public prefix so
    the login wall does not swallow the click; the token (single use) is
    the authorisation."""
    token = request.args.get("t") or ""
    user = _me()
    if token and bs.renew(listing_id, token=token):
        if user:
            return redirect("/tour-board/%s?renewed=1" % listing_id)
        return render_template("board/renewed.html", active_page="tour-board", ok=True, listing_id=listing_id)
    return render_template("board/renewed.html", active_page="tour-board", ok=False, listing_id=listing_id), 404


@bp.route("/tour-board/<listing_id>/renew", methods=["POST"])
def renew(listing_id):
    user = _me()
    if user is None:
        return _login()
    bs.renew(listing_id, user_id=user["id"])
    return redirect(request.form.get("next") or "/tour-board/%s?renewed=1" % listing_id)


@bp.route("/tour-board/<listing_id>/delete", methods=["POST"])
def delete(listing_id):
    user = _me()
    if user is None:
        return _login()
    bs.delete_listing(user["id"], listing_id)
    return redirect("/tour-board")


# --- saved searches -------------------------------------------------------------

@bp.route("/tour-board/watch", methods=["POST"])
def watch():
    user = _me()
    if user is None:
        return _login()
    f = request.form
    region = f.get("region") or ""
    if region and not tx.region_label(region):
        region = tx.parse_region(region)[0] or ""
    genres = [g for g in ([f.get("genre")] + f.getlist("genres")) if g and g in dict(tx.genre_options())]
    bs.add_watch(user["id"], f.get("kind") or "", region, genres, (f.get("from") or "")[:10], (f.get("to") or "")[:10])
    return redirect("/tour-board?watched=1")


@bp.route("/tour-board/watch/<watch_id>/delete", methods=["POST"])
def watch_delete(watch_id):
    user = _me()
    if user is None:
        return _login()
    bs.delete_watch(user["id"], watch_id)
    return redirect("/tour-board")


def init(app, base_url):
    global _base_url
    _base_url = base_url
    bs.init_board()
    app.register_blueprint(bp)
