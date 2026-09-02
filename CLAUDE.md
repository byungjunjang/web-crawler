# 범용 웹 크롤링 에이전트

## 프로젝트 개요

이 프로젝트는 사용자가 URL과 수집 항목을 자연어로 설명하면, 자동으로 해당 웹사이트를 정찰하고 데이터를 대량 수집하여 엑셀 파일로 정리해주는 에이전트입니다.

---

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

## ★ 절대 규칙 0: 도메인 히스토리 우선 (모든 수집의 시작)

새 수집 요청을 받으면 **정찰하기 전에 반드시** 이 두 가지를 먼저 본다:

1. **`fingerprints/<sanitized_domain>/profile.json`** — 그 도메인의 검증된 수집 레시피 (fetcher_type, antibot_type/strategy, selectors, api_endpoints, pagination, notes)
2. **`output/<도메인>/`** — 그 도메인에서 이전에 실행된 수집 작업 폴더들 (그 안의 `crawl_script.py`/`raw_data.json`은 profile.json에 안 박힌 미세 디테일의 보조 reference)

### 운영 흐름

```
[수집 요청] → 도메인 추출 → fingerprints/<sanitized_domain>/profile.json 조회
                                    │
                ┌───────────────────┴───────────────────┐
                │ 프로필 있음                            │ 프로필 없음
                ▼                                       ▼
       ┌────────────────────────┐         ┌─────────────────────────┐
       │ 1. notes 먼저 읽고     │         │ 정찰 (Step 2) 부터 시작 │
       │    전략에 반영          │         │ — 모든 단계 풀 실행      │
       │ 2. fetcher_type/       │         └─────────────────────────┘
       │    antibot_strategy     │
       │    그대로 채택          │
       │ 3. selectors/endpoints │
       │    재사용 시도          │
       │ 4. last_used가 3개월+  │
       │    오래됐거나 사용자가  │
       │    "최신 구조로"를      │
       │    명시했으면 정찰 추가  │
       │ 5. 검증 실패하면 셀렉터/│
       │    엔드포인트만 정찰    │
       └────────────────────────┘
                │
                ▼
       채택한 값이 사다리 B(4단 이상)인가?
                │
        ┌───────┴────────┐
        │ 아니오(1~3단)   │ 예 — consent 기록이 있나?
        ▼                ├── 있음 → 통지 없이 진행 (sticky)
   그대로 진행            └── 없음 → **이번이 최초 통과다. 그대로 통지한다**
        │                          (프로필 재사용은 이음매 면제가 아니다)
        ▼
       정찰 스킵하고 Step 3 (수집 전략 수립)으로 점프
```

> **프로필이 있다는 사실 자체는 게이트를 면제하지 않는다.** 면제하는 것은 `consent` 기록이다.
> `antibot_strategy` 가 4단 이상인데 `consent` 가 없는 프로필은 "이 사용자는 아직 통지받은 적이
> 없다" 는 뜻이다 — 그대로 실행하면 통지 없이 사다리 B 를 돌게 되고, 수집이 다 끝난 뒤
> `save()` 가 `ConsentRequired` 로 막아 있지도 않았던 통지를 기록하도록 떠밀린다.
>
> **그래서 통지는 도메인당 1회가 아니라 이음매를 통과할 때마다 1회다.** 사다리 A 로 내려간
> 수집에서 프로필이 배포 대상이 되면 `save()` 가 `consent` 를 지운다 — 사용자의 통지 이력을
> 배포되는 프로필에 담아 내보낼 수 없기 때문이다. 그 도메인이 나중에 새 보호를 걸면 들고 있는
> 기록이 없으므로 다시 통지한다. **사이트가 새로 막은 것은 달라진 상황이니 그게 맞다.**

### 절대 안 되는 것

- profile.json이 있는데 그걸 무시하고 정찰부터 다시 하기 — 5~20분의 비싼 작업을 매번 반복하는 행위
- profile.json의 `notes` 필드를 읽지 않고 전략 세우기 — notes에는 LLM이 자동으로 못 알아내는 결정적 메타 정보가 박혀 있다 ("리스트는 SSR HTML, 상세는 XHR JSON — 2단으로 충분", "review API는 JSON 아니라 HTML 반환" 등)
- 수집 성공 후 profile.json 저장/갱신을 빠뜨리기 — Step 5-A 필수 게이트. 누락 시 "파이프라인 미완료" 보고

