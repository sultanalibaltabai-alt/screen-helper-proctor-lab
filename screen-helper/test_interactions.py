import io,json,os,unittest,urllib.error
from unittest.mock import patch
import helper

class InteractionTests(unittest.TestCase):
 def test_full_client_recovers_from_one_503_without_changing_model_or_reasoning(self):
  error=urllib.error.HTTPError('https://example.test',503,'busy',{},io.BytesIO(b'{}'))
  body={'status':'completed','model':'gemini-3.5-flash','steps':[{'type':'model_output','content':[{'type':'text','text':'B'}]}]}
  metrics={}
  with patch('urllib.request.urlopen',side_effect=[error,io.BytesIO(json.dumps(body).encode())]) as send,patch('api_transport.time.sleep'):
   self.assertEqual(helper.ask(b'test',{'api_key':'AQ.FAKE','model':'gemini-3.5-flash','_metrics':metrics}),'B')
  self.assertEqual(send.call_count,2)
  self.assertEqual(json.loads(send.call_args.args[0].data)['generation_config']['thinking_level'],'medium')
  self.assertEqual(metrics['transport_retry_count'],1);self.assertEqual(metrics['model_returned'],'gemini-3.5-flash')
 def test_provider_high_demand_is_reported_only_when_explicitly_returned(self):
  for message,expected in [('Model is currently experiencing high demand','API: Gemini перегружен (503)'),('Service unavailable','API: service unavailable (503)')]:
   error=urllib.error.HTTPError('https://example.test',503,'unavailable',{},io.BytesIO(json.dumps({'error':{'message':message}}).encode()))
   metrics={}
   with patch.object(helper,'request_json',side_effect=error):
    self.assertEqual(helper.ask(b'test',{'api_key':'AQ.FAKE','_metrics':metrics}),expected)
   self.assertEqual(metrics['http_status'],503)
 def test_payload_uses_current_image_and_schema_contract_without_server_history(self):
  data=helper.interactions_payload(b'fake-image','gemini-3.8-flash')
  self.assertFalse(data['store']);self.assertEqual(data['input'][1]['mime_type'],'image/png')
  self.assertEqual(data['response_format']['mime_type'],'application/json')
  self.assertIs(data['response_format']['schema'],helper.ANSWER_SCHEMA)
  self.assertEqual(data['generation_config']['thinking_level'],'medium')
  self.assertNotIn('max_output_tokens',data.get('generation_config',{}))
 def test_only_completed_model_text_is_used_not_input_or_thought_steps(self):
  response={'status':'completed','steps':[{'type':'user_input','content':[{'type':'text','text':'D'}]},
      {'type':'thought','content':[{'type':'text','text':'private reasoning'}]},
      {'type':'model_output','content':[{'type':'text','text':'{"answers":['},{'type':'text','text':'{"question":"1","answer":"B","option_labels":["A","B","C","D"]}]}'}]}]}
  self.assertEqual(helper.extract_interactions_answer(response),'B')
  response['status']='in_progress';self.assertEqual(helper.extract_interactions_answer(response),'API: response not completed')
  response['status']='failed';self.assertEqual(helper.extract_interactions_answer(response),'API: generation failed')
 def test_request_routes_new_google_auth_keys_to_interactions(self):
  response={'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'B'}]}]}
  with patch.dict(os.environ,{},clear=True),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as send:
   self.assertEqual(helper.ask(b'fake-image',{'api_key':'AQ.FAKE-KEY','model':'gemini-3.8-flash','streaming':True}),'B')
  request=send.call_args.args[0]
  self.assertEqual(request.full_url,'https://generativelanguage.googleapis.com/v1beta/interactions')
  self.assertEqual(request.get_header('Api-revision'),'2026-05-20')
  self.assertEqual(request.get_header('X-goog-api-key'),'AQ.FAKE-KEY')
  self.assertFalse(json.loads(request.data)['store'])
 def test_classic_transport_remains_explicitly_available(self):
  config=helper.normalize_config({'api_key':'AQ.FAKE','gemini_api':'generate_content','streaming':True})
  self.assertTrue(config['streaming']);self.assertEqual(config['gemini_api'],'generate_content')
  self.assertFalse(helper.normalize_config({'api_key':'AQ.FAKE','streaming':True})['streaming'])
if __name__=='__main__':unittest.main()
