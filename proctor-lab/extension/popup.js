async function update(){const {exam}=await chrome.storage.session.get('exam');document.getElementById('state').textContent=exam&&exam.expires>Date.now()?'Контроль включён':'Контроль выключен';}
document.getElementById('stop').onclick=async()=>{await chrome.runtime.sendMessage({action:'panic'});await update();};update();