<!-- BEGIN GENERATED: domain-list -->
<!-- 이 블록은 scripts/sync_domain_list.py 가 생성한다. 직접 수정하지 말 것. -->

### 알려진 도메인 (14개 profile commit됨)

`books.toscrape.com`, `builtini.co.kr`, `celimax.co.kr`, `data.seoul.go.kr`, `db.itkc.or.kr`, `g2b.go.kr`, `guesskorea.com`, `made-in-china.com`, `wanted.co.kr`, `www.11st.co.kr`, `www.fss.or.kr`, `www.gsmarena.com`, `www.k-startup.go.kr`, `www.kurly.com` — 이 도메인들은 정찰 없이 바로 수집 시도 가능.

<!-- END GENERATED: domain-list -->

### profile 조회/저장 코드

```python
from domain_profile import DomainProfile
profile_mgr = DomainProfile()  # base_dir=./fingerprints

# Step 1-A: 조회
if profile_mgr.exists(domain):
    profile = profile_mgr.load(domain)
    # notes/fetcher_type/antibot_strategy/api_endpoints/selectors 활용

# Step 5-A: 수집 성공 후 저장 (필수 게이트)
profile_mgr.save(domain, {
    "domain": domain,
    "capability": "<static|js_render|api|session>",   # ★ SSOT — 능력 수준. 비워 두면 save() 가 fetcher_type 에서 채운다
    "fetcher_type": "<yt-dlp|RSS|oEmbed|Jina|Fetcher|FetcherSession|DynamicFetcher|DynamicSession|Spider|playwright_spa_intercept|curl_cffi_grid|StealthyFetcher|chrome_cdp|API_SESSION>",   # 파생 — 현재 엔진에서의 구현체. 앞 4개는 Phase 0 공인 우회로
    "antibot_type": "<none|cloudflare|akamai|spa_session|naver_antibot|other>",
    "antibot_strategy": "<none|playwright_intercept|impersonate|curl_cffi_grid|stealthy|chrome_cdp|naver_antibot|authenticated_browser>",   # 실제로 쓴 대응. 사다리 B 를 썼으면 반드시 그 값을 적는다
    "site_type": "<static|csr|api|spa_session|akamai>",
    "selectors": {...},
    "pagination": {...},
    "api_endpoints": [...],
    "notes": "<다음 사람이 정찰 없이 바로 수집할 수 있는 결정적 한두 줄>",
    # 사다리 B(4단 이상)로 수집했을 때만. **실제로 통지했고 사용자가 '진행' 을 고른 경우에만 적는다** —
    # 그 일이 없었으면 이 블록을 적지 않는다. 근거가 아니라 선택을 적는다.
    # 이미 consent 기록이 있는 프로필이면 자동으로 이어지므로(sticky) 생략해도 된다.
    "consent": {"notified_at": "<통지한 실제 시각 ISO8601>", "choice": "proceed"},
    "last_used": "YYYY-MM-DD",
})
```

> `fetcher_type`/`antibot_strategy` 는 위 목록 안의 값으로 적는다. 문서에 없는 값을 지어내면 분류기가 사다리 칸을 판별하지 못해 저장이 거부되고, 사다리 B 로 수집해 놓고 A 쪽 값을 적으면 그 레시피가 배포 대상으로 잘못 분류된다.
>
> **여기 목록이 곧 분류기가 아는 전부는 아니다.** 실제 판정표는 `scripts/profile_policy.py` 의 `TOOLS` 하나뿐이고, 위 목록은 그중 흔히 쓰는 값을 추린 것이다. 적을 값이 애매하면 지어내지 말고 그 표를 직접 본다 — 표에 없는 값은 `save()` 가 `ConsentRequired` 로 거부한다(심사가 아니라 "분류기가 알아들을 수 있는 값을 달라" 는 뜻이다).
>
> **`robots.txt`·ToS 사유로 배포에서 빼야 하는 프로필은 `distribution: "local"` 을 명시한다.** 사다리 A(1~3단)라 자동으로는 `public` 이 되는 프로필이라도 이 선언은 무조건 인정된다(조이는 방향은 항상 통과). 사유는 `distribution_reason` 에 한 줄로 남긴다 — 예: `cafe.naver.com`, `www.instagram.com`.

