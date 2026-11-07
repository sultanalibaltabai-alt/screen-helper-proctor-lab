"""Windows hotkey screen-to-vision helper. Capture only on explicit hotkey."""
import base64
import ctypes
from ctypes import wintypes
from answers import ANSWER_SCHEMA, PROMPT, format_answers
from overlay import Overlay
from api_transport import request_json,request_gemini_stream
from progress import RequestProgress,save_status
from capture import target as capture_target, capture_image, CaptureError
from credentials import clean_key,detect_provider,key_problem,select_provider
import getpass
import io
import json
import os
from pathlib import Path
import queue
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import multiprocessing
from inference import execute,offline_probe,RequestCancelled
from routing import InferenceRouter

BASE = (Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__)).resolve().parent
CONFIG = BASE / "config.local.json"
HOTKEY_MODIFIERS = 0x4003
MUTEX_NAME = "Local\\ScreenHelperSingleInstance"
DEFAULT_MODELS = {"openai": "gpt-5.4-mini", "gemini": "gemini-3.8-flash"}

def configure_openai():
    previous=json.loads(CONFIG.read_text(encoding='utf-8-sig')) if CONFIG.exists() else {}
    current=normalize_config(previous)
    selected=dict(current,provider_mode='openai',provider='openai',model=DEFAULT_MODELS['openai'],fallback_model='')
    if current['provider']!='openai':selected['api_key']=''
    configure_gui(selected)

def configure():
    old = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    if getattr(sys, "frozen", False):
        configure_gui(old)
        return
    key = getpass.getpass("OpenAI or Google AI Studio API key (hidden): ").strip()
    key = clean_key(key or old.get("api_key", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""))
    if key_problem(key):raise ValueError('Enter the complete API key, without masking or whitespace.')
    mode=input(f"API service: auto/gemini/openai [{old.get('provider_mode','auto')}]: ").strip() or old.get('provider_mode','auto')
    old = normalize_config(dict(old, api_key=key,provider_mode=mode))
    model = input(f"Vision model [{old['model']}]: ").strip()
    old=normalize_config(dict(old,model=model or old['model']))
    old["display_seconds"] = 2
    old.setdefault("font_size", 11)
    CONFIG.write_text(json.dumps(old, indent=2), encoding="utf-8")
    print("Saved locally. Do not upload config.local.json to GitHub.")


def normalize_config(config):
    result = dict(config)
    key = clean_key(result.get("api_key", ""))
    provider = select_provider(key,result)
    result.setdefault('provider_mode','auto')
    result["provider"] = provider
    result["api_key"] = key
    model = str(result.get("model", "")).strip().removeprefix("models/")
    if not model or (provider == "gemini" and not model.startswith("gemini-")) or (provider == "openai" and model.startswith("gemini-")):
        model = DEFAULT_MODELS[provider]
    result["model"] = model
    result["display_seconds"] = 2
    result["hold_results"] = result.get("hold_results") is True
    result['show_progress'] = result.get('show_progress',True) is True
    result['streaming'] = result.get('streaming',False) is True
    if result.get('gemini_api') not in ('interactions','generate_content'):
        result['gemini_api']='generate_content' if model.startswith('gemini-2.') else 'interactions'
    if result['gemini_api']=='interactions':result['streaming']=False
    if result.get('reasoning_mode') not in ('balanced','deep','fast','auto'):
        result['reasoning_mode']='balanced'
    result.setdefault("font_size", 11)
    if result.get("capture_mode") not in ("window", "monitor"):
        result["capture_mode"] = "window"
    try:
        result["request_timeout"] = max(0, min(300, int(result.get("request_timeout", 60))))
    except (TypeError, ValueError):
        result["request_timeout"] = 60
    try:settings_version=int(result.get('settings_version',0))
    except (TypeError,ValueError):settings_version=0
    if settings_version<8 and result['request_timeout']==0:result['request_timeout']=60
    result['settings_version']=8
    result['api_retries']=1
    result['fallback_model']=str(result.get('fallback_model','gemini-2.5-flash' if provider=='gemini' and model.startswith('gemini-3') else '')).strip()
    if result['fallback_model'] and not result['fallback_model'].startswith('gemini-'):result['fallback_model']=''
    result['cache_results']=result.get('cache_results',True) is True
    result.pop("thinking_budget", None)
    return result


