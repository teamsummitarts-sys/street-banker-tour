/** Presentation only. Project/audio mutations remain in the controller. */
export function bindConsole(document){
  const $=id=>document.getElementById(id);
  // Calibrated peak scale: both the tick positions and moving needle use dBFS.
  const glass=document.querySelector('.analog-meter'),svgNS='http://www.w3.org/2000/svg';
  const svg=(tag,attributes)=>{const element=document.createElementNS(svgNS,tag);for(const [key,value]of Object.entries(attributes))element.setAttribute(key,value);return element;};
  const dial=svg('svg',{viewBox:'0 0 240 142','aria-hidden':'true'});
  const point=(db,r)=>{const a=(-65+(db+48)/48*130)*Math.PI/180;return [120+Math.sin(a)*r,145-Math.cos(a)*r];};
  const arc=(from,to,r)=>{const a=point(from,r),b=point(to,r);return `M ${a[0]} ${a[1]} A ${r} ${r} 0 0 1 ${b[0]} ${b[1]}`;};
  dial.append(svg('path',{d:arc(-48,0,109),class:'meter-arc'}),svg('path',{d:arc(-6,0,109),class:'meter-redline'}));
  for(let db=-48;db<=0;db+=2){const major=db%12===0||db===-6,a=point(db,109),b=point(db,major?97:103);dial.append(svg('path',{d:`M ${a[0]} ${a[1]} L ${b[0]} ${b[1]}`,class:db>=-6?'meter-tick hot':'meter-tick'}));}
  for(const db of [-48,-36,-24,-12,-6,0]){const p=point(db,85),label=svg('text',{x:p[0],y:p[1]+3,'text-anchor':'middle',class:'meter-number'});label.textContent=String(db).replace('-','−');dial.append(label);}
  const legend=svg('text',{x:120,y:112,'text-anchor':'middle',class:'meter-legend'});legend.textContent='PEAK · dBFS';dial.append(legend);
  const needle=svg('g',{id:'meter-needle'});needle.append(svg('path',{d:'M 119 145 L 120 34 L 121 145 Z',class:'needle-body'}));dial.append(needle);
  glass.replaceChildren(dial);
  $('panel-trim').append($('clip-inspector'));
  $('panel-takes').append(document.querySelector('.generate-desk'));
  document.querySelector('main').append(document.querySelector('.transport'));
  document.querySelector('main').append(document.querySelector('footer'));
  const exports=document.querySelector('.export-desk'),menu=document.createElement('details'),summary=document.createElement('summary');
  menu.className='export-menu';summary.textContent='Export';menu.append(summary,exports);document.querySelector('.project-bar').append(menu);
  for(const side of ['left','right']){const meter=$(`meter-${side}`),housing=document.createElement('span');housing.className='led-meter';meter.before(housing);housing.append(meter);}
  // One console: project header, full-width song map, arrangement/channel strip, rack.
  const main=document.querySelector('main'),header=document.querySelector('.site-bar'),projectBar=document.querySelector('.project-bar');
  header.append(projectBar);document.querySelector('footer').prepend(document.querySelector('.back-link'));
  projectBar.append(document.querySelector('.session-status'));
  const setup=document.createElement('details');setup.className='session-menu';
  const setupTitle=document.createElement('summary');setupTitle.textContent='Session';setup.append(setupTitle);
  const setupFields=document.createElement('div');setupFields.className='session-fields';
  setupFields.append(document.querySelector('.compact-field'),document.querySelector('.key-field'));setup.append(setupFields);projectBar.append(setup);
  // Keep the phone's first screen focused on music; reuse every existing action.
  const projectTools=document.createElement('div');projectTools.id='room-project-tools';projectTools.className='room-project-tools';
  projectTools.append($('save-project'),document.querySelector('.project-menu'),menu,setup);
  const toolsToggle=document.createElement('button');toolsToggle.type='button';toolsToggle.className='room-project-toggle';toolsToggle.textContent='Project';toolsToggle.setAttribute('aria-controls',projectTools.id);toolsToggle.setAttribute('aria-expanded','false');
  const closeTools=()=>{projectTools.classList.remove('is-open');toolsToggle.setAttribute('aria-expanded','false');};
  toolsToggle.addEventListener('click',()=>{const open=toolsToggle.getAttribute('aria-expanded')!=='true';toolsToggle.setAttribute('aria-expanded',String(open));projectTools.classList.toggle('is-open',open);});
  projectTools.addEventListener('keydown',event=>{if(event.key==='Escape'){closeTools();toolsToggle.focus();}});
  projectBar.append(toolsToggle,projectTools);
  const deck=document.querySelector('.section-deck');main.insertBefore(deck,document.querySelector('.workspace'));
  document.querySelector('.audio-actions').append(document.querySelector('.snap-control'),$('loop-section'),$('play-section'));
  document.querySelector('.workspace').append($('sound-rack'));
  const nav=document.createElement('nav');nav.className='room-navigation';nav.setAttribute('aria-label','Studio views');
  for(const [key,label] of [['song','Song'],['instrument','Instrument'],['rack','Rack']]){const b=document.createElement('button');b.type='button';b.textContent=label;b.dataset.roomView=key;b.addEventListener('click',()=>{if(key==='rack')select('sound',{view:'rack'});else showView(key);});nav.append(b);}
  deck.after(nav);
  function showView(name){document.body.dataset.roomView=name;for(const b of nav.querySelectorAll('button'))b.setAttribute('aria-pressed',String(b.dataset.roomView===name));}
  showView('song');
  const sectionTools=document.createElement('div');sectionTools.className='console-section-tools';
  const settingsButton=document.createElement('button');settingsButton.type='button';settingsButton.textContent='Section settings';settingsButton.addEventListener('click',()=>{showView('instrument');$('section-settings').open=!$('section-settings').open;});
  sectionTools.append($('lock-section'),settingsButton);document.querySelector('.track-desk>.section-heading').append(sectionTools);
  const tabs=['sound','trim','takes'];
  function select(name,{focus=false,view='instrument'}={}){
    for(const key of tabs){const selected=key===name;const tab=$(`tab-${key}`);tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;$(`panel-${key}`).hidden=!selected;}
    $('sound-rack').hidden=name!=='sound';
    showView(view);
    if(focus)$(`tab-${name}`).focus();
  }
  tabs.forEach((name,index)=>{
    const tab=$(`tab-${name}`);tab.addEventListener('click',()=>select(name));
    tab.addEventListener('keydown',e=>{let next;if(e.key==='ArrowRight')next=(index+1)%3;if(e.key==='ArrowLeft')next=(index+2)%3;if(e.key==='Home')next=0;if(e.key==='End')next=2;if(next!==undefined){e.preventDefault();select(tabs[next],{focus:true});}});
  });
  $('start-ai')?.addEventListener('click',()=>{select('takes');$('panel-takes').scrollIntoView({behavior:'smooth',block:'start'});$('take-prompt').focus();});
  $('all-instruments').addEventListener('click',()=>{document.body.classList.remove('instrument-focus');showView('song');});
  // One tactile channel strip, still using the controller's existing native inputs.
  function dressMixer(mix){
    if(!mix||mix.dataset.dressed)return;mix.dataset.dressed='true';
    const [level,pan]=mix.querySelectorAll('label'),levelInput=level.querySelector('input'),panInput=pan.querySelector('input');
    const decorate=(label,name,input)=>{label.replaceChildren();const title=document.createElement('strong'),value=document.createElement('output');title.textContent=name;label.append(title,input,value);return value;};
    level.className='mixer-level';const levelValue=decorate(level,'Level',levelInput);levelInput.className='mixer-fader';levelInput.setAttribute('aria-orientation','vertical');
    const scale=document.createElement('span');scale.className='fader-scale';scale.setAttribute('aria-hidden','true');for(const value of [6,0,-12,-24,-48]){const mark=document.createElement('i');mark.textContent=value>0?`+${value}`:String(value).replace('-','−');mark.style.top=`${(6-value)/66*100}%`;scale.append(mark);}level.append(scale);
    const updateLevel=()=>{levelValue.value=`${Number(levelInput.value)>0?'+':''}${levelInput.value} dB`;levelInput.setAttribute('aria-valuetext',levelValue.value);};updateLevel();levelInput.addEventListener('input',updateLevel);
    pan.className='mixer-pan';const panValue=decorate(pan,'Pan',panInput),surface=document.createElement('div'),face=document.createElement('i');surface.className='pan-dial rack-dial';face.className='dial-face';face.setAttribute('aria-hidden','true');panInput.before(surface);surface.append(panInput,face);bindKnob(surface,panInput,0);
    const updatePan=()=>{const v=Number(panInput.value);panValue.value=v===0?'CENTER':`${Math.round(Math.abs(v)*100)} ${v<0?'L':'R'}`;panInput.setAttribute('aria-valuetext',panValue.value);surface.style.setProperty('--angle',`${v*135}deg`);};updatePan();panInput.addEventListener('input',updatePan);
    let panStart=panInput.value;surface.addEventListener('pointerdown',()=>{panStart=panInput.value;});panInput.addEventListener('pointercancel',()=>{panInput.value=panStart;updatePan();});
    const options=document.createElement('details'),caption=document.createElement('summary'),actions=document.createElement('div');options.className='track-options';caption.textContent='Track options';actions.className='track-option-actions';
    for(const button of mix.querySelectorAll('.track-edit,.track-remove')){if(button.textContent==='Rack'){button.addEventListener('click',()=>{select('sound',{view:'rack'});$('sound-rack').scrollIntoView({behavior:'smooth',block:'center'});});button.textContent='Open rack';}actions.append(button);}
    options.append(caption,actions);document.querySelector('.instrument-caption').append(options);
  }
  let clipping=false,lastPaint=0,viewStart=0,viewDuration=1;
  $('clear-clip').addEventListener('click',()=>{clipping=false;paintClip();});
  function paintClip(){$('clear-clip').textContent=clipping?'Clipped · reset':'No clipping';$('clear-clip').setAttribute('aria-pressed',String(clipping));}
  return {
    focusInstrument(){document.body.classList.add('instrument-focus');showView('instrument');},
    sync(project,trackId,section,clip){
      $('selected-context').textContent=`${section.name} · ${(section.duration*project.tempo/240).toFixed(1)} bars · ${project.tempo} BPM${project.key?' · '+project.key:''}`;
      const track=project.tracks.find(t=>t.id===trackId);$('instrument-heading').textContent=track?.name||'Select an instrument';
      const mix=document.querySelector('.track.selected .track-mix');$('selected-mixer').replaceChildren();document.querySelector('.instrument-caption .track-options')?.remove();if(mix){dressMixer(mix);$('selected-mixer').append(mix);}
      document.body.classList.toggle('has-instrument',Boolean(track));
      const solos=project.tracks.filter(t=>t.solo);$('solo-status').hidden=!solos.length;$('clear-solos').hidden=!solos.length;
      $('solo-status').textContent=solos.length?`Solo active: ${solos.map(t=>t.name).join(', ')}`:'';
      $('trim-empty').hidden=Boolean(clip);if(clip)$('clip-inspector').open=true;
      viewStart=0;for(const item of project.sections){if(item.id===section.id)break;viewStart+=item.duration;}viewDuration=section.duration;
      for(const lane of document.querySelectorAll('.lane-content')){
        lane.querySelectorAll('.lane-playhead,.lane-empty').forEach(node=>node.remove());
        if(!lane.querySelector('.clip')){const empty=document.createElement('span');empty.className='lane-empty';empty.textContent='No audio in this section';lane.append(empty);}
        const head=document.createElement('i');head.className='lane-playhead';head.setAttribute('aria-hidden','true');lane.append(head);
      }
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
        const value=levels[index]??-Infinity;$(`meter-${name}`).parentElement.style.setProperty('--level',`${Math.max(0,Math.min(100,(value+60)/60*100))}%`);$(`meter-${name}`).value=Math.max(-60,Math.min(0,value));$(`peak-${name}`).value=Number.isFinite(value)?`${value.toFixed(1)} dBFS`:'−∞ dBFS';if(value>=0)clipping=true;
      }
      const rackReadout=$('rack-level-summary');if(rackReadout)rackReadout.textContent=`Master L ${Number.isFinite(levels[0])?levels[0].toFixed(1):'−∞'} / R ${Number.isFinite(levels[1])?levels[1].toFixed(1):'−∞'} dBFS`;
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
