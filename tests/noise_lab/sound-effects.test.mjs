import test from 'node:test';
import assert from 'node:assert/strict';
import {createSoundEffects} from '../../noise_lab/static/ui/sound-effects.mjs';

function setup() {
  const elements = new Map(), calls = [], loaded = [], saved = [];
  const get = id => {
    if (!elements.has(id)) elements.set(id,{value:'',checked:false,listeners:{},setAttribute(){},
      addEventListener(event,fn){this.listeners[event]=fn;}});
    return elements.get(id);
  };
  globalThis.document={getElementById:get,body:{dataset:{csrf:'scope'}}};
  get('audio-prompt').value='Metal impact'; get('audio-duration').value='5';
  let revision=0;
  const ui=createSoundEffects({getRevision:()=>revision,loadAudio:async(bytes,accept)=>{if(!accept()) throw Error();loaded.push(bytes);},prepareDownload:(...args)=>saved.push(args)});
  ui.setAvailability(true);
  const reply={ok:true,status:200,headers:{get:()=> 'audio/mpeg'},arrayBuffer:async()=>new ArrayBuffer(256)};
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return reply;};
  return {ui,get,calls,loaded,saved,reply,edit:()=>revision++};
}
test('generation sends text only and requires explicit load before replacing source',async()=>{
  const h=setup(); await h.get('generate-audio').listeners.click();
  assert.equal(h.calls.length,1); assert.equal(h.loaded.length,0);
  const request=JSON.parse(h.calls[0].options.body);
  assert.deepEqual(Object.keys(request).sort(),['loop','prompt','requestId','seconds']);
  assert.equal(h.get('load-generated-audio').hidden,false);
  await h.get('load-generated-audio').listeners.click();assert.equal(h.loaded.length,1);
  h.get('save-generated-audio').listeners.click();assert.equal(h.saved[0][0].type,'audio/mpeg');
});
test('cancel and clear discard late provider responses without loading audio',async()=>{
  for(const action of ['cancel','reset']){
    const h=setup();let finish;
    globalThis.fetch=()=>new Promise(resolve=>finish=resolve);
    const pending=h.get('generate-audio').listeners.click();
    if(action==='cancel')h.get('cancel-audio-generation').listeners.click();else h.ui.reset();
    finish(h.reply);await pending;
    assert.equal(h.get('load-generated-audio').hidden,true);assert.equal(h.loaded.length,0);
  }
});
test('failure preserves a prior generated candidate and never retries',async()=>{
  const h=setup();await h.get('generate-audio').listeners.click();
  let calls=0;globalThis.fetch=async()=>{calls++;return {ok:false,status:429,json:async()=>({message:'Credits unavailable'})};};
  await h.get('generate-audio').listeners.click();
  assert.equal(calls,1);assert.equal(h.get('load-generated-audio').hidden,false);
  assert.match(h.get('sfx-status').textContent,/Credits unavailable/);
});
test('account scope change rejects a returned sound',async()=>{
  const h=setup();let finish;
  globalThis.fetch=()=>new Promise(resolve=>finish=resolve);
  const pending=h.get('generate-audio').listeners.click();
  document.body.dataset.csrf='another';finish(h.reply);await pending;
  assert.equal(h.get('load-generated-audio').hidden,true);
});
