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
   증거   Evidence ladder 강제: TF 별 실데이터 워크포워드(E4, null ON, 사전등록 기준) 통과 전
          주문표는 '미검증' 표시 + 위험 25%. 인증/실패 모두 원장에 기록

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

try:
    import numpy as np
    import pandas as pd
except ImportError as _e:              # IDLE 에서 F5 했을 때 읽을 수 있는 안내를 남기고 멈춘다
    print('=' * 70)
    print(f' PatternEdge 실행에 필요한 패키지가 없습니다: {_e.name}')
    print(' Windows 명령 프롬프트(cmd)에서 아래 한 줄을 실행한 뒤 IDLE 에서 다시 F5 하세요.')
    print(f'   "{sys.executable}" -m pip install numpy pandas requests pyarrow numba matplotlib')
    print('=' * 70)
    raise SystemExit(1)

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
    from numba import njit, prange
    NUMBA_OK = True
except Exception:
    NUMBA_OK = False
    prange = range

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
INTERVALS = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240}

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
FAMILY_ALPHA = 0.05               # 합성 무엣지 보정실험: null 이 명목보다 ~1.5배 관대 → 0.05 로 실효 FWER ≈ 0.07–0.09
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
# 사용자 규칙: 격리 증거금 = 시드의 최대 20%. 손실 크기는 '수량 × 손절거리'가 정하고,
# 레버리지는 그 수량을 20% 증거금 안에 담는 최소 정수다 → 레버리지가 바뀌어도 손절 시 손실은 같다.
# 손절이 갭으로 무시되는 최악의 경우에도 격리 청산 손실 ≤ 증거금(시드 20%).
MARGIN_CAP = 0.20
MAX_LEV = 20
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
# Evidence ladder 강제: 실데이터 워크포워드(E4) 인증 전에는 주문표를 '미검증'으로 표시하고 위험을 25% 로 축소.
# 무엣지 합성시장에서도 스캔의 ~1% 는 신호가 난다 (24/7 이면 하루 여러 장) — AUDIT 4.3
UNVERIFIED_RISK_MULT = 0.25
WF_PASS_MIN_TRADES = 50           # 사전등록 E4 기준: 체결 ≥ 50, 평균R 90% CI 하한 > 0, DSR ≥ 0.90, null ON
WF_PASS_DSR = 0.90

# ── 비용 ────────────────────────────────────────────────────────
ENTRY_TYPE = 'taker'
TP_TYPE = 'taker'                 # 바이낸스 주문창 TP/SL 체크박스 = 트리거 후 시장가 → taker 비용으로 보수 계산
SL_TYPE = 'taker'                 # (익절을 reduce-only 지정가로 따로 걸 거라면 TP_TYPE = 'maker')
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
    research_journal = classmethod(lambda cls: cls.p(f'{SYMBOL}_research_journal.json'))
    research_md = classmethod(lambda cls: cls.p('PatternEdge_research_journal.md'))
    funding = classmethod(lambda cls: cls.p(f'{SYMBOL}_funding_8h.csv'))
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
                             '/fapi/v1/ticker/24hr', '/fapi/v1/ticker/price', '/fapi/v1/fundingRate',
                             '/futures/data/'),
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
        era_chg = np.zeros(n)
        era_chg[1:] = (np.diff(self.era) != 0)
        self.cum_era = np.concatenate(([0.0], np.cumsum(era_chg)))
        self.cum_bad = np.concatenate(([0.0], np.cumsum(self.bad)))
        self._cache = {}
        self._clock = threading.Lock()

    def window(self, name, s, K):
        return getattr(self, name)[s:s + K]

    def _cached(self, key, fn):
        with self._clock:
            v = self._cache.get(key)
        if v is None:
            v = fn()
            with self._clock:
                self._cache[key] = v
        return v

    def norm(self, name):
        """전 구간 전역 정규화 (상관은 아핀변환 불변 → 어느 prefix 의 상관과도 같다)."""
        def mk():
            T = getattr(self, name)
            s = T.std()
            return (T - T.mean()) / (s if s > 1e-300 else 1.0), (s if s > 1e-300 else 0.0)
        return self._cached(('norm', name), mk)

    def fft(self, name, size):
        return self._cached(('fft', name, size), lambda: np.fft.rfft(self.norm(name)[0], size))

    def sliding_sd(self, name, m):
        return self._cached(('sd', name, m), lambda: _sliding_ms(self.norm(name)[0], m)[1])


def corr_profile_ch(ch, name, Q, limit):
    """
    corr_profile 의 워크포워드 가속판. 전 구간 FFT·창 표준편차를 채널에 캐시하고 질의만 새로 변환한다.
    위치 s ≤ limit-1 의 상관은 T[s:s+m] 만 쓰므로 prefix 로 계산한 값과 같다 (미래 데이터 누수 없음).
    """
    Q = np.asarray(Q, dtype=np.float64)
    m = len(Q)
    qs = Q.std()
    Tn, ts = ch.norm(name)
    n = len(Tn)
    if m < 2 or n < m or qs < 1e-14 or ts <= 0:
        return np.full(limit, -1.0), np.zeros(limit)
    size = 1
    while size < n + m:
        size <<= 1
    qz = (Q - Q.mean()) / qs
    dot = np.fft.irfft(ch.fft(name, size) * np.fft.rfft(qz[::-1], size), size)[m - 1:m - 1 + limit]
    sdn = ch.sliding_sd(name, m)[:limit]
    with np.errstate(divide='ignore', invalid='ignore'):
        r = np.where(sdn > 1e-13, dot / (m * sdn), -1.0)
    return np.clip(np.nan_to_num(r, nan=-1.0), -1.0, 1.0), sdn * ts


def row_quantile(a, q):
    """axis=0 선형보간 분위수 (np.quantile 과 같은 값, 행 수가 적을 때 훨씬 빠름)."""
    s = np.sort(a, axis=0)
    pos = q * (s.shape[0] - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, s.shape[0] - 1)
    return s[lo] + (pos - lo) * (s[hi] - s[lo])


@njit(cache=False)
def dtw_batch(qz, W, band):
    out = np.empty(W.shape[0])
    for i in range(W.shape[0]):
        out[i] = dtw_band(qz, W[i], band)
    return out


_TS_CACHE = {}


def ts_ns_cached(df):
    """1분봉 인덱스 → ns 변환을 프레임당 한 번만 (V612 초판은 scale 마다 350만 행을 다시 변환했다)."""
    idx = df.index
    key = (id(df), len(idx), int(idx[0].value) if len(idx) else 0, int(idx[-1].value) if len(idx) else 0)
    v = _TS_CACHE.get(key)
    if v is None:
        if len(_TS_CACHE) > 4:
            _TS_CACHE.clear()
        v = _TS_CACHE[key] = ts_ns(idx)
    return v


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
    L = max_start + 1
    prof, sds = {}, {}
    for nm in names:
        prof[nm], sds[nm] = corr_profile_ch(ch, nm, q[nm], L)
    idx = np.arange(L)
    span = K + H
    ce, cb = ch.cum_era, ch.cum_bad
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
    core = 0.90 * (wv * stack).sum(0) + 0.10 * row_quantile(stack, 0.20)
    if spot_fallback:
        core = core - SPOT_PENALTY * (ch.era[:L] == ERA_SPOT)

    kpre = max(cand_pool * 3, topk * 12)
    cp = core[pool]
    pre = pool[np.argpartition(-cp, kpre - 1)[:kpre]] if len(pool) > kpre else pool
    pre_score = core[pre] + 0.02 * _session_similarity(ch.ts, pre + K - 1, n - 1)
    cand = pre[np.argsort(-pre_score, kind='stable')][:max(cand_pool, topk * 5)]
    if use_dtw:
        if status:
            status(f'K={K}: DTW 재순위 {len(cand)}개...', 'blue')
        qz = znorm(q['shape'])
        band = max(2, int(K * DTW_BAND_FRAC))
        W = ch.shape[cand[:, None] + np.arange(K)[None, :]]
        sdw = W.std(axis=1, keepdims=True)
        W = np.where(sdw < 1e-14, W - W.mean(axis=1, keepdims=True),
                     (W - W.mean(axis=1, keepdims=True)) / np.maximum(sdw, 1e-300))
        dtw = dtw_batch(qz, np.ascontiguousarray(W), band)
        dn = (dtw - np.nanmin(dtw)) / max(np.nanstd(dtw), 1e-9)
        ordered = cand[np.argsort(-(core[cand] - 0.025 * dn))]
    else:
        ordered = cand[np.argsort(-core[cand])]
    starts = np.asarray(pick_nonoverlap(ordered, topk, span), dtype=np.int64)
    if len(starts) < MIN_NEIGHBORS:
        return None, f'독립(비중첩) analog {len(starts)}개 < {MIN_NEIGHBORS}'

    exact = {nm: corr_exact(q[nm], getattr(ch, nm), starts) for nm in ANALOG_WEIGHTS}
    ex = np.vstack([exact[nm] for nm in ANALOG_WEIGHTS])
    sim = 0.90 * (wv * ex).sum(0) + 0.10 * row_quantile(ex, 0.20)
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
            self.b_ts = ts_ns_cached(base1m)

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
# [13] 사이징 — 위험예산이 수량(명목)을 정하고, 레버리지는 그 명목을 시드 20% 증거금에 담는 최소 정수
#      손절 시 손실 = 수량 × (손절거리 + 비용) = 위험예산. 레버리지 배수와 무관하게 일정하다.
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


def primary_gate(primary, tf, H):
    """주 scale 만으로 판정 가능한 실패 사유. 하나라도 있으면 다른 scale 은 계산할 필요가 없다."""
    if 'winner' not in primary:
        return [primary.get('reason') or '주 신호 없음']
    pc = precheck(primary, [primary, primary], tf, H)     # 투표는 자기 자신으로 채워 '주 scale 사유'만 남긴다
    return [x for x in pc['reason'].split(' / ') if x]


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
    seed0 = NULL_SEED + INTERVALS[tf] + (n % 100_000)

    def rng_for(kk):                         # scale 마다 독립 난수 → 계산 순서·생략과 무관하게 같은 결과
        return np.random.default_rng(seed0 + 7919 * kk)
    rng = rng or rng_for(K)
    status(f'{tf} K={K}: analog + cross-fit...', 'blue')
    primary = analyze_scale(snap, ch, tf, K, H, rules, n, topk, lv, use_1m, rng, status)
    d = dict(tf=tf, K=K, H=H, trade=False, model_label=spec['label'], votes=[], precheck_ok=False,
             bar_time=str(pd.Timestamp(ch.ts[n - 1])), primary_summary=_primary_summary(primary))
    gate = primary_gate(primary, tf, H)
    if gate:                                 # 주 scale 에서 이미 탈락 → 나머지 scale 생략 (판정 동일, 약 3배 빠름)
        d['reason'] = ' / '.join(gate)
        return d
    scales = [primary]
    for f in SCALE_FACTORS:
        kk = max(30, int(round(K * f)))
        if kk == K:
            continue
        if stop and stop():
            return wait(tf, '중단됨', K=K, H=H)
        status(f'{tf} K={kk}: analog + cross-fit...', 'blue')
        scales.append(analyze_scale(snap, ch, tf, kk, H, rules, n, topk, lv, use_1m, rng_for(kk), status))
    pc = precheck(primary, scales, tf, H)
    d['votes'] = pc['votes']
    if not pc['ok']:
        d['reason'] = pc['reason']
        return d
    d['precheck_ok'] = True
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
    ev_level = 'E3'
    if book.get('evidence_gate'):
        cert = (book.get('evidence') or {}).get(tf) or {}
        verified = cert.get('model_id') == MODEL_ID and cert.get('level') == 'E4'
        refuted = (cert.get('model_id') == MODEL_ID and cert.get('level') == 'FAILED' and cert.get('do_null')
                   and not cert.get('surrogate') and not (cert.get('summary') or {}).get('passed'))
        if refuted:                          # 실데이터·null ON 에서 사전 기준을 못 넘음 = 반증 → 위험만 줄여 내보내지 않는다 (L8·L14)
            d['evidence_level'] = '반증(E4 실패)'
            d['reason'] = (f'{tf} 모델은 실데이터 워크포워드(null ON)에서 반증되었습니다 → 주문표를 만들지 않습니다 '
                           f'(다시 인증받기 전까지)')
            return d
        ev_level = 'E4' if verified else 'E3(미검증)'
        mults['evidence_ladder'] = 1.0 if verified else UNVERIFIED_RISK_MULT
    d['evidence_level'] = ev_level
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
                last_scan={}, fails={}, evidence={}, rebuilt_from_ledger=False)


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
    elif k == 'EVIDENCE':
        st.setdefault('evidence', {})[ev['tf']] = copy.deepcopy(ev['certificate'])
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
    thr = tp * (1 + side * (MAKER_TP_THROUGH if TP_TYPE == 'maker' else 0.0))
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
                    governor_block=gov.get('block') or pro.get('block'), prospective=pro, governor=gov,
                    evidence_gate=True, evidence=copy.deepcopy(st.get('evidence') or {}))

    def record_walkforward(self, tf, res, do_null, surrogate, data_note=''):
        """
        Evidence ladder 를 코드로 강제한다. 실데이터·null ON·대조군 아님·사전 기준 통과일 때만
        (tf, model_id) 에 E4 인증을 원장에 기록한다. 실패도 기록한다 (cherry-picking 금지).
        """
        s = res.get('summary') or {}
        passed = bool(s.get('passed')) and do_null and not surrogate
        cert = dict(level='E4' if passed else 'FAILED', model_id=MODEL_ID, time=_iso_now(), do_null=bool(do_null),
                    surrogate=bool(surrogate), summary=s, note=data_note)
        with self.state.tx() as st:
            if passed or ((st.get('evidence') or {}).get(tf) or {}).get('model_id') != MODEL_ID:
                self.state.emit(st, 'EVIDENCE', tf=tf, certificate=cert)
            else:                                            # 기존 E4 는 유지하되 실패 실험도 원장에 남긴다
                self.state.emit(st, 'SYSTEM', what='walkforward_failed', tf=tf, certificate=cert)
        return cert

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
                   evidence_level=d.get('evidence_level'),
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
    return _reorder_frame(base, ix, r, rel)


def _reorder_frame(base, ix, r=None, rel=None):
    """봉 순서 ix 로 수익률·캔들모양·거래량을 재배치해 새 가격 경로를 만든다 (시각과 era 는 그대로)."""
    c = base['close'].values.astype(np.float64)
    n = len(c)
    if r is None:
        r = np.zeros(n)
        r[1:] = np.diff(np.log(np.maximum(c, 1e-12)))
        rel = {k: base[k].values / np.maximum(c, 1e-12) for k in ('open', 'high', 'low')}
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


# ── 워크포워드 가속 ──────────────────────────────────────────────
#  ① 판정 단계와 체결/복리 단계를 분리한다. 각 시점의 판정은 그 시점 이전 데이터만 보므로 서로 독립 →
#     CPU 코어 수만큼 병렬로 계산하고, 체결·복리·포지션 겹침은 그 뒤에 순서대로 재생(replay)한다.
#  ② 2단계 null: 1차(검색+교차검증)는 모든 시점, 비싼 matched-null 은 1차 통과 시점만.
#     null 은 원래 1차 통과 후에만 돌기 때문에 결과는 전 시점 null 과 완전히 같다.
#  ③ 디스크 캐시: (모델지문, TF, 봉시각) 단위로 판정을 저장 → 같은 구간 재실행·null ON 재실행·
#     시드만 바꾼 재실행은 즉시 끝난다. 과거 데이터가 바뀌면 지문/체크섬 불일치로 자동 재계산.
WF_REF_SEED = 1e6                 # 판정 단계용 기준 시드 (실제 시드 사이징은 replay 에서 다시 한다)
WF_DEFAULT_WORKERS = max(1, min((os.cpu_count() or 2) - 1, 6))
_WF_W = {}


def _wf_compact(d):
    keep = ('tf', 'trade', 'reason', 'side', 'entry', 'entry_ref', 'tp_px', 'sl_px', 'tp', 'sl', 'risk_frac',
            'max_hold_min', 'H', 'K', 'p_raw', 'p_family', 'null_n', 'precheck_ok', 'rules', 'bar_time')
    out = {k: d.get(k) for k in keep if k in d}
    out['reason'] = str(out.get('reason') or '')[:200]
    return json_safe(out)


def _wf_init(base_path, now_iso):
    base = pd.read_pickle(base_path)
    _WF_W['snap'] = Snapshot(base, pd.Timestamp(now_iso).to_pydatetime())


def _wf_eval_with(snap, tf, t, do_null, use_1m=True):
    try:
        d = scan_tf(snap, tf, WF_REF_SEED, NEUTRAL_CONTEXT, book={}, do_null=do_null, end=t, live=False, use_1m=use_1m)
    except Exception as e:
        d = wait(tf, f'스캔 오류: {type(e).__name__}: {e}')
    out = _wf_compact(d)
    ch = snap.channels(tf)
    out['chk'] = float(np.round(np.sum(ch.close[max(0, t - 64):t]), 4))     # 국소 데이터 체크섬
    return t, out


def _wf_eval(args):
    tf, t, do_null, use_1m = args
    return _wf_eval_with(_WF_W['snap'], tf, t, do_null, use_1m)


def _wf_fingerprint(base1m, anchor):
    """WF 시작 이전 이력의 지문 (가짜 BTC·데이터 교체를 구별)."""
    pre = base1m['close'].values[:max(1, int(anchor))]
    h = hashlib.sha1()
    h.update(str((len(pre), str(base1m.index[0]))).encode())
    h.update(np.ascontiguousarray(pre[::997]).tobytes())
    return h.hexdigest()[:16]


def _wf_cache_path(tf, fp, do_null, use_1m):
    d = Paths.p('wf_cache')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f'{MODEL_ID}_{tf}_{fp}_{"null" if do_null else "s1"}{"" if use_1m else "_tf"}.json')


def _wf_cache_load(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        HEALTH.set('wf_cache', 'WARN', f'워크포워드 캐시 손상 → 재계산: {e}')
        return {}


def _wf_cache_save(path, cache):
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        HEALTH.set('wf_cache', 'WARN', f'워크포워드 캐시 저장 실패 (결과는 정상): {e}')


def wf_decisions(base1m, snap, tf, grid, do_null, workers=1, status=None, stop=None, use_1m=True,
                 cache_path=None, stats=None):
    """grid 시점들의 판정 {t: compact}. 캐시 → 병렬 → 순차 순서로 시도."""
    status = status or (lambda *a, **k: None)
    stats = stats if stats is not None else {}
    df = snap.tf(tf)
    ch = snap.channels(tf)
    cache = _wf_cache_load(cache_path) if cache_path else {}
    out, todo = {}, []
    for t in grid:
        key = str(df.index[t - 1])
        c = cache.get(key)
        if c is not None and abs(c.get('chk', -1) - float(np.round(np.sum(ch.close[max(0, t - 64):t]), 4))) < 1e-6:
            out[t] = c
        else:
            todo.append(t)
    stats['cache_hits'] = stats.get('cache_hits', 0) + len(out)
    stats['computed'] = stats.get('computed', 0) + len(todo)
    t0 = time.time()

    def note(i):
        if i and (i % 20 == 0 or i == len(todo)):
            rate = i / max(time.time() - t0, 1e-9)
            status(f'워크포워드 {tf} {"null" if do_null else "1차"} {i}/{len(todo)} '
                   f'({rate:.1f}개/초, 남은 {max(len(todo) - i, 0) / max(rate, 1e-9):.0f}초, 작업자 {workers})', 'blue')

    done = 0
    if workers > 1 and len(todo) > 2 * workers:
        tmp = Paths.p(f'wf_base_{os.getpid()}.pkl')
        try:
            base1m.to_pickle(tmp)
            from concurrent.futures import ProcessPoolExecutor, as_completed
            import multiprocessing
            ctx = multiprocessing.get_context(os.environ.get('PATTERNEDGE_MP_START') or None)
            with ProcessPoolExecutor(max_workers=workers, initializer=_wf_init, mp_context=ctx,
                                     initargs=(tmp, str(pd.Timestamp(snap.now)))) as ex:
                futs = [ex.submit(_wf_eval, (tf, t, do_null, use_1m)) for t in todo]
                for f in as_completed(futs):
                    t, d = f.result()
                    out[t] = d
                    cache[str(df.index[t - 1])] = d
                    done += 1
                    note(done)
                    if stop and stop():
                        for g in futs:
                            g.cancel()
                        break
            todo = [t for t in todo if t not in out]
        except Exception as e:
            HEALTH.set('wf_parallel', 'WARN', f'병렬 실행 실패 → 순차로 계속: {type(e).__name__}: {e}')
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    for t in todo:
        if stop and stop():
            break
        t_, d = _wf_eval_with(snap, tf, t, do_null, use_1m)
        out[t] = d
        cache[str(df.index[t - 1])] = d
        done += 1
        note(done)
    if cache_path:
        _wf_cache_save(cache_path, cache)
    return out


def walk_forward(base1m, tf, start, end=None, step=None, seed=10000.0, do_null=False,
                 status=None, stop=None, max_evals=None, use_1m=True, workers=None, use_cache=True):
    """
    생산엔진 워크포워드. 평가 시점 = start 부터 step 봉 간격의 고정 격자.
    포지션이 열려 있는 동안의 시점은 건너뛴다 (겹치는 포지션 없음). 결과는 작업자 수·캐시와 무관하게 같다.
    """
    status = status or (lambda *a, **k: None)
    t_start_wall = time.time()
    spec = MODELS[tf]
    K, H = spec['K'], spec['H']
    base1m = normalize_frame(base1m)
    snap = Snapshot(base1m, base1m.index[-1].to_pydatetime() + timedelta(minutes=1))
    df = snap.tf(tf)
    mins = INTERVALS[tf]
    t0 = max(int(df.index.searchsorted(pd.Timestamp(start))), 3 * 2 * K + 2 * H + 100)
    t_end = len(df) - H - 2 if end is None else min(int(df.index.searchsorted(pd.Timestamp(end))), len(df) - H - 2)
    step = int(step or max(1, H // 4))          # 기본: 보유기간의 1/4 간격 (15m 이면 1시간). 정밀 검증은 step=1
    grid = list(range(t0, t_end, step))
    if max_evals:
        grid = grid[:int(max_evals)]
    workers = WF_DEFAULT_WORKERS if workers is None else max(1, int(workers))
    fp = _wf_fingerprint(base1m, int(base1m.index.searchsorted(df.index[t0 - 1])) if grid else 1)
    stats = {}
    cp1 = _wf_cache_path(tf, fp, False, use_1m) if use_cache else None
    dec = wf_decisions(base1m, snap, tf, grid, False, workers, status, stop, use_1m, cp1, stats)
    if do_null:
        finalists = [t for t in grid if dec.get(t, {}).get('precheck_ok')]
        status(f'워크포워드 {tf}: 1차 통과 {len(finalists)}/{len(grid)} 시점만 matched-null', 'blue')
        cpn = _wf_cache_path(tf, fp, True, use_1m) if use_cache else None
        dec.update(wf_decisions(base1m, snap, tf, finalists, True, workers, status, stop, use_1m, cpn, stats))
    # replay — 실제 시드로 사이징·체결·복리, 포지션 겹침 금지
    ts = ts_ns(df.index)
    equity, trades, curve, reasons, next_free, last_t = float(seed), [], [], {}, 0, t0
    for t in grid:
        if t not in dec:
            break                                            # 중단된 지점
        last_t = t
        if t < next_free:
            continue
        d = dec[t]
        if not d.get('trade'):
            key = (d.get('reason') or 'WAIT').split(' ')[0][:24]
            reasons[key] = reasons.get(key, 0) + 1
            continue
        sz = size_position(equity, d['entry'], d['sl'], d['risk_frac'], tf, H, d.get('rules') or FALLBACK_RULES)
        if not sz['executable']:
            reasons['사이징불가'] = reasons.get('사이징불가', 0) + 1
            continue
        dd = dict(d, sizing=sz)
        res = simulate_ticket(base1m, dd, pd.Timestamp(ts[t - 1]) + pd.Timedelta(minutes=mins))
        if res is None:
            break
        pnl = float(res['pnl_usdt'])
        equity = max(equity + pnl, 0.0)
        trades.append(dict(time=str(df.index[t - 1]), side=d['side'], tf=tf, r=res['r_mult'], code=res['code'],
                           reason=res['reason'], risk=d['risk_frac'], lev=sz['lev'], pnl=pnl,
                           equity=equity, p_family=d.get('p_family')))
        curve.append((res['exit_time'], equity))
        next_free = int(df.index.searchsorted(pd.Timestamp(res['exit_time']), side='right')) + 1
        if equity <= seed * 0.2:
            break
    evals = len([t for t in grid if t in dec])
    summary = wf_summary(trades, seed)
    summary.update(tf=tf, evals=evals, start=str(start), end=str(df.index[min(last_t, len(df) - 1)]),
                   do_null=bool(do_null), step=step, workers=workers, seconds=round(time.time() - t_start_wall, 1),
                   cache_hits=stats.get('cache_hits', 0), computed=stats.get('computed', 0))
    return dict(report=wf_report(trades, summary, seed, tf, evals, reasons, do_null),
                trades=trades, curve=curve, evals=evals, summary=summary)


def wf_summary(trades, seed):
    if not trades:
        return dict(n=0, passed=False)
    r = np.array([x['r'] for x in trades])
    eq = np.array([seed] + [x['equity'] for x in trades])
    boots = stationary_block_bootstrap(r, n_boot=3000, mean_block=5.0)
    lo, hi = np.quantile(boots, [0.05, 0.95])
    sr, sr0, dsr = deflated_sharpe(np.diff(np.log(np.maximum(eq, 1e-9))), FAMILY_SIZE)
    return dict(n=int(len(r)), mean_r=float(r.mean()), ci_lo=float(lo), ci_hi=float(hi), dsr=float(dsr),
                sr=float(sr), sr0=float(sr0), mdd=float((1 - eq / np.maximum.accumulate(eq)).max()),
                final_equity=float(eq[-1]),
                passed=bool(lo > 0 and dsr >= WF_PASS_DSR and len(r) >= WF_PASS_MIN_TRADES))


def wf_report(trades, s, seed, tf, evals, reasons, do_null):
    L = [f'━━━ 생산엔진 워크포워드 · {SYMBOL} {tf} · model {MODEL_ID} · null {"ON" if do_null else "OFF(1차만)"} ━━━',
         f'평가 시점 {evals}개 (step {s.get("step")}봉) · 구간 {s.get("start")} ~ {s.get("end")}',
         f'속도: {s.get("seconds")}초 · 새로 계산 {s.get("computed")} · 캐시 재사용 {s.get("cache_hits")} · 작업자 {s.get("workers")}개']
    if not trades:
        L += ['체결 0건 — 게이트가 전부 걸렀습니다. 이것도 결과입니다.',
              'WAIT 사유 상위: ' + ', '.join(f'{k}×{v}' for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:8])]
        return '\n'.join(L)
    r = np.array([x['r'] for x in trades])
    eq = np.array([seed] + [x['equity'] for x in trades])
    mdd, lo, hi, sr, sr0, dsr = s['mdd'], s['ci_lo'], s['ci_hi'], s['sr'], s['sr0'], s['dsr']
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
    if s['passed']:
        L.append(f'▶ 사전등록 기준 통과 (CI 하한 > 0, DSR ≥ {WF_PASS_DSR}, 체결 ≥ {WF_PASS_MIN_TRADES}). '
                 '실데이터 + null ON 이면 이 TF 는 E4 인증되어 위험 축소가 풀린다. 가짜 BTC 대조군도 꼭 돌릴 것.')
    elif r.mean() > 0:
        L.append('▶ 평균은 양(+)이나 CI 하한 ≤ 0 또는 표본/DSR 부족 — 엣지 입증 아님.')
    else:
        L.append('▶ 평균 R ≤ 0 — 이 설정은 실전 근거가 없습니다.')
    L += growth_decomposition_lines(trades, s, seed)
    L.append('※ 컨텍스트 veto 는 과거값이 없어 중립. 체결 = 감지 직후 1분봉 시가, 동시도달 = 손절.')
    return '\n'.join(L)


def _kelly_risk(R, cap=0.30):
    grid = np.linspace(0.0, cap, 301)
    with np.errstate(invalid='ignore', divide='ignore'):
        g = np.log1p(np.outer(grid, R))
    g[~np.isfinite(g)] = -1e9
    m = g.mean(axis=1)
    j = int(np.argmax(m))
    return float(grid[j]) if m[j] > 0 else 0.0


def growth_decomposition(trades, s, seed):
    """'왜 느린가'를 숫자로: 연 체결수 × 거래당 위험 × 평균R, 그리고 증거가 허용하는 최대 속도(반켈리)."""
    if not trades:
        return None
    R = np.array([x['r'] for x in trades], dtype=np.float64)
    risk = np.array([x['risk'] for x in trades], dtype=np.float64)
    years = max((to_naive_utc(s['end']) - to_naive_utc(s['start'])).total_seconds() / (365.25 * 86400), 1e-6)
    n_year = len(R) / years
    eq_end = trades[-1]['equity']
    cagr = (max(eq_end, 1e-9) / seed) ** (1 / years) - 1
    g_trade = float(np.mean(np.log1p(np.clip(risk * R, -0.999, None))))
    shift = float(R.mean() - s['ci_lo'])
    f_rob = _kelly_risk(R - shift) if s['ci_lo'] > 0 else 0.0           # 참 평균R = CI 하한이라고 가정
    half = 0.5 * f_rob
    g_half = float(np.mean(np.log1p(half * (R - shift)))) if half > 0 else 0.0
    cagr_half = math.exp(g_half * n_year) - 1
    need = math.log(1.01) * 365 / max(n_year, 1e-9)                      # 하루 1% 에 필요한 거래당 로그성장
    return dict(years=years, n_year=n_year, avg_risk=float(risk.mean()), mean_r=float(R.mean()),
                cagr=cagr, daily=(1 + cagr) ** (1 / 365) - 1, g_trade=g_trade, ci_lo=s['ci_lo'],
                robust_kelly=f_rob, half_kelly=half, cagr_half=cagr_half,
                daily_half=(1 + cagr_half) ** (1 / 365) - 1, need_per_trade=need)


def growth_decomposition_lines(trades, s, seed):
    g = growth_decomposition(trades, s, seed)
    if not g:
        return []
    L = ['── 성장 분해 (왜 이 속도인가) ──',
         f"연 체결 {g['n_year']:.0f}건 × 평균위험 {g['avg_risk']:.2%} × 평균 {g['mean_r']:+.3f}R "
         f"→ 연 {g['cagr']:+.1%} (하루 평균 {g['daily']:+.3%})"]
    if g['ci_lo'] > 0:
        L.append(f"증거가 허용하는 최대 속도: 평균R 을 CI 하한 {g['ci_lo']:+.3f} 로 낮춰 잡은 반켈리 = 거래당 위험 "
                 f"{g['half_kelly']:.2%} → 같은 거래수면 연 {g['cagr_half']:+.1%} (하루 {g['daily_half']:+.3%})")
        L.append(f'   ※ 이론 상한일 뿐 실전 적용 아님: 실전 위험은 상한 {RISK_CAP:.0%}·ST-09·증거 단계가 결정한다. '
                 'prospective(E5)로 같은 edge 가 확인되기 전에는 이 숫자대로 걸지 말 것.')
    else:
        L.append('증거가 허용하는 최대 속도: 평균R 의 CI 하한 ≤ 0 → 위험을 올릴 통계적 근거 없음 '
                 '(올리면 이익이 아니라 운의 크기만 같은 배율로 커진다)')
    L.append(f"하루 1% (연 3,678%) 에 필요한 것: 연 {g['n_year']:.0f}건 기준 거래당 로그성장 {g['need_per_trade']:.2%} "
             f"(현재 {g['g_trade']:+.3%}) — 거래 수를 늘리거나 거래당 edge 를 키워야 하며, 위험만 키우면 켈리 초과로 오히려 느려진다")
    if (s.get('step') or 1) > 1:
        L.append(f"※ 평가 간격 step {s.get('step')}봉: 실시간 감시는 매 봉 평가하므로 실제 거래 빈도를 보려면 --step 1 (캐시로 재실행 가능)")
    return L


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
         f"MAX LOSS          {fnum(sz.get('max_loss_usdt'), 0):,.2f} USDT  (손절가에서 청산 시)",
         f"WORST CASE        {fnum(sz.get('margin'), 0):,.2f} USDT  (손절이 갭으로 무시돼 격리 청산될 때 = 증거금 전액)",
         f"STATUS / TIME     {sig.get('status')} · 감지 {fmt_kst(sig.get('detected_at'))} · 최대보유 {int(sig.get('max_hold_min') or 0) / 60:.1f}h",
         '── 바이낸스 입력 (USDⓈ-M BTCUSDT 무기한) ──',
         f"  ① 마진모드 Isolated(격리)   ② 레버리지 {int(sz.get('lev') or 0)}x",
         f"  ③ {'매수/롱(Buy/Long)' if int(sig['side']) > 0 else '매도/숏(Sell/Short)'} · 시장가 · 수량 {fnum(sz.get('qty'), 0)} BTC",
         f"  ④ TP/SL 체크 → 익절 {fnum(sig.get('tp_px')):,.1f} / 손절 {fnum(sig.get('sl_px')):,.1f} (트리거: Last Price)",
         f"  ⑤ 최대보유 {int(sig.get('max_hold_min') or 0) / 60:.1f}h 가 지나도 안 닿으면 시장가 정리 (EXIT 알림이 옵니다)"]
    L.append(f"EVIDENCE          {sig.get('evidence_level') or '-'}")
    if str(sig.get('evidence_level') or '').startswith('E3'):
        L.append(f'※ 미검증 신호: 이 TF 는 아직 실데이터 워크포워드(E4)를 통과하지 않아 위험을 {UNVERIFIED_RISK_MULT:.0%} 로 줄였습니다.')
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
    check('TP 체결 규칙 (maker=관통 필요 / taker=터치 체결)', code[0] == (0 if TP_TYPE == 'maker' else 1))
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
                    ('데이터 구축/복구', self.build_data, None), ('상세', self.detail, None),
                    ('전략 탐색(Lab)', self.lab, '#00695c')]
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
                elif done == 'lab':
                    self.text_window('STRATEGY LAB', out)
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
            if not NUMBA_OK:
                HEALTH.set('dep:numba', 'WARN', 'numba 없음 — DTW 가 느립니다 (pip install numba 권장)')
            if not PARQUET_OK:
                HEALTH.set('dep:pyarrow', 'WARN', 'pyarrow 없음 — 캐시를 pickle 로 저장합니다 (pip install pyarrow 권장)')
            if not MPL_available():
                HEALTH.set('dep:matplotlib', 'WARN', 'matplotlib 없음 — [패턴 차트] 사용 불가')
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
            def work():
                res = walk_forward(base, tf, start, do_null=use_null, status=self.status)
                cert = self.engine.record_walkforward(tf, res, use_null, surrogate=False,
                                                      data_note='GUI · 로컬 캐시 1분봉')
                res['report'] += f"\n\n[EVIDENCE] {tf}: {cert['level']} (model {MODEL_ID}) — 원장에 기록됨"
                return res
            self.run_bg(work, done='wf', busy=True)

        def lab(self):
            base = self.engine.store.base
            if base is None:
                messagebox.showerror('오류', '데이터가 없습니다.')
                return
            with_sur = messagebox.askyesno('전략 탐색', '가짜 BTC 대조군도 같이 돌릴까요? (권장 — "운의 크기"를 함께 봅니다)')

            def work():
                self.status('Lab: 펀딩비 내려받기...', 'blue')
                funding = load_funding_history(self.engine.store.http)
                journal = ResearchJournal.load()
                keys = lab_planned_keys('btc', LAB_TFS, lab_available_families(funding), 'taker')
                kw = dict(status=self.status, funding=funding, holdout_start=journal.anchor,
                          n_trials_declared=journal.n_trials(keys))
                res = lab_run(base, **kw)
                journal.record('lab', keys, title=f'BTC 절차 {res["n_trials"]}개 (GUI)', top=lab_top_lines(res))
                txt = journal.banner() + '\n' + res['report']
                if with_sur:
                    self.status('Lab: 가짜 BTC 대조군...', 'blue')
                    txt += '\n\n★ 가짜 BTC 대조군 — 아래 최고 성적이 "운으로도 나오는 수준"이다 ★\n'
                    txt += lab_run(make_surrogate_1m(base, seed=1), **kw)['report']
                return txt + ('\n\n(가설 하나만 검증·holdout 공개·가짜 BTC p값은 명령행에서: python pattern_edge_v612.py '
                              '--lab --only 4h:flow --surrogate-n 50 / --lab --only 4h:flow --reveal-holdout)')
            if not self.run_bg(work, done='lab', busy=True):
                messagebox.showinfo('안내', '작업 실행 중입니다.')

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


