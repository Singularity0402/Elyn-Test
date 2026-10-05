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
    ei, xi, sd, rr = pe.lab_sim_x(o, h, lo, c, atr, tgt, 2.0, 0, 0.0002, 0.0007, 0.0007, 0.0, pe.MAKER_TP_THROUGH, 0.0, 0.0)
    assert list(ei) == [15]                          # 6~14번 봉은 달아나서 못 받음 (역선택), 15번에서 체결
    ei_t, _, _, _ = pe.lab_sim_x(o, h, lo, c, atr, tgt, 2.0, 0, 0.0007, 0.0007, 0.0007, 0.0, -1.0, 0.0, 0.0)
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


# ── 패턴 반복(유사 차트 k-NN) ───────────────────────────────────────────
def _frame_4h(n=7800, motif=0.03, noise=0.004, seed=0, start='2019-09-09', period=37):
    g = np.random.default_rng(seed)
    t = np.arange(n)
    lp = motif * np.sin(2 * np.pi * t / period + seed) + np.cumsum(g.normal(0, noise, n))
    c = 30000 * np.exp(lp)
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) * (1 + np.abs(g.normal(0, 0.002, n)))
    lo = np.minimum(o, c) * (1 - np.abs(g.normal(0, 0.002, n)))
    return pd.DataFrame(dict(open=o, high=hi, low=lo, close=c, volume=1.0, taker_buy_base=0.5, trades=1.0, era=1.0),
                        index=pd.date_range(start, periods=n, freq='4h'))


def test_analog_is_causal_finds_repeating_pattern_and_rests_without_one(pe):
    if not pe.NUMBA_OK:
        import pytest
        pytest.skip('numba 없음 — 패턴 반복 전략군은 생략된다')
    f = _frame_4h(9000)
    p = dict(K=24, H=6, th=1.5, k=2.0)
    full = pe._lab_target('analog', p, pe._lab_indicators(f))
    part = pe._lab_target('analog', p, pe._lab_indicators(f.iloc[:6000]))
    assert np.array_equal(full[:6000], part) and np.abs(full).sum() > 0      # 미래 데이터를 바꿔도 과거 신호 불변
    res = pe.lab_run(None, tf_frames={'4h': f}, families=['analog'], tfs=('4h',))
    m = res['rows'][0]['oos']
    assert m['n'] >= 50 and m['ci_lo'] > 0                                    # 반복되는 모양이 있으면 찾는다
    flat = _frame_4h(9000, motif=0.0, noise=0.008, seed=3)
    m0 = pe.lab_run(None, tf_frames={'4h': flat}, families=['analog'], tfs=('4h',))['rows'][0]['oos']
    assert not (m0['n'] >= 50 and m0['ci_lo'] > 0 and m0['dsr'] >= 0.9)      # 없으면 통과시키지 않는다


def test_available_families_follow_data_and_numba(pe):
    fams = pe.lab_available_families(None)
    assert 'funding' not in fams and ('analog' in fams) == pe.NUMBA_OK
    assert 'funding' in pe.lab_available_families(_funding())


def test_tf_frames_and_fixed_holdout_date(pe):
    f = _frame_4h(7800)
    hs = pd.Timestamp('2022-06-01')
    res = pe.lab_run(None, tf_frames={'4h': f}, families=['tsmom'], tfs=('4h',), holdout_start=hs, symbol='ETHUSDT')
    r = res['rows'][0]
    assert res['holdout_start'].startswith('2022-06-01') and 'ETHUSDT' in res['report'] and 'REST 4h 봉' in res['report']
    assert len(r['oos_t']) == r['oos']['n'] and (r['oos_t'] < np.datetime64(hs)).all()


# ── 다른 코인 재현 검증 ────────────────────────────────────────────────
def test_fetch_klines_resumes_and_drops_unfinished_bar(pe):
    t0 = 1577836800000                                   # 2020-01-01
    step = 4 * 3600_000
    rows = [[t0 + k * step, '1', '2', '0.5', str(1 + k), '10', t0 + (k + 1) * step - 1, '0', 7, '6', '0', '0']
            for k in range(1600)]

    class FakeHttp:
        def __init__(self, n):
            self.n, self.urls = n, []

        def get_json(self, url, timeout=None):
            pe.PublicHttp.check_allowed(url)
            self.urls.append(url)
            start = int(url.split('startTime=')[1].split('&')[0])
            return [r for r in rows[:self.n] if r[0] >= start][:1000]

    from conftest import Clock
    pe.utcnow = Clock(pd.Timestamp(t0 + 1300 * step - 1, unit='ms'))   # 1299번 봉은 아직 진행 중
    http = FakeHttp(1300)
    df = pe.fetch_klines_tf(http, 'ETHUSDT', '4h')
    assert len(df) == 1299 and list(df.columns) == pe.STORE_COLS and len(http.urls) == 2
    assert df['taker_buy_base'].iloc[0] == 6.0 and df['trades'].iloc[0] == 7.0 and df['close'].iloc[3] == 4.0
    pe.utcnow = Clock(pd.Timestamp(t0 + 1600 * step, unit='ms'))
    http2 = FakeHttp(1600)
    df2 = pe.fetch_klines_tf(http2, 'ETHUSDT', '4h')
    assert len(df2) == 1600 and f'startTime={t0 + 1299 * step}' in http2.urls[0]     # 진행 중이던 봉부터 다시


def test_cross_asset_replication_verdicts(pe):
    btc = _trend_1m(1300, 0.0)
    good = {s: {'4h': _frame_4h(7800, seed=k)} for k, s in enumerate(('ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT'))}
    res = pe.lab_cross_asset(btc, '4h:tsmom', list(good), frames_by_symbol=good, n_trials_declared=39)
    sm = res['summary'][0]
    assert sm['verdict'].startswith('재현 확인') and sm['n'] >= 100 and sm['pos'] == sm['tot'] == 4
    assert '가설을 고른 데이터' in res['report'] and res['holdout_start'] == res['btc']['holdout_start']
    hs = np.datetime64(pd.Timestamp(res['holdout_start']))
    flat = {s: {'4h': _frame_4h(7800, motif=0.0, noise=0.008, seed=10 + k)} for k, s in enumerate(('ETHUSDT', 'SOLUSDT'))}
    res0 = pe.lab_cross_asset(btc, '4h:tsmom', list(flat) + ['NOPEUSDT'], frames_by_symbol=flat)
    assert not res0['summary'][0]['verdict'].startswith('재현 확인') and 'NOPEUSDT' in res0['skipped']
    one = pe.lab_run(None, tf_frames=good['ETHUSDT'], only='4h:tsmom', holdout_start=res['holdout_start'])
    assert (one['rows'][0]['oos_t'] < hs).all()                      # 알트도 BTC holdout 날짜 이후는 봉인
    import pytest
    with pytest.raises(ValueError):
        pe.lab_cross_asset(btc, None, ['ETHUSDT'], frames_by_symbol=good)


def test_replication_verdict_rule(pe):
    v = pe.lab_replication_verdict
    assert v(0, float('nan'), float('nan'), 0, 0).startswith('판정 불가')
    assert v(300, -0.01, -0.2, 2, 6).startswith('재현 실패')
    assert v(300, 0.2, 0.05, 4, 6).startswith('재현 확인')
    assert v(300, 0.2, 0.05, 3, 6).startswith('불충분')          # 코인 2/3 미만
    assert v(80, 0.4, 0.10, 6, 6).startswith('불충분')           # 체결 100 미만


def test_cli_symbols_requires_declared_hypothesis(pe):
    assert pe.main(['--lab', '--symbols', 'default']) == 2
    assert pe.main(['--lab', '--only', '4h:flow', '--symbols', 'ETH/USDT']) == 2


