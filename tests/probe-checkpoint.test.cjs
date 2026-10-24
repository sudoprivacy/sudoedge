const test = require('node:test');
const assert = require('node:assert/strict');
const {inspectRecords} = require('../scripts/nexus/probe-checkpoint.cjs');
const profile = {expectedLiveAgentId:'original-agent',expectedLiveOwnerId:'original-owner'};
const old = {pid:'node.1',name:'original-agent',owner_id:'original-owner',kind:'MANAGED',zone_id:'root',state:'TERMINATED'};
const current = {...old,pid:'node.2',state:'READY'};

test('historical terminated execution does not become a second logical Agent',()=>{
  const result = inspectRecords([old,current],profile,'--live-agent');
  assert.equal(result.activeManagedCount,1);
  assert.equal(result.historicalTerminatedCount,1);
  assert.equal(result.managedCount,2);
  assert.equal(result.existingExecution.agentId,profile.expectedLiveAgentId);
  assert.equal(result.existingExecution.state,'READY');
});
test('dormant observation stays inactive and cannot pass the live gate',()=>{
  assert.equal(inspectRecords([old],profile,'--existing-agent').executionActive,false);
  assert.throws(()=>inspectRecords([old],profile,'--live-agent'),/active execution count/);
});
test('two active executions of the same principal still refuse',()=>{
  assert.throws(()=>inspectRecords([current,{...current,pid:'node.3'}],profile,'--live-agent'),/active execution count/);
});
test('foreign owner or another identity is not hidden as historical state',()=>{
  for (const changed of [{...old,owner_id:'another-owner'},{...old,name:'another-agent'}]) {
    assert.throws(()=>inspectRecords([changed,current],profile,'--live-agent'),/identity/);
  }
});
test('cold-copy baseline retains its strict no-live and snapshot checks',()=>{
  assert.throws(()=>inspectRecords([old,current],profile,'--baseline'),/Unexpected live/);
  assert.throws(()=>inspectRecords([old],{...profile,expectedManagedCount:0}),/process count/);
  assert.throws(()=>inspectRecords([old],{...profile,expectedManagedCount:1,expectedManagedIdentitySha256:'wrong'}),/bindings/);
});
