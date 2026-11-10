import json,math,re
from pathlib import Path
from datetime import datetime,timezone,timedelta

repo=Path(__file__).resolve().parents[3]
base=Path(__file__).resolve().parent
data=json.loads((base/'opportunities.json').read_text(encoding='utf-8'))
kst=timezone(timedelta(hours=9))
errors=[]
converted=[]
entries=data['entries']
ids=[e['id'] for e in entries]
if len(ids)!=len(set(ids)): errors.append('duplicate ids')
confirmed=[e for e in entries if e['status']=='RULES_CONFIRMED']
for e in entries:
    for field in ('deadline','round2','reported_deadline'):
        local=e.get(field+'_local')
        target=e.get(field+'_kst')
        if local and target:
            got=datetime.fromisoformat(local).astimezone(kst).isoformat()
            if got!=target: errors.append(e['id']+': '+field+' mismatch')
            converted.append({'id':e['id'],'field':field,'kst':got})
    for u in e.get('sources',[]):
        if not u.startswith('https://'): errors.append(e['id']+': invalid source URL')
    if e['status']=='RULES_CONFIRMED':
        for k in ('korea_basis','ai_basis','top_cash','payout','fee','sources'):
            if not e.get(k): errors.append(e['id']+': missing '+k)
        if e['top_cash']['amount']<=0: errors.append(e['id']+': invalid prize')
        if e['deadline_kst'][:10]<data['as_of']: errors.append(e['id']+': expired')
if len(confirmed)!=5: errors.append('unexpected confirmed count')
for p in [base/'README.md',repo/'docs/contests/hetbahn_2026/product_review_2026-11-11/H2_후속판정.md']:
    text=p.read_text(encoding='utf-8')
    for href in re.findall(r'\]\(([^)]+)\)',text):
        if '://' not in href and not href.startswith('#'):
            if not (p.parent/href).exists(): errors.append('missing relative file: '+href)
out={'as_of':data['as_of'],'status':'PASS_RECORD_CHECK_ONLY' if not errors else 'FAIL',
     'records':len(entries),'rules_confirmed':len(confirmed),'holds':sum(e['status'].startswith('HOLD') or e['status']=='RULES_CONFIRMED_PAYMENT_DETAILS_PENDING' for e in entries),
     'excluded':sum(e['status'].startswith('EXCLUDED') for e in entries),
     'timezone_conversions':converted,'errors':errors,
     'limits':'Only stored record consistency, arithmetic, URL syntax and local links. No current website refresh, eligibility certification, account verification, submission or prize receipt.'}
(base/'record_check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,ensure_ascii=True))
raise SystemExit(bool(errors))