# ── 하루 복리 목표 ─────────────────────────────────────────────────────
def test_daily_growth_bets_only_on_evidence_and_respects_concurrency(pe):
    g = np.random.default_rng(0)
    days = pd.date_range('2024-01-01', periods=400, freq='D').values
    R = g.choice([-1.0, 1.5], size=400, p=[0.5, 0.5])                   # 평균 약 +0.25R (상한 25% 안쪽)
    f, d = pe.lab_daily_growth(R, days, days[0], days[-1])
    assert 0 < f < pe.LAB_F_MAX and d > 0
    assert pe.lab_daily_growth(R, days, days[0], days[-1], haircut=R.mean() + 0.05) == (0.0, 0.0)   # 하한 < 0 → 0
    assert pe.lab_daily_growth(R, days, days[0], days[-1], haircut=float('nan')) == (0.0, 0.0)
    f2, _ = pe.lab_daily_growth(np.r_[R, R], np.r_[days, days], days[0], days[-1])       # 같은 날 두 배로 들고 있으면
    assert f2 < f and abs(f2 - f / 2) <= 0.01                                              # 거래당 위험은 절반
    f_gap, d_gap = pe.lab_daily_growth(R, days, days[0], days[0] + np.timedelta64(799, 'D'))
    assert d_gap < d                                                                       # 거래 없는 날도 하루로 센다


def test_single_lab_reports_daily_growth_column(pe):
    res = pe.lab_run(_trend_1m(1300, 0.0), tfs=('4h',), families=['donchian'])
    assert '보수 하루복리@위험' in res['report'] and 'g_day' in res['rows'][0]['oos']
    import pytest
    with pytest.raises(ValueError):
        pe.lab_run(_trend_1m(1300, 0.0), only='4h:xsmom')                 # 코인간 상대강도는 묶음 전용


# ── 코인 묶음 ──────────────────────────────────────────────────────────
def test_universe_pools_coins_and_finds_shared_structure(pe):
    coins = {s: {'4h': _frame_4h(7800, seed=k)} for k, s in enumerate(('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT'))}
    res = pe.lab_run_universe(coins, tfs=('4h',), families=['tsmom'])
    r = res['rows'][0]
    assert pe.lab_universe_passed(r) and r['oos']['g_day'] > 0 and r['oos']['f_star'] > 0
    assert r['tot'] == 4 and '코인 묶음 4개' in res['report'] and '사전 기준 통과' in res['report']
    flat = {s: {'4h': _frame_4h(7800, motif=0.0, noise=0.008, seed=20 + k)}
            for k, s in enumerate(('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT'))}
    res0 = pe.lab_run_universe(flat, tfs=('4h',), families=['tsmom', 'donchian'])
    assert not any(pe.lab_universe_passed(x) for x in res0['rows']) and '통과한 절차 없음' in res0['report']
    assert all(x['oos']['g_day'] == 0.0 or x['oos']['ci_lo'] > 0 for x in res0['rows'])