새 도메인 프로필을 처음 만들었다면 저장 직후 목록을 재생성한다 (위 "알려진 도메인" 블록은 생성물):

```bash
python scripts/sync_domain_list.py          # CLAUDE.md / README.md 목록 재생성
python scripts/sync_domain_list.py --check  # 어긋나면 exit 1
```

> ⚠️ profile.json은 git commit 대상이다. 토큰/쿠키/API key는 절대 박지 말고 `cookies.json`/`auth.json` 같은 별도 파일(.gitignore 차단됨)에 분리.

> 사다리 B 프로필은 `consent` 없이는 저장이 거부된다(`ConsentRequired`). 이건 심사가 아니라
> 기록이다 — 권한 근거를 적을 필요는 없고, 통지를 받고 진행을 골랐다는 사실만 남긴다.

---

## 범위 / 운영 안전 규칙

**포함**: 사이트 정찰, 구조 파악, 로그인 대응, 동적 콘텐츠, pagination, 대량 데이터 수집, 엑셀 출력.

**안전 규칙 (에이전트가 항상 지킴)**:
- **자동 접근 차단을 만나면 통지 후 사용자 선택** — CAPTCHA·WAF·봇 탐지는 법적으로 같은 보호조치다. 어느 쪽이든 **자동으로 넘어가지 않고 한 번 알리고 사용자가 고른다**. '진행' 이면 그대로 간다 — 근거를 묻지도 검증하지도 않는다. 상세는 SKILL.md Step 3 "이음매 통지 게이트"
- **CAPTCHA 자동 풀이 금지** — 통지와 별개다. reCAPTCHA/hCaptcha 를 프로그램으로 푸는 것은 하지 않는다. 사용자가 agent-browser 로 직접 푸는 것은 가능
- **로그인 자격증명 자동 저장 금지** — ID/PW를 코드/메모리/파일에 저장하지 않는다. 사용자가 직접 브라우저에서 로그인 → 쿠키만 추출
- **법적 위험이 큰 요청은 구체적으로 경고** — 저작권 침해 목적의 본문 복제(분량 축), 개인정보 대량 수집(성격 축), 명시적으로 금지된 재배포(목적 축). **어느 축이 왜 걸리는지 짚어서 알린 뒤 진행 여부는 사용자가 정한다** — 근거를 묻지도 검증하지도 않는다. **약관이 크롤링을 금지한다는 사실만으로는 여기 해당하지 않는다** — 그건 접근의 계약 층이고, 통지 게이트로 간다
- **robots.txt 제한 발견 시 사용자 확인** — `Disallow: /` 또는 수집 대상 경로 차단 시 진행 여부를 묻는다
- **PII 감지 (필수)** — 수집 데이터에 전화번호/주민번호/이메일 등이 섞이면 `detect_pii(data)`로 경고하고 사용자에게 보고

> **위 '경고' 규칙과 통지 게이트는 같은 층위다.** 경고는 요청이 **어떤 위험 축에 걸리는지**를,
> 게이트는 **기술적 차단을 만났다는 사실**을 알린다. 알리는 대상만 다를 뿐 둘 다 알리는 데서
> 끝나고 고르는 쪽은 사용자다 — 어느 쪽도 요청 자체를 막지 않으며, 근거를 묻지도 검증하지도
> 않는다. '진행' 을 뒤집는 근거로 쓰이지 않는다.
>
> 이 문서가 정의하는 것은 **도구의 동작**이다. 실행하는 AI 에이전트 자신의 판단 기준은 별개로
> 작동하며 이 문서가 그것을 대신 약속하지 않는다 — `ACCEPTABLE_USE.md` 참조.

---

## 핵심 도구

