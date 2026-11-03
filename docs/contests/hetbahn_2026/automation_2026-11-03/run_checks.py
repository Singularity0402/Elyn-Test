#!/usr/bin/env python3
"""햇반 최종 파일·검증 도구·실제 증거를 한 번에 검사한다."""
from __future__ import annotations
import argparse, base64, copy, hashlib, html, importlib.util, json, os, re, subprocess, sys, time, uuid
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile, ZIP_DEFLATED

if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
HERE=Path(__file__).resolve().parent
KST=timezone(timedelta(hours=9))
EXTERNAL=("J08","L02","L03","L04","L05","L06","L08")
class InvalidEvidence(ValueError): pass
def pairs(items):
    out={}
    for k,v in items:
        if k in out: raise InvalidEvidence("duplicate JSON key: "+k)
        out[k]=v
    return out
def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),object_pairs_hook=pairs,parse_constant=lambda s: (_ for _ in ()).throw(InvalidEvidence("nonfinite JSON: "+s)))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def within(root,name):
    root=Path(root).resolve();p=(root/name).resolve()
    if not p.is_relative_to(root): raise InvalidEvidence("path outside allowed directory: "+str(name))
    return p
def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
def iso(value):
    if not isinstance(value,str): return None
    try:
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
        return d if d.tzinfo else None
    except ValueError:return None

class TextOnly(HTMLParser):
    def __init__(self):super().__init__();self.bits=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style"):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ("script","style") and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip:self.bits.append(data)
def official_fingerprint(raw):
    p=TextOnly();p.feed(raw);text=re.sub(r"\s+"," "," ".join(p.bits))
    compact=re.sub(r"\s+","",text)
    checks={
      "contest_title":"갓지은AI디어공모전" in compact,
      "deadline":"11월13일(금)23:59" in compact and "2026년10월26일" in compact,
      "image_ratios":"정방형(1:1)" in compact and "세로형(4:5)" in compact,
      "real_ai_history_required":"제작히스토리캡처본" in compact and "AI서비스" in compact,
      "future_disclosure":"실제출시된제품이나확정된기능" in compact,
      "unlimited_entries":"출품작품수에는제한이없으나" in compact,
      "public_until":"2026년11월27일" in compact,
      "all_tags":all(s in compact for s in ("#햇반","#햇반AI공모전","#갓지은아이디어","@hetbahn.30years")),
    }
    return checks

def form_constraints(raw):
    match=re.search(r"FB_PUBLIC_LOAD_DATA_\s*=\s*",raw)
    if not match:raise InvalidEvidence("공식 문항 정의가 없음")
    data,_=json.JSONDecoder().raw_decode(raw[match.end():])
    nodes=data[1][1]
    descriptions=[node for node in nodes if isinstance(node,list) and len(node)>2 and isinstance(node[1],str) and "출품작설명" in re.sub(r"\s+","",node[1])]
    if len(descriptions)!=1:raise InvalidEvidence("작품 설명 문항을 단일하게 확인할 수 없음")
    node=descriptions[0]
    hints=re.findall(r"(\d+)\s*자\s*이내|최대\s*(\d+)\s*자",json.dumps(node,ensure_ascii=False))
    limits={int(a or b) for a,b in hints}
    for item in node[4]:
        if len(item)>4 and isinstance(item[4],list):
            for validation in item[4]:
                if isinstance(validation,list) and len(validation)>2 and validation[:2]==[6,202]:
                    limits.update(int(x) for x in validation[2])
    if len(limits)!=1:raise InvalidEvidence("설명 글자 제한이 없거나 서로 다름")
    return {"description_limit":limits.pop(),"question_definitions_sha256":canonical(nodes)}

