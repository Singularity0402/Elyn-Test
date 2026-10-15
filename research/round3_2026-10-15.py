"""
3차 사전등록 P18 ~ P23 (RESEARCH_LOG, 2026-10-15 10:39 UTC 커밋 = 계산 전) — 사람 심리·시장 구조·청산 지도.
규칙은 사전등록 그대로 구현하고 가설마다 한 번만 돌린다. 판정: 거래 ≥ 30 · 평균R ≤ 0 → 반증 · 두 반쪽 모두 > 0 이고
달 묶음 단측 (5% ÷ 묶음 가설 수) 하한 > 0 → 확인 · 그 외 → 반증 안 됨.
실행: python research/round3_2026-10-15.py [p18|p19|p20|p21|p22|p23|all]
"""
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pattern_edge_v612 as pe  # noqa: E402

try:
    from numba import njit
except Exception:
    def njit(*a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]

HOME = os.path.join(os.path.expanduser('~'), 'CoinData_Matrix')
END = '2026-10-04'
COST = 0.0012


# ── 자료 ─────────────────────────────────────────────────────────────
def btc_frames(tfs=('1h',)):
    base = pd.read_parquet(os.path.join(HOME, 'BTCUSDT_1m_v612.parquet'))
    base = base[base.index < pd.Timestamp('2026-10-15')]
    snap = pe.Snapshot(base, base.index[-1].to_pydatetime() + pd.Timedelta(minutes=1))
    out = {}
    for tf in tfs:
        d = snap.tf(tf)
        out[tf] = pe.normalize_frame(d[d['complete'].values > 0.5])
    return out


def eth_frame(tf):
    h = pe.PublicHttp()
    quiet = lambda *a, **k: None  # noqa: E731
    if tf == '1h':
        sp = pe.fetch_spot_klines_vision(h, 'ETHUSDT', '1h', start='2017-08', end='2019-12', log=quiet)
        fu = pe.fetch_futures_klines_vision(h, 'ETHUSDT', '1h', start='2020-01', log=quiet)
        return pe.normalize_frame(pe.merge_spot_perp(sp, fu))
    return pe.normalize_frame(pe.fetch_futures_klines_vision(h, 'ETHUSDT', tf, start='2021-11', log=quiet))


def frame(sym, tf):
    return btc_frames((tf,))[tf] if sym == 'BTCUSDT' else eth_frame(tf)


def metrics(sym):
    return pd.read_parquet(os.path.join(HOME, f'{sym}_metrics_5m.parquet'))


# ── 판정 ─────────────────────────────────────────────────────────────
def verdict_row(name, R, T, start, end, k):
    R = np.asarray(R, dtype=np.float64)
    T = np.asarray(T, dtype='datetime64[ns]')
    n = len(R)
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    mid = a + (b - a) / 2
    if n < 2:
        return dict(name=name, n=n, mean=float('nan'), lo=float('nan'), t=float('nan'), h1=float('nan'), h2=float('nan'),
                    verdict='판정 불가', mid=str(mid.date()))
    t, se = pe._cluster_t(R, T)
    z = pe.norm_ppf(1 - 0.05 / k)
    lo = float(R.mean() - z * se) if se == se else float('nan')
    h = T < np.datetime64(mid)
    h1 = float(R[h].mean()) if h.any() else float('nan')
    h2 = float(R[~h].mean()) if (~h).any() else float('nan')
    if n < 30:
        v = '판정 불가'
    elif not R.mean() > 0:
        v = '반증'
    elif lo > 0 and h1 > 0 and h2 > 0:
        v = '확인'
    else:
        v = '반증 안 됨'
    return dict(name=name, n=n, mean=float(R.mean()), lo=lo, t=t, h1=h1, h2=h2, verdict=v, mid=str(mid.date()),
                win=float(np.mean(R > 0)), years={int(y): (int((pd.DatetimeIndex(T).year == y).sum()),
                                                            round(float(R[pd.DatetimeIndex(T).year == y].mean()), 3))
                                                 for y in sorted(set(pd.DatetimeIndex(T).year))})


