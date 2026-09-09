---
name: web-crawler
description: URL과 수집 항목을 받아 사이트를 정찰하고 데이터를 수집하여 엑셀로 출력하는 범용 웹 크롤링 에이전트. 사용자가 URL과 함께 데이터 수집/크롤링/스크래핑을 요청하거나, 웹사이트에서 정보를 추출하고 싶다고 할 때 반드시 이 스킬을 사용한다. "이 사이트에서 ~를 모아줘", "~를 크롤링해줘", "입찰공고를 수집해줘" 등의 요청에도 트리거된다.
---

# 웹 크롤링 워크플로우

## 절대 규칙

1. **수집에는 Scrapling 또는 Playwright만 사용한다.** `requests`, `urllib`, `httpx`, `BeautifulSoup`로 직접 수집하지 않는다.
2. **agent-browser는 정찰 전용이다.** agent-browser에서 `page.evaluate()`로 데이터를 추출하거나 DOM을 파싱하여 수집하는 것은 금지. agent-browser는 구조 파악, 스크린샷, 네트워크 감시에만 사용한다.
3. **반드시 crawl_script.py를 생성하고 실행한다.** 스크립트 없이 인라인으로 수집하지 않는다.
4. **정찰과 수집의 역할을 분리한다.** 정찰(agent-browser) → 수집(crawl_script.py 내 Scrapling/Playwright) → 출력(openpyxl).

> **규칙 1 예외 — Playwright 직접 사용이 허용되는 경우:**
> SPA 세션 보호 사이트(WebSquare, 내부 API 403 등)에서는 crawl_script.py 안에서 Playwright를 직접 사용하여 SPA를 로드하고, `page.on("response")`로 XHR 응답을 인터셉트하여 데이터를 수집할 수 있다. 이 경우에도 agent-browser가 아닌 Playwright sync_api를 사용한다.

## 워크플로우 개요

```
Step 1: 입력 파싱 → Step 1-A: 도메인 프로필 확인 → Step 1-B: Phase 0 공인 우회로 체크
    ↓                  (재사용 Yes → Step 3)        (해결되면 정찰 스킵 → Step 4)
Step 2: 정찰 (agent-browser) → Step 2-A: 인증 처리 (필요 시)
    ↓
Step 3: 사이트 분류 & 수집 전략 결정 ← 핵심 의사결정
    ↓
Step 4: 수집 코드 생성 & 실행
    ↓
Step 5: 데이터 검증 (Step 5.0 소프트블록 게이트 최우선)
    ↓
Step 5-A: 도메인 프로필 저장 (필수 게이트, 누락 시 파이프라인 미완료)
    ↓
Step 6: 엑셀 출력 & 보고
```

---

## Step 1: 입력 파싱

사용자 메시지에서 추출:
- **URL**: 수집 대상 주소
- **수집 항목**: 데이터 필드 목록
- **특수 조건**: 로그인, 필터, 정렬, 건수 제한 등

불명확하면 되묻기. 최소 요건: URL 1개 + 수집 항목 1개.

### Step 1-A: 도메인 프로필 확인

재수집 시 기존 프로필이 있으면 정찰을 스킵할 수 있다.

```python
from domain_profile import DomainProfile
profile_mgr = DomainProfile()
if profile_mgr.exists(domain):
    profile = profile_mgr.load(domain)
    # "이전 설정을 재사용할까요?"
    #   → Yes(재사용): Phase 0(1-B) 건너뛰고 바로 Step 3 (검증된 레시피 보유)
    #     단 consent 기록이 없는 사다리 B 프로필이면 이번이 최초 통과다 — Step 3 의 이음매 통지를 거친다.
    #   → No(신규·미재사용)·프로필 없음: Step 1-B(Phase 0)부터 진행
```

수집 성공 후 프로필 저장:
```python
profile_mgr.save(domain, {
    "domain": domain,
    "capability": "<static|js_render|api|session>",   # ★ SSOT — 능력 수준. 비워 두면 save() 가 fetcher_type 에서 채운다
    "fetcher_type": "<Fetcher|FetcherSession|DynamicFetcher|DynamicSession|Spider|playwright_spa_intercept|curl_cffi_grid|StealthyFetcher|chrome_cdp|API_SESSION|yt-dlp|RSS|oEmbed|Jina>",
    "antibot_strategy": "<none|playwright_intercept|impersonate|curl_cffi_grid|stealthy|chrome_cdp|naver_antibot|authenticated_browser>",
    "site_type": "<static|csr|api|spa_session|akamai>",
    # robots·ToS 사유로 배포에서 빼야 하면 명시한다 — 사다리 A 여도 이 선언은 무조건 인정된다
    "distribution": "local", "distribution_reason": "<한 줄>",
    "selectors": {<MAPPING>},
    "pagination": {<CONFIG>},
    "api_endpoints": [<LIST>],
    "notes": "<특이사항>",
    # 사다리 B(4단 이상)로 수집했을 때만. **실제로 통지했고 사용자가 '진행' 을 고른 경우에만 적는다** —
    # 그 일이 없었으면 이 블록을 적지 않는다. 적으면 기록이 거짓이 되고, 이 기록의 유일한 쓸모가 사라진다.
    # 근거가 아니라 선택을 적는다. 이미 `consent` 기록이 있는 프로필이면 자동으로 이어지므로(sticky) 생략해도 된다.
    "consent": {"notified_at": "<통지한 실제 시각 ISO8601>", "choice": "proceed"},
})
```

### Step 1-B: Phase 0 공인 우회로 체크

> profile.json이 없거나(신규 도메인) 재사용 안 할 경우, **정찰(Step 2)로 가기 전에** 그 플랫폼에 공개 API/피드/oEmbed가 있는지 먼저 본다. (insane-search Phase 0 차용) 있으면 HTML 정찰·긁기보다 빠르고 안정적이며 차단도 거의 없다 → 정찰 스킵하고 바로 수집.

