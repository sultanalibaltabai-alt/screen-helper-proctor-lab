import {Session} from './core.js';
import {FacePolicy,LocalRecording,NativeClient} from './supervision.js?v=3.0.1';
const $=id=>document.getElementById(id);
$('native-fetch-check').addEventListener('click',async()=>{
  $('native-fetch-check').disabled=true;$('native-fetch-result').textContent='Проверка сетевого вызова…';
  try{await new NativeClient().connect('connection-test-invalid-code');$('native-fetch-result').textContent='Неожиданный ответ: неверный код не должен приниматься.';}
  catch(error){
    const ok=error.message==='Неверный код связи';document.documentElement.dataset.nativeFetchCheck=ok?'passed':'failed';
    $('native-fetch-result').textContent=ok?'Компонент Windows ответил HTTP 401. Сетевой вызов работает; для подключения нужен настоящий код из программы. Контроль этим тестом не включался.':'Проверка не прошла: '+error.message;
  }finally{$('native-fetch-check').disabled=false;}
});
$('record-check').addEventListener('click',()=>{
  $('record-check').disabled=true;const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;
  const context=canvas.getContext('2d');let count=0;const paint=()=>{context.fillStyle=count++%2?'#264f3b':'#9fc5ab';context.fillRect(0,0,320,180);context.fillStyle='white';context.font='24px sans-serif';context.fillText('Proctor Lab test '+count,20,90);};paint();
  const stream=canvas.captureStream?.(10);if(!stream){$('record-result').textContent='captureStream недоступен';$('record-check').disabled=false;return;}
  const recorder=new LocalRecording(text=>{$('record-result').textContent=text;if(recorder.items.length){const video=$('record-preview');video.onloadeddata=()=>{$('record-result').textContent='Запись создана и воспроизведена: '+recorder.items[0].blob.size+' байт, '+video.videoWidth+' × '+video.videoHeight+'. Камера и экран пользователя не использовались.';document.documentElement.dataset.recordCheck='passed';$('record-check').disabled=false;};video.src=URL.createObjectURL(recorder.items[0].blob);video.play().catch(()=>{});}},message=>{$('record-result').textContent=message;document.documentElement.dataset.recordCheck='failed';$('record-check').disabled=false;});
  try{recorder.start([['test',stream]]);const interval=setInterval(paint,100);setTimeout(()=>{clearInterval(interval);recorder.stop();stream.getTracks().forEach(t=>t.stop());},2000);}catch(error){$('record-result').textContent=error.message;$('record-check').disabled=false;}
});
$('rules-check').addEventListener('click',()=>{
  const types=['native_process','native_monitors','native_lost','face_missing','multiple_faces','camera_frozen'];const result=[];
  for(const type of types){const session=new Session();session.start({strict:true});session.record(type);result.push(type+': '+(session.paused===type?'ПАУЗА — OK':'ОШИБКА'));}
  $('rules-result').textContent=result.join('\n');
});
$('vision-check').addEventListener('click',async()=>{
  $('vision-check').disabled=true;$('vision-result').textContent='Загрузка локального WebAssembly и модели…';let detector;
  try{
    const {FaceDetector,FilesetResolver}=await import('./vendor/mediapipe/vision_bundle.mjs');
    const files=await FilesetResolver.forVisionTasks(new URL('./vendor/mediapipe/wasm',import.meta.url).href);
    detector=await FaceDetector.createFromOptions(files,{baseOptions:{modelAssetPath:new URL('./vendor/mediapipe/blaze_face_short_range.tflite',import.meta.url).href,delegate:'CPU'},runningMode:'IMAGE',minDetectionConfidence:.6});
    const image=new Image();image.src='vision-test.jpg';await image.decode();
    const blank=document.createElement('canvas');blank.width=640;blank.height=480;blank.getContext('2d').fillRect(0,0,640,480);
    const count0=detector.detect(blank).detections.length;
    const single=detector.detect(image);const count1=single.detections.length;
    const double=document.createElement('canvas');double.width=800;double.height=450;const context=double.getContext('2d');context.fillStyle='#ddd';context.fillRect(0,0,800,450);
    if(single.detections[0]){const b=single.detections[0].boundingBox;const pad=.3;const x=Math.max(0,b.originX-b.width*pad),y=Math.max(0,b.originY-b.height*pad);const size=Math.min(image.width-x,image.height-y,Math.max(b.width,b.height)*(1+2*pad));context.drawImage(image,x,y,size,size,30,25,360,400);context.drawImage(image,x,y,size,size,410,25,360,400);}
    const count2=detector.detect(double).detections.length;
    const results=[{case:'Пустой кадр',expected:0,actual:count0},{case:'Одно лицо',expected:1,actual:count1},{case:'Два лица',expected:2,actual:count2}];
    $('vision-result').textContent=results.map(r=>`${r.case}: ${r.actual}, ожидается ${r.expected} — ${r.actual===r.expected?'OK':'НЕ СОВПАЛО'}`).join('\n')+'\nМодель выполнялась в этом браузере. Камера не включалась.';
    document.documentElement.dataset.visionCheck=results.every(r=>r.actual===r.expected)?'passed':'failed';
  }catch(error){$('vision-result').textContent='Проверка не прошла: '+error.message;document.documentElement.dataset.visionCheck='failed';}
  finally{detector?.close();$('vision-check').disabled=false;}
});
