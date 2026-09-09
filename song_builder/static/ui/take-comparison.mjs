import {AudioEngine} from '../core/audio.mjs';
import {validateProject,sectionStart,newId} from '../core/project.mjs';
export function candidateForTake(project,take){
 if(!project.sections.some(s=>s.id===take.sectionId)||!project.tracks.some(t=>t.id===take.trackId))throw Error('This take references a removed instrument or section.');
 return validateProject({...project,clips:[...project.clips.filter(c=>c.sectionId!==take.sectionId||c.trackId!==take.trackId),...take.clips.map(c=>({...c,id:newId()}))]});
}
export function createTakeComparison({document,base,message}){
 const engine=new AudioEngine();const retained=new Set();let active=null,request=0;
 const el=(tag,value)=>{const n=document.createElement(tag);if(value)n.textContent=value;return n;};
 function stop(){request++;engine.stop();if(active)active.label.textContent='Stopped · arrangement unchanged';}
 async function open(project,take,container){
  stop();const generation=request,candidate=candidateForTake(project,take),section=project.sections.find(s=>s.id===take.sectionId),start=sectionStart(project,section.id);
  const ids=new Set([...project.clips,...candidate.clips].map(c=>c.assetId));
  for(const id of retained)if(!ids.has(id)){engine.remove(id);retained.delete(id);}
  for(const id of ids){if(engine.has(id))continue;const response=await fetch(`${base}/api/assets/${id}/audio`,{credentials:'same-origin',cache:'no-store'});if(!response.ok||response.redirected)throw Error('A saved take’s audio could not load. Reopen this project.');const raw=await response.arrayBuffer();if(raw.byteLength>40*1024*1024)throw Error('This take’s source is too large for comparison.');await engine.decode(id,raw);retained.add(id);}
  if(generation!==request)return;
  const panel=el('section');panel.className='take-comparison';panel.append(el('h3',`${section.name} · ${take.name}`),el('p','Compare the current lane with this saved take over the same backing. Playback does not alter the arrangement.'));
  const scrub=el('input');scrub.type='range';scrub.min=0;scrub.max=section.duration;scrub.step=.01;scrub.value=0;scrub.setAttribute('aria-label','Take comparison position within section');
  const label=el('p','Ready · arrangement unchanged');let selected='A';active={label};
  const draw=(p,title,color)=>{panel.append(el('strong',title));const canvas=el('canvas');canvas.width=800;canvas.height=76;canvas.setAttribute('aria-label',title+' waveform');const ctx=canvas.getContext('2d');ctx.fillStyle=color;
   for(const c of p.clips.filter(c=>c.sectionId===section.id&&c.trackId===take.trackId)){const buffer=engine.buffer(c.assetId),data=buffer.getChannelData(0);for(let x=0;x<800;x++){const time=x/800*section.duration;if(time<c.offset||time>=c.offset+c.duration)continue;const at=c.sourceOffset+(c.loop?(time-c.offset)%(buffer.duration-c.sourceOffset):(time-c.offset)),index=Math.floor(at*buffer.sampleRate);let peak=0;for(let n=0;n<Math.max(1,buffer.sampleRate*section.duration/800);n+=8)peak=Math.max(peak,Math.abs(data[index+n]||0));const h=Math.max(1,Math.min(72,peak*72));ctx.fillRect(x,38-h/2,1,h);}}panel.append(canvas);};
  draw(project,'A · Current instrument','#a9c5b0');draw(candidate,'B · Saved take','#d9b66c');
  async function play(which){engine.stop();selected=which;const generation=++request;const p=which==='A'?project:candidate;await engine.play(p,{from:start+Number(scrub.value),to:start+section.duration,onEnded:()=>{if(generation===request)label.textContent=which+' · ended';}});label.textContent=`${which} · ${Number(scrub.value).toFixed(2)}s into ${section.name}`;}
  const controls=el('div');controls.className='actions';
  for(const [name,which]of [['Play A · current','A'],['Play B · take','B']]){const b=el('button',name);b.type='button';b.onclick=()=>play(which).catch(e=>message(e.message,true));controls.append(b);}
  const halt=el('button','Stop comparison');halt.type='button';halt.onclick=stop;controls.append(halt);
  scrub.onchange=()=>{if(engine.isPlaying())play(selected).catch(e=>message(e.message,true));else label.textContent=`${Number(scrub.value).toFixed(2)}s into ${section.name}`;};
  panel.append(scrub,controls,label);container.replaceChildren(panel);panel.scrollIntoView?.({behavior:'auto',block:'nearest'});
 }
 window.addEventListener('pagehide',()=>engine.dispose());
 return {open,stop};
}
