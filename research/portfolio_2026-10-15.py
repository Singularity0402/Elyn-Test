"""
확인된 P12 융합(피라미딩)을 BTC·ETH 에서 한 계좌로 함께 돌리는 시뮬레이션 (2026-10-15, 실데이터).
새 시험이 아니라 확인된 규칙의 "운용 성적표"다 (절차 수 늘지 않음).

- 캠페인: BTC 는 1분봉 재생(research/p12_audit.py), ETH 는 4h 봉(P17 과 같은 함수). 단위별 진입 봉·가격, 청산 봉·가격을 쓴다.
- 크기: 캠페인 시작 때 자본 E 로 단위 명목 = E × r ÷ 첫 손절 거리 (단위 4개까지 같은 명목, 터틀 방식).
- 계좌: 4h 봉마다 시가평가. 선물 증거금 = 명목 ÷ 5 (5배), 열린 명목 합 ≤ 자본 × 3.
- 70달러 현실(옵션):
    BTC 선물 최소 주문 100 USDT, ETH 선물 20 USDT (거래소 화면에서 꼭 확인), 현물 5 USDT.
    BTC 롱은 자본이 작을 때 현물로(현금 한도 안에서), BTC 숏은 단위 명목이 100 USDT 를 넘을 때만.
    최소 주문 때문에 단위 위험이 r 의 2배를 넘으면 그 단위는 건너뛴다.
- 비용: 선물 단위 왕복 0.12% + 펀딩(실제, 2020 이전 0.01%/8h 가정), 현물 단위 왕복 0.25%.
실행: python research/portfolio_2026-10-15.py [dist]   (dist = 앞으로의 분포, 블록 부트스트랩)
"""
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import pattern_edge_v612 as pe  # noqa: E402
import p12_audit as pa  # noqa: E402

START, END = '2018-01-01', '2026-10-04'


def campaigns(df4, res, sym, funding):
    """시뮬 결과 → 캠페인 목록 (단위별 시각·가격, 청산 시각·가격, 방향, 첫 손절 거리, 단위별 펀딩 합)."""
    ent, xit, rr, un, sd, d0s, ubar, upx, xpx = res
    idx = df4.index
    ft = funding.index.values.astype('datetime64[ns]')
    cum = np.r_[0.0, np.cumsum(funding.values.astype(np.float64))]
    f0 = ft[0]
    out = []
    for j in range(len(rr)):
        t_out = idx.values[min(xit[j], len(idx) - 1)]
        units = []
        for u in range(un[j]):
            t_u = idx.values[ubar[j, u]]
            a, b = np.searchsorted(ft, t_u, side='right'), np.searchsorted(ft, t_out, side='right')
            paid = cum[b] - cum[a]
            if t_u < f0:
                paid += 0.0001 * max((min(t_out, f0) - t_u) / np.timedelta64(1, 'h'), 0) / 8.0
            units.append((t_u, float(upx[j, u]), float(paid)))
        out.append(dict(sym=sym, side=int(sd[j]), d0=float(d0s[j]), units=units, t_out=t_out, px_out=float(xpx[j]),
                        t_in=units[0][0]))
    return out


