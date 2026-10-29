# 햇반 30주년 AI 공모전 '갓 지은 AI디어' 출품 기획 (2026-10-30)

마감: **2026-11-13(금) 23:59**. 권장 제출일: **11/12**. 11/8에는 영양 음원 마감이 있으니 그 주는 피한다.

## 0. 사용자가 할 일 (순서대로)

1. 로고 PNG를 받는다. 주최 측 드라이브 → `02_이미지_4x5` 폴더에서 `red-red`, `red-white` 두 파일을 받는다.
   - 드라이브 주소: https://drive.google.com/drive/folders/1NYhmzXCRen1FLyXHd2Pvu9BDifkuZNPH
2. 인스타그램 공개 계정을 준비한다. 비공개 계정은 접수가 인정되지 않는다.
3. 인스타에서 `#햇반AI공모전`을 5분쯤 훑어본다. 이미 올라온 출품작과 겹치는 아이디어를 거르기 위해서다.
   - 이 세션의 크롬에는 인스타 로그인이 없어 내가 확인하지 못했다.
4. 출품작을 만든다(2~4절). 만들면서 **2절의 증빙 자료를 그때그때 캡처**한다.
5. 마무리 합성: `python compose.py fit 원본.png 로고.png 결과.png` (7절).
6. 업로드 → 드라이브 공유 → 구글 폼 제출(8절). 제출 전에 9절 체크리스트를 확인한다.

**여러 편을 내도 된다.** 출품 수는 제한이 없고, 본선에는 그중 최고 점수 1편만 올라간다.
그래서 추천 1(필수)과 추천 2(권장)를 내고, 시간이 남으면 추천 3을 낸다.

## 1. 공고 원문 핵심 (OG-02)

출처와 확인 날짜(모두 2026-10-30):
- 구글 폼 본문: https://docs.google.com/forms/d/e/1FAIpQLSfbdn6XHYLkAMdo2-K8EN--QB6H2RYXYV9snzJCvPRe-KBQpA/viewform
- 유의사항 PDF(11쪽, 폼에 링크됨): https://drive.google.com/drive/folders/1F_lErI0IBk7XY-qrRfaAH5FBkUzHpX4V
- 로고 가이드 PNG

**심사 기준**
| 항목 | 비중 |
|---|---|
| 창의성 | 35% |
| 주제 적합성(햇반 브랜드와의 연관성 포함) | 20% |
| AI 활용도 | 20% |
| 완성도 | 10% |
| 온라인 인기투표 | 15% (본선 TOP10만) |

**선정 구조**
- 1차 심사: 심사위원 85점을 100점으로 환산해 TOP10을 뽑는다. 두 부문을 합쳐서 뽑는다.
- TOP10 안에서는 최종 순위대로 대상 1, 최우수 3, 우수 5, AIdea상 1이다.
- **나머지 AIdea상 6명은 본선에 못 간 작품 가운데 1차 점수 순이다.** → 1차 점수가 전체 16위 안이면 최소 50만 원이다.
- 인기투표는 11/23~26 13:00이다. 부정 투표는 집계에서 뺀다.

**형식·제출**
- 이미지는 1:1(1080×1080) 또는 4:5(1080×1350)이다. 단일 이미지나 캐러셀로 낸다.
- 개인 인스타·유튜브에 전체 공개로 올리고 @hetbahn.30years 계정 태그를 한다.
- 해시태그 #햇반 #햇반AI공모전 #갓지은아이디어를 단다.
- 원본과 AI 제작 증빙을 개인 구글 드라이브에 올리고 '링크가 있는 모든 사용자'로 공유한다.
- 폼에는 SNS 링크·드라이브 링크·AI 서비스 명칭·제목·설명(500자 이내)을 넣는다. **셋 중 하나라도 빠지면 제외된다.**
- 게시물은 11/27까지 지우거나 비공개로 바꾸면 안 된다.

