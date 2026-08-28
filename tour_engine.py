"""TOUR — the rules. Readiness, modes, what's next, My Day, change severity,
Ask Tour, the document extractor, importers and exporters.

Engine-free and database-free on purpose: every function here takes plain
dicts and lists that tour_store produced and returns plain dicts, so all
of it is testable without an app, and none of it can reach data the
caller was not allowed to load.

Two honesty rules run through the whole file:

  Nothing is invented. A readiness percentage is checklist arithmetic. A
  drive time is shown only if somebody entered one. A "next" is a real
  schedule row. Ask Tour answers from rows or says the row is missing.

  The extractor proposes, it never writes. It reads pasted text with
  patterns, attaches a confidence and the line it came from, and hands
  the proposals to a review step. There is no language model behind it
  today; the review step is the same one a model would feed.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:          # pragma: no cover
    ZoneInfo = None

import tour_store as ts

# --- time helpers -----------------------------------------------------------

def valid_tz(name):
    if not name or ZoneInfo is None:
        return False
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def now_in(tz_name):
    """Current local datetime in a zone, falling back to UTC when the zone
    is unknown — and saying so via the tzname the caller can display."""
    if valid_tz(tz_name):
        return datetime.now(ZoneInfo(tz_name))
    return datetime.now(timezone.utc)


def today_in(tz_name):
    return now_in(tz_name).date().isoformat()


def local_dt(day, hhmm, tz_name):
    """Combine a date string and HH:MM into an aware datetime."""
    if not day or not hhmm or not re.match(r"^\d{1,2}:\d{2}$", hhmm or ""):
        return None
    try:
        h, m = [int(x) for x in hhmm.split(":")]
        naive = datetime.fromisoformat(day[:10]).replace(hour=h, minute=m)
    except ValueError:
        return None
    if valid_tz(tz_name):
        return naive.replace(tzinfo=ZoneInfo(tz_name))
    return naive.replace(tzinfo=timezone.utc)


def fmt_time(hhmm):
    """'17:00' -> '5:00 PM'. Anything unparseable comes back as typed."""
    m = re.match(r"^(\d{1,2}):(\d{2})$", hhmm or "")
    if not m:
        return hhmm or ""
    h, mi = int(m.group(1)), m.group(2)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return "%d:%s %s" % (h12, mi, suffix)


def fmt_day(day):
    try:
        return datetime.fromisoformat(day[:10]).strftime("%a %b %-d") if hasattr(date, "fromisoformat") else day
    except Exception:
        try:
            return datetime.fromisoformat(day[:10]).strftime("%a %b %d")
        except Exception:
            return day or ""


def fmt_day_long(day):
    try:
        d = datetime.fromisoformat(day[:10])
        return d.strftime("%A %B %d").replace(" 0", " ")
    except Exception:
        return day or ""


def humanize_delta(delta):
    secs = int(delta.total_seconds())
    if secs < 0:
        return "started"
    mins = secs // 60
    if mins < 60:
        return "%d min" % mins
    hours = mins // 60
    if hours < 48:
        return "%dh %02dm" % (hours, mins % 60)
    return "%d days" % (hours // 24)


# --- tour mode --------------------------------------------------------------

def tour_mode(tour, shows, today=None):
    """'live' while the tour is underway, else 'planning'. A manual
    override on the tour wins. Live = today is within the date range, or
    within a day of any show."""
    override = (tour.get("mode_override") or "").strip()
    if override in ("live", "planning"):
        return override
    today = today or today_in(tour.get("home_tz") or "UTC")
    if tour.get("status") == "live":
        return "live"
    if tour.get("status") in ("wrapped", "cancelled"):
        return "planning"
    start, end = tour.get("start_date") or "", tour.get("end_date") or ""
    if start and end and start <= today <= end:
        return "live"
    for s in shows:
        try:
            d = date.fromisoformat(s["date"][:10])
            if abs((d - date.fromisoformat(today)).days) <= 1:
                return "live"
        except ValueError:
            continue
    return "planning"


def show_status_line(tour, shows, today=None):
    """'ON TOUR — SHOW 12 OF 31' / 'PLANNING — 31 DATES' / 'WRAPPED'."""
    today = today or today_in(tour.get("home_tz") or "UTC")
    total = len(shows)
    if tour.get("status") == "wrapped":
        return "WRAPPED — %d SHOW%s" % (total, "" if total == 1 else "S")
    if tour_mode(tour, shows, today) == "live" and shows:
        played = len([s for s in shows if s["date"] < today])
        upcoming_today = [s for s in shows if s["date"] == today]
        n = played + (1 if upcoming_today else 0)
        n = max(1, min(n, total))
        return "ON TOUR — SHOW %d OF %d" % (n, total)
    return "PLANNING — %d DATE%s" % (total, "" if total == 1 else "S")


# --- next -------------------------------------------------------------------

def next_item(tour, shows, schedule, travel, now=None):
    """The single next thing with a time on it, across schedule and travel.
    Returns {kind, title, when, where, show, delta_text, tz} or None."""
    tz = tour.get("home_tz") or "UTC"
    now = now or now_in(tz)
    candidates = []
    show_by_id = {s["id"]: s for s in shows}
    for it in schedule:
        show = show_by_id.get(it.get("show_id") or "")
        z = (show or {}).get("tz") or tz
        dt = local_dt(it["day_date"], it["start_time"], z)
        if dt and dt >= now - timedelta(minutes=5):
            candidates.append((dt, {"kind": "schedule", "title": it["title"],
                                    "when": it["start_time"], "where": it.get("location") or
                                    (show or {}).get("venue") or "", "show": show,
                                    "tz": z, "dt": dt, "item": it}))
    for tr in travel:
        show = show_by_id.get(tr.get("show_id") or "")
        z = tr.get("dep_tz") or (show or {}).get("tz") or tz
        dt = local_dt(tr["day_date"], tr["dep_time"], z)
        if dt and dt >= now - timedelta(minutes=5):
            title = {"air": "Flight", "ground": "Car", "bus": "Bus", "rail": "Train"}.get(tr["mode"], "Travel")
            if tr.get("number"):
                title += " " + tr["number"]
            candidates.append((dt, {"kind": "travel", "title": title, "when": tr["dep_time"],
                                    "where": tr.get("dep_loc") or tr.get("pickup") or "",
                                    "show": show, "tz": z, "dt": dt, "item": tr}))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    dt, best = candidates[0]
    best["delta_text"] = humanize_delta(dt - now)
    best["when_text"] = fmt_time(best["when"])
    return best


# --- readiness --------------------------------------------------------------

READINESS_CATEGORIES = [
    ("confirmation", "Show confirmation"), ("contract", "Contract"),
    ("deposit", "Deposit"), ("venue", "Venue"), ("promoter", "Promoter"),
    ("travel", "Travel"), ("hotel", "Hotel"), ("ground", "Ground"),
    ("advance", "Advance"), ("production", "Production"), ("catering", "Catering"),
    ("hospitality", "Hospitality"), ("guest_list", "Guest list"), ("vip", "VIP"),
    ("marketing", "Marketing"), ("content", "Content"),
    ("settlement", "Settlement requirements"),
]


def _adv(advance_rows, key):
    for r in advance_rows:
        if r["item_key"] == key:
            return r
    return None


def _adv_done(advance_rows, *keys):
    states = [(_adv(advance_rows, k) or {}).get("status") for k in keys]
    states = [s for s in states if s != "na"]
    if not states:
        return None                     # not applicable
    if all(s == "complete" for s in states):
        return True
    if any(s == "waiting" for s in states):
        return "waiting"
    return False


def show_readiness(show, advance_rows, travel, lodging, files, guests_summary, content,
                   vip_count, config=None):
    """Per-category state for one show, from real rows. Returns
    {pct, done, total, items:[{key,label,state,detail}]}. state is True,
    False, 'waiting' or None (not applicable, excluded from the score)."""
    config = config or [k for k, _ in READINESS_CATEGORIES]
    labels = dict(READINESS_CATEGORIES)
    file_cats = {f["category"] for f in files}
    items = []

    def push(key, state, detail=""):
        if key in config:
            items.append({"key": key, "label": labels.get(key, key), "state": state,
                          "detail": detail})

    push("confirmation", show.get("status") in ("confirmed", "advanced", "played", "settled"),
         "Status: %s" % show.get("status"))
    push("contract", "contract" in file_cats or _adv_done(advance_rows, "promoter") is True,
         "Contract file or promoter terms on record")
    dep_req = (show.get("deposit_required") or "").strip()
    dep_rec = (show.get("deposit_received") or "").strip()
    if dep_req in ("", "0"):
        push("deposit", None, "No deposit required")
    else:
        # No amounts here: readiness is shown to every member, money is not.
        push("deposit", bool(dep_rec) and dep_rec not in ("0",),
             "Deposit received" if dep_rec and dep_rec != "0" else "Deposit required, not yet received")
    push("venue", bool(show.get("venue_id")) or _adv_done(advance_rows, "venue_contact") is True,
         "Venue record linked or venue contact confirmed")
    push("promoter", bool((show.get("promoter") or "").strip()) or _adv_done(advance_rows, "promoter") is True,
         show.get("promoter") or "No promoter entered")
    air_or_rail = [t for t in travel if t["mode"] in ("air", "rail", "bus")]
    ground = [t for t in travel if t["mode"] == "ground"]
    push("travel", (any(t["status"] == "confirmed" for t in air_or_rail) if air_or_rail
                    else (True if _adv_done(advance_rows, "airport") is None else bool(air_or_rail))),
         "%d leg%s" % (len(air_or_rail), "" if len(air_or_rail) == 1 else "s"))
    push("hotel", any(l["status"] == "confirmed" for l in lodging) if lodging else False,
         ("%s" % lodging[0]["property"]) if lodging else "No hotel added")
    push("ground", any(g["status"] == "confirmed" for g in ground) if ground else False,
         "%d ground leg%s" % (len(ground), "" if len(ground) == 1 else "s"))
    adv_applicable = [r for r in advance_rows if r["status"] != "na"]
    adv_done = [r for r in adv_applicable if r["status"] == "complete"]
    push("advance", (len(adv_done) == len(adv_applicable)) if adv_applicable else False,
         "%d of %d items complete" % (len(adv_done), len(adv_applicable)))
    push("production", _adv_done(advance_rows, "load_in", "stage", "power", "sound", "lighting", "backline"),
         "Load-in, stage, power, sound, lighting, backline")
    push("catering", _adv_done(advance_rows, "catering"), "Catering advanced")
    push("hospitality", _adv_done(advance_rows, "hospitality", "dressing_rooms"), "Hospitality and dressing rooms")
    gl_ok = bool((show.get("guest_cutoff") or "").strip()) and bool((show.get("guest_allocation") or "").strip())
    push("guest_list", gl_ok, "Allocation %s · cutoff %s" % (show.get("guest_allocation") or "—",
                                                              show.get("guest_cutoff") or "—"))
    push("vip", None if not vip_count else True, "%d VIP record%s" % (vip_count, "" if vip_count == 1 else "s"))
    mk = show.get("marketing") or {}
    push("marketing", bool((show.get("ticket_url") or "").strip()) or bool(mk.get("onsale")),
         "Ticket link or on-sale date set")
    assigned = [c for c in content if c.get("assignee")]
    push("content", (len(assigned) > 0) if content else False,
         "%d of %d content items assigned" % (len(assigned), len(content)))
    push("settlement", _adv_done(advance_rows, "settlement_location", "payment_method"),
         "Settlement location and payment method")

    scored = [i for i in items if i["state"] is not None]
    done = [i for i in scored if i["state"] is True]
    pct = round(100 * len(done) / len(scored)) if scored else 0
    return {"pct": pct, "done": len(done), "total": len(scored), "checks": items,
            "missing": [i for i in items if i["state"] is False],
            "waiting": [i for i in items if i["state"] == "waiting"]}


def tour_readiness(per_show):
    """Mean of show percentages plus the dates that need attention."""
    if not per_show:
        return {"pct": 0, "shows": 0, "attention": []}
    pct = round(sum(p["readiness"]["pct"] for p in per_show) / len(per_show))
    attention = sorted([p for p in per_show if p["readiness"]["pct"] < 70],
                       key=lambda p: p["readiness"]["pct"])
    return {"pct": pct, "shows": len(per_show), "attention": attention}


# --- needs attention --------------------------------------------------------

def needs_attention(shows, readiness_by_show, today):
    """Unresolved issues across the tour, worded as the thing to do."""
    issues = []
    for s in shows:
        if s["date"] < today:
            continue
        r = readiness_by_show.get(s["id"])
        if not r:
            continue
        city = s.get("city") or s.get("venue") or s["date"]
        for item in r["missing"]:
            word = {"hotel": "hotel not confirmed", "deposit": "deposit outstanding",
                    "ground": "ground transport missing", "advance": "advance incomplete",
                    "content": "no content assignment", "travel": "travel not confirmed",
                    "guest_list": "guest cutoff missing", "promoter": "promoter not entered",
                    "venue": "venue not confirmed", "settlement": "settlement details missing",
                    "marketing": "no ticket link", "contract": "contract not on file",
                    "confirmation": "show not confirmed", "production": "production advance open",
                    "catering": "catering incomplete", "hospitality": "hospitality incomplete",
                    }.get(item["key"], item["label"].lower() + " incomplete")
            issues.append({"show": s, "key": item["key"], "text": "%s %s" % (city, word)})
    return issues


# --- my day -----------------------------------------------------------------

def visible_to(viewer, entry, scopes):
    """Whether one schedule/travel/lodging row is visible to a viewer.
    Owner and admin see everything. 'management' needs the people scope or
    edit; 'private' needs admin or to be named in the audience."""
    if viewer.get("is_owner") or "admin" in scopes:
        return True
    vis = entry.get("visibility") or "all"
    if vis == "all":
        return True
    if vis == "management":
        return "edit" in scopes or "people" in scopes or "financials" in scopes
    audience = entry.get("audience") or []
    pid = (viewer.get("person") or {}).get("id")
    return bool(pid and pid in audience)


def personal(viewer, scopes, schedule, travel):
    """The subset of (already visibility-filtered) schedule and travel rows
    that concern this person: items for everyone, items they are
    responsible for by name, items whose audience names them, legs they
    are on. Owner and admin see all. Used by My Day AND by the NEXT
    block, so the two can never disagree."""
    pid = (viewer.get("person") or {}).get("id")
    pname = ((viewer.get("person") or {}).get("name") or "").strip().lower()
    boss = viewer.get("is_owner") or "admin" in scopes
    sched = []
    for it in schedule:
        if not visible_to(viewer, it, scopes):
            continue
        resp = (it.get("responsible") or "").strip().lower()
        mine = boss or not resp or (pname and resp == pname)
        if not mine:
            continue
        if it.get("audience") and not boss and pid not in it["audience"]:
            continue
        sched.append(it)
    legs = []
    for tr in travel:
        if not visible_to(viewer, tr, scopes):
            continue
        trav = tr.get("travelers") or ["all"]
        if "all" in trav or boss or (pid and pid in trav):
            legs.append(tr)
    return sched, legs


def my_day(viewer, scopes, shows, schedule, travel, lodging, on_date):
    """Only what concerns the signed-in person on one date."""
    show_by_id = {s["id"]: s for s in shows}
    sched, legs = personal(viewer, scopes, schedule, travel)
    rows = []
    for it in sched:
        if it["day_date"] != on_date:
            continue
        rows.append({"kind": "schedule", "time": it["start_time"], "title": it["title"],
                     "where": it.get("location") or "", "category": it["category"],
                     "confirmed": bool(it.get("confirmed")), "precision": it["precision"],
                     "show": show_by_id.get(it.get("show_id") or ""), "item": it})
    for tr in legs:
        if tr["day_date"] != on_date:
            continue
        title = {"air": "Flight", "ground": "Car", "bus": "Bus", "rail": "Train"}.get(tr["mode"], "Travel")
        if tr.get("number"):
            title += " " + tr["number"]
        arrow = " → ".join([x for x in (tr.get("dep_loc") or tr.get("pickup"), tr.get("arr_loc") or tr.get("destination")) if x])
        rows.append({"kind": "travel", "time": tr["dep_time"], "title": title, "where": arrow,
                     "category": "travel", "confirmed": tr["status"] == "confirmed",
                     "precision": "exact", "show": show_by_id.get(tr.get("show_id") or ""), "item": tr})
    hotel = None
    for l in lodging:
        if l["checkin"] and l["checkin"] <= on_date and (not l["checkout"] or l["checkout"] >= on_date):
            if visible_to(viewer, l, scopes):
                hotel = l
                break
    rows.sort(key=lambda r: (r["time"] == "", r["time"]))
    return {"date": on_date, "rows": rows, "hotel": hotel}


# --- change severity --------------------------------------------------------

def classify_change(entity_type, field):
    """Which edits are worth telling people about. Time and place moves
    are important; a hotel or a cancelled leg is critical; notes are not
    a notification."""
    if entity_type in ("schedule",) and field in ("start_time", "day_date"):
        return "important"
    if entity_type in ("schedule",) and field in ("title", "location"):
        return "important"
    if entity_type == "travel" and field in ("dep_time", "arr_time", "day_date", "status", "number"):
        return "critical" if field in ("status", "day_date") else "important"
    if entity_type == "lodging" and field in ("property", "checkin", "checkout", "status"):
        return "critical" if field == "property" else "important"
    if entity_type == "show" and field in ("date", "venue", "status"):
        return "critical"
    if entity_type == "money":
        return "important"
    if entity_type == "advance" and field == "status":
        return "info"
    return "info"


# --- ask tour ---------------------------------------------------------------

def _match_show(q, shows):
    ql = q.lower()
    for s in shows:
        for key in (s.get("city") or "", s.get("venue") or ""):
            if key and key.lower().split(",")[0].strip() and key.lower().split(",")[0].strip() in ql:
                return s
    return None


def ask(question, ctx):
    """Answer from the rows the viewer was allowed to load. `ctx` is the
    dict tour_os assembles; every list in it is already permission-
    filtered, so nothing here can leak.

    Returns {answer, sources:[...], found:bool}. When a thing is simply
    not entered, it says so in those words — it never fills the gap.
    """
    q = (question or "").strip()
    ql = q.lower()
    shows = ctx["shows"]
    today = ctx["today"]
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    show = _match_show(ql, shows)

    def src(kind, label):
        return {"kind": kind, "label": label}

    if not q:
        return {"answer": "Ask about times, hotels, travel, guests, money or what changed.", "sources": [], "found": False}

    # --- times on a schedule (lobby call, soundcheck, doors, set) --------
    time_words = {"lobby": "call", "call": "call", "soundcheck": "soundcheck", "sound check": "soundcheck",
                  "doors": "doors", "set time": "set", "set": "set", "load in": "load_in",
                  "load-in": "load_in", "curfew": "curfew", "bus call": "bus_call"}
    for word, cat in time_words.items():
        if word in ql:
            day = tomorrow if "tomorrow" in ql else (show["date"] if show else today)
            rows = [r for r in ctx["schedule"] if r["day_date"] == day and r["category"] == cat]
            if not rows:
                rows = [r for r in ctx["schedule"] if r["day_date"] == day and word.split()[0] in r["title"].lower()]
            if rows:
                r = rows[0]
                others = [x for x in rows if x["start_time"] != r["start_time"]]
                ans = "%s is %s on %s%s." % (
                    r["title"], fmt_time(r["start_time"]) or "TBD", fmt_day_long(day),
                    (" at " + r["location"]) if r.get("location") else "")
                if r.get("precision") == "approx":
                    ans += " That time is marked approximate."
                if not r.get("confirmed"):
                    ans += " It is not confirmed yet."
                if others:
                    ans = ("I found two different %s times: %s and %s. The most recently updated row shows %s."
                           % (r["title"].lower(), fmt_time(r["start_time"]), fmt_time(others[0]["start_time"]),
                              fmt_time(sorted(rows, key=lambda x: x["updated"])[-1]["start_time"])))
                return {"answer": ans, "sources": [src("schedule", r["title"])], "found": True}
            return {"answer": "No %s has been entered for %s yet." % (word, fmt_day_long(day)),
                    "sources": [], "found": False}

    # --- hotel ------------------------------------------------------------
    if "hotel" in ql or "staying" in ql or "stay" in ql:
        rows = ctx["lodging"]
        if show:
            rows = [l for l in rows if l.get("show_id") == show["id"] or
                    (l.get("city") or "").lower().startswith((show.get("city") or "").split(",")[0].lower())]
        elif "tonight" in ql or "today" in ql:
            rows = [l for l in rows if l["checkin"] <= today and (not l["checkout"] or l["checkout"] >= today)]
        if rows:
            l = rows[0]
            bits = [l["property"]]
            if l.get("address"):
                bits.append(l["address"])
            if l.get("checkin"):
                bits.append("check-in %s" % l["checkin"])
            if l.get("confirmation"):
                bits.append("confirmation %s" % l["confirmation"])
            return {"answer": "You are staying at %s." % ", ".join(bits) +
                    ("" if l["status"] == "confirmed" else " The booking is not marked confirmed."),
                    "sources": [src("lodging", l["property"])], "found": True}
        where = show.get("city") if show else "that date"
        return {"answer": "No hotel has been entered for %s yet." % where, "sources": [], "found": False}

    # --- next flight / travel ---------------------------------------------
    if "flight" in ql or "fly" in ql or "travel" in ql or "car" in ql or "driver" in ql or "ground" in ql:
        mode = "air" if ("flight" in ql or "fly" in ql) else ("ground" if ("car" in ql or "driver" in ql or "ground" in ql) else None)
        rows = [t for t in ctx["travel"] if (mode is None or t["mode"] == mode)]
        if show:
            rows = [t for t in rows if t.get("show_id") == show["id"] or t["day_date"] == show["date"]]
        rows = [t for t in rows if t["day_date"] >= today] or rows
        if rows:
            t = sorted(rows, key=lambda x: (x["day_date"], x["dep_time"]))[0]
            label = {"air": "Flight", "ground": "Car", "bus": "Bus", "rail": "Train"}[t["mode"]]
            ans = "%s %s on %s: %s → %s%s%s." % (
                label, t.get("number") or "", fmt_day_long(t["day_date"]),
                t.get("dep_loc") or t.get("pickup") or "—", t.get("arr_loc") or t.get("destination") or "—",
                (", departing %s" % fmt_time(t["dep_time"])) if t.get("dep_time") else "",
                (" (%s)" % t["dep_tz"]) if t.get("dep_tz") else "")
            if t.get("driver") or t.get("phone"):
                ans += " Driver: %s %s." % (t.get("driver") or "", t.get("phone") or "")
            if t["status"] != "confirmed":
                ans += " Not confirmed yet."
            return {"answer": ans.replace("  ", " "), "sources": [src("travel", label)], "found": True}
        what = {"air": "flight", "ground": "Ground transportation"}.get(mode, "Travel")
        where = (" for %s" % show["city"]) if show else ""
        return {"answer": "%s%s has not been entered yet." % (what.capitalize() if what[0].islower() else what, where),
                "sources": [], "found": False}

    # --- missing / readiness ----------------------------------------------
    if "missing" in ql or "ready" in ql or "readiness" in ql:
        if show and show["id"] in ctx["readiness"]:
            r = ctx["readiness"][show["id"]]
            miss = ", ".join(i["label"].lower() for i in r["missing"]) or "nothing"
            return {"answer": "%s is %d%% ready. Missing: %s." % (show.get("city") or show["venue"], r["pct"], miss),
                    "sources": [src("readiness", show.get("city") or show["venue"])], "found": True}
        att = ctx.get("attention") or []
        if att:
            return {"answer": "Needs attention: " + "; ".join(a["text"] for a in att[:8]) + ".",
                    "sources": [src("readiness", "tour")], "found": True}
        return {"answer": "Nothing is flagged as missing right now.", "sources": [], "found": True}

    # --- what changed ------------------------------------------------------
    if "changed" in ql or "changes" in ql:
        rows = [c for c in ctx["changes"] if c["severity"] in ("important", "critical")]
        if "today" in ql:
            rows = [c for c in rows if c["created"][:10] == ctx["today_utc"]]
        if not rows:
            return {"answer": "No important changes%s." % (" today" if "today" in ql else " recorded"), "sources": [], "found": True}
        parts = ["%s %s: %s → %s" % (c["entity_label"], c["field"].replace("_", " "), c["before"] or "—", c["after"] or "—")
                 for c in rows[:6]]
        return {"answer": "; ".join(parts) + ".", "sources": [src("changes", "activity")], "found": True}

    # --- money -------------------------------------------------------------
    if "deposit" in ql:
        if not ctx.get("money_allowed"):
            return {"answer": "Financial details are not in your permissions for this tour.", "sources": [], "found": False}
        rows = [s for s in shows if (s.get("deposit_required") or "").strip() not in ("", "0")
                and not (s.get("deposit_received") or "").strip()]
        if rows:
            return {"answer": "Deposits outstanding: " + ", ".join("%s (%s)" % (s.get("city") or s["venue"], s["date"]) for s in rows) + ".",
                    "sources": [src("money", "deposits")], "found": True}
        return {"answer": "No outstanding deposits on record.", "sources": [src("money", "deposits")], "found": True}
    if "unsettled" in ql or "settle" in ql:
        if not ctx.get("money_allowed"):
            return {"answer": "Financial details are not in your permissions for this tour.", "sources": [], "found": False}
        rows = [s for s in shows if s["date"] < today and (s.get("settlement_status") or "open") != "settled"]
        if rows:
            return {"answer": "Unsettled: " + ", ".join("%s (%s)" % (s.get("city") or s["venue"], s["date"]) for s in rows) + ".",
                    "sources": [src("money", "settlement")], "found": True}
        return {"answer": "Every played show is marked settled.", "sources": [src("money", "settlement")], "found": True}
    if "net" in ql or "gross" in ql or "money" in ql or "paid" in ql:
        if not ctx.get("money_allowed"):
            return {"answer": "Financial details are not in your permissions for this tour.", "sources": [], "found": False}
        f = ctx.get("finance") or {}
        if f.get("shows_with_numbers"):
            return {"answer": "Estimated net %s %.2f across %d show%s with numbers entered (contracted guarantees %.2f, collected %.2f, outstanding %.2f)." % (
                f.get("currency", ""), f["projected_net"], f["shows_with_numbers"], "" if f["shows_with_numbers"] == 1 else "s",
                f["guarantees"], f["collected"], f["outstanding"]),
                    "sources": [src("money", "tour financials")], "found": True}
        return {"answer": "No show money has been entered yet, so there is no estimate to give.", "sources": [], "found": False}

    # --- guests ------------------------------------------------------------
    if "guest" in ql:
        target = show or next((s for s in shows if s["date"] == today), None)
        if target and target["id"] in ctx["guests"]:
            g = ctx["guests"][target["id"]]
            if g["allocation"] is None:
                return {"answer": "%s: %d guest spots used, pending %d — no allocation has been entered, so I cannot say how many remain." % (
                    target.get("city") or target["venue"], g["used"], g["pending"]), "sources": [src("guests", "guest list")], "found": True}
            return {"answer": "%s: %d of %d used, %d remaining, %d pending." % (
                target.get("city") or target["venue"], g["used"], g["allocation"], g["remaining"], g["pending"]),
                    "sources": [src("guests", "guest list")], "found": True}
        return {"answer": "There is no show tonight, and no city in the question to look up.", "sources": [], "found": False}

    # --- promoter / who ----------------------------------------------------
    if "promoter" in ql or "who is" in ql:
        if show:
            if show.get("promoter"):
                return {"answer": "The promoter in %s is %s." % (show.get("city") or show["venue"], show["promoter"]),
                        "sources": [src("show", show["venue"])], "found": True}
            adv = [a for a in ctx["advance"].get(show["id"], []) if a["item_key"] == "promoter" and a["value"]]
            if adv:
                return {"answer": "Promoter (from the advance): %s." % adv[0]["value"], "sources": [src("advance", "promoter")], "found": True}
            return {"answer": "No promoter has been entered for %s yet." % (show.get("city") or show["venue"]), "sources": [], "found": False}

    # --- photographers / assignments ---------------------------------------
    if "photograph" in ql or "videograph" in ql:
        rows = [s for s in shows if s["date"] >= today and not any(
            p["category"] in ("Photographer", "Videographer") and (not p.get("shows") or s["id"] in p["shows"])
            for p in ctx["people"])]
        if rows:
            return {"answer": "Shows without a photographer assigned: " + ", ".join(s.get("city") or s["venue"] for s in rows) + ".",
                    "sources": [src("people", "directory")], "found": True}
        return {"answer": "Every upcoming show has a photographer or videographer assigned.", "sources": [src("people", "directory")], "found": True}

    # --- itinerary ---------------------------------------------------------
    if "itinerary" in ql or "today" in ql or "schedule" in ql or "tomorrow" in ql:
        day = tomorrow if "tomorrow" in ql else today
        rows = [r for r in ctx["schedule"] if r["day_date"] == day]
        if rows:
            return {"answer": "; ".join("%s %s" % (fmt_time(r["start_time"]) or "TBD", r["title"]) for r in rows) + ".",
                    "sources": [src("schedule", fmt_day_long(day))], "found": True}
        return {"answer": "Nothing is on the schedule for %s yet." % fmt_day_long(day), "sources": [], "found": False}

    return {"answer": "I can answer about schedule times, hotels, travel, guests, deposits, settlements, readiness, changes and people. Try naming the city.",
            "sources": [], "found": False}


# --- extraction (rule-based) ------------------------------------------------

_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM|a\.m\.|p\.m\.)\b|\b(\d{1,2}):(\d{2})\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b|\b(\d{1,2})/(\d{1,2})/(20\d{2})\b|\b([A-Z][a-z]{2,8}\.? \d{1,2}(?:st|nd|rd|th)?,? 20\d{2})\b")

_TIME_KEYS = [
    ("load_in", ("load in", "load-in", "loadin", "load")),
    ("soundcheck", ("soundcheck", "sound check", "line check")),
    ("doors", ("doors",)),
    ("support", ("support", "opener", "opening act")),
    ("set", ("set time", "headline", "showtime", "show time", "artist set", "on stage", "stage time")),
    ("curfew", ("curfew",)),
    ("bus_call", ("bus call", "lobby call", "lobby")),
]
_FACT_KEYS = [
    ("hotel", ("hotel", "lodging", "accommodation", "staying at")),
    ("wifi", ("wifi", "wi-fi", "wireless", "password")),
    ("parking", ("parking", "bus park", "truck park")),
    ("catering", ("catering", "buyout", "dinner", "meal")),
    ("dressing_rooms", ("dressing room", "green room")),
    ("guest_cutoff", ("guest list", "guestlist", "comps")),
    ("settlement_location", ("settlement", "settle")),
    ("promoter", ("promoter", "buyer", "talent buyer")),
    ("venue_contact", ("production manager", "pm:", "venue contact", "day of contact", "day-of")),
    ("capacity", ("capacity", "cap:", "cap ")),
    ("driver", ("driver", "pickup", "pick-up", "pick up")),
    ("flight", ("flight", "depart", "arrive", "arrival", "departure")),
]


def _norm_time(m):
    if m.group(1):
        h = int(m.group(1)); mi = int(m.group(2) or 0)
        ap = m.group(3).lower().replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return "%02d:%02d" % (h, mi)
    return "%02d:%02d" % (int(m.group(4)), int(m.group(5)))


def extract(text):
    """Propose structured facts from pasted text. Every proposal carries
    the source line and a confidence: 'high' when a known keyword and a
    parseable value sit on the same line, 'review' otherwise. Nothing is
    written here."""
    proposals = []
    seen = set()
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    for i, line in enumerate(lines, start=1):
        ll = line.lower()
        times = list(_TIME_RE.finditer(line))
        for key, words in _TIME_KEYS:
            if any(w in ll for w in words) and times:
                val = _norm_time(times[0])
                sig = (key, val)
                if sig in seen:
                    continue
                seen.add(sig)
                proposals.append({"kind": "time", "key": key, "label": key.replace("_", " ").title(),
                                  "value": val, "display": fmt_time(val), "confidence": "high",
                                  "line": i, "source": line})
        for key, words in _FACT_KEYS:
            if any(w in ll for w in words):
                value = line
                for w in words:
                    idx = ll.find(w)
                    if idx >= 0:
                        after = line[idx + len(w):].strip(" :-–—\t")
                        if len(after) >= 2:
                            value = after
                        break
                sig = (key, value.lower()[:60])
                if sig in seen:
                    continue
                seen.add(sig)
                conf = "high" if (":" in line or "-" in line) and len(value) < 120 else "review"
                proposals.append({"kind": "fact", "key": key, "label": key.replace("_", " ").title(),
                                  "value": value[:300], "display": value[:120], "confidence": conf,
                                  "line": i, "source": line})
        for m in _EMAIL_RE.finditer(line):
            sig = ("email", m.group(0).lower())
            if sig not in seen:
                seen.add(sig)
                proposals.append({"kind": "contact", "key": "email", "label": "Email", "value": m.group(0),
                                  "display": m.group(0), "confidence": "high", "line": i, "source": line})
        for m in _PHONE_RE.finditer(line):
            digits = re.sub(r"\D", "", m.group(1))
            if 10 <= len(digits) <= 15:
                sig = ("phone", digits)
                if sig not in seen:
                    seen.add(sig)
                    proposals.append({"kind": "contact", "key": "phone", "label": "Phone",
                                      "value": m.group(1).strip(), "display": m.group(1).strip(),
                                      "confidence": "review", "line": i, "source": line})
        for m in _DATE_RE.finditer(line):
            raw = m.group(0)
            iso = _to_iso(raw)
            if iso:
                sig = ("date", iso)
                if sig not in seen:
                    seen.add(sig)
                    proposals.append({"kind": "date", "key": "date", "label": "Date", "value": iso,
                                      "display": iso, "confidence": "high" if m.group(1) else "review",
                                      "line": i, "source": line})
    high = len([p for p in proposals if p["confidence"] == "high"])
    return {"proposals": proposals, "count": len(proposals), "high": high,
            "review": len(proposals) - high, "lines": len(lines)}


def _to_iso(raw):
    raw = raw.strip()
    if re.match(r"^20\d{2}-\d{2}-\d{2}$", raw):
        return raw
    # Two-digit years are what a routing sheet actually carries — an
    # itinerary reads "10/14/26", not "10/14/2026". Windowed the usual
    # way: 69-99 is last century, 00-68 is this one. A tour date is never
    # in the 1900s in practice, but guessing forward would turn a typo
    # into a booking a year out.
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2}|20\d{2})$", raw)
    if m:
        year = int(m.group(3))
        if year < 100:
            year += 2000 if year <= 68 else 1900
        try:
            return date(year, int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            return None
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%b. %d, %Y", "%b. %d %Y"):
        try:
            cleaned = re.sub(r"(\d)(st|nd|rd|th)", r"\1", raw)
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# --- fuel and mileage -------------------------------------------------------
# A van tour's second-largest line after guarantees, and the one nobody
# has in a system. This is arithmetic over figures a person entered — no
# routing engine, no distance API, no guessing. If the miles are an
# estimate somebody typed, the result says so on every screen it reaches.

def _num(value):
    try:
        f = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def fuel_plan(tour, legs=None):
    """-> {miles, miles_source, gallons, fuel_cost, reserve, total, mpg,
    price, per_show, missing, ready}.

    `legs` is the list of drives somebody has actually entered. When they
    add up, they win: a routed total beats a planning estimate, and the
    result says which one it used. Nothing is invented — a missing figure
    comes back in `missing` and the numbers that depend on it stay None.
    """
    mpg = _num(tour.get("fuel_mpg"))
    price = _num(tour.get("fuel_price"))
    reserve_pct = _num(tour.get("fuel_reserve_pct"))
    stated = _num(tour.get("stated_miles"))

    entered = [_num(l.get("miles")) for l in (legs or [])]
    entered = [m for m in entered if m is not None and m > 0]
    routed = sum(entered) if entered else None
    # A part-entered route is worse than no route: it would read as a
    # total and be short by every leg nobody filled in.
    complete = bool(legs) and len(entered) == len(legs)

    if complete and routed:
        miles, source = routed, "routed"
    elif stated:
        miles, source = stated, "estimate"
    else:
        miles, source = None, "none"

    missing = []
    if mpg is None or mpg <= 0:
        missing.append("miles per gallon")
    if price is None or price <= 0:
        missing.append("price per gallon")
    if miles is None:
        missing.append("mileage")

    out = {"miles": miles, "miles_source": source, "mpg": mpg, "price": price,
           "reserve_pct": reserve_pct, "stated_miles": stated,
           "routed_miles": routed if entered else None,
           "legs_entered": len(entered), "legs_total": len(legs or []),
           "gallons": None, "fuel_cost": None, "reserve": None, "total": None,
           "per_show": None, "missing": missing, "ready": not missing}
    if missing:
        return out
    out["gallons"] = miles / mpg
    out["fuel_cost"] = out["gallons"] * price
    out["reserve"] = out["fuel_cost"] * ((reserve_pct or 0) / 100.0)
    out["total"] = out["fuel_cost"] + out["reserve"]
    return out


def fuel_per_show(plan, show_count):
    """Fuel divided across the dates that have to carry it. Returns None
    rather than dividing by zero on a tour with no shows yet."""
    if not plan.get("total") or not show_count:
        return None
    return plan["total"] / show_count


# --- imports ----------------------------------------------------------------

CSV_ALIASES = {
    "date": ("date", "show date", "day", "start"),
    "city": ("city", "market", "location"),
    "venue": ("venue", "venue name", "room", "hall"),
    "kind": ("type", "kind", "day type", "category"),
    "notes": ("notes", "note", "details", "description"),
    "tz": ("timezone", "tz", "time zone"),
    "promoter": ("promoter", "buyer"),
    "capacity": ("capacity", "cap"),
    # A deal sheet carries the parts of a deal. The importer reads them so
    # a tour manager does not retype 35 rows they already have.
    "status": ("status", "confirmation", "hold", "hold status"),
    "fee": ("fee", "guarantee", "money", "artist fee", "devora $$", "support $$", "$$"),
    "merch": ("merch rate", "merch", "merch split", "merchandise"),
    "ticket_url": ("ticket link", "tickets", "ticket url", "on sale link"),
    "support": ("support", "bill", "lineup", "line-up", "with", "special guests"),
}


def parse_csv_rows(text):
    """-> (rows, problems). Each row: {date, city, venue, kind, notes, tz,
    promoter, capacity}. Header aliases are matched case-insensitively."""
    rows, problems = [], []
    text = (text or "").strip()
    # A deal sheet or routing grid is copied out of a spreadsheet, which
    # puts TABS between the columns, not commas — and a venue called
    # "Chelsea's Live" or a merch rate of "90/10, 100% CD/DVD" is full of
    # commas that would tear a comma-split apart. Pick the delimiter from
    # the header line rather than assuming.
    header = text.split("\n", 1)[0]
    delim = "\t" if header.count("\t") >= 1 else (";" if header.count(";") > header.count(",") else ",")
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        raw_rows = list(reader)
    except (csv.Error, ValueError) as exc:
        return [], ["Could not read as CSV: %s" % exc]
    if not raw_rows:
        return [], ["No rows found. The first line must be a header."]
    headers = {(h or "").strip().lower(): h for h in (reader.fieldnames or [])}

    def pick(raw, key):
        for alias in CSV_ALIASES[key]:
            if alias in headers:
                return (raw.get(headers[alias]) or "").strip()
        return ""
    for i, raw in enumerate(raw_rows, start=2):
        d = pick(raw, "date")
        iso = _to_iso(d) if d else None
        if not iso:
            problems.append("Line %d: no usable date (%r)." % (i, d))
            continue
        city, venue = pick(raw, "city"), pick(raw, "venue")
        kind = (pick(raw, "kind") or "").lower()
        kind = {"travel day": "travel", "day off": "off", "off day": "off", "show": "show"}.get(kind, kind)
        if not kind:
            # A routing grid writes the day type in the CITY column —
            # "OFF" on its own line, "START" and "END" to bracket the run.
            # Read as a venue-less show, those became empty date rows.
            marker = city.strip(" *").upper()
            if marker in ("OFF", "DAY OFF", "TRAVEL", "DRIVE", "START", "END", "HOLD"):
                kind = {"TRAVEL": "travel", "DRIVE": "travel"}.get(marker, "off")
                city = ""
            else:
                kind = "show" if venue else "other"
        if kind not in ts.DAY_KINDS:
            kind = "show" if venue else "other"
        rows.append({"date": iso, "city": city, "venue": venue,
                     "kind": kind, "notes": pick(raw, "notes"), "tz": pick(raw, "tz"),
                     "promoter": pick(raw, "promoter"), "capacity": pick(raw, "capacity"),
                     "status": pick(raw, "status"), "fee": pick(raw, "fee"),
                     "merch": pick(raw, "merch"), "ticket_url": pick(raw, "ticket_url"),
                     "support": pick(raw, "support"),
                     "line": i})
    return rows, problems


def parse_ics(text):
    """Minimal VEVENT reader: DTSTART (date or datetime), SUMMARY, LOCATION,
    DESCRIPTION. Enough for a tour calendar export; says what it skipped."""
    rows, problems = [], []
    if "BEGIN:VEVENT" not in (text or ""):
        return [], ["No VEVENT blocks found."]
    # unfold continuation lines
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    for n, block in enumerate(unfolded.split("BEGIN:VEVENT")[1:], start=1):
        body = block.split("END:VEVENT")[0]
        fields = {}
        for line in body.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            fields[k.split(";")[0].upper()] = v.strip()
        dt = fields.get("DTSTART", "")
        iso = dt[:8]
        if not re.match(r"^\d{8}$", iso):
            problems.append("Event %d: unreadable DTSTART %r." % (n, dt))
            continue
        iso = "%s-%s-%s" % (iso[:4], iso[4:6], iso[6:8])
        summary = fields.get("SUMMARY", "").replace("\\,", ",")
        location = fields.get("LOCATION", "").replace("\\,", ",")
        city, venue = "", ""
        if location:
            parts = [p.strip() for p in location.split(",")]
            venue = parts[0]
            city = ", ".join(parts[1:3]) if len(parts) > 1 else ""
        kind = "show"
        sl = summary.lower()
        if any(w in sl for w in ("travel", "drive", "fly")):
            kind = "travel"
        elif "off" in sl and "day" in sl:
            kind = "off"
        elif any(w in sl for w in ("rehearsal", "production", "promo", "press")):
            kind = next(w for w in ("rehearsal", "production", "promo", "press") if w in sl)
        rows.append({"date": iso, "city": city, "venue": venue or summary, "kind": kind,
                     "notes": fields.get("DESCRIPTION", "").replace("\\n", " ")[:500], "tz": "",
                     "promoter": "", "capacity": "", "line": n})
    return rows, problems


_PASTE_RE = re.compile(
    r"^\s*(?P<date>"
    r"20\d{2}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}/(?:20\d{2}|\d{2})"
    # A month name with no year at all is what a routing email looks
    # like ("October 14 - Wednesday - ..."). The tour's own year fills
    # it in; without a tour to ask, the line is reported rather than
    # guessed at.
    r"|[A-Z][a-z]{2,8}\.? \d{1,2}(?:st|nd|rd|th)?(?:,? 20\d{2})?"
    r")\s*[-–—:|]?\s*(?P<rest>.+)$")

_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday", "mon", "tue", "tues", "wed", "thu",
             "thur", "thurs", "fri", "sat", "sun"}
# "Ticket Link:", "GA Ticket Link:", "VIP Ticket Link:" — a routing email
# puts these on their own line under the date they belong to.
_LINK_RE = re.compile(r"^\s*(?P<label>[A-Za-z ]{0,12}?)\s*ticket link\s*:\s*(?P<url>.*)$", re.I)
# "City, ST" — two letters at the end is a state, which is what tells a
# city apart from a venue when a sheet lists them in either order.
_CITY_RE = re.compile(r",\s*[A-Z]{2}\.?$")


def parse_pasted(text, default_year=None):
    """One date per line: '2026-09-12 — Nashville, The Basement' or
    '9/12/2026 Nashville | The Basement | show'.

    Also swallows the shapes a real routing sheet arrives in: two-digit
    years, tab-separated table columns, a month name with no year (which
    takes `default_year`), venue and city in either order, a bare "OFF"
    day, and "Ticket Link:" lines that belong to the date above them.
    """
    rows, problems = [], []
    for i, line in enumerate((text or "").splitlines(), start=1):
        if not line.strip():
            continue

        link = _LINK_RE.match(line)
        if link:
            # Belongs to the row above, not to a row of its own.
            url = link.group("url").strip()
            if not rows:
                problems.append("Line %d: a ticket link with no date above it." % i)
                continue
            if not url or url.startswith("**"):
                rows[-1]["ticket_pending"] = True    # "**waiting on link**"
                continue
            label = (link.group("label") or "").strip().upper()
            if label in ("VIP",) and rows[-1].get("ticket_url"):
                rows[-1].setdefault("extra_links", []).append(("VIP", url))
            elif rows[-1].get("ticket_url"):
                rows[-1].setdefault("extra_links", []).append((label or "Also", url))
            else:
                rows[-1]["ticket_url"] = url
                if label:
                    rows[-1]["ticket_label"] = label
            continue

        m = _PASTE_RE.match(line)
        if not m:
            problems.append("Line %d: no date at the start." % i)
            continue
        raw_date = m.group("date")
        if default_year and not re.search(r"\d{4}$|/\d{2}$", raw_date.strip()):
            raw_date = "%s %d" % (raw_date.rstrip(","), default_year)
        iso = _to_iso(raw_date)
        if not iso:
            problems.append("Line %d: date not understood%s." % (
                i, " — add a year" if not re.search(r"\d{4}|/\d{2}", raw_date) else ""))
            continue

        rest = m.group("rest")
        # "City, ST | Venue" / "City — Venue" / "City - Venue" split on the
        # pipe, dash or a SPACED hyphen; commas are part of a place name,
        # not a separator, unless there is no other separator and three or
        # more comma segments.
        #
        # A TAB counts too, because a table copied out of Word, Excel or
        # Google Docs arrives tab-separated — which is how most routing
        # sheets actually reach this box. Without it every line of a
        # pasted itinerary landed in "city" with the venue stuck on the
        # end of it. The hyphen must have spaces around it, or "X-Ray
        # Arcade" and "Sold-Out Room" would be torn in half.
        parts = [p.strip() for p in re.split(r"\t+|\s+-\s+|\s*[|—–]\s*", rest) if p.strip()]
        if len(parts) == 1:
            # No separator at all: fall back to commas, but only here —
            # doing it after the weekday filter re-split the raw line and
            # undid the filter, so "Wednesday - OFF" came back whole and
            # a day off was read as a show at a venue called "OFF".
            segs = [p.strip() for p in rest.split(",") if p.strip()]
            parts = [", ".join(segs[:2]), ", ".join(segs[2:])] if len(segs) >= 3 else [rest.strip()]
        # A weekday beside the date says nothing the date does not.
        parts = [p for p in parts if p.lower().strip(".,") not in _WEEKDAYS] or parts

        kind = "show"
        rl = " ".join(parts).lower()
        # A whole part that OPENS with travel/drive — "Travel to Atlanta",
        # "Drive day". Not a substring over the joined line: that turned
        # "Drive-In Theater" and any notes column mentioning a drive into a
        # venue-less travel day, and the else-branch below never assigns a
        # venue, so the show simply lost its room.
        def _is_travel(part):
            w = part.strip(" *").lower().replace("-", " ").split()
            return bool(w) and w[0] in ("travel", "drive", "driving") and (
                len(w) == 1 or w[1] in ("to", "day", "back", "north", "south", "east", "west"))
        if any(_is_travel(p) for p in parts):
            kind = "travel"
        elif any(p.strip(" *").lower() in ("off", "day off", "off day") for p in parts) \
                or "day off" in rl or "off day" in rl:
            kind = "off"

        city, venue = "", ""
        if kind == "show":
            # Sheets list these in either order. "Iowa City, IA" ends in a
            # state; "Gabe's" does not — so the state is what decides,
            # rather than the column it happened to land in.
            named = [p for p in parts if p]
            cities = [p for p in named if _CITY_RE.search(p)]
            if cities:
                city = cities[0]
                venue = next((p for p in named if p is not city), "")
            else:
                city = named[0] if named else ""
                venue = named[1] if len(named) > 1 else ""
        else:
            city = next((p for p in parts if _CITY_RE.search(p)), "")

        rows.append({"date": iso, "city": city, "venue": venue, "kind": kind, "notes": "",
                     "tz": "", "promoter": "", "capacity": "", "line": i})
    return rows, problems


def dedupe_against(rows, existing_shows, existing_days):
    """Mark each incoming row new/duplicate/conflict against what the tour
    already holds. duplicate = same date and venue; conflict = same date,
    different venue/city."""
    by_date = {}
    for s in existing_shows:
        by_date.setdefault(s["date"], []).append({"venue": s["venue"], "city": s.get("city") or "",
                                                  "kind": "show", "id": s.get("id") or ""})
    for d in existing_days:
        if not d.get("show_id"):
            by_date.setdefault(d["date"], []).append({"venue": "", "city": d.get("city") or "", "kind": d["kind"]})
    for r in rows:
        r["verdict"] = "new"
        for e in by_date.get(r["date"], []):
            if r["kind"] == "show" and e["kind"] == "show":
                if (e["venue"] or "").strip().lower() == (r["venue"] or "").strip().lower():
                    r["verdict"] = "duplicate"
                    # A re-sent deal sheet is the normal way a hold becomes
                    # a confirmation. Carrying the id lets the import fill
                    # the date in rather than only skipping it.
                    r["match_id"] = e.get("id") or ""
                    break
                r["verdict"] = "conflict"
                r["conflict_with"] = e
            elif r["kind"] != "show" and e["kind"] == r["kind"]:
                r["verdict"] = "duplicate"
                break
    return rows


# --- finance ----------------------------------------------------------------

def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip() or 0)
    except ValueError:
        return 0.0


def show_money(show, expenses):
    """Derived money for one show, every line from stored fields."""
    deal = show.get("deal_type") or "flat"
    guarantee = _num(show.get("guarantee"))
    backend_pct = _num(show.get("backend_pct"))
    adj_gross = _num(show.get("adjusted_gross")) or _num(show.get("ticket_gross"))
    backend = 0.0
    if deal in ("guarantee_vs_pct", "pct_only", "custom") and backend_pct:
        backend = round(adj_gross * backend_pct / 100, 2)
    if deal == "guarantee_vs_pct":
        earned = max(guarantee, backend)
    elif deal == "pct_only":
        earned = backend
    else:
        earned = guarantee + (_num(show.get("bonus")) if show.get("bonus") else 0)
    merch_gross = _num(show.get("merch_gross"))
    merch_net = round(merch_gross * (1 - _num(show.get("venue_merch_cut")) / 100), 2) if merch_gross else 0.0
    vip = _num(show.get("vip_gross"))
    exp_fields = sum(_num(show.get(k)) for k in ("production_expenses", "local_expenses",
                                                 "travel_allocation", "promoter_expenses"))
    exp_ledger = sum(_num(e["amount"]) for e in expenses)
    expenses_total = round(exp_fields + exp_ledger, 2)
    settlement = _num(show.get("settlement_amount"))
    collected = _num(show.get("collected")) + _num(show.get("deposit_received"))
    est_net = round(earned + merch_net + vip - expenses_total, 2)
    actual_net = round(settlement + merch_net + vip - expenses_total, 2) if settlement else None
    outstanding = round(max(0.0, (settlement or earned) - collected), 2)
    has_numbers = any(_num(show.get(k)) for k in ("guarantee", "ticket_gross", "adjusted_gross",
                                                   "settlement_amount", "merch_gross", "vip_gross")) or bool(expenses)
    return {"deal": deal, "guarantee": guarantee, "backend": backend, "earned": round(earned, 2),
            "merch_net": merch_net, "vip": vip, "expenses": expenses_total,
            "settlement": settlement, "collected": round(collected, 2),
            "outstanding": outstanding, "estimated_net": est_net, "actual_net": actual_net,
            "has_numbers": has_numbers, "deposit_outstanding": (
                _num(show.get("deposit_required")) > 0 and _num(show.get("deposit_received")) <= 0)}


def tour_finance(shows, expenses_by_show, currency, today=None):
    """`today` is the tour-local date (callers pass today_in(home_tz));
    the server's own calendar is UTC and would misfile an evening show."""
    today = today or date.today().isoformat()
    rows = []
    for s in shows:
        m = show_money(s, expenses_by_show.get(s["id"], []))
        m["show"] = s
        rows.append(m)
    with_numbers = [r for r in rows if r["has_numbers"]]
    total = lambda key: round(sum(r[key] for r in with_numbers), 2)
    nets = [r for r in with_numbers if r["estimated_net"] is not None]
    best = max(nets, key=lambda r: r["estimated_net"]) if nets else None
    worst = min(nets, key=lambda r: r["estimated_net"]) if nets else None
    return {
        "currency": currency, "rows": rows, "shows_with_numbers": len(with_numbers),
        "projected_gross": total("earned") + total("merch_net") + total("vip"),
        "guarantees": total("guarantee"), "projected_backend": total("backend"),
        "collected": total("collected"), "outstanding": total("outstanding"),
        "deposits_outstanding": len([r for r in rows if r["deposit_outstanding"]]),
        "expenses": total("expenses"), "merch": total("merch_net"), "vip": total("vip"),
        "projected_net": total("estimated_net"),
        "actual_net": round(sum(r["actual_net"] for r in with_numbers if r["actual_net"] is not None), 2),
        "avg_net": round(total("estimated_net") / len(with_numbers), 2) if with_numbers else 0.0,
        "best": best, "worst": worst,
        "unsettled": [r for r in rows if (r["show"].get("settlement_status") or "open") != "settled"
                      and r["show"]["date"] < today],
    }


