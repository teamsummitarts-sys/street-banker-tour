import os
import tempfile


def _client(monkeypatch):
    root = tempfile.mkdtemp(prefix="reach-opportunity-")
    monkeypatch.setenv("REACH_DB_PATH", os.path.join(root, "reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY", "test-reach-key")

    import app as app_module

    return app_module.create_app().test_client()


def test_opportunity_detail_uses_public_product_hierarchy(monkeypatch):
    client = _client(monkeypatch)
    client.post("/reach/unlock", data={"key": "test-reach-key"})

    from reach import campaigns, catalog, entities, profile

    with client.application.app_context():
        recording_id = catalog.add_track({
            "title": "Signal Test",
            "artist_name": "Public Artist",
        })
        catalog.attest_rights(recording_id)
        profile_id = profile.get_or_create(recording_id)
        profile.set_field(profile_id, "primary_genre", "alternative")
        profile.set_field(profile_id, "microgenres", ["indie electronic"])
        profile.set_field(profile_id, "mood", ["cinematic"])
        profile.set_field(profile_id, "language", "en")
        profile.set_field(profile_id, "comparable_artists", ["Reference Artist"])
        campaign_id = campaigns.create(recording_id, name="Signal Test Campaign")
        outlet_id = entities.ensure_outlet(
            "Public Radio Test",
            "https://example.test/music",
            "example.test",
            "RADIO",
            description="Independent new music outlet.",
            territory="US",
        )
        target_id = campaigns.add_target(
            campaign_id,
            outlet_id,
            status=campaigns.QUALIFIED,
        )

    page = client.get(f"/reach/campaigns/{campaign_id}/targets/{target_id}")
    assert page.status_code == 200
    assert b"Public Radio Test" in page.data
    assert b"Why this is a strong fit" in page.data
    assert b"Recent activity &amp; evidence" in page.data
    assert b"Relationship memory" in page.data
    assert b"Write a personalized pitch" in page.data
    assert b"Submission route &amp; contact" in page.data
    assert b"Safety &amp; outreach decision" in page.data
    assert b"deadline" not in page.data.lower()
