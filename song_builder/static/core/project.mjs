/** Portable, immutable song project operations. No host or provider dependencies. */
export const LIMITS = Object.freeze({sections:30, tracks:12, clips:256, assets:128, duration:600});
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ROOT = ['schemaVersion','id','title','tempo','key','sections','tracks','clips'];
const SECTION = ['id','name','duration','lyrics','direction','locked'];
const TRACK = ['id','name','gainDb','pan','muted','solo'];
const CLIP = ['id','trackId','sectionId','assetId','offset','sourceOffset','duration','loop','gainDb'];
function object(value, fields, label, partial = false) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype,null].includes(Object.getPrototypeOf(value))) throw new TypeError(`${label} must be an object.`);
  const keys = Reflect.ownKeys(value);
  if (keys.some(key => !fields.includes(key)) || (!partial && fields.some(key => !Object.hasOwn(value,key)))) {
    throw new TypeError(`${label} has missing or unknown fields.`);
  }
  // JSON data only: do not invoke accessors passed by a caller.
  if (keys.some(key => !Object.hasOwn(Object.getOwnPropertyDescriptor(value,key),'value'))) throw new TypeError(`${label} must contain plain data.`);
}
function string(value, min, max, label) {
  if (typeof value !== 'string' || value.length < min || value.length > max || (min > 0 && !value.trim())) {
    throw new TypeError(`${label} must contain ${min}–${max} characters.`);
  }
}
function number(value,min,max,label) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) throw new RangeError(`${label} must be between ${min} and ${max}.`);
}
function bool(value,label) { if (typeof value !== 'boolean') throw new TypeError(`${label} must be true or false.`); }
function id(value,label='ID') { if (typeof value !== 'string' || !UUID.test(value)) throw new TypeError(`${label} must be a UUID.`); }
function list(value,min,max,label) {
  if (!Array.isArray(value) || value.length < min || value.length > max) throw new RangeError(`${label} must have ${min}–${max} items.`);
  if (Reflect.ownKeys(value).some(key=>key!=='length' && (typeof key!=='string'||!/^(0|[1-9]\d*)$/.test(key)||Number(key)>=value.length))) throw new TypeError(`${label} has unknown fields.`);
  for (let i=0;i<value.length;i++) {
    const descriptor=Object.getOwnPropertyDescriptor(value,i);
    if (!descriptor||!Object.hasOwn(descriptor,'value')) throw new TypeError(`${label} must contain plain items without gaps.`);
  }
}
export function newId() {
  if (!globalThis.crypto?.getRandomValues) throw new Error('Secure UUID generation is unavailable. Open this app over HTTPS.');
  if (globalThis.crypto.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16)); bytes[6]=(bytes[6]&15)|64; bytes[8]=(bytes[8]&63)|128;
  const hex = [...bytes].map(byte=>byte.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export function validateProject(value) {
  object(value,ROOT,'Project');
  if (value.schemaVersion !== 1) throw new TypeError('This project version is not supported.');
  id(value.id,'Project ID'); string(value.title,1,120,'Title'); number(value.tempo,40,240,'Tempo'); string(value.key,0,24,'Key');
  list(value.sections,1,LIMITS.sections,'Sections'); list(value.tracks,0,LIMITS.tracks,'Tracks'); list(value.clips,0,LIMITS.clips,'Clips');
  const ids = new Set([value.id.toLowerCase()]);
  const unique = value => {id(value); const normalized=value.toLowerCase(); if(ids.has(normalized)) throw new TypeError('Project, section, track and clip IDs must be unique.'); ids.add(normalized);};
  const sections = new Map(); const tracks = new Set(); const assets = new Set();
  const output = {schemaVersion:1,id:value.id,title:value.title,tempo:value.tempo,key:value.key,sections:[],tracks:[],clips:[]};
  let total = 0;
  for (const section of value.sections) {
    object(section,SECTION,'Section'); unique(section.id); string(section.name,1,60,'Section name'); number(section.duration,3,120,'Section duration');
    string(section.lyrics,0,3000,'Lyrics'); string(section.direction,0,1000,'Direction'); bool(section.locked,'Section lock');
    total += section.duration; sections.set(section.id,section); output.sections.push({...section});
  }
  if (total > LIMITS.duration) throw new RangeError('A song can be no longer than 600 seconds.');
  for (const track of value.tracks) {
    object(track,TRACK,'Track'); unique(track.id); string(track.name,1,60,'Track name'); number(track.gainDb,-60,6,'Track gain'); number(track.pan,-1,1,'Track pan');
    bool(track.muted,'Track mute'); bool(track.solo,'Track solo'); tracks.add(track.id); output.tracks.push({...track});
  }
  for (const clip of value.clips) {
    object(clip,CLIP,'Clip'); unique(clip.id); id(clip.trackId,'Track reference'); id(clip.sectionId,'Section reference'); id(clip.assetId,'Asset reference');
    if(!tracks.has(clip.trackId) || !sections.has(clip.sectionId)) throw new TypeError('Each clip must reference an existing track and section.');
    number(clip.offset,0,Number.MAX_VALUE,'Clip position'); number(clip.sourceOffset,0,Number.MAX_VALUE,'Source trim');
    number(clip.duration,Number.MIN_VALUE,LIMITS.duration,'Clip duration'); number(clip.gainDb,-60,6,'Clip gain'); bool(clip.loop,'Clip loop');
    if(clip.offset+clip.duration>sections.get(clip.sectionId).duration+0.001) throw new RangeError('A clip must stay inside its section.');
    assets.add(clip.assetId.toLowerCase()); output.clips.push({...clip});
  }
  if (assets.size > LIMITS.assets) throw new RangeError('This project uses too many audio assets.');
  return output;
}
const freshSection = (name='Verse') => ({id:newId(),name,duration:16,lyrics:'',direction:'',locked:false});
export function newProject(title='Untitled song') {
  return validateProject({schemaVersion:1,id:newId(),title,tempo:120,key:'',sections:[freshSection('Verse 1'),freshSection('Chorus'),freshSection('Bridge')],tracks:[],clips:[]});
}
export function projectDuration(project) { return validateProject(project).sections.reduce((sum,section)=>sum+section.duration,0); }
export function sectionStart(project,sectionId) {
  const p=validateProject(project); let start=0;
  for(const section of p.sections) {if(section.id===sectionId) return start; start+=section.duration;}
  throw new RangeError('Section was not found.');
}
function find(items,identifier,label) { const item=items.find(item=>item.id===identifier); if(!item) throw new RangeError(`${label} was not found.`); return item; }
function unlocked(p,identifier) { const section=find(p.sections,identifier,'Section'); if(section.locked) throw new Error(`Unlock “${section.name}” before changing its content.`); return section; }
function mutate(project,operation) { const p=validateProject(project); operation(p); return validateProject(p); }
export function addSection(project,kind='Verse') { return mutate(project,p=>{p.sections.push(freshSection(kind));}); }
export function updateSection(project,identifier,patch) {
  object(patch,SECTION.filter(key=>key!=='id'),'Section changes',true);
  return mutate(project,p=>{
    const section=find(p.sections,identifier,'Section');
    if(section.locked && (Reflect.ownKeys(patch).length !== 1 || patch.locked !== false)) throw new Error('Unlock this section in a separate action before editing it.');
    Object.assign(section,patch);
  });
}
export function prepareSectionTake(project,identifier) {
  return mutate(project,p=>{
    find(p.sections,identifier,'Section');
    for(const section of p.sections) section.locked=section.id!==identifier;
  });
}
export function moveSection(project,identifier,delta) {
  if(!Number.isInteger(delta)) throw new TypeError('Section movement must be a whole number.');
  return mutate(project,p=>{const section=find(p.sections,identifier,'Section'); const index=p.sections.indexOf(section); const target=Math.max(0,Math.min(p.sections.length-1,index+delta)); p.sections.splice(index,1); p.sections.splice(target,0,section);});
}
export function duplicateSection(project,identifier) {
  return mutate(project,p=>{
    const section=find(p.sections,identifier,'Section'); const copy={...section,id:newId(),name:section.name.length<=55?`${section.name} copy`:section.name};
    p.sections.splice(p.sections.indexOf(section)+1,0,copy);
    p.clips.push(...p.clips.filter(clip=>clip.sectionId===identifier).map(clip=>({...clip,id:newId(),sectionId:copy.id})));
  });
}
export function removeSection(project,identifier) { return mutate(project,p=>{unlocked(p,identifier); p.sections=p.sections.filter(section=>section.id!==identifier); p.clips=p.clips.filter(clip=>clip.sectionId!==identifier);}); }
export function addTrack(project,name='New layer') { return mutate(project,p=>{p.tracks.push({id:newId(),name,gainDb:0,pan:0,muted:false,solo:false});}); }
export function updateTrack(project,identifier,patch) { object(patch,TRACK.filter(key=>key!=='id'),'Track changes',true); return mutate(project,p=>{Object.assign(find(p.tracks,identifier,'Track'),patch);}); }
export function removeTrack(project,identifier) {
  return mutate(project,p=>{find(p.tracks,identifier,'Track'); for(const clip of p.clips.filter(clip=>clip.trackId===identifier)) unlocked(p,clip.sectionId); p.tracks=p.tracks.filter(track=>track.id!==identifier); p.clips=p.clips.filter(clip=>clip.trackId!==identifier);});
}
export function addClip(project,clip) {
  object(clip,CLIP,'Clip',true);
  return mutate(project,p=>{const candidate={...clip,id:clip.id===undefined?newId():clip.id}; unlocked(p,candidate.sectionId); p.clips.push(candidate);});
}
/** Change a clip, including trim/loop/move, without mutating either locked section. */
export function updateClip(project,identifier,patch) {
  object(patch,CLIP.filter(key=>key!=='id'),'Clip changes',true);
  return mutate(project,p=>{const clip=find(p.clips,identifier,'Clip'); unlocked(p,clip.sectionId); if(patch.sectionId!==undefined) unlocked(p,patch.sectionId); Object.assign(clip,patch);});
}
export function removeClip(project,identifier) { return mutate(project,p=>{const clip=find(p.clips,identifier,'Clip'); unlocked(p,clip.sectionId); p.clips=p.clips.filter(clip=>clip.id!==identifier);}); }
