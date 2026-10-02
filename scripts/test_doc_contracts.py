"""문서가 코드와 어긋나면 CI 가 잡는다.

이 파일이 있는 이유: 2026-08-21 회귀 테스트에서 **문서에 적힌 대로 하면 죽는** 코드가
세 건 나왔다. 셋 다 master 부터 있었고, 셋 다 사람이 실제로 따라 하다 막혀야만 발견됐다.

  - `from scrapling.fetchers import AsyncFetcherSession`  → 그런 이름이 없다 (ImportError)
  - `from chrome_cdp import CDPSession`                   → 그런 이름이 없다 (ImportError)
  - `session.cookies.update(jar)`                         → _SyncSessionLogic 에 .cookies 없음

앞의 둘은 import 해석으로, 셋째는 래퍼 반환값의 속성 검사로 잡힌다.
네 번째 검사는 문서의 enum 이 분류기가 아는 값의 부분집합인지 본다 — 문서에만 있는 값을
적으면 `save()` 가 ConsentRequired 로 거부하기 때문이다.

전부 실행하는 게 아니라 **해석 가능한 부분만** 본다. 코드블록에는 `<URL>` 같은
자리표시자가 있어 통째 실행은 애초에 불가능하다.
"""
import ast
import importlib
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# 실행 계약을 담은 문서. .codex 는 .claude 의 생성물이라 원본만 본다.
# docs/crawl-reference.md 는 2026-10-02 에 CLAUDE.md 에서 옮겨온 프로필 저장/쿠키 python
# 블록을 담고 있다 — 목록에서 빼면 그 블록들이 드리프트 검사 사각지대로 떨어진다.
DOC_FILES = [
    REPO / "CLAUDE.md",
    REPO / "docs/crawl-reference.md",
    REPO / "AGENTS.md",
    REPO / "README.md",
    REPO / ".claude/skills/web-crawler/SKILL.md",
    REPO / ".claude/skills/web-crawler/references/fetcher-patterns.md",
    REPO / ".claude/skills/web-crawler/references/antibot-strategies.md",
    REPO / ".claude/skills/web-crawler/references/troubleshooting.md",
]

_PY_BLOCK = re.compile(r"^```python\n(.*?)^```", re.S | re.M)


def _python_blocks():
    """(문서경로, 블록번호, 코드) 목록."""
    out = []
    for path in DOC_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for i, block in enumerate(_PY_BLOCK.findall(text)):
            out.append((path.relative_to(REPO).as_posix(), i, block))
    return out


BLOCKS = _python_blocks()


def test_docs_actually_contain_python_blocks():
    """수집기가 0개를 훑고 조용히 통과하는 상태를 막는다."""
    assert len(BLOCKS) >= 20, f"문서 python 블록이 {len(BLOCKS)}개뿐 — 수집기가 깨졌을 수 있다"


# ── 1) 문서가 import 하는 이름이 실제로 존재하는가 ──────────────────────────

