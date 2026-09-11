import os
import tempfile


def _client(monkeypatch):
    root=tempfile.mkdtemp(prefix="reach-ask-")
    monkeypatch.setenv("REACH_DB_PATH",os.path.join(root,"reach.db"))
    monkeypatch.setenv("REACH_ACCESS_KEY","test-reach-key")
    import app as app_module
    client=app_module.create_app().test_client()
    client.post("/reach/unlock",data={"key":"test-reach-key"})
    return client


def _campaign_with_opportunity():
    from reach import campaigns,catalog,entities,profile
    recording_id=catalog.add_track({"title":"Ask Track","artist_name":"Ask Artist"})
    catalog.attest_rights(recording_id)
    profile_id=profile.get_or_create(recording_id)
    profile.set_field(profile_id,"primary_genre","alternative")
    profile.set_field(profile_id,"microgenres",["indie electronic"])
    profile.set_field(profile_id,"mood",["cinematic"])
    profile.set_field(profile_id,"language","en")
    profile.set_field(profile_id,"comparable_artists",["Reference One"])
    campaign_id=campaigns.create(recording_id,name="Ask Campaign")
    outlet_id=entities.ensure_outlet("Ask Music Blog","https://askblog.example/submit","askblog.example","BLOG",territory="US")
    target_id=campaigns.add_target(campaign_id,outlet_id,status=campaigns.QUALIFIED)
    return campaign_id,target_id


def test_ask_reach_empty_state_is_grounded(monkeypatch):
    client=_client(monkeypatch)
    page=client.get("/reach/ask")
    assert page.status_code==200
    assert b"Ask Reach" in page.data
    assert b"Answers come from Reach records" in page.data
    assert b"What should I do today?" in page.data


def test_dashboard_ask_controls_open_ask_reach_but_radar_stays_radar(monkeypatch):
    client=_client(monkeypatch)
    page=client.get("/reach/")
    assert page.status_code==200
    html=page.get_data(as_text=True)
    assert 'class="r6-mobile-search" href="/reach/ask"' in html
    assert 'class="r6-search" href="/reach/ask"' in html
    assert 'href="/reach/opportunities"' in html
    assert '>Radar<' in html


def test_ask_reach_returns_real_opportunity(monkeypatch):
    client=_client(monkeypatch)
    with client.application.app_context():
        campaign_id,target_id=_campaign_with_opportunity()
    page=client.get("/reach/ask",query_string={"q":"show my best opportunities"})
    assert page.status_code==200
    assert b"Ask Music Blog" in page.data
    assert f"/reach/campaigns/{campaign_id}/targets/{target_id}".encode() in page.data

    data=client.get("/reach/ask.json",query_string={"q":"best opportunities"})
    payload=data.get_json()
    assert data.status_code==200
    assert payload["ok"] is True
    assert payload["intent"]=="opportunities"
    assert payload["items"][0]["target_id"]==target_id


def test_ask_reach_searches_owned_records_and_does_not_invent(monkeypatch):
    client=_client(monkeypatch)
    with client.application.app_context():
        _campaign_with_opportunity()

    found=client.get("/reach/ask.json",query_string={"q":"Ask Music Blog"}).get_json()
    assert found["intent"]=="search"
    assert any(item["label"]=="Ask Music Blog" for item in found["items"])

    missing=client.get("/reach/ask.json",query_string={"q":"Definitely Not A Real Reach Record"}).get_json()
    assert missing["intent"]=="search"
    assert missing["items"]==[]
    assert "does not have a matching record" in missing["answer"]
