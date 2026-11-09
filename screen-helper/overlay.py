"""Small native Windows text overlay with a transparent, click-through surface.

This is a normal layered window: it is visible to screen capture and makes no
attempt to hide from other software. All window operations run on the UI thread.
"""
import ctypes
from ctypes import wintypes
import os
import math
from pathlib import Path
import sys
import time
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageChops


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]


def load_font(font_size):
    font_size = max(8, min(40, int(font_size)))
    font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeui.ttf"
    try:
        return ImageFont.truetype(str(font_path), font_size)
    except OSError:
        return ImageFont.load_default(size=font_size)


def paginate_text(text,font_size,max_width,max_lines):
    text=str(text).replace('\r','').expandtabs(4)[:24000] or '?'
    font=load_font(font_size)
    cell=max(1,max(font.getlength(c) for c in set(text) if c!='\n')) if text.strip() else font_size
    columns=max(4,int((max_width-4)/cell));rows=[]
    for line in text.split('\n'):
        rows.extend(textwrap.wrap(line,width=columns,replace_whitespace=False,drop_whitespace=False,break_long_words=True,break_on_hyphens=False) or [''])
    return ['\n'.join(rows[i:i+max_lines]) for i in range(0,len(rows),max_lines)]


def premultiplied_bgra(picture):
    r,g,b,a=picture.split()
    return Image.merge('RGBA',(ImageChops.multiply(b,a),ImageChops.multiply(g,a),ImageChops.multiply(r,a),a)).tobytes()


def render_text(text, font_size=11,color=(0,0,0),align='right'):
    """Render ordinary visible glyphs on transparent pixels; never hide from capture."""
    font=load_font(font_size)
    text = str(text).replace("\r", "")[:24000] or "?"
    scratch = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bounds = scratch.multiline_textbbox((0, 0), text, font=font, spacing=2, align=align)
    pad = 2
    width = max(1, math.ceil(bounds[2] - bounds[0])) + pad * 2
    height = max(1, math.ceil(bounds[3] - bounds[1])) + pad * 2
    picture = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(picture).multiline_text(
        (pad-bounds[0], pad-bounds[1]), text, font=font, fill=(*color,255),
        spacing=2, align=align)
    return picture


