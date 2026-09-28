<!-- PLAN-RULES:BEGIN (plan-continuity-harness v2) -->
계획·사용자 지시·결정의 정본은 공유 원장이다(브랜치·작업트리 공통). 맥락에 「계획 캡슐」이 없으면 작업 전에 `node .plan/bin/plan.mjs inject`를 실행해 읽고 캡슐 규칙을 따른다. 세션 끝에 `node .plan/bin/plan.mjs check --close`.
<!-- PLAN-RULES:END -->

## Git push 정책 (사용자 상시 승인, 2026-09-29)

- 기능 브랜치(main·master 제외)의 push와 PR 생성은 사용자가 상시 승인했다. 검사를 통과한 커밋은 묻지 말고 push한다.
- main·master 직접 push, force push, 병합, 배포는 매번 사용자에게 묻는다.

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

# AGENTS.md — web-crawler (Codex / Claude Code dual-host)

이 레포는 URL과 수집 항목을 받아 사이트를 정찰·대량수집하고 엑셀로 내보내는 범용 웹 크롤링 에이전트다. **`CLAUDE.md`와 `.codex/skills/web-crawler/SKILL.md`가 *어떻게*에 대한 SSOT다.** 이 파일은 Codex용 **실행 계약**이다 — Claude Code는 Skill 런타임으로 같은 규율을 자동 적용받지만, Codex는 Skill 런타임이 없으므로 이 파일이 대신 강제한다.

## 최초 환경 셋업 (클론 직후 1회)

수집 전에 환경을 준비한다. **한 명령**으로 단계별 설치+검증을 하고, 이미 된 단계는 skip한다:

```powershell
# Windows (PowerShell) — 실행 정책 우회가 표준
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```
```bash
# macOS / Linux
python -m venv .venv && . .venv/bin/activate && python scripts/bootstrap.py
```

단계: ① Python deps → ② 브라우저(Chromium) → ③ agent-browser(표준 정찰 도구) → ④ preflight 검증.
실패하면 "다음에 실행할 정확한 명령"이 출력된다. 모드: 기본 full(표준) / `--core-only`(agent-browser 제외) / `--skip-browser` / `-VerbosePip`(pip 상세 로그).

**`py` 런처 깨짐 자동 처리**: `setup.ps1`은 `py -3`/`python`/`python3`를 실제 실행해 3.10+를 확인하고 성공하는 쪽으로 venv를 만든다. `py -3`가 `No installed Python found!`로 실패하면 자동으로 `python`으로 fallback한다. 그래도 venv가 안 생기면 직접: `python -m venv .venv` → `.\.venv\Scripts\python.exe scripts\bootstrap.py`.

