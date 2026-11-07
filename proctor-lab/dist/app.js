import {NativeClient,FaceMonitor,LocalRecording} from './supervision.js?v=3.0.1';
import {QUESTIONS, Session, formatTime, isMonitoredShortcut, shortcutLabel} from './core.js';
import {WORKS,pickQuestions} from './bank.js';
import {graphFigure} from './graphs.js';
import {IntegrityGuard,summarizeProbe} from './integrity.js';
const $=id=>document.getElementById(id);
const questionRoot=$('questions');
let session=new Session();
let media={camera:null,mic:null,screen:null};
let audioContext=null, analyser=null, audioRaf=0, loudSince=0, lastLoud=0;
let connecting=false,starting=false;
let probe=null,nativeLost=false,completedNative=null;
const native=new NativeClient({onState:value=>{nativeLost=false;$('native-state').textContent=value.active?'Контроль идёт':value.consent?'Подключён':'Нет разрешения';$('native-monitors').textContent=String(value.sensors.monitors??'Нет данных');$('native-processes').textContent=!value.sensors.capabilities?.processes?'Датчик недоступен':value.sensors.blocked_processes?.map(p=>p.name).join(', ')||'Из списка не найдены';},onEvent:event=>log(event.type,event.level==='info'?'info':'warning',event.detail),onLost:detail=>{if(!nativeLost){nativeLost=true;log('native_lost','warning',detail);$('native-state').textContent='Связь потеряна';}}});
const face=new FaceMonitor({active:()=>session.state==='active',onState:text=>$('face-state').textContent=text,onSignal:(type,detail)=>log(type,'warning',detail)});
const recording=new LocalRecording(text=>{$('record-state').textContent=text;$('download-recordings').disabled=!recording.items.length;},detail=>log('recording_error','warning',detail));
$('download-recordings').addEventListener('click',()=>recording.download());
$('connect-native').addEventListener('click',async()=>{$('connect-native').disabled=true;try{await native.connect($('native-code').value);$('native-message').textContent='Связь установлена. Код действует до закрытия компонента.';}catch(error){$('native-message').textContent=error.message+' · Запусти компонент, разреши контроль и проверь код. При блокировке локальной сети открой локальный стенд кнопкой в программе.';}finally{$('connect-native').disabled=false;}});
$('use-face').addEventListener('change',()=>{if($('use-face').checked)$('use-camera').checked=true;stopMedia();});

const controls=['require-native','native-code','connect-native','use-face','record-local','work','variant','strict-mode','integrity-mode','maximum-mode','require-extension','return-tab','question-count','duration','require-fullscreen','block-clipboard','use-camera','use-mic','use-screen','connect-media','start'];
const guard=new IntegrityGuard({document,isActive:()=>session.state==='active'&&session.config.integrity,onSignal:(type,detail)=>{log(type,'warning',detail);if(type==='dom_tamper')renderQuestions();}});
function syncGuard(){
  if(session.state==='active'&&session.config.integrity){guard.start(questionRoot,!session.paused);$('integrity-state').textContent=session.paused?'Пауза вопросов':'Включён';}
  else{guard.stop();$('integrity-state').textContent=session.state==='active'?'Выключен':'Ожидание';}
  for(const id of ['check-dom','check-input','check-csp'])$(id).disabled=session.state!=='active'||!!session.paused||!session.config.integrity;
  $('probe-start').disabled=session.state!=='active'||!!session.paused||!!probe;
  $('probe-stop').disabled=!probe;
}

