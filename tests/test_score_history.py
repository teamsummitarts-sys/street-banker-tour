"""Scores over time.

The point of this module is that "no comparison yet" and "no movement"
are different answers, and the difference matters to whoever reads it. A
first-day artist shown "+0" concludes nothing is working; the truth is
that nothing has been compared.
"""
import score_history as sh


def _rows(*totals, start="2026-07-31"):
    """Newest first, one per day, counting backwards - the shape
    db.score_trend returns."""
    import datetime
    d0 = datetime.date.fromisoformat(start)
    return [{"total": t, "day": (d0 - datetime.timedelta(days=i)).isoformat()}
            for i, t in enumerate(totals)]


# --- one reading is not a trend ------------------------------------------

def test_a_single_reading_has_no_delta():
    assert sh.delta(_rows(62)) is None


def test_no_readings_at_all_has_no_delta():
    assert sh.delta([]) is None


def test_a_single_reading_says_tracking_started():
    s = sh.summarise("trust", _rows(62))
    assert s["delta"] is None
    assert "Tracking from today" in s["note"]
    # And it must not imply stasis.
    assert s["phrase"] is None


# --- movement ------------------------------------------------------------

def test_an_improving_score_reads_as_up():
    d = sh.delta(_rows(66, 64, 62))
    assert d["direction"] == "up" and d["change"] == 4
    assert d["now"] == 66 and d["before"] == 62


def test_a_falling_score_reads_as_down():
    d = sh.delta(_rows(58, 60, 62))
    assert d["direction"] == "down" and d["change"] == -4
    assert d["abs_change"] == 4


def test_genuinely_unchanged_is_flat_not_absent():
    d = sh.delta(_rows(62, 62, 62))
    assert d["direction"] == "flat" and d["change"] == 0
    # Distinct from None: this artist has history and has not moved.
    assert d is not None


# --- the comparison window ----------------------------------------------

def test_the_window_bounds_the_comparison():
    # 10 readings, 7-day window: compares against the 7th, not the 10th.
    d = sh.delta(_rows(70, 69, 68, 67, 66, 65, 64, 50, 40, 30), days=7)
    assert d["before"] == 64


def test_a_short_history_compares_against_all_of_it():
    """Someone who last opened the app a month ago should still get a
    comparison rather than nothing."""
    d = sh.delta(_rows(70, 40), days=7)
    assert d["before"] == 40 and d["change"] == 30


# --- refusing to divide by nothing --------------------------------------

def test_percent_is_omitted_when_the_baseline_is_zero():
    d = sh.delta(_rows(4, 0))
    assert d["change"] == 4
    assert d["pct"] is None      # not an infinite improvement


def test_percent_is_given_when_it_means_something():
    assert sh.delta(_rows(60, 50))["pct"] == 20


# --- bad data does not become a trend -----------------------------------

def test_non_numeric_readings_are_dropped():
    rows = [{"total": None, "day": "2026-07-31"},
            {"total": 60, "day": "2026-07-30"},
            {"total": 50, "day": "2026-07-29"}]
    d = sh.delta(rows)
    assert d["now"] == 60 and d["before"] == 50


def test_a_row_that_is_all_junk_yields_nothing():
    assert sh.delta([{"total": "x", "day": "d"}]) is None


# --- what a page renders -------------------------------------------------

def test_the_sparkline_runs_oldest_to_newest():
    assert sh.sparkline(_rows(3, 2, 1)) == [1, 2, 3]


def test_the_phrase_names_the_score_and_the_movement():
    p = sh.phrase("trust", sh.delta(_rows(66, 62)))
    assert "Trust Score" in p and "up" in p and "4" in p


def test_one_point_is_singular():
    assert "1 point since" in sh.phrase("trust", sh.delta(_rows(63, 62)))


def test_every_kind_has_a_human_label():
    for kind in sh.KINDS:
        assert sh.KINDS[kind] and sh.KINDS[kind] != kind


# --- against a real database --------------------------------------------
# These call db directly rather than through a route, so nothing has
# initialised the schema for them. A new TABLE is created by init_db's
# CREATE TABLE IF NOT EXISTS on any existing install - unlike a new
# COLUMN, which needs an explicit ALTER.

def _db():
    import db as store
    store.init_db()
    return store


def test_recording_twice_in_a_day_updates_rather_than_appends():
    """These scores recompute on every page load. Appending would write
    hundreds of identical rows a day and drown the signal."""
    store = _db()
    uid = "sh-test-user"
    store.record_score(uid, "trust", 60)
    store.record_score(uid, "trust", 64)
    rows = store.score_trend(uid, "trust")
    assert len(rows) == 1
    assert rows[0]["total"] == 64          # last write of the day stands


def test_the_detail_blob_survives_the_round_trip():
    store = _db()
    uid = "sh-test-detail"
    store.record_score(uid, "capital", 55, {"income_total": 2290.0,
                                            "periods": 3})
    rows = store.score_trend(uid, "capital")
    assert rows[0]["detail"]["periods"] == 3
    assert rows[0]["detail"]["income_total"] == 2290.0