**수동/디버깅 시 실제 동작하는 명령 (Windows)**:
```powershell
python --version ; py -3 --version       # 어느 쪽이 동작하는지 먼저 확인 (py 깨졌으면 python 사용)
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --progress-bar off    # 멈춘 듯하면 끝에 -v 추가
scrapling install                        # Chromium 1회 설치 (내부에서 playwright install chromium 수행 — 따로 또 X)
npm.cmd install -g agent-browser ; agent-browser.cmd install   # PowerShell은 .cmd 사용
python scripts\preflight.py              # 검증: core / agent-browser 분리 PASS·WARN·FAIL
```
- `python -m scrapling`은 동작 안 함 → `scrapling install`(venv 활성화) 또는 `.\.venv\Scripts\scrapling.exe install`.
- pip이 진행 없이 멈춘 듯하면 정상(대용량 휠 다운로드). 진행 확인: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt --progress-bar off -v`.
- 검증은 `scripts/preflight.py`가 담당: **core(Python/Scrapling/Playwright)**와 **agent-browser**를 분리 보고. core 통과·agent-browser 실패면 "전체 설치 미완료"(종료코드 1). 전체 가이드는 `README.md` "처음 설치하기".

## 스킬 소스 (생성 미러)

- **`.claude/skills/`가 정본. `.codex/skills/`는 생성 미러**다 — 텍스트 안의 `.claude/skills` 경로만 `.codex/skills`로 치환된 것 외엔 byte-identical.
- **`.codex/skills/`를 직접 수정하지 말 것.** `.claude/skills/`를 고친 뒤 `python scripts/sync_codex_mirror.py`를 실행해 미러를 재생성한다. (어긋남 확인: `python scripts/sync_codex_mirror.py --check`)
- **문서의 "알려진 도메인" 목록도 생성물**이다 — `fingerprints/*/profile.json`이 SSOT. 새 프로필을 추가했으면 `python scripts/sync_domain_list.py`로 CLAUDE.md/README.md를 재생성한다. (어긋남 확인: `python scripts/sync_domain_list.py --check` / 테스트: `scripts/test_sync_domain_list.py`)

## 크롤링 요청을 받으면 — 필수 절차

사용자가 "크롤링/스크래핑/수집/~를 모아줘/입찰공고 수집" 등을 요청하면:

1. **즉흥 처리 금지.** `.codex/skills/web-crawler/SKILL.md`를 단계대로 실행한다. 절차를 요약하고 임의로 구현하지 않는다. **폴백 재구현 금지** — `requests`/`urllib`/`httpx`/`BeautifulSoup`로 직접 수집하거나 인라인으로 긁지 않는다. 수집은 항상 생성한 `crawl_script.py` 안의 **Scrapling 또는 Playwright**로만 한다.

2. **절대 규칙 0 — 도메인 히스토리 우선.** 정찰하기 전에 반드시 `fingerprints/<sanitized_domain>/profile.json`과 `output/<도메인>/`을 먼저 본다. 프로필이 있으면 `notes`/`fetcher_type`/`antibot_strategy`를 그대로 채택하고 정찰을 건너뛰어 Step 3으로 점프한다. profile.json이 있는데 무시하고 정찰부터 다시 하는 것은 금지(5~20분 비싼 작업 반복). 알려진 도메인 목록은 `CLAUDE.md` 의 생성 블록 참조.

3. **프로필 게이트.** Step 1-A(프로필 있으면 load) ↔ Step 5-A(수집 성공 직후 save/갱신, `notes` 필드 필수). Step 5-A를 빠뜨리면 수집 결과가 살아있어도 **"파이프라인 미완료"**로 보고한다.

## 정찰 도구 — agent-browser가 표준 (양 host 공통)

- 정찰(Step 2)의 **표준·기본 도구는 `agent-browser`**다. 선택 기능이 아니다 — 워크플로상 정찰 단계에서는 **단순 정적 사이트를 긁더라도 agent-browser를 먼저 사용**한다. vercel-labs의 독립 CLI(`npm install -g agent-browser`)라 **Claude Code·Codex 모두 동일하게** 쓴다(Claude 전용 아님). 양 host 모두 정찰 시작 전 우선 `agent-browser skills get core --full`로 사용법을 로드한다. 설치된 구버전이 `Unknown command: skills`를 반환하면 `agent-browser --help`의 snapshot/network 명령을 로드한다. 이 오류만으로 agent-browser 자체가 불능이라고 판정하거나 폴백으로 내려가지 않는다.
- **정찰 폴백 티어 (agent-browser를 못 쓸 때만).** 위에서부터 내려간다. 어느 티어를 썼는지 profile.json `notes`에 남긴다.
  - **폴백 1 (Claude): Claude in Chrome** (`mcp__claude-in-chrome__*`) — **Claude 계열 host 전용**(Claude Code / Cowork). 사용자의 실제 Chrome을 조종해서 **실제 쿠키·실제 IP**가 그대로 붙는 게 최대 장점. Step 2 정찰 항목 5개는 전부 대체된다(검증 완료). 단 네트워크 감시에 제약이 있으니 반드시 SKILL.md Step 2 "Claude in Chrome 폴백" 절차를 따를 것.
  - **폴백 1 (Codex): ChatGPT Chrome 플러그인 Browser Use** (`chrome:control-chrome`) — **Codex 세션에 Chrome 스킬이 있고 사용자의 ChatGPT Chrome 확장이 연결될 때만** 쓴다. 사용자의 실제 Chrome을 조종하므로 실제 브라우저 상태·세션·IP를 활용할 수 있다(쿠키·스토리지를 직접 읽지는 않는다). Step 2 정찰 항목 5개는 대체한다(2026-08-19 `books.toscrape.com` 실측). 단 일반 XHR/fetch 요청과 응답 헤더·본문을 직접 캡처하는 API는 없으므로, API 네트워크 감시가 필요하면 폴백 2의 Playwright `sync_api`를 네트워크 보조 수단으로 쓴다. 반드시 SKILL.md Step 2 "ChatGPT Chrome Browser Use 폴백" 절차를 따를 것. Chrome 확장이 연결되지 않으면 이 티어를 건너뛴다.
  - **폴백 2 (공통): Scrapling `DynamicFetcher`** 또는 **Playwright `sync_api`**(`page.on("response")`로 XHR/API 캡처) — 양 host 공통, Python 의존성에 포함돼 항상 가능. (SKILL.md 규칙 1 예외와 동일.)
  - **host별 경로를 섞지 않는다.** Claude Code/Cowork는 `agent-browser → Claude in Chrome → 폴백 2`, Codex는 `agent-browser → ChatGPT Chrome Browser Use(연결 시) → 폴백 2`다. Codex에서 Claude in Chrome을 찾지 않는다.
  어느 경우든 가능하면 `agent-browser.cmd install`로 표준 경로 복구를 먼저 시도한다.
- **수집은 폴백 대상이 아니다.** Claude in Chrome과 ChatGPT Chrome Browser Use는 **정찰 전용**이다 — 브라우저에서 전량 추출하는 것은 절대 규칙 2 위반. 수집은 어떤 host에서든 `crawl_script.py`(Scrapling/Playwright)로 한다.
- **원격 전용 환경(Cowork 등)에서 전 파이프라인 실행은 불가.** Cowork 샌드박스는 egress가 기본 "package managers only"(npm/PyPI/GitHub)라 대상 사이트 직접 접속이 막히고, 뚫어도 데이터센터 IP라 브라우저 세션이 필요한 도메인의 profile 레시피가 재현되지 않으며, VM에서 호스트 Chrome의 CDP 포트에 붙을 수 없어 `scripts/chrome_cdp.py` 경로가 통째로 죽는다. 원격에서는 **정찰만** 하고 profile.json을 갱신한 뒤, 수집은 로컬에서 실행한다.
- **수집·프로필·엑셀·CDP는 양 host 완전 동일**: 수집(Scrapling), 도메인 프로필(`scripts/domain_profile.py`), 엑셀(`scripts/export_excel.py`), 브라우저 세션이 필요한 사이트 대응(`scripts/chrome_cdp.py`), 진행 체크포인트(`scripts/progress.py`).

## 안전 — 하드룰 (위반 금지)

- **자동 접근 차단을 만나면 통지 후 사용자 선택** — CAPTCHA·WAF·봇 탐지는 법적으로 같은 보호조치다. 어느 쪽이든 **자동으로 넘어가지 않고 이음매를 통과할 때마다 한 번 알리고 사용자가 고른다**. '진행' 이면 그대로 간다 — 근거를 묻지도 검증하지도 않는다. 통지를 면제하는 것은 도메인이 아니라 그 프로필이 **지금 들고 있는** `consent` 기록이다(sticky) — 사다리 A 로 내려가 프로필이 배포 대상이 되면 그 기록은 지워지므로(사용자의 통지 이력을 배포되는 파일에 실어 보내지 않는다), 사이트가 나중에 새로 막으면 다시 통지한다. 상세는 `.codex/skills/web-crawler/SKILL.md` Step 3 "이음매 통지 게이트".
- **CAPTCHA 자동 풀이 금지** — 위 통지 게이트와 별개다. reCAPTCHA/hCaptcha 를 **프로그램으로 푸는 것**은 하지 않는다. 사용자가 agent-browser 로 직접 풀고 이어가는 것은 가능하다.
- **로그인 자격증명 저장 금지** — ID/PW를 코드·메모리·파일에 저장하지 않는다. 사용자가 직접 로그인 → 쿠키만 추출(`output/<도메인>/cookies.json`, `.gitignore`가 차단).
- **robots.txt 제한** 발견 시(`Disallow: /` 또는 대상 경로 차단) 진행 여부를 사용자에게 묻는다.
- **PII 감지 필수** — 수집 데이터에 전화번호/주민번호/이메일 등이 섞이면 `detect_pii(data)`로 경고하고 보고한다.
- **법적 위험이 큰 요청은 구체적으로 경고** — 저작권 침해 목적의 본문 복제(분량 축)·개인정보 대량 수집(성격 축)·명시적으로 금지된 재배포(목적 축). **어느 축이 왜 걸리는지 짚어서 알린 뒤 진행 여부는 사용자가 정한다** — 근거를 묻지도 검증하지도 않는다. **약관이 크롤링을 금지한다는 사실만으로는 여기 해당하지 않는다** — 그건 접근의 계약 층이고, 위 통지 게이트로 간다.
- **수집 0건이면 즉시 중단·보고** — 계속 시도하면 ban 위험.

> **위 '경고' 규칙과 통지 게이트는 같은 층위다.** 경고는 요청이 **어떤 위험 축에 걸리는지**를,
> 게이트는 **기술적 차단을 만났다는 사실**을 알린다. 알리는 대상만 다를 뿐 둘 다 알리는 데서
> 끝나고 고르는 쪽은 사용자다 — 어느 쪽도 요청 자체를 막지 않으며, 근거를 묻지도 검증하지도
> 않는다.
>
> 이 문서가 정의하는 것은 **도구의 동작**이다. 실행하는 AI 에이전트 자신의 판단 기준은 별개로
> 작동하며 이 문서가 그것을 대신 약속하지 않는다 — `ACCEPTABLE_USE.md` 참조.

## 빠른 참조

| 무엇 | 경로 |
|------|------|
| 워크플로우 전체 | `.codex/skills/web-crawler/SKILL.md` |
| Fetcher 코드 템플릿 | `.codex/skills/web-crawler/references/fetcher-patterns.md` |
| 안티봇(Akamai/Cloudflare/SPA 세션) | `.codex/skills/web-crawler/references/antibot-strategies.md` |
| 수집 실패 진단 | `.codex/skills/web-crawler/references/troubleshooting.md` |
| 프로젝트 규칙·도구 분리 SSOT | `CLAUDE.md` |
| 계획 연속성 검사기 | `python scripts/continuity_check.py` |

## 계획 연속성

```text
작업 전에 .harness/policy.json 과 활성 계약을 읽는다.
제품 변경 전에 python scripts/continuity_check.py 를 실행한다.
검사가 실패하면 제품 변경을 멈추고 표시된 드리프트를 먼저 해결한다.
완료 주장은 활성 계약이 요구한 실제 명령 출력이 있을 때만 한다.
```

- 포인터 정본은 `.harness/policy.json` **하나**다. 파생 복사본을 두지 않는다.
- 세션 시작은 `.harness/state.json` 한 파일만 읽으면 복구된다.
- 근거는 `docs/decisions/ADR-001-harness-lean-install.md` 에 있다.
