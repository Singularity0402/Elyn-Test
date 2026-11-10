from pathlib import Path
import json,hashlib,shutil
p=Path(__file__).resolve().parent
d=p/'원본과기록';d.mkdir(exist_ok=True)
native=Path('C:/Users/user/.codex/generated_images/01a18909-ba7e-7b71-be45-6d9a63b0b87d')
out=[]
for row in json.loads((p/'generation_plan.json').read_text(encoding='utf-8')):
    src=native/row['file'];dest=d/(row['key']+'_생성원본.png')
    shutil.copy2(src,dest)
    out.append({**row,'native':str(src),'saved':dest.relative_to(p).as_posix(),'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'prompt_text':(p/row['prompt']).read_text(encoding='utf-8')})
(p/'실제생성기록.json').write_text(json.dumps({'date':'2026-11-11','service':'OpenAI Codex 내장 이미지 생성 기능','actual_calls':len(out),'entries':out,'not_service_screenshots':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(str(len(out))+' exact generation records preserved.')
