# HARNESS-001 계약

**작업**: 계획 연속성 하네스 경량 설치
**선행**: ADR-001-harness-lean-install

## 범위

`.harness/policy.json`, `.harness/state.json`, `scripts/continuity_check.py`,
`scripts/test_continuity_check.py`, `CLAUDE.md`·`AGENTS.md` 어댑터, CI 검사 1스텝.

## 범위 밖 (왜)

- evidence 매니페스트, `work-items.json`, `docs/handoff.md`, pre-commit 훅.
  근거는 `scripts/test_continuity_check.py` 끝의 "무엇을 왜 버렸나" 참조.

## 수락 기준 (전부 실측)

1. `python scripts/continuity_check.py` → exit 0
2. 위반 fixture 12건이 각각 0 아닌 종료 코드. 그중 11건은 근거 문자열까지 확인
   (`test_missing_policy_fails` 만 종료 코드만 본다)
3. `pytest -k "not e2e"` 전체 통과
4. `sync_domain_list.py --check`, `sync_codex_mirror.py --check` → exit 0
5. 체커가 표준 라이브러리 밖을 쓰지 않음 (테스트로 강제)
6. `CLAUDE.md`·`AGENTS.md` 기존 내용 삭제 0줄

## UNVERIFIED

- NORTH STAR 문장의 담당자 승인.