**로고**
- 제공된 정식 파일을 1회 이상 쓴다.
- AI로 만들거나 바꾸거나 훼손하면 안 된다.
- 위치는 왼쪽 위다. 규격별 PNG(1080×1350 투명, 왼쪽 위에 로고)를 그대로 얹는다.
- 색은 배경에 따라 잘 보이는 쪽을 쓴다. 배경색이 계속 바뀌면 red-red다.

**AI**
- 상업적 이용이 가능한 생성형 AI 서비스만 쓴다. 서비스 명칭을 적는다.
- 'AI 서비스 내 제작 과정 또는 히스토리 캡처본'을 낸다.

**제외·수상 취소 사유 (발표 후에도 회수)**
- 제3자 권리 침해, 표절·도용 이의 제기
- 실존 인물의 얼굴·음성·성명
- **유명인 사진을 참고 자료로 넣거나 프롬프트에 이름을 쓰는 것. 결과물에 이름이 안 보여도 해당한다.**
- 특정 개인 식별 정보
- 직업·공신력 있는 인물 사칭
- 추천·보증·거짓·과장 등 표시광고법 위반 소지
- 허위 정보 제출
- 실제 출시 제품이나 확정 기능으로 오인될 표현은 지양하라고 되어 있다.

**권리**
- 본선 진출작·수상작은 발표일부터 3년 동안 주최사가 광고·홍보에 쓴다.
- 발췌·편집·수정·재구성과 문구·로고·음악 추가가 가능하다.
- 이용 대가는 상금에 포함된다. 추가 대가는 없다.
- 저작권 양도 문구는 없다(이용 허락).

**상금**
- 12월 중 국내 계좌로 지급한다. 제세공과금은 본인 부담이다.
- 신분증 사본·계좌 정보를 요청할 수 있다.
- 기한 안에 내지 않으면 수상이 취소된다.

## 2. 전략

- **캐러셀 4장**으로 낸다.
  - 1장은 한눈에 아이디어가 보이는 장면이다.
  - 2장은 원리, 3장은 쓰는 순간들, 4장은 맺음말이다.
  - 창의성(35)과 주제 적합성(20)은 아이디어가 '읽혀야' 점수가 나서, 단일 이미지보다 유리하다.
- **"새 기능 하나 + 쓰는 순간 하나"**만 보여 준다. 기능을 여러 개 늘어놓는 출품작과 차별된다.
- **브랜드 연결:** 세 추천 모두 햇반의 핵심 이미지를 쓴다. '갓 지은 밥의 김'과 '햇(그해 처음 난)'이다.
- **AI 활용도(20):** 여러 도구를 쓴 과정을 증빙에 보여 준다.
  - 발상 정리(대화형 AI) → 이미지 생성 → AI 편집(손글씨를 김서림으로) → 업스케일
  - 사람이 한 일(손글씨, 문구, 구도 선택)도 기록한다.
- **이미지 속 용기에는 햇반 글자·로고를 그리지 않는다.** 흰 무지 용기로 만든다. AI가 그린 로고는 'AI 생성 로고'로 제외될 수 있다. 브랜드는 공식 로고 PNG로만 넣는다.
- **한글 문구는 사람이 합성한다.** `compose.py --text`를 쓴다. AI가 그린 한글은 자주 틀린다.
  - 예외: 추천 1의 손글씨는 AI 편집으로 '김서림'처럼 만든다. 이때도 글씨 자체는 사용자가 쓴다.
- **인기투표(15):** TOP10에 들면 지인에게 투표를 부탁한다. 투표 구매나 자동 투표는 하지 않는다(집계 제외·수상 취소 사유).

## 3. 아이디어 10개와 클리셰 점검

참가자 다수는 ChatGPT·Gemini에 아이디어를 물을 것이다. 그때 먼저 나올 법한 것을 클리셰로 본다(추정이며, 실제 출품작 표본은 사용자가 3번 단계에서 확인한다).

