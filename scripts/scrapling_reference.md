# Scrapling API 참조 가이드

> 에이전트가 수집 코드를 동적 생성할 때 참조하는 Scrapling API 요약.
> Python 3.14 호환 확인 완료.

---

## 1. Fetcher (기본 HTTP)

가장 가볍고 빠른 Fetcher. SSR(서버 사이드 렌더링) 사이트에 적합.

```python
from scrapling.fetchers import Fetcher

fetcher = Fetcher()
page = fetcher.get("https://example.com")

# 응답 속성
page.status      # int: HTTP 상태 코드
page.url         # str: 최종 URL (리다이렉트 후)
page.encoding    # str: 문서 인코딩
```

### CSS 셀렉터

```python
# 단일 값
title = page.css("h1::text").get()           # str | None
title = page.css("h1::text").get("")          # str (기본값 "")
href = page.css("a::attr(href)").get()        # 속성 값

# 복수 값
texts = page.css("h1::text").getall()         # list[str]

# 요소 리스트
items = page.css("div.product")               # list[Adaptor]
for item in items:
    name = item.css("h2::text").get("").strip()
    price = item.css(".price::text").get("").strip()

# 속성 접근
el = page.css("div.item")[0]
classes = el.attrib.get("class", "")          # 속성 dict
```

### XPath

```python
title = page.xpath("//h1/text()").get()
items = page.xpath("//div[@class='product']")
```

### JSON 응답 (API)

```python
resp = fetcher.get("https://api.example.com/data")
data = resp.json()   # dict | list — Fetcher 응답에도 .json() 메서드 존재
```

### 주의사항

> ⚠️ `Fetcher.configure()` 는 **파서 전용**이다. `impersonate` 같은 fetch 인자를 받지 않는다
> (`ValueError: Unknown parser argument: "impersonate"`). 위장 기본값을 끄려면
> `scripts/utils.py` 의 `plain_get()` / `plain_session()` 을 쓴다.
- JS 렌더링 불가 — CSR 사이트에서는 빈 결과 반환

---

## 2. StealthyFetcher (안티봇 우회)

Cloudflare 등 안티봇 보호를 우회하는 브라우저 기반 Fetcher.

```python
from scrapling.fetchers import StealthyFetcher

fetcher = StealthyFetcher()
page = fetcher.fetch("https://example.com", headless=True)

# Cloudflare 우회
page = fetcher.fetch("https://example.com", headless=True, solve_cloudflare=True)
```

### 주요 차이점

| | Fetcher | StealthyFetcher |
|---|---------|-----------------|
| 메서드 | `.get(url)` | `.fetch(url)` |
| JS 렌더링 | X | O (브라우저) |
| 안티봇 우회 | X | O |
| 속도 | 매우 빠름 | 느림 |

### 주의사항

- `quotes.toscrape.com/js/`는 Fetcher 0건, StealthyFetcher 10건 수집 가능 (JS 렌더링)
- headless=True 권장 (GUI 불필요)

---

## 3. DynamicFetcher (브라우저 렌더링)

Playwright 기반 브라우저 렌더링. JS 렌더링이 필요한 CSR 사이트에 적합.

```python
from scrapling.fetchers import DynamicFetcher

fetcher = DynamicFetcher()
page = fetcher.fetch("https://example.com", network_idle=True)
```

### 파라미터

- `network_idle=True` — 네트워크 요청이 안정될 때까지 대기 (추천)
- `headless=True` — GUI 없이 실행

---

## 4. DynamicSession (Infinite Scroll)

브라우저 세션을 유지하며 스크롤, 클릭 등 상호작용 가능.

```python
from scrapling.fetchers import DynamicSession

with DynamicSession(headless=True) as session:
    page = session.fetch("https://example.com", network_idle=True)

    # 스크롤
    session.execute_script("window.scrollTo(0, document.body.scrollHeight)")

    # 재렌더링 대기 후 재파싱
    import time; time.sleep(2)
    page = session.fetch("https://example.com", network_idle=True)
```

---

## 5. FetcherSession (HTTP 세션)

HTTP 세션을 유지하며 쿠키/헤더를 자동 관리. API 수집에 최적.

```python
from scrapling.fetchers import FetcherSession

with FetcherSession(impersonate='chrome') as session:
    resp = session.get("https://api.example.com/data", stealthy_headers=True)
    data = resp.json()

    # 쿠키 주입
    resp = session.get(url, cookies={"session": "abc123"})

    # 헤더 주입
    resp = session.get(url, headers={"Authorization": "Bearer TOKEN"})
```

