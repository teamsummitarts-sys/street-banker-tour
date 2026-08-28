"""The bill for a date, and a line check for each act on it.

Built for the PRAYERS / DEVORA package tour, where five acts share a stage
every night and the running order is what load-in, line checks, changeovers
and set times all hang off. It changes show to show, which is why it lives on
the SHOW and not the tour.

The tests that matter are the ones about not losing work: re-ordering a bill
is an everyday act, and losing four advanced line checks because one opener
was added is what makes somebody go back to a spreadsheet.
"""
import uuid

import pytest

import db as store
import tour_engine as eng
import tour_store as ts

ACTS = ["CHRIZ AMAYA", "HALLOWS", "EX LOVER", "DEVORA", "PRAYERS"]


@pytest.fixture(scope="module")
def application():
    import app as appmod
    return appmod.app


@pytest.fixture
def tour_show(application):
    """A real tour with one real date from the itinerary.

    The account is made through /signup rather than store.create_user, which
    takes a password HASH and its arguments in a different order - so a test
    that called it directly would build an account nobody can log into.
    """
    email = "lineup-%s@example.net" % uuid.uuid4().hex[:8]
    client = application.test_client()
    client.post("/signup", data={"name": "Tour Manager", "email": email,
                                 "password": "lu-pass-123"})
    client.post("/login", data={"email": email, "password": "lu-pass-123"})

    with application.app_context():
        user = store.get_user_by_email(email)
        tour_id = ts.create_tour(user["id"], {"name": "No Tengo Calma Tour 2026",
                                              "artist_name": "PRAYERS"})
        show_id = store.add_tour_show(user["id"], "2026-10-17", "Bottom Lounge",
                                      "Chicago, IL", "")
        ts.attach_show(tour_id, show_id, "America/Chicago")

    yield {"user_id": user["id"], "email": email, "client": client,
           "tour_id": tour_id, "show_id": show_id}


def _bill(tour_show, acts=None):
    return ts.set_lineup(tour_show["tour_id"], tour_show["show_id"], acts or ACTS)


def _advance(application, tour_show, times):
    rows = ts.list_lineup(tour_show["tour_id"], tour_show["show_id"])
    for row, when in zip(rows, times):
        if when:
            ts.update_lineup_act(tour_show["tour_id"], tour_show["show_id"],
                                 row["id"], {"line_check": when})
    return ts.list_lineup(tour_show["tour_id"], tour_show["show_id"])


# --- the bill --------------------------------------------------------------

def test_the_bill_is_stored_in_running_order(application, tour_show):
    with application.app_context():
        rows = _bill(tour_show)
    assert [r["act_name"] for r in rows] == ACTS
    assert [r["running_order"] for r in rows] == [1, 2, 3, 4, 5]


def test_the_closer_is_the_headliner_by_default(application, tour_show):
    with application.app_context():
        rows = _bill(tour_show)
    assert rows[-1]["is_headliner"]
    assert sum(r["is_headliner"] for r in rows) == 1


def test_duplicate_acts_are_collapsed(application, tour_show):
    with application.app_context():
        rows = _bill(tour_show, ["DEVORA", "devora", "PRAYERS"])
    assert len(rows) == 2


def test_the_comma_bill_is_kept_in_step(application, tour_show):
    """The band share link and the printed day sheet read tour_show_ext
    .support. A second source of truth that disagrees is worse than the
    string alone: the band would see one running order and production
    another, on the same day, from the same tool."""
    with application.app_context():
        _bill(tour_show)
        show = ts.get_show(tour_show["tour_id"], tour_show["show_id"])
    assert show["support"] == ", ".join(ACTS)


def test_an_existing_comma_bill_seeds_the_view_once(application, tour_show):
    """A tour that already has a running order must not appear to have lost
    it the first time somebody opens the new panel."""
    with application.app_context():
        ts.update_show_ext(tour_show["tour_id"], tour_show["show_id"],
                           {"support": "HALLOWS, DEVORA, PRAYERS"})
        show = ts.get_show(tour_show["tour_id"], tour_show["show_id"])
        seeded = ts.seed_lineup_from_support(tour_show["tour_id"], show)
        again = ts.seed_lineup_from_support(tour_show["tour_id"], show)

    assert [r["act_name"] for r in seeded] == ["HALLOWS", "DEVORA", "PRAYERS"]
    assert len(again) == 3, "seeding twice must not duplicate the bill"


# --- not losing advanced work ----------------------------------------------

def test_reordering_keeps_every_advanced_time(application, tour_show):
    """The everyday act on a package tour. Losing four line checks because
    the order changed is what sends somebody back to a spreadsheet."""
    with application.app_context():
        _bill(tour_show)
        _advance(application, tour_show, ["16:00", "16:20", "16:40", "17:00", "17:30"])

        reordered = ts.set_lineup(tour_show["tour_id"], tour_show["show_id"],
                                  ["HALLOWS", "CHRIZ AMAYA", "EX LOVER",
                                   "DEVORA", "PRAYERS"])

    by_name = {r["act_name"]: r["line_check"] for r in reordered}
    assert by_name["CHRIZ AMAYA"] == "16:00"
    assert by_name["HALLOWS"] == "16:20"
    assert all(by_name[name] for name in ACTS), "an advanced time was lost"


