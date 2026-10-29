"""
P33(BNF 25일 이격도, 알트) 확인 뒤 점검 — 새 시험이 아니다(판정은 바뀌지 않는다). L27: 자료와 장부부터 의심한다.
① 분포(중앙값·승률·위아래 1% 뺀 평균·상위 10건 몫) ② 최악 10건(상장 폐지·붕괴 코인) ③ 이웃 문턱(−20·−30·−35%) 진단
④ 한 계좌 동일 비중 포트폴리오(신호마다 자본의 1/10, 동시 최대 10개, 현금 이상은 안 씀) 자본 곡선·낙폭
실행: python research/r6_bnf_audit_2026-10-29.py
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

r6 = importlib.import_module('round6_2026-10-29')
r3 = r6.r3


def bnf_trades(W, U, dev, hold=r6.BNF_HOLD):
    C = W['close']
    days, syms = C.index, list(C.columns)
    A = r6.alt_arrays(W)
    adr = ((W['high'] / W['low'] - 1).rolling(20).mean()).values
    devs = (C / C.rolling(25).mean() - 1).values
    sig = ((C / C.rolling(25).mean() - 1 <= dev) & U).values
    k_a = int(days.searchsorted(pd.Timestamp(r6.A_START)))
    k_b = int(days.searchsorted(pd.Timestamp(r6.A_END)) + 1)
    rows, busy = [], np.full(len(syms), -1)
    for t in range(max(k_a - 1, 0), k_b - 1):
        for j in np.flatnonzero(sig[t]):
            k0 = t + 1
            e = A['O'][k0, j]
            if busy[j] >= k0 or e != e:
                continue
            fills = r6.run_bnf(A, j, k0, hold)
            kx, px = fills[0][2], fills[0][1]
            busy[j] = kx
            t1 = days[kx] + pd.Timedelta(days=1)
            fund = r6.funding_paid(syms[j], days[k0], t1, t1, 0.0)
            net = px / e - 1 - r6.A_COST - fund
            rows.append(dict(sym=syms[j], d0=days[k0], d1=days[kx], ret=net, R=net / adr[t, j], adr=adr[t, j], hold=kx - k0 + 1, dev=devs[t, j],
                             delisted=bool(kx + 1 < len(days) and A['C'][kx + 1, j] != A['C'][kx + 1, j] and kx - k0 + 1 < hold)))
    return pd.DataFrame(rows)


def portfolio(tr, slots=10, start=r6.A_START, end=r6.A_END):
    """신호 순서대로 빈 자리(최대 slots)에 자본의 1/slots 씩. 자리 없으면 건너뜀. 일 단위로 손익을 청산일에 반영(보수적 근사)."""
    tr = tr.sort_values(['d0', 'sym']).reset_index(drop=True)
    eq, cash_days = 1.0, pd.date_range(start, end, freq='D')
    open_pos, curve, taken = [], {}, 0
    by_day = {d: g for d, g in tr.groupby('d0')}
    for d in cash_days:
        still = []
        for p in open_pos:
            if p['d1'] <= d:
                eq += p['stake'] * p['ret']
            else:
                still.append(p)
        open_pos = still
        if d in by_day:
            for _, r in by_day[d].iterrows():
                if len(open_pos) >= slots:
                    break
                open_pos.append(dict(d1=r['d1'], ret=r['ret'], stake=eq / slots))
                taken += 1
        curve[d] = eq
    s = pd.Series(curve)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    mdd = float((1 - s / s.cummax()).max())
    return s, dict(taken=taken, cagr=s.iloc[-1] ** (1 / yrs) - 1, mdd=mdd, final=s.iloc[-1])


def portfolio_vol(tr, risk, cap_pos=0.25, cap_gross=1.0, start=r6.A_START, end=r6.A_END):
    """R 단위와 같은 크기: 자리 = 자본 × min(cap_pos, risk ÷ ADR20). 총 노출 ≤ 자본 × cap_gross(넘치면 건너뜀). 깊이 순(더 많이 빠진 것 먼저)."""
    eq, open_pos, curve, taken = 1.0, [], {}, 0
    by_day = {d: g.sort_values('dev') for d, g in tr.groupby('d0')}
    for d in pd.date_range(start, end, freq='D'):
        still = []
        for p_ in open_pos:
            if p_['d1'] <= d:
                eq += p_['stake'] * p_['ret']
            else:
                still.append(p_)
        open_pos = still
        if d in by_day:
            gross = sum(p_['stake'] for p_ in open_pos)
            for _, r in by_day[d].iterrows():
                st = eq * min(cap_pos, risk / r['adr'])
                if gross + st > cap_gross * eq:
                    continue
                open_pos.append(dict(d1=r['d1'], ret=r['ret'], stake=st))
                gross += st
                taken += 1
        curve[d] = eq
    s = pd.Series(curve)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return s, dict(taken=taken, cagr=s.iloc[-1] ** (1 / yrs) - 1, mdd=float((1 - s / s.cummax()).max()), final=s.iloc[-1])


def main():
    W = r6.alt_panel()
    U = r6.universe(W)
    tr = bnf_trades(W, U, r6.BNF_DEV)
    R = tr['R'].values
    q = np.percentile(R, [1, 99])
    trim = R[(R > q[0]) & (R < q[1])]
    top = np.sort(R)[::-1]
    print(f'━━ P33 BNF 점검 (문턱 {r6.BNF_DEV:.0%}) ━━')
    print(f'  {len(R)}건 · 평균 {R.mean():+.3f}R · 중앙 {np.median(R):+.3f}R · 승률 {np.mean(R > 0):.0%} · 위아래 1% 뺀 평균 {trim.mean():+.3f}R · '
          f'상위 10건 합의 몫 {top[:10].sum() / R.sum():.0%}')
    print(f'  거래당 순수익(가격 %): 평균 {tr["ret"].mean():+.2%} · 중앙 {tr["ret"].median():+.2%} · 평균 보유 {tr["hold"].mean():.1f}일 · '
          f'중도 상장 폐지 {int(tr["delisted"].sum())}건')
    print('  최악 10건:')
    for _, r in tr.nsmallest(10, 'ret').iterrows():
        print(f'    {r["sym"]:<14} {r["d0"].date()} → {r["d1"].date()} {r["ret"]:+.1%} ({r["R"]:+.1f}R){" · 상장 폐지" if r["delisted"] else ""}')
    print('  최고 5건:')
    for _, r in tr.nlargest(5, 'ret').iterrows():
        print(f'    {r["sym"]:<14} {r["d0"].date()} → {r["d1"].date()} {r["ret"]:+.1%} ({r["R"]:+.1f}R)')
    by_m = tr.groupby(tr['d0'].dt.to_period('M'))['ret'].agg(['size', 'mean'])
    print(f'  신호가 몰린 달 상위 5: ' + ' · '.join(f'{p} {int(n)}건 {m:+.1%}' for p, (n, m) in by_m.nlargest(5, 'size').iterrows()))
    print('\n  이웃 문턱 진단 (판정 아님, 같은 청산 규칙):')
    for dev in (-0.20, -0.30, -0.35):
        t2 = bnf_trades(W, U, dev)
        v = r3.verdict_row(f'BNF {dev:.0%}', t2['R'].values, t2['d0'].values, r6.A_START, r6.A_END, r6.A_K)
        print(f'    {dev:.0%}: {v["n"]}건 평균 {v["mean"]:+.3f}R · t {v["t"]:+.2f} · 반쪽 {v["h1"]:+.3f} / {v["h2"]:+.3f} · 거래당 {t2["ret"].mean():+.2%}')
    print('\n  한 계좌 포트폴리오 (자리 10개, 자리당 자본 10%, 레버리지 없음):')
    for slots in (5, 10, 20):
        s, st = portfolio(tr, slots)
        yr = s.resample('YE').last().pct_change()
        yr.iloc[0] = s.resample('YE').last().iloc[0] - 1
        print(f'    자리 {slots:>2}: 체결 {st["taken"]}건 · 연복리 {st["cagr"]:+.0%} · 최대 낙폭 {st["mdd"]:.0%} · 6.3년 ×{st["final"]:.2f} · 연도별 '
              + ' '.join(f'{d.year} {v:+.0%}' for d, v in yr.items()))
    print('\n  R 단위 크기 포트폴리오 (자리 = 자본 × 위험 ÷ ADR20, 자리 상한 25%, 총 노출 ≤ 자본, 깊이 순):')
    for risk in (0.005, 0.01, 0.02):
        s, st = portfolio_vol(tr, risk)
        yr = s.resample('YE').last().pct_change()
        yr.iloc[0] = s.resample('YE').last().iloc[0] - 1
        print(f'    위험 {risk:.1%}/거래: 체결 {st["taken"]}건 · 연복리 {st["cagr"]:+.0%} · 최대 낙폭 {st["mdd"]:.0%} · ×{st["final"]:.2f} · 연도별 '
              + ' '.join(f'{d.year} {v:+.0%}' for d, v in yr.items()))
    tr.to_csv(os.path.join(HERE, 'r6_bnf_trades.csv'), index=False)


if __name__ == '__main__':
    pe.Paths.init()
    main()
