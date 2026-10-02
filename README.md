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
```

## 테스트

```
pip install pytest
python -m pytest            # GUI 테스트는 DISPLAY 가 있을 때만 (Linux: xvfb-run -a python -m pytest)
```

> 합성 데이터 테스트는 **수익성 증거가 아닙니다.** 실데이터 워크포워드(E4)와 prospective shadow(E5)를
> 거치기 전에는 신호를 검증된 엣지로 간주하지 마세요. 자세한 내용은 `AUDIT_V611_V612.md`를 보세요.
