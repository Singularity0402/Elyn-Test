# Elyn-Test — PatternEdge V612

BTCUSDT 무기한선물용 Analog-first 의사결정 지원 도구입니다. **주문은 사람이 직접 클릭합니다.**
이 프로그램은 자동 매매를 하지 않고, private/signed API와 API key를 쓰지 않습니다.

| 파일 | 설명 |
|---|---|
| `pattern_edge_v612.py` | 최종 단일 파일. Windows → IDLE → F5 로 실행하면 GUI가 뜹니다. |
| `01_BASELINE/pattern_edge_v611_visual_audit.py` | V611 원본. 수정 금지이며 SHA256 `6078…775e`로 테스트가 확인합니다. |
| `AUDIT_V611_V612.md` | 객관 감사 보고서: 결함 재현 증거, 수정 내역, 남은 한계, 다음 단계 |
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
python pattern_edge_v612.py --lab --only 4h:flow --symbols default  # 그 가설을 알트 8개에 그대로 적용 (재현 검증, 원장 기록)
python pattern_edge_v612.py --lab --universe                # 코인 묶음(BTC+알트 8개) 탐색: 모든 코인 거래를 합쳐 고르고 하루 복리로 순위
python pattern_edge_v612.py --lab --universe --surrogate-n 20 # 같은 날짜 순서로 섞은 가짜 코인 묶음 20개와 비교 (약 6분)
#   --universe ETHUSDT,SOLUSDT : 코인 직접 지정 (BTC 는 항상 포함) · --tfs 1h,4h : 시간봉 (15m 도 가능, 첫 다운로드가 김)
#   --no-funding : 펀딩비를 받지 않고 실행
```

## 테스트

```
pip install pytest
python -m pytest            # GUI 테스트는 DISPLAY 가 있을 때만 (Linux: xvfb-run -a python -m pytest)
```

> 합성 데이터 테스트는 **수익성 증거가 아닙니다.** 실데이터 워크포워드(E4)와 prospective shadow(E5)를
> 거치기 전에는 신호를 검증된 엣지로 간주하지 마세요. 자세한 내용은 `AUDIT_V611_V612.md`를 보세요.
