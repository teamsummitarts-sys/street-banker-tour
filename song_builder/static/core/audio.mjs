import {validateProject} from './project.mjs';

export const MAX_INPUT_BYTES=40*1024*1024;
export const MAX_DECODED_BYTES=96*1024*1024;
export const MAX_WORKING_BYTES=192*1024*1024;
export const MAX_ASSET_SECONDS=600;
export const EXPORT_SAMPLE_RATE=44100;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const dbToGain=value=>10**(value/20);
function assetId(value) {if(typeof value!=='string'||!UUID.test(value)) throw new TypeError('Audio asset ID must be a UUID.');}
function rate(value) {if(!Number.isInteger(value)||value<8000||value>192000) throw new RangeError('Audio sample rate must be 8–192 kHz.');}
function boundedBuffer(buffer) {
  if(!buffer || ![1,2].includes(buffer.numberOfChannels) || !Number.isInteger(buffer.length) || buffer.length<1 ||
    !Number.isFinite(buffer.duration) || buffer.duration<=0 || buffer.duration>MAX_ASSET_SECONDS) throw new RangeError('Use mono or stereo audio of 600 seconds or less.');
  rate(buffer.sampleRate);
  return buffer.length*buffer.numberOfChannels*4;
}

/** Pure scheduling seam shared by playback and export; all event times are seconds. */
export function buildRenderPlan(project,assets,{from=0,to,trackId}={}) {
  const p=validateProject(project);
  const starts=new Map(); let duration=0;
  for(const section of p.sections) {starts.set(section.id,duration); duration+=section.duration;}
  if(typeof from!=='number'||!Number.isFinite(from)||from<0||from>duration) throw new RangeError('Playback position is outside the song.');
  const end=to===undefined?duration:to;
  if(typeof end!=='number'||!Number.isFinite(end)||end<from||end>duration) throw new RangeError('Render end is outside the song.');
  if(trackId!==undefined&&!p.tracks.some(track=>track.id===trackId)) throw new RangeError('Export track was not found.');
  const solo=p.tracks.some(track=>track.solo);
  const tracks=p.tracks.filter(track=>(trackId===undefined||track.id===trackId)&&!track.muted&&(trackId!==undefined||!solo||track.solo))
    .map(track=>({id:track.id,gain:dbToGain(track.gainDb),pan:track.pan}));
  const audible=new Set(tracks.map(track=>track.id));
  const sectionById=new Map(p.sections.map(section=>[section.id,section]));
  const events=[];
  // Source bounds are checked for every clip, including muted/solo-excluded clips.
  for(const clip of p.clips) {
    const info=assets instanceof Map?assets.get(clip.assetId):assets?.[clip.assetId];
    if(!info) throw new Error('Some song audio is not loaded. Load all sources before playback or export.');
    const sourceDuration=info.duration;
    if(!Number.isFinite(sourceDuration)||sourceDuration<=0||sourceDuration>MAX_ASSET_SECONDS) throw new RangeError('An audio source has an invalid duration.');
    const epsilon=1/(info.sampleRate||44100)+1e-8;
    if(clip.sourceOffset>=sourceDuration || (!clip.loop&&clip.sourceOffset+clip.duration>sourceDuration+epsilon)) {
      throw new RangeError('A clip extends beyond its source. Shorten it or enable looping.');
    }
    const sectionEnd=starts.get(clip.sectionId)+sectionById.get(clip.sectionId).duration;
    const clipStart=starts.get(clip.sectionId)+clip.offset;
    const clipEnd=Math.min(clipStart+clip.duration,sectionEnd);
    const eventStart=Math.max(clipStart,from); const eventEnd=Math.min(clipEnd,end);
    if(eventEnd<=eventStart||!audible.has(clip.trackId)) continue;
    const elapsed=eventStart-clipStart; const loopLength=sourceDuration-clip.sourceOffset;
    events.push({clipId:clip.id,assetId:clip.assetId,trackId:clip.trackId,when:eventStart-from,
      duration:eventEnd-eventStart,offset:clip.sourceOffset+(clip.loop?elapsed%loopLength:elapsed),
      loop:clip.loop,loopStart:clip.sourceOffset,loopEnd:sourceDuration,gain:dbToGain(clip.gainDb)});
  }
  return {duration:end-from,songDuration:duration,from,tracks,events};
}

