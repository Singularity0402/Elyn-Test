from pathlib import Path
from PIL import Image,ImageChops
import json,hashlib,sys,subprocess,zipfile
ROOT=Path(__file__).resolve().parent
KEYS=set('CDEFGH')
checks=[]
def digest(data): return hashlib.sha256(data).hexdigest()
def sha(p): return digest(p.read_bytes())
def pairs(items):
    d={}
    for k,v in items:
        if k in d: raise ValueError('duplicate JSON key')
        d[k]=v
    return d
def load(p):
    return json.loads(p.read_text(encoding='utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def contained(name):
    p=(ROOT/name).resolve()
    if not p.is_relative_to(ROOT) or p==ROOT: raise ValueError('path outside portfolio')
    return p
def record(name,ok,details=None):
    checks.append({'id':name,'status':'PASS' if ok else 'FAIL','details':details})
    return ok
def image(p):
    with Image.open(p) as im: im.verify()
    im=Image.open(p);im.load();return im
def lum(rgb):
    c=[v/255 for v in rgb]
    c=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in c]
    return sum(v*w for v,w in zip(c,[.2126,.7152,.0722]))
def ratio(a,b):
    x,y=lum(a),lum(b)
    return (max(x,y)+.05)/(min(x,y)+.05)
def overlap(a,b):
    return min(a['x']+a['width'],b['x']+b['width'])>max(a['x'],b['x']) and min(a['y']+a['height'],b['y']+b['height'])>max(a['y'],b['y'])
def semantic(p): return digest(json.dumps(load(p),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))
def main():
    lock=load(contained('selection.lock.json'))
    assets=load(contained('assets.json'))['entries']
    outputs=load(contained('원본과기록/출력검수.json'))['entries']
    history=load(contained('원본과기록/실제생성기록.json'))['generations']
    audit=load(contained('원본과기록/120규칙_추가6작.json'))['entries']
    binding=load(contained('원본과기록/검토대상_해시.json'))
    original=ROOT.parent/'quality_2026-11-02'/'규칙120.json'
    record('original_rules_pin',semantic(original)==lock['original_rules_semantic_sha256'])
    rule_ids={r['id'] for r in load(original)['rules']}
    record('entry_sets',len(assets)==6 and {a['key'] for a in assets}==KEYS and {a['key'] for a in outputs}==KEYS and {a['key'] for a in audit}==KEYS)
    for name,expected in lock['files'].items():
        p=contained(name)
        record('pin:'+name,p.is_file() and sha(p)==expected)
    record('history_count',len(history)==12 and len({(g['key'],g['version']) for g in history})==12 and sum(g['selected'] for g in history)==6)
    for g in history:
        p=contained(g['preserved_source'])
        im=image(p)
        record('generation:'+g['key']+str(g['version']),sha(p)==g['source_sha256'] and im.format=='PNG' and im.size==(1122,1402))
    policy=load(ROOT.parent/'automation_2026-11-03'/'policy.json')
    for a in assets:
        k=a['key'];o=next(r for r in outputs if r['key']==k)
        png=contained(o['file']);source=contained(o['source'])
        im=image(png);native=image(source)
        record(k+':png',im.format=='PNG' and im.size==(1080,1350) and im.mode in ['RGB','RGBA'] and im.convert('RGBA').getchannel('A').getextrema()==(255,255))
        record(k+':source',native.format=='PNG' and native.size==tuple(o['source_dimensions']) and sha(source)==o['source_sha256'])
        jpg=image(contained(o['jpg']))
        record(k+':jpg',jpg.format=='JPEG' and jpg.size==(1080,1350) and jpg.mode=='RGB')
        record(k+':final_binding',sha(png)==o['png_sha256']==binding['new_entries'][k] and a['version']==o['selected_version'])
        selected=[g for g in history if g['key']==k and g['selected']]
        record(k+':selected_history',len(selected)==1 and selected[0]['version']==a['version'] and selected[0]['source_sha256']==sha(source))
        description=a['description'];md=contained(k+'_제출문구.md').read_text(encoding='utf-8')
        record(k+':copy',0<len(description)<=500 and len(description)==o['description_chars'] and description in md and a['caption'] in md and all(s in a['caption'] for s in ['@hetbahn.30years','#햇반','#햇반AI공모전','#갓지은아이디어']))
        boxes=o['text_bounds']
        wanted=[*a['headline'],a['sub'],a['title']+' · 미래 제품 상상','미래 제품 상상 · 실제 출시 제품 아님']
        valid=len(boxes)==5 and [b['text'] for b in boxes]==wanted and all(b['x']>=24 and b['y']>=24 and b['x']+b['width']<=1056 and b['y']+b['height']<=1332 for b in boxes)
        valid=valid and not any(overlap(boxes[i],boxes[j]) for i in range(len(boxes)) for j in range(i+1,len(boxes)))
        valid=valid and not any(overlap(b,{'x':64,'y':49,'width':170,'height':69}) for b in boxes)
        record(k+':text_geometry',valid)
        # Independent decoder/compositor. Opaque official pixels are exact;
        # different integer-alpha compositors may round semitransparent pixels by one level.
        logo_path=ROOT.parent/'automation_2026-11-03'/'.private'/('logo_'+a['logo']+'.png')
        logo=image(logo_path).convert('RGBA')
        record(k+':official_logo_file',sha(logo_path)==policy['logos'][a['logo']]['sha256']==o['logo_sha256'] and logo.size==(1080,1350))
        before=image(contained('.private/'+k+'_before_logo.png')).convert('RGBA')
        expected=Image.alpha_composite(before,logo)
        actual=im.convert('RGBA')
        lp,ep,ap=logo.load(),expected.load(),actual.load()
        visible=opaque_bad=alpha_bad=max_delta=0
        left,top,right,bottom=logo.getchannel('A').getbbox()
        for y in range(top,bottom):
            for x in range(left,right):
                if not lp[x,y][3]: continue
                visible+=1
                delta=max(abs(ap[x,y][i]-ep[x,y][i]) for i in range(4))
                max_delta=max(max_delta,delta)
                if delta: alpha_bad+=1
                if lp[x,y][3]==255 and ap[x,y]!=lp[x,y]: opaque_bad+=1
        record(k+':official_logo_pixels',visible==o['logo_alpha_positive_pixels'] and opaque_bad==0 and max_delta<=1 and o['logo_mismatches']==0,
               {'alpha_positive_pixels':visible,'opaque_mismatches':opaque_bad,'independent_alpha_rounding_differences':alpha_bad,'independent_max_delta':max_delta,'production_exact_mismatches':o['logo_mismatches']})
        bg=image(contained('.private/'+k+'_resized_photo.png')).convert('RGB')
        bp=bg.load()
        for b in boxes:
            rgb=tuple(bytes.fromhex(b['color'][1:]))
            minimum=min(ratio(rgb,bp[x,y]) for y in range(b['y'],b['y']+b['height']) for x in range(b['x'],b['x']+b['width']))
            record(k+':contrast:'+b['role'],minimum>=4.5,{'whole_box_min_ratio':round(minimum,3),'target':4.5,'scope':'internal typography contrast, not human legibility certification'})
        aud=next(r for r in audit if r['key']==k)
        rows=aud['rows'];pending={r['id'] for r in rows if r['status']=='PENDING'}
        counts={s:sum(r['status']==s for r in rows) for s in ['PASS','FAIL','PENDING','NA']}
        record(k+':audit_rows',len(rows)==120 and len({r['id'] for r in rows})==120 and {r['id'] for r in rows}==rule_ids and all(r['evidence'] and r['files'] for r in rows) and not counts['FAIL'])
        record(k+':external_not_fabricated',pending=={'J08','L02','L03','L04','L05','L06','L08'} and counts['PENDING']==7,counts)
        for ref in {f for r in rows for f in r['files']}:
            if not contained(ref).is_file(): record(k+':evidence_reference',False,ref)
    for k,name in [('A','A_갓지은편지.png'),('B','B_스물네장의계절.png')]:
        p=ROOT.parent/'audit_2026-11-03'/name
        record(k+':prior_preserved',sha(p)==binding['prior_entries'][k])
    # Re-run isolated local software QA; never count it as a real user or generation screen.
    result=subprocess.run(['node',str(ROOT/'verify_gallery.cjs')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    record('gallery_process',result.returncode==0,{'exit_code':result.returncode,'stderr':result.stderr[-1000:]})
    if result.returncode==0:
        ui=load(contained('원본과기록/갤러리_동작검사.json'))
        record('gallery_binding',ui['status']=='PASS' and ui['html_sha256']==sha(contained('gallery.html')) and ui['external_requests']==[] and ui['asset_hashes']=={a['key']:sha(contained(a['stem']+'.png')) for a in assets} and {v['viewport'] for v in ui['viewports']}=={1200,360})
    return assets,outputs
def bundle(assets,outputs):
    import posixpath,urllib.parse,re
    items=[]
    for a in assets:
        k=a['key'];o=next(o for o in outputs if o['key']==k)
        for source,target in [(a['stem']+'.png','01_출품PNG/'+a['stem']+'.png'),(a['stem']+'.jpg','02_JPG대체/'+a['stem']+'.jpg'),(k+'_제출문구.md','03_신청서와캡션/'+k+'_제출문구.md'),(o['source'],'04_생성원본과기록/'+Path(o['source']).name)]:
            items.append((source,target))
    extras=['실제생성기록.json','출력검수.json','120규칙_추가6작.json','무문구_첫검토.json','시안_수정후검토.json','완성8작품_비교와제품검토.json','검토대상_해시.json','갤러리_동작검사.json']
    items += [('원본과기록/'+name,'05_검수기록/'+name) for name in extras]
    for name in ['추가6작품_제작검수보고.md','기획_제품화_심리.md','제작공정_사전기준.md','120규칙_판정안내.md','관객검증_사전계획.md']:
        items.append((name,'05_검수기록/'+name))
    items += [('README.md','먼저읽기.md'),('추가6작품_한눈에.png','검토용_6작품한눈에.png'),('gallery.html','gallery.html')]
    mapping=dict(items)
    remote='https://github.com/Singularity0402/Elyn-Test/blob/claude/clever-knuth-9b2kk8/docs/contests/hetbahn_2026/expansion_2026-11-04/'
    def archive_link(url,source,target):
        if re.match(r'^(?:https?:|mailto:|#)',url): return url
        resolved=posixpath.normpath(posixpath.join(posixpath.dirname(source),urllib.parse.unquote(url)))
        if resolved in mapping:
            return posixpath.relpath(mapping[resolved],posixpath.dirname(target) or '.')
        if resolved=='검증결과.json':
            return posixpath.relpath('05_검수기록/파일검수_요약.json',posixpath.dirname(target) or '.')
        if resolved in {'검증실행.cmd','추가6작품_제출자료.zip'}:
            return remote+urllib.parse.quote(resolved)
        raise ValueError('Unmapped archive link '+resolved)
    files=[];payloads={}
    for source,target in items:
        p=contained(source)
        if '.private' in p.parts or p.suffix.lower() in ['.otf','.ttf'] or p.name.startswith('logo_'): raise ValueError('standalone restricted asset')
        original=p.read_bytes();data=original
        if p.suffix=='.md':
            text=original.decode('utf-8')
            text=re.sub(r'(\[[^\]]*\]\()([^)]*)(\))',lambda m:m[1]+archive_link(m[2],source,target)+m[3],text)
            if source=='README.md':
                text='> 배포 묶음 안내: 출품파일·선택원본·검토기록을 담았습니다. 재검증 실행 도구와 미선택 시안은 작업 저장소에 있습니다. 실제 생성 서비스 화면 캡처는 별도 필요합니다.\n\n'+text
            data=text.encode('utf-8')
        elif p.suffix=='.html':
            text=original.decode('utf-8')
            text=re.sub(r'((?:href|src)=")([^"]*)(")',lambda m:m[1]+archive_link(m[2],source,target)+m[3],text)
            data=text.encode('utf-8')
        payloads[target]=data
        files.append({'source':source,'source_sha256':digest(original),'archive':target,'bytes':len(data),'sha256':digest(data),'rewritten_links':data!=original})
    summary={'status':'FILES_PASS_EXTERNAL_PENDING','scope':'file checks before package creation, not proof of product/audience/submission','check_count':len(checks),'checks':checks.copy(),'pending_per_entry':['J08','L02','L03','L04','L05','L06','L08'],'actual_data_supplied':{'service_generation_screens':0,'human_responses':0,'public_metrics':0,'verified_submissions':0}}
    summary_name='05_검수기록/파일검수_요약.json'
    summary_data=json.dumps(summary,ensure_ascii=False,indent=2).encode('utf-8')
    payloads[summary_name]=summary_data
    files.append({'source':None,'archive':summary_name,'bytes':len(summary_data),'sha256':digest(summary_data),'generated':'current verification snapshot; no self-referential ZIP hash'})
    links=0
    for name,data in payloads.items():
        targets=[]
        if name.endswith('.html'): targets=re.findall(r'(?:href|src)="([^"]*)"',data.decode('utf-8'))
        elif name.endswith('.md'): targets=re.findall(r'\[[^\]]*\]\(([^)]*)\)',data.decode('utf-8'))
        for target_url in targets:
            if re.match(r'^(?:https?:|mailto:|#)',target_url): continue
            wanted=posixpath.normpath(posixpath.join(posixpath.dirname(name),urllib.parse.unquote(target_url)))
            if wanted not in payloads: raise ValueError('Broken ZIP link '+name+' -> '+wanted)
            links+=1
    record('package_internal_links',True,{'resolved_local_links':links})
    manifest={'date':'2026-11-04','scope':'추가6작 완성PNG/JPG·문구·선택생성원본·검토기록. 실제 서비스 제작 화면 캡처는 별도 필요. MD/HTML 링크는 묶음 폴더에 맞춰 재작성.','files':files}
    target=contained('추가6작품_제출자료.zip')
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for item in files:
            if item['source'] is not None and sha(contained(item['source']))!=item['source_sha256']: raise ValueError('changed during package')
            archive.writestr(item['archive'],payloads[item['archive']])
        archive.writestr('파일목록_SHA256.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None: raise ValueError('ZIP CRC failure')
        if len(archive.namelist())!=len(files)+1 or len(set(archive.namelist()))!=len(archive.namelist()): raise ValueError('ZIP count/duplicate failure')
        for item in files:
            if digest(archive.read(item['archive']))!=item['sha256']: raise ValueError('ZIP content hash')
    (ROOT/'제출파일_목록_SHA256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    record('package_crc_and_hashes',True,{'files':len(files)+1,'sha256':sha(target),'bytes':target.stat().st_size})
    return {'path':target.name,'sha256':sha(target),'bytes':target.stat().st_size,'entries':len(files)+1}
if __name__=='__main__':
    package=None
    try:
        assets,outputs=main()
        if all(c['status']=='PASS' for c in checks): package=bundle(assets,outputs)
    except Exception as exc:
        record('unexpected_error',False,type(exc).__name__+': '+str(exc))
    failed=[c for c in checks if c['status']=='FAIL']
    if failed:
        stale=contained('추가6작품_제출자료.zip')
        if stale.is_file(): stale.unlink()
    report={'artifact_date':'2026-11-04','status':'FAIL' if failed else 'FILES_PASS_EXTERNAL_PENDING','file_validation_complete':bool(checks) and not failed,'submission_ready':False,'scope':'new C-H file checks only; not product safety, audience or award validation','actual_data_supplied':{'service_generation_screens':0,'human_responses':0,'public_metrics':0,'verified_submissions':0},'pending_per_entry':['J08','L02','L03','L04','L05','L06','L08'],'check_count':len(checks),'failed_count':len(failed),'checks':checks,'package':package}
    (ROOT/'검증결과.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':report['status'],'checks':len(checks),'failed':failed,'package_bytes':package['bytes'] if package else None},ensure_ascii=True))
    sys.exit(1 if failed else 2)
