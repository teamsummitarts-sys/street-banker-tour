"""Manager-first Company OS product, access, and navigation contract."""

import company_os
import db as store
import hubs
import pytest
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

from app import create_app


OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "manager-first-pass"
COMPANY_OS_HEADERS = {"X-SB-Intent": "company-os-v2"}


def _signed_in_owner(monkeypatch, tmp_path, *, signup_mode="owner_only"):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "streetbanker.db"))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("SIGNUP_MODE", signup_mode)
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    app = create_app()
    owner_id = store.create_user(
        OWNER_EMAIL, "Owner", generate_password_hash(OWNER_PASSWORD))
    store.set_user_plan(owner_id, "label")
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = owner_id
    return app, client, owner_id


def _create_objective(client, marker="MANAGER-FIRST"):
    response = client.post(
        "/api/company-os/objectives",
        json={
            "title": f"Launch the next single {marker}",
            "success_condition": "Approve a complete release plan with evidence",
            "target_date": "2026-10-30",
            "project": "Street Banker V2",
            "priority": "high",
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def test_team_os_renders_manager_first_and_exact_company_definition(
        monkeypatch, tmp_path):
    _app, client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)

    response = client.get("/team")
    body = response.get_data(as_text=True)
    state_response = client.get("/api/company-os")
    state = state_response.get_json()

    assert response.status_code == 200
    assert state_response.status_code == 200
    assert state["ok"] is True
    assert body.count('data-desk-key="') == 10
    assert "Manager Control Room" in body
    assert "Your Manager + nine specialist desks" in body
    assert "10 desks / 20 capabilities" in body
    assert "company-os-signal-room.css" in body
    assert body.count('data-desk-stage="') == 4
    assert "The proposed plan remains unassigned until you approve it." in body
    assert "Mission Control" in body
    assert body.index("Manager Control Room") < body.index(
        "Your Manager + nine specialist desks")
    assert body.index('href="#sb2-manager"') < body.index(
        'href="#sb2-company-index"')

    team = state["team"]
    assert len(team) == len(company_os.TEAM) == 10
    assert [member["seat"] for member in team] == [
        f"{number:02d}" for number in range(1, 11)
    ]
    assert team[0]["key"] == "manager"
    assert team[0]["name"] == "Your Manager"
    capabilities = [
        capability
        for member in team
        for capability in member["capabilities"]
    ]
    assert all(len(member["capabilities"]) == 2 for member in team)
    assert len(capabilities) == 20
    assert len({item["key"] for item in capabilities}) == 20

    for member in team:
        assert member["name"].replace("&", "&amp;") in body
        for capability in member["capabilities"]:
            assert capability["name"].replace("&", "&amp;") in body


def test_manager_builds_proposed_plan_only_with_explicit_company_intent(
        monkeypatch, tmp_path):
    _app, client, owner_id = _signed_in_owner(monkeypatch, tmp_path)
    request_body = {
        "title": "Launch the next single without accidental assignment",
        "success_condition": "A complete plan is ready for owner approval",
        "target_date": "2026-10-30",
        "project": "Street Banker V2",
    }

    missing_intent = client.post(
        "/api/company-os/objectives", json=request_body)

    assert missing_intent.status_code == 403
    assert missing_intent.get_json() == {
        "ok": False,
        "error": "Missing Company OS request intent.",
    }
    assert store.list_manager_objectives(owner_id) == []

    payload = _create_objective(client)
    objective = payload["objective"]
    assignments = [
        item for item in payload["assignments"]
        if item["objective_id"] == objective["id"]
    ]

    assert objective["plan_status"] == "pending"
    assert assignments
    assert {item["status"] for item in assignments} == {"proposed"}
    assert not any(item.get("started_at") for item in assignments)
    assert not any(item.get("delivered_at") for item in assignments)
    assert payload["mission_control"]["decisions_due"] == 1


def test_owner_approval_assigns_plan_without_claiming_finished_work(
        monkeypatch, tmp_path):
    _app, client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)
    created = _create_objective(client, "APPROVAL-GATE")
    objective = created["objective"]

    response = client.post(
        f"/api/company-os/objectives/{objective['id']}/approve-plan",
        json={"expected_version": objective["version"]},
        headers=COMPANY_OS_HEADERS,
    )
    payload = response.get_json()
    assignments = [
        item for item in payload["assignments"]
        if item["objective_id"] == objective["id"]
    ]

    assert response.status_code == 200
    assert payload["objective"]["plan_status"] == "approved"
    assert assignments
    assert {item["status"] for item in assignments} == {"queued"}
    assert not any(item.get("started_at") for item in assignments)
    assert not any(item.get("delivered_at") for item in assignments)
    assert payload["mission_control"]["decisions_due"] == 0


