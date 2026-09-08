import io
import math
import struct
import uuid
import wave

from flask import Flask
from song_builder import init


def audio(seconds=4, amplitude=0.25):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as f:
        f.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        f.writeframes(b''.join(struct.pack('<h', round(amplitude * 32767 * math.sin(2 * math.pi * 440 * i / 8000))) for i in range(seconds * 8000)))
    return stream.getvalue()


def fixture(tmp_path, **config):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='tests', SONG_BUILDER_ENABLED=True,
                      ROOM_ANALYSIS_AUTOSTART=False, **config)
    identity = {'id': 'alice'}
    init(app, lambda: identity, data_dir=tmp_path)
    client = app.test_client()
    with client.session_transaction() as s:
        s['song_builder_csrf'] = {'account': 'alice', 'token': 'test'}
    return app, client, identity, {'X-Song-Builder-CSRF': 'test'}


def upload(client, headers):
    r = client.post('/song-builder/api/analysis/uploads', headers=headers,
                    data={'authorized': 'true', 'file': (io.BytesIO(audio()), 'reference.wav')})
    assert r.status_code == 201, r.json
    return r.json['track']


def payload(track, destination='local'):
    return dict(requestId=str(uuid.uuid4()), mode='dna', destination=destination, consent=None,
                goal='', sections=[], tracks=[dict(id=track['id'], weight=1, muted=False, keep=[], avoid=[])])


def test_upload_is_private_and_does_not_analyze_or_send(tmp_path):
    app, client, identity, headers = fixture(tmp_path)
    t = upload(client, headers)
    assert t['status'] == 'ready'
    assert client.get('/song-builder/api/analysis/runs').json['runs'] == []
    identity['id'] = 'bob'
    assert client.get('/song-builder/api/analysis/uploads').json['tracks'] == []
    assert client.post('/song-builder/api/analysis/runs', headers=headers, json=payload(t)).status_code == 403


def test_local_analysis_is_measured_idempotent_and_releases_audio(tmp_path):
    app, client, _, headers = fixture(tmp_path)
    t = upload(client, headers)
    p = payload(t)
    r = client.post('/song-builder/api/analysis/runs', headers=headers, json=p)
    assert r.status_code == 202, r.json
    run_id = r.json['run']['id']
    assert client.post('/song-builder/api/analysis/runs', headers=headers, json=p).json['run']['id'] == run_id
    app.extensions['room_analysis'].run(run_id)
    result = client.get('/song-builder/api/analysis/runs/' + run_id).json['run']
    assert result['status'] == 'succeeded'
    measured = result['report']['tracks'][0]['measured']
    assert measured['durationSeconds'] == 4
    assert abs(measured['peakDbfs'] + 12.04) < .1
    assert abs(measured['rmsDbfs'] + 15.05) < .1
    assert result['report']['tracks'][0]['interpretation'] is None
    assert client.get('/song-builder/api/analysis/uploads').json['tracks'] == []


def test_destination_missing_or_unconsented_fails_without_consuming_upload(tmp_path):
    _, client, _, headers = fixture(tmp_path)
    t = upload(client, headers)
    assert client.post('/song-builder/api/analysis/runs', headers=headers, json=payload(t, 'gemini')).status_code == 503
    assert len(client.get('/song-builder/api/analysis/uploads').json['tracks']) == 1


def test_rejects_url_audio_all_muted_and_unknown_owner(tmp_path):
    _, client, identity, headers = fixture(tmp_path)
    t = upload(client, headers)
    p = payload(t)
    p['tracks'][0]['id'] = 'https://open.spotify.com/track/example'
    assert client.post('/song-builder/api/analysis/runs', headers=headers, json=p).status_code == 400
    p = payload(t)
    p['tracks'][0]['muted'] = True
    assert client.post('/song-builder/api/analysis/runs', headers=headers, json=p).status_code == 400
    identity['id'] = 'bob'
    with client.session_transaction() as s:
        s['song_builder_csrf'] = {'account': 'bob', 'token': 'test'}
    assert client.post('/song-builder/api/analysis/runs', headers=headers, json=payload(t)).status_code == 404


def test_authorization_required_and_bad_audio_not_stored(tmp_path):
    _, client, _, headers = fixture(tmp_path)
    assert client.post('/song-builder/api/analysis/uploads', headers=headers,
        data={'file': (io.BytesIO(audio()), 'x.wav')}).status_code == 400
    assert client.post('/song-builder/api/analysis/uploads', headers=headers,
        data={'authorized': 'true', 'file': (io.BytesIO(b'bad'), 'x.wav')}).status_code == 400
    assert client.get('/song-builder/api/analysis/uploads').json['tracks'] == []


def interpretation():
    return {'traits': {k: ['dry drums'] if k == 'instrumentation' else [] for k in
            ('broadGenre','microgenres','mood','instrumentation','vocals','production','texture','rhythm','energy')},
            'key': {'value': 'A minor', 'confidence': 'low'}, 'works': ['Keep the sparse opening.'],
            'recommendations': [dict(start=1,end=2,section='Opening',change='Audition 1 dB less drum level.',
                benefit='More space.',tradeoff='Less impact.',confidence='low',identityRisk='low',requires='stems')]}


