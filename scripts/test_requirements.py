"""requirements.txt 가 '직접 import 하는 것은 직접 선언한다' 원칙을 지키는지 검사."""
from pathlib import Path
import re

import pytest

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"


def _declared():
    """주석·빈 줄을 뺀 '패키지명 -> 원문 줄' 매핑."""
    out = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        name = stripped.split(">=")[0].split("==")[0].split("[")[0].strip().lower()
        out[name] = stripped
    return out


@pytest.mark.parametrize("package", ["scrapling", "playwright", "curl_cffi", "patchright",
                                     "protego", "openpyxl", "pytest"])
def test_direct_imports_are_declared(package):
    assert package in _declared(), (
        f"{package} 를 코드가 직접 쓰는데 requirements.txt 에 선언되지 않았습니다"
    )


def _constraint(package: str) -> str:
    """선언된 줄에서 버전 제약식만 떼어낸다 (패키지명·extras 는 제외).

    `KeyError` 로 죽지 않는다 (2026-10-01 독립 리뷰 [Low]) — 패키지가
    declarations 에서 사라지면 아래 테스트가 **메시지와 함께** 실패해야 한다.
    예외로 죽으면 왜 깨졌는지 읽는 사람이 모른다.
    """
    line = _declared().get(package, "")
    for index, char in enumerate(line):
        if char in "<>=":
            return line[index:].strip()
    return ""


def _version_upper_bound(constraint: str) -> str | None:
    """**버전** 상한만 뽑는다 — 환경 마커의 `<` 로 통과하지 못하게 한다.

    `python_version<"3.14"` 에도 `<` 가 있으므로 substring 검사만 하면
    "버전 상한이 없는데 통과"하는 구멍이 생긴다(독립 리뷰 finding).
    """
    # 환경 마커는 `;` 뒤에 온다(PEP 508). 앞부분만 본다 — `python_version<3.14`
    # 같은 마커의 `<` 를 버전 상한으로 오인하지 않는다 (2026-10-01 독립 리뷰 [Low]).
    specifier = constraint.split(";", 1)[0]
    match = re.search(r"<\s*(\d[\w.]*)", specifier)
    return match.group(1) if match else None


def test_version_upper_bound_ignores_environment_markers():
    """환경 마커의 `<` 를 버전 상한으로 오인하지 않는다 (2026-10-01 독립 리뷰 [Low]).

    `python_version<"3.14"` 는 마커지 상한이 아니다. 이 경로를 실행하는 테스트가
    없어서, 실수로 마커를 인용 없이(`python_version<3.14`) 쓰면 오인할 수 있었다.
    마커는 늘 문자열 리터럴을 요구하므로 실제로는 무해하지만 못 박아 둔다.
    """
    assert _version_upper_bound('>=1.62,<1.64; python_version<"3.14"') == "1.64"
    assert _version_upper_bound('>=1.62; python_version<"3.14"') is None
    assert _version_upper_bound('>=1.62') is None
    # 2026-10-01 독립 리뷰 [Low]: 마커가 **인용 없이** 오면(`python_version<3.14`,
    # 잘못된 PEP 508 이지만 파싱은 된다) `;` 뒤도 버전 제약으로 오인해 "3.14" 를
    # 상한으로 반환했다. `;` 앞만 보게 고쳐 그 경로를 실제로 고정한다.
    assert _version_upper_bound('>=1.62; python_version<3.14') is None


def test_playwright_has_upper_bound():
    """상한은 1.64 가 나왔을 때 patchright 를 두고 독주하는 브레이크다(ADR-002).

    결합 그 자체를 강제하지는 못한다 — 제약식이 같아도 해석된 *패치* 버전은
    달라질 수 있다(patchright 만 1.60.1/1.61.2/1.62.3 같은 추가 패치가 있다).
    강제하는 것은 "한쪽만 상한을 올리는 변경"이다. 그건 이 검사가 먼저 잡는다.
    """
    upper = _version_upper_bound(_constraint("playwright"))
    assert upper is not None, (
        f"playwright 에 버전 상한이 없습니다 (제약식={_constraint('playwright')!r}) — "
        "1.64 출시에 patchright 를 두고 독주할 수 있습니다. "
        "requirements.txt 의 두 줄에 같은 상한을 두세요"
    )
    assert _version_upper_bound(_constraint("patchright")) == upper, (
        f"상한이 다릅니다 — playwright={upper} vs patchright="
        f"{_version_upper_bound(_constraint('patchright'))} (ADR-002)"
    )


def test_playwright_and_patchright_constraints_identical():
    """두 줄의 제약식을 같게 둔다 — 한쪽만 고치는 변경을 이게 먼저 잡는다."""
    playwright = _constraint("playwright")
    patchright = _constraint("patchright")
    assert playwright and patchright, (
        f"제약식이 비었습니다 (playwright={playwright!r}, patchright={patchright!r}) — "
        "두 줄 모두에 버전 제약을 적어야 결합이 표현된다 (ADR-002)"
    )
    assert playwright == patchright, (
        f"playwright={playwright!r} 와 patchright={patchright!r} 가 다릅니다 — "
        "두 줄의 제약식을 같게 두세요 (ADR-002)"
    )


def test_scrapling_has_upper_bound():
    """pre-1.0 이고 v0.3 breaking 전력이 있어 상한이 필수다."""
    assert "<0.5" in _declared()["scrapling"], (
        "scrapling 에 상한(<0.5)이 없습니다 — 0.5 가 나오면 생성 스크립트가 일괄로 깨집니다"
    )


def test_protego_comment_is_true():
    """requirements.txt 의 주석이 실제 코드와 일치하는지.

    G3 의 재발 방지 — protego 는 '런타임에서 사용' 이라고 적혀 있으면서 실제로는
    어디서도 import 되지 않은 채 오래 방치됐다. 주석이 이름을 대면 그 이름은 존재해야 한다.
    """
    import utils
    assert hasattr(utils, "check_robots"), (
        "requirements.txt 의 protego 주석이 scripts/utils.py check_robots() 를 가리키는데 "
        "그 함수가 없습니다 — 주석이 사실과 다릅니다"
    )