| 플랫폼 유형 | 공인 우회로 | 비고 |
|------------|-----------|------|
| YouTube/TikTok/SoundCloud 등 미디어 | `yt-dlp --dump-json <URL>` | 메타/자막, 1,800+ 사이트 |
| arXiv / Wikipedia / GitHub / CrossRef | Atom/REST 공개 API | 인증 불필요 |
| X(트위터) 단일 트윗 | `cdn.syndication.twimg.com` oEmbed | |
| Reddit | 서브레딧/스레드 `.rss` (Atom) | |
| Hacker News | Firebase JSON API | |
| 일반 사이트 (SPA 렌더·단발 본문 추출) | `https://r.jina.ai/<URL>` | 정찰·단발 본문용, 대량 수집엔 부적합 |

> **비공식 내부 엔드포인트는 Phase 0 이 아니다.** 사이트가 문서화하지 않은 JSON 엔드포인트는
> 공인 경로가 아니라 **사다리 2단(숨은 API)** 이다 — 정찰로 찾아내는 것이고, 약관이 그 사용을
> 금지하는지는 별도로 확인해야 한다. 이 표는 제공자가 명시적으로 여는 경로만 담는다.

**판정:** Phase 0로 데이터가 충분히 나오면 → 정찰 스킵, Step 3 분류 트리도 건너뛰고 수집(Step 4)으로. 안 되면 → Step 2 정찰로 정상 진행.

---

## Step 2: 정찰 (agent-browser)

### Step 2-0: robots.txt 확인 (필수 · 정찰 전)

정찰 요청을 보내기 **전에** 한 번 확인한다. 산문 지시가 아니라 실제 호출이다:

```python
from utils import check_robots

verdict = check_robots(target_url)
if verdict["error"]:
    # 가져오지 못한 것과 허용된 것은 다르다 — 사용자에게 '확인 못 함' 으로 알린다
    ...
elif not verdict["allowed"]:
    # 차단 — 진행 여부를 사용자에게 묻는다. 임의로 진행하지 않는다
    ...
if verdict["crawl_delay"]:
    limiter = RateLimiter(delay=max(verdict["crawl_delay"], 1.0))
```

- **차단이면 사용자 확인 없이 진행하지 않는다.**
- `crawl_delay` 가 있으면 RateLimiter 기본값보다 우선한다.
- `error` 가 있으면 "허용됨" 이 아니라 "확인 못 함" 이다 — 사용자에게 그대로 알린다.
- robots.txt 는 법적 구속력이 없지만 표지판이다. 무시했다는 사실은 "알고도 했다" 의 정황이 된다.

> **agent-browser는 이 프로젝트의 표준 정찰 도구다 (선택 아님).** 단순 정적 사이트를 긁더라도 정찰 단계에서는 agent-browser를 먼저 사용한다.
>
> **시작 전 (양 host 공통)**: 우선 `agent-browser skills get core --full`을 실행해 agent-browser 사용법(snapshot-and-ref 워크플로우, 네트워크 캡처 등)을 로드한다. 설치된 구버전이 `Unknown command: skills`를 반환하면 `agent-browser --help`에서 snapshot/network 명령을 로드한다. 이 오류만으로 agent-browser 자체가 불능이라고 판정하거나 폴백으로 내려가지 않는다.
>
> CLI가 없거나 브라우저 실행이 막힌 제한 환경에서만 아래 **정찰 폴백 티어**로 내려간다. 환경 셋업·검증은 `scripts/setup.ps1`(Windows) 또는 `scripts/bootstrap.py` + `scripts/preflight.py`.
>
> | 티어 | 도구 | host |
> |---|---|---|
> | 표준 | `agent-browser` | 양 host 공통 |
> | 폴백 1 (Claude) | **Claude in Chrome** (`mcp__claude-in-chrome__*`) | Claude Code / Cowork 전용 |
> | 폴백 1 (Codex) | **ChatGPT Chrome 플러그인 Browser Use** (`chrome:control-chrome`) | Codex 전용 (Chrome 확장 연결 시) |
> | 폴백 2 (공통) | Scrapling `DynamicFetcher` / Playwright `sync_api` | 양 host 공통 |
>
> **host별 분기:** Claude Code/Cowork는 `agent-browser → Claude in Chrome → 폴백 2`, Codex는 `agent-browser → ChatGPT Chrome Browser Use(연결 시) → 폴백 2`다. Codex에 `chrome:control-chrome` 스킬이 없거나 ChatGPT Chrome 확장이 연결되지 않으면 Codex 폴백 1을 건너뛴다. Codex에서 Claude in Chrome을 찾지 않는다.
>
> 폴백을 썼으면 어느 티어였는지 Step 5-A의 profile.json `notes`에 남긴다.

### 정찰 규칙
- agent-browser 접근 **최대 2회** 시도
- 2회 실패 시 **Step 3 의 이음매 통지 게이트로 돌아간다** — 정찰 단계에서도 사다리 B 진입은 사용자 확인을 거친다
- 같은 도메인에 **5분 내 3회 이상 접근하지 않음**
- **정찰 JS 는 ASCII 로만 쓴다.** `agent-browser eval -b <base64>` 가 페이로드를 UTF-8 이 아닌
  인코딩으로 디코딩해 한글이 깨진다 — `/입찰|공고/` 가 `/?낆같|怨듦퀬/` 로 들어가
  `SyntaxError: Invalid regular expression` 이 난다. 한글이 필요하면
  `'\uC785\uCC30'`(= 입찰) 처럼 유니코드 이스케이프로 적는다. (파일을 만들 때도 `Get-Content -Raw` 는 UTF-8 을
  ANSI 로 읽으므로 애초에 ASCII 로 생성하는 편이 안전하다.)

