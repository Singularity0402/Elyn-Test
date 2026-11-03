# 외부 증거 입력과 검토 receipt (schema 1)

`evidence.py`는 파일 무결성·기록 품질·리뷰 연결을 검사한다. 자유응답의 뜻, 실제 사람 여부, 캡처의 진위를 자동 추론하지 않는다. `verified`는 해당 입력 파일에 연결된 외부 리뷰 receipt가 조건을 충족했다는 뜻이다. reviewer ID의 실제 신원과 진실성은 별도 모집·검토 절차에서 관리해야 한다. 코드가 신원을 인증하거나 화면을 실사했다고 해석하지 않는다.

현재 production 입력은 빈 배열 5개다. 외부 증거가 없으면 A/B 각각 J08·L02·L03·L04·L05·L06·L08 모두 PENDING이며 인원은 0, 미측정 비율은 null이다. 테스트 PASS는 production 증거의 PASS와 무관하다. 테스트의 모든 관객·receipt·이미지는 **SYNTHETIC / QA** 시뮬레이션이며 시스템 임시 testroot에만 생성한다. 합성 fixture를 이 inputs 디렉터리로 복사하지 않는다.

## 실행과 반환

공모전 프로젝트 루트(`hetbahn_2026`)를 `--project-root`에 전달한다. `policy.protocol_path`와 assets 경로는 이 루트 기준이다. 정책의 추가 audit/review_bindings 키는 이 모듈의 외부증거를 대체하지 않는다.

```powershell
python -B evidence.py --policy policy.json --project-root .. --inputs inputs
python -B evidence.py --policy policy.json --project-root .. --inputs inputs --now 2026-11-03T13:30:00Z
python -B -m unittest discover -s tests -p 'test_*.py'
```

Python API: `evaluate(policy: dict, project_root: Path, inputs_root: Path, now_utc: datetime) -> dict`. now는 timezone-aware datetime이어야 한다. CLI의 --now 생략 시 실제 UTC 시각을 사용한다. stdout은 JSON 하나다. FAIL이면 종료코드 1, PASS/PENDING이면 0이다. 출력 파일을 쓰지 않는다.

반환 키: `status`, `rule_states[A|B][rule]`의 `state/reason`, 실제 계산한 `counts`, `errors`, `review_requests`, `outcomes`. 추가 감사 정보는 `exclusions`, `response_records`이다. 각 응답의 모든 원본 파일 경로와 바이트 SHA256을 `response_records[].versions`에 보존한다. JSON 손상·경로 이탈·누락·잘못된 schema·미래시각·비유한수·중복키·무효 리뷰는 errors와 FAIL을 만든다. QA·이전 노출·중단·잘못된 원답·충돌 ID는 명시 제외한다. 오류가 없더라도 증거가 부족하면 PENDING이다. 명시적 rejected receipt는 연결된 규칙을 REJECTED로 둔다.

## 인벤토리: evidence.json

아래 여섯 키를 정확히 사용한다. 배열 원소는 **inputs 기준 상대 파일 경로 문자열**이다. 모든 참조 경로는 resolve하여 inputs 내부인지 검사한다. 절대 경로·드라이브 경로·상위 디렉터리 이탈·외부를 향한 symlink/junction·중복 인벤토리 경로를 허용하지 않는다. inputs 이외의 policy·작품·protocol은 project-root 안에서 읽는다. 단, protocol의 이미지 상대 경로는 기존 protocol 위치 기준이며 실제 policy 작품 파일과 일치해야 한다.

```json
{
  "schema_version": 1,
  "responses": [],
  "reviews": [],
  "screenshots": [],
  "metrics": [],
  "history": []
}
```

본문 JSON은 객체여야 한다. 본문에 schema_version을 넣는다면 정수 1만 허용한다. NaN·Infinity·overflow float·중복 JSON 키를 허용하지 않는다. 모든 시간은 offset을 포함한 ISO8601이다. 응답의 consent/events 및 알 수 없는 중첩 *_at도 미래시각 검사를 받는다. review 시각은 실제 검토 대상의 updated_at/captured_at/period_end/observed_end보다 빠를 수 없다.

QA 표지(`record_kind: "qa"`, `qa: true`, `synthetic: true`, `test_only: true`, `automated: true`)와 명시적 AI/DOM/자동화 provenance는 실제 관객에서 제외한다. receipt의 auto_pass 등 자동 PASS findings도 외부 리뷰로 인정하지 않는다. source_note에 합성·QA·DOM 실험 출처가 명시되면 명시 제외한다. QA를 participant로 바꾸어 실제 사람으로 제출하면 안 된다.

## 관객 응답과 버전

responses에는 기존 관객 수집기가 내보낸 participant JSON 파일을 등록한다. 고정 설계는 P01~P12, A6/B6, 목표 3000ms(허용 2800~3800), 회상 최소 24시간, 내부 목표 5/6이다. policy와 protocol의 현재 작품 해시가 실제 파일과 일치해야 한다.

