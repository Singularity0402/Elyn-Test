# -*- coding: utf-8 -*-
"""
================================================================================
 PatternEdge V612 "HONEST NULL"
 BTCUSDT 무기한선물 — Analog-first 24/7 의사결정 지원 (주문은 사람이 직접 클릭)
================================================================================
 실행 : Windows → Python IDLE → File > Open → pattern_edge_v612.py → F5
        필수  pip install numpy pandas requests
        권장  pip install pyarrow numba matplotlib
 옵션 : python pattern_edge_v612.py --selftest               오프라인 불변식 자가검사
        python pattern_edge_v612.py --once                   콘솔 1회 전체 스캔
        python pattern_edge_v612.py --walkforward 15m 2024-01-01 [--null] [--surrogate]
                                                             생산엔진 워크포워드 검증

 절대규칙
   · 이 프로그램은 주문을 넣지 않는다. Buy/Sell/TP/SL 제출·청산 자동화 없음.
   · private/signed 거래 API, API key/secret/signature 를 사용·저장하지 않는다.
   · 공개 시장데이터(GET)만 허용 목록(allowlist) 안에서 호출한다.
   · research shadow(가상 추적)와 사용자의 실제 수동 포지션은 서로 다른 상태다.
   · WAIT 은 기존 actionable signal 을 지우지 못한다. 늦게 보면 옛 ENTRY 를
     추격하지 않고 현재 시장에서 전체 모델을 다시 통과시킨다.

 정직성
   · 과거 유사성은 미래를 보장하지 않는다. 이 파일 자체는 수익성 증거가 아니다.
   · Evidence ladder: E2(엔지니어링) → E3(purged OOF) → E4(워크포워드)
     → E5(prospective shadow) → E6(수동 실거래 관찰). 실데이터 E4+ 전에는
     신호를 '검증된 엣지'로 간주하지 말 것.

 V611 → V612 변경 요약 (상세: AUDIT_V611_V612.md)
   F-01   WAIT 경로 tuple arity 크래시 + 15초 재시도 폭주
          → 모든 판정은 dict 하나로 반환, TF별 예외 격리, 실패해도 bar-key 기록,
            연속 실패 지수 backoff, 3회 연속 실패 시 CRITICAL 알림
   F-02   shadow 진입시각이 신호 이전으로 backdate
          → 신호 '감지 시각' 이후에 시작한 1분봉부터만 채점, 체결가 = 그 봉 시가
   F-03   이름만 block bootstrap → stationary block bootstrap 실제 구현
   F-04   observed(유사도 가중) ≠ null(균등가중) 추정량 불일치
          → null 도 동일 가중치(무작위 배정)·동일 교차검증·동일 max-over-side
   F-05   주문표 파라미터 EV 를 OOF 절차 EV 와 분리 계산, 둘 다 양수여야 함
   F-06   다중검정 family 에 timeframe 포함 (TF 간 최선 선택을 Bonferroni 보정)
   F-09   N_eff = min(가중치 N_eff, 시간군집 N_eff)
          (V611: cap 0.09 때문에 N_eff ≥ 11.1 이 수학적으로 보장 → 게이트 10 은 무력)
   R1-N01 shadow 예외 침묵 → malformed shadow 는 격리(QUARANTINED) + CRITICAL 표시
   ST-09  edge 가 100% 사라져도 파괴적이지 않은 위험만 허용 (MC 낙폭 제약)
   R-unit OOF 손익을 실제 사이징 분모(SL거리+비용) 기준 R 로 환산
   기회   shadow 1개가 모든 신규 스캔을 막던 구조 제거 → 신호별 독립 shadow,
          포트폴리오 open-risk 한도, 같은 방향 중복신호 군집 한도
   알림   소리 + 최상단 경고창 + 작업표시줄 깜빡임 + 2/5/15분 재알림 (재시작 후에도 유지)
   Tk     모든 위젯 접근을 GUI 스레드로 marshal (queue)
   수동   '내가 진입함' 포지션 추적 → TP/SL/시간만료/반대신호 EXIT_RECOMMENDED
   상태   append-only 이벤트 원장에서 상태를 재구성 (상태파일 손상 시 자동 복구)
   검증   V611 에 없던 '생산엔진' 워크포워드 + 가짜 BTC 대조군 + block-bootstrap CI

 면책 : 통계적 참고 도구. 모든 주문과 손실의 책임은 사용자에게 있다.
================================================================================
"""

from __future__ import annotations

import io
import os
import sys
import json
import math
import time
import copy
import queue
import random
import zipfile
import hashlib
import logging
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import numpy as np
import pandas as pd

__version__ = 'V612-HONEST-NULL'
VERSION = 'V612'
SCRIPT_NAME = 'pattern_edge_v612.py'

# ─────────────────────────── 선택 의존성 ────────────────────────────
try:
    import requests
    REQUESTS_OK = True
except Exception:                      # urllib 로 대체한다 (기능 동일, 느릴 뿐)
    requests = None
    REQUESTS_OK = False
import urllib.request

import importlib.util
PARQUET_OK = importlib.util.find_spec('pyarrow') is not None

try:
    from numba import njit
    NUMBA_OK = True
except Exception:
    NUMBA_OK = False

    def njit(*a, **k):
        def wrap(fn):
            return fn
        return wrap

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo('Asia/Seoul')
except Exception:                      # tzdata 없는 윈도우 대비: 고정 +9h
    _KST = timezone(timedelta(hours=9))

# =============================================================================
# [1] 설정 — 단 한 곳에서만 정의한다 (V611 의 V200/V400/V500/V600 중복 설정 제거)
# =============================================================================
SYMBOL = 'BTCUSDT'
INTERVALS = {'1m': 1, '5m': 5, '15m': 15, '1h': 60}

# K = 기억(패턴) 길이, H = 최대 보유 봉수. 각 모델은 자기 봉이 닫힐 때만 평가된다.
MODELS = {
    '5m':  dict(K=288, H=24, topk=36, label='SCALP-5M'),    # 24h 기억 → 최대 2h 보유
    '15m': dict(K=192, H=16, topk=36, label='CORE-15M'),    # 48h 기억 → 최대 4h 보유
    '1h':  dict(K=168, H=12, topk=32, label='SWING-1H'),    # 7일 기억 → 최대 12h 보유
}
SCALE_FACTORS = (0.5, 1.0, 2.0)

# ── Analog 검색 ──────────────────────────────────────────────────
ANALOG_WEIGHTS = {'shape': 0.50, 'ret': 0.20, 'volume': 0.10, 'vol': 0.10, 'rng': 0.10}
CAND_POOL = 900
MIN_NEIGHBORS = 18
DTW_BAND_FRAC = 0.05
WEIGHT_CAP = 0.09                 # 한 analog 의 최대 영향력
NEFF_TIME_GAP_DAYS = 10.0         # 이 간격 안의 analog 들은 같은 '시간 군집'(같은 국면)으로 본다
VOL_BROAD = (0.40, 2.50)          # 변동성 배율 허용 범위 (검색·스케일 공통)
SPOT_PENALTY = 0.05
RECENCY_HALF_LIFE_DAYS = 900.0

# ── 통계 게이트 ──────────────────────────────────────────────────
MIN_MED_SHAPE = 0.78
MIN_NEFF = 12.0                   # min(가중 N_eff, 시간군집 N_eff) 기준 — 이제 실제로 작동한다
EDGE_PROB_MIN = 0.70
EDGE_Q = 0.15
EDGE_BOOT_N = 1200
SIDE_GAP_MIN = 0.04
VOTE_EDGE_PROB = 0.62
MIN_RR = 1.3
MIN_MOVE_COST_MULT = 3.0
NULL_N_FINAL = 400                # 최종 후보만 비싼 matched-null 을 치른다
FAMILY_ALPHA = 0.10
# F-06: 실제로 '여러 대안 중 고르는' 차원은 timeframe 이다 (가장 좋은 TF 의 신호가 채택됨).
#       scale(K/2, K, 2K)은 주 scale K 가 사전에 고정되고 나머지는 AND 조건(합의)이라
#       거짓양성을 늘리지 않으므로 family 에 넣지 않는다. (넣으면 검정력이 사라진다 — AUDIT 참고)
FAMILY_SIZE = len(MODELS)
NULL_SEED = 61220260930

# ── 위험 / 성장 ─────────────────────────────────────────────────
RISK_CAP = 0.010                  # 트레이드당 계좌위험 '천장' (최적값이 아니다)
RISK_FLOOR = 0.0005               # 이보다 작으면 경제적으로 무의미 → WAIT
PORTFOLIO_MAX_OPEN_RISK = 0.020   # 동시에 열린 shadow/수동 위험 합계 한도
CLUSTER_MAX_RISK = RISK_CAP       # 같은 방향·겹치는 보유구간 신호들의 위험 합계 한도
MARGIN_CAP = 0.30
MAX_LEV = 4
MMR = 0.005                       # 유지증거금률 보수 가정 (청산거리 근사용)
GROWTH_BOOT = 700
GROWTH_Q = 0.10
GROWTH_PROB_MIN = 0.80
GROWTH_DECAY_EVAL = 0.25          # 목적함수는 edge 25% 감쇠를 가정한 성장률로 평가
MC_PATHS = 600
MC_TRADES = 250
MC_BLOCK = 3                      # 손실 군집을 흉내내는 stationary block 평균 길이
MAX_DD, MAX_DD_PROB = 0.25, 0.05                      # edge 유지 가정
ST09_MAX_DD, ST09_MAX_DD_PROB = 0.30, 0.05            # edge 100% 소멸 가정 (ST-09)
ST09_FLOOR, ST09_FLOOR_PROB = 0.60, 0.01
DAILY_MAX_LOSSES = 3
DAILY_MAX_LOSS_FRAC = 0.03

# ── 비용 ────────────────────────────────────────────────────────
ENTRY_TYPE = 'taker'
TP_TYPE = 'maker'
SL_TYPE = 'taker'
TAKER_FEE = float(os.environ.get('PATTERNEDGE_TAKER_FEE', 0.00050))
MAKER_FEE = float(os.environ.get('PATTERNEDGE_MAKER_FEE', 0.00020))
SLIPPAGE_T = float(os.environ.get('PATTERNEDGE_SLIPPAGE_T', 0.00020))
FUNDING_PER_8H = float(os.environ.get('PATTERNEDGE_FUNDING_RESERVE_8H', 0.00010))
MAKER_TP_THROUGH = 0.0001         # 지정가 익절은 TP 를 1bp 이상 '관통'해야 체결로 인정 (대기열 보수)

# ── 시장 컨텍스트 (방향 생성 금지 — veto/축소만) ─────────────────
SPREAD_MAX_BPS = 4.0
FUNDING_ADVERSE = 0.0010
FUNDING_THROTTLE = 0.0005
OI_SHOCK = 0.035
TAKER_OPPOSE = 0.72

# ── 거래소 규칙 기본값 (exchangeInfo 실패 시에만, 보수적) ──────────
FALLBACK_RULES = dict(min_notional=100.0, tick_size=0.1, qty_step=0.001, min_qty=0.001)

# ── 데이터 ──────────────────────────────────────────────────────
VISION_BASE = 'https://data.binance.vision/data'
FAPI_BASE = 'https://fapi.binance.com'
FUT_FIRST_MONTH = (2019, 9)
SPOT_FIRST_MONTH = (2017, 8)
USE_SPOT_PREHISTORY = True
MAX_STALE_MIN = 5
PERSIST_EVERY_SEC = 1200          # 1분봉 전체 재저장은 20분에 한 번 + 종료 시 (V611: 매 갱신)
ERA_FUT, ERA_SPOT = 1.0, 0.0
STORE_COLS = ['open', 'high', 'low', 'close', 'volume', 'taker_buy_base', 'trades', 'era']

# ── 런타임 ──────────────────────────────────────────────────────
AUTO_POLL_MS = 15_000
REALERT_MINUTES = (2, 5, 15)      # 미확인 재알림 간격, 이후 중단 (카드는 남는다)
MAX_DRIFT_SL_FRAC = 0.35          # 기준봉 종가 대비 SL거리의 35% 이상 불리하게 움직였으면 추격 금지
FAIL_BACKOFF_SEC = (30, 60, 120, 300, 600)
CRITICAL_AFTER_FAILS = 3
MAX_SIGNALS_IN_STATE = 300


def _model_fingerprint():
    cfg = dict(models=MODELS, scales=SCALE_FACTORS, w=ANALOG_WEIGHTS, cap=WEIGHT_CAP,
               neff_gap=NEFF_TIME_GAP_DAYS, shape=MIN_MED_SHAPE, neff=MIN_NEFF,
               edge=EDGE_PROB_MIN, edge_q=EDGE_Q, rr=MIN_RR, null=NULL_N_FINAL,
               alpha=FAMILY_ALPHA, family=FAMILY_SIZE, risk=RISK_CAP, port=PORTFOLIO_MAX_OPEN_RISK,
               lev=MAX_LEV, margin=MARGIN_CAP, growth=(GROWTH_PROB_MIN, GROWTH_DECAY_EVAL),
               st09=(ST09_MAX_DD, ST09_MAX_DD_PROB, ST09_FLOOR, ST09_FLOOR_PROB),
               cost=(TAKER_FEE, MAKER_FEE, SLIPPAGE_T, FUNDING_PER_8H, MAKER_TP_THROUGH))
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:12]


MODEL_ID = _model_fingerprint()


# =============================================================================
# [2] 경로 · 로그 · 상태판(HEALTH) — import 시에는 아무 파일도 만들지 않는다
# =============================================================================
class Paths:
    base = None

    @classmethod
    def _default_base(cls):
        env = os.environ.get('PATTERNEDGE_HOME')
        if env:
            return env
        if os.name == 'nt':
            return r'C:\CoinData_Matrix'          # V611 과 같은 위치 → 받아둔 데이터 재사용
        return os.path.join(os.path.expanduser('~'), 'CoinData_Matrix')

    @classmethod
    def init(cls, base=None):
        """최초 실행 시 폴더를 만든다 (REL-005). 쓰기 불가면 문서 폴더로 대체."""
        cands = [base] if base else [cls._default_base(),
                                     os.path.join(os.path.expanduser('~'), 'Documents', 'CoinData_Matrix')]
        last = None
        for b in cands:
            try:
                os.makedirs(os.path.join(b, 'raw'), exist_ok=True)
                t = os.path.join(b, '.wtest')
                with open(t, 'w') as f:
                    f.write('ok')
                os.remove(t)
                cls.base = b
                break
            except Exception as e:
                last = e
        if cls.base is None:
            raise OSError(f'데이터 폴더를 만들 수 없습니다: {last}')
        return cls.base

    @classmethod
    def p(cls, name):
        if cls.base is None:
            cls.init()
        return os.path.join(cls.base, name)

    raw = classmethod(lambda cls: cls.p('raw'))
    data_parquet = classmethod(lambda cls: cls.p(f'{SYMBOL}_1m_v612.parquet'))
    data_pickle = classmethod(lambda cls: cls.p(f'{SYMBOL}_1m_v612.pkl'))
    legacy_parquet = classmethod(lambda cls: cls.p(f'{SYMBOL}_1m_v200.parquet'))
    legacy_csv = classmethod(lambda cls: cls.p(f'{SYMBOL}_1m_v200.csv'))
    state = classmethod(lambda cls: cls.p(f'{SYMBOL}_v612_state.json'))
    ledger = classmethod(lambda cls: cls.p(f'{SYMBOL}_v612_ledger.jsonl'))
    decisions = classmethod(lambda cls: cls.p(f'{SYMBOL}_v612_decisions.jsonl'))
    rules_cache = classmethod(lambda cls: cls.p(f'{SYMBOL}_v612_exchange_rules.json'))
    log_file = classmethod(lambda cls: cls.p('pattern_edge_v612.log'))
    lock_file = classmethod(lambda cls: cls.p('pattern_edge_v612.lock'))


LOG = logging.getLogger('patternedge')
LOG.addHandler(logging.NullHandler())


def setup_logging(console=True):
    from logging.handlers import RotatingFileHandler
    LOG.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(threadName)s %(message)s')
    if not any(isinstance(h, RotatingFileHandler) for h in LOG.handlers):
        fh = RotatingFileHandler(Paths.log_file(), maxBytes=5_000_000, backupCount=3, encoding='utf-8')
        fh.setFormatter(fmt)
        LOG.addHandler(fh)
    if console and not any(type(h) is logging.StreamHandler for h in LOG.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        LOG.addHandler(sh)


class Health:
    """
    '조용한 실패' 금지판. 모든 비정상은 여기 기록되고 GUI 상단에 항상 보인다.
    level: 'WARN' | 'CRITICAL'. clear() 는 해당 조건이 실제로 해소됐을 때만 호출한다.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.items = {}

    def set(self, key, level, msg):
        with self._lock:
            old = self.items.get(key)
            since = old['since'] if old and old['level'] == level else _iso_now()
            self.items[key] = dict(level=level, msg=str(msg), since=since)
        (LOG.error if level == 'CRITICAL' else LOG.warning)(f'[HEALTH {level}] {key}: {msg}')

    def clear(self, key):
        with self._lock:
            self.items.pop(key, None)

    def critical(self):
        with self._lock:
            return {k: v for k, v in self.items.items() if v['level'] == 'CRITICAL'}

    def lines(self):
        with self._lock:
            return [f"{v['level']:<8} {k}: {v['msg']}" for k, v in sorted(self.items.items())]


HEALTH = Health()


# =============================================================================
# [3] 시간 유틸 — 모든 내부 시각은 tz-naive UTC
# =============================================================================
def utcnow():
    """테스트에서 교체 가능하도록 단일 진입점으로 둔다."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso_now():
    return utcnow().replace(microsecond=0).isoformat() + 'Z'


def to_naive_utc(x):
    t = pd.Timestamp(x)
    if t.tzinfo is not None:
        t = t.tz_convert('UTC').tz_localize(None)
    return t


def floor_time(dt, minutes):
    epoch = datetime(1970, 1, 1)
    k = int((dt - epoch).total_seconds() // (minutes * 60))
    return epoch + timedelta(minutes=minutes * k)


def fmt_kst(x):
    try:
        t = pd.Timestamp(x)
        if t.tzinfo is None:
            t = t.tz_localize('UTC')
        return t.tz_convert(_KST).strftime('%Y-%m-%d %H:%M:%S KST')
    except Exception:
        return str(x or '-')


def ts_ns(index):
    """DatetimeIndex → int64 ns (pandas 2.x/3.x 해상도 차이에 안전)."""
    return np.asarray(pd.DatetimeIndex(index).values.astype('datetime64[ns]')).astype('int64')


def month_iter(y0, m0, y1, m1):
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def bar_key(tf, now=None):
    """가장 최근에 '완결된' tf 봉의 번호."""
    now = now or utcnow()
    minute_epoch = int((now - datetime(1970, 1, 1)).total_seconds() // 60)
    return (minute_epoch // INTERVALS[tf]) - 1


def json_safe(obj, _depth=0):
    if _depth > 12:
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): json_safe(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v, _depth + 1) for v in obj]
    if isinstance(obj, np.ndarray):
        return [json_safe(v, _depth + 1) for v in obj.tolist()]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime)):
        return pd.Timestamp(obj).isoformat()
    return obj


def fnum(x, default=float('nan')):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


# =============================================================================
# [4] 공개 HTTP 클라이언트 — GET 전용 · 허용목록 · 유한 재시도 · 서킷브레이커
# -----------------------------------------------------------------------------
#  REL-012: 서명/개인 거래 엔드포인트는 구조적으로 호출 불가능하다.
#           허용목록 밖의 호스트/경로는 요청 전에 PermissionError.
# =============================================================================
class PublicHttp:
    ALLOWED = {
        'fapi.binance.com': ('/fapi/v1/klines', '/fapi/v1/exchangeInfo', '/fapi/v1/premiumIndex',
                             '/fapi/v1/ticker/bookTicker', '/fapi/v1/openInterest',
                             '/fapi/v1/ticker/24hr', '/fapi/v1/ticker/price', '/futures/data/'),
        'data.binance.vision': ('/data/',),
    }

    def __init__(self, timeout=20, retries=3, enabled=True):
        self.timeout = timeout
        self.retries = int(retries)
        self.enabled = bool(enabled)
        self._fails = 0
        self._open_until = 0.0
        self._lock = threading.Lock()
        self.n_requests = 0

    @classmethod
    def check_allowed(cls, url):
        u = urlparse(url)
        if u.scheme != 'https':
            raise PermissionError(f'https 아님: {url}')
        prefixes = cls.ALLOWED.get(u.hostname or '')
        if not prefixes or not any(u.path.startswith(p) for p in prefixes):
            raise PermissionError(f'허용되지 않은 공개 엔드포인트: {u.hostname}{u.path}')
        q = (u.query or '').lower()
        if 'signature=' in q or 'timestamp=' in q:
            raise PermissionError('서명 파라미터는 금지')
        return True

    def get(self, url, timeout=None):
        self.check_allowed(url)
        if not self.enabled:
            raise ConnectionError('offline mode')
        with self._lock:
            if time.time() < self._open_until:
                raise ConnectionError(f'서킷 열림 — {self._open_until - time.time():.0f}초 후 재시도')
        timeout = timeout or self.timeout
        last = None
        for attempt in range(self.retries + 1):
            try:
                self.n_requests += 1
                if REQUESTS_OK:
                    r = requests.get(url, timeout=timeout, headers={'User-Agent': f'PatternEdge/{VERSION}'})
                    code, body, retry_after = r.status_code, r.content, r.headers.get('Retry-After')
                else:
                    req = urllib.request.Request(url, headers={'User-Agent': f'PatternEdge/{VERSION}'})
                    try:
                        with urllib.request.urlopen(req, timeout=timeout) as resp:
                            code, body, retry_after = resp.status, resp.read(), None
                    except urllib.error.HTTPError as he:
                        code, body, retry_after = he.code, b'', he.headers.get('Retry-After')
                if code == 200:
                    with self._lock:
                        self._fails = 0
                    return body
                if code in (404, 400, 403):
                    raise FileNotFoundError(f'HTTP {code} {url}')       # 재시도 무의미
                last = IOError(f'HTTP {code} {url}')
                wait = min(60.0, float(retry_after)) if (retry_after and code in (418, 429)) \
                    else min(8.0, 0.5 * 2 ** attempt)
            except FileNotFoundError:
                raise
            except Exception as e:
                last = e
                wait = min(8.0, 0.5 * 2 ** attempt)
            if attempt < self.retries:
                time.sleep(wait + random.uniform(0, 0.25))
        with self._lock:
            self._fails += 1
            if self._fails >= 6:
                self._open_until = time.time() + 60.0
        raise ConnectionError(f'공개 API 실패({self.retries + 1}회): {last}')

    def get_json(self, url, timeout=None):
        return json.loads(self.get(url, timeout=timeout).decode('utf-8'))


# =============================================================================
# [5] 데이터 레이어 — 1분봉이 유일한 원본, 상위 TF 는 스냅샷에서 리샘플
# =============================================================================
VISION_COLS = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
               'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore']


def _normalize_epoch_ms(series):
    v = pd.to_numeric(series, errors='coerce').astype('float64')
    med = np.nanmedian(v)
    if med > 1e15:                     # 2025년부터 아카이브 일부가 microseconds
        v = v / 1000.0
    return v.astype('int64')


def parse_vision_zip(raw_bytes, era):
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            head = f.readline().decode('utf-8', 'ignore').split(',')[0].strip()
        has_header = not head.replace('.', '').isdigit()
        with z.open(name) as f:
            df = pd.read_csv(f, header=0 if has_header else None, names=VISION_COLS, usecols=range(12))
    ts = _normalize_epoch_ms(df['open_time'])
    out = pd.DataFrame({c: pd.to_numeric(df[c], errors='coerce').astype('float64')
                        for c in ('open', 'high', 'low', 'close', 'volume', 'taker_buy_base', 'trades')})
    out['era'] = float(era)
    out.index = pd.DatetimeIndex(pd.to_datetime(ts.values, unit='ms'), name='timestamp')
    return out.sort_index()


