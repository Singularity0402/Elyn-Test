# -*- coding: utf-8 -*-
"""
================================================================================
 PatternEdge V610 "MISSED SIGNAL GUARD"
 BTCUSDT 무기한선물 — Analog-first 기억 매매 · 통계 검증 · 자동 주문표

 [V400 핵심 철학]
   1) 방향의 1차 근거는 언제나 "현재와 가장 닮은 과거 차트"다.
   2) 기계는 인간보다 훨씬 많은 과거를 기억하되, 가장 닮은 1개가 아니라
      서로 독립적인 analog cluster의 미래분포를 본다.
   3) LONG/SHORT를 각각 독립적으로 검증한다. 어느 쪽도 강하지 않으면 WAIT.
   4) 주문흐름·펀딩·프리미엄·스프레드·변동성은 방향 예측기가 아니라
      analog를 믿어도 되는지 확인하는 Context Validator다.
   5) OOF / purge / cluster bootstrap / 유효표본수 / robust Kelly가
      우연한 쌍둥이 패턴과 과대 베팅을 제거한다.
   6) 사용자가 보는 결과는 ENTRY / TP / SL / 시드% / 레버리지 / 수량뿐이다.

 [Legacy]
 PatternEdge V200 "ANALOG DESK"
 BTCUSDT 무기한선물 — 과거 아날로그(유사 국면) 검색 · 유의성 검정 · 매매 계획
================================================================================

 [이 프로그램이 V101과 다른 점 — 한 줄 요약]
   V101은 "가장 닮은 과거를 찾아 그 평균 방향으로 베팅"했다.
   V200은 "닮은 과거의 미래가, 아무 과거나 뽑은 것과 통계적으로 다른가"를 먼저
   검정하고, 다르지 않으면 아무것도 하지 않는다.
   ── 이것이 시타델/르네상스류 데스크와 개인 백테스터를 가르는 유일한 선이다.

 [왜 그렇게 바꿨는가 — 반드시 읽을 것]
   길이 288인 창(窓)이 350만 개 있는 시계열에서, 완전한 난수(랜덤워크)로 만든
   데이터에서도 상관계수 0.97~0.99짜리 "쌍둥이 패턴"은 반드시 나온다.
   창이 많을수록 최대상관은 1에 수렴한다. 즉 '눈으로 봐도 똑같은 과거'를 찾는 것은
   난이도가 아니라 필연이며, 그 자체로는 정보가 0이다.
   진짜 질문은 이것 하나뿐이다:

       "이 이웃들의 '다음 H봉'의 분포가, 같은 구간에서 무작위로 뽑은
        같은 개수의 창들의 '다음 H봉' 분포와 유의하게 다른가?"

   V200은 매 신호마다 블록 부트스트랩으로 귀무분포를 만들어 p-value를 계산한다.
   p가 크면 아무리 상관계수가 0.99여도 '관망'을 출력한다.

 [핵심 개선 목록]
   1. 데이터  : 바이낸스 공식 아카이브(data.binance.vision) 월별 벌크로
                USDⓈ-M 선물 1분봉 전 구간(2019-09-08~) 일괄 구축.
                옵션으로 2017-08~2019-09 스팟 1분봉을 '검색 라이브러리'로만 접합
                (구간 경계를 넘는 창은 자동 배제 → 접합 불연속 오염 없음).
                5m/15m/1h는 1분봉 리샘플로 생성 → TF별 재다운로드 없음.
   2. 갱신버그: get_historical_klines(..., str(ms)) 가 dateparser에서 터져
                except로 삼켜지던 문제(=스캔해도 갱신 안 됨)를 fapi REST 직접
                호출로 교체. 신선도(지연 분)를 리포트 최상단에 강제 표시.
   3. 표현    : 가격 모양 한 채널 → 5채널(로그가격 형상 / 로그수익률 / 변동성 궤적 /
                테이커 매수비중(주문흐름 대용) / 레인지 구조)로 확장.
                각 채널은 MASS(FFT)로 전 구간 정확 상관을 O(n log n)에 계산.
   4. 무근사  : 게이트를 통과한 후보만 '직접 내적'으로 상관을 재계산해 FFT
                수치오차까지 제거(검증 컬럼으로 표시). 그 후 DTW ±5% 밴드 재순위.
   5. 편향제거: TP/SL을 이웃 전체에서 최대화하던 인샘플 선택편향을 제거.
                이웃을 2겹으로 갈라 A에서 고르고 B에서 평가(교대 2-fold) →
                보고되는 기대값은 '고를 때 보지 않은 표본'의 값이다.
   6. 유의성  : 정상 블록 부트스트랩 귀무분포 대비 p-value. 기본 p<0.05 요구.
   7. 체결현실: 5m/15m 신호의 TP/SL 선후 판정을 1분봉 경로로 수행(같은 봉 안에서
                무엇이 먼저 닿았는지까지 재현). 동시 도달은 항상 손절 처리.
                왕복 수수료·슬리피지에 더해 '펀딩비 예상 크로싱'까지 비용에 차감.
   8. 지지저항: 스윙 피벗 + 볼륨 프로파일로 레벨을 뽑아, 손절을 '무효화 레벨
                바로 바깥'에, 익절을 '반대편 레벨 직전'에 재배치(워뇨띠식 레벨 매매).
   9. 다중스케일: K를 3개(0.5x/1x/2x) 동시 스캔해 방향 합의를 요구.
                단일 스케일 우연 일치를 크게 걸러낸다.
  10. 사이징  : 사용자 원칙(증거금 10%, 리스크 1%)을 상한으로 두고,
                Wilson 하한 승률로 계산한 1/4 켈리를 추가 상한으로 적용.
                = '점추정이 아니라 신뢰구간 하단에 베팅한다'
  11. 검증    : 퍼지(purge)+엠바고 워크포워드. 성과는 DSR(Deflated Sharpe)로
                시행횟수 보정 후 판정.

 [사용자 리스크 원칙 — 절대 규칙]
   · 잃지 않는 것이 최우선.
   · 전체 시드의 10%만 격리(Isolated) 증거금으로 사용한다.
   · 트레이드당 최대 손실 = 전체 시드의 1%.
   · 하루 누적 손실이 시드의 3%면 그날 매매 중단.
   · 레버리지는 '입력'이 아니라 리스크와 손절거리에서 나오는 '출력'이다.
   · 기대값이 0 이하이거나 유의하지 않으면 스스로 관망을 출력한다.

 [소액 계좌 경고 — 71 USDT 기준]
   BTCUSDT 무기한의 최소 주문 명목가는 100 USDT다.
   시드 71 · 리스크 1%(=0.71 USDT)로 명목 100을 채우려면
   (손절거리 + 왕복비용) ≤ 0.71% 여야 한다. 왕복 테이커 비용이 0.14%이므로
   손절은 0.57% 이내여야 한다. 15분봉에서 0.57%는 소음에 자주 스치는 거리다.
   → 이 프로그램은 매 신호마다 '규칙 내 실행 가능 여부'를 판정하고,
      불가하면 필요한 조건(최대 손절거리·필요 리스크%)을 숫자로 보여준다.
   → 소액에서 가장 확실한 '엣지'는 예측이 아니라 비용이다.
      지정가(메이커) 진입/청산으로 왕복 0.14% → 0.036%까지 줄이면
      같은 전략의 순기대값이 배 이상 달라진다. ENTRY_TYPE/TP_TYPE/SL_TYPE 설정을 볼 것.

 설치 :  pip install pandas numpy requests mplfinance
         pip install pyarrow numba          (선택이지만 강력 권장)
 실행 :  python pattern_edge_v200.py        (IDLE 말고 터미널 권장)

 면책 :  이 도구는 통계적 참고 자료다. 과거의 유사성은 미래를 보장하지 않는다.
         모든 주문과 손실의 책임은 사용자에게 있다.
================================================================================
"""

from __future__ import annotations

import io
import os
import sys
import json
import math
import time
import zipfile
import threading
import warnings
from datetime import datetime, timedelta, timezone, time as dt_time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

__version__ = 'V610-MISSED-SIGNAL-GUARD'

# ─────────────────────────── 선택 의존성 ────────────────────────────
try:
    import requests
    REQUESTS_OK = True
except Exception:
    REQUESTS_OK = False
    import urllib.request

try:
    import pyarrow  # noqa: F401
    PARQUET_OK = True
except Exception:
    PARQUET_OK = False

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
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MPL_OK = True
except Exception:
    MPL_OK = False

# =============================================================================
# [1] 설정
# =============================================================================
SYMBOL = 'BTCUSDT'

# 봉 단위(분). 1m은 '저장·정밀체결 전용', 실매매 참고는 5m/15m 권장.
INTERVALS = {'1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240}
TRADE_TF_DEFAULT = '15m'

# TF별 권장 K(패턴 길이) / H(관찰 지평)
RECOMMENDED = {
    '1m':  (240, 120),
    '3m':  (240, 120),
    '5m':  (288, 144),   # 24시간 패턴 → 12시간 관찰
    '15m': (192,  96),   # 48시간 패턴 → 24시간 관찰
    '30m': (168,  84),
    '1h':  (168,  84),   # 7일 패턴 → 3.5일 관찰
    '4h':  (180,  90),
}


# ── V300 ONE-CLICK 운영 모드 ─────────────────────────────────────
# 사용자는 시드만 입력한다. 나머지는 검증된 프리셋으로 고정한다.
# 메인 스캔은 뉴욕 정규장 개장(09:30 ET) 12분 전인 09:18 ET에 1회 실행한다.
# ZoneInfo가 미국 DST를 자동 처리하므로 KST 기준으로는 보통:
#   서머타임 22:18 / 비서머타임 23:18
# 토/일은 미국 정규장이 없으므로 자동 스캔하지 않는다.
ONECLICK_TF       = '15m'
ONECLICK_K        = 192              # 48시간 문맥
ONECLICK_H        = 16               # 최대 4시간 보유(15m × 16)
ONECLICK_TOPK     = 40
ONECLICK_USE_1M   = True
ONECLICK_MULTI    = True
SESSION_TZ        = 'America/New_York'
DISPLAY_TZ        = 'Asia/Seoul'
SESSION_HOUR_ET   = 9
SESSION_MINUTE_ET = 18
SESSION_WEEKDAYS  = {0, 1, 2, 3, 4}  # Mon~Fri
AUTO_POLL_MS      = 10_000
V610_CHART_ANALOGS = 3
V610_CHART_LOOKAHEAD = 1.0   # future pane uses full H

# ── 데이터 소스 ──────────────────────────────────────────────────
VISION_BASE = 'https://data.binance.vision/data'
FAPI_BASE = 'https://fapi.binance.com'
FUT_FIRST_MONTH = (2019, 9)     # USDⓈ-M BTCUSDT 무기한 최초 (2019-09-08)
SPOT_FIRST_MONTH = (2017, 8)    # 스팟 BTCUSDT 최초 (2017-08-17)
USE_SPOT_PREHISTORY = True      # 2017-08~2019-09 스팟을 '검색 라이브러리'로 접합
MAX_STALE_MIN = 5               # 이보다 지연되면 리포트에 경고 표시

# ── 리스크 원칙 (사용자 지정) ────────────────────────────────────
#  V200.1에서 사용자 규칙에 맞춰 변경:
#    "시드 20%를 격리 증거금으로, 1회 손실은 총자산 대비 -2% 안쪽,
#     레버리지는 자연수. 베팅 비율은 늘리되 배율은 낮춘다."
MARGIN_CAP        = 0.20    # 격리 증거금 = 시드의 20%
RISK_PER_TRADE    = 0.02    # 트레이드당 최대 손실 = 시드의 2%
DAILY_LOSS_LIMIT  = 0.06    # 일일 -6%(=연속 3패) 도달 시 중단 — 파생값, 조정 가능
MAX_LEV           = 25.0
INTEGER_LEVERAGE  = True    # 레버리지를 자연수로 내림 (거래소 실제 동작)
MIN_NOTIONAL      = 50.0   # BTCUSDT 무기한 최소 명목가 (거래소 규정, 변동 가능)
KELLY_FRACTION    = 0.25    # 1/4 켈리 상한
KELLY_CONF        = 0.95    # 승률 Wilson 하한 신뢰수준

# ── 가격 라운딩 (사용자 규칙: 뒤 두 자리를 00 또는 50으로) ────────
ROUND_TICK     = 50.0       # 이 단위로 스냅 (뒤 두 자리가 00 또는 50이 된다)
ROUND_LEVELS   = True
SL_EXTRA_TICKS = 1          # 손절은 스냅 후 한 칸 더 바깥으로 (46580 → 46550 → 46500)
                            # 0으로 두면 가장 가까운 00/50에만 맞춘다
#  익절 = 목표(저항/지지)보다 '살짝 안쪽'  → 먼저 체결되도록 보수적으로
#  손절 = 무효화 변곡점보다 '살짝 바깥'    → 소음에 덜 스치도록 널널하게

# ── 비용 모델 ────────────────────────────────────────────────────
#  사용자 규칙: 진입 = 시장가, 익절 = 지정가(메이커), 손절 = 시장가(테이커)
#  → 승/패에 따라 비용이 다르다. 승리는 싸고 패배는 비싸다.
ENTRY_TYPE = 'taker'        # 'taker' 시장가 진입 / 'maker' 지정가 진입
TP_TYPE    = 'maker'        # 익절 지정가
SL_TYPE    = 'taker'        # 손절 시장가
TAKER_FEE  = 0.00050
MAKER_FEE  = 0.00020
SLIPPAGE_T = 0.00020        # 시장가 편도 슬리피지 가정
FUNDING_PER_8H = 0.00010    # 펀딩비 절대값 보수 가정(8시간마다)

# ── 패턴 검색 파라미터 ───────────────────────────────────────────
CH_WEIGHTS = {              # 채널별 가중치 (거리 결합용)
    'shape': 0.40,          # 로그가격 형상
    'ret':   0.25,          # 로그수익률(동역학)
    'vol':   0.15,          # 변동성 궤적
    'flow':  0.12,          # 테이커 매수비중 (주문흐름 대용)
    'rng':   0.08,          # 봉 레인지 구조
}
GATE_STEPS = [              # (shape corr, ret corr, flow corr) 하한 — 순차 완화
    (0.92, 0.30, -0.05),
    (0.88, 0.22, -0.15),
    (0.84, 0.15, -0.30),    # 이 단계부터 추세 게이트 해제
    (0.78, 0.08, -0.50),
    (0.70, 0.00, -1.00),
]
GATE_NAMES = ['엄격', '1단계 완화', '2단계 완화', '3단계 완화', '4단계 완화',
              '★관측 전용(게이트 미통과)']
TREND_GATE_UNTIL = 2        # 이 인덱스까지만 추세 게이트 적용
OBSERVE_FALLBACK = True     # 게이트를 못 넘어도 '가장 닮은 과거'는 항상 보여준다
                            # (차트·베스트매치용. 이 경우 매매 신호는 절대 내지 않는다)
VOL_TOL       = 1.8         # 변동성 배율 허용 0.56x~1.8x
TREND_TOL     = 2.5         # 상위추세 기울기 배율 허용
DTW_BAND_FRAC = 0.05        # DTW 시간왜곡 밴드 ±5%
CAND_POOL     = 500         # DTW 정밀 재순위 후보 수
TOPK          = 40          # 최종 이웃 수
EXCL_FRAC     = 0.60        # 이웃 간 최소 간격 = K × 0.60
MIN_NEIGHBORS = 20          # 이 미만이면 통계 불가 → 관망

# ── 판정 임계 ────────────────────────────────────────────────────
UP_TH, DN_TH  = 0.58, 0.42  # 이웃 상승비율
MIN_RR        = 1.3         # 최소 손익비
PVAL_MAX      = 0.05        # 부트스트랩 유의수준
BOOT_N        = 400         # 부트스트랩 반복
BOOT_CHUNK    = 40
EDGE_COST_MULT = 2.0        # 순기대값 ≥ 왕복비용 × 이 배수 를 요구
MULTISCALE    = True        # K를 0.5x/1x/2x 로 동시 스캔해 합의 요구

SCALE_FACTORS = (0.5, 1.0, 2.0)


def _leg(kind):
    return (TAKER_FEE + SLIPPAGE_T) if kind == 'taker' else MAKER_FEE


def cost_win():
    """익절로 끝났을 때의 왕복 비용 (진입 + 지정가 익절)"""
    return _leg(ENTRY_TYPE) + _leg(TP_TYPE)


def cost_lose():
    """손절/만기청산으로 끝났을 때의 왕복 비용 (진입 + 시장가 청산)"""
    return _leg(ENTRY_TYPE) + _leg(SL_TYPE)


def fee_round_trip():
    """대표 왕복비용 — 표시·문턱용으로 보수적인 쪽(손절 경로)을 쓴다"""
    return cost_lose()


def funding_cost(tf, H):
    """H봉 보유 중 예상 펀딩 크로싱 비용(보수적으로 항상 지불한다고 가정)"""
    hours = INTERVALS[tf] * H / 60.0
    return FUNDING_PER_8H * (hours / 8.0)


def net_pnl(pnl, code, tf, H):
    """
    결과별 비용을 차감한 순손익.
      code  1 익절 → 진입비용 + 메이커
      code -1 손절 / 0 만기청산 → 진입비용 + 테이커(+슬리피지)
    ※ 스칼라 하나로 비용을 빼면 '지정가 익절'의 이점이 통계에 반영되지 않는다.
    """
    f = funding_cost(tf, H)
    c = np.where(np.asarray(code) == 1, cost_win(), cost_lose()) + f
    return np.asarray(pnl, dtype=np.float64) - c


def snap(price, side, kind):
    """
    뒤 두 자리를 00/50으로 스냅 (사용자 규칙).
      kind='tp' → 목표보다 안쪽(먼저 체결되게)   롱: 내림 / 숏: 올림
      kind='sl' → 무효화점보다 바깥(널널하게)    롱: 내림 / 숏: 올림
    두 경우 모두 롱이면 내림, 숏이면 올림이라 식은 같지만 의미가 다르다.
    """
    if not ROUND_LEVELS or ROUND_TICK <= 0:
        return float(price)
    t = float(ROUND_TICK)
    out = float(np.floor(price / t) * t) if side > 0 else \
        float(np.ceil(price / t) * t)
    if kind == 'sl' and SL_EXTRA_TICKS:
        out += (-t if side > 0 else t) * SL_EXTRA_TICKS
    return out


# =============================================================================
# [2] 경로 · 유틸
# =============================================================================
BASE_DIR = r'C:\CoinData_Matrix'
try:
    os.makedirs(BASE_DIR, exist_ok=True)
    _t = os.path.join(BASE_DIR, '.wtest')
    open(_t, 'w').close()
    os.remove(_t)
except Exception:
    BASE_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'CoinData_Matrix')
    os.makedirs(BASE_DIR, exist_ok=True)

RAW_DIR = os.path.join(BASE_DIR, 'raw')
os.makedirs(RAW_DIR, exist_ok=True)
JOURNAL_PATH = os.path.join(BASE_DIR, f'{SYMBOL}_signals_v200.csv')
JCOLS = ['signal_time', 'tf', 'K', 'H', 'side', 'entry', 'tp_px', 'sl_px',
         'tp', 'sl', 'p_up', 'exp_oof', 'pval', 'n_nb', 'status', 'pnl', 'note']


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def floor_time(dt, minutes):
    epoch = datetime(1970, 1, 1)
    k = int((dt - epoch).total_seconds() // (minutes * 60))
    return epoch + timedelta(minutes=minutes * k)


def month_iter(y0, m0, y1, m1):
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def http_get(url, timeout=60):
    if REQUESTS_OK:
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            raise IOError(f'HTTP {r.status_code} {url}')
        return r.content
    req = urllib.request.Request(url, headers={'User-Agent': 'PatternEdge/2.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# =============================================================================
# [3] 데이터 레이어  —  ★ V101 "갱신 안 됨" 버그의 원인과 수정 ★
# -----------------------------------------------------------------------------
#  원인: V101은 증분 갱신 시  get_historical_klines(SYMBOL, tf, str(last_ms)) 로
#        '밀리초 숫자를 문자열로' 넘겼다. python-binance는 문자열을 dateparser로
#        해석하려 하고, 13자리 숫자 문자열은 날짜로 파싱되지 않아 None을 반환 →
#        int(None - epoch) 에서 TypeError. 그 예외를 _update 의 except가
#        조용히 삼키고 '기존 데이터로 진행'을 status에 한 줄 띄운 뒤 반환했다.
#        상태줄은 다음 메시지에 곧바로 덮여서, 사용자 눈에는
#        "스캔은 되는데 데이터가 영원히 갱신되지 않는" 증상으로만 보였다.
#        게다가 신선도 판정이 (마지막봉 + 2×TF > now) 라서 한두 봉 뒤처져도
#        '최신'으로 착각해 아예 갱신 시도조차 하지 않는 경우가 있었다.
#        결정적으로 V101은 '스팟' 캔들을 받고 있었다(선물 기준이 아님).
#  수정: (a) fapi(선물) REST를 startTime/endTime 정수 ms로 직접 페이징 호출
#        (b) 신선도는 '기대되는 마지막 완결봉'과 직접 비교
#        (c) 실패를 삼키지 않고 예외 메시지를 리포트 최상단에 노출
#        (d) 1분봉만 원본으로 저장하고 상위 TF는 리샘플 → 갱신 지점이 하나뿐
# =============================================================================
VISION_COLS = ['open_time', 'open', 'high', 'low', 'close', 'volume',
               'close_time', 'quote_volume', 'trades',
               'taker_buy_base', 'taker_buy_quote', 'ignore']
STORE_COLS = ['open', 'high', 'low', 'close', 'volume', 'taker_buy_base',
              'trades', 'era']
ERA_FUT, ERA_SPOT = 1, 0


def _normalize_epoch(series):
    """바이낸스 아카이브는 파일 시기에 따라 ms/us 가 섞여 있다 → ms로 정규화"""
    v = pd.to_numeric(series, errors='coerce').astype('float64')
    med = np.nanmedian(v)
    if med > 1e15:          # microseconds
        v = v / 1000.0
    elif med > 1e13:        # 잘못된 단위 방어
        v = v / 1000.0
    return v.astype('int64')


def _parse_vision_csv(raw_bytes, era):
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            head = f.readline()
        with z.open(name) as f:
            first = head.decode('utf-8', 'ignore').split(',')[0].strip()
            has_header = not first.replace('.', '').isdigit()
            df = pd.read_csv(f, header=0 if has_header else None,
                             names=VISION_COLS, usecols=range(12))
    ts = _normalize_epoch(df['open_time'])
    out = pd.DataFrame({
        'open': df['open'].astype('float64'),
        'high': df['high'].astype('float64'),
        'low': df['low'].astype('float64'),
        'close': df['close'].astype('float64'),
        'volume': df['volume'].astype('float64'),
        'taker_buy_base': df['taker_buy_base'].astype('float64'),
        'trades': pd.to_numeric(df['trades'], errors='coerce').fillna(0).astype('float64'),
    })
    out['era'] = np.float64(era)
    out.index = pd.to_datetime(ts, unit='ms')
    out.index.name = 'timestamp'
    return out.sort_index()


def _rest_klines(interval, start_ms, end_ms=None, limit=1500):
    """선물(fapi) 캔들 직접 호출 — 정수 ms만 사용한다 (V101 버그의 핵심 수정점)"""
    url = (f'{FAPI_BASE}/fapi/v1/klines?symbol={SYMBOL}&interval={interval}'
           f'&startTime={int(start_ms)}&limit={int(limit)}')
    if end_ms is not None:
        url += f'&endTime={int(end_ms)}'
    data = json.loads(http_get(url, timeout=30).decode('utf-8'))
    if not data:
        return None
    arr = np.array(data, dtype=object)
    out = pd.DataFrame({
        'open': arr[:, 1].astype('float64'),
        'high': arr[:, 2].astype('float64'),
        'low': arr[:, 3].astype('float64'),
        'close': arr[:, 4].astype('float64'),
        'volume': arr[:, 5].astype('float64'),
        'taker_buy_base': arr[:, 9].astype('float64'),
        'trades': arr[:, 8].astype('float64'),
    })
    out['era'] = np.float64(ERA_FUT)
    out.index = pd.to_datetime(arr[:, 0].astype('int64'), unit='ms')
    out.index.name = 'timestamp'
    return out.sort_index()


class DataManager:
    """1분봉을 유일한 원본으로 저장하고, 모든 상위 TF는 리샘플로 파생시킨다."""

    def __init__(self, log=None):
        self.log = log or (lambda *a, **k: None)
        self.base = None                  # 1m DataFrame
        self.res_cache = {}               # tf -> DataFrame
        self.lock = threading.Lock()
        self.last_error = ''
        self.meta = {}

    # ── 저장 경로 ────────────────────────────────────────────────
    @staticmethod
    def _paths():
        return (os.path.join(BASE_DIR, f'{SYMBOL}_1m_v200.parquet'),
                os.path.join(BASE_DIR, f'{SYMBOL}_1m_v200.csv'))

    def _path(self):
        pq, cs = self._paths()
        return pq if PARQUET_OK else cs

    def _save(self, df):
        p = self._path()
        try:
            # 저장 직전에도 정규화 — 깨진 인덱스를 디스크에 다시 굳히지 않는다
            df = self.normalize_index(df, self.log)
            tmp = p + '.tmp'
            if PARQUET_OK:
                df.to_parquet(tmp)
            else:
                # ISO 형식으로 못 박아 저장한다. 형식이 섞이면 다음 로드 때
                # pandas 가 인덱스 전체를 문자열로 돌려주기 때문이다.
                df.to_csv(tmp, date_format='%Y-%m-%d %H:%M:%S')
            os.replace(tmp, p)
        except Exception as e:
            self.log(f'[저장 실패] {e}', 'red')

    def _load_disk(self):
        # ★ 버그 수정: 예전에는 '현재 설정의 확장자' 하나만 확인해서, pyarrow를
        #   나중에 설치하면 이미 받아둔 CSV를 못 찾고 전체를 다시 내려받았다.
        #   이제 parquet/CSV 둘 다 확인하고, CSV만 있으면 parquet로 자동 승격한다.
        pq, cs = self._paths()
        try:
            if PARQUET_OK and os.path.exists(pq):
                df = pd.read_parquet(pq)
            elif os.path.exists(cs):
                df = pd.read_csv(cs, index_col='timestamp', parse_dates=True)
                broken = not isinstance(df.index, pd.DatetimeIndex)
                df = self.normalize_index(df, self.log)   # 승격 전에 반드시 정규화
                if PARQUET_OK:
                    try:
                        df.to_parquet(pq)     # 다음부터 고속 로딩
                    except Exception:
                        pass
                elif broken:
                    # 복구본을 즉시 되써서 다음 실행에 또 복구하지 않게 한다
                    try:
                        tmp = cs + '.tmp'
                        df.to_csv(tmp, date_format='%Y-%m-%d %H:%M:%S')
                        os.replace(tmp, cs)
                        self.log('[캐시 복구] 정상 형식으로 다시 저장했습니다.', 'green')
                    except Exception:
                        pass
            elif os.path.exists(pq):
                df = pd.read_parquet(pq)
            else:
                return None
            for c in STORE_COLS:
                if c not in df.columns:
                    df[c] = np.float64(ERA_FUT if c == 'era' else 0.0)
            df = df[STORE_COLS].astype('float64')
            return self.normalize_index(df, self.log)
        except Exception as e:
            self.log(f'[로드 실패] {e}', 'red')
            return None

    # ── 벌크 구축 (data.binance.vision) ──────────────────────────
    def build_full_history(self, use_spot=USE_SPOT_PREHISTORY, progress=None):
        parts = []
        now = utcnow()
        jobs = []
        if use_spot:
            y1, m1 = FUT_FIRST_MONTH
            # 스팟은 선물 시작 직전 달까지만 (겹치면 선물이 우선)
            em = (y1, m1 - 1) if m1 > 1 else (y1 - 1, 12)
            for y, m in month_iter(*SPOT_FIRST_MONTH, *em):
                jobs.append(('spot', y, m))
        for y, m in month_iter(*FUT_FIRST_MONTH, now.year, now.month):
            jobs.append(('futures/um', y, m))

        total = len(jobs)
        ok = 0
        for i, (market, y, m) in enumerate(jobs, 1):
            era = ERA_SPOT if market == 'spot' else ERA_FUT
            url = (f'{VISION_BASE}/{market}/monthly/klines/{SYMBOL}/1m/'
                   f'{SYMBOL}-1m-{y:04d}-{m:02d}.zip')
            cache = os.path.join(RAW_DIR, f'{market.replace("/", "_")}-1m-{y:04d}-{m:02d}.zip')
            try:
                if os.path.exists(cache) and os.path.getsize(cache) > 1000:
                    raw = open(cache, 'rb').read()
                else:
                    raw = http_get(url, timeout=180)
                    with open(cache, 'wb') as f:
                        f.write(raw)
                parts.append(_parse_vision_csv(raw, era))
                ok += 1
            except Exception as e:
                # 당월 파일은 아직 없을 수 있다(월 마감 전) → 일별로 보충
                if (y, m) == (now.year, now.month):
                    parts.extend(self._daily_fill(y, m))
                else:
                    self.log(f'[스킵] {y}-{m:02d} {market}: {e}', 'orange')
            if progress:
                progress(i, total, f'{market} {y}-{m:02d}')

        if not parts:
            raise IOError('아카이브에서 받은 데이터가 없습니다. 네트워크/방화벽 확인.')

        df = self.normalize_index(pd.concat(parts), self.log)
        df = df[~df.index.duplicated(keep='last')].sort_index()
        df = df[STORE_COLS].astype('float64')
        self._save(df)
        self.base = df
        self.res_cache.clear()
        self.log(f'[구축 완료] 1분봉 {len(df):,}개 · {df.index[0]} ~ {df.index[-1]} '
                 f'(월파일 {ok}/{total})', 'green')
        return df

    def _daily_fill(self, y, m):
        out = []
        d = datetime(y, m, 1)
        while d.month == m and d <= utcnow():
            url = (f'{VISION_BASE}/futures/um/daily/klines/{SYMBOL}/1m/'
                   f'{SYMBOL}-1m-{d:%Y-%m-%d}.zip')
            try:
                out.append(_parse_vision_csv(http_get(url, timeout=90), ERA_FUT))
            except Exception:
                pass
            d += timedelta(days=1)
        return out

    # ── 증분 갱신 (fapi REST) ────────────────────────────────────
    def _incremental(self, df):
        """마지막 저장봉 이후를 1500개씩 페이징으로 채운다."""
        df = self.normalize_index(df, self.log)
        last_ms = int(pd.Timestamp(df.index[-1]).value // 10 ** 6)
        target = floor_time(utcnow(), 1) - timedelta(minutes=1)   # 기대 마지막 완결봉
        got = []
        cursor = last_ms + 60_000
        guard = 0
        while guard < 400:
            guard += 1
            nd = _rest_klines('1m', cursor, limit=1500)
            if nd is None or nd.empty:
                break
            got.append(nd)
            newest = int(nd.index[-1].value // 10 ** 6)
            if newest <= cursor:
                break
            cursor = newest + 60_000
            if nd.index[-1] >= target:
                break
            time.sleep(0.12)              # 레이트리밋 예의
        if not got:
            return df
        add = self.normalize_index(pd.concat(got), self.log)
        df = pd.concat([df, add])
        df = df[~df.index.duplicated(keep='last')].sort_index()
        return self.normalize_index(df[STORE_COLS].astype('float64'), self.log)

    @staticmethod
    def _drop_incomplete_1m(df):
        """진행 중인 1분봉 제거 — 미완성 봉이 패턴을 오염시키지 않게"""
        if df is None or df.empty:
            return df
        cutoff = floor_time(utcnow(), 1)
        return df[df.index < cutoff]

    # ── ★ 인덱스 정규화 — "datetime - str" 오류의 근본 차단 ──────────
    @staticmethod
    def normalize_index(df, log=None):
        """
        디스크에서 읽었든 네트워크에서 받았든, 인덱스를 무조건 tz-naive
        DatetimeIndex 로 만든다.

        왜 필요한가:
          pandas 는 CSV 안의 타임스탬프 형식이 '한 줄이라도' 다르면
          (소수점 초 `00:01:00.500`, T 구분자, tz 오프셋 `+00:00`,
           중간에 다시 낀 헤더 행 등) 인덱스 '전체'를 문자열로 돌려준다.
          그 상태로 ensure() 가 (현재시각 − 마지막봉) 을 계산하면
            unsupported operand type(s) for -: 'datetime.datetime' and 'str'
          로 터지고, 갱신이 영원히 안 되는 것처럼 보인다.
          한 번 그렇게 되면 저장 때도 문자열 인덱스가 그대로 다시 쓰여서
          스스로 낫지 않는다 → 읽을 때와 쓸 때 양쪽에서 강제 정규화한다.
        """
        if df is None or len(df) == 0:
            return df
        idx = df.index
        if not isinstance(idx, pd.DatetimeIndex):
            raw = pd.Index(idx)
            # 1차: 표준 형식으로 벡터화 파싱 (수백만 행도 1초 내외)
            try:
                conv = pd.to_datetime(raw, format='%Y-%m-%d %H:%M:%S',
                                      errors='coerce')
            except Exception:
                conv = pd.Series([pd.NaT] * len(raw)).values
            miss = np.asarray(pd.isna(conv))
            # 2차: 1차에서 실패한 소수만 형식 자유 파싱 (느리지만 몇 개뿐)
            if miss.any():
                sub = np.asarray(raw, dtype=object)[miss]
                fixed = None
                for kw in ({'errors': 'coerce', 'format': 'mixed'},
                           {'errors': 'coerce'}):
                    try:
                        fixed = pd.to_datetime(pd.Index(sub), **kw)
                        break
                    except Exception:
                        continue
                if fixed is not None:
                    vals = np.asarray(conv, dtype='datetime64[ns]').copy()
                    vals[miss] = np.asarray(fixed, dtype='datetime64[ns]')
                    conv = pd.DatetimeIndex(vals)
            conv = pd.DatetimeIndex(conv)
            bad = np.asarray(pd.isna(conv))
            if bad.all():
                raise ValueError('인덱스를 날짜로 변환할 수 없습니다 (파일 손상)')
            if bad.any():
                if log:
                    ex = [str(v) for v in np.asarray(raw, dtype=object)[bad][:3]]
                    log(f'[캐시 복구] 날짜로 읽히지 않는 행 {int(bad.sum()):,}개 제거 '
                        f'(예: {ex})', 'orange')
                df = df.loc[~bad]
                conv = conv[~bad]
            df = df.copy()
            df.index = conv
            if log:
                log('[캐시 복구] 타임스탬프 형식이 섞여 있어 인덱스를 재파싱했습니다.',
                    'orange')
        if getattr(df.index, 'tz', None) is not None:
            df = df.copy()
            df.index = df.index.tz_convert('UTC').tz_localize(None)
        df.index.name = 'timestamp'
        if not df.index.is_monotonic_increasing or df.index.has_duplicates:
            df = df[~df.index.duplicated(keep='last')].sort_index()
        return df

    def _last_ts(self):
        """마지막 봉 시각을 Timestamp 로 안전하게 반환 (실패 시 None)"""
        try:
            v = self.base.index[-1]
            return v if isinstance(v, pd.Timestamp) else pd.Timestamp(v)
        except Exception:
            return None

    def ensure(self, force_refresh=False, progress=None):
        """1분봉 원본을 최신 상태로 만든다. 실패는 삼키지 않고 meta에 남긴다."""
        with self.lock:
            self.last_error = ''
            if self.base is None:
                self.base = self._load_disk()
            if self.base is None or self.base.empty:
                self.log('원본 없음 → 바이낸스 아카이브에서 전체 구축을 시작합니다.', 'red')
                self.base = self.build_full_history(progress=progress)
            else:
                # 어떤 경로로 들어왔든 인덱스를 먼저 정규화한다 (문자열 인덱스 차단)
                self.base = self.normalize_index(self.base, self.log)
                last = self._last_ts()
                if last is None:
                    self.log('캐시 인덱스를 복구할 수 없어 재구축합니다 '
                             '(raw 폴더가 있으면 네트워크 없이 빠르게 끝납니다).', 'red')
                    self.base = self.build_full_history(progress=progress)
                    last = self._last_ts()
                target = floor_time(utcnow(), 1) - timedelta(minutes=1)
                stale_min = (target - last).total_seconds() / 60.0
                if force_refresh or stale_min >= 1:
                    self.log(f'갱신 중... (지연 {stale_min:.0f}분)', 'blue')
                    try:
                        n0 = len(self.base)
                        self.base = self._incremental(self.base)
                        self.base = self._drop_incomplete_1m(self.base)
                        self._save(self.base)
                        self.res_cache.clear()
                        self.log(f'갱신 완료: +{len(self.base) - n0}봉', 'green')
                    except Exception as e:
                        self.last_error = f'{type(e).__name__}: {e}'
                        self.log(f'[갱신 실패] {self.last_error}', 'red')
            self.base = self.normalize_index(self.base, self.log)
            self.base = self._drop_incomplete_1m(self.base)
            target = floor_time(utcnow(), 1) - timedelta(minutes=1)
            last = self._last_ts()
            lag = (target - last).total_seconds() / 60.0 if last else float('nan')
            self.meta = dict(
                rows=len(self.base),
                first=self.base.index[0], last=self.base.index[-1],
                lag_min=lag, error=self.last_error,
                fut_rows=int((self.base['era'].values == ERA_FUT).sum()),
                spot_rows=int((self.base['era'].values == ERA_SPOT).sum()),
            )
            return self.base

    # ── 상위 TF 파생 ────────────────────────────────────────────
    def get(self, tf, force_refresh=False, progress=None):
        base = self.ensure(force_refresh=force_refresh, progress=progress)
        if tf == '1m':
            return base
        if tf in self.res_cache and not force_refresh:
            return self.res_cache[tf]
        mins = INTERVALS[tf]
        rule = f'{mins}min'
        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
               'volume': 'sum', 'taker_buy_base': 'sum', 'trades': 'sum',
               'era': 'min'}
        df = base.resample(rule, label='left', closed='left', origin='epoch').agg(agg)
        df = df.dropna(subset=['open', 'high', 'low', 'close'])
        # 마지막 봉이 완결되지 않았으면 제거
        cutoff = floor_time(utcnow(), mins)
        df = df[df.index < cutoff]
        self.res_cache[tf] = df
        return df

    def data_banner(self, tf):
        m = self.meta
        if not m:
            return '데이터 상태: 미확인'
        lag = m['lag_min']
        mark = '정상' if lag <= MAX_STALE_MIN else f'★지연 {lag:.0f}분★'
        s = (f"데이터 : 1분봉 {m['rows']:,}개  |  {m['first']:%Y-%m-%d} ~ "
             f"{m['last']:%Y-%m-%d %H:%M} UTC  |  신선도 {mark}\n"
             f"         선물 {m['fut_rows']:,}봉")
        if m['spot_rows']:
            s += f" + 스팟(선물이전) {m['spot_rows']:,}봉 — 구간 경계를 넘는 창은 검색 제외"
        if m['error']:
            s += f"\n         ⚠ 갱신 오류: {m['error']}"
        return s


# =============================================================================
# [4] 수학 코어
# =============================================================================
def znorm(x):
    x = np.asarray(x, dtype=np.float64)
    s = x.std()
    if s < 1e-14:
        return x - x.mean()
    return (x - x.mean()) / s


def _sliding_ms(T, m):
    """길이 m 슬라이딩 창의 평균·표준편차 (누적합, O(n))"""
    T = np.asarray(T, dtype=np.float64)
    c1 = np.cumsum(np.concatenate(([0.0], T)))
    c2 = np.cumsum(np.concatenate(([0.0], T * T)))
    s1 = c1[m:] - c1[:-m]
    s2 = c2[m:] - c2[:-m]
    mu = s1 / m
    var = np.maximum(s2 / m - mu * mu, 0.0)
    return mu, np.sqrt(var)


def _sliding_dot(Q, T):
    """Q와 T의 모든 창의 내적 — FFT 컨볼루션 (MASS 핵심), O(n log n)"""
    m, n = len(Q), len(T)
    size = 1
    while size < n + m:
        size <<= 1
    conv = np.fft.irfft(np.fft.rfft(T, size) * np.fft.rfft(Q[::-1], size), size)
    return conv[m - 1:n]


def corr_profile(Q, T):
    """
    T의 '모든' 길이 m 창과 Q의 피어슨 상관을 전부 계산한다(생략·표본추출 없음).
    z-정규화 유클리드 거리와 동치:  d² = 2m(1 − r)
    ※ 입력은 반드시 로그가격/로그수익률 같은 작은 스케일을 쓸 것 (FFT 정밀도).
    반환: (corr[n-m+1], 각 창의 표준편차[n-m+1])
    """
    Q = np.asarray(Q, dtype=np.float64)
    T = np.asarray(T, dtype=np.float64)
    m = len(Q)
    k = max(len(T) - m + 1, 0)
    qs = Q.std()
    if m < 2 or len(T) < m or qs < 1e-14:
        return np.full(k, -1.0), np.zeros(k)
    # ★ 수치안정화: 상관은 T의 아핀변환에 불변이므로 전역 정규화 후 계산한다.
    #   (로그가격처럼 '평균은 큰데 변동은 작은' 계열에서 누적합의 상쇄오차로
    #    상관이 1e-6 수준까지 틀어지는 문제를 제거 → 오차 1e-12 이하)
    tg = T.mean()
    ts = T.std()
    if ts < 1e-300:
        return np.full(k, -1.0), np.zeros(k)
    Tn = (T - tg) / ts
    qz = (Q - Q.mean()) / qs
    dot = _sliding_dot(qz, Tn)
    mu, sdn = _sliding_ms(Tn, m)
    with np.errstate(divide='ignore', invalid='ignore'):
        r = np.where(sdn > 1e-13, dot / (m * sdn), -1.0)
    sd = sdn * ts                       # 원 스케일 표준편차로 되돌림
    return np.clip(np.nan_to_num(r, nan=-1.0), -1.0, 1.0), sd


def corr_exact(Q, T, starts):
    """
    선택된 후보에 대해서만 상관을 '직접 내적'으로 재계산한다.
    FFT 누적 오차 가능성까지 제거하기 위한 검증 단계 (무근사 보증).
    """
    Q = np.asarray(Q, dtype=np.float64)
    T = np.asarray(T, dtype=np.float64)
    m = len(Q)
    qz = znorm(Q)
    out = np.empty(len(starts))
    for i, s in enumerate(starts):
        w = T[s:s + m]
        sd = w.std()
        out[i] = -1.0 if sd < 1e-14 else float(np.dot(qz, (w - w.mean()) / sd) / m)
    return np.clip(out, -1.0, 1.0)


@njit(cache=False, fastmath=True)
def dtw_band(a, b, w):
    """사코에-치바 밴드 DTW (2행 롤링 메모리)"""
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
        lo = i - ww
        if lo < 1:
            lo = 1
        hi = i + ww
        if hi > m:
            hi = m
        for j in range(lo, hi + 1):
            d = a[i - 1] - b[j - 1]
            c = d * d
            best = prev[j]
            if prev[j - 1] < best:
                best = prev[j - 1]
            if cur[j - 1] < best:
                best = cur[j - 1]
            cur[j] = c + best
        tmp = prev
        prev = cur
        cur = tmp
    return prev[m]


def pick_nonoverlap(order, k, excl):
    """점수순 인덱스에서 서로 excl 이상 떨어진 것만 최대 k개 (자기복제 매치 방지)"""
    chosen = []
    for idx in order:
        idx = int(idx)
        if all(abs(idx - c) >= excl for c in chosen):
            chosen.append(idx)
            if len(chosen) >= k:
                break
    return chosen


# ── 브래킷 체결 시뮬레이터 (완전 벡터화) ─────────────────────────
def bracket_vec(HI, LO, CL, side, tp, sl):
    """
    TP/SL 최초 도달 판정.
      HI/LO/CL : (n, T) 진입가 대비 수익률 경로 (1분봉 해상도 권장)
      side     : +1 롱 / -1 숏
      동일 시점 동시 도달은 '손절'로 처리 (낙관 편향 제거)
    반환 (pnl[n], code[n])  code: 1 익절 / -1 손절 / 0 만기청산
    """
    HI = np.atleast_2d(np.asarray(HI, dtype=np.float64))
    LO = np.atleast_2d(np.asarray(LO, dtype=np.float64))
    CL = np.atleast_2d(np.asarray(CL, dtype=np.float64))
    n, T = HI.shape
    if side > 0:
        win = HI >= tp
        lose = LO <= -sl
        final = CL[:, -1]
    else:
        win = LO <= -tp
        lose = HI >= sl
        final = -CL[:, -1]
    fw = np.where(win.any(1), win.argmax(1), T)
    fl = np.where(lose.any(1), lose.argmax(1), T)
    pnl = np.empty(n)
    code = np.zeros(n, dtype=np.int64)
    lose_first = (fl <= fw) & (fl < T)      # 동시 도달 → 손절
    win_first = (fw < fl) & (fw < T)
    pnl[lose_first] = -sl
    code[lose_first] = -1
    pnl[win_first] = tp
    code[win_first] = 1
    rest = ~(lose_first | win_first)
    pnl[rest] = final[rest]
    code[rest] = 0
    return pnl, code


# ── 정상 블록 부트스트랩 귀무분포 ────────────────────────────────
def block_bootstrap_pvalue(observed, paths_fn, pool_idx, n_draw, side, tp, sl,
                           n_boot=BOOT_N, chunk=BOOT_CHUNK, rng=None):
    """
    귀무가설: "이 이웃들은 특별하지 않다 = 같은 구간에서 무작위로 n_draw개 뽑은
              창들과 미래 분포가 같다."
    무작위 표본으로 동일한 브래킷 규칙의 평균 손익을 n_boot번 계산해
    관측 기대값이 상위 몇 %인지(p-value) 반환한다.
    """
    rng = rng or np.random.default_rng(20240917)
    if len(pool_idx) < n_draw * 2:
        return 1.0, np.array([0.0])
    null = np.empty(n_boot)
    done = 0
    while done < n_boot:
        b = min(chunk, n_boot - done)
        for j in range(b):
            pick = rng.choice(pool_idx, size=n_draw, replace=False)
            HI, LO, CL = paths_fn(pick)
            pnl, _ = bracket_vec(HI, LO, CL, side, tp, sl)
            null[done + j] = float(pnl.mean())
        done += b
    p = float((null >= observed).mean())
    # 연속성 보정 (0이 되지 않게)
    p = (np.sum(null >= observed) + 1.0) / (n_boot + 1.0)
    return p, null


def wilson_lower(k, n, conf=0.95):
    """승률의 Wilson 신뢰구간 하한 — '점추정이 아니라 하단에 베팅한다'"""
    if n <= 0:
        return 0.0
    z = 1.959963985 if conf >= 0.95 else 1.6448536
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    m = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d)


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def deflated_sharpe(returns, n_trials):
    """
    Deflated Sharpe Ratio (Bailey & López de Prado).
    '파라미터를 n_trials번 시도해서 고른 최고 성적'이라는 사실을 벌점으로 반영.
    반환: (관측 SR, 기대 최대 SR(귀무), DSR 확률)
    """
    r = np.asarray(returns, dtype=np.float64)
    n = len(r)
    if n < 8 or r.std(ddof=1) < 1e-12:
        return 0.0, 0.0, 0.0
    sr = r.mean() / r.std(ddof=1)
    g3 = float(pd.Series(r).skew())
    g4 = float(pd.Series(r).kurt()) + 3.0
    e = 0.5772156649                                # 오일러-마스케로니 γ
    t = max(int(n_trials), 2)
    z1 = norm_ppf(1.0 - 1.0 / t)
    z2 = norm_ppf(1.0 - 1.0 / (t * math.e))
    se = math.sqrt(1.0 / max(n - 1, 1))             # 귀무 하 SR 표본오차
    sr0 = se * ((1 - e) * z1 + e * z2)              # 시행 t회의 기대 최대 SR
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr * sr))
    dsr = norm_cdf((sr - sr0) * math.sqrt(max(n - 1, 1)) / denom)
    return sr, sr0, dsr


def norm_ppf(p):
    """표준정규 분위수 (Acklam 근사)"""
    if p <= 0.0:
        return -np.inf
    if p >= 1.0:
        return np.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


# =============================================================================
# [5] 특징(표현) 레이어 — '패턴 일치'를 무엇으로 정의할 것인가
# -----------------------------------------------------------------------------
#  가격 모양만 보면 "닮았다"는 판정이 너무 헐거워진다. 같은 모양이라도
#  변동성이 3배거나, 매수세가 정반대이거나, 캔들 구조가 다르면 다른 국면이다.
#  V200은 5개 채널을 각각 z-정규화 상관으로 비교하고 '모두' 통과해야 이웃으로
#  인정한다. 각 채널은 스케일·오프셋 불변(z-norm)이라 절대가격 수준의 영향을 받지 않는다.
# =============================================================================
class Channels:
    """전 구간 채널 시계열을 한 번만 만들어두고 재사용한다."""

    __slots__ = ('shape', 'ret', 'vol', 'volume', 'flow', 'rng', 'era', 'n',
                 'high', 'low', 'close', 'atr')

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

        # 변동성 궤적: 국소 실현변동성의 로그
        rv = pd.Series(r).rolling(vol_win, min_periods=2).std().bfill().values
        vol = np.log(np.maximum(rv, 1e-10))

        # 거래량 패턴: 절대량 대신 log1p를 사용해 시대별 스케일 차이를 완화
        volume = np.log1p(v)

        # 주문흐름 대용: 테이커 매수 비중 (0.5 중심), 짧게 평활
        fl = np.clip(tb / v, 0.0, 1.0) - 0.5
        fl = pd.Series(fl).rolling(5, min_periods=1).mean().values

        # 레인지 구조: (고-저)/종가
        rg = (h - l) / np.maximum(c, 1e-12)
        rg = pd.Series(rg).rolling(3, min_periods=1).mean().values

        # ATR(변동성 단위 — 손절 하한에 사용)
        tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)),
                                          np.abs(l - np.roll(c, 1))))
        tr[0] = h[0] - l[0]
        atr = pd.Series(tr / np.maximum(c, 1e-12)).ewm(
            alpha=1 / 14.0, adjust=False).mean().values

        self.shape = lc
        self.ret = r
        self.vol = np.nan_to_num(vol, nan=np.nanmedian(vol))
        self.volume = np.nan_to_num(volume, nan=np.nanmedian(volume))
        self.flow = np.nan_to_num(fl)
        self.rng = np.nan_to_num(rg)
        self.era = df['era'].values.astype(np.float64)
        self.high, self.low, self.close = h, l, c
        self.atr = np.nan_to_num(atr, nan=0.005)
        self.n = n

    def window(self, name, s, K):
        return getattr(self, name)[s:s + K]


