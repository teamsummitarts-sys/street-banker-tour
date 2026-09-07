import {bindConsole} from './console.mjs';
import * as P from '../core/project.mjs';
import { AudioEngine, createDemoAudio } from '../core/audio.mjs';
import { readBundle, writeBundle } from './portable.mjs';
import { PendingRequests } from './requests.mjs';
import { bindFadeHandle, effectiveFades } from './fade-handles.mjs';
import { renderRackPanel } from './rack-panel.mjs';
import { RACK_DEFAULT, sameRack } from '../core/rack.mjs';

const $ = id => document.getElementById(id);
const base = document.querySelector('meta[name="song-builder-base"]').content.replace(/\/$/, '');
const csrf = document.querySelector('meta[name="song-builder-csrf"]').content;
const engine = new AudioEngine();
const studio = bindConsole(document);
const pendingRequests = new PendingRequests(sessionStorage, `${base}:${csrf}`);
const state = { project:null, revision:0, sectionId:null, trackId:null, clipId:null,
  assets:new Map(), jobs:[], capabilities:null, dirty:false, sequence:0, busy:0,
  playing:false, sectionOnly:false, loopSection:false, playRequest:0, previewEnd:null, saveChain:Promise.resolve(), conflict:false,
  recorder:null, recordingStream:null, recordTimer:null, recordProject:null,
  preparedUrl:null, polling:null, saveTimer:null, history:[], future:[], rejectedJobs:new Set(), audition:null, auditionRacks:new Map() };

