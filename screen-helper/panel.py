"""Visible desktop control panel. No browser inspection or automatic screenshots."""
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
import webbrowser

from inference import execute,offline_probe,RequestCancelled
from progress import save_status,STAGES
from routing import InferenceRouter
from answers import is_control_answer
from config_store import load_config, ConfigError

def load_json(path):
    try:
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def public_error(answer):
    if 'cloud_not_configured' in answer:return 'Облачный сервис доступен, но владелец ещё не подключил модель и оплату. Пока можно выбрать Gemini или OpenAI со своим ключом.'
    if 'API: cloud' in answer:
        if any(v in answer for v in ('quota_reached','registration_limit','provider_quota')):return 'Общий лимит запросов или квота провайдера исчерпаны. Это общий баланс сервиса.'
        if 'duplicate_request' in answer:return 'Такой запрос уже был принят. Повторный платный вызов не выполнялся.'
        if 'image_too_large' in answer:return 'Изображение слишком большое для общего сервиса. Выбери отдельное окно.'
        if 'provider_access' in answer:return 'Владелец должен проверить ключ и доступ к модели на сервере.'
        return 'Общий сервис не вернул ответ. Проверь интернет и состояние сервиса; автоматических платных повторов нет.'
    if answer.startswith('Config:'):return 'Проверь настройки программы через Setup.cmd. Возможно, ключ нужно ввести заново на этом ПК.'
    if 'HTTP 30' in answer:return 'API вернул перенаправление. Запрос остановлен: ключ и изображение не пересылаются на другой адрес.'
    if 'billing/quota' in answer:return 'У OpenAI закончился доступный баланс API или не активирована оплата. Открой Billing в OpenAI Platform. Подписка ChatGPT не заменяет настройку этого ключа.'
    if 'rate limit' in answer:return 'OpenAI ограничил частоту запросов. Повтори позже; новый запрос сейчас автоматически не отправляется.'
    if 'refusal' in answer:return 'Модель отказалась отвечать. Ответ не подставляется.'
    if 'другой запрос' in answer:return 'Уже выполняется другой запрос AI. Дождись его или нажми «Отменить запрос».'
    if '503' in answer or 'перегруз' in answer:return 'Модель перегружена. Запрос не решён; повторные запросы временно приостановлены.'
    if 'quota' in answer or '429' in answer:return 'Недостаточно квоты API для выбранной модели. Проверь лимиты проекта у провайдера.'
    if 'время' in answer or 'timeout' in answer:return 'Ответ не получен в заданное время. Локальное ожидание остановлено.'
    if 'key/provider' in answer:return 'Ключ и выбранный сервис не совпадают. Открой настройки.'
    if 'key' in answer:return 'Проверь полный ключ и выбранный сервис в настройках.'
    if 'access' in answer:return 'У ключа нет доступа к выбранной модели или API.'
    if 'model' in answer:return 'Выбранная модель недоступна для этого проекта.'
    if 'connection' in answer or 'DNS' in answer or 'TLS' in answer:return 'Ошибка сети при обращении к API. Проверь подключение; настройки защиты сети не изменялись.'
    if any(part in answer for part in ('invalid answer','invalid response','incomplete','not completed')):return 'Модель не вернула завершённый проверяемый ответ. Программа не подставляет случайную букву.'
    return answer

