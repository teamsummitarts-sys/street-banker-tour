import {bindLive,mergePending} from '../../song_builder/static/ui/live.mjs';
import {bindCollaboration} from '../../song_builder/static/ui/collaboration.mjs';
import {openProducerRecommendation} from '../../song_builder/static/ui/producer-handoff.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {AudioEngine,encodeWav} from '../../song_builder/static/core/audio.mjs';
import * as P from '../../song_builder/static/core/project.mjs';
import {RACK_DEFAULT,sameRack} from '../../song_builder/static/core/rack.mjs';
import {bindConsole} from '../../song_builder/static/ui/console.mjs';
import {renderRackPanel} from '../../song_builder/static/ui/rack-panel.mjs';
import {PendingRequests} from '../../song_builder/static/ui/requests.mjs';
import {bindFadeHandle,effectiveFades} from '../../song_builder/static/ui/fade-handles.mjs';

const require=createRequire(import.meta.url),modules=process.env.RACK_TEST_MODULES;
const dependency=name=>require(modules?`${modules}/${name}`:name);
const {AudioContext}=dependency('node-web-audio-api');
const {JSDOM}=dependency('jsdom');
globalThis.crypto??=webcrypto;
globalThis.AudioContext=class extends AudioContext{constructor(){super({sinkId:{type:'none'},sampleRate:44100});}};
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

async function fixture(){
  const html=readFileSync(new URL('../../song_builder/templates/song_builder/index.html',import.meta.url),'utf8').replaceAll('{{ builder_base_url }}','/song-builder/');
  const dom=new JSDOM(html,{url:'https://example.test/song-builder/'}),w=dom.window;
  globalThis.document=w.document;
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.HTMLCanvasElement.prototype.getContext=()=>({beginPath(){},moveTo(){},lineTo(){},stroke(){}});
  const sandbox={document:w.document,window:w,navigator:w.navigator,location:w.location,history:w.history,sessionStorage:w.sessionStorage,localStorage:w.localStorage,URLSearchParams,URL,FormData,Blob,Option:w.Option,console,AudioEngine,P,RACK_DEFAULT,PendingRequests,bindFadeHandle,effectiveFades,renderRackPanel,sameRack,bindConsole,bindLive,mergePending,bindCollaboration,openProducerRecommendation,setTimeout:()=>0,clearTimeout:()=>{},setInterval:()=>0,clearInterval:()=>{},requestAnimationFrame:()=>{}};
  const source=readFileSync(new URL('../../song_builder/static/ui/controller.mjs',import.meta.url),'utf8').replace(/^import .*;\n/gm,'').replace(/boot\(\);\s*$/,'');
  const h=new Function(...Object.keys(sandbox),source+'\nreturn {state,render,renderDisabled,engine,play,stop,restoreEdit};')(...Object.values(sandbox));
  let p=P.addTrack(P.newProject(),'Bass');p={...p,sections:[{...p.sections[0],duration:3}]};
  const assetId=P.newId();p=P.addClip(p,{assetId,trackId:p.tracks[0].id,sectionId:p.sections[0].id,offset:0,sourceOffset:0,duration:3,loop:false,gainDb:0});
  const wave=Float32Array.from({length:44100*3},(_,i)=>.25*Math.sin(2*Math.PI*440*i/44100));
  await h.engine.decode(assetId,encodeWav([wave,wave],44100));
  h.state.project=p;h.state.sectionId=p.sections[0].id;h.state.trackId=p.tracks[0].id;h.render();
  return {...h,w,p,close(){h.engine.dispose();dom.window.close();delete globalThis.document;}};
}