**클리셰 목록:**
- 우주·화성 햇반, 3D 프린터·AI 맞춤 영양 햇반, 알약·큐브·캡슐 밥
- 자가 발열 용기, 먹는 용기·생분해 용기, 화면 달린 스마트 용기
- 로봇·드론 배송, 홀로그램·가상현실 가족 식사, 자율주행차 안 식사
- 이색 맛(민트초코·마라), 1996→2056 타임라인, 반려동물 햇반

| # | 주제 | 아이디어 | 점검 | 판정 |
|---|---|---|---|---|
| 1 | 01 | **갓 지은 편지**: 데우면 뚜껑 안쪽 김서림이 보낸 사람의 손글씨가 된다 | 숨은 메시지 포장은 '열 반응 잉크'(Ardagh 캔, 전자레인지 포장 특허)로 있다. 김서림으로 손글씨를 드러내는 식품 뚜껑은 검색에 없다. 김서림 글씨는 이야기 관습이라 보호 대상이 아니다. 제목 동명작 검색 0건 | **추천 1** |
| 2 | 01 | **스물네 번의 갓 지은 계절**: 24절기 한정 햇반. 계절이 흐려진 미래에 밥으로 계절을 센다 | 24절기 즉석밥·구독은 검색 0건. 잡곡 확대는 CJ의 실제 전략 방향(30주년 간담회)과 맞는다 | **추천 2** |
| 3 | 02 | **일곱 시, 동네에 구름이 뜬다**: 1인 가구 아파트. 창마다 데운 햇반의 김이 지붕 위 한 구름으로 모이고, 금요일엔 옥상 식탁에 모인다 | 가상 식사 클리셰는 피했다. '한 지붕 ○ 식구' 제목은 유명 드라마 제목을 비튼 것이라 버렸다(OG-06·09) | 추천 3 (선택) |
| 4 | 02 | 2분 안부: 전자레인지 2분 동안 부모와 통화하는 새 의례 | 미래성이 약하다 | 보류 |
| 5 | 01 | 주먹밥 뚜껑: 뚜껑을 뒤집어 누르면 삼각 주먹밥 틀이 된다 | 실제 제품으로 오인될 수 있다. 주먹밥 틀은 흔하다 | 보류 |
| 6 | 01 | 우리 집 밥맛 코드: 집집마다 밥 질기·누룽지 정도를 코드로 물려준다 | 'AI 맞춤' 클리셰와 가깝다 | 보류 |
| 7 | 02 | 내 논 한 평: 원격으로 논을 키워 내 쌀 햇반을 받는다 | 중국 '게임으로 키우면 진짜 과일 배송'(핀둬둬)과 구조가 겹친다 | 탈락 |
| 8 | 02 | 30년 밥상 3폭(1996·2026·2056) | 타임라인 클리셰. 2026년을 외롭게 그리면 브랜드에 불리하다 | 탈락 |
| 9 | 01 | 바다 논 햇반(내염성 벼) | 중국 '해수 벼'가 이미 실재한다. 라이프스타일이 약하다 | 탈락 |
| 10 | 02 | '짓다' 연작(밥·집·이름·시를 짓다) | 말장난은 좋지만 장면이 흩어져 완성도 위험이 크다 | 보류 |

## 4. 추천 1 — 갓 지은 편지 (주제 01, 이미지 캐러셀 4장, 4:5)

**한 줄**
- 전자레인지에 데우면 뚜껑 필름 안쪽에 맺힌 김이 보낸 사람의 손글씨가 된다.
- 김이 걷히면 사라지는, 한 끼 분량의 편지다.

**원리(오인 방지용 '상상' 표기와 함께 쓴다)**
- 필름 안쪽에 물이 잘 맺히는 코팅과 김서림 방지 코팅을 글씨 모양으로 나눠 인쇄한다. 그러면 김이 글씨 모양대로만 맺힌다.
- 김서림 방지 뚜껑 필름은 실제 시장이 있다. 이 아이디어는 그 원리를 거꾸로 쓴다.

