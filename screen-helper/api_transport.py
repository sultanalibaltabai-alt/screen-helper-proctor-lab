"""Bounded retries for temporary HTTP server errors, never for exhausted quota."""
import json
import time
import urllib.request
import urllib.error


class NoApiRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # API credentials and question images must never be forwarded to a redirect target.
        raise urllib.error.HTTPError(request.full_url, code, 'API redirect refused', headers, response)


def open_request(request, *, timeout=None):
    # Default HTTPS context still verifies the server certificate and hostname.
    return urllib.request.build_opener(NoApiRedirects()).open(request, timeout=timeout)

def _request(request, decoder, *, timeout=None, retries=1, on_progress=None):
    deadline=None if timeout is None else time.monotonic()+timeout
    for attempt in range(min(2,max(0,int(retries)))+1):
        remaining=None if deadline is None else deadline-time.monotonic()
        if remaining is not None and remaining<=0:raise TimeoutError()
        try:
            if on_progress:on_progress('request')
            with open_request(request,timeout=remaining) as response:
                if on_progress:on_progress('receiving')
                return decoder(response,on_progress)
        except urllib.error.HTTPError as error:
            if getattr(error,'partial_response',False) or error.code not in (500,502,503,504) or attempt>=min(2,max(0,int(retries))):raise
            delay=2**(attempt+1)
            try:delay=max(delay,min(8,float(error.headers.get('Retry-After',0))))
            except (ValueError,TypeError,AttributeError):pass
            if deadline is not None and time.monotonic()+delay>=deadline:raise
            error.close()
            if on_progress:on_progress('retry')
            time.sleep(delay)

def request_json(request, *, timeout=None, retries=1, on_progress=None):
    return _request(request,lambda response,progress:json.load(response),timeout=timeout,retries=retries,on_progress=on_progress)

def _decode_gemini_stream(response,on_progress):
    """Assemble complete JSON output; never expose partial JSON as an answer."""
    text=[];finish=None;metadata={};feedback=None;chunks=0;lines=[];has_candidate=False
    def consume():
        nonlocal finish,metadata,feedback,chunks,has_candidate
        if not lines:return
        value='\n'.join(lines);lines.clear()
        if value.strip()=='[DONE]':return
        event=json.loads(value)
        if not isinstance(event,dict):raise ValueError('Invalid stream event')
        if 'error' in event:
            code=event['error'].get('code',502)
            error=urllib.error.HTTPError('https://generativelanguage.googleapis.com',code if isinstance(code,int) and 400<=code<=599 else 502,'Stream error',{},None)
            error.partial_response=chunks>0
            raise error
        chunks+=1
        if on_progress:on_progress('receiving')
        metadata=event.get('usageMetadata',metadata);feedback=event.get('promptFeedback',feedback)
        for candidate in event.get('candidates',[]):
            if candidate.get('index',0)!=0:continue
            has_candidate=True
            for part in candidate.get('content',{}).get('parts',[]):
                if not part.get('thought') and isinstance(part.get('text'),str):text.append(part['text'])
            finish=candidate.get('finishReason',finish)
    first=True
    for raw in response:
        line=raw.decode('utf-8').rstrip('\r\n')
        if first and line.strip():
            first=False
            # Some gateways/test transports return a regular JSON response.
            if line.lstrip().startswith('{'):
                return json.loads(line+response.read().decode('utf-8'))
        if not line:consume()
        elif line.startswith('data:'):lines.append(line[5:].lstrip(' '))
    consume()
    return {'candidates':[{'content':{'parts':[{'text':''.join(text)}]},'finishReason':finish or 'INCOMPLETE'}] if has_candidate else [],
            'usageMetadata':metadata,'promptFeedback':feedback,'_stream_chunks':chunks}

def request_gemini_stream(request, *, timeout=None, retries=1, on_progress=None):
    return _request(request,_decode_gemini_stream,timeout=timeout,retries=retries,on_progress=on_progress)