test('first-use rack previews real audio, cancels cleanly, and commits one undoable edit',async()=>{
  const h=await fixture();
  try{
    const original=JSON.stringify(h.p),d=h.w.document;
    let output=d.querySelector('[data-control="outputDb"]');
    assert.equal(output.disabled,false,'an existing instrument needs no Assign rack step');
    assert.equal([...d.querySelectorAll('#sound-rack button')].some(b=>b.textContent==='Assign rack'),false);
    assert.equal(JSON.stringify(h.state.project),original,'rendering does not assign a saved rack');
    await h.play();await wait(130);
    const before=h.engine.meterLevels()[0];assert.ok(before>-15&&before<-10,`neutral signal ${before}`);
    output.value=-18;output.dispatchEvent(new h.w.Event('input'));await wait(130);
    assert.ok(h.engine.meterLevels()[0]<before-15,'first gesture changes the actual playing signal');
    assert.equal(JSON.stringify(h.state.project),original);assert.equal(h.state.history.length,0);assert.equal(h.state.dirty,false);
    output.dispatchEvent(new h.w.Event('pointercancel'));await wait(130);
    assert.ok(Math.abs(h.engine.meterLevels()[0]-before)<1,'cancel restores neutral audio');
    assert.equal(JSON.stringify(h.state.project),original);assert.equal(output.value,'0');
    output.value=-12;output.dispatchEvent(new h.w.Event('input'));
    output.value=-18;output.dispatchEvent(new h.w.Event('input'));
    output.dispatchEvent(new h.w.Event('change'));await wait(130);
    assert.equal(h.state.project.tracks[0].rack.outputDb,-18);assert.equal(h.state.history.length,1,'all previews commit as one edit');
    assert.equal(h.engine.isPlaying(),true);assert.ok(h.engine.meterLevels()[0]<before-15);
    h.restoreEdit('undo');assert.equal(JSON.stringify(h.state.project),original,'undo removes the newly assigned rack entirely');
    assert.equal(d.querySelector('[data-control="outputDb"]').disabled,false);
    await h.play();await wait(130);assert.ok(Math.abs(h.engine.meterLevels()[0]-before)<1);
  }finally{h.close();}
});

test('first-use rack respects explicit bypass, protection, busy state and empty selection',async()=>{
  const h=await fixture();
  try{
    const d=h.w.document,button=name=>[...d.querySelectorAll('#sound-rack button')].find(b=>b.textContent===name);
    button('Processed').click();assert.equal(h.state.history.length,0,'selecting the already neutral mode is not an edit');
    button('Original').click();assert.equal(h.state.project.tracks[0].rack.enabled,false);
    assert.ok([...d.querySelectorAll('#sound-rack input')].every(input=>input.disabled));
    button('Processed').click();assert.equal(h.state.project.tracks[0].rack.enabled,true);
    assert.ok([...d.querySelectorAll('#sound-rack input')].every(input=>!input.disabled));
    h.state.project=h.p;h.state.history=[];h.state.future=[];h.state.dirty=false;h.render();
    for(const blocker of ['busy','recorder']){
      h.state[blocker]=blocker==='busy'?1:{};h.renderDisabled();
      const output=d.querySelector('[data-control="outputDb"]');assert.equal(output.disabled,true);
      output.value=-24;output.dispatchEvent(new h.w.Event('input'));output.dispatchEvent(new h.w.Event('change'));
      assert.equal(h.state.project.tracks[0].rack,undefined);assert.equal(h.state.history.length,0);
      h.state[blocker]=blocker==='busy'?0:null;h.renderDisabled();assert.equal(output.disabled,false);
    }
    h.state.busy=1;h.render();h.state.busy=0;h.renderDisabled();
    const ready=d.querySelector('[data-control="body"]');ready.value=25;ready.dispatchEvent(new h.w.Event('input'));ready.dispatchEvent(new h.w.Event('change'));
    assert.equal(h.state.project.tracks[0].rack.body,25,'controls recover when loading ends without another render');
    h.state.history=[];h.state.future=[];
    h.state.project=P.updateSection(h.p,h.p.sections[0].id,{locked:true});h.render();
    const output=d.querySelector('[data-control="outputDb"]');assert.equal(output.disabled,true);
    output.value=-24;output.dispatchEvent(new h.w.Event('input'));output.dispatchEvent(new h.w.Event('change'));
    assert.equal(h.state.project.tracks[0].rack,undefined);assert.equal(h.state.history.length,0);
    h.state.project=P.newProject();h.state.sectionId=h.state.project.sections[0].id;h.state.trackId=null;h.render();
    assert.ok([...d.querySelectorAll('#sound-rack input, #sound-rack button')].every(control=>control.disabled));
    assert.equal(d.getElementById('notice').hidden,true,'no handler error');
  }finally{h.close();}
});

