"""Reports have to be files.

POST /reports/<id>/generate used to return a made-up filename and the
page displayed "Ready: royalty-report-20260801.pdf" with nothing behind
it and nowhere to click. These tests hold the line that the name in the
response corresponds to bytes the user can actually download.
"""
import io
from datetime import date

import pytest

import db as store
import report_builder
from app import create_app
from royalty_data import REPORT_TYPES

STATEMENT = (
    "Track,Source,Period,Territory,Amount\n"
    "Night Bus,Spotify,2026-05,US,412.55\n"
    "Night Bus,Apple Music,2026-05,US,180.10\n"
    "Night Bus,Spotify,2026-06,GB,395.20\n"
    "Cold Hallway,Spotify,2026-05,US,88.40\n"
    "Cold Hallway,Spotify,2026-06,US,102.15\n"
    ",YouTube,2026-06,US,54.90\n"          # paid, never attributed
)

_n = [0]


def _pro_account(with_data=False):
    """/reports is a pro-tier page; the gate is not what is under test."""
    app = create_app()
    client = app.test_client()
    _n[0] += 1
    email = "rep%d@example.com" % _n[0]
    client.post("/signup", data={"name": "Rep %d" % _n[0], "email": email,
                                 "password": "reppw12345"})
    user = store.get_user_by_email(email)
    store.set_user_plan(user["id"], "pro")
    if with_data:
        r = client.post("/statements", data={
            "statement": (io.BytesIO(STATEMENT.encode()), "may-june.csv")},
            content_type="multipart/form-data")
        assert r.status_code == 302, "statement upload failed"
        assert store.get_statement_rows(user["id"]), "no rows ingested"
    return client, user


@pytest.mark.parametrize("report_id", [r["id"] for r in REPORT_TYPES])
def test_an_empty_account_gets_a_reason_not_a_filename(report_id):
    """A report with nothing behind it is not an empty report, it is a
    misleading one - an empty Missing Money Report reads as 'nothing is
    missing'."""
    client, _ = _pro_account()
    body = client.post("/reports/%s/generate" % report_id).get_json()
    assert body is not None, "response was not JSON"
    assert body["ok"] is False
    assert body.get("error"), "refused without saying why"
    assert len(body["error"]) > 25, "reason is too terse to act on"


@pytest.mark.parametrize("report_id", [r["id"] for r in REPORT_TYPES])
def test_every_report_downloads_real_bytes(report_id):
    client, _ = _pro_account(with_data=True)
    body = client.post("/reports/%s/generate" % report_id).get_json()
    assert body["ok"] is True, body.get("error")
    rep = body["report"]

    assert rep["filename"].endswith(".csv")
    assert rep["download"], "no download link"

    got = client.get(rep["download"])
    assert got.status_code == 200
    assert "attachment" in got.headers.get("Content-Disposition", "")
    assert rep["filename"] in got.headers["Content-Disposition"]
    text = got.get_data(as_text=True)
    assert text.count("\n") >= 2, "file has no rows under its header"
    assert not text.lstrip().startswith("<"), "served HTML, not a CSV"


def test_the_declared_format_matches_what_arrives():
    """The catalogue said PDF and XLSX while producing nothing at all."""
    client, _ = _pro_account(with_data=True)
    for r in REPORT_TYPES:
        rep = client.post("/reports/%s/generate" % r["id"]).get_json()["report"]
        assert rep["filename"].lower().endswith("." + r["format"].lower()), (
            "%s is advertised as %s but downloads as %s"
            % (r["id"], r["format"], rep["filename"]))


def test_the_royalty_report_carries_the_users_own_rows():
    client, user = _pro_account(with_data=True)
    text = client.get("/reports/royalty-report/download").get_data(as_text=True)
    assert "Night Bus" in text and "Cold Hallway" in text
    assert "412.55" in text
    # Not somebody else's catalogue.
    assert "Midnight Drive" not in text


def test_missing_money_finds_the_unattributed_row_and_the_gap():
    client, _ = _pro_account(with_data=True)
    text = client.get(
        "/reports/missing-money-report/download").get_data(as_text=True)
    assert "Unattributed row" in text and "54.90" in text
    # Cold Hallway earns on Spotify but never on Apple Music.
    assert "Coverage gap" in text and "Cold Hallway" in text
    # An estimate must say it is one.
    assert "estimate" in text.lower()


def test_download_requires_a_login():
    app = create_app()
    r = app.test_client().get("/reports/royalty-report/download")
    assert r.status_code in (302, 401, 402), \
        "reports built from a user's statements must not be public"


def test_build_is_deterministic_for_a_given_day():
    client, user = _pro_account(with_data=True)
    name, body, reason = report_builder.build(
        "royalty-report", user["id"], today=date(2026, 1, 2))
    assert reason is None
    assert name == "royalty-report-20260102.csv"
    again = report_builder.build(
        "royalty-report", user["id"], today=date(2026, 1, 2))
    assert again[1] == body


def test_an_unknown_report_is_refused():
    client, user = _pro_account(with_data=True)
    name, body, reason = report_builder.build("not-a-report", user["id"])
    assert name is None and body is None and reason
