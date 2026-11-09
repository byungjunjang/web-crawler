# 출력·저장 디렉터리 레퍼런스

수집 결과물, 쿠키, 도메인 프로필을 어디에 두는지와 `.gitignore` 정책을 정한다.

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
