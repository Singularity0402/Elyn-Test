"""
Strategy Lab: 무엣지 시장에서는 아무것도 통과시키지 않고, 진짜 추세가 있으면 찾아내는지.
합성 데이터이므로 수익성 증거가 아니다.
"""
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
    base = _trend_1m(1300, 0.0000004)
    res = pe.lab_run(base, tfs=('1h', '4h'))
    assert _passed(res)
    assert 'holdout평균R' not in res['report'] and '봉인' in res['report']
    shown = pe.lab_run(base, tfs=('4h',), families=['donchian'], reveal_holdout=True)
    assert 'holdout평균R' in shown['report']


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