function wavHeader(frames,channels,sampleRate) {
  rate(sampleRate);
  if(![1,2].includes(channels)||!Number.isSafeInteger(frames)||frames<1) throw new TypeError('Invalid WAV dimensions.');
  const size=44+frames*channels*2;
  if(size>MAX_WORKING_BYTES) throw new RangeError('This WAV exceeds the mobile export memory limit.');
  const output=new ArrayBuffer(size); const view=new DataView(output);
  const word=(offset,text)=>{for(let i=0;i<text.length;i++) view.setUint8(offset+i,text.charCodeAt(i));};
  word(0,'RIFF'); view.setUint32(4,size-8,true); word(8,'WAVE'); word(12,'fmt '); view.setUint32(16,16,true);
  view.setUint16(20,1,true); view.setUint16(22,channels,true); view.setUint32(24,sampleRate,true);
  view.setUint32(28,sampleRate*channels*2,true); view.setUint16(32,channels*2,true); view.setUint16(34,16,true);
  word(36,'data'); view.setUint32(40,size-44,true);
  return output;
}
function writePCM(view,channels,startFrame=0) {
  let offset=44+startFrame*channels.length*2;
  for(let frame=0;frame<channels[0].length;frame++) for(const samples of channels) {
    const sample=samples[frame]; if(!Number.isFinite(sample)) throw new TypeError('Audio contains invalid samples.');
    const bounded=Math.max(-1,Math.min(1,sample));
    view.setInt16(offset,Math.round(bounded*(bounded<0?32768:32767)),true); offset+=2;
  }
}
/** PCM16 WAV, interleaved little-endian. Values outside ±1 hard-clip on export. */
export function encodeWav(channels,sampleRate) {
  if(!Array.isArray(channels)||![1,2].includes(channels.length)||!channels[0]?.length||
    channels.some(channel=>!(channel instanceof Float32Array)||channel.length!==channels[0].length)) throw new TypeError('WAV requires equally sized mono or stereo Float32Arrays.');
  const output=wavHeader(channels[0].length,channels.length,sampleRate); writePCM(new DataView(output),channels); return output;
}

function graph(context,plan,buffers,destination,when=0) {
  const nodes=[]; const sources=[];
  const cleanup=()=>{for(const source of sources) {try{source.stop();}catch{ /* already finished */ }} for(const node of nodes) {try{node.disconnect();}catch{ /* disconnected */ }}};
  try {
    const buses=new Map();
    for(const track of plan.tracks) {
      if(typeof context.createStereoPanner!=='function') throw new Error('Stereo panning is not supported in this browser.');
      const gain=context.createGain(); const pan=context.createStereoPanner(); nodes.push(gain,pan);
      gain.gain.value=track.gain; pan.pan.value=track.pan; gain.connect(pan); pan.connect(destination); buses.set(track.id,gain);
    }
    for(const event of plan.events) {
      const source=context.createBufferSource(); const gain=context.createGain(); nodes.push(source,gain); sources.push(source);
      source.buffer=buffers.get(event.assetId); source.loop=event.loop;
      if(event.loop) {source.loopStart=event.loopStart; source.loopEnd=event.loopEnd;}
      gain.gain.value=event.gain; source.connect(gain); gain.connect(buses.get(event.trackId));
      source.start(when+event.when,event.offset,event.duration);
    }
    return {nodes,sources,cleanup};
  } catch(error) {cleanup(); throw error;}
}

