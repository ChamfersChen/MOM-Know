from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class KnowledgeBaseConfig:
    """知识库类型实现执行一次操作所需的最小配置。"""

    kb_id: str
    kb_type: str
    embedding_model_spec: str | None = None
    query_params: dict[str, Any] = field(default_factory=dict)
    additional_params: dict[str, Any] = field(default_factory=dict)

    @property
    def query_options(self) -> dict[str, Any]:
        """返回持久化查询参数中的 options。"""
        options = self.query_params.get("options")
        return options if isinstance(options, dict) else {}
