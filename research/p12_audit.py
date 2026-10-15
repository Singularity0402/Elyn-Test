"""
P12 (성공 요소 융합 · 피라미딩) 확인 결과의 감사 (2026-10-15, 클라우드에서 실데이터로).
사전등록 판정은 바꾸지 않는다. 여기서는 "실제 돈으로 믿어도 되나"를 본다:
 1. 같은 봉 안의 순서: 단위를 더한 봉에서 저가가 새 손절까지 내려갔으면 그 봉에서 손절된 것으로 보는 보수적 처리
 2. 펀딩비: 실제 정산값(2020-01~)으로 단위마다 보유 중 낸/받은 펀딩을 뺀다(2018~2019 현물 시대는 0.01%/8h 가정)
 3. 추가 체결 미끄러짐 0.1N, 왕복 비용 0.2%
 4. 꼬리 의존: 가장 큰 캠페인 1·3·5·10개를 빼고, 연도별, 달 묶음 부트스트랩
 5. 2019-09 ~ 2019-12 선물 자료 공백을 건너는 캠페인
실행: python research/p12_audit.py [1m]   (1m = 1분봉 재생. BTCUSDT 1분봉 캐시가 ~/CoinData_Matrix 에 있어야 한다)
"""
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pattern_edge_v612 as pe  # noqa: E402

try:
    from numba import njit
except Exception:                                    # numba 없으면 느리지만 같은 결과
    def njit(*a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]


@njit(cache=False)
def fusion_sim_x(o, h, l, c, atr, h20, l20, h55, l55, h10, l10, cost, units_max, add_n, stop_n, i0, i1,
                 pessimistic, add_slip_n):
    """pe._fusion_sim 과 같은 규칙. pessimistic=1 이면 단위를 더한 봉에서 저가(고가)가 새 손절을 넘으면 그 봉에서 손절.
    add_slip_n = 추가 체결을 불리하게 미끄러뜨리는 크기(N 배). 단위별 진입 봉도 돌려준다(펀딩 계산용)."""
    n = i1
    ent = np.empty(n, dtype=np.int64)
    xit = np.empty(n, dtype=np.int64)
    rr = np.empty(n, dtype=np.float64)
    un = np.empty(n, dtype=np.int64)
    sd = np.empty(n, dtype=np.int64)
    d0s = np.empty(n, dtype=np.float64)
    ubar = np.full((n, 8), -1, dtype=np.int64)
    upx = np.zeros((n, 8), dtype=np.float64)
    xpx = np.zeros(n, dtype=np.float64)
    eps = np.zeros(8, dtype=np.float64)
    ebar = np.zeros(8, dtype=np.int64)
    m = 0
    trend, pos, pend, xpend, k = 0, 0, 0, False, 0
    Nabs, last_add, stop, d0, t_in, pend_n = 0.0, 0.0, 0.0, 0.0, 0, 0.0
    for i in range(i0, i1):
        if pos != 0 and xpend:
            tot = 0.0
            for u in range(k):
                tot += pos * (o[i] / eps[u] - 1.0) - cost
            ent[m], xit[m], rr[m], un[m], sd[m], d0s[m] = t_in, i, tot / d0, k, pos, d0
            for u in range(k):
                ubar[m, u] = ebar[u]
                upx[m, u] = eps[u]
            xpx[m] = o[i]
            m += 1
            pos, xpend, k = 0, False, 0
        if pos == 0 and pend != 0:
            pos, pend, k, t_in = pend, 0, 1, i
            eps[0] = o[i]
            ebar[0] = i
            Nabs = pend_n * o[i]
            last_add = o[i]
            stop = last_add - pos * stop_n * Nabs
            d0 = stop_n * Nabs / o[i]
        if pos != 0:
            if (pos > 0 and l[i] <= stop) or (pos < 0 and h[i] >= stop):
                px = stop
                if (pos > 0 and o[i] < stop) or (pos < 0 and o[i] > stop):
                    px = o[i]
                tot = 0.0
                for u in range(k):
                    tot += pos * (px / eps[u] - 1.0) - cost
                ent[m], xit[m], rr[m], un[m], sd[m], d0s[m] = t_in, i, tot / d0, k, pos, d0
                for u in range(k):
                    ubar[m, u] = ebar[u]
                    upx[m, u] = eps[u]
                xpx[m] = px
                m += 1
                pos, xpend, k = 0, False, 0
            else:
                added = False
                while k < units_max:
                    lvl = last_add + pos * add_n * Nabs
                    if (pos > 0 and h[i] >= lvl) or (pos < 0 and l[i] <= lvl):
                        px = lvl
                        if (pos > 0 and o[i] > lvl) or (pos < 0 and o[i] < lvl):
                            px = o[i]
                        px = px + pos * add_slip_n * Nabs
                        eps[k] = px
                        ebar[k] = i
                        k += 1
                        last_add = lvl if add_slip_n > 0 else px
                        stop = last_add - pos * stop_n * Nabs
                        added = True
                    else:
                        break
                if pessimistic == 1 and added and ((pos > 0 and l[i] <= stop) or (pos < 0 and h[i] >= stop)):
                    px = stop
                    tot = 0.0
                    for u in range(k):
                        tot += pos * (px / eps[u] - 1.0) - cost
                    ent[m], xit[m], rr[m], un[m], sd[m], d0s[m] = t_in, i, tot / d0, k, pos, d0
                    for u in range(k):
                        ubar[m, u] = ebar[u]
                        upx[m, u] = eps[u]
                    xpx[m] = px
                    m += 1
                    pos, xpend, k = 0, False, 0
        if c[i] > h55[i]:
            trend = 1
        elif c[i] < l55[i]:
            trend = -1
        if pos != 0:
            if (pos > 0 and c[i] < l10[i]) or (pos < 0 and c[i] > h10[i]):
                xpend = True
        elif pend == 0 and atr[i] > 0:
            if trend > 0 and c[i] > h20[i]:
                pend, pend_n = 1, atr[i]
            elif trend < 0 and c[i] < l20[i]:
                pend, pend_n = -1, atr[i]
    return ent[:m], xit[:m], rr[:m], un[:m], sd[:m], d0s[:m], ubar[:m], upx[:m], xpx[:m]


