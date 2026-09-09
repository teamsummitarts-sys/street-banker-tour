/** Complete portable arrangement/workflow snapshots. No provider calls. */
export function bindSessionArchive({document,state,api,save,loadProject,notify,run,base}){
 const root=document.getElementById('session-archive');let pending=false;
 const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
 const button=(label,task)=>{const n=el('button',label);n.type='button';n.addEventListener('click',()=>run(task));return n;};
 async function refresh(){
  if(pending)return;
  if(!state.project||state.access?.role!=='owner'){root.hidden=true;return;}
  root.hidden=false;pending=true;const pid=state.project.id;
  try{
   const result=await api(`/api/projects/${pid}/checkpoints`);if(pid!==state.project.id)return;
   const details=el('details'),summary=el('summary','Session archives & checkpoints');details.append(summary);
   details.append(el('p','Keep the current arrangement, audio, saved takes, section scenes, clip protections, listening notes and named checkpoints together. Invitations, provider candidates, pending submissions and analysis reports are separate; export reports from Analyze & Improve.'));
   const actions=el('div');actions.className='button-row';
   actions.append(button('Download full session archive',async()=>{await save();const a=el('a');a.href=`${base}/api/projects/${state.project.id}/archive`;a.download='The-Room-session.room.zip';document.body.append(a);a.click();a.remove();notify('Archive download requested. Keep the .room.zip file with your session backups.');}));
   const upload=el('input');upload.type='file';upload.accept='.zip,.room.zip';upload.hidden=true;
   actions.append(button('Restore session archive',()=>{upload.value='';upload.click();}));
   upload.addEventListener('change',()=>run(async()=>{const file=upload.files[0];if(!file)return;await save();const form=new FormData();form.append('file',file);notify('Verifying the session archive and its audio…');const r=await api('/api/session-archives',{method:'POST',body:form});await loadProject(r.projectId,{skipSave:true});notify('Session restored as a separate project, including saved takes and scenes.');}));
   const name=el('input');name.maxLength=80;name.placeholder='Before the chorus edit';name.setAttribute('aria-label','Checkpoint name');
   actions.append(name,button('Save checkpoint',async()=>{if(!name.value.trim())throw Error('Name this checkpoint.');await save();const workflow=await api(`/api/workflow?projectId=${state.project.id}`);await api(`/api/projects/${state.project.id}/checkpoints`,{method:'POST',body:{name:name.value.trim(),expectedRevision:state.revision,expectedWorkflowRevision:workflow.revision}});await refresh();notify('Named checkpoint saved. You can restore it into a separate version.');}));
   details.append(actions,upload);
   for(const cp of result.checkpoints){const row=el('div');row.className='button-row';row.append(el('span',`${cp.name} · revision ${cp.revision} · ${new Date(cp.created*1000).toLocaleDateString()}`),button('Restore '+cp.name,async()=>{await save();const r=await api(`/api/projects/${state.project.id}/checkpoints/${cp.id}/restore`,{method:'POST',body:{}});await loadProject(r.projectId,{skipSave:true});notify('Checkpoint restored as a separate project.');}));details.append(row);}
   const wasOpen=root.querySelector('details')?.open;root.replaceChildren(details);details.open=Boolean(wasOpen);
  }catch(error){notify(error.message,true);}finally{pending=false;}
 }
 return {refresh};
}