def check_official(policy,offline,cache):
    out={"id":"official_source","status":"PENDING","url":policy["official_source"]["url"],"checked_at":datetime.now(timezone.utc).isoformat()}
    if offline:
        out["reason"]="오프라인 실행: 이번 실행에서 공식 요강 변경 여부를 확인하지 않음."
        return out
    try:
        req=Request(out["url"],headers={"User-Agent":"Mozilla/5.0"})
        with urlopen(req,timeout=15) as response:
            final=response.geturl()
            if urlparse(final).hostname!="docs.google.com":raise InvalidEvidence("unexpected official source redirect")
            raw=response.read(4000000).decode("utf-8")
        checks=official_fingerprint(raw)
        constraints=form_constraints(raw)
        checks["description_limit"]=constraints["description_limit"]==policy["official_source"]["description_limit"]
        checks["question_definitions_unchanged"]=constraints["question_definitions_sha256"]==policy["official_source"]["question_definitions_sha256"]
        out.update(checks=checks,observed_constraints=constraints,body_sha256=hashlib.sha256(raw.encode()).hexdigest())
        out["status"]="PASS" if all(checks.values()) else "FAIL"
        out["reason"]="필수 안내의 의미 표지를 확인함." if out["status"]=="PASS" else "공식 안내와 고정 기준이 달라 재확인이 필요함."
        if out["status"]=="PASS":write_json(cache/"official_last_checked.json",out)
    except (InvalidEvidence,ValueError,TypeError,KeyError,IndexError) as e:
        out.update(status="FAIL",reason="공식 문항 정의·제한이 일치하지 않음: "+str(e))
    except Exception as e:
        out.update(status="PENDING",reason="공식 안내를 이번 실행에서 확인하지 못함: "+str(e))
    return out
def ensure_brand_cache(policy,cache,offline=False):
    cache.mkdir(parents=True,exist_ok=True);rows=[]
    for key,item in policy["logos"].items():
        path=within(cache,item["cache_name"])
        if path.exists():
            ok=sha(path)==item["sha256"]
            rows.append({"id":"brand_reference_"+key,"status":"PASS" if ok else "FAIL","reason":"공식 원본 해시 일치" if ok else "캐시 변조/변경: 자동 덮어쓰지 않음"})
            continue
        if offline:
            rows.append({"id":"brand_reference_"+key,"status":"FAIL","reason":"공식 로고 검수 캐시 없음"});continue
        try:
            with urlopen(Request(item["url"],headers={"User-Agent":"Mozilla/5.0"}),timeout=15) as response:body=response.read(10000000)
            if hashlib.sha256(body).hexdigest()!=item["sha256"]:raise InvalidEvidence("official asset hash changed")
            part=path.with_suffix(".download");part.write_bytes(body);part.replace(path)
            rows.append({"id":"brand_reference_"+key,"status":"PASS","reason":"공식 원본을 취득하고 고정 해시 확인"})
        except Exception as e:rows.append({"id":"brand_reference_"+key,"status":"FAIL","reason":str(e)})
    return {"status":"PASS" if all(x["status"]=="PASS" for x in rows) else "FAIL","checks":rows}
def child(command,cwd,timeout=150):
    started=time.monotonic()
    env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"}
    try:
        proc=subprocess.run(command,cwd=str(cwd),capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,env=env)
        return {"returncode":proc.returncode,"stdout":proc.stdout,"stderr":proc.stderr,"seconds":round(time.monotonic()-started,3)}
    except Exception as e:return {"returncode":-1,"stdout":"","stderr":str(e),"seconds":round(time.monotonic()-started,3)}
def child_json(command,cwd,timeout=150):
    run=child(command,cwd,timeout)
    try:payload=json.loads(run["stdout"],object_pairs_hook=pairs)
    except Exception:payload={"status":"FAIL","error":"검사 프로세스가 유효한 JSON을 반환하지 않음"}
    if run["returncode"]!=0:payload.update(status="FAIL",process_error="검사 프로세스 비정상 종료")
    return {**payload,"execution":run}

def baseline_checks(policy,auto_root,project_root):
    checks=[]
    lock=read_json(auto_root/"baseline.lock.json")
    checks.append({"id":"policy_lock","status":"PASS" if lock["policy_sha256"]==sha(auto_root/"policy.json") else "FAIL","reason":"실행 중 기준 자동 갱신 금지"})
    rules=read_json(within(project_root,policy["manual_path"]))
    checks.append({"id":"manual_unchanged","status":"PASS" if canonical(rules)==policy["manual_semantic_sha256"] else "FAIL"})
    auditpath=within(project_root,policy["audit_path"]);audit=read_json(auditpath)
    checks.append({"id":"audit_snapshot","status":"PASS" if canonical(audit)==policy["audit_semantic_sha256"] else "FAIL"})
    rulemap={r["id"]:r["rule"] for r in rules["rules"]}
    for entry in ("A","B"):
        rows=[r for r in audit["rows"] if r["entry"]==entry]
        valid=len(rows)==120 and len({r["id"] for r in rows})==120 and all(rulemap.get(r["id"])==r["rule"] for r in rows)
        checks.append({"id":"manual_coverage_"+entry,"status":"PASS" if valid else "FAIL"})
    for review in policy["review_bindings"]:
        p=within(project_root,review["path"]);asset=policy["assets"][review["entry"]]
        expected=asset["sha256"] if review["scope"]=="current_artifact" else asset["source_sha256"]
        valid=p.is_file() and canonical(read_json(p))==review["semantic_sha256"] and expected==review["subject_sha256"]
        checks.append({"id":"review_binding_"+review["entry"],"status":"PASS" if valid else "FAIL","scope":review["scope"],"reason":"기존 AI 판단을 해당 파일 버전에만 적용; 대중 효과나 수상 입증 아님"})
    return {"status":"PASS" if all(c["status"]=="PASS" for c in checks) else "FAIL","checks":checks}

