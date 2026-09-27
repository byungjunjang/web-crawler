"""scripts/domain_profile.py — 도메인별 크롤링 프로필 저장/재사용

프로필 스키마:
{
    "domain": "example.com",
    "capability": "static|js_render|api|session",     # ★ SSOT — 능력 수준
    "distribution": "public|local",                    # 선택 — 없으면 policy 가 자동 판정
    "distribution_reason": "선언 사유",     # distribution 이 있을 때만 의미 있음
    "consent": {"notified_at": "ISO8601", "choice": "proceed"},   # 사다리 B 프로필 필수, sticky
    "fetcher_type": "yt-dlp|RSS|oEmbed|Jina|Fetcher|FetcherSession|DynamicFetcher|DynamicSession|Spider|playwright_spa_intercept|curl_cffi_grid|StealthyFetcher|chrome_cdp|API_SESSION",  # 파생 — 현재 엔진에서의 구현체. 앞 4개는 Phase 0 공인 우회로
    "antibot_type": "none|cloudflare|akamai|spa_session|naver_antibot|other",   # 봇 차단 유형
    "antibot_strategy": "none|playwright_intercept|impersonate|curl_cffi_grid|stealthy|chrome_cdp|naver_antibot|authenticated_browser",    # 대응 전략
    "site_type": "static|csr|api|spa_session|akamai|api_direct|csr_api|html_endpoint|static_html",   # 기술 서술용 상세 라벨. 거친 능력 신호는 capability 가 SSOT 다
    "selectors": {"필드": "셀렉터"},
    "pagination": {"type": "url_param|url_path|query_param|offset|category_param|toc_tree|none_latest_n|next_button|infinite_scroll"},
    "api_endpoints": [{"url": "", "method": "GET", "params": {}, "field_mapping": {}}],
    "notes": "사이트 특이사항 메모 (str, 또는 여러 줄 쌓인 list[str])",  # 목록이 누적되면 배열로 적어도 된다 — 게이트 규칙 6
    "last_used": "2026-03-09",
}
"""
import json
import os
import shutil
from datetime import datetime, timezone

from profile_policy import distribution, infer_capability, is_unrecognized_tool, ladder_rung
from utils import sanitize_filename, setup_logger


# 알려진 안티봇 유형별 추천 전략
ANTIBOT_STRATEGIES = {
    "akamai": "chrome_cdp",
    "cloudflare": "stealthy",
    "none": "none",
}

# 호출자가 새 dict 를 만들어 넘겨도 살아남아야 하는 필드.
# 공통 성격: 전부 "이 프로필을 배포해도 되는가" 를 결정하는 데 관여한다 — 호출자가 생략
# 만으로 그 답을 바꿔서는 안 된다(보존이지 고정은 아니다: 명시적으로 다시 넘기면 그 값이
# 이긴다. 아래 각 필드 참조).
# - distribution/distribution_reason: 배포 여부 선언. 없으면 다음 수집 한 번으로 미배포
#   결정이 조용히 지워진다.
# - capability: 능력 SSOT. fetcher_type 역추론 폴백이 지금은 손실을 감추지만, 그 폴백이
#   깨지는 순간(라이브러리가 클래스 이름을 또 바꾸는 순간) 드러난다 — 폴백이 필요 없어질
#   때가 아니라 필요해질 때 사라지면 안 된다.
# - consent: 이미 내린 통지·선택 기록. 그 프로필에 consent 가 이미 있다는 사실이 그 사용자가
#   한 번 통지받고 진행을 골랐다는 뜻이다 — 매 수집마다 다시 묻지 않는다. (프로필은 있어도
#   consent 가 없는 도메인 — 상속할 기록이 없는 최초 이음매 통과 포함 — 에는 게이트가 그대로
#   발화한다.)
# - antibot_strategy: distribution() 이 rung 을 매길 때 보는 판정 필드 중 하나다(다른 하나인
#   fetcher_type 은 sticky 가 아니다 — 구현체가 바뀌는 건 자연스러우므로). 예: fetcher_type 이
#   FetcherSession 이어도 antibot_strategy 가 "impersonate" 면 local 이다.
#   이 필드가 생략만으로 사라지면 미배포 결정이 조용히 public 으로 뒤집히고,
#   consent 도 (public 프로필에서는 지워야 하므로) 함께 씻겨나간다.
STICKY_FIELDS = ("distribution", "distribution_reason", "capability", "consent",
                  "antibot_strategy")