# =============================================================================
# [24] STRATEGY LAB — 여러 전략군을 빠르게 검증하되, 끼워맞추기(data mining)는 구조적으로 막는다
# -----------------------------------------------------------------------------
#  · 전략군: 추세(TSMOM, EMA 교차), 돌파(Donchian, Bollinger, Keltner), 일중(변동성 돌파, 뉴욕개장 레인지,
#    테이커 체결강도), 평균회귀(z-score, RSI(2)), 선물 전용(펀딩비 역추세 — 공개 REST, 키 불필요),
#    패턴 반복(지금과 가장 비슷했던 과거 차트들 뒤에 무슨 일이 있었나 — k-NN 아날로그)
#  · 모든 전략은 진입 시 ATR 손절을 갖는다 → 결과를 R(1회 위험) 단위로 같은 잣대 비교
#  · 진입·청산 = 신호 다음 봉 시가, 손절은 봉 안에서 먼저 처리, 수수료·슬리피지·펀딩 적립금 차감
#  · 비용 시나리오(--cost): taker(기본) · maker_entry(지정가 진입 — 가격이 지정가를 관통해야 체결, 못 받으면
#    다음 봉에 다시) · maker(청산까지 지정가 — 청산 체결을 가정한 낙관 상한). 손절은 언제나 시장가.
#  · 롤링 워크포워드 최적화(WFO): 과거 train 구간에서 고른 파라미터를 '보지 않은' 다음 test 구간에만 적용
#    → 보고되는 성과는 '파라미터 고르는 절차'의 표본외 성과다. 고를 게 없으면 그 구간은 쉰다.
#  · 마지막 holdout 구간은 기본적으로 '봉인'. 공개(--reveal-holdout)하면 원장에 기록된다 (한 번 쓰면 끝).
#    탐색 결과를 보고 고른 가설은 --only 4h:flow 처럼 '하나만' 선언해서 공개한다 (표본외 DSR 은 탐색 전체 절차 수로 보정).
#  · DSR 은 시험한 절차 수(전략군 × TF)로 보정한다. 가짜 BTC(--surrogate, --surrogate-n)로 '운의 크기'를 함께 본다.
#  · 선언한 가설은 다른 코인에 그대로 적용해 재현되는지 본다 (--symbols, 같은 격자·규칙·비용, BTC holdout 날짜 봉인).
# =============================================================================
LAB_TFS = ('5m', '15m', '1h', '4h')
LAB_RISK = 0.01                 # 비교용 고정 위험 (거래당 계좌 1%)
LAB_TRAIN_YEARS = 2.0
LAB_TEST_MONTHS = 3
LAB_HOLDOUT_MONTHS = 9
LAB_MIN_TRAIN_TRADES = 15
LAB_GRIDS = {
    # 추세·돌파
    'tsmom':    [dict(L=L, k=k) for L in (12, 24, 48, 96, 168, 336, 720) for k in (2.0, 4.0)],
    'ema':      [dict(f=f, s=s, k=k) for f, s in ((5, 35), (10, 50), (12, 26), (20, 100), (50, 200)) for k in (2.0, 4.0)],
    'donchian': [dict(N=N, k=k) for N in (20, 55, 100, 200) for k in (2.0, 4.0)],
    'bollinger': [dict(N=N, z=z, k=k) for N in (20, 50, 100) for z in (2.0, 3.0) for k in (2.0, 4.0)],
    'keltner':  [dict(N=N, m=mm, k=k) for N in (20, 50) for mm in (1.5, 2.5) for k in (2.0, 4.0)],
    # 단타(일중)
    'volbreak': [dict(kr=kr, k=k) for kr in (0.3, 0.5, 0.8) for k in (2.0, 4.0)],
    'session':  [dict(L=L, x=x, k=k) for L in (30, 60) for x in (17, 20) for k in (2.0, 4.0)],
    'flow':     [dict(N=N, th=th, k=k) for N in (12, 48) for th in (0.04, 0.08) for k in (2.0, 4.0)],
    # 평균회귀
    'meanrev':  [dict(N=N, z=z, k=k) for N in (20, 50, 100) for z in (2.0, 2.5, 3.0) for k in (1.5, 3.0)],
    'rsi2':     [dict(th=th, k=k) for th in (5, 10, 20) for k in (2.0, 4.0)],
    # 선물 전용
    'funding':  [dict(q=q, H=H, k=k) for q in (0.90, 0.95) for H in (6, 24) for k in (2.0, 4.0)],
    # 역사는 반복된다: 지금과 가장 비슷했던 과거 차트들 뒤에 무슨 일이 있었나 (k-NN 아날로그)
    'analog':   [dict(K=K, H=H, th=th, k=k) for K in (24, 48) for H in (6, 12) for th in (1.5, 3.0) for k in (2.0, 4.0)],
    # 시간대 쏠림 (2026-10-04 탐색): 하루 중 정해진 시각에 들어가 H시간 뒤 청산 — 가격 조건 없음, 하루 한 번
    'tod':      [dict(h=h, H=H, d=d, k=3.0) for h in (0, 4, 8, 12, 16, 20) for H in (4, 8) for d in (1, -1)],
    # 추세 합의 (2026-10-03 사전등록 P1-H3): 고전 추세 지표 4개가 모두 같은 방향일 때만, 격자 없음 (시험 1회)
    'consensus': [dict(k=3.0)],
    # 코인 묶음 전용: 코인끼리 최근 수익률 순위 (Liu·Tsyvinski·Wu 2022 의 암호화폐 모멘텀 요인), d=−1 이면 반전
    'xsmom':    [dict(L=L, d=d, k=k) for L in (6, 42, 168) for d in (1, -1) for k in (2.0, 4.0)],
}
LAB_FAMILY_KO = {'tsmom': '시계열 모멘텀', 'ema': 'EMA 교차', 'donchian': 'Donchian 돌파',
                 'bollinger': 'Bollinger 돌파', 'keltner': 'Keltner+거래량 돌파',
                 'volbreak': '변동성 돌파(일중)', 'session': '뉴욕개장 레인지 돌파', 'flow': '테이커 체결강도',
                 'meanrev': 'z-score 평균회귀', 'rsi2': 'RSI(2) 단기반전', 'funding': '펀딩비 역추세',
                 'analog': '패턴 반복(유사차트)', 'xsmom': '코인간 상대강도', 'consensus': '추세 합의(4지표)',
                 'tod': '시간대 쏠림(UTC)'}
LAB_FAMILY_TFS = {'session': ('5m', '15m'), 'volbreak': ('5m', '15m', '1h'),   # 일중 구조가 의미 있는 TF 만
                  'funding': ('1h', '4h'),                                       # 8시간 정산 → 짧은 TF 는 같은 값 반복
                  'analog': ('1h', '4h'),                                        # 과거 전체와 비교 (n² 계산) → 1h 이상
                  'xsmom': ('1h', '4h'),
                  'consensus': ('4h',),                                          # 사전등록한 4h 만 (시험 수를 늘리지 않는다)
                  'tod': ('1h',)}                                                # 시각 단위 → 1h
LAB_MAX_HOLD = {'rsi2': 10}
LAB_UNIVERSE_TFS = ('1h', '4h')
LAB_UNIVERSE_ONLY = {'xsmom'}                    # 코인 묶음에서만 의미 있는 전략군
LAB_UNIVERSE_SKIP = {('1h', 'analog')}           # 9개 코인 × 1h 아날로그는 계산이 길고, BTC 단독에서 근거가 없었다 (24건, 0R)
LAB_UNIVERSE_MIN_TRAIN = 30                      # 묶음 train 구간 최소 거래 (코인 합산)
LAB_ALT_EXTRA_SLIP = 0.0001                      # 알트는 호가가 얇다 → 시장가 체결마다 슬리피지 +0.01%
LAB_XS_Q = 0.25                                  # 상대강도 상위·하위 25% (9개 코인이면 2개씩)
LAB_ANALOG_KNN = 30             # 서로 다른 과거 사건 30곳
LAB_ANALOG_PAA = 8              # K봉 모양을 8구간 평균으로 요약 (z-정규화 → 가격 수준·변동폭과 무관한 '모양')
LAB_FUNDING_WINDOW = 270        # 펀딩 정산 270회 ≈ 90일 롤링 백분위
LAB_FUNDING_MAX_AGE_H = 16      # 정산 1회 누락까지만 허용, 더 비면 신호 없음
LAB_COST_MODES = {              # (설명, 진입 비용, 신호·시간 청산 비용, 지정가 관통폭: <0 이면 시장가 진입)
    'taker':       ('시장가 진입·시장가 청산', TAKER_FEE + SLIPPAGE_T, TAKER_FEE + SLIPPAGE_T, -1.0),
    'maker_entry': ('지정가 진입(관통해야 체결, 못 받으면 다음 봉 재시도)·시장가 청산',
                    MAKER_FEE, TAKER_FEE + SLIPPAGE_T, MAKER_TP_THROUGH),
    'maker':       ('지정가 진입·지정가 청산 (청산 체결을 가정 = 낙관 상한)', MAKER_FEE, MAKER_FEE, MAKER_TP_THROUGH),
}
FUNDING_EPOCH_MS = 1567296000000   # 2019-09-01 UTC (BTCUSDT 무기한 상장 전) — 처음부터 받는다
LAB_DEFAULT_FEES = (TAKER_FEE, MAKER_FEE, SLIPPAGE_T)


def lab_set_fees(taker=None, maker=None):
    """실제 계정 수수료(VIP·BNB 할인·USDC 계약 프로모션 등)로 Lab 을 돌릴 때: 전역 수수료와 비용 시나리오 표를 다시 만든다."""
    global TAKER_FEE, MAKER_FEE
    if taker is not None:
        TAKER_FEE = float(taker)
    if maker is not None:
        MAKER_FEE = float(maker)
    LAB_COST_MODES['taker'] = (LAB_COST_MODES['taker'][0], TAKER_FEE + SLIPPAGE_T, TAKER_FEE + SLIPPAGE_T, -1.0)
    LAB_COST_MODES['maker_entry'] = (LAB_COST_MODES['maker_entry'][0], MAKER_FEE, TAKER_FEE + SLIPPAGE_T, MAKER_TP_THROUGH)
    LAB_COST_MODES['maker'] = (LAB_COST_MODES['maker'][0], MAKER_FEE, MAKER_FEE, MAKER_TP_THROUGH)


def lab_fee_tag():
    """기본 수수료가 아니면 일지 키에 붙일 꼬리표 (수수료를 바꾼 실행도 별개의 시험으로 센다)."""
    if (TAKER_FEE, MAKER_FEE, SLIPPAGE_T) == LAB_DEFAULT_FEES:
        return ''
    return f'|fee{TAKER_FEE * 1e4:g}/{MAKER_FEE * 1e4:g}/{SLIPPAGE_T * 1e4:g}bp'


@njit(cache=False)
def lab_state(enter_long, enter_short, exit_long, exit_short):
    """진입/청산 조건 → 매 봉 목표 포지션(+1/0/−1). 상태 유지형."""
    n = len(enter_long)
    out = np.zeros(n, dtype=np.int64)
    pos = 0
    for i in range(n):
        if pos == 1 and exit_long[i]:
            pos = 0
        elif pos == -1 and exit_short[i]:
            pos = 0
        if enter_long[i]:
            pos = 1
        elif enter_short[i]:
            pos = -1
        out[i] = pos
    return out


@njit(cache=False)
def lab_sim_x(o, h, l, c, atr, target, stop_k, max_hold, c_in, c_out, c_stop, fund_per_bar, limit_through,
              fixed_stop, tp_r):
    """
    목표 포지션 → 거래 목록. target[i-1] 을 봉 i 시가에 실행, 진입 시 손절 = 진입가 ∓ k·ATR
    (fixed_stop > 0 이면 진입가 ∓ fixed_stop × 진입가, 예: 0.01 = 가격 1% 고정 손절).
    tp_r > 0 이면 익절 = 진입가 ± tp_r × 손절폭 (바이낸스 TP 트리거 → 시장가 비용 c_out). 같은 봉에서 손절과 익절이
    모두 닿으면 손절로 본다 (보수). 익절 후에도 같은 신호로 바로 재진입하지 않는다.
    손절 후 같은 방향 재진입은 신호가 한 번 바뀐 뒤에만 (같은 추세에 연속 손절 방지).
    비용 = 진입 c_in + (신호·시간 청산 c_out | 손절 c_stop).
    limit_through ≥ 0 이면 진입은 봉 시가 지정가: 그 봉에서 가격이 지정가를 limit_through 이상 관통해야 체결
    (대기열 보수), 못 받으면 신호가 살아 있는 동안 다음 봉 시가로 재시도 → 바로 유리하게 달아나는 거래를
    놓치는 '역선택'이 자연히 반영된다.
    반환 (진입봉, 청산봉, 방향, 순 R)
    """
    n = len(c)
    ei = np.empty(n, dtype=np.int64)
    xi = np.empty(n, dtype=np.int64)
    sd = np.empty(n, dtype=np.int64)
    rr = np.empty(n, dtype=np.float64)
    m = 0
    pos = 0
    entry = 0.0
    dist = 0.0
    stop = 0.0
    tpx = 0.0
    t_in = 0
    blocked = 0
    for i in range(1, n):
        want = target[i - 1]
        if blocked != 0 and want != blocked:
            blocked = 0
        if pos != 0 and want != pos:
            g = pos * (o[i] / entry - 1.0)
            ei[m] = t_in; xi[m] = i; sd[m] = pos
            rr[m] = (g - c_in - c_out - fund_per_bar * (i - t_in)) / (dist / entry)
            m += 1
            pos = 0
        if pos == 0 and want != 0 and want != blocked and atr[i - 1] > 1e-5:
            fill = True
            if limit_through >= 0.0:
                if want > 0:
                    fill = l[i] <= o[i] * (1.0 - limit_through)
                else:
                    fill = h[i] >= o[i] * (1.0 + limit_through)
            if fill:
                pos = want
                entry = o[i]
                dist = (fixed_stop if fixed_stop > 0.0 else stop_k * atr[i - 1]) * entry
                stop = entry - pos * dist
                tpx = entry + pos * tp_r * dist
                t_in = i
        if pos != 0:
            hit = (pos > 0 and l[i] <= stop) or (pos < 0 and h[i] >= stop)
            if hit:
                px = stop
                if (pos > 0 and o[i] < stop) or (pos < 0 and o[i] > stop):
                    px = o[i]
                g = pos * (px / entry - 1.0)
                ei[m] = t_in; xi[m] = i; sd[m] = pos
                rr[m] = (g - c_in - c_stop - fund_per_bar * (i - t_in + 1)) / (dist / entry)
                m += 1
                blocked = pos
                pos = 0
            elif tp_r > 0.0 and ((pos > 0 and h[i] >= tpx) or (pos < 0 and l[i] <= tpx)):
                g = pos * (tpx / entry - 1.0)
                ei[m] = t_in; xi[m] = i; sd[m] = pos
                rr[m] = (g - c_in - c_out - fund_per_bar * (i - t_in + 1)) / (dist / entry)
                m += 1
                blocked = pos
                pos = 0
            elif max_hold > 0 and i - t_in + 1 >= max_hold:
                g = pos * (c[i] / entry - 1.0)
                ei[m] = t_in; xi[m] = i; sd[m] = pos
                rr[m] = (g - c_in - c_out - fund_per_bar * (i - t_in + 1)) / (dist / entry)
                m += 1
                blocked = pos
                pos = 0
    return ei[:m], xi[:m], sd[:m], rr[:m]


def lab_sim(o, h, l, c, atr, target, stop_k, max_hold, cost_frac, fund_per_bar):
    """시장가 진입·청산, 왕복 비용 cost_frac (lab_sim_x 의 단순형)."""
    half = 0.5 * float(cost_frac)
    return lab_sim_x(o, h, l, c, atr, target, float(stop_k), int(max_hold), half, half, half,
                     float(fund_per_bar), -1.0, 0.0, 0.0)


def _funding_from_rows(rows):
    t = np.array([int(r['fundingTime']) for r in rows], dtype=np.int64)
    v = np.array([float(r['fundingRate']) for r in rows], dtype=np.float64)
    return pd.Series(v, index=pd.DatetimeIndex(pd.to_datetime(t, unit='ms')), name='rate')


