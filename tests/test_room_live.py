import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from test_room_collaboration import setup, invite, join


def live(client,headers,pid,sid,scope=None):
    return client.post('/song-builder/api/projects/'+pid+'/live',headers=headers,json={'sessionId':sid,'scope':scope})


def save(client,headers,project,revision,sid=None):
    body={'project':project,'expectedRevision':revision}
    if sid:body['liveSession']=sid
    return client.put('/song-builder/api/projects/'+project['id'],headers=headers,json=body)


def pair(tmp_path):
    app,owner,h,saved=setup(tmp_path);p=copy.deepcopy(saved['project'])
    track=copy.deepcopy(p['tracks'][0]);track['id']=str(uuid.uuid4());track['name']='Drums';p['tracks'].append(track)
    assert save(owner,h,p,1).status_code==200
    guest,gh=join(app,invite(owner,h,saved));a,b=str(uuid.uuid4()),str(uuid.uuid4())
    assert live(owner,h,p['id'],a,'track:'+p['tracks'][0]['id']).status_code==200
    assert live(guest,gh,p['id'],b,'track:'+track['id']).status_code==200
    return app,owner,h,guest,gh,p,a,b


def test_concurrent_different_tracks_merge_without_losing_either_edit(tmp_path):
    app,owner,h,guest,gh,p,a,b=pair(tmp_path);left=copy.deepcopy(p);right=copy.deepcopy(p)
    left['tracks'][0]['gainDb']=-5;right['tracks'][1]['pan']=.5
    ready=Barrier(2)
    def submit(client,headers,value,sid):
        ready.wait();return save(client,headers,value,2,sid)
    with ThreadPoolExecutor(2) as pool:
        one=pool.submit(submit,owner,h,left,a);two=pool.submit(submit,guest,gh,right,b)
        responses=[one.result(),two.result()]
    assert [r.status_code for r in responses]==[200,200]
    result=owner.get('/song-builder/api/projects/'+p['id']).json
    assert result['revision']==4
    assert result['project']['tracks'][0]['gainDb']==-5
    assert result['project']['tracks'][1]['pan']==.5
    assert result['project']['clips']==p['clips']


def test_leases_block_same_track_structure_and_nonlive_writes(tmp_path):
    app,owner,h,guest,gh,p,a,b=pair(tmp_path)
    assert live(guest,gh,p['id'],b,'track:'+p['tracks'][0]['id']).status_code==409
    assert live(owner,h,p['id'],a,'arrangement').status_code==409
    edit=copy.deepcopy(p);edit['tracks'][1]['gainDb']=-3
    assert save(owner,h,edit,2,a).status_code==409
    assert save(owner,h,edit,2).status_code==409
    assert owner.get('/song-builder/api/projects/'+p['id']).json['revision']==2


def test_stale_same_track_rejected_after_release_and_expiry(tmp_path):
    app,owner,h,guest,gh,p,a,b=pair(tmp_path)
    edited=copy.deepcopy(p);edited['tracks'][0]['gainDb']=-4
    assert save(owner,h,edited,2,a).status_code==200
    assert owner.delete('/song-builder/api/projects/'+p['id']+'/live',headers=h,json={'sessionId':a}).status_code==200
    assert live(guest,gh,p['id'],b,'track:'+p['tracks'][0]['id']).status_code==200
    stale=copy.deepcopy(p);stale['tracks'][0]['pan']=.5
    assert save(guest,gh,stale,2,b).status_code==409
    service=app.extensions['room_collaboration']
    with service.store.connection(write=True) as db:db.execute('UPDATE room_live_sessions SET expires=0')
    assert save(guest,gh,edited,3,b).status_code==409
    assert live(owner,h,p['id'],a,'arrangement').status_code==200


def test_viewer_presence_and_revocation_cannot_claim_or_leak(tmp_path):
    app,owner,h,saved=setup(tmp_path);inv=invite(owner,h,saved,'viewer');guest,gh=join(app,inv);sid=str(uuid.uuid4());pid=saved['project']['id']
    assert live(guest,gh,pid,sid).status_code==200
    assert live(guest,gh,pid,sid,'arrangement').status_code==403
    status=guest.get('/song-builder/api/projects/'+pid+'/live');assert status.status_code==200
    assert status.json['presence'][0]['name']=='Guest player'
    assert 'actor' not in status.json['presence'][0]
    assert guest.get('/song-builder/api/projects/'+str(uuid.uuid4())+'/live').status_code==404
    owner.delete('/song-builder/api/projects/'+pid+'/invitations/'+inv['id'],headers=h)
    assert guest.get('/song-builder/api/projects/'+pid+'/live').status_code==401
    assert owner.get('/song-builder/api/projects/'+pid+'/live').json['presence']==[]


def test_live_save_still_enforces_clip_protection_in_transaction(tmp_path):
    app,owner,h,guest,gh,p,a,b=pair(tmp_path);pid=p['id']
    metadata={'version':1,'groups':[],'scenes':[],'takes':[],'protections':[{'clipId':p['clips'][0]['id'],'mode':'never'}]}
    assert owner.put('/song-builder/api/workflow/'+pid,headers=h,json={'metadata':metadata,'expectedRevision':0}).status_code==200
    altered=copy.deepcopy(p);altered['clips'][0]['gainDb']=-6
    assert save(owner,h,altered,2,a).status_code==409
    assert owner.get('/song-builder/api/projects/'+pid).json['revision']==2


def test_listening_session_cannot_save_and_session_ids_do_not_grant_access(tmp_path):
    app,owner,h,saved=setup(tmp_path);guest,gh=join(app,invite(owner,h,saved));pid=saved['project']['id'];sid=str(uuid.uuid4())
    assert live(owner,h,pid,sid).status_code==200
    p=copy.deepcopy(saved['project']);p['title']='Unauthorized live edit'
    assert save(owner,h,p,1,sid).status_code==409
    assert live(guest,gh,pid,sid).status_code==403
    assert save(guest,gh,p,1,sid).status_code==409
    assert owner.get('/song-builder/api/projects/'+pid).json['revision']==1


def test_new_audio_on_another_track_does_not_block_guest_merge(tmp_path):
    import io
    from test_room_workflow import wav_bytes
    app,owner,h,guest,gh,p,a,b=pair(tmp_path)
    asset=owner.post('/song-builder/api/assets',headers=h,data={'file':(io.BytesIO(wav_bytes()),'new-bass.wav')}).json['asset']
    replacement=copy.deepcopy(p);replacement['clips'][0]['assetId']=asset['id']
    assert save(owner,h,replacement,2,a).status_code==200
    guest_edit=copy.deepcopy(p);guest_edit['tracks'][1]['gainDb']=-3
    response=save(guest,gh,guest_edit,2,b)
    assert response.status_code==200
    assert response.json['project']['clips'][0]['assetId']==asset['id']
    assert response.json['project']['tracks'][1]['gainDb']==-3
