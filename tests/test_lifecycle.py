"""
심어둔 엣지(planted) 합성데이터로 전체 신호 수명주기를 확인한다.
감지 → 알림/재알림 → WAIT 이 신호를 지우지 않음 → 수동 진입 → TP/SL/EXIT → 원장 재구성.
합성 데이터이므로 수익성 증거가 아니다 (파이프라인·불변식 검증용).
"""
import json

import numpy as np
import pandas as pd
import pytest

from conftest import offline_engine
from synthetic import planted_cached


@pytest.fixture()
def traded(pe):
    df, starts, cut = planted_cached(days=800)
    eng, store, clock = offline_engine(pe, df.iloc[:cut], df.index[cut - 1] + pd.Timedelta(minutes=1, seconds=20))
    final = eng.cycle(1000.0, tfs=['15m'])
    return pe, eng, store, clock, df, cut, final


def advance(store, clock, df, i):
    clock.t = (df.index[i - 1] + pd.Timedelta(minutes=1, seconds=20)).to_pydatetime()
    store.set_base(df.iloc[:i])


def test_planted_edge_is_detected_with_honest_null(traded):
    pe, eng, store, clock, df, cut, final = traded
    assert final['trade'] is True, final.get('reason')
    assert final['side'] == 1
    assert final['p_family'] <= pe.FAMILY_ALPHA and final['null_n'] >= 300
    assert final['risk_frac'] <= min(pe.RISK_CAP, final['growth']['st09_cap']) + 1e-12
    sz = final['sizing']
    assert sz['executable'] and sz['risk_actual'] <= final['risk_frac'] + 1e-12


def test_realert_schedule_2_5_15_then_pending_user(traded):
    pe, eng, store, clock, df, cut, final = traded
    sid = final['signal_id']
    fired = []
    for minute in range(0, 20):
        advance(store, clock, df, cut + minute)
        for ref_type, ref_id, a in pe.due_alerts(eng.state.read(), pe.utcnow()):
            fired.append(minute)
            eng.alert_fired(ref_type, ref_id)
    assert fired == [0, 2, 5, 15]
    assert eng.state.read()['signals'][-1]['status'] == 'PENDING_USER'
    assert sid == eng.state.read()['signals'][-1]['signal_id']


def test_wait_cycle_does_not_erase_actionable_signal(traded, monkeypatch):
    pe, eng, store, clock, df, cut, final = traded
    advance(store, clock, df, cut + 15)
    monkeypatch.setattr(pe, 'scan_tf', lambda snap, tf, *a, **k: pe.wait(tf, 'forced WAIT'))
    wait_final = eng.cycle(1000.0, tfs=['15m'])
    assert wait_final['trade'] is False
    screen = eng.state.peek(lambda st: pe.render_screen(st, wait_final, 1000.0))
    assert final['signal_id'] in screen and 'SIDE              LONG' in screen and 'LIVE  WAIT' in screen


def test_ack_stops_alerts(traded):
    pe, eng, store, clock, df, cut, final = traded
    eng.mark_seen()
    assert eng.state.read()['signals'][-1]['status'] == 'SEEN'
    assert pe.due_alerts(eng.state.read(), pe.utcnow() + pd.Timedelta(hours=1)) == []


def test_shadow_and_manual_tracking_are_separate(traded):
    pe, eng, store, clock, df, cut, final = traded
    sig = eng.state.read()['signals'][-1]
    pos = eng.open_manual(sig['signal_id'], final['entry'] * 1.001, final['sizing']['qty'],
                          final['tp_px'], final['sl_px'], 1000.0)
    assert eng.state.read()['signals'][-1]['status'] == 'ENTERED'
    advance(store, clock, df, cut + 6 * 60)
    events = eng.monitor(1000.0)
    st = eng.state.read()
    s, p = st['signals'][-1], st['manual'][-1]
    assert s['shadow']['state'] == 'CLOSED'
    assert pd.Timestamp(s['shadow']['fill_time']) >= pd.Timestamp(s['detected_at'])
    assert p['pos_id'] == pos['pos_id'] and p['status'] in ('TP', 'SL', 'EXIT_RECOMMENDED')
    assert any(e[0] == 'MANUAL' for e in events)
    assert p['entry'] != s['shadow']['fill_price']                 # 실제 체결가와 shadow 체결가는 별개
    pnl = eng.close_manual(p['pos_id'], s['shadow']['result']['exit_price'])
    assert eng.state.read()['manual'][-1]['status'] == 'CLOSED' and np.isfinite(pnl)


