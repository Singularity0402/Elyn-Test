from pathlib import Path
from PIL import Image
import json,hashlib,re
p=Path(__file__).resolve().parent
project=p.parent
data=json.loads((p/'원본과기록/출력검수.json').read_text(encoding='utf-8'))
assets=json.loads((p/'assets.json').read_text(encoding='utf-8'))
policy=json.loads((project/'automation_2026-11-03/policy.json').read_text(encoding='utf-8'))
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
def lum(rgb):
    v=[x/255 for x in rgb]
    v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v]
    return sum(x*y for x,y in zip(v,[.2126,.7152,.0722]))
errors=[];rows=[]
for row in data['entries']:
    key=row['key'];a=next(x for x in assets['entries'] if x['key']==key)
    final=Image.open(p/row['file']).convert('RGB');final.load()
    jpg=Image.open(p/row['jpg']);jpg.load()
    if final.size!=(1080,1350) or jpg.size!=(1080,1350):errors.append(key+': dimensions')
    if sha(p/row['file'])!=row['final_sha256']:errors.append(key+': final hash')
    if sha(p/row['source'])!=row['source_sha256']:errors.append(key+': source hash')
    logo_path=project/('automation_2026-11-03/.private/logo_'+row['logo_variant']+'.png')
    if sha(logo_path)!=policy['logos'][row['logo_variant']]['sha256']:errors.append(key+': logo source')
    logo=Image.open(logo_path).convert('RGBA');pre=Image.open(p/'.private'/(key+'_prelogo.png')).convert('RGB')
    opaque_mismatch=0;max_delta=0;visible=0
    for y in range(logo.height):
        for x in range(logo.width):
            r,g,b,alpha=logo.getpixel((x,y))
            if not alpha:continue
            visible+=1;actual=final.getpixel((x,y));background=pre.getpixel((x,y))
            expected=tuple(round((v*alpha+bg*(255-alpha))/255) for v,bg in zip((r,g,b),background))
            max_delta=max(max_delta,max(abs(i-j) for i,j in zip(actual,expected)))
            if alpha==255 and actual!=(r,g,b):opaque_mismatch+=1
    if opaque_mismatch or max_delta>1:errors.append(key+': logo compositing')
    bg=Image.open(p/'.private'/(key+'_background.png')).convert('RGB')
    minimum=100
    for b in row['text_bounds']:
        if min(b['x'],b['y'])<24 or b['x']+b['width']>1056 or b['y']+b['height']>1332:errors.append(key+': text bound')
        fg=lum(tuple(int(b['color'][i:i+2],16) for i in (1,3,5)))
        for y in range(b['y'],b['y']+b['height']):
            for x in range(b['x'],b['x']+b['width']):
                v=lum(bg.getpixel((x,y)));minimum=min(minimum,(max(v,fg)+.05)/(min(v,fg)+.05))
    if minimum<4.5:errors.append(key+': contrast')
    text=(p/(key+'_제출문구.md')).read_text(encoding='utf-8')
    if len(a['description'])>500 or a['description'] not in text:errors.append(key+': description')
    if not all(t in text for t in ['#햇반','#햇반AI공모전','#갓지은아이디어','@hetbahn.30years']):errors.append(key+': tags')
    rows.append({'key':key,'final':row['file'],'sha256':row['final_sha256'],'decoded_dimensions':list(final.size),'all_alpha_logo_pixels':visible,'opaque_logo_mismatch':opaque_mismatch,'alpha_formula_max_channel_delta':max_delta,'conservative_text_contrast':minimum,'description_chars':len(a['description']),'selected':key!='K'})
old=[]
for key,a in policy['assets'].items():
    ok=sha(project/a['path'])==a['sha256'];old.append({'key':key,'unchanged':ok})
    if not ok:errors.append('old '+key+' modified')
prior=json.loads((project/'expansion_2026-11-04/원본과기록/출력검수.json').read_text(encoding='utf-8'))
for a in prior['entries']:
    ok=sha(project/'expansion_2026-11-04'/a['file'])==a['png_sha256'];old.append({'key':a['key'],'unchanged':ok})
    if not ok:errors.append('old '+a['key']+' modified')
generation=json.loads((p/'실제생성기록.json').read_text(encoding='utf-8'))
for r in generation['entries']:
    with Image.open(p/r['saved']) as im:im.load()
    if sha(p/r['saved'])!=r['sha256']:errors.append(r['key']+': generation hash')
out={'date':'2026-11-11','status':'PASS_FILES_ONLY' if not errors else 'FAIL','entries':rows,'prior_8_unchanged':old,'actual_generation_calls':generation['actual_calls'],'errors':errors,'limitations':['Not physical tests','Not audience measurements','Not contest submission or winning verification','Does not provide actual service screenshots']}
(p/'독립파일검사.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':out['status'],'entries':len(rows),'old_assets':len(old),'generation_calls':generation['actual_calls'],'errors':errors,'min_contrast':min(r['conservative_text_contrast'] for r in rows)},ensure_ascii=True))
raise SystemExit(bool(errors))
