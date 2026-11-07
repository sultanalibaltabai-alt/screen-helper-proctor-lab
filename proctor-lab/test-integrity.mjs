import test from 'node:test';
import assert from 'node:assert/strict';
import {IntegrityGuard,executableScript,summarizeProbe} from './dist/integrity.js';
import {Session} from './dist/core.js';

test('unknown executable scripts are distinguished from inert JSON data',()=>{
  const script=type=>({nodeType:1,tagName:'SCRIPT',getAttribute:()=>type});
  assert.equal(executableScript(script('module')),true);
  assert.equal(executableScript(script('')),true);
  assert.equal(executableScript(script('application/json')),false);
});
test('question changes trigger a signal; ordinary rendering and stopped sessions do not',()=>{
  const observers=[];const events=[];let active=true;
  class Observer {constructor(fn){this.fn=fn;observers.push(this);}observe(){this.observing=true;}disconnect(){this.observing=false;}}
  const listeners=new Map();const document={documentElement:{},addEventListener:(t,f)=>listeners.set(t,f),removeEventListener:t=>listeners.delete(t)};
  const guard=new IntegrityGuard({document,onSignal:(...e)=>events.push(e),isActive:()=>active,Observer});
  const root={outerHTML:'original'};guard.start(root);observers[0].fn();assert.equal(events.length,0);
  root.outerHTML='changed';observers[0].fn();assert.equal(events[0][0],'dom_tamper');assert.equal(observers[0].observing,false);
  guard.start(root);guard.pauseQuestions();root.outerHTML='legitimate render';observers[0].fn();assert.equal(events.length,1);
  guard.start(root);active=false;root.outerHTML='inactive';observers[0].fn();assert.equal(events.length,1);
  active=true;root.isConnected=false;observers[1].fn([]);assert.equal(events[1][0],'dom_tamper');
  guard.destroy();assert.equal(listeners.size,0);assert.equal(observers[1].observing,false);
});
test('new integrity signals pause strict sessions and reset on restart',()=>{
  for(const type of ['dom_tamper','synthetic_input','csp_violation','script_added']){
    const s=new Session();s.start({strict:true});s.record(type);assert.equal(s.paused,type);assert.equal(s.choose(s.questions[0].id,'1'),false);
    s.probes.push({status:'test'});s.finish();s.start();assert.deepEqual(s.probes,[]);assert.equal(s.sequence,1);
  }
});
test('probe never equates no observed browser signals with undetectability',()=>{
  const s=new Session();s.start();const start=s.sequence;const times={startedAt:'start',endedAt:'end'};
  s.record('focus','info');let r=summarizeProbe(s.events,start,times);assert.equal(r.status,'no_browser_events');assert.equal(r.osProcesses,'not_observable');assert.equal(r.oesCompatibility,'not_tested');
  s.record('blur');r=summarizeProbe(s.events,start,times);assert.equal(r.status,'events_observed');assert.deepEqual(r.signals.map(e=>e.type),['blur']);
  assert.equal(summarizeProbe([{seq:4000,level:'info'}],1,times).status,'incomplete');
});
