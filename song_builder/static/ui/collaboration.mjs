/** Collaboration UI delegates all authorization to the Room API. */
export function bindCollaboration({document,api,state,save,loadProject,notify,run}){
 const root=document.getElementById('collaboration');if(!root)return {refresh:async()=>{}};
 const make=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
 const status=document.getElementById('collaboration-status'),list=document.getElementById('collaborator-list');
 const action=(label,fn)=>{const b=make('button',label);b.type='button';b.onclick=()=>run(fn);return b;};
 async function refresh(){
  if(!state.revision)return;
  const role=state.access?.role||'owner';
  document.getElementById('invite-fields').hidden=role!=='owner';list.replaceChildren();
  if(role!=='owner'){
   status.textContent=`${state.access.name} · ${role} access. Saves check for newer edits; reload to hear changes from another session. AI requests and invitations are owner-only.`;
   list.append(action('Reload shared project',async()=>{if(state.dirty)throw Error('Save your edits or resolve the conflict before reloading.');await loadProject(state.project.id,{skipSave:true});notify('Loaded the latest shared project.');}),action('Leave this Room',async()=>{await api('/api/collaboration/leave',{method:'POST',body:{}});location.assign(base()+'/join');}));return;
  }
  status.textContent='Create a personal, single-use link. Access expires in seven days. Share it yourself; anyone holding an unused link can redeem it.';
  const data=await api(`/api/projects/${state.project.id}/collaborators`);
  for(const invite of data.invites){const member=data.members.find(m=>m.invite_id===invite.id);const row=make('div');row.className='collaboration-row';row.append(make('span',`${member?.name||invite.label} · ${invite.role} · ${invite.revoked?'revoked':invite.expires*1000<Date.now()?'expired':member?'joined':'waiting'}`));if(!invite.revoked)row.append(action('Revoke',async()=>{await api(`/api/projects/${state.project.id}/invitations/${invite.id}`,{method:'DELETE',body:{}});await refresh();}));list.append(row);}
  for(const edit of data.contributions.slice(0,5))list.append(make('p',`${edit.name} saved revision ${edit.revision} · ${new Date(edit.created*1000).toLocaleString()}`));
 }
 function base(){return document.querySelector('meta[name="song-builder-base"]').content;}
 document.getElementById('create-invite').onclick=()=>run(async()=>{await save();const r=await api(`/api/projects/${state.project.id}/invitations`,{method:'POST',body:{role:document.getElementById('invite-role').value,label:document.getElementById('invite-name').value.trim()}});const output=document.getElementById('invite-link');output.hidden=false;output.value=new URL(r.url,location.origin).href;output.focus();output.select();await refresh();notify('Invitation ready. Copy the link and send it to your collaborator.');});
 root.addEventListener('toggle',()=>{if(root.open)refresh().catch(e=>notify(e.message,true));});
 return {refresh};
}