def load_funding_history(http=None, path=None, refresh=True, log=None, symbol=SYMBOL):
    """
    symbol(기본 BTCUSDT) 8시간 정산 펀딩비 (공개 REST /fapi/v1/fundingRate — 키·서명 없음) → pd.Series(rate, index=정산시각 UTC).
    로컬 CSV 캐시에 이어 받는다. 갱신 실패 시 캐시만 쓰고, 캐시도 없으면 None (펀딩비 전략군은 생략된다).
    """
    log = log or (lambda msg, color='black': LOG.info(msg))
    path = path or (Paths.funding() if symbol == SYMBOL else Paths.p(f'{symbol}_funding_8h.csv'))
    s = None
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            s = pd.Series(df['rate'].values.astype(np.float64),
                          index=pd.DatetimeIndex(pd.to_datetime(df['time_ms'].values.astype(np.int64), unit='ms')),
                          name='rate')
        except Exception as e:
            HEALTH.set('funding', 'WARN', f'펀딩비 캐시 손상 — 처음부터 다시 받습니다: {e}')
            s = None
    if refresh:
        http = http or PublicHttp()
        cursor = int(s.index[-1].value // 10 ** 6) + 1 if s is not None and len(s) else FUNDING_EPOCH_MS
        got = []
        try:
            for _ in range(100):
                rows = http.get_json(f'{FAPI_BASE}/fapi/v1/fundingRate?symbol={symbol}&startTime={cursor}&limit=1000',
                                     timeout=20)
                if not rows:
                    break
                got.extend(rows)
                newest = int(rows[-1]['fundingTime'])
                if len(rows) < 1000 or newest < cursor:
                    break
                cursor = newest + 1
                time.sleep(0.3)
            HEALTH.clear('funding')
        except Exception as e:
            HEALTH.set('funding', 'WARN', f'펀딩비 갱신 실패 ({type(e).__name__}: {e}) — '
                                          f'캐시 {0 if s is None else len(s)}건으로 진행')
        if got:
            new = _funding_from_rows(got)
            s = new if s is None else pd.concat([s, new])
            s = s[~s.index.duplicated(keep='last')].sort_index()
            try:
                tmp = path + '.tmp'
                ms = s.index.values.astype('datetime64[ms]').astype(np.int64)
                pd.DataFrame({'time_ms': ms, 'rate': s.values}).to_csv(tmp, index=False)
                os.replace(tmp, path)
            except Exception as e:
                HEALTH.set('funding', 'WARN', f'펀딩비 캐시 저장 실패: {e}')
            log(f'{symbol} 펀딩비 {len(got)}건 수신 → 총 {len(s)}건 ({s.index[0]:%Y-%m-%d} ~ {s.index[-1]:%Y-%m-%d %H:%M} UTC)',
                'blue')
    if s is None or len(s) == 0:
        return None
    return s


def _lab_funding_pct(idx, bar_minutes, funding, window=LAB_FUNDING_WINDOW):
    """
    봉마다 '그 봉 마감 전에 이미 정산된' 마지막 펀딩비의 롤링 백분위 (인과적 — 봉 마감과 같은 시각 정산은
    다음 봉부터 쓴다 = 보수). 정산이 LAB_FUNDING_MAX_AGE_H 넘게 비어 있으면 NaN (신호 없음).
    """
    if funding is None or len(funding) < window // 2:
        return None
    f = funding.sort_index()
    pct = f.rolling(window, min_periods=window // 2).rank(pct=True).values
    t = f.index.values.astype('datetime64[ns]')
    close = (idx + pd.Timedelta(minutes=bar_minutes)).values.astype('datetime64[ns]')
    j = np.searchsorted(t, close, side='left') - 1
    jj = np.clip(j, 0, len(t) - 1)
    ok = (j >= 0) & ((close - t[jj]) <= np.timedelta64(LAB_FUNDING_MAX_AGE_H, 'h'))
    out = np.full(len(idx), np.nan)
    out[ok] = pct[jj[ok]]
    return out


LAB_ALT_SYMBOLS = ('ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'SOLUSDT', 'LTCUSDT', 'LINKUSDT')
LAB_MAJOR_SYMBOLS = ('ETHUSDT',)                 # L16: BTC 1순위·ETH 2순위 → 기본값은 BTC+ETH, 알트 8개는 'alts' 로 명시할 때만
KLINE_COLS = ['open', 'high', 'low', 'close', 'volume', 'taker_buy_base', 'trades']


def fetch_klines_tf(http, symbol, tf, path=None, log=None):
    """
    공개 REST /fapi/v1/klines (키·서명 없음) 로 symbol 의 tf 봉 전체 이력 → DataFrame(STORE_COLS). 로컬 CSV 캐시에
    이어 받는다. 진행 중인 마지막 봉은 저장하지 않는다 (다음에 그 봉부터 다시 받음). 실패하면 캐시만, 없으면 None.
    """
    log = log or (lambda msg, color='black': LOG.info(msg))
    path = path or Paths.p(f'{symbol}_{tf}_klines.csv')
    step = INTERVALS[tf] * 60_000
    df = None
    if os.path.exists(path):
        try:
            raw = pd.read_csv(path)
            df = pd.DataFrame({k: raw[k].values.astype(np.float64) for k in KLINE_COLS},
                              index=pd.DatetimeIndex(pd.to_datetime(raw['time_ms'].values.astype(np.int64), unit='ms')))
        except Exception as e:
            HEALTH.set(f'klines:{symbol}', 'WARN', f'{symbol} {tf} 캐시 손상 — 다시 받습니다: {e}')
            df = None
    cursor = int(df.index[-1].value // 10 ** 6) + step if df is not None and len(df) else FUNDING_EPOCH_MS
    got = []
    try:
        for _ in range(500):
            data = http.get_json(f'{FAPI_BASE}/fapi/v1/klines?symbol={symbol}&interval={tf}&startTime={cursor}'
                                 f'&limit=1000', timeout=30)
            if not data:
                break
            got.extend(data)
            newest = int(data[-1][0])
            if len(data) < 1000 or newest < cursor:
                break
            cursor = newest + step
            time.sleep(0.35)
        HEALTH.clear(f'klines:{symbol}')
    except Exception as e:
        HEALTH.set(f'klines:{symbol}', 'WARN', f'{symbol} {tf} 봉 갱신 실패 ({type(e).__name__}: {e})')
    if got:
        arr = np.array(got, dtype=object)
        new = pd.DataFrame({k: arr[:, i].astype(np.float64) for k, i in
                            zip(KLINE_COLS, (1, 2, 3, 4, 5, 9, 8))},
                           index=pd.DatetimeIndex(pd.to_datetime(arr[:, 0].astype(np.int64), unit='ms')))
        df = new if df is None else pd.concat([df, new])
        df = df[~df.index.duplicated(keep='last')].sort_index()
        df = df[df.index + pd.Timedelta(minutes=INTERVALS[tf]) <= pd.Timestamp(utcnow())]   # 진행 중인 봉 제외
        try:
            tmp = path + '.tmp'
            out = df.copy()
            out.insert(0, 'time_ms', df.index.values.astype('datetime64[ms]').astype(np.int64))
            out.to_csv(tmp, index=False)
            os.replace(tmp, path)
        except Exception as e:
            HEALTH.set(f'klines:{symbol}', 'WARN', f'{symbol} {tf} 캐시 저장 실패: {e}')
        log(f'{symbol} {tf} 봉 {len(got)}개 수신 → 총 {len(df)}개 ({df.index[0]:%Y-%m-%d} ~ {df.index[-1]:%Y-%m-%d})', 'blue')
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    df['era'] = ERA_FUT
    return df[STORE_COLS]


def _lab_analog_features(c, K, D=LAB_ANALOG_PAA):
    """각 봉 t 에서 끝나는 K봉 로그가격 경로 → z-정규화 → D 구간 평균(PAA). 앞쪽 K−1 봉과 평평한 구간은 NaN."""
    lp = np.log(np.maximum(np.asarray(c, dtype=np.float64), 1e-12))
    n = len(lp)
    out = np.full((n, D), np.nan)
    if n < K or K % D:
        return out
    w = np.lib.stride_tricks.sliding_window_view(lp, K)
    mu = w.mean(axis=1, keepdims=True)
    sd = w.std(axis=1, keepdims=True)
    z = (w - mu) / np.where(sd > 1e-12, sd, np.nan)
    out[K - 1:] = z.reshape(len(w), D, K // D).mean(axis=2)
    return out


@njit(cache=False, parallel=True)
def lab_analog_scores(feat, fwds, K, knn, stride, sep):
    """
    '역사는 반복된다'를 그대로 계산: 봉 t 의 K봉 모양과 가장 가까운 과거 모양 knn 곳을 찾고, 그 뒤 H봉 움직임의
    t-통계(평균 / 표준오차)를 낸다. feat (n, D) 모양, fwds (m, n) H 별 '봉 j 이후 H봉 수익 / ATR_j'.
    후보 j 는 t−K 이하만 → 모양이 겹치지 않고, H ≤ K 이므로 그 결과도 t 시점에 이미 확정된 과거다 (미래 누설 없음).
    서로 sep 봉 안의 후보는 같은 사건으로 보고 더 가까운 하나만 남긴다. 반환 (m, n), 이웃이 모자라면 0.
    """
    n, D = feat.shape
    m = fwds.shape[0]
    out = np.zeros((m, n))
    for t in prange(n):                     # 봉마다 독립 → CPU 코어 수만큼 병렬
        if np.isnan(feat[t, 0]):
            continue
        bd = np.empty(knn)
        bj = np.empty(knn, dtype=np.int64)
        cnt = 0
        wi = 0
        wd = np.inf
        for j in range(K - 1, t - K + 1, stride):
            if np.isnan(feat[j, 0]):
                continue
            d = 0.0
            for q in range(D):
                x = feat[t, q] - feat[j, q]
                d += x * x
            if cnt == knn and d >= wd:
                continue
            near = -1
            for a in range(cnt):
                if j - bj[a] < sep:
                    near = a
                    break
            if near >= 0:
                if d >= bd[near]:
                    continue
                bd[near] = d
                bj[near] = j
            elif cnt < knn:
                bd[cnt] = d
                bj[cnt] = j
                cnt += 1
            else:
                bd[wi] = d
                bj[wi] = j
            if cnt == knn:
                wi = 0
                wd = bd[0]
                for a in range(1, cnt):
                    if bd[a] > wd:
                        wd = bd[a]
                        wi = a
        if cnt < knn:
            continue
        for hh in range(m):
            s1 = 0.0
            s2 = 0.0
            k = 0
            for a in range(cnt):
                v = fwds[hh, bj[a]]
                if not np.isnan(v):
                    s1 += v
                    s2 += v * v
                    k += 1
            if k >= knn // 2:
                mu = s1 / k
                var = (s2 - k * mu * mu) / max(k - 1, 1)
                if var > 1e-12:
                    out[hh, t] = mu / np.sqrt(var / k)
    return out


def _lab_indicators(df):
    c = df['close'].astype(np.float64)
    h = df['high'].astype(np.float64)
    l = df['low'].astype(np.float64)
    pc = c.shift(1).fillna(c)
    tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    atr = (tr / c).ewm(alpha=1 / 14.0, adjust=False).mean()
    return dict(c=c, h=h, l=l, o=df['open'].astype(np.float64), atr=atr,
                v=df['volume'].astype(np.float64), tb=df['taker_buy_base'].astype(np.float64), idx=df.index)


def _lab_day_frame(ind):
    idx = ind['idx']
    day = pd.Series(idx.floor('D'), index=idx)
    last_bar = (day.shift(-1) != day).values
    minute = (idx.hour * 60 + idx.minute).values
    return day, last_bar, minute


def _lab_target(fam, p, ind):
    c, h, l = ind['c'], ind['h'], ind['l']
    zeros = np.zeros(len(c), dtype=np.bool_)
    if fam == 'tsmom':
        return np.sign(np.log(c / c.shift(p['L']))).fillna(0).values.astype(np.int64)
    if fam == 'ema':
        d = c.ewm(span=p['f'], adjust=False).mean() - c.ewm(span=p['s'], adjust=False).mean()
        t = np.sign(d).values.astype(np.int64)
        t[:p['s']] = 0
        return t
    if fam == 'donchian':
        N = p['N']
        up, lo = h.rolling(N).max().shift(1), l.rolling(N).min().shift(1)
        xup, xlo = h.rolling(max(2, N // 2)).max().shift(1), l.rolling(max(2, N // 2)).min().shift(1)
        el, es = (c > up).values, (c < lo).values
        xl, xs = (c < xlo).values, (c > xup).values
        return lab_state(el, es, xl, xs)
    if fam == 'keltner':
        N = p['N']
        mid = c.ewm(span=N, adjust=False).mean()
        band = p['m'] * ind['atr'] * c
        volok = (ind['v'] > 1.5 * ind['v'].rolling(N).mean()).values
        return lab_state(((c > mid + band).values & volok), ((c < mid - band).values & volok),
                         (c < mid).values, (c > mid).values)
    if fam == 'volbreak':
        # Larry Williams 변동성 돌파: 당일 시가 ± k × 전일 레인지, 당일 마지막 봉에 청산
        day, last_bar, _ = _lab_day_frame(ind)
        dopen = ind['o'].groupby(day.values).transform('first')
        dh = h.groupby(day.values).max()
        dl = l.groupby(day.values).min()
        prev_rng = (dh - dl).shift(1)
        rng = pd.Series(day.values, index=c.index).map(prev_rng)
        up, dn = (dopen + p['kr'] * rng).values, (dopen - p['kr'] * rng).values
        cv = c.values
        el = (cv > up) & ~last_bar
        es = (cv < dn) & ~last_bar
        return lab_state(el, es, last_bar, last_bar)
    if fam == 'session':
        # 뉴욕 개장(13:30 UTC) 후 L 분 레인지 돌파, x 시(UTC) 청산
        day, _, minute = _lab_day_frame(ind)
        start = 13 * 60 + 30
        inwin = (minute >= start) & (minute < start + p['L'])
        hh = h.where(inwin).groupby(day.values).transform('max')
        ll = l.where(inwin).groupby(day.values).transform('min')
        live = (minute >= start + p['L']) & (minute < p['x'] * 60)
        cv = c.values
        el = live & (cv > np.nan_to_num(hh.values, nan=np.inf))
        es = live & (cv < np.nan_to_num(ll.values, nan=-np.inf))
        out_t = minute >= p['x'] * 60
        return lab_state(el, es, out_t, out_t)
    if fam == 'flow':
        # 테이커 매수−매도 체결 비율 (주문흐름 대용) + 추세 필터
        N = p['N']
        imb = ((2 * ind['tb'] - ind['v']).rolling(N).sum() / ind['v'].rolling(N).sum()).fillna(0).values
        trend = (c > c.ewm(span=100, adjust=False).mean()).values
        return lab_state((imb > p['th']) & trend, (imb < -p['th']) & ~trend, imb < 0, imb > 0)
    if fam == 'funding':
        # 펀딩비가 최근 90일 중 극단(상위/하위 1−q) = 한쪽으로 쏠린 레버리지 → 반대 방향.
        # 백분위가 50% 로 돌아오면, 또는 H 봉·손절로 청산
        fp = ind.get('fpct')
        if fp is None:
            return zeros.astype(np.int64)
        valid = ~np.isnan(fp)
        f0 = np.where(valid, fp, 0.5)
        return lab_state(valid & (f0 <= 1 - p['q']), valid & (f0 >= p['q']), f0 >= 0.5, f0 <= 0.5)
    if fam == 'tod':
        # 봉 i 의 목표는 봉 i+1 시가에 실행된다 → 다음 봉의 시각이 [h, h+H) 안이면 그 방향으로 들고 있는다.
        # 다음 봉의 시각은 미리 알 수 있는 달력 정보라 미래 데이터가 아니다.
        hrs = ind['idx'].hour.values
        inwin = ((hrs - p['h']) % 24) < p['H']
        t = np.zeros(len(hrs), dtype=np.int64)
        t[:-1] = np.where(inwin[1:], int(p['d']), 0)
        return t
    if fam == 'consensus':
        # EMA20/100 교차 · Donchian55 중간선 · 42봉 모멘텀 · SMA200 위치 — 넷 다 같은 방향이면 진입, 합계가 0 을 넘어가면 청산
        dc = (h.rolling(55).max().shift(1) + l.rolling(55).min().shift(1)) / 2
        votes = (np.sign(c.ewm(span=20, adjust=False).mean() - c.ewm(span=100, adjust=False).mean()).fillna(0)
                 + np.sign(c - dc).fillna(0) + np.sign(np.log(c / c.shift(42))).fillna(0)
                 + np.sign(c - c.rolling(200).mean()).fillna(0)).values
        return lab_state(votes >= 4, votes <= -4, votes <= 0, votes >= 0)
    if fam == 'xsmom':
        # 같은 시각 코인끼리 최근 L봉 수익률 순위 → 상위 25% 롱·하위 25% 숏 (d=+1 모멘텀) 또는 반대 (d=−1 반전),
        # 순위가 중간(50%)을 넘어가면 청산
        xr = (ind.get('xsrank') or {}).get(p['L'])
        if xr is None:
            return zeros.astype(np.int64)
        valid = ~np.isnan(xr)
        x0 = np.where(valid, xr, 0.5)
        top, bot = valid & (x0 >= 1 - LAB_XS_Q), valid & (x0 <= LAB_XS_Q)
        if p['d'] > 0:
            return lab_state(top, bot, x0 < 0.5, x0 > 0.5)
        return lab_state(bot, top, x0 > 0.5, x0 < 0.5)
    if fam == 'analog':
        # 지금과 모양이 가장 비슷했던 과거 30곳(서로 다른 사건)에서 그 뒤 H봉이 어떻게 움직였는지 →
        # t-통계가 th 를 넘으면 그 방향으로 진입, 부호가 바뀌거나 H봉이 지나면 청산. 이웃 탐색은 K 별로 한 번만.
        cache = ind.setdefault('_analog', {})
        if (p['K'], p['H']) not in cache:
            K = int(p['K'])
            Hs = sorted({q['H'] for q in LAB_GRIDS['analog'] if q['K'] == K})
            cv, av = c.values, np.maximum(ind['atr'].values, 1e-6)
            fw = np.full((len(Hs), len(cv)), np.nan)
            for a, H in enumerate(Hs):
                fw[a, :len(cv) - H] = (cv[H:] / cv[:-H] - 1.0) / av[:-H]
            sc = lab_analog_scores(_lab_analog_features(cv, K), fw, K, LAB_ANALOG_KNN, max(1, K // 8), max(1, K // 4))
            for a, H in enumerate(Hs):
                cache[(K, H)] = sc[a]
        sc = cache[(p['K'], p['H'])]
        return lab_state(sc > p['th'], sc < -p['th'], sc < 0, sc > 0)
    if fam == 'rsi2':
        # Connors RSI(2): 장기 추세 방향의 단기 과매도/과매수 되돌림
        d = c.diff()
        up = d.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
        dn = (-d.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
        rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50).values
        s200, s5 = c.rolling(200).mean().values, c.rolling(5).mean().values
        cv = c.values
        return lab_state((rsi < p['th']) & (cv > s200), (rsi > 100 - p['th']) & (cv < s200), cv > s5, cv < s5)
    N = p['N']
    z = ((c - c.rolling(N).mean()) / c.rolling(N).std()).values
    z = np.nan_to_num(z)
    if fam == 'bollinger':
        return lab_state(z > p['z'], z < -p['z'], z < 0, z > 0)
    if fam == 'meanrev':
        return lab_state(z < -p['z'], z > p['z'], z >= 0, z <= 0)
    return zeros.astype(np.int64)


def _lab_metrics(R, years, risk=LAB_RISK, n_trials=1):
    R = np.asarray(R, dtype=np.float64)
    if len(R) == 0:
        return dict(n=0, n_year=0.0, mean_r=float('nan'), ci_lo=float('nan'), ci_hi=float('nan'),
                    win=float('nan'), pf=float('nan'), cagr=0.0, mdd=0.0, dsr=0.0, daily=0.0)
    eq = np.cumprod(1.0 + risk * np.clip(R, -50, 50))
    eq = np.concatenate(([1.0], eq))
    boots = stationary_block_bootstrap(R, n_boot=1500, mean_block=5.0, rng=np.random.default_rng(len(R)))
    lo, hi = (np.quantile(boots, [0.05, 0.95]) if len(R) >= 5 else (float('nan'), float('nan')))
    _, _, dsr = deflated_sharpe(np.diff(np.log(np.maximum(eq, 1e-12))), max(n_trials, 2))
    cagr = max(eq[-1], 1e-12) ** (1 / max(years, 1e-6)) - 1
    return dict(n=int(len(R)), n_year=len(R) / max(years, 1e-6), mean_r=float(R.mean()), ci_lo=float(lo),
                ci_hi=float(hi), win=float(np.mean(R > 0)),
                pf=float(R[R > 0].sum() / max(-R[R <= 0].sum(), 1e-9)), cagr=float(cagr),
                daily=float((1 + cagr) ** (1 / 365) - 1),
                mdd=float((1 - eq / np.maximum.accumulate(eq)).max()), dsr=float(dsr))


LAB_F_MAX = 0.25                 # 거래당 위험 상한 (하루 복리 최적화가 이보다 크게 걸라고 해도 여기서 자른다)


def lab_daily_growth(R, t_exit, d0, d1, haircut=0.0, f_max=LAB_F_MAX):
    """
    평균 하루 복리를 최대로 만드는 거래당 위험 f 와 그때의 하루 복리.
    같은 날 청산된 거래는 합산한다 (여러 코인·전략을 동시에 들고 있으면 그날 위험도 합쳐진다):
        r_d = f × Σ(그날 청산된 거래의 R − haircut),  하루 복리 = exp(평균 log(1 + r_d)) − 1  (거래 없는 날 포함)
    haircut = 평균R − 90% CI 하한 이면 '증거의 하한만큼만' 거는 보수 기준 → 엣지 증거가 없으면 f = 0, 성장 0.
    반환 (f*, 하루 복리)
    """
    R = np.asarray(R, dtype=np.float64)
    if len(R) == 0 or not np.isfinite(haircut):
        return 0.0, 0.0
    d0, d1 = np.datetime64(pd.Timestamp(d0), 'D'), np.datetime64(pd.Timestamp(d1), 'D')
    nd = int((d1 - d0).astype(np.int64)) + 1
    day = (np.asarray(t_exit).astype('datetime64[D]') - d0).astype(np.int64)
    ok = (day >= 0) & (day < nd)
    if nd <= 0 or not ok.any():
        return 0.0, 0.0
    S = np.bincount(day[ok], weights=R[ok] - haircut, minlength=nd)
    fs = np.linspace(0.0, f_max, 501)[1:]
    worst = S.min()
    fs = fs[1.0 + fs * worst > 1e-9]
    if not len(fs):
        return 0.0, 0.0
    g = np.log1p(np.outer(fs, S)).mean(axis=1)
    k = int(np.argmax(g))
    if g[k] <= 0:
        return 0.0, 0.0
    return float(fs[k]), float(math.expm1(g[k]))


LAB_SHARPE_FOR_1PCT = math.sqrt(2 * math.log(1.01)) * math.sqrt(365)          # ≈ 2.70 (켈리 최대 성장 = 일간 샤프²/2)
LAB_SHARPE_FOR_1PCT_HALF = math.sqrt(2 * math.log(1.01) / 0.75) * math.sqrt(365)  # ≈ 3.11 (반켈리는 최대 성장의 3/4)


def lab_daily_sharpe(R, t_exit, d0, d1):
    """하루 단위 손익(그날 청산된 R 합, 거래 없는 날 0)의 연환산 샤프. 레버리지와 무관한 '전략의 질'."""
    R = np.asarray(R, dtype=np.float64)
    if len(R) < 5:
        return float('nan')
    d0, d1 = np.datetime64(pd.Timestamp(d0), 'D'), np.datetime64(pd.Timestamp(d1), 'D')
    nd = int((d1 - d0).astype(np.int64)) + 1
    day = (np.asarray(t_exit).astype('datetime64[D]') - d0).astype(np.int64)
    ok = (day >= 0) & (day < nd)
    if nd <= 1 or not ok.any():
        return float('nan')
    S = np.bincount(day[ok], weights=R[ok], minlength=nd)
    sd = S.std(ddof=1)
    return float(S.mean() / sd * math.sqrt(365)) if sd > 0 else float('nan')


def lab_sharpe_line(rows):
    """하루 1% 목표까지의 거리를 항상 같은 잣대로 보여 준다."""
    best = max((r for r in rows if r['oos']['n'] >= 30 and np.isfinite(r['oos'].get('sharpe', float('nan')))),
               key=lambda r: r['oos']['sharpe'], default=None)
    head = (f'▶ 하루 1% 복리에 필요한 연환산 샤프 ≈ {LAB_SHARPE_FOR_1PCT:.1f} (켈리, 낙폭 매우 큼) · '
            f'{LAB_SHARPE_FOR_1PCT_HALF:.1f} (반켈리)')
    if best is None:
        return head + ' — 이번 실행에 비교할 절차 없음 (거래 30건 이상)'
    sh = best['oos']['sharpe']
    return (head + f' — 이번 최고 {sh:+.2f} ({best["tf"]} {LAB_FAMILY_KO[best["family"]]}, 점추정), 필요한 성장 대비 '
            f'{max(sh, 0) ** 2 / LAB_SHARPE_FOR_1PCT ** 2:.0%}')


def _lab_attach_growth(met, R, t_exit, d0, d1):
    """보수(증거 하한) 기준 f* 와 하루 복리, 같은 f 로 점추정이 맞을 때의 하루 복리, 일간 연환산 샤프."""
    hc = met['mean_r'] - met['ci_lo'] if met['n'] >= 5 and np.isfinite(met['ci_lo']) else float('nan')
    f, g = lab_daily_growth(R, t_exit, d0, d1, haircut=hc)
    gp = lab_daily_growth(R, t_exit, d0, d1, haircut=0.0, f_max=f)[1] if f > 0 else 0.0
    met.update(f_star=f, g_day=g, g_day_point=gp, sharpe=lab_daily_sharpe(R, t_exit, d0, d1))
    return met


def lab_pairs(only=None):
    """'4h:flow,1h:funding' 또는 [('4h','flow')] → 검증된 (TF, 전략군) 목록. None → None."""
    if not only:
        return None
    out = []
    for x in (only.split(',') if isinstance(only, str) else only):
        tf, fam = (x.split(':') if isinstance(x, str) else x)
        tf, fam = tf.strip(), fam.strip()
        if fam not in LAB_GRIDS or tf not in LAB_FAMILY_TFS.get(fam, LAB_TFS):
            ok = ', '.join(f'{t}:{f}' for f in LAB_GRIDS for t in LAB_FAMILY_TFS.get(f, LAB_TFS))
            raise ValueError(f'알 수 없는 조합 {tf}:{fam} — 가능한 값: {ok}')
        if (tf, fam) not in out:
            out.append((tf, fam))
    return out


def lab_available_families(funding=None, universe=False):
    """이 실행에서 돌릴 수 있는 전략군: 펀딩비는 데이터가 있을 때만, 패턴 반복은 numba 가 있을 때만 (없으면 n² 계산이 수십 분),
    코인간 상대강도는 코인 묶음(--universe)에서만."""
    has_funding = funding is not None and len(funding) >= LAB_FUNDING_WINDOW // 2
    return [f for f in LAB_GRIDS if (f != 'funding' or has_funding) and (f != 'analog' or NUMBA_OK)
            and (universe or f not in LAB_UNIVERSE_ONLY)]


def lab_trial_count(tfs=LAB_TFS, families=None):
    """탐색 전체의 절차 수 (전략군 × 적용 TF)."""
    families = list(families or LAB_GRIDS)
    return sum(1 for tf in tfs for fam in families if tf in LAB_FAMILY_TFS.get(fam, LAB_TFS))


LAB_FIXED_TFS = ('5m', '15m', '1h')           # 고정 % 손절 모드의 기본 TF (짧은 시간봉)
LAB_FIXED_TP = (0.0, 2.0, 3.0)                # 익절 없음(신호 청산) · 2R · 3R — train 이 고른다


def lab_fixed_grid(fam, tp_list=LAB_FIXED_TP):
    """고정 % 손절 모드의 파라미터 격자: ATR 배수(k)를 빼고 같은 설정을 하나로 합친 뒤 익절 R 배수를 곱한다."""
    seen, out = set(), []
    for p in LAB_GRIDS[fam]:
        base = {k: v for k, v in p.items() if k != 'k'}
        key = tuple(sorted(base.items()))
        if key in seen:
            continue
        seen.add(key)
        out += [dict(base, k=0.0, tp=float(t)) for t in tp_list]
    return out


def lab_run(base1m, tfs=LAB_TFS, families=None, holdout_months=LAB_HOLDOUT_MONTHS, train_years=LAB_TRAIN_YEARS,
            test_months=LAB_TEST_MONTHS, reveal_holdout=False, status=None, futures_only=True,
            cost_mode='taker', only=None, funding=None, n_trials_declared=None, tf_frames=None,
            holdout_start=None, symbol=SYMBOL, fixed_stop=0.0, tp_list=LAB_FIXED_TP):
    """
    반환 dict(rows=[...], holdout_start, report).
    tf_frames={'4h': df, ...} 이면 1분봉 대신 그 봉을 그대로 쓴다 (다른 코인 재현 검증용 REST 봉).
    holdout_start 를 주면 그 날짜부터 봉인 (알트에서도 BTC 와 같은 날짜를 봉인해야 상관으로 엿보지 않는다).
    only='4h:flow' — 탐색 결과를 보고 고른 가설만 검증. 표본외 DSR 은 n_trials_declared(그 가설을 고른 탐색의
    전체 절차 수)로 보정하고, holdout 은 선언된 가설만 보므로 n_trials=1.
    funding=None 이면 펀딩비 전략군은 생략한다 (절차 수에도 넣지 않는다).
    """
    status = status or (lambda *a, **k: None)
    if cost_mode not in LAB_COST_MODES:
        raise ValueError(f'알 수 없는 비용 시나리오 {cost_mode} — 가능한 값: {", ".join(LAB_COST_MODES)}')
    _, c_in, c_out, limit_through = LAB_COST_MODES[cost_mode]
    c_stop = TAKER_FEE + SLIPPAGE_T
    t_wall = time.time()
    if tf_frames is None:
        base1m = normalize_frame(base1m)
        if futures_only and (base1m['era'].values == ERA_FUT).any():
            base1m = base1m[base1m['era'].values == ERA_FUT]
        snap = Snapshot(base1m, base1m.index[-1].to_pydatetime() + timedelta(minutes=1))

        def get_tf(tf):
            d = snap.tf(tf)
            return d[d['complete'].values > 0.5]
        t_first, t_last = base1m.index[0], base1m.index[-1]
        src = f'선물 {"만" if futures_only else "+스팟"}'
    else:
        frames = {k: normalize_frame(v) for k, v in tf_frames.items() if v is not None and len(v)}
        if not frames:
            raise ValueError(f'{symbol}: 봉 데이터 없음')
        get_tf = frames.get
        t_first = min(v.index[0] for v in frames.values())
        t_last = max(v.index[-1] + pd.Timedelta(minutes=INTERVALS[k] - 1) for k, v in frames.items())
        src = f'REST {"/".join(sorted(frames, key=INTERVALS.get))} 봉'
    has_funding = funding is not None and len(funding) >= LAB_FUNDING_WINDOW // 2
    avail = set(lab_available_families(funding))
    families = [f for f in (families or LAB_GRIDS) if f in avail]
    pairs = lab_pairs(only)
    if pairs:
        if any(f == 'funding' for _, f in pairs) and not has_funding:
            raise ValueError('펀딩비 데이터가 없어 펀딩비 전략군을 검증할 수 없습니다 (네트워크 확인 후 다시)')
        if any(f == 'analog' for _, f in pairs) and not NUMBA_OK:
            raise ValueError('패턴 반복 전략군은 numba 가 필요합니다 (pip install numba)')
        if any(f in LAB_UNIVERSE_ONLY for _, f in pairs):
            raise ValueError('코인간 상대강도는 코인 묶음에서만 검증합니다 (--universe)')
        tfs = tuple(t for t in INTERVALS if any(t == a for a, _ in pairs))
        families = [f for f in LAB_GRIDS if any(f == b for _, b in pairs)]
    hold_start = pd.Timestamp(holdout_start) if holdout_start is not None \
        else t_last - pd.DateOffset(months=int(holdout_months))
    rows, n_sims = [], 0

    def applies(fam, tf):
        return tf in LAB_FAMILY_TFS.get(fam, LAB_TFS) and (pairs is None or (tf, fam) in pairs)
    n_trials = sum(1 for tf in tfs for fam in families if applies(fam, tf))
    n_dsr = max(n_trials, int(n_trials_declared or 0))
    for tf in tfs:
        df = get_tf(tf)
        if df is None or len(df) < 500:
            continue
        ind = _lab_indicators(df)
        o, h, l, c, atr = (ind[k].values for k in ('o', 'h', 'l', 'c', 'atr'))
        idx = df.index
        bar_h = INTERVALS[tf] / 60.0
        if has_funding and applies('funding', tf):
            ind['fpct'] = _lab_funding_pct(idx, INTERVALS[tf], funding)
        fund = FUNDING_PER_8H * bar_h / 8.0
        i_hold = int(idx.searchsorted(hold_start))
        train_n = int(train_years * 365.25 * 24 / bar_h)
        test_n = max(1, int(test_months * 30.44 * 24 / bar_h))
        starts = list(range(train_n, len(df), test_n))
        for fam in families:
            if not applies(fam, tf):
                continue
            grid = lab_fixed_grid(fam, tp_list) if fixed_stop > 0 else LAB_GRIDS[fam]
            status(f'Lab {tf} {LAB_FAMILY_KO[fam]}: 파라미터 {len(grid)}개 백테스트...', 'blue')
            sims = []
            for p in grid:
                tgt = _lab_target(fam, p, ind)
                mh = int(p['N']) if fam == 'meanrev' else int(p['H']) if fam in ('funding', 'analog', 'tod') \
                    else int(LAB_MAX_HOLD.get(fam, 0))
                ei, xi, sd, rr = lab_sim_x(o, h, l, c, atr, tgt, float(p['k']), mh, c_in, c_out, c_stop, fund,
                                           limit_through, float(fixed_stop), float(p.get('tp', 0.0)))
                sims.append((p, ei, rr, xi))
                n_sims += 1
            oos_r, oos_i, oos_x, hold_r, chosen = [], [], [], [], []
            for s in starts:
                e = min(s + test_n, len(df))
                best, best_score = None, 0.0
                for p, ei, rr, xi in sims:
                    m = (ei >= s - train_n) & (ei < s)
                    if m.sum() < LAB_MIN_TRAIN_TRADES:
                        continue
                    x = rr[m]
                    score = x.mean() - x.std(ddof=1) / math.sqrt(len(x))     # 평균 R 의 1σ 하한
                    if score > best_score:
                        best, best_score = (p, ei, rr, xi), score
                chosen.append((str(idx[s])[:10], None if best is None else best[0], e > i_hold))
                if best is None:
                    continue                                                # 고를 게 없으면 쉰다
                p, ei, rr, xi = best
                m = (ei >= s) & (ei < e)
                for j in np.flatnonzero(m):
                    (hold_r if ei[j] >= i_hold else oos_r).append(float(rr[j]))
                    if ei[j] < i_hold:
                        oos_i.append(int(ei[j]))
                        oos_x.append(int(xi[j]))
            years = max((idx[min(i_hold, len(idx) - 1)] - idx[min(train_n, len(idx) - 1)]).days / 365.25, 1e-6)
            hold_years = max((idx[-1] - idx[min(i_hold, len(idx) - 1)]).days / 365.25, 1e-6)
            met = _lab_metrics(oos_r, years, n_trials=n_dsr)
            _lab_attach_growth(met, oos_r, idx[np.asarray(oos_x, dtype=np.int64)].values,
                               idx[min(train_n, len(idx) - 1)], idx[max(min(i_hold, len(idx)) - 1, 0)])
            hmet = _lab_metrics(hold_r, hold_years, n_trials=1)
            last = next((pp for _, pp, _ in reversed(chosen) if pp is not None), None)
            rows.append(dict(tf=tf, family=fam, oos=met, holdout=hmet, last_params=last, oos_r=oos_r, hold_r_list=hold_r,
                             current_params=chosen[-1][1] if chosen else None,
                             oos_start=str(idx[min(train_n, len(idx) - 1)]),
                             oos_t=idx[np.asarray(oos_i, dtype=np.int64)].values, windows=len(chosen),
                             idle_windows=sum(1 for _, pp, _ in chosen if pp is None),
                             hold_windows=sum(1 for _, _, hh in chosen if hh),
                             hold_idle=sum(1 for _, pp, hh in chosen if hh and pp is None)))
    rows.sort(key=lambda r: (np.nan_to_num(r['oos']['ci_lo'], nan=-9), r['oos']['n']), reverse=True)
    out = dict(rows=rows, holdout_start=str(hold_start), n_trials=n_trials, n_dsr=n_dsr, n_sims=n_sims, symbol=symbol,
               fixed_stop=float(fixed_stop), tp_list=list(tp_list),
               n_families=len(families), tfs=list(tfs), cost_mode=cost_mode,
               declared=[f'{a}:{b}' for a, b in pairs] if pairs else None,
               funding_info=(f'{funding.index[0]:%Y-%m-%d} ~ {funding.index[-1]:%Y-%m-%d} · {len(funding):,}회 정산'
                             if has_funding else None),
               seconds=round(time.time() - t_wall, 1), revealed=bool(reveal_holdout),
               data=f'{t_first:%Y-%m-%d} ~ {t_last:%Y-%m-%d} ({src})')
    out['report'] = lab_report(out)
    return out


def lab_holdout_verdict(hm):
    """사전에 고정한 holdout 판정 규칙 — 결과를 보기 전에 정해 둔다."""
    if hm['n'] == 0:
        return '판정 불가 (holdout 체결 0건)'
    if not hm['mean_r'] > 0:
        return '반증 — 실전 신호원으로 연결하지 않는다'
    if hm['ci_lo'] > 0:
        return '확인 — prospective 추적(E5)으로 넘어갈 가치가 있다'
    return '반증 안 됨 — 아직 입증은 아니다, prospective 추적으로 증거를 더 쌓는다'


def lab_risk_table(R, years, fs=(0.01, 0.02, 0.03)):
    """거래당 계좌 위험 f 별로 표본외 거래를 순서대로 복리 적용: (f, 최종 배수, 하루 복리, 최대 낙폭), 최장 연속 손실."""
    R = np.clip(np.asarray(R, dtype=np.float64), -50, 50)
    run = streak = 0
    for x in R:
        run = run + 1 if x <= 0 else 0
        streak = max(streak, run)
    rows = []
    for f in fs:
        eq = np.concatenate(([1.0], np.cumprod(np.maximum(1.0 + f * R, 1e-12))))
        mult = float(eq[-1])
        rows.append((f, mult, mult ** (1.0 / max(365.0 * years, 1.0)) - 1.0, float((1 - eq / np.maximum.accumulate(eq)).max())))
    return rows, streak


def _lab_declared_lines(res):
    """사전 선언 가설의 holdout 판정 줄 (단일 코인·코인 묶음 공통)."""
    if not res.get('declared'):
        return []
    L = ['▶ holdout 판정 규칙 (실행 전에 고정): 평균R ≤ 0 → 반증 · 평균R > 0 → 반증 안 됨 · 90% CI 하한 > 0 → 확인']
    for r in res['rows']:
        name = f'{r["tf"]} {LAB_FAMILY_KO[r["family"]]}'
        if not res['revealed']:
            L.append(f'   {name}: holdout 봉인 — 같은 명령에 --reveal-holdout 을 붙이면 1회 공개(원장 기록)')
            continue
        hm = r['holdout']
        L.append(f'   {name}: holdout 체결 {hm["n"]}건 · 평균R {np.nan_to_num(hm["mean_r"]):+.3f} · '
                 f'90%CI [{np.nan_to_num(hm["ci_lo"]):+.3f}, {np.nan_to_num(hm["ci_hi"]):+.3f}] · '
                 f'승률 {np.nan_to_num(hm["win"]):.0%} · PF {np.nan_to_num(hm["pf"]):.2f} → {lab_holdout_verdict(hm)}')
        if 0 < hm['n'] < 30:
            L.append(f'     ※ 체결 {hm["n"]}건은 적다 — 평균R 의 오차가 커서 "확인"은 어렵고 "반증"이 더 강한 신호다.')
        if r.get('hold_windows'):
            L.append(f'     holdout 에 걸친 test 창 {r["hold_windows"]}개 중 {r["hold_idle"]}개는 쉼 '
                     f'(직전 train 에서 1σ 하한이 양수인 파라미터가 없었음)')
    return L


def lab_report(res):
    mode = res.get('cost_mode', 'taker')
    desc, c_in, c_out, _ = LAB_COST_MODES[mode]
    L = [f'━━━ STRATEGY LAB · {res.get("symbol", SYMBOL)} · {res["data"]} ━━━',
         f'전략군 {res.get("n_families", len(LAB_GRIDS))}개 × TF {"/".join(res.get("tfs", LAB_TFS))} = 절차 {res["n_trials"]}개 · '
         f'파라미터 백테스트 {res["n_sims"]}회 · {res["seconds"]}초',
         f'롤링 WFO: train {LAB_TRAIN_YEARS:g}년 → test {LAB_TEST_MONTHS}개월 · 위험 거래당 {LAB_RISK:.0%} 고정 · '
         f'holdout {res["holdout_start"][:10]} 이후 {"공개됨(원장 기록)" if res["revealed"] else "봉인"}',
         f'비용 [{mode}] {desc}: 진입 {c_in:.3%} + 청산 {c_out:.3%} (손절은 항상 시장가 {TAKER_FEE + SLIPPAGE_T:.3%})'
         + (' — 지정가 체결은 보장되지 않는다, 실제 체결률을 따로 기록해 확인할 것' if mode != 'taker' else ''),
         (f'손절: 가격 {res["fixed_stop"]:.1%} 고정 · 익절: {" / ".join("신호 청산" if t == 0 else f"{t:g}R" for t in res["tp_list"])} '
          f'중 train 이 고름 · 왕복 수수료는 1R 의 {2 * (TAKER_FEE + SLIPPAGE_T) / res["fixed_stop"]:.0%} · '
          f'계좌 위험 = 손절폭 × 레버리지 (가격 1% 손절에 2배 = 계좌 2%)') if res.get('fixed_stop') else '손절: 진입 시 k × ATR',
         f'펀딩비: {res["funding_info"]}' if res.get('funding_info') else '펀딩비: 데이터 없음 → 펀딩비 전략군 생략']
    if res.get('declared'):
        L.append(f'사전 선언 가설: {", ".join(res["declared"])} · 표본외 DSR 은 탐색 전체 절차 {res["n_dsr"]}개로 보정 '
                 f'(가설을 고른 선택까지 반영)')
    L += ['─' * 96,
          f'{"순위":<4}{"TF":<5}{"전략군":<16}{"OOS체결":>8}{"연간":>7}{"승률":>7}{"평균R":>8}{"90%CI 하한":>11}{"PF":>6}'
          f'{"MDD(1%)":>9}{"DSR":>6}{"보수 하루복리@위험":>18}' + ('  holdout평균R/건수' if res['revealed'] else '')]
    idle = [r for r in res['rows'] if r['oos']['n'] == 0]
    for k, r in enumerate([r for r in res['rows'] if r['oos']['n'] > 0], 1):
        m = r['oos']
        line = (f'{k:<4}{r["tf"]:<5}{LAB_FAMILY_KO[r["family"]]:<16}{m["n"]:>8}{m["n_year"]:>7.0f}'
                f'{np.nan_to_num(m["win"]):>7.0%}{np.nan_to_num(m["mean_r"]):>+8.3f}{np.nan_to_num(m["ci_lo"], nan=0):>+11.3f}'
                f'{np.nan_to_num(m["pf"]):>6.2f}{m["mdd"]:>9.1%}{m["dsr"]:>6.2f}'
                f'{m.get("g_day", 0.0):>+12.3%}@{m.get("f_star", 0.0):<6.1%}')
        if res['revealed']:
            hm = r['holdout']
            line += f'  {np.nan_to_num(hm["mean_r"]):+.3f}/{hm["n"]}'
        L.append(line)
    if idle:
        L.append(f'거래 0건 = 모든 test 구간에서 쉼 ({len(idle)}개 — 직전 train 에서 1σ 하한이 양수인 파라미터가 한 번도 없었음, '
                 f'즉 비용을 넘는 근거가 없어 스스로 거래를 거부): ' + ', '.join(f'{r["tf"]} {LAB_FAMILY_KO[r["family"]]}' for r in idle))
    L.append('─' * 96)
    L.append('보수 하루복리 = 90% CI 하한만큼만 엣지가 있다고 보고, 평균 하루 복리가 최대가 되는 거래당 위험(@)으로 걸었을 때의 값 '
             '(같은 날 청산은 합산). 증거가 없으면 0 이 정답이다.')
    good = [r for r in res['rows'] if r['oos']['n'] >= 50 and r['oos']['ci_lo'] > 0 and r['oos']['dsr'] >= 0.9]
    if good:
        good.sort(key=lambda r: r['oos'].get('g_day', 0.0), reverse=True)    # 통과한 것 중 '하루 복리가 큰' 순
        L.append('▶ 사전 기준 통과 (표본외 체결 ≥ 50, CI 하한 > 0, DSR ≥ 0.9) — 하루 복리 순:')
        for g in good[:3]:
            m = g['oos']
            L.append(f'   {g["tf"]} {LAB_FAMILY_KO[g["family"]]}: 거래당 위험 {m["f_star"]:.1%} → 하루 {m["g_day"]:+.3%} (보수) / '
                     f'{m["g_day_point"]:+.3%} (점추정) · 70달러 → 1년 {70 * (1 + m["g_day"]) ** 365:,.0f}달러 (보수) · '
                     f'최근 파라미터 {g["last_params"]}')
        L.append('  다음 단계: 가짜 BTC 대조군(--surrogate-n)에서 같은 수준이 안 나오는지 확인 → holdout 1회 공개로 최종 확인 → '
                 'prospective 추적. 통과해야 실전 신호원으로 연결할 가치가 있다.')
    else:
        L.append('▶ 사전 기준(표본외 체결 ≥ 50, CI 하한 > 0, DSR ≥ 0.9)을 통과한 절차 없음 — 이 데이터·비용에서 입증된 edge 없음.')
    if res.get('fixed_stop'):
        tops = [r for r in res['rows'] if r['oos']['n'] >= 30][:3]
        if tops:
            L.append('▶ 거래당 계좌 위험별 표본외 결과 (가격 손절 고정이므로 레버리지가 곧 계좌 위험: 1배=1% · 2배=2% · 3배=3%)')
        for r in tops:
            m = r['oos']
            rows, streak = lab_risk_table(r['oos_r'], m['n'] / max(m['n_year'], 1e-9))
            cells = ' · '.join(f'{f:.0%}: ×{mult:.2f} (하루 {d:+.3%}, 최대낙폭 {dd:.0%})' for f, mult, d, dd in rows)
            L.append(f'   {r["tf"]} {LAB_FAMILY_KO[r["family"]]} ({m["n"]}건, 평균 {m["mean_r"]:+.3f}R, 최장 연속 손실 {streak}번): {cells}')
        if tops:
            L.append('   ※ 평균R 이 음수면 위험을 키울수록 더 빨리 잃는다. 2~3% 는 프로그램 실전 상한(거래당 1%)보다 높다 — '
                     '앞으로의 데이터가 엣지를 보여 줄 때만 올린다.')
    L += _lab_declared_lines(res)
    L.append('※ 성과는 "과거 train 으로 고른 파라미터를 보지 않은 다음 구간에 적용한" 표본외 성과다. 최상위 1개만 보고 고르면 '
             '그 자체가 선택이므로 DSR(절차 수 보정)과 가짜 BTC 결과를 함께 볼 것.')
    L.append(lab_sharpe_line(res['rows']))
    L.append('※ 거래소 최소주문·레버리지 한도는 반영하지 않은 연구용 결과다 (R 단위 비교가 목적).')
    return '\n'.join(L)


def _lab_luck_collect(res, same, best):
    """가짜 차트 1회 결과를 모은다: 절차별 CI 하한, 그리고 그 회차의 최고 CI 하한 (체결 부족 = NaN = 아무것도 못 이김)."""
    los = []
    for r in res['rows']:
        lo = float(r['oos']['ci_lo'])
        same.setdefault((r['tf'], r['family']), []).append(lo)
        los.append(lo)
    best.append(float(np.nanmax(los)) if np.isfinite(los).any() else float('nan'))


def _lab_luck_report(real, same, best, n, cost_mode, only, seconds, title='LAB 운의 크기'):
    best = np.asarray(best, dtype=np.float64)

    def fmt(x, w):
        return f'{x:>+{w}.3f}' if np.isfinite(x) else f'{"체결부족":>{w - 2}}'

    def p_of(xs, lo):
        if not np.isfinite(lo):
            return 1.0                                        # 실제가 체결 부족이면 증거 없음
        return (1 + int((np.nan_to_num(xs, nan=-np.inf) >= lo).sum())) / (len(xs) + 1)

    def q(xs, f):
        xs = xs[np.isfinite(xs)]
        return f(xs) if len(xs) else float('nan')
    L = [f'━━━ {title} · 가짜 {n}개 × 절차 {real["n_trials"]}개 · 비용 [{cost_mode}] · {round(seconds, 1)}초 ━━━',
         f'가짜 최고 CI 하한: 중앙 {fmt(q(best, np.median), 7)} · 90% 분위 {fmt(q(best, lambda v: np.quantile(v, 0.9)), 7)}'
         f' · 최고 {fmt(q(best, np.max), 7)}',
         f'{"TF":<5}{"전략군":<16}{"실제 CI하한":>11}{"가짜(같은절차) 중앙/최고":>24}{"p(같은 절차)":>13}{"p(최고 절차)":>13}']
    for r in sorted(real['rows'], key=lambda r: np.nan_to_num(r['oos']['ci_lo'], nan=-9), reverse=True)[:10]:
        lo = float(r['oos']['ci_lo'])
        xs = np.asarray(same.get((r['tf'], r['family']), [float('nan')]), dtype=np.float64)
        L.append(f'{r["tf"]:<5}{LAB_FAMILY_KO[r["family"]]:<16}{fmt(lo, 11)}'
                 f'{fmt(q(xs, np.median), 13)} / {fmt(q(xs, np.max), 8)}{p_of(xs, lo):>13.3f}{p_of(best, lo):>13.3f}')
    L.append('※ 탐색 결과를 보고 고른 절차라면 p(최고 절차)가 맞는 값이다. p < 0.05 이어도 holdout·prospective 는 그대로 필요하다.')
    if only:
        L.append('※ --only 로 돌리면 가짜에서도 선언한 절차만 돌리므로 "여러 개 중 고른 선택"은 보정되지 않는다. '
                 '선택까지 보정한 p 는 --only 없이 --surrogate-n 으로 낸다.')
    L.append(f'※ 가짜 {n}개로 낼 수 있는 가장 작은 p 는 {1 / (n + 1):.3f} 다 (더 정밀하게: --surrogate-n 50).')
    return '\n'.join(L)


def lab_surrogate_test(base1m, n=20, only=None, seed0=100, cost_mode='taker', funding=None, n_trials_declared=None,
                       status=None, futures_only=True, holdout_start=None, tfs=LAB_TFS, fixed_stop=0.0,
                       tp_list=LAB_FIXED_TP):
    """
    같은 탐색 절차를 가짜 BTC n 개에서 반복해 '운으로 이만큼 나올 확률'을 잰다.
      p(같은 절차) = (1 + #{가짜에서 같은 TF·전략군의 CI 하한 ≥ 실제}) / (n + 1)
      p(최고 절차) = (1 + #{가짜에서 전체 절차 중 최고 CI 하한 ≥ 실제}) / (n + 1)   ← 여러 개 중 고른 선택까지 반영
    가짜 BTC 는 하루 블록 셔플 → 날을 넘는 가격 구조와 펀딩비-가격 관계(펀딩비는 시각 고정)가 끊긴다.
    """
    status = status or (lambda *a, **k: None)
    t_wall = time.time()
    base1m = normalize_frame(base1m)
    if futures_only and (base1m['era'].values == ERA_FUT).any():
        base1m = base1m[base1m['era'].values == ERA_FUT]
    kw = dict(only=only, cost_mode=cost_mode, funding=funding, n_trials_declared=n_trials_declared,
              futures_only=futures_only, holdout_start=holdout_start, tfs=tfs, fixed_stop=fixed_stop, tp_list=tp_list)
    status('실제 데이터로 탐색...', 'blue')
    real = lab_run(base1m, **kw)
    same, best = {}, []
    for k in range(int(n)):
        status(f'가짜 BTC {k + 1}/{n} 탐색...', 'blue')
        _lab_luck_collect(lab_run(make_surrogate_1m(base1m, seed=seed0 + k), **kw), same, best)
    rep_ = _lab_luck_report(real, same, best, n, cost_mode, only, time.time() - t_wall, title='LAB 운의 크기 · 가짜 BTC')
    return dict(real=real, best=best, same={f'{a}:{b}': v for (a, b), v in same.items()}, report=rep_)


def _month_cluster_ci(R, T, n_boot=3000, q=0.05, seed=0):
    """같은 달 거래는 코인이 달라도 같이 움직이므로 '달' 단위로 묶어 부트스트랩한 평균 R 의 하한."""
    R = np.asarray(R, dtype=np.float64)
    if len(R) < 5:
        return float('nan')
    mon = np.asarray(T).astype('datetime64[M]')
    _, g = np.unique(mon, return_inverse=True)
    sums, cnts = np.bincount(g, weights=R), np.bincount(g).astype(np.float64)
    if len(sums) < 3:
        return float('nan')
    draw = np.random.default_rng(seed).integers(0, len(sums), size=(n_boot, len(sums)))
    return float(np.quantile(sums[draw].sum(1) / np.maximum(cnts[draw].sum(1), 1), q))


def lab_replication_verdict(n, mean_r, ci_lo, pos, tot):
    """사전에 고정한 재현 판정 규칙."""
    if n == 0:
        return '판정 불가 (체결 없음)'
    if not mean_r > 0:
        return '재현 실패 — BTC 결과는 BTC 한 시장의 우연일 가능성이 크다'
    if n >= 100 and ci_lo > 0 and tot > 0 and 3 * pos >= 2 * tot:
        return '재현 확인 — 여러 시장에서 반복되는 구조다 (holdout·prospective 로 최종 확인)'
    return '불충분 — 방향은 같지만 아직 입증은 아니다'


def lab_cross_asset(base1m, only, symbols=LAB_ALT_SYMBOLS, http=None, cost_mode='taker', funding=None,
                    n_trials_declared=None, frames_by_symbol=None, funding_by_symbol=None, status=None,
                    holdout_start=None):
    """
    BTC 에서 고른 가설을 다른 코인에 '그대로' 적용한다 — 같은 파라미터 격자, 같은 WFO 선택 규칙, 같은 비용.
    가설을 고를 때 쓰지 않은 시장이라 진짜 표본외 검증이고("역사는 반복된다"가 사람 심리 때문이라면 다른 코인에서도
    반복돼야 한다), 통과하면 같은 규칙의 거래 기회가 코인 수만큼 늘어 성장 속도가 빨라진다.
    BTC holdout 과 같은 날짜 이후는 알트에서도 봉인한다 (알트는 BTC 와 같이 움직여서, 열면 BTC holdout 을 엿보는 셈).
    """
    status = status or (lambda *a, **k: None)
    pairs = lab_pairs(only)
    if not pairs:
        raise ValueError('다른 코인 재현 검증은 --only 로 선언한 가설에만 씁니다 (다시 탐색하면 표본외가 아니다)')
    t_wall = time.time()
    http = http or PublicHttp()
    tfs = sorted({tf for tf, _ in pairs}, key=INTERVALS.get)
    need_funding = any(f == 'funding' for _, f in pairs)
    btc = lab_run(base1m, only=pairs, cost_mode=cost_mode, funding=funding, n_trials_declared=n_trials_declared,
                  holdout_start=holdout_start)
    hold = btc['holdout_start']
    per, skipped = {}, []
    for sym in symbols:
        status(f'{sym}: 봉 데이터 준비...', 'blue')
        frames = (frames_by_symbol or {}).get(sym) if frames_by_symbol is not None else \
            {tf: fetch_klines_tf(http, sym, tf) for tf in tfs}
        frames = {k: v for k, v in (frames or {}).items() if v is not None and len(v)}
        f = None
        if need_funding:
            f = (funding_by_symbol or {}).get(sym) if funding_by_symbol is not None else \
                load_funding_history(http, symbol=sym)
        use = [(tf, fam) for tf, fam in pairs if tf in frames and (fam != 'funding' or f is not None)]
        if not use:
            skipped.append(sym)
            continue
        try:
            res = lab_run(None, tf_frames=frames, only=use, cost_mode=cost_mode, funding=f, holdout_start=hold,
                          symbol=sym)
        except ValueError as e:
            skipped.append(f'{sym}({e})')
            continue
        for r in res['rows']:
            per.setdefault((r['tf'], r['family']), []).append((sym, r))
    summary, L = [], [f'━━━ 다른 코인 재현 검증 · 가설 {", ".join(f"{a}:{b}" for a, b in pairs)} · 코인 {len(symbols)}개 · '
                      f'비용 [{cost_mode}] · {round(time.time() - t_wall, 1)}초 ━━━',
                      'BTC 에서 고른 가설을 같은 격자·같은 선택 규칙·같은 비용으로 그대로 적용 (선택에 쓰지 않은 시장 = 진짜 표본외)',
                      f'holdout {hold[:10]} 이후는 알트에서도 봉인 · 판정 규칙(사전 고정): 알트 합산 체결 ≥ 100 · 달 단위 묶음 '
                      f'부트스트랩 90% CI 하한 > 0 · 체결 10건 이상 코인의 2/3 이상이 평균R > 0 → 재현 확인 / 합산 평균R ≤ 0 → 재현 실패 / '
                      f'그 외 → 불충분']
    for tf, fam in pairs:
        b = next((r for r in btc['rows'] if (r['tf'], r['family']) == (tf, fam)), None)
        L += ['', f'── {tf} {LAB_FAMILY_KO[fam]} ──',
              f'{"코인":<11}{"체결":>6}{"연간":>6}{"승률":>6}{"평균R":>8}{"90%CI하한":>10}{"PF":>6}{"연복리(1%)":>11}']

        def row_line(sym, m, note=''):
            return (f'{sym:<11}{m["n"]:>6}{m["n_year"]:>6.0f}{np.nan_to_num(m["win"]):>6.0%}{np.nan_to_num(m["mean_r"]):>+8.3f}'
                    f'{np.nan_to_num(m["ci_lo"]):>+10.3f}{np.nan_to_num(m["pf"]):>6.2f}{m["cagr"]:>+11.1%}{note}')
        if b is not None:
            L.append(row_line(SYMBOL, b['oos'], '   ← 가설을 고른 데이터 (표본외 아님)'))
        R, T, n_year, pos, tot = [], [], 0.0, 0, 0
        for sym, r in per.get((tf, fam), []):
            m = r['oos']
            L.append(row_line(sym, m))
            R += list(r['oos_r'])
            T += list(r['oos_t'])
            n_year += m['n_year']
            if m['n'] >= 10:
                tot += 1
                pos += int(m['mean_r'] > 0)
        R = np.asarray(R, dtype=np.float64)
        lo = _month_cluster_ci(R, np.asarray(T, dtype='datetime64[ns]')) if len(R) else float('nan')
        mean = float(R.mean()) if len(R) else float('nan')
        pf = float(R[R > 0].sum() / max(-R[R <= 0].sum(), 1e-9)) if len(R) else float('nan')
        verdict = lab_replication_verdict(len(R), mean, lo, pos, tot)
        L.append(f'{"알트 합산":<9}{len(R):>6}{n_year:>6.0f}{np.nan_to_num(np.mean(R > 0) if len(R) else 0):>6.0%}'
                 f'{np.nan_to_num(mean):>+8.3f}{np.nan_to_num(lo):>+10.3f}{np.nan_to_num(pf):>6.2f}   '
                 f'평균R>0 코인 {pos}/{tot} → {verdict}')
        if b is not None and b['oos']['n_year'] > 0 and n_year > 0:
            L.append(f'   빈도: BTC 연 {b["oos"]["n_year"]:.0f}건 + 알트 연 {n_year:.0f}건 → 같은 규칙의 기회가 약 '
                     f'{(b["oos"]["n_year"] + n_year) / b["oos"]["n_year"]:.1f}배 (코인끼리 같이 움직여서 실제 분산 효과는 그보다 작다)')
        summary.append(dict(pair=f'{tf}:{fam}', n=int(len(R)), mean_r=mean, ci_lo=lo, pos=pos, tot=tot, verdict=verdict,
                            per_symbol={sym: r['oos'] for sym, r in per.get((tf, fam), [])}))
    if skipped:
        L.append(f'\n데이터가 없거나 적용할 수 없어 건너뜀: {", ".join(skipped)}')
    L.append('※ 알트 결과는 가설 선택에 쓰지 않은 데이터라 DSR 대신 사전 고정 규칙으로 판정한다. 같은 가설로 코인 목록을 바꿔 가며 '
             '여러 번 돌리면 그것도 선택이다 — 첫 실행 결과를 기준으로 삼을 것.')
    return dict(btc=btc, summary=summary, holdout_start=hold, symbols=list(symbols), skipped=skipped,
                cost_mode=cost_mode, report='\n'.join(L))


def lab_record_cross_asset(engine, res):
    """다른 코인 재현 검증도 원장에 남긴다 (몇 번, 어떤 가설로 시험했는지가 증거의 일부)."""
    with engine.state.tx() as st:
        engine.state.emit(st, 'SYSTEM', what='lab_cross_asset', holdout_start=res['holdout_start'],
                          symbols=res['symbols'], cost_mode=res['cost_mode'],
                          summary=[{k: v for k, v in x.items() if k != 'per_symbol'} for x in res['summary']])


def make_surrogate_frames(frames_by_symbol, seed=0):
    """
    코인 묶음용 가짜 차트: 모든 코인의 날짜를 '같은 순서'로 하루 블록 셔플한다. 같은 날 코인들이 같이 움직이는 동조는
    남고, 날짜를 넘는 흐름(사람들이 이어 가는 추세·되돌림)은 끊긴다. 펀딩비는 시각에 고정 → 가격과의 관계도 끊긴다.
    """
    g = np.random.default_rng(seed)
    days = np.unique(np.concatenate([df.index.values.astype('datetime64[D]').astype(np.int64)
                                     for fr in frames_by_symbol.values() for df in fr.values() if df is not None]))
    key = g.permutation(len(days))
    out = {}
    for sym, fr in frames_by_symbol.items():
        out[sym] = {}
        for tf, df in fr.items():
            if df is None or not len(df):
                continue
            df = normalize_frame(df)
            day = df.index.values.astype('datetime64[D]').astype(np.int64)
            uniq, start = np.unique(day, return_index=True)
            end = np.r_[start[1:], len(day)]
            order = np.argsort(key[np.searchsorted(days, uniq)], kind='stable')
            ix = np.concatenate([np.arange(start[k], end[k]) for k in order])
            out[sym][tf] = _reorder_frame(df, ix)
    return out


def _lab_xs_ranks(frames_tf, Ls):
    """같은 시각 봉끼리 코인 간 최근 L봉 수익률 순위 (0 = 가장 약함, 1 = 가장 강함). 코인 4개 미만인 시각은 NaN."""
    out = {sym: {} for sym in frames_tf}
    for L in Ls:
        rets = pd.DataFrame({sym: np.log(df['close'] / df['close'].shift(L)) for sym, df in frames_tf.items()})
        cnt = rets.notna().sum(axis=1)
        rk = (rets.rank(axis=1) - 1).div((cnt - 1).where(cnt >= 4), axis=0)
        for sym, df in frames_tf.items():
            out[sym][L] = rk[sym].reindex(df.index).values
    return out


def lab_btc_frames(base1m, tfs):
    """로컬 BTC 1분봉(선물 구간) → 완결된 tf 봉 (코인 묶음에서 BTC 는 REST 대신 이미 받은 1분봉을 쓴다)."""
    base = normalize_frame(base1m)
    if (base['era'].values == ERA_FUT).any():
        base = base[base['era'].values == ERA_FUT]
    snap = Snapshot(base, base.index[-1].to_pydatetime() + timedelta(minutes=1))
    out = {}
    for tf in tfs:
        d = snap.tf(tf)
        out[tf] = d[d['complete'].values > 0.5][STORE_COLS]
    return out


def lab_universe_trial_count(tfs=LAB_UNIVERSE_TFS, families=None):
    families = list(families or LAB_GRIDS)
    return sum(1 for tf in tfs for fam in families
               if tf in LAB_FAMILY_TFS.get(fam, LAB_TFS) and (tf, fam) not in LAB_UNIVERSE_SKIP)


def lab_run_universe(frames_by_symbol, tfs=LAB_UNIVERSE_TFS, families=None, holdout_start=None,
                     holdout_months=LAB_HOLDOUT_MONTHS, train_years=LAB_TRAIN_YEARS, test_months=LAB_TEST_MONTHS,
                     cost_mode='taker', funding_by_symbol=None, reveal_holdout=False, status=None, only=None,
                     n_trials_declared=None):
    """
    여러 코인을 '한 묶음'으로 롤링 WFO 한다. 각 test 구간의 파라미터는 직전 train 구간의 모든 코인 거래를 합쳐서 고르고,
    같은 파라미터를 모든 코인에 적용한다. → 한 코인의 우연에 맞춘 파라미터가 뽑히기 어렵고(BTC 단독 탐색의 패인),
    거래 기회는 코인 수만큼 늘어난다(하루 복리의 원천). 신뢰구간은 같은 달 거래를 묶어 부트스트랩한다
    (코인끼리 같이 움직이므로 거래 수를 그대로 믿으면 과신). 반환 dict(rows, report, ...).
    """
    status = status or (lambda *a, **k: None)
    if cost_mode not in LAB_COST_MODES:
        raise ValueError(f'알 수 없는 비용 시나리오 {cost_mode} — 가능한 값: {", ".join(LAB_COST_MODES)}')
    _, c_in0, c_out0, limit_through = LAB_COST_MODES[cost_mode]
    t_wall = time.time()
    frames = {sym: {tf: normalize_frame(df) for tf, df in fr.items() if df is not None and len(df)}
              for sym, fr in frames_by_symbol.items()}
    frames = {sym: fr for sym, fr in frames.items() if fr}
    if len(frames) < 2:
        raise ValueError('코인 묶음은 봉 데이터가 있는 코인이 2개 이상 필요합니다')
    funding_by_symbol = funding_by_symbol or {}
    good_f = [f for f in funding_by_symbol.values() if f is not None and len(f) >= LAB_FUNDING_WINDOW // 2]
    avail = set(lab_available_families(good_f[0] if good_f else None, universe=True))
    families = [f for f in (families or LAB_GRIDS) if f in avail]
    pairs = lab_pairs(only)
    if pairs:
        if any(f == 'funding' for _, f in pairs) and not good_f:
            raise ValueError('펀딩비 데이터가 없어 펀딩비 전략군을 검증할 수 없습니다')
        if any(f == 'analog' for _, f in pairs) and not NUMBA_OK:
            raise ValueError('패턴 반복 전략군은 numba 가 필요합니다 (pip install numba)')
        tfs = tuple(t for t in INTERVALS if any(t == a for a, _ in pairs))
        families = [f for f in LAB_GRIDS if any(f == b for _, b in pairs)]

    def applies(fam, tf):
        return (tf in LAB_FAMILY_TFS.get(fam, LAB_TFS) and (tf, fam) not in LAB_UNIVERSE_SKIP
                and (pairs is None or (tf, fam) in pairs))
    n_trials = sum(1 for tf in tfs for fam in families if applies(fam, tf))
    n_dsr = max(n_trials, int(n_trials_declared or 0))
    all_df = [(tf, df) for fr in frames.values() for tf, df in fr.items()]
    t_first = min(df.index[0] for _, df in all_df)
    t_last = max(df.index[-1] + pd.Timedelta(minutes=INTERVALS[tf] - 1) for tf, df in all_df)
    hold_start = pd.Timestamp(holdout_start) if holdout_start is not None \
        else t_last - pd.DateOffset(months=int(holdout_months))
    train_off = pd.DateOffset(months=int(round(train_years * 12)))
    oos_start = t_first + train_off
    wins, w = [], oos_start
    while w < t_last:
        wins.append(w)
        w = w + pd.DateOffset(months=int(test_months))
    h64 = np.datetime64(hold_start)
    oos_end = min(hold_start, t_last)                       # holdout 이 데이터 끝 뒤면 표본외는 데이터 끝까지
    years = max((oos_end - oos_start).days / 365.25, 1e-6)
    hold_years = max((t_last - hold_start).days / 365.25, 1e-6)
    syms = list(frames)
    rows, n_sims = [], 0
    for tf in tfs:
        ftf = {sym: fr[tf] for sym, fr in frames.items() if tf in fr and len(fr[tf]) >= 500}
        if len(ftf) < 2 or not any(applies(f, tf) for f in families):
            continue
        inds = {}
        for sym, df in ftf.items():
            ind = _lab_indicators(df)
            f = funding_by_symbol.get(sym)
            if applies('funding', tf) and 'funding' in families and f is not None and len(f) >= LAB_FUNDING_WINDOW // 2:
                ind['fpct'] = _lab_funding_pct(df.index, INTERVALS[tf], f)
            inds[sym] = ind
        if 'xsmom' in families and applies('xsmom', tf):
            xs = _lab_xs_ranks(ftf, sorted({q['L'] for q in LAB_GRIDS['xsmom']}))
            for sym in inds:
                inds[sym]['xsrank'] = xs[sym]
        bar_h = INTERVALS[tf] / 60.0
        fund = FUNDING_PER_8H * bar_h / 8.0
        for fam in families:
            if not applies(fam, tf):
                continue
            status(f'Lab 묶음 {tf} {LAB_FAMILY_KO[fam]}: 파라미터 {len(LAB_GRIDS[fam])}개 × 코인 {len(inds)}개...', 'blue')
            sims = []
            for p in LAB_GRIDS[fam]:
                E, X, RR, S = [], [], [], []
                mh = int(p['N']) if fam == 'meanrev' else int(p['H']) if fam in ('funding', 'analog', 'tod') \
                    else int(LAB_MAX_HOLD.get(fam, 0))
                for k, (sym, ind) in enumerate(inds.items()):
                    extra = 0.0 if sym == SYMBOL else LAB_ALT_EXTRA_SLIP
                    c_in = c_in0 + (extra if limit_through < 0 else 0.0)
                    c_out = c_out0 + (extra if c_out0 > MAKER_FEE + 1e-12 else 0.0)
                    tgt = _lab_target(fam, p, ind)
                    ei, xi, sd, rr = lab_sim_x(ind['o'].values, ind['h'].values, ind['l'].values, ind['c'].values,
                                               ind['atr'].values, tgt, float(p['k']), mh, c_in, c_out,
                                               TAKER_FEE + SLIPPAGE_T + extra, fund, limit_through, 0.0, 0.0)
                    E.append(ind['idx'].values[ei])
                    X.append(ind['idx'].values[xi])
                    RR.append(rr)
                    S.append(np.full(len(rr), syms.index(sym), dtype=np.int64))
                    n_sims += 1
                sims.append((p, np.concatenate(E), np.concatenate(X), np.concatenate(RR), np.concatenate(S)))
            oR, oE, oX, oS, hR, hE, chosen = [], [], [], [], [], [], []
            for w in wins:
                ws, wt = np.datetime64(w), np.datetime64(w - train_off)
                we = np.datetime64(w + pd.DateOffset(months=int(test_months)))
                best, best_score = None, 0.0
                for sim in sims:
                    _, E, X, RR, S = sim
                    m = (E >= wt) & (E < ws)
                    if m.sum() < LAB_UNIVERSE_MIN_TRAIN:
                        continue
                    x = RR[m]
                    neff = min(len(x), len(np.unique(E[m].astype('datetime64[D]'))))     # 같은 날 진입은 한 번으로
                    score = x.mean() - x.std(ddof=1) / math.sqrt(neff)
                    if score > best_score:
                        best, best_score = sim, score
                chosen.append((str(w)[:10], None if best is None else best[0], we > h64))
                if best is None:
                    continue
                _, E, X, RR, S = best
                m = (E >= ws) & (E < we)
                om, hm = m & (E < h64), m & (E >= h64)
                oR.append(RR[om]); oE.append(E[om]); oX.append(X[om]); oS.append(S[om])
                hR.append(RR[hm]); hE.append(E[hm])
            cat = (lambda a, dt: np.concatenate(a) if a else np.array([], dtype=dt))
            oR, oE, oX, oS = cat(oR, np.float64), cat(oE, 'datetime64[ns]'), cat(oX, 'datetime64[ns]'), cat(oS, np.int64)
            hR, hE = cat(hR, np.float64), cat(hE, 'datetime64[ns]')
            order = np.argsort(oX, kind='stable')
            oR, oE, oX, oS = oR[order], oE[order], oX[order], oS[order]
            met = _lab_metrics(oR, years, n_trials=n_dsr)
            if met['n'] >= 5:
                met['ci_lo'], met['ci_hi'] = _month_cluster_ci(oR, oE), _month_cluster_ci(oR, oE, q=0.95)
            _lab_attach_growth(met, oR, oX, oos_start, oos_end)
            hmet = _lab_metrics(hR, hold_years, n_trials=1)
            if hmet['n'] >= 5:
                hmet['ci_lo'], hmet['ci_hi'] = _month_cluster_ci(hR, hE), _month_cluster_ci(hR, hE, q=0.95)
            per = {sym: (int((oS == k).sum()), float(oR[oS == k].mean()) if (oS == k).any() else float('nan'))
                   for k, sym in enumerate(syms) if sym in inds}
            tot = sum(1 for n_, _ in per.values() if n_ >= 10)
            pos = sum(1 for n_, mr in per.values() if n_ >= 10 and mr > 0)
            last = next((pp for _, pp, _ in reversed(chosen) if pp is not None), None)
            rows.append(dict(tf=tf, family=fam, oos=met, holdout=hmet, per_symbol=per, pos=pos, tot=tot,
                             last_params=last, oos_r=oR, oos_t=oE, hold_r_list=hR, windows=len(chosen),
                             idle_windows=sum(1 for _, pp, _ in chosen if pp is None),
                             hold_windows=sum(1 for _, _, hh in chosen if hh),
                             hold_idle=sum(1 for _, pp, hh in chosen if hh and pp is None)))
    rows.sort(key=lambda r: (r['oos'].get('g_day', 0.0), np.nan_to_num(r['oos']['ci_lo'], nan=-9), r['oos']['n']),
              reverse=True)
    out = dict(rows=rows, mode='universe', symbols=syms, holdout_start=str(hold_start), n_trials=n_trials, n_dsr=n_dsr,
               n_sims=n_sims, n_families=len(families), tfs=list(tfs), cost_mode=cost_mode, revealed=bool(reveal_holdout),
               declared=[f'{a}:{b}' for a, b in pairs] if pairs else None, seconds=round(time.time() - t_wall, 1),
               funding_info=f'{len(good_f)}/{len(syms)}개 코인' if good_f else None,
               data=f'{t_first:%Y-%m-%d} ~ {t_last:%Y-%m-%d}')
    out['report'] = lab_universe_report(out)
    return out


def lab_universe_passed(r):
    m = r['oos']
    return m['n'] >= 100 and m['ci_lo'] > 0 and m['dsr'] >= 0.9 and r['tot'] > 0 and 3 * r['pos'] >= 2 * r['tot']


def lab_universe_report(res):
    mode = res['cost_mode']
    desc, c_in, c_out, _ = LAB_COST_MODES[mode]
    L = [f'━━━ STRATEGY LAB · 코인 묶음 {len(res["symbols"])}개 ({", ".join(s.replace("USDT", "") for s in res["symbols"])}) · '
         f'{res["data"]} ━━━',
         f'전략군 {res["n_families"]}개 × TF {"/".join(res["tfs"])} = 절차 {res["n_trials"]}개 · 코인별 백테스트 {res["n_sims"]}회 · '
         f'{res["seconds"]}초',
         f'묶음 WFO: train {LAB_TRAIN_YEARS:g}년의 모든 코인 거래를 합쳐 파라미터 선택 → test {LAB_TEST_MONTHS}개월에 모든 코인 적용 · '
         f'holdout {res["holdout_start"][:10]} 이후 {"공개됨(원장 기록)" if res["revealed"] else "봉인"}',
         f'비용 [{mode}] {desc}: 진입 {c_in:.3%} + 청산 {c_out:.3%} (손절은 항상 시장가, 알트는 시장가마다 +{LAB_ALT_EXTRA_SLIP:.2%})',
         f'펀딩비: {res["funding_info"]}' if res.get('funding_info') else '펀딩비: 데이터 없음 → 펀딩비 전략군 생략']
    if res.get('declared'):
        L.append(f'사전 선언 가설: {", ".join(res["declared"])} · 표본외 DSR 은 탐색 전체 절차 {res["n_dsr"]}개로 보정')
    L += ['─' * 110,
          f'{"순위":<4}{"TF":<5}{"전략군":<16}{"체결":>6}{"연간":>6}{"승률":>6}{"평균R":>8}{"CI하한(달묶음)":>13}{"PF":>6}'
          f'{"코인+":>7}{"DSR":>6}{"보수 하루복리@위험":>18}' + ('  holdout평균R/건수' if res['revealed'] else '')]
    idle = [r for r in res['rows'] if r['oos']['n'] == 0]
    for k, r in enumerate([r for r in res['rows'] if r['oos']['n'] > 0], 1):
        m = r['oos']
        coins = f'{r["pos"]}/{r["tot"]}'
        line = (f'{k:<4}{r["tf"]:<5}{LAB_FAMILY_KO[r["family"]]:<16}{m["n"]:>6}{m["n_year"]:>6.0f}'
                f'{np.nan_to_num(m["win"]):>6.0%}{np.nan_to_num(m["mean_r"]):>+8.3f}{np.nan_to_num(m["ci_lo"]):>+13.3f}'
                f'{np.nan_to_num(m["pf"]):>6.2f}{coins:>7}{m["dsr"]:>6.2f}'
                f'{m.get("g_day", 0.0):>+12.3%}@{m.get("f_star", 0.0):<6.1%}')
        if res['revealed']:
            hm = r['holdout']
            line += f'  {np.nan_to_num(hm["mean_r"]):+.3f}/{hm["n"]}'
        L.append(line)
    if idle:
        L.append(f'거래 0건 = 모든 test 구간에서 쉼 ({len(idle)}개): ' + ', '.join(f'{r["tf"]} {LAB_FAMILY_KO[r["family"]]}' for r in idle))
    L.append('─' * 110)
    L.append('코인+ = 체결 10건 이상 코인 중 평균R > 0 인 코인 수. 보수 하루복리 = CI 하한만큼만 엣지가 있다고 보고 평균 하루 복리가 '
             '최대가 되는 거래당 위험(@)으로 모든 코인 신호에 걸었을 때 (같은 날 청산은 합산).')
    good = [r for r in res['rows'] if lab_universe_passed(r)]
    crit = '합산 체결 ≥ 100, 달묶음 CI 하한 > 0, DSR ≥ 0.9, 코인 2/3 이상 평균R > 0'
    if good:
        L.append(f'▶ 사전 기준 통과 ({crit}) — 하루 복리 순:')
        for g in good[:3]:
            m = g['oos']
            L.append(f'   {g["tf"]} {LAB_FAMILY_KO[g["family"]]}: 거래당 위험 {m["f_star"]:.1%} → 하루 {m["g_day"]:+.3%} (보수) / '
                     f'{m["g_day_point"]:+.3%} (점추정) · 70달러 → 1년 {70 * (1 + m["g_day"]) ** 365:,.0f}달러 (보수) · '
                     f'최근 파라미터 {g["last_params"]}')
        L.append('  다음 단계: --universe --surrogate-n 20 (같은 날짜 순서로 섞은 가짜 코인 묶음과 비교) → --only 로 하나만 holdout 공개 → '
                 'prospective 추적.')
    else:
        L.append(f'▶ 사전 기준({crit})을 통과한 절차 없음 — 이 코인 묶음·비용에서 입증된 edge 없음.')
    L += _lab_declared_lines(res)
    L.append(lab_sharpe_line(res['rows']))
    L.append('※ 성과는 과거 train 으로 고른 파라미터를 보지 않은 다음 구간에 적용한 표본외 성과다. 순위 1위만 보고 고르면 그것도 선택이다.')
    return '\n'.join(L)


def lab_universe_surrogate_test(frames_by_symbol, n=20, seed0=100, status=None, **kw):
    """코인 묶음 탐색을 '같은 날짜 순서로 섞은 가짜 코인 묶음' n 개에서 반복 → 운으로 이만큼 나올 확률."""
    status = status or (lambda *a, **k: None)
    t_wall = time.time()
    status('실제 코인 묶음으로 탐색...', 'blue')
    real = lab_run_universe(frames_by_symbol, **kw)
    same, best = {}, []
    for k in range(int(n)):
        status(f'가짜 코인 묶음 {k + 1}/{n} 탐색...', 'blue')
        res = lab_run_universe(make_surrogate_frames(frames_by_symbol, seed=seed0 + k), **kw)
        _lab_luck_collect(res, same, best)
    rep_ = _lab_luck_report(real, same, best, n, kw.get('cost_mode', 'taker'), kw.get('only'), time.time() - t_wall,
                            title='코인 묶음 운의 크기')
    return dict(real=real, best=best, same={f'{a}:{b}': v for (a, b), v in same.items()}, report=rep_)


# =============================================================================
# [25] 연구 일지 — 패인과 교훈을 영구히 기록하고, 같은 실수는 기계가 막는다
# -----------------------------------------------------------------------------
#  · 실데이터로 시험한 모든 절차를 누적 기록 → DSR 은 '지금까지 시험한 전체 절차 수'로 보정 (실행마다 새로 세면 과신)
#  · holdout 시작일은 한 번 정하면 고정 (데이터 끝 기준으로 매번 다시 계산하면 날마다 봉인 구간이 새어 나온다)
#  · 반증된 가설은 같은 범위에서 다시 시험하지 않는다 (--retest "사유" 가 있어야 하고, 그것도 일지에 남는다)
#  · 처음 보는 구간 검증(--presample)은 가설마다 한 번만
#  · 일지 파일: 데이터 폴더의 {SYMBOL}_research_journal.json. 저장소 RESEARCH_LOG.md 와 같은 기록으로 시작한다.
# =============================================================================
RESEARCH_HOLDOUT_ANCHOR = '2026-01-01'      # 첫 Lab 실행(2026-10-02)의 봉인 시작보다 앞 → 본 적 없는 구간만 봉인된다
RESEARCH_HOLDOUT_CURRENT = '2026-10-04'     # P2 공개로 위 holdout 소진 → 이날부터 쌓이는 데이터가 새 holdout
RESEARCH_SEEN_FROM = '2021-11-27'           # 지금까지 '표본외 성과'로 본 가장 이른 날짜 (코인 묶음 실행). 그 전 BTC 성과는 미관측
RESEARCH_PRESAMPLE_ALPHA = 0.05             # 처음 보는 구간 검증의 유의수준 (가설 수로 나눈다 = Bonferroni)
RESEARCH_LESSONS = [
    ('L1', '한 시장에서 여러 전략 중 1등을 고르면 운이 같이 뽑힌다. 1등은 후보일 뿐이고, 고를 때 쓰지 않은 데이터'
           '(다른 시장·처음 보는 기간)에서 다시 확인하기 전에는 쓰지 않는다. — BTC 4h 체결강도 +0.459R(67건) → 알트 8개 +0.018R(130건)'),
    ('L2', '5m·15m 은 왕복 수수료가 1R 의 25~45% 라서 이 비용·수동 클릭 구조에서는 단타 우위가 없다. '
           '— 41개 절차 중 18개가 스스로 거래 거부, 지정가 진입으로도 같음'),
    ('L3', '차트 모양만 비교하는 패턴 반복은 비용을 넘지 못했다. — BTC 4h +0.024R(262건), 코인 묶음 4h −0.059R(150건)'),
    ('L4', '펀딩비 역추세와 평균회귀(z-score, RSI2)는 1h·4h 에서 근거가 없다. — 묶음 1h 펀딩 −0.206R, 평균회귀는 전 구간 쉼'),
    ('L5', '추세·돌파는 대부분 코인에서 평균R 이 양수지만 꼬리가 두꺼워 4년으로는 운과 구분되지 않는다. '
           '— 묶음 4h Keltner +0.245R(1404건, 8/9 코인), CI 하한 −0.009, p(최고 절차) 0.43, 가짜 최고 +0.674'),
    ('L6', '실행을 거듭할수록 시험한 절차가 쌓인다. DSR 은 누적 절차 수로 보정한다 (실행마다 새로 세면 과신).'),
    ('L7', 'holdout 시작일을 "데이터 끝 − 9개월"로 매번 다시 계산하면 봉인 구간이 날마다 새어 나온다 → 날짜 고정.'),
    ('L8', '반증된 가설을 새 이름·새 설정으로 다시 시험하지 않는다. 재시험은 사유와 함께 일지에 남긴다 (--retest).'),
    ('L9', 'holdout 은 선언한 가설에만, 한 번만 연다 (--only 없는 공개는 거부).'),
    ('L10', '증거가 없으면 거래당 위험 0 이 정답이다. 하루 복리 목표도 증거의 하한으로만 계산한다.'),
    ('L11', '같은 데이터에서 끝없이 찾으면 언젠가 반드시 가짜가 통과한다. 탐색은 계속해도 되지만 확인은 새 데이터'
            '(holdout·앞으로 쌓일 미래·다른 시장)로만 하고, 시험 수가 늘수록 기준도 올라간다 (L6).'),
    ('L12', '한 국면의 성과는 다른 국면에서 다시 확인해야 한다. — BTC 4h Keltner: 2019-08~2021-11(강세장 위주) +0.866R(58건), '
            '2022~2025 +0.070R(86건)'),
    ('L13', '확인된 전략도 국면이 바뀌면 죽는다. 실전 후보는 앞으로의 데이터로 계속 채점하고, 무너지면 멈춘다 (--prospective). '
            '— 4h Keltner: 처음 보는 구간 +0.866R → 2026 holdout 묶음 256건 −0.037R. BTC 자체 WFO 는 2026 내내 쉬어서 손실 0'),
    ('L14', '사전에 정한 판정 규칙은 결과를 본 뒤 바꾸지 않는다. 신뢰구간이 넓어 예전 값과 양립해도 규칙이 반증이면 반증이다. '
            '— 4h Keltner holdout CI [−0.451, +0.561]'),
    ('L15', '승률은 목표가 아니다. 하루 1% 복리 = 연환산 샤프 약 2.7(켈리)·3.1(반켈리) 전략을 그 레버리지로 굴리는 것이다. '
            '모든 보고서에 이 거리를 함께 적는다. — 지금까지 최고(4h Keltner, 반증됨)는 보수 기준 약 0.85'),
    ('L16', '판정과 실전은 BTC 가 1순위, ETH 가 2순위다. 알트는 신뢰성과 변동성 문제로 보조 증거일 뿐 매매 대상이 아니다. '
            '알트를 쓰는 검증은 실행 전에 그 이유를 밝히고, BTC·ETH 결과를 항상 같은 화면에 함께 보인다. — P3 에서 BTC 를 빼고 '
            '알트만 보여 준 실수'),
    ('L17', '여러 국면에서 모두 양수인 것만 후보로 남긴다. 한 국면(2020-21 강세장)에서만 강했던 추세 전략은 다른 국면에서 무너졌다. '
            '— 4h Keltner(P2)·4h 추세 합의(P4: BTC 2021-11~ 55건 −0.197R) 반증, BTC 4h 체결강도만 세 구간 모두 양수'),
    ('L18', '레버리지(계좌 위험)는 엣지를 만들지 못한다. 켈리 지점을 넘으면 성장은 멈추고 낙폭만 커진다. 가격 1% 고정 손절로 수수료 '
            '비중을 1R 의 14% 로 낮춰도 짧은 시간봉 신호는 비용을 넘지 못했다. — 1h Keltner(32개 중 최고, +0.081R): 계좌 1% ×1.23 '
            '낙폭 26% · 2% ×1.35 낙폭 46% · 3% ×1.34 낙폭 62%'),
]
RESEARCH_PREREG = [dict(
    id='P1', registered='2026-10-03', scope='btc_presample', pairs=['4h:keltner', '4h:flow', '4h:consensus'],
    rule='BTC 전체 이력(스팟 2018~ 포함)으로 롤링 WFO 를 돌리고, 표본외 중 지금까지 성과를 본 적 없는 구간'
         f'(표본외 시작 ~ {RESEARCH_SEEN_FROM} 전날)의 거래만으로 판정한다. 가설 3개 → 단측 {RESEARCH_PRESAMPLE_ALPHA / 3:.2%} '
         '하한(블록 부트스트랩). 거래 < 10 → 판정 불가 · 평균R ≤ 0 → 반증 · 하한 > 0 → 확인(holdout 후보) · 그 외 → 반증 안 됨',
    why='H1 4h Keltner+거래량 = 코인 묶음 1위 (8/9 코인 양수, CI 하한 −0.009). H2 4h 체결강도 = BTC 단독 1위 '
        '(알트 재현 불충분 → BTC 고유 효과인지 확인). H3 4h 추세 합의 = 꼬리 잡음을 줄이려고 만든 새 절차 (격자 없음, 시험 1회).'),
    dict(id='P2', registered='2026-10-03', scope='final', pairs=['4h:keltner'],
         rule=f'봉인 구간({RESEARCH_HOLDOUT_ANCHOR}~)을 단 한 번 연다. 같은 가설을 BTC(전체 이력 WFO)와 코인 묶음 9개(합산 WFO)로 '
              '동시에 판정한다. 반증: 묶음 holdout 평균R ≤ 0, 또는 BTC holdout 거래 ≥ 10 이고 평균R ≤ 0 · '
              '확인: 묶음 달묶음 90% CI 하한 > 0 이고 BTC 평균R > 0 · 그 외: 반증 안 됨. 공개하면 holdout 은 소진되고, '
              '그 뒤 쌓이는 데이터가 새 holdout(앞으로의 검증)이 된다.',
         why='P1-H1 확인 (처음 보는 BTC 구간 58건 +0.866R, 단측 1.67% 하한 +0.270). 다만 그 구간은 2020-21 강세장 위주였고 '
             '2022~2025 BTC 단독은 86건 +0.070R 로 약했다 (L12) → 지금 국면에서도 살아 있는지가 핵심이다. BTC 단독 9개월은 '
             '15건 안팎이라 검정력이 낮아 코인 묶음을 함께 본다.'),
    dict(id='P3', registered='2026-10-04', scope='alt_presample', pairs=['4h:flow', '4h:consensus'],
         rule='알트 8개의 스팟 이력(data.binance.vision 월별 4h, 상장~2021-12)으로 같은 WFO 를 돌리고, 표본외 중 '
              f'{RESEARCH_SEEN_FROM} 이전 거래만 코인을 합쳐 판정한다 (이 구간의 알트 성과는 어떤 시험도 본 적 없음). '
              '가설 2개 → 달 단위 묶음 부트스트랩 단측 2.5% 하한. 합산 거래 < 30 → 판정 불가 · 합산 평균R ≤ 0 → 반증 · '
              '하한 > 0 이고 체결 10건 이상 코인의 2/3 이상이 평균R > 0 → 확인 · 그 외 → 반증 안 됨',
         why='P1 에서 반증 안 된 두 가설(BTC 처음 보는 구간 4h 체결강도 22건 +0.239R, 4h 추세 합의 91건 +0.439R)을, '
             'BTC 와 다른 시장의 처음 보는 기간에서 확인한다. holdout 은 P2 로 소진되어 과거에 남은 새 데이터는 이것뿐이다.'),
    dict(id='P4', registered='2026-10-04', scope='regime', pairs=['4h:consensus'],
         rule=f'규칙이 고정된(2026-10-03) 4h 추세 합의를 BTC(1순위, 전체 이력 WFO)와 ETH(2순위, 스팟+선물 이력 WFO)에서 '
              f'{RESEARCH_SEEN_FROM} ~ {RESEARCH_HOLDOUT_CURRENT} 구간(2022 약세장·회복·2026 Keltner 가 죽은 구간) 거래로 판정한다. '
              'BTC 거래 < 20 → 판정 불가 · BTC 평균R ≤ 0 → 반증 · BTC 단측 5% 하한(블록 부트스트랩) > 0 이고 ETH 평균R > 0 → 확인 · '
              '그 외 → 반증 안 됨. 해마다 나눈 성적을 함께 보인다.',
         why='P1(BTC 91건 +0.439R)·P3(ETH 105건 +0.435R, 알트 7/7)은 모두 2019~2021 강세장 구간이다. 같은 구간에서 확인된 4h Keltner 가 '
             '2026 에 죽었으므로(L12·L13), 다른 국면에서 버티는지가 실전 여부를 가른다. 이 구간은 다른 전략들이 이미 본 데이터지만 '
             '이 규칙(격자 없음)으로는 한 번도 계산하지 않았다.')]
RESEARCH_TRACKING = [dict(pair='4h:flow', scope='btc', since=RESEARCH_HOLDOUT_CURRENT, why='P1-H2 반증 안 됨 → 앞으로의 데이터로 채점'),
                     dict(pair='4h:bollinger', scope='btc', since='2026-10-05',
                          why='Lab #4: 2022~2026 82건 +0.878R (2026 포함) → 앞으로의 데이터로 채점'),
                     ]                     # 4h 추세 합의(BTC·ETH)는 P4 에서 반증되어 추적 목록에서 뺐다 (기존 일지에서는 건너뛴다)
RESEARCH_HISTORY = [
    dict(date='2026-10-01', kind='audit', title='V611 객관 감사 → V612',
         summary='알려진 결함 전부 재현·수정, 새 결함 20개(N-01~N-20), null 이 약 1.4배 관대함을 측정, 미검증 신호 위험 25% 로 축소 '
                 '(AUDIT_V611_V612.md)'),
    dict(date='2026-10-02', kind='walkforward', title='생산엔진 15m 아날로그 워크포워드 (실데이터, null ON)',
         summary='19건, 평균 +0.018R, 90% CI [−0.252, +0.293], DSR 0.38 → E4 인증 실패', lessons=['L1']),
    dict(date='2026-10-02', kind='lab', title='Lab #1 — BTC 37개 절차 (taker)',
         summary='통과 0. 1위 4h 테이커 체결강도 67건 +0.459R CI 하한 +0.186 DSR 0.46, 2위 4h Bollinger CI 하한 +0.104. '
                 '가짜 BTC 1개 최고 4h Bollinger +0.134. 5m·15m 전부 쉼 또는 음수', lessons=['L2']),
    dict(date='2026-10-03', kind='lab', title='Lab #2 — 펀딩비 추가 39개 · 지정가 진입 · 가짜 BTC 20개',
         summary='펀딩비 1h CI 하한 −0.056, 4h −0.082. maker_entry 로도 5m·15m 실패. 4h 체결강도 p(최고 절차)=0.048 '
                 '(가짜 20개 최고 +0.160), 4h Bollinger 0.095', lessons=['L2', 'L4']),
    dict(date='2026-10-03', kind='lab', title='Lab #3 — 패턴 반복 추가 41개',
         summary='4h 패턴 반복 262건 +0.024R CI 하한 −0.024, 1h 24건 0R', lessons=['L3']),
    dict(date='2026-10-03', kind='cross', title='4h 체결강도 → 알트 8개 재현 (사전 선언)',
         summary='합산 130건 +0.018R, 달묶음 CI 하한 −0.203, 평균R>0 코인 3/6 → 불충분. BTC 값과 약 3.9 표준오차 차이 → '
                 'BTC 1등은 주로 선택 운', lessons=['L1']),
    dict(date='2026-10-03', kind='universe', title='코인 묶음 9개 · 22개 절차 · 가짜 묶음 20개',
         summary='통과 0. 1위 4h Keltner+거래량 1404건 +0.245R CI 하한 −0.009 DSR 0.67 8/9 코인, p(같은 절차) 0.048 · '
                 'p(최고 절차) 0.429. 가짜 최고 CI 하한 중앙 −0.025 · 90% +0.126 · 최고 +0.674. 평균회귀 전부 쉼, 펀딩 1h −0.206R, '
                 '패턴 반복 4h −0.059R, 상대강도 4h +0.014R', lessons=['L4', 'L5']),
    dict(date='2026-10-03', kind='bug', title='holdout 시작일이 실행마다 미끄러짐 (봉인 구간 누출)',
         summary=f'"데이터 끝 − 9개월"을 매번 다시 계산 → {RESEARCH_HOLDOUT_ANCHOR} 로 고정. 누적 시험 절차 104개를 DSR 에 반영',
         lessons=['L6', 'L7']),
    dict(date='2026-10-03', kind='prereg', title='사전등록 P1 (실행 전 기록)', summary=RESEARCH_PREREG[0]['rule'],
         lessons=['L1', 'L8']),
    dict(date='2026-10-03', kind='review', title='P1 결과 — 처음 보는 BTC 구간 (2019-08-24 ~ 2021-11-26, 스팟 2017-08~ 포함)',
         summary='H1 4h Keltner+거래량 58건 승률 43% 평균 +0.866R 단측 1.67% 하한 +0.270 PF 3.34 → 확인 (보수 하루복리 +0.102% @ '
                 '거래당 8%). H2 4h 체결강도 22건 +0.239R 하한 −0.316 → 반증 안 됨. H3 4h 추세 합의 91건 +0.439R 하한 −0.089 → '
                 '반증 안 됨. 주의: 이 구간은 2020-21 강세장 위주이고, 같은 전략의 BTC 2022~2025 는 86건 +0.070R 이었다 (L12).',
         lessons=['L1', 'L12']),
    dict(date='2026-10-03', kind='prereg', title='사전등록 P2 (실행 전 기록)', summary=RESEARCH_PREREG[1]['rule'],
         lessons=['L9', 'L11', 'L12']),
    dict(date='2026-10-04', kind='review', title='P2 결과 — 최종 검증 4h Keltner+거래량 (holdout 2026-01-01 ~ 2026-10-03)',
         summary='BTC(전체 이력): 표본외 137건 +0.467R, holdout 0건 (2024-25 train 에 근거가 없어 2026 내내 쉼 → 계좌 ×1.000). '
                 '코인 묶음 9개: 표본외 1396건 +0.238R, holdout 256건 −0.037R, 달묶음 90% CI [−0.451, +0.561], 승률 23%, PF 0.91 → '
                 '규칙상 반증. holdout 소진 → 2026-10-04 부터의 데이터가 새 holdout.',
         lessons=['L12', 'L13', 'L14']),
    dict(date='2026-10-04', kind='prereg', title='사전등록 P3 (실행 전 기록)', summary=RESEARCH_PREREG[2]['rule'],
         lessons=['L1', 'L11']),
    dict(date='2026-10-04', kind='review', title='목표를 숫자로: 하루 1% = 연환산 샤프 2.7 · 구조적 틈 분석 → 지정가 꼬리 잡기',
         summary='켈리 최대 하루 log 성장 = 일간 샤프²/2 → 하루 1% 는 연환산 샤프 2.7(반켈리 3.1). 방에서 쓸 수 있는 틈 중 '
                 '짧은 시간봉의 비용 문제(L2)를 정면으로 피하는 것: 강제청산 꼬리에 미리 걸어 둔 지정가로 유동성 공급 '
                 '(진입·익절 지정가 0.02%, 하루 1~2번 수동 주문). 합성 검증: 심은 청산 꼬리 → 평균 +0.41R·승률 73%·샤프 2.8 로 '
                 '통과, 무작위 걷기 → −0.07R 미통과. 실데이터 탐색은 --lab --wick',
         lessons=['L2', 'L15']),
    dict(date='2026-10-04', kind='review', title='P3 결과 — 처음 보는 알트 구간 (스팟 이력, 2019-08 ~ 2021-11)',
         summary='4h 추세 합의: 합산 471건 +0.461R, 단측 2.5% 하한 +0.175, 평균R>0 코인 7/7 → 확인 (ETH 105건 +0.435R, BNB 101건 '
                 '+0.733R, XRP 44건, ADA 70건, DOGE 15건, LTC 93건, LINK 43건). 4h 체결강도: 92건 +0.345R, 하한 −0.056, 10건 이상 '
                 '코인 1/2 → 반증 안 됨 (ETH 54건 +0.661R 외에는 거래가 적음). BTC 참고(P1, 같은 구간): 추세 합의 91건 +0.439R, '
                 '체결강도 22건 +0.239R. 실수: 알트만 보여 주고 BTC 를 같은 화면에 두지 않았다 → L16. 주의: 모두 2019~2021 강세장.',
         lessons=['L12', 'L16']),
    dict(date='2026-10-04', kind='prereg', title='사전등록 P4 (실행 전 기록)', summary=RESEARCH_PREREG[3]['rule'],
         lessons=['L12', 'L13', 'L16']),
    dict(date='2026-10-05', kind='review', title='P4 결과 · 지정가 꼬리 잡기 · 시간대 쏠림 · Lab #4 (2026 포함)',
         summary='P4 4h 추세 합의 (2021-11-27~2026-10-03): BTC 55건 −0.197R 하한 −0.335, ETH 116건 +0.003R → 반증. '
                 '지정가 꼬리 잡기(BTC 1분봉): 81건 승률 69% 평균 이익 +0.43R/손실 −1.08R → −0.035R, CI [−0.142, +0.076] → 근거 없음 '
                 '(높은 승률·음의 기대값). 1h 시간대 쏠림: 전 구간 쉼 → 근거 없음. Lab #4 (43개 절차, 표본외에 2026 포함): '
                 '4h Bollinger 82건 +0.878R CI 하한 +0.302 · 4h 체결강도 91건 +0.459R CI 하한 +0.144, 샤프 0.85(하루 1% 필요량의 '
                 '10%) — 둘 다 DSR(누적 114) 0.14 이하. BTC 4h 체결강도는 2019-21 +0.239R(22건) · 2022-25 +0.459R(67건) · '
                 '2026 약 +0.46R(24건)로 세 구간 모두 양수.',
         lessons=['L15', 'L17']),
    dict(date='2026-10-05', kind='idea', title='사용자 제안: 짧은 시간봉 · 가격 1% 고정 손절 · 레버리지 2~3배 (계좌 2~3%) · 이득 극대화',
         summary='레버리지는 엣지를 바꾸지 않고 손절 1회에 잃는 계좌 비율만 정한다. 다만 가격 1% 고정 손절은 짧은 시간봉의 비용 비중을 '
                 '1R 의 25~45%(ATR 2~4배 손절)에서 14% 로 낮추고, 70달러 시드에서 BTC 최소주문(100 USDT)의 손절 1회 손실을 약 1.4% 로 '
                 '줄인다 → 시험할 가치가 있다. 이득 극대화 = 2R·3R 익절 또는 신호 청산 중 train 이 고름. 계좌 위험 1%·2%·3% 별 '
                 '표본외 결과(배수·하루 복리·최대 낙폭·최장 연속 손실)를 함께 본다. 탐색이므로 새 절차로 누적 집계하고, 통과하면 '
                 '사전등록 후 앞으로의 데이터로 확인한다. 실행: --lab --stop-pct 1',
         lessons=['L2', 'L10', 'L15']),
    dict(date='2026-10-05', kind='review', title='가격 1% 고정 손절 결과 (5m/15m/1h, 32개 절차) · 날짜 섞은 BTC 20개 비교',
         summary='통과 0. 최고 1h Keltner+거래량 328건 승률 33% +0.081R CI 하한 −0.085, 샤프 0.36(하루 1% 필요량의 2%). 계좌 위험 1%: '
                 '×1.23(낙폭 26%) · 2%: ×1.35(46%) · 3%: ×1.34(62%) — 2배를 넘기면 성장은 멈추고 낙폭만 커짐. 15m 변동성 돌파 443건 '
                 '+0.023R · 15m Bollinger +0.003R · 5m 변동성 돌파 −0.036R, 나머지는 쉬거나 음수. 날짜 섞은 BTC 20개: 최고 CI 하한 '
                 '중앙 −0.136 · 최고 +0.175, 1h Keltner p(최고 절차) 0.238. 15m·5m 변동성 돌파는 같은 절차의 섞은 차트 20개를 모두 '
                 '이겼지만(p 0.048) 실제도 손실 근처 → 실제 차트의 구조는 있으나 비용을 넘지 못함. 남은 지렛대 = 실제 수수료(--fees).',
         lessons=['L2', 'L15', 'L18']),
    dict(date='2026-10-05', kind='idea', title='사용자 제안: 실제 정답을 먼저 정하고, 그 정답 앞에 있던 단서를 배워 확률이 가장 높은 곳만 진입',
         summary='정답 = 각 봉 마감에 들어갔다면 +2%(익절 2R)가 −1%(손절)보다 24봉 안에 먼저 왔는가 (같은 봉이면 손절, 롱·숏 따로). '
                 '단서 18개 = 그 시점에 이미 알 수 있던 값(수익률·변동성·이동평균 거리·Bollinger·Donchian·테이커 체결강도·거래량·펀딩비 '
                 '백분위·시각·주말). 직전 2년의 (단서 → 정답)으로 로지스틱 회귀를 배워 다음 3개월에만 적용, 정답 구간이 test·holdout 과 '
                 '겹치는 표본은 지움. 진입 = train 확률 상위 5/10/20% 중 train 이 고른 문턱. 판정 기준은 실행 전에 고정: 체결 ≥ 100, '
                 '달묶음 CI 하한 > 0, DSR(누적 절차) ≥ 0.9 → 통과해도 이미 본 기간이므로 사전등록 후 앞으로의 데이터로 확인. '
                 '분위표(예측 확률 10분위별 실제 승률)로 "확률이 높다고 본 곳이 정말 더 이겼나"를 따로 본다. 실행: --lab --oracle',
         lessons=['L1', 'L6', 'L11', 'L15']),
    dict(date='2026-10-05', kind='bug', title='--oracle 첫 실행이 옛 파일로 돌아 일반 Lab(43개 절차)이 대신 실행됨',
         summary='옛 파일은 모르는 옵션(--oracle)을 조용히 무시하고 기본 Lab 을 돌렸다 → 결과가 이전 Lab #4 와 같았고 새 절차는 없음. '
                 '사용자는 그것을 정답 단서 학습 결과로 읽을 뻔했다. 고친 것: Lab 은 모르는 옵션이 있으면 아무것도 실행하지 않고 거절, '
                 '모든 Lab 출력 첫 줄에 파일 빌드를 표시.'),
    dict(date='2026-10-05', kind='idea', title='사용자 질문: 끝머리(움직임이 어디까지 가는지)도 예측하면 손익비로 이득을 볼 수 있지 않나',
         summary='방향 없는 차트에서 +kR 이 −1R 보다 먼저 올 확률은 1/(1+k) 이고, 손익분기 승률은 (1+비용R)/(1+k) → 목표를 멀리 두는 '
                 '것만으로는 언제나 수수료만큼 손해. 이득은 "큰 움직임이 1/(1+k) 보다 자주 오는 시점"을 단서로 미리 알 때만 생긴다. '
                 '4h Bollinger(승률 32%, +0.878R → 이긴 거래 평균 약 4~5R)가 이미 그런 구조. 시험: 같은 단서·손절·보유에서 익절 목표만 '
                 '2/3/5R 로 바꿔 상위 10% 실제 승률 vs 손익분기를 비교(끝머리 지도). 목표마다 새 절차로 누적 집계. '
                 '실행: --lab --oracle --tp 2,3,5 (4h 는 --tfs 4h --stop-pct 2 --hold 60)',
         lessons=['L6', 'L15', 'L18']),
]


def _research_seed_keys():
    """지금까지 실데이터로 시험한 절차 (2026-10-03 기준 104개). 이후 전략군이 바뀌어도 이 목록은 바뀌지 않게 직접 적는다."""
    scope_tfs = {'session': ('5m', '15m'), 'volbreak': ('5m', '15m', '1h'), 'funding': ('1h', '4h'), 'analog': ('1h', '4h')}
    base10 = ['tsmom', 'ema', 'donchian', 'bollinger', 'keltner', 'volbreak', 'session', 'flow', 'meanrev', 'rsi2']
    keys = ['wf|15m:analog_engine|taker', 'cross|4h:flow|taker']

    def add(scope, fams, cost, tfs=('5m', '15m', '1h', '4h'), skip=()):
        for f in fams:
            for tf in scope_tfs.get(f, tfs):
                if tf in tfs and (tf, f) not in skip:
                    keys.append(f'{scope}|{tf}:{f}|{cost}')
    add('btc', base10 + ['funding', 'analog'], 'taker')                       # Lab #1~#3: 37 + 2 + 2
    add('btc', base10 + ['funding'], 'maker_entry')                           # 지정가 진입 시나리오: 39
    add('universe', ['tsmom', 'ema', 'donchian', 'bollinger', 'keltner', 'volbreak', 'flow', 'meanrev', 'rsi2', 'funding',
                     'analog', 'xsmom'], 'taker', tfs=('1h', '4h'), skip={('1h', 'analog')})   # 코인 묶음: 22
    keys += [f'btc_presample|4h:{f}|taker' for f in ('keltner', 'flow', 'consensus')]          # P1: 3 (누적 107)
    keys.append('final|4h:keltner|taker')                                                      # P2: 1 (누적 108)
    keys += [f'alt_presample|4h:{f}|taker' for f in ('flow', 'consensus')]                     # P3: 2 (누적 110)
    keys += ['regime|4h:consensus|taker', 'btc|1m:wick|maker', 'btc|1h:tod|taker',
             'btc|4h:consensus|taker']                                                       # P4·꼬리·시간대·Lab #4 (누적 114)
    fixed = {'5m': base10, '15m': base10,                                                     # 가격 1% 고정 손절 (누적 146)
             '1h': [f for f in base10 if f != 'session'] + ['funding', 'analog', 'tod']}
    keys += [f'btc|{tf}:{f}|taker|stop1' for tf, fams in fixed.items() for f in fams
             if tf in {'session': ('5m', '15m'), 'volbreak': ('5m', '15m', '1h')}.get(f, ('5m', '15m', '1h'))]
    return sorted(set(keys))


def _research_seed_status():
    st = {}

    def put(key, state, why, date='2026-10-03'):
        st[key] = dict(state=state, why=why, date=date)
    put('wf|15m:analog_engine', 'refuted', '15m 워크포워드 E4 실패: 19건 +0.018R, DSR 0.38', '2026-10-02')
    for f in ['tsmom', 'ema', 'donchian', 'bollinger', 'keltner', 'volbreak', 'session', 'flow', 'meanrev', 'rsi2']:
        for tf in ('5m', '15m'):
            put(f'btc|{tf}:{f}', 'no_evidence', 'L2: 수수료가 1R 의 25~45% — 음수이거나 스스로 거래 거부 (taker·지정가 모두)')
    for scope in ('btc', 'universe'):
        for tf in ('1h', '4h'):
            put(f'{scope}|{tf}:meanrev', 'no_evidence', 'L4: 전 구간 쉼 (train 근거 없음)')
            put(f'{scope}|{tf}:rsi2', 'no_evidence', 'L4: 전 구간 쉼 (train 근거 없음)')
            put(f'{scope}|{tf}:funding', 'no_evidence', 'L4: BTC 1h/4h CI 하한 음수, 묶음 1h −0.206R, 4h 쉼')
    put('btc|1h:analog', 'no_evidence', 'L3: 24건 0R')
    put('btc|4h:analog', 'no_evidence', 'L3: 262건 +0.024R, CI 하한 −0.024')
    put('universe|4h:analog', 'no_evidence', 'L3: 150건 −0.059R')
    put('universe|1h:xsmom', 'no_evidence', '861건 −0.053R, 2/9 코인')
    put('universe|4h:xsmom', 'no_evidence', '557건 +0.014R, CI 하한 −0.090')
    put('btc|4h:flow', 'candidate', 'BTC 1위 +0.459R(67건), p(최고)=0.048 · 알트 재현 불충분(+0.018R) → P1-H2')
    put('cross|4h:flow', 'inconclusive', '알트 8개 합산 130건 +0.018R, 3/6 코인 → 불충분')
    put('btc|4h:bollinger', 'candidate', '+0.702R(70건) CI 하한 +0.104, p(최고)=0.095')
    put('universe|4h:keltner', 'candidate', '1404건 +0.245R, 8/9 코인, CI 하한 −0.009, p(최고) 0.43 → P1-H1')
    put('universe|4h:ema', 'candidate', '785건 +0.437R, 6/9 코인, CI 하한 −0.055')
    put('btc_presample|4h:keltner', 'confirmed', 'P1-H1: 처음 보는 BTC 구간 58건 평균R +0.866 하한 +0.270 → 확인')
    put('btc_presample|4h:flow', 'not_refuted', 'P1-H2: 처음 보는 BTC 구간 22건 평균R +0.239 하한 −0.316 → 반증 안 됨')
    put('btc_presample|4h:consensus', 'not_refuted', 'P1-H3: 처음 보는 BTC 구간 91건 평균R +0.439 하한 −0.089 → 반증 안 됨')
    for sc in ('final', 'btc', 'universe'):
        put(f'{sc}|4h:keltner', 'refuted', 'P2: holdout BTC 0건(쉼) · 묶음 256건 −0.037R 하한 −0.451 → 반증 — 지금 국면에서는 '
                                          '살아 있지 않다', '2026-10-04')
    put('alt_presample|4h:consensus', 'confirmed', 'P3: 처음 보는 알트 구간 471건 평균R +0.461 하한 +0.175, 7/7 코인 → 확인',
        '2026-10-04')
    put('alt_presample|4h:flow', 'not_refuted', 'P3: 처음 보는 알트 구간 92건 평균R +0.345 하한 −0.056, 1/2 코인 → 반증 안 됨',
        '2026-10-04')
    for sc in ('regime', 'btc'):
        put(f'{sc}|4h:consensus', 'refuted', 'P4: BTC 55건 −0.197R 하한 −0.335 · ETH 116건 +0.003R → 반증 — BTC 에서 다른 '
                                            '국면을 버티지 못했다', '2026-10-05')
    put('btc|1m:wick', 'no_evidence', '81건 승률 69% · 평균 −0.035R, CI [−0.142, +0.076] — 높은 승률, 음의 기대값', '2026-10-05')
    put('btc|1h:tod', 'no_evidence', '전 구간 쉼 (train 근거 없음)', '2026-10-05')
    put('btc_stop1|short:all', 'no_evidence', '가격 1% 고정 손절 5m/15m/1h 32개: 통과 0, 최고 1h Keltner +0.081R CI 하한 −0.085 · '
                                              'p(최고) 0.238', '2026-10-05')
    put('btc|4h:flow', 'candidate', '세 구간 모두 양수: 2019-21 +0.239R(22) · 2022-25 +0.459R(67) · 2026 약 +0.46R(24). '
                                    '샤프 0.85, DSR(누적) 0.14 → 앞으로의 검증 중', '2026-10-05')
    put('btc|4h:bollinger', 'candidate', '2022~2026 82건 +0.878R CI 하한 +0.302 (2026 포함), DSR(누적) 0.13 · 묶음 9개 +0.215R '
                                         '→ 앞으로의 검증 중', '2026-10-05')
    return st


RESEARCH_STATE_KO = {'refuted': '반증', 'no_evidence': '근거 없음', 'candidate': '후보', 'inconclusive': '불충분',
                     'preregistered': '사전등록(대기)', 'not_refuted': '반증 안 됨', 'confirmed': '확인',
                     'holdout_passed': 'holdout 통과'}


def research_seed():
    return dict(version=1, symbol=SYMBOL, created=_iso_now(), holdout_anchor=RESEARCH_HOLDOUT_CURRENT,
                holdout_history=[dict(start=RESEARCH_HOLDOUT_ANCHOR, set='2026-10-03',
                                      why='L7 — 미끄러지던 봉인 시작일을 그동안의 모든 봉인 시작보다 앞 날짜로 고정'),
                                 dict(start=RESEARCH_HOLDOUT_CURRENT, set=RESEARCH_HOLDOUT_CURRENT,
                                      why="['4h:keltner'] 공개(P2)로 이전 holdout(2026-01-01~) 소진")],
                seen_oos_from=RESEARCH_SEEN_FROM, procedures=_research_seed_keys(), status=_research_seed_status(),
                prereg=copy.deepcopy(RESEARCH_PREREG), entries=copy.deepcopy(RESEARCH_HISTORY),
                tracking=copy.deepcopy(RESEARCH_TRACKING))


def _research_sync(d, seed):
    """코드에 새로 들어온 사전등록·분석 기록을 기존 일지에 덧붙인다 (지우거나 고치지 않음). 바뀐 게 있으면 True."""
    changed = False
    have = {p.get('id') for p in d.get('prereg', [])}
    for p in seed['prereg']:
        if p['id'] not in have:
            d['prereg'].append(p)
            for pair in p['pairs']:
                key = f'{p["scope"]}|{pair}'
                if key not in d['status']:
                    d['status'][key] = seed['status'].get(key, dict(state='preregistered', why=f'{p["id"]}: 실행 전 등록',
                                                                    date=p['registered']))
            changed = True
    have_t = {(t.get('scope'), t.get('pair')) for t in d.get('tracking', [])}
    for t in seed.get('tracking', []):
        if (t['scope'], t['pair']) not in have_t:
            d.setdefault('tracking', []).append(t)
            changed = True
    seen = {(e.get('date', '')[:10], e.get('title')) for e in d.get('entries', [])}
    for e in seed['entries']:
        if (e['date'][:10], e['title']) not in seen:
            d['entries'].append(dict(e, synced_from_code=True))
            changed = True
    return changed


class ResearchJournal:
    """연구 일지 (JSON 한 파일, 원자적 저장). 없으면 RESEARCH_HISTORY 로 시작한다. 손상되면 보관 후 다시 시작."""

    def __init__(self, path=None):
        self.path = path or Paths.research_journal()
        self.d = None

    @classmethod
    def load(cls, path=None):
        j = cls(path)
        if os.path.exists(j.path):
            try:
                with open(j.path, encoding='utf-8') as f:
                    d = json.load(f)
                if not isinstance(d, dict) or not isinstance(d.get('procedures'), list):
                    raise ValueError('형식 오류')
                seed = research_seed()
                for k, v in seed.items():
                    d.setdefault(k, v)
                if _research_sync(d, seed):
                    j.d = d
                    j.save()
                j.d = d
                return j
            except Exception as e:
                bak = f'{j.path}.corrupt-{utcnow():%Y%m%d%H%M%S}'
                try:
                    os.replace(j.path, bak)
                except Exception:
                    pass
                HEALTH.set('journal', 'WARN', f'연구 일지 손상({e}) → {bak} 로 보관하고 기본 기록으로 다시 시작')
        j.d = research_seed()
        j.save()
        return j

    def save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(json_safe(self.d), f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    @property
    def anchor(self):
        return pd.Timestamp(self.d['holdout_anchor'])

    @property
    def seen_from(self):
        return pd.Timestamp(self.d['seen_oos_from'])

    def n_trials(self, keys=()):
        return len(set(self.d['procedures']) | set(keys))

    def state(self, key):
        return (self.d['status'].get(key) or {}).get('state')

    def set_status(self, key, state, why):
        self.d['status'][key] = dict(state=state, why=why, date=f'{utcnow():%Y-%m-%d}')

    def check(self, scope, pairs, retest=None, once=False):
        """선언 가설 검사 → (막을 이유들, 경고들). 반증된 가설, 그리고 once=True 인데 이미 판정된 가설은 막는다."""
        block, warn = [], []
        for tf, fam in (pairs or []):
            key = f'{scope}|{tf}:{fam}'
            s = self.d['status'].get(key) or {}
            st = s.get('state')
            if st == 'refuted' or (once and st not in (None, 'preregistered')):
                (warn if retest else block).append(f'{tf}:{fam} — 일지상 {RESEARCH_STATE_KO.get(st, st)} ({s.get("why", "")})')
            elif st == 'no_evidence':
                warn.append(f'{tf}:{fam} — 일지상 근거 없음 ({s.get("why", "")})')
        return block, warn

    def record(self, kind, keys=(), **info):
        self.d['procedures'] = sorted(set(self.d['procedures']) | set(keys))
        self.d['entries'].append(dict(date=f'{utcnow():%Y-%m-%d %H:%M}', kind=kind, n_trials=len(self.d['procedures']),
                                      **json_safe(info)))
        self.save()

    def consume_holdout(self, declared, verdicts=None):
        """holdout 을 열면 그 구간은 '본 데이터'가 된다 → 지금부터의 데이터가 새 holdout (앞으로만 움직인다)."""
        new = f'{utcnow():%Y-%m-%d}'
        self.d['holdout_history'].append(dict(start=new, set=new, why=f'{declared} 공개로 이전 holdout({self.d["holdout_anchor"]}~) 소진',
                                              verdicts=verdicts))
        self.d['holdout_anchor'] = new

    def banner(self):
        cnt = {}
        for v in self.d['status'].values():
            cnt[v.get('state')] = cnt.get(v.get('state'), 0) + 1
        return (f'[연구 일지] 실데이터로 시험한 절차 누적 {len(self.d["procedures"])}개 → DSR 은 이 수로 보정 · '
                f'holdout 고정 시작 {self.d["holdout_anchor"]} · 반증 {cnt.get("refuted", 0)} · 근거 없음 '
                f'{cnt.get("no_evidence", 0)} · 후보 {cnt.get("candidate", 0)} · 사전등록 대기 {cnt.get("preregistered", 0)} '
                f'(자세히: --journal)')

    def text(self):
        L = [f'━━━ PatternEdge 연구 일지 · {self.d.get("symbol", SYMBOL)} · {self.path} ━━━', self.banner(), '',
             '■ 교훈 (같은 실수를 반복하지 않기 위한 규칙 — 기계가 강제하는 것은 L6·L7·L8·L9·L10)']
        L += [f'  {k}  {v}' for k, v in RESEARCH_LESSONS]
        L += ['', '■ 사전등록']
        for p in self.d.get('prereg', []):
            L.append(f'  {p["id"]} ({p["registered"]}, {p["scope"]}): {", ".join(p["pairs"])}')
            L.append(f'     규칙: {p["rule"]}')
            L.append(f'     이유: {p["why"]}')
        L += ['', '■ 가설 상태']
        order = ['confirmed', 'holdout_passed', 'not_refuted', 'preregistered', 'candidate', 'inconclusive', 'refuted',
                 'no_evidence']
        items = sorted(self.d['status'].items(), key=lambda kv: (order.index(kv[1].get('state'))
                                                                 if kv[1].get('state') in order else 99, kv[0]))
        for k, v in items:
            L.append(f'  [{RESEARCH_STATE_KO.get(v.get("state"), v.get("state"))}] {k} — {v.get("why", "")} ({v.get("date", "")})')
        L += ['', '■ holdout 기록'] + [f'  {h["start"]} 부터 (설정 {h["set"]}): {h["why"]}' for h in self.d['holdout_history']]
        L += ['', '■ 연구 기록 (오래된 순)']
        for e in self.d['entries']:
            head = f'  {e.get("date", "")} [{e.get("kind", "")}] {e.get("title", "")}'
            L.append(head + (f' · 누적 절차 {e["n_trials"]}' if 'n_trials' in e else ''))
            if e.get('summary'):
                L.append(f'     {e["summary"]}')
            for t in e.get('top', [])[:5]:
                L.append(f'     - {t}')
        return '\n'.join(L)

    def export_md(self, path=None):
        path = path or Paths.research_md()
        with open(path, 'w', encoding='utf-8') as f:
            f.write('```\n' + self.text() + '\n```\n')
        return path


def lab_planned_keys(scope, tfs, families, cost_mode, pairs=None, universe=False):
    """이번 실행이 시험할 절차 → 일지 키 (scope|tf:family|cost)."""
    out = []
    for tf in tfs:
        for fam in families:
            if tf not in LAB_FAMILY_TFS.get(fam, LAB_TFS) or (universe and (tf, fam) in LAB_UNIVERSE_SKIP):
                continue
            if pairs is not None and (tf, fam) not in pairs:
                continue
            out.append(f'{scope}|{tf}:{fam}|{cost_mode}')
    return out


def lab_top_lines(res, k=5):
    out = []
    for r in [r for r in res['rows'] if r['oos']['n'] > 0][:k]:
        m = r['oos']
        coins = f' · 코인 {r["pos"]}/{r["tot"]}' if 'pos' in r else ''
        out.append(f'{r["tf"]}:{r["family"]} {m["n"]}건 평균R {np.nan_to_num(m["mean_r"]):+.3f} CI하한 '
                   f'{np.nan_to_num(m["ci_lo"]):+.3f} DSR {m["dsr"]:.2f} 하루복리 {m.get("g_day", 0.0):+.3%}{coins}')
    return out


def research_apply_presample(journal, verdicts):
    """처음 보는 구간 판정 → 일지 상태. 반증이면 BTC 범위의 같은 가설도 반증. 거래 0건은 시험이 아니므로 등록 유지."""
    for v in verdicts:
        if v['n'] <= 0:
            continue
        st = {'반증': 'refuted', '확인': 'confirmed', '반증 안 됨': 'not_refuted'}.get(v['verdict'].split(' —')[0], 'inconclusive')
        why = f'처음 보는 BTC 구간 {v["n"]}건 평균R {np.nan_to_num(v["mean_r"]):+.3f} → {v["verdict"]}'
        journal.set_status(f'btc_presample|{v["pair"]}', st, why)
        if st == 'refuted':
            journal.set_status(f'btc|{v["pair"]}', 'refuted', why)


def lab_presample_verdict(n, mean_r, lo):
    if n < 10:
        return '판정 불가 (거래 < 10)'
    if not mean_r > 0:
        return '반증 — 처음 보는 BTC 구간에서 평균R ≤ 0'
    if lo > 0:
        return '확인 — holdout 공개 후보'
    return '반증 안 됨 — 방향은 맞지만 입증은 아니다'


def lab_presample(base1m, pairs, seen_from=RESEARCH_SEEN_FROM, funding=None, cost_mode='taker', n_trials_declared=None,
                  status=None, alpha=RESEARCH_PRESAMPLE_ALPHA):
    """
    BTC 전체 이력(스팟 2018~ 포함)으로 선언 가설을 롤링 WFO 하고, 표본외 중 지금까지 성과를 본 적 없는 구간
    [표본외 시작, seen_from) 의 거래만으로 판정한다. seen_from 이후(이미 본 구간과 holdout)는 계산만 하고 보여 주지 않는다.
    판정 규칙은 lab_presample_verdict 로 고정, 하한은 가설 수로 나눈 유의수준 (Bonferroni).
    """
    pairs = lab_pairs(pairs)
    if not pairs:
        raise ValueError('처음 보는 구간 검증은 선언한 가설에만 씁니다')
    res = lab_run(base1m, only=pairs, futures_only=False, holdout_start=seen_from, cost_mode=cost_mode, funding=funding,
                  n_trials_declared=n_trials_declared, status=status)
    q = alpha / len(pairs)
    verdicts = []
    L = [f'━━━ 처음 보는 BTC 구간 검증 · 가설 {len(pairs)}개 · {res["data"]} ━━━',
         f'표본외 중 성과를 한 번도 본 적 없는 구간(~{str(seen_from)[:10]} 전날)의 거래만 판정. 그 뒤(이미 본 구간·holdout)는 보이지 않는다.',
         f'판정 규칙(사전 고정): 거래 < 10 → 판정 불가 · 평균R ≤ 0 → 반증 · 단측 {q:.2%} 하한(가설 {len(pairs)}개 Bonferroni) > 0 → 확인 · '
         f'그 외 → 반증 안 됨',
         '─' * 100,
         f'{"TF":<5}{"전략군":<16}{"구간":>24}{"체결":>6}{"승률":>6}{"평균R":>8}{f"{q:.1%}하한":>9}{"PF":>6}'
         f'{"보수 하루복리@위험":>18}  판정']
    for tf, fam in pairs:
        r = next((x for x in res['rows'] if (x['tf'], x['family']) == (tf, fam)), None)
        R = np.asarray(r['oos_r'] if r else [], dtype=np.float64)
        lo = float(np.quantile(stationary_block_bootstrap(R, n_boot=4000, mean_block=5.0, rng=np.random.default_rng(7)), q)) \
            if len(R) >= 10 else float('nan')
        mean = float(R.mean()) if len(R) else float('nan')
        v = lab_presample_verdict(len(R), mean, lo)
        m = r['oos'] if r else _lab_metrics([], 1.0)
        span = f'{(r or {}).get("oos_start", "")[:10]}~{str(seen_from)[:10]}'
        L.append(f'{tf:<5}{LAB_FAMILY_KO[fam]:<16}{span:>24}{len(R):>6}{np.nan_to_num(m["win"]):>6.0%}'
                 f'{np.nan_to_num(mean):>+8.3f}{np.nan_to_num(lo):>+9.3f}{np.nan_to_num(m["pf"]):>6.2f}'
                 f'{m.get("g_day", 0.0):>+12.3%}@{m.get("f_star", 0.0):<6.1%}  {v}')
        verdicts.append(dict(pair=f'{tf}:{fam}', n=int(len(R)), mean_r=mean, lo=lo, verdict=v,
                             oos_start=(r or {}).get('oos_start')))
    L.append('─' * 100)
    if all(x['n'] == 0 for x in verdicts):
        L.append('※ 처음 보는 구간에 거래가 없습니다 — 스팟 이력(2018~)이 없거나 표본외 시작이 이미 본 구간 이후입니다.')
    L.append('※ 거래 수가 적으면 "확인"은 어렵고 "반증"이 더 강한 신호다. 반증되면 일지에 반증으로 남고 같은 범위에서 다시 시험하지 않는다.')
    res['presample'] = verdicts
    res['report'] = '\n'.join(L)
    return res


def lab_final_verdict(b, u):
    """사전등록 P2 의 판정 규칙. b = BTC holdout 지표, u = 코인 묶음 holdout 지표 (없으면 None)."""
    if u is None:
        return lab_holdout_verdict(b)
    if u['n'] == 0 and b['n'] == 0:
        return '판정 불가 (holdout 거래 없음)'
    if (u['n'] > 0 and not u['mean_r'] > 0) or (b['n'] >= 10 and not b['mean_r'] > 0):
        return '반증 — 지금 국면에서는 살아 있지 않다'
    if u['n'] > 0 and u['ci_lo'] > 0 and b['mean_r'] > 0:
        return '확인 — 앞으로의 데이터(새 holdout)로 계속 추적하며 소액 실전 단계로'
    return '반증 안 됨 — 방향은 맞지만 입증은 아니다, 앞으로의 데이터로 계속 추적'


def lab_final_test(base1m, frames_by_symbol, pair, holdout_start, funding=None, funding_by_symbol=None,
                   cost_mode='taker', n_trials_declared=None, status=None):
    """
    사전등록 P2: 가설 하나를 봉인 구간에서 BTC(전체 이력 WFO)와 코인 묶음(합산 WFO)으로 동시에 판정한다.
    holdout 은 이 한 번으로 소진된다. 표본외 보수 위험(f*)으로 걸었다면 holdout 동안 계좌가 몇 배가 됐는지도 보인다.
    """
    pairs = lab_pairs(pair)
    if not pairs or len(pairs) != 1:
        raise ValueError('최종 검증은 가설 하나만 (예: --final 4h:keltner)')
    tf, fam = pairs[0]
    btc = lab_run(base1m, only=pairs, futures_only=False, holdout_start=holdout_start, reveal_holdout=True,
                  cost_mode=cost_mode, funding=funding, n_trials_declared=n_trials_declared, status=status)
    uni = None
    if frames_by_symbol and sum(1 for fr in frames_by_symbol.values() if fr and tf in fr and fr[tf] is not None) >= 2:
        uni = lab_run_universe(frames_by_symbol, tfs=(tf,), only=pairs, holdout_start=holdout_start, reveal_holdout=True,
                               cost_mode=cost_mode, funding_by_symbol=funding_by_symbol,
                               n_trials_declared=n_trials_declared, status=status)
    rb = next((r for r in btc['rows'] if (r['tf'], r['family']) == (tf, fam)), None)
    ru = next((r for r in (uni or {}).get('rows', []) if (r['tf'], r['family']) == (tf, fam)), None) if uni else None
    empty = _lab_metrics([], 1.0)
    b, u = (rb or {}).get('holdout', empty), (ru['holdout'] if ru else (empty if uni else None))
    verdict = lab_final_verdict(b, u)

    def growth(r):
        if not r or not r['oos'].get('f_star'):
            return '표본외 증거 하한이 0 이하 → 거래당 위험 0 (걸지 않음)'
        f = r['oos']['f_star']
        R = np.asarray(r.get('hold_r_list', []), dtype=np.float64)
        mult = float(np.prod(1.0 + f * np.clip(R, -50, 50))) if len(R) else 1.0
        return f'표본외 보수 위험 {f:.1%} 로 걸었다면 holdout 동안 계좌 ×{mult:.3f}'
    L = [f'━━━ 최종 검증 (사전등록 P2) · {tf} {LAB_FAMILY_KO[fam]} · holdout {str(holdout_start)[:10]} ~ ━━━',
         '봉인 구간을 단 한 번 연다. 판정 규칙(사전 고정): 반증 = 묶음 holdout 평균R ≤ 0 또는 BTC holdout 거래 ≥ 10 이고 평균R ≤ 0 · '
         '확인 = 묶음 달묶음 90% CI 하한 > 0 이고 BTC 평균R > 0 · 그 외 = 반증 안 됨',
         '─' * 100,
         f'{"범위":<22}{"표본외 체결":>10}{"표본외 평균R":>12}{"holdout 체결":>12}{"holdout 평균R":>13}{"90% CI":>20}{"승률":>6}{"PF":>6}']
    for name, r, m in (('BTC (전체 이력)', rb, b), (f'코인 묶음 {len((uni or {}).get("symbols", []))}개', ru, u)):
        if m is None:
            L.append(f'{name:<22}  (알트 봉이 없어 BTC 만으로 판정)')
            continue
        o = (r or {}).get('oos', empty)
        ci = f'[{np.nan_to_num(m["ci_lo"]):+.3f}, {np.nan_to_num(m["ci_hi"]):+.3f}]'
        L.append(f'{name:<22}{o["n"]:>10}{np.nan_to_num(o["mean_r"]):>+12.3f}{m["n"]:>12}{np.nan_to_num(m["mean_r"]):>+13.3f}'
                 f'{ci:>20}{np.nan_to_num(m["win"]):>6.0%}{np.nan_to_num(m["pf"]):>6.2f}')
    L += ['─' * 100, f'▶ 판정: {verdict}', f'  BTC: {growth(rb)}']
    if ru:
        L.append(f'  코인 묶음: {growth(ru)}')
    if 0 < b['n'] < 30:
        L.append(f'  ※ BTC holdout 거래 {b["n"]}건은 적다 — 그래서 코인 묶음을 함께 본다.')
    L.append('※ 공개한 구간은 이제 "본 데이터"다. 다음 확인은 오늘 이후 쌓이는 데이터로만 한다 (L11).')
    return dict(btc=btc, uni=uni, verdict=verdict, pair=f'{tf}:{fam}', holdout_start=str(holdout_start),
                b=b, u=u, report='\n'.join(L))


def fetch_spot_klines_vision(http, symbol, tf, start='2017-08', end='2021-12', path=None, log=None):
    """
    data.binance.vision 의 스팟 월별 봉 zip (공개 아카이브, 키 없음) → DataFrame(STORE_COLS, era=스팟). 상장 전 달은 404 로 건너뛴다.
    로컬 CSV 캐시. 알트의 '선물 상장 전' 이력을 얻어, 지금까지 어떤 시험도 성과를 보지 않은 기간을 만든다.
    """
    log = log or (lambda msg, color='black': LOG.info(msg))
    path = path or Paths.p(f'{symbol}_{tf}_spot_{start}_{end}.csv')
    if os.path.exists(path):
        try:
            raw = pd.read_csv(path)
            df = pd.DataFrame({k: raw[k].values.astype(np.float64) for k in KLINE_COLS},
                              index=pd.DatetimeIndex(pd.to_datetime(raw['time_ms'].values.astype(np.int64), unit='ms')))
            df['era'] = ERA_SPOT
            return df[STORE_COLS]
        except Exception as e:
            HEALTH.set(f'spot:{symbol}', 'WARN', f'{symbol} 스팟 캐시 손상 — 다시 받습니다: {e}')
    parts, missing = [], 0
    for mon in pd.period_range(start, end, freq='M'):
        url = f'{VISION_BASE}/spot/monthly/klines/{symbol}/{tf}/{symbol}-{tf}-{mon.year:04d}-{mon.month:02d}.zip'
        try:
            parts.append(parse_vision_zip(http.get(url, timeout=60), ERA_SPOT))
        except FileNotFoundError:
            missing += 1                                             # 상장 전
        except Exception as e:
            HEALTH.set(f'spot:{symbol}', 'WARN', f'{symbol} 스팟 {mon} 실패: {e}')
            return None                                              # 중간이 비면 쓰지 않는다
        time.sleep(0.15)
    if not parts:
        return None
    df = pd.concat(parts)
    df = df[~df.index.duplicated(keep='last')].sort_index()
    try:
        out = df[KLINE_COLS].copy()
        out.insert(0, 'time_ms', df.index.values.astype('datetime64[ms]').astype(np.int64))
        out.to_csv(path + '.tmp', index=False)
        os.replace(path + '.tmp', path)
    except Exception as e:
        HEALTH.set(f'spot:{symbol}', 'WARN', f'{symbol} 스팟 캐시 저장 실패: {e}')
    log(f'{symbol} 스팟 {tf} {len(df)}개 ({df.index[0]:%Y-%m-%d} ~ {df.index[-1]:%Y-%m-%d}, 상장 전 {missing}개월 없음)', 'blue')
    return df[STORE_COLS]


def lab_alt_presample_verdict(n, mean_r, lo, pos, tot):
    if n < 30:
        return '판정 불가 (합산 거래 < 30)'
    if not mean_r > 0:
        return '반증 — 처음 보는 알트 구간에서 합산 평균R ≤ 0'
    if lo > 0 and tot > 0 and 3 * pos >= 2 * tot:
        return '확인 — BTC 밖에서도 반복된다 (앞으로의 데이터로 추적하며 소액 실전 후보)'
    return '반증 안 됨 — 방향은 맞지만 입증은 아니다'


def lab_alt_presample(frames_by_symbol, pairs, seen_from=RESEARCH_SEEN_FROM, cost_mode='taker', n_trials_declared=None,
                      status=None, alpha=RESEARCH_PRESAMPLE_ALPHA, btc_ref=None):
    """
    사전등록 P3: 알트의 스팟 이력으로 선언 가설을 코인마다 롤링 WFO 하고, 표본외 중 seen_from 이전 거래만 합쳐 판정한다.
    같은 달 거래는 코인이 달라도 같이 움직이므로 달 단위로 묶어 부트스트랩, 하한은 가설 수로 나눈 유의수준.
    """
    status = status or (lambda *a, **k: None)
    pairs = lab_pairs(pairs)
    if not pairs:
        raise ValueError('처음 보는 알트 구간 검증은 선언한 가설에만 씁니다')
    q = alpha / len(pairs)
    per, skipped = {}, []
    for sym, fr in frames_by_symbol.items():
        fr = {k: v for k, v in (fr or {}).items() if v is not None and len(v)}
        use = [(tf, fam) for tf, fam in pairs if tf in fr]
        if not use:
            skipped.append(sym)
            continue
        status(f'{sym}: 처음 보는 구간 WFO...', 'blue')
        try:
            res = lab_run(None, tf_frames=fr, only=use, holdout_start=seen_from, cost_mode=cost_mode,
                          n_trials_declared=n_trials_declared, symbol=sym)
        except ValueError as e:
            skipped.append(f'{sym}({e})')
            continue
        for r in res['rows']:
            per.setdefault((r['tf'], r['family']), []).append((sym, r))
    L = [f'━━━ 처음 보는 알트 구간 검증 (사전등록 P3) · 가설 {len(pairs)}개 · 코인 {len(frames_by_symbol)}개 ━━━',
         f'알트 스팟 이력으로 WFO, 표본외 중 {str(seen_from)[:10]} 이전 거래만 합쳐 판정 (이 구간의 알트 성과는 어떤 시험도 본 적 없음)',
         f'판정 규칙(사전 고정): 합산 거래 < 30 → 판정 불가 · 합산 평균R ≤ 0 → 반증 · 달묶음 단측 {q:.1%} 하한 > 0 이고 '
         f'체결 10건 이상 코인의 2/3 이상 평균R > 0 → 확인 · 그 외 → 반증 안 됨']
    verdicts = []
    for tf, fam in pairs:
        L += ['', f'── {tf} {LAB_FAMILY_KO[fam]} ──', f'{"코인":<11}{"구간 시작":>12}{"체결":>6}{"승률":>6}{"평균R":>8}{"PF":>6}']
        if btc_ref and btc_ref.get(f'{tf}:{fam}'):
            L.append(f'{"BTC":<11}  (같은 구간은 P1 에서 이미 판정 — 다시 시험하지 않음) {btc_ref[f"{tf}:{fam}"]}')
        R, T, pos, tot = [], [], 0, 0
        for sym, r in per.get((tf, fam), []):
            m = r['oos']
            L.append(f'{sym:<11}{r.get("oos_start", "")[:10]:>12}{m["n"]:>6}{np.nan_to_num(m["win"]):>6.0%}'
                     f'{np.nan_to_num(m["mean_r"]):>+8.3f}{np.nan_to_num(m["pf"]):>6.2f}')
            R += list(r['oos_r'])
            T += list(r['oos_t'])
            if m['n'] >= 10:
                tot += 1
                pos += int(m['mean_r'] > 0)
        R = np.asarray(R, dtype=np.float64)
        lo = _month_cluster_ci(R, np.asarray(T, dtype='datetime64[ns]'), q=q) if len(R) else float('nan')
        mean = float(R.mean()) if len(R) else float('nan')
        v = lab_alt_presample_verdict(len(R), mean, lo, pos, tot)
        L.append(f'{"합산":<9}{"":>12}{len(R):>6}{np.nan_to_num(np.mean(R > 0) if len(R) else 0):>6.0%}{np.nan_to_num(mean):>+8.3f}'
                 f'   {q:.1%} 하한 {np.nan_to_num(lo):+.3f} · 평균R>0 코인 {pos}/{tot} → {v}')
        verdicts.append(dict(pair=f'{tf}:{fam}', n=int(len(R)), mean_r=mean, lo=lo, pos=pos, tot=tot, verdict=v))
    if skipped:
        L.append(f'\n스팟 이력이 없거나 처음 보는 구간에 거래가 없어 건너뜀: {", ".join(skipped)}')
    L.append('※ 반증되면 일지에 남고 같은 범위에서 다시 시험하지 않는다. 확인되어도 다음은 앞으로의 데이터 추적이다 (L13).')
    return dict(verdicts=verdicts, skipped=skipped, report='\n'.join(L))


def research_apply_alt_presample(journal, verdicts):
    for v in verdicts:
        if v['n'] <= 0:
            continue                                                 # 거래 0건 = 시험이 아니다
        st = {'반증': 'refuted', '확인': 'confirmed', '반증 안 됨': 'not_refuted'}.get(v['verdict'].split(' —')[0], 'inconclusive')
        journal.set_status(f'alt_presample|{v["pair"]}', st,
                           f'처음 보는 알트 구간 {v["n"]}건 평균R {np.nan_to_num(v["mean_r"]):+.3f} → {v["verdict"]}')


def merge_spot_perp(spot, perp):
    """스팟 이력(선물 상장 전)과 선물 봉을 잇는다: 선물이 있는 시각부터는 선물만 쓴다."""
    if spot is None or not len(spot):
        return perp
    if perp is None or not len(perp):
        return spot
    return pd.concat([spot[spot.index < perp.index[0]], perp])


def lab_eth_frames(http, tfs=('4h',), log=None):
    """ETH (L16 의 2순위): 스팟 아카이브(2017-08~) + 선물 REST 봉을 이은 tf 봉."""
    out = {}
    for tf in tfs:
        df = merge_spot_perp(fetch_spot_klines_vision(http, 'ETHUSDT', tf, log=log),
                             fetch_klines_tf(http, 'ETHUSDT', tf, log=log))
        if df is not None and len(df):
            out[tf] = df
    return out


def lab_regime_verdict(b, e):
    """사전등록 P4 의 판정 규칙. b = BTC 구간 지표(1순위), e = ETH 구간 지표(2순위, 없으면 None)."""
    if b is None or b['n'] < 20:
        return '판정 불가 (BTC 거래 < 20)'
    if not b['mean_r'] > 0:
        return '반증 — BTC 에서 다른 국면을 버티지 못했다'
    if b['lo'] > 0 and (e is None or e['mean_r'] > 0):
        return '확인 — 국면이 바뀌어도 BTC 에서 버텼다 (앞으로의 데이터로 계속 추적하며 소액 실전 후보)'
    return '반증 안 됨 — 방향은 맞지만 입증은 아니다'


def lab_regime_test(base1m, eth_frames, pair, start=RESEARCH_SEEN_FROM, end=RESEARCH_HOLDOUT_CURRENT,
                    alpha=0.05, cost_mode='taker', n_trials_declared=None, status=None):
    """
    사전등록 P4: 고정된 규칙을 BTC(전체 이력)와 ETH(스팟+선물)에서 롤링 WFO 하고, [start, end) 에 진입한 거래만 판정한다.
    해마다 나눈 성적을 함께 보여 국면에 따라 달라지는지 드러낸다.
    """
    pairs = lab_pairs(pair)
    if not pairs or len(pairs) != 1:
        raise ValueError('국면 검증은 가설 하나만 (예: --regime 4h:consensus)')
    tf, fam = pairs[0]
    btc = lab_run(base1m, only=pairs, futures_only=False, holdout_start=end, cost_mode=cost_mode,
                  n_trials_declared=n_trials_declared, status=status)
    eth = lab_run(None, tf_frames=eth_frames, only=pairs, holdout_start=end, cost_mode=cost_mode,
                  n_trials_declared=n_trials_declared, status=status, symbol='ETHUSDT') \
        if eth_frames and tf in eth_frames else None

    def window(res):
        r = next((x for x in (res or {}).get('rows', []) if (x['tf'], x['family']) == (tf, fam)), None)
        if r is None:
            return None
        R, T = np.asarray(r['oos_r'], dtype=np.float64), np.asarray(r['oos_t'])
        m = T >= np.datetime64(pd.Timestamp(start))
        R, T = R[m], T[m]
        lo = float(np.quantile(stationary_block_bootstrap(R, n_boot=4000, mean_block=5.0, rng=np.random.default_rng(11)),
                               alpha)) if len(R) >= 10 else float('nan')
        yr = T.astype('datetime64[Y]').astype(np.int64) + 1970
        years = {int(y): (int((yr == y).sum()), float(R[yr == y].mean())) for y in np.unique(yr)}
        return dict(n=int(len(R)), mean_r=float(R.mean()) if len(R) else float('nan'), lo=lo,
                    win=float(np.mean(R > 0)) if len(R) else float('nan'),
                    pf=float(R[R > 0].sum() / max(-R[R <= 0].sum(), 1e-9)) if len(R) else float('nan'),
                    years=years, idle=r['idle_windows'], windows=r['windows'])
    b, e = window(btc), window(eth)
    verdict = lab_regime_verdict(b, e)
    L = [f'━━━ 다른 국면 검증 (사전등록 P4) · {tf} {LAB_FAMILY_KO[fam]} · {str(start)[:10]} ~ {str(end)[:10]} ━━━',
         '규칙은 2026-10-03 에 고정, 이 구간에서는 처음 계산한다 (다른 전략들은 이미 본 데이터). BTC 가 1순위 판정, ETH 는 2순위 확인.',
         f'판정 규칙(사전 고정): BTC 거래 < 20 → 판정 불가 · BTC 평균R ≤ 0 → 반증 · BTC 단측 {alpha:.0%} 하한 > 0 이고 '
         'ETH 평균R > 0 → 확인 · 그 외 → 반증 안 됨',
         '─' * 100,
         f'{"코인":<10}{"체결":>6}{"승률":>6}{"평균R":>8}{f"{alpha:.0%} 하한":>9}{"PF":>6}{"쉰 test 구간":>14}']
    for name, w in (('BTC', b), ('ETH', e)):
        if w is None:
            L.append(f'{name:<10}  (데이터 없음)')
            continue
        L.append(f'{name:<10}{w["n"]:>6}{np.nan_to_num(w["win"]):>6.0%}{np.nan_to_num(w["mean_r"]):>+8.3f}'
                 f'{np.nan_to_num(w["lo"]):>+9.3f}{np.nan_to_num(w["pf"]):>6.2f}{w["idle"]:>8}/{w["windows"]}')
    yrs = sorted(set((b or {}).get('years', {})) | set((e or {}).get('years', {})))
    L += ['─' * 100, '해마다 (거래 수 / 평균R) — 2022 약세장 · 2023~24 회복 · 2025 · 2026 은 4h Keltner 가 죽은 구간(P2)']
    for y in yrs:
        cells = []
        for w in (b, e):
            n_, mr = (w or {}).get('years', {}).get(y, (0, float('nan')))
            cells.append(f'{n_:>4}건 {np.nan_to_num(mr):>+7.3f}R' if n_ else f'{"—":>15}')
        L.append(f'  {y}   BTC {cells[0]}   ETH {cells[1]}')
    L += ['─' * 100, f'▶ 판정: {verdict}',
          '※ 확인되어도 다음은 앞으로의 데이터 추적(--prospective)과 소액 실전이다. 반증되면 일지에 남고 BTC 범위의 같은 가설도 반증된다.']
    return dict(btc=btc, eth=eth, b=b, e=e, verdict=verdict, pair=f'{tf}:{fam}', report='\n'.join(L))


def lab_prospective(base1m, tracking, funding=None, cost_mode='taker', status=None, kill_n=20, eth_frames=None):
    """
    앞으로의 검증: 규칙이 고정된 날(since) 이후 데이터에서만 채점한다. 규칙을 고친 적이 없으니 그날 이후 거래는 모두 새 증거다.
    거래가 kill_n 건 이상 쌓였는데 평균R ≤ 0 이면 '중단' (L13).
    """
    L = ['━━━ 앞으로의 검증 (규칙 고정 이후 데이터만) ━━━',
         f'{"가설":<24}{"고정일":>12}{"이후 체결":>10}{"평균R":>8}{"누적R":>8}{"1% 위험 계좌":>12}  상태']
    out = []
    for t in tracking:
        pairs = lab_pairs(t['pair'])
        if t.get('scope') == 'eth':
            if not eth_frames or pairs[0][0] not in eth_frames:
                continue
            res = lab_run(None, tf_frames=eth_frames, only=pairs, holdout_start=t['since'], reveal_holdout=True,
                          cost_mode=cost_mode, status=status, symbol='ETHUSDT')
        else:
            res = lab_run(base1m, only=pairs, futures_only=False, holdout_start=t['since'], reveal_holdout=True,
                          cost_mode=cost_mode, funding=funding, status=status)
        r = res['rows'][0] if res['rows'] else None
        R = np.asarray((r or {}).get('hold_r_list', []), dtype=np.float64)
        mean = float(R.mean()) if len(R) else float('nan')
        eq = float(np.prod(1 + 0.01 * np.clip(R, -50, 50))) if len(R) else 1.0
        state = '중단 — 앞으로의 데이터에서 무너짐' if len(R) >= kill_n and not mean > 0 else \
            '추적 중' if len(R) < kill_n else '살아 있음 (계속 추적)'
        L.append(f'{t["scope"] + "|" + t["pair"]:<24}{t["since"]:>12}{len(R):>10}{np.nan_to_num(mean):>+8.3f}{R.sum():>+8.2f}'
                 f'{eq:>12.3f}  {state}')
        out.append(dict(pair=t['pair'], scope=t['scope'], since=t['since'], n=int(len(R)), mean_r=mean, state=state))
    L.append(f'※ 거래가 {kill_n}건 쌓이기 전에는 결론을 내지 않는다. 평균R ≤ 0 으로 {kill_n}건을 넘기면 중단으로 기록한다.')
    return dict(rows=out, report='\n'.join(L))


# ── 지정가 꼬리 잡기: 강제청산 연쇄가 만드는 과도한 꼬리에, 미리 걸어 둔 지정가로 유동성을 공급한다 ──────────
#  경제적 이유: 청산당하는 쪽은 가격을 가리지 않고 시장가로 던진다. 빠른 시장조성자들은 이런 순간 호가를 거둬서
#  꼬리가 더 길어진다. 미리 깊게 걸어 둔 느린 지정가는 그 꼬리를 받고, 되돌림에서 지정가로 익절한다.
#  비용: 진입·익절 = 지정가(0.02%) → 짧은 시간봉을 죽인 수수료 문제(L2)를 정면으로 피한다. 손절·시간 만료만 시장가.
#  실행: 사람이 하루 1~2번(09:00/21:00 KST) 주문을 걸고 나면 체결·익절·손절은 거래소가 한다 (자동 주문 아님).
#  1분봉은 '체결 판정'에만 쓴다 — 방향을 정하지 않는다 (기획서: 1분봉은 방향 결정 금지).
LAB_FAMILY_KO['wick'] = '지정가 꼬리 잡기'
LAB_WICK_GRID = [dict(P=P, a=a, b=b, c=cs, sides=sd) for P in (720, 1440) for a in (1.0, 1.5, 2.0, 2.5)
                 for b in (0.5, 1.0) for cs in (1.0, 2.0) for sd in (1, 0)]
LAB_WICK_VOL_DAYS = 20          # 일간 로그수익 표준편차 창 (기간 시작 전날까지만)
LAB_WICK_OVERSHOOT = 0.25       # 꼬리 속에서 손절되면 손절가 너머 꼬리 길이의 25% 만큼 더 밀려 체결된다고 본다


@njit(cache=False)
def lab_wick_sim(o, h, l, c, pstart, pend, ref, sig, a, b, cst, side, hold, c_maker, c_taker, through, overshoot):
    """
    기간 k 마다 기준가 ref[k] 에서 a·sig[k] 떨어진 곳에 지정가 (side=+1 아래 매수, −1 위 매도), 익절 b·sig, 손절 c·sig.
    주문은 [pstart[k], pend[k]) 동안 유효, 포지션이 있으면 그 방향 새 주문은 걸지 않는다. 체결 판정은 1분봉:
    지정가를 through 이상 관통해야 체결 · 진입한 그 1분에는 손절만 가능 · 손절이 꼬리 속이면 overshoot 만큼 더 불리 ·
    hold 분이 지나면 시장가 청산. 반환 (진입 1분봉 인덱스, 청산 인덱스, 순 R)
    """
    nP = len(pstart)
    ei = np.empty(nP, dtype=np.int64)
    xi = np.empty(nP, dtype=np.int64)
    rr = np.empty(nP, dtype=np.float64)
    m = 0
    busy = 0
    n = len(c)
    for k in range(nP):
        s = max(pstart[k], busy)
        e = pend[k]
        if s >= e or not (sig[k] > 0):
            continue
        lim = ref[k] * (1.0 - side * a * sig[k])
        tp = lim * (1.0 + side * b * sig[k])
        sl = lim * (1.0 - side * cst * sig[k])
        fi = -1
        for i in range(s, e):
            if (side > 0 and l[i] <= lim * (1.0 - through)) or (side < 0 and h[i] >= lim * (1.0 + through)):
                fi = i
                break
        if fi < 0:
            continue
        end = min(fi + hold, n)
        x = -1
        px = 0.0
        cost = c_maker
        for i in range(fi, end):
            if side > 0:
                if l[i] <= sl:
                    base = sl if (i == fi or o[i] > sl) else o[i]
                    px = base - overshoot * max(0.0, base - l[i])
                    x = i
                    cost += c_taker
                    break
                if i > fi and h[i] >= tp * (1.0 + through):
                    px = tp
                    x = i
                    cost += c_maker
                    break
            else:
                if h[i] >= sl:
                    base = sl if (i == fi or o[i] < sl) else o[i]
                    px = base + overshoot * max(0.0, h[i] - base)
                    x = i
                    cost += c_taker
                    break
                if i > fi and l[i] <= tp * (1.0 - through):
                    px = tp
                    x = i
                    cost += c_maker
                    break
        if x < 0:
            x = end - 1
            px = c[x]
            cost += c_taker
        ei[m] = fi
        xi[m] = x
        rr[m] = (side * (px / lim - 1.0) - cost) / (cst * sig[k])
        m += 1
        busy = x + 1
    return ei[:m], xi[:m], rr[:m]


def _lab_wick_periods(idx, P):
    """UTC 00:00 부터 P분 간격의 주문 기간 → (시작 인덱스, 끝 인덱스, 시작 시각). 데이터가 없는 기간은 뺀다."""
    starts = pd.date_range(idx[0].floor('D'), idx[-1], freq=f'{int(P)}min')
    ts = idx.values
    ps = np.searchsorted(ts, starts.values, side='left')
    pe = np.searchsorted(ts, (starts + pd.Timedelta(minutes=int(P))).values, side='left')
    keep = (pe > ps) & (ps < len(ts))
    return ps[keep], pe[keep], starts[keep]


def _lab_wick_sigma(base1m, starts):
    """기간 시작 시각에 이미 알려진 일간 변동성: 전날 종가까지의 20일 일간 로그수익 표준편차 (과거만)."""
    dc = base1m['close'].resample('1D').last().dropna()
    sd = np.log(dc).diff().rolling(LAB_WICK_VOL_DAYS, min_periods=LAB_WICK_VOL_DAYS).std()
    return sd.reindex(pd.DatetimeIndex(starts).floor('D') - pd.Timedelta(days=1)).values


def lab_run_wick(base1m, holdout_start=None, train_years=LAB_TRAIN_YEARS, test_months=LAB_TEST_MONTHS,
                 holdout_months=LAB_HOLDOUT_MONTHS, futures_only=True, n_trials_declared=None, status=None, grid=None):
    """지정가 꼬리 잡기를 1분봉 체결로 롤링 WFO (달력 기준 창, 파라미터는 train 1σ 하한 최고)."""
    status = status or (lambda *a, **k: None)
    t_wall = time.time()
    base = normalize_frame(base1m)
    if futures_only and (base['era'].values == ERA_FUT).any():
        base = base[base['era'].values == ERA_FUT]
    idx = base.index
    o, h, l, c = (base[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    grid = grid or LAB_WICK_GRID
    per_P = {}
    sims = []
    status(f'Lab 지정가 꼬리 잡기: 파라미터 {len(grid)}개 × 1분봉 {len(base):,}개...', 'blue')
    for p in grid:
        if p['P'] not in per_P:
            ps, pe, st = _lab_wick_periods(idx, p['P'])
            sig = _lab_wick_sigma(base, st) * math.sqrt(p['P'] / 1440.0)
            per_P[p['P']] = (ps, pe, o[ps], np.nan_to_num(sig, nan=0.0))
        ps, pe, ref, sig = per_P[p['P']]
        E, X, RR, S = [], [], [], []
        for side in ((1,) if p['sides'] == 1 else (1, -1)):
            ei, xi, rr = lab_wick_sim(o, h, l, c, ps, pe, ref, sig, float(p['a']), float(p['b']), float(p['c']), side,
                                      int(p['P']), MAKER_FEE, TAKER_FEE + SLIPPAGE_T, MAKER_TP_THROUGH, LAB_WICK_OVERSHOOT)
            E.append(idx.values[ei])
            X.append(idx.values[xi])
            RR.append(rr)
            S.append(np.full(len(rr), side, dtype=np.int64))
        sims.append((p, np.concatenate(E), np.concatenate(X), np.concatenate(RR), np.concatenate(S)))
    t_last = idx[-1]
    hold_start = pd.Timestamp(holdout_start) if holdout_start is not None else t_last - pd.DateOffset(months=int(holdout_months))
    train_off = pd.DateOffset(months=int(round(train_years * 12)))
    oos_start = idx[0] + train_off
    h64 = np.datetime64(hold_start)
    wins, w = [], oos_start
    while w < t_last:
        wins.append(w)
        w = w + pd.DateOffset(months=int(test_months))
    oR, oE, oX, oS, hR, chosen = [], [], [], [], [], []
    for w in wins:
        ws, wt = np.datetime64(w), np.datetime64(w - train_off)
        we = np.datetime64(w + pd.DateOffset(months=int(test_months)))
        best, best_score = None, 0.0
        for sim in sims:
            _, E, X, RR, S = sim
            m = (E >= wt) & (E < ws)
            if m.sum() < LAB_UNIVERSE_MIN_TRAIN:
                continue
            x = RR[m]
            neff = min(len(x), len(np.unique(E[m].astype('datetime64[D]'))))
            score = x.mean() - x.std(ddof=1) / math.sqrt(neff)
            if score > best_score:
                best, best_score = sim, score
        chosen.append((str(w)[:10], None if best is None else best[0], we > h64))
        if best is None:
            continue
        _, E, X, RR, S = best
        m = (E >= ws) & (E < we)
        om, hm = m & (E < h64), m & (E >= h64)
        oR.append(RR[om]); oE.append(E[om]); oX.append(X[om]); oS.append(S[om]); hR.append(RR[hm])
    cat = (lambda a, dt: np.concatenate(a) if a else np.array([], dtype=dt))
    oR, oE, oX, oS, hR = cat(oR, np.float64), cat(oE, 'datetime64[ns]'), cat(oX, 'datetime64[ns]'), cat(oS, np.int64), \
        cat(hR, np.float64)
    order = np.argsort(oX, kind='stable')
    oR, oE, oX, oS = oR[order], oE[order], oX[order], oS[order]
    oos_end = min(hold_start, t_last)
    years = max((oos_end - oos_start).days / 365.25, 1e-6)
    met = _lab_metrics(oR, years, n_trials=max(int(n_trials_declared or 0), 2))
    if met['n'] >= 5:
        met['ci_lo'], met['ci_hi'] = _month_cluster_ci(oR, oE), _month_cluster_ci(oR, oE, q=0.95)
    _lab_attach_growth(met, oR, oX, oos_start, oos_end)
    win, loss = oR[oR > 0], oR[oR <= 0]
    met.update(avg_win=float(win.mean()) if len(win) else float('nan'),
               avg_loss=float(loss.mean()) if len(loss) else float('nan'),
               long_n=int((oS > 0).sum()), short_n=int((oS < 0).sum()),
               long_r=float(oR[oS > 0].mean()) if (oS > 0).any() else float('nan'),
               short_r=float(oR[oS < 0].mean()) if (oS < 0).any() else float('nan'))
    last = next((pp for _, pp, _ in reversed(chosen) if pp is not None), None)
    row = dict(tf='1m', family='wick', oos=met, last_params=last, oos_r=oR, oos_t=oE, windows=len(chosen),
               idle_windows=sum(1 for _, pp, _ in chosen if pp is None), chosen=chosen)
    res = dict(rows=[row], data=f'{idx[0]:%Y-%m-%d} ~ {t_last:%Y-%m-%d}', holdout_start=str(hold_start),
               n_sims=len(grid), seconds=round(time.time() - t_wall, 1), n_dsr=max(int(n_trials_declared or 0), 2))
    res['report'] = lab_wick_report(res)
    return res


def lab_wick_report(res):
    r = res['rows'][0]
    m = r['oos']
    p = r['last_params']
    L = [f'━━━ 지정가 꼬리 잡기 · {SYMBOL} 1분봉 체결 · {res["data"]} · 파라미터 {res["n_sims"]}개 · {res["seconds"]}초 ━━━',
         '아이디어: 강제청산 연쇄로 가격이 순간적으로 과하게 밀릴 때, 미리 걸어 둔 지정가가 그 꼬리를 받고 되돌림에서 지정가로 익절한다.',
         f'주문: 매일 09:00 KST(또는 12시간마다) 기준가에서 a·σ 떨어진 곳에 지정가, 익절 b·σ · 손절 c·σ, 다음 갱신까지 유지 '
         f'(σ = 전날까지 {LAB_WICK_VOL_DAYS}일 일간 변동성)',
         f'비용: 진입·익절 지정가 {MAKER_FEE:.2%} · 손절·시간 만료 시장가 {TAKER_FEE + SLIPPAGE_T:.2%} · '
         f'체결 규칙(보수): 지정가 1bp 관통해야 체결, 진입한 1분 안에는 손절만 인정, 꼬리 속 손절은 꼬리의 '
         f'{LAB_WICK_OVERSHOOT:.0%} 더 불리',
         f'WFO: train {LAB_TRAIN_YEARS:g}년 → test {LAB_TEST_MONTHS}개월 · holdout {res["holdout_start"][:10]} 이후 봉인 · '
         f'DSR 은 누적 절차 {res["n_dsr"]}개로 보정',
         '─' * 100]
    if m['n'] == 0:
        L.append(f'거래 0건 — 모든 test 구간({r["windows"]}개)에서 쉼: train 에서 비용을 넘는 설정이 한 번도 없었다.')
    else:
        L += [f'표본외 체결 {m["n"]}건 (연 {m["n_year"]:.0f}) · 승률 {m["win"]:.0%} · 평균 이익 {np.nan_to_num(m["avg_win"]):+.2f}R / '
              f'평균 손실 {np.nan_to_num(m["avg_loss"]):+.2f}R · 평균 {m["mean_r"]:+.3f}R · 달묶음 90% CI '
              f'[{np.nan_to_num(m["ci_lo"]):+.3f}, {np.nan_to_num(m["ci_hi"]):+.3f}] · PF {m["pf"]:.2f}',
              f'DSR {m["dsr"]:.2f} · 연환산 샤프 {np.nan_to_num(m["sharpe"]):+.2f} · 보수 하루복리 {m["g_day"]:+.3%} @ 거래당 위험 '
              f'{m["f_star"]:.1%} (점추정이면 {m["g_day_point"]:+.3%})',
              f'방향별: 아래 매수 {m["long_n"]}건 평균 {np.nan_to_num(m["long_r"]):+.3f}R · 위 매도 {m["short_n"]}건 평균 '
              f'{np.nan_to_num(m["short_r"]):+.3f}R · 쉰 test 구간 {r["idle_windows"]}/{r["windows"]}']
        if p:
            L.append(f'최근 선택 설정: {p["P"] // 60}시간마다 갱신 · 지정가 {p["a"]}σ · 익절 {p["b"]}σ · 손절 {p["c"]}σ · '
                     f'{"매수만" if p["sides"] == 1 else "매수+매도"}')
    L.append('─' * 100)
    passed = m['n'] >= 100 and m['ci_lo'] > 0 and m['dsr'] >= 0.9
    L.append('▶ 사전 기준(체결 ≥ 100, 달묶음 CI 하한 > 0, DSR ≥ 0.9) ' + ('통과 — 사전등록 후 앞으로의 데이터·다른 시장으로 확인할 후보'
                                                                  if passed else '미통과 — 이 비용·체결 규칙에서 입증된 edge 없음'))
    L.append(lab_sharpe_line(res['rows']))
    L.append('※ 승률이 높아도 평균 손실이 크면 소용없다. 볼 것은 평균R·CI 하한·샤프다. 이 결과는 이미 본 BTC 기간의 "탐색"이고, '
             '좋게 나오면 사전등록한 뒤 앞으로의 데이터와 다른 시장으로 확인한다 (L1·L11).')
    return '\n'.join(L)


def lab_live_state(o, h, l, c, atr, target, stop_k, max_hold, fixed_stop=0.0, tp_r=0.0):
    """lab_sim_x(시장가 진입)와 같은 규칙으로 끝까지 재생해 '지금' 상태를 돌려준다: 보유 방향·진입가·손절가·진입 봉, 손절 후 막힌 방향."""
    pos, entry, stop, t_in, blocked, entries = 0, 0.0, 0.0, -1, 0, 0
    for i in range(1, len(c)):
        want = int(target[i - 1])
        if blocked != 0 and want != blocked:
            blocked = 0
        if pos != 0 and want != pos:
            pos = 0
        if pos == 0 and want != 0 and want != blocked and atr[i - 1] > 1e-5:
            pos, entry, t_in = want, float(o[i]), i
            dist = (fixed_stop if fixed_stop > 0 else stop_k * atr[i - 1]) * entry
            stop, tpx = entry - pos * dist, entry + pos * tp_r * dist
            entries += 1
        if pos != 0:
            if ((pos > 0 and l[i] <= stop) or (pos < 0 and h[i] >= stop)
                    or (tp_r > 0 and ((pos > 0 and h[i] >= tpx) or (pos < 0 and l[i] <= tpx)))
                    or (max_hold > 0 and i - t_in + 1 >= max_hold)):
                blocked, pos = pos, 0
    return dict(pos=pos, entry=entry, stop=stop, t_in=t_in, blocked=blocked, want_next=int(target[-1]), entries=entries)


def lab_live_signal(base1m, pairs, seed=70.0, futures_only=True, cost_mode='taker', status=None):
    """
    추적 중인 후보의 '지금' 신호 (종이 매매·연구 추적용 — 실전 인증 아님). 가장 최근 WFO 창이 고른 설정으로 마지막 완결 봉까지
    재생하고, 다음 봉 시가에 할 일(진입/유지/청산/대기)과 손절가를 보인다. 신호 시각은 실행 시각 그대로 기록한다 (소급 금지).
    """
    base = normalize_frame(base1m)
    if futures_only and (base['era'].values == ERA_FUT).any():
        base = base[base['era'].values == ERA_FUT]
    snap = Snapshot(base, base.index[-1].to_pydatetime() + timedelta(minutes=1))
    risk_frac = RISK_CAP * UNVERIFIED_RISK_MULT
    min_notional = FALLBACK_RULES['min_notional']
    L = [f'━━━ 지금 신호 (종이 매매·연구 추적용 — 실전 인증 아님) · {SYMBOL} · 실행 {utcnow():%Y-%m-%d %H:%M} UTC ━━━']
    out = []
    for tf, fam in lab_pairs(pairs) or []:
        res = lab_run(base, only=[(tf, fam)], futures_only=futures_only, cost_mode=cost_mode, status=status,
                      holdout_start=base.index[-1] + timedelta(days=1))
        r = res['rows'][0] if res['rows'] else None
        p = (r or {}).get('current_params')
        df = snap.tf(tf)
        df = df[df['complete'].values > 0.5]
        last_bar = df.index[-1]
        name = f'{tf} {LAB_FAMILY_KO[fam]}'
        if p is None:
            L.append(f'■ {name}: 쉼 — 최근 2년 train 에서 비용을 넘는 근거가 없어 이번 test 구간은 거래하지 않는다')
            out.append(dict(pair=f'{tf}:{fam}', state='rest', last_bar=str(last_bar)))
            continue
        ind = _lab_indicators(df)
        o, h, l, c, atr = (ind[k].values for k in ('o', 'h', 'l', 'c', 'atr'))
        mh = int(p['N']) if fam == 'meanrev' else int(p['H']) if fam in ('funding', 'analog', 'tod') \
            else int(LAB_MAX_HOLD.get(fam, 0))
        st = lab_live_state(o, h, l, c, atr, _lab_target(fam, p, ind), float(p['k']), mh)
        side_ko = {1: '롱', -1: '숏', 0: '없음'}
        if st['pos'] != 0 and st['want_next'] != st['pos']:
            action = f'다음 봉 시가({last_bar + pd.Timedelta(minutes=INTERVALS[tf])} UTC)에 {side_ko[st["pos"]]} 청산'
        elif st['pos'] != 0:
            action = f'{side_ko[st["pos"]]} 유지 · 손절 {st["stop"]:,.1f}'
        elif st['want_next'] != 0 and st['want_next'] != st['blocked'] and atr[-1] > 1e-5:
            action = (f'다음 봉 시가({last_bar + pd.Timedelta(minutes=INTERVALS[tf])} UTC)에 {side_ko[st["want_next"]]} 진입 · '
                      f'손절 = 시가 {"-" if st["want_next"] > 0 else "+"} {p["k"]:g}×ATR (지금 기준 약 {p["k"] * atr[-1]:.2%})')
        else:
            action = '대기 (신호 없음)' + (' — 손절 직후라 같은 방향 재진입은 신호가 한 번 바뀐 뒤' if st['blocked'] else '')
        L.append(f'■ {name} · 설정 {p} · 마지막 완결 봉 {last_bar} UTC')
        if st['pos'] != 0:
            L.append(f'   보유: {side_ko[st["pos"]]} (진입 {df.index[st["t_in"]]} UTC @ {st["entry"]:,.1f}, 손절 {st["stop"]:,.1f})')
        L.append(f'   ▶ {action}')
        stop_frac = (abs(st['entry'] - st['stop']) / st['entry']) if st['pos'] else p['k'] * atr[-1]
        notional = seed * risk_frac / max(stop_frac, 1e-6)
        if notional < min_notional:
            L.append(f'   시드 {seed:,.0f}달러 · 미검증 위험 {risk_frac:.2%} → 명목 {notional:,.0f}달러 < 최소주문 {min_notional:,.0f}달러. '
                     f'최소주문으로 걸면 위험이 시드의 {min_notional * stop_frac / seed:.1%} → 종이 매매로만 추적 권장')
        else:
            lev = int(min(MAX_LEV, max(1, math.ceil(notional / (seed * MARGIN_CAP)))))
            L.append(f'   시드 {seed:,.0f}달러 · 미검증 위험 {risk_frac:.2%}: 명목 약 {notional:,.0f}달러 · 격리 {lev}배')
        out.append(dict(pair=f'{tf}:{fam}', state='position' if st['pos'] else 'flat', pos=st['pos'], action=action,
                        params=p, last_bar=str(last_bar), stop=st['stop'] if st['pos'] else None))
    L.append('※ 후보일 뿐 인증된 전략이 아니다. 앞으로의 데이터(--prospective)로 20건 이상 쌓일 때까지 결론을 내지 않는다.')
    return dict(rows=out, report='\n'.join(L))


# ── 정답에서 단서 찾기: 과거 각 시점에 '실제로 무슨 일이 있었는지'(정답 라벨)를 붙이고, 그 시점에 알 수 있던 단서로 ───────
#    정답 확률을 배운다 (삼중 장벽 라벨링 + 로지스틱 회귀). 배우는 데는 과거 train 만 쓰고, 정답의 결과 구간이 test 와
#    겹치는 train 표본은 지운다(purge) → 미래 누설 없음. 성적은 그다음 test 구간에서만 매긴다.
LAB_FAMILY_KO['oracle'] = '정답 단서 학습'
LAB_BUILD = '2026-10-05c · 정답 단서 학습 · 끝머리 지도'     # 사용자가 어느 파일을 돌렸는지 출력에서 바로 보이게
LAB_CLI_FLAGS = frozenset({'--lab', '--cost', '--only', '--symbols', '--retest', '--presample', '--final', '--alt-presample',
                           '--prospective', '--wick', '--signal', '--seed', '--oracle', '--regime', '--universe', '--tfs',
                           '--reveal-holdout', '--fees', '--stop-pct', '--tp', '--hold', '--surrogate', '--surrogate-n',
                           '--no-funding'})
LAB_ORACLE_Q = (0.05, 0.10, 0.20)     # train 예측 확률 상위 몇 %에서만 진입할지 (train 이 고른다)
LAB_ORACLE_FEATURES = ['1봉 수익', '4봉 수익', '24봉 수익', '168봉 수익', '변동성(ATR%)', '변동성 비율(지금/1주)',
                       'EMA20 거리', 'EMA100 거리', 'SMA200 거리', 'Bollinger z(20)', 'Donchian 위치(55)',
                       '테이커 체결강도(12)', '테이커 체결강도(48)', '거래량 z', '펀딩비 백분위', '시각 sin', '시각 cos', '주말']


@njit(cache=False)
def lab_barrier_labels(o, h, l, c, sl, tp, hold, cost):
    """
    정답 라벨: 봉 i 마감에 결정 → 봉 i+1 시가 진입. 롱은 +tp 익절·−sl 손절, 숏은 반대, hold 봉 안에 안 닿으면 그 봉 종가 청산.
    같은 봉에서 둘 다 닿으면 손절로 본다 (보수). 반환: 롱 R, 롱 청산 봉, 숏 R, 숏 청산 봉 (R = 순손익 / sl, 끝부분은 NaN).
    """
    n = len(c)
    rl = np.full(n, np.nan)
    rs = np.full(n, np.nan)
    xl = np.full(n, -1, dtype=np.int64)
    xs = np.full(n, -1, dtype=np.int64)
    for i in range(n - hold - 1):
        e = o[i + 1]
        for side in (1, -1):
            tpx = e * (1.0 + side * tp)
            slx = e * (1.0 - side * sl)
            px = c[i + hold]
            x = i + hold
            for j in range(i + 1, i + hold + 1):
                if (side > 0 and l[j] <= slx) or (side < 0 and h[j] >= slx):
                    px = slx
                    if (side > 0 and o[j] < slx) or (side < 0 and o[j] > slx):
                        px = o[j]
                    x = j
                    break
                if (side > 0 and h[j] >= tpx) or (side < 0 and l[j] <= tpx):
                    px = tpx
                    x = j
                    break
            r = (side * (px / e - 1.0) - cost) / sl
            if side > 0:
                rl[i] = r
                xl[i] = x
            else:
                rs[i] = r
                xs[i] = x
    return rl, xl, rs, xs


def _oracle_features(df, funding=None):
    """정답 시점에 이미 알 수 있던 단서 (봉 마감 기준, 미래 데이터 없음)."""
    ind = _lab_indicators(df)
    c, h, l, v, tb, atr = ind['c'], ind['h'], ind['l'], ind['v'], ind['tb'], ind['atr']
    lc = np.log(c)
    a = atr.replace(0, np.nan)
    ma20, sd20 = c.rolling(20).mean(), c.rolling(20).std()
    hi55, lo55 = h.rolling(55).max(), l.rolling(55).min()
    imb = lambda N: (2 * tb - v).rolling(N).sum() / v.rolling(N).sum()
    fp = _lab_funding_pct(df.index, int((df.index[1] - df.index[0]).total_seconds() // 60), funding) \
        if funding is not None else None
    hr = df.index.hour.values + df.index.minute.values / 60.0
    cols = [lc.diff(1), lc.diff(4), lc.diff(24), lc.diff(168), atr, atr / atr.rolling(168).mean(),
            (c / c.ewm(span=20, adjust=False).mean() - 1) / a, (c / c.ewm(span=100, adjust=False).mean() - 1) / a,
            (c / c.rolling(200).mean() - 1) / a, (c - ma20) / sd20, (c - lo55) / (hi55 - lo55),
            imb(12), imb(48), np.log(v / v.rolling(168).median()),
            pd.Series(np.nan_to_num(fp, nan=0.5) if fp is not None else np.full(len(c), 0.5), index=c.index),
            pd.Series(np.sin(2 * np.pi * hr / 24), index=c.index), pd.Series(np.cos(2 * np.pi * hr / 24), index=c.index),
            pd.Series((df.index.dayofweek.values >= 5).astype(float), index=c.index)]
    X = np.column_stack([np.asarray(x, dtype=np.float64) for x in cols])
    X[~np.isfinite(X)] = np.nan
    return X


def _logit_fit(X, y, lam_frac=0.001, iters=30):
    """L2 로지스틱 회귀 (뉴턴법). 특성은 미리 표준화. 반환 [절편, 계수...]."""
    n, d = X.shape
    Xb = np.column_stack([np.ones(n), X])
    w = np.zeros(d + 1)
    R = np.eye(d + 1) * lam_frac * n
    R[0, 0] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))
        g = Xb.T @ (p - y) + R @ w
        H = (Xb * (p * (1 - p))[:, None]).T @ Xb + R
        step = np.linalg.solve(H + 1e-9 * np.eye(d + 1), g)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return w


def _logit_predict(w, X):
    return 1.0 / (1.0 + np.exp(-np.clip(w[0] + X @ w[1:], -30, 30)))


def lab_run_oracle(base1m, tf='1h', sl=0.01, tp_r=2.0, hold=24, holdout_start=None, train_years=LAB_TRAIN_YEARS,
                   test_months=LAB_TEST_MONTHS, holdout_months=LAB_HOLDOUT_MONTHS, funding=None, futures_only=True,
                   n_trials_declared=None, status=None, frame=None):
    """
    정답 단서 학습을 롤링 WFO 로: 각 test 구간마다 직전 train 의 (단서 → 정답) 으로 롱·숏 확률 모델을 따로 배우고,
    train 예측 확률 상위 q% 구간의 평균R 이 1σ 하한으로 양수인 쪽만, 그 문턱을 넘는 시점에 진입한다 (포지션은 겹치지 않음).
    """
    status = status or (lambda *a, **k: None)
    t_wall = time.time()
    if frame is None:
        base = normalize_frame(base1m)
        if futures_only and (base['era'].values == ERA_FUT).any():
            base = base[base['era'].values == ERA_FUT]
        df = Snapshot(base, base.index[-1].to_pydatetime() + timedelta(minutes=1)).tf(tf)
        df = df[df['complete'].values > 0.5]
    else:
        df = normalize_frame(frame)
    idx = df.index
    o, h, l, c = (df[k].values.astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    cost = 2 * (TAKER_FEE + SLIPPAGE_T)
    status(f'Lab 정답 단서 학습 {tf}: 정답 라벨(+{tp_r * sl:.1%} 먼저 vs −{sl:.1%} 먼저, {hold}봉) 계산...', 'blue')
    rl, xl, rs, xs = lab_barrier_labels(o, h, l, c, float(sl), float(tp_r * sl), int(hold), float(cost))
    X = _oracle_features(df, funding)
    ok = np.isfinite(X).all(axis=1)
    bar_h = INTERVALS[tf] / 60.0
    train_n = int(train_years * 365.25 * 24 / bar_h)
    test_n = max(1, int(test_months * 30.44 * 24 / bar_h))
    hold_start = pd.Timestamp(holdout_start) if holdout_start is not None else idx[-1] - pd.DateOffset(months=int(holdout_months))
    i_hold = int(idx.searchsorted(hold_start))
    i_end = max(0, i_hold - hold - 1)                                    # 정답 구간이 holdout 가격에 닿는 봉은 쓰지 않는다
    trades, calib_l, calib_s, coefs, chosen = [], [], [], [], []
    for s0 in range(train_n, i_end, test_n):
        e0 = min(s0 + test_n, i_end)
        tr = np.arange(max(0, s0 - train_n), max(0, s0 - hold - 1))       # 결과 구간이 test 와 겹치는 표본은 지운다
        tr = tr[ok[tr] & np.isfinite(rl[tr]) & np.isfinite(rs[tr])]
        if len(tr) < 500:
            chosen.append((str(idx[s0])[:10], None))
            continue
        mu, sd = X[tr].mean(0), X[tr].std(0)
        sd[sd < 1e-12] = 1.0
        Z = lambda rows: np.clip((X[rows] - mu) / sd, -5, 5)
        models, fitted = {}, {}
        for side, R in ((1, rl), (-1, rs)):
            w = _logit_fit(Z(tr), (R[tr] > 0).astype(np.float64))
            fitted[side] = w
            p_tr = _logit_predict(w, Z(tr))
            for q in LAB_ORACLE_Q:
                tau = float(np.quantile(p_tr, 1 - q))
                sel = tr[p_tr >= tau]
                x = R[sel]
                neff = max(2, len(np.unique(idx.values[sel].astype('datetime64[D]'))))
                score = x.mean() - x.std(ddof=1) / math.sqrt(neff)
                if score > 0 and (side not in models or score > models[side][2]):
                    models[side] = (w, tau, score, q)
            coefs.append((side, w[1:].copy()))
        chosen.append((str(idx[s0])[:10], {sd_: round(m[3], 2) for sd_, m in models.items()} or None))
        te = np.arange(s0, e0)
        te = te[ok[te] & np.isfinite(rl[te]) & np.isfinite(rs[te])]
        if not len(te):
            continue
        Zte = Z(te)
        pl = _logit_predict(models[1][0], Zte) if 1 in models else None
        ps = _logit_predict(models[-1][0], Zte) if -1 in models else None
        calib_l += list(zip(_logit_predict(fitted[1], Zte), rl[te]))           # 진입 여부와 무관하게 모든 봉의 예측·정답
        calib_s += list(zip(_logit_predict(fitted[-1], Zte), rs[te]))
        busy = -1
        for k, i in enumerate(te):
            if i <= busy:
                continue
            cand = []
            if pl is not None and pl[k] >= models[1][1]:
                cand.append((models[1][2], 1))
            if ps is not None and ps[k] >= models[-1][1]:
                cand.append((models[-1][2], -1))
            if not cand:
                continue
            side = max(cand)[1]
            R, X_ = (rl, xl) if side > 0 else (rs, xs)
            trades.append((i, int(X_[i]), side, float(R[i])))
            busy = int(X_[i])
    T = np.array([t[0] for t in trades], dtype=np.int64)
    XI = np.array([t[1] for t in trades], dtype=np.int64)
    SD = np.array([t[2] for t in trades], dtype=np.int64)
    RR = np.array([t[3] for t in trades], dtype=np.float64)
    om = T < i_hold
    oos_start, oos_end = idx[min(train_n, len(idx) - 1)], idx[max(min(i_hold, len(idx)) - 1, 0)]
    years = max((oos_end - oos_start).days / 365.25, 1e-6)
    met = _lab_metrics(RR[om], years, n_trials=max(int(n_trials_declared or 0), 2))
    if met['n'] >= 5:
        met['ci_lo'], met['ci_hi'] = _month_cluster_ci(RR[om], idx.values[T[om]]), \
            _month_cluster_ci(RR[om], idx.values[T[om]], q=0.95)
    _lab_attach_growth(met, RR[om], idx.values[XI[om]], oos_start, oos_end)
    met.update(long_n=int(((SD > 0) & om).sum()), short_n=int(((SD < 0) & om).sum()),
               long_r=float(RR[(SD > 0) & om].mean()) if ((SD > 0) & om).any() else float('nan'),
               short_r=float(RR[(SD < 0) & om].mean()) if ((SD < 0) & om).any() else float('nan'))
    rl_, rs_ = rl[:i_end], rs[:i_end]
    base_l = float(np.mean(rl_[np.isfinite(rl_)] > 0)) if np.isfinite(rl_).any() else float('nan')
    base_s = float(np.mean(rs_[np.isfinite(rs_)] > 0)) if np.isfinite(rs_).any() else float('nan')

    def deciles(pairs):
        if len(pairs) < 50:
            return []
        p, r = np.array([a for a, _ in pairs]), np.array([b for _, b in pairs])
        edges = np.quantile(p, np.linspace(0, 1, 11))
        out = []
        for k in range(10):
            m = (p >= edges[k]) & ((p <= edges[k + 1]) if k == 9 else (p < edges[k + 1]))
            if m.any():
                out.append((k + 1, float(p[m].mean()), float(np.mean(r[m] > 0)), float(r[m].mean()), int(m.sum())))
        return out
    clues = {}
    for side in (1, -1):
        W = np.array([w for s_, w in coefs if s_ == side])
        if len(W):
            mean_w = W.mean(0)
            order = np.argsort(-np.abs(mean_w))[:5]
            clues[side] = [(LAB_ORACLE_FEATURES[j], float(mean_w[j]), float(np.mean(np.sign(W[:, j]) == np.sign(mean_w[j]))))
                           for j in order]
    row = dict(tf=tf, family='oracle', oos=met, oos_r=RR[om], oos_t=idx.values[T[om]], windows=len(chosen),
               idle_windows=sum(1 for _, m in chosen if m is None), last_params=chosen[-1][1] if chosen else None)
    res = dict(rows=[row], tf=tf, sl=sl, tp_r=tp_r, hold=hold, data=f'{idx[0]:%Y-%m-%d} ~ {idx[-1]:%Y-%m-%d}',
               holdout_start=str(hold_start), base_long=base_l, base_short=base_s, cost_r=cost / sl,
               calib_long=deciles(calib_l), calib_short=deciles(calib_s), clues=clues,
               n_dsr=max(int(n_trials_declared or 0), 2), seconds=round(time.time() - t_wall, 1))
    res['report'] = lab_oracle_report(res)
    return res


def lab_oracle_report(res):
    r = res['rows'][0]
    m = r['oos']
    be = (1 + res['cost_r']) / (1 + res['tp_r'])
    L = [f'━━━ 정답 단서 학습 · {SYMBOL} {res["tf"]} · {res["data"]} · {res["seconds"]}초 ━━━',
         f'정답: 각 봉 마감에 들어갔다면 +{res["tp_r"] * res["sl"]:.1%}(익절 {res["tp_r"]:g}R)가 −{res["sl"]:.1%}(손절)보다 먼저 왔는가 '
         f'({res["hold"]}봉 안, 같은 봉이면 손절로 침). 단서 {len(LAB_ORACLE_FEATURES)}개는 그 시점에 이미 알 수 있던 값만.',
         f'배우기: 직전 {LAB_TRAIN_YEARS:g}년 정답으로 롱·숏 확률 모델(로지스틱 회귀)을 따로 → 다음 {LAB_TEST_MONTHS}개월에만 적용. '
         f'결과가 test 와 겹치는 train 정답은 지움. 진입 = train 확률 상위 {"/".join(f"{q:.0%}" for q in LAB_ORACLE_Q)} 중 train 이 고른 문턱 이상.',
         f'기준선: 아무 때나 들어가면 이길 확률 롱 {res["base_long"]:.1%} · 숏 {res["base_short"]:.1%} · '
         f'수수료(1R 의 {res["cost_r"]:.0%})를 넘으려면 익절·손절로만 끝날 때 약 {be:.0%} 이상 필요',
         '─' * 100]
    if m['n'] == 0:
        L.append(f'거래 0건 — 모든 test 구간({r["windows"]}개)에서 train 상위 확률 구간도 비용을 넘지 못해 쉼.')
    else:
        L += [f'표본외 체결 {m["n"]}건 (연 {m["n_year"]:.0f}) · 승률 {m["win"]:.0%} · 평균 {m["mean_r"]:+.3f}R · 달묶음 90% CI '
              f'[{np.nan_to_num(m["ci_lo"]):+.3f}, {np.nan_to_num(m["ci_hi"]):+.3f}] · PF {m["pf"]:.2f} · DSR {m["dsr"]:.2f} '
              f'(누적 {res["n_dsr"]}개 보정)',
              f'연환산 샤프 {np.nan_to_num(m["sharpe"]):+.2f} · 보수 하루복리 {m["g_day"]:+.3%} @ 거래당 위험 {m["f_star"]:.1%} · '
              f'롱 {m["long_n"]}건 {np.nan_to_num(m["long_r"]):+.3f}R · 숏 {m["short_n"]}건 {np.nan_to_num(m["short_r"]):+.3f}R · '
              f'쉰 test 구간 {r["idle_windows"]}/{r["windows"]}']
        rows, streak = lab_risk_table(r['oos_r'], m['n'] / max(m['n_year'], 1e-9))
        L.append('계좌 위험별: ' + ' · '.join(f'{f:.0%}: ×{mult:.2f} (낙폭 {dd:.0%})' for f, mult, d, dd in rows)
                 + f' · 최장 연속 손실 {streak}번')
    for name, cal, base in (('롱', res['calib_long'], res['base_long']), ('숏', res['calib_short'], res['base_short'])):
        if not cal:
            continue
        L += ['─' * 100, f'"확률이 높다고 본 시점이 정말 더 이겼나" — 표본외 {name} 예측 확률 10분위 (모든 봉, 기준선 {base:.1%})',
              f'{"분위":>4}{"예측 확률":>10}{"실제 승률":>10}{"평균R":>9}{"봉 수":>8}']
        for k, pm, wr, mr, nn in cal:
            if k in (1, 2, 5, 9, 10):
                L.append(f'{k:>4}{pm:>10.1%}{wr:>10.1%}{mr:>+9.3f}{nn:>8}')
    for side, name in ((1, '롱'), (-1, '숏')):
        if res['clues'].get(side):
            L.append(f'단서 ({name} 정답 확률을 가장 크게 움직인 것, 표준화 계수 · 창마다 같은 방향 비율): ' +
                     ' · '.join(f'{nm} {w:+.2f} ({agree:.0%})' for nm, w, agree in res['clues'][side]))
    L.append('─' * 100)
    passed = m['n'] >= 100 and m['ci_lo'] > 0 and m['dsr'] >= 0.9
    L.append('▶ 사전 기준(체결 ≥ 100, 달묶음 CI 하한 > 0, DSR ≥ 0.9) ' +
             ('통과 — 사전등록 후 앞으로의 데이터로 확인할 후보' if passed else '미통과 — 이 단서로는 정답을 비용 이상으로 맞히지 못했다'))
    L.append(lab_sharpe_line(res['rows']))
    L.append('※ 분위표에서 위쪽 분위의 실제 승률이 기준선과 손익분기 승률을 꾸준히 넘어야 "확률적으로 가장 높은 곳"이 실재한다. '
             '이 결과는 이미 본 BTC 기간의 탐색이다.')
    return '\n'.join(L)


def lab_oracle_map(results):
    """같은 단서·손절·보유로 익절 목표만 바꾼 결과 비교 — '끝머리(움직임이 어디까지 가는지)를 예측할 수 있나'."""
    r0 = results[0]
    L = [f'━━━ 끝머리 지도 · {SYMBOL} {r0["tf"]} · 손절 {r0["sl"]:.1%} · {r0["hold"]}봉 안 · 목표만 멀리 ━━━',
         f'{"익절":>5}{"손익분기 승률":>12}{"무작위 승률":>11}{"기준선 롱/숏":>14}{"상위10% 실제 롱/숏":>18}'
         f'{"상위10% 평균R 롱/숏":>20}{"체결":>6}{"평균R":>8}{"CI하한":>8}  판정']
    for res in results:
        m = res['rows'][0]['oos']
        be = (1 + res['cost_r']) / (1 + res['tp_r'])
        top = lambda cal, j: next((x[j] for x in cal if x[0] == 10), float('nan'))
        passed = m['n'] >= 100 and m['ci_lo'] > 0 and m['dsr'] >= 0.9
        L.append(f'{res["tp_r"]:>4g}R{be:>12.0%}{1 / (1 + res["tp_r"]):>11.0%}'
                 f'{res["base_long"]:>8.0%}/{res["base_short"]:<5.0%}'
                 f'{top(res["calib_long"], 2):>12.0%}/{top(res["calib_short"], 2):<5.0%}'
                 f'{top(res["calib_long"], 3):>+13.2f}/{top(res["calib_short"], 3):<+6.2f}'
                 f'{m["n"]:>6}{np.nan_to_num(m["mean_r"]):>+8.3f}{np.nan_to_num(m["ci_lo"]):>+8.3f}  {"통과" if passed else "미통과"}')
    L += ['─' * 100,
          '무작위 승률 = 방향 없는 차트에서 +목표가 −1R 보다 먼저 올 확률 1/(1+목표). 목표를 멀리 두면 승률이 정확히 그만큼 떨어지고 '
          '수수료만큼 손해다 → 손익비만으로는 이득이 생기지 않는다.',
          '기준선·실제 승률은 보유 시간이 끝나 조금이라도 번 경우도 "이김"으로 센다 → 목표가 멀수록 무작위 승률보다 높게 보인다. '
          '최종 판단은 평균R 과 CI 하한으로 한다.',
          '끝머리를 "예측했다" = 상위 10% 의 평균R 이 꾸준히 양수이고, 그 줄의 표본외 CI 하한이 0 보다 큰 것. '
          '여러 목표를 본 만큼 DSR 은 누적 절차 수로 보정된다.']
    return '\n'.join(L)


def lab_prior_reveals(engine):
    return [ev for ev in engine.state.ledger.read()
            if ev.get('kind') == 'SYSTEM' and ev.get('what') == 'lab_holdout_revealed']


def lab_record_holdout(engine, res):
    """holdout 공개는 되돌릴 수 없다 → 원장에 남긴다 (몇 번 엿봤는지가 증거의 일부)."""
    with engine.state.tx() as st:
        engine.state.emit(st, 'SYSTEM', what='lab_holdout_revealed', holdout_start=res['holdout_start'],
                          declared=res.get('declared'), cost_mode=res.get('cost_mode', 'taker'),
                          mode=res.get('mode', 'single'), symbols=res.get('symbols', [SYMBOL]),
                          top=[dict(tf=r['tf'], family=r['family'], oos=r['oos'], holdout=r['holdout'],
                                    verdict=lab_holdout_verdict(r['holdout']) if res.get('declared') else None)
                               for r in res['rows'][:5]])


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
    if '--journal' in argv:
        j = ResearchJournal.load()
        print(j.text())
        print(f'\n[연구 일지] {j.export_md()} 에도 저장했습니다.')
        return 0
    if '--lab' in argv:
        unknown = [a for a in argv if a.startswith('--') and a not in LAB_CLI_FLAGS]
        if unknown:
            print(f'[LAB] 모르는 옵션: {" ".join(unknown)} — 이 파일(빌드 {LAB_BUILD})에는 없는 기능입니다. '
                  '오타이거나 옛 파일입니다 → 최신 pattern_edge_v612.py 로 바꿨는지 확인하세요. (아무것도 실행하지 않음)')
            return 2

        def lopt(name, default):
            return argv[argv.index(name) + 1] if name in argv and len(argv) > argv.index(name) + 1 else default

        def parse_symbols(text):
            out = LAB_MAJOR_SYMBOLS if text.lower() in ('default', 'majors') else \
                LAB_ALT_SYMBOLS if text.lower() == 'alts' else \
                tuple(x.strip().upper() for x in text.split(',') if x.strip())
            bad = [x for x in out if not (x.endswith('USDT') and x[:-4].isalnum() and 2 <= len(x) - 4 <= 15)]
            if bad or not out:
                raise ValueError(f'코인 이름 형식 오류: {bad or text} (예: ETHUSDT,SOLUSDT)')
            return tuple(x for x in out if x != SYMBOL)
        cost, only, syms, retest = lopt('--cost', 'taker'), lopt('--only', None), lopt('--symbols', None), lopt('--retest', None)
        presample = '--presample' in argv
        final = lopt('--final', None) if '--final' in argv else None
        alt_pre, prosp, wick = '--alt-presample' in argv, '--prospective' in argv, '--wick' in argv
        signal = '--signal' in argv
        oracle = '--oracle' in argv
        stop_pct = None
        fees = None
        ora = dict(tf='1h', sl=0.01, tp_list=(2.0,), hold=24)
        tfs_x, tp_x = LAB_FIXED_TFS, LAB_FIXED_TP
        regime = lopt('--regime', None) if '--regime' in argv else None
        symbols = universe = None
        tfs_u = LAB_UNIVERSE_TFS
        try:
            pairs = lab_pairs(only)
            if cost not in LAB_COST_MODES:
                raise ValueError(f'알 수 없는 비용 시나리오 {cost} — 가능한 값: {", ".join(LAB_COST_MODES)}')
            if '--reveal-holdout' in argv and not only:
                raise ValueError('L9: holdout 은 --only 로 선언한 가설에만 엽니다 (모두 한꺼번에 보면 그중 좋은 것을 고르게 된다)')
            if syms:
                if not only:
                    raise ValueError('--symbols 는 --only 로 선언한 가설에만 씁니다. 예: --only 4h:flow --symbols default')
                symbols = parse_symbols(syms)
            if '--universe' in argv:
                if syms:
                    raise ValueError('--symbols(재현 검증)와 --universe(코인 묶음 탐색)는 함께 쓰지 않습니다')
                i = argv.index('--universe')
                universe = parse_symbols(argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith('--')
                                         else 'default')
                if '--tfs' in argv:
                    tfs_u = tuple(x.strip() for x in lopt('--tfs', '').split(',') if x.strip())
                    if not tfs_u or any(t not in ('15m', '1h', '4h') for t in tfs_u):
                        raise ValueError('--tfs 는 15m,1h,4h 중에서 고릅니다 (예: --tfs 1h,4h)')
            if presample and (universe or symbols or '--reveal-holdout' in argv):
                raise ValueError('--presample 은 BTC 단독 검증입니다 (--universe·--symbols·--reveal-holdout 과 함께 쓰지 않음)')
            if oracle:
                if universe or symbols or presample or alt_pre or prosp or wick or signal or only or '--final' in argv \
                        or '--regime' in argv or '--reveal-holdout' in argv or '--surrogate-n' in argv or '--surrogate' in argv:
                    raise ValueError('--oracle 은 BTC 단독 실행입니다 (--tfs·--stop-pct·--tp·--hold·--fees 만 함께 씀)')
                if cost != 'taker':
                    raise ValueError('--oracle 은 시장가 진입·청산 비용으로 정답을 매깁니다 (--cost 없이, 수수료는 --fees 로)')
                try:
                    ora['tf'] = lopt('--tfs', ora['tf']).split(',')[0].strip()
                    ora['sl'] = float(lopt('--stop-pct', ora['sl'] * 100)) / 100.0
                    ora['tp_list'] = tuple(float(x) for x in str(lopt('--tp', '2')).split(',') if x.strip())
                    ora['hold'] = int(lopt('--hold', ora['hold']))
                except ValueError:
                    raise ValueError('--oracle 옵션 형식: --tfs 1h --stop-pct 1 --tp 2 --hold 24')
                if ora['tf'] not in ('15m', '1h', '4h') or not 0.002 <= ora['sl'] <= 0.05 or not 2 <= ora['hold'] <= 500 \
                        or not 1 <= len(ora['tp_list']) <= 5 or len(set(ora['tp_list'])) != len(ora['tp_list']) \
                        or any(not 0.5 <= t <= 10 for t in ora['tp_list']):
                    raise ValueError('--oracle 범위: --tfs 15m/1h/4h · --stop-pct 0.2~5 · --tp 0.5~10 (여러 개면 쉼표, 최대 5개, '
                                     '예: --tp 2,3,5) · --hold 2~500')
            if '--fees' in argv:
                try:
                    fees = tuple(float(x) / 100.0 for x in lopt('--fees', '').split(','))
                except ValueError:
                    fees = ()
                if len(fees) != 2 or not (0 <= fees[0] <= 0.002 and 0 <= fees[1] <= 0.001):
                    raise ValueError('--fees 는 "시장가%,지정가%" 입니다 (예: --fees 0.045,0.018 · 바이낸스 선물 수수료 등급에서 확인)')
                if universe or symbols or presample or alt_pre or prosp or signal or '--final' in argv \
                        or '--regime' in argv or '--reveal-holdout' in argv:
                    raise ValueError('--fees 는 BTC 탐색(--stop-pct·--cost·--wick·--only·--surrogate-n)에만 씁니다')
            if '--stop-pct' in argv and not oracle:
                try:
                    stop_pct = float(lopt('--stop-pct', ''))
                except ValueError:
                    stop_pct = -1.0
                if not 0.2 <= stop_pct <= 5.0:
                    raise ValueError('--stop-pct 는 가격 기준 손절 % 입니다 (0.2 ~ 5, 예: --stop-pct 1)')
                if universe or symbols or presample or alt_pre or prosp or wick or signal or '--final' in argv \
                        or '--regime' in argv or '--reveal-holdout' in argv:
                    raise ValueError('--stop-pct 는 BTC 탐색(--only·--surrogate-n 포함)에만 씁니다')
                if '--tfs' in argv:
                    tfs_x = tuple(x.strip() for x in lopt('--tfs', '').split(',') if x.strip())
                    if not tfs_x or any(t not in ('5m', '15m', '1h', '4h') for t in tfs_x):
                        raise ValueError('--tfs 는 5m,15m,1h,4h 중에서 고릅니다')
                if '--tp' in argv:
                    try:
                        tp_x = (0.0,) + tuple(float(x) for x in lopt('--tp', '').split(',') if x.strip())
                    except ValueError:
                        tp_x = ()
                    if len(tp_x) < 2 or any(not 0 <= t <= 10 for t in tp_x):
                        raise ValueError('--tp 는 익절 R 배수 목록입니다 (예: --tp 2,3)')
            if (alt_pre or prosp or wick or signal) and (universe or symbols or presample or only or '--final' in argv
                                                         or '--reveal-holdout' in argv or (alt_pre + prosp + wick + signal) > 1):
                raise ValueError('--alt-presample · --prospective · --wick · --signal 은 각각 단독으로 씁니다')
            if '--regime' in argv:
                if (not regime or regime.startswith('--') or only or universe or symbols or presample or alt_pre or prosp
                        or wick or '--final' in argv or '--reveal-holdout' in argv):
                    raise ValueError('국면 검증은 단독으로 가설 하나만: --regime 4h:consensus')
                pairs = lab_pairs(regime)
                if len(pairs) != 1:
                    raise ValueError('국면 검증은 가설 하나만 (예: --regime 4h:consensus)')
            if '--final' in argv:
                if not final or final.startswith('--') or only or universe or symbols or presample or '--reveal-holdout' in argv:
                    raise ValueError('최종 검증은 단독으로 가설 하나만: --final 4h:keltner')
                pairs = lab_pairs(final)
                if len(pairs) != 1:
                    raise ValueError('최종 검증은 가설 하나만 (예: --final 4h:keltner)')
        except ValueError as e:
            print(f'[LAB] {e}')
            return 2
        journal = ResearchJournal.load()
        print(f'[LAB] {VERSION} · 빌드 {LAB_BUILD}')
        print(journal.banner())
        if fees:
            lab_set_fees(*fees)
            print(f'[LAB] 수수료: 시장가 {TAKER_FEE:.3%} · 지정가 {MAKER_FEE:.3%} · 슬리피지 {SLIPPAGE_T:.3%} '
                  '(기본값과 다른 수수료로 돌린 실행은 일지에 별개의 시험으로 센다)')
        if presample and not pairs:
            reg = next((p_ for p_ in journal.d.get('prereg', []) if p_.get('scope') == 'btc_presample'
                        and any(journal.state(f'btc_presample|{x}') == 'preregistered' for x in p_['pairs'])), None)
            if reg is None:
                print('[LAB] 판정을 기다리는 사전등록 가설이 없습니다. --only 로 가설을 지정하면 실행 직전에 등록합니다.')
                return 2
            pairs = lab_pairs(','.join(x for x in reg['pairs'] if journal.state(f'btc_presample|{x}') == 'preregistered'))
            print(f'[LAB] 사전등록 {reg["id"]} ({reg["registered"]}) 실행: {", ".join(f"{a}:{b}" for a, b in pairs)}')
        if alt_pre and not pairs:
            reg = next((p_ for p_ in journal.d.get('prereg', []) if p_.get('scope') == 'alt_presample'
                        and any(journal.state(f'alt_presample|{x}') == 'preregistered' for x in p_['pairs'])), None)
            if reg is None:
                print('[LAB] 판정을 기다리는 알트 사전등록 가설이 없습니다.')
                return 2
            pairs = lab_pairs(','.join(x for x in reg['pairs'] if journal.state(f'alt_presample|{x}') == 'preregistered'))
            print(f'[LAB] 사전등록 {reg["id"]} ({reg["registered"]}) 실행: {", ".join(f"{a}:{b}" for a, b in pairs)}')
        scope = 'regime' if regime else 'alt_presample' if alt_pre else 'final' if final else 'universe' if universe else 'cross' if symbols \
            else 'btc_presample' if presample else 'btc'
        if regime:
            pr = f'{pairs[0][0]}:{pairs[0][1]}'
            reg = next((p_ for p_ in journal.d.get('prereg', []) if p_.get('scope') == 'regime' and pr in p_['pairs']), None)
            if reg is None and not retest:
                print(f'[LAB] {pr} 는 국면 검증에 사전등록되어 있지 않습니다 (L11). 판정 규칙을 먼저 등록해야 합니다.')
                return 2
            if reg:
                print(f'[LAB] 사전등록 {reg["id"]} ({reg["registered"]}) 규칙: {reg["rule"]}')
        if final:
            pr = f'{pairs[0][0]}:{pairs[0][1]}'
            reg = next((p_ for p_ in journal.d.get('prereg', []) if p_.get('scope') == 'final' and pr in p_['pairs']), None)
            prev = journal.state(f'btc_presample|{pr}')
            if reg is None and not retest:
                print(f'[LAB] {pr} 는 최종 검증에 사전등록되어 있지 않습니다 (L9·L11). 판정 규칙을 먼저 등록해야 합니다.')
                return 2
            if prev not in ('confirmed', 'not_refuted') and not retest:
                print(f'[LAB] {pr} 는 처음 보는 구간 검증을 통과하지 않았습니다 (일지: {RESEARCH_STATE_KO.get(prev, prev)}) → '
                      '최종 검증 대상이 아닙니다 (L1).')
                return 2
            if reg:
                print(f'[LAB] 사전등록 {reg["id"]} ({reg["registered"]}) 규칙: {reg["rule"]}')
        if pairs and not prosp and not signal:
            block, warn = journal.check(scope, pairs, retest, once=presample or bool(final) or alt_pre or bool(regime))
            for w in warn:
                print(f'⚠ {w}')
            if block:
                print('[LAB] L8: 일지에 반증되었거나 이미 판정된 가설입니다 → 같은 범위에서 다시 시험하지 않습니다.\n   '
                      + '\n   '.join(block) + '\n   정말 다시 시험하려면 사유를 남기세요: --retest "사유"')
                return 2
        store = DataStore()
        store.refresh()
        base = store.base
        log = lambda t, c='': print(t)
        funding = None if '--no-funding' in argv else load_funding_history(store.http, log=log)
        if funding is None:
            print('[LAB] 펀딩비 데이터 없음 → 펀딩비 전략군 생략')
        status = log
        n_sur = int(lopt('--surrogate-n', 0) or 0)
        sur = '--surrogate' in argv and not universe and not presample
        reveal = '--reveal-holdout' in argv and not sur and n_sur <= 0 and not symbols
        anchor = journal.anchor
        eng = Engine(store=store) if reveal else None
        if reveal:
            prior = lab_prior_reveals(eng)
            if prior:
                print(f'⚠ holdout 은 이미 {len(prior)}회 공개되었습니다 '
                      f'({", ".join(str(ev.get("declared") or "전체") for ev in prior)}) — '
                      '이번 결과는 이미 본 데이터 위의 결과입니다.')
        cost_key = f'{cost}{lab_fee_tag()}'
        if oracle:
            keys = [f'btc|{ora["tf"]}:oracle|{cost_key}|sl{ora["sl"] * 100:g}tp{t:g}h{ora["hold"]}' for t in ora['tp_list']]
        elif signal:
            keys = []                                       # 신호 보기 = 시험이 아니다
        elif regime:
            keys = [f'regime|{a}:{b}|{cost}' for a, b in pairs]
        elif wick:
            keys = [f'btc|1m:wick|maker{lab_fee_tag()}']
        elif prosp:
            keys = []                                       # 같은 절차를 새 데이터로 채점 → 새 시험이 아니다
        elif alt_pre:
            keys = [f'alt_presample|{a}:{b}|{cost}' for a, b in pairs]
        elif final:
            keys = [f'final|{a}:{b}|{cost}' for a, b in pairs]
        elif universe:
            keys = lab_planned_keys('universe', tfs_u, lab_available_families(funding, universe=True), cost, pairs, True)
        elif symbols:
            keys = [f'cross|{a}:{b}|{cost}' for a, b in pairs]
        elif presample:
            keys = lab_planned_keys('btc_presample', LAB_TFS, list(LAB_GRIDS), cost, pairs)
        elif stop_pct:
            keys = lab_planned_keys('btc', tfs_x, lab_available_families(funding), f'{cost_key}|stop{stop_pct:g}', pairs)
        else:
            keys = lab_planned_keys('btc', LAB_TFS, lab_available_families(funding), cost_key, pairs)
        n_cum = journal.n_trials([] if sur else keys)

        def note(kind, title, summary='', top=(), **extra):
            try:
                journal.record(kind, [] if sur else keys, title=title, summary=summary, top=list(top),
                               args=' '.join(argv), retest=retest, **extra)
            except Exception as e_:
                print(f'⚠ 연구 일지 기록 실패: {e_}')
        try:
            if oracle:
                outs = []
                for t in ora['tp_list']:
                    res = lab_run_oracle(base, tf=ora['tf'], sl=ora['sl'], tp_r=t, hold=ora['hold'], holdout_start=anchor,
                                         funding=funding, n_trials_declared=n_cum, status=status)
                    print(res['report'] + '\n')
                    outs.append(res)
                if len(outs) > 1:
                    print(lab_oracle_map(outs))
                note('lab', f'정답 단서 학습 ({ora["tf"]}, 손절 {ora["sl"]:.1%}, 익절 {"/".join(f"{t:g}" for t in ora["tp_list"])}R, '
                     f'{ora["hold"]}봉)', top=[f'익절 {r_["tp_r"]:g}R · {x}' for r_ in outs for x in lab_top_lines(r_)])
                return 0
            if wick:
                res = lab_run_wick(base, holdout_start=anchor, n_trials_declared=n_cum, status=status)
                print(res['report'])
                note('lab', '지정가 꼬리 잡기 (BTC 1분봉 체결)', top=lab_top_lines(res))
                return 0
            if signal:
                live = [t for t in journal.d.get('tracking', []) if t.get('scope') == 'btc'
                        and journal.state(f'btc|{t["pair"]}') != 'refuted']
                if not live:
                    print('[LAB] 추적 중인 BTC 후보가 없습니다.')
                    return 0
                seed = float(lopt('--seed', os.environ.get('PATTERNEDGE_SEED', '70')))
                res = lab_live_signal(base, ','.join(t['pair'] for t in live), seed=seed, cost_mode=cost, status=status)
                print(res['report'])
                note('signal', '지금 신호 (종이 매매·연구 추적)', top=[f'{r["pair"]}: {r.get("action", r["state"])}'
                                                              for r in res['rows']])
                return 0
            if regime:
                tf_r = pairs[0][0]
                status('ETH: 스팟 아카이브 + 선물 봉 준비...')
                res = lab_regime_test(base, lab_eth_frames(store.http, (tf_r,), log=log), regime, journal.seen_from,
                                      journal.anchor, cost_mode=cost, n_trials_declared=n_cum, status=status)
                print(res['report'])
                if res['b'] is None or res['b']['n'] == 0:
                    print('[LAB] BTC 거래가 없어 판정·기록하지 않았습니다.')
                    return 0
                v = res['verdict']
                st_ = {'반증': 'refuted', '확인': 'confirmed', '반증 안 됨': 'not_refuted'}.get(v.split(' —')[0], 'inconclusive')
                why = (f'BTC {res["b"]["n"]}건 {np.nan_to_num(res["b"]["mean_r"]):+.3f}R 하한 {np.nan_to_num(res["b"]["lo"]):+.3f}'
                       + (f' · ETH {res["e"]["n"]}건 {np.nan_to_num(res["e"]["mean_r"]):+.3f}R' if res['e'] else '') + f' → {v}')
                journal.set_status(f'regime|{res["pair"]}', st_, why)
                if st_ == 'refuted':
                    journal.set_status(f'btc|{res["pair"]}', 'refuted', why)
                note('regime', f'다른 국면 검증 {res["pair"]} ({str(journal.seen_from)[:10]}~)', summary=why)
                print('[LAB] 판정이 연구 일지에 기록되었습니다 (같은 가설은 이 구간에서 다시 시험하지 않습니다).')
                return 0
            if prosp:
                tracking = [t for t in journal.d.get('tracking', [])            # 반증된 가설은 채점하지 않는다 (BTC 반증이면 ETH 도)
                            if journal.state(f'{t["scope"]}|{t["pair"]}') != 'refuted'
                            and journal.state(f'btc|{t["pair"]}') != 'refuted']
                if not tracking:
                    print('[LAB] 추적 중인 가설이 없습니다.')
                    return 0
                eth_tfs = tuple(sorted({lab_pairs(t['pair'])[0][0] for t in tracking if t.get('scope') == 'eth'},
                                       key=INTERVALS.get))
                eth_fr = lab_eth_frames(store.http, eth_tfs, log=log) if eth_tfs else None
                res = lab_prospective(base, tracking, funding=funding, cost_mode=cost, status=status, eth_frames=eth_fr)
                print(res['report'])
                for r in res['rows']:
                    if r['state'].startswith('중단'):
                        journal.set_status(f'{r["scope"]}|{r["pair"]}', 'refuted',
                                           f'앞으로의 검증({r["since"]}~) {r["n"]}건 평균R {np.nan_to_num(r["mean_r"]):+.3f} → 중단')
                note('prospective', '앞으로의 검증', top=[f'{r["scope"]}|{r["pair"]} {r["since"]}~ {r["n"]}건 평균R '
                                                      f'{np.nan_to_num(r["mean_r"]):+.3f} → {r["state"]}' for r in res['rows']])
                return 0
            if alt_pre:
                tfs_a = sorted({a for a, _ in pairs}, key=INTERVALS.get)
                frames = {}
                for sym in LAB_ALT_SYMBOLS:
                    status(f'{sym}: 스팟 이력(data.binance.vision) 준비...')
                    frames[sym] = {tf: fetch_spot_klines_vision(store.http, sym, tf, log=log) for tf in tfs_a}
                ref = {f'{a}:{b}': (journal.d['status'].get(f'btc_presample|{a}:{b}') or {}).get('why', '') for a, b in pairs}
                print('※ 알트는 보조 증거다 (L16: BTC 1순위, ETH 2순위). BTC 의 같은 구간은 P1 에서 이미 판정했으므로 참고로만 함께 보인다.')
                res = lab_alt_presample(frames, pairs, journal.seen_from, cost_mode=cost, n_trials_declared=n_cum,
                                        status=status, btc_ref=ref)
                print(res['report'])
                if not any(v['n'] > 0 for v in res['verdicts']):
                    print('[LAB] 처음 보는 알트 구간에 거래가 없어 판정·기록하지 않았습니다 (스팟 이력 다운로드를 확인하세요).')
                    return 0
                research_apply_alt_presample(journal, res['verdicts'])
                note('alt_presample', '처음 보는 알트 구간 검증 (P3)',
                     top=[f'{v["pair"]}: {v["n"]}건 평균R {np.nan_to_num(v["mean_r"]):+.3f} 하한 {np.nan_to_num(v["lo"]):+.3f} '
                          f'코인 {v["pos"]}/{v["tot"]} → {v["verdict"]}' for v in res['verdicts']])
                print('[LAB] 판정이 연구 일지에 기록되었습니다 (같은 가설은 이 구간에서 다시 시험하지 않습니다).')
                return 0
            if final:
                tf_f = pairs[0][0]
                frames, fund_by = {SYMBOL: lab_btc_frames(base, (tf_f,))}, {SYMBOL: funding}
                for sym in LAB_MAJOR_SYMBOLS:
                    status(f'{sym}: 봉 데이터 준비...')
                    frames[sym] = {tf_f: fetch_klines_tf(store.http, sym, tf_f, log=log)}
                    if funding is not None:
                        fund_by[sym] = load_funding_history(store.http, symbol=sym, log=log)
                res = lab_final_test(base, frames, final, anchor, funding=funding, funding_by_symbol=fund_by, cost_mode=cost,
                                     n_trials_declared=n_cum, status=status)
                print(res['report'])
                if res['b']['n'] + (res['u']['n'] if res['u'] else 0) == 0:
                    print('[LAB] holdout 거래가 없어 소진하지 않았습니다.')
                    return 0
                eng_f = Engine(store=store)
                for part in (res['btc'], res['uni']):
                    if part:
                        lab_record_holdout(eng_f, part)
                v = res['verdict']
                st_ = 'refuted' if v.startswith('반증 —') else 'holdout_passed' if v.startswith('확인') else 'not_refuted' \
                    if v.startswith('반증 안 됨') else 'inconclusive'
                why = (f'holdout BTC {res["b"]["n"]}건 {np.nan_to_num(res["b"]["mean_r"]):+.3f}R'
                       + (f' · 묶음 {res["u"]["n"]}건 {np.nan_to_num(res["u"]["mean_r"]):+.3f}R 하한 '
                          f'{np.nan_to_num(res["u"]["ci_lo"]):+.3f}' if res['u'] else '') + f' → {v}')
                for sc in ('final', 'btc', 'universe'):
                    journal.set_status(f'{sc}|{res["pair"]}', st_, why)
                journal.consume_holdout([res['pair']], {res['pair']: v})
                note('final', f'최종 검증 {res["pair"]} (holdout {res["holdout_start"][:10]}~)', summary=why)
                print('[LAB] 최종 판정이 원장과 연구 일지에 기록되었고 holdout 이 소진되었습니다. 오늘 이후 데이터가 새 holdout 입니다.')
                return 0
            if universe:
                frames, fund_by = {SYMBOL: lab_btc_frames(base, tfs_u)}, {SYMBOL: funding}
                for sym in universe:
                    status(f'{sym}: 봉 데이터 준비...')
                    frames[sym] = {tf: fetch_klines_tf(store.http, sym, tf, log=log) for tf in tfs_u}
                    if funding is not None:
                        fund_by[sym] = load_funding_history(store.http, symbol=sym, log=log)
                kw = dict(tfs=tfs_u, cost_mode=cost, funding_by_symbol=fund_by, only=only, n_trials_declared=n_cum,
                          holdout_start=anchor)
                if n_sur > 0:
                    res = lab_universe_surrogate_test(frames, n_sur, status=status, **kw)
                    print(res['real']['report'])
                    print(res['report'])
                    note('luck', f'코인 묶음 가짜 {n_sur}개 비교', top=res['report'].splitlines()[1:9])
                    return 0
                res = lab_run_universe(frames, reveal_holdout=reveal, status=status, **kw)
                title = f'코인 묶음 {len(res["symbols"])}개 · 절차 {res["n_trials"]}개'
            elif symbols:
                res = lab_cross_asset(base, only, symbols, http=store.http, cost_mode=cost, funding=funding,
                                      n_trials_declared=n_cum, status=status, holdout_start=anchor)
                print(res['report'])
                if any(x['n'] > 0 for x in res['summary']):
                    lab_record_cross_asset(Engine(store=store), res)
                    for x in res['summary']:
                        st_ = 'refuted' if x['verdict'].startswith('재현 실패') else \
                            'confirmed' if x['verdict'].startswith('재현 확인') else 'inconclusive'
                        journal.set_status(f'cross|{x["pair"]}', st_, f'{x["n"]}건 평균R {x["mean_r"]:+.3f} → {x["verdict"]}')
                    note('cross', f'재현 검증 {", ".join(x["pair"] for x in res["summary"])} → {len(res["symbols"])}개 코인',
                         top=[f'{x["pair"]}: {x["n"]}건 평균R {x["mean_r"]:+.3f} 하한 {np.nan_to_num(x["ci_lo"]):+.3f} → {x["verdict"]}'
                              for x in res['summary']])
                    print('[LAB] 재현 검증 결과가 원장과 연구 일지에 기록되었습니다.')
                else:
                    print('[LAB] 알트 봉을 하나도 받지 못해 기록하지 않았습니다 (네트워크 확인 후 다시).')
                return 0
            elif presample:
                res = lab_presample(base, pairs, journal.seen_from, funding=funding, cost_mode=cost,
                                    n_trials_declared=n_cum, status=status)
                print(res['report'])
                research_apply_presample(journal, res['presample'])
                note('presample', '처음 보는 BTC 구간 검증', top=[f'{v["pair"]}: {v["n"]}건 평균R {np.nan_to_num(v["mean_r"]):+.3f} '
                                                          f'하한 {np.nan_to_num(v["lo"]):+.3f} → {v["verdict"]}'
                                                          for v in res['presample']])
                print('[LAB] 판정이 연구 일지에 기록되었습니다 (같은 가설은 이 구간에서 다시 시험하지 않습니다).')
                return 0
            else:
                fx = dict(tfs=tfs_x, fixed_stop=stop_pct / 100.0, tp_list=tp_x) if stop_pct else {}
                if n_sur > 0:
                    res = lab_surrogate_test(base, n_sur, only=only, cost_mode=cost, funding=funding,
                                             n_trials_declared=n_cum, status=status, holdout_start=anchor, **fx)
                    print(res['real']['report'])
                    print(res['report'])
                    note('luck', f'BTC 가짜 {n_sur}개 비교', top=res['report'].splitlines()[1:9])
                    return 0
                if sur:
                    base = make_surrogate_1m(base, seed=1)
                    print('★ 가짜 BTC(하루 블록 셔플) — 여기서 나오는 최고 성적이 "운의 크기"다 ★')
                res = lab_run(base, reveal_holdout=reveal, status=status, cost_mode=cost, only=only, funding=funding,
                              n_trials_declared=n_cum, holdout_start=anchor, **fx)
                title = ('가짜 BTC ' if sur else 'BTC ') + f'절차 {res["n_trials"]}개' + \
                    (f' · 가격 {stop_pct:g}% 고정 손절' if stop_pct else '')
        except ValueError as e:
            print(f'[LAB] {e}')
            return 2
        print(res['report'])
        if reveal:
            lab_record_holdout(eng, res)
            verdicts = {f'{r["tf"]}:{r["family"]}': lab_holdout_verdict(r['holdout']) for r in res['rows']}
            for pr, v in verdicts.items():
                journal.set_status(f'{scope}|{pr}', 'refuted' if v.startswith('반증 —') else
                                   'holdout_passed' if v.startswith('확인') else 'inconclusive', f'holdout: {v}')
            journal.consume_holdout(res.get('declared'), verdicts)
            print('[LAB] holdout 공개가 원장과 연구 일지에 기록되었습니다. 이 구간은 이제 "본 데이터"이고, '
                  '지금부터의 데이터가 새 holdout 입니다.')
        note('surrogate' if sur else scope if scope != 'btc' else 'lab', title + (' · holdout 공개' if reveal else ''),
             top=lab_top_lines(res))
        return 0
    if '--walkforward' in argv:
        i = argv.index('--walkforward')
        tf = argv[i + 1] if len(argv) > i + 1 else '15m'
        start = argv[i + 2] if len(argv) > i + 2 else (utcnow() - timedelta(days=365)).strftime('%Y-%m-%d')
        def opt(name, default):
            return argv[argv.index(name) + 1] if name in argv and len(argv) > argv.index(name) + 1 else default
        store = DataStore()
        store.refresh()
        base = store.base
        if '--surrogate' in argv:
            base = make_surrogate_1m(base, seed=int(opt('--surrogate-seed', 1)))
            print('★ 가짜 BTC(하루 블록 셔플) — 여기서도 벌면 엣지가 아니라 곡선맞춤 ★')
        res = walk_forward(base, tf, start, do_null='--null' in argv, status=lambda t, c='': print(t),
                           workers=int(opt('--workers', WF_DEFAULT_WORKERS)),
                           step=int(opt('--step', 0)) or None, use_cache='--no-cache' not in argv)
        print(res['report'])
        cert = Engine(store=store).record_walkforward(tf, res, '--null' in argv, '--surrogate' in argv,
                                                      data_note='CLI · 로컬 캐시 1분봉')
        print(f"[EVIDENCE] {tf}: {cert['level']} (model {MODEL_ID}) — 원장에 기록됨")
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