def _xs_coins(n=7800, k=6, seed=0):
    g = np.random.default_rng(seed)
    out = {}
    for j in range(k):
        reg = np.repeat(g.choice([-1.0, 1.0], size=n // 360 + 1), 360)[:n]          # 60일마다 바뀌는 코인별 추세
        r = 0.0015 * reg + g.normal(0, 0.008, n) + g.normal(0, 0.004, n)
        c = 100 * np.exp(np.cumsum(r))
        o = np.r_[c[0], c[:-1]]
        out[f'C{j}USDT'] = {'4h': pd.DataFrame(dict(open=o, high=np.maximum(o, c) * 1.002, low=np.minimum(o, c) * 0.998,
                                                    close=c, volume=1.0, taker_buy_base=0.5, trades=1.0, era=1.0),
                                               index=pd.date_range('2019-09-09', periods=n, freq='4h'))}
    return out


def test_xs_momentum_ranks_are_causal_and_find_relative_trends(pe):
    coins = _xs_coins()
    ftf = {s: v['4h'] for s, v in coins.items()}
    full = pe._lab_xs_ranks(ftf, [42])
    cut = {s: df.iloc[:5000] for s, df in ftf.items()}
    part = pe._lab_xs_ranks(cut, [42])
    for s in ftf:
        a, b = full[s][42][:5000], part[s][42]
        assert np.allclose(np.nan_to_num(a, nan=-1), np.nan_to_num(b, nan=-1))       # 미래가 바뀌어도 과거 순위 불변
        v = a[~np.isnan(a)]
        assert v.min() >= 0 and v.max() <= 1
    res = pe.lab_run_universe(coins, tfs=('4h',), families=['xsmom'])
    m = res['rows'][0]['oos']
    assert m['n'] >= 20 and m['mean_r'] > 0 and m['ci_lo'] > 0           # 선택 규칙은 긴 추세(L=168, 적은 거래·큰 R)를 고른다


def test_universe_surrogate_keeps_coins_in_sync_and_returns(pe):
    f = _frame_4h(3000)
    sf = pe.make_surrogate_frames({'A': {'4h': f}, 'B': {'4h': f.copy()}}, seed=3)
    a, b = sf['A']['4h'], sf['B']['4h']
    assert np.allclose(a['close'].values, b['close'].values)                       # 같은 날짜 순서 → 동조 유지
    r0 = np.diff(np.log(f['close'].values))
    r1 = np.diff(np.log(a['close'].values))
    assert abs(r1.std() / r0.std() - 1) < 0.01 and not np.allclose(r0, r1)       # 같은 수익률 분포, 다른 순서
    res = pe.lab_universe_surrogate_test({'BTCUSDT': {'4h': f}, 'ETHUSDT': {'4h': _frame_4h(3000, seed=4)}}, n=2,
                                         tfs=('4h',), families=['tsmom'])
    assert 'p(최고 절차)' in res['report'] and len(res['best']) == 2


def test_cli_universe_argument_validation(pe):
    assert pe.main(['--lab', '--universe', '--symbols', 'ETHUSDT', '--only', '4h:flow']) == 2
    assert pe.main(['--lab', '--universe', 'default', '--tfs', '5m']) == 2
    assert pe.main(['--lab', '--universe', 'ETH-USDT']) == 2


# ── 연구 일지: 패인 기록과 같은 실수 방지 ─────────────────────────────
def test_journal_seed_holds_full_history_and_persists(pe):
    j = pe.ResearchJournal.load()
    assert j.n_trials() == 146 and str(j.anchor.date()) == '2026-10-04' and str(j.seen_from.date()) == '2021-11-27'
    assert j.state('btc_presample|4h:keltner') == 'confirmed' and j.state('wf|15m:analog_engine') == 'refuted'
    assert j.state('btc|5m:tsmom') == 'no_evidence' and j.state('btc|4h:flow') == 'candidate'
    assert j.state('final|4h:keltner') == 'refuted' and j.state('universe|4h:keltner') == 'refuted'
    assert [p['id'] for p in j.d['prereg']] == ['P1', 'P2', 'P3', 'P4'] and j.state('alt_presample|4h:consensus') == 'confirmed'
    assert j.state('regime|4h:consensus') == 'refuted' and j.state('btc|4h:consensus') == 'refuted'
    assert j.state('btc|1m:wick') == 'no_evidence' and len(j.d['holdout_history']) == 2
    assert j.state('btc_stop1|short:all') == 'no_evidence'
    assert [(t['scope'], t['pair']) for t in j.d['tracking']] == [('btc', '4h:flow'), ('btc', '4h:bollinger')]
    assert len(pe.RESEARCH_LESSONS) == 18 and any(e['kind'] == 'universe' for e in j.d['entries'])
    assert j.n_trials(['btc|4h:flow|taker']) == 146 and j.n_trials(['btc|4h:keltner|maker']) == 147
    j.record('lab', ['btc|4h:keltner|maker'], title='t')
    j2 = pe.ResearchJournal.load()
    assert j2.n_trials() == 147 and j2.d['entries'][-1]['title'] == 't'
    text = j2.text()
    assert 'L7' in text and 'P1' in text and '반증' in text
    assert os.path.exists(j2.export_md())
    with open(j2.path, 'w', encoding='utf-8') as f:
        f.write('{broken')
    j3 = pe.ResearchJournal.load()                                            # 손상 → 보관 후 기본 기록으로 다시 시작
    assert j3.n_trials() == 146 and 'journal' in pe.HEALTH.items


def test_journal_blocks_refuted_and_repeated_tests(pe):
    j = pe.ResearchJournal.load()
    j.set_status('btc|4h:flow', 'refuted', '테스트')
    block, warn = j.check('btc', [('4h', 'flow'), ('5m', 'tsmom')])
    assert len(block) == 1 and '반증' in block[0] and any('근거 없음' in w for w in warn)
    block, warn = j.check('btc', [('4h', 'flow')], retest='새 데이터 1년 추가')
    assert not block and warn                                                  # 사유가 있으면 경고만 (일지에 남는다)
    j.set_status('btc_presample|4h:keltner', 'preregistered', '테스트용 재등록')
    assert not j.check('btc_presample', [('4h', 'keltner')], once=True)[0]     # 등록 대기 → 실행 가능
    j.set_status('btc_presample|4h:consensus', 'preregistered', '테스트용 재등록')
    pe.research_apply_presample(j, [dict(pair='4h:keltner', n=40, mean_r=-0.1, lo=-0.5, verdict='반증 — x'),
                                    dict(pair='4h:consensus', n=0, mean_r=float('nan'), lo=float('nan'),
                                         verdict='판정 불가 (거래 < 10)')])
    assert j.state('btc_presample|4h:keltner') == 'refuted' and j.state('btc|4h:keltner') == 'refuted'
    assert j.state('btc_presample|4h:consensus') == 'preregistered'          # 거래 0건은 시험이 아니다
    assert j.check('btc_presample', [('4h', 'keltner')], once=True)[0]         # 같은 구간 재시험 금지
    j.save()
    assert pe.main(['--lab', '--only', '4h:flow']) == 2                        # 네트워크 전에 거절
    assert pe.main(['--lab', '--reveal-holdout']) == 2                         # L9
    assert pe.main(['--lab', '--presample', '--universe']) == 2


def test_consume_holdout_moves_anchor_forward_only(pe):
    j = pe.ResearchJournal.load()
    from conftest import Clock
    pe.utcnow = Clock('2026-11-15 12:00')
    j.consume_holdout(['4h:flow'], {'4h:flow': '반증 — x'})
    assert str(j.anchor.date()) == '2026-11-15' and len(j.d['holdout_history']) == 3


def test_fixed_anchor_makes_holdout_independent_of_data_end(pe):
    base = _trend_1m(1300, 0.0)
    a = pe.lab_run(base, tfs=('4h',), families=['donchian'], holdout_start='2022-06-01')
    b = pe.lab_run(base.iloc[:-30 * 1440], tfs=('4h',), families=['donchian'], holdout_start='2022-06-01')
    assert a['holdout_start'] == b['holdout_start']
    assert a['rows'][0]['oos']['n'] == b['rows'][0]['oos']['n']               # 데이터가 늘어도 표본외는 그대로


def test_planned_keys_match_trial_counting(pe):
    fams = pe.lab_available_families(None)
    keys = pe.lab_planned_keys('btc', pe.LAB_TFS, fams, 'taker')
    assert len(keys) == pe.lab_trial_count(pe.LAB_TFS, fams) and all(k.startswith('btc|') for k in keys)
    uk = pe.lab_planned_keys('universe', pe.LAB_UNIVERSE_TFS, pe.lab_available_families(None, True), 'taker', universe=True)
    assert len(uk) == pe.lab_universe_trial_count(pe.LAB_UNIVERSE_TFS, pe.lab_available_families(None, True))
    assert 'universe|1h:analog|taker' not in uk


def test_consensus_family_is_causal_and_needs_all_four_votes(pe):
    f = _frame_4h(4000)
    full = pe._lab_target('consensus', dict(k=3.0), pe._lab_indicators(f))
    part = pe._lab_target('consensus', dict(k=3.0), pe._lab_indicators(f.iloc[:3000]))
    assert np.array_equal(full[:3000], part) and set(np.unique(full)) <= {-1, 0, 1} and np.abs(full).sum() > 0
    assert pe.LAB_FAMILY_TFS['consensus'] == ('4h',) and len(pe.LAB_GRIDS['consensus']) == 1


def test_presample_uses_only_unseen_window_with_spot_history(pe):
    base = _trend_1m(1500, 0.0000004, seed=5)
    base.index = pd.date_range('2018-01-01', periods=len(base), freq='1min')
    base['era'] = np.where(base.index < pd.Timestamp('2020-01-01'), 0.0, 1.0)            # 2018~2019 스팟 이력
    res = pe.lab_presample(base, '4h:donchian,4h:consensus', seen_from='2021-06-01')
    v = {x['pair']: x for x in res['presample']}
    assert v['4h:donchian']['n'] > 0 and v['4h:donchian']['oos_start'].startswith('2020-01-01')
    r = next(x for x in res['rows'] if x['family'] == 'donchian')
    assert (r['oos_t'] < np.datetime64('2021-06-01')).all()                  # 처음 보는 구간 거래만
    assert '처음 보는 BTC 구간 검증' in res['report'] and '2.50%' in res['report']   # 가설 2개 → 단측 2.5%
    fut = pe.lab_presample(base[base['era'] == 1.0], '4h:donchian', seen_from='2021-06-01')
    assert fut['presample'][0]['n'] == 0                                       # 스팟 이력이 없으면 처음 보는 구간도 없다


# ── 최종 검증 (사전등록 P2) ───────────────────────────────────────────
def test_final_verdict_rule(pe):
    v = pe.lab_final_verdict
    m = lambda n, mean, lo: dict(n=n, mean_r=mean, ci_lo=lo, ci_hi=lo + 1)
    assert v(m(0, float('nan'), float('nan')), m(0, float('nan'), float('nan'))).startswith('판정 불가')
    assert v(m(15, 0.3, -0.5), m(200, -0.02, -0.2)).startswith('반증 —')          # 묶음 평균 ≤ 0
    assert v(m(12, -0.1, -0.9), m(200, 0.2, 0.05)).startswith('반증 —')            # BTC 10건 이상 평균 ≤ 0
    assert v(m(8, -0.1, -0.9), m(200, 0.2, 0.05)).startswith('반증 안 됨')         # BTC 10건 미만은 묶음 하한만으론 확인 안 됨
    assert v(m(15, 0.3, -0.5), m(200, 0.2, 0.05)).startswith('확인')
    assert v(m(15, 0.3, -0.5), m(200, 0.2, -0.05)).startswith('반증 안 됨')
    assert v(m(15, 0.3, 0.1), None).startswith('확인')                             # 알트 없으면 BTC 단독 규칙


def test_final_test_reads_only_holdout_and_both_scopes(pe):
    base = _trend_1m(1500, 0.0000004, seed=6)
    base.index = pd.date_range('2018-01-01', periods=len(base), freq='1min')
    coins = {'BTCUSDT': pe.lab_btc_frames(base, ('4h',))}
    for k, sym in enumerate(('ETHUSDT', 'SOLUSDT', 'XRPUSDT')):
        coins[sym] = {'4h': _frame_4h(len(coins['BTCUSDT']['4h']), seed=k, start='2018-01-01')}
    hs = pd.Timestamp('2021-06-01')
    res = pe.lab_final_test(base, coins, '4h:tsmom', hs)
    assert res['pair'] == '4h:tsmom' and res['uni'] is not None and res['b']['n'] > 0 and res['u']['n'] > 0
    rb = res['btc']['rows'][0]
    assert (rb['oos_t'] < np.datetime64(hs)).all() and res['btc']['revealed'] and res['uni']['revealed']
    assert '최종 검증 (사전등록 P2)' in res['report'] and '▶ 판정' in res['report'] and res['verdict']
    import pytest
    with pytest.raises(ValueError):
        pe.lab_final_test(base, coins, '4h:tsmom,4h:ema', hs)


def test_journal_sync_adds_new_preregistration_to_old_journals(pe):
    j = pe.ResearchJournal.load()
    j.d['prereg'] = [p for p in j.d['prereg'] if p['id'] != 'P2']
    j.d['status'].pop('final|4h:keltner')
    j.d['entries'] = [e for e in j.d['entries'] if not e['title'].startswith('P1 결과')]
    j.save()
    j2 = pe.ResearchJournal.load()
    assert 'P2' in [p['id'] for p in j2.d['prereg']] and j2.state('final|4h:keltner') == 'refuted'   # 코드의 기록대로
    assert any(e['title'].startswith('P1 결과') and e.get('synced_from_code') for e in j2.d['entries'])
    n = len(j2.d['entries'])
    assert len(pe.ResearchJournal.load().d['entries']) == n                   # 두 번 덧붙이지 않는다


def test_cli_final_guards(pe):
    assert pe.main(['--lab', '--final', '4h:flow']) == 2                      # P2 에 등록되지 않은 가설
    assert pe.main(['--lab', '--final', '4h:keltner', '--universe']) == 2
    assert pe.main(['--lab', '--final']) == 2
    j = pe.ResearchJournal.load()
    j.set_status('final|4h:keltner', 'refuted', '테스트')
    j.save()
    assert pe.main(['--lab', '--final', '4h:keltner']) == 2                   # 이미 판정됨 → 다시 열지 않음


# ── 시간대 쏠림 · 알트 스팟 이력 · 처음 보는 알트 구간 (P3) · 앞으로의 검증 ─────────────
def _frame_1h_tod(n=24 * 1300, drift_hours=(8, 12), drift=0.0015, seed=0, start='2019-09-09'):
    g = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq='1h')
    r = g.normal(0, 0.004, n) + np.where((idx.hour >= drift_hours[0]) & (idx.hour < drift_hours[1]), drift, 0.0)
    c = 30000 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(dict(open=o, high=np.maximum(o, c) * 1.001, low=np.minimum(o, c) * 0.999, close=c, volume=1.0,
                             taker_buy_base=0.5, trades=1.0, era=1.0), index=idx)


def test_tod_family_holds_only_in_clock_window_and_finds_planted_drift(pe):
    f = _frame_1h_tod()
    ind = pe._lab_indicators(f)
    t = pe._lab_target('tod', dict(h=8, H=4, d=1, k=3.0), ind)
    nxt = f.index.hour.values[1:]
    assert set(np.unique(t)) <= {0, 1} and (t[:-1][(nxt >= 8) & (nxt < 12)] == 1).all()
    assert (t[:-1][(nxt < 8) | (nxt >= 12)] == 0).all()                      # 다음 봉 시각만 본다 (달력 정보)
    res = pe.lab_run(None, tf_frames={'1h': f}, families=['tod'], tfs=('1h',))
    m = res['rows'][0]['oos']
    assert m['n'] >= 200 and m['mean_r'] > 0 and m['ci_lo'] > 0 and res['rows'][0]['last_params']['h'] == 8
    flat = _frame_1h_tod(drift=0.0, seed=4)
    m0 = pe.lab_run(None, tf_frames={'1h': flat}, families=['tod'], tfs=('1h',))['rows'][0]['oos']
    assert not (m0['n'] >= 50 and m0['ci_lo'] > 0 and m0['dsr'] >= 0.9)


def test_spot_vision_fetch_skips_unlisted_months_and_caches(pe):
    import io
    import zipfile

    def zip_rows(year, month):
        t0 = int(pd.Timestamp(f'{year}-{month:02d}-01').value // 10 ** 6)
        lines = [f'{t0 + k * 4 * 3600_000},1,2,0.5,{1 + k},10,0,0,7,6,0,0' for k in range(180)]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('x.csv', '\n'.join(lines))
        return buf.getvalue()

    class FakeHttp:
        def __init__(self):
            self.urls = []

        def get(self, url, timeout=None):
            pe.PublicHttp.check_allowed(url)
            self.urls.append(url)
            ym = url.rsplit('-4h-', 1)[1][:7]
            if ym < '2018-03':
                raise FileNotFoundError('HTTP 404')
            return zip_rows(int(ym[:4]), int(ym[5:7]))

    http = FakeHttp()
    df = pe.fetch_spot_klines_vision(http, 'ADAUSDT', '4h', start='2018-01', end='2018-04')
    assert len(http.urls) == 4 and '/data/spot/monthly/klines/ADAUSDT/4h/' in http.urls[0]
    assert str(df.index[0].date()) == '2018-03-01' and (df['era'] == pe.ERA_SPOT).all() and df['trades'].iloc[0] == 7.0
    again = pe.fetch_spot_klines_vision(http, 'ADAUSDT', '4h', start='2018-01', end='2018-04')
    assert len(http.urls) == 4 and len(again) == len(df)                      # 캐시에서


def test_alt_presample_judges_only_unseen_window_pooled(pe):
    coins = {s: {'4h': _frame_4h(7800, seed=k, start='2017-09-01')} for k, s in enumerate(('ETHUSDT', 'LTCUSDT', 'ADAUSDT'))}
    coins['SOLUSDT'] = {}                                                       # 스팟 이력 없음
    res = pe.lab_alt_presample(coins, '4h:tsmom', seen_from='2021-11-27')
    v = res['verdicts'][0]
    assert v['n'] >= 30 and v['verdict'].startswith('확인') and v['tot'] == 3 and 'SOLUSDT' in res['skipped']
    one = pe.lab_run(None, tf_frames=coins['ETHUSDT'], only='4h:tsmom', holdout_start='2021-11-27')
    assert (one['rows'][0]['oos_t'] < np.datetime64('2021-11-27')).all()
    flat = {s: {'4h': _frame_4h(7800, motif=0.0, noise=0.008, seed=30 + k, start='2017-09-01')}
            for k, s in enumerate(('ETHUSDT', 'LTCUSDT', 'ADAUSDT'))}
    v0 = pe.lab_alt_presample(flat, '4h:tsmom', seen_from='2021-11-27')['verdicts'][0]
    assert not v0['verdict'].startswith('확인')
    j = pe.ResearchJournal.load()
    pe.research_apply_alt_presample(j, [dict(v0, pair='4h:flow')])
    assert j.state('alt_presample|4h:flow') != 'preregistered' or v0['n'] == 0


def test_alt_presample_verdict_rule(pe):
    f = pe.lab_alt_presample_verdict
    assert f(20, 0.5, 0.1, 3, 3).startswith('판정 불가')
    assert f(100, -0.01, -0.3, 1, 4).startswith('반증 —')
    assert f(100, 0.2, 0.05, 3, 4).startswith('확인')
    assert f(100, 0.2, 0.05, 2, 4).startswith('반증 안 됨')
    assert f(100, 0.2, -0.05, 4, 4).startswith('반증 안 됨')


def test_prospective_scores_only_after_freeze_and_stops_when_broken(pe):
    base = _trend_1m(1300, 0.0000004, seed=8)
    since = str((base.index[-1] - pd.Timedelta(days=240)).date())
    res = pe.lab_prospective(base, [dict(pair='4h:tsmom', scope='btc', since=since)], kill_n=5)
    r = res['rows'][0]
    assert r['n'] > 0 and r['since'] == since and '앞으로의 검증' in res['report']
    assert r['state'] in ('살아 있음 (계속 추적)', '중단 — 앞으로의 데이터에서 무너짐')
    flat = _trend_1m(1300, 0.0, seed=9)
    r0 = pe.lab_prospective(flat, [dict(pair='4h:tsmom', scope='btc', since=since)], kill_n=10 ** 6)['rows'][0]
    assert r0['state'] == '추적 중'                                             # 거래가 쌓이기 전에는 결론 없음


def test_cli_alt_presample_and_prospective_guards(pe):
    assert pe.main(['--lab', '--alt-presample', '--prospective']) == 2
    assert pe.main(['--lab', '--alt-presample', '--universe']) == 2
    assert pe.main(['--lab', '--prospective', '--final', '4h:flow']) == 2


# ── 하루 1% 잣대 · 지정가 꼬리 잡기 ─────────────────────────────────────
def test_sharpe_requirement_for_one_percent_a_day(pe):
    assert abs(pe.LAB_SHARPE_FOR_1PCT - 2.695) < 0.01 and abs(pe.LAB_SHARPE_FOR_1PCT_HALF - 3.112) < 0.01
    days = pd.date_range('2024-01-01', periods=400, freq='D').values
    g = np.random.default_rng(2)
    R = g.normal(0.1, 1.0, 400)
    sh = pe.lab_daily_sharpe(R, days, days[0], days[-1])
    assert abs(sh - R.mean() / R.std(ddof=1) * np.sqrt(365)) < 0.05
    res = pe.lab_run(_trend_1m(1300, 0.0), tfs=('4h',), families=['donchian'])
    assert '하루 1% 복리에 필요한 연환산 샤프 ≈ 2.7' in res['report'] and 'sharpe' in res['rows'][0]['oos']


def _wick_arrays(n=40, level=98.5):
    o = np.full(n, level)                                              # 손절 97.02 와 익절 98.98 사이
    c = o.copy()
    h = o + 0.1
    lo = o - 0.1
    return o, h, lo, c


def test_wick_fill_rules_are_conservative(pe):
    args = (np.array([0]), np.array([30]), np.array([100.0]), np.array([0.01]), 2.0, 1.0, 1.0, 1, 30,
            0.0002, 0.0007, 0.0001, 0.25)
    o, h, lo, c = _wick_arrays(level=100.0)
    lo[5] = 98.0                                                       # 지정가 98 에 닿기만 하고 관통 안 함
    assert len(pe.lab_wick_sim(o, h, lo, c, *args)[0]) == 0
    o, h, lo, c = _wick_arrays()
    lo[5], h[8] = 97.9, 99.2                                           # 관통 체결 → 익절 98.98 (지정가)
    ei, xi, rr = pe.lab_wick_sim(o, h, lo, c, *args)
    assert list(ei) == [5] and list(xi) == [8] and abs(rr[0] - (98.98 / 98 - 1 - 0.0004) / 0.01) < 1e-9
    o, h, lo, c = _wick_arrays()
    lo[5] = 96.5                                                       # 진입한 그 1분에 손절가까지 → 손절 (최악 가정)
    ei, xi, rr = pe.lab_wick_sim(o, h, lo, c, *args)
    px = 97.02 - 0.25 * (97.02 - 96.5)
    assert list(xi) == [5] and abs(rr[0] - (px / 98 - 1 - 0.0009) / 0.01) < 1e-9
    o, h, lo, c = _wick_arrays()
    lo[5], h[5] = 97.9, 99.5                                           # 같은 1분의 익절은 인정 안 함 → 시간 만료
    ei, xi, rr = pe.lab_wick_sim(o, h, lo, c, *args)
    assert list(xi) == [34] and abs(rr[0] - (98.5 / 98 - 1 - 0.0009) / 0.01) < 1e-9


def test_wick_sigma_uses_only_past_days(pe):
    idx = pd.date_range('2024-01-01', periods=60 * 1440, freq='1min')
    g = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(g.normal(0, 0.0005, len(idx))))
    b = pd.DataFrame(dict(open=c, high=c, low=c, close=c), index=idx)
    starts = pd.DatetimeIndex(['2024-02-10 00:00', '2024-02-10 12:00', '2024-02-11 00:00'])
    s0 = pe._lab_wick_sigma(b, starts)
    b2 = b.copy()
    b2.loc['2024-02-10', 'close'] *= 1.5                                # 2/10 데이터를 바꿔도
    s1 = pe._lab_wick_sigma(b2, starts)
    assert np.allclose(s0[:2], s1[:2]) and not np.isclose(s0[2], s1[2])  # 그날 시작한 주문의 σ 는 그대로


def _wick_base(planted, days=1500, seed=1):
    g = np.random.default_rng(seed)
    n = days * 1440
    ret = g.normal(0, 0.0006, n)
    if planted:
        s0 = 1000
        while s0 + 60 < n:
            ret[s0:s0 + 5] -= 0.03 / 5                                   # 5분 급락 (강제청산 꼬리)
            ret[s0 + 5:s0 + 45] += 0.03 / 40                             # 40분 되돌림
            s0 += 2880 + int(g.integers(0, 1440))
    c = 30000 * np.exp(np.cumsum(ret))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(dict(open=o, high=np.maximum(o, c) * 1.0002, low=np.minimum(o, c) * 0.9998, close=c, volume=1.0,
                             taker_buy_base=0.5, trades=1.0, era=1.0),
                        index=pd.date_range('2020-01-01', periods=n, freq='1min'))


def test_wick_finds_planted_liquidation_wicks_and_rejects_random_walk(pe):
    good = pe.lab_run_wick(_wick_base(True), n_trials_declared=109, holdout_start='2099-01-01')
    m = good['rows'][0]['oos']
    assert m['n'] >= 50 and m['ci_lo'] > 0 and m['win'] > 0.6 and m['sharpe'] > 1.5 and '통과' in good['report']
    bad = pe.lab_run_wick(_wick_base(False, seed=2), n_trials_declared=109, holdout_start='2099-01-01')
    m0 = bad['rows'][0]['oos']
    assert not (m0['n'] >= 100 and m0['ci_lo'] > 0 and m0['dsr'] >= 0.9) and '미통과' in bad['report']


def test_cli_wick_guards(pe):
    assert pe.main(['--lab', '--wick', '--universe']) == 2
    assert pe.main(['--lab', '--wick', '--prospective']) == 2


def test_far_future_holdout_does_not_dilute_rates(pe):
    coins = {s_: {'4h': _frame_4h(7800, seed=k)} for k, s_ in enumerate(('BTCUSDT', 'ETHUSDT', 'SOLUSDT'))}
    a = pe.lab_run_universe(coins, tfs=('4h',), families=['tsmom'], holdout_start='2099-01-01')['rows'][0]['oos']
    b = pe.lab_run_universe(coins, tfs=('4h',), families=['tsmom'],
                            holdout_start=str(coins['BTCUSDT']['4h'].index[-1] + pd.Timedelta(hours=4)))['rows'][0]['oos']
    assert a['n'] == b['n'] and abs(a['n_year'] - b['n_year']) < 1e-6 and abs(a['g_day'] - b['g_day']) < 1e-9


# ── BTC 1순위 · ETH 2순위: 다른 국면 검증 (사전등록 P4) ─────────────────
def test_majors_are_the_default_and_spot_perp_merge(pe):
    assert pe.LAB_MAJOR_SYMBOLS == ('ETHUSDT',)
    spot = _frame_4h(100, start='2019-01-01')
    perp = _frame_4h(100, seed=3, start='2019-01-10')
    m = pe.merge_spot_perp(spot, perp)
    assert m.index.is_monotonic_increasing and not m.index.has_duplicates
    assert (m.loc[m.index >= perp.index[0], 'close'].values == perp['close'].values).all()   # 겹치면 선물을 쓴다
    assert pe.merge_spot_perp(None, perp) is perp and pe.merge_spot_perp(spot, None) is spot


def test_regime_verdict_rule_puts_btc_first(pe):
    v = pe.lab_regime_verdict
    w = lambda n, mean, lo: dict(n=n, mean_r=mean, lo=lo)
    assert v(w(15, 0.5, 0.1), w(100, 0.5, 0.2)).startswith('판정 불가')
    assert v(w(80, -0.02, -0.3), w(100, 0.5, 0.2)).startswith('반증 —')          # ETH 가 좋아도 BTC 가 음수면 반증
    assert v(w(80, 0.3, 0.05), w(100, -0.1, -0.4)).startswith('반증 안 됨')
    assert v(w(80, 0.3, 0.05), w(100, 0.1, -0.1)).startswith('확인')
    assert v(w(80, 0.3, -0.05), None).startswith('반증 안 됨')


def test_regime_test_scores_only_the_later_window_by_year(pe):
    base = _trend_1m(1500, 0.0000004, seed=6)
    base.index = pd.date_range('2018-01-01', periods=len(base), freq='1min')
    eth = {'4h': _frame_4h(int(1500 * 6), seed=2, start='2018-01-01')}
    res = pe.lab_regime_test(base, eth, '4h:tsmom', start='2021-01-01', end='2022-02-01')
    assert res['b']['n'] > 0 and res['e']['n'] > 0 and set(res['b']['years']) <= {2021, 2022}
    assert '다른 국면 검증 (사전등록 P4)' in res['report'] and '해마다' in res['report'] and res['verdict']
    import pytest
    with pytest.raises(ValueError):
        pe.lab_regime_test(base, eth, '4h:tsmom,4h:ema')


def test_prospective_tracks_eth_with_its_own_frames(pe):
    base = _trend_1m(1300, 0.0000004, seed=8)
    eth = {'4h': _frame_4h(1300 * 6, seed=5, start=str(base.index[0].date()))}
    since = str((base.index[-1] - pd.Timedelta(days=240)).date())
    res = pe.lab_prospective(base, [dict(pair='4h:tsmom', scope='btc', since=since),
                                    dict(pair='4h:tsmom', scope='eth', since=since)], eth_frames=eth, kill_n=5)
    assert [r['scope'] for r in res['rows']] == ['btc', 'eth'] and res['rows'][1]['n'] > 0
    assert len(pe.lab_prospective(base, [dict(pair='4h:tsmom', scope='eth', since=since)])['rows']) == 0   # ETH 봉 없으면 건너뜀


def test_cli_regime_guards(pe):
    assert pe.main(['--lab', '--regime', '4h:flow']) == 2                     # P4 에 등록되지 않음
    assert pe.main(['--lab', '--regime', '4h:consensus', '--universe']) == 2
    assert pe.main(['--lab', '--regime']) == 2
    j = pe.ResearchJournal.load()
    j.set_status('regime|4h:consensus', 'refuted', '테스트')
    j.save()
    assert pe.main(['--lab', '--regime', '4h:consensus']) == 2                # 이미 판정됨


# ── 지금 신호 (종이 매매·연구 추적) ────────────────────────────────────
def test_live_state_matches_the_simulator(pe):
    n = 50
    o = np.full(n, 100.0)
    c = o.copy()
    h = o + 0.5
    lo = o - 0.5
    atr = np.full(n, 0.01)
    tgt = np.zeros(n, dtype=np.int64)
    tgt[8:] = 1
    st = pe.lab_live_state(o, h, lo, c, atr, tgt, 2.0, 0)
    assert st['pos'] == 1 and st['t_in'] == 9 and abs(st['stop'] - 98.0) < 1e-9 and st['want_next'] == 1   # 보유 중
    lo2 = lo.copy()
    lo2[10] = 90.0
    st2 = pe.lab_live_state(o, h, lo2, c, atr, tgt, 2.0, 0)
    assert st2['pos'] == 0 and st2['blocked'] == 1                                # 손절 후 같은 방향 막힘 (lab_sim 과 같음)
    ei, xi, sd, rr = pe.lab_sim(o, h, lo2, c, atr, tgt, 2.0, 0, 0.0014, 0.0)
    assert len(rr) == 1 and xi[0] == 10
    g = np.random.default_rng(4)                                                  # 무작위 경로에서도 거래 수가 같다
    cc = 100 * np.exp(np.cumsum(g.normal(0, 0.01, 2000)))
    oo = np.r_[cc[0], cc[:-1]]
    hh, ll = np.maximum(oo, cc) * 1.003, np.minimum(oo, cc) * 0.997
    tt = np.sign(np.sin(np.arange(2000) / 15.0)).astype(np.int64)
    aa = np.full(2000, 0.01)
    ei2, _, _, _ = pe.lab_sim(oo, hh, ll, cc, aa, tt, 1.5, 0, 0.0, 0.0)
    st3 = pe.lab_live_state(oo, hh, ll, cc, aa, tt, 1.5, 0)
    assert st3['entries'] == len(ei2) + (1 if st3['pos'] != 0 else 0) and len(ei2) > 20
    assert st3['pos'] != 0 or st3['t_in'] == ei2[-1]                              # 마지막 진입 봉도 같다


def test_live_signal_report_for_small_seed(pe):
    base = _trend_1m(1300, 0.0000004, seed=8)
    res = pe.lab_live_signal(base, '4h:tsmom,4h:donchian', seed=70.0)
    assert '지금 신호' in res['report'] and len(res['rows']) == 2
    assert all(r['state'] in ('rest', 'flat', 'position') for r in res['rows'])
    if any(r['state'] != 'rest' for r in res['rows']):
        assert '최소주문' in res['report'] or '격리' in res['report']


def test_cli_signal_guards(pe):
    assert pe.main(['--lab', '--signal', '--universe']) == 2
    assert pe.main(['--lab', '--signal', '--wick']) == 2


# ── 가격 % 고정 손절 + R 배수 익절 (짧은 시간봉, 레버리지 = 계좌 위험) ─────────────
def _flat(n=40, level=100.0):
    o = np.full(n, level)
    return o, o + 0.1, o - 0.1, o.copy()


def test_fixed_stop_and_take_profit_rules(pe):
    atr = np.full(40, 0.002)
    tgt = np.zeros(40, dtype=np.int64)
    tgt[8:] = 1
    args = (2.0, 0, 0.0007, 0.0007, 0.0007, 0.0, -1.0, 0.01, 2.0)       # 가격 1% 손절, 2R 익절
    o, h, lo, c = _flat()
    h[12] = 102.5                                                         # 진입 100 → 익절 102
    ei, xi, sd, rr = pe.lab_sim_x(o, h, lo, c, atr, tgt, *args)
    assert list(ei) == [9] and list(xi) == [12] and abs(rr[0] - (0.02 - 0.0014) / 0.01) < 1e-9
    assert len(rr) == 1                                                    # 익절 후 같은 신호로 바로 재진입 안 함
    o, h, lo, c = _flat()
    lo[11] = 98.9                                                         # 손절 99
    ei, xi, sd, rr = pe.lab_sim_x(o, h, lo, c, atr, tgt, *args)
    assert list(xi) == [11] and abs(rr[0] - (-0.01 - 0.0014) / 0.01) < 1e-9
    o, h, lo, c = _flat()
    lo[11], h[11] = 98.9, 102.5                                           # 같은 봉에 둘 다 → 손절 (보수)
    assert pe.lab_sim_x(o, h, lo, c, atr, tgt, *args)[3][0] < 0
    o, h, lo, c = _flat()                                                 # 익절 없이(0) 고정 손절만: 신호 끝까지 보유
    tgt2 = tgt.copy()
    tgt2[20:] = 0
    ei, xi, sd, rr = pe.lab_sim_x(o, h, lo, c, atr, tgt2, 2.0, 0, 0.0007, 0.0007, 0.0007, 0.0, -1.0, 0.01, 0.0)
    assert list(xi) == [21] and abs(rr[0] - (0.0 - 0.0014) / 0.01) < 1e-9


def test_fixed_grid_drops_atr_multiple_and_adds_take_profit(pe):
    g = pe.lab_fixed_grid('tsmom')
    assert len(g) == 7 * 3 and {p['tp'] for p in g} == {0.0, 2.0, 3.0} and all(p['k'] == 0.0 for p in g)
    assert len(pe.lab_fixed_grid('consensus', (0.0, 2.0))) == 2


def test_live_state_mirrors_fixed_stop_and_take_profit(pe):
    g = np.random.default_rng(6)
    cc = 100 * np.exp(np.cumsum(g.normal(0, 0.004, 3000)))
    oo = np.r_[cc[0], cc[:-1]]
    hh, ll = np.maximum(oo, cc) * 1.002, np.minimum(oo, cc) * 0.998
    tt = np.sign(np.sin(np.arange(3000) / 25.0)).astype(np.int64)
    aa = np.full(3000, 0.004)
    ei, _, _, _ = pe.lab_sim_x(oo, hh, ll, cc, aa, tt, 2.0, 0, 0.0007, 0.0007, 0.0007, 0.0, -1.0, 0.01, 2.0)
    st = pe.lab_live_state(oo, hh, ll, cc, aa, tt, 2.0, 0, fixed_stop=0.01, tp_r=2.0)
    assert st['entries'] == len(ei) + (1 if st['pos'] != 0 else 0) and len(ei) > 20


def test_risk_table_shows_leverage_amplifies_both_ways(pe):
    rows, streak = pe.lab_risk_table([1.0, -1.0, -1.0, -1.0, 2.0, -1.0], years=1.0)
    assert streak == 3 and [r[0] for r in rows] == [0.01, 0.02, 0.03]
    assert rows[2][3] > rows[1][3] > rows[0][3]                            # 위험 클수록 낙폭도 크다
    neg, _ = pe.lab_risk_table([-0.2] * 50, years=1.0)
    assert neg[2][1] < neg[1][1] < neg[0][1] < 1.0                         # 기대값이 음수면 레버리지는 손실만 키운다


def test_fixed_stop_lab_run_reports_risk_table(pe):
    base = _trend_1m(1300, 0.0000004, seed=3)
    res = pe.lab_run(base, tfs=('1h',), families=['tsmom', 'donchian'], fixed_stop=0.01)
    assert res['fixed_stop'] == 0.01 and '가격 1.0% 고정' in res['report'] and '1R 의 14%' in res['report']
    assert all('tp' in (r['last_params'] or {'tp': 0}) for r in res['rows'])
    if any(r['oos']['n'] >= 30 for r in res['rows']):
        assert '거래당 계좌 위험별 표본외 결과' in res['report']
    keys = pe.lab_planned_keys('btc', ('1h',), ['tsmom', 'donchian'], 'taker|stop1')
    assert keys == ['btc|1h:tsmom|taker|stop1', 'btc|1h:donchian|taker|stop1']


def test_cli_stop_pct_guards(pe):
    assert pe.main(['--lab', '--stop-pct', '0']) == 2
    assert pe.main(['--lab', '--stop-pct', '1', '--universe']) == 2
    assert pe.main(['--lab', '--stop-pct', '1', '--tp', 'x']) == 2
    assert pe.main(['--lab', '--stop-pct', '1', '--tfs', '1m']) == 2


# ── 실제 계정 수수료로 다시 돌리기 (--fees) ────────────────────────────
def test_fee_override_rebuilds_costs_and_tags_journal_keys(pe):
    try:
        assert pe.lab_fee_tag() == ''
        pe.lab_set_fees(0.00045, 0.00018)
        assert abs(pe.LAB_COST_MODES['taker'][1] - (0.00045 + pe.SLIPPAGE_T)) < 1e-12
        assert abs(pe.LAB_COST_MODES['maker_entry'][1] - 0.00018) < 1e-12
        assert pe.lab_fee_tag() == '|fee4.5/1.8/2bp'
        res = pe.lab_run(_trend_1m(1300, 0.0), tfs=('4h',), families=['donchian'])
        assert '진입 0.065%' in res['report']                                   # 보고서에 바뀐 수수료가 보인다
    finally:
        pe.lab_set_fees(*pe.LAB_DEFAULT_FEES[:2])
    assert pe.lab_fee_tag() == '' and abs(pe.LAB_COST_MODES['taker'][1] - 0.0007) < 1e-12


def test_cli_fees_guards(pe):
    assert pe.main(['--lab', '--fees', 'x']) == 2
    assert pe.main(['--lab', '--fees', '0.045']) == 2
    assert pe.main(['--lab', '--fees', '0.045,0.018', '--universe']) == 2
    assert pe.lab_fee_tag() == ''                                                # 거절된 실행은 수수료를 바꾸지 않는다


# ── 정답에서 단서 찾기 (--oracle): 삼중 장벽 정답 + 로지스틱 회귀 ────────────────
def test_barrier_labels_rules(pe):
    sl, tp, hold = 0.01, 0.02, 3
    o = np.array([100, 100, 100, 100, 100, 100, 100, 100], dtype=float)
    h = np.array([100, 102.5, 100, 100, 100, 100, 100, 100], dtype=float)     # 봉1: 롱 익절(+2%)
    l = np.array([100, 99.5, 100, 100, 100, 100, 100, 100], dtype=float)
    c = np.array([100, 101, 100.5, 100.5, 100.5, 100.5, 100.5, 100.5], dtype=float)
    rl, xl, rs, xs = pe.lab_barrier_labels(o, h, l, c, sl, tp, hold, 0.0)
    assert abs(rl[0] - 2.0) < 1e-9 and xl[0] == 1                             # 봉0 마감 결정 → 봉1 시가 진입 → 익절
    assert abs(rs[0] - (-1.0)) < 1e-9 and xs[0] == 1                          # 숏은 같은 봉에서 손절(102.5 ≥ 101)
    assert abs(rl[1] - 0.5) < 1e-9 and xl[1] == 4                             # 아무것도 안 닿으면 hold 봉 종가 청산
    assert np.isnan(rl[-1]) and np.isnan(rl[len(c) - hold - 1]) and xl[-1] == -1  # 결과를 모르는 끝부분은 정답 없음
    h2 = h.copy()
    l2 = l.copy()
    h2[1], l2[1] = 102.5, 98.5                                                # 같은 봉에서 익절·손절 둘 다 → 손절로 본다
    rl2, _, _, _ = pe.lab_barrier_labels(o, h2, l2, c, sl, tp, hold, 0.0)
    assert abs(rl2[0] - (-1.0)) < 1e-9
    o3, l3 = o.copy(), l.copy()
    o3[2], l3[2] = 97.0, 96.0                                                 # 갭으로 손절선 아래에서 시작 → 시가에 청산
    rl3, _, _, _ = pe.lab_barrier_labels(o3, np.full(8, 100.0), l3, np.full(8, 100.0), sl, tp, hold, 0.0)
    assert abs(rl3[0] - (-3.0)) < 1e-9
    rl4, _, _, _ = pe.lab_barrier_labels(o, h, l, c, sl, tp, hold, 0.0014)
    assert abs(rl4[0] - (2.0 - 0.14)) < 1e-9                                  # 왕복 비용은 R 에서 뺀다


def test_logit_learns_the_planted_sign_and_ranks(pe):
    g = np.random.default_rng(0)
    X = g.normal(0, 1, (4000, 3))
    y = (X[:, 0] - 0.5 * X[:, 1] + g.normal(0, 1, 4000) > 0).astype(float)
    w = pe._logit_fit(X, y)
    assert w[1] > 0.8 and w[2] < -0.3 and abs(w[3]) < 0.15
    p = pe._logit_predict(w, np.array([[-2.0, 0, 0], [0, 0, 0], [2.0, 0, 0]]))
    assert p[0] < 0.2 < p[1] < 0.8 < p[2]


def _oracle_frame(days, planted, seed=5):
    """1시간봉. planted > 0 이면 관측 가능한 테이커 체결강도(느린 숨은 상태)가 이후 방향을 미리 알려 준다."""
    g = np.random.default_rng(seed)
    n = days * 24
    st = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc = 0.97 * acc + g.normal(0, 0.25)
        st[i] = acc
    r = g.normal(0, 0.004, n) + planted * np.r_[0.0, np.tanh(st[:-1])]
    c = 30000 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) * (1 + np.abs(g.normal(0, 0.001, n)))
    lo = np.minimum(o, c) * (1 - np.abs(g.normal(0, 0.001, n)))
    v = np.exp(g.normal(3, 0.3, n))
    share = np.clip(0.5 + 0.15 * np.tanh(st) + g.normal(0, 0.03, n), 0.01, 0.99) if planted else \
        np.clip(0.5 + g.normal(0, 0.05, n), 0.01, 0.99)
    return pd.DataFrame(dict(open=o, high=hi, low=lo, close=c, volume=v, taker_buy_base=v * share, trades=1.0, era=1.0),
                        index=pd.date_range('2019-09-09', periods=n, freq='1h'))