def test_adding_an_act_keeps_the_others(application, tour_show):
    with application.app_context():
        _bill(tour_show)
        _advance(application, tour_show, ["16:00", "16:20", "16:40", "17:00", "17:30"])
        rows = ts.set_lineup(tour_show["tour_id"], tour_show["show_id"],
                             ACTS + ["LOCAL OPENER"])

    assert len(rows) == 6
    assert len([r for r in rows if r["line_check"]]) == 5


# --- the warnings ----------------------------------------------------------

def test_a_fully_advanced_bill_in_order_warns_about_nothing(application, tour_show):
    with application.app_context():
        _bill(tour_show)
        rows = _advance(application, tour_show,
                        ["16:00", "16:20", "16:40", "17:00", "17:30"])
        assert ts.lineup_warnings(rows) == []


def test_times_running_backwards_are_flagged(application, tour_show):
    """After a re-order the times can run backwards against the new order,
    and nobody spots that in a list sorted by order with the times as plain
    text."""
    with application.app_context():
        _bill(tour_show)
        _advance(application, tour_show, ["16:00", "16:20", "16:40", "17:00", "17:30"])
        rows = ts.set_lineup(tour_show["tour_id"], tour_show["show_id"],
                             ["HALLOWS", "CHRIZ AMAYA", "EX LOVER",
                              "DEVORA", "PRAYERS"])
        warnings = ts.lineup_warnings(rows)

    assert any("need swapping" in w for w in warnings)


def test_an_un_advanced_act_is_named(application, tour_show):
    with application.app_context():
        _bill(tour_show)
        rows = _advance(application, tour_show, ["16:00", "16:20", "16:40", "17:00", ""])
        warnings = ts.lineup_warnings(rows)

    assert any("PRAYERS" in w and "No line check yet" in w for w in warnings)


def test_warnings_use_the_same_clock_as_the_rest_of_the_product(application, tour_show):
    """Every time in this product renders as '5:00 PM'. A warning saying
    '17:00' beside a field showing '05:00 PM' reads as a different time."""
    with application.app_context():
        _bill(tour_show)
        _advance(application, tour_show, ["16:00", "16:20", "16:40", "17:00", "17:30"])
        rows = ts.set_lineup(tour_show["tour_id"], tour_show["show_id"],
                             ["HALLOWS", "CHRIZ AMAYA", "EX LOVER",
                              "DEVORA", "PRAYERS"])
        warnings = ts.lineup_warnings(rows, fmt_time=eng.fmt_time)

    joined = " ".join(warnings)
    assert "4:00 PM" in joined
    assert "16:00" not in joined


# --- the day sheet ---------------------------------------------------------

def test_only_advanced_line_checks_reach_the_day_sheet(application, tour_show):
    """A line check nobody has advanced is not a 16:00 line check, and a day
    sheet that says otherwise sends somebody to the venue at the wrong time."""
    with application.app_context():
        _bill(tour_show)
        _advance(application, tour_show, ["16:00", "16:20", "16:40", "", ""])
        show = ts.get_show(tour_show["tour_id"], tour_show["show_id"])
        added = ts.lineup_schedule_items(tour_show["tour_id"],
                                         tour_show["user_id"], show)
        items = ts.list_schedule(tour_show["tour_id"], show_id=tour_show["show_id"])

    assert added == 3
    assert len(items) == 3
    assert all("line check" in i["title"] for i in items)


def test_putting_them_on_the_day_sheet_twice_does_not_duplicate(application, tour_show):
    with application.app_context():
        _bill(tour_show)
        _advance(application, tour_show, ["16:00", "16:20", "16:40", "17:00", "17:30"])
        show = ts.get_show(tour_show["tour_id"], tour_show["show_id"])
        ts.lineup_schedule_items(tour_show["tour_id"], tour_show["user_id"], show)
        again = ts.lineup_schedule_items(tour_show["tour_id"],
                                         tour_show["user_id"], show)
    assert again == 0


# --- over HTTP -------------------------------------------------------------

def test_a_form_id_cannot_reach_another_shows_bill(application, tour_show):
    """The lineup id arrives in a field name, so it is checked against this
    show's own bill rather than trusted."""
    with application.app_context():
        other_show = store.add_tour_show(tour_show["user_id"], "2026-10-18",
                                         "Zanzabar", "Louisville, KY", "")
        ts.attach_show(tour_show["tour_id"], other_show, "")
        victim = ts.set_lineup(tour_show["tour_id"], other_show, ["SOMEBODY ELSE"])[0]
        _bill(tour_show)

    tour_show["client"].post("/tours/%s/shows/%s/lineup/times"
                % (tour_show["tour_id"], tour_show["show_id"]),
                data={"line_check:%s" % victim["id"]: "23:59"})

    with application.app_context():
        after = ts.list_lineup(tour_show["tour_id"], other_show)[0]
    assert after["line_check"] == "", "a form id reached another show's row"
