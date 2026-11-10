# Source Recall

제작팀이 원본 음성·음악·영상의 사용을 중단하거나 교체하기로 했을 때, 영향을 받는 납품 파일을 추적한다. 예시에서 `narrator-a`는 두 개의 작업 믹스를 거쳐 같은 트레일러에 쓰인다. 트레일러는 한 번만 표시하고 두 경로를 모두 남긴다. 다른 이름의 출력 파일에도 직접 또는 간접 경로를 표시한다.

## 1차 접수 파일

- [영문 제안서 PDF](submission/source-recall-proposal.pdf)
- [초기 Uliya Skill ZIP](submission/source-recall.zip)
- 트랙은 **Unleash Your Creativity**. 개인 참가 기준으로 준비했다. 팀으로 참가할 경우 공식 규정의 팀 동의 항목을 추가한다.
- Devpost의 [공식 규정](https://ugreenhackathon.devpost.com/rules) 기준 마감은 한국 시간 **2026-11-16 16:45**. Devpost에 제안서와 ZIP을 등록한다. 프로젝트 이름은 `Source Recall`.
- 제목과 게시 소개 문구는 [Devpost 입력 문구](submission/devpost.md)에 있다.

## 사용 흐름

1. 편집자가 원본·작업본·출력본의 연결을 [예시 맵](demo/lineage.txt) 형식으로 기록한다.
2. 중단할 원본 ID와 맵 파일, 출력 폴더를 명시한다. 예를 들어 “Source Recall로 `narrator-a`를 점검해 줘. 이 맵 파일과 이 납품 폴더를 사용해.”
3. 스킬이 지정된 맵을 확인한 뒤 선택된 폴더의 바로 아래 항목만 확인한다. 영향받는 파일의 연결 경로와 존재 여부, 폴더 내 별도 검토 항목을 보고한다.

[실행 예시 보기](demo/local-report.html). 예시 화면은 로컬 참조 검사기가 합성 자료와 실제 로컬 폴더 항목을 대조한 결과다.

## 검증과 결선

공식 제작 도구의 카탈로그 2.0.0에서 `ug-filesystem`의 등록 전문가 `file-agent` 및 읽기 동작 `stat`, `cat`, `ls`를 확인했다. ZIP을 임시 폴더에 다시 풀어 주최사 검사기를 돌린 결과는 [공식 검사 결과](submission/official-check.json)에 있다.

참조 검사기는 Python 표준 라이브러리로 동작한다. `python tools/test_recall.py -v`로 경로, 그래프, 현재 폴더 상태와 실패 경로를 확인한다. 빌드 시 `python tools/build_release.py <공식 check-skill.mjs 경로>`를 사용한다. 빌드에는 Node.js와 ReportLab이 필요하다. Python 파일, 시연 데이터, 도구와 검사 결과는 스킬 ZIP 바깥에 있다.

맵은 사람이 관리한다. 관찰 범위는 지정한 한 폴더이며 파일 본문이나 이미 배포한 복사본은 확인하지 않는다. Uliya의 권한 집행, 실제 결과 형식, 읽기 범위, 모델 연결 방식은 장비에서 검증한다. [결선 당일 검증 순서](finalist-validation.md).

공식 도구 출처는 [UGREEN Starter Kit](https://ai.ugreen.com/pages/hackathon-starter-kit)의 0.7.3 영문 배포본이며 다운로드 당시 SHA-256은 `cf557e5a022e4297892f39768132855154232efdedeb726b2845450ccd70e1b3`이다.
