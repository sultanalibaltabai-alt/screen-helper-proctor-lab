"""Real local DPAPI and HTTP-redirect checks; no paid or external API requests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import base64
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import helper
from api_transport import open_request
from config_store import ConfigError, load_config, save_config
from overlay import Overlay
from presentation import result_report, result_text


class SecurityTests(unittest.TestCase):
    def test_real_dpapi_roundtrip_and_plaintext_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.local.json'
            key='AQ.FAKE-LOCAL-DPAPI-TEST'
            path.write_text(json.dumps({'api_key':key,'provider_mode':'gemini'}),encoding='utf-8')
            self.assertEqual(load_config(path)['api_key'],key)
            raw=path.read_text(encoding='utf-8')
            self.assertNotIn(key,raw)
            self.assertNotIn('api_key',json.loads(raw))
            self.assertTrue(json.loads(raw)['api_key_dpapi'])
            self.assertEqual(load_config(path)['api_key'],key)
            self.assertEqual(list(Path(folder).iterdir()),[path])

    def test_damaged_ciphertext_can_be_replaced_without_plaintext_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.local.json'
            path.write_text('{"api_key_dpapi":"not valid base64!"}',encoding='utf-8')
            with self.assertRaises(ConfigError):load_config(path)
            self.assertEqual(load_config(path,for_setup=True)['api_key'],'')
            self.assertTrue(load_config(path,for_setup=True)['_key_load_error'])
            save_config(path,{'api_key':'AQ.FAKE-TAMPER'})
            stored=json.loads(path.read_text(encoding='utf-8'))
            data=bytearray(base64.b64decode(stored['api_key_dpapi']));data[-1]^=1
            stored['api_key_dpapi']=base64.b64encode(data).decode('ascii')
            path.write_text(json.dumps(stored),encoding='utf-8')
            with self.assertRaises(ConfigError):load_config(path)
            save_config(path,{'api_key':'sk-FAKE-NEW','provider_mode':'openai'})
            self.assertEqual(load_config(path)['api_key'],'sk-FAKE-NEW')

    def test_failed_encryption_keeps_previous_configuration_intact(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.local.json'
            save_config(path,{'api_key':'AQ.FAKE-PREVIOUS'})
            before=path.read_bytes()
            with patch('config_store._crypt',side_effect=ConfigError('unavailable')):
                with self.assertRaises(ConfigError):save_config(path,{'api_key':'AQ.FAKE-NEW'})
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(load_config(path)['api_key'],'AQ.FAKE-PREVIOUS')

    def test_corrupt_json_is_recoverable_in_setup_and_never_echoed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.local.json';path.write_text('{not-json SECRET}',encoding='utf-8')
            with self.assertRaises(ConfigError) as error:load_config(path)
            self.assertNotIn('SECRET',str(error.exception))
            self.assertTrue(load_config(path,for_setup=True)['_key_load_error'])

    def test_provider_profiles_keep_their_own_encrypted_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/'config.local.json'
            save_config(config,{'api_key':'AQ.FAKE-GEMINI','provider_mode':'gemini','model':'gemini-3.8-flash'})
            save_config(config.with_name('openai.local.json'),{'api_key':'sk-FAKE-OPENAI','provider_mode':'openai','model':'gpt-5.4-mini'})
            with patch.object(helper,'CONFIG',config),patch.object(helper,'configure_gui') as gui:
                helper.configure_provider('openai')
                self.assertEqual(gui.call_args.args[0]['api_key'],'sk-FAKE-OPENAI')
                self.assertEqual(gui.call_args.args[0]['provider'],'openai')
                helper.configure_provider('gemini')
                self.assertEqual(gui.call_args.args[0]['api_key'],'AQ.FAKE-GEMINI')

    def test_api_redirect_does_not_forward_auth_or_image_body(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(self.path)
                self.rfile.read(int(self.headers.get('Content-Length','0')))
                self.send_response(307)
                self.send_header('Location','/must-not-receive-key');self.end_headers()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/request',data=b'FAKE-IMAGE',headers={'Authorization':'Bearer FAKE'})
            with self.assertRaises(urllib.error.HTTPError) as error:open_request(request,timeout=3)
            self.assertEqual(error.exception.code,307)
            error.exception.close()
            self.assertEqual(seen,['/request'])
        finally:
            server.shutdown();server.server_close();thread.join(2)

    def test_minimal_result_and_metadata_never_keep_answer_history(self):
        report=result_report('M1:2\nM2:4',{'attempts':[{'answer':'M1:2'}],'api_key':'FAKE','model_used':'test'},2.12)
        self.assertNotIn('M1:2',json.dumps(report))
        self.assertNotIn('FAKE',json.dumps(report))
        self.assertEqual(report['result_kind'],'answer')
        self.assertEqual(result_text('API: service unavailable (503)'),'?')
        self.assertEqual(result_text('Запрос отменён локально'),'')
        self.assertEqual(result_text('M1:2\nM2:4'),'M1:2\nM2:4')

    def test_old_debug_flags_cannot_override_fifteen_second_result(self):
        config=helper.normalize_config({'display_seconds':999,'hold_results':True,'show_progress':False,'request_timeout':0,'settings_version':8})
        self.assertEqual(config['display_seconds'],15)
        self.assertNotIn('hold_results',config);self.assertNotIn('show_progress',config)
        self.assertEqual(config['request_timeout'],60)
        self.assertEqual(helper.normalize_config({'request_timeout':9999})['request_timeout'],180)
        self.assertEqual(helper.normalize_config({'request_timeout':float('inf')})['request_timeout'],60)
        damaged=helper.normalize_config({'font_size':'invalid','provider_mode':'invalid','provider':'invalid'})
        self.assertEqual(damaged['font_size'],11);self.assertEqual(damaged['provider_mode'],'auto')
        self.assertEqual(helper.normalize_config({'provider_mode':None})['provider_mode'],'auto')

    def test_answer_remains_for_fifteen_seconds_then_window_hides(self):
        window=Overlay(helper.normalize_config({}))
        try:
            window.show('B');deadline=window.deadline
            self.assertFalse(window.expire(deadline-.01))
            self.assertTrue(window.user.IsWindowVisible(window.hwnd))
            self.assertTrue(window.expire(deadline))
            self.assertFalse(window.user.IsWindowVisible(window.hwnd))
        finally:window.close()


if __name__=='__main__':unittest.main()
