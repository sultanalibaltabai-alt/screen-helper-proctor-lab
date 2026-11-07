"""Capture selected window/monitor. No capture-exclusion or security bypass."""
import ctypes
from ctypes import wintypes
from PIL import ImageGrab,ImageStat

class CaptureError(Exception):pass
class MonitorInfo(ctypes.Structure):
    _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD)]

def target(mode='window'):
    u=ctypes.WinDLL('user32',use_last_error=True)
    u.GetForegroundWindow.restype=wintypes.HWND
    hwnd=u.GetForegroundWindow()
    if not hwnd:raise CaptureError('Capture: no active window')
    u.IsIconic.argtypes=[wintypes.HWND]
    if u.IsIconic(hwnd):raise CaptureError('Capture: window minimized')
    rect=wintypes.RECT()
    dwm=ctypes.WinDLL('dwmapi');dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    if dwm.DwmGetWindowAttribute(hwnd,9,ctypes.byref(rect),ctypes.sizeof(rect))!=0:
        u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        if not u.GetWindowRect(hwnd,ctypes.byref(rect)):raise CaptureError('Capture: window bounds')
    u.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];u.MonitorFromWindow.restype=wintypes.HANDLE
    monitor=u.MonitorFromWindow(hwnd,2);info=MonitorInfo();info.cbSize=ctypes.sizeof(info)
    u.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
    if not u.GetMonitorInfoW(monitor,ctypes.byref(info)):raise CaptureError('Capture: monitor bounds')
    if mode=='monitor':rect=info.rcMonitor
    bounds=tuple(getattr(rect,k) for k in ('left','top','right','bottom'))
    if bounds[2]-bounds[0]<16 or bounds[3]-bounds[1]<16:raise CaptureError('Capture: window too small')
    # Clip off-screen window borders to the actual virtual desktop.
    desktop=(u.GetSystemMetrics(76),u.GetSystemMetrics(77),u.GetSystemMetrics(78),u.GetSystemMetrics(79))
    x,y,w,h=desktop
    bounds=(max(x,bounds[0]),max(y,bounds[1]),min(x+w,bounds[2]),min(y+h,bounds[3]))
    if bounds[2]<=bounds[0] or bounds[3]<=bounds[1]:raise CaptureError('Capture: window outside screen')
    return bounds,tuple(getattr(info.rcWork,k) for k in ('left','top','right','bottom'))

def capture_image(bounds):
    picture=ImageGrab.grab(bbox=bounds,all_screens=True).convert('RGB')
    if picture.width<16 or picture.height<16:raise CaptureError('Capture: image too small')
    # Uniform screenshots are not sent to the model or billed.
    if max(ImageStat.Stat(picture.resize((64,64))).stddev)<0.5:
        raise CaptureError('Capture: blank image')
    return picture
