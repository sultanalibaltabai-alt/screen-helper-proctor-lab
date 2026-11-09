import io,json,tempfile,time,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import cloud_client
import helper
from config_store import load_config

class CloudClientTests(unittest.TestCase):
    def image(self):
        data=io.BytesIO();Image.new('RGB',(100,100),'white').save(data,'PNG');return data.getvalue()
    def test_new_install_selects_cloud_without_a_provider_key(self):
        with tempfile.TemporaryDirectory() as folder:
            config=helper.load_active_config(Path(folder)/'config.local.json')
            self.assertEqual(config['provider'],'cloud');self.assertEqual(config['api_key'],'')
            self.assertEqual(config['api_retries'],0)
    def test_registration_is_automatic_device_token_is_encrypted_and_reused(self):
        token='STC_'+'a'*64
        result={'answers':[{'question':'1','answer':'B','option_labels':['A','B'],'solution':{'kind':'single_choice','selected_labels':['B'],'options':[{'label':'A','text':'3'},{'label':'B','text':'4'}]}}]}
        calls=[]
        def send(request,**options):
            calls.append(request);self.assertEqual(options['retries'],0)
            if request.full_url.endswith('/register'):return {'token':token,'expires_at':int((time.time()+3600)*1000)}
            self.assertEqual(request.get_header('Authorization'),'Bearer '+token)
            return {'result':result,'model':'server-model'}
        with tempfile.TemporaryDirectory() as folder,patch('cloud_client.request_json',side_effect=send):
            cfg=helper.normalize_config({'provider_mode':'cloud','api_key':'sk-FAKE-MUST-NOT-LEAVE-PC'})
            self.assertEqual(cloud_client.infer(self.image(),cfg,Path(folder),{}),'B) 4')
            self.assertEqual(cloud_client.infer(self.image(),cfg,Path(folder),{}),'B) 4')
            path=Path(folder)/'cloud-session.local.json'
            self.assertNotIn(token,path.read_text());self.assertEqual(load_config(path)['api_key'],token)
        self.assertEqual(sum(r.full_url.endswith('/register') for r in calls),1)
        for request in calls:self.assertNotIn('sk-FAKE',str(request.headers)+str(request.data))
    def test_unconfigured_service_is_reported_without_plaintext_remote_body(self):
        error=urllib.error.HTTPError('https://gateway.test',503,'disabled',{},io.BytesIO(b'{"error":"cloud_not_configured","secret":"DO-NOT-ECHO"}'))
        with tempfile.TemporaryDirectory() as folder,patch('cloud_client.request_json',side_effect=error):
            metrics={};answer=cloud_client.infer(self.image(),helper.normalize_config({'provider_mode':'cloud'}),Path(folder),metrics)
            self.assertEqual(answer,'API: cloud cloud_not_configured');self.assertNotIn('DO-NOT-ECHO',answer)
            self.assertEqual(metrics['http_status'],503)
    def test_non_https_or_credential_bearing_gateway_is_never_contacted(self):
        for address in ('http://gateway.test','https://user:password@gateway.test','https://gateway.test/path'):
            with patch('cloud_client.request_json') as send:
                answer=cloud_client.infer(b'',{'cloud_url':address},Path('.'),{})
                self.assertEqual(answer,'API: cloud invalid_address');send.assert_not_called()
    def test_upstream_quota_is_not_retried(self):
        token={'token':'STC_'+'a'*64,'expires_at':int((time.time()+3600)*1000)}
        error=urllib.error.HTTPError('https://gateway.test',429,'quota',{},io.BytesIO(b'{"error":"quota_reached"}'))
        with tempfile.TemporaryDirectory() as folder,patch('cloud_client.request_json',side_effect=[token,error]) as send:
            answer=cloud_client.infer(self.image(),helper.normalize_config({'provider_mode':'cloud'}),Path(folder),{})
            self.assertEqual(answer,'API: cloud quota_reached');self.assertEqual(send.call_count,2)

if __name__=='__main__':unittest.main()
