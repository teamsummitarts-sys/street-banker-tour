import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareWav} from '../../song_builder/static/ui/audio-prepare.mjs';
import {previewWav} from '../../song_builder/static/ui/analysis-upload.mjs';
import {candidateForTake} from '../../song_builder/static/ui/take-comparison.mjs';
import * as P from '../../song_builder/static/core/project.mjs';
function buffer(){const a=Float32Array.from({length:48000*4},(_,i)=>i<48000?.2:.6),b=a.map(v=>v/2);return {duration:4,sampleRate:48000,numberOfChannels:2,getChannelData:i=>i?b:a};}
test('excerpt copies preserve source, duration and measured waveform while explicitly downmixing',async()=>{
 const source=buffer(),original=source.getChannelData(0).slice(),r=prepareWav(source,{start:1,end:3,sampleRate:32000,channels:1});
 const data=new DataView(r.bytes);assert.equal(data.getUint16(22,true),1);assert.equal(data.getUint32(24,true),32000);
 const preview=await previewWav(new File([r.bytes],'excerpt.wav'));
 assert.equal(preview.duration,2);assert.ok(Math.abs(preview.peaks[0]-.45)<.001);assert.deepEqual(source.getChannelData(0),original);
});
test('invalid and oversized conversion is rejected before allocation',()=>{
 assert.throws(()=>prepareWav(buffer(),{start:4,end:2}),/excerpt/);
 const long={...buffer(),duration:400};assert.throws(()=>prepareWav(long,{start:0,end:400}),/14 MiB/);
 assert.throws(()=>prepareWav(buffer(),{sampleRate:192000}),/supported/);
});
test('comparison replaces only the target instrument in its section and leaves source untouched',()=>{
 let p=P.addTrack(P.newProject(),'Bass');p=P.addTrack(p,'Vocal');const source=P.newId(),other=P.newId();
 p=P.addClip(p,{assetId:source,trackId:p.tracks[0].id,sectionId:p.sections[0].id,offset:0,sourceOffset:0,duration:3,loop:false,gainDb:0});
 p=P.addClip(p,{assetId:other,trackId:p.tracks[1].id,sectionId:p.sections[0].id,offset:0,sourceOffset:0,duration:3,loop:false,gainDb:0});
 const before=JSON.stringify(p),take={sectionId:p.sections[0].id,trackId:p.tracks[0].id,clips:[{...p.clips[0],assetId:P.newId()}]};
 const result=candidateForTake(p,take);assert.equal(JSON.stringify(p),before);assert.deepEqual(result.clips.find(c=>c.trackId===p.tracks[1].id),p.clips[1]);assert.equal(result.clips.find(c=>c.trackId===p.tracks[0].id).assetId,take.clips[0].assetId);
});
