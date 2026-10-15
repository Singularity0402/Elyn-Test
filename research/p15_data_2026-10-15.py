"""
P15 자료 받기 (공개 아카이브만, 키 없음): ① 펀딩 기록이 있는 USDT 무기한 목록·현물 목록 ② 무기한마다 월별 펀딩 ③ 극단 펀딩이 있었던
(코인, 달)의 선물·현물 1h 봉. 결과는 ~/CoinData_Matrix/research_p15/ 에 둔다. 그 뒤 research/p15_carry_2026-10-15.py 를 돌린다.
실행: python research/p15_data_2026-10-15.py   (처음 한 번 수십 분, 이후 캐시)
"""
import io
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

HOME = os.path.join(os.path.expanduser('~'), 'CoinData_Matrix')
OUT = os.path.join(HOME, 'research_p15')
FUND = os.path.join(HOME, 'raw', 'funding_all')
KDIR = os.path.join(HOME, 'raw', 'p15_1h')
S3 = 'https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix='


def get(url, tries=4):
    for k in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=60).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1 + k)
        except Exception:
            time.sleep(1 + k)
    return None


def listing(prefix):
    out, marker = [], ''
    while True:
        x = get(S3 + urllib.parse.quote(prefix) + '&delimiter=/' + (f'&marker={urllib.parse.quote(marker)}' if marker else '')).decode()
        ps = re.findall(r'<Prefix>([^<]+)</Prefix>', x)[1:]
        out += [p_[len(prefix):].strip('/') for p_ in ps]
        if '<IsTruncated>true</IsTruncated>' not in x:
            return out
        nm = re.findall(r'<NextMarker>([^<]+)</NextMarker>', x)
        marker = nm[0] if nm else ps[-1]


def funding_one(sym):
    path = os.path.join(FUND, f'{sym}.csv')
    if os.path.exists(path):
        return
    x = get(S3 + urllib.parse.quote(f'data/futures/um/monthly/fundingRate/{sym}/')).decode()
    rows = []
    for k in [k for k in re.findall(r'<Key>([^<]+)</Key>', x) if k.endswith('.zip')]:
        raw = get('https://data.binance.vision/' + urllib.parse.quote(k))
        if raw is None:
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            with z.open(z.namelist()[0]) as f:
                df = pd.read_csv(f)
        if 'calc_time' not in df.columns:
            df.columns = ['calc_time', 'funding_interval_hours', 'last_funding_rate'][:len(df.columns)]
        rows.append(df[['calc_time', 'funding_interval_hours', 'last_funding_rate']])
    (pd.concat(rows) if rows else pd.DataFrame(columns=['calc_time', 'funding_interval_hours', 'last_funding_rate'])).to_csv(path, index=False)


def parse_1h(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(f, header=None)
    if not str(df.iloc[0, 0]).isdigit():
        df = df.iloc[1:]
    df = df.iloc[:, :6].astype(float)
    df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume']
    t = df['open_time'].astype('int64')
    t = t.where(t < 1e14, t // 1000)                 # 2025 이후 현물은 마이크로초
    df.index = pd.to_datetime(t, unit='ms')
    return df[['open', 'high', 'low', 'close']]


def kline_month(market, sym, per, now):
    if per == pd.Period(now, 'M'):
        parts = []
        for day in pd.date_range(f'{per}-01', pd.Timestamp(now) - pd.Timedelta(days=1)):
            raw = get('https://data.binance.vision/' + urllib.parse.quote(f'data/{market}/daily/klines/{sym}/1h/{sym}-1h-{day:%Y-%m-%d}.zip'))
            if raw:
                parts.append(parse_1h(raw))
        return pd.concat(parts) if parts else None
    raw = get('https://data.binance.vision/' + urllib.parse.quote(f'data/{market}/monthly/klines/{sym}/1h/{sym}-1h-{per.year:04d}-{per.month:02d}.zip'))
    return parse_1h(raw) if raw else None


def main():
    for d in (OUT, FUND, KDIR):
        os.makedirs(d, exist_ok=True)
    fut = [s for s in listing('data/futures/um/monthly/fundingRate/') if s.endswith('USDT')]
    spot = set(listing('data/spot/monthly/klines/'))
    print('USDT 무기한', len(fut), '· 현물 심볼', len(spot), flush=True)
    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(funding_one, fut))
    rows = []
    for sym in fut:
        try:
            d = pd.read_csv(os.path.join(FUND, f'{sym}.csv'))
        except Exception:
            continue
        if len(d):
            d['sym'] = sym
            rows.append(d)
    F = pd.concat(rows)
    F['t'] = pd.to_datetime(F['calc_time'] // 1000 * 1000, unit='ms')
    F['rate8'] = F['last_funding_rate'] * 8.0 / F['funding_interval_hours'].clip(lower=1)
    F = F[(F['t'] >= '2020-01-01') & (F['t'] < '2026-10-04')]

    def spot_of(sym):
        if sym in spot:
            return sym, 1.0
        for pre, mul in (('1000000', 1e6), ('10000', 1e4), ('1000', 1e3), ('1M', 1e6)):
            if sym.startswith(pre) and sym[len(pre):] in spot:
                return sym[len(pre):], mul
        return None, None
    spotmap = {s_: spot_of(s_) for s_ in F['sym'].unique()}
    pd.to_pickle(dict(F=F, spotmap=spotmap), os.path.join(OUT, 'p15_funding.pkl'))
    ev = F[(F['rate8'] >= 0.001) & F['sym'].map(lambda s_: bool(spotmap[s_][0]))]
    need = set()
    for s_, t in zip(ev['sym'], ev['t']):
        need.add((s_, t.to_period('M')))
        need.add((s_, (t + pd.Timedelta(days=8)).to_period('M')))
    need = sorted(need)
    pd.to_pickle(need, os.path.join(OUT, 'p15_need.pkl'))
    now = pd.Timestamp.utcnow().tz_localize(None)

    def job(item):
        sym, per = item
        path = os.path.join(KDIR, f'{sym}_{per}.pkl')
        if os.path.exists(path):
            return
        sp, mul = spotmap[sym]
        pd.to_pickle(dict(perp=kline_month('futures/um', sym, per, now), spot=kline_month('spot', sp, per, now), mul=mul, spot_sym=sp), path)
    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(job, need))
    print('극단 펀딩 정산', len(ev), '· (코인, 달)', len(need), '· 끝', flush=True)


if __name__ == '__main__':
    main()