**차별점(OG-32)**
- 기존 숨은 메시지는 '판촉 문구 + 열 반응 잉크'다.
- 이 작품은 '보내는 사람이 직접 쓴 손글씨 + 갓 지은 밥의 김'이다. 장치(②)와 결말(④) 층위에서 다르다.

**문구 주의**
- "밥은 먹고 다니냐"는 유명 영화 대사라 쓰지 않는다(OG-06).
- 아래 문구는 모두 새로 쓴 일상 문장이다. 바꿔도 되지만 유명 대사·가사·광고 문구는 피한다.

| 장 | 장면 | 합성 문구(`--text`) |
|---|---|---|
| 1 | 밤의 원룸. 손이 필름 모서리를 들자 김서림 손글씨가 보인다: "늦게 와도 따뜻하게 먹어. 엄마" | 없음 (손글씨만) |
| 2 | 원리 3단 그림: ① 앱에 손글씨 ② 필름 안쪽에 보이지 않게 인쇄 ③ 데우면 글씨가 맺힘 | "앱에 쓴 손글씨가, 데우는 순간 김으로 떠오릅니다" |
| 3 | 2×2 칸. 고시원 수험생("다 왔다, 조금만 더"), 해외 기숙사("거기도 밤이지? 여긴 아침이야"), 할머니 부엌("할머니, 토요일에 갈게요"), 야근 사무실("먼저 가서 미안, 먹고 해") | 없음 |
| 4 | 위에서 본 빈 용기와 걷혀 가는 김. 글씨가 흐려지는 중이다 | "김이 걷히면 사라지는, 한 끼 분량의 편지" + `--note` |

**손글씨 만드는 법**
- 사용자가 종이에 직접 쓰고 사진을 찍는다. 사람의 기여이면서 독창성 증빙이 된다.
- 그다음 둘 중 하나로 김서림처럼 만든다.
  - (가) Gemini나 ChatGPT 이미지 편집에 1장 원본과 손글씨 사진을 함께 넣는다. 지시: "Make this handwriting appear as condensation on the inside of the clear film lid, following its curve. Keep everything else unchanged."
  - (나) 포토피아(무료 웹)에서 손글씨 레이어를 '스크린' 혼합, 흐림 1~2px, 불투명도 60%로 얹는다.
  - (가)가 AI 활용도 증빙에 유리하다.

**프롬프트 — 1장 (GPT 이미지·Gemini·FLUX schnell용 자연어)**
```
Photorealistic macro close-up, vertical 4:5. A plain white rectangular microwavable rice tray with a clear plastic film lid, just heated, gentle steam rising. The inside of the clear film is fogged with condensation, except for a short handwritten note: the letters appear as clear strokes through which glossy cooked white rice is visible. A young adult's hands, face not visible, lift one corner of the film. Small studio apartment at night, warm desk lamp light from the right, soft bokeh of an open microwave's interior light in the background. The upper-left quarter of the frame is a calm, dark, uncluttered wall. No brand names, no logos, no printed text. 50mm macro, shallow depth of field, quiet and intimate mood.
```
- 한글 손글씨는 비워 두고 만든 뒤 위 방법으로 넣는다. 이미지 모델이 한글을 틀리게 그릴 수 있기 때문이다.

**ComfyUI (SDXL 1.0 계열) — 1장**
- 크기 896×1120, 이후 업스케일 → compose가 1080×1350으로 맞춘다.
- 긍정: `photo, macro close-up, plain white rectangular microwave rice tray, clear plastic film lid half peeled, condensation fog on inside of film, gentle steam, glossy cooked white rice, hands lifting film corner, small studio apartment at night, warm desk lamp, bokeh, cozy, shallow depth of field, 50mm, highly detailed, dark plain wall in upper left`
- 부정: `text, letters, watermark, logo, brand, label, face, deformed hands, extra fingers, lowres, blurry, oversaturated, plastic look`