- **agent-browser** (Playwright): 정찰 전용 (표준) — 사이트 구조 파악, 네트워크 감시, 수동 로그인, 시각적 확인
- **Claude in Chrome** (`mcp__claude-in-chrome__*`): 정찰 **폴백 1 (Claude)** — agent-browser를 못 쓸 때만. Claude 계열 host(Claude Code/Cowork) 전용. 사용자 실제 Chrome을 조종 → 실제 쿠키·실제 IP. 절차는 SKILL.md Step 2 "Claude in Chrome 폴백 절차"
- **ChatGPT Chrome 플러그인 Browser Use** (`chrome:control-chrome`): 정찰 **폴백 1 (Codex)** — agent-browser를 못 쓰고 ChatGPT Chrome 확장이 연결될 때만. 사용자의 실제 Chrome 상태·세션·IP를 활용하되 쿠키·스토리지를 직접 읽지 않는다. 일반 XHR/fetch 응답 캡처는 지원하지 않아 필요 시 폴백 2의 Playwright `sync_api`로 네트워크 감시만 보조한다. 절차는 SKILL.md Step 2 "ChatGPT Chrome Browser Use 폴백 절차"
- **Scrapling** (Python): 수집 전용 — HTTP/브라우저 기반 데이터 수집, 셀렉터 자가 치유
- **openpyxl** (Python): 엑셀 파일 생성
- **DomainProfile** (`scripts/domain_profile.py`): 도메인 히스토리 load/save — 절대 규칙 0의 실행 도구

## 도구 역할 분리 원칙

| 작업 | 도구 | 이유 |
|------|------|------|
| **도메인 히스토리 조회/저장** | **DomainProfile (`scripts/domain_profile.py`)** | **재정찰 비용 회피 — 절대 규칙 0** |
| 사이트 열어서 구조 파악 | agent-browser | 시각적 확인, 네트워크 감시 가능 |
| 〃 — agent-browser 불가 시 | Claude in Chrome(Claude) / ChatGPT Chrome Browser Use(Codex, 연결 시) → DynamicFetcher/Playwright | host별 폴백 티어. 어느 티어를 썼는지 profile `notes`에 기록 |
| 수동 로그인 + 쿠키/JWT 추출 | agent-browser | 사용자 상호작용 필요 |
| 대량 데이터 수집 | Scrapling | 빠름, Fetcher 계층, 자가 치유 |
| 브라우저 세션이 필요한 사이트 대응 — **통지 이후** | Chrome CDP (`scripts/chrome_cdp.py`) | 4·5단이 원리적으로 안 통함 |
| 진행상황 체크포인트 | `scripts/progress.py` | 장시간 수집 시 pause/resume 지원 |
| 엑셀 출력 | openpyxl (`scripts/export_excel.py`) | 공통 모듈 |

**절대 agent-browser로 대량 수집하지 않는다.** 정찰과 수집은 분리. **Claude in Chrome과 ChatGPT Chrome Browser Use도 동일** — 정찰 전용이며 브라우저에서 전량 추출하는 것은 절대 규칙 2 위반.
**원격 전용 환경(Cowork 등)에서는 정찰까지만 가능하다.** 샌드박스 egress 기본값이 "package managers only"라 대상 사이트 접속이 막히고, 통과시켜도 데이터센터 IP라 안티봇 프로필이 재현되지 않으며, VM에서 호스트 Chrome CDP(9222)에 못 붙어 브라우저 세션이 필요한 사이트 대응이 죽는다. 원격은 정찰 → profile.json 갱신까지, 수집은 로컬에서.
**절대 profile 조회 없이 정찰부터 시작하지 않는다.** profile 우선.

## Fetcher 선택 의사결정 트리

