import test from 'node:test';
import assert from 'node:assert/strict';
import {DraftJournal} from '../../song_builder/static/ui/draft-journal.mjs';
import {newProject,validateProject} from '../../song_builder/static/core/project.mjs';
function storage(){const data=new Map();return {get length(){return data.size;},key:i=>[...data.keys()][i],getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};}
test('drafts survive reopening, isolate accounts and tabs, and acknowledge only matching saved contents',()=>{
 const disk=storage(),saved=newProject('Saved'),draft={...saved,title:'Unsent edit'};
 const a=new DraftJournal(disk,'owner-a','tab-a',validateProject,()=>100),b=new DraftJournal(disk,'owner-a','tab-b',validateProject,()=>200);
 a.write(draft,3);b.write({...draft,title:'Second window'},3);
 const reopened=new DraftJournal(disk,'owner-a','new-tab',validateProject);
 assert.equal(reopened.pending(saved.id,saved).length,2);
 assert.equal(new DraftJournal(disk,'owner-b','tab-a',validateProject).pending(saved.id,saved).length,0);
 a.acknowledge(saved);assert.equal(reopened.pending(saved.id,saved).length,2);
 a.acknowledge(draft);assert.equal(reopened.pending(saved.id,saved).length,1);
 assert.equal(reopened.pending(saved.id,saved)[0].project.title,'Second window');
});
test('corrupt drafts cannot replace a saved project and storage failure is observable',()=>{
 const disk=storage(),journal=new DraftJournal(disk,'a','t',validateProject),project=newProject();
 disk.setItem(journal.key(project.id),'broken');assert.deepEqual(journal.pending(project.id,project),[]);
 assert.throws(()=>journal.remove('room:draft:v1:b:other'));
 disk.setItem=()=>{throw Error('quota');};assert.throws(()=>journal.write(project,1),/quota/);
});
