import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {transportPosition,bindListening} from '../../song_builder/static/ui/listening.mjs';
const require=createRequire(import.meta.url),{JSDOM}=require(process.env.RACK_TEST_MODULES?`${process.env.RACK_TEST_MODULES}/jsdom`:'jsdom');

test('transport uses the server clock, bounded latency estimate and song bounds',()=>{
 const t={playing:1,position:5,changed:100};assert.equal(transportPosition(t,102,200,20),7.1);
 assert.equal(transportPosition(t,500,200,20),20);
 assert.equal(transportPosition({...t,playing:0},500,200,20),5);
 assert.equal(transportPosition(t,99,0,20),5);
});

test('remote transport requires Follow, honors pause and cannot restart after local Stop',async()=>{
 const dom=new JSDOM('<section id="listening-room"><p id="listening-status"></p><button id="listen-host"></button><button id="listen-follow"></button><button id="listen-end"></button><button id="listen-play"></button><input id="listen-seek" type="range"><div id="listening-notes"></div><form id="feedback-form"><textarea id="feedback-text"></textarea><button id="feedback-add"></button></form></section><button id="stop-playback"></button>',{pretendToBeVisual:true});
 const document=dom.window.document,state={project:{id:'song',sections:[{duration:20}]},revision:1,access:{role:'viewer'},playing:false,dirty:false};let at=0,played=[],unlocks=0,offline=false;
 let transport={session_id:'host',name:'Producer',revision:1,version:1,playing:1,position:5,changed:100};
 const api=async()=>{if(offline)throw Error('Offline');return {transport,serverNow:102,comments:[]};};
 const instance=bindListening({document,state,api,live:{sessionId:()=>'listener',listenOnly:async()=>{}},save:async()=>{},play:async p=>{played.push(p);at=p;state.playing=true;},stop:()=>{state.playing=false;},position:()=>at,seek:p=>{at=p;},unlock:async()=>{unlocks++;},render:()=>{},notify:()=>{},newId:()=>'note',now:()=>0});
 await instance.tick();assert.equal(played.length,0);
 await document.getElementById('listen-follow').onclick();assert.equal(unlocks,1);assert.deepEqual(played,[7]);
 await instance.tick();assert.equal(played.length,1,'stable playback does not seek repeatedly');
 transport={...transport,playing:0,position:8,version:2};await instance.tick();assert.equal(state.playing,false);assert.equal(at,8);
 transport={...transport,playing:1,position:8,version:3};await instance.tick();assert.equal(state.playing,true);
 offline=true;await instance.tick();assert.equal(state.playing,false);offline=false;
 document.getElementById('stop-playback').click();const count=played.length;await instance.tick();assert.equal(played.length,count);assert.equal(instance.active(),false);
 dom.window.close();
});
