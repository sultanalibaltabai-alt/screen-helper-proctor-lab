"""One total budget, optional explicit reserve, and cooldown after overload."""
import hashlib
import time
from inference import execute,RequestCancelled,RequestDeadline,RequestBusy

class InferenceRouter:
    def __init__(self,runner=execute,clock=time.monotonic):
        self.runner=runner;self.clock=clock;self.cooldowns={};self.credential=None;self.cache={}
    def run(self,image,config,*,cancel=None,on_progress=None):
        credential=(config.get('provider'),config.get('api_key'))
        if credential!=self.credential:self.cooldowns.clear();self.cache.clear();self.credential=credential
        started=self.clock();budget=config.get('request_timeout',60)
        models=[config['model']]
        reserve=str(config.get('fallback_model','')).strip()
        if config['provider']=='gemini' and reserve and reserve not in models:models.append(reserve)
        cache_key=(hashlib.sha256(image).digest(),tuple(models),config.get('reasoning_mode'),config.get('gemini_api'))
        cached=self.cache.get(cache_key)
        if config.get('cache_results',True) and cached and self.clock()-cached[0]<60:
            if on_progress:on_progress('cached')
            return cached[1],dict(cached[2],cache_hit=True,attempts=[])
        attempts=[];last_answer='API: модель временно недоступна';last_metrics={}
        for index,model in enumerate(models):
            if cancel and cancel.is_set():raise RequestCancelled()
            if self.cooldowns.get(model,0)>self.clock():
                attempts.append({'model':model,'skipped':'cooldown'});continue
            remaining=max(0,budget-(self.clock()-started)) if budget else None
            if remaining is not None and remaining<=0:break
            allocation=remaining
            if index==0 and len(models)>1:allocation=min(15,remaining*.6) if remaining is not None else 15
            if index and on_progress:on_progress('fallback')
            current=dict(config,model=model,api_retries=1)
            if index and model.startswith('gemini-2.'):
                current.update(gemini_api='generate_content',streaming=False)
            try:answer,metrics=self.runner(image,current,timeout=allocation,cancel=cancel,on_progress=on_progress)
            except RequestDeadline:answer='API: превышено время ожидания';metrics={'deadline_exceeded':True}
            except RequestBusy:return 'API: уже идёт другой запрос',{'busy':True,'attempts':attempts,'model_used':None}
            attempts.append({'model':model,'answer':answer,'http_status':metrics.get('http_status')})
            last_answer=answer;last_metrics=metrics
            transient=metrics.get('http_status') in (500,502,503,504) or metrics.get('deadline_exceeded')
            if transient:self.cooldowns[model]=self.clock()+60
            if metrics.get('http_status')==429:self.cooldowns[model]=self.clock()+60
            if not answer.startswith(('API:','Capture')):
                result=dict(metrics,model_used=model,attempts=attempts,cache_hit=False)
                if '?' not in answer and config.get('cache_results',True):self.cache[cache_key]=(self.clock(),answer,result)
                if len(self.cache)>8:self.cache.pop(next(iter(self.cache)))
                return answer,result
            if not transient:break  # Never hop models to hide key/access/quota errors.
        if attempts and all(a.get('skipped')=='cooldown' for a in attempts):
            delay=max(1,int(min(self.cooldowns[m]-self.clock() for m in models if m in self.cooldowns)))
            last_answer=f'API: временная пауза, повтор через {delay} с'
        return last_answer,dict(last_metrics,model_used=None,attempts=attempts,cache_hit=False)
