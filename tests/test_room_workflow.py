import copy
import io
import uuid
import wave

from flask import Flask
from song_builder import init


def uid(): return str(uuid.uuid4())


def wav_bytes(seconds=4):
    out=io.BytesIO()
    with wave.open(out,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000)
        audio.writeframes(b'\x00\x00'*8000*seconds)
    return out.getvalue()


def app_client(tmp_path):
    app=Flask(__name__)
    app.config.update(TESTING=True,SECRET_KEY='workflow-tests',SONG_BUILDER_ENABLED=True)
    init(app,lambda:{'id':'alice'},data_dir=tmp_path)
    client=app.test_client()
    with client.session_transaction() as session:
        session['song_builder_csrf']={'account':'alice','token':'test-token'}
    return app,client,{'X-Song-Builder-CSRF':'test-token'}


def make_project(client,headers):
    asset=client.post('/song-builder/api/assets',headers=headers,
        data={'file':(io.BytesIO(wav_bytes()),'take.wav')}).json['asset']
    section={'id':uid(),'name':'Chorus','duration':4,'lyrics':'','direction':'','locked':False}
    track={'id':uid(),'name':'Lead vocal','gainDb':0,'pan':0,'muted':False,'solo':False}
    clip={'id':uid(),'trackId':track['id'],'sectionId':section['id'],'assetId':asset['id'],
          'offset':0,'sourceOffset':0,'duration':4,'loop':False,'gainDb':0}
    project={'schemaVersion':1,'id':uid(),'title':'Workflow song','tempo':100,'key':'D minor',
             'sections':[section],'tracks':[track],'clips':[clip]}
    saved=client.post('/song-builder/api/projects',headers=headers,json={'project':project})
    assert saved.status_code==201
    return saved.json


def metadata(**changes):
    value={'version':1,'groups':[],'scenes':[],'takes':[],'protections':[]}
    value.update(changes);return value


def test_workflow_page_and_default_metadata(tmp_path):
    _,client,headers=app_client(tmp_path);saved=make_project(client,headers);project=saved['project']
    page=client.get('/song-builder/workflow?project='+project['id'])
    assert page.status_code==200 and b'Group Buses' in page.data and b'Takes + Comping' in page.data
    result=client.get('/song-builder/api/workflow?projectId='+project['id'])
    assert result.status_code==200
    assert result.json=={'metadata':metadata(),'revision':0}


def test_workflow_roundtrip_and_revision_conflict(tmp_path):
    _,client,headers=app_client(tmp_path);saved=make_project(client,headers);project=saved['project']
    group={'id':uid(),'name':'Vocals','trackIds':[project['tracks'][0]['id']],
           'gainDb':0,'muted':False,'solo':False}
    first=client.put('/song-builder/api/workflow/'+project['id'],headers=headers,
                     json={'metadata':metadata(groups=[group]),'expectedRevision':0})
    assert first.status_code==200 and first.json['revision']==1
    assert first.json['metadata']['groups'][0]['name']=='Vocals'
    stale=client.put('/song-builder/api/workflow/'+project['id'],headers=headers,
                     json={'metadata':metadata(),'expectedRevision':0})
    assert stale.status_code==409 and stale.json['error']=='workflow_conflict'


def test_position_lock_blocks_move_but_allows_trim(tmp_path):
    _,client,headers=app_client(tmp_path);saved=make_project(client,headers);project=saved['project'];clip=project['clips'][0]
    rule=metadata(protections=[{'clipId':clip['id'],'mode':'position'}])
    assert client.put('/song-builder/api/workflow/'+project['id'],headers=headers,
                      json={'metadata':rule,'expectedRevision':0}).status_code==200
    moved=copy.deepcopy(project);moved['clips'][0]['offset']=.5;moved['clips'][0]['duration']=3.5
    blocked=client.put('/song-builder/api/projects/'+project['id'],headers=headers,
                       json={'project':moved,'expectedRevision':saved['revision']})
    assert blocked.status_code==409 and blocked.json['error']=='clip_protected'
    trimmed=copy.deepcopy(project);trimmed['clips'][0]['duration']=3.5
    allowed=client.put('/song-builder/api/projects/'+project['id'],headers=headers,
                       json={'project':trimmed,'expectedRevision':saved['revision']})
    assert allowed.status_code==200


def test_never_alter_blocks_clip_edit_and_removal(tmp_path):
    _,client,headers=app_client(tmp_path);saved=make_project(client,headers);project=saved['project'];clip=project['clips'][0]
    rule=metadata(protections=[{'clipId':clip['id'],'mode':'never'}])
    client.put('/song-builder/api/workflow/'+project['id'],headers=headers,
               json={'metadata':rule,'expectedRevision':0})
    changed=copy.deepcopy(project);changed['clips'][0]['gainDb']=-1
    response=client.put('/song-builder/api/projects/'+project['id'],headers=headers,
                        json={'project':changed,'expectedRevision':saved['revision']})
    assert response.status_code==409 and response.json['error']=='clip_protected'
    removed=copy.deepcopy(project);removed['clips']=[]
    response=client.put('/song-builder/api/projects/'+project['id'],headers=headers,
                        json={'project':removed,'expectedRevision':saved['revision']})
    assert response.status_code==409 and response.json['error']=='clip_protected'


def test_scene_and_take_snapshots_accept_owned_clip_shapes(tmp_path):
    _,client,headers=app_client(tmp_path);saved=make_project(client,headers);project=saved['project'];clip=project['clips'][0]
    workflow=metadata(
        scenes=[{'id':uid(),'sectionId':project['sections'][0]['id'],'name':'Chorus A','clips':[clip]}],
        takes=[{'id':uid(),'sectionId':project['sections'][0]['id'],'trackId':project['tracks'][0]['id'],
                'name':'Vocal 1','clips':[clip]}])
    response=client.put('/song-builder/api/workflow/'+project['id'],headers=headers,
                        json={'metadata':workflow,'expectedRevision':0})
    assert response.status_code==200
    assert response.json['metadata']['scenes'][0]['name']=='Chorus A'
    assert response.json['metadata']['takes'][0]['name']=='Vocal 1'
