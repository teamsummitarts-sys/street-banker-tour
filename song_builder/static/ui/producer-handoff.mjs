/** Explicit reference-to-song mapping. Suggestions never execute audio edits. */
export function validatePlacement(project,sectionId,position){
 const section=project.sections.find(s=>s.id===sectionId),time=Number(position);
 if(!section||!Number.isFinite(time)||time<0||time>=section.duration)throw Error('Choose a time inside the destination section.');
 return {section,time};
}
export function attachRecommendationTarget({document,card,n,runId,base,saveReview,onError}){
 const make=(tag,value)=>{const e=document.createElement(tag);if(value)e.textContent=value;return e;};
 const details=make('details'),summary=make('summary','Try this in a song');details.className='handoff';details.append(summary);card.append(details);
 let loaded=false;
 const get=async path=>{const response=await fetch(base+path,{credentials:'same-origin',cache:'no-store'});if(!response.ok||response.redirected)throw Error('Reopen The Room to load your project.');return response.json();};
 details.addEventListener('toggle',async()=>{if(!details.open||loaded)return;loaded=true;
  try{
   const rows=(await get('/api/projects')).projects;const projectSelect=make('select'),sectionSelect=make('select'),position=make('input');position.type='number';position.min='0';position.step='.1';position.value='0';
   projectSelect.append(new Option('Choose a song',''));for(const p of rows)projectSelect.append(new Option(p.title,p.id));
   const label=(text,input)=>{const l=make('label',text);l.append(input);details.append(l);};
   label('Destination song',projectSelect);label('Destination section',sectionSelect);label('Place at seconds within this section',position);
   details.append(make('p','Reference timestamps do not automatically match your arrangement. Choose the section and placement explicitly.'));
   let project=null,requestVersion=0;
   projectSelect.onchange=async()=>{const version=++requestVersion;project=null;sectionSelect.replaceChildren();if(!projectSelect.value)return;try{const r=await get('/api/projects/'+encodeURIComponent(projectSelect.value));if(version!==requestVersion)return;project=r.project;for(const s of project.sections)sectionSelect.append(new Option(s.name,s.id));}catch(e){onError(e.message);}};
   const open=make('button','Open recommendation in editor');open.type='button';details.append(open);
   open.onclick=async()=>{open.disabled=true;try{if(!project)throw Error('Choose a destination song.');const {section,time}=validatePlacement(project,sectionSelect.value,position.value);await saveReview();const query=new URLSearchParams({project:project.id,report:runId,change:n.id,section:section.id,at:String(time)});location.assign(base+'/?'+query);}catch(e){onError(e.message);}finally{open.disabled=false;}};
  }catch(e){details.append(make('p',e.message));loaded=false;}
 });
}
export async function openProducerRecommendation({document,params,api,state,base,loadProject,save,play,notify,run,render,newId}){
 const root=document.getElementById('producer-note'),runId=params.get('report'),changeId=params.get('change');
 if(!root||!runId||!changeId)return;
 const reportRun=(await api('/api/analysis/runs/'+encodeURIComponent(runId))).run;
 if(reportRun.status!=='succeeded')throw Error('This analysis has no completed recommendation.');
 const note=reportRun.report.recommendations.find(n=>n.id===changeId);if(!note)throw Error('This recommendation is no longer available.');
 const {section,time}=validatePlacement(state.project,params.get('section'),params.get('at')??0);
 state.sectionId=section.id;render();root.hidden=false;root.replaceChildren();
 const make=(tag,value)=>{const e=document.createElement(tag);e.textContent=value;return e;};
 const headline=make('h2','Producer note · '+section.name),detail=make('p',note.change),context=make('p',`Placed at ${time}s in ${section.name}. Reference: ${note.start}–${note.end}s. ${note.confidence} confidence · ${note.identityRisk} identity risk · requires ${note.requires}.`),benefit=make('p',`Expected benefit: ${note.benefit} Tradeoff: ${note.tradeoff}`),actions=make('div','');actions.className='button-row';root.append(headline,detail,context,benefit,actions);
 const add=(label,fn)=>{const b=make('button',label);b.type='button';b.onclick=()=>run(fn);actions.append(b);return b;};
 const originalId=state.project.id;
 add('Audition this section',async()=>{if(state.project.id!==originalId)throw Error('Reopen this recommendation for the current version.');state.sectionId=section.id;render();let start=0;for(const s of state.project.sections){if(s.id===section.id)break;start+=s.duration;}await play(start+time,{sectionOnly:true});});
 add('Prepare a separate working version',async()=>{
  if(state.project.id!==originalId)throw Error('A working version is already open.');await save();
  const workflow=await api('/api/workflow?projectId='+encodeURIComponent(originalId));
  const copy=structuredClone(state.project);copy.id=newId();copy.title=(copy.title+' — producer test').slice(0,120);
  // Preserve every lock; only the user can explicitly unlock a working copy.
  const saved=await api('/api/projects',{method:'POST',body:{project:copy}});
  try { await api('/api/workflow/'+encodeURIComponent(saved.project.id),{method:'PUT',body:{metadata:workflow.metadata,expectedRevision:0}}); }
  catch(error) {
   try { await api('/api/projects/'+encodeURIComponent(saved.project.id),{method:'DELETE',body:{expectedRevision:saved.revision}}); }
   catch { throw Error('The test copy could not retain its workflow protections. Your original is unchanged. Remove the incomplete producer-test copy before continuing.'); }
   throw error;
  }
  await loadProject(saved.project.id,{skipSave:true});state.sectionId=section.id;render();
  document.getElementById('take-prompt').value=note.change.slice(0,1000);
  root.hidden=true;document.getElementById('panel-takes').scrollIntoView({behavior:'auto',block:'start'});
  notify('Separate working version ready. Your original song is unchanged. Audition a take or make a manual edit; no AI request has been sent.');
 });
 add('Reject suggestion',async()=>{const fresh=(await api('/api/analysis/runs/'+encodeURIComponent(runId))).run;await api('/api/analysis/runs/'+encodeURIComponent(runId),{method:'PATCH',body:{expectedRevision:fresh.revision,decisions:Object.fromEntries(fresh.report.recommendations.map(n=>[n.id,n.id===changeId?'rejected':n.decision])),prompt:fresh.report.blueprint.prompt}});root.hidden=true;notify('Suggestion rejected. Your audio is unchanged.');});
 add('Dismiss',async()=>{root.hidden=true;});
}
