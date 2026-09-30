"""
V611 알려진/신규 결함을 baseline 에서 재현하고, V612 에서 수정됐는지 확인한다.
각 테스트 이름의 ID 는 AUDIT_V611_V612.md 의 결함 ID 와 같다.
"""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from conftest import offline_engine
from synthetic import planted_cached, random_walk_tf


# ── F-01 ─────────────────────────────────────────────────────────
def test_F01_v611_wait_path_crashes(pe611):
    with pytest.raises(ValueError, match='not enough values to unpack'):
        ok, why, votes = pe611._candidate_precheck_v600({'reason': '데이터 부족', 'K': 192}, [])


def test_F01_v612_precheck_single_return_type(pe):
    out = pe.precheck({'reason': '데이터 부족', 'K': 192}, [], '15m', 16)
    assert isinstance(out, dict) and out['ok'] is False and out['votes'] == []


def test_F01_v612_failing_scan_is_marked_and_backs_off(pe, monkeypatch):
    base = pe._synthetic_1m(3, seed=2)
    eng, store, clock = offline_engine(pe, base, base.index[-1] + pd.Timedelta(minutes=1, seconds=10))

    def boom(*a, **k):
        raise RuntimeError('synthetic scan failure')
    monkeypatch.setattr(pe, 'scan_tf', boom)
    for i in range(pe.CRITICAL_AFTER_FAILS):
        final = eng.cycle(1000.0, tfs=['15m'])
        assert final['trade'] is False and '스캔 오류' in final['reason']
        st = eng.state.read()
        assert st['last_scan']['15m'] == pe.bar_key('15m', clock())          # 실패해도 bar-key 기록
        assert st['fails']['15m']['count'] == i + 1
        assert '15m' not in eng.due_models()                                  # backoff 중 → 폭주 없음
        clock.t = pd.Timestamp(st['fails']['15m']['retry_at']).to_pydatetime()
    assert 'scan:15m' in pe.HEALTH.critical()                                 # 3회 연속 → CRITICAL


# ── F-02 ─────────────────────────────────────────────────────────
def _minute_frame(start, n, price=100.0):
    idx = pd.date_range(start, periods=n, freq='1min')
    return pd.DataFrame(dict(open=price, high=price, low=price, close=price, volume=1.0,
                             taker_buy_base=0.5, trades=1.0, era=1.0), index=idx)


def test_F02_v611_shadow_open_time_is_backdated(pe611):
    now = datetime(2026, 9, 30, 11, 0, 20)
    base = _minute_frame('2026-09-28 00:00', 3540)            # ~ 10:59 까지
    pe611_utcnow = pe611.utcnow
    try:
        pe611.utcnow = lambda: now
        dm = pe611.DataManager()
        dm.base = base
        dm.ensure = lambda force_refresh=False, progress=None: dm.base
        open_time = pd.Timestamp(dm.get('1h').index[-1])        # V611 이 shadow open_time 으로 쓰는 값
    finally:
        pe611.utcnow = pe611_utcnow
    scored_before_signal = base[(base.index > open_time) & (base.index < pd.Timestamp('2026-09-30 11:00'))]
    assert open_time == pd.Timestamp('2026-09-30 10:00') and len(scored_before_signal) == 59


def test_F02_v612_shadow_scores_only_after_detection(pe):
    base = _minute_frame('2026-09-30 09:00', 240)
    # 감지 이전 봉들에 SL 을 건드리는 급락을 심어 둔다 → 새 규칙에서는 무시돼야 함
    base.loc[pd.Timestamp('2026-09-30 10:30'):pd.Timestamp('2026-09-30 10:59'), 'low'] = 90.0
    detected = pd.Timestamp('2026-09-30 11:00:20')
    sh = dict(state='PENDING_FILL', first_bar=str(detected.ceil('min')), side=1, tp_px=110.0, sl_px=95.0,
              max_hold_min=60, qty=0.01, risk_usdt=1.0, tf='1h', H=1)
    up = pe.shadow_step(sh, base)
    assert pd.Timestamp(up['fill_time']) == pd.Timestamp('2026-09-30 11:01')
    assert up['state'] == 'CLOSED' and up['result']['reason'] == 'TIME'     # 감지 전 급락은 SL 로 치지 않음


# ── F-03 ─────────────────────────────────────────────────────────
def test_F03_v611_block_bootstrap_is_not_a_block_bootstrap(pe611):
    import inspect
    src = inspect.getsource(pe611.block_bootstrap_pvalue)
    assert 'rng.choice(pool_idx, size=n_draw, replace=False)' in src and 'block' not in src.split('"""')[2]


def test_F03_v612_stationary_block_bootstrap_preserves_dependence(pe):
    g = np.random.default_rng(0)
    x = np.zeros(400)
    for t in range(1, 400):
        x[t] = 0.8 * x[t - 1] + g.normal()
    iid = pe.stationary_block_bootstrap(x, n_boot=800, mean_block=1.0, rng=np.random.default_rng(1))
    blk = pe.stationary_block_bootstrap(x, n_boot=800, mean_block=20.0, rng=np.random.default_rng(1))
    assert blk.std() > 1.8 * iid.std()        # AR(1) 의 평균 불확실성을 block 이 제대로 반영


