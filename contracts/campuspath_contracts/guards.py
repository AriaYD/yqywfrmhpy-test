"""边界扫描器：递归遍历模型字段图，断言某些字段**根本不存在**。

为什么需要这个而不是靠 code review：
``extra="forbid"`` 只挡住运行时多传的字段，挡不住有人日后在
``AvailabilityBlock`` 上加一个 ``title: str``。那样 B5（Calendar Detail
Over-collection）会在没有任何测试变红的情况下被破坏。

本模块把"这些字段不许出现在这条链路上"变成可执行断言，
由 ``tests/test_boundary_guards.py`` 在每次提交时运行。

按 Plan §10 H5：扫描器自身必须用**已知会失败的样例**验证过——
见 ``tests/test_boundary_guards.py::test_scanner_catches_known_bad_model``。
"""

from __future__ import annotations

import dataclasses
from typing import Any, Iterator, get_args, get_origin

from pydantic import BaseModel

__all__ = [
    "FieldNode",
    "walk_fields",
    "find_forbidden_fields",
    "assert_no_forbidden_fields",
    "BoundaryViolation",
    "CALENDAR_DETAIL_TERMS",
    "STUDENT_IDENTITY_TERMS",
    "WELLBEING_TERMS",
    "FREE_TEXT_TERMS",
    "RANKING_TERMS",
    "CREDENTIAL_TERMS",
]


@dataclasses.dataclass(frozen=True)
class FieldNode:
    """模型字段图中的一个节点。"""

    path: str
    name: str
    owner: str
    annotation: Any

    def __str__(self) -> str:  # pragma: no cover - 仅用于报错信息
        return f"{self.path} ({self.owner}.{self.name})"


class BoundaryViolation(AssertionError):
    """某条数据域边界被字段级破坏。"""


def _unwrap(annotation: Any) -> Iterator[Any]:
    """展开 Optional / list / dict / Annotated，产出其中所有具体类型。"""
    origin = get_origin(annotation)
    if origin is None:
        yield annotation
        return
    for arg in get_args(annotation):
        if arg is type(None) or isinstance(arg, str):
            continue
        yield from _unwrap(arg)


def walk_fields(
    model: type[BaseModel],
    *,
    _prefix: str = "",
    _seen: set[type[BaseModel]] | None = None,
) -> Iterator[FieldNode]:
    """深度优先遍历 ``model`` 及其嵌套模型的所有字段。

    循环引用（A supersedes A）只展开一次，避免无限递归。
    """
    seen = _seen if _seen is not None else set()
    if model in seen:
        return
    if not getattr(model, "__pydantic_complete__", True):
        # 前向引用没解析时 model_fields 里的注解还是字符串，扫描器会一无所获。
        # 静默失明比报错危险得多：边界检查会"通过"。
        raise BoundaryViolation(
            f"{model.__name__} 的前向引用尚未解析（未调用 model_rebuild），"
            "此时字段扫描不可信"
        )
    seen = seen | {model}

    for name, field in model.model_fields.items():
        path = f"{_prefix}{model.__name__}.{name}" if not _prefix else f"{_prefix}.{name}"
        yield FieldNode(path=path, name=name, owner=model.__name__, annotation=field.annotation)
        for candidate in _unwrap(field.annotation):
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                yield from walk_fields(candidate, _prefix=path, _seen=seen)


def find_forbidden_fields(
    model: type[BaseModel],
    forbidden_terms: frozenset[str] | set[str],
    *,
    allow_paths: frozenset[str] | set[str] = frozenset(),
) -> list[FieldNode]:
    """返回字段名中包含任一 ``forbidden_terms`` 的所有节点。

    匹配用的是**子串**而非全等：``calendar_event_title`` 也应该被 ``title`` 抓到。
    ``allow_paths`` 用于显式豁免（例如引用 id 而非内容），必须写全路径，
    这样豁免本身在 diff 里是可见的。
    """
    hits: list[FieldNode] = []
    for node in walk_fields(model):
        if node.path in allow_paths:
            continue
        lowered = node.name.lower()
        if any(term in lowered for term in forbidden_terms):
            hits.append(node)
    return hits


def assert_no_forbidden_fields(
    model: type[BaseModel],
    forbidden_terms: frozenset[str] | set[str],
    *,
    allow_paths: frozenset[str] | set[str] = frozenset(),
    reason: str = "",
) -> None:
    hits = find_forbidden_fields(model, forbidden_terms, allow_paths=allow_paths)
    if hits:
        listed = "\n  ".join(str(h) for h in hits)
        raise BoundaryViolation(
            f"{model.__name__} 携带了被禁止的字段（{reason}）：\n  {listed}"
        )


# --------------------------------------------------------------------------
# 各条边界的禁用词表
# --------------------------------------------------------------------------

#: B5 Calendar Detail Over-collection：日历原始事件字段止步于 Capacity & Calendar Service。
CALENDAR_DETAIL_TERMS = frozenset(
    {"title", "summary", "attendee", "participant", "organizer_email", "location",
     "description", "note", "body", "agenda", "conference", "meeting_link"}
)

#: B10 MetricTuple Field Leakage：出域元组不得携带任何可指向个人的字段。
STUDENT_IDENTITY_TERMS = frozenset(
    {"student_id", "student_name", "name", "email", "phone", "sid", "netid",
     "profile", "goal_text", "reflection", "evidence", "note", "calendar"}
)

#: B4 Private Reflection Exposure / §8.9.2：wellbeing 字段不得进入聚合或校方通路。
WELLBEING_TERMS = frozenset(
    {"sleep", "wellbeing", "recovery", "exercise", "activity_minutes",
     "outreach", "counsel", "burnout", "mood", "health"}
)

