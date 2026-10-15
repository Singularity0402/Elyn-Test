"""
1차 검증 (2026-10-17, 데이터 없이): 사용자 PC 실데이터 결과로 기록된 통계만으로 거래 결과 분포를 맞추고,
확인된 BTC 4h 전략(다바스·터틀 1·터틀 2)을 70달러 한 계좌에서 함께 돌릴 때의 미래 분포를 몬테카를로로 본다.
- 거래 결과 R: 손실 ≈ −1R(갭 조금), 이익 ~ 로그정규. 승률·평균·표준편차를 기록값에 맞춘다(표준편차는 하한에서 역산).
- 기본 = 최근 국면(2021-11~2026-10) 평균, 비관 = 그 절반.
- 상관: 주(week)마다 공통 시장 요인 Z — 같은 주에 들어간 거래는 함께 이기거나 함께 진다 (ρ = 0 · 0.5 · 0.8).
- 크기: 거래당 위험 r(손절 한 번에 자산의 r), 명목 = 자산 × r ÷ 손절 거리, 열린 명목 합 ≤ 자산 × 3배.
- 70달러 현실: 터틀은 선물 최소 주문 100 USDT → 위험 = max(r, 100 × 손절 거리 ÷ 자산).
실행: python research/mc_plan_2026-10-17.py [경로 수] [fit|calib|kelly|grid|plan]  (결과: mc_plan_2026-10-17_output.txt)
"""
import math
import sys
import numpy as np

YEARS_DATA = 8.79
# (이름, 거래 수, 승률, 전체 평균R, 최근 국면 평균R, 하한, 하한의 z, 평균 손절 거리, 평균 보유 일)
STATS = [('다바스 4h', 220, 0.41, 0.415, 0.305, 0.032, 2.4977, 0.068, 4.6),
         ('터틀1 4h', 481, 0.35, 0.420, 0.274, 0.078, 2.3940, 0.026, 3.0),
         ('터틀2 4h', 245, 0.33, 0.746, 0.411, 0.074, 2.3940, 0.026, 7.0)]


def fit(n, p, mean_all, mean_use, lo, z):
    sd = (mean_all - lo) / z * math.sqrt(n)               # 하한에서 역산한 거래당 R 표준편차
    ew = (mean_use + (1 - p) * 1.0) / p                     # 이익 거래 평균
    er2 = sd ** 2 + mean_use ** 2
    ew2 = (er2 - (1 - p) * 1.0) / p
    vw = max(ew2 - ew ** 2, 0.25)
    s2 = math.log(1 + vw / ew ** 2)                         # 로그정규 모수
    return dict(p=p, mu=math.log(ew) - s2 / 2, s=math.sqrt(s2), sd=sd, ew=ew)


def _ncdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def _nppf(p):
    # Acklam 역정규 근사 (상대오차 ~1e-9)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    p = np.asarray(p, dtype=float)
    out = np.empty_like(p)
    lo, hi = p < 0.02425, p > 1 - 0.02425
    mid = ~(lo | hi)
    q = np.sqrt(-2 * np.log(p[lo]))
    out[lo] = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = np.sqrt(-2 * np.log(1 - p[hi]))
    out[hi] = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p[mid] - 0.5
    r = q * q
    out[mid] = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    return out


