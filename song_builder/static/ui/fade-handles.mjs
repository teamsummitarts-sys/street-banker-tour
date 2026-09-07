export function effectiveFades(clip){
  const incoming=clip.fadeIn||0,outgoing=clip.fadeOut||0;
  const scale=Math.min(1,clip.duration/(incoming+outgoing||1));
  return {fadeIn:incoming*scale,fadeOut:outgoing*scale};
}

/** One completed gesture produces one undoable edit; cancellation produces none. */
export function bindFadeHandle(handle,clip,key,{width,allowed,preview,apply,restore}){
  handle.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();});
  handle.addEventListener('pointerdown',event=>{
    if(!allowed()||event.isPrimary===false||event.button>0)return;
    event.preventDefault();event.stopPropagation();
    const pixels=width();if(pixels<=0)return;
    handle.setPointerCapture(event.pointerId);
    const original=effectiveFades(clip),other=key==='fadeIn'?'fadeOut':'fadeIn';
    let value=original[key];
    const move=e=>{
      if(e.pointerId!==event.pointerId)return;
      const delta=(e.clientX-event.clientX)/pixels*clip.duration*(key==='fadeIn'?1:-1);
      value=Math.max(0,Math.min(clip.duration-original[other],Math.round((original[key]+delta)*100)/100));
      preview({...original,[key]:value});
    };
    const clean=()=>{for(const [name,fn]of [['pointermove',move],['pointerup',finish],['pointercancel',cancel],['lostpointercapture',cancel]])handle.removeEventListener(name,fn);};
    const cancel=()=>{clean();restore();};
    const finish=e=>{
      if(e.pointerId!==event.pointerId)return;
      move(e);clean();
      if(allowed()&&value!==original[key])apply({...original,[key]:value});else restore();
    };
    for(const [name,fn]of [['pointermove',move],['pointerup',finish],['pointercancel',cancel],['lostpointercapture',cancel]])handle.addEventListener(name,fn);
  });
}