def p16_campaigns(sym, k1h, metrics, start=START, end=END):
    """P16 군중 숏 쏠림 돌파(1h 롱) 거래 → 단위 1개짜리 캠페인 (현물로 한다: 롱 전용, 펀딩·청산 없음)."""
    df = pe.normalize_frame(k1h)
    idx = df.index
    sig, atrp = pe.crowd_squeeze_signal(df, metrics)
    o, h, l, c = (df[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    i0, i1 = int(idx.searchsorted(pd.Timestamp(start))), int(idx.searchsorted(pd.Timestamp(end)))
    out = []
    i = i0
    while i < i1 - 1:
        if not sig[i]:
            i += 1
            continue
        e = i + 1
        entry = o[e]
        dist = pe.P16_STOP_ATR * atrp[i] * c[i]
        if not (dist > 0) or not np.isfinite(dist):
            i += 1
            continue
        stop = entry - dist
        last = min(e + pe.P16_HOLD - 1, i1 - 1)
        px, xi = c[last], last
        for j in range(e, last + 1):
            if l[j] <= stop:
                px = o[j] if o[j] < stop else stop
                xi = j
                break
        # 청산 시각 = 청산 봉의 끝(종가 청산) 또는 손절 봉 시작 — 4h 장부에서는 다음 4h 시각에 반영된다
        t_out = idx.values[xi] + (np.timedelta64(1, 'h') if px == c[xi] and xi == last else np.timedelta64(0, 'h'))
        out.append(dict(sym=sym, side=1, d0=dist / entry, units=[(idx.values[e], float(entry), 0.0)], t_out=t_out, px_out=float(px),
                        t_in=idx.values[e], kind='p16', venue='spot'))
        i = xi + 1
    return out


def simulate(camps, closes, r, seed=70.0, real70=False, lev_cap=3.0, start=START, end=END, mins=None, r16=None):
    """한 계좌 시가평가 시뮬레이션. closes = {sym: 4h 종가 Series}. 반환 (자본 Series, 기록)."""
    mins = mins or {'BTCUSDT': 100.0, 'ETHUSDT': 20.0}
    ev = []
    for k, cp in enumerate(camps):
        if cp['t_in'] < np.datetime64(pd.Timestamp(start)) or cp['t_in'] >= np.datetime64(pd.Timestamp(end)):
            continue
        for u, (t_u, px, paid) in enumerate(cp['units']):
            ev.append((t_u, 0, k, u))
        ev.append((cp['t_out'], 1, k, -1))
    # 같은 시각이면 진입(0)을 청산(1)보다 먼저: 진입 봉에서 바로 손절된 캠페인이 '유령 포지션'으로 남지 않게
    ev.sort(key=lambda e: (e[0], e[1], e[3]))
    times = sorted(set(np.concatenate([closes[s].index.values for s in closes])))
    times = [t for t in times if np.datetime64(pd.Timestamp(start)) <= t < np.datetime64(pd.Timestamp(end))]
    cash = seed                       # 실현 자본 (현물 매수 금액·증거금은 따로 셈)
    open_ = {}                        # k → dict(notional, venue, units[(px, notional)])
    eq_t, eq_v = [], []
    ei = 0
    log = dict(skipped_units=0, skipped_camps=0, spot_units=0, fut_units=0, camps=0)
    last_px = {s: np.nan for s in closes}
    cl_idx = {s: closes[s].index.values for s in closes}
    cl_val = {s: closes[s].values for s in closes}
    cl_pos = {s: 0 for s in closes}

    def equity():
        e = cash
        for k, o in open_.items():
            cp = camps[k]
            p = last_px[cp['sym']]
            if np.isnan(p):
                continue
            for (px, nt) in o['units']:
                e += nt * cp['side'] * (p / px - 1.0)
        return e

    for t in times:
        # 이 봉에서 일어난 사건(4h 봉 시각 = 봉 시작, 사건은 그 봉 안)
        while ei < len(ev) and ev[ei][0] <= t:
            t_e, typ, k, u = ev[ei]
            cp = camps[k]
            if typ == 0:
                px = cp['units'][u][1]
                if u == 0:
                    E = equity()
                    if E <= 1.0:
                        ei += 1
                        continue
                    nt = E * ((r16 if r16 is not None else r) if cp.get('kind') == 'p16' else r) / cp['d0']
                    venue = cp.get('venue', 'fut')
                    if venue == 'spot':
                        nt = min(nt, E)
                    elif real70:
                        if cp['sym'] == 'BTCUSDT' and nt < mins['BTCUSDT']:
                            venue = 'spot' if cp['side'] > 0 else 'skip'
                        elif cp['sym'] != 'BTCUSDT' and nt < mins[cp['sym']]:
                            if mins[cp['sym']] * cp['d0'] / E <= 2.0 * r:
                                nt = mins[cp['sym']]
                            else:
                                venue = 'skip'
                    if venue == 'skip':
                        log['skipped_camps'] += 1
                        ei += 1
                        continue
                    open_[k] = dict(nt=nt, venue=venue, units=[])
                    log['camps'] += 1
                if k not in open_:
                    ei += 1
                    continue
                o = open_[k]
                E = equity()
                fut_nt = sum(sum(x[1] for x in oo['units']) for kk, oo in open_.items() if oo['venue'] == 'fut')
                spot_nt = sum(sum(x[1] for x in oo['units']) for kk, oo in open_.items() if oo['venue'] == 'spot')
                if o['venue'] == 'spot':
                    room = E - spot_nt - fut_nt / 5.0
                    if room < max(5.0, o['nt'] * 0.999):
                        log['skipped_units'] += 1
                        ei += 1
                        continue
                    log['spot_units'] += 1
                else:
                    if fut_nt + spot_nt + o['nt'] > lev_cap * E:
                        log['skipped_units'] += 1
                        ei += 1
                        continue
                    log['fut_units'] += 1
                o['units'].append((px, o['nt']))
                cash -= o['nt'] * (0.00125 if o['venue'] == 'spot' else 0.0006)          # 들어갈 때 비용(왕복의 절반)
            else:
                if k in open_:
                    o = open_.pop(k)
                    for ui, (px, nt) in enumerate(o['units']):
                        cash += nt * cp['side'] * (cp['px_out'] / px - 1.0)
                        cash -= nt * (0.00125 if o['venue'] == 'spot' else 0.0006)
                        if o['venue'] == 'fut':
                            cash -= nt * cp['side'] * cp['units'][ui][2]                    # 롱은 양의 펀딩을 낸다
                    cash = max(cash, 0.0)
            ei += 1
        for s in closes:
            j = cl_pos[s]
            while j < len(cl_idx[s]) and cl_idx[s][j] <= t:
                j += 1
            cl_pos[s] = j
            if j:
                last_px[s] = cl_val[s][j - 1]
        eq_t.append(t)
        eq_v.append(max(equity(), 0.0))
    stale = [k for k in open_ if camps[k]['t_out'] < np.datetime64(pd.Timestamp(end)) - np.timedelta64(30, 'D')]
    assert not stale, f'청산됐어야 할 포지션이 열려 있다: {stale[:5]}'
    return pd.Series(eq_v, index=pd.DatetimeIndex(eq_t)), log


def stats(eq, seed):
    if len(eq) < 2:
        return dict(final=seed, cagr=0.0, mdd=0.0)
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    mdd = float((1 - eq / eq.cummax()).max())
    final = float(eq.iloc[-1])
    return dict(final=final, cagr=(final / seed) ** (1 / max(yrs, 1e-9)) - 1 if final > 0 else -1.0, mdd=mdd)


def yearly(eq):
    y = eq.resample('YE').last()
    prev = np.r_[eq.iloc[0], y.values[:-1]]
    return {int(t.year): float(v / p_ - 1) for t, v, p_ in zip(y.index, y.values, prev)}


def main():
    pe.Paths.init()
    base = pd.read_parquet(os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'BTCUSDT_1m_v612.parquet'))
    base = base[base.index < pd.Timestamp('2026-10-15')]
    btc4 = pe._masters_frame(base, '4h')
    i0, i1 = int(btc4.index.searchsorted(pd.Timestamp(START))), int(btc4.index.searchsorted(pd.Timestamp(END)))
    fb = pe.load_funding_history(refresh=False)
    fe = pe.load_funding_history(refresh=False, symbol='ETHUSDT')
    rb = pa.run_1m(btc4, base, i0, i1)
    eth4 = pe.normalize_frame(pe.lab_eth_frames(pe.PublicHttp(), ('4h',))['4h'])
    j0, j1 = int(eth4.index.searchsorted(pd.Timestamp(START))), int(eth4.index.searchsorted(pd.Timestamp(END)))
    re_ = pa.run(eth4, j0, j1)
    cb = campaigns(btc4, rb, 'BTCUSDT', fb)
    ce = campaigns(eth4, re_, 'ETHUSDT', fe)
    closes = {'BTCUSDT': btc4['close'], 'ETHUSDT': eth4['close']}
    print(f'캠페인: BTC {len(cb)} (1분봉 재생) · ETH {len(ce)} (4h)')
    # BTC·ETH 캠페인 R 의 상관 (같은 달 합)
    def monthly_r(res, df):
        T = pd.DatetimeIndex(df.index.values[res[0]])
        return pd.Series(res[2], index=T).groupby(T.to_period('M')).sum()
    mr = pd.concat([monthly_r(rb, btc4), monthly_r(re_, eth4)], axis=1).fillna(0)
    print(f'월별 캠페인 R 합의 상관 BTC·ETH = {mr.corr().iloc[0, 1]:.2f}')
    mb = pd.read_parquet(os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'BTCUSDT_metrics_5m.parquet'))
    me = pd.read_parquet(os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'ETHUSDT_metrics_5m.parquet'))
    hb = pe.fetch_futures_klines_vision(pe.PublicHttp(), 'BTCUSDT', '1h', start='2020-06', log=lambda *a, **k: None)
    he = pe.fetch_futures_klines_vision(pe.PublicHttp(), 'ETHUSDT', '1h', start='2020-06', log=lambda *a, **k: None)
    qb, qe = p16_campaigns('BTCUSDT', hb, mb), p16_campaigns('ETHUSDT', he, me)
    print(f'P16 거래: BTC {len(qb)} · ETH {len(qe)} (현물, 단위 1개)')
    for label, sel, real in (('P16 BTC + ETH 혼자 (현물)', qb + qe, True),
                             ('P12 BTC+ETH + P16 BTC+ETH · 70달러 현실', cb + ce + qb + qe, True)):
        print(f'\n[{label}]')
        for r, r16 in ((0.005, 0.01), (0.0075, 0.01), (0.01, 0.01), (0.0075, 0.015)):
            for a_, b_, nm in ((START, END, '전체 2018~'), ('2021-11-27', END, '국면 2'), ('2024-03-18', END, '최근 2.5년')):
                eq, lg = simulate(sel, closes, r, real70=real, start=a_, end=b_, r16=r16)
                st = stats(eq, 70.0)
                print(f'  P12 위험 {r:.2%}/단위 · P16 위험 {r16:.1%} · {nm}: 70 → ${st["final"]:,.0f} · 연복리 {st["cagr"]:+.1%} · 최대 낙폭 {st["mdd"]:.0%}')
            if (r, r16) == (0.0075, 0.01):
                eq, _ = simulate(sel, closes, r, real70=real, r16=r16)
                print('    연도별: ' + ' · '.join(f'{y} {v:+.0%}' for y, v in yearly(eq).items()))
    for label, sel, real in (('BTC 혼자 (선물, 최소 주문 무시)', cb, False), ('ETH 혼자 (선물, 최소 주문 무시)', ce, False),
                             ('BTC + ETH (선물, 최소 주문 무시)', cb + ce, False),
                             ('BTC + ETH · 70달러 현실 (BTC 롱 현물·숏은 100 USDT 넘을 때, ETH 20 USDT)', cb + ce, True)):
        print(f'\n[{label}]')
        for r in (0.005, 0.0075, 0.01, 0.015):
            for a_, b_, nm in ((START, END, '전체 2018~'), ('2021-11-27', END, '국면 2'), ('2024-03-18', END, '최근 2.5년')):
                eq, lg = simulate(sel, closes, r, real70=real, start=a_, end=b_)
                st = stats(eq, 70.0)
                extra = f' · 건너뜀 캠페인 {lg["skipped_camps"]} 단위 {lg["skipped_units"]} · 현물 단위 {lg["spot_units"]}' if real else ''
                print(f'  위험 {r:.2%}/단위 · {nm}: 70 → ${st["final"]:,.0f} · 연복리 {st["cagr"]:+.1%} · 최대 낙폭 {st["mdd"]:.0%}{extra}')
            if r == 0.01:
                eq, _ = simulate(sel, closes, r, real70=real)
                print('    연도별(1%): ' + ' · '.join(f'{y} {v:+.0%}' for y, v in yearly(eq).items()))


