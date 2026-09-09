import {encodeWav} from '../core/audio.mjs';
export const PREPARE_LIMIT=14*1024*1024;
/** Explicit PCM copy. Never changes the source buffer, pitch, or playback speed. */
export function prepareWav(buffer,{start=0,end=buffer.duration,sampleRate=44100,channels=2}={}){
 if(![22050,32000,44100,48000].includes(sampleRate)||![1,2].includes(channels))throw Error('Choose a supported WAV sample rate and channel count.');
 if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end>buffer.duration+.001||end-start>600)throw Error('Choose a valid excerpt inside this recording.');
 const frames=Math.floor((end-start)*sampleRate);
 if(44+frames*channels*2>PREPARE_LIMIT)throw Error('This copy exceeds 14 MiB. Shorten the excerpt, or explicitly choose mono or a lower sample rate.');
 const input=Array.from({length:buffer.numberOfChannels},(_,i)=>buffer.getChannelData(i));
 if(input.length>2)throw Error('Use a mono or stereo source for analysis.');
 const output=Array.from({length:channels},()=>new Float32Array(frames));
 for(let c=0;c<channels;c++)for(let i=0;i<frames;i++){
  const position=(start+i/sampleRate)*buffer.sampleRate,at=Math.floor(position),mix=position-at;
  const read=data=>(data[Math.min(at,data.length-1)]||0)*(1-mix)+(data[Math.min(at+1,data.length-1)]||0)*mix;
  output[c][i]=channels===1&&input.length===2?(read(input[0])+read(input[1]))/2:read(input[Math.min(c,input.length-1)]);
 }
 return {bytes:encodeWav(output,sampleRate),start,end: start+frames/sampleRate,sampleRate,channels};
}
export async function decodeForPreparation(file){
 if(file.size>32*1024*1024)throw Error('Choose a source under 32 MiB, or export a shorter excerpt from your editor.');
 const url=URL.createObjectURL(file),audio=new Audio();
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Could not read audio duration. Export a shorter WAV.')),10000);audio.preload='metadata';audio.onloadedmetadata=()=>{clearTimeout(timer);resolve();};audio.onerror=()=>{clearTimeout(timer);reject(Error('This browser cannot open that audio format. Export WAV or MP3.'));};audio.src=url;});
  if(!Number.isFinite(audio.duration)||audio.duration>360)throw Error('For browser preparation, use a source of six minutes or less. Export a shorter excerpt for longer recordings.');
 }finally{audio.removeAttribute('src');audio.load();URL.revokeObjectURL(url);}
 const C=globalThis.AudioContext||globalThis.webkitAudioContext;if(!C)throw Error('Audio conversion is unavailable in this browser.');
 const ctx=new C();try{const result=await ctx.decodeAudioData(await file.arrayBuffer());if(result.duration>360||result.numberOfChannels>2||result.length*result.numberOfChannels>35000000)throw Error('This decoded recording is too large. Use a shorter mono or stereo source.');return result;}finally{await ctx.close();}
}