def show(rows, title, k):
    print(f'\n━━ {title} (가설 {k}개 → 단측 {5 / k:.2f}% 하한) ━━')
    for r in rows:
        print(f'  {r["name"]:<34} {r["n"]:>5}건 평균 {np.nan_to_num(r["mean"]):+.3f}R · t {np.nan_to_num(r["t"]):+.2f} · 하한 '
              f'{np.nan_to_num(r["lo"]):+.3f} · 반쪽 {np.nan_to_num(r["h1"]):+.3f} / {np.nan_to_num(r["h2"]):+.3f} (경계 {r["mid"]}) → {r["verdict"]}')
        if r.get('years'):
            print('      연도별: ' + ' · '.join(f'{y} {v:+.2f}({n})' for y, (n, v) in r['years'].items()))


# ── 공통 체결: 신호 봉 마감 → 다음 봉 시가, 신호마다 정해진 손절가, hold 봉째 종가 ──────────────
@njit(cache=False)
def sim_sig_stop(o, h, l, c, side, stop, hold, cost, i0, i1):
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
        st = stop[i]
        dist = (entry - st) * sd
        if not (dist > 0.0) or not (entry > 0.0):
            i += 1
            continue
        last = min(e + hold - 1, i1 - 1)
        px, xi = c[last], last
        for j in range(e, last + 1):
            if (sd > 0 and l[j] <= st) or (sd < 0 and h[j] >= st):
                px = st
                if (sd > 0 and o[j] < st) or (sd < 0 and o[j] > st):
                    px = o[j]
                xi = j
                break
        ent[m] = e
        rr[m] = (sd * (px / entry - 1.0) - cost) / (dist / entry)
        m += 1
        i = xi + 1
    return ent[:m], rr[:m]


def period_idx(idx, start, end):
    return int(idx.searchsorted(pd.Timestamp(start))), int(idx.searchsorted(pd.Timestamp(end)))


# ── P18 둥근 가격 ─────────────────────────────────────────────────────
def p18_signals(df):
    ind = pe._lab_indicators(df)
    o, h, l, c = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l', 'c'))
    atr = np.nan_to_num(ind['atr'].values) * c
    pc = np.r_[np.nan, c[:-1]]
    g = 10.0 ** (np.floor(np.log10(np.maximum(c, 1e-9))) - 1)
    n = len(c)
    sA, stA = np.zeros(n, dtype=np.int64), np.zeros(n)
    sB, stB = np.zeros(n, dtype=np.int64), np.zeros(n)
    for i in range(1, n):
        if not (atr[i] > 0) or not np.isfinite(pc[i]):
            continue
        gi = g[i]
        # A 돌파 가속
        Lu = math.floor(c[i] / gi) * gi
        if pc[i] < Lu <= c[i]:
            sA[i], stA[i] = 1, Lu - atr[i]
        else:
            Ld = math.ceil(c[i] / gi) * gi
            if c[i] <= Ld < pc[i]:
                sA[i], stA[i] = -1, Ld + atr[i]
        # B 닿고 밀림
        Lb = math.floor(pc[i] / gi) * gi + gi                 # 이전 종가 위의 첫 둥근 가격
        up = h[i] >= Lb and c[i] < Lb
        La = math.ceil(pc[i] / gi) * gi - gi                  # 이전 종가 아래의 첫 둥근 가격
        dn = l[i] <= La and c[i] > La
        if up and not dn:
            sB[i], stB[i] = -1, h[i] + 0.5 * atr[i]
        elif dn and not up:
            sB[i], stB[i] = 1, l[i] - 0.5 * atr[i]
    return o, h, l, c, sA, stA, sB, stB


def run_p18():
    rows = []
    for sym in ('BTCUSDT', 'ETHUSDT'):
        df = frame(sym, '1h')
        o, h, l, c, sA, stA, sB, stB = p18_signals(df)
        i0, i1 = period_idx(df.index, '2018-01-01', END)
        for nm, s_, st_ in (('A 돌파 가속', sA, stA), ('B 닿고 밀림', sB, stB)):
            e, R = sim_sig_stop(o, h, l, c, s_, st_, 12, COST, i0, i1)
            rows.append(verdict_row(f'P18-{nm[0]} {nm[2:]} {sym[:3]}', R, df.index.values[e], '2018-01-01', END, 4))
    show(rows, 'P18 둥근 가격 (Osler)', 4)
    return rows


