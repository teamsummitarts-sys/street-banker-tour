import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {bindLive,mergePending,changedParts} from '../../song_builder/static/ui/live.mjs';
const require=createRequire(import.meta.url),{JSDOM}=require(process.env.RACK_TEST_MODULES?`${process.env.RACK_TEST_MODULES}/jsdom`:'jsdom');
const project=()=>({id:'song',title:'Song',sections:[{id:'verse',duration:8}],tracks:[{id:'bass',gainDb:0},{id:'drums',gainDb:0}],clips:[]});

test('pending local edits merge with server changes to another track, independent of JSON key order',()=>{
 const base=project(),local=structuredClone(base),remote=JSON.parse(JSON.stringify(base,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).reverse()):v));
 assert.equal(changedParts(base,remote).size,0);
 local.tracks[0].gainDb=-6;remote.tracks[1].gainDb=-3;
 const merged=mergePending(base,local,remote);assert.equal(merged.tracks[0].gainDb,-6);assert.equal(merged.tracks[1].gainDb,-3);assert.equal(base.tracks[0].gainDb,0);
 remote.tracks[0].gainDb=-2;assert.throws(()=>mergePending(base,local,remote),/overlap/);
});

test('live UI joins, claims control, defers updates during playback/dirty edits and then refreshes',async()=>{
 const dom=new JSDOM('<section id="live-room"><button id="live-connect"></button><select id="live-target"></select><p id="live-status"></p><div id="live-people"></div></section>',{pretendToBeVisual:true});
 const document=dom.window.document,state={project:project(),revision:1,access:{role:'owner'},busy:0,playing:false,dirty:false,sectionId:'verse',trackId:'bass'},calls=[],errors=[];
 let remoteRevision=1,loads=0,offline=false;
 const api=async(path,options)=>{if(offline)throw Error('Network offline');calls.push({path,options});if(options?.method==='POST')return {expires:Date.now()/1000+20};if(options?.method==='DELETE')return {};return {revision:remoteRevision,presence:[{name:'Producer',role:'editor',scope:'track:drums',sessionId:'other'}]};};
 const live=bindLive({document,state,api,save:async()=>{},loadProject:async()=>{loads++;state.project=project();state.revision=remoteRevision;},render:()=>{},notify:msg=>errors.push(msg),newId:()=>'session'});
 await document.getElementById('live-connect').onclick();assert.equal(state.liveSession,'session');await live.tick();
 const local=project();local.tracks[0].gainDb=-3;assert.equal(live.canEdit(state.project,local),false);
 const target=document.getElementById('live-target');target.value='track:bass';await target.onchange();assert.equal(live.canEdit(state.project,local),true);
 const other=project();other.tracks[1].gainDb=-3;assert.equal(live.canEdit(state.project,other),false);
 remoteRevision=2;state.playing=true;await live.tick();assert.equal(loads,0);assert.match(document.getElementById('live-status').textContent,/playback/);
 state.playing=false;state.dirty=true;offline=true;await live.tick();assert.match(document.getElementById('live-status').textContent,/Connection interrupted/);assert.equal(state.dirty,true);assert.equal(state.liveSession,'session');offline=false;await live.tick();assert.equal(loads,0);
 state.dirty=false;document.dispatchEvent(new dom.window.Event('pointerdown'));await live.tick();assert.equal(loads,0);
 document.dispatchEvent(new dom.window.Event('pointerup'));await live.tick();assert.equal(loads,1);assert.equal(state.revision,2);assert.equal(state.trackId,'bass');
 await document.getElementById('live-connect').onclick();assert.equal(state.liveSession,null);assert.ok(calls.some(c=>c.options?.method==='DELETE'));dom.window.close();
});