def test_a_bad_total_is_ignored_rather_than_stored():
    store = _db()
    uid = "sh-test-junk"
    store.record_score(uid, "trust", None)
    store.record_score(uid, "trust", "not a number")
    store.record_score(uid, "trust", float("nan"))
    assert store.score_trend(uid, "trust") == []


def test_kinds_stay_separate():
    store = _db()
    uid = "sh-test-kinds"
    store.record_score(uid, "trust", 60)
    store.record_score(uid, "qualification", 70)
    assert len(store.score_trend(uid, "trust")) == 1
    assert store.score_trend(uid, "qualification")[0]["total"] == 70
    assert set(store.all_score_trends(uid)) == {"trust", "qualification"}


def test_computing_a_score_records_it():
    """The engines call record_score themselves, so any page that shows a
    score also builds its history - no route has to remember to."""
    import trust_score
    store = _db()
    user = store.get_user_by_email("demo@streetbanker.io")
    if user is None:                      # suite ordering
        return
    before = len(store.score_trend(user["id"], "trust"))
    trust_score.calculate(user["id"])
    after = store.score_trend(user["id"], "trust")
    assert len(after) >= max(before, 1)
    assert after[0]["total"] == trust_score.calculate(user["id"])["total"]


# --- the page shows the movement ----------------------------------------

def test_the_qualification_page_states_its_history():
    """A stored score nobody sees is the same failure as an unstored one."""
    import app as app_mod
    application = app_mod.create_app()
    client = application.test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    body = client.get("/qualification").get_data(as_text=True)
    # First view of the day: either it has history and says how it moved,
    # or it has none and says tracking has started. Never silence.
    assert ("Tracking from today" in body
            or "Qualification Score" in body)


def test_viewing_the_page_builds_the_history():
    import app as app_mod
    import db as store
    application = app_mod.create_app()
    client = application.test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    client.get("/qualification")
    user = store.get_user_by_email("demo@streetbanker.io")
    rows = store.score_trend(user["id"], "qualification")
    assert rows and rows[0]["total"] is not None
    # And the category breakdown rode along, so a per-category trend is
    # possible later without a second migration.
    assert rows[0]["detail"].get("categories")


# --- all four score pages report their movement -------------------------

def _client():
    import app as app_mod
    application = app_mod.create_app()
    c = application.test_client()
    c.post("/login", data={"email": "demo@streetbanker.io",
                           "password": "sweep"})
    return c


_MOVEMENT = ("Tracking from today", "point since", "points since",
             "unchanged at")


def test_the_computed_scores_state_their_history():
    """A score that is stored and never shown is the same failure as one
    that was never stored. These three compute on every view, so there is
    always a reading and always something to say."""
    c = _client()
    for path in ("/qualification", "/trust-score", "/capital-score"):
        body = c.get(path).get_data(as_text=True)
        assert any(m in body for m in _MOVEMENT), path


def test_valuation_states_its_history_once_there_is_one():
    """Valuation is different: it only exists where statements do. With
    none, the page correctly says nothing rather than inventing a zero -
    so this uploads one first."""
    import io as _io
    c = _client()
    csv = 'title,source,amount,period\nVal A,Spotify,410.00,2026-04\nVal B,Apple Music,260.00,2026-05\n'
    c.post("/statements",
           data={"statement": (_io.BytesIO(csv.encode()), "val.csv")},
           content_type="multipart/form-data")
    c.get("/command-center")          # this is what records the valuation
    body = c.get("/valuation").get_data(as_text=True)
    assert any(m in body for m in _MOVEMENT)


def test_all_four_share_one_partial():
    """Four copies of the same markup drift apart. One include does not."""
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("qualification", "trust_score", "capital_score",
                 "valuation"):
        t = io.open(os.path.join(here, "templates", name + ".html"),
                    encoding="utf8").read()
        assert 'include "partials/score_trend.html"' in t, name


def test_the_partial_renders_nothing_without_history():
    """A brand-new account should see no badge at all rather than a zero
    that reads as failure."""
    from jinja2 import Environment, FileSystemLoader
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = Environment(loader=FileSystemLoader(os.path.join(here, "templates")))
    tpl = env.get_template("partials/score_trend.html")
    assert tpl.render(trend=None).strip() == ""
    assert tpl.render(trend={"phrase": None, "note": None}).strip() == ""


def test_a_falling_score_is_not_styled_as_an_error():
    """Down is information, not a broken thing. It must not borrow the
    error red."""
    from jinja2 import Environment, FileSystemLoader
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = Environment(loader=FileSystemLoader(os.path.join(here, "templates")))
    out = env.get_template("partials/score_trend.html").render(
        trend={"phrase": "Trust Score down 3 points since 2026-07-24, now 59.",
               "note": None,
               "delta": {"direction": "down", "change": -3, "pct": -5}})
    assert "▼" in out
    assert "text-red-300" in out          # muted, not the error red
    assert "text-red-500" not in out