def install_key_paste(root, entry, parent):
    """Explicit clipboard action; never read or save clipboard automatically."""
    import tkinter as tk
    from tkinter import messagebox
    row = tk.Frame(parent)
    row.pack(fill="x", pady=(0, 8))
    status = tk.StringVar(value="Ключ ещё не введён")

    def update_status(event=None):
        count = len(entry.get())
        status.set(f"Введено символов: {count}" if count else "Ключ ещё не введён")

    def paste():
        try:
            value = clean_key(root.clipboard_get())
        except tk.TclError:
            messagebox.showwarning("Вставка", "В буфере нет текста. Сначала скопируйте ключ.", parent=root)
            return "break"
        if not value or any(char.isspace() for char in value):
            messagebox.showwarning("Вставка", "Скопируйте только API-ключ, без пояснений и пробелов.", parent=root)
            return "break"
        entry.delete(0, "end")
        entry.insert(0, value)
        entry.icursor("end")
        entry.focus_set()
        update_status()
        return "break"

    def keyboard(event):
        if (event.state & 4 and event.keycode == 86) or (event.state & 1 and event.keycode == 45):
            return paste()
        if event.state & 4 and event.keycode == 65:
            entry.selection_range(0, "end")
            entry.icursor("end")
            return "break"

    tk.Button(row, text="Вставить ключ", command=paste).pack(side="left")
    visible = tk.BooleanVar(value=False)
    tk.Checkbutton(row, text="Показать", variable=visible,
                   command=lambda: entry.configure(show="" if visible.get() else "*")).pack(side="left")
    tk.Label(parent, textvariable=status).pack(anchor="w", pady=(0, 6))
    menu = tk.Menu(entry, tearoff=False)
    menu.add_command(label="Вставить ключ", command=paste)

    def popup(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    entry.bind("<KeyPress>", keyboard)
    entry.bind("<KeyRelease>", update_status)
    entry.bind("<Button-3>", popup)
    return paste


def configure_gui(old):
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    old = normalize_config(old)
    root.title("Screen Helper v8.2 — настройка API")
    root.resizable(False, False)
    frame = tk.Frame(root, padx=18, pady=16)
    frame.pack()
    provider_options={'Авто по ключу':'auto','Google Gemini':'gemini','OpenAI':'openai'}
    provider_mode=tk.StringVar(value=next(label for label,value in provider_options.items() if value==old['provider_mode']))
    tk.Label(frame,text='Сервис API (для ключа Google выбери Google Gemini):').pack(anchor='w')
    tk.OptionMenu(frame,provider_mode,*provider_options,command=lambda *_:update_provider()).pack(anchor='w',pady=(0,8))
    tk.Label(frame, text="Ключ API: OpenAI или Google AI Studio (сохраняется локально)").pack(anchor="w")
    key_value = tk.StringVar()
    key_entry = tk.Entry(frame, show="*", width=58, textvariable=key_value)
    key_entry.pack(pady=(4, 12))
    install_key_paste(root, key_entry, frame)
    tk.Label(frame, text="Пустое поле сохраняет ранее введённый ключ.").pack(anchor="w")
    tk.Label(frame, text="Модель с поддержкой изображений:").pack(anchor="w", pady=(12, 0))
    model_entry = tk.Entry(frame, width=58)
    model_entry.insert(0, old["model"])
    model_entry.pack(pady=(4, 12))
    api_options={'Interactions — основной API':'interactions','GenerateContent — совместимость':'generate_content'}
    api_mode=tk.StringVar(value=next(label for label,value in api_options.items() if value==old['gemini_api']))
    tk.Label(frame,text='Способ подключения Google Gemini:').pack(anchor='w')
    tk.OptionMenu(frame,api_mode,*api_options,command=lambda *_:update_gemini_api()).pack(anchor='w',pady=(0,8))
    profiles={'Сбалансированно':'balanced','Тщательно (дольше)':'deep','Быстро (возможна потеря точности)':'fast','Настройки самой модели':'auto'}
    tk.Label(frame,text='Режим рассуждений поддерживаемой модели:').pack(anchor='w')
    profile=tk.StringVar(value=next(label for label,value in profiles.items() if value==old['reasoning_mode']))
    tk.OptionMenu(frame,profile,*profiles).pack(anchor='w',pady=(0,8))
    tk.Label(frame, text="Общий лимит ожидания, секунд (0 — безлимит с отменой):").pack(anchor="w")
    timeout_entry = tk.Entry(frame, width=12)
    timeout_entry.insert(0, str(old['request_timeout']))
    timeout_entry.pack(anchor="w", pady=(4, 8))
    tk.Label(frame,text='Резервная модель Gemini (необязательно):').pack(anchor='w')
    reserve_entry=tk.Entry(frame,width=58);reserve_entry.insert(0,old['fallback_model']);reserve_entry.pack(pady=(4,8))
    whole_monitor = tk.BooleanVar(value=old["capture_mode"] == "monitor")
    tk.Checkbutton(frame, text="Снимать весь монитор активного окна (иначе только окно)",
                   variable=whole_monitor).pack(anchor="w", pady=(0, 8))
    hold_results = tk.BooleanVar(value=old['hold_results'])
    tk.Checkbutton(frame, text="Оставлять ответ до скрытия — временный режим проверки",
                   variable=hold_results).pack(anchor="w", pady=(0, 8))
    progress_enabled=tk.BooleanVar(value=old['show_progress'])
    tk.Checkbutton(frame,text='Показывать этап и время запроса — временно для проверки',variable=progress_enabled).pack(anchor='w',pady=(0,8))
    streaming=tk.BooleanVar(value=old['streaming'])
    streaming_check=tk.Checkbutton(frame,text='Потоковое получение GenerateContent',variable=streaming)
    streaming_check.pack(anchor='w',pady=(0,8))
    def update_gemini_api():
        enabled=api_options[api_mode.get()]=='generate_content'
        if not enabled:streaming.set(False)
        streaming_check.configure(state='normal' if enabled else 'disabled')
    update_gemini_api()
    service = tk.StringVar(value="Сервис: " + old["provider"])
    tk.Label(frame, textvariable=service).pack(anchor="w")

    def update_provider(*args):
        key = clean_key(key_value.get()) or old.get('api_key','')
        updated = normalize_config(dict(old,api_key=key,model=model_entry.get(),provider_mode=provider_options[provider_mode.get()]))
        service.set("Сервис: " + updated["provider"])
        if updated["model"] != model_entry.get():
            model_entry.delete(0, "end")
            model_entry.insert(0, updated["model"])
    key_value.trace_add("write", update_provider)
    tk.Label(frame, text="Ctrl+Alt+S отправляет выбранное окно/монитор в API.\n"
             "Снимки могут содержать личные данные. Нужен доступный API-лимит.",
             justify="left").pack(anchor="w")

    def save():
        key = clean_key(key_entry.get()) or clean_key(old.get("api_key", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""))
        model = model_entry.get().strip()
        if not key or not model:
            messagebox.showerror("Настройка", "Введите API-ключ и модель.", parent=root)
            return
        if key_problem(key):
            messagebox.showerror("Настройка", "Нужен полный текст ключа: без звёздочек,\n"
                                 "многоточия, переносов строк и пробелов внутри.", parent=root)
            return
        config = normalize_config(dict(old, api_key=key, model=model,provider_mode=provider_options[provider_mode.get()],gemini_api=api_options[api_mode.get()]))
        detected=detect_provider(key)
        if detected and detected!=config['provider']:
            messagebox.showerror('Настройка','Выбранный сервис не соответствует ключу.\nВыбери Google Gemini, OpenAI или «Авто по ключу».',parent=root)
            return
        try:
            seconds = int(timeout_entry.get())
            if not 0 <= seconds <= 300:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Настройка", "Введите 0 (безлимит) или 1–300 секунд.", parent=root)
            return
        reserve=reserve_entry.get().strip()
        if reserve and not reserve.startswith('gemini-'):
            messagebox.showerror('Настройка','Для резерва укажи идентификатор модели gemini-… или оставь поле пустым.',parent=root);return
        config["request_timeout"] = seconds
        config['fallback_model']=reserve
        config["capture_mode"] = "monitor" if whole_monitor.get() else "window"
        config["display_seconds"] = 2
        config["hold_results"] = hold_results.get()
        config['show_progress']=progress_enabled.get()
        config['reasoning_mode']=profiles[profile.get()]
        config['streaming']=streaming.get() and config['gemini_api']=='generate_content'
        config.setdefault("font_size", 11)
        try:
            CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
        except OSError:
            messagebox.showerror("Настройка", "Не удалось сохранить файл. Распакуйте архив\n"
                                 "в папку, где у вас есть право записи.", parent=root)
            return
        messagebox.showinfo("Готово", "Настройки сохранены. Запустите Start.cmd.\n"
                            "Не загружайте config.local.json в GitHub.", parent=root)
        root.destroy()

    tk.Button(frame, text="Сохранить", command=save, width=18).pack(pady=(16, 0))
    root.mainloop()


def payload(png, model, reasoning_mode='balanced'):
    result = {
        "model": model,
        "store": False,
        "text": {"format": {"type": "json_schema", "name": "visible_answers", "strict": True, "schema": ANSWER_SCHEMA}},
        "instructions": PROMPT,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": "Answer the visible question."},
            {"type": "input_image", "detail": "high", "image_url":
             "data:image/png;base64," + base64.b64encode(png).decode("ascii")},
        ]}],
    }
    if model.startswith('gpt-5.4-mini') and reasoning_mode!='auto':
        result['reasoning']={'effort':{'fast':'low','balanced':'medium','deep':'high'}[reasoning_mode]}
    return result