# ── P19 터틀 수프 ─────────────────────────────────────────────────────
@njit(cache=False)
def turtle_soup(o, h, l, c, atr, cost, i0, i1, hold):
    ent = np.empty(i1, dtype=np.int64)
    rr = np.empty(i1, dtype=np.float64)
    m = 0
    i = max(i0, 21)
    while i < i1 - 1:
        # 직전 20봉 최저·최고와 그 위치
        lo, lo_j, hi, hi_j = 1e300, -1, -1e300, -1
        for j in range(i - 20, i):
            if l[j] < lo:
                lo, lo_j = l[j], j
            if h[j] > hi:
                hi, hi_j = h[j], j
        side = 0
        if l[i] < lo and lo_j <= i - 4:
            side, level, st = 1, lo, l[i] - 0.05 * atr[i]
        elif h[i] > hi and hi_j <= i - 4:
            side, level, st = -1, hi, h[i] + 0.05 * atr[i]
        if side == 0 or not (atr[i] > 0):
            i += 1
            continue
        e = i + 1
        filled = (side > 0 and h[e] >= level) or (side < 0 and l[e] <= level)
        if not filled:
            i += 1
            continue
        entry = level
        if (side > 0 and o[e] > level) or (side < 0 and o[e] < level):
            entry = o[e]
        dist = (entry - st) * side
        if not (dist > 0):
            i += 1
            continue
        last = min(e + hold - 1, i1 - 1)
        px, xi = c[last], last
        for j in range(e, last + 1):
            if (side > 0 and l[j] <= st) or (side < 0 and h[j] >= st):
                px = st
                if j > e and ((side > 0 and o[j] < st) or (side < 0 and o[j] > st)):
                    px = o[j]
                xi = j
                break
        ent[m] = e
        rr[m] = (side * (px / entry - 1.0) - cost) / (dist / entry)
        m += 1
        i = xi + 1
    return ent[:m], rr[:m]


def run_p19():
    rows = []
    for sym in ('BTCUSDT', 'ETHUSDT'):
        for tf in ('1h', '4h', '1d'):
            if sym == 'BTCUSDT':
                df = btc_frames((tf,))[tf] if tf != '1d' else pe.lab_daily_bars(btc_frames(('1h',))['1h'], 60)
            else:
                df = eth_frame('1h') if tf == '1h' else (eth_4h() if tf == '4h' else pe.lab_daily_bars(eth_frame('1h'), 60))
            df = pe.normalize_frame(df) if tf != '1d' else df
            if 'taker_buy_base' not in df.columns:
                df = df.assign(taker_buy_base=0.0)
            ind = pe._lab_indicators(df)
            o, h, l, c = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l', 'c'))
            atr = np.nan_to_num(ind['atr'].values) * c
            i0, i1 = period_idx(df.index, '2018-01-01', END)
            e, R = turtle_soup(o, h, l, c, atr, COST, i0, i1, 5)
            rows.append(verdict_row(f'P19 터틀 수프 {sym[:3]} {tf}', R, df.index.values[e], '2018-01-01', END, 6))
    show(rows, 'P19 터틀 수프 (라쉬키·코너스)', 6)
    return rows


def eth_4h():
    return pe.normalize_frame(pe.lab_eth_frames(pe.PublicHttp(), ('4h',))['4h'])