def inputs(df):
    ind = pe._lab_indicators(df)
    o, h, l, c = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l', 'c'))
    hi = lambda N: ind['h'].rolling(N).max().shift(1).values
    lo = lambda N: ind['l'].rolling(N).min().shift(1).values
    return o, h, l, c, np.nan_to_num(ind['atr'].values), hi(20), lo(20), hi(55), lo(55), hi(10), lo(10)


def run(df, i0, i1, cost=pe.P10_COST, pessimistic=0, add_slip_n=0.0):
    return fusion_sim_x(*inputs(df), float(cost), int(pe.P12_UNITS), float(pe.P12_ADD_N), float(pe.P12_STOP_N),
                        int(i0), int(i1), int(pessimistic), float(add_slip_n))


def funding_r(res, idx, funding, base_rate=0.0001):
    """캠페인마다 단위별 보유 구간에 정산된 펀딩의 합 ÷ 첫 단위 위험(R). 롱은 양의 펀딩을 낸다(−), 숏은 받는다(+)."""
    ent, xit, rr, un, sd, d0s, ubar, upx, xpx = res
    ft = funding.index.values.astype('datetime64[ns]')
    fv = funding.values.astype(np.float64)
    cum = np.r_[0.0, np.cumsum(fv)]
    first_f = ft[0]
    out = np.zeros(len(rr))
    tv = idx.values
    for j in range(len(rr)):
        tot = 0.0
        t_out = tv[min(xit[j], len(tv) - 1)]
        for u in range(un[j]):
            t_u = tv[ubar[j, u]]
            a = np.searchsorted(ft, t_u, side='right')
            b = np.searchsorted(ft, t_out, side='right')
            paid = cum[b] - cum[a]
            if t_u < first_f:                         # 2020-01 이전(현물 시대·자료 없음): 기본 0.01%/8h 가정
                hours = (min(t_out, first_f) - t_u) / np.timedelta64(1, 'h')
                paid += base_rate * max(hours, 0) / 8.0
            tot += -sd[j] * paid
        out[j] = tot / d0s[j]
    return out


def growth(R, risk):
    eq = np.cumprod(np.maximum(1 + risk * R, 0))
    mdd = float((1 - eq / np.maximum.accumulate(np.r_[1.0, eq])[1:]).max()) if len(R) else 0.0
    return float(eq[-1]) if len(R) else 1.0, mdd


def month_boot(R, T, n_boot=4000, seed=7):
    """달 묶음 부트스트랩: 같은 달에 시작한 캠페인을 한 덩어리로 다시 뽑는다 → 평균R 의 5% 하한."""
    months = pd.DatetimeIndex(T).to_period('M')
    keys = np.unique(months.astype(str))
    groups = [R[months.astype(str) == k] for k in keys]
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        v = np.concatenate([groups[p] for p in pick])
        means.append(v.mean())
    return float(np.percentile(means, 5)), float(np.percentile(means, 50))


