"""
"70달러의 기적"을 정직하게: 바벨(Taleb) — 대부분은 권장안(P12 0.75% + P16 1%)으로, 작은 몫만 확인된 전략 중 꼬리가 가장 두꺼운
P12 피라미딩을 크게(단위당 2~4%, 노출 10배까지) 거는 '복권 몫'으로. 새 시험이 아니다 (확인된 규칙의 크기·배분만 바꾼다).
- 두 계좌를 따로 굴린다(재배분 없음). 국면 2(2021-11-27 ~ 2026-10-04) 월 수익을 같은 덩어리 순서로 함께 다시 뽑는다(상관 보존).
- 각 계좌는 자기 시드(예: 70 × 30% = 21달러)에서 시작하고 최소 주문(BTC 100 · ETH 20 USDT)을 그대로 적용한다.
실행: python research/barbell_2026-10-15.py
"""
import importlib
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import pattern_edge_v612 as pe  # noqa: E402
import p12_audit as pa  # noqa: E402

pf = importlib.import_module('portfolio_2026-10-15')
HOME = os.path.join(os.path.expanduser('~'), 'CoinData_Matrix')
R2 = ('2021-11-27', pf.END)


def monthly(eq):
    return eq.resample('ME').last().pct_change().dropna()


def joint_boot(series, months, n=20000, block=3, seed=11):
    """같은 달 순서로 여러 계좌의 월 수익을 함께 다시 뽑는다."""
    rng = np.random.default_rng(seed)
    X = np.column_stack([s.values for s in series])
    L = len(X)
    out = np.empty((n, months, X.shape[1]))
    for k in range(n):
        j = rng.integers(L)
        for m in range(months):
            if m and rng.random() < 1.0 / block:
                j = rng.integers(L)
            out[k, m] = X[j % L]
            j += 1
    return out


def main():
    pe.Paths.init()
    base = pd.read_parquet(os.path.join(HOME, 'BTCUSDT_1m_v612.parquet'))
    base = base[base.index < pd.Timestamp('2026-10-15')]
    btc4 = pe._masters_frame(base, '4h')
    i0, i1 = int(btc4.index.searchsorted(pd.Timestamp(pf.START))), int(btc4.index.searchsorted(pd.Timestamp(pf.END)))
    fb = pe.load_funding_history(refresh=False)
    fe = pe.load_funding_history(refresh=False, symbol='ETHUSDT')
    cb = pf.campaigns(btc4, pa.run_1m(btc4, base, i0, i1), 'BTCUSDT', fb)
    eth4 = pe.normalize_frame(pe.lab_eth_frames(pe.PublicHttp(), ('4h',))['4h'])
    j0, j1 = int(eth4.index.searchsorted(pd.Timestamp(pf.START))), int(eth4.index.searchsorted(pd.Timestamp(pf.END)))
    ce = pf.campaigns(eth4, pa.run(eth4, j0, j1), 'ETHUSDT', fe)
    mb = pd.read_parquet(os.path.join(HOME, 'BTCUSDT_metrics_5m.parquet'))
    me = pd.read_parquet(os.path.join(HOME, 'ETHUSDT_metrics_5m.parquet'))
    quiet = lambda *a, **k: None  # noqa: E731
    hb = pe.fetch_futures_klines_vision(pe.PublicHttp(), 'BTCUSDT', '1h', start='2020-06', log=quiet)
    he = pe.fetch_futures_klines_vision(pe.PublicHttp(), 'ETHUSDT', '1h', start='2020-06', log=quiet)
    qb = pf.p16_campaigns('BTCUSDT', hb, mb, funding=fb)
    qe = pf.p16_campaigns('ETHUSDT', he, me, funding=fe)
    closes = {'BTCUSDT': btc4['close'], 'ETHUSDT': eth4['close']}
    print('━━ 바벨: 권장안 몫 + 복권 몫(P12 크게) · 국면 2 월 수익 함께 다시 뽑기 2만 경로 · 시드 70달러 ━━')
    print('열: 2년 중앙(하위10%·상위10%) · 2년 안 한 번이라도 500·1,000·2,000달러 · 2년 끝 35달러 미만(반토막) · 실제 국면 2 복권 몫 연복리/낙폭')
    for frac in (0.0, 0.3, 0.5, 1.0):
        for rs in ((0.02, 0.03, 0.04) if frac > 0 else (None,)):
            seed_core, seed_s = 70.0 * (1 - frac), 70.0 * frac
            series, labels = [], []
            if seed_core > 0:
                eqc, _ = pf.simulate(cb + ce + qb + qe, closes, 0.0075, seed=seed_core, real70=True, start=R2[0], end=R2[1], r16=0.01,
                                     p16_auto=True)
                series.append(monthly(eqc))
                labels.append(('core', seed_core))
            if seed_s > 0:
                eqs, _ = pf.simulate(cb + ce, closes, rs, seed=seed_s, real70=True, lev_cap=10.0, start=R2[0], end=R2[1])
                st = pf.stats(eqs, seed_s)
                series.append(monthly(eqs))
                labels.append(('sleeve', seed_s))
            idx = series[0].index
            for s_ in series[1:]:
                idx = idx.intersection(s_.index)
            P = joint_boot([s_.reindex(idx).fillna(0.0) for s_ in series], 24)
            W = sum(seed_ * np.cumprod(1 + P[:, :, k], axis=1) for k, (_, seed_) in enumerate(labels))
            fin = W[:, -1]
            q = np.percentile(fin, [10, 50, 90])
            mx = W.max(axis=1)
            nm = '권장안 100%' if frac == 0 else (f'복권 100% (P12 {rs:.0%}/단위)' if frac == 1 else f'권장안 {1 - frac:.0%} + 복권 {frac:.0%} (P12 {rs:.0%}/단위)')
            tail = f' · 복권 몫 실제 연 {st["cagr"]:+.0%}/낙폭 {st["mdd"]:.0%}' if seed_s > 0 else ''
            print(f'  {nm:<38} 2년 ${q[1]:>6,.0f} (${q[0]:,.0f}·${q[2]:,.0f}) · 500↑ {np.mean(mx >= 500):>4.0%} · 1,000↑ {np.mean(mx >= 1000):>4.0%} · '
                  f'2,000↑ {np.mean(mx >= 2000):>4.0%} · 끝 35↓ {np.mean(fin < 35):>4.0%}{tail}')


if __name__ == '__main__':
    main()
