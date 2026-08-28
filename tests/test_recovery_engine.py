"""/recovery is the artist's own statements, or it is nothing.

The page it replaced showed every account the same $3,301.38 on the day
they signed up. These tests hold the two things that must stay true: an
account with no statements is told it has not been scanned (not that it
is clean), and an account with statements sees figures that trace back
to its own rows.
"""

import io
import uuid

from app import create_app


def _fresh_client(app_obj=None):
    app_obj = app_obj or create_app()
    client = app_obj.test_client()
    email = "rec%s@x.com" % uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "R", "email": email,
                                 "password": "secret1", "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})  # /recovery is a paid page
    return client


_CSV = (b"Track Title,Store,Net Revenue,Sales Period\n"
        b"Midnight Drive,Spotify,120.50,2026-04\n"
        b"Midnight Drive,Apple Music,80.25,2026-05\n"
        b"Neon Dreams,Spotify,60.00,2026-05\n"
        b",Spotify,12.40,2026-05\n")


def _user_id(client):
    with client.session_transaction() as sess:
        return sess["user_id"]


def _upload(client, data=_CSV):
    return client.post("/statements",
                       data={"statement": (io.BytesIO(data), "s.csv")},
                       content_type="multipart/form-data")


def test_empty_account_is_told_it_was_not_scanned():
    client = _fresh_client()
    body = client.get("/recovery").get_data(as_text=True)
    assert "Nothing scanned yet" in body
    assert "Upload a statement" in body
    # No seed figures, and no claim that the account is clean.
    assert "3,301.38" not in body
    assert "1,731.34" not in body
    assert "No missing royalties" not in body


def test_findings_come_from_the_uploaded_rows():
    client = _fresh_client()
    _upload(client)
    body = client.get("/recovery").get_data(as_text=True)
    # The untitled $12.40 row is actual money with no track on it.
    assert "Unattributed revenue" in body and "12.40" in body
    assert "ACTUAL" in body.upper()
    # Neon Dreams earns on Spotify only; Apple Music is the silent source.
    assert "Neon Dreams" in body and "Apple Music" in body
    assert "4 statement rows" in body


def test_engine_separates_actual_money_from_estimates():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    _upload(client)
    import recovery_engine
    with app_obj.app_context():
        view = recovery_engine.build(_user_id(client))
    assert view["has_data"] is True
    assert view["actual_unattributed"] == 12.40
    assert view["estimated_gaps"] > 0
    assert view["total_at_stake"] == round(
        view["actual_unattributed"] + view["estimated_gaps"], 2)
    kinds = {f["kind"]: f for f in view["findings"]}
    assert kinds["unattributed"]["basis"] == "Actual"
    assert kinds["unattributed"]["confidence"] == "High"
    assert kinds["coverage_gap"]["basis"] == "Estimate"
    # Actual findings sort above estimates - the strongest claim leads.
    assert view["findings"][0]["basis"] == "Actual"


def test_empty_account_engine_state_is_empty_not_zero_confident():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    import recovery_engine
    with app_obj.app_context():
        view = recovery_engine.build(_user_id(client))
    assert view["has_data"] is False
    assert view["findings"] == []
    assert view["total_at_stake"] == 0.0


def test_overview_card_does_not_quote_a_figure_before_any_upload():
    client = _fresh_client()
    body = client.get("/overview").get_data(as_text=True)
    assert "Not scanned" in body
    assert "3,301.38" not in body


def test_overview_card_switches_to_the_accounts_own_scan():
    client = _fresh_client()
    _upload(client)
    body = client.get("/overview").get_data(as_text=True)
    assert "From your statements" in body
    assert "12.40" in body


def test_scan_endpoint_is_per_account():
    client = _fresh_client()
    empty = client.post("/scan/missing-royalties").get_json()
    assert empty["ok"] is True and empty["count"] == 0
    assert empty["total_estimated"] == 0.0
    _upload(client)
    scanned = client.post("/scan/missing-royalties").get_json()
    assert scanned["count"] >= 2
    assert any(f["issue_type"] == "Unattributed revenue"
               and f["estimated_value"] == 12.40
               for f in scanned["findings"])


def test_a_finding_opens_a_real_case_and_the_page_says_so():
    client = _fresh_client()
    _upload(client)
    client.post("/royalty-recovery/cases/from-finding",
                data={"title": "Unattributed revenue on Spotify",
                      "category": "unmatched", "amount": "12.40"})
    body = client.get("/recovery").get_data(as_text=True)
    assert "Case open" in body
    assert "In pipeline" in body


def test_clean_statements_get_a_scoped_all_clear():
    client = _fresh_client()
    _upload(client, b"Track Title,Store,Net Revenue,Sales Period\n"
                    b"Only Song,Spotify,50.00,2026-04\n"
                    b"Only Song,Apple Music,25.00,2026-04\n")
    body = client.get("/recovery").get_data(as_text=True)
    assert "Clean sweep on what you have uploaded" in body
    # Scoped: it does not claim anything about sources never uploaded.
    assert "sources you have not uploaded" in body
