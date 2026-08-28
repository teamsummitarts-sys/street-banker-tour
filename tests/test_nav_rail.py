"""The sidebar has two widths, and neither may hide a destination.

Expanded, it lists five hubs and about seventy pages - a wall of names
that pushes the actual work right. Rail mode drops it to icons. The
risk in collapsing a nav is that something becomes unreachable, so
these check the way back: every hub icon links to its desk page, the
full list is still in the DOM behind a hover or a focus, and the
palette still indexes everything.
"""

import hubs
from app import create_app


def _demo():
    client = create_app().test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    return client


def test_every_hub_has_a_rail_icon():
    """A hub with no icon would render an empty box in rail mode - the
    one state where the icon is the only thing identifying it."""
    for hkey, _name, _tag, _items in hubs.HUBS:
        assert hubs.HUB_ICONS.get(hkey), hkey
    for extra in ("account", "label", "community"):
        assert hubs.HUB_ICONS.get(extra), extra


def test_rail_controls_render():
    body = _demo().get("/overview").get_data(as_text=True)
    assert 'id="sb-rail-tgl"' in body        # the toggle
    assert 'id="sb-recent"' in body          # recently-opened slot
    assert "sb-hide-rail" in body            # things that fold away
    assert 'localStorage.getItem("sbRail")' in body   # applied before paint


def test_each_hub_icon_links_to_its_desk():
    body = _demo().get("/overview").get_data(as_text=True)
    for hkey, _name, _tag, _items in hubs.HUBS:
        assert 'href="/desk/%s"' % hkey in body


def test_collapsing_hides_nothing_from_the_dom():
    """Rail mode is CSS over the same markup, so every page in the nav is
    still there to hover, tab to, or search for."""
    body = _demo().get("/overview").get_data(as_text=True)
    for _hkey, _name, _tag, items in hubs.HUBS:
        for key, href, _icon, _label, _desc in items:
            assert 'href="%s"' % href in body, key


def test_desk_pages_still_open():
    client = _demo()
    for hkey, _name, _tag, _items in hubs.HUBS:
        assert client.get("/desk/%s" % hkey).status_code == 200


def test_fan_shell_has_no_artist_hubs_and_still_renders():
    client = create_app().test_client()
    client.post("/login", data={"email": "demo-fan@streetbanker.io",
                                "password": "sweep"})
    body = client.get("/discover").get_data(as_text=True)
    assert body
    assert 'href="/desk/money"' not in body


# --- login: two doors, named honestly --------------------------------------

def test_the_fan_link_lands_on_the_fan_side():
    """It read "GO TO FAN EXPERIENCE" and delivered /signup with Artist
    already ticked. A link that names a destination has to arrive there."""
    client = create_app().test_client()
    body = client.get("/signup?as=fan").get_data(as_text=True)
    fan = body.index('value="fan"')
    artist = body.index('value="artist"')
    assert 'checked' in body[fan:fan + 60]
    assert 'checked' not in body[artist:artist + 60]
    # The default is unchanged for everybody arriving without the flag.
    plain = client.get("/signup").get_data(as_text=True)
    a2 = plain.index('value="artist"')
    assert 'checked' in plain[a2:a2 + 60]