def test_opposite_signal_invalidates_manual_thesis(traded):
    pe, eng, store, clock, df, cut, final = traded
    sig = eng.state.read()['signals'][-1]
    eng.open_manual(sig['signal_id'], final['entry'], final['sizing']['qty'], final['tp_px'], final['sl_px'], 1000.0)
    fake = dict(final)
    fake.update(side=-1, tp_px=final['entry'] * 0.97, sl_px=final['entry'] * 1.01)
    with eng.state.tx() as st:
        eng._register(st, fake, 1000.0, store.snapshot())
    st = eng.state.read()
    assert st['manual'][-1]['status'] == 'EXIT_RECOMMENDED'
    assert st['manual'][-1]['pending_alert']['kind'] == 'THESIS INVALIDATED'
    assert st['signals'][0]['thesis'] == 'INVALIDATED'


def test_state_equals_ledger_fold_and_survives_corruption(traded):
    pe, eng, store, clock, df, cut, final = traded
    eng.mark_seen()
    live = eng.state.read()
    reb = eng.state.rebuild()
    dump = lambda x: json.dumps(pe.json_safe(x), sort_keys=True)
    assert dump(reb['signals']) == dump(live['signals'])
    with open(eng.state.path, 'w') as f:
        f.write('{"signals": [')
    fresh = pe.StateStore(eng.state.path, eng.state.ledger.path)
    assert dump(fresh.read()['signals']) == dump(live['signals'])
    assert 'state' in pe.HEALTH.critical()
    assert fresh.visual(final['signal_id'])['analogs']                      # 시각 증거는 원장에 보존


def test_recheck_never_chases_old_entry(traded):
    pe, eng, store, clock, df, cut, final = traded
    advance(store, clock, df, cut + 3 * 60)
    out = eng.recheck(1000.0)
    assert out['status'] in ('LATE_VALID', 'EXPIRED')
    if out['valid']:
        new = out['decision']
        assert new['signal_id'] != final['signal_id'] and new['entry'] == pytest.approx(store.snapshot().last_price())
    old = [s for s in eng.state.read()['signals'] if s['signal_id'] == final['signal_id']][0]
    assert old['last_recheck']['status'] == out['status']


def test_unverified_signal_is_labelled_and_risk_reduced(traded):
    pe, eng, store, clock, df, cut, final = traded
    assert final['evidence_level'].startswith('E3')
    assert final['multipliers']['evidence_ladder'] == pe.UNVERIFIED_RISK_MULT
    screen = eng.state.peek(lambda st: pe.render_screen(st, final, 1000.0))
    assert '미검증 신호' in screen


def test_evidence_certificate_requires_null_and_real_data(pe):
    base = pe._synthetic_1m(3, seed=8)
    eng, store, clock = offline_engine(pe, base, base.index[-1] + pd.Timedelta(minutes=1, seconds=10))
    good = dict(summary=dict(passed=True, n=80, ci_lo=0.05, dsr=0.95))
    assert eng.record_walkforward('15m', good, do_null=False, surrogate=False)['level'] == 'FAILED'
    assert eng.record_walkforward('15m', good, do_null=True, surrogate=True)['level'] == 'FAILED'
    assert eng.state.read()['evidence']['15m']['level'] == 'FAILED'
    cert = eng.record_walkforward('15m', good, do_null=True, surrogate=False)
    assert cert['level'] == 'E4' and eng.state.read()['evidence']['15m']['model_id'] == pe.MODEL_ID
    # 이후 실패 실험은 E4 를 덮지 않지만 원장에는 남는다
    eng.record_walkforward('15m', dict(summary=dict(passed=False)), do_null=True, surrogate=False)
    assert eng.state.read()['evidence']['15m']['level'] == 'E4'
    kinds = [e['kind'] for e in eng.state.ledger.read()]
    assert kinds.count('EVIDENCE') == 2 and kinds.count('SYSTEM') == 2     # 실험 4번 모두 기록됨
    book = eng.book(eng.state.read(), 1000.0, clock())
    assert book['evidence_gate'] and book['evidence']['15m']['level'] == 'E4'


def test_stale_data_blocks_new_signals(traded):
    pe, eng, store, clock, df, cut, final = traded
    clock.t = clock.t + pd.Timedelta(minutes=30).to_pytimedelta()
    out = eng.cycle(1000.0, tfs=['15m'])
    assert out['trade'] is False and '지연' in out['reason']
