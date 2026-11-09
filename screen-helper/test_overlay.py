"""Offline overlay checks: no clipboard access, screenshots, or API requests."""
import ctypes
from ctypes import wintypes
import time
import unittest

from overlay import Overlay, render_text, premultiplied_bgra, paginate_text


class OverlayTests(unittest.TestCase):
    def test_white_glyphs_keep_transparent_background_and_correct_alpha(self):
        picture=render_text('Сопоставление: A → 1',color=(255,255,255),align='left')
        pixels=list(picture.getdata())
        self.assertTrue(any(a==0 for r,g,b,a in pixels))
        self.assertTrue(any(a>0 and r==g==b==255 for r,g,b,a in pixels))
        data=premultiplied_bgra(picture)
        for i,(_,_,_,alpha) in enumerate(pixels):
            self.assertEqual(tuple(data[i*4:i*4+4]),(alpha,alpha,alpha,alpha))

    def test_white_answer_bottom_left_and_pages_survive_expiry(self):
        window=Overlay({'capture_work_area':(-1920,0,0,1040),'overlay_anchor':'bottom-left',
                        'text_color':'white','font_size':11,'display_seconds':15})
        answer='\n'.join(f'{i}: элемент{i} → место{i}' for i in range(100))
        try:
            window.show_answer(answer)
            self.assertEqual(window.last_rect[0],-1908)
            self.assertEqual(window.last_rect[3],1028)
            self.assertGreater(len(window.answer_pages),1)
            self.assertEqual('\n'.join(window.answer_pages),answer)
            window.expire(window.deadline)
            self.assertFalse(window.user.IsWindowVisible(window.hwnd))
            window.replay_answer()
            self.assertEqual(window.page_index,1)
            self.assertTrue(window.user.IsWindowVisible(window.hwnd))
            self.assertGreater(window.deadline-time.monotonic(),14.9)
        finally:window.close()

    def test_long_code_wrap_preserves_every_character(self):
        original='    value = '+('abcdefghij'*60)+'\n    return value'
        pages=paginate_text(original,11,200,3)
        self.assertGreater(len(pages),1)
        self.assertEqual(''.join(pages).replace('\n',''),original.replace('\n',''))
    def test_persistent_result_stays_until_hidden_and_status_can_still_expire(self):
        window = Overlay({'font_size':11,'display_seconds':2})
        try:
            window.show('B',persistent=True)
            self.assertIsNone(window.deadline)
            self.assertTrue(window.user.IsWindowVisible(window.hwnd))
            window.hide()
            self.assertFalse(window.user.IsWindowVisible(window.hwnd))
            window.show('AI: working')
            self.assertIsNotNone(window.deadline)
        finally:
            window.close()

    def test_overlay_uses_selected_secondary_monitor(self):
        window = Overlay({'capture_work_area': (-1920, 0, 0, 1040)})
        try:
            window.show('B')
            self.assertEqual(window.last_rect[2:], (-12, 1028))
        finally:
            window.close()

    def test_only_black_glyphs_on_zero_alpha_background(self):
        picture = render_text("A2:4\nA3:1\nA4:2")
        pixels = list(picture.getdata())
        self.assertTrue(any(alpha > 0 for _, _, _, alpha in pixels))
        self.assertTrue(any(alpha == 0 for _, _, _, alpha in pixels))
        self.assertTrue(all(red == green == blue == 0 for red, green, blue, _ in pixels))
        self.assertEqual(picture.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertGreater(picture.height, render_text("B").height * 2)

    def test_repeated_updates_do_not_leak_gdi_handles(self):
        window = Overlay({"font_size": 11})
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        window.user.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        window.user.GetGuiResources.restype = wintypes.DWORD
        process = kernel.GetCurrentProcess()
        try:
            window.show("B")
            baseline = window.user.GetGuiResources(process, 0)
            for number in range(20):
                window.show(f"A2:4\nA3:1\nA4:{number % 4 + 1}")
                window.hide()
            after = window.user.GetGuiResources(process, 0)
            self.assertEqual(after, baseline)
        finally:
            window.close()

    def test_window_placement_styles_deadline_and_cleanup(self):
        window = Overlay({"font_size": 11})
        user = window.user
        user.GetForegroundWindow.restype = wintypes.HWND
        user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.IsWindowVisible.argtypes = [wintypes.HWND]
        user.IsWindow.argtypes = [wintypes.HWND]
        hwnd = window.hwnd
        try:
            start = time.monotonic()
            window.show("A2:4\nA3:1\nA4:2")
            self.assertNotEqual(user.GetForegroundWindow(), hwnd)
            self.assertTrue(user.IsWindowVisible(hwnd))
            style = user.GetWindowLongPtrW(hwnd, -20)
            self.assertEqual(style & 0x080800A8, 0x080800A8)
            area = window.work_area()
            rect = wintypes.RECT()
            user.GetWindowRect(hwnd, ctypes.byref(rect))
            self.assertEqual((rect.right, rect.bottom), (area.right-12, area.bottom-12))
            self.assertEqual((rect.left, rect.top, rect.right, rect.bottom), window.last_rect)
            self.assertGreaterEqual(window.deadline, start + 15)
            self.assertLess(window.deadline, time.monotonic()+15.01)
            self.assertEqual(window.last_size, render_text("A2:4\nA3:1\nA4:2").size)
            window.hide()
            self.assertFalse(user.IsWindowVisible(hwnd))
            self.assertIsNone(window.deadline)
            window.show("B")
            self.assertTrue(user.IsWindowVisible(hwnd))
        finally:
            window.close()
        self.assertFalse(user.IsWindow(hwnd))
        window.close()  # Cleanup is idempotent.


if __name__ == "__main__":
    unittest.main()
