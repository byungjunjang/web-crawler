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
DOC_FILES = [
    REPO / "CLAUDE.md",
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


# ── 4) 문서의 `.css(...)` 호출 kwargs 가 실제 Selector.css 시그니처에 있는가 ──
# 2026-09-01 books.toscrape.com 수집 중 실측:
#   TypeError: Selector.css() got an unexpected keyword argument 'storage_args'
# 문서의 자가치유 예시가 `page.css(SEL, auto_save=True, storage_args={...})` 였는데,
# requirements.txt 가 고정한 scrapling 0.4.x 의 `Selector.css` 는
# (selector, identifier, adaptive, auto_save, percentage) 만 받는다. storage_args 는
# `Selector.__init__` / `Fetcher.configure()` 쪽 인자다. import 검사(1)로는 잡히지 않고
# 런타임에만 죽는 부류라 호출 kwargs 를 시그니처와 직접 대조한다.
#
# scrapling_reference.md 는 DOC_FILES(실행 계약 문서) 에 없지만 자가치유 예시를 담고
# 있어 이 검사에만 추가한다.

CSS_DOC_FILES = DOC_FILES + [REPO / "scripts/scrapling_reference.md"]

_PLACEHOLDER = re.compile(r"<[^<>\n\"']*>")


def _parse_doc_block(block: str):
    """ast 로 파싱. `<URL>` 같은 문자열 밖 자리표시자는 이름으로 바꿔 재시도한다."""
    try:
        return ast.parse(block)
    except SyntaxError:
        pass
    try:
        return ast.parse(_PLACEHOLDER.sub("_PLACEHOLDER_", block))
    except SyntaxError:
        return None


def _documented_css_kwargs():
    """(문서, 블록번호, 호출 kwargs 튜플) — `.css(` 호출 중 kwargs 가 있는 것만."""
    out = []
    for path in CSS_DOC_FILES:
        if not path.exists():
            continue
        doc = path.relative_to(REPO).as_posix()
        text = path.read_text(encoding="utf-8")
        for i, block in enumerate(_PY_BLOCK.findall(text)):
            tree = _parse_doc_block(block)
            assert tree is not None, f"{doc} 블록 {i}: 자리표시자 치환 후에도 파싱 실패"
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "css"):
                    continue
                kws = tuple(sorted(k.arg for k in node.keywords if k.arg))
                if kws:
                    out.append((doc, i, kws))
    return sorted(set(out))


CSS_KWARG_CALLS = _documented_css_kwargs()


def test_css_kwarg_calls_were_collected():
    """자가치유 예시(auto_save/adaptive) 가 문서에 있으니 최소 1건은 잡혀야 한다."""
    assert CSS_KWARG_CALLS, "문서에서 kwargs 있는 `.css(` 호출을 못 찾았다 — 수집기가 깨졌다"


@pytest.mark.parametrize("doc,idx,kwargs", CSS_KWARG_CALLS,
                         ids=[f"{d}#{i}:css({','.join(k)})" for d, i, k in CSS_KWARG_CALLS])
def test_documented_css_kwargs_exist_in_selector_signature(doc, idx, kwargs):
    """문서가 `.css(...)` 에 넘기는 키워드가 설치된 scrapling 의 Selector.css 에 있는가.

    이 검사가 있었으면 `storage_args=` 는 커밋되지 못했다. 네트워크를 타지 않는다 —
    시그니처만 본다. 수신자를 정적으로 못 가르므로 Selector.css(원소) 기준이며,
    Selectors.css(목록) 는 그 부분집합(adaptive 없음) 이라 목록에 대고 adaptive=
    를 쓰는 예시는 따로 잡지 않는다.
    """
    import inspect

    from scrapling.parser import Selector

    allowed = set(inspect.signature(Selector.css).parameters) - {"self"}
    unknown = [k for k in kwargs if k not in allowed]
    assert not unknown, (
        f"{doc} 블록 {idx}: `.css({', '.join(unknown)}=...)` — Selector.css 는 "
        f"{sorted(allowed)} 만 받는다. 실행하면 TypeError. 저장소 경로는 "
        f"Fetcher.configure(adaptive=True, storage_args=...) 또는 "
        f"Selector(..., adaptive=True, storage_args=...) 로 넘긴다"
    )