def main():
    base = pd.read_parquet(os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'BTCUSDT_1m_v612.parquet'))
    base = base[base.index < pd.Timestamp('2026-10-15')]
    df = pe._masters_frame(base, '4h')
    idx = df.index
    reg = pe.P10_REGIMES
    i0, i1 = int(idx.searchsorted(pd.Timestamp(reg[0][0]))), int(idx.searchsorted(pd.Timestamp(reg[-1][1])))
    funding = pe.load_funding_history(refresh=False)
    ref = pe._fusion_run(df, i0, i1)
    variants = [('사전등록 그대로', dict()), ('같은 봉 보수 처리', dict(pessimistic=1)),
                ('보수 + 추가 미끄러짐 0.1N', dict(pessimistic=1, add_slip_n=0.1)),
                ('보수 + 미끄러짐 + 왕복 0.2%', dict(pessimistic=1, add_slip_n=0.1, cost=0.002))]
    print(f'원래 함수와 같은지: 캠페인 {len(ref[2])}건, 평균 {ref[2].mean():+.3f}R')
    keep = None
    for name, kw in variants:
        res = run(df, i0, i1, **kw)
        ent, xit, rr = res[0], res[1], res[2]
        fr = funding_r(res, idx, funding)
        net = rr + fr
        T = idx.values[ent]
        print(f'\n[{name}] 캠페인 {len(rr)}건 · 펀딩 전 평균 {rr.mean():+.3f}R · 펀딩 {fr.mean():+.3f}R · 펀딩 후 평균 {net.mean():+.3f}R '
              f'· 중앙 {np.median(net):+.3f}R · 승률 {np.mean(net > 0):.0%}')
        for a_, b_ in reg:
            mk = (T >= np.datetime64(pd.Timestamp(a_))) & (T < np.datetime64(pd.Timestamp(b_)))
            g1, d1 = growth(net[mk], 0.01)
            g05, d05 = growth(net[mk], 0.005)
            print(f'   국면 {a_}~{b_}: {mk.sum()}건 평균 {net[mk].mean():+.3f}R · 1% ×{g1:.2f}(낙폭 {d1:.0%}) · 0.5% ×{g05:.2f}(낙폭 {d05:.0%})')
        lo5, med = month_boot(net, T)
        print(f'   달 묶음 부트스트랩 평균R: 5% 하한 {lo5:+.3f} · 중앙 {med:+.3f}')
        if keep is None and name.startswith('보수 + 미끄러짐 + 왕복'):
            pass
        keep = (name, res, net, T)
    name, res, net, T = keep
    print(f'\n[꼬리 의존 — {name}, 펀딩 후]')
    order = np.argsort(net)[::-1]
    for drop in (0, 1, 3, 5, 10, 20):
        mk = np.ones(len(net), dtype=bool)
        mk[order[:drop]] = False
        g, d = growth(net[mk], 0.01)
        print(f'   상위 {drop:>2}개 뺌: 평균 {net[mk].mean():+.3f}R · 1% ×{g:.2f} (낙폭 {d:.0%})')
    print('   상위 10개 캠페인:')
    for j in order[:10]:
        print(f'     {pd.Timestamp(idx.values[res[0][j]]):%Y-%m-%d %H:%M} → {pd.Timestamp(idx.values[min(res[1][j], len(idx) - 1)]):%Y-%m-%d} '
              f'{"롱" if res[4][j] > 0 else "숏"} 단위 {res[3][j]} · {net[j]:+.1f}R · 첫 손절 {res[5][j]:.1%}')
    print(f'\n[연도별 — {name}, 펀딩 후, 위험 1%]')
    yrs = pd.DatetimeIndex(T).year
    for y in sorted(set(yrs)):
        mk = yrs == y
        g, d = growth(net[mk], 0.01)
        print(f'   {y}: {mk.sum():>3}건 평균 {net[mk].mean():+.3f}R · ×{g:.2f} · 낙폭 {d:.0%} · 롱 {(res[4][mk] > 0).sum()} 숏 {(res[4][mk] < 0).sum()}')
    gap0, gap1 = np.datetime64('2019-09-01'), np.datetime64('2020-01-01')
    X = idx.values[np.minimum(res[1], len(idx) - 1)]
    span = (T < gap1) & (X > gap0)
    print(f'\n[2019-09 ~ 2019-12 자료 공백을 건너는 캠페인] {span.sum()}건 · 합 {net[span].sum():+.2f}R')
    for side, mk in (('롱', res[4] > 0), ('숏', res[4] < 0)):
        print(f'[{side}] {mk.sum()}건 평균 {net[mk].mean():+.3f}R · 1% ×{growth(net[mk], 0.01)[0]:.2f}')


