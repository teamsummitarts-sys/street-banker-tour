/** Live presence and canonical updates. Playback is never interrupted by a remote save. */
const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
const equal=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));
export function changedParts(before,after){
 const parts=new Set();
 if([...new Set([...Object.keys(before),...Object.keys(after)])].some(k=>!['tracks','clips'].includes(k)&&!equal(before[k],after[k])))parts.add('arrangement');
 if(!equal(before.tracks.map(t=>t.id),after.tracks.map(t=>t.id)))parts.add('arrangement');
 for(const id of new Set([...before.tracks,...after.tracks].map(t=>t.id)))if(!equal(before.tracks.find(t=>t.id===id),after.tracks.find(t=>t.id===id))||!equal(before.clips.filter(c=>c.trackId===id),after.clips.filter(c=>c.trackId===id)))parts.add('track:'+id);
 return parts;
}
export function mergePending(base,local,remote){
 const a=changedParts(base,local),b=changedParts(base,remote);
 if(a.size&&b.size&&(a.has('arrangement')||b.has('arrangement')||[...a].some(k=>b.has(k))))throw Error('Newer changes overlap your pending edit. Keep your edits and resolve the conflict.');
 if(!a.size)return structuredClone(remote);
 if(a.has('arrangement'))return structuredClone(local);
 const result=structuredClone(remote),ids=new Set([...a].map(k=>k.slice(6))),tracks=new Map(local.tracks.map(t=>[t.id,t]));
 result.tracks=result.tracks.map(t=>ids.has(t.id)?structuredClone(tracks.get(t.id)):t);
 result.clips=[...result.clips.filter(c=>!ids.has(c.trackId)),...structuredClone(local.clips.filter(c=>ids.has(c.trackId)))];return result;
}
export function bindLive({document,state,api,save,loadProject,render,notify,newId}){
 const root=document.getElementById('live-room');if(!root)return {tick:async()=>{},canEdit:()=>true,editingScope:()=>undefined,sessionId:()=>null,listenOnly:async()=>{}};
 const status=document.getElementById('live-status'),people=document.getElementById('live-people'),connect=document.getElementById('live-connect'),target=document.getElementById('live-target');
 let connected=false,projectId=null,sessionId=null,working=false,wanted=null,locks=[],expires=0,pointerBusy=false;
 document.addEventListener('pointerdown',()=>{pointerBusy=true;},true);
 for(const event of ['pointerup','pointercancel'])document.addEventListener(event,()=>{pointerBusy=false;},true);
 const active=()=>connected&&projectId===state.project?.id;
 const endpoint=()=>'/api/projects/'+encodeURIComponent(projectId)+'/live';
 const request=scope=>api(endpoint(),{method:'POST',body:{sessionId,scope}});
 const show=message=>{status.textContent=message;connect.textContent=connected?'Leave live session':'Join live session';target.disabled=!active()||state.access?.role==='viewer';};
 async function leave(){const path=endpoint(),id=sessionId;connected=false;state.liveSession=null;locks=[];expires=0;show('Live session closed.');try{await api(path,{method:'DELETE',body:{sessionId:id}});}catch{show('Disconnected. Editing control releases within 20 seconds.');}}
 connect.onclick=async()=>{if(working||state.busy)return;working=true;connect.disabled=true;try{
  if(connected){if(state.dirty)await save();await leave();return;}
  await save();projectId=state.project.id;sessionId=newId();wanted=null;const response=await request(null);expires=response.expires;connected=true;state.liveSession=sessionId;show('Connected · listening. Choose a part to edit.');
 }catch(e){notify(e.message,true);}finally{working=false;connect.disabled=false;render();}};
 target.onchange=async()=>{if(working||!active())return;working=true;try{if(state.dirty)await save();const next=target.value||null;const response=await request(next);wanted=next;if(next?.startsWith('track:')){state.trackId=next.slice(6);state.clipId=null;}expires=response.expires;show(next?'Editing control acquired.':'Connected · listening.');}catch(e){target.value=wanted||'';notify(e.message,true);}finally{working=false;render();}};
 function canEdit(before,after){
  if(!active())return true;
  if(expires*1000<=Date.now()){notify('Live connection expired. Reconnect before editing; your current work is retained.',true);return false;}
  const changed=changedParts(before,after);
  if(changed.size&&!wanted){notify('Choose an instrument or Song arrangement in Live session before editing.',true);return false;}
  if(changed.size&&wanted!=='arrangement'&&[...changed].some(p=>p!==wanted)){notify('That edit affects another part. Select Song arrangement or the appropriate instrument first.',true);return false;}
  return true;
 }
 async function tick(){
  if(working||!state.revision||document.hidden)return;
  working=true;
  try{
   if(connected&&projectId!==state.project.id){await leave();return;}
   if(!active())return;
   const response=await request(wanted);expires=response.expires;
   const data=await api(endpoint());locks=data.presence;
   people.replaceChildren();for(const person of locks){const chip=document.createElement('span');const track=state.project.tracks.find(t=>'track:'+t.id===person.scope);chip.textContent=`${person.name}${person.sessionId===sessionId?' (you)':''} · ${person.scope==='arrangement'?'arrangement':track?.name||'listening'}`;people.append(chip);}
   const prior=target.value;target.replaceChildren(new document.defaultView.Option('Listen only',''),new document.defaultView.Option('Song arrangement','arrangement'));for(const t of state.project.tracks)target.append(new document.defaultView.Option(t.name,'track:'+t.id));target.value=prior;
   if(data.revision!==state.revision){
    if(state.dirty||state.busy||state.playing||state.recorder||pointerBusy){show(state.dirty?'New shared edits available. Save to merge separate tracks.':'New shared edits ready · applied when playback and editing stop.');return;}
    const section=state.sectionId,track=state.trackId;state.busy++;
    try{await loadProject(projectId,{skipSave:true});if(state.project.sections.some(s=>s.id===section))state.sectionId=section;if(state.project.tracks.some(t=>t.id===track))state.trackId=track;render();show('Updated from the shared song · revision '+state.revision);}
    finally{state.busy--;render();}
    return;
   }
   show('Connected · '+locks.length+' present · changes refresh every 3 seconds.');
  }catch(e){show('Connection interrupted · current edits retained. '+e.message);}
  finally{working=false;}
 }
 return {tick,canEdit,listenOnly:async()=>{if(!active())throw Error('Join the live session first.');const response=await request(null);wanted=null;target.value='';expires=response.expires;render();},sessionId:()=>active()?sessionId:null,editingScope:()=>active()?(expires*1000>Date.now()?wanted:null):undefined};
}
