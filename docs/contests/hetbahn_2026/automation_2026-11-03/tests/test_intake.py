import importlib.util,json,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('intake_under_test',ROOT/'intake.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.parent=(ROOT/'.test-runs').resolve();self.parent.mkdir(exist_ok=True)
        self.tmp=Path(tempfile.mkdtemp(prefix='intake-',dir=self.parent)).resolve()
        self.assertEqual(self.tmp.parent,self.parent)
        self.policy={'assets':{a:{'sha256':'a'*64,'source_sha256':'b'*64} for a in ('A','B')}}
    def tearDown(self):
        path=self.tmp.resolve()
        if path.parent!=self.parent or not path.name.startswith('intake-'):raise RuntimeError('unsafe cleanup')
        shutil.rmtree(path)
    def test_empty_bootstrap_creates_no_proof(self):
        result=m.discover(self.policy,self.tmp)
        self.assertTrue(all(n==0 for n in result['registered_totals'].values()))
    def test_response_registration_is_idempotent_not_human_approval(self):
        folder=self.tmp/'inbox/responses';folder.mkdir(parents=True)
        (folder/'qa.json').write_text('{"record_kind":"qa"}')
        first=m.discover(self.policy,self.tmp);second=m.discover(self.policy,self.tmp)
        self.assertEqual(first['registered_new']['responses'],1)
        self.assertEqual(second['registered_new']['responses'],0)
        self.assertNotIn('verified',first)
        data=json.loads((self.tmp/'evidence.json').read_text())
        self.assertEqual(data['responses'],['inbox/responses/qa.json'])
    def test_capture_is_copied_and_queued_not_verified(self):
        folder=self.tmp/'inbox/captures/A';folder.mkdir(parents=True)
        pic=folder/'fixture.png';pic.write_bytes(b'QA ONLY, not a screenshot')
        result=m.discover(self.policy,self.tmp)
        self.assertEqual(result['registered_new']['screenshots'],1)
        data=json.loads((self.tmp/'evidence.json').read_text())
        record=json.loads((self.tmp/data['screenshots'][0]).read_text())
        self.assertEqual(record['binding_status'],'proposed_only_requires_actual_content_review')
        self.assertEqual((self.tmp/record['capture_path']).read_bytes(),pic.read_bytes())
    def test_replaced_inbox_media_preserves_earlier_bytes(self):
        folder=self.tmp/'inbox/captures/A';folder.mkdir(parents=True)
        pic=folder/'fixture.png';pic.write_bytes(b'first QA')
        m.discover(self.policy,self.tmp)
        pic.write_bytes(b'second QA');m.discover(self.policy,self.tmp)
        data=json.loads((self.tmp/'evidence.json').read_text())
        self.assertEqual(len(data['screenshots']),2)
        contents={(self.tmp/json.loads((self.tmp/p).read_text())['capture_path']).read_bytes() for p in data['screenshots']}
        self.assertEqual(contents,{b'first QA',b'second QA'})
    def test_revision_change_does_not_rebind_old_capture(self):
        folder=self.tmp/'inbox/captures/A';folder.mkdir(parents=True)
        (folder/'fixture.png').write_bytes(b'QA')
        m.discover(self.policy,self.tmp);self.policy['assets']['A']['sha256']='c'*64
        with self.assertRaises(ValueError):m.discover(self.policy,self.tmp)
    def test_manifest_duplicates_rejected(self):
        (self.tmp/'evidence.json').write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):m.discover(self.policy,self.tmp)
    def test_resolved_capture_file_escape_is_blocked_before_write(self):
        from unittest.mock import patch
        root=self.tmp/"inputs";folder=root/"inbox/captures/A";folder.mkdir(parents=True)
        (folder/"fixture.png").write_bytes(b"QA")
        outside=self.tmp/"outside.bin";original=Path.resolve
        def redirected(path,*args,**kwargs):
            if path.parent.name=="media" and path.suffix==".png":return outside
            return original(path,*args,**kwargs)
        with patch.object(Path,"resolve",redirected):
            with self.assertRaises(ValueError):m.discover(self.policy,root)
        self.assertFalse(outside.exists())
    def test_resolved_capture_descriptor_escape_is_blocked_before_write(self):
        from unittest.mock import patch
        root=self.tmp/"inputs";folder=root/"inbox/captures/A";folder.mkdir(parents=True)
        (folder/"fixture.png").write_bytes(b"QA")
        outside=self.tmp/"outside.json";original=Path.resolve
        def redirected(path,*args,**kwargs):
            if path.parent.name==".generated" and path.name.startswith("capture-A-"):return outside
            return original(path,*args,**kwargs)
        with patch.object(Path,"resolve",redirected):
            with self.assertRaises(ValueError):m.discover(self.policy,root)
        self.assertFalse(outside.exists())
if __name__=='__main__':unittest.main()
