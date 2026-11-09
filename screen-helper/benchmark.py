"""Same images and reference answers per provider. No invented GPT results."""
import json,time
from pathlib import Path
from config_store import load_config

def run(base):
 import helper
 from quiz_samples import cases
 base=Path(base);primary=load_config(base/'config.local.json')
 configs={helper.normalize_config(primary)['provider']:primary}
 for provider in ('openai','gemini'):
  path=base/(provider+'.local.json')
  if path.exists():configs[provider]=load_config(path)
 report={'desktop_captured':False,'providers':{}}
 for provider in ('gemini','openai'):
  if provider not in configs:
   report['providers'][provider]={'status':'not_configured'};continue
  config=helper.normalize_config(configs[provider]);results=[]
  router=helper.InferenceRouter()
  if config['provider']!=provider:
   report['providers'][provider]={'status':'provider_mismatch'};continue
  for name,image,expected in cases(base):
   start=time.monotonic();answer,_=router.run(image,dict(config,cache_results=False,request_timeout=config['request_timeout'] or 60,output_mode='compact'))
   results.append({'case':name,'answer':answer,'expected':expected,'ok':answer==expected,'request_ok':not answer.startswith(('API:','Capture/')),'seconds':round(time.monotonic()-start,2)})
   if answer.startswith(('API:','Capture/')):break
  report['providers'][provider]={'status':'tested','model':config['model'],'correct':sum(r['ok'] for r in results),'requests_attempted':len(results),'answers_received':sum(r['request_ok'] for r in results),'api_errors':sum(not r['request_ok'] for r in results),'results':results}
 (base/'benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 return report
