import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from benchmark import run
class BenchmarkTests(unittest.TestCase):
 def test_missing_openai_is_not_scored_and_quota_is_not_a_wrong_answer(self):
  with tempfile.TemporaryDirectory() as folder:
   Path(folder,'config.local.json').write_text(json.dumps({'api_key':'AIzaFAKE','model':'gemini-2.5-flash'}))
   with patch('helper.InferenceRouter.run',side_effect=[('B',{}),('API: quota/limit',{'http_status':429})]) as send:report=run(folder)
   self.assertEqual(report['providers']['openai']['status'],'not_configured')
   result=report['providers']['gemini'];self.assertEqual(result['answers_received'],1);self.assertEqual(result['api_errors'],1);self.assertEqual(result['correct'],1);self.assertEqual(send.call_count,2)
if __name__=='__main__':unittest.main()