**2장 (원리 그림)**
```
Clean soft 3D clay-style illustration on an off-white background, vertical 4:5, three steps arranged top to bottom with gentle red accents: (1) a smartphone showing a blank handwriting pad with a stylus, (2) a clear film lid with a faint invisible pattern being printed on its inside, (3) a heated white rectangular rice tray whose film fogs up except for handwritten strokes. Simple arrows between steps, generous white space, empty upper-left corner. No text, no logos, no brand names.
```
- 단계 번호와 설명은 compose로 넣거나, 포토피아에서 S-Core Dream 글꼴로 넣는다.

**3장 (네 장면, 각각 만든 뒤 `compose.py grid --cols 2`)**
- 공통 꼬리말: `..., a plain white rectangular rice tray with a fogged clear film lid showing faint handwritten strokes, warm light, photorealistic, faces turned away or out of focus, no text, no logos`
- 장면별 머리말:
  - `a cramped study cubicle late at night, a student with stacked workbooks`
  - `a small dormitory room abroad at dawn, a foreign city skyline through the window`
  - `a modest old Korean kitchen in the afternoon, an elderly woman's hands`
  - `an empty office at night, one desk lamp on, a person still working`
- 노인·학생은 가상 인물이다. 실존 인물의 사진을 참고로 넣지 않는다.

**4장**
```
Top-down photo, vertical 4:5, an emptied plain white rectangular rice tray on a wooden desk, its clear film lid set beside it with the last traces of condensation fading, a few rice grains, a spoon, soft morning light, lots of calm empty space in the upper-left and lower third. No text, no logos.
```

## 5. 추천 2 — 스물네 번의 갓 지은 계절 (주제 01, 캐러셀 4장)

**한 줄**
- 계절의 경계가 흐려진 미래에도 밥은 계절을 기억한다.
- 입춘부터 대한까지 보름마다 그 절기의 곡물·나물로 지은 한정 햇반이 나온다. 24개를 모으면 한 해 달력이 된다.
- 절기마다 친구들과 그 밥을 데워 먹는 '절기 밥상'이 새 모임 문화가 된다.

**24절기 밥 제안 (색이 봄 초록 → 여름 노랑 → 가을 금빛·붉은색 → 겨울 검붉은색으로 흐르게 고름. ★는 잘 알려진 풍습과 맞는 것)**
- 봄:
  - 입춘 냉이 보리밥
  - 우수 달래밥
  - 경칩 쑥밥
  - 춘분 완두콩밥
  - 청명 미나리밥
  - 곡우 곤드레밥
- 여름:
  - 입하 녹두밥
  - 소만 강낭콩밥
  - ★망종 햇보리밥
  - ★하지 감자밥
  - 소서 옥수수밥
  - 대서 기장밥
- 가을:
  - 입추 조밥
  - 처서 수수밥
  - 백로 밤밥
  - 추분 은행밥
  - 한로 버섯밥
  - 상강 적미밥
- 겨울:
  - 입동 무밥
  - 소설 귀리밥
  - 대설 흑미밥
  - ★동지 팥밥
  - 소한 콩밥
  - 대한 찰흑미 오곡밥

건강 효능(면역·혈당 등)은 쓰지 않는다. 표시광고법 위반 소지가 있다.

| 장 | 장면 | 합성 문구 |
|---|---|---|
| 1 | 6열×4줄 달력 격자. 24개의 흰 무지 용기를 위에서 본다. 줄마다 한 계절이고 색이 흐른다 | 없음 |
| 2 | 입춘 냉이 보리밥 근접. 옆에 빈 한지 카드, 꽃눈 달린 가지 | "입춘 · 냉이 보리밥" |
| 3 | 12월 저녁. 창밖엔 눈 대신 비가 온다. 친구 넷이 낮은 상에 둘러앉아 동지 팥밥을 데워 먹는다 | "눈 대신 비가 온 동짓날, 우리는 팥밥으로 겨울을 셉니다" |
| 4 | 곡물이 흩어진 리넨 위 맺음 카드 | "계절이 흐려져도, 밥은 계절을 기억합니다" + `--note` |

