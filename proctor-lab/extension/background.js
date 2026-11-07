const HOST='https://proctor-lab-sultan-1106.satinwaterlily4.chatgpt.site';
function allowed(url){try{const u=new URL(url);return u.origin===HOST||u.origin==='http://127.0.0.1:8771';}catch{return false;}}
async function current(){const {exam}=await chrome.storage.session.get('exam');if(!exam||exam.expires<Date.now()){if(exam){await chrome.storage.session.remove('exam');await chrome.action.setBadgeText({text:''});}return null;}return exam;}
let queue=Promise.resolve();
function serial(fn){const task=queue.then(fn);queue=task.catch(()=>{});return task;}
async function emit(type,detail=''){
 const exam=await current();if(!exam)return;
 exam.seq++;exam.events.push({seq:exam.seq,type,at:Date.now(),detail});exam.events=exam.events.slice(-100);
 await chrome.storage.session.set({exam});
 try{await chrome.tabs.sendMessage(exam.tabId,{type:'event',sessionId:exam.sessionId,event:exam.events.at(-1)});}catch{}
}
async function restore(exam){if(!exam?.returnTab)return;try{await chrome.tabs.update(exam.tabId,{active:true});await chrome.windows.update(exam.windowId,{focused:true});}catch{await chrome.storage.session.remove('exam');}}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 if(message.action==='panic'&&sender.id===chrome.runtime.id&&!sender.tab){serial(async()=>{await chrome.storage.session.remove('exam');await chrome.action.setBadgeText({text:''});return {stopped:true};}).then(respond);return true;}
 if(!sender.tab||!allowed(sender.url||sender.tab.url))return;
 serial(async()=>{
  let exam=await current();
  if(message.action==='start'){
   if(!/^[a-zA-Z0-9-]{10,80}$/.test(message.sessionId||''))return {error:'invalid session'};
   if(exam&&exam.tabId!==sender.tab.id)return {error:'another session active'};
   exam={tabId:sender.tab.id,windowId:sender.tab.windowId,sessionId:message.sessionId,returnTab:message.returnTab===true,expires:Date.now()+90000,seq:0,events:[]};
   await chrome.storage.session.set({exam});await chrome.action.setBadgeText({text:'ON'});
  }else if(message.action==='stop'){
   if(exam?.tabId===sender.tab.id&&exam.sessionId===message.sessionId){await chrome.storage.session.remove('exam');await chrome.action.setBadgeText({text:''});exam=null;}
  }else if(message.action==='poll'){
   if(exam?.tabId===sender.tab.id&&exam.sessionId===message.sessionId){exam.expires=Date.now()+90000;await chrome.storage.session.set({exam});}
  }else if(message.action!=='hello')return {error:'unknown action'};
  return {version:'2.0.0',active:!!exam,sessionId:exam?.sessionId,events:exam?.tabId===sender.tab.id?exam.events:[]};
 }).then(respond,()=>respond({error:'extension error'}));return true;
});
chrome.tabs.onCreated.addListener(tab=>serial(async()=>{const e=await current();if(e&&tab.id!==e.tabId){await emit('extension_new_tab','Создана новая вкладка');await restore(e);}}));
chrome.tabs.onActivated.addListener(info=>serial(async()=>{const e=await current();if(e&&info.tabId!==e.tabId){await emit('extension_tab_switch','Выбрана другая вкладка');await restore(e);}}));
chrome.windows.onFocusChanged.addListener(id=>serial(async()=>{const e=await current();if(e&&id!==e.windowId){await emit('extension_window_blur','Фокус вне окна экзамена');/* No forced OS focus loop. */}}));
chrome.tabs.onRemoved.addListener(id=>serial(async()=>{const e=await current();if(e?.tabId===id){await chrome.storage.session.remove('exam');await chrome.action.setBadgeText({text:''});}}));
chrome.tabs.onUpdated.addListener((id,change)=>serial(async()=>{const e=await current();if(e?.tabId===id&&change.status==='loading')await emit('extension_navigation','Вкладка экзамена перезагружена или меняет страницу');}));
