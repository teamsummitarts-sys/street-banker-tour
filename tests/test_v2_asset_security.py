"""V2 contract for owned uploads.

Private business files must not inherit the anonymous ``/uploads`` policy
used by public campaign artwork.  These tests exercise the HTTP boundary,
not just the database flags.
"""

import io
import os
import uuid

from app import create_app
import db as store


def _account(app_obj, prefix):
    client = app_obj.test_client()
    email = "%s-%s@example.com" % (prefix, uuid.uuid4().hex[:8])
    client.post("/signup", data={
        "name": prefix.title(), "email": email, "password": "secret1",
        "account_type": "artist",
    })
    client.post("/plan/switch", data={"plan": "pro"})
    return client, store.get_user_by_email(email)


def test_private_document_is_owner_only_at_raw_and_canonical_urls():
    app_obj = create_app()
    owner_client, owner = _account(app_obj, "doc-owner")
    other_client, _other = _account(app_obj, "doc-other")

    owner_client.post("/documents", data={
        "document": (io.BytesIO(b"%PDF-1.4 private"), "contract.pdf"),
        "doc_type": "Producer Agreement",
    }, content_type="multipart/form-data")
    document = store.list_documents(owner["id"])[0]
    asset = store.get_stored_asset(document["path"])

    assert asset["user_id"] == owner["id"]
    assert asset["visibility"] == "private"
    assert owner_client.get(document["path"]).status_code == 200
    assert owner_client.get("/media/" + asset["id"]).status_code == 200
    assert other_client.get(document["path"]).status_code == 404
    assert other_client.get("/media/" + asset["id"]).status_code == 404
    assert app_obj.test_client().get(document["path"]).status_code == 404


def test_private_vault_file_is_owner_only_but_token_share_still_streams():
    app_obj = create_app()
    owner_client, owner = _account(app_obj, "vault-owner")
    upload = owner_client.post("/vault/upload", data={
        "file": (io.BytesIO(b"RIFF private master"), "master.wav"),
        "kind": "master", "label": "Private master",
    }, content_type="multipart/form-data").get_json()
    path = upload["path"]
    vault_file = next(v for v in store.list_vault_files(owner["id"])
                      if v["path"] == path)

    assert store.get_stored_asset(path)["visibility"] == "private"
    assert app_obj.test_client().get(path).status_code == 404

    owner_client.post("/epk/share", data={
        "action": "save", "audio": [vault_file["id"]],
    })
    share = store.get_epk_share(owner["id"])
    anonymous = app_obj.test_client()
    room = anonymous.get("/pitch/" + share["token"])
    assert room.status_code == 200
    assert "/pitch/%s/media/0" % share["token"] in room.get_data(as_text=True)
    assert anonymous.get("/pitch/%s/media/0" % share["token"]).data == b"RIFF private master"


def test_epk_asset_and_smart_link_cover_remain_public():
    app_obj = create_app()
    client, owner = _account(app_obj, "campaign-owner")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64

    epk = client.post("/epk/asset/logo", data={
        "asset": (io.BytesIO(png), "logo.png"),
    }, content_type="multipart/form-data").get_json()
    assert store.get_stored_asset(epk["path"])["visibility"] == "public"
    assert app_obj.test_client().get(epk["path"]).status_code == 200

    response = client.post("/links/new", data={
        "title": "Public cover", "cover_file": (io.BytesIO(png), "cover.png"),
    }, content_type="multipart/form-data")
    import links_store as campaigns
    campaign_id = response.headers["Location"].split("/")[2]
    cover = campaigns.get_campaign(campaign_id)["cover_url"]
    assert store.get_stored_asset(cover)["user_id"] == owner["id"]
    assert store.get_stored_asset(cover)["visibility"] == "public"
    assert app_obj.test_client().get(cover).status_code == 200


def test_epk_visibility_updates_the_http_boundary():
    app_obj = create_app()
    client, _owner = _account(app_obj, "epk-private")
    png = b"\x89PNG\r\n\x1a\n" + b"1" * 64
    path = client.post("/epk/asset/logo", data={
        "asset": (io.BytesIO(png), "logo.png"),
    }, content_type="multipart/form-data").get_json()["path"]

    assert app_obj.test_client().get(path).status_code == 200
    client.post("/epk/asset/logo/visibility", json={"public": False})
    assert store.get_stored_asset(path)["visibility"] == "private"
    assert app_obj.test_client().get(path).status_code == 404
    assert client.get(path).status_code == 200


def test_existing_private_rows_are_backfilled_on_init():
    user_id = uuid.uuid4().hex
    path = "/uploads/pre-v2-contract.pdf"
    with store.get_db() as db:
        db.execute(
            "INSERT INTO users (id,email,name,password_hash,created) VALUES (?,?,?,?,?)",
            (user_id, "%s@example.com" % user_id, "Legacy", "x", "2026-01-01"),
        )
        db.execute(
            "INSERT INTO documents (id,user_id,filename,path,doc_type,note,track,created) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, user_id, "old.pdf", path, "Agreement", "", "",
             "2026-01-01"),
        )
        db.execute("DELETE FROM stored_assets WHERE path = ?", (path,))

    store.init_db()
    asset = store.get_stored_asset(path)
    assert asset["user_id"] == user_id
    assert asset["visibility"] == "private"


def test_staging_refuses_an_unregistered_legacy_upload(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("SECRET_KEY", "test-only-staging-secret")
    app_obj = create_app()
    uploads = os.path.join(os.path.dirname(store.db_path()), "uploads")
    os.makedirs(uploads, exist_ok=True)
    with open(os.path.join(uploads, "unregistered.txt"), "wb") as fh:
        fh.write(b"must not leak")
    assert app_obj.test_client().get("/uploads/unregistered.txt").status_code == 404


def test_private_remote_media_never_uses_the_public_cdn(monkeypatch):
    import blob_store

    app_obj = create_app()
    client, owner = _account(app_obj, "remote-owner")
    asset = store.register_stored_asset(owner["id"], "r2:masters/private.wav",
                                        "private", "vault")
    monkeypatch.setattr(blob_store, "configured", lambda: True)
    monkeypatch.setattr(blob_store, "presigned_get",
                        lambda key, ttl=300: "https://signed.invalid/" + key)
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://public.invalid")

    response = client.get("/media/" + asset["id"])
    assert response.status_code == 302
    assert response.headers["Location"] == "https://signed.invalid/masters/private.wav"
