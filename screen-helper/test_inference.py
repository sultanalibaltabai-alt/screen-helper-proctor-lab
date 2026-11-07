import multiprocessing as mp
import threading,time,unittest
import uuid
from unittest.mock import patch
from inference import execute,offline_probe,RequestCancelled,RequestDeadline,RequestBusy,request_lock
from routing import InferenceRouter

def wait_probe(connection,image,config):
 try:connection.send(('progress','request'))
 except (BrokenPipeError,EOFError,OSError):return
 time.sleep(10)

class ManagedInferenceTests(unittest.TestCase):
 def setUp(self):
  mutex=patch('inference.REQUEST_MUTEX_NAME','Local\\ScreenHelperTest-'+uuid.uuid4().hex)
  mutex.start();self.addCleanup(mutex.stop)
 def test_child_completes_and_does_not_remain_running(self):
  before={p.pid for p in mp.active_children()}
  answer,metrics=execute(b'',{},timeout=5,target=offline_probe)
  self.assertEqual(answer,'SELF-CHECK');self.assertTrue(metrics['offline_test'])
  self.assertEqual({p.pid for p in mp.active_children()},before)
 def test_deadline_really_terminates_a_blocked_child(self):
  started=time.monotonic()
  with self.assertRaises(RequestDeadline):execute(b'',{},timeout=.4,target=wait_probe)
  self.assertLess(time.monotonic()-started,3)
  self.assertFalse(mp.active_children())
 def test_cancel_stops_a_running_child_without_waiting_for_its_network_deadline(self):
  cancel=threading.Event();started=time.monotonic()
  with self.assertRaises(RequestCancelled):
   execute(b'',{},timeout=10,cancel=cancel,on_progress=lambda phase:cancel.set(),target=wait_probe)
  self.assertLess(time.monotonic()-started,3);self.assertFalse(mp.active_children())
 def test_paid_request_lock_rejects_a_second_caller(self):
  blocked=[]
  def other_thread():
   try:
    with request_lock():blocked.append(False)
   except RequestBusy:blocked.append(True)
  with request_lock():
   thread=threading.Thread(target=other_thread);thread.start();thread.join(2)
  self.assertEqual(blocked,[True])

class RoutingTests(unittest.TestCase):
 def config(self,**extra):return dict(provider='gemini',api_key='AQ.FAKE',model='primary',request_timeout=60,reasoning_mode='auto',**extra)
 def test_fallback_only_for_transient_failure_and_model_used_is_reported(self):
  calls=[]
  def runner(image,config,**options):
   calls.append((config['model'],options['timeout']))
   return ('API: unavailable',{'http_status':503}) if config['model']=='primary' else ('B',{})
  router=InferenceRouter(runner=runner)
  answer,metrics=router.run(b'test',self.config(fallback_model='reserve'))
  self.assertEqual(answer,'B');self.assertEqual(metrics['model_used'],'reserve');self.assertEqual([m for m,t in calls],['primary','reserve'])
  self.assertLessEqual(calls[0][1],36)
 def test_quota_does_not_trigger_model_hopping(self):
  calls=[]
  def runner(image,config,**options):calls.append(config['model']);return 'API: quota/limit',{'http_status':429}
  answer,_=InferenceRouter(runner=runner).run(b'test',self.config(fallback_model='reserve'))
  self.assertEqual(answer,'API: quota/limit');self.assertEqual(calls,['primary'])
 def test_gemini_25_reserve_uses_compatible_endpoint_and_keeps_primary_reasoning(self):
  calls=[]
  def runner(image,config,**options):
   calls.append((config,options['timeout']))
   return ('API: unavailable',{'http_status':503}) if len(calls)==1 else ('B',{})
  answer,_=InferenceRouter(runner=runner).run(b'test',self.config(fallback_model='gemini-2.5-flash',gemini_api='interactions'))
  self.assertEqual(answer,'B');self.assertLessEqual(calls[0][1],15)
  self.assertEqual(calls[1][0]['gemini_api'],'generate_content')
  self.assertEqual(calls[1][0]['reasoning_mode'],'auto')
 def test_overload_cooldown_and_credential_change(self):
  now=[100];calls=[]
  def runner(image,config,**options):calls.append(1);return 'API: unavailable',{'http_status':503}
  router=InferenceRouter(runner=runner,clock=lambda:now[0]);config=self.config()
  router.run(b'one',config);answer,_=router.run(b'two',config)
  self.assertEqual(len(calls),1);self.assertIn('повтор через',answer)
  config['api_key']='AQ.OTHER-FAKE';router.run(b'two',config);self.assertEqual(len(calls),2)
 def test_exact_image_cache_does_not_reuse_an_answer_for_a_changed_image(self):
  calls=[]
  def runner(*args,**kwargs):calls.append(1);return 'B',{}
  router=InferenceRouter(runner=runner);config=self.config()
  router.run(b'image1',config);answer,metrics=router.run(b'image1',config)
  self.assertEqual(answer,'B');self.assertTrue(metrics['cache_hit']);self.assertEqual(len(calls),1)
  router.run(b'image2',config);self.assertEqual(len(calls),2)

if __name__=='__main__':unittest.main()
