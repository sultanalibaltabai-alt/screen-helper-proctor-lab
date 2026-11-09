"""Ordinary visible Windows result window with readable, scrollable full answers."""
import ctypes
from ctypes import wintypes
import time

class ResultWindow:
    def __init__(self):
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.gdi=ctypes.WinDLL('gdi32',use_last_error=True)
        self.user.CreateWindowExW.argtypes=[wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,
            ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,ctypes.c_void_p]
        self.user.CreateWindowExW.restype=wintypes.HWND
        self.user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.user.SendMessageW.restype=wintypes.LPARAM
        self.user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        self.user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
        self.user.IsWindow.argtypes=[wintypes.HWND];self.user.IsWindowVisible.argtypes=[wintypes.HWND]
        self.user.DestroyWindow.argtypes=[wintypes.HWND]
        self.user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        self.user.MoveWindow.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.BOOL]
        self.gdi.CreateFontW.argtypes=[ctypes.c_int]*5+[wintypes.DWORD]*8+[wintypes.LPCWSTR]
        self.gdi.CreateFontW.restype=wintypes.HFONT
        self.gdi.DeleteObject.argtypes=[wintypes.HANDLE]
        self.scale=max(1,min(3,self.user.GetDpiForSystem()/96)) if hasattr(self.user,'GetDpiForSystem') else 1
        self.font=self.gdi.CreateFontW(-round(17*self.scale),0,0,0,400,0,0,0,1,0,0,5,0,'Consolas')
        self.hwnd=None;self.edit=None;self.deadline=None

    def show(self,text,area,seconds=15):
        if not self.hwnd or not self.user.IsWindow(self.hwnd):
            self.hwnd=self.user.CreateWindowExW(0x40008,'STATIC','Screen Helper — полный ответ',0x80C80000,
                0,0,1,1,None,None,None,None)
            if not self.hwnd:raise ctypes.WinError(ctypes.get_last_error())
            self.edit=self.user.CreateWindowExW(0x200,'EDIT','',0x50200844,0,0,1,1,self.hwnd,None,None,None)
            if not self.edit:raise ctypes.WinError(ctypes.get_last_error())
            self.user.SendMessageW(self.edit,0x30,self.font,1)
            self.user.SendMessageW(self.edit,0xC5,65535,0)
        left,top,right,bottom=area
        width=max(180,min(round(720*self.scale),right-left-24));height=max(120,min(round(440*self.scale),bottom-top-24))
        self.user.SetWindowPos(self.hwnd,wintypes.HWND(-1),right-width-12,bottom-height-12,width,height,0x0010)
        client=wintypes.RECT();self.user.GetClientRect(self.hwnd,ctypes.byref(client))
        self.user.MoveWindow(self.edit,8,8,max(1,client.right-16),max(1,client.bottom-16),True)
        value=ctypes.c_wchar_p(str(text).replace('\n','\r\n'))
        self.user.SendMessageW(self.edit,0xC,0,ctypes.cast(value,ctypes.c_void_p).value)
        self.user.SendMessageW(self.edit,0xB1,0,0)
        self.user.SendMessageW(self.edit,0xB7,0,0)
        self.user.ShowWindow(self.hwnd,4)  # Show without activating; the user can click to scroll.
        self.deadline=time.monotonic()+seconds

    def hide(self):
        if self.hwnd and self.user.IsWindow(self.hwnd):self.user.ShowWindow(self.hwnd,0)
        self.deadline=None

    def expire(self,now=None):
        if self.deadline is not None and (time.monotonic() if now is None else now)>=self.deadline:
            self.hide();return True
        return False

    def close(self):
        if self.hwnd and self.user.IsWindow(self.hwnd):self.user.DestroyWindow(self.hwnd)
        self.hwnd=None;self.edit=None;self.deadline=None
        if self.font:self.gdi.DeleteObject(self.font);self.font=None
