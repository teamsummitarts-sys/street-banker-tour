import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../../song_builder/static/ui/controller.mjs',import.meta.url),'utf8');
function setup(){
  const audio=[{paused:false,ended:false,pause(){this.paused=true;}},{paused:false,ended:false,pause(){this.paused=true;}}];
  const storage=new Map();let replacements=0,stops=0;
  const state={rejectedJobs:new Set(),playing:true,previewEnd:10,jobs:[]};
  const context=vm.createContext({state,localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
    engine:{stop(){stops++;}},$:id=>id==='jobs'?{querySelectorAll:()=>audio,replaceChildren(){replacements++;}}:{setAttribute(){}},
    pendingRequests:{get:()=>null},notify(){}});
  for(const name of ['stop','takeRejected','renderJobs','rejectTake']){
    const start=source.indexOf(`function ${name}(`),next=source.indexOf('\nfunction ',start+1),asyncNext=source.indexOf('\nasync function ',start+1);
    const ends=[next,asyncNext].filter(i=>i>=0);vm.runInContext(source.slice(start,Math.min(...ends)),context);
  }
  return {context,audio,state,storage,replacements:()=>replacements,stops:()=>stops};
}
test('background job refresh preserves a playing candidate; Stop silences all audio',()=>{
  const s=setup();s.context.renderJobs();assert.equal(s.replacements(),0);
  s.context.stop();assert.ok(s.audio.every(a=>a.paused));assert.equal(s.stops(),1);
  s.context.renderJobs();assert.equal(s.replacements(),1);
});
test('starting a candidate leaves that player running and stops other playback',()=>{
  const s=setup();s.context.stop(s.audio[0]);assert.equal(s.audio[0].paused,false);
  assert.equal(s.audio[1].paused,true);assert.equal(s.state.playing,false);
});
test('rejection survives an in-memory reset without modifying arrangement data',()=>{
  const s=setup(),job={projectId:'project-a',id:'take-a'};
  s.context.rejectTake(job);s.state.rejectedJobs=new Set();
  assert.equal(s.context.takeRejected(job),true);
  assert.equal(s.context.takeRejected({...job,projectId:'project-b'}),false);
  assert.ok(s.audio.every(a=>a.paused));
});
