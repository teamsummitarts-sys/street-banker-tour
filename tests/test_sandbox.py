"""Sandbox mode — the throwaway copy of the site cannot reach anything real.

Two halves, and the second matters as much as the first:

  With SANDBOX set, the three providers that touch the outside world all
  report themselves unconfigured, so nothing can be emailed, charged or
  written to the production bucket no matter which keys are present.

  With SANDBOX unset, every one of those code paths behaves exactly as it
  did before this feature existed. A safety net that changes the thing it
  is protecting is not a safety net, so production identity is pinned
  here rather than assumed.
"""
import blob_store
import email_provider
import sandbox
import stripe_provider

from app import create_app


# --- the switch itself ------------------------------------------------------

def test_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("SANDBOX", raising=False)
    assert sandbox.active() is False
    for falsey in ("", "0", "no", "off", "false", " "):
        monkeypatch.setenv("SANDBOX", falsey)
        assert sandbox.active() is False, falsey
    for truthy in ("1", "true", "TRUE", "yes", "on", " 1 "):
        monkeypatch.setenv("SANDBOX", truthy)
        assert sandbox.active() is True, truthy


# --- nothing reaches the real world -----------------------------------------

def test_a_sandbox_cannot_email_charge_or_write_to_the_bucket(monkeypatch):
    """Every key present and every provider still refuses."""
    monkeypatch.setenv("RESEND_API_KEY", "re_live_key")
    monkeypatch.setenv("EMAIL_FROM", "Artist <press@artist.example>")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_key")
    for key in ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID",
                "R2_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "set")

    monkeypatch.delenv("SANDBOX", raising=False)
    assert email_provider.configured() is True
    assert stripe_provider.configured() is True
    assert blob_store.configured() is True

    monkeypatch.setenv("SANDBOX", "1")
    assert email_provider.configured() is False
    assert stripe_provider.configured() is False
    assert blob_store.configured() is False


def test_send_refuses_outright_in_a_sandbox(monkeypatch):
    """send() gates on configured(), so this is the whole path closing —
    not a message that goes out and is discarded somewhere later."""
    monkeypatch.setenv("RESEND_API_KEY", "re_live_key")
    monkeypatch.setenv("SANDBOX", "1")

    def explode(*_a, **_k):                       # pragma: no cover
        raise AssertionError("a sandbox tried to make an HTTP call")

    monkeypatch.setattr(email_provider, "_http", explode)
    assert email_provider.send("someone@example.com", "s", "<p>b</p>") is False


def test_the_press_desk_will_not_send_from_a_sandbox(monkeypatch):
    """The specific hazard this was built for: the Press Desk mails
    journalists, and there is no undo for a sent email."""
    import press_desk

    monkeypatch.setenv("RESEND_API_KEY", "re_live_key")
    monkeypatch.setenv("EMAIL_FROM", "Artist <press@artist.example>")
    monkeypatch.setenv("SANDBOX", "1")
    assert press_desk.send_state()["platform"] is False


# --- the page says so -------------------------------------------------------

def test_pages_are_stamped_and_the_tab_is_renamed(monkeypatch):
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("SANDBOX_NAME", "Sandbox")
    body = create_app().test_client().get("/").get_data(as_text=True)
    assert "experiments only" in body
    assert "Nothing here reaches the live site" in body
    assert "<title>[SANDBOX] " in body
    # Fixed to the viewport, so it cannot move the layout it sits over.
    assert "position:fixed" in body
    assert "bottom:0" in body


def test_the_strip_names_the_deployment(monkeypatch):
    monkeypatch.setenv("SANDBOX", "1")
    monkeypatch.setenv("SANDBOX_NAME", "Nav experiment")
    body = create_app().test_client().get("/").get_data(as_text=True)
    assert "Nav experiment — experiments only" in body
    assert "<title>[NAV EXPERIMENT] " in body


def test_mark_leaves_a_fragment_alone():
    """The hook runs on every HTML response. Anything without a body is
    returned untouched rather than having a strip welded onto it."""
    import os
    os.environ["SANDBOX"] = "1"
    try:
        assert sandbox.mark("<li>a row</li>") == "<li>a row</li>"
        assert sandbox.mark("") == ""
        assert sandbox.mark(None) is None
    finally:
        del os.environ["SANDBOX"]


# --- production is untouched ------------------------------------------------

def test_production_html_is_byte_identical(monkeypatch):
    """The whole design rests on this: with SANDBOX unset the hook is
    registered but returns the response object unchanged."""
    monkeypatch.delenv("SANDBOX", raising=False)
    client = create_app().test_client()
    for path in ("/", "/login", "/press", "/remix-lab"):
        body = client.get(path).get_data(as_text=True)
        assert "experiments only" not in body, path
        assert "[SANDBOX]" not in body, path
        assert "2147483647" not in body, path       # the strip's z-index
    assert sandbox.mark("<html><body>x</body></html>") == "<html><body>x</body></html>"