def run(edge='recent', rho=0.5, risk=0.02, years=1, paths=20000, seed=70.0, real70=True, lev=3.0, rng=None, use=(0, 1, 2),
        risks=None, fut_slots=None, slot_until=0.0):
    # risks: 전략별 위험(없으면 모두 risk) · fut_slots: 자산 < slot_until 동안 동시에 열 선물(터틀) 포지션 수
    rng = rng or np.random.default_rng(1)
    days = 365 * years
    fins, dd50, mins = np.empty(paths), 0, np.empty(paths)
    pars = []
    for j, (nm, n, p, ma, mr, lo, z, d, hold) in enumerate(STATS):
        mu_use = mr if edge == 'recent' else (ma if edge == 'all' else mr / 2)
        pars.append((fit(n, p, ma, mu_use, lo, z), (n / YEARS_DATA) if j in use else 0.0, d, hold, nm))
    for k in range(paths):
        ev = []
        Zw = rng.normal(size=days // 7 + 2)
        for si, (f, rate, d, hold, nm) in enumerate(pars):
            m = rng.poisson(rate * years)
            t_in = np.sort(rng.uniform(0, days, m))
            t_out = t_in + rng.exponential(hold, m)
            x = math.sqrt(rho) * Zw[(t_in // 7).astype(int)] + math.sqrt(1 - rho) * rng.normal(size=m)
            u = _ncdf(x) if m else np.zeros(0)
            loss = u < 1 - f['p']
            uw = np.clip((u - (1 - f['p'])) / f['p'], 1e-9, 1 - 1e-9)
            W = np.exp(f['mu'] + f['s'] * _nppf(uw)) if m else np.zeros(0)
            R = np.where(loss, -1.0 - rng.exponential(0.05, m), W)
            for a, b, r in zip(t_in, t_out, R):
                ev.append((a, 1, si, r, b))
                ev.append((b, 0, si, r, a))
        ev.sort(key=lambda e: (e[0], e[1]))
        E, peak, mdd, opened = seed, seed, 0.0, {}
        lo_e = seed
        for t, typ, si, r, other in ev:
            key = (si, other if typ == 0 else t)
            d = pars[si][2]
            if typ == 1:
                rk = risks[si] if risks else risk
                if fut_slots is not None and si > 0 and E < slot_until and sum(1 for (sj, _) in opened if sj > 0) >= fut_slots:
                    continue
                if real70 and si > 0:                      # 터틀 = 선물 최소 주문
                    rk = max(risk, 100.0 * d / max(E, 1e-9))
                notional = E * rk / d
                room = lev * E - sum(v[0] for v in opened.values())
                if room <= 0 or E <= 1.0:
                    continue
                notional = min(notional, room)
                opened[(si, t)] = (notional, d)
            else:
                if (si, other) in opened:
                    notional, dd_ = opened.pop((si, other))
                    E += notional * dd_ * r                 # 손익 = 명목 × 손절 거리 × R
                    E = max(E, 0.0)
                    peak = max(peak, E)
                    mdd = max(mdd, 1 - E / peak if peak > 0 else 1)
                    lo_e = min(lo_e, E)
        fins[k] = E
        mins[k] = lo_e
        dd50 += mdd >= 0.5
    q = np.percentile(fins, [10, 50, 90])
    return dict(p10=q[0], p50=q[1], p90=q[2], p_loss=float(np.mean(fins < seed)), p_dd50=dd50 / paths,
                p_1000=float(np.mean(fins >= 1000)), p_ruin=float(np.mean(mins < seed * 0.2)))


def kelly_table():
    """거래당 R의 평균 μ, 제곱평균 m2, 연 거래 수 N → 위험 r에서 연 로그성장 ≈ N(rμ − r²m2/2). 최대 = Nμ²/(2m2) (r = μ/m2)."""
    tot_info, rows = 0.0, []
    sN_mu = sN_m2 = 0.0
    for nm, n, p, ma, mr, lo, z, d, hold in STATS:
        f = fit(n, p, ma, mr, lo, z)
        N = n / YEARS_DATA
        m2 = f['sd'] ** 2 + mr ** 2
        info = N * mr ** 2 / m2                            # 연간 "엣지 정보" = N × (거래당 샤프)²
        tot_info += info
        sN_mu += N * mr
        sN_m2 += N * m2
        rows.append((nm, N, mr, f['sd'], mr / math.sqrt(m2), mr / m2, info / 2))
        print(f'{nm}: 연 {N:.0f}건 · 평균 {mr:+.3f}R · 표준편차 {f["sd"]:.2f} · 거래당 샤프 {mr / math.sqrt(m2):.3f} · '
              f'켈리 위험 {mr / m2:.1%} · 혼자 최대 연 로그성장 {info / 2:.2f} (×{math.exp(info / 2):.2f}/년)')
    g1 = sN_mu ** 2 / (2 * sN_m2)
    print(f'셋 함께, 같은 위험 하나(상관 0 가정): 최적 위험 {sN_mu / sN_m2:.1%} · 연 로그성장 {g1:.2f} (×{math.exp(g1):.2f}/년, 하루 {math.expm1(g1 / 365):.2%})')
    print(f'셋 각자 최적 위험(상관 0 가정): 연 로그성장 {tot_info / 2:.2f} (×{math.exp(tot_info / 2):.2f}/년)')
    for nm, daily in (('BNF 8년 (1.6백만엔 → 180억엔)', math.log(11250) / 8 / 365), ('미너비니 1994~2000 (연 평균 220%)', math.log(3.2) / 365),
                      ('하루 1%', math.log(1.01))):
        g = daily * 365
        print(f'목표 {nm}: 연 로그성장 {g:.2f} → 필요한 엣지 정보 {2 * g:.2f} = 지금 셋의 {2 * g / tot_info:.1f}배')
    return rows


def plan(paths=4000):
    """70달러 단계 계획 비교 (최근 국면 엣지, ρ=0.5, 70달러 최소 주문 반영)."""
    cases = [('A 다바스 현물 2%만', dict(use=(0,), real70=False, risk=0.02)),
             ('B 셋 함께 1% (터틀은 최소주문 때문에 실제 ~3.7%)', dict(use=(0, 1, 2), real70=True, risk=0.01)),
             ('C 다바스 2% + 터틀 한 자리(260달러 전까지)', dict(use=(0, 1, 2), real70=True, risks=(0.02, 0.01, 0.01), fut_slots=1, slot_until=260.0)),
             ('D 다바스 2% + 터틀2만 한 자리(260달러 전까지)', dict(use=(0, 2), real70=True, risks=(0.02, 0.01, 0.01), fut_slots=1, slot_until=260.0)),
             ('E 다바스 2%, 260달러부터 터틀 1% 합류', dict(use=(0, 1, 2), real70=True, risks=(0.02, 0.01, 0.01), fut_slots=0, slot_until=260.0))]
    for edge in ('recent', 'half'):
        for label, kw in cases:
            kw = dict(kw)
            risk = kw.pop('risk', 0.01)
            r1 = run(edge, 0.5, risk, 1, paths, **kw)
            r3 = run(edge, 0.5, risk, 3, paths, **kw)
            print(f'{"최근 국면" if edge == "recent" else "절반 엣지"} · {label} | 1년 중앙 ${r1["p50"]:,.0f} (하위10% ${r1["p10"]:,.0f}, 반토막 {r1["p_dd50"]:.0%}) | '
                  f'3년 중앙 ${r3["p50"]:,.0f} (하위10% ${r3["p10"]:,.0f}, 상위10% ${r3["p90"]:,.0f}, 반토막 {r3["p_dd50"]:.0%}, 80%↓ {r3["p_ruin"]:.0%})', flush=True)


def grid(paths=4000):
    rows = []
    for label, use, real in (('다바스 혼자(현물)', (0,), False), ('3개 함께(이론)', (0, 1, 2), False), ('3개 함께(70달러 최소주문)', (0, 1, 2), True)):
        for edge in ('recent', 'half'):
            for rho in ((0.5, 0.8) if len(use) > 1 else (0.0,)):
                for risk in (0.01, 0.02, 0.03, 0.05):
                    r1 = run(edge, rho, risk, 1, paths, use=use, real70=real)
                    r3 = run(edge, rho, risk, 3, paths, use=use, real70=real)
                    rows.append((label, edge, rho, risk, r1, r3))
                    print(f'{label} · {"최근 국면" if edge == "recent" else "절반 엣지"} · ρ={rho} · 위험 {risk:.0%} | '
                          f'1년 중앙 ${r1["p50"]:,.0f} (하위10% ${r1["p10"]:,.0f}, 반토막 {r1["p_dd50"]:.0%}) | '
                          f'3년 중앙 ${r3["p50"]:,.0f} (하위10% ${r3["p10"]:,.0f}, 상위10% ${r3["p90"]:,.0f}, 반토막 {r3["p_dd50"]:.0%}, '
                          f'80%↓ {r3["p_ruin"]:.0%}, 1천달러↑ {r3["p_1000"]:.0%})', flush=True)
    return rows



if __name__ == '__main__':
    paths = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    mode = sys.argv[2] if len(sys.argv) > 2 else 'fit'
    if mode == 'calib':
        # 보정: 다바스 혼자, 전체 국면 평균, 상관 없음, 9년 → 실데이터 시드 백테스트(1% → 156달러, 전부 매수 → 905달러)와 비교
        r = run('all', 0.0, 0.01, 9, paths, use=(0,), real70=False)
        print(f'보정(다바스 혼자 1%, 9년): 중앙 ${r["p50"]:,.0f} · 하위10% ${r["p10"]:,.0f} · 상위10% ${r["p90"]:,.0f} · 반토막 {r["p_dd50"]:.0%}')
        r = run('all', 0.0, 1.0, 9, paths, use=(0,), real70=False, lev=1.0)
        print(f'보정(다바스 혼자 전부 매수, 9년): 중앙 ${r["p50"]:,.0f} · 하위10% ${r["p10"]:,.0f} · 상위10% ${r["p90"]:,.0f} · 반토막 {r["p_dd50"]:.0%}')
    elif mode == 'grid':
        grid(paths)
    elif mode == 'kelly':
        kelly_table()
    elif mode == 'plan':
        plan(paths)
    else:
        for nm, n, p, ma, mr, lo, z, d, hold in STATS:
            f = fit(n, p, ma, mr, lo, z)
            print(f'{nm}: 거래당 R 표준편차 {f["sd"]:.2f} · 이익 거래 평균 {f["ew"]:.2f}R (최근 국면 기준)')
