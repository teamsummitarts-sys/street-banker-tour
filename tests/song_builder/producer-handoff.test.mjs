import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {validatePlacement,openProducerRecommendation} from '../../song_builder/static/ui/producer-handoff.mjs';
const require=createRequire(import.meta.url);
const {JSDOM}=require(process.env.RACK_TEST_MODULES?`${process.env.RACK_TEST_MODULES}/jsdom`:'jsdom');

test('reference placement rejects unknown sections and out-of-range times',()=>{
 const p={sections:[{id:'chorus',duration:8}]};
 for(const [id,time] of [['missing',0],['chorus',-1],['chorus',8],['chorus','bad']])assert.throws(()=>validatePlacement(p,id,time));
 assert.equal(validatePlacement(p,'chorus','2.5').time,2.5);
});

test('producer note auditions mapped audio and forks a protected working version without generation',async()=>{
 const dom=new JSDOM('<section id="producer-note"></section><textarea id="take-prompt"></textarea><section id="panel-takes"></section>');
 const d=dom.window.document;d.getElementById('panel-takes').scrollIntoView=()=>{};
 const project={id:'original',title:'Song',sections:[{id:'intro',duration:4},{id:'chorus',name:'Chorus',duration:8,locked:true}],tracks:[],clips:[]};
 const untouched=structuredClone(project),state={project},calls=[],played=[];
 const metadata={version:1,groups:[],scenes:[],takes:[],protections:[{clipId:'protected-clip',mode:'never'}]};
 const note={id:'note',change:'Test a quieter backing vocal.',start:50,end:60,confidence:'medium',identityRisk:'low',requires:'stems',benefit:'Clarity.',tradeoff:'Less weight.',decision:'pending'};
 let task;
 const api=async(path,options)=>{
  calls.push([path,options]);
  if(path==='/api/analysis/runs/report')return {run:{status:'succeeded',report:{recommendations:[note]}}};
  if(path==='/api/workflow?projectId=original')return {metadata};
  if(path==='/api/projects'){assert.deepEqual(project,untouched);return {project:options.body.project};}
  if(path==='/api/workflow/copy'){assert.deepEqual(options.body.metadata,metadata);return {revision:1};}
  throw Error('Unexpected API call '+path);
 };
 await openProducerRecommendation({document:d,params:new URLSearchParams({report:'report',change:'note',section:'chorus',at:'2'}),api,state,base:'/song-builder',loadProject:async id=>{state.project={...state.project,id};},save:async()=>{},play:async(...args)=>played.push(args),notify:()=>{},run:fn=>{task=fn();},render:()=>{},newId:()=>'copy'});
 const button=text=>[...d.querySelectorAll('button')].find(b=>b.textContent===text);
 button('Audition this section').click();await task;assert.deepEqual(played,[[6,{sectionOnly:true}]]);
 button('Prepare a separate working version').click();await task;
 assert.deepEqual(project,untouched);assert.equal(state.project.id,'copy');assert.equal(state.project.sections[1].locked,true);
 assert.equal(d.getElementById('take-prompt').value,note.change);assert.equal(d.getElementById('producer-note').hidden,true);
 assert.equal(calls.some(([path])=>path.includes('/jobs')),false);
 dom.window.close();
});
