import test from 'node:test';
import assert from 'node:assert/strict';
import {bindFadeHandle} from '../../song_builder/static/ui/fade-handles.mjs';
function setup(key='fadeIn'){
  const handle=new EventTarget();handle.setPointerCapture=()=>{};
  const edits=[],previews=[];let enabled=true,restored=0;
  bindFadeHandle(handle,{duration:10,fadeIn:1,fadeOut:2},key,{width:()=>100,allowed:()=>enabled,preview:x=>previews.push(x),apply:x=>edits.push(x),restore:()=>restored++});
  return {edits,previews,disable:()=>{enabled=false;},restored:()=>restored,
    fire(type,x=0){const event=new Event(type,{cancelable:true});Object.assign(event,{pointerId:1,clientX:x,isPrimary:true,button:0});handle.dispatchEvent(event);}};
}
test('drag previews without writing, then commits a single fade edit on release',()=>{
  const s=setup();s.fire('pointerdown',10);s.fire('pointermove',30);s.fire('pointermove',40);
  assert.equal(s.edits.length,0);assert.equal(s.previews.at(-1).fadeIn,4);
  s.fire('pointerup',40);assert.deepEqual(s.edits,[{fadeIn:4,fadeOut:2}]);
  s.fire('lostpointercapture');assert.equal(s.restored(),0);
});
test('outward drag can restore zero; fade-out grows when dragged left and clamps to fit',()=>{
  const s=setup();s.fire('pointerdown',20);s.fire('pointerup',0);assert.equal(s.edits[0].fadeIn,0);
  const out=setup('fadeOut');out.fire('pointerdown',100);out.fire('pointerup',-100);assert.deepEqual(out.edits,[{fadeIn:1,fadeOut:9}]);
});
test('cancelled, protected and stale gestures do not change clips',()=>{
  for(const cancel of ['pointercancel','lostpointercapture']){const s=setup();s.fire('pointerdown');s.fire('pointermove',30);s.fire(cancel);s.fire('pointerup',30);assert.equal(s.edits.length,0);assert.equal(s.restored(),1);}
  const s=setup();s.fire('pointerdown');s.fire('pointermove',20);s.disable();s.fire('pointerup',20);assert.equal(s.edits.length,0);
  const locked=setup();locked.disable();locked.fire('pointerdown');locked.fire('pointerup',20);assert.equal(locked.edits.length,0);
});