# =============================================================================
# [6] 지지·저항 레벨 (스윙 피벗 + 볼륨 프로파일)
# -----------------------------------------------------------------------------
#  워뇨띠식 레벨 매매의 핵심은 "틀렸음이 확정되는 지점 바로 바깥에 손절"이다.
#  통계적 분위수 손절은 '평균적으로' 맞지만 구조적으로는 무의미한 자리에 놓인다.
#  두 가지를 결합한다: 손절은 max(통계 하한, 구조 레벨 바깥), 익절은
#  min(통계 상한, 반대편 레벨 직전).
# =============================================================================
def sr_levels(high, low, close, volume, lookback=1500, pivot_w=6,
              tol=0.0015, top_n=8):
    n = len(close)
    a = max(0, n - lookback)
    h, l, c, v = high[a:], low[a:], close[a:], volume[a:]
    m = len(c)
    if m < pivot_w * 3:
        return []
    piv = []
    for i in range(pivot_w, m - pivot_w):
        seg_h = h[i - pivot_w:i + pivot_w + 1]
        seg_l = l[i - pivot_w:i + pivot_w + 1]
        if h[i] == seg_h.max():
            piv.append((h[i], v[i], 1))
        if l[i] == seg_l.min():
            piv.append((l[i], v[i], -1))
    if not piv:
        return []
    piv.sort(key=lambda x: x[0])
    clusters = []
    cur = [piv[0]]
    for p in piv[1:]:
        if abs(p[0] - cur[-1][0]) / max(cur[-1][0], 1e-9) <= tol:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    out = []
    vsum = max(v.sum(), 1e-9)
    for cl in clusters:
        px = float(np.average([x[0] for x in cl],
                              weights=[max(x[1], 1e-9) for x in cl]))
        touches = len(cl)
        vol_w = float(sum(x[1] for x in cl)) / vsum
        strength = touches * (1.0 + 3.0 * vol_w)
        out.append(dict(price=px, touches=touches, strength=strength))
    out.sort(key=lambda d: -d['strength'])
    return out[:top_n]


def nearest_levels(levels, price):
    below = [d for d in levels if d['price'] < price]
    above = [d for d in levels if d['price'] > price]
    sup = max(below, key=lambda d: d['price']) if below else None
    res = min(above, key=lambda d: d['price']) if above else None
    return sup, res


# =============================================================================
# [7] 이웃 검색 — 다채널 게이트 → DTW 재순위 → 무근사 검증
# =============================================================================
def find_neighbors(ch, K, H, end=None, topk=TOPK, status=None, embargo=None,
                   cand_pool=CAND_POOL, use_dtw=True):
    """
    현재(=end 직전) K봉과 유사한 과거 구간을 찾는다.
      · 같은 TF·같은 K 안에서만 검색 → 기간 스케일은 구조적으로 동일
      · 5채널 상관 게이트 + 변동성/추세 강도 게이트
      · 선물/스팟 구간 경계를 넘는 창은 배제
      · 이웃의 미래 H봉이 질의 구간과 겹치지 않도록 시작 상한 제한(선견 누수 차단)
      · 게이트 통과분은 직접 내적으로 상관 재계산(FFT 오차 제거)
    """
    n = ch.n if end is None else int(end)
    if n > ch.n:
        n = ch.n
    embargo = H if embargo is None else int(embargo)
    if n < 3 * K + 2 * H + 20:
        return None, '데이터 부족 (K·H 대비 히스토리가 짧음)'

    qs = n - K                      # 질의 창 시작
    max_start = n - 2 * K - H - embargo
    if max_start < 10:
        return None, '데이터 부족 (검색 가능한 과거 구간 없음)'

    q = {name: ch.window(name, qs, K) for name in CH_WEIGHTS}
    q_vol = float(np.std(q['ret']))
    if q_vol < 1e-12:
        return None, '현재 구간 변동성 0 — 분석 불가'
    q_trend = float((q['shape'][-1] - q['shape'][0]) / (K * q_vol))

    if status:
        status('전 구간 정확 상관 스캔 (5채널 MASS/FFT)...', 'blue')

    prof, sds = {}, {}
    for name in CH_WEIGHTS:
        T = getattr(ch, name)[:max_start + K]
        r, sd = corr_profile(q[name], T)
        prof[name] = r[:max_start + 1]
        sds[name] = sd[:max_start + 1]

    L = min(len(v) for v in prof.values())
    for name in prof:
        prof[name] = prof[name][:L]
        sds[name] = sds[name][:L]

    # 변동성 강도 게이트
    volr = sds['ret'] / q_vol
    vol_ok = (volr >= 1.0 / VOL_TOL) & (volr <= VOL_TOL)

    # 상위 추세 강도 게이트
    idx = np.arange(L)
    sh = ch.shape
    trend = (sh[idx + K - 1] - sh[idx]) / (K * np.maximum(sds['ret'], 1e-12))
    if abs(q_trend) < 1e-6:
        trend_ok = np.abs(trend) <= max(0.05, abs(q_trend) * TREND_TOL + 0.05)
    else:
        ratio = trend / q_trend
        trend_ok = (ratio > 0) & (ratio >= 1.0 / TREND_TOL) & (ratio <= TREND_TOL)

    # 구간(선물/스팟) 경계 배제
    era = ch.era
    era_chg = np.zeros(ch.n)
    era_chg[1:] = (np.diff(era) != 0).astype(np.float64)
    cse = np.concatenate(([0.0], np.cumsum(era_chg)))
    span = K + H
    era_ok = (cse[np.minimum(idx + span, ch.n)] - cse[idx]) == 0
    era_ok = era_ok[:L]

    relax = -1
    pool = None
    observe_only = False
    for lvl, (cp, cr, cf) in enumerate(GATE_STEPS):
        base_ok = era_ok & vol_ok
        if lvl <= TREND_GATE_UNTIL:
            base_ok = base_ok & trend_ok
        mask = base_ok & (prof['shape'] >= cp) & (prof['ret'] >= cr) & \
               (prof['flow'] >= cf)
        if int(mask.sum()) >= MIN_NEIGHBORS:
            relax, pool = lvl, np.flatnonzero(mask)
            break
    if pool is None:
        if not OBSERVE_FALLBACK:
            return None, ('게이트(형상·동역학·흐름·변동성·추세)를 통과한 유사 구간이 '
                          f'{MIN_NEIGHBORS}개 미만 → 관망')
        # ── 관측 전용 폴백 ───────────────────────────────────────
        # 게이트를 못 넘어도 '가장 닮은 과거'는 항상 존재한다. 차트와 베스트매치를
        # 볼 수 있도록 형상 상관 상위만으로 이웃을 구성하되, observe_only 플래그를
        # 세워 매매 신호는 절대 내지 않는다. (닮음 ≠ 근거)
        observe_only = True
        relax = len(GATE_STEPS)
        pool = np.flatnonzero(era_ok)
        if len(pool) < MIN_NEIGHBORS:
            pool = np.arange(L, dtype=np.int64)
        if len(pool) < 3:
            return None, '검색 가능한 과거 구간이 없습니다 (데이터 부족)'

    combo = np.zeros(L)
    for name, w in CH_WEIGHTS.items():
        combo += w * prof[name]

    order0 = pool[np.argsort(-combo[pool])]
    cand = order0[:max(int(cand_pool), topk * 2)]

    if use_dtw:
        if status:
            status(f'DTW 정밀 재순위 (후보 {len(cand)}개)...', 'blue')
        tz = znorm(q['shape'])
        band = max(2, int(K * DTW_BAND_FRAC))
        dtws = np.empty(len(cand))
        for i in range(len(cand)):
            s = int(cand[i])
            dtws[i] = dtw_band(tz, znorm(sh[s:s + K]), band)
        score = dtws / (np.maximum(combo[cand], 1e-6) ** 4 + 1e-9)
    else:
        score = -combo[cand]

    excl = max(1, int(K * EXCL_FRAC))
    starts = pick_nonoverlap(cand[np.argsort(score)], topk, excl)
    if len(starts) < MIN_NEIGHBORS:
        if not observe_only and OBSERVE_FALLBACK:
            # 게이트는 넘었지만 비중첩 개수가 부족 → 관측 전용으로 강등(차트는 살린다)
            observe_only = True
            relax = len(GATE_STEPS)
        if len(starts) < 3:
            return None, f'비중첩 이웃 {len(starts)}개 — 검색 불가'

    # ── 무근사 검증: 선택된 이웃만 직접 내적으로 상관 재계산 ──
    ex_shape = corr_exact(q['shape'], sh, starts)
    ex_ret = corr_exact(q['ret'], ch.ret, starts)
    fft_err = float(np.max(np.abs(ex_shape - prof['shape'][starts])))

    nvol = np.array([float(np.std(ch.ret[s:s + K])) for s in starts])
    scales = np.clip(q_vol / np.maximum(nvol, 1e-12), 1.0 / VOL_TOL, VOL_TOL)

    return dict(
        starts=starts, K=K, H=H, end=n, qs=qs,
        corr_shape=ex_shape.tolist(), corr_ret=ex_ret.tolist(),
        corr_flow=[float(prof['flow'][s]) for s in starts],
        corr_vol=[float(prof['vol'][s]) for s in starts],
        combo=[float(combo[s]) for s in starts],
        vol_scale=scales.tolist(), relax=relax, fft_err=fft_err,
        pool=pool, q_vol=q_vol, max_start=max_start,
        era=[int(era[s]) for s in starts],
        observe_only=observe_only,
    ), None


# =============================================================================
# [8] 미래 경로 — TF 해상도 / 1분봉 정밀 해상도
# =============================================================================
class PathMaker:
    """이웃의 '진입 직후 H봉' 수익률 경로를 만든다."""

    def __init__(self, ch, base_df, tf, K, H, scales_map=None, use_1m=True):
        self.ch = ch
        self.K, self.H, self.tf = K, H, tf
        self.mult = INTERVALS[tf]
        self.use_1m = bool(use_1m) and base_df is not None and tf != '1m'
        self.scales_map = scales_map or {}
        if self.use_1m:
            self.b_hi = base_df['high'].values.astype(np.float64)
            self.b_lo = base_df['low'].values.astype(np.float64)
            self.b_cl = base_df['close'].values.astype(np.float64)
            self.b_ts = base_df.index.values.astype('datetime64[ns]').astype('int64')
        self.tf_ts = None

    def bind_tf_index(self, tf_index):
        self.tf_ts = tf_index.values.astype('datetime64[ns]').astype('int64')

    def _scale(self, starts):
        return np.array([self.scales_map.get(int(s), 1.0) for s in starts])

    def tf_paths(self, starts):
        K, H = self.K, self.H
        ch = self.ch
        sc = self._scale(starts)
        m = len(starts)
        HI = np.empty((m, H))
        LO = np.empty((m, H))
        CL = np.empty((m, H))
        for i, s in enumerate(starts):
            e = int(s) + K - 1
            entry = ch.close[e]
            HI[i] = (ch.high[e + 1:e + 1 + H] / entry - 1.0) * sc[i]
            LO[i] = (ch.low[e + 1:e + 1 + H] / entry - 1.0) * sc[i]
            CL[i] = (ch.close[e + 1:e + 1 + H] / entry - 1.0) * sc[i]
        return HI, LO, CL

    def paths(self, starts):
        """1분봉 정밀 경로 (가능하면). 같은 봉 안 TP/SL 선후까지 재현."""
        if not self.use_1m or self.tf_ts is None:
            return self.tf_paths(starts)
        K, H = self.K, self.H
        mult = self.mult
        steps = H * mult
        sc = self._scale(starts)
        m = len(starts)
        HI = np.empty((m, steps))
        LO = np.empty((m, steps))
        CL = np.empty((m, steps))
        ok = True
        for i, s in enumerate(starts):
            e = int(s) + K - 1
            entry = self.ch.close[e]
            t_close_ns = self.tf_ts[e] + np.int64(mult * 60_000_000_000)
            p0 = int(np.searchsorted(self.b_ts, t_close_ns, side='left'))
            if p0 + steps > len(self.b_cl):
                ok = False
                break
            HI[i] = (self.b_hi[p0:p0 + steps] / entry - 1.0) * sc[i]
            LO[i] = (self.b_lo[p0:p0 + steps] / entry - 1.0) * sc[i]
            CL[i] = (self.b_cl[p0:p0 + steps] / entry - 1.0) * sc[i]
        if not ok:
            return self.tf_paths(starts)
        return HI, LO, CL


# =============================================================================
# [9] 전략 엔진 — OOF 파라미터 선택 · 유의성 검정 · 켈리 상한
# =============================================================================
def total_cost(tf, H):
    return fee_round_trip() + funding_cost(tf, H)


def _grid_from(mfe, mae):
    tp_g = np.unique(np.quantile(mfe, [0.40, 0.55, 0.70, 0.85]))
    sl_g = np.unique(np.quantile(mae, [0.25, 0.40, 0.55, 0.70]))
    return tp_g, sl_g


def _best_on(HI, LO, CL, side, tp_g, sl_g, tf, H):
    cost = total_cost(tf, H)
    best = None
    for tp in tp_g:
        for sl in sl_g:
            tp, sl = float(tp), float(sl)
            if tp <= cost * 2 or sl <= 1e-5 or tp / sl < MIN_RR:
                continue
            pnl, code = bracket_vec(HI, LO, CL, side, tp, sl)
            ev = float(net_pnl(pnl, code, tf, H).mean())
            if best is None or ev > best[0]:
                best = (ev, tp, sl)
    return best


KELLY_LB_Q = 0.20      # 켈리 부트스트랩 하한 분위수 (작을수록 보수적)


def kelly_fraction(pnl_net, sl, n_boot=300, rng=None, q=KELLY_LB_Q):
    """
    경험분포 기반 수치 켈리. 자본의 f를 '손절 시 잃는 양'으로 정의:
        자산배수 = 1 + (pnl/sl) × f
    부트스트랩 하한 분위수를 써서 표본 우연을 벌한다.
    반환 (점추정 f, 하한 f)
    ※ 하한이 0이어도 점추정이 양수면 '거래 금지'가 아니라 '베팅 축소'로 처리한다
      (n=40 수준 표본에서 5% 하한이 0이 되는 것은 매우 흔하다).
    """
    x = np.asarray(pnl_net, dtype=np.float64) / max(sl, 1e-9)
    if len(x) < 5 or x.mean() <= 0:
        return 0.0, 0.0
    grid = np.linspace(0.001, 0.5, 120)

    def opt(v):
        with np.errstate(divide='ignore', invalid='ignore'):
            g = np.log1p(np.outer(grid, v))
        g[~np.isfinite(g)] = -1e9
        mg = g.mean(axis=1)
        return float(grid[int(np.argmax(mg))]) if mg.max() > 0 else 0.0

    f_hat = opt(x)
    if f_hat <= 0:
        return 0.0, 0.0
    rng = rng or np.random.default_rng(7)
    fs = np.empty(n_boot)
    for i in range(n_boot):
        fs[i] = opt(rng.choice(x, size=len(x), replace=True))
    return f_hat, float(np.quantile(fs, q))


def analyze_scale(ch, base_frame, tf_index, tf, K, H, end=None,
                  topk=TOPK, use_1m=True, boot_n=BOOT_N, status=None,
                  levels=None, rng=None, use_dtw=True, cand_pool=CAND_POOL):
    """단일 K에 대한 전체 분석. 반환 dict(신호 또는 관망 사유)."""
    out = dict(K=K, H=H, trade=False, reason='', side=0)
    nb, err = find_neighbors(ch, K, H, end=end, topk=topk, status=status,
                             cand_pool=cand_pool, use_dtw=use_dtw)
    if nb is None:
        out['reason'] = err
        return out
    out['nb'] = nb

    starts = nb['starts']
    scales_map = {int(s): float(v) for s, v in zip(starts, nb['vol_scale'])}
    pm = PathMaker(ch, base_frame, tf, K, H, scales_map, use_1m=use_1m)
    if tf_index is not None:
        pm.bind_tf_index(tf_index)

    HI, LO, CL = pm.paths(starts)
    fin = CL[:, -1]
    p_up = float((fin > 0).mean())
    out['p_up'] = p_up
    out['n'] = len(starts)
    out['paths'] = (HI, LO, CL)

    if nb.get('observe_only'):
        # 이웃(=가장 닮은 과거)은 찾았고 차트도 볼 수 있지만, 게이트를 통과하지
        # 못했으므로 매매 신호는 내지 않는다. '닮음'과 '근거'는 다른 것이다.
        out['reason'] = (f'게이트 미통과 — 관측 전용 (형상 상관 상위 {len(starts)}개만 '
                         f'추출). 유사도 조건이 충족되지 않아 매매 판단 불가 → 관망')
        return out

    if p_up >= UP_TH:
        side = 1
    elif p_up <= DN_TH:
        side = -1
    else:
        out['reason'] = f'방향 합의 부족 (이웃 상승비율 {p_up:.0%}) → 관망'
        return out
    out['side'] = side

    cost = total_cost(tf, H)
    out['cost'] = cost

    if side > 0:
        mfe = np.maximum(HI.max(axis=1), 1e-6)
        mae = np.maximum(-LO.min(axis=1), 1e-6)
    else:
        mfe = np.maximum(-LO.min(axis=1), 1e-6)
        mae = np.maximum(HI.max(axis=1), 1e-6)

    # ── 교대 2-fold OOF 선택 (인샘플 선택편향 제거) ──
    order = np.argsort([int(s) for s in starts])       # 시간순
    fa = order[0::2]
    fb = order[1::2]
    oof = []
    trials = 0
    for tr, te in ((fa, fb), (fb, fa)):
        if len(tr) < 5 or len(te) < 5:
            continue
        tp_g, sl_g = _grid_from(mfe[tr], mae[tr])
        trials += len(tp_g) * len(sl_g)
        b = _best_on(HI[tr], LO[tr], CL[tr], side, tp_g, sl_g, tf, H)
        if b is None:
            continue
        pnl, code_te = bracket_vec(HI[te], LO[te], CL[te], side, b[1], b[2])
        oof.append(float(net_pnl(pnl, code_te, tf, H).mean()))
    out['trials'] = max(trials, 1)
    if not oof:
        out['reason'] = '유효한 TP/SL 조합 없음(손익비·비용 기준 미달) → 관망'
        return out
    ev_oof = float(np.mean(oof))
    out['ev_oof'] = ev_oof

    # ── 실제 주문용 파라미터는 전체 이웃에서 확정 ──
    tp_g, sl_g = _grid_from(mfe, mae)
    best = _best_on(HI, LO, CL, side, tp_g, sl_g, tf, H)
    if best is None:
        out['reason'] = '유효한 TP/SL 조합 없음 → 관망'
        return out
    ev_in, tp, sl = best

    # ── 지지·저항 재배치 ──
    src = '통계 분위수'
    if levels:
        entry_px = ch.close[(end or ch.n) - 1]
        sup, res = nearest_levels(levels, entry_px)
        atr = float(ch.atr[(end or ch.n) - 1])
        buf = max(0.10 * atr, 0.0005)
        tp2, sl2 = tp, sl
        if side > 0:
            if sup is not None:
                d = (entry_px - sup['price']) / entry_px + buf
                if 0.3 * sl <= d <= 2.5 * sl:
                    sl2 = d
            if res is not None:
                d = (res['price'] - entry_px) / entry_px - buf
                if d > 0 and d < tp:
                    tp2 = d
        else:
            if res is not None:
                d = (res['price'] - entry_px) / entry_px + buf
                if 0.3 * sl <= d <= 2.5 * sl:
                    sl2 = d
            if sup is not None:
                d = (entry_px - sup['price']) / entry_px - buf
                if d > 0 and d < tp:
                    tp2 = d
        if tp2 / max(sl2, 1e-9) >= MIN_RR and tp2 > cost * 2:
            pnl2, code2 = bracket_vec(HI, LO, CL, side, tp2, sl2)
            if float(net_pnl(pnl2, code2, tf, H).mean()) > ev_in:
                tp, sl, src = tp2, sl2, '지지·저항 레벨'
                ev_in = float(net_pnl(pnl2, code2, tf, H).mean())
    out['level_src'] = src

    # ── 라운드 넘버 스냅 (사용자 규칙: 뒤 두 자리 00/50) ──
    #  최고점을 정확히 맞추려는 강박 대신, 목표보다 살짝 안쪽에서 익절하고
    #  무효화 지점보다 살짝 바깥에서 손절한다. 스냅 후 반드시 EV를 재평가한다.
    entry_px = float(ch.close[(end or ch.n) - 1])
    if ROUND_LEVELS:
        tp_px = entry_px * (1 + tp) if side > 0 else entry_px * (1 - tp)
        sl_px = entry_px * (1 - sl) if side > 0 else entry_px * (1 + sl)
        tp_px_s = snap(tp_px, side, 'tp')
        sl_px_s = snap(sl_px, side, 'sl')
        tp_s = abs(tp_px_s / entry_px - 1.0)
        sl_s = abs(sl_px_s / entry_px - 1.0)
        if tp_s > cost * 2 and sl_s > 1e-5 and tp_s / sl_s >= 1.0:
            tp, sl = tp_s, sl_s
            out['snapped'] = (tp_px_s, sl_px_s)
        else:
            out['snapped'] = None
    else:
        out['snapped'] = None

    pnl, code = bracket_vec(HI, LO, CL, side, tp, sl)
    pnl_net = net_pnl(pnl, code, tf, H)
    out.update(tp=tp, sl=sl, rr=tp / sl, ev_in=float(pnl_net.mean()),
               ev_in_presnap=ev_in,
               win=float((code == 1).mean()), lose=float((code == -1).mean()),
               tout=float((code == 0).mean()), pnl_net=pnl_net)

    # 보수적 대조값: TF 해상도(같은 봉 동시도달=손절)
    HIt, LOt, CLt = pm.tf_paths(starts)
    pnl_c, code_c = bracket_vec(HIt, LOt, CLt, side, tp, sl)
    out['ev_conservative'] = float(net_pnl(pnl_c, code_c, tf, H).mean())

    # ── 유의성: 블록 부트스트랩 귀무분포 ──
    if boot_n and boot_n > 0:
        if status:
            status('유의성 검정(부트스트랩 귀무분포) 중...', 'blue')
        pool = nb['pool']
        forb = set()
        for s in starts:
            for d in range(-K, K + 1):
                forb.add(int(s) + d)
        cand_pool_idx = np.array([int(p) for p in pool if int(p) not in forb],
                                 dtype=np.int64)
        if len(cand_pool_idx) < len(starts) * 3:
            cand_pool_idx = np.arange(0, nb['max_start'] + 1, dtype=np.int64)
        pv, null = block_bootstrap_pvalue(
            float(pnl.mean()), lambda idx: pm.paths(idx),
            cand_pool_idx, len(starts), side, tp, sl,
            n_boot=int(boot_n), rng=rng)
        out['pval'] = pv
        out['null_mean'] = float(np.mean(null))
    else:
        out['pval'] = float('nan')
        out['null_mean'] = float('nan')

    # ── 켈리 ──
    f_hat, f_low = kelly_fraction(pnl_net, sl, rng=rng)
    out['kelly'] = f_hat
    out['kelly_low'] = f_low

    # ── 최종 게이트 ──
    reasons = []
    if ev_oof <= cost * (EDGE_COST_MULT - 1.0):
        reasons.append(f'표본외 기대값 {ev_oof:+.3%} 이 비용문턱({cost * (EDGE_COST_MULT - 1.0):+.3%})을 넘지 못함')
    if boot_n and boot_n > 0 and out['pval'] > PVAL_MAX:
        reasons.append(f'유의하지 않음 (p={out["pval"]:.3f} > {PVAL_MAX})')
    if f_hat <= 0:
        reasons.append('켈리 점추정 ≤ 0 (복리 성장에 기여하지 않는 베팅)')
    if reasons:
        out['reason'] = ' / '.join(reasons) + ' → 관망'
        return out

    out['trade'] = True
    return out


