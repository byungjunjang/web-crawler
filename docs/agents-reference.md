# 에이전트 상세 참조 — 셋업 · 정찰 · 수집 절차

> **출처**: 2026-10-01 에 `AGENTS.md` 와 `CLAUDE.md` 에서 **원문 그대로** 옮겼다(내용 변경 0).
> 목적은 두 진입 문서를 지도 역할로 줄이는 것이다. 판정 기준·안전 하드룰·실행 계약은
> 여전히 `AGENTS.md` 에 있고, 이 파일은 그 규칙을 수행할 때 보는 상세 절차다.
> 아래 두 셋업 절은 host 별 원문이다 — 위는 `AGENTS.md` 판(Windows 포함), 아래는
> `CLAUDE.md` 판(macOS/Linux)이다.

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


---

> **여기부터는 `CLAUDE.md` 판이다** (macOS/Linux 중심). 위 `AGENTS.md` 판과 host 차이만
> 다르고 나머지는 같다 — 그 차이는 의도된 분업이다(`scripts/sync_agent_contract.py`).

## 최초 환경 셋업 (클론 직후 1회, 수집 전 확인)

수집 시도 전에 환경을 준비한다. **한 명령**으로 단계별 설치+검증(이미 된 단계는 skip):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # Windows (venv 자동 생성)
```
```bash
python -m venv .venv && . .venv/bin/activate && python scripts/bootstrap.py   # macOS/Linux
```

수동/디버깅 시 실제 동작 명령:
```bash
pip install -r requirements.txt          # scrapling[fetchers] 포함 — fetcher 런타임 일괄
scrapling install                        # Chromium 1회 (내부에서 playwright install chromium 수행 — 따로 또 X)
npm.cmd install -g agent-browser ; agent-browser.cmd install   # 표준 정찰 도구 (PowerShell은 .cmd)
python scripts/preflight.py              # 검증: core / agent-browser 분리 PASS·WARN·FAIL
```

- `python -m scrapling`은 동작 안 함 → `scrapling install`(venv 활성화) 또는 `.\.venv\Scripts\scrapling.exe install`.
- 검증은 `scripts/preflight.py`(설치 안 함). core 통과·agent-browser 실패면 "전체 설치 미완료"(exit 1).
- 전체 가이드(비개발자용 포함)는 `README.md`의 "처음 설치하기" 참조.

---