def test_oracle_finds_a_planted_clue_and_rejects_random_walk(pe):
    noise = pe.lab_run_oracle(None, tf='1h', frame=_oracle_frame(1500, 0.0))
    m = noise['rows'][0]['oos']
    assert not (m['n'] >= 100 and m['ci_lo'] > 0 and m['dsr'] >= 0.9)
    assert '미통과' in noise['report'] and '기준선' in noise['report']
    real = pe.lab_run_oracle(None, tf='1h', frame=_oracle_frame(1500, 0.0012))
    m = real['rows'][0]['oos']
    assert m['n'] >= 100 and m['mean_r'] > 0.2 and m['ci_lo'] > 0
    top = [nm for nm, w, agree in real['clues'][1][:3]]
    assert any('체결강도' in nm for nm in top)                                 # 심어 둔 단서를 단서로 찾아낸다
    cal = real['calib_long']
    assert cal[-1][2] > cal[0][2] + 0.15                                      # 위쪽 분위의 실제 승률이 확실히 높다
    assert '분위' in real['report'] and '단서 (롱' in real['report']


def test_oracle_never_touches_holdout_prices(pe):
    f = _oracle_frame(1100, 0.0012, seed=8)
    hold = f.index[-1] - pd.DateOffset(months=3)
    a = pe.lab_run_oracle(None, tf='1h', frame=f, holdout_start=hold)
    g = f.copy()
    after = g.index >= hold
    g.loc[after, ['open', 'high', 'low', 'close']] *= np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.02, after.sum())))[:, None]
    b = pe.lab_run_oracle(None, tf='1h', frame=g, holdout_start=hold)
    assert a['rows'][0]['oos']['n'] == b['rows'][0]['oos']['n'] > 0
    assert np.allclose(a['rows'][0]['oos_r'], b['rows'][0]['oos_r'])
    assert a['calib_long'] == b['calib_long'] and a['base_long'] == b['base_long']


