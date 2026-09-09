// Real transfer progress and local previews. No analysis or provider call on selection.
const LIMIT = 14 * 1024 * 1024;
const el = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};

export function sendUpload({url, csrf, file, onProgress, xhrFactory = () => new XMLHttpRequest()}) {
  return new Promise((resolve, reject) => {
    const xhr = xhrFactory();
    xhr.open('POST', url);
    xhr.withCredentials = true;
    xhr.timeout = 180000;
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('X-Song-Builder-CSRF', csrf);
    xhr.upload.onprogress = event => onProgress(event.lengthComputable ? event.loaded / event.total : null);
    xhr.upload.onload = () => onProgress(1);
    xhr.onload = () => {
      let value;
      try {
        if (!(xhr.getResponseHeader('Content-Type') || '').includes('application/json')) throw Error();
        value = JSON.parse(xhr.responseText);
      } catch {
        reject(Error('Upload not confirmed. Sign in again, then check your inbox before resending.'));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) reject(Error(value.message || 'Upload was not accepted. Check the file and try again.'));
      else if (!value.track?.id) reject(Error('Upload not confirmed. Check your inbox before resending.'));
      else resolve(value.track);
    };
    xhr.onerror = xhr.ontimeout = xhr.onabort = () => reject(Error('Connection interrupted. Check your inbox before resending; the file may have arrived.'));
    const body = new FormData();
    body.append('authorized', 'true');
    body.append('file', file);
    xhr.send(body);
  });
}

// Sample peaks for a thumbnail only. Full signal analysis still waits for assignment.
export async function previewWav(file) {
  if (!/\.wav$/i.test(file.name) || !file.size || file.size > LIMIT) throw Error('Choose a 16-bit WAV up to 14 MiB.');
  const data = new DataView(await file.arrayBuffer());
  const word = at => String.fromCharCode(...new Uint8Array(data.buffer, at, 4));
  if (data.byteLength < 44 || word(0) !== 'RIFF' || word(8) !== 'WAVE') throw Error('This file is not a readable WAV.');
  let format, audio;
  for (let pos = 12; pos + 8 <= data.byteLength;) {
    const id = word(pos), length = data.getUint32(pos + 4, true), start = pos + 8;
    if (start + length > data.byteLength) throw Error('The WAV appears incomplete. Export a fresh copy.');
    if (id === 'fmt ' && length >= 16) format = {encoding:data.getUint16(start,true),channels:data.getUint16(start+2,true),rate:data.getUint32(start+4,true),align:data.getUint16(start+12,true),bits:data.getUint16(start+14,true)};
    if (id === 'data') audio = {start,length};
    pos = start + length + length % 2;
  }
  if (!format || !audio || format.encoding !== 1 || format.bits !== 16 || ![1,2].includes(format.channels) || !format.rate || format.align !== format.channels * 2 || audio.length % format.align) throw Error('Use mono or stereo 16-bit PCM WAV.');
  const frames = audio.length / format.align, duration = frames / format.rate;
  if (!duration || duration > 600) throw Error('Use an excerpt of 10 minutes or less.');
  const peaks = [];
  for (let i = 0; i < 120; i++) {
    const start = Math.floor(i * frames / 120), end = Math.floor((i + 1) * frames / 120);
    let peak = 0;
    for (let frame = start; frame < end; frame += Math.max(1, Math.floor((end-start)/200))) {
      for (let channel = 0; channel < format.channels; channel++) peak = Math.max(peak, Math.abs(data.getInt16(audio.start + frame * format.align + channel * 2, true)) / 32768);
    }
    peaks.push(peak);
  }
  return {peaks, duration};
}

export function waveThumbnail(peaks) {
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 600 64');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Sampled amplitude preview from this file');
  svg.classList.add('file-wave');
  peaks.forEach((peak, i) => {
    const rect = document.createElementNS(ns, 'rect'), height = Math.max(1, peak * 60);
    for (const [key,value] of Object.entries({x:i*5,y:32-height/2,width:3,height,rx:1})) rect.setAttribute(key,String(value));
    svg.append(rect);
  });
  return svg;
}

