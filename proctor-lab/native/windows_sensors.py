"""Read-only Windows observations. No screenshots, key hooks, titles or clipboard text."""
import ctypes
from ctypes import wintypes as W
import os
import sys

BLOCKED = {
    'screenhelper.exe':'AI-помощник', 'anydesk.exe':'Удалённый доступ',
    'teamviewer.exe':'Удалённый доступ', 'teamviewer_service.exe':'Удалённый доступ',
    'rustdesk.exe':'Удалённый доступ', 'radmin.exe':'Удалённый доступ',
    'obs64.exe':'Запись экрана', 'obs32.exe':'Запись экрана', 'sharex.exe':'Захват экрана',
    'snippingtool.exe':'Захват экрана', 'lightshot.exe':'Захват экрана',
}
BROWSERS = {'chrome.exe','msedge.exe','browser.exe','firefox.exe','brave.exe','opera.exe'}


class WindowsSensors:
    def __init__(self):
        if sys.platform!='win32':raise RuntimeError('Windows x64 required')
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.kernel.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD]
        self.kernel.CreateToolhelp32Snapshot.restype=W.HANDLE
        self.kernel.CloseHandle.argtypes=[W.HANDLE]
        self.user.GetForegroundWindow.restype=W.HWND
        self.user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
        self.user.GetWindowLongPtrW.argtypes=[W.HWND,ctypes.c_int]
        self.user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.user.IsWindowVisible.argtypes=[W.HWND]
        self.kernel.GetDriveTypeW.argtypes=[W.LPCWSTR]
        self.kernel.GetDriveTypeW.restype=W.UINT
        self.user.GetClipboardSequenceNumber.restype=W.DWORD

    def processes(self):
        class Entry(ctypes.Structure):
            _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),
                ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',W.DWORD),
                ('cntThreads',W.DWORD),('th32ParentProcessID',W.DWORD),
                ('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]
        handle=self.kernel.CreateToolhelp32Snapshot(2,0)
        if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        self.kernel.Process32FirstW.argtypes=[W.HANDLE,ctypes.POINTER(Entry)]
        self.kernel.Process32NextW.argtypes=[W.HANDLE,ctypes.POINTER(Entry)]
        try:
            item=Entry();item.dwSize=ctypes.sizeof(item);result={}
            ok=self.kernel.Process32FirstW(handle,ctypes.byref(item))
            if not ok:raise ctypes.WinError(ctypes.get_last_error())
            while ok:
                result[int(item.th32ProcessID)]=item.szExeFile.lower()
                ok=self.kernel.Process32NextW(handle,ctypes.byref(item))
            return result
        finally:self.kernel.CloseHandle(handle)

    def monitors(self):
        count=0
        callback_type=ctypes.WINFUNCTYPE(W.BOOL,W.HANDLE,W.HDC,ctypes.POINTER(W.RECT),W.LPARAM)
        def count_one(*args):
            nonlocal count
            count+=1;return True
        callback=callback_type(count_one)
        if not self.user.EnumDisplayMonitors(None,None,callback,0):raise ctypes.WinError()
        return count

    def foreground(self,processes):
        handle=self.user.GetForegroundWindow();pid=W.DWORD()
        self.user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        name=processes.get(pid.value,'unknown')
        return {'browser':name in BROWSERS,'agent':pid.value==os.getpid(),'process':name}

    def overlays(self,processes):
        found=set();callback_type=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        def inspect(handle,_):
            if not self.user.IsWindowVisible(handle):return True
            style=self.user.GetWindowLongPtrW(handle,-20)
            if style&0x8 and style&0x80000:  # TOPMOST + LAYERED, a signal, not a verdict.
                pid=W.DWORD();self.user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
                name=processes.get(pid.value,'unknown')
                if pid.value!=os.getpid() and name not in {'explorer.exe','dwm.exe','shellexperiencehost.exe'}:found.add(name)
            return True
        callback=callback_type(inspect)
        if not self.user.EnumWindows(callback,0):raise ctypes.WinError()
        return sorted(found)

    def removable_drives(self):
        mask=self.kernel.GetLogicalDrives()
        if not mask:raise ctypes.WinError()
        return [chr(65+i)+':' for i in range(26) if mask&(1<<i) and self.kernel.GetDriveTypeW(chr(65+i)+':\\')==2]

    def collect(self):
        result={'capabilities':{},'errors':{}};processes={}
        for name,fn in [('processes',self.processes),('monitors',self.monitors),
                ('removable_drives',self.removable_drives),
                ('clipboard_sequence',lambda:int(self.user.GetClipboardSequenceNumber()))]:
            try:
                value=fn();result['capabilities'][name]=True
                if name=='processes':
                    processes=value
                    result['blocked_processes']=[{'name':n,'category':BLOCKED[n]} for n in sorted(set(value.values())&BLOCKED.keys())]
                else:result[name]=value
            except Exception as error:
                result['capabilities'][name]=False;result['errors'][name]=type(error).__name__
        for name,fn in [('foreground',lambda:self.foreground(processes)),('overlays',lambda:self.overlays(processes))]:
            try:result[name]=fn();result['capabilities'][name]=bool(processes)
            except Exception as error:result['capabilities'][name]=False;result['errors'][name]=type(error).__name__
        return result
