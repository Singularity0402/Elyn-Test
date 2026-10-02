"""
Strategy Lab: 무엣지 시장에서는 아무것도 통과시키지 않고, 진짜 추세가 있으면 찾아내는지.
합성 데이터이므로 수익성 증거가 아니다.
"""
import os

import numpy as np
import pandas as pd


def _trend_1m(days, strength, seed=3):
    g = np.random.default_rng(seed)
    n = days * 1440
    phi = 1 - 1 / (1440 * 3)
    e = g.normal(0, 1, n)
    d = np.empty(n)
    acc = 0.0
    for i in range(n):                       # AR(1) 추세 성분 (scipy 없이)
        acc = phi * acc + e[i]
        d[i] = acc
    r = g.normal(0, 0.0007, n) + d * strength
    c = 30000 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) * (1 + np.abs(g.normal(0, 0.0003, n)))
    lo = np.minimum(o, c) * (1 - np.abs(g.normal(0, 0.0003, n)))
    return pd.DataFrame(dict(open=o, high=hi, low=lo, close=c, volume=1.0, taker_buy_base=0.5, trades=1.0, era=1.0),
                        index=pd.date_range('2019-09-09', periods=n, freq='1min'))


def _passed(res):
    return [r for r in res['rows'] if r['oos']['n'] >= 50 and r['oos']['ci_lo'] > 0 and r['oos']['dsr'] >= 0.9]


def test_lab_rejects_no_edge_market(pe):
    base = _trend_1m(1300, 0.0)
    res = pe.lab_run(base, tfs=('1h', '4h'))
    assert not _passed(res)
    assert '통과한 절차 없음' in res['report']


def test_lab_finds_real_trend_and_hides_holdout(pe):
    base = _trend_1m(2000, 0.0000004)          # 전략군이 늘수록(절차 17개) 통과 기준이 올라가므로 표본외 기간을 충분히
    res = pe.lab_run(base, tfs=('1h', '4h'))
    assert _passed(res)
    assert 'holdout평균R' not in res['report'] and '봉인' in res['report']
    shown = pe.lab_run(base, tfs=('4h',), families=['donchian'], reveal_holdout=True)
    assert 'holdout평균R' in shown['report']


def test_intraday_families_run_and_respect_tf_scope(pe):
    base = _trend_1m(900, 0.0)
    g = np.random.default_rng(1)
    base['volume'] = np.exp(g.normal(3, 0.5, len(base)))
    base['taker_buy_base'] = base['volume'] * np.clip(0.5 + g.normal(0, 0.1, len(base)), 0, 1)
    res = pe.lab_run(base, tfs=('15m', '1h'), families=['volbreak', 'session', 'flow', 'rsi2', 'keltner'])
    pairs = {(r['tf'], r['family']) for r in res['rows']}
    assert ('15m', 'session') in pairs and ('1h', 'session') not in pairs        # 개장 레인지는 단기 TF 만
    assert res['n_trials'] == len(pairs) == 9
    snap = pe.Snapshot(base, base.index[-1].to_pydatetime())
    ind = pe._lab_indicators(snap.tf('15m'))
    for fam in ('volbreak', 'session', 'rsi2'):
        tgt = pe._lab_target(fam, pe.LAB_GRIDS[fam][0], ind)
        assert set(np.unique(tgt)) <= {-1, 0, 1} and np.abs(tgt).sum() > 0


def test_lab_sim_stop_is_minus_one_R_plus_costs(pe):
    n = 50
    o = np.full(n, 100.0)
    c = o.copy()
    h = o + 0.5
    lo = o - 0.5
    lo[10] = 90.0                                   # 진입 직후 손절
    atr = np.full(n, 0.01)
    tgt = np.zeros(n, dtype=np.int64)
    tgt[8:] = 1
    ei, xi, sd, rr = pe.lab_sim(o, h, lo, c, atr, tgt, 2.0, 0, 0.0014, 0.0)
    assert len(rr) >= 1 and ei[0] == 9 and xi[0] == 10
    assert abs(rr[0] - (-1.0 - 0.0014 / 0.02)) < 1e-9
    assert len(rr) == 1                              # 손절 후 같은 신호로 재진입하지 않음


