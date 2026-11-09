import { ANSWER_SCHEMA, PROMPT } from './contract.mjs';
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
const number=(value,fallback)=>Math.max(1,Math.min(1000,Number.parseInt(value,10)||fallback));
const hex=data=>Array.from(new Uint8Array(data),v=>v.toString(16).padStart(2,'0')).join('');
const hash=async value=>hex(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)));
const randomToken=()=> 'STC_'+hex(crypto.getRandomValues(new Uint8Array(32)));
export function configuration(env){
 const provider=env.AI_PROVIDER==='openai'?'openai':'gemini',key=provider==='openai'?env.OPENAI_API_KEY:env.GEMINI_API_KEY;
 return {provider,key,model:env.AI_MODEL||(provider==='openai'?'gpt-5.4-mini':'gemini-3.8-flash'),enabled:env.SERVICE_ENABLED==='true',
  configured:!!(key&&env.DB&&env.IP_HASH_SECRET),total:number(env.TOTAL_REQUEST_LIMIT,50),daily:number(env.DAILY_REQUEST_LIMIT,20),
  clientDaily:number(env.CLIENT_DAILY_LIMIT,10),namespace:env.QUOTA_NAMESPACE||'v1'};
}
async function readJson(request,maximum=4*1024*1024){
 if(!request.headers.get('content-type')?.startsWith('application/json'))throw new Error('invalid_input');
 if(Number(request.headers.get('content-length'))>maximum)throw new Error('image_too_large');
 const reader=request.body?.getReader();if(!reader)throw new Error('invalid_input');
 let size=0;const chunks=[];
 try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>maximum)throw new Error('image_too_large');chunks.push(value);}}
 finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
 const bytes=new Uint8Array(size);let offset=0;for(const value of chunks){bytes.set(value,offset);offset+=value.length;}
 try{return JSON.parse(new TextDecoder().decode(bytes));}catch{throw new Error('invalid_input');}
}
export function validateImage(image){
 if(typeof image!=='string'||image.length>3*1024*1024||image.length%4!==0||! /^[A-Za-z0-9+/]+={0,2}$/.test(image))throw new Error('invalid_input');
 let bytes;try{bytes=Uint8Array.from(atob(image),c=>c.charCodeAt(0));}catch{throw new Error('invalid_input');}
 if(bytes.length>2*1024*1024)throw new Error('image_too_large');
 if(bytes.length<24||![137,80,78,71,13,10,26,10].every((b,i)=>bytes[i]===b)||String.fromCharCode(...bytes.slice(12,16))!=='IHDR')throw new Error('invalid_input');
 const view=new DataView(bytes.buffer),width=view.getUint32(16),height=view.getUint32(20);
 if(width<16||height<16||width>5000||height>5000||width*height>12000000)throw new Error('image_too_large');
 return image;
}
// Each batch is a D1 transaction, so quotas remain atomic across Worker isolates.
export async function claim(db,id,tokenId,buckets,now){
 const statement=(sql,args=[])=>db.prepare(sql).bind(...args);
 const steps=[statement("INSERT OR IGNORE INTO requests(id,token_id,status,created_at) VALUES(?,?,'new',?)",[id,tokenId,now])];
 for(const [bucket,period] of buckets)steps.push(statement('INSERT OR IGNORE INTO quotas(bucket,period,used) VALUES(?,?,0)',[bucket,period]));
 const checks=buckets.map(()=> 'EXISTS(SELECT 1 FROM quotas WHERE bucket=? AND period=? AND used<?)').join(' AND ');
 steps.push(statement("UPDATE requests SET status='reserved' WHERE id=? AND status='new' AND "+checks,[id,...buckets.flat()]));
 const selected=buckets.map(()=> '(bucket=? AND period=?)').join(' OR ');
 steps.push(statement("UPDATE quotas SET used=used+1 WHERE ("+selected+") AND EXISTS(SELECT 1 FROM requests WHERE id=? AND status='reserved')",[...buckets.flatMap(([b,p])=>[b,p]),id]));
 steps.push(statement("UPDATE requests SET status='running' WHERE id=? AND status='reserved'",[id]));
 const results=await db.batch(steps);
 if(results[0].meta.changes!==1)return 'duplicate_request';
 return results.at(-1).meta.changes===1?'allowed':'quota_reached';
}
async function register(request,env,now){
 const body=await readJson(request,512);
 if(typeof body.device_id!=='string'||! /^[a-f0-9-]{32,40}$/i.test(body.device_id))return json({error:'invalid_input'},400);
 const day=new Date(now).toISOString().slice(0,10),ip=await hash(env.IP_HASH_SECRET+'|'+(request.headers.get('cf-connecting-ip')||'unknown'));
 const clientHash=await hash(body.device_id);
 if(await claim(env.DB,crypto.randomUUID(),'registration',[["registrations",day,200],["ip:"+ip,day,20]],now)!=='allowed')return json({error:'registration_limit'},429);
 const existing=await env.DB.prepare('SELECT id,disabled FROM clients WHERE client_hash=?').bind(clientHash).first();
 if(existing?.disabled)return json({error:'access_revoked'},403);
 const token=randomToken(),id=existing?.id||crypto.randomUUID(),expires=now+30*86400000;
 await env.DB.prepare('INSERT INTO clients(id,client_hash,token_hash,expires_at,disabled) VALUES(?,?,?,?,0) ON CONFLICT(client_hash) DO UPDATE SET token_hash=excluded.token_hash,expires_at=excluded.expires_at').bind(id,clientHash,await hash(token),expires).run();
 return json({token,expires_at:expires});
}
async function infer(request,env,config,upstream,now){
 const authorization=request.headers.get('authorization')||'';
 if(! /^Bearer STC_[a-f0-9]{64}$/.test(authorization))return json({error:'authentication_required'},401);
 const client=await env.DB.prepare('SELECT id FROM clients WHERE token_hash=? AND expires_at>? AND disabled=0').bind(await hash(authorization.slice(7)),now).first();
 if(!client)return json({error:'authentication_required'},401);
 const id=request.headers.get('idempotency-key')||'';
 if(! /^[A-Za-z0-9-]{16,64}$/.test(id))return json({error:'invalid_request_id'},400);
 const body=await readJson(request),image=validateImage(body.image),day=new Date(now).toISOString().slice(0,10),minute=new Date(now).toISOString().slice(0,16);
 const allowed=await claim(env.DB,id,client.id,[['all','lifetime-'+config.namespace,config.total],['all',day,config.daily],['client:'+client.id,day,config.clientDaily],['minute:'+client.id,minute,2]],now);
 if(allowed!=='allowed')return json({error:allowed},allowed==='duplicate_request'?409:429);
 let endpoint,payload,headers={'Content-Type':'application/json','User-Agent':'ScreenHelperCloud/8.5'};
 if(config.provider==='openai'){
  endpoint='https://api.openai.com/v1/responses';headers.Authorization='Bearer '+config.key;
  payload={model:config.model,store:false,max_output_tokens:8000,reasoning:{effort:'low'},instructions:PROMPT,
   text:{format:{type:'json_schema',name:'visible_answers',strict:true,schema:ANSWER_SCHEMA}},
   input:[{role:'user',content:[{type:'input_text',text:'Solve the complete visible questions.'},{type:'input_image',detail:'high',image_url:'data:image/png;base64,'+image}]}]};
 }else{
  endpoint='https://generativelanguage.googleapis.com/v1beta/interactions';headers['x-goog-api-key']=config.key;headers['Api-Revision']='2026-05-20';
  payload={model:config.model,store:false,system_instruction:PROMPT+'\nResponse JSON contract (content guidance):\n'+JSON.stringify(ANSWER_SCHEMA),input:[{type:'text',text:'Solve the complete visible questions.'},{type:'image',mime_type:'image/png',data:image}],
   generation_config:{thinking_level:'low',max_output_tokens:8000},response_format:{type:'text',mime_type:'application/json'}};
 }
 try{
  // Workers supports manual/follow, not Fetch's error redirect mode. Never follow redirects with a provider key.
  const response=await upstream(endpoint,{method:'POST',headers,body:JSON.stringify(payload),signal:AbortSignal.timeout(55000),redirect:'manual'});
  if(!response.ok){
   let category='other';try{const problem=await response.json();const message=String(problem?.error?.message||'').toLowerCase();
    category=message.includes('schema')?'schema':message.includes('thinking')?'thinking':message.includes('location')?'location':message.includes('credential')||message.includes('api key')?'credentials':message.includes('demand')?'overloaded':'other';}catch{}
   console.error(JSON.stringify({event:'provider_http_failure',status:response.status,category}));
   await env.DB.prepare("UPDATE requests SET status='upstream_error' WHERE id=?").bind(id).run();
   return json({error:response.status===429?'provider_quota':[401,403].includes(response.status)?'provider_access':'provider_unavailable'},response.status===429?429:503);
  }
  const data=await response.json();if(data.status!=='completed')return json({error:'incomplete_response'},502);
  const text=config.provider==='openai'?data.output?.flatMap(i=>i.content||[]).filter(p=>p.type==='output_text').map(p=>p.text).join(''):data.steps?.filter(s=>s.type==='model_output').flatMap(s=>s.content||[]).filter(p=>p.type==='text').map(p=>p.text).join('');
  let result;try{result=JSON.parse(text);}catch{return json({error:'invalid_response'},502);}
  if(!Array.isArray(result.answers)||result.answers.length<1||result.answers.length>8||JSON.stringify(result).length>60000)return json({error:'invalid_response'},502);
  await env.DB.prepare("UPDATE requests SET status='completed' WHERE id=?").bind(id).run();
  return json({result,model:config.model,provider:config.provider});
 }catch(error){
  const reason=String(error?.message||'').toLowerCase();
  console.error(JSON.stringify({event:'provider_transport_failure',type:error?.name||'Error',category:reason.includes('illegal invocation')?'invocation':reason.includes('timeout')?'timeout':reason.includes('abortsignal')?'abort_signal':'other'}));
  await env.DB.prepare("UPDATE requests SET status='connection_failed' WHERE id=?").bind(id).run().catch(()=>{});
  return json({error:'provider_unavailable'},503);
 }
}
function home(config){
 const state=config.configured&&config.enabled?'Модель подключена':'Модель пока не подключена';
 return new Response(`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Study Tools Cloud</title><style>body{margin:0;background:#f5f7fb;color:#1f3048;font:17px/1.7 system-ui}main{max-width:760px;margin:8vh auto;padding:32px}small{color:#5e7187}h1{font-size:42px;line-height:1.15}.card{background:white;border:1px solid #dce5ee;border-radius:18px;padding:28px;margin:24px 0}.state{color:#236341;font-weight:650}a{color:#285ab7}</style><main><small>SCREEN HELPER · ОБЩИЙ СЕРВИС</small><h1>Ключ остаётся<br>на сервере.</h1><div class="card"><div class="state">${state}</div><p>Приложение Windows подключается автоматически. Вводить ключ провайдера на каждом компьютере не требуется.</p><p>Поддерживаются Gemini и OpenAI. Сейчас выбран ${config.provider==='openai'?'OpenAI':'Gemini'}. Ключ и оплата добавляются владельцем отдельно.</p></div><p>Ограничения общего доступа: ${config.total} запросов всего, ${config.daily} в сутки, ${config.clientDaily} на установку в сутки. Это лимиты запросов, а не денежный баланс.</p><p>Изображения, распознанные вопросы и ответы не сохраняются. Технические записи нужны для авторизации и квот. AI может ошибаться и видит только переданное изображение.</p><p><a href="https://github.com/sultanalibaltabai-alt/screen-helper-proctor-lab/releases/latest">Скачать Windows ZIP</a> · <a href="/health">Состояние API</a></p><small>Общий API не даёт безлимитного доступа за $5. Подписка ChatGPT не является ключом этого сервиса.</small></main></html>`,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"}});
}
export async function handle(request,env,ctx={},upstream=(url,options)=>globalThis.fetch(url,options),now=Date.now()){
 const config=configuration(env),url=new URL(request.url);
 if(request.method==='GET'&&url.pathname==='/')return home(config);
 if(request.method==='GET'&&url.pathname==='/health')return json({version:'8.4',ready:config.configured&&config.enabled,provider:config.provider,limits:{total:config.total,daily:config.daily,client_daily:config.clientDaily}});
 if(!['/v1/register','/v1/infer'].includes(url.pathname))return json({error:'not_found'},404);
 if(request.method!=='POST')return json({error:'method_not_allowed'},405);
 if(!config.configured||!config.enabled)return json({error:'cloud_not_configured'},503);
 try{
  const result=url.pathname==='/v1/register'?await register(request,env,now):await infer(request,env,config,upstream,now);
  if(ctx.waitUntil)ctx.waitUntil(env.DB.batch([
   env.DB.prepare('DELETE FROM requests WHERE created_at<?').bind(now-86400000),
   env.DB.prepare('DELETE FROM clients WHERE expires_at<?').bind(now-86400000),
   env.DB.prepare("DELETE FROM quotas WHERE period NOT LIKE 'lifetime-%' AND period<?").bind(new Date(now-31*86400000).toISOString().slice(0,10))]).catch(()=>{}));
  return result;
 }catch(error){return json({error:error.message==='image_too_large'?'image_too_large':'invalid_input'},400);}
}
export default {fetch:handle};