### 정찰 항목
1. 스냅샷 + DOM 구조 확인
2. 데이터 로딩 방식 판단 (SSR / CSR / API / SPA 세션 보호 / infinite scroll)
3. CSS 셀렉터 식별
4. pagination 방식 (URL 파라미터 / next 버튼 / infinite scroll / scroll 페이지네이션)
5. 총 데이터 건수 추정

### 네트워크 감시 (필수)

agent-browser에서 네트워크 요청을 캡처하여 API를 식별한다.

**API 식별 2단계:**
1. **URL 패턴 휴리스틱**: `/api/`, `/graphql/`, `/v1/` 포함, `application/json` 응답, 광고/분석 제외
2. **LLM 응답 분석**: 후보 API의 JSON 응답에서 사용자 요청 항목과 매칭되는 필드 식별

**SPA 세션 보호 감지 (중요):**

정찰 중 다음을 확인하면 "SPA 세션 보호 사이트"로 분류:
- 브라우저에서는 검색/조회가 되지만 API 직접 호출 시 403/401 반환
- WebSquare, SAP UI5, Oracle ADF 등 엔터프라이즈 SPA 프레임워크 사용
- URL이 변하지 않는 SPA 내비게이션 (메뉴 클릭해도 URL 동일)
- XHR 요청에 서버 측 세션 토큰이 자동 포함됨

### Claude in Chrome 폴백 절차 (폴백 1)

agent-browser를 못 쓸 때 Claude 계열 host에서 쓴다. **사용자의 실제 Chrome**을 조종하므로 실제 쿠키·실제 IP가 그대로 붙는 것이 장점이다. 정찰 항목 5개는 그대로 대체된다.

| 정찰 항목 | 도구 |
|---|---|
| ① 스냅샷·DOM 구조 | `read_page` (a11y tree, `filter:"interactive"` / `depth` / `ref_id`로 축소) + `computer` 스크린샷 |
| ② 로딩 방식 판단 | `javascript_tool` — `#__next`/`#root`/`[data-reactroot]` 유무, 초기 DOM에 아이템이 있는지 |
| ③ CSS 셀렉터 | `javascript_tool` — 반복되는 `tag.class` 조합을 집계해 item_root 후보 도출 |
| ④ pagination | `javascript_tool` — `li.next a`/pager 텍스트/URL 패턴 |
| ⑤ 총 건수 | `javascript_tool` |

**네트워크 감시는 제약이 있다 (실측).** 아래 절차를 그대로 따르지 않으면 API를 못 찾는다.

1. **arming** — `read_network_requests`는 **처음 호출한 시점부터** 추적을 시작한다. 페이지를 연 직후 한 번 호출해 무장한다.
2. **navigate는 버퍼를 비운다** — 전체 리로드뿐 아니라 **SPA pushState 내비게이션에서도** 캡처가 초기화된다. 따라서 *페이지 로드 중에 나가는 XHR은 구조적으로 못 잡는다*.
3. **로드 후 액션으로 XHR을 재발생시킨다** — 스크롤(infinite scroll), 필터/정렬 변경, 다음 페이지 버튼 등 **내비게이션을 일으키지 않는** 상호작용을 준 뒤 `read_network_requests`를 읽는다.
4. **응답 본문은 안 나온다** — URL·method·statusCode만 반환한다. 위 "API 식별 2단계"의 2단계(JSON 필드 매칭)를 하려면, 후보 URL을 `javascript_tool`에서 페이지 컨텍스트로 재호출한다:
   ```js
   // 페이지 컨텍스트라 세션 쿠키·헤더가 그대로 탑승한다 (정찰용 1회 호출)
   await fetch('<후보 API URL>', {cache:'no-store'}).then(r => r.json())
   ```
   `fetch`·`XMLHttpRequest` 둘 다 캡처 대상임은 확인됐다. 광고·분석 픽셀(criteo/adnxs/facebook)과 RUM(Datadog `browser-intake-datadoghq.com/api/v2/rum`)이 진짜 API보다 훨씬 많으므로, `urlPattern`을 `/api/`가 아니라 **1st-party 도메인**으로 걸어 읽는다.

**값 마스킹에 주의한다 (실측).** Claude in Chrome은 자격증명처럼 보이는 값을 자동으로 가린다 — `[BLOCKED: JWT token]`, `[BLOCKED: Cookie/query string data]`, `[BLOCKED: Base64 encoded data]`. 원시 덩어리를 통째로 뽑으면 정작 필요한 부분이 가려진다:

- ❌ `el.outerHTML` 통째 덤프, `JSON.parse(...)` 결과 전체 반환, 쿼리스트링 포함 URL 그대로 반환
- ✅ **속성·키 이름 단위로 뽑는다** — `Object.keys(obj)`, `el.className`, `el.getAttribute('href')`, `locator.count()`
- 응답 구조를 볼 때도 값이 아니라 키만: `Object.keys(j)`, `Object.keys(j.data[0])`

즉 마스킹은 정찰을 막지 않는다. 정찰에 필요한 건 값이 아니라 **구조**이므로, 처음부터 키·개수·셀렉터만 뽑으면 걸리지 않는다.

