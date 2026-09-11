"""Regression tests for the dedicated TOUR preview, not production auth."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[1]


def test_open_preview_renders_without_a_render_disk_or_login(tmp_path):
    # Importing tour_preview changes only the dedicated process's application.
    # A subprocess prevents those changes leaking into production-auth tests.
    env = os.environ.copy()
    for key in ("REACH_DB_PATH", "OWNER_BOOTSTRAP_EMAIL",
                "OWNER_BOOTSTRAP_PASSWORD_HASH", "OWNER_EMAILS"):
        env.pop(key, None)
    env.update({
        "APP_ENV": "development", "SIGNUP_MODE": "open", "RENDER": "true",
        "DATABASE_PATH": str(tmp_path / "preview.db"),
        "SECRET_KEY": "test-only-preview-secret-not-a-deployed-credential",
        "PUBLIC_BASE_URL": "https://tour-preview.test",
    })
    script = textwrap.dedent('''
        import os
        from pathlib import Path
        import tour_preview as preview
        import tour_store as ts

        app = preview.app
        app.config['TESTING'] = True
        origin = 'https://tour-preview.test'
        assert Path(os.environ['REACH_DB_PATH']) == (
            Path(os.environ['DATABASE_PATH']).parent / 'reach-preview.db'
        )

        first = app.test_client()
        response = first.get('/', base_url=origin, follow_redirects=True)
        assert response.status_code == 200
        assert response.request.path.startswith('/tours/')
        assert 'tour-app-body' in response.get_data(as_text=True)
        assert 'Sign out' not in response.get_data(as_text=True)
        assert response.headers['X-TOUR-Preview-Revision'] == preview.PREVIEW_REVISION
        assert response.headers['Cache-Control'] == 'private, no-store'
        home = response.request.path
        tour_id = home.rsplit('/', 1)[1]

        # The old middleware sent browsers with ANY session cookie to the
        # parent homepage. All entry URLs must now reuse the same tour.
        for path in ('/', '/tours', '/tours/'):
            response = first.get(path, base_url=origin, follow_redirects=True)
            assert response.status_code == 200, path
            assert response.request.path == home, path

        # Render the actual templates, not just the service health endpoint.
        for tab in ('calendar', 'shows', 'schedule', 'travel', 'hotels',
                    'people', 'tasks', 'money', 'merch'):
            response = first.get(home + '/' + tab, base_url=origin)
            assert response.status_code == 200, (tab, response.status_code)
        show_id = ts.list_shows(tour_id)[0]['id']
        for tab in ('overview', 'schedule', 'advance', 'travel', 'hotel', 'money'):
            response = first.get(home + '/shows/' + show_id + '?tab=' + tab,
                                 base_url=origin)
            assert response.status_code == 200, ('show', tab, response.status_code)

        # A new browser gets a different example; it cannot open the first
        # browser's tour by guessing or copying its URL.
        second = app.test_client()
        response = second.get('/', base_url=origin, follow_redirects=True)
        assert response.status_code == 200
        assert response.request.path != home
        assert second.get(home, base_url=origin).status_code == 404

        # Invalid cookies recover at the entry without revealing a login form.
        stale = app.test_client()
        stale.set_cookie('session', 'invalid-expired-preview-session',
                         domain='tour-preview.test')
        response = stale.get('/', base_url=origin, follow_redirects=True)
        assert response.status_code == 200
        assert response.request.path.startswith('/tours/')
        print('TOUR preview: fresh/repeat/stale sessions, isolation and 15 pages passed')
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
