from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def test_advance_is_the_email_workflow_not_a_separate_tool():
    advance = read("templates/tour/show/_advance.html")
    show = read("templates/tour/show.html")

    assert "Advance this show" in advance
    assert "Email the venue / promoter" in advance
    assert 'action="/tour-tools/advance/send"' in advance
    assert "Send advance" in advance
    assert "Paste / review reply" in advance
    assert "Email Venue" not in show
    assert "Email Venue" not in advance


def test_advance_uses_v2_resend_provider_and_records_send():
    integration = read("tour_preview_integrations.py")

    assert "import email_provider as emailer" in integration
    assert "emailer.configured()" in integration
    assert "emailer.send(recipient, subject" in integration
    assert '"advance_email"' in integration
    assert "ts.log_change" in integration
    assert "using_shared_test_sender" in integration


def test_google_places_photo_stays_server_side_and_degrades_cleanly():
    integration = read("tour_preview_integrations.py")
    show = read("templates/tour/show.html")
    shows = read("templates/tour/shows.html")

    assert "GOOGLE_PLACES_API_KEY" in integration
    assert "places.googleapis.com/v1/places:searchText" in integration
    assert '"X-Goog-Api-Key"' in integration
    assert "/tour-tools/venue-photo" in show
    assert "/tour-tools/venue-photo" in shows
    assert "tour_places_ready" in show
    assert "tour_places_ready" in shows
    # Browser URLs point to our proxy route, not to Google with a credential.
    assert "GOOGLE_PLACES_API_KEY" not in show
    assert "GOOGLE_PLACES_API_KEY" not in shows


def test_preview_registers_integrations():
    preview = read("tour_preview.py")
    assert "import tour_preview_integrations" in preview
    assert "tour_preview_integrations.register(app)" in preview
