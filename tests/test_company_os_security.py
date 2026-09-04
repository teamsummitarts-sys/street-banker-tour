"""Security contract for the private, owner-only Company OS API.

These tests intentionally exercise HTTP behavior and persisted aggregate state.
They must not be weakened to mirror implementation helpers: the boundaries under
test are authentication, tenant ownership, request trust, optimistic locking,
and the requirement that completed work has approved evidence.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from werkzeug.security import generate_password_hash

import db as store
from app import create_app


V2_ORIGIN = "https://street-banker-v2-workflows.onrender.com"
V1_ORIGIN = "https://street-banker.onrender.com"
OWNER_A = "company-owner-a@example.com"
OWNER_B = "company-owner-b@example.com"
OUTSIDER = "company-outsider@example.com"
PASSWORD = "company-os-security-pass"


def _private_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "company-os.db"))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "company-os-test-secret-not-for-deploys")
    monkeypatch.setenv("PUBLIC_BASE_URL", V2_ORIGIN)
    monkeypatch.setenv("SIGNUP_MODE", "owner_only")
    monkeypatch.setenv("OWNER_EMAILS", f"{OWNER_A},{OWNER_B}")
    monkeypatch.setenv("DEMO_PASSWORD", "company-os-demo-test-secret")
    return create_app()


def _add_user(email):
    user_id = store.create_user(
        email,
        email.split("@", 1)[0],
        generate_password_hash(PASSWORD),
    )
    assert user_id is not None
    return user_id


def _signed_in_client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


@pytest.fixture
def private_clients(monkeypatch, tmp_path):
    app = _private_app(monkeypatch, tmp_path)
    owner_a_id = _add_user(OWNER_A)
    owner_b_id = _add_user(OWNER_B)
    outsider_id = _add_user(OUTSIDER)
    return {
        "app": app,
        "anonymous": app.test_client(),
        "owner_a": _signed_in_client(app, owner_a_id),
        "owner_b": _signed_in_client(app, owner_b_id),
        "outsider": _signed_in_client(app, outsider_id),
        "owner_a_id": owner_a_id,
        "owner_b_id": owner_b_id,
        "outsider_id": outsider_id,
    }


def _same_origin_headers():
    return {"Origin": V2_ORIGIN, "X-SB-Intent": "company-os-v2"}


def _assert_json(response, status, *, ok):
    assert response.status_code == status, response.get_data(as_text=True)
    assert response.is_json
    payload = response.get_json()
    assert isinstance(payload, dict)
    assert payload.get("ok") is ok
    return payload


def _assert_json_one_of(response, statuses, *, ok):
    assert response.status_code in statuses, response.get_data(as_text=True)
    assert response.is_json
    payload = response.get_json()
    assert isinstance(payload, dict)
    assert payload.get("ok") is ok
    return payload


def _create_objective(client, marker="SECURITY-CONTRACT"):
    response = client.post(
        "/api/company-os/objectives",
        json={
            "title": f"Launch the next single {marker}",
            "success_condition": "Approve a complete release plan with evidence",
            "target_date": "2026-10-30",
            "project": "Company OS security verification",
        },
        headers=_same_origin_headers(),
    )
    payload = _assert_json(response, 201, ok=True)
    assert isinstance(payload.get("objective"), dict)
    assert isinstance(payload.get("assignments"), list)
    assert isinstance(payload.get("deliverables"), list)
    assert isinstance(payload.get("activity"), list)
    assert payload["objective"]["title"].endswith(marker)
    assert payload["assignments"], "a real operating plan must contain assignments"
    return payload


def _state(client):
    payload = _assert_json(client.get("/api/company-os"), 200, ok=True)
    for key in (
        "objectives",
        "assignments",
        "deliverables",
        "activity",
        "mission_control",
    ):
        assert key in payload
    return payload


def _objective(state, objective_id):
    return next(item for item in state["objectives"] if item["id"] == objective_id)


def _assignment(state, assignment_id):
    return next(item for item in state["assignments"] if item["id"] == assignment_id)


def _deliverable(state, deliverable_id):
    return next(item for item in state["deliverables"] if item["id"] == deliverable_id)


def _approve_plan(client, created):
    objective = created["objective"]
    response = client.post(
        f"/api/company-os/objectives/{objective['id']}/approve-plan",
        json={"expected_version": objective["version"]},
        headers=_same_origin_headers(),
    )
    return _assert_json(response, 200, ok=True)


def _first_assignment_for(client, objective_id):
    state = _state(client)
    return next(
        item for item in state["assignments"]
        if item["objective_id"] == objective_id
    )


def _patch_assignment(client, assignment, status):
    return client.patch(
        f"/api/company-os/assignments/{assignment['id']}",
        json={"status": status, "expected_version": assignment["version"]},
        headers=_same_origin_headers(),
    )


def test_company_os_requires_authentication_and_owner_authorization(private_clients):
    anonymous = private_clients["anonymous"]
    outsider = private_clients["outsider"]

    _assert_json(anonymous.get("/api/company-os"), 401, ok=False)
    _assert_json(
        anonymous.post(
            "/api/company-os/objectives",
            json={"title": "Unauthorized objective"},
            headers=_same_origin_headers(),
        ),
        401,
        ok=False,
    )
    _assert_json(outsider.get("/api/company-os"), 403, ok=False)
    _assert_json(
        outsider.post(
            "/api/company-os/objectives",
            json={"title": "Paid plans are not owner authorization"},
            headers=_same_origin_headers(),
        ),
        403,
        ok=False,
    )


def test_company_os_rejects_cross_origin_mutation_without_writing(private_clients):
    owner = private_clients["owner_a"]
    before = _state(owner)

    for origin in ("https://attacker.example", V1_ORIGIN):
        response = owner.post(
            "/api/company-os/objectives",
            json={
                "title": "Cross-origin objective must never persist",
                "success_condition": "This request is rejected",
            },
            headers={"Origin": origin},
        )
        _assert_json(response, 403, ok=False)

    after = _state(owner)
    assert after["objectives"] == before["objectives"]
    assert after["assignments"] == before["assignments"]
    assert after["activity"] == before["activity"]


@pytest.mark.parametrize(
    "raw_body",
    (
        b"[",
        b"[]",
        b'"not-an-object"',
        b"null",
        b"7",
    ),
)
def test_objective_endpoint_rejects_malformed_or_non_object_json(
        private_clients, raw_body):
    owner = private_clients["owner_a"]
    response = owner.post(
        "/api/company-os/objectives",
        data=raw_body,
        content_type="application/json",
        headers=_same_origin_headers(),
    )
    _assert_json(response, 400, ok=False)
    assert _state(owner)["objectives"] == []


def test_client_cannot_choose_ownership_or_audit_identity(private_clients):
    owner = private_clients["owner_a"]
    before = _state(owner)
    created = owner.post(
        "/api/company-os/objectives",
        json={
            "title": "Ignore forged ownership",
            "success_condition": "Persist only server-authored identity",
            "target_date": "2026-10-30",
            "project": "Security",
            "user_id": private_clients["owner_b_id"],
            "owner_id": private_clients["owner_b_id"],
            "actor_user_id": private_clients["owner_b_id"],
            "created": "1999-01-01T00:00:00Z",
            "version": 9000,
            "status": "delivered",
        },
        headers=_same_origin_headers(),
    )
    _assert_json(created, 400, ok=False)
    after = _state(owner)
    assert after["objectives"] == before["objectives"]
    assert after["assignments"] == before["assignments"]
    assert after["activity"] == before["activity"]


def test_cross_owner_ids_are_not_found_at_every_mutation_boundary(private_clients):
    owner_a = private_clients["owner_a"]
    owner_b = private_clients["owner_b"]
    created = _create_objective(owner_a, "TENANT-A")
    objective = created["objective"]
    assignment = created["assignments"][0]

    attempts = (
        owner_b.post(
            f"/api/company-os/objectives/{objective['id']}/approve-plan",
            json={"expected_version": objective["version"]},
            headers=_same_origin_headers(),
        ),
        owner_b.patch(
            f"/api/company-os/assignments/{assignment['id']}",
            json={"status": "in_progress", "expected_version": assignment["version"]},
            headers=_same_origin_headers(),
        ),
        owner_b.post(
            f"/api/company-os/assignments/{assignment['id']}/deliverables",
            json={
                "title": "Stolen result",
                "summary": "An owner must not attach evidence to another account.",
                "evidence_refs": ["https://evidence.example/foreign-record"],
                "expected_version": assignment["version"],
            },
            headers=_same_origin_headers(),
        ),
    )
    for response in attempts:
        _assert_json(response, 404, ok=False)

    other_state = _state(owner_b)
    assert objective["id"] not in {
        item["id"] for item in other_state["objectives"]
    }
    assert assignment["id"] not in {
        item["id"] for item in other_state["assignments"]
    }


def test_illegal_transition_is_atomic_and_writes_no_activity(private_clients):
    owner = private_clients["owner_a"]
    created = _create_objective(owner, "ILLEGAL-TRANSITION")
    _approve_plan(owner, created)
    assignment = _first_assignment_for(owner, created["objective"]["id"])
    before = _state(owner)

    response = _patch_assignment(owner, assignment, "delivered")
    _assert_json(response, 409, ok=False)

    after = _state(owner)
    saved = _assignment(after, assignment["id"])
    assert saved["status"] == assignment["status"]
    assert saved["version"] == assignment["version"]
    assert after["activity"] == before["activity"]


def test_stale_assignment_version_conflicts_without_double_transition(private_clients):
    owner = private_clients["owner_a"]
    created = _create_objective(owner, "VERSION-CONFLICT")
    _approve_plan(owner, created)
    assignment = _first_assignment_for(owner, created["objective"]["id"])
    original_version = assignment["version"]

    first = _patch_assignment(owner, assignment, "in_progress")
    _assert_json(first, 200, ok=True)
    replay = owner.patch(
        f"/api/company-os/assignments/{assignment['id']}",
        json={"status": "review", "expected_version": original_version},
        headers=_same_origin_headers(),
    )
    _assert_json(replay, 409, ok=False)

    saved = _assignment(_state(owner), assignment["id"])
    assert saved["status"] == "in_progress"
    assert saved["version"] == original_version + 1


def test_stale_objective_version_cannot_approve_a_plan_twice(private_clients):
    owner = private_clients["owner_a"]
    created = _create_objective(owner, "PLAN-VERSION-CONFLICT")
    objective = created["objective"]

    _assert_json(
        owner.post(
            f"/api/company-os/objectives/{objective['id']}/approve-plan",
            json={"expected_version": objective["version"]},
            headers=_same_origin_headers(),
        ),
        200,
        ok=True,
    )
    replay = owner.post(
        f"/api/company-os/objectives/{objective['id']}/approve-plan",
        json={"expected_version": objective["version"]},
        headers=_same_origin_headers(),
    )
    _assert_json(replay, 409, ok=False)

    state = _state(owner)
    saved = _objective(state, objective["id"])
    assert saved["version"] == objective["version"] + 1
    assignment_ids = [
        item["id"] for item in state["assignments"]
        if item["objective_id"] == objective["id"]
    ]
    assert len(assignment_ids) == len(set(assignment_ids))


def test_review_and_delivery_require_real_approved_evidence(private_clients):
    owner = private_clients["owner_a"]
    other_owner = private_clients["owner_b"]
    created = _create_objective(owner, "EVIDENCE-GATE")
    _approve_plan(owner, created)
    objective_id = created["objective"]["id"]
    assignment = _first_assignment_for(owner, objective_id)
    evidence_id = store.add_vault_file(
        private_clients["owner_a_id"],
        "/security-test/release-decision.txt",
        "Release decision evidence",
        "document",
    )

    _assert_json(_patch_assignment(owner, assignment, "in_progress"), 200, ok=True)
    assignment = _assignment(_state(owner), assignment["id"])

    no_evidence = _patch_assignment(owner, assignment, "review")
    _assert_json_one_of(no_evidence, (409, 422), ok=False)
    unchanged = _assignment(_state(owner), assignment["id"])
    assert unchanged["status"] == "in_progress"
    assert unchanged["version"] == assignment["version"]

    incomplete = owner.post(
        f"/api/company-os/assignments/{assignment['id']}/deliverables",
        json={
            "title": "A&R release decision",
            "summary": "",
            "evidence_refs": [],
            "expected_version": assignment["version"],
        },
        headers=_same_origin_headers(),
    )
    _assert_json_one_of(incomplete, (400, 422), ok=False)

    submitted = owner.post(
        f"/api/company-os/assignments/{assignment['id']}/deliverables",
        json={
            "title": "A&R release decision",
            "summary": "GO: the master, ownership, and positioning are documented.",
            "evidence_refs": [f"vault_file:{evidence_id}"],
            "expected_version": assignment["version"],
        },
        headers=_same_origin_headers(),
    )
    submitted_payload = _assert_json(submitted, 201, ok=True)
    assert submitted_payload["deliverables"]
    deliverable_id = submitted_payload["deliverables"][-1]["id"]

    assignment = _assignment(_state(owner), assignment["id"])
    _assert_json(_patch_assignment(owner, assignment, "review"), 200, ok=True)
    assignment = _assignment(_state(owner), assignment["id"])

    unapproved = _patch_assignment(owner, assignment, "delivered")
    _assert_json_one_of(unapproved, (409, 422), ok=False)

    deliverable = _deliverable(_state(owner), deliverable_id)
    foreign_review = other_owner.post(
        f"/api/company-os/deliverables/{deliverable_id}/review",
        json={
            "decision": "approved",
            "note": "A different owner must not approve this.",
            "expected_version": deliverable["version"],
        },
        headers=_same_origin_headers(),
    )
    _assert_json(foreign_review, 404, ok=False)

    approved = owner.post(
        f"/api/company-os/deliverables/{deliverable_id}/review",
        json={
            "decision": "approved",
            "note": "Evidence reviewed and approved by the owner.",
            "expected_version": deliverable["version"],
        },
        headers=_same_origin_headers(),
    )
    _assert_json(approved, 200, ok=True)
    assert _deliverable(_state(owner), deliverable_id)["status"] == "approved"

    assignment = _assignment(_state(owner), assignment["id"])
    _assert_json(_patch_assignment(owner, assignment, "delivered"), 200, ok=True)
    delivered = _assignment(_state(owner), assignment["id"])
    assert delivered["status"] == "delivered"

    terminal = _patch_assignment(owner, delivered, "in_progress")
    _assert_json(terminal, 409, ok=False)
    assert _assignment(_state(owner), assignment["id"])["status"] == "delivered"


def _deployed_env(tmp_path, **updates):
    env = os.environ.copy()
    env.update({
        "APP_ENV": "staging",
        "SECRET_KEY": "deployed-company-os-secret-for-test-only",
        "DATABASE_PATH": str(tmp_path / "deployed.db"),
        "PUBLIC_BASE_URL": V2_ORIGIN,
        "SIGNUP_MODE": "owner_only",
        "OWNER_EMAILS": OWNER_A,
        "DEMO_PASSWORD": "deployed-demo-secret-for-test-only",
    })
    for key, value in updates.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _startup(env):
    return subprocess.run(
        [sys.executable, "-c", "from app import create_app; create_app()"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("signup_mode", [None, "", "owner-onyl", "open"])
def test_deployed_registration_configuration_fails_closed(tmp_path, signup_mode):
    script = """
