import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
const require=createRequire(import.meta.url),root=process.env.RACK_TEST_MODULES;
const dependency=name=>require(root?`${root}/${name}`:name);
const {AudioContext,OfflineAudioContext}=dependency('node-web-audio-api');
const {JSDOM}=dependency('jsdom');
import {AudioEngine,encodeWav} from '../../song_builder/static/core/audio.mjs';
import * as P from '../../song_builder/static/core/project.mjs';
import {RACK_DEFAULT} from '../../song_builder/static/core/rack.mjs';
import {bindConsole} from '../../song_builder/static/ui/console.mjs';
import {renderRackPanel} from '../../song_builder/static/ui/rack-panel.mjs';
globalThis.crypto??=webcrypto;
globalThis.AudioContext=class extends AudioContext{constructor(){super({sinkId:{type:'none'},sampleRate:44100});}};
globalThis.OfflineAudioContext=OfflineAudioContext;
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function fixture(){
 let p=P.addTrack(P.newProject(),'Bass');p={...p,sections:[{...p.sections[0],duration:3}]};const id=P.newId();
 p=P.addClip(p,{assetId:id,trackId:p.tracks[0].id,sectionId:p.sections[0].id,offset:0,sourceOffset:0,duration:3,loop:false,gainDb:0});
 const left=Float32Array.from({length:44100*3},(_,i)=>.25*Math.sin(2*Math.PI*440*i/44100));
 const right=left.map(v=>v*.5),engine=new AudioEngine();await engine.decode(id,encodeWav([left,right],44100));return {engine,p};
}
test('native: section playback ends at its requested audio boundary, not song end',async()=>{
 const {engine,p}=await fixture();try{
  let ended=false;await engine.play(p,{from:1,to:1.15,onEnded:()=>{ended=true;}});
  await wait(260);assert.equal(ended,true);assert.equal(engine.isPlaying(),false);assert.ok(Math.abs(engine.position()-1.15)<1e-6);
  assert.deepEqual(engine.meterLevels(),[-Infinity,-Infinity]);
 }finally{engine.dispose();}
});
test('native: repeated audio-clock cycles retain stereo signal, pan and live rack changes',async()=>{
 const {engine,p:initial}=await fixture();let p=P.updateTrack(initial,initial.tracks[0].id,{rack:{...RACK_DEFAULT}});
 try{
  let ended=false;await engine.play(p,{from:.5,to:.65,loop:true,onEnded:()=>{ended=true;}});
  for(let pass=0;pass<5;pass++){
   await wait(90);const levels=engine.meterLevels();assert.ok(levels[0]>-14&&levels[0]<-10,`left ${levels[0]}`);assert.ok(levels[1]>-20&&levels[1]<-16,`right ${levels[1]}`);
   assert.ok(engine.position()>=.5&&engine.position()<.65);
  }
  assert.equal(ended,false);assert.equal(engine.updateRack(p.tracks[0].id,{...RACK_DEFAULT,outputDb:-6}),true);
  await wait(120);assert.ok(engine.meterLevels()[0]<-17,'live rack changes reach meters on later cycles');
  engine.stop();const stopped=engine.position();await wait(180);assert.equal(engine.isPlaying(),false);assert.equal(engine.position(),stopped);
  p=P.updateTrack(p,p.tracks[0].id,{pan:-1});await engine.play(p,{from:0,to:.2});await wait(90);assert.ok(engine.meterLevels()[0]>-20);assert.ok(engine.meterLevels()[1]<-60,'hard left pan reaches output meter');
 }finally{engine.dispose();}
});
test('DOM: tabs expose existing tools, selection does not solo, clip latch resets',()=>{
 const html=readFileSync(new URL('../../song_builder/templates/song_builder/index.html',import.meta.url),'utf8');
 const dom=new JSDOM(html),d=dom.window.document,studio=bindConsole(d);
 assert.equal(d.querySelectorAll('#clip-inspector').length,1);
 assert.equal(d.getElementById('panel-trim').contains(d.getElementById('clip-inspector')),true);
 d.getElementById('tab-trim').click();assert.equal(d.getElementById('panel-trim').hidden,false);assert.equal(d.getElementById('panel-sound').hidden,true);
 d.getElementById('tab-trim').dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'ArrowRight'}));assert.equal(d.getElementById('tab-takes').getAttribute('aria-selected'),'true');
 let p=P.addTrack(P.newProject(),'Bass');studio.sync(p,p.tracks[0].id,p.sections[0],null);assert.equal(d.getElementById('solo-status').hidden,true);
 p=P.updateTrack(p,p.tracks[0].id,{solo:true});studio.sync(p,p.tracks[0].id,p.sections[0],null);assert.match(d.getElementById('solo-status').textContent,/Bass/);
 studio.meter([1,-7],100);assert.equal(d.getElementById('clear-clip').getAttribute('aria-pressed'),'true');
 studio.meter([-30,-30],200);assert.equal(d.getElementById('clear-clip').getAttribute('aria-pressed'),'true');
 d.getElementById('clear-clip').click();assert.equal(d.getElementById('clear-clip').getAttribute('aria-pressed'),'false');
 dom.window.close();
});
test('DOM: knob drags are one undoable edit, cancel restores, double-tap resets',()=>{
 const dom=new JSDOM('<section id="rack"></section>');globalThis.document=dom.window.document;const d=document,root=d.getElementById('rack');
 const track={name:'Bass',rack:{...RACK_DEFAULT}},applied=[];let cancel=()=>{};
 const render=()=>{cancel();cancel=renderRackPanel(root,{track,blocked:false,protectedNames:[],allowed:()=>true,preview:()=>{},apply:v=>{applied.push(v);track.rack=v;}});};render();
 const dial=root.querySelector('.rack-dial'),input=dial.querySelector('input');dial.setPointerCapture=()=>{};dial.releasePointerCapture=()=>{};
 const pointer=(type,y)=>{const e=new dom.window.Event(type);Object.assign(e,{button:0,pointerId:1,clientY:y});dial.dispatchEvent(e);};
 pointer('pointerdown',100);pointer('pointermove',60);assert.equal(applied.length,0);pointer('pointerup',60);assert.equal(applied.length,1);assert.equal(track.rack.body,50);
 render();const cancelled=root.querySelector('.rack-dial');cancelled.setPointerCapture=()=>{};cancelled.releasePointerCapture=()=>{};
 const event=(type,y)=>{const e=new dom.window.Event(type);Object.assign(e,{button:0,pointerId:2,clientY:y});cancelled.dispatchEvent(e);};
 event('pointerdown',100);event('pointermove',70);event('pointercancel',70);assert.equal(applied.length,1);assert.equal(cancelled.querySelector('input').value,'50');
 event('pointerdown',100);event('pointerup',100);event('pointerdown',100);event('pointerup',100);assert.equal(track.rack.body,0);assert.equal(applied.length,2);
 assert.ok(root.querySelector('[data-control="body"]').getAttribute('aria-valuetext').includes('0'));
 cancel();dom.window.close();delete globalThis.document;
});

