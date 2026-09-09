/** Hosted listening is opt-in; remote clocks never start audio before a user gesture. */
export function transportPosition(transport,serverNow,roundTripMs,total){
 const elapsed=transport.playing?Math.max(0,serverNow-transport.changed)+Math.min(Math.max(roundTripMs,0),2000)/2000:0;
 return Math.max(0,Math.min(total,transport.position+elapsed));
}
export function bindListening({document,state,api,live,save,play,stop,position,seek,unlock,render,notify,newId,now=()=>Date.now()}){
 const root=document.getElementById('listening-room');if(!root)return {tick:async()=>{},active:()=>false};
 const status=document.getElementById('listening-status'),hostButton=document.getElementById('listen-host'),followButton=document.getElementById('listen-follow'),endButton=document.getElementById('listen-end'),toggle=document.getElementById('listen-play'),scrub=document.getElementById('listen-seek'),notes=document.getElementById('listening-notes');
 let mode='',projectId=null,transport=null,working=false,epoch=0,lastCommand=null,notesSignature='',pendingNote=null,queuedCommand=null;
 const request=async(path,options={})=>{const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),5000);try{return await api(path,{...options,signal:abort.signal});}finally{clearTimeout(timer);}};
 const path=()=>'/api/projects/'+encodeURIComponent(state.project.id);
 const duration=()=>state.project.sections.reduce((sum,s)=>sum+s.duration,0);
 const message=text=>{status.textContent=text;};
 function buttons(){hostButton.textContent=transport?.session_id===live.sessionId()?'Resume hosting':'Host listening';hostButton.disabled=working||!!mode||state.access?.role==='viewer';followButton.textContent=mode==='follow'?'Stop following':'Follow host';followButton.disabled=working||mode==='host';endButton.disabled=working||mode!=='host';toggle.disabled=working||mode!=='host';scrub.disabled=working||mode!=='host';scrub.max=state.project?duration():0;toggle.textContent=transport?.playing?'Pause shared playback':'Play shared mix';render();}
 function detach(){epoch++;mode='';projectId=null;lastCommand=null;stop();message('Local listening. Shared playback is no longer controlling your device.');buttons();}
 async function command(action,at=position()){
  if(working){queuedCommand={action,at};epoch++;return;}working=true;buttons();
  try{await request(path()+'/listening',{method:'POST',body:{sessionId:live.sessionId(),action,position:Math.min(duration(),Math.max(0,at)),expectedVersion:transport?.version||0,expectedRevision:state.revision}});if(action==='end'){detach();transport=null;}}
  catch(e){message(e.message);}
  finally{working=false;buttons();}await tick();
 }
 hostButton.onclick=async()=>{
  if(working||!live.sessionId()){message('Join the live session first.');return;}working=true;buttons();
  try{await unlock();await save();await live.listenOnly();if(!transport||transport.session_id!==live.sessionId())await request(path()+'/listening',{method:'POST',body:{sessionId:live.sessionId(),action:'host',position:position(),expectedVersion:0,expectedRevision:state.revision}});mode='host';projectId=state.project.id;epoch++;message('You are leading. The saved mix is held until you end the session.');}
  catch(e){message(e.message);}finally{working=false;buttons();}await tick();
 };
 followButton.onclick=async()=>{
  if(mode==='follow'){detach();return;}if(working||!live.sessionId()){message('Join the live session first.');return;}working=true;buttons();
  try{await unlock();if(state.dirty)throw Error('Save or resolve your edits before following the host.');await live.listenOnly();mode='follow';projectId=state.project.id;epoch++;message('Following the host.');}
  catch(e){message(e.message);}finally{working=false;buttons();}await tick();
 };
 endButton.onclick=()=>command('end');toggle.onclick=()=>command(transport?.playing?'pause':'play');scrub.onchange=()=>command('seek',Number(scrub.value));
 document.getElementById('stop-playback')?.addEventListener('click',()=>{if(mode==='follow')detach();else if(mode==='host')command('pause',position());},true);
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&mode==='follow')detach();});
 function renderNotes(comments){
  const signature=JSON.stringify([state.revision,mode,comments]);if(signature===notesSignature)return;notesSignature=signature;notes.replaceChildren();
  for(const note of comments){const row=document.createElement('article'),label=document.createElement('strong'),text=document.createElement('p');label.textContent=`${Math.floor(note.position/60)}:${String(Math.floor(note.position%60)).padStart(2,'0')} · ${note.name} · revision ${note.revision}${note.resolved?' · resolved':''}`;text.textContent=note.text;row.append(label,text);
   const jump=document.createElement('button');jump.type='button';jump.textContent='Listen here';jump.disabled=note.revision!==state.revision||mode==='host';jump.onclick=async()=>{try{if(state.dirty)throw Error('Save your edits before auditioning this note.');detach();await play(note.position);}catch(e){message(e.message);}};row.append(jump);
   if(note.canResolve){const resolve=document.createElement('button');resolve.type='button';resolve.textContent=note.resolved?'Reopen note':'Resolve note';resolve.onclick=async()=>{resolve.disabled=true;try{await request(path()+'/feedback/'+note.id,{method:'PATCH',body:{resolved:!note.resolved}});notesSignature='';await tick();}catch(e){message(e.message);}finally{resolve.disabled=false;}};row.append(resolve);}notes.append(row);
  }
 }
 document.getElementById('feedback-form').onsubmit=async event=>{event.preventDefault();const button=document.getElementById('feedback-add');button.disabled=true;
  try{if(state.dirty)throw Error('Save your edits before attaching feedback to this version.');const text=document.getElementById('feedback-text').value.trim();if(!text)throw Error('Write a listening note first.');
   if(!pendingNote)pendingNote={projectId:state.project.id,id:newId(),text,position:position(),expectedRevision:state.revision};
   if(pendingNote.projectId!==state.project.id)throw Error('Return to the previous song to retry its pending note.');
   const {projectId:pid,...body}=pendingNote;await request('/api/projects/'+encodeURIComponent(pid)+'/feedback',{method:'POST',body});pendingNote=null;document.getElementById('feedback-text').value='';message('Feedback saved at the current song position.');notesSignature='';await tick();
  }catch(e){if(e.status&&e.status<500)pendingNote=null;message(e.message);}finally{button.disabled=false;}
 };
 async function tick(){
  if(working||!state.revision||document.hidden)return;working=true;const token=epoch,pid=state.project.id,start=now();
  try{
   const data=await request(path()+'/listening');if(token!==epoch||pid!==state.project.id)return;transport=data.transport;renderNotes(data.comments);
   if(mode){
    if(projectId!==pid||!live.sessionId()||!transport){detach();message('The hosted session has ended.');return;}
    if(mode==='host'&&transport.session_id!==live.sessionId()){detach();message('Another session is leading playback.');return;}
    if(transport.revision!==state.revision||state.dirty){stop();message('Waiting for the host’s saved revision. Stop following, reload the shared song, then follow again.');return;}
    const total=duration(),target=transportPosition(transport,data.serverNow,now()-start,total),key=transport.session_id+':'+transport.version;
    if(transport.playing&&target<total){if(!state.playing||key!==lastCommand||Math.abs(position()-target)>.5){await play(target);if(token!==epoch){stop();return;}}}
    else{if(state.playing)stop();seek(target);}
    lastCommand=key;scrub.value=String(target);message(`${mode==='host'?'Leading':'Following '+transport.name} · revision ${transport.revision}. Network timing may vary.`);
   }else message(transport?transport.name+' is hosting. Tap Follow host to listen together.':'No hosted session. Join live, then lead or follow.');
  }catch(e){if(mode)stop();message('Listening connection interrupted. '+e.message);}
  finally{working=false;buttons();if(queuedCommand){const next=queuedCommand;queuedCommand=null;await command(next.action,next.at);}}
 }
 return {tick,active:()=>!!mode};
}