def rest_klines_1m(http, start_ms, limit=1500):
    url = (f'{FAPI_BASE}/fapi/v1/klines?symbol={SYMBOL}&interval=1m'
           f'&startTime={int(start_ms)}&limit={int(limit)}')
    data = http.get_json(url, timeout=30)
    if not data:
        return None
    arr = np.array(data, dtype=object)
    out = pd.DataFrame({
        'open': arr[:, 1].astype('float64'), 'high': arr[:, 2].astype('float64'),
        'low': arr[:, 3].astype('float64'), 'close': arr[:, 4].astype('float64'),
        'volume': arr[:, 5].astype('float64'), 'taker_buy_base': arr[:, 9].astype('float64'),
        'trades': arr[:, 8].astype('float64')})
    out['era'] = ERA_FUT
    out.index = pd.DatetimeIndex(pd.to_datetime(arr[:, 0].astype('int64'), unit='ms'), name='timestamp')
    return out.sort_index()


def normalize_frame(df):
    """인덱스 tz-naive DatetimeIndex·정렬·중복제거·스키마 고정. 실패는 예외로 올린다."""
    if df is None or len(df) == 0:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            idx = pd.to_datetime(pd.Index(df.index), errors='coerce', format='mixed')
        except (TypeError, ValueError):                       # pandas < 2.0
            idx = pd.to_datetime(pd.Index(df.index), errors='coerce')
        bad = np.asarray(pd.isna(idx))
        if bad.all():
            raise ValueError('인덱스를 날짜로 변환할 수 없습니다 (캐시 손상)')
        df = df.loc[~bad].copy()
        df.index = pd.DatetimeIndex(idx[~bad])
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert('UTC').tz_localize(None)
    df.index.name = 'timestamp'
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        df = df[~df.index.duplicated(keep='last')].sort_index()
    for c in STORE_COLS:
        if c not in df.columns:
            df[c] = ERA_FUT if c == 'era' else 0.0
    return df[STORE_COLS].astype('float64')


def dq_report(df):
    """DQ: 행수·갭·OHLC 모순·음수/0 가격. 판정은 호출자가 한다."""
    if df is None or df.empty:
        return dict(rows=0)
    t = ts_ns(df.index) // 60_000_000_000
    d = np.diff(t)
    gaps = d[d > 1] - 1
    o, h, l, c = (df[k].values for k in ('open', 'high', 'low', 'close'))
    bad_ohlc = int(np.sum((h < np.maximum(o, c) - 1e-9) | (l > np.minimum(o, c) + 1e-9) | (l <= 0)))
    recent = t >= t[-1] - 7 * 1440
    rd = np.diff(t[recent]) if recent.sum() > 1 else np.array([1])
    return dict(rows=int(len(df)), gap_count=int(len(gaps)), gap_minutes=int(gaps.sum()) if len(gaps) else 0,
                max_gap_min=int(gaps.max()) if len(gaps) else 0, bad_ohlc=bad_ohlc,
                recent_gap_minutes=int(np.sum(rd[rd > 1] - 1)))


