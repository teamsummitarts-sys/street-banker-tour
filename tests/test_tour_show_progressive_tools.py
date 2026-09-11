from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def test_show_keeps_minimum_run_surface_and_expandable_tool_rack():
    page = read("templates/tour/show.html")

    assert "Run the show" in page
    assert "Additional show tools" in page
    assert "Open only what this show needs. Leave the rest alone." in page
    assert "<details class=\"to-tool-rack\"" in page
    assert "to-tool-link__plus" in page

    # The minimum show workflow stays immediately visible.
    for key in ("overview", "schedule", "advance", "tasks"):
        assert "'%s'" % key in page

    # Deep tools remain available without flattening them into the main nav.
    for key in ("travel", "hotel", "venue", "people", "guests", "vip",
                "production", "money", "merch", "marketing", "content",
                "setlist", "files", "notes", "activity"):
        assert "'%s'" % key in page

    # Existing server-side permission checks still gate sensitive tools.
    for scope in ("financials", "merch", "guests", "vip", "marketing",
                  "content", "advance", "files"):
        assert "'%s'" % scope in page