def _is_real_timestamp(value) -> bool:
    """`consent.notified_at` 이 진짜 시각인지 — placeholder 나 빈 값이 아닌지 판별.

    Step 5-A 템플릿을 그대로 복사해 `<ISO8601>` 같은 자리표시자를 지우지 않고 남기면,
    통지를 실제로 한 적이 없어도 choice 만 "proceed" 면 게이트를 통과했다. 그 값이
    거짓이면 consent 기록의 유일한 쓸모(실제로 통지했다는 증거)가 사라지므로, 여기서
    막는다. 형식 검증이 아니라 "명백한 자리표시자를 배제" 하는 최소한의 체크다 —
    실제 타임스탬프 문법을 강제하지는 않는다.

    꺾쇠만 지우고 안의 문구는 그대로 둔 반쯤 지운 자리표시자("통지한 실제 시각 ISO8601")도
    막는다 — "ISO8601" 이라는 문자열 자체가 실제 값에는 등장할 이유가 없는, 템플릿의 흔적이다.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith("<") and stripped.endswith(">"):
        return False
    if "ISO8601" in stripped:
        return False
    return True


class ConsentRequired(Exception):
    """사다리 B(우회) 프로필을 consent 기록 없이 저장하려 할 때.

    통지 게이트의 백스톱이다. 사용자에게 한 번 알리지 않고 조용히 우회한 경우,
    이 예외 때문에 Step 5-A 프로필 저장을 완료할 수 없다.

    consent 는 '근거' 가 아니라 '선택' 을 기록한다 — 무엇을 정당화했는지가 아니라
    통지를 봤고 진행을 골랐다는 사실과 그 시각만 남긴다.

    consent 는 sticky 필드다 — 한 번 기록되면 그 도메인의 다음 저장들이 (STICKY_FIELDS
    병합을 통해) 다시 요구하지 않는다. 트리거는 "프로필이 있다" 가 아니라 "그 프로필에
    consent 기록이 있다" 는 사실이다 — 사다리 A로만 수집돼 오던 도메인이 이번에 처음
    이음매를 넘는 경우처럼, 프로필은 있어도 상속할 consent 가 없으면 게이트는 그대로
    발화한다. 게이트 자체는 배포 판정이 아니라 ladder_rung(profile) >= 4, 즉 실제로
    이음매를 넘었는지로만 발화한다(distribution()=="local" 과는 다르다 — 후자는 robots/ToS
    declare-local, 판별 불가, withheld 도구까지 포함하는 더 넓은 집합이다).
    """


class DomainProfile:
    """도메인별 사이트 프로필을 관리."""

    def __init__(self, base_dir: str = "./fingerprints", clock=None):
        self.base_dir = base_dir
        # 손상 파일 백업 접미사에 쓰는 시각 소스. 기본은 실제 UTC now, 테스트는 주입해서 고정.
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def save(self, domain: str, profile: dict):
        profile = dict(profile)   # 호출자의 dict 를 건드리지 않는다
        domain_dir = os.path.join(self.base_dir, sanitize_filename(domain))
        filepath = os.path.join(domain_dir, "profile.json")

        existing = {}
        read_failed = False
        try:
            existing = self.load(domain) or {}
        except (ValueError, OSError):
            # 기존 파일이 깨졌어도 저장은 진행한다 — 수집 성공 후 게이트에서 죽으면 안 된다.
            # 다만 이 저장이 게이트에 막혀 거부되면, 손상된 원본이라도 손대지 않는다 —
            # 거부된 저장이 기존 파일을 지워버리면 "저장 실패" 가 "프로필 소실" 이 되어버린다.
            # 그래서 백업은 지금 하지 않고, 실제로 쓰기로 확정된 뒤로 미룬다.
            read_failed = True

        for field in STICKY_FIELDS:
            if field not in profile and field in existing:
                profile[field] = existing[field]

        # capability 는 SSOT 인데, 저장 템플릿을 그대로 따르는 호출자도 이 필드를 빠뜨릴 수 있다.
        # 그러면 읽는 쪽은 fetcher_type 역추론 폴백에만 기대게 되는데, 그 폴백은 있어도 기대면
        # 안 되는 것이다(위 STICKY_FIELDS 주석 참조 — 라이브러리가 클래스 이름을 바꾸는 순간
        # 깨진다). 저장 시점에 한 번 확정해 두면 새 도메인도 마이그레이션된 프로필과 같은 모양이
        # 된다. 호출자가 명시한 값은 건드리지 않고, 추론이 실패하면(모르는 fetcher_type) 지어내지
        # 않고 그대로 비워 둔다 — 없는 것과 틀린 것 중에서는 없는 쪽이 낫다.
        if not profile.get("capability"):
            inferred = infer_capability(profile)
            if inferred:
                profile["capability"] = inferred

        # 게이트는 배포 판정(distribution)이 아니라 이음매를 실제로 넘었는지(ladder_rung >= 4)
        # 로만 발화한다. distribution()=="local" 은 더 넓은 집합이다 — robots/ToS 사유의 명시적
        # `distribution: "local"` 선언(rung 1이어도 해당), 판별 불가(rung 0), withheld 도구
        # (예: authenticated_browser)도 전부 "local" 로 묶인다. 그 셋은 이음매를 넘은 사건이
        # 아니므로 consent 를 요구하면 안 된다 — consent 는 "4단 이상 도구로 실제로 돌파했다"
        # 는 사실 하나만 기록한다.
        # 단, ladder_rung 은 '없는 값'(정보 없음)과 '있는데 모르는 값'(오타·신종·서술형)을
        # 둘 다 0 으로 뭉갠다 — 후자는 이음매를 건넜는지 판단 불가라는 뜻이지 안전하다는 뜻이
        # 아니다. is_unrecognized_tool 이 그 경우를 따로 잡아 게이트를 발화시킨다.
        #
        # 두 조건은 서로 배타적이다 — ladder_rung() 은 모르는 값을 하나라도 만나면 즉시 0을
        # 반환하므로(다른 필드에서 이미 찾은 rung 도 버린다), rung>=4 가 성립했다는 것 자체가
        # 모든 필드가 인식된 값이었다는 뜻이다. 그래서 아래에서 rung 하나만으로 두 트리거를
        # 구분해 서로 다른 안내를 줄 수 있다 — 전자는 "진짜 4단 이상", 후자는 "판별 불가".
        rung = ladder_rung(profile)
        if rung >= 4 or is_unrecognized_tool(profile):
            consent = profile.get("consent")
            notified_at = consent.get("notified_at") if isinstance(consent, dict) else None
            consent_ok = (
                isinstance(consent, dict)
                and consent.get("choice") == "proceed"
                and _is_real_timestamp(notified_at)
            )
            if not consent_ok:
                if rung >= 4:
                    raise ConsentRequired(
                        f"{domain}: 이 프로필은 자동 접근 차단을 넘어선 방법(사다리 B, 4단 이상)을 "
                        "기록하고 있습니다. 사용자에게 실제로 한 번 통지하고, 그 선택과 통지한 실제 "
                        "시각을 consent 블록에 남긴 뒤 저장하세요 — "
                        '예: {"notified_at": "2026-08-20T14:30:00+09:00", "choice": "proceed"}. '
                        "<ISO8601> 같은 자리표시자나 빈 값은 유효하지 않습니다. "
                        "권한 근거를 적을 필요는 없습니다."
                    )
                raise ConsentRequired(
                    f"{domain}: fetcher_type/antibot_strategy 에 적힌 값이 어느 사다리 칸에도 "
                    "해당하지 않아 분류기가 이음매를 넘었는지 판별할 수 없습니다(오타 또는 "
                    "문서에 없는 신종 값일 수 있습니다). 문서화된 값 목록은 Step 5-A 저장 템플릿의 "
                    "fetcher_type/antibot_strategy enum(SKILL.md)을 참조하세요. "
                    "통지가 실제로 없었다면 consent 를 적지 말고 값을 고쳐라 — 이 오류는 심사가 "
                    "아니라 분류기가 알아들을 수 있는 값을 요구하는 것입니다."
                )

        if distribution(profile) != "local":
            # public 으로 (재)분류된 프로필에 이전 통지 이력이 남아있으면 안 된다 — consent 는
            # 배포되지 않는 로컬 결정의 기록이지, 배포 whitelist 에 들어갈 값이 아니다.
            # fetcher_type 은 sticky 가 아니므로, 도구가 사다리 A로 내려온 재수집은 이 분기를
            # 그대로 통과해 consent 를 씻어낸다.
            profile.pop("consent", None)

        # 여기까지 왔다면 이 저장은 실제로 진행된다 — 그제야 손상된 기존 파일을 백업한다.
        if read_failed and os.path.exists(filepath):
            backup_path = (
                f"{filepath}.corrupt-{self._clock().strftime('%Y%m%dT%H%M%S.%fZ')}"
            )
            shutil.move(filepath, backup_path)
            setup_logger(__name__).warning(
                "%s: 기존 profile.json을 읽지 못해 백업 후 새로 씁니다 "
                "(distribution 선언이 있었다면 유실 — 백업 파일에서 복구) → %s",
                domain, backup_path,
            )

        os.makedirs(domain_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

    def load(self, domain: str) -> dict | None:
        filepath = os.path.join(self.base_dir, sanitize_filename(domain), "profile.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def exists(self, domain: str) -> bool:
        filepath = os.path.join(self.base_dir, sanitize_filename(domain), "profile.json")
        return os.path.exists(filepath)

    def get_antibot_strategy(self, domain: str) -> str:
        """도메인의 안티봇 대응 전략 반환. 프로필 없으면 'none'."""
        profile = self.load(domain)
        if not profile:
            return "none"
        return profile.get("antibot_strategy", "none")

    def is_akamai(self, domain: str) -> bool:
        """해당 도메인이 Akamai 보호 사이트인지 확인."""
        profile = self.load(domain)
        if not profile:
            return False
        return profile.get("antibot_type") == "akamai"

    def capability(self, domain: str) -> str | None:
        """도메인의 능력 수준(static|js_render|api|session). 프로필 없으면 None.

        capability 필드가 SSOT 이고 fetcher_type 은 파생이다. 필드가 없는 옛 프로필은
        fetcher_type 에서 역추론하므로 마이그레이션 없이도 읽힌다.
        """
        from profile_policy import infer_capability
        profile = self.load(domain)
        return infer_capability(profile) if profile else None