test('controller integration: selected mixer, solo clear and undo remain connected after reparenting',async()=>{
 const {PendingRequests}=await import('../../song_builder/static/ui/requests.mjs');
 const {bindFadeHandle,effectiveFades}=await import('../../song_builder/static/ui/fade-handles.mjs');
 const {sameRack}=await import('../../song_builder/static/core/rack.mjs');
 const html=readFileSync(new URL('../../song_builder/templates/song_builder/index.html',import.meta.url),'utf8').replaceAll('{{ builder_base_url }}','/song-builder/');
 const dom=new JSDOM(html,{url:'https://example.test/song-builder/'}),w=dom.window;globalThis.document=w.document;
 const sandbox={document:w.document,window:w,navigator:w.navigator,location:w.location,history:w.history,sessionStorage:w.sessionStorage,localStorage:w.localStorage,URLSearchParams,URL,FormData,Blob,Option:w.Option,console,AudioEngine,P,PendingRequests,bindFadeHandle,effectiveFades,renderRackPanel,sameRack,bindConsole,setTimeout:()=>0,clearTimeout:()=>{},setInterval:()=>0,clearInterval:()=>{},requestAnimationFrame:()=>{}};
 const source=readFileSync(new URL('../../song_builder/static/ui/controller.mjs',import.meta.url),'utf8').replace(/^import .*;\n/gm,'').replace(/boot\(\);\s*$/,'');
 const h=new Function(...Object.keys(sandbox),source+'\nreturn {state,render,engine};')(...Object.values(sandbox));let p=P.addTrack(P.newProject(),'Bass');p=P.addTrack(p,'Drums');h.state.project=p;h.state.sectionId=p.sections[0].id;h.state.trackId=p.tracks[0].id;h.render();
 const d=w.document;assert.equal(d.querySelectorAll('#selected-mixer [type="range"]').length,2);
 const pan=d.querySelector('[aria-label="Pan for Bass"]');pan.value=.5;pan.dispatchEvent(new w.Event('change'));assert.equal(h.state.project.tracks[0].pan,.5);
 d.querySelector('[aria-label="Center pan for Bass"]').click();await Promise.resolve();assert.equal(h.state.project.tracks[0].pan,0);
 const panSurface=d.querySelector('.pan-dial');panSurface.setPointerCapture=()=>{};panSurface.releasePointerCapture=()=>{};
 const panPointer=(type,y)=>{const e=new w.Event(type);Object.assign(e,{button:0,pointerId:12,clientY:y});panSurface.dispatchEvent(e);};
 const beforeTap=h.state.history.length;panPointer('pointerdown',100);panPointer('pointerup',100);assert.equal(h.state.history.length,beforeTap,'a pan tap does not create an undo edit');
 panPointer('pointerdown',100);panPointer('pointermove',60);
 assert.notEqual(panSurface.querySelector('input').value,'0','pan displays the pending gesture');
 panPointer('pointercancel',60);assert.equal(panSurface.querySelector('input').value,'0');assert.equal(h.state.project.tracks[0].pan,0,'cancel preserves original pan');
 d.querySelector('[aria-label="Solo Bass"]').click();await Promise.resolve();assert.equal(h.state.project.tracks[0].solo,true);assert.equal(d.getElementById('solo-status').hidden,false);
 d.getElementById('clear-solos').click();await Promise.resolve();assert.equal(h.state.project.tracks[0].solo,false);
 d.getElementById('undo-edit').click();await Promise.resolve();assert.equal(h.state.project.tracks[0].solo,true);
 assert.equal(d.getElementById('notice').hidden,true,'no handler error');h.engine.dispose();dom.window.close();delete globalThis.document;
});