class Overlay:
    def __init__(self, config):
        if sys.platform != "win32":
            raise RuntimeError("The native overlay requires Windows.")
        self.config = dict(config)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        self._bind()
        self.hwnd = self.user.CreateWindowExW(
            0x080800A8, "STATIC", "Screen Helper answer", 0x80000000,
            0, 0, 1, 1, None, None, None, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.deadline = None
        self.last_rect = None
        self.last_size = None
        self.answer_pages=[]
        self.page_index=0

    def _bind(self):
        u, g = self.user, self.gdi
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        u.CreateWindowExW.restype = wintypes.HWND
        u.GetDC.argtypes = [wintypes.HWND]
        u.GetDC.restype = wintypes.HDC
        u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        u.ReleaseDC.restype = ctypes.c_int
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.DestroyWindow.argtypes = [wintypes.HWND]
        u.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
        u.SystemParametersInfoW.restype = wintypes.BOOL
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.SetWindowPos.restype = wintypes.BOOL
        u.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC,
            ctypes.POINTER(wintypes.POINT), ctypes.POINTER(SIZE), wintypes.HDC,
            ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
            ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
        u.UpdateLayeredWindow.restype = wintypes.BOOL
        g.CreateCompatibleDC.argtypes = [wintypes.HDC]
        g.CreateCompatibleDC.restype = wintypes.HDC
        g.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                     ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
        g.CreateDIBSection.restype = wintypes.HBITMAP
        g.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        g.SelectObject.restype = wintypes.HANDLE
        g.DeleteObject.argtypes = [wintypes.HANDLE]
        g.DeleteDC.argtypes = [wintypes.HDC]

    def work_area(self):
        selected = self.config.get('capture_work_area')
        if selected and len(selected) == 4:
            return wintypes.RECT(*selected)
        area = wintypes.RECT()
        if not self.user.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return area

    def show(self, text, *, persistent=False,font_size=None):
        if not self.hwnd:
            raise RuntimeError("The overlay is closed.")
        left=self.config.get('overlay_anchor')=='bottom-left'
        color=(255,255,255) if self.config.get('text_color')=='white' else (0,0,0)
        picture = render_text(text, self.config.get("font_size", 11) if font_size is None else font_size,color,'left' if left else 'right')
        area = self.work_area()
        margin = max(0, int(self.config.get("overlay_margin", 12)))
        # Avoid placing oversized messages outside the primary monitor's work area.
        max_width = max(1, area.right-area.left-margin*2)
        max_height = max(1, area.bottom-area.top-margin*2)
        if picture.width > max_width or picture.height > max_height:
            start=0 if left else max(0,picture.width-max_width)
            picture = picture.crop((start,0,min(picture.width,start+max_width),min(picture.height,max_height)))
        x = area.left+margin if left else max(area.left, area.right-margin-picture.width)
        y = max(area.top, area.bottom-margin-picture.height)
        self._upload(picture, x, y)
        if not self.user.SetWindowPos(self.hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0053):
            raise ctypes.WinError(ctypes.get_last_error())
        self.last_size = picture.size
        self.last_rect = (x, y, x+picture.width, y+picture.height)
        self.deadline = None if persistent else time.monotonic() + float(self.config.get("display_seconds", 15))

    def show_answer(self,text):
        area=self.work_area();size=self.config.get('font_size',11)
        width=max(60,min(760,int((area.right-area.left)*.7))-24)
        height=max(50,min(350,int((area.bottom-area.top)*.4)))
        font=load_font(size);bounds=font.getbbox('AgЖ')
        lines=max(2,int(height/max(1,bounds[3]-bounds[1]+2))-2)
        self.answer_pages=paginate_text(text,size,width,lines);self.page_index=0
        self._show_answer_page()

    def _show_answer_page(self):
        text=self.answer_pages[self.page_index]
        if len(self.answer_pages)>1:text+=f'\n[{self.page_index+1}/{len(self.answer_pages)}]'
        self.show(text)

    def replay_answer(self):
        if self.answer_pages:
            self.page_index=(self.page_index+1)%len(self.answer_pages)
            self._show_answer_page()

    def _upload(self, picture, x, y):
        desktop_dc = self.user.GetDC(None)
        if not desktop_dc:
            raise ctypes.WinError(ctypes.get_last_error())
        memory_dc = self.gdi.CreateCompatibleDC(desktop_dc)
        bitmap = None
        original = None
        try:
            if not memory_dc:
                raise ctypes.WinError(ctypes.get_last_error())
            info = BITMAPINFO()
            info.bmiHeader = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), picture.width,
                -picture.height, 1, 32, 0, picture.width*picture.height*4, 0, 0, 0, 0)
            bits = ctypes.c_void_p()
            bitmap = self.gdi.CreateDIBSection(desktop_dc, ctypes.byref(info), 0,
                                              ctypes.byref(bits), None, 0)
            if not bitmap or not bits.value:
                raise ctypes.WinError(ctypes.get_last_error())
            pixels = premultiplied_bgra(picture)
            ctypes.memmove(bits, pixels, len(pixels))
            original = self.gdi.SelectObject(memory_dc, bitmap)
            source = wintypes.POINT(0, 0)
            target = wintypes.POINT(x, y)
            size = SIZE(*picture.size)
            blend = BLENDFUNCTION(0, 0, 255, 1)
            if not self.user.UpdateLayeredWindow(self.hwnd, desktop_dc, ctypes.byref(target),
                    ctypes.byref(size), memory_dc, ctypes.byref(source), 0, ctypes.byref(blend), 2):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if original:
                self.gdi.SelectObject(memory_dc, original)
            if bitmap:
                self.gdi.DeleteObject(bitmap)
            if memory_dc:
                self.gdi.DeleteDC(memory_dc)
            self.user.ReleaseDC(None, desktop_dc)

    def hide(self):
        if self.hwnd:
            self.user.ShowWindow(self.hwnd, 0)
        self.deadline = None

    def expire(self, now=None):
        if self.deadline is not None and (time.monotonic() if now is None else now) >= self.deadline:
            self.hide()
            return True
        return False

    def close(self):
        if self.hwnd:
            self.user.DestroyWindow(self.hwnd)
            self.hwnd = None
        self.deadline = None
