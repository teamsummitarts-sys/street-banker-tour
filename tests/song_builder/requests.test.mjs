import test from 'node:test';
import assert from 'node:assert/strict';
import {PendingRequests} from '../../song_builder/static/ui/requests.mjs';
function storage(){const values=new Map();return {getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};}
test('uncertain request survives reload with its original ID and settings',()=>{
  const backing=storage(),requests=new PendingRequests(backing,'account-token');
  const body={requestId:'first',projectId:'song',prompt:'Original direction',expectedRevision:1};
  requests.begin(body);body.prompt='Later edit';
  const reloaded=new PendingRequests(backing,'account-token');
  assert.equal(reloaded.get().prompt,'Original direction');
  assert.equal(reloaded.get().requestId,'first');
  assert.throws(()=>reloaded.begin({requestId:'second'}),/previous/);
  reloaded.observe([{requestId:'different'}]);assert.ok(reloaded.get());
  reloaded.observe([{requestId:'first'}]);assert.equal(reloaded.get(),null);
});
test('account scopes isolate recovery and storage failure prevents submission',()=>{
  const backing=storage();new PendingRequests(backing,'alice').begin({requestId:'one'});
  assert.equal(new PendingRequests(backing,'bob').get(),null);
  const broken={getItem:()=>null,setItem:()=>{throw new Error('Storage unavailable');}};
  assert.throws(()=>new PendingRequests(broken,'alice').begin({requestId:'two'}),/unavailable/);
});