```
Step 0: fingerprints/<sanitized_domain>/profile.json 있나? ──Yes──→
   │      └→ profile.capability / fetcher_type 그대로 채택
   │         (이미 consent 기록이 있으면 통지 없음 — 기록이 없으면
   │          이번이 최초 통과이므로 그대로 통지한다)
   No
   │
Phase 0: 공인 우회로 있나? ──Yes──→ yt-dlp / RSS·Atom / oEmbed / Jina(r.jina.ai)
   No
   │
┌─ 사다리 A — 자동 · 통지 없음 ────────────────────────────┐
│  API 발견?        ──Yes──→ 2단 plain_session             │
│  정적 HTML?       ──Yes──→ 1단 plain_get                 │
│  JS 렌더링 필요?  ──Yes──→ 3단 plain_dynamic             │
└──────────────────────────────────────────────────────────┘
   │
   │ 사다리 A 소진 = 상대가 나를 식별하고 거절했다
   ▼
■ 통지 게이트 ■  자동 진행을 멈추고 사용자에게 알린다  [진행 / 중단]
   │             '진행' 이면 그대로 간다. 근거는 묻지 않는다.
   ▼
┌─ 사다리 B — 통지 후 진행 ────────────────────────────────┐
│  기타 WAF·단순 403  → 4단 curl_cffi 그리드 (브라우저 X)   │
│  Cloudflare         → 5단 StealthyFetcher                │
│  Akamai/고급 WAF    → 6단 Chrome CDP (4·5 건너뜀)         │
└──────────────────────────────────────────────────────────┘
```

> **에스컬레이션 순서 = 가벼운 것부터.** 자동 체인은 `plain_get → plain_session → plain_dynamic` 으로 **사다리 A 에서 끝난다.** 그 위(`curl_cffi 그리드` · `StealthyFetcher` · `Chrome CDP`)는 능력으로 전부 남아 있되 **통지 이후에** 진입한다. Akamai 는 4·5 단이 원리적으로 안 통해 통지 후 바로 6단이다. 상세 코드는 `references/fetcher-patterns.md § F`, capability 판정 근거는 `references/antibot-strategies.md § WAF capability 라우팅`.

> **세 단 모두 래퍼를 쓴다.** 맨 `Fetcher.get()`/`FetcherSession()` 은 기본이 `impersonate="chrome"` + `stealthy_headers=True` 라 평문이 아니고, 맨 `DynamicFetcher.fetch()` 는 `google_search=True` 라 **`Referer: https://www.google.com/` 를 지어내 붙인다.** 사다리 A 는 통지 없이 도는 칸이므로 셋 다 끈 상태가 기본이다 — `plain_get()` · `plain_session()` · `plain_dynamic()`. (`fetcher_type` 에 기록하는 **어휘**는 그대로 `Fetcher`/`FetcherSession`/`DynamicFetcher` 다 — 래퍼 이름이 아니라 구현체 이름을 적는다.)

> profile.json이 있는 도메인은 Akamai 탐지 시그널을 따로 안 봐도 `antibot_type` 필드로 즉시 판정된다 (`antibot_type: akamai` → `chrome_cdp` 직행). 단 그 직행도 이음매 뒤에 있다 — 이미 `consent` 기록이 있으면 통지 없음, 기록이 없으면 이번이 최초 통과이므로 그대로 통지한다.

### Akamai 탐지 시그널

다음 중 하나라도 발견되면 Akamai/고급 WAF로 판단한다. 이건 **사다리 B 진입 신호**이므로 먼저 통지 게이트를 거치고, '진행' 이면 4·5단을 건너뛰고 바로 Chrome CDP로 간다:
- `Access Denied` + `errors.edgesuite.net` 참조
- `_abck`, `bm_sz`, `ak_bmsc` 쿠키 존재
- `sec-if-cpt-container` 챌린지 페이지

### Chrome CDP 전략 (브라우저 세션이 필요한 사이트 대응)

```bash
# 1. Chrome 실행 (사용자 Chrome 종료 필요)
chrome.exe --remote-debugging-port=9222 \
  --user-data-dir="C:/temp/crawl_profile" \
  --no-first-run --no-default-browser-check <URL>

# 2. 연결
# scripts/chrome_cdp.py 유틸리티 사용
# 또는 Playwright: p.chromium.connect_over_cdp("http://localhost:9222")
```

## Spider 활용 기준

| 조건 | 방식 |
|------|------|
| ~500건 미만, 단일 리스트 | `plain_session()` 순차 처리 |
| 500건 이상, 단일 리스트 | `Spider` + 단일 세션 (`concurrent_requests=5`) |
| 여러 카테고리 동시 수집 | `Spider` + multi-session routing |
| 장시간 수집 (1000건+) | `Spider` + `crawldir='./crawl_data'` (Ctrl+C 시 자동 체크포인트, 재실행 시 이어서) |

