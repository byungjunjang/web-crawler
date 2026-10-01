# 세션 핸드오프

> 이 파일은 **생성물**이다. `python scripts/session_handoff.py write` 로 만든다.
>
> `--check` 가 잡는 것: **정본(state/policy)이 바뀌었는데 문서가 따라가지 않은 것**.
> `--check` 가 **못** 잡는 것: 이 본문 안의 문장을 손으로 고치는 것.
> 정본이 아닌 본문은 사람이 읽는 설명일 뿐이라 기계가 검증할 수 없다.
> 정본은 `.harness/state.json` 이고, 생성기는 `scripts/session_handoff.py` 다.

다음 세션은 이 파일과 `.harness/state.json` 만 읽으면 된다. 이전 대화 이력은 근거가 아니다.

- 입력 다이제스트: `1d157b9af98abdd7346a6d3211f8627bbf9261f71efecb83315186b724a5b354`

## 상태 한 줄 요약

- 활성 작업: **PY311-001** — 계약 `docs/task-contracts/PY311-001.md`
- NORTH STAR: URL과 수집 항목을 받아 사이트를 정찰·대량수집하고 엑셀로 내보내는 범용 웹 크롤링 에이전트 — 문서에 적힌 대로 따라 하면 죽지 않는다 (`GOAL-001`)
- 단계: `POST_CHECK` / dirty=`False`
- 검증 커밋: `9e8384a`
- 작업 도구: **opencode-go/deepseek-v4.1-flash**

## 실측 검증 (write 시점에 돌린 결과다)

측정 시점 HEAD: `aa3c573` · 브랜치 `chore/plan-harness-v2`

> ⚠ **출처**: 아래 결과는 이 문서를 커밋하기 **전의 작업 트리**에서 돌았다.
> `write` 는 커밋 전에 불리므로 위 해시는 이 문서를 담는 커밋의 **부모**다.
> 그래서 그 커밋을 체크아웃해 `baseline` 을 다시 돌리면 통과 수가 **다를 수 있다** —
> 아래 수는 '이 커밋의 트리'가 아니라 '그 커밋 직전의 작업 트리'의 실측이다.
> 이 문서를 커밋한 다음 다시 생성하면(HEAD 가 바뀐다) 수치가 맞춰진다.

| 항목 | 명령 | 결과 |
|---|---|---|
| baseline | `python -m pytest -q -k "not e2e"` | exit=0 ✅ — 579 passed, 14 deselected |
| 연속성 | `python scripts/continuity_check.py` | exit=0 ✅ — 연속성 검사 통과 — 포인터와 실제 파일이 일치한다 |
| 도메인 목록 | `python scripts/sync_domain_list.py --check` | exit=0 ✅ — [OK] 도메인 목록 최신 — 14개 |
| Codex 미러 | `python scripts/sync_codex_mirror.py --check` | exit=0 ✅ — 출력 없음 |
| 실행 계약 | `python scripts/sync_agent_contract.py --check` | exit=0 ✅ — 출력 없음 |

## 이번 세션에 한 일

- aa3c573 docs(contract): ubuntu/x86_64 러너 통과를 실측해 UNVERIFIED 에서 닫는다
- beb6e31 chore(harness): 세션 종료 — 상태를 닫고 핸드오프를 생성한다
- 9e8384a feat(requirements): playwright·patchright 결합을 파일 제약으로 강제한다
- 07dad93 fix(harness): write 가 거짓 exit=1 을 기록하는 순환을 닫는다
- 73367de chore(plan): 하네스 CLI 갱신(제안 ADR 캡슐 표시, ADR 상태 표기 확대, 기준선 계획 폴더 새 문서 허용)
- 92ce606 docs(agents): git push 정책 명시(기능 브랜치 push·PR은 사용자 상시 승인, main·force·병합·배포는 매번 승인)
- be9a8ee chore(plan): 하네스 CLI 갱신(ADR 범위 표기 인정)
- d59108a chore(plan): 하네스 CLI 갱신(계획 편집 허용+승인 전 변경은 종료 게이트, ADR 번호 표기 인정)
- d76c133 chore(plan): 계획 정본 하네스 v2 설치
- 32ca3f2 wip: 계획 하네스 설치 전 사용자 변경 보존
- dca2779 chore(harness): 세션 종료 — 핸드오프 생성기를 독립 리뷰 결과로 교정하고 상태를 닫는다
- e725dc4 fix(harness): 다이제스트에서 HEAD 를 빼 고정점 불가 구조를 없앤다

## 남은 것 / 다음 세션

- 활성 계약의 미해결 항목을 먼저 본다: `docs/task-contracts/PY311-001.md`
- UNVERIFIED 로 남아 있는 것은 지어내지 말고 그대로 유지한다.
- `.context/STATE` 가 세션 중간에서 멈췄다면 갱신한다 — 그 파일은 세션 문맥의 SSOT 다.

## 다음 세션 즉시 시작

```text
세션 이어받기. 프로젝트: /Users/joonake/Developer/projects/web-crawler
먼저 docs/session-handoff.md 와 .harness/state.json 을 읽는다.
그리고 baseline 확인: python -m pytest -q -k "not e2e"  (위 표의 통과 수와 같아야 한다)
활성 작업: PY311-001 — 계약 docs/task-contracts/PY311-001.md
```