def test_cli_oracle_guards(pe):
    assert pe.main(['--lab', '--oracle', '--universe']) == 2
    assert pe.main(['--lab', '--oracle', '--only', '4h:flow']) == 2
    assert pe.main(['--lab', '--oracle', '--surrogate-n', '5']) == 2
    assert pe.main(['--lab', '--oracle', '--tfs', '5m']) == 2
    assert pe.main(['--lab', '--oracle', '--stop-pct', '9']) == 2
    assert pe.main(['--lab', '--oracle', '--tp', 'x']) == 2
    assert pe.main(['--lab', '--oracle', '--hold', '1']) == 2
    assert pe.main(['--lab', '--oracle', '--cost', 'maker_entry']) == 2
    assert pe.main(['--lab', '--oracle', '--tp', '2,2']) == 2                 # 같은 목표 두 번
    assert pe.main(['--lab', '--oracle', '--tp', '1,2,3,4,5,6']) == 2         # 최대 5개
    assert pe.main(['--lab', '--oracle', '--tp', '2,20']) == 2


def test_lab_rejects_unknown_options_instead_of_running_something_else(pe, capsys):
    assert pe.main(['--lab', '--orcale']) == 2                                # 오타·옛 파일 → 다른 실행으로 새지 않는다
    out = capsys.readouterr().out
    assert '모르는 옵션' in out and pe.LAB_BUILD in out


