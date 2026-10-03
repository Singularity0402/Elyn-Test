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
