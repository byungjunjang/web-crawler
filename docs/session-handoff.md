# 세션 핸드오프

> 이 파일은 **생성물**이다. `python scripts/session_handoff.py write` 로 만든다.
>
> `--check` 가 잡는 것: **정본(state/policy)이 바뀌었는데 문서가 따라가지 않은 것**.
> `--check` 가 **못** 잡는 것: 이 본문 안의 문장을 손으로 고치는 것.
> 정본이 아닌 본문은 사람이 읽는 설명일 뿐이라 기계가 검증할 수 없다.
> 정본은 `.harness/state.json` 이고, 생성기는 `scripts/session_handoff.py` 다.

다음 세션은 이 파일과 `.harness/state.json` 만 읽으면 된다. 이전 대화 이력은 근거가 아니다.

- 입력 다이제스트: `8e39effb200eb4f9633cd775a10f8e04a334fcd71512bb2c015bc420b7715288`

## 상태 한 줄 요약

- 활성 작업: **HARNESS-001** — 계약 `docs/task-contracts/HARNESS-001.md`
- NORTH STAR: URL과 수집 항목을 받아 사이트를 정찰·대량수집하고 엑셀로 내보내는 범용 웹 크롤링 에이전트 — 문서에 적힌 대로 따라 하면 죽지 않는다 (`GOAL-001`)
- 단계: `POST_CHECK` / dirty=`False`
- 검증 커밋: `947802ace6b657971e567aa559c151aa7ceb7588`
- 작업 도구: **opencode-go/deepseek-v4.1-flash**

## 실측 검증 (write 시점에 돌린 결과다)

기준선: `c9bdd14` · 브랜치 `master`

| 항목 | 명령 | 결과 |
|---|---|---|
| baseline | `python -m pytest -q -k "not e2e"` | exit=0 ✅ — 573 passed, 14 deselected |
| 연속성 | `python scripts/continuity_check.py` | exit=0 ✅ — 연속성 검사 통과 — 포인터와 실제 파일이 일치한다 |
| 도메인 목록 | `python scripts/sync_domain_list.py --check` | exit=0 ✅ — [OK] 도메인 목록 최신 — 14개 |
| Codex 미러 | `python scripts/sync_codex_mirror.py --check` | exit=0 ✅ — 출력 없음 |
| 실행 계약 | `python scripts/sync_agent_contract.py --check` | exit=0 ✅ — 출력 없음 |

## 이번 세션에 한 일

- c9bdd14 chore(harness): 커밋으로 HEAD 가 바뀌어 생성이 먼저 필요하므로 핸드오프 재생성
- 9a4e116 feat(harness): 세션 종료 시 핸드오프 문서를 생성하는 하네스를 이식한다
- 0672b81 chore(harness): 세션 종료 — 독립 리뷰 기록을 남기고 상태를 닫는다
- 947802a fix(harness): 독립 리뷰가 찾은 세션 종료 우회 3건과 CI 실패 1건을 닫는다
- 22873dd feat(contract): 실행 계약을 단일 정본에서 생성해 모델 간 기준을 같게 한다
- 1488f98 ci: 하네스 검사가 실제 러너에서 도는지 확인
- 9896e3b feat(harness): 계획 연속성 하네스를 경량 설치한다
- 11abe6e test(profile): 문서 계약 위반 4건을 CI 가 발화하도록 고정한다
- e9c3060 fix(docs): 문서가 코드와 정본 계약을 거슬렀다 — 4건 정정
- 5867a4b chore: 세션 상태(.context/)를 커밋 대상에서 뺀다
- d94f621 test(profile): 프로필 계약 불일치 6건을 CI 가 잡는다
- ecac61a fix(profile): builtini·celimax 리뷰 API 레시피를 실측값으로 되살린다

## 남은 것 / 다음 세션

- 활성 계약의 미해결 항목을 먼저 본다: `docs/task-contracts/HARNESS-001.md`
- UNVERIFIED 로 남아 있는 것은 지어내지 말고 그대로 유지한다.
- `.context/STATE` 가 세션 중간에서 멈췄다면 갱신한다 — 그 파일은 세션 문맥의 SSOT 다.

## 다음 세션 즉시 시작

```text
세션 이어받기. 프로젝트: /Users/joonake/Developer/projects/web-crawler
먼저 docs/session-handoff.md 와 .harness/state.json 을 읽는다.
그리고 baseline 확인: python -m pytest -q -k "not e2e"  (위 표의 통과 수와 같아야 한다)
활성 작업: HARNESS-001 — 계약 docs/task-contracts/HARNESS-001.md
```