def copy_checks(policy,project_root):
    rows=[]
    for entry,path in policy["copy_paths"].items():
        try:
            text=within(project_root,path).read_text(encoding="utf-8-sig")
            desc=text.split("## 작품 설명\n",1)[1].split("\n## ",1)[0].strip()
            tags=all(t in text for t in policy["official_source"]["required_tags"])
            absolutes=re.findall(r"무조건\s*(?:우승|대상|1등)|(?:우승|수상|대상)\s*(?:확정|보장)|모든\s*사람이\s*반드시",text)
            disclosure="실제 출시 제품" in text and "아닙니다" in text
            valid=len(desc)<=policy["official_source"]["description_limit"] and tags and disclosure and not absolutes
            rows.append({"entry":entry,"status":"PASS" if valid else "FAIL","description_chars":len(desc),"copy_sha256":sha(within(project_root,path)),"required_tags":tags,"future_disclosure":disclosure,"unsupported_absolute_phrases":absolutes})
        except Exception as e:rows.append({"entry":entry,"status":"FAIL","reason":str(e)})
    return {"status":"PASS" if all(r["status"]=="PASS" for r in rows) else "FAIL","checks":rows}

def submission_checks(policy,inputs_root,evidence,now):
    path=inputs_root/"submission.json"
    if not path.exists():return {"status":"PENDING","entries":{},"missing":["공개 게시물·드라이브 주소"]}
    try:
        data=read_json(path)
        if data.get("schema_version")!=1:raise InvalidEvidence("submission schema mismatch")
        receipts=[]
        for name in data.get("receipt_refs",[]):
            rec=read_json(within(inputs_root,name));stamp=iso(rec.get("reviewed_at"))
            if rec.get("review_kind")!="public_link" or rec.get("verdict")!="verified" or not stamp or stamp>now:raise InvalidEvidence("invalid public-link review")
            if not isinstance(rec.get("reviewer"),dict) or not rec["reviewer"].get("id"):raise InvalidEvidence("public-link reviewer missing")
            receipts.append(rec)
        entries={};missing=[]
        for entry in ("A","B"):
            item=data.get("entries",{}).get(entry,{})
            states={}
            for kind,hosts in [("sns_url",{"instagram.com","www.instagram.com","youtube.com","www.youtube.com","youtu.be"}),("drive_url",{"drive.google.com","docs.google.com"})]:
                url=item.get(kind)
                if not url:
                    states[kind]="PENDING";missing.append(entry+" "+kind);continue
                parsed=urlparse(url)
                if parsed.scheme!="https" or parsed.hostname not in hosts or not parsed.path.strip("/"):raise InvalidEvidence("unsupported or invalid submission URL")
                valid=any(r.get("entry")==entry and r.get("artifact_sha256")==policy["assets"][entry]["sha256"] and r.get("target_url")==url and r.get("findings",{}).get("public_anonymous_access") is True for r in receipts)
                states[kind]="VERIFIED" if valid else "PENDING_PUBLIC_ACCESS_REVIEW"
                if not valid:missing.append(entry+" 공개 접근 확인 "+kind)
            capture=evidence.get("rule_states",{}).get(entry,{}).get("J08",{}).get("state")=="VERIFIED"
            states["ai_generation_capture"]="VERIFIED" if capture else "PENDING"
            if not capture:missing.append(entry+" 실제 제작 화면")
            entries[entry]=states
        return {"status":"PASS" if not missing else "PENDING","entries":entries,"missing":missing,"note":"주소 형식/HTTP200만으로 로그인 없는 실제 열람을 확정하지 않음. 게시·폼 접수는 실행하지 않음."}
    except Exception as e:return {"status":"FAIL","entries":{},"errors":[str(e)]}