기존 `관객검증/응답_집계.py`의 `protocol_from`, `inspect_record`를 그대로 호출한다. 최초 원답 6개 필드는 `product/event/scene/share_recipient/share_sentence/share_reason`, 회상 2개는 `brand/scene`이다. 유효 필드가 없거나 이전 노출·중단·불일치한 이미지이면 사람 리뷰가 있어도 제외한다. 실제 사람 확인은 별도 human source_attestation이 있어야 계산된다. AI semantic_coding은 사람 출처 확인을 대체하지 않는다.

동일 ID의 최초 waiting 파일과 complete 회상 파일은 다음 조건에서 최신 회상 파일로 병합한다. consent·screen·노출정보·최초 원답을 포함하여 `updated_at/stage/recall_raw_answers/recall_submitted_at/events` 이외의 모든 값이 정확히 같아야 한다. 최초본은 회상 미입력, 최신본은 24시간 회상 품질 검사를 통과해야 한다. events는 기존 배열을 그대로 보존한 접두사 뒤에 recall_opened/recall_submitted/download/revisit만 추가할 수 있다. 추가 이벤트 시각은 이전 updated_at 이후여야 한다. 완전히 동일한 복사본은 인원을 중복 계산하지 않고 모든 파일 해시를 남긴다. 다른 변경이나 부적합 버전이 섞인 충돌 ID는 모든 버전을 제외한다.

보수적으로 **선택된 최신 응답 파일의 해시**에 source_attestation 및 semantic_coding을 다시 연결한다. 이전 최초본의 receipt를 변경된 회상 파일에 자동 전용하지 않는다. 이 때문에 회상 수집 후 기존 최초 측정 검토를 다시 연결해야 할 수 있다.

## 공통 review receipt

reviews에는 아래 객체 JSON의 상대 경로를 등록한다. 예제의 꺾쇠 placeholder를 실제 해시로 교체해야 한다. 예제 텍스트는 schema 설명이며 증거가 아니다.

```json
{
  "review_kind": "source_attestation",
  "entry": "A",
  "artifact_sha256": "<현재 A 작품 실제 바이트 SHA256 64자리>",
  "target_sha256": "<검토한 입력 파일 실제 바이트 SHA256 64자리>",
  "reviewer": {"id": "<책임 있는 검토자 ID>", "kind": "human"},
  "reviewed_at": "2026-11-03T10:00:00Z",
  "verdict": "verified",
  "findings": {},
  "source_note": "<실제 모집·현장·원자료 대조의 근거와 위치 설명>"
}
```

review_kind는 source_attestation/semantic_coding/generation_capture/social_metrics/longitudinal, reviewer.kind는 human/AI, verdict는 verified/rejected/pending만 허용한다. source_attestation만 반드시 **human**이다. verified source_attestation은 source_note를 근거로 실제 관객 출처를 확인했다는 사람의 선언이다. 이를 자동 생성하지 않는다. target은 실제 인벤토리에 있고 종류·entry가 맞아야 한다. 현재 작품과 다른 안/이전 이미지 해시의 receipt는 사용하지 않는다. source_note·reviewed_at·파일 해시는 필수다. 같은 대상에 명시적 rejected가 있으면 성공 receipt로 덮지 않는다. 같은 대상의 verified findings가 충돌해도 검증 완료로 처리하지 않는다. 서로 다른 의미 코딩 필드를 담은 receipt는 같은 대상 해시 안에서만 합칠 수 있다.

리뷰가 없거나 pending/불완전이면 `review_requests`에 review_kind·entry·rule·현재 작품 해시·target_sha256·target_file·필요 findings를 반환한다. 이 목록은 검토 요청 자료이며 메시지를 외부에 전송하지 않는다.

## 의미 코딩과 측정/효과 구분

semantic_coding은 같은 응답 파일을 target으로 쓴다. findings의 각 코딩값은 bool이며, false도 유효한 측정이다. 각 값에 대한 quotes는 관련 원답의 **정확한 비어 있지 않은 부분문자열**이어야 한다. 다음 예시는 형식 설명이다. 실제 원답에 없는 예시 문장을 제출하지 않는다.

```json
{
  "product_understood": false,
  "event_understood": false,
  "share_intent": false,
  "brand_recalled": false,
  "relationship_recalled": false,
  "quotes": {
    "product_understood": {"field": "product", "text": "제품을 모르겠습니다"},
    "event_understood": {"field": "event", "text": "행사를 모르겠습니다"},
    "share_intent": {"field": "share_reason", "text": "관심이 없습니다"},
    "brand_recalled": {"field": "brand", "text": "기억 안남"},
    "relationship_recalled": {"field": "scene", "text": "기억 안남"}
  }
}
```

quote는 위 객체, 원답 부분문자열 문자열, 또는 이들로 구성한 비어 있지 않은 배열을 허용한다. product는 product, event는 event, 공유 의향은 share_recipient/share_sentence/share_reason, brand는 회상 brand, relationship은 회상 scene에서 인용해야 한다. 최초 scene을 회상 scene으로 전용하지 않는다. 문자열 매칭은 인용의 무결성 검사이며 의미의 옳음을 자동 판정한 것이 아니다.

