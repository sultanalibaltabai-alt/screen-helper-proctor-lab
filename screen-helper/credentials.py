"""Credential input handling. Only the provider can validate an opaque API key."""

def clean_key(value):
    key=str(value or '').strip().lstrip('\ufeff').strip()
    if len(key)>=2 and key[0]==key[-1] and key[0] in ('\"',"'"):
        key=key[1:-1].strip()
    return key

def detect_provider(key):
    if key.startswith(('AIza','AQ.')):return 'gemini'
    if key.startswith('sk-'):return 'openai'
    return None

def key_problem(key):
    if not key:return 'empty'
    if '*' in key or '…' in key:return 'masked'
    if any(ord(char)<33 or ord(char)>126 for char in key):return 'characters'
    return None

def select_provider(key,config):
    mode=config.get('provider_mode','auto')
    if mode not in ('auto','gemini','openai'):raise ValueError('Unsupported provider mode')
    provider=mode if mode!='auto' else detect_provider(key) or config.get('provider') or ('gemini' if str(config.get('model','')).removeprefix('models/').startswith('gemini-') else 'openai')
    if provider not in ('gemini','openai'):raise ValueError('Unsupported API provider')
    return provider
