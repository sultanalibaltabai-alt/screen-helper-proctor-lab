import io,json,unittest,urllib.error
from unittest.mock import patch
from PIL import Image
from api_transport import request_json
from capture import capture_image,CaptureError
class TransportTests(unittest.TestCase):
 def test_default_wait_has_no_local_deadline_and_completed_response_is_read(self):
  with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"answer":"B"}')) as send:
   self.assertEqual(request_json('https://example.test'),{'answer':'B'});self.assertIsNone(send.call_args.kwargs['timeout'])
 def test_optional_finite_timeout_remains_available(self):
  with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{}')) as send:
   request_json('https://example.test',timeout=180)
   self.assertGreater(send.call_args.kwargs['timeout'],179);self.assertLessEqual(send.call_args.kwargs['timeout'],180)
 def test_503_retries_once_then_succeeds(self):
  error=urllib.error.HTTPError('https://example.test',503,'busy',{},io.BytesIO(b'{}'))
  with patch('urllib.request.urlopen',side_effect=[error,io.BytesIO(b'{"ok":true}')]) as send,patch('api_transport.time.sleep') as sleep:
   self.assertEqual(request_json('https://example.test'),{'ok':True});self.assertEqual(send.call_count,2);sleep.assert_called_once_with(2)
 def test_quota_is_not_retried(self):
  with patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('https://example.test',429,'quota',{},None)) as send:
   with self.assertRaises(urllib.error.HTTPError):request_json('https://example.test')
   self.assertEqual(send.call_count,1)
 def test_repeated_503_is_bounded(self):
  with patch('urllib.request.urlopen',side_effect=lambda *a,**k: (_ for _ in ()).throw(urllib.error.HTTPError('https://example.test',503,'busy',{},None))) as send,patch('api_transport.time.sleep'):
   with self.assertRaises(urllib.error.HTTPError):request_json('https://example.test')
   self.assertEqual(send.call_count,2)
 def test_blank_screen_is_not_sent(self):
  with patch('PIL.ImageGrab.grab',return_value=Image.new('RGB',(100,100),'black')):
   with self.assertRaises(CaptureError):capture_image((0,0,100,100))
 def test_valid_image_and_secondary_monitor_coordinates(self):
  picture=Image.linear_gradient('L').convert('RGB')
  with patch('PIL.ImageGrab.grab',return_value=picture) as grab:
   self.assertEqual(capture_image((-1920,0,-920,900)).size,picture.size);grab.assert_called_once_with(bbox=(-1920,0,-920,900),all_screens=True)
if __name__=='__main__':unittest.main()
