# 안티봇 대응 전략 레퍼런스

> ## ■ 이 문서의 우회 티어는 전부 통지 이후에 쓴다 ■
>
> **사다리 B(4~6단) 절** — `WAF capability 라우팅` · `curl_cffi 경량 그리드` ·
> `URL 변형 / referer 트릭` · `Akamai/고급 WAF → Chrome CDP` · `Cloudflare → StealthyFetcher` ·
> `우회 티어는 통지 후 진행` — 은 상대가 나를 식별하고 거절한 뒤에 쓰는 방법들이다.
> 사다리 A(정적 HTML · 숨은 API · JS 렌더링)를 소진하기 전에는 그 절들을 열 이유가 없다.
>
> **사다리 B 에 진입할 때는 자동으로 넘어가지 않고 사용자에게 한 번 알린다.**
> '진행' 을 고르면 그대로 간다 — 근거를 묻지도 검증하지도 않는다. 통지는 심사가 아니다.
> 문구와 발동 조건은 `SKILL.md` Step 3 "이음매 통지 게이트".
>
> **나머지 절은 사다리 A 에서도 쓴다** — `소프트블록 탐지`(모든 수집의 사전 게이트) ·
> `SPA 세션 인터셉트`(3단) · `Jina Reader 폴백`(1단) · `종료 사유 분류`. 이 절들은 그 자체로
> 이음매를 넘지 않는다. 다만 소프트블록이 잡히면 그 순간이 **이음매에 도달한** 순간이므로,
> 사다리 B 로 올리기 전에 게이트로 돌아간다.
>
> 능력은 전부 여기 그대로 있다. 바뀐 것은 **침묵**이다.

사이트의 봇 차단 메커니즘별 대응 전략을 정리한 문서.
SKILL.md Step 3에서 안티봇이 감지되면 이 문서를 참조한다.

## 목차