**1장 만드는 두 방법**
- (가) 한 장에 통째로 생성: GPT 이미지가 격자를 비교적 잘 그린다. 개수가 24개인지 꼭 센다.
- (나) 24개를 따로 생성해 `compose.py grid 절기01.png ... 절기24.png 1장_바탕.png --cols 6 --top 160`로 배치하고, 이어서 `fit`으로 로고를 얹는다.
  - 개수와 정렬이 정확하다.
  - 같은 시드·같은 조명에서 곡물만 바꾸면 통일감이 생긴다.
  - ComfyUI 일괄 생성 기록이 AI 활용도 증빙이 된다.
- 낱개 프롬프트:
```
Top-down photo of a plain white rectangular microwavable rice tray, film removed, filled with freshly cooked {GRAINS}, glossy grains, faint steam, on pale beige linen, soft daylight from the upper left, centered, square framing, no text, no logo.
```
- `{GRAINS}` 예:
  - `barley rice mixed with chopped shepherd's purse greens`
  - `white rice with yellow corn kernels`
  - `rice with red adzuki beans`
  - `black rice`

**3장**
```
Cinematic photo, vertical 4:5, a small cozy apartment in the near future on a late December evening; through the window rain falls on a city instead of snow. Four friends of different ages sit on the floor around a low wooden table, each with a plain white rectangular rice tray of red bean rice, steam rising, warm lamp light, relaxed laughter, faces turned away or softly out of focus. Upper-left area is a plain dark wall. No text, no logos.
```

## 6. 추천 3 — 일곱 시, 동네에 구름이 뜬다 (주제 02, 선택)

- **한 줄**
  - 혼자 사는 집이 대부분인 미래의 아파트다.
  - 저녁 일곱 시, 집집마다 데운 햇반의 김이 창문에서 피어올라 지붕 위 한 구름으로 모인다.
  - 금요일엔 각자의 햇반을 들고 옥상 긴 식탁에 모인다.
  - '식구(食口)'가 '같은 시각에 밥을 먹는 사람'으로 넓어진다.
- **약점:** 햇반만의 기능이 약하다. 추천 1·2를 다 낸 뒤 시간이 남을 때만 만든다.
- **1장 프롬프트**
```
Wide cinematic shot at blue hour, vertical 4:5, a mid-rise apartment building in a near-future Korean city with dozens of warmly lit windows. From many windows thin wisps of steam rise from people heating rice trays inside; the wisps drift upward and merge into one soft white cloud hovering above the rooftop, where a long wooden table with string lights waits. Gentle, hopeful mood. Upper-left area is clear sky. No text, no logos.
```

## 7. 도구·라이선스와 마무리 합성

| 도구 | 쓰는 곳 | 상업 이용 | 폼 기재 예 |
|---|---|---|---|
| ChatGPT(GPT 이미지) | 1·3·4장, 절기 격자 | OpenAI 약관상 출력물 권리는 사용자에게 있다 | ChatGPT |
| Gemini / Google AI Studio | 손글씨 김서림 편집 | 무료·Pro 앱 이미지에 눈에 보이는 워터마크가 붙을 수 있다 → AI Studio를 쓰거나 결과에 표식이 없는지 확인 (미확인) | Google Gemini |
| ComfyUI | 낱개 일괄 생성·인페인팅·업스케일 | **모델 라이선스가 기준이다.** SDXL 1.0 = CreativeML Open RAIL++-M(상업 가능), FLUX.1 [schnell] = Apache 2.0(가능), **FLUX.1 [dev]는 비상업 라이선스라 쓰지 않는다.** 커뮤니티 파생 모델은 모델 페이지의 라이선스를 캡처해 둔다 | ComfyUI(Stable Diffusion XL 1.0) |

