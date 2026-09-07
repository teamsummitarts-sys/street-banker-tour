import {bindKnob} from './console.mjs';
import {RACK_DEFAULT,RACK_PRESETS,presetSettings,sameRack} from '../core/rack.mjs';

const controls=[['body','Body',-100,100,'Lean / Full'],['bite','Bite',-100,100,'Soft / Bright'],['dirt','Dirt',0,100,'Clean / Driven'],['space','Space',0,100,'Close / Room'],['outputDb','Output',-24,6,'Rack level · dB']];
const node=(tag,label,className)=>{const el=document.createElement(tag);el.textContent=label;if(className)el.className=className;return el;};
/** A preview never writes the project. Release/change commits one undo step. */
export function bindRackSlider(input,{read,allowed,preview,apply,display}){
  let original=null;
  const cancel=()=>{if(original){preview(original);display(original);original=null;}};
  input.addEventListener('input',()=>{
    if(!allowed()){cancel();return;}
    original??=read();const value={...original,[input.dataset.control]:Number(input.value)};preview(value);display(value);
  });
  input.addEventListener('change',()=>{
    if(!allowed()){cancel();return;}
    const start=original||read(),value={...start,[input.dataset.control]:Number(input.value)};original=null;
    if(!sameRack(start,value))apply(value);
  });
  input.addEventListener('pointercancel',cancel);
  input.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();cancel();}});
  return cancel;
}
export function renderRackPanel(root,{track,blocked,protectedNames,allowed,preview,apply,audition=false}){
  root.replaceChildren();const cancellations=[];
  const heading=node('div','','rack-heading');
  const title=node('div','');title.append(node('span',audition?'TAKE / SOUND RACK':'INSTRUMENT / SOUND RACK','rack-eyebrow'),node('h2',track?track.name:'Select an instrument layer'));
  heading.append(title);root.append(heading);
  const hasTrack=Boolean(track);
  blocked=blocked||!hasTrack;
  track=track||{name:'Select an instrument layer'};
  const settings=track.rack||RACK_DEFAULT;
  const action=(label,fn,pressed)=>{const b=node('button',label);b.type='button';b.disabled=blocked;b.dataset.rackAction='';if(pressed!==undefined)b.setAttribute('aria-pressed',String(pressed));b.addEventListener('click',()=>{if(allowed())fn();});return b;};
  const modes=node('div','','button-row');
  if(hasTrack&&!track.rack)modes.append(action('Assign rack',()=>apply({...RACK_DEFAULT})));
  else if(hasTrack)for(const [label,enabled]of [['Original',false],['Processed',true]])modes.append(action(label,()=>apply({...settings,enabled}),settings.enabled===enabled));
  heading.append(modes);
  root.append(node('p',!hasTrack?'Add an instrument, upload audio, or try the synth demo. Your rack is ready when you are.':protectedNames.length?`Unlock ${protectedNames.join(', ')} to change this rack. It affects this track throughout the song.`:audition?'Shape this alternate take while it plays. Accept it to keep these settings in a new version.':'Whole song · Processing follows this instrument into your WAV export.','hint'));
  const presets=node('div','','rack-presets');presets.setAttribute('aria-label','Sound presets');
  for(const p of RACK_PRESETS){const values=presetSettings(p);const b=action('',()=>apply(values),sameRack(track.rack,values));b.append(node('strong',p.name),node('span',p.detail));presets.append(b);}
  root.append(presets);
  const bank=node('div','','rack-controls');
  for(const [key,label,min,max,detail]of controls){
    const field=node('div','','rack-control'),top=node('span','','rack-control-label'),output=node('output','');top.append(node('strong',label),output);
    const input=document.createElement('input');input.type='range';input.min=min;input.max=max;input.step=1;input.value=settings[key];input.dataset.control=key;input.dataset.rackAssigned='';input.setAttribute('aria-label',`${label} rack control`);input.disabled=blocked||!track.rack||!settings.enabled;
    const dial=node('div','','rack-dial');dial.append(input);const face=node('i','','dial-face');face.setAttribute('aria-hidden','true');dial.append(face);bindKnob(dial,input,RACK_DEFAULT[key]);
    const display=value=>{input.value=value[key];output.value=`${value[key]>0&&min<0?'+':''}${value[key]}${key==='outputDb'?' dB':key==='dirt'||key==='space'?'%':''}`;input.setAttribute('aria-valuetext',output.value);dial.style.setProperty('--angle',`${(value[key]-min)/(max-min)*270-135}deg`);};display(settings);
    cancellations.push(bindRackSlider(input,{read:()=>({...settings}),allowed:()=>allowed()&&Boolean(track.rack)&&settings.enabled,preview,apply,display}));
    const reset=action('Reset',()=>apply({...settings,[key]:RACK_DEFAULT[key]}));reset.setAttribute('aria-label',`Reset ${label}`);reset.dataset.rackAssigned='';reset.disabled=input.disabled;
    field.append(top,dial,node('span',detail,'hint'),reset);bank.append(field);
  }
  const meter=node('output','Master L −∞ / R −∞ dBFS','rack-level-summary');meter.id='rack-level-summary';root.append(meter);
  root.append(bank,node('p',track.rack&&!settings.enabled?'Original selected. Select Processed to hear and adjust your rack.':'Drag a knob up or down. Double-tap to reset, or use its Reset button. No generation credits.','rack-footnote'));
  return ()=>cancellations.forEach(cancel=>cancel());
}
