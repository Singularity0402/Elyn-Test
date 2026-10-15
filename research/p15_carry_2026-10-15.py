"""
사전등록 P15 (선구자 트랙 2: 작은 돈만 갈 수 있는 자리 — 현물이 있는 알트의 극단 펀딩 캐리, 방향 중립).
구현 세부는 RESEARCH_LOG 에 자료를 받기 전에 고정(2026-10-15 09:15 UTC 커밋). 여기서는 그대로 구현해 한 번 돌린다.

- 대상: 펀딩 기록이 있는 USDⓈ-M 무기한 USDT 중 같은 코인 현물(접두 1000 등은 떼고 배수로 맞춤)이 그 시각에 1h 봉으로 있는 것
- 신호: 정산 t 의 펀딩(8h 환산) ≥ +0.10% → t + 1h 에 시작하는 1h 봉 시가에 현물 매수 + 무기한 숏, 같은 명목
- 크기: 한 자리 명목 = 그때 자본 ÷ 6 (현물 1/6 + 선물 증거금 1/6), 동시에 3자리, 같은 시각이면 펀딩이 큰 순
- 펀딩: 진입 < 정산 ≤ 청산 결정 정산의 실제 값 × 명목
- 청산: 정산 펀딩(8h 환산) < +0.03% → 그 정산 + 1h 봉 시가, 또는 진입 + 7일 뒤 첫 1h 시가
- 비용: 명목의 0.35% · 급등: 선물 1h 고가 ≥ 진입가 × 1.9 → 그 봉에서 선물 진입가×1.9, 현물 종가로 닫고 명목 2% 벌칙
- 판정: 두 반쪽(경계 2023-05-19) 손익 모두 > 0, 월 수익 평균의 단측 5% 하한 > 0, 연복리 ≥ 21% → 확인 · 평균 ≤ 0 → 반증
실행: python research/p15_data_2026-10-15.py 로 자료를 받은 뒤 python research/p15_carry_2026-10-15.py
"""
import glob
import math
import os

import numpy as np
import pandas as pd

RUN = os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'research_p15')   # research/p15_data_2026-10-15.py 가 만든다
KDIR = os.path.join(os.path.expanduser('~'), 'CoinData_Matrix', 'raw', 'p15_1h')
START, END, SPLIT = pd.Timestamp('2020-01-01'), pd.Timestamp('2026-10-04'), pd.Timestamp('2023-05-19')
ENTRY_TH, EXIT_TH, MAX_DAYS, SLOTS = 0.0010, 0.0003, 7, 3
COST, SPIKE, PENALTY = 0.0035, 1.9, 0.02


def load_prices(sym):
    perp, spot, mul = [], [], 1.0
    for f in sorted(glob.glob(os.path.join(KDIR, f'{sym}_*.pkl'))):
        d = pd.read_pickle(f)
        mul = d['mul']
        if d['perp'] is not None:
            perp.append(d['perp'])
        if d['spot'] is not None:
            spot.append(d['spot'])
    if not perp or not spot:
        return None
    p = pd.concat(perp)
    s = pd.concat(spot)
    p = p[~p.index.duplicated()].sort_index()
    s = s[~s.index.duplicated()].sort_index()
    s = s * mul                                    # 현물 값을 선물 계약 단위(예: 1000PEPE)로
    return p, s