# ── P20 펀딩 정산 시각 ────────────────────────────────────────────────
def run_p20():
    rows = []
    for sym in ('BTCUSDT', 'ETHUSDT'):
        df = frame(sym, '1h')
        f = pe.load_funding_history(refresh=False, symbol=sym)
        f = f[(f.index >= '2020-01-01') & (f.index < END)]
        ind = pe._lab_indicators(df)
        o, c = ind['o'].values, ind['c'].values
        atrp = ind['atr'].values
        pos = {t: i for i, t in enumerate(df.index)}
        fa = f.index.floor('h')
        RA, TA, RB, TB = [], [], [], []
        for k in range(1, len(f)):
            t = fa[k]
            fp = float(f.values[k - 1])
            if abs(fp) < 0.0003:
                continue
            sd = -1 if fp > 0 else 1
            ia, ib = pos.get(t - pd.Timedelta(hours=1)), pos.get(t)
            if ia is not None and ia >= 1 and atrp[ia - 1] > 0:
                RA.append((sd * (c[ia] / o[ia] - 1.0) - COST) / atrp[ia - 1])
                TA.append(df.index.values[ia])
            if ib is not None and ib >= 1 and atrp[ib - 1] > 0:
                RB.append((-sd * (c[ib] / o[ib] - 1.0) - COST) / atrp[ib - 1])
                TB.append(df.index.values[ib])
        rows.append(verdict_row(f'P20-A 정산 전 {sym[:3]}', RA, TA, '2020-01-01', END, 4))
        rows.append(verdict_row(f'P20-B 정산 후 {sym[:3]}', RB, TB, '2020-01-01', END, 4))
    show(rows, 'P20 펀딩 정산 시각', 4)
    return rows


# ── P21 CME 주말 공백 ─────────────────────────────────────────────────
def us_dst(day):
    """미국 서머타임: 3월 둘째 일요일 ~ 11월 첫 일요일 (날짜 기준 근사)."""
    y = day.year
    mar = pd.Timestamp(year=y, month=3, day=1)
    second_sun = mar + pd.Timedelta(days=(6 - mar.weekday()) % 7 + 7)
    nov = pd.Timestamp(year=y, month=11, day=1)
    first_sun = nov + pd.Timedelta(days=(6 - nov.weekday()) % 7)
    return second_sun <= day < first_sun


def run_p21():
    rows = []
    for sym, start in (('BTCUSDT', '2020-01-01'), ('ETHUSDT', '2021-03-01')):
        df = frame(sym, '1h')
        o, h, l, c = (df[k].values for k in ('open', 'high', 'low', 'close'))
        pos = {t: i for i, t in enumerate(df.index)}
        R, T = [], []
        fridays = pd.date_range(start, END, freq='W-FRI')
        for F in fridays:
            dst = us_dst(F)
            close_t = F + pd.Timedelta(hours=20 if dst else 21)
            open_t = F + pd.Timedelta(days=2, hours=22 if dst else 23)
            ic, io = pos.get(close_t - pd.Timedelta(hours=1)), pos.get(open_t)
            if ic is None or io is None:
                continue
            pc_, po = c[ic], o[io]
            gap = po / pc_ - 1
            if abs(gap) < 0.01:
                continue
            sd = -1 if gap > 0 else 1
            target, stop = pc_, po - sd * abs(po - pc_)
            dist = abs(po - stop)
            px, last = None, min(io + 71, len(c) - 1)
            for j in range(io, last + 1):
                hit_stop = (sd > 0 and l[j] <= stop) or (sd < 0 and h[j] >= stop)
                hit_tgt = (sd > 0 and h[j] >= target) or (sd < 0 and l[j] <= target)
                if hit_stop:
                    px = stop
                    break
                if hit_tgt:
                    px = target
                    break
            if px is None:
                px = c[last]
            R.append((sd * (px / po - 1.0) - COST) / (dist / po))
            T.append(df.index.values[io])
        rows.append(verdict_row(f'P21 CME 공백 메우기 {sym[:3]}', R, T, start, END, 2))
    show(rows, 'P21 CME 주말 공백', 2)
    return rows


