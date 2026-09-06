import { validateProject } from '../core/project.mjs';

const FILE_LIMIT=100*1024*1024, AUDIO_LIMIT=70*1024*1024;
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function exact(value,keys){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join('|')!==[...keys].sort().join('|'))throw new Error('Invalid Song Builder project file.');}
function encode(bytes){let result='';const data=new Uint8Array(bytes);for(let i=0;i<data.length;i+=32768)result+=String.fromCharCode(...data.subarray(i,i+32768));return btoa(result);}
function decode(value){if(typeof value!=='string'||value.length>FILE_LIMIT||value.length%4!==0||!/^[A-Za-z0-9+/]*={0,2}$/.test(value))throw new Error('A project audio file is malformed.');let data;try{data=atob(value);}catch{throw new Error('A project audio file is malformed.');}if(btoa(data)!==value)throw new Error('A project audio file is malformed.');const out=new Uint8Array(data.length);for(let i=0;i<data.length;i++)out[i]=data.charCodeAt(i);return out.buffer;}
export async function writeBundle(value,resolveAsset){const project=validateProject(value),ids=[...new Set(project.clips.map(c=>c.assetId))],assets=[];let total=0;
  if(ids.length>128)throw new Error('A portable project supports at most 128 audio sources. Export individual tracks instead.');
  for(const id of ids){const a=await resolveAsset(id);total+=a.bytes.byteLength;if(total>AUDIO_LIMIT)throw new Error('This project is too large for a mobile project backup. Export the mix and individual tracks instead.');assets.push({id,name:a.name,mime:a.mime,dataBase64:encode(a.bytes)});}
  const blob=new Blob([JSON.stringify({format:'street-banker-song-project',version:1,project,assets})],{type:'application/json'});if(blob.size>FILE_LIMIT)throw new Error('This project backup exceeds 100 MB.');return blob;
}
export async function readBundle(file){if(file.size>FILE_LIMIT)throw new Error('Choose a project file smaller than 100 MB.');let value;try{value=JSON.parse(await file.text());}catch{throw new Error('This is not a valid Song Builder project file.');}
  exact(value,['format','version','project','assets']);if(value.format!=='street-banker-song-project'||value.version!==1||!Array.isArray(value.assets)||value.assets.length>128)throw new Error('This project format is not supported.');const project=validateProject(value.project),needed=new Set(project.clips.map(c=>c.assetId)),seen=new Set(),assets=[];let total=0;
  for(const a of value.assets){exact(a,['id','name','mime','dataBase64']);if(!uuid.test(a.id)||seen.has(a.id)||!needed.has(a.id)||typeof a.name!=='string'||!a.name.length||a.name.length>255||!['audio/wav','audio/mpeg'].includes(a.mime))throw new Error('The project contains invalid or duplicate audio.');seen.add(a.id);const bytes=decode(a.dataBase64);total+=bytes.byteLength;if(total>AUDIO_LIMIT)throw new Error('The project audio is too large for this importer.');assets.push({id:a.id,name:a.name,mime:a.mime,bytes});}
  if(seen.size!==needed.size)throw new Error('The project backup is missing audio.');return {project,assets};
}
