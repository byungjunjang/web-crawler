"""scripts/preflight.py — 설치/환경 검증 (단계별 PASS/WARN/FAIL)

core(Python·Scrapling·Playwright)와 agent-browser(표준 정찰 도구)를 분리해 검증한다.
**설치는 하지 않는다 — 확인만.** 설치는 scripts/bootstrap.py 또는 scripts/setup.ps1.

사용법:
    python scripts/preflight.py            # core + agent-browser
    python scripts/preflight.py --core-only
    python scripts/preflight.py --no-network

종료 코드: 0=전체 통과 / 1=core 통과·agent-browser 미완료(=전체 설치 미완료) / 2=core 실패
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows 콘솔(cp949 등)에서 인코딩 불가 문자로 죽지 않도록.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

IS_WIN = os.name == "nt"
REPO = Path(__file__).resolve().parents[1]

_results: list[tuple[str, str, str]] = []  # (group, status, name)


def record(group, status, name, detail="", fix=""):
    _results.append((group, status, name))
    tag = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
    line = f"  {tag} {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    if status != "PASS" and fix:
        print(f"         다음 명령: {fix}")


def _cmd(name):
    """Windows에선 .cmd 우선 (PowerShell .ps1 실행정책 회피)."""
    if IS_WIN:
        return shutil.which(name + ".cmd") or shutil.which(name)
    return shutil.which(name)


def _scrapling_install_cmd():
    return ".\\.venv\\Scripts\\scrapling.exe install" if IS_WIN else "scrapling install"


# ---------------- CORE ----------------
def check_python():
    v = sys.version_info
    ok = v >= (3, 10)
    record("CORE", "PASS" if ok else "FAIL", "Python 버전", f"{v.major}.{v.minor}.{v.micro}",
           "" if ok else "Python 3.10+ 설치: https://www.python.org/downloads/")
    return ok


def check_imports():
    mods = {
        "scrapling.fetchers": "pip install -r requirements.txt",
        "scrapling.parser": "pip install -r requirements.txt",
        "scrapling.spiders": "pip install -r requirements.txt",
        "openpyxl": "pip install -r requirements.txt",
        "playwright": 'pip install "scrapling[fetchers]"',
        "curl_cffi": 'pip install "scrapling[fetchers]"',
        "browserforge": 'pip install "scrapling[fetchers]"',
        "patchright": 'pip install "scrapling[fetchers]"',
        "msgspec": 'pip install "scrapling[fetchers]"',
    }
    ok = True
    for mod, fix in mods.items():
        try:
            __import__(mod)
            record("CORE", "PASS", f"import {mod}")
        except Exception as e:
            ok = False
            record("CORE", "FAIL", f"import {mod}", str(e).splitlines()[0][:80], fix)
    return ok


def check_fetchers():
    try:
        from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher  # noqa: F401
        record("CORE", "PASS", "Fetcher 클래스 로드", "Fetcher/StealthyFetcher/DynamicFetcher")
        return True
    except Exception as e:
        record("CORE", "FAIL", "Fetcher 클래스 로드", str(e).splitlines()[0][:80],
               'pip install "scrapling[fetchers]"')
        return False


def check_chromium_launch():
    """Playwright Chromium 실행 가능 여부 (네트워크 불필요, 브라우저 바이너리 필요)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        record("CORE", "FAIL", "Playwright Chromium 실행", "playwright 미설치",
               'pip install "scrapling[fetchers]"')
        return False
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        record("CORE", "PASS", "Playwright Chromium 실행", "headless 기동 OK")
        return True
    except Exception as e:
        record("CORE", "FAIL", "Playwright Chromium 실행", str(e).splitlines()[0][:100],
               _scrapling_install_cmd())
        return False


# libcurl 이 CA 파일을 못 열었을 때의 서명. 네트워크 문제가 아니라 설치 문제다.
_CA_ERROR_MARKERS = ("error adding trust anchors", "CAfile")


def check_http_fetch():
    """가벼운 HTTP fetch (네트워크 필요).

    실패는 원칙적으로 WARN 이다 — 오프라인/방화벽일 수 있다. 다만 CA 번들을 못 읽은
    경우는 예외로 FAIL 이다. 그건 네트워크 제약이 아니라 이 환경에서 HTTPS 수집이
    전부 불가능하다는 뜻인데, WARN 으로 두면 '전체 통과' 로 보고돼 그냥 지나가게 된다.
    """
    try:
        # 수집 때와 같은 조건으로 확인한다 — crawl_script.py 도 utils 를 import 하면서
        # 같은 처리를 거친다. 여기서만 통과하고 수집에서 죽는 상황을 만들지 않는다.
        import utils
        utils.ensure_ascii_ca_bundle()

        from scrapling.fetchers import Fetcher
        page = Fetcher().get("https://httpbin.org/html")
        status = getattr(page, "status", None)
        if status == 200:
            record("CORE", "PASS", "HTTP fetch (httpbin)", "status 200")
            return True
        record("CORE", "WARN", "HTTP fetch (httpbin)", f"status={status}")
        return True
    except Exception as e:
        msg = str(e).splitlines()[0]
        if any(marker in str(e) for marker in _CA_ERROR_MARKERS):
            record("CORE", "FAIL", "HTTP fetch (httpbin)",
                   f"CA 번들을 읽지 못했습니다: {msg[:60]}",
                   "경로에 한글이 있으면 발생합니다. utils.ensure_ascii_ca_bundle() 이 "
                   "처리하는지 확인하거나 CURL_CA_BUNDLE 을 ASCII 경로로 지정하세요")
            return False
        record("CORE", "WARN", "HTTP fetch (httpbin)",
               f"네트워크 제한 가능: {msg[:60]}",
               "오프라인/방화벽이면 정상. 연결 확인 후 재시도")
        return True


