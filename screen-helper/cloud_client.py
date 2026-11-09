"""Shared gateway client. Provider keys never enter this client or its ZIP."""
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import base64
from PIL import Image
from api_transport import request_json
from config_store import load_config,save_config
from answers import format_answers

GATEWAY_URL='https://study-tools-cloud-sultan-1109.satinwaterlily4.chatgpt.site'

class CloudError(Exception):
    def __init__(self,code,status=0):self.code=code;self.status=status

def _post(origin,path,body,timeout,headers=None,on_progress=None):
    request=urllib.request.Request(origin+path,data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'ScreenHelper/8.5',**(headers or {})},method='POST')
    try:return request_json(request,timeout=timeout,retries=0,on_progress=on_progress)
    except urllib.error.HTTPError as error:
        allowed={'cloud_not_configured','authentication_required','access_revoked','registration_limit','quota_reached',
            'duplicate_request','provider_quota','provider_access','provider_unavailable','incomplete_response','invalid_response','image_too_large','invalid_input'}
        try:code=json.loads(error.read(8192)).get('error')
        except (ValueError,OSError,AttributeError):code=None
        finally:error.close()
        raise CloudError(code if code in allowed else 'connection',error.code) from None

def prepare_image(png):
    with Image.open(io.BytesIO(png)) as source:
        picture=source.convert('RGB')
    for _ in range(8):
        if picture.width<=5000 and picture.height<=5000 and picture.width*picture.height<=12000000:
            buffer=io.BytesIO();picture.save(buffer,'PNG',optimize=True);data=buffer.getvalue()
            if len(data)<=2*1024*1024:return data
        ratio=min(.85,4800/picture.width,4800/picture.height,(11000000/(picture.width*picture.height))**.5)
        width,height=int(picture.width*ratio),int(picture.height*ratio)
        if min(width,height)<16:break
        picture=picture.resize((width,height),Image.Resampling.LANCZOS)
    raise CloudError('image_too_large')

def infer(png,config,base,metrics,on_progress=None):
    origin=str(config.get('cloud_url') or GATEWAY_URL).rstrip('/')
    url=urllib.parse.urlsplit(origin)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
        return 'API: cloud invalid_address'
    started=time.monotonic();budget=config.get('request_timeout',60)
    def remaining():
        value=budget-(time.monotonic()-started)
        if value<=0:raise TimeoutError()
        return value
    path=base/'cloud-session.local.json'
    session=load_config(path,for_setup=True)
    if session.get('origin')!=origin or session.get('_key_load_error'):session={}
    device=session.get('device_id') or str(uuid.uuid4())
    request_id=str(uuid.uuid4())
    try:
        data=prepare_image(png)
        for attempt in range(2):
            if not session.get('api_key') or session.get('expires_at',0)<=time.time()*1000:
                response=_post(origin,'/v1/register',{'device_id':device},min(15,remaining()),on_progress=on_progress)
                token=response.get('token')
                if not isinstance(token,str) or not token.startswith('STC_') or len(token)!=68:raise CloudError('invalid_response')
                session={'api_key':token,'expires_at':response.get('expires_at',0),'device_id':device,'origin':origin}
                save_config(path,session)
            try:
                response=_post(origin,'/v1/infer',{'image':base64.b64encode(data).decode('ascii')},remaining(),
                    {'Authorization':'Bearer '+session['api_key'],'Idempotency-Key':request_id},on_progress)
                metrics.update(http_status=200,model_used=response.get('model'),model_returned=response.get('model'),endpoint='shared_gateway')
                if on_progress:on_progress('validating')
                return format_answers(json.dumps(response['result'],ensure_ascii=False),compact=config.get('output_mode')=='compact')
            except CloudError as error:
                if attempt==0 and error.code=='authentication_required':session['api_key']='';continue
                raise
        raise CloudError('authentication_required')
    except CloudError as error:
        metrics.update(http_status=error.status,cloud_error=error.code)
        return 'API: cloud '+error.code
    except (urllib.error.URLError,TimeoutError,OSError):
        return 'API: cloud connection'
    except (ValueError,TypeError,KeyError,AttributeError):
        return 'API: cloud invalid_response'