def build_plan(ch, base_frame, tf_index, tf, K, H, seed, end=None, topk=TOPK,
               use_1m=True, boot_n=BOOT_N, multiscale=MULTISCALE, status=None,
               levels=None, rng=None, use_dtw=True, cand_pool=CAND_POOL):
    """다중 스케일 합의 → 최종 매매 계획"""
    Ks = [K]
    if multiscale:
        Ks = []
        for f in SCALE_FACTORS:
            k = int(round(K * f))
            if k >= 30 and k not in Ks:
                Ks.append(k)
        if K not in Ks:
            Ks.append(K)

    results = []
    for k in Ks:
        h = max(5, int(round(H * k / K)))
        r = analyze_scale(ch, base_frame, tf_index, tf, k, h, end=end,
                          topk=topk, use_1m=use_1m,
                          boot_n=(boot_n if k == K else 0), status=status,
                          levels=levels, rng=rng, use_dtw=use_dtw,
                          cand_pool=cand_pool)
        results.append(r)

    primary = next((r for r in results if r['K'] == K), results[0])
    plan = dict(tf=tf, K=K, H=H, scales=results, primary=primary, trade=False,
                seed=seed, cost=total_cost(tf, H))

    sides = [r['side'] for r in results if r['side'] != 0]
    agree = len(sides) >= 2 and len(set(sides)) == 1 if multiscale else \
        len(sides) == 1
    plan['agree'] = agree
    plan['sides'] = sides

    if not primary.get('trade'):
        plan['reason'] = primary.get('reason', '관망')
        return plan
    if multiscale and not agree:
        plan['reason'] = (f'스케일 간 방향 불일치 (K={[r["K"] for r in results]}, '
                          f'side={[r["side"] for r in results]}) → 관망')
        return plan

    entry = float(ch.close[(end or ch.n) - 1])
    side = primary['side']
    tp, sl = primary['tp'], primary['sl']
    # 켈리 하한이 0이면 '거래 금지'가 아니라 점추정의 절반으로 베팅을 줄인다
    f_use = primary['kelly_low'] if primary['kelly_low'] > 0 \
        else 0.5 * primary['kelly']
    risk_frac = min(RISK_PER_TRADE, KELLY_FRACTION * f_use)
    if risk_frac <= 0:
        plan['reason'] = '켈리 기준 베팅 크기 0 → 관망'
        return plan
    plan['kelly_used'] = f_use

    plan.update(trade=True, side=side, entry=entry, tp=tp, sl=sl,
                rr=tp / sl, risk_frac=risk_frac,
                tp_px=entry * (1 + tp) if side > 0 else entry * (1 - tp),
                sl_px=entry * (1 - sl) if side > 0 else entry * (1 + sl),
                sizing=size_position(seed, sl, risk_frac, tf, H))
    return plan


# =============================================================================
# [10] 사이징 — 레버리지는 입력이 아니라 출력
# =============================================================================
def size_position(seed, sl, risk_frac, tf, H):
    """
    사용자 규칙 그대로:
      · 격리 증거금 = 시드 × MARGIN_CAP (20%)
      · 1회 최대 손실 = 시드 × risk_frac (2% 이내)
      · 레버리지 = 자연수로 '내림' → 실질 리스크는 항상 목표보다 작아진다
      · 명목 = 레버리지 × 증거금
    레버리지는 여전히 계산 결과이지 선택값이 아니다.
    """
    cost = total_cost(tf, H)
    risk = seed * risk_frac
    denom = sl + cost
    margin = seed * MARGIN_CAP
    notes = []

    want = risk / denom if denom > 1e-9 else 0.0          # 리스크가 허용하는 명목
    lev_raw = want / margin if margin > 1e-9 else 0.0
    lev = math.floor(lev_raw) if INTEGER_LEVERAGE else lev_raw
    if lev_raw >= 1 and lev < 1:
        lev = 1
    capped = False
    if lev > MAX_LEV:
        lev, capped = MAX_LEV, True
    notional = lev * margin
    risk_actual = notional * denom / seed if seed > 0 else 0.0
    executable = notional >= MIN_NOTIONAL and lev >= 1

    if INTEGER_LEVERAGE and lev >= 1:
        notes.append(f'· 레버리지 {lev_raw:.2f}x → 자연수 내림 {int(lev)}x '
                     f'⇒ 실질 리스크 {risk_actual:.3%} (목표 {risk_frac:.2%} 이내)')
    if capped:
        notes.append(f'⚠ 필요 레버리지가 상한 {MAX_LEV:.0f}x를 초과해 잘렸습니다 '
                     f'(리스크는 더 작아짐)')
    if not executable:
        max_sl = risk / max(MIN_NOTIONAL, 1e-9) - cost
        need_lev = math.ceil(MIN_NOTIONAL / max(margin, 1e-9))
        notes.append(f'✖ 규칙 내 실행 불가: 명목 {notional:,.1f} < 거래소 최소 '
                     f'{MIN_NOTIONAL:.0f} USDT')
        notes.append(f'   최소 명목을 채우려면 레버리지 {need_lev}x 이상이 필요하고, '
                     f'그때 손절은 {max_sl:.3%} 이내여야 함 (현재 {sl:.3%})')
        if ENTRY_TYPE == 'taker':
            notes.append(f'   ▶ 비용부터 줄일 것: 진입을 지정가로 바꾸면 '
                         f'왕복 {cost_lose():.3%} → '
                         f'{MAKER_FEE + TAKER_FEE + SLIPPAGE_T:.3%}')

    liq = 0.9 / lev if lev > 1e-9 else float('inf')
    if np.isfinite(liq) and sl > liq * 0.7:
        notes.append(f'⚠ 손절({sl:.2%})이 추정 청산거리({liq:.2%})의 70% 초과 — 위험')
    return dict(risk=risk, risk_frac=risk_frac, risk_actual=risk_actual,
                notional=notional, margin=margin, lev=lev, lev_raw=lev_raw,
                liq_dist=liq, notes=notes, executable=executable, cost=cost)


