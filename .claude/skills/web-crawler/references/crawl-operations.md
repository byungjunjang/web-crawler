# 수집 운영 레퍼런스

도구 역할 분리, Fetcher 선택 보충, 에스컬레이션, 에러별 대응, 요청 간격을 정한다.
Fetcher 선택 의사결정 트리 자체는 `CLAUDE.md` 에 있다.

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

## Fetcher 선택 보충

`CLAUDE.md` 「Fetcher 선택 의사결정 트리」의 보충 설명이다.

> **세 단 모두 래퍼를 쓴다.** 맨 `Fetcher.get()`/`FetcherSession()` 은 기본이 `impersonate="chrome"` + `stealthy_headers=True` 라 평문이 아니고, 맨 `DynamicFetcher.fetch()` 는 `google_search=True` 라 **`Referer: https://www.google.com/` 를 지어내 붙인다.** 사다리 A 는 통지 없이 도는 칸이므로 셋 다 끈 상태가 기본이다 — `plain_get()` · `plain_session()` · `plain_dynamic()`. (`fetcher_type` 에 기록하는 **어휘**는 그대로 `Fetcher`/`FetcherSession`/`DynamicFetcher` 다 — 래퍼 이름이 아니라 구현체 이름을 적는다.)

> profile.json이 있는 도메인은 Akamai 탐지 시그널을 따로 안 봐도 `antibot_type` 필드로 즉시 판정된다 (`antibot_type: akamai` → `chrome_cdp` 직행). 단 그 직행도 이음매 뒤에 있다 — 이미 `consent` 기록이 있으면 통지 없음, 기록이 없으면 이번이 최초 통과이므로 그대로 통지한다.

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
| Cloudflare Challenge·Turnstile | 통지 게이트를 거친 뒤 `StealthyFetcher(solve_cloudflare=True)` (5단) |
| 도구가 못 넘는 CAPTCHA | 중단하지 않는다 — 보이는 Chrome 창(`launch_chrome_cdp`)에서 사용자가 풀고 그 세션으로 이어간다 (SKILL.md Step 3) |
| 셀렉터 매칭 실패 | `adaptive=True`로 자가 치유 시도. 재실패 시 정찰 재실행 |
| 페이지 구조 완전 변경 | 정찰 재실행 → profile.json의 selectors 갱신 |
| JS 렌더링 실패 | DynamicFetcher로 에스컬레이션. `disable_resources=True`로 경량화 |
| 네트워크 타임아웃 | 3회 재시도 후 해당 페이지 스킵 + 로그 |
| **수집 데이터 0건** | **즉시 중단, 사용자 보고** (계속 시도하면 ban 위험) |
| Spider 중단 (Ctrl+C) | `crawldir`에서 자동 체크포인트, 재실행 시 이어서 수집 |

## Rate Limiting

| 규모 | HTTP 요청 간격 | 브라우저 내 fetch 간격 | Spider concurrent_requests |
|------|---------------|----------------------|---------------------------|
| ~100건 | 1초 | 200ms | 해당 없음 |
| 100~500건 | 1.5초 | 300ms | 해당 없음 |
| 500~2000건 | 1.5초 | 500ms | 5 |
| 2000건+ | 2초 + 100건마다 15초 휴식 | 1초 + 50건마다 3초 휴식 | 3 |

브라우저 내 fetch는 동일 세션이므로 서버 부하가 상대적으로 낮음. 단, 봇 탐지 행동 분석에 걸리지 않도록 최소 200ms 간격 유지.
