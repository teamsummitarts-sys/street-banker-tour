from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def test_tour_uses_its_own_product_shell():
    shell = read("templates/tour/_shell.html")
    index = read("templates/tour/index.html")
    app_base = read("templates/tour/_app_base.html")

    assert '{% extends "tour/_app_base.html" %}' in shell
    assert '{% extends "tour/_app_base.html" %}' in index
    assert '{% extends "base.html" %}' not in shell
    assert '{% extends "base.html" %}' not in index
    assert "ROYALTY SWEEP" not in app_base
    assert "TOUR" in app_base
    assert '/static/img/tour-logo.svg' in app_base
    assert 'alt="TOUR by Street Banker"' in app_base


def test_tour_switcher_shows_suite_without_linking_development_room_route():
    app_base = read("templates/tour/_app_base.html")

    assert 'href="/command-center"' in app_base
    assert 'href="/overview"' not in app_base
    assert 'href="/reach/"' in app_base
    assert 'href="/noise-lab/"' in app_base
    assert 'href="/tours"' in app_base
    assert "THE ROOM" in app_base
    assert 'aria-disabled="true"' in app_base
    # The Room currently lives behind the default-off Portable Song Builder.
    # Keep the product visible, but do not advertise that development route.
    assert 'href="/song-builder' not in app_base


def test_tour_navigation_groups_existing_routes_without_rewriting_them():
    shell = read("templates/tour/_shell.html")

    for label in ("TODAY", "TOUR", "SHOW", "TRAVEL", "OPERATIONS", "MONEY", "TEAM"):
        assert "('%s'" % label in shell
    for key in ("home", "my-day", "changes", "ask", "calendar", "shows", "map",
                "schedule", "venues", "travel", "hotels", "people", "tasks", "files",
                "guests", "marketing", "content", "import", "exports", "money", "merch",
                "share", "team", "settings"):
        assert "'%s'" % key in shell
    assert "/tours/{{ tour['id'] }}" in shell


def test_tour_standalone_css_keeps_mobile_layouts_first_class():
    css = read("static/css/tour-app.css")

    assert ".tour-appbar" in css
    assert ".to-product-nav" in css
    assert ".is-unavailable" in css
    assert "@media (max-width: 760px)" in css
    assert "@media (max-width: 420px)" in css
