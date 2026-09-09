import copy
import uuid
from test_room_collaboration import setup,invite,join
from test_room_live import live,save


def command(client,h,pid,sid,action='host',version=0,position=0,revision=1):
    return client.post('/song-builder/api/projects/'+pid+'/listening',headers=h,json={'sessionId':sid,'action':action,'expectedVersion':version,'position':position,'expectedRevision':revision})


def test_host_controls_are_versioned_and_freeze_the_reviewed_mix(tmp_path):
    app,owner,h,saved=setup(tmp_path);pid=saved['project']['id'];sid=str(uuid.uuid4());live(owner,h,pid,sid)
    assert command(owner,h,pid,sid).status_code==200
    assert command(owner,h,pid,sid,'play',1,1).status_code==200
    assert command(owner,h,pid,sid,'pause',1,2).status_code==409
    data=owner.get('/song-builder/api/projects/'+pid+'/listening').json
    assert data['transport']['playing']==1
    assert data['transport']['version']==2
    changed=copy.deepcopy(saved['project']);changed['title']='Changed mid-listen'
    assert save(owner,h,changed,1).status_code==409
    assert live(owner,h,pid,sid,'arrangement').status_code==409
    assert command(owner,h,pid,sid,'end',2).status_code==200
    assert save(owner,h,changed,1).status_code==200


def test_viewer_can_comment_but_not_host_and_revocation_removes_access(tmp_path):
    app,owner,h,saved=setup(tmp_path);pid=saved['project']['id'];inv=invite(owner,h,saved,'viewer');guest,gh=join(app,inv);sid=str(uuid.uuid4());live(guest,gh,pid,sid)
    assert command(guest,gh,pid,sid).status_code==403
    note={'id':str(uuid.uuid4()),'text':'Keep the rough vocal.','position':1.5,'expectedRevision':1}
    path='/song-builder/api/projects/'+pid+'/feedback'
    assert guest.post(path,headers=gh,json=note).status_code==201
    assert guest.post(path,headers=gh,json=note).status_code==200
    assert len(owner.get('/song-builder/api/projects/'+pid+'/listening').json['comments'])==1
    assert owner.patch(path+'/'+note['id'],headers=h,json={'resolved':True}).status_code==200
    assert owner.get('/song-builder/api/projects/'+pid+'/listening').json['comments'][0]['resolved']==1
    assert guest.get('/song-builder/api/projects/'+str(uuid.uuid4())+'/listening').status_code==404
    owner.delete('/song-builder/api/projects/'+pid+'/invitations/'+inv['id'],headers=h)
    assert guest.get('/song-builder/api/projects/'+pid+'/listening').status_code==401


def test_expiry_releases_host_and_other_session_cannot_hijack_transport(tmp_path):
    app,owner,h,saved=setup(tmp_path);pid=saved['project']['id'];guest,gh=join(app,invite(owner,h,saved));a,b=str(uuid.uuid4()),str(uuid.uuid4());live(owner,h,pid,a);live(guest,gh,pid,b)
    assert command(owner,h,pid,a).status_code==200
    assert command(guest,gh,pid,b,'play',1).status_code==403
    assert command(guest,gh,pid,b).status_code==409
    service=app.extensions['room_collaboration']
    with service.store.connection(write=True) as db:db.execute('UPDATE room_live_sessions SET expires=0 WHERE session_id=?',(a,))
    assert owner.get('/song-builder/api/projects/'+pid+'/listening').json['transport'] is None
    assert command(guest,gh,pid,b).status_code==200


def test_feedback_preserves_revision_and_rejects_stale_timestamp_and_foreign_resolution(tmp_path):
    app,owner,h,saved=setup(tmp_path);pid=saved['project']['id'];guest,gh=join(app,invite(owner,h,saved,'viewer'))
    note={'id':str(uuid.uuid4()),'text':'At the chorus','position':2,'expectedRevision':1};path='/song-builder/api/projects/'+pid+'/feedback'
    assert owner.post(path,headers=h,json=note).status_code==201
    assert guest.patch(path+'/'+note['id'],headers=gh,json={'resolved':True}).status_code==403
    changed=copy.deepcopy(saved['project']);changed['title']='Revision two';save(owner,h,changed,1)
    note['id']=str(uuid.uuid4());assert guest.post(path,headers=gh,json=note).status_code==409
    old=owner.get('/song-builder/api/projects/'+pid+'/listening').json['comments'][0];assert old['revision']==1
    note['expectedRevision']=2;note['position']=10;assert guest.post(path,headers=gh,json=note).status_code==400
    assert guest.post(path,json=note).status_code==403


def test_reusing_expired_session_id_does_not_inherit_host_authority(tmp_path):
    app,owner,h,saved=setup(tmp_path);pid=saved['project']['id'];sid=str(uuid.uuid4());live(owner,h,pid,sid);command(owner,h,pid,sid)
    service=app.extensions['room_collaboration']
    with service.store.connection(write=True) as db:db.execute('UPDATE room_live_sessions SET expires=0 WHERE session_id=?',(sid,))
    guest,gh=join(app,invite(owner,h,saved));assert live(guest,gh,pid,sid).status_code==200
    assert guest.get('/song-builder/api/projects/'+pid+'/listening').json['transport'] is None
    assert command(guest,gh,pid,sid,'play',1).status_code==403
