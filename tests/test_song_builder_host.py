"""The portable module must not depend on V2 routes or tables."""
from flask import Flask
from song_builder import init


def test_alternate_host_prefix_and_private_storage(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='local-test-only', SONG_BUILDER_ENABLED=True)
    directory = tmp_path / 'independent-audio'
    init(app, lambda: {'id': 9}, data_dir=directory,
         url_prefix='/workbench', return_url='/home')
    client = app.test_client()
    page = client.get('/workbench/')
    assert page.status_code == 200
    assert b'/workbench/assets/ui/controller.mjs' in page.data
    assert b'href="/home"' in page.data
    assert client.get('/workbench/assets/core/project.mjs').status_code == 200
    assert client.get('/workbench/api/projects').json == {'projects': []}
    assert client.get('/workbench/api/capabilities').json['storage']['durable'] is False
    assert directory.exists()
    assert client.get('/song-builder/').status_code == 404


def test_disabled_registration_does_not_create_storage(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, SONG_BUILDER_ENABLED=False)
    directory = tmp_path / 'must-not-exist'
    init(app, lambda: {'id': 9}, data_dir=directory)
    assert app.test_client().get('/song-builder/').status_code == 404
    assert not directory.exists()