test('controller: candidate rack changes reach audio and acceptance; Stop cancels pending auditions',async()=>{
 const {PendingRequests}=await import('../../song_builder/static/ui/requests.mjs');
 const {bindFadeHandle,effectiveFades}=await import('../../song_builder/static/ui/fade-handles.mjs');
 const {sameRack}=await import('../../song_builder/static/core/rack.mjs');
 const html=readFileSync(new URL('../../song_builder/templates/song_builder/index.html',import.meta.url),'utf8').replaceAll('{{ builder_base_url }}','/song-builder/');
 const dom=new JSDOM(html,{url:'https://example.test/song-builder/'}),w=dom.window;globalThis.document=w.document;
 w.HTMLElement.prototype.scrollIntoView=()=>{};
 w.HTMLCanvasElement.prototype.getContext=()=>({beginPath(){},moveTo(){},lineTo(){},stroke(){}});
 const sandbox={document:w.document,window:w,navigator:w.navigator,location:w.location,history:w.history,sessionStorage:w.sessionStorage,localStorage:w.localStorage,URLSearchParams,URL,FormData,Blob,Option:w.Option,console,AudioEngine,P,RACK_DEFAULT,PendingRequests,bindFadeHandle,effectiveFades,renderRackPanel,sameRack,bindConsole,confirm:()=>true,setTimeout:()=>0,clearTimeout:()=>{},setInterval:()=>0,clearInterval:()=>{},requestAnimationFrame:()=>{}};
 const source=readFileSync(new URL('../../song_builder/static/ui/controller.mjs',import.meta.url),'utf8').replace(/^import .*;\n/gm,'').replace(/boot\(\);\s*$/,'');
 const h=new Function(...Object.keys(sandbox),source+'\nreturn {state,render,engine,auditionTake,stop,acceptTake,setLoader(fn){ensureAudio=fn;},noSave(){save=async()=>{};}};')(...Object.values(sandbox));
 try{
  const p=P.newProject(),assetId=P.newId(),job={id:P.newId(),projectId:p.id,sectionId:p.sections[0].id,status:'succeeded',kind:'generate',asset:{id:assetId,url:'/song-builder/api/assets/'+assetId+'/audio'}};
  h.state.project=p;h.state.sectionId=p.sections[0].id;h.state.jobs=[job];h.render();
  const wave=Float32Array.from({length:44100*3},(_,i)=>.25*Math.sin(2*Math.PI*440*i/44100));await h.engine.decode(assetId,encodeWav([wave,wave],44100));
  h.setLoader(async()=>h.engine.buffer(assetId));h.noSave();
  await h.auditionTake(job);await wait(100);
  const before=h.engine.meterLevels()[0],input=w.document.querySelector('[data-control="outputDb"]');
  assert.equal(input.disabled,false);input.value=-18;input.dispatchEvent(new w.Event('input'));input.dispatchEvent(new w.Event('change'));await wait(120);
  assert.ok(h.engine.meterLevels()[0]<before-15,'candidate output knob changes the actual audible graph');
  assert.equal(h.state.project,p,'preview never replaces or edits the arrangement');assert.equal(h.state.history.length,0);assert.equal(h.state.dirty,false);
  const original=[...w.document.querySelectorAll('#sound-rack button')].find(b=>b.textContent==='Original');original.click();await wait(100);
  assert.ok(Math.abs(h.engine.meterLevels()[0]-before)<1,'Original bypass restores neutral audio');
  [...w.document.querySelectorAll('#sound-rack button')].find(b=>b.textContent==='Processed').click();await wait(100);
  assert.ok(h.engine.meterLevels()[0]<before-15);
  h.stop();assert.equal(h.state.audition,null);assert.equal(h.engine.isPlaying(),false);
  await h.auditionTake(job);assert.equal(h.state.audition.project.tracks[0].rack.outputDb,-18,'replay retains the take settings');
  await h.acceptTake(job);assert.notEqual(h.state.project.id,p.id);assert.equal(h.state.project.tracks[0].rack.outputDb,-18);assert.equal(h.state.project.clips[0].assetId,assetId);assert.equal(p.clips.length,0);
  h.state.project=p;h.state.sectionId=p.sections[0].id;h.render();
  let resolve;h.setLoader(()=>new Promise(r=>{resolve=r;}));const loading=h.auditionTake(job);h.stop();resolve(h.engine.buffer(assetId));await loading;
  assert.equal(h.engine.isPlaying(),false,'late decode cannot restart a stopped audition');assert.equal(h.state.audition,null);
 }finally{h.engine.dispose();dom.window.close();delete globalThis.document;}
});