def test_checks(auto_root,project_root,skip_browser=False):
    print("검증 도구의 오류·오염 방지 검사를 실행합니다.",flush=True)
    unit=child([sys.executable,"-m","unittest","discover","-s","tests","-p","test_*.py","-v"],auto_root)
    match=re.search(r"Ran (\d+) tests?",unit["stderr"]+unit["stdout"])
    unit["tests_run"]=int(match[1]) if match else 0
    unit["status"]="PASS" if unit["returncode"]==0 and unit["tests_run"]>0 else "FAIL"
    asset=child(["node",str(auto_root/"tests/test_assets.cjs")],auto_root)
    try:
        asset_result=json.loads(asset["stdout"])
        asset["tests_run"]=asset_result.get("tests_run",asset_result.get("passed",0))
    except (ValueError,AttributeError):asset["tests_run"]=0
    asset["status"]="PASS" if asset["returncode"]==0 and asset["tests_run"]>0 else "FAIL"
    if skip_browser:browser={"status":"NOT_RUN","reason":"명시적으로 브라우저 검사 생략. 전체 내부 검수 완료 판정 금지."}
    else:
        browser=child_json(["node",str(project_root/"audit_2026-11-03/관객검증/동작검사.cjs"),"--final-only"],auto_root)
        valid=browser.get("status")=="PASS" and browser.get("execution",{}).get("returncode")==0 and browser.get("real_participants_added")==0 and not browser.get("errors") and not browser.get("external_requests")
        policy=read_json(auto_root/"policy.json")
        valid=valid and all(browser.get("image_sources",{}).get(a,{}).get("image_sha256")==policy["assets"][a]["sha256"] for a in ("A","B"))
        browser["status"]="PASS" if valid else "FAIL"
    return {"status":"PASS" if all(r["status"]=="PASS" for r in [unit,asset,browser]) else ("PENDING" if skip_browser and unit["status"]==asset["status"]=="PASS" else "FAIL"),"python":unit,"asset_mutations":asset,"observer_browser":browser}

def evaluate_verdict(stages,evidence,submission):
    statuses={k:v.get("status","FAIL") for k,v in stages.items()}
    internal_keys=("baseline","brand_cache","assets","copy","tests")
    internal=all(statuses.get(k)=="PASS" for k in internal_keys)
    failures=[k for k,v in statuses.items() if v=="FAIL"]
    if evidence.get("status") not in {"PASS","PENDING"} or evidence.get("errors"):failures.append("evidence")
    if submission.get("status")=="FAIL":failures.append("submission")
    pending={a:[r for r in EXTERNAL if evidence.get("rule_states",{}).get(a,{}).get(r,{}).get("state")!="VERIFIED"] for a in ("A","B")}
    source_ok=statuses.get("official")=="PASS"
    submission_ready=internal and source_ok and evidence.get("status")!="FAIL" and submission.get("status")=="PASS"
    verdict="FAIL" if failures else ("SUBMISSION_READY" if submission_ready else "EVIDENCE_PENDING")
    return {"verdict":verdict,"internal_validation_complete":internal,"submission_ready":submission_ready,"research_observation_complete":all(not pending[a] for a in ("A","B")),"pending_rules":pending,"pending_counts":{a:len(v) for a,v in pending.items()},"failed_stages":failures,"contest_result":"NOT_OBSERVED","claim_scope":"출품 준비·관측 완료·목표 반응·수상 결과는 별도 판정. 운명·우승 확정 수치 없음."}


def human_counts(counts):
    out=["|자료|A|B|","|---|---:|---:|"]
    labels={"valid_first_by_arm":"노출 기록 유효","verified_human_first_by_arm":"실제 사람 출처 확인","coded_understanding_by_arm":"첫인상 원답 검토","coded_share_intent_by_arm":"공유 의향 원답 검토","coded_recall_by_arm":"지연 회상 검토"}
    for key,label in labels.items():
        values=counts.get(key,{})
        out.append("|"+label+"|"+str(values.get("A","미확인"))+"|"+str(values.get("B","미확인"))+"|")
    out.append("받은 응답 파일: "+str(counts.get("received_response_files","미확인"))+" / QA 제외: "+str(counts.get("qa_excluded","미확인")))
    return "\n".join(out)
