"""
6차 자료 받기 (공개 아카이브만, 키 없음): 바이낸스 USDT 무기한 '전 종목'(상장 폐지 포함)의 1d 봉.
생존 편향을 피하려고 그날그날 거래대금 순위로 종목을 고른다(시점 기준 유니버스). 결과: ~/CoinData_Matrix/r6/alts_1d.parquet
열: date, symbol, open, high, low, close, volume, qvol(USDT 거래대금)
실행: python research/r6_data_2026-10-29.py   (처음 한 번 수 분, 이후 캐시)
"""
import io
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

HOME = os.path.join(os.path.expanduser('~'), 'CoinData_Matrix')
OUT = os.path.join(HOME, 'r6')
RAW = os.path.join(OUT, 'raw_1d')
S3 = 'https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix='
LAST_MONTH = '2026-09'


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


def listing(prefix, what='Prefix'):
    out, marker = [], ''
    while True:
        x = get(S3 + urllib.parse.quote(prefix) + ('&delimiter=/' if what == 'Prefix' else '')
                + (f'&marker={urllib.parse.quote(marker)}' if marker else '')).decode()
        if what == 'Prefix':
            ps = re.findall(r'<Prefix>([^<]+)</Prefix>', x)[1:]
            out += [p_[len(prefix):].strip('/') for p_ in ps]
            last = ps[-1] if ps else ''
        else:
            ps = re.findall(r'<Key>([^<]+)</Key>', x)
            out += ps
            last = ps[-1] if ps else ''
        if '<IsTruncated>true</IsTruncated>' not in x or not last:
            return out
        nm = re.findall(r'<NextMarker>([^<]+)</NextMarker>', x)
        marker = nm[0] if nm else last


def parse_1d(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(f, header=None)
    if not str(df.iloc[0, 0]).isdigit():
        df = df.iloc[1:]
    df = df.iloc[:, [0, 1, 2, 3, 4, 5, 7]].astype(float)
    df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'qvol']
    t = df['open_time'].astype('int64')
    t = t.where(t < 1e14, t // 1000)
    df['date'] = pd.to_datetime(t, unit='ms').dt.normalize()
    return df.drop(columns='open_time')


def one(sym):
    path = os.path.join(RAW, f'{sym}.pkl')
    if os.path.exists(path):
        return sym, 'cached'
    keys = [k for k in listing(f'data/futures/um/monthly/klines/{sym}/1d/', what='Key') if k.endswith('.zip')]
    keys = [k for k in keys if re.search(r'-(\d{4}-\d{2})\.zip$', k).group(1) <= LAST_MONTH]
    parts = []
    for k in keys:
        raw = get('https://data.binance.vision/' + urllib.parse.quote(k))
        if raw is None:
            continue
        try:
            parts.append(parse_1d(raw))
        except Exception:
            continue
    df = pd.concat(parts) if parts else pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume', 'qvol', 'date'])
    df['symbol'] = sym
    df.to_pickle(path)
    return sym, len(df)


def main():
    os.makedirs(RAW, exist_ok=True)
    syms = [s for s in listing('data/futures/um/monthly/klines/') if s.endswith('USDT')]
    print(f'USDT 무기한 종목 {len(syms)}개 (상장 폐지 포함)', flush=True)
    done = 0
    with ThreadPoolExecutor(24) as ex:
        for sym, n in ex.map(one, syms):
            done += 1
            if done % 100 == 0:
                print(f'  {done}/{len(syms)} …', flush=True)
    parts = [pd.read_pickle(os.path.join(RAW, f'{s}.pkl')) for s in syms if os.path.exists(os.path.join(RAW, f'{s}.pkl'))]
    df = pd.concat([p_ for p_ in parts if len(p_)])
    df = df.drop_duplicates(['symbol', 'date']).sort_values(['date', 'symbol']).reset_index(drop=True)
    df.to_parquet(os.path.join(OUT, 'alts_1d.parquet'))
    print(f'저장: {len(df):,}행 · 종목 {df["symbol"].nunique()} · {df["date"].min().date()} ~ {df["date"].max().date()}')


if __name__ == '__main__':
    sys.exit(main())