def test_oracle_map_compares_targets_against_random_and_break_even(pe):
    f = _oracle_frame(1500, 0.0012)
    outs = [pe.lab_run_oracle(None, tf='1h', frame=f, tp_r=t) for t in (2.0, 3.0)]
    txt = pe.lab_oracle_map(outs)
    assert '끝머리 지도' in txt and ' 2R' in txt and ' 3R' in txt
    assert '38%' in txt and '28%' in txt and '33%' in txt and '25%' in txt   # 손익분기 (1.14/3, 1.14/4) · 무작위 1/3, 1/4


def test_cli_oracle_runs_each_target_and_records_one_procedure_each(pe, monkeypatch, capsys):
    g = np.random.default_rng(0)
    n = 900 * 1440
    c = 30000 * np.exp(np.cumsum(g.normal(0, 0.0006, n)))
    o = np.r_[c[0], c[:-1]]
    base = pd.DataFrame(dict(open=o, high=np.maximum(o, c) * 1.0002, low=np.minimum(o, c) * 0.9998, close=c, volume=1.0,
                             taker_buy_base=0.5, trades=1.0, era=1.0), index=pd.date_range('2023-01-01', periods=n, freq='1min'))

    class FakeStore:
        def __init__(self):
            self.base, self.http = base, None

        def refresh(self):
            pass
    monkeypatch.setattr(pe, 'DataStore', FakeStore)
    monkeypatch.setattr(pe, 'load_funding_history', lambda *a, **k: None)
    assert pe.main(['--lab', '--oracle', '--tp', '2,3']) == 0
    out = capsys.readouterr().out
    assert pe.LAB_BUILD in out and out.count('━━━ 정답 단서 학습') == 2 and '끝머리 지도' in out
    j = pe.ResearchJournal.load()
    assert {'btc|1h:oracle|taker|sl1tp2h24', 'btc|1h:oracle|taker|sl1tp3h24'} <= set(j.d['procedures'])
    assert j.d['entries'][-1]['title'].startswith('정답 단서 학습 (1h, 손절 1.0%, 익절 2/3R')