## Infinite Scroll 처리 (우선순위)

1. **API 직행**: 정찰 시 infinite scroll의 underlying API 엔드포인트 발견 → `plain_session()`으로 직접 호출 (가장 빠르고 안정적). 맨 `FetcherSession()`은 기본값이 `impersonate="chrome"` + `stealthy_headers=True` 라 사다리 2단이 아니다
2. **렌더 스크롤**: API 없으면 `DynamicSession(headless=True, google_search=False)`으로 스크롤 → `network_idle=True` 대기 → 추출 반복. 세션 쪽에는 래퍼가 없으므로 `google_search=False`를 직접 넘긴다 (기본값 `True`는 가짜 Google Referer를 붙인다)
3. **agent-browser 폴백**: 위 둘 다 실패 시 agent-browser로 수동 스크롤 → DOM 추출 → Scrapling Selector로 파싱

## Fetcher 에스컬레이션

수집 실패 시 상위 Fetcher로 전환하되, **자동 전환은 사다리 A 안에서만 일어난다**:
```
[자동] plain_get → plain_session → plain_dynamic
   │
   ■ 통지 게이트 ■  [진행 / 중단] — '진행' 이면 근거를 묻지 않고 그대로 간다
   │
[통지 후] curl_cffi 그리드 → StealthyFetcher → Chrome CDP
   (고급 WAF는 4·5단을 건너뛰고 바로 Chrome CDP)
   ※ B 안에서 4→5→6 으로 옮겨갈 때는 다시 묻지 않는다 — 이음매는 한 곳이다
```

> 체인을 다 소진해도 안 되면 agent-browser 정찰로 원인을 확인하고 사용자에게 보고한다 (agent-browser 로 수집하지는 않는다 — 정찰 전용).

### 에러별 대응표

| 에러 유형 | 대응 |
|----------|------|
| HTTP 429 (Rate Limit) | 대기 시간 2배 증가 후 재시도. 누적 3회면 사용자 보고 |
| HTTP 403 (Forbidden) | 사다리 A 가 남아 있으면 먼저 소진. 남은 게 없으면 **통지 게이트** → '진행' 이면 curl_cffi 그리드 → StealthyFetcher, 고급 WAF 시그널이면 바로 Chrome CDP |
| 가짜 200 (소프트블록) | `detect_softblock()`로 감지 — 챌린지/빈 셸/`_abck=~-1~`. 수집 강행 금지. 상위 티어가 사다리 B면 **통지 후** 에스컬레이션 |
| Cloudflare Challenge | 통지 게이트를 거친 뒤 `StealthyFetcher(solve_cloudflare=True)` (5단) |
| 셀렉터 매칭 실패 | `adaptive=True`로 자가 치유 시도. 재실패 시 정찰 재실행 |
| 페이지 구조 완전 변경 | 정찰 재실행 → profile.json의 selectors 갱신 |
| JS 렌더링 실패 | DynamicFetcher로 에스컬레이션. `disable_resources=True`로 경량화 |
| 네트워크 타임아웃 | 3회 재시도 후 해당 페이지 스킵 + 로그 |
| **수집 데이터 0건** | **즉시 중단, 사용자 보고** (계속 시도하면 ban 위험) |
| Spider 중단 (Ctrl+C) | `crawldir`에서 자동 체크포인트, 재실행 시 이어서 수집 |

## 수집 코드 생성 원칙

에이전트는 **(profile.json + 정찰 결과 + 사용자 요청)** 세 가지를 합성해 Python 수집 코드를 동적으로 생성한다.

