import test from 'node:test';
import assert from 'node:assert/strict';
import {newProject, addTrack, addClip, newId} from '../../song_builder/static/core/project.mjs';
import {readBundle, writeBundle} from '../../song_builder/static/ui/portable.mjs';

function fixture(){
  let project=addTrack(newProject(),'Drums');
  const id=newId();
  project=addClip(project,{trackId:project.tracks[0].id,sectionId:project.sections[0].id,assetId:id,offset:0,sourceOffset:0,duration:3,loop:false,gainDb:0});
  return {project,id};
}
test('portable backup round trips embedded bytes without host URLs',async()=>{
  const {project,id}=fixture(),bytes=new Uint8Array([0,1,127,255]).buffer;
  const blob=await writeBundle(project,async()=>({name:'Drums.wav',mime:'audio/wav',bytes}));
  const loaded=await readBundle(blob);
  assert.deepEqual(loaded.project,project);
  assert.equal(loaded.assets[0].id,id);
  assert.deepEqual(loaded.assets[0].bytes,bytes);
  assert.equal((await blob.text()).includes('https://'),false);
});
test('large audio backup does not overflow regular expression stack',async()=>{
  const {project}=fixture();
  const bytes=new Uint8Array(1024*1024).buffer;
  const blob=await writeBundle(project,async()=>({name:'Layer.wav',mime:'audio/wav',bytes}));
  assert.equal((await readBundle(blob)).assets[0].bytes.byteLength,bytes.byteLength);
});
test('missing audio and noncanonical base64 fail before import',async()=>{
  const {project}=fixture();
  const blob=await writeBundle(project,async()=>({name:'Layer.wav',mime:'audio/wav',bytes:new Uint8Array([1]).buffer}));
  const envelope=JSON.parse(await blob.text());
  envelope.assets[0].dataBase64='AR==';
  await assert.rejects(readBundle(new Blob([JSON.stringify(envelope)])),/malformed/);
  envelope.assets=[];
  await assert.rejects(readBundle(new Blob([JSON.stringify(envelope)])),/missing audio/);
});
