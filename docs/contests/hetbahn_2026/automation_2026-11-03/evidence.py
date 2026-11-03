"""Evidence inventory and receipt validation; never infer people or free-text meaning."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import sys
from urllib.parse import urlsplit

ARMS = ('A', 'B')
RULES = ('J08', 'L02', 'L03', 'L04', 'L05', 'L06', 'L08')
KINDS = ('responses', 'reviews', 'screenshots', 'metrics', 'history')
REVIEW_KINDS = {'source_attestation', 'semantic_coding', 'generation_capture',
                'social_metrics', 'longitudinal'}
SHA = re.compile(r'[a-f0-9]{64}\Z')
CONTAMINATED = re.compile(r'\b(?:qa|synthetic|fixture|dom|automated|automation|bot)\b|auto[_ -]?pass|automatic(?:ally)?|합성|자동생성|자동응답|자동.{0,4}(?:PASS|검증|통과)', re.I)
MEASUREMENTS = ('impressions', 'reach', 'shares', 'saves', 'reactions')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timezone-aware ISO timestamp required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timezone required')
    return parsed.astimezone(timezone.utc)


def strict_json(path, with_digest=False):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError('nonfinite JSON: ' + value)

    raw = path.read_bytes()
    result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs,
                        parse_constant=constant)

    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('nonfinite number')
        if isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)
    finite(result)
    return (result, hashlib.sha256(raw).hexdigest()) if with_digest else result


def inside(root, relative):
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError('nonempty relative file path required')
    if Path(relative).is_absolute() or PureWindowsPath(relative).drive or PureWindowsPath(relative).root:
        raise ValueError('absolute path forbidden')
    # Interpret both separators consistently, including when tests run on POSIX.
    candidate = (root / relative.replace('\\', '/')).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError('path escapes root: ' + relative)
    if not candidate.is_file():
        raise ValueError('missing file: ' + relative)
    return candidate


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def contaminated(record):
    if any(record.get(k) is True for k in ('auto_pass', 'automated_pass', 'automatic_pass')):
        return True
    if record.get('record_kind') == 'qa' or any(record.get(k) is True for k in ('qa', 'synthetic', 'test_only', 'automated')):
        return True
    for key in ('source_kind', 'source_type', 'provenance', 'record_kind', 'source_note', 'source', 'origin', 'kind'):
        value = record.get(key)
        if isinstance(value, str) and (CONTAMINATED.search(value.replace('_', ' ')) or value.lower() in ('ai', 'browser_automation', 'ai_generated', 'ai-generated')):
            return True
        if isinstance(value, dict) and contaminated(value):
            return True
    return False


def check_times(record, now):
    """Reject future times anywhere, including nested consent/events and unknown *_at."""
    if isinstance(record, list):
        for value in record:
            check_times(value, now)
    elif isinstance(record, dict):
        for key, value in record.items():
            if (key.endswith('_at') or key in ('at', 'period_start', 'period_end', 'observed_start', 'observed_end')) and value is not None:
                if timestamp(value) > now:
                    raise ValueError('future timestamp: ' + key)
            elif isinstance(value, (dict, list)):
                check_times(value, now)


def url(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in ('https', 'http') and bool(parsed.hostname) and not parsed.username


def load_auditor(protocol_path):
    # Compile without import machinery: no __pycache__ mutation in the shared repo.
    path = protocol_path.with_name('응답_집계.py')
    namespace = {'__name__': '_evidence_record_auditor', '__file__': str(path)}
    exec(compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec'), namespace)
    return namespace


def compatible_versions(older, newer, auditor, protocol, image_errors):
    if older == newer:
        return True
    mutable = {'updated_at', 'stage', 'recall_raw_answers', 'recall_submitted_at', 'events'}
    if {k: v for k, v in older.items() if k not in mutable} != {k: v for k, v in newer.items() if k not in mutable}:
        return False
    if older.get('stage') != 'waiting' or older.get('recall_raw_answers') not in ({}, None) or older.get('recall_submitted_at') is not None:
        return False
    if timestamp(older['updated_at']) >= timestamp(newer['updated_at']):
        return False
    first_issues, recall_issues = auditor['inspect_record'](newer, protocol, image_errors)
    if first_issues or recall_issues:
        return False
    old_events, new_events = older.get('events', []), newer.get('events', [])
    if new_events[:len(old_events)] != old_events:
        return False
    return all(e.get('type') in ('recall_opened', 'recall_submitted', 'download', 'revisit')
               and timestamp(e['at']) >= timestamp(older['updated_at'])
               for e in new_events[len(old_events):])


def evaluate(policy: dict, project_root: Path, inputs_root: Path, now_utc: datetime) -> dict:
    report = {
        'status': 'PENDING',
        'rule_states': {a: {r: {'state': 'PENDING', 'reason': 'required external evidence or review is incomplete'} for r in RULES} for a in ARMS},
        'counts': {'received_response_files': 0, 'qa_excluded': 0,
                   **{k: {a: 0 for a in ARMS} for k in (
                       'valid_first_by_arm', 'valid_recall_by_arm', 'verified_human_first_by_arm',
                       'verified_human_recall_by_arm', 'coded_understanding_by_arm',
                       'coded_share_intent_by_arm', 'coded_recall_by_arm')},
                   'conflicting_participant_ids': 0, 'excluded_response_files': 0,
                   'valid_review_files': 0, 'verified_metrics_files': 0, 'verified_history_files': 0},
        'errors': [], 'review_requests': [], 'exclusions': [], 'response_records': [],
        'outcomes': {'by_arm': {}, 'metrics': {a: [] for a in ARMS}, 'history': {a: [] for a in ARMS},
                     'comparison': {'comparable': False, 'scope': 'fixed A/B pilot only; no contest-wide ranking or winner inference'}},
    }
    errors = report['errors']
    counts = report['counts']
    states = report['rule_states']
    entities = {}
    loaded = {kind: [] for kind in KINDS}
    request_keys = set()

    def error(code, file, reason):
        item = {'code': code, 'file': str(file), 'reason': str(reason)}
        if item not in errors:
            errors.append(item)

    def state(arm, rule, value, reason, **details):
        if states[arm][rule]['state'] == 'REJECTED' and value != 'REJECTED':
            return
        states[arm][rule] = {'state': value, 'reason': reason, **details}

    def finish():
        report['status'] = 'FAIL' if errors or any(s['state'] == 'REJECTED' for rules in states.values() for s in rules.values()) else (
            'PASS' if all(s['state'] == 'VERIFIED' for rules in states.values() for s in rules.values()) else 'PENDING')
        return report

    try:
        project_root, inputs_root = Path(project_root).resolve(), Path(inputs_root).resolve()
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise ValueError('now_utc must be timezone-aware')
        now_utc = now_utc.astimezone(timezone.utc)
        plan = policy['sample_plan']
        for key, required in {'participants': 12, 'per_arm': 6, 'target_ms': 3000, 'recall_hours': 24}.items():
            if type(plan.get(key)) is not int or plan[key] != required:
                raise ValueError('fixed sample plan changed: ' + key)
        if plan.get('valid_ms') != [2800, 3800] or plan.get('internal_target_per_arm') != 5:
            raise ValueError('fixed exposure or internal target changed')
        protocol_path = inside(project_root, policy['protocol_path'])
        auditor = load_auditor(protocol_path)
        protocol = auditor['protocol_from'](protocol_path)
    except (KeyError, OSError, ValueError, TypeError, AttributeError) as exc:
        error('policy_or_protocol_invalid', 'policy', exc)
        return finish()

    image_errors, pins, sources = {}, {}, {}
    for arm in ARMS:
        try:
            asset = policy['assets'][arm]
            path = inside(project_root, asset['path'])
            digest = sha256(path)
            protocol_image = (protocol_path.parent / protocol['images'][arm]['path']).resolve()
            if (digest != asset['sha256'] or digest != protocol['images'][arm]['sha256']
                    or protocol_image != path or not protocol_image.is_relative_to(project_root)):
                raise ValueError('current artifact / policy / protocol pin mismatch')
            pins[arm] = digest
            source = inside(project_root, asset['source_path'])
            sources[arm] = sha256(source)
            if sources[arm] != asset['source_sha256']:
                raise ValueError('generation original pin mismatch')
        except (KeyError, OSError, ValueError, TypeError) as exc:
            image_errors[arm] = str(exc)
            pins.pop(arm, None)
            sources.pop(arm, None)
            error('artifact_pin_invalid', arm, exc)
            for rule in RULES:
                state(arm, rule, 'REJECTED', str(exc))

    try:
        manifest = strict_json(inside(inputs_root, 'evidence.json'))
        if (not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int
                or manifest['schema_version'] != 1 or set(manifest) != {'schema_version', *KINDS}
                or any(not isinstance(manifest.get(k), list) for k in KINDS)):
            raise ValueError('schema 1 manifest requires exactly the five path arrays')
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        error('manifest_invalid', 'evidence.json', exc)
        return finish()

    seen_paths = set()
    for kind in KINDS:
        for relative in manifest[kind]:
            record = None
            path = None
            try:
                path = inside(inputs_root, relative)
                if path in seen_paths:
                    raise ValueError('duplicate manifest path')
                seen_paths.add(path)
                if kind == 'responses':
                    counts['received_response_files'] += 1
                record, digest = strict_json(path, with_digest=True)
                if not isinstance(record, dict):
                    raise ValueError('JSON object required')
                if 'schema_version' in record and (type(record['schema_version']) is not int or record['schema_version'] != 1):
                    raise ValueError('unsupported schema_version')
                if contaminated(record):
                    report['exclusions'].append({'file': relative, 'reason': 'qa_or_source_contamination'})
                    if kind == 'responses':
                        counts['qa_excluded'] += 1
                        counts['excluded_response_files'] += 1
                    continue
                check_times(record, now_utc)
                item = {'file': relative, 'sha256': digest, 'record': record}
                loaded[kind].append(item)
            except (OSError, ValueError, TypeError, UnicodeError, OverflowError) as exc:
                error('input_invalid', relative, exc)
                if kind == 'responses':
                    if isinstance(record, dict) and path is not None:
                        loaded[kind].append({'file': relative, 'sha256': digest, 'record': record,
                                             'preissues': ['invalid_input: ' + str(exc)]})
                    else:
                        counts['excluded_response_files'] += 1

    # Validate records before grouping; even an invalid duplicate must not hide a conflict.
    groups = defaultdict(list)
    for item in loaded['responses']:
        rec = item['record']
        try:
            issues, recall_issues = auditor['inspect_record'](rec, protocol, image_errors)
            # Preserve reused audit issues; chronology is an additional check.
            if not issues and timestamp(rec['created_at']) > timestamp(rec['exposure_started_at']):
                issues.append('created_after_exposure')
            if not issues and any(timestamp(e['at']) < timestamp(rec['created_at']) or timestamp(e['at']) > timestamp(rec['updated_at']) for e in rec.get('events', [])):
                issues.append('event_outside_record_lifetime')
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            issues, recall_issues = ['invalid_record: ' + str(exc)], ['invalid_record']
        issues = item.get('preissues', []) + issues
        item.update(issues=issues, recall_issues=recall_issues)
        groups[rec.get('participant_id') if isinstance(rec.get('participant_id'), str) else '__invalid__:' + item['file']].append(item)
        entities[item['sha256']] = {'entry': rec.get('arm'), 'kind': 'responses', 'item': item,
                                    'time': rec.get('updated_at')}

    valid = []
    for pid, versions in groups.items():
        versions.sort(key=lambda x: (str(x['record'].get('updated_at', '')), x['file']))
        # Sorting parsed instants avoids offset-dependent lexical ordering.
        if all(not x['issues'] for x in versions):
            versions.sort(key=lambda x: timestamp(x['record']['updated_at']))
        conflict = len(versions) > 1 and (any(x['issues'] for x in versions) or any(
            not compatible_versions(x['record'], y['record'], auditor, protocol, image_errors)
            for x, y in zip(versions, versions[1:])))
        if conflict:
            counts['conflicting_participant_ids'] += 1
        selected = versions[-1]
        issues = ['conflicting_participant_id_all_versions_excluded'] if conflict else selected['issues']
        report['response_records'].append({
            'participant_id': pid, 'entry': selected['record'].get('arm'),
            'selected_file': None if issues else selected['file'],
            'versions': [{'file': x['file'], 'sha256': x['sha256'], 'issues': x['issues'], 'recall_issues': x['recall_issues']} for x in versions],
            'issues': issues,
        })
        if issues:
            counts['excluded_response_files'] += len(versions)
            for item in versions:
                report['exclusions'].append({'file': item['file'], 'reason': ', '.join(issues)})
            continue
        valid.append(selected)
        arm = selected['record']['arm']
        counts['valid_first_by_arm'][arm] += 1
        counts['valid_recall_by_arm'][arm] += int(not selected['recall_issues'])

    # Screenshot descriptors bind the actual capture bytes to both current image and original.
    for kind in ('screenshots', 'metrics', 'history'):
        accepted = []
        for item in loaded[kind]:
            rec, relative = item['record'], item['file']
            try:
                arm = rec.get('entry')
                if arm not in pins or rec.get('artifact_sha256') != pins[arm]:
                    raise ValueError('current artifact pin mismatch')
                if kind == 'screenshots':
                    if rec.get('source_sha256') != sources[arm]:
                        raise ValueError('current generation original pin mismatch')
                    timestamp(rec['captured_at'])
                    capture = inside(inputs_root, rec['capture_path'])
                    from PIL import Image
                    with Image.open(capture) as image:
                        image.verify()
                    item['target_sha256'] = sha256(capture)
                    item['target_file'] = rec['capture_path']
                    when = rec['captured_at']
                elif kind == 'metrics':
                    if not url(rec.get('platform_url')) or timestamp(rec['period_start']) > timestamp(rec['period_end']):
                        raise ValueError('metrics URL or period invalid')
                    values, reasons = rec.get('measurements'), rec.get('unavailable_reasons', {})
                    if not isinstance(values, dict) or set(values) != set(MEASUREMENTS) or not isinstance(reasons, dict):
                        raise ValueError('five distinct measurements required')
                    for key, value in values.items():
                        if value is None:
                            if not nonempty(reasons.get(key)):
                                raise ValueError('null requires unavailable_reasons.' + key)
                        elif type(value) is not int or value < 0:
                            raise ValueError('measurement must be nonnegative integer or null: ' + key)
                    when = rec['period_end']
                else:
                    if (not url(rec.get('source_url')) or timestamp(rec['observed_start']) >= timestamp(rec['observed_end'])
                            or not nonempty(rec.get('independence_note')) or not nonempty(rec.get('long_term_basis'))):
                        raise ValueError('history URL / observation period / basis invalid')
                    when = rec['observed_end']
                item.setdefault('target_sha256', item['sha256'])
                item.setdefault('target_file', relative)
                entities[item['target_sha256']] = {'entry': arm, 'kind': kind, 'item': item, 'time': when}
                accepted.append(item)
            except (KeyError, OSError, ValueError, TypeError, ImportError) as exc:
                error(kind + '_invalid', relative, exc)
        loaded[kind] = accepted

    receipts = defaultdict(list)
    kind_targets = {'source_attestation': 'responses', 'semantic_coding': 'responses',
                    'generation_capture': 'screenshots', 'social_metrics': 'metrics', 'longitudinal': 'history'}
    for item in loaded['reviews']:
        rec = item['record']
        try:
            kind, arm = rec.get('review_kind'), rec.get('entry')
            reviewer = rec.get('reviewer')
            if kind not in REVIEW_KINDS or arm not in pins or rec.get('artifact_sha256') != pins[arm]:
                raise ValueError('review kind, entry, or current artifact pin invalid')
            if not isinstance(reviewer, dict) or not nonempty(reviewer.get('id')) or reviewer.get('kind') not in ('human', 'AI'):
                raise ValueError('reviewer id and human/AI kind required')
            if kind == 'source_attestation' and reviewer['kind'] != 'human':
                raise ValueError('source_attestation requires separate human review')
            if isinstance(rec.get('findings'), dict) and contaminated(rec['findings']):
                raise ValueError('automated/QA findings cannot substitute for external review')
            if rec.get('verdict') not in ('verified', 'rejected', 'pending') or not isinstance(rec.get('findings'), dict) or not nonempty(rec.get('source_note')):
                raise ValueError('explicit verdict, findings object and source_note required')
            digest = rec.get('target_sha256')
            if not isinstance(digest, str) or not SHA.fullmatch(digest) or digest not in entities:
                raise ValueError('review target is not an actual inventoried evidence file')
            target = entities[digest]
            if target['entry'] != arm or target['kind'] != kind_targets[kind]:
                raise ValueError('review target entry/type mismatch')
            if timestamp(rec['reviewed_at']) < timestamp(target['time']):
                raise ValueError('review predates reviewed evidence')
            receipts[(kind, arm, digest)].append(item)
            counts['valid_review_files'] += 1
        except (KeyError, ValueError, TypeError) as exc:
            error('review_invalid', item['file'], exc)

    def reviewed(kind, arm, item, rule, required=(), quote_fields=None):
        digest = item.get('target_sha256', item['sha256'])
        matches = receipts.get((kind, arm, digest), [])
        if any(x['record']['verdict'] == 'rejected' for x in matches):
            state(arm, rule, 'REJECTED', 'review receipt explicitly rejects evidence', target_sha256=digest)
            return False
        verified = [x for x in matches if x['record']['verdict'] == 'verified']
        merged = {}
        conflict = False
        for receipt in verified:
            for key, value in receipt['record']['findings'].items():
                # Quotes can cover disjoint coding tasks in separate receipts.
                if key == 'quotes' and isinstance(value, dict) and isinstance(merged.get(key, {}), dict):
                    old = merged.setdefault(key, {})
                    for qkey, qvalue in value.items():
                        if qkey in old and old[qkey] != qvalue:
                            conflict = True
                        old[qkey] = qvalue
                else:
                    if key in merged and merged[key] != value:
                        conflict = True
                    merged[key] = value
        if conflict:
            error('conflicting_reviews', item['file'], kind + ': contradictory verified findings')
            state(arm, rule, 'REJECTED', 'conflicting review receipts', target_sha256=digest)
            return False
        okay = bool(verified)
        for key in required:
            okay = okay and type(merged.get(key)) is bool
            if kind in ('source_attestation', 'generation_capture', 'longitudinal'):
                okay = okay and merged.get(key) is True
        if okay and quote_fields:
            quotes = merged.get('quotes', {})
            answers = item['record'].get('raw_answers', {}) if rule != 'L04' else item['record'].get('recall_raw_answers', {})
            for key, fields in quote_fields.items():
                quote = quotes.get(key) if isinstance(quotes, dict) else None
                candidates = quote if isinstance(quote, list) else [quote]
                def grounded(q):
                    if isinstance(q, str):
                        return nonempty(q) and any(q in answers.get(f, '') for f in fields)
                    return (isinstance(q, dict) and q.get('field') in fields and nonempty(q.get('text'))
                            and q['text'] in answers.get(q['field'], ''))
                if not candidates or not all(grounded(q) for q in candidates):
                    okay = False
                    if quote is not None:
                        error('coding_quote_not_in_raw_answer', item['file'], key)
        if not okay:
            key = (kind, arm, digest, rule)
            if key not in request_keys:
                request_keys.add(key)
                report['review_requests'].append({'review_kind': kind, 'entry': arm, 'rule': rule,
                    'artifact_sha256': pins.get(arm), 'target_sha256': digest,
                    'target_file': item.get('target_file', item['file']), 'required_findings': list(required),
                    'reason': 'external review missing, pending, incomplete, or ungrounded; no automatic semantic/source conclusion'})
        if okay:
            item.setdefault('accepted_findings', {})[rule] = merged
        return okay

    by_arm = {a: [] for a in ARMS}
    for item in valid:
        arm = item['record']['arm']
        by_arm[arm].append(item)
        human = reviewed('source_attestation', arm, item, 'L02')
        item['human'] = human
        counts['verified_human_first_by_arm'][arm] += int(human)
        recall = not item['recall_issues']
        counts['verified_human_recall_by_arm'][arm] += int(human and recall)
        understood = reviewed('semantic_coding', arm, item, 'L02', ('product_understood', 'event_understood'),
                              {'product_understood': ('product',), 'event_understood': ('event',)})
        shared = reviewed('semantic_coding', arm, item, 'L03', ('share_intent',),
                          {'share_intent': ('share_recipient', 'share_sentence', 'share_reason')})
        recalled = recall and reviewed('semantic_coding', arm, item, 'L04', ('brand_recalled', 'relationship_recalled'),
                          {'brand_recalled': ('brand',), 'relationship_recalled': ('scene',)})
        counts['coded_understanding_by_arm'][arm] += int(human and understood)
        counts['coded_share_intent_by_arm'][arm] += int(human and shared)
        counts['coded_recall_by_arm'][arm] += int(human and recalled)
        item['measured'] = {'L02': human and understood, 'L03': human and shared, 'L04': human and recalled}

    for arm in ARMS:
        for item in loaded['screenshots']:
            if item['record']['entry'] == arm and reviewed('generation_capture', arm, item, 'J08',
                    ('service_visible', 'prompt_visible', 'result_visible', 'entry_matches')):
                state(arm, 'J08', 'VERIFIED', 'capture file, current original hash, and review receipt verified',
                      target_sha256=item['target_sha256'], source_sha256=sources[arm])
        for kind, review_kind, rule in (('metrics', 'social_metrics', 'L05'), ('history', 'longitudinal', 'L08')):
            for item in loaded[kind]:
                if item['record']['entry'] != arm:
                    continue
                required = ('independent', 'long_term', 'not_self_generated') if kind == 'history' else ()
                if reviewed(review_kind, arm, item, rule, required):
                    counts['verified_' + kind + '_files'] += 1
                    report['outcomes'][kind][arm].append({'file': item['file'], 'sha256': item['sha256'], **item['record']})
                    state(arm, rule, 'VERIFIED', 'actual file and external source review verified; periods and measures remain distinct')
        for rule, key in (('L02', 'coded_understanding_by_arm'), ('L03', 'coded_share_intent_by_arm'), ('L04', 'coded_recall_by_arm')):
            enough = counts[key][arm] == plan['per_arm']
            if rule == 'L02':
                enough = enough and sum(counts[key].values()) == plan['participants']
            if enough:
                state(arm, rule, 'VERIFIED', 'complete human-attested cohort and grounded coding; measurement completion only')
        outcomes = {}
        for rule, keys in (('L02', ('product_understood', 'event_understood')), ('L03', ('share_intent',)), ('L04', ('brand_recalled', 'relationship_recalled'))):
            measured = [x for x in by_arm[arm] if x['measured'][rule]]
            for key in keys:
                positive = sum(x['accepted_findings'][rule][key] for x in measured)
                outcomes[key] = {'measured': len(measured), 'positive': positive,
                    'percent': 100 * positive / len(measured) if measured else None,
                    'target_per_arm': plan['internal_target_per_arm'],
                    'target_met': positive >= plan['internal_target_per_arm'] if len(measured) == plan['per_arm'] else None}
            if rule in ('L02', 'L04'):
                positive = sum(all(x['accepted_findings'][rule][key] for key in keys) for x in measured)
                outcomes['understanding_joint' if rule == 'L02' else 'recall_joint'] = {
                    'measured': len(measured), 'positive': positive,
                    'percent': 100 * positive / len(measured) if measured else None,
                    'target_per_arm': plan['internal_target_per_arm'],
                    'target_met': positive >= plan['internal_target_per_arm'] if len(measured) == plan['per_arm'] else None}
        outcomes['actual_sharing_from_intent'] = None
        report['outcomes']['by_arm'][arm] = outcomes
    comparable = all(counts['coded_understanding_by_arm'][a] == plan['per_arm']
                     and counts['coded_share_intent_by_arm'][a] == plan['per_arm'] for a in ARMS)
    if comparable:
        for arm in ARMS:
            state(arm, 'L06', 'VERIFIED', 'complete current-image human cohorts, fixed assignment and equivalent protocol; pilot comparison only')
    report['outcomes']['comparison']['comparable'] = comparable
    report['outcomes']['comparison']['recall_comparable'] = all(counts['coded_recall_by_arm'][a] == plan['per_arm'] for a in ARMS)
    return finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--now', help='timezone-aware ISO time; defaults to current UTC')
    args = parser.parse_args()
    try:
        policy = strict_json(args.policy)
        if not isinstance(policy, dict):
            raise ValueError('policy must be an object')
        report = evaluate(policy, args.project_root, args.inputs,
                          timestamp(args.now) if args.now else datetime.now(timezone.utc))
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        report = {'status': 'FAIL', 'rule_states': {a: {r: {'state': 'REJECTED', 'reason': str(exc)} for r in RULES} for a in ARMS},
                  'counts': {}, 'errors': [{'code': 'cli_invalid', 'reason': str(exc)}], 'review_requests': [], 'outcomes': {}}
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if report['status'] == 'FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
