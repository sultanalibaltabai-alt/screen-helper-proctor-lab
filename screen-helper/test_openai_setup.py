import io,json,unittest,urllib.error
from unittest.mock import patch
import helper

class OpenAISetupTests(unittest.TestCase):
 def test_openai_image_response_uses_official_endpoint_and_reports_actual_usage(self):
  body={'status':'completed','model':'gpt-5.4-mini-2026-03-17','usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150},'output':[{'type':'message','content':[{'type':'output_text','text':'B'}]}]}
  metrics={}
  with patch('api_transport.open_request',return_value=io.BytesIO(json.dumps(body).encode())) as send:
   self.assertEqual(helper.ask(b'fake-image',{'api_key':'sk-FAKE-KEY','provider_mode':'openai','model':'gpt-5.4-mini','_metrics':metrics}),'B')
  request=send.call_args.args[0];payload=json.loads(request.data)
  self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
  self.assertEqual(request.get_header('Authorization'),'Bearer sk-FAKE-KEY')
  self.assertNotIn('sk-FAKE',request.full_url);self.assertFalse(payload['store'])
  self.assertEqual(payload['reasoning']['effort'],'medium')
  self.assertEqual(metrics['tokens'],{'input_tokens':100,'output_tokens':50,'total_tokens':150})
 def test_openai_insufficient_balance_is_not_retried_or_confused_with_rate_limit(self):
  for code,expected in [('insufficient_quota','API: billing/quota'),('rate_limit_exceeded','API: rate limit (429)')]:
   error=urllib.error.HTTPError('https://api.openai.com/v1/responses',429,'limit',{},io.BytesIO(json.dumps({'error':{'code':code,'message':'PRIVATE REMOTE BODY'}}).encode()))
   with patch('api_transport.open_request',side_effect=error) as send:
    self.assertEqual(helper.ask(b'test',{'api_key':'sk-FAKE','provider_mode':'openai'}),expected)
   self.assertEqual(send.call_count,1)
 def test_reasoning_compatibility_does_not_add_parameters_to_unrelated_models(self):
  self.assertNotIn('reasoning',helper.payload(b'x','gpt-4.1-mini'))
  self.assertNotIn('reasoning',helper.payload(b'x','gpt-5.4-mini','auto'))
  self.assertEqual(helper.payload(b'x','gpt-5.4-mini','deep')['reasoning']['effort'],'high')
 def test_incomplete_or_refused_response_is_not_presented_as_an_answer(self):
  self.assertEqual(helper.extract_answer({'status':'failed','output':[]}),'API: response not completed')
  self.assertEqual(helper.extract_answer({'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'test'}]}]}),'API: refusal')

if __name__=='__main__':unittest.main()
