"""
4차 사전등록 P24 ~ P26 (RESEARCH_LOG, 2026-10-15 10:51 UTC 커밋 = 자료 받기·계산 전) — "누가 어느 쪽에 서 있나"를 더 깊이.
공통: 1h, 다음 봉 시가, 손절 1.5 ATR(신호 봉, 진입가 기준), 48봉째 종가, 왕복 0.12%, 한 번에 하나, z = 직전 500봉.
실행: python research/round4_2026-10-15.py [p24|p25|p26|all]
"""
import glob
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
njit = r3.njit
HOME = r3.HOME
END = r3.END
COST = r3.COST


@njit(cache=False)
def sim_side_dist(o, h, l, c, side, dist_frac, hold, cost, i0, i1):
    """양방향: 신호 봉 마감 → 다음 봉 시가, 손절 = 진입가 ∓ dist_frac[신호 봉] × 진입가 … 가 아니라 P16 과 같게 1.5 ATR(신호 봉 종가 기준 가격)."""
    ent = np.empty(i1, dtype=np.int64)
    rr = np.empty(i1, dtype=np.float64)
    m = 0
    i = i0
    while i < i1 - 1:
        sd = side[i]
        if sd == 0:
            i += 1
            continue
        e = i + 1
        entry = o[e]
        dist = dist_frac[i] * c[i]
        if not (dist > 0.0) or not (entry > 0.0):
            i += 1
            continue
        stop = entry - sd * dist
        last = min(e + hold - 1, i1 - 1)
        px, xi = c[last], last
        for j in range(e, last + 1):
            if (sd > 0 and l[j] <= stop) or (sd < 0 and h[j] >= stop):
                px = stop
                if (sd > 0 and o[j] < stop) or (sd < 0 and o[j] > stop):
                    px = o[j]
                xi = j
                break
        ent[m] = e
        rr[m] = (sd * (px / entry - 1.0) - cost) / (dist / entry)
        m += 1
        i = xi + 1
    return ent[:m], rr[:m]


def base_feats(df):
    ind = pe._lab_indicators(df)
    c = ind['c'].values.astype(np.float64)
    atrp = np.nan_to_num(ind['atr'].values.astype(np.float64))
    brk = (c - ind['h'].rolling(20).max().shift(1).values) / (atrp * c)
    return ind, c, atrp, pe._z_prev(brk)


def run_p24():
    rows = []
    for sym, start in (('BTCUSDT', '2020-10-01'), ('ETHUSDT', '2022-01-01')):
        df = r3.frame(sym, '1h')
        m = r3.metrics(sym)
        ind, c, atrp, zb = base_feats(df)
        close_t = (df.index + pd.Timedelta(hours=1)).values.astype('datetime64[ns]')
        zt = pe._z_prev(pe._metrics_at(m, 'top_ls_pos', close_t))
        zc = pe._z_prev(pe._metrics_at(m, 'ls_acct', close_t))
        zt0, zc0, zb0 = (np.nan_to_num(x, nan=0.0) for x in (zt, zc, zb))
        okt = ~np.isnan(zt) & ~np.isnan(zc)
        o, h, l = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l'))
        i0, i1 = r3.period_idx(df.index, start, END)
        sideA = np.zeros(len(c), dtype=np.int64)
        sideA[okt & (zt0 > 1) & (zc0 < -1)] = 1
        sideA[okt & (zt0 < -1) & (zc0 > 1)] = -1
        e, R = sim_side_dist(o, h, l, c, sideA, 1.5 * atrp, 48, COST, i0, i1)
        rows.append(r3.verdict_row(f'P24-A 큰손 대 군중 {sym[:3]}', R, df.index.values[e], start, END, 4))
        sideB = np.zeros(len(c), dtype=np.int64)
        sideB[okt & (zc0 < -1) & (zb0 > 2) & (zt0 > 0)] = 1
        e, R = sim_side_dist(o, h, l, c, sideB, 1.5 * atrp, 48, COST, i0, i1)
        rows.append(r3.verdict_row(f'P24-B P16 + 큰손 확인 {sym[:3]}', R, df.index.values[e], start, END, 4))
    r3.show(rows, 'P24 큰손 대 군중', 4)
    return rows


