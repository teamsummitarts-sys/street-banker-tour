"""Regression tests for the dedicated TOUR preview, not production auth."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[1]


def test_open_preview_renders_launcher_without_a_render_disk_or_login(tmp_path):
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
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'tour-app-body' in html
        assert 'Start a tour' in html
        assert 'Add a one-off show' in html
        assert 'Sign out' not in html
        assert response.headers['X-TOUR-Preview-Revision'] == preview.PREVIEW_REVISION
        assert response.headers['Cache-Control'].startswith('private, no-store')

        # Every launcher URL renders the same launcher instead of bouncing
        # through login or forcing an example tour. Flask's response.request
        # retains the browser's original URL when the preview WSGI shim rewrites
        # PATH_INFO internally, so content/status are the stable contract.
        for path in ('/', '/tours', '/tours/'):
            response = first.get(path, base_url=origin, follow_redirects=True)
            assert response.status_code == 200, path
            launcher = response.get_data(as_text=True)
            assert 'Start a tour' in launcher
            assert 'Add a one-off show' in launcher
            assert 'Sign out' not in launcher

        # Full-tour creation still uses the real TOUR route and then every
        # major workspace renders from that stored tour.
        response = first.post('/tours/new', base_url=origin, data={
            'name': 'Fall 2026', 'artist_name': 'Preview Artist',
            'start_date': '2026-10-01', 'end_date': '2026-10-20',
            'home_tz': 'America/New_York', 'currency': 'USD',
        }, follow_redirects=True)
        assert response.status_code == 200
        home = response.request.path
        assert home.startswith('/tours/')
        tour_id = home.rsplit('/', 1)[1]
        assert ts.get_tour(tour_id)['name'] == 'Fall 2026'
        for tab in ('calendar', 'shows', 'schedule', 'travel', 'hotels',
                    'people', 'tasks', 'money', 'merch'):
            response = first.get(home + '/' + tab, base_url=origin)
            assert response.status_code == 200, (tab, response.status_code)

        # A one-off show gets a minimal internal TOUR container and lands in
        # the same Show Command workspace, so the deep tools remain optional.
        response = first.post('/tour-share/preview/one-off', base_url=origin, data={
            'venue': 'The Basement East', 'city': 'Nashville, TN',
            'date': '2026-11-02', 'artist_name': 'Preview Artist',
            'home_tz': 'America/New_York', 'currency': 'USD',
        }, follow_redirects=True)
        assert response.status_code == 200
        one_off = response.request.path
        assert '/shows/' in one_off
        assert 'Additional show tools' in response.get_data(as_text=True)

        # A different browser cannot open the first browser's stored tour.
        second = app.test_client()
        response = second.get('/', base_url=origin, follow_redirects=True)
        assert response.status_code == 200
        assert 'Start a tour' in response.get_data(as_text=True)
        assert second.get(home, base_url=origin).status_code == 404

        # Invalid cookies recover at the launcher without revealing a login form.
        stale = app.test_client()
        stale.set_cookie('session', 'invalid-expired-preview-session',
                         domain='tour-preview.test')
        response = stale.get('/', base_url=origin, follow_redirects=True)
        assert response.status_code == 200
        assert 'Start a tour' in response.get_data(as_text=True)

        # The preview-specific worker is a self-removing worker, never the
        # production offline fallback that caused the iPhone screenshot.
        response = first.get('/sw.js', base_url=origin)
        sw = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'unregister' in sw
        assert 'offline.html' not in sw
        print('TOUR preview: launcher, full tour, one-off, stale session and no-offline-worker passed')
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
