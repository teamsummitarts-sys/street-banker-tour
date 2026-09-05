"""Phase 2 security and provider contract, using synthetic responses only."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from flask import Flask

from noise_lab import init


def make_host(user=None, provider=None, enabled=True):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='isolated-test-secret',
                      NOISE_LAB_ENABLED=True, NOISE_LAB_AI_ENABLED=enabled,
                      OPENAI_API_KEY='synthetic-key', NOISE_LAB_PROVIDER=provider)
    identity = {'user': user or {'id': 'account-one'}}
    init(app, current_user=lambda: identity['user'])
    return app, identity


def settings():
    return {'profile': 'metal-bloom', 'macros': {
        'texture': 72, 'motion': 20, 'space': 30, 'mix': 60}}


def envelope(value=None):
    return {'status': 'completed', 'output': [{
        'type': 'message', 'role': 'assistant', 'status': 'completed',
        'content': [{'type': 'output_text', 'text': json.dumps(value or settings())}]}],
        'usage': {'input_tokens': 350, 'output_tokens': 50}}


def csrf(client):
    client.get('/noise-lab/')
    with client.session_transaction() as session:
        return {'X-Noise-Lab-CSRF': session['noise_lab_csrf']['token']}


def test_generation_vertical_slice_requires_account_csrf_and_preserves_recipe_contract():
    calls = []
    def provider(prompt):
        calls.append(prompt)
        return envelope()
    app, identity = make_host(provider=provider)
    client = app.test_client()
    headers = csrf(client)
    assert client.post('/noise-lab/api/generate', json={'prompt': 'Dark metallic growl'}).status_code == 403
    response = client.post('/noise-lab/api/generate', headers=headers,
                           json={'prompt': 'Dark metallic growl'})
    assert response.status_code == 200
    assert calls == ['Dark metallic growl']
    assert response.json['recipe'] == {'schemaVersion': 1,
        'engineVersion': 'noise-lab-1.0.0', 'profile': 'metal-bloom',
        'macros': {**settings()['macros'], 'level': -12}}
    assert response.json['generationVersion'] == 'noise-lab-prompt-1.0.0'
    assert response.headers['Cache-Control'] == 'no-store'
    identity['user'] = {'id': 'account-two'}
    assert client.post('/noise-lab/api/generate', headers=headers,
                       json={'prompt': 'hello'}).status_code == 403
    assert client.get('/noise-lab/capabilities').json['generation']['usage']['attempts'] == 0
    identity['user'] = None
    assert client.post('/noise-lab/api/generate', headers=headers,
                       json={'prompt': 'hello'}).status_code == 401
    assert calls == ['Dark metallic growl']


@pytest.mark.parametrize('payload', [{}, {'prompt': ''}, {'prompt': 'x'*501},
    {'prompt': 2}, {'prompt': 'x', 'user_id': 'other'}, {'prompt': 'x', 'audio': 'data'},
    {'prompt': 'x', 'model': 'other'}, ['hello']])
def test_bad_requests_do_not_reach_provider_or_consume_allowance(payload):
    app, _ = make_host(provider=lambda _: pytest.fail('provider must not run'))
    client = app.test_client()
    response = client.post('/noise-lab/api/generate', headers=csrf(client), json=payload)
    assert response.status_code == 400
    assert client.get('/noise-lab/capabilities').json['generation']['usage']['attempts'] == 0


def test_cross_site_oversized_and_non_json_requests_are_rejected():
    app, _ = make_host(provider=lambda _: pytest.fail('provider must not run'))
    client = app.test_client()
    headers = csrf(client)
    for extra in ({'Origin': 'https://other.invalid'}, {'Sec-Fetch-Site': 'cross-site'}):
        assert client.post('/noise-lab/api/generate', headers={**headers, **extra}, json={'prompt': 'x'}).status_code == 403
    assert client.post('/noise-lab/api/generate', headers={'X-Noise-Lab-CSRF': 'é'}, json={'prompt': 'x'}).status_code == 403
    assert client.post('/noise-lab/api/generate', headers=headers, data='x', content_type='text/plain').status_code == 415
    assert client.post('/noise-lab/api/generate', headers=headers, data='x'*5000, content_type='application/json').status_code == 413


@pytest.mark.parametrize('value', [None, True, '50', -1, 101, float('nan'), float('inf')])
def test_generated_numbers_are_strict_not_coerced_or_clamped(value):
    from noise_lab.generation import parse_response, GenerationError
    output = settings(); output['macros']['texture'] = value
    with pytest.raises(GenerationError):
        parse_response(envelope(output))


def test_malformed_refused_truncated_and_executable_responses_are_rejected():
    from noise_lab.generation import parse_response, GenerationError
    bad = []
    x = envelope(); x['status'] = 'incomplete'; bad.append(x)
    x = envelope(); x['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'no'}]; bad.append(x)
    x = envelope(); x['output'][0]['content'][0]['text'] = '```json\n{}\n```'; bad.append(x)
    for output in ({**settings(), 'code': 'evil()'}, {**settings(), 'profile': '__proto__'},
                   {**settings(), 'macros': {**settings()['macros'], 'level': 0}}):
        bad.append(envelope(output))
    x = envelope(); x['output'][0]['content'][0]['text'] = '{"profile":"clean","profile":"metal-bloom","macros":{}}'; bad.append(x)
    x = envelope(); x['output'].append({'type': 'function_call', 'name': 'execute'}); bad.append(x)
    for response in bad:
        with pytest.raises(GenerationError): parse_response(response)


def test_unconfigured_disabled_and_provider_failure_are_honest_and_redacted():
    app, _ = make_host(provider=lambda _: (_ for _ in ()).throw(RuntimeError('secret upstream body')))
    client = app.test_client(); headers = csrf(client)
    app.config['OPENAI_API_KEY'] = ''
    assert client.get('/noise-lab/capabilities').json['ai_generation'] is False
    assert client.post('/noise-lab/api/generate', headers=headers, json={'prompt': 'x'}).status_code == 503
    app.config['OPENAI_API_KEY'] = 'synthetic-key'
    app.config['NOISE_LAB_AI_ENABLED'] = False
    assert client.post('/noise-lab/api/generate', headers=headers, json={'prompt': 'x'}).status_code == 503
    app.config['NOISE_LAB_AI_ENABLED'] = True
    response = client.post('/noise-lab/api/generate', headers=headers, json={'prompt': 'x'})
    assert response.status_code == 502
    assert b'secret' not in response.data
    status = client.get('/noise-lab/capabilities').json['generation']
    assert status['usage']['failures'] == 1
    assert status['usage']['unknown_usage_attempts'] == 1
    assert status['verified_live'] is False


def test_allowance_is_atomic_account_scoped_and_failure_does_not_refund_attempt():
    from noise_lab.generation import Allowance, GenerationError
    ledger = Allowance(clock=lambda: 100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        def reserve(_):
            try: ledger.reserve('one'); return True
            except GenerationError: return False
        assert sum(pool.map(reserve, range(4))) == 1
    ledger.finish('one', False, None)
    assert ledger.snapshot('one')['attempts'] == 1
    assert ledger.snapshot('two')['attempts'] == 0
    with pytest.raises(GenerationError): ledger.reserve('one')
    now = [0]
    ledger = Allowance(clock=lambda: now[0])
    for _ in range(20):
        ledger.reserve('one'); ledger.finish('one', True, {'input_tokens': 10, 'output_tokens': 4}); now[0] += 11
    with pytest.raises(GenerationError): ledger.reserve('one')
    assert ledger.snapshot('one')['remaining'] == 0
    assert ledger.snapshot('one')['input_tokens'] == 200


def test_real_adapter_request_is_text_only_bounded_and_non_storing(monkeypatch):
    from noise_lab import generation
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            captured['read_bound'] = size
            return json.dumps(envelope()).encode()
    class Opener:
        def open(self, req, timeout):
            captured.update(url=req.full_url, body=json.loads(req.data), timeout=timeout)
            return Response()
    monkeypatch.setattr(generation.urllib.request, 'build_opener', lambda *args: Opener())
    response = generation.request_settings('preserve attack', 'synthetic-key')
    body = captured['body']
    assert captured['url'] == 'https://api.openai.com/v1/responses'
    assert body['store'] is False and body['max_output_tokens'] == 256
    assert body['model'] == 'gpt-4.1-mini-2025-04-14'
    assert body['text']['format']['strict'] is True
    assert body['input'] == [{'role': 'user', 'content': 'preserve attack'}]
    assert 'tools' not in body
    assert captured['timeout'] == 12 and captured['read_bound'] == 32769
    assert response['status'] == 'completed'


def test_global_allowance_and_concurrency_limit_cannot_be_bypassed_with_new_accounts():
    from noise_lab.generation import Allowance, GenerationError
    ledger = Allowance(clock=lambda: 100)
    ledger.reserve('a'); ledger.reserve('b')
    with pytest.raises(GenerationError): ledger.reserve('c')
    ledger.finish('a', False, None); ledger.finish('b', False, None)
    for index in range(98):
        account = str(index)
        ledger.reserve(account); ledger.finish(account, False, None)
    with pytest.raises(GenerationError): ledger.reserve('brand-new-account')
    assert ledger.snapshot('brand-new-account')['remaining'] == 0


@pytest.mark.parametrize('status, expected', [(401, 'provider_auth'), (403, 'provider_auth'),
    (429, 'provider_limit'), (500, 'provider_unavailable')])
def test_provider_errors_are_not_retried_or_exposed(monkeypatch, status, expected):
    import io
    from noise_lab import generation
    calls = []
    class Opener:
        def open(self, req, timeout):
            calls.append(True)
            raise generation.urllib.error.HTTPError(req.full_url, status,
                'sensitive upstream detail', {}, io.BytesIO(b'private provider response'))
    monkeypatch.setattr(generation.urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(generation.GenerationError) as caught:
        generation.request_settings('synthetic description', 'synthetic-key')
    assert caught.value.code == expected and len(calls) == 1
    assert 'private' not in str(caught.value)


def test_oversized_response_and_redirect_are_rejected(monkeypatch):
    from noise_lab import generation
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return b'x'*size
    class Opener:
        def open(self, *args, **kwargs): return Response()
    monkeypatch.setattr(generation.urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(generation.GenerationError): generation.request_settings('x', 'synthetic')
    with pytest.raises(generation.GenerationError):
        generation.NoRedirect().redirect_request(None, None, 307, '', {}, 'https://other.invalid')


def test_generated_recipes_remain_readable_by_the_unchanged_browser_v1_reader():
    import subprocess
    from pathlib import Path
    from noise_lab.generation import parse_response, PROFILES
    outputs = []
    for profile in PROFILES:
        for edge in (0, 100):
            outputs.append(parse_response(envelope({'profile': profile,
                'macros': {key: edge for key in ('texture', 'motion', 'space', 'mix')}})))
    source = '''import {validateRecipe, PROFILES} from './noise_lab/static/engine/recipes.mjs';
let input=''; for await (const chunk of process.stdin) input+=chunk;
const rows=JSON.parse(input); for (const row of rows) validateRecipe(row);
if (new Set(rows.map(x=>x.profile)).size !== Object.keys(PROFILES).length) throw Error('profile contract drift');
console.log('v1 reader accepts all generated profile boundaries');'''
    result = subprocess.run(['node', '--input-type=module', '-e', source],
        input=json.dumps(outputs), cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