- **profile.json 우선 활용**: `selectors`/`api_endpoints`/`pagination`이 있으면 그걸 기반으로 코드 골격을 짠다. 새로 정찰해서 코드를 처음부터 쓰지 않는다.
- **`output/<도메인>/` 의 이전 `crawl_script.py` 참조**: profile.json에 안 박힌 미세 디테일(배치 사이즈, JS evaluate 패턴, 예외 처리)을 그대로 가져와 재사용. 단, raw_data.json은 PII 가능성 있으므로 구조만 확인하고 데이터는 읽지 않는다.
- `scripts/utils.py`를 import하여 RateLimiter, cookie 관리, 로깅 등 공통 기능 사용
- `scripts/export_excel.py`를 import하여 엑셀 출력
- `scripts/chrome_cdp.py`는 `antibot_strategy: chrome_cdp`(사다리 6단)로 기록된 도메인에서 사용 — 통지 게이트를 이미 넘은 경우
- 수집 스크립트는 해당 작업의 출력 디렉터리 하에서 작업 (아래 출력 위치 참조)
- 셀렉터 핑거프린트 저장소는 **파서를 만드는 쪽**에서 지정 — `Fetcher.configure(adaptive=True, storage_args={"storage_file": "./fingerprints/elements_storage.db", "url": url})`. `.css()` 에 `storage_args` 를 넘기면 scrapling 0.4.x 에서 TypeError (SKILL.md § 셀렉터 자가 치유)
- **수집 성공 후 반드시 profile.json save/갱신** — 새로 알아낸 endpoint/selector/notes는 누적, `last_used`만 업데이트하지 말 것 (Step 5-A 게이트)
- **새 도메인이면 `python scripts/sync_domain_list.py` 실행** — CLAUDE.md/README.md의 "알려진 도메인" 목록은 profile.json에서 생성된다. 손으로 고치지 말 것 (`scripts/test_sync_domain_list.py`가 어긋남을 잡는다)

## 사용자 상호작용 규칙

### 에이전트가 자동 판단
- Fetcher 유형 선택
- 셀렉터 매핑
- pagination 방식
- 데이터 정제 수준
- 재시도/에스컬레이션 — **사다리 A 안에서만**

### 사용자에게 묻기
- **사다리 A→B 이음매를 넘을지 (통지 게이트)** — 자동 접근 차단을 만났을 때. 심사가 아니라 통지이고, '진행' 이면 근거를 묻지 않는다
- **법적 위험이 큰 요청을 진행할지** — 위 "범위 / 운영 안전 규칙" 의 경고 규칙. 어느 축이 왜 걸리는지 알리는 데서 끝나고, 고르는 쪽은 사용자다
- robots.txt 제한 시 진행 여부
- 디테일 페이지 크롤링 여부 (기본은 리스트만)
- 로그인 수행 요청
- 수집 결과가 기대와 다를 때 계속 진행할지

### 검증 통과 기준 (Step 5)

- 수집 건수가 목표 대비 **90% 이상** (API/HTML 수집)
- 전체 데이터의 **95% 이상이 유효** (Step 5 검증 통과)
- 각 필드별 **null/빈값 비율 10% 이하**
- 미달 시 Step 4 재시도 (최대 2회). 재실패 시 수집된 데이터로 진행하되 사용자에게 경고

## Rate Limiting

| 규모 | HTTP 요청 간격 | 브라우저 내 fetch 간격 | Spider concurrent_requests |
|------|---------------|----------------------|---------------------------|
| ~100건 | 1초 | 200ms | 해당 없음 |
| 100~500건 | 1.5초 | 300ms | 해당 없음 |
| 500~2000건 | 1.5초 | 500ms | 5 |
| 2000건+ | 2초 + 100건마다 15초 휴식 | 1초 + 50건마다 3초 휴식 | 3 |

브라우저 내 fetch는 동일 세션이므로 서버 부하가 상대적으로 낮음. 단, 봇 탐지 행동 분석에 걸리지 않도록 최소 200ms 간격 유지.

## 스킬 참조

크롤링 워크플로우 상세는 `.claude/skills/web-crawler/SKILL.md`를 따른다. Step 1-A(프로필 조회) ↔ Step 5-A(프로필 저장) 게이트가 포함된 7단계 흐름. 추가 레퍼런스:
- `.claude/skills/web-crawler/references/fetcher-patterns.md` — Fetcher별 코드 템플릿
- `.claude/skills/web-crawler/references/antibot-strategies.md` — Akamai/Cloudflare/SPA 세션 대응
- `.claude/skills/web-crawler/references/troubleshooting.md` — 수집 실패 진단

## 출력/저장 디렉터리 구조

