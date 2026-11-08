import io,json,unittest,urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from api_transport import request_gemini_stream
from progress import RequestProgress,save_status

def frame(text='',finish=None,**extra):
 candidate={'content':{'parts':[{'text':text}]},'index':0}
 if finish:candidate['finishReason']=finish
 return ('data: '+json.dumps({'candidates':[candidate],**extra},ensure_ascii=False)+'\r\n\r\n').encode('utf-8')

class StreamProgressTests(unittest.TestCase):
 def test_stream_assembles_fragments_inside_json_strings_exactly(self):
  chunks=frame('{"ans')+frame('wers":[{"answer":"Б"}]}','STOP')
  stages=[]
  with patch('api_transport.open_request',return_value=io.BytesIO(chunks)):
   data=request_gemini_stream('https://example.test',on_progress=stages.append)
  self.assertEqual(json.loads(data['candidates'][0]['content']['parts'][0]['text']),{'answers':[{'answer':'Б'}]})
  self.assertEqual(data['candidates'][0]['finishReason'],'STOP')
  self.assertEqual(data['_stream_chunks'],2);self.assertIn('receiving',stages)
 def test_truncated_stream_is_not_a_completed_answer(self):
  with patch('api_transport.open_request',return_value=io.BytesIO(frame('B'))):
   self.assertEqual(request_gemini_stream('https://example.test')['candidates'][0]['finishReason'],'INCOMPLETE')
 def test_error_after_partial_data_is_not_retried(self):
  raw=frame('partial')+b'data: {"error":{"code":503}}\n\n'
  with patch('api_transport.open_request',return_value=io.BytesIO(raw)) as send:
   with self.assertRaises(urllib.error.HTTPError):request_gemini_stream('https://example.test')
   self.assertEqual(send.call_count,1)
 def test_thought_text_is_not_included_in_answer(self):
  raw=b'data: {"candidates":[{"content":{"parts":[{"text":"private reasoning","thought":true}]}}]}\n\n'+frame('B','STOP')
  with patch('api_transport.open_request',return_value=io.BytesIO(raw)):
   self.assertEqual(request_gemini_stream('https://example.test')['candidates'][0]['content']['parts'][0]['text'],'B')
 def test_status_tracks_time_and_stops_at_completion(self):
  now=[10.0];state=RequestProgress(7,clock=lambda:now[0]);now[0]=15.0;state.update('request')
  self.assertEqual(state.snapshot()['elapsed_seconds'],5);self.assertEqual('5',state.text())
  now[0]=17.0;state.update('done');now[0]=50
  self.assertEqual(state.snapshot()['elapsed_seconds'],7);self.assertEqual(state.snapshot()['state'],'done')
  with TemporaryDirectory() as folder:
   path=Path(folder)/'status.json';save_status(path,state.snapshot());self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['request_id'],7)
if __name__=='__main__':unittest.main()