def main():
    d = pd.read_pickle(os.path.join(RUN, 'p15_funding.pkl'))
    F, spotmap = d['F'], d['spotmap']
    F = F[F['sym'].map(lambda s_: bool(spotmap.get(s_, (None,))[0]))].copy()
    F = F.sort_values(['t', 'rate8'], ascending=[True, False])
    cand_syms = sorted(F.loc[F['rate8'] >= ENTRY_TH, 'sym'].unique())
    prices = {}
    for s_ in cand_syms:
        r = load_prices(s_)
        if r is not None:
            prices[s_] = r
    print(f'후보 코인 {len(cand_syms)} · 선물·현물 1h 가격이 모두 있는 것 {len(prices)}')
    fund = {s_: g[['t', 'rate8', 'last_funding_rate']].set_index('t').sort_index() for s_, g in F[F['sym'].isin(prices)].groupby('sym')}
    # 사건: 정산 시각 순서
    E = F[F['sym'].isin(prices)][['t', 'sym', 'rate8', 'last_funding_rate']].sort_values(['t', 'rate8'], ascending=[True, False])
    times = E['t'].values
    cap = 70.0
    eq_hist = []                                   # (시각, 자본) — 실현 기준 + 열린 포지션의 펀딩·가격은 청산 때 실현
    open_ = {}                                     # sym → dict
    trades = []

    def bar_at(df, t):
        j = df.index.searchsorted(t)
        return j if j < len(df) and df.index[j] == t else -1

    def close_pos(sym, t_exit, reason):
        nonlocal cap
        o = open_.pop(sym)
        p, s = prices[sym]
        jp, js = bar_at(p, t_exit), bar_at(s, t_exit)
        if o.get('spiked'):
            pp, sp_ = o['spike_pp'], o['spike_sp']
        else:
            if jp < 0 or js < 0:                   # 그 시각 봉이 없으면 그 뒤 첫 봉
                jp = p.index.searchsorted(t_exit)
                js = s.index.searchsorted(t_exit)
                if jp >= len(p) or js >= len(s):
                    jp, js = len(p) - 1, len(s) - 1
            pp, sp_ = p['open'].iloc[jp], s['open'].iloc[js]
        nt = o['nt']
        pnl = nt * ((sp_ / o['sp0'] - 1.0) - (pp / o['pp0'] - 1.0)) + o['fund'] * nt - COST * nt
        if o.get('spiked'):
            pnl -= PENALTY * nt
        cap += pnl
        trades.append(dict(sym=sym, t_in=o['t_in'], t_out=t_exit, pnl=pnl, nt=nt, fund=o['fund'], basis=(sp_ / o['sp0'] - 1.0) - (pp / o['pp0'] - 1.0),
                           reason=reason, ret_on_notional=pnl / nt))

    E = E[(E['t'] >= START) & (E['t'] < END + pd.Timedelta(days=MAX_DAYS + 1))]
    for t, g in E.groupby('t', sort=True):
        t = pd.Timestamp(t)
        # 1) 시간 경과: 급등(선물 1h 고가 ≥ 진입가 × 1.9)과 7일 만기 — 열린 포지션마다, 마지막 점검 이후 봉만
        for s_ in list(open_.keys()):
            o = open_[s_]
            p, s = prices[s_]
            j0 = o['chk']
            j1 = int(p.index.searchsorted(t, side='right'))
            if j1 > j0:
                hi = p['high'].values[j0:j1]
                k = np.nonzero(hi >= o['pp0'] * SPIKE)[0]
                o['chk'] = j1
                if len(k):
                    th = p.index[j0 + k[0]]
                    if th < o['t_in'] + pd.Timedelta(days=MAX_DAYS):
                        js = s.index.searchsorted(th)
                        o['spiked'] = True
                        o['spike_pp'] = o['pp0'] * SPIKE
                        o['spike_sp'] = s['close'].iloc[min(js, len(s) - 1)]
                        close_pos(s_, th, 'spike')
                        continue
            if t >= o['t_in'] + pd.Timedelta(days=MAX_DAYS):
                close_pos(s_, o['t_in'] + pd.Timedelta(days=MAX_DAYS), '7d')
        # 2) 이 시각의 정산: 열린 포지션은 펀딩 수입·청산 판단
        for sym, r8, raw in zip(g['sym'].values, g['rate8'].values, g['last_funding_rate'].values):
            if sym in open_:
                o = open_[sym]
                if t > o['t_in']:
                    o['fund'] += raw
                    if r8 < EXIT_TH:
                        close_pos(sym, t + pd.Timedelta(hours=1), 'funding')
        # 3) 진입: 펀딩이 큰 순서
        if START <= t < END:
            for sym, r8 in zip(g['sym'].values, g['rate8'].values):
                if r8 < ENTRY_TH or len(open_) >= SLOTS or cap <= 1.0 or sym in open_:
                    continue
                p, s = prices[sym]
                te = t + pd.Timedelta(hours=1)
                jp, js = bar_at(p, te), bar_at(s, te)
                if jp < 0 or js < 0:
                    continue                       # 그 시각 현물(또는 선물) 봉이 없다 = 현물 없음 → 대상 아님
                open_[sym] = dict(t_in=te, pp0=p['open'].iloc[jp], sp0=s['open'].iloc[js], nt=cap / 6.0, fund=0.0, chk=jp)
        eq_hist.append((t, cap))
    for s_ in list(open_.keys()):
        close_pos(s_, open_[s_]['t_in'] + pd.Timedelta(days=MAX_DAYS), 'end')
    T = pd.DataFrame(trades)
    eq = pd.Series([c for _, c in eq_hist], index=pd.DatetimeIndex([t for t, _ in eq_hist]))
    eq = eq[~eq.index.duplicated(keep='last')]
    me = eq.resample('ME').last().ffill()
    mret = me.pct_change().dropna()
    yrs = (END - START).days / 365.25
    final = float(T['pnl'].sum() + 70.0)
    cagr = (final / 70.0) ** (1 / yrs) - 1
    h1 = T['t_in'] < SPLIT
    lo = mret.mean() - 1.645 * mret.std(ddof=1) / math.sqrt(len(mret))
    print(f'거래 {len(T)} · 승률 {np.mean(T["pnl"] > 0):.0%} · 명목 대비 평균 {T["ret_on_notional"].mean():+.3%} '
          f'(펀딩 {T["fund"].mean():+.3%} · 베이시스 {T["basis"].mean():+.3%} · 비용 −{COST:.2%})')
    print(f'청산 이유: {T["reason"].value_counts().to_dict()}')
    print(f'70달러 → {final:,.1f}달러 · 연복리 {cagr:+.1%} · 반쪽 손익 {T.loc[h1, "pnl"].sum():+.1f} / {T.loc[~h1, "pnl"].sum():+.1f}달러')
    print(f'월 수익 평균 {mret.mean():+.2%} · 표준편차 {mret.std():.2%} · 단측 5% 하한 {lo:+.2%} · 최악의 달 {mret.min():+.1%} · 개월 {len(mret)}')
    dd = float((1 - me / me.cummax()).max())
    print(f'월말 자본 최대 낙폭 {dd:.0%}')
    yr = T.groupby(pd.DatetimeIndex(T['t_in']).year)['pnl'].agg(['count', 'sum'])
    print('연도별 손익(달러):', {int(k): (int(v['count']), round(float(v['sum']), 1)) for k, v in yr.iterrows()})
    print('명목 대비 수익 분포:', T['ret_on_notional'].describe(percentiles=[.05, .25, .5, .75, .95]).round(4).to_dict())
    if (T['pnl'].mean() <= 0):
        v = '반증'
    elif T.loc[h1, 'pnl'].sum() > 0 and T.loc[~h1, 'pnl'].sum() > 0 and lo > 0 and cagr >= 0.21:
        v = '확인'
    else:
        v = '반증 안 됨'
    print('판정:', v)
    T.to_pickle(os.path.join(RUN, 'p15_trades.pkl'))


if __name__ == '__main__':
    main()