class DataStore:
    """
    1분봉 원본 저장소. 원본 DataFrame 은 절대 in-place 수정하지 않는다
    (갱신 = 새 프레임 교체) → 스냅샷은 락 없이 안전하게 읽힌다.
    """

    def __init__(self, http=None, log=None):
        self.http = http or PublicHttp()
        self.log = log or (lambda msg, color='black': LOG.info(msg))
        self._lock = threading.RLock()
        self._base = None
        self._dirty = False
        self._last_persist = 0.0
        self.meta = {}
        self.last_error = ''

    # ── 주입/조회 ───────────────────────────────────────────────
    def set_base(self, df):
        with self._lock:
            self._base = normalize_frame(df)
            self._update_meta()

    @property
    def base(self):
        return self._base

    # ── 디스크 ─────────────────────────────────────────────────
    def load_disk(self):
        cands = []
        if PARQUET_OK:
            cands.append(('parquet', Paths.data_parquet()))
        cands += [('pickle', Paths.data_pickle())]
        if PARQUET_OK:
            cands.append(('parquet', Paths.legacy_parquet()))
        cands.append(('csv', Paths.legacy_csv()))
        for kind, p in cands:
            if not os.path.exists(p):
                continue
            try:
                if kind == 'parquet':
                    df = pd.read_parquet(p)
                elif kind == 'pickle':
                    df = pd.read_pickle(p)
                else:
                    df = pd.read_csv(p, index_col='timestamp')
                df = normalize_frame(df)
                if df is not None and len(df):
                    self.log(f'캐시 로드: {os.path.basename(p)} ({len(df):,}봉)', 'green')
                    return df
            except Exception as e:
                HEALTH.set(f'cache:{os.path.basename(p)}', 'WARN', f'캐시 읽기 실패 → 다음 후보 사용: {e}')
        return None

    def persist(self, force=False):
        with self._lock:
            if self._base is None or self._base.empty:
                return False
            if not force and (not self._dirty or time.time() - self._last_persist < PERSIST_EVERY_SEC):
                return False
            df = self._base
        p = Paths.data_parquet() if PARQUET_OK else Paths.data_pickle()
        tmp = p + '.tmp'
        try:
            if PARQUET_OK:
                df.to_parquet(tmp)
            else:
                df.to_pickle(tmp)
            os.replace(tmp, p)
            with self._lock:
                self._dirty = False
                self._last_persist = time.time()
            HEALTH.clear('persist')
            return True
        except Exception as e:
            HEALTH.set('persist', 'WARN', f'1분봉 캐시 저장 실패 (메모리 데이터는 정상): {e}')
            return False

    # ── 벌크 구축 ───────────────────────────────────────────────
    def build_full_history(self, use_spot=USE_SPOT_PREHISTORY, progress=None):
        now = utcnow()
        jobs = []
        if use_spot:
            y1, m1 = FUT_FIRST_MONTH
            em = (y1, m1 - 1) if m1 > 1 else (y1 - 1, 12)
            jobs += [('spot', y, m) for y, m in month_iter(*SPOT_FIRST_MONTH, *em)]
        jobs += [('futures/um', y, m) for y, m in month_iter(*FUT_FIRST_MONTH, now.year, now.month)]
        parts, ok, skipped = [], 0, []
        for i, (market, y, m) in enumerate(jobs, 1):
            era = ERA_SPOT if market == 'spot' else ERA_FUT
            url = f'{VISION_BASE}/{market}/monthly/klines/{SYMBOL}/1m/{SYMBOL}-1m-{y:04d}-{m:02d}.zip'
            cache = os.path.join(Paths.raw(), f'{market.replace("/", "_")}-1m-{y:04d}-{m:02d}.zip')
            try:
                if os.path.exists(cache) and os.path.getsize(cache) > 1000:
                    with open(cache, 'rb') as f:
                        raw = f.read()
                else:
                    raw = self.http.get(url, timeout=180)
                    tmp = cache + '.tmp'
                    with open(tmp, 'wb') as f:
                        f.write(raw)
                    os.replace(tmp, cache)
                parts.append(parse_vision_zip(raw, era))
                ok += 1
            except Exception as e:
                if (y, m) == (now.year, now.month) and market != 'spot':
                    parts.extend(self._daily_fill(y, m))
                else:
                    skipped.append(f'{market} {y}-{m:02d}: {e}')
            if progress:
                progress(i, len(jobs), f'{market} {y}-{m:02d}')
        if not parts:
            raise IOError('아카이브에서 받은 데이터가 없습니다 (네트워크/방화벽 확인).')
        if skipped:
            HEALTH.set('archive', 'WARN', f'월 파일 {len(skipped)}개 누락 (예: {skipped[0]})')
        df = normalize_frame(pd.concat(parts))
        with self._lock:
            self._base = df
            self._dirty = True
            self._update_meta()
        self.persist(force=True)
        self.log(f'[구축 완료] 1분봉 {len(df):,}개 {df.index[0]} ~ {df.index[-1]} (월파일 {ok}/{len(jobs)})', 'green')
        return df

    def _daily_fill(self, y, m):
        out, d = [], datetime(y, m, 1)
        while d.month == m and d <= utcnow():
            url = f'{VISION_BASE}/futures/um/daily/klines/{SYMBOL}/1m/{SYMBOL}-1m-{d:%Y-%m-%d}.zip'
            try:
                out.append(parse_vision_zip(self.http.get(url, timeout=90), ERA_FUT))
            except FileNotFoundError:
                pass                              # 아직 게시 안 된 날짜 — REST 가 채운다
            except Exception as e:
                HEALTH.set('daily_fill', 'WARN', f'{d:%Y-%m-%d} 일별 파일 실패: {e}')
            d += timedelta(days=1)
        return out

    # ── 증분 갱신 ───────────────────────────────────────────────
    def refresh(self, force=False, progress=None):
        """완결된 1분봉까지 채운다. 실패는 삼키지 않고 HEALTH/meta 에 남긴다."""
        with self._lock:
            if self._base is None:
                self._base = self.load_disk()
            if self._base is None or self._base.empty:
                self.log('원본 없음 → 바이낸스 아카이브에서 전체 구축', 'red')
                self.build_full_history(progress=progress)
            base = self._base
            target = floor_time(utcnow(), 1) - timedelta(minutes=1)
            last = base.index[-1]
            stale_min = (target - last).total_seconds() / 60.0
            self.last_error = ''
            if force or stale_min >= 1:
                try:
                    got = []
                    cursor = int(pd.Timestamp(last).value // 10 ** 6) + 60_000
                    for _ in range(400):
                        nd = rest_klines_1m(self.http, cursor)
                        if nd is None or nd.empty:
                            break
                        got.append(nd)
                        newest = int(nd.index[-1].value // 10 ** 6)
                        if newest < cursor or nd.index[-1] >= target:
                            break
                        cursor = newest + 60_000
                        time.sleep(0.12)
                    if got:
                        new = normalize_frame(pd.concat([base] + got))
                        cutoff = floor_time(utcnow(), 1)
                        new = new[new.index < cutoff]          # 진행 중인 1분봉 제거
                        self._base = new
                        self._dirty = True
                    HEALTH.clear('data_refresh')
                except Exception as e:
                    self.last_error = f'{type(e).__name__}: {e}'
                    HEALTH.set('data_refresh', 'WARN', f'1분봉 갱신 실패: {self.last_error}')
            self._update_meta()
        self.persist()
        return self.meta

    def _update_meta(self):
        b = self._base
        if b is None or b.empty:
            self.meta = dict(rows=0, lag_min=float('inf'), error=self.last_error)
            return
        target = floor_time(utcnow(), 1) - timedelta(minutes=1)
        lag = (target - b.index[-1]).total_seconds() / 60.0
        dq = dq_report(b.iloc[-200_000:])
        self.meta = dict(rows=len(b), first=b.index[0], last=b.index[-1], lag_min=lag,
                         error=self.last_error, dq=dq,
                         fut_rows=int((b['era'].values == ERA_FUT).sum()),
                         spot_rows=int((b['era'].values == ERA_SPOT).sum()))
        if lag > MAX_STALE_MIN:
            HEALTH.set('data_stale', 'WARN', f'1분봉 지연 {lag:.0f}분 > {MAX_STALE_MIN}분 — 신규 신호 중단')
        else:
            HEALTH.clear('data_stale')

    def snapshot(self):
        with self._lock:
            if self._base is None or self._base.empty:
                raise RuntimeError('1분봉 데이터가 없습니다 — [데이터 구축] 필요')
            return Snapshot(self._base, utcnow(), dict(self.meta))

    def banner(self):
        m = self.meta
        if not m or not m.get('rows'):
            return '데이터: 없음 — [데이터 구축/복구] 필요'
        lag = m['lag_min']
        mark = '정상' if lag <= MAX_STALE_MIN else f'★지연 {lag:.0f}분★'
        dq = m.get('dq', {})
        s = (f"데이터 1분봉 {m['rows']:,} · {m['first']:%Y-%m-%d} ~ {m['last']:%Y-%m-%d %H:%M} UTC · 신선도 {mark}"
             f" · 최근7일 누락 {dq.get('recent_gap_minutes', 0)}분")
        if m.get('error'):
            s += f"\n⚠ 갱신 오류: {m['error']}"
        return s


class Snapshot:
    """한 스캔 사이클 동안 고정된 데이터 뷰. TF 프레임에 완결성(n1m) 표시."""

    def __init__(self, base, now, meta=None):
        self.base = base
        self.now = now
        self.meta = meta or {}
        self._tf = {}
        self._ch = {}
        self._lock = threading.Lock()

    def tf(self, tf):
        with self._lock:
            if tf in self._tf:
                return self._tf[tf]
            if tf == '1m':
                df = self.base.copy()
                df['n1m'] = 1.0
            else:
                mins = INTERVALS[tf]
                r = self.base.resample(f'{mins}min', label='left', closed='left', origin='epoch')
                df = r.agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
                           close=('close', 'last'), volume=('volume', 'sum'),
                           taker_buy_base=('taker_buy_base', 'sum'), trades=('trades', 'sum'),
                           era=('era', 'min'), n1m=('close', 'count'))
                df = df.dropna(subset=['open', 'high', 'low', 'close'])
                df = df[df.index < pd.Timestamp(floor_time(self.now, mins))]   # 미완결 마지막 봉 제거
            df['complete'] = (df['n1m'].values >= INTERVALS[tf]).astype(np.float64)
            self._tf[tf] = df
            return df

    def channels(self, tf):
        with self._lock:
            ch = self._ch.get(tf)
        if ch is None:
            ch = Channels(self.tf(tf))
            with self._lock:
                self._ch[tf] = ch
        return ch

    def last_price(self):
        return float(self.base['close'].values[-1])


# =============================================================================
# [6] 수학 코어 — MASS 상관 · 직접내적 검증 · 밴드 DTW · 브래킷 체결
# =============================================================================
def znorm(x):
    x = np.asarray(x, dtype=np.float64)
    s = x.std()
    return x - x.mean() if s < 1e-14 else (x - x.mean()) / s


def _sliding_ms(T, m):
    c1 = np.cumsum(np.concatenate(([0.0], T)))
    c2 = np.cumsum(np.concatenate(([0.0], T * T)))
    s1 = c1[m:] - c1[:-m]
    s2 = c2[m:] - c2[:-m]
    mu = s1 / m
    return mu, np.sqrt(np.maximum(s2 / m - mu * mu, 0.0))


def _sliding_dot(Q, T):
    m, n = len(Q), len(T)
    size = 1
    while size < n + m:
        size <<= 1
    conv = np.fft.irfft(np.fft.rfft(T, size) * np.fft.rfft(Q[::-1], size), size)
    return conv[m - 1:n]


def corr_profile(Q, T):
    """T 의 모든 길이 m 창과 Q 의 피어슨 상관 (전역 정규화로 수치안정화). 반환 (r, 창 표준편차)."""
    Q = np.asarray(Q, dtype=np.float64)
    T = np.asarray(T, dtype=np.float64)
    m = len(Q)
    k = max(len(T) - m + 1, 0)
    qs = Q.std()
    ts = T.std() if len(T) else 0.0
    if m < 2 or len(T) < m or qs < 1e-14 or ts < 1e-300:
        return np.full(k, -1.0), np.zeros(k)
    Tn = (T - T.mean()) / ts
    dot = _sliding_dot((Q - Q.mean()) / qs, Tn)
    _, sdn = _sliding_ms(Tn, m)
    with np.errstate(divide='ignore', invalid='ignore'):
        r = np.where(sdn > 1e-13, dot / (m * sdn), -1.0)
    return np.clip(np.nan_to_num(r, nan=-1.0), -1.0, 1.0), sdn * ts


def corr_exact(Q, T, starts):
    Q = np.asarray(Q, dtype=np.float64)
    T = np.asarray(T, dtype=np.float64)
    m = len(Q)
    qz = znorm(Q)
    out = np.empty(len(starts))
    for i, s in enumerate(starts):
        w = T[int(s):int(s) + m]
        sd = w.std()
        out[i] = -1.0 if sd < 1e-14 else float(np.dot(qz, (w - w.mean()) / sd) / m)
    return np.clip(out, -1.0, 1.0)


@njit(cache=False, fastmath=True)
def dtw_band(a, b, w):
    n = len(a)
    m = len(b)
    ww = w if w > abs(n - m) else abs(n - m)
    if ww < 1:
        ww = 1
    INF = 1e18
    prev = np.full(m + 1, INF)
    cur = np.full(m + 1, INF)
    prev[0] = 0.0
    for i in range(1, n + 1):
        cur[:] = INF
        lo = max(1, i - ww)
        hi = min(m, i + ww)
        for j in range(lo, hi + 1):
            d = a[i - 1] - b[j - 1]
            best = prev[j]
            if prev[j - 1] < best:
                best = prev[j - 1]
            if cur[j - 1] < best:
                best = cur[j - 1]
            cur[j] = d * d + best
        tmp = prev
        prev = cur
        cur = tmp
    return prev[m]


def pick_nonoverlap(order, k, excl):
    """점수순 후보에서 서로 excl 이상 떨어진 것만 최대 k 개."""
    chosen = []
    for idx in order:
        idx = int(idx)
        ok = True
        for c in chosen:
            if abs(idx - c) < excl:
                ok = False
                break
        if ok:
            chosen.append(idx)
            if len(chosen) >= k:
                break
    return chosen


def bracket_vec(HI, LO, CL, side, tp, sl, tp_through=MAKER_TP_THROUGH):
    """
    TP/SL 최초 도달. HI/LO/CL = (n, T) 진입가 대비 수익률 경로.
    · 같은 시점 동시 도달 → 손절 (낙관 편향 제거)
    · 지정가 익절은 TP 를 tp_through 이상 관통해야 체결 (터치만으로는 대기열 뒤일 수 있음)
    반환 (gross pnl[n], code[n])  code: 1 익절 / -1 손절 / 0 시간청산
    """
    HI = np.atleast_2d(np.asarray(HI, dtype=np.float64))
    LO = np.atleast_2d(np.asarray(LO, dtype=np.float64))
    CL = np.atleast_2d(np.asarray(CL, dtype=np.float64))
    n, T = HI.shape
    thr = tp + (tp_through if TP_TYPE == 'maker' else 0.0)
    if side > 0:
        win, lose, final = HI >= thr, LO <= -sl, CL[:, -1]
    else:
        win, lose, final = LO <= -thr, HI >= sl, -CL[:, -1]
    fw = np.where(win.any(1), win.argmax(1), T)
    fl = np.where(lose.any(1), lose.argmax(1), T)
    pnl = final.copy()
    code = np.zeros(n, dtype=np.int64)
    lose_first = (fl <= fw) & (fl < T)
    win_first = (fw < fl) & (fw < T)
    pnl[lose_first] = -sl
    code[lose_first] = -1
    pnl[win_first] = tp
    code[win_first] = 1
    return pnl, code


def _leg(kind):
    return (TAKER_FEE + SLIPPAGE_T) if kind == 'taker' else MAKER_FEE


def cost_win():
    return _leg(ENTRY_TYPE) + _leg(TP_TYPE)


def cost_lose():
    return _leg(ENTRY_TYPE) + _leg(SL_TYPE)


def funding_cost(tf, H):
    return FUNDING_PER_8H * (INTERVALS[tf] * H / 60.0 / 8.0)


def total_cost(tf, H):
    """손절 경로 왕복비용 + 펀딩 예비. 사이징 분모(sl + total_cost)와 동일해야 한다."""
    return cost_lose() + funding_cost(tf, H)


def net_pnl(pnl, code, tf, H):
    c = np.where(np.asarray(code) == 1, cost_win(), cost_lose()) + funding_cost(tf, H)
    return np.asarray(pnl, dtype=np.float64) - c


def wmean(v, w):
    v = np.asarray(v, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    ok = np.isfinite(v) & np.isfinite(w) & (w >= 0)
    if not ok.any():
        return float('nan')
    v, w = v[ok], w[ok]
    return float(np.mean(v)) if w.sum() <= 0 else float(np.dot(v, w) / w.sum())


def wquantile(v, w, q):
    v = np.asarray(v, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    ok = np.isfinite(v) & np.isfinite(w) & (w >= 0)
    if not ok.any():
        return float('nan')
    v, w = v[ok], w[ok]
    if w.sum() <= 0:
        w = np.ones_like(v)
    o = np.argsort(v)
    v, w = v[o], w[o]
    c = np.cumsum(w) / w.sum()
    return float(v[min(int(np.searchsorted(c, min(max(q, 0.0), 1.0), side='left')), len(v) - 1)])


def soft_cap_weights(raw, cap=WEIGHT_CAP):
    x = np.maximum(np.asarray(raw, dtype=np.float64), 0.0)
    if len(x) == 0:
        return x
    if not np.isfinite(x).all() or x.sum() <= 0:
        x = np.ones(len(x))
    w = x / x.sum()
    cap = max(float(cap), 1.0 / len(w))
    for _ in range(50):
        hi = w > cap + 1e-15
        if not hi.any():
            break
        excess = float((w[hi] - cap).sum())
        w[hi] = cap
        lo = ~hi
        if lo.any() and excess > 0:
            d = float(w[lo].sum())
            w[lo] += excess * (w[lo] / d if d > 0 else 1.0 / lo.sum())
        w /= w.sum()
    return w / w.sum()


def neff_weights(w):
    w = np.asarray(w, dtype=np.float64)
    return float(1.0 / max(np.square(w / max(w.sum(), 1e-12)).sum(), 1e-12))


def neff_time(end_ns, w, gap_days=NEFF_TIME_GAP_DAYS):
    """
    F-09: 시간 군집 N_eff. 끝시각이 gap_days 이내로 이어지는 analog 들은 한 국면으로 묶고
    군집 가중치 합으로 N_eff 를 다시 잰다. 같은 2주에서 나온 36개는 36개의 증거가 아니다.
    """
    end_ns = np.asarray(end_ns, dtype=np.int64)
    w = np.asarray(w, dtype=np.float64)
    if len(end_ns) == 0:
        return 0.0, 0
    o = np.argsort(end_ns)
    gap = np.diff(end_ns[o]) > int(gap_days * 86400e9)
    cid = np.concatenate(([0], np.cumsum(gap)))
    W = np.bincount(cid, weights=w[o] / max(w.sum(), 1e-12))
    return float(1.0 / max(np.square(W).sum(), 1e-12)), int(len(W))


# =============================================================================
# [7] 채널 (전부 인과적: t 시점 값은 t 이전 데이터만 사용)
# =============================================================================
class Channels:
    def __init__(self, df, vol_win=20):
        c = df['close'].values.astype(np.float64)
        h = df['high'].values.astype(np.float64)
        l = df['low'].values.astype(np.float64)
        v = np.maximum(df['volume'].values.astype(np.float64), 1e-12)
        tb = df['taker_buy_base'].values.astype(np.float64)
        n = len(c)
        lc = np.log(np.maximum(c, 1e-12))
        r = np.zeros(n)
        r[1:] = np.diff(lc)
        rv = pd.Series(r).rolling(vol_win, min_periods=2).std().ffill().bfill().values
        fl = pd.Series(np.clip(tb / v, 0.0, 1.0) - 0.5).rolling(5, min_periods=1).mean().values
        rg = pd.Series((h - l) / np.maximum(c, 1e-12)).rolling(3, min_periods=1).mean().values
        pc = np.r_[c[0], c[:-1]]
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        self.shape = lc
        self.ret = r
        self.vol = np.nan_to_num(np.log(np.maximum(rv, 1e-10)), nan=-7.0)
        self.volume = np.log1p(v)
        self.flow = np.nan_to_num(fl)
        self.rng = np.nan_to_num(rg)
        self.atr = np.nan_to_num(pd.Series(tr / np.maximum(c, 1e-12)).ewm(alpha=1 / 14.0, adjust=False).mean().values,
                                 nan=0.005)
        self.era = df['era'].values.astype(np.float64)
        comp = df['complete'].values if 'complete' in df.columns else np.ones(n)
        self.bad = (np.asarray(comp) < 0.5).astype(np.float64)
        self.high, self.low, self.close, self.volume_raw = h, l, c, v
        self.ts = ts_ns(df.index)
        self.n = n

    def window(self, name, s, K):
        return getattr(self, name)[s:s + K]


def sr_levels(high, low, close, volume, lookback=1500, pivot_w=6, tol=0.0015, top_n=8):
    n = len(close)
    a = max(0, n - lookback)
    h, l, v = high[a:], low[a:], volume[a:]
    m = len(h)
    if m < pivot_w * 3:
        return []
    piv = []
    for i in range(pivot_w, m - pivot_w):
        if h[i] == h[i - pivot_w:i + pivot_w + 1].max():
            piv.append((h[i], v[i]))
        if l[i] == l[i - pivot_w:i + pivot_w + 1].min():
            piv.append((l[i], v[i]))
    if not piv:
        return []
    piv.sort(key=lambda x: x[0])
    clusters, cur = [], [piv[0]]
    for p in piv[1:]:
        if abs(p[0] - cur[-1][0]) / max(cur[-1][0], 1e-9) <= tol:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    vsum = max(float(v.sum()), 1e-9)
    out = []
    for cl in clusters:
        px = float(np.average([x[0] for x in cl], weights=[max(x[1], 1e-9) for x in cl]))
        out.append(dict(price=px, touches=len(cl),
                        strength=len(cl) * (1.0 + 3.0 * float(sum(x[1] for x in cl)) / vsum)))
    out.sort(key=lambda d: -d['strength'])
    return out[:top_n]


def nearest_levels(levels, price):
    below = [d for d in levels if d['price'] < price]
    above = [d for d in levels if d['price'] > price]
    return (max(below, key=lambda d: d['price']) if below else None,
            min(above, key=lambda d: d['price']) if above else None)


# =============================================================================
# [8] Analog 검색 — 방향 가설 제안자 (유의성 선언 금지)
# =============================================================================
def _session_similarity(ts_ns_arr, ends, query_end):
    """같은 시각대(UTC 분)의 기억에 작은 가산점. 하드 필터 아님."""
    day = 1440
    qm = (int(ts_ns_arr[int(query_end)]) // 60_000_000_000) % day
    em = (ts_ns_arr[np.asarray(ends, dtype=np.int64)] // 60_000_000_000) % day
    d = np.abs(em - qm)
    d = np.minimum(d, day - d)
    return 0.5 + 0.5 * np.cos(2 * np.pi * d / day)


def _recency_factor(ts_ns_arr, ends, query_end):
    days = np.maximum(0.0, (ts_ns_arr[int(query_end)] - ts_ns_arr[np.asarray(ends, dtype=np.int64)]) / 86400e9)
    return 0.5 + 0.5 * np.exp(-math.log(2) * days / RECENCY_HALF_LIFE_DAYS)


def find_neighbors(ch, K, H, end=None, topk=36, cand_pool=CAND_POOL, use_dtw=True, status=None):
    """
    현재(end 직전 K봉)와 닮은 과거를 찾는다. 반환 (nb dict, None) 또는 (None, 사유).
    · 이웃 창과 그 미래(K+H)는 질의 창과 겹치지 않는다 (선견 누수 차단)
    · 선물/스팟 구간 경계, 불완전(1m 누락) 봉을 포함한 창은 배제
    · 선택된 이웃끼리는 K+H 이상 떨어진다 (사건 독립성)
    · 변동성 재스케일 배율은 명시적으로 기록한다
    """
    n = ch.n if end is None else min(int(end), ch.n)
    if n < 3 * K + 2 * H + 40:
        return None, '데이터 부족'
    qs = n - K
    if ch.bad[qs:n].any():
        return None, '기준 패턴 구간에 불완전 봉(1분봉 누락) 포함 — 판단 보류'
    max_start = n - 2 * K - 2 * H
    if max_start < 10:
        return None, '검색 가능한 과거 부족'
    names = list(ANALOG_WEIGHTS) + ['flow']
    q = {nm: ch.window(nm, qs, K) for nm in names}
    q_vol = float(np.std(q['ret']))
    if q_vol < 1e-12:
        return None, '현재 변동성 0'
    if status:
        status(f'K={K}: 전 구간 analog 검색 (MASS)...', 'blue')
    prof, sds = {}, {}
    for nm in names:
        r, sd = corr_profile(q[nm], getattr(ch, nm)[:max_start + K])
        prof[nm], sds[nm] = r[:max_start + 1], sd[:max_start + 1]
    L = min(len(v) for v in prof.values())
    for nm in names:
        prof[nm], sds[nm] = prof[nm][:L], sds[nm][:L]
    idx = np.arange(L)
    span = K + H
    era_chg = np.zeros(ch.n)
    era_chg[1:] = (np.diff(ch.era) != 0)
    ce = np.concatenate(([0.0], np.cumsum(era_chg)))
    cb = np.concatenate(([0.0], np.cumsum(ch.bad)))
    end_i = np.minimum(idx + span, ch.n)
    valid = ((ce[end_i] - ce[idx + 1]) == 0) & ((cb[end_i] - cb[idx]) == 0)
    volr = sds['ret'] / q_vol
    valid &= (volr >= VOL_BROAD[0]) & (volr <= VOL_BROAD[1])
    base_pool = np.flatnonzero(valid)
    if len(base_pool) < MIN_NEIGHBORS:
        return None, f'유효 analog 후보 {len(base_pool)}개 부족'
    fut_pool = base_pool[ch.era[base_pool] == ERA_FUT]
    spot_fallback = len(fut_pool) < max(MIN_NEIGHBORS * 3, topk * 3)
    pool = base_pool if spot_fallback else fut_pool

    stack = np.vstack([prof[nm] for nm in ANALOG_WEIGHTS])
    wv = np.array([ANALOG_WEIGHTS[nm] for nm in ANALOG_WEIGHTS])[:, None]
    core = 0.90 * (wv * stack).sum(0) + 0.10 * np.quantile(stack, 0.20, axis=0)
    if spot_fallback:
        core = core - SPOT_PENALTY * (ch.era[:L] == ERA_SPOT)

    pre = pool[np.argsort(-core[pool])][:max(cand_pool * 3, topk * 12)]
    pre_score = core[pre] + 0.02 * _session_similarity(ch.ts, pre + K - 1, n - 1)
    cand = pre[np.argsort(-pre_score)][:max(cand_pool, topk * 5)]
    if use_dtw:
        if status:
            status(f'K={K}: DTW 재순위 {len(cand)}개...', 'blue')
        qz = znorm(q['shape'])
        band = max(2, int(K * DTW_BAND_FRAC))
        dtw = np.array([dtw_band(qz, znorm(ch.shape[int(s):int(s) + K]), band) for s in cand])
        dn = (dtw - np.nanmin(dtw)) / max(np.nanstd(dtw), 1e-9)
        ordered = cand[np.argsort(-(core[cand] - 0.025 * dn))]
    else:
        ordered = cand[np.argsort(-core[cand])]
    starts = np.asarray(pick_nonoverlap(ordered, topk, span), dtype=np.int64)
    if len(starts) < MIN_NEIGHBORS:
        return None, f'독립(비중첩) analog {len(starts)}개 < {MIN_NEIGHBORS}'

    exact = {nm: corr_exact(q[nm], getattr(ch, nm), starts) for nm in ANALOG_WEIGHTS}
    ex = np.vstack([exact[nm] for nm in ANALOG_WEIGHTS])
    sim = 0.90 * (wv * ex).sum(0) + 0.10 * np.quantile(ex, 0.20, axis=0)
    ends = starts + K - 1
    raw_w = (np.exp(np.clip(7.0 * (sim - sim.max()), -25, 0)) * _recency_factor(ch.ts, ends, n - 1)
             * (0.90 + 0.10 * _session_similarity(ch.ts, ends, n - 1)))
    weights = soft_cap_weights(raw_w)
    n_eff_w = neff_weights(weights)
    n_eff_t, n_clusters = neff_time(ch.ts[ends], weights)
    nvol = np.array([float(np.std(ch.ret[s:s + K])) for s in starts])
    scales = np.clip(q_vol / np.maximum(nvol, 1e-12), VOL_BROAD[0], VOL_BROAD[1])
    med_shape = wquantile(exact['shape'], weights, 0.50)
    years = pd.Series(pd.to_datetime(ch.ts[ends]).year).value_counts().sort_index()
    return dict(starts=starts.tolist(), K=K, H=H, end=n, qs=qs, pool=pool, q_vol=q_vol,
                max_start=max_start, vol_scale=scales.tolist(),
                vol_scale_clipped=int(np.sum((scales <= VOL_BROAD[0]) | (scales >= VOL_BROAD[1]))),
                similarity=sim.tolist(), weights=weights.tolist(),
                n_eff_w=n_eff_w, n_eff_time=n_eff_t, n_time_clusters=n_clusters,
                n_eff=min(n_eff_w, n_eff_t), median_shape=float(med_shape),
                corr_shape=exact['shape'].tolist(), corr_ret=exact['ret'].tolist(),
                corr_volume=exact['volume'].tolist(),
                fft_err=float(np.max(np.abs(exact['shape'] - prof['shape'][starts]))),
                futures_only=not spot_fallback, years={int(k): int(v) for k, v in years.items()},
                weak_analog=bool(med_shape < MIN_MED_SHAPE)), None


# =============================================================================
# [9] 미래 경로 — 1분봉 정밀 (같은 TF 봉 안의 TP/SL 선후까지 재현)
# =============================================================================
class PathMaker:
    def __init__(self, ch, base1m, tf, K, H, use_1m=True):
        self.ch, self.K, self.H, self.tf = ch, K, H, tf
        self.mult = INTERVALS[tf]
        self.use_1m = bool(use_1m) and base1m is not None and tf != '1m'
        if self.use_1m:
            self.b_hi = base1m['high'].values
            self.b_lo = base1m['low'].values
            self.b_cl = base1m['close'].values
            self.b_ts = ts_ns(base1m.index)

    def paths(self, starts, scales):
        starts = np.asarray(starts, dtype=np.int64)
        sc = np.asarray(scales, dtype=np.float64)
        K, H = self.K, self.H
        ch = self.ch
        if self.use_1m:
            steps = H * self.mult
            step_ns = np.int64(60_000_000_000)
            HI = np.empty((len(starts), steps))
            LO = np.empty_like(HI)
            CL = np.empty_like(HI)
            ok = True
            for i, s in enumerate(starts):
                e = int(s) + K - 1
                entry = ch.close[e]
                t_close = ch.ts[e] + np.int64(self.mult) * step_ns
                p0 = int(np.searchsorted(self.b_ts, t_close, side='left'))
                if p0 + steps > len(self.b_cl) or self.b_ts[p0 + steps - 1] - self.b_ts[p0] != (steps - 1) * step_ns:
                    ok = False
                    break
                HI[i] = (self.b_hi[p0:p0 + steps] / entry - 1.0) * sc[i]
                LO[i] = (self.b_lo[p0:p0 + steps] / entry - 1.0) * sc[i]
                CL[i] = (self.b_cl[p0:p0 + steps] / entry - 1.0) * sc[i]
            if ok:
                return HI, LO, CL, True
        HI = np.empty((len(starts), H))
        LO = np.empty_like(HI)
        CL = np.empty_like(HI)
        for i, s in enumerate(starts):
            e = int(s) + K - 1
            entry = ch.close[e]
            HI[i] = (ch.high[e + 1:e + 1 + H] / entry - 1.0) * sc[i]
            LO[i] = (ch.low[e + 1:e + 1 + H] / entry - 1.0) * sc[i]
            CL[i] = (ch.close[e + 1:e + 1 + H] / entry - 1.0) * sc[i]
        return HI, LO, CL, False


def vol_scales(ch, starts, K, q_vol):
    nvol = np.array([float(np.std(ch.ret[int(s):int(s) + K])) for s in starts])
    return np.clip(float(q_vol) / np.maximum(nvol, 1e-12), VOL_BROAD[0], VOL_BROAD[1])


# =============================================================================
# [10] 교차검증 · 방향 평가 · 동일추정량 matched null · 통계 도구
# =============================================================================
def _grid_from(mfe, mae):
    return (np.unique(np.quantile(mfe, [0.40, 0.55, 0.70, 0.85])),
            np.unique(np.quantile(mae, [0.25, 0.40, 0.55, 0.70])))


def _mfe_mae(HI, LO, side):
    if side > 0:
        return np.maximum(HI.max(axis=1), 1e-6), np.maximum(-LO.min(axis=1), 1e-6)
    return np.maximum(-LO.min(axis=1), 1e-6), np.maximum(HI.max(axis=1), 1e-6)


def fold_splits(starts, nfold=4):
    s = np.asarray(starts, dtype=np.int64)
    chunks = [np.asarray(x, dtype=int) for x in np.array_split(np.argsort(s), nfold) if len(x)]
    out = []
    for te in chunks:
        tr = np.setdiff1d(np.arange(len(s)), te, assume_unique=True)
        if len(tr) >= 8 and len(te) >= 3:
            out.append((tr, te))
    return out


def _best_on_weighted(HI, LO, CL, side, tp_g, sl_g, tf, H, w):
    best = None
    cost = total_cost(tf, H)
    for tp0 in tp_g:
        for sl0 in sl_g:
            tp, sl = float(tp0), float(sl0)
            if tp <= cost * 2 or sl <= 1e-5 or tp / sl < MIN_RR:
                continue
            pnl, code = bracket_vec(HI, LO, CL, side, tp, sl)
            net = net_pnl(pnl, code, tf, H)
            ev = wmean(net, w)
            obj = ev + 0.15 * min(wquantile(net, w, 0.20), 0.0)
            if best is None or obj > best[0]:
                best = (float(obj), tp, sl, float(ev))
    return best


def crossfit_direction(HI, LO, CL, starts, weights, side, tf, K, H):
    """
    4-fold 시간블록 교차적합. 각 fold 의 TP/SL 은 나머지 fold 에서만 고른다.
    반환 outcome 은 R 단위도 함께: R = net / (그 fold 가 쓴 SL + total_cost)
    → 사이징 분모와 같은 단위 (V611 은 최종 SL 로 나눠 손실을 축소 표시했다).
    """
    starts = np.asarray(starts, dtype=np.int64)
    weights = np.asarray(weights, dtype=np.float64)
    n = len(starts)
    splits = fold_splits(starts, 4)
    if len(splits) < 3:
        return None
    mfe, mae = _mfe_mae(HI, LO, side)
    cost = total_cost(tf, H)
    net = np.full(n, np.nan)
    R = np.full(n, np.nan)
    code = np.zeros(n, dtype=np.int64)
    params = []
    for tr, te in splits:
        tp_g, sl_g = _grid_from(mfe[tr], mae[tr])
        b = _best_on_weighted(HI[tr], LO[tr], CL[tr], side, tp_g, sl_g, tf, H, weights[tr])
        if b is None:
            continue
        pnl, c = bracket_vec(HI[te], LO[te], CL[te], side, b[1], b[2])
        net[te] = net_pnl(pnl, c, tf, H)
        R[te] = net[te] / (b[2] + cost)
        code[te] = c
        params.append((b[1], b[2]))
    valid = np.isfinite(net)
    if valid.sum() < max(12, int(0.70 * n)) or len(params) < 3:
        return None
    wv = weights[valid] / max(weights[valid].sum(), 1e-12)
    arr = np.asarray(params, dtype=np.float64)
    rel = np.std(arr, axis=0) / np.maximum(np.mean(arr, axis=0), 1e-9)
    return dict(ev=wmean(net[valid], wv), net=net[valid], R=R[valid], code=code[valid], weights=wv,
                order=np.argsort(starts[valid]), params=params,
                tp=float(np.median(arr[:, 0])), sl=float(np.median(arr[:, 1])),
                stability=float(max(0.0, 1.0 - np.mean(np.clip(rel, 0, 1)))))


def tick_round(price, side, kind, tick):
    """TP 는 안쪽(체결 쉬운 쪽), SL 은 바깥쪽으로만 반올림 — 둘 다 롱=내림, 숏=올림."""
    t = max(float(tick or 0.1), 1e-12)
    return math.floor(price / t) * t if side > 0 else math.ceil(price / t) * t


def final_params(ch, oof, side, tf, H, end, levels, rules):
    """주문표 파라미터: 교차적합 중앙값 → (선택) 구조적 무효화 레벨 → 거래소 tick."""
    tp, sl = float(oof['tp']), float(oof['sl'])
    cost = total_cost(tf, H)
    entry = float(ch.close[int(end) - 1])
    src = '4-fold cross-fit median'
    if levels:
        sup, res = nearest_levels(levels, entry)
        buf = max(0.08 * float(ch.atr[int(end) - 1]), 0.0004)
        tp2, sl2 = tp, sl
        stop_lv, tgt_lv = (sup, res) if side > 0 else (res, sup)
        if stop_lv is not None:
            d = abs(entry - stop_lv['price']) / entry + buf
            if 0.65 * sl <= d <= 1.60 * sl:
                sl2 = d
        if tgt_lv is not None:
            d = abs(tgt_lv['price'] - entry) / entry - buf
            if cost * 2 < d < tp * 1.10:
                tp2 = min(tp, d)
        if tp2 / max(sl2, 1e-12) >= MIN_RR and tp2 > cost * 2:
            tp, sl = tp2, sl2
            src += ' + structural invalidation'
    tick = float(rules.get('tick_size', FALLBACK_RULES['tick_size']))
    tp_px = tick_round(entry * (1 + side * tp), side, 'tp', tick)
    sl_px = tick_round(entry * (1 - side * sl), side, 'sl', tick)
    tp, sl = abs(tp_px / entry - 1.0), abs(sl_px / entry - 1.0)
    if tp <= cost * 2 or sl <= 1e-5 or tp / max(sl, 1e-12) < MIN_RR:
        return None
    return dict(tp=tp, sl=sl, tp_px=tp_px, sl_px=sl_px, src=src, entry_ref=entry)


def bayes_boot_mean(values, base_w, n_boot=EDGE_BOOT_N, rng=None):
    v = np.asarray(values, dtype=np.float64)
    bw = np.asarray(base_w, dtype=np.float64)
    bw = bw / max(bw.sum(), 1e-12)
    rng = rng or np.random.default_rng(NULL_SEED + 71)
    e = rng.exponential(1.0, size=(int(n_boot), len(v))) * bw[None, :]
    e /= e.sum(axis=1, keepdims=True)
    return e @ v


def evaluate_direction(ch, HI, LO, CL, starts, weights, side, tf, K, H, end, levels, rules, rng=None):
    oof = crossfit_direction(HI, LO, CL, starts, weights, side, tf, K, H)
    if oof is None:
        return None
    fin = final_params(ch, oof, side, tf, H, end, levels, rules)
    if fin is None:
        return None
    cost = total_cost(tf, H)
    # F-05: 실제 주문표 파라미터를 전체 이웃에 적용한 EV (in-sample 이므로 낙관적일 수 있어 별도 게이트)
    pnl_p, code_p = bracket_vec(HI, LO, CL, side, fin['tp'], fin['sl'])
    net_p = net_pnl(pnl_p, code_p, tf, H)
    R_p = net_p / (fin['sl'] + cost)
    ev_prod = wmean(net_p, weights)
    boot = bayes_boot_mean(oof['net'], oof['weights'], rng=rng)
    edge_prob = float(np.mean(boot > 0.0))
    edge_lb = float(np.quantile(boot, EDGE_Q))
    k = max(1, int(math.ceil(0.20 * len(oof['net']))))
    cvar = float(np.mean(np.sort(oof['net'])[:k]))
    move_med = wquantile(np.maximum(np.max(HI, axis=1), -np.min(LO, axis=1)), weights, 0.50)
    # 사이징용 R 분포: OOF 절차 vs 최종 주문표 중 평균이 더 나쁜 쪽 (보수적)
    mean_oof, mean_prod = wmean(oof['R'], oof['weights']), wmean(R_p, weights)
    if mean_prod < mean_oof:
        r_src, r_vals, r_w, r_order = 'production-params(in-sample)', R_p, np.asarray(weights), np.argsort(starts)
    else:
        r_src, r_vals, r_w, r_order = 'cross-fit OOF', oof['R'], oof['weights'], oof['order']
    unit = max(fin['sl'], 1e-9)
    score = edge_lb / unit + 0.20 * oof['ev'] / unit + 0.10 * oof['stability'] + 0.08 * min(cvar / unit, 0.0)
    return dict(side=int(side), ev_oof=float(oof['ev']), ev_prod=float(ev_prod), edge_prob=edge_prob,
                edge_lb=edge_lb, cvar=cvar, stability=oof['stability'], score=float(score),
                tp=fin['tp'], sl=fin['sl'], tp_px=fin['tp_px'], sl_px=fin['sl_px'],
                entry_ref=fin['entry_ref'], rr=fin['tp'] / max(fin['sl'], 1e-12), level_src=fin['src'],
                move_median=float(move_med), win=float(np.mean(code_p == 1)), lose=float(np.mean(code_p == -1)),
                tout=float(np.mean(code_p == 0)), r_source=r_src, r_vals=np.asarray(r_vals),
                r_weights=np.asarray(r_w), r_order=np.asarray(r_order), fold_params=oof['params'])


def observed_statistic(HI, LO, CL, starts, weights, tf, K, H):
    """검정통계량 T = max_side OOF EV. observed 와 null 이 반드시 이 함수 하나를 공유한다 (F-04)."""
    vals = []
    for side in (1, -1):
        oo = crossfit_direction(HI, LO, CL, starts, weights, side, tf, K, H)
        if oo is not None:
            vals.append(oo['ev'])
    return max(vals) if vals else None


NULL_BUCKET = 120                 # 각 analog 마다 '같은 변동성 상태'의 대체 후보 수


def matched_null(ch, base1m, tf, K, H, nb, observed, use_1m, n_boot=NULL_N_FINAL, rng=None,
                 stop=None, mode='paired'):
    """
    귀무 H0: '현재와 닮았다'는 사실이 미래 방향/손익에 정보를 주지 않는다.

    F-04 수정 — observed 와 null 이 '같은 추정량'을 쓴다:
      · 같은 함수 observed_statistic (4-fold 교차적합 + max over LONG/SHORT)
      · 같은 가중치 벡터
    mode='paired' (기본): 각 analog i 를, 끝 시점의 변동성 상태가 가장 비슷한 무작위 과거 창으로
      바꿔치기하고 i 의 가중치를 그대로 붙인다. 유사도 검색이 암묵적으로 맞춰 주는
      변동성 상태·표본 동질성은 보존하고, '모양 → 방향' 연결만 끊는다.
    mode='pool': 변동성 비율만 맞춘 무작위 창 + 가중치 무작위 배정 (비교용).
    """
    rng = rng or np.random.default_rng(NULL_SEED)
    pool = np.asarray(nb['pool'], dtype=np.int64)
    chosen = np.asarray(nb['starts'], dtype=np.int64)
    w_obs = np.asarray(nb['weights'], dtype=np.float64)
    sep = K + H
    far = np.ones(len(pool), dtype=bool)
    for s in chosen:
        far &= np.abs(pool - int(s)) >= sep
    pool = pool[far]
    n_draw = len(chosen)
    if len(pool) < n_draw * 3:
        return 1.0, np.array([]), 'null pool 부족'
    qv = float(nb['q_vol'])
    pm = PathMaker(ch, base1m, tf, K, H, use_1m=use_1m)
    vals, attempts = [], 0
    if mode == 'paired':
        st_pool = ch.vol[pool + K - 1]
        order = np.argsort(st_pool)
        sp = st_pool[order]
        half = max(10, min(NULL_BUCKET, len(pool) // (2 * n_draw)) // 2)
        buckets = []
        for s in chosen:
            j = int(np.searchsorted(sp, ch.vol[int(s) + K - 1]))
            lo, hi = max(0, j - half), min(len(pool), j + half)
            buckets.append(pool[order[lo:hi]])
    else:
        pvol = _sliding_ms(np.asarray(ch.ret, dtype=np.float64), K)[1][pool]
        keep = (pvol / max(qv, 1e-12) >= 0.60) & (pvol / max(qv, 1e-12) <= 1.67)
        if keep.sum() >= n_draw * 3:
            pool = pool[keep]
        m = min(len(pool), max(60 * n_draw, 2000))
    while len(vals) < int(n_boot) and attempts < int(n_boot) * 6:
        if stop and stop():
            break
        attempts += 1
        if mode == 'paired':
            sample, ok = [], True
            for bk in buckets:
                for _ in range(12):
                    c = int(bk[rng.integers(len(bk))])
                    if all(abs(c - x) >= sep for x in sample):
                        sample.append(c)
                        break
                else:
                    ok = False
                    break
            if not ok:
                continue
            sample = np.asarray(sample, dtype=np.int64)
            wd = w_obs
        else:
            sample = np.asarray(pick_nonoverlap(rng.choice(pool, size=m, replace=False), n_draw, sep), dtype=np.int64)
            if len(sample) < n_draw:
                continue
            wd = rng.permutation(w_obs)
        HI, LO, CL, _ = pm.paths(sample, vol_scales(ch, sample, K, qv))
        t = observed_statistic(HI, LO, CL, sample, wd, tf, K, H)
        if t is not None:
            vals.append(t)
    if not vals:
        return 1.0, np.array([]), 'null 표본 생성 실패'
    arr = np.asarray(vals)
    return float((np.sum(arr >= float(observed)) + 1) / (len(arr) + 1)), arr, ''


def stationary_block_bootstrap(x, stat=np.mean, n_boot=2000, mean_block=5.0, rng=None):
    """
    F-03: Politis-Romano stationary block bootstrap (이름과 방법이 일치한다).
    시계열 의존(연속 손실 등)을 보존한 채 통계량 분포를 만든다.
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n == 0:
        return np.array([])
    rng = rng or np.random.default_rng(12345)
    p = 1.0 / max(mean_block, 1.0)
    out = np.empty(int(n_boot))
    for b in range(int(n_boot)):
        idx = np.empty(n, dtype=np.int64)
        idx[0] = rng.integers(n)
        jump = rng.random(n) < p
        fresh = rng.integers(0, n, size=n)
        for t in range(1, n):
            idx[t] = fresh[t] if jump[t] else (idx[t - 1] + 1) % n
        out[b] = stat(x[idx])
    return out


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    lo, hi = -10.0, 10.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def deflated_sharpe(returns, n_trials):
    r = np.asarray(returns, dtype=np.float64)
    n = len(r)
    if n < 8 or r.std(ddof=1) < 1e-12:
        return 0.0, 0.0, 0.0
    sr = r.mean() / r.std(ddof=1)
    g3 = float(pd.Series(r).skew())
    g4 = float(pd.Series(r).kurt()) + 3.0
    e = 0.5772156649
    t = max(int(n_trials), 2)
    se = math.sqrt(1.0 / (n - 1))
    sr0 = se * ((1 - e) * norm_ppf(1 - 1.0 / t) + e * norm_ppf(1 - 1.0 / (t * math.e)))
    den = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr * sr))
    return sr, sr0, norm_cdf((sr - sr0) * math.sqrt(n - 1) / den)


# =============================================================================
# [11] 성장 / 위험 엔진 — robust log growth + ST-09(edge 소멸) 낙폭 제약
# -----------------------------------------------------------------------------
#  RAW growth optimum → 추정불확실성(Bayesian bootstrap) → edge 감쇠(25/50/100%)
#  → 낙폭/자본바닥 MC (edge 유지 & edge 0) → 증거·표본·안정성·컨텍스트·prospective
#  → 포트폴리오 open-risk/군집 → 거래소 실행가능성 → 최종 계좌위험
#  불변식: 모든 감쇠 배수 ∈ [0,1], risk=0 은 정당한 답, 검증기는 위험을 올릴 수 없다.
# =============================================================================
def _bb_log_growth(R, w, grid, n_boot, rng):
    f = 1.0 + grid[:, None] * R[None, :]
    logm = np.where(f > 0, np.log(np.maximum(f, 1e-300)), -1e12)
    e = rng.exponential(1.0, size=(int(n_boot), len(R))) * w[None, :]
    e /= np.maximum(e.sum(axis=1, keepdims=True), 1e-12)
    draws = e @ logm.T
    return dict(point=logm @ w, median=np.median(draws, axis=0),
                lower=np.quantile(draws, GROWTH_Q, axis=0), prob=(draws > 0).mean(axis=0))


def _mc_equity(R_time, w_time, grid, rng, n_paths=MC_PATHS, n_trades=MC_TRADES, block=MC_BLOCK):
    """가중 stationary-block 재표본으로 연속 손실(군집)을 보존한 자산경로 MC."""
    n = len(R_time)
    p = w_time / max(w_time.sum(), 1e-12)
    fresh = rng.choice(n, size=(n_paths, n_trades), replace=True, p=p)
    cont = rng.random((n_paths, n_trades)) < (1.0 - 1.0 / max(block, 1.0))
    idx = np.empty((n_paths, n_trades), dtype=np.int64)
    idx[:, 0] = fresh[:, 0]
    for t in range(1, n_trades):
        idx[:, t] = np.where(cont[:, t], (idx[:, t - 1] + 1) % n, fresh[:, t])
    seq = R_time[idx]
    out = dict(mdd=[], floor=[], terminal=[])
    for f in grid:
        fac = 1.0 + float(f) * seq
        if np.any(fac <= 0):
            out['mdd'].append(np.ones(n_paths))
            out['floor'].append(np.zeros(n_paths))
            out['terminal'].append(np.zeros(n_paths))
            continue
        eq = np.cumprod(fac, axis=1)
        pk = np.maximum.accumulate(np.maximum(eq, 1.0), axis=1)
        out['mdd'].append(np.max(1.0 - eq / pk, axis=1))
        out['floor'].append(np.min(eq, axis=1))
        out['terminal'].append(eq[:, -1])
    return {k: np.asarray(v) for k, v in out.items()}      # (G, paths)


def holding_hours(HI, LO, side, tp, sl, tf, H, w=None):
    n, T = HI.shape
    thr = tp + (MAKER_TP_THROUGH if TP_TYPE == 'maker' else 0.0)
    win, lose = ((HI >= thr, LO <= -sl) if side > 0 else (LO <= -thr, HI >= sl))
    fw = np.where(win.any(1), win.argmax(1), T - 1)
    fl = np.where(lose.any(1), lose.argmax(1), T - 1)
    step_h = INTERVALS[tf] * H / 60.0 / max(T, 1)
    h = (np.minimum(fw, fl) + 1) * step_h
    return float(max(step_h, wmean(h, w) if w is not None and len(w) == len(h) else np.mean(h)))


def growth_risk(cand, HI, LO, tf, H, rng=None):
    """주문표 1건에 대해 성장 최적 계좌위험(천장 RISK_CAP 이하)을 찾는다."""
    rng = rng or np.random.default_rng(NULL_SEED + 11)
    R = np.asarray(cand['r_vals'], dtype=np.float64)
    w = np.asarray(cand['r_weights'], dtype=np.float64)
    order = np.asarray(cand.get('r_order', np.arange(len(R))), dtype=np.int64)
    R, w = R[order], w[order]                              # 과거 시간순 정렬 (block MC 용)
    ok = np.isfinite(R) & np.isfinite(w) & (w >= 0)
    if ok.sum() < 8 or w[ok].sum() <= 0:
        return dict(risk=0.0, reason='R 표본 부족')
    R, w = R[ok], w[ok] / w[ok].sum()
    mu = float(np.dot(R, w))
    if mu <= 0:
        return dict(risk=0.0, reason=f'가중 평균 R {mu:+.3f} ≤ 0', r_mean=mu)
    grid = np.linspace(0.0, RISK_CAP, 41)
    p0 = _bb_log_growth(R, w, grid, GROWTH_BOOT, rng)
    pe = _bb_log_growth(R - GROWTH_DECAY_EVAL * mu, w, grid, GROWTH_BOOT, rng)
    p50 = _bb_log_growth(R - 0.50 * mu, w, grid, GROWTH_BOOT, rng)
    mci = _mc_equity(R, w, grid, rng)
    mcz = _mc_equity(R - mu, w, grid, rng)                         # ST-09: edge 100% 소멸
    dd_i = (mci['mdd'] > MAX_DD).mean(axis=1)
    dd_z = (mcz['mdd'] > ST09_MAX_DD).mean(axis=1)
    fl_z = (mcz['floor'] < ST09_FLOOR).mean(axis=1)
    st09_ok = (dd_z <= ST09_MAX_DD_PROB) & (fl_z <= ST09_FLOOR_PROB)
    feasible = ((p0['prob'] >= GROWTH_PROB_MIN) & (p50['median'] > 0) &
                (dd_i <= MAX_DD_PROB) & st09_ok)
    feasible[0] = True
    obj = np.where(feasible, pe['median'] + 0.20 * np.minimum(pe['lower'], 0.0), -np.inf)
    j = int(np.argmax(obj))
    st09_cap = float(grid[np.flatnonzero(st09_ok)].max()) if st09_ok.any() else 0.0
    base = dict(r_mean=mu, st09_cap=st09_cap, growth_prob_at_cap=float(p0['prob'][-1]))
    if grid[j] <= 0:
        why = []
        if not (p0['prob'][1:] >= GROWTH_PROB_MIN).any():
            why.append(f'P(성장>0) 최대 {p0["prob"].max():.0%} < {GROWTH_PROB_MIN:.0%}')
        if not st09_ok[1:].any():
            why.append('edge 소멸 가정(ST-09) 낙폭 제약 위반')
        return dict(risk=0.0, reason='양(+)의 안전 위험 없음: ' + (' / '.join(why) or '제약 동시충족 불가'), **base)
    hold = holding_hours(HI, LO, cand['side'], cand['tp'], cand['sl'], tf, H)
    return dict(risk=float(grid[j]), growth_median=float(p0['median'][j]), growth_eval=float(pe['median'][j]),
                growth_lb=float(p0['lower'][j]), growth_prob=float(p0['prob'][j]),
                mdd_prob=float(dd_i[j]), st09_dd_prob=float(dd_z[j]), st09_floor_prob=float(fl_z[j]),
                expected_hold_hours=hold, growth_per_hour=float(pe['median'][j]) / max(hold, 1e-6), **base)


def clip01(x):
    x = float(x)
    return 0.0 if not math.isfinite(x) else min(1.0, max(0.0, x))


# =============================================================================
# [12] 거래소 규칙 · 시장 컨텍스트 (공개 데이터, 실패 시 값을 지어내지 않는다)
# =============================================================================
def fetch_rules(http):
    """exchangeInfo 에서 tick/step/minQty/minNotional. 실패 → 7일 이내 캐시 → 보수적 기본값."""
    try:
        ex = http.get_json(f'{FAPI_BASE}/fapi/v1/exchangeInfo', timeout=15)
        sym = next(x for x in ex.get('symbols', []) if x.get('symbol') == SYMBOL)
        r = dict(FALLBACK_RULES)
        for f in sym.get('filters', []):
            ft = f.get('filterType')
            if ft == 'PRICE_FILTER':
                r['tick_size'] = float(f['tickSize'])
            elif ft == 'LOT_SIZE':
                r['qty_step'] = float(f['stepSize'])
                r['min_qty'] = float(f['minQty'])
            elif ft in ('MIN_NOTIONAL', 'NOTIONAL'):
                r['min_notional'] = float(f.get('notional', f.get('minNotional', r['min_notional'])))
        r.update(source='live', fetched_at=_iso_now())
        try:
            tmp = Paths.rules_cache() + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(r, fh)
            os.replace(tmp, Paths.rules_cache())
        except Exception as e:
            HEALTH.set('rules_cache', 'WARN', f'거래소 규칙 캐시 저장 실패: {e}')
        HEALTH.clear('rules')
        return r
    except Exception as e:
        err = e
    try:
        with open(Paths.rules_cache(), encoding='utf-8') as fh:
            r = json.load(fh)
        age = (utcnow() - to_naive_utc(r['fetched_at'])).total_seconds() / 86400
        if age <= 7:
            r['source'] = f'cache({age:.1f}d)'
            HEALTH.set('rules', 'WARN', f'exchangeInfo 실패 → {age:.1f}일 전 캐시 사용 ({err})')
            return r
    except Exception:
        pass
    HEALTH.set('rules', 'WARN', f'exchangeInfo·캐시 모두 실패 → 보수적 기본값 사용 ({err})')
    return dict(FALLBACK_RULES, source='fallback', fetched_at=None)


def fetch_context(http):
    ctx = dict(rules=fetch_rules(http), spread_bps=float('nan'), funding_rate=float('nan'),
               premium_bps=float('nan'), next_funding_time=0, oi_change_1h=float('nan'),
               taker_buy_sell=float('nan'), warnings=[])

    def grab(url, fn, label):
        try:
            fn(http.get_json(url, timeout=8))
        except Exception as e:
            ctx['warnings'].append(f'{label}: {type(e).__name__}')

    def prem(d):
        mark, idx = float(d['markPrice']), float(d['indexPrice'])
        ctx.update(funding_rate=float(d.get('lastFundingRate', 'nan')), mark_price=mark,
                   premium_bps=(mark / idx - 1.0) * 1e4 if idx else float('nan'),
                   next_funding_time=int(d.get('nextFundingTime', 0) or 0))

    def book(d):
        bid, ask = float(d['bidPrice']), float(d['askPrice'])
        ctx.update(bid=bid, ask=ask, spread_bps=(ask - bid) / ((ask + bid) / 2) * 1e4)

    def oih(d):
        v = np.asarray([float(x.get('sumOpenInterestValue', 'nan')) for x in d], dtype=np.float64)
        v = v[np.isfinite(v) & (v > 0)]
        if len(v) >= 2:
            ctx['oi_change_1h'] = float(v[-1] / v[0] - 1.0)

    def taker(d):
        b = sum(float(x.get('buyVol', 0)) for x in d)
        s = sum(float(x.get('sellVol', 0)) for x in d)
        if s > 0:
            ctx['taker_buy_sell'] = b / s

    grab(f'{FAPI_BASE}/fapi/v1/premiumIndex?symbol={SYMBOL}', prem, 'premiumIndex')
    grab(f'{FAPI_BASE}/fapi/v1/ticker/bookTicker?symbol={SYMBOL}', book, 'bookTicker')
    grab(f'{FAPI_BASE}/futures/data/openInterestHist?symbol={SYMBOL}&period=5m&limit=13', oih, 'oiHist')
    grab(f'{FAPI_BASE}/futures/data/takerlongshortRatio?symbol={SYMBOL}&period=5m&limit=12', taker, 'taker')
    return ctx


NEUTRAL_CONTEXT = dict(rules=dict(FALLBACK_RULES, source='neutral'), spread_bps=float('nan'),
                       funding_rate=float('nan'), next_funding_time=0, oi_change_1h=float('nan'),
                       taker_buy_sell=float('nan'), warnings=['neutral context (backtest/offline)'])


def context_multiplier(ctx, side, tf, H, now=None):
    """컨텍스트는 방향을 만들거나 뒤집지 못한다. veto 또는 [0,1] 축소만."""
    notes, mult = [], 1.0
    spread = fnum(ctx.get('spread_bps'))
    if math.isfinite(spread) and spread > SPREAD_MAX_BPS:
        return 0.0, f'스프레드 {spread:.2f}bp > {SPREAD_MAX_BPS:.1f}bp', notes
    fr = fnum(ctx.get('funding_rate'))
    nft = int(ctx.get('next_funding_time') or 0)
    crosses = True
    if nft:
        now_ms = int(((now or utcnow()) - datetime(1970, 1, 1)).total_seconds() * 1000)
        crosses = now_ms <= nft <= now_ms + INTERVALS[tf] * H * 60_000
    adverse = fr * side if (math.isfinite(fr) and crosses) else 0.0
    if adverse > FUNDING_ADVERSE:
        return 0.0, f'보유구간 내 불리한 funding {fr:+.4%}', notes
    if adverse > FUNDING_THROTTLE:
        mult *= 0.50
        notes.append('불리한 funding → 위험 50%')
    oi = fnum(ctx.get('oi_change_1h'))
    if math.isfinite(oi) and abs(oi) > OI_SHOCK:
        mult *= 0.70
        notes.append(f'OI 1h 급변 {oi:+.1%} → 위험 70%')
    tk = fnum(ctx.get('taker_buy_sell'))
    if math.isfinite(tk) and ((side > 0 and tk < TAKER_OPPOSE) or (side < 0 and tk > 1.0 / TAKER_OPPOSE)):
        mult *= 0.75
        notes.append(f'taker flow 반대({tk:.2f}) → 위험 75%')
    return clip01(mult), None, notes


# =============================================================================
# [13] 사이징 — 위험예산이 명목을 정하고, 레버리지는 그 명목을 담는 최소 정수
# =============================================================================
def _step_decimals(step):
    s = f'{step:.10f}'.rstrip('0')
    return len(s.split('.')[1]) if '.' in s else 0


def size_position(seed, entry, sl, risk_frac, tf, H, rules):
    seed, entry, sl, risk_frac = float(seed), float(entry), float(sl), float(risk_frac)
    cost = total_cost(tf, H)
    denom = sl + cost
    budget = seed * risk_frac
    step = max(float(rules.get('qty_step', FALLBACK_RULES['qty_step'])), 1e-12)
    min_qty = float(rules.get('min_qty', step))
    min_notional = float(rules.get('min_notional', FALLBACK_RULES['min_notional']))
    max_margin = seed * MARGIN_CAP
    target = min(budget / max(denom, 1e-12), max_margin * MAX_LEV)
    qty = math.floor(target / entry / step + 1e-9) * step
    need_qty = max(min_qty, math.ceil(min_notional / entry / step - 1e-9) * step)
    base = dict(executable=False, risk_frac=risk_frac, cost=cost, rules_source=rules.get('source', '?'))
    if qty + 1e-12 < need_qty:
        need_risk = need_qty * entry * denom / max(seed, 1e-12)
        return dict(base, reason=(f'거래소 최소주문 {need_qty:g} BTC(≈{need_qty * entry:,.0f} USDT)을 채우려면 '
                                  f'계좌위험 {need_risk:.2%} 필요 > 허용 {risk_frac:.2%} (위험을 올려 맞추지 않음)'),
                    need_risk=need_risk)
    notional = qty * entry
    lev = max(1, int(math.ceil(notional / max_margin - 1e-9)))
    if lev > MAX_LEV:
        return dict(base, reason=f'저레버리지 한도 {MAX_LEV}x 로 명목 {notional:,.0f} 구현 불가')
    margin = notional / lev
    liq = max(0.0, 1.0 / lev - MMR)
    if liq < max(3.0 * sl, sl + 0.02):
        return dict(base, reason=f'청산거리 {liq:.1%} 가 손절 {sl:.2%} 대비 부족')
    risk_actual = notional * denom / seed
    return dict(executable=True, reason='', risk_frac=risk_frac, risk_actual=float(risk_actual),
                max_loss_usdt=float(notional * denom), margin=float(margin), margin_pct=float(margin / seed),
                lev=int(lev), notional=float(notional), qty=round(qty, _step_decimals(step)),
                liq_dist=float(liq), cost=cost, rules_source=rules.get('source', '?'))


# =============================================================================
# [14] 스캔 — Analog 제안 → 통계가 죽이려 시도 → 컨텍스트 veto → 성장/위험 → 사이징
#      모든 경로가 dict 하나를 반환한다 (F-01: tuple arity 불일치 원천 제거)
# =============================================================================
def wait(tf, reason, **kw):
    d = dict(tf=tf, trade=False, reason=str(reason))
    d.update(kw)
    return d


def analyze_scale(snap, ch, tf, K, H, rules, end, topk, levels, use_1m, rng, status=None):
    out = dict(K=K, H=H, reason='', side=0)
    nb, err = find_neighbors(ch, K, H, end=end, topk=topk, status=status)
    if nb is None:
        out['reason'] = err
        return out
    starts = np.asarray(nb['starts'], dtype=np.int64)
    weights = np.asarray(nb['weights'], dtype=np.float64)
    pm = PathMaker(ch, snap.base if use_1m else None, tf, K, H, use_1m=use_1m)
    HI, LO, CL, used_1m = pm.paths(starts, nb['vol_scale'])
    out.update(nb=nb, n=len(starts), used_1m=used_1m, paths=(HI, LO, CL))
    cands = []
    for side in (1, -1):
        c = evaluate_direction(ch, HI, LO, CL, starts, weights, side, tf, K, H, nb['end'], levels, rules, rng)
        if c is not None:
            cands.append(c)
    out['T_obs'] = observed_statistic(HI, LO, CL, starts, weights, tf, K, H)
    if not cands:
        out['reason'] = 'LONG/SHORT 모두 교차검증 가능한 주문구조 없음'
        return out
    cands.sort(key=lambda x: x['score'], reverse=True)
    out.update(winner=cands[0], runner_up=cands[1] if len(cands) > 1 else None, side=cands[0]['side'])
    return out


def precheck(primary, scales, tf, H):
    """단일 dict 반환: ok / reason / votes."""
    if 'winner' not in primary:
        return dict(ok=False, reason=primary.get('reason') or '주 신호 없음', votes=[])
    p, nb = primary['winner'], primary['nb']
    r = []
    if nb['median_shape'] < MIN_MED_SHAPE:
        r.append(f'Analog 중앙 형상 r={nb["median_shape"]:.3f} < {MIN_MED_SHAPE}')
    if nb['n_eff'] < MIN_NEFF:
        r.append(f'N_eff {nb["n_eff"]:.1f} < {MIN_NEFF:.0f} (가중 {nb["n_eff_w"]:.1f}, 시간군집 {nb["n_eff_time"]:.1f})')
    if p['ev_oof'] <= 0:
        r.append(f'OOF 순EV {p["ev_oof"]:+.3%} ≤ 0')
    if p['ev_prod'] <= 0:
        r.append(f'주문표 파라미터 EV {p["ev_prod"]:+.3%} ≤ 0')
    if p['edge_prob'] < EDGE_PROB_MIN:
        r.append(f'P(edge>0) {p["edge_prob"]:.1%} < {EDGE_PROB_MIN:.0%}')
    if p['move_median'] < total_cost(tf, H) * MIN_MOVE_COST_MULT:
        r.append('analog 미래 이동폭이 비용 대비 작음')
    ru = primary.get('runner_up')
    if ru is not None and ru.get('edge_lb', -1) > 0:
        gap = p['edge_prob'] - ru['edge_prob']
        if gap < SIDE_GAP_MIN and abs(p['score'] - ru['score']) < 0.15:
            r.append(f'LONG/SHORT 양면 edge 모호 (확률격차 {gap:.1%})')
    votes = [int(x['winner']['side']) for x in scales
             if x.get('winner') and x['winner']['edge_prob'] >= VOTE_EDGE_PROB and x['winner']['ev_oof'] > 0]
    if sum(v == p['side'] for v in votes) < 2:
        r.append(f'multiscale 합의 부족 {votes}')
    return dict(ok=not r, reason=' / '.join(r), votes=votes)


def _visual_payload(ch, tf, K, H, nb, paths, used_1m, entry_ref, tp, sl, side):
    """육안검사용 증거를 신호에 동봉 (데이터가 바뀌어도 당시 근거를 다시 그릴 수 있게)."""
    HI, LO, CL = paths
    mult = INTERVALS[tf] if used_1m else 1
    cl_tf = CL[:, mult - 1::mult] if mult > 1 else CL
    qs = nb['qs']
    qn = ch.close[qs:qs + K] / ch.close[qs] - 1.0
    w = np.asarray(nb['weights'])
    order = np.argsort(-w)[:8]
    analogs = []
    for rank, i in enumerate(order, 1):
        s = int(nb['starts'][i])
        e = s + K - 1
        fut_end = min(e + H, ch.n - 1)
        analogs.append(dict(rank=rank, start_ts=str(pd.Timestamp(ch.ts[s])), end_ts=str(pd.Timestamp(ch.ts[e])),
                            future_end_ts=str(pd.Timestamp(ch.ts[fut_end])), weight=float(w[i]),
                            similarity=float(nb['similarity'][i]), corr_shape=float(nb['corr_shape'][i]),
                            vol_scale=float(nb['vol_scale'][i]),
                            pattern=(ch.close[s:s + K] / ch.close[s] - 1.0).round(5).tolist() if rank <= 3 else None,
                            future=(cl_tf[i]).round(5).tolist()))
    return dict(tf=tf, K=K, H=H, query_start=str(pd.Timestamp(ch.ts[qs])),
                query_end=str(pd.Timestamp(ch.ts[qs + K - 1])), pattern=qn.round(5).tolist(),
                future_q={str(q): np.quantile(cl_tf, q, axis=0).round(5).tolist() for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
                analogs=analogs, entry_ref=entry_ref, tp=tp, sl=sl, side=side,
                vol_scale_note='analog 미래경로는 (현재 변동성 / analog 변동성) 배율로 스케일됨',
                n_neighbors=len(nb['starts']))


def scan_tf(snap, tf, seed, ctx, book=None, do_null=True, end=None, live=True, status=None, rng=None,
            stop=None, family_size=FAMILY_SIZE, use_1m=True):
    """한 timeframe 의 전체 판정. 어떤 경로든 dict 하나를 반환한다."""
    status = status or (lambda *a, **k: None)
    book = book or {}
    spec = MODELS[tf]
    K, H, topk = int(spec['K']), int(spec['H']), int(spec['topk'])
    df = snap.tf(tf)
    n = len(df) if end is None else min(int(end), len(df))
    if n < 3 * max(int(round(K * f)) for f in SCALE_FACTORS) + 2 * H + 100:
        return wait(tf, '데이터 부족', model_label=spec['label'], K=K, H=H)
    if df['complete'].values[n - 1] < 0.5:
        return wait(tf, '기준봉 미완성(1분봉 누락) — 다음 봉에서 재평가', model_label=spec['label'], K=K, H=H)
    ch = snap.channels(tf)
    rules = ctx.get('rules') or FALLBACK_RULES
    lv = sr_levels(ch.high[:n], ch.low[:n], ch.close[:n], ch.volume_raw[:n])
    rng = rng or np.random.default_rng(NULL_SEED + INTERVALS[tf] + (n % 100_000))
    scales = []
    for f in SCALE_FACTORS:
        kk = max(30, int(round(K * f)))
        if stop and stop():
            return wait(tf, '중단됨', K=K, H=H)
        status(f'{tf} K={kk}: analog + cross-fit...', 'blue')
        scales.append(analyze_scale(snap, ch, tf, kk, H, rules, n, topk, lv, use_1m, rng, status))
    primary = next(x for x in scales if x['K'] == K)
    pc = precheck(primary, scales, tf, H)
    d = dict(tf=tf, K=K, H=H, trade=False, model_label=spec['label'], votes=pc['votes'],
             bar_time=str(pd.Timestamp(ch.ts[n - 1])), primary_summary=_primary_summary(primary))
    if not pc['ok']:
        d['reason'] = pc['reason']
        return d
    p, nb = primary['winner'], primary['nb']

    # 비싼 matched-null 은 1차 통과 후보만 (선별 후 검정이지만 무조건부 null 과 비교하므로 FPR ≤ α 유지)
    if do_null:
        status(f'{tf} 최종후보: 동일추정량 matched-null {NULL_N_FINAL}회...', 'blue')
        pv, null, why = matched_null(ch, snap.base if primary['used_1m'] else None, tf, K, H, nb,
                                     primary['T_obs'], primary['used_1m'], rng=rng, stop=stop)
        d.update(p_raw=pv, p_family=min(1.0, pv * family_size), null_n=int(len(null)),
                 null_mean=float(np.mean(null)) if len(null) else float('nan'), null_note=why)
        if d['p_family'] > FAMILY_ALPHA:
            d['reason'] = (f'matched-null p={pv:.4f} × family {family_size} = {d["p_family"]:.3f} '
                           f'> α {FAMILY_ALPHA}')
            return d
    else:
        d.update(p_raw=float('nan'), p_family=float('nan'), null_n=0)

    cmult, veto, cnotes = context_multiplier(ctx, p['side'], tf, H, snap.now)
    d['context_notes'] = cnotes
    if veto:
        d['reason'] = veto
        return d
    HI, LO, _ = primary['paths']
    g = growth_risk(p, HI, LO, tf, H, rng=rng)
    d['growth'] = {k: v for k, v in g.items() if k != 'reason'}
    if g.get('risk', 0) <= 0:
        d['reason'] = g.get('reason', '성장 최적 위험 0')
        return d
    mults = dict(evidence=clip01(np.clip((p['edge_prob'] - 0.50) / 0.35, 0.25, 1.0)),
                 sample=clip01(np.clip(nb['n_eff'] / 20.0, 0.40, 1.0)),
                 stability=clip01(np.clip(p['stability'], 0.40, 1.0)),
                 context=clip01(cmult), prospective=clip01(book.get('prospective_mult', 1.0)),
                 governor=clip01(book.get('governor_mult', 1.0)))
    risk = min(RISK_CAP, g['risk'] * float(np.prod(list(mults.values()))))
    if book.get('governor_block'):
        d['reason'] = book['governor_block']
        return d
    d['multipliers'] = mults
    if risk < RISK_FLOOR:
        d['reason'] = f'감쇠 후 계좌위험 {risk:.3%} < 실행하한 {RISK_FLOOR:.2%}'
        return d

    side, entry_ref = p['side'], p['entry_ref']
    entry = snap.last_price() if (live and end is None) else entry_ref
    drift = side * (entry / entry_ref - 1.0)
    sl_eff = side * (entry - p['sl_px']) / entry
    tp_eff = side * (p['tp_px'] - entry) / entry
    if drift < -MAX_DRIFT_SL_FRAC * p['sl'] or sl_eff <= 1e-5:
        d['reason'] = f'기준봉 이후 가격이 SL 방향으로 {drift:+.3%} 이동 — 추격 금지'
        return d
    if tp_eff <= 2 * total_cost(tf, H) or tp_eff / sl_eff < MIN_RR:
        d['reason'] = f'기준봉 이후 유리하게 {drift:+.3%} 이동해 남은 손익비 {tp_eff / max(sl_eff, 1e-9):.2f} 부족 — 추격 금지'
        return d
    sz = size_position(seed, entry, sl_eff, risk, tf, H, rules)
    if not sz['executable']:
        d['reason'] = sz['reason']
        d['sizing'] = sz
        return d
    d.update(trade=True, reason='', side=side, entry=entry, entry_ref=entry_ref, drift=drift, rules=rules,
             tp_px=p['tp_px'], sl_px=p['sl_px'], tp=tp_eff, sl=sl_eff, rr=tp_eff / sl_eff,
             risk_frac=risk, sizing=sz, winner=_winner_summary(p), level_src=p['level_src'],
             expected_hold_hours=g['expected_hold_hours'], growth_per_hour=g['growth_per_hour'],
             max_hold_min=INTERVALS[tf] * H,
             visual=_visual_payload(ch, tf, K, H, nb, primary['paths'], primary['used_1m'],
                                    entry_ref, p['tp'], p['sl'], side))
    return d


def _winner_summary(p):
    keep = ('side', 'ev_oof', 'ev_prod', 'edge_prob', 'edge_lb', 'cvar', 'stability', 'score', 'tp', 'sl',
            'rr', 'win', 'lose', 'tout', 'move_median', 'r_source', 'level_src', 'fold_params')
    return {k: p.get(k) for k in keep}


def _primary_summary(primary):
    nb = primary.get('nb') or {}
    out = dict(K=primary.get('K'), reason=primary.get('reason', ''), n=primary.get('n'),
               median_shape=nb.get('median_shape'), n_eff=nb.get('n_eff'), n_eff_w=nb.get('n_eff_w'),
               n_eff_time=nb.get('n_eff_time'), n_time_clusters=nb.get('n_time_clusters'),
               futures_only=nb.get('futures_only'), years=nb.get('years'), used_1m=primary.get('used_1m'),
               vol_scale_clipped=nb.get('vol_scale_clipped'), fft_err=nb.get('fft_err'))
    if primary.get('winner'):
        out['winner'] = _winner_summary(primary['winner'])
    return out


def choose(decisions):
    """한 사이클에 새 주문표는 최대 1장. 반대방향 유효신호가 동시에 있으면 WAIT."""
    valid = [d for d in decisions if d.get('trade')]
    if not valid:
        return wait('ALL', ' | '.join(f"{d.get('tf')}: {d.get('reason', 'WAIT')}" for d in decisions),
                    alternatives=decisions)
    if len({d['side'] for d in valid}) > 1:
        return wait('ALL', '서로 반대 방향의 유효 신호가 동시에 존재 — 모순된 증거 → WAIT', alternatives=decisions)
    valid.sort(key=lambda d: (d.get('growth_per_hour', -1e9), d.get('risk_frac', 0)), reverse=True)
    best = dict(valid[0])
    best['alternatives'] = decisions
    best['confirming'] = [d['tf'] for d in valid[1:]]
    return best


# =============================================================================
# [15] 원장(ledger) · 상태 — 상태는 append-only 이벤트의 fold 다
# =============================================================================
class Ledger:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, ev):
        line = json.dumps(json_safe(ev), ensure_ascii=False)
        with self._lock:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
                f.flush()
                os.fsync(f.fileno())

    def read(self):
        if not os.path.exists(self.path):
            return []
        out, bad = [], 0
        with open(self.path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    bad += 1
        if bad:
            HEALTH.set('ledger', 'WARN', f'원장에서 손상된 줄 {bad}개 건너뜀 (마지막 줄 쓰기 중 종료 가능성)')
        return out


def new_state():
    return dict(version=VERSION, model_id=MODEL_ID, created=_iso_now(), signals=[], manual=[],
                last_scan={}, fails={}, rebuilt_from_ledger=False)


def _find(items, key, value):
    for x in reversed(items):
        if x.get(key) == value:
            return x
    return None


def apply_event(st, ev):
    k = ev.get('kind')
    if k == 'SIGNAL_DETECTED':
        if not _find(st['signals'], 'signal_id', ev['signal']['signal_id']):
            sig = {kk: copy.deepcopy(vv) for kk, vv in ev['signal'].items() if kk != 'visual'}
            sig['has_visual'] = bool(ev['signal'].get('visual'))      # 무거운 시각증거는 원장에만
            st['signals'].append(sig)
    elif k == 'SIGNAL_UPDATE':
        s = _find(st['signals'], 'signal_id', ev['signal_id'])
        if s is not None:
            for kk, vv in ev['fields'].items():
                if isinstance(vv, dict) and isinstance(s.get(kk), dict):
                    s[kk].update(copy.deepcopy(vv))
                else:
                    s[kk] = copy.deepcopy(vv)
    elif k == 'MANUAL_OPENED':
        if not _find(st['manual'], 'pos_id', ev['position']['pos_id']):
            st['manual'].append(copy.deepcopy(ev['position']))
    elif k == 'MANUAL_UPDATE':
        p = _find(st['manual'], 'pos_id', ev['pos_id'])
        if p is not None:
            for kk, vv in ev['fields'].items():
                if isinstance(vv, dict) and isinstance(p.get(kk), dict):
                    p[kk].update(copy.deepcopy(vv))
                else:
                    p[kk] = copy.deepcopy(vv)
    if len(st['signals']) > MAX_SIGNALS_IN_STATE:
        keep_open = [s for s in st['signals'][:-MAX_SIGNALS_IN_STATE]
                     if (s.get('shadow') or {}).get('state') in ('PENDING_FILL', 'OPEN')]
        st['signals'] = keep_open + st['signals'][-MAX_SIGNALS_IN_STATE:]


class StateStore:
    def __init__(self, path=None, ledger_path=None):
        self.path = path or Paths.state()
        self.ledger = Ledger(ledger_path or Paths.ledger())
        self._lock = threading.RLock()
        self._st = None

    def rebuild(self):
        st = new_state()
        for ev in self.ledger.read():
            apply_event(st, ev)
        st['rebuilt_from_ledger'] = True
        return st

    def _load(self):
        if self._st is not None:
            return self._st
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding='utf-8') as f:
                    st = json.load(f)
                if not isinstance(st, dict) or not isinstance(st.get('signals'), list):
                    raise ValueError('state schema invalid')
                for k, v in new_state().items():
                    st.setdefault(k, v)
                self._st = st
                return st
            except Exception as e:
                bak = f'{self.path}.corrupt-{utcnow():%Y%m%d%H%M%S}'
                try:
                    os.replace(self.path, bak)
                except Exception as e2:
                    bak = f'(백업 실패: {e2})'
                HEALTH.set('state', 'CRITICAL', f'상태파일 손상({e}) → {bak} 로 보관, 원장에서 재구성')
        self._st = self.rebuild()
        self._save(self._st)
        return self._st

    def _save(self, st):
        tmp = self.path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(json_safe(st), f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            HEALTH.clear('state_save')
        except Exception as e:
            HEALTH.set('state_save', 'CRITICAL', f'상태 저장 실패 — 원장에는 기록됨, 재시작 시 복구: {e}')

    @contextmanager
    def tx(self):
        with self._lock:
            st = self._load()
            try:
                yield st
            finally:
                self._save(st)

    def read(self):
        with self._lock:
            return copy.deepcopy(self._load())

    def peek(self, fn):
        """복사 없이 락 안에서 fn(state) 실행 — fn 은 읽기만 하고 작은 값을 반환해야 한다."""
        with self._lock:
            return fn(self._load())

    def visual(self, signal_id):
        for ev in reversed(self.ledger.read()):
            if ev.get('kind') == 'SIGNAL_DETECTED' and ev['signal'].get('signal_id') == signal_id:
                return ev['signal'].get('visual')
        return None

    def emit(self, st, kind, **payload):
        ev = dict(kind=kind, time=_iso_now(), model_id=MODEL_ID, **payload)
        self.ledger.append(ev)
        apply_event(st, ev)
        return ev


# =============================================================================
# [16] research shadow (가상 추적) · 수동 포지션 (실제) — 서로 섞지 않는다
# =============================================================================
SHADOW_REQUIRED = ('first_bar', 'side', 'tp_px', 'sl_px', 'max_hold_min', 'qty', 'risk_usdt', 'tf', 'H')


def shadow_step(sh, base1m):
    """
    F-02 수정: 채점은 신호 '감지 시각 이후에 시작한' 1분봉부터. 체결가 = 그 첫 봉의 시가.
    반환: 변경 필드 dict (없으면 None). 형식 오류는 ValueError 로 올린다 (R1-N01: 침묵 금지).
    """
    st = sh.get('state')
    if st not in ('PENDING_FILL', 'OPEN'):
        return None
    miss = [k for k in SHADOW_REQUIRED if sh.get(k) in (None, '')]
    if miss:
        raise ValueError(f'shadow 필드 누락: {miss}')
    side = int(sh['side'])
    tp, sl = float(sh['tp_px']), float(sh['sl_px'])
    if side not in (1, -1) or tp <= 0 or sl <= 0 or (side > 0 and not sl < tp) or (side < 0 and not tp < sl):
        raise ValueError(f'shadow 가격/방향 모순: side={side} tp={tp} sl={sl}')
    first = to_naive_utc(sh['first_bar'])
    upd = {}
    fill_t = to_naive_utc(sh['fill_time']) if sh.get('fill_time') else None
    if fill_t is None:
        sub = base1m[base1m.index >= first]
        if sub.empty:
            return None
        fill_t, fill = sub.index[0], float(sub['open'].values[0])
        upd.update(state='OPEN', fill_time=str(fill_t), fill_price=fill)
    else:
        fill = float(sh['fill_price'])
    expiry = fill_t + pd.Timedelta(minutes=int(sh['max_hold_min']))
    sub = base1m[(base1m.index >= fill_t) & (base1m.index < expiry)]
    if sub.empty:
        return upd or None
    op, hi, lo, cl = sub['open'].values, sub['high'].values, sub['low'].values, sub['close'].values
    thr = tp * (1 + side * MAKER_TP_THROUGH)
    if side > 0:
        hs, ht = lo <= sl, hi >= thr
    else:
        hs, ht = hi >= sl, lo <= thr
    i_s = int(np.argmax(hs)) if hs.any() else len(sub)
    i_t = int(np.argmax(ht)) if ht.any() else len(sub)
    covered = sub.index[-1] + pd.Timedelta(minutes=1) >= expiry
    if i_s <= i_t and i_s < len(sub):
        gap_px = min(sl, float(op[i_s])) if side > 0 else max(sl, float(op[i_s]))   # 갭으로 SL 관통 시 더 나쁜 가격
        code, reason, ex_px, ex_t = -1, 'SL', gap_px, sub.index[i_s]
    elif i_t < len(sub):
        code, reason, ex_px, ex_t = 1, 'TP', tp, sub.index[i_t]
    elif covered:
        code, reason, ex_px, ex_t = 0, 'TIME', float(cl[-1]), sub.index[-1]
    else:
        return upd or None
    gross = side * (ex_px / fill - 1.0)
    hours = (ex_t - fill_t).total_seconds() / 3600.0 + 1 / 60
    net = gross - (_leg(ENTRY_TYPE) + _leg(TP_TYPE if code == 1 else SL_TYPE)) - FUNDING_PER_8H * hours / 8
    pnl = float(sh['qty']) * fill * net
    upd.update(state='CLOSED', result=dict(code=code, reason=reason, exit_price=float(ex_px),
                                           exit_time=str(ex_t), net_return=float(net), pnl_usdt=pnl,
                                           r_mult=float(pnl / max(float(sh['risk_usdt']), 1e-12))))
    return upd


def manual_check(pos, base1m, live_price, now):
    """수동 포지션 긴급 이벤트: TP/SL 도달, 최대보유 경과. 반환 [(kind, msg)]"""
    if pos.get('status') in ('CLOSED', 'TP', 'SL'):        # 이미 도달 알림 → 사용자 [포지션 종료] 대기
        return []
    side = int(pos['side'])
    tp, sl = float(pos['tp_px']), float(pos['sl_px'])
    opened = to_naive_utc(pos['opened_at'])
    sub = base1m[base1m.index >= opened.ceil('min')]          # 진입 이후에 시작한 1분봉만
    hi_v, lo_v = [], []
    if len(sub):
        hi_v.append(float(sub['high'].max()))
        lo_v.append(float(sub['low'].min()))
    if live_price is not None and math.isfinite(float(live_price)):
        hi_v.append(float(live_price))
        lo_v.append(float(live_price))
    hi = max(hi_v) if hi_v else -np.inf
    lo = min(lo_v) if lo_v else np.inf
    ev = []
    done = pos.get('alerted') or {}
    tp_hit = hi >= tp if side > 0 else lo <= tp
    sl_hit = lo <= sl if side > 0 else hi >= sl
    if sl_hit and not done.get('SL'):
        ev.append(('SL', f'SL 도달 {sl:,.1f} — 거래소에서 포지션이 정리됐는지 확인하세요'))
    elif tp_hit and not done.get('TP'):
        ev.append(('TP', f'TP 도달 {tp:,.1f} — 체결 여부 확인 후 [포지션 종료] 기록'))
    if now >= opened + pd.Timedelta(minutes=int(pos.get('max_hold_min') or 0)) and not done.get('TIME') \
            and not (sl_hit or tp_hit):
        ev.append(('TIME', f'최대 보유 {int(pos.get("max_hold_min") or 0)}분 경과 — 모델 가정상 청산 권고 (EXIT_RECOMMENDED)'))
    return ev


def prospective_health(signals):
    """
    E5 prospective 감시. 같은 움직임(cluster)은 1표로 센다. 위험을 줄이거나 막을 수만 있다.
    """
    by_cluster = {}
    for s in signals:
        r = ((s.get('shadow') or {}).get('result') or {}).get('r_mult')
        if r is None or not math.isfinite(float(r)):
            continue
        by_cluster.setdefault(s.get('cluster_id') or s['signal_id'], []).append(float(r))
    r = np.asarray([np.mean(v) for v in by_cluster.values()][-60:], dtype=np.float64)
    out = dict(mult=1.0, n=int(len(r)), mean_r=float(np.mean(r)) if len(r) else float('nan'))
    if len(r) < 20:
        out['note'] = f'prospective 표본 {len(r)}건 (<20) — 판단 보류'
        return out
    boots = stationary_block_bootstrap(r, n_boot=1500, mean_block=3.0, rng=np.random.default_rng(len(r)))
    pp = float(np.mean(boots > 0))
    out['p_positive'] = pp
    if pp < 0.20:
        out.update(mult=0.0, block=f'prospective edge 붕괴 의심 P(meanR>0)={pp:.0%} — 신규 진입 중단')
    elif pp < 0.50:
        out.update(mult=0.50, note=f'prospective 약화 P(meanR>0)={pp:.0%} → 위험 50%')
    elif pp < 0.70:
        out.update(mult=0.75, note=f'prospective 불확실 P(meanR>0)={pp:.0%} → 위험 75%')
    return out


def daily_governor(manual, seed, now):
    """실제 수동 포지션 실현손실 기준 일일 kill-switch (KST 날짜)."""
    today = pd.Timestamp(now).tz_localize('UTC').tz_convert(_KST).date()
    losses, pnl = 0, 0.0
    for p in manual:
        if p.get('status') != 'CLOSED' or not p.get('closed_at'):
            continue
        t = pd.Timestamp(to_naive_utc(p['closed_at'])).tz_localize('UTC').tz_convert(_KST).date()
        if t == today:
            v = fnum(p.get('pnl_usdt'), 0.0)
            pnl += v
            losses += v < 0
    if losses >= DAILY_MAX_LOSSES or pnl <= -DAILY_MAX_LOSS_FRAC * float(seed):
        return dict(mult=0.0, block=f'오늘 실현손실 {losses}회 / {pnl:+,.2f} USDT — 일일 한도, 신규 진입 중단')
    return dict(mult=1.0, block=None, losses=losses, pnl=pnl)


def manual_open_risk(manual, side=None, window=None):
    tot = 0.0
    for p in manual:
        if p.get('status') == 'CLOSED':
            continue
        if side is not None and int(p['side']) != side:
            continue
        tot += fnum(p.get('risk_frac'), 0.0)
    return tot


# =============================================================================
# [17] 엔진 — 사이클 오케스트레이션 (GUI 없이도 완결: --once, 테스트, 워크포워드)
# =============================================================================
LIVE_STATUSES = ('ALERTING', 'PENDING_USER', 'SEEN', 'LATE_VALID', 'ENTERED')


def _ceil_minute(t):
    t = pd.Timestamp(t)
    return t if (t.second == 0 and t.microsecond == 0 and t.nanosecond == 0) else t.floor('min') + pd.Timedelta(minutes=1)


def _alert(kind, title, msg, now):
    return dict(kind=kind, title=title, msg=msg, first_at=str(pd.Timestamp(now)), count=0,
                next_at=str(pd.Timestamp(now)), acked=False)


def due_alerts(st, now):
    """재알림 스케줄 도래분. 반환 [(ref_type, ref_id, alert)]"""
    out = []
    now = pd.Timestamp(now)
    for ref_type, items, key in (('signal', st['signals'], 'signal_id'), ('manual', st['manual'], 'pos_id')):
        for x in items:
            a = x.get('pending_alert')
            if not a or a.get('acked') or not a.get('next_at'):
                continue
            if pd.Timestamp(a['next_at']) <= now:
                out.append((ref_type, x[key], a))
    return out


def fetch_last_price(http):
    try:
        return float(http.get_json(f'{FAPI_BASE}/fapi/v1/ticker/price?symbol={SYMBOL}', timeout=5)['price'])
    except Exception as e:
        HEALTH.set('live_price', 'WARN', f'실시간 가격 조회 실패 — 1분봉으로 감시: {type(e).__name__}')
        return None


class Engine:
    def __init__(self, store=None, http=None, state=None):
        self.http = http or PublicHttp()
        self.store = store or DataStore(self.http)
        self.state = state or StateStore()
        self._cycle_lock = threading.Lock()

    # ── 스케줄 ──────────────────────────────────────────────────
    def due_models(self, now=None):
        now = now or utcnow()
        st = self.state.read()
        due = []
        for tf in MODELS:
            key = bar_key(tf, now)
            f = st['fails'].get(tf) or {}
            retry_at = pd.Timestamp(f['retry_at']) if f.get('retry_at') else None
            if retry_at is not None and pd.Timestamp(now) < retry_at:
                continue                                     # backoff 중 — 폭주 금지
            if st['last_scan'].get(tf) != key or (f.get('count', 0) > 0 and f.get('key') == key):
                due.append(tf)
        return due

    def book(self, st, seed, now):
        gov = daily_governor(st['manual'], seed, now)
        pro = prospective_health(st['signals'])
        return dict(prospective_mult=pro['mult'], governor_mult=gov['mult'],
                    governor_block=gov.get('block') or pro.get('block'), prospective=pro, governor=gov)

    # ── 추적 (shadow · 수동) ─────────────────────────────────────
    def update_tracking(self, st, base1m, now, live_price=None):
        events = []
        for s in list(st['signals']):
            sh = s.get('shadow') or {}
            if sh.get('state') in ('PENDING_FILL', 'OPEN'):
                try:
                    upd = shadow_step(sh, base1m)
                except Exception as e:
                    self.state.emit(st, 'SIGNAL_UPDATE', signal_id=s['signal_id'],
                                    fields=dict(shadow=dict(state='QUARANTINED', error=f'{type(e).__name__}: {e}')))
                    HEALTH.set(f"shadow:{s['signal_id']}", 'CRITICAL',
                               f'shadow 형식 오류 → 격리. 신규 스캔은 계속됨: {e}')
                    events.append(('SHADOW_QUARANTINED', s['signal_id']))
                    continue
                if upd:
                    fields = dict(shadow=upd)
                    if upd.get('state') == 'CLOSED':
                        if s.get('status') in ('ALERTING', 'PENDING_USER'):
                            fields['status'] = 'MISSED_' + upd['result']['reason']
                            fields['pending_alert'] = dict(acked=True)
                        events.append(('SHADOW_CLOSED', s['signal_id'], upd['result']))
                    self.state.emit(st, 'SIGNAL_UPDATE', signal_id=s['signal_id'], fields=fields)
            elif sh.get('state') == 'QUARANTINED' and s.get('status') in ('ALERTING', 'PENDING_USER'):
                exp = to_naive_utc(s['detected_at']) + pd.Timedelta(minutes=int(s.get('max_hold_min') or 0))
                if pd.Timestamp(now) > exp:
                    self.state.emit(st, 'SIGNAL_UPDATE', signal_id=s['signal_id'],
                                    fields=dict(status='EXPIRED', pending_alert=dict(acked=True)))
        for p in list(st['manual']):
            if p.get('status') == 'CLOSED':
                continue
            try:
                evs = manual_check(p, base1m, live_price, pd.Timestamp(now))
            except Exception as e:
                HEALTH.set(f"manual:{p.get('pos_id')}", 'CRITICAL', f'수동 포지션 감시 오류: {e}')
                continue
            for kind, msg in evs:
                title = {'TP': 'TP HIT', 'SL': 'SL HIT', 'TIME': 'EXIT_RECOMMENDED'}[kind]
                fields = dict(alerted={kind: _iso_now()}, pending_alert=_alert(title, title, msg, now),
                              status={'TP': 'TP', 'SL': 'SL', 'TIME': 'EXIT_RECOMMENDED'}[kind])
                self.state.emit(st, 'MANUAL_UPDATE', pos_id=p['pos_id'], fields=fields)
                events.append(('MANUAL', p['pos_id'], kind))
        return events

    def monitor(self, seed=None):
        """가벼운 주기 감시: 데이터(1분에 1회 네트워크) + shadow/수동 포지션 이벤트."""
        try:
            self.store.refresh()
        except Exception as e:
            HEALTH.set('data_refresh', 'WARN', f'감시 중 갱신 실패: {e}')
        base = self.store.base
        if base is None or base.empty:
            return []
        st0 = self.state.read()
        live = fetch_last_price(self.http) if any(p.get('status') != 'CLOSED' for p in st0['manual']) else None
        with self.state.tx() as st:
            return self.update_tracking(st, base, utcnow(), live)

    # ── 사이클 ──────────────────────────────────────────────────
    def cycle(self, seed, tfs=None, do_null=True, status=None, stop=None):
        tfs = [tf for tf in (tfs or list(MODELS)) if tf in MODELS]
        status = status or (lambda *a, **k: None)
        if not self._cycle_lock.acquire(blocking=False):
            return wait('ALL', '다른 사이클 실행 중')
        try:
            return self._cycle(float(seed), tfs, do_null, status, stop)
        finally:
            self._cycle_lock.release()

    def _cycle(self, seed, tfs, do_null, status, stop):
        t0 = utcnow()
        keys = {tf: bar_key(tf, t0) for tf in tfs}
        decisions, errors = [], {}
        try:
            status('최신 1분봉 갱신...', 'blue')
            self.store.refresh()
            snap = self.store.snapshot()
        except Exception as e:
            msg = f'데이터 실패: {type(e).__name__}: {e}'
            errors = {tf: msg for tf in tfs}
            final = wait('ALL', msg)
            self._finish(tfs, keys, errors, final, [])
            return final
        with self.state.tx() as st:
            self.update_tracking(st, snap.base, snap.now)
            book = self.book(st, seed, snap.now)
        lag = float(snap.meta.get('lag_min', float('inf')))
        if not math.isfinite(lag) or lag > MAX_STALE_MIN:
            decisions = [wait(tf, f'데이터 지연 {lag:.0f}분 > {MAX_STALE_MIN}분 — 신규 신호 중단') for tf in tfs]
        else:
            status('거래소 규칙·시장 컨텍스트 확인...', 'blue')
            ctx = fetch_context(self.http)
            for tf in tfs:
                try:
                    decisions.append(scan_tf(snap, tf, seed, ctx, book, do_null=do_null, status=status, stop=stop))
                except Exception as e:
                    errors[tf] = f'{type(e).__name__}: {e}'
                    LOG.error(f'scan {tf} 실패\n{traceback.format_exc()}')
                    decisions.append(wait(tf, f'스캔 오류: {errors[tf]}', error=True))
        final = choose(decisions)
        final = self._finish(tfs, keys, errors, final, decisions, snap=snap, seed=seed)
        return final

    def _finish(self, tfs, keys, errors, final, decisions, snap=None, seed=None, origin='SCAN', parent_id=None):
        now = utcnow()
        with self.state.tx() as st:
            for tf in tfs:
                st['last_scan'][tf] = keys[tf]                 # 실패해도 기록 (F-01 폭주 차단)
                if tf in errors:
                    f = st['fails'].get(tf) or {}
                    c = int(f.get('count', 0)) + 1
                    wait_s = FAIL_BACKOFF_SEC[min(c, len(FAIL_BACKOFF_SEC)) - 1]
                    st['fails'][tf] = dict(count=c, key=keys[tf], error=errors[tf],
                                           retry_at=str(pd.Timestamp(now) + pd.Timedelta(seconds=wait_s)))
                    if c >= CRITICAL_AFTER_FAILS:
                        HEALTH.set(f'scan:{tf}', 'CRITICAL', f'{c}회 연속 스캔 실패: {errors[tf]}')
                else:
                    st['fails'].pop(tf, None)
                    HEALTH.clear(f'scan:{tf}')
            if final.get('trade') and snap is not None:
                final = self._register(st, final, seed, snap, origin, parent_id)
        self._log_decision(final, decisions)
        return final

    def _register(self, st, d, seed, snap, origin='SCAN', parent_id=None):
        side = int(d['side'])
        room = min(PORTFOLIO_MAX_OPEN_RISK - manual_open_risk(st['manual']),
                   CLUSTER_MAX_RISK - manual_open_risk(st['manual'], side=side))
        if room + 1e-12 < d['risk_frac']:
            if room < RISK_FLOOR:
                return wait(d['tf'], '열린 수동 포지션 위험으로 포트폴리오/군집 한도 소진 — 신규 WAIT',
                            alternatives=d.get('alternatives'))
            sz = size_position(seed, d['entry'], d['sl'], room, d['tf'], d['H'], d.get('rules') or FALLBACK_RULES)
            if not sz['executable']:
                return wait(d['tf'], f'포트폴리오 한도 반영 후 실행 불가: {sz["reason"]}')
            d = dict(d, risk_frac=room, sizing=sz, portfolio_note=f'열린 위험 반영 → {room:.2%}')
        now = utcnow()
        tag = hashlib.sha1(f'{now.isoformat()}{d["tf"]}{side}{d["entry"]}'.encode()).hexdigest()[:4]
        sid = f"{now:%Y%m%dT%H%M%SZ}-{d['tf'].upper()}-{'L' if side > 0 else 'S'}-{tag}"
        cluster = None
        for s in st['signals']:
            if int(s.get('side') or 0) == side and (s.get('shadow') or {}).get('state') in ('PENDING_FILL', 'OPEN'):
                cluster = s.get('cluster_id') or s['signal_id']
                break
        side_txt = 'LONG' if side > 0 else 'SHORT'
        sz = d['sizing']
        sig = dict(signal_id=sid, detected_at=str(pd.Timestamp(now)), bar_time=d.get('bar_time'),
                   tf=d['tf'], model_label=d.get('model_label'), side=side, entry=d['entry'],
                   entry_ref=d.get('entry_ref'), tp_px=d['tp_px'], sl_px=d['sl_px'], tp=d['tp'], sl=d['sl'],
                   rr=d['rr'], risk_frac=d['risk_frac'], sizing=sz, seed=float(seed), H=d['H'], K=d['K'],
                   max_hold_min=d['max_hold_min'], expected_hold_hours=d.get('expected_hold_hours'),
                   growth=d.get('growth'), winner=d.get('winner'), p_raw=d.get('p_raw'),
                   p_family=d.get('p_family'), null_n=d.get('null_n'), votes=d.get('votes'),
                   confirming=d.get('confirming'), context_notes=d.get('context_notes'),
                   multipliers=d.get('multipliers'), primary_summary=d.get('primary_summary'),
                   visual=d.get('visual'), model_id=MODEL_ID, version=VERSION, status='ALERTING',
                   thesis='VALID', cluster_id=cluster, origin=origin, parent_id=parent_id,
                   pending_alert=_alert(f'NEW {side_txt}', f'NEW {side_txt} — {d["tf"]}',
                                        f'{side_txt} 진입 {d["entry"]:,.1f} / TP {d["tp_px"]:,.1f} / SL {d["sl_px"]:,.1f}',
                                        now),
                   shadow=dict(state='PENDING_FILL', first_bar=str(_ceil_minute(now)), side=side,
                               tp_px=d['tp_px'], sl_px=d['sl_px'], max_hold_min=d['max_hold_min'],
                               qty=sz['qty'], risk_usdt=sz['max_loss_usdt'], tf=d['tf'], H=d['H']))
        self.state.emit(st, 'SIGNAL_DETECTED', signal=sig)
        for s in st['signals']:
            if s['signal_id'] == sid or int(s.get('side') or 0) != -side or s.get('thesis') != 'VALID':
                continue
            exp = to_naive_utc(s['detected_at']) + pd.Timedelta(minutes=int(s.get('max_hold_min') or 0))
            if pd.Timestamp(now) > exp:
                continue
            fields = dict(thesis='INVALIDATED', invalidated_by=sid)
            if s.get('status') in ('ALERTING', 'PENDING_USER'):
                fields.update(status='INVALIDATED', pending_alert=dict(acked=True))
            self.state.emit(st, 'SIGNAL_UPDATE', signal_id=s['signal_id'], fields=fields)
        for p in st['manual']:
            if p.get('status') != 'CLOSED' and int(p['side']) == -side:
                self.state.emit(st, 'MANUAL_UPDATE', pos_id=p['pos_id'], fields=dict(
                    status='EXIT_RECOMMENDED', thesis='INVALIDATED',
                    pending_alert=_alert('THESIS INVALIDATED', 'THESIS INVALIDATED — EXIT 권고',
                                         f'반대 방향 {side_txt} 신호 {sid} 가 검증을 통과했습니다. 보유 포지션의 근거가 깨졌습니다.',
                                         now)))
        out = dict(d, signal_id=sid, cluster_id=cluster)
        return out

    def _log_decision(self, final, decisions):
        rec = dict(time=_iso_now(), model_id=MODEL_ID, trade=bool(final.get('trade')), tf=final.get('tf'),
                   side=final.get('side'), reason=final.get('reason', ''), signal_id=final.get('signal_id'),
                   risk_frac=final.get('risk_frac'),
                   per_tf=[dict(tf=d.get('tf'), trade=d.get('trade'), reason=d.get('reason', '')[:300],
                                p_raw=d.get('p_raw'), p_family=d.get('p_family'),
                                winner=(d.get('primary_summary') or {}).get('winner'))
                           for d in decisions])
        try:
            with open(Paths.decisions(), 'a', encoding='utf-8') as f:
                f.write(json.dumps(json_safe(rec), ensure_ascii=False) + '\n')
        except Exception as e:
            HEALTH.set('decision_log', 'WARN', f'판정 기록 실패: {e}')

    # ── 사용자 행동 ─────────────────────────────────────────────
    def latest_signal(self, st, signal_id=None):
        if signal_id:
            return _find(st['signals'], 'signal_id', signal_id)
        for s in reversed(st['signals']):
            if s.get('status') != 'DISMISSED':
                return s
        return None

    def mark_seen(self, signal_id=None):
        with self.state.tx() as st:
            s = self.latest_signal(st, signal_id)
            if not s:
                return None
            fields = dict(seen_at=_iso_now(), acknowledged=True, pending_alert=dict(acked=True))
            if s.get('status') in ('ALERTING', 'PENDING_USER'):
                fields['status'] = 'SEEN'
            self.state.emit(st, 'SIGNAL_UPDATE', signal_id=s['signal_id'], fields=fields)
            return copy.deepcopy(s)

    def dismiss(self, signal_id):
        with self.state.tx() as st:
            s = self.latest_signal(st, signal_id)
            if s:
                self.state.emit(st, 'SIGNAL_UPDATE', signal_id=s['signal_id'],
                                fields=dict(status='DISMISSED', pending_alert=dict(acked=True)))
            return s

    def ack_alert(self, ref_type, ref_id):
        if ref_type == 'signal':
            return self.mark_seen(ref_id)
        with self.state.tx() as st:
            self.state.emit(st, 'MANUAL_UPDATE', pos_id=ref_id, fields=dict(pending_alert=dict(acked=True)))

    def alert_fired(self, ref_type, ref_id):
        now = pd.Timestamp(utcnow())
        with self.state.tx() as st:
            items, key, kind = ((st['signals'], 'signal_id', 'SIGNAL_UPDATE') if ref_type == 'signal'
                                else (st['manual'], 'pos_id', 'MANUAL_UPDATE'))
            x = _find(items, key, ref_id)
            if not x or not x.get('pending_alert'):
                return
            a = x['pending_alert']
            c = int(a.get('count', 0)) + 1
            nxt = (str(pd.Timestamp(a['first_at']) + pd.Timedelta(minutes=REALERT_MINUTES[c - 1]))
                   if c - 1 < len(REALERT_MINUTES) else None)
            fields = dict(pending_alert=dict(count=c, next_at=nxt, last_at=str(now)))
            if nxt is None and ref_type == 'signal' and x.get('status') == 'ALERTING':
                fields['status'] = 'PENDING_USER'           # 재알림 종료, 카드는 남는다
            payload = dict(signal_id=ref_id) if ref_type == 'signal' else dict(pos_id=ref_id)
            self.state.emit(st, kind, fields=fields, **payload)

    def open_manual(self, signal_id, entry, qty, tp_px, sl_px, seed):
        entry, qty, tp_px, sl_px, seed = map(float, (entry, qty, tp_px, sl_px, seed))
        with self.state.tx() as st:
            s = self.latest_signal(st, signal_id)
            if not s:
                raise ValueError('연결할 신호가 없습니다.')
            side = int(s['side'])
            if side > 0 and not (sl_px < entry < tp_px) or side < 0 and not (tp_px < entry < sl_px):
                raise ValueError('방향과 ENTRY/TP/SL 순서가 맞지 않습니다.')
            risk_usdt = qty * abs(entry - sl_px) + qty * entry * total_cost(s['tf'], int(s['H']))
            pos = dict(pos_id=f"M-{utcnow():%Y%m%dT%H%M%S}-{s['signal_id'][-4:]}", signal_id=s['signal_id'],
                       side=side, entry=entry, qty=qty, tp_px=tp_px, sl_px=sl_px, tf=s['tf'],
                       opened_at=str(pd.Timestamp(utcnow())), max_hold_min=int(s['max_hold_min']),
                       seed=seed, risk_usdt=risk_usdt, risk_frac=risk_usdt / max(seed, 1e-12),
                       status='HEALTHY', thesis='VALID', alerted={})
            self.state.emit(st, 'MANUAL_OPENED', position=pos)
            self.state.emit(st, 'SIGNAL_UPDATE', signal_id=s['signal_id'],
                            fields=dict(status='ENTERED', pending_alert=dict(acked=True), manual_pos_id=pos['pos_id']))
            return pos

    def close_manual(self, pos_id, exit_price):
        exit_price = float(exit_price)
        with self.state.tx() as st:
            p = _find(st['manual'], 'pos_id', pos_id)
            if not p or p.get('status') == 'CLOSED':
                raise ValueError('열린 수동 포지션이 아닙니다.')
            side, entry, qty = int(p['side']), float(p['entry']), float(p['qty'])
            fees = qty * (entry + exit_price) * (TAKER_FEE + SLIPPAGE_T)       # 보수적: 양쪽 taker
            pnl = side * (exit_price - entry) * qty - fees
            self.state.emit(st, 'MANUAL_UPDATE', pos_id=pos_id, fields=dict(
                status='CLOSED', closed_at=str(pd.Timestamp(utcnow())), exit_price=exit_price,
                pnl_usdt=pnl, r_mult=pnl / max(float(p['risk_usdt']), 1e-12), pending_alert=dict(acked=True)))
            return pnl

    def recheck(self, seed, signal_id=None, status=None):
        """늦게 본 신호: 옛 ENTRY 추격 금지. 현재 시장에서 전체 모델을 다시 통과해야 새 주문표."""
        status = status or (lambda *a, **k: None)
        st0 = self.state.read()
        sig = self.latest_signal(st0, signal_id)
        if not sig:
            return dict(valid=False, status='NO_SIGNAL', reason='재검증할 신호가 없습니다.')
        if not self._cycle_lock.acquire(blocking=False):
            return dict(valid=False, status='BUSY', reason='스캔 사이클 실행 중 — 잠시 후 다시')
        try:
            tf, old_side = sig['tf'], int(sig['side'])
            status('재검증: 최신 데이터...', 'blue')
            self.store.refresh()
            snap = self.store.snapshot()
            lag = float(snap.meta.get('lag_min', float('inf')))
            if not math.isfinite(lag) or lag > MAX_STALE_MIN:
                return dict(valid=False, status='STALE', reason=f'데이터 지연 {lag:.0f}분', signal=sig)
            with self.state.tx() as st:
                self.update_tracking(st, snap.base, snap.now)
                book = self.book(st, seed, snap.now)
            ctx = fetch_context(self.http)
            d = scan_tf(snap, tf, float(seed), ctx, book, do_null=True, live=True, status=status)
            valid = bool(d.get('trade')) and int(d.get('side', 0)) == old_side
            if d.get('trade') and not valid:
                why = '현재는 반대 방향이 우세 — 과거 신호 추격 금지'
            elif not valid:
                why = f"현재 가격에서 기존 방향 조건 미충족 — 추격 금지 ({d.get('reason', '')})"
            else:
                why = '현재 가격에서도 같은 방향이 전체 audit 통과 → 새 주문표'
            if valid:
                d = self._finish([], {}, {}, d, [d], snap=snap, seed=seed, origin='RECHECK',
                                 parent_id=sig['signal_id'])
                valid = bool(d.get('trade'))
                if not valid:
                    why = d.get('reason', '')
            name = 'LATE_VALID' if valid else 'EXPIRED'
            with self.state.tx() as st:
                fields = dict(last_recheck=dict(time=_iso_now(), status=name, reason=why,
                                                price=snap.last_price(), new_signal_id=d.get('signal_id')))
                s = _find(st['signals'], 'signal_id', sig['signal_id'])
                if s and s.get('status') in ('ALERTING', 'PENDING_USER', 'SEEN', 'LATE_VALID'):
                    fields['status'] = name
                    fields['pending_alert'] = dict(acked=True)
                self.state.emit(st, 'SIGNAL_UPDATE', signal_id=sig['signal_id'], fields=fields)
            return dict(valid=valid, status=name, reason=why, signal=sig, decision=d,
                        current_price=snap.last_price())
        finally:
            self._cycle_lock.release()


# =============================================================================
# [18] 워크포워드 — '실제로 돌아가는 생산엔진'을 그대로 과거 시점마다 재실행
# -----------------------------------------------------------------------------
#  V611 의 walk_forward 는 V200 연구엔진(build_plan)만 검증했다. 실전 V600 엔진은
#  한 번도 워크포워드되지 않았다. V612 는 scan_tf 를 end=t 로 호출한다 (t 이후 데이터 미사용:
#  analog 검색은 [:t], 채널은 인과적, 레벨은 [:t]). 체결은 감지 직후 1분봉 시가, 보수적 순서.
#  한계: 거래소 컨텍스트(funding/OI 등)는 과거값이 없어 중립 처리. 연구자가 설정을 데이터를
#  보고 골랐다면 그 자유도는 워크포워드로도 제거되지 않는다 → prospective(E5) 가 최종 관문.
# =============================================================================
def make_surrogate_1m(base, block=1440, seed=0):
    """1분 수익률·캔들모양을 하루 블록 단위로 뒤섞은 가짜 BTC. 변동성 군집/팻테일은 남고
    '과거 패턴 → 미래' 관계는 블록 경계에서 끊긴다. 여기서도 벌면 엣지가 아니라 곡선맞춤."""
    g = np.random.default_rng(seed)
    c = base['close'].values.astype(np.float64)
    n = len(c)
    r = np.zeros(n)
    r[1:] = np.diff(np.log(np.maximum(c, 1e-12)))
    rel = {k: base[k].values / np.maximum(c, 1e-12) for k in ('open', 'high', 'low')}
    nb = max(1, n // block)
    order = g.permutation(nb)
    ix = np.concatenate([np.arange(b * block, min((b + 1) * block, n)) for b in order])
    if len(ix) < n:
        ix = np.concatenate([ix, np.arange(len(ix), n)])
    px = c[0] * np.exp(np.cumsum(r[ix]))
    out = pd.DataFrame(index=base.index[:n])
    out['close'] = px
    out['open'] = px * rel['open'][ix]
    out['high'] = np.maximum.reduce([px * rel['high'][ix], out['open'].values, px])
    out['low'] = np.minimum.reduce([px * rel['low'][ix], out['open'].values, px])
    out['volume'] = base['volume'].values[ix]
    out['taker_buy_base'] = base['taker_buy_base'].values[ix]
    out['trades'] = base['trades'].values[ix]
    out['era'] = base['era'].values
    return out[STORE_COLS]


def simulate_ticket(base1m, d, bar_close_time):
    """워크포워드 체결: 기준봉 마감 직후 1분봉 시가에 진입 → shadow 와 같은 규칙으로 채점."""
    sh = dict(state='PENDING_FILL', first_bar=str(bar_close_time), side=d['side'], tp_px=d['tp_px'],
              sl_px=d['sl_px'], max_hold_min=d['max_hold_min'], qty=d['sizing']['qty'],
              risk_usdt=d['sizing']['max_loss_usdt'], tf=d['tf'], H=d['H'])
    upd = shadow_step(sh, base1m)
    if not upd or upd.get('state') != 'CLOSED':
        return None
    res = dict(upd['result'])
    res['fill_price'] = upd.get('fill_price', sh.get('fill_price'))
    res['fill_time'] = upd.get('fill_time')
    return res


def walk_forward(base1m, tf, start, end=None, step=None, seed=10000.0, do_null=False,
                 status=None, stop=None, max_evals=None, use_1m=True):
    status = status or (lambda *a, **k: None)
    spec = MODELS[tf]
    K, H = spec['K'], spec['H']
    base1m = normalize_frame(base1m)
    snap = Snapshot(base1m, base1m.index[-1].to_pydatetime() + timedelta(minutes=1))
    df = snap.tf(tf)
    mins = INTERVALS[tf]
    t = max(int(df.index.searchsorted(pd.Timestamp(start))), 3 * 2 * K + 2 * H + 100)
    t_end = len(df) - H - 2 if end is None else min(int(df.index.searchsorted(pd.Timestamp(end))), len(df) - H - 2)
    step = int(step or H)
    equity, trades, curve, reasons, evals = float(seed), [], [], {}, 0
    ts = ts_ns(df.index)
    while t < t_end:
        if stop and stop():
            break
        if max_evals and evals >= max_evals:
            break
        evals += 1
        if evals % 10 == 0:
            status(f'워크포워드 {tf} {df.index[t]:%Y-%m-%d} | 평가 {evals} | 체결 {len(trades)} | 자산 {equity:,.0f}', 'blue')
        d = scan_tf(snap, tf, equity, NEUTRAL_CONTEXT, book={}, do_null=do_null, end=t, live=False, use_1m=use_1m)
        if not d.get('trade'):
            key = (d.get('reason') or 'WAIT').split(' ')[0][:24]
            reasons[key] = reasons.get(key, 0) + 1
            t += step
            continue
        close_t = pd.Timestamp(ts[t - 1]) + pd.Timedelta(minutes=mins)
        res = simulate_ticket(base1m, d, close_t)
        if res is None:
            break
        pnl = float(res['pnl_usdt'])
        equity = max(equity + pnl, 0.0)
        trades.append(dict(time=str(df.index[t - 1]), side=d['side'], tf=tf, r=res['r_mult'], code=res['code'],
                           reason=res['reason'], risk=d['risk_frac'], lev=d['sizing']['lev'], pnl=pnl,
                           equity=equity, p_family=d.get('p_family')))
        curve.append((res['exit_time'], equity))
        exit_t = pd.Timestamp(res['exit_time'])
        t = max(t + 1, int(df.index.searchsorted(exit_t, side='right')) + 1)
        if equity <= seed * 0.2:
            break
    return dict(report=wf_report(trades, curve, seed, tf, df.index[min(t, len(df) - 1)], evals, reasons, do_null),
                trades=trades, curve=curve, evals=evals)


def wf_report(trades, curve, seed, tf, t_last, evals, reasons, do_null):
    L = [f'━━━ 생산엔진 워크포워드 · {SYMBOL} {tf} · model {MODEL_ID} · null {"ON" if do_null else "OFF(1차만)"} ━━━',
         f'평가 시점 {evals}개 · 마지막 {t_last}']
    if not trades:
        L += ['체결 0건 — 게이트가 전부 걸렀습니다. 이것도 결과입니다.',
              'WAIT 사유 상위: ' + ', '.join(f'{k}×{v}' for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:8])]
        return '\n'.join(L)
    r = np.array([x['r'] for x in trades])
    eq = np.array([seed] + [x['equity'] for x in trades])
    mdd = float((1 - eq / np.maximum.accumulate(eq)).max())
    boots = stationary_block_bootstrap(r, n_boot=3000, mean_block=5.0)
    lo, hi = np.quantile(boots, [0.05, 0.95])
    lr = np.diff(np.log(np.maximum(eq, 1e-9)))
    sr, sr0, dsr = deflated_sharpe(lr, FAMILY_SIZE)
    wins, losses = r[r > 0].sum(), -r[r <= 0].sum()
    per_year = {}
    for x in trades:
        per_year.setdefault(x['time'][:4], []).append(x['r'])
    L += ['─' * 70,
          f'체결 {len(r)}건 · 승률 {np.mean(r > 0):.1%} · 평균 {r.mean():+.3f}R · PF {wins / max(losses, 1e-9):.2f}',
          f'평균 R 90% CI (stationary block bootstrap, L=5): [{lo:+.3f}, {hi:+.3f}]',
          f'자산 {seed:,.0f} → {eq[-1]:,.0f} ({eq[-1] / seed - 1:+.1%}) · MDD {mdd:.1%} · 평균위험 {np.mean([x["risk"] for x in trades]):.2%}',
          f'Sharpe/trade {sr:.2f} · 시행보정 기대최대 {sr0:.2f} · DSR {dsr:.3f}',
          '연도별 평균 R: ' + '  '.join(f'{y}:{np.mean(v):+.2f}({len(v)})' for y, v in sorted(per_year.items())),
          '─' * 70]
    if lo > 0 and dsr >= 0.90 and len(r) >= 50:
        L.append('▶ 표본외 평균 R 의 CI 하한 > 0 이고 DSR ≥ 0.90. (실데이터라면 E4 증거) '
                 '그래도 가짜 BTC 대조군과 prospective shadow 로 재확인할 것.')
    elif r.mean() > 0:
        L.append('▶ 평균은 양(+)이나 CI 하한 ≤ 0 또는 표본/DSR 부족 — 엣지 입증 아님.')
    else:
        L.append('▶ 평균 R ≤ 0 — 이 설정은 실전 근거가 없습니다.')
    L.append('※ 컨텍스트 veto 는 과거값이 없어 중립. 체결 = 감지 직후 1분봉 시가, 동시도달 = 손절.')
    return '\n'.join(L)


# =============================================================================
# [19] 텍스트 렌더링 — 주문표가 먼저, 통계 설명은 그 다음
# =============================================================================
BORDER = '━' * 58


def side_txt(side):
    return 'LONG' if int(side or 0) > 0 else ('SHORT' if int(side or 0) < 0 else '-')


def render_ticket(sig, current_seed=None):
    if not sig:
        return ['[ACTIONABLE SIGNAL] 아직 기록된 V612 신호 없음', '']
    sz = sig.get('sizing') or {}
    live = sig.get('status') in ('ALERTING', 'PENDING_USER', 'SEEN', 'LATE_VALID')
    expired = pd.Timestamp(utcnow()) > to_naive_utc(sig['detected_at']) + pd.Timedelta(minutes=int(sig.get('max_hold_min') or 0))
    head = f"{side_txt(sig['side'])} · {sig.get('model_label') or sig.get('tf')} · {sig.get('signal_id')}"
    L = [BORDER, f'  {head}', BORDER,
         f"SIDE              {side_txt(sig['side'])}",
         f"CURRENT ENTRY     {fnum(sig.get('entry')):,.1f} USDT  (기준봉 종가 {fnum(sig.get('entry_ref')):,.1f})",
         f"MARGIN % OF SEED  {fnum(sz.get('margin_pct'), 0):.2%}",
         f"MARGIN USDT       {fnum(sz.get('margin'), 0):,.2f}",
         f"ISOLATED LEVERAGE {int(sz.get('lev') or 0)}x",
         f"NOTIONAL          {fnum(sz.get('notional'), 0):,.2f} USDT",
         f"BTC QUANTITY      {fnum(sz.get('qty'), 0)}",
         f"TP                {fnum(sig.get('tp_px')):,.1f}  (+{fnum(sig.get('tp'), 0):.3%})",
         f"SL                {fnum(sig.get('sl_px')):,.1f}  (-{fnum(sig.get('sl'), 0):.3%})",
         f"ACCOUNT RISK      {fnum(sz.get('risk_actual'), 0):.3%}",
         f"MAX LOSS          {fnum(sz.get('max_loss_usdt'), 0):,.2f} USDT",
         f"STATUS / TIME     {sig.get('status')} · 감지 {fmt_kst(sig.get('detected_at'))} · 최대보유 {int(sig.get('max_hold_min') or 0) / 60:.1f}h"]
    if sig.get('thesis') == 'INVALIDATED':
        L.append(f"THESIS            INVALIDATED by {sig.get('invalidated_by')}")
    if sig.get('status') == 'ENTERED':
        L.append('※ 실제 진입이 기록된 신호입니다 — 아래 수동 포지션 패널에서 TP/SL/EXIT 를 감시합니다.')
    elif not live or expired:
        L.append('※ 과거 기록입니다. 이 가격으로 추격하지 말고 [늦은 진입 재검증]으로 현재 시장을 다시 평가하세요.')
    if current_seed and abs(float(current_seed) - fnum(sig.get('seed'), 0)) > 1e-9:
        L.append(f"※ 이 주문표는 시드 {fnum(sig.get('seed'), 0):,.2f} 기준. 현재 입력 시드 {float(current_seed):,.2f}.")
    sh = sig.get('shadow') or {}
    if sh.get('state') == 'CLOSED':
        r = sh['result']
        L.append(f"RESEARCH SHADOW   {r['reason']} {r['r_mult']:+.2f}R (체결 {fnum(sh.get('fill_price')):,.1f} → {r['exit_price']:,.1f})")
    elif sh.get('state'):
        L.append(f"RESEARCH SHADOW   {sh.get('state')}" + (f" · {sh.get('error')}" if sh.get('error') else ''))
    if sig.get('last_recheck'):
        lr = sig['last_recheck']
        L.append(f"최근 재검증        {lr.get('status')} · {fmt_kst(lr.get('time'))} · {lr.get('reason', '')[:120]}")
    w, g, ps = sig.get('winner') or {}, sig.get('growth') or {}, sig.get('primary_summary') or {}
    L += ['─' * 58, 'WHY / EVIDENCE',
          f"Analog      r50={fnum(ps.get('median_shape'), 0):.3f} · N_eff={fnum(ps.get('n_eff'), 0):.1f} "
          f"(가중 {fnum(ps.get('n_eff_w'), 0):.1f} / 시간군집 {fnum(ps.get('n_eff_time'), 0):.1f}, 군집 {ps.get('n_time_clusters')}개)",
          f"OOF EV      {fnum(w.get('ev_oof'), 0):+.3%} · 주문표 EV {fnum(w.get('ev_prod'), 0):+.3%} · P(edge>0) {fnum(w.get('edge_prob'), 0):.1%}",
          f"Null        p_raw={fnum(sig.get('p_raw')):.4f} · family×{FAMILY_SIZE} p={fnum(sig.get('p_family')):.3f} (null {sig.get('null_n')}회, 동일추정량)",
          f"Growth      P(성장>0) {fnum(g.get('growth_prob'), 0):.0%} · 25%감쇠 로그성장 {fnum(g.get('growth_eval'), 0):+.5%}/trade · ST-09 안전상한 {fnum(g.get('st09_cap'), 0):.2%}",
          f"MultiScale  {sig.get('votes')} · 동의 TF {sig.get('confirming') or '-'}",
          '감쇠배수    ' + ', '.join(f'{k} {v:.2f}' for k, v in (sig.get('multipliers') or {}).items()),
          f"거래소규칙  {sz.get('rules_source')} · 모델 {sig.get('model_id')}"]
    for nt in sig.get('context_notes') or []:
        L.append(f'컨텍스트    {nt}')
    L.append('')
    return L


def render_live(final):
    if final is None:
        return ['LIVE  24/7 감시 대기', '']
    if final.get('trade'):
        return [f"LIVE  🚨 NEW {side_txt(final['side'])} {final['tf']} → 위 주문표", '']
    L = [f"LIVE  WAIT — {fmt_kst(utcnow())}"]
    alts = final.get('alternatives') or []
    if alts:
        for d in alts:
            L.append(f"  {d.get('tf', '-'):>4}  {str(d.get('reason', 'WAIT'))[:150]}")
    else:
        L.append(f"  {str(final.get('reason', ''))[:200]}")
    L.append('')
    return L


def render_manual(manual):
    open_ = [p for p in manual if p.get('status') != 'CLOSED']
    if not open_:
        return ['수동 포지션  없음 ([내가 진입함]으로 등록하면 TP/SL/EXIT 를 감시합니다)', '']
    L = ['수동 포지션 (실제 계좌 — shadow 와 별개)']
    for p in open_:
        L.append(f"  {p['pos_id']} {side_txt(p['side'])} {p['qty']} BTC @ {p['entry']:,.1f} · TP {p['tp_px']:,.1f} · "
                 f"SL {p['sl_px']:,.1f} · {p.get('status')} · 위험 {fnum(p.get('risk_frac'), 0):.2%}")
    L.append('')
    return L


def render_screen(st, final=None, seed=None):
    sig = None
    for s in reversed(st['signals']):
        if s.get('status') != 'DISMISSED':
            sig = s
            break
    L = [f'PatternEdge {__version__} · {SYMBOL} PERP · model {MODEL_ID} · {fmt_kst(utcnow())}']
    crit = HEALTH.critical()
    if crit:
        L += ['!!! CRITICAL !!!'] + [f'  {k}: {v["msg"]}' for k, v in crit.items()]
    L.append('')
    L += render_ticket(sig, seed)
    L += render_live(final)
    L += render_manual(st['manual'])
    closed = [s for s in st['signals'] if (s.get('shadow') or {}).get('state') == 'CLOSED']
    if closed:
        rr = [s['shadow']['result']['r_mult'] for s in closed]
        L.append(f'Prospective shadow  {len(rr)}건 · 평균 {np.mean(rr):+.2f}R  (E5 증거 축적 중, 20건 미만이면 판단 보류)')
    return '\n'.join(L)


# =============================================================================
# [20] 자가검사 (--selftest) — 네트워크 없이 불변식 확인
# =============================================================================
def _synthetic_1m(n_days=40, seed=0, drift_signal=0.0):
    g = np.random.default_rng(seed)
    n = n_days * 1440
    lv = np.zeros(n)
    e = g.normal(0, 1, n)
    for i in range(1, n):
        lv[i] = 0.9995 * lv[i - 1] + 0.02 * e[i]
    sig = 0.0007 * np.exp(lv)
    r = g.normal(0, 1, n) * sig
    c = 30000 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) * (1 + np.abs(g.normal(0, 0.4, n)) * sig)
    lo = np.minimum(o, c) * (1 - np.abs(g.normal(0, 0.4, n)) * sig)
    v = np.exp(g.normal(3, 0.5, n))
    idx = pd.date_range('2024-01-01', periods=n, freq='1min')
    return pd.DataFrame(dict(open=o, high=hi, low=lo, close=c, volume=v,
                             taker_buy_base=v * np.clip(0.5 + g.normal(0, 0.05, n), 0, 1),
                             trades=np.full(n, 50.0), era=np.full(n, ERA_FUT)), index=idx)


def forbidden_tokens():
    # 문자열을 쪼개 두어 이 함수 자체가 검사에 걸리지 않게 한다
    return ['X-MBX-' + 'APIKEY', '/fapi/v1/' + 'order', '/fapi/v1/' + 'leverage', '/fapi/v1/' + 'marginType',
            'hmac.' + 'new', 'api_' + 'secret', '/s' + 'api/', 'listen' + 'Key', '/fapi/v1/' + 'positionSide']


def selftest(verbose=True):
    results = []

    def check(name, cond, detail=''):
        results.append((name, bool(cond), detail))
        if verbose:
            print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")

    # 1. 브래킷: 같은 봉 동시도달 = 손절, TP 는 관통해야 체결
    HI = np.array([[0.02]])
    LO = np.array([[-0.02]])
    CL = np.array([[0.0]])
    pnl, code = bracket_vec(HI, LO, CL, 1, 0.01, 0.01)
    check('bracket 동시도달=손절', code[0] == -1)
    pnl, code = bracket_vec(np.array([[0.01]]), np.array([[0.0]]), np.array([[0.0]]), 1, 0.01, 0.02)
    check('maker TP 터치만으로는 미체결', code[0] == 0)
    # 2. F-01: 승자 없는 primary → dict WAIT, 예외 없음
    pc = precheck(dict(reason='데이터 부족', K=192), [], '15m', 16)
    check('F-01 precheck 단일 dict 반환', isinstance(pc, dict) and pc['ok'] is False)
    base = _synthetic_1m(12, seed=1)
    snap = Snapshot(base, base.index[-1].to_pydatetime() + timedelta(minutes=1))
    d = scan_tf(snap, '1h', 1000.0, NEUTRAL_CONTEXT, do_null=False)
    check('F-01 scan_tf 짧은 데이터 → WAIT dict', isinstance(d, dict) and d['trade'] is False, d.get('reason', ''))
    # 3. F-02: 감지 이전 봉 미사용
    t_det = base.index[-300]
    sh = dict(state='PENDING_FILL', first_bar=str(t_det), side=1, tp_px=float(base['close'].iloc[-300]) * 1.5,
              sl_px=float(base['close'].iloc[-300]) * 0.5, max_hold_min=60, qty=0.001, risk_usdt=10.0, tf='15m', H=4)
    up = shadow_step(sh, base)
    check('F-02 체결 시각 ≥ 감지 시각', pd.Timestamp(up['fill_time']) >= t_det, up.get('fill_time'))
    # 4. R1-N01: 형식 오류는 예외로 올라온다
    try:
        shadow_step(dict(state='OPEN', first_bar='x'), base)
        check('R1-N01 malformed shadow 예외', False)
    except ValueError:
        check('R1-N01 malformed shadow 예외', True)
    # 5. ST-09: 제로엣지에서 선택 위험 ≤ ST-09 안전상한
    g = np.random.default_rng(5)
    R = g.choice([-1.0, 1.6], size=36, p=[0.42, 0.58]) + g.normal(0, 0.05, 36)
    cand = dict(r_vals=R, r_weights=np.ones(36) / 36, r_order=np.arange(36), side=1, tp=0.012, sl=0.008)
    HIp = np.abs(g.normal(0, .004, (36, 16)))
    LOp = -np.abs(g.normal(0, .004, (36, 16)))
    gr = growth_risk(cand, HIp, LOp, '15m', 16, rng=np.random.default_rng(1))
    check('ST-09 선택위험 ≤ edge소멸 안전상한', gr['risk'] <= gr['st09_cap'] + 1e-12,
          f"risk={gr['risk']:.4f} cap={gr['st09_cap']:.4f}")
    gr0 = growth_risk(dict(cand, r_vals=R - np.mean(R) - 0.01), HIp, LOp, '15m', 16)
    check('음(-)의 edge → 위험 0', gr0['risk'] == 0.0)
    # 6. 사이징은 위험예산을 넘지 않는다
    ok = True
    for i in range(300):
        seed_ = float(g.uniform(50, 50000))
        sz = size_position(seed_, float(g.uniform(20000, 120000)), float(g.uniform(0.002, 0.03)),
                           float(g.uniform(0.0005, 0.01)), '15m', 16, FALLBACK_RULES)
        if sz['executable'] and sz['risk_actual'] > sz['risk_frac'] + 1e-12:
            ok = False
    check('사이징 risk_actual ≤ 예산 (300 무작위)', ok)
    # 7. 컨텍스트 배수 ∈ [0,1]
    m, veto, _ = context_multiplier(dict(spread_bps=1, funding_rate=0.0007, oi_change_1h=0.05, taker_buy_sell=0.5), 1, '15m', 16)
    check('컨텍스트 배수 ∈ [0,1]', 0 <= m <= 1 and veto is None, f'{m:.3f}')
    # 8. 허용목록: 주문 엔드포인트 차단
    try:
        PublicHttp.check_allowed(FAPI_BASE + '/fapi/v1/' + 'order?symbol=BTCUSDT')
        check('REL-012 주문 엔드포인트 차단', False)
    except PermissionError:
        check('REL-012 주문 엔드포인트 차단', True)
    # 9. 소스에 금지 토큰 없음
    try:
        src = open(os.path.abspath(__file__), encoding='utf-8').read()
        hits = [t for t in forbidden_tokens() if t in src]
        check('REL-012 소스 금지토큰 0', not hits, str(hits))
    except NameError:
        check('REL-012 소스 금지토큰 0 (__file__ 없음 — 건너뜀)', True)
    # 10. 원장 재구성 = 상태
    import tempfile
    tmp = tempfile.mkdtemp(prefix='pe612_selftest_')
    ss = StateStore(os.path.join(tmp, 's.json'), os.path.join(tmp, 'l.jsonl'))
    with ss.tx() as st:
        ss.emit(st, 'SIGNAL_DETECTED', signal=dict(signal_id='A', side=1, status='ALERTING', detected_at=_iso_now(),
                                                   max_hold_min=60, visual={'x': 1}))
        ss.emit(st, 'SIGNAL_UPDATE', signal_id='A', fields=dict(status='SEEN'))
    reb = ss.rebuild()
    check('원장 fold 로 상태 재구성', reb['signals'][0]['status'] == 'SEEN' and ss.visual('A') == {'x': 1})
    with open(ss.path, 'w') as f:
        f.write('{broken')
    ss2 = StateStore(ss.path, ss.ledger.path)
    check('손상 상태파일 → 원장에서 자동복구', ss2.read()['signals'][0]['status'] == 'SEEN')
    HEALTH.clear('state')
    n_fail = sum(1 for _, ok_, _ in results if not ok_)
    if verbose:
        print(f'\n{len(results) - n_fail}/{len(results)} PASS')
    return n_fail == 0, results


# =============================================================================
# [21] 알림 — 소리 · 최상단 경고창 · 작업표시줄 깜빡임 · 재알림 (GUI 스레드 전용)
# =============================================================================
class AlertManager:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.windows = {}
        self.system_alerts = {}          # HEALTH CRITICAL → P0 (메모리 스케줄)

    def _sound(self):
        try:
            if os.name == 'nt':
                import winsound
                winsound.PlaySound('SystemExclamation', winsound.SND_ALIAS | winsound.SND_ASYNC)
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                for i in range(3):
                    self.root.after(i * 250, self.root.bell)
        except Exception as e:
            LOG.warning(f'알림음 실패: {e}')
            self.root.bell()

    def _flash(self):
        try:
            self.root.deiconify()
            self.root.lift()
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes

                class FLASHWINFO(ctypes.Structure):
                    _fields_ = [('cbSize', wintypes.UINT), ('hwnd', wintypes.HWND), ('dwFlags', wintypes.DWORD),
                                ('uCount', wintypes.UINT), ('dwTimeout', wintypes.DWORD)]
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x3 | 0xC, 0, 0)   # ALL | TIMERNOFG
                ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception as e:
            LOG.warning(f'작업표시줄 깜빡임 실패: {e}')

    def fire(self, ref_type, ref_id, alert):
        import tkinter as tk
        key = (ref_type, ref_id)
        self._sound()
        self._flash()
        n = int(alert.get('count', 0)) + 1
        text = f"{alert.get('title', alert.get('kind'))}\n\n{alert.get('msg', '')}\n\n알림 {n}회차 · {fmt_kst(utcnow())}"
        w = self.windows.get(key)
        if w is not None and w.winfo_exists():
            w.body.config(text=text)
            w.deiconify()
            w.lift()
            return
        w = tk.Toplevel(self.root)
        w.title(f'🚨 PatternEdge — {alert.get("title", "ALERT")}')
        w.attributes('-topmost', True)
        w.geometry('560x300')
        color = '#b71c1c' if any(k in str(alert.get('kind')) for k in ('SL', 'INVALID', 'CRITICAL', 'EXIT')) else '#0b6e4f'
        tk.Label(w, text=alert.get('title', 'ALERT'), font=('Malgun Gothic', 18, 'bold'), fg='white', bg=color
                 ).pack(fill='x')
        w.body = tk.Label(w, text=text, font=('Malgun Gothic', 11), justify='left', anchor='w', wraplength=520)
        w.body.pack(fill='both', expand=True, padx=12, pady=8)
        fr = tk.Frame(w)
        fr.pack(fill='x', pady=8)
        tk.Button(fr, text='확인 (SEEN) — 재알림 중지', bg=color, fg='white', font=('Malgun Gothic', 11, 'bold'),
                  command=lambda: self._ack(key)).pack(side='left', padx=10)
        tk.Button(fr, text='창 닫기 (재알림 유지)', command=w.withdraw).pack(side='right', padx=10)
        w.protocol('WM_DELETE_WINDOW', w.withdraw)
        self.windows[key] = w

    def _ack(self, key):
        w = self.windows.pop(key, None)
        if w is not None and w.winfo_exists():
            w.destroy()
        ref_type, ref_id = key
        if ref_type == 'system':
            if ref_id in self.system_alerts:
                self.system_alerts[ref_id]['acked'] = True      # HEALTH 표시는 조건이 해소될 때까지 유지
            return
        self.app.run_bg(lambda: self.app.engine.ack_alert(ref_type, ref_id), done='refresh')

    def tick_system(self):
        """HEALTH CRITICAL 을 P0 로 승격. 2/5/15분 재알림 후 중지(표시는 유지)."""
        now = pd.Timestamp(utcnow())
        crit = HEALTH.critical()
        for k in list(self.system_alerts):
            if k not in crit:
                self.system_alerts.pop(k)
        for k, v in crit.items():
            a = self.system_alerts.get(k)
            if a is None:
                a = self.system_alerts[k] = _alert('CRITICAL FAILURE', 'CRITICAL SYSTEM/DATA FAILURE', f'{k}: {v["msg"]}', now)
            if not a.get('acked') and a.get('next_at') and pd.Timestamp(a['next_at']) <= now:
                self.fire('system', k, a)
                a['count'] += 1
                c = a['count']
                a['next_at'] = (str(pd.Timestamp(a['first_at']) + pd.Timedelta(minutes=REALERT_MINUTES[c - 1]))
                                if c - 1 < len(REALERT_MINUTES) else None)


# =============================================================================
# [22] GUI — Tk 는 GUI 스레드에서만 만진다. 작업 스레드는 queue 로만 말한다.
# =============================================================================
def run_gui(engine=None, autoclose_ms=None, on_ready=None):
    """engine/autoclose_ms/on_ready 는 테스트용 주입점. 일반 실행은 인자 없이."""
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    from tkinter.scrolledtext import ScrolledText

    class App:
        def __init__(self, root):
            self.root = root
            Paths.init()
            setup_logging(console=False)
            self.engine = engine or Engine()
            self.q = queue.Queue()
            self.busy = False
            self.monitor_busy = False
            self.last_final = None
            self.alerts = AlertManager(self)
            self._check_instance()
            root.title(f'PatternEdge {__version__} — {SYMBOL} PERP · 주문은 직접 클릭 · 수익 보장 없음')
            root.geometry('1040x960')
            root.protocol('WM_DELETE_WINDOW', self.close)

            top = tk.Frame(root, padx=10, pady=8)
            top.pack(fill='x')
            tk.Label(top, text=f'PatternEdge {VERSION} — ANALOG FIRST · HONEST NULL',
                     font=('Malgun Gothic', 15, 'bold')).grid(row=0, column=0, columnspan=6, sticky='w')
            tk.Label(top, text='시드(USDT)').grid(row=1, column=0, sticky='e')
            self.seed_e = tk.Entry(top, width=12, font=('Consolas', 12))
            self.seed_e.grid(row=1, column=1, sticky='w')
            self.seed_e.insert(0, '1000')
            self.auto_var = tk.IntVar(value=1)
            tk.Checkbutton(top, text='24/7 자동 감시 (5m/15m/1h 봉 마감마다)', variable=self.auto_var
                           ).grid(row=2, column=0, columnspan=6, sticky='w')
            btns = [('지금 전체 분석', self.run_now, '#0b6e4f'), ('신호 확인', self.mark_seen, None),
                    ('늦은 진입 재검증', self.recheck, '#b71c1c'), ('패턴 차트', self.chart, '#263238'),
                    ('내가 진입함', self.open_manual, '#1565c0'), ('포지션 종료', self.close_manual, None),
                    ('신호 기록', self.history, None), ('워크포워드', self.walkforward, '#4527a0'),
                    ('데이터 구축/복구', self.build_data, None), ('상세', self.detail, None)]
            bar = tk.Frame(root, padx=10)
            bar.pack(fill='x')
            self.buttons = {}
            for i, (t, cmd, color) in enumerate(btns):
                kw = dict(bg=color, fg='white') if color else {}
                b = tk.Button(bar, text=t, command=cmd, **kw)
                b.grid(row=i // 5, column=i % 5, sticky='ew', padx=2, pady=2)
                self.buttons[t] = b
            for c in range(5):
                bar.grid_columnconfigure(c, weight=1)
            self.health_l = tk.Label(root, text='', anchor='w', justify='left', fg='#b71c1c', font=('Consolas', 9))
            self.health_l.pack(fill='x', padx=12)
            self.data_l = tk.Label(root, text='데이터 확인 중...', anchor='w', justify='left', font=('Consolas', 9))
            self.data_l.pack(fill='x', padx=12)
            self.status_l = tk.Label(root, text='시작 중...', anchor='w', fg='blue')
            self.status_l.pack(fill='x', padx=12, pady=(0, 4))
            self.txt = ScrolledText(root, height=40, font=('Consolas', 10), wrap='word', state='disabled')
            self.txt.pack(fill='both', expand=True, padx=10, pady=(0, 10))
            self.txt.tag_configure('long', foreground='#0b6e4f', font=('Consolas', 16, 'bold'))
            self.txt.tag_configure('short', foreground='#b71c1c', font=('Consolas', 16, 'bold'))
            self.txt.tag_configure('crit', foreground='white', background='#b71c1c')

            self.root.after(100, self.pump)
            self.root.after(1000, self.tick_fast)
            self.root.after(AUTO_POLL_MS, self.tick_slow)
            self.run_bg(self._boot, done='boot')

        # ── 스레드 경계 ─────────────────────────────────────────
        def post(self, kind, *payload):
            self.q.put((kind, payload))

        def status(self, text, color='black'):
            self.post('status', text, color)                  # 작업 스레드에서 호출해도 안전

        def run_bg(self, fn, done=None, busy=False):
            if busy:
                if self.busy:
                    return False
                self.busy = True

            def work():
                try:
                    out = fn()
                    self.post('done', done, out)
                except Exception as e:
                    LOG.error(traceback.format_exc())
                    self.post('error', f'{type(e).__name__}: {e}')
                finally:
                    if busy:
                        self.post('unbusy')
            threading.Thread(target=work, daemon=True).start()
            return True

        def pump(self):
            try:
                for _ in range(200):
                    kind, payload = self.q.get_nowait()
                    self._handle(kind, payload)
            except queue.Empty:
                pass
            self.root.after(100, self.pump)

        def _handle(self, kind, payload):
            if kind == 'status':
                self.status_l.config(text=payload[0], fg=payload[1])
            elif kind == 'unbusy':
                self.busy = False
            elif kind == 'monitor_done':
                self.monitor_busy = False
                self.refresh_screen()
            elif kind == 'error':
                self.status_l.config(text=f'오류: {payload[0]}', fg='red')
            elif kind == 'done':
                done, out = payload
                if done == 'cycle':
                    self.last_final = out
                    self.status_l.config(text=('🚨 새 주문표 — 원장에 영구 저장' if out.get('trade') else 'WAIT'),
                                         fg='red' if out.get('trade') else '#b26a00')
                elif done == 'recheck':
                    self.show_recheck(out)
                elif done == 'chart':
                    self.show_chart(*out)
                elif done == 'wf':
                    self.text_window('생산엔진 워크포워드', out['report'] + '\n\n' +
                                     json.dumps(json_safe(out['trades'][-50:]), ensure_ascii=False, indent=1))
                elif done == 'boot':
                    self.status_l.config(text='준비 완료 — 24/7 감시', fg='green')
                elif done == 'info':
                    messagebox.showinfo('PatternEdge', str(out))
                self.refresh_screen()

        # ── 화면 ────────────────────────────────────────────────
        def seed(self):
            v = float(self.seed_e.get())
            if not (v > 0):
                raise ValueError('시드는 0보다 커야 합니다.')
            return v

        def refresh_screen(self):
            try:
                seed = self.seed()
            except Exception:
                seed = None
            text = self.engine.state.peek(lambda st: render_screen(st, self.last_final, seed))
            self.txt.config(state='normal')
            self.txt.delete('1.0', 'end')
            self.txt.insert('end', text)
            for tag, word in (('long', 'SIDE              LONG'), ('short', 'SIDE              SHORT')):
                i = self.txt.search(word, '1.0', 'end')
                if i:
                    self.txt.tag_add(tag, i, f'{i} lineend')
            i = self.txt.search('!!! CRITICAL !!!', '1.0', 'end')
            if i:
                self.txt.tag_add('crit', i, f'{i} lineend')
            self.txt.config(state='disabled')
            self.data_l.config(text=self.engine.store.banner())
            self.health_l.config(text='\n'.join(HEALTH.lines()[:6]))

        def text_window(self, title, text):
            w = tk.Toplevel(self.root)
            w.title(title)
            w.geometry('1050x850')
            box = ScrolledText(w, font=('Consolas', 10), wrap='word')
            box.pack(fill='both', expand=True)
            box.insert('1.0', text)
            box.config(state='disabled')

        # ── 주기 작업 ───────────────────────────────────────────
        def tick_fast(self):
            """1초: 재알림 스케줄 (디스크/네트워크 없음)."""
            try:
                now = utcnow()
                for ref_type, ref_id, a in self.engine.state.peek(lambda st: copy.deepcopy(due_alerts(st, now))):
                    self.alerts.fire(ref_type, ref_id, a)
                    self.engine.alert_fired(ref_type, ref_id)
                self.alerts.tick_system()
            except Exception as e:
                HEALTH.set('alert_loop', 'CRITICAL', f'알림 루프 오류: {e}')
            self.root.after(1000, self.tick_fast)

        def tick_slow(self):
            """15초: 새 봉 스캔 스케줄 + 가벼운 감시."""
            try:
                self._heartbeat()
                if self.auto_var.get() and not self.busy:
                    due = self.engine.due_models()
                    if due:
                        self.start_cycle(due, auto=True)
                if not self.busy and not self.monitor_busy:
                    self.monitor_busy = True

                    def mon():
                        try:
                            self.engine.monitor()
                        finally:
                            self.post('monitor_done')
                    threading.Thread(target=mon, daemon=True).start()
                self.refresh_screen()
            except Exception as e:
                HEALTH.set('scheduler', 'CRITICAL', f'스케줄러 오류: {e}')
            self.root.after(AUTO_POLL_MS, self.tick_slow)

        def _boot(self):
            self.status('데이터 로드/갱신 (최초 실행이면 아카이브 전체 구축 — 수 분)...', 'blue')
            self.engine.store.refresh(progress=lambda i, t, m: self.status(f'[{i}/{t}] {m} 다운로드/캐시', 'blue'))
            fetch_rules(self.engine.http)
            return True

        def _check_instance(self):
            p = Paths.lock_file()
            try:
                if os.path.exists(p) and time.time() - os.path.getmtime(p) < 60:
                    HEALTH.set('instance', 'WARN', '다른 PatternEdge 인스턴스가 실행 중일 수 있습니다 (상태 충돌 주의)')
            except Exception as e:
                HEALTH.set('instance', 'WARN', f'인스턴스 잠금 확인 실패: {e}')

        def _heartbeat(self):
            try:
                with open(Paths.lock_file(), 'w') as f:
                    f.write(str(os.getpid()))
            except Exception as e:
                HEALTH.set('instance', 'WARN', f'heartbeat 기록 실패: {e}')

        # ── 버튼 ────────────────────────────────────────────────
        def start_cycle(self, tfs=None, auto=False):
            try:
                seed = self.seed()
            except Exception as e:
                if not auto:
                    messagebox.showerror('입력 오류', str(e))
                return
            self.status(('자동' if auto else '수동') + f' 분석 {tfs or list(MODELS)}...', 'blue')
            self.run_bg(lambda: self.engine.cycle(seed, tfs, status=self.status), done='cycle', busy=True)

        def run_now(self):
            if self.busy:
                messagebox.showinfo('안내', '작업 실행 중입니다.')
                return
            self.start_cycle(None)

        def mark_seen(self):
            self.run_bg(lambda: self.engine.mark_seen(), done='refresh')
            for key in list(self.alerts.windows):
                if key[0] == 'signal':
                    w = self.alerts.windows.pop(key)
                    if w.winfo_exists():
                        w.destroy()

        def recheck(self):
            try:
                seed = self.seed()
            except Exception as e:
                messagebox.showerror('입력 오류', str(e))
                return
            if not self.run_bg(lambda: self.engine.recheck(seed, status=self.status), done='recheck', busy=True):
                messagebox.showinfo('안내', '작업 실행 중입니다.')

        def show_recheck(self, out):
            L = [BORDER, '   늦은 진입 재검증 — 옛 ENTRY 추격 금지', BORDER]
            s = out.get('signal') or {}
            L.append(f"원 신호   {s.get('signal_id', '-')} · {side_txt(s.get('side'))} · 감지 {fmt_kst(s.get('detected_at'))}")
            L.append(f"판정      {out.get('status')} — {out.get('reason')}")
            if out.get('valid'):
                L += ['', '새 주문표 (현재가 기준, 원장에 새 신호로 저장됨):']
                st = self.engine.state.read()
                L += render_ticket(_find(st['signals'], 'signal_id', out['decision'].get('signal_id')))
            else:
                L.append('████  DO NOT CHASE  ████')
            self.text_window('늦은 진입 재검증', '\n'.join(L))

        def chart(self):
            if not MPL_available():
                messagebox.showerror('오류', 'matplotlib 가 없어 차트를 그릴 수 없습니다 (pip install matplotlib).')
                return
            st = self.engine.state.read()
            sig = self.engine.latest_signal(st)
            if not sig:
                messagebox.showinfo('안내', '표시할 신호가 없습니다.')
                return

            def prep():
                vis = self.engine.state.visual(sig['signal_id'])
                if not vis:
                    raise ValueError('이 신호에는 시각 증거가 없습니다.')
                ctx = None
                base = self.engine.store.base
                if base is not None:
                    q_end = to_naive_utc(vis['query_end'])
                    mins = INTERVALS[vis['tf']]
                    a = q_end - pd.Timedelta(minutes=mins * vis['K'] * 1.5)
                    b = q_end + pd.Timedelta(minutes=mins * (vis['H'] + 4))
                    sub = base[(base.index >= a) & (base.index <= b)]['close']
                    ctx = sub.resample(f'{mins}min', label='left', closed='left', origin='epoch').last().dropna()
                return sig, vis, ctx
            self.run_bg(prep, done='chart')

        def show_chart(self, sig, vis, ctx):
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            fig = Figure(figsize=(11.5, 9), dpi=100)
            gs = fig.add_gridspec(3, 1, height_ratios=[1.1, 1.1, 0.9], hspace=0.4)
            ax1, ax2, ax3 = (fig.add_subplot(gs[i, 0]) for i in range(3))
            ax1.plot(vis['pattern'], lw=2.6, color='black', label='Current')
            for a in vis['analogs'][:3]:
                if a.get('pattern'):
                    ax1.plot(a['pattern'], lw=1.4, alpha=0.9,
                             label=f"#{a['rank']} {a['start_ts'][:10]} r={a['corr_shape']:.3f} w={a['weight']:.2f}")
            ax1.set_title(f"Current vs top analogs · {vis['tf']} K={vis['K']} (N={vis['n_neighbors']})")
            ax1.legend(fontsize=8)
            ax1.grid(alpha=0.25)
            fq = vis['future_q']
            x = np.arange(1, len(fq['0.5']) + 1)
            ax2.fill_between(x, fq['0.1'], fq['0.9'], alpha=0.15, label='10–90%')
            ax2.fill_between(x, fq['0.25'], fq['0.75'], alpha=0.25, label='25–75%')
            for a in vis['analogs'][:8]:
                ax2.plot(x[:len(a['future'])], a['future'], lw=0.9, alpha=0.55, color='gray')
            ax2.plot(x, fq['0.5'], lw=2.6, label='median')
            sd = int(vis['side'])
            ax2.axhline(sd * vis['tp'], ls='--', color='green', label='TP')
            ax2.axhline(-sd * vis['sl'], ls='--', color='red', label='SL')
            ax2.axhline(0, color='black', lw=0.8)
            ax2.set_title('What all neighbors did next (vol-scaled to current volatility)')
            ax2.legend(fontsize=8)
            ax2.grid(alpha=0.25)
            if ctx is not None and len(ctx):
                ax3.plot(ctx.index, ctx.values, lw=1.6)
                ax3.axvspan(to_naive_utc(vis['query_start']), to_naive_utc(vis['query_end']), alpha=0.15)
                for y, c in ((sig['entry'], 'black'), (sig['tp_px'], 'green'), (sig['sl_px'], 'red')):
                    ax3.axhline(y, ls=':', color=c)
            ax3.set_title('Price context around the signal (shaded = matched pattern)')
            ax3.grid(alpha=0.25)
            fig.autofmt_xdate()
            w = tk.Toplevel(self.root)
            w.title(f"VISUAL AUDIT — {sig['signal_id']}")
            w.geometry('1180x960')
            tk.Label(w, anchor='w', justify='left', padx=10, pady=6,
                     text=(f"{side_txt(sig['side'])} {sig['tf']} ENTRY {sig['entry']:,.1f} TP {sig['tp_px']:,.1f} SL {sig['sl_px']:,.1f}\n"
                           '육안검사는 통계검증을 대체하지 않는다 — "정말 비슷한가"를 보는 2차 감사용')).pack(fill='x')
            cv = FigureCanvasTkAgg(fig, master=w)
            cv.draw()
            cv.get_tk_widget().pack(fill='both', expand=True)

        def open_manual(self):
            st = self.engine.state.read()
            sig = self.engine.latest_signal(st)
            if not sig:
                messagebox.showinfo('안내', '연결할 신호가 없습니다.')
                return
            sz = sig.get('sizing') or {}
            vals = {}
            for key, label, default in (('entry', '실제 체결가', sig['entry']), ('qty', '수량(BTC)', sz.get('qty')),
                                        ('tp', 'TP 가격', sig['tp_px']), ('sl', 'SL 가격', sig['sl_px'])):
                v = simpledialog.askfloat('내가 진입함', f'{label}', initialvalue=default, parent=self.root)
                if v is None:
                    return
                vals[key] = v
            try:
                seed = self.seed()
                pos = self.engine.open_manual(sig['signal_id'], vals['entry'], vals['qty'], vals['tp'], vals['sl'], seed)
                self.status(f"수동 포지션 등록 {pos['pos_id']} — TP/SL/EXIT 감시 시작", 'green')
            except Exception as e:
                messagebox.showerror('등록 실패', str(e))
            self.refresh_screen()

        def close_manual(self):
            st = self.engine.state.read()
            open_ = [p for p in st['manual'] if p.get('status') != 'CLOSED']
            if not open_:
                messagebox.showinfo('안내', '열린 수동 포지션이 없습니다.')
                return
            p = open_[-1]
            v = simpledialog.askfloat('포지션 종료', f"{p['pos_id']} 실제 청산가", parent=self.root,
                                      initialvalue=self.engine.store.base['close'].values[-1]
                                      if self.engine.store.base is not None else p['entry'])
            if v is None:
                return
            try:
                pnl = self.engine.close_manual(p['pos_id'], v)
                self.status(f"종료 기록 {p['pos_id']} PnL {pnl:+,.2f} USDT (수수료 보수 추정)", 'green')
            except Exception as e:
                messagebox.showerror('종료 실패', str(e))
            self.refresh_screen()

        def history(self):
            st = self.engine.state.read()
            L = [f'V612 SIGNAL LEDGER — {Paths.ledger()}', '']
            for s in reversed(st['signals'][-200:]):
                sh = s.get('shadow') or {}
                res = sh.get('result') or {}
                L.append(f"[{s['signal_id']}] {fmt_kst(s['detected_at'])} {side_txt(s['side'])} {s['tf']} "
                         f"status={s.get('status')} thesis={s.get('thesis')} shadow={sh.get('state')} "
                         f"{('%s %+.2fR' % (res.get('reason'), res.get('r_mult'))) if res else ''}")
                L.append(f"    ENTRY {fnum(s.get('entry')):,.1f} TP {fnum(s.get('tp_px')):,.1f} SL {fnum(s.get('sl_px')):,.1f} "
                         f"risk {fnum((s.get('sizing') or {}).get('risk_actual'), 0):.2%} p_family {fnum(s.get('p_family')):.3f}")
            self.text_window('신호 기록', '\n'.join(L))

        def walkforward(self):
            tf = simpledialog.askstring('워크포워드', 'timeframe (5m / 15m / 1h)', initialvalue='15m', parent=self.root)
            if tf not in MODELS:
                return
            start = simpledialog.askstring('워크포워드', '시작일 (YYYY-MM-DD)',
                                           initialvalue=(utcnow() - timedelta(days=365)).strftime('%Y-%m-%d'),
                                           parent=self.root)
            if not start:
                return
            use_null = messagebox.askyesno('워크포워드', 'matched-null 도 적용할까요? (매우 느림, 정직한 전체 절차)')
            base = self.engine.store.base
            if base is None:
                messagebox.showerror('오류', '데이터가 없습니다.')
                return
            self.run_bg(lambda: walk_forward(base, tf, start, do_null=use_null, status=self.status),
                        done='wf', busy=True)

        def build_data(self):
            def work():
                self.engine.store.build_full_history(
                    progress=lambda i, t, m: self.status(f'[{i}/{t}] {m}', 'blue'))
                self.engine.store.refresh(force=True)
                return '데이터 구축 완료'
            self.run_bg(work, done='info', busy=True)

        def detail(self):
            st = self.engine.state.read()
            txt = [render_screen(st, self.last_final, None), '', '[HEALTH]'] + HEALTH.lines()
            txt += ['', '[DATA]', self.engine.store.banner(), json.dumps(json_safe(self.engine.store.meta), ensure_ascii=False),
                    '', '[LAST DECISION]', json.dumps(json_safe(self.last_final or {}), ensure_ascii=False, indent=1)[:60000],
                    '', f'[FILES] {Paths.base}']
            self.text_window('상세', '\n'.join(txt))

        def close(self):
            try:
                self.engine.store.persist(force=True)
            except Exception as e:
                LOG.error(f'종료 저장 실패: {e}')
            try:
                os.remove(Paths.lock_file())
            except Exception:
                pass
            self.root.quit()
            self.root.destroy()

    root = tk.Tk()
    app = App(root)
    if on_ready:
        root.after(300, lambda: on_ready(app))
    if autoclose_ms:
        root.after(int(autoclose_ms), app.close)
    root.mainloop()
    return app


def MPL_available():
    return importlib.util.find_spec('matplotlib') is not None


# =============================================================================
# [23] 진입점 — IDLE F5 는 인자 없이 GUI
# =============================================================================
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--selftest' in argv:
        ok, _ = selftest()
        return 0 if ok else 1
    Paths.init()
    setup_logging(console=True)
    if '--once' in argv:
        seed = float(os.environ.get('PATTERNEDGE_SEED', '1000'))
        eng = Engine()
        final = eng.cycle(seed, status=lambda t, c='': print(t))
        print(eng.state.peek(lambda st: render_screen(st, final, seed)))
        eng.store.persist(force=True)
        return 0
    if '--walkforward' in argv:
        i = argv.index('--walkforward')
        tf = argv[i + 1] if len(argv) > i + 1 else '15m'
        start = argv[i + 2] if len(argv) > i + 2 else (utcnow() - timedelta(days=365)).strftime('%Y-%m-%d')
        store = DataStore()
        store.refresh()
        base = store.base
        if '--surrogate' in argv:
            base = make_surrogate_1m(base, seed=int(time.time()) % 100000)
            print('★ 가짜 BTC(하루 블록 셔플) — 여기서도 벌면 엣지가 아니라 곡선맞춤 ★')
        res = walk_forward(base, tf, start, do_null='--null' in argv, status=lambda t, c='': print(t))
        print(res['report'])
        return 0
    try:
        run_gui()
    except ImportError as e:
        print(f'tkinter 를 불러올 수 없습니다 ({e}). --once 또는 --selftest 로 실행하세요.')
        return 1
    return 0


if __name__ == '__main__':
    rc = main()
    if 'idlelib' not in sys.modules:           # IDLE 셸을 죽이지 않는다
        sys.exit(rc)
