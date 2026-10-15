"""
2026-10-15 클라우드 실데이터 연구(P13 ~ P17, 권장 운용안)의 프로그램 검증 — 합성 자료만 쓴다 (네트워크 없음).
"""
import io
import math
import zipfile

import numpy as np
import pandas as pd


def _walk(n, seed=1, drift=0.0, vol=0.01, start='2020-01-01', freq='1h'):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, n)
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    idx = pd.date_range(start, periods=n, freq=freq)
    v = rng.uniform(50, 150, n)
    return pd.DataFrame(dict(open=o, high=h, low=l, close=c, volume=v, taker_buy_base=v * 0.5, trades=v * 10, era=1.0), index=idx)


# ── P13 ─────────────────────────────────────────────────────────────
def test_gated_darvas_equals_p10_darvas_when_gate_open(pe):
    df = _walk(6000, seed=3, drift=0.0003, freq='4h')
    ind = pe._lab_indicators(df)
    o, h, l, c = (ind[k].values.astype(np.float64) for k in ('o', 'h', 'l', 'c'))
    a = pe._m_darvas(o, h, l, c, 3, 3 * pe.P10_COST, pe.P10_COST, 10, len(c))
    b = pe._m_darvas_g(o, h, l, c, np.ones(len(c), dtype=np.bool_), 3, 3 * pe.P10_COST, pe.P10_COST, 10, len(c))
    assert len(a[0]) > 5 and np.array_equal(a[0], b[0]) and np.allclose(a[1], b[1])
    z = pe._m_darvas_g(o, h, l, c, np.zeros(len(c), dtype=np.bool_), 3, 3 * pe.P10_COST, pe.P10_COST, 10, len(c))
    assert len(z[0]) == 0                                        # 문이 닫혀 있으면 진입 없음


def test_minervini_template_trend_and_causality(pe):
    up = _walk(900, seed=4, drift=0.003, vol=0.01, freq='1D')
    dn = _walk(900, seed=4, drift=-0.003, vol=0.01, freq='1D')
    tu, td = pe.minervini_template(up), pe.minervini_template(dn)
    assert not tu.iloc[:364].any() and tu.iloc[400:].mean() > 0.8 and td.iloc[400:].mean() < 0.05
    # 시간봉에 붙일 때: 그 봉 마감까지 마감된 마지막 일봉의 값만
    bars = pd.date_range(up.index[500], periods=48, freq='1h')
    g = pe._template_on_bars(bars, 60, up)
    day_close = up.index[500] + pd.Timedelta(days=1)
    first_after = int(np.searchsorted(bars + pd.Timedelta(hours=1), day_close))
    assert g[0] == tu.iloc[499] and g[first_after] == tu.iloc[500]