def run(base):
    import tkinter as tk
    from tkinter import ttk
    from helper import normalize_config,load_active_config
    root=tk.Tk();root.title('Screen Helper 8.4 — управление');root.geometry(f"740x{min(700,root.winfo_screenheight()-100)}");root.minsize(660,560)
    root.configure(bg='#eef2f7')
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('TFrame',background='#eef2f7');style.configure('TLabel',background='#eef2f7',foreground='#233047',font=('Segoe UI',10))
    style.configure('Title.TLabel',font=('Segoe UI',22,'bold'));style.configure('Status.TLabel',font=('Segoe UI',16,'bold'))
    style.configure('TButton',font=('Segoe UI',10),padding=(12,8))
    frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Screen Helper',style='Title.TLabel').pack(anchor='w')
    ttk.Label(frame,text='Состояние, проверка AI и управление запросами').pack(anchor='w',pady=(2,18))
    state=tk.StringVar(value='Проверка состояния…');model_label=tk.StringVar();details=tk.StringVar()
    ttk.Label(frame,textvariable=state,style='Status.TLabel',wraplength=660).pack(anchor='w')
    ttk.Label(frame,textvariable=model_label,wraplength=660).pack(anchor='w',pady=(8,3))
    ttk.Label(frame,textvariable=details,wraplength=660).pack(anchor='w',pady=(0,16))
    actions=ttk.Frame(frame);actions.pack(fill='x')
    answer=tk.Text(frame,height=7,wrap='word',font=('Segoe UI',13),relief='flat',padx=14,pady=12,bg='white',fg='#20334f')
    answer.pack(fill='both',expand=True,pady=(18,10));answer.configure(state='disabled')
    notice=tk.StringVar(value='AI может ошибаться. Поддерживаемые графовые задачи пересчитываются локально после распознавания.')
    ttk.Label(frame,textvariable=notice,wraplength=660).pack(anchor='w',pady=(0,12))
    ttk.Label(frame,text='Ctrl+Alt+S — снимок   ·   Ctrl+Alt+X — отмена   ·   Ctrl+Alt+H — скрыть',wraplength=660).pack(anchor='w')
    ttk.Label(frame,text='Снимок отправляется только по горячей клавише. Панель не снимает экран автоматически.',wraplength=660).pack(anchor='w',pady=(6,0))
    messages=queue.Queue();test_cancel=threading.Event();test_busy=False;testing=False;router=InferenceRouter();last_output=None;test_started=0;test_phase='request';test_thread=None

    config_error=''
    def config():
        nonlocal config_error
        try:
            value=load_active_config(base/'config.local.json')
            config_error=''
            return value
        except (ConfigError,OSError) as error:
            config_error=str(error)
            return normalize_config({})
    def launch(*arguments):
        if getattr(sys,'frozen',False):command=[str(base/'ScreenHelper.exe'),*arguments]
        else:command=[sys.executable,str(base/'helper.py'),*arguments]
        subprocess.Popen(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    def control(action):save_status(base/'control.local.json',{'nonce':uuid.uuid4().hex,'action':action})
    def status():
        value=load_json(base/'process-status.json')
        live=value.get('process_running') and time.time()-value.get('updated_at',0)<5
        return value,bool(live)
    def show(text):
        answer.configure(state='normal');answer.delete('1.0','end');answer.insert('1.0',text);answer.configure(state='disabled')
    def start():
        nonlocal testing
        testing=False
        config()
        if config_error:notice.set(config_error);launch('--configure');return
        _,live=status()
        if not live:launch()
        else:notice.set('Помощник уже запущен. Перейди к вопросу и нажми Ctrl+Alt+S.')
    def cancel():
        if test_busy:test_cancel.set()
        else:control('cancel')
    def stop():
        test_cancel.set();control('stop')
    def test_api():
        nonlocal test_busy,test_cancel,testing,test_started,test_phase,test_thread
        current=dict(config(),cache_results=False)
        if config_error:notice.set(config_error);return
        active,live=status()
        if test_busy:return
        if live and active.get('state')=='working':notice.set('Сначала дождись текущего запроса или отмени его.');return
        test_busy=True;testing=True;test_cancel=threading.Event();test_button.configure(state='disabled');local_button.configure(state='disabled')
        test_started=time.monotonic();test_phase='request'
        state.set('Проверка AI');show('Создан контрольный вопрос 2 + 2. Снимок рабочего стола не делается.')
        def work():
            from PIL import Image,ImageDraw
            picture=Image.new('RGB',(500,240),'white')
            ImageDraw.Draw(picture).text((20,20),'What is 2 + 2?\n\nA) 3\nB) 4\nC) 5\nD) 6',fill='black',font_size=24)
            output=io.BytesIO();picture.save(output,'PNG');started=time.monotonic()
            try:
                result,metrics=router.run(output.getvalue(),current,cancel=test_cancel,on_progress=lambda phase:messages.put(('phase',phase)))
                report={'version':'8.4','answer':result,'ok':is_control_answer(result),'seconds':round(time.monotonic()-started,2),'desktop_captured':False,'metrics':metrics}
                save_status(base/'api-check.json',report);messages.put(('result',report))
            except RequestCancelled:messages.put(('cancelled',None))
            except Exception:messages.put(('error','Проверка завершилась внутренней ошибкой. Открой отчёты для диагностики.'))
        test_thread=threading.Thread(target=work,daemon=True);test_thread.start()
    def test_local():
        nonlocal test_busy,test_cancel,testing,test_started,test_phase,test_thread
        active,live=status()
        if test_busy or (live and active.get('state')=='working'):notice.set('Сначала заверши или отмени текущий запрос.');return
        test_busy=True;testing=True;test_cancel=threading.Event();test_started=time.monotonic();test_phase='validating'
        test_button.configure(state='disabled');local_button.configure(state='disabled');state.set('Локальная проверка без API')
        def work():
            try:
                result,_=execute(b'',{},timeout=10,cancel=test_cancel,target=offline_probe)
                from graph_solver import solve
                weight=solve({'kind':'mst_weight','nodes':['A','B'],'directed':False,'source':'A','target':'B','edges':[{'from':'A','to':'B','weight':2}]})
                messages.put(('local',result=='SELF-CHECK' and weight=='2'))
            except RequestCancelled:messages.put(('cancelled',None))
            except Exception:messages.put(('error','Локальная проверка не прошла. Запусти Check.cmd при остановленном помощнике.'))
        test_thread=threading.Thread(target=work,daemon=True);test_thread.start()
    ttk.Button(actions,text='Запустить помощник',command=start).pack(side='left',padx=(0,8))
    ttk.Button(actions,text='Отменить запрос',command=cancel).pack(side='left',padx=(0,8))
    ttk.Button(actions,text='Настройки',command=lambda:launch('--configure')).pack(side='left')
    second=ttk.Frame(frame);second.pack(fill='x',before=answer,pady=(8,0))
    test_button=ttk.Button(second,text='Проверить AI · возможен расход API',command=test_api);test_button.pack(side='left',padx=(0,8))
    local_button=ttk.Button(second,text='Проверить программу без API',command=test_local);local_button.pack(side='left',padx=(0,8))
    links=ttk.Frame(frame);links.pack(fill='x',before=answer,pady=(8,0))
    ttk.Button(links,text='Отчёты',command=lambda:os.startfile(str(base))).pack(side='left',padx=(0,8))
    def limits():
        current=config()
        return current['cloud_url']+'/health' if current['provider']=='cloud' else 'https://ai.google.dev/gemini-api/docs/rate-limits' if current['provider']=='gemini' else 'https://platform.openai.com/settings/organization/limits'
    ttk.Button(links,text='Лимиты API',command=lambda:webbrowser.open(limits())).pack(side='left',padx=(0,8))
    ttk.Button(actions,text='Остановить помощник',command=stop).pack(side='left',padx=(8,0))
    def tick():
        nonlocal test_busy,last_output,testing,test_phase
        current=config();value,live=status()
        model_name='на общем сервере' if current['provider']=='cloud' else current['model']
        model_label.set(f"Модель: {model_name}  ·  Лимит ожидания: {current['request_timeout']} с"+(f"\nРезерв: {current['fallback_model']}" if current['fallback_model'] else ''))
        if testing and not test_busy and live and value.get('state')=='working':testing=False
        if test_busy:details.set(f"{STAGES.get(test_phase,test_phase)} · {int(time.monotonic()-test_started)} с")
        if not test_busy and not testing:
            label='Ответ не получен' if value.get('result_kind')=='error' else 'Запрос отменён' if value.get('result_kind')=='cancelled' else value.get('label','Готов к запросу')
            state.set(label if live else 'Помощник остановлен')
            details.set(f"Прошло: {value.get('elapsed_seconds',0)} с" if live and value.get('state')=='working' else 'Горячие клавиши работают в запущенном помощнике.' if live else 'Нажми «Запустить помощник».')
            report=load_json(base/'last-result.json')
            stamp=(report.get('result_kind'),report.get('error'),report.get('seconds'))
            if report and stamp!=last_output:
                last_output=stamp;raw=report.get('error') or ''
                text=public_error(raw) if raw else 'Запрос отменён.' if report.get('result_kind')=='cancelled' else 'Ответ показан поверх окна на 15 секунд. История ответов не сохраняется.'
                used=report.get('metrics',{}).get('model_used')
                returned=report.get('metrics',{}).get('model_returned')
                cached=report.get('metrics',{}).get('cache_hit')
                show(text+(f'\n\nМодель ответа: {used}' if used else '')+(f'\nМодель в ответе API: {returned}' if returned and returned!=used else '')+('\nПовторно использован ответ для точно такого же снимка.' if cached else '')+f"\nВремя запроса: {report.get('seconds','—')} с")
        while True:
            try:kind,data=messages.get_nowait()
            except queue.Empty:break
            if kind=='phase':test_phase=data
            else:
                test_busy=False;test_button.configure(state='normal');local_button.configure(state='normal')
                if kind=='result':
                    state.set('Контрольный пример решён' if data['ok'] else 'Ответ не подтверждён')
                    show(('Ожидаемый ответ: B\nПолучено: '+data['answer'] if data['ok'] else public_error(data['answer']))+f"\nВремя: {data['seconds']} с"+(f"\nМодель ответа: {data['metrics']['model_used']}" if data['metrics'].get('model_used') else ''))
                    notice.set('Этот пример не доказывает точность на любых университетских вопросах.')
                elif kind=='cancelled':state.set('Проверка отменена');show('Локальный процесс запроса остановлен. Провайдер мог уже принять запрос.')
                elif kind=='local':
                    state.set('Локальная проверка пройдена' if data else 'Ошибка локальной проверки')
                    show('Запуск отдельного процесса и вычисление графа проверены.\n\nЗапросов к API и снимков экрана не было.\nДоступность модели и качество её ответов этой проверкой не подтверждаются.')
                else:state.set('Ошибка проверки');show(data)
        root.after(400,tick)
    def close():test_cancel.set();root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);tick();root.mainloop()
    test_cancel.set()
    if test_thread:test_thread.join(2)