# ── P22 추정 청산 지도 ────────────────────────────────────────────────
@njit(cache=False)
def liq_map_signals(p5, h5, l5, oi, ls, hour_end, step_decay, bin_w, lo_ln, nb):
    """5분마다 지도를 갱신하고, 1h 마감(hour_end=True) 마다 A(위 숏 청산 물량)·B(아래 롱 청산 물량)를 기록."""
    longm = np.zeros(nb)
    shortm = np.zeros(nb)
    levs = np.array([10.0, 25.0, 50.0, 100.0])
    wts = np.array([0.4, 0.3, 0.2, 0.1])
    n = len(p5)
    A = np.full(n, np.nan)
    B = np.full(n, np.nan)
    for t in range(1, n):
        if not (p5[t] > 0) or not (oi[t] > 0) or not (oi[t - 1] > 0):
            continue
        for b in range(nb):
            longm[b] *= step_decay
            shortm[b] *= step_decay
        d = oi[t] - oi[t - 1]
        if d > 0:
            s = ls[t] / (1.0 + ls[t]) if ls[t] > 0 else 0.5
            for k in range(4):
                pl = p5[t] * (1.0 - 1.0 / levs[k] + 0.005)
                ps = p5[t] * (1.0 + 1.0 / levs[k] - 0.005)
                bl = int((math.log(pl) - lo_ln) / bin_w)
                bs = int((math.log(ps) - lo_ln) / bin_w)
                if 0 <= bl < nb:
                    longm[bl] += d * s * wts[k]
                if 0 <= bs < nb:
                    shortm[bs] += d * (1.0 - s) * wts[k]
        elif d < 0:
            r = oi[t] / oi[t - 1]
            for b in range(nb):
                longm[b] *= r
                shortm[b] *= r
        # 닿은 칸은 청산됨
        bl_low = int((math.log(l5[t]) - lo_ln) / bin_w)
        bh_high = int((math.log(h5[t]) - lo_ln) / bin_w)
        for b in range(max(bl_low, 0), nb):
            longm[b] = 0.0
        for b in range(0, min(bh_high + 1, nb)):
            shortm[b] = 0.0
        if hour_end[t]:
            bp = (math.log(p5[t]) - lo_ln) / bin_w
            up0, up1 = int(bp + math.log(1.005) / bin_w), int(bp + math.log(1.05) / bin_w)
            dn0, dn1 = int(bp + math.log(0.95) / bin_w), int(bp + math.log(0.995) / bin_w)
            a_ = 0.0
            for b in range(max(up0 + 1, 0), min(up1 + 1, nb)):
                a_ += shortm[b]
            b_ = 0.0
            for b in range(max(dn0, 0), min(dn1, nb)):
                b_ += longm[b]
            A[t] = a_
            B[t] = b_
    return A, B


def run_p22():
    rows = []
    for sym, start in (('BTCUSDT', '2020-10-01'), ('ETHUSDT', '2022-01-01')):
        if sym == 'BTCUSDT':
            fr = btc_frames(('5m', '1h'))
            d5, d1 = fr['5m'], fr['1h']
        else:
            d5, d1 = eth_frame('5m'), eth_frame('1h')
        m = metrics(sym)
        close_t = (d5.index + pd.Timedelta(minutes=5)).values.astype('datetime64[ns]')
        oi = pe._metrics_at(m, 'oi', close_t)
        ls = pe._metrics_at(m, 'ls_acct', close_t)
        p5, h5, l5 = (d5[k].values.astype(np.float64) for k in ('close', 'high', 'low'))
        hour_end = ((d5.index + pd.Timedelta(minutes=5)).minute == 0)
        lo_ln = math.log(max(np.nanmin(l5[l5 > 0]) * 0.5, 1e-9))
        bin_w = math.log(1.0025)
        nb = int((math.log(np.nanmax(h5) * 2.0) - lo_ln) / bin_w) + 2
        step_decay = math.exp(-math.log(2) * 5.0 / (7 * 24 * 60))
        A, B = liq_map_signals(p5, h5, l5, np.nan_to_num(oi), np.nan_to_num(ls), np.asarray(hour_end, dtype=np.bool_),
                               step_decay, bin_w, lo_ln, nb)
        # 1h 봉에 붙이기: 1h 봉 마감 = 5분 봉 마감이 정시인 그 시각
        t_hour = (d5.index + pd.Timedelta(minutes=5))[hour_end]
        sA = pd.Series(A[hour_end], index=t_hour - pd.Timedelta(hours=1))
        sB = pd.Series(B[hour_end], index=t_hour - pd.Timedelta(hours=1))
        a1, b1 = sA.reindex(d1.index).values, sB.reindex(d1.index).values
        ind = pe._lab_indicators(d1)
        o, h, l, c = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l', 'c'))
        atr = np.nan_to_num(ind['atr'].values) * c
        side = np.zeros(len(c), dtype=np.int64)
        ok = np.isfinite(a1) & np.isfinite(b1) & ((a1 + b1) > 0)
        side[ok & (a1 > 2 * b1)] = 1
        side[ok & (b1 > 2 * a1)] = -1
        stop = c - side * 1.5 * atr
        i0, i1 = period_idx(d1.index, start, END)
        e, R = sim_sig_stop(o, h, l, c, side, stop, 24, COST, i0, i1)
        print(f'  {sym}: 지도 신호 봉 롱 {int((side[i0:i1] > 0).sum())} · 숏 {int((side[i0:i1] < 0).sum())}')
        rows.append(verdict_row(f'P22 청산 지도 {sym[:3]}', R, d1.index.values[e], start, END, 2))
    show(rows, 'P22 추정 청산 지도', 2)
    return rows


