export const NATIVE_EVENTS=new Set(['native_start','native_stop','native_process','native_monitors','native_display_change','native_foreground','native_overlay','native_clipboard','native_removable','native_sensor_error']);
export class NativeClient {
  constructor({onState=()=>{},onEvent=()=>{},onLost=()=>{},fetcher=(...args)=>globalThis.fetch(...args)}={}){Object.assign(this,{onState,onEvent,onLost,fetcher});this.token='';this.value=null;this.sessionId=null;this.seq=0;this.timer=0;this.busy=false;this.lastSeen=0;}
  async request(path,body){
    const response=await this.fetcher('http://127.0.0.1:8771/api/'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+this.token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,cache:'no-store',credentials:'omit',redirect:'error',signal:AbortSignal.timeout(3000)});
    if(!response.ok)throw new Error(response.status===401?'Неверный код связи':response.status===403?'Этот домен не разрешён компонентом Windows':'Компонент отклонил запрос ('+response.status+')');
    const value=await response.json();if(value.version!=='3.0.0'||!value.sensors||!Array.isArray(value.events))throw new Error('Несовместимый компонент Windows');
    this.value=value;this.lastSeen=Date.now();this.onState(value);return value;
  }
  async connect(token){this.token=String(token).trim();if(!this.token)throw new Error('Вставь код из окна Proctor Lab Windows');const value=await this.request('status');if(!value.consent)throw new Error('Включи разрешение контроля в окне программы Windows');return value;}
  async start(sessionId){this.seq=0;this.sessionId=sessionId;try{return await this.request('start',{sessionId});}catch(error){this.sessionId=null;throw error;}}
  flush(){if(this.value?.sessionId!==this.sessionId)return;for(const event of this.value.events){if(Number.isInteger(event.seq)&&event.seq>this.seq&&NATIVE_EVENTS.has(event.type)){this.seq=event.seq;this.onEvent(event);}}}
  beginPolling(){clearInterval(this.timer);this.timer=setInterval(()=>this.poll(),1500);}
  async poll(){if(!this.sessionId||this.busy)return;this.busy=true;try{const value=await this.request('poll',{sessionId:this.sessionId});if(!value.active||value.sessionId!==this.sessionId)throw new Error('Контроль Windows остановлен');this.flush();}catch(error){this.onLost(error.message);}finally{this.busy=false;}}
  async stop(){clearInterval(this.timer);this.timer=0;const sessionId=this.sessionId;this.sessionId=null;if(sessionId)try{await this.request('stop',{sessionId});}catch{} }
  healthy(){return this.value?.consent&&this.value?.active&&this.value.sessionId===this.sessionId&&Date.now()-this.lastSeen<5000;}
}

export class FacePolicy {
  constructor({clock=()=>performance.now(),onSignal=()=>{}}={}){this.clock=clock;this.onSignal=onSignal;this.reset();}
  reset(){this.problem=null;this.since=0;this.lastSignal=-Infinity;this.lastFrame=0;this.lastVideoTime=-1;}
  observe(count,videoTime){
    const now=this.clock();if(videoTime!==this.lastVideoTime){this.lastVideoTime=videoTime;this.lastFrame=now;}
    const problem=now-this.lastFrame>5000?'camera_frozen':count===0?'face_missing':count>1?'multiple_faces':null;
    if(problem!==this.problem){this.problem=problem;this.since=now;}
    const wait=problem==='multiple_faces'?1500:4000;
    if(problem&&now-this.since>=wait&&now-this.lastSignal>10000){this.onSignal(problem,problem==='multiple_faces'?'В кадре более одного лица':problem==='camera_frozen'?'Видеокадр не обновляется':'Лицо не обнаружено более 4 секунд');this.lastSignal=now;}
    return problem;
  }
}

export class FaceMonitor {
  constructor({onState=()=>{},onSignal=()=>{},active=()=>false}={}){Object.assign(this,{onState,onSignal,active});this.policy=new FacePolicy({onSignal});this.detector=null;this.timer=0;this.count=null;this.lastFrameAt=0;this.error=null;}
  async load(){
    if(this.detector)return;
    this.onState('Загрузка локальной модели…');
    const {FaceDetector,FilesetResolver}=await import('./vendor/mediapipe/vision_bundle.mjs');
    const files=await FilesetResolver.forVisionTasks(new URL('./vendor/mediapipe/wasm',import.meta.url).href);
    this.detector=await FaceDetector.createFromOptions(files,{baseOptions:{modelAssetPath:new URL('./vendor/mediapipe/blaze_face_short_range.tflite',import.meta.url).href,delegate:'CPU'},runningMode:'VIDEO',minDetectionConfidence:.6});
    this.error=null;this.onState('Модель готова · кадры обрабатываются на устройстве');
  }
  start(video){
    this.stop();this.policy.reset();let last=-1;
    this.timer=setInterval(()=>{
      if(!this.detector||video.readyState<2)return;
      try{
        if(last!==video.currentTime){const value=this.detector.detectForVideo(video,performance.now());this.count=value.detections.length;last=video.currentTime;this.lastFrameAt=Date.now();}
        this.onState('Лиц в кадре: '+this.count);
        if(this.active())this.policy.observe(this.count,video.currentTime);else this.policy.reset();
      }catch(error){if(!this.error&&this.active())this.onSignal('face_error','Локальная модель не смогла обработать кадр');this.error=error.name||'Ошибка модели';this.onState('Проверка лица недоступна');}
    },500);
  }
  healthy(){return this.detector&&!this.error&&this.count===1&&Date.now()-this.lastFrameAt<4000;}
  stop(){clearInterval(this.timer);this.timer=0;this.count=null;this.lastFrameAt=0;}
}

export class LocalRecording {
  constructor(onState=()=>{},onError=()=>{}){this.onState=onState;this.onError=onError;this.items=[];this.recorders=[];this.bytes=0;this.failed=false;}
  supported(){return typeof MediaRecorder!=='undefined';}
  start(streams){
    if(!this.supported())throw new Error('MediaRecorder не поддерживается');
    this.items=[];this.recorders=[];this.bytes=0;this.failed=false;
    const mime=['video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
    if(!mime)throw new Error('Нет поддерживаемого формата записи');
    try{for(const [name,stream]of streams){if(!stream)continue;const chunks=[];const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:600000});
      recorder.ondataavailable=event=>{if(event.data.size){chunks.push(event.data);this.bytes+=event.data.size;}if(this.bytes>128*1024*1024&&!this.failed){this.failed=true;this.onError('Достигнут лимит памяти локальной записи (128 МБ)');this.stop();}};
      recorder.onerror=()=>{if(!this.failed){this.failed=true;this.onError('Браузер сообщил об ошибке локальной записи');this.stop();}};
      recorder.onstop=()=>{this.items.push({name,blob:new Blob(chunks,{type:recorder.mimeType})});this.onState('Записей готово: '+this.items.length);};
      this.recorders.push(recorder);recorder.start(1000);}
    }catch(error){this.stop();throw error;}
    if(!this.recorders.length)throw new Error('Для записи нужны выбранные источники');
    this.onState('Идёт локальная запись · ограничение 10 минут');
  }
  stop(){for(const recorder of this.recorders)if(recorder.state!=='inactive')recorder.stop();this.recorders=[];}
  download(){for(const item of this.items){const url=URL.createObjectURL(item.blob);const a=document.createElement('a');a.href=url;a.download='proctor-'+item.name+(item.blob.type.includes('mp4')?'.mp4':'.webm');a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}}
}