/** Browser-only WebAudio adapter. Constructing it never plays or opens a context. */
export class AudioEngine {
  constructor() {
    this._context=null; this._buffers=new Map(); this._bytes=0; this._active=null;
    this._position=0; this._generation=0; this._disposed=false; this._decoding=false; this._rendering=false;
  }
  _assert() {if(this._disposed) throw new Error('The audio engine has been disposed.');}
  _audioContext() {
    this._assert();
    if(!this._context) {const Constructor=globalThis.AudioContext||globalThis.webkitAudioContext; if(!Constructor) throw new Error('WebAudio is unavailable in this browser.'); this._context=new Constructor();}
    return this._context;
  }
  async decode(identifier,arrayBuffer) {
    this._assert(); assetId(identifier);
    if(this._decoding||this._rendering) throw new Error('Wait for the current audio operation to finish.');
    if(!(arrayBuffer instanceof ArrayBuffer)||arrayBuffer.byteLength<12||arrayBuffer.byteLength>MAX_INPUT_BYTES) throw new RangeError('Choose an audio file no larger than 40 MiB.');
    this.stop();
    this._decoding=true;
    try {
      const context=this._audioContext();
      // Probe duration before decoding compressed audio, so a small compressed
      // file cannot expand into an unbounded AudioBuffer on a mobile device.
      const duration=this._preflightWav(arrayBuffer)??await this._probeDuration(arrayBuffer);
      this._assert();
      const estimated=Math.ceil(duration*context.sampleRate)*2*4;
      if(duration<=0||duration>MAX_ASSET_SECONDS||estimated>MAX_DECODED_BYTES||this._bytes+estimated+arrayBuffer.byteLength*2>MAX_WORKING_BYTES) {
        throw new RangeError('This file exceeds the mobile audio memory limit. Choose a shorter source.');
      }
      const buffer=await context.decodeAudioData(arrayBuffer.slice(0));
      this._assert(); const bytes=boundedBuffer(buffer);
      const previous=this._buffers.get(identifier); const retained=this._bytes-(previous?previous.length*previous.numberOfChannels*4:0);
      if(retained+bytes>MAX_DECODED_BYTES) throw new RangeError('Decoded audio exceeds the 96 MiB mobile limit. Remove unused sources or use shorter files.');
      for(let ch=0;ch<buffer.numberOfChannels;ch++) {const samples=buffer.getChannelData(ch); for(let i=0;i<samples.length;i++) if(!Number.isFinite(samples[i])) throw new TypeError('This audio contains invalid samples.');}
      this._buffers.set(identifier,buffer); this._bytes=retained+bytes;
      return {duration:buffer.duration,sampleRate:buffer.sampleRate,channels:buffer.numberOfChannels};
    } catch(error) {
      if(error?.name==='EncodingError'||error?.name==='NotSupportedError') throw new Error('This browser could not decode the audio. Try a PCM WAV file.');
      throw error;
    } finally {this._decoding=false;}
  }
  _preflightWav(input) {
    const view=new DataView(input); const code=offset=>String.fromCharCode(...new Uint8Array(input,offset,4));
    if(input.byteLength<12||code(0)!=='RIFF'||code(8)!=='WAVE') return;
    if(view.getUint32(4,true)+8!==input.byteLength) throw new TypeError('The WAV size header does not match the file.');
    let channels; let sampleRate; let blockAlign; let dataBytes; let encoding; let bits; let byteRate;
    for(let offset=12;offset+8<=input.byteLength;) {
      const size=view.getUint32(offset+4,true); const start=offset+8;
      if(start+size>input.byteLength) throw new TypeError('The WAV file is truncated.');
      if(code(offset)==='fmt ') {
        if(channels!==undefined||size<16) throw new TypeError('The WAV format header is invalid.');
        encoding=view.getUint16(start,true); channels=view.getUint16(start+2,true); sampleRate=view.getUint32(start+4,true);
        byteRate=view.getUint32(start+8,true); blockAlign=view.getUint16(start+12,true); bits=view.getUint16(start+14,true);
      }
      if(code(offset)==='data') {if(dataBytes!==undefined) throw new TypeError('Multiple WAV data chunks are unsupported.'); dataBytes=size;}
      offset=start+size+(size%2);
    }
    if(channels===undefined||dataBytes===undefined||!dataBytes) throw new TypeError('The WAV file is incomplete or empty.');
    if(![1,2].includes(channels)) throw new RangeError('Choose mono or stereo audio.');
    if(encoding===1||encoding===3) {
      rate(sampleRate);
      if(!((encoding===1&&[8,16,24,32].includes(bits))||(encoding===3&&bits===32))||blockAlign!==channels*bits/8||byteRate!==sampleRate*blockAlign||dataBytes%blockAlign) throw new TypeError('The WAV sample layout is invalid.');
      const duration=dataBytes/blockAlign/sampleRate;
      return duration;
    }
    return undefined;
  }
  _probeDuration(input) {
    if(!globalThis.document?.createElement||!globalThis.URL?.createObjectURL) return Promise.reject(new Error('Audio metadata is unavailable. Use an uncompressed PCM WAV.'));
    return new Promise((resolve,reject)=>{
      const audio=globalThis.document.createElement('audio'); const url=URL.createObjectURL(new Blob([input]));
      let timer;
      const finish=(error)=>{
        clearTimeout(timer); audio.onloadedmetadata=null; audio.onerror=null;
        const duration=audio.duration; audio.removeAttribute('src'); audio.load(); URL.revokeObjectURL(url);
        if(error) reject(error); else if(!Number.isFinite(duration)||duration<=0) reject(new Error('Could not read a bounded audio duration. Use a PCM WAV file.')); else resolve(duration);
      };
      audio.preload='metadata'; audio.onloadedmetadata=()=>finish(); audio.onerror=()=>finish(new Error('This browser could not read the audio. Try a PCM WAV file.'));
      timer=setTimeout(()=>finish(new Error('Audio metadata timed out. Try a PCM WAV file.')),10000); audio.src=url; audio.load();
    });
  }
  has(identifier) {return !this._disposed&&this._buffers.has(identifier);}
  /** Read-only by convention: do not change channel arrays supplied by this method. */
  buffer(identifier) {this._assert(); const buffer=this._buffers.get(identifier); if(!buffer) throw new Error('Audio source is not loaded.'); return buffer;}
  remove(identifier) {
    this._assert(); if(this._rendering||this._decoding) throw new Error('Wait for the current audio operation to finish.'); this.stop();
    const buffer=this._buffers.get(identifier); if(buffer) {this._bytes-=buffer.length*buffer.numberOfChannels*4; this._buffers.delete(identifier);}
  }
  normalizedWav(identifier) {
    const buffer=this.buffer(identifier); const outputBytes=44+buffer.length*buffer.numberOfChannels*2;
    if(this._bytes+outputBytes>MAX_WORKING_BYTES) throw new RangeError('Not enough audio memory to prepare this source.');
    return encodeWav(Array.from({length:buffer.numberOfChannels},(_,ch)=>buffer.getChannelData(ch)),buffer.sampleRate);
  }
  waveform(identifier,bins=100) {
    const buffer=this.buffer(identifier);
    if(!Number.isInteger(bins)||bins<1||bins>2048) throw new RangeError('Waveform bins must be between 1 and 2048.');
    const peaks=new Float32Array(bins);
    for(let bin=0;bin<bins;bin++) {
      const start=Math.floor(bin*buffer.length/bins); const end=Math.min(buffer.length,Math.max(start+1,Math.floor((bin+1)*buffer.length/bins)));
      let peak=0;
      for(let ch=0;ch<buffer.numberOfChannels;ch++) {const samples=buffer.getChannelData(ch); for(let frame=start;frame<end;frame++) peak=Math.max(peak,Math.abs(samples[frame]));}
      peaks[bin]=peak;
    }
    return peaks;
  }
  async play(project,{from=0,onEnded}={}) {
    this._assert(); if(this._decoding||this._rendering) throw new Error('Wait for the current audio operation to finish.');
    if(onEnded!==undefined&&typeof onEnded!=='function') throw new TypeError('Playback completion callback must be a function.');
    const plan=buildRenderPlan(project,this._buffers,{from}); this.stop(); const token=this._generation;
    this._position=from;
    if(plan.duration===0) {onEnded?.(); return;}
    const context=this._audioContext();
    await context.resume();
    if(this._disposed||token!==this._generation) return;
    if(context.state!=='running') throw new Error('Tap Play again to enable audio on this device.');
    const startAt=context.currentTime+0.035;
    let playing;
    try {
      playing=graph(context,plan,this._buffers,context.destination,startAt);
      // Silent clock source makes completion follow the audio clock, including
      // empty tails, background suspension and entirely silent arrangements.
      const clock=context.createBufferSource(); const silence=context.createGain(); silence.gain.value=0;
      clock.buffer=context.createBuffer(1,1,context.sampleRate); clock.loop=true; clock.connect(silence); silence.connect(context.destination);
      playing.nodes.push(clock,silence); playing.sources.push(clock);
      const active={...playing,from,startAt,duration:plan.duration,clock}; this._active=active;
      clock.onended=()=>{if(this._active!==active) return; this._position=plan.songDuration; this._active=null; active.cleanup(); onEnded?.();};
      clock.start(startAt); clock.stop(startAt+plan.duration);
    } catch(error) {playing?.cleanup(); this._active=null; throw error;}
  }
  position() {
    if(!this._active) return this._position;
    const active=this._active;
    return active.from+Math.min(active.duration,Math.max(0,this._context.currentTime-active.startAt));
  }
  stop() {
    this._generation++;
    if(this._active) {const active=this._active; this._position=this.position(); this._active=null; active.clock.onended=null; active.cleanup();}
    return this._position;
  }
  async render(project,{trackId}={}) {
    this._assert(); if(this._rendering||this._decoding) throw new Error('Wait for the current audio operation to finish.');
    const p=validateProject(project); const complete=buildRenderPlan(p,this._buffers,{trackId});
    const Offline=globalThis.OfflineAudioContext||globalThis.webkitOfflineAudioContext;
    if(!Offline) throw new Error('Audio export is not available in this browser.');
    const frames=Math.ceil(complete.songDuration*EXPORT_SAMPLE_RATE); const outputBytes=44+frames*4;
    const chunkFrames=EXPORT_SAMPLE_RATE*8; // bounded 8-second stereo render scratch
    // Include Blob copy, decoded assets, offline output and a conservative scratch reserve.
    if(this._bytes+2*outputBytes+chunkFrames*16>MAX_WORKING_BYTES) throw new RangeError('This export exceeds the mobile memory limit. Shorten the arrangement or remove unused sources.');
    this.stop(); this._rendering=true;
    try {
      const output=wavHeader(frames,2,EXPORT_SAMPLE_RATE); const view=new DataView(output);
      for(let start=0;start<frames;start+=chunkFrames) {
        this._assert(); const length=Math.min(chunkFrames,frames-start); const from=start/EXPORT_SAMPLE_RATE;
        const end=Math.min(complete.songDuration,(start+length)/EXPORT_SAMPLE_RATE);
        const plan=buildRenderPlan(p,this._buffers,{from,to:end,trackId});
        const offline=new Offline(2,length,EXPORT_SAMPLE_RATE); const playing=graph(offline,plan,this._buffers,offline.destination);
        try {const rendered=await offline.startRendering(); this._assert(); writePCM(view,[rendered.getChannelData(0),rendered.getChannelData(1)],start);}
        finally {playing.cleanup();}
        // Yield so the browser can paint export progress and respond on iPhone.
        await new Promise(resolve=>setTimeout(resolve,0));
      }
      return new Blob([output],{type:'audio/wav'});
    } finally {this._rendering=false;}
  }
  dispose() {
    if(this._disposed) return;
    this.stop(); this._disposed=true; this._buffers.clear(); this._bytes=0;
    if(this._context&&this._context.state!=='closed') this._context.close().catch(()=>{});
    this._context=null;
  }
}