---

## 6. Spider (대규모 수집)

비동기 크롤러. 500건+ 대규모 수집에 적합. 자동 체크포인트/resume 지원.

```python
from scrapling.spiders import Spider, Request, Response
from scrapling.fetchers import AsyncFetcherSession

class MySpider(Spider):
    name = "my_spider"
    start_urls = ["https://example.com/page-1.html"]
    concurrent_requests = 5    # 동시 요청 수

    def configure_sessions(self, manager):
        manager.add("default", AsyncFetcherSession(impersonate="chrome"))

    async def parse(self, response: Response):
        # 아이템 yield
        for item in response.css("div.product"):
            yield {
                "title": item.css("h2::text").get("").strip(),
                "price": item.css(".price::text").get("").strip(),
            }

        # 다음 페이지 follow
        next_page = response.css("a.next::attr(href)").get()
        if next_page:
            yield response.follow(next_page)

    async def on_scraped_item(self, item):
        """아이템 후처리. None 반환 시 아이템 드롭, item 반환 시 유지."""
        return item

    async def on_error(self, request: Request, error: Exception):
        """에러 핸들러. request 인자 필수."""
        print(f"Error: {error}")

    async def on_close(self):
        """Spider 종료 시 호출."""
        print("Spider closed")

# 실행
result = MySpider(crawldir="./crawl_data").start()

# 결과
result.items          # 수집된 아이템 리스트
result.completed      # bool: 완료 여부
result.stats          # dict: 통계
len(result.items)     # 수집 건수

# JSON 저장
result.items.to_json("./output/raw_data.json", indent=True)
```

### crawldir (체크포인트)

- `crawldir` 지정 시 자동 체크포인트 생성
- 중단 후 동일 `crawldir`로 `start()` 호출하면 이어서 수집
- **완료 시 체크포인트 자동 정리** ("Checkpoint file cleaned up")

### concurrent_requests 가이드

| 규모 | concurrent_requests |
|------|-------------------|
| ~500건 | 5 |
| 500~2000건 | 5 |
| 2000건+ | 3 |

---

## 7. Adaptor (파서)

HTML 문자열을 직접 파싱. 셀렉터 자가 치유에 사용.

```python
from scrapling.parser import Adaptor

html = "<div class='item'><h2>Product</h2></div>"
adaptor = Adaptor(html, url="https://example.com")

# CSS 셀렉터
items = adaptor.css("div.item h2")

# 자가 치유는 생성자에서 켠다 — storage_args 는 .css() 인자가 아니다 (0.4.x: TypeError)
adaptor = Adaptor(html, url="https://example.com", adaptive=True,
    storage_args={"storage_file": "./fingerprints/elements_storage.db",
                  "url": "https://example.com"})   # url 이 없으면 도메인 구분 없이 'default' 버킷

# auto_save: 셀렉터 핑거프린트 저장
items = adaptor.css("div.item", auto_save=True)

# adaptive: 셀렉터 변경 시 저장된 핑거프린트로 자동 복구
items = adaptor.css("div.item", adaptive=True, auto_save=True)
```

`Adaptor` 는 `Selector` 의 별칭이다(`scrapling/parser.py` 끝의 `Adaptor = Selector`). 생성자에
`adaptive=True` 가 없으면 `.css(auto_save=True)`/`adaptive=True` 는 경고만 남기고 무시된다.

---

## 8. 셀렉터 자가 치유

Scrapling의 핵심 기능. 셀렉터가 변경되어도 핑거프린트 기반으로 자동 복구.

> ⚠️ scrapling 0.4.x 의 `Selector.css()` 시그니처는 `(selector, identifier='', adaptive=False,
> auto_save=False, percentage=40)` 다. **`storage_args` 를 `.css()` 에 넘기면
> `TypeError: Selector.css() got an unexpected keyword argument 'storage_args'`** (2026-09-01
> books.toscrape.com 실측). 저장소는 파서를 만드는 쪽에서 지정한다 — `Fetcher.configure()` 가
> 받는 파서 인자(`huge_tree, adaptive, storage, keep_cdata, storage_args, keep_comments,
> adaptive_domain`)에 `adaptive`/`storage_args` 가 들어 있다.