function message(text,error=false){$('preflight-message').textContent=text;$('preflight-message').classList.toggle('error',error);}
function selectedQuestions(){return session.state==='idle'?pickQuestions($('work').value,Number($('question-count').value),Number($('variant').value)):session.questions;}
function renderQuestions(){
  guard.pauseQuestions();
  const target=questionRoot;
  if(!target.isConnected)$('exam-panel').insertBefore(target,$('exam-panel').querySelector('.exam-footer'));
  for(const attribute of Array.from(target.attributes))target.removeAttribute(attribute.name);
  target.id='questions';target.className='questions'+(session.state==='active'&&session.paused?' hidden':'');
  target.replaceChildren();
  for(const q of selectedQuestions()){
    const article=document.createElement('article');article.className='question';
    const h=document.createElement('h3');h.className='question-title';
    const id=document.createElement('span');id.className='question-id';id.textContent=`${q.id}.`;
    const text=document.createElement('span');text.textContent=q.text;h.append(id,text);article.append(h);if(q.graph)article.append(graphFigure(q.graph,q.id));
    const options=document.createElement('div');options.className='options';
    q.options.forEach((option,index)=>{
      const label=document.createElement('label');label.className='option';
      const radio=document.createElement('input');radio.type='radio';radio.name=q.id;radio.value=String(index+1);radio.disabled=session.state!=='active'||!!session.paused;radio.checked=session.answers[q.id]===radio.value;
      radio.addEventListener('change',event=>{
        if(session.state==='active'&&session.config.integrity&&!event.isTrusted){log('synthetic_input','warning','Получено программное событие выбора ответа');renderQuestions();return;}
        session.choose(q.id,radio.value);updateAnswered();
      });
      const caption=document.createElement('span');caption.textContent=`${index+1}) ${option}`;label.append(radio,caption);
      if(session.state==='finished'){
        if(radio.value===q.correct)label.classList.add('correct');
        else if(radio.checked)label.classList.add('wrong');
      }
      options.append(label);
    });article.append(options);target.append(article);
  }
  updateAnswered();
  syncGuard();
}
function updateAnswered(){const questions=selectedQuestions();$('answered-count').textContent=`Выбрано ответов: ${questions.filter(q=>session.answers[q.id]).length} из ${questions.length}`;}
function renderLog(){
  const report=session.report();$('event-count').textContent=String(report.events.length);$('warning-count').textContent=String(report.warnings);$('export').disabled=!report.events.length;
  const list=$('event-list');list.replaceChildren();
  if(!report.events.length){const li=document.createElement('li');li.className='empty-log';li.textContent='События появятся после начала сеанса.';list.append(li);return;}
  for(const event of report.events.slice(-100).reverse()){
    const li=document.createElement('li');li.className=event.level;
    const dot=document.createElement('span');dot.className='event-dot';
    const content=document.createElement('span');content.className='event-text';content.textContent=event.label;
    if(event.detail){const detail=document.createElement('span');detail.className='event-detail';detail.textContent=event.detail;content.append(detail);}
    const time=document.createElement('span');time.className='event-time';time.textContent=`+${formatTime(event.elapsedMs/1000)} · ${new Date(event.at).toLocaleTimeString('ru-RU')}`;content.append(time);li.append(dot,content);list.append(li);
  }
}
function log(type,level='warning',detail=''){if(session.record(type,level,detail)){renderLog();applyLock();}}
function applyLock(){guard.pauseQuestions();const locked=session.state==='active'&&!!session.paused;questionRoot.classList.toggle('hidden',locked);$('lock-message').classList.toggle('hidden',!locked);if(locked){$('lock-reason').textContent='Причина: '+(session.events.findLast(e=>e.type===session.paused)?.label||session.paused);$('monitor-pill').textContent='ПАУЗА';}else if(session.state==='active')$('monitor-pill').textContent='НАБЛЮДЕНИЕ';syncGuard();}
function updateMonitor(){
  $('fullscreen-state').textContent=document.fullscreenElement?'Включён':'Выключен';
  $('fullscreen-state').classList.toggle('warn',session.state==='active'&&session.config.fullscreen&&!document.fullscreenElement);
  $('tab-state').textContent=document.hidden?'Скрыта':document.hasFocus()?'Активна':'Без фокуса';
  $('tab-state').classList.toggle('warn',document.hidden||!document.hasFocus());
  $('camera-state').textContent=hasLiveTrack(media.camera,'video')?'Подключена':'Не подключена';
  $('mic-state').textContent=hasLiveTrack(media.mic,'audio')?'Подключён':'Не подключён';
  $('screen-state').textContent=hasLiveTrack(media.screen,'video')?'Подключён':'Не подключён';
  $('previews').classList.toggle('hidden',!hasLiveTrack(media.camera,'video')&&!hasLiveTrack(media.screen,'video'));
}
function hasLiveTrack(stream,kind){return !!stream?.getTracks().some(t=>t.kind===kind&&t.readyState==='live');}
function stopMedia(){
  face.stop();recording.stop();
  cancelAnimationFrame(audioRaf);audioRaf=0;analyser=null;
  if(audioContext){audioContext.close().catch(()=>{});audioContext=null;}
  for(const stream of new Set(Object.values(media))){stream?.getTracks().forEach(track=>track.stop());}
  media={camera:null,mic:null,screen:null};
  for(const id of ['camera-preview','screen-preview']){$(id).srcObject=null;$(id).classList.add('hidden');}
  $('mic-meter').classList.add('hidden');$('mic-level').style.width='0%';loudSince=0;lastLoud=0;updateMonitor();
}
function watchStream(stream,kind){
  for(const track of stream.getTracks()){
    const type=kind==='screen'?'screen':track.kind==='audio'?'mic':'camera';
    track.addEventListener('ended',()=>{log(`${type}_ended`);updateMonitor();});
  }
}
async function beginAudio(stream){
  const Audio=window.AudioContext||window.webkitAudioContext;
  if(!Audio)return;
  audioContext=new Audio();await audioContext.resume();
  analyser=audioContext.createAnalyser();analyser.fftSize=512;
  audioContext.createMediaStreamSource(stream).connect(analyser);
  const data=new Float32Array(analyser.fftSize);$('mic-meter').classList.remove('hidden');
  function measure(){
    if(!analyser)return;
    analyser.getFloatTimeDomainData(data);const rms=Math.sqrt(data.reduce((sum,v)=>sum+v*v,0)/data.length);
    $('mic-level').style.width=`${Math.min(100,rms*350)}%`;
    const now=performance.now();
    if(session.state==='active'&&rms>.13){
      if(!loudSince)loudSince=now;
      if(now-loudSince>1500&&(!lastLoud||now-lastLoud>8000)){log('loud_audio','warning','Уровень выше порога более 1,5 с');lastLoud=now;}
    }else loudSince=0;
    audioRaf=requestAnimationFrame(measure);
  }measure();
}
async function connectMedia(){
  if(connecting||session.state==='active')return;
  connecting=true;$('connect-media').disabled=true;stopMedia();
  try{
    const video=$('use-camera').checked,audio=$('use-mic').checked,screen=$('use-screen').checked;
    if((video||audio||screen)&&!navigator.mediaDevices)throw new Error('Для источников нужен HTTPS или localhost и поддерживаемый браузер.');
    if(video||audio){
      const stream=await navigator.mediaDevices.getUserMedia({video,audio});
      watchStream(stream,'user');
      if(video){media.camera=stream;$('camera-preview').srcObject=stream;$('camera-preview').classList.remove('hidden');}
      if(audio){media.mic=stream;await beginAudio(stream);}
    }
    if(screen){
      if(!navigator.mediaDevices.getDisplayMedia)throw new Error('Демонстрация экрана не поддерживается браузером.');
      const stream=await navigator.mediaDevices.getDisplayMedia({video:true,audio:false});
      media.screen=stream;watchStream(stream,'screen');$('screen-preview').srcObject=stream;$('screen-preview').classList.remove('hidden');
    }
    if($('use-face').checked){if(!video)throw new Error('Для проверки лица включи камеру');await face.load();await $('camera-preview').play();face.start($('camera-preview'));}
    message(video||audio||screen?'Источники подключены. Включи полный экран, если он обязателен.':'Дополнительные источники не выбраны. Можно начинать.');
  }catch(error){
    stopMedia();
    const names={NotAllowedError:'Доступ не предоставлен. Можно повторить подключение или снять соответствующий флажок.',NotFoundError:'Выбранное устройство не найдено.',NotReadableError:'Устройство занято или недоступно.'};
    message(names[error.name]||error.message||'Не удалось подключить источники.',true);
  }finally{connecting=false;$('connect-media').disabled=false;updateMonitor();}
}
async function start(){
  if(connecting||starting||session.state==='active')return;
  if($('require-fullscreen').checked&&!document.fullscreenElement){message('Сначала нажми «Полный экран», затем «Начать тренировочный сеанс».',true);return;}
  for(const [id,kind,track] of [['use-camera','camera','video'],['use-mic','mic','audio'],['use-screen','screen','video']]){
    if($(id).checked&&!hasLiveTrack(media[kind],track)){message('Подключи выбранные источники или отключи их флажки.',true);return;}
  }
  if($('use-face').checked&&!face.healthy()){message('Дождись обнаружения одного лица в камере. Если модель недоступна, подключи источники заново.',true);return;}
  if($('record-local').checked&&!recording.supported()){message('Этот браузер не поддерживает локальную запись.',true);return;}
  if($('require-native').checked){
    starting=true;
    try{const value=await native.connect($('native-code').value);const sensors=value.sensors;
      if(!['processes','monitors','foreground','overlays','clipboard_sequence','removable_drives'].every(k=>sensors.capabilities?.[k]))throw new Error('Не все датчики Windows доступны');
      if(sensors.blocked_processes?.length)throw new Error('Найдены программы из запрещённого списка: '+sensors.blocked_processes.map(p=>p.name).join(', '));
      if(sensors.monitors!==1)throw new Error('Для строгого режима нужен один дисплей');
      if(sensors.removable_drives?.length)throw new Error('Подключены съёмные диски');
    }catch(error){message(error.message,true);return;}finally{starting=false;}
  }
  if($('require-extension').checked){starting=true;const ok=await startExtension();starting=false;if(!ok){message('Расширение не ответило. Установи его и обнови страницу либо отключи требование расширения.',true);return;}}
  if($('use-screen').checked){const surface=media.screen?.getVideoTracks()[0]?.getSettings().displaySurface;if(surface!=='monitor'){message('Для этого режима выбери демонстрацию всего экрана, а не окна или вкладки.',true);sendExtension('stop');extSessionId=null;return;}}
  if($('require-native').checked){starting=true;try{await native.start(crypto.randomUUID());}catch(error){message(error.message,true);sendExtension('stop');extSessionId=null;return;}finally{starting=false;}}
  session.start({work:$('work').value,variant:Number($('variant').value),strict:$('strict-mode').checked,integrity:$('integrity-mode').checked,count:Number($('question-count').value),duration:Number($('duration').value),fullscreen:$('require-fullscreen').checked,clipboard:$('block-clipboard').checked});
  completedNative=null;Object.assign(session.config,{nativeRequired:$('require-native').checked,faceCheck:$('use-face').checked,recordLocal:$('record-local').checked});
  recording.items=[];$('download-recordings').disabled=true;$('record-state').textContent='Выключена';
  if($('require-native').checked){native.flush();native.beginPolling();}
  face.policy.reset();
  if($('record-local').checked){try{recording.start([['camera',media.camera||media.mic],['screen',media.screen]]);}catch(error){log('recording_error','warning',error.message);}}
  $('probe-result').textContent='Проба скрипта ещё не проводилась.';
  controls.forEach(id=>$(id).disabled=true);$('finish').disabled=false;$('result').classList.add('hidden');document.body.classList.add('exam-active');
  $('session-status').textContent='Сеанс идёт';$('session-substatus').textContent='Наблюдение за событиями включено';$('status-dot').classList.add('active');$('monitor-pill').textContent='НАБЛЮДЕНИЕ';$('monitor-pill').classList.add('active');
  applyLock();renderQuestions();renderLog();updateMonitor();$('timer').textContent=formatTime(session.remaining());
}
async function finish(reason='manual'){
  if(probe)endProbe();
  const report=session.finish(reason);if(!report)return;await native.stop();completedNative=native.value?structuredClone(native.value):null;recording.stop();sendExtension('stop');extSessionId=null;applyLock();
  $('finish').disabled=true;controls.forEach(id=>$(id).disabled=false);document.body.classList.remove('exam-active');$('start').textContent='Начать новый сеанс →';
  $('session-status').textContent='Сеанс завершён';$('session-substatus').textContent='Отчёт доступен для скачивания';$('status-dot').classList.remove('active');$('monitor-pill').textContent='ЗАВЕРШЁН';$('monitor-pill').classList.remove('active');
  stopMedia();renderQuestions();renderLog();
  const result=$('result');result.replaceChildren();
  const h=document.createElement('h2');h.textContent='Тренировка завершена';
  const score=document.createElement('div');score.className='score';score.textContent=`${report.score} / ${report.total}`;
  const p=document.createElement('p');p.textContent=`Правильных ответов. Замечаний браузера: ${report.warnings}. Это сигналы для проверки, а не заключение о нарушении.`;
  const row=document.createElement('div');row.className='result-row';
  for(const answer of report.results){const item=document.createElement('div');item.textContent=`${answer.id}: выбран ${answer.selected||'—'}`;const strong=document.createElement('strong');strong.textContent=`Верный вариант: ${answer.correct}`;item.append(strong);const explanation=document.createElement('p');explanation.textContent=session.questions.find(q=>q.id===answer.id)?.explanation||'';item.append(explanation);row.append(item);}
  const note=document.createElement('p');note.textContent='Отсутствие замечаний здесь не доказывает незаметность для OES. Камера, микрофон и экран отключены.';
  result.append(h,score,p,row,note);result.classList.remove('hidden');
  if(document.fullscreenElement)await document.exitFullscreen().catch(()=>{});
}
async function toggleFullscreen(){
  try{if(document.fullscreenElement)await document.exitFullscreen();else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();else message('Браузер не поддерживает полный экран. Отключи обязательный полный экран для этого устройства.',true);}
  catch{message('Не удалось включить полный экран. Нажми кнопку ещё раз в обычном браузере.',true);}
}
function exportReport(){
  const blob=new Blob([JSON.stringify({...session.report(),schemaVersion:4,native:completedNative||native.value,faceCheck:{enabled:!!session.config.faceCheck,identityVerification:false},localRecordings:recording.items.map(x=>({name:x.name,bytes:x.blob.size})),limitations:'Local training evidence only. No OES equivalence, universal screenshot detection or anti-spoof guarantee. Native process list is based on names. No remote attestation. Recordings remain local.'},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`proctor-lab-${new Date().toISOString().replaceAll(':','-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
for(const type of ['copy','cut','paste','contextmenu'])document.addEventListener(type,event=>{
  if(session.state!=='active')return;
  if(session.config.clipboard)event.preventDefault();
  log(type,'warning',session.config.clipboard?'Действие предотвращено страницей':'Только наблюдение');
},true);
document.addEventListener('keydown',event=>{if(session.state==='active'&&!event.repeat&&(isMonitoredShortcut(event)||event.code==='F12'))log('shortcut','warning',shortcutLabel(event));},true);
window.addEventListener('blur',()=>{log('blur');updateMonitor();});window.addEventListener('focus',()=>{log('focus','info');updateMonitor();});
document.addEventListener('visibilitychange',()=>{log(document.hidden?'hidden':'visible',document.hidden?'warning':'info');updateMonitor();});
document.addEventListener('fullscreenchange',()=>{log(document.fullscreenElement?'fullscreen_enter':'fullscreen_exit',document.fullscreenElement||!session.config.fullscreen?'info':'warning');updateMonitor();});
window.addEventListener('pagehide',()=>{sendExtension('stop');native.stop();stopMedia();});
window.addEventListener('beforeunload',event=>{if(session.state==='active'){event.preventDefault();event.returnValue='';}});
$('question-count').addEventListener('change',()=>{if(session.state!=='active'){session=new Session();$('result').classList.add('hidden');renderQuestions();renderLog();}});
$('duration').addEventListener('change',()=>{if(session.state!=='active')$('timer').textContent=formatTime(Number($('duration').value));});
for(const id of ['use-camera','use-mic','use-screen'])$(id).addEventListener('change',()=>{stopMedia();message('Выбор изменён. Подключи источники заново, если они нужны.');});
$('connect-media').addEventListener('click',connectMedia);$('fullscreen').addEventListener('click',toggleFullscreen);$('start').addEventListener('click',start);$('finish').addEventListener('click',()=>finish());$('export').addEventListener('click',exportReport);
$('help-open').addEventListener('click',()=>$('help').showModal());$('help-close').addEventListener('click',()=>$('help').close());$('help-done').addEventListener('click',()=>$('help').close());
setInterval(()=>{if(session.state!=='active')return;const remaining=session.remaining();$('timer').textContent=formatTime(remaining);$('timer').parentElement.classList.toggle('urgent',remaining<=30);if(remaining<=0)finish('timeout');},250);
$('work-title').textContent=WORKS[$('work').value].title;renderQuestions();updateMonitor();

let extSessionId=null,extLastSeen=0,extSeq=0,extensionReady=false,extActive=false,extWait=null;
const extensionEvents=new Set(['extension_new_tab','extension_tab_switch','extension_window_blur','extension_navigation']);
function sendExtension(action){window.postMessage({source:'proctor-lab-page',action,sessionId:extSessionId,returnTab:$('return-tab').checked},location.origin);}
async function startExtension(){extSessionId=crypto.randomUUID();extSeq=0;const wait=new Promise(resolve=>{extWait=resolve;setTimeout(()=>{if(extWait===resolve){extWait=null;resolve(false);}},2500);});sendExtension('start');return wait;}
window.addEventListener('message',event=>{
 if(event.source!==window||event.origin!==location.origin||event.data?.source!=='proctor-lab-extension')return;
 const {action,result}=event.data;if(!result||typeof result!=='object')return;
 if(result.version){extensionReady=true;extLastSeen=Date.now();$('extension-status').textContent='подключено '+result.version;}
 if((action==='poll'||action==='start')&&result.sessionId===extSessionId)extActive=result.active===true;
 if(action==='poll'&&session.state==='active'&&$('require-extension').checked&&result.active!==true){extActive=false;log('extension_lost');return;}
 if(action==='start'&&extWait){const resolve=extWait;extWait=null;resolve(result.active===true&&result.sessionId===extSessionId);}
 if(session.state!=='active'||!$('require-extension').checked||result.sessionId!==extSessionId)return;
 if(result.active===false||result.error){log('extension_lost');return;}
 for(const e of (action==='event'?[result.event]:result.events||[])){
  if(e&&Number.isInteger(e.seq)&&e.seq>extSeq&&extensionEvents.has(e.type)){extSeq=e.seq;log(e.type,'warning',String(e.detail||'').slice(0,160));}
 }
});
setInterval(()=>{sendExtension(extSessionId?'poll':'hello');if(session.state==='active'&&$('require-extension').checked&&Date.now()-extLastSeen>10000)log('extension_lost');},3000);
sendExtension('hello');
for(const id of ['work','variant'])$(id).addEventListener('change',()=>{if(session.state!=='active'){session=new Session();$('work-title').textContent=WORKS[$('work').value].title;$('result').classList.add('hidden');applyLock();renderQuestions();renderLog();}});
$('resume').addEventListener('click',()=>{
 if(document.hidden||!document.hasFocus()){return;}
 if(session.config.fullscreen&&!document.fullscreenElement){$('lock-reason').textContent='Восстанови полный экран кнопкой ниже.';return;}
 for(const [id,kind,track]of [['use-camera','camera','video'],['use-mic','mic','audio'],['use-screen','screen','video']])if($(id).checked&&!hasLiveTrack(media[kind],track)){message('Источник остановлен. Заверши сеанс и подключи источники заново.',true);return;}
 if($('use-face').checked&&!face.healthy()){$('lock-reason').textContent='Нужно одно обнаруженное лицо и обновляющийся видеопоток.';return;}
 if($('require-native').checked&&(!native.healthy()||native.value.sensors.blocked_processes?.length||native.value.sensors.monitors!==1||native.value.sensors.removable_drives?.length)){$('lock-reason').textContent='Контроль Windows не восстановлен или остаются запрещённые условия.';return;}
 if($('require-extension').checked&&(!extensionReady||!extActive||Date.now()-extLastSeen>7000)){$('lock-reason').textContent='Связь с расширением не восстановлена. Заверши сеанс и подключи расширение заново.';return;}
 session.resume();applyLock();renderQuestions();renderLog();
});

$('restore-fullscreen').addEventListener('click',toggleFullscreen);

$('maximum-mode').addEventListener('click',()=>{if(session.state==='active')return;for(const id of ['require-fullscreen','block-clipboard','strict-mode','require-extension','return-tab','use-camera','use-mic','use-screen','use-face','record-local','require-native'])$(id).checked=true;stopMedia();message('Выбраны максимальные условия. Подключи компонент Windows и расширение, затем камеру/микрофон/весь экран. Будет включена локальная запись.');});

function beginProbe(){
  if(session.state!=='active'||session.paused||probe)return;
  log('probe_start','info','Ручная проба внешней программы');
  probe={afterSeq:session.sequence,startedAt:new Date().toISOString()};
  $('probe-result').textContent='Выполни действие скриптом, затем нажми «Закончить пробу». Сайт не запускает программу и не получает её снимки.';
  syncGuard();
}
function endProbe(){
  if(!probe)return;
  const result=summarizeProbe(session.events,probe.afterSeq,{startedAt:probe.startedAt,endedAt:new Date().toISOString()});
  result.nativeAttached=!!native.sessionId;result.osProcesses=native.sessionId?'named_processes_observed':'not_observable';result.nativeSeq=native.seq;
  session.probes.push(result);probe=null;
  $('probe-result').textContent=result.conclusion+(native.sessionId?' Дополнительно приложены события компонента Windows.':' Компонент Windows в этой пробе не подключён.');
  log('probe_end','info',result.status==='events_observed'?'Замечены события':result.status==='incomplete'?'Неполный журнал':'Событий не замечено');syncGuard();
}
$('probe-start').addEventListener('click',beginProbe);$('probe-stop').addEventListener('click',endProbe);
for(const [id,kind] of [['check-dom','dom'],['check-input','input'],['check-csp','csp']])$(id).addEventListener('click',()=>{
  if(session.state!=='active'||session.paused||!session.config.integrity)return;
  log('sensor_test','info','Контрольная проба датчика: '+kind);
  if(kind==='dom'){$('questions').querySelector('.question-title').append(' · контрольная подмена');}
  else if(kind==='input'){$('questions').querySelector('input').dispatchEvent(new Event('change',{bubbles:true}));}
  else{const script=document.createElement('script');script.textContent='void 0;';document.head.append(script);setTimeout(()=>script.remove(),100);}
});
$('maximum-mode').addEventListener('click',()=>{$('integrity-mode').checked=true;});