def extract_answer(data):
    if data.get('status') == 'incomplete':
        return 'API: incomplete response'
    if data.get('status') not in (None,'completed'):return 'API: response not completed'
    if any(p.get('type')=='refusal' for item in data.get('output',[]) for p in item.get('content',[])):
        return 'API: refusal'
    parts = [p.get("text", "") for item in data.get("output", [])
             if item.get("type") == "message" for p in item.get("content", [])
             if p.get("type") == "output_text"]
    answer = " ".join(" ".join(parts).split())
    return format_answers(answer)


def gemini_payload(png, model, reasoning_mode='balanced'):
    generation = {"responseMimeType": "application/json", "responseJsonSchema": ANSWER_SCHEMA}
    if model.startswith('gemini-3') and 'flash' in model and reasoning_mode!='auto':
        generation['thinkingConfig']={'thinkingLevel':{'fast':'LOW','balanced':'MEDIUM','deep':'HIGH'}[reasoning_mode]}
    elif model.startswith('gemini-2.5-flash') and reasoning_mode in ('fast','balanced'):
        generation['thinkingConfig']={'thinkingBudget':1024 if reasoning_mode=='fast' else 4096}
    return {"systemInstruction": {"parts": [{"text": PROMPT}]},
            "contents": [{"role": "user", "parts": [
                {"text": "Answer the visible question."},
                {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(png).decode("ascii")}}]}],
            "generationConfig": generation}