export function createUploadDesk({base, csrf, message, inboxCount, onStored, refreshInbox, isBusy, onActivity}) {
  const input = document.getElementById('upload'), list = document.getElementById('upload-queue');
  const picker = document.getElementById('choose-files'), drop = document.getElementById('upload-drop');
  const transfer = document.getElementById('transfer-progress'), label = document.getElementById('transfer-label');
  const lamp = document.getElementById('transfer-lamp'), clear = document.getElementById('clear-queue');
  let entries = [], generation = 0, preparing = false, uploading = false;
  function state(text, status = 'idle', ratio = 0) {
    label.textContent = text; lamp.dataset.state = status;
    if (ratio === null) transfer.removeAttribute('value'); else transfer.value = ratio;
    transfer.setAttribute('aria-label', text);
  }
  function release(entry) {
    entry.audio?.pause();
    if (entry.objectURL) URL.revokeObjectURL(entry.objectURL);
  }
  function reset() {
    generation++; entries.forEach(release); entries = []; input.value = ''; list.replaceChildren(); clear.hidden = true; document.getElementById('preview-empty').hidden=false;
    state('No files selected');
  }
  async function choose(files) {
    if (isBusy() || uploading || preparing) return;
    reset();
    if (!files.length) return;
    if (files.length + inboxCount() > 12) {message('Your inbox holds 12 files. Choose fewer files or remove unused uploads.', true);return;}
    document.getElementById('preview-empty').hidden=true;
    preparing = true;picker.disabled = true;const version = generation;
    state('Preparing local previews', 'active', null);
    try {
      for (const file of files) {
        const entry = {file, status:'selected'}, card = el('article', undefined, 'upload-file');
        const heading = el('div', undefined, 'upload-file-heading'), status = el('span','Selected','file-state');
        heading.append(el('strong',file.name),status);card.append(heading,el('small',(file.size/1024/1024).toFixed(2)+' MiB','hint'));entry.card=card;entry.label=status;
        entries.push(entry);list.append(card);
        try {
          const preview = await previewWav(file);
          if (version !== generation) return;
          card.querySelector('.hint').textContent += ' · '+Math.floor(preview.duration/60)+':'+String(Math.floor(preview.duration%60)).padStart(2,'0');
          card.append(waveThumbnail(preview.peaks));
          const player = document.createElement('audio');player.controls=true;player.preload='none';player.setAttribute('aria-label','Preview '+file.name);
          entry.objectURL=URL.createObjectURL(file);player.src=entry.objectURL;entry.audio=player;
          player.onplay=()=>entries.forEach(other=>{if(other!==entry)other.audio?.pause();});
          card.append(player,el('small','Local preview · nothing uploaded yet','preview-note'));
        } catch (error) {entry.status='invalid';status.textContent='Check file';card.dataset.state='error';card.append(el('p',error.message,'file-error'));}
      }
      clear.hidden=false;const ready=entries.filter(e=>e.status==='selected').length;state(ready+' '+(ready===1?'file':'files')+' ready to upload','selected');
    } finally {preparing=false;picker.disabled=false;}
  }
  picker.onclick=()=>{if(!isBusy())input.click();};
  input.onchange=()=>choose([...input.files]);
  for(const name of ['dragenter','dragover'])drop.addEventListener(name,event=>{event.preventDefault();if(!isBusy())drop.classList.add('drag-over');});
  for(const name of ['dragleave','drop'])drop.addEventListener(name,event=>{event.preventDefault();drop.classList.remove('drag-over');});
  drop.addEventListener('drop',event=>{if(!isBusy())void choose([...event.dataTransfer.files]);});
  clear.onclick=()=>{if(!isBusy()&&!preparing)reset();};
  window.addEventListener('pagehide',()=>{if(!uploading)reset();});
  window.addEventListener('beforeunload',event=>{if(uploading){event.preventDefault();event.returnValue='';}});
  return {
    async upload() {
      if (preparing) throw Error('Wait for the file previews to finish.');
      if (!document.getElementById('authorized').checked) throw Error('Confirm that you are authorized to analyze these files.');
      const pending=entries.filter(e=>e.status==='selected');
      if (!pending.length) throw Error('Choose a WAV file to upload.');
      if (pending.length+inboxCount()>12) throw Error('Remove unused inbox files before uploading this selection.');
      uploading=true;let uploadError=null;onActivity(true);const total=pending.reduce((n,e)=>n+e.file.size,0);let completed=0;
      try {
        for(const entry of pending) {
          entry.audio?.pause();entry.status='uploading';entry.card.dataset.state='active';entry.label.textContent='Transferring';
          state(entry.file.name+' · Transferring','active',null);
          const note=entry.card.querySelector('.preview-note');if(note)note.textContent='Preview stays on this device';
          message('Uploading '+entry.file.name+' to your private inbox…');
          try {
            const track=await sendUpload({url:base+'/api/analysis/uploads',csrf,file:entry.file,onProgress:ratio=>{
              const percent=ratio===null?null:Math.min(100,Math.floor(ratio*100));
              entry.label.textContent=percent===null?'Transferring':percent===100?'Verifying file':percent+'% transferred';
              state(entry.file.name+' · '+entry.label.textContent,'active',ratio===null?null:(completed+entry.file.size*ratio)/total);
            }});
            completed+=entry.file.size;entry.status='ready';entry.label.textContent='Ready in inbox';entry.card.dataset.state='ready';
            if(note)note.textContent='Uploaded · analysis has not started';onStored(track);
          } catch(error) {
            entry.status='error';entry.label.textContent='Needs attention';entry.card.dataset.state='error';
            entry.card.append(el('p',error.message,'file-error'));state('Upload stopped · check your inbox','error',completed/total);throw error;
          }
        }
        state('Upload complete · choose your analysis destination','ready',1);
        message('Upload complete. Choose a destination to analyze.');
        input.value='';
      } catch(error) {uploadError=error;throw error;} finally {
        uploading=false;onActivity(false);
        try {await refreshInbox();} catch(error) {if(!uploadError)throw error;}
      }
    }
  };
}
