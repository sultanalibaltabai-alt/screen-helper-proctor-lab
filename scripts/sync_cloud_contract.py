"""Keep client/gateway schemas identical. No credentials, network or paid calls."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'screen-helper'))
from answers import ANSWER_SCHEMA,PROMPT

def render():
    return 'export const ANSWER_SCHEMA='+json.dumps(ANSWER_SCHEMA,ensure_ascii=False)+';\nexport const PROMPT='+json.dumps(PROMPT,ensure_ascii=False)+';\n'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--site-checkout',type=Path)
    args=parser.parse_args();targets=[ROOT/'cloud-gateway/worker/contract.mjs']
    if args.site_checkout:
        site=args.site_checkout.resolve()
        if not (site/'.openai/hosting.json').is_file():raise SystemExit('Expected the owning Sites checkout with its hosting manifest.')
        targets.append(site/'worker/contract.mjs')
    for target in targets:
        if args.check:
            if target.read_text(encoding='utf-8')!=render():raise SystemExit('Client/gateway contract differs. Run scripts/sync_cloud_contract.py and publish the matching Sites source.')
        else:target.write_text(render(),encoding='utf-8')
    print('Client and gateway answer contracts match.' if args.check else 'Updated answer contract; publish the owning Site separately.')
