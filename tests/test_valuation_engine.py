"""A valuation is a multiple of income, so it needs income on record.

The page these replace annualised get_earnings_trend() - Jan 800 through
Jun 3200, hardcoded - which meant a brand-new account was quoted a
five-figure catalog value and a suggested advance before it had uploaded
anything. These hold the line: no statements, no figure; thin history,
said out loud; and every number traceable to the account's own months.
"""

import io
import uuid

from app import create_app


_CSV = (b"Track Title,Store,Net Revenue,Sales Period\n"
        b"Midnight Drive,Spotify,100.00,2026-01\n"
        b"Midnight Drive,Apple Music,50.00,2026-02\n"
        b"Neon Dreams,Spotify,150.00,2026-03\n")


def _fresh_client(app_obj=None):
    app_obj = app_obj or create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "V",
                                 "email": "val%s@x.com" % uuid.uuid4().hex[:8],
                                 "password": "secret1", "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})  # /valuation is a paid page
    return client


def _user_id(client):
    with client.session_transaction() as sess:
        return sess["user_id"]


def _upload(client, data=_CSV):
    return client.post("/statements",
                       data={"statement": (io.BytesIO(data), "s.csv")},
                       content_type="multipart/form-data")


def test_no_statements_means_no_valuation_figure():
    client = _fresh_client()
    body = client.get("/valuation").get_data(as_text=True)
    assert "No income on record to value" in body
    # The showcase's annualised curve is $31,000/yr at 4x. None of it here.
    assert "Suggested Advance" not in body
    assert "124,000" not in body and "31,000" not in body


def test_valuation_is_the_accounts_own_months():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    _upload(client)
    import valuation_engine
    with app_obj.app_context():
        view = valuation_engine.build(_user_id(client))
    assert view["has_data"] is True
    assert view["months"] == 3
    assert view["tracked_total"] == 300.00
    assert view["monthly_avg"] == 100.00
    assert view["annualized"] == 1200.00
    # 3x/4x/5x, the same range report_builder's CSV quotes.
    assert view["value"] == {"low": 3600, "mid": 4800, "high": 6000}
    # The range is the artist's own worst and best month, not a model.
    assert view["month_low"] == 50.00 and view["month_high"] == 150.00
    labels = {f["label"]: f for f in view["forecast"]}
    assert labels["Worst month on record"]["y1"] == 600.00
    assert labels["Best month on record"]["y1"] == 1800.00


def test_page_renders_those_numbers():
    client = _fresh_client()
    _upload(client)
    body = client.get("/valuation").get_data(as_text=True)
    assert "3 statement months" in body
    assert "4,800" in body          # mid multiple on the real run rate
    assert "2026-01" in body        # the months it averaged
    assert "Best month on record" in body


def test_thin_history_is_labelled_not_smoothed():
    client = _fresh_client()
    _upload(client, b"Track Title,Store,Net Revenue,Sales Period\n"
                    b"One Song,Spotify,500.00,2026-01\n")
    body = client.get("/valuation").get_data(as_text=True)
    assert "Thin history" in body
    # It still annualises - it just refuses to do it quietly.
    assert "6,000" in body


def test_statements_with_no_dates_cannot_produce_a_run_rate():
    client = _fresh_client()
    _upload(client, b"Track Title,Store,Net Revenue\n"
                    b"One Song,Spotify,500.00\n")
    body = client.get("/valuation").get_data(as_text=True)
    assert "no dates on it" in body
    assert "Annualised run rate" not in body


def test_advance_figures_come_from_capital_engine():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    _upload(client)
    import capital_engine
    import valuation_engine
    with app_obj.app_context():
        uid = _user_id(client)
        view = valuation_engine.build(uid)
        assert view["advance"] == capital_engine.advance_eligibility(uid)
    body = client.get("/valuation").get_data(as_text=True)
    assert "Indicative range" in body
    assert "not an offer" in body


def test_value_drivers_are_measured_not_invented():
    client = _fresh_client()
    _upload(client)
    body = client.get("/valuation").get_data(as_text=True)
    assert "What Would Move This Number" in body
    # The old drivers carried hardcoded payoffs.
    assert "28,650" not in body and "4,820" not in body
    assert "of 6 months" in body


def test_overview_drops_the_showcases_week_for_real_accounts():
    """The strip survived - see test_since_engine - but none of the
    constants it used to quote did."""
    client = _fresh_client()
    body = client.get("/overview").get_data(as_text=True)
    assert "482.15" not in body
    assert "New payouts received" not in body
    assert "Tasks completed" not in body