def test_new_pending_plan_becomes_current_over_older_in_progress_objective(
        monkeypatch, tmp_path):
    _app, client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)
    first = _create_objective(client, "FIRST")
    approved = client.post(
        f"/api/company-os/objectives/{first['objective']['id']}/approve-plan",
        json={"expected_version": first["objective"]["version"]},
        headers=COMPANY_OS_HEADERS,
    ).get_json()
    first_assignment = next(
        item for item in approved["assignments"]
        if item["objective_id"] == first["objective"]["id"])
    started = client.patch(
        f"/api/company-os/assignments/{first_assignment['id']}",
        json={
            "status": "in_progress",
            "expected_version": first_assignment["version"],
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert started.status_code == 200

    second = _create_objective(client, "SECOND")

    assert second["objective"]["id"] != first["objective"]["id"]
    assert second["active_objective"]["id"] == second["objective"]["id"]
    assert second["active_objective"]["plan_status"] == "pending"

    # The UI may show a specialist as proposed only when that specialist has
    # an assignment on the current objective. Historical work from the first
    # objective must not fabricate participation in the second plan.
    page = client.get("/team").get_data(as_text=True)
    assert "assignment.objective_id === currentObjectiveId" in page
    assert "&& currentRecords.length" in page


def test_owner_can_record_and_clear_assignment_blocker(monkeypatch, tmp_path):
    _app, client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)
    created = _create_objective(client, "BLOCKER")
    approved = client.post(
        f"/api/company-os/objectives/{created['objective']['id']}/approve-plan",
        json={"expected_version": created["objective"]["version"]},
        headers=COMPANY_OS_HEADERS,
    ).get_json()
    assignment = next(
        item for item in approved["assignments"]
        if item["objective_id"] == created["objective"]["id"])

    blocked = client.patch(
        f"/api/company-os/assignments/{assignment['id']}",
        json={
            "status": "blocked",
            "blocker": "Need the final master WAV",
            "expected_version": assignment["version"],
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert blocked.status_code == 200
    blocked_payload = blocked.get_json()
    blocked_assignment = next(
        item for item in blocked_payload["assignments"]
        if item["id"] == assignment["id"])
    assert blocked_assignment["status"] == "blocked"
    assert blocked_assignment["blocker"] == "Need the final master WAV"
    assert blocked_payload["mission_control"]["blocked_count"] == 1

    resumed = client.patch(
        f"/api/company-os/assignments/{assignment['id']}",
        json={
            "status": "in_progress",
            "expected_version": blocked_assignment["version"],
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert resumed.status_code == 200
    resumed_payload = resumed.get_json()
    resumed_assignment = next(
        item for item in resumed_payload["assignments"]
        if item["id"] == assignment["id"])
    assert resumed_assignment["status"] == "in_progress"
    assert resumed_assignment["blocker"] == ""
    assert resumed_payload["mission_control"]["blocked_count"] == 0


def test_deliverable_lifecycle_requires_active_work_and_every_revision_reviewed(
        monkeypatch, tmp_path):
    _app, client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)
    created = _create_objective(client, "DELIVERABLE-LIFECYCLE")
    objective = created["objective"]
    approved = client.post(
        f"/api/company-os/objectives/{objective['id']}/approve-plan",
        json={"expected_version": objective["version"]},
        headers=COMPANY_OS_HEADERS,
    ).get_json()
    assignment = next(
        item for item in approved["assignments"]
        if item["objective_id"] == objective["id"])
    activity_before = list(approved["activity"])

    queued_submission = client.post(
        f"/api/company-os/assignments/{assignment['id']}/deliverables",
        json={
            "title": "Premature decision",
            "summary": "This must not persist before work begins.",
            "evidence_refs": ["https://example.com/premature"],
            "expected_version": assignment["version"],
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert queued_submission.status_code == 409
    unchanged = client.get("/api/company-os").get_json()
    assert not any(
        item.get("work_item_id") == assignment["id"]
        for item in unchanged["deliverables"])
    assert unchanged["activity"] == activity_before

    started = client.patch(
        f"/api/company-os/assignments/{assignment['id']}",
        json={
            "status": "in_progress",
            "expected_version": assignment["version"],
        },
        headers=COMPANY_OS_HEADERS,
    ).get_json()
    assignment = next(
        item for item in started["assignments"]
        if item["id"] == assignment["id"])

    first = client.post(
        f"/api/company-os/assignments/{assignment['id']}/deliverables",
        json={
            "title": "Release decision v1",
            "summary": "First documented release recommendation.",
            "evidence_refs": ["https://example.com/decision-v1"],
            "expected_version": assignment["version"],
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert first.status_code == 201
    first_payload = first.get_json()
    first_deliverable = first_payload["deliverable"]
    assignment = next(
        item for item in first_payload["assignments"]
        if item["id"] == assignment["id"])

    second = client.post(
        f"/api/company-os/assignments/{assignment['id']}/deliverables",
        json={
            "title": "Release decision v2",
            "summary": "Latest documented release recommendation.",
            "evidence_refs": ["https://example.com/decision-v2"],
            "expected_version": assignment["version"],
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert second.status_code == 201
    second_payload = second.get_json()
    second_deliverable = second_payload["deliverable"]
    assignment = next(
        item for item in second_payload["assignments"]
        if item["id"] == assignment["id"])
    assert second_deliverable["revision"] > first_deliverable["revision"]

    review = client.patch(
        f"/api/company-os/assignments/{assignment['id']}",
        json={"status": "review", "expected_version": assignment["version"]},
        headers=COMPANY_OS_HEADERS,
    ).get_json()
    assignment = next(
        item for item in review["assignments"]
        if item["id"] == assignment["id"])

    newest_approved = client.post(
        f"/api/company-os/deliverables/{second_deliverable['id']}/review",
        json={
            "decision": "approved",
            "note": "Latest revision approved.",
            "expected_version": second_deliverable["version"],
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert newest_approved.status_code == 200

    pending_blocks_delivery = client.patch(
        f"/api/company-os/assignments/{assignment['id']}",
        json={"status": "delivered", "expected_version": assignment["version"]},
        headers=COMPANY_OS_HEADERS,
    )
    assert pending_blocks_delivery.status_code == 409

    older_reviewed = client.post(
        f"/api/company-os/deliverables/{first_deliverable['id']}/review",
        json={
            "decision": "approved",
            "note": "Earlier revision also reviewed.",
            "expected_version": first_deliverable["version"],
        },
        headers=COMPANY_OS_HEADERS,
    )
    assert older_reviewed.status_code == 200
    assignment = next(
        item for item in older_reviewed.get_json()["assignments"]
        if item["id"] == assignment["id"])

    delivered = client.patch(
        f"/api/company-os/assignments/{assignment['id']}",
        json={"status": "delivered", "expected_version": assignment["version"]},
        headers=COMPANY_OS_HEADERS,
    )
    assert delivered.status_code == 200
    saved = next(
        item for item in delivered.get_json()["assignments"]
        if item["id"] == assignment["id"])
    assert saved["status"] == "delivered"


def test_rejected_latest_revision_cannot_hide_behind_older_approval(
        monkeypatch, tmp_path):
    _app, _client, owner_id = _signed_in_owner(monkeypatch, tmp_path)
    bundle = store.create_manager_objective_plan(
        owner_id,
        "Verify the latest release decision",
        "a_and_r",
        [{
            "assignee": "a_and_r",
            "capability": "release_decision",
            "title": "Make the release decision",
            "expected_deliverable": "A&R decision memo",
            "due_date": "2026-10-30",
        }],
        actor_user_id=owner_id,
    )
    bundle = store.approve_manager_plan(
        owner_id,
        bundle["objective"]["id"],
        expected_version=bundle["objective"]["version"],
        actor_user_id=owner_id,
    )
    assignment = bundle["work_items"][0]
    bundle = store.transition_manager_work_item(
        owner_id,
        assignment["id"],
        "in_progress",
        expected_version=assignment["version"],
        actor_user_id=owner_id,
    )
    assignment = bundle["work_items"][0]
    bundle = store.create_manager_deliverable(
        owner_id,
        assignment["id"],
        kind="text",
        title="Decision v1",
        body="The first supported decision.",
        metadata={"evidence_refs": ["https://example.com/v1"]},
        expected_version=assignment["version"],
        actor_user_id=owner_id,
    )
    first = bundle["deliverable"]
    assignment = bundle["work_items"][0]
    bundle = store.transition_manager_work_item(
        owner_id,
        assignment["id"],
        "review",
        expected_version=assignment["version"],
        actor_user_id=owner_id,
    )
    bundle = store.decide_manager_deliverable(
        owner_id,
        first["id"],
        "approved",
        expected_version=first["version"],
        actor_user_id=owner_id,
    )
    assignment = bundle["work_items"][0]
    bundle = store.transition_manager_work_item(
        owner_id,
        assignment["id"],
        "in_progress",
        expected_version=assignment["version"],
        actor_user_id=owner_id,
    )
    assignment = bundle["work_items"][0]
    bundle = store.create_manager_deliverable(
        owner_id,
        assignment["id"],
        kind="text",
        title="Decision v2",
        body="The newer decision requires another revision.",
        metadata={"evidence_refs": ["https://example.com/v2"]},
        expected_version=assignment["version"],
        actor_user_id=owner_id,
    )
    latest = bundle["deliverable"]
    assignment = bundle["work_items"][0]
    bundle = store.transition_manager_work_item(
        owner_id,
        assignment["id"],
        "review",
        expected_version=assignment["version"],
        actor_user_id=owner_id,
    )
    bundle = store.decide_manager_deliverable(
        owner_id,
        latest["id"],
        "revision_requested",
        expected_version=latest["version"],
        note="Revise the recommendation.",
        actor_user_id=owner_id,
    )
    assignment = bundle["work_items"][0]
    bundle = store.transition_manager_work_item(
        owner_id,
        assignment["id"],
        "review",
        expected_version=assignment["version"],
        actor_user_id=owner_id,
    )
    assignment = bundle["work_items"][0]
    activity_before = list(bundle["activity"])

    with pytest.raises(
            store.ManagerConflictError,
            match="latest deliverable revision must be approved"):
        store.transition_manager_work_item(
            owner_id,
            assignment["id"],
            "delivered",
            expected_version=assignment["version"],
            actor_user_id=owner_id,
        )

    unchanged = store.get_manager_objective(
        owner_id, bundle["objective"]["id"])
    assert unchanged["work_items"][0]["status"] == "review"
    assert unchanged["work_items"][0]["version"] == assignment["version"]
    assert unchanged["activity"] == activity_before


def test_manager_rejects_unclear_objective_without_persisting_it(
        monkeypatch, tmp_path):
    _app, client, owner_id = _signed_in_owner(monkeypatch, tmp_path)

    response = client.post(
        "/api/company-os/objectives",
        json={"title": "x"},
        headers=COMPANY_OS_HEADERS,
    )

    assert response.status_code == 400
    assert response.get_json()["ok"] is False
    assert store.list_manager_objectives(owner_id) == []
    assert store.list_manager_work_items(owner_id) == []


@pytest.mark.parametrize(
    "request_body",
    [
        {"title": "Launch the next release"},
        {
            "title": "Launch the next release",
            "success_condition": "Approve a complete plan",
        },
    ],
)
def test_manager_requires_success_condition_and_decision_deadline(
        monkeypatch, tmp_path, request_body):
    _app, client, owner_id = _signed_in_owner(monkeypatch, tmp_path)

    response = client.post(
        "/api/company-os/objectives",
        json=request_body,
        headers=COMPANY_OS_HEADERS,
    )

    assert response.status_code == 400
    assert response.get_json()["ok"] is False
    assert store.list_manager_objectives(owner_id) == []


def test_company_os_requires_sign_in_and_owner_authorization(
        monkeypatch, tmp_path):
    app, owner_client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)
    outsider_id = store.create_user(
        "outsider@example.com",
        "Outsider",
        generate_password_hash("outsider-pass"),
    )
    outsider = app.test_client()
    with outsider.session_transaction() as session:
        session["user_id"] = outsider_id

    anonymous = app.test_client()
    team_redirect = anonymous.get("/team", follow_redirects=False)
    anonymous_api = anonymous.get("/api/company-os")
    outsider_team = outsider.get("/team")
    outsider_api = outsider.get("/api/company-os")

    assert team_redirect.status_code == 302
    assert "/login" in team_redirect.headers["Location"]
    assert anonymous_api.status_code == 401
    assert outsider_team.status_code == 403
    assert outsider_api.status_code == 403
    assert owner_client.get("/team").status_code == 200


def test_team_is_first_navigation_item_and_not_duplicated():
    all_items = [
        item
        for _key, _name, _tagline, items in hubs.HUBS
        for item in items
    ] + list(hubs.ACCOUNT_GROUP[1])

    assert hubs.HUBS[0][0] == "command"
    assert hubs.HUBS[0][3][0][0] == "team"
    assert [item[0] for item in all_items].count("team") == 1


def test_owner_login_lands_on_manager_first_team(monkeypatch, tmp_path):
    _app, client, _owner_id = _signed_in_owner(monkeypatch, tmp_path)
    with client.session_transaction() as session:
        session.clear()

    response = client.post(
        "/login",
        data={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/team")


def test_new_owner_account_enters_through_team(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "new-owner.db"))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("SIGNUP_MODE", "owner_only")
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/signup",
        data={
            "name": "Owner",
            "email": OWNER_EMAIL,
            "password": OWNER_PASSWORD,
            "account_type": "artist",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/team")


def test_closed_signup_blocks_registration_invites_and_join_links(
        monkeypatch, tmp_path):
    _app, client, _owner_id = _signed_in_owner(
        monkeypatch, tmp_path, signup_mode="closed")

    signup_page = client.get("/signup", follow_redirects=False)
    registration = client.post(
        "/signup",
        data={
            "name": "Unapproved User",
            "email": "unapproved@example.com",
            "password": "unapproved-pass",
            "account_type": "artist",
        },
    )
    invite = client.post(
        "/team/invite",
        data={"email": "collaborator@example.com", "role": "manager"},
        headers=COMPANY_OS_HEADERS,
    )
    join = client.get("/team/join/not-a-live-invite")
    roster_invite = client.post(
        "/roster/invite",
        data={"email": "artist@example.com"},
    )
    roster_join = client.get("/roster/join/not-a-live-invite")

    assert signup_page.status_code == 302
    assert "/login?signup=closed" in signup_page.headers["Location"]
    assert registration.status_code == 403
    assert "Street Banker V2 registration is closed." in registration.get_data(
        as_text=True)
    assert store.get_user_by_email("unapproved@example.com") is None
    assert invite.status_code == 403
    assert invite.get_json() == {
        "ok": False,
        "error": "Invites are disabled while V2 registration is closed.",
    }
    assert join.status_code == 404
    assert roster_invite.status_code == 403
    assert roster_join.status_code == 404


def test_closed_mode_allows_only_explicit_owner_login(monkeypatch, tmp_path):
    app, client, _owner_id = _signed_in_owner(
        monkeypatch, tmp_path, signup_mode="closed")
    outsider_password = "existing-account-pass"
    outsider_id = store.create_user(
        "existing@example.com",
        "Existing Account",
        generate_password_hash(outsider_password),
    )
    with client.session_transaction() as session:
        session["user_id"] = outsider_id
    stale_session = client.get("/command-center", follow_redirects=False)
    assert stale_session.status_code == 302
    assert "/login" in stale_session.headers["Location"]
    with client.session_transaction() as session:
        assert "user_id" not in session

    with client.session_transaction() as session:
        session.clear()

    denied = client.post(
        "/login",
        data={"email": "existing@example.com", "password": outsider_password},
        follow_redirects=False,
    )
    assert denied.status_code == 200
    assert "Incorrect email or password." in denied.get_data(as_text=True)

    outsider_token = URLSafeTimedSerializer(
        app.config["SECRET_KEY"], salt="pw-reset").dumps(outsider_id)
    denied_reset = client.get(f"/reset/{outsider_token}")
    assert denied_reset.status_code == 200
    assert "invalid" in denied_reset.get_data(as_text=True).lower()

    allowed = client.post(
        "/login",
        data={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        follow_redirects=False,
    )
    assert allowed.status_code == 302
    assert allowed.headers["Location"].endswith("/team")


def test_closed_login_page_exposes_no_signup_or_demo_entry(monkeypatch, tmp_path):
    _app, client, _owner_id = _signed_in_owner(
        monkeypatch, tmp_path, signup_mode="closed")
    with client.session_transaction() as session:
        session.clear()

    response = client.get("/login")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "PRIVATE V2 ACCESS" in body
    assert "Registration and demo access are closed." in body
    assert 'href="/signup' not in body
    assert 'action="/demo-open"' not in body
    assert 'action="/demo-access"' not in body


def test_closed_mode_disables_configured_demo_and_legacy_task_writes(
        monkeypatch, tmp_path):
    _app, client, owner_id = _signed_in_owner(
        monkeypatch, tmp_path, signup_mode="closed")
    monkeypatch.setenv("DEMO_PASSWORD", "legacy-demo-password-123")

    demo = client.post(
        "/demo-open",
        data={
            "demo_workspace": "demo@streetbanker.io",
            "demo_password": "legacy-demo-password-123",
        },
        follow_redirects=False,
    )
    legacy = client.post(
        "/team/manager/tasks",
        json={"title": "Bypass evidence", "assignee": "manager"},
        headers=COMPANY_OS_HEADERS,
    )

    assert demo.status_code == 302
    assert "/login?demo=unavailable" in demo.headers["Location"]
    assert legacy.status_code == 404
    assert store.list_manager_objectives(owner_id) == []


@pytest.mark.parametrize("owner_emails", ["", "one@example.com,two@example.com"])
def test_closed_mode_requires_exactly_one_explicit_owner(
        monkeypatch, tmp_path, owner_emails):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "owner-count.db"))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("SIGNUP_MODE", "closed")
    monkeypatch.setenv("OWNER_EMAILS", owner_emails)
    monkeypatch.delenv("OWNER_BOOTSTRAP_EMAIL", raising=False)

    with pytest.raises(RuntimeError, match="exactly one"):
        create_app()
