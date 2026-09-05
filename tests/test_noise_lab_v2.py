"""Exercise the actual V2 factory in an isolated process with no provider env."""
import os
from pathlib import Path
import subprocess
import sys


def test_noise_lab_uses_v2_identity_and_flag_without_new_database_tables(tmp_path):
    root = Path(__file__).resolve().parents[1]
    # Deliberately do not inherit provider credentials, production database paths,
    # secrets, Render flags or any other application environment from the runner.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "APP_ENV": "development",
        "DATABASE_PATH": str(tmp_path / "v2-test.db"),
        "NOISE_LAB_ENABLED": "1",
    }
    result = subprocess.run([sys.executable, "-c", r'''
import app
client = app.app.test_client()
anonymous = client.get('/noise-lab/capabilities')
assert anonymous.status_code == 302  # V2's existing session gate runs first.
assert anonymous.headers['Location'].startswith('/login?')
user = app.store.get_user_by_email('demo@streetbanker.io')
assert user is not None  # A synthetic fixture seeded only in this test process.
with client.session_transaction() as session:
    session['user_id'] = user['id']
response = client.get('/noise-lab/capabilities')
assert response.status_code == 200
assert response.json['ai_generation'] is False
assert response.headers['Cache-Control'] == 'no-store'
assert client.get('/noise-lab/').status_code == 200
with client.session_transaction() as session:
    csrf = session['noise_lab_csrf']['token']
headers = {'X-Noise-Lab-CSRF': csrf}
assert client.post('/noise-lab/api/generate', headers=headers, json={'prompt': 'soft echo'}).status_code == 503
assert client.post('/noise-lab/api/generate', headers=headers, json={'prompt': 'x', 'user_id': 'another'}).status_code == 400
app.app.config.update(TESTING=True, OPENAI_API_KEY='synthetic-test-key')
app.app.config['NOISE_LAB_PROVIDER'] = lambda _: {
    'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
    'content': [{'type': 'output_text', 'text': '{"profile":"clean","macros":{"texture":0,"motion":0,"space":10,"mix":25}}'}]}]}
generated = client.post('/noise-lab/api/generate', headers=headers, json={'prompt': 'soft echo'})
assert generated.status_code == 200
assert generated.json['recipe']['engineVersion'] == 'noise-lab-1.0.0'
assert generated.json['generation']['verified_live'] is False
assert client.get('/noise-lab/assets/engine/index.mjs').status_code == 200
with app.store.get_db() as db:
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
assert not any(name.startswith('noise_lab') for name in tables)
app.app.config['NOISE_LAB_ENABLED'] = False
assert client.get('/noise-lab/').status_code == 404
assert client.get('/noise-lab/assets/engine/index.mjs').status_code == 404
with client.session_transaction() as session:
    session['user_id'] = 'unrecognized-account'
app.app.config['NOISE_LAB_ENABLED'] = True
assert client.get('/noise-lab/capabilities').status_code == 302
assert client.post('/noise-lab/api/generate', headers=headers, json={'prompt': 'x'}).status_code == 302
print('V2 identity, assets, feature flag and no-migration boundary passed.')
'''], cwd=root, env=env, text=True, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
