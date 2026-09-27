# ADR-001: 계획 연속성 하네스를 경량 설치한다

**상태**: accepted
**결정일**: 2026-09-27

## 맥락

다른 프로젝트(`/Users/joonake/Developer/projects/`)를 조사한 결과 하네스 계열이 두 부류로
갈라져 있었다.

1. `docstudio`·`poms`·`kssa`·`korean-ascent-ai` — `docs/harness/` 에 rubric·features JSON 을 두고
   `scripts/harness-check.mjs`(36~406줄) 로 채점한다. **UI/기능 rubric 구조라 Node 런타임이 필요하다.**
2. `planning-continuity-harness-docs` — "포터블" 하네스 문서 + 설치 지시서. 언어 중립,
   결정론적 체커, 단일 포인터 SSOT 를 전제로 한다.

이 저장소는 Python CLI 다. 1번 부류는 런타임·개념 모두 맞지 않는다.

## 결정

2번의 **원칙만** 가져오되, "장점만" 이라는 요구에 맞춰 판단 근거로 검증할 수 없는 항목을
제외한다. 4절이 스스로 "가장 작은 실용 설치" 를 밝힌 경로에 더 줄여
`policy.json`·`state.json`·체커 3개 파일로 제한한다.

## 대안과 버린 이유

- **전체 4절 구조 그대로** — 근거 없는 evidence 매니페스트와 pre-commit 훅을 포함하게 된다.
  지시서 5절이 "체커가 실제 실행 여부를 증명 못 한다" 고 인정하는 항목이라, 증명 못 하는
  규칙을 두는 것은 조용히 통과하는 장식이다.
- **1번 부류의 rubric 모델 채택** — Node 런타임 추가. 이 저장소의 의존성 표면을 키운다.

## 결과

- 새 의존성 0개 (표준 라이브러리만).
- 포인터 불일치·승인 파일 변형·저장소 밖 참조를 커밋 전에 드러낸다.
- 세션 재개는 `.harness/state.json` 한 파일만 읽으면 된다.

## UNVERIFIED

- required status check 설정 여부는 확인하지 못했다(원격 관리자 권한 필요).
- 이 ADR 은 `CLAUDE.md` 규약상 사람 승인 항목이다. 사용자의 설치 지시를 승인으로 간주했다.