if __name__ == '__main__' and len(sys.argv) == 1:
    main()


@njit(cache=False)
def fusion_sim_1m(o4, c4, atr, h20, l20, h55, l55, h10, l10, m_start, m_end, o1, h1, l1, cost, units_max, add_n, stop_n,
                  i0, i1, add_slip_n):
    """
    같은 규칙을 1분봉으로 재생한다. 신호(큰 추세·진입·10봉 청산)는 4h 종가로, 체결(손절·추가)은 1분봉 순서대로.
    1분봉 안에서도 손절이 먼저이고, 단위를 더한 1분봉의 저가(고가)가 새 손절을 넘으면 그 1분봉에서 손절(보수).
    m_start[i], m_end[i] = 4h 봉 i 에 속한 1분봉 범위.
    """
    n = i1
    ent = np.empty(n, dtype=np.int64)
    xit = np.empty(n, dtype=np.int64)
    rr = np.empty(n, dtype=np.float64)
    un = np.empty(n, dtype=np.int64)
    sd = np.empty(n, dtype=np.int64)
    d0s = np.empty(n, dtype=np.float64)
    ubar = np.full((n, 8), -1, dtype=np.int64)
    upx = np.zeros((n, 8), dtype=np.float64)
    xpx = np.zeros(n, dtype=np.float64)
    eps = np.zeros(8, dtype=np.float64)
    ebar = np.zeros(8, dtype=np.int64)
    m = 0
    trend, pos, pend, xpend, k = 0, 0, 0, False, 0
    Nabs, last_add, stop, d0, t_in, pend_n = 0.0, 0.0, 0.0, 0.0, 0, 0.0
    for i in range(i0, i1):
        if pos != 0 and xpend:
            tot = 0.0
            for u in range(k):
                tot += pos * (o4[i] / eps[u] - 1.0) - cost
            ent[m], xit[m], rr[m], un[m], sd[m], d0s[m] = t_in, i, tot / d0, k, pos, d0
            for u in range(k):
                ubar[m, u] = ebar[u]
                upx[m, u] = eps[u]
            xpx[m] = o4[i]
            m += 1
            pos, xpend, k = 0, False, 0
        if pos == 0 and pend != 0:
            pos, pend, k, t_in = pend, 0, 1, i
            eps[0] = o4[i]
            ebar[0] = i
            Nabs = pend_n * o4[i]
            last_add = o4[i]
            stop = last_add - pos * stop_n * Nabs
            d0 = stop_n * Nabs / o4[i]
        if pos != 0:
            for j in range(m_start[i], m_end[i]):
                if (pos > 0 and l1[j] <= stop) or (pos < 0 and h1[j] >= stop):
                    px = stop
                    if (pos > 0 and o1[j] < stop) or (pos < 0 and o1[j] > stop):
                        px = o1[j]
                    tot = 0.0
                    for u in range(k):
                        tot += pos * (px / eps[u] - 1.0) - cost
                    ent[m], xit[m], rr[m], un[m], sd[m], d0s[m] = t_in, i, tot / d0, k, pos, d0
                    for u in range(k):
                        ubar[m, u] = ebar[u]
                        upx[m, u] = eps[u]
                    xpx[m] = px
                    m += 1
                    pos, xpend, k = 0, False, 0
                    break
                added = False
                while k < units_max:
                    lvl = last_add + pos * add_n * Nabs
                    if (pos > 0 and h1[j] >= lvl) or (pos < 0 and l1[j] <= lvl):
                        px = lvl
                        if (pos > 0 and o1[j] > lvl) or (pos < 0 and o1[j] < lvl):
                            px = o1[j]
                        px = px + pos * add_slip_n * Nabs
                        eps[k] = px
                        ebar[k] = i
                        k += 1
                        last_add = lvl if add_slip_n > 0 else px
                        stop = last_add - pos * stop_n * Nabs
                        added = True
                    else:
                        break
                if added and ((pos > 0 and l1[j] <= stop) or (pos < 0 and h1[j] >= stop)):
                    px = stop
                    tot = 0.0
                    for u in range(k):
                        tot += pos * (px / eps[u] - 1.0) - cost
                    ent[m], xit[m], rr[m], un[m], sd[m], d0s[m] = t_in, i, tot / d0, k, pos, d0
                    for u in range(k):
                        ubar[m, u] = ebar[u]
                        upx[m, u] = eps[u]
                    xpx[m] = px
                    m += 1
                    pos, xpend, k = 0, False, 0
                    break
        if c4[i] > h55[i]:
            trend = 1
        elif c4[i] < l55[i]:
            trend = -1
        if pos != 0:
            if (pos > 0 and c4[i] < l10[i]) or (pos < 0 and c4[i] > h10[i]):
                xpend = True
        elif pend == 0 and atr[i] > 0:
            if trend > 0 and c4[i] > h20[i]:
                pend, pend_n = 1, atr[i]
            elif trend < 0 and c4[i] < l20[i]:
                pend, pend_n = -1, atr[i]
    return ent[:m], xit[:m], rr[:m], un[:m], sd[:m], d0s[:m], ubar[:m], upx[:m], xpx[:m]


