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

- 전체 가이드(비개발자용 포함)는 `README.md`의 "처음 설치하기" 참조.
- 수동/디버깅 명령과 막혔을 때의 대처는 `AGENTS.md` 「최초 환경 셋업」과 `README.md` 「에이전트용 셋업 안내」를 읽는다.

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

프로필 조회·저장 코드와 저장 값 규칙, 목록 재생성 명령은 `.claude/skills/web-crawler/SKILL.md` Step 1-A·Step 5-A 를 읽는다.

---

## 범위 / 운영 안전 규칙

**포함**: 사이트 정찰, 구조 파악, 로그인 대응, 동적 콘텐츠, pagination, 대량 데이터 수집, 엑셀 출력.

**안전 규칙 (에이전트가 항상 지킴)**:
- **자동 접근 차단을 만나면 통지 후 사용자 선택** — CAPTCHA·WAF·봇 탐지는 법적으로 같은 보호조치다. 어느 쪽이든 **자동으로 넘어가지 않고 한 번 알리고 사용자가 고른다**. '진행' 이면 그대로 간다 — 근거를 묻지도 검증하지도 않는다. 상세는 SKILL.md Step 3 "이음매 통지 게이트"
- **CAPTCHA 는 도구로 넘기거나 사용자가 직접 푼다** — 통지와 별개다. '진행' 뒤에는 CAPTCHA 때문에 수집을 멈추지 않는다. Cloudflare 관리형 챌린지·Turnstile 은 `StealthyFetcher(solve_cloudflare=True)`(5단)로 통과시킨다. 도구가 못 넘는 CAPTCHA(reCAPTCHA·hCaptcha 등)는 전용 프로필의 보이는 Chrome 창(`launch_chrome_cdp`)을 띄워 사용자가 직접 풀고, 그 브라우저 세션에 붙어 이어간다. 외부 CAPTCHA 풀이 서비스(유료 풀이 API·풀이 대행)는 쓰지 않는다. 상세는 SKILL.md Step 3 「CAPTCHA — 도구가 넘기거나, 사용자가 푼다」
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

> **에스컬레이션 순서 = 가벼운 것부터.** 자동 체인은 `plain_get → plain_session → plain_dynamic` 으로 **사다리 A 에서 끝난다.** 그 위(`curl_cffi 그리드` · `StealthyFetcher` · `Chrome CDP`)는 능력으로 전부 남아 있되 **통지 이후에** 진입한다. Akamai 는 4·5 단이 원리적으로 안 통해 통지 후 바로 6단이다. 상세 코드는 `.claude/skills/web-crawler/references/fetcher-patterns.md § F`, capability 판정 근거는 `.claude/skills/web-crawler/references/antibot-strategies.md § WAF capability 라우팅`.

## Spider 활용 기준

| 조건 | 방식 |
|------|------|
| ~500건 미만, 단일 리스트 | `plain_session()` 순차 처리 |
| 500건 이상, 단일 리스트 | `Spider` + 단일 세션 (`concurrent_requests=5`) |
| 여러 카테고리 동시 수집 | `Spider` + multi-session routing |
| 장시간 수집 (1000건+) | `Spider` + `crawldir='./crawl_data'` (Ctrl+C 시 자동 체크포인트, 재실행 시 이어서) |

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

## 작업별로 먼저 읽을 문서

작업을 시작하기 전에 해당 행의 문서를 먼저 읽는다. 스킬 경로는 `.claude/skills/web-crawler/` 이다.

| 작업 | 먼저 읽을 문서 |
|------|----------------|
| 크롤링 요청 처리 (7단계, Step 1-A ↔ 5-A 프로필 게이트) | `SKILL.md` |
| 도메인 프로필 조회·저장, 저장 값 규칙, 도메인 목록 재생성 | `SKILL.md` Step 1-A · Step 5-A |
| 도구 역할 분리, Fetcher 선택 보충, 에스컬레이션, 에러별 대응표, Rate Limiting | `references/crawl-operations.md` |
| 수집 코드 생성 원칙 | `SKILL.md` Step 4 |
| Fetcher별 코드 템플릿 (Infinite Scroll 우선순위 포함) | `references/fetcher-patterns.md` |
| 안티봇 대응 (Akamai 탐지 시그널, Chrome CDP 실행, Cloudflare, SPA 세션) | `references/antibot-strategies.md` |
| 로그인 후 쿠키 전달 | `SKILL.md` Step 2-A |
| 검증 통과 기준 | `SKILL.md` Step 5 |
| 수집 실패 진단 | `references/troubleshooting.md` |
| 출력·저장 디렉터리 구조, `.gitignore` whitelist 정책 | `references/output-layout.md` |
| Scrapling API 사용법 | `scripts/scrapling_reference.md` |
