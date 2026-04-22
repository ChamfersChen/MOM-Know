from __future__ import annotations

import importlib
import sys


def _reset_toolkit_modules() -> None:
    """清理已加载模块，确保按最新环境变量重新执行工具注册逻辑。"""
    for module_name in list(sys.modules):
        if module_name == "yuxi.config" or module_name.startswith("yuxi.config."):
            sys.modules.pop(module_name, None)
        if module_name.startswith("yuxi.agents.toolkits"):
            sys.modules.pop(module_name, None)


def test_java_tools_not_registered_when_java_access_disabled(monkeypatch):
    monkeypatch.setenv("JAVA_ACCESS", "false")
    _reset_toolkit_modules()

    importlib.import_module("yuxi.agents.toolkits")

    registry = importlib.import_module("yuxi.agents.toolkits.registry")
    tool_names = {tool.name for tool in registry.get_all_tool_instances()}

    assert "call_mom_api" not in tool_names
    assert "list_mom_endpoints" not in tool_names
