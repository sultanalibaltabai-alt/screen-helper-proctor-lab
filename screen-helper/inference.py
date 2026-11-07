"""Run paid inference in a disposable process, with a real local deadline/cancel."""
import multiprocessing as mp
import os
import threading
import time
import ctypes
import sys
from contextlib import contextmanager
from ctypes import wintypes

class RequestCancelled(Exception):pass
class RequestDeadline(Exception):pass
class RequestBusy(Exception):pass
REQUEST_MUTEX_NAME='Local\\ScreenHelperPaidInference'

@contextmanager
def request_lock():
    if sys.platform!='win32':yield;return
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.ReleaseMutex.argtypes=[wintypes.HANDLE];kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateMutexW(None,False,REQUEST_MUTEX_NAME)
    if not handle:raise OSError('Cannot create inference mutex')
    acquired=False
    try:
        acquired=kernel.WaitForSingleObject(handle,0) in (0,0x80)
        if not acquired:raise RequestBusy()
        yield
    finally:
        if acquired:kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)

def _child_entry(connection,image,config):
    def watch_parent():
        try:
            while True:
                if connection.poll(.2):
                    connection.recv()
        except (EOFError,OSError):
            os._exit(71)  # Parent exited; do not leave an orphan API process.
    threading.Thread(target=watch_parent,daemon=True).start()
    def emit(phase):
        try:connection.send(('progress',phase))
        except (BrokenPipeError,EOFError,OSError):pass
    try:
        from helper import ask
        metrics={}
        config=dict(config,_metrics=metrics,_on_progress=emit)
        answer=ask(image,config)
        connection.send(('result',answer,metrics))
    except Exception as error:
        try:connection.send(('failure',type(error).__name__))
        except (BrokenPipeError,EOFError,OSError):pass
    finally:
        connection.close()

def offline_probe(connection,image,config):
    """Packaged-runtime test only; never used by the normal inference route."""
    connection.send(('progress','validating'))
    connection.send(('result','SELF-CHECK',{'offline_test':True}))
    connection.close()

def execute(image,config,*,timeout=60,cancel=None,on_progress=None,target=None):
    with request_lock():
        return _execute_process(image,config,timeout=timeout,cancel=cancel,on_progress=on_progress,target=target)

def _execute_process(image,config,*,timeout=60,cancel=None,on_progress=None,target=None):
    if cancel and cancel.is_set():raise RequestCancelled()
    started=time.monotonic()
    safe={key:value for key,value in config.items() if not key.startswith('_')}
    if isinstance(config.get('_trace_path'),str):safe['_trace_path']=config['_trace_path']
    context=mp.get_context('spawn')
    parent,child=context.Pipe(duplex=True)
    process=context.Process(target=target or _child_entry,args=(child,image,safe),daemon=True)
    process.start();child.close()
    try:
        while True:
            if cancel and cancel.is_set():raise RequestCancelled()
            if timeout and time.monotonic()-started>=timeout:raise RequestDeadline()
            if parent.poll(.05):
                try:message=parent.recv()
                except EOFError:raise RuntimeError('API worker exited without a result') from None
                if message[0]=='progress':
                    if on_progress:on_progress(message[1])
                elif message[0]=='result':
                    metrics=dict(message[2],worker_pid=process.pid)
                    return message[1],metrics
                elif message[0]=='failure':raise RuntimeError('API worker failed: '+message[1])
            elif not process.is_alive():raise RuntimeError('API worker exited without a result')
    finally:
        parent.close()
        process.join(.15)
        if process.is_alive():process.terminate();process.join(1)
        if process.is_alive():process.kill();process.join(1)
        process.close()