def spot_1h(sym):
    f = sorted(glob.glob(os.path.join(HOME, f'{sym}_1h_spot_2020-01_2026-09.csv')))[0]
    raw = pd.read_csv(f)
    return pd.Series(raw['volume'].values.astype(np.float64), index=pd.DatetimeIndex(pd.to_datetime(raw['time_ms'].values, unit='ms')))


def run_p25():
    rows = []
    for sym in ('BTCUSDT', 'ETHUSDT'):
        df = pe.normalize_frame(pe.fetch_futures_klines_vision(pe.PublicHttp(), sym, '1h', start='2020-01', log=lambda *a, **k: None))
        sv = spot_1h(sym).reindex(df.index)
        share = sv.values / (sv.values + df['volume'].values)
        ind, c, atrp, zb = base_feats(df)
        zs = pe._z_prev(share)
        side = np.zeros(len(c), dtype=np.int64)
        side[(np.nan_to_num(zb, nan=0) > 2) & (np.nan_to_num(zs, nan=0) > 1)] = 1
        o, h, l = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l'))
        i0, i1 = r3.period_idx(df.index, '2020-02-01', END)
        e, R = sim_side_dist(o, h, l, c, side, 1.5 * atrp, 48, COST, i0, i1)
        rows.append(r3.verdict_row(f'P25 현물 주도 돌파 {sym[:3]}', R, df.index.values[e], '2020-02-01', END, 2))
        # 참고(판정 아님): 선물 주도 돌파(현물 비중 z < −1)
        side2 = np.zeros(len(c), dtype=np.int64)
        side2[(np.nan_to_num(zb, nan=0) > 2) & (np.nan_to_num(zs, nan=0) < -1)] = 1
        e2, R2 = sim_side_dist(o, h, l, c, side2, 1.5 * atrp, 48, COST, i0, i1)
        print(f'  참고 {sym[:3]} 선물 주도 돌파(현물 비중 z < −1): {len(R2)}건 {np.nan_to_num(R2.mean()):+.3f}R')
    r3.show(rows, 'P25 현물 주도 돌파', 2)
    return rows


def depth_1h(sym):
    parts = []
    for f in sorted(glob.glob(os.path.join(HOME, 'raw', 'bookdepth_1h', f'{sym}_*.csv'))):
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        if len(d):
            parts.append(d)
    d = pd.concat(parts)
    d['t'] = pd.to_datetime(d['t'])
    d = d.set_index('t').sort_index()
    d = d[~d.index.duplicated(keep='last')]
    return (d['bid1'] - d['ask1']) / (d['bid1'] + d['ask1'])


def run_p26():
    rows = []
    for sym in ('BTCUSDT', 'ETHUSDT'):
        df = pe.normalize_frame(pe.fetch_futures_klines_vision(pe.PublicHttp(), sym, '1h', start='2022-11', log=lambda *a, **k: None))
        imb = depth_1h(sym).reindex(df.index).values
        ind, c, atrp, zb = base_feats(df)
        zi = pe._z_prev(imb)
        side = np.zeros(len(c), dtype=np.int64)
        side[(np.nan_to_num(zb, nan=0) > 2) & (np.nan_to_num(zi, nan=0) > 1)] = 1
        o, h, l = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l'))
        i0, i1 = r3.period_idx(df.index, '2023-02-01', END)
        e, R = sim_side_dist(o, h, l, c, side, 1.5 * atrp, 48, COST, i0, i1)
        print(f'  {sym}: 호가 깊이 기록 있는 시간 {np.mean(~np.isnan(imb[i0:i1])):.0%}')
        rows.append(r3.verdict_row(f'P26 호가 불균형 돌파 {sym[:3]}', R, df.index.values[e], '2023-02-01', END, 2))
    r3.show(rows, 'P26 호가 깊이 불균형', 2)
    return rows


if __name__ == '__main__':
    pe.Paths.init()
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    for k, f in dict(p24=run_p24, p25=run_p25, p26=run_p26).items():
        if what in (k, 'all'):
            f()
