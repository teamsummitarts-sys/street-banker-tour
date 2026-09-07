import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import * as P from '../../song_builder/static/core/project.mjs';
import {buildRenderPlan} from '../../song_builder/static/core/audio.mjs';
import {bindRackSlider} from '../../song_builder/static/ui/rack-panel.mjs';
import {writeBundle,readBundle} from '../../song_builder/static/ui/portable.mjs';
globalThis.crypto ??= webcrypto;
const settings={enabled:true,body:30,bite:-20,dirt:40,space:25,outputDb:-3};
function fixture(){let p=P.addTrack(P.newProject(),'Guitar');return P.addClip(p,{trackId:p.tracks[0].id,sectionId:p.sections[0].id,assetId:P.newId(),offset:0,sourceOffset:0,duration:8,loop:false,gainDb:0});}
test('rack settings round-trip without altering source clips or old project shapes',()=>{
  const p=fixture();assert.deepEqual(P.validateProject(p),p);
  const q=P.updateTrack(p,p.tracks[0].id,{rack:settings});
  assert.deepEqual(q.clips,p.clips);assert.equal(p.tracks[0].rack,undefined);
  const restored=P.validateProject(JSON.parse(JSON.stringify(q)));
  assert.deepEqual(restored,q);restored.tracks[0].rack.dirt=0;assert.equal(q.tracks[0].rack.dirt,40);
  assert.deepEqual(buildRenderPlan(q,new Map([[p.clips[0].assetId,{duration:8}]])).tracks[0].rack,settings);
});
test('malformed rack settings are rejected at the project boundary',()=>{
  const p=fixture();
  for(const patch of [{body:101},{bite:-101},{dirt:-1},{space:101},{outputDb:7},{enabled:'yes'},{surprise:1}])assert.throws(()=>P.updateTrack(p,p.tracks[0].id,{rack:{...settings,...patch}}));
  assert.throws(()=>P.updateTrack(p,p.tracks[0].id,{rack:null}));
});
test('rack changes require unlocking every affected section; unrelated mixing remains available',()=>{
  let p=fixture();p=P.updateTrack(p,p.tracks[0].id,{rack:settings});p=P.updateSection(p,p.sections[0].id,{locked:true});
  assert.throws(()=>P.updateTrack(p,p.tracks[0].id,{rack:{...settings,dirt:80}}),/Unlock/);
  assert.equal(P.updateTrack(p,p.tracks[0].id,{gainDb:-2}).tracks[0].gainDb,-2);
});
test('portable backups retain rack settings with the original audio',async()=>{
  let p=fixture();p=P.updateTrack(p,p.tracks[0].id,{rack:settings});
  const bytes=new Uint8Array([1,2,3]).buffer;
  const bundle=await writeBundle(p,async()=>({name:'Guitar.wav',mime:'audio/wav',bytes}));
  const restored=await readBundle(bundle);assert.deepEqual(restored.project,p);assert.deepEqual(restored.assets[0].bytes,bytes);
});
test('slider previews are immediate; release is one edit and cancellation restores',()=>{
  const input=new EventTarget();input.dataset={control:'dirt'};const previews=[],edits=[];let allowed=true;
  bindRackSlider(input,{read:()=>({...settings}),allowed:()=>allowed,preview:s=>previews.push(s),apply:s=>edits.push(s),display:()=>{}});
  for(const v of [50,60,70]){input.value=v;input.dispatchEvent(new Event('input'));}
  assert.equal(edits.length,0);assert.equal(previews.at(-1).dirt,70);
  input.dispatchEvent(new Event('change'));assert.equal(edits.length,1);assert.equal(edits[0].dirt,70);
  input.value=80;input.dispatchEvent(new Event('input'));input.dispatchEvent(new Event('pointercancel'));
  assert.equal(edits.length,1);assert.equal(previews.at(-1).dirt,40);
  allowed=false;input.dispatchEvent(new Event('input'));input.dispatchEvent(new Event('change'));assert.equal(edits.length,1);
});