**마무리 합성 (`compose.py`, 이 폴더)**
- `pip install pillow`가 먼저 필요하다.
- 실행: `python compose.py fit 원본.png 햇반30주년_로고가이드_이미지_4x5_red-red.png 1장.png`
  - 가운데 기준으로 4:5로 자르고 1080×1350으로 맞춘 뒤 공식 로고 PNG를 그대로 얹는다.
  - 로고 자리 배경이 복잡하거나 어두우면 경고한다. 어두우면 red-white도 얹어 보고 고른다.
- `--text "문구"`: 아래쪽 띠에 한글 문구를 넣는다. 글꼴은 S-Core Dream 5(상업 무료)다.
  - '—' 같은 특수 기호는 글꼴에 없을 수 있으니 쉼표를 쓴다.
- `--note`: 오른쪽 아래에 "※ 공모전을 위해 상상한 콘셉트이며 실제 제품이 아닙니다." 를 넣는다. 4장(마지막 장)에 넣는다.
- `grid`: 여러 장을 칸으로 배치한다. 위쪽 160px은 로고 자리로 비운다.

## 8. 업로드·제출 문구

**제목**
- 추천 1: "갓 지은 편지"
- 추천 2: "스물네 번의 갓 지은 계절"

**폼 '출품작 설명' — 추천 1 (공백·줄바꿈 포함 376자)**
> 전자레인지에 데우면 뚜껑 안쪽에 맺힌 김이 보낸 사람의 손글씨가 되는 햇반을 상상했습니다. 보내는 사람이 앱에 손으로 쓴 짧은 글을, 김이 맺히는 부분과 맺히지 않는 부분으로 나뉜 투명 코팅으로 필름 안쪽에 인쇄합니다. 데우기 전에는 보이지 않다가 갓 지은 밥의 김이 오르는 순간에만 글씨가 떠오르고, 식으면 사라집니다. 한 끼 분량의 편지입니다.
> 혼자 사는 자녀, 시험을 앞둔 수험생, 멀리 사는 할머니처럼 떨어져 밥을 먹는 사람에게 안부를 밥과 함께 보낼 수 있습니다. 30년 동안 햇반이 밥 짓는 수고를 덜어 주었다면, 앞으로의 햇반은 그 밥에 마음을 실어 보내는 그릇이 될 수 있다고 생각했습니다.
> 손글씨는 직접 쓰고, AI로 장면을 만들고 김서림으로 합성했습니다.

**폼 '출품작 설명' — 추천 2 (공백·줄바꿈 포함 321자)**
> 계절의 경계가 흐려진 미래에도 밥은 계절을 기억할 수 있다고 상상했습니다. '절기 햇반'은 입춘부터 대한까지 24절기마다 그 절기에 어울리는 곡물과 나물로 지은 한정 햇반입니다. 입춘에는 냉이 보리밥, 하지에는 감자밥, 동지에는 팥밥처럼 보름에 한 번 새 밥이 나오고, 24개를 모으면 한 해 달력이 됩니다.
> 사람들은 날짜 대신 밥으로 계절을 셉니다. 절기마다 친구들과 그 절기의 햇반을 데워 함께 먹는 '절기 밥상'이 새로운 모임이 됩니다. 지난 30년 동안 햇반이 밥을 쉽게 만들었다면, 다음 30년에는 잊혀 가는 계절을 밥상 위에 다시 지어 줄 수 있다고 생각했습니다.

**인스타 캡션 (추천 1 예)**
```
갓 지은 편지
데우면 뚜껑 안쪽의 김이 보낸 사람의 손글씨가 되는 햇반을 상상했습니다.
김이 걷히면 사라지는, 한 끼 분량의 편지.
※ 공모전을 위해 상상한 콘셉트이며 실제 제품이 아닙니다.
사용한 AI: ChatGPT, Google Gemini, ComfyUI(Stable Diffusion XL)

@hetbahn.30years
#햇반 #햇반AI공모전 #갓지은아이디어
```
- 게시물 사진에도 @hetbahn.30years를 '사람 태그'로 단다. 캡션 멘션만으로 인정되는지는 공고에 명시가 없으니 둘 다 한다.