try:
    from app import create_app
    import db as store
    application = create_app()
except RuntimeError:
    raise SystemExit(0)
client = application.test_client()
client.post(
    '/signup',
    data={
        'name': 'Public Visitor',
        'email': 'uninvited-public@example.net',
        'password': 'uninvited-security-pass',
    },
)
raise SystemExit(2 if store.get_user_by_email('uninvited-public@example.net') else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=_deployed_env(tmp_path, SIGNUP_MODE=signup_mode),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        "A deployed private V2 must refuse or safely override a missing, "
        "invalid, or open SIGNUP_MODE; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@pytest.mark.parametrize(
    "public_base_url",
    [None, "", V1_ORIGIN, V1_ORIGIN.upper(), V1_ORIGIN + "."],
)
def test_deployed_v2_refuses_missing_or_v1_public_origin(tmp_path, public_base_url):
    result = _startup(
        _deployed_env(tmp_path, PUBLIC_BASE_URL=public_base_url)
    )
    assert result.returncode != 0, (
        "V2 must not boot with a missing origin or the V1 origin; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_deployed_database_path_cannot_silently_fall_back(tmp_path):
    not_a_directory = tmp_path / "not-a-directory"
    not_a_directory.write_text("blocks directory creation", encoding="utf-8")
    result = _startup(
        _deployed_env(
            tmp_path,
            DATABASE_PATH=str(not_a_directory / "company-os.db"),
        )
    )
    assert result.returncode != 0, (
        "A configured but unusable database path must stop deployment instead "
        f"of falling back to ephemeral storage; stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


def test_deployed_build_never_accepts_the_known_demo_fallback(tmp_path):
    """Either refusing startup or disabling the fallback login is fail-closed."""
    script = """
try:
    from app import create_app
    application = create_app()
except RuntimeError:
    raise SystemExit(0)
client = application.test_client()
client.post(
    '/demo-open',
    data={'demo_workspace': 'demo@streetbanker.io', 'demo_password': 'sweep'},
    follow_redirects=False,
)
with client.session_transaction() as session:
    raise SystemExit(2 if 'user_id' in session else 0)
"""
    env = _deployed_env(tmp_path, DEMO_PASSWORD=None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        "A deployed private V2 accepted the repository's known demo fallback; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