# ------------- AGENT-BROWSER -------------
def _run(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def check_npm():
    p = _cmd("npm")
    if p:
        record("AGENT-BROWSER", "PASS", "npm", p)
        return True
    record("AGENT-BROWSER", "FAIL", "npm", "PATH에 없음",
           "Node.js 설치: https://nodejs.org/ (PowerShell은 npm.cmd 사용)")
    return False


def check_agent_browser():
    p = _cmd("agent-browser")
    install_fix = "npm.cmd install -g agent-browser" if IS_WIN else "npm install -g agent-browser"
    if not p:
        record("AGENT-BROWSER", "FAIL", "agent-browser CLI", "미설치", install_fix)
        return False
    try:
        r = _run([p, "--version"])
        ver = ((r.stdout or r.stderr).strip().splitlines() or ["?"])[0][:40]
        if r.returncode == 0:
            record("AGENT-BROWSER", "PASS", "agent-browser --version", ver)
            return True
        record("AGENT-BROWSER", "FAIL", "agent-browser --version", f"exit {r.returncode}", install_fix)
        return False
    except Exception as e:
        record("AGENT-BROWSER", "FAIL", "agent-browser --version", str(e).splitlines()[0][:60], install_fix)
        return False


def check_agent_browser_ready():
    """CLI 동작 + Chrome 준비. skills 명령으로 CLI 정상 여부 확인."""
    p = _cmd("agent-browser")
    if not p:
        return
    ab_install = "agent-browser.cmd install" if IS_WIN else "agent-browser install"
    try:
        r = _run([p, "skills", "list"], timeout=30)
        if r.returncode == 0:
            record("AGENT-BROWSER", "PASS", "agent-browser 동작", "skills list OK (Chrome는 정찰 시 최종 검증)")
        else:
            record("AGENT-BROWSER", "WARN", "agent-browser 동작", f"exit {r.returncode}", ab_install)
    except Exception as e:
        record("AGENT-BROWSER", "WARN", "agent-browser 동작", str(e).splitlines()[0][:60], ab_install)


def main():
    ap = argparse.ArgumentParser(description="설치/환경 검증 (PASS/WARN/FAIL)")
    ap.add_argument("--core-only", action="store_true", help="agent-browser 검증 제외")
    ap.add_argument("--no-network", action="store_true", help="네트워크 fetch 검증 생략")
    args = ap.parse_args()

    print("=== [CORE] Python · Scrapling · Playwright ===")
    core_ok = True
    core_ok &= check_python()
    core_ok &= check_imports()
    core_ok &= check_fetchers()
    core_ok &= check_chromium_launch()
    if not args.no_network:
        core_ok &= check_http_fetch()

    ab_ok = True
    if not args.core_only:
        print("\n=== [AGENT-BROWSER] 표준 정찰 도구 (이 프로젝트의 기본) ===")
        ab_ok &= check_npm()
        found = check_agent_browser()
        ab_ok &= found
        if found:
            check_agent_browser_ready()

    print("\n=== 요약 ===")
    def n(g, s):
        return sum(1 for (gg, ss, _) in _results if gg == g and ss == s)
    print(f"  CORE         : PASS {n('CORE','PASS')} / WARN {n('CORE','WARN')} / FAIL {n('CORE','FAIL')}")
    if not args.core_only:
        print(f"  AGENT-BROWSER: PASS {n('AGENT-BROWSER','PASS')} / WARN {n('AGENT-BROWSER','WARN')} / FAIL {n('AGENT-BROWSER','FAIL')}")

    if not core_ok:
        print("\n[FAIL] core 미통과 — 위 '다음 명령'을 실행하세요 (Python/Scrapling/Playwright).")
        return 2
    if not args.core_only and not ab_ok:
        print("\n[INCOMPLETE] core는 통과했으나 agent-browser 미완료 → 전체 설치 미완료.")
        print("  agent-browser는 이 프로젝트의 '표준 정찰 도구'입니다. 위 명령으로 설치 후 재검증하세요.")
        print("  (core만 급히 쓰려면 --core-only 로 재확인 가능하나, 표준 설치는 agent-browser 포함 full입니다.)")
        return 1
    print("\n[OK] 전체 통과 — 수집 환경 준비 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
