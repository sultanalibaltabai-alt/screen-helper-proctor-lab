"""User-scoped Windows DPAPI storage. No embedded shared key or plaintext fallback."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile


class ConfigError(ValueError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if sys.platform != 'win32':
        raise ConfigError('Защищённое хранение ключа требует Windows.')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt.CryptProtectData.restype = crypt.CryptUnprotectData.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, output = DATA_BLOB(len(data), buffer), DATA_BLOB()
    try:
        if decrypt:
            ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
        else:
            ok = crypt.CryptProtectData(ctypes.byref(source), 'Screen Helper API key',
                None, None, None, 1, ctypes.byref(output))
        if not ok:
            raise ConfigError('Ключ недоступен в этой учётной записи Windows. Введи его заново в настройках.')
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.memset(buffer, 0, len(data))
        if output.pbData:
            ctypes.memset(output.pbData, 0, output.cbData)
            kernel.LocalFree(output.pbData)


def save_config(path, config):
    """Encrypt before touching disk; atomically replace the existing configuration."""
    path = Path(path)
    stored = {k: v for k, v in config.items() if not k.startswith('_') and k not in ('api_key', 'api_key_dpapi')}
    key = str(config.get('api_key') or '')
    if key:
        stored['api_key_dpapi'] = base64.b64encode(_crypt(key.encode('utf-8'))).decode('ascii')
    stored['key_storage'] = 'windows-user-dpapi-v1'
    content = json.dumps(stored, ensure_ascii=False, indent=2)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                prefix=path.name + '.', suffix='.local.tmp', delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_config(path, *, for_setup=False):
    path = Path(path)
    if not path.exists():
        if for_setup:
            return {}
        raise ConfigError('Настройки не найдены. Открой Setup.cmd.')
    try:
        if path.stat().st_size > 65536:
            raise ValueError()
        result = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(result, dict):
            raise ValueError()
        result={k:v for k,v in result.items() if not k.startswith('_')}
    except (ValueError, OSError):
        if for_setup:
            return {'_key_load_error': True}
        raise ConfigError('Файл настроек повреждён или недоступен. Открой Setup.cmd.') from None
    protected = result.pop('api_key_dpapi', None)
    if protected:
        try:
            result['api_key'] = _crypt(base64.b64decode(protected, validate=True), decrypt=True).decode('utf-8')
        except (ConfigError, ValueError, TypeError, UnicodeError):
            if not for_setup:
                raise ConfigError('Ключ не удалось расшифровать. Введи его заново в настройках.') from None
            result['api_key'] = ''
            result['_key_load_error'] = True
    elif result.get('api_key'):
        # Legacy releases used plaintext: encrypt in place without creating a plaintext backup.
        save_config(path, result)
    return result
