# Elyn-Test — PatternEdge V612

BTCUSDT 무기한선물용 Analog-first 의사결정 지원 도구입니다. **주문은 사람이 직접 클릭합니다.**
이 프로그램은 자동 매매를 하지 않고, private/signed API와 API key를 쓰지 않습니다.

| 파일 | 설명 |
|---|---|
| `pattern_edge_v612.py` | 최종 단일 파일. Windows → IDLE → F5 로 실행하면 GUI가 뜹니다. |
| `01_BASELINE/pattern_edge_v611_visual_audit.py` | V611 원본. 수정 금지이며 SHA256 `6078…775e`로 테스트가 확인합니다. |
| `AUDIT_V611_V612.md` | 객관 감사 보고서: 결함 재현 증거, 수정 내역, 남은 한계, 다음 단계 |
| `RESEARCH_LOG.md` | **연구 일지·패인 기록** (덧붙이기만 함). 교훈 L1~L10, 가설 상태, 사전등록, 모든 실험 결과 |
| `tests/` | V611 결함 재현 + V612 수정 검증 + 수명주기/GUI 스모크 (pytest) |
| `experiments/` | 감사 보고서 숫자를 재현하는 스크립트 (null 보정도, 무엣지 시장 거짓 신호율) |

## 실행

```
pip install numpy pandas requests pyarrow numba matplotlib
python pattern_edge_v612.py --selftest                      # 오프라인 자가검사
python pattern_edge_v612.py                                 # GUI (IDLE F5 와 동일)
python pattern_edge_v612.py --walkforward 15m 2024-01-01    # 생산엔진 워크포워드
python pattern_edge_v612.py --walkforward 15m 2024-01-01 --surrogate   # 가짜 BTC 대조군
#   추가 옵션: --null (matched-null 포함) --workers 6 (병렬 작업자 수) --step 8 (평가 간격, 봉) --no-cache
python pattern_edge_v612.py --lab                           # 전략 탐색기: 12개 전략군(펀딩비·패턴반복 포함) × 5m/15m/1h/4h 롤링 WFO (약 20초)
python pattern_edge_v612.py --lab --surrogate               # 같은 탐색을 가짜 BTC 에서 (운의 크기)
python pattern_edge_v612.py --lab --surrogate-n 20          # 가짜 BTC 20개로 p값 (선택까지 보정한 p(최고 절차), 약 4분)
python pattern_edge_v612.py --lab --cost maker_entry        # 지정가 진입 비용 시나리오 (taker / maker_entry / maker)
python pattern_edge_v612.py --lab --only 4h:flow            # 탐색에서 고른 가설 하나만 (표본외 DSR 은 전체 절차 수로 보정)
python pattern_edge_v612.py --lab --only 4h:flow --surrogate-n 50     # 그 가설의 운의 크기 (약 2분)
python pattern_edge_v612.py --lab --only 4h:flow --reveal-holdout     # 그 가설만 봉인된 최근 9개월 공개 (1회, 원장 기록)
python pattern_edge_v612.py --lab --only 4h:flow --symbols default  # 그 가설을 ETH 에 그대로 적용 (재현 검증, 원장 기록 · 알트는 alts)
python pattern_edge_v612.py --lab --universe                # 코인 묶음(BTC+ETH) 탐색: 모든 코인 거래를 합쳐 고르고 하루 복리로 순위
python pattern_edge_v612.py --lab --universe --surrogate-n 20 # 같은 날짜 순서로 섞은 가짜 코인 묶음 20개와 비교 (약 6분)
#   --universe ETHUSDT,SOLUSDT : 코인 직접 지정 (BTC 는 항상 포함) · --tfs 1h,4h : 시간봉 (15m 도 가능, 첫 다운로드가 김)
python pattern_edge_v612.py --journal                       # 연구 일지: 교훈·가설 상태·사전등록·모든 실행 기록 (md 로도 저장)
python pattern_edge_v612.py --lab --presample               # 사전등록 P1: BTC 전체 이력에서 처음 보는 구간(2019-08~2021-11)만으로 판정 (가설마다 1회)
python pattern_edge_v612.py --lab --final 4h:keltner        # 사전등록 P2: 봉인 구간(2026-01-01~)을 단 한 번 열어 BTC + 코인 묶음으로 최종 판정
python pattern_edge_v612.py --lab --alt-presample          # 사전등록 P3: 알트 스팟 이력(2017~2021)의 처음 보는 구간으로 판정 (1회)
python pattern_edge_v612.py --lab --prospective             # 앞으로의 검증: 규칙 고정(2026-10-04) 이후 데이터로만 후보 채점 (언제든)
python pattern_edge_v612.py --lab --wick                    # 지정가 꼬리 잡기: 미리 거는 지정가(수수료 0.02%)로 청산 꼬리를 받는 단타, 1분봉 체결 판정
python pattern_edge_v612.py --lab --regime 4h:consensus     # 사전등록 P4: 다른 국면(2021-11~2026-10)에서 BTC(1순위)·ETH(2순위)로 판정 (1회)
python pattern_edge_v612.py --lab --signal --seed 70        # 지금 신호: 추적 중인 BTC 후보(4h 체결강도·Bollinger)의 다음 봉 할 일·손절가 (종이 매매용)
python pattern_edge_v612.py --lab --stop-pct 1              # 짧은 시간봉(5m/15m/1h) · 가격 1% 고정 손절 · 익절 2R/3R/신호 중 선택 · 계좌 위험 1/2/3% 별 결과
#   --tp 2,3,5 : 익절 R 배수 후보 · --tfs 5m,15m : 시간봉 · --surrogate-n 20 : 같은 설정의 운의 크기
python pattern_edge_v612.py --lab --stop-pct 1 --cost maker_entry --fees 0.045,0.018   # 내 실제 수수료(시장가%,지정가%)로 다시 (별개의 시험으로 집계)
python pattern_edge_v612.py --lab --oracle                  # 정답 단서 학습: '+2%가 −1%보다 먼저 왔나'(정답)를 붙이고, 그 시점의 단서 18개로 확률을 배워 상위 확률에서만 진입
#   --tfs 15m|1h|4h · --stop-pct 1 · --tp 2 · --hold 24 : 정답 정의 바꾸기 (설정마다 새 시험으로 집계) · 분위표·단서표 함께 출력
#   코인 묶음·재현의 기본값은 BTC+ETH 입니다 (L16). 알트 8개는 --universe alts / --symbols alts 로 명시할 때만.
#   모든 보고서 끝에 '하루 1% 복리에 필요한 연환산 샤프 ≈ 2.7(켈리)/3.1(반켈리)' 와 이번 최고 샤프를 함께 보인다.
#   모든 Lab 실행은 연구 일지에 자동 기록되고, DSR 은 누적 시험 절차 수로 보정되며, holdout 시작은 2026-01-01 로 고정된다.
#   반증된 가설의 재시험은 --retest "사유" 가 있어야 하고, holdout 공개는 --only 로 선언한 가설에만 된다.
#   --no-funding : 펀딩비를 받지 않고 실행
```

## 테스트

```
pip install pytest
python -m pytest            # GUI 테스트는 DISPLAY 가 있을 때만 (Linux: xvfb-run -a python -m pytest)
```

> 합성 데이터 테스트는 **수익성 증거가 아닙니다.** 실데이터 워크포워드(E4)와 prospective shadow(E5)를
> 거치기 전에는 신호를 검증된 엣지로 간주하지 마세요. 자세한 내용은 `AUDIT_V611_V612.md`를 보세요.