# --- exports ----------------------------------------------------------------

def csv_text(header, rows):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return out.getvalue()


def ics_text(tour, shows, days, schedule):
    """One VEVENT per day (all-day) plus timed VEVENTs for schedule rows that
    have a time and a zone. Honest about the zone: TZID is only emitted
    when the row has one."""
    def esc(s):
        return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Street Banker//TOUR//EN",
             "X-WR-CALNAME:%s" % esc(tour["name"])]
    show_by_id = {s["id"]: s for s in shows}
    for d in days:
        show = show_by_id.get(d.get("show_id") or "")
        title = show["venue"] if show else (d.get("title") or d["kind"].title())
        if d.get("city"):
            title = "%s — %s" % (d["city"], title)
        lines += ["BEGIN:VEVENT", "UID:sbtour-day-%s@streetbanker" % d["id"],
                  "DTSTART;VALUE=DATE:%s" % d["date"].replace("-", ""),
                  "SUMMARY:%s" % esc(title),
                  "DESCRIPTION:%s" % esc(d.get("notes") or ""), "END:VEVENT"]
    for it in schedule:
        show = show_by_id.get(it.get("show_id") or "")
        tz = (show or {}).get("tz") or tour.get("home_tz") or ""
        if it["start_time"] and re.match(r"^\d{2}:\d{2}$", it["start_time"]):
            stamp = "%sT%s00" % (it["day_date"].replace("-", ""), it["start_time"].replace(":", ""))
            dtline = ("DTSTART;TZID=%s:%s" % (tz, stamp)) if valid_tz(tz) else ("DTSTART:%s" % stamp)
            lines += ["BEGIN:VEVENT", "UID:sbtour-item-%s@streetbanker" % it["id"], dtline,
                      "SUMMARY:%s" % esc(it["title"]),
                      "LOCATION:%s" % esc(it.get("location") or ""), "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
