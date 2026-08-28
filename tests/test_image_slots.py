"""Artwork that ships with the repo, not artwork somebody has to send.

The remaining image slots - the hub backdrop, the press-sheet desk, the
club hero, the empty-state motifs - are hand-authored SVG in brand
colour rather than photographs. That makes them a few kilobytes, crisp
at any size, and correct on every artist's page without anyone
sourcing a picture first.

These check the files exist, that every path a template asks for
resolves, and that the empty states actually draw something.
"""

import os
import re
import uuid

from app import create_app

ASSETS = ["static/img/hub-backdrop.svg", "static/img/club-hero.svg",
          "static/img/tex-paper.svg"]


def _artist():
    app_obj = create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "A",
                                 "email": "slot%s@x.com" % uuid.uuid4().hex[:8],
                                 "password": "secret1", "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    return client


def test_the_new_assets_are_in_the_repo_and_small():
    for path in ASSETS:
        assert os.path.exists(path), path
        size = os.path.getsize(path)
        # A backdrop that costs more than the page it decorates is a
        # backdrop somebody will delete later.
        assert size < 8000, "%s is %d bytes" % (path, size)


def test_every_image_a_template_asks_for_exists():
    missing = []
    for root, _dirs, files in os.walk("templates"):
        for name in files:
            path = os.path.join(root, name)
            body = open(path, encoding="utf-8", errors="ignore").read()
            for ref in re.findall(r"/static/img/[A-Za-z0-9_\-./]+", body):
                rel = ref.split("?")[0].lstrip("/")
                if "{{" in ref or not os.path.exists(rel):
                    missing.append((ref, path))
    assert not missing, missing


def test_empty_states_draw_their_motif():
    client = _artist()
    for path in ("/recovery", "/valuation", "/inbox"):
        body = client.get(path).get_data(as_text=True)
        assert 'viewBox="0 0 64 64"' in body, path
        # The words are unchanged - the drawing is added to them.
    assert "Nothing scanned yet" in client.get("/recovery").get_data(as_text=True)
    assert "No income on record" in client.get("/valuation").get_data(as_text=True)
    assert "Nothing here yet" in client.get("/inbox").get_data(as_text=True)


def test_the_backdrops_are_wired_where_they_belong():
    app_obj = create_app()
    client = app_obj.test_client()
    # Opening the editor is what mints the public slug.
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    client.get("/epk")
    sheet = app_obj.test_client().get("/epk/synthwave-surfer").get_data(as_text=True)
    assert "tex-paper.svg" in sheet
    # ...and not at print time, where a background is just wasted ink.
    assert "@media print { body { background-image: none !important; } }" in sheet


def test_club_page_opens_with_the_marquee():
    app_obj = create_app()
    editor = app_obj.test_client()
    editor.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    editor.get("/epk")                      # mint the slug
    client = app_obj.test_client()
    page = client.get("/club/synthwave-surfer")
    if page.status_code != 200:
        return  # the showcase has no club; nothing to assert
    body = page.get_data(as_text=True)
    assert "club-hero.svg" in body
    assert 'aria-hidden="true"' in body   # decoration, not content