# ── 지정가 진입 · 비용 시나리오 ────────────────────────────────────────
def test_limit_entry_fills_only_when_price_trades_through(pe):
    n = 30
    o = 100.0 + np.arange(n, dtype=np.float64)      # 계속 오르는 시장: 봉 저가 = 시가 → 롱 지정가는 안 받힌다
    c = o + 0.9
    h = o + 1.0
    lo = o.copy()
    lo[15] = o[15] * (1 - 0.0005)                    # 15번 봉에서만 시가 아래로 관통
    atr = np.full(n, 0.01)
    tgt = np.zeros(n, dtype=np.int64)
    tgt[5:20] = 1
    ei, xi, sd, rr = pe.lab_sim_x(o, h, lo, c, atr, tgt, 2.0, 0, 0.0002, 0.0007, 0.0007, 0.0, pe.MAKER_TP_THROUGH)
    assert list(ei) == [15]                          # 6~14번 봉은 달아나서 못 받음 (역선택), 15번에서 체결
    ei_t, _, _, _ = pe.lab_sim_x(o, h, lo, c, atr, tgt, 2.0, 0, 0.0007, 0.0007, 0.0007, 0.0, -1.0)
    assert list(ei_t) == [6]                         # 시장가는 바로 진입
    x = xi[0]
    expect = ((o[x] / o[15] - 1) - 0.0002 - 0.0007) / 0.02
    assert abs(rr[0] - expect) < 1e-9                # 진입 maker + 신호 청산 taker


def test_cost_modes_change_costs_and_are_reported(pe):
    base = _trend_1m(1300, 0.0)
    a = pe.lab_run(base, tfs=('4h',), families=['donchian'], cost_mode='taker')
    b = pe.lab_run(base, tfs=('4h',), families=['donchian'], cost_mode='maker_entry')
    assert '[taker]' in a['report'] and '[maker_entry]' in b['report'] and '체결은 보장되지 않는다' in b['report']
    assert a['rows'][0]['oos']['n'] > 0 and b['rows'][0]['oos']['n'] > 0
    import pytest
    with pytest.raises(ValueError):
        pe.lab_run(base, tfs=('4h',), families=['donchian'], cost_mode='free')


# ── 사전 선언 가설 하나만 검증 ─────────────────────────────────────────
def test_declared_single_hypothesis_matches_exploration_and_uses_full_trial_count(pe):
    base = _trend_1m(1300, 0.0)
    full = pe.lab_run(base, tfs=('1h', '4h'), families=['donchian', 'tsmom'])
    one = pe.lab_run(base, only='4h:donchian', n_trials_declared=full['n_trials'], reveal_holdout=True)
    assert [(r['tf'], r['family']) for r in one['rows']] == [('4h', 'donchian')]
    ref = next(r for r in full['rows'] if (r['tf'], r['family']) == ('4h', 'donchian'))
    assert one['rows'][0]['oos']['n'] == ref['oos']['n']
    assert np.isclose(np.nan_to_num(one['rows'][0]['oos']['mean_r']), np.nan_to_num(ref['oos']['mean_r']))
    assert one['n_trials'] == 1 and one['n_dsr'] == full['n_trials'] == 4
    assert '사전 선언 가설: 4h:donchian' in one['report'] and 'holdout 판정 규칙' in one['report']
    r1 = one['rows'][0]
    assert r1['hold_windows'] >= 3 and 0 <= r1['hold_idle'] <= r1['hold_windows'] and 'holdout 에 걸친 test 창' in one['report']
    sealed = pe.lab_run(base, only='4h:donchian', n_trials_declared=4)
    assert 'holdout 봉인' in sealed['report'] and 'holdout평균R' not in sealed['report']


def test_holdout_verdict_rule(pe):
    v = pe.lab_holdout_verdict
    assert v(dict(n=0, mean_r=float('nan'), ci_lo=float('nan'))).startswith('판정 불가')
    assert v(dict(n=12, mean_r=-0.1, ci_lo=-0.5)).startswith('반증 —')
    assert v(dict(n=12, mean_r=0.3, ci_lo=-0.2)).startswith('반증 안 됨')
    assert v(dict(n=60, mean_r=0.3, ci_lo=0.05)).startswith('확인')


def test_only_rejects_unknown_or_out_of_scope_pairs(pe):
    import pytest
    for bad in ('4h:session', '1m:flow', '4h:nope', '15m:funding'):
        with pytest.raises(ValueError):
            pe.lab_pairs(bad)
    assert pe.lab_pairs('4h:flow, 1h:funding') == [('4h', 'flow'), ('1h', 'funding')]
    assert pe.main(['--lab', '--only', '4h:session']) == 2           # 네트워크 전에 거절
    assert pe.main(['--lab', '--cost', 'free']) == 2


