"""Visible, opt-in local proctor. Loopback only; no persistence or process termination."""
import argparse
import functools
import hashlib
import hmac
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
import sys
import webbrowser
from windows_sensors import WindowsSensors

VERSION='3.0.0'
ORIGINS={'http://127.0.0.1:8771','https://proctor-lab-sultan-1106.satinwaterlily4.chatgpt.site'}
BASE=(Path(sys.executable) if getattr(sys,'frozen',False) else Path(__file__)).resolve().parent
PUBLIC=BASE/'web' if getattr(sys,'frozen',False) else BASE.parent/'dist'


class AgentState:
    def __init__(self,collector,clock=time.monotonic):
        self.collector=collector;self.clock=clock;self.lock=threading.RLock()
        self.token=secrets.token_urlsafe(24);self.consent=False;self.session_id=None
        self.deadline=0;self.snapshot={};self.events=[];self.previous=None;self.chain='0'*64
        self.revision=0;self.last_seen={};self.recordings_notice='No recording; metadata only'

    def record(self,type,detail,level='warning'):
        if len(self.events)>=4000:return
        event={'seq':len(self.events)+1,'at':time.time(),'type':type,'detail':detail,'level':level}
        self.chain=hashlib.sha256((self.chain+json.dumps(event,sort_keys=True)).encode()).hexdigest()
        event['chain']=self.chain;self.events.append(event)

    def allow(self,enabled):
        with self.lock:
            self.consent=bool(enabled)
            if not enabled:self.stop('local_stop')

    def start(self,session_id):
        with self.lock:
            if not self.consent:raise ValueError('local_consent_required')
            if not re.fullmatch(r'[a-zA-Z0-9-]{10,80}',str(session_id)):raise ValueError('invalid_session')
            if self.session_id and self.session_id!=session_id:raise ValueError('another_session_active')
            if self.session_id:return self.view()
            self.session_id=session_id;self.deadline=self.clock()+15;self.events=[];self.chain='0'*64
            self.previous=None;self.last_seen={};self.record('native_start','Контроль Windows включён','info')
            self.sample();return self.view()

    def stop(self,reason='page_stop'):
        with self.lock:
            if self.session_id:self.record('native_stop',reason,'info')
            self.session_id=None;self.deadline=0

    def sample(self):
        with self.lock:
            if not self.consent:return
            if self.session_id and self.clock()>self.deadline:self.stop('heartbeat_expired')
            try:self.snapshot=self.collector()
            except Exception as error:self.snapshot={'capabilities':{},'errors':{'collector':type(error).__name__}}
            self.revision+=1
            if not self.session_id:return
            now=self.clock();s=self.snapshot;p=self.previous or {}
            def signal(type,detail,key=None,repeat=12):
                identity=(type,key or detail)
                if now-self.last_seen.get(identity,-1e9)>=repeat:
                    self.record(type,detail);self.last_seen[identity]=now
            for entry in s.get('blocked_processes',[]):signal('native_process',entry['category']+': '+entry['name'],entry['name'])
            if s.get('monitors',1)>1:signal('native_monitors','Дисплеев: '+str(s['monitors']))
            if p and s.get('monitors')!=p.get('monitors'):signal('native_display_change','Изменилось число дисплеев')
            foreground=s.get('foreground',{})
            if foreground and not foreground.get('browser'):signal('native_foreground','Активно другое приложение: '+foreground.get('process','unknown'))
            for name in s.get('overlays',[]):signal('native_overlay','Окно поверх других с прозрачностью: '+name,name)
            if p and s.get('clipboard_sequence')!=p.get('clipboard_sequence'):signal('native_clipboard','Изменился системный буфер обмена',repeat=0)
            if p and s.get('removable_drives')!=p.get('removable_drives'):signal('native_removable','Изменился список съёмных дисков',repeat=0)
            if s.get('removable_drives'):signal('native_removable','Подключены съёмные диски: '+', '.join(s['removable_drives']))
            if s.get('errors'):signal('native_sensor_error','Недоступны датчики: '+', '.join(s['errors']))
            self.previous=s

    def view(self,session_id=None,heartbeat=False):
        with self.lock:
            if self.session_id and self.clock()>self.deadline:self.stop('heartbeat_expired')
            if heartbeat and self.session_id and session_id==self.session_id:self.deadline=self.clock()+15
            return {'version':VERSION,'consent':self.consent,'active':bool(self.session_id),
                'sessionId':self.session_id,'revision':self.revision,'sensors':self.snapshot,
                'events':list(self.events),'watchdogSeconds':15,'chain':self.chain,
                'limitations':'Named-process detection can be evaded by renaming. No kernel driver, universal screenshot detector, biometric identity proof or remote attestation.'}


