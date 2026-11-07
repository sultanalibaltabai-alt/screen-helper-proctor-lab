import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from agent import AgentState,handler_for


def healthy():return {'capabilities':{k:True for k in ('processes','monitors','foreground','overlays','clipboard_sequence','removable_drives')},'errors':{},'blocked_processes':[],'monitors':1,'foreground':{'browser':True,'process':'chrome.exe'},'overlays':[],'clipboard_sequence':1,'removable_drives':[]}

class StateTests(unittest.TestCase):
    def setUp(self):
        self.now=100;self.reads=0;self.sensor=healthy()
        def collect():self.reads+=1;return json.loads(json.dumps(self.sensor))
        self.state=AgentState(collect,lambda:self.now)
    def test_no_observation_or_start_without_explicit_local_consent(self):
        self.state.sample();self.assertEqual(self.reads,0)
        with self.assertRaises(ValueError):self.state.start('session-first-123')
    def test_windows_process_and_clipboard_changes_are_journaled_without_contents(self):
        self.state.allow(True);self.sensor['blocked_processes']=[{'name':'screenhelper.exe','category':'AI'}]
        self.state.start('session-first-123')
        self.assertIn('native_process',[e['type'] for e in self.state.events])
        self.sensor['clipboard_sequence']=2;self.state.sample()
        self.assertIn('native_clipboard',[e['type'] for e in self.state.events])
        self.assertNotIn('clipboard_text',json.dumps(self.state.view()))
        self.assertNotIn('token',self.state.view())
        self.assertEqual(len(self.state.chain),64)
    def test_session_ownership_and_watchdog_cannot_be_revived_by_a_late_heartbeat(self):
        self.state.allow(True);self.state.start('session-first-123')
        with self.assertRaises(ValueError):self.state.start('session-second-123')
        self.now+=16;view=self.state.view('session-first-123',heartbeat=True)
        self.assertFalse(view['active']);self.assertEqual(self.state.events[-1]['detail'],'heartbeat_expired')
    def test_local_stop_immediately_stops_observation(self):
        self.state.allow(True);self.state.start('session-first-123');self.state.allow(False)
        reads=self.reads;self.state.sample();self.assertEqual(self.reads,reads);self.assertFalse(self.state.view()['active'])
    def test_known_windows_signals_are_not_reported_as_universal_detection(self):
        self.state.allow(True);self.sensor.update(monitors=2,removable_drives=['E:'],overlays=['example.exe'],foreground={'browser':False,'process':'example.exe'})
        self.state.start('session-first-123');types={e['type'] for e in self.state.events}
        self.assertTrue({'native_monitors','native_removable','native_overlay','native_foreground'}<=types)
        self.assertIn('No kernel driver',self.state.view()['limitations'])

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.state=AgentState(healthy);self.directory=tempfile.TemporaryDirectory()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.state,Path(self.directory.name)))
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.directory.cleanup()
    def request(self,path='/api/status',token=True,origin='http://127.0.0.1:8771',body=None,host=None):
        headers={'Origin':origin}
        if token:headers['Authorization']='Bearer '+self.state.token
        if host:headers['Host']=host
        request=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body else None,headers=headers)
        return urllib.request.urlopen(request,timeout=3)
    def test_wrong_origin_missing_pairing_and_rebinding_are_rejected(self):
        for options,code in [({'token':False},401),({'origin':'https://untrusted.example'},403),({'host':'untrusted.example'},403)]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(**options)
            self.assertEqual(error.exception.code,code)
    def test_authenticated_start_poll_and_stop_require_the_same_session(self):
        self.state.allow(True)
        with self.request('/api/start',body={'sessionId':'session-first-123'}) as r:self.assertTrue(json.load(r)['active'])
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/stop',body={'sessionId':'session-wrong-123'})
        with self.request('/api/poll',body={'sessionId':'session-first-123'}) as r:
            self.assertEqual(r.headers['Access-Control-Allow-Origin'],'http://127.0.0.1:8771');self.assertTrue(json.load(r)['active'])
        with self.request('/api/stop',body={'sessionId':'session-first-123'}) as r:self.assertFalse(json.load(r)['active'])
    def test_module_mime_does_not_depend_on_windows_registry_associations(self):
        Path(self.directory.name,'model.mjs').write_text('export const ready=true;')
        with self.request('/model.mjs',token=False) as response:
            self.assertEqual(response.headers['Content-Type'],'text/javascript')

if __name__=='__main__':unittest.main()
