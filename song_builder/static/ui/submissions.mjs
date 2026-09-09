/** Immutable contribution queue. Approval never replaces the source project. */
export function mountSubmissions({root,state,api,audition,stopAudition,notice,onAccepted,upload,save,run,newId}){
 const d=root.ownerDocument,el=(tag,value)=>{const n=d.createElement(tag);if(value)n.textContent=value;return n;};
 const button=(name,fn)=>{const n=el('button',name);n.type='button';n.onclick=()=>run(fn);return n;};
 let loading=false;
 async function refresh(){
  if(!state.project||!state.revision||loading)return;loading=true;const pid=state.project.id;
  try{
   const r=await api(`/api/projects/${pid}/submissions`);if(pid!==state.project.id)return;
   const details=el('details');details.append(el('summary',`Submitted performances · ${r.submissions.filter(s=>s.status==='pending').length} awaiting review`));
   details.append(button('Refresh submissions',refresh));
   details.append(el('p','Submit a recorded performance against this saved backing. The owner can audition it in context, accept it into a new version, or request changes.'));
   if(state.access?.role!=='viewer'){
    const fields=el('div');fields.className='button-row';
    const section=el('select'),track=el('select');section.setAttribute('aria-label','Submission section');track.setAttribute('aria-label','Submission instrument');
    for(const s of state.project.sections)section.add(new Option(s.name,s.id));section.value=state.sectionId;
    for(const t of state.project.tracks)track.add(new Option(t.name,t.id));track.value=state.trackId;
    const file=el('input');file.type='file';file.accept='.wav,audio/wav';file.setAttribute('aria-label','Recorded performance WAV');
    const offset=el('input');offset.type='number';offset.min=0;offset.step=.01;offset.value=0;offset.setAttribute('aria-label','Start within section in seconds');
    const note=el('input');note.maxLength=1000;note.placeholder='What changed in this performance?';note.setAttribute('aria-label','Performance note');
    let attempt=null;
    const submit=button('Submit for review',async()=>{
     if(!file.files[0]||!track.value)throw Error('Choose a WAV performance and its section and instrument.');
     await save();const target=state.project.sections.find(s=>s.id===section.value);if(!target)throw Error('Select a current section.');
     const selected=file.files[0],signature=JSON.stringify([selected.name,selected.size,selected.lastModified,section.value,track.value,offset.value,note.value,state.revision]);
     if(attempt?.signature!==signature){const asset=await upload(selected);attempt={signature,payload:{requestId:newId(),assetId:asset.id,sectionId:section.value,trackId:track.value,offset:Number(offset.value),sourceOffset:0,duration:Math.min(asset.duration,target.duration-Number(offset.value)),expectedRevision:state.revision,note:note.value.trim()}};}
     if(attempt.payload.duration<=0)throw Error('The performance needs to start before this section ends.');
     await api(`/api/projects/${pid}/submissions`,{method:'POST',body:attempt.payload});attempt=null;await refresh();notice('Performance submitted. Your saved arrangement has not changed.');
    });fields.append(section,track,file,offset,note,submit);details.append(fields);
   }
   for(const s of r.submissions){
    const card=el('article');card.className='submission-card';card.append(el('h3',`${s.name} · ${s.sectionName} / ${s.trackName}`),el('p',`${s.status.replaceAll('_',' ')} · source revision ${s.sourceRevision}${s.stale?' · backing has since changed':''}`),el('p',s.note));
    if(s.reason)card.append(el('p','Requested changes: '+s.reason));
    const controls=el('div');controls.className='button-row';controls.append(button('Audition in context',async()=>{const preview=await api(`/api/projects/${pid}/submissions/${s.id}/preview`);await audition(preview);notice(`Auditioning against saved revision ${preview.sourceRevision}${preview.stale?' (earlier backing)':''}.`);}),button('Stop audition',stopAudition));
    if(state.access?.role==='owner'&&s.status==='pending'){
     const acceptId=newId();controls.append(button('Accept into new version',async()=>{await save();const result=await api(`/api/projects/${pid}/submissions/${s.id}/accept`,{method:'POST',body:{requestId:acceptId,expectedRevision:state.revision}});await onAccepted(result);}),button('Request changes',async()=>{const reason=prompt('What should the contributor change?');if(!reason?.trim())return;await api(`/api/projects/${pid}/submissions/${s.id}/changes`,{method:'POST',body:{requestId:newId(),reason:reason.trim()}});await refresh();notice('Change request saved in this project.');}));
    }
    if(s.acceptedProjectId&&state.access?.role==='owner')controls.append(button('Open accepted version',()=>onAccepted({projectId:s.acceptedProjectId})));
    card.append(controls);details.append(card);
   }
   const open=root.querySelector('details')?.open;root.replaceChildren(details);details.open=Boolean(open);
  }catch(error){notice(error.message,true);}finally{loading=false;}
 }
 return {refresh};
}