```python
from pathlib import Path
from scrapling.fetchers import Fetcher

STORAGE = {"storage_file": "./fingerprints/elements_storage.db", "url": url}
Path("./fingerprints").mkdir(exist_ok=True)   # 디렉터리가 없으면 sqlite 가 응답 파싱 시점에 죽는다
Fetcher.configure(adaptive=True, storage_args=STORAGE)   # 전역. 요청별로는 Fetcher.get(url, selector_config={...})

# 첫 수집: 핑거프린트 저장
page = Fetcher.get(url)   # utils.plain_get(url) 도 내부가 Fetcher.get 이라 같은 설정을 탄다
items = page.css("<SELECTOR>", auto_save=True)

# 이후 수집: 자가 치유 — 저장소 오류(잠김·권한)가 수집을 죽이지 않게 감싼다
page = Fetcher.get(url)
try:
    items = page.css("<SELECTOR>", adaptive=True, auto_save=True)
except Exception as exc:   # 자가치유만 포기하고 일반 셀렉터로 계속
    print(f"자가치유 저장소 사용 불가: {exc}")
    items = page.css("<SELECTOR>")
```

- 핑거프린트 저장 경로: `./fingerprints/elements_storage.db` (sqlite, 도메인별 버킷은 `storage_args["url"]` 로 나뉜다).
  지정하지 않으면 기본값은 site-packages 안의 `scrapling/elements_storage.db` 다.
- 세션(`FetcherSession`/`plain_session`)은 `Fetcher.configure()` 를 읽지 않는다 —
  `FetcherSession(selector_config={"adaptive": True, "storage_args": STORAGE})` 로 세션에 직접 넘긴다.

---

## 9. Fetcher 선택 의사결정 트리

```
API 발견? ──Yes──→ FetcherSession (가장 빠르고 안정적)
   │
   No
   │
JS 렌더링 필요? ──Yes──→ DynamicFetcher (Playwright 브라우저 렌더링)
   │
   No
   │
plain_get (1단 — 위장 없는 평문 HTTP)
```

안티봇 보호가 있는 사이트는 이 트리 밖이다. 위 세 갈래(사다리 A, 1~3단)를 소진했다는 것은
사이트가 나를 식별하고 거절했다는 뜻이므로, 자동으로 `StealthyFetcher`/Chrome CDP 로 넘어가지
않고 사용자에게 한 번 확인한다. 상세는 `.claude/skills/web-crawler/references/fetcher-patterns.md`.

## 10. 에스컬레이션 체인

자동 전환은 **사다리 A(1~3단)에서 끝난다:**

```
plain_get → plain_session → DynamicFetcher
  1단 정적    2단 숨은 API    3단 JS 렌더링
```

그 위 티어(`curl_cffi` 그리드 · `StealthyFetcher` · `chrome_cdp`)는 **능력으로 전부 남아 있되
자동 체인에 없다.** 3단까지 소진했다는 것은 사이트가 나를 식별하고 거절했다는 뜻이므로,
그 지점에서 자동으로 넘어가지 않고 사용자에게 한 번 확인한다.
상세는 `.claude/skills/web-crawler/references/fetcher-patterns.md`.

## 11. 구현 시 발견된 사항

- Scrapling Fetcher 응답에 `.json()` 메서드 존재 → FetcherSession 없이도 API JSON 파싱 가능
- `Fetcher.configure()` 는 **파서 전용**이다 — `impersonate` 등 fetch 인자를 받지 않는다(`ValueError`). 위장 기본값을 끄려면 `scripts/utils.py` 의 `plain_get()` / `plain_session()` 을 쓴다
- 셀렉터 자가치유의 `storage_args` 는 `.css()` 인자가 아니라 파서 생성 인자다(0.4.15 실측 `TypeError`). `Fetcher.configure(adaptive=True, storage_args=...)` / `Adaptor(..., adaptive=True, storage_args=...)` / `FetcherSession(selector_config=...)` 로 지정한다 — §8 참조
- Windows cp949 인코딩 문제: stdout에 `£` 등 특수문자 출력 시 `io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')` 필요
- Spider 완료 시 crawldir 체크포인트를 자동 정리함
- Spider `on_error` 시그니처: `(self, request: Request, error: Exception)` — request 인자 필요
- Spider `on_scraped_item` 반환값: `None` 반환 시 아이템 드롭, `item` 반환 시 유지
