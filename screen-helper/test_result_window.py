import ctypes,time,unittest
from ctypes import wintypes
from result_window import ResultWindow

class FullResultWindowTests(unittest.TestCase):
    def test_long_full_answer_is_not_cut_at_500_characters_and_can_expire(self):
        window=ResultWindow()
        try:
            value='Полный ответ\n'+('Элемент → категория\n'*100)
            window.show(value,(0,0,1280,720),15)
            self.assertGreater(window.user.SendMessageW(window.edit,0xE,0,0),len(value))
            self.assertTrue(window.user.IsWindowVisible(window.hwnd))
            self.assertTrue(14<=window.deadline-time.monotonic()<=15)
            self.assertFalse(window.expire(window.deadline-.01));self.assertTrue(window.expire(window.deadline))
            self.assertFalse(window.user.IsWindowVisible(window.hwnd))
        finally:window.close()
    def test_result_window_does_not_take_foreground_and_can_be_reopened(self):
        window=ResultWindow();window.user.GetForegroundWindow.restype=wintypes.HWND
        try:
            window.show('A → B',(0,0,1280,720));self.assertNotEqual(window.user.GetForegroundWindow(),window.hwnd)
            window.user.SendMessageW(window.hwnd,0x10,0,0)
            window.show('Снова ответ',(0,0,1280,720));self.assertTrue(window.user.IsWindowVisible(window.hwnd))
        finally:window.close()

if __name__=='__main__':unittest.main()
