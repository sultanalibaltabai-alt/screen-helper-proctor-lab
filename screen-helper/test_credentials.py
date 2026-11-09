import gc,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from credentials import clean_key,detect_provider,key_problem,select_provider
import helper

class CredentialTests(unittest.TestCase):
 def test_explicitly_saved_key_has_priority_over_an_old_environment_key(self):
  body={'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'B'}]}]}
  with patch.dict(os.environ,{'GEMINI_API_KEY':'AQ.OLD-FAKE'},clear=True),patch('api_transport.open_request',return_value=io.BytesIO(json.dumps(body).encode())) as send:
   self.assertEqual(helper.ask(b'test',{'api_key':'AQ.SAVED-FAKE','provider_mode':'gemini'}),'B')
  self.assertEqual(send.call_args.args[0].get_header('X-goog-api-key'),'AQ.SAVED-FAKE')
 def test_google_auth_keys_fix_the_old_openai_model_selection(self):
  for key in ('AIzaFAKE','AQ.FAKE-AUTH-KEY'):
   config=helper.normalize_config({'api_key':key,'provider':'openai','model':'gpt-4.1-mini'})
   self.assertEqual(config['provider'],'gemini');self.assertEqual(config['model'],helper.DEFAULT_MODELS['gemini'])
 def test_unknown_key_formats_can_use_an_explicit_provider(self):
  config=helper.normalize_config({'api_key':'FUTURE_FAKE_FORMAT','provider_mode':'gemini','model':'gpt-4.1-mini'})
  self.assertEqual(config['provider'],'gemini');self.assertEqual(config['model'],helper.DEFAULT_MODELS['gemini'])
  self.assertIsNone(key_problem(config['api_key']))
 def test_new_auth_key_is_sent_only_in_the_google_header(self):
  with patch.dict(os.environ,{},clear=True),patch('api_transport.open_request',return_value=io.BytesIO(b'{"status":"completed","steps":[{"type":"model_output","content":[{"type":"text","text":"B"}]}]}')) as send:
   self.assertEqual(helper.ask(b'fake-image',{'api_key':'AQ.FAKE-AUTH-KEY','model':'gpt-4.1-mini'}),'B')
  request=send.call_args.args[0]
  self.assertTrue(request.full_url.startswith('https://generativelanguage.googleapis.com/'))
  self.assertEqual(request.get_header('X-goog-api-key'),'AQ.FAKE-AUTH-KEY')
  self.assertNotIn('AQ.FAKE',request.full_url);self.assertIsNone(request.get_header('Authorization'))
 def test_wrong_explicit_service_does_not_receive_a_recognized_key(self):
  with patch('api_transport.open_request') as send:
   self.assertEqual(helper.ask(b'fake-image',{'api_key':'AQ.FAKE','provider_mode':'openai'}),'API: key/provider mismatch')
   send.assert_not_called()
 def test_pasted_quotes_and_bom_are_cleaned_but_masked_keys_are_rejected(self):
  self.assertEqual(clean_key('\ufeff  "AQ.FAKE"  '),'AQ.FAKE')
  for key in ('***','AQ.XXX…','AQ.bad\nheader','AQ.bad header',''):
   self.assertIsNotNone(key_problem(key))
  self.assertIsNone(key_problem('AQ.FAKE_-+.abc'))
 def test_setup_saves_new_google_auth_key_and_corrected_model(self):
  import tkinter as tk
  root=tk.Tk();root.withdraw()
  def descendants(widget):
   for child in widget.winfo_children():
    yield child;yield from descendants(child)
  def fill_and_save():
   widgets=list(descendants(root))
   entry=next(w for w in widgets if isinstance(w,tk.Entry) and w.cget('show')=='*')
   entry.insert(0,'AQ.FAKE-GUI-KEY')
   next(w for w in widgets if isinstance(w,tk.Button) and w.cget('text')=='Сохранить').invoke()
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'config.local.json'
   try:
    with patch.object(helper,'CONFIG',path),patch.object(tk,'Tk',return_value=root),patch.object(root,'mainloop',side_effect=fill_and_save),patch('tkinter.messagebox.showinfo'),patch('tkinter.messagebox.showerror') as error:
     helper.configure_gui({'provider':'openai','model':'gpt-4.1-mini'})
    error.assert_not_called();config=helper.load_config(path)
    self.assertEqual(config['provider'],'gemini');self.assertEqual(config['model'],helper.DEFAULT_MODELS['gemini']);self.assertEqual(config['api_key'],'AQ.FAKE-GUI-KEY')
   finally:
    try:root.destroy()
    except tk.TclError:pass
  del root
  gc.collect()
if __name__=='__main__':unittest.main()
