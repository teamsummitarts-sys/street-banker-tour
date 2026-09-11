from app import create_app
from landing_config import get_landing_config


APPROVED_SUPPORT_EMAIL = "support@streetbankermusic.com"
APPROVED_COMPANY = "Street Banker, Inc."


def test_public_support_and_legal_surfaces_are_reachable_and_current():
    client = create_app().test_client()

    support = client.get("/support")
    assert support.status_code == 200
    support_body = support.get_data(as_text=True)
    assert "Support and account requests" in support_body
    assert APPROVED_SUPPORT_EMAIL in support_body
    assert APPROVED_COMPANY in support_body
    assert "passwords" in support_body.lower()

    for path, title in (("/terms", "Terms of Service"), ("/privacy", "Privacy Policy")):
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert title in body
        assert APPROVED_SUPPORT_EMAIL in body
        assert 'href="/support"' in body


def test_landing_and_login_use_approved_company_and_support():
    client = create_app().test_client()

    landing = client.get("/").get_data(as_text=True)
    assert APPROVED_COMPANY in landing
    assert 'href="/support"' in landing

    login = client.get("/login").get_data(as_text=True)
    assert APPROVED_COMPANY in login
    assert 'href="/support"' in login

    footer_links = [
        link
        for column in get_landing_config()["footer"]["columns"]
        for link in column["links"]
    ]
    assert {"label": "Support", "href": "/support"} in footer_links