- L02: 양 안 합계 12명(A6/B6)의 정상 최초 응답, human 출처, product_understood/event_understood 검토가 완료되면 측정 VERIFIED. 효과는 `outcomes.by_arm[arm]`의 개별·공동 positive/percent/target_met에 따로 출력한다.
- L03: 해당 안 6명의 최초 원답 6필드·human 출처·share_intent 코딩이 완료되면 VERIFIED. 공유하지 않음도 측정 완료이며 실제 공유 행동과 다르다. `actual_sharing_from_intent`는 항상 null이다. 실제 shares는 L05에서 기간별로만 보고한다.
- L04: 해당 안 6명의 24시간 회상·human 출처·brand_recalled/relationship_recalled 코딩이 완료되면 VERIFIED.
- L06: 양 안 A6/B6의 human 출처와 최초 이해/공유 코딩이 완비되고 고정 protocol 조건을 충족하면 파일럿 비교자료 VERIFIED. 회상 비교 가능성은 별도 recall_comparable이다. 경쟁대회 전체 최고·승리·수상 확률을 계산하지 않는다.

분모는 실제 human 검토+코딩 완료 인원이다. 0명이면 percent는 null이다. 6명이 완비되기 전에는 target_met도 null이다. 공동 understanding_joint/recall_joint는 두 코딩값 모두 true인 인원이다. 목표 5/6은 내부 목표이며 모집단 추정이나 유의성 보장이 아니다.

## J08: 생성 화면 캡처

screenshots 배열에는 **캡처 설명 JSON 파일** 경로를 등록한다. 실제 캡처 PNG/JPEG 등 파일을 capture_path에 inputs 상대 경로로 적는다. 캡처의 실제 디코딩/파일 존재를 확인하며 표의 8/8 체크만으로 닫지 않는다.

```json
{
  "entry": "A",
  "artifact_sha256": "<현재 작품 SHA256>",
  "source_sha256": "<policy.assets.A.source_sha256와 실제 생성원본 SHA256>",
  "capture_path": "captures/A-generation.png",
  "captured_at": "2026-11-03T09:00:00Z"
}
```

generation_capture receipt의 target_sha256는 설명 JSON이 아니라 **캡처 이미지 파일 바이트**의 SHA256이다. findings에는 service_visible/prompt_visible/result_visible/entry_matches 네 값 모두 true가 필요하다. 현재 작품 파일·현재 생성원본 파일·실제 캡처 파일·리뷰가 모두 있어야 J08 VERIFIED다. 이미지 디코딩은 화면 진위를 확정하지 않는다.

## L05: 플랫폼 관측치

metrics 배열에는 다음 JSON 경로를 등록한다. social_metrics receipt의 target은 이 JSON 파일이다. 값이 없는 지표는 0으로 채우지 않고 null과 사유를 유지한다. 측정 종류·기간별 파일을 따로 보고하며 서로 더하거나 공유 의향과 섞지 않는다.

```json
{
  "entry": "A",
  "artifact_sha256": "<현재 작품 SHA256>",
  "platform_url": "https://example.org/post/actual-post",
  "period_start": "2026-11-01T00:00:00Z",
  "period_end": "2026-11-02T00:00:00Z",
  "measurements": {"impressions": 25, "reach": null, "shares": 0, "saves": null, "reactions": 2},
  "unavailable_reasons": {"reach": "플랫폼 미제공", "saves": "비공개"}
}
```

다섯 measurements 키가 모두 필요하다. 각 값은 nonnegative int 또는 null이며 bool·음수·실수는 허용하지 않는다. null인 각 키에는 비어 있지 않은 unavailable_reasons 문자열이 있어야 한다. URL은 http/https여야 한다. 시작은 끝보다 늦을 수 없고 미래 기간은 안 된다. verified social_metrics receipt와 source_note로 실제 플랫폼 출처를 검토해야 VERIFIED다. 지표값이 null이라는 사실 자체는 플랫폼이 그 지표를 제공하지 않는다는 명시이며 0건을 뜻하지 않는다.

## L08: 독립 장기 관측

history 배열에는 다음 JSON 경로를 등록하고 그 JSON 바이트 해시를 target으로 longitudinal receipt를 작성한다.

```json
{
  "entry": "A",
  "artifact_sha256": "<현재 작품 SHA256>",
  "source_url": "https://example.org/independent-observation",
  "observed_start": "2026-01-01T00:00:00Z",
  "observed_end": "2026-11-01T00:00:00Z",
  "independence_note": "<제3자 독립 관측임을 뒷받침하는 근거>",
  "long_term_basis": "<장기 관측이라고 판단한 맥락과 근거>"
}
```

observed_start < observed_end, 시각은 미래가 아니어야 한다. longitudinal findings의 independent/long_term/not_self_generated 모두 true와 verified receipt가 필요하다. 일정 개월수를 새 기준으로 강제하지 않으며 실제 독립성·장기성은 검토자의 책임 있는 판단으로 남긴다. 자체 생성물이나 예약 계획을 독립 관측으로 세지 않는다.
