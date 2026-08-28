"""Street Banker Signal: access, tenancy, providers, scoring, evidence and
the hand-off to the Operator Desk."""
import uuid
from datetime import date, timedelta

import pytest

import app as appmod
import db as store
import signal_ingest as ingest
import signal_providers as providers
import signal_scoring as scoring
import signal_store as sstore

PASSWORD = "signal-pass-123"


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _user(flask_app, label="Scout", role="owner", org=None):
    email = "sig-%s@example.net" % uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/signup", data={"name": label, "email": email, "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})
    user = store.get_user_by_email(email)
    org = org or sstore.default_org()
    if role:
        sstore.upsert_member(org["id"], email, label, role, user_id=user["id"])
    return client, user, org


@pytest.fixture(scope="module")
def seeded(flask_app):
    """One deterministic mock universe for the whole module."""
    providers.reset_registry(providers.ProviderRegistry(adapters=[]))
    ingest.refresh_universe(max_artists=12, force=True)
    return True


# --- access -----------------------------------------------------------------

def test_signal_is_behind_the_login_wall(flask_app):
    anon = flask_app.test_client()
    r = anon.get("/signal")
    assert r.status_code in (301, 302) and "/login" in r.headers.get("Location", "")


def test_a_login_without_a_seat_is_refused(flask_app):
    client, user, org = _user(flask_app, "No Seat", role=None)
    r = client.get("/signal")
    assert r.status_code == 403
    body = r.get_data(as_text=True)
    assert "do not have access" in body
    # and it says nothing about what is inside
    assert "Breaking Now" not in body and "Momentum" not in body


def test_roles_gate_actions_server_side(flask_app, seeded):
    """A viewer may look and nothing else - enforced by the decorator, not by
    hiding buttons."""
    client, user, org = _user(flask_app, "Viewer Only", role="viewer")
    assert client.get("/signal").status_code == 200
    artist_id = sstore.list_artists(limit=1)[0]["id"]
    assert client.post("/signal/artist/%s/watch" % artist_id).status_code == 403
    assert client.post("/signal/artist/%s/operator-desk" % artist_id).status_code == 403
    assert client.get("/signal/admin/data-sources").status_code == 403
    # a scout may watch and push, but not administer providers
    scout, _, _ = _user(flask_app, "A Scout", role="scout")
    assert scout.post("/signal/artist/%s/watch" % artist_id).status_code in (302, 303)
    assert scout.get("/signal/admin/data-sources").status_code == 403