> **여기서도 수집은 금지다.** `javascript_tool`은 구조 파악과 API 후보 1회 검증에만 쓴다. 페이지 안에서 루프 돌려 전량 추출하는 것은 절대 규칙 2 위반 — 수집은 `crawl_script.py`로 한다.
>
> **원격 전용 환경(Cowork)에서는 정찰까지만 가능하다.** 샌드박스 egress가 기본 "package managers only"라 대상 사이트 직접 접속이 막히고, 통과시켜도 데이터센터 IP라 안티봇 프로필이 재현되지 않으며, VM에서 호스트 Chrome의 CDP 포트(9222)에 붙을 수 없어 Akamai 대응이 불가능하다. 원격에서는 정찰 → profile.json 갱신까지 하고, 수집은 로컬에서 이어서 실행한다.

### ChatGPT Chrome Browser Use 폴백 절차 (Codex 폴백 1)

agent-browser를 못 쓰고 현재 Codex 세션에 `chrome:control-chrome` 스킬이 있으며 사용자의 ChatGPT Chrome 확장이 연결돼 있을 때만 쓴다. 스킬을 먼저 읽고 그 Bootstrap·Chrome 선택 절차를 그대로 따른다. 반드시 `agent.browsers.get("chrome")`으로 **Chrome을 명시 선택**하고, 연결 후 `chrome.nameSession(...)`을 호출한 다음 탭을 생성하거나 사용자가 지정한 탭을 claim한다. 다른 브라우저 surface로 자동 대체하지 않는다.

이 경로는 **사용자의 실제 Chrome**을 조종하므로 기존 브라우저 상태·로그인 세션·실제 IP가 적용되는 것이 장점이다. 단 브라우저 쿠키·localStorage·프로필·비밀번호를 직접 조회하지 않는다.

| 정찰 항목 | Browser Use API |
|---|---|
| ① 스냅샷·DOM 구조 | `tab.playwright.domSnapshot()` + 필요 시 `tab.screenshot()` |
| ② 로딩 방식 판단 | `tab.playwright.evaluate()`의 read-only page scope에서 `#__next`/`#root`/`[data-reactroot]`·초기 아이템 유무 확인 |
| ③ CSS 셀렉터 | `tab.playwright.locator()`의 `count()` 또는 read-only `evaluate()`로 반복되는 `tag.class` 조합과 매칭 개수만 집계 |
| ④ pagination | `locator()`/`evaluate()`로 next/pager URL·텍스트 확인 후 `expectNavigation()` + `click()`으로 1회 검증 |
| ⑤ 총 건수 | read-only `evaluate()`로 표시 총계 또는 `총 페이지 × 페이지당 건수` 확인 |

**네트워크 감시는 제한적이다 (실측).**

1. `tab.capabilities.list()`에 `pageAssets`가 있으면 해당 capability의 `documentation()`을 먼저 읽고 `pageAssets.list()`로 현재 페이지에서 관찰된 script/image/stylesheet/font URL을 확인한다.
2. Browser Use 공개 API는 일반 document/XHR/fetch 요청 목록과 응답 status/header/body 캡처를 제공하지 않는다. read-only `evaluate()` scope에서도 `window.performance`/`document.defaultView.performance`를 사용할 수 없었다.
3. 따라서 `/api/`·`/graphql/`·`/v1/` 후보나 JSON 응답 필드 매핑이 필요한 사이트는 **네트워크 감시 부분에 한해** 폴백 2의 Playwright `sync_api`(`page.on("response")`)를 병행한다. profile.json `notes`에는 `Codex 폴백 1 Chrome Browser Use + 폴백 2 network 보조`처럼 둘 다 기록한다.

**실측 기준 (2026-08-19):** 실제 ChatGPT Chrome 확장 세션의 `books.toscrape.com`에서 DOM 스냅샷, `article.product_pod` 20개, `catalogue/page-{n}.html`, `Page 1 of 50`, 총 1000건을 재현했고 다음 페이지 클릭으로 `page-2.html → page-3.html` 패턴을 확인했다. `pageAssets`는 31개(이미지 21, 스크립트 6, 스타일시트 4)를 관찰했다. 이 사이트는 정적이라 XHR/API 후보는 없었다.

> **여기서도 수집은 금지다.** Browser Use의 `evaluate()`/locator는 구조·셀렉터·페이지네이션·건수 판정에만 쓴다. DOM을 루프로 전량 추출하지 않는다. 수집은 반드시 `crawl_script.py` 안의 Scrapling 또는 Playwright로 한다.

### Step 2-A: 인증 처리

로그인이 필요한 경우:

0. **먼저 `agent-browser close --all`.** 정찰로 이미 데몬이 떠 있으면 이후 호출의
   `--headed`·`--profile`·`--session` 이 **경고 한 줄만 남기고 무시된다**
   (`⚠ --profile ignored: daemon already running`). 창이 안 뜬 채로 "로그인해 주세요" 라고
   말하게 되는 실패가 여기서 나온다.
1. 전용 프로필로 **보이는 창**을 띄운다 — `agent-browser --headed --profile <경로> open <로그인URL>`.
   사용자의 평소 Chrome 프로필을 붙이지 않는다(다른 사이트 세션까지 딸려온다).
   경로를 주면 로그인이 그 디렉터리에 남아 다음 호출에서도 유지된다.
2. 사용자에게 안내하고 **직접 로그인하도록 기다린다.** ID/PW 를 대신 입력하지 않고,
   코드·파일·메모리 어디에도 저장하지 않는다. CAPTCHA·2단계 인증도 사용자가 처리한다.
3. 로그인 여부를 **쿠키 이름으로 확인한다** — 값은 출력하지 않는다.
   (예: 네이버 `NID_AUT`/`NID_SES`, 인스타그램 `sessionid`/`ds_user_id`)
4. `agent-browser state save <스크래치경로>` 로 받은 뒤 **대상 도메인분만 골라**
   `output/<도메인>/cookies.json` 에 넣는다 — 프로필 전체 쿠키를 프로젝트 폴더로 옮기지 않는다.
