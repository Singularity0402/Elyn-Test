import json, hashlib, html, zipfile
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent

def read(p): return p.read_text(encoding='utf-8-sig')
def write(p,s): p.write_text(s,encoding='utf-8',newline='\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,o): write(p,json.dumps(o,ensure_ascii=False,indent=2)+'\n')
wrong=ROOT/'AI_무문구原본검토.json'
if wrong.exists(): wrong.rename(ROOT/'AI_무문구원본검토.json')
assets=json.loads(read(ROOT/'assets.json'))['entries']
qa=json.loads(read(ROOT/'독립파일검사.json'))
assert qa['status']=='PASS_FILES_ONLY' and not qa['errors']

write(ROOT/'선행검색_추가.md','''# 추가 선행 검색과 판정 변화
2026-11-11. 검색 결과가 없다는 사실을 최초·고유성의 증거로 삼지 않는다. 검색에서 발견한 외부 이미지·문구는 생성 참조로 사용하지 않았다.

실행 검색어: `"갓 지은 편지" 햇반 김서림 그림`; `"내 밥을 환영합니다" 햇반 식당`; `"floating rice" paddy farm freshwater`; `condensation hidden message food packaging drawing rice heat reveal`; `bring your own rice restaurant corkage Japan Korea 햇반 반입`; `floating paddy rice freshwater sea agriculture platform`; `"밥을 데웠더니" "그림" 햇반`; `"내 밥을 환영합니다"`; `"지을 자리를 찾습니다" 밥`; `"밥은 빨리 준비해도"`.

- A: 온도에 반응하는 포장/숨은 메시지는 이미 존재하는 기술 범주라는 검색 단서가 나왔다. 이를 발명했다는 주장을 하지 않는다. 가족의 그림·햇반 가열·안부 발견의 표현이 이번 기획의 범위이며, 직접 소재를 선정하거나 검증하지 않았다. 가까운 광고 구도 전체를 차용하지 않았다.
- I: 외부 음식 반입/술 콜키지는 기존 관행이다. 검색의 상당수는 밥 반입과 무관한 주류 안내로, 밥 반입 운영의 증거에서 제외했다. 개인의 밥을 격식 있게 환대하는 햇반 제휴 문화라는 제안으로 범위를 제한한다. 새로운 시장과 수익을 입증하지 않았다.
- J: [TheNavalArch의 2023년 저자 구상](https://thenavalarch.com/floating-rice-fields-the-quest-for-solutions-to-combat-drought-floods-and-rising-sea-levels/)을 직접 열었다. 바다 위 플랫폼·담수 공급·벼 재배가 가까운 선행이다. **해상 논 자체의 기술 독창성 주장은 철회하며, J는 주력보다 낮은 비전형 추가안이다.** 이 자료의 낙관적 경제·재난 효과를 사실로 가져오지 않는다.
- [Widodo 외 원 연구](https://jurnal.fp.unila.ac.id/index.php/JTP/article/download/8281/pdf)는 이탄 습지의 뗏목 재배를 다룬다. 바다 위 미래 시설의 안전·원가·생산성 검증으로 전용하지 않는다.
- [CTCN 부유식 농업](https://www.ctc-n.org/technologies/floating-agricultural-systems)은 침수 지역의 기존 농업 방식 설명이다. J의 신기술 인증이 아니다.
- K: 카피 검색은 관련 없는 결과가 중심이었다. 발견 실패를 고유성의 증거로 삼지 않고, 기획상 브랜드 기여 약함으로 이미 제외했다.

전체 광고·특허·상표를 망라한 법적 조사 또는 자유실시 판정이 아니다. 공식 브랜드·서비스·글꼴 조건과 선행 표현 검색의 범위는 구분했다.
''')

report=read(ROOT/'선별_기획_검수보고.md')
if '## 마지막 원본 검토와 선행 재분류' not in report:
 report+='''
## 마지막 원본 검토와 선행 재분류
별도 새 AI에는 기획서·조판본 없이 A8/I3/J2/K2 생성원본만 제공했다. 원답은 `AI_무문구원본검토.json`이다. A8의 종이/덮개 그림 대응, I의 가방/용기/쟁반, J의 바다/벼/식탁이 보인다고 답했다. 다만 A8은 미리 인쇄된 그림, I는 직원이 밥을 주는 역방향 전달, J는 비현실적 합성 풍경으로도 읽힐 수 있다고 지적했다. 이 잔여 해석을 감추거나 실제 관객의 이해율로 수치화하지 않았다. 카피와 상태 표찰은 이 해석 범위를 좁히는 역할이다.

추가 검색에서 바다 위 담수 벼 재배의 직접적인 2023년 구상이 확인됐다(`선행검색_추가.md`). J를 기술 발명이나 즉시 상품화 안으로 내세우지 않는다. **주력은 A8+A6, 추가 출품은 I, 비전형 추가안은 J** 순으로 선별한다. J는 원래 제품 중심 120규칙의 ‘배경을 지워도 남는 새 행동’, ‘제품 동작과 결과의 직접 시각 연결’을 충족한 것으로 세지 않았다. K는 7개 기획 항목 불통과로 제외한다. 공식 주제02의 폭넓은 미래상 허용과 내부 전용 매뉴얼의 엄격한 제품 기준을 혼동하지 않는다.

독립 파일 검사는 4개 PNG/JPG 디코드·규격, 공식 로고 원본/합성, 글자 대비, 설명 글자 수, 9개 원생성 파일, 기존 A~H 8개 불변을 확인했다. 오류0이며 `독립파일검사.json`에 실제 해시를 기록했다. 이 파일 통과는 기획·관객·실물 성능까지 통과했다는 뜻이 아니다.
'''
write(ROOT/'선별_기획_검수보고.md',report)

# Each rule gets an explicit reviewed decision; arithmetic only assembles the table.
# These are internal procedural/visual decisions, never measured audience responses.
base_rows='''A01|PASS|assets.json의 주제와 설명을 공식 폼의 미래제품/미래생활에 대조했다.
A02|PASS|각 4:5 단일 이미지에 사건·제안 카피가 있다. A8+A6 캐러셀 결합은 별도 편집안이며 단일이미지 매뉴얼의 검증 범위를 확대하지 않는다.
A03|PASS|독립파일검사.json에서 PNG/JPG 모두1080×1350으로 직접 판독했다.
A04|PASS|공식 전체화면4:5 로고 템플릿을 좌표0,0에 원비율 합성했다. 출력검수/독립파일검사 참조.
A05|PASS|공식소스 해시 대조, 불투명픽셀 불일치0, 반투명 합성 오차최대1을 확인했다.
A06|PASS|9개 실제프롬프트/참조는 자체 생성사진이다. 실존인물·유명인·작가스타일을 입력하지 않았다.
A07|PASS|11/11 실제생성 원본·프롬프트와 선행검색_추가.md를 대조했다. 전세계 독점성 인증으로 세지 않는다.
A08|PASS|실사용서비스를 OpenAI Codex 내장 이미지 생성으로 기재했다. 약관/글꼴 공식 조건을 대조하고 별도원본 자산을 묶지 않았다.
A09|PASS|이미지 하단과 설명에 미래상/실제품·실서비스 아님을 명시했다.
A10|PASS|공식제외사항과 화면·캡션·자발공유 계획을 대조했다. 위반표현/부정참여 수단을 넣지 않았다.
B01|PASS|각 기획심사와 선별보고의 생활 긴장·중심이득 한 문장을 확인했다.
B02|PASS|기획서 없는 첫검토와 무문구원본검토가 각각 장면의 단서를 지목했다. 아래 작품별 단서 참조.
B03|PASS|A는 안부발견, I는 주식취향 환대, J는 다음쌀의 재배장소, K는 식사시간으로 초점을 하나씩 지정했다.
B04|PASS|선별보고의 상품화 경로/남은입력에서 소재·운영·공급의 숨은 가정을 분리했다. 검증된 효과로 주장하지 않는다.
B05|PASS|반찬·식당요리·농업/물류·업무인계의 별도 필요를 설명에서 인정한다. 밥만으로 전체 문제가 해결된다고 쓰지 않았다.
B06|PASS|각 기획의 새로운 설정과 기존행동의 차이를 기록했다. 실제 존재하는 관행·기술을 최초라고 쓰지 않았다.
B07|PASS|받는사람/취향선택 손님/농업주체의 행동을 중심으로 하며 취약성을 결핍 구경거리로 만들지 않았다.
B08|PASS|덮개열기·가방과외식·벼와점심·헤드셋내려놓기라는 일상 단서가 있다.
B09|PASS|폐허·굶주림·공포 대신 온기·환대·밝은재배풍경을 쓴다.
B10|PASS|현재제품과 미래발현/제휴/재배/인계 설정을 제출설명과 고지에서 구분했다.
C01|PASS|아래 작품별 직접연결을 반례검사했다. 밥/포장을 제거하면 그림대응 또는 용기전달 사건이 사라진다.
C02|PASS|밥가열/주식반입/쌀생산의 장면을 업종치환 반례와 비교했다. 선별보고와 기획반론 참조.
C03|PASS|개봉·김·한공기/곡물·쌀원료 중 실제 화면에 쓰인 제품자산을 지정했다.
C04|PASS|다른즉석밥도 가능한 범주이득이며 독점기술·세계최초를 주장하지 않았다.
C05|PASS|CJ공식 브랜드의 제품군을 확인했다. 특정질환·품종·가격·수치 특성을 추가하지 않았다.
C06|PASS|치료/혈당/탄소/재활용/수익/생산성의 입증 수치를 넣지 않았다. J의 농업성능도 미검증으로 명시했다.
C07|PASS|로고 외에 쌀밥·개봉필름·한공기 포맷과 다음식생활 제안을 연결했다. 연결 강도의 차이는 선별 순위에 반영했다.
C08|PASS|밥과 포장에 기괴한 인체·오염·위협적 장치를 붙이지 않았다. 원본 시각검토 참조.
C09|PASS|공식30주년 표시는 보조이며 다음제품/문화/공급의 제안이 중심이다.
C10|PASS|다른곡물 취향·가족·식습관을 열등하게 묘사하지 않았다.
D01|PASS|사전심사기준과 선별보고에 기구추가·운송관·카페·기존H2의 탈락/통합 이유를 남겼다.
D02|PASS|편지·반입식당·재배장소·업무인계라는4개 전제를 만들었다. 수정9회를9개기획으로 세지 않았다.
D03|PASS|두 제안자의 외부음식/카페 수렴을 고유성증거로 삼지 않고 I에 통합했다.
D04|PASS|선행검색_추가.md의 한/영 기능·장면·카피 검색을 실행했다. J 직접선행 발견으로 발명주장을 배제했다.
D05|PASS|미검색을 최초증명으로 부르지 않는다. 선행검색의 범위와 제외결과를 남겼다.
D06|PASS|외부광고 구도·인물·대사 이미지를 참조 입력으로 쓰지 않았다. 실제생성기록 참조.
D07|PASS|그림출현/개인밥접객/바다위논이라는 의문과 답을 문구·장면으로 연결했다. 인쇄·역방향·합성 오독도 기록했다.
D08|PASS|색/소품변형이 아니라 안부발견 또는 반입환대의 행동/관계를 바꿨다. J/K는 아래 별도판정이다.
D09|PASS|‘밥을 데우면 네 그림이 나타난다’/‘내 밥을 가져가도 환대한다’/‘다음쌀을 기를 곳을 넓힌다’로 한 관계씩 기술했다.
D10|PASS|독창성 차이를 기능·행동·관계로 구분하고 익숙한 선행과 약점을 기록했다. 역사적 초대작으로 자체인증하지 않았다.
E01|PASS|발견하다/건네다/기르다/쉬며먹다의 중심동사 하나씩 지정했다.
E02|PASS|두상태와종이그림/가방에서쟁반으로 전달이 같은 화면에 있다. J/K는 직접인과 미충족을 별도판정했다.
E03|PASS|별도순서도 대신 열린덮개·종이그림·열린가방·성숙한벼의 현재흔적으로 전후 설정을 암시했다.
E04|PASS|A는 그림발현, 나머지는 제휴문화/재배공간/업무인계 한 설정씩이다. 텔레포트·마법자동조리 등을 추가하지 않았다.
E05|PASS|A7작은용기→A8동일크기, J1큰컵→J2얕은컵으로 수정했다. 마지막 원본검토에 명백한 비례오류 보고 없음.
E06|PASS|인물은 카메라를 보며 모델연기하지 않고 덮개·밥·접객·식사에 손을 쓴다.
E07|PASS|그림을발견/취향을건네/함께점심먹는 행동을 사용했다. 웃는표정만으로 결과를 설명하지 않는다.
E08|PASS|신청서 명사를 화면과 대조했다. J의 수확후 공급경로는 화면에서 직접증명되지 않는 미래구상으로 명시했다.
E09|PASS|별도AI가 인쇄그림/직원의제공/바다합성/업무석식사라는 오독을 제시했다. 수정된것과 남은것을 보고서에 구분했다.
E10|PASS|두그림의대응/가방밥과은쟁반/바다와논/밥과헤드셋이라는 시각관계를 한 줄씩 남겼다. 실제지연회상 아님.
F01|PASS|기존 기획_제품화_심리.md의 출처·대상·측정·가설·한계5칸을 참조했다. 이번적용은 선별보고의 가설이며 관객측정치0이다.
F02|PASS|발견·환대·긍정적 미래를 목표로 하며 불쾌/위협/질병자극을 쓰지 않았다.
F03|PASS|무문구원본검토에서 그림대응·가방/쟁반·바다/논의 단서가 확인됐다. 전체기능의 자발이해를 증명하지는 않는다.
F04|PASS|선별보고에 가족/취향동행/농업미래관심자에게 보낼 문장을 각각 썼다.
F05|PASS|공개는 관계/취향/미래관 표현, 개인전송은 가족그림/동행의취향/아이의다음밥이라는 수신자 가치를 구분했다.
F06|PASS|덮개와김/외식가방/벼와흰밥의 반복생활 단서를 지정했다.
F07|PASS|온기·환대·밝은전망 중 하나를 중심감정으로 두고 공포/유머/분노를 동시에 섞지 않았다.
F08|PASS|공유/투표계획에 죄책감·가짜갈등·비방·강요를 넣지 않았다.
F09|PASS|기존논문을 이번작품의 공유/구매/우승 증명으로 전용하지 않았다.
F10|PASS|제작자반복검토·초기AI·후속AI·새무문구AI의 노출범위를 구분해 기록했다.
G01|PASS|A는그림대응, I는용기전달, J는논과바다를 주목표로 하고 카피와인물을 보조로 둔다. K는 의미위계약점으로 제외했다.
G02|PASS|원본과기록의360폭 미리보기를 직접 만들고 최종선별 한눈에와 별도AI 후속검토로 확인했다.
G03|PASS|원본과기록의 흑백360 미리보기를 만들었다. 용기외곽/그림밝기/물과재배구획을 확인했다.
G04|PASS|출력검수의 텍스트경계/충돌과 공식로고 영역을 확인했다. J고지바탕과 I상단제목 위치를 수정했다.
G05|PASS|그림-용기/가방-전달/바다-논-식탁의 핵심단서가 프레임 안에 남는다.
G06|PASS|카피→핵심관계→로고의 경로는 연출 의도다. 검토자 서술과 분리하며 시선추적 실험으로 부르지 않는다.
G07|PASS|상단 조판은 대략3분의1이하이고 아래 장면의 면적을 유지한다. J는 하늘여백을 이용한다.
G08|PASS|가까운손/한공기와 큰공간을 함께읽도록 시점을 정했다. A7/J1비례오독은 재생성했다.
G09|PASS|A/I의짙은남색·따뜻한음식, J의하늘/바다청색·황금벼·흰밥으로 재질과 식사를 분리했다.
G10|PASS|전체 원본/360폭/손부분을 초기·후속AI가 확인했고 마지막 원본검토도 했다. 파일해상도를 별도판독했다.
H01|PASS|I1큰콩질감을 I2에서 쌀알로 바꿨다. 선택원본에서 지은밥 형태를 시각검토했다. 시식/식감실험 아님.
H02|PASS|A의김은 용기부근의 반투명 온기이다. 독가스/연소연기로 연출하지 않았다. 나머지는 과장된김 없음.
H03|PASS|필름/용기와밥의 경계가 보인다. A의큰곡면은 가상포장형태로 기록하며 실제필름복원력 검증 아님.
H04|PASS|K1상체절단을 K2로 고쳤다. 최종원본4개 별도검토에서 명백한 인체오류 보고 없음.
H05|PASS|밥 위 미니인물·먼지·폐기물 등을 배치하지 않았다.
H06|PASS|따뜻한실내/창빛/밝은야외라는 주광원과 용기·손·식탁의 가림/그림자를 대조했다. 시각검토이며 광학실측 아님.
H07|PASS|의도한 미래발현/부유재배와 우발적콩질감/비례/신체잘림을 분리해 후자는 고쳤다.
H08|PASS|쌀·종이·투명덮개·은쟁반·바다·벼의 재질을 원본에서 확인했다. 미세재질의 실물성능 증명 아님.
H09|PASS|식탁/쟁반 접촉을 확인하고 J인물은 난간안에 둔다. 플랫폼의 구조안전 인증으로 부르지 않는다.
H10|PASS|원생성1122×1402와 최종1080×1350을 구분했다. 원생성4K라고 쓰지 않았다.
I01|PASS|각 메인카피는 온기발현/반입선언/재배장소/식사여유의 한 주장이다.
I02|PASS|새 별도AI가 기획서·조판본 없이 선택원본4개를 열어 사건단서를 기술했다. AI_무문구원본검토.json 참조.
I03|PASS|단순물체이름 대신 안부/환대/다음세대/식사시간의 의미를 더했다.
I04|PASS|카피 구절을 검색하고 가까운명문/대사/가사를 차용하지 않았다. 검색완전성·독점성을 주장하지 않는다.
I05|PASS|정식한글 조판의 최종래스터를 읽고 assets.json의 원문과 대조했다.
I06|PASS|고지26px·제목22px, 대비최저4.5유지. 원본/360후속검토했다. 고지는 작은보조글이며 메인카피와 동급크기 아님.
I07|PASS|제목·설명·SNS카피가 같은 미래설정을 말한다. I무료암시를 없애고 J실제성능 오인을 제한했다.
I08|PASS|AI/역사/혁신 등 자기찬사 대신 구체적 장면·제안을 설명했다.
I09|PASS|설정연도를 증거로 쓰지 않았다. J다음30년은 브랜드의 지향 기간이지 성능검증이 아니다.
I10|PASS|4개설명264/235/219/227자로500자이하이며 주제·서비스·태그를 함께 제공했다.
J01|PASS|기존규칙120을 바꾸지 않고 사전심사기준·각 기획심사를 생성 전에 작성했다. 적용범위 차이는 별도보고했다.
J02|PASS|9개 실행 프롬프트원문·소스경로를 실제생성기록.json과 txt에 보존했다.
J03|PASS|generation_plan.json에 각 수정의 목적/탈락이유/선택상태를 기록했다.
J04|PASS|사진영역은9번 실제 이미지생성/편집으로만 바꿨다. 조판·공식로고는 별도합성이다.
J05|PASS|공식로고와 한글은 이미지생성 후 정식원본/글꼴로 조판했다.
J06|PASS|새폴더에서 작업하고9개생성원본을 모두 보존했다. 독립검사에서 이전A~H8개해시불변을 확인했다.
J07|PASS|ComfyUI·다른서비스·실제사람/실물시험을 실행했다고 적지 않았다. 동일서비스AI검토로 명시했다.
J08|PENDING|실제서비스 화면캡처 파일이 아직 없다. 사용자에게 생성 대화화면 캡처가 필요하며 기록문서는 그 대체가 아니다.
J09|PASS|공개대상/제출묶음에서 별도공식로고·폰트원본·.private를 제외한다.
J10|PASS|출력검수·독립파일검사·실제생성기록·검토대상연결과 제출문구를 연결했다.
K01|PASS|기획/시각첫검토/기획반론/후속/새무문구검토를 다른작업으로 수행하고 원답을 보존했다.
K02|PASS|초기시각검토는 기획서를 보지 않았고 새무문구검토는 조판본·기획서 없이 원본만 봤다.
K03|PASS|검토지시는 강제성공/강제탈락 없이 관찰·오독·강약을 묻는다. 실제요청과 원답을 구분해 보존했다.
K04|PASS|I제목/중복용기·J비례·K인체오류와 K브랜드기획약점을 구분했다. K는 미세수정 반복대신 제외했다.
K05|PASS|A7/I2/J1/K1의 구체적결함을 기록하고 변경후결과를 검토했다. 남은기획반론은 통과로 감추지 않았다.
K06|PASS|같은서비스의 별도AI이며 인간표본·교차서비스·통계실험으로 세지 않았다.
K07|PASS|이 표는4작각120개 규칙ID의 중복/누락을 프로그램으로 검사한다. 상태가 있는것과 통과는 다르다.
K08|PASS|PASS/FAIL/PENDING/NA를 따로집계한다. 미관측을 통과에 합산하지 않는다.
K09|PASS|원래120규칙은 불변이다. J/K미충족과 A캐러셀의 추가구성을 사후통과로 덮지 않았다.
K10|PASS|내부추천과 외부수상결과를 구분한다. 수상확률이나 확정대상 수치를 만들지 않았다.
L01|PASS|관객관측_사전계획.md에 실행전 표본24명/배정/3초노출/원답/기준/24시간회상을 고정했다. 실행0이다.
L02|PENDING|새로운 실제관객의3초노출 원답이 없다. AI서술을 원답으로 대체하지 않는다.
L03|PENDING|실제관객의 자발공유 이유 원답이 없다. 선별보고의 문장은 제작가설이다.
L04|PENDING|실제24시간 지연회상 원답이 없다.
L05|PENDING|게시 후 플랫폼 노출·공유·저장·반응 숫자가 없다. 게시/제출도 수행하지 않았다.
L06|PENDING|같은조건의 실제관객 비교관측이 없다. AI내부순위를 모집단 우위로 부르지 않는다.
L07|PASS|공식투표단계에서 자발안내만 쓰는 계획을 준비했다. 실행·지지 확보를 주장하지 않는다.
L08|PENDING|장기회상·자발재해석·문화인용의 독립기록이 없다. 당일 자체검토로 역사성을 인증하지 않는다.
L09|PASS|이미지 재생성은 구체적내부결함만 고쳤다. 외부관측의 공백을 재생성으로 해결했다고 쓰지 않았다.
L10|PASS|제작완료·내부선별·실제화면캡처/게시/접수대기를 구분하고 허위우승/바이럴 표현을 쓰지 않았다.'''
common={}
for line in base_rows.splitlines():
 k,s,e=line.split('|',2); assert k not in common; common[k]=(s,e)
rules=json.loads(read(BASE/'quality_2026-11-02/규칙120.json'))['rules']
assert set(common)=={r['id'] for r in rules} and len(common)==120
scenes={
 'A8':'同크기 두 용기의 무그림/김서림그림과 앞 종이그림을 대응시켰다. 인쇄그림 오독은 남고 온도발현을 실물증명한 장면은 아니다.',
 'I':'가방을 연 손님/밀봉잡곡 한공기/직원쟁반으로 관계를 집중했다. 무문구에서는 전달방향이 양쪽으로 읽힐 수 있어 메인카피가 방향을 정한다.',
 'J':'바다·독립재배구획·벼·난간안식사를 한장에 배치했다. 담수 정체와 미래제품 공급은 문구에 의존한다. 가까운 해상논 선행이 있어 기술발명으로 세지 않는다.',
 'K':'업무석/밥/헤드셋만으로는 쉬는시간이 보장되지 않고 일반업무복지광고에 더 가깝다는 반론 때문에 제외했다.'}
scenes['A8']=scenes['A8'].replace('同크기','같은 크기')
overrides={
 'J':{'D08':('FAIL','미래배경을 가리면 평범한 야외식사만 남는다. 원래 전용매뉴얼의 새생활행동 기준은 충족했다고 세지 않고 비전형 추가안으로 낮췄다.'),'E02':('FAIL','논→도정/취반/포장→미래햇반 공급의 중간단계는 화면에 없다. 설명상의 미래구상이며 직접시각인과 통과로 세지 않았다.')},
 'K':{k:('FAIL',e) for k,e in {
  'B04':'제품의 빠른준비가 충분한식사시간을 보장하지 않는다. 별도업무인계합의가 핵심이다.',
  'B06':'사진은 현재의 업무석식사로도 읽혀 새생활행동이 분명하지 않다.',
  'C01':'햇반을 다른식사로 바꿔도 업무인계/복지의 중심사건은 남는다.',
  'C02':'업무복지/인계시스템 광고로 더 자연스럽게 읽힌다는 두별도검토가 있었다.',
  'C07':'용기 외에 햇반만의 서사연결이 약하다. 로고로 기획약점을 보완하지 않는다.',
  'D08':'배경의 화면문구를 가리면 현재의 책상식사와 새행동 차이가 약하다.',
  'E02':'인계완료는 모니터 문장으로만 제시되며 제품행동과 충분한식사시간 사이의 인과가 화면에 성립하지 않는다.'}.items()}}
rows=[]
for a in assets:
 for rule in rules:
  s,e=overrides.get(a['key'],{}).get(rule['id'],common[rule['id']])
  rows.append({'work':a['key'],'rule_id':rule['id'],'rule':rule['rule'],'status':s,'evidence':e,'scene_scope':scenes[a['key']]})
for a in assets:
 rr=[r for r in rows if r['work']==a['key']]
 assert len(rr)==120 and len({r['rule_id'] for r in rr})==120
counts={a['key']:dict(Counter(r['status'] for r in rows if r['work']==a['key'])) for a in assets}
audit={'date':'2026-11-11','scope':'Internal rule-by-rule review; not audience/product/winning validation','original_rules_sha256':sha(BASE/'quality_2026-11-02/규칙120.json'),'counts':counts,'reviewed_rows':len(rows),'rows':rows}
dump(ROOT/'규칙별감사.json',audit)
md=['# 규칙별 내부 감사','원래120규칙을 변경하지 않고4작480행의 상태와 근거를 기록했다. 내부 문서/시각 판단의 PASS는 실제 관객·실물·수상 검증이 아니다. J의2개·K의7개 불통과를 따로 기록한다. 실제화면캡처1개와 외부관측6개는 각작7개 PENDING이다.','', '|작품|PASS|FAIL|PENDING|선별|','|---|---:|---:|---:|---|']
for a in assets:
 c=counts[a['key']];md.append(f"|{a['title']}|{c.get('PASS',0)}|{c.get('FAIL',0)}|{c.get('PENDING',0)}|{ {'A8':'주력','I':'추가출품','J':'비전형 추가안·매뉴얼 부분 미충족','K':'제외'}[a['key']]}|")
for a in assets:
 md+=['',f"## {a['key']} {a['title']}",scenes[a['key']],'','|ID|상태|규칙|근거|','|---|---|---|---|']
 for r in rows:
  if r['work']==a['key']:md.append(f"|{r['rule_id']}|{r['status']}|{r['rule']}|{r['evidence']}|")
write(ROOT/'규칙별감사.md','\n'.join(md)+'\n')

# Freeze review scope without assigning a new file hash to reviews of older versions.
bindings={'date':'2026-11-11','initial_reviews':'Initial visual/strategy files relate to pre-final I2/J1 and prior typography. No current-final hash is retroactively assigned.','followup':'AI_후속검토.json relates to final I3/J2 raster files below; A8/A6/K not re-reviewed in that followup.','wordless':'AI_무문구원본검토.json opened only the four selected render sources, no brief or composed copy.','entries':[]}
for a in assets:
 src=ROOT/'원본과기록'/f"{a['key']}_선택생성원본.png"
 bindings['entries'].append({'key':a['key'],'final_png':a['stem']+'.png','final_sha256':sha(ROOT/(a['stem']+'.png')),'source':str(src.relative_to(ROOT)),'source_sha256':sha(src),'followup_raster_review':a['key'] in ['I','J'],'wordless_source_review':True})
dump(ROOT/'검토대상연결.json',bindings)

carousel='''# 갓 지은 편지 — 2장 캐러셀 제출안
주제: 01. 미래의 햇반을 만들어밥
순서: 01_상태비교.png → 02_안부의순간.png. 같은 작품의 두 장으로 게시한다. 두개의 별도 신제품이 아니다.

## 작품 설명
밥을 데우면 보내온 그림이 뚜껑의 김서림 속에 드러나는 미래의 햇반을 상상했습니다. 첫 장은 같은 크기의 두 예시로 가열 전 무그림과 가열 후 그림 발현의 설정을 비교하고, 둘째 장은 한 공기를 열며 보낸 사람의 안부를 발견하는 순간에 집중했습니다. 종이와 필름의 그림을 연결해 식사의 온기를 관계의 온기로 확장했습니다. AI 미래 제품 상상이며, 발현 소재·맞춤 제작·제품 연결·가열 성능은 검증 전입니다.

## AI 활용
OpenAI Codex 내장 이미지 생성 기능으로 장면을 생성·수정했습니다. 한글과 공식 제공 로고는 별도 조판했습니다. 실제 제작 대화 화면 캡처를 별도로 첨부해야 합니다.

## SNS 문구
밥을 데웠더니, 네 그림이 피었다.
네가 보낸 그림이, 밥의 온기 속에 나타나는 햇반.
AI로 만든 미래 제품 상상이며 실제 출시 제품이 아닙니다.

@hetbahn.30years
#햇반 #햇반AI공모전 #갓지은아이디어
'''
write(ROOT/'A_캐러셀_제출문구.md',carousel)
assert len(carousel.split('## 작품 설명\n')[1].split('\n\n')[0])<=500

readme='''# 햇반 추가 출품 후보 — 2026-11-11
기존 우수작을 보존하고 새 기획/반대심사/재제작으로 선별한 묶음이다. **주력은 갓 지은 편지(A8+A6), 다음은 내 밥을 환영합니다(I), 비전형 추가안은 내일의 논(J)** 이다.

[세 작품 한눈에](최종선별_한눈에.png) · [이미지 갤러리](gallery.html) · [기획/수정/제외 보고](선별_기획_검수보고.md) · [규칙별 내부 감사](규칙별감사.md) · [파일 검사](독립파일검사.json)

|작품|최종 이미지|제출 문구|선별 이유|
|---|---|---|---|
|갓 지은 편지|[A8 PNG](A8_갓지은편지_변화.png) · [JPG](A8_갓지은편지_변화.jpg) · [보존 A6](../audit_2026-11-03/A_갓지은편지.png)|[2장 캐러셀용](A_캐러셀_제출문구.md) · [A8 단독용](A8_제출문구.md)|A8은 상태 비교, A6는 안부를 발견하는 감정 장면. 같은 작품으로 결합|
|내 밥을 환영합니다|[PNG](I_내밥을환영합니다.png) · [JPG](I_내밥을환영합니다.jpg)|[문구](I_제출문구.md)|내 취향의 밥을 가져가는 외식을 격식 있는 접객으로 표현. 기존 제품/식당 제휴로 시범 운영 설계부터 가능|
|내일의 논|[PNG](J_내일의논.png) · [JPG](J_내일의논.jpg)|[문구](J_제출문구.md)|원료 공급의 미래를 보여주는 비전형. 가까운 해상논 선행이 있어 기술 발명·즉시 상품화 주력으로 내세우지 않음|

밥 먹는 동안(K)은4:5 조판본까지 만들었으나 제품 인과/새 행동이 약해 제외했다. [기존 B 스물네 장의 계절](../audit_2026-11-03/B_스물네장의계절.png)와 이전 C~H·H2도 덮어쓰지 않았다.

## 제작과 검수
- 실제 이미지 생성/편집9회, 보존원본9개, 새조판4작, 이번 출품 묶음3기획. A8은 기존 편지안의 개선이며 별도 새기획으로 부풀리지 않는다.
- 기획서 없는 시각 검토·기획 반론·I3/J2 후속 확인·새 무문구 원본 검토를 구분했다. 모두 같은 서비스 내 별도 AI이며 인간 표본이 아니다.
- 파일 검사는4작 PNG/JPG·1080×1350·공식로고·대비·설명제한·원본9개·기존8개 불변에서 오류0. 규칙별 감사에는 불통과/미관측도 그대로 남겼다.
- 최종 PNG와 JPG를 제공한다. 원생성1122×1402를 최종1080×1350으로 조판했으며4K 원생성이 아니다.

## 제출할 때
1. 편지는 A8→A6 순의 한 캐러셀, I와 J는 각각 별도 작품으로 준비한다. 각 문구 파일에서 주제·설명·서비스·SNS 태그를 가져온다.
2. 실제 이미지 제작 대화 화면을 캡처해 함께 첨부한다. 원본과프롬프트 기록은 실제 서비스 화면 캡처의 대체물이 아니다.
3. 공개 SNS 게시와 접근 가능한 작품 파일 링크를 마련해 공식 폼에 접수한다. **이 세션은 게시·폼 접수를 하지 않았다.**

[공식 폼](https://docs.google.com/forms/d/e/1FAIpQLSfbdn6XHYLkAMdo2-K8EN--QB6H2RYXYV9snzJCvPRe-KBQpA/viewform)을11/11 다시 대조했다. 단일/캐러셀·다작 허용 범위와 인당 최고1작의 TOP10 진출 제한을 구분한다. 출품 수를 수상확률로 환산하지 않는다.

`햇반_추가출품_3작.zip`은 이 폴더에 만들어지는 로컬 제출 준비 묶음이다. `finish_round.py`로 같은 파일 구성을 다시 만들 수 있다. 공개 Git에는 압축파일을 중복 저장하지 않고 이미지·문구·실제생성·검수 기록을 저장한다.
'''
write(ROOT/'README.md',readme)

cards=[]
for a,rank in zip(assets[:3],['01 · 주력','02 · 추가 출품','03 · 비전형 추가안']):
 key=a['key']; extra=''
 if key=='A8': extra='<p><a href="../audit_2026-11-03/A_갓지은편지.png">둘째 장: 보존한 A6의 감정 장면 보기</a></p>'
 cards.append(f'<article><p class="rank">{rank}</p><h2>{html.escape(a["title"])}</h2><a href="{a["stem"]}.png"><img src="{a["stem"]}.png" alt="{html.escape(a["title"])}"></a><p>{html.escape(a["headline"][0]+" "+a["headline"][1])}</p><p><a href="{a["stem"]}.png">PNG 원본</a> · <a href="{a["stem"]}.jpg">JPG</a> · <a href="{("A_캐러셀_제출문구.md" if key=="A8" else key+"_제출문구.md")}">제출 문구</a></p>{extra}</article>')
write(ROOT/'gallery.html','''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>햇반 추가 출품 후보</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f1e9;color:#152c37;font-family:system-ui,sans-serif;line-height:1.6}main{max-width:1420px;margin:auto;padding:40px 24px}h1{font-size:32px;margin:0}h2{font-size:23px;margin:0 0 18px}.intro{max-width:850px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;margin-top:32px}article{background:white;padding:20px;border-radius:12px}img{width:100%;height:auto;display:block}.rank{color:#8a3030;font-weight:700;margin:0 0 4px}a{color:#184d70}footer{margin-top:32px;padding-top:20px;border-top:1px solid #b7b7ad}@media(max-width:900px){.grid{grid-template-columns:1fr}main{padding:24px 14px}}</style><main><h1>햇반 추가 출품 후보</h1><p class="intro">기존 편지안의 이해를 보강하고, 식당 문화와 쌀 공급의 미래를 추가했습니다. 편지는 두 장의 한 작품, 나머지는 각각 별도 작품으로 준비했습니다.</p><div class="grid">'''+''.join(cards)+'''</div><footer><p><a href="햇반_추가출품_3작.zip">제출 준비 묶음 받기</a> · <a href="선별_기획_검수보고.md">의도·수정·선별 보고</a> · <a href="규칙별감사.md">검수 기록</a> · <a href="../audit_2026-11-03/B_스물네장의계절.png">보존한 스물네 장의 계절</a></p><p>이미지 제작·내부 검토 완료. 실제 제작 화면 캡처 첨부·SNS 게시·공모전 접수는 대기 상태입니다.</p></footer></main></html>''')

# Bundle selected finals, not excluded works or standalone licensed assets.
files=[]
def add(src,dst):
 assert src.is_file(),str(src)
 files.append((src,dst))
for ext in ['png','jpg']:
 add(ROOT/f'A8_갓지은편지_변화.{ext}',f'01_갓지은편지/01_상태비교.{ext}')
 add(BASE/f'audit_2026-11-03/A_갓지은편지.{ext}',f'01_갓지은편지/02_안부의순간.{ext}')
 for key,folder in [('I','02_내밥을환영합니다'),('J','03_내일의논')]:
  a=next(a for a in assets if a['key']==key)
  add(ROOT/(a['stem']+'.'+ext),f'{folder}/최종.{ext}')
for src,dst in [('A_캐러셀_제출문구.md','01_갓지은편지/제출문구.md'),('I_제출문구.md','02_내밥을환영합니다/제출문구.md'),('J_제출문구.md','03_내일의논/제출문구.md')]:add(ROOT/src,dst)
for key,folder in [('A8','01_갓지은편지'),('I','02_내밥을환영합니다'),('J','03_내일의논')]:add(ROOT/f'원본과기록/{key}_선택생성원본.png',f'{folder}/기록/선택생성원본.png')
add(BASE/'audit_2026-11-03/원본과기록/A_선택생성원본.png','01_갓지은편지/기록/둘째장_선택생성원본.png')
add(BASE/'audit_2026-11-03/원본과기록/실제생성기록.json','01_갓지은편지/기록/이전A6_생성기록.json')
add(BASE/'audit_2026-11-03/원본과기록/A6_후속시각검토.json','01_갓지은편지/기록/이전A6_시각검토.json')
for name in ['실제생성기록.json','선별_기획_검수보고.md','독립파일검사.json','규칙별감사.json','규칙별감사.md','검토대상연결.json','선행검색_추가.md','AI_무문구원본검토.json','AI_후속검토.json']:
 add(ROOT/name,'검수기록/'+name)
zip_path=ROOT/'햇반_추가출품_3작.zip'
zip_readme='''햇반 추가 출품 준비 묶음 · 2026-11-11
01_갓지은편지: 01_상태비교 → 02_안부의순간을 한 작품의 캐러셀로 게시합니다.
02_내밥을환영합니다: 별도 한 장 작품입니다.
03_내일의논: 비전형 추가 작품입니다. 해상 논 자체의 발명이 아니며 즉시 상용화 안이 아닙니다.
각 폴더의 제출문구.md에서 주제/설명/AI활용/SNS태그를 가져오세요.
PNG는 조판 원본, JPG는 업로드 편의용입니다. 같은 장의 두 포맷을 모두 게시할 필요는 없습니다.
실제 AI서비스 제작 대화 화면 캡처를 별도로 첨부해야 합니다. 텍스트 로그가 이를 대신하지 않습니다.
SNS 게시·접수는 아직 하지 않았습니다. 검수기록의 내부판정과 외부 미관측을 구분하세요.
'''
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 z.writestr('먼저읽기.txt',zip_readme.encode('utf-8'))
 for src,dst in files:z.write(src,dst)
with zipfile.ZipFile(zip_path) as z:
 assert z.testzip() is None
 names=z.namelist(); assert len(names)==len(set(names))
 for src,dst in files:assert hashlib.sha256(z.read(dst)).hexdigest()==sha(src)
 assert all(not any(x in n for x in ['.private','logo_white','logo_red','.otf','K_밥먹는']) for n in names)
manifest={'date':'2026-11-11','zip':zip_path.name,'sha256':sha(zip_path),'bytes':zip_path.stat().st_size,'entry_count':len(names),'crc_and_each_source_sha256':'PASS','files':[{'archive_path':dst,'sha256':sha(src)} for src,dst in files]}
dump(ROOT/'제출묶음검사.json',manifest)
write(ROOT/'.gitignore','.private/\n__pycache__/\n*.zip\n')
print(json.dumps({'rule_rows':len(rows),'counts':counts,'zip_files':len(names),'zip_bytes':zip_path.stat().st_size,'file_qa':qa['status']},ensure_ascii=True))