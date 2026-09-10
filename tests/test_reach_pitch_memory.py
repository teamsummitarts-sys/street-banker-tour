import os
import tempfile


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-pitch-memory-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")
    import app as app_module
    client = app_module.create_app().test_client()
    client.post("/reach/unlock", data={"key": "test-reach-key"})
    return client


def _campaign(title, artist="Memory Artist"):
    from reach import campaigns, catalog, profile

    recording_id = catalog.add_track({"title": title, "artist_name": artist})
    catalog.attest_rights(recording_id)
    profile_id = profile.get_or_create(recording_id)
    profile.set_field(profile_id, "primary_genre", "alternative")
    profile.set_field(profile_id, "microgenres", ["indie electronic"])
    profile.set_field(profile_id, "mood", ["cinematic"])
    profile.set_field(profile_id, "language", "en")
    profile.set_field(profile_id, "comparable_artists", ["Reference One"])
    return campaigns.create(recording_id, name=f"{title} campaign")


def _target(campaign_id, outlet_id):
    from reach import campaigns
    return campaigns.add_target(campaign_id, outlet_id, status=campaigns.QUALIFIED)


def _insert_sent_pitch(target_id, subject, body, sent_at="2026-08-01T12:00:00+00:00", response_kind=None):
    from reach import campaigns, clock, db, rbac

    principal = rbac.current_principal()
    target = campaigns.get_target(target_id)
    draft_id = db.new_id("draft")
    db.insert("outreach_draft", {
        "id": draft_id,
        "tenant_id": principal.tenant_id,
        "target_id": target_id,
        "recipient_preview": "editor@…",
        "recipient_hash": "hash-" + draft_id,
        "subject": subject,
        "body": body,
        "links_json": "[]",
        "attachments_json": "[]",
        "language": "en",
        "translation_flagged": 0,
        "facts_json": "[]",
        "generator_version": "test",
        "payload_hash": "payload-" + draft_id,
        "status": "SENT",
        "created_at": sent_at,
        "updated_at": sent_at,
    })
    approval_id = db.new_id("apr")
    db.insert("approval", {
        "id": approval_id,
        "tenant_id": principal.tenant_id,
        "draft_id": draft_id,
        "target_id": target_id,
        "approved_by": principal.id,
        "approved_at": sent_at,
        "payload_hash": "payload-" + draft_id,
        "cost": 0.0,
        "invalidated_at": None,
        "invalidation_reason": None,
    })
    submission_id = db.new_id("sub")
    db.insert("submission", {
        "id": submission_id,
        "tenant_id": principal.tenant_id,
        "target_id": target_id,
        "route_id": None,
        "approval_id": approval_id,
        "method": "EMAIL",
        "provider": "test",
        "provider_message_id": None,
        "payload_hash": "payload-" + draft_id,
        "status": "DELIVERED",
        "cost": 0.0,
        "sent_at": sent_at,
        "recorded_by": principal.id,
        "error": None,
        "created_at": sent_at,
    })
    if response_kind:
        db.insert("response", {
            "id": db.new_id("resp"),
            "tenant_id": principal.tenant_id,
            "target_id": target_id,
            "submission_id": submission_id,
            "kind": response_kind,
            "sentiment": "POSITIVE" if response_kind == "ACCEPT" else "NEGATIVE",
            "body_excerpt": None,
            "received_at": clock.now_iso(),
            "recorded_by": principal.id,
            "created_at": clock.now_iso(),
        })
    return draft_id


def test_pitch_memory_recalls_prior_sent_pitch_and_warns_on_reuse(monkeypatch):
    client = _client(monkeypatch)
    from reach import entities, pitch_memory

    with client.application.app_context():
        outlet_id = entities.ensure_outlet(
            "Memory Outlet", "https://memory.example/submit", "memory.example", "BLOG"
        )
        old_campaign = _campaign("Old Single")
        old_target = _target(old_campaign, outlet_id)
        _insert_sent_pitch(
            old_target,
            "Submission — Memory Artist — Old Single",
            "Hello Memory Outlet, I am writing because you cover indie electronic music. Please consider this cinematic alternative track.",
            response_kind="ACCEPT",
        )

        current_campaign = _campaign("New Single")
        current_target = _target(current_campaign, outlet_id)
        memory = pitch_memory.summary(current_target, {
            "subject": "Submission — Memory Artist — New Single",
            "body": "Hello Memory Outlet, I am writing because you cover indie electronic music. Please consider this cinematic alternative track.",
        })

        assert memory["prior_pitch_count"] == 1
        assert memory["history"][0]["recording_title"] == "Old Single"
        assert memory["positive_count"] == 1
        assert memory["warning"] is not None
        assert memory["warning"]["level"] in ("MEDIUM", "HIGH")


def test_pitch_memory_does_not_mix_unrelated_outlets(monkeypatch):
    client = _client(monkeypatch)
    from reach import entities, pitch_memory

    with client.application.app_context():
        first = entities.ensure_outlet("First Outlet", "https://first.example/", "first.example", "BLOG")
        second = entities.ensure_outlet("Second Outlet", "https://second.example/", "second.example", "BLOG")
        old_campaign = _campaign("History Track")
        _insert_sent_pitch(_target(old_campaign, first), "First subject", "First body")
        current_campaign = _campaign("Current Track")
        current_target = _target(current_campaign, second)
        assert pitch_memory.summary(current_target)["prior_pitch_count"] == 0


def test_pitch_memory_pages_render_inside_opportunity_flow(monkeypatch):
    client = _client(monkeypatch)
    from reach import entities

    with client.application.app_context():
        outlet_id = entities.ensure_outlet(
            "Visible Memory Outlet", "https://visible-memory.example/", "visible-memory.example", "BLOG"
        )
        campaign_id = _campaign("Visible Track")
        target_id = _target(campaign_id, outlet_id)

    detail = client.get(f"/reach/campaigns/{campaign_id}/targets/{target_id}")
    assert detail.status_code == 200
    assert b"Pitch Memory" in detail.data
    assert b"Open full Pitch Memory" in detail.data

    page = client.get(f"/reach/campaigns/{campaign_id}/targets/{target_id}/pitch-memory")
    assert page.status_code == 200
    assert b"Outlet memory" in page.data
    assert b"No prior sent pitch is recorded" in page.data

    data = client.get(f"/reach/campaigns/{campaign_id}/targets/{target_id}/pitch-memory.json")
    assert data.status_code == 200
    assert data.get_json()["prior_pitch_count"] == 0