**'사용한 AI 서비스 명칭'**
- 실제로 쓴 것만 적는다. 예: `ChatGPT(GPT 이미지), Google Gemini, ComfyUI(Stable Diffusion XL 1.0)`

## 9. AI 제작 증빙 (구글 드라이브)

**폴더 구조 (작품마다 하나)**
```
갓지은AI디어_갓지은편지/
  01_최종본/            1장.png ~ 4장.png (1080x1350, 로고 포함), 로고 얹기 전 원본
  02_제작과정_캡처/      AI 서비스 화면 캡처: 프롬프트와 결과가 함께 보이게, 날짜가 보이게
  03_중간산출물/        후보 이미지, 버린 시안, ComfyUI 워크플로 JSON
  04_사람이_한_일/      손글씨 원본 사진, 문구 초안
  05_제작기록.pdf       아래 표
```

**제작기록 표**
| 장 | 단계 | 날짜·시각 | 도구(요금제) | 모델·버전 | 프롬프트 전문 | 시드·설정 | 결과 파일 | 사람이 한 일 |
|---|---|---|---|---|---|---|---|---|
| 1 | 장면 생성 | | | | | | | 구도 선택 |
| 1 | 손글씨 합성 | | | | | | | 손글씨 작성 |

**지킬 것**
- 공유 설정은 '링크가 있는 모든 사용자'로 한다. **시크릿 창에서 링크를 열어** 실제로 보이는지 확인한다.
- 생성하는 동안 화면 녹화를 켜 두면 의혹이 생겼을 때 가장 강한 증거가 된다(OG-45).
- 유명인 사진·이름을 넣은 프롬프트가 기록에 하나도 없어야 한다.

## 10. 제출 전 체크리스트

**이미지**
- [ ] 1080×1350이다. 모든 장 왼쪽 위에 공식 로고 PNG가 있고, 잘 보인다.
- [ ] 용기·화면에 AI가 그린 햇반 글자·로고·가짜 상표가 없다.
- [ ] 실존 인물로 보이는 얼굴이 없다. 손가락·글자 깨짐이 없다.
- [ ] 마지막 장에 '실제 제품이 아닙니다' 안내가 있다. 효능·최고·1위 같은 과장 표현이 없다.

**업로드**
- [ ] 인스타 공개 계정에 올렸고, 캡션에 @hetbahn.30years와 #햇반 #햇반AI공모전 #갓지은아이디어가 있다.
- [ ] 사진에도 계정 태그를 달았다.
- [ ] 드라이브 링크를 시크릿 창에서 확인했다. 01~05 폴더가 다 있다.

**폼**
- [ ] 출품 주제 01을 골랐다(추천 1·2). 유형은 이미지다.
- [ ] 제목을 넣었다. 설명은 500자 이내다.
- [ ] 동의 항목 7개를 모두 확인했다.

**제출 후**
- [ ] 11/27까지 게시물을 지우거나 비공개로 바꾸지 않는다. 11/23 TOP10 발표를 확인한다.

## 참고: 같은 날 마감인 다른 이미지 공모전

**AI 활용 옥외광고 간판 디자인 공모전** (한국옥외광고센터)
- 출처: 씽유 요약 https://thinkyou.co.kr/contest/66692/ (원문 미확인)
- 마감 11/13, 총 1,500만 원, 12팀
- 내는 것:
  - 신청서(기획 의도·프로세스별 프롬프트와 이미지)
  - 간판 시안(도면 + 주·야간 시뮬레이션, 300dpi PDF)
  - 원본 파일(psd 등)
- 수상 후보는 얼굴·목소리 없는 작업 화면 녹화(5분 이내)를 낸다 → 방구석으로 가능하다.
- 할 일: 햇반을 다 낸 뒤 여력이 있으면 공식 홈페이지(ai간판디자인공모전.com)에서 요강 PDF를 확인한다.