def public_evidence(evidence):
    result=copy.deepcopy(evidence)
    result.pop("response_records",None);result.pop("exclusions",None)
    result["errors"]=[{"code":e.get("code","INVALID_EVIDENCE")} if isinstance(e,dict) else {"code":"INVALID_EVIDENCE"} for e in evidence.get("errors",[])]
    result["review_requests"]=[{k:v for k,v in r.items() if k in {"review_kind","entry","rule","target_sha256","artifact_sha256","required_findings","required_fields"}} for r in evidence.get("review_requests",[]) if isinstance(r,dict)]
    for key in ("metrics","history"):
        if key in result.get("outcomes",{}):
            rows=result["outcomes"][key];safe={}
            for arm,items in rows.items():
                safe[arm]=[{k:v for k,v in item.items() if k in {"sha256","entry","artifact_sha256","platform_url","source_url","period_start","period_end","observed_start","observed_end","measurements","unavailable_reasons"}} for item in items]
            result["outcomes"][key]=safe
    return result

def render_md(report):
    decision=report["decision"];label={"FAIL":"검사 실패 — 수정 필요","SUBMISSION_READY":"제출 자료 검사 통과","EVIDENCE_PENDING":"내부 검사 결과와 증거 대기를 확인하세요"}[decision["verdict"]]
    out=["# 햇반 작품 자동 검증 결과","",label,"",f"실행 시각: {report['generated_at_kst']}","",
      "|영역|상태|","|---|---|"]
    names={"intake":"새 증거 자동 등록","baseline":"기준·120규칙·검토 대상","official":"공식 요강 재확인","brand_cache":"공식 로고 원본","assets":"실제 이미지·로고 픽셀·대비","copy":"설명·필수 태그·가상 고지","tests":"오류 주입·관객 도구 동작"}
    for k,v in report["stages"].items():out.append("|"+names.get(k,k)+"|"+str(v.get("status","FAIL"))+"|")
    out+=["",f"내부 검수 완료: {decision['internal_validation_complete']}",f"공식 제출 준비: {decision['submission_ready']}",f"외부 연구 관측 완료: {decision['research_observation_complete']}","",
     "‘관측 완료’는 실제 반응이 긍정적이라는 뜻이 아닙니다. 목표 반응은 outcomes에서 따로 확인합니다. 수상 결과와 역사성을 자동 확정하지 않습니다.","",
     "|작품|남은 항목 수|항목|","|---|---:|---|"]
    for a in ("A","B"):out.append("|"+a+"|"+str(decision["pending_counts"][a])+"|"+", ".join(decision["pending_rules"][a])+"|")
    out+=["","## 남은 증거",""]
    for a,states in report["evidence"].get("rule_states",{}).items():
        for rid,st in states.items():
            if st.get("state")!="VERIFIED":out.append("- "+a+" "+rid+": "+str(st.get("reason",st.get("state","PENDING"))))
    for item in report["submission"].get("missing",[]):out.append("- 제출 준비: "+item)
    for req in report["evidence"].get("review_requests",[]):out.append("- 추가 검토: "+json.dumps(req,ensure_ascii=False))
    out+=["","## 실제 자료 집계","",human_counts(report["evidence"].get("counts",{})),"",
     "자료가 없다는 사실을 효과가 없다는 결과로 해석하지 않습니다. QA 응답·AI 추정은 실제 사람 응답에 합산하지 않습니다.","",
     "## 자동화 범위","",
     "새 파일·실제 원답·검토 기록을 입력함에서 읽어 다시 계산합니다. 문서에 적어 둔 0명·7개를 그대로 출력하지 않습니다. 공식 필수 제출과 장기 효과 연구를 별도로 판단합니다. 새 자료가 없으면 대기 상태를 유지합니다.","",
     "자동 판독이 담당하지 않는 실제 사람의 출처·자유답 의미·제작 화면 진위는 해시가 연결된 검토 기록으로만 반영합니다. 기록이 없으면 검토 요청을 생성하고 통과를 막습니다.",""]
    return "\n".join(out).rstrip()+"\n"