def test_explicit_assignment_routes_only_active_audio_and_exports_decisions(tmp_path):
    calls=[]
    adapter=dict(label='Test destination', model='fixture-v1', detail='Test-only external destination.',
                 external=True,available=True,analyze=lambda data,measure,context:(calls.append((data,context)) or interpretation()))
    app, client, _, headers=fixture(tmp_path,ROOM_ANALYSIS_ADAPTERS={'fixture':adapter})
    a,b=upload(client,headers),upload(client,headers)
    p=payload(a,'fixture');p['mode']='improve'
    p['tracks'].append(dict(id=b['id'],weight=1,muted=True,keep=[],avoid=[]))
    p['sections']=[dict(name='Opening',start=0,end=4)]
    assert client.post('/song-builder/api/analysis/runs',headers=headers,json=p).status_code==400
    assert calls==[]
    d=next(d for d in client.get('/song-builder/api/analysis/destinations').json['destinations'] if d['id']=='fixture')
    p['consent']=d['consentToken']
    run=client.post('/song-builder/api/analysis/runs',headers=headers,json=p).json['run']
    assert calls==[]
    app.extensions['room_analysis'].run(run['id'])
    assert len(calls)==1 and calls[0][0]==audio()
    assert calls[0][1]['sections']==p['sections']
    assert [t['id'] for t in client.get('/song-builder/api/analysis/uploads').json['tracks']]==[b['id']]
    url='/song-builder/api/analysis/runs/'+run['id']
    report=client.get(url).json['run']['report']
    assert report['tracks'][0]['interpretation']['key']['confidence']=='low'
    assert len(report['blueprint']['prompt'])<1000
    review=dict(expectedRevision=1,decisions={'change-1':'accepted'},prompt='Original dry drums; no artist imitation.')
    assert client.patch(url,headers=headers,json=review).status_code==200
    assert client.patch(url,headers=headers,json=review).status_code==409
    for kind in ['full','producer','timecoded','prompt','markdown','text','json']:
        result=client.get(url+'/export/'+kind)
        assert result.status_code==200 and 'attachment' in result.headers['Content-Disposition']
    assert b'Audition 1 dB less' in client.get(url+'/export/producer').data
    review.update(expectedRevision=2,decisions={'change-1':'rejected'})
    assert client.patch(url,headers=headers,json=review).status_code==200
    assert b'Audition 1 dB less' not in client.get(url+'/export/producer').data


def test_invalid_provider_response_releases_copies_without_retry(tmp_path):
    calls=[]
    bad=interpretation();bad['recommendations'][0]['end']=999
    app,client,_,h=fixture(tmp_path,ROOM_ANALYSIS_ADAPTERS={'fixture':dict(
        label='Test',model='v1',detail='Internal test.',external=False,available=True,
        analyze=lambda *args:(calls.append(1) or bad))})
    p=payload(upload(client,h),'fixture')
    run=client.post('/song-builder/api/analysis/runs',headers=h,json=p).json['run']
    service=app.extensions['room_analysis'];service.run(run['id']);service.run(run['id'])
    assert calls==[1]
    r=client.get('/song-builder/api/analysis/runs/'+run['id']).json['run']
    assert r['status']=='failed' and r['report'] is None
    assert client.get('/song-builder/api/analysis/uploads').json['tracks']==[]


def test_expiry_removes_only_analysis_copies(tmp_path):
    app,client,_,h=fixture(tmp_path)
    t=upload(client,h)
    saved=tmp_path/'approved-song.wav';saved.write_bytes(audio())
    service=app.extensions['room_analysis']
    with service.db() as db: db.execute('UPDATE uploads SET expires=0 WHERE id=?',(t['id'],))
    service.purge()
    assert client.get('/song-builder/api/analysis/uploads').json['tracks']==[]
    assert saved.read_bytes()==audio()


def test_run_report_owner_isolation_and_prompt_limit(tmp_path):
    app,client,identity,h=fixture(tmp_path)
    run=client.post('/song-builder/api/analysis/runs',headers=h,json=payload(upload(client,h))).json['run']
    app.extensions['room_analysis'].run(run['id'])
    url='/song-builder/api/analysis/runs/'+run['id']
    assert client.patch(url,headers=h,json=dict(expectedRevision=1,decisions={},prompt='x'*1000)).status_code==400
    identity['id']='bob'
    assert client.get(url).status_code==404
    assert client.get(url+'/export/json').status_code==404