# =============================================================================
# [11] 워크포워드 검증 (퍼지 + 엠바고) — 실전 투입 전 유일한 관문
# -----------------------------------------------------------------------------
#  각 평가 시점 t 에서 '그 이전 데이터만' 으로 동일 규칙을 적용하고,
#  이웃의 미래 구간이 질의 구간과 겹치지 않도록 퍼지·엠바고를 강제한다.
#  체결은 TF 해상도(같은 봉 동시도달=손절)로 보수적으로 판정한다 → 하한 추정.
# =============================================================================
def walk_forward(ch, tf_index, tf, K, H, sim_seed, start_idx=None, step=None,
                 topk=TOPK, boot_n=0, multiscale=False, use_dtw=True,
                 cand_pool=180, status=None, stop=None, levels_dyn=False,
                 enforce_min_notional=True):
    n = ch.n
    step = max(step or max(1, K // 2), H)  # V300: 미청산 미래를 다음 신호 자본에 선반영하지 않음
    t_start = int(start_idx if start_idx is not None else n * 0.7)
    t_start = max(t_start, 3 * K + 2 * H + 40)
    t_end = n - H - 1
    if t_start >= t_end:
        return dict(report='검증 구간 부족 — 시작일을 앞으로 당기거나 K·H를 줄이세요.',
                    trades=[], curve_t=[], curve_v=[], fr=np.array([]))

    equity = float(sim_seed)
    trades, curve_t, curve_v = [], [], []
    skipped = 0
    total = max(1, (t_end - t_start + step - 1) // step)
    done = 0
    rng = np.random.default_rng(11)

    for t in range(t_start, t_end, step):
        if stop and stop():
            break
        done += 1
        if status and done % 5 == 0:
            status(f'워크포워드 {done}/{total} | 트레이드 {len(trades)} | '
                   f'가상자산 {equity:,.2f}', 'blue')
        levels = None
        if levels_dyn:
            levels = sr_levels(ch.high[:t], ch.low[:t], ch.close[:t],
                               np.ones(t))
        plan = build_plan(ch, None, tf_index, tf, K, H, equity, end=t,
                          topk=topk, use_1m=False, boot_n=boot_n,
                          multiscale=multiscale, use_dtw=use_dtw,
                          cand_pool=cand_pool, levels=levels, rng=rng)
        if not plan.get('trade'):
            continue
        sz = plan['sizing']
        if not sz['executable']:
            skipped += 1
            if enforce_min_notional:
                continue          # 실제로 주문을 낼 수 없으므로 체결 자체가 없다
        entry = ch.close[t - 1]
        hi = (ch.high[t:t + H] / entry - 1.0)[None, :]
        lo = (ch.low[t:t + H] / entry - 1.0)[None, :]
        cl = (ch.close[t:t + H] / entry - 1.0)[None, :]
        pnl, code = bracket_vec(hi, lo, cl, plan['side'], plan['tp'], plan['sl'])
        frac = float(net_pnl(pnl, code, tf, H)[0])
        rf = sz['risk_actual']            # 정수 레버리지 내림이 반영된 실질 리스크
        r_mult = frac / max(plan['sl'], 1e-9)
        equity *= (1.0 + r_mult * rf)
        trades.append(dict(t=t, time=tf_index[t - 1], side=plan['side'],
                           frac=frac, code=int(code[0]), r_mult=r_mult,
                           risk=rf, lev=sz['lev'], notional=sz['notional'],
                           equity=equity, exec_ok=sz['executable']))
        curve_t.append(tf_index[t - 1])
        curve_v.append(equity)
        if equity <= sim_seed * 0.15:
            break

    fr = np.array([x['r_mult'] * x['risk'] for x in trades])
    rep = wf_report(trades, fr, curve_v, sim_seed, skipped, done, total,
                    tf_index, t_start, K, H, tf)
    return dict(report=rep, trades=trades, curve_t=curve_t, curve_v=curve_v, fr=fr)


def wf_report(trades, fr, curve_v, seed, skipped, done, total, tf_index,
              t_start, K, H, tf):
    L = ['━━━ 워크포워드 검증 (퍼지+엠바고, 각 시점마다 그 이전 데이터만 사용) ━━━',
         f'대상: {SYMBOL} {tf} | K={K} H={H} | 검증 시작 {tf_index[t_start]:%Y-%m-%d} '
         f'| 평가 시점 {done}/{total}']
    if len(fr) == 0:
        L += ['', '▶ 트레이드 0건 — 게이트·유의성·비용 필터가 전부 걸렀습니다.',
              '   이것 자체가 결과입니다: 현 설정에는 실전 투입 근거가 없습니다.',
              '   (필터를 풀어 거래수를 늘리는 것은 엣지를 만드는 게 아니라 '
              '노이즈를 사는 것입니다.)']
        return '\n'.join(L)

    rmul = np.array([x['r_mult'] for x in trades])
    wins = fr[fr > 0]
    losses = fr[fr <= 0]
    pf = (wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float('inf')
    worst = cur = 0
    for f in fr:
        cur = cur + 1 if f <= 0 else 0
        worst = max(worst, cur)
    eq = np.concatenate(([seed], np.asarray(curve_v, dtype=np.float64)))
    peak = np.maximum.accumulate(eq)
    mdd = float((1 - eq / peak).max())
    lr = np.diff(np.log(np.maximum(eq, 1e-9)))
    sr, sr0, dsr = deflated_sharpe(lr, n_trials=128)  # 거래수와 탐색시행수는 다른 개념
    per_year = {}
    for x in trades:
        y = x['time'].year
        per_year.setdefault(y, []).append(x['r_mult'])

    levs = [x.get('lev', 0) for x in trades]
    L += [
        '─' * 66,
        f'체결 {len(fr)}건 | 최소명목 미달로 주문 불가했던 신호 {skipped}건 '
        f'(자산곡선에서 제외됨)',
        f'평균 레버리지 {np.mean(levs):.1f}x (최대 {max(levs) if levs else 0:.0f}x) | '
        f'평균 1회 리스크 {np.mean([x["risk"] for x in trades]):.3%}',
        f'승률 {(fr > 0).mean():.1%} | 프로핏팩터 {pf:.2f} | 평균 {rmul.mean():+.3f}R '
        f'(R = 1회 리스크)',
        f'자산 {seed:,.0f} → {eq[-1]:,.2f} ({eq[-1] / seed - 1:+.1%}) | '
        f'MDD {mdd:.1%} | 최장 연속손실 {worst}회',
        f'샤프(트레이드 기준) {sr:.2f} | 시행보정 기대최대샤프 {sr0:.2f} | '
        f'DSR(편향보정 신뢰도) {dsr:.3f}',
        '─' * 66,
        '연도별 평균 R: ' + '  '.join(
            f'{y}:{np.mean(v):+.2f}({len(v)}건)' for y, v in sorted(per_year.items())),
        '─' * 66,
    ]
    if rmul.mean() <= 0:
        L.append('▶ 판정: 기대값 ≤ 0 — 실전 투입 금지.')
    elif dsr < 0.90:
        L.append(f'▶ 판정: 양(+)이지만 DSR {dsr:.2f} < 0.90 — 파라미터 탐색으로 인한 '
                 '우연일 가능성을 배제하지 못함. 기간·TF를 바꿔 재검증 필요.')
    elif len(fr) < 30:
        L.append(f'▶ 판정: 양(+)이고 DSR도 높지만 표본 {len(fr)}건은 너무 적음. '
                 '최소 50~100건 확보 후 재판정.')
    else:
        L.append('▶ 판정: 표본외 기준 양(+)의 기대값이며 시행횟수 보정 후에도 유의. '
                 '단, 엣지는 감쇠하므로 연도별 R 추이가 꺾이면 즉시 중단할 것.')
    L.append('※ 체결은 TF 해상도(같은 봉 동시도달=손절)로 판정한 보수적 하한입니다.')
    L.append('※ 가상 시드 복리 기준. 실계좌에서는 최소 명목가 제약이 추가로 작동합니다.')
    return '\n'.join(L)


# =============================================================================
# [11-b] 귀무 대조군(surrogate) — "이 전략이 가짜 비트코인에서도 돈을 버는가"
# -----------------------------------------------------------------------------
#  실전 판정의 최종 관문. 실제 BTC 수익률을 블록 단위로 뒤섞으면
#  변동성 클러스터링·팻테일·캔들 구조는 그대로 남고, '패턴 → 미래' 관계만 파괴된다.
#  이 가짜 데이터에서도 워크포워드 성적이 비슷하게 나온다면,
#  당신이 발견한 것은 엣지가 아니라 곡선 맞춤(curve fitting)이다.
# =============================================================================
def make_surrogate(df, block=240, seed=0):
    g = np.random.default_rng(seed)
    c = df['close'].values.astype(np.float64)
    n = len(c)
    r = np.zeros(n)
    r[1:] = np.diff(np.log(np.maximum(c, 1e-12)))
    up = df['high'].values / np.maximum(c, 1e-12)
    dn = df['low'].values / np.maximum(c, 1e-12)
    op = df['open'].values / np.maximum(c, 1e-12)
    vol = df['volume'].values.astype(np.float64)
    tbr = np.clip(df['taker_buy_base'].values / np.maximum(vol, 1e-12), 0, 1)

    order = []
    while len(order) < n:
        s = int(g.integers(0, max(1, n - block)))
        order.extend(range(s, min(s + block, n)))
    ix = np.array(order[:n], dtype=np.int64)

    rs = r[ix]
    px = c[0] * np.exp(np.cumsum(rs))
    out = pd.DataFrame(index=df.index[:n])
    out['close'] = px
    out['high'] = px * up[ix]
    out['low'] = px * dn[ix]
    out['open'] = px * op[ix]
    out['high'] = np.maximum.reduce([out['high'].values, out['open'].values, px])
    out['low'] = np.minimum.reduce([out['low'].values, out['open'].values, px])
    out['volume'] = vol[ix]
    out['taker_buy_base'] = vol[ix] * tbr[ix]
    out['trades'] = df['trades'].values[ix]
    out['era'] = np.float64(ERA_FUT)
    return out[STORE_COLS]


# =============================================================================
# [12] 저널 — 신호 기록 및 실제 결과 자동 채점
# =============================================================================
def journal_append(plan, tf_index):
    if not plan.get('trade'):
        return
    p = plan['primary']
    row = dict(signal_time=str(tf_index[-1]), tf=plan['tf'], K=plan['K'],
               H=plan['H'], side='LONG' if plan['side'] > 0 else 'SHORT',
               entry=plan['entry'], tp_px=plan['tp_px'], sl_px=plan['sl_px'],
               tp=plan['tp'], sl=plan['sl'], p_up=p.get('p_up'),
               exp_oof=p.get('ev_oof'), pval=p.get('pval'), n_nb=p.get('n'),
               status='OPEN', pnl='',
               note=('EXEC' if plan['sizing']['executable'] else 'NO_EXEC'))
    try:
        jdf = pd.read_csv(JOURNAL_PATH) if os.path.exists(JOURNAL_PATH) \
            else pd.DataFrame(columns=JCOLS)
        jdf = pd.concat([jdf, pd.DataFrame([row])], ignore_index=True)
        jdf.to_csv(JOURNAL_PATH, index=False)
    except Exception as e:
        print(f'[저널 기록 실패] {e}')


def journal_score(dm):
    if not os.path.exists(JOURNAL_PATH):
        return '채점할 신호 없음'
    jdf = pd.read_csv(JOURNAL_PATH)
    if jdf.empty:
        return '채점할 신호 없음'
    changed = 0
    frames = {}
    for i, r in jdf.iterrows():
        if str(r.get('status')) != 'OPEN':
            continue
        tf = str(r['tf'])
        if tf not in frames:
            frames[tf] = dm.get(tf)
        df = frames[tf]
        if df is None:
            continue
        try:
            t0 = pd.Timestamp(r['signal_time'])
            pos = int(df.index.get_indexer([t0])[0])
        except Exception:
            continue
        if pos < 0:
            continue
        H = int(r['H'])
        if pos + H >= len(df):
            continue
        entry = float(r['entry'])
        hi = (df['high'].values[pos + 1:pos + 1 + H] / entry - 1.0)[None, :]
        lo = (df['low'].values[pos + 1:pos + 1 + H] / entry - 1.0)[None, :]
        cl = (df['close'].values[pos + 1:pos + 1 + H] / entry - 1.0)[None, :]
        side = 1 if str(r['side']) == 'LONG' else -1
        pnl, code = bracket_vec(hi, lo, cl, side, float(r['tp']), float(r['sl']))
        jdf.at[i, 'status'] = {1: 'WIN', -1: 'LOSS', 0: 'TIMEOUT'}[int(code[0])]
        jdf.at[i, 'pnl'] = round(float(net_pnl(pnl, code, tf, H)[0]), 6)
        changed += 1
    jdf.to_csv(JOURNAL_PATH, index=False)
    closed = jdf[jdf['status'] != 'OPEN']
    msg = f'채점 {changed}건 갱신 | 누적 종결 {len(closed)}건'
    if len(closed):
        pnls = pd.to_numeric(closed['pnl'], errors='coerce').dropna()
        if len(pnls):
            msg += f' | 승률 {(pnls > 0).mean():.0%} | 평균 {pnls.mean():+.3%}/건'
    return msg


# =============================================================================
# [13] 리포트
# =============================================================================
BANNER = (
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
    ' [리스크 원칙 — 절대 규칙]  잃지 않는 것이 최우선\n'
    f' · 격리 증거금 = 시드의 {MARGIN_CAP:.0%}  ·  트레이드당 최대 손실 = 시드의 '
    f'{RISK_PER_TRADE:.0%}  ·  일일 -{DAILY_LOSS_LIMIT:.0%} 시 중단\n'
    ' · 레버리지는 선택값이 아니라 리스크와 손절거리에서 나오는 계산 결과다\n'
    ' · 유의하지 않으면 관망한다. 관망도 포지션이다.\n'
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
)


def render_report(plan, tf_index, ch, seed, dm_banner, levels=None):
    L = [dm_banner, '']
    tf, K, H = plan['tf'], plan['K'], plan['H']
    L.append(f'━━━ 스캔 결과 [{SYMBOL} {tf} | K={K} H={H} | 기준봉 '
             f'{tf_index[-1]:%Y-%m-%d %H:%M} UTC] ━━━')
    L.append(f'비용 모델: 진입 {ENTRY_TYPE} / 익절 {TP_TYPE} / 손절 {SL_TYPE} '
             f'→ 익절 시 {cost_win():.3%}, 손절 시 {cost_lose():.3%} '
             f'(+ 예상 펀딩 {funding_cost(tf, H):.3%})')
    L.append('')

    for r in plan['scales']:
        nb = r.get('nb')
        tag = f"K={r['K']:>4d}"
        if nb is None:
            L.append(f'  [{tag}] 이웃 확보 실패 — {r["reason"]}')
            continue
        yrs = pd.Series([tf_index[s].year for s in nb['starts']]).value_counts().sort_index()
        gname = ('★관측 전용(게이트 미통과)' if nb.get('observe_only')
                 else GATE_NAMES[min(nb['relax'], len(GATE_NAMES) - 1)])
        L.append(f'  [{tag}] 이웃 {r.get("n", 0)}개 · 게이트 {gname} · '
                 f'상승비율 {r.get("p_up", float("nan")):.0%} · '
                 f'최고상관 {max(nb["corr_shape"]):.4f} · '
                 f'연도 {" ".join(f"{y}×{c}" for y, c in yrs.items())}')
        if 'ev_oof' in r:
            pv = r.get('pval', float('nan'))
            pv_s = f'{pv:.3f}' if pv == pv else '검정생략'
            L.append(f'         표본외 기대값 {r["ev_oof"]:+.3%} | '
                     f'인샘플 {r.get("ev_in", 0):+.3%} | '
                     f'보수(TF해상도) {r.get("ev_conservative", float("nan")):+.3%} | '
                     f'p={pv_s} | '
                     f'켈리 {r.get("kelly", 0):.3f}(하한 {r.get("kelly_low", 0):.3f})')
        if not r.get('trade'):
            L.append(f'         → {r.get("reason", "관망")}')
    L.append('')

    p = plan['primary']
    view = pick_view(plan) or {}
    nb = view.get('nb')
    if nb:
        top = ' | '.join(
            f'{tf_index[s]:%Y-%m-%d %H:%M} (r={c:.4f})'
            for s, c in list(zip(nb['starts'], nb['corr_shape']))[:5])
        L.append(f'베스트 매치(K={view.get("K")}): {top}')
        L.append(f'FFT 상관 vs 직접내적 최대오차 {nb["fft_err"]:.2e} '
                 f'(무근사 검증 통과)')
        if nb.get('observe_only'):
            L.append('※ 이 이웃들은 게이트를 통과하지 못한 "가장 닮은 과거"입니다. '
                     '차트로 볼 수는 있지만 매매 근거로는 쓰지 않습니다.')
    else:
        L.append('베스트 매치: 없음 — 어떤 스케일에서도 이웃을 구성하지 못했습니다. '
                 '(히스토리 부족이거나 K가 과대)')
    if levels:
        px = plan.get('entry', ch.close[-1])
        sup, res = nearest_levels(levels, px)
        s_txt = f'{sup["price"]:,.1f}(터치 {sup["touches"]})' if sup else '없음'
        r_txt = f'{res["price"]:,.1f}(터치 {res["touches"]})' if res else '없음'
        L.append(f'구조 레벨: 지지 {s_txt}  |  현재가 {px:,.1f}  |  저항 {r_txt}')
    L.append('─' * 66)

    if not plan.get('trade'):
        L.append(f'▶ 관망 — {plan.get("reason", "조건 미충족")}')
        L.append('')
        L.append('   V200은 다음을 모두 만족해야만 진입 신호를 냅니다:')
        L.append(f'     ① 비중첩 이웃 {MIN_NEIGHBORS}개 이상')
        L.append(f'     ② 이웃 상승비율 ≥{UP_TH:.0%} 또는 ≤{DN_TH:.0%}')
        L.append('     ③ 표본외(OOF) 기대값 > 비용문턱')
        L.append(f'     ④ 부트스트랩 p < {PVAL_MAX} (무작위 이웃 대비 유의)')
        L.append('     ⑤ 켈리 하한 > 0')
        L.append('     ⑥ 다중 스케일 방향 합의')
        L.append('   하나라도 실패하면 관망합니다. 대부분의 시각에는 엣지가 없습니다.')
        L.append('')
        L.append('   ※ 패턴 검색 자체는 항상 수행됩니다. 게이트를 통과하지 못해도')
        L.append('     "가장 닮은 과거"는 위 베스트 매치와 차트 버튼으로 항상 볼 수 있습니다.')
        return '\n'.join(L)

    side_txt = 'LONG (매수)' if plan['side'] > 0 else 'SHORT (매도)'
    L.append(f'▶ 방향: {side_txt}      진입가(현재 종가): {plan["entry"]:,.1f}')
    snap_tag = ' [00/50 스냅]' if p.get('snapped') else ''
    L.append(f'   익절 TP  {plan["tp_px"]:>12,.1f}  ({plan["tp"]:+.3%})  '
             f'← 지정가{snap_tag}')
    L.append(f'   손절 SL  {plan["sl_px"]:>12,.1f}  ({-plan["sl"]:+.3%})  '
             f'← 시장가{snap_tag}   손익비 {plan["rr"]:.2f}   '
             f'(레벨 근거: {p.get("level_src", "-")})')
    L.append(f'   이웃 브래킷: 승 {p["win"]:.0%} / 패 {p["lose"]:.0%} / '
             f'만기청산 {p["tout"]:.0%}')
    L.append(f'   표본외 기대값 {p["ev_oof"]:+.3%} · 유의확률 p={p["pval"]:.4f} · '
             f'귀무평균 {p["null_mean"]:+.3%}')
    L.append(f'   최대 보유: {H}봉 = {INTERVALS[tf] * H / 60:.1f}시간 경과 시 무조건 청산')

    s = plan['sizing']
    L.append('─' * 66)
    L.append(f'[사이징]  시드 {seed:,.2f} USDT')
    L.append(f'   적용 리스크 {s["risk_frac"]:.3%} '
             f'(원칙 {RISK_PER_TRADE:.0%} 와 1/4켈리 '
             f'{KELLY_FRACTION * plan.get("kelly_used", 0):.3%} 중 작은 값) '
             f'→ 허용손실 {s["risk"]:,.3f} USDT')
    L.append(f'   켈리 점추정 {p["kelly"]:.3f} / 부트스트랩 하한 {p["kelly_low"]:.3f} '
             f'(하한이 0이면 점추정의 절반만 사용)')
    L.append(f'   격리 증거금 {s["margin"]:,.2f} USDT ({MARGIN_CAP:.0%}) × '
             f'레버리지 {int(s["lev"])}x = 명목 {s["notional"]:,.1f} USDT')
    L.append(f'   ⇒ 실질 1회 손실 {s["risk_actual"]:.3%} '
             f'({seed * s["risk_actual"]:,.3f} USDT) · '
             f'주문 수량 ≈ {s["notional"] / plan["entry"]:.5f} BTC')
    if np.isfinite(s['liq_dist']):
        L.append(f'   추정 청산거리 {s["liq_dist"]:.2%} '
                 f'(손절 대비 {s["liq_dist"] / max(plan["sl"], 1e-9):.1f}배 여유)')
    for nt in s['notes']:
        L.append('   ' + nt)
    L.append('─' * 66)
    L.append(f'저널 기록: {JOURNAL_PATH}')
    L.append('※ 과거 유사 ≠ 미래 보장. 이 출력은 통계적 참고이며 모든 책임은 사용자에게 있습니다.')
    return '\n'.join(L)


# =============================================================================
# [14] 차트 (GUI에서만 로드 — 헤드리스 임포트 가능하도록 지연 로딩)
# =============================================================================
_FONT_DONE = []


def _mpl():
    """
    matplotlib 초기화 + 한글 폰트 설정.

    ★ 로그 도배 수정:
      예전에는 font.family 에 ['Malgun Gothic','NanumGothic','AppleGothic',...]
      처럼 '없을 수도 있는 이름'을 그대로 나열했다. matplotlib 은 텍스트를 그릴
      때마다 목록을 앞에서부터 훑으면서 못 찾은 이름마다
      "findfont: Font family 'X' not found." 를 콘솔에 찍는다.
      (윈도우에는 NanumGothic/AppleGothic 이 없으므로 매번 2줄씩 쌓인다.
       한글 자체는 Malgun Gothic 으로 정상 출력되므로 동작에는 문제가 없었다.)
      → 이제 '실제로 설치된 폰트'만 골라서 지정하고, font_manager 로거도 낮춘다.
    """
    import logging
    import matplotlib
    try:
        import tkinter  # noqa: F401  — Tk가 실제로 있을 때만 TkAgg 로 전환
        matplotlib.use('TkAgg')
    except Exception:
        pass
    from matplotlib import font_manager as fm

    if not _FONT_DONE:
        for p in (r'C:\Windows\Fonts\malgun.ttf',
                  r'C:\Windows\Fonts\malgunbd.ttf',
                  r'C:\Windows\Fonts\NanumGothic.ttf',
                  r'C:\Windows\Fonts\gulim.ttc',
                  '/System/Library/Fonts/AppleSDGothicNeo.ttc',
                  '/Library/Fonts/AppleGothic.ttf',
                  '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'):
            if os.path.exists(p):
                try:
                    fm.fontManager.addfont(p)
                except Exception:
                    pass
        have = set()
        try:
            have = {f.name for f in fm.fontManager.ttflist}
        except Exception:
            pass
        pick = next((n for n in ('Malgun Gothic', 'NanumGothic',
                                 'Apple SD Gothic Neo', 'AppleGothic',
                                 'NanumBarunGothic', 'Noto Sans CJK KR',
                                 'Noto Sans KR', 'Gulim', 'Batang')
                     if n in have), None)
        matplotlib.rcParams['font.family'] = ([pick] if pick else []) + ['DejaVu Sans']
        matplotlib.rcParams['axes.unicode_minus'] = False
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
        _FONT_DONE.append(pick or '')
        if not pick:
            print('[안내] 한글 폰트를 찾지 못했습니다. 차트의 한글이 네모로 보일 수 '
                  '있습니다. (윈도우라면 맑은 고딕이 있어야 정상입니다)')

    try:
        import matplotlib.pyplot as plt
    except Exception:                     # Tk 없는 환경(헤드리스 등) 대비
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    return plt


def pick_view(plan):
    """
    차트용 결과 선택.
    ★ 버그 수정: 기존에는 plan['primary']에 이웃이 없으면(=게이트 미통과) 차트
      버튼이 '먼저 스캔을 실행하세요'를 띄웠다. 스캔은 이미 했는데 말이다.
      이제 primary에 이웃이 없으면 다른 스케일(K/2, 2K) 중 이웃이 있는 것을 쓰고,
      그마저 없을 때만 진짜 '이웃 없음'으로 보고한다.
    """
    if not plan:
        return None
    p = plan.get('primary') or {}
    if p.get('nb'):
        return p
    for r in plan.get('scales', []):
        if r.get('nb'):
            return r
    return None


def plot_paths(plan, tf):
    plt = _mpl()
    p = pick_view(plan)
    if p is None or 'paths' not in p:
        raise RuntimeError('이웃 경로가 없습니다.')
    HI, LO, CL = p['paths']
    T = CL.shape[1]
    mult = INTERVALS[tf] if (T == p['H'] * INTERVALS[tf]) else 1
    x = np.arange(1, T + 1) * (1.0 / 60.0 if mult > 1 else INTERVALS[tf] / 60.0)
    fig, ax = plt.subplots(figsize=(10, 5.4))
    for row in CL[:60]:
        ax.plot(x, row * 100, color='gray', alpha=0.30, lw=0.8)
    ax.fill_between(x, np.quantile(CL, 0.25, axis=0) * 100,
                    np.quantile(CL, 0.75, axis=0) * 100, alpha=0.18,
                    color='tab:blue')
    ax.plot(x, np.median(CL, axis=0) * 100, lw=2.2, color='tab:blue',
            label='이웃 중앙 경로')
    ax.axhline(0, color='black', lw=0.8)
    if plan.get('trade'):
        sgn = 1 if plan['side'] > 0 else -1
        ax.axhline(sgn * plan['tp'] * 100, ls='--', color='green',
                   label=f'TP {plan["tp"] * 100:.2f}%')
        ax.axhline(-sgn * plan['sl'] * 100, ls='--', color='red',
                   label=f'SL {plan["sl"] * 100:.2f}%')
        head = 'LONG' if plan['side'] > 0 else 'SHORT'
        head += f' (p={p.get("pval", float("nan")):.3f})'
    else:
        head = '관망'
    ax.set_xlabel('진입 후 경과 시간 (시간)')
    ax.set_ylabel('수익률 % (현재 변동성으로 스케일 보정)')
    ax.set_title(f'유사 이웃 {CL.shape[0]}개의 실제 미래 경로 — 판단: {head} '
                 f'· 상승비율 {p.get("p_up", 0):.0%}')
    ax.legend(loc='best', fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    plt.show(block=False)


def plot_match(plan, df):
    _mpl()                                  # 한글 폰트 설정 선행
    import matplotlib
    import mplfinance as mpf
    _fam = matplotlib.rcParams['font.family']   # mpf 스타일이 폰트를 덮지 않게 고정
    p = pick_view(plan)
    nb = p.get('nb') if p else None
    if not nb:
        raise RuntimeError('이웃이 없습니다.')
    K, H = p['K'], p['H']
    s = nb['starts'][0]
    a, b = max(0, s - K // 2), min(len(df), s + K + H)
    sl_df = df.iloc[a:b][['open', 'high', 'low', 'close', 'volume']]
    mc = mpf.make_marketcolors(up='green', down='red', inherit=True)
    sty = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='binance',
                             rc={'font.family': _fam,
                                 'axes.unicode_minus': False})
    mpf.plot(sl_df, type='candle', style=sty, volume=True,
             vlines=dict(vlines=[df.index[s + K - 1]], colors='blue',
                         linestyle='--', linewidths=1.5),
             title=(f'BEST MATCH {df.index[s]:%Y-%m-%d %H:%M} → '
                    f'{df.index[s + K - 1]:%Y-%m-%d %H:%M} '
                    f'(r={nb["corr_shape"][0]:.4f})'),
             tight_layout=True, block=False)
    mpf.show()


def plot_equity(res):
    if not res.get('curve_v'):
        return
    plt = _mpl()
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.4), sharex=False,
                             gridspec_kw=dict(height_ratios=[2, 1]))
    axes[0].plot(res['curve_t'], res['curve_v'], lw=1.6)
    axes[0].set_title('워크포워드 자산 곡선 (복리, 비용 차감, 보수적 체결)')
    axes[0].set_ylabel('Equity')
    axes[0].grid(alpha=0.3)
    r = res['fr']
    if len(r):
        axes[1].bar(range(len(r)), [x['r_mult'] for x in res['trades']],
                    color=['tab:green' if v > 0 else 'tab:red'
                           for v in [x['r_mult'] for x in res['trades']]])
        axes[1].set_ylabel('R 배수')
        axes[1].set_xlabel('트레이드 순번')
        axes[1].grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    plt.show(block=False)


# =============================================================================
# [15] GUI
# =============================================================================
def main_advanced():
    from tkinter import (Tk, Button, Entry, Label, StringVar, IntVar, OptionMenu,
                         Frame, Checkbutton, messagebox, END, DISABLED, NORMAL,
                         WORD)
    from tkinter.scrolledtext import ScrolledText

    class App:
        def __init__(self, root):
            self.root = root
            self.dm = DataManager(log=self.set_status)
            self.plan = None
            self.df = None
            self.tf = None
            self.levels = None
            self.stop_flag = False
            root.title(f'PatternEdge {__version__} — {SYMBOL} 무기한선물 '
                       f'· 통계적 참고 도구 (수익 보장 없음)')
            root.geometry('900x1000')
            root.protocol('WM_DELETE_WINDOW', self.close)

            Label(root, text=BANNER, justify='left', anchor='w',
                  font=('Malgun Gothic', 9), fg='#8B0000', bg='#FFF4F4'
                  ).pack(fill='x', padx=8, pady=(8, 2))

            # ── 0. 데이터 ──
            f0 = Frame(root, relief='groove', borderwidth=2, padx=10, pady=6)
            f0.pack(fill='x', padx=8, pady=3)
            Label(f0, text='0. 데이터 (1분봉을 원본으로 저장 → 5m/15m 자동 파생)',
                  font=('Malgun Gothic', 11, 'bold'), fg='#00695c'
                  ).grid(row=0, column=0, columnspan=6, sticky='w')
            self.dstat = Label(f0, text='상태: 미확인', anchor='w', justify='left',
                               font=('Consolas', 9))
            self.dstat.grid(row=1, column=0, columnspan=6, sticky='w')
            Button(f0, text='전체 히스토리 구축/점검', command=self.build_data,
                   bg='#00695c', fg='white').grid(row=2, column=0, pady=4, padx=2)
            Button(f0, text='최신봉 강제 갱신', command=self.refresh_data,
                   bg='#0277bd', fg='white').grid(row=2, column=1, padx=2)
            self.spot_var = IntVar(value=1 if USE_SPOT_PREHISTORY else 0)
            Checkbutton(f0, text='2017~2019 스팟 접합(검색용)',
                        variable=self.spot_var).grid(row=2, column=2, sticky='w')
            for c in range(6):
                f0.grid_columnconfigure(c, weight=1)

            # ── 1. 스캔 ──
            f1 = Frame(root, relief='groove', borderwidth=2, padx=10, pady=6)
            f1.pack(fill='x', padx=8, pady=3)
            Label(f1, text='1. 패턴 스캔 → 유의성 검정 → 매매 계획',
                  font=('Malgun Gothic', 12, 'bold'), fg='#1a4fa0'
                  ).grid(row=0, column=0, columnspan=9, sticky='w')
            Label(f1, text='TF').grid(row=1, column=0, sticky='e')
            self.tf_var = StringVar(root, value=TRADE_TF_DEFAULT)
            OptionMenu(f1, self.tf_var, *INTERVALS.keys()).grid(row=1, column=1, sticky='w')
            Label(f1, text='K').grid(row=1, column=2, sticky='e')
            self.k_e = Entry(f1, width=6)
            self.k_e.grid(row=1, column=3)
            Label(f1, text='H').grid(row=1, column=4, sticky='e')
            self.h_e = Entry(f1, width=6)
            self.h_e.grid(row=1, column=5)
            Label(f1, text='이웃수').grid(row=1, column=6, sticky='e')
            self.topk_e = Entry(f1, width=5)
            self.topk_e.grid(row=1, column=7)
            self.topk_e.insert(0, str(TOPK))
            Label(f1, text='시드(USDT)').grid(row=2, column=0, sticky='e')
            self.seed_e = Entry(f1, width=8)
            self.seed_e.grid(row=2, column=1, sticky='w')
            self.seed_e.insert(0, '71')
            self.ms_var = IntVar(value=1)
            Checkbutton(f1, text='다중 스케일 합의', variable=self.ms_var
                        ).grid(row=2, column=2, columnspan=2, sticky='w')
            self.boot_var = IntVar(value=1)
            Checkbutton(f1, text='유의성 검정(부트스트랩)', variable=self.boot_var
                        ).grid(row=2, column=4, columnspan=2, sticky='w')
            self.p1m_var = IntVar(value=1)
            Checkbutton(f1, text='1분봉 정밀 체결', variable=self.p1m_var
                        ).grid(row=2, column=6, columnspan=2, sticky='w')
            self.tf_var.trace_add('write', self._tf_changed)
            self._tf_changed()
            self.scan_btn = Button(f1, text='패턴 스캔 시작', command=self.run_scan,
                                   bg='#2e7d32', fg='white',
                                   font=('Malgun Gothic', 11, 'bold'), height=2)
            self.scan_btn.grid(row=3, column=0, columnspan=9, sticky='ew', pady=(8, 2))
            self.status = Label(f1, text='대기 중', anchor='w')
            self.status.grid(row=4, column=0, columnspan=9, sticky='w')
            for c in range(8):
                f1.grid_columnconfigure(c, weight=1)

            self.txt = ScrolledText(root, height=22, font=('Consolas', 10),
                                    wrap=WORD, state=DISABLED)
            self.txt.pack(fill='both', expand=True, padx=8, pady=3)

            fb = Frame(root)
            fb.pack(fill='x', padx=8)
            Button(fb, text='이웃 미래경로 차트', command=self.btn_paths).pack(side='left', padx=2)
            Button(fb, text='베스트 매치 캔들', command=self.btn_match).pack(side='left', padx=2)
            Button(fb, text='저널 채점', command=self.btn_journal).pack(side='left', padx=2)
            Button(fb, text='결과 저장(txt)', command=self.btn_save).pack(side='left', padx=2)

            # ── 2. 워크포워드 ──
            f3 = Frame(root, relief='groove', borderwidth=2, padx=10, pady=6)
            f3.pack(fill='x', padx=8, pady=(3, 8))
            Label(f3, text='2. 워크포워드 검증 — 실전 투입 전 유일한 관문',
                  font=('Malgun Gothic', 11, 'bold'), fg='#b71c1c'
                  ).grid(row=0, column=0, columnspan=9, sticky='w')
            Label(f3, text='시작일').grid(row=1, column=0)
            self.wf_start = Entry(f3, width=11)
            self.wf_start.grid(row=1, column=1)
            self.wf_start.insert(0, (utcnow() - timedelta(days=540)).strftime('%Y-%m-%d'))
            Label(f3, text='스텝(봉)').grid(row=1, column=2)
            self.wf_step = Entry(f3, width=6)
            self.wf_step.grid(row=1, column=3)
            Label(f3, text='가상시드').grid(row=1, column=4)
            self.wf_seed = Entry(f3, width=8)
            self.wf_seed.grid(row=1, column=5)
            self.wf_seed.insert(0, '10000')
            Button(f3, text='검증 실행', command=self.run_wf,
                   bg='#1565c0', fg='white').grid(row=1, column=6, padx=4)
            Button(f3, text='중단', command=self.stop_wf).grid(row=1, column=7)
            Button(f3, text='귀무 대조군(가짜 BTC) 검증',
                   command=lambda: self.run_wf(surrogate=True),
                   bg='#4527a0', fg='white').grid(row=3, column=0, columnspan=3,
                                                  sticky='ew', pady=3)
            Label(f3, text='← 같은 설정으로 "수익률을 블록 단위로 뒤섞은 가짜 BTC"에서 '
                           '검증합니다. 여기서도 비슷하게 벌면 그건 엣지가 아니라 곡선 맞춤입니다.',
                  font=('Malgun Gothic', 8), fg='#4527a0', wraplength=520,
                  justify='left').grid(row=3, column=3, columnspan=5, sticky='w')
            self.wfboot_var = IntVar(value=0)
            Checkbutton(f3, text='검증에도 유의성 검정 적용(매우 느림)',
                        variable=self.wfboot_var).grid(row=2, column=0, columnspan=4,
                                                       sticky='w')
            Label(f3, text='※ numba 미설치 시 DTW가 병목입니다. pip install numba 권장.',
                  font=('Malgun Gothic', 8), fg='gray'
                  ).grid(row=2, column=4, columnspan=4, sticky='w')

        # ── UI 헬퍼 ──
        def set_status(self, text, color='black'):
            try:
                self.root.after(0, lambda: self.status.config(text=text, fg=color))
            except Exception:
                print(text)

        def show(self, text):
            def _do():
                self.txt.configure(state=NORMAL)
                self.txt.delete('1.0', END)
                self.txt.insert(END, text)
                self.txt.configure(state=DISABLED)
            self.root.after(0, _do)

        def set_dstat(self, s):
            self.root.after(0, lambda: self.dstat.config(text=s))

        def _tf_changed(self, *a):
            tf = self.tf_var.get()
            k, h = RECOMMENDED.get(tf, (200, 100))
            self.k_e.delete(0, END)
            self.k_e.insert(0, str(k))
            self.h_e.delete(0, END)
            self.h_e.insert(0, str(h))

        # ── 데이터 ──
        def build_data(self):
            threading.Thread(target=self._build_worker, daemon=True).start()

        def _build_worker(self):
            try:
                global USE_SPOT_PREHISTORY
                USE_SPOT_PREHISTORY = bool(self.spot_var.get())
                self.set_status('아카이브에서 전체 히스토리 구축 중 (최초 1회, 수 분)', 'red')
                self.dm.build_full_history(
                    use_spot=USE_SPOT_PREHISTORY,
                    progress=lambda i, t, m: self.set_status(
                        f'[{i}/{t}] {m} 다운로드/캐시 중...', 'blue'))
                self.dm.ensure(force_refresh=True)
                self.set_dstat(self.dm.data_banner('1m'))
                self.set_status('데이터 준비 완료', 'green')
            except Exception as e:
                self.set_status(f'구축 실패: {e}', 'red')

        def refresh_data(self):
            threading.Thread(target=self._refresh_worker, daemon=True).start()

        def _refresh_worker(self):
            try:
                self.dm.ensure(force_refresh=True)
                self.dm.res_cache.clear()
                self.set_dstat(self.dm.data_banner('1m'))
                if self.dm.meta.get('error'):
                    self.set_status('갱신 실패 — 상단 데이터 상태를 확인하세요', 'red')
                else:
                    self.set_status('갱신 완료', 'green')
            except Exception as e:
                self.set_status(f'갱신 실패: {e}', 'red')

        # ── 스캔 ──
        def run_scan(self):
            try:
                tf = self.tf_var.get()
                K, H = int(self.k_e.get()), int(self.h_e.get())
                topk, seed = int(self.topk_e.get()), float(self.seed_e.get())
                if K < 30 or H < 5 or topk < MIN_NEIGHBORS or seed <= 0:
                    raise ValueError(f'K≥30, H≥5, 이웃수≥{MIN_NEIGHBORS}, 시드>0')
            except Exception as e:
                messagebox.showerror('입력 오류', str(e))
                return
            self.scan_btn.config(state=DISABLED)
            threading.Thread(target=self._scan_worker,
                             args=(tf, K, H, topk, seed), daemon=True).start()

        def _scan_worker(self, tf, K, H, topk, seed):
            try:
                self.set_status('데이터 확인/갱신 중...', 'blue')
                df = self.dm.get(tf)
                self.set_dstat(self.dm.data_banner(tf))
                if df is None or df.empty:
                    self.set_status('데이터 없음 — 먼저 [전체 히스토리 구축]', 'red')
                    return
                base = self.dm.base
                ch = Channels(df)
                self.levels = sr_levels(ch.high, ch.low, ch.close,
                                        df['volume'].values.astype(np.float64))
                plan = build_plan(
                    ch, base, df.index, tf, K, H, seed,
                    topk=topk, use_1m=bool(self.p1m_var.get()),
                    boot_n=BOOT_N if self.boot_var.get() else 0,
                    multiscale=bool(self.ms_var.get()),
                    status=self.set_status, levels=self.levels)
                self.plan, self.df, self.tf = plan, df, tf
                journal_append(plan, df.index)
                self.show(BANNER + '\n\n' + render_report(
                    plan, df.index, ch, seed, self.dm.data_banner(tf), self.levels))
                self.set_status('스캔 완료', 'green')
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.set_status(f'에러: {type(e).__name__}: {e}', 'red')
            finally:
                self.root.after(0, lambda: self.scan_btn.config(state=NORMAL))

        # ── 버튼 ──
        def _chart_guard(self):
            """차트 버튼 공통 사전점검 — 실패 사유를 정확히 구분해서 알려준다."""
            if self.plan is None:
                messagebox.showinfo('안내', '먼저 [패턴 스캔 시작]을 실행하세요.')
                return None
            v = pick_view(self.plan)
            if v is None:
                messagebox.showwarning(
                    '이웃 없음',
                    '스캔은 완료되었지만 어떤 스케일에서도 과거 이웃을 찾지 못했습니다.\n\n'
                    '가능한 원인:\n'
                    ' · 히스토리가 K·H에 비해 너무 짧음 → [전체 히스토리 구축] 실행\n'
                    ' · K를 너무 크게 잡음 → K를 줄여보세요\n'
                    ' · 현재 구간 변동성이 0에 가까움')
                return None
            return v

        def btn_paths(self):
            if self._chart_guard() is None:
                return
            try:
                plot_paths(self.plan, self.tf)
            except Exception as e:
                messagebox.showerror('차트 오류', f'{type(e).__name__}: {e}')

        def btn_match(self):
            v = self._chart_guard()
            if v is None:
                return
            try:
                plot_match(self.plan, self.df)
            except Exception as e:
                messagebox.showerror('차트 오류', f'{type(e).__name__}: {e}')

        def btn_journal(self):
            threading.Thread(target=self._journal_worker, daemon=True).start()

        def _journal_worker(self):
            try:
                msg = journal_score(self.dm)
                self.set_status(msg, 'green')
                self.root.after(0, lambda: messagebox.showinfo('저널 채점', msg))
            except Exception as e:
                self.set_status(f'저널 채점 실패: {e}', 'red')

        def btn_save(self):
            try:
                txt = self.txt.get('1.0', END)
                p = os.path.join(BASE_DIR,
                                 f'report_{utcnow():%Y%m%d_%H%M%S}.txt')
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(txt)
                messagebox.showinfo('저장', p)
            except Exception as e:
                messagebox.showerror('저장 실패', str(e))

        # ── 워크포워드 ──
        def run_wf(self, surrogate=False):
            try:
                tf = self.tf_var.get()
                K, H = int(self.k_e.get()), int(self.h_e.get())
                st = self.wf_start.get().strip()
                stp = self.wf_step.get().strip()
                step = int(stp) if stp else None
                seed = float(self.wf_seed.get())
            except Exception as e:
                messagebox.showerror('입력 오류', str(e))
                return
            self.stop_flag = False
            threading.Thread(target=self._wf_worker,
                             args=(tf, K, H, st, step, seed, surrogate),
                             daemon=True).start()

        def stop_wf(self):
            self.stop_flag = True
            self.set_status('중단 요청됨...', 'red')

        def _wf_worker(self, tf, K, H, st, step, seed, surrogate=False):
            try:
                df = self.dm.get(tf)
                if df is None or df.empty:
                    self.set_status('데이터 없음', 'red')
                    return
                head = ''
                if surrogate:
                    self.set_status('귀무 대조군(가짜 BTC) 생성 중...', 'blue')
                    df = make_surrogate(df, block=max(4 * K, 240),
                                        seed=int(time.time()) % 100000)
                    head = ('★★ 귀무 대조군(수익률 블록 셔플) 결과 — 여기 성적이 '
                            '실제 데이터와 비슷하면 엣지가 아니라 곡선 맞춤입니다 ★★\n\n')
                ch = Channels(df)
                try:
                    si = int(df.index.searchsorted(pd.Timestamp(st)))
                except Exception:
                    si = int(len(df) * 0.7)
                res = walk_forward(
                    ch, df.index, tf, K, H, seed, start_idx=si, step=step,
                    topk=int(self.topk_e.get()),
                    boot_n=(150 if self.wfboot_var.get() else 0),
                    multiscale=bool(self.ms_var.get()),
                    use_dtw=NUMBA_OK, cand_pool=180,
                    status=self.set_status, stop=lambda: self.stop_flag)
                self.show(head + self.dm.data_banner(tf) + '\n\n' + res['report'])
                self.root.after(0, lambda: plot_equity(res))
                self.set_status('검증 완료', 'green')
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.set_status(f'검증 에러: {type(e).__name__}: {e}', 'red')

        def close(self):
            self.stop_flag = True
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
            os._exit(0)

    root = Tk()
    app = App(root)
    if not NUMBA_OK:
        app.set_status('numba 미설치 — DTW 단계가 느립니다. pip install numba 권장.',
                       'red')

    def _boot():
        try:
            app.dm.ensure()
            app.set_dstat(app.dm.data_banner('1m'))
        except Exception as e:
            pq, cs = DataManager._paths()
            has = os.path.exists(pq) or os.path.exists(cs)
            if has:
                app.set_dstat(
                    f'캐시를 읽지 못했습니다 — {type(e).__name__}: {e}\n'
                    f'[전체 히스토리 구축/점검]을 누르면 raw 폴더의 받아둔 파일로 '
                    f'네트워크 없이 재구축합니다.')
            else:
                app.set_dstat('데이터 없음 — [전체 히스토리 구축/점검]을 먼저 실행하세요.\n'
                              f'({type(e).__name__}: {e})')
    threading.Thread(target=_boot, daemon=True).start()
    root.mainloop()




# =============================================================================
# [15-b] V400 ANALOG-FIRST DECISION ENGINE
# =============================================================================
# 실시간 의사결정용 엔진. 기존 V200/V300 연구 엔진은 --advanced에서 그대로 보존한다.
# V400은 "Analog가 먼저 말하고, 나머지는 검증만 한다"는 구조다.
V400_ANALOG_WEIGHTS = {
    'shape':  0.45,   # 가격 형상
    'ret':    0.20,   # 수익률 동역학
    'volume': 0.15,   # 거래량 형상
    'vol':    0.10,   # 실현변동성 궤적
    'rng':    0.10,   # 캔들 레인지 구조
}
V400_CAND_POOL       = 700
V400_MIN_MED_SHAPE   = 0.78
V400_MIN_NEFF        = 10.0
V400_EDGE_PROB_MIN   = 0.72
V400_BOOT_N          = 160       # 실시간용 selection-aware null 반복
V400_POST_BOOT       = 800       # edge 확률/하한 추정
V400_KELLY_Q         = 0.20
V400_RISK_CAP        = 0.010     # 계좌 최대 1% 손실
V400_RISK_FLOOR      = 0.0015    # 너무 작은 베팅은 거래 가치가 낮으므로 WAIT
V400_MARGIN_CAP      = 0.30      # 증거금 최대 35%; 레버리지를 낮추기 위한 여유
V400_MAX_LEV         = 5
V400_SPREAD_MAX_BPS  = 5.0
V400_FUNDING_WARN    = 0.0015    # |0.15%|/funding interval 이상이면 극단으로 간주
V400_SCALE_FACTORS   = (0.5, 1.0, 2.0)
V400_NULL_SEED       = 20260919


def _safe_json(url, timeout=8):
    try:
        return json.loads(http_get(url, timeout=timeout).decode('utf-8'))
    except Exception:
        return None


def fetch_exchange_context():
    """API key 없이 얻을 수 있는 현재 선물시장 컨텍스트 + 거래규칙. 실패해도 분석은 계속."""
    out = dict(ok=False, min_notional=MIN_NOTIONAL, tick_size=0.1,
               qty_step=0.001, min_qty=0.001, spread_bps=float('nan'),
               funding_rate=float('nan'), premium_bps=float('nan'),
               open_interest=float('nan'), price_change_24h=float('nan'),
               quote_volume_24h=float('nan'), warnings=[])
    ex = _safe_json(f'{FAPI_BASE}/fapi/v1/exchangeInfo')
    if isinstance(ex, dict):
        try:
            sym = next(x for x in ex.get('symbols', []) if x.get('symbol') == SYMBOL)
            for f in sym.get('filters', []):
                ft = f.get('filterType')
                if ft == 'PRICE_FILTER':
                    out['tick_size'] = float(f.get('tickSize', out['tick_size']))
                elif ft == 'LOT_SIZE':
                    out['qty_step'] = float(f.get('stepSize', out['qty_step']))
                    out['min_qty'] = float(f.get('minQty', out['min_qty']))
                elif ft in ('MIN_NOTIONAL', 'NOTIONAL'):
                    out['min_notional'] = float(f.get('notional', f.get('minNotional', out['min_notional'])))
        except Exception as e:
            out['warnings'].append(f'exchangeInfo parse: {e}')

    prem = _safe_json(f'{FAPI_BASE}/fapi/v1/premiumIndex?symbol={SYMBOL}')
    if isinstance(prem, dict):
        try:
            mark = float(prem['markPrice']); idx = float(prem['indexPrice'])
            out['funding_rate'] = float(prem.get('lastFundingRate', float('nan')))
            out['premium_bps'] = (mark / idx - 1.0) * 10000.0 if idx else float('nan')
            out['mark_price'] = mark
            out['next_funding_time'] = int(prem.get('nextFundingTime', 0) or 0)
        except Exception as e:
            out['warnings'].append(f'premium parse: {e}')

    book = _safe_json(f'{FAPI_BASE}/fapi/v1/ticker/bookTicker?symbol={SYMBOL}')
    if isinstance(book, dict):
        try:
            bid, ask = float(book['bidPrice']), float(book['askPrice'])
            mid = (bid + ask) / 2.0
            out['spread_bps'] = (ask - bid) / mid * 10000.0 if mid else float('nan')
            out['bid'], out['ask'] = bid, ask
        except Exception as e:
            out['warnings'].append(f'book parse: {e}')

    oi = _safe_json(f'{FAPI_BASE}/fapi/v1/openInterest?symbol={SYMBOL}')
    if isinstance(oi, dict):
        try: out['open_interest'] = float(oi.get('openInterest', float('nan')))
        except Exception: pass

    t24 = _safe_json(f'{FAPI_BASE}/fapi/v1/ticker/24hr?symbol={SYMBOL}')
    if isinstance(t24, dict):
        try:
            out['price_change_24h'] = float(t24.get('priceChangePercent', float('nan'))) / 100.0
            out['quote_volume_24h'] = float(t24.get('quoteVolume', float('nan')))
        except Exception: pass
    out['ok'] = True
    return out


def _percentile_rank(x, hist):
    h = np.asarray(hist, dtype=np.float64)
    h = h[np.isfinite(h)]
    if not len(h) or not np.isfinite(x):
        return 0.5
    return float((h <= x).mean())


def local_activity_context(df, ch, lookback=5760):
    """방향을 결정하지 않는 activity/regime 설명자. 15m 기준 약 60일을 기본 사용."""
    n = len(df); a = max(0, n - lookback)
    vol = df['volume'].values.astype(np.float64)
    rg = (df['high'].values - df['low'].values) / np.maximum(df['close'].values, 1e-12)
    atr_p = _percentile_rank(float(ch.atr[-1]), ch.atr[a:])
    vol_p = _percentile_rank(float(vol[-1]), vol[a:])
    rng_p = _percentile_rank(float(rg[-1]), rg[a:])
    score = float(np.mean([atr_p, vol_p, rng_p]))
    return dict(activity_score=score, atr_pct=atr_p, volume_pct=vol_p, range_pct=rng_p,
                flow_now=float(ch.flow[-1]))


def _session_similarity(tf_index, ends, query_end):
    """24/7 시장에서도 같은 세션 기억에 작은 가산점. 하드 필터가 아니다."""
    try:
        qts = pd.Timestamp(tf_index[int(query_end)])
        if qts.tzinfo is None: qts = qts.tz_localize('UTC')
        qts = qts.tz_convert(SESSION_TZ)
        qmin = qts.hour * 60 + qts.minute
        vals = []
        for e in ends:
            ts = pd.Timestamp(tf_index[int(e)])
            if ts.tzinfo is None: ts = ts.tz_localize('UTC')
            ts = ts.tz_convert(SESSION_TZ)
            m = ts.hour * 60 + ts.minute
            d = abs(m - qmin); d = min(d, 1440 - d)
            vals.append(0.5 + 0.5 * math.cos(2 * math.pi * d / 1440.0))
        return np.asarray(vals, dtype=np.float64)
    except Exception:
        return np.full(len(ends), 0.5, dtype=np.float64)


def find_neighbors_v400(ch, tf_index, K, H, end=None, topk=TOPK,
                        status=None, cand_pool=V400_CAND_POOL, use_dtw=True):
    """Analog-first 검색: 가격/수익률/거래량 형상을 먼저 찾고 context는 나중에 검증한다."""
    n = ch.n if end is None else min(int(end), ch.n)
    if n < 3 * K + 2 * H + 20:
        return None, '데이터 부족'
    qs = n - K
    embargo = H
    max_start = n - 2 * K - H - embargo
    if max_start < 10:
        return None, '검색 가능한 과거가 부족함'

    names = list(V400_ANALOG_WEIGHTS) + ['flow']
    q = {name: ch.window(name, qs, K) for name in names}
    q_vol = float(np.std(q['ret']))
    if q_vol < 1e-12:
        return None, '현재 변동성 0'
    if status: status('Analog memory: 전 구간 패턴 검색...', 'blue')

    prof, sds = {}, {}
    for name in names:
        T = getattr(ch, name)[:max_start + K]
        r, sd = corr_profile(q[name], T)
        prof[name] = r[:max_start + 1]
        sds[name] = sd[:max_start + 1]
    L = min(len(v) for v in prof.values())
    for name in names:
        prof[name] = prof[name][:L]; sds[name] = sds[name][:L]

    idx = np.arange(L)
    era = ch.era
    era_chg = np.zeros(ch.n); era_chg[1:] = (np.diff(era) != 0).astype(np.float64)
    cse = np.concatenate(([0.0], np.cumsum(era_chg)))
    span = K + H
    era_ok = (cse[np.minimum(idx + span, ch.n)] - cse[idx]) == 0
    # 너무 다른 변동성만 제거. 방향/flow/trend는 analog를 찾기 전에 막지 않는다.
    volr = sds['ret'] / max(q_vol, 1e-12)
    broad_vol_ok = (volr >= 1/3.0) & (volr <= 3.0)
    pool = np.flatnonzero(era_ok & broad_vol_ok)
    if len(pool) < MIN_NEIGHBORS:
        return None, f'유효 analog 후보 {len(pool)}개 < {MIN_NEIGHBORS}'

    core = np.zeros(L, dtype=np.float64)
    for name, w in V400_ANALOG_WEIGHTS.items():
        core += w * prof[name]

    pre = pool[np.argsort(-core[pool])][:max(int(cand_pool) * 3, topk * 8)]
    # 같은 뉴욕 세션에 작은 보너스만 준다. 패턴 자체가 여전히 압도적 비중.
    ses = _session_similarity(tf_index, pre + K - 1, n - 1)
    pre_score = core[pre] + 0.03 * ses
    cand = pre[np.argsort(-pre_score)][:max(int(cand_pool), topk * 3)]

    if use_dtw:
        if status: status(f'Analog memory: DTW 정밀 재순위 ({len(cand)} 후보)...', 'blue')
        tz = znorm(q['shape']); band = max(2, int(K * DTW_BAND_FRAC))
        dtws = np.empty(len(cand))
        for i, st in enumerate(cand):
            dtws[i] = dtw_band(tz, znorm(ch.shape[int(st):int(st)+K]), band)
        rank_score = dtws / (np.maximum(core[cand] + 1.05, 1e-6) ** 2)
        ordered = cand[np.argsort(rank_score)]
    else:
        ordered = cand[np.argsort(-core[cand])]

    excl = max(1, int(K * 0.80))
    starts = pick_nonoverlap(ordered, topk, excl)
    if len(starts) < MIN_NEIGHBORS:
        return None, f'독립 analog {len(starts)}개 < {MIN_NEIGHBORS}'

    starts_arr = np.asarray(starts, dtype=np.int64)
    ex_shape = corr_exact(q['shape'], ch.shape, starts_arr)
    ex_ret = corr_exact(q['ret'], ch.ret, starts_arr)
    ex_volume = corr_exact(q['volume'], ch.volume, starts_arr)
    fft_err = float(np.max(np.abs(ex_shape - prof['shape'][starts_arr])))
    nvol = np.array([float(np.std(ch.ret[s:s+K])) for s in starts_arr])
    scales = np.clip(q_vol / np.maximum(nvol, 1e-12), 1/3.0, 3.0)
    analog = np.array([float(core[s]) for s in starts_arr])
    # 유사도가 높은 표본이 몇 개에만 몰렸는지 진단한다.
    z = analog - np.max(analog)
    w = np.exp(np.clip(8.0 * z, -30, 0))
    neff = float((w.sum() ** 2) / max(np.square(w).sum(), 1e-12))
    med_shape = float(np.median(ex_shape))
    med_flow = float(np.median([prof['flow'][s] for s in starts_arr]))
    med_vol = float(np.median([prof['vol'][s] for s in starts_arr]))
    context_match = float(0.65 * med_flow + 0.35 * med_vol)

    return dict(starts=starts, K=K, H=H, end=n, qs=qs,
                corr_shape=ex_shape.tolist(), corr_ret=ex_ret.tolist(),
                corr_volume=ex_volume.tolist(),
                corr_flow=[float(prof['flow'][s]) for s in starts_arr],
                corr_vol=[float(prof['vol'][s]) for s in starts_arr],
                combo=analog.tolist(), vol_scale=scales.tolist(),
                pool=pool, q_vol=q_vol, max_start=max_start,
                fft_err=fft_err, era=[int(era[s]) for s in starts_arr],
                n_eff=neff, median_shape=med_shape,
                context_match=context_match, median_flow=med_flow, median_vol=med_vol,
                weak_analog=(med_shape < V400_MIN_MED_SHAPE)), None


def _event_clusters(starts, K, H):
    starts = np.asarray(starts, dtype=np.int64)
    order = np.argsort(starts)
    cid = np.empty(len(starts), dtype=np.int64)
    c = -1; right = -10**18
    for ix in order:
        st = int(starts[ix]); en = st + K + H
        if st > right:
            c += 1; right = en
        else:
            right = max(right, en)
        cid[ix] = c
    return cid


def _purged_two_folds(starts, K, H):
    cid = _event_clusters(starts, K, H)
    groups = [(g, np.flatnonzero(cid == g)) for g in np.unique(cid)]
    # 큰 cluster부터 두 fold에 균형 배치
    groups.sort(key=lambda z: -len(z[1]))
    folds = [[], []]; sizes = [0, 0]
    for _, ix in groups:
        j = 0 if sizes[0] <= sizes[1] else 1
        folds[j].extend(ix.tolist()); sizes[j] += len(ix)
    fa, fb = np.asarray(folds[0], dtype=int), np.asarray(folds[1], dtype=int)
    if len(fa) < 5 or len(fb) < 5:
        o = np.argsort(np.asarray(starts))
        cut = len(o)//2
        fa, fb = o[:cut], o[cut:]
    return fa, fb, cid


def _direction_mfe_mae(HI, LO, side):
    if side > 0:
        return np.maximum(HI.max(axis=1), 1e-6), np.maximum(-LO.min(axis=1), 1e-6)
    return np.maximum(-LO.min(axis=1), 1e-6), np.maximum(HI.max(axis=1), 1e-6)


def _oof_direction_v400(HI, LO, CL, starts, side, tf, K, H):
    n = len(starts)
    fa, fb, cid = _purged_two_folds(starts, K, H)
    mfe, mae = _direction_mfe_mae(HI, LO, side)
    oof = np.full(n, np.nan); ocode = np.zeros(n, dtype=np.int64)
    params = []; trials = 0
    for tr, te in ((fa, fb), (fb, fa)):
        if len(tr) < 5 or len(te) < 5: continue
        tp_g, sl_g = _grid_from(mfe[tr], mae[tr]); trials += len(tp_g)*len(sl_g)
        b = _best_on(HI[tr], LO[tr], CL[tr], side, tp_g, sl_g, tf, H)
        if b is None: continue
        pnl, code = bracket_vec(HI[te], LO[te], CL[te], side, b[1], b[2])
        oof[te] = net_pnl(pnl, code, tf, H); ocode[te] = code
        params.append((float(b[1]), float(b[2])))
    valid = np.isfinite(oof)
    if valid.sum() < max(8, int(0.6*n)):
        return None
    return dict(ev=float(np.mean(oof[valid])), net=oof[valid], code=ocode[valid],
                valid_idx=np.flatnonzero(valid), params=params,
                trials=max(1,trials), clusters=cid[valid])


def _cluster_boot_mean(values, clusters, n_boot=V400_POST_BOOT, rng=None):
    v = np.asarray(values, dtype=np.float64); c = np.asarray(clusters)
    rng = rng or np.random.default_rng(V400_NULL_SEED + 17)
    ug = np.unique(c)
    blocks = [v[c == g] for g in ug if np.any(c == g)]
    if not blocks:
        return np.array([float(np.mean(v))])
    out = np.empty(n_boot)
    for b in range(n_boot):
        picks = rng.integers(0, len(blocks), size=len(blocks))
        arr = np.concatenate([blocks[i] for i in picks])
        out[b] = float(np.mean(arr))
    return out


def _robust_kelly_v400(pnl_net, sl, n_boot=500, rng=None):
    """하한 Kelly가 0이면 억지로 살리지 않는다."""
    x = np.asarray(pnl_net, dtype=np.float64) / max(float(sl), 1e-9)
    if len(x) < 8 or np.mean(x) <= 0:
        return 0.0, 0.0
    grid = np.linspace(0.0, 0.20, 101)
    def opt(v):
        g = np.log1p(np.outer(grid, v))
        g[~np.isfinite(g)] = -1e12
        m = g.mean(axis=1); j = int(np.argmax(m))
        return float(grid[j]) if m[j] > 0 else 0.0
    fh = opt(x); rng = rng or np.random.default_rng(741)
    fs = np.empty(n_boot)
    for i in range(n_boot):
        fs[i] = opt(rng.choice(x, size=len(x), replace=True))
    return fh, float(np.quantile(fs, V400_KELLY_Q))


def _final_params_v400(ch, HI, LO, CL, side, tf, H, end, levels):
    mfe, mae = _direction_mfe_mae(HI, LO, side)
    tp_g, sl_g = _grid_from(mfe, mae)
    best = _best_on(HI, LO, CL, side, tp_g, sl_g, tf, H)
    if best is None: return None
    ev, tp, sl = best; src = 'analog distribution'
    entry = float(ch.close[int(end)-1])
    cost = total_cost(tf, H)
    if levels:
        sup, res = nearest_levels(levels, entry)
        atr = float(ch.atr[int(end)-1]); buf = max(0.10*atr, 0.0005)
        tp2, sl2 = tp, sl
        if side > 0:
            if sup is not None:
                d = (entry - sup['price'])/entry + buf
                if 0.4*sl <= d <= 2.2*sl: sl2 = d
            if res is not None:
                d = (res['price'] - entry)/entry - buf
                if d > 0: tp2 = min(tp2, d)
        else:
            if res is not None:
                d = (res['price'] - entry)/entry + buf
                if 0.4*sl <= d <= 2.2*sl: sl2 = d
            if sup is not None:
                d = (entry - sup['price'])/entry - buf
                if d > 0: tp2 = min(tp2, d)
        if tp2 > cost*2 and tp2/max(sl2,1e-9) >= MIN_RR:
            pnl2, code2 = bracket_vec(HI, LO, CL, side, tp2, sl2)
            ev2 = float(net_pnl(pnl2, code2, tf, H).mean())
            if ev2 >= ev * 0.90:   # 구조적 무효화점을 쓰되 EV를 과도하게 희생하지 않음
                tp, sl, ev, src = float(tp2), float(sl2), ev2, 'support/resistance + analog'
    if ROUND_LEVELS:
        tp_px = entry*(1+tp) if side>0 else entry*(1-tp)
        sl_px = entry*(1-sl) if side>0 else entry*(1+sl)
        tps = snap(tp_px, side, 'tp'); sls = snap(sl_px, side, 'sl')
        tp3 = abs(tps/entry-1); sl3 = abs(sls/entry-1)
        if tp3 > cost*2 and sl3 > 1e-5 and tp3/max(sl3,1e-9) >= MIN_RR:
            tp, sl = tp3, sl3; src += ' + 00/50'
    return dict(tp=float(tp), sl=float(sl), src=src, ev_in=float(ev))


def evaluate_direction_v400(ch, HI, LO, CL, starts, side, tf, K, H, end, levels, rng=None):
    oof = _oof_direction_v400(HI, LO, CL, starts, side, tf, K, H)
    if oof is None: return None
    final = _final_params_v400(ch, HI, LO, CL, side, tf, H, end, levels)
    if final is None: return None
    tp, sl = final['tp'], final['sl']
    pnl, code = bracket_vec(HI, LO, CL, side, tp, sl)
    net = net_pnl(pnl, code, tf, H)
    boot = _cluster_boot_mean(oof['net'], oof['clusters'], rng=rng)
    edge_prob = float((boot > 0).mean())
    edge_lb = float(np.quantile(boot, V400_KELLY_Q))
    cvar_n = max(1, int(math.ceil(0.20*len(oof['net']))))
    cvar = float(np.sort(oof['net'])[:cvar_n].mean())
    kh, kl = _robust_kelly_v400(oof['net'], sl, rng=rng)
    stability = 1.0
    if len(oof['params']) >= 2:
        arr = np.asarray(oof['params'])
        rel = np.std(arr, axis=0) / np.maximum(np.mean(arr, axis=0), 1e-9)
        stability = float(max(0.0, 1.0 - np.mean(np.clip(rel, 0, 1))))
    # 선택은 하한 edge가 최우선. EV/안정성은 동률 해소용.
    score = edge_lb/max(sl,1e-9) + 0.25*oof['ev']/max(sl,1e-9) + 0.10*stability
    return dict(side=int(side), ev_oof=float(oof['ev']), oof_net=oof['net'],
                edge_prob=edge_prob, edge_lb=edge_lb, cvar=cvar,
                kelly=kh, kelly_low=kl, score=float(score),
                tp=tp, sl=sl, rr=tp/max(sl,1e-9), level_src=final['src'],
                ev_in=float(np.mean(net)), win=float((code==1).mean()),
                lose=float((code==-1).mean()), tout=float((code==0).mean()),
                pnl_net=net, trials=oof['trials'], stability=stability,
                p_up=float((CL[:,-1]>0).mean()))


def _paths_for_starts_v400(ch, base_frame, tf_index, tf, K, H, starts, q_vol, use_1m=True):
    starts = np.asarray(starts, dtype=np.int64)
    nvol = np.array([float(np.std(ch.ret[s:s+K])) for s in starts])
    scales = np.clip(float(q_vol)/np.maximum(nvol,1e-12), 1/3.0, 3.0)
    pm = PathMaker(ch, base_frame, tf, K, H,
                   {int(s):float(v) for s,v in zip(starts,scales)}, use_1m=use_1m)
    if tf_index is not None: pm.bind_tf_index(tf_index)
    return pm.paths(starts)


def selection_aware_null_v400(ch, base_frame, tf_index, tf, K, H, nb,
                              observed, n_draw, use_1m=True, n_boot=V400_BOOT_N, rng=None):
    """방향 + TP/SL 선택까지 null마다 다시 수행해 selection bias를 일부 직접 벌한다."""
    rng = rng or np.random.default_rng(V400_NULL_SEED)
    chosen = np.asarray(nb['starts'], dtype=np.int64)
    pool = np.asarray(nb['pool'], dtype=np.int64)
    far = np.ones(len(pool), dtype=bool)
    sep = K + H
    for st in chosen:
        far &= np.abs(pool - int(st)) >= sep
    pool = pool[far]
    if len(pool) < n_draw*3:
        return 1.0, np.array([0.0])
    null = []
    attempts = 0
    while len(null) < n_boot and attempts < n_boot*5:
        attempts += 1
        perm = rng.permutation(pool)
        sample = pick_nonoverlap(perm, n_draw, max(K, int(0.8*K)))
        if len(sample) < n_draw: continue
        HI, LO, CL = _paths_for_starts_v400(ch, base_frame, tf_index, tf, K, H,
                                             sample, nb['q_vol'], use_1m=use_1m)
        vals = []
        for side in (1,-1):
            oo = _oof_direction_v400(HI,LO,CL,sample,side,tf,K,H)
            if oo is not None: vals.append(float(oo['ev']))
        if vals: null.append(max(vals))
    if not null: return 1.0, np.array([0.0])
    arr = np.asarray(null, dtype=np.float64)
    p = float((np.sum(arr >= observed)+1)/(len(arr)+1))
    return p, arr


def analyze_scale_v400(ch, base_frame, tf_index, tf, K, H, end=None,
                       topk=TOPK, levels=None, status=None, use_1m=True,
                       do_null=False, rng=None):
    nb, err = find_neighbors_v400(ch, tf_index, K, H, end=end, topk=topk, status=status)
    out = dict(K=K,H=H,trade=False,reason='',side=0)
    if nb is None:
        out['reason']=err; return out
    out['nb']=nb
    starts = nb['starts']
    HI,LO,CL = _paths_for_starts_v400(ch,base_frame,tf_index,tf,K,H,starts,nb['q_vol'],use_1m)
    out['paths']=(HI,LO,CL); out['n']=len(starts); out['p_up']=float((CL[:,-1]>0).mean())
    if nb.get('weak_analog'):
        out['reason']=(f'analog 품질 부족: 중앙 형상상관 {nb["median_shape"]:.3f} '
                       f'< {V400_MIN_MED_SHAPE:.2f}')
    cand=[]
    for side in (1,-1):
        c=evaluate_direction_v400(ch,HI,LO,CL,starts,side,tf,K,H,nb['end'],levels,rng)
        if c is not None: cand.append(c)
    out['candidates']=cand
    if not cand:
        out['reason']=out['reason'] or 'LONG/SHORT 모두 유효한 OOF 파라미터 없음'; return out
    cand.sort(key=lambda x:x['score'], reverse=True)
    best=cand[0]; out['winner']=best; out.update(best)
    if do_null:
        obs=max(c['ev_oof'] for c in cand)
        pv,null=selection_aware_null_v400(ch,base_frame,tf_index,tf,K,H,nb,obs,len(starts),
                                          use_1m=use_1m,rng=rng)
        out['pval']=pv; out['null_mean']=float(np.mean(null))
        best['pval']=pv; best['null_mean']=out['null_mean']
    else:
        out['pval']=float('nan'); out['null_mean']=float('nan')
    return out


def size_position_v400(seed, entry, sl, risk_frac, tf, H, rules):
    """리스크에서 명목을 먼저 구하고, 그 명목을 담을 수 있는 가장 낮은 레버리지를 선택."""
    seed=float(seed); entry=float(entry); sl=float(sl); risk_frac=float(risk_frac)
    cost=total_cost(tf,H); denom=sl+cost
    risk_budget=seed*risk_frac
    target=risk_budget/max(denom,1e-12)
    min_notional=float(rules.get('min_notional',MIN_NOTIONAL))
    target=max(target,min_notional)
    max_margin=seed*V400_MARGIN_CAP
    # 원하는 위험예산을 전부 쓰기 위해 과도한 레버리지를 요구한다면,
    # 레버리지를 올리는 대신 포지션 명목을 줄여 실제 위험을 낮춘다.
    capacity=max_margin*V400_MAX_LEV
    target=min(target,capacity)
    if target < min_notional:
        return dict(executable=False,reason='최소 명목을 안전한 레버리지/증거금으로 구현 불가',
                    risk_frac=risk_frac,risk_actual=0,margin=0,lev=0,notional=0,qty=0,cost=cost)
    lev=None
    for L in range(1,V400_MAX_LEV+1):
        if target/L <= max_margin:
            lev=L; break
    if lev is None:
        return dict(executable=False,reason='증거금/레버리지 상한 안에서 명목 구현 불가',
                    risk_frac=risk_frac,risk_actual=0,margin=0,lev=0,notional=0,qty=0,cost=cost)
    step=max(float(rules.get('qty_step',0.001)),1e-12)
    min_qty=float(rules.get('min_qty',step))
    qty=math.floor((target/entry)/step)*step
    if qty<min_qty: qty=min_qty
    notional=qty*entry; margin=notional/lev
    actual=notional*denom/max(seed,1e-12)
    executable=(notional>=min_notional*0.999 and margin<=max_margin*1.0001 and actual<=V400_RISK_CAP*1.02)
    return dict(executable=bool(executable),reason='' if executable else '거래소 최소명목/리스크 상한 불일치',
                risk=risk_budget,risk_frac=risk_frac,risk_actual=float(actual),
                margin=float(margin),lev=int(lev),notional=float(notional),qty=float(qty),
                liq_dist=(0.9/lev if lev else float('inf')),cost=cost)


def build_plan_v400(ch, base_frame, tf_index, tf, K, H, seed, rules,
                    topk=TOPK, use_1m=True, status=None, levels=None, rng=None):
    rng=rng or np.random.default_rng(V400_NULL_SEED)
    scales=[]
    for f in V400_SCALE_FACTORS:
        kk=max(30,int(round(K*f)))
        r=analyze_scale_v400(ch,base_frame,tf_index,tf,kk,H,topk=topk,levels=levels,
                             status=status,use_1m=use_1m,do_null=(kk==K),rng=rng)
        scales.append(r)
    primary=next((r for r in scales if r['K']==K),scales[0])
    plan=dict(tf=tf,K=K,H=H,scales=scales,primary=primary,trade=False,seed=seed)
    if 'winner' not in primary:
        plan['reason']=primary.get('reason','주 신호 없음'); return plan
    p=primary['winner']; p['nb']=primary.get('nb'); p['paths']=primary.get('paths'); p['n']=primary.get('n')
    p['p_up']=primary.get('p_up'); p['pval']=primary.get('pval',float('nan'))
    p['null_mean']=primary.get('null_mean',float('nan'))
    p['median_shape']=primary['nb'].get('median_shape') if primary.get('nb') else float('nan')
    p['n_eff']=primary['nb'].get('n_eff') if primary.get('nb') else 0
    p['context_match']=primary['nb'].get('context_match') if primary.get('nb') else 0
    primary.update(p)

    reasons=[]
    nb=primary['nb']
    if nb.get('weak_analog'): reasons.append(f'analog 형상상관 중앙값 {nb["median_shape"]:.3f} 부족')
    if nb.get('n_eff',0)<V400_MIN_NEFF: reasons.append(f'유효 독립표본 {nb.get("n_eff",0):.1f} 부족')
    if nb.get('context_match',0) < -0.25:
        reasons.append(f'analog context 불일치 ({nb.get("context_match",0):+.2f})')
    if p['ev_oof']<=0: reasons.append(f'OOF 순기대값 {p["ev_oof"]:+.3%} ≤ 0')
    if p['edge_lb']<=0: reasons.append(f'cluster-bootstrap edge 하한 {p["edge_lb"]:+.3%} ≤ 0')
    if p['edge_prob']<V400_EDGE_PROB_MIN: reasons.append(f'P(edge>0) {p["edge_prob"]:.1%} 부족')
    if np.isfinite(primary.get('pval',float('nan'))) and primary['pval']>PVAL_MAX:
        reasons.append(f'selection-aware p={primary["pval"]:.3f} > {PVAL_MAX}')
    if p['kelly_low']<=0: reasons.append('robust Kelly 하한 = 0')

    # 여러 문맥 길이에서 같은 방향을 지지해야 한다. 단, 다른 scale의 약한 신호는 표결에서 제외.
    votes=[]
    for r in scales:
        w=r.get('winner')
        if w and w.get('edge_lb',-1)>0 and w.get('edge_prob',0)>=0.60:
            votes.append(int(w['side']))
    same=sum(v==p['side'] for v in votes)
    if same<2: reasons.append(f'multiscale 합의 부족 ({votes})')

    if reasons:
        plan['reason']=' / '.join(reasons)+' → WAIT'; return plan

    # robust Kelly + 통계 확신에 따라 위험을 자동 축소. 상한은 1%.
    conf=max(0.0,min(1.0,(p['edge_prob']-0.50)/0.35))
    sample_conf=max(0.0,min(1.0,nb.get('n_eff',0)/25.0))
    risk=min(V400_RISK_CAP,0.25*p['kelly_low'])*conf*sample_conf
    if risk<V400_RISK_FLOOR:
        plan['reason']=f'계산된 합리적 계좌위험 {risk:.3%} < 최소 실행 {V400_RISK_FLOOR:.2%} → WAIT'; return plan
    entry=float(ch.close[-1])
    sz=size_position_v400(seed,entry,p['sl'],risk,tf,H,rules)
    if not sz['executable']:
        plan['reason']=sz['reason']+' → WAIT'; return plan
    plan.update(trade=True,side=p['side'],entry=entry,tp=p['tp'],sl=p['sl'],rr=p['rr'],
                risk_frac=risk,kelly_used=p['kelly_low'],sizing=sz,
                tp_px=entry*(1+p['tp']) if p['side']>0 else entry*(1-p['tp']),
                sl_px=entry*(1-p['sl']) if p['side']>0 else entry*(1+p['sl']),
                votes=votes,agree=same>=2)
    return plan


# =============================================================================
# [16] V400 ANALOG ONE-CLICK DESK — 사용자가 보는 것은 주문표 하나뿐
# =============================================================================
_ET = ZoneInfo(SESSION_TZ)
_KST = ZoneInfo(DISPLAY_TZ)


def _now_utc_aware():
    return datetime.now(timezone.utc)


def next_main_session(now=None):
    """다음 09:18 ET 평일 세션을 (ET, KST) aware datetime으로 반환."""
    now = now or _now_utc_aware()
    et_now = now.astimezone(_ET)
    d = et_now.date()
    for add in range(10):
        dd = d + timedelta(days=add)
        if dd.weekday() not in SESSION_WEEKDAYS:
            continue
        cand = datetime.combine(dd, dt_time(SESSION_HOUR_ET, SESSION_MINUTE_ET), tzinfo=_ET)
        if cand > et_now:
            return cand, cand.astimezone(_KST)
    dd = d + timedelta(days=10)
    cand = datetime.combine(dd, dt_time(SESSION_HOUR_ET, SESSION_MINUTE_ET), tzinfo=_ET)
    return cand, cand.astimezone(_KST)


def session_mode_text(et_dt):
    dst = et_dt.dst()
    summer = bool(dst and dst.total_seconds() != 0)
    return '서머타임' if summer else '비서머타임'


def _session_key_if_due(now=None):
    """현재가 09:18 ET의 해당 1분 안이면 YYYY-MM-DD 키를 반환, 아니면 None."""
    now = now or _now_utc_aware()
    et = now.astimezone(_ET)
    if et.weekday() not in SESSION_WEEKDAYS:
        return None
    if et.hour == SESSION_HOUR_ET and et.minute == SESSION_MINUTE_ET:
        return et.date().isoformat()
    return None


def daily_journal_guard(max_losses=3):
    """V400 1% 리스크 상한 기준: KST 하루 종결 LOSS가 3회면 당일 신규진입 차단."""
    if not os.path.exists(JOURNAL_PATH):
        return None
    try:
        j=pd.read_csv(JOURNAL_PATH)
        if j.empty or 'status' not in j: return None
        today=_now_utc_aware().astimezone(_KST).date()
        losses=0
        for _,r in j.iterrows():
            if str(r.get('status',''))!='LOSS': continue
            ts=pd.Timestamp(r.get('signal_time'))
            if ts.tzinfo is None: ts=ts.tz_localize('UTC')
            if ts.tz_convert(DISPLAY_TZ).date()==today: losses+=1
        if losses>=max_losses:
            return f'오늘 종결 손절 {losses}회 ≥ {max_losses}회 — 일일 kill-switch'
    except Exception:
        return None
    return None


def oneclick_scan(dm, seed, status=None):
    """V400 실전 호출: 갱신 → Analog-first → 양방향 검증 → context veto → 자동 사이징."""
    tf, K, H = ONECLICK_TF, ONECLICK_K, ONECLICK_H
    status = status or (lambda *a, **k: None)
    status('최신 1분봉 갱신...', 'blue')
    df = dm.get(tf, force_refresh=True)
    if df is None or df.empty:
        raise RuntimeError('데이터가 없습니다. 먼저 전체 히스토리를 구축하세요.')
    lag = float(dm.meta.get('lag_min', 9999))
    if not np.isfinite(lag) or lag > MAX_STALE_MIN:
        return dict(blocked=True, reason=f'데이터 지연 {lag:.0f}분 > {MAX_STALE_MIN}분',
                    tf=tf,K=K,H=H), df, None, None

    # 과거 OPEN 신호가 만료됐으면 먼저 채점하고, 당일 손실 kill-switch를 확인한다.
    try:
        journal_score(dm)
    except Exception:
        pass
    guard=daily_journal_guard()
    if guard:
        return dict(blocked=True,reason=guard,tf=tf,K=K,H=H), df, None, None

    status('현재 거래소 규칙·선물 컨텍스트 확인...', 'blue')
    exctx = fetch_exchange_context()
    if np.isfinite(exctx.get('spread_bps', float('nan'))) and exctx['spread_bps'] > V400_SPREAD_MAX_BPS:
        return dict(blocked=True,reason=f'호가 스프레드 {exctx["spread_bps"]:.2f}bp 과대',
                    tf=tf,K=K,H=H,exchange_context=exctx), df, None, None

    status('Analog memory 구축...', 'blue')
    ch = Channels(df)
    act = local_activity_context(df,ch)
    levels = sr_levels(ch.high,ch.low,ch.close,df['volume'].values.astype(np.float64))
    plan = build_plan_v400(ch,dm.base,df.index,tf,K,H,float(seed),exctx,
                           topk=ONECLICK_TOPK,use_1m=ONECLICK_USE_1M,
                           status=status,levels=levels)
    plan['exchange_context']=exctx; plan['activity_context']=act
    # 극단 funding은 방향을 뒤집지 않고 단지 새 포지션 진입을 veto한다.
    fr=exctx.get('funding_rate',float('nan'))
    if plan.get('trade') and np.isfinite(fr) and abs(fr)>V400_FUNDING_WARN:
        plan['trade']=False
        plan['reason']=f'funding 극단치 {fr:+.4%} — analog 방향은 유지하되 신규진입 WAIT'
    journal_append(plan,df.index)
    return plan,df,ch,levels


def render_oneclick_card(plan, seed, df=None, dm=None, next_kst=None):
    now_kst=_now_utc_aware().astimezone(_KST)
    next_txt=next_kst.strftime('%Y-%m-%d %H:%M KST') if next_kst else '-'
    head=['━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
          '      PatternEdge V400 — ANALOG ONE CLICK',
          '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
          f'현재시각   {now_kst:%Y-%m-%d %H:%M:%S KST}',
          f'시장       {SYMBOL} PERP','']
    if plan is None:
        return '\n'.join(head+['판정       아직 분석 전','',f'다음 자동   {next_txt}'])
    if plan.get('blocked'):
        return '\n'.join(head+['████████████  WAIT  ████████████','',
                               f'사유       {plan.get("reason","안전조건 미충족")}',
                               '',f'다음 자동   {next_txt}',head[0]])
    p=plan.get('primary',{})
    nb=p.get('nb') or {}
    ex=plan.get('exchange_context',{})
    act=plan.get('activity_context',{})
    if not plan.get('trade'):
        lines=head+['████████████  WAIT  ████████████','',
                    f'사유       {plan.get("reason","조건 미충족")}']
        if p.get('winner') or 'ev_oof' in p:
            if np.isfinite(p.get('ev_oof',float('nan'))): lines.append(f'OOF 순EV   {p["ev_oof"]:+.3%}')
            if np.isfinite(p.get('edge_prob',float('nan'))): lines.append(f'P(edge>0) {p["edge_prob"]:.1%}')
            if np.isfinite(p.get('pval',float('nan'))): lines.append(f'p-value    {p["pval"]:.4f}')
            if nb: lines.append(f'Analog     중앙 r={nb.get("median_shape",0):.3f} · N_eff={nb.get("n_eff",0):.1f}')
        lines += ['',f'다음 자동   {next_txt}',head[0]]
        return '\n'.join(lines)

    sz=plan['sizing']; side='LONG' if plan['side']>0 else 'SHORT'
    actual_loss=float(seed)*sz['risk_actual']; margin_pct=sz['margin']/max(float(seed),1e-12)
    qty=sz.get('qty',sz['notional']/max(plan['entry'],1e-9))
    lines=head+[f'████████████  {side:^5s}  ████████████','',
                f'진입       {plan["entry"]:,.1f} USDT',
                f'익절 TP    {plan["tp_px"]:,.1f} USDT   (+{plan["tp"]:.3%})',
                f'손절 SL    {plan["sl_px"]:,.1f} USDT   (-{plan["sl"]:.3%})',
                f'손익비     1 : {plan["rr"]:.2f}',
                f'최대보유   {INTERVALS[plan["tf"]]*plan["H"]/60:.1f}시간','',
                f'시드 사용  {margin_pct:.2%}  ({sz["margin"]:,.2f} USDT)',
                f'레버리지   {int(sz["lev"])}x 격리',
                f'주문수량   {qty:.6f} BTC',
                f'명목금액   {sz["notional"]:,.2f} USDT',
                f'최대손실   약 -{actual_loss:,.2f} USDT  (계좌 -{sz["risk_actual"]:.2%})','',
                f'Analog     중앙 형상 r={nb.get("median_shape",0):.3f} · N_eff={nb.get("n_eff",0):.1f}',
                f'OOF 순EV   {p.get("ev_oof",0):+.3%}',
                f'Edge 하한  {p.get("edge_lb",0):+.3%}',
                f'P(edge>0) {p.get("edge_prob",0):.1%}',
                f'p-value    {p.get("pval",float("nan")):.4f}',
                f'멀티스케일 {plan.get("votes",[])}',
                f'활동성     {act.get("activity_score",0.5):.0%}',]
    if np.isfinite(ex.get('spread_bps',float('nan'))): lines.append(f'스프레드   {ex["spread_bps"]:.2f} bp')
    if np.isfinite(ex.get('funding_rate',float('nan'))): lines.append(f'펀딩       {ex["funding_rate"]:+.4%}')
    lines += ['',f'다음 자동   {next_txt}',head[0],
              '※ 방향은 Analog가 결정하고, context/statistics/risk는 거부권만 가집니다.',
              '※ TP/SL 이동·레버리지 수동 증액 없이 주문표 그대로 쓰는 전제입니다.']
    return '\n'.join(lines)



def _json_safe_plan(obj):
    if isinstance(obj, dict):
        return {str(k): _json_safe_plan(v) for k,v in obj.items() if k not in ('paths','pnl_net','oof_net','pool')}
    if isinstance(obj, (list,tuple)):
        return [_json_safe_plan(v) for v in obj[:100]]
    if isinstance(obj, np.ndarray):
        return obj[:100].tolist()
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)): return float(obj)
    if isinstance(obj, (pd.Timestamp, datetime)): return str(obj)
    return obj


def main():
    from tkinter import Tk, Button, Entry, Label, IntVar, Checkbutton, Frame, messagebox, END, NORMAL, DISABLED, WORD
    from tkinter.scrolledtext import ScrolledText

    class OneClickApp:
        def __init__(self, root):
            self.root = root
            self.dm = DataManager(log=self.set_status)
            self.plan = None
            self.df = None
            self.ch = None
            self.levels = None
            self.last_auto_key = None
            self.running = False
            self.stop_flag = False

            root.title(f'PatternEdge {__version__} — {SYMBOL} ANALOG ONE CLICK')
            root.geometry('820x860')
            root.protocol('WM_DELETE_WINDOW', self.close)

            top = Frame(root, relief='groove', borderwidth=2, padx=12, pady=10)
            top.pack(fill='x', padx=10, pady=10)
            Label(top, text='PatternEdge V400 — ANALOG ONE CLICK',
                  font=('Malgun Gothic', 16, 'bold')).grid(row=0, column=0, columnspan=5, sticky='w')
            Label(top, text='시드(USDT)').grid(row=1, column=0, sticky='e', pady=8)
            self.seed_e = Entry(top, width=12, font=('Consolas', 12))
            self.seed_e.grid(row=1, column=1, sticky='w')
            self.seed_e.insert(0, '1000')

            self.auto_var = IntVar(value=1)
            Checkbutton(top, text='자동 세션 ON (뉴욕 09:18 ET, 평일 1회)',
                        variable=self.auto_var).grid(row=1, column=2, columnspan=3, sticky='w', padx=12)

            self.scan_btn = Button(top, text='지금 분석', command=self.run_now,
                                   bg='#1565c0', fg='white', height=2,
                                   font=('Malgun Gothic', 12, 'bold'))
            self.scan_btn.grid(row=2, column=0, columnspan=2, sticky='ew', pady=5)
            Button(top, text='상세 리포트', command=self.show_detail,
                   height=2).grid(row=2, column=2, sticky='ew', padx=4)
            Button(top, text='저널 채점', command=self.score_journal,
                   height=2).grid(row=2, column=3, sticky='ew', padx=4)
            Button(top, text='데이터 구축/복구', command=self.build_data,
                   height=2).grid(row=2, column=4, sticky='ew', padx=4)
            for c in range(5):
                top.grid_columnconfigure(c, weight=1)

            self.next_label = Label(root, text='', anchor='w', justify='left',
                                    font=('Malgun Gothic', 10))
            self.next_label.pack(fill='x', padx=12, pady=(0, 4))
            self.status = Label(root, text='시작 중...', anchor='w', fg='blue')
            self.status.pack(fill='x', padx=12, pady=(0, 6))

            self.txt = ScrolledText(root, height=30, font=('Consolas', 11),
                                    wrap=WORD, state=DISABLED)
            self.txt.pack(fill='both', expand=True, padx=10, pady=(0, 10))

            self.refresh_clock()
            threading.Thread(target=self.boot, daemon=True).start()

        def seed(self):
            v = float(self.seed_e.get())
            if v <= 0:
                raise ValueError('시드는 0보다 커야 합니다.')
            return v

        def set_status(self, text, color='black'):
            try:
                self.root.after(0, lambda: self.status.config(text=text, fg=color))
            except Exception:
                print(text)

        def show(self, text):
            def _do():
                self.txt.configure(state=NORMAL)
                self.txt.delete('1.0', END)
                self.txt.insert(END, text)
                self.txt.configure(state=DISABLED)
            self.root.after(0, _do)

        def next_session(self):
            et, kst = next_main_session()
            return et, kst

        def refresh_clock(self):
            try:
                et, kst = self.next_session()
                mode = session_mode_text(et)
                now = _now_utc_aware()
                delta = max(0, int((kst.astimezone(timezone.utc) - now).total_seconds()))
                hh, rem = divmod(delta, 3600)
                mm = rem // 60
                self.next_label.config(
                    text=(f'다음 자동 스캔: {kst:%Y-%m-%d %H:%M KST} '
                          f'({mode}, 뉴욕 {SESSION_HOUR_ET:02d}:{SESSION_MINUTE_ET:02d} ET) '
                          f'· 약 {hh}시간 {mm}분 후'))

                key = _session_key_if_due()
                if self.auto_var.get() and key and key != self.last_auto_key and not self.running:
                    self.last_auto_key = key
                    self.run_now(auto=True)
            except Exception as e:
                self.next_label.config(text=f'세션 시계 오류: {e}')
            self.root.after(AUTO_POLL_MS, self.refresh_clock)

        def boot(self):
            try:
                self.dm.ensure()
                self.set_status(self.dm.data_banner('1m'), 'green')
            except Exception as e:
                self.set_status(f'데이터 준비 필요: {type(e).__name__}: {e}', 'red')
            try:
                _, kst = self.next_session()
                self.show(render_oneclick_card(None, self.seed(), next_kst=kst))
            except Exception:
                pass

        def run_now(self, auto=False):
            if self.running:
                return
            try:
                seed = self.seed()
            except Exception as e:
                messagebox.showerror('입력 오류', str(e))
                return
            self.running = True
            self.scan_btn.config(state=DISABLED)
            who = '자동 세션' if auto else '수동'
            self.set_status(f'{who} 분석 시작...', 'blue')
            threading.Thread(target=self._scan_worker, args=(seed,), daemon=True).start()

        def _scan_worker(self, seed):
            try:
                plan, df, ch, levels = oneclick_scan(self.dm, seed, self.set_status)
                self.plan, self.df, self.ch, self.levels = plan, df, ch, levels
                _, next_kst = self.next_session()
                self.show(render_oneclick_card(plan, seed, df, self.dm, next_kst))
                if plan.get('trade'):
                    self.set_status('완료 — 주문표 생성됨', 'green')
                else:
                    self.set_status('완료 — WAIT', '#b26a00')
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.set_status(f'분석 실패: {type(e).__name__}: {e}', 'red')
            finally:
                self.running = False
                self.root.after(0, lambda: self.scan_btn.config(state=NORMAL))

        def show_detail(self):
            if not self.plan or self.df is None or self.ch is None:
                messagebox.showinfo('안내', '먼저 분석을 실행하세요.')
                return
            try:
                seed = self.seed()
                _, nk = self.next_session()
                text = render_oneclick_card(self.plan, seed, self.df, self.dm, nk)
                text += '\n\n[DATA]\n' + self.dm.data_banner(ONECLICK_TF)
                text += '\n\n[RAW PLAN]\n' + json.dumps(_json_safe_plan(self.plan), ensure_ascii=False, indent=2)
                w = __import__('tkinter').Toplevel(self.root)
                w.title('PatternEdge 상세 리포트')
                w.geometry('1000x850')
                box = ScrolledText(w, font=('Consolas', 10), wrap=WORD)
                box.pack(fill='both', expand=True)
                box.insert('1.0', text)
                box.configure(state=DISABLED)
            except Exception as e:
                messagebox.showerror('상세 리포트 오류', str(e))

        def score_journal(self):
            threading.Thread(target=self._score_worker, daemon=True).start()

        def _score_worker(self):
            try:
                msg = journal_score(self.dm)
                self.set_status(msg, 'green')
                self.root.after(0, lambda: messagebox.showinfo('저널 채점', msg))
            except Exception as e:
                self.set_status(f'저널 채점 실패: {e}', 'red')

        def build_data(self):
            if self.running:
                return
            self.running = True
            threading.Thread(target=self._build_worker, daemon=True).start()

        def _build_worker(self):
            try:
                self.set_status('전체 히스토리 구축/복구 중...', 'blue')
                self.dm.build_full_history(progress=lambda i, t, m:
                    self.set_status(f'[{i}/{t}] {m}', 'blue'))
                self.dm.ensure(force_refresh=True)
                self.set_status('데이터 구축 완료', 'green')
            except Exception as e:
                self.set_status(f'데이터 구축 실패: {e}', 'red')
            finally:
                self.running = False

        def close(self):
            self.stop_flag = True
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass

    root = Tk()
    app = OneClickApp(root)
    root.mainloop()


# =============================================================================
# [17] V500 ANALOG COUNCIL — hostile-audit production engine
# =============================================================================
# Design rule:
#   Analog memory proposes the trade.
#   Statistics tries to kill it.
#   Market context may veto or throttle it, never invent the direction.
#   Risk sizing assumes the model can be wrong.
#   The user sees only LONG / SHORT / WAIT and one order ticket.
#
# Major V500 changes vs V400:
#   - true non-overlap separation: K+H, not 0.8K
#   - futures-era analogs preferred; spot prehistory only fallback memory
#   - similarity concentration capped and explicit effective sample size
#   - 4-fold grouped cross-fit TP/SL; live TP/SL = median of fold choices
#   - Bayesian/bootstrap edge distribution with similarity weights
#   - LONG and SHORT both evaluated; ambiguous two-sided edge => WAIT
#   - matched-context null + familywise scale penalty
#   - arbitrary 00/50 snapping disabled in production; exchange tick only
#   - adverse funding / spread / OI shock / taker imbalance can veto or throttle
#   - journal/drawdown throttle before sizing
#   - low leverage preferred; unsafe capacity never "fixed" by adding leverage

V500_ANALOG_WEIGHTS = {
    'shape':  0.50,
    'ret':    0.20,
    'volume': 0.10,
    'vol':    0.10,
    'rng':    0.10,
}
V500_SCALE_FACTORS      = (0.5, 1.0, 2.0)
V500_CAND_POOL          = 900
V500_TOPK               = 36
V500_MIN_NEIGHBORS      = 18
V500_MIN_MED_SHAPE      = 0.80
V500_MIN_NEFF           = 12.0
V500_EDGE_PROB_MIN      = 0.78
V500_EDGE_Q              = 0.15
V500_NULL_N             = 180
V500_BOOT_N             = 1200
V500_KELLY_BOOT         = 700
V500_RISK_CAP           = 0.0100       # max 1.00% account loss budget
V500_RISK_FLOOR         = 0.0010       # below 0.10% risk: not worth forcing a fill
V500_MARGIN_CAP         = 0.30
V500_MAX_LEV            = 4
V500_SPREAD_MAX_BPS     = 4.0
V500_FUNDING_ADVERSE    = 0.0010       # 0.10% adverse funding = hard veto
V500_FUNDING_THROTTLE   = 0.00050      # 0.05% adverse funding = half risk
V500_OI_SHOCK           = 0.035        # 1h OI move 3.5% => risk throttle
V500_TAKER_OPPOSE       = 0.72         # buy/sell ratio opposing direction threshold
V500_FAMILYWISE_SCALES  = 3
V500_SIDE_GAP_MIN       = 0.06
V500_MIN_MOVE_COST_MULT = 3.0
V500_SPOT_PENALTY       = 0.05
V500_RECENCY_HALF_LIFE_DAYS = 900.0    # soft confidence only, never a hard filter
V500_NULL_SEED          = 50020260919
V500_PRODUCTION_ROUND_00_50 = False
V500_JOURNAL_JSONL      = os.path.join(BASE_DIR, f'{SYMBOL}_v500_signals.jsonl')

# Account-specific costs can be fixed once via environment variables without touching the model.
# Example: PATTERNEDGE_TAKER_FEE=0.0004 PATTERNEDGE_MAKER_FEE=0.0002
TAKER_FEE = float(os.environ.get('PATTERNEDGE_TAKER_FEE', TAKER_FEE))
MAKER_FEE = float(os.environ.get('PATTERNEDGE_MAKER_FEE', MAKER_FEE))
SLIPPAGE_T = float(os.environ.get('PATTERNEDGE_SLIPPAGE_T', SLIPPAGE_T))
FUNDING_PER_8H = float(os.environ.get('PATTERNEDGE_FUNDING_RESERVE_8H', FUNDING_PER_8H))


def _v500_soft_cap_weights(raw, cap=0.09):
    """Normalize positive weights while capping any one analog's influence."""
    x = np.asarray(raw, dtype=np.float64)
    x = np.maximum(x, 0.0)
    if not np.isfinite(x).all() or x.sum() <= 0:
        x = np.ones(len(x), dtype=np.float64)
    w = x / x.sum()
    if len(w) == 0:
        return w
    cap = max(float(cap), 1.0 / len(w))
    for _ in range(20):
        hi = w > cap
        if not hi.any():
            break
        excess = float((w[hi] - cap).sum())
        w[hi] = cap
        lo = ~hi
        if lo.any() and excess > 0:
            denom = float(w[lo].sum())
            if denom <= 0:
                w[lo] += excess / lo.sum()
            else:
                w[lo] += excess * w[lo] / denom
        w /= w.sum()
    return w / w.sum()


def _v500_weighted_quantile(values, weights, q):
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(v) & np.isfinite(w) & (w >= 0)
    if not ok.any():
        return float('nan')
    v, w = v[ok], w[ok]
    if w.sum() <= 0:
        w = np.ones_like(v)
    order = np.argsort(v)
    v, w = v[order], w[order]
    c = np.cumsum(w) / np.sum(w)
    return float(v[np.searchsorted(c, min(max(q, 0.0), 1.0), side='left').clip(0, len(v)-1)])


def _v500_weighted_mean(values, weights):
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(v) & np.isfinite(w) & (w >= 0)
    if not ok.any():
        return float('nan')
    v, w = v[ok], w[ok]
    if w.sum() <= 0:
        return float(np.mean(v))
    return float(np.dot(v, w) / w.sum())


def _v500_recency_factor(tf_index, starts, K, query_end):
    """Very soft structural-change confidence factor; old analogs still remain usable."""
    try:
        qts = pd.Timestamp(tf_index[int(query_end)])
        out = []
        for s in starts:
            ts = pd.Timestamp(tf_index[int(s) + int(K) - 1])
            days = max(0.0, float((qts - ts).total_seconds()) / 86400.0)
            out.append(0.50 + 0.50 * math.exp(-math.log(2) * days / V500_RECENCY_HALF_LIFE_DAYS))
        return np.asarray(out, dtype=np.float64)
    except Exception:
        return np.ones(len(starts), dtype=np.float64)


def _v500_model_fingerprint():
    import hashlib
    cfg = {
        'tf': ONECLICK_TF, 'K': ONECLICK_K, 'H': ONECLICK_H,
        'weights': V500_ANALOG_WEIGHTS, 'scales': V500_SCALE_FACTORS,
        'topk': V500_TOPK, 'edge_prob': V500_EDGE_PROB_MIN,
        'edge_q': V500_EDGE_Q, 'risk_cap': V500_RISK_CAP,
        'max_lev': V500_MAX_LEV, 'margin_cap': V500_MARGIN_CAP,
        'shape_min': V500_MIN_MED_SHAPE, 'neff_min': V500_MIN_NEFF,
    }
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]


