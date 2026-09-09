import copy
import io
from test_room_collaboration import setup, invite, join
from test_room_workflow import uid, wav_bytes, metadata


def submission(guest,h,saved):
    asset=guest.post('/song-builder/api/assets',headers=h,data={'file':(io.BytesIO(wav_bytes()),'new performance.wav')}).json['asset']
    p=saved['project'];payload={'requestId':uid(),'assetId':asset['id'],'sectionId':p['sections'][0]['id'],'trackId':p['tracks'][0]['id'],'offset':1,'sourceOffset':0,'duration':2,'expectedRevision':saved['revision'],'note':'Alternative chorus phrasing'}
    path='/song-builder/api/projects/'+p['id']+'/submissions'
    result=guest.post(path,headers=h,json=payload)
    assert result.status_code==201,result.json
    return path,payload,result.json['submission']


def test_guest_submits_owner_auditions_and_accepts_exactly_once_into_new_version(tmp_path):
    app,owner,h,saved=setup(tmp_path);guest,gh=join(app,invite(owner,h,saved))
    path,payload,s=submission(guest,gh,saved)
    assert guest.post(path,headers=gh,json=payload).status_code==200
    assert owner.get('/song-builder/api/projects/'+saved['project']['id']).json==saved
    preview=owner.get(path+'/'+s['id']+'/preview');assert preview.status_code==200,preview.json
    clips=preview.json['project']['clips'];assert sorted((c['offset'],c['duration']) for c in clips)==[(0,1),(1,2),(3,1)]
    assert all(owner.get(a['url']).status_code==200 for a in preview.json['assets'])
    decision={'requestId':uid(),'expectedRevision':1}
    assert guest.post(path+'/'+s['id']+'/accept',headers=gh,json=decision).status_code==403
    accepted=owner.post(path+'/'+s['id']+'/accept',headers=h,json=decision);assert accepted.status_code==201,accepted.json
    version=accepted.json['version'];assert version['project']['id']!=saved['project']['id']
    retry=owner.post(path+'/'+s['id']+'/accept',headers=h,json=decision);assert retry.status_code==200
    assert retry.json['version']['project']['id']==version['project']['id']
    assert len(owner.get('/song-builder/api/projects').json['projects'])==2
    assert owner.get('/song-builder/api/projects/'+saved['project']['id']).json==saved


def test_submission_privacy_stale_source_and_requested_changes(tmp_path):
    app,owner,h,saved=setup(tmp_path);guest,gh=join(app,invite(owner,h,saved))
    path,payload,s=submission(guest,gh,saved)
    other,oh=join(app,invite(owner,h,saved));assert other.get(path).json['submissions']==[]
    assert other.get(path+'/'+s['id']+'/preview').status_code==404
    viewer,vh=join(app,invite(owner,h,saved,'viewer'));assert viewer.post(path,headers=vh,json={}).status_code==403
    changed=copy.deepcopy(saved['project']);changed['title']='New backing revision'
    assert owner.put('/song-builder/api/projects/'+changed['id'],headers=h,json={'project':changed,'expectedRevision':1}).status_code==200
    assert owner.post(path+'/'+s['id']+'/accept',headers=h,json={'requestId':uid(),'expectedRevision':2}).status_code==409
    r=owner.post(path+'/'+s['id']+'/changes',headers=h,json={'requestId':uid(),'reason':'Try this against the updated backing.'});assert r.status_code==200
    assert guest.get(path).json['submissions'][0]['reason']=='Try this against the updated backing.'
    assert len(owner.get('/song-builder/api/projects').json['projects'])==1


def test_submission_protections_and_csrf_are_enforced(tmp_path):
    app,owner,h,saved=setup(tmp_path);guest,gh=join(app,invite(owner,h,saved));path,payload,s=submission(guest,gh,saved)
    assert owner.post(path+'/'+s['id']+'/accept',json={'requestId':uid(),'expectedRevision':1}).status_code==403
    p=saved['project'];rules=metadata(protections=[{'clipId':p['clips'][0]['id'],'mode':'never'}])
    assert owner.put('/song-builder/api/workflow/'+p['id'],headers=h,json={'metadata':rules,'expectedRevision':0}).status_code==200
    assert owner.post(path+'/'+s['id']+'/accept',headers=h,json={'requestId':uid(),'expectedRevision':1}).status_code==409
    payload['requestId']=uid();assert guest.post(path,headers=gh,json=payload).status_code==409
