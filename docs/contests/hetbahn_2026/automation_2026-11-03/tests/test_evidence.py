"""SYNTHETIC / QA ONLY: all positive people/reviews below are simulated test data.

Fixtures exist only beneath a guarded system-temp test root. They are never
written to production inputs and do not prove any real person or outcome.
Run: python -m unittest discover -s tests -p test_*.py
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

AUTOMATION = Path(__file__).resolve().parents[1]
MODULE_PATH = AUTOMATION / 'evidence.py'
# Avoid creating __pycache__ in the shared repository.
evidence_namespace = {'__name__': 'evidence_under_test', '__file__': str(MODULE_PATH)}
exec(compile(MODULE_PATH.read_text(encoding='utf-8-sig'), str(MODULE_PATH), 'exec'), evidence_namespace)
evaluate = evidence_namespace['evaluate']
strict_json = evidence_namespace['strict_json']
TEST_ROOT = (Path(tempfile.gettempdir()) / 'hetbahn-evidence-unittest-synthetic-qa').resolve()
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='synthetic-qa-', dir=TEST_ROOT)).resolve()
        self.project = self.root / 'project'
        self.inputs = self.root / 'inputs'
        self.project.mkdir()
        self.inputs.mkdir()
        self.observer = self.project / 'observer'
        self.observer.mkdir()
        source = AUTOMATION.parent / 'audit_2026-11-03' / '관객검증' / '응답_집계.py'
        shutil.copyfile(source, self.observer / '응답_집계.py')
        self.assets = {}
        for arm, color in (('A', 'red'), ('B', 'blue')):
            Image.new('RGB', (12, 12), color).save(self.project / (arm + '.png'))
            (self.project / (arm + '-source.bin')).write_bytes(('SYNTHETIC QA original ' + arm).encode())
            self.assets[arm] = {'path': arm + '.png', 'sha256': self.digest(self.project / (arm + '.png')),
                                'source_path': arm + '-source.bin', 'source_sha256': self.digest(self.project / (arm + '-source.bin'))}
        self.assignments = {f'P{i:02}': ('A' if i <= 6 else 'B') for i in range(1, 13)}
        self.protocol = self.observer / 'protocol.js'
        self.protocol.write_text("protocol_id: 'synthetic-qa-only-v1',\n" +
            '\n'.join(f"{a}: Object.freeze({{path: '../{a}.png', sha256: '{self.assets[a]['sha256']}'}})," for a in ('A', 'B')) +
            '\nassignment: Object.freeze({' + ', '.join(f"{pid}:'{a}'" for pid, a in self.assignments.items()) + '}),\n' +
            'valid_exposure_ms: Object.freeze([2800, 3800]),\n', encoding='utf-8')
        self.policy = {'schema_version': 1, 'protocol_path': 'observer/protocol.js', 'assets': self.assets,
                       'sample_plan': {'participants': 12, 'per_arm': 6, 'target_ms': 3000,
                                       'valid_ms': [2800, 3800], 'recall_hours': 24, 'internal_target_per_arm': 5}}
        self.manifest = {'schema_version': 1, **{k: [] for k in ('responses', 'reviews', 'screenshots', 'metrics', 'history')}}
        self.serial = 0

    def tearDown(self):
        # Mandatory boundary validation immediately before recursive deletion.
        target = self.root.resolve()
        self.assertNotEqual(target, TEST_ROOT)
        self.assertTrue(target.is_relative_to(TEST_ROOT))
        self.assertTrue(target.name.startswith('synthetic-qa-'))
        shutil.rmtree(target)

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write(self, name, value):
        path = self.inputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        return name

    def add(self, kind, record, name=None):
        self.serial += 1
        name = name or f'{kind}/{self.serial}.json'
        self.write(name, record)
        self.manifest[kind].append(name)
        return name

    def run_evaluation(self):
        self.write('evidence.json', self.manifest)
        return evaluate(self.policy, self.project, self.inputs, NOW)

    def response(self, pid='P01', recall=False):
        arm = self.assignments[pid]
        record = {'schema_version': 1, 'record_kind': 'participant', 'protocol_id': 'synthetic-qa-only-v1',
            'participant_id': pid, 'arm': arm, 'image_sha256': self.assets[arm]['sha256'],
            'consent': {'agreed': True, 'adult': True, 'at': '2026-11-01T10:00:00Z'},
            'prior_exposure': False, 'interrupted': False,
            'screen': {'width': 1080, 'height': 1920, 'viewport_width': 1080, 'viewport_height': 1800, 'device_pixel_ratio': 1},
            'exposure_ms': 3000, 'created_at': '2026-11-01T09:59:59Z',
            'exposure_started_at': '2026-11-01T10:00:01Z', 'exposure_ended_at': '2026-11-01T10:00:04Z',
            'answers_submitted_at': '2026-11-01T10:01:00Z', 'updated_at': '2026-11-01T10:01:01Z',
            'stage': 'waiting', 'events': [{'type': 'exposure_start', 'at': '2026-11-01T10:00:01Z'},
                                            {'type': 'exposure_end', 'at': '2026-11-01T10:00:04Z'},
                                            {'type': 'answers_submitted', 'at': '2026-11-01T10:01:00Z'}],
            'raw_answers': {'product': '제품을 모르겠습니다', 'event': '행사를 모르겠습니다', 'scene': '김이 보입니다',
                            'share_recipient': '없음', 'share_sentence': '공유하지 않음', 'share_reason': '관심이 없습니다'},
            'recall_raw_answers': {}, 'recall_submitted_at': None}
        if recall:
            record.update(stage='complete', updated_at='2026-11-02T10:02:01Z',
                          recall_submitted_at='2026-11-02T10:02:00Z',
                          recall_raw_answers={'brand': '브랜드 기억 안남', 'scene': '관계 기억 안남'})
            record['events'].extend([{'type': 'recall_opened', 'at': '2026-11-02T10:01:00Z'},
                                     {'type': 'recall_submitted', 'at': '2026-11-02T10:02:00Z'}])
        return record

    def receipt(self, kind, target, arm='A', findings=None, reviewer='human', verdict='verified'):
        return {'review_kind': kind, 'entry': arm, 'artifact_sha256': self.assets[arm]['sha256'],
                'target_sha256': self.digest(self.inputs / target),
                'reviewer': {'id': 'simulated-reviewer-for-unit-test', 'kind': reviewer},
                'reviewed_at': '2026-11-03T10:00:00Z', 'verdict': verdict,
                'findings': findings or {}, 'source_note': '모집 기록과 익명 원답을 대조했다는 receipt 형식 예시'}

    def code(self, record, value=False):
        raw, recall = record['raw_answers'], record['recall_raw_answers']
        result = {'product_understood': value, 'event_understood': value, 'share_intent': value,
                  'quotes': {'product_understood': raw['product'], 'event_understood': raw['event'], 'share_intent': raw['share_reason']}}
        if recall:
            result.update(brand_recalled=value, relationship_recalled=value)
            result['quotes'].update(brand_recalled=recall['brand'], relationship_recalled=recall['scene'])
        return result

    def attested_response(self, pid='P01', recall=False, value=False):
        record = self.response(pid, recall)
        name = self.add('responses', record)
        self.add('reviews', self.receipt('source_attestation', name, record['arm']))
        self.add('reviews', self.receipt('semantic_coding', name, record['arm'], self.code(record, value), reviewer='AI'))
        return name

    def complete_external(self, arm):
        capture = self.inputs / (arm + '-capture.png')
        Image.new('RGB', (32, 24), 'green' if arm == 'A' else 'yellow').save(capture)
        self.add('screenshots', {'entry': arm, 'artifact_sha256': self.assets[arm]['sha256'],
            'source_sha256': self.assets[arm]['source_sha256'], 'capture_path': capture.name,
            'captured_at': '2026-11-01T10:00:00Z'})
        self.add('reviews', self.receipt('generation_capture', capture.name, arm,
            {k: True for k in ('service_visible', 'prompt_visible', 'result_visible', 'entry_matches')}))
        metrics = {'entry': arm, 'artifact_sha256': self.assets[arm]['sha256'],
                   'platform_url': 'https://example.org/post/' + arm, 'period_start': '2026-11-01T00:00:00Z',
                   'period_end': '2026-11-02T00:00:00Z',
                   'measurements': {'impressions': 25, 'reach': None, 'shares': 0, 'saves': None, 'reactions': 2},
                   'unavailable_reasons': {'reach': '플랫폼 미제공', 'saves': '비공개'}}
        name = self.add('metrics', metrics)
        self.add('reviews', self.receipt('social_metrics', name, arm))
        history = {'entry': arm, 'artifact_sha256': self.assets[arm]['sha256'],
                   'source_url': 'https://example.org/independent/' + arm,
                   'observed_start': '2026-01-01T00:00:00Z', 'observed_end': '2026-11-01T00:00:00Z',
                   'independence_note': '제3자 관측', 'long_term_basis': '독립 반복 관측의 장기성은 리뷰어가 판단'}
        name = self.add('history', history)
        self.add('reviews', self.receipt('longitudinal', name, arm,
            {k: True for k in ('independent', 'long_term', 'not_self_generated')}))

    def test_empty_input_seven_pending_each_arm(self):
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'PENDING')
        self.assertEqual(report['errors'], [])
        for arm in ('A', 'B'):
            self.assertEqual(len(report['rule_states'][arm]), 7)
            self.assertTrue(all(x['state'] == 'PENDING' for x in report['rule_states'][arm].values()))
            self.assertEqual(report['counts']['valid_first_by_arm'][arm], 0)
            self.assertIsNone(report['outcomes']['by_arm'][arm]['product_understood']['percent'])
        self.assertEqual(report['counts']['received_response_files'], 0)

    def test_qa_dom_and_synthetic_excluded(self):
        for marker in ({'record_kind': 'qa'}, {'source_kind': 'DOM'}, {'synthetic': True}, {'source_type': 'AI'}, {'provenance': {'kind': 'DOM'}}):
            record = self.response()
            record.update(marker)
            self.add('responses', record)
        report = self.run_evaluation()
        self.assertEqual(report['counts']['qa_excluded'], 5)
        self.assertEqual(sum(report['counts']['valid_first_by_arm'].values()), 0)

    def test_image_hash_changed_response_excluded_even_with_receipt(self):
        record = self.response()
        record['image_sha256'] = '0' * 64
        name = self.add('responses', record)
        self.add('reviews', self.receipt('source_attestation', name))
        report = self.run_evaluation()
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 0)
        self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)
        self.assertIn('image_sha256_mismatch', report['response_records'][0]['issues'])

    def test_first_and_recall_merge_preserves_all_file_hashes(self):
        first = self.add('responses', self.response())
        last = self.add('responses', self.response(recall=True))
        report = self.run_evaluation()
        self.assertEqual(report['counts']['received_response_files'], 2)
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 1)
        self.assertEqual(report['counts']['valid_recall_by_arm']['A'], 1)
        row = report['response_records'][0]
        self.assertEqual(row['selected_file'], last)
        self.assertEqual({x['sha256'] for x in row['versions']}, {self.digest(self.inputs / p) for p in (first, last)})

    def test_conflicting_duplicate_id_excludes_all_versions(self):
        self.add('responses', self.response())
        changed = self.response(recall=True)
        changed['raw_answers']['product'] = '수정된 최초 원답'
        self.add('responses', changed)
        report = self.run_evaluation()
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 0)
        self.assertEqual(report['counts']['conflicting_participant_ids'], 1)
        self.assertEqual(report['counts']['excluded_response_files'], 2)

    def test_invalid_duplicate_does_not_leave_valid_copy_counted(self):
        self.add('responses', self.response())
        changed = self.response(recall=True)
        changed['updated_at'] = '2099-01-01T00:00:00Z'
        self.add('responses', changed)
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 0)

    def test_unreviewed_response_never_counts_as_verified_human(self):
        self.add('responses', self.response())
        report = self.run_evaluation()
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 1)
        self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)
        self.assertTrue(any(x['review_kind'] == 'source_attestation' for x in report['review_requests']))

    def test_receipt_cannot_override_prior_exposure_interruption_or_missing_answers(self):
        for patch in ({'prior_exposure': True}, {'interrupted': True}, {'raw_answers': {}}):
            with self.subTest(patch=patch):
                self.manifest['responses'].clear()
                self.manifest['reviews'].clear()
                record = self.response()
                record.update(patch)
                name = self.add('responses', record)
                self.add('reviews', self.receipt('source_attestation', name))
                report = self.run_evaluation()
                self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)
                self.assertEqual(report['counts']['valid_first_by_arm']['A'], 0)

    def test_ai_source_attestation_is_invalid(self):
        name = self.add('responses', self.response())
        self.add('reviews', self.receipt('source_attestation', name, reviewer='AI'))
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)

    def test_fake_auto_pass_receipt_does_not_verify(self):
        name = self.add('responses', self.response())
        receipt = self.receipt('source_attestation', name)
        receipt['verdict'] = 'PASS'
        self.add('reviews', receipt)
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)

    def test_auto_findings_are_explicitly_rejected(self):
        name = self.add('responses', self.response())
        self.add('reviews', self.receipt('source_attestation', name, findings={'auto_pass': True}))
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)

    def test_missing_file_path_escape_absolute_and_future_rejected(self):
        outside = self.root / 'outside.json'
        outside.write_text('{}', encoding='utf-8')
        for invalid in ('missing.json', '../outside.json', str(outside), 'C:\\outside.json'):
            with self.subTest(path=invalid):
                self.manifest['responses'] = [invalid]
                self.assertEqual(self.run_evaluation()['status'], 'FAIL')
        self.manifest['responses'] = []
        record = self.response()
        record['consent']['at'] = '2099-01-01T00:00:00Z'
        self.add('responses', record)
        self.assertEqual(self.run_evaluation()['status'], 'FAIL')

    def test_json_duplicate_keys_nan_overflow_bad_schema_and_broken_json(self):
        for text in ('{"schema_version":1,"schema_version":1}', '{"n":NaN}', '{"n":1e999}', '[]', '{', '{"schema_version":2}'):
            with self.subTest(text=text):
                self.manifest['responses'] = ['broken.json']
                (self.inputs / 'broken.json').write_text(text, encoding='utf-8')
                self.assertEqual(self.run_evaluation()['status'], 'FAIL')

    def test_review_missing_source_note_time_target_or_current_artifact_rejected(self):
        name = self.add('responses', self.response())
        for patch in ({'source_note': ''}, {'reviewed_at': None}, {'target_sha256': '0' * 64},
                      {'artifact_sha256': '0' * 64}, {'reviewed_at': '2099-01-01T00:00:00Z'},
                      {'reviewed_at': '2026-10-01T00:00:00Z'}):
            with self.subTest(patch=patch):
                self.manifest['reviews'] = []
                receipt = self.receipt('source_attestation', name)
                receipt.update(patch)
                self.add('reviews', receipt)
                report = self.run_evaluation()
                self.assertEqual(report['status'], 'FAIL')
                self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)

    def test_ungrounded_quote_not_accepted(self):
        name = self.add('responses', self.response())
        self.add('reviews', self.receipt('source_attestation', name))
        coding = self.code(self.response())
        coding['quotes']['product_understood'] = '원답에 존재하지 않는 문장'
        self.add('reviews', self.receipt('semantic_coding', name, findings=coding))
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts']['coded_understanding_by_arm']['A'], 0)
        self.assertEqual(report['counts']['coded_share_intent_by_arm']['A'], 1)

    def test_synthetic_positive_measurement_negative_effects_all_seven_verified(self):
        # This simulates the entire receipt workflow; it is NOT external evidence.
        for pid in self.assignments:
            self.attested_response(pid, recall=True, value=False)
        for arm in ('A', 'B'):
            self.complete_external(arm)
        report = self.run_evaluation()
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['status'], 'PASS')
        for arm in ('A', 'B'):
            self.assertTrue(all(s['state'] == 'VERIFIED' for s in report['rule_states'][arm].values()))
            self.assertEqual(report['counts']['verified_human_first_by_arm'][arm], 6)
            self.assertEqual(report['counts']['verified_human_recall_by_arm'][arm], 6)
            outcome = report['outcomes']['by_arm'][arm]
            self.assertEqual(outcome['understanding_joint']['percent'], 0)
            self.assertFalse(outcome['understanding_joint']['target_met'])
            self.assertEqual(outcome['share_intent']['positive'], 0)
            self.assertIsNone(outcome['actual_sharing_from_intent'])
            self.assertIsNone(report['outcomes']['metrics'][arm][0]['measurements']['reach'])
        self.assertTrue(report['outcomes']['comparison']['comparable'])

    def test_positive_five_of_six_target_and_partial_cohort_not_complete(self):
        for pid in self.assignments:
            self.attested_response(pid, value=pid not in ('P06', 'P12'))
        report = self.run_evaluation()
        self.assertEqual(report['rule_states']['A']['L02']['state'], 'VERIFIED')
        self.assertTrue(report['outcomes']['by_arm']['A']['understanding_joint']['target_met'])
        self.assertEqual(report['outcomes']['by_arm']['A']['understanding_joint']['positive'], 5)
        self.manifest['responses'].pop()
        # Remove receipts targeting the removed input, since dangling receipts are errors.
        self.manifest['reviews'] = self.manifest['reviews'][:-2]
        partial = self.run_evaluation()
        self.assertEqual(partial['rule_states']['A']['L02']['state'], 'PENDING')
        self.assertFalse(partial['outcomes']['comparison']['comparable'])
        self.assertIsNone(partial['outcomes']['by_arm']['B']['product_understood']['target_met'])

    def test_capture_checklist_without_review_remains_pending(self):
        self.complete_external('A')
        self.manifest['reviews'] = [p for p in self.manifest['reviews']
                                    if strict_json(self.inputs / p)['review_kind'] != 'generation_capture']
        report = self.run_evaluation()
        self.assertEqual(report['rule_states']['A']['J08']['state'], 'PENDING')
        self.assertTrue(any(r['review_kind'] == 'generation_capture' for r in report['review_requests']))

    def test_capture_missing_binary_escape_or_wrong_original_rejected(self):
        for patch in ({'capture_path': 'absent.png'}, {'capture_path': '../outside.png'}, {'source_sha256': '0' * 64}):
            with self.subTest(patch=patch):
                self.manifest['screenshots'] = []
                descriptor = {'entry': 'A', 'artifact_sha256': self.assets['A']['sha256'],
                    'source_sha256': self.assets['A']['source_sha256'], 'capture_path': 'missing.png',
                    'captured_at': '2026-11-01T10:00:00Z'}
                descriptor.update(patch)
                self.add('screenshots', descriptor)
                report = self.run_evaluation()
                self.assertEqual(report['status'], 'FAIL')
                self.assertEqual(report['rule_states']['A']['J08']['state'], 'PENDING')

    def test_metrics_null_requires_reason_bool_and_negative_forbidden(self):
        self.complete_external('A')
        metric_path = self.manifest['metrics'][0]
        original = strict_json(self.inputs / metric_path)
        for patch in ({'reach': None}, {'shares': -1}, {'shares': True}, {'shares': 1.2}):
            with self.subTest(patch=patch):
                bad = copy.deepcopy(original)
                bad['measurements'].update(patch)
                if 'reach' in patch:
                    bad['unavailable_reasons'].pop('reach')
                self.write(metric_path, bad)
                self.assertEqual(self.run_evaluation()['status'], 'FAIL')

    def test_history_flags_required_no_invented_months_threshold(self):
        self.complete_external('A')
        path = self.manifest['history'][0]
        short = strict_json(self.inputs / path)
        short['observed_start'] = '2026-10-31T23:59:59Z'
        short['long_term_basis'] = '장기성의 타당성은 receipt에서 외부 검토'
        self.write(path, short)
        self.manifest['reviews'] = [p for p in self.manifest['reviews'] if strict_json(self.inputs / p)['review_kind'] != 'longitudinal']
        self.add('reviews', self.receipt('longitudinal', path, findings={k: True for k in ('independent', 'long_term', 'not_self_generated')}))
        report = self.run_evaluation()
        self.assertEqual(report['rule_states']['A']['L08']['state'], 'VERIFIED')
        receipt_path = self.manifest['reviews'][-1]
        rec = strict_json(self.inputs / receipt_path)
        rec['findings']['not_self_generated'] = False
        self.write(receipt_path, rec)
        report = self.run_evaluation()
        self.assertEqual(report['rule_states']['A']['L08']['state'], 'PENDING')

    def test_rejected_receipt_yields_rejected_rule(self):
        name = self.add('responses', self.response())
        self.add('reviews', self.receipt('source_attestation', name, verdict='rejected'))
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['rule_states']['A']['L02']['state'], 'REJECTED')

    def test_current_asset_changed_rejects_all_success(self):
        self.attested_response()
        (self.project / 'A.png').write_bytes(b'SYNTHETIC altered asset')
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)
        self.assertTrue(all(s['state'] == 'REJECTED' for s in report['rule_states']['A'].values()))


    def test_recall_before_24_hours_not_counted_or_merged(self):
        record = self.response(recall=True)
        record['recall_submitted_at'] = '2026-11-01T20:00:00Z'
        record['updated_at'] = '2026-11-01T20:00:01Z'
        record['events'] = record['events'][:3]
        self.add('responses', record)
        report = self.run_evaluation()
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 1)
        self.assertEqual(report['counts']['valid_recall_by_arm']['A'], 0)
        self.add('responses', self.response())
        report = self.run_evaluation()
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 0)

    def test_rewritten_first_event_or_screen_conflicts(self):
        for field in ('events', 'screen'):
            with self.subTest(field=field):
                self.manifest['responses'] = []
                self.add('responses', self.response())
                altered = self.response(recall=True)
                if field == 'events':
                    altered['events'][0]['at'] = '2026-11-01T10:00:02Z'
                else:
                    altered['screen']['width'] = 2000
                self.add('responses', altered)
                report = self.run_evaluation()
                self.assertEqual(report['counts']['valid_first_by_arm']['A'], 0)

    def test_future_nested_event_is_error(self):
        record = self.response()
        record['events'][0]['at'] = '2099-01-01T00:00:00Z'
        self.add('responses', record)
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 0)

    def test_ai_coding_alone_never_proves_human_source(self):
        record = self.response()
        name = self.add('responses', record)
        self.add('reviews', self.receipt('semantic_coding', name, findings=self.code(record, True), reviewer='AI'))
        report = self.run_evaluation()
        self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)
        self.assertEqual(report['counts']['coded_understanding_by_arm']['A'], 0)

    def test_only_current_selected_version_receipts_count(self):
        name = self.attested_response()
        self.add('responses', self.response(recall=True))
        report = self.run_evaluation()
        self.assertEqual(report['counts']['valid_first_by_arm']['A'], 1)
        self.assertEqual(report['counts']['valid_recall_by_arm']['A'], 1)
        self.assertEqual(report['counts']['verified_human_first_by_arm']['A'], 0)
        self.assertTrue(any(r['target_sha256'] != self.digest(self.inputs / name) for r in report['review_requests']))

    def test_metrics_separate_periods_preserve_null_and_actual_zero(self):
        self.complete_external('A')
        second = strict_json(self.inputs / self.manifest['metrics'][0])
        second.update(period_start='2026-11-02T00:00:00Z', period_end='2026-11-03T00:00:00Z')
        second['measurements']['shares'] = 3
        name = self.add('metrics', second)
        self.add('reviews', self.receipt('social_metrics', name))
        report = self.run_evaluation()
        periods = report['outcomes']['metrics']['A']
        self.assertEqual(len(periods), 2)
        self.assertEqual([p['measurements']['shares'] for p in periods], [0, 3])
        self.assertTrue(all(p['measurements']['reach'] is None for p in periods))

    def test_conflicting_review_findings_do_not_auto_pass(self):
        name = self.attested_response()
        self.add('reviews', self.receipt('semantic_coding', name, findings=self.code(self.response(), True)))
        report = self.run_evaluation()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['counts']['coded_understanding_by_arm']['A'], 0)

    def test_cli_stdout_is_json_and_optional_now(self):
        policy_path = self.root / 'policy.json'
        policy_path.write_text(json.dumps(self.policy), encoding='utf-8')
        self.write('evidence.json', self.manifest)
        for tail in ([], ['--now', NOW.isoformat()]):
            result = subprocess.run([sys.executable, '-B', str(MODULE_PATH), '--policy', str(policy_path),
                                     '--project-root', str(self.project), '--inputs', str(self.inputs), *tail],
                                    capture_output=True, text=True, encoding='utf-8', check=True)
            self.assertEqual(json.loads(result.stdout)['status'], 'PENDING')

    def test_production_inventory_is_not_fixture_storage(self):
        # Read-only sanity check. Real evidence may arrive later, so assert schema,
        # not a permanently hardcoded production count.
        path = AUTOMATION / 'inputs' / 'evidence.json'
        raw = path.read_bytes()
        manifest = strict_json(path)
        self.assertEqual(manifest['schema_version'], 1)
        self.assertEqual(path.read_bytes(), raw)
        for key in ('responses', 'reviews', 'screenshots', 'metrics', 'history'):
            self.assertIsInstance(manifest[key], list)
            self.assertFalse(any('synthetic-qa-' in str(value) for value in manifest[key]))


if __name__ == '__main__':
    unittest.main()