def interactions_payload(png,model,reasoning_mode='balanced'):
    result={'model':model,'store':False,'system_instruction':PROMPT,
            'input':[{'type':'text','text':'Answer the visible questions.'},
                     {'type':'image','mime_type':'image/png','data':base64.b64encode(png).decode('ascii')}],
            'response_format':{'type':'text','mime_type':'application/json','schema':ANSWER_SCHEMA}}
    if reasoning_mode!='auto':result['generation_config']={'thinking_level':{'fast':'low','balanced':'medium','deep':'high'}[reasoning_mode]}
    return result

def interactions_text(data):
    return ''.join(part.get('text','') for step in data.get('steps',[]) if step.get('type')=='model_output'
                   for part in step.get('content',[]) if part.get('type')=='text')

def extract_interactions_answer(data):
    if data.get('status')=='failed':return 'API: generation failed'
    if data.get('status')!='completed':return 'API: response not completed'
    return format_answers(interactions_text(data))

def extract_gemini_answer(data):
    candidates = data.get("candidates", [])
    if not candidates:
        return "API: no candidate"
    finish = candidates[0].get('finishReason')
    if finish == 'MAX_TOKENS':
        return 'API: incomplete response'
    if finish and finish != 'STOP':
        return 'API: response not completed'
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return format_answers(text)


def network_error(error):
    reason = getattr(error, "reason", error)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(reason, socket.gaierror):
        return "DNS"
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "TLS certificate"
    if isinstance(reason, ssl.SSLError):
        return "TLS connection"
    if isinstance(reason, ConnectionResetError) or getattr(reason, "winerror", None) == 10054:
        return "connection reset"
    if isinstance(reason, ConnectionRefusedError):
        return "connection refused"
    return "connection failed"