test('Room navigation keeps song, instrument, rack and take tools reachable without duplicate controls',()=>{
 const html=readFileSync(new URL('../../song_builder/templates/song_builder/index.html',import.meta.url),'utf8');
 const dom=new JSDOM(html),d=dom.window.document;d.defaultView.HTMLElement.prototype.scrollIntoView=()=>{};
 const studio=bindConsole(d);
 assert.equal(d.querySelector('.site-bar').contains(d.getElementById('song-title')),true);
 assert.equal(d.querySelector('.workspace').contains(d.getElementById('sound-rack')),true);
 assert.equal(d.querySelector('.arrangement').contains(d.querySelector('.section-deck')),false);
 assert.equal(d.body.dataset.roomView,'song');
 d.querySelector('[data-room-view="rack"]').click();assert.equal(d.body.dataset.roomView,'rack');assert.equal(d.getElementById('sound-rack').hidden,false);
 d.getElementById('tab-takes').click();assert.equal(d.body.dataset.roomView,'instrument');assert.equal(d.getElementById('panel-takes').hidden,false);
 d.querySelector('[data-room-view="song"]').click();assert.equal(d.body.dataset.roomView,'song');
 studio.focusInstrument();assert.equal(d.body.dataset.roomView,'instrument');
 d.getElementById('tab-sound').click();assert.equal(d.body.dataset.roomView,'instrument','Sound stays in the Instrument view');
 assert.equal(d.getElementById('panel-sound').hidden,false);
 d.querySelector('.console-section-tools button:last-child').click();assert.equal(d.getElementById('section-settings').open,true);
 for(const id of ['song-title','song-tempo','song-key','lock-section','record-audio','play-section','loop-section','generate-take','sound-rack'])assert.equal(d.querySelectorAll('#'+id).length,1,id);
 assert.ok(d.querySelector('.room-brand-crop img').src.endsWith('the-room-approved.png'));
 dom.window.close();
});
