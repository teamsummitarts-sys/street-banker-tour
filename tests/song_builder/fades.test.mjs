import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as P from '../../song_builder/static/core/project.mjs';
import {buildRenderPlan,fadeEnvelope} from '../../song_builder/static/core/audio.mjs';
globalThis.crypto ??= webcrypto;
function fixture(){
  let p=P.addTrack(P.newProject(),'Vocal');
  const clip={sectionId:p.sections[0].id,trackId:p.tracks[0].id,assetId:P.newId(),offset:0,sourceOffset:0,duration:8,loop:false,gainDb:0};
  p=P.addClip(p,clip);p=P.addClip(p,{...clip,offset:6});return p;
}
test('old clips retain their exact shape; invalid fades are rejected',()=>{
  const p=fixture();assert.deepEqual(P.validateProject(p),p);
  for(const bad of [-1,NaN,121,null,'1'])assert.throws(()=>P.updateClip(p,p.clips[0].id,{fadeIn:bad}));
});
test('a crossfade preserves sources and timing and produces complementary overlap levels',()=>{
  const p=fixture(),q=P.crossfadeClip(p,p.clips[0].id);
  assert.equal(q.clips[0].fadeOut,2);assert.equal(q.clips[1].fadeIn,2);
  assert.equal(p.clips[0].fadeOut,undefined);
  for(let i=0;i<2;i++)for(const field of ['assetId','offset','duration','sourceOffset'])assert.equal(q.clips[i][field],p.clips[i][field]);
  for(const t of [0,.5,1,1.5])assert.equal(fadeEnvelope(q.clips[0],6+t,.1)[0].value+fadeEnvelope(q.clips[1],t,.1)[0].value,1);
  const locked=P.updateSection(p,p.sections[0].id,{locked:true});assert.throws(()=>P.crossfadeClip(locked,p.clips[0].id),/Unlock/);
});
test('non-overlapping and nested clips cannot be crossfaded',()=>{
  let p=fixture();p=P.updateClip(p,p.clips[1].id,{offset:8});assert.throws(()=>P.crossfadeClip(p,p.clips[0].id),/Overlap/);
  p=P.updateClip(p,p.clips[1].id,{offset:2,duration:3});assert.throws(()=>P.crossfadeClip(p,p.clips[0].id),/Stagger/);
});
test('seek and range export resume inside the existing fade instead of restarting it',()=>{
  let p=fixture();p=P.updateClip(p,p.clips[0].id,{fadeIn:4,fadeOut:2});
  const assets=new Map([[p.clips[0].assetId,{duration:16,sampleRate:44100}]]);
  const plan=buildRenderPlan(p,assets,{from:2,to:7});
  assert.deepEqual(plan.events[0].envelope,[{time:0,value:.5},{time:2,value:1},{time:4,value:1},{time:5,value:.5}]);
  assert.deepEqual(fadeEnvelope({duration:2,fadeIn:4,fadeOut:4},0,2),[{time:0,value:0},{time:1,value:1},{time:2,value:0}]);
});
test('the shared playback/export graph schedules fade automation at the audio clock',()=>{
  const code=readFileSync(new URL('../../song_builder/static/core/audio.mjs',import.meta.url),'utf8');
  const graphCode=code.slice(code.indexOf('function graph('),code.indexOf('/** Browser-only'));
  const scope=vm.createContext({});vm.runInContext(graphCode,scope);
  const calls=[],starts=[];let index=0;
  const context={createGain(){const n=index++;return {gain:{setValueAtTime:(...args)=>calls.push([n,'set',...args]),linearRampToValueAtTime:(...args)=>calls.push([n,'ramp',...args])},connect(){},disconnect(){}};},
    createStereoPanner:()=>({pan:{},connect(){},disconnect(){}}),
    createBufferSource:()=>({connect(){},disconnect(){},stop(){},start:(...args)=>starts.push(args)})};
  scope.graph(context,{tracks:[{id:'track',gain:1,pan:0}],events:[{trackId:'track',assetId:'asset',gain:.5,when:2,offset:3,duration:4,loop:false,envelope:[{time:0,value:.5},{time:1,value:1},{time:4,value:0}]}]},new Map([['asset',{}]]),{},10);
  assert.deepEqual(calls,[[1,'set',.25,12],[1,'ramp',.5,13],[1,'ramp',0,16]]);
  assert.deepEqual(starts,[[12,3,4]]);
});
