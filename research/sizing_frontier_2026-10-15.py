"""
크기 경계 (2026-10-15): 확인된 P12(BTC·ETH) + P16(BTC·ETH)을 한 계좌로, 크기를 바꿔 가며 앞으로의 분포를 본다. 새 시험이 아니다.
- 국면 2(2021-11-27 ~ 2026-10-04)의 월 수익을 3개월 덩어리로 다시 뽑아(2만 경로) 1·2·3년 뒤를 본다.
- P16 이 현금보다 커지면 선물로(펀딩 냄, 최소 주문 BTC 100 · ETH 20 USDT), 노출 합 ≤ 자본 × 3.
- 정직하게: P16 BTC 는 발견에 쓴 표본이라 부풀려졌을 수 있다 → P16 엣지를 절반으로 깎은 경우를 함께 본다.
실행: python research/sizing_frontier_2026-10-15.py
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
    closes = {'BTCUSDT': btc4['close'], 'ETHUSDT': eth4['close']}
    print('━━ 크기 경계: 국면 2 월 수익 다시 뽑기 (2만 경로, 시드 70달러, 70달러 최소 주문 반영) ━━')
    print('열: 1년 중앙 · 2년 중앙(하위10%·상위10%) · 2년 안 500달러↑ · 1,000달러↑ · 2년 손실 · 2년 반토막 경험 · 국면 2 실제 연복리/낙폭')
    for label, hc in (('P16 엣지 그대로', 0.0), ('P16 엣지 절반으로 깎음 (보수)', 0.5)):
        qb = pf.p16_campaigns('BTCUSDT', hb, mb, funding=fb, haircut=hc)
        qe = pf.p16_campaigns('ETHUSDT', he, me, funding=fe, haircut=hc)
        print(f'\n[{label}]')
        for r12 in (0.0, 0.0075, 0.01):
            for r16 in (0.01, 0.02, 0.03, 0.05, 0.08):
                sel = (cb + ce if r12 > 0 else []) + qb + qe
                eq, _ = pf.simulate(sel, closes, max(r12, 1e-9), real70=True, start='2021-11-27', end=pf.END, r16=r16, p16_auto=True)
                st = pf.stats(eq, 70.0)
                mret = eq.resample('ME').last().pct_change().dropna().values
                P = pf.block_boot(mret, 24, n=20000)
                W = 70.0 * np.cumprod(1 + P, axis=1)
                f12, f24 = W[:, 11], W[:, -1]
                peak = np.maximum.accumulate(np.c_[np.full(len(W), 70.0), W], axis=1)[:, 1:]
                mdd = (1 - W / peak).max(axis=1)
                q = np.percentile(f24, [10, 50, 90])
                nm = f'P12 {r12:.2%} + P16 {r16:.0%}' if r12 > 0 else f'P16만 {r16:.0%}'
                print(f'  {nm:<22} 1년 ${np.median(f12):>6,.0f} · 2년 ${q[1]:>6,.0f} (${q[0]:,.0f}·${q[2]:,.0f}) · 500↑ {np.mean(W.max(axis=1) >= 500):>4.0%} · '
                      f'1000↑ {np.mean(W.max(axis=1) >= 1000):>4.0%} · 손실 {np.mean(f24 < 70):>4.0%} · 반토막 {np.mean(mdd >= 0.5):>4.0%} · '
                      f'실제 연 {st["cagr"]:+.0%}/낙폭 {st["mdd"]:.0%}')


if __name__ == '__main__':
    main()