# ── P23 P16 확장 ─────────────────────────────────────────────────────
def crowd_z(df, m, tf_min):
    idx = df.index
    ind = pe._lab_indicators(df)
    c = ind['c'].values.astype(np.float64)
    atrp = ind['atr'].values.astype(np.float64)
    close_t = (idx + pd.Timedelta(minutes=tf_min)).values.astype('datetime64[ns]')
    ls = pe._metrics_at(m, 'ls_acct', close_t)
    brk_up = (c - ind['h'].rolling(20).max().shift(1).values) / (atrp * c)
    brk_dn = (ind['l'].rolling(20).min().shift(1).values - c) / (atrp * c)
    return pe._z_prev(ls), pe._z_prev(brk_up), pe._z_prev(brk_dn), atrp


def run_p23():
    rows = []
    for sym, start in (('BTCUSDT', '2021-01-01'), ('ETHUSDT', '2022-01-01')):
        df = frame(sym, '1h')
        zl, zu, zd, atrp = crowd_z(df, metrics(sym), 60)
        sig = (np.nan_to_num(zl, nan=0) > 1.0) & (np.nan_to_num(zd, nan=0) > 2.0)
        o, h, l, c = (df[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close'))
        i0, i1 = period_idx(df.index, start, END)
        e, R = pe._fixed_stop_hold_sim(o, h, l, c, sig, np.nan_to_num(atrp), 1.5, 48, -1, COST, i0, i1)
        rows.append(verdict_row(f'P23-A 거울(숏) {sym[:3]} 1h', R, df.index.values[e], start, END, 4))
    m = metrics('ETHUSDT')
    for tf, tf_min in (('15m', 15), ('4h', 240)):
        df = eth_frame(tf) if tf == '15m' else eth_4h()
        zl, zu, zd, atrp = crowd_z(df, m, tf_min)
        sig = (np.nan_to_num(zl, nan=0) < -1.0) & (np.nan_to_num(zu, nan=0) > 2.0)
        o, h, l, c = (df[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close'))
        i0, i1 = period_idx(df.index, '2022-01-01', END)
        e, R = pe._fixed_stop_hold_sim(o, h, l, c, sig, np.nan_to_num(atrp), 1.5, 48, 1, COST, i0, i1)
        rows.append(verdict_row(f'P23-B P16 규칙 ETH {tf}', R, df.index.values[e], '2022-01-01', END, 4))
    show(rows, 'P23 P16 확장 (거울 · 다른 시간봉)', 4)
    return rows


if __name__ == '__main__':
    pe.Paths.init()
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    runs = dict(p18=run_p18, p19=run_p19, p20=run_p20, p21=run_p21, p22=run_p22, p23=run_p23)
    for k, f in runs.items():
        if what in (k, 'all'):
            f()