5. 수집 시 주입은 **요청별 인자**로 한다: `session.get(url, cookies=jar)`.
   `session.cookies.update(jar)` 는 동작하지 않는다(`_SyncSessionLogic` 에 `.cookies` 없음).

---

## Step 3: 사이트 분류 & 수집 전략 결정

정찰 결과로 사이트를 분류하고 수집 전략을 고른다. 전체 워크플로우에서 가장 중요한 결정이다.

> **Phase 0 선행 확인됨 가정.** 여기 오기 전 [Step 1-B](#step-1-b-phase-0-공인-우회로-체크)에서 공인 API/피드(yt-dlp·RSS·oEmbed·Jina)를 이미 확인했다. Phase 0로 해결됐으면 이 트리를 건너뛴다.

### 사다리는 둘이 이어붙은 것이다

```
사다리 B   "상대가 나를 막고 있다"      ← 돌파. 통지 후 진행
──────────────────────────────────    ← 이음매: 성격이 바뀌는 지점
사다리 A   "데이터가 어디 있나"         ← 탐색. 자동
```

1~3단에서 사이트는 나를 막은 적이 없다. **데이터가 있는 위치가 다를 뿐이다.** 4단부터가 처음으로 "상대가 나를 식별하고 거절한" 상황이다. 통지 게이트가 정확히 이 이음매에 놓이는 것은 우연이 아니다.

### 사다리 A — 데이터가 어디 있나 (자동 · 통지 없음)

| 칸 | 비유 | 판별 | 도구 | 페이지당 요청 |
|---|---|---|---|---|
| **0** 공식 API·공개데이터 | 그냥 주는 것 | 개발자 문서 / data.go.kr | `plain_session` | 1 |
| **1** 정적 HTML | 종이에 글자가 이미 있다 | `Ctrl+U` 소스에 보임 | `plain_get` | 1 |
| **2** 숨은 API | 종이엔 없고 **전화번호**가 적혀 있다 | Network 탭 XHR 응답에 데이터 | `plain_session` | 1 |
| **3** 렌더링 | 전화를 **브라우저만** 걸 수 있다 | 내부 주소 직접 호출 시 토큰·서명 부족 | `DynamicFetcher` | **수십~수백** |

- **2단이 사다리의 심장이다.** 가장 자주 정답이고 가장 자주 건너뛰어진다. WAF 가 감지돼도 API 를 찾으면 우회 없이 끝나는 경우가 많다 — **우회한 게 아니라 우회할 필요가 없는 길을 찾은 것.**
- **3단의 더 나은 변형**: 화면을 그리되 DOM 을 읽지 말고 **응답을 가로챈다**(`page.on("response")`). 브라우저는 띄우되 데이터는 JSON 으로 받으므로 정확하고 구조 변경에 강하다.
- **비용 절벽은 2→3 사이다.** 요청 수가 1 → 수십~수백으로 뛴다(부담 축과 직결).
- **위장 경계는 3→4 사이다.** 사다리 A 에서는 지문을 위장하지 않는다. `plain_get`/`plain_session` 이 `impersonate`·`stealthy_headers` **두 인자를 함께** 꺼서 이 경계를 실제로 성립시킨다. **하나만 끄면 불일치 지문이 되어 오히려 악화된다.**

### ■ 이음매 — 통지 게이트 ■

**사다리 A 를 소진했고 다음이 사다리 B 라면, 자동으로 넘어가지 않는다.** 사용자에게 한 번 알린다:

```
이 사이트는 자동 접근을 차단하고 있습니다 (<감지된 유형>).
다음 단계는 그 차단을 우회하는 것입니다.
 · 수집 권한이나 정당한 사유가 있는지 확인하세요
 · 참고: 공식 API·데이터 개방·제휴 경로나 대체 데이터원이 있으면 그쪽이 낫습니다
계속하시겠습니까?  [진행 / 중단]
```

- **'진행' 이면 그대로 사다리 B 로 간다.** 근거를 묻지도 검증하지도 않는다.
- **통지는 이음매를 통과할 때마다 한 번이다.** '도메인당 한 번' 이 아니다 — 면제하는 것은 도메인이 아니라 그 프로필이 **지금 들고 있는 `consent` 기록**이다. 한 번 통과한 뒤 B 안에서 4→5→6 으로 더 올라가는 것은 다시 묻지 않는다(이음매는 한 곳이고 이미 넘었다).
- 선택 사실과 시각을 프로필 `consent` 블록에 남긴다 (Step 5-A). 이게 없으면 프로필 저장이 거부된다.
- **이미 `consent` 기록이 있는 프로필이면 통지하지 않는다.** 그 기록 자체가 이 사용자가 이 도메인에서 통지받고 진행을 골랐다는 증거다(sticky). 프로필이 있어도 `consent`가 없다면(예: 사다리 A로만 수집돼 오다가 이번에 처음 사이트가 막은 경우) 이번이 최초로 이음매를 넘는 것이므로 그대로 통지한다.
- **B → A → B 로 돌아온 도메인은 다시 묻는다.** 사다리 A 로 내려간 수집에서 프로필이 배포 대상이 되면 `save()` 가 `consent` 를 지운다 — 사용자가 언제 무엇을 통지받았는지를 배포되는 프로필에 실어 내보낼 수 없기 때문이다. 그래서 사이트가 나중에 새로 막기 시작하면 들고 있는 기록이 없고, 그대로 다시 통지한다. **그게 맞다 — 사이트가 새 보호를 건 것은 달라진 상황이고, 이음매를 다시 건너는 것은 새로운 사건이다.**
- **CAPTCHA 도 같은 층위다** — 자동으로 풀지 않는 것은 그대로지만, 통지 없이 조용히 중단하지도 않는다. 다른 경로가 있는지 함께 제시한다.

### 사다리 B — 상대가 막고 있다 (통지 후 진행)

| 칸 | 무엇이 걸렸나 | 무엇을 하나 | 도구 |
|---|---|---|---|
| **4** 지문 정렬 | **목소리** — "크롬입니다" 라고 말했는데 TLS 협상 지문이 파이썬 | 협상 지문을 실제 크롬과 동일하게. **브라우저 안 띄움** | `curl_cffi` 그리드 |
| **5** 스텔스 브라우저 | **걸음걸이** — `navigator.webdriver`, 폰트·캔버스 지문, 직선 마우스 | 브라우저를 띄우되 자동화 흔적을 지움 | `StealthyFetcher` |
| **6** 실제 크롬 | 위 전부가 안 통함 | 흉내가 아니라 **실제 사용자 프로필 Chrome** 을 띄우고 그 안에서 fetch | `chrome_cdp` |

> **B 는 순차가 아니다.** 고급 WAF 는 4·5 단이 원리적으로 통하지 않아 **바로 6 단**으로 간다. WAF capability 라우팅은 `references/antibot-strategies.md` 참조. **단 그 라우팅도 통지 이후에 일어난다.**

### 증상 → 칸 판별표

| 증상 | 무슨 뜻 | 칸 |
|---|---|---|
| `Ctrl+U` 소스에 글자 있음 | 종이에 적혀 있다 | 1 |
| 소스엔 없는데 Network 에 JSON | 전화번호가 있다 | 2 |
| 내부 주소 호출 시 401·토큰 필요 | 전화는 브라우저만 건다 | 3 |
| 헤더 다 맞췄는데 403 | **지문**에서 걸렸다 | **4** ⚠ |
| 챌린지 페이지 / "봇 감지" | **행동**에서 걸렸다 | **5** ⚠ |
| `_abck` 쿠키 · `Access Denied` | 고급 WAF | **6** ⚠ |

⚠ = 통지 대상. 이 표의 위 셋과 아래 셋은 성격이 다르다 —
**위 셋은 내가 안 갖춘 것(고쳐라), 아래 셋은 상대가 안 주는 것(멈추고 물어라).**

### 오르내리는 규칙

```
올리려면:   ① 아래 칸이 실패했다는 '확인' (추측 아님)
            ② 4단 이상이면 사용자의 한 번의 진행 선택 (이미 `consent` 기록이 있는 프로필이면 면제)

내려오기:   6단으로 성공했어도 영구 자격이 아니다.
            사이트 구조가 바뀌면 다시 1단부터 판별한다.
```

### 각 전략의 코드 패턴

> 📖 상세 코드 템플릿은 `references/fetcher-patterns.md` 를 참조한다.

| 칸 | 전략 | 도구 | 참조 섹션 |
|---|------|---------|----------|
| 0·2 | API 직접 | `plain_session` | fetcher-patterns.md § API 수집 |
| 1 | 정적 HTML | `plain_get` | fetcher-patterns.md § 정적 HTML |
| 3 | JS 렌더링 | `DynamicFetcher` | fetcher-patterns.md § 동적 사이트 |
| 3 | SPA 세션 인터셉트 | Playwright 인터셉트 | antibot-strategies.md § SPA 세션 |
| 4 ⚠ | 경량 그리드 | `curl_cffi` 그리드 | antibot-strategies.md § curl_cffi 그리드 |
| 5 ⚠ | 스텔스 | `StealthyFetcher` | antibot-strategies.md § Cloudflare |
| 6 ⚠ | 실제 크롬 | Chrome CDP | antibot-strategies.md § 고급 WAF |

### 안티봇 감지 시그널

> 📖 상세 감지 로직은 `references/antibot-strategies.md` 참조.

**Akamai 계열**: `_abck`/`bm_sz`/`ak_bmsc` 쿠키, `Access Denied` + `errors.edgesuite.net`
**Cloudflare**: `cf_clearance` 쿠키, 챌린지 페이지
**SPA 세션 보호**: 브라우저에서는 정상인데 API 직접 호출 시 403 (ErrorCode -801 등) — 이건 3단이지 우회 대상이 아니다

### Step 3.5: API 필드 매핑 검증

API 사용 시, 코드 생성 전에 샘플 5건으로 필드 매핑을 검증한다:
1. API 1페이지 호출 → JSON 구조 확인
2. 사용자 요청 필드 ↔ API 필드 매핑표 작성
3. null/빈값 비율, 병합 필요 여부 확인

---

## Step 4: 수집 코드 생성 & 실행

Step 3에서 결정한 전략에 맞는 코드 패턴을 `references/fetcher-patterns.md`에서 참조하여 crawl_script.py를 생성한다.

### 모든 수집 코드의 필수 요소

1. **try/except + continue** — 한 페이지 실패가 전체를 중단시키지 않도록
2. **consecutive_errors 추적** — 연속 5회 실패 시에만 최종 중단
3. **RateLimiter** — `scripts/utils.py`의 RateLimiter 사용
4. **부분 데이터 저장** — 100건마다 raw_data.json에 중간 저장
5. **FETCHER_CHAIN 에스컬레이션** — 연속 2회 실패 시 상위 티어로 전환. **체인은 사다리 A(3단)에서 끝난다** — 사다리 B 진입은 Step 3 의 통지 게이트를 거친다
6. **0건이면 기존 산출물을 덮지 않는다** — 같은 출력 폴더로 재실행하는 것은 흔한 일이고, 실패한 재실행이 성공했던 `raw_data.json` 을 빈 배열로 밀어버리면 "이번 실패" 가 "지난 성공 소실" 이 된다. 쓰기 직전에 `if not data: return` 로 막거나, 기존 파일이 있으면 `raw_data.json.bak` 로 옮긴 뒤 쓴다

> **except 블록에서 반드시 `continue`** — 절대 `break`로 중단하지 않는다.

### 출력 디렉토리 구조

```
output/<도메인>/<주제_YYYYMMDD_HHMMSS>/
├── crawl_script.py    # 생성된 수집 스크립트
├── raw_data.json      # 원시 데이터
├── crawl_result.xlsx   # 엑셀 결과
└── progress.json       # 진행 상황
```

### 셀렉터 자가 치유

```python
# 첫 수집: 핑거프린트 저장
items = page.css("<SELECTOR>", auto_save=True,
    storage_args={"storage_file": "./fingerprints/elements_storage.db"})

# 이후: 자가 치유
items = page.css("<SELECTOR>", adaptive=True, auto_save=True,
    storage_args={"storage_file": "./fingerprints/elements_storage.db"})
```

---

## Step 5: 데이터 검증

### Step 5.0: 소프트블록 게이트 (최우선 — 다른 검증보다 먼저)

> **HTTP 200 = 성공이 아니라 "검증 시작"이다.** Akamai/DataDome/PerimeterX는 200 OK로 가짜 챌린지 페이지나 빈 셸을 돌려준다. 0건이 아니라 **"쓰레기 N건"으로 통과**해 엑셀로 납품되는 사고를 막는 게 이 게이트의 목적이다. (insane-search R2 차용)

**언제 실행하나:** 첫 페이지 응답 직후(대량 루프 진입 전)와, Step 5 검증 시작 시 1회. 즉 **수집 전·후 양쪽**에서 건다.

```python
from utils import detect_softblock

# 첫 페이지 본문 + status + 쿠키로 판별 (cookies는 session.cookies 등에서 dict로)
verdict = detect_softblock(
    page.html_content,                 # 또는 resp.text
    status=page.status,
    cookies=dict(session.cookies) if hasattr(session, "cookies") else None,
    selector_hit=bool(page.css("<ITEM_SELECTOR>")),  # 핵심 콘텐츠 셀렉터 매칭 여부
)
if verdict["blocked"]:
    logger.error(f"소프트블록 감지 — {verdict['verdict']}: {verdict['signals']}")
    #   무엇이 감지됐든, 다음 단계가 사다리 B(4단 이상)라면 **먼저 Step 3 의 이음매 통지 게이트를 거친다.**
    #   소프트블록 감지는 "상대가 나를 식별하고 거절했다" 는 신호다 — 즉 이음매에 도달했다는 뜻이지,
    #   이음매를 건너뛰어도 된다는 뜻이 아니다.
```

**게이트 규칙:**
1. `blocked=True`면 **수집을 강행하지 않는다.** 에스컬레이션 여부는 규칙 2(이음매 통지 게이트)를 따른다 — 게이트를 통과해 상위 단계로 가도 안 뚫리면 사용자에게 보고 후 중단.
2. 소프트블록으로 판정되면 **수집을 멈추고 Step 3 의 이음매 통지 게이트로 돌아간다.**
   감지된 유형(Akamai 시그널 / 챌린지 / 빈 셸)은 게이트 문구의 `<감지된 유형>` 에 넣는다.
   사용자가 '진행' 을 고른 뒤에야 WAF capability 라우팅(4·5 를 건너뛸지 등)을 적용한다.
3. `weak_ok`(셀렉터 미검증 통과)는 통과시키되, 수집 후 필드 채움률이 비정상적으로 낮으면 이 게이트를 의심한다.

### 일반 검증

1. 수집 건수 확인 (목표 대비 %)
2. 각 필드별 null/빈값 비율 체크
3. 샘플 확인 (처음 5건 + 마지막 5건)
4. 중복 제거
5. PII 감지: `detect_pii(data)` 실행
6. robots.txt 제한 발견 시 사용자에게 경고

95% 이상 유효 데이터면 통과. 미달 시 Step 4 재시도 (최대 2회).

> 📖 수집 실패 시 원인 진단은 `references/troubleshooting.md`를 참조한다.

### 값이 그럴듯한가 (필수)

건수와 null 비율만 보면 **광고를 상품으로 가져온 경우를 통과시킨다.** 자가치유 셀렉터는
"못 찾겠다" 고 말하지 않고 늘 무언가를 반환하기 때문이다.

```python
from utils import validate_values

issues = validate_values(results, {
    "상품명":   {"type": "str", "required": True, "max_empty_ratio": 0.1},
    "가격":     {"type": "int", "required": True, "min": 1, "max": 100_000_000},
    "카테고리": {"type": "str", "required": True, "allow_uniform": True},  # 한 페이지가 단일 카테고리일 수 있다 — 균일해도 정상
})
if issues:
    logger.warning("값 검증 경고:\n" + "\n".join(issues))
```

- `allow_uniform: True`는 그 필드의 **중복률 검사만** 면제한다 — 카테고리·플래그·정액
  배송비처럼 전부 같은 값이어도 정상인 필드에 쓴다. 명시적으로 걸지 않은 필드는 10건 이상
  전부 동일하면 그대로 경고한다(셀렉터가 광고·머리글 등 고정 요소를 잡았을 가능성).
- `adaptive=True` 로 요소를 **재탐색한 행**에는 플래그 컬럼을 남겨 엑셀에서 구분되게 한다.
- 문제가 있으면 사용자에게 그대로 보고한다 — 조용히 진행하지 않는다.

---

## Step 5-A: 도메인 프로필 저장 (필수 게이트)

검증을 통과한 직후, **반드시** `fingerprints/<도메인>/profile.json`을 저장하거나 갱신한다. 이걸 빼먹으면 다음 수집 시 정찰부터 다시 해야 하고, 다른 머신/세션에서는 노하우가 완전히 사라진다.

```python
from domain_profile import DomainProfile
from datetime import date

profile_mgr = DomainProfile()  # base_dir=./fingerprints
profile_mgr.save(domain, {
    "domain": domain,
    "capability": "<static|js_render|api|session>",   # ★ SSOT — 능력 수준. 비워 두면 save() 가 fetcher_type 에서 채운다
    "fetcher_type": "<yt-dlp|RSS|oEmbed|Jina|Fetcher|FetcherSession|DynamicFetcher|DynamicSession|Spider|playwright_spa_intercept|curl_cffi_grid|StealthyFetcher|chrome_cdp|API_SESSION>",   # 파생 — 현재 엔진에서의 구현체. 앞 4개는 Step 1-B Phase 0 공인 우회로
    "antibot_type": "<none|cloudflare|akamai|spa_session|naver_antibot|other>",
    "antibot_strategy": "<none|playwright_intercept|impersonate|curl_cffi_grid|stealthy|chrome_cdp|naver_antibot|authenticated_browser>",   # 실제로 쓴 대응. 사다리 B 를 썼으면 반드시 그 값을 적는다
    "site_type": "<static|csr|api|spa_session|akamai>",
    # robots·ToS 사유로 배포에서 빼야 하면 명시 — 사다리 A 여도 이 선언은 무조건 인정된다
    "distribution": "local", "distribution_reason": "<한 줄>",
    "selectors": {<필드: 셀렉터>},
    "pagination": {<config — type/param/limit 등>},
    "api_endpoints": [{<url, method, params, field_mapping>}],
    "notes": "<다음 사람이 정찰 없이 바로 수집할 수 있는 결정적 한두 줄>",
    "last_used": str(date.today()),
    # 사다리 B(4단 이상)로 수집했을 때만. **실제로 통지했고 사용자가 '진행' 을 고른 경우에만 적는다** —
    # 그 일이 없었으면 이 블록을 적지 않는다. 적으면 기록이 거짓이 되고, 이 기록의 유일한 쓸모가 사라진다.
    # 근거가 아니라 선택을 적는다. 이미 `consent` 기록이 있는 프로필이면 자동으로 이어지므로(sticky) 생략해도 된다.
    "consent": {"notified_at": "<통지한 실제 시각 ISO8601>", "choice": "proceed"},
})
```

### 게이트 규칙

1. **`notes` 필드는 비워두지 않는다.** 다음 사람(미래의 나 포함)이 정찰 안 하고도 바로 수집할 수 있는 한두 줄의 결정적 정보를 적는다 — "API key는 OK, job_group_id=518이 일반 목록", "리스트는 SSR HTML, 상세는 XHR JSON — 2단으로 충분", "review API는 POST에 originProductNo 필요" 같은 형식.
2. **인증 토큰/쿠키/내부 API key는 profile.json에 박지 않는다.** `.gitignore`가 `cookies*.json`/`*auth*.json`/`*token*.json`/`*secret*`은 차단하지만 profile.json은 commit 대상이므로 평문 자격증명이 새지 않게 분리한다.
3. **fetcher_type / antibot_strategy 둘은 무조건 채운다.** 다음 실행에서 Step 1-A가 이 두 값만 보고 fetcher chain을 건너뛰므로, 빈 값이면 게이트 기능을 못 한다.
4. **사다리 B 로 수집했으면 `antibot_strategy` 에 그 사실을 적는다.** `none` 으로 적으면 분류기가 탐색 단계로 오판해 그 레시피를 배포 대상에 넣고 `consent` 기록도 지운다. 실제로 쓴 것을 적을 것.
   **`Spider` 는 티어가 아니라 래퍼다** — 밑에서 실제로 쓴 티어를 적는다.
5. 사다리 B 프로필은 `consent` 없이는 저장이 거부된다(`ConsentRequired`). 심사가 아니라 기록이다. 인식되지 않는 `fetcher_type`/`antibot_strategy` 값도 같은 예외로 저장을 막는다 — 이때는 통지를 기록할 게 아니라 값을 문서화된 것으로 고쳐야 한다.
6. **이미 profile이 있으면 `last_used`만 갱신하지 말고**, 이번 수집에서 새로 알아낸 게 있으면 `notes`와 endpoint/selector를 누적/수정한다.

저장이 끝나면 Step 6으로 진행. profile.json 저장 실패 시 수집 결과는 살아있어도 **"파이프라인 미완료"**로 보고하고 사용자에게 원인을 알린다 (디스크 권한, 스키마 누락 등).

---

## Step 6: 엑셀 출력 & 보고

```python
from export_excel import export_to_excel
export_to_excel(data, filepath)
```

### 완료 보고 항목
- 엑셀 파일 경로
- 수집 건수 / 목표 건수 (%)
- 각 필드별 채움률
- 누락/에러 건수
- 소요 시간
- 사용된 Fetcher 유형
- **`fingerprints/<도메인>/profile.json` 저장 여부 (신규 / 갱신 / 실패)** — 실패면 사유 명시

---

## 레퍼런스 가이드

| 파일 | 내용 | 언제 참조 |
|------|------|----------|
| `references/fetcher-patterns.md` | 모든 수집 패턴의 코드 템플릿 | Step 4에서 crawl_script.py 생성 시 |
| `references/antibot-strategies.md` | Akamai, SPA 세션, Cloudflare 대응 전략 | Step 3에서 안티봇 감지 시 |
| `references/troubleshooting.md` | 실패 사례와 해결책 | 수집 실패 시 원인 진단 |
| `scripts/scrapling_reference.md` | Scrapling API 레퍼런스 (Fetcher 종류·Selector·Spider·세션) | 라이브러리 사용법이 헷갈릴 때 |
