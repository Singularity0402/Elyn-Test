"""새 증거를 등록하지만 화면 진위나 관객 효과를 승인하지 않는다."""
import hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
KINDS=('responses','reviews','metrics','history')
def _read(path):
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:raise ValueError('duplicate intake key')
            out[key]=value
        return out
    return json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite intake JSON')))
def _safe(root,path):
    path=path.resolve()
    if not path.is_relative_to(root):raise ValueError('inbox path escapes input root')
    return path
def discover(policy,root):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    manifest=_safe(root,root/'evidence.json')
    if not manifest.exists():
        template=_safe(root,root/'evidence.example.json')
        data=_read(template) if template.exists() else {'schema_version':1,'responses':[],'reviews':[],'screenshots':[],'metrics':[],'history':[]}
    else:data=_read(manifest)
    if set(data)!={'schema_version','responses','reviews','screenshots','metrics','history'} or data['schema_version']!=1 or any(not isinstance(data[k],list) for k in (*KINDS,'screenshots')):raise ValueError('invalid intake manifest')
    original=json.dumps(data,sort_keys=True)
    added={k:0 for k in (*KINDS,'screenshots')}
    for kind in KINDS:
        folder=_safe(root,root/'inbox'/kind);folder.mkdir(parents=True,exist_ok=True)
        for p in sorted(folder.glob('*.json')):
            _safe(root,p)
            name=p.relative_to(root).as_posix()
            if name not in data[kind]:data[kind].append(name);added[kind]+=1
    generated=_safe(root,root/'.generated');generated.mkdir(exist_ok=True)
    media=_safe(root,generated/'media');media.mkdir(exist_ok=True)
    for arm in ('A','B'):
        folder=_safe(root,root/'inbox/captures'/arm);folder.mkdir(parents=True,exist_ok=True)
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() not in ('.png','.jpg','.jpeg'):continue
            _safe(root,p)
            body=p.read_bytes();digest=hashlib.sha256(body).hexdigest()
            dest=_safe(root,media/(digest+p.suffix.lower()))
            if not dest.exists():dest.write_bytes(body)
            elif hashlib.sha256(dest.read_bytes()).hexdigest()!=digest:raise ValueError('immutable capture copy changed')
            descriptor=_safe(root,generated/('capture-'+arm+'-'+digest+'.json'))
            item={'entry':arm,'artifact_sha256':policy['assets'][arm]['sha256'],'source_sha256':policy['assets'][arm]['source_sha256'],'capture_path':dest.relative_to(root).as_posix(),'captured_at':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),'capture_time_basis':'filesystem_mtime_unverified','binding_status':'proposed_only_requires_actual_content_review'}
            if descriptor.exists():
                old=_read(descriptor)
                if any(old.get(k)!=item[k] for k in ('entry','artifact_sha256','source_sha256','capture_path')):raise ValueError('capture descriptor belongs to a different revision; use a new input directory/protocol')
            else:descriptor.write_text(json.dumps(item,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
            name=descriptor.relative_to(root).as_posix()
            if name not in data['screenshots']:data['screenshots'].append(name);added['screenshots']+=1
    if original!=json.dumps(data,sort_keys=True) or not manifest.exists():
        part=_safe(root,manifest.with_suffix('.new'));part.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');part.replace(manifest)
    if not _safe(root,root/'submission.json').exists():
        template=_safe(root,root/'submission.example.json')
        if template.exists():shutil.copyfile(template,root/'submission.json')
    return {'status':'PASS','registered_new':added,'registered_totals':{k:len(data[k]) for k in added},'claim':'자동 등록만 수행. 자료 진위·의미·효과는 승인하지 않음.'}
