// Optional native audio/DOM integration checks; see docs/song-builder/RACK.md.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {webcrypto} from 'node:crypto';
const require=createRequire(import.meta.url);
const dependency=name=>require(process.env.RACK_TEST_MODULES?`${process.env.RACK_TEST_MODULES}/${name}`:name);
const {AudioContext,OfflineAudioContext}=dependency('node-web-audio-api');
const {JSDOM}=dependency('jsdom');
import {createRack,RACK_DEFAULT,RACK_PRESETS,presetSettings} from '../../song_builder/static/core/rack.mjs';
import {AudioEngine,encodeWav} from '../../song_builder/static/core/audio.mjs';
import * as P from '../../song_builder/static/core/project.mjs';
import {renderRackPanel} from '../../song_builder/static/ui/rack-panel.mjs';
globalThis.crypto??=webcrypto;
globalThis.AudioContext=class extends AudioContext{constructor(){super({sinkId:{type:'none'},sampleRate:44100});}};
globalThis.OfflineAudioContext=OfflineAudioContext;
const rate=44100;
const rms=samples=>Math.sqrt(samples.reduce((sum,s)=>sum+s*s,0)/samples.length);
async function processed(samples,settings){
  const c=new OfflineAudioContext(2,samples.length,rate),buffer=c.createBuffer(2,samples.length,rate);
  buffer.copyToChannel(samples,0);buffer.copyToChannel(samples,1);
  const source=c.createBufferSource();source.buffer=buffer;const rack=createRack(c,settings);
  source.connect(rack.input);rack.output.connect(c.destination);source.start();
  const result=await c.startRendering();rack.dispose();return result.getChannelData(0);
}
test('native audio: neutral and Original preserve samples; tone, drive and room change sound',async()=>{
  const samples=Float32Array.from({length:rate},(_,i)=>.15*Math.sin(2*Math.PI*110*i/rate));
  const neutral=await processed(samples,RACK_DEFAULT);
  assert.ok(rms(neutral.map((s,i)=>s-samples[i]))<.00001);
  const bypass=await processed(samples,{enabled:false,body:100,bite:100,dirt:100,space:100,outputDb:6});
  assert.ok(rms(bypass.map((s,i)=>s-samples[i]))<.00001);
  const full=await processed(samples,{...RACK_DEFAULT,body:80});
  assert.ok(rms(full.subarray(4000))>rms(samples.subarray(4000))*1.4);
  const brightInput=Float32Array.from({length:rate},(_,i)=>.1*Math.sin(2*Math.PI*6500*i/rate));
  const bright=await processed(brightInput,{...RACK_DEFAULT,bite:80});
  assert.ok(rms(bright.subarray(4000))>rms(brightInput.subarray(4000))*1.4);
  const driven=await processed(samples,{...RACK_DEFAULT,dirt:100});
  assert.ok(rms(driven.map((s,i)=>s-samples[i]))>.005);
  const impulse=new Float32Array(rate);impulse[100]=.5;
  const spacious=await processed(impulse,{...RACK_DEFAULT,space:100});
  assert.ok(rms(spacious.subarray(1000,12000))>.00001,'room must ring after the source ends');
  assert.ok([...spacious,...driven].every(Number.isFinite));
});
test('native audio: exported chunks and selected ranges carry room tails across eight seconds',async()=>{
  const samples=new Float32Array(rate*18);
  for(let i=Math.round(rate*7.8);i<Math.round(rate*7.98);i++)samples[i]=.15*Math.sin(2*Math.PI*220*i/rate);
  let p=P.addTrack(P.newProject(),'Guitar');p={...p,sections:[{...p.sections[0],duration:18}]};
  const id=P.newId();p=P.addClip(p,{assetId:id,trackId:p.tracks[0].id,sectionId:p.sections[0].id,offset:0,sourceOffset:0,duration:18,loop:false,gainDb:0});
  const settings={...RACK_DEFAULT,space:100,body:20,bite:-10};p=P.updateTrack(p,p.tracks[0].id,{rack:settings});
  const engine=new AudioEngine();
  try{
    await engine.decode(id,encodeWav([samples,samples],rate));
    const reference=await processed(engine.buffer(id).getChannelData(0),settings);
    const wav=new DataView(await (await engine.render(p)).arrayBuffer());
    const range=new DataView(await (await engine.render(p,{from:8,to:9})).arrayBuffer());
    let maxError=0,maxRangeError=0,energy=0;
    for(let i=8*rate;i<9*rate;i++){
      const actual=wav.getInt16(44+i*4,true)/32768,partial=range.getInt16(44+(i-8*rate)*4,true)/32768;
      maxError=Math.max(maxError,Math.abs(actual-reference[i]));maxRangeError=Math.max(maxRangeError,Math.abs(partial-actual));energy+=actual*actual;
    }
    assert.ok(energy>0.00001,'export retains the preceding audio tail');
    assert.ok(maxError<.0001,`chunk error ${maxError}`);assert.ok(maxRangeError<.0001,`range error ${maxRangeError}`);
    await engine.play(p);const active=engine._active,generation=engine._generation;
    assert.equal(engine.updateRack(p.tracks[0].id,{...settings,dirt:50}),true);
    assert.equal(engine._active,active);assert.equal(engine._generation,generation);
    engine.stop();assert.equal(engine._active,null);
  }finally{engine.dispose();}
});
test('DOM: presets survive reordered JSON, controls commit, reset and Original disable correctly',()=>{
  const dom=new JSDOM('<section id="rack"></section>');globalThis.document=dom.window.document;
  const root=document.getElementById('rack'),track={name:'Guitar',rack:JSON.parse(JSON.stringify(presetSettings(RACK_PRESETS[2]),Object.keys(RACK_DEFAULT).sort()))};
  const applied=[];let cancel=()=>{};
  const render=()=>{cancel();cancel=renderRackPanel(root,{track,blocked:false,protectedNames:[],allowed:()=>true,preview:()=>{},apply:s=>{applied.push(s);track.rack=s;render();}});};render();
  assert.equal(root.querySelector('.rack-presets button[aria-pressed="true"] strong').textContent,'Grit');
  let slider=root.querySelector('[data-control="body"]');slider.value=55;slider.dispatchEvent(new dom.window.Event('input'));slider.dispatchEvent(new dom.window.Event('change'));
  assert.equal(applied.length,1);assert.equal(track.rack.body,55);
  root.querySelector('[aria-label="Reset Body"]').click();assert.equal(track.rack.body,0);
  [...root.querySelectorAll('button')].find(b=>b.textContent==='Original').click();
  assert.equal(track.rack.enabled,false);assert.ok([...root.querySelectorAll('input')].every(input=>input.disabled));
  cancel();dom.window.close();delete globalThis.document;
});

test('empty Room keeps five disabled metal controls and cannot apply a preset',()=>{
  const dom=new JSDOM('<section id="rack"></section>');globalThis.document=dom.window.document;
  const root=document.getElementById('rack');let changes=0;
  renderRackPanel(root,{track:null,blocked:false,protectedNames:[],allowed:()=>true,preview:()=>{},apply:()=>{changes++;}});
  assert.equal(root.querySelectorAll('.rack-dial').length,5);
  assert.ok([...root.querySelectorAll('button,input')].every(el=>el.disabled));
  root.querySelector('.rack-presets button').click();assert.equal(changes,0);
  dom.window.close();delete globalThis.document;
});