V500_MODEL_ID = _v500_model_fingerprint()


def fetch_exchange_context_v500():
    """Public Binance futures context. All extra fields are veto/throttle inputs only."""
    out = fetch_exchange_context()
    out.update(dict(oi_change_1h=float('nan'), taker_buy_sell=float('nan'),
                    global_long_short=float('nan'), top_position_ratio=float('nan')))

    # USDⓈ-M public futures-data endpoints. Failures never fabricate values.
    oi_hist = _safe_json(f'{FAPI_BASE}/futures/data/openInterestHist?symbol={SYMBOL}&period=5m&limit=13')
    if isinstance(oi_hist, list) and len(oi_hist) >= 2:
        try:
            vals = np.asarray([float(x.get('sumOpenInterestValue', x.get('sumOpenInterest', 'nan')))
                               for x in oi_hist], dtype=np.float64)
            vals = vals[np.isfinite(vals) & (vals > 0)]
            if len(vals) >= 2:
                out['oi_change_1h'] = float(vals[-1] / vals[0] - 1.0)
        except Exception as e:
            out['warnings'].append(f'oiHist parse: {e}')

    taker = _safe_json(f'{FAPI_BASE}/futures/data/takerlongshortRatio?symbol={SYMBOL}&period=5m&limit=12')
    if isinstance(taker, list) and taker:
        try:
            buy = sum(float(x.get('buyVol', 0.0)) for x in taker)
            sell = sum(float(x.get('sellVol', 0.0)) for x in taker)
            if sell > 0:
                out['taker_buy_sell'] = float(buy / sell)
        except Exception as e:
            out['warnings'].append(f'taker parse: {e}')

    gls = _safe_json(f'{FAPI_BASE}/futures/data/globalLongShortAccountRatio?symbol={SYMBOL}&period=5m&limit=1')
    if isinstance(gls, list) and gls:
        try: out['global_long_short'] = float(gls[-1].get('longShortRatio', float('nan')))
        except Exception: pass
    tpr = _safe_json(f'{FAPI_BASE}/futures/data/topLongShortPositionRatio?symbol={SYMBOL}&period=5m&limit=1')
    if isinstance(tpr, list) and tpr:
        try: out['top_position_ratio'] = float(tpr[-1].get('longShortRatio', float('nan')))
        except Exception: pass
    return out