def handler_for(state,public=PUBLIC):
    class Handler(SimpleHTTPRequestHandler):
        extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.js':'text/javascript','.mjs':'text/javascript','.wasm':'application/wasm','.tflite':'application/octet-stream'}
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(public),**kwargs)
        def log_message(self,*args):pass  # Never log tokens, requests or browsing data.
        def end_headers(self):
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            origin=self.headers.get('Origin')
            if origin in ORIGINS:
                self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin')
                self.send_header('Access-Control-Allow-Private-Network','true')
            super().end_headers()
        def reply(self,data,status=200):
            raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
        def allowed(self):
            if self.headers.get('Host') not in ('127.0.0.1:8771',f'127.0.0.1:{self.server.server_port}'):
                self.reply({'error':'invalid_host'},403);return False
            if self.headers.get('Origin') not in ORIGINS|{None}:
                self.reply({'error':'origin_not_allowed'},403);return False
            expected='Bearer '+state.token
            if not hmac.compare_digest(self.headers.get('Authorization',''),expected):
                self.reply({'error':'pairing_required'},401);return False
            return True
        def do_OPTIONS(self):
            if self.headers.get('Origin') not in ORIGINS:self.reply({'error':'origin_not_allowed'},403);return
            self.send_response(204);self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type');self.end_headers()
        def do_GET(self):
            if self.path.startswith('/api/'):
                if not self.allowed():return
                if self.path=='/api/status':self.reply(state.view())
                else:self.reply({'error':'not_found'},404)
                return
            if self.headers.get('Host') not in ('127.0.0.1:8771',f'127.0.0.1:{self.server.server_port}'):
                self.reply({'error':'invalid_host'},403);return
            return super().do_GET()
        def do_POST(self):
            if not self.path.startswith('/api/') or not self.allowed():return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=2048:raise ValueError('invalid_body')
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):raise ValueError('invalid_body')
                sid=body.get('sessionId')
                if self.path=='/api/start':self.reply(state.start(sid))
                elif self.path=='/api/poll':
                    if sid!=state.session_id:raise ValueError('session_mismatch')
                    self.reply(state.view(sid,heartbeat=True))
                elif self.path=='/api/stop':
                    if sid!=state.session_id:raise ValueError('session_mismatch')
                    state.stop();self.reply(state.view())
                else:self.reply({'error':'not_found'},404)
            except (ValueError,TypeError):self.reply({'error':'invalid_request_or_session'},409)
    return Handler


def run():
    import tkinter as tk
    from tkinter import ttk,messagebox,filedialog
    state=AgentState(WindowsSensors().collect);root=tk.Tk();root.title('Proctor Lab 3 — контроль Windows')
    root.geometry('770x640');root.configure(bg='#eef2f7')
    frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Proctor Lab · Windows',font=('Segoe UI',22,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Локальный компонент контроля учебного сеанса',font=('Segoe UI',11)).pack(anchor='w',pady=(4,18))
    ttk.Label(frame,text='Проверяет процессы из списка, мониторы, активное приложение, окна поверх других,\nизменения буфера и съёмных дисков. Содержимое буфера и заголовки окон не читает.',justify='left').pack(anchor='w')
    enabled=tk.BooleanVar(value=False)
    ttk.Checkbutton(frame,text='Разрешить контроль на этом компьютере',variable=enabled,command=lambda:state.allow(enabled.get())).pack(anchor='w',pady=16)
    ttk.Label(frame,text='Код связи с сайтом (действует до закрытия этой программы):').pack(anchor='w')
    entry=ttk.Entry(frame,width=55,show='*');entry.insert(0,state.token);entry.configure(state='readonly');entry.pack(anchor='w',pady=6)
    def copy():root.clipboard_clear();root.clipboard_append(state.token)
    buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=8)
    ttk.Button(buttons,text='Скопировать код',command=copy).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='Открыть локальный стенд',command=lambda:webbrowser.open('http://127.0.0.1:8771/')).pack(side='left')
    label=tk.StringVar();ttk.Label(frame,textvariable=label,font=('Segoe UI',13,'bold')).pack(anchor='w',pady=16)
    text=tk.Text(frame,height=9,wrap='word',font=('Segoe UI',10));text.pack(fill='both',expand=True)
    ttk.Label(frame,text='Наблюдение явно включается вами. Закрытие программы останавливает контроль.\nПроцессы не завершаются. Журнал — на этом ПК; записи экрана и камеры здесь нет.',justify='left').pack(anchor='w',pady=12)
    def export():
        path=filedialog.asksaveasfilename(parent=root,defaultextension='.json',initialfile='proctor-windows-report.json')
        if path:Path(path).write_text(json.dumps(state.view(),ensure_ascii=False,indent=2),encoding='utf-8')
    ttk.Button(frame,text='Экспорт журнала Windows',command=export).pack(anchor='w')
    try:server=ThreadingHTTPServer(('127.0.0.1',8771),handler_for(state))
    except OSError:
        messagebox.showerror('Порт занят','Порт 8771 уже занят. Остановите старый локальный сервер или уже запущенный компонент Proctor Lab.',parent=root);root.destroy();return
    done=threading.Event();server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def sample():
        while not done.wait(1):state.sample()
    threading.Thread(target=sample,daemon=True).start()
    def tick():
        value=state.view();label.set('КОНТРОЛЬ СЕАНСА ВКЛЮЧЁН' if value['active'] else 'Готов к подключению сайта' if state.consent else 'Контроль выключен — нужно разрешение')
        names=', '.join(x['name'] for x in value['sensors'].get('blocked_processes',[])) or 'не обнаружены'
        lines=['Дисплеев: '+str(value['sensors'].get('monitors','—')),'Программы из списка: '+names,
            'Съёмные диски: '+str(len(value['sensors'].get('removable_drives',[]))),
            'Событий Windows: '+str(len(value['events']))]+[x['type']+': '+x['detail'] for x in value['events'][-5:]]
        text.configure(state='normal');text.delete('1.0','end');text.insert('1.0','\n'.join(lines));text.configure(state='disabled');root.after(500,tick)
    def close():
        state.allow(False);done.set();root.destroy();threading.Thread(target=server.shutdown,daemon=True).start()
    root.protocol('WM_DELETE_WINDOW',close);tick();root.mainloop();server.server_close()


if __name__=='__main__':
    if '--self-check' in sys.argv:
        sample=WindowsSensors().collect()
        report={'version':VERSION,'capabilities':sample['capabilities'],'errors':sample['errors'],
            'monitors':sample.get('monitors'),'blocked_process_count':len(sample.get('blocked_processes',[])),
            'clipboard_text_read':False,'keys_recorded':False,'screen_captured':False}
        (BASE/'native-self-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    else:run()