# ── F-04 ─────────────────────────────────────────────────────────
def test_F04_v611_null_uses_equal_weights_while_observed_is_weighted(pe611):
    import inspect
    src = inspect.getsource(pe611.matched_null_v500)
    assert 'ew = np.ones(len(sample),dtype=np.float64)/len(sample)' in src


def test_F04_v612_null_uses_identical_estimator(pe, monkeypatch):
    df = random_walk_tf(20000, seed=11)
    ch = pe.Channels(df)
    nb, err = pe.find_neighbors(ch, 96, 16, topk=36)
    assert nb is not None, err
    seen = []
    real = pe.observed_statistic

    def spy(HI, LO, CL, starts, weights, tf, K, H):
        seen.append(np.asarray(weights).copy())
        return real(HI, LO, CL, starts, weights, tf, K, H)
    monkeypatch.setattr(pe, 'observed_statistic', spy)
    pe.matched_null(ch, None, '15m', 96, 16, nb, 0.0, False, n_boot=5, rng=np.random.default_rng(0))
    w = np.asarray(nb['weights'])
    assert len(seen) >= 5 and all(np.allclose(s, w) for s in seen)       # paired: 같은 가중치 벡터


# ── F-09 ─────────────────────────────────────────────────────────
def test_F09_v611_neff_gate_is_mathematically_vacuous(pe611):
    w = pe611._v500_soft_cap_weights(np.r_[np.ones(11), np.full(25, 1e-9)], cap=0.09)
    assert 1 / np.square(w).sum() > 11.0 > pe611.V600_MIN_NEFF


def test_F09_v612_time_cluster_neff_catches_same_episode(pe):
    w = np.ones(36) / 36
    ends = pd.date_range('2024-05-01', periods=36, freq='6h')               # 전부 9일 안 = 한 국면
    neff_t, n_cl = pe.neff_time(pe.ts_ns(ends), w)
    assert n_cl == 1 and neff_t == pytest.approx(1.0)
    spread = pd.date_range('2020-01-01', periods=36, freq='30D')
    assert pe.neff_time(pe.ts_ns(spread), w)[0] == pytest.approx(36.0)


# ── R1-N01 ───────────────────────────────────────────────────────
def test_R1N01_v611_malformed_shadow_is_silent_permanent_hold(pe611):
    state = dict(active=dict(open_time='not-a-time', entry=1.0, tp_px=2.0, sl_px=0.5, side=1), closed=[], signals=[])

    class DM:
        def ensure(self, force_refresh=False):
            return pd.DataFrame(dict(high=[1.0], low=[1.0], close=[1.0]), index=pd.DatetimeIndex(['2026-09-30']))
    assert pe611._update_shadow_position_v600(DM(), state) is None
    assert state['active'] is not None


def test_R1N01_v612_malformed_shadow_is_quarantined_and_scanning_continues(pe):
    base = pe._synthetic_1m(3, seed=4)
    eng, store, clock = offline_engine(pe, base, base.index[-1] + pd.Timedelta(minutes=1, seconds=10))
    with eng.state.tx() as st:
        eng.state.emit(st, 'SIGNAL_DETECTED', signal=dict(
            signal_id='BAD', side=1, status='SEEN', detected_at=str(base.index[-100]), max_hold_min=60,
            shadow=dict(state='OPEN', first_bar='garbage')))
    final = eng.cycle(1000.0, tfs=['15m'])
    st = eng.state.read()
    assert st['signals'][0]['shadow']['state'] == 'QUARANTINED'
    assert 'shadow:BAD' in pe.HEALTH.critical()
    assert final.get('hold') is None and final['alternatives'][0]['tf'] == '15m'   # 스캔은 계속됨


# ── R-unit ───────────────────────────────────────────────────────
def test_Runit_v612_stop_loss_is_exactly_minus_one_R(pe):
    T, n = 20, 36
    HI = np.full((n, T), 0.001)
    LO = np.full((n, T), -0.02)                 # 전부 손절
    CL = np.full((n, T), -0.02)
    starts = np.arange(n) * 100
    oo = pe.crossfit_direction(HI, LO, CL, starts, np.ones(n) / n, 1, '15m', 96, 16)
    if oo is not None:
        sl_hits = oo['code'] == -1
        assert np.allclose(oo['R'][sl_hits], -1.0)


def test_Runit_v611_divides_by_final_sl(pe611):
    import inspect
    src = inspect.getsource(pe611.optimize_growth_risk_v600)
    assert 'r_mult = vals / sl' in src          # vals 는 fold 마다 다른 SL 로 만든 손익


