"""
5차 사전등록 P27 · P29 (RESEARCH_LOG, 2026-10-15 11:10 UTC 커밋 = 계산 전) — 군중 쏠림 계열, 아직 안 본 시장에서만.
실행: python research/round5_2026-10-15.py
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

r3 = importlib.import_module('round3_2026-10-15')
r4 = importlib.import_module('round4_2026-10-15')
END, COST = r3.END, r3.COST


def p27():
    df = r3.frame('ETHUSDT', '1h')
    m = r3.metrics('ETHUSDT')
    ind = pe._lab_indicators(df)
    o, h, l, c = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l', 'c'))
    atrp = np.nan_to_num(ind['atr'].values)
    close_t = (df.index + pd.Timedelta(hours=1)).values.astype('datetime64[ns]')
    z = pe._z_prev(pe._metrics_at(m, 'ls_acct', close_t))
    side = np.zeros(len(c), dtype=np.int64)
    z0 = np.nan_to_num(z, nan=0.0)
    side[z0 < -2] = 1
    side[z0 > 2] = -1
    i0, i1 = r3.period_idx(df.index, '2022-01-01', END)
    e, R = r4.sim_side_dist(o, h, l, c, side, 1.5 * atrp, 48, COST, i0, i1)
    S = side[e - 1]
    row = r3.verdict_row('P27 군중 극단 역행 ETH 1h', R, df.index.values[e], '2022-01-01', END, 2)
    print(f'  롱 {int((S > 0).sum())}건 {np.nan_to_num(R[S > 0].mean()):+.3f}R · 숏 {int((S < 0).sum())}건 {np.nan_to_num(R[S < 0].mean()):+.3f}R')
    return row


def p29():
    allR, allT, per = [], [], []
    for sym in pe.P16_ALT_SYMBOLS:
        df = pe.normalize_frame(pe.fetch_futures_klines_vision(pe.PublicHttp(), sym, '1h', start='2020-06', log=lambda *a, **k: None))
        m = r3.metrics(sym)
        zl, zu, zd, atrp = r3.crowd_z(df, m, 60)
        sig = (np.nan_to_num(zl, nan=0) > 1.0) & (np.nan_to_num(zd, nan=0) > 2.0)
        o, h, l, c = (df[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close'))
        start = str((m.index[0] + pd.Timedelta(hours=520)).date())
        i0, i1 = r3.period_idx(df.index, start, END)
        e, R = pe._fixed_stop_hold_sim(o, h, l, c, sig, np.nan_to_num(atrp), 1.5, 48, -1, COST, i0, i1)
        per.append((sym, len(R), float(np.nan_to_num(R.mean()))))
        allR.append(R)
        allT.append(df.index.values[e])
    print('  시장별: ' + ' · '.join(f'{s[:-4]} {n}건 {v:+.3f}' for s, n, v in per))
    return r3.verdict_row('P29 P16 거울 알트 7개 합산', np.concatenate(allR), np.concatenate(allT), '2022-01-01', END, 2)


if __name__ == '__main__':
    pe.Paths.init()
    rows = [p27(), p29()]
    r3.show(rows, '5차 P27 · P29', 2)
