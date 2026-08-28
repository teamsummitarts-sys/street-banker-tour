"""The vault counts files, or it counts nothing.

The page these replace showed "Vault Completeness 34%", five songs and
nineteen missing documents to every account, from _DOCUMENT_PRESENCE.
Uploading a real split sheet moved none of it. These hold the new
contract: the numbers come from the documents table, and an upload
changes them.
"""

import io
import uuid

from app import create_app


def _fresh_client(app_obj=None):
    app_obj = app_obj or create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "D",
                                 "email": "doc%s@x.com" % uuid.uuid4().hex[:8],
                                 "password": "secret1", "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    return client


def _upload_statement(client):
    csv_data = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"Midnight Drive,Spotify,120.50,2026-04\n"
                b"Neon Dreams,Spotify,60.00,2026-05\n")
    return client.post("/statements",
                       data={"statement": (io.BytesIO(csv_data), "s.csv")},
                       content_type="multipart/form-data")


def _upload_doc(client, name="split.pdf", doc_type="Split Agreement", track=""):
    return client.post("/documents",
                       data={"document": (io.BytesIO(b"%PDF-1.4 signed"), name),
                             "doc_type": doc_type, "track": track,
                             "note": "test"},
                       content_type="multipart/form-data")


def test_empty_vault_shows_no_invented_completeness():
    client = _fresh_client()
    body = client.get("/documents").get_data(as_text=True)
    assert "34%" not in body
    assert "Songs Tracked" not in body
    # No recordings named: a percentage would have no denominator.
    assert "No recordings named yet" in body
    assert "Nothing stored yet" in body


def test_tracks_come_from_the_accounts_own_statements():
    client = _fresh_client()
    _upload_statement(client)
    body = client.get("/documents").get_data(as_text=True)
    assert "Paperwork by Recording" in body
    assert "Midnight Drive" in body and "Neon Dreams" in body
    # Two recordings, three asked-for documents each, none uploaded.
    assert "0 of 6 asked for" in body


def test_uploading_a_document_moves_the_coverage():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    _upload_statement(client)
    import documents_engine
    with app_obj.app_context():
        with client.session_transaction() as sess:
            uid = sess["user_id"]
        before = documents_engine.build(uid)
        assert before["coverage_pct"] == 0
    _upload_doc(client, track="Midnight Drive")
    with app_obj.app_context():
        after = documents_engine.build(uid)
    assert after["covered_slots"] == 1
    assert after["total_slots"] == 6
    assert after["coverage_pct"] == 17
    entry = next(e for e in after["entries"] if e["title"] == "Midnight Drive")
    assert entry["missing_count"] == 2
    assert "Split Agreement" not in entry["missing"]


def test_catalog_wide_paperwork_is_not_held_against_a_track():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    _upload_statement(client)
    _upload_doc(client, name="distro.pdf", doc_type="Distribution", track="")
    import documents_engine
    with app_obj.app_context():
        with client.session_transaction() as sess:
            view = documents_engine.build(sess["user_id"])
    assert view["covered_slots"] == 0
    assert view["catalog_missing"] == ["Publishing", "Registration"]
    assert len(view["unfiled"]) == 1
    body = client.get("/documents").get_data(as_text=True)
    assert "Filed to the whole catalog" in body


def test_a_document_filed_against_an_unknown_title_is_flagged():
    client = _fresh_client()
    _upload_statement(client)
    _upload_doc(client, name="ghost.pdf", track="Song That Does Not Exist")
    body = client.get("/documents").get_data(as_text=True)
    assert "no longer names" in body
    assert "Song That Does Not Exist" in body


def test_coverage_is_scoped_not_claimed_as_clean_rights():
    client = _fresh_client()
    _upload_statement(client)
    body = client.get("/documents").get_data(as_text=True)
    assert "not a legal opinion" in body
    assert "invisible to this page" in body
