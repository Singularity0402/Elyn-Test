#!/usr/bin/env python3
"""원답 보존 및 기록 품질 검사 전용. 의미/정답/사람 여부를 자동 판정하지 않는다."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys

FIRST_FIELDS = ('product', 'event', 'scene', 'share_recipient', 'share_sentence', 'share_reason')
RECALL_FIELDS = ('brand', 'scene')


def moment(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def protocol_from(path):
    text = path.read_text(encoding='utf-8-sig')
    def match(pattern):
        found = re.search(pattern, text)
        if not found:
            raise ValueError('protocol.js 형식 또는 필수 필드를 확인하세요: ' + pattern)
        return found
    pid = match(r"protocol_id:\s*'([^']+)'")[1]
    assignments = dict(re.findall(r"(P\d{2}):\s*'([AB])'", match(r'assignment:\s*Object.freeze\(\{([^}]+)\}')[1]))
    if set(assignments) != {f'P{i:02}' for i in range(1, 13)} or Counter(assignments.values()) != {'A': 6, 'B': 6}:
        raise ValueError('P01~P12, A6/B6 고정 배정이 필요합니다.')
    images = {}
    for arm in ('A', 'B'):
        found = match(arm + r":\s*Object.freeze\(\{path:\s*'([^']+)',\s*sha256:\s*'([a-f0-9]{64})'")
        images[arm] = {'path': found[1], 'sha256': found[2]}
    bounds = match(r'valid_exposure_ms:\s*Object.freeze\(\[(\d+),\s*(\d+)\]')
    if (int(bounds[1]), int(bounds[2])) != (2800, 3800):
        raise ValueError('고정된 노출시간 범위 2800..3800ms가 변경되었습니다.')
    return {'protocol_id': pid, 'assignment': assignments, 'images': images, 'minimum': 2800, 'maximum': 3800}


def filled(mapping, fields):
    return isinstance(mapping, dict) and all(isinstance(mapping.get(k), str) and bool(mapping[k].strip()) for k in fields)


def inspect_record(record, protocol, image_errors):
    issues = []
    def check(condition, code):
        if not condition:
            issues.append(code)
    check(record.get('record_kind') == 'participant', 'record_kind_invalid')
    check(type(record.get('schema_version')) is int and record['schema_version'] == 1, 'schema_version_invalid')
    check(record.get('protocol_id') == protocol['protocol_id'], 'protocol_id_mismatch')
    pid, arm = record.get('participant_id'), record.get('arm')
    check(isinstance(pid, str) and pid in protocol['assignment'], 'participant_id_invalid')
    check(isinstance(arm, str) and arm in ('A', 'B'), 'arm_invalid')
    if isinstance(pid, str) and pid in protocol['assignment']:
        check(arm == protocol['assignment'][pid], 'fixed_assignment_mismatch')
    if isinstance(arm, str) and arm in ('A', 'B'):
        check(record.get('image_sha256') == protocol['images'][arm]['sha256'], 'image_sha256_mismatch')
        check(arm not in image_errors, 'protocol_image_file_unverified')
    consent = record.get('consent')
    check(isinstance(consent, dict) and consent.get('agreed') is True and consent.get('adult') is True and moment(consent.get('at')) is not None, 'consent_missing_or_invalid')
    check(type(record.get('prior_exposure')) is bool, 'prior_exposure_missing')
    check(record.get('prior_exposure') is False, 'not_a_new_viewer')
    screen = record.get('screen')
    check(isinstance(screen, dict) and all(type(screen.get(k)) in (int, float) and math.isfinite(screen[k]) and screen[k] > 0 for k in ('width','height','viewport_width','viewport_height','device_pixel_ratio')), 'screen_missing_or_invalid')
    exposure = record.get('exposure_ms')
    check(type(exposure) in (float, int) and math.isfinite(exposure) and protocol['minimum'] <= exposure <= protocol['maximum'], 'exposure_ms_out_of_range_or_missing')
    check(record.get('interrupted') is False, 'exposure_interrupted_or_unknown')
    start, end = moment(record.get('exposure_started_at')), moment(record.get('exposure_ended_at'))
    created, updated = moment(record.get('created_at')), moment(record.get('updated_at'))
    check(created is not None and updated is not None and created <= updated, 'record_timestamps_invalid')
    check(start is not None and end is not None and end >= start, 'exposure_timestamps_invalid')
    if start is not None and end is not None and type(exposure) in (int,float) and math.isfinite(exposure):
        check(abs((end-start)*1000 - exposure) <= 1000, 'exposure_clock_inconsistent')
    if isinstance(consent, dict) and moment(consent.get('at')) is not None and start is not None:
        check(moment(consent['at']) <= start, 'consent_after_exposure')
    events = record.get('events')
    if not isinstance(events, list) or not all(isinstance(e, dict) and isinstance(e.get('type'), str) and moment(e.get('at')) is not None for e in events):
        issues.append('events_missing_or_invalid')
        events = []
    check(sum(e.get('type') == 'exposure_start' for e in events) == 1, 'exposure_start_count_invalid')
    check(sum(e.get('type') == 'exposure_end' for e in events) == 1, 'exposure_end_count_invalid')
    check(not any(e.get('type') in ('interruption', 'preparation_failed') for e in events), 'interruption_event_present')
    check(record.get('stage') in ('waiting','recall','complete'), 'first_response_not_submitted')
    check(filled(record.get('raw_answers'), FIRST_FIELDS), 'raw_answers_missing')
    submitted = moment(record.get('answers_submitted_at'))
    check(submitted is not None and end is not None and submitted >= end, 'answers_submission_time_invalid')
    recall_issues = []
    recall_time = moment(record.get('recall_submitted_at'))
    if not filled(record.get('recall_raw_answers'), RECALL_FIELDS):
        recall_issues.append('recall_raw_answers_missing')
    if recall_time is None or end is None or recall_time - end < 24*60*60:
        recall_issues.append('recall_before_24h_or_missing')
    if submitted is not None and recall_time is not None and recall_time < submitted:
        recall_issues.append('recall_before_first_submission')
    if record.get('stage') != 'complete':
        recall_issues.append('recall_not_submitted')
    if updated is not None and any(t is not None and t > updated for t in (end, submitted, recall_time)):
        issues.append('updated_at_precedes_submission')
    return issues, recall_issues


def aggregate(paths, protocol_path):
    protocol = protocol_from(protocol_path)
    image_errors = {}
    for arm, image in protocol['images'].items():
        file = (protocol_path.parent / image['path']).resolve()
        if not file.is_file():
            image_errors[arm] = 'protocol_image_file_missing'
        elif hashlib.sha256(file.read_bytes()).hexdigest() != image['sha256']:
            image_errors[arm] = 'protocol_image_file_hash_mismatch'
    report = {
        'report_kind': 'record_quality_audit_only', 'protocol_id': protocol['protocol_id'],
        'scope': 'A/B 파일럿 동등노출 비교. 경쟁대회 우위를 주장하지 않는다. L06은 실제 경쟁작 필수 기준으로 해석하지 않는다.',
        'interpretation': '품질조건 유효여부는 실제 사람이 응답했다는 외부 출처 확인과 다르다. 정답 자동채점·학술 유의성·수상확률·성과비율을 산출하지 않는다. 내부목표 5/6은 통계보장이 아니다.',
        'human_source_verification': 'unverified; 진행자가 별도 익명 현장/모집 기록으로 확인해야 함',
        'protocol_image_errors': image_errors, 'files': [], 'counts': {},
    }
    for path in sorted(set(paths)):
        entry = {'file': str(path.resolve()), 'raw_text': None, 'record': None, 'issues': [], 'recall_issues': [], 'eligible_new_first_exposure': False, 'eligible_24h_recall': False, 'human_source_verification': 'unverified'}
        try:
            entry['raw_text'] = path.read_bytes().decode('utf-8')
            record = json.loads(entry['raw_text'].lstrip('\ufeff'), parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite JSON: '+s)))
            entry['record'] = record
            if not isinstance(record, dict):
                entry['issues'] = ['record_must_be_object']
            elif record.get('record_kind') == 'qa':
                entry['issues'] = ['qa_excluded']
            else:
                entry['issues'], entry['recall_issues'] = inspect_record(record, protocol, image_errors)
        except (OSError, UnicodeError, ValueError, TypeError, OverflowError) as error:
            entry['issues'] = ['unreadable_or_invalid_json: ' + str(error)]
        report['files'].append(entry)
    ids = Counter(e['record'].get('participant_id') for e in report['files'] if isinstance(e['record'],dict) and e['record'].get('record_kind') != 'qa' and isinstance(e['record'].get('participant_id'),str))
    for entry in report['files']:
        rec = entry['record']
        if isinstance(rec,dict) and rec.get('record_kind') != 'qa' and isinstance(rec.get('participant_id'),str) and ids[rec['participant_id']] > 1:
            entry['issues'].append('duplicate_participant_id_all_copies_excluded')
        entry['eligible_new_first_exposure'] = not entry['issues']
        entry['eligible_24h_recall'] = entry['eligible_new_first_exposure'] and not entry['recall_issues']
    valid = [e for e in report['files'] if e['eligible_new_first_exposure']]
    report['counts'] = {
        'input_files': len(report['files']),
        'qa_excluded': sum(isinstance(e['record'],dict) and e['record'].get('record_kind') == 'qa' for e in report['files']),
        'eligible_new_first_exposure': len(valid),
        'eligible_24h_recall': sum(e['eligible_24h_recall'] for e in valid),
        'eligible_by_arm': {a: sum(e['record']['arm'] == a for e in valid) for a in ('A','B')},
    }
    if not valid:
        report['sample_status'] = '유효 신규표본 0명. 관객 결과나 비율을 만들지 않는다.'
    else:
        report['sample_status'] = '기록 품질 검사만 완료. 실제 사람 여부는 외부 출처 확인 전이며, 자유응답 해석은 별도 수동 검토 대상이다.'
    report['duplicate_ids'] = sorted(k for k,v in ids.items() if v > 1)
    report['missing_participant_ids'] = sorted(set(protocol['assignment']) - set(ids))
    report['missing_eligible_participant_ids'] = sorted(set(protocol['assignment']) - {e['record']['participant_id'] for e in valid})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='*', type=Path, help='응답 JSON 파일 또는 JSON만 보관한 디렉터리(비재귀)')
    parser.add_argument('--protocol', type=Path, default=Path(__file__).with_name('protocol.js'))
    parser.add_argument('--output', type=Path, help='감사 보고서 JSON. 입력 디렉터리 밖 경로를 권장')
    args = parser.parse_args()
    paths = []
    for path in args.inputs:
        if path.is_dir():
            paths.extend(path.glob('*.json'))
        elif path.is_file():
            paths.append(path)
        else:
            parser.error('입력이 없습니다: ' + str(path))
    if args.output and args.output.resolve() in {p.resolve() for p in paths}:
        parser.error('출력 경로가 입력 JSON과 같습니다. 원답을 덮어쓸 수 없습니다.')
    try:
        report = aggregate(paths, args.protocol.resolve())
    except (ValueError, OSError) as error:
        parser.error(str(error))
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(output, encoding='utf-8')
        print('품질 감사 보고서 저장: ' + str(args.output))
    else:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        print(output, end='')


if __name__ == '__main__':
    main()
