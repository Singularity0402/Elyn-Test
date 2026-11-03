import importlib.util, json, shutil, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pipeline_under_test',ROOT/'run_checks.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def stages():
    return {k:{'status':'PASS'} for k in ('baseline','official','brand_cache','assets','copy','tests')}
def pending_evidence():
    return {'status':'PENDING','errors':[],'rule_states':{a:{r:{'state':'PENDING','reason':'synthetic test, not collected'} for r in m.EXTERNAL} for a in ('A','B')},'counts':{'actual_records':0}}
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.parent=(ROOT/'.test-runs').resolve();self.parent.mkdir(exist_ok=True)
        self.tmp=Path(tempfile.mkdtemp(prefix='pipeline-',dir=self.parent)).resolve()
        self.assertEqual(self.tmp.parent,self.parent)
    def tearDown(self):
        target=self.tmp.resolve()
        if target.parent!=self.parent or not target.name.startswith('pipeline-'):raise RuntimeError('unsafe test cleanup')
        shutil.rmtree(target)
    def test_no_evidence_is_pending_not_complete(self):
        got=m.evaluate_verdict(stages(),pending_evidence(),{'status':'PENDING'})
        self.assertTrue(got['internal_validation_complete'])
        self.assertFalse(got['submission_ready']);self.assertFalse(got['research_observation_complete'])
        self.assertEqual(got['pending_counts'],{'A':7,'B':7})
        self.assertEqual(got['verdict'],'EVIDENCE_PENDING')
    def test_evidence_count_recomputed_when_one_item_changes(self):
        ev=pending_evidence();ev['rule_states']['A']['J08']={'state':'VERIFIED','reason':'synthetic receipt'}
        got=m.evaluate_verdict(stages(),ev,{'status':'PENDING'})
        self.assertEqual(got['pending_counts'],{'A':6,'B':7})
    def test_formal_readiness_does_not_wait_for_history(self):
        ev=pending_evidence()
        for a in ('A','B'):ev['rule_states'][a]['J08']={'state':'VERIFIED'}
        got=m.evaluate_verdict(stages(),ev,{'status':'PASS'})
        self.assertTrue(got['submission_ready']);self.assertFalse(got['research_observation_complete'])
        self.assertEqual(got['contest_result'],'NOT_OBSERVED')
    def test_observation_completion_never_declares_award(self):
        ev=pending_evidence();ev['status']='PASS'
        for a in ('A','B'):
            for r in m.EXTERNAL:ev['rule_states'][a][r]={'state':'VERIFIED'}
        got=m.evaluate_verdict(stages(),ev,{'status':'PASS'})
        self.assertTrue(got['research_observation_complete'])
        self.assertNotIn('probability',got);self.assertEqual(got['contest_result'],'NOT_OBSERVED')
    def test_failed_assets_override_positive_receipts(self):
        s=stages();s['assets']['status']='FAIL'
        got=m.evaluate_verdict(s,pending_evidence(),{'status':'PASS'})
        self.assertEqual(got['verdict'],'FAIL');self.assertFalse(got['submission_ready'])
    def test_evidence_error_cannot_be_hidden_by_pass_label(self):
        ev=pending_evidence();ev.update(status='PASS',errors=['tampered'])
        self.assertEqual(m.evaluate_verdict(stages(),ev,{'status':'PASS'})['verdict'],'FAIL')
    def test_duplicate_json_keys_rejected(self):
        p=self.tmp/'bad.json';p.write_text('{"state":"PASS","state":"FAIL"}')
        with self.assertRaises(ValueError):m.read_json(p)
    def test_nonfinite_json_rejected(self):
        p=self.tmp/'bad.json';p.write_text('{"score":NaN}')
        with self.assertRaises(ValueError):m.read_json(p)
    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):m.within(self.tmp,'../outside')
    def test_process_nonzero_cannot_report_pass(self):
        fake={'returncode':1,'stdout':'{"status":"PASS"}','stderr':'error','seconds':0}
        with patch.object(m,'child',return_value=fake):got=m.child_json([],self.tmp)
        self.assertEqual(got['status'],'FAIL')
    def test_official_markers_inside_script_are_not_trusted(self):
        fake='<script>갓 지은 AI디어 공모전 2026년10월26일11월13일(금)23:59 정방형(1:1) 세로형(4:5) 제작히스토리캡처본 AI서비스 실제출시된제품이나확정된기능 출품작품수에는제한이없으나 2026년11월27일 #햇반 #햇반AI공모전 #갓지은아이디어 @hetbahn.30years</script>'
        self.assertFalse(any(m.official_fingerprint(fake).values()))
    def report(self):
        ev=pending_evidence();decision=m.evaluate_verdict(stages(),ev,{'status':'PENDING','missing':['fixture']})
        return {'run_id':'qa-fixture','generated_at_kst':'2026-11-03T00:00:00+09:00','stages':stages(),'decision':decision,'evidence':ev,'submission':{'status':'PENDING','missing':['fixture']}}
    def test_package_failure_and_published_report_agree(self):
        r=self.report();run=self.tmp/'run';reports=self.tmp/'reports';reports.mkdir()
        old=reports/'현재작품_검증자료.zip';old.write_bytes(b'previous generated fixture')
        pol={'assets':{'A':{'path':'missing.png','source_path':'missing-original.png'}},'copy_paths':{'A':'missing.md'}}
        result=m.finalize(r,pol,self.tmp,run,reports)
        self.assertEqual(result['status'],'FAIL')
        published=m.read_json(reports/'latest.json')
        self.assertEqual(published['decision']['verdict'],'FAIL')
        self.assertIn('FAIL',(reports/'latest.md').read_text(encoding='utf-8'))
        self.assertFalse(old.exists())
        self.assertEqual(result['report_sha256'],m.sha(reports/'latest.json'))
    def test_archive_manifest_has_no_self_hash_or_duplicate(self):
        from zipfile import ZipFile
        p=self.tmp/'a.png';p.write_bytes(b'qa-only bytes')
        zp=self.tmp/'out.zip'
        result=m.build_package(zp,{'A.png':p},'QA only, not production')
        self.assertEqual(result['status'],'PASS')
        with ZipFile(zp) as z:
            manifest=json.loads(z.read('파일해시.json'))
            self.assertNotIn('파일해시.json',manifest)
            self.assertEqual(len(z.namelist()),len(set(z.namelist())))
            self.assertEqual(z.read('A.png'),p.read_bytes())
    def test_terminal_summary_has_explicit_output_root(self):
        report=self.report()
        result=m.terminal_summary(report,{"status":"PASS"},self.tmp)
        self.assertEqual(result["report"],str(self.tmp/"reports/latest.html"))
        self.assertEqual(result["verdict"],"EVIDENCE_PENDING")
    def test_official_tags_survive_markup_boundaries(self):
        body="#햇반 #햇반AI<span>공모전</span> #갓지은아이디어 @hetbahn.<b>30years</b>"
        self.assertTrue(m.official_fingerprint(body)["all_tags"])
    def test_changed_required_tag_is_detected(self):
        body="#햇반 #햇반AI공모전 #다른태그 @hetbahn.30years"
        self.assertFalse(m.official_fingerprint(body)["all_tags"])
    def test_public_report_omits_actual_raw_answers(self):
        ev=pending_evidence()
        ev["response_records"]=[{"raw_answers":{"product":"PRIVATE_RESPONSE_SENTINEL"}}]
        ev["review_requests"]=[{"entry":"A","rule":"L02","target_file":"PRIVATE_NAME_SENTINEL.json","target_sha256":"abc"}]
        safe=m.public_evidence(ev)
        text=json.dumps(safe)
        self.assertNotIn("PRIVATE_RESPONSE_SENTINEL",text)
        self.assertNotIn("PRIVATE_NAME_SENTINEL",text)
        self.assertIn("abc",text)
        self.assertIn("response_records",ev)

    def test_live_form_constraint_limit_and_definition_change(self):
        def doc(limit):
            nodes=[[457854809,"출품작 설명을 작성해 주세요.",f"설명은 {limit}자 이내",1,[[1,None,1,None,[[6,202,[str(limit)],f"최대 {limit}자"]]]]]]
            return "<script>FB_PUBLIC_LOAD_DATA_ = "+json.dumps([None,[None,nodes]],ensure_ascii=False)+";</script>"
        old=m.form_constraints(doc(500));new=m.form_constraints(doc(300))
        self.assertEqual(old["description_limit"],500)
        self.assertEqual(new["description_limit"],300)
        self.assertNotEqual(old["question_definitions_sha256"],new["question_definitions_sha256"])
    def test_form_limit_hint_validation_conflict_rejected(self):
        nodes=[[457854809,"출품작 설명","500자 이내",1,[[1,None,1,None,[[6,202,["300"],"최대 300자"]]]]]]
        raw="<script>FB_PUBLIC_LOAD_DATA_ = "+json.dumps([None,[None,nodes]])+";</script>"
        with self.assertRaises(ValueError):m.form_constraints(raw)
    def test_confirmed_constraint_conflict_is_fail_not_pending(self):
        policy={"official_source":{"url":"https://docs.google.com/forms/example"}}
        response=unittest.mock.MagicMock()
        response.__enter__.return_value.geturl.return_value=policy["official_source"]["url"]
        response.__enter__.return_value.read.return_value=b"fixture"
        with patch.object(m,"urlopen",return_value=response), patch.object(m,"form_constraints",side_effect=m.InvalidEvidence("conflicting500/300")):
            result=m.check_official(policy,False,self.tmp)
        self.assertEqual(result["status"],"FAIL")
    def test_verified_capture_is_actually_added_to_package_members(self):
        root=self.tmp/"inputs";root.mkdir()
        image=root/"real.png";image.write_bytes(b"QA fixture not a real screenshot")
        digest=m.sha(image)
        desc={"entry":"A","artifact_sha256":"artifact","source_sha256":"source","capture_path":"real.png"}
        m.write_json(root/"cap.json",desc);m.write_json(root/"evidence.json",{"screenshots":["cap.json"]})
        report=self.report();report["evidence"]["rule_states"]["A"]["J08"]={"state":"VERIFIED","target_sha256":digest}
        policy={"assets":{"A":{"sha256":"artifact","source_sha256":"source"}}}
        members=m.capture_members(report,policy,root)
        self.assertEqual(members["A_AI제작화면.png"],image)
        image.write_bytes(b"tampered")
        with self.assertRaises(ValueError):m.capture_members(report,policy,root)
    def test_package_rechecks_bytes_after_prior_validation(self):
        path=self.tmp/"image.png";path.write_bytes(b"original QA")
        approved=m.sha(path);path.write_bytes(b"changed after validation")
        with self.assertRaises(ValueError):m.build_package(self.tmp/"bad.zip",{"A.png":path},"qa",{"A.png":approved})
    def test_html_never_displays_changed_file_as_approved_snapshot(self):
        path=self.tmp/"image.png";path.write_bytes(b"original QA")
        policy={"assets":{"A":{"path":"image.png","sha256":m.sha(path)}}}
        report=self.report()
        page=m.render_html(report,"qa",self.tmp,policy)
        self.assertIn("data:image/png;base64,",page)
        path.write_bytes(b"changed")
        page=m.render_html(report,"qa",self.tmp,policy)
        self.assertNotIn("data:image/png;base64,",page)
        self.assertIn("버전이 달라",page)
    def test_git_line_endings_do_not_invalidate_semantic_review(self):
        policy=m.read_json(ROOT/"policy.json")
        auto=self.tmp/"auto";project=self.tmp/"project";auto.mkdir();project.mkdir()
        for name in ("policy.json","baseline.lock.json"):
            (auto/name).write_bytes((ROOT/name).read_bytes())
        names=[policy["manual_path"],policy["audit_path"]]+[x["path"] for x in policy["review_bindings"]]
        for name in names:
            dest=project/name;dest.parent.mkdir(parents=True,exist_ok=True)
            source=(ROOT.parent/name).read_text(encoding="utf-8-sig")
            dest.write_text(source,encoding="utf-8",newline="\r\n")
        result=m.baseline_checks(policy,auto,project)
        self.assertEqual(result["status"],"PASS")
        audit=m.read_json(project/policy["audit_path"]);audit["rows"][0]["rule"]+=" changed"
        m.write_json(project/policy["audit_path"],audit)
        self.assertEqual(m.baseline_checks(policy,auto,project)["status"],"FAIL")
    def test_archive_path_escape_rejected(self):
        p=self.tmp/'x';p.write_bytes(b'qa')
        with self.assertRaises(ValueError):m.build_package(self.tmp/'bad.zip',{'../escape':p},'qa')
if __name__=='__main__':unittest.main()