def test_blend_uses_weights_and_global_avoid_without_muted_traits():
    from song_builder.analysis_report import build_report
    from song_builder.analysis_signal import measure
    a,b=dict(id='a',weight=3,muted=False,keep=['dry','close'],avoid=['washy']),dict(id='b',weight=1,muted=False,keep=['dry','washy'],avoid=[])
    results=[dict(id=t['id'],name='test',measured=measure(audio()),interpretation=None) for t in (a,b)]
    report=build_report(results,dict(mode='dna',tracks=[a,b],sections=[]))
    assert report['blend']['shared']==[dict(trait='dry',weight=1.0,trackIds=['a','b'])]
    assert 'washy' not in report['blend']['center']
    assert report['blueprint']['prompt'].endswith('Avoid: washy')


def test_silence_does_not_invent_tempo_key_or_changes():
    from song_builder.analysis_signal import measure, conservative_notes
    m=measure(audio(amplitude=0))
    assert m['rmsDbfs'] is None and m['peakDbfs'] is None
    assert m['tempoEstimate']['bpm'] is None and m['keyEstimate']['value'] is None
    assert conservative_notes(m)[1]==[]


def test_analysis_page_preserves_private_host_policy(tmp_path):
    _,client,identity,h=fixture(tmp_path)
    r=client.get('/song-builder/analyze')
    assert r.status_code==200
    assert b'Assign &amp; direct' in r.data
    assert r.headers['Cache-Control']=='private, no-store'
    assert "connect-src 'self'" in r.headers['Content-Security-Policy']
    identity.clear()
    assert client.get('/song-builder/analyze').status_code==401


def test_gemini_adapter_uses_fixed_endpoint_inline_audio_and_bounded_json(tmp_path, monkeypatch):
    import json
    from song_builder import analysis_provider as provider
    from song_builder.analysis_signal import measure
    seen={}
    class Reply:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,size):
            return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(interpretation())}]}}]}).encode()
    class Opener:
        def open(self,request,timeout):
            seen.update(url=request.full_url,body=json.loads(request.data),timeout=timeout,key=request.get_header('X-goog-api-key'))
            return Reply()
    monkeypatch.setattr(provider.urllib.request,'build_opener',lambda *args:Opener())
    app,_,_,_=fixture(tmp_path,ROOM_ANALYSIS_GEMINI_KEY='fake-test-key',ROOM_ANALYSIS_GEMINI_MODEL='gemini-test',ROOM_ANALYSIS_GEMINI_PAID_CONFIRMED='true')
    d=provider.select(app,'gemini')
    result=provider.analyze(app,d,audio(),measure(audio()),{'mode':'improve'})
    assert result==interpretation()
    assert seen['url']=='https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent'
    assert seen['timeout']==60 and seen['key']=='fake-test-key'
    assert 'inlineData' in seen['body']['contents'][0]['parts'][0]
    assert 'fileData' not in str(seen['body'])
    assert seen['body']['generationConfig']['responseMimeType']=='application/json'
    assert provider.NoRedirect().redirect_request is not None


def test_configuration_change_after_consent_does_not_send(tmp_path):
    calls=[]
    adapter=dict(label='Test',model='v1',detail='External test.',external=True,available=True,
                 analyze=lambda *args:(calls.append(1) or interpretation()))
    app,client,_,h=fixture(tmp_path,ROOM_ANALYSIS_ADAPTERS={'fixture':adapter})
    p=payload(upload(client,h),'fixture')
    p['consent']=next(d for d in client.get('/song-builder/api/analysis/destinations').json['destinations'] if d['id']=='fixture')['consentToken']
    r=client.post('/song-builder/api/analysis/runs',headers=h,json=p).json['run']
    adapter['model']='v2'
    app.extensions['room_analysis'].run(r['id'])
    assert calls==[]
    assert client.get('/song-builder/api/analysis/runs/'+r['id']).json['run']['status']=='failed'


def test_tempo_periodicity_on_known_120_bpm_pulses():
    from song_builder.analysis_signal import measure
    stream=io.BytesIO()
    with wave.open(stream,'wb') as f:
        f.setparams((1,2,8000,0,'NONE','not compressed'))
        f.writeframes(b''.join(struct.pack('<h',12000 if i%4000<160 else 0) for i in range(8000*12)))
    m=measure(stream.getvalue())
    assert abs(m['tempoEstimate']['bpm']-120)<1
    assert m['tempoEstimate']['alternatives']==[60,240]


def test_blueprint_reserves_exclusions_and_reports_overflow():
    from song_builder.analysis_report import build_report
    from song_builder.analysis_signal import measure
    track = dict(id='a', weight=1, muted=False, keep=['warm'], avoid=['harsh cymbals'])
    result = dict(id='a', measured=measure(audio()), interpretation=None)
    data = dict(mode='dna', tracks=[track], sections=[], goal='x' * 990)
    blueprint = build_report([result], data)['blueprint']
    assert len(blueprint['prompt']) < 1000
    assert blueprint['prompt'].endswith('Avoid: harsh cymbals')
    assert blueprint['omitted'] == ['Goal: '+data['goal']]
    assert 'review omitted details' in blueprint['note']
    data['goal'] = 'Restrained chorus'
    assert 'Goal: Restrained chorus' in build_report([result], data)['blueprint']['prompt']