def minute_map(df4, base1m):
    """4h 봉마다 속한 1분봉 [시작, 끝) 위치."""
    t1 = base1m.index.values
    st = df4.index.values
    en = st + np.timedelta64(240, 'm')
    return np.searchsorted(t1, st, side='left').astype(np.int64), np.searchsorted(t1, en, side='left').astype(np.int64)


def run_1m(df4, base1m, i0, i1, cost=pe.P10_COST, add_slip_n=0.0):
    o, h, l, c, atr, h20, l20, h55, l55, h10, l10 = inputs(df4)
    ms, me = minute_map(df4, base1m)
    o1, h1, l1 = (base1m[k].values.astype(np.float64) for k in ('open', 'high', 'low'))
    return fusion_sim_1m(o, c, atr, h20, l20, h55, l55, h10, l10, ms, me, o1, h1, l1, float(cost), int(pe.P12_UNITS),
                         float(pe.P12_ADD_N), float(pe.P12_STOP_N), int(i0), int(i1), float(add_slip_n))


def main_1m():
    base = pd.read_parquet(os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'BTCUSDT_1m_v612.parquet'))
    base = base[base.index < pd.Timestamp('2026-10-15')]
    df = pe._masters_frame(base, '4h')
    idx = df.index
    reg = pe.P10_REGIMES
    i0, i1 = int(idx.searchsorted(pd.Timestamp(reg[0][0]))), int(idx.searchsorted(pd.Timestamp(reg[-1][1])))
    funding = pe.load_funding_history(refresh=False)
    print('\n━━ 1분봉 재생 (체결 순서를 1분 단위로) ━━')
    for name, kw in (('1분봉 재생', dict()), ('1분봉 재생 + 추가 미끄러짐 0.1N', dict(add_slip_n=0.1)),
                     ('1분봉 재생 + 미끄러짐 0.1N + 왕복 0.2%', dict(add_slip_n=0.1, cost=0.002))):
        res = run_1m(df, base, i0, i1, **kw)
        ent, rr = res[0], res[2]
        fr = funding_r(res, idx, funding)
        net = rr + fr
        T = idx.values[ent]
        print(f'[{name}] 캠페인 {len(rr)}건 · 펀딩 전 평균 {rr.mean():+.3f}R · 펀딩 후 {net.mean():+.3f}R · 중앙 {np.median(net):+.3f}R · 승률 {np.mean(net > 0):.0%}')
        for a_, b_ in reg:
            mk = (T >= np.datetime64(pd.Timestamp(a_))) & (T < np.datetime64(pd.Timestamp(b_)))
            g1, d1 = growth(net[mk], 0.01)
            print(f'   국면 {a_}~{b_}: {mk.sum()}건 평균 {net[mk].mean():+.3f}R · 1% ×{g1:.2f}(낙폭 {d1:.0%})')
        lo5, med = month_boot(net, T)
        sdv = net.std(ddof=1)
        print(f'   정규 근사 단측 5% 하한 {net.mean() - 1.645 * sdv / math.sqrt(len(net)):+.3f} · 달 묶음 부트스트랩 5% 하한 {lo5:+.3f}')
        order = np.argsort(net)[::-1]
        print('   꼬리: ' + ' · '.join(f'상위 {d}개 뺌 {np.delete(net, order[:d]).mean():+.3f}R' for d in (1, 3, 5, 10)))
        for side, mk in (('롱', res[4] > 0), ('숏', res[4] < 0)):
            print(f'   {side} {mk.sum()}건 평균 {net[mk].mean():+.3f}R · 1% ×{growth(net[mk], 0.01)[0]:.2f}')
        yrs = pd.DatetimeIndex(T).year
        print('   연도별(1%): ' + ' · '.join(f'{y} ×{growth(net[yrs == y], 0.01)[0]:.2f}' for y in sorted(set(yrs))))


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == '1m':
    main_1m()
