import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {handle,claim} from './worker/index.js';

class DB{
 constructor(){this.sql=new DatabaseSync(':memory:');for(const f of readdirSync('drizzle').filter(n=>n.endsWith('.sql')))this.sql.exec(readFileSync('drizzle/'+f,'utf8'));}
 prepare(sql){const statement=this.sql.prepare(sql);let args=[];return {bind(...values){args=values;return this;},exec(){return {meta:{changes:Number(statement.run(...args).changes)}};},async run(){return this.exec();},async first(){return statement.get(...args)||null;}};}
 async batch(steps){this.sql.exec('BEGIN IMMEDIATE');try{const result=steps.map(s=>s.exec());this.sql.exec('COMMIT');return result;}catch(e){this.sql.exec('ROLLBACK');throw e;}}
}
const context=()=>({waitUntil(p){p.catch(()=>{});}});
const request=(path,body={},headers={})=>new Request('https://gateway.test'+path,{method:'POST',headers:{'content-type':'application/json',...headers},body:JSON.stringify(body)});
const environment=extra=>({DB:new DB(),SERVICE_ENABLED:'true',GEMINI_API_KEY:'FAKE-SERVER-KEY',IP_HASH_SECRET:'FAKE-PRIVATE-SALT',...extra});
const png=()=>{const b=Buffer.alloc(24);Buffer.from([137,80,78,71,13,10,26,10]).copy(b);b.write('IHDR',12);b.writeUInt32BE(100,16);b.writeUInt32BE(100,20);return b.toString('base64');};
async function token(env){const response=await handle(request('/v1/register',{device_id:crypto.randomUUID()}),env);assert.equal(response.status,200);return (await response.json()).token;}
const auth=(token,id=crypto.randomUUID())=>({Authorization:'Bearer '+token,'Idempotency-Key':id});
const result={answers:[{question:'1',answer:'B',option_labels:['A','B'],readable:true,graph:null,solution:{kind:'single_choice',selected_labels:['B'],options:[{label:'A',text:'3'},{label:'B',text:'4'}],text:'',pairs:[],sequence:[],explanation:''}}]};
const success=()=>Response.json({status:'completed',steps:[{type:'model_output',content:[{type:'text',text:JSON.stringify(result)}]}]});

test('disabled/unfunded service never registers clients or contacts a provider',async()=>{
 let calls=0;const env=environment({SERVICE_ENABLED:'false'});
 assert.equal((await handle(request('/v1/register',{device_id:crypto.randomUUID()}),env,{},()=>calls++)).status,503);
 assert.equal((await handle(new Request('https://gateway.test/health'),env).then(r=>r.json())).ready,false);
 assert.equal(calls,0);assert.equal(env.DB.sql.prepare('SELECT count(*) n FROM clients').get().n,0);
});
test('issued token is hashed in D1 and full answers come from a server-controlled provider',async()=>{
 const env=environment(),bearer=await token(env);let calls=0;
 const r=await handle(request('/v1/infer',{image:png(),model:'attacker-model'},auth(bearer)),env,{},async(url,options)=>{
  calls++;assert.equal(url,'https://generativelanguage.googleapis.com/v1beta/interactions');
  assert.equal(options.headers['x-goog-api-key'],'FAKE-SERVER-KEY');assert.equal(options.redirect,'error');
  assert.equal(JSON.parse(options.body).model,'gemini-3.8-flash');return success();
 });
 assert.equal(r.status,200);assert.deepEqual((await r.json()).result,result);assert.equal(calls,1);
 const stored=JSON.stringify(env.DB.sql.prepare('SELECT * FROM clients').all());
 assert.ok(!stored.includes(bearer));assert.ok(!stored.includes('FAKE-SERVER-KEY'));
 const metadata=JSON.stringify(env.DB.sql.prepare('SELECT * FROM requests').all());assert.ok(!metadata.includes('single_choice'));
});
test('missing/revoked credentials and malformed screenshots cannot reach upstream',async()=>{
 const env=environment();let calls=0;const upstream=()=>{calls++;return success();};
 assert.equal((await handle(request('/v1/infer',{image:png()}),env,{},upstream)).status,401);
 const bearer=await token(env);
 assert.equal((await handle(request('/v1/infer',{image:'not a png'},auth(bearer)),env,{},upstream)).status,400);
 env.DB.sql.exec('UPDATE clients SET disabled=1');
 assert.equal((await handle(request('/v1/infer',{image:png()},auth(bearer)),env,{},upstream)).status,401);assert.equal(calls,0);
});
test('duplicate request identifiers cannot spend upstream credits twice',async()=>{
 const env=environment(),bearer=await token(env),headers=auth(bearer);let calls=0;
 const upstream=async()=>{calls++;return success();};
 assert.equal((await handle(request('/v1/infer',{image:png()},headers),env,{},upstream)).status,200);
 assert.equal((await handle(request('/v1/infer',{image:png()},headers),env,{},upstream)).status,409);assert.equal(calls,1);
});
test('global quota cannot be reset by registering another client',async()=>{
 const env=environment({TOTAL_REQUEST_LIMIT:'1'}),one=await token(env),two=await token(env);let calls=0;
 const upstream=async()=>{calls++;return success();};
 assert.equal((await handle(request('/v1/infer',{image:png()},auth(one)),env,{},upstream)).status,200);
 const r=await handle(request('/v1/infer',{image:png()},auth(two)),env,{},upstream);
 assert.equal(r.status,429);assert.equal((await r.json()).error,'quota_reached');assert.equal(calls,1);
});
test('multi-bucket reservations do not partially consume quota when another bucket is exhausted',async()=>{
 const db=new DB();const now=Date.now();
 assert.equal(await claim(db,crypto.randomUUID(),'first',[['global','day',10],['client','day',1]],now),'allowed');
 assert.equal(await claim(db,crypto.randomUUID(),'second',[['global','day',10],['client','day',1]],now),'quota_reached');
 assert.equal(db.sql.prepare("SELECT used FROM quotas WHERE bucket='global'").get().used,1);
});
test('upstream errors and redirects never echo provider secrets or trigger a retry',async()=>{
 const env=environment(),bearer=await token(env),headers=auth(bearer);let calls=0;
 const upstream=async()=>{calls++;return new Response('SECRET BODY FAKE-SERVER-KEY',{status:503});};
 const r=await handle(request('/v1/infer',{image:png()},headers),env,{},upstream);
 assert.equal(r.status,503);assert.ok(!(await r.text()).includes('SECRET'));
 assert.equal((await handle(request('/v1/infer',{image:png()},headers),env,{},upstream)).status,409);assert.equal(calls,1);
});
test('OpenAI path keeps its key server-side and uses the shared full-answer schema',async()=>{
 const env=environment({AI_PROVIDER:'openai',OPENAI_API_KEY:'FAKE-OPENAI'}),bearer=await token(env);
 const r=await handle(request('/v1/infer',{image:png()},auth(bearer)),env,{},async(url,options)=>{
  const b=JSON.parse(options.body);assert.equal(url,'https://api.openai.com/v1/responses');assert.equal(b.store,false);
  assert.ok(b.text.format.schema.properties.answers.items.required.includes('solution'));
  return Response.json({status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(result)}]}]});
 });assert.equal(r.status,200);assert.ok(!(await r.text()).includes('FAKE-OPENAI'));
});