class ApiError extends Error { constructor(message,status) { super(message); this.status=status; } }
async function api(path, {method='GET',body,signal}={}) {
  const headers = {Accept:'application/json'};
  if(method!=='GET') headers['X-Song-Builder-CSRF']=csrf;
  if(body && !(body instanceof FormData)) { headers['Content-Type']='application/json'; body=JSON.stringify(body); }
  const response=await fetch(base+path,{method,headers,body,signal,credentials:'same-origin',cache:'no-store'});
  if(response.redirected || !(response.headers.get('Content-Type')||'').includes('application/json'))
    throw new ApiError('Your session expired. Keep this page open and sign in again in another tab, then save.',401);
  const value=await response.json();
  if(!response.ok) throw new ApiError(value.message || value.error || 'That action could not finish. Your current song is still here.',response.status);
  return value;
}
function notify(message,error=false) { const n=$('notice'); n.textContent=message; n.hidden=false; n.setAttribute('role',error?'alert':'status'); }
function failure(error) { notify(error.message || 'That action could not finish. Your current song is still here.',true); }
function seconds(value) { const s=Math.max(0,Math.floor(value||0));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`; }
function selectedSection() { return state.project?.sections.find(s=>s.id===state.sectionId); }
function selectedClip() { return state.project?.clips.find(c=>c.id===state.clipId); }
function text(tag,value,className) { const node=document.createElement(tag);node.textContent=value;if(className)node.className=className;return node; }
function button(label,handler,options={}) { const node=text('button',label,options.className);node.type='button';node.disabled=Boolean(options.disabled);if(options.pressed!==undefined)node.setAttribute('aria-pressed',String(options.pressed));node.addEventListener('click',()=>run(handler));return node; }
async function run(action) { if(state.busy)return; state.busy++;renderDisabled();try { await action(); } catch(e) {failure(e);}finally {state.busy--;renderDisabled();} }
function stop(except=null) { for(const audio of $('jobs').querySelectorAll('audio'))if(audio!==except)audio.pause();engine.stop();state.playRequest++;state.playing=false;state.previewEnd=null;$('play-song').setAttribute('aria-pressed','false'); if(state.audition){state.audition=null;$('seek').value=0;document.body.classList.remove('auditioning');$('selected-mixer').hidden=false;renderRack();$('instrument-heading').textContent=state.project.tracks.find(t=>t.id===state.trackId)?.name||'Select an instrument';} }
function markDirty() { state.dirty=true;state.sequence++;$('save-state').textContent='Unsaved changes';clearTimeout(state.saveTimer);state.saveTimer=setTimeout(()=>save().catch(failure),800); }
function commit(project,{redraw=true,history=true,resume=false,rackTrackId=null}={}) {
  const wasPlaying=(resume||rackTrackId)&&state.playing,from=engine.position(),sectionOnly=state.sectionOnly;
  const next=P.validateProject(project);
  const track=rackTrackId&&next.tracks.find(t=>t.id===rackTrackId);
  const inaudible=track&&(track.muted||(next.tracks.some(t=>t.solo)&&!track.solo));
  const keepAudio=track&&(engine.updateRack(track.id,track.rack)||inaudible);
  if(!keepAudio)stop();
  if(history&&state.project){state.history.push(state.project);if(state.history.length>30)state.history.shift();state.future=[];}
  state.project=next;
  if(!next.sections.some(s=>s.id===state.sectionId))state.sectionId=next.sections[0].id;
  if(!next.tracks.some(t=>t.id===state.trackId))state.trackId=next.tracks[0]?.id??null;
  if(!next.clips.some(c=>c.id===state.clipId))state.clipId=null;
  markDirty();if(redraw)render();else renderMeta();
  if(wasPlaying&&!keepAudio)play(from,{sectionOnly}).catch(failure);
}
function restoreEdit(direction){
  const source=direction==='undo'?state.history:state.future,target=direction==='undo'?state.future:state.history;
  if(!source.length)return;target.push(state.project);commit(source.pop(),{history:false});
}
async function listProjects(){const r=await api('/api/projects');const list=$('project-list');list.replaceChildren(new Option('Choose a project',''));for(const p of r.projects)list.add(new Option(p.title,p.id));list.value=state.revision?state.project.id:'';}
function showConflict(){state.conflict=true;$('recovery').hidden=false;$('recovery-message').textContent='This project changed in another session. Your edits are still here. Save a separate copy, or load the latest saved version.';}
async function performSave() {
  if(!state.project||!state.dirty)return;
  if(state.conflict)throw new Error('Resolve the saved-project conflict before saving this version.');
  const snapshot=P.validateProject(state.project),sequence=state.sequence,revision=state.revision;
  $('save-state').textContent='Saving…';
  try {
    const r=revision ? await api(`/api/projects/${snapshot.id}`,{method:'PUT',body:{project:snapshot,expectedRevision:revision}}) : await api('/api/projects',{method:'POST',body:{project:snapshot}});
    if(state.project.id!==snapshot.id)return;
    state.revision=r.revision;
    if(state.sequence===sequence)state.dirty=false;
    $('save-state').textContent=state.dirty?'Unsaved changes':'Saved';
    history.replaceState(null,'',`${location.pathname}?project=${snapshot.id}`);
    await listProjects().catch(()=>notify('Song saved. The project list could not refresh; your changes are stored.',true));
  } catch(e) { $('save-state').textContent='Not saved';if(e.status===409)showConflict();throw e; }
}
function save(){clearTimeout(state.saveTimer);const task=state.saveChain.catch(()=>{}).then(performSave);state.saveChain=task;return task;}
async function audioBytes(asset){
  const url=new URL(asset.url,location.href);
  if(url.origin!==location.origin || !url.pathname.startsWith(base+'/api/assets/'))throw new Error('This audio link is not part of The Room.');
  const r=await fetch(url,{credentials:'same-origin',cache:'no-store'});
  if(!r.ok||r.redirected)throw new Error('Audio could not load. Sign in again and reopen this project.');
  const length=Number(r.headers.get('Content-Length'));if(length>40*1024*1024)throw new Error('This audio is too large for this editor.');
  const bytes=await r.arrayBuffer();if(bytes.byteLength>40*1024*1024)throw new Error('This audio is too large for this editor.');return bytes;
}
async function ensureAudio(asset){if(!engine.has(asset.id))await engine.decode(asset.id,await audioBytes(asset));return engine.buffer(asset.id);}
function releaseProjectAudio(keep=[]){const retained=new Set(keep);for(const id of state.assets.keys())if(!retained.has(id))engine.remove(id);}
async function loadProject(id,{skipSave=false}={}) {
  if(!skipSave)await save();
  const r=await api(`/api/projects/${id}`),project=P.validateProject(r.project);
  stop();releaseProjectAudio(r.assets.map(a=>a.id));
  stop();state.project=project;state.revision=r.revision;state.assets=new Map(r.assets.map(a=>[a.id,a]));state.sectionId=project.sections[0].id;state.trackId=project.tracks[0]?.id??null;state.clipId=null;state.dirty=false;state.conflict=false;state.history=[];state.future=[];state.jobs=[];state.rejectedJobs=new Set();
  $('recovery').hidden=true;$('save-state').textContent='Loading audio…';render();
  history.replaceState(null,'',`${location.pathname}?project=${project.id}`);
  let failed=0;for(const a of r.assets){try{await ensureAudio(a);}catch{failed++;}}
  $('save-state').textContent=failed?'Some audio unavailable':'Saved';
  if(failed)notify('Some audio could not load. Your arrangement is saved. Reopen the project to retry before playing or exporting.',true);
  await pollJobs();render();
}
async function startNew(title='Untitled song'){await save();stop();releaseProjectAudio();state.project=P.newProject(title);state.revision=0;state.sectionId=state.project.sections[0].id;state.trackId=null;state.clipId=null;state.assets=new Map();state.jobs=[];state.history=[];state.future=[];state.rejectedJobs=new Set();state.conflict=false;$('recovery').hidden=true;markDirty();render();await save();}
async function saveVersion(){
  await save();const suggested=`${state.project.title} — Version 2`,name=prompt('Name this version',suggested);if(name===null)return;if(!name.trim())throw new Error('Give this version a name.');
  stop();state.project=P.validateProject({...state.project,id:P.newId(),title:name.trim().slice(0,120)});state.revision=0;state.jobs=[];state.history=[];state.future=[];state.conflict=false;markDirty();render();await save();notify(`Saved ${state.project.title} as an independent version. The original is unchanged.`);
}

function renderMeta(){if(!state.project)return;$('duration-label').textContent=`${seconds(P.projectDuration(state.project))} arranged`;$('seek').max=P.projectDuration(state.project);}
function render(){if(!state.project)return;renderMeta();$('song-title').value=state.project.title;$('song-tempo').value=state.project.tempo;$('song-key').value=state.project.key;renderSections();renderTracks();renderInspector();renderJobs();renderDisabled();}
function renderSections(){
  const list=$('sections');list.replaceChildren();state.project.sections.forEach((s,i)=>{
    const li=document.createElement('li'),b=button('',()=>{if(state.audition||(state.playing&&state.sectionOnly))stop();state.sectionId=s.id;state.clipId=null;render();},{pressed:s.id===state.sectionId,className:'section-button'});
    li.style.setProperty('--section-width',`${Math.max(110,Math.min(320,s.duration*9))}px`);
    b.append(text('span',`${String(i+1).padStart(2,'0')} · ${seconds(P.sectionStart(state.project,s.id))}`,'section-number'),text('strong',s.name),text('span',`${s.duration}s${s.locked?' · Protected':''}`));li.append(b);list.append(li);
  });
}
function snapDelta(value){const mode=$('snap-grid').value;if(mode==='free')return Math.round(value*100)/100;const beat=60/state.project.tempo,unit=mode==='bar'?beat*4:beat;return Math.round(value/unit)*unit;}
function bindTrimHandle(handle,clip,edge,clipNode,section){
  handle.addEventListener('pointerdown',event=>{
    if(selectedSection().locked)return;event.preventDefault();event.stopPropagation();handle.setPointerCapture(event.pointerId);
    const startX=event.clientX,start={...clip},laneWidth=clipNode.parentElement.getBoundingClientRect().width;let candidate=start;
    const move=e=>{const raw=(e.clientX-startX)/laneWidth*section.duration,delta=snapDelta(raw),audio=engine.buffer(start.assetId);
      if(edge==='start'){const applied=Math.max(-Math.min(start.offset,start.sourceOffset),Math.min(start.duration-.1,delta));candidate={...start,offset:start.offset+applied,sourceOffset:start.sourceOffset+applied,duration:start.duration-applied};}
      else{const maximum=Math.min(section.duration-start.offset,start.loop?section.duration-start.offset:audio.duration-start.sourceOffset);candidate={...start,duration:Math.max(.1,Math.min(maximum,start.duration+delta))};}
      clipNode.style.left=`${candidate.offset/section.duration*100}%`;clipNode.style.width=`${candidate.duration/section.duration*100}%`;};
    const finish=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',finish);handle.removeEventListener('pointercancel',cancel);if(candidate.offset!==start.offset||candidate.duration!==start.duration){state.clipId=start.id;commit(P.updateClip(state.project,start.id,{offset:candidate.offset,sourceOffset:candidate.sourceOffset,duration:candidate.duration}));}};
    const cancel=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',finish);handle.removeEventListener('pointercancel',cancel);renderTracks();};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',cancel);
  });
}
function bindClipMove(surface,clip,clipNode,section){
  surface.addEventListener('pointerdown',event=>{
    if(selectedSection().locked)return;event.preventDefault();event.stopPropagation();surface.setPointerCapture(event.pointerId);
    const startX=event.clientX,start=clip.offset,laneWidth=clipNode.parentElement.getBoundingClientRect().width;let offset=start,moved=false;
    const move=e=>{const delta=snapDelta((e.clientX-startX)/laneWidth*section.duration);offset=Math.max(0,Math.min(section.duration-clip.duration,start+delta));moved=moved||Math.abs(e.clientX-startX)>5;clipNode.style.left=`${offset/section.duration*100}%`;};
    const clean=()=>{surface.removeEventListener('pointermove',move);surface.removeEventListener('pointerup',finish);surface.removeEventListener('pointercancel',cancel);};
    const finish=()=>{clean();state.clipId=clip.id;state.trackId=clip.trackId;if(moved&&offset!==start)commit(P.updateClip(state.project,clip.id,{offset}));else{renderTracks();renderInspector();}};
    const cancel=()=>{clean();renderTracks();};surface.addEventListener('pointermove',move);surface.addEventListener('pointerup',finish);surface.addEventListener('pointercancel',cancel);
  });
}
function renderTracks(){
  const tracks=$('tracks');tracks.replaceChildren();const section=selectedSection();$('selected-context').textContent=`Layers in ${section.name} · ${section.duration} seconds`;
  for(const track of state.project.tracks){
    const row=document.createElement('div');row.className='track'+(track.id===state.trackId?' selected':'');row.dataset.trackId=track.id;const ink=['#a7b59a','#dcac59','#8daec8','#d9cbbc'][state.project.tracks.indexOf(track)%4];row.style.setProperty('--track-ink',ink);
    const controls=document.createElement('div');controls.className='track-controls';const title=document.createElement('div');title.className='track-title';
    title.append(button(track.name,()=>{if(state.audition)stop();state.trackId=track.id;studio.focusInstrument();renderTracks();renderDisabled();},{className:'track-name',pressed:track.id===state.trackId}),
      button('M',()=>commit(P.updateTrack(state.project,track.id,{muted:!track.muted}),{resume:true}),{className:'track-switch',pressed:track.muted}),
      button('S',()=>commit(P.updateTrack(state.project,track.id,{solo:!track.solo}),{resume:true}),{className:'track-switch',pressed:track.solo}));
    title.children[1].setAttribute('aria-label',`Mute ${track.name}`);title.children[2].setAttribute('aria-label',`Solo ${track.name}`);
    const mix=document.createElement('div');mix.className='track-mix';
    for(const [key,label,min,max,step]of[['gainDb','Level',-60,6,1],['pan','Pan',-1,1,.05]]){
      const field=document.createElement('label');field.textContent=`${label} ${key==='gainDb'?track[key]+' dB':track[key]===0?'C':track[key]<0?'L':'R'}`;
      const input=document.createElement('input');input.type='range';input.min=min;input.max=max;input.step=step;input.value=track[key];input.setAttribute('aria-label',`${label} for ${track.name}`);input.addEventListener('change',()=>{try{const value=Number(input.value);const centered=key==='pan'&&Math.abs(value)<=.100001?0:value;if(centered===track[key])return;commit(P.updateTrack(state.project,track.id,{[key]:centered}),{resume:true});}catch(e){failure(e);}});field.append(input);mix.append(field);
    }
    const center=button('Center',()=>commit(P.updateTrack(state.project,track.id,{pan:0}),{resume:true}),{className:'pan-center',disabled:track.pan===0});
    center.setAttribute('aria-label',`Center pan for ${track.name}`);const rename=button('Rename',()=>{const name=prompt('Track name',track.name);if(name!==null&&name.trim())commit(P.updateTrack(state.project,track.id,{name:name.trim().slice(0,60)}));},{className:'track-edit'}),remove=button('Remove',()=>{if(confirm(`Remove ${track.name} and its clips from this song?`))commit(P.removeTrack(state.project,track.id));},{className:'track-remove'});mix.append(center,rename,remove);
    mix.append(button('Rack',()=>{if(state.audition)stop();state.trackId=track.id;renderTracks();renderDisabled();$('sound-rack').scrollIntoView({behavior:'smooth',block:'center'});},{className:'track-edit'}));
    controls.append(title,mix);const lane=document.createElement('div');lane.className='lane';const content=document.createElement('div');content.className='lane-content';
    for(const clip of state.project.clips.filter(c=>c.trackId===track.id&&c.sectionId===section.id)){
      const asset=state.assets.get(clip.assetId);const c=button('',()=>{if(state.audition)stop();state.clipId=clip.id;state.trackId=clip.trackId;studio.focusInstrument();renderTracks();renderInspector();},{className:'clip'+(state.clipId===clip.id?' selected':'')});
      c.style.left=`${clip.offset/section.duration*100}%`;c.style.width=`${clip.duration/section.duration*100}%`;c.setAttribute('aria-label',`${asset?.name||'Audio clip'}, ${clip.duration.toFixed(1)} seconds on ${track.name}`);
      const left=text('i','','trim-handle trim-left'),right=text('i','','trim-handle trim-right');left.setAttribute('aria-label','Trim clip start');right.setAttribute('aria-label','Trim clip end');
      c.append(left,text('span',asset?.name||'Audio clip'));const canvas=document.createElement('canvas');canvas.width=900;canvas.height=96;canvas.setAttribute('aria-label','Drag clip along section');c.append(canvas,right);bindTrimHandle(left,clip,'start',c,section);bindTrimHandle(right,clip,'end',c,section);bindClipMove(canvas,clip,c,section);
      if(engine.has(clip.assetId)){const peaks=engine.waveform(clip.assetId,450),ctx=canvas.getContext('2d');ctx.strokeStyle=state.clipId===clip.id?'#f2c57a':ink;ctx.lineWidth=1.5;ctx.beginPath();for(let i=0;i<peaks.length;i++){const x=i/peaks.length*900,v=Math.max(1,peaks[i]*44);ctx.moveTo(x,48-v);ctx.lineTo(x,48+v);}ctx.stroke();}
      const incoming=text('i','','fade-region fade-region-in'),outgoing=text('i','','fade-region fade-region-out');
      const showFades=values=>{incoming.style.width=`${values.fadeIn/clip.duration*100}%`;outgoing.style.width=`${values.fadeOut/clip.duration*100}%`;};
      showFades(effectiveFades(clip));c.append(incoming,outgoing);
      if(state.clipId===clip.id&&!section.locked){
        const projectId=state.project.id,sequence=state.sequence;
        for(const [key,label]of [['fadeIn','IN'],['fadeOut','OUT']]){
          const handle=text('i',label,`fade-handle ${key==='fadeIn'?'fade-handle-in':'fade-handle-out'}`);handle.title=`Drag inward to adjust ${key==='fadeIn'?'fade in':'fade out'}`;
          bindFadeHandle(handle,clip,key,{width:()=>c.getBoundingClientRect().width,
            allowed:()=>!state.busy&&!state.recorder&&state.project.id===projectId&&state.sequence===sequence&&!selectedSection()?.locked,
            preview:showFades,restore:()=>showFades(effectiveFades(clip)),
            apply:patch=>{try{commit(P.updateClip(state.project,clip.id,patch));}catch(error){failure(error);renderTracks();}}});
          c.append(handle);
        }
      }
      content.append(c);
    }
    lane.append(content);row.append(controls,lane);tracks.append(row);
  }
  $('audio-empty').hidden=state.project.clips.length>0;
  renderRack();
  studio.sync(state.project,state.trackId,section,selectedClip());
}

let cancelRackGesture=()=>{};
function rackProtectedSections(trackId){return state.project?.sections.filter(s=>s.locked&&state.project.clips.some(c=>c.sectionId===s.id&&c.trackId===trackId)).map(s=>s.name)||[];}
function renderRack(){
  cancelRackGesture();
  const audition=state.audition;
  const track=audition?.project.tracks[0]||state.project?.tracks.find(t=>t.id===state.trackId),projectId=state.project?.id,sequence=state.sequence;
  const protectedNames=audition?[]:rackProtectedSections(track?.id);
  const allowed=()=>Boolean(track)&&!state.busy&&!state.recorder&&state.project?.id===projectId&&state.sequence===sequence&&state.audition===audition&&!rackProtectedSections(track.id).length;
  cancelRackGesture=renderRackPanel($('sound-rack'),{track,protectedNames,audition:Boolean(audition),blocked:state.busy>0||Boolean(state.recorder)||protectedNames.length>0,
    allowed,preview:settings=>{if(state.project?.id===projectId)engine.updateRack(track.id,settings);},
    apply:settings=>{try{
      if(!allowed())return;
      if(audition){audition.project=P.updateTrack(audition.project,track.id,{rack:settings});state.auditionRacks.set(audition.key,{...settings});engine.updateRack(track.id,settings);renderRack();renderDisabled();return;}
      const next=P.updateTrack(state.project,track.id,{rack:settings});
      if(sameRack(track.rack||RACK_DEFAULT,settings))return;
      commit(next,{rackTrackId:track.id});
    }catch(error){failure(error);renderRack();}}
  });
  if(audition){const actions=text('div','','audition-actions');actions.append(text('span','TAKE AUDITION · Not yet accepted','audition-label'),button('Replay take',()=>auditionTake(audition.job)),button('Accept into new version',()=>acceptTake(audition.job),{disabled:selectedSection()?.locked}),button('Back to takes',()=>{stop();$('panel-takes').scrollIntoView({behavior:'auto',block:'start'});}));$('sound-rack').prepend(actions);}
}
function renderInspector(){const s=selectedSection();if(!s)return;$('section-heading').textContent=s.name;$('section-name').value=s.name;$('section-duration').value=s.duration;$('section-direction').value=s.direction;$('section-lyrics').value=s.lyrics;$('lock-section').textContent=s.locked?'Protected':'Protect';$('lock-section').setAttribute('aria-pressed',String(s.locked));$('lock-hint').textContent=s.locked?'These parts are protected. Unlock before changing their audio, lyrics or length.':'Protect this section when you want to keep its parts.';
  const protectedCount=state.project.sections.filter(section=>section.id!==s.id&&section.locked).length;
  $('section-test-status').textContent=protectedCount===state.project.sections.length-1&&!s.locked?`${s.name} is editable. All ${protectedCount} other section${protectedCount===1?' is':'s are'} protected.`:'The selected section stays editable. Every other section is protected.';
  const clip=selectedClip();$('clip-inspector').hidden=!clip;if(clip){$('clip-offset').value=clip.offset;$('clip-source').value=clip.sourceOffset;$('clip-duration').value=clip.duration;$('clip-loop').checked=clip.loop;$('clip-fade-in').value=clip.fadeIn||0;$('clip-fade-out').value=clip.fadeOut||0;}
}
function renderDisabled(){const s=selectedSection(),busy=state.busy>0,lock=Boolean(s?.locked),hasAudio=Boolean(state.project?.clips.length),recording=Boolean(state.recorder);
  const rackTrack=state.audition?.project.tracks[0]||state.project?.tracks.find(t=>t.id===state.trackId),rackBlocked=!rackTrack||busy||recording||(!state.audition&&rackProtectedSections(state.trackId).length>0);
  for(const input of $('sound-rack').querySelectorAll('button,input'))input.disabled=Boolean(rackBlocked||(input.hasAttribute('data-rack-assigned')&&rackTrack?.rack?.enabled===false));
  $('loop-section').disabled=busy||recording||!hasAudio;$('clear-solos').disabled=busy||recording;
  for(const input of document.querySelectorAll('#selected-mixer input,#selected-mixer button,.instrument-caption button'))input.disabled=busy||recording||Boolean(state.audition)||(input.classList.contains('pan-center')&&rackTrack?.pan===0);
  for(const id of ['save-project','new-project','save-version','import-project','export-project','project-list','start-ai','load-demo','export-mix','export-section','export-track','export-30','export-15','play-song','play-section','add-section','add-track','prepare-section-test'])$(id).disabled=busy||recording;
  for(const id of ['section-name','section-duration','section-direction','section-lyrics','duplicate-section','remove-section','upload-audio','apply-clip','remove-clip','duplicate-clip','split-clip','clip-offset','clip-source','clip-duration','clip-loop','clip-fade-in','clip-fade-out','crossfade-clip'])$(id).disabled=busy||lock||recording;
  for(const id of ['song-title','song-tempo','song-key','lock-section','move-earlier','move-later'])$(id).disabled=busy||recording;
  $('record-audio').disabled=busy||lock||!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder;
  $('record-audio').textContent=recording?'Stop recording':'Record a part';
  const configured=state.capabilities?.generation?.configured;
  $('generate-take').disabled=busy||lock||!configured||recording;
  $('separate-stems').disabled=busy||lock||!state.capabilities?.generation?.separationConfigured||!selectedClip()||recording;
  if(!hasAudio)for(const id of ['play-song','play-section','export-mix','export-section','export-track','export-30','export-15'])$(id).disabled=true;
  const i=state.project?.sections.findIndex(s=>s.id===state.sectionId);$('move-earlier').disabled=busy||recording||i===0;$('move-later').disabled=busy||recording||i===state.project?.sections.length-1;
  if(state.project?.sections.length===1)$('remove-section').disabled=true;
  $('undo-edit').disabled=busy||recording||!state.history.length;$('redo-edit').disabled=busy||recording||!state.future.length;
}
function quickTrim(action){const c=selectedClip();if(!c)return;const audio=engine.buffer(c.assetId),step=.5;let patch={};
  if(action==='trim-start'){const amount=Math.min(step,c.duration-.1);patch={sourceOffset:c.sourceOffset+amount,offset:c.offset+amount,duration:c.duration-amount};}
  if(action==='extend-start'){const amount=Math.min(step,c.sourceOffset,c.offset);patch={sourceOffset:c.sourceOffset-amount,offset:c.offset-amount,duration:c.duration+amount};}
  if(action==='trim-end')patch={duration:Math.max(.1,c.duration-step)};
  if(action==='extend-end'){const room=selectedSection().duration-c.offset-c.duration,sourceRoom=c.loop?room:audio.duration-c.sourceOffset-c.duration;patch={duration:c.duration+Math.max(0,Math.min(step,room,sourceRoom))};}
  if(!Object.keys(patch).length||Object.entries(patch).every(([k,v])=>v===c[k]))throw new Error('There is no more audio or section space in that direction.');commit(P.updateClip(state.project,c.id,patch));}
function duplicateClip(){const c=selectedClip();if(!c)return;const section=selectedSection(),offset=Math.min(section.duration-c.duration,c.offset+c.duration);const p=P.addClip(state.project,{...c,id:P.newId(),offset});state.clipId=p.clips.at(-1).id;commit(p);}
function splitClip(){const c=selectedClip();if(!c)return;if(c.duration<.2)throw new Error('This clip is too short to split.');const first=Math.round(c.duration/2*1000)/1000,second=c.duration-first;let p=P.updateClip(state.project,c.id,{duration:first});p=P.addClip(p,{...c,id:P.newId(),offset:c.offset+first,sourceOffset:c.loop?c.sourceOffset:(c.sourceOffset+first),duration:second});state.clipId=p.clips.at(-1).id;commit(p);}
async function play(from=0,{sectionOnly=false}={}){
  stop();if(!state.project.clips.length)return;
  const request=state.playRequest,section=selectedSection(),start=P.sectionStart(state.project,section.id),end=start+section.duration;
  const loop=sectionOnly&&state.loopSection;
  if(loop||sectionOnly&&(from<start||from>=end))from=start;
  state.sectionOnly=sectionOnly;
  // Ready neutral racks belong only to the playback graph. Selecting a track or
  // cancelling a first adjustment must never add settings to its saved project.
  const playback={...state.project,tracks:state.project.tracks.map(track=>track.rack?track:{...track,rack:{...RACK_DEFAULT}})};
  await engine.play(playback,{from,to:sectionOnly?end:undefined,loop,onEnded:()=>{if(request!==state.playRequest)return;state.playing=false;$('seek').value=engine.position();$('play-song').setAttribute('aria-pressed','false');}});
  if(request!==state.playRequest)return;
  state.playing=engine.isPlaying();$('play-song').setAttribute('aria-pressed',String(state.playing));
}
function clock(time=0){
  if(state.project){const position=state.playing||state.audition?engine.position():Number($('seek').value);if(state.playing)$('seek').value=position;$('play-time').textContent=`${seconds(position)} / ${seconds(P.projectDuration(state.audition?.project||state.project))}${state.audition?' · TAKE':''}`;studio.playhead(state.audition?-1:position);studio.meter(engine.meterLevels(),time);}
  requestAnimationFrame(clock);
}
async function uploadWav(bytes,name){const form=new FormData();form.append('file',new Blob([bytes],{type:'audio/wav'}),name.replace(/\.[^.]*$/,'')+'.wav');const r=await api('/api/assets',{method:'POST',body:form});state.assets.set(r.asset.id,r.asset);await engine.decode(r.asset.id,bytes);return r.asset;}
async function importAudio(file,{sectionId=state.sectionId,trackId=state.trackId}={}){
  if(!file)return;if(file.size>32*1024*1024)throw new Error('Choose an audio file smaller than 32 MB.');
  if(state.project.sections.find(s=>s.id===sectionId)?.locked)throw new Error('Unlock this section before adding audio.');
  const temporary=P.newId();try{await engine.decode(temporary,await file.arrayBuffer());const bytes=engine.normalizedWav(temporary);engine.remove(temporary);const asset=await uploadWav(bytes,file.name);let p=state.project;if(!p.tracks.some(t=>t.id===trackId)){p=P.addTrack(p,file.name.replace(/\.[^.]*$/,'').slice(0,60)||'Audio');trackId=p.tracks.at(-1).id;}
    const section=p.sections.find(s=>s.id===sectionId),duration=Math.min(section.duration,engine.buffer(asset.id).duration);p=P.addClip(p,{trackId,sectionId,assetId:asset.id,offset:0,sourceOffset:0,duration,loop:false,gainDb:0});state.trackId=trackId;state.clipId=p.clips.at(-1).id;commit(p);await save();notify(`Added ${file.name}. Its original timing and pitch are preserved.`);
  }finally{engine.remove(temporary);}
}
async function loadDemo(){await startNew('After hours — synth demo');let p=state.project;for(const s of p.sections)p=P.updateSection(p,s.id,{duration:8});const demos=createDemoAudio();
  for(const d of demos){const a=await uploadWav(d.buffer,d.name);p=P.addTrack(p,d.name);const trackId=p.tracks.at(-1).id;for(const s of p.sections)p=P.addClip(p,{trackId,sectionId:s.id,assetId:a.id,offset:0,sourceOffset:0,duration:8,loop:true,gainDb:0});}
  commit(p);await save();notify('Original synth demo loaded. Select a section, mute a layer, or protect the chorus. This demo used no AI credits.');
}
async function toggleRecord(){if(state.recorder){state.recorder.stop();return;}if(selectedSection().locked)throw new Error('Unlock this section before recording.');
  stop();const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false}});const chunks=[];let bytes=0;const recorder=new MediaRecorder(stream);state.recorder=recorder;state.recordingStream=stream;state.recordProject={projectId:state.project.id,sectionId:state.sectionId,trackId:state.trackId};
  recorder.addEventListener('dataavailable',e=>{if(e.data.size){chunks.push(e.data);bytes+=e.data.size;}if(bytes>24*1024*1024&&recorder.state!=='inactive')recorder.stop();});
  recorder.addEventListener('error',()=>{notify('Recording stopped unexpectedly. Your saved song is unchanged.',true);releaseRecording();});
  recorder.addEventListener('stop',async()=>{const target=state.recordProject;releaseRecording();if(!chunks.length)return;try{if(target.projectId!==state.project.id)throw new Error('Project changed while recording. The recording was not applied.');await run(()=>importAudio(new File([new Blob(chunks)],`Recorded part.${recorder.mimeType.includes('mp4')?'m4a':'webm'}`,{type:recorder.mimeType}),target));}catch(e){failure(e);}});
  recorder.start(1000);state.recordTimer=setTimeout(()=>{if(recorder.state!=='inactive')recorder.stop();},120000);$('record-status').textContent='Recording · stops after 2 minutes';renderDisabled();
}
function releaseRecording(){clearTimeout(state.recordTimer);state.recordingStream?.getTracks().forEach(t=>t.stop());state.recorder=null;state.recordingStream=null;$('record-status').textContent='';renderDisabled();}
function showDownload(blob,name){if(state.preparedUrl)URL.revokeObjectURL(state.preparedUrl);state.preparedUrl=URL.createObjectURL(blob);$('save-download').href=state.preparedUrl;$('save-download').download=name;$('prepared-name').textContent=name;$('file-ready').hidden=false;$('file-ready').scrollIntoView({behavior:'auto',block:'nearest'});$('save-download').focus();}
function filename(extension){return (state.project.title.replace(/[^a-zA-Z0-9_-]+/g,'-').replace(/^-|-$/g,'').slice(0,80)||'song')+extension;}
async function exportProject(){const blob=await writeBundle(state.project,async id=>{const asset=state.assets.get(id);if(!asset)throw new Error('An audio asset is missing. Reopen this project before exporting.');await ensureAudio(asset);return {name:asset.name,mime:'audio/wav',bytes:engine.normalizedWav(id)};});showDownload(blob,filename('.sbsong'));}
async function importProject(file){if(!file)return;const bundle=await readBundle(file);await save();const prepared=[];
  try{for(const a of bundle.assets){const temp=P.newId();await engine.decode(temp,a.bytes);prepared.push({oldId:a.id,name:a.name,bytes:engine.normalizedWav(temp)});engine.remove(temp);}}
  catch(e){throw new Error('The project contains audio this device cannot decode. No project was replaced.');}
  let project={...bundle.project,id:P.newId()};const mapping=new Map(),assets=new Map();for(const p of prepared){const asset=await uploadWav(p.bytes,p.name);mapping.set(p.oldId,asset.id);assets.set(asset.id,asset);}
  project.clips=project.clips.map(c=>({...c,assetId:mapping.get(c.assetId)}));project=P.validateProject(project);
  stop();releaseProjectAudio([...assets.keys()]);
  stop();state.project=project;state.revision=0;state.assets=assets;state.sectionId=project.sections[0].id;state.trackId=project.tracks[0]?.id??null;state.clipId=null;state.jobs=[];state.history=[];state.future=[];state.conflict=false;markDirty();render();await save();notify('Imported as a new project with its audio and arrangement intact.');
}
async function pollJobs(){if(!state.revision)return;const projectId=state.project.id;try{const r=await api(`/api/jobs?projectId=${encodeURIComponent(projectId)}`);if(state.project.id!==projectId)return;state.jobs=r.jobs;pendingRequests.observe(r.jobs);renderJobs();}catch(e){if(e.status===401)notify(e.message,true);} }
function takeRejected(job){if(state.rejectedJobs.has(job.id))return true;try{return localStorage.getItem(`song-builder:rejected:${job.projectId}:${job.id}`)==='1';}catch{return false;}}
function renderJobs(){const holder=$('jobs');if([...holder.querySelectorAll('audio')].some(audio=>!audio.paused&&!audio.ended))return;holder.replaceChildren();if(pendingRequests.get()){holder.append(text('p','A music request has an unknown outcome. Recover the same request before creating another.'),button('Recover previous request',recoverJob));}for(const job of state.jobs){if(takeRejected(job))continue;const item=document.createElement('div');item.className='job';const section=state.project.sections.find(s=>s.id===job.sectionId);item.append(text('p',job.kind==='separate'?'Separated instrument layers':`${section?.name||'Section'} · alternate take`),text('p',job.status,'job-status'));
    if(job.error)item.append(text('p',typeof job.error==='string'?job.error:'This take could not finish. Your accepted parts are unchanged.','hint'));
    if(job.status==='succeeded'){
      if(job.asset){item.append(button('Audition with rack',()=>auditionTake(job),{className:'primary',disabled:state.busy}),text('p','Play this take through Body, Bite, Dirt and Space before accepting it.','hint'));item.append(button('Play original section',()=>auditionOriginal(job),{disabled:state.busy||!section}),button('Accept into new version',()=>acceptTake(job),{disabled:state.busy||!section||section.locked}),button('Reject take',()=>rejectTake(job)));}
      if(job.assets?.length)item.append(button(`Use ${job.assets.length} stems`,()=>acceptStems(job),{disabled:state.busy||selectedSection()?.locked}));
    }holder.append(item);
  }}
// Candidate playback uses the same decoded buffers, rack DSP and meters as the arrangement.
async function auditionTake(job){
  stop();const request=state.playRequest,projectId=state.project.id;
  const section=state.project.sections.find(s=>s.id===job.sectionId);
  if(!section||!job.asset)throw new Error('This take is no longer available in this project.');
  const audio=await ensureAudio(job.asset);
  if(request!==state.playRequest||projectId!==state.project.id)return;
  const key=`${projectId}:${job.id}`,duration=Math.min(section.duration,audio.duration);
  let project=P.newProject('Take audition');
  project={...project,tempo:state.project.tempo,key:state.project.key,sections:[{...project.sections[0],name:section.name,duration}]};
  project=P.addTrack(project,`${section.name} · take audition`.slice(0,60));
  const track=project.tracks[0];
  project=P.updateTrack(project,track.id,{rack:state.auditionRacks.get(key)||{...RACK_DEFAULT}});
  project=P.addClip(project,{trackId:track.id,sectionId:project.sections[0].id,assetId:job.asset.id,offset:0,sourceOffset:0,duration,loop:false,gainDb:0});
  state.audition={project,job,key};
  try{await engine.play(project,{onEnded:()=>{if(request===state.playRequest)state.playing=false;}});}
  catch(error){if(request===state.playRequest)stop();throw error;}
  if(request!==state.playRequest)return;
  state.playing=engine.isPlaying();document.body.classList.add('auditioning');
  $('sound-rack').scrollIntoView({behavior:'auto',block:'start'});$('selected-mixer').hidden=true;$('instrument-heading').textContent='Listening to alternate take';
  renderRack();$('sound-rack').scrollIntoView({behavior:'smooth',block:'center'});
  notify('Auditioning through the rack. Your changes stay with this take when you accept it.');
}
async function sendJob(body){
  try{const r=await api('/api/jobs',{method:'POST',body});pendingRequests.resolve(body.requestId);if(r.job.projectId===state.project.id){state.jobs=state.jobs.filter(j=>j.id!==r.job.id);state.jobs.unshift(r.job);}notify('Music request confirmed. Your accepted audio stays in place.');}
  catch(e){if([400,403,404,409,429].includes(e.status))pendingRequests.resolve(body.requestId);throw e;}
  finally{renderJobs();}
}
async function recoverJob(){const body=pendingRequests.get();if(body)await sendJob(body);}
async function submitJob(kind){if(pendingRequests.get())throw new Error('Use Recover previous request below before creating another take.');await save();const body={requestId:P.newId(),kind,projectId:state.project.id,expectedRevision:state.revision};if(kind==='generate'){body.sectionId=state.sectionId;body.prompt=$('take-prompt').value.trim()||selectedSection().direction;if(!body.prompt)throw new Error('Describe the musical direction for this take.');}else{if(!selectedClip())throw new Error('Select a clip to separate.');body.assetId=selectedClip().assetId;}
  await sendJob(pendingRequests.begin(body));}
async function auditionOriginal(job){const s=state.project.sections.find(section=>section.id===job.sectionId);if(!s)throw new Error('That original section is no longer in this version.');state.sectionId=s.id;state.clipId=null;render();await play(P.sectionStart(state.project,s.id),{sectionOnly:true});}
function rejectTake(job){stop();state.rejectedJobs.add(job.id);let persisted=true;try{localStorage.setItem(`song-builder:rejected:${job.projectId}:${job.id}`,'1');}catch{persisted=false;}renderJobs();notify(persisted?'Take rejected and hidden on this browser. Your original arrangement is unchanged.':'Take hidden for this session. Browser storage is unavailable; it may return after reopening.');}
async function prepareSectionTest(){const s=selectedSection();commit(P.prepareSectionTake(state.project,s.id));await save();notify(`${s.name} is ready for an AI test. Every other section is protected.`);}
async function acceptTake(job){stop();const s=state.project.sections.find(section=>section.id===job.sectionId);if(!s||s.locked)throw new Error('Unlock the original section before using this take.');if(!confirm(`Accept this take for ${s.name} into a new song version? The current version will remain unchanged.`))return;const a=job.asset;const audio=await ensureAudio(a);state.assets.set(a.id,a);await save();let p={...state.project,id:P.newId(),title:`${state.project.title} — ${s.name} AI take`.slice(0,120),clips:state.project.clips.filter(c=>c.sectionId!==s.id)};p=P.addTrack(p,'Generated take');const t=p.tracks.at(-1);p=P.updateTrack(p,t.id,{rack:state.auditionRacks.get(`${state.project.id}:${job.id}`)||{...RACK_DEFAULT}});p=P.addClip(p,{trackId:t.id,sectionId:s.id,assetId:a.id,offset:0,sourceOffset:0,duration:Math.min(s.duration,audio.duration),loop:false,gainDb:0});state.revision=0;state.jobs=[];state.rejectedJobs=new Set();state.history=[];state.future=[];state.sectionId=s.id;state.trackId=t.id;state.clipId=p.clips.at(-1).id;state.project=P.validateProject(p);state.dirty=true;state.sequence++;render();await save();notify(`Take accepted into ${state.project.title}. The prior song version and every other section were preserved.`);}
async function acceptStems(job){const section=selectedSection();if(section.locked)throw new Error('Unlock this section before adding stems.');const selected=selectedClip();const source=selected&&selected.assetId===job.assetId&&selected.sectionId===section.id?selected:null;if(!source)throw new Error('Select the original clip in the section where you want the stems.');
  if(state.project.tracks.length+job.assets.length>12)throw new Error('This would exceed 12 tracks. Start a project with fewer layers before adding these stems.');
  for(const a of job.assets){await ensureAudio(a);state.assets.set(a.id,a);}let p=P.removeClip(state.project,source.id);for(const a of job.assets){p=P.addTrack(p,a.name.slice(0,60));const t=p.tracks.at(-1);const duration=Math.min(source.duration,engine.buffer(a.id).duration-source.sourceOffset);if(duration<=0)throw new Error('The separated audio does not cover this clip’s source range.');p=P.addClip(p,{trackId:t.id,sectionId:section.id,assetId:a.id,offset:source.offset,sourceOffset:source.sourceOffset,duration,loop:source.loop,gainDb:source.gainDb});}commit(p);await save();notify('Separated layers added. Audition them for separation artifacts before exporting.');}

$('save-project').addEventListener('click',()=>run(async()=>{await save();notify('Project saved. You can keep working here.');}));
$('new-project').addEventListener('click',()=>run(()=>startNew()));
$('save-version').addEventListener('click',()=>run(saveVersion));
$('project-list').addEventListener('change',e=>{if(e.target.value)run(()=>loadProject(e.target.value));});
for(const [id,key]of[['song-title','title'],['song-key','key']])$(id).addEventListener('input',()=>{const value=$(id).value;if(key==='title'&&!value.trim())return;try{commit({...state.project,[key]:value},{redraw:false,history:false});}catch(e){failure(e);}});
$('song-tempo').addEventListener('change',()=>{try{commit({...state.project,tempo:Number($('song-tempo').value)});notify('Target tempo updated. Existing audio has not been stretched.');}catch(e){failure(e);render();}});
for(const [id,key]of[['section-name','name'],['section-direction','direction'],['section-lyrics','lyrics']])$(id).addEventListener('input',()=>{const value=$(id).value;if(key==='name'&&!value.trim())return;try{commit(P.updateSection(state.project,state.sectionId,{[key]:value}),{redraw:false,history:false});if(key==='name'){$('section-heading').textContent=value;renderSections();}}catch(e){failure(e);}});
$('section-duration').addEventListener('change',()=>{try{commit(P.updateSection(state.project,state.sectionId,{duration:Number($('section-duration').value)}));}catch(e){failure(e);renderInspector();}});
$('add-section').addEventListener('click',()=>run(()=>{const p=P.addSection(state.project,'Chorus');state.sectionId=p.sections.at(-1).id;commit(p);}));
$('duplicate-section').addEventListener('click',()=>run(()=>{const old=state.project.sections.map(s=>s.id),p=P.duplicateSection(state.project,state.sectionId);state.sectionId=p.sections.find(s=>!old.includes(s.id)).id;commit(p);}));
$('remove-section').addEventListener('click',()=>run(()=>{if(!confirm('Remove this section and its arranged clips? Saved source audio will remain available in other projects.'))return;commit(P.removeSection(state.project,state.sectionId));}));
for(const[id,delta]of[['move-earlier',-1],['move-later',1]])$(id).addEventListener('click',()=>run(()=>commit(P.moveSection(state.project,state.sectionId,delta))));
$('lock-section').addEventListener('click',()=>run(async()=>{commit(P.updateSection(state.project,state.sectionId,{locked:!selectedSection().locked}));await save();}));
$('add-track').addEventListener('click',()=>run(()=>{const p=P.addTrack(state.project,`Layer ${state.project.tracks.length+1}`);state.trackId=p.tracks.at(-1).id;commit(p);}));
$('upload-audio').addEventListener('click',()=>{$('audio-file').value='';$('audio-file').click();});
$('audio-file').addEventListener('change',()=>run(()=>importAudio($('audio-file').files[0])));
$('record-audio').addEventListener('click',()=>{if(state.recorder)state.recorder.stop();else run(()=>toggleRecord());});
$('load-demo').addEventListener('click',()=>run(loadDemo));
$('play-song').addEventListener('click',()=>run(()=>play(Number($('seek').value),{sectionOnly:state.loopSection})));
$('loop-section').addEventListener('click',()=>run(async()=>{state.loopSection=!state.loopSection;$('loop-section').setAttribute('aria-pressed',String(state.loopSection));if(state.playing||state.loopSection)await play(P.sectionStart(state.project,state.sectionId),{sectionOnly:true});}));
$('clear-solos').addEventListener('click',()=>run(()=>{let project=state.project;for(const track of project.tracks)if(track.solo)project=P.updateTrack(project,track.id,{solo:false});commit(project,{resume:true});}));
$('play-section').addEventListener('click',()=>run(()=>play(P.sectionStart(state.project,state.sectionId),{sectionOnly:true})));
$('stop-playback').addEventListener('click',()=>{stop();$('seek').value=0;});
$('seek').addEventListener('change',()=>{if(state.playing)run(()=>play(Number($('seek').value),{sectionOnly:state.sectionOnly}));});
$('undo-edit').addEventListener('click',()=>run(()=>restoreEdit('undo')));$('redo-edit').addEventListener('click',()=>run(()=>restoreEdit('redo')));
for(const id of ['trim-start','extend-start','trim-end','extend-end'])$(id).addEventListener('click',()=>run(()=>quickTrim(id)));
$('duplicate-clip').addEventListener('click',()=>run(duplicateClip));$('split-clip').addEventListener('click',()=>run(splitClip));
$('apply-clip').addEventListener('click',()=>run(()=>{const c=selectedClip();if(!c)return;const patch={offset:Number($('clip-offset').value),sourceOffset:Number($('clip-source').value),duration:Number($('clip-duration').value),loop:$('clip-loop').checked,fadeIn:Number($('clip-fade-in').value),fadeOut:Number($('clip-fade-out').value)};const audio=engine.buffer(c.assetId);if(patch.sourceOffset>=audio.duration||(!patch.loop&&patch.sourceOffset+patch.duration>audio.duration+.001))throw new Error('This edit extends past the source audio. Shorten it or enable looping.');commit(P.updateClip(state.project,c.id,patch));}));
$('remove-clip').addEventListener('click',()=>run(()=>{if(selectedClip())commit(P.removeClip(state.project,state.clipId));}));
$('crossfade-clip').addEventListener('click',()=>run(()=>{if(selectedClip()){commit(P.crossfadeClip(state.project,state.clipId));notify('Crossfade applied to both overlapping clips. Undo restores the previous fades.');}}));
$('export-mix').addEventListener('click',()=>run(async()=>showDownload(await engine.render(state.project),filename('.wav'))));
$('export-section').addEventListener('click',()=>run(async()=>{const start=P.sectionStart(state.project,state.sectionId),section=selectedSection();showDownload(await engine.render(state.project,{from:start,to:start+section.duration}),filename('-'+section.name.replace(/[^a-zA-Z0-9]/g,'-')+'.wav'));}));
$('export-track').addEventListener('click',()=>run(async()=>{if(!state.trackId)throw new Error('Select a track to export.');const track=state.project.tracks.find(t=>t.id===state.trackId);if(track.muted)throw new Error('Unmute this track before exporting it.');showDownload(await engine.render(state.project,{trackId:state.trackId}),filename('-'+track.name.replace(/[^a-zA-Z0-9]/g,'-')+'.wav'));}));
for(const length of [30,15])$(`export-${length}`).addEventListener('click',()=>run(async()=>{const total=P.projectDuration(state.project),start=Math.min(Number($('seek').value),Math.max(0,total-length)),end=Math.min(total,start+length);showDownload(await engine.render(state.project,{from:start,to:end}),filename(`-${length}s.wav`));}));
$('export-project').addEventListener('click',()=>run(exportProject));
$('import-project').addEventListener('click',()=>{$('project-file').value='';$('project-file').click();});
$('project-file').addEventListener('change',()=>run(()=>importProject($('project-file').files[0])));
$('dismiss-download').addEventListener('click',()=>{$('file-ready').hidden=true;});
$('generate-take').addEventListener('click',()=>run(()=>submitJob('generate')));
$('prepare-section-test').addEventListener('click',()=>run(prepareSectionTest));
$('separate-stems').addEventListener('click',()=>run(()=>submitJob('separate')));
$('recover-copy').addEventListener('click',()=>run(async()=>{state.project={...state.project,id:P.newId(),title:(state.project.title+' — recovered').slice(0,120)};state.revision=0;state.conflict=false;state.dirty=true;$('recovery').hidden=true;await save();notify('Your edits were saved as a separate project.');}));
$('reload-saved').addEventListener('click',()=>run(async()=>{if(!confirm('Replace these unsaved edits with the saved version?'))return;await loadProject(state.project.id,{skipSave:true});}));
window.addEventListener('beforeunload',e=>{if(state.dirty||state.recorder){e.preventDefault();e.returnValue='';}});
window.addEventListener('pagehide',()=>{stop();if(state.recorder?.state==='recording')state.recorder.stop();});
document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();if(state.recorder?.state==='recording')state.recorder.stop();if(state.dirty)save().catch(()=>{});}else pollJobs();});

async function boot(){state.busy++;try{
  state.capabilities=await api('/api/capabilities');
  const gen=state.capabilities.generation;
  $('generation-availability').textContent=gen.configured?'Create a new section mix with ElevenLabs Music. Exact voice and musical continuity need listening review.':'Music generation is not connected. You can arrange, record and mix your own audio now.';
  $('generation-cost').textContent=gen.configured?'Generation and stem separation use provider credits. Exact dollar cost is unavailable here. Each click submits one request; failed or abandoned requests may still be billed.':'';
  $('storage-note').textContent=state.capabilities.storage?.durable?'Saved to persistent storage. Export a project backup anytime.':'Private account projects on this server. Storage may reset on redeploy; download a project backup.';
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)$('record-status').textContent='Recording is unavailable in this browser. Import audio instead.';
  const list=await api('/api/projects');const requested=new URLSearchParams(location.search).get('project');const first=list.projects.find(p=>p.id===requested)||list.projects[0];
  if(first)await loadProject(first.id,{skipSave:true});else await startNew();await listProjects();
  state.polling=setInterval(()=>{if(!document.hidden&&!state.busy)pollJobs();},5000);clock();
 }catch(e){failure(e);$('save-state').textContent='Workspace unavailable';}finally{state.busy--;renderDisabled();}}
boot();
