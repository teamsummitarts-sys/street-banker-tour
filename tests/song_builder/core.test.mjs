import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {newProject,newId,validateProject,projectDuration,sectionStart,addSection,updateSection,moveSection,duplicateSection,removeSection,addTrack,updateTrack,removeTrack,addClip,updateClip,removeClip} from '../../song_builder/static/core/project.mjs';
import {AudioEngine,buildRenderPlan,encodeWav,createDemoAudio} from '../../song_builder/static/core/audio.mjs';
if(!globalThis.crypto) globalThis.crypto=webcrypto;

function fixture() {
  let project=addTrack(newProject('Original arrangement'),'Bass');
  const sectionId=project.sections[0].id; const trackId=project.tracks[0].id; const assetId=newId();
  project=addClip(project,{sectionId,trackId,assetId,offset:2,sourceOffset:1,duration:8,loop:true,gainDb:0});
  return {project,sectionId,trackId,assetId,clipId:project.clips[0].id,assets:new Map([[assetId,{duration:5,sampleRate:44100}]])};
}

test('a new song is editable, UUID identified, and independent validation returns a deep clone',()=>{
  const project=newProject(); assert.equal(projectDuration(project),48);
  assert.deepEqual(project.sections.map(section=>section.name),['Verse 1','Chorus','Bridge']);
  const clone=validateProject(project); clone.sections[0].name='Changed'; assert.equal(project.sections[0].name,'Verse 1');
  assert.notEqual(newProject().id,project.id);
});
test('strict import validation rejects untrusted shapes, dangling references, nonfinite values and oversized input',()=>{
  const {project}=fixture();
  const changes=[p=>{p.hostAccount='hidden';},p=>{p.sections[0].url='https://example.com';},p=>{p.tempo=Infinity;},p=>{p.clips[0].trackId=newId();},
    p=>{p.clips[0].offset=15;},p=>{p.clips[0].duration=0;},p=>{p.tracks[0].solo='true';},p=>{p.sections[0].lyrics='x'.repeat(3001);},
    p=>{p.sections[1].id=p.sections[0].id;},p=>{p.sections=[];},p=>{p.tracks[0].pan=2;},p=>{p.clips[0].assetId='../../secret';},p=>{p.sections.length=31;}];
  for(const change of changes) {const candidate=structuredClone(project); change(candidate); assert.throws(()=>validateProject(candidate));}
  let called=false; const accessor={...project}; Object.defineProperty(accessor,'title',{enumerable:true,get(){called=true;return 'bad';}});
  assert.throws(()=>validateProject(accessor)); assert.equal(called,false);
});
test('section edits preserve original state and reorder moves complete music without changing clip references',()=>{
  const {project,sectionId,clipId}=fixture(); const moved=moveSection(project,sectionId,1);
  assert.equal(sectionStart(moved,sectionId),16); assert.equal(sectionStart(project,sectionId),0);
  assert.equal(moved.clips[0].id,clipId); assert.equal(moved.clips[0].sectionId,sectionId);
  assert.throws(()=>updateSection(project,sectionId,{duration:3}),/inside its section/);
  assert.throws(()=>updateSection(project,sectionId,{id:newId()}),/unknown fields/);
  const longer=updateSection(project,sectionId,{duration:20}); assert.equal(projectDuration(longer),52); assert.equal(projectDuration(project),48);
});
test('duplication creates independently editable clips sharing the existing source, and removal cleans references',()=>{
  const {project,sectionId,assetId}=fixture(); const duplicate=duplicateSection(project,sectionId);
  assert.equal(duplicate.sections.length,4); assert.equal(duplicate.clips.length,2);
  assert.notEqual(duplicate.clips[0].id,duplicate.clips[1].id); assert.equal(duplicate.clips[1].assetId,assetId);
  assert.equal(duplicate.clips[1].sectionId,duplicate.sections[1].id);
  const removed=removeSection(duplicate,sectionId); assert.equal(removed.clips.length,1); assert.equal(removed.clips[0].sectionId,duplicate.sections[1].id);
  const noTrack=removeTrack(removed,removed.tracks[0].id); assert.equal(noTrack.tracks.length,0); assert.equal(noTrack.clips.length,0);
});
test('locked content requires a separate unlock; mixing and whole-section reordering remain available',()=>{
  const {project,sectionId,trackId,clipId}=fixture(); const locked=updateSection(project,sectionId,{locked:true});
  assert.throws(()=>updateSection(locked,sectionId,{locked:false,name:'Changed'}),/separate action/);
  assert.throws(()=>updateSection(locked,sectionId,{lyrics:'new'}),/Unlock/);
  assert.throws(()=>removeSection(locked,sectionId),/Unlock/); assert.throws(()=>removeClip(locked,clipId),/Unlock/);
  assert.throws(()=>removeTrack(locked,trackId),/Unlock/); assert.throws(()=>updateClip(locked,clipId,{gainDb:-3}),/Unlock/);
  assert.throws(()=>addClip(locked,{...project.clips[0],id:newId()}),/Unlock/);
  assert.equal(updateTrack(locked,trackId,{gainDb:-6}).tracks[0].gainDb,-6);
  assert.equal(moveSection(locked,sectionId,2).sections[2].id,sectionId);
  const unlocked=updateSection(locked,sectionId,{locked:false}); assert.equal(removeClip(unlocked,clipId).clips.length,0);
});
test('moving a clip cannot introduce content into a locked target section',()=>{
  const {project,clipId}=fixture(); const target=project.sections[1].id; const locked=updateSection(project,target,{locked:true});
  assert.throws(()=>updateClip(locked,clipId,{sectionId:target}),/Unlock/);
});
test('project limits remain enforced through normal editing operations',()=>{
  let p=newProject(); for(let i=0;i<9;i++) p=addTrack(p,`Layer ${i}`);
  p=addTrack(addTrack(addTrack(p))); assert.equal(p.tracks.length,12); assert.throws(()=>addTrack(p));
  let song=newProject(); for(let i=0;i<27;i++) song=addSection(song); assert.equal(song.sections.length,30); assert.throws(()=>addSection(song));
  const single={...newProject(),sections:[{...newProject().sections[0],duration:3}]}; assert.throws(()=>removeSection(single,single.sections[0].id));
});
test('the audio plan seeks inside looped sources and keeps independent clips on one timeline',()=>{
  const {project,assets,assetId,sectionId}=fixture();
  const plan=buildRenderPlan(project,assets,{from:7,to:20});
  assert.equal(plan.duration,13); assert.equal(plan.events.length,1);
  assert.equal(plan.events[0].when,0); assert.equal(plan.events[0].offset,2); assert.equal(plan.events[0].duration,3);
  assert.equal(plan.events[0].loopStart,1); assert.equal(plan.events[0].loopEnd,5);
  const moved=moveSection(project,sectionId,1); const movedPlan=buildRenderPlan(moved,assets);
  assert.equal(movedPlan.events[0].when,18); assert.equal(movedPlan.events[0].assetId,assetId);
});
test('source trims and missing audio fail cleanly even on currently muted tracks',()=>{
  const {project,assets,trackId,clipId}=fixture(); const nonloop=updateClip(project,clipId,{loop:false});
  assert.throws(()=>buildRenderPlan(nonloop,assets),/beyond its source/);
  assert.throws(()=>buildRenderPlan(updateTrack(nonloop,trackId,{muted:true}),assets),/beyond its source/);
  assert.throws(()=>buildRenderPlan(project,new Map()),/not loaded/);
  assert.throws(()=>buildRenderPlan(project,assets,{from:-1})); assert.throws(()=>buildRenderPlan(project,assets,{to:49}));
  const trimmed=updateClip(project,clipId,{loop:false,duration:3}); const plan=buildRenderPlan(trimmed,assets,{from:3});
  assert.equal(plan.events[0].offset,2); assert.equal(plan.events[0].duration,2);
});
test('mute/solo/gain/pan survive mixing; isolated export selects the requested layer',()=>{
  const {project,assets,trackId,sectionId,assetId}=fixture(); let p=addTrack(project,'Second layer'); const second=p.tracks[1].id;
  p=addClip(p,{sectionId,trackId:second,assetId,offset:0,sourceOffset:0,duration:5,loop:false,gainDb:-6});
  p=updateTrack(p,second,{solo:true,gainDb:-6,pan:-1}); const solo=buildRenderPlan(p,assets);
  assert.equal(solo.tracks.length,1); assert.equal(solo.tracks[0].id,second); assert.equal(solo.tracks[0].pan,-1);
  assert.ok(Math.abs(solo.tracks[0].gain-0.501187)<0.000001); assert.ok(Math.abs(solo.events[0].gain-0.501187)<0.000001);
  assert.equal(buildRenderPlan(p,assets,{trackId}).events[0].trackId,trackId);
  p=updateTrack(p,second,{muted:true}); assert.equal(buildRenderPlan(p,assets).events.length,0);
});
test('clips never spill across section boundaries, including permitted millisecond import tolerance',()=>{
  const {project,assets,clipId}=fixture(); const p=updateClip(project,clipId,{offset:8,duration:8.0009});
  const plan=buildRenderPlan(p,assets); assert.equal(plan.events[0].when+plan.events[0].duration,16);
  const chunk=buildRenderPlan(p,assets,{from:10,to:12}); assert.equal(chunk.events[0].duration,2);
});
test('PCM WAV output contains exact stereo frame order, valid headers and bounded samples',()=>{
  const wav=encodeWav([new Float32Array([-1,0,1,2]),new Float32Array([1,0,-1,-2])],44100); const view=new DataView(wav);
  assert.equal(new TextDecoder().decode(new Uint8Array(wav,0,4)),'RIFF'); assert.equal(view.getUint32(4,true),wav.byteLength-8);
  assert.equal(view.getUint16(22,true),2); assert.equal(view.getUint32(24,true),44100); assert.equal(view.getUint32(40,true),16);
  assert.deepEqual(Array.from({length:8},(_,i)=>view.getInt16(44+i*2,true)),[-32768,32767,0,0,32767,-32768,32767,-32768]);
  assert.throws(()=>encodeWav([new Float32Array([NaN])],44100)); assert.throws(()=>encodeWav([new Float32Array([0])],0));
  assert.throws(()=>encodeWav([new Float32Array(2),new Float32Array(1)],44100));
});
test('demo sources are deterministic, separate, audible original synthesis with eight-second WAVs',()=>{
  const first=createDemoAudio(); const second=createDemoAudio(); assert.equal(first.length,3);
  assert.deepEqual(first.map(item=>item.kind),['drums','bass','texture']);
  for(let i=0;i<first.length;i++) {
    assert.match(first[i].name,/Demo.*original synthesis/); assert.deepEqual(new Uint8Array(first[i].buffer),new Uint8Array(second[i].buffer));
    const view=new DataView(first[i].buffer); assert.equal(view.getUint32(40,true),8*44100*2);
    let peak=0; for(let frame=44;frame<view.byteLength;frame+=2) peak=Math.max(peak,Math.abs(view.getInt16(frame,true)));
    assert.ok(peak>500&&peak<20000);
  }
  assert.notDeepEqual(new Uint8Array(first[0].buffer),new Uint8Array(first[1].buffer));
});
test('an engine can be constructed and disposed without opening any audio device',()=>{
  const engine=new AudioEngine(); assert.equal(engine.has(newId()),false); assert.equal(engine.position(),0); engine.stop(); engine.dispose(); engine.dispose();
  assert.throws(()=>engine.buffer(newId()),/disposed/);
});