def test_surrogate_test_reports_selection_aware_p_values(pe):
    base = _trend_1m(1300, 0.0)
    res = pe.lab_surrogate_test(base, n=2, only='4h:donchian')
    assert 'p(같은 절차)' in res['report'] and 'p(최고 절차)' in res['report']
    assert len(res['best']) == 2 and len(res['same']['4h:donchian']) == 2


# ── 펀딩비 ─────────────────────────────────────────────────────────────
def _funding(index_start='2019-09-10', days=1300, seed=5):
    g = np.random.default_rng(seed)
    t = pd.date_range(index_start, periods=days * 3, freq='8h')
    return pd.Series(0.0001 + g.normal(0, 0.0002, len(t)), index=t, name='rate')


def test_funding_percentile_is_causal_and_goes_stale(pe):
    f = pd.Series(np.arange(400, dtype=np.float64), index=pd.date_range('2024-01-01', periods=400, freq='8h'))
    idx = pd.date_range('2024-03-01', periods=6, freq='4h')        # 4h 봉 시작 시각
    pct = pe._lab_funding_pct(idx, 240, f)
    # 00:00~04:00 봉(마감 04:00) 은 00:00 정산을, 04:00~08:00 봉(마감 08:00) 도 08:00 정산은 아직 못 본다
    j0 = f.index.searchsorted(pd.Timestamp('2024-03-01 00:00'))
    roll = f.rolling(270, min_periods=135).rank(pct=True).values
    assert pct[0] == roll[j0] and pct[1] == roll[j0] and pct[2] == roll[j0 + 1]
    gap = f.drop(f.index[(f.index > '2024-02-29 08:00') & (f.index < '2024-03-02')])
    assert np.isnan(pe._lab_funding_pct(idx, 240, gap)[3])          # 정산이 16시간 넘게 비면 신호 없음


def test_funding_family_skipped_without_data_and_counted_with_it(pe):
    base = _trend_1m(1300, 0.0)
    no = pe.lab_run(base, tfs=('1h', '4h'), families=['funding', 'tsmom'])
    assert {r['family'] for r in no['rows']} == {'tsmom'} and no['n_trials'] == 2
    assert '펀딩비 전략군 생략' in no['report']
    yes = pe.lab_run(base, tfs=('1h', '4h'), families=['funding', 'tsmom'], funding=_funding())
    assert {(r['tf'], r['family']) for r in yes['rows']} >= {('1h', 'funding'), ('4h', 'funding')}
    assert yes['n_trials'] == 4 and '정산' in yes['report']
    fr = [r for r in yes['rows'] if r['family'] == 'funding']
    assert all(r['oos']['n'] + r['idle_windows'] > 0 for r in fr)
    import pytest
    with pytest.raises(ValueError):
        pe.lab_run(base, only='4h:funding')


def test_load_funding_history_caches_and_resumes(pe):
    t0 = 1568102400000
    rows = [dict(symbol='BTCUSDT', fundingTime=t0 + k * 8 * 3600_000, fundingRate=f'{0.0001 * (k % 5):.8f}')
            for k in range(1500)]

    class FakeHttp:
        def __init__(self, data):
            self.data, self.urls = data, []

        def get_json(self, url, timeout=None):
            pe.PublicHttp.check_allowed(url)                          # 허용목록을 통과하는 공개 URL 인지
            self.urls.append(url)
            start = int(url.split('startTime=')[1].split('&')[0])
            return [r for r in self.data if r['fundingTime'] >= start][:1000]

    http = FakeHttp(rows[:1200])
    s = pe.load_funding_history(http)
    assert len(s) == 1200 and len(http.urls) == 2 and s.index[0] == pd.Timestamp(t0, unit='ms')
    assert os.path.exists(pe.Paths.funding())
    http2 = FakeHttp(rows)
    s2 = pe.load_funding_history(http2)
    assert len(s2) == 1500 and len(http2.urls) == 1
    assert f'startTime={rows[1199]["fundingTime"] + 1}' in http2.urls[0]   # 캐시 다음부터 이어 받기
    off = pe.load_funding_history(pe.PublicHttp(enabled=False))
    assert len(off) == 1500 and 'funding' in pe.HEALTH.items           # 오프라인이면 캐시로, 경고는 남긴다


def test_funding_endpoint_is_public_allowlisted(pe):
    assert pe.PublicHttp.check_allowed('https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime=1&limit=1000')