def find_neighbors_v500(ch, tf_index, K, H, end=None, topk=V500_TOPK,
                        status=None, cand_pool=V500_CAND_POOL, use_dtw=True):
    """Analog is first. Context can rank softly but cannot create a direction."""
    n = ch.n if end is None else min(int(end), ch.n)
    if n < 3*K + 2*H + 40:
        return None, '데이터 부족'
    qs = n - K
    embargo = H
    max_start = n - 2*K - H - embargo
    if max_start < 10:
        return None, '검색 가능한 과거가 부족함'

    names = list(V500_ANALOG_WEIGHTS) + ['flow']
    q = {name: ch.window(name, qs, K) for name in names}
    q_vol = float(np.std(q['ret']))
    if q_vol < 1e-12:
        return None, '현재 변동성 0'
    if status: status('V500 Analog memory: 전 구간 검색...', 'blue')

    prof, sds = {}, {}
    for name in names:
        T = getattr(ch, name)[:max_start + K]
        r, sd = corr_profile(q[name], T)
        prof[name] = r[:max_start+1]
        sds[name] = sd[:max_start+1]
    L = min(len(v) for v in prof.values())
    for name in names:
        prof[name] = prof[name][:L]; sds[name] = sds[name][:L]

    idx = np.arange(L)
    era = ch.era
    era_chg = np.zeros(ch.n); era_chg[1:] = (np.diff(era) != 0).astype(np.float64)
    cse = np.concatenate(([0.0], np.cumsum(era_chg)))
    span = K + H
    era_ok = (cse[np.minimum(idx + span, ch.n)] - cse[idx]) == 0
    volr = sds['ret'] / max(q_vol, 1e-12)
    broad_vol_ok = (volr >= 0.40) & (volr <= 2.50)
    base_pool = np.flatnonzero(era_ok & broad_vol_ok)
    if len(base_pool) < V500_MIN_NEIGHBORS:
        return None, f'유효 analog 후보 {len(base_pool)}개 부족'

    # Prefer futures history. Spot is only admitted if futures memory alone is insufficient.
    fut_pool = base_pool[ch.era[base_pool] == ERA_FUT]
    if len(fut_pool) >= max(V500_MIN_NEIGHBORS*3, topk*3):
        pool = fut_pool
        spot_fallback = False
    else:
        pool = base_pool
        spot_fallback = True

    core = np.zeros(L, dtype=np.float64)
    channel_stack = []
    for name, w in V500_ANALOG_WEIGHTS.items():
        core += float(w) * prof[name]
        channel_stack.append(prof[name])
    channel_stack = np.vstack(channel_stack)
    # Penalize a candidate whose similarity is driven by only one channel.
    weak_channel = np.quantile(channel_stack, 0.20, axis=0)
    core = 0.90*core + 0.10*weak_channel
    if spot_fallback:
        core = core - V500_SPOT_PENALTY * (ch.era[:L] == ERA_SPOT)

    pre = pool[np.argsort(-core[pool])][:max(cand_pool*3, topk*12)]
    ses = _session_similarity(tf_index, pre + K - 1, n - 1)
    pre_score = core[pre] + 0.02*ses
    cand = pre[np.argsort(-pre_score)][:max(cand_pool, topk*5)]

    if use_dtw:
        if status: status(f'V500 Analog memory: DTW 재순위 {len(cand)}개...', 'blue')
        qz = znorm(q['shape']); band = max(2, int(K*DTW_BAND_FRAC))
        dtw = np.empty(len(cand), dtype=np.float64)
        for i, s in enumerate(cand):
            dtw[i] = dtw_band(qz, znorm(ch.shape[int(s):int(s)+K]), band)
        # Core correlation is primary; DTW breaks near-ties.
        dnorm = (dtw - np.nanmin(dtw)) / max(np.nanstd(dtw), 1e-9)
        rank_score = core[cand] - 0.025*dnorm
        ordered = cand[np.argsort(-rank_score)]
    else:
        ordered = cand[np.argsort(-core[cand])]

    # True event independence: pattern + future must not overlap another selected event.
    sep = K + H
    starts = pick_nonoverlap(ordered, topk, sep)
    if len(starts) < V500_MIN_NEIGHBORS:
        return None, f'진짜 비중첩 analog {len(starts)}개 < {V500_MIN_NEIGHBORS}'

    starts_arr = np.asarray(starts, dtype=np.int64)
    exact = {name: corr_exact(q[name], getattr(ch, name), starts_arr)
             for name in V500_ANALOG_WEIGHTS}
    combo = np.zeros(len(starts_arr), dtype=np.float64)
    for name, wgt in V500_ANALOG_WEIGHTS.items():
        combo += float(wgt)*exact[name]
    weak = np.quantile(np.vstack([exact[nm] for nm in V500_ANALOG_WEIGHTS]), 0.20, axis=0)
    combo = 0.90*combo + 0.10*weak

    rec = _v500_recency_factor(tf_index, starts_arr, K, n-1)
    ses2 = _session_similarity(tf_index, starts_arr + K - 1, n-1)
    raw_w = np.exp(np.clip(7.0*(combo - np.max(combo)), -25, 0)) * rec * (0.90 + 0.10*ses2)
    weights = _v500_soft_cap_weights(raw_w, cap=0.09)
    neff = float(1.0 / max(np.square(weights).sum(), 1e-12))

    nvol = np.array([float(np.std(ch.ret[s:s+K])) for s in starts_arr])
    scales = np.clip(q_vol / np.maximum(nvol, 1e-12), 0.40, 2.50)
    fft_err = float(np.max(np.abs(exact['shape'] - prof['shape'][starts_arr])))
    med_shape = _v500_weighted_quantile(exact['shape'], weights, 0.50)
    med_ret = _v500_weighted_quantile(exact['ret'], weights, 0.50)

    return dict(starts=starts, K=K, H=H, end=n, qs=qs, pool=pool,
                q_vol=q_vol, max_start=max_start, vol_scale=scales.tolist(),
                similarity=combo.tolist(), weights=weights.tolist(), n_eff=neff,
                median_shape=float(med_shape), median_ret=float(med_ret),
                corr_shape=exact['shape'].tolist(), corr_ret=exact['ret'].tolist(),
                corr_volume=exact['volume'].tolist(), corr_vol=exact['vol'].tolist(),
                corr_rng=exact['rng'].tolist(), fft_err=fft_err,
                futures_only=not spot_fallback,
                weak_analog=(med_shape < V500_MIN_MED_SHAPE)), None


def _v500_fold_splits(starts, nfold=4):
    """Contiguous time-grouped CV: each fold is a different historical block."""
    s = np.asarray(starts, dtype=np.int64)
    order = np.argsort(s)
    chunks = [np.asarray(x, dtype=int) for x in np.array_split(order, nfold) if len(x)]
    splits = []
    for te in chunks:
        tr = np.setdiff1d(np.arange(len(s)), te, assume_unique=True)
        if len(tr) >= 8 and len(te) >= 3:
            splits.append((tr, te))
    return splits


def _best_on_weighted_v500(HI, LO, CL, side, tp_g, sl_g, tf, H, weights):
    best = None
    cost = total_cost(tf, H)
    w = np.asarray(weights, dtype=np.float64)
    w = w / max(w.sum(), 1e-12)
    for tp0 in tp_g:
        for sl0 in sl_g:
            tp, sl = float(tp0), float(sl0)
            if tp <= cost*2 or sl <= 1e-5 or tp/sl < MIN_RR:
                continue
            pnl, code = bracket_vec(HI, LO, CL, side, tp, sl)
            net = net_pnl(pnl, code, tf, H)
            ev = _v500_weighted_mean(net, w)
            # Robust objective: mean - small downside penalty, not raw mean alone.
            q20 = _v500_weighted_quantile(net, w, 0.20)
            obj = ev + 0.15*min(q20, 0.0)
            if best is None or obj > best[0]:
                best = (float(obj), tp, sl, float(ev))
    return best


def _oof_direction_v500(HI, LO, CL, starts, weights, side, tf, K, H):
    starts = np.asarray(starts, dtype=np.int64)
    weights = np.asarray(weights, dtype=np.float64)
    n = len(starts)
    splits = _v500_fold_splits(starts, nfold=4)
    if len(splits) < 3:
        return None
    mfe, mae = _direction_mfe_mae(HI, LO, side)
    oof = np.full(n, np.nan, dtype=np.float64)
    ocode = np.zeros(n, dtype=np.int64)
    params = []
    trials = 0
    for tr, te in splits:
        tp_g, sl_g = _grid_from(mfe[tr], mae[tr])
        trials += len(tp_g)*len(sl_g)
        b = _best_on_weighted_v500(HI[tr], LO[tr], CL[tr], side,
                                    tp_g, sl_g, tf, H, weights[tr])
        if b is None:
            continue
        pnl, code = bracket_vec(HI[te], LO[te], CL[te], side, b[1], b[2])
        oof[te] = net_pnl(pnl, code, tf, H)
        ocode[te] = code
        params.append((float(b[1]), float(b[2])))
    valid = np.isfinite(oof)
    if valid.sum() < max(12, int(0.70*n)) or len(params) < 3:
        return None
    wv = weights[valid]; wv = wv / max(wv.sum(), 1e-12)
    ev = _v500_weighted_mean(oof[valid], wv)
    # Production parameter is cross-fit consensus, not a fresh full-sample optimum.
    arr = np.asarray(params, dtype=np.float64)
    tp = float(np.median(arr[:,0])); sl = float(np.median(arr[:,1]))
    rel = np.std(arr, axis=0) / np.maximum(np.mean(arr, axis=0), 1e-9)
    stability = float(max(0.0, 1.0 - np.mean(np.clip(rel, 0, 1))))
    return dict(ev=float(ev), net=oof[valid], code=ocode[valid], weights=wv,
                params=params, tp=tp, sl=sl, trials=max(trials,1),
                stability=stability, valid_idx=np.flatnonzero(valid))


def _bayesian_boot_edge_v500(values, base_weights, n_boot=V500_BOOT_N, rng=None):
    """Bayesian bootstrap around similarity-weighted OOF outcomes."""
    v = np.asarray(values, dtype=np.float64)
    bw = np.asarray(base_weights, dtype=np.float64)
    bw = bw / max(bw.sum(), 1e-12)
    rng = rng or np.random.default_rng(V500_NULL_SEED + 71)
    out = np.empty(int(n_boot), dtype=np.float64)
    for i in range(int(n_boot)):
        e = rng.exponential(1.0, size=len(v))
        w = bw * e; w /= max(w.sum(), 1e-12)
        out[i] = float(np.dot(w, v))
    return out


def _robust_kelly_v500(values, base_weights, sl, n_boot=V500_KELLY_BOOT, rng=None):
    x = np.asarray(values, dtype=np.float64) / max(float(sl), 1e-9)
    bw = np.asarray(base_weights, dtype=np.float64)
    bw = bw / max(bw.sum(), 1e-12)
    if len(x) < 10 or np.dot(bw, x) <= 0:
        return 0.0, 0.0
    grid = np.linspace(0.0, 0.15, 121)
    def opt(v, w):
        g = np.log1p(np.outer(grid, v))
        g[~np.isfinite(g)] = -1e12
        m = g @ w
        j = int(np.argmax(m))
        return float(grid[j]) if m[j] > 0 else 0.0
    fhat = opt(x, bw)
    rng = rng or np.random.default_rng(V500_NULL_SEED + 99)
    fs = np.empty(int(n_boot), dtype=np.float64)
    for i in range(int(n_boot)):
        e = rng.exponential(1.0, size=len(x))
        w = bw*e; w /= max(w.sum(),1e-12)
        fs[i] = opt(x, w)
    return fhat, float(np.quantile(fs, V500_EDGE_Q))


def _tick_round_v500(price, side, kind, tick_size):
    """Production uses exchange tick, not arbitrary 00/50 anchoring."""
    t = max(float(tick_size or 0.1), 1e-12)
    p = float(price)
    if kind == 'tp':
        # Move slightly inward for fill probability.
        return math.floor(p/t)*t if side > 0 else math.ceil(p/t)*t
    # SL sits outward, never closer by rounding.
    return math.floor(p/t)*t if side > 0 else math.ceil(p/t)*t


def _final_params_v500(ch, HI, LO, CL, oof, side, tf, H, end, levels, rules):
    tp, sl = float(oof['tp']), float(oof['sl'])
    cost = total_cost(tf,H)
    entry = float(ch.close[int(end)-1])
    src = '4-fold cross-fit median'
    # Structure may move the stop outside an invalidation level, but cannot create a new optimum.
    if levels:
        sup, res = nearest_levels(levels, entry)
        atr = float(ch.atr[int(end)-1]); buf = max(0.08*atr, 0.0004)
        tp2, sl2 = tp, sl
        if side > 0:
            if sup is not None:
                d = (entry - sup['price'])/entry + buf
                if 0.65*sl <= d <= 1.60*sl: sl2 = float(d)
            if res is not None:
                d = (res['price'] - entry)/entry - buf
                if cost*2 < d < tp*1.10: tp2 = float(min(tp, d))
        else:
            if res is not None:
                d = (res['price'] - entry)/entry + buf
                if 0.65*sl <= d <= 1.60*sl: sl2 = float(d)
            if sup is not None:
                d = (entry - sup['price'])/entry - buf
                if cost*2 < d < tp*1.10: tp2 = float(min(tp, d))
        if tp2/max(sl2,1e-12) >= MIN_RR and tp2 > cost*2:
            tp, sl = tp2, sl2
            src += ' + structural invalidation'

    tick = float(rules.get('tick_size', 0.1))
    tppx = entry*(1+tp) if side>0 else entry*(1-tp)
    slpx = entry*(1-sl) if side>0 else entry*(1+sl)
    tppx = _tick_round_v500(tppx, side, 'tp', tick)
    slpx = _tick_round_v500(slpx, side, 'sl', tick)
    tp = abs(tppx/entry - 1.0); sl = abs(slpx/entry - 1.0)
    if tp <= cost*2 or sl <= 1e-5 or tp/max(sl,1e-12) < MIN_RR:
        return None
    return dict(tp=float(tp), sl=float(sl), tp_px=float(tppx), sl_px=float(slpx), src=src)


def evaluate_direction_v500(ch, HI, LO, CL, starts, weights, side, tf, K, H,
                            end, levels, rules, rng=None):
    oof = _oof_direction_v500(HI,LO,CL,starts,weights,side,tf,K,H)
    if oof is None:
        return None
    final = _final_params_v500(ch,HI,LO,CL,oof,side,tf,H,end,levels,rules)
    if final is None:
        return None

    boot = _bayesian_boot_edge_v500(oof['net'], oof['weights'], rng=rng)
    edge_prob = float(np.mean(boot > 0.0))
    edge_lb = float(np.quantile(boot, V500_EDGE_Q))
    cvar_cut = max(1, int(math.ceil(0.20*len(oof['net']))))
    cvar = float(np.mean(np.sort(oof['net'])[:cvar_cut]))
    kh, kl = _robust_kelly_v500(oof['net'], oof['weights'], final['sl'], rng=rng)

    # Does the analog set imply movement large enough to pay for execution?
    max_exc = np.maximum(np.max(HI,axis=1), -np.min(LO,axis=1))
    move_med = _v500_weighted_quantile(max_exc, weights, 0.50)

    # Score is dimensionless, conservative, and punishes downside/parameter instability.
    unit = max(final['sl'], 1e-9)
    score = (edge_lb/unit
             + 0.20*oof['ev']/unit
             + 0.10*oof['stability']
             + 0.08*min(cvar/unit, 0.0))
    return dict(side=int(side), ev_oof=float(oof['ev']), edge_prob=edge_prob,
                edge_lb=edge_lb, cvar=cvar, kelly=kh, kelly_low=kl,
                stability=oof['stability'], score=float(score),
                tp=final['tp'], sl=final['sl'], tp_px=final['tp_px'],
                sl_px=final['sl_px'], rr=final['tp']/max(final['sl'],1e-12),
                level_src=final['src'], move_median=float(move_med),
                oof_net=oof['net'], oof_weights=oof['weights'], trials=oof['trials'])


def _paths_for_starts_v500(ch, base_frame, tf_index, tf, K, H, starts, q_vol, use_1m=True):
    return _paths_for_starts_v400(ch,base_frame,tf_index,tf,K,H,starts,q_vol,use_1m)


def matched_null_v500(ch, base_frame, tf_index, tf, K, H, nb, rules,
                      observed, n_draw, use_1m=True, n_boot=V500_NULL_N, rng=None):
    """Context-matched null: destroys analog-history -> future link, reselects side/TP/SL."""
    rng = rng or np.random.default_rng(V500_NULL_SEED)
    pool = np.asarray(nb['pool'], dtype=np.int64)
    chosen = np.asarray(nb['starts'], dtype=np.int64)
    sep = K + H
    far = np.ones(len(pool), dtype=bool)
    for s in chosen:
        far &= np.abs(pool-int(s)) >= sep
    pool = pool[far]
    if len(pool) < n_draw*3:
        return 1.0, np.array([0.0])

    # Prefer same era and similar pattern-window volatility for null draws.
    qv = float(nb['q_vol'])
    pvol = np.array([float(np.std(ch.ret[s:s+K])) for s in pool])
    ratio = pvol/max(qv,1e-12)
    keep = (ratio >= 0.60) & (ratio <= 1.67)
    if keep.sum() >= n_draw*3:
        pool = pool[keep]

    vals = []
    attempts = 0
    while len(vals) < int(n_boot) and attempts < int(n_boot)*8:
        attempts += 1
        perm = rng.permutation(pool)
        sample = pick_nonoverlap(perm, n_draw, sep)
        if len(sample) < n_draw:
            continue
        HI,LO,CL = _paths_for_starts_v500(ch,base_frame,tf_index,tf,K,H,sample,qv,use_1m)
        ew = np.ones(len(sample),dtype=np.float64)/len(sample)
        side_vals=[]
        for side in (1,-1):
            oo=_oof_direction_v500(HI,LO,CL,sample,ew,side,tf,K,H)
            if oo is not None:
                side_vals.append(float(oo['ev']))
        if side_vals:
            vals.append(max(side_vals))
    if not vals:
        return 1.0, np.array([0.0])
    arr=np.asarray(vals,dtype=np.float64)
    p=float((np.sum(arr>=float(observed))+1)/(len(arr)+1))
    return p,arr


def analyze_scale_v500(ch,base_frame,tf_index,tf,K,H,rules,end=None,topk=V500_TOPK,
                       levels=None,status=None,use_1m=True,do_null=False,rng=None):
    out=dict(K=K,H=H,trade=False,reason='',side=0)
    nb,err=find_neighbors_v500(ch,tf_index,K,H,end=end,topk=topk,status=status)
    if nb is None:
        out['reason']=err; return out
    out['nb']=nb
    starts=np.asarray(nb['starts'],dtype=np.int64)
    weights=np.asarray(nb['weights'],dtype=np.float64)
    HI,LO,CL=_paths_for_starts_v500(ch,base_frame,tf_index,tf,K,H,starts,nb['q_vol'],use_1m)
    out['paths']=(HI,LO,CL); out['n']=len(starts)

    cand=[]
    for side in (1,-1):
        c=evaluate_direction_v500(ch,HI,LO,CL,starts,weights,side,tf,K,H,nb['end'],levels,rules,rng)
        if c is not None: cand.append(c)
    out['candidates']=cand
    if not cand:
        out['reason']='LONG/SHORT 모두 교차검증 가능한 주문구조 없음'; return out
    cand.sort(key=lambda x:x['score'],reverse=True)
    out['winner']=cand[0]; out.update(cand[0])
    out['runner_up']=cand[1] if len(cand)>1 else None
    if do_null:
        obs=max(c['ev_oof'] for c in cand)
        pv,null=matched_null_v500(ch,base_frame,tf_index,tf,K,H,nb,rules,obs,len(starts),use_1m,rng=rng)
        out['pval_raw']=pv
        out['pval_global']=min(1.0,pv*V500_FAMILYWISE_SCALES)
        out['null_mean']=float(np.mean(null))
    else:
        out['pval_raw']=float('nan'); out['pval_global']=float('nan'); out['null_mean']=float('nan')
    return out


def journal_risk_state_v500(seed):
    """Realized-loss governor. Never increases risk; only throttles or blocks."""
    state=dict(mult=1.0,blocked=False,reason='',today_losses=0,loss_streak=0)
    if not os.path.exists(JOURNAL_PATH):
        return state
    try:
        j=pd.read_csv(JOURNAL_PATH)
        if j.empty or 'status' not in j.columns:
            return state
        today=_now_utc_aware().astimezone(_KST).date()
        statuses=[]
        for _,r in j.iterrows():
            st=str(r.get('status',''))
            if st in ('WIN','LOSS'):
                statuses.append(st)
            if st=='LOSS':
                ts=pd.Timestamp(r.get('signal_time'))
                if ts.tzinfo is None: ts=ts.tz_localize('UTC')
                if ts.tz_convert(DISPLAY_TZ).date()==today:
                    state['today_losses']+=1
        streak=0
        for st in reversed(statuses):
            if st=='LOSS': streak+=1
            else: break
        state['loss_streak']=streak
        if state['today_losses']>=3:
            state.update(blocked=True,mult=0.0,reason='당일 손절 3회 kill-switch')
        elif streak>=2:
            state['mult']=0.50; state['reason']='최근 연속손절 2회 → 위험 50% 축소'
        elif streak==1:
            state['mult']=0.75; state['reason']='최근 손절 → 위험 25% 축소'
    except Exception:
        pass
    return state


def context_risk_multiplier_v500(ctx, side, tf=None, H=None):
    """Context cannot reverse Analog. It may veto or reduce risk."""
    reasons=[]; mult=1.0; veto=None
    spread=ctx.get('spread_bps',float('nan'))
    if np.isfinite(spread) and spread>V500_SPREAD_MAX_BPS:
        veto=f'스프레드 {spread:.2f}bp > {V500_SPREAD_MAX_BPS:.1f}bp'
        return 0.0,veto,reasons

    fr=ctx.get('funding_rate',float('nan'))
    # Funding matters only if the planned maximum hold can actually cross the next funding timestamp.
    crosses=True
    nft=ctx.get('next_funding_time',0)
    if tf in INTERVALS and H is not None and nft:
        now_ms=int(datetime.now(timezone.utc).timestamp()*1000)
        horizon_ms=int(INTERVALS[tf]*int(H)*60*1000)
        crosses = now_ms <= int(nft) <= now_ms+horizon_ms
    adverse = float(fr)*int(side) if (np.isfinite(fr) and crosses) else 0.0
    if adverse>V500_FUNDING_ADVERSE:
        veto=f'보유구간 내 방향에 불리한 funding {fr:+.4%}'
        return 0.0,veto,reasons
    if adverse>V500_FUNDING_THROTTLE:
        mult*=0.50; reasons.append('보유구간 내 불리한 funding → 위험 50%')

    oi=ctx.get('oi_change_1h',float('nan'))
    if np.isfinite(oi) and abs(oi)>V500_OI_SHOCK:
        mult*=0.70; reasons.append(f'OI 1h shock {oi:+.1%} → 위험 70%')

    tak=ctx.get('taker_buy_sell',float('nan'))
    if np.isfinite(tak):
        if side>0 and tak<V500_TAKER_OPPOSE:
            mult*=0.75; reasons.append(f'taker flow 반대({tak:.2f}) → 위험 75%')
        if side<0 and tak>1.0/V500_TAKER_OPPOSE:
            mult*=0.75; reasons.append(f'taker flow 반대({tak:.2f}) → 위험 75%')
    return float(mult),veto,reasons


def size_position_v500(seed,entry,sl,risk_frac,tf,H,rules):
    seed=float(seed); entry=float(entry); sl=float(sl); risk_frac=float(risk_frac)
    cost=total_cost(tf,H); denom=sl+cost
    budget=seed*risk_frac
    target=budget/max(denom,1e-12)
    min_notional=float(rules.get('min_notional',MIN_NOTIONAL))
    max_margin=seed*V500_MARGIN_CAP
    capacity=max_margin*V500_MAX_LEV
    target=min(target,capacity)
    if target<min_notional:
        return dict(executable=False,reason='안전한 위험예산으로 거래소 최소명목 충족 불가',risk_actual=0)
    lev=None
    for L in range(1,V500_MAX_LEV+1):
        if target/L<=max_margin:
            lev=L; break
    if lev is None:
        return dict(executable=False,reason='저레버리지 원칙 안에서 명목 구현 불가',risk_actual=0)
    step=max(float(rules.get('qty_step',0.001)),1e-12)
    min_qty=float(rules.get('min_qty',step))
    qty=math.floor((target/entry)/step)*step
    if qty<min_qty: qty=min_qty
    notional=qty*entry; margin=notional/lev
    actual=notional*denom/max(seed,1e-12)
    liq_dist=0.90/max(lev,1)
    if liq_dist < max(3.0*sl, sl+0.02):
        return dict(executable=False,reason='손절 대비 청산거리 버퍼 부족',risk_actual=actual)
    ok=(notional>=min_notional*0.999 and margin<=max_margin*1.0001 and actual<=V500_RISK_CAP*1.01)
    return dict(executable=bool(ok),reason='' if ok else '최소명목/리스크 제약 불일치',
                risk=budget,risk_frac=risk_frac,risk_actual=float(actual),margin=float(margin),
                lev=int(lev),notional=float(notional),qty=float(qty),liq_dist=float(liq_dist),cost=cost)


def build_plan_v500(ch,base_frame,tf_index,tf,K,H,seed,rules,topk=V500_TOPK,use_1m=True,
                    status=None,levels=None,rng=None):
    rng=rng or np.random.default_rng(V500_NULL_SEED)
    scales=[]
    for f in V500_SCALE_FACTORS:
        kk=max(30,int(round(K*f)))
        r=analyze_scale_v500(ch,base_frame,tf_index,tf,kk,H,rules,topk=topk,levels=levels,
                             status=status,use_1m=use_1m,do_null=(kk==K),rng=rng)
        scales.append(r)
    primary=next((r for r in scales if r['K']==K),scales[0])
    plan=dict(tf=tf,K=K,H=H,scales=scales,primary=primary,trade=False,seed=float(seed),model_id=V500_MODEL_ID)
    if 'winner' not in primary:
        plan['reason']=primary.get('reason','주 신호 없음'); return plan
    p=primary['winner']; nb=primary['nb']; runner=primary.get('runner_up')

    reasons=[]
    if nb.get('weak_analog'): reasons.append(f'Analog 중앙 형상 r={nb["median_shape"]:.3f} 부족')
    if nb.get('n_eff',0)<V500_MIN_NEFF: reasons.append(f'유효표본 N_eff={nb.get("n_eff",0):.1f} 부족')
    if p['ev_oof']<=0: reasons.append(f'OOF 순EV {p["ev_oof"]:+.3%} ≤ 0')
    if p['edge_lb']<=0: reasons.append(f'edge 하한 {p["edge_lb"]:+.3%} ≤ 0')
    if p['edge_prob']<V500_EDGE_PROB_MIN: reasons.append(f'P(edge>0) {p["edge_prob"]:.1%} 부족')
    if p['kelly_low']<=0: reasons.append('robust Kelly 하한 0')
    if p['move_median'] < total_cost(tf,H)*V500_MIN_MOVE_COST_MULT:
        reasons.append('Analog 미래 이동폭이 비용 대비 너무 작음')
    pg=primary.get('pval_global',float('nan'))
    if np.isfinite(pg) and pg>PVAL_MAX:
        reasons.append(f'다중스케일 보정 p={pg:.3f} > {PVAL_MAX}')

    # Both sides may look positive in choppy distributions. Refuse ambiguous edges.
    if runner is not None and runner.get('edge_lb',-1)>0:
        gap=float(p['edge_prob']-runner.get('edge_prob',0.0))
        if gap<V500_SIDE_GAP_MIN and abs(p['score']-runner.get('score',0.0))<0.20:
            reasons.append(f'LONG/SHORT 양면 edge 모호 (확률격차 {gap:.1%})')

    votes=[]
    for r in scales:
        w=r.get('winner')
        if w and w.get('edge_lb',-1)>0 and w.get('edge_prob',0)>=0.65:
            votes.append(int(w['side']))
    same=sum(v==p['side'] for v in votes)
    if same<2: reasons.append(f'multiscale 합의 부족 {votes}')

    if reasons:
        plan['reason']=' / '.join(reasons)+' → WAIT'; return plan

    # Context has veto/throttle power only after Analog+statistics pass.
    cmult,veto,creasons=context_risk_multiplier_v500(rules,p['side'],tf,H)
    if veto:
        plan['reason']=veto+' → WAIT'; plan['context_notes']=creasons; return plan

    jstate=journal_risk_state_v500(seed)
    if jstate['blocked']:
        plan['reason']=jstate['reason']+' → WAIT'; return plan

    conf=np.clip((p['edge_prob']-0.50)/0.40,0,1)
    sample_conf=np.clip(nb.get('n_eff',0)/24.0,0,1)
    stability_conf=np.clip(p.get('stability',0),0.25,1.0)
    base=min(V500_RISK_CAP,0.25*p['kelly_low'])
    risk=float(base*conf*sample_conf*stability_conf*cmult*jstate['mult'])
    if risk<V500_RISK_FLOOR:
        plan['reason']=f'최종 합리적 위험 {risk:.3%} < 실행 하한 {V500_RISK_FLOOR:.2%} → WAIT'; return plan

    entry=float(ch.close[-1])
    sz=size_position_v500(seed,entry,p['sl'],risk,tf,H,rules)
    if not sz.get('executable'):
        plan['reason']=sz.get('reason','사이징 실패')+' → WAIT'; return plan

    plan.update(trade=True,side=p['side'],entry=entry,tp=p['tp'],sl=p['sl'],rr=p['rr'],
                tp_px=p['tp_px'],sl_px=p['sl_px'],risk_frac=risk,sizing=sz,
                votes=votes,agree=True,context_notes=creasons,journal_state=jstate)
    # Flatten useful fields into primary for display/details.
    p['nb']=nb; p['pval_raw']=primary.get('pval_raw'); p['pval_global']=primary.get('pval_global')
    primary.update(p)
    return plan


def _append_v500_json(plan):
    rec=dict(time=datetime.now(timezone.utc).isoformat(),model_id=V500_MODEL_ID,
             trade=bool(plan.get('trade')),reason=plan.get('reason',''),
             side=plan.get('side'),entry=plan.get('entry'),tp_px=plan.get('tp_px'),sl_px=plan.get('sl_px'))
    p=plan.get('primary',{})
    nb=p.get('nb') or {}
    rec.update(edge_prob=p.get('edge_prob'),edge_lb=p.get('edge_lb'),ev_oof=p.get('ev_oof'),
               p_global=p.get('pval_global'),n_eff=nb.get('n_eff'),median_shape=nb.get('median_shape'))
    try:
        with open(V500_JOURNAL_JSONL,'a',encoding='utf-8') as f:
            f.write(json.dumps(_json_safe_plan(rec),ensure_ascii=False)+'\n')
    except Exception:
        pass


def oneclick_scan_v500(dm,seed,status=None):
    tf,K,H=ONECLICK_TF,ONECLICK_K,ONECLICK_H
    status=status or (lambda *a,**k:None)
    status('최신 1분봉 갱신...', 'blue')
    df=dm.get(tf,force_refresh=True)
    if df is None or df.empty:
        raise RuntimeError('데이터가 없습니다. 전체 히스토리를 먼저 구축하세요.')
    lag=float(dm.meta.get('lag_min',9999))
    if not np.isfinite(lag) or lag>MAX_STALE_MIN:
        return dict(blocked=True,reason=f'데이터 지연 {lag:.0f}분',tf=tf,K=K,H=H,model_id=V500_MODEL_ID),df,None,None

    try: journal_score(dm)
    except Exception: pass
    js=journal_risk_state_v500(seed)
    if js['blocked']:
        return dict(blocked=True,reason=js['reason'],tf=tf,K=K,H=H,model_id=V500_MODEL_ID),df,None,None

    status('거래소 규칙·선물 컨텍스트 확인...', 'blue')
    ctx=fetch_exchange_context_v500()
    if np.isfinite(ctx.get('spread_bps',float('nan'))) and ctx['spread_bps']>V500_SPREAD_MAX_BPS:
        return dict(blocked=True,reason=f'스프레드 {ctx["spread_bps"]:.2f}bp 과대',tf=tf,K=K,H=H,
                    exchange_context=ctx,model_id=V500_MODEL_ID),df,None,None

    status('Analog-first hostile audit...', 'blue')
    ch=Channels(df)
    levels=sr_levels(ch.high,ch.low,ch.close,df['volume'].values.astype(np.float64))
    plan=build_plan_v500(ch,dm.base,df.index,tf,K,H,float(seed),ctx,topk=V500_TOPK,
                         use_1m=ONECLICK_USE_1M,status=status,levels=levels)
    plan['exchange_context']=ctx
    plan['activity_context']=local_activity_context(df,ch)
    plan['model_id']=V500_MODEL_ID
    journal_append(plan,df.index)
    _append_v500_json(plan)
    return plan,df,ch,levels


def render_oneclick_card_v500(plan,seed,next_kst=None):
    now=_now_utc_aware().astimezone(_KST)
    nxt=next_kst.strftime('%Y-%m-%d %H:%M KST') if next_kst else '-'
    border='━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
    head=[border,'      PatternEdge V500 — ANALOG COUNCIL',border,
          f'모델       {V500_MODEL_ID}',f'현재시각   {now:%Y-%m-%d %H:%M:%S KST}',f'시장       {SYMBOL} PERP','']
    if plan is None:
        return '\n'.join(head+['판정       아직 분석 전','',f'다음 자동   {nxt}'])
    if plan.get('blocked'):
        return '\n'.join(head+['████████████  WAIT  ████████████','',f'사유       {plan.get("reason","안전조건 미충족")}',
                               '',f'다음 자동   {nxt}',border])
    p=plan.get('primary',{}); nb=p.get('nb') or {}; ctx=plan.get('exchange_context',{})
    if not plan.get('trade'):
        lines=head+['████████████  WAIT  ████████████','',f'사유       {plan.get("reason","조건 미충족")}']
        if np.isfinite(p.get('edge_prob',float('nan'))): lines.append(f'P(edge>0) {p["edge_prob"]:.1%}')
        if np.isfinite(p.get('edge_lb',float('nan'))): lines.append(f'Edge 하한  {p["edge_lb"]:+.3%}')
        if np.isfinite(p.get('pval_global',float('nan'))): lines.append(f'Global p   {p["pval_global"]:.4f}')
        if nb: lines.append(f'Analog     r50={nb.get("median_shape",0):.3f} · N_eff={nb.get("n_eff",0):.1f}')
        lines+=['',f'다음 자동   {nxt}',border]
        return '\n'.join(lines)

    sz=plan['sizing']; side='LONG' if plan['side']>0 else 'SHORT'
    loss=float(seed)*sz['risk_actual']; margin_pct=sz['margin']/max(float(seed),1e-12)
    lines=head+[f'████████████  {side:^5s}  ████████████','',
                f'진입       {plan["entry"]:,.1f} USDT',f'익절 TP    {plan["tp_px"]:,.1f} USDT',
                f'손절 SL    {plan["sl_px"]:,.1f} USDT',f'손익비     1 : {plan["rr"]:.2f}',
                f'최대보유   {INTERVALS[plan["tf"]]*plan["H"]/60:.1f}시간','',
                f'시드 사용  {margin_pct:.2%} ({sz["margin"]:,.2f} USDT)',f'레버리지   {int(sz["lev"])}x 격리',
                f'주문수량   {sz["qty"]:.6f} BTC',f'명목금액   {sz["notional"]:,.2f} USDT',
                f'최대손실   약 -{loss:,.2f} USDT (계좌 -{sz["risk_actual"]:.2%})','',
                f'Analog     r50={nb.get("median_shape",0):.3f} · N_eff={nb.get("n_eff",0):.1f}',
                f'OOF 순EV   {p.get("ev_oof",0):+.3%}',f'Edge 하한  {p.get("edge_lb",0):+.3%}',
                f'P(edge>0) {p.get("edge_prob",0):.1%}',f'Global p   {p.get("pval_global",float("nan")):.4f}',
                f'멀티스케일 {plan.get("votes",[])}']
    if np.isfinite(ctx.get('spread_bps',float('nan'))): lines.append(f'스프레드   {ctx["spread_bps"]:.2f} bp')
    if np.isfinite(ctx.get('funding_rate',float('nan'))): lines.append(f'펀딩       {ctx["funding_rate"]:+.4%}')
    if np.isfinite(ctx.get('oi_change_1h',float('nan'))): lines.append(f'OI 1h      {ctx["oi_change_1h"]:+.2%}')
    if np.isfinite(ctx.get('taker_buy_sell',float('nan'))): lines.append(f'Taker B/S  {ctx["taker_buy_sell"]:.2f}')
    for note in plan.get('context_notes',[]): lines.append(f'리스크     {note}')
    lines+=['',f'다음 자동   {nxt}',border,
            '※ Analog가 방향을 제안하고, 통계/시장상태/리스크는 거부권만 행사합니다.',
            '※ 00/50 임의 스냅은 생산모드에서 사용하지 않고 거래소 tick만 사용합니다.']
    return '\n'.join(lines)


# Preserve the old V400 GUI for forensic comparison.
main_v400 = main


