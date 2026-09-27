# 계획 연속성 하네스 승인 REV-001

**승인일**: 2026-09-27
**승인자**: 저장소 소유자 (사용자 지시에 의한 설치)

## 설치하는 것

`.harness/policy.json` + `.harness/state.json` + `scripts/continuity_check.py` 3개 파일과
`CLAUDE.md`·`AGENTS.md` 의 얇은 어댑터, CI 의 검사 한 스텝.

## 의도적으로 설치하지 않는 것

다른 프로젝트(`/Users/joonake/Developer/projects/planning-continuity-harness-docs/`)
의 `PROJECT-HARNESS-INSTALL.md` 4절이 밝힌 전체 구조가 아니라,
**판단 근거로 검증할 수 있는 항목만** 남겼다. 제외 항목과 이유는
`scripts/test_continuity_check.py` 끝의 "무엇을 왜 버렸나" 에 적었다.

- `work-items.json` — `policy.active_work` 에 이미 id·roadmap_id·contract_path 가 있어
  파생 복사본은 드리프트만 늘린다.
- `docs/handoff.md` — `state.json` 이 정본이다. 같은 정보를 두 곳에 적으면 반드시 어긋난다.
- evidence manifest — 지시서 5절이 "체커가 실제 실행 여부를 증명 못 한다" 고 인정한다.
  증명 못 하는 규칙은 조용히 통과하는 장식이라 두지 않았다.
- pre-commit 훅 — 지시서 8절이 선택 사항이라 명시. CI 가 최종 검문이고,
  로컬 훅은 커밋을 느리게 만들어 되돌리기 비용을 높인다.

## 검증된 것

- 위반 fixture 12건이 모두 0 아닌 종료 코드로 보고되고, 그중 11건은 발화한
  규칙의 근거 문자열까지 함께 확인한다.
- `python scripts/continuity_check.py` 가 exit 0 이다.
- 기존 스위트(`pytest -k "not e2e"`)가 회귀하지 않는다.
- `sync_domain_list.py --check` 와 `sync_codex_mirror.py --check` 가 exit 0 이다.

## UNVERIFIED

- NORTH STAR 문장: `CLAUDE.md` 의 서술을 옮겼을 뿐 **담당자의 승인 문장을 받지 않았다**.
- `active_work` 는 이 설치 작업 자체를 가리킨다. 승인된 제품 작업이 아니다.
