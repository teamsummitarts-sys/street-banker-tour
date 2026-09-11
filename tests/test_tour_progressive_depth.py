from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def test_launcher_keeps_full_tour_and_one_off_paths_simple():
    page = read("templates/tour/index.html")
    assert "Start a tour" in page
    assert "Add a one-off show" in page
    assert "Run the road. Only as deep as you need." in page
    assert "to-tour-card" in page
    assert "to-form-optional" in page
    assert "/tour-share/preview/one-off" in page


def test_tour_shell_shows_essentials_before_deeper_tools():
    shell = read("templates/tour/_shell.html")
    assert "to-tour-core-nav" in shell
    assert "to-tour-tool-rack" in shell
    assert "Open only the parts this tour needs." in shell
    for key in ("home", "calendar", "shows", "my-day", "ask"):
        assert "'%s'" % key in shell
    for label in ("TODAY", "TOUR", "SHOW", "TRAVEL", "OPERATIONS", "MONEY", "TEAM"):
        assert "('%s'" % label in shell
    assert "to-mode-pill" in shell


def test_show_workspace_keeps_advanced_sections_behind_plus_rack():
    show = read("templates/tour/show.html")
    assert "Run the show" in show
    assert "Additional show tools" in show
    assert "Open only what this show needs. Leave the rest alone." in show
    for key in ("overview", "schedule", "advance", "tasks"):
        assert "'%s'" % key in show
    for key in ("travel", "hotel", "venue", "people", "guests", "money", "merch", "files", "notes"):
        assert "'%s'" % key in show


def test_calendar_has_fast_add_date_path_with_optional_depth():
    calendar = read("templates/tour/calendar.html")
    assert 'id="add-date"' in calendar
    assert "Add date / show" in calendar
    assert "Optional details · title, timezone, notes" in calendar
    assert "/import" in calendar


def test_refinement_css_is_mobile_first_and_loaded_globally():
    base = read("templates/tour/_app_base.html")
    css = read("static/css/tour-refine.css")
    assert "tour-refine.css?v=1" in base
    for selector in (".to-launch-actions", ".to-tour-grid", ".to-tour-core-nav",
                     ".to-tour-tool-rack", ".to-mode-pill", ".to-add-day"):
        assert selector in css
    assert "@media (max-width: 700px)" in css
    assert "@media (max-width: 430px)" in css