def main():
    from tkinter import Tk, Button, Entry, Label, Frame, Checkbutton, IntVar, DISABLED, NORMAL, WORD, messagebox
    from tkinter.scrolledtext import ScrolledText

    class V500App:
        def __init__(self,root):
            self.root=root; self.dm=DataManager(log=self.set_status); self.running=False; self.last_auto_key=None
            self.plan=None; self.df=None; self.ch=None; self.levels=None
            root.title(f'PatternEdge {__version__} — {SYMBOL} ONE CLICK')
            root.geometry('860x820')
            root.protocol('WM_DELETE_WINDOW',self.close)

            top=Frame(root,padx=12,pady=10); top.pack(fill='x')
            Label(top,text='PatternEdge V500 — ANALOG COUNCIL',font=('Malgun Gothic',16,'bold')).grid(row=0,column=0,columnspan=5,sticky='w')
            Label(top,text='시드(USDT)').grid(row=1,column=0,sticky='e',pady=8)
            self.seed_e=Entry(top,width=12,font=('Consolas',12)); self.seed_e.grid(row=1,column=1,sticky='w'); self.seed_e.insert(0,'71')
            self.auto_var=IntVar(value=1); Checkbutton(top,text='09:18 ET 자동 세션',variable=self.auto_var).grid(row=1,column=2,sticky='w',padx=10)
            self.scan_btn=Button(top,text='지금 분석',command=self.run_now,bg='#0b6e4f',fg='white',font=('Malgun Gothic',12,'bold'),height=2)
            self.scan_btn.grid(row=2,column=0,columnspan=3,sticky='ew',pady=6)
            Button(top,text='전체 데이터 구축/복구',command=self.build_data).grid(row=2,column=3,padx=4)
            Button(top,text='상세',command=self.show_detail).grid(row=2,column=4,padx=4)
            self.next_label=Label(top,text='',font=('Malgun Gothic',9)); self.next_label.grid(row=3,column=0,columnspan=5,sticky='w')
            self.status=Label(top,text='대기 중',anchor='w'); self.status.grid(row=4,column=0,columnspan=5,sticky='w')
            for c in range(5): top.grid_columnconfigure(c,weight=1)

            self.txt=ScrolledText(root,height=31,font=('Consolas',11),wrap=WORD,state=DISABLED)
            self.txt.pack(fill='both',expand=True,padx=10,pady=(0,10))
            threading.Thread(target=self.boot,daemon=True).start()
            self.root.after(AUTO_POLL_MS,self.refresh_clock)

        def seed(self):
            v=float(self.seed_e.get())
            if v<=0: raise ValueError('시드는 0보다 커야 합니다.')
            return v
        def set_status(self,text,color='black'):
            try:self.root.after(0,lambda:self.status.config(text=text,fg=color))
            except Exception:pass
        def show(self,text):
            def f():
                self.txt.config(state=NORMAL); self.txt.delete('1.0','end'); self.txt.insert('end',text); self.txt.config(state=DISABLED)
            self.root.after(0,f)
        def next_session(self): return next_main_session()
        def boot(self):
            try:
                self.dm.ensure(); self.set_status(self.dm.data_banner('1m'),'green')
            except Exception as e:self.set_status(f'데이터 준비 필요: {e}','red')
            try:
                _,kst=self.next_session(); self.show(render_oneclick_card_v500(None,self.seed(),kst))
            except Exception:pass
        def refresh_clock(self):
            try:
                et,kst=self.next_session(); self.next_label.config(text=f'다음 자동: {kst:%Y-%m-%d %H:%M KST} ({session_mode_text(et)}) · model {V500_MODEL_ID}')
                key=_session_key_if_due()
                if self.auto_var.get() and key and key!=self.last_auto_key and not self.running:
                    self.last_auto_key=key; self.run_now(auto=True)
            except Exception as e:self.next_label.config(text=f'세션 시계 오류: {e}')
            self.root.after(AUTO_POLL_MS,self.refresh_clock)
        def run_now(self,auto=False):
            if self.running:return
            try:s=self.seed()
            except Exception as e:messagebox.showerror('입력 오류',str(e));return
            self.running=True; self.scan_btn.config(state=DISABLED)
            self.set_status(('자동' if auto else '수동')+' hostile audit 시작...','blue')
            threading.Thread(target=self._worker,args=(s,),daemon=True).start()
        def _worker(self,s):
            try:
                plan,df,ch,levels=oneclick_scan_v500(self.dm,s,self.set_status)
                self.plan,self.df,self.ch,self.levels=plan,df,ch,levels
                _,kst=self.next_session(); self.show(render_oneclick_card_v500(plan,s,kst))
                self.set_status('완료 — 주문표 생성' if plan.get('trade') else '완료 — WAIT','green' if plan.get('trade') else '#b26a00')
            except Exception as e:
                import traceback; traceback.print_exc(); self.set_status(f'분석 실패: {type(e).__name__}: {e}','red')
            finally:
                self.running=False; self.root.after(0,lambda:self.scan_btn.config(state=NORMAL))
        def show_detail(self):
            if not self.plan: messagebox.showinfo('안내','먼저 분석하세요.'); return
            try:
                _,kst=self.next_session(); txt=render_oneclick_card_v500(self.plan,self.seed(),kst)
                txt+='\n\n[DATA]\n'+self.dm.data_banner(ONECLICK_TF)
                txt+='\n\n[RAW PLAN]\n'+json.dumps(_json_safe_plan(self.plan),ensure_ascii=False,indent=2)
                w=__import__('tkinter').Toplevel(self.root); w.title('V500 hostile audit detail'); w.geometry('1050x900')
                box=ScrolledText(w,font=('Consolas',10),wrap=WORD); box.pack(fill='both',expand=True); box.insert('1.0',txt); box.config(state=DISABLED)
            except Exception as e:messagebox.showerror('상세 오류',str(e))
        def build_data(self):
            if self.running:return
            self.running=True; threading.Thread(target=self._build,daemon=True).start()
        def _build(self):
            try:
                self.set_status('전체 히스토리 구축/복구...','blue')
                self.dm.build_full_history(progress=lambda i,t,m:self.set_status(f'[{i}/{t}] {m}','blue'))
                self.dm.ensure(force_refresh=True); self.set_status('데이터 구축 완료','green')
            except Exception as e:self.set_status(f'구축 실패: {e}','red')
            finally:self.running=False
        def close(self):
            try:self.root.quit();self.root.destroy()
            except Exception:pass

    root=Tk(); V500App(root); root.mainloop()



# =============================================================================
# [18] V600 GROWTH MACHINE — 24/7 opportunity harvesting + geometric growth
# =============================================================================
# Council verdict:
#   * Analog memory remains the alpha hypothesis and proposes direction/payoff.
#   * 24/7 monitoring is desirable; 24/7 forced trading is not.
#   * The production objective is not maximum win rate or minimum p-value.
#   * Objective: maximize posterior/OOF expected log wealth growth subject to
#       - hard per-trade risk cap
#       - drawdown probability constraint
#       - catastrophic capital-floor probability constraint
#       - execution/context vetoes
#       - prospective live/shadow decay monitoring
#   * Multiple horizons compete for scarce risk capital. Only the best current
#     growth opportunity becomes the one-click ticket.
#   * This file does NOT place live exchange orders. It autonomously scans and
#     shadow-scores signals. Live execution should only be connected after
#     prospective validation with the exact frozen model fingerprint.

main_v500 = main

V600_MODELS = {
    # Crypto never closes. Each model is evaluated only when its own candle closes.
    # K = remembered context, H = maximum forward holding horizon.
    '5m':  dict(K=288, H=24, topk=36, label='SCALP-5M'),   # 24h memory -> 2h max hold
    '15m': dict(K=192, H=16, topk=36, label='CORE-15M'),   # 48h memory -> 4h max hold
    '1h':  dict(K=168, H=12, topk=32, label='SWING-1H'),   # 7d memory -> 12h max hold
}
V600_SCALE_FACTORS       = (0.5, 1.0, 2.0)
V600_MIN_MED_SHAPE       = 0.78
V600_MIN_NEFF            = 10.0
V600_EDGE_PROB_MIN       = 0.70
V600_GLOBAL_P_MAX        = 0.10
V600_SIDE_GAP_MIN        = 0.04
V600_RISK_CAP            = 0.0100      # hard account-risk ceiling per trade
V600_RISK_FLOOR          = 0.0005      # smaller than this is economically irrelevant
V600_MARGIN_CAP          = 0.30
V600_MAX_LEV             = 4
V600_GROWTH_BOOT         = 700
V600_GROWTH_Q            = 0.10
V600_GROWTH_PROB_MIN     = 0.80
V600_MC_PATHS            = 500
V600_MC_TRADES           = 250
V600_MAX_DD              = 0.25        # risk policy, not prediction
V600_MAX_DD_PROB         = 0.05
V600_CAPITAL_FLOOR       = 0.40        # severe impairment / practical ruin proxy
V600_FLOOR_PROB_MAX      = 0.005
V600_NULL_N              = 160
V600_AUTO_POLL_MS        = 15_000
V600_COOLDOWN_MINUTES    = 5
V600_STATE_PATH          = os.path.join(BASE_DIR, f'{SYMBOL}_v600_state.json')
V600_JOURNAL_JSONL       = os.path.join(BASE_DIR, f'{SYMBOL}_v600_decisions.jsonl')
V600_NULL_SEED           = 60020260919


def _v600_model_fingerprint():
    import hashlib
    cfg = {
        'models': V600_MODELS,
        'analog_weights': V500_ANALOG_WEIGHTS,
        'scales': V600_SCALE_FACTORS,
        'shape_min': V600_MIN_MED_SHAPE,
        'neff_min': V600_MIN_NEFF,
        'edge_prob_min': V600_EDGE_PROB_MIN,
        'global_p_max': V600_GLOBAL_P_MAX,
        'risk_cap': V600_RISK_CAP,
        'margin_cap': V600_MARGIN_CAP,
        'max_lev': V600_MAX_LEV,
        'growth_boot': V600_GROWTH_BOOT,
        'growth_q': V600_GROWTH_Q,
        'growth_prob_min': V600_GROWTH_PROB_MIN,
        'max_dd': V600_MAX_DD,
        'max_dd_prob': V600_MAX_DD_PROB,
        'capital_floor': V600_CAPITAL_FLOOR,
        'floor_prob_max': V600_FLOOR_PROB_MAX,
    }
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]


V600_MODEL_ID = _v600_model_fingerprint()

# =============================================================================
# V610 MISSED SIGNAL GUARD — persistent actionable-signal ledger
# =============================================================================
V600_LEGACY_MODEL_ID = V600_MODEL_ID
V600_LEGACY_STATE_PATH = os.path.join(BASE_DIR, f'{SYMBOL}_v600_state.json')
V600_LEGACY_JOURNAL_JSONL = os.path.join(BASE_DIR, f'{SYMBOL}_v600_decisions.jsonl')
V610_STATE_PATH = os.path.join(BASE_DIR, f'{SYMBOL}_v610_state.json')
V610_DECISION_JSONL = os.path.join(BASE_DIR, f'{SYMBOL}_v610_decisions.jsonl')
V610_SIGNAL_JSONL = os.path.join(BASE_DIR, f'{SYMBOL}_v610_signals.jsonl')
V610_MAX_SIGNALS = 500
V610_MODEL_ID = __import__('hashlib').sha256((V600_LEGACY_MODEL_ID + '|MISSED-SIGNAL-GUARD-v1').encode()).hexdigest()[:12]
# Downstream V600 engine functions intentionally reuse the same names, but all new
# decisions/states carry the V610 fingerprint.
V600_MODEL_ID = V610_MODEL_ID


def _signal_event_v610(event, signal, extra=None):
    rec = dict(event=str(event), event_time=datetime.now(timezone.utc).isoformat(),
               model_id=V610_MODEL_ID, signal_id=(signal or {}).get('signal_id'))
    if signal:
        for k in ('detected_at','tf','side','entry','tp_px','sl_px','status','shadow_state'):
            rec[k] = signal.get(k)
        # Full immutable snapshot makes the JSONL a forensic ledger even after the
        # in-memory/state rolling window eventually trims old signals.
        rec['snapshot'] = _json_safe_plan(signal)
    if extra:
        rec.update(_json_safe_plan(extra))
    try:
        os.makedirs(os.path.dirname(V610_SIGNAL_JSONL), exist_ok=True)
        with open(V610_SIGNAL_JSONL, 'a', encoding='utf-8') as f:
            f.write(json.dumps(_json_safe_plan(rec), ensure_ascii=False) + '\n')
    except Exception:
        pass


def _import_legacy_signals_v610(state):
    """Best-effort import of V600 decisions so an upgrade does not erase old opportunities."""
    if state.get('legacy_imported'):
        return state
    seen={str(x.get('legacy_key','')) for x in state.get('signals',[]) if x.get('legacy_key')}
    try:
        if os.path.exists(V600_LEGACY_JOURNAL_JSONL):
            with open(V600_LEGACY_JOURNAL_JSONL,'r',encoding='utf-8') as f:
                for line in f:
                    try: rec=json.loads(line)
                    except Exception: continue
                    if not rec.get('trade'): continue
                    key=f"{rec.get('time')}|{rec.get('tf')}|{rec.get('side')}"
                    if key in seen: continue
                    sig=dict(signal_id='LEGACY-'+__import__('hashlib').sha1(key.encode()).hexdigest()[:12],
                             legacy_key=key,legacy=True,detected_at=rec.get('time'),tf=rec.get('tf'),
                             model_label='V600 legacy',side=rec.get('side'),entry=None,tp_px=None,sl_px=None,
                             status='LEGACY',acknowledged=True,dismissed=False,shadow_state='UNKNOWN',
                             growth_score=rec.get('growth_score'),growth_prob=rec.get('growth_prob'),
                             growth_median=rec.get('growth_median'),growth_lb=rec.get('growth_lb'),
                             growth_per_hour=rec.get('growth_per_hour'),risk_frac=rec.get('risk_frac'),
                             edge_prob=rec.get('edge_prob'),edge_lb=rec.get('edge_lb'),ev_oof=rec.get('ev_oof'),
                             p_global=rec.get('p_global'),n_eff=rec.get('n_eff'),median_shape=rec.get('median_shape'),
                             note='V600에서 감지된 과거 신호. 당시 V600 journal은 TP/SL 전체 주문표를 저장하지 않아 일부 필드는 복구 불가.')
                    state.setdefault('signals',[]).append(sig); seen.add(key)
    except Exception:
        pass
    state['signals']=state.get('signals',[])[-V610_MAX_SIGNALS:]
    state['legacy_imported']=True
    return state


def _load_v600_state(seed=None):
    d = dict(model_id=V610_MODEL_ID, active=None, closed=[], signals=[],
             paper_equity=float(seed or 0.0), last_scan={},
             created=datetime.now(timezone.utc).isoformat(), legacy_imported=False)
    loaded=False
    try:
        if os.path.exists(V610_STATE_PATH):
            with open(V610_STATE_PATH, 'r', encoding='utf-8') as f:
                old=json.load(f)
            if isinstance(old,dict): d.update(old); loaded=True
    except Exception:
        pass
    # First V610 boot: carry prospective state forward from V600 when available.
    if not loaded:
        try:
            if os.path.exists(V600_LEGACY_STATE_PATH):
                with open(V600_LEGACY_STATE_PATH,'r',encoding='utf-8') as f:
                    old=json.load(f)
                if isinstance(old,dict):
                    for k in ('active','closed','paper_equity','last_scan','created'):
                        if k in old: d[k]=old[k]
        except Exception:
            pass
    if seed is not None and (not np.isfinite(float(d.get('paper_equity',0))) or float(d.get('paper_equity',0))<=0):
        d['paper_equity']=float(seed)
    d['model_id']=V610_MODEL_ID
    d.setdefault('closed',[]); d.setdefault('last_scan',{}); d.setdefault('signals',[])
    _import_legacy_signals_v610(d)
    return d


def _save_v600_state(state):
    try:
        os.makedirs(os.path.dirname(V610_STATE_PATH), exist_ok=True)
        tmp=V610_STATE_PATH+'.tmp'
        with open(tmp,'w',encoding='utf-8') as f:
            json.dump(_json_safe_plan(state),f,ensure_ascii=False,indent=2)
        os.replace(tmp,V610_STATE_PATH)
    except Exception:
        pass


def _append_v600_decision(plan):
    rec=dict(time=datetime.now(timezone.utc).isoformat(),model_id=V610_MODEL_ID,
             trade=bool(plan.get('trade')),blocked=bool(plan.get('blocked')),
             reason=plan.get('reason',''),tf=plan.get('tf'),side=plan.get('side'),
             growth_score=plan.get('growth_score'),risk_frac=plan.get('risk_frac'))
    p=plan.get('primary') or {}; nb=p.get('nb') or {}
    rec.update(edge_prob=p.get('edge_prob'),edge_lb=p.get('edge_lb'),ev_oof=p.get('ev_oof'),
               p_global=p.get('pval_global'),n_eff=nb.get('n_eff'),median_shape=nb.get('median_shape'),
               growth_prob=plan.get('growth_prob'),growth_median=plan.get('growth_median'),
               growth_lb=plan.get('growth_lb'),growth_per_hour=plan.get('growth_per_hour'),
               mdd_prob=plan.get('mdd_prob'),floor_prob=plan.get('floor_prob'))
    try:
        with open(V610_DECISION_JSONL,'a',encoding='utf-8') as f:
            f.write(json.dumps(_json_safe_plan(rec),ensure_ascii=False)+'\n')
    except Exception:
        pass


def _signal_snapshot_v610(plan, dm, seed):
    now=datetime.now(timezone.utc)
    p=plan.get('primary') or {}; nb=p.get('nb') or {}; sz=plan.get('sizing') or {}
    sid=f"{now:%Y%m%dT%H%M%SZ}-{str(plan.get('tf','NA')).upper()}-{'L' if int(plan.get('side',1))>0 else 'S'}"
    visual=dict(query_start=None, query_end=None, K=int(plan.get('K') or 0), H=int(plan.get('H') or 0), analogs=[])
    try:
        tf=plan.get('tf')
        idx=dm.get(tf).index
        end=int(nb.get('end') or len(idx))
        K=int(plan.get('K') or nb.get('K') or 0)
        H=int(plan.get('H') or nb.get('H') or 0)
        if len(idx) and K>0 and end>=K:
            visual['query_start']=pd.Timestamp(idx[end-K]).isoformat()
            visual['query_end']=pd.Timestamp(idx[end-1]).isoformat()
        corr_shape=list(nb.get('corr_shape') or [])
        corr_ret=list(nb.get('corr_ret') or [])
        combo=list(nb.get('combo') or [])
        era=list(nb.get('era') or [])
        for rank,s in enumerate(list(nb.get('starts') or [])[:V610_CHART_ANALOGS], start=1):
            s=int(s)
            a=dict(rank=rank,start=int(s),corr_shape=float(corr_shape[rank-1]) if rank-1 < len(corr_shape) else None,
                   corr_ret=float(corr_ret[rank-1]) if rank-1 < len(corr_ret) else None,
                   combo=float(combo[rank-1]) if rank-1 < len(combo) else None,
                   era=int(era[rank-1]) if rank-1 < len(era) else None)
            if len(idx) and s >= 0 and s + K - 1 < len(idx):
                a['start_ts']=pd.Timestamp(idx[s]).isoformat()
                a['end_ts']=pd.Timestamp(idx[s+K-1]).isoformat()
                fend=min(s+K+max(H,0)-1, len(idx)-1)
                a['future_end_ts']=pd.Timestamp(idx[fend]).isoformat()
            visual['analogs'].append(a)
    except Exception:
        pass
    return dict(signal_id=sid,model_id=V610_MODEL_ID,detected_at=now.isoformat(),
                tf=plan.get('tf'),model_label=plan.get('model_label'),side=int(plan.get('side',0)),
                entry=float(plan.get('entry',0)),tp_px=float(plan.get('tp_px',0)),sl_px=float(plan.get('sl_px',0)),
                tp=float(plan.get('tp',0)),sl=float(plan.get('sl',0)),rr=float(plan.get('rr',0)),
                max_hold_min=int(INTERVALS.get(plan.get('tf'),1)*int(plan.get('H',0))),
                expected_hold_hours=float(plan.get('expected_hold_hours',0)),
                risk_frac=float(plan.get('risk_frac',0)),risk_actual=float(sz.get('risk_actual',0)),
                margin=float(sz.get('margin',0)),notional=float(sz.get('notional',0)),qty=float(sz.get('qty',0)),
                lev=int(sz.get('lev',0) or 0),seed=float(seed),growth_score=plan.get('growth_score'),
                growth_prob=plan.get('growth_prob'),growth_median=plan.get('growth_median'),
                growth_lb=plan.get('growth_lb'),growth_per_hour=plan.get('growth_per_hour'),
                mdd_prob=plan.get('mdd_prob'),floor_prob=plan.get('floor_prob'),
                edge_prob=p.get('edge_prob'),edge_lb=p.get('edge_lb'),ev_oof=p.get('ev_oof'),
                p_global=p.get('pval_global'),n_eff=nb.get('n_eff'),median_shape=nb.get('median_shape'),
                votes=plan.get('votes',[]),status='UNSEEN',acknowledged=False,dismissed=False,
                shadow_state='OPEN',shadow_result=None,last_recheck=None,legacy=False,visual=visual)


def _register_signal_v610(plan, dm, seed, state):
    sig=_signal_snapshot_v610(plan,dm,seed)
    state.setdefault('signals',[]).append(sig)
    state['signals']=state['signals'][-V610_MAX_SIGNALS:]
    state['last_actionable_signal_id']=sig['signal_id']
    _signal_event_v610('DETECTED',sig)
    return sig


def _find_signal_v610(state, signal_id=None):
    sigs=state.get('signals') or []
    if signal_id:
        for s in reversed(sigs):
            if s.get('signal_id')==signal_id: return s
        return None
    # Prefer newest non-dismissed signal. It remains visible after acknowledgement and after shadow close.
    for s in reversed(sigs):
        if not s.get('dismissed'): return s
    return sigs[-1] if sigs else None


def _mark_signal_seen_v610(state, signal_id=None):
    s=_find_signal_v610(state,signal_id)
    if not s: return None
    s['acknowledged']=True
    if s.get('status')=='UNSEEN': s['status']='SEEN'
    s['seen_at']=datetime.now(timezone.utc).isoformat()
    _signal_event_v610('SEEN',s); _save_v600_state(state)
    return s


def _dismiss_signal_v610(state, signal_id=None):
    s=_find_signal_v610(state,signal_id)
    if not s: return None
    s['dismissed']=True; s['status']='DISMISSED'; s['dismissed_at']=datetime.now(timezone.utc).isoformat()
    _signal_event_v610('DISMISSED',s); _save_v600_state(state)
    return s


def _fmt_signal_time_v610(x):
    try:
        t=pd.Timestamp(x)
        if t.tzinfo is None: t=t.tz_localize('UTC')
        return t.tz_convert('Asia/Seoul').strftime('%Y-%m-%d %H:%M:%S KST')
    except Exception:
        return str(x or '-')


def render_signal_banner_v610(state):
    s=_find_signal_v610(state)
    if not s:
        return ['[ACTIONABLE SIGNAL LEDGER] 아직 저장된 V610 신호 없음','']
    side='LONG' if int(s.get('side') or 0)>0 else ('SHORT' if int(s.get('side') or 0)<0 else '-')
    stat=s.get('status','-'); shadow=s.get('shadow_state','-')
    lines=['━━━━━━━━━━━━━━  LAST ACTIONABLE SIGNAL — WAIT가 덮지 않음  ━━━━━━━━━━━━━━',
           f"신호 ID     {s.get('signal_id','-')}",f"발견시각    {_fmt_signal_time_v610(s.get('detected_at'))}",
           f"상태        {stat} · shadow={shadow}",f"판정        {side} · {s.get('model_label') or s.get('tf')}"]
    if s.get('entry') is not None:
        lines += [f"당시 진입    {float(s.get('entry',0)):,.1f}",f"당시 TP      {float(s.get('tp_px',0)):,.1f}",
                  f"당시 SL      {float(s.get('sl_px',0)):,.1f}",f"당시 위험    {float(s.get('risk_actual') or 0):.3%} · {int(s.get('lev') or 0)}x · {float(s.get('qty') or 0):.6f} BTC"]
    if s.get('shadow_result'):
        r=s['shadow_result']
        lines += [f"사후결과    {r.get('reason')} · {float(r.get('r_mult',0)):+.2f}R · PnL {float(r.get('pnl_usdt',0)):+.2f} USDT",
                  '            ※ 네가 못 봤더라도 당시 시스템이 냈던 기회와 결과는 여기 남습니다.']
    elif s.get('legacy'):
        lines.append('            ※ V600 legacy 기록: 당시 전체 TP/SL 주문표는 원 journal 구조상 복구 불가.')
    if s.get('last_recheck'):
        lr=s['last_recheck']; lines.append(f"최근 재검증  {lr.get('status')} · {_fmt_signal_time_v610(lr.get('time'))} · {lr.get('reason','')}")
    lines += ['버튼        [최근 신호 재검증] = 지금 가격에서 새로 들어가도 되는지 전체 audit 재실행',
              '            [패턴 차트] = 당시 현재 패턴 vs top analog 그림/미래경로를 육안 검증',
              '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━','']
    return lines


def _signal_history_text_v610(state, limit=100):
    sigs=(state.get('signals') or [])[-int(limit):]
    lines=['PatternEdge V610 — ACTIONABLE SIGNAL LEDGER',f'저장 위치: {V610_SIGNAL_JSONL}','']
    if not sigs: return '\n'.join(lines+['기록 없음'])
    for s in reversed(sigs):
        side='LONG' if int(s.get('side') or 0)>0 else ('SHORT' if int(s.get('side') or 0)<0 else '-')
        lines += [f"[{s.get('signal_id')}] {_fmt_signal_time_v610(s.get('detected_at'))}",
                  f"  {side} {s.get('tf')} · 상태={s.get('status')} · shadow={s.get('shadow_state')}"]
        if s.get('entry') is not None:
            lines.append(f"  ENTRY {float(s.get('entry',0)):,.1f} | TP {float(s.get('tp_px',0)):,.1f} | SL {float(s.get('sl_px',0)):,.1f} | risk {float(s.get('risk_actual') or 0):.3%}")
        if s.get('shadow_result'):
            r=s['shadow_result']; lines.append(f"  RESULT {r.get('reason')} {float(r.get('r_mult',0)):+.2f}R / {float(r.get('pnl_usdt',0)):+.2f} USDT")
        if s.get('last_recheck'):
            lr=s['last_recheck']; lines.append(f"  RECHECK {lr.get('status')} — {lr.get('reason','')}")
        lines.append('')
    return '\n'.join(lines)



def _signal_pattern_df_v610(dm, sig):
    tf = sig.get('tf')
    visual = sig.get('visual') or {}
    K = int(visual.get('K') or 0)
    H = int(visual.get('H') or 0)
    if not tf or K <= 0:
        raise ValueError('시각화용 패턴 메타데이터가 없습니다.')
    df = dm.get(tf, force_refresh=False)
    if df is None or df.empty:
        raise ValueError('차트 데이터를 불러올 수 없습니다.')
    def _clip_slice(s, e=None):
        s = pd.Timestamp(s)
        if s.tzinfo is not None:
            s = s.tz_convert('UTC').tz_localize(None)
        e = pd.Timestamp(e) if e is not None else None
        if e is not None and e.tzinfo is not None:
            e = e.tz_convert('UTC').tz_localize(None)
        out = df.loc[s:e] if e is not None else df.loc[s:]
        return out.copy()
    q = _clip_slice(visual.get('query_start'), visual.get('query_end'))
    analogs = []
    for a in list(visual.get('analogs') or [])[:V610_CHART_ANALOGS]:
        try:
            seg = _clip_slice(a.get('start_ts'), a.get('end_ts'))
            fut = _clip_slice(a.get('end_ts'), a.get('future_end_ts'))
            analogs.append((a, seg, fut))
        except Exception:
            continue
    return df, q, analogs, K, H


def _norm_close_series(df):
    if df is None or df.empty:
        return np.array([])
    c = pd.to_numeric(df['close'], errors='coerce').astype('float64').values
    c = c[np.isfinite(c)]
    if len(c) == 0:
        return np.array([])
    base = c[0] if abs(c[0]) > 1e-12 else 1.0
    return c / base - 1.0


def _build_pattern_figure_v610(dm, sig):
    if not MPL_OK:
        raise RuntimeError('matplotlib 사용 불가')
    full_df, q, analogs, K, H = _signal_pattern_df_v610(dm, sig)
    fig = Figure(figsize=(11.5, 8.5), dpi=110)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.15, 1.05, 0.9], hspace=0.36)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[2, 0])

    qn = _norm_close_series(q)
    xq = np.arange(len(qn))
    ax1.plot(xq, qn, linewidth=2.6, label='Current pattern')
    colors = ['tab:orange', 'tab:green', 'tab:red', 'tab:purple']
    for i, (meta, seg, fut) in enumerate(analogs):
        yn = _norm_close_series(seg)
        ax1.plot(np.arange(len(yn)), yn, linewidth=1.8, alpha=0.95,
                 label=f"A{i+1} r={float(meta.get('corr_shape') or 0):.3f}  {str(meta.get('start_ts',''))[:10]}")
    ax1.set_title(f"Current vs top analogs · {sig.get('tf')} · K={K}")
    ax1.set_ylabel('Normalized return from segment start')
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc='best', fontsize=8)

    # future trajectories from analog end
    side = int(sig.get('side') or 0)
    if analogs:
        fut_mat = []
        for i, (meta, seg, fut) in enumerate(analogs):
            yc = pd.to_numeric(fut['close'], errors='coerce').astype('float64').values
            if len(yc) < 2:
                continue
            base = yc[0] if abs(yc[0]) > 1e-12 else 1.0
            ret = yc / base - 1.0
            ax2.plot(np.arange(len(ret)), ret, linewidth=1.6, alpha=0.85,
                     label=f"A{i+1} future")
            fut_mat.append(ret)
        if fut_mat:
            m = min(len(v) for v in fut_mat)
            if m > 1:
                arr = np.vstack([v[:m] for v in fut_mat])
                med = np.median(arr, axis=0)
                ax2.plot(np.arange(m), med, linewidth=2.8, linestyle='--', label='Median future')
                ax2.axhline(float(sig.get('tp') or 0) * side, linestyle=':', linewidth=1.1)
                ax2.axhline(-float(sig.get('sl') or 0) * side, linestyle=':', linewidth=1.1)
    ax2.set_title('What the matched analogs did next')
    ax2.set_ylabel('Forward return from analog end')
    ax2.grid(True, alpha=0.25)
    ax2.legend(loc='best', fontsize=8)

    # price context panel
    q_end = pd.Timestamp((sig.get('visual') or {}).get('query_end')) if (sig.get('visual') or {}).get('query_end') else None
    if q_end is not None:
        if q_end.tzinfo is not None:
            q_end = q_end.tz_convert('UTC').tz_localize(None)
        mins = INTERVALS.get(sig.get('tf'), 1)
        lookback = max(K * 2, 80)
        idx = full_df.index.get_indexer([q_end], method='nearest')[0]
        s0 = max(0, idx - lookback + 1)
        s1 = min(len(full_df), idx + max(H, 8) + 1)
        ctx = full_df.iloc[s0:s1]
    else:
        ctx = full_df.tail(max(K * 2, 80))
    c = pd.to_numeric(ctx['close'], errors='coerce').astype('float64')
    ax3.plot(ctx.index, c.values, linewidth=1.8)
    if q_end is not None:
        q_start = pd.Timestamp((sig.get('visual') or {}).get('query_start'))
        if q_start.tzinfo is not None:
            q_start = q_start.tz_convert('UTC').tz_localize(None)
        ax3.axvspan(q_start, q_end, alpha=0.18)
        ax3.axhline(float(sig.get('entry') or 0), linestyle='--', linewidth=1.0)
        ax3.axhline(float(sig.get('tp_px') or 0), linestyle=':', linewidth=1.0)
        ax3.axhline(float(sig.get('sl_px') or 0), linestyle=':', linewidth=1.0)
    ax3.set_title('Current market context around the detected pattern')
    ax3.set_ylabel('Price')
    ax3.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    return fig


def show_pattern_window_v610(root, dm, state, signal_id=None):
    import tkinter as tk
    from tkinter import messagebox
    sig = _find_signal_v610(state, signal_id)
    if not sig:
        messagebox.showinfo('안내', '표시할 신호가 없습니다.')
        return
    if not MPL_OK:
        messagebox.showerror('오류', 'matplotlib가 없어 패턴 차트를 띄울 수 없습니다.')
        return
    try:
        dm.ensure(force_refresh=False)
        fig = _build_pattern_figure_v610(dm, sig)
    except Exception as e:
        messagebox.showerror('패턴 차트 오류', str(e))
        return
    win = tk.Toplevel(root)
    win.title(f"PatternEdge V610 — PATTERN VISUAL AUDIT — {sig.get('signal_id','')}")
    win.geometry('1180x930')
    header = tk.Label(win, anchor='w', justify='left', padx=10, pady=8,
                      text=(f"신호 {sig.get('signal_id')}\n"
                            f"{('LONG' if int(sig.get('side') or 0)>0 else 'SHORT')} · {sig.get('tf')} · "
                            f"ENTRY {float(sig.get('entry') or 0):,.1f} / TP {float(sig.get('tp_px') or 0):,.1f} / "
                            f"SL {float(sig.get('sl_px') or 0):,.1f}\n"
                            f"Analog r50={float(sig.get('median_shape') or 0):.3f} · N_eff={float(sig.get('n_eff') or 0):.1f} · "
                            f"P(edge>0)={float(sig.get('edge_prob') or 0):.1%}"))
    header.pack(fill='x')
    canvas = FigureCanvasTkAgg(fig, master=win)
    canvas.draw()
    canvas.get_tk_widget().pack(fill='both', expand=True)
    footer = tk.Label(win, anchor='w', justify='left', padx=10, pady=6,
                      text='상단: 현재 패턴과 top analog 비교 · 중단: analog 이후 실제 미래 경로 · 하단: 현재 시장 문맥.\n'
                           '육안 검증용이며, 최종 판단은 여전히 통계/성장성 audit를 우선합니다.')
    footer.pack(fill='x')


def recheck_latest_signal_v610(dm, seed, state, signal_id=None, status=None):
    """Full current-market re-audit. Never tells the user to chase an old entry blindly."""
    status=status or (lambda *a,**k:None)
    sig=_find_signal_v610(state,signal_id)
    if not sig:
        return dict(valid=False,status='NO_SIGNAL',reason='재검증할 과거 신호가 없습니다.'),state
    tf=sig.get('tf'); old_side=int(sig.get('side') or 0)
    if tf not in V600_MODELS or old_side==0:
        out=dict(valid=False,status='UNAVAILABLE',reason='legacy/불완전 신호라 동일 모델 재검증 불가',signal=sig)
    else:
        status('놓친 신호 현재가 재검증: 최신 데이터 갱신...','blue')
        dm.ensure(force_refresh=True)
        ctx=fetch_exchange_context_v500()
        plan=scan_model_v600(dm,float(seed),tf,ctx,state,status=status,do_null=True)
        cur=float(dm.get(tf).iloc[-1]['close'])
        if plan.get('trade') and int(plan.get('side',0))==old_side:
            old=float(sig.get('entry') or cur); drift=old_side*(cur/old-1.0) if old>0 else 0.0
            status_name='REENTRY_VALID' if sig.get('shadow_state')=='CLOSED' else 'LATE_VALID'
            out=dict(valid=True,status=status_name,reason='현재 가격에서도 동일 방향 robust growth audit 통과',
                     signal=sig,plan=plan,current_price=cur,price_drift=drift)
        else:
            if plan.get('trade') and int(plan.get('side',0))==-old_side:
                why='현재는 반대 방향 신호가 우세 — 과거 신호 추격 금지'
            else:
                why='현재 가격에서는 기존 방향의 성장/통계 조건 미충족 — 추격 금지'
                if plan.get('reason'): why += f" ({plan.get('reason')})"
            out=dict(valid=False,status='EXPIRED',reason=why,signal=sig,plan=plan,current_price=cur)
    sig['last_recheck']=dict(time=datetime.now(timezone.utc).isoformat(),status=out['status'],reason=out['reason'],
                             current_price=out.get('current_price'),price_drift=out.get('price_drift'))
    if out['status'] in ('LATE_VALID','REENTRY_VALID') and not sig.get('dismissed'):
        sig['status']=out['status']
    elif out['status']=='EXPIRED' and not sig.get('acknowledged'):
        sig['status']='MISSED_EXPIRED'
    _signal_event_v610('RECHECK',sig,dict(status=out['status'],reason=out['reason'],current_price=out.get('current_price')))
    _save_v600_state(state)
    return out,state


def render_recheck_card_v610(out, seed):
    border='━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
    s=out.get('signal') or {}; side='LONG' if int(s.get('side') or 0)>0 else 'SHORT'
    lines=[border,'       V610 — MISSED SIGNAL RECHECK',border,
           f"원 신호      {s.get('signal_id','-')}",f"발견시각    {_fmt_signal_time_v610(s.get('detected_at'))}",
           f"원 판정      {side} · ENTRY {float(s.get('entry') or 0):,.1f} / TP {float(s.get('tp_px') or 0):,.1f} / SL {float(s.get('sl_px') or 0):,.1f}",'']
    if not out.get('valid'):
        lines += ['████████████  DO NOT CHASE  ████████████','',f"현재가      {float(out.get('current_price') or 0):,.1f}",
                  f"판정        {out.get('status')}",f"사유        {out.get('reason')}",'',
                  '※ 과거 주문표를 그대로 뒤늦게 따라가지 않습니다. 현재 시점의 성장기여가 사라졌으면 WAIT입니다.',border]
        return '\n'.join(lines)
    p=out['plan']; sz=p.get('sizing') or {}; drift=float(out.get('price_drift') or 0)
    loss=float(seed)*float(sz.get('risk_actual',0))
    margin=float(sz.get('margin',0) or 0)
    lines += [f"████████████  {out.get('status')}  ████████████",'',f"현재 진입    {float(p.get('entry',0)):,.1f}",
              f"새 TP        {float(p.get('tp_px',0)):,.1f}",f"새 SL        {float(p.get('sl_px',0)):,.1f}",
              f"새 RR        1 : {float(p.get('rr',0)):.2f}",f"원진입 대비  {drift:+.3%} ({'유리한 이동' if drift<0 else '불리/추격 이동'})",'',
              f"시드 사용    {margin/max(float(seed),1e-12):.2%} ({margin:,.2f} USDT)",f"레버리지    {int(sz.get('lev',0))}x 격리",f"주문수량    {float(sz.get('qty',0)):.6f} BTC",
              f"명목금액    {float(sz.get('notional',0)):.2f} USDT",f"계좌위험    -{float(sz.get('risk_actual',0)):.3%} ≈ -{loss:,.2f} USDT",
              f"P(growth>0) {float(p.get('growth_prob',0)):.1%}",f"성장 하단   {float(p.get('growth_lb',0)):+.5%}",
              '', '※ 이것은 옛 신호의 ENTRY를 추격하라는 뜻이 아니라, 현재 가격에서 전체 모델을 새로 통과한 새 주문표입니다.',border]
    return '\n'.join(lines)


def _weighted_sample_indices(weights, shape, rng):
    w = np.asarray(weights, dtype=np.float64)
    w = np.maximum(w, 0.0)
    if w.sum() <= 0:
        w = np.ones_like(w)
    w = w / w.sum()
    return rng.choice(len(w), size=shape, replace=True, p=w)


