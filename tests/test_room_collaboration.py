import ast
from pathlib import Path
from types import SimpleNamespace
import copy
import io
import re
from flask import Flask, session, request, redirect, url_for
from song_builder import init
from song_builder.collaboration import allow_guest_gate
from test_room_workflow import make_project, wav_bytes


def setup(tmp_path):
    app=Flask(__name__);app.config.update(TESTING=True,SECRET_KEY='collab-test',SONG_BUILDER_ENABLED=True)
    # Exercise the actual host gate without importing unrelated services.
    node=next(n for n in ast.walk(ast.parse(Path('app.py').read_text())) if isinstance(n,ast.FunctionDef) and n.name=='plan_gate')
    node.decorator_list=[]
    scope=dict(app=app,request=request,redirect=redirect,url_for=url_for,
        current_user=lambda:{'id':session['host']} if session.get('host') else None,
        _is_public_path=lambda path:path=='/login',_valid_backup_token=lambda:False,
        plans=SimpleNamespace(required_tier=lambda path:None))
    exec(compile(ast.Module(body=[node],type_ignores=[]),'app.py','exec'),scope)
    app.before_request(scope['plan_gate'])
    app.add_url_rule('/login','login',lambda:'Sign in')
    init(app,lambda:{'id':session['host']} if session.get('host') else None,data_dir=tmp_path)
    owner=app.test_client()
    with owner.session_transaction() as s:s['host']='alice';s['song_builder_csrf']={'account':'alice','token':'owner-csrf'}
    headers={'X-Song-Builder-CSRF':'owner-csrf'}
    saved=make_project(owner,headers)
    return app,owner,headers,saved


def invite(owner,headers,saved,role='editor'):
    r=owner.post('/song-builder/api/projects/'+saved['project']['id']+'/invitations',headers=headers,json={'role':role,'label':'Guest'})
    assert r.status_code==201
    return r.json


def join(app,invitation):
    guest=app.test_client();page=guest.get('/song-builder/join')
    assert page.status_code==200
    token=re.search(rb'name="room-join-csrf" content="([^"]+)"',page.data).group(1).decode()
    r=guest.post('/song-builder/api/invitations/redeem',headers={'X-Room-Join-CSRF':token},json={'token':invitation['url'].split('#')[1],'name':'Guest player'})
    assert r.status_code==200
    page=guest.get(r.json['url']);assert page.status_code==200
    csrf=re.search(rb'name="song-builder-csrf" content="([^"]+)"',page.data).group(1).decode()
    return guest,{'X-Song-Builder-CSRF':csrf}


def test_editor_scoping_conflicts_and_revocation(tmp_path):
    app,owner,h,saved=setup(tmp_path);inv=invite(owner,h,saved);guest,gh=join(app,inv);pid=saved['project']['id']
    assert guest.get('/noise-lab/').status_code==302
    assert guest.get('/song-builder/analyze').status_code==403
    assert guest.get('/song-builder/api/projects').json['projects'][0]['id']==pid
    assert guest.get(saved['assets'][0]['url']).status_code==200
    assert guest.get('/song-builder/api/capabilities').json['generation']['configured'] is False
    p=copy.deepcopy(saved['project']);p['title']='Guest edit'
    r=guest.put('/song-builder/api/projects/'+pid,headers=gh,json={'project':p,'expectedRevision':1});assert r.status_code==200
    conflict=owner.put('/song-builder/api/projects/'+pid,headers=h,json={'project':saved['project'],'expectedRevision':1});assert conflict.status_code==409
    assert guest.post('/song-builder/api/projects',headers=gh,json={'project':p}).status_code==403
    assert guest.post('/song-builder/api/jobs',headers=gh,json={}).status_code==403
    other=make_project(owner,h)
    assert guest.get('/song-builder/api/projects/'+other['project']['id']).status_code==404
    assert guest.get(other['assets'][0]['url']).status_code==403
    spoof=copy.deepcopy(p);spoof['clips'][0]['assetId']=other['assets'][0]['id']
    assert guest.put('/song-builder/api/projects/'+pid,headers=gh,json={'project':spoof,'expectedRevision':2}).status_code==403
    assert owner.get('/song-builder/api/projects/'+pid+'/collaborators').json['contributions'][0]['name']=='Guest player'
    assert owner.delete('/song-builder/api/projects/'+pid+'/invitations/'+inv['id'],headers=h).status_code==200
    assert guest.get('/song-builder/api/projects/'+pid).status_code==401
    assert guest.get(saved['assets'][0]['url']).status_code==401


