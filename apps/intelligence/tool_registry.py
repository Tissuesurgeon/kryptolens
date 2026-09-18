from __future__ import annotations

from apps.cmc.adapter import CMCAdapter, CMCCall
from apps.intelligence.permissions import require_sensitivity
from apps.intelligence.tools import (
    CMC_TOOL_NAMES,
    TOOL_GROUPS,
    ToolPermissionError,
    dispatch_cmc,
    require_tool,
    tool_allowed,
)

DISABLED_SLOTS = frozenset({"on_chain", "onchain", "news", "derivatives", "dex", "rwa"})


def registry_names() -> tuple[str, ...]:
    return CMC_TOOL_NAMES


def grouped_registry() -> dict[str, tuple[str, ...]]:
    return dict(TOOL_GROUPS)


def tool_in_registry(name: str) -> bool:
    return name in CMC_TOOL_NAMES or name in DISABLED_SLOTS


def invoke(adapter: CMCAdapter, name: str, permissions: dict | None, **kwargs) -> CMCCall:
    require_sensitivity(name)
    if name in DISABLED_SLOTS:
        raise ToolPermissionError(f"{name} is not available yet.")
    require_tool(permissions, name)
    return dispatch_cmc(adapter, name, permissions, **kwargs)


def permitted_tools(permissions: dict | None) -> list[str]:
    return [name for name in CMC_TOOL_NAMES if tool_allowed(permissions, name) and name not in DISABLED_SLOTS]
