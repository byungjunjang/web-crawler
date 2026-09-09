# 트러블슈팅 가이드

autoresearch 실험(4회 반복, 6개 사이트)과 실제 크롤링에서 발견된 실패 패턴과 해결책.
수집 실패 시 이 문서를 참조하여 원인을 진단한다.

## 목차

1. [실패 유형 진단 플로우차트](#실패-유형-진단)
2. [Akamai 사이트 수집 실패](#akamai-사이트-수집-실패)
3. [SPA 세션 보호 사이트 수집 실패](#spa-세션-보호-사이트-수집-실패)
4. [False Positive (잘못된 데이터 수집)](#false-positive)
5. [API 키 필요 사이트](#api-키-필요-사이트)
6. [셀렉터 불일치](#셀렉터-불일치)
7. [검증된 사이트별 전략](#검증된-사이트별-전략)

---

## 실패 유형 진단

```
수집 결과가 0건?
├── HTTP 403/401 반환 → 인증 또는 안티봇 문제
│   ├── Akamai 시그널? → "Akamai 사이트 수집 실패" 참조
│   ├── 브라우저에서는 정상? → "SPA 세션 보호" 참조
│   └── API 키 필요? → "API 키 필요 사이트" 참조
│
├── HTTP 200이지만 데이터 없음 → JS 렌더링 또는 SPA 문제
│   ├── 페이지 내용이 빈 HTML? → DynamicFetcher로 전환 (3단, 자동)
│   ├── JS 챌린지 페이지? → **이음매 통지 게이트** → '진행' 이면 StealthyFetcher 또는 Chrome CDP
│   └── SPA 내비게이션 필요? → DynamicFetcher + page_action (3단, 자동)
│
├── 데이터는 있지만 잘못된 데이터 → "False Positive" 참조
│
└── 연결 실패 (timeout, refused) → 포트/URL 확인, 레거시 URL 제거
```

---

## Akamai 사이트 수집 실패

### 증상
- Fetcher/StealthyFetcher/DynamicFetcher 모두 실패
- HTTP 200이지만 JS 챌린지 페이지만 반환 (< 1KB, div 몇 개)
- `_abck`, `bm_sz` 쿠키가 설정됨

### 원인 (autoresearch baseline에서 발견)
`antibot_type: akamai` 로 기록된 도메인에서 수집이 0건으로 끝났다. FETCHER_CHAIN에 Chrome CDP가 포함되지 않아 DynamicFetcher까지만 시도하고 종료됨.

### 해결책
1. **FETCHER_CHAIN 사용 중지** — 사다리 A 전용 체인이라 이 상황을 풀 수 없다
2. **이음매 통지 게이트를 거친다** — Akamai 감지는 사다리 B 진입 신호다. 사용자가 '진행' 을 고른 뒤에 4·5단을 건너뛰고 Chrome CDP로 간다 (`consent` 기록이 이미 있으면 통지 없이 진행)
3. **headed Chrome 필수** — headless Chrome은 Akamai에 탐지됨
4. `antibot-strategies.md § Akamai` 패턴 적용

### autoresearch 검증 결과
- baseline: 0/50건 (FAIL — 체인이 사다리 A 에서 끝나 이 사이트를 풀 수 없었다)
- exp-1: Chrome CDP 적용 → 50/50건 (100%)
- exp-2~3: 안정적 100% 유지

---

## SPA 세션 보호 사이트 수집 실패

### 증상
- 브라우저에서는 검색/조회가 정상 작동
- API를 requests/Scrapling으로 직접 호출하면 403
- 에러 메시지: "접근 권한이 존재하지 않습니다" (ErrorCode -801 등)
- 세션 쿠키를 포함해도 403

### 원인 (g2b.go.kr 크롤링에서 발견)
WebSquare 프레임워크가 서버 측에서 SPA 네비게이션 상태를 추적. 메인 페이지 → 메뉴 클릭 → 검색 화면 순서로 이동해야만 API 호출 권한이 부여됨. HTTP 클라이언트로는 이 상태를 재현할 수 없음.

### 해결 과정
1. ❌ requests + 세션 쿠키 → 403
2. ❌ Playwright page.evaluate fetch() → 403 (SPA 상태 미포함)
3. ❌ Playwright expect_response (검색 버튼) → 타이밍 불일치로 실패
4. ✅ **Playwright `page.on("response")` 백그라운드 리스너** + UI 버튼 클릭 → 성공

### 해결책
`antibot-strategies.md § SPA 세션 보호` 패턴 적용:
- Playwright로 SPA 정상 로드 (메뉴 네비게이션 포함)
- `page.on("response")` 백그라운드 리스너 등록
- UI 조작(검색/적용 버튼 클릭)으로 API 트리거
- 인터셉트된 JSON 데이터 수집

### 핵심 교훈
- `page.on("response")`가 `expect_response`보다 안정적 (타이밍 무관)
- WebSquare 검색 버튼은 `page.evaluate()`로 클릭하는 것이 locator보다 안정적
- 페이지 사이즈 변경 시 select + change 이벤트 + 적용 버튼 순서로 조작

---

## False Positive (잘못된 데이터 수집)

### 증상
- 건수는 많지만 데이터가 달력 셀, UI 텍스트, 타임스탬프 등 쓰레기

### 원인 (autoresearch exp-2에서 발견)
g2b.go.kr에서 DOM 추출 시 달력 위젯의 날짜 셀(1~31)을 입찰공고로 오인. exp-2에서 49건의 false positive 발생.

### 해결책: 검증 함수 적용

```python
import re

def validate_record(record):
    """수집된 레코드가 실제 데이터인지 검증."""
    name = record.get("공고명", "")

    # 너무 짧은 텍스트 거부
    if len(name) < 10:
        return False

    # 순수 숫자 거부 (달력 셀)
    if re.match(r'^\d+$', name.strip()):
        return False

    # 타임스탬프 패턴 거부
    if re.match(r'^\d{4}[/\-]\d{2}[/\-]\d{2}\s+\d{2}:\d{2}', name.strip()):
        return False

    # UI 텍스트 거부
    ui_keywords = ['닫기', '확인', '취소', '이전', '다음', '검색', '선택']
    if name.strip() in ui_keywords:
        return False

    return True
```

---

## API 키 필요 사이트

### 증상
- 공공데이터포털(data.go.kr) API 호출 시 HTTP 500 또는 인증 에러
- 유효하지 않은 ServiceKey

### 해결책
1. 사용자에게 API 키 발급 안내 (data.go.kr 회원가입 → 활용신청)
2. 환경변수로 키 전달: `DATA_GO_KR_API_KEY`
3. API 키 없이는 수집 불가능함을 명확히 보고

---

## 셀렉터 불일치

### 증상
- CSS Module 해시 클래스 (예: `_1a2b3c`) 때문에 셀렉터 무효
- Next.js/React 사이트에서 클래스명이 빌드마다 변경

### 해결책 (autoresearch exp-1에서 발견)
- CSS 클래스 대신 **구조적 셀렉터** 사용: `div > ul > li`, `[data-testid]`, `[aria-label]`
- Scrapling의 **adaptive 모드** 활용: `page.css(selector, adaptive=True, auto_save=True)`
- 별점 등 시각적 데이터는 `aria-label` 속성에서 추출

---

## 검증된 사이트별 전략

autoresearch 4회 실험 + 실제 크롤링에서 검증된 최적 전략:

| 사이트 | 전략 | Fetcher | 성공률 | 비고 |
|--------|------|---------|--------|------|
| `antibot_type: akamai` 로 기록된 도메인 | 6단 Chrome CDP (**통지 이후**) | `launch_chrome_cdp()` (headed) | 100% | headless 불가 |
| **kurly.com** | CSR DynamicFetcher | DynamicFetcher | 100% | Next.js, page_action 필요 시 |
| **wanted.co.kr** | API 직접 | `plain_session()` | 100% | 0.6초에 30건, 가장 빠름 |
| **g2b.go.kr** | SPA 세션 인터셉트 | Playwright on("response") | 100% | WebSquare, 로그인 불필요 |
| **books.toscrape.com** | 정적 HTML | `plain_get()` | 100% | 테스트 사이트 |
| **quotes.toscrape.com** | JS 렌더링 | DynamicFetcher | 100% | 테스트 사이트 |
