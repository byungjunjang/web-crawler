@AGENTS.md
@.plan/CAPSULE.md

<!-- BEGIN GENERATED: agent-contract -->
## 실행 계약 (모델 공통)

이 절은 Claude Code, Codex, Cursor, Gemini CLI, 그 밖의 어떤 모델·도구에서
작업하든 **똑같이** 지켜야 하는 부분이다. 두 파일 모두 아래 블록은
`python scripts/sync_agent_contract.py` 로 같은 정본에서 생성된다.
판단이 필요한 부분(무엇을 정할지)은 모델이 아니라 이 저장소의 파일이 정한다.

> **아래 `python` 은 venv 안의 인터프리터다.** venv 밖에는 `python` 이 없을 수 있다
> (macOS 는 `python3` 이고, 이 저장소实测 기준 `python` 은 `.venv/bin/python` 이다).
> venv 를 먼저 활성화하거나, 없는 명령이 오면 곧바로 `python3` 로 되받아라.
>
> ```bash
> python -m venv .venv && . .venv/bin/activate    # Windows: .\.venv\Scripts\Activate.ps1
> ```

### 세션 시작

1. `.harness/policy.json` 과 `.harness/state.json` 을 읽는다.
   여기 없는 계획은 없다. 대화창에 남은 기억을 근거로 삼지 않는다.
2. 작업이 `.harness/active_work` 와 다르면 새 작업으로 등록한다.

### 제품 변경 전 (모두 실행하고, 실패하면 멈춘다)

```text
python -m pytest -q -k "not e2e"
python scripts/continuity_check.py
python scripts/sync_domain_list.py --check
python scripts/sync_codex_mirror.py --check
python scripts/sync_agent_contract.py --check
python scripts/session_handoff.py --check
```

### 완료 선언

- 위 다섯 명령이 **모두 exit 0** 이고, 그 출력을 본 뒤에만 완료라고 말한다.
- 실행하지 않은 명령의 결과를 예상으로 쓰지 않는다. 모르면 `미확인` 이라고 쓴다.
- 추측·추론을 결과로 보고하지 않는다. 실측 값과 그 출처를 함께 적는다.

### 세션 종료

1. **독립 리뷰**를 돌린다 (같은 모델이 아니라 다른 모델로).
2. finding 을 **고친다**. 통과가 아니라 수정까지 끝낸다.
3. `.harness/state.json` 의 `dirty` 를 `false` 로 바꾸고
   `session_end.independent_review` 에 `status`(passed/findings_open)와
   `model` 을 적는다. `dirty: false` 인데 이 기록이 없으면 검사기가 실패한다.
4. `python scripts/session_handoff.py write` 로 핸드오프를 생성하고,
   `python scripts/continuity_check.py` 를 다시 돌려 통과를 확인한다.

### 변경 직후

- TDD 는 RED 확인 → 최소 GREEN → 리팩터 순서다. RED 를 확인하지 않은 테스트는
  통과한 것이 아니라 **아직 아무것도 검증하지 않은 것** 이다.
<!-- END GENERATED: agent-contract -->

# 범용 웹 크롤링 에이전트

## 프로젝트 개요

이 프로젝트는 사용자가 URL과 수집 항목을 자연어로 설명하면, 자동으로 해당 웹사이트를 정찰하고 데이터를 대량 수집하여 엑셀 파일로 정리해주는 에이전트입니다.

## 이 문서는 지도다 — 상세는 아래에서 본다

규칙을 지우지 않고 원문을 옮겼다. 판정 기준·안전 하드룰·실행 계약은 `AGENTS.md` 에,
수집 워크플로우는 `SKILL.md` 에 있고, 이 문서는 그 위치를 가리키는 지도다.

- 수집 워크플로우 전체: `.claude/skills/web-crawler/SKILL.md`
- 셋업 · 정찰 · 크롤링 요청 절차: `docs/agents-reference.md` · [`README.md`](README.md) "처음 설치하기"
- 크롤링 운영 상세 (절대 규칙 0 · 안전/통지 규칙 · Fetcher 트리 · 에러 대응표 · Rate Limiting · 출력 구조 · 쿠키 흐름 · 프로필 스키마): `docs/crawl-reference.md`
- 코드 템플릿 / 안티봇 / 문제해결: `.claude/skills/web-crawler/references/` 의 `fetcher-patterns.md`, `antibot-strategies.md`, `troubleshooting.md`

## ★ 절대 규칙 0 — 도메인 히스토리 우선

새 수집 요청을 받으면 정찰 전에 `fingerprints/<sanitized_domain>/profile.json` 과 `output/<도메인>/` 을 먼저 본다. 프로필이 있으면 `notes`/`fetcher_type`/`antibot_strategy` 를 그대로 채택하고 정찰을 건너뛰어 Step 3 으로 간다.

**프로필이 있다는 사실은 통지 게이트를 면제하지 않는다 — 면제하는 것은 그 프로필이 지금 들고 있는 `consent` 기록뿐이다(sticky).** 전체 운영 흐름과 프로필 저장 계약은 `docs/crawl-reference.md` 의 같은 절에 있다.

## 도메인 프로필

<!-- BEGIN GENERATED: domain-list -->
<!-- 이 블록은 scripts/sync_domain_list.py 가 생성한다. 직접 수정하지 말 것. -->

### 알려진 도메인 (14개 profile commit됨)

`books.toscrape.com`, `builtini.co.kr`, `celimax.co.kr`, `data.seoul.go.kr`, `db.itkc.or.kr`, `g2b.go.kr`, `guesskorea.com`, `made-in-china.com`, `wanted.co.kr`, `www.11st.co.kr`, `www.fss.or.kr`, `www.gsmarena.com`, `www.k-startup.go.kr`, `www.kurly.com` — 이 도메인들은 정찰 없이 바로 수집 시도 가능.

<!-- END GENERATED: domain-list -->

## 안전 · 통지 (요약)

- **자동 접근 차단(CAPTCHA·WAF·봇 탐지)을 만나면 자동으로 넘어가지 않고 한 번 알리고 사용자가 고른다.** '진행' 이면 근거를 묻지 않고 그대로 간다.
- CAPTCHA 자동 풀이 금지 / 로그인 자격증명 저장 금지 / robots.txt 제한 시 사용자 확인 / PII 감지 시 경고 / 법적 위험이 큰 요청은 어느 축인지 짚어 경고.
- 상세: `docs/crawl-reference.md` "범위 / 운영 안전 규칙", `AGENTS.md` "안전 — 하드룰", `SKILL.md` Step 3 "이음매 통지 게이트".

## 계획 연속성

작업 전 `.harness/policy.json` 과 활성 계약을 읽는다. 제품 변경 전 `python scripts/continuity_check.py` 를 실행하고, 실패하면 표시된 드리프트를 먼저 해결한다. 포인터 정본은 `.harness/policy.json` 하나다. 근거: `docs/decisions/ADR-001-harness-lean-install.md`.