def render_html(report,md,project=None,policy=None):
    decision=report["decision"]
    esc=html.escape
    cards="".join("<div class='card'><b>"+esc(k)+"</b><p>"+esc(str(v))+"</p></div>" for k,v in [
      ("내부 검수","통과" if decision["internal_validation_complete"] else "미완료"),("제출 준비","준비됨" if decision["submission_ready"] else "증거 대기"),("수상 결과","관측되지 않음")])
    gallery=""
    if project is not None and policy and report["stages"].get("baseline",{}).get("status")=="PASS" and report["stages"].get("assets",{}).get("status")=="PASS":
        for arm,asset in policy["assets"].items():
            try:
                image=within(project,asset["path"]);body=image.read_bytes()
                if hashlib.sha256(body).hexdigest()!=asset["sha256"]:raise InvalidEvidence("revision mismatch")
                gallery+="<img alt='"+arm+" 이번 검사 이미지' src='data:image/png;base64,"+base64.b64encode(body).decode()+"'>"
            except Exception:gallery+="<p>"+arm+" 파일 버전이 달라 미리보기를 표시하지 않습니다.</p>"
    stages="".join("<tr><td>"+esc(k)+"</td><td>"+esc(str(v.get("status")))+"</td></tr>" for k,v in report["stages"].items())
    return "<!doctype html><html lang='ko'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>햇반 검증 결과</title><style>body{font:16px/1.65 system-ui,sans-serif;background:#f5f2eb;color:#25221f;margin:0}main{max-width:1000px;margin:auto;padding:32px 20px}h1{font-size:28px}.cards{display:flex;gap:14px;flex-wrap:wrap}.card{background:white;padding:15px 20px;border-radius:12px;min-width:200px}.gallery{display:flex;gap:20px;flex-wrap:wrap;margin:24px 0}.gallery img{width:300px;max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;border-radius:12px}td,th{padding:8px 16px;text-align:left;border-bottom:1px solid #ddd}a{color:#8c2025}strong{color:#922}</style><main><h1>햇반 작품 자동 검증</h1><p>"+esc(report["generated_at_kst"])+"</p><div class='cards'>"+cards+"</div><p><strong>"+esc({"FAIL":"검사 실패","SUBMISSION_READY":"제출 자료 검사 통과","EVIDENCE_PENDING":"필수 증거 대기"}[decision["verdict"]])+"</strong> — 파일·증거 기준의 현재 판정입니다.</p><div class='gallery'>"+gallery+"</div><table><tr><th>검사</th><th>결과</th></tr>"+stages+"</table><pre>"+esc(md)+"</pre><p><a href='latest.json'>전체 검사 기록</a> · <a href='package_check.json'>묶음 검사 결과</a></p></main></html>\n"

def build_package(path,files,report_md,expected_hashes=None):
    names=set();manifest={}
    with ZipFile(path,"w",ZIP_DEFLATED,compresslevel=6) as archive:
        for name,source in sorted(files.items()):
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name or name in names:raise InvalidEvidence("unsafe archive name")
            names.add(name);body=Path(source).read_bytes()
            if expected_hashes and name in expected_hashes and hashlib.sha256(body).hexdigest()!=expected_hashes[name]:raise InvalidEvidence("검사 중 파일 변경: "+name)
            archive.writestr(name,body);manifest[name]=hashlib.sha256(body).hexdigest()
        body=report_md.encode();archive.writestr("현재상태.md",body);manifest["현재상태.md"]=hashlib.sha256(body).hexdigest()
        archive.writestr("파일해시.json",json.dumps(manifest,ensure_ascii=False,indent=2).encode())
    with ZipFile(path) as archive:
        if archive.testzip() is not None:raise InvalidEvidence("archive CRC mismatch")
        if len(archive.namelist())!=len(set(archive.namelist())):raise InvalidEvidence("duplicate archive member")
        for name,digest in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:raise InvalidEvidence("archive file mismatch")
    return {"status":"PASS","files":len(manifest)+1,"bytes":path.stat().st_size,"sha256":sha(path),"crc":"PASS","participant_raw_answers_included":False,"standalone_logo_or_font_included":False}