#: 向 Aggregation Service 的输入不得含自由文本载体。
FREE_TEXT_TERMS = frozenset(
    {"text", "comment", "freeform", "free_text", "private_text", "narrative",
     "verbatim", "raw"}
)

#: Spec §8.1：A2 的 AnnotatedCourseCandidate 不含任何排序分数。排序只属于 A5。
RANKING_TERMS = frozenset({"score", "rank", "ranking", "utility", "priority_value", "weight"})

#: 「Calendar Token 不进任何 LLM 上下文」是架构六条之一，此前在契约层
#: **没有一个能工作的字段级检查**：那条断言写的是集合相等（只命中完全同名的
#: 字段），于是 ``oauth_token`` / ``bearer`` 直接放行，而 CALENDAR_DETAIL_TERMS
#: 里根本没有凭据类词。
CREDENTIAL_TERMS = frozenset(
    {"token", "credential", "secret", "password", "bearer", "api_key", "apikey",
     "private_key", "client_secret", "refresh", "access_key"}
)


# --------------------------------------------------------------------------
# 零 LLM 断言（B11 的类型层前哨；构建期完整检查在 CI）
# --------------------------------------------------------------------------

#: 禁止在确定性服务平面中被 import 的模块前缀（Spec §8.1 表末、Plan D6 B11）。
#:
#: 注意这里的口径是"**任何**模型 SDK"，与 B12 的"AI Studio 路径"不是一回事：
#: `vertexai` 是我们唯一允许的模型调用方式，但确定性服务照样不许 import 它。
MODEL_SDK_MODULES = frozenset(
    {
        "google.generativeai",        # 旧版 AI-Studio-only SDK  ai-studio-denylist
        "google.genai",               # 现行统一 SDK，两种后端都支持，见下方 B12 说明
        "google.ai.generativelanguage",
        "langchain_google_genai",
        "vertexai",
        "google.cloud.aiplatform",
        "google.adk",
        "openai",
        "anthropic",
        "litellm",
        "transformers",
    }
)


def imported_model_sdks(module_names: list[str] | set[str]) -> set[str]:
    """从一组已导入模块名中挑出模型 SDK。供 CI 的依赖树扫描复用。"""
    hits: set[str] = set()
    for name in module_names:
        for banned in MODEL_SDK_MODULES:
            if name == banned or name.startswith(banned + "."):
                hits.add(name)
    return hits


# --------------------------------------------------------------------------
# B12：AI Studio 路径（这条是关于**钱**的，不是关于零 LLM）
# --------------------------------------------------------------------------
#
# 容易搞混的一点：`google-genai`（`from google import genai`）**两种后端都支持**。
#   genai.Client(vertexai=True, project=..., location=...)  → Vertex，吃赠金 ✅
#   genai.Client(api_key=...)  → AI Studio，直扣个人卡 ❌  ai-studio-denylist
# 所以 B12 要禁的不是这个包，而是**它的 AI Studio 用法**。
# 一刀切禁掉包名会在 WP6 挡住我们自己该走的路。
#
# 旧包 `google.generativeai` 没有 Vertex 后端，因此整体禁用。  ai-studio-denylist

#: 出现即等于走 AI Studio 认证——无论用哪个 SDK。
AI_STUDIO_AUTH_TERMS = frozenset({"GOOGLE_API_KEY", "GEMINI_API_KEY"})  # ai-studio-denylist

#: 只能是 AI Studio 的包与端点。
AI_STUDIO_ONLY_MARKERS = frozenset(
    {
        "google.generativeai",              # ai-studio-denylist
        "generativelanguage.googleapis.com",  # ai-studio-denylist
    }
)

#: 同时支持两种后端的 SDK 构造点。出现它就必须能看到 `vertexai=True`。
DUAL_BACKEND_CLIENT_MARKER = "genai.Client("
VERTEX_BACKEND_MARKER = "vertexai=True"

#: 同行标注这个词即视为正当引用（禁用词表、拦截器自身的测试样例）。
DENYLIST_MARKER = "ai-studio-denylist"


def ai_studio_violations(source: str, *, proximity_lines: int = 3) -> list[str]:
    """扫描一段源码，返回走 AI Studio 路径的证据。

    三类命中：

    1. 只属于 AI Studio 的包名或端点；
    2. API key 环境变量（那是 AI Studio 的认证方式）；
    3. ``genai.Client(`` 附近 ``proximity_lines`` 行内看不到 ``vertexai=True``
       —— 双后端 SDK 默认走 AI Studio，**没写就是走错了**。

    带 ``ai-studio-denylist`` 同行标注的行一律放行：禁用词表本身要能提到这些串。
    """
    lines = source.splitlines()
    hits: list[str] = []
    for index, line in enumerate(lines, start=1):
        if DENYLIST_MARKER in line:
            continue
        for marker in sorted(AI_STUDIO_ONLY_MARKERS):
            if marker in line:
                hits.append(f"{index}: 使用了只属于 AI Studio 的 {marker}")
        for term in sorted(AI_STUDIO_AUTH_TERMS):
            if term in line:
                hits.append(f"{index}: 出现 {term}——那是 AI Studio 的认证方式，赠金不覆盖")
        if DUAL_BACKEND_CLIENT_MARKER in line:
            window = "\n".join(lines[index - 1 : index - 1 + proximity_lines])
            if VERTEX_BACKEND_MARKER not in window:
                hits.append(
                    f"{index}: {DUAL_BACKEND_CLIENT_MARKER} 附近 {proximity_lines} 行内没有 "
                    f"{VERTEX_BACKEND_MARKER}——双后端 SDK 默认走 AI Studio"
                )
    return hits