/** Original deterministic synthesis, explicitly a demo, not an AI generation. */
export function createDemoAudio() {
  const sampleRate=44100; const duration=8; const frames=sampleRate*duration;
  const kinds=['drums','bass','texture'];
  return kinds.map(kind=>{
    const samples=new Float32Array(frames); let noise=0x517cc1b7;
    const frequencies=[65.4064,65.4064,77.7817,58.2705];
    for(let frame=0;frame<frames;frame++) {
      const time=frame/sampleRate; const beat=time%0.5; const eighth=time%0.25;
      const phrase=Math.floor(time/2); const frequency=frequencies[phrase];
      noise^=noise<<13; noise^=noise>>>17; noise^=noise<<5;
      const random=(noise>>>0)/2147483648-1;
      let sample=0;
      if(kind==='drums') {
        const kickPhase=2*Math.PI*(48*beat+75*0.025*(1-Math.exp(-beat/0.025)));
        const kick=0.32*Math.sin(kickPhase)*Math.exp(-beat*23);
        const snare=(Math.floor(time/0.5)%2===1)?random*Math.exp(-beat*35)*0.11:0;
        const hat=random*Math.exp(-eighth*100)*0.035;
        sample=kick+snare+hat;
      } else if(kind==='bass') {
        const attack=Math.min(1,beat/0.008); const release=Math.min(1,(0.5-beat)/0.035);
        sample=(Math.sin(2*Math.PI*frequency*time)+0.13*Math.sin(4*Math.PI*frequency*time))*attack*release*Math.exp(-beat*2.5)*0.2;
      } else {
        const local=time%2; const envelope=Math.min(1,local/0.12)*Math.min(1,(2-local)/0.2);
        sample=(Math.sin(2*Math.PI*frequency*4*time)+Math.sin(2*Math.PI*frequency*6*time)+Math.sin(2*Math.PI*frequency*8*time))*envelope*0.025;
      }
      const edge=Math.min(1,time/0.004,(duration-time)/0.004);
      samples[frame]=sample*Math.max(0,edge);
    }
    return {name:`Demo ${kind} · original synthesis`,kind,buffer:encodeWav([samples],sampleRate)};
  });
}