def capture_members(report,policy,inputs_root):
    verified={a:report["evidence"].get("rule_states",{}).get(a,{}).get("J08",{}) for a in ("A","B")}
    if not any(v.get("state")=="VERIFIED" for v in verified.values()):return {}
    if inputs_root is None:raise InvalidEvidence("검증된 제작 화면의 입력 위치가 없음")
    root=Path(inputs_root).resolve();manifest=read_json(within(root,"evidence.json"))
    members={}
    for arm,state in verified.items():
        if state.get("state")!="VERIFIED":continue
        target=state.get("target_sha256")
        for name in manifest.get("screenshots",[]):
            desc=read_json(within(root,name))
            if desc.get("entry")!=arm or desc.get("artifact_sha256")!=policy["assets"][arm]["sha256"] or desc.get("source_sha256")!=policy["assets"][arm]["source_sha256"]:continue
            image=within(root,desc["capture_path"])
            if sha(image)==target:
                members[arm+"_AI제작화면"+image.suffix.lower()]=image;break
        else:raise InvalidEvidence(arm+" 검증된 실제 제작 캡처를 묶음에 연결할 수 없음")
    return members

def finalize(report,policy,project,run_dir,reports,inputs_root=None):
    reports=Path(reports);reports.mkdir(parents=True,exist_ok=True)
    run_dir=Path(run_dir);run_dir.mkdir(parents=True,exist_ok=True)
    write_json(run_dir/"evidence-private.json",report["evidence"])
    write_json(run_dir/"review_queue_private.json",report["evidence"].get("review_requests",[]))
    report["evidence"]=public_evidence(report["evidence"])
    md=render_md(report)
    write_json(run_dir/"result.json",report)
    (run_dir/"result.md").write_text(md,encoding="utf-8",newline="\n")
    package={"status":"SKIPPED","reason":"내부 검사 미완료: 제출 묶음을 발행하지 않음."}
    if report["decision"]["internal_validation_complete"] and report["decision"]["verdict"]!="FAIL":
        try:
            files={"검증결과.json":run_dir/"result.json"}
            files.update(capture_members(report,policy,inputs_root))
            for a,asset in policy["assets"].items():
                files[Path(asset["path"]).name]=within(project,asset["path"])
                files[a+"_제출문구.md"]=within(project,policy["copy_paths"][a])
                files["생성원본/"+a+".png"]=within(project,asset["source_path"])
            expected={}
            for arm,asset in policy["assets"].items():
                expected[Path(asset["path"]).name]=asset["sha256"]
                expected["생성원본/"+arm+".png"]=asset["source_sha256"]
            for row in report["stages"].get("copy",{}).get("checks",[]):
                if row.get("copy_sha256"):expected[row["entry"]+"_제출문구.md"]=row["copy_sha256"]
            for name in files:
                if "_AI제작화면" in name:
                    expected[name]=report["evidence"]["rule_states"][name[0]]["J08"]["target_sha256"]
            package=build_package(run_dir/"bundle.zip",files,md,expected)
        except Exception as e:
            package={"status":"FAIL","reason":str(e)}
            report["stages"]["package"]={"status":"FAIL","reason":str(e)}
            report["decision"].update(verdict="FAIL",submission_ready=False)
            report["decision"]["failed_stages"].append("package")
            md=render_md(report)
            write_json(run_dir/"result.json",report)
            (run_dir/"result.md").write_text(md,encoding="utf-8",newline="\n")
    package.update(run_id=report["run_id"],report_sha256=sha(run_dir/"result.json"))
    write_json(run_dir/"package_check.json",package)
    for name,body in [("latest.json",(run_dir/"result.json").read_bytes()),("latest.md",md.encode()),("latest.html",render_html(report,md,project,policy).encode()),("package_check.json",(run_dir/"package_check.json").read_bytes())]:
        part=reports/(name+".new");part.write_bytes(body);part.replace(reports/name)
    zip_path=reports/"현재작품_검증자료.zip"
    if package["status"]=="PASS":
        part=reports/"bundle.new";part.write_bytes((run_dir/"bundle.zip").read_bytes());part.replace(zip_path)
    elif zip_path.exists():
        if not zip_path.resolve().is_relative_to(reports.resolve()):raise InvalidEvidence("unsafe generated package path")
        zip_path.unlink()
    return package