def test_access_is_a_roster_row_not_a_name_in_code():
    """The brief names three people; the standing rule forbids hardcoding
    anyone. Membership must be data."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("signal_hub.py", "signal_store.py", "signal_scoring.py",
                 "signal_ingest.py", "signal_providers.py"):
        src = (root / name).read_text(encoding="utf-8")
        low = src.lower()
        for forbidden in ("warren", "javon", "jovan", " lj ", "ljs"):
            assert forbidden not in low, "%s hardcodes %r" % (name, forbidden)


def test_a_desk_seat_carries_into_signal(flask_app):
    """Nobody is granted access by name - an Operator Desk seat is mirrored
    into Signal with the mapped role."""
    import desk_store
    email = "desk-carry-%s@example.net" % uuid.uuid4().hex[:6]
    desk_store.add_user(email, "Desk Person", "admin")
    org = sstore.default_org()
    sstore.sync_desk_roster(org["id"])
    m = sstore.get_member(org["id"], email)
    assert m is not None and m["role"] == "admin" and m["source"] == "desk"


# --- tenancy ----------------------------------------------------------------

def test_one_organisation_never_sees_another_s_work(flask_app, seeded):
    """Watchlists, mandates, alerts and desk links are tenant-owned. The
    shared intelligence layer is not - that split is deliberate."""
    org_b_id = sstore.create_org("Rival Records", "rival-records-%s" % uuid.uuid4().hex[:6])
    org_b = [o for o in sstore.list_orgs() if o["id"] == org_b_id][0]
    a_client, _, org_a = _user(flask_app, "Org A Owner", role="owner")
    b_client, b_user, _ = _user(flask_app, "Org B Owner", role=None)
    sstore.upsert_member(org_b["id"], b_user["email"], "Org B Owner", "owner")

    artist_id = sstore.list_artists(limit=1)[0]["id"]
    a_client.post("/signal/artist/%s/watch" % artist_id, data={"watchlist": "A secret list"})
    sstore.create_mandate(org_a["id"], "A private mandate", {"genres": "rock"}, "Org A Owner")
    sstore.raise_alert(org_a["id"], "momentum_above", "A private alert", artist_id=artist_id)

    assert sstore.watch_items(org_b["id"]) == []
    assert sstore.list_mandates(org_b["id"]) == []
    assert sstore.list_alerts(org_b["id"]) == []
    assert sstore.list_desk_links(org_b["id"]) == []
    # and org A's own rows are there, so the assertions above mean something
    assert len(sstore.watch_items(org_a["id"])) >= 1
    assert any(m["name"] == "A private mandate" for m in sstore.list_mandates(org_a["id"]))

    # cross-tenant ids are refused, not silently honoured
    a_mandate = sstore.list_mandates(org_a["id"])[0]
    assert sstore.get_mandate(org_b["id"], a_mandate["id"]) is None
    assert sstore.delete_mandate(org_b["id"], a_mandate["id"]) is False
    assert sstore.get_mandate(org_a["id"], a_mandate["id"]) is not None
    a_item = sstore.watch_items(org_a["id"])[0]
    assert sstore.remove_watch_item(org_b["id"], a_item["id"]) is False


# --- providers --------------------------------------------------------------

def test_the_product_runs_with_no_credentials():
    reg = providers.ProviderRegistry(adapters=[])
    assert reg.is_demo() is True
    for cap in providers.ALL_CAPABILITIES:
        assert reg.for_capability(cap) is not None, cap


def test_real_adapters_declare_themselves_but_stay_inert(monkeypatch):
    """An unconfigured adapter reports why, and never answers with a guess."""
    for cls in (providers.SoundchartsAdapter, providers.ChartmetricAdapter,
                providers.MLCAdapter, providers.SoundExchangeAdapter):
        p = cls()
        assert p.configured() is False
        h = p.health_check()
        assert h["configured"] is False and h["detail"]
        assert p.capabilities, "%s declares no capabilities" % p.key
        with pytest.raises(NotImplementedError):
            p.get_artist("anything")


def test_a_configured_adapter_is_preferred_over_the_mock(monkeypatch):
    monkeypatch.setenv("SOUNDCHARTS_ENABLED", "1")
    monkeypatch.setenv("SOUNDCHARTS_APP_ID", "id")
    monkeypatch.setenv("SOUNDCHARTS_API_KEY", "key")
    reg = providers.ProviderRegistry(adapters=[providers.SoundchartsAdapter()])
    assert reg.is_demo() is False
    assert reg.for_capability(providers.CAP_METRICS).key == "soundcharts"
    # a capability it does not claim still falls back rather than failing
    assert reg.for_capability(providers.CAP_RIGHTS).key == "mock"


def test_a_failing_provider_degrades_and_is_recorded(flask_app):
    class Broken(providers.MockMusicIntelligenceAdapter):
        key = "broken"

        def get_artist_cities(self, provider_artist_id, start, end):
            raise RuntimeError("upstream on fire")

    reg = providers.ProviderRegistry(adapters=[], mock=Broken(count=2))
    before = len(sstore.provider_usage())
    artist_id = ingest.ingest_artist("mock-a01", reg=reg)
    assert artist_id, "a failing capability must not abort the whole ingest"
    runs = sstore.provider_usage()
    assert any(r["provider"] == "broken" for r in runs)
    assert any(r["error_rate"] > 0 for r in runs if r["provider"] == "broken")


# --- entities and scoring ---------------------------------------------------

def test_the_same_provider_artist_resolves_to_one_canonical_row():
    a1 = sstore.upsert_artist("mock", "dupe-1", {"name": "Ivy Vance", "genre": "Pop"})
    a2 = sstore.upsert_artist("mock", "dupe-1", {"name": "Ivy Vance", "genre": "Pop"})
    assert a1 == a2
    assert sstore.get_artist(a1)["identity_confidence"] >= 0.99
    # a different provider matching only by name is kept, but at lower confidence
    a3 = sstore.upsert_artist("other", "dupe-x", {"name": "ivy   vance!", "genre": "Pop"})
    assert a3 == a1


def test_scores_are_versioned_explainable_and_never_overwritten(seeded):
    artist_id = sstore.list_artists(limit=1)[0]["id"]
    scoring.score_artist(artist_id)
    scoring.score_artist(artist_id)
    scores = sstore.latest_scores(artist_id)
    assert scoring.MOMENTUM in scores
    m = scores[scoring.MOMENTUM]
    assert m["version"] == scoring.SCORE_VERSION
    assert 0 <= m["value"] <= 100
    expl = m["explanation"]
    assert expl["contributions"], "a score with no contributions is not shippable"
    assert expl["weights"] and "shape" in expl
    for name, c in expl["contributions"].items():
        assert set(("value", "weight", "points")) <= set(c), name
    assert len(sstore.score_history(artist_id, scoring.MOMENTUM)) >= 2, "history was overwritten"


def test_missing_inputs_are_named_and_renormalised_not_zeroed():
    """An artist with no data must not score 0 as if that were a finding."""
    aid = sstore.upsert_artist("mock", "bare-artist", {"name": "Bare Artist", "genre": "Rock",
                                                       "monthly_listeners": 5000})
    value, expl, quality = scoring.momentum(aid)
    assert quality in ("partial", "thin")
    assert expl["missing"], "missing inputs must be named"
    assert expl["coverage"] <= 1.0


def test_cohorts_compare_like_with_like():
    small = {"career_stage": "Emerging", "monthly_listeners": 4000, "genre": "Punk"}
    big = {"career_stage": "Established", "monthly_listeners": 4000000, "genre": "Punk"}
    assert scoring.cohort_of(small) != scoring.cohort_of(big)
    assert scoring.audience_band(4000) == "0-10k"
    assert scoring.audience_band(4000000) == "1M+"


def test_acceleration_distinguishes_a_spike_from_a_trend():
    base = date(2030, 1, 1)

    def series(values):
        return [((base + timedelta(days=i)).isoformat(), v) for i, v in enumerate(values)]

    steady = series([100 + i for i in range(60)])
    accel = series([100 * (1.01 ** i) for i in range(60)])
    assert scoring.acceleration(accel, 28) > scoring.acceleration(steady, 28)
    assert scoring.pct_change(series([100] * 30), 28) == 0


def test_distribution_is_a_per_release_reading_with_consistency():
    aid = sstore.upsert_artist("mock", "dist-artist", {"name": "Dist Artist"})
    sstore.replace_releases(aid, "mock", [
        {"title": "New", "release_date": "2030-06-01", "distributor_name": "Ridgeline Digital",
         "distributor_class": "DIY / Self-Service", "provider_release_id": "r1"},
        {"title": "Old", "release_date": "2029-01-01", "distributor_name": "Ridgeline Digital",
         "distributor_class": "DIY / Self-Service", "provider_release_id": "r2"},
        {"title": "Older", "release_date": "2028-01-01", "distributor_name": "Pelham Row Records",
         "distributor_class": "Independent Label", "provider_release_id": "r3"},
    ])
    d = scoring.current_distribution(sstore.list_releases(aid))
    assert d["name"] == "Ridgeline Digital"
    assert d["classification"] == "DIY / Self-Service"
    assert 0 < d["consistency"] < 1, "a split catalogue must not read as fully consistent"


def test_rights_health_is_cautious_never_a_finding_of_fact():
    aid = sstore.upsert_artist("mock", "rights-artist", {"name": "Rights Artist"})
    sstore.replace_releases(aid, "mock", [
        {"title": "Untitled", "release_date": "2030-01-01", "upc": "", "provider_release_id": "x1"}])
    value, expl, quality = scoring.rights_health(aid)
    assert "caution" in expl and "only an authorised" in expl["caution"]
    statuses = [f["status"] for f in expl["findings"]]
    assert statuses, "no findings recorded"
    assert "unregistered" not in " ".join(f["detail"].lower() for f in expl["findings"])
    for s in statuses:
        assert s in sstore.EVIDENCE_STATUSES


def test_contact_confidence_ranks_by_source_strength():
    aid = sstore.upsert_artist("mock", "contact-artist", {"name": "Contact Artist"})
    sstore.add_evidence("artist", aid, sstore.CLAIM_CONTACT, "Manager", "mgmt@example.test",
                        "official_site", "Artist site", "", "Management: ...", 0.9)
    sstore.add_evidence("artist", aid, sstore.CLAIM_CONTACT, "Publicist", "someone@example.test",
                        "directory", "A directory", "", "", 0.9)
    value, expl, quality = scoring.contact_confidence(aid)
    assert expl["best"]["role"] == "Manager", "a directory outranked an official site"
    assert expl["best"]["why"]


# --- the critical end-to-end flow from the brief ----------------------------

def test_end_to_end_discovery_to_operator_desk(flask_app):
    """Mock provider -> score -> DIY distribution -> manager identified ->
    rights gap flagged as POTENTIAL -> high gap -> recommendation -> pushed to
    the Operator Desk with lead, note, task, watchlist and a preserved
    snapshot."""
    import desk_store
    providers.reset_registry(providers.ProviderRegistry(adapters=[]))
    client, user, org = _user(flask_app, "E2E Owner", role="owner")

    # 1-2. the provider detects an ACCELERATING artist, and it is scored.
    # Pick the strongest mover rather than a fixed id: the demo universe is
    # deliberately mostly ordinary, and a DIY artist who is not moving is
    # correctly not an opportunity.
    ingest.refresh_universe(max_artists=14, force=True)
    ranked = []
    for a in sstore.list_artists(limit=40):
        m = sstore.latest_scores(a["id"]).get(scoring.MOMENTUM)
        if m:
            ranked.append((m["value"], a["id"]))
    ranked.sort(reverse=True)
    assert ranked, "the mock universe produced no scored artists"
    artist_id = ranked[0][1]
    assert ranked[0][0] >= 55, "no artist in the demo universe is actually moving"
    scores = sstore.latest_scores(artist_id)
    assert scores[scoring.MOMENTUM]["version"] == scoring.SCORE_VERSION

    # 3. distribution is classified per release
    releases = sstore.list_releases(artist_id)
    assert releases
    dist = scoring.current_distribution(releases)
    assert dist["classification"] in sstore.DISTRIBUTOR_CLASSES

    # force the shape the brief describes: DIY, a manager, a rights gap
    sstore.replace_releases(artist_id, "mock", [
        {"title": "Recent", "release_date": date.today().isoformat(), "upc": "",
         "distributor_name": "Ridgeline Digital", "distributor_class": "DIY / Self-Service",
         "provider_release_id": "e2e-1"}])
    sstore.add_evidence("artist", artist_id, sstore.CLAIM_CONTACT, "Manager",
                        "management@hollowpine.example", "official_site",
                        "Artist site - Contact", "", "Management: Hollow Pine", 0.93)
    sstore.add_evidence("artist", artist_id, sstore.CLAIM_RIGHTS, "Recent",
                        "no_confident_match", "work_registry", "Registry lookup", "",
                        "no match", 0.5, status="potential_gap",
                        detail={"work_match": False, "writers_complete": False,
                                "publisher_detected": False, "shares_complete": False,
                                "recording_linked": False})
    scoring.score_artist(artist_id)

    # 4. the manager is identified, with a source and a confidence
    contacts = sstore.list_evidence("artist", artist_id, sstore.CLAIM_CONTACT)
    mgr = [c for c in contacts if c["claim_key"] == "Manager"][0]
    assert mgr["source_label"] and mgr["confidence"] >= 0.9
    assert mgr["status"] in ("verified", "high_confidence")

    # 5. the rights gap is POTENTIAL, never definitive
    rights = sstore.list_evidence("artist", artist_id, sstore.CLAIM_RIGHTS)
    assert any(r["status"] == "potential_gap" for r in rights)
    assert all(r["status"] != "unregistered" for r in rights)

    # 6-7. gap is high and the recommendation reflects it
    scores = sstore.latest_scores(artist_id)
    gap = scores[scoring.DISTRIBUTION_GAP]["value"]
    assert gap >= 55, "a DIY artist with a rights gap should read as under-supported (%s)" % gap
    rec = scoring.recommend(artist_id)
    assert "Distribution" in rec["lanes"] or "Royalty Sweep" in rec["lanes"]
    assert rec["action"]
    assert "does not sign" in rec["disclaimer"]

    # 8. push to the Operator Desk that already exists. This person holds a
    # seat there too, which is the ordinary case, so they land on the lead.
    desk_store.add_user(user["email"], "E2E Owner", "admin")
    r = client.post("/signal/artist/%s/operator-desk" % artist_id)
    assert r.status_code in (302, 303)
    assert "/operator-desk/leads/" in r.headers["Location"]
    lead_id = r.headers["Location"].rsplit("/", 1)[1]

    # 9. lead, note, task and watchlist all exist
    lead = desk_store.get_lead(lead_id)
    assert lead and lead["artist_name"] == sstore.get_artist(artist_id)["canonical_name"]
    assert lead["lead_source"] == "Street Banker Signal"
    assert lead["current_distributor"] == "Ridgeline Digital"
    notes = desk_store.list_notes(lead_id)
    assert notes and "Signal" in notes[0]["body"]
    assert scoring.SCORE_VERSION in notes[0]["body"]
    tasks = desk_store.list_tasks(lead_id=lead_id)
    assert tasks, "no follow-up task was created"
    assert sstore.is_watched(org["id"], artist_id)

    # 10. the snapshot and score version are preserved for later scoring of Signal itself
    link = sstore.desk_link_for(org["id"], artist_id)
    assert link and link["lead_id"] == lead_id
    assert link["score_version"] == scoring.SCORE_VERSION
    snap = link["snapshot"]
    assert snap["scores"][scoring.MOMENTUM] == round(scores[scoring.MOMENTUM]["value"])
    assert snap["captured_at"] and snap["cohort"]

    # pushing twice does not create a second lead
    r2 = client.post("/signal/artist/%s/operator-desk" % artist_id)
    assert r2.headers["Location"].rsplit("/", 1)[1] == lead_id


def test_a_signal_seat_without_a_desk_seat_is_not_sent_to_a_403(flask_app, seeded):
    """The Desk has its own roster. Pushing must still create the lead — it
    belongs to the organisation — but must not dump the user on a page they
    cannot open."""
    import desk_store
    providers.reset_registry(providers.ProviderRegistry(adapters=[]))
    client, user, org = _user(flask_app, "No Desk Seat", role="admin")
    assert desk_store.get_user_by_email(user["email"]) is None

    artist_id = [a["id"] for a in sstore.list_artists(limit=8)
                 if not sstore.desk_link_for(org["id"], a["id"])][0]
    r = client.post("/signal/artist/%s/operator-desk" % artist_id)
    assert r.status_code in (302, 303)
    assert "/operator-desk/" not in r.headers["Location"], "sent to a page they cannot open"
    assert "/signal/artist/" in r.headers["Location"]

    # the lead really was created for the organisation
    link = sstore.desk_link_for(org["id"], artist_id)
    assert link and desk_store.get_lead(link["lead_id"])
    # and the artist page tells them plainly rather than offering a dead link
    body = client.get("/signal/artist/%s" % artist_id).get_data(as_text=True)
    assert "On the desk" in body and "do not hold an Operator Desk seat" in body
    assert "/operator-desk/leads/%s" % link["lead_id"] not in body


def test_signal_and_the_desk_link_to_each_other(flask_app, seeded):
    """The two halves of one workflow. Signal was reachable only by typing
    the URL, and a lead gave no way back to the intelligence behind it."""
    import desk_store
    providers.reset_registry(providers.ProviderRegistry(adapters=[]))
    client, user, org = _user(flask_app, "Linked Owner", role="owner")
    desk_store.add_user(user["email"], "Linked Owner", "owner")

    # the Desk sidebar offers Signal
    desk_body = client.get("/operator-desk/").get_data(as_text=True)
    assert 'href="/signal"' in desk_body

    # the main app sidebar carries an Internal footer for a seat-holder
    site = client.get("/command-center").get_data(as_text=True)
    assert "Internal" in site and 'href="/signal"' in site and 'href="/operator-desk/"' in site

    # ...and does not for someone with no seat at all
    plain, plain_user, _ = _user(flask_app, "Plain User", role=None)
    plain_site = plain.get("/command-center").get_data(as_text=True)
    assert 'href="/signal"' not in plain_site and 'href="/operator-desk/"' not in plain_site

    # a lead created by Signal links back, and shows the frozen snapshot
    artist_id = [a["id"] for a in sstore.list_artists(limit=10)
                 if not sstore.desk_link_for(org["id"], a["id"])][0]
    r = client.post("/signal/artist/%s/operator-desk" % artist_id)
    lead_id = r.headers["Location"].rsplit("/", 1)[1]
    lead_body = client.get("/operator-desk/leads/%s" % lead_id).get_data(as_text=True)
    assert "From Signal" in lead_body
    assert '/signal/artist/%s' % artist_id in lead_body
    assert scoring.SCORE_VERSION in lead_body
    assert "not the live figures" in lead_body

    # a lead that did NOT come from Signal shows no such panel
    other_lead = desk_store.create_lead({"artist_name": "Walk-in Artist"}, [], [],
                                        {"id": None, "name": "Linked Owner"})
    assert "From Signal" not in client.get("/operator-desk/leads/%s" % other_lead).get_data(as_text=True)


# --- pages ------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/signal", "/signal/breaking", "/signal/early",
                                  "/signal/cities", "/signal/undervalued",
                                  "/signal/deal-ready", "/signal/watchlists",
                                  "/signal/mandates", "/signal/alerts", "/signal/team",
                                  "/signal/ask"])
def test_every_page_renders(flask_app, seeded, path):
    client, user, org = _user(flask_app, "Page Reader", role="owner")
    r = client.get(path)
    assert r.status_code == 200, path
    body = r.get_data(as_text=True)
    for leak in ("<built-in method", "&lt;built-in method", "object at 0x",
                 "&lt;bound method", "dict_items("):
        assert leak not in body, "%s leaked %r" % (path, leak)


def test_demo_mode_is_declared_on_every_page(flask_app, seeded):
    providers.reset_registry(providers.ProviderRegistry(adapters=[]))
    client, user, org = _user(flask_app, "Demo Reader", role="owner")
    body = client.get("/signal").get_data(as_text=True)
    assert "Demo data" in body and "fictional" in body


def test_artist_page_and_score_explanations_render(flask_app, seeded):
    client, user, org = _user(flask_app, "Detail Reader", role="owner")
    artist_id = sstore.list_artists(limit=1)[0]["id"]
    scoring.score_artist(artist_id)
    for tab in ("overview", "momentum", "releases", "cities", "distribution",
                "contacts", "rights", "opportunity"):
        r = client.get("/signal/artist/%s?tab=%s" % (artist_id, tab))
        assert r.status_code == 200, tab
    r = client.get("/signal/artist/%s/score/%s" % (artist_id, scoring.MOMENTUM))
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert scoring.SCORE_VERSION in body and "Weight" in body


def test_ask_signal_shows_its_filters_and_admits_what_it_cannot_do(flask_app, seeded):
    client, user, org = _user(flask_app, "Asker", role="owner")
    body = client.get("/signal/ask?q=" +
                      "independent rock artists under 250000 listeners growing more than 5%25 "
                      "with tiktok conversion").get_data(as_text=True)
    assert "Interpreted as" in body
    assert "max listeners" in body or "max_listeners" in body
    # the part it cannot honour is declared, not silently dropped
    assert "cannot be answered" in body and "tiktok" in body.lower()


def test_board_csv_export(flask_app, seeded):
    client, user, org = _user(flask_app, "Exporter", role="owner")
    r = client.get("/signal/export/board.csv")
    assert r.status_code == 200 and "text/csv" in r.headers["Content-Type"]
    text = r.get_data(as_text=True)
    assert "SB Momentum" in text and scoring.SCORE_VERSION in text


def test_alerts_only_fire_against_your_own_watchlist(flask_app, seeded):
    # a dedicated org: the default one carries watch items from other tests,
    # and "nothing watched yet" has to actually mean nothing watched
    oid = sstore.create_org("Alert Co", "alert-co-%s" % uuid.uuid4().hex[:6])
    org = [o for o in sstore.list_orgs() if o["id"] == oid][0]
    client, user, _ = _user(flask_app, "Alerting", role="owner", org=org)
    artist_id = sstore.list_artists(limit=1)[0]["id"]
    scoring.score_artist(artist_id)
    sstore.create_alert_rule(org["id"], "Anything", "momentum_above", 0, "in_app", "Alerting")
    # nothing watched yet -> nothing fires
    assert ingest.evaluate_alerts(org["id"]) == 0
    wid = sstore.ensure_watchlist(org["id"], "Test", "Alerting")
    sstore.add_to_watchlist(org["id"], wid, artist_id, "Alerting")
    assert ingest.evaluate_alerts(org["id"]) >= 1
    # and it is idempotent within the day, so a per-request sweep cannot spam
    before = len(sstore.list_alerts(org["id"]))
    ingest.evaluate_alerts(org["id"])
    assert len(sstore.list_alerts(org["id"])) == before


def test_evidence_always_carries_a_source_and_can_be_overruled():
    aid = sstore.upsert_artist("mock", "ev-artist", {"name": "Evidence Artist"})
    eid = sstore.add_evidence("artist", aid, sstore.CLAIM_DISTRIBUTOR, "Album", "Foxglove",
                              "release_metadata", "Release metadata", "", "(P) Foxglove", 0.8)
    ev = sstore.list_evidence("artist", aid, sstore.CLAIM_DISTRIBUTOR)[0]
    assert ev["source_label"] and ev["first_observed_at"] and ev["last_verified_at"]
    assert ev["status"] == "high_confidence"
    # a human overrules the machine, and it is recorded as such
    sstore.set_evidence_verification(eid, "manually_rejected", "A Human")
    ev = sstore.list_evidence("artist", aid, sstore.CLAIM_DISTRIBUTOR)[0]
    assert ev["status"] == "manually_rejected" and ev["verified_by"] == "A Human"
    # and a later automatic pass does not silently undo that judgement
    sstore.add_evidence("artist", aid, sstore.CLAIM_DISTRIBUTOR, "Album", "Foxglove",
                        "release_metadata", "Release metadata", "", "(P) Foxglove", 0.95)
    ev = sstore.list_evidence("artist", aid, sstore.CLAIM_DISTRIBUTOR)[0]
    assert ev["status"] == "manually_rejected"
