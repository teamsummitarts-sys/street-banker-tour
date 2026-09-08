import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {setTimeout as wait} from 'node:timers/promises';
const require=createRequire(import.meta.url),root=process.env.RACK_TEST_MODULES;
const {JSDOM}=require(root?`${root}/jsdom`:'jsdom');
const nativeFetch=globalThis.fetch;
const originalCreate=URL.createObjectURL;
const originalGlobals=Object.fromEntries(['document','window','Option','XMLHttpRequest','FormData'].map(k=>[k,globalThis[k]]));
function wav(){const sampleRate=8000,frames=32000,b=new ArrayBuffer(44+frames*2),v=new DataView(b);const str=(at,s)=>[...s].forEach((c,i)=>v.setUint8(at+i,c.charCodeAt(0)));str(0,'RIFF');v.setUint32(4,b.byteLength-8,true);str(8,'WAVE');str(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,sampleRate,true);v.setUint32(28,sampleRate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,frames*2,true);for(let i=0;i<frames;i++)v.setInt16(44+i*2,Math.sin(2*Math.PI*440*i/sampleRate)*8000,true);return b;}
async function until(check){for(let i=0;i<100;i++){if(await check())return;await wait(50);}throw Error('Timed out waiting for UI');}
test('real Flask + DOM: upload stays unassigned, choose local, review and persist editable blueprint',async()=>{
 const server=spawn('python',['tests/room_analysis_preview.py','18765'],{stdio:'ignore'});let dom,cookie='';
 const origin='http://127.0.0.1:18765';
 try{
  await until(async()=>{try{return (await nativeFetch(origin+'/song-builder/analyze')).ok;}catch{return false;}});
  const page=await nativeFetch(origin+'/song-builder/analyze');cookie=page.headers.get('set-cookie').split(';')[0];
  dom=new JSDOM(await page.text(),{url:origin+'/song-builder/analyze'});dom.cookieJar.setCookieSync(cookie,origin);
  dom.window.Blob.prototype.arrayBuffer=function(){return new Promise(resolve=>{const r=new dom.window.FileReader();r.onload=()=>resolve(r.result);r.readAsArrayBuffer(this);});};
  dom.window.HTMLMediaElement.prototype.pause=function(){};
  URL.createObjectURL=()=> 'blob:test-preview';
  Object.assign(globalThis,{document:dom.window.document,window:dom.window,Option:dom.window.Option,XMLHttpRequest:dom.window.XMLHttpRequest,FormData:dom.window.FormData});
  dom.window.HTMLElement.prototype.scrollIntoView=function(){};
  globalThis.fetch=async(url,options={})=>nativeFetch(new URL(url,origin),{...options,headers:{...options.headers,Cookie:cookie}});
  await import('../../song_builder/static/ui/analysis.mjs');
  const d=dom.window.document;
  await until(()=>d.getElementById('status').textContent.includes('Upload privately'));
  assert.equal(d.getElementById('destination').value,'');
  d.getElementById('authorized').checked=true;
  Object.defineProperty(d.getElementById('upload'),'files',{value:[new dom.window.File([wav()],'original.wav',{type:'audio/wav'})]});
  d.getElementById('upload').dispatchEvent(new dom.window.Event('change'));
  await until(()=>d.querySelector('#upload-queue .file-wave'));
  assert.equal(d.querySelectorAll('#upload-queue audio').length,1);
  d.getElementById('upload-button').click();
  await until(()=>d.getElementById('status').textContent.includes('Upload complete'));
  assert.equal(d.getElementById('transfer-progress').value,1);
  assert.equal(d.getElementById('transfer-lamp').dataset.state,'ready');
  let runs=await (await globalThis.fetch('/song-builder/api/analysis/runs')).json();assert.equal(runs.runs.length,0);
  assert.match(d.getElementById('inbox').textContent,/original.wav/);
  const select=d.getElementById('destination');select.value='local';select.dispatchEvent(new dom.window.Event('change'));
  d.querySelector('[name=mode][value=improve]').checked=true;
  d.getElementById('analyze-button').click();
  await until(()=>d.getElementById('status').textContent.includes('Analysis ready'));
  assert.match(d.getElementById('report').textContent,/Key \/ mode unavailable/);
  assert.match(d.getElementById('report').textContent,/No supported changes proposed/);
  const textarea=d.querySelector('#report textarea');textarea.value='Dry drums; restrained dynamics.';textarea.dispatchEvent(new dom.window.Event('input'));
  const save=[...d.querySelectorAll('#report button')].find(x=>x.textContent==='Save review & prompt');save.click();
  await until(()=>d.getElementById('status').textContent.includes('Review saved'));
  runs=await (await globalThis.fetch('/song-builder/api/analysis/runs')).json();
  const report=await (await globalThis.fetch('/song-builder/api/analysis/runs/'+runs.runs[0].id)).json();
  assert.equal(report.run.report.blueprint.prompt,'Dry drums; restrained dynamics.');
  assert.equal((await (await globalThis.fetch('/song-builder/api/analysis/uploads')).json()).tracks.length,0);
 }finally{server.kill();dom?.window.close();globalThis.fetch=nativeFetch;URL.createObjectURL=originalCreate;for(const [key,value] of Object.entries(originalGlobals)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
});
