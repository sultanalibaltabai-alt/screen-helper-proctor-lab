"""Offline checks: synthetic images, mocked API; never captures the real desktop."""
import ctypes
import gc
from ctypes import wintypes
import json
import io
import os
from pathlib import Path
import queue
import shutil
import subprocess
import socket
import ssl
import urllib.error
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import helper


class HelperTests(unittest.TestCase):
    def test_model_uses_its_own_reasoning_and_output_defaults(self):
        for model in ('gemini-2.5-flash','gemini-3.8-flash'):
            generation = helper.gemini_payload(b'test', model,'auto')['generationConfig']
            self.assertNotIn('thinkingConfig', generation)
            self.assertNotIn('maxOutputTokens', generation)
            self.assertEqual(generation['responseMimeType'], 'application/json')
        self.assertNotIn('max_output_tokens', helper.payload(b'test','example-model'))

    def test_gemini_reasoning_profiles_do_not_truncate_output(self):
        for mode,level in [('fast','LOW'),('balanced','MEDIUM'),('deep','HIGH')]:
            generation=helper.gemini_payload(b'test','gemini-3.8-flash',mode)['generationConfig']
            self.assertEqual(generation['thinkingConfig']['thinkingLevel'],level)
            self.assertNotIn('maxOutputTokens',generation)

    def test_old_unlimited_wait_is_migrated_to_a_bounded_request(self):
        config=helper.normalize_config({'thinking_budget':2048})
        self.assertNotIn('thinking_budget',config)
        self.assertEqual(config['request_timeout'],60)
        self.assertEqual(helper.normalize_config({'request_timeout':'invalid'})['request_timeout'],60)
        self.assertEqual(helper.normalize_config({'request_timeout':0})['request_timeout'],60)
        self.assertEqual(helper.normalize_config({'settings_version':8,'request_timeout':0})['request_timeout'],60)
        self.assertEqual(helper.normalize_config({'request_timeout':180})['request_timeout'],180)

    def test_partial_output_is_not_shown_as_a_final_answer(self):
        self.assertEqual(helper.extract_answer({'status':'incomplete','output':[{'type':'message','content':[{'type':'output_text','text':'B'}]}]}),'API: incomplete response')
        self.assertEqual(helper.extract_gemini_answer({'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'B'}]}}]}),'API: incomplete response')

    def test_google_key_migrates_openai_model(self):
        config = helper.normalize_config({"api_key": "AIzaFAKE", "model": "gpt-4.1-mini"})
        self.assertEqual(config["provider"], "gemini")
        self.assertEqual(config["model"], "gemini-3.8-flash")

    def test_google_request_never_uses_openai_host_or_authorization(self):
        body = {"candidates": [{"content": {"parts": [{"text": "B"}]}}]}
        with patch.dict(os.environ, {}, clear=True), \
             patch("api_transport.open_request", return_value=io.BytesIO(json.dumps(body).encode())) as send:
            self.assertEqual(helper.ask(b"fake-image", {"api_key": "AIzaFAKE", "model": "gemini-2.5-flash","gemini_api":"generate_content"}), "B")
        request = send.call_args.args[0]
        self.assertGreater(send.call_args.kwargs['timeout'],0)
        self.assertLessEqual(send.call_args.kwargs['timeout'],60)
        self.assertTrue(request.full_url.startswith("https://generativelanguage.googleapis.com/"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(request.get_header("X-goog-api-key"), "AIzaFAKE")
        self.assertEqual(json.loads(request.data)["contents"][0]["parts"][1]["inlineData"]["mimeType"], "image/png")

    def test_streaming_google_request_uses_the_stream_endpoint_and_validates_final_json(self):
        body=b'data: {"candidates":[{"content":{"parts":[{"text":"B"}]},"finishReason":"STOP"}]}\n\n'
        with patch.dict(os.environ,{},clear=True),patch('api_transport.open_request',return_value=io.BytesIO(body)) as send:
            self.assertEqual(helper.ask(b'fake-image',{'api_key':'AIzaFAKE','streaming':True,'gemini_api':'generate_content'}),'B')
        self.assertTrue(send.call_args.args[0].full_url.endswith(':streamGenerateContent?alt=sse'))

    def test_key_paste_button_replaces_field_without_reading_real_clipboard(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            entry = tk.Entry(root, show="*")
            entry.insert(0, "old-value")
            with patch.object(root, "clipboard_get", return_value="  fake-test-key  ") as read:
                paste = helper.install_key_paste(root, entry, root)
                read.assert_not_called()
                self.assertEqual(paste(), "break")
                self.assertEqual(entry.get(), "fake-test-key")
                self.assertEqual(entry.cget("show"), "*")
            with patch.object(root, "clipboard_get", side_effect=tk.TclError()), \
                 patch("tkinter.messagebox.showwarning") as warning:
                paste()
                warning.assert_called_once()
                self.assertEqual(entry.get(), "fake-test-key")
        finally:
            root.destroy()
        del paste, entry, root
        gc.collect()  # Tk objects must be collected on the thread that created them.

    def test_service_unavailable_is_reported_without_leaking_remote_body(self):
        error = urllib.error.HTTPError('https://example.test',503,'busy',{},io.BytesIO(b'secret remote body'))
        with patch.object(helper, 'request_json', side_effect=error):
            self.assertEqual(helper.ask(b'test', {'api_key':'AIzaFAKE','streaming':False}), 'API: service unavailable (503)')

    def test_network_failure_classification(self):
        for error, expected in ((TimeoutError(), "timeout"),
            (socket.gaierror(), "DNS"), (ConnectionResetError(), "connection reset"),
            (ssl.SSLCertVerificationError(), "TLS certificate")):
            self.assertEqual(helper.network_error(urllib.error.URLError(error)), expected)

    def test_incomplete_archive_stops_before_dependency_install(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "Setup.cmd"
            shutil.copy2(helper.BASE / "Setup.cmd", script)
            result = subprocess.run(["cmd.exe", "/d", "/c", str(script)],
                                    input="\n", capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Extract All", result.stdout)
            self.assertFalse((Path(folder) / ".venv").exists())

    def test_image_request_and_answer(self):
        request = helper.payload(b"synthetic png", "example-model")
        self.assertFalse(request["store"])
        self.assertEqual(request["input"][0]["content"][1]["image_url"],
                         "data:image/png;base64,c3ludGhldGljIHBuZw==")
        self.assertEqual(helper.extract_answer({"output": [{"type": "message",
            "content": [{"type": "output_text", "text": " B \n"}]}]}), "B")
        self.assertEqual(helper.extract_answer({"output": []}), "API: invalid answer")

    def test_hotkey_registration_delivery_and_cleanup(self):
        events = queue.Queue()
        keys = helper.Hotkeys(events)
        with patch.object(helper, "HOTKEY_MODIFIERS", 0x4007):
            keys.start()
            try:
                self.assertEqual(events.get(timeout=3)[0], "ready")
                self.assertTrue(ctypes.windll.user32.PostThreadMessageW(
                    keys.thread_id, 0x0312, 1, 0))
                self.assertEqual(events.get(timeout=3), ("key", 1))
            finally:
                keys.stop()
                keys.join(timeout=3)
        self.assertFalse(keys.is_alive())

    def test_optional_replay_hotkey_conflict_does_not_prevent_start(self):
        events = queue.Queue()
        keys = helper.Hotkeys(events)
        original = ctypes.windll.user32.RegisterHotKey
        def register(hwnd, ident, modifiers, key):
            return False if ident == 4 else original(hwnd, ident, modifiers, key)
        with patch.object(helper, 'HOTKEY_MODIFIERS', 0x4007), \
             patch.object(ctypes.windll.user32, 'RegisterHotKey', side_effect=register):
            keys.start()
            try:
                self.assertEqual(events.get(timeout=3)[0], 'ready')
                self.assertFalse(keys.replay_available)
            finally:
                keys.stop()
                keys.join(timeout=3)
        self.assertFalse(keys.is_alive())

    def test_window_capture_answer_hide_quit_without_focus_change(self):
        from PIL import Image
        foreground = ctypes.windll.user32.GetForegroundWindow
        foreground.restype = wintypes.HWND
        seen = []
        states = []
        done = threading.Event()
        real_overlay = helper.Overlay

        class ObservedOverlay(real_overlay):
            def show(self, text, **options):
                super().show(text, **options)
                seen.append(text)
                rect = wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
                states.append((ctypes.windll.user32.IsWindowVisible(self.hwnd),
                               rect.right-rect.left, rect.bottom-rect.top,
                               foreground(), self.hwnd))

        def scripted(keys):
            keys.events.put(("ready", "Ready"))
            time.sleep(0.35)
            keys.events.put(("key", 1))
            done.wait(3)
            time.sleep(0.25)
            keys.events.put(("key", 4))
            time.sleep(0.1)
            keys.events.put(("key", 2))
            time.sleep(0.15)
            keys.events.put(("key", 3))

        def answer(png, config, **options):
            self.assertTrue(png.startswith(b"\x89PNG"))
            self.assertFalse(done.is_set(), "Redisplay must not make another API request")
            options['on_progress']('request')
            time.sleep(.7)
            options['on_progress']('validating')
            done.set()
            return "B",{}

        with tempfile.TemporaryDirectory() as folder:
            cfg = Path(folder) / "config.json"
            cfg.write_text(json.dumps({"api_key": "fake-offline-test", "model": "test",
                                       "font_size": 14, "display_seconds": 2}))
            with patch.object(helper, "CONFIG", cfg), \
                 patch.object(helper, "MUTEX_NAME", "Local\\ScreenHelperTestInstance"), \
                 patch.object(helper.Hotkeys, "run", scripted), \
                 patch.object(helper.InferenceRouter, "run", side_effect=answer), \
                 patch.object(helper, "capture_target", return_value=((0,0,320,200),(0,0,1920,1080))), \
                 patch("PIL.ImageGrab.grab", return_value=Image.linear_gradient("L").convert("RGB")), \
                 patch.object(helper, "Overlay", ObservedOverlay):
                helper.main()
        self.assertIn("B", seen)
        self.assertEqual(seen.count("B"), 2)
        self.assertTrue(any(text.isdecimal() for text in seen),seen)
        self.assertTrue(all(text=='B' or text.isdecimal() for text in seen),seen)
        self.assertTrue(states[0][0], states)
        self.assertGreater(states[0][1], 4, states)
        self.assertGreater(states[0][2], 10, states)
        for state in states:
            self.assertNotEqual(state[3], state[4], "Overlay became foreground window")


if __name__ == "__main__":
    unittest.main()