def _growth_posterior_v600(r_mult, weights, risk_grid, n_boot=V600_GROWTH_BOOT, rng=None):
    """Posterior-like Bayesian bootstrap of expected log growth per trade."""
    r = np.asarray(r_mult, dtype=np.float64)
    w0 = np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(r) & np.isfinite(w0) & (w0 >= 0)
    r, w0 = r[ok], w0[ok]
    if len(r) < 8:
        return None
    w0 = w0 / max(w0.sum(), 1e-12)
    grid = np.asarray(risk_grid, dtype=np.float64)
    factors = 1.0 + grid[:, None] * r[None, :]
    if np.any(factors <= 0):
        # Unsafe grid points are set to -inf growth, not silently clipped.
        logm = np.where(factors > 0, np.log(np.maximum(factors, 1e-300)), -1e12)
    else:
        logm = np.log(factors)
    point = logm @ w0
    rng = rng or np.random.default_rng(V600_NULL_SEED + 11)
    e = rng.exponential(1.0, size=(int(n_boot), len(r)))
    wb = e * w0[None, :]
    wb /= np.maximum(wb.sum(axis=1, keepdims=True), 1e-12)
    draws = wb @ logm.T
    return dict(point=point,
                median=np.median(draws, axis=0),
                lower=np.quantile(draws, V600_GROWTH_Q, axis=0),
                prob=(draws > 0.0).mean(axis=0),
                draws=draws)


def _risk_path_constraints_v600(r_mult, weights, risk_grid, rng=None):
    """Monte-Carlo resampling of OOF R-multiples for drawdown/capital-floor constraints."""
    r = np.asarray(r_mult, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(r) & np.isfinite(w) & (w >= 0)
    r, w = r[ok], w[ok]
    if len(r) < 8:
        return None
    w = w / max(w.sum(), 1e-12)
    rng = rng or np.random.default_rng(V600_NULL_SEED + 17)
    ids = _weighted_sample_indices(w, (V600_MC_PATHS, V600_MC_TRADES), rng)
    seq = r[ids]
    dd_prob = np.ones(len(risk_grid), dtype=np.float64)
    floor_prob = np.ones(len(risk_grid), dtype=np.float64)
    med_terminal = np.zeros(len(risk_grid), dtype=np.float64)
    for j, f in enumerate(np.asarray(risk_grid, dtype=np.float64)):
        fac = 1.0 + float(f) * seq
        if np.any(fac <= 0):
            continue
        eq = np.cumprod(fac, axis=1)
        peak = np.maximum.accumulate(eq, axis=1)
        mdd = np.max(1.0 - eq / np.maximum(peak, 1e-300), axis=1)
        dd_prob[j] = float(np.mean(mdd > V600_MAX_DD))
        floor_prob[j] = float(np.mean(np.min(eq, axis=1) < V600_CAPITAL_FLOOR))
        med_terminal[j] = float(np.median(eq[:, -1]))
    return dict(dd_prob=dd_prob, floor_prob=floor_prob, med_terminal=med_terminal)


def _holding_hours_v600(paths, side, tp, sl, tf, H, weights=None):
    """Expected capital lock time using first TP/SL touch, capped by H."""
    HI, LO, _ = paths
    HI = np.asarray(HI); LO = np.asarray(LO)
    n, T = HI.shape
    if side > 0:
        win = HI >= tp; lose = LO <= -sl
    else:
        win = LO <= -tp; lose = HI >= sl
    fw = np.where(win.any(1), win.argmax(1), T - 1)
    fl = np.where(lose.any(1), lose.argmax(1), T - 1)
    first = np.minimum(fw, fl) + 1
    total_hours = INTERVALS[tf] * H / 60.0
    step_hours = total_hours / max(T, 1)
    h = np.maximum(first * step_hours, step_hours)
    if weights is None or len(weights) != len(h):
        return float(np.mean(h))
    return max(step_hours, _v500_weighted_mean(h, weights))


def optimize_growth_risk_v600(candidate, paths, tf, H, rng=None):
    """Maximize expected log growth under explicit drawdown and impairment constraints."""
    vals = np.asarray(candidate.get('oof_net', []), dtype=np.float64)
    weights = np.asarray(candidate.get('oof_weights', []), dtype=np.float64)
    sl = float(candidate.get('sl', 0.0))
    if len(vals) < 8 or sl <= 0:
        return None
    r_mult = vals / sl
    # Include zero in grid: if all positive-risk choices fail, WAIT is the optimizer.
    grid = np.linspace(0.0, V600_RISK_CAP, 41)
    post = _growth_posterior_v600(r_mult, weights, grid, rng=rng)
    mc = _risk_path_constraints_v600(r_mult, weights, grid, rng=rng)
    if post is None or mc is None:
        return None
    feasible = ((post['prob'] >= V600_GROWTH_PROB_MIN) &
                (mc['dd_prob'] <= V600_MAX_DD_PROB) &
                (mc['floor_prob'] <= V600_FLOOR_PROB_MAX))
    feasible[0] = True
    # Growth objective: posterior median log growth. Lower-tail growth is recorded and
    # used as a tie-break/quality penalty, not a hard demand that every bootstrap is positive.
    objective = np.where(feasible, post['median'] + 0.20*np.minimum(post['lower'], 0.0), -np.inf)
    j = int(np.argmax(objective))
    risk = float(grid[j])
    if risk <= 0:
        return dict(risk=0.0, reason='drawdown/ruin/growth constraints 아래 양(+) risk 없음')
    hold = _holding_hours_v600(paths, candidate['side'], candidate['tp'], candidate['sl'], tf, H, weights)
    gmed = float(post['median'][j]); glb = float(post['lower'][j]); gp = float(post['prob'][j])
    return dict(risk=risk, growth_median=gmed, growth_lb=glb, growth_prob=gp,
                growth_per_hour=gmed/max(hold, 1e-6), expected_hold_hours=float(hold),
                mdd_prob=float(mc['dd_prob'][j]), floor_prob=float(mc['floor_prob'][j]),
                terminal_median=float(mc['med_terminal'][j]), r_mult=r_mult)


def _prospective_state_v600(state):
    """Prospective decay monitor. It can only reduce/block risk; it never increases it."""
    closed = list(state.get('closed') or [])
    r = np.asarray([x.get('r_mult', np.nan) for x in closed[-60:]], dtype=np.float64)
    r = r[np.isfinite(r)]
    out = dict(mult=1.0, blocked=False, reason='', n=int(len(r)), mean_r=float(np.mean(r)) if len(r) else float('nan'))
    if len(r) < 20:
        return out
    rng = np.random.default_rng(V600_NULL_SEED + len(r))
    boots = np.mean(r[rng.integers(0, len(r), size=(1200, len(r)))], axis=1)
    ppos = float(np.mean(boots > 0))
    out['p_positive'] = ppos
    if ppos < 0.20:
        out.update(blocked=True, mult=0.0, reason=f'prospective edge 붕괴 의심 P(meanR>0)={ppos:.1%}')
    elif ppos < 0.50:
        out.update(mult=0.50, reason=f'prospective calibration 약화 P(meanR>0)={ppos:.1%} → risk 50%')
    elif ppos < 0.70:
        out.update(mult=0.75, reason=f'prospective calibration 불확실 P(meanR>0)={ppos:.1%} → risk 75%')
    return out


def _bar_key_v600(tf, now=None):
    now = now or datetime.now(timezone.utc)
    mins = INTERVALS[tf]
    minute_epoch = int(now.timestamp() // 60)
    # key identifies the most recently completed candle.
    return (minute_epoch // mins) - 1


def due_models_v600(state, now=None):
    now = now or datetime.now(timezone.utc)
    due = []
    last = state.setdefault('last_scan', {})
    for tf in V600_MODELS:
        key = str(_bar_key_v600(tf, now))
        if str(last.get(tf, '')) != key:
            due.append(tf)
    return due


def _mark_scanned_v600(state, tfs, now=None):
    now = now or datetime.now(timezone.utc)
    for tf in tfs:
        state.setdefault('last_scan', {})[tf] = str(_bar_key_v600(tf, now))


def _update_shadow_position_v600(dm, state):
    """Prospective paper execution. Shadow outcome is attached to the originating signal forever."""
    a=state.get('active')
    if not a: return None
    try:
        base=dm.ensure(force_refresh=True); st=pd.Timestamp(a['open_time'])
        if st.tzinfo is not None: st=st.tz_convert('UTC').tz_localize(None)
        sub=base[base.index>st]
        if sub.empty: return None
        entry=float(a['entry']); tp=float(a['tp_px']); sl=float(a['sl_px']); side=int(a['side'])
        expiry=st+pd.Timedelta(minutes=int(a['max_hold_min']))
        exit_px=exit_time=None; code=0; reason=''
        for ts,row in sub.iterrows():
            if ts>expiry: break
            hi,lo=float(row['high']),float(row['low'])
            hit_tp,hit_sl=((hi>=tp,lo<=sl) if side>0 else (lo<=tp,hi>=sl))
            if hit_sl:
                exit_px,exit_time,code,reason=sl,ts,-1,'SL'; break
            if hit_tp:
                exit_px,exit_time,code,reason=tp,ts,1,'TP'; break
        if exit_px is None and sub.index[-1]>=expiry:
            eligible=sub[sub.index<=expiry]; row=eligible.iloc[-1] if not eligible.empty else sub.iloc[0]
            exit_px=float(row['close']); exit_time=eligible.index[-1] if not eligible.empty else sub.index[0]
            code,reason=0,'TIME'
        if exit_px is None: return None
        notional=float(a['notional']); seed0=float(a['seed']); gross=side*(exit_px/entry-1.0)
        exit_kind=TP_TYPE if code==1 else SL_TYPE; net_price=gross-(_leg(ENTRY_TYPE)+_leg(exit_kind))
        pnl=notional*net_price; account_ret=pnl/max(seed0,1e-12); risk0=max(float(a.get('risk_actual',0)),1e-9)
        r_mult=account_ret/risk0
        rec=dict(model_id=a.get('model_id'),signal_id=a.get('signal_id'),tf=a.get('tf'),open_time=a['open_time'],
                 close_time=pd.Timestamp(exit_time).isoformat(),side=side,entry=entry,exit=float(exit_px),
                 code=int(code),reason=reason,pnl_usdt=float(pnl),account_ret=float(account_ret),
                 r_mult=float(r_mult),risk_actual=risk0)
        state.setdefault('closed',[]).append(rec); state['closed']=state['closed'][-500:]
        peq=float(state.get('paper_equity',seed0) or seed0); state['paper_equity']=max(0.0,peq*(1.0+account_ret))
        sid=a.get('signal_id')
        sig=_find_signal_v610(state,sid) if sid else None
        if sig:
            sig['shadow_state']='CLOSED'; sig['shadow_result']=rec
            if not sig.get('acknowledged') and not sig.get('dismissed'):
                sig['status']='MISSED_'+reason
            _signal_event_v610('SHADOW_CLOSED',sig,rec)
        state['active']=None; _save_v600_state(state); return rec
    except Exception:
        return None


def _candidate_precheck_v600(primary, scales):
    if 'winner' not in primary:
        return False, primary.get('reason', '주 신호 없음')
    p = primary['winner']; nb = primary.get('nb') or {}
    reasons = []
    if nb.get('median_shape', -1) < V600_MIN_MED_SHAPE:
        reasons.append(f'Analog r50 {nb.get("median_shape",0):.3f} 부족')
    if nb.get('n_eff', 0) < V600_MIN_NEFF:
        reasons.append(f'N_eff {nb.get("n_eff",0):.1f} 부족')
    if p.get('ev_oof', 0) <= 0:
        reasons.append(f'OOF EV {p.get("ev_oof",0):+.3%} ≤ 0')
    if p.get('edge_prob', 0) < V600_EDGE_PROB_MIN:
        reasons.append(f'P(edge>0) {p.get("edge_prob",0):.1%} 부족')
    pg = primary.get('pval_global', float('nan'))
    if np.isfinite(pg) and pg > V600_GLOBAL_P_MAX:
        reasons.append(f'Global p {pg:.3f} > {V600_GLOBAL_P_MAX:.2f}')
    runner = primary.get('runner_up')
    if runner is not None and runner.get('edge_lb', -1) > 0:
        gap = float(p.get('edge_prob',0) - runner.get('edge_prob',0))
        if gap < V600_SIDE_GAP_MIN and abs(p.get('score',0)-runner.get('score',0)) < 0.15:
            reasons.append('LONG/SHORT 양면 edge 모호')
    votes=[]
    for r in scales:
        w = r.get('winner')
        if w and w.get('edge_prob',0) >= 0.62 and w.get('ev_oof',0) > 0:
            votes.append(int(w['side']))
    if sum(v == p['side'] for v in votes) < 2:
        reasons.append(f'multiscale 합의 부족 {votes}')
    return (not reasons), (' / '.join(reasons) if reasons else ''), votes


def scan_model_v600(dm, seed, tf, ctx, state, status=None, do_null=True):
    """Two-stage production scan: cheap scout first, expensive matched-null only for survivors."""
    status = status or (lambda *a, **k: None)
    spec = V600_MODELS[tf]; K=int(spec['K']); H=int(spec['H']); topk=int(spec['topk'])
    df = dm.get(tf, force_refresh=False)
    if df is None or len(df) < 3*K + 2*H + 100:
        return dict(tf=tf, trade=False, reason='데이터 부족', model_label=spec['label'])
    ch = Channels(df)
    levels = sr_levels(ch.high, ch.low, ch.close, df['volume'].values.astype(np.float64))
    rng = np.random.default_rng(V600_NULL_SEED + INTERVALS[tf])

    # Stage 1: Analog + cross-fit edge + posterior uncertainty. No expensive null yet.
    scales=[]
    for f in V600_SCALE_FACTORS:
        kk=max(30,int(round(K*f)))
        status(f'{tf} scout K={kk}: Analog + OOF...', 'blue')
        r=analyze_scale_v500(ch, dm.base, df.index, tf, kk, H, ctx, topk=topk, levels=levels,
                             status=status, use_1m=True, do_null=False, rng=rng)
        scales.append(r)
    primary=next((x for x in scales if x.get('K')==K), scales[0])
    ok, why, votes = _candidate_precheck_v600(primary, scales)
    plan=dict(tf=tf,K=K,H=H,scales=scales,primary=primary,trade=False,reason=why,
              seed=float(seed),model_id=V600_MODEL_ID,model_label=spec['label'],votes=votes,
              exchange_context=ctx)
    if not ok:
        return plan
    p=primary['winner']; nb=primary['nb']

    # Stage 2: only a plausible growth candidate pays the expensive data-snooping tax.
    if do_null:
        status(f'{tf} finalist: matched-null hostile audit...', 'blue')
        obs=max(c.get('ev_oof',-1e99) for c in primary.get('candidates',[]) if c is not None)
        pv,null=matched_null_v500(ch,dm.base,df.index,tf,K,H,nb,ctx,obs,len(nb['starts']),
                                 use_1m=True,n_boot=V600_NULL_N,rng=rng)
        primary['pval_raw']=float(pv)
        primary['pval_global']=min(1.0,float(pv)*len(V600_SCALE_FACTORS))
        primary['null_mean']=float(np.mean(null)) if len(null) else float('nan')
        if primary['pval_global']>V600_GLOBAL_P_MAX:
            plan['reason']=f'final matched-null Global p={primary["pval_global"]:.3f} > {V600_GLOBAL_P_MAX:.2f}'
            return plan

    # Context validates but never reverses the Analog direction.
    cmult,veto,creasons=context_risk_multiplier_v500(ctx,p['side'],tf,H)
    if veto:
        plan['reason']=veto; plan['context_notes']=creasons; return plan

    growth=optimize_growth_risk_v600(p, primary['paths'], tf, H, rng=rng)
    if not growth or growth.get('risk',0)<=0:
        plan['reason']=(growth or {}).get('reason','robust growth optimizer 실패'); return plan

    prospective=_prospective_state_v600(state)
    if prospective.get('blocked'):
        plan['reason']=prospective.get('reason','prospective decay'); return plan

    # Evidence/context/prospective can only reduce the log-growth optimizer's risk.
    evidence_mult=np.clip((p.get('edge_prob',0.5)-0.50)/0.35,0.25,1.0)
    sample_mult=np.clip(nb.get('n_eff',0)/20.0,0.40,1.0)
    stability_mult=np.clip(p.get('stability',0.5),0.40,1.0)
    risk=float(growth['risk']*evidence_mult*sample_mult*stability_mult*cmult*prospective.get('mult',1.0))
    risk=min(risk,V600_RISK_CAP)
    if risk<V600_RISK_FLOOR:
        plan['reason']=f'성장 최적 risk가 검증 페널티 후 {risk:.3%} → WAIT'; return plan

    entry=float(ch.close[-1])
    sz=size_position_v500(seed,entry,p['sl'],risk,tf,H,ctx)
    if not sz.get('executable') or sz.get('lev',99)>V600_MAX_LEV or sz.get('margin',1e99)>seed*V600_MARGIN_CAP:
        plan['reason']=sz.get('reason','V600 저레버리지/증거금 제약 불일치'); return plan
    if sz.get('risk_actual',1)>V600_RISK_CAP*1.01:
        plan['reason']='실질 계좌위험이 V600 상한 초과'; return plan

    plan.update(trade=True,side=p['side'],entry=entry,tp=p['tp'],sl=p['sl'],rr=p['rr'],
                tp_px=p['tp_px'],sl_px=p['sl_px'],risk_frac=risk,sizing=sz,
                growth_score=float(growth['growth_per_hour']),context_notes=creasons,
                prospective=prospective,**{k:v for k,v in growth.items() if k!='r_mult'})
    p['nb']=nb; p['pval_global']=primary.get('pval_global'); primary.update(p)
    return plan

def choose_opportunity_v600(plans):
    valid=[p for p in plans if p.get('trade')]
    if not valid:
        reasons=' | '.join(f'{p.get("tf")}: {p.get("reason","WAIT")}' for p in plans)
        return dict(trade=False,reason=reasons,alternatives=plans,model_id=V600_MODEL_ID)
    # Scarce capital goes to the best robust log-growth per expected lock hour.
    valid.sort(key=lambda p:(p.get('growth_score',-1e99),p.get('growth_median',-1e99)),reverse=True)
    best=valid[0]
    best['alternatives']=plans
    if len(valid)>1:
        second=valid[1]
        # If opposite directions have almost identical growth efficiency, abstain.
        if second.get('side') != best.get('side'):
            a=max(abs(best.get('growth_score',0)),1e-12)
            if abs(best.get('growth_score',0)-second.get('growth_score',0))/a < 0.10:
                return dict(trade=False,reason='서로 반대인 시간축의 성장기여도가 거의 동일 → WAIT',
                            alternatives=plans,model_id=V600_MODEL_ID)
    return best


def oneclick_scan_v600(dm, seed, tfs=None, status=None):
    status=status or (lambda *a,**k:None); seed=float(seed); state=_load_v600_state(seed)
    status('최신 1분봉 갱신...','blue'); dm.ensure(force_refresh=True)
    lag=float(dm.meta.get('lag_min',9999))
    if not np.isfinite(lag) or lag>MAX_STALE_MIN:
        return dict(blocked=True,trade=False,reason=f'데이터 지연 {lag:.0f}분',model_id=V610_MODEL_ID),state
    closed=_update_shadow_position_v600(dm,state)
    if closed: status(f'prospective shadow 종료: {closed["reason"]} {closed["r_mult"]:+.2f}R','green' if closed['r_mult']>0 else 'orange')
    # Prospective strategy still uses one BTC shadow position at a time, but the originating signal remains in the ledger.
    if state.get('active'):
        return dict(blocked=True,trade=False,hold=True,reason='활성 shadow 포지션 보유 중 — 신규 BTC 위험 중첩 금지',
                    active=state['active'],model_id=V610_MODEL_ID),state
    status('거래소 규칙·시장 컨텍스트 확인...','blue'); ctx=fetch_exchange_context_v500()
    if np.isfinite(ctx.get('spread_bps',float('nan'))) and ctx['spread_bps']>V500_SPREAD_MAX_BPS:
        return dict(blocked=True,trade=False,reason=f'스프레드 {ctx["spread_bps"]:.2f}bp 과대',exchange_context=ctx,model_id=V610_MODEL_ID),state
    plans=[]
    for tf in list(tfs or V600_MODELS.keys()):
        if tf in V600_MODELS: plans.append(scan_model_v600(dm,seed,tf,ctx,state,status=status,do_null=True))
    result=choose_opportunity_v600(plans); result['exchange_context']=ctx; result['model_id']=V610_MODEL_ID
    if result.get('trade'):
        sig=_register_signal_v610(result,dm,seed,state); sz=result['sizing']; result['signal_id']=sig['signal_id']
        state['active']=dict(model_id=V610_MODEL_ID,signal_id=sig['signal_id'],tf=result['tf'],side=result['side'],
                             open_time=pd.Timestamp(dm.get(result['tf']).index[-1]).tz_localize('UTC').isoformat(),
                             entry=result['entry'],tp_px=result['tp_px'],sl_px=result['sl_px'],
                             max_hold_min=INTERVALS[result['tf']]*result['H'],notional=sz['notional'],qty=sz['qty'],
                             lev=sz['lev'],margin=sz.get('margin',0.0),risk_actual=sz['risk_actual'],seed=seed)
        _save_v600_state(state)
    _append_v600_decision(result); return result,state


def render_oneclick_card_v600(plan, seed, state=None):
    now=_now_utc_aware().astimezone(_KST); state=state or _load_v600_state(seed)
    border='━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
    head=[border,'       PatternEdge V610 — MISSED SIGNAL GUARD',border,
          f'모델        {V610_MODEL_ID}',f'현재시각    {now:%Y-%m-%d %H:%M:%S KST}',f'시장        {SYMBOL} PERP · 24/7 AUTO','']
    closed=state.get('closed') or []
    if closed:
        rr=np.asarray([x.get('r_mult',np.nan) for x in closed],dtype=np.float64); rr=rr[np.isfinite(rr)]
        if len(rr): head += [f'Shadow      {len(rr)} trades · 평균 {np.mean(rr):+.2f}R · paper {float(state.get("paper_equity",seed)):,.2f} USDT','']
    head += render_signal_banner_v610(state)
    if plan is None: return '\n'.join(head+['LIVE SCANNER  24/7 감시 대기','',border])
    if plan.get('hold'):
        a=plan.get('active') or {}; side='LONG' if int(a.get('side',1))>0 else 'SHORT'
        margin=float(a.get('margin',0) or 0); seed0=max(float(a.get('seed', seed) or seed),1e-12);
        risk_actual=float(a.get('risk_actual',0) or 0); loss=seed0*risk_actual
        return '\n'.join(head+[f'██████████  SHADOW HOLD {side}  ██████████','',f'진입        {a.get("entry",0):,.1f}',
                               f'TP          {a.get("tp_px",0):,.1f}',f'SL          {a.get("sl_px",0):,.1f}',
                               f'시드 사용   {margin/seed0:.2%} ({margin:,.2f} USDT)',f'레버리지    {int(a.get("lev",0) or 0)}x 격리',
                               f'주문수량    {float(a.get("qty",0) or 0):.6f} BTC',f'명목금액    {float(a.get("notional",0) or 0):,.2f} USDT',
                               f'계좌위험    -{risk_actual:.3%} ≈ -{loss:,.2f} USDT',
                               f'사유        {plan.get("reason","")}',border])
    if plan.get('blocked') or not plan.get('trade'):
        lines=head+['████████████   LIVE: WAIT   ████████████','',f'사유        {plan.get("reason","조건 미충족")}']
        for p in plan.get('alternatives',[])[:3]: lines.append(f'{p.get("tf","-"):>4}         {p.get("reason","WAIT")[:100]}')
        lines += ['', '※ 위 LAST ACTIONABLE SIGNAL은 새 WAIT가 떠도 삭제되지 않습니다.',
                  '다음 판정    새 5m/15m/1h 완결봉에서 자동 재평가',border]
        return '\n'.join(lines)
    p=plan.get('primary') or {}; nb=p.get('nb') or {}; sz=plan['sizing']; side='LONG' if plan['side']>0 else 'SHORT'
    loss=float(seed)*float(sz.get('risk_actual',0)); margin_pct=float(sz['margin'])/max(float(seed),1e-12)
    lines=head+[f'████████████  NEW {side:^5s}  ████████████',f'신호 ID     {plan.get("signal_id","-")}',
                f'선택모델    {plan.get("model_label",plan.get("tf"))} ({plan.get("tf")})','',
                f'진입        {plan["entry"]:,.1f} USDT',f'익절 TP     {plan["tp_px"]:,.1f} USDT',f'손절 SL     {plan["sl_px"]:,.1f} USDT',
                f'손익비      1 : {plan["rr"]:.2f}',f'예상보유    {plan.get("expected_hold_hours",0):.2f}h / 최대 {INTERVALS[plan["tf"]]*plan["H"]/60:.1f}h','',
                f'시드 사용   {margin_pct:.2%} ({sz["margin"]:,.2f} USDT)',f'레버리지    {int(sz["lev"])}x 격리',f'주문수량    {sz["qty"]:.6f} BTC',
                f'명목금액    {sz["notional"]:,.2f} USDT',f'계좌위험    -{sz["risk_actual"]:.3%} ≈ -{loss:,.2f} USDT','',
                f'로그성장/tr {plan.get("growth_median",0):+.5%}',f'성장 하단   {plan.get("growth_lb",0):+.5%}',f'P(growth>0) {plan.get("growth_prob",0):.1%}',
                f'성장/시간   {plan.get("growth_per_hour",0):+.6%}/h',f'MDD>{V600_MAX_DD:.0%}   {plan.get("mdd_prob",1):.2%}',
                f'Analog      r50={nb.get("median_shape",0):.3f} · N_eff={nb.get("n_eff",0):.1f}',f'OOF EV      {p.get("ev_oof",0):+.3%}',
                f'P(edge>0)   {p.get("edge_prob",0):.1%}',f'Global p    {p.get("pval_global",float("nan")):.4f}','',
                '※ 이 주문표는 SIGNAL LEDGER에 즉시 영구 저장되었습니다. 못 봐도 다음 WAIT가 지우지 않습니다.',border]
    return '\n'.join(lines)


def _v600_selftest():
    rng=np.random.default_rng(42)
    # Negative edge must choose zero risk.
    neg=rng.choice([-1.0,0.7],size=36,p=[0.58,0.42])
    w=np.ones(len(neg))/len(neg)
    dummy=dict(oof_net=neg*0.01,oof_weights=w,sl=0.01,side=1,tp=0.015)
    T=24; HI=np.maximum.accumulate(rng.normal(0,0.002,(36,T)),axis=1); LO=np.minimum.accumulate(rng.normal(0,0.002,(36,T)),axis=1); CL=rng.normal(0,0.002,(36,T))
    a=optimize_growth_risk_v600(dummy,(HI,LO,CL),'5m',24,rng=np.random.default_rng(1))
    # Positive edge should usually admit some risk under the configured constraints.
    pos=rng.choice([-1.0,1.5],size=36,p=[0.42,0.58])
    dummy2=dict(oof_net=pos*0.01,oof_weights=w,sl=0.01,side=1,tp=0.015)
    b=optimize_growth_risk_v600(dummy2,(HI,LO,CL),'5m',24,rng=np.random.default_rng(2))
    return dict(negative=a,positive=b,model_id=V600_MODEL_ID)


def main():
    from tkinter import Tk,Button,Entry,Label,Frame,Checkbutton,IntVar,DISABLED,NORMAL,WORD,messagebox
    from tkinter.scrolledtext import ScrolledText
    class V610App:
        def __init__(self,root):
            self.root=root; self.dm=DataManager(log=self.set_status); self.running=False; self.plan=None
            self.state=_load_v600_state(71)
            root.title(f'PatternEdge {__version__} — {SYMBOL} 24/7'); root.geometry('980x940'); root.protocol('WM_DELETE_WINDOW',self.close)
            top=Frame(root,padx=12,pady=10); top.pack(fill='x')
            Label(top,text='PatternEdge V610 — MISSED SIGNAL GUARD',font=('Malgun Gothic',16,'bold')).grid(row=0,column=0,columnspan=9,sticky='w')
            Label(top,text='시드(USDT)').grid(row=1,column=0,sticky='e',pady=8)
            self.seed_e=Entry(top,width=12,font=('Consolas',12)); self.seed_e.grid(row=1,column=1,sticky='w'); self.seed_e.insert(0,'71')
            self.auto_var=IntVar(value=1); Checkbutton(top,text='24/7 자동 감시',variable=self.auto_var).grid(row=1,column=2,sticky='w',padx=10)
            self.scan_btn=Button(top,text='지금 전체 분석',command=self.run_now,bg='#0b6e4f',fg='white',font=('Malgun Gothic',11,'bold'),height=2)
            self.scan_btn.grid(row=2,column=0,columnspan=2,sticky='ew',pady=6)
            Button(top,text='최근 신호 재검증',command=self.recheck_signal,bg='#b71c1c',fg='white').grid(row=2,column=2,padx=3)
            Button(top,text='패턴 차트',command=self.show_pattern_chart,bg='#263238',fg='white').grid(row=2,column=3,padx=3)
            Button(top,text='신호 확인',command=self.mark_seen).grid(row=2,column=4,padx=3)
            Button(top,text='신호 기록',command=self.show_signal_history).grid(row=2,column=5,padx=3)
            Button(top,text='전체 데이터 구축/복구',command=self.build_data).grid(row=2,column=6,padx=3)
            Button(top,text='상세',command=self.show_detail).grid(row=2,column=7,padx=3)
            Button(top,text='Shadow 초기화',command=self.reset_shadow).grid(row=2,column=8,padx=3)
            self.next_label=Label(top,text='',font=('Malgun Gothic',9)); self.next_label.grid(row=3,column=0,columnspan=9,sticky='w')
            self.status=Label(top,text='대기 중',anchor='w'); self.status.grid(row=4,column=0,columnspan=9,sticky='w')
            for c in range(9): top.grid_columnconfigure(c,weight=1)
            self.txt=ScrolledText(root,height=38,font=('Consolas',10),wrap=WORD,state=DISABLED); self.txt.pack(fill='both',expand=True,padx=10,pady=(0,10))
            threading.Thread(target=self.boot,daemon=True).start(); self.root.after(V600_AUTO_POLL_MS,self.auto_loop)
        def seed(self):
            v=float(self.seed_e.get());
            if v<=0: raise ValueError('시드는 0보다 커야 합니다.')
            return v
        def set_status(self,text,color='black'):
            try:self.root.after(0,lambda:self.status.config(text=text,fg=color))
            except Exception:pass
        def show(self,text):
            def f(): self.txt.config(state=NORMAL); self.txt.delete('1.0','end'); self.txt.insert('end',text); self.txt.config(state=DISABLED)
            self.root.after(0,f)
        def boot(self):
            try:
                self.dm.ensure(); self.state=_load_v600_state(self.seed()); _save_v600_state(self.state)
                self.set_status(self.dm.data_banner('1m'),'green'); self.show(render_oneclick_card_v600(None,self.seed(),self.state))
            except Exception as e:self.set_status(f'데이터 준비 필요: {e}','red')
        def auto_loop(self):
            try:
                self.state=_load_v600_state(self.seed()); due=due_models_v600(self.state); a=self.state.get('active')
                latest=_find_signal_v610(self.state); unseen=' · 🚨미확인신호' if latest and not latest.get('acknowledged') and not latest.get('dismissed') else ''
                active_txt=f' · shadow {a.get("tf")}' if a else ''
                self.next_label.config(text=f'24/7 새 봉 감시 · due={due or "없음"}{active_txt}{unseen} · model {V610_MODEL_ID}')
                if self.auto_var.get() and due and not self.running:self.run_now(auto=True,tfs=due)
            except Exception as e:self.next_label.config(text=f'감시 오류: {e}')
            self.root.after(V600_AUTO_POLL_MS,self.auto_loop)
        def run_now(self,auto=False,tfs=None):
            if self.running:return
            try:s=self.seed()
            except Exception as e:messagebox.showerror('입력 오류',str(e));return
            self.running=True; self.scan_btn.config(state=DISABLED); self.set_status(('자동' if auto else '수동')+' growth audit 시작...','blue')
            threading.Thread(target=self._worker,args=(s,tfs,auto),daemon=True).start()
        def _worker(self,s,tfs,auto):
            try:
                plan,state=oneclick_scan_v600(self.dm,s,tfs=tfs,status=self.set_status)
                if auto and tfs:_mark_scanned_v600(state,tfs); _save_v600_state(state)
                self.plan,self.state=plan,state; self.show(render_oneclick_card_v600(plan,s,state))
                if plan.get('trade'):
                    self.set_status('🚨 성장기회 포착 — SIGNAL LEDGER 영구 저장','red')
                    try:self.root.after(0,lambda:self.root.bell())
                    except Exception:pass
                else:self.set_status('포지션 관리 중' if plan.get('hold') else '완료 — WAIT','#b26a00')
            except Exception as e:
                import traceback; traceback.print_exc(); self.set_status(f'분석 실패: {type(e).__name__}: {e}','red')
            finally:self.running=False; self.root.after(0,lambda:self.scan_btn.config(state=NORMAL))
        def recheck_signal(self):
            if self.running:return
            self.running=True; self.set_status('놓친 신호 현재가 전체 재검증...','blue')
            def work():
                try:
                    out,state=recheck_latest_signal_v610(self.dm,self.seed(),_load_v600_state(self.seed()),status=self.set_status)
                    self.state=state; self.show(render_recheck_card_v610(out,self.seed()))
                    self.set_status('재진입 가능 — 현재 주문표 확인' if out.get('valid') else '재진입 금지/만료', 'green' if out.get('valid') else 'red')
                except Exception as e:self.set_status(f'재검증 실패: {e}','red')
                finally:self.running=False
            threading.Thread(target=work,daemon=True).start()
        def show_pattern_chart(self):
            self.state=_load_v600_state(self.seed())
            show_pattern_window_v610(self.root, self.dm, self.state)
        def mark_seen(self):
            self.state=_load_v600_state(self.seed()); s=_mark_signal_seen_v610(self.state)
            if s:self.show(render_oneclick_card_v600(self.plan,self.seed(),self.state)); self.set_status('최근 신호 확인 처리 — 기록은 삭제되지 않음','green')
            else:messagebox.showinfo('안내','확인할 신호가 없습니다.')
        def show_signal_history(self):
            self.state=_load_v600_state(self.seed()); w=__import__('tkinter').Toplevel(self.root); w.title('V610 ACTIONABLE SIGNAL LEDGER'); w.geometry('1050x850')
            box=ScrolledText(w,font=('Consolas',10),wrap=WORD); box.pack(fill='both',expand=True); box.insert('1.0',_signal_history_text_v610(self.state,200)); box.config(state=DISABLED)
        def show_detail(self):
            try:
                txt=render_oneclick_card_v600(self.plan,self.seed(),self.state)+'\n\n[SIGNAL HISTORY]\n'+_signal_history_text_v610(self.state,50)
                txt+='\n\n[DATA]\n'+self.dm.data_banner('1m')+'\n\n[STATE]\n'+json.dumps(_json_safe_plan(self.state),ensure_ascii=False,indent=2)
                w=__import__('tkinter').Toplevel(self.root); w.title('V610 detail'); w.geometry('1100x920'); box=ScrolledText(w,font=('Consolas',9),wrap=WORD); box.pack(fill='both',expand=True); box.insert('1.0',txt); box.config(state=DISABLED)
            except Exception as e:messagebox.showerror('상세 오류',str(e))
        def build_data(self):
            if self.running:return
            self.running=True; threading.Thread(target=self._build,daemon=True).start()
        def _build(self):
            try:
                self.set_status('전체 히스토리 구축/복구...','blue'); self.dm.build_full_history(progress=lambda i,t,m:self.set_status(f'[{i}/{t}] {m}','blue'))
                self.dm.ensure(force_refresh=True); self.set_status('데이터 구축 완료','green')
            except Exception as e:self.set_status(f'구축 실패: {e}','red')
            finally:self.running=False
        def reset_shadow(self):
            if messagebox.askyesno('확인','prospective shadow만 초기화할까요? SIGNAL LEDGER는 절대 삭제하지 않습니다.'):
                self.state=_load_v600_state(self.seed()); self.state['active']=None; self.state['closed']=[]; self.state['paper_equity']=self.seed(); self.state['last_scan']={}
                _save_v600_state(self.state); self.show(render_oneclick_card_v600(None,self.seed(),self.state))
        def close(self):
            try:self.root.quit();self.root.destroy()
            except Exception:pass
    root=Tk(); V610App(root); root.mainloop()


if __name__ == '__main__':
    # Forensic/research modes are intentionally preserved.
    #   default     : V610 24/7 growth machine + persistent missed-signal guard
    #   --once      : console one-shot full scan
    #   --selftest  : offline growth/risk sanity test
    #   --v500      : previous council GUI
    #   --v400      : older one-click GUI
    #   --advanced  : original research GUI
    if '--selftest' in sys.argv:
        print(json.dumps(_json_safe_plan(_v600_selftest()),ensure_ascii=False,indent=2))
    elif '--once' in sys.argv:
        seed=float(os.environ.get('PATTERNEDGE_SEED','71'))
        dm=DataManager(log=lambda x,*a: print(x))
        plan,state=oneclick_scan_v600(dm,seed)
        print(render_oneclick_card_v600(plan,seed,state))
    elif '--advanced' in sys.argv:
        main_advanced()
    elif '--v400' in sys.argv:
        main_v400()
    elif '--v500' in sys.argv:
        main_v500()
    else:
        main()