if __name__ == '__main__' and len(sys.argv) == 1:
    main()


def block_boot(mret, months, n=20000, block=3, seed=11):
    """월 수익을 평균 길이 block 개월의 덩어리로 다시 뽑아(정상 블록 부트스트랩) months 개월 경로를 만든다."""
    rng = np.random.default_rng(seed)
    x = np.asarray(mret, dtype=np.float64)
    L = len(x)
    out = np.empty((n, months))
    for k in range(n):
        j = rng.integers(L)
        for m in range(months):
            if m and rng.random() < 1.0 / block:
                j = rng.integers(L)
            out[k, m] = x[j % L]
            j += 1
    return out


def plan_distribution():
    pe.Paths.init()
    base = pd.read_parquet(os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'BTCUSDT_1m_v612.parquet'))
    base = base[base.index < pd.Timestamp('2026-10-15')]
    btc4 = pe._masters_frame(base, '4h')
    i0, i1 = int(btc4.index.searchsorted(pd.Timestamp(START))), int(btc4.index.searchsorted(pd.Timestamp(END)))
    fb = pe.load_funding_history(refresh=False)
    fe = pe.load_funding_history(refresh=False, symbol='ETHUSDT')
    cb = campaigns(btc4, pa.run_1m(btc4, base, i0, i1), 'BTCUSDT', fb)
    eth4 = pe.normalize_frame(pe.lab_eth_frames(pe.PublicHttp(), ('4h',))['4h'])
    j0, j1 = int(eth4.index.searchsorted(pd.Timestamp(START))), int(eth4.index.searchsorted(pd.Timestamp(END)))
    ce = campaigns(eth4, pa.run(eth4, j0, j1), 'ETHUSDT', fe)
    mb = pd.read_parquet(os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'BTCUSDT_metrics_5m.parquet'))
    me = pd.read_parquet(os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'ETHUSDT_metrics_5m.parquet'))
    hb = pe.fetch_futures_klines_vision(pe.PublicHttp(), 'BTCUSDT', '1h', start='2020-06', log=lambda *a, **k: None)
    he = pe.fetch_futures_klines_vision(pe.PublicHttp(), 'ETHUSDT', '1h', start='2020-06', log=lambda *a, **k: None)
    qb, qe = p16_campaigns('BTCUSDT', hb, mb), p16_campaigns('ETHUSDT', he, me)
    closes = {'BTCUSDT': btc4['close'], 'ETHUSDT': eth4['close']}
    print('\n━━ 앞으로의 분포 (국면 2 의 월 수익을 3개월 덩어리로 다시 뽑기, 2만 경로, 시드 70달러) ━━')
    for label, sel, r, r16 in (('P16 BTC+ETH 만 (현물, 위험 1%)', qb + qe, 0.01, 0.01),
                               ('P12 0.5% + P16 1%', cb + ce + qb + qe, 0.005, 0.01),
                               ('P12 0.75% + P16 1%', cb + ce + qb + qe, 0.0075, 0.01),
                               ('P12 1% + P16 1%', cb + ce + qb + qe, 0.01, 0.01)):
        eq, _ = simulate(sel, closes, r, real70=True, start='2021-11-27', end=END, r16=r16)
        me_ = eq.resample('ME').last()
        mret = me_.pct_change().dropna().values
        for months in (12, 36):
            P = block_boot(mret, months)
            W = 70.0 * np.cumprod(1 + P, axis=1)
            fin = W[:, -1]
            peak = np.maximum.accumulate(np.c_[np.full(len(W), 70.0), W], axis=1)[:, 1:]
            mdd = (1 - W / peak).max(axis=1)
            q = np.percentile(fin, [10, 50, 90])
            print(f'  {label} · {months // 12}년: 중앙 ${q[1]:,.0f} · 하위10% ${q[0]:,.0f} · 상위10% ${q[2]:,.0f} · 손실 {np.mean(fin < 70):.0%} · '
                  f'반토막 경험 {np.mean(mdd >= 0.5):.0%} · 30% 낙폭 경험 {np.mean(mdd >= 0.3):.0%}')


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'dist':
    plan_distribution()
