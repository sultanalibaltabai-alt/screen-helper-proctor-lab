import test from 'node:test';
import assert from 'node:assert/strict';
import {NativeClient,FacePolicy} from './dist/supervision.js';
import {Session} from './dist/core.js';

test('default transport preserves the Window receiver required by browser fetch',async()=>{
  const previous=globalThis.fetch;let requests=0;
  globalThis.fetch=async function(url,options){
    if(this!==globalThis)throw new TypeError('Illegal invocation');
    requests++;assert.equal(url,'http://127.0.0.1:8771/api/status');
    assert.equal(options.headers.Authorization,'Bearer pairing-test');
    return {ok:true,json:async()=>({version:'3.0.0',consent:true,active:false,sensors:{},events:[]})};
  };
  try{assert.equal((await new NativeClient().connect('pairing-test')).consent,true);assert.equal(requests,1);}
  finally{globalThis.fetch=previous;}
});

test('face absence and multiple faces require sustained evidence; recovery resets the threshold',()=>{
  let now=0;const signals=[];const p=new FacePolicy({clock:()=>now,onSignal:t=>signals.push(t)});
  p.observe(0,0);now=3500;p.observe(0,1);assert.equal(signals.length,0);
  p.observe(1,2);now=5000;p.observe(0,3);now=8500;p.observe(0,4);assert.equal(signals.length,0);
  now=9100;p.observe(0,5);assert.deepEqual(signals,['face_missing']);
  now=20000;p.observe(2,6);now=21600;p.observe(2,7);assert.deepEqual(signals,['face_missing','multiple_faces']);
});
test('native and face warnings pause strict sessions and block selection',()=>{
  for(const signal of ['native_process','native_lost','native_monitors','face_missing','multiple_faces','camera_frozen','recording_error']){
    const s=new Session();s.start({strict:true});s.record(signal);assert.equal(s.paused,signal);assert.equal(s.choose(s.questions[0].id,'1'),false);
  }
});
test('pairing is carried in a header; owned native events are deduplicated and cannot cross sessions',async()=>{
  const calls=[],events=[];const value={version:'3.0.0',consent:true,active:true,sessionId:'session-test-123',sensors:{},events:[{seq:1,type:'native_process',detail:'test'}]};
  const client=new NativeClient({fetcher:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>structuredClone(value)};},onEvent:e=>events.push(e)});
  await client.connect('secret-test');await client.start('session-test-123');client.flush();client.flush();assert.equal(events.length,1);
  assert(calls.every(x=>!x.url.includes('secret-test')));assert.equal(calls[0].options.headers.Authorization,'Bearer secret-test');
  value.sessionId='another-session';await client.request('status');client.flush();assert.equal(events.length,1);
});
test('loss of native service is surfaced instead of fabricating a clean report',async()=>{
  const errors=[];const client=new NativeClient({fetcher:async()=>{throw new Error('offline');},onLost:e=>errors.push(e)});
  client.sessionId='session-test-123';await client.poll();assert.equal(errors.length,1);assert.equal(client.healthy(),undefined);
});
