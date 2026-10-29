"""
6차 사전등록 P30 ~ P38 (RESEARCH_LOG, 2026-10-29 커밋 = 계산 전) — 이름을 남긴 단타·스윙 고수의 규칙을 그대로 옮긴다.
6A 알트 횡단면 (그날그날 20일 평균 거래대금 상위 100 · 상장 폐지 포함 · BTC·ETH·스테이블·지수 제외 · 왕복 0.2% + 실제 펀딩):
   P30 쿨라마기 돌파 · P31 쿨라마기 에피소딕 피벗 · P32 쿨라마기 포물선 공매도 · P33 BNF 25일 이격도
6B BTC·ETH (왕복 0.12%): P34 크래블 NR7 시가 범위 돌파(5m) · P35 코너스 RSI(2) 일봉 · P36 라쉬키 홀리 그레일 4h ·
   P37 자라티니 소음 영역 일중 모멘텀 · P38 일중 시계열 모멘텀(첫 30분 → 마지막 30분)
판정은 3차와 같다 (거래 ≥ 30 · 평균 ≤ 0 → 반증 · 두 반쪽 > 0 이고 달 묶음 단측 5%/k 하한 > 0 → 확인 · 그 외 반증 안 됨). k 는 가족마다.
실행: python research/round6_2026-10-29.py [6a|6b|all|p38]   (먼저 research/r6_data_2026-10-29.py [spot])
"""
import importlib
import io
import os
import sys
import time
import urllib.request
import zipfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import pattern_edge_v612 as pe  # noqa: E402

r3 = importlib.import_module('round3_2026-10-15')
njit = r3.njit
HOME = r3.HOME
R6 = os.path.join(HOME, 'r6')

# ── 6A 사전등록 숫자 ───────────────────────────────────────────────
A_START, A_END = '2020-06-01', '2026-09-30'
A_COST = 0.002
A_K = 4
EXCLUDE = {'BTCUSDT', 'ETHUSDT', 'USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'USDPUSDT', 'FDUSDUSDT', 'BTCDOMUSDT', 'DEFIUSDT',
           'FOOTBALLUSDT', 'BLUEBIRDUSDT'}
TOP_N, MIN_QV, MIN_HIST = 100, 5e6, 120
Q_TOP, Q_MOVE, Q_TIGHT = 0.05, 0.30, 2.5           # 상위 5% · 30% 이상 움직임 · 10일 폭 ≤ 2.5 ADR
Q_PARTIAL, Q_CAP = 3, 120                          # 3일째 종가에 절반, 나머지 10일선 종가 이탈
EP_RET, EP_VOL, EP_PRIOR = 0.20, 5.0, 0.20         # 하루 +20% · 거래대금 5배 · 직전 63일 +20% 이하
PARA_RET, PARA_CAP = 0.50, 10                      # 5일 +50%(대형주 기준 하한) · 3일 연속 상승 → 다음 날 첫 1h 저가 이탈 공매도
BNF_DEV, BNF_HOLD = -0.25, 10                      # 25일선 −25% 이하 → 다음 날 시가, 25일선 닿는 종가 또는 10일째

# ── 6B 사전등록 숫자 ───────────────────────────────────────────────
B_END = '2026-10-04'
B_COST = r3.COST
B_K = 9
NOISE_LB, NOISE_TGT, NOISE_LEV = 14, 0.02, 4.0       # 자라티니: 14일 소음 · 하루 변동성 목표 2% · 최대 4배


def qtime(day):
    return np.datetime64(pd.Timestamp(day))


# ═════════════════════════════════ 6A 알트 ═════════════════════════════════
def alt_panel():
    df = pd.read_parquet(os.path.join(R6, 'alts_1d.parquet'))
    df = df[~df['symbol'].isin(EXCLUDE)]
    days = pd.date_range(df['date'].min(), df['date'].max(), freq='D')
    W = {k: df.pivot(index='date', columns='symbol', values=k).reindex(days).astype(np.float64)
         for k in ('open', 'high', 'low', 'close', 'qvol')}
    return W


def universe(W):
    C, H, L, QV = W['close'], W['high'], W['low'], W['qvol']
    valid = C.notna()
    hist = valid.astype(float).rolling(MIN_HIST, min_periods=1).sum() >= MIN_HIST
    aqv = QV.rolling(20, min_periods=20).mean()
    rng = (H / L - 1).rolling(60, min_periods=20).median()
    ok = valid & hist & (aqv >= MIN_QV) & (rng >= 0.004)
    rank = aqv.where(ok).rank(axis=1, ascending=False, method='first')
    return ok & (rank <= TOP_N)


