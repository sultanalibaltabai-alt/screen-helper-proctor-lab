(()=>{
 const origin=location.origin;
 function post(data){window.postMessage({source:'proctor-lab-extension',...data},origin);}
 window.addEventListener('message',async event=>{
  if(event.source!==window||event.origin!==origin||event.data?.source!=='proctor-lab-page')return;
  const data=event.data;if(!['hello','start','stop','poll'].includes(data.action))return;
  try{const result=await chrome.runtime.sendMessage({action:data.action,sessionId:data.sessionId,returnTab:data.returnTab});post({action:data.action,result});}catch{post({action:data.action,result:{error:'extension disconnected'}});}
 });
 chrome.runtime.onMessage.addListener(message=>{if(message.type==='event')post({action:'event',result:message});});
 post({action:'hello',result:{version:chrome.runtime.getManifest().version,active:false}});
})();