def network_check():
    """Unauthenticated connectivity check. No key, screenshots, or paid inference."""
    started = time.monotonic()
    config = normalize_config(json.loads(CONFIG.read_text(encoding="utf-8-sig"))) if CONFIG.exists() else {"provider": "openai"}
    host = "generativelanguage.googleapis.com" if config["provider"] == "gemini" else "api.openai.com"
    url = f"https://{host}/v1beta/models" if config["provider"] == "gemini" else f"https://{host}/v1/models"
    report = {"version": 7, "host": host, "key_sent": False, "image_sent": False}
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            report.update(connection="reachable", http_status=response.status)
    except urllib.error.HTTPError as error:
        report.update(connection="reachable", http_status=error.code)
        if error.code == 401:
            report["note"] = "Expected without a key: API can be reached."
    except (urllib.error.URLError, OSError) as error:
        report.update(connection="failed", reason=network_error(error))
        reason = getattr(error, "reason", error)
        report["error_type"] = type(reason).__name__
        report["windows_error"] = getattr(reason, "winerror", None)
    report["seconds"] = round(time.monotonic() - started, 2)
    (BASE / "network-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def ask(png, config):
    config = normalize_config(config)
    provider = config["provider"]
    key = clean_key(config.get("api_key", "")) or clean_key(os.environ.get("GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY",''))
    metrics=config.get('_metrics',{})
    on_progress=config.get('_on_progress')
    def emit(stage):
        if stage=='retry':metrics['transport_retry_count']=metrics.get('transport_retry_count',0)+1
        if callable(on_progress):on_progress(stage)
    if key_problem(key):
        return "API: key format"
    detected=detect_provider(key)
    if detected and detected!=provider:return 'API: key/provider mismatch'
    if provider == "gemini":
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        if config['gemini_api']=='interactions':
            url='https://generativelanguage.googleapis.com/v1beta/interactions'
            body=interactions_payload(png,config['model'],config['reasoning_mode'])
            headers['Api-Revision']='2026-05-20'
        else:
            action=':streamGenerateContent?alt=sse' if config['streaming'] else ':generateContent'
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + urllib.parse.quote(config["model"], safe="-") + action
            body = gemini_payload(png, config["model"],config['reasoning_mode'])
    else:
        url = "https://api.openai.com/v1/responses"
        body = payload(png, config["model"],config['reasoning_mode'])
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        transport=request_gemini_stream if provider=='gemini' and config['gemini_api']=='generate_content' and config['streaming'] else request_json
        metrics['endpoint']=config['gemini_api'] if provider=='gemini' else 'openai_responses'
        started=time.monotonic()
        try:data = transport(req, timeout=config['request_timeout'] or None, retries=config['api_retries'],on_progress=emit)
        finally:metrics['transport_seconds']=round(time.monotonic()-started,3)
        if not isinstance(data, dict):
            return "API: invalid response"
        metrics['http_status']=200
        if isinstance(data.get('model'),str):metrics['model_returned']=data['model']
        metrics['stream_chunks']=data.get('_stream_chunks',0)
        usage=data.get('usage') if provider=='openai' or config['gemini_api']=='interactions' else data.get('usageMetadata')
        if not isinstance(usage,dict):usage={}
        metrics['tokens']={k:usage[k] for k in ('input_tokens','output_tokens','promptTokenCount','candidatesTokenCount','thoughtsTokenCount','totalTokenCount','total_input_tokens','total_output_tokens','total_thought_tokens','total_tokens') if isinstance(usage.get(k),int)}
        emit('validating')
        if config.get('_trace_path'):
            try:
                if provider=='gemini':
                    raw=interactions_text(data) if config['gemini_api']=='interactions' else ''.join(p.get('text','') for p in data.get('candidates',[{}])[0].get('content',{}).get('parts',[]) if not p.get('thought'))
                else:
                    raw=' '.join(p.get('text','') for item in data.get('output',[]) for p in item.get('content',[]) if p.get('type')=='output_text')
                Path(config['_trace_path']).write_text(json.dumps(json.loads(raw),ensure_ascii=False,indent=2),encoding='utf-8')
            except (ValueError,OSError,IndexError):pass
        validation_started=time.monotonic()
        answer=(extract_interactions_answer(data) if config['gemini_api']=='interactions' else extract_gemini_answer(data)) if provider == "gemini" else extract_answer(data)
        metrics['validation_seconds']=round(time.monotonic()-validation_started,3)
        return answer
    except urllib.error.HTTPError as exc:
        # Never log request bodies, images, keys, or remote error bodies.
        metrics['http_status']=exc.code
        if provider=='openai' and exc.code==429:
            try:
                remote=json.loads(exc.read()).get('error',{})
                if remote.get('code')=='insufficient_quota' or remote.get('type')=='insufficient_quota':
                    return 'API: billing/quota'
            except (ValueError,OSError,AttributeError):pass
            return 'API: rate limit (429)'
        if provider == "gemini" and exc.code in (400,503):
            try:
                error = json.loads(exc.read()).get("error", {})
                message=str(error.get('message','')).casefold()
                if exc.code==503 and any(phrase in message for phrase in ('high demand','overloaded')):
                    metrics['provider_error']='high_demand'
                    return 'API: Gemini перегружен (503)'
                if exc.code==400 and any(d.get("reason") == "API_KEY_INVALID" for d in error.get("details", []) if isinstance(d, dict)):
                    return "API: key"
            except (ValueError, OSError,AttributeError):
                pass
        return {401: "API: key", 403: "API: access", 404: "API: model",
                429: "API: quota/limit", 503: "API: service unavailable (503)",
                502: "API: gateway (502)", 504: "API: gateway timeout (504)"}.get(exc.code, f"API: HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        metrics['network_error_type']=type(getattr(error,'reason',error)).__name__
        return "API: " + network_error(error)
    except (ValueError, TypeError, AttributeError):
        return "API: invalid response"


class Hotkeys(threading.Thread):
    def __init__(self, events):
        super().__init__(daemon=True)
        self.events = events
        self.thread_id = None
        self.replay_available = False
        self.cancel_available = False

    def run(self):
        user = ctypes.windll.user32
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        registered = []
        try:
            # S capture; H hide; Q quit. Optional Ctrl+Alt+F8 redisplays a result.
            for ident, letter in enumerate("SHQ", 1):
                if not user.RegisterHotKey(None, ident, HOTKEY_MODIFIERS, ord(letter)):
                    self.events.put(("fatal", f"Hotkey Ctrl+Alt+{letter} is busy."))
                    return
                registered.append(ident)
            self.replay_available = bool(user.RegisterHotKey(None, 4, HOTKEY_MODIFIERS, 0x77))
            if self.replay_available:
                registered.append(4)
            self.cancel_available=bool(user.RegisterHotKey(None,5,HOTKEY_MODIFIERS,ord('X')))
            if self.cancel_available:registered.append(5)
            self.events.put(("ready", "v8.2 Ready: Ctrl+Alt+S" + ("" if self.replay_available else " (F8 busy)")))
            msg = wintypes.MSG()
            while user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    self.events.put(("key", int(msg.wParam)))
        finally:
            for ident in registered:
                user.UnregisterHotKey(None, ident)

    def stop(self):
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)


def main():
    if sys.platform != "win32":
        raise RuntimeError("Windows is required.")
    config = normalize_config(json.loads(CONFIG.read_text(encoding="utf-8-sig")))
    user = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex:
        raise ctypes.WinError()
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    if kernel.GetLastError() == 183:
        kernel.CloseHandle(mutex)
        user.MessageBoxW(None, "Screen Helper уже запущен. Завершите его через Ctrl+Alt+Q,\n"
                         "затем запустите нужную версию ещё раз.", "Screen Helper v8.2", 0x40)
        return
    overlay = None
    keys = None
    try:
        user.SetProcessDPIAware()
        overlay = Overlay(config)
        events = queue.Queue()
        keys = Hotkeys(events)
        busy = False
        generation = 0
        last_answer = None
        progress = None
        status_visible = True
        last_status_tick = 0
        cancel_event=threading.Event()
        worker_thread=None
        router=InferenceRouter()
        last_control=None
        control_path=CONFIG.with_name('control.local.json')
        try:last_control=json.loads(control_path.read_text(encoding='utf-8')).get('nonce')
        except (OSError,ValueError,AttributeError):pass
        status_view={'state':'idle','label':'Готов к запросу'}
        status_path=CONFIG.with_name('process-status.json')
        save_status(status_path,{'process_running':True,'state':'idle','label':'Готов к запросу'})

        def worker(token, bounds, current_config):
            started = time.monotonic()
            metrics={}
            last_phase=None;last_emitted=0
            def emit(phase):
                nonlocal last_phase,last_emitted
                now=time.monotonic()
                if phase!=last_phase or now-last_emitted>=.5:
                    events.put(('progress',(token,phase)));last_phase=phase;last_emitted=now
            try:
                # Wait for the compositor instead of a fixed 150 ms delay.
                ctypes.windll.dwmapi.DwmFlush()
                picture = capture_image(bounds)
                metrics['capture_seconds']=round(time.monotonic()-started,3)
                emit('encoding')
                encoding_started=time.monotonic()
                output = io.BytesIO()
                picture.save(output, format="PNG")
                metrics['encoding_seconds']=round(time.monotonic()-encoding_started,3)
                metrics['image_bytes']=len(output.getvalue())
                current_config['_trace_path'] = str(CONFIG.with_name('last-recognition.json'))
                result,api_metrics=router.run(output.getvalue(),current_config,cancel=cancel_event,on_progress=emit)
                metrics.update(api_metrics)
            except RequestCancelled:
                result='Запрос отменён локально'
                emit('cancelled')
            except CaptureError as error:
                result = str(error)
            except Exception:
                result = "Capture/API error"
            try:
                CONFIG.with_name("last-result.json").write_text(json.dumps({
                    "version": "8.2", "answer": result, "capture_mode": current_config['capture_mode'],
                    "hold_results": current_config['hold_results'],
                    "reasoning_mode":current_config['reasoning_mode'],'streaming':current_config['streaming'],
                    "metrics":metrics,
                    "seconds": round(time.monotonic()-started, 2),
                    "note": "Local result only; no screenshot or API key is saved."
                }, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            events.put(("answer", (token, result)))

        keys.start()
        msg = wintypes.MSG()
        while True:
            while user.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user.TranslateMessage(ctypes.byref(msg))
                user.DispatchMessageW(ctypes.byref(msg))
            if overlay.deadline and time.monotonic() >= overlay.deadline:
                overlay.hide()
            now=time.monotonic()
            if now-last_status_tick>=.5:
                if busy and progress:
                    visible=status_visible and overlay.config['show_progress'] and progress.phase!='capture'
                    if visible:overlay.show(progress.text(),persistent=True,font_size=14)
                    status_view=dict(progress.snapshot(),status_visible=visible)
                save_status(status_path,dict(status_view,process_running=True,pid=os.getpid(),updated_at=time.time(),cancel_hotkey=keys.cancel_available))
                last_status_tick=now
                try:
                    command=json.loads(control_path.read_text(encoding='utf-8'))
                    if command.get('nonce')!=last_control:
                        last_control=command.get('nonce')
                        if command.get('action') in ('cancel','stop'):events.put(('key',5 if command['action']=='cancel' else 3))
                except (OSError,ValueError,AttributeError):pass
            try:
                kind, value = events.get(timeout=0.03)
            except queue.Empty:
                continue
            if kind == "fatal":
                user.MessageBoxW(None, value, "Screen Helper", 0x10)
                break
            if kind == "ready":
                overlay.show(value)
            elif kind == 'progress':
                token,phase=value
                if progress and token==progress.token:progress.update(phase)
            elif kind == "answer":
                busy = False
                token, answer = value
                if progress and token==progress.token:
                    progress.update('done')
                    status_view=dict(progress.snapshot(),result_kind='cancelled' if answer.startswith('Запрос отменён') else 'error' if answer.startswith(('API:','Capture')) else 'answer')
                    save_status(status_path,dict(status_view,process_running=True,pid=os.getpid(),updated_at=time.time()))
                if token == generation:
                    last_answer = answer
                    overlay.show(answer,persistent=overlay.config['hold_results'])
                else:overlay.hide()
            elif kind == "key":
                if value == 3:
                    break
                if value==5:
                    if busy:cancel_event.set();progress.update('cancelling')
                    continue
                if value == 2:
                    generation += 1
                    status_visible=False
                    overlay.hide()
                elif value == 4:
                    if busy:
                        status_visible=True
                        overlay.show(progress.text() if progress else 'AI: working',font_size=14)
                    elif last_answer:
                        overlay.show(last_answer,persistent=overlay.config['hold_results'])
                    else:overlay.show('Готов: Ctrl+Alt+S',font_size=14)
                elif value == 1 and not busy:
                    try:
                        current_config = normalize_config(json.loads(CONFIG.read_text(encoding="utf-8-sig")))
                        bounds, work_area = capture_target(current_config['capture_mode'])
                    except CaptureError as error:
                        overlay.show(str(error))
                        continue
                    except (ValueError, OSError):
                        overlay.show('Config: run Setup.cmd')
                        continue
                    busy = True
                    cancel_event=threading.Event()
                    last_answer = None
                    generation += 1
                    progress=RequestProgress(generation)
                    status_visible=True;last_status_tick=0
                    overlay.config.update(current_config, capture_work_area=work_area)
                    overlay.hide()
                    worker_thread=threading.Thread(target=worker,args=(generation,bounds,current_config),daemon=True)
                    worker_thread.start()
                elif value==1 and busy:
                    status_visible=True
                    overlay.show(progress.text() if progress else 'AI: working',font_size=14)
    finally:
        if 'cancel_event' in locals():cancel_event.set()
        if 'worker_thread' in locals() and worker_thread:worker_thread.join(timeout=2)
        if 'status_path' in locals():
            if progress:progress.update('stopped');save_status(status_path,dict(progress.snapshot(),process_running=False))
            else:save_status(status_path,{'process_running':False,'state':'stopped'})
        if keys:
            keys.stop()
            keys.join(timeout=1)
        if overlay:
            overlay.close()
        kernel.CloseHandle(mutex)


def self_check():
    """Offline packaged-runtime check: synthetic image, no API, no screen capture."""
    from PIL import Image
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.destroy()
    image = Image.new("RGB", (32, 32), "white")
    buf = io.BytesIO()
    image.save(buf, "PNG")
    assert payload(buf.getvalue(), "test")["store"] is False
    letter=format_answers(json.dumps({'answers':[{'question':'1','answer':'b)','option_labels':['A','B','C','D']}]}))
    number=format_answers(json.dumps({'answers':[{'question':'1','answer':'3','option_labels':['1','2','3','4']}]}))
    assert (letter,number)==('B','3'), 'Option label formatting failed'
    auth_example=normalize_config({'api_key':'AQ.FAKE-SELF-CHECK','model':'gpt-4.1-mini'})
    assert auth_example['provider']=='gemini' and key_problem(auth_example['api_key']) is None
    assert interactions_payload(b'test','gemini-3.8-flash')['store'] is False
    assert extract_interactions_answer({'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'B'}]}]})=='B'
    offline_result,_=execute(b'',{},timeout=10,target=offline_probe)
    assert offline_result=='SELF-CHECK'
    rejected,_=execute(b'',{'api_key':'*','provider_mode':'gemini','model':'gemini-3.8-flash'},timeout=10)
    assert rejected=='API: key format'
    events = queue.Queue()
    keys = Hotkeys(events)
    keys.start()
    try:
        status = events.get(timeout=5)
        assert status[0] == "ready", status[1]
    finally:
        keys.stop()
        keys.join(timeout=2)
    overlay = Overlay({"font_size": 11, "display_seconds": 1})
    try:
        overlay.show("B")
        ctypes.windll.user32.GetForegroundWindow.restype = wintypes.HWND
        assert ctypes.windll.user32.GetForegroundWindow() != overlay.hwnd
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        ctypes.windll.user32.GetWindowRect(overlay.hwnd, ctypes.byref(rect))
        assert (rect.right - rect.left, rect.bottom - rect.top) == overlay.last_size
        area = overlay.work_area()
        assert rect.right <= area.right and rect.bottom <= area.bottom
        overlay.hide()
        overlay.show('B',persistent=True)
        assert overlay.deadline is None
        overlay.hide()
    finally:
        overlay.close()
    (BASE / "self-check.json").write_text(json.dumps({"ok": True, "api_called": False,
        "desktop_captured": False, "transparent_black_text": True, "position": "bottom-right",
        "replay_hotkey": "Ctrl+Alt+F8" if keys.replay_available else "unavailable",
        "version": "8.2", "letter_example":letter,"number_example":number,
        "persistent_result_supported":True,"auth_key_input_supported":True,"interactions_parser_checked":True,
        "managed_worker_checked":True,"cancel_hotkey":keys.cancel_available}), encoding="utf-8")


def api_check():
    """One real request using a synthetic question; never captures the desktop."""
    from PIL import Image, ImageDraw
    config = normalize_config(json.loads(CONFIG.read_text(encoding="utf-8-sig")))
    picture = Image.new("RGB", (500, 240), "white")
    ImageDraw.Draw(picture).text((20, 20), "What is 2 + 2?\n\nA) 3\nB) 4\nC) 5\nD) 6", fill="black", font_size=24)
    buf = io.BytesIO()
    picture.save(buf, "PNG")
    start = time.monotonic()
    config=dict(config,cache_results=False,request_timeout=config['request_timeout'] or 60)
    answer,metrics=InferenceRouter().run(buf.getvalue(),config)
    report = {"version": "8.2", "provider": config["provider"], "model": config["model"], "answer": answer,
              "ok": answer.strip().strip(".").upper() == "B", "desktop_captured": False,
              "seconds": round(time.monotonic()-start, 2)}
    report['metrics']=metrics
    (BASE / "api-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def multi_check():
    from quiz_samples import cases
    config = normalize_config(json.loads(CONFIG.read_text(encoding="utf-8-sig")))
    results = []
    router=InferenceRouter()
    path = BASE / "multi-check.json"
    for name, image, expected in cases(BASE):
        start = time.monotonic()
        answer,_=router.run(image,dict(config,cache_results=False,request_timeout=config['request_timeout'] or 60))
        results.append({"case": name, "answer": answer, "expected": expected,
                        "ok": answer == expected, "seconds": round(time.monotonic()-start, 2)})
        path.write_text(json.dumps({"version": 7, "all_ok": len(results) == 3 and all(r["ok"] for r in results),
            "desktop_captured": False, "results": results}, indent=2), encoding="utf-8")
        if answer.startswith(('API:','Capture')):break


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        if '--configure-openai' in sys.argv:
            configure_openai()
        elif '--panel' in sys.argv:
            from panel import run
            run(BASE)
        elif '--cancel' in sys.argv or '--stop' in sys.argv:
            import uuid
            save_status(CONFIG.with_name('control.local.json'),{'nonce':uuid.uuid4().hex,'action':'cancel' if '--cancel' in sys.argv else 'stop'})
        elif "--benchmark" in sys.argv:
            from benchmark import run
            run(BASE)
        elif "--multi-check" in sys.argv:
            multi_check()
        elif "--api-check" in sys.argv:
            api_check()
        elif "--network-check" in sys.argv:
            network_check()
        elif "--self-check" in sys.argv:
            self_check()
        elif "--configure" in sys.argv:
            configure()
        else:
            main()
    except Exception as error:
        if getattr(sys, "frozen", False) or sys.executable.lower().endswith("pythonw.exe"):
            ctypes.windll.user32.MessageBoxW(None, "Launch failed. Run Setup.cmd, "
                                           "or run python helper.py for details.",
                                           "Screen Helper", 0x10)
        else:
            raise