1. [소프트블록(가짜 200) 탐지 — 모든 수집의 사전 게이트](#소프트블록가짜-200-탐지)
2. [WAF capability 라우팅 — 왜 Stealthy 말고 CDP인가](#waf-capability-라우팅)
3. [curl_cffi 경량 그리드 — 브라우저 전 저비용 돌파](#curl_cffi-경량-그리드)
4. [URL 변형 / referer 트릭](#url-변형--referer-트릭)
5. [Akamai/고급 WAF → Chrome CDP](#akamai고급-waf--chrome-cdp)
6. [SPA 세션 보호 → Playwright 인터셉트](#spa-세션-보호--playwright-인터셉트)
7. [Cloudflare → StealthyFetcher](#cloudflare--stealthyfetcher)
8. [Jina Reader 폴백](#jina-reader-폴백)
9. [종료 사유 분류 — terminal vs retryable](#종료-사유-분류)
10. [우회 티어는 통지 후 진행](#우회-티어는-통지-후-진행)

> 1~4·8·9번은 insane-search(접근/돌파 관점)에서 차용한 전략이다. 5~7번은 이 프로젝트의 검증된 수집 전략.

---

## 소프트블록(가짜 200) 탐지

**HTTP 200 = 성공이 아니라 "검증 시작"이다.** (insane-search R2) WAF는 200 OK로 챌린지/빈 셸을 돌려주는 경우가 많아, 그대로 파싱하면 "0건"이 아니라 **"쓰레기 N건"이 통과**한다. 수집 직전(첫 페이지)과 Step 5 검증에서 `utils.detect_softblock()`로 거른다.

### 4단계 AND 검증

| # | 검사 | 차단 시그널 |
|---|------|------------|
| 1 | 챌린지 마커 부재 | `sec-if-cpt-container`, `Access Denied`, `errors.edgesuite.net`, `Pardon Our Interruption`(PX), `captcha-delivery.com`(DataDome), `Just a moment...`(CF) |
| 2 | 응답 크기 정상 | < 3KB 또는 WAF 특유 고정 크기 |
| 3 | 쿠키 센서 정상 | **`_abck=...~-1~`** = Akamai 미통과(아직 차단) 상태 — 존재 여부가 아니라 **값**을 본다 |
| 4 | success selector 매칭 | 핵심 콘텐츠 셀렉터 hit → `strong_ok`, 미제공 → `weak_ok` |

```python
from utils import detect_softblock

v = detect_softblock(page.html_content, status=page.status,
                     cookies=dict(session.cookies) if hasattr(session, "cookies") else None,
                     selector_hit=bool(page.css("<ITEM_SELECTOR>")))
# v["blocked"]가 True면 수집 강행 금지 → **Step 3 의 이음매 통지 게이트로 돌아간다.**
# 소프트블록 감지는 "상대가 나를 식별하고 거절했다" 는 신호다 — 이음매에 도달했다는 뜻이지
# 이음매를 건너뛰어도 된다는 뜻이 아니다. 사용자가 '진행' 을 고른 뒤에 capability 라우팅을 적용한다.
```

> ⚠️ `_abck` 쿠키 **존재**만으로 Akamai를 판정하던 기존 로직보다, `~-1~` **값**이 더 날카롭다. 통과(`~0~`/`~N~`)면 수집 진행, 미통과(`~-1~`)면 차단으로 본다.

---

## WAF capability 라우팅

WAF를 "탐지"만 하지 말고 **"이 WAF를 뚫으려면 무엇이 필요한가"**로 분기한다. (insane-search 차용)

| WAF 유형 | 필요 역량 | 올바른 도구 | curl_cffi/Stealthy로 되나? |
|----------|----------|------------|---------------------------|
| Cloudflare 기본 | JS 실행 | StealthyFetcher / DynamicFetcher | ✅ (Stealthy `solve_cloudflare=True`) |
| DataDome / PerimeterX / F5 / 단순 403 | TLS 지문 위조 | **curl_cffi 그리드** 먼저 → 안되면 브라우저 | ✅ 종종 그리드로 뚫림 |
| **Akamai Bot Manager** | **실제 TLS 스택 + 행동** | **Chrome CDP (headed real Chrome)** | ❌ **안 됨** |

### 왜 Akamai엔 curl_cffi/StealthyFetcher가 안 되나 (헛고생 방지)

- Akamai Bot Manager는 TLS 지문 + HTTP/2 프레이밍 + 마우스/타이밍 행동 신호를 종합한다. curl_cffi의 TLS 위조만으로는 `_abck` 센서가 `~-1~`에서 안 풀린다.
- **headless/일반 Playwright(MCP 포함)는 탐지 가능한 stub을 주입**하므로 Akamai에 걸린다. 그래서 **headed real Chrome + CDP**라야 한다.
- 결론: `antibot_type=akamai` 또는 `_abck ~-1~` 이 잡히면 curl_cffi·Stealthy 는 원리적으로 통하지 않는다 — **이음매 통지 게이트를 먼저 거친 뒤**, 사용자가 '진행' 을 고르면 4·5 단을 건너뛰고 6단으로 간다. 이게 시간 절약의 핵심이고, 건너뛰는 것은 4·5 단이지 이음매가 아니다.

---

## curl_cffi 경량 그리드

브라우저를 띄우기 전, **TLS 지문 위조 HTTP 요청을 격자로 완전탐색**해 저비용으로 뚫는 단계. (insane-search Phase 1 차용) DataDome/PerimeterX/단순 403에 효과적. **Akamai는 제외**(위 capability 라우팅 참조).

### 그리드 축 (개념 — 정확한 impersonate 값/규칙의 단일 출처는 `fetcher-patterns.md § F` 코드)

```
impersonate     × url_transform        × referer_strategy
─────────────     ─────────────────       ────────────────
safari17_0        원본 URL                self-root (도메인 루트)
chrome131         www→m. (모바일)         google_search
chrome120         am- prefix              none
firefox133        www 제거
safari_ios (모바일)
```

각 셀을 시도하고 **매 응답마다 `detect_softblock()`로 검증** — 200이어도 통과로 치지 않는다. 모든 셀 소진 후에도 `blocked`면 브라우저 단계(StealthyFetcher → DynamicFetcher)로 에스컬레이션.

> 코드 템플릿은 `fetcher-patterns.md § F: curl_cffi 경량 그리드` 참조.

---

## URL 변형 / referer 트릭

브라우저 없이 공짜로 시도하는 우회. 그리드의 일부지만 단독으로도 효과가 커서 따로 둔다.

| 트릭 | 방법 | 왜 통하나 |
|------|------|----------|
| 모바일 서브도메인 | `www.x.com` → `m.x.com` / `am-x.com` | 모바일 엔드포인트는 WAF가 약하게 걸린 경우 흔함 |
| www 제거 | `www.x.com` → `x.com` | 리다이렉트 체인/엣지 룰 차이 |
| self-root referer | `Referer: https://x.com/` | 내부 네비게이션처럼 보임 |
| 검색엔진 referer | `Referer: https://www.google.com/` | 크롤러/SEO 트래픽으로 허용되는 경로 ⚠️ ToS 경계 주의 — 사다리 B 티어이므로 통지 게이트를 거친 뒤에 쓴다 |

---

## Akamai/고급 WAF → Chrome CDP

### 감지 시그널

다음 중 **하나라도** 발견되면 Akamai로 판단한다. 사다리 B 진입이므로 통지 게이트를 먼저 거치고, '진행' 이면 4·5단을 건너뛰고 Chrome CDP 전략으로 간다:
- `Access Denied` 페이지 + `errors.edgesuite.net` 참조
- `_abck`, `bm_sz`, `ak_bmsc` 쿠키 존재
- `sec-if-cpt-container` 챌린지 페이지
- profile.json 에 `antibot_type: akamai` 로 기록된 도메인

### 핵심 원칙

- **일반 FETCHER_CHAIN을 사용하지 않는다** (StealthyFetcher, DynamicFetcher 시도하지 않음)
- **통지가 끝난 뒤에는 4·5단을 거치지 않고 곧바로 Chrome CDP로 전환한다** — 헛고생 방지
- headless Chrome은 Akamai에 탐지됨 → **headed Chrome** 필수 (macOS/Windows)

### Chrome CDP 수집 코드 패턴

```python
# Akamai 사이트 전용 — FETCHER_CHAIN 사용 금지
import sys, os, json, time
sys.path.insert(0, './scripts')
from utils import RateLimiter, setup_logger
from export_excel import export_to_excel
from chrome_cdp import launch_chrome_cdp, close_chrome_cdp, get_playwright_cdp_connection

logger = setup_logger("akamai_crawler")
limiter = RateLimiter(delay=1.5)
results = []
consecutive_errors = 0

# 1) headed Chrome 을 임시 프로필로 띄운다 (기존 Chrome 은 모두 종료돼 있어야 한다).
#    상품/목록 페이지를 **먼저 열어** Akamai 쿠키를 받은 다음, 같은 세션에서 API 를 호출한다.
info = launch_chrome_cdp(port=9222, url="<TARGET_URL>")
browser = None
try:
    browser, context, page = get_playwright_cdp_connection(9222)
    page.goto("<TARGET_URL>", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(6000)

    for page_num in range(1, max_pages + 1):
        try:
            limiter.wait()
            # 2) 페이지 컨텍스트 안에서 fetch — 세션 쿠키·헤더가 그대로 탑승한다.
            data = page.evaluate(
                """async (n) => {
                    const resp = await fetch(`<API_URL>?page=${n}`);
                    return await resp.json();
                }""", page_num)
            # ... 데이터 파싱 ...
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            logger.warning(f"Page {page_num} error: {e}")
            if consecutive_errors >= 5:
                logger.error("5회 연속 실패, 중단")
                break
            continue

        # 100건마다 중간 저장 (0건이면 기존 파일을 덮지 않는다)
        if results and len(results) % 100 == 0:
            with open(raw_data_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
finally:
    if browser:
        browser.close()
    if info and not info.get("reused"):
        close_chrome_cdp(port=9222, cleanup_profile=True,
                         user_data_dir=info.get("user_data_dir"))
```

### JS 일괄 수집 규모별 패턴

| 규모 | 방식 | 이유 |
|------|------|------|
| ~200건 | JS 일괄 실행 | 빠르고 간단 |
| 200~2000건 | JS 일괄 + 배치 분할 | 메모리 안전 |
| 2000건+ | Python 루프 + 체크포인트 | 중간 저장, 재시도 필수 |

```python
# 배치 분할 패턴 (200~2000건)
BATCH_SIZE = 50
all_data = []

for batch_start in range(1, TOTAL_PAGES + 1, BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE - 1, TOTAL_PAGES)
    batch = page.evaluate(f"""
        async () => {{
            const data = [];
            for (let p = {batch_start}; p <= {batch_end}; p++) {{
                const resp = await fetch(`/api/endpoint?page=${{p}}&size=10`);
                const json = await resp.json();
                data.push(...json.data);
                await new Promise(r => setTimeout(r, 300));
            }}
            return data;
        }}
    """)
    all_data.extend(batch)
    # 중간 저장
    with open(raw_data_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
```

### Chrome CDP 사용 불가 시

StealthyFetcher → DynamicFetcher 순서로 폴백하되, 사용자에게 경고:
"Akamai 보호 사이트이므로 Chrome CDP가 필요합니다"

---

## SPA 세션 보호 → Playwright 인터셉트

### 감지 시그널

다음 조건이 모두 충족되면 SPA 세션 보호 사이트로 판단:
- 브라우저에서 정상적으로 데이터가 표시됨 (검색, 조회 가능)
- 동일한 API를 HTTP 클라이언트로 직접 호출하면 **403** 반환
- 에러 메시지 예: "접근 권한이 존재하지 않습니다" (ErrorCode -801)
- WebSquare, SAP UI5, Oracle ADF 등 엔터프라이즈 SPA 프레임워크 사용
- URL이 변하지 않는 SPA 네비게이션

### 왜 API 직접 호출이 안 되는가

이런 사이트들은 서버 측에서 SPA의 네비게이션 상태를 추적한다:
1. 메인 페이지 로드 → 서버 세션 생성
2. SPA 내 메뉴 클릭 → 서버가 현재 화면 상태를 기록
3. API 호출 시 서버가 "이 세션이 해당 화면에 있는가" 검증
4. 직접 API 호출은 이 상태 없이 오므로 403 거부

### 해결 전략: Playwright + 응답 인터셉트

SPA를 정상적으로 로드하고 UI를 조작하되, 데이터는 XHR 응답을 인터셉트하여 수집한다.

```python
"""SPA 세션 보호 사이트 수집 패턴 (g2b.go.kr 등)"""
import json, time
from playwright.sync_api import sync_playwright

all_items = []
collected_ids = set()

def on_response(response):
    """백그라운드 XHR 응답 리스너."""
    try:
        if "<API_PATH_KEYWORD>" in response.url and response.status == 200:
            data = response.json()
            items = data.get("result", [])
            for item in items:
                item_id = item.get("<ID_FIELD>", "")
                if item_id and item_id not in collected_ids:
                    collected_ids.add(item_id)
                    all_items.append(item)
            if items:
                print(f"[캡쳐] +{len(items)}건 (누적 {len(all_items)}건)")
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(locale="ko-KR")
    page = ctx.new_page()

    # 응답 인터셉터 등록
    page.on("response", on_response)

    # 1. 메인 페이지 로드
    page.goto("https://<DOMAIN>/", wait_until="networkidle", timeout=60000)

    # 2. SPA 내비게이션 (메뉴 클릭)
    page.locator('a:has-text("<MENU_1>")').first.click()
    page.wait_for_timeout(2000)
    page.locator('a:has-text("<MENU_2>")').first.click()
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle")

    # 3. 검색/조회 트리거 (UI 버튼 클릭)
    page.evaluate("""() => {
        document.querySelectorAll('button').forEach(btn => {
            if (btn.textContent.trim() === '<SEARCH_TEXT>') btn.click();
        });
    }""")
    page.wait_for_timeout(8000)

    # 4. 필요 시 페이지 사이즈 변경 + 적용
    page.evaluate("""() => {
        const sels = document.querySelectorAll('select');
        for (const sel of sels) {
            const opt = Array.from(sel.options).find(o => o.value === '100');
            if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event('change', {bubbles:true})); }
        }
    }""")
    page.wait_for_timeout(500)
    page.evaluate("""() => {
        document.querySelectorAll('button').forEach(b => {
            if (b.textContent.trim() === '적용') b.click();
        });
    }""")
    page.wait_for_timeout(8000)

    browser.close()

# all_items에 인터셉트된 데이터가 축적됨
```

### 핵심 포인트

1. **`page.on("response")`는 백그라운드 리스너** — expect_response와 달리 타이밍에 덜 민감
2. **UI 조작으로 API를 트리거** — fetch()로 직접 호출하면 403
3. **중복 제거** — 같은 데이터가 여러 번 인터셉트될 수 있으므로 ID 기반 중복 체크 필수
4. **`page.evaluate()`로 검색/적용 버튼 클릭** — Playwright의 locator보다 WebSquare 같은 프레임워크에서 안정적

---

## Cloudflare → StealthyFetcher

> **5단이다 — 통지 이후에 쓴다.** 아래 시그널은 사다리 B 진입 신호이지 바로 실행하라는
> 신호가 아니다. 한 번 알리고, '진행' 을 고르면 그대로 간다 (`SKILL.md` Step 3).

### 감지 시그널
- `cf_clearance` 쿠키
- Cloudflare 챌린지 페이지 (5초 대기 화면)

### 수집 패턴

```python
from scrapling.fetchers import StealthyFetcher

fetcher = StealthyFetcher()

# Cloudflare 보호 사이트
page = fetcher.fetch("<URL>", headless=True, solve_cloudflare=True)
```

---

## Jina Reader 폴백

JS 렌더링이 필요하거나 가볍게 막힌 페이지를 **브라우저 없이** 외부 렌더된 마크다운으로 받는 저비용 폴백. (insane-search 차용) 사다리 A 안에서 DynamicFetcher(3단)로 올리기 전, 또는 **이음매를 넘기 직전** 단계. 정찰 시 본문 빠른 확인용으로도 쓴다.

```python
from utils import plain_get   # Jina 는 사다리 A 쪽이다 — 위장 인자를 붙이지 않는다

resp = plain_get(f"https://r.jina.ai/{target_url}")  # 렌더된 markdown 반환
markdown = resp.text
```

- **용도**: 정찰·단발 본문 확인. 페이지네이션/대량 구조화 수집엔 부적합(레코드 추출이 아니라 본문 마크다운).
- **한계**: 강한 WAF(Akamai 등)는 Jina도 못 뚫는다. 여기서 막히면 사다리 A 가 소진된 것이므로 **이음매 통지 게이트로 간다** — Chrome CDP 는 그 뒤다.

---

## 종료 사유 분류

"못 뚫었다"를 선언하기 전, 종료 사유가 **terminal인지 retryable인지** 구분한다. (insane-search R6 차용) 잘못 분류하면 retryable을 포기하거나 terminal을 무한 재시도한다.

| 분류 | stop_reason | 대응 |
|------|------------|------|
| **terminal (즉시 종료)** | `auth_required`(로그인 필요), `404`, `paywall`, 명시적 ToS 차단 | 에스컬레이션 중단 → 사용자 보고. 더 시도해도 무의미 |
| **retryable (계속)** | `429`(rate limit), 네트워크 타임아웃, 일시적 5xx | **종료 아님.** 대기시간 2배(`limiter.backoff()`) 후 재시도. 429는 절대 "차단됨"으로 최종 판정하지 않는다 |
| **escalate (상위 도구)** | `challenge`/`blocked`(소프트블록) | 사다리 A 를 소진했으면 **이음매 통지 게이트**로 돌아간다. '진행' 이후에만 그리드 → Stealthy → CDP 로 올린다. 전부 소진 후에만 실패 선언 |

> **실패 선언 게이트:** ① 에스컬레이션 체인 소진 ② 남은 시도 경로 없음 ③ stop_reason이 terminal. 셋 다 충족 전엔 "이 사이트는 못 뚫는다"고 보고하지 않는다.

---

## 우회 티어는 통지 후 진행

아래 패턴은 사다리 B 안에서의 티어 전환이다. **B 에 처음 들어가는 순간에는 이미 통지가 끝나 있어야 한다** (SKILL.md Step 3). B 안에서 4→5→6 으로 옮겨가는 것은 다시 묻지 않는다 — 이음매는 한 곳이고 이미 넘었다.

범용 에스컬레이션 함수. 어떤 Fetcher를 사용해야 할지 불확실할 때 사용.

**순서: 평문 HTTP → curl_cffi 그리드(브라우저 X) → 브라우저 티어.** 그리드를 브라우저 앞에 둔다.

```python
from scrapling.fetchers import StealthyFetcher, DynamicFetcher
from scrapling import Selector
from utils import setup_logger, detect_softblock, plain_get
# fetch_via_grid 는 fetcher-patterns.md § F 참조

logger = setup_logger("escalation")

def _grid_tier(url):
    r, _ = fetch_via_grid(url)
    return Selector(r.text) if r else None

# 사다리 A 전용 체인(fetcher-patterns.md § FETCHER_CHAIN)과 다른 물건이다 — 이건 B 쪽이고,
# 여기 진입하기 전에 통지가 이미 끝나 있어야 한다.
# 아래 DynamicFetcher 는 `google_search` 기본값(=조작된 Google Referer)을 그대로 둔다.
# 사다리 A 의 `plain_dynamic()` 이 그걸 끄는 것과 대비되는데, 실수가 아니라 층이 다르다 —
# 여기는 통지를 이미 마친 뒤이고, 우회 수단을 쓰기로 사용자가 고른 자리다.
FETCHER_CHAIN = [
    ("plain_get",       plain_get),                                           # 위장 없는 재시도 (맨 Fetcher().get 은 기본이 impersonate+stealthy_headers 라 평문이 아니다)
    ("curl_cffi grid",  _grid_tier),                                          # 4단 — 브라우저 앞 티어
    ("StealthyFetcher", lambda url: StealthyFetcher().fetch(url, headless=True)),
    ("DynamicFetcher",  lambda url: DynamicFetcher().fetch(url, network_idle=True)),
]

def fetch_with_escalation(url: str):
    for name, fetch_fn in FETCHER_CHAIN:
        try:
            page = fetch_fn(url)
            if page is None:                       # 그리드 미돌파 → 다음 티어
                logger.warning(f"[{name}] blocked, escalating")
                continue
            status = getattr(page, "status", 200)
            # 소프트블록 검증 — 200이어도 통과로 치지 않는다
            v = detect_softblock(getattr(page, "html_content", ""), status=status,
                                 selector_hit=bool(page.css("body")))
            if not v["blocked"]:
                logger.info(f"[{name}] Success ({v['verdict']})")
                return page, name
            logger.warning(f"[{name}] {v['verdict']}: {v['signals']}, escalating")
        except Exception as e:
            logger.warning(f"[{name}] Error: {e}, escalating")
            continue
    return None, None
```

> Akamai는 이 체인을 건너뛰고 통지 후 바로 Chrome CDP. curl_cffi/Stealthy로 Akamai를 두드리지 않는다.