def terminal_summary(report,package,auto_root):
    return {"verdict":report["decision"]["verdict"],
      "internal_validation_complete":report["decision"]["internal_validation_complete"],
      "submission_ready":report["decision"]["submission_ready"],
      "pending_counts":report["decision"]["pending_counts"],
      "report":str(Path(auto_root)/"reports/latest.html"),"package":package["status"]}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root",type=Path,default=HERE.parent)
    parser.add_argument("--inputs",type=Path,default=HERE/"inputs")
    parser.add_argument("--offline",action="store_true")
    parser.add_argument("--skip-browser",action="store_true")
    args=parser.parse_args(argv)
    auto=HERE;project=args.project_root.resolve();inputs=args.inputs.resolve()
    now=datetime.now(timezone.utc)
    run_id=now.strftime("run-%Y%m%dT%H%M%SZ-")+uuid.uuid4().hex[:8]
    run_dir=auto/"runs"/run_id;run_dir.mkdir(parents=True,exist_ok=False)
    report={"schema_version":1,"run_id":run_id,"generated_at":now.isoformat(),"generated_at_kst":now.astimezone(KST).isoformat(),"stages":{}}
    evidence={"status":"PENDING","rule_states":{a:{r:{"state":"PENDING","reason":"증거 검사 미완료"} for r in EXTERNAL} for a in ("A","B")},"counts":{},"errors":[]}
    submission={"status":"PENDING","missing":["제출 자료 검사 미완료"]}
    try:
        policy=read_json(auto/"policy.json")
        report["policy_sha256"]=sha(auto/"policy.json")
        print("고정 기준과 실제 작품을 검사합니다.",flush=True)
        report["stages"]["baseline"]=baseline_checks(policy,auto,project)
        if report["stages"]["baseline"]["status"]!="PASS":raise InvalidEvidence("고정 기준 변경 또는 이전 검토 연결 오류. 이후 검사를 자동 승인하지 않음.")
        report["stages"]["official"]=check_official(policy,args.offline,auto/".private")
        report["stages"]["brand_cache"]=ensure_brand_cache(policy,auto/".private",args.offline)
        report["stages"]["assets"]=child_json(["node",str(auto/"asset_checks.cjs"),"--policy",str(auto/"policy.json"),"--project-root",str(project),"--cache",str(auto/".private")],auto)
        report["stages"]["copy"]=copy_checks(policy,project)
        print("새 증거·관객 원답과 기존 검토의 연결을 검사합니다.",flush=True)
        intake_spec=importlib.util.spec_from_file_location("hetbahn_intake",auto/"intake.py")
        intake_module=importlib.util.module_from_spec(intake_spec);intake_spec.loader.exec_module(intake_module)
        report["stages"]["intake"]=intake_module.discover(policy,inputs)
        spec=importlib.util.spec_from_file_location("hetbahn_evidence",auto/"evidence.py");module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        evidence=module.evaluate(policy,project,inputs,now)
        if set(evidence.get("rule_states",{}))!={"A","B"} or any(set(evidence["rule_states"][a])!=set(EXTERNAL) for a in ("A","B")):raise InvalidEvidence("external rule coverage missing")
        submission=submission_checks(policy,inputs,evidence,now)
        report["stages"]["tests"]=test_checks(auto,project,args.skip_browser)
    except Exception as e:
        report["stages"]["pipeline"]={"status":"FAIL","reason":type(e).__name__+": "+str(e)}
    report.update(evidence=evidence,submission=submission)
    report["decision"]=evaluate_verdict(report["stages"],evidence,submission)
    report["code_sha256"]={p.name:sha(p) for p in sorted(auto.glob("*.py"))}
    report["code_sha256"].update({p.name:sha(p) for p in sorted(auto.glob("*.cjs"))})
    package=finalize(report,policy if "policy" in locals() else {},project,run_dir,auto/"reports",inputs)
    ui=child_json(["node",str(auto/"report_ui.cjs")],auto)
    if ui.get("status")!="PASS":
        report["stages"]["report_ui"]={"status":"FAIL","errors":ui.get("errors",[ui.get("error","UI check failed")])}
        report["decision"].update(verdict="FAIL",submission_ready=False,internal_validation_complete=False)
        report["decision"]["failed_stages"].append("report_ui")
        package=finalize(report,policy if "policy" in locals() else {},project,run_dir,auto/"reports",inputs)
    print(json.dumps(terminal_summary(report,package,auto),ensure_ascii=False),flush=True)
    return 1 if report["decision"]["verdict"]=="FAIL" else (0 if report["decision"]["submission_ready"] else 2)
if __name__=="__main__":raise SystemExit(main())
