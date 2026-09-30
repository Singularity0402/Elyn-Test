"""테스트용 합성 시장 데이터. 실데이터 성과의 증거가 아니다 — 불변식·보정·검정력 확인용."""
import numpy as np
import pandas as pd


def random_walk_tf(n, seed, freq_min=15, start='2019-09-09'):
    """엣지 없음(마팅게일) + 변동성 군집. 미래 방향은 과거와 독립."""
    g = np.random.default_rng(seed)
    lv = np.zeros(n)
    e = g.normal(0, 1, n)
    for i in range(1, n):
        lv[i] = 0.985 * lv[i - 1] + 0.12 * e[i]
    sig = 0.004 * np.exp(lv)
    r = g.normal(0, 1, n) * sig
    c = 30000 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) * (1 + np.abs(g.normal(0, 0.5, n)) * sig)
    lo = np.minimum(o, c) * (1 - np.abs(g.normal(0, 0.5, n)) * sig)
    vol = np.exp(g.normal(5, 0.4, n)) * (1 + 50 * np.abs(r))
    tb = vol * np.clip(0.5 + g.normal(0, 0.05, n), 0.05, 0.95)
    idx = pd.date_range(start, periods=n, freq=f'{freq_min}min')
    return pd.DataFrame(dict(open=o, high=hi, low=lo, close=c, volume=vol, taker_buy_base=tb,
                             trades=np.full(n, 100.0), era=np.full(n, 1.0)), index=idx)


def planted_1m(days=800, seed=7, every_days=6.0, amp=0.08, drift=0.015, K=192, H=16, tfm=15):
    """
    1분봉에 '되풀이되는 15m 스케일 패턴 → 이후 상승' 엣지를 심는다.
    반환 (df, starts, cut): cut = 마지막 패턴이 끝나는 1분봉 위치 (df.iloc[:cut] 의 마지막 K봉 = 패턴).
    가격 수준은 cut 시점 60,000 USDT 로 맞춘다 (로그수익률 불변).
    """
    g = np.random.default_rng(seed)
    n = days * 1440
    sig = 0.0007 * np.exp(np.convolve(g.normal(0, 1, n), np.ones(600) / 600, mode='same') * 8)
    r = g.normal(0, 1, n) * sig
    L, F = K * tfm, H * tfm
    x = np.linspace(0, 1, L)
    inc = np.diff(np.r_[0.0, -amp * np.sin(np.pi * x) ** 2 + 0.4 * amp * x])
    starts, s, step = [], int(3 * L), int(every_days * 1440)
    while s + L + F < n - 2 * L:
        s0 = (s // tfm) * tfm
        r[s0:s0 + L] += inc
        r[s0 + L:s0 + L + F] += drift / F
        starts.append(s0)
        s += step + int(g.integers(-300, 300))
    c = 30000 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) * (1 + np.abs(g.normal(0, 0.4, n)) * sig)
    lo = np.minimum(o, c) * (1 - np.abs(g.normal(0, 0.4, n)) * sig)
    v = np.exp(g.normal(3, 0.5, n))
    cut = starts[-1] + L
    k = c[cut - 1] / 60000.0
    idx = pd.date_range('2024-01-01', periods=n, freq='1min')
    df = pd.DataFrame(dict(open=o / k, high=hi / k, low=lo / k, close=c / k, volume=v,
                           taker_buy_base=v * np.clip(0.5 + g.normal(0, 0.05, n), 0, 1),
                           trades=np.full(n, 50.0), era=np.full(n, 1.0)), index=idx)
    return df, starts, cut


_PLANTED = {}


def planted_cached(**kw):
    key = tuple(sorted(kw.items()))
    if key not in _PLANTED:
        _PLANTED[key] = planted_1m(**kw)
    df, starts, cut = _PLANTED[key]
    return df.copy(), list(starts), cut
