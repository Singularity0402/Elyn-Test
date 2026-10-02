"""
워크포워드 가속(병렬·캐시·2단계 null)이 결과를 바꾸지 않는지 확인한다.
합성 데이터이므로 수익성 증거가 아니다.
"""
import numpy as np
import pandas as pd

from synthetic import planted_cached


def _run(pe, base, start, **kw):
    return pe.walk_forward(base, '15m', start, step=16, max_evals=48, **kw)


def _key(res):
    return [(t['time'], t['side'], round(t['r'], 9), round(t['equity'], 6)) for t in res['trades']], res['evals']


def test_parallel_cache_and_sequential_give_identical_results(pe):
    df, starts, cut = planted_cached(days=800)
    base = df.iloc[:cut + 2000]
    start = str(base.index[-1] - pd.Timedelta(days=12))
    seq = _run(pe, base, start, workers=1, use_cache=False)
    par = _run(pe, base, start, workers=2, use_cache=True)
    again = _run(pe, base, start, workers=2, use_cache=True)
    assert _key(seq) == _key(par) == _key(again)
    assert par['summary']['computed'] == 48 and again['summary']['cache_hits'] == 48 and again['summary']['computed'] == 0
    import multiprocessing as mp
    if mp.get_start_method() == 'fork':
        assert 'wf_parallel' not in pe.HEALTH.items                      # 병렬 경로가 실제로 동작함


def test_two_stage_null_equals_null_everywhere(pe):
    df, starts, cut = planted_cached(days=800)
    base = df.iloc[:cut + 2000]
    start = str(base.index[-1] - pd.Timedelta(days=12))
    two = _run(pe, base, start, workers=1, do_null=True, use_cache=False)
    # 기준: 모든 시점에서 null ON 으로 직접 판정
    snap = pe.Snapshot(base, base.index[-1].to_pydatetime() + pd.Timedelta(minutes=1))
    df15 = snap.tf('15m')
    t0 = max(int(df15.index.searchsorted(pd.Timestamp(start))), 3 * 2 * 192 + 2 * 16 + 100)
    grid = list(range(t0, len(df15) - 16 - 2, 16))[:48]
    full = {t: pe._wf_eval_with(snap, '15m', t, True)[1] for t in grid}
    s1 = pe.wf_decisions(base, snap, '15m', grid, False, workers=1)
    fin = [t for t in grid if s1[t].get('precheck_ok')]
    s2 = pe.wf_decisions(base, snap, '15m', fin, True, workers=1)
    merged = {t: (s2[t] if t in fin else s1[t]) for t in grid}
    for t in grid:
        assert merged[t]['trade'] == full[t]['trade'] and merged[t].get('p_raw') == full[t].get('p_raw')
    assert two['evals'] == 48


def test_cache_is_invalidated_when_history_changes(pe):
    df, starts, cut = planted_cached(days=800)
    base = df.iloc[:cut + 2000].copy()
    start = str(base.index[-1] - pd.Timedelta(days=12))
    _run(pe, base, start, workers=1)
    base.iloc[1000:2000, base.columns.get_loc('close')] *= 1.01      # WF 시작 이전 이력 변경
    r = _run(pe, base, start, workers=1)
    assert r['summary']['cache_hits'] == 0


def test_search_speedups_keep_neighbors_identical(pe):
    """캐시형 FFT 상관·row_quantile·벡터 znorm 이 원래 계산과 같은 값을 낸다."""
    g = np.random.default_rng(0)
    x = np.cumsum(g.normal(size=5000))
    df = pd.DataFrame(dict(open=x + 100, high=x + 101, low=x + 99, close=x + 100, volume=1 + g.random(5000),
                           taker_buy_base=0.5 + 0 * x, trades=1.0, era=1.0),
                      index=pd.date_range('2024-01-01', periods=5000, freq='15min'))
    ch = pe.Channels(df)
    Q = ch.shape[4000:4096]
    r_old, sd_old = pe.corr_profile(Q, ch.shape[:3000 + 96])
    r_new, sd_new = pe.corr_profile_ch(ch, 'shape', Q, 3001)
    assert np.allclose(r_old[:3001], r_new, atol=1e-9) and np.allclose(sd_old[:3001], sd_new, rtol=1e-9)
    a = g.normal(size=(5, 1000))
    assert np.allclose(pe.row_quantile(a, 0.2), np.quantile(a, 0.2, axis=0))