# ── ST-09 ────────────────────────────────────────────────────────
def test_ST09_v612_zero_edge_drawdown_constraint_binds(pe):
    g = np.random.default_rng(5)
    R = g.choice([-1.0, 2.5], size=36, p=[0.45, 0.55]) + g.normal(0, 0.05, 36)
    cand = dict(r_vals=R, r_weights=np.ones(36) / 36, r_order=np.arange(36), side=1, tp=0.02, sl=0.008)
    HI = np.abs(g.normal(0, .004, (36, 16)))
    LO = -np.abs(g.normal(0, .004, (36, 16)))
    out = pe.growth_risk(cand, HI, LO, '15m', 16, rng=np.random.default_rng(1))
    assert out['risk'] <= out['st09_cap'] + 1e-12
    assert out['st09_dd_prob'] <= pe.ST09_MAX_DD_PROB and out['st09_floor_prob'] <= pe.ST09_FLOOR_PROB


# ── 기회 억제 (opportunity suppression) ──────────────────────────
def test_opportunity_v611_active_shadow_blocks_all_scans(pe611):
    import inspect
    src = inspect.getsource(pe611.oneclick_scan_v600)
    assert "if state.get('active'):" in src and 'hold=True' in src


def test_opportunity_v612_open_shadow_does_not_block_scan(pe):
    base = pe._synthetic_1m(3, seed=6)
    eng, store, clock = offline_engine(pe, base, base.index[-1] + pd.Timedelta(minutes=1, seconds=10))
    with eng.state.tx() as st:
        eng.state.emit(st, 'SIGNAL_DETECTED', signal=dict(
            signal_id='OPEN1', side=1, status='SEEN', detected_at=str(base.index[-10]), max_hold_min=240,
            shadow=dict(state='PENDING_FILL', first_bar=str(base.index[-5]), side=1, tp_px=1e9, sl_px=1.0,
                        max_hold_min=240, qty=0.001, risk_usdt=1.0, tf='15m', H=16)))
    final = eng.cycle(1000.0, tfs=['5m', '15m'])
    assert [d['tf'] for d in final['alternatives']] == ['5m', '15m']
    assert eng.state.read()['signals'][0]['shadow']['state'] == 'OPEN'


# ── 상태 경합 (lost update) ──────────────────────────────────────
def test_state_concurrent_writers_do_not_lose_events(pe):
    import threading
    ss = pe.StateStore()
    with ss.tx() as st:
        ss.emit(st, 'SIGNAL_DETECTED', signal=dict(signal_id='S0', side=1, status='ALERTING',
                                                   detected_at=pe._iso_now(), max_hold_min=60))

    def writer(i):
        with ss.tx() as st:
            ss.emit(st, 'SIGNAL_DETECTED', signal=dict(signal_id=f'S{i}', side=1, status='ALERTING',
                                                       detected_at=pe._iso_now(), max_hold_min=60))

    def seer():
        for _ in range(20):
            with ss.tx() as st:
                ss.emit(st, 'SIGNAL_UPDATE', signal_id='S0', fields=dict(status='SEEN'))
    th = [threading.Thread(target=writer, args=(i,)) for i in range(1, 21)] + [threading.Thread(target=seer)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    ids = {s['signal_id'] for s in pe.StateStore(ss.path, ss.ledger.path).read()['signals']}
    assert ids == {f'S{i}' for i in range(21)}
    assert pe.StateStore(ss.path, ss.ledger.path).read()['signals'][0]['status'] == 'SEEN'


# ── 사이징: 검증기는 위험을 올리지 못한다 ────────────────────────
def test_sizing_never_raises_risk_to_meet_min_notional(pe):
    sz = pe.size_position(100.0, 60000.0, 0.01, 0.005, '15m', 16, pe.FALLBACK_RULES)
    assert sz['executable'] is False and sz['need_risk'] > 0.005


def test_sizing_invariants_random(pe):
    g = np.random.default_rng(3)
    for _ in range(500):
        seed = float(g.uniform(50, 100000))
        sz = pe.size_position(seed, float(g.uniform(15000, 150000)), float(g.uniform(0.001, 0.04)),
                              float(g.uniform(0.0003, 0.01)), '15m', 16, pe.FALLBACK_RULES)
        if sz['executable']:
            assert sz['risk_actual'] <= sz['risk_frac'] + 1e-12
            assert 1 <= sz['lev'] <= pe.MAX_LEV and isinstance(sz['lev'], int)
            assert sz['margin'] <= seed * pe.MARGIN_CAP + 1e-6
            assert sz['notional'] >= pe.FALLBACK_RULES['min_notional'] - 1e-6


def test_context_never_creates_or_raises(pe):
    for spread in (0.5, 10.0):
        for fr in (-0.002, 0.0, 0.0007, 0.002):
            for side in (1, -1):
                m_, veto, _ = pe.context_multiplier(dict(spread_bps=spread, funding_rate=fr, oi_change_1h=0.05,
                                                         taker_buy_sell=0.5), side, '15m', 16)
                assert 0.0 <= m_ <= 1.0


def test_planted_edge_fixture_is_valid():
    df, starts, cut = planted_cached(days=300)
    assert len(starts) > 20 and abs(df['close'].values[cut - 1] - 60000) < 1e-6
