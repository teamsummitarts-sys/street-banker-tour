import os
import tempfile


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-debrief-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")
    import app as app_module
    client = app_module.create_app().test_client()
    client.post("/reach/unlock", data={"key": "test-reach-key"})
    return client


def _campaign():
    from reach import campaigns, catalog, profile
    recording_id = catalog.add_track({"title": "Debrief Single", "artist_name": "Debrief Artist"})
    catalog.attest_rights(recording_id)
    profile_id = profile.get_or_create(recording_id)
    profile.set_field(profile_id, "primary_genre", "alternative")
    profile.set_field(profile_id, "microgenres", ["indie electronic"])
    profile.set_field(profile_id, "mood", ["cinematic"])
    profile.set_field(profile_id, "language", "en")
    profile.set_field(profile_id, "comparable_artists", ["Reference One"])
    return campaigns.create(recording_id, name="Debrief Campaign")


def _sent_target(campaign_id, index, response_kind=None, rejection_reason=None):
    from reach import campaigns, clock, db, entities, rbac
    outlet_id = entities.ensure_outlet(
        f"Debrief Blog {index}",
        f"https://debrief{index}.example/submit",
        f"debrief{index}.example",
        "BLOG",
        territory="US",
    )
    target_id = campaigns.add_target(campaign_id, outlet_id, status=campaigns.SENT)
    principal = rbac.current_principal()
    submission_id = db.new_id("sub")
    db.insert("submission", {
        "id": submission_id, "tenant_id": principal.tenant_id,
        "target_id": target_id, "route_id": None, "approval_id": None,
        "method": "EMAIL", "provider": "test", "provider_message_id": None,
        "payload_hash": f"payload-{index}", "status": "DELIVERED", "cost": 0.0,
        "sent_at": clock.now_iso(), "recorded_by": principal.id, "error": None,
        "created_at": clock.now_iso(),
    })
    if response_kind:
        db.insert("response", {
            "id": db.new_id("resp"), "tenant_id": principal.tenant_id,
            "target_id": target_id, "submission_id": submission_id,
            "kind": response_kind,
            "sentiment": "POSITIVE" if response_kind == "ACCEPT" else "NEGATIVE",
            "body_excerpt": None, "received_at": clock.now_iso(),
            "recorded_by": principal.id, "created_at": clock.now_iso(),
        })
    if rejection_reason:
        db.update("campaign_target", target_id, {"rejection_reason": rejection_reason})
    return target_id


def test_debrief_stays_empty_until_campaign_has_activity(monkeypatch):
    client = _client(monkeypatch)
    with client.application.app_context():
        from reach import campaign_debrief
        campaign_id = _campaign()
        report = campaign_debrief.build(campaign_id)
        assert report["has_activity"] is False
        assert report["metrics"]["submitted"] == 0


def test_debrief_reports_observed_patterns_without_causal_claim(monkeypatch):
    client = _client(monkeypatch)
    with client.application.app_context():
        from reach import campaign_debrief
        campaign_id = _campaign()
        _sent_target(campaign_id, 1, response_kind="ACCEPT")
        _sent_target(campaign_id, 2, response_kind="DECLINE", rejection_reason="Not a genre fit")
        _sent_target(campaign_id, 3, rejection_reason="Not a genre fit")

        report = campaign_debrief.build(campaign_id)
        assert report["has_activity"] is True
        assert report["metrics"]["submitted"] == 3
        assert report["metrics"]["responses"] == 2
        blog = next(row for row in report["channels"] if row["label"] == "BLOG")
        assert blog["sent"] == 3
        assert blog["responses"] == 2
        assert blog["response_rate"] == 67
        assert report["relationship_wins"][0]["accepts"] == 1
        assert report["rejections"][0]["reason"] == "Not a genre fit"
        assert report["rejections"][0]["n"] == 2
        assert any(item["kind"] == "observed_channel" for item in report["carry_forward"])
        assert "does not claim" in report["disclaimer"]


def test_debrief_page_and_flight_plan_link_render(monkeypatch):
    client = _client(monkeypatch)
    with client.application.app_context():
        campaign_id = _campaign()
        _sent_target(campaign_id, 1, response_kind="ACCEPT")

    page = client.get(f"/reach/campaigns/{campaign_id}/debrief")
    assert page.status_code == 200
    assert b"Campaign Debrief" in page.data
    assert b"Measured learning" in page.data
    assert b"Observed by outlet type" in page.data
    assert b"does not claim" in page.data

    overview = client.get(f"/reach/campaigns/{campaign_id}")
    assert overview.status_code == 200
    assert b"Debrief" in overview.data
    assert f"/reach/campaigns/{campaign_id}/debrief".encode() in overview.data
