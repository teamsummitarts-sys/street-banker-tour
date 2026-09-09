from test_room_collaboration import setup, invite, join
from test_room_workflow import metadata, uid


def test_storage_scope_stable_per_account_distinct_from_guest(tmp_path):
    app,owner,h,saved=setup(tmp_path)
    a=owner.get('/song-builder/api/capabilities').json['accountScope']
    assert len(a)==64 and owner.get('/song-builder/api/capabilities').json['accountScope']==a
    assert a.encode() in owner.get('/song-builder/analyze').data
    guest,gh=join(app,invite(owner,h,saved));b=guest.get('/song-builder/api/capabilities').json['accountScope'];assert b!=a
    assert guest.get('/song-builder/analyze').status_code==403


def test_named_version_carries_workflow_without_rewriting_source(tmp_path):
    app,c,h,saved=setup(tmp_path);p=saved['project'];clip=p['clips'][0]
    value=metadata(takes=[{'id':uid(),'sectionId':clip['sectionId'],'trackId':clip['trackId'],'name':'Before edit','clips':[clip]}])
    c.put('/song-builder/api/workflow/'+p['id'],headers=h,json={'metadata':value,'expectedRevision':0})
    result=c.post('/song-builder/api/projects/'+p['id']+'/fork',headers=h,json={'expectedRevision':1,'title':'New version'})
    assert result.status_code==201,result.json
    new=result.json['projectId'];assert new!=p['id']
    assert c.get('/song-builder/api/workflow?projectId='+new).json['metadata']['takes'][0]['name']=='Before edit'
    assert c.get('/song-builder/api/projects/'+p['id']).json==saved
    assert c.post('/song-builder/api/projects/'+p['id']+'/fork',headers=h,json={'expectedRevision':2,'title':'Stale'}).status_code==409


def test_fork_edit_respects_protected_clips(tmp_path):
    import copy
    app,c,h,saved=setup(tmp_path);p=saved['project'];pid=p['id']
    value=metadata(protections=[{'clipId':p['clips'][0]['id'],'mode':'never'}])
    c.put('/song-builder/api/workflow/'+pid,headers=h,json={'metadata':value,'expectedRevision':0})
    changed=copy.deepcopy(p);changed['clips']=[]
    r=c.post('/song-builder/api/projects/'+pid+'/fork',headers=h,json={'expectedRevision':1,'title':'Protected edit','project':changed})
    assert r.status_code==409
    assert len(c.get('/song-builder/api/projects').json['projects'])==1
