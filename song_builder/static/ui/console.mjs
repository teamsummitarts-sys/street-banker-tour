/** Presentation only. Project/audio mutations remain in the controller. */
export function bindConsole(document){
  const $=id=>document.getElementById(id);
  $('panel-trim').append($('clip-inspector'));
  $('panel-takes').append(document.querySelector('.generate-desk'));
  document.querySelector('main').append(document.querySelector('.transport'));
  const exports=document.querySelector('.export-desk'),menu=document.createElement('details'),summary=document.createElement('summary');
  menu.className='export-menu';summary.textContent='Export';menu.append(summary,exports);document.querySelector('.project-bar').append(menu);
  const tabs=['sound','trim','takes'];
  function select(name,{focus=false}={}){
    for(const key of tabs){const selected=key===name;const tab=$(`tab-${key}`);tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;$(`panel-${key}`).hidden=!selected;}
    $('sound-rack').hidden=name!=='sound';
    if(focus)$(`tab-${name}`).focus();
  }
  tabs.forEach((name,index)=>{
    const tab=$(`tab-${name}`);tab.addEventListener('click',()=>select(name));
    tab.addEventListener('keydown',e=>{let next;if(e.key==='ArrowRight')next=(index+1)%3;if(e.key==='ArrowLeft')next=(index+2)%3;if(e.key==='Home')next=0;if(e.key==='End')next=2;if(next!==undefined){e.preventDefault();select(tabs[next],{focus:true});}});
  });
  $('all-instruments').addEventListener('click',()=>document.body.classList.remove('instrument-focus'));
  let clipping=false,lastPaint=0,viewStart=0,viewDuration=1;
  $('clear-clip').addEventListener('click',()=>{clipping=false;paintClip();});
  function paintClip(){$('clear-clip').textContent=clipping?'Clipped · reset':'No clipping';$('clear-clip').setAttribute('aria-pressed',String(clipping));}
  return {
    focusInstrument(){document.body.classList.add('instrument-focus');},
    sync(project,trackId,section,clip){
      const track=project.tracks.find(t=>t.id===trackId);$('instrument-heading').textContent=track?.name||'Select an instrument';
      const mix=document.querySelector('.track.selected .track-mix');$('selected-mixer').replaceChildren();if(mix)$('selected-mixer').append(mix);
      const solos=project.tracks.filter(t=>t.solo);$('solo-status').hidden=!solos.length;$('clear-solos').hidden=!solos.length;
      $('solo-status').textContent=solos.length?`Solo active: ${solos.map(t=>t.name).join(', ')}`:'';
      $('trim-empty').hidden=Boolean(clip);if(clip)$('clip-inspector').open=true;
      viewStart=0;for(const item of project.sections){if(item.id===section.id)break;viewStart+=item.duration;}viewDuration=section.duration;
      for(const lane of document.querySelectorAll('.lane-content')){const head=document.createElement('i');head.className='lane-playhead';head.setAttribute('aria-hidden','true');lane.append(head);}
      document.querySelector('.track-desk').style.setProperty('--bar-width',`${240/project.tempo/section.duration*100}%`);
      const ruler=$('section-ruler');ruler.replaceChildren();const bars=section.duration*project.tempo/240,step=Math.max(1,Math.ceil(bars/12));
      for(let bar=0;bar<bars;bar+=step){const mark=document.createElement('span');mark.style.left=`${bar/bars*100}%`;mark.textContent=String(bar+1);ruler.append(mark);}
      ruler.setAttribute('aria-label',`${section.name}, ${bars.toFixed(1)} bars in 4/4`);
      $('loop-section').disabled=!project.clips.length;
    },
    playhead(position){const percent=(position-viewStart)/viewDuration*100;for(const head of document.querySelectorAll('.lane-playhead')){head.hidden=percent<0||percent>100;head.style.left=`${percent}%`;}},
    meter(levels,time){
      if(levels.some(value=>value>=0))clipping=true;
      if(time-lastPaint<70)return;lastPaint=time;
      for(const [index,name]of ['left','right'].entries()){
        const value=levels[index]??-Infinity;$(`meter-${name}`).value=Math.max(-60,Math.min(0,value));$(`peak-${name}`).value=Number.isFinite(value)?`${value.toFixed(1)} dBFS`:'−∞ dBFS';if(value>=0)clipping=true;
      }
      const maximum=Math.max(...levels);$('meter-needle').style.transform=`rotate(${-65+Math.max(0,Math.min(1,(maximum+48)/48))*130}deg)`;paintClip();
    }
  };
}

/** Vertical drag plus native keyboard control, cancellation and double-tap reset. */
export function bindKnob(surface,input,defaultValue){
  const Event=input.ownerDocument.defaultView.Event;let gesture=null,lastTap=0;
  const emit=type=>input.dispatchEvent(new Event(type));
  const finish=(cancel=false)=>{
    if(!gesture)return;const {id,moved}=gesture;gesture=null;
    try{surface.releasePointerCapture(id);}catch{/* detached/cancelled */}
    if(cancel){emit('pointercancel');return;}
    emit('change');
    if(!moved){const now=Date.now();if(now-lastTap<350){input.value=defaultValue;emit('input');emit('change');lastTap=0;}else lastTap=now;}
  };
  surface.addEventListener('pointerdown',e=>{if(input.disabled||gesture||e.button!==0)return;e.preventDefault();input.focus();surface.setPointerCapture(e.pointerId);gesture={id:e.pointerId,y:e.clientY,value:Number(input.value),moved:false};});
  surface.addEventListener('pointermove',e=>{if(!gesture||gesture.id!==e.pointerId)return;const delta=gesture.y-e.clientY;if(Math.abs(delta)<3&&!gesture.moved)return;gesture.moved=true;const step=Number(input.step)||1;input.value=Math.max(Number(input.min),Math.min(Number(input.max),Math.round((gesture.value+delta/160*(input.max-input.min))/step)*step));emit('input');});
  surface.addEventListener('pointerup',e=>{if(gesture?.id===e.pointerId)finish();});
  surface.addEventListener('pointercancel',()=>finish(true));
  surface.addEventListener('lostpointercapture',()=>finish(true));
  input.addEventListener('keydown',e=>{if(e.key==='Escape'&&gesture){e.preventDefault();finish(true);}});
}