# ── P14 ─────────────────────────────────────────────────────────────
def test_p14_rule_counts_and_procedures(pe):
    r = pe.p14_b_rules()
    assert r.shape == (5988, 3) and pe.p14_procedure_count() == 35928
    keys = pe.p14_procedure_keys()
    assert len(keys) == len(set(keys)) == 35930 and pe.P14_A1_KEY in keys
    for row in r:                                               # 한 규칙 안의 원자는 서로 다른 특징
        f = [a // 4 for a in row if a >= 0]
        assert len(f) == len(set(f))


def test_metrics_at_never_reads_the_future(pe):
    t = pd.date_range('2024-01-01', periods=24, freq='5min')
    m = pd.DataFrame({'oi': np.arange(24, dtype=float)}, index=t)
    q = np.array([t[6]], dtype='datetime64[ns]')                    # 00:30 마감 → 00:25 까지만
    assert pe._metrics_at(m, 'oi', q)[0] == 5.0
    assert np.isnan(pe._metrics_at(m, 'oi', np.array([t[0]], dtype='datetime64[ns]'))[0])


def test_cluster_t_matches_hand_calculation(pe):
    R = np.array([1.0, -1.0, 2.0, 0.5])
    T = np.array(['2024-01-05', '2024-01-20', '2024-02-03', '2024-03-01'], dtype='datetime64[ns]')
    t, se = pe._cluster_t(R, T)
    mean = R.mean()
    S = np.array([1 - mean + (-1 - mean), 2 - mean, 0.5 - mean])
    se_hand = math.sqrt((S ** 2).sum() / 16 * (3 / 2))
    assert abs(se - se_hand) < 1e-12 and abs(t - mean / se_hand) < 1e-9


def test_p14_scan_matches_slow_reference(pe):
    df = _walk(4000, seed=7, drift=0.0002)
    rng = np.random.default_rng(5)
    A = rng.random((len(df), 36)) < 0.12
    rules = np.array([[0, -1, -1], [1, 5, -1]], dtype=np.int64)
    side = np.array([1, -1], dtype=np.int64)
    atrp = pe._lab_indicators(df)['atr'].values
    o, h, l, c = (df[k].values for k in ('open', 'high', 'low', 'close'))
    mon = (df.index.month.values - 1).astype(np.int64)
    half = np.asarray(df.index < df.index[2000], dtype=np.bool_)
    cnt, sm, *_ = pe._p14_b_scan(o, h, l, c, np.nan_to_num(atrp), A, rules, side, 10, 0.0012, 100, len(df), mon, half, 12)
    for r_, (a1, a2, _), sd in zip(range(2), rules, side):
        sig = A[:, a1] & (A[:, a2] if a2 >= 0 else True)
        i, R = 100, []
        while i < len(df) - 1:
            if not sig[i]:
                i += 1
                continue
            e = i + 1
            dist = 1.5 * atrp[i] * c[i]
            stop = o[e] - sd * dist
            last = min(e + 9, len(df) - 1)
            px, xi = c[last], last
            for j in range(e, last + 1):
                if (sd > 0 and l[j] <= stop) or (sd < 0 and h[j] >= stop):
                    px = stop if not ((sd > 0 and o[j] < stop) or (sd < 0 and o[j] > stop)) else o[j]
                    xi = j
                    break
            R.append((sd * (px / o[e] - 1) - 0.0012) / (dist / o[e]))
            i = xi + 1
        assert cnt[r_] == len(R) > 5 and abs(sm[r_] - sum(R)) < 1e-9


# ── P16 ─────────────────────────────────────────────────────────────
def test_crowd_signal_and_state(pe):
    df = _walk(1500, seed=9)
    t = pd.date_range(df.index[0], df.index[-1] + pd.Timedelta(hours=1), freq='5min')
    ls = 1.5 + 0.1 * np.sin(np.arange(len(t)) / 50.0)
    m = pd.DataFrame({'ls_acct': ls}, index=t)
    sig, atrp, zl, zb, _ = pe.crowd_squeeze_signal(df, m, return_z=True)
    assert np.isnan(zl[:500]).all() and not sig[:500].any()
    o, h, l, c = (df[k].values for k in ('open', 'high', 'low', 'close'))
    s2 = np.zeros(len(c), dtype=np.bool_)
    s2[len(c) - 11] = True                                        # 10봉 전 신호 → 보유 중, 남은 봉 = 48 − 10
    lo = np.minimum(l, o * 0.9999)
    st = pe._crowd_state(s2, o, np.maximum(h, o), np.maximum(lo, o * 0.97), c, np.full(len(c), 0.05))
    assert st['state'] == 'position' and st['bars_left'] == 38
    s3 = np.zeros(len(c), dtype=np.bool_)
    s3[-1] = True
    assert pe._crowd_state(s3, o, h, l, c, np.full(len(c), 0.01))['state'] == 'entry'
    assert pe._crowd_state(np.zeros(len(c), dtype=np.bool_), o, h, l, c, np.full(len(c), 0.01))['state'] == 'armed'


def test_crowd_live_holds_when_ratio_is_stale(pe):
    df = _walk(1500, seed=2)
    t = pd.date_range(df.index[0], df.index[-1] - pd.Timedelta(hours=5), freq='5min')
    m = pd.DataFrame({'ls_acct': 1.5 + 0.0 * np.arange(len(t))}, index=t)
    r = pe._crowd_live('ETHUSDT', df, m, seed=70.0)
    assert r['state'] == 'stale' and '보류' in r['action'] and r['pair'] == '1h:crowd_eth'


# ── P17 · 권장 운용안의 신호 ──────────────────────────────────────────
def test_fusion_live_venue_rules_for_small_seed(pe):
    df = _walk(3000, seed=11, drift=-0.0006, freq='4h')
    r_btc = pe._fusion_live(None, '4h', seed=70.0, risk=pe.PLAN_RISK['fusion'], frame=df)
    r_eth = pe._fusion_live(None, '4h', seed=70.0, risk=pe.PLAN_RISK['fusion'], frame=df, sym='ETHUSDT')
    assert r_btc['pair'] == '4h:fusion' and r_eth['pair'] == '4h:fusion_eth' and 'ETHUSDT' in r_eth['lines'][0]
    text_b, text_e = '\n'.join(r_btc['lines']), '\n'.join(r_eth['lines'])
    assert ('현물' in text_b or '건너뜀' in text_b or '선물' in text_b) and ('$20' in text_e or '선물' in text_e)


def test_signal_board_groups_plan_first(pe, monkeypatch):
    calls = []

    def fake_live(base1m, method, tf, seed=70.0, risk=None, frame=None, metrics=None):
        calls.append(method)
        return dict(pair=f'{tf}:{method}', state='armed', action='대기', lines=[f'■ {method}'], stop=None)
    monkeypatch.setattr(pe, 'lab_masters_live', fake_live)
    monkeypatch.setattr(pe, 'lab_eth_frames', lambda http, tfs: {'4h': _walk(100, freq='4h')})
    monkeypatch.setattr(pe, '_live_frame', lambda http, sym, tf, base1m=None: _walk(100))
    monkeypatch.setattr(pe, 'live_metrics', lambda http, sym: pd.DataFrame({'ls_acct': [1.0]}, index=[pd.Timestamp('2020-01-01')]))
    live = [dict(pair='4h:fusion', scope='btc', method='fusion'), dict(pair='4h:darvas', scope='btc', method='darvas'),
            dict(pair='1h:crowd_eth', scope='eth', method='crowd_eth')]
    states = {'4h:fusion': 'confirmed', '4h:darvas': 'confirmed', '1h:crowd_eth': 'confirmed'}
    out = pe.lab_signal_all(None, live, states=states, http=object())['report']
    i_plan, i_conf = out.index('권장 운용안'), out.index('권장안 밖')
    assert i_plan < out.index('■ fusion') < i_conf < out.index('■ darvas') and out.index('■ crowd_eth') < i_conf
    assert calls == ['fusion', 'darvas', 'crowd_eth']


# ── 자료 대체 경로 · 일지 동기화 ─────────────────────────────────────
def _zip_csv(text):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('x.csv', text)
    return b.getvalue()


def test_funding_archive_fallback_parses_monthly_files(pe):
    class Http:
        def get(self, url, timeout=None):
            if '2024-01' in url:
                return _zip_csv('calc_time,funding_interval_hours,last_funding_rate\n1704067200003,8,0.0001\n1704096000001,8,0.0002\n')
            raise FileNotFoundError(url)
    pe.utcnow = lambda: pd.Timestamp('2024-02-15').to_pydatetime()
    rows = pe._funding_from_archive(Http(), 'BTCUSDT', 1704067200000)
    assert [r['fundingTime'] for r in rows] == [1704067200000, 1704096000000] and rows[1]['fundingRate'] == 0.0002


def test_http_451_is_not_retried(pe, monkeypatch):
    class R:
        status_code, content, headers = 451, b'', {}
    n = []
    monkeypatch.setattr(pe, 'REQUESTS_OK', True)
    monkeypatch.setattr(pe.requests, 'get', lambda *a, **k: n.append(1) or R())
    h = pe.PublicHttp(retries=3)
    try:
        h.get('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT')
        raise AssertionError('451 이 예외가 아니다')
    except PermissionError as e:
        assert '451' in str(e)
    assert len(n) == 1


def test_gap_repair_fills_missing_months_from_spot(pe, monkeypatch):
    a = _walk(60 * 24 * 3, freq='1min', start='2019-08-29')
    b = _walk(60 * 24 * 3, freq='1min', start='2020-01-01')
    ds = pe.DataStore(log=lambda *a_, **k: None)
    ds.set_base(pd.concat([a, b]))
    filler = _walk(60 * 24 * 2, freq='1min', start='2019-10-01')
    filler['era'] = pe.ERA_SPOT
    monkeypatch.setattr(ds, '_spot_month', lambda y, m: filler if (y, m) == (2019, 10) else None)
    fixed = ds.repair_gaps()
    assert fixed == ['2019-10'] and (ds.base.index.month == 10).sum() == len(filler)


def test_journal_sync_adds_new_procedures_to_old_journal(pe):
    j = pe.ResearchJournal.load()
    old = dict(j.d)
    old['procedures'] = old['procedures'][:100]
    seed = pe.research_seed()
    assert pe._research_sync(old, seed) and len(set(old['procedures'])) == len(set(seed['procedures']))