def test_viewer_can_listen_but_cannot_write_or_upload(tmp_path):
    app,owner,h,saved=setup(tmp_path);guest,gh=join(app,invite(owner,h,saved,'viewer'))
    assert guest.get(saved['assets'][0]['url']).status_code==200
    assert guest.put('/song-builder/api/projects/'+saved['project']['id'],headers=gh,json={'project':saved['project'],'expectedRevision':1}).status_code==403
    assert guest.post('/song-builder/api/assets',headers=gh,data={'file':(io.BytesIO(wav_bytes()),'x.wav')}).status_code==403
    assert guest.get('/song-builder/api/capabilities').json['access']['role']=='viewer'


def test_single_use_csrf_and_guest_upload(tmp_path):
    app,owner,h,saved=setup(tmp_path);inv=invite(owner,h,saved)
    stranger=app.test_client();assert stranger.post('/song-builder/api/invitations/redeem',json={'token':inv['url'].split('#')[1],'name':'X'}).status_code==403
    guest,gh=join(app,inv);other=app.test_client();other.get('/song-builder/join')
    with other.session_transaction() as s:csrf=s['room_join_csrf']
    assert other.post('/song-builder/api/invitations/redeem',headers={'X-Room-Join-CSRF':csrf},json={'token':inv['url'].split('#')[1],'name':'X'}).status_code==403
    assert guest.put('/song-builder/api/projects/'+saved['project']['id'],json={'project':saved['project'],'expectedRevision':1}).status_code==403
    upload=guest.post('/song-builder/api/assets',headers=gh,data={'file':(io.BytesIO(wav_bytes()),'guitar.wav')});assert upload.status_code==201
    p=copy.deepcopy(saved['project']);p['clips'][0]['assetId']=upload.json['asset']['id']
    assert guest.put('/song-builder/api/projects/'+p['id'],headers=gh,json={'project':p,'expectedRevision':1}).status_code==200
    assert owner.get(upload.json['asset']['url']).status_code==200


def test_editor_cannot_unlock_owner_protection(tmp_path):
    app,owner,h,saved=setup(tmp_path);p=copy.deepcopy(saved['project']);p['sections'][0]['locked']=True
    assert owner.put('/song-builder/api/projects/'+p['id'],headers=h,json={'project':p,'expectedRevision':1}).status_code==200
    guest,gh=join(app,invite(owner,h,saved));p['sections'][0]['locked']=False
    assert guest.put('/song-builder/api/projects/'+p['id'],headers=gh,json={'project':p,'expectedRevision':2}).status_code==403


def test_expired_invitation_and_atomic_save_revocation(tmp_path):
    import pytest
    from song_builder.validation import SongError
    app,owner,h,saved=setup(tmp_path);inv=invite(owner,h,saved)
    service=app.extensions['room_collaboration']
    with service.store.connection(write=True) as db:
        db.execute('UPDATE room_invites SET expires=0 WHERE id=?',(inv['id'],))
    stranger=app.test_client();stranger.get('/song-builder/join')
    with stranger.session_transaction() as session_value:csrf=session_value['room_join_csrf']
    response=stranger.post('/song-builder/api/invitations/redeem',headers={'X-Room-Join-CSRF':csrf},json={'token':inv['url'].split('#')[1],'name':'Guest'})
    assert response.status_code==403
    active=invite(owner,h,saved);guest,gh=join(app,active)
    with guest.session_transaction() as session_value:member_id=session_value['room_guest']
    with service.store.connection(write=True) as db:
        member=dict(db.execute('SELECT * FROM room_members WHERE id=?',(member_id,)).fetchone())
        db.execute('UPDATE room_members SET revoked=1 WHERE id=?',(member_id,))
    with pytest.raises(SongError):
        service.store.save_project('alice',saved['project'],1,access=member)
    assert owner.get('/song-builder/api/projects/'+saved['project']['id']).json['revision']==1
    assert guest.get('/song-builder/api/projects').status_code==401