```
output/                                  # gitignore — 수집 결과물
└── <도메인>/                            # 사이트별 폴더 (예: books.toscrape.com)
    ├── <크롤링주제_YYYYMMDD_HHMMSS>/    # 실행 건별 폴더
    │   ├── crawl_result.xlsx            # 최종 엑셀
    │   ├── raw_data.json                # 원시 수집 데이터
    │   ├── progress.json                # 진행상황
    │   └── crawl_script.py              # 생성된 수집 스크립트
    └── cookies.json                     # 사이트별 쿠키 (gitignore + cookies* 차단)

fingerprints/                            # gitignore + whitelist 정책
├── elements_storage.db                  # gitignore — Scrapling 셀렉터 자가 치유 DB (전역 공유)
└── <sanitized_domain>/                  # 예: books_toscrape_com, www_kurly_com
    ├── profile.json                     # 배포 판정 통과분만 tracked — 도메인 수집 레시피 (절대 규칙 0의 source)
    └── recipe.md                        # 배포 판정 통과분만 tracked (선택) — 추가 노트
```

### 규칙
- **사이트 폴더 (output/)**: 도메인 기준으로 하나만 생성 (예: `books.toscrape.com`, `www.kurly.com`)
- **작업 폴더**: `<주제요약>_<YYYYMMDD_HHMMSS>` 형식. 주제는 한글/영문 모두 가능, 공백은 `_`로 대체
- **쿠키**: 사이트 폴더 루트에 저장하여 같은 사이트의 모든 작업이 공유
- **셀렉터 핑거프린트**: `fingerprints/elements_storage.db` (전역 공유, ignore)
- **도메인 프로필**: `fingerprints/<sanitized_domain>/profile.json` (commit 대상). `sanitize_filename`은 `[^\w\-]`를 `_`로 치환 — 예: `books.toscrape.com` → `books_toscrape_com`, `made-in-china.com` → `made-in-china_com`

### .gitignore whitelist 정책

`fingerprints/**`로 전부 차단한 뒤(default-deny), **배포 판정을 통과한 프로필만** 도메인별 경로로 명시 whitelist 한다 — 이 목록은 `scripts/profile_policy.py` 의 판정 결과로 `scripts/sync_domain_list.py` 가 생성하므로 손으로 고치지 않는다. `!fingerprints/*/profile.json` 같은 와일드카드 한 줄은 정책 전체를 무력화하므로 쓰지 않는다(`scripts/test_profile_policy.py` 가 막는다). 그 다음 줄에서 `**/cookies*.json`, `**/*auth*.json`, `**/*token*.json`, `**/*secret*` 패턴을 **whitelist 다음에 배치** (last-match-wins로 자격증명 재차단).

- profile.json에 토큰/API key/JWT/세션 쿠키 박지 말 것 — commit되면 GitHub에 평문 노출됨
- 새 도메인 프로필 commit 전 `git diff --cached fingerprints/` 로 자격증명 누출 확인
- 검증: `git check-ignore -v <file>` 로 차단 패턴 확인 가능

## 쿠키 전달 흐름 (로그인 후)

```python
import json
from utils import plain_session

# 1. agent-browser로 수동 로그인 후 쿠키 추출 → output/<도메인>/cookies.json 저장
#    ★ 수동 로그인 전에 `agent-browser close --all` — 데몬이 떠 있으면 --headed 가 무시된다
with open("output/<도메인>/cookies.json") as f:
    cookies = json.load(f)   # {"name": "value", ...}

# 2. 사다리 2단 세션에 주입 (위장 인자 없음 — 로그인 쿠키는 위장이 아니다)
#    ★ 쿠키는 **요청별 인자**로 넘긴다. `session.cookies.update(...)` 는 동작하지 않는다 —
#      plain_session() 이 돌려주는 _SyncSessionLogic 에는 .cookies 속성이 없다.
with plain_session() as session:
    resp = session.get(url, cookies=cookies)
```

쿠키 파일은 `.gitignore`의 `**/cookies*.json` 패턴으로 자동 차단된다. 전용 프로필 창에서
받은 상태를 저장했다면 **대상 도메인분만 골라** 넣는다 — 다른 사이트 세션까지 프로젝트
폴더로 들어오지 않게.