def _import_targets():
    """(문서, 모듈, 심볼) — 심볼이 None 이면 모듈 자체."""
    targets = []
    for doc, idx, block in BLOCKS:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            # 자리표시자(<URL>) 때문에 파싱이 안 되는 블록은 줄 단위로 훑는다
            for line in block.splitlines():
                line = line.strip()
                m = re.match(r"^from\s+([\w.]+)\s+import\s+(.+)$", line)
                if m:
                    mod = m.group(1)
                    for name in m.group(2).split("#")[0].split(","):
                        name = name.strip()
                        if name and name != "*":
                            targets.append((doc, mod, name))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name != "*":
                        targets.append((doc, node.module, alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    targets.append((doc, alias.name, None))
    # 중복 제거 (문서는 같은 import 를 여러 번 쓴다)
    return sorted(set(targets))


IMPORT_TARGETS = _import_targets()


def test_import_targets_were_collected():
    assert IMPORT_TARGETS, "문서에서 import 문을 하나도 못 찾았다 — 수집기가 깨졌다"


@pytest.mark.parametrize("doc,module,symbol", IMPORT_TARGETS,
                         ids=[f"{d}:{m}.{s}" for d, m, s in IMPORT_TARGETS])
def test_documented_import_resolves(doc, module, symbol):
    """문서가 시키는 import 가 실제로 되는가.

    이 검사가 있었으면 `AsyncFetcherSession` 과 `CDPSession` 은 커밋되지 못했다.
    """
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:                      # pragma: no cover
        pytest.fail(f"{doc}: `import {module}` 실패 — {exc}")

    if symbol is None:
        return
    assert hasattr(mod, symbol), (
        f"{doc}: `from {module} import {symbol}` — {module} 에 {symbol} 이 없다. "
        f"문서가 존재하지 않는 이름을 시키고 있다"
    )


# ── 2) 래퍼 반환값에 대고 부르는 속성이 실제로 있는가 ────────────────────────
# `session.cookies.update(jar)` 가 문서에 살아 있던 이유는, import 는 멀쩡하고
# **런타임에만** 죽기 때문이다. 우리 래퍼가 돌려주는 객체는 테스트에서 만들 수 있으므로
# 문서가 그 객체에 대고 부르는 속성만 따로 검사한다.

_SESSION_ATTR = re.compile(r"\bsession\.([A-Za-z_][A-Za-z0-9_]*)")


def _strip_comments(block: str) -> str:
    """주석은 실행되지 않는다 — '이렇게 하지 말라' 는 설명까지 검사하면 오탐이 난다.

    문자열 리터럴 안의 `#` 까지 정확히 가르지는 않는다. 이 검사가 보는 것은
    `session.<attr>` 호출이고 그게 문자열 안에 있을 일은 없다.
    """
    return "\n".join(line.split("#", 1)[0] for line in block.splitlines())


def _documented_session_attrs():
    attrs = set()
    for doc, idx, block in BLOCKS:
        if "plain_session()" not in block:
            continue
        for name in _SESSION_ATTR.findall(_strip_comments(block)):
            attrs.add((doc, name))
    return sorted(attrs)


SESSION_ATTRS = _documented_session_attrs()


def test_session_attr_collection_is_not_empty():
    assert SESSION_ATTRS, "plain_session() 을 쓰는 문서 블록을 못 찾았다 — 수집기가 깨졌다"


@pytest.mark.parametrize("doc,attr", SESSION_ATTRS, ids=[f"{d}:session.{a}" for d, a in SESSION_ATTRS])
def test_documented_session_attribute_exists(doc, attr):
    """`with plain_session() as session:` 블록이 부르는 session.<attr> 이 실제로 있는가.

    이 검사가 있었으면 `session.cookies.update(...)` 는 커밋되지 못했다.
    네트워크를 타지 않는다 — 세션 객체를 만들기만 한다.
    """
    from utils import plain_session

    with plain_session() as session:
        assert hasattr(session, attr), (
            f"{doc}: 문서가 `session.{attr}` 를 부르는데 "
            f"{type(session).__name__} 에는 그 속성이 없다"
        )


# ── 3) 문서의 값 목록이 분류기가 아는 값의 부분집합인가 ──────────────────────
# 문서에만 있는 값을 그대로 적으면 save() 가 ConsentRequired 로 거부한다.
# (반대 방향 — 레지스트리에만 있는 값 — 은 오류가 아니다. 문서는 추린 목록이다.)

_ENUM_LINE = re.compile(
    r'"(fetcher_type|antibot_strategy)"\s*:\s*"<([^">]+)>"'
)


def _documented_enum_values():
    out = []
    for path in DOC_FILES:
        if not path.exists():
            continue
        for field, body in _ENUM_LINE.findall(path.read_text(encoding="utf-8")):
            for value in body.split("|"):
                value = value.strip()
                if value:
                    out.append((path.relative_to(REPO).as_posix(), field, value))
    return sorted(set(out))


ENUM_VALUES = _documented_enum_values()


def test_enum_values_were_collected():
    assert ENUM_VALUES, "문서에서 fetcher_type/antibot_strategy 목록을 못 찾았다"


@pytest.mark.parametrize("doc,field,value", ENUM_VALUES,
                         ids=[f"{d}:{f}={v}" for d, f, v in ENUM_VALUES])
def test_documented_enum_value_is_known_to_classifier(doc, field, value):
    """문서가 제시하는 값을 그대로 적었을 때 분류기가 알아듣는가.

    모르는 값이면 save() 가 ConsentRequired 로 거부한다 — 문서를 따랐는데 저장이 막힌다.
    """
    from profile_policy import TOOLS, _norm

    key = _norm(value)
    assert key in TOOLS, (
        f"{doc}: {field} 목록의 `{value}` 가 profile_policy.TOOLS 에 없다. "
        f"문서를 따라 적으면 save() 가 거부한다 — 목록에서 빼거나 TOOLS 에 등록하라"
    )