def top_frac(X, U, frac):
    Xu = X.where(U)
    k = np.ceil(frac * U.sum(axis=1)).clip(lower=1)
    rk = Xu.rank(axis=1, ascending=False, method='first')
    return rk.le(k, axis=0) & U


def funding_series(sym, cache={}):
    if sym not in cache:
        f = os.path.join(HOME, 'raw', 'funding_all', f'{sym}.csv')
        s = pd.Series(dtype=np.float64)
        if os.path.exists(f):
            d = pd.read_csv(f)
            if len(d):
                s = pd.Series(d['last_funding_rate'].values.astype(np.float64),
                              index=pd.to_datetime(d['calc_time'].values.astype(np.int64), unit='ms')).sort_index()
        cache[sym] = s
    return cache[sym]


def funding_paid(sym, t0, t_half, t1, w_after):
    """t0 ~ t_half 는 전량, t_half ~ t1 은 w_after 만큼. 양수 = 롱이 낸 비율(가격 대비)."""
    s = funding_series(sym)
    if not len(s):
        return 0.0
    a = s[(s.index > t0) & (s.index <= t_half)].sum()
    b = s[(s.index > t_half) & (s.index <= t1)].sum() if t1 > t_half else 0.0
    return float(a + w_after * b)


def hours_of(sym, day):
    """그날의 1h 봉(바이낸스 아카이브 월 파일, 캐시). 없으면 None."""
    ym = f'{day:%Y-%m}'
    folder = os.path.join(R6, 'raw_1h')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f'{sym}_{ym}.pkl')
    if not os.path.exists(path):
        url = f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/1h/{sym}-1h-{ym}.zip'
        d = pd.DataFrame(columns=['open', 'high', 'low', 'close'])
        for k in range(4):
            try:
                raw = urllib.request.urlopen(url, timeout=60).read()
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    with z.open(z.namelist()[0]) as f:
                        x = pd.read_csv(f, header=None)
                if not str(x.iloc[0, 0]).isdigit():
                    x = x.iloc[1:]
                x = x.iloc[:, :5].astype(float)
                x.columns = ['t', 'open', 'high', 'low', 'close']
                t = x['t'].astype('int64')
                x.index = pd.to_datetime(t.where(t < 1e14, t // 1000), unit='ms')
                d = x[['open', 'high', 'low', 'close']]
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    break
                time.sleep(1 + k)
            except Exception:
                time.sleep(1 + k)
        d.to_pickle(path)
    d = pd.read_pickle(path)
    if not len(d):
        return None
    d = d[(d.index >= day) & (d.index < day + pd.Timedelta(days=1))]
    return d if len(d) else None


def entry_day_stopped(hb, side, lv, s0):
    """진입 날 1h 경로: 역지정가 lv 에 들어간 뒤 같은 날 손절 s0 에 닿았나. 진입 봉 안의 순서는 모르면 닿은 것으로(보수)."""
    if hb is None:
        return None
    entered = False
    for o, h, l in zip(hb['open'].values, hb['high'].values, hb['low'].values):
        if not entered:
            if (side > 0 and h >= lv) or (side < 0 and l <= lv):
                entered = True
                if (side > 0 and l <= s0) or (side < 0 and h >= s0):
                    return True
            continue
        if (side > 0 and l <= s0) or (side < 0 and h >= s0):
            return True
    return False if entered else None


def run_long(A, j, k0, e, s0, partial=Q_PARTIAL, cap=Q_CAP):
    """진입 날(k0) 다음 날부터: 손절 → 3일째 종가 절반·본전 손절 → 10일선 종가 이탈. 반환 [(비중, 가격, 날)]."""
    O, H, L, C, S10 = A['O'], A['H'], A['L'], A['C'], A['S10']
    fills, w, stop, last = [], 1.0, s0, k0
    for k in range(k0 + 1, min(k0 + cap, C.shape[0])):
        c = C[k, j]
        if c != c:
            break
        last = k
        o, l = O[k, j], L[k, j]
        if l <= stop:
            fills.append((w, o if o < stop else stop, k))
            return fills
        d = k - k0
        if d == partial:
            fills.append((0.5, c, k))
            w, stop = 0.5, max(stop, e)
            continue
        if d > partial and c < S10[k, j]:
            fills.append((w, c, k))
            return fills
    fills.append((w, C[last, j], last))
    return fills


def run_bnf(A, j, k0, hold=BNF_HOLD):
    """BNF: 25일선 근처(종가 ≥ 25일선)까지 되돌리면 그 종가, 아니면 10일째 종가. 손절 없음."""
    C, S25 = A['C'], A['S25']
    last = k0
    for k in range(k0, min(k0 + hold, C.shape[0])):
        c = C[k, j]
        if c != c:
            break
        last = k
        if c >= S25[k, j]:
            return [(1.0, c, k)]
    return [(1.0, C[last, j], last)]


def para_entry(hb, s10_prev):
    """포물선 공매도 진입 날 1h: 첫 1h 봉 저가(시가 범위 저가) 이탈에 진입, 손절 = 그때까지 고가(진입 봉 포함),
    같은 날 남은 시간에 손절·목표(전날 10일선) 확인. 반환 (진입가, 손절, 결과) — 결과 None = 그날 안 끝남, 진입 없으면 None."""
    if hb is None or len(hb) < 2:
        return None
    o, h, l = hb['open'].values, hb['high'].values, hb['low'].values
    orl = l[0]
    for i in range(1, len(o)):
        if l[i] < orl:
            e = min(o[i], orl)
            st = h[:i + 1].max()
            if not (st > e):
                return None
            if s10_prev == s10_prev and l[i] <= s10_prev < e:
                return e, st, s10_prev
            for k in range(i + 1, len(o)):
                if h[k] >= st:
                    return e, st, (o[k] if o[k] > st else st)
                if s10_prev == s10_prev and l[k] <= s10_prev:
                    return e, st, (o[k] if o[k] < s10_prev else s10_prev)
            return e, st, None
    return None


def run_para_short(A, j, k0, e, s0, cap=PARA_CAP):
    O, H, L, C, S10 = A['O'], A['H'], A['L'], A['C'], A['S10']
    last = k0
    for k in range(k0 + 1, min(k0 + cap + 1, C.shape[0])):
        c = C[k, j]
        if c != c:
            break
        last = k
        o, h, l = O[k, j], H[k, j], L[k, j]
        if h >= s0:
            return [(1.0, o if o > s0 else s0, k)]
        tgt = S10[k - 1, j]
        if tgt == tgt and l <= tgt:
            return [(1.0, o if o < tgt else tgt, k)]
    return [(1.0, C[last, j], last)]


def trade_R(sym, side, e, s0, fills, days, k0, partial_day=None):
    risk = abs(e - s0)
    pnl = sum(w * side * (p - e) for w, p, _ in fills)
    t0 = days[k0]
    t1 = days[max(k for _, _, k in fills)] + pd.Timedelta(days=1)
    if partial_day is not None and len(fills) > 1:
        th = days[fills[0][2]] + pd.Timedelta(days=1)
        fund = funding_paid(sym, t0, th, t1, 0.5)
    else:
        fund = funding_paid(sym, t0, t1, t1, 0.0)
    return (pnl - A_COST * e - side * fund * e) / risk


def alt_arrays(W):
    C = W['close']
    return dict(O=W['open'].values, H=W['high'].values, L=W['low'].values, C=C.values,
                S10=C.rolling(10).mean().values, S5=C.rolling(5).mean().values, S25=C.rolling(25).mean().values)


def run_6a():
    W = alt_panel()
    U = universe(W)
    O, H, L, C, QV = (W[k] for k in ('open', 'high', 'low', 'close', 'qvol'))
    days, syms = C.index, list(C.columns)
    A = alt_arrays(W)
    sma10, sma20, sma25 = C.rolling(10).mean(), C.rolling(20).mean(), C.rolling(25).mean()
    adr = (H / L - 1).rolling(20).mean()
    r21, r63 = C / C.shift(21) - 1, C / C.shift(63) - 1
    hh10, ll10 = H.rolling(10).max(), L.rolling(10).min()
    k_a, k_b = int(days.searchsorted(pd.Timestamp(A_START))), int(days.searchsorted(pd.Timestamp(A_END)) + 1)
    n_u = U.iloc[k_a:k_b].sum(axis=1)
    print(f'유니버스: 하루 평균 {n_u.mean():.0f}종목 (최소 {n_u.min()} · 최대 {n_u.max()}), 거쳐 간 종목 {int(U.iloc[k_a:k_b].any().sum())}개')
    rows = []

    # P30 쿨라마기 돌파
    mom = (top_frac(r21, U, Q_TOP) & (r21 >= Q_MOVE)) | (top_frac(r63, U, Q_TOP) & (r63 >= Q_MOVE))
    setup = (mom & (C > sma10) & (sma10 > sma20) & ((hh10 - ll10) / C <= Q_TIGHT * adr)).values
    R, T, busy = [], [], np.full(len(syms), -1)
    hh, ad = hh10.values, adr.values
    n1h = [0, 0]
    for t in range(max(k_a - 1, 0), k_b - 1):
        for j in np.flatnonzero(setup[t]):
            k0 = t + 1
            if busy[j] >= k0 or not (A['H'][k0, j] >= hh[t, j]):
                continue
            lv = hh[t, j]
            e = max(A['O'][k0, j], lv)
            s0 = e * (1 - ad[t, j])
            st = entry_day_stopped(hours_of(syms[j], days[k0]), 1, lv, s0)
            n1h[st is None] += 1
            if st is None:
                st = A['L'][k0, j] <= s0
            fills = [(1.0, s0, k0)] if st else run_long(A, j, k0, e, s0)
            busy[j] = max(k for _, _, k in fills)
            R.append(trade_R(syms[j], 1, e, s0, fills, days, k0, partial_day=Q_PARTIAL))
            T.append(qtime(days[k0]))
    print(f'  P30 진입 날 경로: 1h 로 판정 {n1h[0]}건 · 1h 없음(최악 가정) {n1h[1]}건')
    rows.append(r3.verdict_row('P30 쿨라마기 돌파 (알트)', R, T, A_START, A_END, A_K))

    # P31 에피소딕 피벗
    ep = ((C / C.shift(1) - 1 >= EP_RET) & (QV / QV.shift(1).rolling(20).mean() >= EP_VOL)
          & (C.shift(1) / C.shift(64) - 1 <= EP_PRIOR) & U.shift(1, fill_value=False)).values
    R, T, busy = [], [], np.full(len(syms), -1)
    for t in range(max(k_a - 1, 0), k_b - 1):
        for j in np.flatnonzero(ep[t]):
            k0 = t + 1
            e, s0 = A['O'][k0, j], A['L'][t, j]
            if busy[j] >= k0 or not (e > s0) or e != e:
                continue
            fills = [(1.0, s0, k0)] if A['L'][k0, j] <= s0 else run_long(A, j, k0, e, s0)
            busy[j] = max(k for _, _, k in fills)
            R.append(trade_R(syms[j], 1, e, s0, fills, days, k0, partial_day=Q_PARTIAL))
            T.append(qtime(days[k0]))
    rows.append(r3.verdict_row('P31 쿨라마기 에피소딕 피벗 (알트)', R, T, A_START, A_END, A_K))

    # P32 포물선 공매도 (진입 날은 1h: 첫 1h 저가 이탈 · 손절 = 진입 때까지 고가 · 목표 = 전날 10일선)
    up3 = (C > C.shift(1)) & (C.shift(1) > C.shift(2)) & (C.shift(2) > C.shift(3))
    para = ((C / C.shift(5) - 1 >= PARA_RET) & up3 & U.shift(5, fill_value=False)).values
    R, T, busy = [], [], np.full(len(syms), -1)
    n_no1h = 0
    for t in range(max(k_a - 1, 0), k_b - 1):
        for j in np.flatnonzero(para[t]):
            k0 = t + 1
            if busy[j] >= k0 or A['C'][k0, j] != A['C'][k0, j]:
                continue
            hb = hours_of(syms[j], days[k0])
            if hb is None:
                n_no1h += 1
                continue
            got = para_entry(hb, A['S10'][t, j])
            if got is None:
                continue
            e, s0, px = got
            fills = [(1.0, px, k0)] if px is not None else run_para_short(A, j, k0, e, s0)
            busy[j] = max(k for _, _, k in fills)
            R.append(trade_R(syms[j], -1, e, s0, fills, days, k0))
            T.append(qtime(days[k0]))
    print(f'  P32 1h 없음(건너뜀) {n_no1h}건')
    rows.append(r3.verdict_row('P32 쿨라마기 포물선 공매도 (알트)', R, T, A_START, A_END, A_K))

    # P33 BNF 25일 이격도 (손절 없음 → R = 순수익 ÷ ADR20)
    bnf = ((C / sma25 - 1 <= BNF_DEV) & U).values
    R, T, busy = [], [], np.full(len(syms), -1)
    for t in range(max(k_a - 1, 0), k_b - 1):
        for j in np.flatnonzero(bnf[t]):
            k0 = t + 1
            e = A['O'][k0, j]
            if busy[j] >= k0 or e != e:
                continue
            fills = run_bnf(A, j, k0)
            kx = fills[0][2]
            busy[j] = kx
            t1 = days[kx] + pd.Timedelta(days=1)
            fund = funding_paid(syms[j], days[k0], t1, t1, 0.0)
            R.append((fills[0][1] - e - A_COST * e - fund * e) / (ad[t, j] * e))
            T.append(qtime(days[k0]))
    rows.append(r3.verdict_row('P33 BNF 25일 이격도 (알트)', R, T, A_START, A_END, A_K))
    r3.show(rows, '6A 알트 횡단면 — 쿨라마기·BNF', A_K)
    return rows


# ═════════════════════════════════ 6B BTC·ETH ═════════════════════════════════
def majors():
    quiet = lambda *a, **k: None  # noqa: E731
    h = pe.PublicHttp()
    out = {}
    b = r3.btc_frames(('5m', '4h'))
    base = pd.read_parquet(os.path.join(HOME, 'BTCUSDT_1m_v612.parquet'))
    base = base[base.index < pd.Timestamp('2026-10-15')]
    bd = base[['open', 'high', 'low', 'close']].resample('1D').agg(dict(open='first', high='max', low='min', close='last')).dropna()
    out['BTCUSDT'] = dict(m5=b['5m'], h4=b['4h'], d1=bd, start='2019-09-10')
    e5 = pe.normalize_frame(pe.fetch_futures_klines_vision(h, 'ETHUSDT', '5m', start='2019-11', log=quiet))
    e4 = pe.normalize_frame(pe.fetch_futures_klines_vision(h, 'ETHUSDT', '4h', start='2019-11', log=quiet))
    e1 = r3.eth_frame('1h')
    ed = e1[['open', 'high', 'low', 'close']].resample('1D').agg(dict(open='first', high='max', low='min', close='last')).dropna()
    out['ETHUSDT'] = dict(m5=e5, h4=e4, d1=ed, start='2019-12-01')
    return out


def day_bounds(idx):
    d = idx.floor('D')
    starts = np.flatnonzero(np.r_[True, d[1:] != d[:-1]])
    ends = np.r_[starts[1:], len(idx)]
    return d[starts], starts, ends


@njit(cache=False)
def orb_one(o, h, l, c, a, b, up, dn, cost):
    """양쪽 역지정가: 먼저 닿은 쪽으로, 반대쪽이 손절, 그날 마지막 봉 종가 청산. 같은 봉 양쪽 = 최악. (R, 방향)"""
    side, entry, stop = 0, 0.0, 0.0
    for j in range(a, b):
        if side == 0:
            hu, hd = h[j] >= up, l[j] <= dn
            if not (hu or hd):
                continue
            if hu and hd:
                return (dn / up - 1.0 - cost) / ((up - dn) / up), 1
            if hu:
                side, entry, stop = 1, max(o[j], up), dn
                if l[j] <= stop:
                    return ((stop / entry - 1.0) - cost) / ((entry - stop) / entry), 1
            else:
                side, entry, stop = -1, min(o[j], dn), up
                if h[j] >= stop:
                    return ((1.0 - stop / entry) - cost) / ((stop - entry) / entry), -1
            continue
        if side > 0 and l[j] <= stop:
            px = o[j] if o[j] < stop else stop
            return ((px / entry - 1.0) - cost) / ((entry - stop) / entry), 1
        if side < 0 and h[j] >= stop:
            px = o[j] if o[j] > stop else stop
            return ((1.0 - px / entry) - cost) / ((stop - entry) / entry), -1
    if side == 0:
        return np.nan, 0
    px = c[b - 1]
    return ((side * (px / entry - 1.0)) - cost) / (abs(entry - stop) / entry), side


def p34_crabel(m5, d1, start, end):
    rng = d1['high'] - d1['low']
    nr7 = (rng <= rng.rolling(7).min()).values
    stretch = np.minimum(d1['high'] - d1['open'], d1['open'] - d1['low']).rolling(10).mean().values
    dd = d1.index
    o, h, l, c = (m5[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    days, a_, b_ = day_bounds(m5.index)
    pos = {d: i for i, d in enumerate(days)}
    R, T = [], []
    for i in range(1, len(dd)):
        if not nr7[i - 1] or not (stretch[i - 1] > 0) or dd[i] < pd.Timestamp(start) or dd[i] >= pd.Timestamp(end):
            continue
        k = pos.get(dd[i])
        if k is None or b_[k] - a_[k] < 200:
            continue
        op = o[a_[k]]
        r, sd = orb_one(o, h, l, c, a_[k], b_[k], op + stretch[i - 1], op - stretch[i - 1], B_COST)
        if sd != 0 and r == r:
            R.append(r)
            T.append(qtime(dd[i]))
    return R, T


def rsi(c, n):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def p35_connors(d1, start, end, lo=10.0):
    c = d1['close'].astype(np.float64)
    s200, s5, r2 = c.rolling(200).mean().values, c.rolling(5).mean().values, rsi(c, 2).values
    atr = pe._lab_indicators(d1.assign(volume=0.0, taker_buy_base=0.0))['atr'].values
    cv, idx = c.values, d1.index
    i0, i1 = int(idx.searchsorted(pd.Timestamp(start))), int(idx.searchsorted(pd.Timestamp(end)))
    R, T, i = [], [], max(i0, 200)
    while i < i1 - 1:
        sd = 1 if (cv[i] > s200[i] and r2[i] < lo) else 0          # 책 규칙: 롱만
        if sd == 0:
            i += 1
            continue
        j = i + 1
        while j < i1 - 1 and not ((sd > 0 and cv[j] > s5[j]) or (sd < 0 and cv[j] < s5[j])):
            j += 1
        R.append((sd * (cv[j] / cv[i] - 1) - B_COST) / atr[i])
        T.append(qtime(idx[i]))
        i = j + 1
    return R, T


def adx(df, n=14):
    h, l, c = (df[k].astype(np.float64) for k in ('high', 'low', 'close'))
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    pc = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * mdm.ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=1 / n, adjust=False).mean().values, pdi.values, mdi.values


def p36_holy_grail(h4, start, end, adx_min=30.0, swing=20, tmax=30):
    o, h, l, c = (h4[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    ema = h4['close'].ewm(span=20, adjust=False).mean().values
    ax, pdi, mdi = adx(h4)
    idx = h4.index
    i0, i1 = int(idx.searchsorted(pd.Timestamp(start))), int(idx.searchsorted(pd.Timestamp(end)))
    R, T, i = [], [], max(i0, 60)
    while i < i1 - 2:
        sd = 0
        if ax[i] > adx_min and ax[i] > ax[i - 1]:
            if pdi[i] > mdi[i] and l[i] <= ema[i]:
                sd, lv, st, tg = 1, h[i], l[i], h[i - swing:i].max()
            elif mdi[i] > pdi[i] and h[i] >= ema[i]:
                sd, lv, st, tg = -1, l[i], h[i], l[i - swing:i].min()
        if sd == 0 or not ((sd > 0 and tg > lv) or (sd < 0 and tg < lv)):
            i += 1
            continue
        e = i + 1
        if not ((sd > 0 and h[e] >= lv) or (sd < 0 and l[e] <= lv)):
            i += 1
            continue
        entry = max(o[e], lv) if sd > 0 else min(o[e], lv)
        if (sd > 0 and entry <= st) or (sd < 0 and entry >= st) or (sd > 0 and entry >= tg) or (sd < 0 and entry <= tg):
            i += 1
            continue
        px, xi = c[min(e + tmax - 1, i1 - 1)], min(e + tmax - 1, i1 - 1)
        for j in range(e, xi + 1):
            if (sd > 0 and l[j] <= st) or (sd < 0 and h[j] >= st):
                px = st if j == e else ((o[j] if o[j] < st else st) if sd > 0 else (o[j] if o[j] > st else st))
                xi = j
                break
            if (sd > 0 and h[j] >= tg) or (sd < 0 and l[j] <= tg):
                px, xi = tg, j
                break
        R.append((sd * (px / entry - 1) - B_COST) / (abs(entry - st) / entry))
        T.append(qtime(idx[e]))
        i = xi + 1
    return R, T


def run_6b():
    rows = []
    M = majors()
    for sym, m in M.items():
        R, T = p34_crabel(m['m5'], m['d1'], m['start'], B_END)
        rows.append(r3.verdict_row(f'P34 크래블 NR7 시가 범위 돌파 {sym[:3]}', R, T, m['start'], B_END, B_K))
    R, T = [], []
    for sym, m in M.items():
        r_, t_ = p35_connors(m['d1'], '2019-12-01', B_END)
        R += r_
        T += t_
    rows.append(r3.verdict_row('P35 코너스 RSI(2) 일봉 BTC+ETH', R, T, '2019-12-01', B_END, B_K))
    for sym, m in M.items():
        R, T = p36_holy_grail(m['h4'], m['start'], B_END)
        rows.append(r3.verdict_row(f'P36 라쉬키 홀리 그레일 4h {sym[:3]}', R, T, m['start'], B_END, B_K))
    rows += run_6b_intraday(M)
    r3.show(rows, '6B BTC·ETH 고전 단타', B_K)
    return rows


def sessions(m5, clock):
    """(날짜, 첫 봉, 끝 봉+1, 직전 세션 종가). utc = 00:00 UTC 하루(288봉), us = 뉴욕 9:30~16:00 평일(78봉, 서머타임 반영)."""
    idx = m5.index
    c = m5['close'].values
    out = []
    if clock == 'utc':
        days, a_, b_ = day_bounds(idx)
        for d, a, b in zip(days, a_, b_):
            if b - a == 288 and a > 0:
                out.append((d, a, b, c[a - 1]))
        return out
    ny = idx.tz_localize('UTC').tz_convert('America/New_York')
    mins = (ny.hour * 60 + ny.minute).values
    inside = (mins >= 570) & (mins < 960) & (ny.dayofweek.values < 5)
    dkey = ny.normalize().tz_localize(None).values
    prev = None
    i, n = 0, len(idx)
    while i < n:
        if not inside[i]:
            i += 1
            continue
        j = i
        while j < n and inside[j] and dkey[j] == dkey[i]:
            j += 1
        if j - i == 78 and prev is not None:
            out.append((pd.Timestamp(dkey[i]), i, j, prev))
        if j - i == 78:
            prev = c[j - 1]
        i = j
    return out


def p37_noise(m5, d1, start, end, clock):
    """자라티니·아지즈·바르본(2024) 소음 영역: 30분마다 가격 > max(위 경계, VWAP) 롱 · < min(아래 경계, VWAP) 숏 · 그 사이 0,
    세션 끝 청산. 경계 = max/min(시가, 직전 종가) × (1 ± σ), σ = 직전 14세션 같은 시각 |가격/시가 − 1| 평균.
    크기 = min(4, 2% ÷ 직전 14일 일간 변동성). 관측 = 포지션이 있었던 세션의 손익 ÷ 2%(목표 변동성 단위)."""
    o, h, l, c, v = (m5[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close', 'volume'))
    tp = (h + l + c) / 3.0
    S = sessions(m5, clock)
    nb = 288 if clock == 'utc' else 78
    marks = np.arange(6, nb - 5, 6)
    move = np.array([[abs(c[a + m - 1] / o[a] - 1.0) for m in marks] for (_, a, b, _) in S])
    dret = d1['close'].pct_change()
    vol14 = dret.rolling(NOISE_LB).std().shift(1)
    side_cost = B_COST / 2.0
    R, T = [], []
    for s_i in range(NOISE_LB, len(S)):
        d, a, b, pc = S[s_i]
        if d < pd.Timestamp(start) or d >= pd.Timestamp(end):
            continue
        sv = vol14.get(d.normalize())
        if sv is None or not (sv > 0):
            continue
        lev = min(NOISE_LEV, NOISE_TGT / sv)
        sig = move[s_i - NOISE_LB:s_i].mean(axis=0)
        op = o[a]
        ub, lb = max(op, pc) * (1 + sig), min(op, pc) * (1 - sig)
        cpv, cv_ = np.cumsum(tp[a:b] * v[a:b]), np.cumsum(v[a:b])
        pos_prev, pnl, any_pos = 0, 0.0, False
        for k, m in enumerate(marks):
            p = c[a + m - 1]
            vw = cpv[m - 1] / cv_[m - 1] if cv_[m - 1] > 0 else p
            pos = 1 if p > max(ub[k], vw) else (-1 if p < min(lb[k], vw) else 0)
            pnl -= side_cost * lev * abs(pos - pos_prev)
            nxt = c[a + marks[k + 1] - 1] if k + 1 < len(marks) else c[b - 1]
            pnl += pos * lev * (nxt / p - 1.0)
            any_pos |= pos != 0
            pos_prev = pos
        pnl -= side_cost * lev * abs(pos_prev)
        if any_pos:
            R.append(pnl / NOISE_TGT)
            T.append(qtime(d))
    return R, T


def run_6b_intraday(M):
    rows = []
    for clock, nm in (('utc', '00:00 UTC 하루'), ('us', '뉴욕 정규장')):
        for sym, m in M.items():
            R, T = p37_noise(m['m5'], m['d1'], m['start'], B_END, clock)
            rows.append(r3.verdict_row(f'P37 소음 영역 {nm} {sym[:3]}', R, T, m['start'], B_END, B_K))
    return rows


# ═════════════════════ P38 재현: P33 을 2018~2019 현물 알트에서 (어떤 시험에도 안 쓴 기간) ═════════════════════
P38_START, P38_END = '2018-01-01', '2019-12-31'
SPOT_EXCLUDE = {'PAXUSDT', 'USDSUSDT', 'USDSBUSDT', 'BKRWUSDT', 'EURUSDT', 'GBPUSDT', 'AUDUSDT', 'BGBPUSDT', 'IDRTUSDT', 'DAIUSDT'}


def spot_panel():
    df = pd.read_parquet(os.path.join(R6, 'spot_1d_2017_2019.parquet'))
    df = df[~df['symbol'].isin(EXCLUDE | SPOT_EXCLUDE) & ~df['symbol'].str.contains(r'(?:UP|DOWN|BULL|BEAR)USDT$', regex=True)]
    days = pd.date_range(df['date'].min(), df['date'].max(), freq='D')
    return {k: df.pivot(index='date', columns='symbol', values=k).reindex(days).astype(np.float64)
            for k in ('open', 'high', 'low', 'close', 'qvol')}


def bnf_rows(W, U, start, end, use_funding):
    C = W['close']
    days, syms = C.index, list(C.columns)
    A = alt_arrays(W)
    ad = ((W['high'] / W['low'] - 1).rolling(20).mean()).values
    sig = ((C / C.rolling(25).mean() - 1 <= BNF_DEV) & U).values
    k_a, k_b = int(days.searchsorted(pd.Timestamp(start))), int(days.searchsorted(pd.Timestamp(end)) + 1)
    R, T, ret, busy = [], [], [], np.full(len(syms), -1)
    for t in range(max(k_a - 1, 0), k_b - 1):
        for j in np.flatnonzero(sig[t]):
            k0 = t + 1
            e = A['O'][k0, j]
            if busy[j] >= k0 or e != e:
                continue
            fills = run_bnf(A, j, k0)
            kx = fills[0][2]
            busy[j] = kx
            t1 = days[kx] + pd.Timedelta(days=1)
            fund = funding_paid(syms[j], days[k0], t1, t1, 0.0) if use_funding else 0.0
            net = fills[0][1] / e - 1 - A_COST - fund
            R.append(net / ad[t, j])
            ret.append(net)
            T.append(qtime(days[k0]))
    return R, T, ret


def run_p38():
    W = spot_panel()
    U = universe(W)
    k_a = int(W['close'].index.searchsorted(pd.Timestamp(P38_START)))
    n_u = U.iloc[k_a:].sum(axis=1)
    print(f'유니버스(현물 2018~2019): 하루 평균 {n_u.mean():.0f}종목 (최소 {n_u.min()} · 최대 {n_u.max()}), 거쳐 간 종목 {int(U.iloc[k_a:].any().sum())}개')
    R, T, ret = bnf_rows(W, U, P38_START, P38_END, use_funding=False)
    row = r3.verdict_row('P38 BNF 재현 (현물 알트 2018~2019)', R, T, P38_START, P38_END, 1)
    r3.show([row], 'P38 재현', 1)
    if ret:
        print(f'  거래당 순수익: 평균 {np.mean(ret):+.2%} · 중앙 {np.median(ret):+.2%} · 승률 {np.mean(np.array(ret) > 0):.0%}')
    return row


if __name__ == '__main__':
    pe.Paths.init()
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if what in ('6a', 'all'):
        run_6a()
    if what in ('6b', 'all'):
        run_6b()
    if what == 'p38':
        run_p38()
