"""scripts/sync_domain_list.py — 문서의 "알려진 도메인" 목록을 profile.json에서 재생성

`fingerprints/<sanitized_domain>/profile.json`이 단일 진실의 원천(SSOT). 프로필이
추가/삭제될 때마다 CLAUDE.md와 README.md의 도메인 목록을 손으로 고치면 반드시
어긋난다(실제로 11개/12개로 적혀 있는 동안 프로필은 19개였다).

각 문서의 마커 블록 사이만 재생성한다. 마커는 HTML 주석이라 GitHub 렌더링에
보이지 않는다:

    <!-- BEGIN GENERATED: domain-list -->
    ...생성 영역...
    <!-- END GENERATED: domain-list -->

사용법:
    python scripts/sync_domain_list.py          # 목록 재생성
    python scripts/sync_domain_list.py --check  # 어긋나면 exit 1 (쓰지 않음)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from profile_policy import is_distributable, public_dirs

# Codex/Work가 캡처하는 Windows 콘솔에서도 한글과 em dash를 UTF-8로 안전하게 출력한다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# scripts/sync_domain_list.py: parents[0]=scripts [1]=repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
FINGERPRINTS = REPO_ROOT / "fingerprints"

BEGIN = "<!-- BEGIN GENERATED: domain-list -->"
END = "<!-- END GENERATED: domain-list -->"
REGEN_HINT = "<!-- 이 블록은 scripts/sync_domain_list.py 가 생성한다. 직접 수정하지 말 것. -->"

GITIGNORE_BEGIN = "# BEGIN GENERATED: public-profiles"
GITIGNORE_END = "# END GENERATED: public-profiles"


def collect_domains():
    """fingerprints/*/profile.json 의 domain 값을 정렬해 반환.

    domain 필드가 없으면 디렉터리명을 폴백으로 쓴다(sanitize된 형태라 부정확할 수
    있으나, 목록에서 조용히 누락되는 것보다 낫다).
    """
    domains = []
    if not FINGERPRINTS.is_dir():
        return domains
    for profile in sorted(FINGERPRINTS.glob("*/profile.json")):
        try:
            data = json.loads(profile.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[WARN] 읽기 실패, 건너뜀: {profile} ({exc})", file=sys.stderr)
            continue
        if not is_distributable(data):
            continue        # 미배포 프로필은 문서 목록에도 나오지 않는다
        domain = (data.get("domain") or "").strip() or profile.parent.name
        domains.append(domain)
    return sorted(set(domains))


def render_claude(domains):
    listed = ", ".join(f"`{d}`" for d in domains)
    return (
        f"### 알려진 도메인 ({len(domains)}개 profile commit됨)\n"
        "\n"
        f"{listed} — 이 도메인들은 정찰 없이 바로 수집 시도 가능."
    )


def render_readme(domains):
    listed = ", ".join(f"`{d}`" for d in domains)
    return f"현재 {len(domains)}개 도메인 프로필이 포함되어 있습니다: {listed}."


TARGETS = (
    (REPO_ROOT / "CLAUDE.md", render_claude),
    (REPO_ROOT / "README.md", render_readme),
)


def render_gitignore_whitelist():
    """배포 대상 프로필만 whitelist 하는 블록 본문."""
    lines = []
    for name in public_dirs():
        lines.append(f"!fingerprints/{name}/profile.json")
        if (FINGERPRINTS / name / "recipe.md").exists():
            lines.append(f"!fingerprints/{name}/recipe.md")
    return "\n".join(lines)


def sync_gitignore(check_only):
    """.gitignore 의 whitelist 블록을 재생성. 변경됐으면 True."""
    path = REPO_ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    start = text.find(GITIGNORE_BEGIN)
    end = text.find(GITIGNORE_END)
    if start == -1 or end == -1:
        raise RuntimeError(f".gitignore 에 마커가 없습니다 ({GITIGNORE_BEGIN})")
    head = text[: start + len(GITIGNORE_BEGIN)]
    tail = text[end:]
    updated = f"{head}\n{render_gitignore_whitelist()}\n{tail}"
    if updated == text:
        return False
    if not check_only:
        path.write_text(updated, encoding="utf-8")
    return True


def replace_block(text, body, path):
    """마커 사이를 body로 교체한 전체 텍스트를 반환. 마커가 없으면 RuntimeError."""
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 or end == -1:
        raise RuntimeError(f"{path.name}에 마커가 없습니다 ({BEGIN} / {END})")
    if end < start:
        raise RuntimeError(f"{path.name}의 마커 순서가 뒤집혔습니다")
    head = text[: start + len(BEGIN)]
    tail = text[end:]
    return f"{head}\n{REGEN_HINT}\n\n{body}\n\n{tail}"


def build(check_only):
    domains = collect_domains()
    if not domains:
        print("[FAIL] fingerprints/*/profile.json 을 하나도 찾지 못했습니다.", file=sys.stderr)
        return 2

    stale = []
    for path, render in TARGETS:
        current = path.read_text(encoding="utf-8")
        updated = replace_block(current, render(domains), path)
        if updated == current:
            continue
        stale.append(path.name)
        if not check_only:
            path.write_text(updated, encoding="utf-8")

    if sync_gitignore(check_only):
        stale.append(".gitignore")

    if check_only:
        if stale:
            print(
                f"[FAIL] 생성 블록이 어긋났습니다 ({', '.join(stale)}). "
                "`python scripts/sync_domain_list.py` 를 실행하세요.",
                file=sys.stderr,
            )
            return 1
        print(f"[OK] 도메인 목록 최신 — {len(domains)}개")
        return 0

    if stale:
        print(f"[sync_domain_list] 갱신: {', '.join(stale)} — {len(domains)}개 도메인")
    else:
        print(f"[sync_domain_list] 변경 없음 — {len(domains)}개 도메인")
    return 0


def main():
    ap = argparse.ArgumentParser(description="문서의 도메인 목록을 profile.json에서 재생성")
    ap.add_argument("--check", action="store_true",
                    help="어긋나면 exit 1 (쓰지 않음)")
    args = ap.parse_args()
    return build(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
